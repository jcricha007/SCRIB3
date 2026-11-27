import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import patch

from test_controller import FakeSerial
from scrib3.app import Studio
from scrib3.board import Mark
from scrib3.controller import Controller
from scrib3.discovery import Device
from scrib3.firmware import SERVO_PROFILE
from scrib3 import controls, presets
from scrib3.units import to_mm


@skipUnless(os.environ.get("SCRIB3_DESKTOP_TESTS") == "1", "Set SCRIB3_DESKTOP_TESTS=1 with a display to run desktop checks")
class DesktopTests(TestCase):
    def test_setup_and_motion_controls_with_simulated_arduino(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        preset_file = Path(folder.name) / "prefs.json"
        root = tk.Tk()
        def destroy_root():
            for callback in root.tk.call('after', 'info'):
                root.tk.call('after', 'cancel', callback)
            root.destroy()
        def cleanup():
            if getattr(self, 'panel', None) and self.panel.session:
                self.panel.session.close()
                self.panel.session.thread.join(2)
            try:
                destroy_root()
            except tk.TclError:
                pass
        self.addCleanup(cleanup)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args))
        peer = FakeSerial()
        verification_started, finish_verification = Event(), Event()
        self.addCleanup(finish_verification.set)
        operate = Controller._operate
        def pause_verification(session, kind, values):
            if kind == 'settings' and values.get('automatic'):
                verification_started.set()
                if not finish_verification.wait(8):
                    raise ValueError('Test did not release simulated verification.')
            return operate(session, kind, values)

        def layout_fits(panel):
            for geometry in ('1120x740', '800x650'):
                root.geometry(geometry)
                root.update()
                for name, button in panel.buttons.items():
                    assert button.winfo_rooty() + button.winfo_height() <= panel.winfo_rooty() + panel.winfo_height() - 2, name
                    assert button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width(), name

        with patch.object(Controller, '_operate', pause_verification), patch.object(controls, 'Controller', side_effect=lambda port, baud, **kw: Controller(port, baud, **kw, serial_factory=lambda *a, **k: peer)), patch.object(controls, 'detect', return_value=Device('COM7', 115200, 'GRBL')), patch.object(controls.messagebox, 'showerror', side_effect=lambda *a, **k: errors.append(str(a))):
            studio = Studio(root, preset_file=preset_file)
            # This control regression uses the original small test sheet.
            studio.paper_width.set(str(148/25.4)); studio.paper_height.set(str(105/25.4))
            studio.margin.set(str(7/25.4)); studio.refresh()
            panel = self.panel = studio.controls
            assert studio.tabs.select() == str(panel)
            def wait(predicate, timeout=5):
                deadline = monotonic() + timeout
                while monotonic() < deadline:
                    root.update()
                    if predicate():
                        # Allow a complete UI polling cycle after a worker transition.
                        until = monotonic() + .12
                        while monotonic() < until:
                            root.update(); sleep(.005)
                        return
                    sleep(.005)
                raise AssertionError('Desktop condition timed out')
            root.update()
            assert panel.state_text.get() == 'Disconnected'
            panel.buttons['Auto detect'].invoke()
            wait(verification_started.is_set)
            assert not panel.session.snapshot()['connected']
            assert panel.state_text.get() == 'Verifying motion setup'
            assert 'readback' in panel.readiness_text.get()
            assert panel.buttons['Reset / abort'].winfo_ismapped()
            assert panel.buttons['X +'].instate(['disabled'])
            layout_fits(panel)
            finish_verification.set()
            wait(lambda: panel.session is not None and panel.session.snapshot()['connected'])
            assert studio.baud.get() == '115200' and studio.port.get() == 'COM7'
            assert panel.buttons['Connect'].instate(['disabled'])
            assert '0.3543' in panel.position_text.get()
            assert studio.unit == 'in'
            assert abs(to_mm(studio.feed.get(), studio.unit) - 1500) < 0.00001
            assert peer.settings[110] == 1500 and peer.settings[111] == 1500
            assert not panel.session.snapshot()['motion_defaults_pending']
            assert panel.state_text.get() == 'Idle · paper origin not set'
            assert (studio.pen_up.get(), studio.pen_down.get()) == ('M3 S180', 'M3 S70')
            assert panel.buttons['Home'].instate(['disabled'])
            assert panel.buttons['Go to manual home'].instate(['disabled'])
            panel.buttons['Set manual home'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            assert panel.session.snapshot()['manual_home'] == (10, 20)
            panel.buttons['Go to manual home'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            assert panel.session.snapshot()['state'] == 'Jog'
            panel.buttons['Cancel jog'].invoke()
            wait(lambda: panel.session.snapshot()['state'] == 'Idle')
            # Invalid entries cannot be silently relabeled into a different unit.
            studio.feed.set('bad')
            before = [v.get() for v in studio.dimension_fields().values()]
            studio.unit_choice.set('Millimeters')
            studio.change_units()
            assert studio.unit == 'in'
            assert [v.get() for v in studio.dimension_fields().values()] == before
            assert len(errors) == 1
            errors.clear()
            studio.feed.set('4')
            writes = [w for w in peer.writes if w != b'?']
            for choice in ('Millimeters', 'Inches') * 5 + ('Millimeters',):
                studio.unit_choice.set(choice)
                studio.change_units()
            assert [w for w in peer.writes if w != b'?'] == writes
            assert abs(float(studio.paper_width.get()) - 148) < .00001
            assert abs(float(panel.step.get()) - .254) < .00001
            assert (studio.pen_up.get(), studio.pen_down.get()) == ('M3 S180', 'M3 S70')
            panel.buttons['Setup…'].invoke()
            root.update()
            dialog = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel))
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            label = next(w for w in descendants(dialog) if w.winfo_class() == 'TLabel' and str(w.cget('text')).startswith('$22 '))
            entry = next(w for w in label.master.grid_slaves(row=label.grid_info()['row']) if w.winfo_class() == 'TEntry')
            entry.delete(0, 'end'); entry.insert(0, '1')
            apply = next(w for w in descendants(dialog) if w.winfo_class() == 'TButton' and w.cget('text') == 'Apply changed settings')
            apply.invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            assert peer.settings[22] == 1
            panel.buttons['Home'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            assert b'$H\n' in peer.writes
            panel.buttons['X +'].invoke()
            wait(lambda: panel.session.snapshot()['state'] == 'Jog' and not panel.session.snapshot()['busy'])
            assert panel.buttons['X +'].instate(['disabled'])
            panel.buttons['Cancel jog'].invoke()
            wait(lambda: panel.session.snapshot()['state'] == 'Idle')
            panel.buttons['Set paper XY zero'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            assert panel.session.snapshot()['work'] == (0, 0, 0)
            assert panel.state_text.get() == 'Idle · paper origin set'
            session = panel.session
            reference = session.snapshot()
            writes = [w for w in peer.writes if w != b'?']
            studio.show_board()
            root.update()
            editor = studio.board_editor
            assert editor.winfo_toplevel() != panel.winfo_toplevel()
            assert editor.winfo_viewable() and panel.winfo_viewable()
            line = Mark(editor.pen.get(), ((3, 3), (13, 3)))
            editor.insert((line,), placed=True)
            root.update()
            assert '1 path  ' in studio.monitor_summary.get()
            studio.hide_board()
            root.update()
            assert not editor.winfo_viewable() and panel.winfo_viewable()
            studio.show_board()
            root.update()
            assert studio.board_editor is editor and editor.board.marks == (line,)
            assert panel.session is session and session.snapshot()['connected']
            for field in ('origin_set', 'work', 'reference', 'manual_home'):
                assert session.snapshot()[field] == reference[field]
            assert [w for w in peer.writes if w != b'?'] == writes
            studio.hide_board()
            studio.firmware.set(SERVO_PROFILE)
            studio.pen_up.set('M3 S180'); studio.pen_down.set('M3 S70')
            panel.buttons['Pen down'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            panel.buttons['Pen up'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            assert b'M3 S180.000\n' in peer.writes and b'M3 S70.000\n' in peer.writes
            machine_labels = {str(w.cget('text')) for w in descendants(studio.motion_defaults_button.master)
                              if w.winfo_class() in ('TLabel', 'TButton')}
            assert not any(label.startswith(('Usable X', 'Usable Y', 'Use controller travel')) for label in machine_labels)
            assert studio.travel_limits() == (200, 200)
            panel.buttons['Read GRBL'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel) and w is not studio.board_window:
                    w.destroy()
            studio.unit_choice.set('Inches')
            studio.change_units()
            with patch.object(studio, 'text_dialog', wraps=studio.text_dialog) as review:
                studio.review()
                assert 'G20 G90' in review.call_args.args[1]
                assert 'M3 S180.000' in review.call_args.args[1]
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel) and w is not studio.board_window:
                    w.destroy()
            studio.auto_motion_defaults.set(False)
            studio.save_preset()
            saved = presets.read(preset_file)
            assert saved['units'] == 'in' and saved['pen_down'] == 'M3 S70'
            assert (saved['machine_width_mm'], saved['machine_height_mm']) == (200, 200)
            assert not any(w.startswith((b'$130=', b'$131=')) for w in peer.writes)
            layout_fits(panel)

            assert not errors, errors
            panel.shutdown()
            while panel.session.thread.is_alive():
                root.update(); sleep(.01)
            assert peer.closed
            destroy_root()
            root = tk.Tk()
            studio = Studio(root, preset_file=preset_file)
            self.panel = studio.controls
            assert studio.unit == 'in' and studio.pen_up.get() == 'M3 S180'
            assert studio.pen_down.get() == 'M3 S70'
            assert self.panel.session is None
            assert not studio.auto_motion_defaults.get()
            assert abs(float(studio.feed.get()) - 4) < .00001
            assert studio.travel_limits() == (200, 200)
            destroy_root()
