"""Geometry-preserving stroke joining and bounded travel optimization."""
from collections import defaultdict
from math import dist

from .drawing import order_strokes, path_lengths


def _least_rotation(points):
    """Lexicographically least cyclic rotation in linear time (Booth's scan)."""
    n = len(points)
    doubled = points + points
    i, j, offset = 0, 1, 0
    while i < n and j < n and offset < n:
        a, b = doubled[i + offset], doubled[j + offset]
        if a == b:
            offset += 1
            continue
        if a > b:
            i += offset + 1
            if i <= j:
                i = j + 1
        else:
            j += offset + 1
            if j <= i:
                j = i + 1
        offset = 0
    first = min(i, j)
    return doubled[first:first + n]


def stroke_key(stroke):
    """Exact vertex identity, ignoring direction and a closed contour's seam."""
    if stroke[0] == stroke[-1]:
        ring = stroke[:-1]
        return ('closed', min(_least_rotation(ring), _least_rotation(ring[::-1])))
    return ('open', min(stroke, stroke[::-1]))


def join_exact_strokes(drawing):
    """Join degree-two endpoints only; never snap or bridge a gap.

    A vertex inside any stroke (including every vertex of a closed contour)
    blocks joining there. Branches therefore remain explicit pen lifts.
    """
    return tuple(stroke for _, stroke in joined_strokes_with_indices(drawing))


def joined_strokes_with_indices(drawing):
    """Yield each joined path at its earliest contributing input index."""
    endpoints = defaultdict(list)
    blocked = set()
    for index, stroke in enumerate(drawing):
        if stroke[0] == stroke[-1]:
            blocked.update(stroke)
        else:
            endpoints[stroke[0]].append((index, False))
            endpoints[stroke[-1]].append((index, True))
            blocked.update(stroke[1:-1])

    def neighbor(point, current):
        entries = endpoints.get(point, ())
        if point in blocked or len(entries) != 2:
            return None
        return next((entry for entry in entries if entry[0] != current), None)

    used = set()
    for first, stroke in enumerate(drawing):
        if first in used:
            continue
        used.add(first)
        # Extend both ends with lists of pieces, avoiding quadratic tuple copies.
        pieces = [stroke]
        current, point = first, stroke[-1]
        while (entry := neighbor(point, current)) is not None and entry[0] not in used:
            current, reverse = entry
            used.add(current)
            piece = drawing[current][::-1] if reverse else drawing[current]
            pieces.append(piece)
            point = piece[-1]
        prefix = []
        current, point = first, stroke[0]
        while (entry := neighbor(point, current)) is not None and entry[0] not in used:
            current, reverse = entry
            used.add(current)
            piece = drawing[current] if reverse else drawing[current][::-1]
            prefix.append(piece)
            point = piece[0]
        pieces = prefix[::-1] + pieces
        points = list(pieces[0])
        for piece in pieces[1:]:
            points.extend(piece[1:])
        yield first, tuple(points)


def _rotate_loop(stroke, before, after=None):
    if stroke[0] != stroke[-1]:
        return stroke
    ring = stroke[:-1]

    def cost(point):
        return dist(before, point) + (dist(point, after) if after is not None else 0)

    index = min(range(len(ring)), key=lambda i: cost(ring[i]))
    if cost(ring[index]) >= cost(ring[0]) - 1e-12:
        return stroke
    ring = ring[index:] + ring[:index]
    return ring + (ring[0],)


def _relocate_seams(drawing, start):
    result = list(drawing)
    previous = start
    for i, stroke in enumerate(result):
        after = result[i + 1][0] if i + 1 < len(result) else None
        result[i] = _rotate_loop(stroke, previous, after)
        previous = result[i][-1]
    return tuple(result)


def _two_opt_pass(drawing, start, window=32):
    # Reverse a route section AND the direction of every stroke in it. Internal
    # travel stays identical; only the two boundary distances need comparison.
    # Keep orientation separately so large strokes are copied only once per pass.
    route = [(stroke, False) for stroke in drawing]

    def entry(i):
        stroke, reverse = route[i]
        return stroke[-1 if reverse else 0]

    def exit_point(i):
        stroke, reverse = route[i]
        return stroke[0 if reverse else -1]

    for i in range(len(route)):
        previous = exit_point(i - 1) if i else start
        for j in range(i, min(len(route), i + window)):
            after = entry(j + 1) if j + 1 < len(route) else None
            first, last = entry(i), exit_point(j)
            old = dist(previous, first) + (dist(last, after) if after is not None else 0)
            new = dist(previous, last) + (dist(first, after) if after is not None else 0)
            if new < old - 1e-12:
                route[i:j + 1] = [(s, not reverse) for s, reverse in reversed(route[i:j + 1])]
    return tuple(stroke[::-1] if reverse else stroke for stroke, reverse in route)


def _large_greedy_route(drawing, start):
    """Delete visited endpoint pairs from a periodically rebuilt spatial index."""
    from scipy.spatial import cKDTree
    pending = set(range(len(drawing)))
    route = []
    position = start
    while pending:
        ends = [(i, side) for i in sorted(pending) for side in (0, -1)]
        tree = cKDTree([drawing[i][side] for i, side in ends])
        rebuild_at = len(pending) // 2
        while len(pending) > rebuild_at:
            k = min(8, len(ends))
            while True:
                _, nearest = tree.query(position, k=k)
                hit = next((ends[j] for j in nearest if ends[j][0] in pending), None)
                if hit is not None:
                    break
                k = min(k*2, len(ends))
            i, side = hit
            stroke = drawing[i] if side == 0 else drawing[i][::-1]
            route.append(stroke)
            position = stroke[-1]
            pending.remove(i)
    return tuple(route)


def optimize_route(drawing, start=(0, 0), reloop=True):
    """Greedy route plus three local passes, retaining the shortest route found.

    Travel includes the move from origin and ends at the last stroke. Closed
    seams only move to existing vertices. This is a bounded heuristic, not an
    exact traveling-salesman solver, and never increases input route distance.
    """
    def travel(route):
        return path_lengths(route, start)[1]

    seed = tuple(_rotate_loop(s, start) for s in drawing) if reloop else drawing
    greedy = _large_greedy_route if len(seed) > 2000 else order_strokes
    result = min((drawing, greedy(seed, start)), key=travel)
    for _ in range(3):
        candidate = _relocate_seams(result, start) if reloop else result
        candidate = _two_opt_pass(candidate, start)
        if travel(candidate) >= travel(result) - 1e-12:
            break
        result = candidate
    return result
