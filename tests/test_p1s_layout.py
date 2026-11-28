from dataclasses import replace
from hashlib import md5
from io import BytesIO
import json
from zipfile import ZipFile

import pytest

from scrib3.board import Board, Mark
from scrib3.p1s_layout import Layout, PaperSetup, clip_path
from scrib3.printer_output import Holder, plan_printer


HOLDER = Holder("P1S", 4.3352, -3.1234, 1.2, 5, 7, 30, 8, 8)
STOCK = PaperSetup(160, 120, 30, 45, 4, 5, 7, 6, 10)
INK = "#222222"
RED = "#cc4422"
BOARD = Board(230, 155, (Mark(INK, ((1,1), (229,154)), ("Art",)),
                         Mark(RED, ((12,15), (225,150)))), hidden=frozenset((RED,)))


def test_retraced_segment_and_outside_excursion_are_preserved():
    path = ((-1,3),(4,3),(12,3),(12,6),(5,6),(4,6),(5,6))
    assert list(clip_path(path,(0,0,10,10))) == [
        ((0,3),(4,3),(10,3)), ((10,6),(5,6),(4,6),(5,6))]


def test_scale_clip_bands_and_crosses_in_source_coordinates():
    layout = Layout(BOARD, HOLDER, STOCK)
    assert (layout.rows,layout.cols) == (2,2)
    centers = []
    for i in range(4):
        row,col = divmod(i,layout.cols)
        tile = layout.tile(i)
        assert tile.pens() == (INK,)
        pairs = [m.points for m in tile.marks if m.groups == ("Registration",)]
        centers.append({(round(col*layout.sx+(p[0][0]+p[1][0])/2,4),
                         round(row*layout.sy+(p[0][1]+p[1][1])/2,4)) for p in pairs})
        plan = layout.plan(i,dry=True)
        assert plan.scale == pytest.approx(1.0)
        for _, paths in plan.passes:
            for stroke in paths:
                for x,y in stroke:
                    for ax,ay in [(x,y),(x+HOLDER.offset_x,y+HOLDER.offset_y)]:
                        assert STOCK.left+STOCK.clip_left <= ax <= STOCK.left+STOCK.width-STOCK.clip_right
                        assert STOCK.front+STOCK.clip_front <= ay <= STOCK.front+STOCK.height-STOCK.clip_back
    assert all(len(centers[i] & centers[j]) == 2 for i,j in ((0,1),(0,2),(1,3),(2,3)))
    assert plan_printer(BOARD,HOLDER,area=layout.area,fit=True).scale < 1
    with pytest.raises(ValueError,match="Overlap"):
        Layout(BOARD,HOLDER,replace(STOCK,overlap=200))
    assert Layout(BOARD,HOLDER,replace(STOCK,overlap=200),tiled=False).rows == 1
    with pytest.raises(ValueError,match="P1S"):
        STOCK.area(replace(HOLDER,printer="H2S"))


@pytest.mark.parametrize("dry", (True, False))
def test_bundle_is_complete_and_individual_plates_keep_reviewed_program(tmp_path, dry):
    layout = Layout(BOARD,HOLDER,STOCK)
    dest = tmp_path/"poster.zip"
    layout.export(dest,dry)
    with ZipFile(dest) as archive:
        manifest = json.loads(archive.read("layout.json"))
        assert manifest["dry_run"] is dry and manifest["scale"] == 1
        assert len(manifest["tiles"]) == 4
        for i,tile in enumerate(manifest["tiles"]):
            assert tile["x_mm"] == pytest.approx((i%2)*layout.sx)
            assert tile["y_mm"] == pytest.approx((i//2)*layout.sy)
            with ZipFile(BytesIO(archive.read(tile["file"]))) as plate:
                gcode = plate.read("Metadata/plate_1.gcode")
                assert gcode == layout.plan(i,dry).gcode().encode("ascii")
                assert plate.read("Metadata/plate_1.gcode.md5") == md5(gcode).hexdigest().upper().encode()
                assert (b"G1 Z1.200 " in gcode) != dry
                assert gcode.rstrip().endswith(b"; SCRIB3 complete; pen raised.")


def test_failed_tile_keeps_previous_bundle(tmp_path, monkeypatch):
    layout = Layout(BOARD,HOLDER,STOCK)
    original = layout.plan
    def fail_second(i,dry):
        if i == 1:
            raise ValueError("failed second plate")
        return original(i,dry)
    monkeypatch.setattr(layout,"plan",fail_second)
    target = tmp_path/"poster.zip"
    target.write_bytes(b"previous poster")
    with pytest.raises(ValueError,match="second plate"):
        layout.export(target)
    assert target.read_bytes() == b"previous poster"
