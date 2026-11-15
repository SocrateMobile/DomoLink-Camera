"""Base class for all DomoLink Camera drivers."""

from __future__ import annotations

import abc
import asyncio
import logging
import shutil
import time
from typing import Any, Callable

from ..const import DEFAULT_STREAM_FPS, MAX_UDP_FRAME_BUFFER, STATUS_STREAMING

_LOGGER = logging.getLogger(__name__)


def extract_jpegs_from_buffer(buf: bytearray) -> list[bytes]:
    """Extract complete JPEG frames (SOI..EOI) from a rolling byte buffer."""
    frames: list[bytes] = []
    while True:
        soi = buf.find(b"\xff\xd8")
        if soi == -1:
            if len(buf) > MAX_UDP_FRAME_BUFFER:
                buf.clear()
            break
        if soi > 0:
            del buf[:soi]
        eoi = buf.find(b"\xff\xd9", 2)
        if eoi == -1:
            if len(buf) > MAX_UDP_FRAME_BUFFER:
                buf.clear()
            break
        frames.append(bytes(buf[: eoi + 2]))
        del buf[: eoi + 2]
    return frames


class BaseCameraDriver(abc.ABC):
    """Abstract interface for modular camera hardware drivers."""

    def __init__(self, camera_id: str, config: dict[str, Any], on_frame_callback: Callable[[bytes], None] | None = None) -> None:
        """Initialize driver with camera configuration."""
        self.camera_id = camera_id
        self.config = config
        self.on_frame_callback = on_frame_callback
        self._frame_listeners: set[Callable[[bytes], None]] = set()
        self._stream_clients: int = 0
        self._explicit_live: bool = False
        self._stream_url: str | None = None
        self._ffmpeg_proc: asyncio.subprocess.Process | None = None
        self.fps: float = 0.0
        self._frame_times: list[float] = []
        self.is_connected = False
        self.is_streaming = False
        self.last_snapshot: bytes | None = None
        self.last_snapshot_time: float | None = None
        self.status = "offline"

    def subscribe_frames(self, cb: Callable[[bytes], None]) -> None:
        """Register a listener callback for live JPEG frames."""
        self._frame_listeners.add(cb)

    def unsubscribe_frames(self, cb: Callable[[bytes], None]) -> None:
        """Unregister a listener callback."""
        self._frame_listeners.discard(cb)

    def notify_frame(self, jpeg: bytes) -> None:
        """Store valid JPEG frame, update FPS metric, and notify all subscribers."""
        if not jpeg or len(jpeg) < 100:
            return
        now = time.time()
        self.last_snapshot = jpeg
        self.last_snapshot_time = now

        self._frame_times.append(now)
        cutoff = now - 2.0
        self._frame_times = [t for t in self._frame_times if t >= cutoff]
        if len(self._frame_times) >= 2:
            span = self._frame_times[-1] - self._frame_times[0]
            self.fps = (len(self._frame_times) - 1) / span if span > 0 else 0.0
        else:
            self.fps = 0.0

        if self.on_frame_callback:
            try:
                self.on_frame_callback(jpeg)
            except Exception as err:
                _LOGGER.debug("[%s] Frame callback error: %s", self.camera_id, err)

        for cb in list(self._frame_listeners):
            try:
                cb(jpeg)
            except Exception as err:
                _LOGGER.debug("[%s] Frame listener error: %s", self.camera_id, err)

    async def async_acquire_stream(self) -> None:
        """Acquire a live stream reference and start streaming if not active."""
        self._stream_clients += 1
        if not self.is_streaming:
            await self.async_start_stream()

    async def async_release_stream(self) -> None:
        """Release a live stream reference and stop hardware stream when idle."""
        self._stream_clients = max(0, self._stream_clients - 1)
        if self._stream_clients == 0 and not self._explicit_live and self.is_streaming:
            await self.async_stop_stream()

    def get_stream_info(self) -> dict[str, Any]:
        """Return stream metadata (stream URL and live FPS)."""
        return {
            "stream_url": self._stream_url,
            "fps": round(self.fps, 1),
        }

    def stop_ffmpeg_process(self) -> None:
        """Terminate active FFmpeg subprocess if running."""
        if self._ffmpeg_proc and self._ffmpeg_proc.returncode is None:
            try:
                self._ffmpeg_proc.terminate()
            except Exception:
                pass

    async def async_probe_tcp_port(
        self, host: str, port: int = 554, timeout: float = 0.75
    ) -> bool:
        """Fast non-blocking TCP connect probe to test local LAN camera ports."""
        clean_host = (host or "").strip()
        if not clean_host or port <= 0:
            return False
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(clean_host, int(port)),
                timeout=timeout,
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _ffmpeg_input_attempts(self, url: str) -> list[tuple[str | None, list[str]]]:
        """Build ordered FFmpeg input option attempts for RTSP, RTSPS, HTTP, or HLS URLs."""
        lower = url.lower()
        if lower.startswith("rtsps://"):
            rtsp_flags = [
                "-rtsp_transport", "tcp",
                "-rw_timeout", "5000000",
                "-fflags", "nobuffer+genpts+discardcorrupt",
                "-flags", "low_delay",
                "-probesize", "327680",
                "-analyzeduration", "400000",
            ]
            # Try with -tls_verify 0 first (needed for some Arlo/cloud RTSPS certs), then plain TCP
            return [
                ("tcp_noverify", [*rtsp_flags, "-tls_verify", "0"]),
                ("tcp", rtsp_flags),
            ]
        if lower.startswith("rtsp://"):
            pref = self.config.get("rtsp_transport", "tcp")
            transports = [pref] + [t for t in ("tcp", "udp") if t != pref]
            attempts: list[tuple[str | None, list[str]]] = []
            for t in transports:
                flags = ["-rtsp_transport", t]
                if t == "tcp":
                    flags.extend(["-rw_timeout", "5000000"])
                flags.extend([
                    "-fflags", "nobuffer+genpts+discardcorrupt",
                    "-flags", "low_delay",
                    "-probesize", "327680",
                    "-analyzeduration", "400000",
                ])
                attempts.append((t, flags))
            return attempts
        if lower.startswith(("http://", "https://")):
            return [
                (
                    "http_reconnect",
                    [
                        "-rw_timeout", "6000000",
                        "-reconnect", "1",
                        "-reconnect_streamed", "1",
                        "-reconnect_delay_max", "2",
                        "-fflags", "nobuffer+discardcorrupt",
                        "-flags", "low_delay",
                        "-probesize", "327680",
                        "-analyzeduration", "400000",
                    ],
                )
            ]
        return [(None, ["-fflags", "nobuffer+discardcorrupt"])]

    async def async_capture_ffmpeg_snapshot(
        self, url: str, timeout_s: float = 8.0
    ) -> bytes | None:
        """Extract a single JPEG frame from an RTSP, RTSPS, HTTP, or HLS stream via FFmpeg."""
        if not url or not shutil.which("ffmpeg"):
            return None
        if not url.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
            return None

        for label, extra_args in self._ffmpeg_input_attempts(url):
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                *extra_args,
                "-i",
                url,
                "-frames:v",
                "1",
                "-f",
                "image2",
                "-vcodec",
                "mjpeg",
                "-q:v",
                "3",
                "pipe:1",
            ]
            proc = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
                if stdout and len(stdout) >= 100 and b"\xff\xd8" in stdout:
                    start = stdout.find(b"\xff\xd8")
                    end = stdout.rfind(b"\xff\xd9")
                    if end > start:
                        return stdout[start : end + 2]
                    return stdout[start:]
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("[%s] FFmpeg snapshot (%s) failed: %s", self.camera_id, label, err)
            finally:
                if proc and proc.returncode is None:
                    try:
                        proc.kill()
                        await proc.wait()
                    except Exception:
                        pass
        return None

    async def async_stream_ffmpeg_mjpeg(
        self, url: str, fps: int = DEFAULT_STREAM_FPS, quality: int = 5
    ) -> bool:
        """Transcode an RTSP/RTSPS/HLS stream into JPEG frames via FFmpeg pipe."""
        if not url or not shutil.which("ffmpeg"):
            return False

        for label, extra_args in self._ffmpeg_input_attempts(url):
            if not self.is_streaming:
                return False
            cmd = [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                *extra_args,
                "-i",
                url,
                "-an",
                "-threads",
                "2",
                "-vf",
                "scale='min(1280,iw)':-2",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "-q:v",
                str(quality),
                "-r",
                str(fps),
                "pipe:1",
            ]
            proc = None
            received_any = False
            buf = bytearray()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                self._ffmpeg_proc = proc
                while self.is_streaming and proc.stdout:
                    chunk = await asyncio.wait_for(proc.stdout.read(16384), timeout=8.0)
                    if not chunk:
                        break
                    buf.extend(chunk)
                    for frame in extract_jpegs_from_buffer(buf):
                        received_any = True
                        self.is_connected = True
                        self.status = STATUS_STREAMING
                        self.notify_frame(frame)
                if received_any:
                    return True
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("[%s] FFmpeg stream (%s) error: %s", self.camera_id, label, err)
            finally:
                self._ffmpeg_proc = None
                if proc and proc.returncode is None:
                    try:
                        proc.terminate()
                        await asyncio.wait_for(proc.wait(), timeout=1.0)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass
        return False

    @property
    def host(self) -> str:
        """Return host IP or domain."""
        return self.config.get("host", "")

    @property
    def port(self) -> int:
        """Return primary port."""
        return int(self.config.get("port", 0))

    @abc.abstractmethod
    async def async_connect(self) -> bool:
        """Establish connection to the camera."""
        pass

    @abc.abstractmethod
    async def async_disconnect(self) -> None:
        """Close connection cleanly."""
        pass

    @abc.abstractmethod
    async def async_get_snapshot(self) -> bytes | None:
        """Retrieve latest snapshot image (JPEG bytes)."""
        pass

    @abc.abstractmethod
    async def async_start_stream(self) -> None:
        """Start receiving live video stream."""
        pass

    @abc.abstractmethod
    async def async_stop_stream(self) -> None:
        """Stop receiving live video stream."""
        pass

    async def async_set_night_vision(self, enabled: bool) -> bool:
        """Toggle infrared night vision if supported."""
        return False

    async def async_reboot(self) -> bool:
        """Trigger device reboot if supported."""
        return False

    def get_capabilities(self) -> dict[str, Any]:
        """Return supported capabilities (ptz, night_vision, audio, etc.)."""
        return {
            "night_vision": False,
            "ptz": False,
            "audio": False,
            "reboot": False,
        }
