"""Main Admin Dashboard: manage employees, permissions, and attendance logs."""
import logging
import shutil
import re
from sqlalchemy import func
import math
from PyQt5.QtCore import Qt, QDateTime
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateTimeEdit, QDialog, QFormLayout, QFrame, 
    QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit, 
    QMainWindow, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, 
    QVBoxLayout, QWidget,
)

import config
import kiosk_identity
from database.db_manager import get_session, log_kiosk_audit, register_kiosk, hash_password
from database.models import (
    AttendanceLog, Employee, FieldPermission, Kiosk, KioskAuditLog, AdminAccount
)
from ui.change_password_dialog import ChangePasswordDialog
from ui.user_registration import EmployeeRegistrationDialog
from ui.workers import RetrainWorker

logger = logging.getLogger("attendance.ui.admin")

def is_strong_password(password):
    pattern = r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$"
    return bool(re.match(pattern, password))

class CreateAdminDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Admin")
        self.resize(380, 250)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.username_input = QLineEdit()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.confirm_password_input = QLineEdit()
        self.confirm_password_input.setEchoMode(QLineEdit.Password)

        form.addRow("New Admin ID:", self.username_input)
        form.addRow("Password:", self.password_input)
        form.addRow("Confirm Password:", self.confirm_password_input)
        layout.addLayout(form)

        hint = QLabel("Password MUST contain at least:\n• 8 characters, 1 Uppercase, 1 Lowercase\n• 1 Number, 1 Special Character (!@#$...)")
        hint.setStyleSheet("color:#777; font-size:11px;")
        layout.addWidget(hint)

        btn_layout = QHBoxLayout()
        create_btn = QPushButton("Create Admin")
        create_btn.setStyleSheet("background:#27ae60; color:white; font-weight:bold; padding:8px;")
        create_btn.clicked.connect(self._create_admin)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def _create_admin(self):
        user = self.username_input.text().strip()
        pwd = self.password_input.text().strip()
        confirm = self.confirm_password_input.text().strip()

        if not user or not pwd:
            return QMessageBox.warning(self, "Error", "All fields are required.")
        if not is_strong_password(pwd):
            return QMessageBox.warning(self, "Weak Password", "Password does not meet security requirements.")
        if pwd != confirm:
            return QMessageBox.warning(self, "Error", "Passwords do not match.")

        with get_session() as session:
            if session.query(AdminAccount).filter_by(username=user).first():
                return QMessageBox.warning(self, "Error", "This Admin ID already exists.")
            pwd_hash, salt = hash_password(pwd)
            session.add(AdminAccount(username=user, password_hash=pwd_hash, salt=salt))
            
        logger.info(f"New admin '{user}' was created.")
        QMessageBox.information(self, "Success", f"New admin '{user}' created successfully.")
        self.accept()


class AdminDashboard(QMainWindow):
    def __init__(self, admin_username, parent=None):
        super().__init__(parent)
        self.admin_username = admin_username
        self.setWindowTitle(f"{config.APP_NAME} — Admin Dashboard")
        self.resize(1150, 750)
        self._retrain_worker = None

        # --- Pagination Variables ---
        self.emp_page = 1
        self.emp_per_page = 50
        self.emp_total_pages = 1
        
        self.log_page = 1
        self.log_per_page = 100
        self.log_total_pages = 1

        self._this_kiosk_active = True
        self._this_kiosk_label = None
        try:
            with get_session() as session:
                kiosk = register_kiosk(session, mode_label="ADMIN")
                self._this_kiosk_active = kiosk.is_active
                self._this_kiosk_label = kiosk.location_label
        except Exception:
            pass

        self._build_menu_bar()

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        
        if not self._this_kiosk_active:
            central_layout.addWidget(self._build_unapproved_kiosk_banner())

        tabs = QTabWidget()
        tabs.addTab(self._build_employees_tab(), "👥 Employees")
        tabs.addTab(self._build_attendance_tab(), "🕒 Attendance Logs")
        tabs.addTab(self._build_kiosks_tab(), "🖥️ Kiosks / Locations")
        tabs.addTab(self._build_admin_mgmt_tab(), "🛡️ Admins & Security")
        tabs.addTab(self._build_permissions_tab(), "🔧 Field Visibility")
        
        central_layout.addWidget(tabs)
        self.setCentralWidget(central)

        self._refresh_employee_table()
        self._refresh_kiosk_table()
        self._refresh_attendance_table()
        self._refresh_admin_table()

    def _build_menu_bar(self):
        menu_bar = self.menuBar()
        # FIX: Show the logged-in username in the Account menu
        account_menu = menu_bar.addMenu(f"Account ({self.admin_username})")
        change_pw_action = account_menu.addAction("🔑 Change My Password…")
        change_pw_action.triggered.connect(self._open_change_password)
        account_menu.addSeparator()
        logout_action = account_menu.addAction("🚪 Logout")
        logout_action.triggered.connect(self.close)

    def _open_change_password(self):
        dlg = ChangePasswordDialog(self.admin_username, self)
        dlg.exec_()

    def _build_unapproved_kiosk_banner(self):
        banner = QFrame()
        banner.setStyleSheet("background:#7a3b0b; border-bottom:2px solid #c0611b;")
        layout = QHBoxLayout(banner)
        label = QLabel("⚠️ This PC is NOT an approved kiosk. Scanning is blocked until approved below.")
        label.setStyleSheet("color:#ffe9d6; font-weight:600;")
        layout.addWidget(label, stretch=1)
        approve_btn = QPushButton("✅ Approve This PC Now")
        approve_btn.setStyleSheet("background:#27ae60; color:white; font-weight:600; padding:6px 14px; border-radius:6px;")
        approve_btn.clicked.connect(self._approve_this_kiosk)
        layout.addWidget(approve_btn)
        self._kiosk_banner = banner
        return banner

    def _approve_this_kiosk(self):
        ident = kiosk_identity.get_identity()
        with get_session() as session:
            kiosk = session.query(Kiosk).filter_by(mac_address=ident.mac_address, machine_username=ident.machine_username).first()
            if kiosk:
                kiosk.is_active = True
                log_kiosk_audit(session, kiosk, "APPROVED", performed_by=self.admin_username)
        self._this_kiosk_active = True
        if hasattr(self, "_kiosk_banner") and self._kiosk_banner is not None:
            self._kiosk_banner.setParent(None)
            self._kiosk_banner.deleteLater()
            self._kiosk_banner = None
        self._refresh_kiosk_table()

    # ==================================================================
    # Admins Tab
    # ==================================================================
    def _build_admin_mgmt_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        info = QLabel("Manage administrator accounts. You cannot delete the account you are currently logged in with.")
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ Create New Admin")
        add_btn.setStyleSheet("background:#27ae60; color:white; font-weight:bold;")
        add_btn.clicked.connect(self._add_admin)
        delete_btn = QPushButton("🗑️ Delete Selected Admin")
        delete_btn.setStyleSheet("color:#c0392b; font-weight:bold;")
        delete_btn.clicked.connect(self._delete_admin)
        
        btn_row.addWidget(add_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.admin_table = QTableWidget(0, 4)
        self.admin_table.setHorizontalHeaderLabels(["ID", "Username", "Failed Attempts", "Account Status"])
        self.admin_table.setColumnHidden(0, True)
        self.admin_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.admin_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.admin_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.admin_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.admin_table)
        return widget

    def _refresh_admin_table(self):
        with get_session() as session:
            admins = session.query(AdminAccount).all()
            now = QDateTime.currentDateTime().toPyDateTime()
            
            rows = []
            for adm in admins:
                status = "✅ Active"
                if adm.locked_until and adm.locked_until > now:
                    status = f"🚫 Locked until {adm.locked_until.strftime('%H:%M')}"
                display_name = f"{adm.username} (You)" if adm.username == self.admin_username else adm.username
                rows.append([adm.id, display_name, adm.failed_attempts, status])

        self.admin_table.setRowCount(0)
        for row_idx, data in enumerate(rows):
            self.admin_table.insertRow(row_idx)
            for col_idx, val in enumerate(data):
                self.admin_table.setItem(row_idx, col_idx, QTableWidgetItem(str(val)))

    def _add_admin(self):
        dlg = CreateAdminDialog(self)
        if dlg.exec_(): self._refresh_admin_table()

    def _delete_admin(self):
        row = self.admin_table.currentRow()
        if row < 0: return QMessageBox.warning(self, "No Selection", "Please select an admin to delete.")
        admin_id = int(self.admin_table.item(row, 0).text())
        
        with get_session() as session:
            target_admin = session.get(AdminAccount, admin_id)
            if target_admin.username == self.admin_username:
                return QMessageBox.critical(self, "Action Denied", "You cannot delete your own account.")
            confirm = QMessageBox.question(self, "Confirm Delete", f"Permanently delete admin '{target_admin.username}'?", QMessageBox.Yes | QMessageBox.No)
            if confirm == QMessageBox.Yes:
                session.delete(target_admin)
        self._refresh_admin_table()

    # ==================================================================
    # Field Permissions Tab
    # ==================================================================
    def _build_permissions_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        info = QLabel("Choose which employee details are shown on the User screen after a successful scan.")
        layout.addWidget(info)

        box = QGroupBox("Visible Fields")
        box_layout = QVBoxLayout()
        self.permission_checkboxes = {}

        with get_session() as session:
            perms = session.query(FieldPermission).all()
            for perm in perms:
                cb = QCheckBox(perm.field_label)
                cb.setChecked(perm.visible_to_user)
                cb.stateChanged.connect(self._save_permissions)
                box_layout.addWidget(cb)
                self.permission_checkboxes[perm.field_key] = cb

        box.setLayout(box_layout)
        layout.addWidget(box)
        layout.addStretch()
        return widget

    def _save_permissions(self):
        with get_session() as session:
            for field_key, checkbox in self.permission_checkboxes.items():
                perm = session.query(FieldPermission).filter_by(field_key=field_key).first()
                if perm: perm.visible_to_user = checkbox.isChecked()

    # ==================================================================
    # Employees Tab 
    # ==================================================================

    def _build_employees_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("➕ Add Employee")
        add_btn.clicked.connect(self._add_employee)
        edit_btn = QPushButton("✏️ Edit Selected")
        edit_btn.clicked.connect(self._edit_employee)
        delete_btn = QPushButton("🗑️ Delete Selected")
        delete_btn.setStyleSheet("color:#c0392b;")
        delete_btn.clicked.connect(self._delete_employee)
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.clicked.connect(lambda: self._refresh_employee_table(reset_page=True))
        
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self.employee_table = QTableWidget(0, 6)
        self.employee_table.setHorizontalHeaderLabels(["DB ID", "Employee ID", "Name", "Age", "Department", "Contact"])
        self.employee_table.setColumnHidden(0, True)
        self.employee_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.employee_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.employee_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.employee_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.employee_table)

        # --- NEW: Employee Pagination Controls ---
        page_layout = QHBoxLayout()
        self.emp_prev_btn = QPushButton("◀ Previous")
        self.emp_prev_btn.clicked.connect(self._emp_page_prev)
        self.emp_page_label = QLabel("Page 1 of 1")
        self.emp_page_label.setAlignment(Qt.AlignCenter)
        self.emp_next_btn = QPushButton("Next ▶")
        self.emp_next_btn.clicked.connect(self._emp_page_next)
        
        page_layout.addStretch()
        page_layout.addWidget(self.emp_prev_btn)
        page_layout.addWidget(self.emp_page_label)
        page_layout.addWidget(self.emp_next_btn)
        page_layout.addStretch()
        layout.addLayout(page_layout)

        self.training_status_label = QLabel("Model status: unknown")
        layout.addWidget(self.training_status_label)

        return widget

    def _emp_page_prev(self):
        if self.emp_page > 1:
            self.emp_page -= 1
            self._refresh_employee_table()

    def _emp_page_next(self):
        if self.emp_page < self.emp_total_pages:
            self.emp_page += 1
            self._refresh_employee_table()

    def _refresh_employee_table(self, reset_page=False):
        if reset_page:
            self.emp_page = 1

        with get_session() as session:
            # 1. Get total count for pagination math
            total_emps = session.query(func.count(Employee.id)).filter_by(is_active=True).scalar()
            self.emp_total_pages = max(1, math.ceil(total_emps / self.emp_per_page))
            
            # 2. Fetch only the current page
            offset = (self.emp_page - 1) * self.emp_per_page
            employees = session.query(Employee).filter_by(is_active=True).order_by(Employee.name).limit(self.emp_per_page).offset(offset).all()
            
            rows = [(e.id, e.employee_id, e.name, e.age, e.department, e.contact) for e in employees]

        # Update UI Table
        self.employee_table.setRowCount(0)
        for row_idx, row_data in enumerate(rows):
            self.employee_table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data):
                self.employee_table.setItem(row_idx, col_idx, QTableWidgetItem("" if value is None else str(value)))

        # Update UI Controls
        self.emp_page_label.setText(f"Page {self.emp_page} of {self.emp_total_pages}")
        self.emp_prev_btn.setEnabled(self.emp_page > 1)
        self.emp_next_btn.setEnabled(self.emp_page < self.emp_total_pages)

        from face_engine.recognizer import face_recognizer
        status = "Trained ✅" if face_recognizer.is_trained else "Not trained yet ⚠️"
        self.training_status_label.setText(f"Model status: {status}  |  Total Enrolled: {total_emps}")

    def _selected_employee_pk(self):
        row = self.employee_table.currentRow()
        return None if row < 0 else int(self.employee_table.item(row, 0).text())

    def _add_employee(self):
        dlg = EmployeeRegistrationDialog(self)
        if dlg.exec_():
            self._refresh_employee_table()
            self._retrain_async()

    def _edit_employee(self):
        pk = self._selected_employee_pk()
        if pk is None: return
        dlg = EmployeeRegistrationDialog(self, employee_pk=pk)
        if dlg.exec_():
            self._refresh_employee_table()
            self._retrain_async()

    def _delete_employee(self):
        pk = self._selected_employee_pk()
        if pk is None: return
        with get_session() as session:
            emp = session.get(Employee, pk)
            name = emp.name
        confirm = QMessageBox.question(self, "Confirm Delete", f"Remove employee '{name}'?", QMessageBox.Yes | QMessageBox.No)
        if confirm == QMessageBox.Yes:
            with get_session() as session:
                session.delete(session.get(Employee, pk))
            self._refresh_employee_table()
            self._retrain_async()

    def _retrain_async(self):
        self.training_status_label.setText("Model status: retraining… please wait")
        self._retrain_worker = RetrainWorker()
        self._retrain_worker.finished_ok.connect(self._on_retrain_done)
        self._retrain_worker.start()

    def _on_retrain_done(self, ok):
        self._refresh_employee_table()

    # ==================================================================
    # Kiosks Tab (NEW PER-KIOSK HW TOGGLE)
    # ==================================================================
    def _build_kiosks_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        info = QLabel("Every machine that connects to this database is listed here. You can rename locations, block access, and toggle hardware turnstile/door signals per-kiosk.")
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        rename_btn = QPushButton("✏️ Rename Location")
        rename_btn.clicked.connect(self._rename_kiosk)
        toggle_btn = QPushButton("🚫 Block / ✅ Unblock Scanner")
        toggle_btn.clicked.connect(self._toggle_kiosk_access)
        
        # NEW: HW Toggle Button
        hw_btn = QPushButton("🔌 Toggle HW Signal (Door/Relay)")
        hw_btn.setStyleSheet("background:#2980b9; color:white; font-weight:bold;")
        hw_btn.clicked.connect(self._toggle_kiosk_hw)
        
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.clicked.connect(self._refresh_kiosk_table)
        
        btn_row.addWidget(rename_btn)
        btn_row.addWidget(toggle_btn)
        btn_row.addWidget(hw_btn)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self.kiosk_table = QTableWidget(0, 9)
        self.kiosk_table.setHorizontalHeaderLabels(["DB ID", "Location", "MAC", "User", "Host", "Mode", "Last Seen", "App Access", "HW Door Signal"])
        self.kiosk_table.setColumnHidden(0, True)
        self.kiosk_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.kiosk_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.kiosk_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.kiosk_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.kiosk_table)
        return widget

    def _refresh_kiosk_table(self):
        with get_session() as session:
            kiosks = session.query(Kiosk).order_by(Kiosk.location_label).all()
            rows = []
            for k in kiosks:
                rows.append([
                    k.id, k.location_label, k.mac_address, k.machine_username, k.hostname, k.last_mode_used, 
                    k.last_seen.strftime("%Y-%m-%d %H:%M") if k.last_seen else "", 
                    "✅ Active" if k.is_active else "🚫 Blocked",
                    "🔌 Enabled" if k.hw_signal_enabled else "❌ Disabled"
                ])

        self.kiosk_table.setRowCount(0)
        for row_idx, data in enumerate(rows):
            self.kiosk_table.insertRow(row_idx)
            for col_idx, val in enumerate(data):
                self.kiosk_table.setItem(row_idx, col_idx, QTableWidgetItem(str(val)))

    def _selected_kiosk_pk(self):
        row = self.kiosk_table.currentRow()
        return None if row < 0 else int(self.kiosk_table.item(row, 0).text())

    def _rename_kiosk(self):
        pk = self._selected_kiosk_pk()
        if pk is None: return QMessageBox.information(self, "No Selection", "Select a kiosk first.")
        with get_session() as session:
            kiosk = session.get(Kiosk, pk)
            current = kiosk.location_label or ""
        new_label, ok = QInputDialog.getText(self, "Rename Location", "Friendly name:", QLineEdit.Normal, current)
        if ok and new_label.strip():
            with get_session() as session:
                kiosk = session.get(Kiosk, pk)
                kiosk.location_label = new_label.strip()
            self._refresh_kiosk_table()

    def _toggle_kiosk_access(self):
        pk = self._selected_kiosk_pk()
        if pk is None: return QMessageBox.information(self, "No Selection", "Select a kiosk first.")
        with get_session() as session:
            kiosk = session.get(Kiosk, pk)
            kiosk.is_active = not kiosk.is_active
        self._refresh_kiosk_table()

    def _toggle_kiosk_hw(self):
        pk = self._selected_kiosk_pk()
        if pk is None: return QMessageBox.information(self, "No Selection", "Select a kiosk first.")
        with get_session() as session:
            kiosk = session.get(Kiosk, pk)
            kiosk.hw_signal_enabled = not kiosk.hw_signal_enabled
            logger.info(f"Admin toggled HW signal for kiosk '{kiosk.location_label}' to {kiosk.hw_signal_enabled}")
        self._refresh_kiosk_table()


    def _build_attendance_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        btn_row = QHBoxLayout()
        refresh = QPushButton("↻ Refresh Logs")
        refresh.clicked.connect(lambda: self._refresh_attendance_table(reset_page=True))
        btn_row.addWidget(refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        
        self.attendance_table = QTableWidget(0, 6)
        self.attendance_table.setHorizontalHeaderLabels(["Timestamp", "Emp ID", "Name", "Status", "Location", "Signal"])
        self.attendance_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.attendance_table)

        # --- NEW: Log Pagination Controls ---
        page_layout = QHBoxLayout()
        self.log_prev_btn = QPushButton("◀ Previous")
        self.log_prev_btn.clicked.connect(self._log_page_prev)
        self.log_page_label = QLabel("Page 1 of 1")
        self.log_page_label.setAlignment(Qt.AlignCenter)
        self.log_next_btn = QPushButton("Next ▶")
        self.log_next_btn.clicked.connect(self._log_page_next)
        
        page_layout.addStretch()
        page_layout.addWidget(self.log_prev_btn)
        page_layout.addWidget(self.log_page_label)
        page_layout.addWidget(self.log_next_btn)
        page_layout.addStretch()
        layout.addLayout(page_layout)

        return widget

    def _log_page_prev(self):
        if self.log_page > 1:
            self.log_page -= 1
            self._refresh_attendance_table()

    def _log_page_next(self):
        if self.log_page < self.log_total_pages:
            self.log_page += 1
            self._refresh_attendance_table()

    def _refresh_attendance_table(self, reset_page=False):
        if reset_page:
            self.log_page = 1

        with get_session() as session:
            # 1. Get total count for pagination
            total_logs = session.query(func.count(AttendanceLog.id)).scalar()
            self.log_total_pages = max(1, math.ceil(total_logs / self.log_per_page))
            
            # 2. Fetch only current page
            offset = (self.log_page - 1) * self.log_per_page
            logs = session.query(AttendanceLog).order_by(AttendanceLog.timestamp.desc()).limit(self.log_per_page).offset(offset).all()
            
            rows = []
            for log in logs:
                rows.append([
                    log.timestamp.strftime("%Y-%m-%d %H:%M") if log.timestamp else "", 
                    log.employee_id_snapshot or "", 
                    log.name_snapshot or "", 
                    log.status, 
                    log.kiosk_location_snapshot or "—", 
                    "Yes" if log.signal_sent else "No"
                ])

        self.attendance_table.setRowCount(0)
        for row_idx, data in enumerate(rows):
            self.attendance_table.insertRow(row_idx)
            for col_idx, val in enumerate(data):
                self.attendance_table.setItem(row_idx, col_idx, QTableWidgetItem(str(val)))

        # Update UI Controls
        self.log_page_label.setText(f"Page {self.log_page} of {self.log_total_pages} (Total: {total_logs})")
        self.log_prev_btn.setEnabled(self.log_page > 1)
        self.log_next_btn.setEnabled(self.log_page < self.log_total_pages)