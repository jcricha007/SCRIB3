# Run a sketch

The **Run sketch** button executes the reviewed workspace drawing through the connected GRBL controller. It supports drawings imported from SVG, DXF, or SCRIB3 drawing JSON, built-in patterns, and accepted Ollama drawing proposals. On an existing installation, first choose **Design → Paper guide → Use John's Letter setup** for the sideways Letter sheet: 11 inches along Y, 8.5 inches along X, top-left home. This saves the mapping without changing motor direction settings.

1. Complete [travel calibration](calibration.md). The bundled 5 steps/mm X/Y values are a starting correction from the reported measurement, not a verified calibration. SCRIB3 reads maximum travel from the connected controller and checks the whole sheet in its selected orientation. Set the drawing feed on **Machine** and confirm pen up/down with the assembled mechanism.
2. Prepare a small drawing on **Design** and fit it to the paper. Raise the pen, jog to the paper corner selected in **Design → Paper guide** (top-left for John's **+Y right, −X down** mounting), and select **Control → Paper XY zero**. **Set home** also establishes paper zero. This must happen during the current connection.
3. Select **Review G-code**. **Pen-up test** is selected initially: the same XY paths execute with the configured pen-up command throughout. Uncheck it to draw with ink. Both modes pause for **Pen settle** after each lift or lower command, with a minimum of 0.5 seconds. **Save .gcode** exports the exact program for the selected mode. If saving fails, an existing export is left intact.
4. Choose **Run sketch**. The pen rises, travels from its current position to the first drawing point, and waits there for ten seconds with the pen raised before the first stroke. This hold also appears in exported G-code and pen-up tests. The progress window counts accepted commands and shows the last line whose motion has been confirmed complete. Accepted commands may still be queued in GRBL. **Pause** sends GRBL feed hold and leaves the pen at its current height; **Resume** continues the same job. A paused pen can leave an ink mark.
5. **Stop print** stops sending drawing commands. GRBL finishes moves already submitted, then SCRIB3 raises the pen and waits for Idle. Stopping a paused print releases its hold so those queued moves can finish. The connection, manual home, paper zero, and settings remain available. **Control → Reset / abort** is the immediate abort. A reset can lower the servo and requires reconnecting and establishing position again. Closing the active progress window minimizes it.

The run uses an immutable copy of the reviewed drawing and configuration. SCRIB3 rejects a stale review after drawing, layout, units, pen settings, controller settings, connection, or paper-origin changes. Running also requires the controller's X/Y steps/mm to match the saved calibration. Loading a preset alone sends no commands. By default, connecting applies and verifies the [59.06 in/min controller motion profile](smooth-motion-paper.md) before normal motion is enabled; calibration and motor current are not part of that setup.

For the DRV8825 / 0.60 A trial, use the [hardware acceptance procedure](hardware-baseline.md) before a full drawing. The current target requires a physical driver adjustment and has not been validated on the assembled plotter.

Each XY line waits for `ok` before the next line is sent, allowing GRBL to plan consecutive segments together. Pen changes and other commands wait for queued motion to finish. After the last stroke, SCRIB3 finishes the pen lift and settle at that XY point, waits for Idle, and leaves the Arduino connected for the next manual action. The preflight rejects any trailing move, home, or pen command. An error, alarm, timeout, or unexpected restart stops the job without retrying commands. Pause time does not consume a command's execution timeout. See [smooth motion and paper setup](smooth-motion-paper.md) for the starting profile and paper orientation.

This runner executes generated workspace sketches; it does not import arbitrary G-code files. The Ollama assistant can propose drawings, but cannot start a job or operate the controller. Protocol and desktop behavior are tested with a simulated controller; real Mac, Arduino, and drawing-quality acceptance remain operator tests.

From the repository folder on Mac, launch and connect using:

```bash
bash Run-SCRIB3.command --connect auto --baud 115200
```
