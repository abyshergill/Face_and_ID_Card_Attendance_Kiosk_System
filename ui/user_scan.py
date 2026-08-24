"""
User Mode: live camera scan screen.

Flow:
  - Camera preview runs continuously.
  - User clicks "Scan Face".
  - On success: shows an info card with only the Admin-permitted fields,
    logs the attendance event, and fires the physical PASS signal.
  - On failure: shows a "Try Again" message (no data is stored, no
    physical signal is fired... unless you want a FAIL pulse too).
"""
import logging
from datetime import datetime, timedelta

import cv2
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QImage, QPixmap
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

import config
import kiosk_identity
from database.db_manager import get_session, register_kiosk
from database.models import AttendanceLog, Employee, FieldPermission
from face_engine.recognizer import face_recognizer
from hardware.signal_controller import signal_controller

logger = logging.getLogger("attendance.ui.scan")

FIELD_DISPLAY_ORDER = ["name", "employee_id", "age", "department", "contact"]
FIELD_ICONS = {
    "name": "🧑", "employee_id": "🪪", "age": "🎂", "department": "🏢", "contact": "📞",
}
FIELD_TO_ATTR = {
    "name": "name", "employee_id": "employee_id", "age": "age",
    "department": "department", "contact": "contact",
}


class UserScanWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{config.APP_NAME} — Face Scan")
        self.resize(760, 680)

        self.cap = None
        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self._update_frame)
        self.model_sync_timer = QTimer(self)
        self.model_sync_timer.timeout.connect(self._auto_sync_model)
        self._last_frame = None
        self._scanning_locked = False

        self.kiosk_info = self._register_this_kiosk()

        self._build_ui()

        if self.kiosk_info["is_active"]:
            self._start_camera()
            self.model_sync_timer.start(max(config.MODEL_AUTO_SYNC_SECONDS, 5) * 1000)
        else:
            self._show_blocked_screen()

    # ------------------------------------------------------------------
    def _register_this_kiosk(self):
        """Checks this machine in with the central DB and returns its access status."""
        try:
            with get_session() as session:
                kiosk = register_kiosk(session, mode_label="USER")
                return {
                    "id": kiosk.id,
                    "location_label": kiosk.location_label,
                    "mac_address": kiosk.mac_address,
                    "machine_username": kiosk.machine_username,
                    "is_active": kiosk.is_active,
                }
        except Exception:
            logger.exception("Could not register this kiosk with the database — allowing scan as a fallback.")
            ident = kiosk_identity.get_identity()
            return {
                "id": None,
                "location_label": ident.hostname,
                "mac_address": ident.mac_address,
                "machine_username": ident.machine_username,
                "is_active": True,
            }

    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)

        title = QLabel("👁️  Face Attendance Scan")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        location = self.kiosk_info.get("location_label") or "Unregistered Location"
        kiosk_footer = QLabel(
            f"📍 {location}   •   MAC: {self.kiosk_info.get('mac_address', '—')}   •   "
            f"User: {self.kiosk_info.get('machine_username', '—')}"
        )
        kiosk_footer.setAlignment(Qt.AlignCenter)
        kiosk_footer.setStyleSheet("font-size:11px; color:#999; margin-bottom:4px;")
        layout.addWidget(kiosk_footer)

        self.camera_label = QLabel("Starting camera…")
        self.camera_label.setFixedSize(560, 400)
        self.camera_label.setStyleSheet("background:#111; border-radius:10px; color:#888;")
        self.camera_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.camera_label, alignment=Qt.AlignCenter)

        self.status_label = QLabel("Position your face inside the frame and click Scan.")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size:14px; color:#555; margin-top:8px;")
        layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        self.scan_btn = QPushButton("🔍  Scan Face")
        self.scan_btn.setStyleSheet(
            "font-size:16px; font-weight:600; padding:12px; background:#2d6cdf; color:white; border-radius:8px;"
        )
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        btn_row.addWidget(self.scan_btn)

        self.sync_btn = QPushButton("🔄  Sync Now")
        self.sync_btn.setToolTip("Manually re-check the shared face model for newly enrolled employees.")
        self.sync_btn.clicked.connect(lambda: self._auto_sync_model(manual=True))
        btn_row.addWidget(self.sync_btn)
        layout.addLayout(btn_row)

        # Result card (hidden until a scan completes)
        self.result_card = QFrame()
        self.result_card.setFrameShape(QFrame.StyledPanel)
        self.result_card.setStyleSheet(
            "QFrame { background:#f4f9f4; border:2px solid #2ecc71; border-radius:10px; padding:14px; }"
        )
        self.result_layout = QVBoxLayout(self.result_card)
        self.result_card.hide()
        layout.addWidget(self.result_card)

        self.setCentralWidget(central)

    # ------------------------------------------------------------------
    def _show_blocked_screen(self):
        self.camera_label.setText("🚫")
        self.camera_label.setStyleSheet(
            "background:#2c2c2c; border-radius:10px; color:#e74c3c; font-size:48px;"
        )
        self.scan_btn.setEnabled(False)
        self.sync_btn.setEnabled(False)
        self.status_label.setText(
            "This device is not authorized for attendance scanning yet.\n"
            "Please ask your administrator to approve this location from the Admin Dashboard."
        )
        self.status_label.setStyleSheet("font-size:14px; color:#c0392b; font-weight:600; margin-top:8px;")

    # ------------------------------------------------------------------
    def _auto_sync_model(self, manual=False):
        reloaded = face_recognizer.reload_if_changed()
        if reloaded:
            logger.info("Face model reloaded from shared storage (new/updated enrollment detected).")
            if manual:
                QMessageBox.information(self, "Model Synced", "Face recognition model updated successfully.")
            else:
                self.status_label.setText("🔄 Face model updated with the latest enrollments.")
                self.status_label.setStyleSheet("font-size:14px; color:#2d6cdf; font-weight:600; margin-top:8px;")
        elif manual:
            QMessageBox.information(self, "Already Up To Date", "The face recognition model is already up to date.")

    # ------------------------------------------------------------------
    def _start_camera(self):
        self.cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if not self.cap.isOpened():
            self.status_label.setText("⚠️ Could not access the camera. Check connection and restart.")
            self.scan_btn.setEnabled(False)
            return
        self.camera_timer.start(30)

    def _update_frame(self):
        if self.cap is None:
            return
        ok, frame = self.cap.read()
        if not ok:
            return
        self._last_frame = frame

        display_frame = frame.copy()
        _, box = face_recognizer.detect_face(display_frame)
        if box is not None:
            x, y, w, h = box
            cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 200, 0), 2)

        rgb = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
        h_, w_, ch = rgb.shape
        qimg = QImage(rgb.data, w_, h_, ch * w_, QImage.Format_RGB888)
        self.camera_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(self.camera_label.size(), Qt.KeepAspectRatio)
        )

    # ------------------------------------------------------------------
    def _on_scan_clicked(self):
        if self._scanning_locked or self._last_frame is None:
            return

        if not face_recognizer.is_trained:
            self._show_failure("No employees enrolled yet. Please contact your administrator.")
            return

        face_roi, box = face_recognizer.detect_face(self._last_frame)
        if face_roi is None:
            self._show_failure("No face detected. Please center your face in the frame and try again.")
            return

        employee_id, confidence = face_recognizer.predict(face_roi)

        if employee_id is None or confidence is None or confidence > config.RECOGNITION_CONFIDENCE_THRESHOLD:
            self._show_failure("Face not recognized. Please try again.")
            return

        self._handle_success(employee_id, confidence)

    # ------------------------------------------------------------------
    def _handle_success(self, employee_id, confidence):
        with get_session() as session:
            emp = session.query(Employee).filter_by(employee_id=employee_id, is_active=True).first()
            if not emp:
                self._show_failure("Recognized profile is no longer active. Please contact your administrator.")
                return

            emp_dict = emp.to_dict()

            recent_cutoff = datetime.utcnow() - timedelta(minutes=config.ATTENDANCE_COOLDOWN_MINUTES)
            recent_log = (
                session.query(AttendanceLog)
                .filter(AttendanceLog.employee_pk == emp.id, AttendanceLog.timestamp >= recent_cutoff)
                .first()
            )

            signal_sent = signal_controller.send_pass()

            if not recent_log:
                session.add(AttendanceLog(
                    employee_pk=emp.id,
                    employee_id_snapshot=emp.employee_id,
                    name_snapshot=emp.name,
                    kiosk_pk=self.kiosk_info.get("id"),
                    kiosk_mac_snapshot=self.kiosk_info.get("mac_address"),
                    kiosk_username_snapshot=self.kiosk_info.get("machine_username"),
                    kiosk_location_snapshot=self.kiosk_info.get("location_label"),
                    confidence_score=f"{confidence:.1f}",
                    status="SUCCESS",
                    signal_sent=signal_sent,
                ))
                already_marked = False
            else:
                already_marked = True

            permissions = {p.field_key: p.visible_to_user for p in session.query(FieldPermission).all()}

        logger.info("Attendance SUCCESS for %s (confidence=%.1f, signal_sent=%s)", employee_id, confidence, signal_sent)
        self._render_success_card(emp_dict, permissions, already_marked)

    def _render_success_card(self, emp_dict, permissions, already_marked):
        self.status_label.setText("✅ Face recognized successfully!" + (" (already recorded recently)" if already_marked else ""))
        self.status_label.setStyleSheet("font-size:14px; color:#1e8449; font-weight:600; margin-top:8px;")

        self._clear_layout(self.result_layout)
        header = QLabel("✅ Access Granted — Attendance Logged" if not already_marked else "ℹ️ Already Checked In Recently")
        header.setFont(QFont("Arial", 14, QFont.Bold))
        header.setStyleSheet("color:#1e8449;")
        self.result_layout.addWidget(header)

        any_field_shown = False
        for field_key in FIELD_DISPLAY_ORDER:
            if not permissions.get(field_key, True):
                continue
            attr = FIELD_TO_ATTR[field_key]
            value = emp_dict.get(attr)
            if value in (None, ""):
                continue
            any_field_shown = True
            row = QLabel(f"{FIELD_ICONS.get(field_key, '')}  <b>{field_key.replace('_', ' ').title()}:</b> {value}")
            row.setStyleSheet("font-size:13px; color:#222; padding:2px 0;")
            self.result_layout.addWidget(row)

        if not any_field_shown:
            note = QLabel("(Administrator has not enabled any fields for display.)")
            note.setStyleSheet("color:#777; font-style:italic;")
            self.result_layout.addWidget(note)

        self.result_card.setStyleSheet(
            "QFrame { background:#f4f9f4; border:2px solid #2ecc71; border-radius:10px; padding:14px; }"
        )
        self.result_card.show()

    def _show_failure(self, message):
        signal_controller.send_fail()
        self.status_label.setText(f"❌ {message}")
        self.status_label.setStyleSheet("font-size:14px; color:#c0392b; font-weight:600; margin-top:8px;")

        self._clear_layout(self.result_layout)
        header = QLabel("❌ Scan Failed")
        header.setFont(QFont("Arial", 14, QFont.Bold))
        header.setStyleSheet("color:#c0392b;")
        self.result_layout.addWidget(header)

        detail = QLabel(f"{message}  Please try again.")
        detail.setWordWrap(True)
        detail.setStyleSheet("font-size:13px; color:#333;")
        self.result_layout.addWidget(detail)

        self.result_card.setStyleSheet(
            "QFrame { background:#fdf2f2; border:2px solid #e74c3c; border-radius:10px; padding:14px; }"
        )
        self.result_card.show()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self.camera_timer.stop()
        self.model_sync_timer.stop()
        if self.cap is not None:
            self.cap.release()
        event.accept()
