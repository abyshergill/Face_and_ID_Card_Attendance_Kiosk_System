"""
Employee Card Scan Mode.
"""
import logging
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget
)

import config
import kiosk_identity
from database.db_manager import get_session, register_kiosk
from database.models import AttendanceLog, Employee, FieldPermission, EmployeePhoto
from hardware.signal_controller import signal_controller

logger = logging.getLogger("attendance.ui.card_scan")

FIELD_DISPLAY_ORDER = ["name", "employee_id", "age", "department", "contact"]
FIELD_ICONS = {
    "name": "🧑", "employee_id": "🪪", "age": "🎂", 
    "department": "🏢", "contact": "📞"
}
FIELD_TO_ATTR = {
    "name": "name", "employee_id": "employee_id", "age": "age",
    "department": "department", "contact": "contact"
}

class EmployeeCardScanWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{config.APP_NAME} — Card Scan")
        self.resize(1000, 700)
        self.setMinimumSize(800, 600)

        self._is_blocked = False

        self.inactivity_timer = QTimer(self)
        self.inactivity_timer.setSingleShot(True)
        self.inactivity_timer.timeout.connect(self._clear_screen)

        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self._maintain_focus)
        
        self.kiosk_info = self._register_this_kiosk()
        self._build_ui()

        if self.kiosk_info["is_active"]:
            self.focus_timer.start(500)
        else:
            self._show_blocked_screen()

    def _register_this_kiosk(self):
        try:
            with get_session() as session:
                kiosk = register_kiosk(session, mode_label="CARD_SCAN")
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
        self.setCentralWidget(central)

        outer_layout = QVBoxLayout(central)
        outer_layout.addStretch(1)

        h_center_layout = QHBoxLayout()
        h_center_layout.addStretch(1)

        content_container = QWidget()
        content_container.setMaximumWidth(850)
        content_container.setMinimumWidth(600)
        
        main_layout = QVBoxLayout(content_container)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(25)

        title = QLabel("💳 Card Attendance Kiosk")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        location = self.kiosk_info.get("location_label") or "Unregistered Location"
        kiosk_footer = QLabel(f"📍 {location}   •   MAC: {self.kiosk_info.get('mac_address', '—')}")
        kiosk_footer.setAlignment(Qt.AlignCenter)
        kiosk_footer.setStyleSheet("font-size:13px; color:#777;")
        main_layout.addWidget(kiosk_footer)

        self.status_label = QLabel("Please tap your Employee ID Card or enter it below")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet(
            "font-size:18px; font-weight:600; color:#2d6cdf; background:#eef4ff; "
            "padding:20px; border-radius:10px; border:1px solid #d0e1fd; margin-top:10px;"
        )
        main_layout.addWidget(self.status_label)

        input_layout = QHBoxLayout()
        input_layout.setSpacing(15)
        
        self.card_input = QLineEdit()
        self.card_input.setPlaceholderText("Scan card or type ID here...")
        self.card_input.setAlignment(Qt.AlignCenter)
        self.card_input.setStyleSheet(
            "font-size: 20px; padding: 15px; border: 2px solid #ccc; border-radius: 8px;"
        )
        self.card_input.returnPressed.connect(self._process_scan)
        input_layout.addWidget(self.card_input, stretch=4)

        self.submit_btn = QPushButton("Submit")
        self.submit_btn.setStyleSheet(
            "font-size:18px; font-weight:bold; padding:15px 30px; border-radius:8px; background:#2d6cdf; color:white;"
        )
        self.submit_btn.clicked.connect(self._process_scan)
        input_layout.addWidget(self.submit_btn, stretch=1)
        
        main_layout.addLayout(input_layout)

        self.result_card = QFrame()
        self.result_card.setFrameShape(QFrame.StyledPanel)
        self.result_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.result_card.setStyleSheet(
            "QFrame { background:#f4f9f4; border:2px solid #2ecc71; border-radius:12px; padding:20px; }"
        )
        self.result_layout = QVBoxLayout(self.result_card)
        self.result_card.hide()
        
        main_layout.addWidget(self.result_card)
        
        h_center_layout.addWidget(content_container, stretch=3)
        h_center_layout.addStretch(1)
        
        outer_layout.addLayout(h_center_layout)
        outer_layout.addStretch(2)

    def _maintain_focus(self):
        if not self._is_blocked and not self.card_input.hasFocus():
            self.card_input.setFocus()

    def _show_blocked_screen(self):
        self._is_blocked = True
        self.status_label.setText("🚫 This device is not authorized for scanning.")
        self.status_label.setStyleSheet("font-size:18px; color:#c0392b; background:#fdf2f2; padding:20px; border-radius:10px;")
        self.card_input.setEnabled(False)
        self.submit_btn.setEnabled(False)

    def _process_scan(self):
        if self._is_blocked:
            return

        scanned_id = self.card_input.text().strip()
        self.card_input.clear()

        if not scanned_id:
            return

        self.inactivity_timer.start(5000)

        with get_session() as session:
            emp = session.query(Employee).filter_by(employee_id=scanned_id, is_active=True).first()
            
            if not emp:
                self._show_failure(f"Employee ID '{scanned_id}' not found or inactive.")
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
                session.add(
                    AttendanceLog(
                        employee_pk=emp.id, employee_id_snapshot=emp.employee_id,
                        name_snapshot=emp.name, kiosk_pk=self.kiosk_info.get("id"),
                        kiosk_mac_snapshot=self.kiosk_info.get("mac_address"),
                        kiosk_username_snapshot=self.kiosk_info.get("machine_username"),
                        kiosk_location_snapshot=self.kiosk_info.get("location_label"),
                        confidence_score="N/A (Card)", status="SUCCESS", signal_sent=signal_sent,
                    )
                )
                already_marked = False
            else:
                already_marked = True

            permissions = {p.field_key: p.visible_to_user for p in session.query(FieldPermission).all()}

        self._render_success_card(emp_dict, permissions, already_marked)
        self.card_input.setFocus()

    def _render_success_card(self, emp_dict, permissions, already_marked):
        status_text = "✅ Access Granted!" if not already_marked else "ℹ️ Already Logged Recently"
        self.status_label.setText(status_text)
        self.status_label.setStyleSheet("font-size:18px; font-weight:600; color:#1e8449; background:#eafaf1; padding:20px; border-radius:10px;")

        self._clear_layout(self.result_layout)
        
        card_inner_layout = QHBoxLayout()
        card_inner_layout.setSpacing(30)

        photo_label = QLabel()
        photo_label.setFixedSize(160, 200)
        photo_label.setAlignment(Qt.AlignCenter)
        photo_label.setStyleSheet("border: 2px solid #ccc; border-radius: 8px; background: #fff;")
        
        image_loaded = False
        
        # --- NEW: Fetch the dedicated Profile Picture from the Dictionary ---
        prof_pic_bytes = emp_dict.get("profile_picture_data")
        
        if prof_pic_bytes:
            pixmap = QPixmap()
            if pixmap.loadFromData(prof_pic_bytes):
                photo_label.setPixmap(pixmap.scaled(
                    photo_label.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                ))
                image_loaded = True

        if not image_loaded:
            photo_label.setText("No Image\nFound")
            photo_label.setFont(QFont("Arial", 12))
            photo_label.setStyleSheet("border: 2px dashed #ccc; border-radius: 8px; background: #fafafa; color: #888;")

        card_inner_layout.addWidget(photo_label)

        details_layout = QVBoxLayout()
        details_layout.setAlignment(Qt.AlignVCenter)
        
        header = QLabel("Attendance Recorded" if not already_marked else "Already Checked In")
        header.setFont(QFont("Arial", 18, QFont.Bold))
        header.setStyleSheet("color:#1e8449; margin-bottom: 12px;")
        details_layout.addWidget(header)

        for field_key in FIELD_DISPLAY_ORDER:
            if permissions.get(field_key, True):
                val = emp_dict.get(FIELD_TO_ATTR[field_key])
                if val:
                    row = QLabel(f"{FIELD_ICONS.get(field_key, '')} <b>{field_key.replace('_', ' ').title()}:</b> {val}")
                    row.setStyleSheet("font-size:16px; color:#222; padding:5px 0;")
                    details_layout.addWidget(row)

        card_inner_layout.addLayout(details_layout)
        card_inner_layout.addStretch()

        self.result_layout.addLayout(card_inner_layout)
        self.result_card.setStyleSheet("QFrame { background:#f4f9f4; border:2px solid #2ecc71; border-radius:12px; padding:20px; }")
        self.result_card.show()

    def _show_failure(self, message):
        signal_controller.send_fail()
        self.status_label.setText("❌ Scan Failed")
        self.status_label.setStyleSheet("font-size:18px; font-weight:600; color:#c0392b; background:#fdf2f2; padding:20px; border-radius:10px;")

        self._clear_layout(self.result_layout)
        header = QLabel("❌ Access Denied")
        header.setFont(QFont("Arial", 18, QFont.Bold))
        header.setStyleSheet("color:#c0392b; margin-bottom: 12px;")
        self.result_layout.addWidget(header)

        detail = QLabel(message)
        detail.setStyleSheet("font-size:16px; color:#444;")
        self.result_layout.addWidget(detail)

        self.result_card.setStyleSheet("QFrame { background:#fdf2f2; border:2px solid #e74c3c; border-radius:12px; padding:20px; }")
        self.result_card.show()
        self.card_input.setFocus() 

    def _clear_screen(self):
        self.result_card.hide()
        self.status_label.setText("Please tap your Employee ID Card or enter it below")
        self.status_label.setStyleSheet(
            "font-size:18px; font-weight:600; color:#2d6cdf; background:#eef4ff; "
            "padding:20px; border-radius:10px; border:1px solid #d0e1fd; margin-top:10px;"
        )
        self.card_input.setFocus()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                EmployeeCardScanWindow._clear_layout(item.layout())
                item.layout().deleteLater()

    def closeEvent(self, event):
        self.focus_timer.stop()
        self.inactivity_timer.stop()
        event.accept()