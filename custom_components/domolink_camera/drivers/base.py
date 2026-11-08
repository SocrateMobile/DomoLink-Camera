"""Base class for all DomoLink Camera drivers."""

from __future__ import annotations

import abc
import logging
from typing import Any, Callable

_LOGGER = logging.getLogger(__name__)


class BaseCameraDriver(abc.ABC):
    """Abstract interface for modular camera hardware drivers."""

    def __init__(self, camera_id: str, config: dict[str, Any], on_frame_callback: Callable[[bytes], None] | None = None) -> None:
        """Initialize driver with camera configuration."""
        self.camera_id = camera_id
        self.config = config
        self.on_frame_callback = on_frame_callback
        self.is_connected = False
        self.is_streaming = False
        self.last_snapshot: bytes | None = None
        self.last_snapshot_time: float | None = None
        self.status = "offline"

    @property
    def host(self) -> str:
        """Return host IP or domain."""
        return self.config.get("host", "")

    @property
    def port(self) -> int:
        """Return primary port."""
        return int(self.config.get("port", 0))

    @abc.abstractmethod
    async def async_connect(self) -> bool:
        """Establish connection to the camera."""
        pass

    @abc.abstractmethod
    async def async_disconnect(self) -> None:
        """Close connection cleanly."""
        pass

    @abc.abstractmethod
    async def async_get_snapshot(self) -> bytes | None:
        """Retrieve latest snapshot image (JPEG bytes)."""
        pass

    @abc.abstractmethod
    async def async_start_stream(self) -> None:
        """Start receiving live video stream."""
        pass

    @abc.abstractmethod
    async def async_stop_stream(self) -> None:
        """Stop receiving live video stream."""
        pass

    async def async_set_night_vision(self, enabled: bool) -> bool:
        """Toggle infrared night vision if supported."""
        return False

    async def async_reboot(self) -> bool:
        """Trigger device reboot if supported."""
        return False

    def get_capabilities(self) -> dict[str, Any]:
        """Return supported capabilities (ptz, night_vision, audio, etc.)."""
        return {
            "night_vision": False,
            "ptz": False,
            "audio": False,
            "reboot": False,
        }
