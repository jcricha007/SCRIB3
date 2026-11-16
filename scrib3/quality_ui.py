"""Per-preset seam treatment for closed pen paths."""
import tkinter as tk
from tkinter import ttk

from .units import display, to_mm


class QualityWindow:
    def __init__(self, studio):
        self.studio = studio
        self.unit = studio.unit
        self.window = tk.Toplevel(studio.root)
        self.window.title('SCRIB3 | Plot quality')
        self.window.geometry('520x330')
        self.window.minsize(520, 330)
        panel = ttk.Frame(self.window, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Closed-loop seams', style='Title.TLabel').pack(anchor='w')
        ttk.Label(panel, text='Retrace the start of each closed loop before lifting the pen. '
                  'Try 0.5 mm (0.0197 in) for small gaps at circle seams. Open paths keep their original endpoints.',
                  wraplength=480).pack(anchor='w', pady=10)
        row = ttk.Frame(panel)
        row.pack(fill='x')
        ttk.Label(row, text=f'Overlap ({self.unit})').pack(side='left')
        self.overlap = tk.StringVar(value=studio.seam_overlap.get())
        ttk.Entry(row, textvariable=self.overlap, width=14).pack(side='left', padx=12)
        ttk.Button(row, text='Use 0.5 mm', command=lambda: self.overlap.set(display(.5, self.unit))).pack(side='left')
        ttk.Label(panel, text='Set 0 to disable. Maximum 5 mm. This follows the existing path and may darken the seam. '
                  'Pen settle remains adjustable on Machine; sketch runs use at least 0.5 seconds.',
                  wraplength=480, style='Muted.TLabel').pack(anchor='w', pady=12)
        self.status = tk.StringVar()
        ttk.Label(panel, textvariable=self.status, wraplength=480).pack(anchor='w')
        self.apply_button = ttk.Button(panel, text='Apply and save', command=self.apply)
        self.apply_button.pack(side='bottom', anchor='e')

    def apply(self):
        try:
            value = to_mm(self.overlap.get(), self.unit)
            if not 0 <= value <= 5:
                raise ValueError('Choose an overlap between 0 and 5 mm.')
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.studio.seam_overlap.set(display(value, self.studio.unit))
        saved = self.studio.save_preset()
        self.status.set('Saved. Review G-code again to use this overlap.' if saved else
                        'Overlap changed; saving failed. Correct preset fields and save again.')

    def close(self):
        self.window.destroy()
