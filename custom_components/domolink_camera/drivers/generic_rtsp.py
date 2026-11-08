"""Generic RTSP / ONVIF / HTTP Camera Driver for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

import aiohttp

from .base import BaseCameraDriver
from ..const import (
    DEFAULT_HTTP_PORT,
    DEFAULT_RTSP_PORT,
    STATUS_CONNECTING,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_STREAMING,
)

_LOGGER = logging.getLogger(__name__)


class GenericRtspDriver(BaseCameraDriver):
    """Driver for standard IP cameras using RTSP or HTTP snapshots."""

    def __init__(
        self,
        camera_id: str,
        config: dict[str, Any],
        on_frame_callback: Callable[[bytes], None] | None = None,
    ) -> None:
        """Initialize generic RTSP driver."""
        super().__init__(camera_id, config, on_frame_callback)
        self.rtsp_port = int(config.get("port", DEFAULT_RTSP_PORT))
        self.http_port = int(config.get("http_port", DEFAULT_HTTP_PORT))
        self.stream_path = config.get("stream_path", "/live/ch0")
        self.snapshot_path = config.get("snapshot_path", "/snapshot.jpg")
        self.username = config.get("username", "")
        self.password = config.get("password", "")
        self._mjpeg_task: asyncio.Task | None = None

    @property
    def rtsp_url(self) -> str:
        """Construct RTSP stream URL with optional credentials."""
        auth = f"{self.username}:{self.password}@" if self.username else ""
        return f"rtsp://{auth}{self.host}:{self.rtsp_port}{self.stream_path}"

    @property
    def http_snapshot_url(self) -> str:
        """Construct HTTP snapshot URL."""
        return f"http://{self.host}:{self.http_port}{self.snapshot_path}"

    async def async_connect(self) -> bool:
        """Verify camera reachability."""
        self.status = STATUS_CONNECTING
        snap = await self.async_get_snapshot()
        if snap:
            self.is_connected = True
            self.status = STATUS_ONLINE
            return True
        self.is_connected = False
        self.status = STATUS_OFFLINE
        return False

    async def async_disconnect(self) -> None:
        """Disconnect and stop streaming."""
        await self.async_stop_stream()
        self.is_connected = False
        self.status = STATUS_OFFLINE

    async def async_get_snapshot(self) -> bytes | None:
        """Fetch snapshot via HTTP."""
        auth = aiohttp.BasicAuth(self.username, self.password) if self.username else None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.http_snapshot_url, auth=auth, timeout=3.0) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        self.last_snapshot = data
                        self.last_snapshot_time = time.time()
                        self.status = STATUS_ONLINE
                        return data
        except Exception as err:
            _LOGGER.debug("[%s] Snapshot fetch failed: %s", self.camera_id, err)
        return self.last_snapshot

    async def async_start_stream(self) -> None:
        """Start streaming."""
        self.is_streaming = True
        self.status = STATUS_STREAMING

    async def async_stop_stream(self) -> None:
        """Stop streaming."""
        self.is_streaming = False
        self.status = STATUS_ONLINE
        if self._mjpeg_task and not self._mjpeg_task.done():
            self._mjpeg_task.cancel()

    def get_capabilities(self) -> dict[str, Any]:
        """Return capabilities for Generic camera."""
        return {
            "night_vision": False,
            "ptz": False,
            "audio": True,
            "reboot": False,
        }
