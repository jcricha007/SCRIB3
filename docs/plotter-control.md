# Connect and bring up the plotter

The **Control** tab provides a persistent GRBL 1.1 connection, live work/machine XY positions in millimeters, active input pins, controller setup, homing, step jogging, paper zero, and pen controls. The Arduino stores settings in EEPROM; the **Machine** tab contains the drawing/export and pen-command values.

## Connection

Close any serial monitor or sender using the Arduino. Select **Auto detect** to scan available serial ports and these baud rates: 115200, 57600, 38400, 19200, 9600, 230400, 250000. SCRIB3 accepts a valid GRBL 1.1 status response before connecting. The scan can be cancelled. For a known device, use **Find ports**, choose its port and baud, and select **Connect**. The port and baud fields also accept a manually entered value.

Discovery sends only realtime status requests (`?`). Opening each serial connection may reset the board, execute its configured startup blocks, and move the servo. A complete scan can take about 18 seconds per port; a busy port is skipped. macOS outbound `/dev/cu.*` ports are preferred over duplicate `/dev/tty.*` aliases. Detection identifies a GRBL responder, not an Arduino model or the exact installed servo fork. When several controllers are attached, use an explicit port to select the intended one.

The supplied source sets `BAUD_RATE 115200` in `config.h`. GRBL has no runtime baud-setting command. The baud field and `--baud` configure the computer's serial connection; changing the firmware baud requires rebuilding and flashing the controller. This update does not flash firmware.

### From a Mac terminal

From the repository folder, detect a device at the supplied firmware's rate and open the connected application:

```bash
bash Run-SCRIB3.command --connect auto --baud 115200
```

To try all supported baud rates, omit `--baud 115200`. To scan and print the detected port/rate without opening the main application:

```bash
.venv-macos/bin/python -m scrib3 --scan
```

For an explicit port:

```bash
.venv-macos/bin/python -m scrib3 --connect /dev/cu.usbmodem1101 --baud 115200
```

### From Windows PowerShell

With the repository's Python environment installed:

```powershell
.\.venv\Scripts\python.exe -m scrib3 --connect auto --baud 115200
```

Use `--connect COM3 --baud 115200` for a known port, or `--scan` to print discovery results. No-argument launch still opens the drawing workbench without touching serial ports.

## Setup and first movement

1. Connect and open **Setup…**. Values come from the Arduino, including steps/mm, X/Y maximum travel, rate, acceleration, direction masks, limits, homing, and spindle settings. **Apply changed settings** writes only edited values, one acknowledged setting at a time, then reads back the controller. An error stops the remaining writes; earlier successful changes stay saved. Reopen Setup to see the resulting values.
2. Check the limit switches using **Active inputs**. Enable homing only when the switches, their polarity, seek direction, and pull-off are configured. The supplied firmware homes X and Y together; `$22=0` disables homing by default. **Home** sends `$H` and uses the installed firmware's homing cycle. Homing has a 180-second response timeout. Firmware startup blocks may run after successful homing.
3. With the pen clear of the paper, start with the default **1 mm** step and **300 mm/min** feed. Each X/Y button requests one incremental jog. Wait for **Idle** before the next move. Verify direction and measured travel, then calibrate steps/mm in Setup if needed. The maximum step accepted by the app is 100 mm. GRBL enforces enabled soft/hard limits; the app cannot infer physical travel limits or switch locations from an uncalibrated board.
4. On **Machine**, choose the appropriate firmware profile and enter the lift commands. Test **Pen up** and **Pen down** on Control. The uploaded RC-servo profile checks the current `$30`, `$31`, `$32`, and spindle override before issuing a pen command. Its pulse limits are described in [firmware.md](firmware.md). Z lift commands run in absolute millimeters in G54 with tool-length offset disabled, matching exported jobs. PWM commands and settle time use the entered values.
5. Jog to the paper's lower-left corner and select **Paper XY zero**. This selects G54, clears all temporary G92 offsets, and writes the current XY location as G54 zero (`G10 L20 P1 X0 Y0`). It does not move an axis or change the G54 Z offset. Clearing a previous G92 Z offset also changes the displayed Z reference; recheck a Z-based pen lift if one was active. Re-establish the origin after a reset, missed steps, or power loss.
6. Use **Machine → Use controller X/Y travel** if the controller's travel settings match the plotter's usable paper area. Review and export a drawing as before. Full drawing/job streaming remains a later step; this update adds setup and manual control.

Homing finds a machine reference using switches. Paper zero defines where the drawing starts. **Unlock alarm** explicitly sends `$X`; unlocking does not establish a machine reference or verify the reason for the alarm.

## Cancellation, reset, and failures

- **Cancel jog** sends GRBL's realtime jog-cancel byte, including while a jog acknowledgement is pending. It is intended for XY jogging. Use **Reset / abort** to interrupt homing or a pending pen operation.
- **Reset / abort** sends a soft reset and closes the connection. Reset may change the servo position. Reconnect, resolve any alarm, and re-establish the machine/work reference before moving.
- Disconnecting or closing the app during active or unconfirmed motion sends a reset before closing the port. A lost cable or unresponsive controller can prevent delivery; software cannot confirm a physical stop in that situation.
- The worker keeps status polling and reset/cancel processing active during command waits. It sends one normal command at a time and does not retry unacknowledged motion. Stale status disables normal controls. An alarm during a command, serial failure, unexpected restart, or timeout invalidates the session and its cached settings. Normal acknowledgements are distinct from motion completion; the live state must return to Idle before another move.
- **Read GRBL** refreshes settings/parser/offsets on the existing connection. **Connection log** shows recent commands and replies for troubleshooting. It never opens a second connection to the same Arduino.

## Validation and protocol references

Automated tests use a simulated serial peer for fragmented replies, delayed acknowledgements, busy-state gating, cancel/reset during motion, failed settings writes, unit conversion, servo validation, discovery, and CLI routing. Desktop checks exercise the actual Tk controls with that peer. Physical motion, native Mac/Windows USB behavior, and the exact installed firmware still require verification on the assembled plotter.

- [GRBL 1.1 jogging](https://github.com/gnea/grbl/blob/master/doc/markdown/jogging.md)
- [GRBL serial interface](https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md)
- [GRBL settings](https://github.com/gnea/grbl/blob/master/doc/markdown/settings.md)

To include the desktop test when a graphical display is available, set `SCRIB3_DESKTOP_TESTS=1` before running the unit suite. For example, on Mac:

```bash
SCRIB3_DESKTOP_TESTS=1 .venv-macos/bin/python -m unittest discover -s tests -v
```

The desktop test uses a simulated serial peer and never opens a physical serial port.
