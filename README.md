# SCRIB3

SCRIB3 is a desktop workbench for Arduino pen plotters on Windows and macOS. It combines vector design tools, local Ollama chat and drawing proposals, toolpath preview, SVG/G-code export, guided travel calibration, direct plotter control, saved presets, and metric/imperial units.

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

For AI generation, open your installed Ollama app, then choose **Design → Open Ollama assistant**. **Refresh models** finds installed local models; select one for chat and drawing generation. **Save choice** remembers the model together with the current machine preset. [Assistant and design guide](docs/design-assistant.md)

If you have several Python installations, set **SCRIB3_PYTHON** to the executable you want the launcher to use when creating its environment.

## Units and saved pen preset

Choose **Inches** (imperial) or **Millimeters** (metric) with the **Units** selector in the header. It converts paper dimensions, travel, feeds, jog steps, live positions, and setup fields while preserving their physical values. Export uses **G20** for inches and **G21** for millimeters. Servo S values stay unchanged.

The bundled **John's servo plotter** preset opens in inches with **Pen up = M3 S180**, **Pen down = M3 S70**, and an X/Y starting calibration of **5.000 steps/mm** (**127 steps/in**). The travel correction comes from the reported 0.1-inch command producing 5 inches of movement with the original 250 steps/mm settings; verify it with the calibration guide before plotting. Drawing feed starts at 8,890 mm/min (350 in/min); usable travel remains unset until measured/configured.

On **Machine**, choose **Save preset** to remember current values and units. **Restore John's** reloads the bundled preset. On this upgrade, older saved presets adopt a 350 in/min drawing feed and automatic motion setup while retaining pen commands, dimensions, calibration, and units. Later saved feed adjustments are preserved. Loading a preset alone does not connect to the Arduino. In **Control → Setup → Motion**, **Use preset X/Y calibration** fills the setup fields; **Apply changed settings** writes them. A steps/mm change requires reset and reconnect before motion is enabled again.

For guided setup, use **Control → Setup → Motion → Guided calibration…**. The guide reads the current settings, applies the saved starting calibration on request, raises the pen for a small test move, and calculates an axis correction from your ruler/caliper measurement. It waits for Idle, accounts for step rounding, checks readback, and saves successful corrections. [Calibration instructions](docs/calibration.md)

**Drawing and rapid travel default to 350 in/min (8,890 mm/min).** On connection, SCRIB3 automatically waits for Idle, applies changed X/Y maximum rates (8,890 mm/min), acceleration (25 mm/s²), and junction deviation (0.020 mm), then verifies readback before enabling normal motion. Manual jog remains 150 mm/min. No Smooth motion / Apply step is required. **Machine → Smooth motion** remains available for restoring the baseline or disabling automatic setup when retaining custom controller tuning across connections. The runner now feeds consecutive XY segments to GRBL's planner without stopping at each vertex. [Motion and paper setup](docs/smooth-motion-paper.md)

John's installed **DRV8825** drivers have a provisional **0.60 A** current-limit target. On a module with confirmed **R100** sense resistors, that corresponds to **0.300 V Vref**, set and measured physically on each driver. SCRIB3 cannot apply this current setting. Follow the [hardware baseline and acceptance test](docs/hardware-baseline.md) for the current adjustment, pen-up test, seam comparison, and temperature checks.

Fresh presets use **US Letter landscape (11 inches across, 8.5 inches down)**, a 0.5-inch margin, and **top-left home with +Y right and −X down**. For an existing installation, choose **Design → Paper guide → Use John's Letter setup** to apply and save that mapping. The guide also offers Letter/A4 layouts and the original bottom-left mapping. Jog buttons follow the selected mounting. Changing the mounting invalidates paper zero and old reviews. Paper selection never changes machine travel: verify usable X travel down the page and Y travel across it.

## Make a drawing

1. Load the sample, import SVG, DXF, or drawing JSON, create a Grid/Spiral/Rosette on **Design**, or open the Ollama assistant. In **Create / revise**, request new line art or revise the workspace drawing; inspect the proposal and choose **Use drawing in workspace**. Chat can help develop the brief. AI responses cannot operate the controller.
2. Set paper size and margin, then select **Fit to paper**. The drawing scales proportionally using its artwork bounds. Rotate or mirror it, use **Undo design** to restore the previous source, and **Export drawing** to save the fitted geometry. **Show pen-up travel** reveals moves between strokes.
3. For the supplied servo firmware, select **Machine → Firmware profile → Uploaded RC-servo**, then connect on **Control** to capture its settings. See the [firmware setup notes](docs/firmware.md). On the **Machine** tab, enter the plotter's usable X/Y travel, drawing feed, and verified pen-up and pen-down commands. Enter a settle time if the actuator needs time before the next move.
4. Use **Control → Set home** (or **Paper XY zero**) at the paper corner selected in Paper guide—top-left for John's setup, then select **Review G-code**. The review starts with **Pen-up test** selected; leave it selected for the first trial, or uncheck it to draw with ink. Choose **Run sketch** to execute in SCRIB3, or **Save .gcode** to export the reviewed mode. The job uses absolute coordinates in the selected units and G54, with the selected paper mapping. John's setup plots into **−X and +Y** from top-left home. [Running sketches](docs/running-sketches.md)

**Plot quality** offers a short closed-loop overlap to help cover pen-contact gaps at circle seams. Choose **Use 0.5 mm → Apply and save**, then review again. Open paths retain their endpoints. See [vector formats, seam checks, and motor heat](docs/vector-formats.md) for supported DXF entities, examples, and the JSON format.

SVG import plots outlines. Convert live text to paths, trace raster images to vectors, and flatten clipping and masks to paths before importing. Pen commands currently support Z-axis **G0 Z** or **G1 Z … F…**, and spindle-PWM **M3 S** or **M5** on firmware that maps those commands to the lift. The prototype requires those values from the actual plotter before it exports a job.

## Check the Arduino connection

Close any serial monitor or sender using the same port. On **Control**, select **Auto detect** to find a GRBL controller and its baud rate, or choose a port and rate manually. The connection stays open for **Setup**, manual home, switch homing, XY jogging, paper-zero setting, and pen controls. Live state, positions, and active inputs appear above the jog buttons.

On Mac, launch and automatically find the supplied firmware at 115200 baud from the repository folder:

~~~bash
bash Run-SCRIB3.command --connect auto --baud 115200
~~~

Omit the baud option to scan all supported rates. `--baud` sets the computer's rate; the supplied GRBL firmware's rate is fixed at compile time. See the [connection and plotter-control guide](docs/plotter-control.md) for terminal commands, calibration, limits, cancellation, and reset behavior.

Opening a port can reset the Arduino and move the servo. Physical travel calibration and pen motion still need to be checked on the assembled machine. Establish paper zero during the current connection and begin with a small pen-up test before drawing with ink.

## Manual home without switches

Jog to the desired starting location and click **Control → Set home**. It marks that location for this connection and sets G54 XY zero without moving the axes. **Go home** lifts the pen with the configured command, waits at least half a second, and returns in a straight line at the jog feed. **Cancel jog** cancels the return. You can set a separate drawing origin with **Paper XY zero** afterward.

**Switch home** is the separate GRBL homing cycle and requires configured switches and `$22=1`. A manual reference does not establish a switch-based machine reference or enable soft limits. Set manual home again after reconnecting, resetting, an alarm, switch homing, or changes to the axis calibration. Firmware startup/reset still moves the servo to its original **M5** position; saving a preset does not change the firmware.

## Build sequence

| Milestone | Deliverable |
| --- | --- |
| Drawing workbench | SVG/DXF/drawing JSON import/export, seam overlap, pattern creation, rotate/mirror/undo, local Ollama chat, and reviewed drawing generation/revision before G-code export. |
| Plotter bring-up | Port/baud discovery, persistent connection, setup, guided measured calibration, manual/switch home, live positions, XY jog, work origin, and saved presets. Corrected travel and the first full plot still need physical verification. |
| In-app plotting | Reviewed workspace sketches, pen-up tests, continuous XY planner feeding, pen-transition/final Idle checks, accepted-versus-completed progress, pause/resume, and stop/reset. Physical motion quality still needs verification. |
| Next design tools | Raster tracing, point/stroke editing, and multiple machine-profile management. |

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
