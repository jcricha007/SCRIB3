"""Asynchronous route comparison with explicit application of improvements."""
from queue import Empty, SimpleQueue
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk

from . import theme
from .route_compare import run_vpype


class RouteWindow:
    def __init__(self, studio):
        self.studio = studio
        self.window = tk.Toplevel(studio.root)
        self.window.title('SCRIB3 | Compare routes')
        self.window.geometry('660x540')
        self.window.minsize(580, 480)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.window.bind('<Destroy>', self.destroyed, add='+')
        self.closed = False
        self.busy = False
        self.result = None
        self.cancel = Event()
        self.events = SimpleQueue()
        self.status = tk.StringVar(value='Compare vpype with the current route. Geometry and pen lifts stay unchanged.')
        panel = ttk.Frame(self.window, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Compare travel routes', style='Title.TLabel').pack(anchor='w')
        ttk.Label(panel, text='Blue lines show pen-up travel from the selected paper origin. '
                  'Only a shorter route can be applied. Changes last for this drawing and layout.',
                  wraplength=540, style='Muted.TLabel').pack(anchor='w', pady=8)
        footer = ttk.Frame(panel)
        footer.pack(side='bottom', fill='x', pady=(10, 0))
        ttk.Label(footer, textvariable=self.status, wraplength=530).pack(anchor='w')
        actions = ttk.Frame(footer)
        actions.pack(fill='x', pady=(10, 0))
        self.compare_button = ttk.Button(actions, text='Compare with vpype', command=self.compare)
        self.compare_button.pack(side='left')
        ttk.Button(actions, text='Cancel', command=self.cancel.set).pack(side='left', padx=6)
        self.apply_button = ttk.Button(actions, text='Apply shorter route', style='Primary.TButton', command=self.apply, state='disabled')
        self.apply_button.pack(side='right')
        ttk.Button(footer, text='Restore built-in route', command=self.restore).pack(anchor='e', pady=(8, 0))
        self.canvas = tk.Canvas(panel, background=theme.DESK, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda _: self.paint())
        self.after_id = self.window.after(80, self.poll)

    def compare(self):
        if self.busy:
            return
        self.result = None
        self.apply_button.state(['disabled'])
        try:
            self.studio.refresh()
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.key = self.studio._toolpath_cache[0]
        self.revision = self.studio.revision
        self.sheet = self.studio.sheet
        self.start = self.key[-1]
        drawing = self.studio.drawing
        self.cancel = Event()
        cancel = self.cancel
        self.busy = True
        self.compare_button.state(['disabled'])
        self.status.set('Comparing routes… You can cancel while the optimizer works.')
        def work():
            try:
                result = run_vpype(drawing, self.start, cancel)
                self.events.put((result, None))
            except Exception as exc:
                self.events.put((None, str(exc)))
        Thread(target=work, daemon=True, name='SCRIB3 route comparison').start()

    def current(self):
        try:
            self.studio.refresh()
            return self.studio.revision == self.revision and self.studio._toolpath_cache[0] == self.key
        except ValueError:
            return False

    def poll(self):
        if self.closed:
            return
        try:
            result, error = self.events.get_nowait()
        except Empty:
            pass
        else:
            self.busy = False
            self.compare_button.state(['!disabled'])
            if self.cancel.is_set():
                self.status.set('Comparison cancelled. The route is unchanged.')
            elif not self.current():
                self.status.set('Drawing or layout changed. Compare again.')
            elif error:
                self.status.set(error)
            else:
                self.result = result
                self.status.set(f'Pen-up travel: {result.before_mm:.2f} → {result.after_mm:.2f} mm. '
                                + ('Ready to apply.' if result.improved else 'Current route is already as short or shorter.'))
                if result.improved:
                    self.apply_button.state(['!disabled'])
                self.paint()
        self.after_id = self.window.after(80, self.poll)

    def paint(self):
        self.canvas.delete('all')
        if self.result is None:
            return
        w, h = max(80, self.canvas.winfo_width()), max(80, self.canvas.winfo_height())
        scale = min((w-24)/self.sheet.width, (h-24)/self.sheet.height)
        xy = lambda p: (12+p[0]*scale, h-12-p[1]*scale)
        position = self.start
        for stroke in self.result.drawing:
            self.canvas.create_line(*xy(position), *xy(stroke[0]), fill='#718fb5', dash=(3, 3))
            self.canvas.create_line(*(v for p in stroke for v in xy(p)), fill='#172033')
            position = stroke[-1]

    def apply(self):
        if self.result is None or not self.result.improved:
            return
        if not self.current():
            self.result = None
            self.apply_button.state(['disabled'])
            self.status.set('Drawing or layout changed. Compare again.')
            return
        self.studio.route_override = (self.key, self.result.drawing)
        self.studio.revision += 1
        self.studio.refresh()
        self.apply_button.state(['disabled'])
        self.status.set('Shorter route applied. Review G-code again before plotting.')

    def restore(self):
        self.cancel.set()
        self.studio.route_override = None
        self.studio.revision += 1
        self.result = None
        self.apply_button.state(['disabled'])
        try:
            self.studio.refresh()
            self.status.set('Built-in route restored.')
        except ValueError as exc:
            self.status.set(str(exc))
        self.paint()

    def destroyed(self, event):
        if event.widget == self.window:
            self.closed = True
            self.cancel.set()

    def close(self):
        self.closed = True
        self.cancel.set()
        self.window.after_cancel(self.after_id)
        self.window.destroy()
