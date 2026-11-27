"""P1S holder measurements, registration jobs and local Bambu Studio handoff."""

from dataclasses import asdict
from math import isfinite
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk

from .board import Board, Mark
from .geometry import shape
from .printer_output import Holder

BOARD = "Current drawing board"
DRY_A4 = "A4 pen-up footprint"
REGISTER = "Two-pen registration"


def qualification_board(target):
    dark, blue = "#242c39", "#286aa1"
    if target == DRY_A4:
        return Board(
            297,
            210,
            (
                Mark(dark, shape("Rectangle", (5, 5), (292, 205))),
                Mark(dark, ((145, 105), (152, 105))),
                Mark(dark, ((148.5, 101.5), (148.5, 108.5))),
            ),
        )
    if target != REGISTER:
        raise ValueError("Choose a P1S test pattern.")
    marks = [Mark(dark, shape("Rectangle", (5, 5), (45, 45)))]
    for x, y in ((12, 12), (38, 12), (12, 38), (38, 38), (25, 25)):
        marks.extend(
            (
                Mark(dark, ((x - 2, y), (x + 2, y))),
                Mark(dark, ((x, y - 2), (x, y + 2))),
                Mark(blue, ((x - 3, y), (x, y - 3), (x + 3, y), (x, y + 3), (x - 3, y))),
            )
        )
    return Board(50, 50, tuple(marks), pen_order=(dark, blue))


def open_in_studio(path):
    path = Path(path).resolve()
    if not path.is_file() or not path.name.lower().endswith(".gcode.3mf"):
        raise ValueError("Choose a saved sliced .gcode.3mf plate.")
    configured = os.environ.get("SCRIB3_BAMBU_STUDIO")
    if configured:
        exe = Path(configured).expanduser()
        if not exe.is_file():
            raise ValueError("SCRIB3_BAMBU_STUDIO must point to the Bambu Studio executable.")
        command = [str(exe)]
    elif sys.platform == "darwin":
        result = subprocess.run(
            ["/usr/bin/open", "-a", "BambuStudio", str(path)], capture_output=True, text=True
        )
        if result.returncode:
            raise OSError(result.stderr.strip() or "Bambu Studio could not open the plate.")
        return
    else:
        exe = shutil.which("bambu-studio") or shutil.which("BambuStudio")
        if not exe and sys.platform == "win32":
            roots = (os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA"))
            exe = next(
                (
                    p
                    for root in roots
                    if root
                    for sub in ("Bambu Studio", "BambuStudio", "Programs/Bambu Studio")
                    for p in [Path(root) / sub / "bambu-studio.exe"]
                    if p.is_file()
                ),
                None,
            )
        if exe:
            command = [str(exe)]
        elif (
            sys.platform.startswith("linux")
            and shutil.which("flatpak")
            and subprocess.run(
                ["flatpak", "info", "com.bambulab.BambuStudio"], capture_output=True
            ).returncode
            == 0
        ):
            command = ["flatpak", "run", "com.bambulab.BambuStudio"]
        else:
            raise OSError("Install Bambu Studio or set SCRIB3_BAMBU_STUDIO to its executable.")
    subprocess.Popen([*command, str(path)])


class HolderGuide:
    def __init__(self, output):
        self.output = output
        self.window = tk.Toplevel(output.window)
        self.window.title("SCRIB3 | P1S holder setup")
        self.window.transient(output.window)
        self.panel = ttk.Frame(self.window, padding=14)
        self.panel.pack(fill="both", expand=True)
        self.step = 0
        self.measured = {key: tk.StringVar(value=v.get()) for key, v in output.fields.items()}
        for key in ("nozzle_x", "nozzle_y", "tip_x", "tip_y"):
            self.measured[key] = tk.StringVar()
        self.pages = (
            (
                "Measure tip offset",
                "Use the same XY reference for the tip and nozzle at one carriage position. "
                "Enter both measured points in mm, or enter your measured tip-minus-nozzle offsets below.",
                (
                    ("nozzle_x", "Nozzle X"),
                    ("nozzle_y", "Nozzle Y"),
                    ("tip_x", "Pen tip X"),
                    ("tip_y", "Pen tip Y"),
                    ("offset_x", "Offset X"),
                    ("offset_y", "Offset Y"),
                ),
            ),
            (
                "Measure pen heights",
                "On a cool machine with your paper and holder, enter the measured Z at light "
                "contact and a higher Z that clears the sheet and fixtures during travel.",
                (("contact_z", "Contact Z (mm)"), ("lift_z", "Lift Z (mm)")),
            ),
            (
                "Check travel clearances",
                "Enter clearances for the nozzle with this holder and clips. "
                "P1S front-left exclusion requires 18 mm left or 28 mm front clearance.",
                (
                    ("left", "Left (mm)"),
                    ("front", "Front (mm)"),
                    ("right", "Right (mm)"),
                    ("back", "Rear (mm)"),
                ),
            ),
            (
                "Review holder",
                "Apply these measurements to the P1S output window. Save holder there to reuse them.",
                (),
            ),
        )
        self.status = tk.StringVar()
        self.show()

    def show(self):
        for w in self.panel.winfo_children():
            w.destroy()
        title, hint, fields = self.pages[self.step]
        ttk.Label(self.panel, text=f"{self.step + 1} / 4   {title}", style="Title.TLabel").grid(
            row=0, columnspan=2, sticky="w"
        )
        ttk.Label(self.panel, text=hint, wraplength=410).grid(
            row=1, columnspan=2, sticky="w", pady=6
        )
        for row, (key, label) in enumerate(fields, 2):
            ttk.Label(self.panel, text=label).grid(row=row, column=0, sticky="w")
            ttk.Entry(self.panel, textvariable=self.measured[key], width=16).grid(row=row, column=1)
        row = 2 + len(fields)
        ttk.Label(self.panel, textvariable=self.status, wraplength=410).grid(
            row=row, columnspan=2, sticky="w", pady=8
        )
        if self.step:
            ttk.Button(self.panel, text="Back", command=self.back).grid(
                row=row + 1, column=0, sticky="w"
            )
        ttk.Button(
            self.panel, text="Apply measurements" if self.step == 3 else "Next", command=self.next
        ).grid(row=row + 1, column=1, sticky="e")

    def back(self):
        self.step -= 1
        self.status.set("")
        self.show()

    def next(self):
        try:
            if self.step == 0:
                readings = [
                    self.measured[k].get().strip()
                    for k in ("nozzle_x", "nozzle_y", "tip_x", "tip_y")
                ]
                if any(readings):
                    nx, ny, tx, ty = map(float, readings)
                    self.measured["offset_x"].set(f"{tx - nx:.6f}")
                    self.measured["offset_y"].set(f"{ty - ny:.6f}")
                if not all(
                    isfinite(float(self.measured[k].get())) for k in ("offset_x", "offset_y")
                ):
                    raise ValueError("Enter finite tip offsets.")
            if self.step == 1:
                down, up = [float(self.measured[k].get()) for k in ("contact_z", "lift_z")]
                if not 0 <= round(down, 3) < round(up, 3) <= 200:
                    raise ValueError("Enter a contact Z and a higher lift Z.")
            self.status.set("")
            if self.step >= 2:
                holder = Holder(
                    "P1S", **{k: float(self.measured[k].get()) for k in self.output.fields}
                )
                x0, y0, x1, y1 = holder.reach()
                self.status.set(
                    f"Reachable pen area {x1 - x0:.1f} × {y1 - y0:.1f} mm. "
                    f"Tip offset ({holder.offset_x:g}, {holder.offset_y:g}) mm. "
                    f"Contact / lift {holder.contact_z:g} / {holder.lift_z:g} mm."
                )
            if self.step == 3:
                for k, v in asdict(holder).items():
                    if k in self.output.fields:
                        self.output.fields[k].set(str(v))
                self.output.target.set(DRY_A4)
                self.output.target_changed()
                self.output.status.set(
                    "Holder applied. Preview the A4 footprint and select shrink to reach if needed."
                )
                self.window.destroy()
            else:
                self.step += 1
                self.show()
        except (ValueError, OverflowError) as exc:
            self.status.set(str(exc))
