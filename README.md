# Centralised Attendance Kiosk System 2.0

## Secure Face & Card Attendance System

An enterprise-grade, edge-capable facial recognition and ID card attendance system built with Python, OpenCV, and SQLAlchemy.

**The Problem It Solves:** Traditional attendance systems suffer from "buddy punching" (ID card sharing), rely on expensive recurring cloud subscriptions, or leave sensitive biometric photos sitting in plain-text folders on vulnerable kiosk computers.

**The Solution:** This system utilizes a **Zero-Trust Kiosk Architecture**, storing all biometric data securely as compressed Database BLOBs, and executing face recognition entirely on the edge using OpenCV's LBPH algorithm (no GPU, internet, or cloud required).

---

## Core Features

* **Dual Scan Modes:** Live face recognition (LBPH) and manual ID card entry.
* **Database-Driven Biometrics:** Enrollment photos and profile pictures are stored securely inside the database as BLOBs. No employee photos are ever saved to local hard drives.
* **Enterprise Security:**
* PBKDF2-SHA256 Password Hashing.
* Escalating Brute-Force Lockouts (15, 20, 25+ minutes).
* Strict Admin Password Policies (Regex validation).


* **Multi-Location Kiosk Control:** Fingerprint Kiosk PCs by MAC address/OS User. Admins can rename, approve, or instantly block specific machines from writing attendance data.
* **Centralized Database Logging:** App logs (INFO, WARNING, ERROR) are written directly to a `system_logs` table for remote IT auditing.
* **PostgreSQL Ready:** Easily migrate from local SQLite to a centralized PostgreSQL server. Features restricted database roles so kiosks can only append data, protecting against compromised endpoints.
    * [PostgreSQL Integration Guide]( ./PostgreSQL_Migration_&_Setup_Guide/README.md)
* **Hardware Signalling:** Integrates with external microcontrollers (Arduino, ESP32, Raspberry Pi) via Serial or GPIO to physically unlock doors, turnstiles, or relays upon a successful scan. Can be toggled globally via the Admin Dashboard.

    * [Hardware Integration Guide](./Hardware_Integration/README.md)

---

## Tech Stack
* **UI Framework:** PyQt5
* **Computer Vision:** OpenCV (Haar Cascades + LBPH)
* **Database ORM:** SQLAlchemy (SQLite & PostgreSQL)
* **Hardware IO:** PySerial / RPi.GPIO

---

## How to Run (Application Entry Points)

This application is designed to be highly modular depending on the computer it is running on. You can run the application using one of three provided entry points:

### 1. `main.py` (Full Application)

* **Usage:** `python main.py`
* **Purpose:** Opens a Mode Selector screen. You can choose to enter either the Admin Dashboard or the Kiosk Scanner. Great for testing, development, or single-PC environments.

### 2. `main_admin.py` (Manager / IT PC)

* **Usage:** `python main_admin.py`
* **Purpose:** Bypasses the mode selector and goes straight to the secure Admin Login. Used to manage employees, settings, and database configurations.
* **Note:** This is the *only* script that has database initialization privileges (creates tables). You must run this at least once to set up a new database.

### 3. `main_kiosk.py` (Door / Turnstile PC)

* **Usage:** `python main_kiosk.py`
* **Purpose:** Bypasses the mode selector and opens the Kiosk scanning interface directly. **It contains absolutely zero admin code.** Even if a user reverse-engineers this file, they cannot access the dashboard or employee management screens.

---

## Quick Setup

1. **Install Dependencies:**
```bash
pip install -r requirements.txt
```


2. **Configure Environment:**
Review the `.env.example` file to configure your database connection and hardware settings.
3. **Initialize the System:**
Run the admin script to create the local `data/attendance.db` database and seed the default administrator account.
```bash
python main.py
```


*(Default Login is `admin` / `Admin@123` — Change this immediately upon login!)*

---

## Compiling Secure Executables (Deployment)

For production, you should compile the separated Python scripts into standalone `.exe` files using PyInstaller so source code is not exposed on the kiosk endpoints.

**Build Admin App:**

```bash
pyinstaller --noconsole --name "FaceAttendance_Admin" --add-data "assets/haarcascade_frontalface_default.xml;assets" main_admin.py

```

**Build Kiosk App:**

```bash
pyinstaller --noconsole --name "FaceAttendance_Kiosk" --add-data "assets/haarcascade_frontalface_default.xml;assets" main_kiosk.py

```

*Distribute the `FaceAttendance_Kiosk` output to your scanning PCs, and keep the `FaceAttendance_Admin` output strictly on Manager machines.*

---

## 📄 License : MIT