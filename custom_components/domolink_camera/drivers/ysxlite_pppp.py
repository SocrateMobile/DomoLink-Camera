"""Driver for YsxLite / iLnk / PPPP Wi-Fi mini cameras (A9, X5, etc.)."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from typing import Any, Callable

import aiohttp

from .base import BaseCameraDriver
from ..const import (
    DEFAULT_PPPP_DISCOVERY_PORT,
    PPPP_CMD_IRCUT_ONOFF,
    PPPP_CMD_LIVE_VIDEO_START,
    PPPP_CMD_LIVE_VIDEO_STOP,
    PPPP_CMD_SNAPSHOT_GET,
    PPPP_CMD_SYSTEM_REBOOT,
    STATUS_CONNECTING,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_STREAMING,
)

_LOGGER = logging.getLogger(__name__)

# PPPP Packet Magic Headers
PPPP_MAGIC = b"PPPP"
ILNK_MAGIC = b"\x4c\x4e\x4b\x01"


class YsxLiteProtocol(asyncio.DatagramProtocol):
    """UDP protocol handler for YsxLite PPPP packets."""

    def __init__(self, driver: YsxLiteDriver) -> None:
        """Initialize protocol."""
        self.driver = driver
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        """UDP socket connected."""
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Handle incoming UDP datagram."""
        self.driver.handle_udp_packet(data, addr)

    def error_received(self, exc: Exception) -> None:
        """Handle UDP error."""
        _LOGGER.warning("[%s] UDP Error received: %s", self.driver.camera_id, exc)

    def connection_lost(self, exc: Exception | None) -> None:
        """UDP connection closed."""
        self.transport = None


class YsxLiteDriver(BaseCameraDriver):
    """Driver implementing iLnk / PPPP UDP communication for YsxLite cameras."""

    def __init__(
        self,
        camera_id: str,
        config: dict[str, Any],
        on_frame_callback: Callable[[bytes], None] | None = None,
    ) -> None:
        """Initialize YsxLite driver."""
        super().__init__(camera_id, config, on_frame_callback)
        self.pppp_port = int(config.get("port", DEFAULT_PPPP_DISCOVERY_PORT))
        self.http_port = int(config.get("http_port", 80))
        self.device_id = config.get("device_id", "")
        self.transport: asyncio.DatagramTransport | None = None
        self.protocol: YsxLiteProtocol | None = None
        self._seq = 0
        self._frame_buffer = bytearray()
        self._is_receiving_frame = False
        self._stream_task: asyncio.Task | None = None
        self._poll_task: asyncio.Task | None = None
        self._pending_snapshot: asyncio.Future[bytes] | None = None

    async def async_connect(self) -> bool:
        """Initialize UDP socket and handshake with camera."""
        if not self.host:
            _LOGGER.error("[%s] Missing host IP for YsxLite camera", self.camera_id)
            self.status = STATUS_OFFLINE
            return False

        self.status = STATUS_CONNECTING
        loop = asyncio.get_running_loop()

        try:
            # Create UDP endpoint bound to an ephemeral port
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: YsxLiteProtocol(self),
                local_addr=("0.0.0.0", 0),
            )
            self.transport = transport
            self.protocol = protocol
            self.is_connected = True
            self.status = STATUS_ONLINE

            # Send ping/handshake to the camera
            await self._send_pppp_cmd(PPPP_CMD_SNAPSHOT_GET)

            # Start periodic snapshot polling (every 10s) to keep thumbnail fresh
            if not self._poll_task or self._poll_task.done():
                self._poll_task = asyncio.create_task(self._periodic_snapshot_poll())

            _LOGGER.info(
                "[%s] Connected to YsxLite camera at %s:%s",
                self.camera_id,
                self.host,
                self.pppp_port,
            )
            return True
        except Exception as err:
            _LOGGER.error("[%s] Connection failed to %s: %s", self.camera_id, self.host, err)
            self.status = STATUS_OFFLINE
            self.is_connected = False
            return False

    async def async_disconnect(self) -> None:
        """Close UDP socket and stop background tasks."""
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()

        if self.is_streaming:
            await self.async_stop_stream()

        if self.transport:
            self.transport.close()
            self.transport = None
            self.protocol = None

        self.is_connected = False
        self.status = STATUS_OFFLINE

    def _build_packet(self, cmd: int, payload: bytes = b"") -> bytes:
        """Build binary PPPP / iLnk packet."""
        self._seq = (self._seq + 1) & 0xFFFF
        # Header: Magic (4B) + Cmd (2B) + Length (2B) + Seq (2B) + Payload
        header = PPPP_MAGIC + struct.pack(">HHH", cmd, len(payload), self._seq)
        return header + payload

    async def _send_pppp_cmd(self, cmd: int, payload: bytes = b"") -> None:
        """Send PPPP command packet over UDP."""
        if not self.transport:
            return
        packet = self._build_packet(cmd, payload)
        self.transport.sendto(packet, (self.host, self.pppp_port))

    def handle_udp_packet(self, data: bytes, addr: tuple[str, int]) -> None:
        """Process incoming packet from camera."""
        if not data:
            return

        # Check for direct JPEG payload (SOI = 0xFF 0xD8)
        if b"\xff\xd8" in data:
            start = data.find(b"\xff\xd8")
            end = data.find(b"\xff\xd9", start)
            if end != -1:
                # Complete JPEG within one datagram
                jpeg = data[start : end + 2]
                self._update_frame(jpeg)
                return

        # Multi-packet frame assembly
        if data.startswith(PPPP_MAGIC) or data.startswith(ILNK_MAGIC):
            if len(data) >= 10:
                _, cmd, length, _ = struct.unpack(">4sHHH", data[:10])
                payload = data[10 : 10 + length]

                if b"\xff\xd8" in payload:
                    self._frame_buffer = bytearray(payload[payload.find(b"\xff\xd8") :])
                    self._is_receiving_frame = True
                elif self._is_receiving_frame:
                    self._frame_buffer.extend(payload)

                if b"\xff\xd9" in self._frame_buffer:
                    end_idx = self._frame_buffer.find(b"\xff\xd9") + 2
                    jpeg = bytes(self._frame_buffer[:end_idx])
                    self._frame_buffer = bytearray()
                    self._is_receiving_frame = False
                    self._update_frame(jpeg)

    def _update_frame(self, jpeg: bytes) -> None:
        """Store new valid JPEG frame and notify callback."""
        if len(jpeg) < 100:
            return
        self.last_snapshot = jpeg
        self.last_snapshot_time = time.time()
        self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE

        if self._pending_snapshot and not self._pending_snapshot.done():
            self._pending_snapshot.set_result(jpeg)

        if self.on_frame_callback:
            self.on_frame_callback(jpeg)

    async def async_get_snapshot(self) -> bytes | None:
        """Request a fresh snapshot from camera."""
        if not self.is_connected:
            await self.async_connect()

        # If we have a very recent snapshot (< 3 sec old), return it immediately
        if self.last_snapshot and self.last_snapshot_time and (time.time() - self.last_snapshot_time < 3):
            return self.last_snapshot

        # Try requesting snapshot via UDP command
        try:
            loop = asyncio.get_running_loop()
            self._pending_snapshot = loop.create_future()
            await self._send_pppp_cmd(PPPP_CMD_SNAPSHOT_GET)
            # Wait up to 2.5 seconds for UDP response
            return await asyncio.wait_for(self._pending_snapshot, timeout=2.5)
        except (asyncio.TimeoutError, Exception):
            pass

        # Fallback: attempt HTTP snapshot if camera exposes port 80/8080/81
        http_snap = await self._fetch_http_snapshot()
        if http_snap:
            self.last_snapshot = http_snap
            self.last_snapshot_time = time.time()
            return http_snap

        # Return cached snapshot if available
        return self.last_snapshot

    async def _fetch_http_snapshot(self) -> bytes | None:
        """Fallback HTTP snapshot request for standard web-enabled firmwares."""
        paths = ["/snapshot.jpg", "/tmpfs/snap.jpg", "/cgi-bin/snapshot.cgi", "/action/snap"]
        async with aiohttp.ClientSession() as session:
            for p in paths:
                url = f"http://{self.host}:{self.http_port}{p}"
                try:
                    async with session.get(url, timeout=1.5) as resp:
                        if resp.status == 200 and "image" in resp.headers.get("Content-Type", ""):
                            return await resp.read()
                except Exception:
                    continue
        return None

    async def _periodic_snapshot_poll(self) -> None:
        """Background loop to periodically refresh the snapshot thumbnail."""
        while True:
            try:
                await asyncio.sleep(10)
                if not self.is_streaming:
                    await self._send_pppp_cmd(PPPP_CMD_SNAPSHOT_GET)
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("[%s] Periodic snapshot poll error: %s", self.camera_id, err)

    async def async_start_stream(self) -> None:
        """Start high-framerate live streaming."""
        self.is_streaming = True
        self.status = STATUS_STREAMING
        await self._send_pppp_cmd(PPPP_CMD_LIVE_VIDEO_START)

        # Send keep-alive packets every 3 seconds to prevent timeout
        if not self._stream_task or self._stream_task.done():
            self._stream_task = asyncio.create_task(self._stream_keepalive_loop())

    async def _stream_keepalive_loop(self) -> None:
        """Maintain stream session active."""
        while self.is_streaming:
            try:
                await asyncio.sleep(3)
                await self._send_pppp_cmd(PPPP_CMD_LIVE_VIDEO_START)
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("[%s] Stream keepalive error: %s", self.camera_id, err)

    async def async_stop_stream(self) -> None:
        """Stop high-framerate live streaming."""
        self.is_streaming = False
        self.status = STATUS_ONLINE
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        await self._send_pppp_cmd(PPPP_CMD_LIVE_VIDEO_STOP)

    async def async_set_night_vision(self, enabled: bool) -> bool:
        """Toggle infrared night vision."""
        payload = b"\x01" if enabled else b"\x00"
        await self._send_pppp_cmd(PPPP_CMD_IRCUT_ONOFF, payload)
        return True

    async def async_reboot(self) -> bool:
        """Reboot camera device."""
        await self._send_pppp_cmd(PPPP_CMD_SYSTEM_REBOOT)
        return True

    def get_capabilities(self) -> dict[str, Any]:
        """Return capabilities for YsxLite."""
        return {
            "night_vision": True,
            "ptz": False,
            "audio": True,
            "reboot": True,
        }
