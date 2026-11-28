from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch
import os
import tkinter as tk

from scrib3.board import (
    Board,
    Mark,
    export_svg,
    load_board,
    save_board,
)

from scrib3.demo import sample, sample_board
from scrib3.geometry import shape, hatch, bezier
from scrib3.svg_artwork import import_svg

RED = "#f56600"
BLUE = "#522d80"


class BoardTests(TestCase):
    def test_airframe_retains_the_svg_page_position_and_pen_groups(self):
        board = sample_board()
        self.assertEqual((board.width, board.height), (279.4, 215.9))
        self.assertEqual(board.pens(), ("#171717",))
        self.assertEqual(len(board.marks), 117)
        self.assertEqual({m.groups for m in board.marks},
                         {("exterior",), ("panel-lines",), ("surface-marks",)})
        self.assertEqual(sample(), tuple(m.points for m in board.marks))
        # The first move is at (73.8, 349.8) in a viewBox starting at (48, 34.25).
        x, y = board.marks[0].points[0]
        self.assertAlmostEqual(x, (73.8 - 48) * 279.4 / 473)
        self.assertAlmostEqual(y, (349.8 - 34.25) * 215.9 / 365.5)
        pen_paths, sheet = board.plot_layer("#171717")
        self.assertEqual(pen_paths[0][0], (x, sheet.height - y))

    def test_color_and_placement_round_trip_across_pen_passes(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "drawing.svg"
            board = Board(
                297,
                210,
                (
                    Mark(RED, ((10.0, 30.0), (31.0, 54.0))),
                    Mark(BLUE, ((150.0, 40.0), (153.0, 45.0))),
                ),
            )
            export_svg(p, board)
            marks = import_svg(p)
            self.assertEqual([m.color for m in marks], [RED, BLUE])
            for got, want in zip(marks, board.marks):
                for pt, ref in zip(got.points, want.points):
                    for x, y in zip(pt, ref):
                        self.assertAlmostEqual(x, y, places=4)
            self.assertEqual(board.plot_layer(BLUE)[0], (((150.0, 170.0), (153.0, 165.0)),))

    def test_transform_and_full_board_file_preserve_locked_layers(self):
        a = Mark(RED, ((0, 0), (10, 0)))
        b = Mark(BLUE, ((2, 4), (6, 4)))
        board = Board(297, 210, (a, b), locked=frozenset([RED]), bed=(340, 320))
        changed = board.transform({0, 1}, angle=90, factor=2, dx=2)
        self.assertEqual(changed.marks, (a, Mark(BLUE, ((6, 0), (6, 8)))))
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "boat.scrib3"
            save_board(p, changed)
            self.assertEqual(load_board(p), changed)
            p.write_text("{}")
            with self.assertRaises(ValueError):
                load_board(p)

    def test_hatch_leaves_hole_and_only_plots_visible_inside_sheet(self):
        outline = Mark(RED, shape("Rectangle", (0, 0), (10, 10)))
        hole = Mark(RED, shape("Rectangle", (3, 3), (7, 7)))
        lines = hatch([outline, hole], 1)
        self.assertEqual(
            [m.points for m in lines if m.points[0][1] == 4.5],
            [((0, 4.5), (3, 4.5)), ((7, 4.5), (10, 4.5))],
        )
        self.assertTrue(hatch([outline], 1, "Crosshatch"))
        board = Board(marks=(outline,))
        for bad in [replace(board, hidden=frozenset([RED])), board.transform({0}, dx=-1)]:
            with self.assertRaises(ValueError):
                bad.plot_layer(RED)
        self.assertEqual(bezier([(0, 0), (0, 5), (5, 5), (5, 0)])[-1], (5, 0))


@skipUnless(os.environ.get("SCRIB3_DESKTOP_TESTS") == "1", "Desktop display required")
class BoardDesktopTests(TestCase):
    def test_new_board_mouse_edit_save_open_and_pen_review(self):
        from scrib3.app import Studio

        with TemporaryDirectory() as tmp:
            root = tk.Tk()
            try:
                studio = Studio(root, Path(tmp) / "preset.json")
                studio.show_board()
                root.update()
                editor = studio.board_editor
                self.assertTrue(editor.canvas.winfo_viewable())
                editor.new()
                cv = editor.canvas
                editor.mode.set("Rectangle")
                cv.event_generate("<Button-1>", x=120, y=120)
                cv.event_generate("<B1-Motion>", x=260, y=250)
                cv.event_generate("<ButtonRelease-1>", x=260, y=250)
                root.update()
                self.assertEqual(len(editor.board.marks), 1)
                editor.all()
                editor.transform(fit=True)
                editor.transform(factor=0.5, angle=90)
                editor.duplicate()
                self.assertEqual(len(editor.board.marks), 2)
                editor.undo(False)
                editor.undo(True)
                p = str(Path(tmp) / "test.scrib3")
                with patch("tkinter.filedialog.asksaveasfilename", return_value=p):
                    self.assertTrue(editor.save())
                original = editor.board
                editor.new()
                with patch("tkinter.filedialog.askopenfilename", return_value=p):
                    editor.open()
                self.assertEqual(editor.board, original)
                # Verify the running app reviews exactly the selected pen in board coordinates.
                studio.firmware.set("Manual commands")
                studio.pen_up.set("M5")
                studio.pen_down.set("M3 S200")
                with patch("scrib3.app.PlotJob", side_effect=ValueError("captured")) as job, patch(
                    "tkinter.messagebox.showerror"
                ):
                    studio.review(board_editor=editor)
                self.assertEqual(job.call_args.args[1].width, 297)
                self.assertEqual(job.call_args.args[1].height, 210)
                self.assertEqual((job.call_args.args[2].width, job.call_args.args[2].height), (210, 297))
                self.assertTrue(job.call_args.args[4])
                studio.show_workbench()
                self.assertFalse(studio.on_board())
            finally:
                for item in root.tk.call("after", "info"):
                    root.after_cancel(item)
                root.destroy()
