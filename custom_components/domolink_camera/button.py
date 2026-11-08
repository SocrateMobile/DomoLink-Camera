"""Button platform for DomoLink Camera (Reboot, etc.)."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
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
    """Set up button entities from DomoLink Camera manager."""
    mgr: CameraManager = hass.data[DOMAIN]["manager"]

    entities = []
    for cam_info in mgr.get_cameras_list():
        entities.append(DomoLinkRebootButton(mgr, cam_info["id"]))

    async_add_entities(entities)


class DomoLinkRebootButton(ButtonEntity):
    """Button to reboot camera device."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:restart"

    def __init__(self, manager: CameraManager, camera_id: str) -> None:
        """Initialize reboot button."""
        self.manager = manager
        self.camera_id = camera_id
        self._attr_unique_id = f"{DOMAIN}_{camera_id}_reboot"
        self._cam = self.manager.cameras.get(camera_id, {})
        self._attr_name = "Redémarrer"

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

    async def async_press(self) -> None:
        """Handle button press to reboot camera."""
        await self.manager.async_reboot(self.camera_id)
