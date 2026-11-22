"""Operator-facing interpretation of the existing controller snapshot.

The result is explanatory only. It is not a motion or job interlock.
"""

_STATE_HINTS = {
    "Alarm": "Inspect the plotter and connection log before clearing the alarm.",
    "Hold": "The controller is holding motion. It is not waiting for a new move.",
    "Door": "The controller reports a safety-door state. Inspect the hardware.",
    "Home": "Switch homing is in progress. Wait for a fresh Idle report.",
    "Run": "Controller motion is in progress. Wait for a fresh Idle report.",
    "Jog": "A jog is in progress. Wait for a fresh Idle report.",
    "Check": "GRBL is in check mode; this is not normal motion mode.",
    "Sleep": "GRBL is asleep. Start a new verified session before continuing.",
}


def machine_readiness(snapshot, *, active=False, scanning=False, closing=False):
    """Return a short state label and next-step description without doing I/O."""
    if closing:
        return "Closing", "Wait for the connection to close."
    if scanning:
        return "Scanning", "Looking for a GRBL controller. No active session is ready."
    if snapshot.get("fault"):
        return "Connection fault", "Inspect the connection log. Re-establish position in a fresh session."
    if not active:
        return "Disconnected", "Select a port and connect before using machine controls."
    if not snapshot.get("connected"):
        return "Connecting", "Waiting for GRBL connection and controller settings."
    if snapshot.get("reset_required"):
        return "Reset required", "Calibration changed. Follow the reset and reconnect prompt before moving."
    if not snapshot.get("fresh"):
        return "Waiting for status", "Live status is stale. Do not treat the previous position or state as current."

    state = snapshot.get("state", "")
    base = state.split(":", 1)[0]
    if base in {"Alarm", "Door", "Check", "Sleep"}:
        return state, _STATE_HINTS[base]
    job = snapshot.get("job", {}).get("state")
    if job == "paused":
        return "Job paused", "The current job still owns the controller. Do not start a second job."
    if job == "running":
        return "Job in progress", "The current job still owns the controller, even between moves."
    if base in _STATE_HINTS:
        return state, _STATE_HINTS[base]
    if base != "Idle":
        return state or "Unknown state", "Wait for a recognized controller status."
    if snapshot.get("busy", True):
        return "Command in progress", "Wait for the current request to finish."
    if snapshot.get("motion_defaults_pending"):
        return "Motion setup pending", "Review the controller motion setup before using normal motion controls."
    if not snapshot.get("origin_set"):
        return "Idle · paper origin not set", "Establish the paper origin and review the drawing before running it."
    return "Idle · paper origin set", "Review paper placement and the job preview before starting a drawing."
