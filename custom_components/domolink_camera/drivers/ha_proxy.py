"""Home Assistant Camera Proxy Driver for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

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
        """Fetch snapshot directly from Home Assistant camera component."""
        if not self.hass or not self.entity_id:
            return self.last_snapshot

        try:
            # Query Home Assistant camera platform directly
            camera_comp = getattr(self.hass.components, "camera", None)
            if camera_comp and hasattr(camera_comp, "async_get_image"):
                image = await camera_comp.async_get_image(self.hass, self.entity_id, timeout=4.0)
                if image and image.content:
                    self.last_snapshot = image.content
                    self.last_snapshot_time = time.time()
                    self.status = STATUS_ONLINE
                    return image.content
        except Exception as err:
            _LOGGER.debug("[%s] Failed fetching snapshot from HA entity: %s", self.entity_id, err)

        return self.last_snapshot

    async def async_start_stream(self) -> None:
        """Request live HLS or WebRTC stream from Home Assistant camera component."""
        self.is_streaming = True
        self.status = STATUS_STREAMING

        if not self.hass or not self.entity_id:
            return

        try:
            camera_comp = getattr(self.hass.components, "camera", None)
            if camera_comp and hasattr(camera_comp, "async_request_stream"):
                url = await camera_comp.async_request_stream(self.hass, self.entity_id, fmt="hls")
                if url:
                    self._stream_url = url
        except Exception as err:
            _LOGGER.debug("[%s] Stream request to HA failed: %s", self.entity_id, err)

    async def async_stop_stream(self) -> None:
        """Stop streaming."""
        self.is_streaming = False
        self.status = STATUS_ONLINE
        self._stream_url = None

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
        }
