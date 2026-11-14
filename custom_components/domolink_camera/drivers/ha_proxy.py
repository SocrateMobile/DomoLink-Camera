"""Home Assistant Camera Proxy Driver for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import shutil
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
        self._stream_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None

    def _get_ha_camera_entity(self) -> Any | None:
        """Look up underlying Home Assistant Camera entity instance if available."""
        if not self.hass or not self.entity_id:
            return None
        try:
            cam_comp = self.hass.data.get("camera")
            if cam_comp and hasattr(cam_comp, "get_entity"):
                return cam_comp.get_entity(self.entity_id)
            if cam_comp and hasattr(cam_comp, "entities"):
                for ent in cam_comp.entities:
                    if getattr(ent, "entity_id", None) == self.entity_id:
                        return ent
        except Exception:
            pass
        return None

    async def _periodic_snapshot_poll(self) -> None:
        """Periodically refresh snapshot thumbnail in background."""
        while True:
            try:
                await asyncio.sleep(15)
                if not self.is_streaming:
                    await self.async_get_snapshot()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("[%s] Periodic snapshot poll error: %s", self.entity_id, err)

    async def _live_feed_loop(self) -> None:
        """Stream via entity stream_source FFmpeg pipe when available, else poll snapshots rapidly."""
        entity = self._get_ha_camera_entity()
        if entity and hasattr(entity, "stream_source") and shutil.which("ffmpeg"):
            try:
                src = await entity.stream_source()
                if src and str(src).startswith(("rtsp://", "http://", "https://")):
                    await self.async_stream_ffmpeg_mjpeg(str(src))
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("[%s] HA stream_source FFmpeg error: %s", self.entity_id, err)

        while self.is_streaming:
            try:
                snap = await self.async_get_snapshot()
                if snap:
                    self.notify_frame(snap)
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("[%s] Error in live stream loop: %s", self.entity_id, err)
            await asyncio.sleep(0.2)

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
        await self.async_get_snapshot()
        self.is_connected = True
        self.status = STATUS_ONLINE

        if not self._poll_task or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._periodic_snapshot_poll())
        return True

    async def async_disconnect(self) -> None:
        """Disconnect driver and cancel background tasks."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            self._poll_task = None
        await self.async_stop_stream()
        self.is_connected = False
        self.status = STATUS_OFFLINE

    async def _fetch_http_url(self, url: str) -> bytes | None:
        """Download image bytes using HA shared aiohttp session with safe fallback."""
        timeout = aiohttp.ClientTimeout(total=6.0)
        try:
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            session = async_get_clientsession(self.hass)
            if hasattr(session, "get"):
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception:
            pass

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception:
            pass
        return None

    async def async_get_snapshot(self) -> bytes | None:
        """Fetch snapshot directly from Home Assistant camera component with multi-level fallback."""
        if not self.hass or not self.entity_id:
            return self.last_snapshot

        if not self.is_streaming and self.last_snapshot and self.last_snapshot_time and (time.time() - self.last_snapshot_time < 1.5):
            return self.last_snapshot

        # 1. Primary method: async_get_image from camera component
        try:
            from homeassistant.components.camera import async_get_image
            image = await async_get_image(self.hass, self.entity_id, timeout=6.0)
            if image and getattr(image, "content", None):
                self.last_snapshot = image.content
                self.last_snapshot_time = time.time()
                self.is_connected = True
                self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                return image.content
        except Exception:
            try:
                camera_comp = getattr(self.hass.components, "camera", None)
                if camera_comp and hasattr(camera_comp, "async_get_image"):
                    image = await camera_comp.async_get_image(self.entity_id, timeout=6.0)
                    if image and getattr(image, "content", None):
                        self.last_snapshot = image.content
                        self.last_snapshot_time = time.time()
                        self.is_connected = True
                        self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                        return image.content
            except Exception as err:
                _LOGGER.debug("[%s] async_get_image failed: %s", self.entity_id, err)

        # 2. Secondary fallback: direct entity async_camera_image()
        try:
            entity = self._get_ha_camera_entity()
            if entity and hasattr(entity, "async_camera_image"):
                data = await entity.async_camera_image()
                if data and len(data) > 100:
                    self.last_snapshot = data
                    self.last_snapshot_time = time.time()
                    self.is_connected = True
                    self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                    return data
        except Exception as err:
            _LOGGER.debug("[%s] entity.async_camera_image failed: %s", self.entity_id, err)

        # 3. Tertiary fallback: entity attributes (last_thumbnail for Arlo / cloud cameras)
        try:
            state = self.hass.states.get(self.entity_id)
            if state and state.attributes:
                last_thumb = state.attributes.get("last_thumbnail")
                if last_thumb and str(last_thumb).startswith(("http://", "https://")):
                    data = await self._fetch_http_url(str(last_thumb))
                    if data and len(data) > 100:
                        self.last_snapshot = data
                        self.last_snapshot_time = time.time()
                        self.is_connected = True
                        self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                        return data
        except Exception as err:
            _LOGGER.debug("[%s] Fallback to last_thumbnail failed: %s", self.entity_id, err)

        return self.last_snapshot

    async def async_start_stream(self) -> None:
        """Request live HLS stream from Home Assistant camera component and start frame feed."""
        self.is_streaming = True
        self.status = STATUS_STREAMING

        if not self.hass or not self.entity_id:
            return

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
        """Stop streaming and clean up FFmpeg or polling task."""
        self.is_streaming = False
        self.status = STATUS_ONLINE if self.is_connected else STATUS_OFFLINE
        self._stream_url = None
        self.stop_ffmpeg_process()
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
