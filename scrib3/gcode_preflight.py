"""Offline verification for SCRIB3's generated pen-plotter program only."""

from dataclasses import dataclass
from math import isfinite
import re

from .motion_profile import START_HOLD_SECONDS

NUMBER = r"[+-]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)"
XY = re.compile(rf"(G[01]) X({NUMBER}) Y({NUMBER})(?: F({NUMBER}))?\Z")
Z = re.compile(rf"(G[01]) Z({NUMBER})(?: F({NUMBER}))?\Z")
PWM = re.compile(rf"M3 S({NUMBER})\Z")
DWELL = re.compile(rf"G4 P({NUMBER})\Z")


START_DWELL = f"G4 P{START_HOLD_SECONDS:.3f}"


@dataclass(frozen=True)
class ProgramPreflight:
    command_count: int
    pen_up_travels: int
    plotted_segments: int


def _actuator(line, expected, scale, tolerance):
    if line == expected == "M5":
        return True
    actual_z, expected_z = Z.fullmatch(line), Z.fullmatch(expected)
    if actual_z and expected_z and actual_z[1] == expected_z[1]:
        for index in (2, 3):
            a, b = actual_z[index], expected_z[index]
            if (a is None) != (b is None):
                return False
            if a is not None and abs(float(a) * scale - float(b)) > tolerance:
                return False
        return actual_z[3] is None or float(actual_z[3]) > 0
    actual_pwm, expected_pwm = PWM.fullmatch(line), PWM.fullmatch(expected)
    return bool(actual_pwm and expected_pwm and float(actual_pwm[1]) == float(expected_pwm[1]))


def verify_program(program, *, units, machine, expected_strokes, dry_run=False):
    """Verify state and bounds from actual serialized commands, without GRBL."""
    if units not in {"mm", "in"} or not isinstance(program, str) or len(program) > 12_100_000:
        raise ValueError("Invalid or oversized generated program.")
    scale = 25.4 if units == "in" else 1
    step = (0.00001 if units == "in" else 0.001) * scale
    z_tol = step / 2 + 1e-10
    lines = program.splitlines()
    comment = "(SCRIB3 pen-up test)" if dry_run else "(SCRIB3 pen plotter job)"
    modes = ("G20" if units == "in" else "G21") + " G90 G94 G17 G54 G49"
    if len(lines) < 7 or lines[:2] != [comment, modes]:
        raise ValueError("G-code preflight: expected explicit job modes and lift sequence.")
    if len(lines) > 150001 or any(len(line) > 79 or not line.isascii() for line in lines):
        raise ValueError("G-code preflight: supported GRBL line limits exceeded.")

    state = "initial"
    dwell_pending = False
    position = None
    travels = plotted = segments = 0
    lower_x, upper_x = (-machine.width, 0) if machine.paper_mount == "top_left_y" else (0, machine.width)
    for index, line in enumerate(lines[2:], 3):
        def refuse(reason):
            raise ValueError(f"G-code preflight line {index}: {reason}.")

        if state == "first_point":
            if line != START_DWELL:
                refuse(f"missing {START_HOLD_SECONDS}-second pen-up hold at the first point")
            state = "travelled"
            continue

        if dwell_pending:
            delay = DWELL.fullmatch(line)
            if not delay or not 0 <= float(delay[1]) <= 10 or abs(float(delay[1]) - machine.settle) > .0005 + 1e-10:
                refuse("missing or mismatched pen settle dwell")
            dwell_pending = False
            continue

        if state == "lifted" and travels == expected_strokes:
            refuse("unexpected command after the final pen lift")

        if state in {"initial", "travelled"} or (state == "drawing" and not XY.fullmatch(line)):
            expected = machine.down if state == "travelled" and not dry_run else machine.up
            if state == "drawing" and not segments:
                refuse("stroke did not contain a drawing move")
            if not _actuator(line, expected, scale, z_tol):
                refuse("unexpected pen actuator command")
            if state == "travelled":
                state, segments = "drawing", 0
            else:
                state = "lifted"
            dwell_pending = bool(machine.settle)
            continue

        move = XY.fullmatch(line)
        if not move:
            refuse("expected an explicit XY move")
        kind, raw_x, raw_y, raw_feed = move.groups()
        x, y = (float(v) * scale for v in (raw_x, raw_y))
        if (not isfinite(x + y) or not lower_x - 1e-9 <= x <= upper_x + 1e-9
                or not -1e-9 <= y <= machine.height + 1e-9):
            refuse("serialized XY coordinate is outside the configured travel and mounting")
        if state == "lifted":
            if kind != "G0" or raw_feed is not None:
                refuse("expected pen-up travel with no cutting feed")
            state = "first_point" if travels == 0 else "travelled"
            travels += 1
        else:
            if kind != "G1" or (x, y) == position:
                refuse("expected a distinct linear draw move without a rapid")
            if not segments:
                if raw_feed is None or not 0 < float(raw_feed) or abs(float(raw_feed) * scale - machine.feed) > z_tol:
                    refuse("first drawing move requires the configured explicit feed")
            elif raw_feed is not None:
                refuse("unexpected drawing feed change")
            segments += 1
            plotted += 1
        position = (x, y)

    if dwell_pending or state != "lifted" or not travels or travels != expected_strokes:
        raise ValueError("G-code preflight: unfinished program or unexpected stroke count.")
    return ProgramPreflight(len(lines) - 1, travels, plotted)
