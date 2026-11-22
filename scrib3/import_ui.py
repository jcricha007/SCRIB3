"""Asynchronous artwork conversion with explicit preview and apply."""
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk

from .artwork_import import ImportOptions, read_artwork
from .drawing import Sheet, fit_to_sheet
from .raster import RASTER_FORMATS, TraceOptions


class ImportWindow:
    def __init__(self, studio, path):
        self.studio, self.path = studio, Path(path)
        self.closed = self.busy = False
        self.generation = 0
        self.draft = None
        self.events = Queue()
        self.cancel = Event()
        self.photo = None
        self.window = tk.Toplevel(studio.root)
        self.window.title('SCRIB3 | Import artwork')
        self.window.geometry('880x660')
        self.window.minsize(800, 620)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        panel = ttk.Frame(self.window, padding=14)
        panel.pack(fill='both', expand=True)
        ttk.Label(panel, text=self.path.name, style='Title.TLabel', wraplength=740).pack(anchor='w')
        ttk.Label(panel, text='Preview the converted paths, then apply them to your drawing.',
                  style='Muted.TLabel').pack(anchor='w', pady=(2, 12))
        raster = self.path.suffix.lower() in RASTER_FORMATS
        paged = self.path.suffix.lower() in ('.pdf', '.ai')
        self.method = tk.StringVar(value='Trace image' if raster else 'Vector paths')
        self.page = tk.StringVar(value='1')
        self.mode = tk.StringVar(value='Centerline')
        self.threshold = tk.StringVar(value='128')
        self.resolution = tk.StringVar(value='1024')
        self.despeckle = tk.StringVar(value='0')
        self.invert = tk.BooleanVar(value=False)
        row = ttk.Frame(panel)
        row.pack(fill='x')
        ttk.Label(row, text='Import method').pack(side='left')
        values = ('Vector paths', 'Trace image') if paged else (self.method.get(),)
        ttk.Combobox(row, textvariable=self.method, values=values, state='readonly', width=16).pack(side='left', padx=8)
        ttk.Label(row, text='Page').pack(side='left', padx=(12, 4))
        ttk.Spinbox(row, textvariable=self.page, from_=1, to=10000, width=6,
                    state='normal' if paged else 'disabled').pack(side='left')
        self.preview_button = ttk.Button(row, text='Generate preview', command=self.preview)
        self.preview_button.pack(side='right')
        settings = ttk.LabelFrame(panel, text='Image tracing', padding=8)
        settings.pack(fill='x', pady=10)
        self.trace_widgets = []
        for col, (title, variable, choices) in enumerate((
                ('Paths', self.mode, ('Centerline', 'Outline')),
                ('Resolution (px)', self.resolution, ('256', '512', '1024', '2048')))):
            ttk.Label(settings, text=title).grid(row=0, column=2 * col, padx=4, sticky='w')
            widget = ttk.Combobox(settings, textvariable=variable, values=choices, state='readonly', width=12)
            widget.grid(row=0, column=2 * col + 1, padx=4)
            self.trace_widgets.append((widget, 'readonly'))
        for col, (title, variable, low, high) in enumerate((
                ('Threshold', self.threshold, 1, 254), ('Remove specks (px)', self.despeckle, 0, 100))):
            ttk.Label(settings, text=title).grid(row=1, column=2 * col, padx=4, pady=6, sticky='w')
            widget = ttk.Spinbox(settings, textvariable=variable, from_=low, to=high, width=12)
            widget.grid(row=1, column=2 * col + 1, padx=4)
            self.trace_widgets.append((widget, 'normal'))
        widget = ttk.Checkbutton(settings, text='Light ink on dark background', variable=self.invert)
        widget.grid(row=2, column=0, columnspan=4, padx=4, sticky='w')
        self.trace_widgets.append((widget, 'normal'))
        self.status = tk.StringVar(value='Ready to preview. Raster artwork is approximated as pen paths.')
        self.details = tk.StringVar()
        footer = ttk.Frame(panel)
        footer.pack(side='bottom', fill='x', pady=(10, 0))
        self.apply_button = ttk.Button(footer, text='Use drawing', style='Primary.TButton', command=self.apply)
        self.apply_button.pack(side='right')
        self.apply_button.state(['disabled'])
        self.cancel_button = ttk.Button(footer, text='Cancel conversion', command=self.cancel_work)
        self.cancel_button.pack(side='right', padx=8)
        self.cancel_button.state(['disabled'])
        ttk.Label(panel, textvariable=self.status, wraplength=740).pack(side='bottom', fill='x', pady=(5, 0))
        ttk.Label(panel, textvariable=self.details, style='Muted.TLabel', wraplength=740).pack(side='bottom', fill='x')
        previews = ttk.Frame(panel)
        previews.pack(fill='both', expand=True)
        self.canvases = []
        for i, title in enumerate(('Source image', 'Pen paths')):
            previews.columnconfigure(i, weight=1, uniform='preview')
            previews.rowconfigure(1, weight=1)
            ttk.Label(previews, text=title, style='Muted.TLabel').grid(row=0, column=i, sticky='w')
            canvas = tk.Canvas(previews, background='white', highlightthickness=1, highlightbackground='#d7dce5')
            canvas.grid(row=1, column=i, sticky='nsew', padx=(0, 8) if i == 0 else (0, 0))
            canvas.bind('<Configure>', lambda _event: self.paint())
            self.canvases.append(canvas)
        self.variables = (self.method, self.page, self.mode, self.threshold, self.resolution, self.despeckle, self.invert)
        for variable in self.variables:
            variable.trace_add('write', self.invalidate)
        self.update_controls()
        self.after_id = self.window.after(50, self.poll)
        self.preview()

    def update_controls(self):
        tracing = self.method.get() == 'Trace image'
        for widget, state in self.trace_widgets:
            widget.configure(state=state if tracing else 'disabled')

    def invalidate(self, *_):
        self.generation += 1
        self.cancel.set()
        self.draft = None
        self.apply_button.state(['disabled'])
        self.update_controls()
        self.status.set('Settings changed. Generate a new preview before applying.')
        self.details.set('')
        self.paint()

    def preview(self):
        if self.busy or self.closed:
            return
        self.draft = None
        self.apply_button.state(['disabled'])
        try:
            trace = (TraceOptions(self.mode.get(), int(self.threshold.get()), self.invert.get(),
                                  int(self.resolution.get()), int(self.despeckle.get()))
                     if self.method.get() == 'Trace image' else TraceOptions())
            options = ImportOptions(self.method.get(), int(self.page.get()), trace)
        except ValueError as exc:
            self.status.set(str(exc))
            self.paint()
            return
        self.generation += 1
        generation = self.generation
        self.workspace_revision = self.studio.revision
        self.cancel = Event()
        cancel = self.cancel
        self.busy = True
        self.preview_button.state(['disabled'])
        self.cancel_button.state(['!disabled'])
        self.status.set('Converting artwork locally...')
        self.details.set('')
        self.paint()

        def work():
            try:
                result = read_artwork(self.path, options, cancel)
            except Exception as exc:
                self.events.put((generation, None, str(exc)))
            else:
                self.events.put((generation, result, None))

        Thread(target=work, name='scrib3-artwork-import', daemon=True).start()

    def poll(self):
        if self.closed:
            return
        try:
            generation, result, error = self.events.get_nowait()
        except Empty:
            pass
        else:
            self.busy = False
            self.preview_button.state(['!disabled'])
            self.cancel_button.state(['disabled'])
            if generation == self.generation and not self.cancel.is_set():
                if error:
                    self.status.set(error)
                else:
                    self.draft = result
                    self.details.set(result.note)
                    self.status.set(f'{len(result.drawing):,} strokes / {sum(map(len, result.drawing)):,} points. '
                                    'Use drawing replaces the workspace; Undo design restores it.')
                    self.apply_button.state(['!disabled'])
                self.paint()
        self.after_id = self.window.after(50, self.poll)

    def paint(self):
        if self.closed:
            return
        for canvas in self.canvases:
            canvas.delete('all')
        self.photo = None
        if self.draft is None:
            return
        left, right = self.canvases
        if self.draft.image is not None:
            from PIL import Image, ImageTk
            image = self.draft.image
            for canvas in self.canvases:
                width, height = max(40, canvas.winfo_width()), max(40, canvas.winfo_height())
                scale = min((width - 24) / image.width, (height - 24) / image.height)
                x0, y0 = (width - image.width * scale) / 2, (height - image.height * scale) / 2
                if canvas is left:
                    resized = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
                    self.photo = ImageTk.PhotoImage(resized, master=self.window)
                    canvas.create_image(x0, y0, image=self.photo, anchor='nw')
                else:
                    for stroke in self.draft.drawing:
                        canvas.create_line(*(v for x, y in stroke for v in (x0 + x * scale, y0 + y * scale)), fill='#172033')
        else:
            left.create_text(16, 18, text='Vector artwork\nPaths are shown on the right.', anchor='nw', fill='#617085')
            width, height = max(40, right.winfo_width()), max(40, right.winfo_height())
            for stroke in fit_to_sheet(self.draft.drawing, Sheet(width, height, 12)):
                right.create_line(*(v for x, y in stroke for v in (x, height - y)), fill='#172033')

    def apply(self):
        if self.draft is None or self.busy or self.closed:
            return
        if self.studio.revision != self.workspace_revision:
            self.invalidate()
            self.status.set('The workspace drawing changed. Generate a new preview before replacing it.')
            return
        try:
            self.studio.set_drawing(self.path.stem, self.draft.drawing)
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.studio.status.set(f'Imported {self.path.name}. Undo design restores the previous drawing. Review G-code before plotting.')
        self.close()

    def cancel_work(self):
        self.invalidate()
        self.status.set('Conversion cancelled. The workspace drawing is unchanged.')

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel.set()
        self.window.after_cancel(self.after_id)
        self.window.destroy()
