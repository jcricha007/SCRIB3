# Run a sketch

The **Run sketch** button executes the reviewed workspace drawing through the connected GRBL controller. It supports drawings imported from SVG, built-in patterns, and accepted Ollama drawing proposals.

1. Complete [travel calibration](calibration.md). The bundled 5 steps/mm X/Y values are a starting correction from the reported measurement, not a verified calibration. Set the plotter's usable travel and drawing feed on **Machine**, and confirm pen up/down with the assembled mechanism.
2. Prepare a small drawing on **Design** and fit it to the paper. Raise the pen, jog to the paper's lower-left corner, and select **Control → Paper XY zero**. **Set home** also establishes paper zero. This must happen during the current connection.
3. Select **Review G-code**. **Pen-up test** is selected initially: the same XY paths execute with the configured pen-up command throughout. Uncheck it to draw with ink. Both modes use at least 0.5 seconds of pen settling. **Save .gcode** exports whichever mode is selected.
4. Choose **Run sketch**. The progress window counts completed commands. **Pause** sends GRBL feed hold and leaves the pen at its current height; **Resume** continues the same job. A paused pen can leave an ink mark.
5. **Stop / reset** aborts the job and resets the controller. The supplied firmware can lower the servo on reset. Reconnect, inspect the position, and establish paper zero before another job. Closing the app or disconnecting during execution also aborts; closing the active progress window minimizes it so its controls remain available.

The run uses an immutable copy of the reviewed drawing and configuration. SCRIB3 rejects a stale review after drawing, layout, units, pen settings, controller settings, connection, or paper-origin changes. Running also requires the controller's X/Y steps/mm to match the saved calibration. Loading a preset or connecting does not write settings to the Arduino.

Each line waits for `ok` and a subsequent Idle status before the next line is sent. Completion requires the final pen-up command and dwell to finish. This conservative sender can be slower and less smooth than buffered senders on dense curves. An error, alarm, timeout, or unexpected restart stops the job without retrying commands. Pause time does not consume a command's execution timeout.

This runner executes generated workspace sketches; it does not import arbitrary G-code files. The Ollama assistant can propose drawings, but cannot start a job or operate the controller. Protocol and desktop behavior are tested with a simulated controller; real Mac, Arduino, and drawing-quality acceptance remain operator tests.

From the repository folder on Mac, launch and connect using:

```bash
bash Run-SCRIB3.command --connect auto --baud 115200
```
