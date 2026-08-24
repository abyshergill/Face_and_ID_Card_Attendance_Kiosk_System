"""
SQLAlchemy ORM models for the Face Attendance System.
Works identically against SQLite (current) and PostgreSQL (production) -
no model code changes are required when switching databases.
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class AdminAccount(Base):
    """Administrator login credentials (password stored as salted PBKDF2 hash)."""
    __tablename__ = "admin_accounts"

    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    salt = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Employee(Base):
    """A registered employee/user enrolled for face attendance."""
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True)
    employee_id = Column(String(32), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    age = Column(Integer, nullable=True)
    department = Column(String(120), nullable=True)
    contact = Column(String(120), nullable=True)

    photo_dir = Column(String(255), nullable=False)          # folder holding enrollment photos
    face_label = Column(Integer, unique=True, nullable=False)  # numeric label used internally by the LBPH recognizer

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    attendance_logs = relationship(
        "AttendanceLog", back_populates="employee", cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "employee_id": self.employee_id,
            "name": self.name,
            "age": self.age,
            "department": self.department,
            "contact": self.contact,
        }


class FieldPermission(Base):
    """
    Controls which employee data fields the Admin has chosen to reveal on
    the User (scan) side after a successful recognition.
    """
    __tablename__ = "field_permissions"

    id = Column(Integer, primary_key=True)
    field_key = Column(String(64), unique=True, nullable=False)   # e.g. "name", "age"
    field_label = Column(String(120), nullable=False)             # e.g. "Name", "Age"
    visible_to_user = Column(Boolean, default=True)


class Kiosk(Base):
    """
    A physical machine (scan kiosk or admin PC) that has connected to this
    (centralized) database. Identity = MAC address + OS username, which
    together uniquely identify a station across a multi-PC deployment.

    Admins can rename ("Main Gate", "Building B Entrance"), and
    activate/deactivate a kiosk's ability to log attendance from the
    central Admin Dashboard - this is the physical access-control layer
    for which machines are allowed to write attendance data.
    """
    __tablename__ = "kiosks"
    __table_args__ = (
        UniqueConstraint("mac_address", "machine_username", name="uq_kiosk_identity"),
    )

    id = Column(Integer, primary_key=True)
    mac_address = Column(String(64), nullable=False, index=True)
    machine_username = Column(String(120), nullable=False)
    hostname = Column(String(120), nullable=True)
    location_label = Column(String(150), nullable=True)  # admin-editable friendly name

    is_active = Column(Boolean, default=True)   # False = blocked from scanning
    last_mode_used = Column(String(20), default="USER")  # USER | ADMIN

    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)

    attendance_logs = relationship("AttendanceLog", back_populates="kiosk")

    def to_dict(self):
        return {
            "id": self.id,
            "mac_address": self.mac_address,
            "machine_username": self.machine_username,
            "hostname": self.hostname,
            "location_label": self.location_label,
            "is_active": self.is_active,
            "last_mode_used": self.last_mode_used,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


class KioskAuditLog(Base):
    """
    Immutable audit trail of every kiosk approval/access-control action taken
    by an admin (approve, bulk-approve, block, unblock, rename, remove).
    Kept separate from AttendanceLog (which is about face-scan events, not
    kiosk administration) so the two histories never mix.
    """
    __tablename__ = "kiosk_audit_logs"

    id = Column(Integer, primary_key=True)
    kiosk_pk = Column(Integer, ForeignKey("kiosks.id"), nullable=True)
    kiosk_location_snapshot = Column(String(150), nullable=True)
    kiosk_mac_snapshot = Column(String(64), nullable=True)
    kiosk_username_snapshot = Column(String(120), nullable=True)

    action = Column(String(30), nullable=False)
    # one of: APPROVED | BULK_APPROVED | BLOCKED | UNBLOCKED | RENAMED | REMOVED
    performed_by = Column(String(64), nullable=True)   # admin username
    details = Column(String(255), nullable=True)       # e.g. "'Lobby' -> 'Main Gate'"

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    kiosk = relationship("Kiosk")


class AttendanceLog(Base):
    """One row per successful (or failed) attendance scan event."""
    __tablename__ = "attendance_logs"

    id = Column(Integer, primary_key=True)
    employee_pk = Column(Integer, ForeignKey("employees.id"), nullable=True)
    employee_id_snapshot = Column(String(32), nullable=True)  # kept even if employee is later deleted
    name_snapshot = Column(String(120), nullable=True)

    kiosk_pk = Column(Integer, ForeignKey("kiosks.id"), nullable=True)
    kiosk_mac_snapshot = Column(String(64), nullable=True)       # kept even if kiosk is later removed
    kiosk_username_snapshot = Column(String(120), nullable=True)
    kiosk_location_snapshot = Column(String(150), nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    confidence_score = Column(String(20), nullable=True)
    status = Column(String(20), default="SUCCESS")   # SUCCESS | FAILED
    signal_sent = Column(Boolean, default=False)

    employee = relationship("Employee", back_populates="attendance_logs")
    kiosk = relationship("Kiosk", back_populates="attendance_logs")
