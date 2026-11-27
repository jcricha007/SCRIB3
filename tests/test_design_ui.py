import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import patch

from scrib3 import controls, ollama, presets
from scrib3.app import Studio
from scrib3.calibration_ui import CalibrationWindow
from scrib3.controller import Controller
from scrib3.setup_guides import MotionDefaultsWindow, PaperGuideWindow, SMOOTH_SETTINGS
from scrib3.quality_ui import QualityWindow
from scrib3.vector_io import read_drawing
from scrib3.units import to_mm
from test_controller import FakeSerial


@skipUnless(os.environ.get('SCRIB3_DESKTOP_TESTS') == '1', 'Desktop display required')
class DesignDesktopTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.root = tk.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(str(args))
        self.app = Studio(self.root, preset_file=Path(self.folder.name) / 'prefs.json')
        self.app.tabs.select(self.app.design_tab)
        self.windows = []
        self.root.update()

    def tearDown(self):
        for window in self.windows:
            if not getattr(window, 'closed', False):
                window.close()
        if self.app.assistant:
            self.app.assistant.shutdown()
        if self.app.controls.session:
            self.app.controls.session.close()
            self.app.controls.session.thread.join(2)
        for callback in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', callback)
        self.root.destroy()
        self.folder.cleanup()
        self.assertFalse(self.errors, self.errors)

    def wait(self, predicate, timeout=6):
        end = monotonic() + timeout
        while monotonic() < end:
            self.root.update()
            if predicate():
                return
            sleep(.01)
        raise AssertionError('Desktop condition timed out')

    def settle(self):
        end = monotonic() + .2
        while monotonic() < end:
            self.root.update(); sleep(.01)

    def test_chat_design_review_undo_cancel_and_local_model_save(self):
        original = self.app.source
        reply = (((0, 0), (1000, 500)), ((500, 300), (700, 900)))
        def chat(model, messages, context, **kwargs):
            kwargs['on_chunk']('Try a contour drawing.')
            return 'Try a contour drawing.'
        with patch.object(ollama, 'local_models', return_value=('engineering:latest',)), patch.object(ollama, 'chat', side_effect=chat), patch.object(ollama, 'generate_drawing', return_value=reply):
            self.app.open_assistant()
            ai = self.app.assistant
            self.wait(lambda: not ai.busy and self.app.model.get() == 'engineering:latest')
            ai.chat_input.insert('1.0', 'Help me design a landscape.')
            ai.send_chat()
            self.wait(lambda: not ai.busy)
            self.assertIn('Try a contour', ai.chat_output.get('1.0', 'end'))
            self.assertEqual(len(ai.history), 2)
            ai.prompt_to_design()
            self.assertIn('landscape', ai.design_input.get('1.0', 'end'))
            ai.generate()
            self.wait(lambda: not ai.busy)
            self.assertEqual(self.app.source, original)
            self.assertEqual(ai.draft, reply)
            ai.apply()
            self.assertEqual(self.app.source, reply)
            self.app.undo_design()
            self.assertEqual(self.app.source, original)
            self.app.save_preset()
            self.assertEqual(presets.load(self.app.preset_file)['ollama_model'], 'engineering:latest')
            ai.clear_chat()
            self.assertFalse(ai.history)
            ai.window.geometry('720x600')
            self.root.update()
            self.assertLessEqual(ai.apply_button.winfo_rooty() + ai.apply_button.winfo_height(), ai.window.winfo_rooty() + ai.window.winfo_height())
        waiting, release = Event(), Event()
        def slow(*args):
            waiting.set(); release.wait(4); return reply
        with patch.object(ollama, 'generate_drawing', side_effect=slow):
            ai.generate(True)
            self.wait(waiting.is_set)
            self.app.create_pattern()
            changed = self.app.source
            ai.hide()
            release.set()
            self.wait(lambda: not ai.busy)
            self.assertEqual(self.app.source, changed)
            self.assertIn('cancelled', ai.status.get())
        for geometry in ('1120x740', '800x650'):
            self.root.geometry(geometry); self.app.tabs.select(0); self.root.update()
            self.assertLessEqual(self.app.tabs.winfo_rootx()+self.app.tabs.winfo_width(), self.root.winfo_rootx()+self.root.winfo_width())

    def test_calibration_migration_readback_reset_measurement_and_axis_specific_apply(self):
        peer = FakeSerial()
        with patch.object(controls, 'Controller', side_effect=lambda *a, **kw: Controller(*a, **kw, serial_factory=lambda *a, **k: peer)):
            panel = self.app.controls
            self.app.port.set('COM7'); panel.connect()
            self.wait(lambda: panel.session.snapshot()['connected'])
            self.settle()
            wizard = CalibrationWindow(panel); self.windows.append(wizard)
            wizard.test_move()
            self.assertIn('starting calibration', wizard.status.get())
            self.assertFalse(any(w.startswith(b'$J=') for w in peer.writes))
            wizard.apply_preset()
            self.wait(lambda: not panel.session.snapshot()['busy'] and wizard.applying is None)
            self.assertTrue(panel.session.snapshot()['reset_required'])
            self.assertEqual((peer.settings[100], peer.settings[101]), (5, 5))
            self.settle()
            self.assertTrue(panel.buttons['X +'].instate(['disabled']))
            wizard.close()
            panel.reset()
            self.wait(lambda: not panel.session.thread.is_alive())
            peer.state = 'Idle'
            panel.connect()
            self.wait(lambda: panel.session.snapshot()['connected'])
            wizard = CalibrationWindow(panel); self.windows.append(wizard)
            wizard.axis.set('X'); wizard.test_move()
            self.wait(lambda: peer.state == 'Jog' and not panel.session.snapshot()['busy'])
            # 2.54 mm requested at 5 steps/mm rounds to 13 steps = 2.6 mm.
            peer.position = '12.6,20,0'; peer.state = 'Idle'
            self.wait(lambda: wizard.measurement is not None)
            self.assertAlmostEqual(wizard.measurement['effective'], 2.6)
            wizard.measured.set(str(2.6/25.4))
            wizard.calculate()
            self.assertIn('$100: 5 steps/mm', wizard.correction.get())
            wizard.measured.set(str(2.5/25.4))
            wizard.apply_correction()
            self.wait(lambda: wizard.applying is None and not panel.session.snapshot()['busy'])
            self.assertEqual(peer.settings[100], 5.2)
            self.assertEqual(peer.settings[101], 5)
            self.assertEqual(presets.load(self.app.preset_file)['x_steps_per_mm'], 5.2)
            self.assertTrue(panel.session.snapshot()['reset_required'])

    def test_review_requires_current_design_and_runs_pen_up_test(self):
        from test_jobs import JobSerial
        peer = JobSerial(); peer.block_moves = False
        with patch.object(controls, 'Controller', side_effect=lambda *a, **kw: Controller(*a, **kw, serial_factory=lambda *a, **k: peer)), patch('scrib3.app.messagebox.showerror') as error:
            app, panel = self.app, self.app.controls
            app.port.set('COM7'); panel.connect()
            self.wait(lambda: panel.session.snapshot()['connected'])
            self.settle()
            app.unit_choice.set('Millimeters'); app.change_units()
            app.paper_width.set('10'); app.paper_height.set('10'); app.margin.set('1')
            app.feed.set('60')
            app.set_drawing('Test line', (((0, 0), (1, 1)),))
            panel.perform('zero')
            self.wait(lambda: not panel.session.snapshot()['busy'])
            self.settle()
            app.review()
            self.assertFalse(error.called, error.call_args)
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith('G-code review'))
            run = next(w for w in descendants(dialog) if w.winfo_class() == 'TButton' and w.cget('text') == 'Run sketch')
            self.assertIn('pen-up test', dialog.output.get('1.0', 'end'))
            for variable, changed in ((app.quality_mode, 'Fine'), (app.remove_duplicates, True),
                                      (app.join_strokes, True), (app.reloop, False)):
                original = variable.get()
                variable.set(changed)
                run.invoke()
                self.assertIn('settings changed', error.call_args.args[1])
                self.assertFalse(peer.normal_moves)
                variable.set(original)
                error.reset_mock()
            app.feed.set('61')
            run.invoke()
            self.assertIn('settings changed', error.call_args.args[1])
            self.assertFalse(peer.normal_moves)
            app.feed.set('60')
            app.seam_overlap.set('1')
            run.invoke()
            self.assertIn('settings changed', error.call_args.args[1])
            self.assertFalse(peer.normal_moves)
            dialog.destroy(); error.reset_mock()
            app.review()
            dialog = next(w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel) and w.title().startswith('G-code review'))
            dry = next(w for w in descendants(dialog) if w.winfo_class() == 'TCheckbutton')
            dry.invoke()
            self.assertIn('M3 S70.000', dialog.output.get('1.0', 'end'))
            dry.invoke()
            run = next(w for w in descendants(dialog) if w.winfo_class() == 'TButton' and w.cget('text') == 'Run sketch')
            run.invoke()
            self.wait(lambda: panel.session.snapshot()['job']['state'] == 'completed')
            self.assertFalse(error.called, error.call_args)
            self.assertNotIn(b'M3 S70.000\n', peer.writes)
            self.assertTrue(peer.normal_moves)

    def test_review_uses_paper_offline_and_current_controller_limits_when_connected(self):
        app, panel = self.app, self.app.controls
        app.unit_choice.set('Millimeters')
        app.change_units()
        app.firmware.set('Manual commands')
        app.paper_width.set('12')
        app.paper_height.set('8')
        app.margin.set('1')
        app.set_drawing('Travel check', (((0, 0), (1, 1)),))
        peer = FakeSerial()
        with patch.object(controls, 'Controller', side_effect=lambda *a, **kw: Controller(
                *a, **kw, serial_factory=lambda *a, **k: peer)), patch.object(
                app, 'text_dialog', wraps=app.text_dialog) as dialogs, patch('scrib3.app.messagebox.showerror') as error:
            app.review()
            self.assertIn('Offline review uses paper bounds', dialogs.call_args.args[1])
            self.assertTrue(app.save_preset())
            saved = presets.load(app.preset_file)
            self.assertEqual((saved['machine_width_mm'], saved['machine_height_mm']), (None, None))

            app.port.set('COM7')
            panel.connect()
            self.wait(lambda: panel.session.snapshot()['connected'])
            self.assertTrue(app.save_preset())
            self.assertEqual(app.saved_travel, (200, 200))
            app.review()
            self.assertFalse(error.called, error.call_args)
            self.assertNotIn('Offline review', dialogs.call_args.args[1])

            peer.settings[131] = 11
            panel.perform('refresh')
            self.wait(lambda: not panel.session.snapshot()['busy'])
            app.review()
            self.assertIn('needs X 8 and Y 12 mm', error.call_args.args[1])
            self.assertIn('X 200 and Y 11 mm', error.call_args.args[1])

            del peer.settings[131]
            panel.perform('refresh')
            self.wait(lambda: not panel.session.snapshot()['busy'])
            app.review()
            self.assertIn('$130 and $131', error.call_args.args[1])

    def test_smooth_motion_apply_readback_preserves_calibration_and_paper_orientation(self):
        peer = FakeSerial()
        with patch.object(controls, 'Controller', side_effect=lambda *a, **kw: Controller(*a, **kw, serial_factory=lambda *a, **k: peer)):
            app, panel = self.app, self.app.controls
            app.port.set('COM7'); panel.connect()
            self.wait(lambda: panel.session.snapshot()['connected'])
            app.feed.set('1'); panel.rate.set('2')
            before = dict(peer.settings)
            motion = MotionDefaultsWindow(app); self.windows.append(motion)
            motion.apply_controller()
            self.wait(lambda: motion.pending is None and not panel.session.snapshot()['busy'])
            self.assertEqual({n: peer.settings[n] for n in SMOOTH_SETTINGS}, SMOOTH_SETTINGS)
            self.assertEqual({n: v for n, v in peer.settings.items() if n not in SMOOTH_SETTINGS},
                             {n: v for n, v in before.items() if n not in SMOOTH_SETTINGS})
            # Allow inch-display rounding, well below exported feed precision.
            self.assertAlmostEqual(to_mm(app.feed.get(), app.unit), 1500, delta=1e-5)
            self.assertAlmostEqual(to_mm(panel.rate.get(), app.unit), 1500, places=6)
            self.assertAlmostEqual(presets.load(app.preset_file)['feed_mm_min'], 1500, delta=1e-5)
            self.assertFalse(panel.session.snapshot()['reset_required'])
            app.auto_motion_defaults.set(False)
            motion.save_automatic()
            self.assertFalse(presets.load(app.preset_file)['auto_motion_defaults'])
            self.assertIn('next connection', motion.status.get())
            app.tabs.select(1); self.root.geometry('800x650'); self.root.update()
            button = app.motion_defaults_button
            self.assertTrue(button.winfo_viewable())
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                 app.tabs.winfo_rooty() + app.tabs.winfo_height())
            guide = PaperGuideWindow(app)
            for name, dims in [('US Letter landscape', (279.4, 215.9)), ('US Letter portrait', (215.9, 279.4))]:
                guide.choice.set(name); guide.apply(); self.root.update()
                self.assertAlmostEqual(app.sheet.width, dims[0])
                self.assertAlmostEqual(app.sheet.height, dims[1])
                self.assertIn('exceeds', guide.status.get())
                self.assertEqual(app.travel_limits(), (200, 200))
            self.assertAlmostEqual(app.sheet.margin, 12.7)
            for geometry in ('660x740', '620x700'):
                guide.window.geometry(geometry); self.root.update()
                self.assertGreater(guide.canvas.winfo_height(), 200)
            panel.perform('zero')
            self.wait(lambda: not panel.session.snapshot()['busy'])
            self.assertTrue(panel.session.snapshot()['origin_set'])
            peer.settings.update({130: 215.9, 131: 279.4})
            panel.perform('refresh')
            self.wait(lambda: not panel.session.snapshot()['busy'])
            guide.use_john(); self.root.update()
            self.assertEqual(app.paper_mount.get(), 'top_left_y')
            self.assertEqual(presets.load(app.preset_file)['paper_mount'], 'top_left_y')
            self.assertIn('Fits configured', guide.status.get())
            guide.choice.set('US Letter portrait')
            guide.paint()
            self.assertIn('exceeds', guide.status.get())
            self.assertIn('+Y moves right; -X moves down', guide.instructions.get())
            self.assertFalse(panel.session.snapshot()['origin_set'])
            self.assertEqual(int(panel.buttons['Y +'].grid_info()['column']), 2)
            self.assertEqual(int(panel.buttons['Y −'].grid_info()['column']), 0)
            self.assertEqual(int(panel.buttons['X −'].grid_info()['row']), 2)
            guide.window.destroy()

    def test_vector_file_dialogs_quality_units_save_and_minimum_layout(self):
        app = self.app
        with patch('scrib3.app.messagebox.showerror') as error:
            app.create_pattern()
            for extension in ('svg', 'dxf', 'json'):
                path = Path(self.folder.name) / ('rosette.'+extension)
                with patch('scrib3.app.filedialog.asksaveasfilename', return_value=str(path)):
                    app.export_drawing()
                self.assertEqual(len(read_drawing(path)), 12)
                with patch('scrib3.app.filedialog.askopenfilename', return_value=str(path)):
                    app.import_drawing()
                self.assertEqual(app.source_name.get(), 'rosette')
                self.assertTrue(all(s[0] == s[-1] for s in app.source))
            def choose_dxf(**kwargs):
                kwargs['typevariable'].set('DXF')
                return str(Path(self.folder.name) / 'chosen-format')
            with patch('scrib3.app.filedialog.asksaveasfilename', side_effect=choose_dxf):
                app.export_drawing()
            self.assertEqual(len(read_drawing(Path(self.folder.name) / 'chosen-format.dxf')), 12)
            previous = app.source
            bad = Path(self.folder.name) / 'bad.json'; bad.write_text('{}')
            with patch('scrib3.app.filedialog.askopenfilename', return_value=str(bad)):
                app.import_drawing()
            self.assertTrue(error.called)
            self.assertEqual(app.source, previous)
            error.reset_mock()
            quality = QualityWindow(app); self.windows.append(quality)
            quality.overlap.set(str(.5/25.4))
            quality.join_strokes.set(True)
            quality.reloop.set(False)
            # An already-open quality window keeps its displayed unit even when
            # the main workspace switches units before Apply.
            app.unit_choice.set('Millimeters'); app.change_units()
            quality.apply()
            self.assertAlmostEqual(float(app.seam_overlap.get()), .5)
            self.assertAlmostEqual(presets.load(app.preset_file)['seam_overlap_mm'], .5)
            self.assertTrue(presets.load(app.preset_file)['join_strokes'])
            self.assertFalse(presets.load(app.preset_file)['reloop'])
            quality.overlap.set('99'); quality.apply()
            self.assertIn('between', quality.status.get())
            self.assertAlmostEqual(float(app.seam_overlap.get()), .5)
            app.root.geometry('800x650'); self.root.update()
            for widget, parent in ((app.quality_button, app.canvas.master), (quality.apply_button, quality.window)):
                self.assertTrue(widget.winfo_viewable())
                self.assertLessEqual(widget.winfo_rootx()+widget.winfo_width(), parent.winfo_rootx()+parent.winfo_width())
                self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(), parent.winfo_rooty()+parent.winfo_height())
            self.assertFalse(error.called, error.call_args)

    def test_quality_metrics_overlay_cache_and_compact_workspace(self):
        from math import sin
        from scrib3 import app as app_module
        app = self.app
        app.set_drawing('Dense curve', (tuple((i/20, sin(i/30)) for i in range(1001)),))
        report = app.quality_report
        self.assertEqual(report.before.points, 1001)
        self.assertLess(report.after.points, 1001)
        self.assertEqual(app.metric_points.get(), f'{report.after.points:,}')
        before = app.drawing
        app.show_original.set(True); app.paint()
        self.assertEqual(len(app.canvas.find_withtag('source')), len(app.source))
        self.assertEqual(app.drawing, before)
        with patch.object(app_module, 'prepare_toolpath', wraps=app_module.prepare_toolpath) as process:
            app.refresh(); app.refresh()
            self.assertEqual(process.call_count, 0)
            app.quality_mode.set('Fine'); app.refresh()
            self.assertEqual(process.call_count, 1)
            app.margin.set('0.4'); app.refresh()
            self.assertEqual(process.call_count, 2)
            app.paper_mount.set('bottom_left_x')
            self.assertEqual(process.call_count, 3)
        app.remove_duplicates.set(True); app.refresh()
        app.save_preset()
        saved = presets.load(app.preset_file)
        self.assertEqual(saved['quality_mode'], 'Fine')
        self.assertTrue(saved['remove_duplicates'])
        for geometry in ('1280x820', '800x650'):
            self.root.geometry(geometry); app.tabs.select(0); self.root.update()
            self.assertGreater(app.canvas.winfo_height(), 100)
            for card in app.metric_cards:
                self.assertLessEqual(card.winfo_rootx()+card.winfo_width(),
                                     app.canvas.winfo_rootx()+app.canvas.winfo_width())
                self.assertLess(card.winfo_rooty()+card.winfo_height(), self.root.winfo_rooty()+self.root.winfo_height())
