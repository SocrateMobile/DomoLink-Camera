"""Box & ISP Detection service and TV Channels Manager for DomoLink Camera."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
from typing import Any
import urllib.parse
import urllib.request

import aiohttp

_LOGGER = logging.getLogger(__name__)

FREEBOX_API_URL = "http://mafreebox.freebox.fr/api/v8/api_version"
FREEBOX_API_IP = "http://192.168.1.254/api/v8/api_version"
FREEBOX_M3U_URL = "http://mafreebox.freebox.fr/freeboxtv/playlist.m3u"

# Channel color themes for high-contrast vector SVG logos
CHANNEL_SVG_THEMES: dict[str, tuple[str, str, str, str, int]] = {
    # key: (bg_color, fg_color, main_text, sub_text, font_size)
    "tf1": ("#004CA3", "#FFFFFF", "TF1", "", 24),
    "france 2": ("#E20025", "#FFFFFF", "2", "FRANCE", 28),
    "france 3": ("#0067A5", "#FFFFFF", "3", "FRANCE", 28),
    "france 4": ("#BA007C", "#FFFFFF", "4", "FRANCE", 28),
    "france 5": ("#009E49", "#FFFFFF", "5", "FRANCE", 28),
    "m6": ("#1A1D20", "#FFFFFF", "M6", "", 26),
    "arte": ("#FA5000", "#FFFFFF", "arte", "", 24),
    "c8": ("#1D70B8", "#FFFFFF", "C8", "", 24),
    "w9": ("#822980", "#FFFFFF", "W9", "", 24),
    "tmc": ("#0078D7", "#FFFFFF", "TMC", "", 24),
    "tfx": ("#E6007E", "#FFFFFF", "TFX", "", 24),
    "nrj 12": ("#E2001A", "#FFFFFF", "NRJ", "12", 22),
    "lcp": ("#004B87", "#FFFFFF", "LCP", "SÉNAT", 22),
    "la chaîne parlementaire": ("#004B87", "#FFFFFF", "LCP", "SÉNAT", 22),
    "gulli": ("#7DBE00", "#FFFFFF", "gulli", "", 24),
    "bfm tv": ("#00428A", "#FFFFFF", "BFM", "TV", 22),
    "bfmtv": ("#00428A", "#FFFFFF", "BFM", "TV", 22),
    "cnews": ("#1E252B", "#FFFFFF", "CNEWS", "", 18),
    "cstar": ("#111827", "#38BDF8", "C★", "STAR", 22),
    "gulli": ("#7DBE00", "#FFFFFF", "gulli", "", 24),
    "tf1 séries films": ("#7B2CBF", "#FFFFFF", "TF1", "SÉRIES", 20),
    "l'équipe": ("#ED1C24", "#FFFFFF", "L'EQ", "SPORT", 20),
    "la chaîne l'equipe": ("#ED1C24", "#FFFFFF", "L'EQ", "SPORT", 20),
    "6ter": ("#5C2D91", "#FFFFFF", "6ter", "", 24),
    "rmc story": ("#0055A5", "#FFFFFF", "RMC", "STORY", 20),
    "rmc découverte": ("#002D62", "#FFFFFF", "RMC", "DÉCOUV.", 18),
    "chérie 25": ("#E4007D", "#FFFFFF", "chérie", "25", 20),
    "lci": ("#003875", "#FFFFFF", "LCI", "", 24),
    "franceinfo": ("#FFE400", "#111827", "info:", "FRANCE", 22),
    "paris première": ("#2B2D42", "#FFFFFF", "PARIS", "1ÈRE", 18),
    "canal+": ("#000000", "#FFFFFF", "CANAL+", "", 18),
    "france 24": ("#0055A5", "#FFFFFF", "F24", "FRANCE", 22),
    "euronews": ("#002D62", "#FFFFFF", "EURO", "NEWS", 20),
    "tv5 monde": ("#009EE0", "#FFFFFF", "TV5", "MONDE", 20),
    "kto": ("#003366", "#FFFFFF", "KTO", "TV", 22),
    "t18": ("#1F2937", "#60A5FA", "T18", "TV", 22),
    "novo19": ("#374151", "#F59E0B", "19", "NOVO", 22),
}


def generate_svg_channel_logo(name: str, num: int | None = None, category: str = "") -> str:
    """Generate a crisp, self-contained SVG Data URI logo for a channel."""
    clean = name.lower().strip()
    theme = None

    for k, v in CHANNEL_SVG_THEMES.items():
        if k == clean or k in clean or clean in k:
            theme = v
            break

    if theme:
        bg, fg, text, sub, fz = theme
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60" width="100" height="60">'
            f'<rect width="100" height="60" rx="10" fill="{bg}"/>'
            f'<text x="50" y="{36 if not sub else 32}" fill="{fg}" font-family="system-ui, -apple-system, sans-serif" font-size="{fz}" font-weight="900" text-anchor="middle">{text}</text>'
        )
        if sub:
            svg += f'<text x="50" y="49" fill="{fg}" opacity="0.9" font-family="system-ui, -apple-system, sans-serif" font-size="10" font-weight="700" text-anchor="middle">{sub}</text>'
        svg += "</svg>"
        return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)

    # Fallback styled badge using channel number or initials
    label = str(num) if num is not None else re.sub(r"[^A-Za-z0-9]", "", name)[:4].upper()
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60" width="100" height="60">'
        '<defs><linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" stop-color="#1e293b"/><stop offset="100%" stop-color="#0f172a"/>'
        '</linearGradient></defs>'
        '<rect width="100" height="60" rx="10" fill="url(#g)" stroke="#334155" stroke-width="1.5"/>'
        f'<text x="50" y="38" fill="#60A5FA" font-family="system-ui, -apple-system, sans-serif" font-size="22" font-weight="800" text-anchor="middle">{label}</text>'
        '</svg>'
    )
    return "data:image/svg+xml;utf8," + urllib.parse.quote(svg)


def canonical_channel_key(name: str) -> str:
    """Normalize channel name to match duplicates across Freebox and Web feeds."""
    n = name.lower().strip()
    for src, dst in (
        ("é", "e"), ("è", "e"), ("ê", "e"), ("ë", "e"),
        ("à", "a"), ("î", "i"), ("ï", "i"), ("ô", "o"),
        ("ù", "u"), ("ç", "c"), ("'", ""), ("-", " "),
    ):
        n = n.replace(src, dst)
    n = re.sub(r"[^a-z0-9]+", "", n)

    if "parlementaire" in n or "lcp" in n:
        return "lcp"
    if "franceinfo" in n:
        return "franceinfo"
    if "equipe" in n:
        return "lequipe"
    if "bfm" in n:
        return "bfmtv"
    if "cnews" in n:
        return "cnews"
    if "cstar" in n:
        return "cstar"
    if "arte" in n:
        return "arte"
    if "tv5" in n:
        return "tv5monde"
    if "euronews" in n:
        return "euronews"
    if "kto" in n:
        return "kto"
    return n


# Universal TNT & Info Free Web Streams (Legal public HLS feeds available for all ISPs)
UNIVERSAL_TNT_CHANNELS: list[dict[str, Any]] = [
    {
        "id": "arte",
        "num": 7,
        "name": "Arte",
        "category": "Culture",
        "logo": generate_svg_channel_logo("Arte", 7, "Culture"),
        "stream_url": "https://artesimulcast.akamaized.net/hls/live/2031003/artelive_fr/index.m3u8",
        "type": "hls",
        "quality": "1080p Full HD",
    },
    {
        "id": "bfmtv",
        "num": 15,
        "name": "BFM TV",
        "category": "Information",
        "logo": generate_svg_channel_logo("BFM TV", 15, "Information"),
        "stream_url": "https://stream.bfmtv.com/bfmtv/hls/live.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "franceinfo",
        "num": 27,
        "name": "franceinfo:",
        "category": "Information",
        "logo": generate_svg_channel_logo("franceinfo", 27, "Information"),
        "stream_url": "https://static.france24.com/live/F24_FR_LO_HLS/live_tv.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "france24",
        "num": 33,
        "name": "France 24",
        "category": "Information",
        "logo": generate_svg_channel_logo("France 24", 33, "Information"),
        "stream_url": "https://static.france24.com/live/F24_FR_LO_HLS/live_tv.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "euronews",
        "num": 34,
        "name": "Euronews Français",
        "category": "Information",
        "logo": generate_svg_channel_logo("Euronews", 34, "Information"),
        "stream_url": "https://euronews-fr-p2p.secure.footprint.net/live/fr.m3u8",
        "type": "hls",
        "quality": "720p HD",
    },
    {
        "id": "tv5monde",
        "num": 35,
        "name": "TV5 Monde",
        "category": "Généraliste",
        "logo": generate_svg_channel_logo("TV5 Monde", 35, "Généraliste"),
        "stream_url": "https://ott.tv5monde.com/Content/HLS/Live/channel(fbs)/index.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "lcp",
        "num": 13,
        "name": "LCP / Public Sénat",
        "category": "Information",
        "logo": generate_svg_channel_logo("LCP", 13, "Information"),
        "stream_url": "https://lcp.senat.fr/live/stream.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "kto",
        "num": 40,
        "name": "KTO Télévision",
        "category": "Culture",
        "logo": generate_svg_channel_logo("KTO", 40, "Culture"),
        "stream_url": "https://live.ktotv.com/hls/kto_live.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
]


class BoxDetectorService:
    """Detects ISP Box (Freebox, Livebox, SFR, Bbox) and aggregates available TV streams."""

    def __init__(self, hass: Any) -> None:
        """Initialize service."""
        self.hass = hass
        self._box_info: dict[str, Any] | None = None
        self._cached_channels: list[dict[str, Any]] = []
        self._cache_time: float = 0

    async def async_detect_box(self) -> dict[str, Any]:
        """Probe network and identify the local ISP gateway."""
        if self._box_info:
            return self._box_info

        # 1. Test Freebox API
        freebox_data = await self._probe_freebox()
        if freebox_data:
            self._box_info = freebox_data
            return freebox_data

        # 2. Test Orange Livebox
        livebox_data = await self._probe_livebox()
        if livebox_data:
            self._box_info = livebox_data
            return livebox_data

        # 3. Test SFR Box
        sfr_data = await self._probe_sfr()
        if sfr_data:
            self._box_info = sfr_data
            return sfr_data

        # 4. Test Bouygues Bbox
        bbox_data = await self._probe_bbox()
        if bbox_data:
            self._box_info = bbox_data
            return bbox_data

        # 5. Generic / Fallback ISP
        generic_info = {
            "brand": "generic",
            "name": "Box Internet / Routeur Local",
            "model": "Passerelle Standard",
            "multiposte_supported": False,
            "has_web_tv": True,
            "badge": "TNT Web Universelle",
            "description": "Accès direct au bouquet gratuit TNT & Informations en haute définition (HLS).",
            "ip": "192.168.1.1",
        }
        self._box_info = generic_info
        return generic_info

    async def _probe_freebox(self) -> dict[str, Any] | None:
        """Test if a Freebox is present on the network."""
        urls = [FREEBOX_API_URL, FREEBOX_API_IP]
        for url in urls:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=1.5) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            model_name = data.get("box_model_name", "Freebox")
                            device_type = data.get("device_type", "Freebox Server")
                            api_ver = data.get("api_version", "")
                            return {
                                "brand": "free",
                                "name": f"Freebox ({model_name})",
                                "model": model_name,
                                "device_type": device_type,
                                "api_version": api_ver,
                                "multiposte_supported": True,
                                "has_web_tv": True,
                                "badge": "Freebox TV Multiposte Actif ⚡",
                                "description": f"{model_name} détectée avec succès. Accès direct aux flux vidéo Multiposte locaux en qualité maximale.",
                                "ip": "192.168.1.254",
                                "m3u_url": FREEBOX_M3U_URL,
                            }
            except Exception:
                continue
        return None

    async def _probe_livebox(self) -> dict[str, Any] | None:
        """Probe for Orange Livebox."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://192.168.1.1/sysbus/NMC:getWANStatus", timeout=0.8) as resp:
                    if resp.status in (200, 401, 403):
                        return {
                            "brand": "orange",
                            "name": "Orange Livebox",
                            "model": "Livebox",
                            "multiposte_supported": False,
                            "has_web_tv": True,
                            "badge": "Orange Livebox (TNT Web)",
                            "description": "Livebox Orange détectée. Accès aux flux TNT Web légaux HD.",
                            "ip": "192.168.1.1",
                        }
        except Exception:
            pass
        return None

    async def _probe_sfr(self) -> dict[str, Any] | None:
        """Probe for SFR Box."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("http://192.168.1.1/api/1.0/?method=system.getInfo", timeout=0.8) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        if "sfr" in text.lower() or "neufbox" in text.lower() or "nb6" in text.lower():
                            return {
                                "brand": "sfr",
                                "name": "SFR Box",
                                "model": "Box SFR / Neufbox",
                                "multiposte_supported": False,
                                "has_web_tv": True,
                                "badge": "Box SFR (TNT Web)",
                                "description": "Box SFR détectée. Accès au bouquet direct TNT Web HD.",
                                "ip": "192.168.1.1",
                            }
        except Exception:
            pass
        return None

    async def _probe_bbox(self) -> dict[str, Any] | None:
        """Probe for Bouygues Bbox."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get("https://mabbox.bytel.fr/api/v1/device", timeout=0.8, ssl=False) as resp:
                    if resp.status in (200, 401):
                        return {
                            "brand": "bouygues",
                            "name": "Bouygues Bbox",
                            "model": "Bbox Fibre / ADSL",
                            "multiposte_supported": False,
                            "has_web_tv": True,
                            "badge": "Bouygues Bbox (TNT Web)",
                            "description": "Bbox détectée. Accès au bouquet TNT Web HD.",
                            "ip": "192.168.1.254",
                        }
        except Exception:
            pass
        return None

    async def async_get_tv_channels(self) -> list[dict[str, Any]]:
        """Retrieve aggregated and formatted list of channels based on detected box."""
        if self._cached_channels:
            return self._cached_channels

        box = await self.async_detect_box()
        channels: list[dict[str, Any]] = []

        # 1. If Freebox, fetch and parse official Freebox TV Multiposte playlist
        if box.get("multiposte_supported"):
            try:
                freebox_channels = await self._fetch_freebox_playlist()
                if freebox_channels:
                    channels.extend(freebox_channels)
            except Exception as e:
                _LOGGER.error("Failed to parse Freebox TV playlist: %s", e)

        # 2. Canonical index of existing Freebox channels for deduplication
        existing_keys = {canonical_channel_key(c["name"]): c for c in channels}

        # 3. Merge universal TNT & Web HLS channels without creating duplicates
        for u_ch in UNIVERSAL_TNT_CHANNELS:
            ck = canonical_channel_key(u_ch["name"])
            matched_channel = existing_keys.get(ck)

            if matched_channel:
                # Channel already available from Freebox: attach web HLS stream as fallback
                matched_channel["web_hls_url"] = u_ch["stream_url"]
                if not matched_channel.get("logo"):
                    matched_channel["logo"] = u_ch["logo"]
            else:
                # Add channel from universal TNT list (e.g. if absent from Freebox multiposte)
                channels.append(u_ch)
                existing_keys[ck] = u_ch

        # Ensure all channels have a high-contrast SVG logo
        for ch in channels:
            if not ch.get("logo") or "wikimedia.org" in ch.get("logo", ""):
                ch["logo"] = generate_svg_channel_logo(ch["name"], ch.get("num"), ch.get("category", ""))

        # Sort channels by channel number, then by name
        def _sort_key(ch: dict[str, Any]) -> tuple[int, str]:
            num = ch.get("num")
            try:
                n = int(num) if num is not None else 999
            except Exception:
                n = 999
            return (n, ch.get("name", ""))

        channels.sort(key=_sort_key)
        self._cached_channels = channels
        return channels

    async def _fetch_freebox_playlist(self) -> list[dict[str, Any]]:
        """Fetch and parse Freebox TV M3U playlist from local gateway."""
        def _download_m3u() -> str:
            req = urllib.request.Request(
                FREEBOX_M3U_URL,
                headers={"User-Agent": "DomoLink-Camera/1.0"},
            )
            with urllib.request.urlopen(req, timeout=4.0) as response:
                content = response.read()
                try:
                    return content.decode("utf-8")
                except UnicodeDecodeError:
                    return content.decode("latin-1", errors="replace")

        raw_text = await self.hass.async_add_executor_job(_download_m3u)
        lines = raw_text.splitlines()

        parsed: dict[str, dict[str, Any]] = {}
        current_num: int | None = None
        current_name: str = ""

        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF:"):
                # Format: #EXTINF:0,2 - France 2 (auto)
                match = re.match(r"#EXTINF:0,(?:(\d+)\s*-\s*)?(.*)", line)
                if match:
                    num_str = match.group(1)
                    current_num = int(num_str) if num_str else None
                    current_name = match.group(2).strip()
            elif line.startswith("rtsp://") and current_name:
                url = line
                # Extract clean canonical channel name (remove "(auto)", "(HD)", etc.)
                clean_name_match = re.match(r"^(.*?)(?:\s*\((.*?)\))?$", current_name)
                canonical_name = clean_name_match.group(1).strip() if clean_name_match else current_name
                flavour = clean_name_match.group(2).strip().lower() if clean_name_match and clean_name_match.group(2) else "auto"

                channel_id = re.sub(r"[^a-z0-9]+", "_", canonical_name.lower()).strip("_")

                if channel_id not in parsed:
                    # Determine category
                    lower_name = canonical_name.lower()
                    cat = "Généraliste"
                    if any(w in lower_name for w in ("info", "news", "lcp", "parlementaire", "euronews")):
                        cat = "Information"
                    elif any(w in lower_name for w in ("arte", "culture", "histoire", "science", "kto")):
                        cat = "Culture"
                    elif any(w in lower_name for w in ("gulli", "junior", "disney", "cartoon", "toon")):
                        cat = "Jeunesse"
                    elif any(w in lower_name for w in ("equipe", "sport", "racing", "golf")):
                        cat = "Sport"
                    elif any(w in lower_name for w in ("france 3", "region", "alpes", "alsace", "bretagne", "normandie")):
                        cat = "Régionale"
                    elif any(w in lower_name for w in ("music", "cstar", "radio", "m6 music", "trace")):
                        cat = "Musique"

                    logo_url = generate_svg_channel_logo(canonical_name, current_num, cat)

                    parsed[channel_id] = {
                        "id": channel_id,
                        "num": current_num,
                        "name": canonical_name,
                        "category": cat,
                        "logo": logo_url,
                        "stream_url": url,
                        "streams": {},
                        "fallback_urls": [],
                        "type": "rtsp",
                        "quality": "HD (Freebox Multiposte)",
                    }

                # Store stream flavour
                parsed[channel_id]["streams"][flavour] = url
                if url not in parsed[channel_id]["fallback_urls"]:
                    parsed[channel_id]["fallback_urls"].append(url)

                # Prefer HD or auto stream as the primary stream URL
                if flavour in ("hd", "auto") or not parsed[channel_id].get("stream_url"):
                    parsed[channel_id]["stream_url"] = url

                current_name = ""
                current_num = None

        return list(parsed.values())
