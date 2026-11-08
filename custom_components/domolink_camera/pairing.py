"""Autonomous Wi-Fi Pairing and Discovery Engine for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import re
import socket
import struct
import subprocess
from typing import Any

from .const import (
    DEFAULT_PPPP_DISCOVERY_PORT,
    DOMAIN,
    DRIVER_GENERIC_MJPEG,
    DRIVER_GENERIC_RTSP,
    DRIVER_YSXLITE_PPPP,
    PPPP_CMD_DEV_SEARCH,
    PPPP_CMD_WIFI_SET,
    PPPP_MAGIC,
)

_LOGGER = logging.getLogger(__name__)

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

    def get_status(self) -> dict[str, Any]:
        """Return pairing status snapshot."""
        return {
            "active": self._is_pairing,
            "step": self._current_step,
            "logs": self._pairing_log[-10:],
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

        # 2. Collect candidate LAN IPs from ARP table
        def _get_candidate_ips() -> set[str]:
            ips = set()
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

            return ips

        try:
            candidate_ips = await self.hass.async_add_executor_job(_get_candidate_ips)
        except Exception:
            candidate_ips = set()

        # 3. Concurrent TCP port probing on candidate IPs (RTSP 554, 8554)
        async def _probe_ip(ip: str) -> dict[str, Any] | None:
            # Skip if already found via PPPP
            if any(d["host"] == ip for d in compatible_found):
                return None

            # Test RTSP port 554
            for port in (554, 8554):
                try:
                    _, writer = await asyncio.wait_for(
                        asyncio.open_connection(ip, port), timeout=0.35
                    )
                    writer.close()
                    await writer.wait_closed()
                    return {
                        "host": ip,
                        "port": port,
                        "device_id": f"RTSP_{ip.replace('.', '_')}_{port}",
                        "name": f"Caméra IP / RTSP ({ip})",
                        "driver": DRIVER_GENERIC_RTSP,
                        "protocol": f"RTSP Standard (Port {port})",
                        "model": "Generic RTSP / ONVIF IP Camera",
                        "details": f"Serveur RTSP actif détecté sur le port {port} - Compatible flux direct H.264/RTSP",
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

                # Check if known compatible
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
                # Check if known incompatible / proprietary / cloud
                elif platform in KNOWN_INCOMPATIBLE_PLATFORMS:
                    info = KNOWN_INCOMPATIBLE_PLATFORMS[platform]
                    incompatible.append({
                        "entity_id": eid,
                        "name": friendly_name,
                        "platform": info["platform_name"],
                        "protocol": info["protocol"],
                        "model": model,
                        "reason": info["reason"],
                        "compatible": False,
                        "details": f"Gérée par l'intégration '{platform}'",
                    })
                else:
                    # Unknown or generic platform
                    incompatible.append({
                        "entity_id": eid,
                        "name": friendly_name,
                        "platform": platform.capitalize(),
                        "protocol": f"Intégration {platform}",
                        "model": model,
                        "reason": f"Protocole géré par '{platform}'. Pour l'intégrer en direct dans DomoLink, vérifiez si un flux local RTSP ou MJPEG est exposé.",
                        "compatible": False,
                        "details": f"Plateforme: {platform}",
                    })

        except Exception as e:
            _LOGGER.error("Error inspecting HA camera entities: %s", e)

        return compatible, incompatible

    async def async_start_pairing(self, ssid: str, password: str, camera_ap_ip: str = "192.168.1.254") -> dict[str, Any]:
        """Execute autonomous Wi-Fi pairing routine."""
        self._is_pairing = True
        self._current_step = "sending_credentials"
        self._pairing_log = [f"Démarrage de l'appairage pour le réseau Wi-Fi '{ssid}'..."]
        self._discovered_devices = []

        try:
            # Step 1: Send Wi-Fi credentials to camera AP
            self._pairing_log.append(f"Transmission des identifiants vers la caméra ({camera_ap_ip}:32108)...")
            success = await self._send_wifi_config(camera_ap_ip, ssid, password)

            if success:
                self._pairing_log.append("Identifiants transmis ! En attente de redémarrage de la caméra...")
            else:
                self._pairing_log.append("Envoi initial UDP terminé. Scan actif en cours...")

            # Step 2: Listen for camera connecting to local Wi-Fi
            self._current_step = "waiting_connection"
            for attempt in range(1, 7):
                self._pairing_log.append(f"Recherche de la nouvelle caméra sur le réseau local (tentative {attempt}/6)...")
                await asyncio.sleep(4)
                scan_res = await self.async_scan_all_cameras(timeout=3.0)
                found = scan_res.get("compatible", [])
                if found:
                    self._discovered_devices = found
                    self._current_step = "completed"
                    self._pairing_log.append(f"Caméra détectée avec succès : {found[0].get('host', found[0].get('name'))} !")
                    self._is_pairing = False
                    return {"success": True, "devices": found}

            self._current_step = "timeout"
            self._pairing_log.append("Délai dépassé. Si la caméra a clignoté, vérifiez son IP sur votre box.")
            self._is_pairing = False
            return {"success": False, "devices": []}

        except Exception as err:
            _LOGGER.error("Pairing failure: %s", err)
            self._current_step = "error"
            self._pairing_log.append(f"Erreur lors de l'appairage: {err}")
            self._is_pairing = False
            return {"success": False, "error": str(err)}

    async def _send_wifi_config(self, ip: str, ssid: str, password: str) -> bool:
        """Send SSID and password payload to camera in AP mode."""
        def _send() -> bool:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2.0)
            try:
                # Format: [SSID_LEN (1B)] + SSID + [PASS_LEN (1B)] + PASS
                s_bytes = ssid.encode("utf-8")
                p_bytes = password.encode("utf-8")
                payload = struct.pack("B", len(s_bytes)) + s_bytes + struct.pack("B", len(p_bytes)) + p_bytes

                packet = PPPP_MAGIC + struct.pack(">HHH", PPPP_CMD_WIFI_SET, len(payload), 1) + payload
                # Send to target AP IP and broadcast fallback
                sock.sendto(packet, (ip, DEFAULT_PPPP_DISCOVERY_PORT))
                sock.sendto(packet, ("192.168.16.101", DEFAULT_PPPP_DISCOVERY_PORT))
                return True
            except Exception as e:
                _LOGGER.warning("Could not send direct AP packet: %s", e)
                return False
            finally:
                sock.close()

        return await self.hass.async_add_executor_job(_send)

