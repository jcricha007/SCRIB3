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

def test_compare_review_and_reopen_saved_winner(studio):
    from scrib3.quality_card_ui import QualityCardWindow
    from scrib3.units import to_mm
    card = QualityCardWindow(studio)
    card.pen.set("Fineliner")
    card.paper.set("Cardstock")
    card.ratings[1].set("Clean")
    card.winner.set(1)
    card.notes.set("Middle row closed cleanly.")
    card.save()
    before = (studio.paper_mount.get(),studio.pen_up.get(),studio.pen_down.get())
    studio.firmware.set("Manual commands")
    with patch("tkinter.messagebox.showerror") as errors:
        card.review(1)
        errors.assert_not_called()
    assert any("Quality test at" in w.title() for w in studio.root.winfo_children() if isinstance(w,tk.Toplevel))
    card.window.destroy()
    again = QualityCardWindow(studio)
    again.choice.current(0)
    again.load()
    again.apply()
    assert to_mm(studio.feed.get(), studio.unit) == pytest.approx(float(again.feeds[1].get()))
    assert again.winner.get()==1 and again.notes.get()=="Middle row closed cleanly."
    assert (studio.paper_mount.get(),studio.pen_up.get(),studio.pen_down.get()) == before
