"""Immutable, millimetre paper-space artwork with registered color passes."""

from dataclasses import dataclass, replace
import json
from math import cos, sin, radians, isfinite
from xml.etree import ElementTree as ET

from .atomic_export import write_atomic_export

MAX_PATHS = 16000
MAX_POINTS = 400000
DEFAULT_PEN = "#242c39"
PAPER = {"A4": (297, 210), "Letter": (279.4, 215.9), "A3": (420, 297), "A5": (210, 148), "Tabloid": (431.8, 279.4)}


@dataclass(frozen=True)
class Mark:
    color: str
    points: tuple


@dataclass(frozen=True)
class Board:
    width: float = 297
    height: float = 210
    marks: tuple = ()
    hidden: frozenset = frozenset()
    locked: frozenset = frozenset()
    bed: tuple | None = None
    pen_order: tuple = ()

    def checked(self):
        import re

        if not all(
            type(v) in (int, float) and isfinite(v) and 1 <= v <= 10000
            for v in (self.width, self.height)
        ):
            raise ValueError("Paper dimensions must be 1 to 10000 mm.")
        if self.bed is not None and (
            len(self.bed) != 2 or not all(isfinite(v) and v > 0 for v in self.bed)
        ):
            raise ValueError("Invalid bed dimensions.")
        if len(self.marks) > MAX_PATHS or sum(len(m.points) for m in self.marks) > MAX_POINTS:
            raise ValueError("Reduce artwork below 16,000 paths and 400,000 points.")
        if len(self.pen_order) > MAX_PATHS or len(set(self.pen_order)) != len(self.pen_order):
            raise ValueError("Invalid pen order.")
        colors = (
            [m.color for m in self.marks]
            + list(self.hidden)
            + list(self.locked)
            + list(self.pen_order)
        )
        if any(not isinstance(c, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", c) for c in colors):
            raise ValueError("Use six-digit hexadecimal pen colors.")
        for m in self.marks:
            if len(m.points) < 2 or any(
                len(p) != 2
                or any(type(v) not in (float, int) or not isfinite(v) or abs(v) > 1e7 for v in p)
                for p in m.points
            ):
                raise ValueError("Invalid path coordinates.")
        return self

    def pens(self, visible=True):
        present = dict.fromkeys(m.color for m in self.marks)
        return tuple(
            c
            for c in dict.fromkeys((*self.pen_order, *present))
            if c in present and (not visible or c not in self.hidden)
        )

    def plot_layer(self, color):
        from .drawing import Sheet

        paths = tuple(
            tuple((x, self.height - y) for x, y in m.points) for m in self.marks if m.color == color
        )
        if not paths or color in self.hidden:
            raise ValueError("Select a visible pen with artwork.")
        if any(not (0 <= x <= self.width and 0 <= y <= self.height) for p in paths for x, y in p):
            raise ValueError("Move all artwork inside the paper before output.")
        return paths, Sheet(self.width, self.height, 0)

    def transform(
        self,
        indices,
        *,
        factor=1,
        angle=0,
        dx=0,
        dy=0,
        fit=False,
        center=False,
        mirror_x=False,
        mirror_y=False,
    ):
        indices = {i for i in indices if self.marks[i].color not in self.hidden | self.locked}
        if not indices:
            raise ValueError("Select visible unlocked artwork.")
        if not all(isfinite(v) for v in (factor, angle, dx, dy)) or factor <= 0:
            raise ValueError("Invalid transform.")
        x0, y0, x1, y1 = bounds(self.marks[i] for i in indices)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if fit:
            factor = 0.94 * min(
                [
                    page / size
                    for page, size in [(self.width, x1 - x0), (self.height, y1 - y0)]
                    if size > 0
                ]
                or [1]
            )
        if fit or center:
            dx, dy = self.width / 2 - cx, self.height / 2 - cy
        a, b = cos(radians(angle)) * factor, sin(radians(angle)) * factor

        def move(m):
            points = []
            for x, y in m.points:
                x, y = (x - cx) * (-1 if mirror_x else 1), (y - cy) * (-1 if mirror_y else 1)
                points.append((cx + dx + a * x - b * y, cy + dy + b * x + a * y))
            return replace(m, points=tuple(points))

        return replace(
            self, marks=tuple(move(m) if i in indices else m for i, m in enumerate(self.marks))
        ).checked()


def bounds(marks):
    pts = [p for m in marks for p in m.points]
    if not pts:
        raise ValueError("Add artwork first.")
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def save_board(path, board):
    board.checked()
    data = dict(
        format="scrib3-board",
        version=1,
        width=board.width,
        height=board.height,
        bed=board.bed,
        hidden=sorted(board.hidden),
        locked=sorted(board.locked),
        pen_order=board.pen_order,
        paths=[[m.color, m.points] for m in board.marks],
    )
    write_atomic_export(
        path, lambda p: p.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
    )


def load_board(path):
    try:
        if path.stat().st_size > 32_000_000:
            raise ValueError("Board exceeds 32 MB.")
        d = json.loads(path.read_text(encoding="utf-8"))
        if d["format"] != "scrib3-board" or d["version"] != 1:
            raise ValueError("Unknown board format.")
        return Board(
            d["width"],
            d["height"],
            tuple(Mark(c, tuple(tuple(p) for p in pts)) for c, pts in d["paths"]),
            frozenset(d.get("hidden", [])),
            frozenset(d.get("locked", [])),
            tuple(d["bed"]) if d.get("bed") else None,
            tuple(d.get("pen_order", [])),
        ).checked()
    except (TypeError, KeyError, IndexError, OverflowError) as e:
        raise ValueError("Invalid board file.") from e


def export_svg(path, board):
    board.checked()
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width=f"{board.width}mm",
        height=f"{board.height}mm",
        viewBox=f"0 0 {board.width} {board.height}",
    )
    for color in board.pens():
        group = ET.SubElement(
            root,
            "g",
            id="pen-" + color[1:],
            stroke=color,
            fill="none",
            attrib={"stroke-width": "0.3"},
        )
        for m in board.marks:
            if m.color == color:
                ET.SubElement(
                    group, "path", d="M" + " L".join(f"{x:.6f},{y:.6f}" for x, y in m.points)
                )
    write_atomic_export(
        path, lambda p: ET.ElementTree(root).write(p, encoding="utf-8", xml_declaration=True)
    )
