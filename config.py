"""
Central configuration for the Face Attendance System.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Windows Icon
# --------------------------------------------------------------------------
WINDOW_ICON_PATH = os.environ.get("WINDOW_ICON_PATH", ".\\assets\\icon\\a.png")

# --------------------------------------------------------------------------
# Database Configuration
# --------------------------------------------------------------------------
DATABASE_URL = os.environ.get(
    "ATTENDANCE_DB_URL",
    f"sqlite:///{(BASE_DIR / 'data' / 'attendance.db').as_posix()}"
)

DB_POOL_SIZE = int(os.environ.get("ATTENDANCE_DB_POOL_SIZE", 5))
DB_POOL_MAX_OVERFLOW = int(os.environ.get("ATTENDANCE_DB_POOL_MAX_OVERFLOW", 10))
DB_POOL_RECYCLE_SECONDS = int(os.environ.get("ATTENDANCE_DB_POOL_RECYCLE", 1800))

# --------------------------------------------------------------------------
# Face Recognition Settings
# --------------------------------------------------------------------------
CAMERA_INDEX = int(os.environ.get("ATTENDANCE_CAMERA_INDEX", 0))

# Store the cached LBPH model directly in the 'data' folder alongside the DB
MODEL_PATH = Path(os.environ.get("ATTENDANCE_MODEL_PATH", str(BASE_DIR / "data" / "lbph_model.yml")))
LABEL_MAP_PATH = Path(os.environ.get("ATTENDANCE_LABEL_MAP_PATH", str(BASE_DIR / "data" / "label_map.json")))

MODEL_AUTO_SYNC_SECONDS = int(os.environ.get("ATTENDANCE_MODEL_SYNC_SECONDS", 60))

MIN_PHOTOS_PER_USER = 3
MAX_PHOTOS_PER_USER = 5
RECOGNITION_CONFIDENCE_THRESHOLD = float(os.environ.get("ATTENDANCE_CONF_THRESHOLD", 70.0))
FACE_DETECT_MIN_SIZE = (120, 120)
ATTENDANCE_COOLDOWN_MINUTES = 1

# --------------------------------------------------------------------------
# Hardware Pass-Signal Settings
# --------------------------------------------------------------------------
HARDWARE_SIGNAL_ENABLED = os.environ.get("ATTENDANCE_HW_ENABLED", "false").lower() == "true"
HARDWARE_SIGNAL_MODE = os.environ.get("ATTENDANCE_HW_MODE", "SERIAL").upper()

GPIO_PASS_PIN = int(os.environ.get("ATTENDANCE_GPIO_PIN", 17))
GPIO_PULSE_SECONDS = float(os.environ.get("ATTENDANCE_GPIO_PULSE", 1.5))

SERIAL_PORT = os.environ.get("ATTENDANCE_SERIAL_PORT", "COM3")
SERIAL_BAUDRATE = int(os.environ.get("ATTENDANCE_SERIAL_BAUD", 9600))
SERIAL_PASS_BYTE = b"1"
SERIAL_FAIL_BYTE = b"0"

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
DEFAULT_ADMIN_USERNAME = os.environ.get("ATTENDANCE_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ATTENDANCE_ADMIN_PASS", "Admin@123")
KIOSK_REQUIRE_APPROVAL = os.environ.get("ATTENDANCE_KIOSK_REQUIRE_APPROVAL", "false").lower() == "true"

# --------------------------------------------------------------------------
# Application metadata & Logging
# --------------------------------------------------------------------------
LOG_LEVEL = os.environ.get("ATTENDANCE_LOG_LEVEL", "INFO")
APP_NAME = "Face Attendance System"
APP_VERSION = "1.0.0"

