from dataclasses import replace

import pytest

from scrib3.drawing import Sheet
from scrib3.gcode import Machine, review_gcode
from scrib3.gcode_preflight import verify_program

SHEET = Sheet(10, 10, 0)
ART = (((1, 2), (3, 4), (4, 4), (1, 2)), ((5, 6), (6, 6)))
PWM = Machine(10, 10, 60, "M3 S180", "M3 S70", settle=0.2)


@pytest.mark.parametrize("units", ["mm", "in"])
@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("mount", ["top_left_y", "bottom_left_x"])
@pytest.mark.parametrize("actuator", [("M3 S180", "M5"), ("G0 Z2", "G1 Z0.5 F100")])
def test_generated_program_roundtrips_offline(units, dry_run, mount, actuator):
    machine = replace(PWM, paper_mount=mount, up=actuator[0], down=actuator[1])
    result = review_gcode(ART, SHEET, machine, units, dry_run=dry_run)
    commands = result.program.splitlines()
    travel = next(i for i, line in enumerate(commands) if line.startswith("G0 X"))
    assert commands[travel + 1] == "G4 P10.000"
    assert commands.count("G4 P10.000") == 1
    assert result.preflight.pen_up_travels == 2
    assert result.preflight.plotted_segments == 4
    assert result.preflight.command_count == len(result.program.splitlines()) - 1
    assert "Offline preflight passed" in result.summary()


@pytest.mark.parametrize(("old", "new", "reason"), [
    ("G4 P10.000", "G4 P0.000", "10-second"),
    ("G90", "G91", "explicit job modes"),
    ("G0 X1.000", "G0 X-1.000", "outside the configured"),
    ("G1 X3.000 Y4.000 F60.000", "G1 X3.000 Y4.000", "explicit feed"),
    ("G1 X3.000", "G0 X3.000", "without a rapid"),
    ("G4 P0.200", "G4 P1.000", "settle dwell"),
    ("M3 S70.000", "M3 S95.000", "actuator"),
    ("G0 X1.000 Y2.000", "G2 X1.000 Y2.000", "explicit XY"),
])
def test_refuses_tampered_serialized_command(old, new, reason):
    text = review_gcode(ART, SHEET, PWM).program
    assert old in text
    with pytest.raises(ValueError, match=reason):
        verify_program(text.replace(old, new, 1), units="mm", machine=PWM, expected_strokes=2)


def test_refuses_missing_final_lift_and_wrong_stroke_count():
    text = review_gcode(ART, SHEET, PWM).program
    with pytest.raises(ValueError, match="unfinished program"):
        verify_program("\n".join(text.splitlines()[:-2]), units="mm",
                       machine=PWM, expected_strokes=2)
    with pytest.raises(ValueError, match="unexpected stroke count"):
        verify_program(text, units="mm", machine=PWM, expected_strokes=3)


def test_dry_run_refuses_pen_down_command():
    text = review_gcode(ART, SHEET, PWM, dry_run=True).program
    index = text.index("M3 S180.000", text.index("G0 X"))
    altered = text[:index] + text[index:].replace("M3 S180.000", "M3 S70.000", 1)
    with pytest.raises(ValueError, match="actuator"):
        verify_program(altered, units="mm", machine=PWM, expected_strokes=2, dry_run=True)


@pytest.mark.parametrize("tail", ["G0 X0.000 Y0.000", "$H", "G28", "M2", "M30", "M5", "M3 S70.000"])
def test_no_command_after_final_lift_and_settle(tail):
    program = review_gcode(ART, SHEET, PWM).program
    with pytest.raises(ValueError, match="after the final pen lift"):
        verify_program(program + tail + "\n", units="mm", machine=PWM, expected_strokes=2)
