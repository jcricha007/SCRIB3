"""Playback of the serialized, preflighted GRBL program in sender line order."""
from bisect import bisect_right
from dataclasses import dataclass
from math import dist

from .gcode_preflight import XY, DWELL
from .units import factor


@dataclass(frozen=True)
class Event:
    command: str
    kind: str
    xy: tuple
    down: bool
    stroke: int
    end: float


class PlotTimeline:
    def __init__(self, job, review, start=(0., 0.)):
        scale = factor(job.units)
        settings = dict(job.settings)
        rates = tuple(settings.get(axis) or job.machine.feed for axis in (110, 111))
        self.start = tuple(start[:2])
        self.sheet, self.mount = job.sheet, job.machine.paper_mount
        self.events = []
        self.hold_seconds = 0.
        xy, down, stroke, elapsed = self.start, False, 0, 0.
        after_travel = first_hold = False
        for line in review.program.splitlines()[1:]:
            seconds = 0.
            if move := XY.fullmatch(line):
                target = float(move[2]) * scale, float(move[3]) * scale
                if move[1] == "G0":
                    kind = "Travel"
                    seconds = 60 * max(abs(a-b) / max(.001, rate) for a, b, rate in zip(xy, target, rates))
                    stroke += 1
                    first_hold = stroke == 1
                    after_travel = True
                else:
                    kind = "Draw" if down else "Dry stroke"
                    if move[4]:
                        feed = float(move[4]) * scale
                    seconds = 60 * dist(xy, target) / feed
                xy = target
            elif dwell := DWELL.fullmatch(line):
                seconds = float(dwell[1])
                self.hold_seconds += seconds
                kind = "Start hold" if first_hold else "Pen settle"
                first_hold = False
            elif line.startswith(("G20 ", "G21 ")):
                kind = "Set units"
            else:
                down = after_travel and not job.dry_run
                kind = "Lower pen" if down else "Lift pen"
                after_travel = False
            self.events.append(Event(line, kind, xy, down, stroke, elapsed + seconds))
            elapsed += seconds
        self.ends = tuple(e.end for e in self.events)
        self.seconds = elapsed
        self.strokes = stroke

    def at_time(self, seconds):
        """Return completed sender commands, plus the fraction of the next command."""
        count = bisect_right(self.ends, max(0., seconds))
        if count == len(self.events):
            return count, 0.
        previous = self.ends[count-1] if count else 0.
        return count, max(0., (seconds-previous) / (self.ends[count]-previous))

    def paper_point(self, xy):
        x, y = xy
        return (y, -x) if self.mount == "top_left_y" else (x, self.sheet.height-y)
