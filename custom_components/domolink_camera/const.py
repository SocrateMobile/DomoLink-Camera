"""Constants for DomoLink Camera integration."""

DOMAIN = "domolink_camera"
NAME = "DomoLink Camera"
VERSION = "1.0.2"

# Storage
STORAGE_KEY = "domolink_camera_data"
STORAGE_VERSION = 1

# Supported camera drivers
DRIVER_YSXLITE_PPPP = "ysxlite_pppp"
DRIVER_GENERIC_RTSP = "generic_rtsp"
DRIVER_GENERIC_MJPEG = "generic_mjpeg"

SUPPORTED_DRIVERS = {
    DRIVER_YSXLITE_PPPP: "YsxLite / A9 / PPPP (Wi-Fi Mini Cam)",
    DRIVER_GENERIC_RTSP: "RTSP / ONVIF (Standard IP Camera)",
    DRIVER_GENERIC_MJPEG: "MJPEG / HTTP (Webcam & ESP32-CAM)",
}

# Network defaults
DEFAULT_PPPP_DISCOVERY_PORT = 32108
DEFAULT_RTSP_PORT = 554
DEFAULT_HTTP_PORT = 80
DEFAULT_SNAPSHOT_INTERVAL = 10  # seconds between snapshot updates in thumbnail mode

# PPPP Packet Magic Headers
PPPP_MAGIC = b"PPPP"
ILNK_MAGIC = b"\x4c\x4e\x4b\x01"

# YsxLite / iLnk PPPP Binary Command IDs (Extracted from APK reverse engineering)
PPPP_CMD_LIVE_VIDEO_START = 0x0001
PPPP_CMD_LIVE_VIDEO_STOP = 0x0002
PPPP_CMD_LIVE_AUDIO_START = 0x0003
PPPP_CMD_LIVE_AUDIO_STOP = 0x0004
PPPP_CMD_SNAPSHOT_GET = 0x0005
PPPP_CMD_IRCUT_ONOFF = 0x0006
PPPP_CMD_SYSTEM_REBOOT = 0x0007
PPPP_CMD_WIFI_SET = 0x0008
PPPP_CMD_DEV_SEARCH = 0x0009

# Camera Statuses
STATUS_ONLINE = "online"
STATUS_OFFLINE = "offline"
STATUS_CONNECTING = "connecting"
STATUS_STREAMING = "streaming"
STATUS_PAIRING = "pairing"

# Default Camera Icons and Entity Types allowed for bottom banner
ALLOWED_ENTITY_DOMAINS = [
    "switch",
    "light",
    "binary_sensor",
    "sensor",
    "cover",
    "lock",
    "fan",
    "climate",
]

# WebSocket API Types
WS_TYPE_GET_CAMERAS = "domolink_camera/get_cameras"
WS_TYPE_SAVE_LAYOUT = "domolink_camera/save_layout"
WS_TYPE_SAVE_CAMERA = "domolink_camera/save_camera"
WS_TYPE_DELETE_CAMERA = "domolink_camera/delete_camera"
WS_TYPE_START_PAIRING = "domolink_camera/start_pairing"
WS_TYPE_PAIR_STATUS = "domolink_camera/pair_status"
WS_TYPE_SCAN_LOCAL = "domolink_camera/scan_local"
WS_TYPE_GET_ENTITIES = "domolink_camera/get_entities"
WS_TYPE_TRIGGER_LIVE = "domolink_camera/trigger_live"
WS_TYPE_SET_IR = "domolink_camera/set_ir"
WS_TYPE_REBOOT = "domolink_camera/reboot"
