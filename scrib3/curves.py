"""Error-bounded flattening of reified svgelements geometry.

Control polygons bound Bezier deviation; ellipse second derivatives bound arc
interpolation. A midpoint-only test would miss symmetric S curves and cusps.
"""
from math import ceil, dist, isfinite, pi, sqrt

from svgelements import Arc, Close, CubicBezier, Line, QuadraticBezier


def segment_distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    if not length2:
        return dist(point, start)
    t = max(0.0, min(1.0, ((point[0]-start[0])*dx + (point[1]-start[1])*dy) / length2))
    return dist(point, (start[0] + t*dx, start[1] + t*dy))


def xy(point):
    value = (float(point.x), float(point.y))
    if not all(isfinite(v) and abs(v) <= 1e9 for v in value):
        raise ValueError('The SVG has invalid or excessively large curve coordinates.')
    return value


def flatten_segment(segment, tolerance, limit):
    """Return endpoints after the start, with error in source coordinate units."""
    if not isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Curve tolerance must be finite and positive.')
    start, end = xy(segment.start), xy(segment.end)
    if limit < 1:
        raise ValueError('Simplify the SVG to reduce the number of plotting points.')
    if isinstance(segment, (Line, Close)):
        return [end]
    if isinstance(segment, Arc):
        radius = max(segment.rx, segment.ry)
        if not isfinite(radius) or not isfinite(segment.sweep):
            raise ValueError('The SVG has invalid arc geometry.')
        step = min(pi/2, sqrt(8*tolerance/radius)) if radius else pi/2
        count = max(1, ceil(abs(segment.sweep)/step))
        if count > limit:
            raise ValueError('Simplify the SVG to reduce the number of plotting points.')
        return [xy(segment.point(i/count)) for i in range(1, count)] + [end]
    if isinstance(segment, CubicBezier):
        controls = (start, xy(segment.control1), xy(segment.control2), end)
    elif isinstance(segment, QuadraticBezier):
        controls = (start, xy(segment.control), end)
    else:
        raise ValueError(f'Unsupported SVG curve: {type(segment).__name__}. Convert it to paths.')
    result = []
    pending = [(controls, 0)]
    while pending:
        points, depth = pending.pop()
        if max(segment_distance(p, points[0], points[-1]) for p in points[1:-1]) <= tolerance:
            result.append(points[-1])
        else:
            if depth >= 40:
                raise ValueError('SVG curve cannot be flattened at the requested precision.')
            levels = [points]
            while len(levels[-1]) > 1:
                levels.append(tuple(((a[0]+b[0])/2, (a[1]+b[1])/2)
                                    for a, b in zip(levels[-1], levels[-1][1:])))
            left = tuple(level[0] for level in levels)
            right = tuple(level[-1] for level in reversed(levels))
            pending.extend(((right, depth+1), (left, depth+1)))
        if len(result) + len(pending) > limit:
            raise ValueError('Simplify the SVG to reduce the number of plotting points.')
    return result
