# SCRIB3

SCRIB3 is a desktop workbench for Arduino pen plotters on Windows and macOS. It combines SVG import, local Ollama line-art generation, toolpath preview, and GRBL G-code export.

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

## Make a drawing

1. Load the built-in sample, import an SVG, or use **Generate with Ollama**. For Ollama, open the local Ollama app, run **ollama list** in Terminal or PowerShell, and enter an installed local model tag in SCRIB3.
2. Set the paper size and margin, then select **Fit to paper**. The drawing scales proportionally to the paper using the bounds of its artwork. Use **Show pen-up travel** to see the moves between strokes.
3. For the supplied servo firmware, select **Machine → Firmware profile → Uploaded RC-servo**, then **Read GRBL** to capture its settings. See the [firmware setup notes](docs/firmware.md). On the **Machine** tab, enter the plotter's usable X/Y travel, drawing feed, and verified pen-up and pen-down commands. Enter a settle time if the actuator needs time before the next move.
4. Select **Review G-code** and **Save .gcode**. The job uses absolute millimeter coordinates in G54, with positive X to the right and positive Y toward the top of the page. Set the work origin at the paper's lower-left corner in your existing sender and account for any active G92 offset.

SVG import plots outlines. Convert live text to paths, trace raster images to vectors, and flatten clipping and masks to paths before importing. Pen commands currently support Z-axis **G0 Z** or **G1 Z … F…**, and spindle-PWM **M3 S** or **M5** on firmware that maps those commands to the lift. The prototype requires those values from the actual plotter before it exports a job.

## Check the Arduino connection

Close any serial monitor or sender using the same port. With the plotter idle, open the **Machine** tab, select **Find ports**, choose the port, and click **Read GRBL**. The report captures the GRBL banner when available, status and override snapshots, build info, controller settings, parser modes, and coordinate offsets. Opening the port can reset some Arduino boards and move the servo. Run exported files through your existing sender in this version.

## Build sequence

| Milestone | Deliverable |
| --- | --- |
| Drawing workbench | SVG or Ollama prompt to paper preview, then reviewable G-code export with an explicit plotter configuration. |
| Plotter bring-up | Read the installed controller settings, calibrate the lift and axes, then establish a first small plot from SCRIB3 output. |
| In-app plotting | Add jogging, work-origin setup, and GRBL job streaming with controller acknowledgement, pause/resume, and confirmed completion. |
| Drawing tools | Add raster tracing, direct drawing edits, saved machine profiles, and prompt-based revisions. |

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
