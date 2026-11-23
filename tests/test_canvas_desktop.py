"""Normal-entry UI regressions, enabled in a desktop test session."""

import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import patch, Mock

from scrib3.app import Studio
from scrib3.board import Mark
from scrib3.printer_ui import PrinterWindow


@skipUnless(os.environ.get("SCRIB3_DESKTOP_TESTS") == "1", "Desktop display required")
class CanvasDesktopTests(TestCase):
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
                with patch(
                    "scrib3.canvas_ui.form",
                    return_value={"quality": "Fine", "duplicates": "Yes", "joins": "No"},
                ):
                    e.clean()
                self.assertEqual(len(e.board.marks), 1)
                p = Path(tmp) / "board.scrib3"
                with patch("tkinter.filedialog.asksaveasfilename", return_value=str(p)):
                    self.assertTrue(e.save())
                original = e.board
                e.new()
                with patch("tkinter.filedialog.askopenfilename", return_value=str(p)):
                    e.open()
                self.assertEqual(e.board, original)
                w = PrinterWindow(e, "H2S")
                for k, v in dict(offset_x=0, offset_y=-28, contact_z=2, lift_z=5).items():
                    w.fields[k].set(str(v))
                self.assertIsNotNone(w.preview())
                self.assertTrue(w.canvas.find_all())
                root.geometry("800x650")
                root.update()
                self.assertTrue(e.canvas.winfo_viewable())
                self.assertGreater(e.canvas.winfo_width(), 400)
                studio.show_workbench()
                root.update()
                self.assertFalse(e.winfo_viewable())
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
                e.commit(replace(e.board, marks=(Mark("#522d80", ((10, 10), (20, 20))),)))
                e.pen.set("#522d80")
                s.firmware.set("Manual commands")
                s.machine_width.set("20")
                s.machine_height.set("20")
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
                    review.assert_called_once_with()
            finally:
                for after in root.tk.call("after", "info"):
                    root.after_cancel(after)
                root.destroy()
