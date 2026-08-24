"""Admin authentication dialog."""
import logging

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
)

from database.db_manager import get_session, verify_password
from database.models import AdminAccount

logger = logging.getLogger("attendance.ui.login")


class AdminLoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Admin Login")
        self.setFixedSize(360, 220)
        self.authenticated_username = None

        layout = QVBoxLayout(self)

        title = QLabel("🔒 Administrator Login")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        form = QFormLayout()
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.returnPressed.connect(self.try_login)
        form.addRow("Username:", self.username_input)
        form.addRow("Password:", self.password_input)
        layout.addLayout(form)

        btn_row = QVBoxLayout()
        login_btn = QPushButton("Login")
        login_btn.setDefault(True)
        login_btn.clicked.connect(self.try_login)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(login_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def try_login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            QMessageBox.warning(self, "Missing Fields", "Please enter both username and password.")
            return

        with get_session() as session:
            account = session.query(AdminAccount).filter_by(username=username).first()
            if account and verify_password(password, account.salt, account.password_hash):
                self.authenticated_username = username
                self.accept()
                return

        logger.warning("Failed admin login attempt for username '%s'.", username)
        QMessageBox.critical(self, "Login Failed", "Invalid username or password.")
        self.password_input.clear()
