"""Autonomous Wi-Fi Pairing and Discovery Engine for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
import struct
import subprocess
from typing import Any
import urllib.parse
import urllib.request

from .const import (
    CAMERA_AP_EXCLUDE,
    CAMERA_AP_KEYWORDS,
    CAMERA_AP_SSID_PREFIXES,
    CAMERA_AP_UID_REGEX,
    DEFAULT_PPPP_DISCOVERY_PORT,
    DOMAIN,
    DRIVER_GENERIC_MJPEG,
    DRIVER_GENERIC_RTSP,
    DRIVER_HA_PROXY,
    DRIVER_YSXLITE_PPPP,
    ILNK_MAGIC,
    PPPP_CMD_DEV_SEARCH,
    PPPP_CMD_WIFI_SET,
    PPPP_MAGIC,
)

_LOGGER = logging.getLogger(__name__)
_RE_CAMERA_UID = re.compile(CAMERA_AP_UID_REGEX, re.IGNORECASE)


def is_camera_ssid(ssid: str) -> bool:
    """Check if an SSID is likely a camera access point using wildcards (*keyword*) and UID regex."""
    if not ssid:
        return False
    upper = ssid.strip().upper()
    # Exclude standard domestic routers & ISPs
    if any(ex in upper for ex in CAMERA_AP_EXCLUDE):
        return False
    # 1. Wildcard check: match if any camera manufacturer/model keyword is inside the SSID (e.g. *TBAT*, *BAT*, *AYS*)
    for kw in CAMERA_AP_KEYWORDS:
        if kw in upper:
            return True
    # 2. Match standard camera AP UID structure (e.g. TBAT652718GRDCE, AYS-123456-ABCDE)
    if _RE_CAMERA_UID.match(upper):
        return True
    return False

# Protocol classification dictionary for known Home Assistant platforms
KNOWN_INCOMPATIBLE_PLATFORMS: dict[str, dict[str, str]] = {
    "aarlo": {
        "platform_name": "Arlo Cloud",
        "protocol": "Arlo AWS Cloud (Propriétaire)",
        "reason": "Flux vidéo chiffré hébergé sur les serveurs Amazon/Arlo. Ne fournit pas de flux direct RTSP/PPPP local sans passerelle tierce.",
    },
    "arlo": {
        "platform_name": "Arlo Cloud",
        "protocol": "Arlo AWS Cloud (Propriétaire)",
        "reason": "Flux vidéo chiffré hébergé sur les serveurs Arlo Cloud. Ne propose pas de serveur RTSP local.",
    },
    "blink": {
        "platform_name": "Blink Cloud (Amazon)",
        "protocol": "Blink Sync Module Propriétaire",
        "reason": "Caméra sur batterie reliée au Sync Module Amazon Blink. Aucun flux continu RTSP/MJPEG local disponible.",
    },
    "xiaomi_miot": {
        "platform_name": "Xiaomi Mi Home",
        "protocol": "Xiaomi MIIO Cloud (Chiffré)",
        "reason": "Flux vidéo chiffré par token matériel MIIO propriétaire. Requiert un firmware hacké (ex: Dafang-Hacks) pour exposer un flux RTSP direct.",
    },
    "xiaomi_home": {
        "platform_name": "Xiaomi Mi Home",
        "protocol": "Xiaomi MIIO Cloud (Chiffré)",
        "reason": "Flux vidéo chiffré par token matériel MIIO propriétaire. Requiert une passerelle ou un hack firmware.",
    },
    "tuya": {
        "platform_name": "Tuya / Smart Life",
        "protocol": "Tuya P2P Cloud (AES-128)",
        "reason": "Protocole propriétaire Tuya P2P chiffré AES. La caméra n'expose pas de flux RTSP/MJPEG direct non authentifié sur le LAN sans NVR compatible.",
    },
    "localtuya": {
        "platform_name": "Local Tuya",
        "protocol": "Tuya Local P2P",
        "reason": "Protocole propriétaire Tuya Local P2P (flux vidéo chiffré inaccessible sans serveur RTSP ouvert).",
    },
    "localtuya_rc": {
        "platform_name": "Local Tuya RC",
        "protocol": "Tuya Local P2P",
        "reason": "Protocole propriétaire Tuya Local P2P sans serveur RTSP ouvert.",
    },
    "ring": {
        "platform_name": "Ring Cloud (Amazon)",
        "protocol": "Ring SIP/WebRTC Cloud",
        "reason": "Flux hébergé dans le cloud Ring d'Amazon. Aucun flux RTSP direct local.",
    },
    "nest": {
        "platform_name": "Google Nest",
        "protocol": "Google Cloud WebRTC",
        "reason": "Flux vidéo propriétaire Google Nest Cloud.",
    },
    "eufy_security": {
        "platform_name": "Eufy Security",
        "protocol": "Eufy P2P Propriétaire",
        "reason": "Protocole propriétaire Anker Eufy P2P sans flux RTSP activé.",
    },
    "remote_homeassistant": {
        "platform_name": "Home Assistant Distant",
        "protocol": "Websocket HA Distant",
        "reason": "Entité miroir provenant d'un Home Assistant distant.",
    },
}

KNOWN_COMPATIBLE_PLATFORMS: dict[str, dict[str, str]] = {
    "generic": {
        "driver": DRIVER_GENERIC_RTSP,
        "protocol": "RTSP / MJPEG Générique",
        "model": "Caméra IP Générique HA",
    },
    "onvif": {
        "driver": DRIVER_GENERIC_RTSP,
        "protocol": "ONVIF Standard (Profil S/T)",
        "model": "Caméra ONVIF IP",
    },
    "mjpeg": {
        "driver": DRIVER_GENERIC_MJPEG,
        "protocol": "MJPEG HTTP Stream",
        "model": "Webcam MJPEG / ESP32-CAM",
    },
    "ffmpeg": {
        "driver": DRIVER_GENERIC_RTSP,
        "protocol": "FFmpeg Video Stream",
        "model": "Flux Vidéo FFmpeg",
    },
}


class WifiPairingEngine:
    """Manages pairing and discovery of cameras without requiring a mobile app."""

    def __init__(self, hass: Any) -> None:
        """Initialize pairing engine."""
        self.hass = hass
        self._is_pairing = False
        self._current_step = "idle"
        self._pairing_log: list[str] = []
        self._discovered_devices: list[dict[str, Any]] = []

    @property
    def is_pairing(self) -> bool:
        """Return True if pairing process is active."""
        return self._is_pairing

    def add_log(self, msg: str) -> None:
        """Add timestamped message to the terminal log."""
        import datetime
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        self._pairing_log.append(f"[{now_str}] {msg}")
        if len(self._pairing_log) > 60:
            self._pairing_log = self._pairing_log[-60:]

    def get_status(self) -> dict[str, Any]:
        """Return pairing status snapshot."""
        return {
            "active": self._is_pairing,
            "step": self._current_step,
            "logs": self._pairing_log[-40:],
            "discovered": self._discovered_devices,
        }

    async def async_scan_local_network(self, timeout: float = 4.0) -> list[dict[str, Any]]:
        """Legacy helper: Broadcast UDP discovery packets for online PPPP/YsxLite cameras."""
        result = await self.async_scan_all_cameras(timeout=timeout)
        return result.get("compatible", [])

    async def async_scan_all_cameras(self, timeout: float = 4.0) -> dict[str, Any]:
        """Scan network and Home Assistant entities, classifying cameras by protocol compatibility."""
        loop = asyncio.get_running_loop()

        # Step 1: Scan active LAN hosts (UDP PPPP + RTSP TCP + ONVIF)
        lan_compatible = await self._scan_lan_hosts(loop, timeout)

        # Step 2: Scan Home Assistant camera entities and registry
        ha_compatible, ha_incompatible = await self._scan_ha_camera_entities()

        # Step 3: Get already configured cameras in DomoLink-Camera
        configured_hosts = set()
        configured_names = set()
        mgr = self.hass.data.get(DOMAIN, {}).get("manager")
        if mgr and hasattr(mgr, "cameras"):
            for cam in mgr.cameras.values():
                if cam.get("host"):
                    configured_hosts.add(str(cam.get("host")).strip().lower())
                if cam.get("name"):
                    configured_names.add(str(cam.get("name")).strip().lower())

        # Combine compatible devices (de-duplicate by host/name)
        compatible_list: list[dict[str, Any]] = []
        seen_hosts: set[str] = set()

        for item in lan_compatible + ha_compatible:
            host_key = item.get("host", "").lower()
            name_key = item.get("name", "").lower()
            key = host_key or name_key
            if key in seen_hosts:
                continue
            seen_hosts.add(key)

            # Check if already added
            is_added = (
                (host_key and host_key in configured_hosts)
                or (name_key and name_key in configured_names)
            )
            item["already_added"] = is_added
            compatible_list.append(item)

        # De-duplicate incompatible list (filter mirror duplicates like _2, _2_2)
        incompatible_list: list[dict[str, Any]] = []
        seen_incompatible_names: set[str] = set()

        for item in ha_incompatible:
            raw_id = item.get("entity_id", "")
            base_name = item.get("name", "")
            # Filter obvious remote mirror duplicates
            if re.search(r"_\d+(_\d+)*$", raw_id) and item.get("platform") == "remote_homeassistant":
                continue
            clean_name = base_name.strip().lower()
            if clean_name in seen_incompatible_names:
                continue
            seen_incompatible_names.add(clean_name)
            incompatible_list.append(item)

        return {
            "compatible": compatible_list,
            "incompatible": incompatible_list,
            "summary": {
                "total": len(compatible_list) + len(incompatible_list),
                "compatible_count": len(compatible_list),
                "incompatible_count": len(incompatible_list),
            },
        }

    async def _scan_lan_hosts(self, loop: asyncio.AbstractEventLoop, timeout: float) -> list[dict[str, Any]]:
        """Probe local subnet for PPPP (32108), RTSP (554/8554), and MJPEG/HTTP."""
        compatible_found: list[dict[str, Any]] = []

        # 1. Broadcast PPPP UDP Search
        def _broadcast_pppp() -> list[dict[str, Any]]:
            results = []
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.2)

            pkt = PPPP_MAGIC + struct.pack(">HHH", PPPP_CMD_DEV_SEARCH, 0, 1)
            broadcast_ips = ["255.255.255.255", "192.168.1.255", "192.168.0.255"]
            for b_ip in broadcast_ips:
                try:
                    sock.sendto(pkt, (b_ip, DEFAULT_PPPP_DISCOVERY_PORT))
                except Exception:
                    continue

            start_t = loop.time()
            while loop.time() - start_t < 1.5:
                try:
                    data, addr = sock.recvfrom(2048)
                    host = addr[0]
                    dev_id = f"CAM_{host.replace('.', '_')}"
                    if PPPP_MAGIC in data:
                        raw_str = "".join([chr(b) for b in data if 32 <= b <= 126])
                        if len(raw_str) > 4:
                            dev_id = raw_str[:20].strip()

                    entry = {
                        "host": host,
                        "port": DEFAULT_PPPP_DISCOVERY_PORT,
                        "device_id": dev_id,
                        "name": f"Caméra YsxLite ({host})",
                        "driver": DRIVER_YSXLITE_PPPP,
                        "protocol": "YsxLite PPPP (UDP 32108)",
                        "model": "YsxLite / A9 Mini Wi-Fi",
                        "details": "Protocole PPPP natif détecté - Prise en charge Live, Snapshot, IR et Reboot",
                        "compatible": True,
                    }
                    if not any(d["host"] == host for d in results):
                        results.append(entry)
                except socket.timeout:
                    break
                except Exception:
                    break

            sock.close()
            return results

        try:
            pppp_devices = await self.hass.async_add_executor_job(_broadcast_pppp)
            compatible_found.extend(pppp_devices)
        except Exception as e:
            _LOGGER.debug("UDP PPPP broadcast error: %s", e)

        # 2. Collect candidate LAN IPs from ARP table and detect gateway IPs
        def _get_network_info() -> tuple[set[str], set[str]]:
            ips = set()
            gateways = {"192.168.1.254", "192.168.0.254", "192.168.1.1", "192.168.0.1"}

            # Read default gateway from /proc/net/route
            try:
                with open("/proc/net/route", "r", encoding="utf-8") as f:
                    for line in f.readlines()[1:]:
                        parts = line.strip().split()
                        if len(parts) >= 3 and parts[1] == "00000000":
                            gw_ip = socket.inet_ntoa(struct.pack("<L", int(parts[2], 16)))
                            gateways.add(gw_ip)
            except Exception:
                pass

            # Read ARP table
            try:
                with open("/proc/net/arp", "r", encoding="utf-8") as f:
                    for line in f.readlines()[1:]:
                        parts = line.split()
                        if len(parts) >= 4 and parts[3] != "00:00:00:00:00:00":
                            ip = parts[0]
                            if not ip.endswith(".255") and not ip.endswith(".0"):
                                ips.add(ip)
            except Exception:
                pass

            if not ips:
                try:
                    out = subprocess.check_output(["arp", "-an"]).decode("utf-8", errors="ignore")
                    for match in re.finditer(r"\((192\.168\.\d+\.\d+)\)", out):
                        ip = match.group(1)
                        if not ip.endswith(".255") and not ip.endswith(".0"):
                            ips.add(ip)
                except Exception:
                    pass

            return ips, gateways

        try:
            candidate_ips, gateway_ips = await self.hass.async_add_executor_job(_get_network_info)
        except Exception:
            candidate_ips, gateway_ips = set(), {"192.168.1.254", "192.168.0.254", "192.168.1.1", "192.168.0.1"}

        # 3. Concurrent RTSP handshake probing on candidate IPs (RTSP 554, 8554)
        async def _probe_ip(ip: str) -> dict[str, Any] | None:
            # Skip if already found via PPPP or if it is a known router / Freebox gateway
            if any(d["host"] == ip for d in compatible_found):
                return None
            if ip in gateway_ips:
                return None

            # Test RTSP port 554 / 8554 with real RTSP OPTIONS protocol verification
            for port in (554, 8554):
                try:
                    reader, writer = await asyncio.wait_for(
                        asyncio.open_connection(ip, port), timeout=0.4
                    )
                    # Send RTSP OPTIONS probe to verify it is actually an RTSP camera
                    probe_req = (
                        f"OPTIONS rtsp://{ip}:{port}/ RTSP/1.0\r\n"
                        f"CSeq: 1\r\n"
                        f"User-Agent: DomoLink-Camera\r\n\r\n"
                    )
                    writer.write(probe_req.encode("ascii"))
                    await writer.drain()

                    # Require valid RTSP response signature (e.g. RTSP/1.0 200 or RTSP/1.0 401)
                    raw_resp = await asyncio.wait_for(reader.read(256), timeout=0.7)
                    writer.close()
                    await writer.wait_closed()

                    if b"RTSP/1." in raw_resp:
                        return {
                            "host": ip,
                            "port": port,
                            "device_id": f"RTSP_{ip.replace('.', '_')}_{port}",
                            "name": f"Caméra IP / RTSP ({ip})",
                            "driver": DRIVER_GENERIC_RTSP,
                            "protocol": f"RTSP Standard (Port {port})",
                            "model": "Generic RTSP / ONVIF IP Camera",
                            "details": f"Serveur RTSP actif et validé sur le port {port} - Compatible flux direct H.264/RTSP",
                            "compatible": True,
                        }
                except Exception:
                    pass
            return None

        if candidate_ips:
            tasks = [_probe_ip(ip) for ip in candidate_ips]
            rtsp_results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in rtsp_results:
                if isinstance(r, dict) and r:
                    compatible_found.append(r)

        return compatible_found

    async def _scan_ha_camera_entities(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Inspect all Home Assistant camera entities and categorize them."""
        compatible: list[dict[str, Any]] = []
        incompatible: list[dict[str, Any]] = []

        try:
            # Query entity registry to resolve integration platform
            ent_map: dict[str, Any] = {}
            if "entity_registry" in self.hass.data:
                er = self.hass.data["entity_registry"]
                if hasattr(er, "entities"):
                    ent_map = er.entities
            elif hasattr(self.hass.helpers, "entity_registry"):
                er = self.hass.helpers.entity_registry.async_get(self.hass)
                ent_map = er.entities

            for state in self.hass.states.async_all():
                eid = state.entity_id
                if not eid.startswith("camera."):
                    continue

                # Skip unavailable camera entities
                if state.state == "unavailable":
                    continue

                # Filter out obvious mirror duplicates from Remote Home Assistant (e.g. _2, _2_2)
                if re.search(r"_\d+(_\d+)*$", eid):
                    continue

                attrs = state.attributes or {}
                friendly_name = attrs.get("friendly_name") or eid
                model = attrs.get("model_name") or attrs.get("brand") or "Caméra Détectée"

                # Find platform in entity registry
                reg_entry = ent_map.get(eid)
                platform = getattr(reg_entry, "platform", "") if reg_entry else ""
                if not platform:
                    platform = attrs.get("platform") or "inconnu"

                # Skip DomoLink-Camera self entities to avoid recursion
                if platform == DOMAIN:
                    continue

                # Check if known direct RTSP/MJPEG compatible
                if platform in KNOWN_COMPATIBLE_PLATFORMS:
                    info = KNOWN_COMPATIBLE_PLATFORMS[platform]
                    compatible.append({
                        "host": eid,
                        "port": 0,
                        "device_id": eid,
                        "name": friendly_name,
                        "driver": info["driver"],
                        "protocol": info["protocol"],
                        "model": model if model != "Caméra Détectée" else info["model"],
                        "details": f"Entité locale Home Assistant ({platform}) avec flux direct compatible",
                        "compatible": True,
                        "source": "ha_entity",
                    })
                else:
                    # Active camera in HA (Tuya, Arlo, Xiaomi, Blink, etc.) proxied through Home Assistant!
                    info = KNOWN_INCOMPATIBLE_PLATFORMS.get(platform, {})
                    plat_name = info.get("platform_name") or platform.capitalize()
                    compatible.append({
                        "host": eid,
                        "port": 0,
                        "device_id": eid,
                        "name": friendly_name,
                        "driver": DRIVER_HA_PROXY,
                        "protocol": f"Passerelle Home Assistant ({plat_name})",
                        "model": model if model != "Caméra Détectée" else f"Caméra {plat_name}",
                        "details": f"Gérée par '{plat_name}' dans Home Assistant • Snapshot et Live streaming proxifiés automatiquement",
                        "compatible": True,
                        "source": "ha_entity",
                    })

        except Exception as e:
            _LOGGER.error("Error inspecting HA camera entities: %s", e)

        return compatible, incompatible

    def build_wifi_payloads(self, ssid: str, password: str) -> list[bytes]:
        """Generate all binary and structural payload variants for PPPP / YsxLite Wi-Fi pairing."""
        s_bytes = ssid.encode("utf-8")
        p_bytes = password.encode("utf-8")
        payload = struct.pack("B", len(s_bytes)) + s_bytes + struct.pack("B", len(p_bytes)) + p_bytes

        # 1. Standard Big-Endian PPPP packet
        p1 = PPPP_MAGIC + struct.pack(">HHH", PPPP_CMD_WIFI_SET, len(payload), 1) + payload

        # 2. Little-Endian header variant (some ARM SoC camera firmwares)
        p2 = PPPP_MAGIC + struct.pack("<HHH", PPPP_CMD_WIFI_SET, len(payload), 1) + payload

        # 3. Fixed 128-byte C-struct: char ssid[64] + char pass[64]
        payload_fixed = s_bytes.ljust(64, b"\x00") + p_bytes.ljust(64, b"\x00")
        p3 = PPPP_MAGIC + struct.pack(">HHH", PPPP_CMD_WIFI_SET, 128, 1) + payload_fixed

        # 4. iLnk header variant
        p4 = ILNK_MAGIC + struct.pack(">HH", PPPP_CMD_WIFI_SET, len(payload)) + payload

        # 5. JSON / Text null-terminated fallback
        p5 = f'{{"ssid":"{ssid}","pwd":"{password}"}}\x00'.encode("utf-8")

        return [p1, p2, p3, p4, p5]

    async def _async_supervisor_scan_wlan0(self) -> list[dict[str, Any]]:
        """Query Home Assistant OS Supervisor API to scan Wi-Fi access points via host wireless interface."""
        token = os.environ.get("SUPERVISOR_TOKEN")
        if not token:
            return []

        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        try:
            # Import aiohttp or use HA helper
            if hasattr(self.hass.helpers, "aiohttp_client"):
                session = self.hass.helpers.aiohttp_client.async_get_clientsession(self.hass)
            else:
                import aiohttp
                session = aiohttp.ClientSession()

            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }

            # Find wireless interface name (default wlan0)
            iface = "wlan0"
            try:
                async with session.get(
                    "http://supervisor/network/info",
                    headers=headers,
                    timeout=4.0,
                ) as info_resp:
                    if info_resp.status == 200:
                        info_data = await info_resp.json()
                        for if_item in info_data.get("data", {}).get("interfaces", []):
                            if if_item.get("type") == "wireless":
                                iface = if_item.get("interface", "wlan0")
                                break
            except Exception:
                pass

            # Trigger Wi-Fi scan on interface
            scan_url = f"http://supervisor/network/interface/{iface}/accesspoints"
            try:
                async with session.post(scan_url, headers=headers, timeout=5.0) as post_resp:
                    pass
            except Exception:
                pass

            # Read scanned access points
            async with session.get(scan_url, headers=headers, timeout=5.0) as get_resp:
                if get_resp.status == 200:
                    ap_data = await get_resp.json()
                    accesspoints = ap_data.get("data", {}).get("accesspoints", [])
                    for ap in accesspoints:
                        s_name = ap.get("ssid", "").strip()
                        if not s_name or s_name in seen:
                            continue
                        seen.add(s_name)
                        sig = ap.get("signal", 70)
                        sec = ap.get("security", "OPEN")
                        results.append({
                            "ssid": s_name,
                            "signal": sig,
                            "security": sec,
                            "mac": ap.get("mac", ""),
                            "frequency": ap.get("frequency", 2412),
                            "is_camera": is_camera_ssid(s_name),
                        })
        except Exception as err:
            _LOGGER.debug("Supervisor wlan scan unavailable or failed: %s", err)

        return results

    async def async_scan_camera_aps(self) -> list[dict[str, Any]]:
        """Scan nearby Wi-Fi Access Points to find cameras in AP mode (Supervisor wlan0 + nmcli + airport)."""
        # 1. Primary: Try Home Assistant OS Supervisor API (wlan0)
        supervisor_aps = await self._async_supervisor_scan_wlan0()
        if supervisor_aps:
            supervisor_aps.sort(key=lambda x: (not x["is_camera"], -x["signal"]))
            return supervisor_aps

        # 2. Secondary fallback: Host nmcli or macOS airport
        def _scan() -> list[dict[str, Any]]:
            results: list[dict[str, Any]] = []
            seen: set[str] = set()

            # Linux nmcli scan
            try:
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "device", "wifi", "list"],
                    timeout=4,
                    stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="ignore")
                for line in out.splitlines():
                    parts = line.strip().split(":")
                    if parts and parts[0]:
                        s_name = parts[0].strip()
                        if s_name in seen:
                            continue
                        seen.add(s_name)
                        sig = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 70
                        sec = parts[2] if len(parts) > 2 else "OPEN"
                        is_cam = is_camera_ssid(s_name)
                        results.append({
                            "ssid": s_name,
                            "signal": sig,
                            "security": sec,
                            "is_camera": is_cam,
                        })
            except Exception:
                pass

            # macOS airport utility scan (for development / local Mac environments)
            if not results:
                try:
                    airport_bin = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
                    out = subprocess.check_output(
                        [airport_bin, "-s"],
                        timeout=4,
                        stderr=subprocess.DEVNULL,
                    ).decode("utf-8", errors="ignore")
                    for line in out.splitlines()[1:]:
                        parts = line.split()
                        if parts:
                            s_name = parts[0].strip()
                            if s_name in seen:
                                continue
                            seen.add(s_name)
                            is_cam = is_camera_ssid(s_name)
                            results.append({
                                "ssid": s_name,
                                "signal": 75,
                                "security": "OPEN" if "NONE" in line.upper() else "WPA",
                                "is_camera": is_cam,
                            })
                except Exception:
                    pass

            # Sort cameras first, then by signal
            results.sort(key=lambda x: (not x["is_camera"], -x["signal"]))
            return results

        try:
            return await self.hass.async_add_executor_job(_scan)
        except Exception as e:
            _LOGGER.debug("AP scan error: %s", e)
            return []

    async def _send_http_cgi_wifi_config(self, ip: str, ssid: str, password: str) -> None:
        """Send HTTP CGI Wi-Fi setup queries commonly supported by IP camera chipsets."""
        def _request_all() -> None:
            q_ssid = urllib.parse.quote(ssid)
            q_pwd = urllib.parse.quote(password)
            endpoints = [
                f"http://{ip}/set_wifi.cgi?ssid={q_ssid}&pwd={q_pwd}",
                f"http://{ip}/wifi_set?ssid={q_ssid}&password={q_pwd}",
                f"http://{ip}/cgi-bin/hi3510/param.cgi?cmd=setwirelessattr&-wf_ssid={q_ssid}&-wf_key={q_pwd}",
                f"http://{ip}/config?ssid={q_ssid}&pwd={q_pwd}",
            ]
            for url in endpoints:
                try:
                    req = urllib.request.Request(
                        url,
                        headers={"User-Agent": "DomoLink-Camera-Engine"},
                    )
                    with urllib.request.urlopen(req, timeout=0.8):
                        pass
                except Exception:
                    pass

        try:
            await self.hass.async_add_executor_job(_request_all)
        except Exception:
            pass

    async def _async_bridge_camera_ap(
        self, camera_ssid: str | None, target_ssid: str, target_pass: str, camera_ap_ip: str
    ) -> bool:
        """Attempt autonomous server-side Wi-Fi bridge to camera AP using secondary interface or Supervisor."""
        if not camera_ssid:
            return False

        # 1. Try Home Assistant OS Supervisor API bridge
        token = os.environ.get("SUPERVISOR_TOKEN")
        if token:
            try:
                if hasattr(self.hass.helpers, "aiohttp_client"):
                    session = self.hass.helpers.aiohttp_client.async_get_clientsession(self.hass)
                else:
                    import aiohttp
                    session = aiohttp.ClientSession()

                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }
                update_url = "http://supervisor/network/interface/wlan0/update"
                body = {
                    "enabled": True,
                    "wifi": {
                        "mode": "infrastructure",
                        "auth": "open",
                        "ssid": camera_ssid,
                    },
                }
                async with session.post(update_url, json=body, headers=headers, timeout=8.0) as resp:
                    if resp.status in (200, 201):
                        self.add_log(f"📶 [SUPERVISOR WLAN] Interface wlan0 connectée à l'AP '{camera_ssid}' !")
                        return True
            except Exception as e:
                _LOGGER.debug("Supervisor bridge attempt failed: %s", e)

        # 2. Try host nmcli
        def _bridge() -> bool:
            try:
                out = subprocess.check_output(
                    ["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"],
                    timeout=3,
                    stderr=subprocess.DEVNULL,
                ).decode("utf-8", errors="ignore")
                wlan_dev = None
                for line in out.splitlines():
                    parts = line.strip().split(":")
                    if len(parts) >= 2 and parts[1] == "wifi" and "connected" not in parts[2]:
                        wlan_dev = parts[0]
                        break

                if not wlan_dev:
                    return False

                subprocess.run(
                    ["nmcli", "dev", "wifi", "connect", camera_ssid, "ifname", wlan_dev],
                    timeout=8,
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return True
            except Exception:
                return False

        try:
            return await self.hass.async_add_executor_job(_bridge)
        except Exception:
            return False

    def stop_pairing(self) -> None:
        """Cancel ongoing pairing process immediately."""
        self._is_pairing = False
        self._current_step = "cancelled"
        self.add_log("🛑 Assistant d'appairage arrêté par l'utilisateur.")

    async def async_start_pairing(
        self,
        ssid: str,
        password: str,
        camera_ap_ip: str = "192.168.1.1",
        camera_ssid: str | None = None,
    ) -> dict[str, Any]:
        """Execute autonomous Wi-Fi pairing routine."""
        self._is_pairing = True
        self._current_step = "sending_credentials"
        self._pairing_log = []
        self._discovered_devices = []

        self.add_log(f"🚀 Initialisation de l'assistant d'appairage Wi-Fi pour '{ssid}'...")
        self.add_log(f"📋 Paramètres : Longueur SSID={len(ssid)} car. | Longueur mot de passe={len(password)} car. | IP cible={camera_ap_ip}")

        # Warn only if camera_ap_ip is actually the Freebox / LAN gateway (e.g. 192.168.1.254)
        if camera_ap_ip in ("192.168.1.254", "192.168.0.254"):
            self.add_log(f"⚠️ AVERTISSEMENT : L'IP cible '{camera_ap_ip}' correspond à votre passerelle Freebox.")
            self.add_log("💡 En mode Point d'Accès d'usine, l'adresse de la caméra est généralement 192.168.1.1 ou 192.168.10.1.")

        try:
            # Step 1: Check for autonomous server-side Wi-Fi AP bridge
            bridged = await self._async_bridge_camera_ap(camera_ssid, ssid, password, camera_ap_ip)
            if bridged:
                self.add_log(f"📶 [PONT AUTONOME SERVEUR] Interface Wi-Fi connectée directement à l'AP '{camera_ssid}' !")

            # Step 2: Multi-vector transmission (UDP multi-payloads + HTTP CGI)
            self.add_log(f"📡 Transmission des identifiants vers la caméra ({camera_ap_ip}:32108 + 192.168.1.1 / 192.168.10.1)...")
            success = await self._send_wifi_config(camera_ap_ip, ssid, password)

            if success:
                self.add_log("✅ Trames UDP multi-formats (Big/Little-Endian, Struct 128B, iLnk) & requêtes CGI transmises !")
                self.add_log("🔄 La caméra enregistre les paramètres et redémarre pour rejoindre votre Wi-Fi...")
            else:
                self.add_log("⚠️ Émission UDP standard complétée. Diffusion broadcast étendue en cours...")

            # Step 3: Listen for camera connecting to local Wi-Fi with extended 72s timeout
            self._current_step = "waiting_connection"
            max_attempts = 18  # 18 * 4s = 72s
            for attempt in range(1, max_attempts + 1):
                if not self._is_pairing:
                    return {"success": False, "cancelled": True}

                self.add_log(f"🔍 [Écoute LAN {attempt}/{max_attempts}] Recherche de la caméra connectée sur le réseau...")
                await asyncio.sleep(4)

                if not self._is_pairing:
                    return {"success": False, "cancelled": True}

                scan_res = await self.async_scan_all_cameras(timeout=3.0)
                found = scan_res.get("compatible", [])
                # Only look for newly connected LAN cameras (host is an IP, not HA entity)
                new_cams = [d for d in found if not str(d.get("host", "")).startswith("camera.")]
                if new_cams:
                    self._discovered_devices = new_cams
                    self._current_step = "completed"
                    cam_name = new_cams[0].get("name", "Caméra Détectée")
                    cam_ip = new_cams[0].get("host", "")
                    self.add_log(f"🎉 CAMÉRA DÉTECTÉE SUR LE RÉSEAU : {cam_name} ({cam_ip}) !")
                    self.add_log("✅ Appairage terminé avec succès ! Vous pouvez l'ajouter à vos caméras.")
                    self._is_pairing = False
                    return {"success": True, "devices": new_cams}

            self._current_step = "timeout"
            self.add_log("❌ DÉLAI D'ATTENTE ATTEINT (72s) : La caméra n'a pas encore répondu sur le réseau local.")
            self.add_log("📋 VÉRIFICATIONS CONSEILLÉES :")
            self.add_log("  1. Fréquence Wi-Fi : Les caméras YsxLite/A9 requièrent une bande 2.4 GHz active sur la Freebox.")
            self.add_log("  2. Si votre appareil était sur le Wi-Fi de la caméra, reconnectez-le à votre Freebox et cliquez sur 'Scanner le réseau'.")
            self.add_log("  3. Vérifiez l'exactitude de la clé Wi-Fi saisie (sensible à la casse).")
            self._is_pairing = False
            return {"success": False, "devices": []}

        except Exception as err:
            _LOGGER.error("Pairing failure: %s", err)
            self._current_step = "error"
            self.add_log(f"❌ ERREUR SYSTÈME LORS DE L'APPAIRAGE : {err}")
            self._is_pairing = False
            return {"success": False, "error": str(err)}

    async def _send_wifi_config(self, ip: str, ssid: str, password: str) -> bool:
        """Send all SSID and password payload variants to camera in AP mode across candidate IPs."""
        # Also trigger HTTP CGI probes asynchronously
        for target in (ip, "192.168.1.1", "192.168.10.1", "192.168.1.254"):
            asyncio.create_task(self._send_http_cgi_wifi_config(target, ssid, password))

        def _send() -> bool:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(2.0)
            try:
                payloads = self.build_wifi_payloads(ssid, password)
                candidate_ips = [ip, "192.168.1.1", "192.168.10.1", "192.168.1.254", "255.255.255.255"]
                candidate_ips = list(dict.fromkeys(candidate_ips))

                for packet in payloads:
                    for target_ip in candidate_ips:
                        try:
                            sock.sendto(packet, (target_ip, DEFAULT_PPPP_DISCOVERY_PORT))
                        except Exception:
                            continue
                return True
            except Exception as e:
                _LOGGER.warning("Could not send direct AP packet: %s", e)
                return False
            finally:
                sock.close()

        return await self.hass.async_add_executor_job(_send)

