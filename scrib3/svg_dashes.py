"""Convert SVG dash styling into separate physical pen strokes."""
from math import dist, isfinite
import re

from svgelements import Length

_LENGTH = re.compile(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?(?:px|mm|cm|in|pt|pc|Q)?\Z')


def dash_pattern(values):
    raw = str(values.get('stroke-dasharray', 'none')).strip()
    if raw == 'none':
        return None
    if values.get('vector-effect', 'none') != 'none' or 'pathLength' in values:
        raise ValueError('Convert dashed SVG pathLength/vector-effect strokes to ordinary paths before importing.')
    def length(token):
        if not _LENGTH.fullmatch(token):
            raise ValueError('Use numeric or physical-unit SVG dashes; convert percentage/font-relative dashes to paths.')
        result = float(Length(token).value(ppi=96))
        if not isfinite(result):
            raise ValueError('SVG dash lengths must be finite.')
        return result
    tokens = re.split(r'[\s,]+', raw)
    if not 1 <= len(tokens) <= 256:
        raise ValueError('Simplify the SVG dash pattern.')
    pattern = tuple(length(t) for t in tokens)
    if any(v < 0 for v in pattern):
        raise ValueError('SVG dash lengths must not be negative.')
    if not sum(pattern):
        return None  # SVG defines an all-zero array as an undashed stroke.
    if len(pattern) % 2:
        pattern *= 2
    if values.get('stroke-linecap', 'butt') != 'butt' and any(v == 0 for v in pattern[::2]):
        raise ValueError('Convert zero-length dotted strokes to explicit paths before importing.')
    offset = length(str(values.get('stroke-dashoffset', '0')).strip())
    return pattern, offset


def split_dashes(stroke, pattern, offset, max_strokes=2000, max_points=100000):
    """Dash one flattened subpath in its own coordinate system.

    Phase restarts at each Move, continues through vertices, and wraps across a
    closed seam. All-zero patterns are handled by dash_pattern, not this walker.
    """
    period = sum(pattern)
    phase = offset % period
    index = 0
    while pattern[index] == 0 or phase >= pattern[index]:
        phase -= pattern[index]
        index = (index+1) % len(pattern)
    remaining = pattern[index]-phase
    paths, ink = [], []
    point_count = steps = 0

    def finish():
        nonlocal ink
        if len(ink) > 1:
            paths.append(tuple(ink))
            if len(paths) > max_strokes:
                raise ValueError('SVG dashes exceed the 2,000 stroke limit. Increase dash spacing.')
        ink = []

    for a, b in zip(stroke, stroke[1:]):
        size = dist(a, b)
        if not size:
            continue
        used = 0.0
        while used < size:
            steps += 1
            if steps > 200000:
                raise ValueError('SVG dash pattern is too dense. Increase dash spacing.')
            take = min(remaining, size-used)
            end = used+take
            if end <= used:
                raise ValueError('SVG dash spacing is too small for these coordinates.')
            at = lambda t: a if t == 0 else b if t == size else (a[0]+(b[0]-a[0])*t/size, a[1]+(b[1]-a[1])*t/size)
            if index % 2 == 0:
                if not ink:
                    ink.append(at(used)); point_count += 1
                ink.append(at(end)); point_count += 1
                if point_count > max_points:
                    raise ValueError('SVG dashes exceed the point limit. Increase dash spacing.')
            used = end
            remaining -= take
            if remaining <= 0:
                index = (index+1) % len(pattern)
                while pattern[index] == 0:
                    index = (index+1) % len(pattern)
                remaining = pattern[index]
                if index % 2:
                    finish()
    finish()
    if len(paths) > 1 and stroke[0] == stroke[-1] and paths[0][0] == paths[-1][-1]:
        paths[0] = paths[-1] + paths[0][1:]
        paths.pop()
    return tuple(paths)
