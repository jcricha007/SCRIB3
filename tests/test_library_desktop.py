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

def test_interrupted_artwork_restores_to_an_unsaved_copy_then_becomes_recent(studio,tmp_path):
    from dataclasses import replace
    from scrib3.board import Board, Mark, save_board, load_board
    from scrib3.board_library import BoardLibrary
    source = tmp_path/"airframe.scrib3"
    save_board(source,Board())
    studio.show_board()
    e = studio.board_editor
    e.load(load_board(source),source)
    art = Board(marks=(Mark("#224f80",((30,20),(70,60)),("Logo",)),))
    e.commit(art)
    # Losing the first process releases its lease without a clean save or discard.
    studio.library.release()
    studio.library = BoardLibrary(tmp_path)
    e.load(Board(),None)
    studio.update_recovery_link()
    assert studio.recovery_button.grid_info()
    gallery = studio.open_library("Recovery")
    row, = gallery.list.get_children()
    gallery.list.selection_set(row)
    gallery.open()
    assert e.board == art and e.path is None and e.saved is None and load_board(source) == Board()
    target = tmp_path/"restored.scrib3"
    with patch("tkinter.filedialog.asksaveasfilename",return_value=str(target)):
        assert e.save()
    assert load_board(target) == art and studio.library.entries("Recovery") == []
    gallery = studio.open_library("Boards")
    assert list(gallery.rows.values())[0].key == str(target)
    gallery.window.destroy()
    e.all()
    element = tmp_path/"Garage logo.scrib3"
    with patch("tkinter.filedialog.asksaveasfilename",return_value=str(element)):
        e.save_asset()
    gallery = studio.open_library("Elements")
    gallery.list.selection_set(gallery.list.get_children()[0])
    gallery.open()
    assert len(e.board.marks)==2 and e.board.marks[0]==art.marks[0]
