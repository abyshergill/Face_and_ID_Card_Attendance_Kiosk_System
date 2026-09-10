"""SQLAlchemy ORM models for the Face Attendance System."""
from datetime import datetime
from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, String, 
    UniqueConstraint, LargeBinary
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class AdminAccount(Base):
    __tablename__ = "admin_accounts"
    id = Column(Integer, primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    salt = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    failed_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)

class FieldPermission(Base):
    __tablename__ = "field_permissions"
    id = Column(Integer, primary_key=True)
    field_key = Column(String(64), unique=True, nullable=False)
    field_label = Column(String(120), nullable=False)
    visible_to_user = Column(Boolean, default=True)

class Kiosk(Base):
    __tablename__ = "kiosks"
    __table_args__ = (UniqueConstraint("mac_address", "machine_username", name="uq_kiosk_identity"),)

    id = Column(Integer, primary_key=True)
    mac_address = Column(String(64), nullable=False, index=True)
    machine_username = Column(String(120), nullable=False)
    hostname = Column(String(120), nullable=True)
    location_label = Column(String(150), nullable=True) 

    is_active = Column(Boolean, default=True)
    # NEW: Per-Kiosk Hardware Signal Toggle
    hw_signal_enabled = Column(Boolean, default=False)
    last_mode_used = Column(String(20), default="USER") 

    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)

    attendance_logs = relationship("AttendanceLog", back_populates="kiosk")

class KioskAuditLog(Base):
    __tablename__ = "kiosk_audit_logs"
    id = Column(Integer, primary_key=True)
    kiosk_pk = Column(Integer, ForeignKey("kiosks.id"), nullable=True)
    kiosk_location_snapshot = Column(String(150), nullable=True)
    kiosk_mac_snapshot = Column(String(64), nullable=True)
    kiosk_username_snapshot = Column(String(120), nullable=True)
    action = Column(String(30), nullable=False)
    performed_by = Column(String(64), nullable=True)
    details = Column(String(255), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    kiosk = relationship("Kiosk")

class Employee(Base):
    __tablename__ = "employees"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    age = Column(Integer)
    department = Column(String)
    contact = Column(String)
    photo_dir = Column(String, nullable=True)
    profile_picture_data = Column(LargeBinary, nullable=True) 
    face_label = Column(Integer, unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    attendance_logs = relationship("AttendanceLog", back_populates="employee", cascade="all, delete-orphan")
    photos = relationship("EmployeePhoto", back_populates="employee", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": self.id, "employee_id": self.employee_id, "name": self.name,
            "age": self.age, "department": self.department, "contact": self.contact,
            "profile_picture_data": self.profile_picture_data,
        }

class EmployeePhoto(Base):
    __tablename__ = "employee_photos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    employee_pk = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    image_data = Column(LargeBinary, nullable=False)
    employee = relationship("Employee", back_populates="photos")

class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    id = Column(Integer, primary_key=True)
    employee_pk = Column(Integer, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True)
    employee_id_snapshot = Column(String(32), nullable=True)
    name_snapshot = Column(String(120), nullable=True)
    kiosk_pk = Column(Integer, ForeignKey("kiosks.id", ondelete="SET NULL"), nullable=True)
    kiosk_mac_snapshot = Column(String(64), nullable=True)
    kiosk_username_snapshot = Column(String(120), nullable=True)
    kiosk_location_snapshot = Column(String(150), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    confidence_score = Column(String(20), nullable=True)
    status = Column(String(20), default="SUCCESS")
    signal_sent = Column(Boolean, default=False)
    employee = relationship("Employee", back_populates="attendance_logs")
    kiosk = relationship("Kiosk", back_populates="attendance_logs")

class SystemLog(Base):
    __tablename__ = "system_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    level = Column(String(20))
    logger_name = Column(String(100))
    message = Column(String)