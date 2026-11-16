import os
from time import monotonic, sleep
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import patch

from test_controller import FakeSerial
from scrib3.app import Studio
from scrib3.controller import Controller
from scrib3.discovery import Device
from scrib3.firmware import SERVO_PROFILE
from scrib3 import controls


@skipUnless(os.environ.get("SCRIB3_DESKTOP_TESTS") == "1", "Set SCRIB3_DESKTOP_TESTS=1 with a display to run desktop checks")
class DesktopTests(TestCase):
    def test_setup_and_motion_controls_with_simulated_arduino(self):
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
            studio = Studio(root)
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
            assert '9.000' in panel.position_text.get()
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
            studio.pen_up.set('M5'); studio.pen_down.set('M3 S100')
            panel.buttons['Pen down'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            panel.buttons['Pen up'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            assert b'M3 S100.000\n' in peer.writes and b'M5\n' in peer.writes
            panel.copy_travel()
            assert studio.machine_width.get() == '200'
            panel.buttons['Read GRBL'].invoke()
            wait(lambda: not panel.session.snapshot()['busy'])
            for w in root.winfo_children():
                if isinstance(w, tk.Toplevel):
                    w.destroy()
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
