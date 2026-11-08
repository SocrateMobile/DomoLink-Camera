"""Home Assistant Camera Proxy Driver for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

import aiohttp

from .base import BaseCameraDriver
from ..const import (
    STATUS_CONNECTING,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_STREAMING,
)

_LOGGER = logging.getLogger(__name__)


class HaProxyDriver(BaseCameraDriver):
    """Driver for cameras already integrated in Home Assistant via cloud or local integrations.

    Proxies snapshots and live streams through Home Assistant's native camera infrastructure.
    """

    def __init__(
        self,
        camera_id: str,
        config: dict[str, Any],
        hass: Any = None,
        on_frame_callback: Callable[[bytes], None] | None = None,
    ) -> None:
        """Initialize HA proxy driver."""
        super().__init__(camera_id, config, on_frame_callback)
        self.hass = hass
        self.entity_id = config.get("entity_id") or config.get("host") or ""
        self._stream_url: str | None = None
        self._stream_task: asyncio.Task[None] | None = None

    async def _live_feed_loop(self) -> None:
        """Continuously poll snapshots to feed the live MJPEG stream."""
        while self.is_streaming:
            try:
                snap = await self.async_get_snapshot()
                if snap and self.on_frame_callback:
                    self.on_frame_callback(snap)
            except Exception as err:
                _LOGGER.debug("[%s] Error in live stream loop: %s", self.entity_id, err)
            await asyncio.sleep(0.5)

    async def async_connect(self) -> bool:
        """Verify camera entity exists and is available in Home Assistant."""
        self.status = STATUS_CONNECTING
        if not self.hass or not self.entity_id:
            self.status = STATUS_OFFLINE
            return False

        state = self.hass.states.get(self.entity_id)
        if not state or state.state == "unavailable":
            self.is_connected = False
            self.status = STATUS_OFFLINE
            return False

        # Try fetching a first snapshot
        snap = await self.async_get_snapshot()
        if snap:
            self.is_connected = True
            self.status = STATUS_ONLINE
            return True

        self.is_connected = True
        self.status = STATUS_ONLINE
        return True

    async def async_disconnect(self) -> None:
        """Disconnect driver."""
        await self.async_stop_stream()
        self.is_connected = False
        self.status = STATUS_OFFLINE

    async def async_get_snapshot(self) -> bytes | None:
        """Fetch snapshot directly from Home Assistant camera component with multi-level fallback."""
        if not self.hass or not self.entity_id:
            return self.last_snapshot

        # 1. Primary method: async_get_image from camera component
        try:
            from homeassistant.components.camera import async_get_image
            image = await async_get_image(self.hass, self.entity_id, timeout=8.0)
            if image and image.content:
                self.last_snapshot = image.content
                self.last_snapshot_time = time.time()
                self.status = STATUS_ONLINE
                return image.content
        except Exception:
            # Fallback to hass.components.camera.async_get_image(entity_id) without duplicate hass arg
            try:
                camera_comp = getattr(self.hass.components, "camera", None)
                if camera_comp and hasattr(camera_comp, "async_get_image"):
                    image = await camera_comp.async_get_image(self.entity_id, timeout=8.0)
                    if image and image.content:
                        self.last_snapshot = image.content
                        self.last_snapshot_time = time.time()
                        self.status = STATUS_ONLINE
                        return image.content
            except Exception as err:
                _LOGGER.debug("[%s] async_get_image failed: %s", self.entity_id, err)

        # 2. Secondary fallback: check entity attributes (last_thumbnail for Arlo / cloud cameras)
        try:
            state = self.hass.states.get(self.entity_id)
            if state and state.attributes:
                last_thumb = state.attributes.get("last_thumbnail")
                if last_thumb and str(last_thumb).startswith("http"):
                    async with aiohttp.ClientSession() as session:
                        async with session.get(last_thumb, timeout=6.0) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                if data and len(data) > 100:
                                    self.last_snapshot = data
                                    self.last_snapshot_time = time.time()
                                    self.status = STATUS_ONLINE
                                    return data
        except Exception as err:
            _LOGGER.debug("[%s] Fallback to last_thumbnail failed: %s", self.entity_id, err)

        return self.last_snapshot

    async def async_start_stream(self) -> None:
        """Request live HLS or WebRTC stream from Home Assistant camera component and start frame feed."""
        self.is_streaming = True
        self.status = STATUS_STREAMING

        if not self.hass or not self.entity_id:
            return

        # Start live feed task for MJPEG endpoint
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        self._stream_task = asyncio.create_task(self._live_feed_loop())

        try:
            from homeassistant.components.camera import async_request_stream
            url = await async_request_stream(self.hass, self.entity_id, fmt="hls")
            if url:
                self._stream_url = url
        except Exception:
            try:
                camera_comp = getattr(self.hass.components, "camera", None)
                if camera_comp and hasattr(camera_comp, "async_request_stream"):
                    url = await camera_comp.async_request_stream(self.entity_id, fmt="hls")
                    if url:
                        self._stream_url = url
            except Exception as err:
                _LOGGER.debug("[%s] Stream request to HA failed: %s", self.entity_id, err)

    async def async_stop_stream(self) -> None:
        """Stop streaming."""
        self.is_streaming = False
        self.status = STATUS_ONLINE
        self._stream_url = None
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            self._stream_task = None

    def get_capabilities(self) -> dict[str, Any]:
        """Return capabilities for HA Proxy camera."""
        state = self.hass.states.get(self.entity_id) if self.hass else None
        attrs = state.attributes if state else {}
        return {
            "night_vision": False,
            "ptz": False,
            "audio": bool(attrs.get("supported_features", 0) & 2),
            "reboot": False,
            "ha_entity": self.entity_id,
            "entity_picture": attrs.get("entity_picture"),
            "access_token": attrs.get("access_token"),
            "brand": attrs.get("brand") or attrs.get("device_brand") or "Home Assistant",
            "model": attrs.get("model_name") or attrs.get("device_model") or "Caméra",
        }
