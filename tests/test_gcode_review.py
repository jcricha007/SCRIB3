from dataclasses import replace

import pytest

from scrib3.drawing import Sheet
from scrib3.gcode import Machine, generate_gcode, review_gcode
from scrib3.jobs import PlotJob


SHEET = Sheet(10, 10, 0)
MACHINE = Machine(10, 10, 60, "M3 S180", "M3 S70")
DRAWING = (
    ((1, 2), (1.00005, 2)),  # Drops on both grids.
    ((3, 4), (3.0003, 4), (4, 4)),  # Drops one point on the mm grid; not inch.
    ((5, 6), (6, 6)),
)


@pytest.mark.parametrize("unit,step,duplicates", [
    ("mm", 0.001, 2), ("in", 0.00001, 1),
])
def test_review_explains_exact_emitted_geometry(unit, step, duplicates):
    job = PlotJob(DRAWING, SHEET, MACHINE, unit, False, (), 0)
    review = job.review()
    assert review.coordinate_step == step
    assert review.strokes_omitted == 1 and review.strokes_in == 3
    assert review.rounded_xy_duplicates == duplicates
    assert "Warning: 1 stroke(s)" in review.summary()
    assert review.program == job.program() == generate_gcode(DRAWING, SHEET, MACHINE, unit)
    assert "Warning" not in review.program and "Output coordinates" not in review.program
    assert review.program.count("G0 X") == 2
    assert review.program.count("M3 S70.000") == 2


def test_pen_up_review_does_not_change_xy_summary():
    job = PlotJob(DRAWING, SHEET, MACHINE, "mm", False, (), 0)
    actual = job.review()
    dry = replace(job, dry_run=True).review()
    assert actual.summary() == dry.summary()
    assert "M3 S70.000" not in dry.program
    assert [line for line in dry.program.splitlines() if line.startswith(("G0 X", "G1 X"))] == [
        line for line in actual.program.splitlines() if line.startswith(("G0 X", "G1 X"))
    ]


def test_entirely_unplottable_drawings_still_fail():
    with pytest.raises(ValueError, match="No stroke is long enough"):
        review_gcode(DRAWING[:1], SHEET, MACHINE)


def test_a_retained_closed_loop_does_not_trigger_a_warning():
    square = (((1, 1), (2, 1), (2, 2), (1, 2), (1, 1)),)
    review = review_gcode(square, SHEET, replace(MACHINE, seam_overlap=.5))
    assert review.strokes_omitted == review.rounded_xy_duplicates == 0
    assert "Warning" not in review.summary()
    assert "G1 X1.500 Y1.000" in review.program
