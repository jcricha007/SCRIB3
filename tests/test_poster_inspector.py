import pytest
from scrib3.board import Board, Mark, bounds
from scrib3.poster_inspector import guide_targets, place, snap_axis
from scrib3.poster_objects import StrokeText
from scrib3.units import to_mm


def test_absolute_size_position_and_artwork_ownership():
    pen = "#222222"
    text = StrokeText("logo","GT40").marks(pen,("Logo",))
    board = Board(marks=(*text, Mark("#000000",((0,0),(1,1)))), locked=frozenset(("#000000",)))
    source = bounds(text)
    changed = place(board,{0,len(text)},to_mm(1,"in"),20,50,30)
    result = bounds(changed.marks[:-1])
    assert result == pytest.approx((25.4,20,75.4,50))
    assert changed.marks[-1] == board.marks[-1]
    assert changed.marks[0].text.frame != text[0].text.frame and changed.marks[0].groups == ("Logo",)
    ratio = (source[2]-source[0])/(source[3]-source[1])
    locked = place(board,{0},4,5,80,10,keep_aspect=True,driver="height")
    assert bounds(locked.marks[:-1]) == pytest.approx((4,5,4+ratio*10,15))


def test_guides_and_flat_paths():
    b = Board(marks=(Mark("#101010",((3,4),(3,9))),Mark("#cc0000",((12,20),(15,30)),("A",))))
    moved = place(b,{0},10,20,0,15)
    assert bounds(moved.marks[:1]) == (10,20,10,35)
    with pytest.raises(ValueError):
        place(b,{0},0,0,8,16)
    xs, ys = guide_targets(b,{0})
    assert 12 in xs and 20 in ys and 3 not in xs
    assert snap_axis(0,2,11.9,xs,.4) == (12,12)
    assert snap_axis(0,2,40,xs,.4) == (40,None)
