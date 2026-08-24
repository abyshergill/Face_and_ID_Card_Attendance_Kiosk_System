"""Landing window: choose Admin Mode or User (Scan) Mode."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

import config
import kiosk_identity
from ui.admin_dashboard import AdminDashboard
from ui.admin_login import AdminLoginDialog
from ui.user_scan import UserScanWindow


class ModeSelectWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.resize(480, 420)
        self._child_window = None

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 60, 40, 60)

        title = QLabel(f"🧬  {config.APP_NAME}")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(f"v{config.APP_VERSION}  •  Select a mode to continue")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#777;")
        layout.addWidget(subtitle)

        admin_btn = QPushButton("🔐  Admin Mode")
        admin_btn.setMinimumHeight(60)
        admin_btn.setStyleSheet("font-size:16px; font-weight:600; border-radius:10px; background:#34495e; color:white;")
        admin_btn.clicked.connect(self._open_admin_mode)
        layout.addWidget(admin_btn)

        user_btn = QPushButton("👁️  User Mode (Scan Face)")
        user_btn.setMinimumHeight(60)
        user_btn.setStyleSheet("font-size:16px; font-weight:600; border-radius:10px; background:#2d6cdf; color:white;")
        user_btn.clicked.connect(self._open_user_mode)
        layout.addWidget(user_btn)

        layout.addStretch()

        ident = kiosk_identity.get_identity()
        footer = QLabel(
            f"This PC: {ident.hostname}  •  MAC: {ident.mac_address}  •  User: {ident.machine_username}\n"
            "(Share this with your admin if this station needs location approval.)"
        )
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color:#aaa; font-size:10px;")
        layout.addWidget(footer)

        self.setCentralWidget(central)

    def _open_admin_mode(self):
        login = AdminLoginDialog(self)
        if login.exec_():
            self._child_window = AdminDashboard(login.authenticated_username)
            self._child_window.show()

    def _open_user_mode(self):
        self._child_window = UserScanWindow()
        self._child_window.show()
