from dataclasses import replace
from io import BytesIO

from PIL import Image
import pytest

from scrib3.board import Board, Mark, save_board, load_board
from scrib3.board_library import BoardLibrary
from scrib3.poster_objects import StrokeText


ART = Board(marks=StrokeText("title","GT40").marks("#18283b",("Title block",)))


def test_gallery_refreshes_modified_artwork_and_discovers_older_assets(tmp_path):
    library = BoardLibrary(tmp_path)
    path = tmp_path/"garage.scrib3"
    save_board(path,ART)
    library.remember(path,ART)
    entry, = library.entries("Boards")
    assert entry.name == "garage" and Image.open(BytesIO(entry.image)).size == (130,76)
    other = replace(ART,marks=(Mark("#cc0000",((0,0),(285,200))),))
    save_board(path,other)
    assert library.entries("Boards")[0].image != entry.image
    for kind in ("Templates","Elements"):
        folder = tmp_path/kind.lower()
        folder.mkdir()
        save_board(folder/"Title block.scrib3",ART)
        assert [e.name for e in library.entries(kind)] == ["Title block"]
    path.unlink()
    assert library.entries("Boards") == []


def test_recovery_restores_rich_art_and_blank_edits_only_after_owner_exits(tmp_path):
    a, b, reader = [BoardLibrary(tmp_path) for _ in range(3)]
    a.checkpoint(ART,"Garage poster")
    b.checkpoint(Board(),"Empty page")
    assert reader.entries("Recovery") == []
    a.release()
    item, = reader.entries("Recovery")
    assert reader.restore(item) == ART
    reader.checkpoint(ART,"Garage poster",recovered=item)
    with pytest.raises(ValueError,match="already"):
        a.restore(item)
    b.release()
    second, = reader.entries("Recovery")
    assert reader.restore(second) == Board()
    reader.clear()
    assert a.entries("Recovery") == [second]
    a.checkpoint(Board(),"Empty page",recovered=second)
    a.clear()
    assert reader.entries("Recovery") == []


def test_recent_boards_are_bounded_and_reopening_updates_order(tmp_path):
    library = BoardLibrary(tmp_path)
    for n in range(32):
        p = tmp_path / f"sheet-{n:02d}.scrib3"
        save_board(p,Board())
        library.remember(p,Board())
    p = tmp_path/"sheet-02.scrib3"
    library.remember(p,load_board(p))
    items = library.entries("Boards")
    assert len(items) == 30 and items[0].name == "sheet-02"
    assert "sheet-00" not in [e.name for e in items]
