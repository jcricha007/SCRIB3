import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import patch

from test_controller import FakeSerial
from scrib3.app import Studio
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
        def cleanup():
            if getattr(self, 'panel', None) and self.panel.session:
                self.panel.session.close()
                self.panel.session.thread.join(2)
            try:
                root.destroy()
            except tk.TclError:
                pass
        self.addCleanup(cleanup)
        errors = []
        root.report_callback_exception = lambda *args: errors.append(str(args))
        peer = FakeSerial()
        with patch.object(controls, 'Controller', side_effect=lambda port, baud: Controller(port, baud, serial_factory=lambda *a, **k: peer)), patch.object(controls, 'detect', return_value=Device('COM7', 115200, 'GRBL')), patch.object(controls.messagebox, 'showerror', side_effect=lambda *a, **k: errors.append(str(a))):
            studio = Studio(root, preset_file=preset_file)
            panel = self.panel = studio.controls
            studio.tabs.select(panel)
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
            panel.buttons['Auto detect'].invoke()
            wait(lambda: panel.session is not None and panel.session.snapshot()['connected'])
            assert studio.baud.get() == '115200' and studio.port.get() == 'COM7'
            assert panel.buttons['Connect'].instate(['disabled'])
            assert '0.3543' in panel.position_text.get()
            assert studio.unit == 'in'
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
            apply = next(w for w in descendants(dialog) if w.winfo_class() == 'TButton')
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
            studio.firmware.set(SERVO_PROFILE)
            studio.pen_up.set('M3 S180'); studio.pen_down.set('M3 S70')
            panel.buttons['Pen down'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            panel.buttons['Pen up'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            assert b'M3 S180.000\n' in peer.writes and b'M3 S70.000\n' in peer.writes
            panel.copy_travel()
            assert studio.machine_width.get() == '200'
            panel.buttons['Read GRBL'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel):
                    w.destroy()
            studio.unit_choice.set('Inches')
            studio.change_units()
            with patch.object(studio, 'text_dialog', wraps=studio.text_dialog) as review:
                studio.review()
                assert 'G20 G90' in review.call_args.args[1]
                assert 'M3 S180.000' in review.call_args.args[1]
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel):
                    w.destroy()
            studio.save_preset()
            saved = presets.read(preset_file)
            assert saved['units'] == 'in' and saved['pen_down'] == 'M3 S70'
            assert abs(saved['machine_width_mm'] - 200) < .00001
            for geometry, image in [('1120x740', 'control-desktop.png'), ('800x650', 'control-small.png')]:
                root.geometry(geometry)
                root.update()
                for name, button in panel.buttons.items():
                    assert button.winfo_rooty() + button.winfo_height() <= panel.winfo_rooty() + panel.winfo_height() - 2, name
                    assert button.winfo_rootx() + button.winfo_width() <= root.winfo_rootx() + root.winfo_width(), name

            assert not errors, errors
            panel.shutdown()
            while panel.session.thread.is_alive():
                root.update(); sleep(.01)
            assert peer.closed
            root.destroy()
            root = tk.Tk()
            studio = Studio(root, preset_file=preset_file)
            self.panel = studio.controls
            assert studio.unit == 'in' and studio.pen_up.get() == 'M3 S180'
            assert studio.pen_down.get() == 'M3 S70'
            assert self.panel.session is None
            assert abs(to_mm(studio.machine_width.get(), studio.unit) - 200) < .00001
            root.destroy()
