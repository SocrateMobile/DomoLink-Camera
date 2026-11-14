"""Sensor platform for DomoLink Camera."""

from __future__ import annotations

import logging
from typing import Any

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

    def _refresh() -> None:
        current_ids = {e.camera_id for e in entities}
        for ent in entities:
            if ent.hass:
                ent.async_write_ha_state()
        new_entities = [
            DomoLinkCameraStatusSensor(mgr, c["id"])
            for c in mgr.get_cameras_list()
            if c["id"] not in current_ids
        ]
        if new_entities:
            entities.extend(new_entities)
            async_add_entities(new_entities)

    mgr.add_update_listener(_refresh)


class DomoLinkCameraStatusSensor(SensorEntity):
    """Sensor reporting camera status."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:cctv"

    def __init__(self, manager: CameraManager, camera_id: str) -> None:
        """Initialize status sensor."""
        self.manager = manager
        self.camera_id = camera_id
        self._attr_unique_id = f"{DOMAIN}_{camera_id}_status"
        self._attr_name = "État"

    @property
    def _cam(self) -> dict[str, Any]:
        """Resolve live camera configuration dictionary dynamically."""
        return self.manager.cameras.get(self.camera_id, {})

    @property
    def native_value(self) -> str:
        """Return current status."""
        driver = self.manager.drivers.get(self.camera_id)
        return driver.status if driver else "offline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic capabilities attributes (battery, signal, account)."""
        attrs: dict[str, Any] = {}
        driver = self.manager.drivers.get(self.camera_id)
        if driver:
            caps = driver.get_capabilities() or {}
            for key in ("battery_level", "signal_strength", "account_email", "model_id"):
                if caps.get(key) is not None and caps.get(key) != "":
                    attrs[key] = caps[key]
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.camera_id)},
            name=self._cam.get("name", "Caméra"),
            manufacturer="Arlo" if self._cam.get("driver") == "arlo_cloud" else "DomoLink",
            model=self._cam.get("model_id") or self._cam.get("driver", "YsxLite PPPP"),
            sw_version=VERSION,
        )
