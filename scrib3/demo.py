"""The editable artwork SCRIB3 opens on launch."""

from functools import cache
from pathlib import Path

from .board import Board, PAPER
from .drawing import Drawing
from .svg_artwork import import_svg


SAMPLE_NAME = "Isometric airframe"


@cache
def sample_board() -> Board:
    artwork = Path(__file__).with_name("assets") / "isometric-airframe.svg"
    return Board(*PAPER["Letter"], marks=import_svg(artwork)).checked()


def sample() -> Drawing:
    return tuple(mark.points for mark in sample_board().marks)
