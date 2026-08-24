"""Main Admin Dashboard: manage employees, field-visibility permissions, and attendance logs."""
import logging
import shutil
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGroupBox, QHBoxLayout,
    QHeaderView, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

import config
import kiosk_identity
from database.db_manager import get_session, log_kiosk_audit, register_kiosk
from database.models import (
    AttendanceLog, Employee, FieldPermission, Kiosk, KioskAuditLog,
)
from ui.change_password_dialog import ChangePasswordDialog
from ui.user_registration import EmployeeRegistrationDialog
from ui.workers import RetrainWorker

logger = logging.getLogger("attendance.ui.admin")


class AdminDashboard(QMainWindow):
    def __init__(self, admin_username, parent=None):
        super().__init__(parent)
        self.admin_username = admin_username
        self.setWindowTitle(f"{config.APP_NAME} — Admin Dashboard ({admin_username})")
        self.resize(1080, 680)
        self._retrain_worker = None

        # Register/check-in this admin PC in the kiosks table too, so it
        # shows up alongside scan kiosks for full multi-location visibility.
        # NOTE: Admin Mode login is intentionally allowed on ANY machine even
        # if the kiosk is unapproved/blocked (an admin must always be able to
        # get in to fix things) — we just surface a warning banner instead.
        self._this_kiosk_active = True
        self._this_kiosk_label = None
        try:
            with get_session() as session:
                kiosk = register_kiosk(session, mode_label="ADMIN")
                self._this_kiosk_active = kiosk.is_active
                self._this_kiosk_label = kiosk.location_label
        except Exception:
            logger.exception("Failed to register this admin PC as a kiosk (non-fatal).")

        self._build_menu_bar()

        central = QWidget()
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        if not self._this_kiosk_active:
            central_layout.addWidget(self._build_unapproved_kiosk_banner())

        tabs = QTabWidget()
        tabs.addTab(self._build_employees_tab(), "👥 Employees")
        tabs.addTab(self._build_permissions_tab(), "🔧 Field Visibility Settings")
        tabs.addTab(self._build_kiosks_tab(), "🖥️ Kiosks / Locations")
        tabs.addTab(self._build_kiosk_audit_tab(), "🕵️ Kiosk Audit Log")
        tabs.addTab(self._build_attendance_tab(), "🕒 Attendance Logs")
        central_layout.addWidget(tabs)

        self.setCentralWidget(central)

        ident = kiosk_identity.get_identity()
        self.statusBar().showMessage(
            f"Logged in as '{admin_username}'  •  This PC: {ident.hostname}  ({ident.mac_address})"
        )

        self._refresh_employee_table()
        self._refresh_kiosk_table()          # this also refreshes the audit tab (see method body)
        self._refresh_attendance_table()

    # ==================================================================
    # Menu Bar
    # ==================================================================
    def _build_menu_bar(self):
        menu_bar = self.menuBar()
        account_menu = menu_bar.addMenu("Account")

        change_pw_action = account_menu.addAction("🔑 Change Password…")
        change_pw_action.triggered.connect(self._open_change_password)

        account_menu.addSeparator()
        logout_action = account_menu.addAction("🚪 Logout")
        logout_action.triggered.connect(self.close)

    def _open_change_password(self):
        dlg = ChangePasswordDialog(self.admin_username, self)
        dlg.exec_()

    # ==================================================================
    # Unapproved-kiosk warning banner
    # ==================================================================
    def _build_unapproved_kiosk_banner(self):
        """
        Shown when THIS admin PC itself is not yet an approved kiosk
        (e.g. ATTENDANCE_KIOSK_REQUIRE_APPROVAL=true and nobody has approved
        it yet). Admin login is still allowed on any machine — this is just
        a visible heads-up so the admin knows to approve their own station
        from the Kiosks tab below (or knows why a fresh install looks new).
        """
        banner = QFrame()
        banner.setStyleSheet(
            "background:#7a3b0b; border-bottom:2px solid #c0611b;"
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(14, 8, 14, 8)

        label = QLabel(
            "⚠️  This PC ('" + (self._this_kiosk_label or "this station") + "') is NOT an approved kiosk yet. "
            "Admin access still works, but User Mode scanning on this machine (and any station "
            "like it) will be blocked until approved below."
        )
        label.setStyleSheet("color:#ffe9d6; font-weight:600;")
        label.setWordWrap(True)
        layout.addWidget(label, stretch=1)

        approve_btn = QPushButton("✅ Approve This PC Now")
        approve_btn.setStyleSheet(
            "background:#27ae60; color:white; font-weight:600; padding:6px 14px; border-radius:6px;"
        )
        approve_btn.clicked.connect(self._approve_this_kiosk)
        layout.addWidget(approve_btn)

        self._kiosk_banner = banner
        return banner

    def _approve_this_kiosk(self):
        ident = kiosk_identity.get_identity()
        with get_session() as session:
            kiosk = (
                session.query(Kiosk)
                .filter_by(mac_address=ident.mac_address, machine_username=ident.machine_username)
                .first()
            )
            if kiosk:
                kiosk.is_active = True
                log_kiosk_audit(
                    session, kiosk, "APPROVED", performed_by=self.admin_username,
                    details="Self-approved from the Admin Dashboard warning banner.",
                )
        self._this_kiosk_active = True
        logger.info("Admin '%s' approved their own station ('%s').", self.admin_username, ident.hostname)
        if hasattr(self, "_kiosk_banner") and self._kiosk_banner is not None:
            self._kiosk_banner.setParent(None)
            self._kiosk_banner.deleteLater()
            self._kiosk_banner = None
        self._refresh_kiosk_table()
        QMessageBox.information(self, "Approved", "This PC is now an approved kiosk/location.")

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
        refresh_btn.clicked.connect(self._refresh_employee_table)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(delete_btn)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self.employee_table = QTableWidget(0, 6)
        self.employee_table.setHorizontalHeaderLabels(
            ["DB ID", "Employee ID", "Name", "Age", "Department", "Contact"]
        )
        self.employee_table.setColumnHidden(0, True)
        self.employee_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.employee_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.employee_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.employee_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.employee_table)

        self.training_status_label = QLabel("Model status: unknown")
        layout.addWidget(self.training_status_label)

        return widget

    def _refresh_employee_table(self):
        with get_session() as session:
            employees = session.query(Employee).filter_by(is_active=True).order_by(Employee.name).all()
            rows = [(e.id, e.employee_id, e.name, e.age, e.department, e.contact) for e in employees]

        self.employee_table.setRowCount(0)
        for row_idx, row_data in enumerate(rows):
            self.employee_table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data):
                self.employee_table.setItem(row_idx, col_idx, QTableWidgetItem("" if value is None else str(value)))

        from face_engine.recognizer import face_recognizer
        status = "Trained ✅" if face_recognizer.is_trained else "Not trained yet ⚠️ (add employees to enable scanning)"
        self.training_status_label.setText(f"Model status: {status}  |  Enrolled employees: {len(rows)}")

    def _selected_employee_pk(self):
        row = self.employee_table.currentRow()
        if row < 0:
            return None
        return int(self.employee_table.item(row, 0).text())

    def _add_employee(self):
        dlg = EmployeeRegistrationDialog(self)
        if dlg.exec_():
            self._refresh_employee_table()
            self._retrain_async()

    def _edit_employee(self):
        pk = self._selected_employee_pk()
        if pk is None:
            QMessageBox.information(self, "No Selection", "Select an employee to edit first.")
            return
        dlg = EmployeeRegistrationDialog(self, employee_pk=pk)
        if dlg.exec_():
            self._refresh_employee_table()
            self._retrain_async()

    def _delete_employee(self):
        pk = self._selected_employee_pk()
        if pk is None:
            QMessageBox.information(self, "No Selection", "Select an employee to delete first.")
            return

        with get_session() as session:
            emp = session.get(Employee, pk)
            if not emp:
                return
            name, photo_dir = emp.name, emp.photo_dir

        confirm = QMessageBox.question(
            self, "Confirm Delete",
            f"Remove employee '{name}'? This also deletes their enrollment photos and attendance history.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        with get_session() as session:
            emp = session.get(Employee, pk)
            session.delete(emp)

        shutil.rmtree(photo_dir, ignore_errors=True)
        logger.info("Employee '%s' deleted by admin '%s'.", name, self.admin_username)
        self._refresh_employee_table()
        self._retrain_async()

    def _retrain_async(self):
        self.training_status_label.setText("Model status: retraining… please wait")
        self._retrain_worker = RetrainWorker()
        self._retrain_worker.finished_ok.connect(self._on_retrain_done)
        self._retrain_worker.start()

    def _on_retrain_done(self, ok):
        self._refresh_employee_table()
        if not ok:
            QMessageBox.warning(self, "Training Warning", "Model could not be trained (no valid enrollment photos found).")

    # ==================================================================
    # Field Visibility Settings Tab
    # ==================================================================
    def _build_permissions_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel(
            "Choose which employee details are shown on the User (scan) screen\n"
            "after a face is successfully recognized."
        )
        layout.addWidget(info)

        box = QGroupBox("Visible Fields")
        box_layout = QVBoxLayout()
        self.permission_checkboxes = {}

        with get_session() as session:
            perms = session.query(FieldPermission).all()
            for perm in perms:
                cb = QCheckBox(perm.field_label)
                cb.setChecked(perm.visible_to_user)
                box_layout.addWidget(cb)
                self.permission_checkboxes[perm.field_key] = cb

        box.setLayout(box_layout)
        layout.addWidget(box)

        save_btn = QPushButton("💾 Save Visibility Settings")
        save_btn.clicked.connect(self._save_permissions)
        layout.addWidget(save_btn)
        layout.addStretch()
        return widget

    def _save_permissions(self):
        with get_session() as session:
            for field_key, checkbox in self.permission_checkboxes.items():
                perm = session.query(FieldPermission).filter_by(field_key=field_key).first()
                if perm:
                    perm.visible_to_user = checkbox.isChecked()
        QMessageBox.information(self, "Saved", "Field visibility settings updated.")

    # ==================================================================
    # Kiosks / Locations Tab
    # ==================================================================
    def _build_kiosks_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel(
            "Every PC that has opened this application (scan kiosks and admin dashboards) is\n"
            "listed below, identified by its MAC address + Windows/OS username. Rename a station\n"
            "to a friendly location name, and block/unblock its ability to log attendance centrally."
        )
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        rename_btn = QPushButton("✏️ Rename Location")
        rename_btn.clicked.connect(self._rename_kiosk)
        toggle_btn = QPushButton("🚫 Block / ✅ Unblock Selected")
        toggle_btn.clicked.connect(self._toggle_kiosk_access)
        approve_all_btn = QPushButton("✅ Approve All Pending")
        approve_all_btn.setStyleSheet("background:#27ae60; color:white; font-weight:600;")
        approve_all_btn.setToolTip(
            "Unblocks every currently-blocked kiosk in one click — useful when rolling out\n"
            "many new scan stations at once and approving them all after verifying the list."
        )
        approve_all_btn.clicked.connect(self._approve_all_pending_kiosks)
        remove_btn = QPushButton("🗑️ Remove Kiosk")
        remove_btn.setStyleSheet("color:#c0392b;")
        remove_btn.clicked.connect(self._remove_kiosk)
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.clicked.connect(self._refresh_kiosk_table)
        btn_row.addWidget(rename_btn)
        btn_row.addWidget(toggle_btn)
        btn_row.addWidget(approve_all_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self.pending_count_label = QLabel("")
        self.pending_count_label.setStyleSheet("color:#e08a2c; font-weight:600;")
        layout.addWidget(self.pending_count_label)

        self.kiosk_table = QTableWidget(0, 8)
        self.kiosk_table.setHorizontalHeaderLabels(
            ["DB ID", "Location", "MAC Address", "Machine User", "Hostname", "Last Mode", "Last Seen", "Status"]
        )
        self.kiosk_table.setColumnHidden(0, True)
        self.kiosk_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.kiosk_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.kiosk_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.kiosk_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.kiosk_table)

        approval_note = QLabel(
            "Tip: set ATTENDANCE_KIOSK_REQUIRE_APPROVAL=true in production so any brand-new\n"
            "machine is registered BLOCKED by default until you approve it here."
        )
        approval_note.setStyleSheet("color:#777; font-size:11px;")
        layout.addWidget(approval_note)

        return widget

    def _refresh_kiosk_table(self):
        with get_session() as session:
            kiosks = session.query(Kiosk).order_by(Kiosk.location_label).all()
            rows = [
                (
                    k.id, k.location_label or "(unnamed)", k.mac_address, k.machine_username,
                    k.hostname or "", k.last_mode_used or "", 
                    k.last_seen.strftime("%Y-%m-%d %H:%M:%S") if k.last_seen else "",
                    "✅ Active" if k.is_active else "🚫 Blocked",
                )
                for k in kiosks
            ]

        pending = sum(1 for row_data in rows if row_data[7].startswith("🚫"))
        if hasattr(self, "pending_count_label"):
            self.pending_count_label.setText(
                f"⏳ {pending} station(s) pending approval." if pending else "✅ All known stations are approved."
            )

        self.kiosk_table.setRowCount(0)
        for row_idx, row_data in enumerate(rows):
            self.kiosk_table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data):
                item = QTableWidgetItem(str(value))
                if col_idx == 7 and value.startswith("🚫"):
                    item.setForeground(Qt.red)
                self.kiosk_table.setItem(row_idx, col_idx, item)

        # Keep the Attendance tab's kiosk filter dropdown in sync
        if hasattr(self, "attendance_kiosk_filter"):
            current = self.attendance_kiosk_filter.currentText()
            self.attendance_kiosk_filter.blockSignals(True)
            self.attendance_kiosk_filter.clear()
            self.attendance_kiosk_filter.addItem("All Locations")
            for row_data in rows:
                self.attendance_kiosk_filter.addItem(row_data[1])
            idx = self.attendance_kiosk_filter.findText(current)
            self.attendance_kiosk_filter.setCurrentIndex(idx if idx >= 0 else 0)
            self.attendance_kiosk_filter.blockSignals(False)

        # Keep the Kiosk Audit Log tab in sync too, if it has been built.
        if hasattr(self, "kiosk_audit_table"):
            self._refresh_kiosk_audit_table()

    def _approve_all_pending_kiosks(self):
        with get_session() as session:
            pending_kiosks = session.query(Kiosk).filter_by(is_active=False).all()
            count = len(pending_kiosks)
            labels = [k.location_label or k.hostname or k.mac_address for k in pending_kiosks]

        if count == 0:
            QMessageBox.information(self, "Nothing to Approve", "There are no pending/blocked stations right now.")
            return

        confirm = QMessageBox.question(
            self, "Confirm Bulk Approve",
            f"Approve ALL {count} pending station(s)? This immediately allows them to log "
            "attendance from the central database.\n\nStations to be approved:\n\n"
            + "\n".join(f"• {lbl}" for lbl in labels),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        with get_session() as session:
            pending_kiosks = session.query(Kiosk).filter_by(is_active=False).all()
            count = len(pending_kiosks)
            labels = [k.location_label or k.hostname or k.mac_address for k in pending_kiosks]
            for k in pending_kiosks:
                k.is_active = True
                log_kiosk_audit(
                    session, k, "BULK_APPROVED", performed_by=self.admin_username,
                    details=f"Approved together with {count - 1} other station(s) in one bulk action."
                    if count > 1 else "Bulk-approve action (only pending station at the time).",
                )

        if count == 0:
            QMessageBox.information(self, "Nothing to Approve", "There are no pending/blocked stations right now.")
            return

        logger.info(
            "Admin '%s' bulk-approved %d pending kiosk(s): %s",
            self.admin_username, count, ", ".join(labels),
        )
        # This admin PC itself may have just been approved via bulk-approve.
        ident = kiosk_identity.get_identity()
        if not self._this_kiosk_active:
            with get_session() as session:
                kiosk = (
                    session.query(Kiosk)
                    .filter_by(mac_address=ident.mac_address, machine_username=ident.machine_username)
                    .first()
                )
                if kiosk and kiosk.is_active:
                    self._this_kiosk_active = True
                    if hasattr(self, "_kiosk_banner") and self._kiosk_banner is not None:
                        self._kiosk_banner.setParent(None)
                        self._kiosk_banner.deleteLater()
                        self._kiosk_banner = None

        self._refresh_kiosk_table()
        QMessageBox.information(
            self, "Approved",
            f"Approved {count} station(s):\n\n" + "\n".join(f"• {lbl}" for lbl in labels),
        )

    def _selected_kiosk_pk(self):
        row = self.kiosk_table.currentRow()
        if row < 0:
            return None
        return int(self.kiosk_table.item(row, 0).text())

    def _rename_kiosk(self):
        pk = self._selected_kiosk_pk()
        if pk is None:
            QMessageBox.information(self, "No Selection", "Select a kiosk/location to rename first.")
            return
        with get_session() as session:
            kiosk = session.get(Kiosk, pk)
            if not kiosk:
                return
            current_label = kiosk.location_label or ""
        new_label, ok = QInputDialog.getText(
            self, "Rename Location", "Friendly location name (e.g. 'Main Gate', 'Building B Entrance'):",
            QLineEdit.Normal, current_label,
        )
        if not ok or not new_label.strip():
            return
        with get_session() as session:
            kiosk = session.get(Kiosk, pk)
            old_label = kiosk.location_label or "(unnamed)"
            kiosk.location_label = new_label.strip()
            log_kiosk_audit(
                session, kiosk, "RENAMED", performed_by=self.admin_username,
                details=f"'{old_label}' -> '{new_label.strip()}'",
            )
        self._refresh_kiosk_table()
        self._refresh_attendance_table()

    def _toggle_kiosk_access(self):
        pk = self._selected_kiosk_pk()
        if pk is None:
            QMessageBox.information(self, "No Selection", "Select a kiosk/location to block or unblock first.")
            return
        with get_session() as session:
            kiosk = session.get(Kiosk, pk)
            if not kiosk:
                return
            kiosk.is_active = not kiosk.is_active
            new_state = "unblocked ✅" if kiosk.is_active else "blocked 🚫"
            label = kiosk.location_label
            log_kiosk_audit(
                session, kiosk, "UNBLOCKED" if kiosk.is_active else "BLOCKED",
                performed_by=self.admin_username,
            )
        logger.info("Admin '%s' %s kiosk '%s'.", self.admin_username, new_state, label)
        self._refresh_kiosk_table()

    def _remove_kiosk(self):
        pk = self._selected_kiosk_pk()
        if pk is None:
            QMessageBox.information(self, "No Selection", "Select a kiosk/location to remove first.")
            return
        with get_session() as session:
            kiosk = session.get(Kiosk, pk)
            if not kiosk:
                return
            label = kiosk.location_label

        confirm = QMessageBox.question(
            self, "Confirm Remove",
            f"Remove kiosk '{label}' from the system? Its historical attendance records are kept "
            "(the location name is preserved on each log entry), but the station will need to "
            "re-register the next time it opens the app.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        with get_session() as session:
            kiosk = session.get(Kiosk, pk)
            if kiosk:
                log_kiosk_audit(
                    session, kiosk, "REMOVED", performed_by=self.admin_username,
                    details="Station removed from the system; historical logs retained via snapshot fields.",
                )
            # Preserve history on both tables (snapshot fields already hold the
            # readable info) while avoiding a dangling foreign key after delete.
            session.query(AttendanceLog).filter_by(kiosk_pk=pk).update({"kiosk_pk": None})
            session.query(KioskAuditLog).filter_by(kiosk_pk=pk).update({"kiosk_pk": None})
            if kiosk:
                session.delete(kiosk)

        logger.info("Admin '%s' removed kiosk '%s'.", self.admin_username, label)
        self._refresh_kiosk_table()
        self._refresh_attendance_table()

    # ==================================================================
    # Kiosk Audit Log Tab
    # ==================================================================
    def _build_kiosk_audit_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        info = QLabel(
            "A separate, permanent trail of every kiosk approval/access action taken by an\n"
            "admin — who approved, blocked, unblocked, renamed, or removed which station, and when.\n"
            "This is independent from Attendance Logs, which record face-scan events, not admin actions."
        )
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("↻ Refresh")
        refresh_btn.clicked.connect(self._refresh_kiosk_audit_table)
        btn_row.addStretch()
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self.kiosk_audit_table = QTableWidget(0, 6)
        self.kiosk_audit_table.setHorizontalHeaderLabels(
            ["Timestamp", "Action", "Location", "MAC / Machine User", "Performed By", "Details"]
        )
        self.kiosk_audit_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.kiosk_audit_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.kiosk_audit_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.kiosk_audit_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.kiosk_audit_table)

        return widget

    ACTION_COLORS = {
        "APPROVED": "#27ae60", "BULK_APPROVED": "#27ae60",
        "UNBLOCKED": "#27ae60", "BLOCKED": "#c0392b",
        "REMOVED": "#c0392b", "RENAMED": "#2980b9",
    }
    ACTION_ICONS = {
        "APPROVED": "✅ Approved", "BULK_APPROVED": "✅ Bulk-Approved",
        "UNBLOCKED": "✅ Unblocked", "BLOCKED": "🚫 Blocked",
        "REMOVED": "🗑️ Removed", "RENAMED": "✏️ Renamed",
    }

    def _refresh_kiosk_audit_table(self):
        with get_session() as session:
            entries = (
                session.query(KioskAuditLog)
                .order_by(KioskAuditLog.timestamp.desc())
                .limit(500)
                .all()
            )
            rows = [
                (
                    e.timestamp.strftime("%Y-%m-%d %H:%M:%S") if e.timestamp else "",
                    e.action,
                    e.kiosk_location_snapshot or "(unknown)",
                    f"{e.kiosk_mac_snapshot or '—'} / {e.kiosk_username_snapshot or '—'}",
                    e.performed_by or "—",
                    e.details or "",
                )
                for e in entries
            ]

        self.kiosk_audit_table.setRowCount(0)
        for row_idx, row_data in enumerate(rows):
            self.kiosk_audit_table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data):
                display = self.ACTION_ICONS.get(value, value) if col_idx == 1 else str(value)
                item = QTableWidgetItem(display)
                if col_idx == 1 and value in self.ACTION_COLORS:
                    item.setForeground(QColor(self.ACTION_COLORS[value]))
                self.kiosk_audit_table.setItem(row_idx, col_idx, item)

    # ==================================================================
    # Attendance Logs Tab
    # ==================================================================
    def _build_attendance_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        btn_row = QHBoxLayout()
        filter_label = QLabel("Filter by Location:")
        btn_row.addWidget(filter_label)
        self.attendance_kiosk_filter = QComboBox()
        self.attendance_kiosk_filter.addItem("All Locations")
        self.attendance_kiosk_filter.currentIndexChanged.connect(self._refresh_attendance_table)
        btn_row.addWidget(self.attendance_kiosk_filter)
        btn_row.addStretch()
        refresh_btn = QPushButton("↻ Refresh Logs")
        refresh_btn.clicked.connect(self._refresh_attendance_table)
        btn_row.addWidget(refresh_btn)
        layout.addLayout(btn_row)

        self.attendance_table = QTableWidget(0, 7)
        self.attendance_table.setHorizontalHeaderLabels(
            ["Timestamp", "Employee ID", "Name", "Status", "Location", "MAC Address", "Signal Sent"]
        )
        self.attendance_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.attendance_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.attendance_table)
        return widget

    def _refresh_attendance_table(self):
        location_filter = None
        if hasattr(self, "attendance_kiosk_filter") and self.attendance_kiosk_filter.currentIndex() > 0:
            location_filter = self.attendance_kiosk_filter.currentText()

        with get_session() as session:
            query = session.query(AttendanceLog).order_by(AttendanceLog.timestamp.desc())
            if location_filter:
                query = query.filter(AttendanceLog.kiosk_location_snapshot == location_filter)
            logs = query.limit(500).all()
            rows = [
                (
                    log.timestamp.strftime("%Y-%m-%d %H:%M:%S") if log.timestamp else "",
                    log.employee_id_snapshot or "",
                    log.name_snapshot or "",
                    log.status,
                    log.kiosk_location_snapshot or "—",
                    log.kiosk_mac_snapshot or "—",
                    "Yes" if log.signal_sent else "No",
                )
                for log in logs
            ]

        self.attendance_table.setRowCount(0)
        for row_idx, row_data in enumerate(rows):
            self.attendance_table.insertRow(row_idx)
            for col_idx, value in enumerate(row_data):
                self.attendance_table.setItem(row_idx, col_idx, QTableWidgetItem(str(value)))
