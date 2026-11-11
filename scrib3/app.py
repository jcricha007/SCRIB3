from __future__ import annotations

from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Thread
import tkinter as tk
from tkinter import filedialog, font, messagebox, ttk
from xml.etree.ElementTree import ParseError

from . import grbl, ollama
from .demo import sample
from .drawing import Drawing, Sheet, fit_to_sheet, order_strokes, path_lengths, read_svg
from .gcode import Machine, generate_gcode

INK = "#262a25"
MUTED = "#555e54"
BACKGROUND = "#f1f2ec"
DESK = "#e4e9e1"
PAPER = "#fffef8"
GREEN = "#245849"
TEAL = "#598676"


class Studio:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("SCRIB3 | Pen Plotter Studio")
        root.geometry("1120x740")
        root.minsize(800, 650)
        root.configure(background=BACKGROUND)
        self.configure_theme()

        self.source: Drawing = sample()
        self.drawing: Drawing = ()
        self.sheet = Sheet(148, 105, 7)
        self.revision = 0
        self.results = SimpleQueue()
        self.paper_width = tk.StringVar(value="148")
        self.paper_height = tk.StringVar(value="105")
        self.margin = tk.StringVar(value="7")
        self.optimize = tk.BooleanVar(value=True)
        self.show_travel = tk.BooleanVar(value=False)
        self.source_name = tk.StringVar(value="Mountain contours")
        self.status = tk.StringVar(value="Sample loaded. Import an SVG or generate a new drawing.")
        self.stats = tk.StringVar()
        self.model = tk.StringVar()
        self.machine_width = tk.StringVar()
        self.machine_height = tk.StringVar()
        self.feed = tk.StringVar()
        self.pen_up = tk.StringVar()
        self.pen_down = tk.StringVar()
        self.settle = tk.StringVar(value="0")
        self.port = tk.StringVar()
        self.baud = tk.StringVar(value="115200")

        self.build_layout()
        self.refresh()
        root.after(80, self.poll_results)

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

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        workspace = ttk.Frame(body)
        workspace.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        toolbar = ttk.Frame(workspace)
        toolbar.pack(fill="x", pady=(0, 7))
        ttk.Button(toolbar, text="Import SVG", command=self.import_svg).pack(side="left")
        ttk.Button(toolbar, text="Load sample", command=self.load_sample).pack(side="left", padx=6)
        ttk.Checkbutton(
            toolbar, text="Show pen-up travel", variable=self.show_travel, command=self.paint,
        ).pack(side="right")
        self.canvas = tk.Canvas(workspace, background=DESK, borderwidth=0, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.paint())
        ttk.Label(workspace, textvariable=self.source_name, style="Title.TLabel").pack(
            anchor="w", pady=(8, 0)
        )
        ttk.Label(workspace, textvariable=self.stats, style="Muted.TLabel").pack(anchor="w")

        tabs = ttk.Notebook(body)
        tabs.grid(row=0, column=1, sticky="ns")
        drawing = ttk.Frame(tabs, padding=12, width=310)
        machine = ttk.Frame(tabs, padding=12, width=310)
        for tab in (drawing, machine):
            tab.columnconfigure(1, weight=1)
        tabs.add(drawing, text="Drawing")
        tabs.add(machine, text="Machine")
        self.build_drawing_tab(drawing)
        self.build_machine_tab(machine)
        ttk.Separator(frame).pack(fill="x", pady=(8, 4))
        ttk.Label(frame, textvariable=self.status, style="Muted.TLabel", wraplength=730).pack(anchor="w")

    def build_drawing_tab(self, panel: ttk.Frame) -> None:
        ttk.Label(panel, text="Paper and toolpath", style="Title.TLabel").grid(row=0, columnspan=2, sticky="w")
        self.field(panel, 1, "Paper width (mm)", self.paper_width)
        self.field(panel, 2, "Paper height (mm)", self.paper_height)
        self.field(panel, 3, "Margin (mm)", self.margin)
        ttk.Checkbutton(panel, text="Order strokes by nearest endpoint", variable=self.optimize).grid(
            row=4, columnspan=2, sticky="w", pady=4
        )
        ttk.Button(panel, text="Fit to paper", command=self.apply_layout).grid(row=5, columnspan=2, sticky="ew")
        ttk.Separator(panel).grid(row=6, columnspan=2, sticky="ew", pady=12)

        ttk.Label(panel, text="Generate with Ollama", style="Title.TLabel").grid(row=7, columnspan=2, sticky="w")
        self.field(panel, 8, "Installed model tag", self.model)
        ttk.Label(panel, text="Drawing prompt", style="Muted.TLabel").grid(row=9, columnspan=2, sticky="w")
        self.prompt = tk.Text(panel, height=5, width=28, wrap="word", background=PAPER,
                              foreground=INK, padx=6, pady=4)
        self.prompt.grid(row=10, columnspan=2, sticky="ew", pady=(3, 7))
        self.prompt.insert("1.0", "Draw a mountain valley with a winding river and three pine trees.")
        self.generate_button = ttk.Button(panel, text="Generate drawing", command=self.generate)
        self.generate_button.grid(row=11, columnspan=2, sticky="ew")

    def build_machine_tab(self, panel: ttk.Frame) -> None:
        ttk.Label(panel, text="Plotter settings", style="Title.TLabel").grid(row=0, columnspan=2, sticky="w")
        for row, (label, variable) in enumerate((
            ("Usable X travel (mm)", self.machine_width),
            ("Usable Y travel (mm)", self.machine_height),
            ("Draw feed (mm/min)", self.feed),
            ("Pen up command", self.pen_up),
            ("Pen down command", self.pen_down),
            ("Pen settle (sec)", self.settle),
        ), start=1):
            self.field(panel, row, label, variable)
        ttk.Label(panel, text="Use your firmware’s verified pen commands.\nSet G54 XY zero at the paper’s lower left.",
                  style="Muted.TLabel").grid(row=7, columnspan=2, sticky="w", pady=(6, 0))
        ttk.Separator(panel).grid(row=8, columnspan=2, sticky="ew", pady=12)

        ttk.Label(panel, text="Arduino connection", style="Title.TLabel").grid(row=9, columnspan=2, sticky="w")
        ttk.Label(panel, text="Serial port").grid(row=10, column=0, sticky="w", pady=3)
        self.port_picker = ttk.Combobox(panel, textvariable=self.port, state="readonly", width=15)
        self.port_picker.grid(row=10, column=1, sticky="ew")
        self.field(panel, 11, "Baud rate", self.baud)
        ttk.Button(panel, text="Find ports", command=self.scan_ports).grid(row=12, column=0, sticky="ew", padx=(0, 7))
        self.inspect_button = ttk.Button(panel, text="Read GRBL", command=self.inspect)
        self.inspect_button.grid(row=12, column=1, sticky="ew")
        ttk.Label(panel, text="Opening the port can reset the Arduino.\nInspect while the plotter is idle.",
                  style="Muted.TLabel").grid(row=13, columnspan=2, sticky="w", pady=(6, 0))

    def field(self, panel: ttk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        ttk.Label(panel, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=3)
        ttk.Entry(panel, textvariable=variable, width=17).grid(row=row, column=1, sticky="ew")

    def refresh(self) -> None:
        try:
            dimensions = tuple(float(field.get()) for field in (self.paper_width, self.paper_height, self.margin))
        except ValueError as exc:
            raise ValueError("Enter numeric paper dimensions and margin on the Drawing tab.") from exc
        sheet = Sheet(*dimensions)
        fitted = fit_to_sheet(self.source, sheet)
        self.sheet = sheet
        self.drawing = order_strokes(fitted) if self.optimize.get() else fitted
        drawn, travel = path_lengths(self.drawing)
        self.stats.set(
            f"{self.sheet.width:g} × {self.sheet.height:g} mm  ·  {len(self.drawing):,} strokes"
            f"  ·  {drawn:,.0f} mm drawn  ·  {travel:,.0f} mm pen-up"
        )
        self.paint()

    def paint(self) -> None:
        canvas = self.canvas
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if min(width, height) < 76:
            return
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
        previous = (left, bottom)
        for stroke in self.drawing:
            points = tuple(coord for x, y in stroke for coord in (left + x * scale, bottom - y * scale))
            if self.show_travel.get():
                canvas.create_line(*previous, *points[:2], fill=TEAL, dash=(3, 4))
            canvas.create_line(*points, fill=INK, width=1.4, capstyle="round", joinstyle="round")
            previous = points[-2:]
        canvas.create_oval(left - 3, bottom - 3, left + 3, bottom + 3, fill=GREEN, outline="")
        canvas.create_text(left + 8, bottom + 8, text="0, 0", anchor="nw", fill=MUTED, font=(self.ui_font, 9))

    def apply_layout(self) -> None:
        try:
            self.refresh()
        except ValueError as exc:
            messagebox.showerror("Paper settings", str(exc), parent=self.root)
        else:
            self.status.set("Preview updated.")

    def set_drawing(self, name: str, source: Drawing) -> None:
        old_source = self.source
        self.source = source
        try:
            self.refresh()
        except ValueError:
            self.source = old_source
            raise
        self.source_name.set(name)
        self.revision += 1

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
        try:
            available = grbl.ports()
        except OSError as exc:
            messagebox.showerror("Find serial ports", str(exc), parent=self.root)
            return
        self.port_picker.configure(values=available)
        if self.port.get() not in available:
            self.port.set(available[0] if available else "")
        self.status.set(f"Found {len(available)} serial port(s)." if available else "No serial ports found.")

    def run_background(self, action, callback, button: ttk.Button, title: str) -> None:
        button.state(["disabled"])

        def work() -> None:
            try:
                result = action()
            except (OSError, ValueError) as exc:
                self.results.put((button, title, callback, None, str(exc)))
            else:
                self.results.put((button, title, callback, result, None))

        Thread(target=work, daemon=True).start()

    def poll_results(self) -> None:
        while True:
            try:
                button, title, callback, result, error = self.results.get_nowait()
            except Empty:
                break
            button.state(["!disabled"])
            try:
                if error is not None:
                    raise ValueError(error)
                callback(result)
            except ValueError as exc:
                self.status.set(f"{title} failed.")
                messagebox.showerror(title, str(exc), parent=self.root)
        self.root.after(80, self.poll_results)

    def generate(self) -> None:
        prompt = self.prompt.get("1.0", "end-1c")
        model = self.model.get()
        revision = self.revision
        self.status.set("Generating line art in Ollama…")

        def show(drawing: Drawing) -> None:
            if self.revision != revision:
                self.status.set("Drawing changed during generation. Generate again to replace it.")
                return
            self.set_drawing("Ollama drawing", drawing)
            self.status.set("Ollama drawing ready for preview.")

        self.run_background(lambda: ollama.generate_drawing(model, prompt), show,
                            self.generate_button, "Generate drawing")

    def inspect(self) -> None:
        port = self.port.get()
        try:
            baud = int(self.baud.get())
        except ValueError:
            messagebox.showerror("Read GRBL", "Enter a whole-number baud rate.", parent=self.root)
            return
        self.status.set(f"Reading GRBL on {port}…" if port else "Select a serial port.")

        def show(report: str) -> None:
            self.status.set(f"GRBL responded on {port}.")
            dialog, controls = self.text_dialog("GRBL connection report", report)

            def copy() -> None:
                dialog.clipboard_clear()
                dialog.clipboard_append(report)
                self.status.set("GRBL report copied.")

            ttk.Button(controls, text="Copy report", command=copy).pack(side="right")

        self.run_background(lambda: grbl.inspect(port, baud), show, self.inspect_button, "Read GRBL")

    def review(self) -> None:
        try:
            self.refresh()
            machine = Machine(
                float(self.machine_width.get()), float(self.machine_height.get()),
                float(self.feed.get()), self.pen_up.get(), self.pen_down.get(), float(self.settle.get()),
            )
            program = generate_gcode(self.drawing, self.sheet, machine)
        except ValueError as exc:
            error = str(exc)
            if "could not convert string to float" in error:
                error = "Enter the plotter’s X/Y travel, draw feed, and verified pen commands on the Machine tab."
            messagebox.showerror("Review G-code", error, parent=self.root)
            return
        lines = program.splitlines()
        preview = "\n".join(lines[:400])
        if len(lines) > 400:
            preview += f"\n\nShowing 400 of {len(lines):,} lines. Save to view the full program."
        dialog, controls = self.text_dialog("G-code review", preview)
        ttk.Button(controls, text="Save .gcode", style="Primary.TButton",
                   command=lambda: self.save_program(dialog, program)).pack(side="right")

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
        return dialog, controls


def main() -> None:
    root = tk.Tk()
    Studio(root)
    root.mainloop()
