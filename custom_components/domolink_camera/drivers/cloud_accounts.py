"""Multi-brand Cloud & LAN Account Sessions for DomoLink Camera (Tuya OEM, Blink, Ezviz, Reolink)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import logging
import os
import re
import time
import uuid
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from ..const import (
    DRIVER_BLINK_HYBRID,
    DRIVER_EZVIZ_HYBRID,
    DRIVER_REOLINK_HYBRID,
    DRIVER_TUYA_HYBRID,
)
from .ha_proxy import _normalize_label, _normalize_mac, extract_tuya_device_id, is_private_lan_ip

_LOGGER = logging.getLogger(__name__)


def _d(s: str, k: int = 0x5A) -> str:
    """Deobfuscate embedded mobile app signature fields at runtime."""
    if not s:
        return ""
    return bytes([b ^ k for b in base64.b85decode(s.encode("ascii"))]).decode("utf-8")


# Verified mobile profiles extracted from official Tuya & OEM APKs
TUYA_OEM_PROFILES: dict[str, dict[str, Any]] = {
    "smartlife": {
        "name": "Smart Life (Officiel)",
        "package": _d("IW;$QE-xcHbSXDGC@wZLJU;"),
        "schema": _d("DK|SPE;chfKL"),
        "client_id": _d("KQT8nEh=L?Zz?o0X)Y)}E-F1E"),
        "secret": _d("C}}r8Z9OtKA}~KJC@eH8KQ}EmGA(I5A}%{QDl#KI"),
        "cert_sha256": _d("Y8)A9Y-?j<V;LE08EJ1A8)6$78*gnM8yjzLV`&>`Y8f1FZ*6F8ZE9#A8)9!89&H$DXlP<%Zetu`VqzR0"),
        "app_key": _d("Fg!hPC@F6-F*hhMZ#N=4GA}(WFF7bFEG=$nE^cBX"),
        "app_version": "7.10.0",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
    },
    "tuya": {
        "name": "Tuya Smart (Officiel)",
        "package": _d("IW;$QE-xcHbSXDGC@u"),
        "schema": _d("E-xcH2{$_^E&"),
        "client_id": _d("X*nVyE@?Y2V<Ks3BQ7i}X)<Fl"),
        "secret": _d("Z#_OPJ2WsZJZWMqBO);?GGc8xFfBYeD=;!FFfc1S"),
        "cert_sha256": _d("V`*q>V;mW1ZD}89XliO4ZW|sSA8#COYh!C38EkKC7#nCCXdZ1CXdE1G9%ybE9&c|MZWwH9Z*OX9YaecE"),
        "app_key": _d("JZUmMZ7M%5ZYpAFF+VpjK0I$ND=9l~E;}qJEN^XN"),
        "app_version": "7.8.6",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
    },
    "lsc": {
        "name": "Action LSC Smart Connect",
        "package": _d("IW;$QHYqtNH#;aUIW;siKRGTlH8gZ7H#;aU"),
        "schema": _d("HYqtNH#;aUIW;siKRGTlH8d$VJ18y"),
        "client_id": _d("J|iMOH!(djIbtq6Vr@TdX>KuZ"),
        "secret": _d("J!xV$FEB4MDk(Q_K0G%pGAcY{E-NuDZaX|8E-E`R"),
        "app_version": "3.1.1",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
    },
    "lidlhome": {
        "name": "Lidl Home (Silvercrest)",
        "package": _d("IW;$QHZwjpGBr0pbSXDGC@u"),
        "schema": _d("HZwjpGBr0pDK|SPE&"),
        "client_id": _d("DJ&u`EombwC@nBNJUeeZKQB8Y"),
        "secret": _d("JSjdoD>82)X*oS@HzPi7GCyuHDJd^MJ~t^bB57$O"),
        "cert_sha256": _d("ZEtR99Aao_8yFZHZyacEVr?5}Y;9_49vo;M8E9x5VrgP+Y;PWE9B*xGZfI+7Z)tCDZWteFA8TxBVsB}0"),
        "app_version": "3.1.1",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
    },
    "nedis": {
        "name": "Nedis SmartLife",
        "package": _d("IW;$QG(SEwDRe0}J18zTGdw>"),
        "schema": _d("G(SEwDJeHQC@wZLJU;"),
        "client_id": _d("E^RA4FElJHV`(BQKPo>yJ2E3}"),
        "secret": _d("JZ>~@Ff3^(E;KhgBW@@wZYn4&Z6h!}FF!J3DQ`Y6"),
        "app_version": "3.1.1",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
    },
    "calex": {
        "name": "Calex Smart",
        "package": _d("IW;$QIXgB#A}KdJC@yp<H#;aU"),
        "schema": _d("IXgB#A}KdJC@v{CJ18y"),
        "client_id": _d("Dlk1QFDf}PEj%}EEGr{4Ic{S="),
        "secret": _d("ZY?P(G$~^!FEA`EZZa%CC@3*4J2!74D?DvIJZ)`1"),
        "app_version": "3.1.1",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
    },
    "konyks": {
        "name": "Konyks",
        "package": _d("IW;$QF*P(JF)0"),
        "schema": _d("F*P(JF)0"),
        "client_id": _d("BReiGFfJ@SV>>i0IV&kYZ80fh"),
        "secret": _d("DljcAEMhAtDK|SgIWI9XVr?%YZYwKkFf24YDJ^0>"),
        "app_version": "3.1.1",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
    },
    "thanks": {
        "name": "Thank's (GiFi)",
        "package": _d("IW;$QE;2hbF)2GLDs(e7E&"),
        "schema": _d("E;2hbF)2GLDg"),
        "client_id": _d("EIT4AIU_wQGH!1$GA$@QD=Iy2"),
        "secret": _d("X>B8IH*G8~DK|83X(}>lB5fl%Ep9X-Fd{i9Z(?pe"),
        "cert_sha256": _d("9v^BPY#eB9Vq+U`7-}3F8y;_LV`3R%Vs335X&7u{XlZI<8yjkCY-1l{9&2J8Vrm;}A8l!392sk4Z)s_2"),
        "app_key": _d("X(MhoEN?0?A}A^%DKsNAZa-opKRrETZ8s@xX+0uo"),
        "app_version": "3.1.1",
        "mobile_endpoint": "https://a1.tuyaeu.com/api.json",
    },
}

PROVIDER_DRIVER_MAP: dict[str, str] = {
    "tuya_oem": DRIVER_TUYA_HYBRID,
    "blink": DRIVER_BLINK_HYBRID,
    "ezviz": DRIVER_EZVIZ_HYBRID,
    "reolink": DRIVER_REOLINK_HYBRID,
}

EZVIZ_REGIONS: dict[str, str] = {
    "eu": "https://apiieu.ezvizlife.com",
    "us": "https://apiius.ezvizlife.com",
    "global": "https://apiisgp.ezvizlife.com",
    "cn": "https://apii.ezvizlife.com",
}


def get_tuya_oem_brands_list() -> list[dict[str, str]]:
    """Return UI-friendly list of supported Tuya / OEM mobile applications."""
    return [
        {"key": k, "name": v["name"], "package": v["package"]}
        for k, v in TUYA_OEM_PROFILES.items()
    ]


def _read_ha_provider_entries_sync(config_dir: str) -> dict[str, Any]:
    """Read HA .storage/core.config_entries & Tuya OEM overrides in executor thread."""
    result: dict[str, Any] = {
        "entries": [],
        "tuya_overrides": {},
    }
    if not config_dir or not os.path.isdir(config_dir):
        return result

    ce_path = os.path.join(config_dir, ".storage", "core.config_entries")
    if os.path.isfile(ce_path):
        try:
            with open(ce_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            entries = raw.get("data", {}).get("entries", [])
            for item in entries:
                if not isinstance(item, dict):
                    continue
                if item.get("disabled_by"):
                    continue
                domain = str(item.get("domain") or "")
                if domain in ("domolink_tuya_oem", "tuya", "blink", "ezviz", "reolink"):
                    result["entries"].append({
                        "entry_id": item.get("entry_id", ""),
                        "domain": domain,
                        "title": item.get("title", ""),
                        "data": dict(item.get("data") or {}),
                    })
        except Exception as err:
            _LOGGER.debug("Could not read core.config_entries: %s", err)

    ov_path = os.path.join(config_dir, ".storage", "domolink_tuya_oem_overrides")
    if os.path.isfile(ov_path):
        try:
            with open(ov_path, "r", encoding="utf-8") as f:
                raw_ov = json.load(f)
            payload = raw_ov.get("data", raw_ov) if isinstance(raw_ov, dict) else {}
            if isinstance(payload, dict):
                entries = payload.get("overrides") if isinstance(payload.get("overrides"), dict) else payload
                for dev_id, info in entries.items():
                    if isinstance(info, dict):
                        ip_val = str(info.get("local_ip") or info.get("ip") or "").strip()
                        result["tuya_overrides"][str(dev_id)] = {
                            "local_ip": ip_val if is_private_lan_ip(ip_val) else "",
                            "rtsp_url": str(info.get("rtsp_url") or info.get("stream_url") or "").strip(),
                            "custom_name": str(info.get("custom_name") or "").strip(),
                        }
        except Exception:
            pass

    return result


class ProviderAccountSession:
    """Persistent Cloud/LAN account session for Tuya OEM, Blink, Ezviz, and Reolink."""

    def __init__(
        self,
        account_id: str,
        provider: str,
        name: str = "",
        username: str = "",
        password: str = "",
        brand: str = "smartlife",
        country_code: str = "33",
        host: str = "",
        port: int = 80,
        rtsp_port: int = 554,
        verification_code: str = "",
        region: str = "eu",
        token: str = "",
        refresh_token: str = "",
        uid: str = "",
        account_num_id: str = "",
        client_id: str = "",
        hardware_id: str = "",
        status: str = "disconnected",
        last_sync: float | None = None,
        last_error: str = "",
        devices: list[dict[str, Any]] | None = None,
        hass: Any = None,
    ) -> None:
        """Initialize a provider session."""
        self.account_id = account_id
        self.provider = str(provider).strip().lower()
        self.name = name.strip() if name else ""
        self.username = username.strip() if username else ""
        self.password = password or ""
        self.brand = (brand or "smartlife").strip().lower()
        self.country_code = (country_code or "33").strip()
        self.host = (host or "").strip()
        self.port = int(port or 80)
        self.rtsp_port = int(rtsp_port or 554)
        self.verification_code = (verification_code or "").strip()
        self.region = (region or "eu").strip()
        self.token = token or ""
        self.refresh_token = refresh_token or ""
        self.uid = str(uid or "").strip()
        self.account_num_id = str(account_num_id or "").strip()
        self.client_id = str(client_id or "").strip()
        self.hardware_id = str(hardware_id or "").strip() or f"DomoLink-{uuid.uuid5(uuid.NAMESPACE_DNS, account_id).hex[:12]}"
        self.status = status or ("connected" if token else "disconnected")
        self.last_sync = last_sync
        self.last_error = last_error or ""
        self.devices: list[dict[str, Any]] = list(devices or [])
        self.hass = hass
        self._own_session: aiohttp.ClientSession | None = None

    async def _get_http_session(self) -> aiohttp.ClientSession:
        """Return reusable aiohttp session, avoiding MagicMock clientsession in tests."""
        if self.hass is not None:
            try:
                from homeassistant.helpers.aiohttp_client import async_get_clientsession
                cand = async_get_clientsession(self.hass)
                if cand and callable(getattr(cand, "request", None)) and not type(cand).__name__.endswith("Mock"):
                    return cand
            except Exception:
                pass
        if self._own_session is None or self._own_session.closed:
            self._own_session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15.0))
        return self._own_session

    async def async_close(self) -> None:
        """Close owned aiohttp session if open."""
        if self._own_session and not self._own_session.closed:
            await self._own_session.close()
            self._own_session = None

    async def _http_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json_data: Any = None,
        form_data: dict[str, Any] | None = None,
        ssl: Any = None,
    ) -> tuple[int, Any]:
        """Perform HTTP request returning (status, parsed_json_or_text)."""
        sess = await self._get_http_session()
        async with sess.request(
            method,
            url,
            headers=headers,
            json=json_data,
            data=form_data,
            ssl=ssl,
        ) as resp:
            text = await resp.text()
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = text
            return resp.status, parsed

    def _find_matching_ha_entities_for_provider(self) -> list[dict[str, Any]]:
        """Inspect HA states & entity_registry for existing camera entities matching this provider."""
        if not self.hass or not hasattr(self.hass, "states"):
            return []

        found: list[dict[str, Any]] = []
        target_platforms = {
            "tuya_oem": ("domolink_tuya_oem", "tuya", "localtuya", "tuya_local"),
            "blink": ("blink",),
            "ezviz": ("ezviz",),
            "reolink": ("reolink",),
        }.get(self.provider, ())

        ent_reg = self.hass.data.get("entity_registry") if isinstance(getattr(self.hass, "data", None), dict) else None
        if ent_reg is None and hasattr(getattr(self.hass, "helpers", None), "entity_registry"):
            try:
                ent_reg = self.hass.helpers.entity_registry.async_get(self.hass)
            except Exception:
                ent_reg = None
        ent_map = getattr(ent_reg, "entities", {}) if ent_reg else {}
        if not isinstance(ent_map, dict) and not hasattr(ent_map, "get"):
            ent_map = {}

        seen_eids: set[str] = set()
        for state in self.hass.states.async_all():
            eid = str(getattr(state, "entity_id", ""))
            if not eid.startswith("camera."):
                continue
            attrs = dict(getattr(state, "attributes", {}) or {})
            if getattr(state, "state", "") == "unavailable" and bool(attrs.get("restored")):
                continue

            reg_e = ent_map.get(eid) if hasattr(ent_map, "get") else None
            if reg_e is None and ent_reg and hasattr(ent_reg, "async_get"):
                try:
                    reg_e = ent_reg.async_get(eid)
                except Exception:
                    reg_e = None
            plat = str(getattr(reg_e, "platform", "") or attrs.get("platform") or "").lower()
            if plat not in target_platforms:
                continue

            seen_eids.add(eid)
            uid = str(getattr(reg_e, "unique_id", "") or "")
            tuya_id = extract_tuya_device_id(uid, eid) if self.provider == "tuya_oem" else ""
            local_ip = ""
            for k in ("local_ip", "ip_address", "lan_ip", "host"):
                val = str(attrs.get(k) or "").strip()
                if is_private_lan_ip(val):
                    local_ip = val
                    break

            found.append({
                "device_id": tuya_id or uid or eid,
                "tuya_device_id": tuya_id,
                "name": str(attrs.get("friendly_name") or eid),
                "model_id": str(attrs.get("model_name") or attrs.get("brand") or self.provider.upper()),
                "local_ip": local_ip,
                "battery_level": attrs.get("battery_level"),
                "signal_strength": attrs.get("signal_strength"),
                "ha_entity_id": eid,
                "platform": plat,
                "online": getattr(state, "state", "") != "unavailable",
            })

        # Fallback: include entity_registry cameras that have no runtime state yet (e.g. dormant Blink)
        if hasattr(ent_map, "values"):
            for reg_e in ent_map.values():
                eid = str(getattr(reg_e, "entity_id", "") or "")
                if not eid.startswith("camera.") or eid in seen_eids:
                    continue
                if getattr(reg_e, "disabled_by", None) is not None:
                    continue
                plat = str(getattr(reg_e, "platform", "") or "").lower()
                if plat not in target_platforms:
                    continue
                uid = str(getattr(reg_e, "unique_id", "") or "")
                tuya_id = extract_tuya_device_id(uid, eid) if self.provider == "tuya_oem" else ""
                reg_name = str(getattr(reg_e, "name", "") or getattr(reg_e, "original_name", "") or eid)
                found.append({
                    "device_id": tuya_id or uid or eid,
                    "tuya_device_id": tuya_id,
                    "name": reg_name,
                    "model_id": self.provider.upper(),
                    "local_ip": "",
                    "ha_entity_id": eid,
                    "platform": plat,
                    "online": False,
                })

        return found

    def _merge_ha_entities_into_devices(self, devs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Attach matching HA camera entities (ha_entity_id) and append unmatched HA cameras."""
        ha_cams = self._find_matching_ha_entities_for_provider()
        if not ha_cams:
            return devs

        merged = list(devs)
        for hcam in ha_cams:
            htuya = hcam.get("tuya_device_id", "")
            hlabel = _normalize_label(hcam.get("name"))
            h_uid_head = str(hcam.get("device_id") or "").split("-")[0]

            matched = False
            for d in merged:
                if htuya and d.get("tuya_device_id") == htuya:
                    matched = True
                elif h_uid_head and len(h_uid_head) >= 4 and (
                    h_uid_head == str(d.get("device_id") or "")
                    or h_uid_head in str(d.get("serial") or "")
                ):
                    matched = True
                elif hlabel and hlabel == _normalize_label(d.get("name")):
                    matched = True

                if matched:
                    if hcam.get("platform") == "domolink_tuya_oem":
                        d["tuya_oem_entity_id"] = hcam["ha_entity_id"]
                        if not d.get("ha_entity_id"):
                            d["ha_entity_id"] = hcam["ha_entity_id"]
                    elif not d.get("ha_entity_id"):
                        d["ha_entity_id"] = hcam["ha_entity_id"]
                    if hcam.get("local_ip") and not d.get("local_ip"):
                        d["local_ip"] = hcam["local_ip"]
                    break

            if not matched:
                if hcam.get("platform") == "domolink_tuya_oem":
                    hcam["tuya_oem_entity_id"] = hcam["ha_entity_id"]
                merged.append(hcam)

        return merged

    async def async_start_login(self) -> dict[str, Any]:
        """Authenticate against provider Cloud API or local CGI endpoint."""
        if self.provider == "tuya_oem":
            return await self._login_tuya_oem()
        if self.provider == "blink":
            return await self._login_blink()
        if self.provider == "ezviz":
            return await self._login_ezviz()
        if self.provider == "reolink":
            return await self._login_reolink()
        return {"status": "error", "error": f"Fournisseur non supporté : {self.provider}"}

    async def async_verify_2fa(self, otp_code: str) -> dict[str, Any]:
        """Verify 2FA PIN/OTP code for Blink or Ezviz."""
        code = (otp_code or "").strip()
        if not code:
            return {"status": "error", "error": "Code 2FA requis."}
        if self.provider == "blink":
            return await self._verify_blink_2fa(code)
        if self.provider == "ezviz":
            return await self._login_ezviz(sms_code=code)
        return {"status": "error", "error": f"Validation 2FA non requise pour {self.provider}"}

    async def async_fetch_devices(self) -> list[dict[str, Any]]:
        """Refresh camera devices from active provider session and matching HA entities."""
        if self.provider == "tuya_oem":
            devs = await self._fetch_tuya_oem_devices()
        elif self.provider == "blink":
            devs = await self._fetch_blink_devices()
        elif self.provider == "ezviz":
            devs = await self._fetch_ezviz_devices()
        elif self.provider == "reolink":
            devs = await self._fetch_reolink_devices()
        else:
            devs = []

        self.devices = self._merge_ha_entities_into_devices(devs)
        self.last_sync = time.time()
        return self.devices

    # --- 1. Tuya & Tuya OEM ---

    def _find_installed_tuya_oem_coordinator(self) -> Any | None:
        """Locate an active DomoLink Tuya OEM coordinator when available in HA."""
        if not self.hass or not isinstance(getattr(self.hass, "data", None), dict):
            return None
        oem_data = self.hass.data.get("domolink_tuya_oem")
        if not isinstance(oem_data, dict):
            return None
        for entry_val in oem_data.values():
            if not isinstance(entry_val, dict):
                continue
            coord = entry_val.get("coordinator")
            if coord is None:
                continue
            if not self.username:
                return coord
            mc = getattr(coord, "mobile_client", None)
            mc_user = str(getattr(mc, "username", "") or "").strip().lower()
            mc_brand = str(getattr(mc, "brand_key", "") or "").strip().lower()
            if (mc_user and mc_user == self.username.lower()) or (not mc_user and (not self.brand or mc_brand == self.brand)):
                return coord
        # Return first loaded coordinator if username/brand not strictly matched
        for entry_val in oem_data.values():
            if isinstance(entry_val, dict) and entry_val.get("coordinator") is not None:
                return entry_val["coordinator"]
        return None

    async def _login_tuya_oem(self) -> dict[str, Any]:
        """Connect via installed DomoLink Tuya OEM coordinator or tuya_mobile."""
        coord = self._find_installed_tuya_oem_coordinator()
        if coord is not None and not self.password:
            self.status = "connected"
            self.last_error = ""
            await self.async_fetch_devices()
            return {"status": "connected", "devices": self.devices}

        try:
            from tuya_mobile import TuyaMobileApp, TuyaMobileAppProfile, TuyaPasswordClient
        except ImportError:
            if coord is not None:
                self.status = "connected"
                self.last_error = ""
                await self.async_fetch_devices()
                return {"status": "connected", "devices": self.devices}
            self.last_error = "Le module tuya_mobile / DomoLink Tuya OEM est requis pour une connexion directe."
            self.status = "disconnected"
            return {"status": "error", "error": self.last_error}

        if not self.username or not self.password:
            return {"status": "error", "error": "E-mail et mot de passe Tuya/OEM requis."}

        prof_data = TUYA_OEM_PROFILES.get(self.brand, TUYA_OEM_PROFILES["smartlife"])
        sess = await self._get_http_session()

        if self.brand == "tuya":
            client = TuyaPasswordClient.for_application(
                TuyaMobileApp.TUYA_SMART,
                sess,
                username=self.username,
                endpoint="https://a1.tuyaeu.com/api.json",
            )
        elif self.brand == "smartlife":
            client = TuyaPasswordClient.for_application(
                TuyaMobileApp.SMART_LIFE,
                sess,
                username=self.username,
                endpoint="https://a1.tuyaeu.com/api.json",
            )
        else:
            custom_prof = TuyaMobileAppProfile(
                name=prof_data["name"],
                app_id=prof_data["client_id"],
                app_secret=prof_data["secret"],
                cert_sha256_hex=prof_data.get(
                    "cert_sha256",
                    "0FC361999CC0C35BA8ACA57DAA5593A20CF55727702EA85AD7B3228949F888FE",
                ),
                app_key=prof_data.get("app_key", prof_data["client_id"]),
                package=prof_data["package"],
                app_version=prof_data.get("app_version", "3.1.1"),
                ttid=f"sdk_international@{prof_data['client_id']}",
                sdk_version="5.24.0",
                device_core_version="5.17.0",
                os_system="14",
                platform="Android",
                channel="sdk",
                endpoints=(
                    "https://a1.tuyaeu.com/api.json",
                    "https://a1.tuyaus.com/api.json",
                    "https://a1-sg.iotbing.com/api.json",
                    "https://a1.tuyacn.com/api.json",
                ),
            )
            client = TuyaPasswordClient(
                custom_prof,
                sess,
                username=self.username,
                endpoint=prof_data.get("mobile_endpoint", "https://a1.tuyaeu.com/api.json"),
            )

        try:
            mobile_sess = await client.login_with_password(self.password, self.country_code)
            self.token = str(getattr(mobile_sess, "sid", "") or "mobile_ok")
            self.uid = str(getattr(mobile_sess, "uid", "") or "")
            self.host = str(getattr(mobile_sess, "endpoint", "") or prof_data["mobile_endpoint"])
            self.status = "connected"
            self.last_error = ""
            devs = await self._fetch_tuya_mobile_devices_from_client(client)
            self.devices = self._merge_ha_entities_into_devices(devs)
            self.last_sync = time.time()
            return {"status": "connected", "devices": self.devices}
        except Exception as err:
            self.last_error = str(err)
            self.status = "error"
            return {"status": "error", "error": f"Connexion {prof_data['name']} refusée : {err}"}

    async def _fetch_tuya_mobile_devices_from_client(self, client: Any) -> list[dict[str, Any]]:
        """Extract cameras only from an authenticated tuya_mobile client."""
        cams: list[dict[str, Any]] = []
        try:
            records = await client.get_local_keys([])
        except Exception:
            records = []

        # Also query full device payloads where category ("sp" = smart camera) is returned
        try:
            from tuya_mobile.password_client import _walk
            gids: set[Any] = set()
            for home_api in ("m.life.home.space.list", "tuya.m.home.space.list", "m.life.home.list"):
                try:
                    homes = await client._call(home_api, {})
                    for o in _walk(homes):
                        gid_val = o.get("gid") or o.get("groupId") or o.get("homeId")
                        if gid_val:
                            gids.add(gid_val)
                    if gids:
                        break
                except Exception:
                    continue
            if not gids:
                gids = {0}
            seen: dict[str, dict[str, Any]] = {}
            dev_apis = (
                ("m.life.my.group.device.list", "2.2"),
                ("m.life.my.group.device.list", "2.0"),
                ("thing.m.my.group.device.list", "1.0"),
                ("tuya.m.my.group.device.list", "1.0"),
            )
            for gid in gids:
                resp = None
                for api_name, ver in dev_apis:
                    try:
                        resp = await client._call(api_name, {"gid": gid} if gid else {}, version=ver)
                        if resp:
                            break
                    except Exception:
                        continue
                if not resp:
                    continue
                for obj in _walk(resp):
                    did = obj.get("devId") or obj.get("deviceId")
                    if not did or did in seen:
                        continue
                    p_bean = obj.get("productBean") or {}
                    cat = str(obj.get("category") or p_bean.get("category") or "").lower()
                    pname = str(obj.get("productName") or p_bean.get("name") or "")
                    if cat in ("sp", "ipc", "camera") or "cam" in pname.lower() or "115" in (obj.get("dps") or {}):
                        raw_lan = obj.get("lanIp") or obj.get("localIp") or obj.get("ip")
                        seen[did] = {
                            "device_id": did,
                            "tuya_device_id": did,
                            "name": str(obj.get("name") or obj.get("devName") or pname or f"Caméra {did[:6]}"),
                            "model_id": pname or "Caméra Tuya OEM",
                            "local_ip": str(raw_lan) if is_private_lan_ip(str(raw_lan or "")) else "",
                            "mac_address": _normalize_mac(obj.get("mac") or obj.get("macAddress")),
                            "local_key": str(obj.get("localKey") or obj.get("local_key") or ""),
                            "online": bool(obj.get("isOnline", True)),
                        }
            for rec in records:
                did = rec.get("device_id")
                if did and did in seen:
                    if not seen[did]["local_ip"] and is_private_lan_ip(str(rec.get("ip") or "")):
                        seen[did]["local_ip"] = str(rec["ip"])
                    if not seen[did]["local_key"] and rec.get("local_key"):
                        seen[did]["local_key"] = str(rec["local_key"])
            cams = list(seen.values())
        except Exception as err:
            _LOGGER.debug("Tuya mobile camera enumeration fallback: %s", err)
        return cams

    async def _fetch_tuya_oem_devices(self) -> list[dict[str, Any]]:
        """Collect camera devices from installed domolink_tuya_oem coordinator or login."""
        coord = self._find_installed_tuya_oem_coordinator()
        if coord is None:
            if self.password:
                res = await self._login_tuya_oem()
                return res.get("devices", []) if isinstance(res, dict) else []
            return list(self.devices)

        devs: list[dict[str, Any]] = []
        raw_devices = getattr(coord, "data", None) or getattr(coord, "devices", {}) or {}
        overrides = getattr(coord, "overrides", {}) or {}
        local_devs = getattr(coord, "local_devices", {}) or {}

        for did, obj in raw_devices.items():
            did_str = str(did)
            cat = str(obj.get("category") if isinstance(obj, dict) else getattr(obj, "category", "") or "").lower()
            pname = str(obj.get("product_name") if isinstance(obj, dict) else getattr(obj, "product_name", "") or "")
            name = str(obj.get("name") if isinstance(obj, dict) else getattr(obj, "name", "") or f"Caméra {did_str[:6]}")
            dps = (obj.get("dps") if isinstance(obj, dict) else getattr(obj, "dps", {})) or {}

            is_cam = cat in ("sp", "ipc", "camera") or "cam" in pname.lower() or "115" in dps or "150" in dps
            if not is_cam:
                continue

            ov = overrides.get(did_str, {}) if isinstance(overrides, dict) else {}
            loc = local_devs.get(did_str, {}) if isinstance(local_devs, dict) else {}
            ip_cand = str(
                (ov.get("local_ip") or ov.get("ip") if isinstance(ov, dict) else "")
                or (loc.get("local_ip") or loc.get("ip") if isinstance(loc, dict) else "")
                or (obj.get("ip") if isinstance(obj, dict) else getattr(obj, "ip", "") or "")
            ).strip()
            mac_cand = (
                (ov.get("mac") if isinstance(ov, dict) else "")
                or (loc.get("mac") if isinstance(loc, dict) else "")
                or (obj.get("mac") if isinstance(obj, dict) else getattr(obj, "mac", "") or "")
            )
            linked = ""
            if callable(getattr(coord, "find_linked_camera_entity", None)):
                try:
                    linked = str(coord.find_linked_camera_entity(did_str) or "")
                except Exception:
                    pass

            devs.append({
                "device_id": did_str,
                "tuya_device_id": did_str,
                "name": (ov.get("custom_name") if isinstance(ov, dict) else "") or name,
                "model_id": pname or "Caméra Tuya OEM",
                "local_ip": ip_cand if is_private_lan_ip(ip_cand) else "",
                "mac_address": _normalize_mac(mac_cand),
                "local_key": str(obj.get("local_key") if isinstance(obj, dict) else getattr(obj, "local_key", "") or ""),
                "rtsp_url": str(ov.get("rtsp_url") or ov.get("stream_url") or "") if isinstance(ov, dict) else "",
                "ha_entity_id": linked,
                "online": bool(obj.get("online", True) if isinstance(obj, dict) else getattr(obj, "online", True)),
            })

        return devs

    # --- 2. Blink ---

    def _blink_base_url(self) -> str:
        """Resolve Blink REST endpoint URL from region/tier or host."""
        cand = (self.host or self.region or "prod").strip().lower()
        if cand.startswith("http"):
            return cand.rstrip("/")
        if "immedia-semi.com" in cand:
            host_only = cand.lstrip("/")
            if not host_only.startswith("rest-"):
                host_only = f"rest-{host_only}"
            return f"https://{host_only}"
        reg = (self.region or "prod").strip().lower()
        if reg in ("eu", "global", ""):
            reg = "prod"
        return f"https://rest-{reg}.immedia-semi.com"

    async def _login_blink(self) -> dict[str, Any]:
        """Authenticate against Blink Cloud REST API (handles 2FA PIN verification)."""
        if not self.username or not self.password:
            return {"status": "error", "error": "E-mail et mot de passe Blink requis."}

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Blink/270422 (Android 14)",
        }
        payload = {
            "email": self.username,
            "password": self.password,
            "unique_id": self.hardware_id,
            "reauth": True,
        }
        try:
            code, data = await self._http_request(
                "POST",
                "https://rest-prod.immedia-semi.com/api/v5/account/login",
                headers=headers,
                json_data=payload,
            )
        except Exception as err:
            self.last_error = str(err)
            return {"status": "error", "error": f"Erreur réseau Blink : {err}"}

        if not isinstance(data, dict) or code >= 400:
            msg = data.get("message") if isinstance(data, dict) else str(data)
            self.last_error = str(msg or f"HTTP {code}")
            return {"status": "error", "error": f"Connexion Blink refusée : {self.last_error}"}

        auth_obj = data.get("auth") or {}
        acc_obj = data.get("account") or {}
        self.token = str(auth_obj.get("token") or "")
        self.account_num_id = str(acc_obj.get("account_id") or "")
        self.client_id = str(acc_obj.get("client_id") or "")
        if acc_obj.get("tier"):
            self.region = str(acc_obj["tier"])

        if acc_obj.get("client_verification_required"):
            self.status = "2fa_required"
            self.last_error = ""
            return {
                "status": "2fa_required",
                "session_id": self.account_id,
                "provider": "blink",
                "message": "Blink a envoyé un code PIN de vérification (E-mail ou SMS). Saisissez-le ci-dessous.",
            }

        self.status = "connected"
        self.last_error = ""
        await self.async_fetch_devices()
        return {"status": "connected", "devices": self.devices}

    async def _verify_blink_2fa(self, pin_code: str) -> dict[str, Any]:
        """Complete Blink 2FA client verification with received PIN."""
        if not self.token or not self.account_num_id or not self.client_id:
            return {"status": "error", "error": "Session Blink 2FA expirée. Recommencez la connexion."}

        url = f"{self._blink_base_url()}/api/v4/account/{self.account_num_id}/client/{self.client_id}/pin/verify"
        headers = {
            "TOKEN-AUTH": self.token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            code, data = await self._http_request("POST", url, headers=headers, json_data={"pin": pin_code})
        except Exception as err:
            return {"status": "error", "error": f"Erreur réseau validation Blink : {err}"}

        valid = isinstance(data, dict) and (data.get("valid") is True or (code == 200 and not data.get("error")))
        if not valid:
            msg = data.get("message") if isinstance(data, dict) else f"HTTP {code}"
            return {"status": "error", "error": f"Code PIN Blink invalide : {msg}"}

        self.status = "connected"
        self.last_error = ""
        await self.async_fetch_devices()
        return {"status": "connected", "devices": self.devices}

    async def _fetch_blink_devices(self) -> list[dict[str, Any]]:
        """Fetch Blink cameras & Blink Mini devices from homescreen endpoint."""
        devs: list[dict[str, Any]] = []
        if not self.token or not self.account_num_id:
            return devs

        url = f"{self._blink_base_url()}/api/v3/accounts/{self.account_num_id}/homescreen"
        headers = {"TOKEN-AUTH": self.token, "Accept": "application/json"}
        try:
            code, data = await self._http_request("GET", url, headers=headers)
            if code == 401 and self.username and self.password:
                re_res = await self._login_blink()
                if re_res.get("status") == "connected":
                    code, data = await self._http_request(
                        "GET",
                        f"{self._blink_base_url()}/api/v3/accounts/{self.account_num_id}/homescreen",
                        headers={"TOKEN-AUTH": self.token, "Accept": "application/json"},
                    )
            if code == 200 and isinstance(data, dict):
                for section, kind in (("cameras", "Blink Camera"), ("owls", "Blink Mini")):
                    for cam in data.get(section) or []:
                        if not isinstance(cam, dict):
                            continue
                        cid = str(cam.get("id") or cam.get("serial") or "")
                        if not cid:
                            continue
                        signals = cam.get("signals") or {}
                        bat = cam.get("battery")
                        if bat is None:
                            bat = signals.get("battery")
                        devs.append({
                            "device_id": cid,
                            "serial": str(cam.get("serial") or ""),
                            "name": str(cam.get("name") or f"Blink {cid}"),
                            "model_id": str(cam.get("type") or kind),
                            "battery_level": bat,
                            "signal_strength": signals.get("wifi"),
                            "online": str(cam.get("status") or "").lower() != "offline",
                            "network_id": str(cam.get("network_id") or ""),
                        })
                self.status = "connected"
                self.last_error = ""
            elif code == 401:
                self.status = "token_expired"
                self.last_error = "Jeton Blink expiré — reconnectez ou resynchronisez depuis HA"
        except Exception as err:
            _LOGGER.debug("Blink homescreen fetch failed: %s", err)

        return devs

    # --- 3. Ezviz ---

    def _ezviz_base_url(self) -> str:
        """Resolve Ezviz API domain for selected region."""
        reg = (self.region or "eu").strip()
        if reg.startswith("http"):
            return reg.rstrip("/")
        if "." in reg:
            return f"https://{reg}"
        return EZVIZ_REGIONS.get(reg.lower(), EZVIZ_REGIONS["eu"])

    async def _login_ezviz(self, sms_code: str = "") -> dict[str, Any]:
        """Authenticate against Ezviz Cloud REST v3 API."""
        if not self.username or not self.password:
            return {"status": "error", "error": "E-mail/téléphone et mot de passe Ezviz requis."}

        pwd_md5 = hashlib.md5(self.password.encode("utf-8")).hexdigest()
        form: dict[str, Any] = {
            "account": self.username,
            "password": pwd_md5,
            "featureCode": hashlib.md5(self.hardware_id.encode("utf-8")).hexdigest(),
            "msgType": "3" if sms_code else "0",
            "cuName": "Android",
        }
        if sms_code:
            form["smsCode"] = sms_code

        try:
            code, data = await self._http_request(
                "POST",
                f"{self._ezviz_base_url()}/v3/users/login/v5",
                headers={"Accept": "application/json"},
                form_data=form,
            )
        except Exception as err:
            return {"status": "error", "error": f"Erreur réseau Ezviz : {err}"}

        if not isinstance(data, dict) or code >= 400:
            return {"status": "error", "error": f"Erreur HTTP Ezviz ({code})"}

        meta = data.get("meta") or {}
        mcode = meta.get("code")
        if mcode in (6002, 6003, 6004, 1020):
            self.status = "2fa_required"
            return {
                "status": "2fa_required",
                "session_id": self.account_id,
                "provider": "ezviz",
                "message": "Validation 2FA Ezviz requise. Saisissez le code SMS/e-mail reçu.",
            }

        if mcode != 200:
            return {"status": "error", "error": f"Connexion Ezviz refusée : {meta.get('message') or mcode}"}

        login_sess = data.get("loginSession") or {}
        login_area = data.get("loginArea") or {}
        self.token = str(login_sess.get("sessionId") or "")
        self.uid = str(login_sess.get("userId") or "")
        if login_area.get("apiDomain"):
            self.region = str(login_area["apiDomain"])
        self.status = "connected"
        self.last_error = ""
        await self.async_fetch_devices()
        return {"status": "connected", "devices": self.devices}

    async def _fetch_ezviz_devices(self) -> list[dict[str, Any]]:
        """Fetch Ezviz cameras from v3 resources pagelist."""
        devs: list[dict[str, Any]] = []
        if not self.token:
            return devs

        url = f"{self._ezviz_base_url()}/v3/userdevices/v1/resources/pagelist?groupId=-1&limit=50&offset=0"
        headers = {"sessionId": self.token, "Accept": "application/json"}
        try:
            code, data = await self._http_request("GET", url, headers=headers)
            if code == 200 and isinstance(data, dict):
                for item in data.get("deviceInfos") or []:
                    if not isinstance(item, dict):
                        continue
                    serial = str(item.get("deviceSerial") or item.get("subSerial") or "")
                    if not serial:
                        continue
                    raw_ip = str(item.get("localIp") or item.get("netIp") or "").strip()
                    devs.append({
                        "device_id": serial,
                        "serial": serial,
                        "name": str(item.get("name") or item.get("deviceName") or f"Ezviz {serial}"),
                        "model_id": str(item.get("deviceType") or item.get("fullSerial") or "Caméra Ezviz"),
                        "local_ip": raw_ip if is_private_lan_ip(raw_ip) else "",
                        "online": int(item.get("status", 1)) == 1,
                    })
                self.status = "connected"
        except Exception as err:
            _LOGGER.debug("Ezviz device pagelist error: %s", err)

        return devs

    # --- 4. Reolink ---

    async def _probe_tcp(self, host: str, port: int, timeout: float = 1.5) -> bool:
        """Non-blocking TCP connect check for Reolink HTTP/RTSP ports."""
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=timeout)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return True
        except Exception:
            return False

    async def _login_reolink(self) -> dict[str, Any]:
        """Authenticate against Reolink local CGI API (with RTSP port fallback for battery models)."""
        clean_host = urlsplit(self.host).hostname or self.host.strip()
        if not clean_host:
            return {"status": "error", "error": "Adresse IP ou hôte Reolink requis."}

        self.host = clean_host
        scheme = "https" if self.port == 443 else "http"
        base_cgi = f"{scheme}://{clean_host}:{self.port}/cgi-bin/api.cgi"

        login_payload = [
            {
                "cmd": "Login",
                "action": 0,
                "param": {
                    "User": {
                        "userName": self.username or "admin",
                        "password": self.password,
                    }
                },
            }
        ]
        try:
            code, data = await self._http_request(
                "POST",
                f"{base_cgi}?cmd=Login",
                json_data=login_payload,
                ssl=False if scheme == "https" else None,
            )
            if code == 200 and isinstance(data, list) and data:
                first = data[0]
                if first.get("code") == 0:
                    self.token = str((first.get("value") or {}).get("Token", {}).get("name") or "")
                    self.status = "connected"
                    self.last_error = ""
                    await self.async_fetch_devices()
                    return {"status": "connected", "devices": self.devices}
                err_detail = (first.get("error") or {}).get("detail") or f"code {first.get('code')}"
                return {"status": "error", "error": f"Identifiants Reolink refusés : {err_detail}"}
        except Exception as err:
            _LOGGER.debug("Reolink HTTP CGI login failed on %s:%s (%s), checking RTSP", clean_host, self.port, err)

        # Fallback: verify direct RTSP port 554 (some Reolink hubs/cameras expose RTSP cleanly)
        if await self._probe_tcp(clean_host, self.rtsp_port):
            self.status = "connected"
            self.last_error = ""
            self.devices = self._merge_ha_entities_into_devices([{
                "device_id": f"reolink_{clean_host.replace('.', '_')}",
                "name": self.name or f"Reolink {clean_host}",
                "model_id": "Reolink RTSP",
                "local_ip": clean_host if is_private_lan_ip(clean_host) else "",
                "rtsp_port": self.rtsp_port,
                "online": True,
            }])
            self.last_sync = time.time()
            return {"status": "connected", "devices": self.devices}

        self.status = "error"
        self.last_error = f"Caméra Reolink injoignable sur {clean_host}:{self.port} / RTSP {self.rtsp_port}"
        return {"status": "error", "error": self.last_error}

    async def _fetch_reolink_devices(self) -> list[dict[str, Any]]:
        """Query Reolink GetDevInfo & GetChannelstatus via CGI API."""
        clean_host = urlsplit(self.host).hostname or self.host.strip()
        if not clean_host:
            return []

        scheme = "https" if self.port == 443 else "http"
        base_cgi = f"{scheme}://{clean_host}:{self.port}/cgi-bin/api.cgi"

        tok = self.token
        try:
            if not tok:
                _, ldata = await self._http_request(
                    "POST",
                    f"{base_cgi}?cmd=Login",
                    json_data=[{"cmd": "Login", "action": 0, "param": {"User": {"userName": self.username or "admin", "password": self.password}}}],
                    ssl=False if scheme == "https" else None,
                )
                if isinstance(ldata, list) and ldata and ldata[0].get("code") == 0:
                    tok = str((ldata[0].get("value") or {}).get("Token", {}).get("name") or "")

            if tok:
                _, info_data = await self._http_request(
                    "POST",
                    f"{base_cgi}?token={tok}",
                    json_data=[
                        {"cmd": "GetDevInfo", "action": 0, "param": {}},
                        {"cmd": "GetChannelstatus", "action": 0, "param": {}},
                    ],
                    ssl=False if scheme == "https" else None,
                )
                dev_info = {}
                channels = []
                if isinstance(info_data, list):
                    for block in info_data:
                        if block.get("cmd") == "GetDevInfo" and block.get("code") == 0:
                            dev_info = (block.get("value") or {}).get("DevInfo") or {}
                        elif block.get("cmd") == "GetChannelstatus" and block.get("code") == 0:
                            channels = (block.get("value") or {}).get("status") or []

                # Close temporary CGI token cleanly
                try:
                    await self._http_request(
                        "POST",
                        f"{base_cgi}?cmd=Logout&token={tok}",
                        json_data=[{"cmd": "Logout", "action": 0, "param": {}}],
                        ssl=False if scheme == "https" else None,
                    )
                except Exception:
                    pass

                model = str(dev_info.get("model") or "Caméra Reolink")
                dev_name = str(dev_info.get("name") or self.name or f"Reolink {clean_host}")
                results: list[dict[str, Any]] = []
                if isinstance(channels, list) and len(channels) > 1:
                    for ch in channels:
                        if not isinstance(ch, dict):
                            continue
                        ch_num = ch.get("channel", 0)
                        ch_name = ch.get("name") or f"{dev_name} CH{int(ch_num) + 1}"
                        results.append({
                            "device_id": f"reolink_{clean_host.replace('.', '_')}_ch{ch_num}",
                            "name": str(ch_name),
                            "model_id": model,
                            "local_ip": clean_host if is_private_lan_ip(clean_host) else "",
                            "channel": ch_num,
                            "rtsp_port": self.rtsp_port,
                            "online": int(ch.get("online", 1)) == 1,
                        })
                if not results:
                    results.append({
                        "device_id": f"reolink_{clean_host.replace('.', '_')}",
                        "name": dev_name,
                        "model_id": model,
                        "local_ip": clean_host if is_private_lan_ip(clean_host) else "",
                        "rtsp_port": self.rtsp_port,
                        "online": True,
                    })
                return results
        except Exception as err:
            _LOGGER.debug("Reolink CGI device fetch error on %s: %s", clean_host, err)

        if self.devices:
            return list(self.devices)
        return [{
            "device_id": f"reolink_{clean_host.replace('.', '_')}",
            "name": self.name or f"Reolink {clean_host}",
            "model_id": "Caméra Reolink",
            "local_ip": clean_host if is_private_lan_ip(clean_host) else "",
            "rtsp_port": self.rtsp_port,
            "online": True,
        }]

    # --- Serialization ---

    def to_dict(self) -> dict[str, Any]:
        """Serialize full session state to persistent storage."""
        return {
            "id": self.account_id,
            "provider": self.provider,
            "name": self.name,
            "username": self.username,
            "password": self.password,
            "brand": self.brand,
            "country_code": self.country_code,
            "host": self.host,
            "port": self.port,
            "rtsp_port": self.rtsp_port,
            "verification_code": self.verification_code,
            "region": self.region,
            "token": self.token,
            "refresh_token": self.refresh_token,
            "uid": self.uid,
            "account_num_id": self.account_num_id,
            "client_id": self.client_id,
            "hardware_id": self.hardware_id,
            "status": self.status,
            "last_sync": self.last_sync,
            "last_error": self.last_error,
            "devices": self.devices,
        }

    def to_public_dict(self, configured_keys: set[str] | None = None) -> dict[str, Any]:
        """Serialize sanitized account overview for the frontend panel."""
        cfg = configured_keys or set()
        pub_devs = []
        for dev in self.devices:
            d = dict(dev)
            did = str(d.get("device_id") or "")
            tdid = str(d.get("tuya_device_id") or "")
            heid = str(d.get("ha_entity_id") or "")
            lip = str(d.get("local_ip") or "")
            d["already_added"] = any(
                k and k in cfg for k in (did, tdid, heid, f"ip:{lip}" if lip else "")
            )
            pub_devs.append(d)

        brand_label = self.provider.upper()
        if self.provider == "tuya_oem":
            brand_label = TUYA_OEM_PROFILES.get(self.brand, {}).get("name", self.brand or "Tuya OEM")
        elif self.provider == "blink":
            brand_label = "Blink"
        elif self.provider == "ezviz":
            brand_label = "Ezviz"
        elif self.provider == "reolink":
            brand_label = "Reolink"

        return {
            "id": self.account_id,
            "provider": self.provider,
            "provider_label": brand_label,
            "name": self.name or self.username or self.host or brand_label,
            "username": self.username,
            "brand": self.brand,
            "host": self.host,
            "region": self.region,
            "status": self.status,
            "last_sync": self.last_sync,
            "last_error": self.last_error,
            "camera_count": len(pub_devs),
            "devices": pub_devs,
        }
