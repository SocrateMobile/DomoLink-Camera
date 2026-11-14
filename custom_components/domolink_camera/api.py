"""HTTP Views and WebSocket APIs for DomoLink Camera."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import ipaddress
import logging
from typing import Any
from urllib.parse import urlparse

import aiohttp
from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .const import (
    ALLOWED_ENTITY_DOMAINS,
    DOMAIN,
    DRIVER_GENERIC_RTSP,
    WS_TYPE_DELETE_CAMERA,
    WS_TYPE_DETECT_BOX,
    WS_TYPE_GET_CAMERAS,
    WS_TYPE_GET_ENTITIES,
    WS_TYPE_GET_TV_CHANNELS,
    WS_TYPE_GET_TV_STREAM,
    WS_TYPE_PAIR_STATUS,
    WS_TYPE_PIN_TV_CAMERA,
    WS_TYPE_REBOOT,
    WS_TYPE_SAVE_CAMERA,
    WS_TYPE_SAVE_LAYOUT,
    WS_TYPE_SCAN_LOCAL,
    WS_TYPE_SCAN_WIFI_APS,
    WS_TYPE_SET_IR,
    WS_TYPE_START_PAIRING,
    WS_TYPE_STOP_PAIRING,
    WS_TYPE_TRIGGER_LIVE,
)

_LOGGER = logging.getLogger(__name__)


def _sign_api_path(hass: HomeAssistant, path: str, expiration_seconds: int = 3600) -> str:
    """Sign a Home Assistant API URL with ?authSig=... for media elements."""
    try:
        from homeassistant.components.http.auth import async_sign_path
        return async_sign_path(hass, path, timedelta(seconds=expiration_seconds))
    except Exception:
        return path


class DomolinkCameraSnapshotView(HomeAssistantView):
    """Serve current snapshot for a camera."""

    url = "/api/domolink_camera/snapshot/{camera_id}"
    name = "api:domolink_camera:snapshot"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize view."""
        self.hass = hass

    async def get(self, request: web.Request, camera_id: str) -> web.Response:
        """Return latest snapshot image."""
        user = request.get("hass_user")
        if not user:
            raise Unauthorized()

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
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize stream view."""
        self.hass = hass

    async def get(self, request: web.Request, camera_id: str) -> web.StreamResponse:
        """Stream MJPEG frames directly to client with multi-subscriber low-latency queue."""
        user = request.get("hass_user")
        if not user:
            raise Unauthorized()

        mgr = self.hass.data[DOMAIN]["manager"]
        driver = mgr.drivers.get(camera_id)
        if not driver:
            return web.Response(status=404, text=f"Caméra '{camera_id}' introuvable.")

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

        frame_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2)

        def _on_frame(jpeg_bytes: bytes) -> None:
            if frame_queue.full():
                try:
                    frame_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                frame_queue.put_nowait(jpeg_bytes)
            except asyncio.QueueFull:
                pass

        driver.subscribe_frames(_on_frame)
        await driver.async_acquire_stream()

        # Emit immediate initial frame if cached for instant startup
        initial = driver.last_snapshot
        if initial and not initial.startswith(b"<svg"):
            _on_frame(initial)

        try:
            while True:
                try:
                    jpeg = await asyncio.wait_for(frame_queue.get(), timeout=2.5)
                except asyncio.TimeoutError:
                    jpeg = await mgr.async_get_snapshot(camera_id)

                if jpeg and not jpeg.startswith(b"<svg"):
                    part = (
                        b"--frameboundary\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("utf-8")
                        + jpeg
                        + b"\r\n"
                    )
                    await response.write(part)
                else:
                    await asyncio.sleep(0.4)
        except (asyncio.CancelledError, ConnectionResetError, Exception):
            pass
        finally:
            driver.unsubscribe_frames(_on_frame)
            await driver.async_release_stream()

        return response


class DomolinkTvLiveStreamView(HomeAssistantView):
    """Serve real-time transcoded/remuxed TV stream via FFmpeg for browser playback."""

    url = "/api/domolink_camera/tv_live/{channel_id}"
    name = "api:domolink_camera:tv_live"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize TV live stream view."""
        self.hass = hass

    async def get(self, request: web.Request, channel_id: str) -> web.StreamResponse:
        """Remux RTSP/UDP stream to fragmented MP4 for browser HTML5 video playback."""
        user = request.get("hass_user")
        if not user:
            raise Unauthorized()

        mgr = self.hass.data[DOMAIN]["manager"]
        channels = await mgr.box_detector.async_get_tv_channels()
        channel = next((c for c in channels if c["id"] == channel_id), None)
        if not channel:
            return web.Response(status=404, text=f"Chaîne '{channel_id}' non trouvée.")

        candidate_urls: list[str] = []
        if channel.get("stream_url"):
            candidate_urls.append(channel["stream_url"])
        for fb in channel.get("fallback_urls", []):
            if fb not in candidate_urls:
                candidate_urls.append(fb)

        if not candidate_urls:
            return web.Response(status=404, text="Aucun flux disponible pour cette chaîne.")

        response = web.StreamResponse(
            status=200,
            reason="OK",
            headers={
                "Content-Type": "video/mp4",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Connection": "close",
                "Access-Control-Allow-Origin": "*",
            },
        )
        await response.prepare(request)

        for target_url in candidate_urls:
            is_rtsp = target_url.startswith("rtsp://")
            ffmpeg_cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
            if is_rtsp:
                ffmpeg_cmd.extend(["-rtsp_transport", "udp", "-timeout", "4000000"])
            ffmpeg_cmd.extend([
                "-i", target_url,
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-c:v", "copy",
                "-c:a", "aac",
                "-ac", "2",
                "-b:a", "128k",
                "-f", "mp4",
                "-movflags", "frag_keyframe+empty_moov+default_base_moof",
                "pipe:1",
            ])

            _LOGGER.info("Starting TV FFmpeg stream for %s from %s", channel_id, target_url)
            proc = None
            first_chunk = True
            try:
                proc = await asyncio.create_subprocess_exec(
                    *ffmpeg_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                while True:
                    chunk = await proc.stdout.read(32768)
                    if not chunk:
                        break
                    first_chunk = False
                    await response.write(chunk)
            except (asyncio.CancelledError, ConnectionResetError):
                _LOGGER.debug("Client disconnected from TV stream %s", channel_id)
                return response
            except Exception as exc:
                _LOGGER.warning("FFmpeg TV stream error on %s: %s", target_url, exc)
            finally:
                if proc and proc.returncode is None:
                    try:
                        proc.terminate()
                        await asyncio.wait_for(proc.wait(), timeout=1.0)
                    except Exception:
                        proc.kill()

            if not first_chunk:
                break

        return response


class DomolinkTvProxyView(HomeAssistantView):
    """CORS proxy for web HLS streams and playlists."""

    url = "/api/domolink_camera/tv_proxy"
    name = "api:domolink_camera:tv_proxy"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize proxy view."""
        self.hass = hass

    async def get(self, request: web.Request) -> web.Response:
        """Proxy external HLS stream bypassing browser CORS constraints."""
        user = request.get("hass_user")
        if not user or not user.is_admin:
            raise Unauthorized()

        url = request.query.get("url")
        if not url:
            return web.Response(status=400, text="Paramètre url requis.")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return web.Response(status=400, text="Schéma d'URL non autorisé.")

        hostname = parsed.hostname or ""
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
                return web.Response(status=403, text="Adresse IP non autorisée.")
        except ValueError:
            pass

        try:
            session = async_get_clientsession(self.hass)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8.0)) as resp:
                data = await resp.read()
                ct = resp.headers.get("Content-Type", "application/vnd.apple.mpegurl")
                return web.Response(
                    body=data,
                    content_type=ct,
                    headers={"Access-Control-Allow-Origin": "*"},
                )
        except Exception as e:
            return web.Response(status=502, text=str(e))


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
        for cam in cameras:
            cid = cam["id"]
            cam["signed_snapshot_url"] = _sign_api_path(
                hass, f"/api/domolink_camera/snapshot/{cid}"
            )
            cam["signed_stream_url"] = _sign_api_path(
                hass, f"/api/domolink_camera/stream/{cid}"
            )
            if cam.get("channel_id"):
                cam["signed_tv_live_url"] = _sign_api_path(
                    hass, f"/api/domolink_camera/tv_live/{cam['channel_id']}"
                )
        connection.send_result(msg["id"], {"cameras": cameras})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_SAVE_LAYOUT,
        vol.Required("order"): [str],
    })
    @websocket_api.require_admin
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
    @websocket_api.require_admin
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
    @websocket_api.require_admin
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
        vol.Optional("camera_ap_ip", default="192.168.1.1"): str,
        vol.Optional("camera_ssid"): str,
    })
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_start_pairing(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        # Run pairing asynchronously in background
        asyncio.create_task(
            mgr.pairing_engine.async_start_pairing(
                msg["ssid"],
                msg["password"],
                msg.get("camera_ap_ip", "192.168.1.1"),
                msg.get("camera_ssid"),
            )
        )
        connection.send_result(msg["id"], {"started": True})

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_STOP_PAIRING})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_stop_pairing(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        mgr.pairing_engine.stop_pairing()
        connection.send_result(msg["id"], {"stopped": True})

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_SCAN_WIFI_APS})
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_scan_wifi_aps(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        aps = await mgr.pairing_engine.async_scan_camera_aps()
        connection.send_result(msg["id"], {"aps": aps})

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_PAIR_STATUS})
    @websocket_api.async_response
    async def ws_pair_status(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        connection.send_result(msg["id"], mgr.pairing_engine.get_status())

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_SCAN_LOCAL})
    @websocket_api.require_admin
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
        """Return available controllable entities in Home Assistant for bottom banner (capped to prevent WS payload overflow)."""
        entities = []
        controllable_domains = {"switch", "light", "cover", "lock", "fan"}
        for state in hass.states.async_all():
            domain = state.domain
            if domain in controllable_domains:
                entities.append({
                    "entity_id": state.entity_id,
                    "name": state.attributes.get("friendly_name", state.entity_id),
                    "domain": domain,
                })
                if len(entities) >= 150:
                    break
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
        camera_id = msg["camera_id"]
        if msg["live"]:
            await mgr.async_start_live(camera_id)
        else:
            await mgr.async_stop_live(camera_id)
        driver = mgr.drivers.get(camera_id)
        cam_cfg = mgr.cameras.get(camera_id, {})
        hls_url = (driver._stream_url if driver else None) or cam_cfg.get("web_hls_url") or ""
        connection.send_result(
            msg["id"],
            {
                "success": True,
                "signed_stream_url": _sign_api_path(
                    hass, f"/api/domolink_camera/stream/{camera_id}"
                ),
                "signed_snapshot_url": _sign_api_path(
                    hass, f"/api/domolink_camera/snapshot/{camera_id}"
                ),
                "hls_url": hls_url,
            },
        )

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_SET_IR,
        vol.Required("camera_id"): str,
        vol.Required("enabled"): bool,
    })
    @websocket_api.require_admin
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
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_reboot(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        mgr = hass.data[DOMAIN]["manager"]
        ok = await mgr.async_reboot(msg["camera_id"])
        connection.send_result(msg["id"], {"success": ok})

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_DETECT_BOX})
    @websocket_api.async_response
    async def ws_detect_box(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        """Detect local ISP box (Freebox, Livebox, SFR, Bbox)."""
        mgr = hass.data[DOMAIN]["manager"]
        box_info = await mgr.box_detector.async_detect_box()
        connection.send_result(msg["id"], box_info)

    @websocket_api.websocket_command({vol.Required("type"): WS_TYPE_GET_TV_CHANNELS})
    @websocket_api.async_response
    async def ws_get_tv_channels(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        """Return available TV channels for detected box."""
        mgr = hass.data[DOMAIN]["manager"]
        channels = await mgr.box_detector.async_get_tv_channels()
        box_info = await mgr.box_detector.async_detect_box()
        connection.send_result(msg["id"], {"box": box_info, "channels": channels})

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_GET_TV_STREAM,
        vol.Required("channel_id"): str,
    })
    @websocket_api.async_response
    async def ws_get_tv_stream(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        """Get playable HLS or RTSP stream URL for chosen TV channel."""
        mgr = hass.data[DOMAIN]["manager"]
        channel_id = msg["channel_id"]
        channels = await mgr.box_detector.async_get_tv_channels()
        channel = next((c for c in channels if c["id"] == channel_id), None)
        if not channel:
            connection.send_error(msg["id"], "not_found", "Chaîne non trouvée")
            return

        # 1. Prefer direct web HLS stream if available
        if channel.get("web_hls_url"):
            connection.send_result(
                msg["id"],
                {
                    "url": channel["web_hls_url"],
                    "format": "hls",
                    "channel": channel,
                },
            )
            return

        # 2. If it's a web HLS stream directly
        if channel.get("type") == "hls" and channel.get("stream_url"):
            connection.send_result(
                msg["id"],
                {
                    "url": channel["stream_url"],
                    "format": "hls",
                    "channel": channel,
                },
            )
            return

        # 3. For Freebox RTSP stream, try HA stream component with UDP transport
        rtsp_url = channel.get("stream_url")
        if rtsp_url and "stream" in hass.config.components:
            try:
                from homeassistant.components.stream import create_stream
                stream = create_stream(hass, rtsp_url, options={"rtsp_transport": "udp"})
                stream.add_provider("hls")
                await stream.start()
                hls_url = stream.endpoint_url("hls")
                if hls_url:
                    connection.send_result(
                        msg["id"],
                        {
                            "url": hls_url,
                            "format": "hls",
                            "channel": channel,
                        },
                    )
                    return
            except Exception as e:
                _LOGGER.debug("Error creating HA HLS stream for %s: %s", channel_id, e)

        # 4. Fallback to FFmpeg live stream proxy view (Fragmented MP4)
        connection.send_result(
            msg["id"],
            {
                "url": _sign_api_path(hass, f"/api/domolink_camera/tv_live/{channel_id}"),
                "format": "mp4",
                "proxied": True,
                "channel": channel,
            },
        )

    @websocket_api.websocket_command({
        vol.Required("type"): WS_TYPE_PIN_TV_CAMERA,
        vol.Required("channel_id"): str,
    })
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_pin_tv_camera(
        hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
    ) -> None:
        """Pin a TV channel as a live camera in the Cameras grid."""
        mgr = hass.data[DOMAIN]["manager"]
        channel_id = msg["channel_id"]
        channels = await mgr.box_detector.async_get_tv_channels()
        channel = next((c for c in channels if c["id"] == channel_id), None)
        if not channel:
            connection.send_error(msg["id"], "not_found", "Chaîne non trouvée")
            return

        cam_id = f"tv_{channel_id}"
        stream_url = channel.get("stream_url", "")
        web_hls_url = channel.get("web_hls_url", "")
        target_url = stream_url or web_hls_url

        parsed = urlparse(target_url) if target_url else None
        host = (parsed.hostname if parsed and parsed.hostname else "") or "mafreebox.freebox.fr"
        if parsed and parsed.port:
            port = parsed.port
        elif parsed and parsed.scheme == "https":
            port = 443
        elif parsed and parsed.scheme == "http":
            port = 80
        else:
            port = 554
        path = (
            f"{parsed.path or '/'}{f'?{parsed.query}' if parsed.query else ''}"
            if parsed and parsed.scheme
            else "/live/ch0"
        )

        cam_config = {
            "id": cam_id,
            "name": f"TV - {channel['name']}",
            "description": f"Chaîne TV {channel['name']} ({channel.get('category', 'Direct')})",
            "driver": DRIVER_GENERIC_RTSP,
            "host": host,
            "port": port,
            "stream_path": path,
            "stream_url": stream_url,
            "web_hls_url": web_hls_url,
            "channel_id": channel_id,
            "type": channel.get("type", "rtsp"),
            "order": mgr.cameras.get(cam_id, {}).get("order", len(mgr.cameras)),
            "linked_entities": mgr.cameras.get(cam_id, {}).get("linked_entities", []),
        }

        if cam_id in mgr.drivers:
            await mgr.drivers[cam_id].async_disconnect()
        mgr.cameras[cam_id] = cam_config
        driver = mgr._init_driver(cam_id, cam_config)
        asyncio.create_task(driver.async_connect())
        await mgr.async_save()
        mgr._notify_listeners()
        connection.send_result(msg["id"], {"success": True, "camera": cam_config})

    websocket_api.async_register_command(hass, ws_get_cameras)
    websocket_api.async_register_command(hass, ws_save_layout)
    websocket_api.async_register_command(hass, ws_save_camera)
    websocket_api.async_register_command(hass, ws_delete_camera)
    websocket_api.async_register_command(hass, ws_start_pairing)
    websocket_api.async_register_command(hass, ws_stop_pairing)
    websocket_api.async_register_command(hass, ws_pair_status)
    websocket_api.async_register_command(hass, ws_scan_wifi_aps)
    websocket_api.async_register_command(hass, ws_scan_local)
    websocket_api.async_register_command(hass, ws_get_entities)
    websocket_api.async_register_command(hass, ws_trigger_live)
    websocket_api.async_register_command(hass, ws_set_ir)
    websocket_api.async_register_command(hass, ws_reboot)
    websocket_api.async_register_command(hass, ws_detect_box)
    websocket_api.async_register_command(hass, ws_get_tv_channels)
    websocket_api.async_register_command(hass, ws_get_tv_stream)
    websocket_api.async_register_command(hass, ws_pin_tv_camera)
