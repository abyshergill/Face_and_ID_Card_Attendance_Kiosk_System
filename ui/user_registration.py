"""
Admin-side dialog to register a NEW employee or EDIT an existing one.
Includes separate handling for AI Training Photos vs the ID Profile Picture.
"""
import logging
from pathlib import Path
import cv2
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap, QIcon
from PyQt5.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMessageBox, QPushButton, QSizePolicy,
    QSpinBox, QVBoxLayout, QDialog, QWidget,
)

import config
from sqlalchemy import func

from database.db_manager import get_session
from database.models import Employee, EmployeePhoto
from face_engine.recognizer import face_recognizer

logger = logging.getLogger("attendance.ui.registration")

class EmployeeRegistrationDialog(QDialog):
    def __init__(self, parent=None, employee_pk=None):
        super().__init__(parent)
        self.employee_pk = employee_pk
        self.is_edit = employee_pk is not None
        self.setWindowTitle("Edit Employee" if self.is_edit else "Register New Employee")
        self.resize(760, 600)

        self.captured_photos = []    
        self.existing_photo_count = 0 
        self.deleted_photo_ids = []  
        self.profile_picture_bytes = None # Stores the raw bytes of the ID card picture
        
        self.cap = None
        self.camera_timer = QTimer(self)
        self.camera_timer.timeout.connect(self._update_camera_frame)

        self._build_ui()
        if self.is_edit:
            self._load_existing_employee()

    def _build_ui(self):
        root = QHBoxLayout(self)

        # ---- Left: employee details form ----
        left_col = QVBoxLayout()
        
        form_box = QGroupBox("Employee Details")
        form = QFormLayout()
        self.name_input = QLineEdit()
        self.age_input = QSpinBox()
        self.age_input.setRange(16, 100)
        self.age_input.setValue(25)
        self.department_input = QLineEdit()
        self.employee_id_input = QLineEdit()
        self.contact_input = QLineEdit()

        form.addRow("Name*:", self.name_input)
        form.addRow("Age:", self.age_input)
        form.addRow("Department:", self.department_input)
        form.addRow("Employee ID*:", self.employee_id_input)
        form.addRow("Contact Information:", self.contact_input)
        form_box.setLayout(form)
        left_col.addWidget(form_box)

        if self.is_edit:
            self.employee_id_input.setEnabled(False)

        # ---- NEW: ID Card Profile Picture Upload ----
        prof_box = QGroupBox("ID Card Profile Picture (Optional)")
        prof_layout = QHBoxLayout()
        
        self.prof_pic_label = QLabel("No Image")
        self.prof_pic_label.setFixedSize(120, 160)
        self.prof_pic_label.setAlignment(Qt.AlignCenter)
        self.prof_pic_label.setStyleSheet("border: 1px dashed #aaa; background: #eee;")
        
        prof_btn_layout = QVBoxLayout()
        prof_btn = QPushButton("Upload ID Picture")
        prof_btn.clicked.connect(self._upload_profile_picture)
        prof_btn_layout.addWidget(prof_btn)
        prof_btn_layout.addStretch()
        
        prof_layout.addWidget(self.prof_pic_label)
        prof_layout.addLayout(prof_btn_layout)
        prof_box.setLayout(prof_layout)
        left_col.addWidget(prof_box)

        left_col.addStretch()

        # Save/Cancel Row
        save_row = QHBoxLayout()
        save_btn = QPushButton("💾 Save Employee")
        save_btn.setStyleSheet("font-weight:600; padding:8px; background:#27ae60; color:white;")
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

        # ---- Right: camera capture panel ----
        cam_box = QGroupBox(f"AI Face Training ({config.MIN_PHOTOS_PER_USER}-{config.MAX_PHOTOS_PER_USER} required)")
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
        
        cam_btn_row.addWidget(self.start_cam_btn)
        cam_btn_row.addWidget(self.capture_btn)
        cam_layout.addLayout(cam_btn_row)

        self.photo_list = QListWidget()
        self.photo_list.setFixedHeight(100)
        self.photo_list.setFlow(QListWidget.LeftToRight)
        self.photo_list.setIconSize(cam_btn_row.sizeHint())
        cam_layout.addWidget(QLabel("Captured AI photos:"))
        cam_layout.addWidget(self.photo_list)

        remove_btn = QPushButton("Remove Selected AI Photo")
        remove_btn.clicked.connect(self._remove_selected_photo)
        cam_layout.addWidget(remove_btn)

        cam_box.setLayout(cam_layout)
        root.addWidget(cam_box, 1)

    def _upload_profile_picture(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Profile Photo", "", "Images (*.jpg *.jpeg *.png)")
        if not file_path:
            return
            
        with open(file_path, "rb") as f:
            self.profile_picture_bytes = f.read()
            
        pixmap = QPixmap()
        pixmap.loadFromData(self.profile_picture_bytes)
        self.prof_pic_label.setPixmap(pixmap.scaled(self.prof_pic_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

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

            # Load Profile Picture
            if emp.profile_picture_data:
                self.profile_picture_bytes = emp.profile_picture_data
                pixmap = QPixmap()
                pixmap.loadFromData(self.profile_picture_bytes)
                self.prof_pic_label.setPixmap(pixmap.scaled(self.prof_pic_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))

            # Load AI Training Photos
            photos = session.query(EmployeePhoto).filter_by(employee_pk=emp.id).all()
            for p in photos:
                item = QListWidgetItem(f"Saved DB Photo")
                item.setData(Qt.UserRole, ("existing", p.id))
                nparr = np.frombuffer(p.image_data, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    h_img, w_img, ch = rgb_img.shape
                    qimg = QImage(rgb_img.data, w_img, h_img, ch * w_img, QImage.Format_RGB888)
                    item.setIcon(QIcon(QPixmap.fromImage(qimg)))
                self.photo_list.addItem(item)
            self.existing_photo_count = len(photos)

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
        
        if self._total_photo_count() >= config.MAX_PHOTOS_PER_USER:
            QMessageBox.information(self, "Limit Reached", f"Maximum {config.MAX_PHOTOS_PER_USER} photos allowed.")
            return
            
        frame = self._last_frame.copy()
        
        _, box = face_recognizer.detect_face(frame)
        if box is None:
            QMessageBox.warning(self, "No Face Detected", "Could not detect a clear face.")
            return

        x, y, w, h = box
        color_face = frame[y:y+h, x:x+w]
        color_face = cv2.resize(color_face, (250, 250))
        
        self.captured_photos.append(color_face)

        item = QListWidgetItem(f"Capture {len(self.captured_photos)}")
        rgb_face = cv2.cvtColor(color_face, cv2.COLOR_BGR2RGB)
        h_img, w_img, ch = rgb_face.shape
        qimg = QImage(rgb_face.data, w_img, h_img, ch * w_img, QImage.Format_RGB888)
        
        item.setData(Qt.UserRole, ("new", color_face))
        item.setIcon(QIcon(QPixmap.fromImage(qimg)))
        self.photo_list.addItem(item)

    def _remove_selected_photo(self):
        row = self.photo_list.currentRow()
        if row < 0:
            return
        item = self.photo_list.item(row)
        kind, payload = item.data(Qt.UserRole)
        
        if kind == "new":
            for i, f in enumerate(self.captured_photos):
                if f is payload:
                    del self.captured_photos[i]
                    break
        else:
            self.deleted_photo_ids.append(payload)
            self.existing_photo_count -= 1
            
        self.photo_list.takeItem(row)

    def _total_photo_count(self):
        return len(self.captured_photos) + self.existing_photo_count

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
            QMessageBox.warning(self, "Not Enough Photos", f"Please capture at least {config.MIN_PHOTOS_PER_USER} AI photos.")
            return

        with get_session() as session:
            if not self.is_edit:
                if session.query(Employee).filter_by(employee_id=employee_id).first():
                    QMessageBox.warning(self, "Duplicate ID", "This Employee ID already exists.")
                    return
                max_label = session.query(func.max(Employee.face_label)).scalar()
                face_label = (max_label or 0) + 1
                
                emp = Employee(
                    employee_id=employee_id, name=name, age=age, department=department,
                    contact=contact, photo_dir="", face_label=face_label,
                    profile_picture_data=self.profile_picture_bytes # Save the Profile Picture
                )
                session.add(emp)
                session.flush() 
            else:
                emp = session.get(Employee, self.employee_pk)
                emp.name = name
                emp.age = age
                emp.department = department
                emp.contact = contact
                emp.profile_picture_data = self.profile_picture_bytes # Save the Profile Picture

            if self.deleted_photo_ids:
                session.query(EmployeePhoto).filter(EmployeePhoto.id.in_(self.deleted_photo_ids)).delete(synchronize_session=False)

            for frame in self.captured_photos:
                ret, buffer = cv2.imencode('.jpg', frame)
                if ret:
                    session.add(EmployeePhoto(employee_pk=emp.id, image_data=buffer.tobytes()))
                else:
                    QMessageBox.critical(self, "Error", "Failed to compress image data.")
                    return

        logger.info("Employee '%s' saved securely to DB.", name)
        self.accept()

    def _on_cancel(self):
        self.reject()

    def closeEvent(self, event):
        if self.cap is not None:
            self.camera_timer.stop()
            self.cap.release()
        event.accept()