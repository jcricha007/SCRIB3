# Connect and bring up the plotter

After setup, use the [guided calibration](calibration.md) and [Run sketch](running-sketches.md) guides to verify travel and test a drawing directly in SCRIB3.

The **Control** tab provides a persistent GRBL 1.1 connection, live work/machine XY positions in the selected display units, active input pins, controller setup, homing, step jogging, paper zero, and pen controls. The Arduino stores settings in EEPROM; the **Machine** tab contains the drawing/export and pen-command values.

## Connection

Close any serial monitor or sender using the Arduino. Select **Auto detect** to scan available serial ports and these baud rates: 115200, 57600, 38400, 19200, 9600, 230400, 250000. SCRIB3 accepts a valid GRBL 1.1 status response before connecting. The scan can be cancelled. For a known device, use **Find ports**, choose its port and baud, and select **Connect**. The port and baud fields also accept a manually entered value.

Discovery sends only realtime status requests (`?`). Opening each serial connection may reset the board, execute its configured startup blocks, and move the servo. A complete scan can take about 18 seconds per port; a busy port is skipped. macOS outbound `/dev/cu.*` ports are preferred over duplicate `/dev/tty.*` aliases. Detection identifies a GRBL responder, not an Arduino model or the exact installed servo fork. When several controllers are attached, use an explicit port to select the intended one.

After detection, the desktop connection automatically checks the [59.06 in/min motion baseline](smooth-motion-paper.md), writes only changed profile values while Idle, and verifies readback before normal motion. An Alarm waits for the operator to resolve it; a failed setup keeps normal motion unavailable. Discovery/terminal scan stays read-only.

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
2. Check the limit switches using **Active inputs**. Enable homing only when the switches, their polarity, seek direction, and pull-off are configured. The supplied firmware homes X and Y together; `$22=0` disables homing by default. **Switch home** sends `$H` and uses the installed firmware's homing cycle. Homing has a 180-second response timeout. Firmware startup blocks may run after successful homing.
3. With the pen clear of the paper, start with the bundled preset's **0.01 in** step and **59.06 in/min** feed (0.254 mm and 1,500 mm/min). Each X/Y button requests one incremental jog. Wait for **Idle** before the next move. Verify direction and measured travel, then calibrate steps/mm in Setup if needed. The maximum step accepted by the app is 100 mm (about 3.937 in). GRBL enforces enabled soft/hard limits; the app cannot infer physical travel limits or switch locations from an uncalibrated board.
4. On **Machine**, choose the appropriate firmware profile and enter the lift commands. Test **Pen up** and **Pen down** on Control. The uploaded RC-servo profile checks the current `$30`, `$31`, `$32`, and spindle override before issuing a pen command. Its pulse limits are described in [firmware.md](firmware.md). Z lift commands run in absolute millimeters in G54 with tool-length offset disabled, matching exported jobs. PWM commands and settle time use the entered values.
5. Jog to the paper corner selected in **Design → Paper guide** (top-left for John's setup) and select **Paper XY zero**. This selects G54, clears all temporary G92 offsets, and writes the current XY location as G54 zero (`G10 L20 P1 X0 Y0`). It does not move an axis or change the G54 Z offset. Clearing a previous G92 Z offset also changes the displayed Z reference; recheck a Z-based pen lift if one was active. Re-establish the origin after a reset, missed steps, or power loss.
6. Use **Machine → Use controller X/Y travel** only if the controller's travel settings match the measured usable envelope. Open **Review G-code**, keep **Pen-up test** selected for the first run, and choose **Run sketch**. See the [drawing guide](running-sketches.md) and [hardware acceptance procedure](hardware-baseline.md).

Homing finds a machine reference using switches. Paper zero defines where the drawing starts. **Unlock alarm** explicitly sends `$X`; unlocking does not establish a machine reference or verify the reason for the alarm.

## Metric/imperial units and presets

The header's **Units** selector changes between **Inches** and **Millimeters**. Existing numeric inputs are converted, including paper size/margins, usable travel, drawing feed, jog distance/feed, live positions, and controller setup fields. Setup shows steps per inch in imperial mode; for example, 250 steps/mm becomes 6350 steps/in. Applying that unchanged value performs no EEPROM write. Setup dialogs retain the unit labels they had when opened, even if the main window's units change.

Internally, geometry and the controller API use millimeters. Jog and reference commands explicitly use G21; only their displayed/input values are converted. The unit selector does not write `$13`, change steps/mm, or move the machine. Raw GRBL reports/logs retain the controller's original values. Export emits G20 with inch coordinates/feeds or G21 with metric coordinates/feeds. Raw Z pen commands on Machine are always entered in millimeters and converted for inch export; M3 S values, M5, seconds, and non-distance settings are never rescaled.

The bundled preset in `scrib3/presets/john-servo.json` contains John's observed pen-up `M3 S180` and pen-down `M3 S70` positions and defaults to inches. The full-up trial `M3 S240` is not used. Drawing feed defaults to **59.06 in/min**; usable travel remains blank until measured/configured. The firmware profile continues to validate each pen action against live spindle settings and override. The DRV8825 **0.60 A** current target is a physical adjustment, not a preset or GRBL setting.

**Machine → Save preset** stores the current paper, travel, feed, jog, pen, firmware-profile, and unit preferences as the single active local preset. It reloads on the next launch, including after repository updates. **Restore John's** reloads the bundled values into the form; choose Save preset to retain them for later launches. Saved values are stored in:

- macOS: `~/Library/Application Support/SCRIB3/machine-preset.json`
- Windows: `%APPDATA%/SCRIB3/machine-preset.json`
- Linux: `$XDG_CONFIG_HOME/SCRIB3/machine-preset.json`, defaulting to `~/.config/SCRIB3/machine-preset.json`

Saving uses an atomic file replacement. Invalid saved files produce a message and fall back to the bundled preset; they are preserved until an explicit successful save. The file contains no connection or position state, and loading it sends no serial commands. Saved pen commands do not alter the firmware's startup/reset M5 position.

## Setting manual home

1. Jog to the point you want to use as the manual home reference, with GRBL Idle.
2. Click **Set home**. SCRIB3 records the current machine XY position for this connection, selects G54, clears temporary G92 offsets, and sets G54 XY zero using `G10 L20 P1 X0 Y0`. It moves no axes and needs no switches or `$22` change. As with Paper XY zero, clearing G92 also clears a temporary G92 Z offset.
3. **Go home** first issues the configured Pen up command, waits the configured settle time or 0.5 seconds, whichever is longer, then uses an absolute machine-coordinate jog to the recorded point at the current jog feed. It follows a direct XY line; ensure that path is clear. The saved reference remains the same if you later change Paper XY zero.

**Cancel jog** works during the return, and cancellation during pen lifting prevents the subsequent XY move. Invalid pen commands or controller errors prevent the return. The reference is cleared by disconnect/reset, an alarm, switch homing, or changes to direction/steps-per-distance/travel/homing settings. It is never restored from a preset. Re-establish it if the machine loses steps or is moved by hand; software cannot detect that displacement.

Manual home is a work reference. It does not establish physical machine limits, clear alarms, enable soft limits, or make an uncalibrated machine position reliable after power loss. **Switch home** performs the firmware's `$H` cycle instead and is disabled when `$22=0`.

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

The readiness line on the Control tab shows when the automatic motion baseline is being verified, and explains why normal controls may be waiting, with
distinct messages for connection, stale status, reset/setup, active jobs, and
idle with or without a paper origin. A controller in Idle is not by itself a
verified drawing setup: review paper placement and the job preview before a
run. The line interprets the existing snapshot only; it changes no command,
firmware, serial polling, motion settings, or button gates.
