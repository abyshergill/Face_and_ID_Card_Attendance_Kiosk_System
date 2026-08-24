"""
Database engine/session management + first-run seeding.

Swapping from SQLite to PostgreSQL requires ZERO changes to this file -
just change config.DATABASE_URL (see config.py for the commented
production connection string) and restart the application.
"""
import binascii
import hashlib
import logging
import os
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

import config
import kiosk_identity
from database.models import AdminAccount, Base, FieldPermission, Kiosk, KioskAuditLog

logger = logging.getLogger("attendance.db")

os.makedirs(config.BASE_DIR / "data", exist_ok=True)

_engine_kwargs = {"pool_pre_ping": True}
if config.DATABASE_URL.startswith("sqlite"):
    # Required so the same SQLite connection can be safely touched from the
    # Qt main thread and any background worker threads (e.g. retraining).
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL (or any other networked DB): tuned for several kiosk PCs
    # + admin dashboards holding connections concurrently.
    _engine_kwargs["pool_size"] = config.DB_POOL_SIZE
    _engine_kwargs["max_overflow"] = config.DB_POOL_MAX_OVERFLOW
    _engine_kwargs["pool_recycle"] = config.DB_POOL_RECYCLE_SECONDS

engine = create_engine(config.DATABASE_URL, echo=False, future=True, **_engine_kwargs)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
)

DEFAULT_FIELDS = [
    ("name", "Name"),
    ("age", "Age"),
    ("department", "Department"),
    ("employee_id", "Employee ID"),
    ("contact", "Contact Information"),
]


def hash_password(password: str, salt: Optional[str] = None):
    """PBKDF2-SHA256 password hashing (no extra native dependency needed)."""
    if salt is None:
        salt = binascii.hexlify(os.urandom(16)).decode()
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return binascii.hexlify(pwd_hash).decode(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    computed, _ = hash_password(password, salt)
    return computed == expected_hash


def init_db():
    """Create all tables (if missing) and seed default admin + field permissions."""
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        if not session.query(AdminAccount).first():
            pwd_hash, salt = hash_password(config.DEFAULT_ADMIN_PASSWORD)
            session.add(AdminAccount(
                username=config.DEFAULT_ADMIN_USERNAME,
                password_hash=pwd_hash,
                salt=salt,
            ))
            logger.info(
                "Seeded default admin account '%s' - CHANGE THE PASSWORD IMMEDIATELY.",
                config.DEFAULT_ADMIN_USERNAME,
            )

        existing_keys = {fp.field_key for fp in session.query(FieldPermission).all()}
        for key, label in DEFAULT_FIELDS:
            if key not in existing_keys:
                session.add(FieldPermission(field_key=key, field_label=label, visible_to_user=True))

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_session():
    """Context-managed session: commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# --------------------------------------------------------------------------
# Kiosk / Multi-Location Identity
# --------------------------------------------------------------------------
def register_kiosk(session, mode_label: str = "USER") -> Kiosk:
    """
    Registers (or checks in) the machine this process is running on.

    Called once when Admin Mode or User Mode opens. Returns the live Kiosk
    ORM row (still attached to `session`) so the caller can immediately
    check `.is_active` before allowing scanning.
    """
    ident = kiosk_identity.get_identity()
    now = datetime.utcnow()

    kiosk = (
        session.query(Kiosk)
        .filter_by(mac_address=ident.mac_address, machine_username=ident.machine_username)
        .first()
    )

    if kiosk is None:
        kiosk = Kiosk(
            mac_address=ident.mac_address,
            machine_username=ident.machine_username,
            hostname=ident.hostname,
            location_label=ident.hostname or f"{ident.mac_address}",
            is_active=not config.KIOSK_REQUIRE_APPROVAL,
            last_mode_used=mode_label,
            first_seen=now,
            last_seen=now,
        )
        session.add(kiosk)
        session.flush()
        logger.info(
            "New kiosk registered: %s (%s / %s) — active=%s",
            kiosk.location_label, kiosk.mac_address, kiosk.machine_username, kiosk.is_active,
        )
    else:
        kiosk.last_seen = now
        kiosk.hostname = ident.hostname
        kiosk.last_mode_used = mode_label

    return kiosk


def log_kiosk_audit(session, kiosk, action: str, performed_by: str = None, details: str = None) -> KioskAuditLog:
    """
    Records one immutable audit entry for a kiosk administration action
    (APPROVED, BULK_APPROVED, BLOCKED, UNBLOCKED, RENAMED, REMOVED).

    Snapshot fields are captured from the live `kiosk` object at call time so
    the audit trail remains fully readable even after a kiosk is later removed.
    """
    entry = KioskAuditLog(
        kiosk_pk=kiosk.id if kiosk is not None else None,
        kiosk_location_snapshot=kiosk.location_label if kiosk is not None else None,
        kiosk_mac_snapshot=kiosk.mac_address if kiosk is not None else None,
        kiosk_username_snapshot=kiosk.machine_username if kiosk is not None else None,
        action=action,
        performed_by=performed_by,
        details=details,
    )
    session.add(entry)
    session.flush()
    return entry
