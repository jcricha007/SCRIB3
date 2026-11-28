"""Preview and apply stroke lettering, with workspace revision checks."""
import tkinter as tk
from tkinter import ttk

from . import theme
from .drawing import Sheet, fit_to_sheet
from .lettering import ALIGNMENTS, FONTS, add_caption, lettering


class LetteringWindow:
    def __init__(self, studio):
        self.studio = studio
        self.window = tk.Toplevel(studio.root)
        self.window.title('SCRIB3 | Stroke lettering')
        self.window.geometry('720x620')
        self.window.minsize(620, 560)
        self.draft = None
        self.snapshot = None
        self.font = tk.StringVar(value='Technical sans')
        self.alignment = tk.StringVar(value='Left')
        self.placement = tk.StringVar(value='New lettering')
        self.height = tk.StringVar(value='4')
        self.tracking = tk.StringVar(value='0')
        self.spacing = tk.StringVar(value='1.5')
        self.status = tk.StringVar(value='Printable ASCII, including lowercase and punctuation. Preview before applying.')
        panel = ttk.Frame(self.window, padding=16)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text='Single-stroke lettering', style='Title.TLabel').pack(anchor='w')
        ttk.Label(panel, text='Create plotter lettering or add a caption below your artwork. The result fits to paper.',
                  wraplength=570, style='Muted.TLabel').pack(anchor='w', pady=6)
        footer = ttk.Frame(panel)
        footer.pack(side='bottom', fill='x', pady=(10, 0))
        ttk.Label(footer, textvariable=self.status, wraplength=550).pack(anchor='w')
        self.apply_button = ttk.Button(footer, text='Apply lettering', style='Primary.TButton', command=self.apply, state='disabled')
        self.apply_button.pack(side='right', pady=(8, 0))
        ttk.Button(footer, text='Preview', command=self.preview).pack(side='left', pady=(8, 0))
        self.text = tk.Text(panel, height=4, width=50, wrap='word')
        self.text.pack(fill='x', pady=8)
        self.text.insert('1.0', 'SCRIB3\nENGINEERING DRAWINGS')
        self.text.edit_modified(False)
        self.text.bind('<<Modified>>', self.text_changed)
        fields = ttk.Frame(panel)
        fields.pack(fill='x', pady=4)
        fields.columnconfigure(1, weight=1)
        for row, (label, var, choices) in enumerate((
            ('Font', self.font, tuple(FONTS)), ('Alignment', self.alignment, ALIGNMENTS),
            ('Placement', self.placement, ('New lettering', 'Caption below drawing')),
            ('Caption height (% artwork extent)', self.height, None),
            ('Extra letter spacing (font units)', self.tracking, None),
            ('Line spacing (capital heights)', self.spacing, None))):
            ttk.Label(fields, text=label).grid(row=row, column=0, sticky='w', padx=(0, 12))
            widget = (ttk.Combobox(fields, textvariable=var, values=choices, state='readonly')
                      if choices else ttk.Entry(fields, textvariable=var))
            widget.grid(row=row, column=1, sticky='ew', pady=2)
            var.trace_add('write', self.invalidate)
        self.canvas = tk.Canvas(panel, background=theme.DESK, highlightthickness=0)
        self.canvas.pack(fill='both', expand=True, pady=(8, 0))
        self.canvas.bind('<Configure>', lambda _: self.paint())

    def text_changed(self, _event=None):
        if self.text.edit_modified():
            self.text.edit_modified(False)
            self.invalidate()

    def invalidate(self, *_):
        self.draft = None
        self.apply_button.state(['disabled'])
        self.paint()

    def signature(self):
        return (self.studio.revision, self.studio.source, self.text.get('1.0', 'end-1c'),
                *(v.get() for v in (self.font, self.alignment, self.placement, self.height, self.tracking, self.spacing)))

    def preview(self):
        self.invalidate()
        try:
            letters = lettering(self.text.get('1.0', 'end-1c'), self.font.get(), self.alignment.get(),
                                float(self.tracking.get()), float(self.spacing.get()))
            self.draft = (add_caption(self.studio.source, letters, float(self.height.get()))
                          if self.placement.get() == 'Caption below drawing' else letters)
            self.snapshot = self.signature()
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.apply_button.state(['!disabled'])
        self.status.set(f'{len(self.draft):,} strokes. Apply updates the workspace; Undo design restores it.')
        self.paint()

    def paint(self):
        if not hasattr(self, 'canvas'):
            return
        self.canvas.delete('all')
        if self.draft:
            w, h = max(60, self.canvas.winfo_width()), max(60, self.canvas.winfo_height())
            for stroke in fit_to_sheet(self.draft, Sheet(w, h, 12)):
                self.canvas.create_line(*(v for x, y in stroke for v in (x, h-y)), fill='#172033')

    def apply(self):
        if self.draft is None or self.signature() != self.snapshot:
            self.invalidate()
            self.status.set('Text, settings or artwork changed. Preview again before applying.')
            return
        try:
            self.studio.set_drawing('Lettering: ' + self.text.get('1.0', 'end-1c')[:55].replace('\n', ' / '), self.draft)
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.invalidate()
        self.status.set('Applied. Undo design restores your previous artwork.')

    def close(self):
        self.window.destroy()
