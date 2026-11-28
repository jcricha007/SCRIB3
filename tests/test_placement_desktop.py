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

def test_save_load_holder_guides_on_blank_board_and_export_both_modes(studio,tmp_path):
    from scrib3.board import Board
    from scrib3.p1s_layout_ui import PlacementWindow
    from zipfile import ZipFile
    p = studio.show_p1s()
    for field, value in (("offset_x","4"),("offset_y","-3"),("contact_z","1.2"),("lift_z","5")):
        p.fields[field].set(value)
    w = PlacementWindow(p)
    w.name.set("Fine pen on cardstock")
    w.fields["clip_left"].set("6")
    w.save()
    p.fields["offset_x"].set("25")
    w.fields["clip_left"].set("3")
    w.load()
    assert float(p.fields["offset_x"].get())==4 and float(w.fields["clip_left"].get())==6
    for mode,name in (("Full-scale tiles","poster.zip"),("Fit on one sheet","poster.gcode.3mf")):
        w.mode.set(mode)
        assert w.preview()
        dst = tmp_path/name
        with patch("tkinter.messagebox.askokcancel",return_value=True), patch("tkinter.filedialog.asksaveasfilename",return_value=str(dst)):
            w.export()
        with ZipFile(dst) as z:
            assert ("layout.json" if mode=="Full-scale tiles" else "Metadata/plate_1.gcode") in z.namelist()
    studio.show_board()
    studio.board_editor.load(Board(),None)
    w.overlay()
    studio.root.update()
    assert studio.board_editor.canvas.find_withtag("p1s_guides")
    studio.board_editor.hide_p1s_guides()
    assert not studio.board_editor.canvas.find_withtag("p1s_guides")
