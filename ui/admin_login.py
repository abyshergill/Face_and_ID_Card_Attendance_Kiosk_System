"""Admin login dialog with Escalating Brute-Force protection."""
import logging
from datetime import datetime, timedelta

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout,
)

from database.db_manager import get_session, verify_password
from database.models import AdminAccount

logger = logging.getLogger("attendance.ui.login")

MAX_FAILED_ATTEMPTS = 5
BASE_LOCKOUT_MINUTES = 15
LOCKOUT_INCREMENT = 5

class AdminLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin Login")
        self.setFixedSize(340, 200)

        self.authenticated_username = None

        layout = QVBoxLayout(self)

        title = QLabel("🔐 Admin Login")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        self.user_input = QLineEdit()
        self.pass_input = QLineEdit()
        self.pass_input.setEchoMode(QLineEdit.Password)
        self.pass_input.returnPressed.connect(self._do_login)

        form.addRow("Username:", self.user_input)
        form.addRow("Password:", self.pass_input)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        login_btn = QPushButton("Login")
        login_btn.setDefault(True)
        login_btn.clicked.connect(self._do_login)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_row.addWidget(login_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _do_login(self):
        username = self.user_input.text().strip()
        password = self.pass_input.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Error", "Username and password required.")
            return

        with get_session() as session:
            account = session.query(AdminAccount).filter_by(username=username).first()
            
            if not account:
                logger.warning(f"Failed login attempt for unknown user: '{username}'")
                QMessageBox.critical(self, "Access Denied", "Invalid username or password.")
                return

            now = datetime.utcnow()

            # 1. Check if Account is currently Locked
            if account.locked_until and account.locked_until > now:
                remaining = int((account.locked_until - now).total_seconds() / 60)
                QMessageBox.critical(self, "Account Locked", f"Too many failed attempts. Try again in {remaining} minutes.")
                return

            # 2. Verify Password
            if verify_password(password, account.salt, account.password_hash):
                # SUCCESS: Reset attempts and unlock
                account.failed_attempts = 0
                account.locked_until = None
                self.authenticated_username = username
                logger.info(f"Admin '{username}' successfully logged in.")
                self.accept()
            else:
                # FAILED: Increment attempts and escalate lockout
                account.failed_attempts += 1
                
                if account.failed_attempts >= MAX_FAILED_ATTEMPTS:
                    # Calculate progressive penalty: 15, 20, 25, 30...
                    penalty_multiplier = account.failed_attempts - MAX_FAILED_ATTEMPTS
                    lock_minutes = BASE_LOCKOUT_MINUTES + (penalty_multiplier * LOCKOUT_INCREMENT)
                    
                    account.locked_until = now + timedelta(minutes=lock_minutes)
                    logger.warning(f"Admin '{username}' LOCKED OUT for {lock_minutes} minutes due to brute force.")
                    QMessageBox.critical(self, "Account Locked", f"Too many failed attempts. Account locked for {lock_minutes} minutes.")
                else:
                    remaining_tries = MAX_FAILED_ATTEMPTS - account.failed_attempts
                    logger.warning(f"Failed login attempt for '{username}'. {remaining_tries} tries left.")
                    QMessageBox.critical(self, "Access Denied", f"Invalid username or password.\nWarning: {remaining_tries} attempts remaining.")