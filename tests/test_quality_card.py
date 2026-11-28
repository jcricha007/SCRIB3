import math
import pytest
from scrib3.drawing import Sheet
from scrib3.quality_card import trials, profile_store, save_card
from scrib3.gcode import Machine, review_gcode


def test_registered_rows_keep_geometry_and_run_through_normal_preflight():
    sheet = Sheet(120, 90, 4)
    rows = trials(sheet, (450, 700, 950))
    reference = rows[0].paths
    for row in rows:
        offset = row.paths[0][0][1] - reference[0][0][1]
        for path, other in zip(row.paths, reference):
            for (x,y), (a,b) in zip(path, other):
                assert (x,y) == pytest.approx((a,b+offset))
                assert 0 < x < sheet.width and 0 < y < sheet.height
        assert row.paths[0][0] == row.paths[0][-1]
        m = Machine(120,90,row.feed,"M5","M3 S100",.5)
        for dry in (False, True):
            review = review_gcode(row.paths,sheet,m,dry_run=dry)
            assert review.preflight.pen_up_travels == 3
            assert f"F{row.feed:.3f}" in review.program and review.program.count("G4 P10.000") == 1
            assert ("M3 S100.000" in review.program) != dry
    with pytest.raises(ValueError):
        trials(sheet, (500,500,math.nan))


def test_winning_feed_is_saved_by_pen_and_stock(tmp_path):
    db = profile_store(tmp_path/"cards.db")
    try:
        args = ("Fineliner", "Cardstock", (400,600,800), ("Clean","Clean","Chatter"), "Corners", 1)
        data = save_card(db,*args)
        assert data["feeds"][data["winner"]] == 600
        save_card(db,*args)
        save_card(db,args[0],"Letter",*args[2:])
        assert db.execute("SELECT count(*) FROM cards").fetchone()[0] == 2
        with pytest.raises(ValueError):
            save_card(db,*args[:-1],2)
    finally:
        db.close()
