"""Central Camera Manager for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import re
import time
import unicodedata
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DRIVER_ARLO_CLOUD,
    DRIVER_BLINK_HYBRID,
    DRIVER_EZVIZ_HYBRID,
    DRIVER_GENERIC_MJPEG,
    DRIVER_GENERIC_RTSP,
    DRIVER_HA_PROXY,
    DRIVER_REOLINK_HYBRID,
    DRIVER_TUYA_HYBRID,
    DRIVER_YSXLITE_PPPP,
    HYBRID_PROXY_DRIVERS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .drivers.arlo_cloud import ArloCloudAccountSession, ArloCloudDriver
from .drivers.base import BaseCameraDriver
from .drivers.cloud_accounts import (
    PROVIDER_DRIVER_MAP,
    ProviderAccountSession,
    get_tuya_oem_brands_list,
)
from .drivers.generic_rtsp import GenericRtspDriver
from .drivers.ha_proxy import HaProxyDriver, _normalize_label
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


_SECRET_KEYS = (
    "password",
    "local_key",
    "verification_code",
    "access_token",
    "token",
    "refresh_token",
    "cookie",
    "secret",
)


def _mask_url_credentials(url: str) -> str:
    """Mask embedded user:password@ credentials in RTSP/HTTP URLs."""
    if not url or "://" not in url:
        return url
    masked = re.sub(r"(://)([^/@:\s]+):([^/@\s]+)@", r"\1***:***@", url)
    return re.sub(r"(://)([^/@:\s]+)@", r"\1***@", masked)


def _sanitize_camera_public(cam: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of camera data with secrets removed and URL credentials masked."""
    clean = dict(cam)
    for key in _SECRET_KEYS:
        clean.pop(key, None)
    for url_key in ("stream_url", "rtsp_url", "hls_url", "web_hls_url"):
        if isinstance(clean.get(url_key), str) and clean[url_key]:
            clean[url_key] = _mask_url_credentials(clean[url_key])
    if isinstance(clean.get("capabilities"), dict):
        caps = dict(clean["capabilities"])
        for key in _SECRET_KEYS:
            caps.pop(key, None)
        for url_key in ("stream_url", "rtsp_url", "hls_url", "web_hls_url"):
            if isinstance(caps.get(url_key), str) and caps[url_key]:
                caps[url_key] = _mask_url_credentials(caps[url_key])
        clean["capabilities"] = caps
    return clean


class CameraManager:
    """Manages all registered cameras, drivers, pairing, and layout persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize camera manager."""
        self.hass = hass
        self.store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.cameras: dict[str, dict[str, Any]] = {}
        self.drivers: dict[str, BaseCameraDriver] = {}
        self.arlo_accounts: dict[str, dict[str, Any]] = {}
        self.arlo_sessions: dict[str, ArloCloudAccountSession] = {}
        self._pending_arlo_logins: dict[str, ArloCloudAccountSession] = {}
        self.provider_accounts: dict[str, dict[str, Any]] = {}
        self.provider_sessions: dict[str, ProviderAccountSession] = {}
        self._pending_provider_logins: dict[str, ProviderAccountSession] = {}
        self.pairing_engine = WifiPairingEngine(hass)
        self.box_detector = BoxDetectorService(hass)
        self._listeners: list[Any] = []
        self._bg_tasks: set[asyncio.Task[Any]] = set()

    def _spawn_bg_task(self, coro: Any) -> asyncio.Task[Any]:
        """Track background tasks so they can be cancelled cleanly on unload."""
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    async def async_close(self) -> None:
        """Cancel background tasks, disconnect drivers, and close all cloud sessions."""
        for task in list(self._bg_tasks):
            if not task.done():
                task.cancel()
        if self._bg_tasks:
            await asyncio.gather(*self._bg_tasks, return_exceptions=True)
        self._bg_tasks.clear()

        for driver in list(self.drivers.values()):
            await driver.async_disconnect()
        for session in list(self.arlo_sessions.values()):
            await session.async_close()
        for session in list(self._pending_arlo_logins.values()):
            await session.async_close()
        self._pending_arlo_logins.clear()
        for session in list(self.provider_sessions.values()):
            await session.async_close()
        for session in list(self._pending_provider_logins.values()):
            await session.async_close()
        self._pending_provider_logins.clear()
        self._listeners.clear()

    async def async_load(self) -> None:
        """Load Arlo cloud accounts, camera configs, and layout order from persistent storage."""
        data = await self.store.async_load()
        if data and isinstance(data, dict):
            raw_accounts = data.get("arlo_accounts", {})
            for aid, acfg in raw_accounts.items():
                if not isinstance(acfg, dict):
                    continue
                self.arlo_accounts[aid] = acfg
                self.arlo_sessions[aid] = ArloCloudAccountSession(
                    account_id=str(acfg.get("id") or aid),
                    email=str(acfg.get("email") or ""),
                    name=str(acfg.get("name") or ""),
                    token=str(acfg.get("token") or ""),
                    user_id=str(acfg.get("user_id") or ""),
                    serial_number=str(acfg.get("serial_number") or ""),
                    xcloud_id=str(acfg.get("xcloud_id") or ""),
                    status=str(acfg.get("status") or ("connected" if acfg.get("token") else "disconnected")),
                    last_sync=acfg.get("last_sync"),
                    devices=list(acfg.get("devices") or []),
                    hass=self.hass,
                    cookie=str(acfg.get("cookie") or ""),
                )

            raw_providers = data.get("provider_accounts", {})
            for aid, pcfg in raw_providers.items():
                if not isinstance(pcfg, dict):
                    continue
                self.provider_accounts[aid] = pcfg
                self.provider_sessions[aid] = ProviderAccountSession(
                    account_id=str(pcfg.get("id") or aid),
                    provider=str(pcfg.get("provider") or "tuya_oem"),
                    name=str(pcfg.get("name") or ""),
                    username=str(pcfg.get("username") or ""),
                    password=str(pcfg.get("password") or ""),
                    brand=str(pcfg.get("brand") or "smartlife"),
                    country_code=str(pcfg.get("country_code") or "33"),
                    host=str(pcfg.get("host") or ""),
                    port=int(pcfg.get("port") or 80),
                    rtsp_port=int(pcfg.get("rtsp_port") or 554),
                    verification_code=str(pcfg.get("verification_code") or ""),
                    region=str(pcfg.get("region") or "eu"),
                    token=str(pcfg.get("token") or ""),
                    refresh_token=str(pcfg.get("refresh_token") or ""),
                    uid=str(pcfg.get("uid") or ""),
                    account_num_id=str(pcfg.get("account_num_id") or ""),
                    client_id=str(pcfg.get("client_id") or ""),
                    hardware_id=str(pcfg.get("hardware_id") or ""),
                    status=str(pcfg.get("status") or ("connected" if pcfg.get("token") else "disconnected")),
                    last_sync=pcfg.get("last_sync"),
                    last_error=str(pcfg.get("last_error") or ""),
                    devices=list(pcfg.get("devices") or []),
                    hass=self.hass,
                )

            raw_cams = data.get("cameras", {})
            for cid, ccfg in raw_cams.items():
                self.cameras[cid] = ccfg
                self._init_driver(cid, ccfg)
        else:
            # Seed with demo/default configuration if totally empty
            _LOGGER.info("No saved DomoLink cameras found. Ready for pairing or addition.")

        # Connect drivers in background
        for driver in self.drivers.values():
            self._spawn_bg_task(driver.async_connect())

        if self.cameras:
            self._spawn_bg_task(self.async_auto_enrich_hybrid_cameras(delay=3.0))

    async def async_save(self) -> None:
        """Persist cameras, layout, and Cloud accounts to disk."""
        for aid, session in self.arlo_sessions.items():
            self.arlo_accounts[aid] = session.to_dict()
        for aid, session in self.provider_sessions.items():
            self.provider_accounts[aid] = session.to_dict()
        await self.store.async_save({
            "cameras": self.cameras,
            "arlo_accounts": self.arlo_accounts,
            "provider_accounts": self.provider_accounts,
        })

    def _init_driver(self, camera_id: str, config: dict[str, Any]) -> BaseCameraDriver:
        """Instantiate driver based on configuration."""
        driver_type = config.get("driver", DRIVER_YSXLITE_PPPP)
        host = str(config.get("host", ""))

        if driver_type == DRIVER_ARLO_CLOUD:
            acc_id = str(config.get("arlo_account_id") or "")
            session = self.arlo_sessions.get(acc_id)
            driver = ArloCloudDriver(
                camera_id, config, hass=self.hass, account_session=session
            )
        elif host.startswith("camera.") or driver_type in HYBRID_PROXY_DRIVERS:
            driver = HaProxyDriver(camera_id, config, hass=self.hass)
        elif driver_type in (DRIVER_GENERIC_RTSP, DRIVER_GENERIC_MJPEG):
            driver = GenericRtspDriver(camera_id, config, hass=self.hass)
        else:
            driver = YsxLiteDriver(camera_id, config)

        self.drivers[camera_id] = driver
        return driver

    async def async_auto_enrich_hybrid_cameras(self, delay: float = 0.0) -> int:
        """Auto-upgrade existing HA proxy cameras (Tuya, Reolink, Ezviz, Blink, Xiaomi) with LAN metadata."""
        if delay > 0:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return 0

        changed = 0
        for cid, cam_cfg in list(self.cameras.items()):
            if not isinstance(cam_cfg, dict):
                continue
            cur_driver = str(cam_cfg.get("driver") or "")
            host = str(cam_cfg.get("host") or "")
            if cur_driver not in HYBRID_PROXY_DRIVERS and not host.startswith("camera."):
                continue

            drv = self.drivers.get(cid)
            if not isinstance(drv, HaProxyDriver):
                drv = self._init_driver(cid, cam_cfg)
                if not isinstance(drv, HaProxyDriver):
                    continue

            try:
                meta = await drv.async_resolve_hybrid_metadata(force=True)
            except Exception as err:
                _LOGGER.debug("[%s] Hybrid metadata enrichment failed: %s", cid, err)
                continue

            plat = str(meta.get("platform") or cam_cfg.get("platform") or "").lower()
            brand_hint = f"{plat} {cam_cfg.get('brand', '')} {host}".lower()
            target_driver = cur_driver

            if cur_driver == DRIVER_HA_PROXY:
                if plat in ("tuya", "domolink_tuya_oem", "localtuya", "tuya_local") or meta.get("tuya_device_id"):
                    target_driver = DRIVER_TUYA_HYBRID
                elif plat == "reolink" or "reolink" in brand_hint:
                    target_driver = DRIVER_REOLINK_HYBRID
                elif plat == "ezviz" or "ezviz" in brand_hint:
                    target_driver = DRIVER_EZVIZ_HYBRID
                elif plat == "blink" or "blink" in brand_hint:
                    target_driver = DRIVER_BLINK_HYBRID

            cam_modified = False
            if target_driver != cur_driver:
                cam_cfg["driver"] = target_driver
                drv.driver_type = target_driver
                cam_modified = True

            for field_name in (
                "local_ip",
                "mac_address",
                "tuya_device_id",
                "tuya_oem_entity_id",
                "brand",
                "model_id",
            ):
                val = cam_cfg.get(field_name) or meta.get(field_name) or getattr(drv, field_name, "")
                if val and cam_cfg.get(field_name) != val:
                    cam_cfg[field_name] = val
                    cam_modified = True

            if cam_modified:
                changed += 1

        if changed:
            await self.async_save()
            self._notify_listeners()
            _LOGGER.info("Hybrid Option 2 enrichment updated %d camera(s)", changed)
        return changed

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
                "http_port": c.get("http_port", 80),
                "stream_path": c.get("stream_path", ""),
                "snapshot_path": c.get("snapshot_path", ""),
                "username": c.get("username", ""),
                "stream_url": c.get("stream_url", ""),
                "web_hls_url": c.get("web_hls_url", ""),
                "channel_id": c.get("channel_id", ""),
                "arlo_account_id": c.get("arlo_account_id", ""),
                "arlo_device_id": c.get("arlo_device_id", ""),
                "parent_id": c.get("parent_id", ""),
                "xcloud_id": c.get("xcloud_id", ""),
                "model_id": c.get("model_id", ""),
                "ha_entity_id": c.get("ha_entity_id", ""),
                "tuya_device_id": c.get("tuya_device_id", ""),
                "tuya_oem_entity_id": c.get("tuya_oem_entity_id", ""),
                "local_ip": c.get("local_ip", "") or caps.get("local_ip", ""),
                "mac_address": c.get("mac_address", "") or caps.get("mac_address", ""),
                "wifi_ssid": c.get("wifi_ssid", "") or caps.get("wifi_ssid", ""),
                "wifi_rssi": c.get("wifi_rssi") if c.get("wifi_rssi") is not None else caps.get("wifi_rssi"),
                "brand": c.get("brand", "") or caps.get("brand", ""),
                "stream_mode": caps.get("stream_mode", ""),
                "battery_protected_mode": bool(caps.get("battery_protected_mode", False)),
                "order": c.get("order", 0),
                "linked_entities": c.get("linked_entities", []),
                "status": status,
                "is_streaming": bool(driver and driver.is_streaming),
                "fps": round(driver.fps, 1) if driver else 0.0,
                "hls_url": (driver._stream_url if driver else None) or c.get("web_hls_url") or "",
                "capabilities": caps,
                "has_snapshot": has_snap,
                "snapshot_timestamp": snap_time,
                "night_vision": c.get("night_vision", False),
            }
            result.append(_sanitize_camera_public(item))
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
            # Generate pure ASCII URL-safe ID from name or timestamp
            import re, unicodedata
            raw_name = str(camera_data.get("name") or "camera")
            clean_name = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("ascii")
            slug = re.sub(r"[^\w\s-]", "", clean_name.lower())
            slug = re.sub(r"[-\s]+", "_", slug).strip("-_") or "cam"
            cid = f"cam_{slug}_{int(time.time())}"
            camera_data["id"] = cid

        # Keep existing order or assign to end, and preserve stored secrets if omitted
        existing = self.cameras.get(cid)
        if existing:
            for secret_key in ("password", "local_key", "verification_code"):
                if secret_key not in camera_data and existing.get(secret_key):
                    camera_data[secret_key] = existing[secret_key]
            if "order" not in camera_data and "order" in existing:
                camera_data["order"] = existing["order"]

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
            driver._explicit_live = True
            await driver.async_start_stream()
            return True
        return False

    async def async_stop_live(self, camera_id: str) -> bool:
        """Return camera to periodic snapshot mode."""
        driver = self.drivers.get(camera_id)
        if driver:
            driver._explicit_live = False
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

    # --- Multi-Account Arlo Cloud Management ---

    def _slugify(self, raw_text: str, fallback: str = "cam") -> str:
        """Return pure ASCII slug suitable for entity/camera IDs."""
        clean = unicodedata.normalize("NFKD", str(raw_text or "")).encode("ascii", "ignore").decode("ascii")
        slug = re.sub(r"[^\w\s-]", "", clean.lower())
        slug = re.sub(r"[-\s]+", "_", slug).strip("-_")
        return slug or fallback

    def _make_account_id(self, email: str, account_name: str = "") -> str:
        """Resolve an existing account ID for same email or create a unique multi-account ID."""
        norm_email = (email or "").strip().lower()
        if norm_email:
            for aid, sess in self.arlo_sessions.items():
                if (sess.email or "").strip().lower() == norm_email:
                    return aid
        base = self._slugify(account_name or norm_email.split("@")[0], fallback="compte")
        candidate = f"arlo_{base}_{int(time.time())}"
        while candidate in self.arlo_sessions:
            candidate = f"{candidate}_x"
        return candidate

    def _find_matching_ha_arlo_entity(self, device_name: str, device_id: str) -> str:
        """Find a matching Home Assistant camera entity (e.g. from aarlo) for hybrid fallback."""
        if not self.hass or not hasattr(self.hass, "states"):
            return ""
        try:
            target_name = self._slugify(device_name, fallback="")
            target_dev = str(device_id or "").lower()
            for state in self.hass.states.async_all():
                eid = str(getattr(state, "entity_id", ""))
                if not eid.startswith("camera."):
                    continue
                attrs = getattr(state, "attributes", {}) or {}
                if attrs.get("platform") == "domolink_camera":
                    continue
                eid_lower = eid.lower()
                attr_dev = str(attrs.get("device_id") or "").lower()
                if target_dev and (target_dev in eid_lower or target_dev == attr_dev):
                    return eid
                if ("arlo" in eid_lower or "aarlo" in str(attrs.get("attribution", "")).lower() or "arlo" in str(attrs.get("brand", "")).lower()) and target_name:
                    friendly_slug = self._slugify(attrs.get("friendly_name", ""), fallback="")
                    if target_name and (target_name == friendly_slug or target_name in eid_lower):
                        return eid
        except Exception:
            pass
        return ""

    def get_arlo_accounts_list(self) -> list[dict[str, Any]]:
        """Return sanitized list of all configured Arlo Cloud accounts and their cameras."""
        configured_device_ids = {
            str(c.get("arlo_device_id"))
            for c in self.cameras.values()
            if c.get("arlo_device_id")
        }
        return [
            sess.to_public_dict(configured_device_ids)
            for sess in self.arlo_sessions.values()
        ]

    async def async_arlo_start_login(
        self,
        email: str,
        password: str,
        account_name: str = "",
        auto_add: bool = True,
    ) -> dict[str, Any]:
        """Start Arlo Cloud login flow (returns 2FA factors or connects directly)."""
        account_id = self._make_account_id(email, account_name)
        stale_pending = self._pending_arlo_logins.pop(account_id, None)
        if stale_pending:
            await stale_pending.async_close()

        existing = self.arlo_sessions.get(account_id)
        session = ArloCloudAccountSession(
            account_id=account_id,
            email=email,
            name=account_name or (existing.name if existing else ""),
            hass=self.hass,
        )
        try:
            res = await session.async_start_login(password)
        except Exception as err:
            await session.async_close()
            return {"status": "error", "error": str(err)}
        status = res.get("status")

        if status == "2fa_required":
            self._pending_arlo_logins[account_id] = session
            return res

        if status == "connected":
            if existing and existing is not session:
                await existing.async_close()
            self.arlo_sessions[account_id] = session
            self.arlo_accounts[account_id] = session.to_dict()
            sync_res = await self.async_arlo_sync_account(
                account_id, auto_add=auto_add, refresh_remote=False
            )
            return {
                "status": "connected",
                "account": sync_res.get("account"),
                "imported_count": sync_res.get("imported_count", 0),
                "total_devices": sync_res.get("total_devices", 0),
            }

        await session.async_close()
        return res

    async def async_arlo_request_2fa(
        self, session_id: str, factor_id: str
    ) -> dict[str, Any]:
        """Trigger Arlo OTP / push challenge for an ongoing 2FA login session."""
        session = self._pending_arlo_logins.get(session_id)
        if not session:
            return {"status": "error", "error": "Session d'authentification introuvable ou expirée."}
        return await session.async_request_2fa_code(factor_id)

    async def async_arlo_verify_2fa(
        self,
        session_id: str,
        otp_code: str,
        factor_auth_code: str | None = None,
        auto_add: bool = True,
    ) -> dict[str, Any]:
        """Complete Arlo 2FA verification, persist account, and import cameras."""
        session = self._pending_arlo_logins.get(session_id)
        if not session:
            return {"status": "error", "error": "Session d'authentification 2FA introuvable ou expirée."}

        try:
            res = await session.async_verify_2fa_code(otp_code, factor_auth_code)
        except Exception as err:
            return {"status": "error", "error": str(err)}

        if res.get("status") != "connected":
            return res

        self._pending_arlo_logins.pop(session_id, None)
        old_session = self.arlo_sessions.get(session.account_id)
        if old_session and old_session is not session:
            await old_session.async_close()

        self.arlo_sessions[session.account_id] = session
        self.arlo_accounts[session.account_id] = session.to_dict()
        sync_res = await self.async_arlo_sync_account(
            session.account_id, auto_add=auto_add, refresh_remote=False
        )
        return {
            "status": "connected",
            "account": sync_res.get("account"),
            "imported_count": sync_res.get("imported_count", 0),
            "total_devices": sync_res.get("total_devices", 0),
        }

    async def async_arlo_save_token(
        self,
        email: str,
        token: str,
        account_name: str = "",
        user_id: str = "",
        xcloud_id: str = "",
        cookie: str = "",
        account_id: str = "",
        auto_add: bool = True,
    ) -> dict[str, Any]:
        """Register or refresh an Arlo account directly using an Authorization token."""
        target_id = account_id.strip() or self._make_account_id(email, account_name)
        session = self.arlo_sessions.get(target_id)
        created_new = False
        if not session:
            created_new = True
            session = ArloCloudAccountSession(
                account_id=target_id,
                email=email,
                name=account_name,
                hass=self.hass,
            )
        else:
            if email.strip():
                session.email = email.strip()
            if account_name.strip():
                session.name = account_name.strip()

        try:
            res = await session.async_validate_and_set_token(
                token=token,
                user_id=user_id,
                xcloud_id=xcloud_id,
                cookie=cookie,
            )
        except Exception as err:
            adopted = False
            if "401" in str(err) or "403" in str(err):
                adopted = await session.async_try_adopt_local_aarlo_session(test_connection=True)
            if adopted:
                res = {"status": "connected", "devices": session.devices}
            else:
                if created_new:
                    await session.async_close()
                return {"status": "error", "error": str(err)}

        if res.get("status") != "connected":
            adopted = await session.async_try_adopt_local_aarlo_session(test_connection=True)
            if adopted:
                res = {"status": "connected", "devices": session.devices}
            else:
                if created_new:
                    await session.async_close()
                return res

        self.arlo_sessions[target_id] = session
        self.arlo_accounts[target_id] = session.to_dict()
        sync_res = await self.async_arlo_sync_account(
            target_id, auto_add=auto_add, refresh_remote=False
        )
        return {
            "status": "connected",
            "account": sync_res.get("account"),
            "imported_count": sync_res.get("imported_count", 0),
            "total_devices": sync_res.get("total_devices", 0),
        }

    async def async_arlo_sync_account(
        self,
        account_id: str,
        auto_add: bool = True,
        refresh_remote: bool = True,
    ) -> dict[str, Any]:
        """Fetch latest cameras from an Arlo account and optionally add/update them in DomoLink."""
        session = self.arlo_sessions.get(account_id)
        if not session:
            return {"status": "error", "error": f"Compte Arlo '{account_id}' introuvable."}

        if refresh_remote:
            try:
                devices = await session.async_fetch_devices()
            except Exception as err:
                self.arlo_accounts[account_id] = session.to_dict()
                await self.async_save()
                return {"status": "error", "error": str(err)}
        else:
            devices = list(session.devices)

        imported_count = 0
        if auto_add:
            for dev in devices:
                dev_id = str(dev["device_id"])
                dev_slug = self._slugify(dev["name"], fallback="")
                ha_ent = self._find_matching_ha_arlo_entity(dev["name"], dev_id)
                existing_cid = None
                for cid, cam in self.cameras.items():
                    if str(cam.get("arlo_device_id") or "") == dev_id:
                        existing_cid = cid
                        break

                ha_match_cid = None
                for cid, cam in self.cameras.items():
                    if cid == existing_cid:
                        continue
                    c_host = str(cam.get("host") or "").lower()
                    c_ha_ent = str(cam.get("ha_entity_id") or "").lower()
                    if ha_ent and (c_ha_ent == ha_ent.lower() or c_host == ha_ent.lower()):
                        ha_match_cid = cid
                        break
                    if cam.get("driver") == DRIVER_HA_PROXY and (
                        "aarlo" in c_host or "arlo" in c_host
                    ):
                        c_name_slug = self._slugify(cam.get("name", ""), fallback="")
                        if dev_id.lower() in c_host or (
                            dev_slug and (c_name_slug == dev_slug or dev_slug in c_host)
                        ):
                            ha_match_cid = cid
                            if not ha_ent and c_host.startswith("camera."):
                                ha_ent = str(cam.get("host") or "")
                            break

                stale_dup_cid = None
                if existing_cid and ha_match_cid:
                    dup_cam = self.cameras.get(existing_cid, {})
                    orig_cam = self.cameras.get(ha_match_cid, {})
                    if orig_cam.get("order", 999) <= dup_cam.get("order", 999):
                        stale_dup_cid = existing_cid
                        existing_cid = ha_match_cid
                    else:
                        stale_dup_cid = ha_match_cid
                elif not existing_cid and ha_match_cid:
                    existing_cid = ha_match_cid

                if stale_dup_cid and stale_dup_cid in self.cameras:
                    if stale_dup_cid in self.drivers:
                        try:
                            await self.drivers[stale_dup_cid].async_disconnect()
                        except Exception:
                            pass
                        del self.drivers[stale_dup_cid]
                    self.cameras.pop(stale_dup_cid, None)

                if existing_cid:
                    cam = self.cameras[existing_cid]
                    was_cloud_driver = cam.get("driver") == DRIVER_ARLO_CLOUD
                    cam["driver"] = DRIVER_ARLO_CLOUD
                    cam["host"] = dev_id
                    cam["port"] = 443
                    cam["arlo_account_id"] = account_id
                    cam["account_email"] = session.email
                    cam["arlo_device_id"] = dev_id
                    cam["parent_id"] = dev.get("parent_id", dev_id)
                    cam["xcloud_id"] = dev.get("xcloud_id", "")
                    cam["model_id"] = dev.get("model_id", cam.get("model_id", "Arlo"))
                    if dev.get("local_ip"):
                        cam["local_ip"] = dev["local_ip"]
                    if dev.get("mac_address"):
                        cam["mac_address"] = dev["mac_address"]
                    if dev.get("wifi_ssid"):
                        cam["wifi_ssid"] = dev["wifi_ssid"]
                    if dev.get("wifi_rssi") is not None:
                        cam["wifi_rssi"] = dev["wifi_rssi"]
                    if ha_ent:
                        cam["ha_entity_id"] = ha_ent
                    drv = self.drivers.get(existing_cid)
                    if isinstance(drv, ArloCloudDriver) and was_cloud_driver:
                        drv.account_session = session
                        drv.config = cam
                        if dev.get("local_ip"):
                            drv.local_ip = str(dev["local_ip"])
                    else:
                        if drv is not None:
                            try:
                                await drv.async_disconnect()
                            except Exception:
                                pass
                        new_drv = self._init_driver(existing_cid, cam)
                        asyncio.create_task(new_drv.async_connect())
                else:
                    slug = self._slugify(dev["device_id"], fallback="arlo")
                    cid = f"arlo_{slug}"
                    if cid in self.cameras:
                        cid = f"arlo_{slug}_{int(time.time())}"
                    max_order = max([c.get("order", 0) for c in self.cameras.values()], default=-1)
                    cam_cfg = {
                        "id": cid,
                        "name": dev["name"],
                        "description": f"Arlo {dev.get('model_id', '')} ({session.email})".strip(),
                        "driver": DRIVER_ARLO_CLOUD,
                        "host": dev_id,
                        "port": 443,
                        "arlo_account_id": account_id,
                        "arlo_device_id": dev_id,
                        "parent_id": dev.get("parent_id", dev_id),
                        "xcloud_id": dev.get("xcloud_id", ""),
                        "model_id": dev.get("model_id", "Arlo"),
                        "account_email": session.email,
                        "ha_entity_id": ha_ent,
                        "local_ip": dev.get("local_ip", ""),
                        "mac_address": dev.get("mac_address", ""),
                        "wifi_ssid": dev.get("wifi_ssid", ""),
                        "wifi_rssi": dev.get("wifi_rssi"),
                        "order": max_order + 1,
                        "linked_entities": [],
                    }
                    self.cameras[cid] = cam_cfg
                    drv = self._init_driver(cid, cam_cfg)
                    asyncio.create_task(drv.async_connect())
                    imported_count += 1

        self.arlo_accounts[account_id] = session.to_dict()
        await self.async_save()
        self._notify_listeners()

        configured_device_ids = {
            str(c.get("arlo_device_id"))
            for c in self.cameras.values()
            if c.get("arlo_device_id")
        }
        return {
            "status": "synced",
            "account": session.to_public_dict(configured_device_ids),
            "imported_count": imported_count,
            "total_devices": len(devices),
        }

    async def async_arlo_delete_account(
        self, account_id: str, delete_cameras: bool = False
    ) -> bool:
        """Delete an Arlo account session and optionally remove all cameras owned by it."""
        session = self.arlo_sessions.pop(account_id, None)
        if session:
            await session.async_close()
        existed = account_id in self.arlo_accounts or session is not None
        self.arlo_accounts.pop(account_id, None)
        self._pending_arlo_logins.pop(account_id, None)

        if delete_cameras:
            to_delete = [
                cid
                for cid, cam in list(self.cameras.items())
                if cam.get("arlo_account_id") == account_id
            ]
            for cid in to_delete:
                if cid in self.drivers:
                    await self.drivers[cid].async_disconnect()
                    del self.drivers[cid]
                del self.cameras[cid]

        if existed:
            await self.async_save()
            self._notify_listeners()
        return existed

    # --- Multi-Brand Cloud / LAN Accounts (Tuya OEM, Blink, Ezviz, Reolink) ---

    def _configured_provider_keys(self) -> set[str]:
        """Collect all identifying keys of already registered cameras."""
        keys: set[str] = set()
        for c in self.cameras.values():
            for k in ("device_id", "tuya_device_id", "ha_entity_id", "tuya_oem_entity_id", "host"):
                v = str(c.get(k) or "").strip()
                if v:
                    keys.add(v)
            lip = str(c.get("local_ip") or "").strip()
            if lip:
                keys.add(f"ip:{lip}")
        return keys

    def get_provider_accounts_list(self) -> dict[str, Any]:
        """Return sanitized list of all multi-brand provider accounts and supported Tuya OEM apps."""
        cfg = self._configured_provider_keys()
        return {
            "accounts": [sess.to_public_dict(cfg) for sess in self.provider_sessions.values()],
            "tuya_oem_brands": get_tuya_oem_brands_list(),
        }

    def _make_provider_account_id(self, provider: str, identifier: str, account_name: str = "") -> str:
        """Reuse an existing account ID or generate a clean unique ID for provider session."""
        norm = (identifier or "").strip().lower()
        for aid, sess in self.provider_sessions.items():
            if sess.provider != provider:
                continue
            cand = (sess.username or sess.host or "").strip().lower()
            if norm and cand == norm:
                return aid
        base = self._slugify(account_name or norm.split("@")[0], fallback=provider)
        aid = f"prov_{provider}_{base}_{int(time.time())}"
        while aid in self.provider_sessions:
            aid = f"{aid}_x"
        return aid

    async def async_provider_start_login(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Initiate login or direct connection for Tuya OEM, Blink, Ezviz, or Reolink."""
        provider = str(payload.get("provider") or "").strip().lower()
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        host = str(payload.get("host") or "").strip()
        account_name = str(payload.get("account_name") or "").strip()
        account_id = str(payload.get("account_id") or "").strip() or self._make_provider_account_id(
            provider, username or host, account_name
        )

        stale = self._pending_provider_logins.pop(account_id, None)
        if stale:
            await stale.async_close()

        session = ProviderAccountSession(
            account_id=account_id,
            provider=provider,
            name=account_name,
            username=username,
            password=password,
            brand=str(payload.get("brand") or "smartlife"),
            country_code=str(payload.get("country_code") or "33"),
            host=host,
            port=int(payload.get("port") or 80),
            rtsp_port=int(payload.get("rtsp_port") or 554),
            verification_code=str(payload.get("verification_code") or ""),
            region=str(payload.get("region") or "eu"),
            hass=self.hass,
        )
        res = await session.async_start_login()
        status = res.get("status")

        if status == "2fa_required":
            self._pending_provider_logins[account_id] = session
            return res

        if status == "connected":
            existing = self.provider_sessions.get(account_id)
            if existing and existing is not session:
                await existing.async_close()
            self.provider_sessions[account_id] = session
            self.provider_accounts[account_id] = session.to_dict()
            sync_res = await self.async_provider_sync_account(
                account_id,
                auto_add=bool(payload.get("auto_add", True)),
                refresh_remote=False,
            )
            return {
                "status": "connected",
                "account": sync_res.get("account"),
                "imported_count": sync_res.get("imported_count", 0),
                "total_devices": sync_res.get("total_devices", 0),
            }

        await session.async_close()
        return res

    async def async_provider_verify_2fa(
        self, session_id: str, otp_code: str, auto_add: bool = True
    ) -> dict[str, Any]:
        """Complete 2FA challenge for Blink or Ezviz and sync cameras."""
        session = self._pending_provider_logins.get(session_id)
        if not session:
            return {"status": "error", "error": "Session 2FA introuvable ou expirée."}

        res = await session.async_verify_2fa(otp_code)
        if res.get("status") == "connected":
            self._pending_provider_logins.pop(session_id, None)
            existing = self.provider_sessions.get(session_id)
            if existing and existing is not session:
                await existing.async_close()
            self.provider_sessions[session_id] = session
            self.provider_accounts[session_id] = session.to_dict()
            sync_res = await self.async_provider_sync_account(
                session_id, auto_add=auto_add, refresh_remote=False
            )
            return {
                "status": "connected",
                "account": sync_res.get("account"),
                "imported_count": sync_res.get("imported_count", 0),
                "total_devices": sync_res.get("total_devices", 0),
            }
        return res

    async def async_provider_sync_account(
        self, account_id: str, auto_add: bool = True, refresh_remote: bool = True
    ) -> dict[str, Any]:
        """Sync cameras from a multi-brand provider session without duplicating existing cameras."""
        session = self.provider_sessions.get(account_id)
        if not session:
            return {"status": "error", "error": "Compte fournisseur introuvable."}

        if refresh_remote:
            devices = await session.async_fetch_devices()
        else:
            devices = session.devices or await session.async_fetch_devices()

        target_driver = PROVIDER_DRIVER_MAP.get(session.provider, DRIVER_HA_PROXY)
        imported_count = 0

        for dev in devices:
            dev_id = str(dev.get("device_id") or "").strip()
            tuya_id = str(dev.get("tuya_device_id") or "").strip()
            ha_eid = str(dev.get("ha_entity_id") or "").strip()
            oem_eid = str(dev.get("tuya_oem_entity_id") or "").strip()
            local_ip = str(dev.get("local_ip") or "").strip()
            dev_norm = _normalize_label(dev.get("name"))

            existing_cid = None
            for cid, cam in self.cameras.items():
                if tuya_id and cam.get("tuya_device_id") == tuya_id:
                    existing_cid = cid
                    break
                if dev_id and (cam.get("device_id") == dev_id or cam.get("host") == dev_id):
                    existing_cid = cid
                    break
                if ha_eid and (cam.get("ha_entity_id") == ha_eid or cam.get("host") == ha_eid):
                    existing_cid = cid
                    break
                if oem_eid and (cam.get("tuya_oem_entity_id") == oem_eid or cam.get("host") == oem_eid):
                    existing_cid = cid
                    break
                if local_ip and cam.get("local_ip") == local_ip and cam.get("driver") == target_driver:
                    existing_cid = cid
                    break
                if dev_norm and _normalize_label(cam.get("name")) == dev_norm and cam.get("driver") in (DRIVER_HA_PROXY, target_driver):
                    existing_cid = cid
                    break

            if existing_cid:
                cam = self.cameras[existing_cid]
                old_drv = cam.get("driver")
                if old_drv == DRIVER_HA_PROXY:
                    cam["driver"] = target_driver
                cam["provider_account_id"] = account_id
                if tuya_id:
                    cam["tuya_device_id"] = tuya_id
                if oem_eid:
                    cam["tuya_oem_entity_id"] = oem_eid
                if ha_eid and not cam.get("ha_entity_id"):
                    cam["ha_entity_id"] = ha_eid
                if local_ip:
                    cam["local_ip"] = local_ip
                for fld in ("mac_address", "local_key", "rtsp_url", "model_id"):
                    if dev.get(fld):
                        cam[fld] = dev[fld]
                if session.provider in ("ezviz", "reolink"):
                    if session.username:
                        cam["username"] = session.username
                    if session.password:
                        cam["password"] = session.password
                    if session.verification_code:
                        cam["verification_code"] = session.verification_code
                if old_drv != cam.get("driver"):
                    old_obj = self.drivers.get(existing_cid)
                    if old_obj:
                        try:
                            await old_obj.async_disconnect()
                        except Exception:
                            pass
                    new_drv = self._init_driver(existing_cid, cam)
                    asyncio.create_task(new_drv.async_connect())
            elif auto_add:
                slug = self._slugify(dev.get("name") or dev_id or session.provider, fallback=session.provider)
                cid = f"{session.provider}_{slug}"
                if cid in self.cameras:
                    cid = f"{cid}_{int(time.time())}"
                max_order = max([c.get("order", 0) for c in self.cameras.values()], default=-1)
                cam_host = ha_eid or oem_eid or local_ip or dev_id or session.host
                cam_cfg: dict[str, Any] = {
                    "id": cid,
                    "name": dev.get("name") or f"Caméra {session.provider.upper()}",
                    "description": f"{session.provider.upper()} {dev.get('model_id', '')}".strip(),
                    "driver": target_driver,
                    "host": cam_host,
                    "port": int(dev.get("rtsp_port") or session.rtsp_port or 554),
                    "provider_account_id": account_id,
                    "device_id": dev_id,
                    "tuya_device_id": tuya_id,
                    "tuya_oem_entity_id": oem_eid,
                    "ha_entity_id": ha_eid,
                    "local_ip": local_ip,
                    "mac_address": dev.get("mac_address", ""),
                    "local_key": dev.get("local_key", ""),
                    "rtsp_url": dev.get("rtsp_url", ""),
                    "model_id": dev.get("model_id", session.provider.upper()),
                    "brand": session.provider.upper(),
                    "order": max_order + 1,
                    "linked_entities": [],
                }
                if session.provider in ("ezviz", "reolink"):
                    cam_cfg["username"] = session.username
                    cam_cfg["password"] = session.password
                    cam_cfg["verification_code"] = session.verification_code
                self.cameras[cid] = cam_cfg
                drv = self._init_driver(cid, cam_cfg)
                asyncio.create_task(drv.async_connect())
                imported_count += 1

        self.provider_accounts[account_id] = session.to_dict()
        await self.async_save()
        self._notify_listeners()

        return {
            "status": "synced",
            "account": session.to_public_dict(self._configured_provider_keys()),
            "imported_count": imported_count,
            "total_devices": len(devices),
        }

    async def async_provider_delete_account(
        self, account_id: str, delete_cameras: bool = False
    ) -> bool:
        """Delete a multi-brand provider account session."""
        session = self.provider_sessions.pop(account_id, None)
        if session:
            await session.async_close()
        existed = account_id in self.provider_accounts or session is not None
        self.provider_accounts.pop(account_id, None)
        self._pending_provider_logins.pop(account_id, None)

        if delete_cameras:
            to_delete = [
                cid for cid, cam in list(self.cameras.items()) if cam.get("provider_account_id") == account_id
            ]
            for cid in to_delete:
                if cid in self.drivers:
                    await self.drivers[cid].async_disconnect()
                    del self.drivers[cid]
                del self.cameras[cid]

        if existed:
            await self.async_save()
            self._notify_listeners()
        return existed
