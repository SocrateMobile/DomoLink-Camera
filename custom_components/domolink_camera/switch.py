"""Switch platform for DomoLink Camera (IR Night Vision, etc.)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, VERSION
from .manager import CameraManager

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities from DomoLink Camera manager."""
    mgr: CameraManager = hass.data[DOMAIN]["manager"]

    entities = []
    for cam_info in mgr.get_cameras_list():
        if cam_info.get("capabilities", {}).get("night_vision"):
            entities.append(DomoLinkNightVisionSwitch(mgr, cam_info["id"]))

    async_add_entities(entities)


class DomoLinkNightVisionSwitch(SwitchEntity):
    """Switch to toggle camera infrared night vision."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:weather-night"

    def __init__(self, manager: CameraManager, camera_id: str) -> None:
        """Initialize night vision switch."""
        self.manager = manager
        self.camera_id = camera_id
        self._attr_unique_id = f"{DOMAIN}_{camera_id}_night_vision"
        self._cam = self.manager.cameras.get(camera_id, {})
        self._attr_name = "Vision Nocturne IR"

    @property
    def is_on(self) -> bool:
        """Return True if night vision is on."""
        return self._cam.get("night_vision", False)

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.camera_id)},
            name=self._cam.get("name", "Caméra"),
            manufacturer="DomoLink",
            model=self._cam.get("driver", "YsxLite PPPP"),
            sw_version=VERSION,
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on night vision."""
        await self.manager.async_set_night_vision(self.camera_id, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off night vision."""
        await self.manager.async_set_night_vision(self.camera_id, False)
        self.async_write_ha_state()
