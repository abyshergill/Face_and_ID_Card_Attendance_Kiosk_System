"""
Central configuration for the Face Attendance System.

Everything that changes between a developer laptop, a pilot deployment,
and a full production rollout lives here (or is overridden through
environment variables), so no application code needs to change when you
move environments.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Database Configuration
# --------------------------------------------------------------------------
# ACTIVE (current): SQLite - zero-config, single-file database. Perfect for
# a pilot / single-kiosk deployment. The file lives under ./data/attendance.db
DATABASE_URL = os.environ.get(
    "ATTENDANCE_DB_URL",
    f"sqlite:///{(BASE_DIR / 'data' / 'attendance.db').as_posix()}"
)

# Connection pool tuning - only meaningful for a networked database
# (PostgreSQL). Several kiosk PCs + admin dashboards may hold idle
# connections open for long periods, so pool_pre_ping is critical to avoid
# "server closed the connection unexpectedly" errors after firewall/NAT
# idle timeouts or brief network blips.
DB_POOL_SIZE = int(os.environ.get("ATTENDANCE_DB_POOL_SIZE", 5))
DB_POOL_MAX_OVERFLOW = int(os.environ.get("ATTENDANCE_DB_POOL_MAX_OVERFLOW", 10))
DB_POOL_RECYCLE_SECONDS = int(os.environ.get("ATTENDANCE_DB_POOL_RECYCLE", 1800))

# --------------------------------------------------------------------------
# PRODUCTION DATABASE (PostgreSQL) -- commented out for now.
#
# When you are ready to move this system to production with a shared,
# multi-kiosk, networked database:
#   1. `pip install psycopg2-binary` (already pinned in requirements.txt)
#   2. Uncomment the line below and fill in your real credentials, OR
#      (recommended) just set the ATTENDANCE_DB_URL environment variable
#      on the production machine/service and leave this file untouched.
#   3. Restart the application - init_db() will create all tables
#      automatically on first run against the new database.
#
# DATABASE_URL = os.environ.get(
#     "ATTENDANCE_DB_URL",
#     "postgresql+psycopg2://<db_user>:<db_password>@<db_host>:5432/face_attendance"
# )
#
# Example:
# DATABASE_URL = "postgresql+psycopg2://attendance_admin:StrongPass123@10.0.0.5:5432/face_attendance"
#
# MULTI-KIOSK / MULTI-PC DEPLOYMENT
# ----------------------------------
# This is the standard production topology: several User-Mode scan
# kiosks running on separate PCs, plus one (or more) Admin dashboards,
# ALL pointed at the same centralized PostgreSQL server via the same
# ATTENDANCE_DB_URL environment variable. No code changes are needed on
# any machine - only the environment variable differs, and every
# machine reads/writes the same live employee, attendance, and kiosk
# data in real time.
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Face Recognition Settings
# --------------------------------------------------------------------------
CAMERA_INDEX = int(os.environ.get("ATTENDANCE_CAMERA_INDEX", 0))

# IMPORTANT for multi-kiosk deployments: enrollment photos and the trained
# recognition model are files on disk, NOT rows in the database. For every
# scan kiosk to recognize every enrolled employee, these paths must point
# to storage all machines can read - typically a shared network path
# (Windows UNC share \\SERVER\attendance-data\..., or a mounted NFS/SMB
# path on Linux). Point every kiosk AND the admin PC at the same location
# via these two environment variables. Left as local folders by default
# for single-PC / pilot use.
FACE_DIR = Path(os.environ.get("ATTENDANCE_FACE_DIR", str(BASE_DIR / "assets" / "faces")))
MODEL_PATH = Path(os.environ.get("ATTENDANCE_MODEL_PATH", str(BASE_DIR / "assets" / "model" / "lbph_model.yml")))
LABEL_MAP_PATH = Path(os.environ.get("ATTENDANCE_LABEL_MAP_PATH", str(BASE_DIR / "assets" / "model" / "label_map.json")))

# How often (seconds) each running User-Mode kiosk checks whether the
# shared model file has been updated (e.g. admin enrolled someone new on
# a different PC) and silently reloads it - no restart required.
MODEL_AUTO_SYNC_SECONDS = int(os.environ.get("ATTENDANCE_MODEL_SYNC_SECONDS", 60))

MIN_PHOTOS_PER_USER = 3
MAX_PHOTOS_PER_USER = 5

# LBPH prediction returns a "distance" - LOWER means a more confident match.
# 0 = perfect match. Typical acceptable range is 40-80 depending on lighting/camera.
RECOGNITION_CONFIDENCE_THRESHOLD = float(os.environ.get("ATTENDANCE_CONF_THRESHOLD", 70.0))
FACE_DETECT_MIN_SIZE = (120, 120)

# Prevents duplicate attendance rows if the same person scans repeatedly
# within a short window (e.g. camera re-triggering).
ATTENDANCE_COOLDOWN_MINUTES = 1

# --------------------------------------------------------------------------
# Hardware Pass-Signal Settings
# --------------------------------------------------------------------------
# Lets this application drive an external microcontroller (Arduino, ESP32,
# relay board, turnstile controller, door strike, LED/buzzer, etc.) the
# instant a scan is verified as a PASS. Two transport modes are supported:
#   "SERIAL" - send a single byte over USB/UART        (most common)
#   "GPIO"   - drive a physical GPIO pin (Raspberry Pi only)
#   "NONE"   - disable physical signalling entirely
HARDWARE_SIGNAL_ENABLED = os.environ.get("ATTENDANCE_HW_ENABLED", "false").lower() == "true"
HARDWARE_SIGNAL_MODE = os.environ.get("ATTENDANCE_HW_MODE", "SERIAL").upper()

# --- GPIO (Raspberry Pi) ---
GPIO_PASS_PIN = int(os.environ.get("ATTENDANCE_GPIO_PIN", 17))   # BCM numbering
GPIO_PULSE_SECONDS = float(os.environ.get("ATTENDANCE_GPIO_PULSE", 1.5))

# --- Serial (Arduino / ESP32 / generic microcontroller) ---
SERIAL_PORT = os.environ.get("ATTENDANCE_SERIAL_PORT", "COM3")   # e.g. "/dev/ttyUSB0" on Linux/RPi
SERIAL_BAUDRATE = int(os.environ.get("ATTENDANCE_SERIAL_BAUD", 9600))
SERIAL_PASS_BYTE = b"1"
SERIAL_FAIL_BYTE = b"0"

# --------------------------------------------------------------------------
# Security
# --------------------------------------------------------------------------
DEFAULT_ADMIN_USERNAME = os.environ.get("ATTENDANCE_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.environ.get("ATTENDANCE_ADMIN_PASS", "Admin@123")
# ^ CHANGE THIS IMMEDIATELY after first login in any real deployment.
#   (Admin Dashboard -> Account menu -> Change Password)

# --------------------------------------------------------------------------
# Kiosk / Multi-Location Access Control
# --------------------------------------------------------------------------
# Every machine that opens this application (User Mode scan kiosk OR Admin
# dashboard) is fingerprinted by MAC address + OS username and recorded in
# the "kiosks" table (see database/models.py::Kiosk). From the Admin
# Dashboard's "Kiosks / Locations" tab, an admin can rename each one to a
# friendly location name and toggle its access on/off.
#
# If KIOSK_REQUIRE_APPROVAL is enabled, any brand-new machine seen for the
# first time is registered but INACTIVE by default, so it cannot log
# attendance until an admin explicitly approves it from the dashboard.
# This is recommended for production so a stray/unauthorized PC can never
# silently start writing attendance data into the central database.
KIOSK_REQUIRE_APPROVAL = os.environ.get("ATTENDANCE_KIOSK_REQUIRE_APPROVAL", "false").lower() == "true"

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "attendance_system.log"
LOG_LEVEL = os.environ.get("ATTENDANCE_LOG_LEVEL", "INFO")

# --------------------------------------------------------------------------
# Application metadata
# --------------------------------------------------------------------------
APP_NAME = "Face Attendance System"
APP_VERSION = "1.0.0"
