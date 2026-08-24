"""Background QThread workers so long-running tasks never freeze the UI."""
import logging

from PyQt5.QtCore import QThread, pyqtSignal

from database.db_manager import get_session
from database.models import Employee
from face_engine.recognizer import face_recognizer

logger = logging.getLogger("attendance.ui.workers")


class RetrainWorker(QThread):
    """Retrains the LBPH face model from all active employees on disk."""
    finished_ok = pyqtSignal(bool)

    def run(self):
        try:
            with get_session() as session:
                employees = [
                    (e.face_label, e.employee_id, e.photo_dir)
                    for e in session.query(Employee).filter_by(is_active=True).all()
                ]
            ok = face_recognizer.train(employees)
            self.finished_ok.emit(ok)
        except Exception:
            logger.exception("Retraining failed.")
            self.finished_ok.emit(False)
