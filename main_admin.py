#!/usr/bin/env python3
"""
Face Attendance System — ADMIN Entry Point.
Run this on the Manager/IT PC to set up the DB and manage the system.
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

def main():
    setup_logging()
    logger = logging.getLogger("attendance.admin")
    logger.info("Starting %s v%s (ADMIN MODE)", config.APP_NAME, config.APP_VERSION)

    # Admin is allowed to create tables and seed default users
    from database.db_manager import init_db
    init_db()

    from PyQt5.QtWidgets import QApplication
    from ui.admin_login import AdminLoginDialog
    from ui.admin_dashboard import AdminDashboard

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    # Go straight to login
    login = AdminLoginDialog()
    if login.exec_():
        dashboard = AdminDashboard(login.authenticated_username)
        dashboard.show()
        exit_code = app.exec_()
    else:
        exit_code = 0

    logger.info("Admin application closed with exit code %s", exit_code)
    sys.exit(exit_code)

if __name__ == "__main__":
    main()