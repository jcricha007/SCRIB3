"""Immutable, validated job snapshots created from reviewed workspace geometry."""
from dataclasses import dataclass

from .drawing import Drawing, Sheet
from .gcode import Machine, review_gcode


@dataclass(frozen=True)
class PlotJob:
    drawing: Drawing
    sheet: Sheet
    machine: Machine
    units: str
    dry_run: bool
    settings: tuple
    reference: int

    def review(self):
        return review_gcode(self.drawing, self.sheet, self.machine, self.units, dry_run=self.dry_run)

    def program(self):
        return self.review().program

    def commands(self):
        lines = tuple(line for line in self.program().splitlines() if line and not line.startswith('('))
        if len(lines) > 150000 or any(len(line.encode('ascii')) > 79 for line in lines):
            raise ValueError('The generated job exceeds the supported GRBL line limits.')
        return lines
