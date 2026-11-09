"""Unit tests for DomoLink Camera Wi-Fi Pairing Engine."""

import asyncio
import os
import struct
import sys
from unittest.mock import AsyncMock, MagicMock, patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Mock homeassistant modules for offline testing
import types

ha_mods = [
    "homeassistant",
    "homeassistant.core",
    "homeassistant.components",
    "homeassistant.components.frontend",
    "homeassistant.components.http",
    "homeassistant.components.websocket_api",
    "homeassistant.components.camera",
    "homeassistant.config_entries",
    "homeassistant.helpers",
    "homeassistant.helpers.event",
    "homeassistant.helpers.entity_registry",
    "homeassistant.helpers.storage",
    "homeassistant.exceptions",
    "homeassistant.helpers.aiohttp_client",
]

for mod in ha_mods:
    if mod not in sys.modules:
        m = types.ModuleType(mod)
        sys.modules[mod] = m

# Mock Store and callback
sys.modules["homeassistant.helpers.storage"].Store = MagicMock()
sys.modules["homeassistant.helpers.aiohttp_client"].async_get_clientsession = MagicMock()
sys.modules["homeassistant.exceptions"].Unauthorized = type("Unauthorized", (Exception,), {})
sys.modules["homeassistant.core"].callback = lambda f: f
sys.modules["homeassistant.core"].HomeAssistant = MagicMock
sys.modules["homeassistant.config_entries"].ConfigEntry = MagicMock
sys.modules["homeassistant.components.http"].HomeAssistantView = MagicMock
sys.modules["homeassistant.components.websocket_api"].websocket_command = lambda schema: lambda f: f
sys.modules["homeassistant.components.websocket_api"].async_response = lambda f: f
sys.modules["homeassistant.components.websocket_api"].require_admin = lambda f: f
sys.modules["homeassistant.components.websocket_api"].ActiveConnection = MagicMock

import unittest

from custom_components.domolink_camera.const import (
    CAMERA_AP_SSID_PREFIXES,
    DEFAULT_PPPP_DISCOVERY_PORT,
    ILNK_MAGIC,
    PPPP_CMD_WIFI_SET,
    PPPP_MAGIC,
)
from custom_components.domolink_camera.pairing import WifiPairingEngine


class TestWifiPairingEngine(unittest.IsolatedAsyncioTestCase):
    """Test suite for WifiPairingEngine."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.mock_hass = MagicMock()
        self.mock_hass.data = {}
        # Make async_add_executor_job execute synchronously for unit testing
        async def _exec(func, *args):
            return func(*args)
        self.mock_hass.async_add_executor_job = _exec
        self.engine = WifiPairingEngine(self.mock_hass)

    def test_camera_ap_prefixes_and_wildcards(self) -> None:
        """Verify presence of known camera AP keywords and wildcard SSID matching."""
        from custom_components.domolink_camera.pairing import is_camera_ssid

        self.assertIn("AYS-", CAMERA_AP_SSID_PREFIXES)
        self.assertIn("ACCQ-", CAMERA_AP_SSID_PREFIXES)
        self.assertIn("A9-", CAMERA_AP_SSID_PREFIXES)
        self.assertIn("PTZ-", CAMERA_AP_SSID_PREFIXES)
        self.assertIn("V380", CAMERA_AP_SSID_PREFIXES)
        self.assertIn("TBAT", CAMERA_AP_SSID_PREFIXES)
        self.assertIn("BAT", CAMERA_AP_SSID_PREFIXES)

        # Test wildcard and regex matching for camera APs
        # 1. User's camera AP
        self.assertTrue(is_camera_ssid("TBAT652718GRDCE"))
        self.assertTrue(is_camera_ssid("BAT-123456"))
        self.assertTrue(is_camera_ssid("AYS-928172-ABCDE"))
        self.assertTrue(is_camera_ssid("ACCQ-33129"))
        self.assertTrue(is_camera_ssid("my_cam_BAT_test"))
        self.assertTrue(is_camera_ssid("CAM_HD_1080P"))

        # 2. Domestic routers and ISPs must be excluded
        self.assertFalse(is_camera_ssid("Freebox_Media_5G"))
        self.assertFalse(is_camera_ssid("Livebox-1234"))
        self.assertFalse(is_camera_ssid("SocrateFreeLan_Media"))
        self.assertFalse(is_camera_ssid("Bbox-A890"))
        self.assertFalse(is_camera_ssid("SFR_Wifi_Guest"))

    def test_build_wifi_payloads_all_formats(self) -> None:
        """Test generation of all 5 PPPP / YsxLite Wi-Fi pairing variants."""
        ssid = "SocrateFreeLan_Media"
        password = "SecretPassword123"

        payloads = self.engine.build_wifi_payloads(ssid, password)
        self.assertEqual(len(payloads), 5)

        # 1. Big-Endian PPPP packet
        p1 = payloads[0]
        self.assertTrue(p1.startswith(PPPP_MAGIC))
        cmd, length, seq = struct.unpack(">HHH", p1[4:10])
        self.assertEqual(cmd, PPPP_CMD_WIFI_SET)
        self.assertEqual(seq, 1)
        self.assertEqual(length, len(p1[10:]))
        # Check SSID len & bytes
        self.assertEqual(p1[10], len(ssid))
        self.assertIn(ssid.encode("utf-8"), p1)
        self.assertIn(password.encode("utf-8"), p1)

        # 2. Little-Endian variant
        p2 = payloads[1]
        self.assertTrue(p2.startswith(PPPP_MAGIC))
        cmd_le, length_le, seq_le = struct.unpack("<HHH", p2[4:10])
        self.assertEqual(cmd_le, PPPP_CMD_WIFI_SET)

        # 3. Fixed 128-byte C-struct
        p3 = payloads[2]
        self.assertTrue(p3.startswith(PPPP_MAGIC))
        cmd_fixed, length_fixed, _ = struct.unpack(">HHH", p3[4:10])
        self.assertEqual(cmd_fixed, PPPP_CMD_WIFI_SET)
        self.assertEqual(length_fixed, 128)
        self.assertEqual(len(p3[10:]), 128)

        # 4. iLnk header variant
        p4 = payloads[3]
        self.assertTrue(p4.startswith(ILNK_MAGIC))

        # 5. Null-terminated JSON string
        p5 = payloads[4]
        self.assertTrue(p5.endswith(b"\x00"))
        self.assertIn(b'"ssid":"SocrateFreeLan_Media"', p5)

    @patch("subprocess.check_output")
    async def test_scan_camera_aps_filtering(self, mock_subp) -> None:
        """Test identification and sorting of camera APs from Wi-Fi scan."""
        # Simulated nmcli output: SSID:SIGNAL:SECURITY
        mock_subp.return_value = (
            "Livebox-1234:80:WPA2\n"
            "AYS-928172-ABCDE:88:OPEN\n"
            "SocrateFreeLan_Media:95:WPA2\n"
            "ACCQ-33129:72:NONE\n"
        ).encode("utf-8")

        aps = await self.engine.async_scan_camera_aps()
        self.assertTrue(len(aps) >= 2)

        # The camera APs should be flagged and sorted first
        first = aps[0]
        self.assertTrue(first["is_camera"])
        self.assertTrue(first["ssid"].startswith(("AYS-", "ACCQ-")))

    def test_stop_pairing_immediately(self) -> None:
        """Test stopping the pairing engine resets flags."""
        self.engine._is_pairing = True
        self.engine.stop_pairing()
        self.assertFalse(self.engine.is_pairing)
        status = self.engine.get_status()
        self.assertFalse(status["active"])
        self.assertEqual(status["step"], "cancelled")

    @patch.dict("os.environ", {"SUPERVISOR_TOKEN": "mock_supervisor_token"})
    async def test_supervisor_wlan0_scanning(self) -> None:
        """Test scanning APs via HAOS Supervisor API with wildcard camera detection."""
        from unittest.mock import AsyncMock

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.json = AsyncMock(return_value={
            "result": "ok",
            "data": {
                "accesspoints": [
                    {"ssid": "TBAT652718GRDCE", "signal": 85, "security": "open"},
                    {"ssid": "SocrateFreeLan_Media", "signal": 95, "security": "wpa2"},
                    {"ssid": "AYS-12345", "signal": 70, "security": "open"},
                ]
            }
        })

        mock_session = MagicMock()
        mock_session.get.return_value.__aenter__.return_value = mock_resp
        mock_session.post.return_value.__aenter__.return_value = mock_resp

        with patch("custom_components.domolink_camera.pairing.os.environ.get", return_value="mock_token"):
            self.mock_hass.helpers.aiohttp_client.async_get_clientsession.return_value = mock_session
            aps = await self.engine.async_scan_camera_aps()
            self.assertTrue(len(aps) >= 2)
            # The detected camera APs must be flagged is_camera = True
            cams = [ap for ap in aps if ap["is_camera"]]
            cam_ssids = [c["ssid"] for c in cams]
            self.assertIn("TBAT652718GRDCE", cam_ssids)
            self.assertIn("AYS-12345", cam_ssids)
            self.assertNotIn("SocrateFreeLan_Media", [c["ssid"] for c in cams])

    @patch("socket.socket")
    async def test_send_wifi_config_multi_target(self, mock_sock_cls) -> None:
        """Test multi-target dispatch of UDP payloads across candidate IPs."""
        mock_sock = MagicMock()
        mock_sock_cls.return_value = mock_sock

        with patch.object(self.engine, "_send_http_cgi_wifi_config", new_callable=AsyncMock) as mock_cgi:
            success = await self.engine._send_wifi_config("192.168.1.1", "TestSSID", "TestPass")
            self.assertTrue(success)
            self.assertTrue(mock_sock.sendto.called)

            # Check candidate IP targets were hit
            called_addrs = [call[0][1] for call in mock_sock.sendto.call_args_list]
            dest_ips = {addr[0] for addr in called_addrs}
            self.assertIn("192.168.1.1", dest_ips)
            self.assertIn("192.168.10.1", dest_ips)
            self.assertIn("255.255.255.255", dest_ips)


if __name__ == "__main__":
    unittest.main()
