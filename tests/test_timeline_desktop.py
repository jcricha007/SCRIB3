import os
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch, Mock

import pytest
from scrib3.app import Studio

pytestmark = pytest.mark.skipif(os.environ.get("SCRIB3_DESKTOP_TESTS") != "1", reason="Desktop display required")


@pytest.fixture
def studio(tmp_path):
    root = tk.Tk()
    app = Studio(root, tmp_path/"preset.json")
    try:
        yield app
    finally:
        for timer in root.tk.call("after","info"):
            root.after_cancel(timer)
        root.destroy()

def descend(widget):
    for child in widget.winfo_children():
        yield child
        yield from descend(child)


def button(widget, label):
    return next(w for w in descend(widget) if isinstance(w,(ttk.Button,ttk.Checkbutton)) and w.cget("text")==label)

def test_review_scrub_toggle_and_controller_confirmed_trace(studio):
    from scrib3.timeline_ui import TimelineWindow
    from scrib3.job_ui import JobWindow
    studio.show_board()
    root = studio.root
    root.update()
    with patch("scrib3.timeline_ui.TimelineWindow", wraps=TimelineWindow) as make, patch("tkinter.messagebox.showerror") as errors:
        studio.review(board_editor=studio.board_editor)
        errors.assert_not_called()
        dialog = next(w for w in descend(root) if isinstance(w,tk.Toplevel) and "G-code review" in w.title())
        assert button(dialog,"Save .gcode").instate(["disabled"])
        button(dialog,"Plot timeline").invoke()
        plan = make.call_args.args[1]
        assert plan.strokes == 117
        window = next(w for w in descend(dialog) if isinstance(w,tk.Toplevel))
        root.update()
        hold = next(e for e in plan.events if e.kind == "Start hold")
        slider = next(w for w in descend(window) if isinstance(w,ttk.Scale))
        slider.set(hold.end-5)
        button(window,"Play").invoke()
        root.update()
        assert button(window,"Pause")
        button(dialog,"Pen-up test (uncheck to draw with ink)").invoke()
        assert not window.winfo_exists()
        button(dialog,"Plot timeline").invoke()
        ink = make.call_args.args[1]
        assert any(e.down for e in ink.events)
    session = Mock()
    state = dict(connected=True,busy=True,state="Run",last_result=None,
                 job=dict(state="running",accepted=27,completed=4,total=len(ink.events),error="",operation=3))
    session.snapshot.return_value = state
    live = JobWindow(root,session,3,timeline=ink)
    live.window.after_cancel(live.after_id)
    live.poll()
    root.update()
    assert live.trace.count == 4
    live.window.after_cancel(live.after_id)
    state["job"].update(completed=11, operation=2)
    live.poll()
    assert live.trace.count == 4
    live.window.after_cancel(live.after_id)
    state.update(busy=False,last_result=(3, 'run_job', ''))
    state['job'].update(state='stopped',operation=3)
    live.poll()
    assert 'Pen up' in live.trace.caption.cget('text')
    live.close()
