"""
Face detection + recognition engine.

Uses OpenCV's Haar Cascade for face detection and LBPH (Local Binary
Patterns Histograms) for recognition. This combination requires no GPU,
no large model downloads, and no dlib compilation - making it easy to
deploy on kiosk-grade Windows/Linux/Raspberry Pi hardware while still
being fully production-capable for single/multi-camera attendance use.
"""
import json
import logging
from pathlib import Path

import cv2
import numpy as np

import config

logger = logging.getLogger("attendance.face")


class FaceRecognizer:

    def __init__(self):
        # 1. Try OpenCV built-in directory (normalized with Path)
        cascade_path = Path(
            cv2.data.haarcascades
        ) / "haarcascade_frontalface_default.xml"

        # 2. Fallback to project's local assets directory
        if not cascade_path.exists():
            cascade_path = (
                Path(__file__).resolve().parents[1]
                / "assets"
                / "haarcascade_frontalface_default.xml"
            )

        # Ensure file exists on disk
        if not cascade_path.exists():
            raise FileNotFoundError(
                f"Cascade XML file not found at: {cascade_path}\n"
                "Please reinstall opencv-python or place the XML in your 'assets' folder."
            )

        # Load into OpenCV using resolved string path
        self.detector = cv2.CascadeClassifier(str(cascade_path.resolve()))

        if self.detector.empty():
            raise RuntimeError(
                f"OpenCV found the file, but failed to parse XML at: {cascade_path}"
            )

        self.recognizer = cv2.face.LBPHFaceRecognizer_create()
        self.label_map = {}  # {int_label: employee_id}
        self._trained = False
        self._model_mtime = None

        config.MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.load()

    # ------------------------------------------------------------------
    def detect_face(self, frame_bgr):
        """Returns (face_roi_gray_200x200, (x,y,w,h)) for the largest detected face, or (None, None)."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = self.detector.detectMultiScale(
            gray, scaleFactor=1.15, minNeighbors=6, minSize=config.FACE_DETECT_MIN_SIZE
        )
        if len(faces) == 0:
            return None, None
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face_roi = cv2.resize(gray[y:y + h, x:x + w], (200, 200))
        return face_roi, (x, y, w, h)

    # ------------------------------------------------------------------
    def train(self, employees):
        """
        employees: iterable of (face_label:int, employee_id:str, photo_dir:str)
        Retrains the LBPH model from scratch using all enrollment photos on disk.
        """
        faces, labels = [], []
        new_label_map = {}

        for face_label, employee_id, photo_dir in employees:
            new_label_map[face_label] = employee_id
            photo_path = Path(photo_dir)
            if not photo_path.exists():
                continue
            for img_file in sorted(photo_path.glob("*.jpg")):
                img = cv2.imread(str(img_file), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                face_roi, _ = self.detect_face(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
                if face_roi is None:
                    face_roi = cv2.resize(img, (200, 200))
                faces.append(face_roi)
                labels.append(face_label)
        print("TRAIN DEBUG:", employee_id, photo_dir, list(photo_path.glob("*.jpg")))
        if not faces:
            logger.warning("No enrollment images found - model NOT trained yet.")
            self._trained = False
            return False

        self.recognizer.train(faces, np.array(labels))
        self.label_map = new_label_map
        self._trained = True
        self.save()
        logger.info("Model retrained on %d images across %d employees.", len(faces), len(new_label_map))
        return True

    # ------------------------------------------------------------------
    def predict(self, face_roi_gray):
        """Returns (employee_id, confidence_distance) or (None, None) if not trained."""
        if not self._trained:
            return None, None
        label, confidence = self.recognizer.predict(face_roi_gray)
        return self.label_map.get(label), confidence

    # ------------------------------------------------------------------
    def save(self):
        self.recognizer.write(str(config.MODEL_PATH))
        with open(config.LABEL_MAP_PATH, "w") as f:
            json.dump(self.label_map, f)

    def load(self):
        try:
            if config.MODEL_PATH.exists() and config.LABEL_MAP_PATH.exists():
                self.recognizer.read(str(config.MODEL_PATH))
                with open(config.LABEL_MAP_PATH) as f:
                    raw = json.load(f)
                self.label_map = {int(k): v for k, v in raw.items()}
                self._trained = True
                self._model_mtime = config.MODEL_PATH.stat().st_mtime
                logger.info("Loaded existing face model (%d enrolled employees).", len(self.label_map))
        except Exception:
            logger.exception("Failed to load existing face model - starting untrained.")
            self._trained = False

    def reload_if_changed(self) -> bool:
        """
        Re-reads the model file from disk if its modification time has
        advanced since the last load. Used by remote User-Mode kiosks that
        share a network model path with the Admin dashboard PC, so a kiosk
        automatically picks up newly enrolled employees without needing a
        restart. Returns True if a reload actually happened.
        """
        try:
            if not config.MODEL_PATH.exists():
                return False
            mtime = config.MODEL_PATH.stat().st_mtime
            if self._model_mtime is None or mtime > self._model_mtime:
                self.load()
                return True
        except Exception:
            logger.exception("Failed while checking/reloading the face model for updates.")
        return False

    @property
    def is_trained(self):
        return self._trained


# Singleton used across the application
face_recognizer = FaceRecognizer()
