"""
User Mode: live camera scan screen.

Flow:
  - Camera preview runs continuously without freezing.
  - Automatically detects and scans faces, or user can click "Scan Now".
  - On scan (success, fail, or no detection): shows result card for 5 seconds.
  - Pulls the profile picture safely from the database.
"""
import logging
from datetime import datetime, timedelta

import cv2
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QImage, QPixmap
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
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
    "name": "🧑", "employee_id": "🪪", "age": "🎂", 
    "department": "🏢", "contact": "📞"
}
FIELD_TO_ATTR = {
    "name": "name", "employee_id": "employee_id", "age": "age",
    "department": "department", "contact": "contact"
}

class UserScanWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{config.APP_NAME} — Face Scan")
        self.resize(1000, 680)
        self.setMinimumSize(800, 550)

        self.cap = None
        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self._update_frame)
        
        self.model_sync_timer = QTimer(self)
        self.model_sync_timer.timeout.connect(self._auto_sync_model)
        
        self.reset_scan_timer = QTimer(self)
        self.reset_scan_timer.setSingleShot(True)
        self.reset_scan_timer.timeout.connect(self._reset_scan_state)

        self._last_frame = None
        self._scanning_locked = False

        self.kiosk_info = self._register_this_kiosk()

        self._build_ui()

        if self.kiosk_info["is_active"]:
            self._start_camera()
            self.model_sync_timer.start(max(config.MODEL_AUTO_SYNC_SECONDS, 5) * 1000)
        else:
            self._show_blocked_screen()

    def _register_this_kiosk(self):
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
            logger.exception("Could not register kiosk.")
            ident = kiosk_identity.get_identity()
            return {
                "id": None, "location_label": ident.hostname,
                "mac_address": ident.mac_address, "machine_username": ident.machine_username,
                "is_active": True,
            }

    def _build_ui(self):
        central = QWidget()
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)
        
        title = QLabel("Face Attendance Kiosk")
        title.setFont(QFont("Arial", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(title)

        location = self.kiosk_info.get("location_label") or "Unregistered Location"
        kiosk_footer = QLabel(f"📍 {location}   •   MAC: {self.kiosk_info.get('mac_address', '—')}")
        kiosk_footer.setAlignment(Qt.AlignCenter)
        kiosk_footer.setStyleSheet("font-size:12px; color:#777;")
        header_layout.addWidget(kiosk_footer)

        main_layout.addLayout(header_layout)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(20)

        # Left Pane: Camera
        cam_container = QWidget()
        cam_layout = QVBoxLayout(cam_container)
        cam_layout.setContentsMargins(0, 0, 0, 0)

        self.camera_label = QLabel("Starting camera…")
        self.camera_label.setMinimumSize(480, 360)
        self.camera_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.camera_label.setStyleSheet("background:#111; border: 2px solid #333; border-radius:12px; color:#888;")
        self.camera_label.setAlignment(Qt.AlignCenter)
        cam_layout.addWidget(self.camera_label)

        body_layout.addWidget(cam_container, stretch=3)

        # Right Pane: Controls & Results
        right_panel = QWidget()
        right_panel.setMinimumWidth(320)
        right_panel.setMaximumWidth(420)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(15)

        self.status_label = QLabel("🔍 Scanning for faces...")
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size:14px; font-weight:600; color:#2d6cdf; background:#eef4ff; padding:12px; border-radius:8px; border:1px solid #d0e1fd;")
        right_layout.addWidget(self.status_label)

        self.result_card = QFrame()
        self.result_card.setFrameShape(QFrame.StyledPanel)
        self.result_card.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.result_card.setStyleSheet("QFrame { background:#f4f9f4; border:2px solid #2ecc71; border-radius:10px; padding:16px; }")
        self.result_layout = QVBoxLayout(self.result_card)
        self.result_card.hide()
        right_layout.addWidget(self.result_card)

        right_layout.addStretch()

        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("📷 Scan Now")
        self.scan_btn.setStyleSheet("font-size:13px; font-weight:bold; padding:10px; border-radius:6px; background:#2d6cdf; color:white;")
        self.scan_btn.clicked.connect(self._on_scan_clicked)
        btn_layout.addWidget(self.scan_btn)

        self.sync_btn = QPushButton("🔄 Sync Model")
        self.sync_btn.setStyleSheet("font-size:13px; font-weight:bold; padding:10px; border-radius:6px; background:#f0f0f0; color:#333;")
        self.sync_btn.clicked.connect(lambda: self._auto_sync_model(manual=True))
        btn_layout.addWidget(self.sync_btn)

        right_layout.addLayout(btn_layout)
        body_layout.addWidget(right_panel, stretch=2)

        main_layout.addLayout(body_layout)
        self.setCentralWidget(central)

    def _show_blocked_screen(self):
        self.camera_label.setText("🚫")
        self.camera_label.setStyleSheet("background:#2c2c2c; border-radius:10px; color:#e74c3c; font-size:48px;")
        self.sync_btn.setEnabled(False)
        self.scan_btn.setEnabled(False)
        self.status_label.setText("This device is not authorized for attendance scanning.")
        self.status_label.setStyleSheet("font-size:14px; color:#c0392b; background:#fdf2f2; padding:12px; border-radius:8px;")

    def _auto_sync_model(self, manual=False):
        reloaded = face_recognizer.reload_if_changed()
        if reloaded:
            logger.info("Face model reloaded from disk.")
            if manual:
                QMessageBox.information(self, "Model Synced", "Face recognition model updated successfully.")
            else:
                self.status_label.setText("🔄 Face model updated.")
        elif manual:
            QMessageBox.information(self, "Up To Date", "The face recognition model is already up to date.")

    def _start_camera(self):
        self.cap = cv2.VideoCapture(config.CAMERA_INDEX)
        if not self.cap.isOpened():
            self.status_label.setText("⚠️ Could not access the camera.")
            self.status_label.setStyleSheet("font-size:14px; color:#c0392b; background:#fdf2f2; padding:12px; border-radius:8px;")
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
        
        face_roi, box = face_recognizer.detect_face(display_frame)

        if box is not None:
            x, y, w, h = box
            cv2.rectangle(display_frame, (x, y), (x + w, y + h), (0, 200, 0), 2)
            if not self._scanning_locked:
                self._process_auto_scan(face_roi)

        self._set_camera_image(display_frame)

    def _set_camera_image(self, bgr_frame):
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        h_, w_, ch = rgb.shape
        qimg = QImage(rgb.data, w_, h_, ch * w_, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        self.camera_label.setPixmap(pixmap.scaled(self.camera_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def _on_scan_clicked(self):
        if self._scanning_locked or self._last_frame is None:
            return
        self._scanning_locked = True
        self.scan_btn.setEnabled(False)

        if not face_recognizer.is_trained:
            self._show_failure("No employees enrolled yet.")
            self.reset_scan_timer.start(5000)
            return

        display_frame = self._last_frame.copy()
        face_roi, _ = face_recognizer.detect_face(display_frame)

        if face_roi is None:
            self._show_failure("No face detected. Please face the camera and try again.")
            self.reset_scan_timer.start(5000)
            return

        self._execute_prediction(face_roi)

    def _process_auto_scan(self, face_roi):
        self._scanning_locked = True 
        self.scan_btn.setEnabled(False)

        if not face_recognizer.is_trained:
            self._show_failure("No employees enrolled yet.")
            self.reset_scan_timer.start(5000)
            return

        self._execute_prediction(face_roi)

    def _execute_prediction(self, face_roi):
        employee_id, confidence = face_recognizer.predict(face_roi)

        if employee_id is None or confidence is None or confidence > config.RECOGNITION_CONFIDENCE_THRESHOLD:
            self._show_failure("Face not recognized. Please try again.")
            self.reset_scan_timer.start(5000)
            return

        self._handle_success(employee_id, confidence)
        self.reset_scan_timer.start(5000)

    def _reset_scan_state(self):
        self.result_card.hide()
        self.status_label.setText("🔍 Scanning for faces...")
        self.status_label.setStyleSheet("font-size:14px; font-weight:600; color:#2d6cdf; background:#eef4ff; padding:12px; border-radius:8px; border:1px solid #d0e1fd;")
        self.scan_btn.setEnabled(True)
        self._scanning_locked = False

    def _handle_success(self, employee_id, confidence):
        with get_session() as session:
            emp = session.query(Employee).filter_by(employee_id=employee_id, is_active=True).first()
            if not emp:
                self._show_failure("Recognized profile is inactive.")
                return

            emp_dict = emp.to_dict()

            recent_cutoff = datetime.utcnow() - timedelta(minutes=config.ATTENDANCE_COOLDOWN_MINUTES)
            recent_log = session.query(AttendanceLog).filter(AttendanceLog.employee_pk == emp.id, AttendanceLog.timestamp >= recent_cutoff).first()

            # Trigger Hardware Signal (Now safely checking DB global toggle)
            signal_sent = signal_controller.send_pass()

            if not recent_log:
                session.add(AttendanceLog(
                    employee_pk=emp.id, employee_id_snapshot=emp.employee_id,
                    name_snapshot=emp.name, kiosk_pk=self.kiosk_info.get("id"),
                    kiosk_mac_snapshot=self.kiosk_info.get("mac_address"),
                    kiosk_username_snapshot=self.kiosk_info.get("machine_username"),
                    kiosk_location_snapshot=self.kiosk_info.get("location_label"),
                    confidence_score=f"{confidence:.1f}", status="SUCCESS", signal_sent=signal_sent,
                ))
                already_marked = False
            else:
                already_marked = True

            permissions = {p.field_key: p.visible_to_user for p in session.query(FieldPermission).all()}

        logger.info(f"Attendance SUCCESS for {employee_id} (confidence={confidence:.1f}, signal_sent={signal_sent})")
        self._render_success_card(emp_dict, permissions, already_marked)

    def _render_success_card(self, emp_dict, permissions, already_marked):
        status_text = "✅ Access Granted!" if not already_marked else "ℹ️ Already Logged Recently"
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet("font-size:14px; font-weight:600; color:#1e8449; background:#eafaf1; padding:12px; border-radius:8px; border:1px solid #a3e4d7;")

        self._clear_layout(self.result_layout)
        
        # Split Layout: Left for Photo, Right for Text
        card_inner_layout = QHBoxLayout()
        card_inner_layout.setSpacing(15)

        # --- LEFT: Profile Photo from Database ---
        photo_label = QLabel()
        photo_label.setFixedSize(120, 160)
        photo_label.setAlignment(Qt.AlignCenter)
        photo_label.setStyleSheet("border: 2px solid #ccc; border-radius: 8px; background: #fff;")
        
        image_loaded = False
        prof_pic_bytes = emp_dict.get("profile_picture_data")
        
        if prof_pic_bytes:
            pixmap = QPixmap()
            if pixmap.loadFromData(prof_pic_bytes):
                photo_label.setPixmap(pixmap.scaled(photo_label.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
                image_loaded = True

        if not image_loaded:
            photo_label.setText("No Image")
            photo_label.setStyleSheet("border: 2px dashed #ccc; border-radius: 8px; background: #fafafa; color: #888;")

        card_inner_layout.addWidget(photo_label)

        # --- RIGHT: Employee Text Details ---
        details_layout = QVBoxLayout()
        details_layout.setAlignment(Qt.AlignVCenter)
        
        header = QLabel("Attendance Recorded" if not already_marked else "Already Checked In")
        header.setFont(QFont("Arial", 12, QFont.Bold))
        header.setStyleSheet("color:#1e8449; margin-bottom: 6px;")
        details_layout.addWidget(header)

        any_field_shown = False
        for field_key in FIELD_DISPLAY_ORDER:
            if permissions.get(field_key, True):
                val = emp_dict.get(FIELD_TO_ATTR[field_key])
                if val:
                    any_field_shown = True
                    row = QLabel(f"{FIELD_ICONS.get(field_key, '')} <b>{field_key.replace('_', ' ').title()}:</b> {val}")
                    row.setStyleSheet("font-size:13px; color:#222; padding:2px 0;")
                    details_layout.addWidget(row)

        if not any_field_shown:
            note = QLabel("(Administrator restricted field displays.)")
            note.setStyleSheet("color:#777; font-style:italic;")
            details_layout.addWidget(note)

        card_inner_layout.addLayout(details_layout)
        card_inner_layout.addStretch()

        self.result_layout.addLayout(card_inner_layout)
        self.result_card.setStyleSheet("QFrame { background:#f4f9f4; border:2px solid #2ecc71; border-radius:10px; padding:14px; }")
        self.result_card.show()

    def _show_failure(self, message):
        signal_controller.send_fail()
        self.status_label.setText("❌ Scan Failed")
        self.status_label.setStyleSheet("font-size:14px; font-weight:600; color:#c0392b; background:#fdf2f2; padding:12px; border-radius:8px; border:1px solid #f5b7b1;")

        self._clear_layout(self.result_layout)
        header = QLabel("❌ Access Denied")
        header.setFont(QFont("Arial", 13, QFont.Bold))
        header.setStyleSheet("color:#c0392b; margin-bottom: 6px;")
        self.result_layout.addWidget(header)

        detail = QLabel(message)
        detail.setWordWrap(True)
        detail.setStyleSheet("font-size:13px; color:#444;")
        self.result_layout.addWidget(detail)

        self.result_card.setStyleSheet("QFrame { background:#fdf2f2; border:2px solid #e74c3c; border-radius:10px; padding:14px; }")
        self.result_card.show()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                UserScanWindow._clear_layout(item.layout())
                item.layout().deleteLater()

    def closeEvent(self, event):
        # 1. Instantly hide the window so the user doesn't see a frozen screen
        self.hide()
        
        # 2. Stop all background timers
        self.camera_timer.stop()
        self.model_sync_timer.stop()
        self.reset_scan_timer.stop()
        
        # 3. Release the camera hardware safely
        # (This is the part that takes Windows 2-3 seconds to process)
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            
        event.accept()