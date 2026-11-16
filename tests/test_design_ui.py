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
from test_controller import FakeSerial


@skipUnless(os.environ.get('SCRIB3_DESKTOP_TESTS') == '1', 'Desktop display required')
class DesignDesktopTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.root = tk.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(str(args))
        self.app = Studio(self.root, preset_file=Path(self.folder.name) / 'prefs.json')
        self.windows = []
        self.root.update()

    def tearDown(self):
        for window in self.windows:
            if not window.closed:
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
        with patch.object(controls, 'Controller', side_effect=lambda *a: Controller(*a, serial_factory=lambda *a, **k: peer)):
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
        with patch.object(controls, 'Controller', side_effect=lambda *a: Controller(*a, serial_factory=lambda *a, **k: peer)), patch('scrib3.app.messagebox.showerror') as error:
            app, panel = self.app, self.app.controls
            app.port.set('COM7'); panel.connect()
            self.wait(lambda: panel.session.snapshot()['connected'])
            self.settle()
            app.unit_choice.set('Millimeters'); app.change_units()
            app.paper_width.set('10'); app.paper_height.set('10'); app.margin.set('1')
            app.machine_width.set('10'); app.machine_height.set('10'); app.feed.set('60')
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
            app.feed.set('61')
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
