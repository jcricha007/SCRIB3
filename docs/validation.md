# Cloud validation — 23 November 2026

Base: `7a60edab778ae73ef9328ac1d76df7855ac18e27` from SCRIB3 main.
Branch: `scrib3/printer-studio`.

## Results

The complete suite ran with Python 3.12, a real Tk desktop on Linux/Xvfb, and simulated GRBL serial peers:

```text
SCRIB3_DESKTOP_TESTS=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests -q
229 passed, 3 skipped, 65 subtests passed in 132.02s
```

The skipped checks are optional external integrations. This result does not assert Windows/macOS desktop acceptance or physical printer operation.

Coverage includes drawing and undo/redo through native UI events; board save/open; paper-size registration in the normal GRBL review entry point; shortcuts following the active workspace; compact layout; imported SVG color, physical dimensions, nested clipping, opacity and fill holes; all twelve fonts; photo generation; hidden-line removal on a mesh; finite holder calibration and nozzle/tip bounds; G-code pen state and pauses; plate metadata/checksum; and controlled GRBL stopping while running and paused.

A separate desktop check selected, rotated and fitted 1,000 paths and exported the result as an H2S pen-up sliced plate. No hardware connection was made. `python -m compileall -q scrib3 scripts` and `git diff --check` also passed. `docs/images/drawing-studio.png` is a capture of the running native application with the included example board.

## Windows handoff

1. Reconnect Windows and preserve the local `scrib3/plotter-board` branch at `73f22dc`, presets and saved boards. Reconcile it with this branch before replacing an existing checkout.
2. Run the Windows launcher dependency check and regression tests. The `.cmd`/PowerShell launcher has not been executed on Windows in this cloud session.
3. Confirm the current plotter's pen-up position, home retention after Stop, first-point pause and 1,500 mm/min motion. A normal stop drains buffered moves; reset/disconnect retains the firmware's existing startup behavior.
4. Open a pen-up `.gcode.3mf` in Bambu Studio for P1S and H2S. Verify the correct model, scale and pauses. Enter measured holder offsets and heights; no measured calibration is supplied by this build.
5. Perform a small pen-up motion check on each physical machine before an ink run. There is no direct network printer upload in this build.

The full 3dplotter tool catalog and cloud functionality remain incomplete. See [the studio guide](drawing-studio.md) for the implemented workflows and remaining gaps.
