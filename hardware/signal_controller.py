"""Hardware Signal Controller (Turnstiles, Doors, Relays)"""
import logging
import config

try:
    import serial
except ImportError:
    serial = None

logger = logging.getLogger("attendance.hardware")

class SignalController:
    def __init__(self):
        self.mode = config.HARDWARE_SIGNAL_MODE
        self.ser = None

        if self.mode == "SERIAL":
            if serial is None:
                logger.error("pyserial is not installed. Cannot use SERIAL hardware mode.")
            else:
                try:
                    self.ser = serial.Serial(config.SERIAL_PORT, config.SERIAL_BAUDRATE, timeout=1)
                    logger.info(f"Hardware signal ready on {config.SERIAL_PORT} ({self.mode}).")
                except Exception as e:
                    logger.error(f"Could not open serial port {config.SERIAL_PORT}: {e}")

    def send_pass(self, is_enabled: bool = False) -> bool:
        if not is_enabled:
            return False
        if self.mode == "SERIAL" and self.ser and self.ser.is_open:
            try:
                self.ser.write(config.SERIAL_PASS_BYTE)
                return True
            except Exception as e:
                logger.error(f"Serial write error: {e}")
        return False

    def send_fail(self, is_enabled: bool = False) -> bool:
        if not is_enabled:
            return False
        if self.mode == "SERIAL" and self.ser and self.ser.is_open:
            try:
                self.ser.write(config.SERIAL_FAIL_BYTE)
                return True
            except Exception as e:
                logger.error(f"Serial write error: {e}")
        return False

    def close(self):
        if self.ser and self.ser.is_open:
            self.ser.close()

signal_controller = SignalController()