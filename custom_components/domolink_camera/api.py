"""HTTP Views and WebSocket APIs for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
import voluptuous as vol

from .const import (
    ALLOWED_ENTITY_DOMAINS,
    DOMAIN,
    WS_TYPE_DELETE_CAMERA,
    WS_TYPE_GET_CAMERAS,
    WS_TYPE_GET_ENTITIES,
    WS_TYPE_PAIR_STATUS,
    WS_TYPE_REBOOT,
    WS_TYPE_SAVE_CAMERA,
    WS_TYPE_SAVE_LAYOUT,
    WS_TYPE_SCAN_LOCAL,
    WS_TYPE_SET_IR,
    WS_TYPE_START_PAIRING,
    WS_TYPE_TRIGGER_LIVE,
)

_LOGGER = logging.getLogger(__name__)


class DomolinkCameraSnapshotView(HomeAssistantView):
    """Serve current snapshot for a camera."""

    url = "/api/domolink_camera/snapshot/{camera_id}"
    name = "api:domolink_camera:snapshot"
    requires_auth = False  # Allows secure signed token or frontend token

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize view."""
        self.hass = hass

    async def get(self, request: web.Request, camera_id: str) -> web.Response:
        """Return latest snapshot image."""
        mgr = self.hass.data[DOMAIN]["manager"]
        data = await mgr.async_get_snapshot(camera_id)

        content_type = "image/svg+xml" if data.startswith(b"<svg") else "image/jpeg"
        return web.Response(
            body=data,
            content_type=content_type,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )


class DomolinkCameraStreamView(HomeAssistantView):
    """Serve live MJPEG stream for real-time video."""

    url = "/api/domolink_camera/stream/{camera_id}"
    name = "api:domolink_camera:stream"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize stream view."""
        self.hass = hass

    async def get(self, request: web.Request, camera_id: str) -> web.StreamResponse:
        """Stream MJPEG frames directly to client."""
        mgr = self.hass.data[DOMAIN]["manager"]
        driver = mgr.drivers.get(camera_id)

        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "multipart/x-mixed-replace;boundary=--frameboundary",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Connection": "close",
            },
        )
        await response.prepare(request)

        # Start live video feed on driver
        await mgr.async_start_live(camera_id)

        frame_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=10)

        def _on_frame(jpeg_bytes: bytes) -> None:
            if frame_queue.full():
                try:
                    frame_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            frame_queue.put_nowait(jpeg_bytes)

        orig_callback = driver.on_frame_callback if driver else None
        if driver:
            driver.on_frame_callback = _on_frame

        try:
            while True:
                # Get frame or timeout to check client disconnect
                try:
                    jpeg = await asyncio.wait_for(frame_queue.get(), timeout=2.0)
                except asyncio.TimeoutError:
                    # Send last known snapshot if available
                    jpeg = await mgr.async_get_snapshot(camera_id)

                part = (
                    b"--frameboundary\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("utf-8")
                    + jpeg
                    + b"\r\n"
                )
                await response.write(part)
        except (asyncio.CancelledError, ConnectionResetError, Exception):
            pass
        finally:
            if driver:
                driver.on_frame_callback = orig_callback
            await mgr.async_stop_live(camera_id)

        return response


@callback
def register_websocket_handlers(hass: HomeAssistant) -> None:
    """Register all DomoLink Camera WebSocket commands."""

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_GET_CAMERAS})
    @websocket_api.async_response
    async def ws_get_cameras(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        cameras = mgr.get_cameras_list()
        connection.send_result(msg["id"], {"cameras": cameras})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_SAVE_LAYOUT,
        vol.Required("order"): [str],
    })
    @websocket_api.async_response
    async def ws_save_layout(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        await mgr.async_save_layout(msg["order"])
        connection.send_result(msg["id"], {"success": True})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_SAVE_CAMERA,
        vol.Required("camera"): dict,
    })
    @websocket_api.async_response
    async def ws_save_camera(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        saved = await mgr.async_save_camera(msg["camera"])
        connection.send_result(msg["id"], {"success": True, "camera": saved})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_DELETE_CAMERA,
        vol.Required("camera_id"): str,
    })
    @websocket_api.async_response
    async def ws_delete_camera(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        ok = await mgr.async_delete_camera(msg["camera_id"])
        connection.send_result(msg["id"], {"success": ok})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_START_PAIRING,
        vol.Required("ssid"): str,
        vol.Required("password"): str,
        vol.Optional("camera_ap_ip", default="192.168.1.254"): str,
    })
    @websocket_api.async_response
    async def ws_start_pairing(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        # Run pairing asynchronously in background
        asyncio.create_task(
            mgr.pairing_engine.async_start_pairing(
                msg["ssid"], msg["password"], msg.get("camera_ap_ip", "192.168.1.254")
            )
        )
        connection.send_result(msg["id"], {"started": True})

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_PAIR_STATUS})
    @websocket_api.async_response
    async def ws_pair_status(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        connection.send_result(msg["id"], mgr.pairing_engine.get_status())

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_SCAN_LOCAL})
    @websocket_api.async_response
    async def ws_scan_local(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        scan_data = await mgr.pairing_engine.async_scan_all_cameras()
        connection.send_result(
            msg["id"],
            {
                "compatible": scan_data.get("compatible", []),
                "incompatible": scan_data.get("incompatible", []),
                "summary": scan_data.get("summary", {}),
                "devices": scan_data.get("compatible", []),
            },
        )

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_GET_ENTITIES})
    @websocket_api.async_response
    async def ws_get_entities(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        """Return available entities in Home Assistant for bottom banner."""
        entities = []
        for state in hass.states.async_all():
            domain = state.domain
            if domain in ALLOWED_ENTITY_DOMAINS:
                entities.append({
                    "entity_id": state.entity_id,
                    "name": state.attributes.get("friendly_name", state.entity_id),
                    "domain": domain,
                    "state": state.state,
                    "icon": state.attributes.get("icon"),
                })
        # Sort by friendly name
        entities.sort(key=lambda x: x["name"].lower())
        connection.send_result(msg["id"], {"entities": entities})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_TRIGGER_LIVE,
        vol.Required("camera_id"): str,
        vol.Required("live"): bool,
    })
    @websocket_api.async_response
    async def ws_trigger_live(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        if msg["live"]:
            await mgr.async_start_live(msg["camera_id"])
        else:
            await mgr.async_stop_live(msg["camera_id"])
        connection.send_result(msg["id"], {"success": True})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_SET_IR,
        vol.Required("camera_id"): str,
        vol.Required("enabled"): bool,
    })
    @websocket_api.async_response
    async def ws_set_ir(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        ok = await mgr.async_set_night_vision(msg["camera_id"], msg["enabled"])
        connection.send_result(msg["id"], {"success": ok})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_REBOOT,
        vol.Required("camera_id"): str,
    })
    @websocket_api.async_response
    async def ws_reboot(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        ok = await mgr.async_reboot(msg["camera_id"])
        connection.send_result(msg["id"], {"success": ok})

    websocket_api.async_register_command(hass, ws_get_cameras)
    websocket_api.async_register_command(hass, ws_save_layout)
    websocket_api.async_register_command(hass, ws_save_camera)
    websocket_api.async_register_command(hass, ws_delete_camera)
    websocket_api.async_register_command(hass, ws_start_pairing)
    websocket_api.async_register_command(hass, ws_pair_status)
    websocket_api.async_register_command(hass, ws_scan_local)
    websocket_api.async_register_command(hass, ws_get_entities)
    websocket_api.async_register_command(hass, ws_trigger_live)
    websocket_api.async_register_command(hass, ws_set_ir)
    websocket_api.async_register_command(hass, ws_reboot)
