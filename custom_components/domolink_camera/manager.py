"""Central Camera Manager for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DRIVER_GENERIC_RTSP,
    DRIVER_YSXLITE_PPPP,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .drivers.base import BaseCameraDriver
from .drivers.generic_rtsp import GenericRtspDriver
from .drivers.ysxlite_pppp import YsxLiteDriver
from .pairing import WifiPairingEngine
from .box_detector import BoxDetectorService

_LOGGER = logging.getLogger(__name__)

# Lightweight SVG placeholder when no camera frame is yet available
DEFAULT_PLACEHOLDER_SVG = b"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360">
  <rect width="640" height="360" fill="#0d1117"/>
  <rect x="20" y="20" width="600" height="320" rx="16" fill="rgba(22, 27, 34, 0.85)" stroke="rgba(255,255,255,0.1)" stroke-width="2"/>
  <circle cx="320" cy="160" r="50" fill="none" stroke="#3b82f6" stroke-width="4" stroke-dasharray="6 6"/>
  <circle cx="320" cy="160" r="28" fill="#1e293b"/>
  <circle cx="328" cy="152" r="8" fill="#60a5fa" opacity="0.6"/>
  <text x="320" y="250" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto" font-size="16" font-weight="600" fill="#f0f6fc" text-anchor="middle">
    DomoLink Camera - En attente du flux
  </text>
  <text x="320" y="275" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, Roboto" font-size="12" fill="#8b949e" text-anchor="middle">
    Cliquez sur Live pour activer le direct
  </text>
</svg>"""


class CameraManager:
    """Manages all registered cameras, drivers, pairing, and layout persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize camera manager."""
        self.hass = hass
        self.store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.cameras: dict[str, dict[str, Any]] = {}
        self.drivers: dict[str, BaseCameraDriver] = {}
        self.pairing_engine = WifiPairingEngine(hass)
        self.box_detector = BoxDetectorService(hass)
        self._listeners: list[Any] = []

    async def async_load(self) -> None:
        """Load camera configs and layout order from persistent storage."""
        data = await self.store.async_load()
        if data and isinstance(data, dict):
            raw_cams = data.get("cameras", {})
            for cid, ccfg in raw_cams.items():
                self.cameras[cid] = ccfg
                self._init_driver(cid, ccfg)
        else:
            # Seed with demo/default configuration if totally empty
            _LOGGER.info("No saved DomoLink cameras found. Ready for pairing or addition.")

        # Connect drivers in background
        for driver in self.drivers.values():
            asyncio.create_task(driver.async_connect())

    async def async_save(self) -> None:
        """Persist cameras and layout to disk."""
        await self.store.async_save({"cameras": self.cameras})

    def _init_driver(self, camera_id: str, config: dict[str, Any]) -> BaseCameraDriver:
        """Instantiate driver based on configuration."""
        driver_type = config.get("driver", DRIVER_YSXLITE_PPPP)

        if driver_type == DRIVER_GENERIC_RTSP:
            driver = GenericRtspDriver(camera_id, config)
        else:
            driver = YsxLiteDriver(camera_id, config)

        self.drivers[camera_id] = driver
        return driver

    def get_cameras_list(self) -> list[dict[str, Any]]:
        """Return list of all cameras sorted by their layout order."""
        result = []
        sorted_cams = sorted(self.cameras.values(), key=lambda c: c.get("order", 0))

        for c in sorted_cams:
            cid = c["id"]
            driver = self.drivers.get(cid)
            status = driver.status if driver else "offline"
            caps = driver.get_capabilities() if driver else {}
            has_snap = bool(driver and driver.last_snapshot)
            snap_time = driver.last_snapshot_time if driver else None

            # Build enriched camera dict for frontend
            item = {
                "id": cid,
                "name": c.get("name", "Caméra"),
                "description": c.get("description", ""),
                "driver": c.get("driver", DRIVER_YSXLITE_PPPP),
                "host": c.get("host", ""),
                "port": c.get("port", 32108),
                "order": c.get("order", 0),
                "linked_entities": c.get("linked_entities", []),
                "status": status,
                "capabilities": caps,
                "has_snapshot": has_snap,
                "snapshot_timestamp": snap_time,
                "night_vision": c.get("night_vision", False),
            }
            result.append(item)
        return result

    async def async_save_layout(self, order_list: list[str]) -> bool:
        """Update display ordering of camera thumbnails from drag & drop."""
        for idx, cid in enumerate(order_list):
            if cid in self.cameras:
                self.cameras[cid]["order"] = idx
        await self.async_save()
        _LOGGER.info("Saved new camera thumbnail layout order: %s", order_list)
        return True

    async def async_save_camera(self, camera_data: dict[str, Any]) -> dict[str, Any]:
        """Create or update camera configuration."""
        cid = camera_data.get("id")
        if not cid:
            # Generate ID from name or timestamp
            raw_name = camera_data.get("name", "camera").lower().replace(" ", "_")
            cid = f"cam_{raw_name}_{int(time.time())}"
            camera_data["id"] = cid

        # Keep existing order or assign to end
        if "order" not in camera_data:
            max_order = max([c.get("order", 0) for c in self.cameras.values()], default=-1)
            camera_data["order"] = max_order + 1

        self.cameras[cid] = camera_data

        # Re-initialize driver cleanly
        if cid in self.drivers:
            await self.drivers[cid].async_disconnect()
        driver = self._init_driver(cid, camera_data)
        asyncio.create_task(driver.async_connect())

        await self.async_save()
        self._notify_listeners()
        return camera_data

    async def async_delete_camera(self, camera_id: str) -> bool:
        """Remove camera and disconnect its driver."""
        if camera_id in self.drivers:
            await self.drivers[camera_id].async_disconnect()
            del self.drivers[camera_id]

        if camera_id in self.cameras:
            del self.cameras[camera_id]
            await self.async_save()
            self._notify_listeners()
            return True
        return False

    async def async_get_snapshot(self, camera_id: str) -> bytes:
        """Get latest camera snapshot or fallback placeholder."""
        driver = self.drivers.get(camera_id)
        if driver:
            snap = await driver.async_get_snapshot()
            if snap:
                return snap
        return DEFAULT_PLACEHOLDER_SVG

    async def async_start_live(self, camera_id: str) -> bool:
        """Switch camera to active streaming mode."""
        driver = self.drivers.get(camera_id)
        if driver:
            await driver.async_start_stream()
            return True
        return False

    async def async_stop_live(self, camera_id: str) -> bool:
        """Return camera to periodic snapshot mode."""
        driver = self.drivers.get(camera_id)
        if driver:
            await driver.async_stop_stream()
            return True
        return False

    async def async_set_night_vision(self, camera_id: str, state: bool) -> bool:
        """Toggle infrared night vision."""
        if camera_id in self.cameras:
            self.cameras[camera_id]["night_vision"] = state
            await self.async_save()
        driver = self.drivers.get(camera_id)
        if driver:
            return await driver.async_set_night_vision(state)
        return False

    async def async_reboot(self, camera_id: str) -> bool:
        """Trigger camera reboot."""
        driver = self.drivers.get(camera_id)
        if driver:
            return await driver.async_reboot()
        return False

    def add_update_listener(self, listener: Any) -> None:
        """Add listener for state updates."""
        self._listeners.append(listener)

    def _notify_listeners(self) -> None:
        """Notify registered entity listeners."""
        for cb in self._listeners:
            try:
                cb()
            except Exception as e:
                _LOGGER.debug("Listener callback error: %s", e)
