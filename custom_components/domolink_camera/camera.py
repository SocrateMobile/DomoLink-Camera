"""Camera platform for DomoLink Camera."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NAME, VERSION
from .manager import CameraManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up camera entities from DomoLink Camera manager."""
    mgr: CameraManager = hass.data[DOMAIN]["manager"]

    entities = []
    for cam_info in mgr.get_cameras_list():
        entities.append(DomoLinkCameraEntity(mgr, cam_info["id"], entry.entry_id))

    async_add_entities(entities)

    # Listen for added/removed cameras
    def _refresh() -> None:
        current_ids = {e.camera_id for e in entities}
        new_cams = [
            DomoLinkCameraEntity(mgr, c["id"], entry.entry_id)
            for c in mgr.get_cameras_list()
            if c["id"] not in current_ids
        ]
        if new_cams:
            entities.extend(new_cams)
            async_add_entities(new_cams)

    mgr.add_update_listener(_refresh)


class DomoLinkCameraEntity(Camera):
    """Home Assistant camera entity for DomoLink."""

    _attr_has_entity_name = True
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, manager: CameraManager, camera_id: str, entry_id: str) -> None:
        """Initialize camera entity."""
        super().__init__()
        self.manager = manager
        self.camera_id = camera_id
        self._entry_id = entry_id
        self._attr_unique_id = f"{DOMAIN}_{camera_id}"
        self._cam = self.manager.cameras.get(camera_id, {})
        self._attr_name = self._cam.get("name", "Caméra")

    @property
    def is_on(self) -> bool:
        """Return True if camera is online."""
        driver = self.manager.drivers.get(self.camera_id)
        return driver.is_connected if driver else False

    @property
    def is_recording(self) -> bool:
        """Return True if camera is streaming."""
        driver = self.manager.drivers.get(self.camera_id)
        return driver.is_streaming if driver else False

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for Home Assistant."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.camera_id)},
            name=self._attr_name,
            manufacturer="DomoLink",
            model=self._cam.get("driver", "YsxLite PPPP"),
            sw_version=VERSION,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        return {
            "description": self._cam.get("description", ""),
            "host": self._cam.get("host", ""),
            "order": self._cam.get("order", 0),
            "linked_entities": self._cam.get("linked_entities", []),
        }

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return bytes of latest snapshot."""
        return await self.manager.async_get_snapshot(self.camera_id)

    async def stream_source(self) -> str | None:
        """Return the source of the stream."""
        # Provide direct endpoint for MJPEG / RTSP streaming
        return f"http://127.0.0.1:8123/api/domolink_camera/stream/{self.camera_id}"
