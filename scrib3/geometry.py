"""Clipping, fills and path modifiers backed by robust planar geometry."""

from math import ceil, cos, sin, tau
from shapely import affinity
from shapely.geometry import Polygon, LineString, GeometryCollection
from .board import Mark, MAX_PATHS, MAX_POINTS


def line_marks(geometry, color):
    if geometry.is_empty:
        return ()
    if geometry.geom_type in ("LineString", "LinearRing"):
        return (
            (Mark(color, tuple((float(x), float(y)) for x, y in geometry.coords)),)
            if geometry.length > 1e-7
            else ()
        )
    if geometry.geom_type == "Polygon":
        return line_marks(geometry.boundary, color)
    return tuple(m for g in getattr(geometry, "geoms", ()) for m in line_marks(g, color))


def region(marks):
    result = GeometryCollection()
    for m in marks:
        if len(m.points) < 4 or m.points[0] != m.points[-1]:
            raise ValueError("Select closed outlines for this operation.")
        result = result.symmetric_difference(Polygon(m.points).buffer(0))
    return result


def fill_region(area, color, spacing, mode="Horizontal"):
    if not 0.15 <= spacing <= 100:
        raise ValueError("Spacing must be 0.15 to 100 mm.")
    if area.is_empty:
        return ()
    result = []
    if mode == "Concentric":
        for _ in range(10000):
            area = area.buffer(-spacing / 2 if not result else -spacing)
            if area.is_empty:
                break
            result.extend(line_marks(area.boundary, color))
            check_size(result)
    else:
        angles = {
            "Horizontal": (0,),
            "Vertical": (90,),
            "Diagonal": (45,),
            "Crosshatch": (45, -45),
        }[mode]
        for angle in angles:
            turned = affinity.rotate(area, -angle, origin=(0, 0))
            x0, y0, x1, y1 = turned.bounds
            count = ceil((y1 - y0) / spacing)
            if count > MAX_PATHS:
                raise ValueError("Increase spacing.")
            for i in range(count):
                y = y0 + (i + 0.5) * spacing
                cut = turned.intersection(LineString([(x0 - 1, y), (x1 + 1, y)]))
                result.extend(line_marks(affinity.rotate(cut, angle, origin=(0, 0)), color))
            check_size(result)
    return tuple(result)


def check_size(marks):
    if len(marks) > MAX_PATHS or sum(len(m.points) for m in marks) > MAX_POINTS:
        raise ValueError("Operation exceeds board complexity. Reduce copies or increase spacing.")


def hatch(marks, spacing, mode="Horizontal"):
    result = []
    for c in dict.fromkeys(m.color for m in marks):
        result.extend(fill_region(region([m for m in marks if m.color == c]), c, spacing, mode))
    check_size(result)
    return tuple(result)


def offset(marks, distance):
    return tuple(
        m
        for c in dict.fromkeys(m.color for m in marks)
        for m in line_marks(region([m for m in marks if m.color == c]).buffer(distance).boundary, c)
    )


def array(marks, count, step_x=10, step_y=0, angle=0):
    from .board import Board

    if not 1 <= count <= 100:
        raise ValueError("Use 1 to 100 copies.")
    from .poster_objects import independent_copy

    result = list(marks)
    b = Board(marks=tuple(marks))
    for i in range(1, count):
        copy = b.transform(range(len(marks)), angle=i * angle, dx=i * step_x, dy=i * step_y)
        result.extend(independent_copy(copy.marks, result))
    check_size(result)
    return tuple(result)


def shape(kind, start, end):
    x, y = start
    u, v = end
    if kind == "Line":
        return start, end
    if kind == "Rectangle":
        return start, (u, y), end, (x, v), start
    n = 96 if kind == "Ellipse" else 10 if kind == "Star" else 5
    pts = []
    for i in range(n):
        r = 0.42 if kind == "Star" and i % 2 else 1
        a = tau * (i / n - 0.25)
        pts.append(((x + u) / 2 + r * (u - x) / 2 * cos(a), (y + v) / 2 + r * (v - y) / 2 * sin(a)))
    return tuple(pts + [pts[0]])


def bezier(points):
    """Sample a four-point cubic with error scaled to board millimetres."""
    from svgelements import CubicBezier
    from .curves import flatten_segment

    curve = CubicBezier(*(complex(x, y) for x, y in points))
    return (points[0], *flatten_segment(curve, 0.04, 4096))
