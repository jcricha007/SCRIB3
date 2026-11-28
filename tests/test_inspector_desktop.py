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

def test_group_selection_inches_absolute_placement_and_undo(studio):
    from scrib3.board import Board, Mark, bounds
    studio.show_board()
    e = studio.board_editor
    original = Board(marks=(Mark("#112233",((10,12),(30,22)),("Title block","Logo")),
                            Mark("#335555",((80,50),(100,60)),("Notes",))))
    e.load(original,None)
    panel = e.open_inspector()
    studio.root.update()
    nested = next(i for i,g in panel.groups.items() if g == ("Title block","Logo"))
    panel.tree.selection_set(nested)
    studio.root.update()
    assert e.selection == {0}
    panel.unit.set("in")
    panel.refresh(force=True)
    panel.fields["x"].set("1")
    panel.fields["y"].set(".5")
    panel.fields["width"].set("2")
    panel.apply_button.invoke()
    assert bounds(e.selected()) == pytest.approx((25.4,12.7,76.2,38.1))
    assert e.board.marks[1] == original.marks[1]
    e.undo()
    assert e.board == original
