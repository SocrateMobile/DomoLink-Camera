"""DomoLink Camera custom integration for Home Assistant."""

from __future__ import annotations

import logging
import os

from homeassistant.components import frontend
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .api import (
    DomolinkCameraSnapshotView,
    DomolinkCameraStreamView,
    DomolinkTvLiveStreamView,
    DomolinkTvProxyView,
    register_websocket_handlers,
)
from .const import DOMAIN, NAME, VERSION
from .manager import CameraManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["camera", "switch", "button", "sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DomoLink Camera from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Initialize manager and load persistent cameras
    manager = CameraManager(hass)
    await manager.async_load()

    hass.data[DOMAIN]["manager"] = manager
    hass.data[DOMAIN][entry.entry_id] = {"manager": manager}

    # Register HTTP views
    hass.http.register_view(DomolinkCameraSnapshotView(hass))
    hass.http.register_view(DomolinkCameraStreamView(hass))
    hass.http.register_view(DomolinkTvLiveStreamView(hass))
    hass.http.register_view(DomolinkTvProxyView(hass))

    # Register WebSocket commands
    register_websocket_handlers(hass)

    # Register frontend panel in left sidebar
    frontend_dir = os.path.join(os.path.dirname(__file__), "frontend")

    # Register static path
    if hasattr(hass.http, "async_register_static_paths"):
        from homeassistant.components.http import StaticPathConfig
        await hass.http.async_register_static_paths([
            StaticPathConfig("/domolink_camera_panel", frontend_dir, False)
        ])
    else:
        hass.http.register_static_path(
            "/domolink_camera_panel",
            frontend_dir,
            cache_headers=False,
        )

    try:
        frontend.async_remove_panel(hass, "domolink_camera")
    except Exception:
        pass

    try:
        frontend.async_register_built_in_panel(
            hass,
            component_name="custom",
            sidebar_title=NAME,
            sidebar_icon="mdi:cctv",
            frontend_url_path="domolink_camera",
            config={
                "_panel_custom": {
                    "name": "domolink-camera-panel",
                    "module_url": f"/domolink_camera_panel/domolink-camera-panel.js?v={VERSION}",
                }
            },
            require_admin=True,
        )
    except ValueError:
        # Panel already registered
        pass

    # Forward entry setups to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload DomoLink Camera config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        manager: CameraManager = hass.data[DOMAIN].get("manager")
        if manager:
            # Disconnect all active camera drivers
            for driver in manager.drivers.values():
                await driver.async_disconnect()

        hass.data[DOMAIN].pop(entry.entry_id, None)
        try:
            frontend.async_remove_panel(hass, "domolink_camera")
        except Exception:
            pass

    return unload_ok
