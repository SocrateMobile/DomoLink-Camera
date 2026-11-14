"""Native Arlo Cloud Driver & Multi-Account Session Manager for DomoLink Camera.

Implements Arlo OCAPI authentication (with 2FA/MFA and direct token support),
HMSWeb device discovery, battery-safe presigned snapshot retrieval, and
on-demand RTSPS live streaming with automatic stream termination.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Any, Callable

import aiohttp

from .base import BaseCameraDriver
from .ha_proxy import HaProxyDriver
from ..const import (
    DRIVER_ARLO_CLOUD,
    STATUS_CONNECTING,
    STATUS_OFFLINE,
    STATUS_ONLINE,
    STATUS_STREAMING,
)

_LOGGER = logging.getLogger(__name__)

ARLO_AUTH_HOST = "https://ocapi-app.arlo.com"
ARLO_API_HOST = "https://myapi.arlo.com"

# Public RSA-2048 key extracted from Arlo Android APK v7.5.1 (assets/public_rsa_key.txt)
ARLO_PUBLIC_RSA_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAwTfCAvNi3l59KvTLjIoI
nLA6/oV72wiVbgRy7UcHNJiYj4AEKZyDLb2tCuIFe057QEXMY/VVb5p+v6TvID4x
vsRDgJH6Ub7fzWnacqI/h743l3YgsP6WRS2cRfduoTOI+B7tN3QFoLGMOwTnMQkb
hJxxn4cAkRd7korf6inBvBadunFS4a0gsUmOCP9AS0USOSywQp8tJsiMI3wD45GK
WtKfMRJEYbd2ggP/Z9Ya2Vx7DMnn0nZJgAkrqVfkMbv1W/hBSot9FvaEwtlJu+NK
v9cj5nhJ0GjNklkShZCwTd8fRQPsQ5g0cc44vK7H2Z5uKbCyQbyulNb71jxkD2FG
/wIDAQAB
-----END PUBLIC KEY-----"""

ARLO_CAMERA_DEVICE_TYPES = {"camera", "doorbell", "arloq", "arloqs", "lights"}
ARLO_EXCLUDED_DEVICE_TYPES = {"basestation", "siren", "bridge", "keypad", "sensor", "router"}

ARLO_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
)


def _encode_arlo_password(password: str) -> str:
    """Encode an Arlo account password in Base64 UTF-8 for OCAPI /api/auth."""
    return base64.b64encode(password.encode("utf-8")).decode("ascii")


def _encrypt_arlo_password_rsa(password: str) -> str:
    """Encrypt an Arlo password using the official APK RSA-2048 public key (PKCS1v15)."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        public_key = serialization.load_pem_public_key(ARLO_PUBLIC_RSA_KEY_PEM.encode("ascii"))
        encrypted = public_key.encrypt(password.encode("utf-8"), padding.PKCS1v15())  # type: ignore[union-attr]
        return base64.b64encode(encrypted).decode("ascii")
    except Exception:
        return _encode_arlo_password(password)


def _b64(value: str) -> str:
    """Base64-encode a header/token value cleanly."""
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _clean_arlo_token(raw_token: str) -> str:
    """Strip whitespace and optional 'Bearer ' prefix from a pasted token."""
    tok = (raw_token or "").strip()
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    return tok


def normalize_arlo_device(
    raw: dict[str, Any],
    account_id: str = "",
    email: str = "",
) -> dict[str, Any] | None:
    """Normalize a raw HMSWeb device entry into a DomoLink Arlo camera dict."""
    dev_type = str(raw.get("deviceType") or "").lower()
    if dev_type in ARLO_EXCLUDED_DEVICE_TYPES:
        return None
    if dev_type not in ARLO_CAMERA_DEVICE_TYPES and "camera" not in dev_type and "doorbell" not in dev_type:
        # Check if it exposes snapshot/streaming fields despite an unlisted model type
        if not raw.get("presignedLastImageUrl") and not raw.get("presignedFullFrameSnapshotUrl"):
            return None

    device_id = str(raw.get("deviceId") or "")
    if not device_id:
        return None

    props = raw.get("properties") or {}
    if not isinstance(props, dict):
        props = {}

    parent_id = str(raw.get("parentId") or device_id)
    xcloud_id = str(raw.get("xCloudId") or raw.get("xcloudId") or "")
    model_id = str(raw.get("modelId") or raw.get("model") or "Arlo Camera")
    device_name = str(raw.get("deviceName") or f"Arlo {device_id}")
    unique_id = str(raw.get("uniqueId") or f"{raw.get('owner', {}).get('ownerId', '')}_{device_id}")

    return {
        "device_id": device_id,
        "parent_id": parent_id,
        "unique_id": unique_id,
        "name": device_name,
        "device_type": dev_type or "camera",
        "model_id": model_id,
        "xcloud_id": xcloud_id,
        "user_id": str(raw.get("userId") or raw.get("owner", {}).get("ownerId") or ""),
        "account_id": account_id,
        "account_email": email,
        "state": str(raw.get("state") or "provisioned"),
        "connection_state": str(props.get("connectionState") or "available"),
        "battery_level": props.get("batteryLevel"),
        "signal_strength": props.get("signalStrength"),
        "charging_state": props.get("chargingState"),
        "presigned_last_image_url": raw.get("presignedLastImageUrl") or "",
        "presigned_snapshot_url": raw.get("presignedFullFrameSnapshotUrl") or "",
    }


class ArloCloudAccountSession:
    """Manages authentication, 2FA/MFA, device sync, and stream signaling for one Arlo account."""

    def __init__(
        self,
        account_id: str,
        email: str,
        name: str = "",
        token: str = "",
        user_id: str = "",
        serial_number: str = "",
        xcloud_id: str = "",
        status: str = "disconnected",
        last_sync: float | None = None,
        devices: list[dict[str, Any]] | None = None,
        hass: Any = None,
        cookie: str = "",
    ) -> None:
        """Initialize an Arlo cloud session for a single user account."""
        self.account_id = account_id
        self.email = (email or "").strip()
        self.name = (name or "").strip() or (self.email.split("@")[0] if "@" in self.email else account_id)
        self.token = _clean_arlo_token(token)
        self.user_id = (user_id or "").strip()
        self.serial_number = (serial_number or "").strip()
        self.xcloud_id = (xcloud_id or "").strip()
        self.cookie = (cookie or "").strip()
        self.status = status
        self.last_sync = last_sync
        self.devices: list[dict[str, Any]] = list(devices or [])
        self.hass = hass
        self.last_error: str = ""

        # Ephemeral 2FA login state
        self._temp_token: str = ""
        self._factor_auth_code: str = ""
        self._selected_factor_id: str = ""
        self._factors: list[dict[str, Any]] = []
        self._session: aiohttp.ClientSession | None = None
        self._last_device_refresh: float = 0.0
        self._auth_lock = asyncio.Lock()

    def to_dict(self) -> dict[str, Any]:
        """Serialize account metadata and persistent token for Home Assistant Store."""
        return {
            "id": self.account_id,
            "name": self.name,
            "email": self.email,
            "token": self.token,
            "user_id": self.user_id,
            "serial_number": self.serial_number,
            "xcloud_id": self.xcloud_id,
            "cookie": self.cookie,
            "status": self.status,
            "last_sync": self.last_sync,
            "devices": self.devices,
        }

    def to_public_dict(self, configured_device_ids: set[str] | None = None) -> dict[str, Any]:
        """Return sanitized account info (no secret token/cookie) for UI WebSocket responses."""
        configured = configured_device_ids or set()
        enriched_devices = []
        for dev in self.devices:
            d_copy = dict(dev)
            d_copy["already_added"] = str(dev.get("device_id", "")) in configured
            enriched_devices.append(d_copy)

        return {
            "id": self.account_id,
            "name": self.name,
            "email": self.email,
            "user_id": self.user_id,
            "xcloud_id": self.xcloud_id,
            "has_token": bool(self.token),
            "status": self.status,
            "last_sync": self.last_sync,
            "last_error": self.last_error,
            "camera_count": len(self.devices),
            "devices": enriched_devices,
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        """Return isolated per-account aiohttp session so cookies never bleed across accounts."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=15.0)
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                cookie_jar=aiohttp.CookieJar(),
            )
        return self._session

    async def async_close(self) -> None:
        """Close the isolated HTTP session cleanly."""
        if self._session and not self._session.closed:
            try:
                await self._session.close()
            except Exception:
                pass
        self._session = None

    def _ocapi_headers(self, auth_token: str = "", encode_b64: bool = True) -> dict[str, str]:
        """Build headers for Arlo OCAPI authentication endpoints."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Auth-Version": "2",
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": ARLO_API_HOST,
            "Referer": f"{ARLO_API_HOST}/",
            "Source": "arloCamWeb",
            "User-Agent": ARLO_DEFAULT_USER_AGENT,
        }
        if auth_token:
            headers["Authorization"] = _b64(auth_token) if encode_b64 else auth_token
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    def _hmsweb_headers(self, xcloud_id: str = "") -> dict[str, str]:
        """Build headers for Arlo HMSWeb API endpoints."""
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Auth-Version": "2",
            "Authorization": self.token,
            "Content-Type": "application/json; charset=UTF-8",
            "Origin": ARLO_API_HOST,
            "Referer": f"{ARLO_API_HOST}/",
            "User-Agent": ARLO_DEFAULT_USER_AGENT,
        }
        target_xcloud = xcloud_id or self.xcloud_id
        if target_xcloud:
            headers["xcloudId"] = target_xcloud
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    async def _post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any], str]:
        """Execute a POST JSON request safely and capture HTTP status + text fallback."""
        session = await self._get_session()
        async with session.post(url, json=payload, headers=headers) as resp:
            text = await resp.text()
            try:
                data = json.loads(text) if text else {}
            except Exception:
                data = {}
            return resp.status, data, text

    async def _get_json(
        self, url: str, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any], str]:
        """Execute a GET JSON request safely and capture HTTP status + text fallback."""
        session = await self._get_session()
        async with session.get(url, headers=headers) as resp:
            text = await resp.text()
            try:
                data = json.loads(text) if text else {}
            except Exception:
                data = {}
            return resp.status, data, text

    @staticmethod
    def _is_cloudflare_block(status: int, text: str) -> bool:
        """Detect Cloudflare WAF / bot challenge responses from Arlo auth endpoints."""
        lower = (text or "").lower()
        return status in (403, 429, 503) and (
            "cloudflare" in lower
            or "cf-ray" in lower
            or "just a moment" in lower
            or "access denied" in lower
            or "<html" in lower
        )

    async def async_start_login(self, password: str) -> dict[str, Any]:
        """Initiate Arlo OCAPI login and discover available 2FA/MFA factors."""
        if not self.email or not password:
            return {"status": "error", "error": "Adresse e-mail et mot de passe requis."}

        self.last_error = ""
        url = f"{ARLO_AUTH_HOST}/api/auth"
        body = {
            "email": self.email,
            "password": _encode_arlo_password(password),
            "language": "fr",
            "EnvSource": "prod",
        }
        status, resp_json, raw_text = await self._post_json(url, body, self._ocapi_headers())

        # Retry once with APK RSA-2048 encryption if OCAPI rejects plain base64 password
        meta = resp_json.get("meta") or {}
        if status == 400 or meta.get("code") in (400, 401):
            rsa_body = {
                "email": self.email,
                "password": _encrypt_arlo_password_rsa(password),
                "language": "fr",
                "EnvSource": "prod",
            }
            status_rsa, resp_rsa, raw_rsa = await self._post_json(
                url, rsa_body, self._ocapi_headers()
            )
            if (resp_rsa.get("meta") or {}).get("code") == 200 or (
                status_rsa == 200 and resp_rsa.get("data", {}).get("token")
            ):
                status, resp_json, raw_text = status_rsa, resp_rsa, raw_rsa
                meta = resp_json.get("meta") or {}

        if self._is_cloudflare_block(status, raw_text):
            err = (
                "Pare-feu Cloudflare détecté sur ocapi-app.arlo.com depuis cette IP. "
                "Utilisez l'onglet 'Jeton Direct' pour importer votre jeton Authorization."
            )
            self.last_error = err
            self.status = "cloudflare_blocked"
            return {"status": "cloudflare_blocked", "error": err}

        data = resp_json.get("data") or {}
        if status >= 400 or (meta.get("code") and meta.get("code") != 200) or not data.get("token"):
            msg = meta.get("message") or data.get("error") or f"Échec d'authentification Arlo (HTTP {status})."
            self.last_error = str(msg)
            self.status = "auth_error"
            return {"status": "error", "error": self.last_error}

        temp_token = str(data["token"])
        self._temp_token = temp_token
        self.user_id = str(data.get("userId") or self.user_id)
        if data.get("serialNumber"):
            self.serial_number = str(data["serialNumber"])

        # Check whether 2FA/MFA challenge is required
        authenticated = data.get("authenticated")
        mfa_state = str(data.get("MFA_State") or "")
        if authenticated == 1 and mfa_state.lower() == "certified":
            self.token = temp_token
            self.status = "connected"
            try:
                devices = await self.async_fetch_devices()
                return {
                    "status": "connected",
                    "session_id": self.account_id,
                    "email": self.email,
                    "devices": devices,
                }
            except Exception as err:
                _LOGGER.debug("Direct post-auth device check needed 2FA: %s", err)

        # Fetch MFA factors
        ts_ms = int(time.time() * 1000)
        f_url = f"{ARLO_AUTH_HOST}/api/getFactors?data={ts_ms}"
        f_status, f_json, f_raw = await self._get_json(f_url, self._ocapi_headers(temp_token))

        if self._is_cloudflare_block(f_status, f_raw):
            err = (
                "Cloudflare a bloqué la récupération des facteurs 2FA. "
                "Utilisez le mode 'Jeton Direct' depuis votre session navigateur my.arlo.com."
            )
            self.last_error = err
            return {"status": "cloudflare_blocked", "error": err}

        f_items = (f_json.get("data") or {}).get("items") or []
        factors: list[dict[str, Any]] = []
        for item in f_items:
            if not isinstance(item, dict) or not item.get("factorId"):
                continue
            factors.append({
                "factorId": str(item["factorId"]),
                "factorType": str(item.get("factorType") or "EMAIL"),
                "displayName": str(item.get("displayName") or item.get("applicationName") or item.get("factorType") or "2FA"),
                "factorRole": str(item.get("factorRole") or ""),
            })

        self._factors = factors
        self.status = "2fa_required"
        return {
            "status": "2fa_required",
            "session_id": self.account_id,
            "email": self.email,
            "user_id": self.user_id,
            "factors": factors,
        }

    async def async_request_2fa_code(self, factor_id: str) -> dict[str, Any]:
        """Request Arlo to dispatch an OTP code (or push prompt) for the selected MFA factor."""
        if not self._temp_token or not self.user_id:
            return {"status": "error", "error": "Session d'authentification expirée. Recommencez la connexion."}

        url = f"{ARLO_AUTH_HOST}/api/startAuth"
        body = {"factorId": factor_id, "userId": self.user_id}
        status, resp_json, raw_text = await self._post_json(
            url, body, self._ocapi_headers(self._temp_token)
        )

        if self._is_cloudflare_block(status, raw_text):
            return {
                "status": "cloudflare_blocked",
                "error": "Requête bloquée par Cloudflare lors de l'envoi du code 2FA.",
            }

        meta = resp_json.get("meta") or {}
        data = resp_json.get("data") or {}
        factor_auth_code = str(data.get("factorAuthCode") or "")
        if status >= 400 or (meta.get("code") and meta.get("code") != 200) or not factor_auth_code:
            msg = meta.get("message") or f"Impossible d'envoyer le code 2FA (HTTP {status})."
            self.last_error = str(msg)
            return {"status": "error", "error": self.last_error}

        self._selected_factor_id = factor_id
        self._factor_auth_code = factor_auth_code
        return {
            "status": "code_sent",
            "factor_id": factor_id,
            "factor_auth_code": factor_auth_code,
        }

    async def async_verify_2fa_code(
        self, otp_code: str, factor_auth_code: str | None = None
    ) -> dict[str, Any]:
        """Complete 2FA/MFA verification and obtain final Arlo session token."""
        code_ref = (factor_auth_code or self._factor_auth_code or "").strip()
        if not self._temp_token or not code_ref:
            return {"status": "error", "error": "Code d'étape 2FA manquant. Demandez d'abord l'envoi du code."}

        url = f"{ARLO_AUTH_HOST}/api/finishAuth"
        body: dict[str, Any] = {
            "factorAuthCode": code_ref,
            "otp": str(otp_code or "").strip(),
            "isBrowserTrusted": True,
        }
        status, resp_json, raw_text = await self._post_json(
            url, body, self._ocapi_headers(self._temp_token)
        )

        if self._is_cloudflare_block(status, raw_text):
            return {
                "status": "cloudflare_blocked",
                "error": "Requête bloquée par Cloudflare lors de la validation du code OTP.",
            }

        meta = resp_json.get("meta") or {}
        data = resp_json.get("data") or {}
        final_token = str(data.get("token") or "")
        if status >= 400 or (meta.get("code") and meta.get("code") != 200) or not final_token:
            msg = meta.get("message") or f"Code 2FA invalide ou expiré (HTTP {status})."
            self.last_error = str(msg)
            return {"status": "error", "error": self.last_error}

        self.token = _clean_arlo_token(final_token)
        if data.get("userId"):
            self.user_id = str(data["userId"])
        if data.get("serialNumber"):
            self.serial_number = str(data["serialNumber"])
        self._temp_token = ""
        self._factor_auth_code = ""
        self.status = "connected"
        self.last_error = ""

        devices = await self.async_fetch_devices()
        return {
            "status": "connected",
            "session_id": self.account_id,
            "devices": devices,
        }

    async def async_validate_and_set_token(
        self,
        token: str,
        user_id: str = "",
        xcloud_id: str = "",
        cookie: str = "",
    ) -> dict[str, Any]:
        """Set a direct Arlo Authorization token (and optional cookies) and sync devices."""
        cleaned = _clean_arlo_token(token)
        if not cleaned:
            return {"status": "error", "error": "Le jeton Authorization ne peut pas être vide."}

        self.token = cleaned
        if user_id:
            self.user_id = user_id.strip()
        if xcloud_id:
            self.xcloud_id = xcloud_id.strip()
        if cookie:
            self.cookie = cookie.strip()

        devices = await self.async_fetch_devices()
        return {
            "status": "connected",
            "devices": devices,
        }

    async def async_fetch_devices(self) -> list[dict[str, Any]]:
        """Query HMSWeb v2/users/devices and cache normalized camera/doorbell devices."""
        if not self.token:
            self.status = "token_missing"
            raise RuntimeError("Aucun jeton Arlo configuré pour ce compte.")

        async with self._auth_lock:
            ts_ms = int(time.time() * 1000)
            url = f"{ARLO_API_HOST}/hmsweb/v2/users/devices?t={ts_ms}"
            status, resp_json, raw_text = await self._get_json(url, self._hmsweb_headers())

            if status in (401, 403):
                self.status = "token_expired"
                self.last_error = f"Jeton Arlo expiré ou refusé (HTTP {status})."
                raise RuntimeError(self.last_error)

            if status >= 400 or not resp_json.get("success", False):
                err = resp_json.get("data", {}).get("message") or resp_json.get("data", {}).get("reason") or f"HTTP {status}"
                self.last_error = f"Erreur synchronisation Arlo: {err}"
                if not raw_text:
                    self.last_error = f"Réponse vide d'Arlo (HTTP {status})"
                raise RuntimeError(self.last_error)

            raw_devices = resp_json.get("data") or []
            normalized: list[dict[str, Any]] = []
            for raw_dev in raw_devices:
                if not isinstance(raw_dev, dict):
                    continue
                if not self.user_id:
                    uid = raw_dev.get("userId") or (raw_dev.get("owner") or {}).get("ownerId")
                    if uid:
                        self.user_id = str(uid)
                if not self.xcloud_id:
                    xc = raw_dev.get("xCloudId") or raw_dev.get("xcloudId")
                    if xc:
                        self.xcloud_id = str(xc)

                norm = normalize_arlo_device(raw_dev, self.account_id, self.email)
                if norm:
                    normalized.append(norm)

            self.devices = normalized
            self.last_sync = time.time()
            self._last_device_refresh = time.time()
            self.status = "connected"
            self.last_error = ""
            return normalized

    def get_device_info(self, device_id: str) -> dict[str, Any] | None:
        """Look up cached normalized metadata for a specific Arlo device ID."""
        for dev in self.devices:
            if str(dev.get("device_id")) == str(device_id):
                return dev
        return None

    async def async_request_snapshot_url(
        self, device_id: str, force_refresh: bool = False
    ) -> str | None:
        """Return latest presigned S3 snapshot URL without waking the camera battery."""
        dev = self.get_device_info(device_id)
        if force_refresh or not dev or (time.time() - self._last_device_refresh > 30.0):
            try:
                await self.async_fetch_devices()
                dev = self.get_device_info(device_id)
            except Exception as err:
                _LOGGER.debug("[%s] Arlo device refresh failed: %s", self.account_id, err)

        if not dev:
            return None
        return dev.get("presigned_snapshot_url") or dev.get("presigned_last_image_url") or None

    async def async_trigger_full_frame_snapshot(
        self, device_id: str, parent_id: str = "", xcloud_id: str = ""
    ) -> bool:
        """Send active fullFrameSnapshot request (only on explicit user demand)."""
        if not self.token:
            return False
        dev = self.get_device_info(device_id) or {}
        target_parent = parent_id or str(dev.get("parent_id") or device_id)
        target_xcloud = xcloud_id or str(dev.get("xcloud_id") or self.xcloud_id)
        from_id = f"{self.user_id}_web" if self.user_id else "web"
        trans_id = f"web!{uuid.uuid4()}!{int(time.time() * 1000)}"
        url = f"{ARLO_API_HOST}/hmsweb/users/devices/fullFrameSnapshot"
        body = {
            "from": from_id,
            "to": target_parent,
            "resource": f"cameras/{device_id}",
            "action": "set",
            "publishResponse": True,
            "transId": trans_id,
            "properties": {"activityState": "fullFrameSnapshot"},
        }
        try:
            status, resp_json, _ = await self._post_json(
                url, body, self._hmsweb_headers(target_xcloud)
            )
            return status == 200 and bool(resp_json.get("success", True))
        except Exception as err:
            _LOGGER.debug("[%s] fullFrameSnapshot failed: %s", device_id, err)
            return False

    async def _listen_sse_for_stream_url(
        self, device_id: str, xcloud_id: str, result_future: asyncio.Future[str]
    ) -> None:
        """Briefly subscribe to /hmsweb/client/subscribe SSE to capture async stream URL events."""
        url = f"{ARLO_API_HOST}/hmsweb/client/subscribe"
        headers = self._hmsweb_headers(xcloud_id)
        headers["Accept"] = "text/event-stream"
        headers["Cache-Control"] = "no-cache"
        try:
            session = await self._get_session()
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return
                async for raw_line in resp.content:
                    if result_future.done():
                        break
                    line = raw_line.decode("utf-8", errors="ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    payload_str = line[5:].strip()
                    if not payload_str.startswith("{"):
                        continue
                    try:
                        evt = json.loads(payload_str)
                    except Exception:
                        continue
                    res = str(evt.get("resource") or "")
                    props = evt.get("properties") or {}
                    candidate_url = props.get("url") or evt.get("url")
                    if candidate_url and (not device_id or device_id in res or not res):
                        if not result_future.done():
                            result_future.set_result(str(candidate_url))
                        break
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.debug("[%s] SSE subscribe ended: %s", device_id, err)

    async def async_start_camera_stream(
        self, device_id: str, parent_id: str = "", xcloud_id: str = ""
    ) -> str | None:
        """Request an on-demand RTSPS/HLS live stream URL for an Arlo camera."""
        if not self.token:
            return None

        dev = self.get_device_info(device_id) or {}
        target_parent = parent_id or str(dev.get("parent_id") or device_id)
        target_xcloud = xcloud_id or str(dev.get("xcloud_id") or self.xcloud_id)
        target_user = self.user_id or str(dev.get("user_id") or "domolink")
        from_id = f"{target_user}_web"
        trans_id = f"web!{uuid.uuid4()}!{int(time.time() * 1000)}"

        url = f"{ARLO_API_HOST}/hmsweb/users/devices/startStream"
        body = {
            "from": from_id,
            "to": target_parent,
            "resource": f"cameras/{device_id}",
            "action": "set",
            "publishResponse": True,
            "transId": trans_id,
            "properties": {
                "activityState": "startUserStream",
                "cameraId": device_id,
            },
        }

        loop = asyncio.get_running_loop()
        sse_future: asyncio.Future[str] = loop.create_future()
        sse_task = asyncio.create_task(
            self._listen_sse_for_stream_url(device_id, target_xcloud, sse_future)
        )

        try:
            # Give SSE handshake a brief moment before posting startStream
            await asyncio.sleep(0.15)
            status, resp_json, _ = await self._post_json(
                url, body, self._hmsweb_headers(target_xcloud)
            )
            if status in (401, 403):
                self.status = "token_expired"
                self.last_error = f"Jeton Arlo expiré (HTTP {status})."
                return None

            data = resp_json.get("data") or {}
            if isinstance(data, dict) and data.get("url"):
                return str(data["url"])

            if status == 200 and resp_json.get("success", True):
                try:
                    return await asyncio.wait_for(sse_future, timeout=4.5)
                except asyncio.TimeoutError:
                    _LOGGER.debug("[%s] Timed out waiting for SSE stream URL", device_id)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.warning("[%s] Arlo startStream failed: %s", device_id, err)
        finally:
            if not sse_task.done():
                sse_task.cancel()
                try:
                    await sse_task
                except (asyncio.CancelledError, Exception):
                    pass

        return None

    async def async_stop_camera_stream(
        self, device_id: str, parent_id: str = "", xcloud_id: str = ""
    ) -> None:
        """Stop an active live stream on Arlo Cloud so the camera returns to battery sleep."""
        if not self.token:
            return

        dev = self.get_device_info(device_id) or {}
        target_parent = parent_id or str(dev.get("parent_id") or device_id)
        target_xcloud = xcloud_id or str(dev.get("xcloud_id") or self.xcloud_id)
        target_user = self.user_id or str(dev.get("user_id") or "domolink")
        trans_id = f"web!{uuid.uuid4()}!{int(time.time() * 1000)}"

        url = f"{ARLO_API_HOST}/hmsweb/users/devices/stopStream"
        body = {
            "from": f"{target_user}_web",
            "to": target_parent,
            "resource": f"cameras/{device_id}",
            "action": "set",
            "publishResponse": True,
            "transId": trans_id,
            "properties": {
                "activityState": "stopUserStream",
                "cameraId": device_id,
            },
        }
        try:
            await self._post_json(url, body, self._hmsweb_headers(target_xcloud))
        except Exception as err:
            _LOGGER.debug("[%s] Arlo stopStream error: %s", device_id, err)


class ArloCloudDriver(BaseCameraDriver):
    """DomoLink Camera driver for native Arlo Cloud accounts (with optional hybrid HA fallback)."""

    def __init__(
        self,
        camera_id: str,
        config: dict[str, Any],
        hass: Any = None,
        account_session: ArloCloudAccountSession | None = None,
        on_frame_callback: Callable[[bytes], None] | None = None,
    ) -> None:
        """Initialize Arlo Cloud driver."""
        super().__init__(camera_id, config, on_frame_callback)
        self.hass = hass
        self.account_session = account_session
        self.arlo_account_id: str = str(config.get("arlo_account_id") or "")
        self.arlo_device_id: str = str(
            config.get("arlo_device_id") or config.get("host") or ""
        )
        self.parent_id: str = str(config.get("parent_id") or self.arlo_device_id)
        self.xcloud_id: str = str(config.get("xcloud_id") or "")
        self._stream_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._ha_delegate: HaProxyDriver | None = None

        ha_entity = config.get("ha_entity_id") or config.get("entity_id") or ""
        if str(ha_entity).startswith("camera."):
            proxy_cfg = dict(config)
            proxy_cfg["entity_id"] = ha_entity
            self._ha_delegate = HaProxyDriver(
                camera_id,
                proxy_cfg,
                hass=self.hass,
                on_frame_callback=self.notify_frame,
            )

    def _resolve_session(self) -> ArloCloudAccountSession | None:
        """Resolve associated Arlo account session dynamically from manager if needed."""
        if self.account_session:
            return self.account_session
        if self.hass and self.arlo_account_id:
            try:
                from ..const import DOMAIN
                mgr = self.hass.data.get(DOMAIN, {}).get("manager")
                if mgr and hasattr(mgr, "arlo_sessions"):
                    self.account_session = mgr.arlo_sessions.get(self.arlo_account_id)
            except Exception:
                pass
        return self.account_session

    async def _download_presigned_image(self, url: str) -> bytes | None:
        """Download a JPEG snapshot from Arlo AWS S3 presigned URL without touching camera battery."""
        if not url or not str(url).startswith(("http://", "https://")):
            return None
        timeout = aiohttp.ClientTimeout(total=8.0)
        try:
            if self.hass:
                from homeassistant.helpers.aiohttp_client import async_get_clientsession
                session = async_get_clientsession(self.hass)
                if hasattr(session, "get"):
                    async with session.get(url, timeout=timeout) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            if data and len(data) >= 100:
                                return data
        except Exception:
            pass

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if data and len(data) >= 100:
                            return data
        except Exception as err:
            _LOGGER.debug("[%s] Presigned S3 snapshot download failed: %s", self.camera_id, err)
        return None

    async def _periodic_snapshot_poll(self) -> None:
        """Passively refresh cached S3 snapshot every 45s while idle (zero battery drain)."""
        while True:
            try:
                await asyncio.sleep(45)
                if not self.is_streaming:
                    await self.async_get_snapshot()
            except asyncio.CancelledError:
                break
            except Exception as err:
                _LOGGER.debug("[%s] Arlo passive snapshot poll error: %s", self.camera_id, err)

    async def async_connect(self) -> bool:
        """Connect passively using cached metadata and last S3 thumbnail (preserves battery)."""
        self.status = STATUS_CONNECTING
        session = self._resolve_session()
        if not session and self._ha_delegate:
            return await self._ha_delegate.async_connect()

        if not session or not session.token:
            self.is_connected = False
            self.status = STATUS_OFFLINE
            return False

        snap = await self.async_get_snapshot()
        dev = session.get_device_info(self.arlo_device_id)
        if dev or snap:
            self.is_connected = True
            self.status = STATUS_ONLINE
            if not self._poll_task or self._poll_task.done():
                self._poll_task = asyncio.create_task(self._periodic_snapshot_poll())
            return True

        self.is_connected = False
        self.status = STATUS_OFFLINE
        return False

    async def async_disconnect(self) -> None:
        """Disconnect cleanly and terminate any active live stream."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            self._poll_task = None
        await self.async_stop_stream()
        if self._ha_delegate:
            await self._ha_delegate.async_disconnect()
        self.is_connected = False
        self.status = STATUS_OFFLINE

    async def async_get_snapshot(self) -> bytes | None:
        """Return latest snapshot from live frame, Arlo S3 presigned URL, or hybrid HA delegate."""
        if self.is_streaming and self.last_snapshot and self.last_snapshot_time:
            if time.time() - self.last_snapshot_time < 2.0:
                return self.last_snapshot

        if not self.is_streaming and self.last_snapshot and self.last_snapshot_time:
            if time.time() - self.last_snapshot_time < 5.0:
                return self.last_snapshot

        session = self._resolve_session()
        if session and session.token:
            img_url = await session.async_request_snapshot_url(self.arlo_device_id)
            if img_url:
                data = await self._download_presigned_image(img_url)
                if data:
                    self.last_snapshot = data
                    self.last_snapshot_time = time.time()
                    self.is_connected = True
                    self.status = STATUS_STREAMING if self.is_streaming else STATUS_ONLINE
                    return data

        if self._ha_delegate:
            snap = await self._ha_delegate.async_get_snapshot()
            if snap:
                self.last_snapshot = snap
                self.last_snapshot_time = time.time()
                self.is_connected = True
                return snap

        if self.is_streaming and self._stream_url:
            snap = await self.async_capture_ffmpeg_snapshot(self._stream_url)
            if snap:
                self.last_snapshot = snap
                self.last_snapshot_time = time.time()
                return snap

        return self.last_snapshot

    async def _stream_loop(self) -> None:
        """Open on-demand Arlo RTSPS stream and transcode MJPEG frames via FFmpeg."""
        session = self._resolve_session()
        try:
            while self.is_streaming:
                stream_url: str | None = None
                if session and session.token:
                    stream_url = await session.async_start_camera_stream(
                        self.arlo_device_id,
                        parent_id=self.parent_id,
                        xcloud_id=self.xcloud_id,
                    )

                if stream_url:
                    self._stream_url = stream_url
                    ok = await self.async_stream_ffmpeg_mjpeg(stream_url)
                    if ok and not self.is_streaming:
                        break

                # Hybrid fallback via linked HA entity (e.g. aarlo) if cloud stream failed
                if self.is_streaming and self._ha_delegate:
                    await self._ha_delegate.async_start_stream()
                    while self.is_streaming and self._ha_delegate.is_streaming:
                        await asyncio.sleep(0.5)
                    break

                if self.is_streaming:
                    snap = await self.async_get_snapshot()
                    if snap:
                        self.notify_frame(snap)
                    await asyncio.sleep(2.0)
        except asyncio.CancelledError:
            raise
        except Exception as err:
            _LOGGER.debug("[%s] Arlo live stream loop error: %s", self.camera_id, err)

    async def async_start_stream(self) -> None:
        """Start on-demand live video stream (wakes Arlo camera only when viewed)."""
        self.is_streaming = True
        self.status = STATUS_STREAMING
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        self._stream_task = asyncio.create_task(self._stream_loop())

    async def async_stop_stream(self) -> None:
        """Stop FFmpeg pipeline and instruct Arlo Cloud to put camera back to sleep."""
        was_streaming = self.is_streaming
        self.is_streaming = False
        self.status = STATUS_ONLINE if self.is_connected else STATUS_OFFLINE
        self._stream_url = None
        self.stop_ffmpeg_process()
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
            self._stream_task = None

        if self._ha_delegate and self._ha_delegate.is_streaming:
            await self._ha_delegate.async_stop_stream()

        if was_streaming:
            session = self._resolve_session()
            if session and session.token:
                await session.async_stop_camera_stream(
                    self.arlo_device_id,
                    parent_id=self.parent_id,
                    xcloud_id=self.xcloud_id,
                )

    def get_capabilities(self) -> dict[str, Any]:
        """Return rich Arlo device capabilities including battery and RF signal."""
        session = self._resolve_session()
        dev = session.get_device_info(self.arlo_device_id) if session else None
        dev = dev or {}
        return {
            "driver_type": DRIVER_ARLO_CLOUD,
            "protocol": "Arlo Cloud Direct (RTSPS / HMSWeb)",
            "night_vision": False,
            "ptz": False,
            "audio": True,
            "reboot": False,
            "battery_protected_mode": True,
            "account_id": self.arlo_account_id,
            "account_email": session.email if session else self.config.get("account_email", ""),
            "arlo_device_id": self.arlo_device_id,
            "parent_id": self.parent_id,
            "model_id": dev.get("model_id") or self.config.get("model_id", "Arlo"),
            "battery_level": dev.get("battery_level"),
            "signal_strength": dev.get("signal_strength"),
            "charging_state": dev.get("charging_state"),
        }
