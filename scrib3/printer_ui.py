"""Calibrated Bambu output review and saved holder settings."""

from dataclasses import asdict
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from . import theme
from .atomic_export import write_atomic_export
from .board import Board
from .motion_profile import START_HOLD_SECONDS
from .printer_output import Holder, P1S_FINISH_HOLD_SECONDS, PRINTERS, plan_printer


class PrinterWindow:
    def __init__(self, studio, printer, *, parent=None, container=None):
        self.studio = studio
        self.printer = printer
        self.prefs = studio.preset_file.with_name("holder-" + printer.lower() + ".json")
        embedded = container is not None
        if container is None:
            self.window = tk.Toplevel(parent or studio.root)
            self.window.title("SCRIB3 | " + printer)
            self.window.geometry("920x620")
            self.window.minsize(720, 560)
            container = self.window
        else:
            self.window = container.winfo_toplevel()
        body = ttk.Frame(container, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        view = ttk.Frame(body)
        view.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        ttk.Label(view, text=f"{printer} plate preview", style="Title.TLabel").pack(anchor="w", pady=(0, 6))
        self.plan = None
        self.canvas = tk.Canvas(view, width=150, height=180, bg=theme.DESK,
                                highlightthickness=1, highlightbackground=theme.BORDER)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self.draw_plate)
        self.status = tk.StringVar(value="Enter measured calibration, then preview.")
        status = ttk.Label(view, textvariable=self.status, style="Muted.TLabel", wraplength=380)
        status.pack(anchor="w", pady=(6, 0))
        view.bind("<Configure>", lambda event: status.configure(wraplength=max(100, event.width - 10)))

        panel = ttk.Frame(body)
        panel.grid(row=0, column=1, sticky="ns")
        panel.columnconfigure((0, 1), weight=1, uniform="holder")
        ttk.Label(panel, text="Pen-holder calibration (mm)", style="Title.TLabel").grid(row=0, columnspan=2, sticky="w")
        ttk.Label(panel, text="Offsets are pen tip minus nozzle. Clearances limit nozzle travel.",
                  wraplength=295, style="Muted.TLabel").grid(row=1, columnspan=2, sticky="w", pady=(3, 6))
        data = dict(left=5, front=30, right=5, back=5, draw_feed=1500, travel_feed=1500)
        try:
            saved = json.loads(self.prefs.read_text())
            Holder(**saved).reach()
            if saved["printer"] == printer:
                data.update(saved)
        except (OSError, ValueError, TypeError, KeyError):
            pass
        self.fields = {}
        labels = [
            ("offset_x", "Tip offset X"),
            ("offset_y", "Tip offset Y"),
            ("contact_z", "Contact Z"),
            ("lift_z", "Lift Z"),
            ("left", "Left clearance"),
            ("front", "Front clearance"),
            ("right", "Right clearance"),
            ("back", "Rear clearance"),
            ("draw_feed", "Draw mm/min"),
            ("travel_feed", "Travel mm/min"),
        ]
        for i, (k, label) in enumerate(labels):
            field = ttk.Frame(panel)
            field.grid(row=2 + i // 2, column=i % 2, sticky="ew", padx=(0, 6), pady=2)
            ttk.Label(field, text=label).pack(anchor="w")
            v = tk.StringVar(value=str(data.get(k, "")))
            self.fields[k] = v
            ttk.Entry(field, textvariable=v, width=13, style="Compact.TEntry").pack(fill="x")
        ttk.Button(panel, text="Save holder", command=self.save).grid(row=7, column=0, sticky="ew", padx=(0, 5), pady=5)
        self.dry = tk.BooleanVar(value=True)
        self.fit = tk.BooleanVar(value=False)
        ttk.Separator(panel).grid(row=8, columnspan=2, sticky="ew", pady=5)
        ttk.Label(panel, text="Output", style="Section.TLabel").grid(row=9, columnspan=2, sticky="w")
        self.dry_button = ttk.Checkbutton(panel, text="Pen-up test", variable=self.dry)
        self.dry_button.grid(row=11, column=0, sticky="w")
        ttk.Checkbutton(panel, text="Shrink paper to reach", variable=self.fit).grid(row=11, column=1, sticky="w")
        if not embedded:
            ttk.Button(panel, text="Preview", command=self.preview).grid(row=13, column=0, sticky="ew", padx=(0, 5), pady=5)
        ttk.Button(panel, text="Export G-code / 3MF", style="Primary.TButton", command=self.export).grid(
            row=13, column=0 if embedded else 1, columnspan=2 if embedded else 1, sticky="ew", pady=4)
        if printer == "P1S":
            from .p1s_workflow import BOARD, DRY_A4, REGISTER, HolderGuide
            self.target = tk.StringVar(value=BOARD)
            ttk.Button(panel, text="Guided holder setup", command=lambda: HolderGuide(self)).grid(
                row=7, column=1, sticky="ew")
            jobs = ttk.Combobox(panel, textvariable=self.target, state="readonly", values=(BOARD, DRY_A4, REGISTER))
            jobs.grid(row=10, columnspan=2, sticky="ew", pady=4)
            jobs.bind("<<ComboboxSelected>>", self.target_changed)
            self.travel = tk.BooleanVar(value=False)
            ttk.Checkbutton(panel, text="Show pen-up travel", variable=self.travel, command=self.preview).grid(
                row=12, columnspan=2, sticky="w")
            ttk.Button(panel, text="Open in Bambu Studio", command=lambda: self.export(open_studio=True)).grid(
                row=14, columnspan=2, sticky="ew")

    def target_changed(self, *_):
        from .p1s_workflow import DRY_A4
        self.dry.set(True)
        self.dry_button.state(["disabled"] if self.target.get() == DRY_A4 else ["!disabled"])
        self.plan = None
        self.draw_plate()
        self.status.set("Preview the selected P1S job with the measured holder.")

    def holder(self):
        return Holder(self.printer, **{k: float(v.get()) for k, v in self.fields.items()})

    def save(self):
        try:
            h = self.holder()
            h.reach()
            self.prefs.parent.mkdir(parents=True, exist_ok=True)
            write_atomic_export(
                self.prefs, lambda p: p.write_text(json.dumps(asdict(h)), encoding="utf-8")
            )
            self.status.set("Saved holder calibration.")
        except (OSError, ValueError) as e:
            self.status.set(str(e))

    def preview(self):
        try:
            editor = getattr(self.studio, "board_editor", None)
            board, dry = editor.board if editor else Board(), self.dry.get()
            if self.printer == "P1S":
                from .p1s_workflow import BOARD, DRY_A4, qualification_board
                target = self.target.get()
                if target != BOARD:
                    board = qualification_board(target)
                    dry = dry or target == DRY_A4
            plan = plan_printer(board, self.holder(), fit=self.fit.get(), dry=dry)
        except ValueError as e:
            self.plan = None
            self.draw_plate()
            self.status.set(str(e))
            return
        self.plan = plan
        self.draw_plate()
        a, b, c, d = plan.holder.reach()
        left, front = (a + c - plan.width) / 2, (b + d - plan.height) / 2
        self.status.set(
            f"{100*plan.scale:.1f}% · Paper {plan.width:.1f} × {plan.height:.1f} mm · Front-left {left:.1f}, {front:.1f} mm · "
            f"{len(plan.passes)} pens · {plan.seconds/60:.1f} min motion plus homing and pauses."
        )
        return plan

    def draw_plate(self, _event=None):
        cv = self.canvas
        cv.delete("all")
        width, height = max(64, cv.winfo_width()), max(64, cv.winfo_height())
        _, bw, bh = PRINTERS[self.printer]
        k = min((width - 48) / bw, (height - 48) / bh)
        ox, oy = (width - bw*k) / 2, (height + bh*k) / 2

        def pt(x, y):
            return ox + x*k, oy - y*k

        cv.create_rectangle(*pt(0, 0), *pt(bw, bh), fill="#c8d4e0", outline="#8b9caf", tags="plate")
        for mm in range(50, int(bw), 50):
            cv.create_line(*pt(mm, 0), *pt(mm, bh), fill="#b4c3d3")
        for mm in range(50, int(bh), 50):
            cv.create_line(*pt(0, mm), *pt(bw, mm), fill="#b4c3d3")
        cv.create_text(width / 2, oy + 12, text=f"{bw:g} × {bh:g} mm", fill=theme.MUTED)
        plan = self.plan
        if plan is None:
            return
        h = plan.holder
        a, b, c, d = h.reach()
        left, front = (a + c - plan.width) / 2, (b + d - plan.height) / 2
        cv.create_rectangle(*pt(left, front), *pt(left + plan.width, front + plan.height),
                            fill=theme.PAPER, outline=theme.BORDER)
        cv.create_rectangle(*pt(a, b), *pt(c, d), outline=theme.ACCENT, dash=(4, 3))
        previous = None
        for color, paths in plan.passes:
            for path in paths:
                if self.printer == "P1S" and self.travel.get() and previous is not None:
                    self.canvas.create_line(*pt(*previous), *pt(path[0][0]+h.offset_x, path[0][1]+h.offset_y),
                                            fill=theme.TRAVEL, dash=(3, 3))
                previous = (path[-1][0]+h.offset_x, path[-1][1]+h.offset_y)
                self.canvas.create_line(
                    *[v for x, y in path for v in pt(x + h.offset_x, y + h.offset_y)], fill=color
                )

    def export(self, open_studio=False):
        plan = self.preview()
        if plan is None:
            return
        instructions = ("Home with the pen and any obstructing attachment removed. Install the calibrated "
                        "holder and pen at the setup pause.")
        if self.printer == "P1S":
            instructions += (f" After arrival, the pen waits {START_HOLD_SECONDS} seconds above the first point. "
                             f"The file finishes with a {P1S_FINISH_HOLD_SECONDS}-second raised hold at the last point.")
        if not messagebox.askokcancel(
            "Review printer job",
            self.status.get() + "\n\n" + instructions + " Review the exported plate in Bambu Studio.",
            parent=self.window,
        ):
            return
        label = self.target.get().replace(" ", "-") if self.printer == "P1S" else self.printer
        target = filedialog.asksaveasfilename(
            parent=self.window,
            initialfile=f"SCRIB3-{self.printer}-{label}.gcode.3mf" if self.printer == "P1S" else f"SCRIB3-{self.printer}.gcode.3mf",
            defaultextension=".3mf",
            filetypes=[("Bambu sliced plate", "*.3mf")] if open_studio else [("Bambu sliced plate", "*.3mf"), ("G-code", "*.gcode")],
        )
        if target:
            try:
                path = Path(target)
                # The macOS save panel accepts a single extension. Studio identifies sliced
                # plates by the whole .gcode.3mf suffix when opening the saved file.
                if self.printer == "P1S" and path.suffix.lower() == ".3mf" and not path.name.lower().endswith(".gcode.3mf"):
                    path = path.with_suffix(".gcode.3mf")
                    if path.exists() and not messagebox.askyesno(
                        "Replace sliced plate", f"Replace {path.name}?", parent=self.window
                    ):
                        return
                if open_studio and not path.name.lower().endswith(".gcode.3mf"):
                    raise ValueError("Use the .gcode.3mf extension to open a sliced plate in Bambu Studio.")
                plan.export(path)
                self.status.set("Saved " + path.name)
                if open_studio:
                    from .p1s_workflow import open_in_studio
                    try:
                        open_in_studio(path)
                        self.status.set("Opened " + path.name + " in Bambu Studio.")
                    except (ValueError, OSError) as exc:
                        self.status.set(f"Saved {path.name}. {exc}")
            except (OSError, ValueError) as e:
                self.status.set(str(e))
