## Troubleshooting

**Q: The app crashes on startup with a "Serial" error.**

* Make sure your Arduino is plugged in.
* Check your Device Manager (Windows) or run `ls /dev/tty*` (Linux) to verify the correct COM port. Update `ATTENDANCE_SERIAL_PORT` in your `.env` file to match.
* Ensure no other program (like the Arduino IDE Serial Monitor) is currently connected to that port.

**Q: The scan is successful, but the door doesn't open.**

* Go to the Admin Dashboard -> Settings tab, and ensure **"Enable Hardware Signal"** is checked.
* Ensure the Baud Rate in your `.env` (`9600`) matches the `Serial.begin(9600);` in your Arduino code.
* Check the physical relay: Does it "click" when a face is scanned? If it clicks but the door doesn't open, the issue is your physical wiring to the magnetic lock, not the software.

**Q: Can I trigger different turnstiles from different PCs?**

* Yes! Just run a local Arduino on each Kiosk PC. Because Kiosk 1 is connected to `COM3` locally, and Kiosk 2 is connected to `COM3` locally, they operate their own local doors independently while sharing the same central database.