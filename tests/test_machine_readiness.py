import pytest

from scrib3.machine_readiness import machine_readiness


IDLE = {"connected": True, "fresh": True, "busy": False, "state": "Idle"}


@pytest.mark.parametrize(("snapshot", "options", "headline", "guidance"), [
    ({}, {}, "Disconnected", "Select a port"),
    ({}, {"scanning": True}, "Scanning", "No active session"),
    ({}, {"active": True}, "Connecting", "Waiting for GRBL"),
    ({**IDLE, "fault": "lost"}, {}, "Connection fault", "fresh session"),
    ({**IDLE, "reset_required": True}, {"active": True}, "Reset required", "Calibration changed"),
    ({**IDLE, "fresh": False, "motion_defaults_pending": True}, {"active": True},
     "Waiting for status", "status is stale"),
    ({**IDLE, "state": "Alarm", "motion_defaults_pending": True}, {"active": True},
     "Alarm", "before clearing"),
    ({**IDLE, "state": "Door:2", "job": {"state": "running"}}, {"active": True},
     "Door:2", "safety-door"),
    ({**IDLE, "state": "Hold:0", "job": {"state": "paused"}}, {"active": True},
     "Job paused", "still owns"),
    ({**IDLE, "job": {"state": "running"}}, {"active": True},
     "Job in progress", "between moves"),
    ({**IDLE, "state": "Jog"}, {"active": True}, "Jog", "jog is in progress"),
    ({**IDLE, "busy": True}, {"active": True},
     "Command in progress", "current request"),
    ({**IDLE, "motion_defaults_pending": True, "origin_set": True}, {"active": True},
     "Motion setup pending", "Review"),
    ({**IDLE, "origin_set": False}, {"active": True},
     "Idle · paper origin not set", "Establish"),
    ({**IDLE, "origin_set": True}, {"active": True}, "Idle · paper origin set", "Review paper"),
    ({**IDLE, "state": "FutureMode"}, {"active": True}, "FutureMode", "recognized"),
    (IDLE, {"active": True, "scanning": True, "closing": True},
     "Closing", "Wait for the connection"),
])
def test_snapshot_states_are_explanatory(snapshot, options, headline, guidance):
    before = dict(snapshot)
    title, hint = machine_readiness(snapshot, **options)
    assert title == headline
    assert guidance in hint
    assert snapshot == before
