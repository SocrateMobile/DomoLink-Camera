"""Box & ISP Detection service and TV Channels Manager for DomoLink Camera."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
from typing import Any
import urllib.request

import aiohttp

_LOGGER = logging.getLogger(__name__)

FREEBOX_API_URL = "http://mafreebox.freebox.fr/api/v8/api_version"
FREEBOX_API_IP = "http://192.168.1.254/api/v8/api_version"
FREEBOX_M3U_URL = "http://mafreebox.freebox.fr/freeboxtv/playlist.m3u"

# Universal TNT & Info Free Web Streams (Legal public HLS feeds available for all ISPs)
UNIVERSAL_TNT_CHANNELS: list[dict[str, Any]] = [
    {
        "id": "arte",
        "num": 7,
        "name": "Arte",
        "category": "Culture",
        "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Arte_logo_2017.svg/320px-Arte_logo_2017.svg.png",
        "stream_url": "https://artesimulcast.akamaized.net/hls/live/2031003/artelive_fr/index.m3u8",
        "type": "hls",
        "quality": "1080p Full HD",
    },
    {
        "id": "bfmtv",
        "num": 15,
        "name": "BFM TV",
        "category": "Information",
        "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/BFMTV_logo_2019.svg/320px-BFMTV_logo_2019.svg.png",
        "stream_url": "https://stream.bfmtv.com/bfmtv/hls/live.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "franceinfo",
        "num": 27,
        "name": "franceinfo:",
        "category": "Information",
        "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Franceinfo_logo_2016.svg/320px-Franceinfo_logo_2016.svg.png",
        "stream_url": "https://static.france24.com/live/F24_FR_LO_HLS/live_tv.m3u8",  # French public info feed
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "france24",
        "num": 33,
        "name": "France 24",
        "category": "Information",
        "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/France_24_logo_2013.svg/320px-France_24_logo_2013.svg.png",
        "stream_url": "https://static.france24.com/live/F24_FR_LO_HLS/live_tv.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "euronews",
        "num": 34,
        "name": "Euronews Français",
        "category": "Information",
        "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Euronews_2016_logo.svg/320px-Euronews_2016_logo.svg.png",
        "stream_url": "https://euronews-fr-p2p.secure.footprint.net/live/fr.m3u8",
        "type": "hls",
        "quality": "720p HD",
    },
    {
        "id": "tv5monde",
        "num": 35,
        "name": "TV5 Monde",
        "category": "Généraliste",
        "logo": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/TV5Monde_logo.svg/320px-TV5Monde_logo.svg.png",
        "stream_url": "https://ott.tv5monde.com/Content/HLS/Live/channel(fbs)/index.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "lcp",
        "num": 13,
        "name": "LCP / Public Sénat",
        "category": "Information",
        "logo": "https://upload.wikimedia.org/wikipedia/fr/thumb/5/52/LCP_logo_2019.svg/320px-LCP_logo_2019.svg.png",
        "stream_url": "https://lcp.senat.fr/live/stream.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
    {
        "id": "kto",
        "num": 40,
        "name": "KTO Télévision",
        "category": "Culture",
        "logo": "https://upload.wikimedia.org/wikipedia/fr/thumb/a/a2/KTO_logo_2018.svg/320px-KTO_logo_2018.svg.png",
        "stream_url": "https://live.ktotv.com/hls/kto_live.m3u8",
        "type": "hls",
        "quality": "1080p HD",
    },
]

# Known Channel Logos for Freebox Channels
CHANNEL_LOGOS: dict[str, str] = {
    "france 2": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/France_2_2018.svg/320px-France_2_2018.svg.png",
    "france 3": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/France_3_2018.svg/320px-France_3_2018.svg.png",
    "france 4": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/08/France_4_2021.svg/320px-France_4_2021.svg.png",
    "france 5": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/France_5_2018.svg/320px-France_5_2018.svg.png",
    "arte": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Arte_logo_2017.svg/320px-Arte_logo_2017.svg.png",
    "la chaîne parlementaire": "https://upload.wikimedia.org/wikipedia/fr/thumb/5/52/LCP_logo_2019.svg/320px-LCP_logo_2019.svg.png",
    "gulli": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/64/Gulli_logo_2023.svg/320px-Gulli_logo_2023.svg.png",
    "bfm tv": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/87/BFMTV_logo_2019.svg/320px-BFMTV_logo_2019.svg.png",
    "cnews": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/4b/CNews_logo_2017.svg/320px-CNews_logo_2017.svg.png",
    "cstar": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dc/CStar_logo_2016.svg/320px-CStar_logo_2016.svg.png",
    "franceinfo": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e2/Franceinfo_logo_2016.svg/320px-Franceinfo_logo_2016.svg.png",
    "la chaîne l'equipe": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/b3/L%27%C3%89quipe_21_logo_2016.svg/320px-L%27%C3%89quipe_21_logo_2016.svg.png",
    "tv5 monde": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/TV5Monde_logo.svg/320px-TV5Monde_logo.svg.png",
    "euronews": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Euronews_2016_logo.svg/320px-Euronews_2016_logo.svg.png",
}


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
                                "description": f"{model_name} détectée avec succès. Accès direct aux flux vidéo Multiposte RTSP locaux en qualité maximale.",
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
                            "description": "Livebox Orange détectée. Accès aux flux TNT Web légaux HD et possibilité de configurer votre décodeur.",
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
                                "description": "Box SFR détectée. Accès au bouquet direct TNT Web HD et chaînes d'information.",
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
                            "description": "Bbox détectée. Accès au bouquet TNT Web HD et chaînes d'actualité en continu.",
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

        # If Freebox, fetch and parse official Freebox TV Multiposte playlist
        if box.get("multiposte_supported"):
            try:
                freebox_channels = await self._fetch_freebox_playlist()
                if freebox_channels:
                    channels.extend(freebox_channels)
            except Exception as e:
                _LOGGER.error("Failed to parse Freebox TV playlist: %s", e)

        # Merge universal TNT & Web HLS channels (deduplicating or supplementing)
        existing_names = {c["name"].lower().strip() for c in channels}
        for u_ch in UNIVERSAL_TNT_CHANNELS:
            clean_name = u_ch["name"].lower().strip()
            # If Freebox channel exists, attach web HLS fallback URL
            matched = False
            for c in channels:
                if c["name"].lower().strip() == clean_name or clean_name in c["name"].lower():
                    c["web_hls_url"] = u_ch["stream_url"]
                    if not c.get("logo"):
                        c["logo"] = u_ch["logo"]
                    matched = True
                    break
            if not matched:
                channels.append(u_ch)

        # Sort channels primarily by channel number
        def _sort_key(ch: dict[str, Any]) -> int:
            num = ch.get("num")
            try:
                return int(num) if num is not None else 999
            except Exception:
                return 999

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
                return response.read().decode("latin-1")

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

                    logo_url = CHANNEL_LOGOS.get(lower_name, "")

                    parsed[channel_id] = {
                        "id": channel_id,
                        "num": current_num,
                        "name": canonical_name,
                        "category": cat,
                        "logo": logo_url,
                        "stream_url": url,
                        "streams": {},
                        "type": "rtsp",
                        "quality": "HD (Freebox Multiposte)",
                    }

                # Store stream flavour
                parsed[channel_id]["streams"][flavour] = url
                # Default to HD or auto stream URL
                if flavour in ("hd", "auto") or not parsed[channel_id].get("stream_url"):
                    parsed[channel_id]["stream_url"] = url

                current_name = ""
                current_num = None

        return list(parsed.values())
