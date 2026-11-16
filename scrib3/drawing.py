from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from math import dist, hypot, isfinite
from pathlib import Path
from xml.etree import ElementTree

from svgelements import Close, Image, Line, Move, SVG, Shape, Text
from svgelements import Path as SvgPath

from .curves import flatten_segment

Point = tuple[float, float]
Stroke = tuple[Point, ...]
Drawing = tuple[Stroke, ...]
MAX_STROKES = 2_000
MAX_POINTS = 100_000
MAX_SVG_BYTES = 2_000_000


@dataclass(frozen=True)
class Sheet:
    width: float
    height: float
    margin: float

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.width, self.height, self.margin)):
            raise ValueError("Enter finite paper dimensions and margin.")
        if not 1 <= min(self.width, self.height) <= max(self.width, self.height) <= 10_000:
            raise ValueError("Paper dimensions must be between 1 and 10,000 mm.")
        if not 0 <= self.margin < min(self.width, self.height) / 2:
            raise ValueError("The margin must be nonnegative and leave room to draw.")


def fit_to_sheet(drawing: Drawing, sheet: Sheet) -> Drawing:
    """Map source coordinates (Y down) to centered paper coordinates (Y up)."""
    if not drawing:
        return ()
    points = [point for stroke in drawing for point in stroke]
    if not all(isfinite(value) and abs(value) <= 1e9 for point in points for value in point):
        raise ValueError("The drawing contains invalid or excessively large coordinates.")
    xs, ys = zip(*points)
    low_x, high_x = min(xs), max(xs)
    low_y, high_y = min(ys), max(ys)
    width, height = high_x - low_x, high_y - low_y
    if max(width, height) <= 0:
        raise ValueError("The drawing has no measurable extent.")
    available_width = sheet.width - 2 * sheet.margin
    available_height = sheet.height - 2 * sheet.margin
    if width * available_height >= height * available_width and width:
        fitted_width = available_width
        fitted_height = height / width * fitted_width
    else:
        fitted_height = available_height
        fitted_width = width / height * fitted_height
    left = (sheet.width - fitted_width) / 2
    bottom = (sheet.height - fitted_height) / 2
    return tuple(
        tuple((left + (x - low_x) / (width or 1) * fitted_width,
               bottom + (high_y - y) / (height or 1) * fitted_height) for x, y in stroke)
        for stroke in drawing
    )


def order_strokes(drawing: Drawing, start: Point = (0, 0)) -> Drawing:
    """Choose the closest available endpoint, starting from the paper origin."""
    remaining = list(drawing)
    ordered: list[Stroke] = []
    position: Point = start
    while remaining:
        index, reverse = min(
            ((index, side) for index in range(len(remaining)) for side in (False, True)),
            key=lambda choice: dist(position, remaining[choice[0]][-1 if choice[1] else 0]),
        )
        stroke = remaining.pop(index)
        if reverse:
            stroke = stroke[::-1]
        ordered.append(stroke)
        position = stroke[-1]
    return tuple(ordered)


def read_svg(path: Path) -> Drawing:
    with path.open("rb") as stream:
        raw = stream.read(MAX_SVG_BYTES + 1)
    if len(raw) > MAX_SVG_BYTES:
        raise ValueError("Choose an SVG under 2 MB for this prototype.")
    markup = raw.decode("utf-8-sig")
    if "<!DOCTYPE" in markup.upper() or "<!ENTITY" in markup.upper():
        raise ValueError("Save the SVG without a doctype or entity declarations.")
    root = ElementTree.fromstring(markup)
    if root.tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
        raise ValueError("Choose a valid SVG document.")
    if any(
        element.tag.rsplit("}", 1)[-1] in {"clipPath", "mask", "filter"}
        for element in root.iter()
    ):
        raise ValueError("Flatten SVG clipping, masks, and filters to paths before importing.")

    svg = SVG.parse(StringIO(markup), reify=True, ppi=96, on_error="raise")
    shapes = []
    for element in svg.elements():
        visibility = element.values.get("visibility")
        if visibility in {"hidden", "collapse"}:
            continue
        if isinstance(element, (Text, Image)):
            raise ValueError("Convert visible text and images to vector paths before importing.")
        if isinstance(element, Shape):
            shapes.append(SvgPath(element).reify())
            if len(shapes) > MAX_STROKES:
                raise ValueError("Simplify the SVG to 2,000 shapes or fewer.")
    bounds = [bound for shape in shapes if (bound := shape.bbox()) is not None]
    if not bounds:
        raise ValueError("This SVG contains no supported vector paths.")
    width = max(box[2] for box in bounds) - min(box[0] for box in bounds)
    height = max(box[3] for box in bounds) - min(box[1] for box in bounds)
    if not isfinite(max(width, height)) or max(width, height) <= 0:
        raise ValueError("The SVG has invalid dimensions.")
    # Relative source tolerance scales with paper fitting. On a 250 mm-wide
    # drawing, 1e-5 corresponds to approximately 0.0025 mm before rounding.
    tolerance = max(width, height) * 1e-5
    drawing: list[Stroke] = []
    count = 0
    for shape in shapes:
        points: list[Point] = []
        for segment in shape:
            if isinstance(segment, Move):
                if len(points) > 1:
                    drawing.append(tuple(points))
                points = []
                if len(drawing) >= MAX_STROKES:
                    raise ValueError("Simplify the SVG to 2,000 strokes or fewer.")
                continue
            if segment.start is None or segment.end is None:
                continue
            start = (float(segment.start.x), float(segment.start.y))
            if not points:
                points.append(start)
                count += 1
            samples = flatten_segment(segment, tolerance, MAX_POINTS - count)
            count += len(samples)
            if count > MAX_POINTS:
                raise ValueError("Simplify the SVG to reduce the number of plotting points.")
            for point in samples:
                xy = points[0] if isinstance(segment, Close) else point
                if xy != points[-1]:
                    points.append(xy)
        if len(points) > 1:
            drawing.append(tuple(points))
        if len(drawing) > MAX_STROKES:
            raise ValueError("Simplify the SVG to 2,000 strokes or fewer.")
    if not drawing:
        raise ValueError("The SVG contains no drawable strokes.")
    return tuple(drawing)


def path_lengths(drawing: Drawing, start: Point = (0, 0)) -> tuple[float, float]:
    drawn = 0.0
    travel = 0.0
    previous: Point = start
    for stroke in drawing:
        travel += dist(previous, stroke[0])
        drawn += sum(hypot(x2 - x1, y2 - y1) for (x1, y1), (x2, y2) in zip(stroke, stroke[1:]))
        previous = stroke[-1]
    return drawn, travel
