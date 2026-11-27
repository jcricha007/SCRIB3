"""Editable stroke lettering and cubic curves in physical board coordinates."""

from dataclasses import dataclass, replace
from math import isfinite
from uuid import uuid4

from svgelements import CubicBezier

from .curves import flatten_segment
from .lettering import ALIGNMENTS, FONTS, lettering


def valid_point(p):
    return len(p) == 2 and all(type(v) in (int, float) and isfinite(v) and abs(v) <= 1e7 for v in p)


def cubic_points(controls):
    from .board import MAX_POINTS

    if len(controls) < 4 or (len(controls) - 1) % 3 or not all(map(valid_point, controls)):
        raise ValueError("A cubic path needs a start and three control points per segment.")
    points = [controls[0]]
    for i in range(0, len(controls) - 1, 3):
        curve = CubicBezier(*(complex(x, y) for x, y in controls[i : i + 4]))
        points.extend(flatten_segment(curve, 0.025, MAX_POINTS - len(points)))
    return tuple(points)


@dataclass(frozen=True)
class StrokeText:
    key: str
    value: str = "SCRIB3"
    font: str = "Technical sans"
    height: float = 8.0
    tracking: float = 0.0
    spacing: float = 1.5
    alignment: str = "Left"
    # Origin and two unit basis points preserve the anchor through rotation, flipping and scaling.
    frame: tuple = ((0, 0), (1, 0), (0, 1))

    def check(self):
        if not isinstance(self.key, str) or not 1 <= len(self.key) <= 80:
            raise ValueError("Invalid text object ID.")
        if not isinstance(self.value, str) or not self.value.strip() or len(self.value) > 300:
            raise ValueError("Enter 1 to 300 characters of lettering.")
        if any(c != "\n" and not 32 <= ord(c) <= 126 for c in self.value):
            raise ValueError("Use printable ASCII lettering.")
        if self.font not in FONTS or self.alignment not in ALIGNMENTS:
            raise ValueError("Choose a listed font and alignment.")
        if (
            not 0.21 <= self.height <= 1050
            or not 0 <= self.tracking <= 20
            or not 1 <= self.spacing <= 4
        ):
            raise ValueError("Check text height, tracking and line spacing.")
        if len(self.frame) != 3 or not all(map(valid_point, self.frame)):
            raise ValueError("Invalid text placement.")

    def marks(self, color, groups=()):
        from .board import Mark

        self.check()
        origin, x_axis, y_axis = self.frame
        scale = self.height / 21

        def project(point):
            x, y = point
            return tuple(
                origin[i] + scale * (x * (x_axis[i] - origin[i]) + y * (y_axis[i] - origin[i]))
                for i in (0, 1)
            )

        paths = lettering(self.value, self.font, self.alignment, self.tracking, self.spacing)
        return tuple(Mark(color, tuple(map(project, p)), groups, self) for p in paths)


def unused_group(name, taken):
    name = name.strip()
    if not name or len(name) > 160:
        raise ValueError("Enter a group name of 1 to 160 characters.")
    candidate = name
    suffix = 2
    while candidate in taken:
        candidate = f"{name[:147]} ({suffix})"
        suffix += 1
    return candidate


def independent_copy(marks, existing):
    """Give inserted text and named root groups identities independent of the source."""
    taken = {m.groups[0] for m in existing if m.groups}
    names, texts = {}, {}
    result = []
    for m in marks:
        groups = m.groups
        if groups:
            root = groups[0]
            if root not in names:
                names[root] = unused_group(root, taken)
                taken.add(names[root])
            groups = (names[root], *groups[1:])
        text = m.text
        if text is not None:
            if text.key not in texts:
                texts[text.key] = replace(text, key=uuid4().hex)
            text = texts[text.key]
        result.append(replace(m, groups=groups, text=text, sheet_part=None))
    return tuple(result)
