"""Operator-measured calibration. No physical distance is inferred from step counts."""
from time import monotonic
import tkinter as tk
from tkinter import ttk

from .calibration import corrected_steps
from .firmware import SERVO_PROFILE
from .units import display, to_mm


class CalibrationWindow:
    def __init__(self, panel):
        self.panel, self.studio, self.session = panel, panel.studio, panel.session
        self.unit = self.studio.unit
        self.window = tk.Toplevel(self.studio.root)
        self.window.title('SCRIB3 | Guided travel calibration')
        self.window.geometry('620x650')
        self.window.minsize(600, 650)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.pending = None
        self.measurement = None
        self.applying = None
        self.closed = False
        self.axis = tk.StringVar(value='X')
        self.direction = tk.StringVar(value='+')
        self.distance = tk.StringVar(value=display(2.54, self.unit))
        self.measured = tk.StringVar()
        self.summary = tk.StringVar()
        self.status = tk.StringVar(value='Read the starting settings below. Measure each axis independently.')
        frame = ttk.Frame(self.window, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Calibrate physical travel', style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='The app moves one axis with the pen raised. Measure its actual travel with a ruler or caliper, then enter that distance.',
                  wraplength=550).pack(anchor='w', pady=8)
        ttk.Label(frame, textvariable=self.summary, wraplength=550, style='Muted.TLabel').pack(anchor='w')
        self.preset_button = ttk.Button(frame, text='Apply saved X/Y starting calibration', command=self.apply_preset)
        self.preset_button.pack(fill='x', pady=8)
        ttk.Label(frame, text='After applying steps/mm: use Control → Reset / abort, reconnect, then reopen this guide. Reset can lower the servo; keep the pen tip clear.',
                  wraplength=550, style='Muted.TLabel').pack(anchor='w')
        ttk.Separator(frame).pack(fill='x', pady=12)
        fields = ttk.Frame(frame)
        fields.pack(fill='x')
        ttk.Label(fields, text='Axis / direction').grid(row=0, column=0, sticky='w', pady=4)
        ttk.Combobox(fields, textvariable=self.axis, values=('X', 'Y'), state='readonly', width=5).grid(row=0, column=1)
        ttk.Combobox(fields, textvariable=self.direction, values=('+', '-'), state='readonly', width=5).grid(row=0, column=2)
        ttk.Label(fields, text=f'Requested distance ({self.unit})').grid(row=1, column=0, sticky='w', pady=4)
        ttk.Entry(fields, textvariable=self.distance, width=14).grid(row=1, column=1, columnspan=2, sticky='ew')
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x', pady=8)
        self.test_button = ttk.Button(buttons, text='Raise pen + test move', command=self.test_move)
        self.test_button.pack(side='left')
        self.cancel_button = ttk.Button(buttons, text='Cancel test', command=self.cancel_test)
        self.cancel_button.pack(side='left', padx=8)
        ttk.Label(frame, text='Choose a direction with clear space. Test moves are limited to 10 mm at 25 mm/min.',
                  wraplength=550, style='Muted.TLabel').pack(anchor='w')
        measured = ttk.Frame(frame)
        measured.pack(fill='x', pady=12)
        ttk.Label(measured, text=f'Actual measured travel ({self.unit})').pack(side='left')
        ttk.Entry(measured, textvariable=self.measured, width=14).pack(side='left', padx=10)
        self.calculate_button = ttk.Button(frame, text='Calculate correction', command=self.calculate)
        self.calculate_button.pack(anchor='w')
        self.correction = tk.StringVar(value='Complete a test move before calculating.')
        ttk.Label(frame, textvariable=self.correction, wraplength=550).pack(anchor='w', pady=8)
        self.apply_button = ttk.Button(frame, text='Apply measured correction', command=self.apply_correction)
        self.apply_button.pack(anchor='w')
        ttk.Label(frame, textvariable=self.status, wraplength=550, style='Muted.TLabel').pack(anchor='w', pady=10)
        self.after_id = self.window.after(80, self.poll)

    def snapshot(self):
        if self.panel.session is not self.session or self.session is None:
            raise ValueError('Connection changed. Close and reopen calibration.')
        snap = self.session.snapshot()
        if not snap['connected'] or not snap['fresh']:
            raise ValueError('Connect to a responding controller, then reopen calibration.')
        return snap

    def ready(self):
        snap = self.snapshot()
        if snap['busy'] or snap['state'] != 'Idle':
            raise ValueError('Wait for the controller to be Idle.')
        if snap['reset_required']:
            raise ValueError('Reset / abort and reconnect before testing the new calibration.')
        if snap['machine'] is None:
            raise ValueError('Wait for machine coordinates.')
        return snap

    def apply_preset(self):
        try:
            snap = self.ready()
            changes = {n: self.studio.calibration[n] for n in (100, 101)
                       if snap['settings'].get(n) != self.studio.calibration[n]}
            if not changes:
                self.status.set('Controller already matches the saved starting calibration.')
                return
            self.measurement = None
            self.applying = self.session.request('settings', values=changes)
            self.status.set('Writing starting calibration. Wait for readback, then reset and reconnect.')
        except ValueError as exc:
            self.status.set(str(exc))

    def test_move(self):
        try:
            snap = self.ready()
            if any(abs(snap['settings'][n] - self.studio.calibration[n]) > .0005 for n in (100, 101)):
                raise ValueError('Apply the saved starting calibration, reset, and reconnect before testing.')
            axis = self.axis.get()
            distance = to_mm(self.distance.get(), self.unit)
            if axis not in ('X', 'Y') or not .1 <= distance <= 10:
                raise ValueError('Choose X or Y and a test distance from 0.1 to 10 mm (0.00394 to 0.39370 in).')
            signed = distance if self.direction.get() == '+' else -distance
            operation = self.session.request('calibration_jog', axis=axis, distance=signed, feed=25,
                command=self.studio.pen_up.get(), servo=self.studio.firmware.get() == SERVO_PROFILE,
                settle=self.studio.settle.get())
            self.pending = dict(operation=operation, axis=axis, distance=round(signed, 3),
                                before=snap['machine'], steps=snap['settings'][100 if axis == 'X' else 101],
                                started=monotonic())
            self.measurement = None
            self.measured.set('')
            self.correction.set('Waiting for the test move to finish…')
            self.status.set('Test moving. Wait for Idle, then measure the physical distance.')
        except ValueError as exc:
            self.status.set(str(exc))

    def cancel_test(self):
        if self.pending:
            self.session.cancel_jog()
            self.pending = None
            self.measurement = None
            self.status.set('Test cancelled. Its measurement cannot be applied.')

    def candidate(self):
        snap = self.ready()
        test = self.measurement
        if test is None:
            raise ValueError('Complete an uninterrupted test move first.')
        n = 100 if test['axis'] == 'X' else 101
        if snap['settings'][n] != test['steps'] or snap['machine'] != test['after']:
            raise ValueError('Position or calibration changed after the test. Repeat the test before applying.')
        measured = to_mm(self.measured.get(), self.unit)
        value = corrected_steps(test['steps'], test['effective'], measured)
        return n, value

    def calculate(self):
        try:
            n, value = self.candidate()
            self.correction.set(f'${n}: {value:g} steps/mm ({value*25.4:g} steps/in). Apply writes this axis only.')
        except ValueError as exc:
            self.status.set(str(exc))

    def apply_correction(self):
        try:
            n, value = self.candidate()
            if value == self.session.snapshot()['settings'][n]:
                self.status.set('Measured travel matches the current calibration at controller precision. Check the other axis next.')
                return
            self.applying = self.session.request('settings', values={n: value})
            self.measurement = None
            self.status.set('Writing correction. Wait for readback, then reset and reconnect; repeat the test to verify.')
        except ValueError as exc:
            self.status.set(str(exc))

    def poll(self):
        if self.closed:
            return
        try:
            snap = self.snapshot()
            steps = snap['settings']
            self.summary.set(f"Controller: X {steps.get(100, 0):g}, Y {steps.get(101, 0):g} steps/mm. "
                             f"Saved starting values: X {self.studio.calibration[100]:g}, Y {self.studio.calibration[101]:g} steps/mm.")
            result = snap['last_result']
            if self.applying and result and result[0] == self.applying and not snap['busy']:
                self.applying = None
                if result[2]:
                    self.status.set(result[2])
                else:
                    self.studio.calibration = {n: steps[n] for n in (100, 101)}
                    self.studio.save_preset()
                    self.status.set('Calibration read back. Reset / abort, reconnect, and reopen this guide to verify travel.')
            if self.pending:
                test = self.pending
                if monotonic() - test['started'] > 90:
                    self.cancel_test()
                    self.status.set('Test timed out and was cancelled. Reconnect and inspect the controller before retrying.')
                elif result and result[0] == test['operation'] and not snap['busy']:
                    if result[2]:
                        self.pending = None
                        self.status.set(result[2])
                    elif snap['state'] == 'Idle' and snap['machine'] is not None:
                        self.pending = None
                        index = 0 if test['axis'] == 'X' else 1
                        actual = snap['machine'][index] - test['before'][index]
                        if abs(actual-test['distance']) > max(.002, 1/test['steps']) or actual * test['distance'] <= 0:
                            self.status.set('Test did not reach its commanded position. Repeat an uninterrupted test.')
                        else:
                            self.measurement = test | {'after': snap['machine'], 'effective': abs(actual)}
                            self.correction.set(f"Controller distance: {display(abs(actual), self.unit)} {self.unit} (includes step rounding).")
                            self.status.set(f"Measure actual {test['axis']} travel, enter it in {self.unit}, and calculate the correction.")
            ready = not snap['busy'] and snap['state'] == 'Idle' and not snap['reset_required'] and not self.pending and not self.applying
        except ValueError as exc:
            ready = False
            self.pending = self.measurement = None
            self.status.set(str(exc))
        for button in (self.preset_button, self.test_button):
            button.state(['!disabled'] if ready else ['disabled'])
        for button in (self.calculate_button, self.apply_button):
            button.state(['!disabled'] if ready and self.measurement else ['disabled'])
        self.cancel_button.state(['!disabled'] if self.pending else ['disabled'])
        self.after_id = self.window.after(80, self.poll)

    def close(self):
        self.cancel_test()
        self.closed = True
        self.window.after_cancel(self.after_id)
        self.window.destroy()
