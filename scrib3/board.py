"""Editable paper-space artwork. Coordinates are millimetres from the upper left."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from math import ceil, cos, hypot, isfinite, radians, sin, tau
from pathlib import Path
from xml.etree import ElementTree as ET

from .atomic_export import write_atomic_export
from .drawing import MAX_POINTS, Sheet, Stroke, _svg_paths

DEFAULT_PEN = "#242c39"
MAX_PATHS = 8000
PAPER = {
    "A4": (297, 210),
    "Letter": (279.4, 215.9),
    "A3": (420, 297),
    "A5": (210, 148),
    "Tabloid": (431.8, 279.4),
}


@dataclass(frozen=True)
class Mark:
    color: str
    points: Stroke


@dataclass(frozen=True)
class Board:
    width: float = 297
    height: float = 210
    marks: tuple[Mark, ...] = ()
    hidden: frozenset[str] = frozenset()
    locked: frozenset[str] = frozenset()

    bed: tuple[float, float] | None = None

    def checked(self):
        if self.bed is not None:
            Sheet(*self.bed, 0)
        Sheet(self.width, self.height, 0)
        if len(self.marks) > MAX_PATHS or sum(len(m.points) for m in self.marks) > MAX_POINTS:
            raise ValueError("Board limit is 8,000 paths and 100,000 points.")
        for m in self.marks:
            if len(m.points) < 2 or not re.fullmatch(r"#[0-9a-fA-F]{6}", m.color):
                raise ValueError("Invalid pen or empty board path.")
            if any(
                len(p) != 2
                or any(type(v) not in (int, float) or not isfinite(v) or abs(v) > 1e7 for v in p)
                for p in m.points
            ):
                raise ValueError("Invalid board coordinates.")
        return self

    def plot_layer(self, color):
        paths = tuple(
            tuple((x, self.height - y) for x, y in m.points) for m in self.marks if m.color == color
        )
        if not paths or color in self.hidden:
            raise ValueError("Select a visible pen with artwork.")
        if any(not (0 <= x <= self.width and 0 <= y <= self.height) for s in paths for x, y in s):
            raise ValueError("Move this pen layer onto the paper before reviewing it.")
        return paths, Sheet(self.width, self.height, 0)

    def transform(self, indices, *, factor=1, angle=0, dx=0, dy=0, fit=False, center=False):
        indices = {i for i in indices if self.marks[i].color not in self.hidden | self.locked}
        if not indices:
            raise ValueError("Select at least one visible, unlocked path.")
        if not all(isfinite(v) for v in (angle, factor, dx, dy)) or factor <= 0:
            raise ValueError("Use a positive scale and finite transform values.")
        x0, y0, x1, y1 = bounds(self.marks[i] for i in indices)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if fit:
            ratios = [
                page / extent
                for page, extent in [(self.width, x1 - x0), (self.height, y1 - y0)]
                if extent > 0
            ]
            if not ratios:
                raise ValueError("Selection has no measurable extent.")
            factor = 0.94 * min(ratios)
        if fit or center:
            dx, dy = self.width / 2 - cx, self.height / 2 - cy
        a, b = cos(radians(angle)) * factor, sin(radians(angle)) * factor

        def apply(mark):
            return replace(
                mark,
                points=tuple(
                    (cx + dx + a * (x - cx) - b * (y - cy), cy + dy + b * (x - cx) + a * (y - cy))
                    for x, y in mark.points
                ),
            )

        return replace(
            self, marks=tuple(apply(m) if i in indices else m for i, m in enumerate(self.marks))
        ).checked()


def bounds(marks):
    xs, ys = zip(*(p for m in marks for p in m.points))
    return min(xs), min(ys), max(xs), max(ys)


def import_svg(path, sheet_size=None):
    strokes, colors, viewport, declared = _svg_paths(path, max_strokes=MAX_PATHS)
    units = {"mm": 1.0, "cm": 10.0, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6, "px": 25.4 / 96}
    scales = []
    for original, size in zip(declared, viewport):
        match = re.fullmatch(
            r"\s*(\d*\.?\d+(?:[eE][+-]?\d+)?)\s*(mm|cm|in|pt|pc|px)\s*", original or ""
        )
        scales.append(float(match[1]) * units[match[2]] / size if match and size > 0 else 25.4 / 96)
    dx = dy = 0
    if sheet_size:
        dx, dy = (
            (sheet - size * unit) / 2 for sheet, size, unit in zip(sheet_size, viewport, scales)
        )
    return tuple(
        Mark(
            c,
            tuple((round(dx + x * scales[0], 9), round(dy + y * scales[1], 9)) for x, y in points),
        )
        for c, points in zip(colors, strokes)
    )


def bezier(points):
    """Sample a four-point cubic with error scaled to board millimetres."""
    from svgelements import CubicBezier
    from .curves import flatten_segment

    curve = CubicBezier(*(complex(x, y) for x, y in points))
    return (points[0], *flatten_segment(curve, 0.04, 4096))


def shape(tool, start, end, trail=()):
    x, y = start
    u, v = end
    if tool == "Freehand":
        return tuple(trail or (start,)) + (end,)
    if tool == "Line":
        return start, end
    if tool == "Rectangle":
        return start, (u, y), end, (x, v), start
    cx, cy = (x + u) / 2, (y + v) / 2
    if tool == "Ellipse":
        n = 96
    elif tool == "Star":
        n = 10
    elif tool == "Pentagon":
        n = 5
    else:
        raise ValueError("Unknown shape.")
    pts = []
    for k in range(n):
        radius = 0.42 if tool == "Star" and k % 2 else 1
        angle = tau * (k / n - 0.25)
        pts.append((cx + radius * (u - x) / 2 * cos(angle), cy + radius * (v - y) / 2 * sin(angle)))
    return tuple(pts + [pts[0]])


def save_board(path, board):
    board.checked()
    data = dict(
        format="scrib3-board",
        version=1,
        width=board.width,
        height=board.height,
        hidden=sorted(board.hidden),
        locked=sorted(board.locked),
        bed=board.bed,
        paths=[[m.color, m.points] for m in board.marks],
    )
    write_atomic_export(
        path,
        lambda p: p.write_text(
            json.dumps(data, separators=(",", ":"), allow_nan=False), encoding="utf-8"
        ),
    )


def load_board(path):
    try:
        with path.open("rb") as f:
            raw = f.read(12_000_001)
        if len(raw) > 12_000_000:
            raise ValueError("Choose a board under 12 MB.")
        d = json.loads(raw)
        if d["format"] != "scrib3-board" or d["version"] != 1:
            raise ValueError("Unknown board format.")
        if not isinstance(d["paths"], list) or len(d["paths"]) > MAX_PATHS:
            raise ValueError("Invalid path count.")
        flags = [frozenset(d[k]) for k in ("hidden", "locked")]
        if any(
            not isinstance(c, str) or not re.fullmatch(r"#[0-9a-f]{6}", c)
            for group in flags
            for c in group
        ):
            raise ValueError("Invalid layer settings.")
        marks = tuple(Mark(c, tuple(tuple(p) for p in points)) for c, points in d["paths"])
        bed = tuple(d["bed"]) if d.get("bed") is not None else None
        return Board(d["width"], d["height"], marks, *flags, bed).checked()
    except (KeyError, TypeError, IndexError, RecursionError, OverflowError) as exc:
        raise ValueError("Invalid SCRIB3 board.") from exc


def export_svg(path, board):
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=f"{board.width:g}mm",
        height=f"{board.height:g}mm",
        viewBox=f"0 0 {board.width:g} {board.height:g}",
    )
    groups = {}
    for mark in board.marks:
        if mark.color in board.hidden:
            continue
        if mark.color not in groups:
            groups[mark.color] = ET.SubElement(root, "g", id="pen-" + mark.color[1:])
        ET.SubElement(
            groups[mark.color],
            "path",
            d="M" + " L".join(f"{x:.6f},{y:.6f}" for x, y in mark.points),
            stroke=mark.color,
            fill="none",
            **{"stroke-width": "0.3", "stroke-linejoin": "round", "stroke-linecap": "round"},
        )
    write_atomic_export(
        path, lambda p: ET.ElementTree(root).write(p, encoding="utf-8", xml_declaration=True)
    )


def hatch(marks, pitch, mode="Horizontal"):
    angles = {"Horizontal": (0,), "Vertical": (90,), "Diagonal": (45,), "Crosshatch": (45, -45)}

    def rotated(marks, degrees):
        a, b = cos(radians(degrees)), sin(radians(degrees))
        return tuple(
            Mark(m.color, tuple((a * x - b * y, b * x + a * y) for x, y in m.points)) for m in marks
        )

    result = []
    for angle in angles[mode]:
        lines = _horizontal_hatch(rotated(marks, -angle), pitch)
        result.extend(rotated(lines, angle))
    return tuple(result)


def _horizontal_hatch(marks, pitch):
    """Even-odd scanline fill, including holes, independently for each pen."""
    if not isfinite(pitch) or pitch < 0.15:
        raise ValueError("Hatch spacing must be at least 0.15 mm.")
    if not marks or any(
        len(m.points) < 4
        or hypot(m.points[0][0] - m.points[-1][0], m.points[0][1] - m.points[-1][1]) > 0.001
        for m in marks
    ):
        raise ValueError("Select closed contours to hatch.")
    result = []
    for color in dict.fromkeys(m.color for m in marks):
        rows = {}
        crossings = 0
        for m in marks:
            if m.color != color:
                continue
            for (x0, y0), (x1, y1) in zip(m.points, m.points[1:]):
                if y0 == y1:
                    continue
                a = ceil(min(y0, y1) / pitch - 0.5)
                b = ceil(max(y0, y1) / pitch - 0.5)
                crossings += b - a
                if crossings > MAX_POINTS or b - a > MAX_PATHS:
                    raise ValueError("Increase the hatch spacing.")
                for n in range(a, b):
                    y = (n + 0.5) * pitch
                    rows.setdefault(n, []).append(x0 + (x1 - x0) * (y - y0) / (y1 - y0))
                    if len(rows) > MAX_PATHS:
                        raise ValueError("Increase the hatch spacing.")
        for n in sorted(rows):
            edges = sorted(rows[n])
            y = (n + 0.5) * pitch
            for x0, x1 in zip(edges[::2], edges[1::2]):
                if x1 - x0 > 0.02:
                    result.append(Mark(color, ((x0, y), (x1, y))))
            if len(result) > MAX_PATHS:
                raise ValueError("Increase the hatch spacing.")
    if not result:
        raise ValueError("Reduce hatch spacing for these contours.")
    return tuple(result)
