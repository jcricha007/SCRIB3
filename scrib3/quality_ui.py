"""Per-preset seam treatment for closed pen paths."""
import tkinter as tk
from tkinter import ttk

from .units import display, to_mm
from .toolpath import QUALITY_MODES


class QualityWindow:
    def __init__(self, studio):
        self.studio = studio
        self.unit = studio.unit
        self.window = tk.Toplevel(studio.root)
        self.window.title('SCRIB3 | Plot quality')
        self.window.geometry('540x560')
        self.window.minsize(540, 560)
        panel = ttk.Frame(self.window, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Toolpath cleanup', style='Title.TLabel').pack(anchor='w')
        self.mode = tk.StringVar(value=studio.quality_mode.get())
        ttk.Combobox(panel, textvariable=self.mode, values=tuple(QUALITY_MODES),
                     state='readonly', width=20).pack(anchor='w', pady=8)
        ttk.Label(panel, text='Original: no simplification. Fine: 0.005 mm. Balanced: 0.02 mm. '
                  'Tolerance applies after fitting to paper, before G-code rounding.',
                  wraplength=490, style='Muted.TLabel').pack(anchor='w')
        self.deduplicate = tk.BooleanVar(value=studio.remove_duplicates.get())
        ttk.Checkbutton(panel, text='Remove exactly repeated strokes (including reversed copies)',
                        variable=self.deduplicate).pack(anchor='w', pady=8)
        ttk.Label(panel, text='Leave off to preserve intentional overdraw. Small gaps are never joined.',
                  wraplength=490, style='Muted.TLabel').pack(anchor='w')
        ttk.Separator(panel).pack(fill='x', pady=14)
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
        old_overlap = self.studio.seam_overlap.get()
        self.studio.seam_overlap.set(display(value, self.studio.unit))
        old_mode, old_duplicates = self.studio.quality_mode.get(), self.studio.remove_duplicates.get()
        self.studio.quality_mode.set(self.mode.get())
        self.studio.remove_duplicates.set(self.deduplicate.get())
        try:
            self.studio.refresh()
        except ValueError as exc:
            self.studio.seam_overlap.set(old_overlap)
            self.studio.quality_mode.set(old_mode)
            self.studio.remove_duplicates.set(old_duplicates)
            self.status.set(str(exc))
            return
        saved = self.studio.save_preset()
        self.status.set('Saved. Review G-code again to use this overlap.' if saved else
                        'Overlap changed; saving failed. Correct preset fields and save again.')

    def close(self):
        self.window.destroy()
