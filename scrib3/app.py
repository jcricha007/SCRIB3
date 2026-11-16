from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
from xml.etree.ElementTree import ParseError

from . import design, presets
from .assistant_ui import AssistantWindow
from .jobs import PlotJob
from .job_ui import JobWindow
from .setup_guides import MotionDefaultsWindow, PaperGuideWindow
from .paper_mount import origin_corner
from .units import UNIT_NAMES, display, from_mm, to_mm
from .controls import ControlPanel
from .demo import sample
from .drawing import Drawing, Sheet, fit_to_sheet, order_strokes, path_lengths, read_svg
from .gcode import Machine
from .firmware import SERVO_PROFILE, ServoSettings

INK = "#262a25"
MUTED = "#555e54"
BACKGROUND = "#f1f2ec"
DESK = "#e4e9e1"
PAPER = "#fffef8"
GREEN = "#245849"
TEAL = "#598676"


class Studio:
    def __init__(self, root: tk.Tk, preset_file: Path | None = None) -> None:
        self.root = root
        root.title("SCRIB3 | Pen Plotter Studio")
        root.geometry("1120x740")
        root.minsize(800, 650)
        root.configure(background=BACKGROUND)
        self.configure_theme()

        self.preset_file = preset_file if preset_file is not None else presets.preset_path()
        load_warning = ""
        try:
            self.initial_preset = presets.load(self.preset_file)
        except (OSError, ValueError) as exc:
            self.initial_preset = presets.builtin()
            load_warning = f"Saved preset could not be loaded: {exc} Built-in preset loaded."
        data = self.initial_preset
        self.unit = data["units"]
        self.unit_choice = tk.StringVar(value=UNIT_NAMES[self.unit])
        self.paper_mount = tk.StringVar(value=data['paper_mount'])
        self.unit_labels = []
        self.preset_name = tk.StringVar(value=data["name"])
        self.source: Drawing = sample()
        self.drawing: Drawing = ()
        self.sheet = Sheet(148, 105, 7)
        self.revision = 0
        self.undo_state = None
        self.assistant = None
        self.calibration = {100: data["x_steps_per_mm"], 101: data["y_steps_per_mm"]}
        self.paper_width = tk.StringVar(value=display(data["paper_width_mm"], self.unit))
        self.paper_height = tk.StringVar(value=display(data["paper_height_mm"], self.unit))
        self.margin = tk.StringVar(value=display(data["margin_mm"], self.unit))
        self.optimize = tk.BooleanVar(value=True)
        self.show_travel = tk.BooleanVar(value=False)
        self.source_name = tk.StringVar(value="Mountain contours")
        self.status = tk.StringVar(value="Sample loaded. Import an SVG or generate a new drawing.")
        self.stats = tk.StringVar()
        self.model = tk.StringVar(value=data["ollama_model"])
        self.machine_width = tk.StringVar(value="" if data["machine_width_mm"] is None else display(data["machine_width_mm"], self.unit))
        self.machine_height = tk.StringVar(value="" if data["machine_height_mm"] is None else display(data["machine_height_mm"], self.unit))
        self.feed = tk.StringVar(value="" if data["feed_mm_min"] is None else display(data["feed_mm_min"], self.unit))
        self.pen_up = tk.StringVar(value=data["pen_up"])
        self.pen_down = tk.StringVar(value=data["pen_down"])
        self.settle = tk.StringVar(value=f"{data['settle']:g}")
        self.port = tk.StringVar()
        self.baud = tk.StringVar(value="115200")
        self.firmware = tk.StringVar(value=data["firmware"])
        self.controller_report: tuple[str, int, str] | None = None

        self.build_layout()
        self.paper_mount.trace_add('write', self.mount_changed)
        root.protocol("WM_DELETE_WINDOW", self.shutdown)
        self.refresh()
        if load_warning:
            self.status.set(load_warning)

    def configure_theme(self) -> None:
        families = set(font.families(self.root))
        ui = next((name for name in ("Inter", "Segoe UI", "DejaVu Sans") if name in families), "Arial")
        display = next((name for name in ("Instrument Serif", "Georgia", "DejaVu Serif") if name in families), ui)
        font.nametofont("TkDefaultFont").configure(family=ui, size=10)
        font.nametofont("TkTextFont").configure(family=ui, size=10)
        self.ui_font = ui
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background=BACKGROUND, foreground=INK, font=(ui, 10))
        style.configure("TButton", padding=(9, 6))
        style.configure("Primary.TButton", background=GREEN, foreground="white", bordercolor=GREEN)
        style.map("Primary.TButton", background=[("active", "#326c5c")])
        style.configure("Brand.TLabel", font=(display, 33), foreground=GREEN)
        style.configure("Title.TLabel", font=(ui, 13, "bold"))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("TNotebook", padding=0)
        style.configure("TNotebook.Tab", padding=(13, 7))
        style.configure("TEntry", padding=4)

    def build_layout(self) -> None:
        frame = ttk.Frame(self.root, padding=(20, 12, 20, 10))
        frame.pack(fill="both", expand=True)
        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="SCRIB3", style="Brand.TLabel").pack(side="left")
        ttk.Label(header, text="Pen Plotter Studio", style="Muted.TLabel").pack(
            side="left", padx=(12, 0), pady=(11, 0)
        )
        ttk.Button(header, text="Review G-code", style="Primary.TButton", command=self.review).pack(
            side="right", pady=5
        )

        unit_bar = ttk.Frame(header)
        unit_bar.pack(side="right", padx=12)
        ttk.Label(unit_bar, text="Units").pack(side="left", padx=(0, 5))
        self.unit_picker = ttk.Combobox(unit_bar, textvariable=self.unit_choice,
                                       values=tuple(UNIT_NAMES.values()), state="readonly", width=11)
        self.unit_picker.pack(side="left")
        self.unit_picker.bind("<<ComboboxSelected>>", self.change_units)

        tk.Label(frame, textvariable=self.status, background=BACKGROUND, foreground=MUTED,
                 wraplength=730, height=2, justify="left", anchor="w").pack(side="bottom", anchor="w")
        ttk.Separator(frame).pack(side="bottom", fill="x", pady=(8, 4))
        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        workspace = ttk.Frame(body)
        workspace.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        toolbar = ttk.Frame(workspace)
        toolbar.pack(fill="x", pady=(0, 7))
        buttons = ttk.Frame(toolbar)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Import SVG", command=self.import_svg).pack(side="left")
        ttk.Button(buttons, text="Load sample", command=self.load_sample).pack(side="left", padx=6)
        ttk.Checkbutton(
            toolbar, text="Show pen-up travel", variable=self.show_travel, command=self.paint,
        ).pack(anchor="w", pady=(5, 0))
        self.canvas = tk.Canvas(workspace, background=DESK, borderwidth=0, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.paint())
        ttk.Label(workspace, textvariable=self.source_name, style="Title.TLabel").pack(
            anchor="w", pady=(8, 0)
        )
        self.stats_label = ttk.Label(workspace, textvariable=self.stats, style="Muted.TLabel", wraplength=320)
        self.stats_label.pack(anchor="w")

        tabs = ttk.Notebook(body)
        tabs.grid(row=0, column=1, sticky="ns")
        drawing = ttk.Frame(tabs, padding=12, width=310)
        machine = ttk.Frame(tabs, padding=12, width=310)
        for tab in (drawing, machine):
            tab.columnconfigure(1, weight=1)
        tabs.add(drawing, text="Design")
        tabs.add(machine, text="Machine")
        self.build_drawing_tab(drawing)
        self.build_machine_tab(machine)
        self.controls = ControlPanel(tabs, self)
        tabs.add(self.controls, text="Control")
        self.tabs = tabs

    def build_drawing_tab(self, panel: ttk.Frame) -> None:
        title = ttk.Frame(panel)
        title.grid(row=0, columnspan=2, sticky='ew')
        ttk.Label(title, text="Paper and toolpath", style="Title.TLabel").pack(side='left')
        ttk.Button(title, text='Paper guide', padding=(5, 2), command=lambda: PaperGuideWindow(self)).pack(side='right')
        self.field(panel, 1, "Paper width ({unit})", self.paper_width)
        self.field(panel, 2, "Paper height ({unit})", self.paper_height)
        self.field(panel, 3, "Margin ({unit})", self.margin)
        ttk.Checkbutton(panel, text="Order strokes by nearest endpoint", variable=self.optimize).grid(
            row=4, columnspan=2, sticky="w", pady=4
        )
        ttk.Button(panel, text="Fit to paper", command=self.apply_layout).grid(row=5, columnspan=2, sticky="ew")
        ttk.Separator(panel).grid(row=6, columnspan=2, sticky="ew", pady=12)

        ttk.Button(panel, text="Open Ollama assistant", style="Primary.TButton", command=self.open_assistant).grid(
            row=7, columnspan=2, sticky="ew")
        ttk.Label(panel, text="Chat, create line art, and revise this design.", style="Muted.TLabel").grid(
            row=8, columnspan=2, sticky="w", pady=(3, 8))
        ttk.Label(panel, text="Design tools", style="Title.TLabel").grid(row=9, columnspan=2, sticky="w")
        self.pattern_kind = tk.StringVar(value="Rosette")
        self.pattern_detail = tk.StringVar(value="12")
        ttk.Combobox(panel, textvariable=self.pattern_kind, values=("Grid", "Spiral", "Rosette"),
                     state="readonly", width=13).grid(row=10, column=0, sticky="ew", pady=4)
        detail = ttk.Frame(panel)
        detail.grid(row=10, column=1, sticky="ew")
        ttk.Label(detail, text="Detail").pack(side="left", padx=5)
        ttk.Spinbox(detail, textvariable=self.pattern_detail, from_=3, to=40, width=5).pack(side="left")
        ttk.Button(panel, text="Create pattern", command=self.create_pattern).grid(row=11, columnspan=2, sticky="ew")
        transforms = ttk.Frame(panel)
        transforms.grid(row=12, columnspan=2, sticky="ew", pady=6)
        for operation in ("Rotate 90°", "Mirror X", "Mirror Y"):
            ttk.Button(transforms, text=operation, padding=(5, 4),
                       command=lambda op=operation: self.transform_design(op)).pack(side="left", fill="x", expand=True)
        ttk.Button(panel, text="Undo design", command=self.undo_design).grid(row=13, column=0, sticky="ew")
        ttk.Button(panel, text="Export SVG", command=self.export_svg).grid(row=13, column=1, sticky="ew")

    def build_machine_tab(self, panel: ttk.Frame) -> None:
        profile_panel = ttk.Frame(panel)
        profile_panel.grid(row=0, columnspan=2, sticky="ew", pady=(0, 7))
        ttk.Label(profile_panel, text="Firmware profile").pack(side="left", padx=(0, 10))
        ttk.Combobox(profile_panel, textvariable=self.firmware, state="readonly", width=18,
                     values=("Manual commands", SERVO_PROFILE)).pack(side="left", fill="x", expand=True)
        settings_panel = ttk.Frame(panel)
        settings_panel.grid(row=1, columnspan=2, sticky="ew")
        settings_panel.columnconfigure(1, weight=1)
        panel = settings_panel
        ttk.Label(panel, text="Plotter settings", style="Title.TLabel").grid(row=0, columnspan=2, sticky="w")
        for row, (label, variable) in enumerate((
            ("Usable X travel ({unit})", self.machine_width),
            ("Usable Y travel ({unit})", self.machine_height),
            ("Draw feed ({unit}/min)", self.feed),
            ("Pen up command", self.pen_up),
            ("Pen down command", self.pen_down),
            ("Pen settle (sec)", self.settle),
        ), start=1):
            self.field(panel, row, label, variable)
        ttk.Label(panel, text="Z pen commands use mm; servo S values are unitless.",
                  style="Muted.TLabel", wraplength=320).grid(row=7, columnspan=2, sticky="w", pady=(6, 0))
        motion_actions = ttk.Frame(panel)
        motion_actions.grid(row=8, columnspan=2, sticky='ew', pady=(8, 4))
        ttk.Button(motion_actions, text="Use controller travel", padding=(5, 6),
                   command=lambda: self.controls.copy_travel()).pack(side='left', fill='x', expand=True)
        self.motion_defaults_button = ttk.Button(motion_actions, text='Smooth motion', padding=(5, 6),
                                                command=lambda: MotionDefaultsWindow(self))
        self.motion_defaults_button.pack(side='right', fill='x', expand=True, padx=(5, 0))
        ttk.Separator(panel).grid(row=9, columnspan=2, sticky="ew", pady=6)
        self.field(panel, 10, "Preset name", self.preset_name)
        ttk.Button(panel, text="Save preset", command=self.save_preset).grid(row=11, column=0, sticky="ew", pady=4)
        ttk.Button(panel, text="Restore John's", command=self.restore_preset).grid(row=11, column=1, sticky="ew", pady=4)
        ttk.Label(panel, text="Saved presets reload when SCRIB3 opens.\nFirmware startup/reset still uses the M5 position.",
                  style="Muted.TLabel", wraplength=320).grid(row=12, columnspan=2, sticky="w", pady=(4, 0))

    def field(self, panel: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        widget = ttk.Label(panel, text=label.format(unit=self.unit))
        widget.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
        if "{unit}" in label:
            self.unit_labels.append((widget, label))
        ttk.Entry(panel, textvariable=variable, width=17).grid(row=row, column=1, sticky="ew")

    def dimension_fields(self):
        return {"paper_width_mm": self.paper_width, "paper_height_mm": self.paper_height,
                "margin_mm": self.margin, "machine_width_mm": self.machine_width,
                "machine_height_mm": self.machine_height, "feed_mm_min": self.feed,
                "jog_step_mm": self.controls.step, "jog_feed_mm_min": self.controls.rate}

    def update_unit_labels(self):
        for label, template in self.unit_labels:
            label.configure(text=template.format(unit=self.unit))
        self.controls.update_units()

    def change_units(self, _event=None):
        requested = next((code for code, name in UNIT_NAMES.items() if name == self.unit_choice.get()), None)
        if requested == self.unit:
            return
        try:
            if requested is None:
                raise ValueError("Select inches or millimeters.")
            converted = [(variable, display(to_mm(variable.get(), self.unit), requested)
                          if variable.get().strip() else "") for variable in self.dimension_fields().values()]
        except ValueError as exc:
            self.unit_choice.set(UNIT_NAMES[self.unit])
            messagebox.showerror("Change units", str(exc), parent=self.root)
            return
        self.unit = requested
        for variable, value in converted:
            variable.set(value)
        self.update_unit_labels()
        self.apply_layout()
        self.status.set(f"Units: {UNIT_NAMES[self.unit]}. Save preset to remember this choice.")

    def save_preset(self):
        try:
            values = {name: (to_mm(variable.get(), self.unit) if variable.get().strip() else None)
                      for name, variable in self.dimension_fields().items()}
            values.update(schema_version=3, name=self.preset_name.get(), units=self.unit,
                          paper_mount=self.paper_mount.get(),
                          firmware=self.firmware.get(), pen_up=self.pen_up.get(), pen_down=self.pen_down.get(),
                          settle=float(self.settle.get()), x_steps_per_mm=self.calibration[100],
                          y_steps_per_mm=self.calibration[101], ollama_model=self.model.get())
            presets.save(self.preset_file, values)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Save preset", str(exc), parent=self.root)
            return False
        else:
            self.status.set(f"Saved {values['name']}. These settings will reload next time.")
            return True

    def restore_preset(self):
        data = presets.builtin()
        self.calibration = {100: data["x_steps_per_mm"], 101: data["y_steps_per_mm"]}
        self.unit = data["units"]
        self.unit_choice.set(UNIT_NAMES[self.unit])
        self.paper_mount.set(data['paper_mount'])
        for name, variable in self.dimension_fields().items():
            variable.set("" if data[name] is None else display(data[name], self.unit))
        for key in ("name", "firmware", "pen_up", "pen_down", "settle"):
            variable = self.preset_name if key == "name" else getattr(self, key)
            variable.set(str(data[key]))
        self.update_unit_labels()
        self.refresh()
        self.status.set("Restored John's pen preset. Save preset to keep it for the next launch.")

    def refresh(self) -> None:
        try:
            dimensions = tuple(to_mm(field.get(), self.unit) for field in (self.paper_width, self.paper_height, self.margin))
        except ValueError as exc:
            raise ValueError("Enter numeric paper dimensions and margin on the Design tab.") from exc
        sheet = Sheet(*dimensions)
        fitted = fit_to_sheet(self.source, sheet)
        self.sheet = sheet
        self.drawing = order_strokes(fitted) if self.optimize.get() else fitted
        drawn, travel = path_lengths(self.drawing)
        self.stats.set(
            f"{from_mm(self.sheet.width, self.unit):.3f} × {from_mm(self.sheet.height, self.unit):.3f} {self.unit}  ·  {len(self.drawing):,} strokes"
            f"  ·  {from_mm(drawn, self.unit):,.2f} {self.unit} drawn  ·  {from_mm(travel, self.unit):,.2f} {self.unit} pen-up"
        )
        self.paint()

    def paint(self) -> None:
        canvas = self.canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if min(width, height) < 76:
            return
        self.stats_label.configure(wraplength=max(150, width))
        canvas.delete("all")
        for x in range(12, width, 16):
            for y in range(12, height, 16):
                canvas.create_oval(x, y, x + 1, y + 1, fill="#b7c4b8", outline="")
        sheet = self.sheet
        scale = min((width - 64) / sheet.width, (height - 64) / sheet.height)
        left = (width - sheet.width * scale) / 2
        top = (height - sheet.height * scale) / 2
        right, bottom = width - left, height - top
        canvas.create_rectangle(left + 4, top + 5, right + 4, bottom + 5, fill="#c4cec2", outline="")
        canvas.create_rectangle(left, top, right, bottom, fill=PAPER, outline="#a0aa9d")
        margin = sheet.margin * scale
        if margin:
            canvas.create_rectangle(left + margin, top + margin, right - margin, bottom - margin,
                                    outline="#cbd0c2", dash=(3, 4))
        origin_y = top if self.paper_mount.get() == 'top_left_y' else bottom
        previous = (left, origin_y)
        for stroke in self.drawing:
            points = tuple(coord for x, y in stroke for coord in (left + x * scale, bottom - y * scale))
            if self.show_travel.get():
                canvas.create_line(*previous, *points[:2], fill=TEAL, dash=(3, 4))
            canvas.create_line(*points, fill=INK, width=1.4, capstyle="round", joinstyle="round")
            previous = points[-2:]
        canvas.create_oval(left - 3, origin_y - 3, left + 3, origin_y + 3, fill=GREEN, outline="")
        canvas.create_text(left + 8, origin_y - 8 if origin_y == top else origin_y + 8,
                           text="0, 0", anchor="sw" if origin_y == top else "nw", fill=MUTED, font=(self.ui_font, 9))

    def mount_changed(self, *_):
        self.controls.update_axes()
        if self.controls.session:
            self.controls.session.invalidate_paper_origin()
        self.paint()

    def apply_layout(self) -> None:
        try:
            self.refresh()
        except ValueError as exc:
            messagebox.showerror("Paper settings", str(exc), parent=self.root)
        else:
            self.status.set("Preview updated.")

    def set_drawing(self, name: str, source: Drawing) -> None:
        old_source = self.source
        old_name = self.source_name.get()
        self.source = source
        try:
            self.refresh()
        except ValueError:
            self.source = old_source
            raise
        self.source_name.set(name)
        self.undo_state = (old_name, old_source)
        self.revision += 1

    def open_assistant(self):
        if self.assistant is None:
            self.assistant = AssistantWindow(self)
        else:
            self.assistant.window.deiconify()
            self.assistant.window.lift()

    def shutdown(self):
        if self.assistant is not None:
            self.assistant.shutdown()
        self.controls.shutdown()

    def create_pattern(self):
        try:
            self.set_drawing(self.pattern_kind.get(), design.pattern(self.pattern_kind.get(), int(self.pattern_detail.get())))
            self.status.set("Pattern ready. Undo design restores the previous drawing.")
        except ValueError as exc:
            messagebox.showerror("Create pattern", str(exc), parent=self.root)

    def transform_design(self, operation):
        try:
            self.set_drawing(self.source_name.get(), design.transform(self.source, operation))
            self.status.set(operation + " applied.")
        except ValueError as exc:
            messagebox.showerror("Transform design", str(exc), parent=self.root)

    def undo_design(self):
        if self.undo_state is not None:
            previous = self.undo_state
            try:
                self.set_drawing(*previous)
                self.undo_state = None
                self.status.set("Previous design restored.")
            except ValueError as exc:
                messagebox.showerror("Undo design", str(exc), parent=self.root)

    def export_svg(self):
        try:
            self.refresh()
            document = design.svg_document(self.drawing, self.sheet)
            file = filedialog.asksaveasfilename(parent=self.root, defaultextension=".svg", filetypes=[("SVG drawing", "*.svg")])
            if file:
                Path(file).write_text(document, encoding="utf-8")
                self.status.set(f"Saved {Path(file).name}.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Export SVG", str(exc), parent=self.root)

    def load_sample(self) -> None:
        try:
            self.set_drawing("Mountain contours", sample())
        except ValueError as exc:
            messagebox.showerror("Load sample", str(exc), parent=self.root)
        else:
            self.status.set("Sample loaded.")

    def import_svg(self) -> None:
        file = filedialog.askopenfilename(parent=self.root, filetypes=[("SVG drawing", "*.svg")])
        if not file:
            return
        path = Path(file)
        try:
            self.set_drawing(path.stem, read_svg(path))
        except (OSError, ValueError, ParseError) as exc:
            messagebox.showerror("Import SVG", str(exc), parent=self.root)
        else:
            self.status.set("SVG fitted to paper. Filled shapes plot as outlines.")

    def scan_ports(self) -> None:
        self.controls.find_ports()

    def inspect(self) -> None:
        self.controls.read_report()

    def review(self) -> None:
        try:
            if self.controls.session and self.controls.session.snapshot()["reset_required"]:
                raise ValueError("Calibration changed. Reset and reconnect before reviewing a job.")
            self.refresh()
            servo = None
            if self.firmware.get() == SERVO_PROFILE:
                if self.controller_report is None or self.controller_report[:2] != (self.port.get(), int(self.baud.get())):
                    raise ValueError("Read GRBL on the selected port to check the uploaded servo profile.")
                servo = ServoSettings.from_report(self.controller_report[2])
            machine = Machine(
                to_mm(self.machine_width.get(), self.unit), to_mm(self.machine_height.get(), self.unit),
                to_mm(self.feed.get(), self.unit), self.pen_up.get(), self.pen_down.get(), float(self.settle.get()),
                servo=servo, paper_mount=self.paper_mount.get(),
            )
            machine = replace(machine, settle=max(.5, machine.settle))
            session = self.controls.session
            snap = session.snapshot() if session else {}
            job = PlotJob(self.drawing, self.sheet, machine, self.unit, True,
                          tuple(sorted(snap.get('settings', {}).items())), snap.get('reference', -1))
            program = job.program()
        except ValueError as exc:
            error = str(exc)
            if "could not convert string to float" in error:
                error = "Enter the plotter’s X/Y travel, draw feed, and verified pen commands on the Machine tab."
            messagebox.showerror("Review G-code", error, parent=self.root)
            return
        def preview(program):
            lines = program.splitlines()
            return "\n".join(lines[:400]) + (f"\n\nShowing 400 of {len(lines):,} lines." if len(lines) > 400 else '')
        dialog, controls = self.text_dialog("G-code review / Run sketch", preview(program))
        dialog.geometry('680x540')
        dry_run = tk.BooleanVar(value=True)
        def update_preview():
            nonlocal job, program
            job = replace(job, dry_run=dry_run.get())
            program = job.program()
            dialog.output.configure(state='normal')
            dialog.output.delete('1.0', 'end')
            dialog.output.insert('1.0', preview(program))
            dialog.output.configure(state='disabled')
        ttk.Checkbutton(controls, text='Pen-up test (uncheck to draw with ink)', variable=dry_run,
                        command=update_preview).pack(anchor='w')
        corner = origin_corner(machine.paper_mount)
        direction = '+Y right, -X down' if machine.paper_mount == 'top_left_y' else '+X right, +Y up'
        ttk.Label(controls, text=f'Paper XY zero: {corner} corner; {direction}. Minimum pen settle: 0.5 seconds.',
                  wraplength=630, style='Muted.TLabel').pack(anchor='w', pady=4)
        actions = ttk.Frame(controls)
        actions.pack(fill='x')
        def signature():
            return (self.revision, self.unit, self.firmware.get(), self.pen_up.get(), self.pen_down.get(),
                    self.settle.get(), self.paper_mount.get(), self.optimize.get(), *(v.get() for v in self.dimension_fields().values()))
        reviewed = signature()
        def run():
            try:
                if self.controls.session is not session or session is None:
                    raise ValueError('Connect to the Arduino, set paper XY zero, then review again.')
                if signature() != reviewed:
                    raise ValueError('The drawing or settings changed. Close this review and review the new drawing.')
                current = session.snapshot()
                if not current['connected'] or current['busy'] or current['state'] != 'Idle' or not current['fresh']:
                    raise ValueError('Wait for a connected, Idle controller.')
                if not current['origin_set'] or current['reference'] != job.reference:
                    raise ValueError('Set paper XY zero or manual home during this connection, then review again.')
                if any(abs(current['settings'].get(n, 0) - self.calibration[n]) > .0005 for n in (100, 101)):
                    raise ValueError('Controller X/Y steps differ from the saved calibration. Use Setup before running.')
                operation = session.request('run_job', job=job)
            except ValueError as exc:
                messagebox.showerror('Run sketch', str(exc), parent=dialog)
            else:
                JobWindow(self.root, session, operation)
                dialog.destroy()
                self.status.set('Sketch running. Use its progress window to pause, resume, or stop.')
        ttk.Button(actions, text='Save .gcode', command=lambda: self.save_program(dialog, program)).pack(side='left')
        ttk.Button(actions, text='Run sketch', style='Primary.TButton', command=run).pack(side='right')

    def save_program(self, parent: tk.Toplevel, program: str) -> None:
        file = filedialog.asksaveasfilename(parent=parent, defaultextension=".gcode",
                                            filetypes=[("G-code program", "*.gcode")])
        if file:
            try:
                Path(file).write_text(program, encoding="ascii", newline="\n")
            except OSError as exc:
                messagebox.showerror("Save G-code", str(exc), parent=parent)
            else:
                self.status.set(f"Saved {Path(file).name}.")

    def text_dialog(self, title: str, content: str) -> tuple[tk.Toplevel, ttk.Frame]:
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.transient(self.root)
        dialog.geometry("580x440")
        panel = ttk.Frame(dialog, padding=12)
        panel.pack(fill="both", expand=True)
        controls = ttk.Frame(panel)
        controls.pack(side="bottom", fill="x", pady=(8, 0))
        scroll = ttk.Scrollbar(panel)
        scroll.pack(side="right", fill="y")
        output = tk.Text(panel, wrap="none", background=PAPER, foreground=INK, font="TkFixedFont",
                         yscrollcommand=scroll.set)
        output.pack(side="left", fill="both", expand=True)
        scroll.configure(command=output.yview)
        output.insert("1.0", content)
        output.configure(state="disabled")
        dialog.output = output
        return dialog, controls


def main(connect: str | None = None, baud: int | None = None) -> None:
    root = tk.Tk()
    studio = Studio(root)
    if connect is not None:
        studio.tabs.select(studio.controls)
        if connect == "auto" or baud is None:
            root.after(100, lambda: studio.controls.auto_detect(
                port=None if connect == "auto" else connect, baud=baud))
        else:
            studio.port.set(connect)
            studio.baud.set(str(baud))
            root.after(100, studio.controls.connect)
    root.mainloop()
