from __future__ import annotations

import re
from dataclasses import dataclass
from math import dist, isfinite

from .drawing import Drawing, Sheet
from .firmware import ServoSettings
from .units import factor
from .gcode_preflight import ProgramPreflight, verify_program
from .paper_mount import machine_point, required_travel, validate_mount

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
    servo: ServoSettings | None = None
    paper_mount: str = 'bottom_left_x'
    seam_overlap: float = 0

    def __post_init__(self) -> None:
        validate_mount(self.paper_mount)
        if not all(0 < value <= 10_000 for value in (self.width, self.height)):
            raise ValueError("Enter the plotter's positive usable X and Y travel in mm.")
        if not 0.001 <= self.feed <= 100_000:
            raise ValueError("Enter a positive drawing feed rate in mm/min.")
        if not 0 <= self.settle <= 10:
            raise ValueError("Pen settle time must be between 0 and 10 seconds.")
        if not 0 <= self.seam_overlap <= 5:
            raise ValueError("Closed-loop overlap must be between 0 and 5 mm.")
        up_mode, up, up_value = pen_command(self.up)
        down_mode, down, down_value = pen_command(self.down)
        if up_mode != down_mode or up_value == down_value:
            raise ValueError("Use two distinct positions for the same pen actuator.")
        if self.servo is not None:
            if up_mode != "PWM":
                raise ValueError("The uploaded servo profile uses M3 S and M5 pen commands.")
            up_count = self.servo.timer_count(None if up == "M5" else up_value)
            down_count = self.servo.timer_count(None if down == "M5" else down_value)
            if up_count == down_count:
                raise ValueError("The pen commands select the same servo pulse. Choose distinct positions.")
        object.__setattr__(self, "up", up)
        object.__setattr__(self, "down", down)


@dataclass(frozen=True)
class GcodeReview:
    program: str
    units: str
    coordinate_step: float
    strokes_in: int
    strokes_omitted: int
    rounded_xy_duplicates: int
    preflight: ProgramPreflight

    def summary(self) -> str:
        rows = [f"Output coordinates: {self.coordinate_step:g} {self.units} grid.",
                f"Strokes in output: {self.strokes_in - self.strokes_omitted:,} of {self.strokes_in:,}."]
        rows.append(f"Offline preflight passed: {self.preflight.plotted_segments:,} linear drawing segments.")
        if self.strokes_omitted:
            rows.append(f"Warning: {self.strokes_omitted:,} stroke(s) have no XY motion at this precision and will not be drawn.")
        if self.rounded_xy_duplicates:
            rows.append(f"Adjacent points at the same output XY position: {self.rounded_xy_duplicates:,}.")
        return "\n".join(rows)


def generate_gcode(drawing: Drawing, sheet: Sheet, machine: Machine, units: str = "mm", *, dry_run: bool = False) -> str:
    """Keep the command-only API for exports and plot jobs."""
    return review_gcode(drawing, sheet, machine, units, dry_run=dry_run).program


def review_gcode(drawing: Drawing, sheet: Sheet, machine: Machine, units: str = "mm", *, dry_run: bool = False) -> GcodeReview:
    """Generate commands and describe lost XY motion from the same pass."""
    scale = factor(units)
    precision = 5 if units == "in" else 3
    def coordinate(value):
        return f"{value / scale:.{precision}f}"

    if not drawing:
        raise ValueError("Create or import a drawing first.")
    x_travel, y_travel = required_travel(sheet.width, sheet.height, machine.paper_mount)
    if x_travel > machine.width or y_travel > machine.height:
        raise ValueError("The paper does not fit the configured usable X/Y travel.")
    lines = ["(SCRIB3 pen-up test)" if dry_run else "(SCRIB3 pen plotter job)", f"{'G20' if units == 'in' else 'G21'} G90 G94 G17 G54 G49"]

    def actuate(command: str) -> None:
        # Raw Z pen commands are calibrated in mm; adapt them to the job units.
        if units == "in" and (match := Z_COMMAND.fullmatch(command)):
            mode, position, feed = match.groups()
            command = f"{mode} Z{coordinate(float(position))}"
            if feed:
                command += f" F{coordinate(float(feed))}"
        lines.append(command)
        if machine.settle:
            lines.append(f"G4 P{machine.settle:.3f}")

    actuate(machine.up)
    omitted = duplicates = 0
    for stroke in drawing:
        # Only exact, explicitly closed source loops get overlap. Do not infer
        # closure from rounded coordinates or bridge deliberate small gaps.
        stroke = overlap_closed_stroke(stroke, machine.seam_overlap)
        points: list[tuple[float, float]] = []
        for x, y in stroke:
            if not (0 <= x <= sheet.width + 1e-8 and 0 <= y <= sheet.height + 1e-8):
                raise ValueError("A plotting point is outside the paper.")
            mx, my = machine_point(x, y, sheet.height, machine.paper_mount)
            point = (float(coordinate(mx)) * scale, float(coordinate(my)) * scale)
            if abs(point[0]) > machine.width + 1e-9 or abs(point[1]) > machine.height + 1e-9:
                raise ValueError("A rounded plotting point is outside usable X/Y travel.")
            if not points or point != points[-1]:
                points.append(point)
            else:
                duplicates += 1
        if len(points) < 2:
            omitted += 1
            continue
        x, y = points[0]
        lines.append(f"G0 X{coordinate(x)} Y{coordinate(y)}")
        actuate(machine.up if dry_run else machine.down)
        for index, (x, y) in enumerate(points[1:]):
            feed = f" F{coordinate(machine.feed)}" if index == 0 else ""
            lines.append(f"G1 X{coordinate(x)} Y{coordinate(y)}{feed}")
        actuate(machine.up)
    if omitted == len(drawing):
        raise ValueError(f"No stroke is long enough to plot at {10 ** -precision:g} {units} resolution.")
    program = "\n".join(lines) + "\n"
    preflight = verify_program(program, units=units, machine=machine,
                               expected_strokes=len(drawing) - omitted, dry_run=dry_run)
    return GcodeReview(program, units, 10 ** -precision, len(drawing), omitted, duplicates, preflight)


def overlap_closed_stroke(stroke, distance):
    """Retrace at most one lap along existing segments, never beyond the path."""
    if distance <= 0 or len(stroke) < 4 or stroke[0] != stroke[-1]:
        return stroke
    extra = []
    remaining = distance
    for start, end in zip(stroke, stroke[1:]):
        length = dist(start, end)
        if length == 0:
            continue
        if remaining < length:
            ratio = remaining / length
            extra.append(tuple(a + (b-a)*ratio for a, b in zip(start, end)))
            break
        extra.append(end)
        remaining -= length
        if remaining <= 1e-12:
            break
    return tuple(stroke) + tuple(extra)
