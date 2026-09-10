#!/usr/bin/env python3
"""
Face Attendance System — application entry point.
"""
import logging
import sys
import datetime

import config

from PyQt5.QtWidgets import QApplication
from ui.mode_select import ModeSelectWindow
from database.db_manager import init_db

class DatabaseLogHandler(logging.Handler):
    """Custom logging handler that writes logs directly to the database."""
    def emit(self, record):
        # Ignore internal SQLAlchemy logs to prevent infinite recursion
        if record.name.startswith('sqlalchemy'):
            return
            
        try:
            from database.db_manager import engine
            from database.models import SystemLog
            from sqlalchemy.orm import sessionmaker
            
            # Create a completely separate, isolated session just for logging
            # so it doesn't accidentally close the main application's active sessions.
            LogSession = sessionmaker(bind=engine)
            
            with LogSession() as session:
                log_entry = SystemLog(
                    level=record.levelname,
                    logger_name=record.name,
                    message=record.getMessage(),
                    # Fix DeprecationWarning by using timezone-aware UTC datetime
                    timestamp=datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc)
                )
                session.add(log_entry)
                session.commit()
        except Exception:
            # If the database fails to write, fail silently to prevent app crashes
            pass

def setup_logging():
    # 1. Console Output (for debugging during development)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    
    # 2. Database Output (Replaces the old text file)
    db_handler = DatabaseLogHandler()
    
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        handlers=[console_handler, db_handler],
    )


def main():
    # Setup database logging BEFORE starting the app
    setup_logging()
    
    logger = logging.getLogger("attendance.main")
    logger.info("Starting %s v%s", config.APP_NAME, config.APP_VERSION)

    init_db()


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