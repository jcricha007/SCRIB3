from __future__ import annotations

import re
from dataclasses import dataclass
from math import isfinite

from .drawing import Drawing, Sheet

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
Z_COMMAND = re.compile(rf"(G[01])[ \t]*Z({NUMBER})(?:[ \t]*F({NUMBER}))?", re.ASCII)
PWM_COMMAND = re.compile(rf"M3[ \t]*S({NUMBER})", re.ASCII)


def pen_command(value: str) -> tuple[str, str, float]:
    """Return the actuator family, normalized command, and position."""
    value = value.strip().upper()
    if len(value) > 50:
        raise ValueError("Enter one short G-code command per pen position.")
    if match := Z_COMMAND.fullmatch(value):
        mode, position, feed = match.groups()
        z = float(position)
        if not isfinite(z) or abs(z) > 10_000:
            raise ValueError("Enter a valid Z position in millimeters.")
        if mode == "G1" and (feed is None or not 0.001 <= float(feed) <= 100_000):
            raise ValueError("A G1 pen command requires its own positive Z feed rate.")
        if mode == "G0" and feed is not None:
            raise ValueError("Use G0 Z without a feed rate, or G1 Z with a feed rate.")
        return "Z", f"{mode} Z{z:.3f}" + (f" F{float(feed):.3f}" if feed else ""), round(z, 3)
    if match := PWM_COMMAND.fullmatch(value):
        speed = float(match.group(1))
        if not 0 <= speed <= 100_000:
            raise ValueError("Enter a valid nonnegative spindle S value.")
        return "PWM", f"M3 S{speed:.3f}", round(speed, 3)
    if value == "M5":
        return "PWM", "M5", 0
    raise ValueError("Enter a verified G0/G1 Z, M3 S, or M5 pen command.")


@dataclass(frozen=True)
class Machine:
    width: float
    height: float
    feed: float
    up: str
    down: str
    settle: float = 0

    def __post_init__(self) -> None:
        if not all(0 < value <= 10_000 for value in (self.width, self.height)):
            raise ValueError("Enter the plotter's positive usable X and Y travel in mm.")
        if not 0.001 <= self.feed <= 100_000:
            raise ValueError("Enter a positive drawing feed rate in mm/min.")
        if not 0 <= self.settle <= 10:
            raise ValueError("Pen settle time must be between 0 and 10 seconds.")
        up_mode, up, up_value = pen_command(self.up)
        down_mode, down, down_value = pen_command(self.down)
        if up_mode != down_mode or up_value == down_value:
            raise ValueError("Use two distinct positions for the same pen actuator.")
        object.__setattr__(self, "up", up)
        object.__setattr__(self, "down", down)


def generate_gcode(drawing: Drawing, sheet: Sheet, machine: Machine) -> str:
    if not drawing:
        raise ValueError("Create or import a drawing first.")
    if sheet.width > machine.width or sheet.height > machine.height:
        raise ValueError("The paper does not fit the configured usable X/Y travel.")
    lines = ["(SCRIB3 pen plotter job)", "G21 G90 G94 G17 G54 G49"]

    def actuate(command: str) -> None:
        lines.append(command)
        if machine.settle:
            lines.append(f"G4 P{machine.settle:.3f}")

    actuate(machine.up)
    plotted = False
    for stroke in drawing:
        points: list[tuple[float, float]] = []
        for x, y in stroke:
            if not (0 <= x <= sheet.width + 1e-8 and 0 <= y <= sheet.height + 1e-8):
                raise ValueError("A plotting point is outside the paper.")
            point = (round(x, 3), round(y, 3))
            if point[0] > machine.width or point[1] > machine.height:
                raise ValueError("A rounded plotting point is outside usable X/Y travel.")
            if not points or point != points[-1]:
                points.append(point)
        if len(points) < 2:
            continue
        x, y = points[0]
        lines.append(f"G0 X{x:.3f} Y{y:.3f}")
        actuate(machine.down)
        for index, (x, y) in enumerate(points[1:]):
            feed = f" F{machine.feed:.3f}" if index == 0 else ""
            lines.append(f"G1 X{x:.3f} Y{y:.3f}{feed}")
        actuate(machine.up)
        plotted = True
    if not plotted:
        raise ValueError("No stroke is long enough to plot at 0.001 mm resolution.")
    return "\n".join(lines) + "\n"
