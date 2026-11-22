# Run a sketch

The **Run sketch** button executes the reviewed workspace drawing through the connected GRBL controller. It supports drawings imported from SVG, DXF, or SCRIB3 drawing JSON, built-in patterns, and accepted Ollama drawing proposals. On an existing installation, first choose **Design → Paper guide → Use John's Letter setup** for the sideways Letter sheet: 11 inches along Y, 8.5 inches along X, top-left home. This saves the mapping without changing motor direction settings.

1. Complete [travel calibration](calibration.md). The bundled 5 steps/mm X/Y values are a starting correction from the reported measurement, not a verified calibration. Set the plotter's usable travel and drawing feed on **Machine**, and confirm pen up/down with the assembled mechanism.
2. Prepare a small drawing on **Design** and fit it to the paper. Raise the pen, jog to the paper corner selected in **Design → Paper guide** (top-left for John's **+Y right, −X down** mounting), and select **Control → Paper XY zero**. **Set home** also establishes paper zero. This must happen during the current connection.
3. Select **Review G-code**. **Pen-up test** is selected initially: the same XY paths execute with the configured pen-up command throughout. Uncheck it to draw with ink. Both modes use at least 0.5 seconds of pen settling. **Save .gcode** exports the exact program for the selected mode. If saving fails, an existing export is left intact.
4. Choose **Run sketch**. The progress window counts accepted commands and shows the last line whose motion has been confirmed complete. Accepted commands may still be queued in GRBL. **Pause** sends GRBL feed hold and leaves the pen at its current height; **Resume** continues the same job. A paused pen can leave an ink mark.
5. **Stop / reset** aborts the job and resets the controller. The supplied firmware can lower the servo on reset. Reconnect, inspect the position, and establish paper zero before another job. Closing the app or disconnecting during execution also aborts; closing the active progress window minimizes it so its controls remain available.

The run uses an immutable copy of the reviewed drawing and configuration. SCRIB3 rejects a stale review after drawing, layout, units, pen settings, controller settings, connection, or paper-origin changes. Running also requires the controller's X/Y steps/mm to match the saved calibration. Loading a preset alone sends no commands. By default, connecting applies and verifies the [350 in/min controller motion profile](smooth-motion-paper.md) before normal motion is enabled; calibration and motor current are not part of that setup.

For the DRV8825 / 0.60 A trial, use the [hardware acceptance procedure](hardware-baseline.md) before a full drawing. The current target requires a physical driver adjustment and has not been validated on the assembled plotter.

Each XY line waits for `ok` before the next line is sent, allowing GRBL to plan consecutive segments together. Pen changes and other commands wait for queued motion to finish. Completion requires the final pen-up command, dwell, and Idle status. An error, alarm, timeout, or unexpected restart stops the job without retrying commands. Pause time does not consume a command's execution timeout. See [smooth motion and paper setup](smooth-motion-paper.md) for the starting profile and paper orientation.

This runner executes generated workspace sketches; it does not import arbitrary G-code files. The Ollama assistant can propose drawings, but cannot start a job or operate the controller. Protocol and desktop behavior are tested with a simulated controller; real Mac, Arduino, and drawing-quality acceptance remain operator tests.

From the repository folder on Mac, launch and connect using:

```bash
bash Run-SCRIB3.command --connect auto --baud 115200
```
