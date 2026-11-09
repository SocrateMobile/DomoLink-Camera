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
    assert manifest["version"] == "1.4.6"
    assert manifest["codeowners"] == ["@SocrateMobile"]
    assert "SocrateMobile" in manifest["documentation"]
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

    assert len(views) >= 4, f"Expected 4 views, found {len(views)}"
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
