"""Sensor platform for DomoLink Camera."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
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
    """Set up sensor entities."""
    mgr: CameraManager = hass.data[DOMAIN]["manager"]

    entities = []
    for cam_info in mgr.get_cameras_list():
        entities.append(DomoLinkCameraStatusSensor(mgr, cam_info["id"]))

    async_add_entities(entities)


class DomoLinkCameraStatusSensor(SensorEntity):
    """Sensor reporting camera status."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:cctv"

    def __init__(self, manager: CameraManager, camera_id: str) -> None:
        """Initialize status sensor."""
        self.manager = manager
        self.camera_id = camera_id
        self._attr_unique_id = f"{DOMAIN}_{camera_id}_status"
        self._cam = self.manager.cameras.get(camera_id, {})
        self._attr_name = "État"

    @property
    def native_value(self) -> str:
        """Return current status."""
        driver = self.manager.drivers.get(self.camera_id)
        return driver.status if driver else "offline"

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
