from math import isclose
import pytest

from scrib3.demo import sample_board
from scrib3.gcode import Machine
from scrib3.jobs import PlotJob
from scrib3.paper_mount import required_travel
from scrib3.plot_timeline import PlotTimeline
from scrib3.toolpath import prepare_toolpath


@pytest.mark.parametrize("units,mount", [("in", "top_left_y"), ("mm", "bottom_left_x")])
@pytest.mark.parametrize("dry", [True, False])
def test_airframe_replays_the_export_and_confirmed_line_numbers(units, mount, dry):
    board = sample_board()
    paths, sheet = board.plot_layer(board.pens()[0])
    start = (0, sheet.height) if mount == "top_left_y" else (0, 0)
    paths, _ = prepare_toolpath(paths, start=start)
    machine = Machine(*required_travel(sheet.width, sheet.height, mount), 1500,
                      "M3 S180", "M3 S70", .5, paper_mount=mount, seam_overlap=.5)
    job = PlotJob(paths, sheet, machine, units, dry, (), 0)
    review = job.review()
    plan = PlotTimeline(job, review)
    assert tuple(e.command for e in plan.events) == job.commands()
    assert plan.strokes == len(paths) == 117 and plan.hold_seconds == 127.5
    hold, = [e for e in plan.events if e.kind == "Start hold"]
    i = plan.events.index(hold)
    assert hold.end - plan.events[i-1].end == pytest.approx(10)
    assert not hold.down and hold.xy == plan.events[i-1].xy
    count, fraction = plan.at_time(hold.end - 5)
    assert count == i and isclose(fraction, .5)
    moves = [e for e in plan.events if e.kind in ("Dry stroke", "Draw")]
    assert len(moves) == review.preflight.plotted_segments
    assert all(e.down != dry for e in moves)
    assert plan.events[-1].xy == moves[-1].xy and not plan.events[-1].down
    assert plan.at_time(plan.seconds) == (len(plan.events), 0)
