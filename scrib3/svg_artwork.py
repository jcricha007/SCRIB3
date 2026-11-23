"""Color SVG import in physical units, including clipping and opaque occlusion."""

from copy import deepcopy
from io import StringIO
import re
from xml.etree import ElementTree as ET
from svgelements import SVG, Group, Shape, Path as SvgPath, Move, Close, Text, Image, Matrix
from shapely import affinity
from shapely.geometry import Polygon, GeometryCollection, LineString
from shapely.ops import unary_union, polygonize

from .board import Mark, MAX_PATHS, MAX_POINTS
from .curves import flatten_segment
from .svg_dashes import dash_pattern, split_dashes
from .geometry import line_marks, fill_region, check_size

PX_MM = 25.4 / 96


def paths_of(element):
    path = SvgPath(element)
    points = []
    paths = []
    count = 0
    for seg in path:
        if isinstance(seg, Move):
            if len(points) > 1:
                paths.append(tuple(points))
            points = []
        elif seg.start is not None and seg.end is not None:
            if not points:
                points = [(float(seg.start.x), float(seg.start.y))]
            for p in flatten_segment(seg, 0.025, MAX_POINTS - count):
                p = points[0] if isinstance(seg, Close) else p
                if p != points[-1]:
                    points.append(p)
                    count += 1
            if count > MAX_POINTS:
                raise ValueError("SVG exceeds point limit.")
    if len(points) > 1:
        paths.append(tuple(points))
    return tuple(paths)


def filled_region(paths, rule):
    closed = [p if p[0] == p[-1] else (*p, p[0]) for p in paths if len(p) >= 3]
    if not closed:
        return GeometryCollection()
    if rule == "evenodd":
        area = GeometryCollection()
        for p in closed:
            area = area.symmetric_difference(Polygon(p).buffer(0))
        return area
    # Resolve winding numbers per planar face, including self-intersections.
    faces = polygonize(unary_union([LineString(p) for p in closed]))
    kept = []
    for face in faces:
        q = face.representative_point()
        x, y = q.x, q.y
        winding = 0
        for p in closed:
            for (ax, ay), (bx, by) in zip(p, p[1:]):
                cross = (bx - ax) * (y - ay) - (x - ax) * (by - ay)
                if ay <= y < by and cross > 0:
                    winding += 1
                elif by <= y < ay and cross < 0:
                    winding -= 1
        if winding:
            kept.append(face)
    return unary_union(kept)


def drawing_elements(node, clips=(), opacity=1):
    """Carry container clipping and opacity without applying child transforms twice."""
    values = node.values
    own = values.get("attributes", {})
    opacity *= float(own.get("opacity", 1))
    if opacity <= 0 or values.get("display") == "none":
        return
    if own.get("clip-path"):
        clips = (*clips, node)
    if isinstance(node, (SVG, Group)):
        for child in node:
            yield from drawing_elements(child, clips, opacity)
    else:
        yield node, clips, opacity


def clipping_region(owner, definitions, sx, sy):
    match = re.fullmatch(r"url\(#([^\)]+)\)", owner.values["clip-path"])
    if not match or match[1] not in definitions:
        raise ValueError("Unresolved SVG clipping path.")
    node = definitions[match[1]]
    dummy = ET.Element("svg", width="100", height="100")
    for child in node:
        dummy.append(deepcopy(child))
    parsed = SVG.parse(StringIO(ET.tostring(dummy, encoding="unicode")), reify=True)
    mask = unary_union(
        [
            filled_region(
                paths_of(child), child.values.get("clip-rule", node.get("clip-rule", "nonzero"))
            )
            for child in parsed.elements()
            if isinstance(child, Shape)
        ]
    )
    cm = Matrix(node.get("transform", ""))
    mask = affinity.affine_transform(mask, [cm.a, cm.c, cm.b, cm.d, cm.e, cm.f])
    if node.get("clipPathUnits") == "objectBoundingBox":
        if isinstance(owner, Shape):
            coords = [p for part in paths_of(owner) for p in part]
        else:
            inverse = ~owner.transform
            coords = []
            for child, _, _ in drawing_elements(owner):
                if isinstance(child, Shape):
                    for part in paths_of(child):
                        for x, y in part:
                            q = inverse.point_in_matrix_space(
                                child.transform.point_in_matrix_space((x, y))
                            )
                            coords.append((q.x, q.y))
        if not coords:
            return GeometryCollection()
        xs, ys = zip(*coords)
        mask = affinity.scale(mask, max(xs) - min(xs), max(ys) - min(ys), origin=(0, 0))
        mask = affinity.translate(mask, min(xs), min(ys))
    m = owner.transform
    return affinity.affine_transform(
        mask, [m.a * sx, m.c * sx, m.b * sy, m.d * sy, m.e * sx, m.f * sy]
    )


def import_svg(path, *, fill="Outline", spacing=1, hide_covered=True):
    if path.stat().st_size > 10_000_000:
        raise ValueError("SVG exceeds 10 MB.")
    markup = path.read_text(encoding="utf-8-sig")
    if "<!DOCTYPE" in markup.upper() or "<!ENTITY" in markup.upper():
        raise ValueError("Save SVG without document entities.")
    root = ET.fromstring(markup)
    if any(e.tag.split("}")[-1] in ("mask", "filter") for e in root.iter()):
        raise ValueError("Flatten SVG masks and filters before importing.")
    clips = {e.get("id"): e for e in root.iter() if e.tag.split("}")[-1] == "clipPath"}
    svg = SVG.parse(StringIO(markup), reify=False, ppi=96, on_error="raise")
    units = {"mm": 1, "cm": 10, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6, "px": PX_MM}
    scales = []
    for key, size in [("width", svg.width), ("height", svg.height)]:
        match = re.fullmatch(r"([0-9.]+)(mm|cm|in|pt|pc|px)", root.get(key, ""))
        scales.append(float(match[1]) * units[match[2]] / float(size) if match and size else PX_MM)
    sx, sy = scales
    objects = []
    mask_cache = {}
    for e, owners, opacity in drawing_elements(svg):
        values = e.values
        if values.get("visibility") in ("hidden", "collapse") or values.get("display") == "none":
            continue
        if isinstance(e, (Text, Image)):
            raise ValueError("Convert text to paths and trace embedded images before SVG import.")
        if not isinstance(e, Shape):
            continue
        local = paths_of(e)
        matrix = e.transform
        transformed = lambda pts: tuple(
            (
                sx * (matrix.a * x + matrix.c * y + matrix.e),
                sy * (matrix.b * x + matrix.d * y + matrix.f),
            )
            for x, y in pts
        )
        paths = tuple(transformed(p) for p in local)
        if not paths:
            continue
        fill_color = e.fill if float(values.get("fill-opacity", 1)) > 0 else None
        stroke_color = e.stroke if float(values.get("stroke-opacity", 1)) > 0 else None
        has_fill = (
            fill_color is not None and fill_color.value is not None and fill_color.opacity > 0
        )
        has_stroke = (
            stroke_color is not None and stroke_color.value is not None and stroke_color.opacity > 0
        )
        if not has_fill and not has_stroke:
            continue
        area = (
            filled_region(paths, values.get("fill-rule", "nonzero"))
            if has_fill
            else GeometryCollection()
        )
        mask = None
        for owner in owners:
            key = id(owner)
            if key not in mask_cache:
                mask_cache[key] = clipping_region(owner, clips, sx, sy)
            current = mask_cache[key]
            mask = current if mask is None else mask.intersection(current)
        if mask is not None:
            area = area.intersection(mask)
        outline = []
        if has_stroke:
            dashes = dash_pattern(values)
            parts = (
                tuple(
                    transformed(p)
                    for part in local
                    for p in split_dashes(
                        part, *dashes, max_strokes=MAX_PATHS, max_points=MAX_POINTS
                    )
                )
                if dashes
                else paths
            )
            for p in parts:
                line = LineString(p)
                outline.extend(
                    line_marks(
                        line.intersection(mask) if mask is not None else line, stroke_color.hex[:7]
                    )
                )
        elif has_fill:
            outline.extend(line_marks(area.boundary, fill_color.hex[:7]))
        opaque = (
            has_fill
            and opacity * float(values.get("fill-opacity", 1)) * fill_color.opacity >= 0.999
        )
        objects.append((tuple(outline), area, fill_color.hex[:7] if has_fill else None, opaque))
        if len(objects) > MAX_PATHS:
            raise ValueError("SVG exceeds shape limit.")
    covered = GeometryCollection()
    result = []
    for outlines, area, color, opaque in reversed(objects):
        visible = area.difference(covered) if hide_covered else area
        chunk = []
        for mark in outlines:
            chunk.extend(
                line_marks(LineString(mark.points).difference(covered), mark.color)
                if hide_covered
                else (mark,)
            )
        if fill != "Outline" and color:
            chunk.extend(fill_region(visible, color, spacing, fill))
        result.append(chunk)
        if hide_covered and opaque:
            covered = covered.union(area)
    marks = tuple(m for chunk in reversed(result) for m in chunk)
    check_size(marks)
    if not marks:
        raise ValueError("SVG contains no visible vector paths.")
    return marks
