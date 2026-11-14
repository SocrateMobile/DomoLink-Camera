"""Button platform for DomoLink Camera (Reboot, etc.)."""

from __future__ import annotations

import logging
from typing import Any

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

    def _refresh() -> None:
        current_ids = {e.camera_id for e in entities}
        for ent in entities:
            if ent.hass:
                ent.async_write_ha_state()
        new_entities = [
            DomoLinkRebootButton(mgr, c["id"])
            for c in mgr.get_cameras_list()
            if c["id"] not in current_ids
        ]
        if new_entities:
            entities.extend(new_entities)
            async_add_entities(new_entities)

    mgr.add_update_listener(_refresh)


class DomoLinkRebootButton(ButtonEntity):
    """Button to reboot camera device."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:restart"

    def __init__(self, manager: CameraManager, camera_id: str) -> None:
        """Initialize reboot button."""
        self.manager = manager
        self.camera_id = camera_id
        self._attr_unique_id = f"{DOMAIN}_{camera_id}_reboot"
        self._attr_name = "Redémarrer"

    @property
    def _cam(self) -> dict[str, Any]:
        """Resolve live camera configuration dictionary dynamically."""
        return self.manager.cameras.get(self.camera_id, {})

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
