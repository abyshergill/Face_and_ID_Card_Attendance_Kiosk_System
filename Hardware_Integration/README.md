# Hardware Integration Guide: Doors, Turnstiles & Relays

The Face Attendance System isn't just for logging data—it can physically unlock doors, trigger turnstiles, or flash LEDs the exact moment a successful face or card scan occurs.

This guide explains how to connect the software to external hardware using either **Serial Communication** (Arduino, ESP32, USB Relays) or **Direct GPIO** (Raspberry Pi).

---

## 1. How It Works (High Level)

1. A user approaches the Kiosk and scans their face or ID card.
2. The system verifies the identity against the PostgreSQL/SQLite database.
3. If successful, the `SignalController` checks if Hardware Signalling is enabled globally.
4. The system sends an electrical pulse via **GPIO** or a data byte (`1` or `0`) via **USB/Serial** to an external microcontroller.
5. The microcontroller triggers a physical Relay, which opens the magnetic door lock or turnstile.

---

## 2. Enabling Hardware Signalling in the App

You can enable or disable the hardware signal instantly across all kiosks without editing any code.

1. Log into the **Admin Dashboard**.
2. Go to the **System Settings** tab.
3. Check the box labeled **"Enable Hardware Signal (Turnstiles, Doors, Relays)"**.
4. The setting is saved instantly to the database and takes effect immediately.

---

## 3. Configuration (`.env` File)

Before opening the application, you need to tell the kiosk *how* to communicate with your hardware. Open your `.env` file (located in the root folder of the kiosk) and configure the following variables:

```env
# Enable/Disable locally (Overridden by Admin Dashboard)
ATTENDANCE_HW_ENABLED=true

# Choose Mode: "SERIAL" (Arduino/USB) or "GPIO" (Raspberry Pi)
ATTENDANCE_HW_MODE=SERIAL

# --- If using SERIAL (Arduino / ESP32) ---
# Windows: COM3, COM4, etc. 
# Linux/Mac: /dev/ttyUSB0 or /dev/ttyACM0
ATTENDANCE_SERIAL_PORT=COM3
ATTENDANCE_SERIAL_BAUD=9600

# --- If using GPIO (Raspberry Pi Only) ---
ATTENDANCE_GPIO_PIN=17
ATTENDANCE_GPIO_PULSE=1.5

```

*(Note: You must install `pyserial` to use Serial mode. Run `pip install pyserial`).*

---

## 4. Method A: Serial Communication (Arduino / ESP32)

*This is the most common and reliable setup for Windows/Linux desktop kiosks.*

### The Setup:

1. Connect an Arduino Uno/Nano or ESP32 to your Kiosk PC via USB.
2. Connect a **5V Relay Module** to the Arduino (e.g., Signal pin to Arduino Digital Pin 8).
3. Connect your Door Magnetic Lock or Turnstile controller to the Relay's COM (Common) and NO (Normally Open) terminals.

### The Microcontroller Code:

Upload this C++ sketch to your Arduino using the Arduino IDE. It listens for the `1` byte sent by our Python software.

```cpp
const int RELAY_PIN = 8;        // The pin connected to your Relay module
const int UNLOCK_TIME = 2000;   // Keep door open for 2 seconds (2000 ms)

void setup() {
  Serial.begin(9600);           // Must match ATTENDANCE_SERIAL_BAUD in .env
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW); // Lock the door by default
}

void loop() {
  if (Serial.available() > 0) {
    char incomingByte = Serial.read();
    
    // Python sends "1" on successful scan
    if (incomingByte == '1') {
      digitalWrite(RELAY_PIN, HIGH); // Trigger relay (Unlock door)
      delay(UNLOCK_TIME);            // Wait
      digitalWrite(RELAY_PIN, LOW);  // Lock door again
    }
    // Python sends "0" on failed scan (optional: wire up a red LED/buzzer)
    else if (incomingByte == '0') {
      // Trigger error buzzer here if desired
    }
  }
}

```

---

## 5. Method B: Direct GPIO (Raspberry Pi)

*Use this method if your kiosk is running directly on a Raspberry Pi.*

In `GPIO` mode, the Python app bypasses USB entirely and sends a 3.3V pulse directly to one of the Pi's physical pins.

### The Setup:

1. Ensure your `.env` is set to `ATTENDANCE_HW_MODE=GPIO`.
2. Install the GPIO library on your Pi: `pip install RPi.GPIO`.
3. Connect the **Signal (S)** pin of a 3.3V Relay module to **Pin 11 (GPIO 17)** on the Raspberry Pi.
4. Connect the Relay's VCC to Pi 3.3V and GND to Pi Ground.

When a successful scan occurs, Python will automatically turn GPIO 17 `HIGH` for the duration specified in `ATTENDANCE_GPIO_PULSE` (e.g., 1.5 seconds), and then turn it `LOW` again.

## `Note :`
If face issue with hardware integration follow : [Troubleshoot Guide](./Troubleshoot/README.md)


