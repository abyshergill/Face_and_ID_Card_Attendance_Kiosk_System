"""
Admin-side dialog to register a NEW employee or EDIT an existing one,
including live-camera capture of the 3-5 enrollment photos required for
face recognition training.
"""
import logging
import shutil
from pathlib import Path

import cv2
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSizePolicy,
    QSpinBox, QVBoxLayout, QDialog, QWidget,
)

import config
from sqlalchemy import func

from database.db_manager import get_session
from database.models import Employee
from face_engine.recognizer import face_recognizer

logger = logging.getLogger("attendance.ui.registration")


class EmployeeRegistrationDialog(QDialog):
    """
    Pass `employee_id` (the DB primary key `Employee.id`, not the badge
    number) to edit an existing record, or leave it as None to register a
    brand-new employee.
    """

    def __init__(self, parent=None, employee_pk=None):
        super().__init__(parent)
        self.employee_pk = employee_pk
        self.is_edit = employee_pk is not None
        self.setWindowTitle("Edit Employee" if self.is_edit else "Register New Employee")
        self.resize(760, 520)

        self.captured_photos = []   # list of numpy BGR frames captured this session
        self.existing_photo_files = []  # existing jpg paths (edit mode, kept unless re-captured)
        self.cap = None
        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self._update_camera_frame)

        self._build_ui()
        if self.is_edit:
            self._load_existing_employee()

    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QHBoxLayout(self)

        # ---- Left: employee details form ----
        form_box = QGroupBox("Employee Details")
        form = QFormLayout()
        self.name_input = QLineEdit()
        self.age_input = QSpinBox()
        self.age_input.setRange(16, 100)
        self.age_input.setValue(25)
        self.department_input = QLineEdit()
        self.employee_id_input = QLineEdit()
        self.contact_input = QLineEdit()
        self.contact_input.setPlaceholderText("Phone / Email")

        form.addRow("Name*:", self.name_input)
        form.addRow("Age:", self.age_input)
        form.addRow("Department:", self.department_input)
        form.addRow("Employee ID*:", self.employee_id_input)
        form.addRow("Contact Information:", self.contact_input)
        form_box.setLayout(form)

        if self.is_edit:
            self.employee_id_input.setEnabled(False)  # employee_id is immutable once created

        # ---- Right: camera capture panel ----
        cam_box = QGroupBox(f"Face Enrollment ({config.MIN_PHOTOS_PER_USER}-{config.MAX_PHOTOS_PER_USER} photos required)")
        cam_layout = QVBoxLayout()

        self.camera_label = QLabel("Camera preview will appear here")
        self.camera_label.setFixedSize(320, 240)
        self.camera_label.setStyleSheet("background:#111; color:#888; border-radius:6px;")
        self.camera_label.setAlignment(Qt.AlignCenter)
        cam_layout.addWidget(self.camera_label, alignment=Qt.AlignCenter)

        cam_btn_row = QHBoxLayout()
        self.start_cam_btn = QPushButton("Start Camera")
        self.start_cam_btn.clicked.connect(self._toggle_camera)
        self.capture_btn = QPushButton("📸 Capture Photo")
        self.capture_btn.setEnabled(False)
        self.capture_btn.clicked.connect(self._capture_photo)
        self.upload_btn = QPushButton("Upload From File")
        self.upload_btn.clicked.connect(self._upload_photo)
        cam_btn_row.addWidget(self.start_cam_btn)
        cam_btn_row.addWidget(self.capture_btn)
        cam_btn_row.addWidget(self.upload_btn)
        cam_layout.addLayout(cam_btn_row)

        self.photo_list = QListWidget()
        self.photo_list.setFixedHeight(90)
        self.photo_list.setFlow(QListWidget.LeftToRight)
        self.photo_list.setIconSize(cam_btn_row.sizeHint())
        cam_layout.addWidget(QLabel("Captured photos:"))
        cam_layout.addWidget(self.photo_list)

        remove_btn = QPushButton("Remove Selected Photo")
        remove_btn.clicked.connect(self._remove_selected_photo)
        cam_layout.addWidget(remove_btn)

        cam_box.setLayout(cam_layout)

        left_col = QVBoxLayout()
        left_col.addWidget(form_box)
        left_col.addStretch()

        save_row = QHBoxLayout()
        save_btn = QPushButton("💾 Save Employee")
        save_btn.setStyleSheet("font-weight:600; padding:8px;")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self._on_cancel)
        save_row.addWidget(save_btn)
        save_row.addWidget(cancel_btn)
        left_col.addLayout(save_row)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        left_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        root.addWidget(left_widget, 1)
        root.addWidget(cam_box, 1)

    # ------------------------------------------------------------------
    def _load_existing_employee(self):
        with get_session() as session:
            emp = session.get(Employee, self.employee_pk)
            if not emp:
                return
            self.name_input.setText(emp.name)
            self.age_input.setValue(emp.age or 25)
            self.department_input.setText(emp.department or "")
            self.employee_id_input.setText(emp.employee_id)
            self.contact_input.setText(emp.contact or "")

            photo_dir = Path(emp.photo_dir)
            if photo_dir.exists():
                self.existing_photo_files = sorted(photo_dir.glob("*.jpg"))
                for p in self.existing_photo_files:
                    item = QListWidgetItem(p.name)
                    item.setData(Qt.UserRole, ("existing", str(p)))
                    self.photo_list.addItem(item)

    # ------------------------------------------------------------------
    def _toggle_camera(self):
        if self.cap is None:
            self.cap = cv2.VideoCapture(config.CAMERA_INDEX)
            if not self.cap.isOpened():
                QMessageBox.critical(self, "Camera Error", "Could not access the webcam.")
                self.cap = None
                return
            self.camera_timer.start(30)
            self.start_cam_btn.setText("Stop Camera")
            self.capture_btn.setEnabled(True)
        else:
            self.camera_timer.stop()
            self.cap.release()
            self.cap = None
            self.camera_label.setText("Camera stopped")
            self.start_cam_btn.setText("Start Camera")
            self.capture_btn.setEnabled(False)

    def _update_camera_frame(self):
        if self.cap is None:
            return
        ok, frame = self.cap.read()
        if not ok:
            return
        self._last_frame = frame
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        self.camera_label.setPixmap(
            QPixmap.fromImage(qimg).scaled(self.camera_label.size(), Qt.KeepAspectRatio)
        )

    def _capture_photo(self):
        if not hasattr(self, "_last_frame"):
            return
        total = len(self.captured_photos) + len(self.existing_photo_files)
        if total >= config.MAX_PHOTOS_PER_USER:
            QMessageBox.information(self, "Limit Reached", f"Maximum {config.MAX_PHOTOS_PER_USER} photos allowed.")
            return
        frame = self._last_frame.copy()
        self.captured_photos.append(frame)

        item = QListWidgetItem(f"capture_{len(self.captured_photos)}.jpg")
        item.setData(Qt.UserRole, ("new", frame))
        self.photo_list.addItem(item)

    def _upload_photo(self):
        total = len(self.captured_photos) + len(self.existing_photo_files)
        if total >= config.MAX_PHOTOS_PER_USER:
            QMessageBox.information(self, "Limit Reached", f"Maximum {config.MAX_PHOTOS_PER_USER} photos allowed.")
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Photo", "", "Images (*.jpg *.jpeg *.png)")
        if not file_path:
            return
        frame = cv2.imread(file_path)
        if frame is None:
            QMessageBox.warning(self, "Invalid Image", "Could not read the selected image file.")
            return
        self.captured_photos.append(frame)
        item = QListWidgetItem(Path(file_path).name)
        item.setData(Qt.UserRole, ("new", frame))
        self.photo_list.addItem(item)

    def _remove_selected_photo(self):
        row = self.photo_list.currentRow()
        if row < 0:
            return
        item = self.photo_list.item(row)
        kind, payload = item.data(Qt.UserRole)
        if kind == "new":
            # remove matching frame from captured_photos (by identity/order)
            new_frames = []
            removed = False
            for f in self.captured_photos:
                if not removed and f is payload:
                    removed = True
                    continue
                new_frames.append(f)
            self.captured_photos = new_frames
        else:
            self.existing_photo_files = [p for p in self.existing_photo_files if str(p) != payload]
        self.photo_list.takeItem(row)

    def _total_photo_count(self):
        return len(self.captured_photos) + len(self.existing_photo_files)

    # ------------------------------------------------------------------
    def _save(self):
        name = self.name_input.text().strip()
        employee_id = self.employee_id_input.text().strip()
        department = self.department_input.text().strip()
        contact = self.contact_input.text().strip()
        age = self.age_input.value()

        if not name or not employee_id:
            QMessageBox.warning(self, "Missing Fields", "Name and Employee ID are required.")
            return

        if self._total_photo_count() < config.MIN_PHOTOS_PER_USER:
            QMessageBox.warning(
                self, "Not Enough Photos",
                f"Please capture/upload at least {config.MIN_PHOTOS_PER_USER} photos "
                f"(currently have {self._total_photo_count()})."
            )
            return

        with get_session() as session:
            if not self.is_edit:
                if session.query(Employee).filter_by(employee_id=employee_id).first():
                    QMessageBox.warning(self, "Duplicate Employee ID", "This Employee ID already exists.")
                    return
                max_label = session.query(func.max(Employee.face_label)).scalar()
                face_label = (max_label or 0) + 1
                photo_dir = config.FACE_DIR / employee_id
                photo_dir.mkdir(parents=True, exist_ok=True)
                emp = Employee(
                    employee_id=employee_id, name=name, age=age, department=department,
                    contact=contact, photo_dir=str(photo_dir), face_label=face_label,
                )
                session.add(emp)
                session.flush()
            else:
                emp = session.get(Employee, self.employee_pk)
                emp.name = name
                emp.age = age
                emp.department = department
                emp.contact = contact
                photo_dir = Path(emp.photo_dir)
                photo_dir.mkdir(parents=True, exist_ok=True)

            # Persist only the photos still referenced in the list widget.
            # Remove stale files first, then write new captures.
            kept_existing = {str(p) for p in self.existing_photo_files}
            if photo_dir.exists():
                for f in photo_dir.glob("*.jpg"):
                    if str(f) not in kept_existing:
                        try:
                            f.unlink()
                        except OSError:
                            pass

            next_index = len(list(photo_dir.glob("*.jpg"))) + 1
            for frame in self.captured_photos:
                out_path = photo_dir / f"photo_{next_index}.jpg"
                ok = cv2.imwrite(str(out_path), frame)
                if not ok:
                    QMessageBox.critical(
                        self,
                        "Photo Save Failed",
                        f"Could not save photo to:\n{out_path}"
                    )
                    return
                next_index += 1


            self.saved_employee_id = emp.employee_id

        logger.info("Employee '%s' (%s) saved.", name, employee_id)
        self.accept()

    def _on_cancel(self):
        self.reject()

    def closeEvent(self, event):
        if self.cap is not None:
            self.camera_timer.stop()
            self.cap.release()
        event.accept()
