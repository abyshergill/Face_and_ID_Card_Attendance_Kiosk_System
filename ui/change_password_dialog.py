"""Admin self-service password change dialog."""
import logging
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout,
)

from database.db_manager import get_session, hash_password, verify_password
from database.models import AdminAccount

logger = logging.getLogger("attendance.ui.change_password")

def is_strong_password(password):
    """Requires 8+ chars, 1 uppercase, 1 lowercase, 1 number, 1 special character."""
    pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$"
    return bool(re.match(pattern, password))

class ChangePasswordDialog(QDialog):
    def __init__(self, admin_username, parent=None):
        super().__init__(parent)
        self.admin_username = admin_username
        self.setWindowTitle("Change Password")
        self.setFixedSize(400, 300)

        layout = QVBoxLayout(self)

        title = QLabel(f"🔑 Change Password — {admin_username}")
        title.setStyleSheet("font-size:16px; font-weight:600;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        self.current_pw = QLineEdit()
        self.current_pw.setEchoMode(QLineEdit.Password)
        self.new_pw = QLineEdit()
        self.new_pw.setEchoMode(QLineEdit.Password)
        self.confirm_pw = QLineEdit()
        self.confirm_pw.setEchoMode(QLineEdit.Password)
        self.confirm_pw.returnPressed.connect(self._submit)

        form.addRow("Current Password:", self.current_pw)
        form.addRow("New Password:", self.new_pw)
        form.addRow("Confirm Password:", self.confirm_pw)
        layout.addLayout(form)

        hint = QLabel("Password MUST contain at least:\n• 8 characters\n• 1 Uppercase letter\n• 1 Lowercase letter\n• 1 Number\n• 1 Special Character (!@#$%^&*)")
        hint.setStyleSheet("color:#777; font-size:11px;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._submit)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _submit(self):
        current = self.current_pw.text()
        new = self.new_pw.text()
        confirm = self.confirm_pw.text()

        if not current or not new or not confirm:
            QMessageBox.warning(self, "Missing Fields", "Please fill in all three fields.")
            return

        if not is_strong_password(new):
            QMessageBox.warning(self, "Weak Password", "Password does not meet the security requirements.")
            return

        if new != confirm:
            QMessageBox.warning(self, "Mismatch", "New password and confirmation do not match.")
            return

        with get_session() as session:
            account = session.query(AdminAccount).filter_by(username=self.admin_username).first()
            
            if not verify_password(current, account.salt, account.password_hash):
                QMessageBox.critical(self, "Incorrect Password", "Your current password is incorrect.")
                self.current_pw.clear()
                return

            pwd_hash, salt = hash_password(new)
            account.password_hash = pwd_hash
            account.salt = salt

        logger.info("Admin '%s' changed their password.", self.admin_username)
        QMessageBox.information(self, "Password Changed", "Your password has been updated successfully.")
        self.accept()