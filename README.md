# SCRIB3

SCRIB3 is a desktop workbench for Arduino pen plotters on Windows and macOS. It combines SVG import, local Ollama line-art generation, toolpath preview, GRBL G-code export, direct plotter setup and manual control, saved pen presets, and metric/imperial units.

## Run on Windows

With Python 3.12 installed, open PowerShell in the cloned repository and run the following commands.

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scrib3
~~~

To reopen SCRIB3, run the last command from the repository folder.

## Run on Mac

Install Python 3.12 or newer using the macOS installer from python.org. The installer includes Tk and supports Apple Silicon and Intel Macs. Complete Python's **Install Certificates.command** step in its Applications folder. [Python macOS installation guide](https://docs.python.org/3/using/mac.html)

If you already use Homebrew, install its matching Tk package. For Python 3.13, run **brew install python-tk@3.13**. [Homebrew Tk package](https://formulae.brew.sh/formula/python-tk@3.13)

Clone or download this repository, then double-click **Run-SCRIB3.command** in Finder. You can also run it from Terminal after changing to the repository folder.

~~~bash
bash Run-SCRIB3.command
~~~

The launcher finds Python with Tk, creates a local **.venv-macos** environment, installs the pinned dependencies, checks the desktop startup, and opens SCRIB3. Reuse the same launcher to open the app later. If setup is interrupted, run it again.

To check the installation and available serial ports, run the following command.

~~~bash
bash Run-SCRIB3.command --check
~~~

Use **Find ports** in SCRIB3 to select the Arduino's Mac device path, commonly **/dev/cu.usbmodem…** or **/dev/cu.usbserial…**. A report showing no serial ports still allows drawing and G-code export. Connect the Arduino with a USB data cable when you are ready to inspect the controller.

For AI generation, install and open Ollama on the Mac, then enter a model shown by **ollama list** in SCRIB3. The current Ollama app requires macOS 14 or newer and provides GPU acceleration on Apple Silicon. [Ollama macOS requirements](https://docs.ollama.com/macos)

If you have several Python installations, set **SCRIB3_PYTHON** to the executable you want the launcher to use when creating its environment.

## Units and saved pen preset

Choose **Inches** (imperial) or **Millimeters** (metric) with the **Units** selector in the header. It converts paper dimensions, travel, feeds, jog steps, live positions, and setup fields while preserving their physical values. Export uses **G20** for inches and **G21** for millimeters. Servo S values stay unchanged.

The bundled **John's servo plotter** preset opens in inches with **Pen up = M3 S180** and **Pen down = M3 S70**, matching the positions tested on John's plotter. On **Machine**, choose **Save preset** to remember your current values and unit choice across launches. **Restore John's** reloads the bundled preset. Usable travel and drawing feed remain unset until configured; the reported 250 steps/mm and 200 mm travel have not been physically calibrated.

## Make a drawing

1. Load the built-in sample, import an SVG, or use **Generate with Ollama**. For Ollama, open the local Ollama app, run **ollama list** in Terminal or PowerShell, and enter an installed local model tag in SCRIB3.
2. Set the paper size and margin, then select **Fit to paper**. The drawing scales proportionally to the paper using the bounds of its artwork. Use **Show pen-up travel** to see the moves between strokes.
3. For the supplied servo firmware, select **Machine → Firmware profile → Uploaded RC-servo**, then connect on **Control** to capture its settings. See the [firmware setup notes](docs/firmware.md). On the **Machine** tab, enter the plotter's usable X/Y travel, drawing feed, and verified pen-up and pen-down commands. Enter a settle time if the actuator needs time before the next move.
4. Select **Review G-code** and **Save .gcode**. The job uses absolute coordinates in the selected units and G54, with positive X to the right and positive Y toward the top of the page. Use **Control → Paper XY zero** at the paper's lower-left corner before plotting.

SVG import plots outlines. Convert live text to paths, trace raster images to vectors, and flatten clipping and masks to paths before importing. Pen commands currently support Z-axis **G0 Z** or **G1 Z … F…**, and spindle-PWM **M3 S** or **M5** on firmware that maps those commands to the lift. The prototype requires those values from the actual plotter before it exports a job.

## Check the Arduino connection

Close any serial monitor or sender using the same port. On **Control**, select **Auto detect** to find a GRBL controller and its baud rate, or choose a port and rate manually. The connection stays open for **Setup**, manual home, switch homing, XY jogging, paper-zero setting, and pen controls. Live state, positions, and active inputs appear above the jog buttons.

On Mac, launch and automatically find the supplied firmware at 115200 baud from the repository folder:

~~~bash
bash Run-SCRIB3.command --connect auto --baud 115200
~~~

Omit the baud option to scan all supported rates. `--baud` sets the computer's rate; the supplied GRBL firmware's rate is fixed at compile time. See the [connection and plotter-control guide](docs/plotter-control.md) for terminal commands, calibration, limits, cancellation, and reset behavior.

Opening a port can reset the Arduino and move the servo. Physical homing and pen motion still need to be checked on the assembled machine. Run exported drawing jobs through your existing sender until in-app job streaming is added.

## Manual home without switches

Jog to the desired starting location and click **Control → Set home**. It marks that location for this connection and sets G54 XY zero without moving the axes. **Go home** lifts the pen with the configured command, waits at least half a second, and returns in a straight line at the jog feed. **Cancel jog** cancels the return. You can set a separate drawing origin with **Paper XY zero** afterward.

**Switch home** is the separate GRBL homing cycle and requires configured switches and `$22=1`. A manual reference does not establish a switch-based machine reference or enable soft limits. Set manual home again after reconnecting, resetting, an alarm, switch homing, or changes to the axis calibration. Firmware startup/reset still moves the servo to its original **M5** position; saving a preset does not change the firmware.

## Build sequence

| Milestone | Deliverable |
| --- | --- |
| Drawing workbench | SVG or Ollama prompt to paper preview, then reviewable G-code export with an explicit plotter configuration. |
| Plotter bring-up | Port/baud discovery, persistent connection, editable controller settings, manual and switch home, live positions, XY jog, work origin, and saved pen presets with metric/imperial units. Physical calibration and first plot remain to be verified. |
| In-app plotting | Next: full GRBL job streaming with acknowledgement, pause/resume, and confirmed completion. |
| Drawing tools | Add raster tracing, direct drawing edits, multiple machine-profile management, and prompt-based revisions. |

## Developer checks

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

On macOS, run the checks with the environment created by the launcher.

~~~bash
.venv-macos/bin/python -m unittest discover -s tests -v
~~~

- [GRBL serial interface](https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
