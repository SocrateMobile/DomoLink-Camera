"""Autonomous Wi-Fi Pairing and Discovery Engine for DomoLink Camera."""

from __future__ import annotations

import asyncio
import logging
import socket
import struct
from typing import Any

from .const import DEFAULT_PPPP_DISCOVERY_PORT, PPPP_CMD_DEV_SEARCH, PPPP_CMD_WIFI_SET, PPPP_MAGIC

_LOGGER = logging.getLogger(__name__)


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
        """Broadcast UDP discovery packets to discover online PPPP/YsxLite cameras."""
        discovered: list[dict[str, Any]] = []
        loop = asyncio.get_running_loop()

        def _broadcast_search() -> list[dict[str, Any]]:
            results = []
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(1.0)

            # Build PPPP discovery packet
            # Header: PPPP + Cmd(0x0009) + Length(0) + Seq(1)
            pkt = PPPP_MAGIC + struct.pack(">HHH", PPPP_CMD_DEV_SEARCH, 0, 1)

            broadcast_ips = ["255.255.255.255", "192.168.1.255", "192.168.0.255"]
            for b_ip in broadcast_ips:
                try:
                    sock.sendto(pkt, (b_ip, DEFAULT_PPPP_DISCOVERY_PORT))
                except Exception:
                    continue

            start_t = loop.time()
            while loop.time() - start_t < timeout:
                try:
                    data, addr = sock.recvfrom(2048)
                    host = addr[0]
                    # Parse device info if available
                    dev_id = f"CAM_{host.replace('.', '_')}"
                    if PPPP_MAGIC in data:
                        # Extract any readable serial number/id
                        raw_str = "".join([chr(b) for b in data if 32 <= b <= 126])
                        if len(raw_str) > 4:
                            dev_id = raw_str[:20].strip()

                    entry = {
                        "host": host,
                        "port": DEFAULT_PPPP_DISCOVERY_PORT,
                        "device_id": dev_id,
                        "driver": "ysxlite_pppp",
                        "model": "YsxLite / A9 Mini Wi-Fi",
                    }
                    if not any(d["host"] == host for d in results):
                        results.append(entry)
                except socket.timeout:
                    break
                except Exception as err:
                    _LOGGER.debug("Scan error: %s", err)
                    break

            sock.close()
            return results

        try:
            discovered = await self.hass.async_add_executor_job(_broadcast_search)
        except Exception as err:
            _LOGGER.error("LAN discovery error: %s", err)

        return discovered

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
                found = await self.async_scan_local_network(timeout=3.0)
                if found:
                    self._discovered_devices = found
                    self._current_step = "completed"
                    self._pairing_log.append(f"Caméra détectée avec succès : {found[0]['host']} !")
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
