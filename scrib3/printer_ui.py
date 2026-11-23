"""Calibrated Bambu output review and saved holder settings."""

from dataclasses import asdict
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .atomic_export import write_atomic_export
from .printer_output import Holder, PRINTERS, plan_printer


class PrinterWindow:
    def __init__(self, editor, printer):
        self.editor = editor
        self.printer = printer
        self.prefs = editor.studio.preset_file.with_name("holder-" + printer.lower() + ".json")
        self.window = tk.Toplevel(editor.root)
        self.window.title("SCRIB3 | " + printer)
        panel = ttk.Frame(self.window, padding=12)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Measured pen-holder calibration", style="Title.TLabel").grid(
            row=0, columnspan=4, sticky="w"
        )
        ttk.Label(
            panel,
            text="Tip offsets are pen tip minus nozzle. Clearances limit nozzle travel. All lengths are mm.",
            wraplength=510,
        ).grid(row=1, columnspan=4, pady=6)
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
            row, col = 2 + i // 2, (i % 2) * 2
            ttk.Label(panel, text=label).grid(row=row, column=col, sticky="w", padx=4)
            v = tk.StringVar(value=str(data.get(k, "")))
            self.fields[k] = v
            ttk.Entry(panel, textvariable=v, width=10).grid(row=row, column=col + 1, pady=2)
        self.dry = tk.BooleanVar(value=True)
        self.fit = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, text="Pen-up test", variable=self.dry).grid(
            row=7, columnspan=2, sticky="w"
        )
        ttk.Checkbutton(panel, text="Shrink paper to reach", variable=self.fit).grid(
            row=7, column=2, columnspan=2
        )
        self.canvas = tk.Canvas(panel, width=510, height=240, bg="#192330", highlightthickness=0)
        self.canvas.grid(row=8, columnspan=4, pady=8)
        self.status = tk.StringVar(value="Enter measured calibration, then preview.")
        ttk.Label(panel, textvariable=self.status, wraplength=510).grid(
            row=9, columnspan=4, sticky="w"
        )
        ttk.Button(panel, text="Preview", command=self.preview).grid(row=10, column=0, pady=8)
        ttk.Button(panel, text="Save holder", command=self.save).grid(row=10, column=1)
        ttk.Button(panel, text="Export G-code / 3MF", command=self.export).grid(
            row=10, column=2, columnspan=2
        )

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
        self.canvas.delete("all")
        try:
            plan = plan_printer(
                self.editor.board, self.holder(), fit=self.fit.get(), dry=self.dry.get()
            )
        except ValueError as e:
            self.status.set(str(e))
            return
        h = plan.holder
        _, bw, bh = PRINTERS[h.printer]
        k = min(490 / bw, 220 / bh)
        ox = (510 - bw * k) / 2

        def pt(x, y):
            return ox + x * k, 230 - y * k

        self.canvas.create_rectangle(*pt(0, 0), *pt(bw, bh), fill="#3a4755")
        a, b, c, d = h.reach()
        left = (a + c - plan.width) / 2
        front = (b + d - plan.height) / 2
        self.canvas.create_rectangle(*pt(a, b), *pt(c, d), outline="#55c8dc")
        self.canvas.create_rectangle(
            *pt(left, front), *pt(left + plan.width, front + plan.height), fill="white"
        )
        for color, paths in plan.passes:
            for path in paths:
                self.canvas.create_line(
                    *[v for x, y in path for v in pt(x + h.offset_x, y + h.offset_y)], fill=color
                )
        self.status.set(
            f"{100*plan.scale:.1f}% | Paper {plan.width:.1f} x {plan.height:.1f} mm | front-left {left:.1f}, {front:.1f} mm | {len(plan.passes)} pens | {plan.seconds/60:.1f} min motion plus homing and pauses."
        )
        return plan

    def export(self):
        plan = self.preview()
        if plan is None:
            return
        if not messagebox.askokcancel(
            "Review printer job",
            self.status.get()
            + "\n\nHome with pen and any obstructing attachment removed. Install the calibrated holder and pen at the first pause. Review the exported plate in Bambu Studio.",
            parent=self.window,
        ):
            return
        target = filedialog.asksaveasfilename(
            parent=self.window,
            initialfile=f"SCRIB3-{self.printer}.gcode.3mf",
            defaultextension=".3mf",
            filetypes=[("Bambu sliced plate", "*.3mf"), ("G-code", "*.gcode")],
        )
        if target:
            try:
                plan.export(Path(target))
                self.status.set("Saved " + Path(target).name)
            except (OSError, ValueError) as e:
                self.status.set(str(e))
