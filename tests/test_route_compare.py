import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import patch

from scrib3.route_compare import compare_candidate, run_vpype

BAD = (((90, 0), (100, 0)), ((0, 0), (10, 0)), ((50, 0), (60, 0)))
GOOD = (BAD[1], BAD[2], BAD[0])


class RouteComparisonTests(TestCase):
    def test_rejects_geometry_changes_missing_strokes_and_lost_overdraw(self):
        for candidate in (GOOD[:-1], GOOD+GOOD[:1], (GOOD[0], GOOD[1], ((90, 0), (100, .001)))):
            with self.assertRaisesRegex(ValueError, 'geometry'):
                compare_candidate(BAD, candidate, (0, 0))
        with self.assertRaisesRegex(ValueError, 'geometry'):
            compare_candidate(BAD+BAD[:1], GOOD, (0, 0))
        result = compare_candidate(BAD, GOOD, (0, 0))
        self.assertTrue(result.improved)
        self.assertEqual(result.drawing, GOOD)
        self.assertEqual((result.before_mm, result.after_mm), (230, 70))

    def test_actual_origin_reverse_and_non_improving_candidates(self):
        result = compare_candidate(GOOD, BAD, (0, 0))
        self.assertEqual(result.drawing, GOOD)
        self.assertFalse(result.improved)
        result = compare_candidate(BAD, GOOD, (100, 0))
        self.assertEqual(result.drawing[0][0], (100, 0))
        self.assertTrue(result.improved)
        event = Event(); event.set()
        with self.assertRaisesRegex(ValueError, 'cancelled'):
            run_vpype(BAD, (0, 0), event)

    def test_worker_timeout_and_cancellation_kill_process(self):
        with patch('scrib3.route_compare.subprocess.Popen') as popen:
            process = popen.return_value
            process.poll.return_value = None
            with self.assertRaisesRegex(ValueError, 'exceeded'):
                run_vpype(BAD, (0, 0), Event(), timeout=0)
            process.kill.assert_called_once()
            process.wait.assert_called_once()

    @skipUnless(os.environ.get('SCRIB3_VPYPE_TESTS') == '1', 'Optional vpype integration')
    def test_real_worker_preserves_curves_loops_gaps_and_repeated_strokes(self):
        drawing = BAD + (((20, 20), (21, 23), (22, 20), (20, 20)),) + BAD[:1]
        result = run_vpype(drawing, (0, 0), Event())
        self.assertLessEqual(result.after_mm, result.before_mm)
        compare_candidate(drawing, result.drawing, (0, 0))
        # A difficult ordering must actually improve with the real installed tool.
        self.assertTrue(run_vpype(BAD, (0, 0), Event()).improved)


@skipUnless(os.environ.get('SCRIB3_DESKTOP_TESTS') == '1', 'Desktop display required')
class RouteDesktopTests(TestCase):
    def test_apply_restore_and_stale_worker_results(self):
        from scrib3.app import Studio
        from scrib3.route_ui import RouteWindow
        with TemporaryDirectory() as folder:
            root = tk.Tk()
            errors = []
            root.report_callback_exception = lambda *args: errors.append(str(args))
            app = Studio(root, Path(folder)/'prefs.json')
            app.tabs.select(app.design_tab)
            win = RouteWindow(app)
            def wait(predicate):
                deadline = monotonic()+5
                while monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    sleep(.01)
                self.fail('UI operation timed out')
            def fake(drawing, start, cancel):
                ordered = tuple(sorted(drawing, key=lambda s: s[0][0]))
                return compare_candidate(drawing, ordered, start)
            try:
                app.optimize.set(False)
                app.paper_mount.set('bottom_left_x')
                app.set_drawing('Route fixture', BAD)
                before = app.drawing
                with patch('scrib3.route_ui.run_vpype', side_effect=fake):
                    win.compare(); wait(lambda: not win.busy)
                    self.assertTrue(win.result.improved)
                    self.assertEqual(app.drawing, before)
                    revision = app.revision
                    win.apply()
                    self.assertGreater(app.revision, revision)
                    self.assertNotEqual(app.drawing, before)
                    app.refresh()
                    self.assertEqual(app.drawing, win.result.drawing)
                    win.restore()
                    self.assertEqual(app.drawing, before)
                    win.compare(); wait(lambda: not win.busy)
                    app.margin.set('0.6')
                    win.apply()
                    self.assertIn('changed', win.status.get())
                    self.assertIsNone(getattr(app, 'route_override', None))
                release = Event()
                def slow(drawing, start, cancel):
                    release.wait(3)
                    return fake(drawing, start, cancel)
                with patch('scrib3.route_ui.run_vpype', side_effect=slow):
                    win.compare(); app.create_pattern(); release.set()
                    wait(lambda: not win.busy)
                    self.assertIn('changed', win.status.get())
                    self.assertIsNone(win.result)
                    release.clear(); win.compare(); win.cancel.set(); release.set()
                    wait(lambda: not win.busy)
                    self.assertIn('cancelled', win.status.get())
                win.window.geometry('580x480'); root.geometry('800x650'); root.update()
                self.assertGreater(win.canvas.winfo_height(), 100)
                self.assertLessEqual(win.apply_button.winfo_rootx()+win.apply_button.winfo_width(),
                                     win.window.winfo_rootx()+win.window.winfo_width())
                self.assertTrue(app.route_button.winfo_viewable())
                self.assertFalse(errors, errors)
            finally:
                win.close(); app.shutdown()
                for callback in root.tk.call('after', 'info'):
                    root.tk.call('after', 'cancel', callback)
                root.destroy()
