"""Optional vpype route comparison; only order and direction may change."""
from collections import Counter
from dataclasses import dataclass
import json
from math import isfinite
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

from .drawing import path_lengths
from .vector_io import checked_drawing


@dataclass(frozen=True)
class RouteComparison:
    drawing: tuple
    before_mm: float
    after_mm: float

    @property
    def improved(self):
        return self.after_mm < self.before_mm - 1e-7


def checked_start(start):
    if len(start) != 2 or any(type(v) not in (int, float) or not isfinite(v) or abs(v) > 1e9 for v in start):
        raise ValueError('Route origin must be finite XY coordinates.')
    return tuple(start)


def compare_candidate(original, candidate, start):
    """Reject geometry edits, even if total length or bounds happen to match."""
    original, candidate = checked_drawing(original), checked_drawing(candidate)
    start = checked_start(start)
    key = lambda s: min(s, s[::-1])
    if Counter(map(key, original)) != Counter(map(key, candidate)):
        raise ValueError('Optimizer changed stroke geometry; result was rejected.')
    before = path_lengths(original, start)[1]
    # Include travel from the actual paper origin, which vpype linesort omits.
    reverse = tuple(s[::-1] for s in candidate[::-1])
    candidate = min((candidate, reverse), key=lambda d: path_lengths(d, start)[1])
    after = path_lengths(candidate, start)[1]
    if after >= before - 1e-7:
        return RouteComparison(original, before, before)
    return RouteComparison(candidate, before, after)


def run_vpype(drawing, start, cancel, timeout=30):
    drawing, start = checked_drawing(drawing), checked_start(start)
    if cancel.is_set():
        raise ValueError('Comparison cancelled.')
    with TemporaryDirectory(prefix='scrib3-route-') as folder:
        request, output, log = (Path(folder)/s for s in ('request.json', 'result.json', 'worker.log'))
        request.write_text(json.dumps({'drawing': drawing, 'start': start}, allow_nan=False), encoding='utf-8')
        with log.open('w', encoding='utf-8') as stream:
            process = subprocess.Popen([sys.executable, '-m', 'scrib3.vpype_worker', str(request), str(output)],
                                       cwd=Path(__file__).resolve().parent.parent,
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deadline = monotonic() + timeout
            try:
                while process.poll() is None:
                    if cancel.wait(.05):
                        raise ValueError('Comparison cancelled.')
                    if monotonic() >= deadline:
                        raise ValueError('Optimizer exceeded 30 seconds. The existing route is unchanged.')
                if cancel.is_set():
                    raise ValueError('Comparison cancelled.')
                if process.returncode or not output.exists():
                    raise ValueError('vpype could not run. Install requirements-optimizer.txt in the SCRIB3 Python environment.')
                if output.stat().st_size > 12_000_000:
                    raise ValueError('Optimizer result exceeded the size limit.')
                result = json.loads(output.read_text(encoding='utf-8'))
                return compare_candidate(drawing, result, start)
            finally:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
