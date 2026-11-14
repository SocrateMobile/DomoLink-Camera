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
    DRIVER_ARLO_CLOUD,
    DRIVER_GENERIC_MJPEG,
    DRIVER_HA_PROXY,
    ILNK_MAGIC,
    MAX_UDP_FRAME_BUFFER,
    PPPP_CMD_WIFI_SET,
    PPPP_MAGIC,
)
from custom_components.domolink_camera.drivers.arlo_cloud import (
    ArloCloudAccountSession,
    ArloCloudDriver,
    normalize_arlo_device,
)
from custom_components.domolink_camera.drivers.generic_rtsp import GenericRtspDriver
from custom_components.domolink_camera.drivers.ha_proxy import HaProxyDriver
from custom_components.domolink_camera.drivers.ysxlite_pppp import YsxLiteDriver
from custom_components.domolink_camera.manager import CameraManager
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

    async def test_scan_ha_entities_keeps_numbered_and_unavailable_cameras(self) -> None:
        """Verify numbered HA cameras are not filtered out and use ha_proxy."""
        s1 = MagicMock(entity_id="camera.cam_1", state="idle", attributes={"friendly_name": "Cam 1", "platform": "onvif"})
        s2 = MagicMock(entity_id="camera.tapo_c200_1", state="unavailable", attributes={"friendly_name": "Tapo 1", "platform": "tplink"})
        s3 = MagicMock(entity_id="camera.salon", state="idle", attributes={"friendly_name": "Salon", "platform": "generic"})
        s4 = MagicMock(entity_id="camera.salon_2", state="idle", attributes={"friendly_name": "Salon Mirror", "platform": "remote_homeassistant"})
        s5 = MagicMock(entity_id="camera.jardin_2_2", state="idle", attributes={"friendly_name": "Jardin Dup", "platform": "remote_homeassistant"})

        self.mock_hass.states.async_all.return_value = [s1, s2, s3, s4, s5]
        self.mock_hass.data["entity_registry"] = MagicMock(entities={})

        compatible, incompatible = await self.engine._scan_ha_camera_entities()
        ids = {c["device_id"] for c in compatible}

        self.assertIn("camera.cam_1", ids)
        self.assertIn("camera.tapo_c200_1", ids)
        self.assertIn("camera.salon", ids)
        self.assertNotIn("camera.salon_2", ids)
        self.assertNotIn("camera.jardin_2_2", ids)
        self.assertEqual(incompatible, [])
        for cam in compatible:
            self.assertEqual(cam["driver"], DRIVER_HA_PROXY)

    async def test_ysxlite_udp_reassembly_and_multi_subscriber_fanout(self) -> None:
        """Verify multi-packet UDP JPEG reassembly (raw/ILNK/PPPP) and multi-client callbacks."""
        driver = YsxLiteDriver("cam_test", {"host": "192.168.1.50", "port": 32108})
        driver.async_start_stream = AsyncMock(side_effect=lambda: setattr(driver, "is_streaming", True))
        driver.async_stop_stream = AsyncMock(side_effect=lambda: setattr(driver, "is_streaming", False))

        sub1_frames = []
        sub2_frames = []
        driver.subscribe_frames(sub1_frames.append)
        driver.subscribe_frames(sub2_frames.append)

        await driver.async_acquire_stream()
        await driver.async_acquire_stream()
        self.assertEqual(driver._stream_clients, 2)
        driver.async_start_stream.assert_awaited_once()

        # Fragment 1: PPPP header + JPEG SOI + body
        part1_body = b"\xff\xd8\xff\xe0" + b"A" * 80
        pkt1 = PPPP_MAGIC + struct.pack(">HHH", 0x0001, len(part1_body), 1) + part1_body
        # Fragment 2: raw continuation UDP datagram (no header)
        pkt2 = b"B" * 60
        # Fragment 3: iLnk 8-byte header + tail + JPEG EOI
        part3_body = b"C" * 40 + b"\xff\xd9"
        pkt3 = ILNK_MAGIC + struct.pack(">HH", 0x0001, len(part3_body)) + part3_body

        driver.handle_udp_packet(pkt1, ("192.168.1.50", 32108))
        driver.handle_udp_packet(pkt2, ("192.168.1.50", 32108))
        driver.handle_udp_packet(pkt3, ("192.168.1.50", 32108))

        self.assertEqual(len(sub1_frames), 1)
        self.assertEqual(len(sub2_frames), 1)
        self.assertTrue(sub1_frames[0].startswith(b"\xff\xd8"))
        self.assertTrue(sub1_frames[0].endswith(b"\xff\xd9"))
        self.assertEqual(sub1_frames[0], part1_body + pkt2 + part3_body)

        # Oversized corrupt frame buffer resets safely
        driver.handle_udp_packet(b"\xff\xd8" + b"X" * (MAX_UDP_FRAME_BUFFER + 10), ("192.168.1.50", 32108))
        self.assertEqual(len(driver._frame_buffer), 0)
        self.assertFalse(driver._is_receiving_frame)

        # Releasing 1 of 2 clients keeps stream alive; releasing 2nd stops it
        driver.unsubscribe_frames(sub1_frames.append)
        await driver.async_release_stream()
        self.assertEqual(driver._stream_clients, 1)
        driver.async_stop_stream.assert_not_awaited()

        driver.unsubscribe_frames(sub2_frames.append)
        await driver.async_release_stream()
        self.assertEqual(driver._stream_clients, 0)
        driver.async_stop_stream.assert_awaited_once()

    async def test_generic_rtsp_ha_delegation_and_manager_mjpeg_driver(self) -> None:
        """Verify GenericRtspDriver delegates camera.* hosts and CameraManager routes MJPEG."""
        rtsp_with_entity = GenericRtspDriver(
            "cam_ent", {"host": "camera.entree_1", "driver": "generic_rtsp"}, hass=self.mock_hass
        )
        self.assertIsNotNone(rtsp_with_entity._ha_delegate)

        fake_jpeg = b"\xff\xd8\xff\xe0" + b"Z" * 150 + b"\xff\xd9"
        rtsp_with_entity._ha_delegate.async_get_snapshot = AsyncMock(return_value=fake_jpeg)
        snap = await rtsp_with_entity.async_get_snapshot()
        self.assertEqual(snap, fake_jpeg)

        mgr = CameraManager(self.mock_hass)
        mjpeg_drv = mgr._init_driver(
            "cam_esp",
            {"id": "cam_esp", "driver": DRIVER_GENERIC_MJPEG, "host": "192.168.1.90", "http_port": 81, "stream_path": "/stream"},
        )
        self.assertIsInstance(mjpeg_drv, GenericRtspDriver)
        self.assertEqual(mjpeg_drv.primary_stream_url, "http://192.168.1.90:81/stream")

    def test_arlo_device_normalization_and_rtsps_ffmpeg_attempts(self) -> None:
        """Verify Arlo raw device parsing filters non-cameras and BaseCameraDriver builds RTSPS args."""
        raw_base = {"deviceId": "BASE123", "deviceType": "basestation", "deviceName": "SmartHub"}
        self.assertIsNone(normalize_arlo_device(raw_base, "acc_1", "a@b.com"))

        raw_cam = {
            "deviceId": "ARLOCAM01",
            "parentId": "BASE123",
            "deviceType": "camera",
            "deviceName": "Jardin Pro 4",
            "modelId": "VMC4041P",
            "xCloudId": "XCL-99",
            "presignedLastImageUrl": "https://s3.example.com/last.jpg",
            "properties": {"batteryLevel": 82, "signalStrength": 3},
        }
        norm = normalize_arlo_device(raw_cam, "acc_1", "a@b.com")
        self.assertIsNotNone(norm)
        self.assertEqual(norm["device_id"], "ARLOCAM01")
        self.assertEqual(norm["parent_id"], "BASE123")
        self.assertEqual(norm["battery_level"], 82)
        self.assertEqual(norm["xcloud_id"], "XCL-99")

        drv = HaProxyDriver("c_arlo", {"host": "camera.arlo_jardin", "entity_id": "camera.arlo_jardin"}, hass=self.mock_hass)
        attempts = drv._ffmpeg_input_attempts("rtsps://vzwow01.arlo.com:443/vzmodulelive?egressToken=abc")
        self.assertEqual(attempts[0][0], "tcp_noverify")
        self.assertIn("-tls_verify", attempts[0][1])
        self.assertIn("tcp", attempts[0][1])
        self.assertEqual(attempts[1][0], "tcp")

        # Relative HA HLS URL resolves safely to local HA URL
        self.assertEqual(
            drv._resolve_local_ha_url("/api/hls/tok123/master_playlist.m3u8"),
            "http://127.0.0.1:8123/api/hls/tok123/master_playlist.m3u8",
        )

    async def test_arlo_2fa_flow_and_battery_safe_driver(self) -> None:
        """Test Arlo 2FA authentication steps and passive snapshot/on-demand RTSPS lifecycle."""
        sess = ArloCloudAccountSession("arlo_1", "user@example.com", name="Maison")

        async def fake_post(url, payload, headers):
            if url.endswith("/api/auth"):
                return 200, {"meta": {"code": 200}, "data": {"token": "TMP_TOK", "userId": "USR1"}}, "{}"
            if url.endswith("/api/startAuth"):
                self.assertEqual(payload["factorId"], "FACT_EMAIL")
                return 200, {"meta": {"code": 200}, "data": {"factorAuthCode": "FAC_99"}}, "{}"
            if url.endswith("/api/finishAuth"):
                self.assertEqual(payload["otp"], "654321")
                return 200, {"meta": {"code": 200}, "data": {"token": "FINAL_TOK", "userId": "USR1"}}, "{}"
            return 404, {}, "{}"

        async def fake_get(url, headers):
            if "/api/getFactors" in url:
                return 200, {"meta": {"code": 200}, "data": {"items": [{"factorId": "FACT_EMAIL", "factorType": "EMAIL", "displayName": "u***@example.com"}]}}, "{}"
            if "/hmsweb/v2/users/devices" in url:
                return 200, {
                    "success": True,
                    "data": [{
                        "deviceId": "DEV_FRONT",
                        "parentId": "BASE_1",
                        "deviceType": "doorbell",
                        "deviceName": "Sonnette Entrée",
                        "modelId": "AVD2001",
                        "xCloudId": "XC1",
                        "presignedLastImageUrl": "https://s3.example.com/doorbell.jpg",
                        "properties": {"batteryLevel": 76, "signalStrength": 4},
                    }],
                }, "{}"
            return 404, {}, "{}"

        sess._post_json = AsyncMock(side_effect=fake_post)
        sess._get_json = AsyncMock(side_effect=fake_get)

        login_res = await sess.async_start_login("MySecretPass!")
        self.assertEqual(login_res["status"], "2fa_required")
        self.assertEqual(len(login_res["factors"]), 1)

        otp_req = await sess.async_request_2fa_code("FACT_EMAIL")
        self.assertEqual(otp_req["status"], "code_sent")

        verify_res = await sess.async_verify_2fa_code("654321")
        self.assertEqual(verify_res["status"], "connected")
        self.assertEqual(sess.token, "FINAL_TOK")
        self.assertEqual(len(sess.devices), 1)

        # Battery-safe driver: async_connect fetches presigned image, never calls startStream
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"J" * 160 + b"\xff\xd9"
        driver = ArloCloudDriver(
            "cam_arlo_doorbell",
            {
                "id": "cam_arlo_doorbell",
                "driver": DRIVER_ARLO_CLOUD,
                "arlo_account_id": "arlo_1",
                "arlo_device_id": "DEV_FRONT",
                "parent_id": "BASE_1",
                "xcloud_id": "XC1",
            },
            hass=self.mock_hass,
            account_session=sess,
        )
        driver._download_presigned_image = AsyncMock(return_value=fake_jpeg)
        sess.async_start_camera_stream = AsyncMock(return_value="rtsps://vzwow.arlo.com:443/vzmodulelive")
        sess.async_stop_camera_stream = AsyncMock()

        ok = await driver.async_connect()
        self.assertTrue(ok)
        self.assertEqual(driver.last_snapshot, fake_jpeg)
        sess.async_start_camera_stream.assert_not_awaited()

        caps = driver.get_capabilities()
        self.assertEqual(caps["driver_type"], DRIVER_ARLO_CLOUD)
        self.assertEqual(caps["battery_level"], 76)
        self.assertTrue(caps["battery_protected_mode"])

        # On-demand RTSPS live stream starts and calls stopStream when closed
        driver.async_stream_ffmpeg_mjpeg = AsyncMock(return_value=True)
        await driver.async_start_stream()
        await asyncio.sleep(0.05)
        sess.async_start_camera_stream.assert_awaited()
        await driver.async_stop_stream()
        sess.async_stop_camera_stream.assert_awaited()

    async def test_manager_multi_account_arlo_persistence_and_sync(self) -> None:
        """Verify CameraManager handles multiple Arlo accounts, persists data, and deletes cleanly."""
        self.mock_hass.states.async_all.return_value = [
            MagicMock(
                entity_id="camera.aarlo_terrasse",
                state="idle",
                attributes={"friendly_name": "Terrasse", "brand": "Arlo", "battery_level": 64},
            )
        ]
        mgr = CameraManager(self.mock_hass)
        mgr.store.async_save = AsyncMock()
        mgr.store.async_load = AsyncMock(return_value=None)

        async def mock_get_json(session_self, url, headers):
            if headers.get("Authorization") == "TOK_1":
                return 200, {
                    "success": True,
                    "data": [{
                        "deviceId": "DEV_A1",
                        "parentId": "BASE_A",
                        "deviceType": "camera",
                        "deviceName": "Terrasse",
                        "modelId": "VMC5040",
                        "xCloudId": "XCA",
                        "properties": {"batteryLevel": 91, "signalStrength": 4},
                    }],
                }, "{}"
            return 200, {
                "success": True,
                "data": [{
                    "deviceId": "DEV_B1",
                    "parentId": "BASE_B",
                    "deviceType": "camera",
                    "deviceName": "Entrepot",
                    "modelId": "VMC4030P",
                    "xCloudId": "XCB",
                    "properties": {"batteryLevel": 48, "signalStrength": 3},
                }],
            }, "{}"

        with patch.object(
            ArloCloudAccountSession,
            "_get_json",
            autospec=True,
            side_effect=mock_get_json,
        ), patch.object(ArloCloudDriver, "async_connect", return_value=True):
            res1 = await mgr.async_arlo_save_token(
                email="maison@example.com",
                token="Bearer TOK_1",
                account_name="Maison",
            )
            res2 = await mgr.async_arlo_save_token(
                email="bureau@example.com",
                token="TOK_2",
                account_name="Bureau",
            )

        self.assertEqual(res1["status"], "connected")
        self.assertEqual(res2["status"], "connected")
        self.assertEqual(len(mgr.arlo_sessions), 2)
        self.assertEqual(len(mgr.cameras), 2)

        # Verify hybrid HA entity auto-linking on DEV_A1 ("Terrasse" -> camera.aarlo_terrasse)
        cam_a = next(c for c in mgr.cameras.values() if c.get("arlo_device_id") == "DEV_A1")
        self.assertEqual(cam_a["ha_entity_id"], "camera.aarlo_terrasse")
        self.assertEqual(cam_a["driver"], DRIVER_ARLO_CLOUD)
        self.assertIsInstance(mgr.drivers[cam_a["id"]], ArloCloudDriver)

        # Verify store save received both arlo_accounts and cameras
        last_saved = mgr.store.async_save.call_args.args[0]
        self.assertEqual(len(last_saved["arlo_accounts"]), 2)
        self.assertEqual(len(last_saved["cameras"]), 2)

        # Delete second account along with its cameras
        acc2_id = res2["account"]["id"]
        deleted = await mgr.async_arlo_delete_account(acc2_id, delete_cameras=True)
        self.assertTrue(deleted)
        self.assertEqual(len(mgr.arlo_sessions), 1)
        self.assertEqual(len(mgr.cameras), 1)

    async def test_ysxlite_concurrent_snapshot_deduplication(self) -> None:
        """Verify concurrent YsxLite async_get_snapshot calls share one pending future."""
        drv = YsxLiteDriver("cam_ysx", {"host": "192.168.1.77", "port": 32108})
        drv.is_connected = True
        drv._send_pppp_cmd = AsyncMock()
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"Y" * 140 + b"\xff\xd9"

        async def resolve_soon():
            await asyncio.sleep(0.03)
            drv._update_frame(fake_jpeg)

        t1 = asyncio.create_task(drv.async_get_snapshot())
        t2 = asyncio.create_task(drv.async_get_snapshot())
        t3 = asyncio.create_task(resolve_soon())
        r1, r2, _ = await asyncio.gather(t1, t2, t3)

        self.assertEqual(r1, fake_jpeg)
        self.assertEqual(r2, fake_jpeg)
        # Only one UDP snapshot request should have been dispatched for both waiters
        drv._send_pppp_cmd.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
