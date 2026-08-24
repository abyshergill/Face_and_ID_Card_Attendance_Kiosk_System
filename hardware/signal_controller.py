"""
Physical PASS/FAIL signal output for integrating this application with an
external microcontroller (Arduino, ESP32, relay board, turnstile
controller, door strike, LED/buzzer, etc.).

Two transport modes are supported out of the box:
  - SERIAL : writes a single byte over a USB/UART serial connection.
             On the microcontroller side, simply read one byte and act on
             it, e.g. (Arduino sketch sketch):
                 void loop() {
                   if (Serial.available()) {
                     char c = Serial.read();
                     if (c == '1') digitalWrite(RELAY_PIN, HIGH); // PASS
                     if (c == '0') digitalWrite(RELAY_PIN, LOW);  // FAIL/idle
                   }
                 }
  - GPIO   : drives a physical GPIO pin HIGH for a short pulse
             (Raspberry Pi only, via RPi.GPIO).

Both modes are fully optional and safely guarded: if the enabled hardware
library or physical device is not present (e.g. running on a developer's
Windows laptop with no Arduino attached), the controller logs a warning
and the rest of the application keeps working normally.
"""
import logging
import threading
import time

import config

logger = logging.getLogger("attendance.hardware")


class SignalController:
    def __init__(self):
        self.enabled = config.HARDWARE_SIGNAL_ENABLED
        self.mode = config.HARDWARE_SIGNAL_MODE
        self._serial_conn = None
        self._gpio_ready = False

        if not self.enabled:
            logger.info("Hardware signal output disabled (ATTENDANCE_HW_ENABLED=false).")
            return

        if self.mode == "SERIAL":
            self._init_serial()
        elif self.mode == "GPIO":
            self._init_gpio()
        else:
            logger.info("Hardware signal mode is NONE - no physical signal will be sent.")

    # ------------------------------------------------------------------
    def _init_serial(self):
        try:
            import serial  # pyserial
            self._serial_conn = serial.Serial(config.SERIAL_PORT, config.SERIAL_BAUDRATE, timeout=1)
            logger.info("Serial hardware link opened on %s @ %d baud.", config.SERIAL_PORT, config.SERIAL_BAUDRATE)
        except Exception as e:
            logger.warning(
                "Could not open serial port '%s' (%s). Continuing WITHOUT hardware signal output.",
                config.SERIAL_PORT, e,
            )
            self._serial_conn = None

    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO  # only importable on a Raspberry Pi
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(config.GPIO_PASS_PIN, GPIO.OUT, initial=GPIO.LOW)
            self._gpio_ready = True
            logger.info("GPIO hardware link ready on BCM pin %d.", config.GPIO_PASS_PIN)
        except Exception as e:
            logger.warning("RPi.GPIO unavailable (%s). Continuing WITHOUT hardware signal output.", e)
            self._gpio_ready = False

    # ------------------------------------------------------------------
    def send_pass(self) -> bool:
        """Trigger the physical PASS signal - call this on a successful face match."""
        if not self.enabled:
            return False
        if self.mode == "SERIAL":
            return self._send_serial(config.SERIAL_PASS_BYTE)
        if self.mode == "GPIO":
            return self._pulse_gpio()
        return False

    def send_fail(self) -> bool:
        """Optionally notify hardware of a failed scan (e.g. red LED / buzzer)."""
        if not self.enabled:
            return False
        if self.mode == "SERIAL":
            return self._send_serial(config.SERIAL_FAIL_BYTE)
        return False

    # ------------------------------------------------------------------
    def _send_serial(self, payload: bytes) -> bool:
        if not self._serial_conn:
            logger.debug("Serial signal skipped - no active connection.")
            return False
        try:
            self._serial_conn.write(payload)
            logger.info("Hardware signal sent over serial: %s", payload)
            return True
        except Exception as e:
            logger.error("Failed to send serial signal: %s", e)
            return False

    def _pulse_gpio(self) -> bool:
        if not self._gpio_ready:
            logger.debug("GPIO signal skipped - GPIO not ready.")
            return False
        try:
            import RPi.GPIO as GPIO

            def _pulse():
                GPIO.output(config.GPIO_PASS_PIN, GPIO.HIGH)
                time.sleep(config.GPIO_PULSE_SECONDS)
                GPIO.output(config.GPIO_PASS_PIN, GPIO.LOW)

            threading.Thread(target=_pulse, daemon=True).start()
            logger.info("GPIO pin %d pulsed for %.1fs.", config.GPIO_PASS_PIN, config.GPIO_PULSE_SECONDS)
            return True
        except Exception as e:
            logger.error("Failed to pulse GPIO pin: %s", e)
            return False

    def close(self):
        if self._serial_conn:
            try:
                self._serial_conn.close()
            except Exception:
                pass
        if self._gpio_ready:
            try:
                import RPi.GPIO as GPIO
                GPIO.cleanup()
            except Exception:
                pass


# Singleton used across the application
signal_controller = SignalController()
