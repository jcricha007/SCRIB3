"""Conservative cleanup in fitted paper millimeters, before GRBL generation."""
from dataclasses import dataclass

from .curves import segment_distance
from .drawing import Drawing, path_lengths
from .routing import join_exact_strokes, optimize_route, stroke_key
from .vector_io import checked_drawing

QUALITY_MODES = {'Original': 0.0, 'Fine': 0.005, 'Balanced': 0.02}


@dataclass(frozen=True)
class QualityOptions:
    mode: str = 'Balanced'
    remove_duplicates: bool = False
    order: bool = True
    join_strokes: bool = False
    reloop: bool = True

    def __post_init__(self):
        if not isinstance(self.mode, str) or self.mode not in QUALITY_MODES:
            raise ValueError('Choose Original, Fine, or Balanced toolpath quality.')
        if any(type(value) is not bool for value in
               (self.remove_duplicates, self.order, self.join_strokes, self.reloop)):
            raise ValueError('Toolpath switches must be true or false.')


@dataclass(frozen=True)
class PathMetrics:
    strokes: int
    points: int
    drawn_mm: float
    travel_mm: float

    @classmethod
    def measure(cls, drawing, start=(0, 0)):
        drawn, travel = path_lengths(drawing, start)
        return cls(len(drawing), sum(map(len, drawing)), drawn, travel)


@dataclass(frozen=True)
class QualityReport:
    before: PathMetrics
    after: PathMetrics
    tolerance_mm: float
    duplicates_removed: int
    joins: int = 0


def simplify_stroke(stroke, tolerance):
    if not tolerance or len(stroke) <= 2:
        return stroke
    try:
        from rdp import rdp
    except ImportError as exc:
        raise ValueError('Install the updated requirements.txt to enable Fine or Balanced quality.') from exc
    # Preserve global bounds, endpoints and deliberate direction reversals.
    # Chunk anchors bound worst-case RDP work, and avoid recursion in both our
    # code and the library. All coordinates here are physical paper millimeters.
    anchors = {0, len(stroke)-1, *range(0, len(stroke), 128)}
    for axis in (0, 1):
        anchors.add(min(range(len(stroke)), key=lambda i: stroke[i][axis]))
        anchors.add(max(range(len(stroke)), key=lambda i: stroke[i][axis]))
    for i in range(1, len(stroke)-1):
        a, b, c = stroke[i-1:i+2]
        if (b[0]-a[0])*(c[0]-b[0]) + (b[1]-a[1])*(c[1]-b[1]) < 0:
            anchors.add(i)
    anchors = sorted(anchors)
    result = [stroke[0]]
    for first, last in zip(anchors, anchors[1:]):
        simplified = rdp(stroke[first:last+1], epsilon=tolerance,
                         dist=segment_distance, algo='iter')
        result.extend((float(x), float(y)) for x, y in simplified[1:])
    if stroke[0] == stroke[-1] and len(set(result)) < 3:
        return stroke  # Never collapse a small closed contour to a line or dot.
    return tuple(result)


def prepare_toolpath(drawing: Drawing, options=QualityOptions(), start=(0, 0)):
    drawing = checked_drawing(drawing)
    before = PathMetrics.measure(drawing, start)
    tolerance = QUALITY_MODES[options.mode]
    seen = set()
    cleaned = []
    duplicates = 0
    for stroke in drawing:
        # Compare original points exactly: simplification must not cause two
        # nearby but distinct lines to be mistaken for duplicate ink passes.
        if options.remove_duplicates:
            key = stroke_key(stroke)
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
        cleaned.append(stroke)
    result = tuple(cleaned)
    if options.join_strokes:
        result = join_exact_strokes(result)
    joins = len(cleaned) - len(result)
    result = tuple(simplify_stroke(stroke, tolerance) for stroke in result)
    if options.order:
        result = optimize_route(result, start, options.reloop)
    after = PathMetrics.measure(result, start)
    return result, QualityReport(before, after, tolerance, duplicates, joins)
