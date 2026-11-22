"""Security, manifest, and non-regression tests for DomoLink-Camera."""
import json
import os
import ast
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPONENT_DIR = os.path.join(REPO_ROOT, "custom_components", "domolink_camera")


def test_manifest_structure_and_version():
    """Verify manifest.json has properly sorted keys and valid URLs."""
    manifest_path = os.path.join(COMPONENT_DIR, "manifest.json")
    assert os.path.isfile(manifest_path)
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["domain"] == "domolink_camera"
    assert manifest["name"] == "DomoLink Camera"
    assert manifest["version"] == "1.8.0"
    assert manifest["codeowners"] == ["@SocrateMobile"]
    assert "socratemobile" in manifest["documentation"].lower()
    assert "SocrateMobile" in manifest["issue_tracker"]

    # Verify keys are sorted: domain, name, then alphabetical
    keys = list(manifest.keys())
    assert keys[0] == "domain"
    assert keys[1] == "name"
    assert keys[2:] == sorted(keys[2:]), f"Manifest keys not sorted: {keys[2:]}"


def test_translations_parity():
    """Verify fr.json and en.json exist and match keys perfectly."""
    fr_path = os.path.join(COMPONENT_DIR, "translations", "fr.json")
    en_path = os.path.join(COMPONENT_DIR, "translations", "en.json")
    assert os.path.isfile(fr_path), "translations/fr.json must exist"
    assert os.path.isfile(en_path), "translations/en.json must exist"

    with open(fr_path, "r", encoding="utf-8") as f:
        fr = json.load(f)
    with open(en_path, "r", encoding="utf-8") as f:
        en = json.load(f)

    def extract_keys(d, prefix=""):
        keys = set()
        for k, v in d.items():
            full = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                keys.update(extract_keys(v, full))
            else:
                keys.add(full)
        return keys

    fr_keys = extract_keys(fr)
    en_keys = extract_keys(en)
    assert fr_keys == en_keys, f"Translation keys mismatch: {fr_keys ^ en_keys}"


def test_views_require_auth_and_admin_checks():
    """Verify all HTTP views have requires_auth = True and check user."""
    api_path = os.path.join(COMPONENT_DIR, "api.py")
    with open(api_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=api_path)

    views = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for base in node.bases:
                base_name = getattr(base, "id", getattr(base, "attr", None))
                if base_name == "HomeAssistantView":
                    requires_auth = None
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if getattr(target, "id", None) == "requires_auth":
                                    if isinstance(item.value, ast.Constant):
                                        requires_auth = item.value.value
                    views[node.name] = requires_auth

    assert len(views) == 3, f"Expected 3 views, found {len(views)}: {list(views.keys())}"
    assert "DomolinkTvProxyView" not in views
    for view_name, req_auth in views.items():
        assert req_auth is True, f"View {view_name} must have requires_auth = True (found {req_auth})"


def test_no_direct_blocking_io_in_async_functions():
    """Verify no blocking calls directly inside async def."""
    blocking_calls = {"open", "check_output", "urlopen"}
    violations = []

    def check_node(node):
        if isinstance(node, (ast.FunctionDef, ast.Lambda)):
            return
        if isinstance(node, ast.AsyncFunctionDef):
            for child in node.body:
                check_async_body(child, node.name, file)
            return

        for child in ast.iter_child_nodes(node):
            check_node(child)

    def check_async_body(node, func_name, file_name):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            return
        if isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in blocking_calls:
                violations.append((file_name, func_name, name, node.lineno))

        for child in ast.iter_child_nodes(node):
            check_async_body(child, func_name, file_name)

    for root, _, files in os.walk(COMPONENT_DIR):
        for file in files:
            if not file.endswith(".py"):
                continue
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
            for item in tree.body:
                check_node(item)

    assert not violations, f"Blocking calls found: {violations}"


def test_local_hls_bundle_and_no_cdn_urls():
    """Verify hls.min.js is bundled locally and no CDN script URLs exist in panel JS."""
    hls_path = os.path.join(COMPONENT_DIR, "frontend", "hls.min.js")
    assert os.path.isfile(hls_path), "frontend/hls.min.js must be bundled locally"
    assert os.path.getsize(hls_path) > 50_000, "hls.min.js appears incomplete"

    panel_path = os.path.join(COMPONENT_DIR, "frontend", "domolink-camera-panel.js")
    with open(panel_path, "r", encoding="utf-8") as f:
        panel_js = f.read()

    assert "cdn.jsdelivr.net" not in panel_js
    assert "/domolink_camera_panel/hls.min.js" in panel_js
    assert 'onerror="' not in panel_js


def test_no_pickle_storage_or_obfuscation():
    """Verify removal of pickle.load, third-party .storage reads, and _d() obfuscation."""
    forbidden_patterns = (
        "pickle.load",
        ".storage/core.config_entries",
        ".storage/xiaomi_miot",
        ".storage/domolink_tuya_oem_overrides",
        "def _d(",
        "DomolinkTvProxyView",
    )
    for root, _, files in os.walk(COMPONENT_DIR):
        for file in files:
            if not file.endswith(".py"):
                continue
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            for pat in forbidden_patterns:
                assert pat not in content, f"Forbidden pattern '{pat}' found in {path}"


def test_all_websocket_commands_require_admin():
    """Verify every WebSocket command in api.py has @websocket_api.require_admin."""
    api_path = os.path.join(COMPONENT_DIR, "api.py")
    with open(api_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=api_path)

    ws_funcs = []
    missing_admin = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("ws_"):
            ws_funcs.append(node.name)
            dec_names = []
            for dec in node.decorator_list:
                if isinstance(dec, ast.Attribute):
                    dec_names.append(dec.attr)
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    dec_names.append(dec.func.attr)
            if "require_admin" not in dec_names:
                missing_admin.append(node.name)

    assert len(ws_funcs) >= 20, f"Expected >=20 ws_* handlers, found {len(ws_funcs)}"
    assert not missing_admin, f"WS handlers missing @require_admin: {missing_admin}"


def test_secret_sanitization_and_pairing_validation():
    """Verify secrets are stripped from public payloads and pairing validates SSID/IP."""
    from unittest.mock import MagicMock
    import tests.test_pairing  # noqa: F401 - initializes HA module stubs
    from custom_components.domolink_camera.manager import _sanitize_camera_public
    from custom_components.domolink_camera.drivers.cloud_accounts import ProviderAccountSession
    from custom_components.domolink_camera.pairing import _validate_camera_ssid, _validate_private_ap_ip

    sanitized = _sanitize_camera_public({
        "id": "cam1",
        "name": "Front",
        "password": "my_secret_password",
        "local_key": "secret_tuya_key",
        "verification_code": "ABCDEF",
        "access_token": "tok_123",
        "stream_url": "rtsp://admin:my_secret_password@192.168.1.50:554/stream1",
    })
    for key in ("password", "local_key", "verification_code", "access_token"):
        assert key not in sanitized
    assert "my_secret_password" not in sanitized["stream_url"]
    assert "***:***@" in sanitized["stream_url"]

    sess = ProviderAccountSession(
        account_id="p1",
        provider="ezviz",
        devices=[{"device_id": "d1", "local_key": "k1", "verification_code": "V1", "rtsp_url": "rtsp://u:p@192.168.1.10/h264"}],
        hass=MagicMock(),
    )
    pub = sess.to_public_dict()
    assert "local_key" not in pub["devices"][0]
    assert "verification_code" not in pub["devices"][0]
    assert "u:p@" not in pub["devices"][0]["rtsp_url"]

    assert _validate_camera_ssid("AYS-123456") == "AYS-123456"
    assert _validate_camera_ssid("-malicious") is None
    assert _validate_camera_ssid("bad\nssid") is None
    assert _validate_private_ap_ip("192.168.1.1") == "192.168.1.1"
    for bad_ip in ("127.0.0.1", "169.254.169.254", "8.8.8.8", "not-an-ip"):
        with pytest.raises(ValueError):
            _validate_private_ap_ip(bad_ip)


def test_options_flow_no_arg_instantiation():
    """Verify DomoLinkCameraOptionsFlow instantiates without config_entry argument."""
    import sys
    from unittest.mock import MagicMock
    import tests.test_pairing  # noqa: F401 - initializes HA module stubs

    class _StubConfigFlow:
        def __init_subclass__(cls, **kwargs):
            pass

    sys.modules["homeassistant.config_entries"].ConfigFlow = _StubConfigFlow
    sys.modules["homeassistant.config_entries"].OptionsFlow = type("OptionsFlow", (), {})
    sys.modules["homeassistant.config_entries"].ConfigFlowResult = dict

    from custom_components.domolink_camera.config_flow import (
        DomoLinkCameraConfigFlow,
        DomoLinkCameraOptionsFlow,
    )

    flow = DomoLinkCameraOptionsFlow()
    assert flow is not None
    flow2 = DomoLinkCameraConfigFlow.async_get_options_flow(MagicMock())
    assert isinstance(flow2, DomoLinkCameraOptionsFlow)
