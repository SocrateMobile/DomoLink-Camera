"""Generic RTSP / ONVIF / HTTP / MJPEG Camera Driver for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable
from urllib.parse import urlparse

import aiohttp

from .base import BaseCameraDriver, extract_jpegs_from_buffer
from .ha_proxy import HaProxyDriver
from ..const import (
    DEFAULT_HTTP_PORT,
    DEFAULT_RTSP_PORT,
    DRIVER_GENERIC_MJPEG,
    DRIVER_GENERIC_RTSP,
    STATUS_CONNECTING,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_STREAMING,
)

_LOGGER = logging.getLogger(__name__)


class GenericRtspDriver(BaseCameraDriver):
    """Driver for standard IP cameras using RTSP, HLS, MJPEG, or HTTP snapshots."""

    def __init__(
        self,
        camera_id: str,
        config: dict[str, Any],
        on_frame_callback: Callable[[bytes], None] | None = None,
        hass: Any = None,
    ) -> None:
        """Initialize generic RTSP/MJPEG driver."""
        super().__init__(camera_id, config, on_frame_callback)
        self.hass = hass
        self.driver_type = config.get("driver", DRIVER_GENERIC_RTSP)
        self.rtsp_port = int(config.get("port") or DEFAULT_RTSP_PORT)
        self.http_port = int(config.get("http_port") or DEFAULT_HTTP_PORT)
        self.stream_path = config.get("stream_path", "/live/ch0")
        self.snapshot_path = config.get("snapshot_path", "/snapshot.jpg")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self._configured_stream_url = config.get("stream_url") or ""
        self._web_hls_url = config.get("web_hls_url") or ""
        if self._web_hls_url:
            self._stream_url = self._web_hls_url
        elif self._configured_stream_url and self._configured_stream_url.startswith(("http://", "https://")) and ".m3u8" in self._configured_stream_url:
            self._stream_url = self._configured_stream_url
        elif str(self.host).startswith(("http://", "https://")) and ".m3u8" in str(self.host):
            self._stream_url = str(self.host)

        self._mjpeg_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._ha_delegate: HaProxyDriver | None = None

        if str(self.host).startswith("camera."):
            self._ha_delegate = HaProxyDriver(
                camera_id,
                config,
                hass=self.hass,
                on_frame_callback=self.notify_frame,
            )

    @property
    def rtsp_url(self) -> str:
        """Construct primary RTSP/RTSPS or stream URL with optional credentials."""
        if self._configured_stream_url:
            return self._configured_stream_url
        if str(self.host).lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
            return str(self.host)
        auth = f"{self.username}:{self.password}@" if self.username else ""
        path = self.stream_path if str(self.stream_path).startswith("/") else f"/{self.stream_path}"
        return f"rtsp://{auth}{self.host}:{self.rtsp_port}{path}"

    @property
    def primary_stream_url(self) -> str:
        """Return best available video stream URL."""
        if self._web_hls_url:
            return self._web_hls_url
        if self._configured_stream_url:
            return self._configured_stream_url
        if str(self.host).lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
            return str(self.host)
        if self.driver_type == DRIVER_GENERIC_MJPEG:
            path = self.stream_path if str(self.stream_path).startswith("/") else f"/{self.stream_path}"
            if path == "/live/ch0":
                path = "/stream"
            return f"http://{self.host}:{self.http_port}{path}"
        return self.rtsp_url

    @property
    def http_snapshot_url(self) -> str:
        """Construct HTTP snapshot URL."""
        lower_host = str(self.host).lower()
        if lower_host.startswith(("http://", "https://")):
            parsed = urlparse(str(self.host))
            return f"{parsed.scheme}://{parsed.netloc}{self.snapshot_path}"
        if lower_host.startswith(("rtsp://", "rtsps://")):
            parsed = urlparse(str(self.host))
            hostname = parsed.hostname or ""
            return f"http://{hostname}:{self.http_port}{self.snapshot_path}"
        return f"http://{self.host}:{self.http_port}{self.snapshot_path}"

    def _sync_from_delegate(self) -> None:
        """Mirror delegate state onto this driver."""
        if not self._ha_delegate:
            return
        self.is_connected = self._ha_delegate.is_connected
        self.is_streaming = self._ha_delegate.is_streaming
        self.status = self._ha_delegate.status
        self.last_snapshot = self._ha_delegate.last_snapshot
        self.last_snapshot_time = self._ha_delegate.last_snapshot_time
        self._stream_url = self._ha_delegate._stream_url

    async def _check_tcp_reachable(self) -> bool:
        """Test TCP connectivity to RTSP or HTTP port."""
        target = self.primary_stream_url
        parsed = urlparse(target)
        host = parsed.hostname or str(self.host)
        if not host or host.startswith("camera."):
            return False

        ports: list[int] = []
        if parsed.port:
            ports.append(parsed.port)
        elif parsed.scheme == "https":
            ports.append(443)
        elif parsed.scheme == "http":
            ports.append(self.http_port or 80)
        else:
            ports.extend([self.rtsp_port, self.http_port])

        for port in dict.fromkeys(p for p in ports if p):
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port), timeout=1.5
                )
                writer.close()
                await writer.wait_closed()
                return True
            except Exception:
                continue
        return False

    async def async_connect(self) -> bool:
        """Verify camera reachability and start background snapshot polling."""
        if self._ha_delegate:
            ok = await self._ha_delegate.async_connect()
            self._sync_from_delegate()
            return ok

        self.status = STATUS_CONNECTING
        snap = await self.async_get_snapshot()
        if snap:
            self.is_connected = True
            self.status = STATUS_ONLINE
            if not self._poll_task or self._poll_task.done():
                self._poll_task = asyncio.create_task(self._periodic_snapshot_poll())
            return True

        # Mark reachable if TCP port responds or valid remote HLS/RTSP stream URL is configured
        reachable = await self._check_tcp_reachable()
        if reachable or self._web_hls_url or self._configured_stream_url:
            self.is_connected = True
            self.status = STATUS_ONLINE
            if not self._poll_task or self._poll_task.done():
                self._poll_task = asyncio.create_task(self._periodic_snapshot_poll())
            return True

        self.is_connected = False
        self.status = STATUS_OFFLINE
        return False

    async def async_disconnect(self) -> None:
        """Disconnect and stop all background tasks."""
        if self._ha_delegate:
            await self._ha_delegate.async_disconnect()
            self._sync_from_delegate()
            return

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            self._poll_task = None

        await self.async_stop_stream()
        self.is_connected = False
        self.status = STATUS_OFFLINE

    async def _periodic_snapshot_poll(self) -> None:
        """Refresh snapshot periodically when idle."""
        while True:
            try:
                await asyncio.sleep(15)
                if not self.is_streaming:
                    await self.async_get_snapshot()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("[%s] Periodic snapshot poll error: %s", self.camera_id, err)

    async def _fetch_http_snapshot(self) -> bytes | None:
        """Attempt HTTP snapshot or single-frame extraction from HTTP MJPEG endpoint."""
        parsed = urlparse(self.http_snapshot_url)
        base_host = parsed.hostname or str(self.host)
        if not base_host or base_host.startswith("camera."):
            return None

        auth = aiohttp.BasicAuth(self.username, self.password) if self.username else None
        candidate_urls = [self.http_snapshot_url]
        if self.driver_type == DRIVER_GENERIC_MJPEG:
            candidate_urls.append(self.primary_stream_url)
        for p in ("/snapshot.jpg", "/snap.jpg", "/cgi-bin/snapshot.cgi", "/onvif-http/snapshot", "/capture"):
            candidate_urls.append(f"http://{base_host}:{self.http_port}{p}")

        timeout = aiohttp.ClientTimeout(total=2.5)
        shared_session = None
        owns_session = False
        try:
            if self.hass:
                from homeassistant.helpers.aiohttp_client import async_get_clientsession
                candidate = async_get_clientsession(self.hass)
                if isinstance(candidate, aiohttp.ClientSession) and not candidate.closed:
                    shared_session = candidate
        except Exception:
            shared_session = None

        try:
            if shared_session is None:
                shared_session = aiohttp.ClientSession(timeout=timeout)
                owns_session = True
            for url in dict.fromkeys(candidate_urls):
                if ".m3u8" in url:
                    continue
                try:
                    async with shared_session.get(url, auth=auth, timeout=timeout) as resp:
                        if resp.status != 200:
                            continue
                        ct = resp.headers.get("Content-Type", "").lower()
                        if "multipart" in ct or "mjpeg" in ct:
                            buf = bytearray()
                            async for chunk in resp.content.iter_chunked(4096):
                                buf.extend(chunk)
                                frames = extract_jpegs_from_buffer(buf)
                                if frames and len(frames[0]) >= 100:
                                    return frames[0]
                                if len(buf) > 262144:
                                    break
                        elif "image" in ct or "octet-stream" in ct:
                            data = await resp.read()
                            if data and len(data) >= 100 and (data.startswith(b"\xff\xd8") or "image" in ct):
                                return data
                except Exception:
                    continue
        except Exception as err:
            _LOGGER.debug("[%s] HTTP snapshot fetch failed: %s", self.camera_id, err)
        finally:
            if owns_session and shared_session is not None and not shared_session.closed:
                await shared_session.close()
        return None

    async def _fetch_ffmpeg_snapshot(self) -> bytes | None:
        """Extract a single JPEG frame from RTSP, RTSPS, or HLS stream via FFmpeg."""
        return await self.async_capture_ffmpeg_snapshot(self.primary_stream_url, timeout_s=4.0)

    async def async_get_snapshot(self) -> bytes | None:
        """Fetch latest snapshot via HTTP or FFmpeg frame extraction."""
        if self._ha_delegate:
            snap = await self._ha_delegate.async_get_snapshot()
            self._sync_from_delegate()
            return snap

        if self.last_snapshot and self.last_snapshot_time and (time.time() - self.last_snapshot_time < 2.0):
            return self.last_snapshot

        data = await self._fetch_http_snapshot()
        if not data:
            data = await self._fetch_ffmpeg_snapshot()

        if data and len(data) >= 100:
            self.last_snapshot = data
            self.last_snapshot_time = time.time()
            self.is_connected = True
            self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
            return data

        return self.last_snapshot

    async def _stream_http_mjpeg(self, url: str) -> bool:
        """Read continuous MJPEG HTTP stream and emit JPEG frames."""
        auth = aiohttp.BasicAuth(self.username, self.password) if self.username else None
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=4.0, sock_read=8.0)
        received_any = False
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, auth=auth) as resp:
                    if resp.status != 200:
                        return False
                    ct = resp.headers.get("Content-Type", "").lower()
                    if "multipart" not in ct and "mjpeg" not in ct:
                        return False
                    buf = bytearray()
                    async for chunk in resp.content.iter_chunked(8192):
                        if not self.is_streaming:
                            break
                        buf.extend(chunk)
                        for frame in extract_jpegs_from_buffer(buf):
                            received_any = True
                            self.is_connected = True
                            self.status = STATUS_STREAMING
                            self.notify_frame(frame)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.debug("[%s] HTTP MJPEG stream error: %s", self.camera_id, err)
        return received_any

    async def _stream_loop(self) -> None:
        """Maintain real-time video frame delivery while streaming is active."""
        url = self.primary_stream_url
        while self.is_streaming:
            try:
                ok = False
                if self.driver_type == DRIVER_GENERIC_MJPEG and url.startswith(("http://", "https://")):
                    ok = await self._stream_http_mjpeg(url)

                if not ok and self.is_streaming and url.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
                    ok = await self.async_stream_ffmpeg_mjpeg(url)

                if not ok and self.is_streaming:
                    # Fallback to high-frequency snapshot polling
                    snap = await self._fetch_http_snapshot()
                    if snap:
                        self.is_connected = True
                        self.status = STATUS_STREAMING
                        self.notify_frame(snap)
                    await asyncio.sleep(0.25)
                elif self.is_streaming:
                    await asyncio.sleep(0.5)
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("[%s] Stream loop error: %s", self.camera_id, err)
                await asyncio.sleep(1.0)

    async def async_start_stream(self) -> None:
        """Start live video streaming."""
        if self._ha_delegate:
            await self._ha_delegate.async_start_stream()
            self._sync_from_delegate()
            return

        self.is_streaming = True
        self.status = STATUS_STREAMING
        if not self._mjpeg_task or self._mjpeg_task.done():
            self._mjpeg_task = asyncio.create_task(self._stream_loop())

    async def async_stop_stream(self) -> None:
        """Stop live video streaming and terminate FFmpeg process if running."""
        if self._ha_delegate:
            await self._ha_delegate.async_stop_stream()
            self._sync_from_delegate()
            return

        self.is_streaming = False
        self.status = STATUS_ONLINE if self.is_connected else STATUS_OFFLINE
        if self._mjpeg_task and not self._mjpeg_task.done():
            self._mjpeg_task.cancel()
            self._mjpeg_task = None
        self.stop_ffmpeg_process()

    def get_capabilities(self) -> dict[str, Any]:
        """Return capabilities for Generic camera."""
        if self._ha_delegate:
            return self._ha_delegate.get_capabilities()
        return {
            "night_vision": False,
            "ptz": False,
            "audio": True,
            "reboot": False,
        }
