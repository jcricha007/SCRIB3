"""Operator-applied motion starting values and physical paper orientation."""
import tkinter as tk
from tkinter import ttk

from .units import display, setting_display, to_mm
from .paper_mount import MOUNTS, origin_corner, required_travel

DRAW_FEED = 3000.0
TRAVEL_FEED = 8890.0  # John's tested 350 in/min rapid-travel baseline.
JOG_FEED = 150.0
SMOOTH_SETTINGS = {11: .020, 110: TRAVEL_FEED, 111: TRAVEL_FEED, 120: 25.0, 121: 25.0}
PAPER_SIZES = {
    'US Letter portrait': (215.9, 279.4),
    'US Letter landscape': (279.4, 215.9),
    'A4 portrait': (210.0, 297.0),
    'A4 landscape': (297.0, 210.0),
}


class MotionDefaultsWindow:
    def __init__(self, studio):
        self.studio, self.session = studio, studio.controls.session
        self.pending = None
        self.window = tk.Toplevel(studio.root)
        self.window.title('SCRIB3 | Smooth motion starting values')
        self.window.geometry('610x470')
        self.window.minsize(610, 470)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        panel = ttk.Frame(self.window, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Smooth motion starting values', style='Title.TLabel').pack(anchor='w')
        ttk.Label(panel, text='The runner keeps XY segments in the motion planner. Check the updated run speed with a pen-up test on your machine.',
                  wraplength=570).pack(anchor='w', pady=8)
        unit = self.unit = studio.unit
        ttk.Label(panel, text=f'Draw: {display(DRAW_FEED, unit)} {unit}/min   |   Jog: {display(JOG_FEED, unit)} {unit}/min',
                  wraplength=570).pack(anchor='w', pady=6)
        grid = ttk.Frame(panel)
        grid.pack(fill='x', pady=4)
        self.current = self.session.snapshot()['settings'] if self.session else {}
        self.current_labels = {}
        for column, title in enumerate(('Controller setting', 'Current', f'Proposed ({unit})')):
            ttk.Label(grid, text=title).grid(row=0, column=column, sticky='w', padx=(0, 20))
        for row, (number, name, suffix) in enumerate(((110, 'X maximum rate', '/min'), (111, 'Y maximum rate', '/min'),
                (120, 'X acceleration', '/s²'), (121, 'Y acceleration', '/s²'), (11, 'Junction deviation', '')), 1):
            current = self.current.get(number)
            values = (f'${number} {name}', 'Not read' if current is None else f'{setting_display(number, current, unit):.4g}',
                      f'{setting_display(number, SMOOTH_SETTINGS[number], unit):.4g} {unit}{suffix}')
            for column, value in enumerate(values):
                label = ttk.Label(grid, text=value)
                label.grid(row=row, column=column, sticky='w', pady=4, padx=(0, 20))
                if column == 1:
                    self.current_labels[number] = label
        ttk.Label(panel, text='Apply changes only speed, acceleration, and junction deviation. Your steps/mm, axis direction, travel limits, home, and pen positions stay as configured.',
                  wraplength=570, style='Muted.TLabel').pack(anchor='w', pady=8)
        self.status = tk.StringVar(value='Controller writes occur only when you choose Apply app + controller.')
        ttk.Label(panel, textvariable=self.status, wraplength=570).pack(anchor='w', pady=8)
        actions = ttk.Frame(panel)
        actions.pack(side='bottom', fill='x')
        self.app_button = ttk.Button(actions, text='Use app speeds only', command=self.apply_app)
        self.app_button.pack(side='left')
        self.apply_button = ttk.Button(actions, text='Apply app + controller', command=self.apply_controller)
        self.apply_button.pack(side='right')
        self.after_id = self.window.after(80, self.poll)

    def apply_app(self):
        if self.pending:
            return
        self.studio.feed.set(display(DRAW_FEED, self.studio.unit))
        self.studio.controls.rate.set(display(JOG_FEED, self.studio.unit))
        saved = self.studio.save_preset()
        self.status.set('App speeds saved. Review G-code again before running.' if saved else
                        'App speeds changed, but saving failed. Correct the preset fields and save again.')

    def apply_controller(self):
        try:
            if self.session is None or self.studio.controls.session is not self.session:
                raise ValueError('Connect and reopen this window for the current Arduino.')
            snap = self.session.snapshot()
            if not snap['connected'] or snap['busy'] or snap['state'] != 'Idle' or not snap['fresh'] or snap['reset_required']:
                raise ValueError('Wait for Idle. Resolve any pending calibration reset first.')
            if snap['settings'] != self.current:
                raise ValueError('Controller settings changed. Reopen this window before applying.')
            self.pending = self.session.request('settings', values=SMOOTH_SETTINGS)
            self.status.set('Writing motion settings and checking readback…')
        except ValueError as exc:
            self.status.set(str(exc))

    def poll(self):
        if self.pending:
            snap = self.session.snapshot()
            result = snap['last_result']
            if not snap['connected']:
                self.pending = None
                self.status.set('Disconnected during setup. Read actual settings before retrying; app speeds were not changed.')
            elif result and result[0] == self.pending and not snap['busy']:
                self.pending = None
                if result[2]:
                    self.status.set(result[2])
                else:
                    self.current = snap['settings']
                    for number, label in self.current_labels.items():
                        label.configure(text=f'{setting_display(number, self.current[number], self.unit):.4g}')
                    self.apply_app()
                    self.status.set('Controller readback verified. ' + self.status.get())
        self.app_button.state(['disabled'] if self.pending else ['!disabled'])
        self.apply_button.state(['disabled'] if self.pending or self.session is None else ['!disabled'])
        self.after_id = self.window.after(80, self.poll)

    def close(self):
        if self.pending:
            self.window.iconify()
        else:
            self.window.after_cancel(self.after_id)
            self.window.destroy()


class PaperGuideWindow:
    def __init__(self, studio):
        self.studio = studio
        self.window = tk.Toplevel(studio.root)
        self.window.title('SCRIB3 | Paper and starting position')
        self.window.geometry('660x740')
        self.window.minsize(620, 700)
        panel = ttk.Frame(self.window, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Paper and starting position', style='Title.TLabel').pack(anchor='w')
        self.choice = tk.StringVar(value='US Letter landscape')
        for name, (width, height) in PAPER_SIZES.items():
            if abs(studio.sheet.width-width) < .01 and abs(studio.sheet.height-height) < .01:
                self.choice.set(name)
        select = ttk.Combobox(panel, textvariable=self.choice, values=tuple(PAPER_SIZES), state='readonly')
        select.pack(fill='x', pady=8)
        select.bind('<<ComboboxSelected>>', lambda _: self.paint())
        self.mount = tk.StringVar(value=MOUNTS[studio.paper_mount.get()])
        mount_picker = ttk.Combobox(panel, textvariable=self.mount, values=tuple(MOUNTS.values()), state='readonly')
        mount_picker.pack(fill='x', pady=(0, 8))
        mount_picker.bind('<<ComboboxSelected>>', lambda _: self.paint())
        footer = ttk.Frame(panel)
        footer.pack(side='bottom', fill='x')
        self.status = tk.StringVar()
        ttk.Label(footer, textvariable=self.status, wraplength=520).pack(anchor='w', pady=8)
        self.instructions = tk.StringVar()
        ttk.Label(footer, textvariable=self.instructions, wraplength=570).pack(anchor='w', pady=8)
        ttk.Button(footer, text="Use John's Letter setup", command=self.use_john).pack(fill='x', pady=(0, 5))
        ttk.Button(footer, text='Apply and save paper setup', command=self.apply).pack(fill='x')
        self.canvas = tk.Canvas(panel, background='#e4e9e1', highlightthickness=0, height=300)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _: self.paint())

    def mount_code(self):
        return next(code for code, label in MOUNTS.items() if label == self.mount.get())

    def use_john(self):
        self.choice.set('US Letter landscape')
        self.mount.set(MOUNTS['top_left_y'])
        self.apply()

    def paint(self):
        width, height = PAPER_SIZES[self.choice.get()]
        mount = self.mount_code()
        john = mount == 'top_left_y'
        canvas = self.canvas
        canvas.delete('all')
        cw, ch = max(200, canvas.winfo_width()), max(250, canvas.winfo_height())
        scale = min((cw-130)/width, (ch-110)/height)
        left, bottom = (cw-width*scale)/2, ch-48
        right, top = left+width*scale, bottom-height*scale
        canvas.create_rectangle(left, top, right, bottom, fill='#fffef8', outline='#555e54')
        margin = 12.7*scale
        canvas.create_rectangle(left+margin, top+margin, right-margin, bottom-margin, dash=(4, 4), outline='#598676')
        canvas.create_text((left+right)/2, bottom+31, text=f'{"Y" if john else "X"} width: {width/25.4:.3g} in', fill='#262a25')
        canvas.create_text(left-28, (top+bottom)/2, text=f'{"X" if john else "Y"} height: {height/25.4:.3g} in', angle=90, fill='#262a25')
        canvas.create_line(left, bottom+12, right, bottom+12, arrow='last', fill='#245849', width=2)
        canvas.create_text(right+6, bottom+12, text='+Y' if john else '+X', anchor='w', fill='#262a25')
        canvas.create_line(right+20, top if john else bottom, right+20, bottom if john else top, arrow='last', fill='#245849', width=2)
        canvas.create_text(right+20, top-12, text='-X' if john else '+Y', fill='#262a25')
        origin_y = top if john else bottom
        canvas.create_oval(left-5, origin_y-5, left+5, origin_y+5, fill='#245849', outline='')
        canvas.create_text(left, top-28, text=f'START: {origin_corner(mount)} corner (0, 0), pen up', anchor='w', fill='#262a25')
        canvas.create_text((left+right)/2, (top+bottom)/2, text='Top view\n0.5-inch margin', fill='#555e54')
        try:
            x_travel, y_travel = required_travel(width, height, mount)
            fits = to_mm(self.studio.machine_width.get(), self.studio.unit) >= x_travel-.001 and to_mm(self.studio.machine_height.get(), self.studio.unit) >= y_travel-.001
        except ValueError:
            fits = False
        self.status.set('Fits configured travel. Confirm clearance from the selected corner in the drawing directions.' if fits else
                        'Full sheet exceeds or lacks configured travel. Measure usable travel first; paper size does not establish machine limits.')
        direction = '+Y moves right; -X moves down. Drawings extend into +Y and -X.' if john else '+X moves right; +Y moves up.'
        self.instructions.set(f'Tape the sheet flat. Raise the pen, jog to the {origin_corner(mount)} paper corner, then click Control > Set home (or Paper XY zero). {direction} Re-establish zero after applying this setup.')

    def apply(self):
        session = self.studio.controls.session
        if session and session.snapshot()['busy']:
            self.status.set('Wait for the current controller operation to finish before applying paper setup.')
            return
        width, height = PAPER_SIZES[self.choice.get()]
        self.studio.paper_width.set(display(width, self.studio.unit))
        self.studio.paper_height.set(display(height, self.studio.unit))
        self.studio.margin.set(display(12.7, self.studio.unit))
        self.studio.paper_mount.set(self.mount_code())
        self.studio.apply_layout()
        if self.studio.save_preset():
            self.studio.status.set('Paper setup saved. Raise the pen and set home at the selected paper corner before reviewing a run.')
        self.paint()
