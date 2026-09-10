# Face & ID Card Attendance Kiosk System

A production-ready desktop face-recognition attendance system built with **Python 3** and **PyQt5**, featuring two modes (Admin / User), configurable per-field data privacy, SQLite storage with a documented PostgreSQL upgrade path for centralized **multi-kiosk / multi-PC** deployments, per-location access control, and an optional physical PASS-signal output for integrating turnstiles, door locks, LEDs, or buzzers via a microcontroller.

---

## ✨ Features

- **Admin Mode**
  - Create, edit, and delete employees (Name, Age, Department, Employee ID, Contact Information)
  - Enroll 3–5 face photos per employee via live webcam capture or file upload
  - Choose exactly which fields are shown to users after a successful scan (Field Visibility Settings)
  - In-app **Change Password** (Account menu) — no more editing the database by hand to rotate the admin password
  - **Kiosks / Locations tab** — see every PC that has ever opened the app (scan kiosks + admin dashboards), identified by MAC address + OS username; rename each to a friendly location, and block/unblock its ability to log attendance
  - **Attendance Logs** filterable by location, showing which physical kiosk (name + MAC) each scan came from
  - Model auto-retrains in the background whenever employees are added/edited/removed
- **User Mode**
  - Live camera preview with real-time face-box detection
  - One-click "Scan Face" — on success, shows only the admin-approved fields; on failure, prompts to try again
  - Every successful scan is written to the database automatically, tagged with the kiosk's location, MAC address, and machine username
  - A duplicate-scan cooldown avoids spamming the log if someone scans repeatedly within a short window
  - Unauthorized/unapproved kiosks are automatically blocked from scanning until an admin approves them centrally
  - Auto-syncs the shared face recognition model on an interval (plus a manual "Sync Now" button), so a kiosk on a different PC picks up newly enrolled employees without restarting
- **Multi-Kiosk / Multi-PC ready** — many User-Mode scan stations on separate PCs plus one or more central Admin dashboards, all reading/writing the same centralized PostgreSQL database and shared face-model storage in real time
- **Physical hardware signal output** — fires a PASS pulse over **Serial (USB/UART)** or **GPIO (Raspberry Pi)** the instant a scan succeeds, so you can drive a relay, turnstile, door strike, LED, or buzzer from any microcontroller (Arduino, ESP32, etc.)
- **SQLite today, PostgreSQL tomorrow** — a single config line switches databases with zero code changes
- Salted PBKDF2 password hashing for the admin account, structured logging to file + console, and a clean modular codebase

---

## 📁 Project Structure

```
face_attendance_app/
├── main.py                     # Application entry point
├── config.py                   # All settings (DB, camera, hardware, security, kiosks)
├── kiosk_identity.py            # Resolves this machine's MAC address + OS username
├── requirements.txt
├── database/
│   ├── models.py                # SQLAlchemy models (Employee, AttendanceLog, Kiosk, etc.)
│   └── db_manager.py             # Engine/session setup, first-run seeding, kiosk registration
├── face_engine/
│   └── recognizer.py             # OpenCV Haar Cascade + LBPH face recognition engine
├── hardware/
│   └── signal_controller.py      # Serial / GPIO physical PASS-signal output
├── ui/
│   ├── mode_select.py             # Landing screen (Admin / User)
│   ├── admin_login.py             # Admin authentication dialog
│   ├── change_password_dialog.py  # In-app admin password change
│   ├── admin_dashboard.py         # Employee CRUD, permissions, kiosks, attendance logs
│   ├── user_registration.py       # Add/Edit employee + camera photo capture
│   ├── user_scan.py                # User-facing scan screen (kiosk-aware)
│   └── workers.py                  # Background QThread (model retraining)
├── assets/
│   ├── faces/<employee_id>/        # Enrollment photos per employee (put on shared storage for multi-kiosk)
│   └── model/                      # Trained LBPH model + label map (put on shared storage for multi-kiosk)
├── data/                        # SQLite database file lives here (single-PC / pilot mode only)
└── logs/                        # Rotating application log file
```

---

## 🚀 Getting Started

### 1. Install Python 3.9+

Confirm with `python3 --version`.

### 2. Create a virtual environment and install dependencies

```bash
cd face_attendance_app
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> `opencv-contrib-python` (not the plain `opencv-python`) is required — it includes the `cv2.face` module used for LBPH recognition.

### 3. Run the application

```bash
python main.py
```

On first launch the app automatically:
- Creates `data/attendance.db` (SQLite) and all required tables
- Seeds a default admin account: **username `admin` / password `Admin@123`**
- Seeds default field-visibility settings (all fields visible)

> ⚠️ **Change the default admin password immediately** in any real deployment — see the Security section below.

### 4. Register your first employees

1. Launch the app → **Admin Mode** → log in.
2. Go to the **Employees** tab → **Add Employee**.
3. Fill in Name, Age, Department, Employee ID, and Contact Information.
4. Click **Start Camera**, then **Capture Photo** 3–5 times from slightly different angles (or use **Upload From File**).
5. Click **Save Employee** — the recognition model retrains automatically in the background.

### 5. Configure what users can see

Admin Dashboard → **Field Visibility Settings** tab → check/uncheck fields → **Save**.

### 6. Run a scan

From the landing screen, choose **User Mode (Scan Face)**, center your face in frame, and click **Scan Face**.

> ℹ️ The very first time *any* PC opens the app (Admin or User Mode), it auto-registers itself in the **Kiosks / Locations** tab using its MAC address + OS username. By default new kiosks are active immediately; set `ATTENDANCE_KIOSK_REQUIRE_APPROVAL=true` in production so an admin must approve each new station before it can scan (see the Multi-Kiosk section below).

---

## 🗄️ Database: SQLite Now, PostgreSQL for Production

The active database is **SQLite** (`config.DATABASE_URL`), which needs no setup and is ideal for a single-kiosk pilot.

`config.py` already contains a **commented-out PostgreSQL connection block** for when you're ready to scale to a shared, networked, multi-kiosk production database:

```python
# DATABASE_URL = os.environ.get(
#     "ATTENDANCE_DB_URL",
#     "postgresql+psycopg2://<db_user>:<db_password>@<db_host>:5432/face_attendance"
# )
```

To migrate:
1. Provision a PostgreSQL database and user.
2. `pip install psycopg2-binary` (already pinned in `requirements.txt`).
3. Either uncomment that block in `config.py` with your real credentials, **or** (recommended, more secure) leave `config.py` untouched and set the environment variable instead:
   ```bash
   export ATTENDANCE_DB_URL="postgresql+psycopg2://attendance_admin:StrongPass123@10.0.0.5:5432/face_attendance"
   ```
4. Restart the app — all tables are created automatically on first connection via `init_db()`. No application code changes are needed since all data access goes through SQLAlchemy's ORM layer.

---

## 🖥️ Multi-Kiosk / Multi-PC Deployment (Production Topology)

The recommended production setup is: **several User-Mode scan kiosks on separate PCs** (e.g. one per entrance/floor) **+ one central Admin dashboard**, all pointed at **one centralized PostgreSQL server** on the network. No application code changes are required for this — only environment variables differ per machine.

### 1. Point every machine at the same PostgreSQL database

On **every** kiosk PC and every Admin PC, set the same connection string:

```bash
export ATTENDANCE_DB_URL="postgresql+psycopg2://attendance_admin:StrongPass123@10.0.0.5:5432/face_attendance"
```

All employees, field-visibility settings, kiosk records, and attendance logs are now shared and update in real time across every machine. Connection pooling (`ATTENDANCE_DB_POOL_SIZE`, `ATTENDANCE_DB_POOL_MAX_OVERFLOW`, `ATTENDANCE_DB_POOL_RECYCLE`) is already tuned with `pool_pre_ping` enabled so idle kiosk connections reconnect cleanly after network blips.

### 2. Share the face model + enrollment photos across all machines

The trained recognition model and enrollment photos are **files on disk**, not database rows — every kiosk needs to read the *same* files the Admin PC writes to when enrolling employees. Point every machine (kiosks + admin) at a shared network path:

```bash
# Example: a Windows UNC share mapped/accessible from every kiosk
export ATTENDANCE_FACE_DIR="\\FILESERVER\attendance-data\faces"
export ATTENDANCE_MODEL_PATH="\\FILESERVER\attendance-data\model\lbph_model.yml"
export ATTENDANCE_LABEL_MAP_PATH="\\FILESERVER\attendance-data\model\label_map.json"

# Example: a mounted NFS/SMB path on Linux
export ATTENDANCE_FACE_DIR="/mnt/attendance-data/faces"
export ATTENDANCE_MODEL_PATH="/mnt/attendance-data/model/lbph_model.yml"
export ATTENDANCE_LABEL_MAP_PATH="/mnt/attendance-data/model/label_map.json"
```

Once an admin enrolls or edits an employee (from any Admin PC), the model retrains and is written to that shared path. Every running User-Mode kiosk automatically detects the updated file and reloads it — by default every 60 seconds (`ATTENDANCE_MODEL_SYNC_SECONDS`), or instantly via the **🔄 Sync Now** button on the scan screen. No kiosk restart required.

### 3. Identify and control access per location

Every machine that opens the app — kiosk or admin — is fingerprinted by **MAC address + OS username** and appears in the Admin Dashboard's **🖥️ Kiosks / Locations** tab, showing hostname, last mode used, last-seen time, and status. From there an admin can:

- **Rename** a station to a friendly label (e.g. "Main Gate", "Building B Entrance", "3rd Floor Turnstile")
- **Block / Unblock** a station's ability to log attendance — a blocked kiosk shows a "not authorized, contact your administrator" screen instead of the camera
- **✅ Approve All Pending** — bulk-unblock every currently-blocked station in one click, useful when rolling out many new kiosks at once (the tab also shows a live "N station(s) pending approval" counter). A confirmation dialog lists every station that will be approved before anything is changed, so a rollout of dozens of kiosks can't be unblocked by accident.
- **Remove** a decommissioned station (its historical attendance rows keep the location name for audit purposes)

Every one of these actions — approve, bulk-approve, block, unblock, rename, remove — is written to a dedicated **🕵️ Kiosk Audit Log** tab, completely separate from face-scan Attendance Logs. Each entry records the timestamp, the action taken, the station's location/MAC/username, which admin performed it, and human-readable details (e.g. a rename shows `'Lobby' -> 'Main Gate'`). This gives you a permanent, tamper-evident history of exactly who granted or revoked access to which physical location, even after a kiosk is later removed from the live list.

For maximum security, enable approval-gating so brand-new/unrecognized machines can't silently start writing attendance data:

```bash
export ATTENDANCE_KIOSK_REQUIRE_APPROVAL=true
```

With this set, any PC opening User Mode for the first time is registered but **blocked by default** until an admin approves it from the Kiosks tab. The blocked screen (and the footer on the landing screen) shows that machine's MAC address and username so someone on-site can read it out over the phone for the admin to find and approve.

**Admin Mode is never blocked by kiosk approval** — an admin can always log in from any PC, even a brand-new/unapproved one, so there's always a way to fix access issues. If the PC an admin is currently using isn't approved yet, the dashboard shows an orange **"This PC is NOT an approved kiosk yet"** banner at the top with a one-click **✅ Approve This PC Now** button, so admins never get locked out while still keeping unapproved *scan* stations from logging attendance.

### 4. Filter attendance by location

The **Attendance Logs** tab includes a **Filter by Location** dropdown, plus dedicated **Location** and **MAC Address** columns, so an admin overseeing multiple entrances/sites can see exactly which physical kiosk logged each scan.

---

## 🔌 Physical Pass-Signal / Microcontroller Integration

When enabled, the app sends a signal the instant a scan **passes**, so you can trigger a relay, turnstile, electric door strike, LED, or buzzer from an external microcontroller.

### Enable it

```bash
export ATTENDANCE_HW_ENABLED=true
export ATTENDANCE_HW_MODE=SERIAL      # or GPIO
```

(or edit the defaults directly in `config.py`)

### Option A — Serial (Arduino / ESP32 / any USB-UART device) — recommended for most setups

```bash
export ATTENDANCE_SERIAL_PORT=COM5        # Windows example
export ATTENDANCE_SERIAL_PORT=/dev/ttyUSB0  # Linux example
export ATTENDANCE_SERIAL_BAUD=9600
```

The app writes a single byte: `b"1"` on a successful scan, `b"0"` on a failed scan. Example Arduino sketch:

```cpp
const int RELAY_PIN = 7;

void setup() {
  Serial.begin(9600);
  pinMode(RELAY_PIN, OUTPUT);
}

void loop() {
  if (Serial.available()) {
    char c = Serial.read();
    if (c == '1') {
      digitalWrite(RELAY_PIN, HIGH);   // e.g. unlock door / open turnstile
      delay(1500);
      digitalWrite(RELAY_PIN, LOW);
    }
  }
}
```

### Option B — GPIO (Raspberry Pi running the app directly)

```bash
export ATTENDANCE_HW_MODE=GPIO
export ATTENDANCE_GPIO_PIN=17     # BCM numbering
export ATTENDANCE_GPIO_PULSE=1.5  # seconds the pin stays HIGH
```

`RPi.GPIO` must be installed (`pip install RPi.GPIO`, uncomment it in `requirements.txt`) and only works when running on actual Raspberry Pi hardware.

### No hardware attached?

If `ATTENDANCE_HW_ENABLED` is left `false` (the default), or the serial port/GPIO library isn't available, the app logs a warning and continues to work normally — nothing breaks on a regular development machine.

---

## 🔐 Security Notes for Production

- Change the default admin password on first login via **Admin Dashboard → Account menu → Change Password**.
- Passwords are stored as salted PBKDF2-SHA256 hashes, never in plain text.
- If moving to PostgreSQL over a network, use TLS/SSL connections and firewall the database host to only the kiosk machines that need it.
- Enrollment photos and the trained model are biometric data — if hosted on a shared network path for multi-kiosk use, restrict that share's permissions to only the accounts running this application, and apply full-disk/share-level encryption.
- Enable `ATTENDANCE_KIOSK_REQUIRE_APPROVAL=true` in production so a stray or unauthorized PC can never silently start writing attendance data — every new station must be approved from the Kiosks / Locations tab first.
- Consider running the User Mode screen in kiosk/fullscreen mode and locking down the OS shell so end users cannot exit to Admin Mode without going through the login dialog.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| UI | PyQt5 |
| Face detection | OpenCV Haar Cascade |
| Face recognition | OpenCV LBPH (`cv2.face`) |
| Database ORM | SQLAlchemy (SQLite active, PostgreSQL production-ready) |
| Hardware I/O | pyserial (Serial) / RPi.GPIO (GPIO) |

---

## 🧩 Known Limitations / Roadmap Ideas

- LBPH is lightweight and dependency-free but less accurate than deep-learning face embeddings (e.g. `dlib`/`face_recognition` or ArcFace) in poor lighting or with many hundreds of enrolled faces — swap `face_engine/recognizer.py` for a deep model if higher accuracy is required at scale.
- Multi-kiosk face-model sharing relies on a shared network filesystem (see the Multi-Kiosk section above) rather than streaming the model through the database — simple and reliable for typical deployments, but a future enhancement could store the trained model as a BLOB in PostgreSQL for environments without a shared file server.
- Kiosk identity (MAC + OS username) assumes each physical station runs under a dedicated machine/account; if multiple kiosks somehow share both an identical MAC and OS username (e.g. cloned VM images), give each a distinct local OS username to keep them uniquely identifiable.
- Admin login is intentionally never blocked by kiosk approval (by design, so admins can't be locked out) — it only shows a warning banner on unapproved machines. If you need Admin Mode itself to be hard-blocked on unrecognized PCs, add that check in `ui/admin_dashboard.py`'s `__init__` next to the existing `register_kiosk(...)` call.

---

## 📜 License

Use, modify, and deploy freely within your organization.
