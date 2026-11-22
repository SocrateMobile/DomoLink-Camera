"""Home Assistant Camera Proxy Driver for DomoLink Camera."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import glob
import ipaddress
import json
import logging
import os
import re
import shutil
import time
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import aiohttp

from .base import BaseCameraDriver, async_has_ffmpeg
from ..const import (
    DRIVER_BLINK_HYBRID,
    DRIVER_EZVIZ_HYBRID,
    DRIVER_HA_PROXY,
    DRIVER_REOLINK_HYBRID,
    DRIVER_TUYA_HYBRID,
    STATUS_CONNECTING,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_STREAMING,
)

_LOGGER = logging.getLogger(__name__)

_TUYA_DEVID_RE = re.compile(r"(?:^|[^0-9a-z])(bf[0-9a-z]{18,22}|[0-9a-f]{20,24})(?:$|[^0-9a-z])")
_MAC_RE = re.compile(r"(?:[0-9a-f]{2}[:\-]){5}[0-9a-f]{2}", re.IGNORECASE)


def _normalize_mac(mac: Any) -> str:
    """Normalize a MAC address to lowercase colon-separated aa:bb:cc:dd:ee:ff."""
    raw = re.sub(r"[^0-9a-f]", "", str(mac or "").lower())
    if len(raw) != 12:
        return ""
    return ":".join(raw[i : i + 2] for i in range(0, 12, 2))


def _normalize_label(text: Any) -> str:
    """Normalize friendly name / model labels for cross-integration matching."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def is_private_lan_ip(host_or_url: str) -> bool:
    """Return True if host or URL targets a non-loopback private LAN IPv4 address."""
    raw = str(host_or_url or "").strip()
    if not raw:
        return False
    host = raw
    if "://" in raw:
        host = urlsplit(raw).hostname or ""
    try:
        ip_obj = ipaddress.ip_address(host)
        return bool(ip_obj.is_private and not ip_obj.is_loopback and not ip_obj.is_link_local)
    except ValueError:
        return False


def extract_tuya_device_id(*values: Any) -> str:
    """Extract a 20-24 char Tuya device ID from unique_ids, identifiers, or strings."""
    for val in values:
        if val is None:
            continue
        if isinstance(val, (list, tuple, set)):
            found = extract_tuya_device_id(*val)
            if found:
                return found
            continue
        if isinstance(val, dict):
            found = extract_tuya_device_id(*val.values())
            if found:
                return found
            continue
        match = _TUYA_DEVID_RE.search(str(val).lower())
        if match:
            return match.group(1)
    return ""


def _read_local_arp_cache_sync() -> dict[str, dict[str, str]]:
    """Read local Linux ARP table (/proc/net/arp) in executor."""
    caches: dict[str, dict[str, str]] = {
        "arp_mac_to_ip": {},
        "arp_ip_to_mac": {},
    }

    if os.path.isfile("/proc/net/arp"):
        try:
            with open("/proc/net/arp", "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()[1:]
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    ip_addr = parts[0].strip()
                    mac_addr = _normalize_mac(parts[3])
                    if mac_addr and mac_addr != "00:00:00:00:00:00" and is_private_lan_ip(ip_addr):
                        caches["arp_mac_to_ip"][mac_addr] = ip_addr
                        caches["arp_ip_to_mac"][ip_addr] = mac_addr
        except Exception:
            pass

    return caches


class HaProxyDriver(BaseCameraDriver):
    """Hybrid driver for cameras integrated in Home Assistant (Tuya, Reolink, Ezviz, Blink, Xiaomi, ONVIF).

    Prioritizes low-latency direct local LAN RTSP/FLV streaming whenever a local IP and port
    can be resolved, and automatically falls back to Tuya OEM / Cloud stream_source() and
    Home Assistant HLS or snapshot polling.
    """

    def __init__(
        self,
        camera_id: str,
        config: dict[str, Any],
        hass: Any = None,
        on_frame_callback: Callable[[bytes], None] | None = None,
    ) -> None:
        """Initialize HA hybrid proxy driver."""
        super().__init__(camera_id, config, on_frame_callback)
        self.hass = hass
        self.driver_type = str(config.get("driver") or DRIVER_HA_PROXY)
        self.entity_id = str(
            config.get("entity_id") or config.get("ha_entity_id") or config.get("host") or ""
        ).strip()
        self.tuya_device_id = str(config.get("tuya_device_id") or "").strip()
        self.tuya_oem_entity_id = str(config.get("tuya_oem_entity_id") or "").strip()
        self.local_ip = str(config.get("local_ip") or "").strip()
        self.mac_address = _normalize_mac(config.get("mac_address"))
        self.wifi_ssid = str(config.get("wifi_ssid") or "").strip()
        self.wifi_rssi = config.get("wifi_rssi")
        self.local_key = str(config.get("local_key") or "").strip()
        self.custom_rtsp_url = str(config.get("rtsp_url") or config.get("stream_url") or "").strip()
        self.username = str(config.get("username") or "").strip()
        self.password = str(config.get("password") or config.get("verification_code") or "").strip()
        self.brand = str(config.get("brand") or "").strip()
        self.model_id = str(config.get("model_id") or "").strip()
        self._resolved_platform = str(config.get("platform") or "").strip().lower()
        self._active_stream_mode: str = ""
        self._verified_local_port: int | None = None
        self._last_metadata_resolve: float = 0.0
        self.battery_protected_mode: bool = self._detect_battery_mode()
        self._stream_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None

    def _detect_battery_mode(self) -> bool:
        """Return True for battery/solar cameras to avoid aggressive background polling."""
        if self.driver_type == DRIVER_BLINK_HYBRID or self._resolved_platform == "blink":
            return True
        state = self.hass.states.get(self.entity_id) if self.hass and self.entity_id else None
        attrs = dict(state.attributes) if state and getattr(state, "attributes", None) else {}
        if attrs.get("battery_level") is not None:
            return True
        hint = f"{self.model_id} {self.config.get('name', '')} {attrs.get('model_name', '')}".lower()
        return any(k in hint for k in ("solar", "solaire", "battery", "batterie", "blink"))

    def _effective_brand(self) -> str:
        """Infer normalized camera brand profile from driver, platform, and metadata."""
        if self.driver_type == DRIVER_REOLINK_HYBRID:
            return "reolink"
        if self.driver_type == DRIVER_EZVIZ_HYBRID:
            return "ezviz"
        if self.driver_type == DRIVER_BLINK_HYBRID:
            return "blink"
        if self.driver_type == DRIVER_TUYA_HYBRID:
            return "tuya"
        plat = self._resolved_platform.lower()
        if plat in ("tuya", "domolink_tuya_oem", "localtuya", "tuya_local"):
            return "tuya"
        if plat in ("reolink", "ezviz", "blink"):
            return plat
        if "xiaomi" in plat:
            return "xiaomi"
        hint = f"{self.brand} {self.model_id} {self.entity_id}".lower()
        for key in ("reolink", "ezviz", "blink", "xiaomi", "tuya", "arlo", "onvif"):
            if key in hint:
                return key
        return plat or "generic"

    def _find_tuya_oem_coordinator_and_device(self) -> tuple[Any | None, str, dict[str, Any]]:
        """Look up matching device metadata inside installed domolink_tuya_oem integration."""
        if not self.hass or not isinstance(getattr(self.hass, "data", None), dict):
            return None, "", {}
        tuya_oem_entries = self.hass.data.get("domolink_tuya_oem")
        if not isinstance(tuya_oem_entries, dict):
            return None, "", {}

        state = self.hass.states.get(self.entity_id) if self.entity_id else None
        friendly = state.attributes.get("friendly_name", "") if state and getattr(state, "attributes", None) else ""
        target_labels = {
            lbl
            for lbl in (
                _normalize_label(self.config.get("name")),
                _normalize_label(friendly),
            )
            if lbl
        }

        for entry_val in tuya_oem_entries.values():
            if not isinstance(entry_val, dict):
                continue
            coord = entry_val.get("coordinator")
            if coord is None:
                continue

            devices = getattr(coord, "devices", {}) or {}
            overrides = getattr(coord, "overrides", {}) or {}
            local_devs = getattr(coord, "local_devices", {}) or {}

            matched_dev_id = ""
            if self.tuya_device_id and (
                self.tuya_device_id in devices
                or self.tuya_device_id in overrides
                or self.tuya_device_id in local_devs
            ):
                matched_dev_id = self.tuya_device_id

            if not matched_dev_id and isinstance(devices, dict):
                find_linked = getattr(coord, "find_linked_camera_entity", None)
                for dev_id, dev_obj in devices.items():
                    if callable(find_linked):
                        try:
                            if find_linked(dev_id) == self.entity_id:
                                matched_dev_id = str(dev_id)
                                break
                        except Exception:
                            pass
                    dev_name = (
                        dev_obj.get("name")
                        if isinstance(dev_obj, dict)
                        else getattr(dev_obj, "name", "")
                    )
                    ov = overrides.get(dev_id, {}) if isinstance(overrides, dict) else {}
                    ov_name = ov.get("custom_name", "") if isinstance(ov, dict) else ""
                    if _normalize_label(dev_name) in target_labels or _normalize_label(ov_name) in target_labels:
                        matched_dev_id = str(dev_id)
                        break

            if not matched_dev_id:
                continue

            dev_obj = devices.get(matched_dev_id) if isinstance(devices, dict) else None
            ov = overrides.get(matched_dev_id, {}) if isinstance(overrides, dict) else {}
            loc = local_devs.get(matched_dev_id, {}) if isinstance(local_devs, dict) else {}

            def _pick(obj: Any, *keys: str) -> Any:
                if isinstance(obj, dict):
                    for k in keys:
                        if obj.get(k) not in (None, ""):
                            return obj[k]
                elif obj is not None:
                    for k in keys:
                        val = getattr(obj, k, None)
                        if val not in (None, ""):
                            return val
                return None

            linked_eid = ""
            if callable(getattr(coord, "find_linked_camera_entity", None)):
                try:
                    linked_eid = str(coord.find_linked_camera_entity(matched_dev_id) or "")
                except Exception:
                    pass

            ip_cand = (
                _pick(ov, "local_ip", "ip")
                or _pick(loc, "local_ip", "ip")
                or _pick(dev_obj, "local_ip", "ip")
                or ""
            )
            mac_cand = _pick(ov, "mac", "mac_address") or _pick(loc, "mac") or _pick(dev_obj, "mac") or ""
            info = {
                "tuya_device_id": matched_dev_id,
                "tuya_oem_entity_id": linked_eid,
                "local_ip": str(ip_cand).strip() if is_private_lan_ip(str(ip_cand)) else "",
                "mac_address": _normalize_mac(mac_cand),
                "rtsp_url": str(_pick(ov, "rtsp_url", "stream_url") or _pick(dev_obj, "rtsp_url") or "").strip(),
                "local_key": str(_pick(dev_obj, "local_key") or "").strip(),
                "model_id": str(_pick(dev_obj, "product_name", "model", "category") or "").strip(),
            }
            return coord, matched_dev_id, info

        return None, "", {}

    async def async_resolve_hybrid_metadata(self, force: bool = False) -> dict[str, Any]:
        """Resolve local LAN IP, MAC, Tuya ID, platform, and OEM bindings safely."""
        now = time.time()
        if not force and self._last_metadata_resolve and (now - self._last_metadata_resolve < 30.0):
            return {
                "local_ip": self.local_ip,
                "mac_address": self.mac_address,
                "tuya_device_id": self.tuya_device_id,
                "tuya_oem_entity_id": self.tuya_oem_entity_id,
                "platform": self._resolved_platform,
            }

        self._last_metadata_resolve = now
        if not self.hass or not self.entity_id:
            return {}

        if not self.tuya_device_id:
            self.tuya_device_id = extract_tuya_device_id(self.entity_id, self.config.get("device_id"))

        # 1. HA State attributes
        state = self.hass.states.get(self.entity_id)
        attrs = dict(state.attributes) if state and getattr(state, "attributes", None) else {}
        if attrs.get("platform") and not self._resolved_platform:
            self._resolved_platform = str(attrs["platform"]).lower()
        for ip_key in ("local_ip", "ip_address", "lan_ip", "host"):
            cand = str(attrs.get(ip_key) or "").strip()
            if not self.local_ip and is_private_lan_ip(cand):
                self.local_ip = cand
        if not self.mac_address:
            self.mac_address = _normalize_mac(attrs.get("mac") or attrs.get("mac_address"))
        if not self.brand and (attrs.get("brand") or attrs.get("device_brand")):
            self.brand = str(attrs.get("brand") or attrs.get("device_brand"))
        if not self.model_id and (attrs.get("model_name") or attrs.get("model_id")):
            self.model_id = str(attrs.get("model_name") or attrs.get("model_id"))
        if not self.custom_rtsp_url and isinstance(attrs.get("rtsp_url"), str):
            self.custom_rtsp_url = attrs["rtsp_url"].strip()

        # 2. Entity & Device Registry
        ent_reg_obj = None
        ent_reg_entry = None
        try:
            from homeassistant.helpers import entity_registry as er
            er_inst = er.async_get(self.hass)
            if er_inst and hasattr(er_inst, "async_get"):
                ent_reg_obj = er_inst
                ent_reg_entry = er_inst.async_get(self.entity_id)
        except Exception:
            ent_reg_entry = None

        xiaomi_did = ""
        if ent_reg_entry is not None:
            plat = getattr(ent_reg_entry, "platform", None)
            if isinstance(plat, str) and plat:
                self._resolved_platform = plat.lower()
            uid = getattr(ent_reg_entry, "unique_id", None)
            if isinstance(uid, str) and uid:
                if not self.tuya_device_id:
                    self.tuya_device_id = extract_tuya_device_id(uid)
                if "xiaomi" in self._resolved_platform:
                    # xiaomi_miot unique_id often carries DID or MAC
                    mac_in_uid = _MAC_RE.search(uid)
                    if mac_in_uid and not self.mac_address:
                        self.mac_address = _normalize_mac(mac_in_uid.group(0))
                    did_m = re.search(r"\b(\d{7,15})\b", uid)
                    if did_m:
                        xiaomi_did = did_m.group(1)

            dev_id = getattr(ent_reg_entry, "device_id", None)
            if isinstance(dev_id, str) and dev_id:
                try:
                    dev_reg = None
                    if isinstance(getattr(self.hass, "data", None), dict):
                        dev_reg = self.hass.data.get("device_registry")
                    if dev_reg is None:
                        from homeassistant.helpers import device_registry as dr
                        dev_reg = dr.async_get(self.hass)
                    dev_entry = dev_reg.async_get(dev_id) if dev_reg and hasattr(dev_reg, "async_get") else None
                    if dev_entry is not None:
                        if not self.tuya_device_id:
                            self.tuya_device_id = extract_tuya_device_id(getattr(dev_entry, "identifiers", None))
                        for c_type, c_val in getattr(dev_entry, "connections", ()) or ():
                            if str(c_type).lower() == "mac" and not self.mac_address:
                                self.mac_address = _normalize_mac(c_val)
                        cfg_url = getattr(dev_entry, "configuration_url", None)
                        if isinstance(cfg_url, str) and not self.local_ip:
                            host_part = urlsplit(cfg_url).hostname or ""
                            if is_private_lan_ip(host_part):
                                self.local_ip = host_part
                        if not self.brand and isinstance(getattr(dev_entry, "manufacturer", None), str):
                            self.brand = dev_entry.manufacturer
                        if not self.model_id and isinstance(getattr(dev_entry, "model", None), str):
                            self.model_id = dev_entry.model
                except Exception:
                    pass

        if self.tuya_device_id and isinstance(getattr(ent_reg_obj, "entities", None), Mapping):
            for reg_eid, reg_item in ent_reg_obj.entities.items():
                if getattr(reg_item, "platform", "") != "domolink_tuya_oem":
                    continue
                dis = getattr(reg_item, "disabled_by", None)
                if isinstance(dis, str) or (dis is not None and "Disabler" in type(dis).__name__):
                    continue
                uid_str = str(getattr(reg_item, "unique_id", "") or "")
                if self.tuya_device_id not in uid_str:
                    continue
                cand_eid = (
                    reg_eid
                    if isinstance(reg_eid, str) and reg_eid.startswith("camera.")
                    else str(getattr(reg_item, "entity_id", "") or "")
                )
                if cand_eid.startswith("camera."):
                    self.tuya_oem_entity_id = cand_eid
                    break

        # 3. Installed domolink_tuya_oem coordinator bridge
        _, matched_dev_id, oem_info = self._find_tuya_oem_coordinator_and_device()
        if matched_dev_id:
            if not self.tuya_device_id:
                self.tuya_device_id = matched_dev_id
            if oem_info.get("tuya_oem_entity_id") and not self.tuya_oem_entity_id:
                self.tuya_oem_entity_id = oem_info["tuya_oem_entity_id"]
            if oem_info.get("local_ip") and not self.local_ip:
                self.local_ip = oem_info["local_ip"]
            if oem_info.get("mac_address") and not self.mac_address:
                self.mac_address = oem_info["mac_address"]
            if oem_info.get("rtsp_url") and not self.custom_rtsp_url:
                self.custom_rtsp_url = oem_info["rtsp_url"]
            if oem_info.get("local_key") and not self.local_key:
                self.local_key = oem_info["local_key"]
            if oem_info.get("model_id") and not self.model_id:
                self.model_id = oem_info["model_id"]

        # 4. Executor local storage & ARP resolution (.storage caches & /proc/net/arp)
        cfg_dir = ""
        if callable(getattr(self.hass, "async_add_executor_job", None)) and (
            (self.mac_address and not self.local_ip) or (self.local_ip and not self.mac_address)
        ):
            try:
                caches = await self.hass.async_add_executor_job(_read_local_arp_cache_sync)
                if self.mac_address and not self.local_ip:
                    arp_ip = caches.get("arp_mac_to_ip", {}).get(self.mac_address)
                    if arp_ip:
                        self.local_ip = arp_ip
                if self.local_ip and not self.mac_address:
                    arp_mac = caches.get("arp_ip_to_mac", {}).get(self.local_ip)
                    if arp_mac:
                        self.mac_address = arp_mac
            except Exception as err:
                _LOGGER.debug("[%s] Local ARP lookup failed: %s", self.entity_id, err)

        # Persist enriched fields onto config dict so UI and WS expose them
        for field_name, val in (
            ("local_ip", self.local_ip),
            ("mac_address", self.mac_address),
            ("tuya_device_id", self.tuya_device_id),
            ("tuya_oem_entity_id", self.tuya_oem_entity_id),
            ("brand", self.brand),
            ("model_id", self.model_id),
        ):
            if val and not self.config.get(field_name):
                self.config[field_name] = val

        self.battery_protected_mode = self._detect_battery_mode()
        return {
            "local_ip": self.local_ip,
            "mac_address": self.mac_address,
            "tuya_device_id": self.tuya_device_id,
            "tuya_oem_entity_id": self.tuya_oem_entity_id,
            "platform": self._resolved_platform,
        }

    def _build_rtsp_auth(self, default_user: str = "") -> str:
        """Build URL-escaped user:pass@ prefix for LAN RTSP endpoints when credentials exist."""
        user = self.username or default_user
        pwd = self.password
        if user and pwd:
            return f"{quote(user, safe='')}:{quote(pwd, safe='')}@"
        if user and self.username:
            return f"{quote(user, safe='')}@"
        return ""

    async def _build_local_rtsp_candidates(self) -> list[dict[str, str]]:
        """Probe standard RTSP ports on resolved LAN IP and return brand-specific direct URLs."""
        if not self.local_ip or not is_private_lan_ip(self.local_ip):
            return []

        brand = self._effective_brand()
        if brand == "blink":
            # Blink routes video through Sync Module / Blink Cloud only
            return []

        p554, p8554 = await asyncio.gather(
            self.async_probe_tcp_port(self.local_ip, 554, timeout=0.65),
            self.async_probe_tcp_port(self.local_ip, 8554, timeout=0.65),
        )
        candidates: list[dict[str, str]] = []
        auth = self._build_rtsp_auth()

        if brand == "reolink" and p554:
            self._verified_local_port = 554
            for path in ("/h264Preview_01_sub", "/h264Preview_01_main", "/Preview_01_sub"):
                candidates.append({
                    "url": f"rtsp://{auth}{self.local_ip}:554{path}",
                    "mode": "local_lan",
                    "source": "reolink_rtsp_lan",
                })
        elif brand == "ezviz" and p554:
            self._verified_local_port = 554
            ez_auth = self._build_rtsp_auth(default_user="admin" if self.password else "")
            for path in ("/h264/ch1/sub/av_stream", "/h264/ch1/main/av_stream"):
                candidates.append({
                    "url": f"rtsp://{ez_auth}{self.local_ip}:554{path}",
                    "mode": "local_lan",
                    "source": "ezviz_rtsp_lan",
                })
        else:
            if p554:
                self._verified_local_port = 554
                for path in ("/live/ch00_1", "/live/ch00_0", "/stream1", "/h264Preview_01_sub", "/h264"):
                    candidates.append({
                        "url": f"rtsp://{auth}{self.local_ip}:554{path}",
                        "mode": "local_lan",
                        "source": f"{brand}_rtsp_lan",
                    })
            if p8554:
                self._verified_local_port = self._verified_local_port or 8554
                for path in ("/unicast", "/live", "/stream1"):
                    candidates.append({
                        "url": f"rtsp://{auth}{self.local_ip}:8554{path}",
                        "mode": "local_lan",
                        "source": f"{brand}_rtsp8554_lan",
                    })

        return candidates

    async def async_get_hybrid_stream_candidates(self) -> list[dict[str, str]]:
        """Build Option 2 ordered stream candidates: Local LAN -> Cloud Direct -> HA HLS."""
        await self.async_resolve_hybrid_metadata()

        lan_candidates: list[dict[str, str]] = []
        cloud_candidates: list[dict[str, str]] = []
        ha_candidates: list[dict[str, str]] = []

        # 1. Explicit custom/override RTSP/FLV URL first
        if self.custom_rtsp_url and self.custom_rtsp_url.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
            target = lan_candidates if is_private_lan_ip(self.custom_rtsp_url) else cloud_candidates
            target.append({
                "url": self.custom_rtsp_url,
                "mode": "local_lan" if is_private_lan_ip(self.custom_rtsp_url) else "cloud_hybrid",
                "source": "custom_override_url",
            })

        # 2. Local LAN RTSP probing (before cloud fallbacks)
        lan_candidates.extend(await self._build_local_rtsp_candidates())

        # 3. Native HA entity stream_source() (wakes cloud cams or exposes LAN RTSP/FLV directly)
        entity = self._get_ha_camera_entity()
        if entity and hasattr(entity, "stream_source"):
            try:
                src = await entity.stream_source()
                if src and str(src).lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
                    src_str = str(src)
                    if is_private_lan_ip(src_str):
                        lan_candidates.append({
                            "url": src_str,
                            "mode": "local_lan",
                            "source": "ha_entity_stream_source",
                        })
                    else:
                        cloud_candidates.append({
                            "url": src_str,
                            "mode": "cloud_hybrid",
                            "source": "ha_entity_stream_source",
                        })
            except asyncio.CancelledError:
                raise
            except Exception as err:
                _LOGGER.debug("[%s] HA stream_source lookup error: %s", self.entity_id, err)

        # 4. domolink_tuya_oem Cloud Bridge (secondary cloud source for Tuya cameras)
        if self.tuya_device_id:
            coord, matched_id, _ = self._find_tuya_oem_coordinator_and_device()
            if coord is not None and hasattr(coord, "async_get_camera_stream"):
                try:
                    oem_url = await coord.async_get_camera_stream(matched_id or self.tuya_device_id)
                    if oem_url and str(oem_url).lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
                        oem_str = str(oem_url)
                        target = lan_candidates if is_private_lan_ip(oem_str) else cloud_candidates
                        target.append({
                            "url": oem_str,
                            "mode": "local_lan" if is_private_lan_ip(oem_str) else "cloud_hybrid",
                            "source": "domolink_tuya_oem_bridge",
                        })
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    _LOGGER.debug("[%s] domolink_tuya_oem stream bridge error: %s", self.entity_id, err)

        # 5. Pre-fetched HA HLS URL if already requested
        if self._stream_url:
            hls_full = self._resolve_local_ha_url(self._stream_url)
            if hls_full.lower().startswith(("http://", "https://", "rtsp://", "rtsps://")):
                ha_candidates.append({
                    "url": hls_full,
                    "mode": "ha_hybrid",
                    "source": "ha_hls_proxy",
                })

        # Deduplicate preserving Option 2 priority (LAN > Cloud Direct > HA HLS)
        seen: set[str] = set()
        ordered: list[dict[str, str]] = []
        for cand in (*lan_candidates, *cloud_candidates, *ha_candidates):
            u = cand["url"]
            if u not in seen:
                seen.add(u)
                ordered.append(cand)
        return ordered

    def _get_ha_camera_entity(self) -> Any | None:
        """Look up underlying Home Assistant Camera entity instance if available."""
        if not self.hass or not self.entity_id:
            return None
        try:
            cam_comp = self.hass.data.get("camera")
            if cam_comp and hasattr(cam_comp, "get_entity"):
                return cam_comp.get_entity(self.entity_id)
            if cam_comp and hasattr(cam_comp, "entities"):
                for ent in cam_comp.entities:
                    if getattr(ent, "entity_id", None) == self.entity_id:
                        return ent
        except Exception:
            pass
        return None

    async def _periodic_snapshot_poll(self) -> None:
        """Periodically refresh snapshot thumbnail in background (battery-safe interval)."""
        while True:
            try:
                interval = 60 if self.battery_protected_mode else 15
                await asyncio.sleep(interval)
                if not self.is_streaming:
                    await self.async_get_snapshot()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("[%s] Periodic snapshot poll error: %s", self.entity_id, err)

    def _resolve_local_ha_url(self, path_or_url: str) -> str:
        """Resolve a relative Home Assistant API path (e.g. /api/hls/...) to a full local URL."""
        raw = str(path_or_url or "")
        if not raw or raw.startswith(("http://", "https://", "rtsp://", "rtsps://")):
            return raw
        base = "http://127.0.0.1:8123"
        try:
            from homeassistant.helpers.network import get_url
            detected = get_url(self.hass, allow_internal=True, prefer_external=False)
            if detected and detected.startswith(("http://", "https://")):
                base = detected.rstrip("/")
        except Exception:
            pass
        return f"{base}{raw}" if raw.startswith("/") else f"{base}/{raw}"

    async def _request_ha_hls_stream(self) -> str | None:
        """Lazily ask Home Assistant camera component to prepare an HLS fallback stream."""
        if not self.hass or not self.entity_id:
            return None
        try:
            from homeassistant.components.camera import async_request_stream
            url = await async_request_stream(self.hass, self.entity_id, fmt="hls")
            if url:
                self._stream_url = url
                return str(url)
        except Exception as err:
            _LOGGER.debug("[%s] Stream request to HA failed: %s", self.entity_id, err)
        return None

    async def _live_feed_loop(self) -> None:
        """Stream prioritizing direct Local LAN RTSP/FLV, then Cloud direct, then HA HLS and snapshot poll."""
        has_ffmpeg = await async_has_ffmpeg(self.hass)

        if has_ffmpeg:
            candidates = await self.async_get_hybrid_stream_candidates()
            for cand in candidates:
                if not self.is_streaming:
                    return
                try:
                    self._active_stream_mode = cand["mode"]
                    _LOGGER.info(
                        "[%s] Trying %s stream (%s)",
                        self.entity_id,
                        cand["mode"],
                        cand["source"],
                    )
                    ok = await self.async_stream_ffmpeg_mjpeg(cand["url"])
                    if ok or not self.is_streaming:
                        return
                except asyncio.CancelledError:
                    raise
                except Exception as err:
                    _LOGGER.debug("[%s] Hybrid candidate (%s) failed: %s", self.entity_id, cand["source"], err)

            # Lazy HA HLS fallback when no direct LAN/Cloud candidate worked
            if self.is_streaming and not self._stream_url:
                hls_rel = await self._request_ha_hls_stream()
                if hls_rel and self.is_streaming:
                    try:
                        self._active_stream_mode = "ha_hybrid"
                        hls_full = self._resolve_local_ha_url(hls_rel)
                        ok = await self.async_stream_ffmpeg_mjpeg(hls_full)
                        if ok or not self.is_streaming:
                            return
                    except asyncio.CancelledError:
                        raise
                    except Exception as err:
                        _LOGGER.debug("[%s] Lazy HA HLS FFmpeg error: %s", self.entity_id, err)

        self._active_stream_mode = "snapshot_poll"
        poll_sleep = 1.5 if self.battery_protected_mode else 0.35
        while self.is_streaming:
            try:
                snap = await self.async_get_snapshot()
                if snap:
                    self.notify_frame(snap)
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("[%s] Error in live stream loop: %s", self.entity_id, err)
            await asyncio.sleep(poll_sleep)

    async def async_connect(self) -> bool:
        """Verify camera entity exists, resolve local hybrid metadata, and fetch initial snapshot."""
        self.status = STATUS_CONNECTING
        if not self.hass or not self.entity_id:
            self.status = STATUS_OFFLINE
            return False

        await self.async_resolve_hybrid_metadata()

        state = self.hass.states.get(self.entity_id)
        if not state or state.state == "unavailable":
            self.is_connected = False
            self.status = STATUS_OFFLINE
            return False

        # Try fetching a first snapshot
        await self.async_get_snapshot()
        self.is_connected = True
        self.status = STATUS_ONLINE

        if not self._poll_task or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._periodic_snapshot_poll())
        return True

    async def async_disconnect(self) -> None:
        """Disconnect driver and cancel background tasks."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            self._poll_task = None
        await self.async_stop_stream()
        self.is_connected = False
        self.status = STATUS_OFFLINE

    async def _fetch_http_url(self, url: str) -> bytes | None:
        """Download image bytes using HA shared aiohttp session with safe fallback."""
        timeout = aiohttp.ClientTimeout(total=6.0)
        try:
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            session = async_get_clientsession(self.hass)
            if hasattr(session, "get"):
                async with session.get(url, timeout=timeout) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception:
            pass

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.read()
        except Exception:
            pass
        return None

    async def async_get_snapshot(self) -> bytes | None:
        """Fetch snapshot directly from Home Assistant camera component with multi-level fallback."""
        if not self.hass or not self.entity_id:
            return self.last_snapshot

        if not self.is_streaming and self.last_snapshot and self.last_snapshot_time and (time.time() - self.last_snapshot_time < 1.5):
            return self.last_snapshot

        # 1. Primary method: async_get_image from camera component
        try:
            from homeassistant.components.camera import async_get_image
            image = await async_get_image(self.hass, self.entity_id, timeout=6.0)
            if image and getattr(image, "content", None):
                self.last_snapshot = image.content
                self.last_snapshot_time = time.time()
                self.is_connected = True
                self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                return image.content
        except Exception as err:
            _LOGGER.debug("[%s] async_get_image failed: %s", self.entity_id, err)

        # 2. Secondary fallback: direct entity async_camera_image()
        try:
            entity = self._get_ha_camera_entity()
            if entity and hasattr(entity, "async_camera_image"):
                data = await entity.async_camera_image()
                if data and len(data) > 100:
                    self.last_snapshot = data
                    self.last_snapshot_time = time.time()
                    self.is_connected = True
                    self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                    return data
        except Exception as err:
            _LOGGER.debug("[%s] entity.async_camera_image failed: %s", self.entity_id, err)

        # 3. Tertiary fallback: entity attributes (aarlo / Arlo / cloud thumbnails)
        try:
            state = self.hass.states.get(self.entity_id)
            if state and state.attributes:
                for attr_key in (
                    "presignedFullFrameSnapshotUrl",
                    "presignedLastImageUrl",
                    "last_thumbnail",
                    "entity_picture",
                ):
                    thumb_val = state.attributes.get(attr_key)
                    if not thumb_val:
                        continue
                    thumb_url = self._resolve_local_ha_url(str(thumb_val))
                    if not thumb_url.startswith(("http://", "https://")):
                        continue
                    data = await self._fetch_http_url(thumb_url)
                    if data and len(data) > 100:
                        self.last_snapshot = data
                        self.last_snapshot_time = time.time()
                        self.is_connected = True
                        self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                        return data
        except Exception as err:
            _LOGGER.debug("[%s] Fallback to entity attributes failed: %s", self.entity_id, err)

        # 4. Quaternary fallback: linked domolink_tuya_oem entity / mobile cloud cover snapshot
        if self.tuya_oem_entity_id and self.tuya_oem_entity_id != self.entity_id:
            try:
                from homeassistant.components.camera import async_get_image
                image = await async_get_image(self.hass, self.tuya_oem_entity_id, timeout=6.0)
                if image and getattr(image, "content", None):
                    self.last_snapshot = image.content
                    self.last_snapshot_time = time.time()
                    self.is_connected = True
                    self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                    return image.content
            except Exception:
                pass

        if self.tuya_device_id:
            coord, matched_id, _ = self._find_tuya_oem_coordinator_and_device()
            mobile = getattr(coord, "mobile_client", None) if coord else None
            if mobile and hasattr(mobile, "get_camera_snapshot_url"):
                try:
                    snap_url = await mobile.get_camera_snapshot_url(matched_id or self.tuya_device_id)
                    if snap_url and str(snap_url).startswith(("http://", "https://")):
                        data = await self._fetch_http_url(str(snap_url))
                        if data and len(data) > 100:
                            self.last_snapshot = data
                            self.last_snapshot_time = time.time()
                            self.is_connected = True
                            self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                            return data
                except Exception as err:
                    _LOGGER.debug("[%s] Tuya OEM cloud snapshot fallback failed: %s", self.entity_id, err)

        # 5. Quinary fallback: direct LAN RTSP snapshot via FFmpeg (skipped on battery cameras)
        if not self.battery_protected_mode and self.custom_rtsp_url and await async_has_ffmpeg(self.hass):
            try:
                data = await self.async_capture_ffmpeg_snapshot(self.custom_rtsp_url)
                if data and len(data) > 100:
                    self.last_snapshot = data
                    self.last_snapshot_time = time.time()
                    self.is_connected = True
                    self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                    return data
            except Exception:
                pass

        return self.last_snapshot

    async def async_start_stream(self) -> None:
        """Start hybrid live stream prioritizing Local LAN over Cloud Direct and HA HLS."""
        self.is_streaming = True
        self.status = STATUS_STREAMING

        if not self.hass or not self.entity_id:
            return

        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()

        if self.is_streaming:
            self._stream_task = asyncio.create_task(self._live_feed_loop())

    async def async_stop_stream(self) -> None:
        """Stop streaming and clean up FFmpeg or polling task."""
        self.is_streaming = False
        self.status = STATUS_ONLINE if self.is_connected else STATUS_OFFLINE
        self._stream_url = None
        self.stop_ffmpeg_process()
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            self._stream_task = None

    def get_capabilities(self) -> dict[str, Any]:
        """Return capabilities for hybrid HA proxy camera (LAN IP, brand, battery, stream mode)."""
        state = self.hass.states.get(self.entity_id) if self.hass else None
        attrs = dict(state.attributes) if state and getattr(state, "attributes", None) else {}
        if self._active_stream_mode:
            stream_mode = self._active_stream_mode
        elif self.local_ip and (self._verified_local_port or is_private_lan_ip(self.custom_rtsp_url)):
            stream_mode = "local_lan_ready"
        elif self.local_ip:
            stream_mode = "local_ip_resolved"
        else:
            stream_mode = "cloud_or_ha_proxy"

        return {
            "night_vision": False,
            "ptz": False,
            "audio": bool(attrs.get("supported_features", 0) & 2),
            "reboot": False,
            "driver_type": self.driver_type,
            "ha_entity": self.entity_id,
            "entity_picture": attrs.get("entity_picture"),
            "brand": self.brand or attrs.get("brand") or attrs.get("device_brand") or self._effective_brand().capitalize(),
            "model": self.model_id or attrs.get("model_name") or attrs.get("model_id") or attrs.get("device_model") or "Caméra",
            "local_ip": self.local_ip,
            "mac_address": self.mac_address,
            "tuya_device_id": self.tuya_device_id,
            "tuya_oem_entity_id": self.tuya_oem_entity_id,
            "wifi_ssid": self.wifi_ssid,
            "wifi_rssi": self.wifi_rssi,
            "stream_mode": stream_mode,
            "battery_protected_mode": self.battery_protected_mode,
            "battery_level": attrs.get("battery_level"),
            "signal_strength": attrs.get("signal_strength"),
        }
