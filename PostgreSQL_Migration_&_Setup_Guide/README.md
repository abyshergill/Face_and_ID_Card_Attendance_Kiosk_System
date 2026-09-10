# PostgreSQL Migration & Setup Guide

By default, this application uses a local SQLite database (`data/attendance.db`). This is perfect for testing or a single-PC setup. However, for a **Multi-Kiosk Deployment** where several doors/kiosks share the same data, you must migrate to a centralized PostgreSQL database.

Because the app uses SQLAlchemy, **no Python code needs to change.** You simply update your `.env` file.

## Step 1: Install the PostgreSQL Driver

Ensure the PostgreSQL Python driver is installed on all machines (Admin PC and all Kiosk PCs).

```bash
pip install psycopg2-binary
```

*(Note: This is already included in your `requirements.txt`).*

## Step 2: Database Setup & Security Roles

Open your PostgreSQL server (using pgAdmin or the `psql` command line) and create the database.

To ensure maximum security, we will create **two separate users**: one for you (the Admin) and one restricted user for the physical Kiosk PCs.

Execute these SQL commands:

```sql
-- 1. Create the central database
CREATE DATABASE face_attendance;

-- 2. Create the Admin User (Full Access)
CREATE USER attendance_admin WITH PASSWORD 'SuperSecretAdmin123';
GRANT ALL PRIVILEGES ON DATABASE face_attendance TO attendance_admin;

-- 3. Create the Kiosk User (Restricted Access)
CREATE USER kiosk_user WITH PASSWORD 'RestrictedKiosk123';
GRANT CONNECT ON DATABASE face_attendance TO kiosk_user;

```

## Step 3: Initialize the Database (Admin PC Only)

The Admin PC needs to connect to the database first so SQLAlchemy can automatically build all the tables.

On your **Admin PC**, open the `.env` file and set the URL using your Admin database credentials:

```env
# Format: postgresql+psycopg2://user:password@ip_address/dbname
ATTENDANCE_DB_URL=postgresql+psycopg2://attendance_admin:SuperSecretAdmin123@192.168.1.100/face_attendance

```

Run `python main_admin.py`. The system will connect to PostgreSQL, create all the tables, and seed the default `admin` login account.

## Step 4: Secure the Kiosk Permissions

Now that the Admin PC has created the tables, go back to your PostgreSQL server and restrict the `kiosk_user` so it can only read employees and write attendance logs. It will be physically impossible for a kiosk to delete an employee.

Execute these SQL commands:

```sql
-- Connect to the new database
\c face_attendance;

-- Give Kiosks permission to read employees, photos, and settings
GRANT SELECT ON employees, employee_photos, system_settings TO kiosk_user;

-- Give Kiosks permission to write attendance logs and read/write their own kiosk status
GRANT SELECT, INSERT ON attendance_logs TO kiosk_user;
GRANT SELECT, INSERT, UPDATE ON kiosks TO kiosk_user;

-- Allow Kiosks to increment primary keys
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO kiosk_user;

```

## Step 5: Connect the Kiosk PCs

On your **Kiosk PCs**, open their `.env` file and use the restricted user credentials:

```env
ATTENDANCE_DB_URL=postgresql+psycopg2://kiosk_user:RestrictedKiosk123@192.168.1.100/face_attendance

```

### `Note :`
* Kiosks stream attendance data to the central server in real-time.
* If a kiosk is stolen or hacked, the `kiosk_user` database password only grants them the ability to *add* attendance logs, not destroy or alter your system data.