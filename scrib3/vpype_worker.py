"""Isolated entry point for the pinned optional vpype optimizer."""
import json
from pathlib import Path
import sys

from .route_compare import checked_start, compare_candidate
from .vector_io import checked_drawing


def optimize(drawing, start):
    import vpype
    from vpype_cli import execute

    drawing, start = checked_drawing(drawing), checked_start(start)
    doc = vpype.Document()
    doc.add(vpype.LineCollection([[complex(x, y) for x, y in stroke] for stroke in drawing]), 1)
    # Eight passes cap work. No linemerge, reloop or simplification: this adapter
    # must preserve every original stroke, including intentional repeats/gaps.
    result = execute('linesort --two-opt --passes 8', doc)
    candidate = tuple(tuple((float(p.real), float(p.imag)) for p in line) for line in result.layers[1])
    return compare_candidate(drawing, candidate, start).drawing


def main():
    request, output = map(Path, sys.argv[1:])
    if request.stat().st_size > 12_000_000:
        raise ValueError('Oversized optimizer input.')
    data = json.loads(request.read_text(encoding='utf-8'))
    result = optimize(data['drawing'], data['start'])
    output.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
