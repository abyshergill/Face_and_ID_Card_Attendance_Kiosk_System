"""Landing window: choose Admin Mode, Face Scan, or Card Scan."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

import config
import kiosk_identity
from ui.admin_dashboard import AdminDashboard
from ui.admin_login import AdminLoginDialog
from ui.user_scan import UserScanWindow
from ui.employee_scan import EmployeeCardScanWindow  

import os
from dotenv import load_dotenv
from PyQt5.QtGui import QIcon

# 1. Get the absolute folder where b.py is located
current_dir = os.path.dirname(os.path.abspath(__file__))

# 2. Explicitly load the .env file from this same folder
env_path = os.path.join(current_dir, ".env")
load_dotenv(dotenv_path=env_path)


class ModeSelectWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(config.APP_NAME)
        self.resize(480, 500)  
        self._child_window = None

        # 3. Get the path from .env
        icon_rel_path = config.WINDOW_ICON_PATH 

        if icon_rel_path:
            # Clean up the leading './' if present to avoid path joining issues
            icon_rel_path = icon_rel_path.lstrip("./\\")
            
            # Combine script folder with the relative asset path
            # (Use "..", icon_rel_path if your 'assets' folder is one level up in the root)
            icon_path = os.path.join(current_dir, icon_rel_path)
            
            if os.path.exists(icon_path):
                self.setWindowIcon(QIcon(icon_path))
                print(f"Successfully loaded icon from: {icon_path}")
            else:
                print(f"Error: Icon file does not exist at resolved path -> {icon_path}")
        else:
            print("Warning: WINDOW_ICON_PATH not found in .env file.")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setSpacing(15)
        layout.setContentsMargins(40, 40, 40, 40)

        title = QLabel(f"🧬  {config.APP_NAME}")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel(f"v{config.APP_VERSION}  •  Select a mode to continue")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color:#777; margin-bottom: 20px;")
        layout.addWidget(subtitle)

        # --- ADMIN BUTTON ---
        admin_btn = QPushButton("Admin Mode")
        admin_btn.setMinimumHeight(60)
        admin_btn.setStyleSheet("font-size:16px; font-weight:600; border-radius:10px; background:#34495e; color:white;")
        admin_btn.clicked.connect(self._open_admin_mode)
        layout.addWidget(admin_btn)

        # --- FACE SCAN BUTTON ---
        user_btn = QPushButton("Face Scan Kiosk")
        user_btn.setMinimumHeight(60)
        user_btn.setStyleSheet("font-size:16px; font-weight:600; border-radius:10px; background:#2d6cdf; color:white;")
        user_btn.clicked.connect(self._open_user_mode)
        layout.addWidget(user_btn)

        # --- CARD SCAN BUTTON ---
        card_btn = QPushButton("ID Card Scan Kiosk")
        card_btn.setMinimumHeight(60)
        card_btn.setStyleSheet("font-size:16px; font-weight:600; border-radius:10px; background:#8e44ad; color:white;")
        card_btn.clicked.connect(self._open_card_mode)
        layout.addWidget(card_btn)

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
        
    def _open_card_mode(self):
        self._child_window = EmployeeCardScanWindow()
        self._child_window.show()