#!/usr/bin/env python3
"""
Face Attendance System — KIOSK Entry Point.
Run this on the physical door/turnstile PCs. Contains ZERO admin code.
"""
import logging
import sys
import datetime
import config

class DatabaseLogHandler(logging.Handler):
    def emit(self, record):
        if record.name.startswith('sqlalchemy'):
            return
        try:
            from database.db_manager import engine
            from database.models import SystemLog
            from sqlalchemy.orm import sessionmaker
            LogSession = sessionmaker(bind=engine)
            with LogSession() as session:
                log_entry = SystemLog(
                    level=record.levelname,
                    logger_name=record.name,
                    message=record.getMessage(),
                    timestamp=datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc)
                )
                session.add(log_entry)
                session.commit()
        except Exception:
            pass

def setup_logging():
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    db_handler = DatabaseLogHandler()
    logging.basicConfig(level=getattr(logging, config.LOG_LEVEL, logging.INFO), handlers=[console_handler, db_handler])

# --- UI Imports (NO ADMIN IMPORTS HERE) ---
from PyQt5.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from ui.user_scan import UserScanWindow
from ui.employee_scan import EmployeeCardScanWindow

class KioskModeSelect(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.APP_NAME} - Kiosk Mode")
        self.resize(480, 350)
        self._child_window = None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)

        title = QLabel("Select Kiosk Mode")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        face_btn = QPushButton("📷 Face Scan Kiosk")
        face_btn.setMinimumHeight(60)
        face_btn.setStyleSheet("font-size:16px; font-weight:bold; background:#2d6cdf; color:white; border-radius:10px;")
        face_btn.clicked.connect(self._open_face)
        layout.addWidget(face_btn)

        card_btn = QPushButton("💳 ID Card Kiosk")
        card_btn.setMinimumHeight(60)
        card_btn.setStyleSheet("font-size:16px; font-weight:bold; background:#8e44ad; color:white; border-radius:10px;")
        card_btn.clicked.connect(self._open_card)
        layout.addWidget(card_btn)

        self.setCentralWidget(central)

    def _open_face(self):
        self._child_window = UserScanWindow()
        self._child_window.show()
        self.close()

    def _open_card(self):
        self._child_window = EmployeeCardScanWindow()
        self._child_window.show()
        self.close()


def main():
    setup_logging()
    logger = logging.getLogger("attendance.kiosk")
    logger.info("Starting %s v%s (KIOSK MODE)", config.APP_NAME, config.APP_VERSION)

    # NOTE: We DO NOT call init_db() here. 
    # The Kiosk uses a restricted DB user and cannot create tables.
    # The Admin PC must be run at least once first to setup the database.

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = KioskModeSelect()
    window.show()

    exit_code = app.exec_()

    try:
        from hardware.signal_controller import signal_controller
        signal_controller.close()
    except Exception:
        pass

    logger.info("Kiosk application closed with exit code %s", exit_code)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()