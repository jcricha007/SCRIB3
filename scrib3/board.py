"""Immutable, millimetre paper-space artwork with registered color passes."""

from dataclasses import asdict, dataclass, replace
import json
from math import cos, sin, radians, isfinite
from xml.etree import ElementTree as ET

from .atomic_export import write_atomic_export
from .poster_objects import StrokeText, valid_point

MAX_PATHS = 16000
MAX_POINTS = 400000
DEFAULT_PEN = "#242c39"
PAPER = {"A4": (297, 210), "Letter": (279.4, 215.9), "A3": (420, 297), "A5": (210, 148), "Tabloid": (431.8, 279.4)}


@dataclass(frozen=True)
class Mark:
    color: str
    points: tuple
    groups: tuple = ()
    text: StrokeText | None = None
    controls: tuple = ()
    sheet_part: str | None = None


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
        if (len(self.marks) > MAX_PATHS or sum(len(m.points) for m in self.marks) > MAX_POINTS
                or sum(len(m.controls) for m in self.marks) > MAX_POINTS):
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
        texts = {}
        for m in self.marks:
            if m.sheet_part not in (None, "view", "frame"):
                raise ValueError("Invalid engineering sheet component.")
            if len(m.points) < 2 or not all(map(valid_point, m.points)):
                raise ValueError("Invalid path coordinates.")
            if len(m.groups) > 64 or any(not isinstance(n, str) or not n.strip() or len(n) > 160 for n in m.groups):
                raise ValueError("Invalid group name or nesting depth.")
            if m.controls and (len(m.controls) < 4 or (len(m.controls)-1) % 3 or
                               not all(map(valid_point, m.controls))):
                raise ValueError("Invalid cubic control points.")
            if m.text is not None:
                prior = texts.get(m.text.key)
                if prior is None:
                    m.text.check()
                    texts[m.text.key] = (m.text, m.color, m.groups, m.sheet_part)
                elif prior != (m.text, m.color, m.groups, m.sheet_part):
                    raise ValueError("Inconsistent lettering object.")
        return self

    def text_selection(self, indices):
        indices = {i for i in indices if self.marks[i].color not in self.hidden | self.locked}
        keys = {self.marks[i].text.key for i in indices if self.marks[i].text}
        if keys:
            indices.update(i for i, m in enumerate(self.marks) if m.text and m.text.key in keys)
        return indices

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
        scale_x=1,
        scale_y=1,
        angle=0,
        dx=0,
        dy=0,
        fit=False,
        center=False,
        mirror_x=False,
        mirror_y=False,
    ):
        indices = self.text_selection(indices)
        if not indices:
            raise ValueError("Select visible unlocked artwork.")
        if not all(isfinite(v) for v in (factor, angle, dx, dy, scale_x, scale_y)) or min(factor, scale_x, scale_y) <= 0:
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

        def point(p):
            x = (p[0] - cx) * (-scale_x if mirror_x else scale_x)
            y = (p[1] - cy) * (-scale_y if mirror_y else scale_y)
            return (cx + dx + a * x - b * y, cy + dy + b * x + a * y)

        texts = {}
        def move(m):
            text = m.text
            if text:
                if text.key not in texts:
                    texts[text.key] = replace(text, frame=tuple(map(point, text.frame)))
                text = texts[text.key]
            return replace(m, points=tuple(map(point, m.points)), controls=tuple(map(point, m.controls)), text=text)

        return replace(
            self, marks=tuple(move(m) if i in indices else m for i, m in enumerate(self.marks))
        ).checked()


def bounds(marks):
    pts = [p for m in marks for p in m.points]
    if not pts:
        raise ValueError("Add artwork first.")
    xs, ys = zip(*pts)
    return min(xs), min(ys), max(xs), max(ys)


def encode_board(board):
    board.checked()
    paths, texts = [], {}
    for m in board.marks:
        row = [m.color, m.points]
        details = {}
        if m.groups:
            details["groups"] = m.groups
        if m.controls:
            details["controls"] = m.controls
        if m.sheet_part:
            details["sheet_part"] = m.sheet_part
        if m.text:
            details["text"] = m.text.key
            if m.text.key not in texts:
                texts[m.text.key] = asdict(m.text)
        if details:
            row.append(details)
        paths.append(row)
    data = dict(
        format="scrib3-board",
        version=2 if any(len(row) == 3 for row in paths) else 1,
        width=board.width,
        height=board.height,
        bed=board.bed,
        hidden=sorted(board.hidden),
        locked=sorted(board.locked),
        pen_order=board.pen_order,
        paths=paths,
    )
    if texts:
        data["texts"] = texts
    encoded = json.dumps(data, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if len(encoded) > 32_000_000:
        raise ValueError("Board exceeds 32 MB.")
    return encoded


def save_board(path, board):
    encoded = encode_board(board)
    write_atomic_export(path, lambda p: p.write_bytes(encoded))


def load_board(path):
    if path.stat().st_size > 32_000_000:
        raise ValueError("Board exceeds 32 MB.")
    return decode_board(path.read_bytes())


def decode_board(payload):
    if len(payload) > 32_000_000:
        raise ValueError("Board exceeds 32 MB.")
    try:
        d = json.loads(payload.decode('utf-8'))
        if d["format"] != "scrib3-board" or d["version"] not in (1, 2):
            raise ValueError("Unknown board format.")
        texts = {}
        for key, values in d.get("texts", {}).items():
            obj = StrokeText(**{**values, "frame": tuple(tuple(p) for p in values["frame"])})
            if key != obj.key:
                raise ValueError("Invalid text object ID.")
            obj.check()
            texts[key] = obj
        marks = []
        for row in d["paths"]:
            if len(row) not in ((2,) if d["version"] == 1 else (2, 3)):
                raise ValueError("Invalid path record.")
            color, points = row[:2]
            details = row[2] if len(row) == 3 else {}
            groups = details.get("groups", [])
            if not isinstance(groups, list):
                raise ValueError("Invalid path groups.")
            text = texts[details["text"]] if "text" in details else None
            controls = tuple(tuple(p) for p in details.get("controls", ()))
            marks.append(Mark(color, tuple(tuple(p) for p in points), tuple(groups), text, controls, details.get("sheet_part")))
        return Board(
            d["width"],
            d["height"],
            tuple(marks),
            frozenset(d.get("hidden", [])),
            frozenset(d.get("locked", [])),
            tuple(d["bed"]) if d.get("bed") else None,
            tuple(d.get("pen_order", [])),
        ).checked()
    except (AttributeError, TypeError, KeyError, IndexError, OverflowError) as e:
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
        group.set("data-scrib3-pen", color)
        active, parents = (), [group]
        for m in board.marks:
            if m.color != color:
                continue
            common = 0
            for a, b in zip(active, m.groups):
                if a != b:
                    break
                common += 1
            parents = parents[:common+1]
            for name in m.groups[common:]:
                parents.append(ET.SubElement(parents[-1], "g", {"data-scrib3-group": name, "aria-label": name}))
            active = m.groups
            if m.controls:
                x, y = m.controls[0]
                coords = " ".join(f"{u:.6f},{v:.6f}" for u, v in m.controls[1:])
                d = f"M{x:.6f},{y:.6f} C{coords}"
            else:
                d = "M" + " L".join(f"{x:.6f},{y:.6f}" for x, y in m.points)
            ET.SubElement(parents[-1], "path", d=d)
    write_atomic_export(
        path, lambda p: ET.ElementTree(root).write(p, encoding="utf-8", xml_declaration=True)
    )
