"""Normal-entry UI regressions, enabled in a desktop test session."""

import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from tkinter import ttk
from unittest import TestCase, skipUnless
from unittest.mock import patch, Mock
from zipfile import ZipFile

from scrib3.app import Studio
from scrib3.board import Mark


@skipUnless(os.environ.get("SCRIB3_DESKTOP_TESTS") == "1", "Desktop display required")
class CanvasDesktopTests(TestCase):
    def test_compact_toolbars_layers_and_plate_preview(self):
        root = tk.Tk()
        try:
            with TemporaryDirectory() as tmp:
                studio = Studio(root, Path(tmp) / "preset.json")
                root.geometry("800x650")
                studio.show_board()
                editor = studio.board_editor
                studio.board_window.geometry("800x600")
                ink = "#2563eb"
                editor.commit(replace(editor.board, marks=(Mark(ink, ((1, 1), (10, 10))),)))
                editor.layers.selection_set(ink)
                root.update()
                self.assertEqual(editor.pen.get(), ink)
                self.assertEqual(int(editor.layers.set(ink, "count")), 1)
                self.assertTrue(editor.layers.item(ink, "image"))
                header = editor.winfo_children()[0]
                side = editor.layers.master
                fit, = (item for item in side.winfo_children()
                        if isinstance(item, ttk.Button) and item.cget("text") == "Fit view")
                self.assertGreaterEqual(fit.winfo_height(), fit.winfo_reqheight())
                menus = [button for button in header.winfo_children() if isinstance(button, ttk.Menubutton)]
                self.assertEqual(len(menus), 7)
                for button in menus:
                    self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth())
                board_menu = menus[0].nametowidget(menus[0].cget("menu"))
                self.assertEqual(board_menu.type(0), "command")

                printer = studio.show_p1s()
                root.update()
                plate = printer.canvas.coords("plate")
                self.assertTrue(plate)
                self.assertFalse(studio.status_bar.winfo_ismapped())
                actions = printer.dry_button.master
                for button in actions.winfo_children():
                    if isinstance(button, ttk.Button):
                        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                             studio.p1s_panel.winfo_rooty() + studio.p1s_panel.winfo_height())
                root.geometry("1200x800")
                root.update()
                self.assertNotEqual(plate, printer.canvas.coords("plate"))
                studio.show_workbench()
                root.update()
                self.assertTrue(studio.status_bar.winfo_ismapped())
        finally:
            for callback in root.tk.call("after", "info"):
                root.after_cancel(callback)
            root.destroy()

    def test_color_sequence_advances_only_on_successful_current_job(self):
        from scrib3.job_ui import JobWindow

        root = tk.Tk()
        root.withdraw()
        try:
            for state, connected, operation, error, expected in [
                ("completed", True, 7, "", 1),
                ("stopped", True, 7, "", 0),
                ("failed", True, 7, "alarm", 0),
                ("completed", False, 7, "", 0),
                ("completed", True, 8, "", 0),
            ]:
                with self.subTest(state=state, connected=connected, operation=operation):
                    session = Mock()
                    session.snapshot.return_value = dict(
                        connected=connected, busy=False, state="Idle",
                        last_result=(operation, "run_job", error),
                        job=dict(state=state, accepted=5, completed=5, total=5, error=error),
                    )
                    complete = Mock()
                    window = JobWindow(root, session, 7, on_complete=complete)
                    window.window.after_cancel(window.after_id)
                    window.poll()
                    root.update()
                    self.assertEqual(complete.call_count, expected)
                    window.close()
        finally:
            for after in root.tk.call("after", "info"):
                root.after_cancel(after)
            root.destroy()

    def test_draw_transform_save_legacy_open_and_printer_review(self):
        with TemporaryDirectory() as tmp:
            root = tk.Tk()
            try:
                studio = Studio(root, Path(tmp) / "preset.json")
                studio.show_board()
                root.update()
                e = studio.board_editor
                e.new()
                e.bed((340, 320))
                root.update()
                self.assertTrue(e.canvas.find_withtag("bed_guide"))
                e.mode.set("Rectangle")
                e.canvas.event_generate("<Button-1>", x=200, y=200)
                e.canvas.event_generate("<B1-Motion>", x=350, y=300)
                e.canvas.event_generate("<ButtonRelease-1>", x=350, y=300)
                root.update()
                self.assertEqual(len(e.board.marks), 1)
                e.all()
                e.transform(factor=0.5, angle=90)
                e.duplicate()
                self.assertEqual(len(e.board.marks), 2)
                e.undo()
                self.assertEqual(len(e.board.marks), 1)
                e.undo(True)
                self.assertEqual(len(e.board.marks), 2)
                e.all()
                clean = e.clean()
                clean.remove.set(True)
                clean.update()
                self.assertEqual(len(e.board.marks), 2)
                self.assertEqual(len(clean.result), 1)
                clean.apply()
                self.assertEqual(len(e.board.marks), 1)
                p = Path(tmp) / "board.scrib3"
                with patch("tkinter.filedialog.asksaveasfilename", return_value=str(p)):
                    self.assertTrue(e.save())
                original = e.board
                e.new()
                with patch("tkinter.filedialog.askopenfilename", return_value=str(p)):
                    e.open()
                self.assertEqual(e.board, original)
                w = e.printer("H2S")
                for k, v in dict(offset_x=0, offset_y=-28, contact_z=2, lift_z=5).items():
                    w.fields[k].set(str(v))
                self.assertIsNotNone(w.preview())
                self.assertTrue(w.canvas.find_all())
                e.root.geometry("800x650")
                root.update()
                self.assertTrue(e.canvas.winfo_viewable())
                self.assertGreater(e.canvas.winfo_width(), 400)
                studio.show_workbench()
                root.update()
                self.assertTrue(e.winfo_viewable())
                self.assertTrue(studio.controls.winfo_viewable())
                studio.show_board()
                root.update()
                self.assertTrue(e.winfo_viewable())
            finally:
                for after in root.tk.call("after", "info"):
                    root.after_cancel(after)
                root.destroy()

    def test_board_review_uses_registered_geometry(self):
        with TemporaryDirectory() as tmp:
            root = tk.Tk()
            try:
                s = Studio(root, Path(tmp) / "preset.json")
                s.show_board()
                e = s.board_editor
                e.new()
                e.commit(replace(e.board, marks=(Mark("#522d80", ((10, 10), (20, 20))),)))
                e.pen.set("#522d80")
                s.firmware.set("Manual commands")
                with patch("scrib3.app.PlotJob", side_effect=ValueError("captured")) as job, patch(
                    "tkinter.messagebox.showerror"
                ):
                    s.review(board_editor=e)
                self.assertEqual(job.call_args.args[1].width, 297)
                self.assertEqual(set(job.call_args.args[0][0]), {(10, 200), (20, 190)})
                with patch.object(s, "review") as review:
                    s.workspace_action("review")
                    review.assert_called_once_with(board_editor=e)
                s.show_workbench()
                with patch.object(s, "review") as review:
                    s.workspace_action("review")
                    review.assert_called_once_with(board_editor=e)
            finally:
                for after in root.tk.call("after", "info"):
                    root.after_cancel(after)
                root.destroy()

    def test_p1s_guide_reviews_and_opens_the_saved_calibration_plate(self):
        from scrib3.p1s_workflow import DRY_A4, REGISTER, HolderGuide

        with TemporaryDirectory() as tmp:
            root = tk.Tk()
            try:
                studio = Studio(root, Path(tmp) / "preset.json")
                startup_board = studio.current_board
                printer = studio.show_p1s()
                self.assertIs(printer.window, root)
                self.assertIsNone(studio.board_window)
                for key, value in dict(offset_x=0, offset_y=-28, contact_z=2, lift_z=5).items():
                    printer.fields[key].set(str(value))
                printer.fit.set(True)
                plan = printer.preview()
                self.assertEqual([color for color, _ in plan.passes], list(startup_board.pens()))
                self.assertIsNone(studio.board_window)
                printer.fit.set(False)
                studio.show_board()
                self.assertIs(studio.board_editor.printer("P1S"), printer)
                root.update()
                self.assertTrue(studio.board_editor.winfo_viewable())
                guide = HolderGuide(printer)
                for key, value in dict(nozzle_x=100, nozzle_y=100, tip_x=100,
                                       tip_y=72, contact_z=2, lift_z=5).items():
                    guide.measured[key].set(str(value))
                for _ in range(4):
                    guide.next()
                self.assertEqual(printer.holder().offset_y, -28)
                self.assertEqual(printer.target.get(), DRY_A4)
                self.assertTrue(printer.dry_button.instate(["disabled"]))
                self.assertIsNone(printer.preview())
                printer.fit.set(True)
                printer.dry.set(False)
                self.assertTrue(printer.preview().dry)
                printer.target.set(REGISTER)
                printer.target_changed()
                self.assertTrue(printer.dry_button.instate(["!disabled"]))
                printer.dry.set(False)
                plan = printer.preview()
                self.assertEqual(len(plan.passes), 2)
                path = Path(tmp) / "registration.gcode.3mf"
                with patch("tkinter.filedialog.asksaveasfilename", return_value=str(Path(tmp) / "registration.3mf")), patch(
                    "tkinter.messagebox.askokcancel", return_value=True
                ), patch("scrib3.p1s_workflow.open_in_studio") as handoff:
                    printer.export(open_studio=True)
                handoff.assert_called_once_with(path)
                with ZipFile(path) as archive:
                    self.assertEqual(archive.read("Metadata/plate_1.gcode"), plan.gcode().encode("ascii"))
                self.assertIs(studio.board_editor.board, startup_board)
                studio.hide_board()
                self.assertTrue(studio.p1s_active)
                studio.show_workbench()
                root.update()
                self.assertTrue(studio.controls.winfo_viewable())
            finally:
                for after in root.tk.call("after", "info"):
                    root.after_cancel(after)
                root.destroy()

    def test_drag_cubic_handle_and_reuse_the_group_on_a_new_board(self):
        from scrib3.poster_objects import cubic_points

        with TemporaryDirectory() as tmp:
            root = tk.Tk()
            try:
                studio = Studio(root, Path(tmp) / "prefs.json")
                studio.show_board()
                root.update()
                editor = studio.board_editor
                editor.new()
                points = ((40, 50), (48, 28), (70, 32), (85, 50))
                line = Mark(editor.pen.get(), cubic_points(points), ("Mirror",), controls=points)
                editor.insert((line,), placed=True)
                editor.mode.set("Edit nodes")
                root.update()
                handle = editor.canvas.find_withtag("point-0-1")[0]
                x0, y0, x1, y1 = editor.canvas.coords(handle)
                x, y = round((x0+x1)/2), round((y0+y1)/2)
                editor.canvas.event_generate("<Button-1>", x=x, y=y)
                editor.canvas.event_generate("<B1-Motion>", x=x+12, y=y+15)
                editor.canvas.event_generate("<ButtonRelease-1>", x=x+12, y=y+15)
                edited = editor.board.marks[0]
                self.assertNotEqual(edited.controls[1], points[1])
                self.assertEqual(edited.controls[2:], points[2:])
                self.assertEqual(edited.points, cubic_points(edited.controls))
                element = Path(tmp) / "mirror.scrib3"
                with patch("tkinter.filedialog.asksaveasfilename", return_value=str(element)):
                    editor.save_asset()
                with patch("tkinter.messagebox.askyesnocancel", return_value=False):
                    editor.new()
                with patch("tkinter.filedialog.askopenfilename", return_value=str(element)):
                    editor.open_asset()
                    editor.open_asset()
                self.assertEqual([m.groups for m in editor.board.marks], [("Mirror",), ("Mirror (2)",)])
                self.assertEqual(editor.board.marks[0].controls, editor.board.marks[1].controls)
            finally:
                for after in root.tk.call("after", "info"):
                    root.after_cancel(after)
                root.destroy()

    def test_sheet_template_keeps_title_block_and_custom_artwork(self):
        from time import monotonic, sleep
        import trimesh
        from scrib3.board import load_board
        from scrib3.engineering_sheet import VIEW_GROUP

        with TemporaryDirectory() as tmp:
            root = tk.Tk()
            try:
                studio = Studio(root, Path(tmp) / "prefs.json")
                studio.show_board()
                editor = studio.board_editor
                logo = Mark(editor.pen.get(), ((20, 20), (25, 25)), (VIEW_GROUP,))
                editor.insert((logo,), placed=True)
                model = Path(tmp) / "Bracket.stl"
                trimesh.creation.box(extents=(30, 20, 10)).export(model)
                with patch("tkinter.filedialog.askopenfilename", return_value=str(model)):
                    sheet = editor.engineering_sheet()
                deadline = monotonic() + 10
                while sheet.views is None and monotonic() < deadline:
                    root.update()
                    sleep(.01)
                self.assertIsNotNone(sheet.result, sheet.status.get())
                sheet.apply()
                self.assertIn(logo, editor.board.marks)
                self.assertTrue(any(m.sheet_part == "view" for m in editor.board.marks))
                template = Path(tmp) / "shop.scrib3"
                with patch("tkinter.filedialog.asksaveasfilename", return_value=str(template)):
                    editor.save_asset(template=True)
                stored = load_board(template)
                self.assertIn(logo, stored.marks)
                self.assertTrue(any(m.sheet_part == "frame" and m.text for m in stored.marks))
                self.assertFalse(any(m.sheet_part == "view" for m in stored.marks))
                with patch("tkinter.filedialog.askopenfilename", return_value=str(template)), patch(
                    "tkinter.messagebox.askyesnocancel", return_value=False
                ):
                    editor.open_asset(template=True)
                self.assertEqual(editor.board, stored)
                self.assertIsNone(editor.path)
            finally:
                for after in root.tk.call("after", "info"):
                    root.after_cancel(after)
                root.destroy()
