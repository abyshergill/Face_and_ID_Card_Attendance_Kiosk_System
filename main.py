#!/usr/bin/env python3
"""
Face Attendance System — application entry point.

Usage:
    python main.py

On first run this will:
  - create ./data/attendance.db (SQLite) with all required tables
  - seed a default admin account (see config.py for credentials — CHANGE
    THE PASSWORD after first login)
  - seed default field-visibility permissions (all fields visible)

See README.md for full setup, hardware-integration, and PostgreSQL
migration instructions.
"""
import logging
import sys

import config


def setup_logging():
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def main():
    setup_logging()
    logger = logging.getLogger("attendance.main")
    logger.info("Starting %s v%s", config.APP_NAME, config.APP_VERSION)

    from database.db_manager import init_db
    init_db()

    from PyQt5.QtWidgets import QApplication
    from ui.mode_select import ModeSelectWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = ModeSelectWindow()
    window.show()

    exit_code = app.exec_()

    try:
        from hardware.signal_controller import signal_controller
        signal_controller.close()
    except Exception:
        pass

    logger.info("Application closed with exit code %s", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
