# SCRIB3

SCRIB3 is a Windows-first desktop workbench for Arduino pen plotters. It combines SVG import, local Ollama line-art generation, toolpath preview, and GRBL G-code export.

## Run on Windows

With Python 3.12 installed, open PowerShell in the cloned repository and run the following commands.

~~~powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m scrib3
~~~

To reopen SCRIB3, run the last command from the repository folder.

## Make a drawing

1. Load the built-in sample, import an SVG, or use **Generate with Ollama**. For Ollama, open the local Ollama app, run **ollama list** in PowerShell, and enter an installed local model tag in SCRIB3.
2. Set the paper size and margin, then select **Fit to paper**. The drawing scales proportionally to the paper using the bounds of its artwork. Use **Show pen-up travel** to see the moves between strokes.
3. On the **Machine** tab, enter the plotter's usable X/Y travel, drawing feed, and verified pen-up and pen-down commands. Enter a settle time if the actuator needs time before the next move.
4. Select **Review G-code** and **Save .gcode**. The job uses absolute millimeter coordinates in G54, with positive X to the right and positive Y toward the top of the page. Set the work origin at the paper's lower-left corner in your existing sender and account for any active G92 offset.

SVG import plots outlines. Convert live text to paths, trace raster images to vectors, and flatten clipping and masks to paths before importing. Pen commands currently support Z-axis **G0 Z** or **G1 Z … F…**, and spindle-PWM **M3 S** or **M5** on firmware that maps those commands to the lift. The prototype requires those values from the actual plotter before it exports a job.

## Check the Arduino connection

Close any serial monitor or sender using the same port. With the plotter idle, open the **Machine** tab, select **Find ports**, choose the port, and click **Read GRBL**. The report captures the GRBL banner when available, a status snapshot, build info, and controller settings. Opening the port can reset some Arduino boards. Run exported files through your existing sender in this version.

## Build sequence

| Milestone | Deliverable |
| --- | --- |
| Drawing workbench | SVG or Ollama prompt to paper preview, then reviewable G-code export with an explicit plotter configuration. |
| Plotter bring-up | Identify the installed GRBL build and lift commands, then compare a known-good job against SCRIB3 output and verify a small dry run. |
| In-app plotting | Add jogging, work-origin setup, and GRBL job streaming with controller acknowledgement, pause/resume, and confirmed completion. |
| Drawing tools | Add raster tracing, direct drawing edits, saved machine profiles, and prompt-based revisions. |

## Developer checks

~~~powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
~~~

- [GRBL serial interface](https://github.com/gnea/grbl/blob/master/doc/markdown/interface.md)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
