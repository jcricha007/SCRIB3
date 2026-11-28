"""Registered, separately reviewed rows on a single DIY plot-quality test sheet."""
from dataclasses import dataclass
from math import cos, isfinite, pi, sin
from pathlib import Path
import json
import sqlite3

from .drawing import Drawing, Sheet


@dataclass(frozen=True)
class Trial:
    sheet: Sheet
    paths: Drawing
    feed: float


def checked_feeds(feeds):
    feeds = tuple(float(value) for value in feeds)
    if len(feeds) != 3 or not all(isfinite(v) and .001 <= v <= 100000 for v in feeds):
        raise ValueError("Enter three positive drawing feeds in mm/min.")
    if not feeds[0] < feeds[1] < feeds[2]:
        raise ValueError("Enter three increasing feeds.")
    return feeds


def trials(sheet, feeds):
    feeds = checked_feeds(feeds)
    margin = max(3, sheet.margin)
    size = min(18, (sheet.width-2*margin)/6, (sheet.height-2*margin)/6)
    if size < 3:
        raise ValueError("Increase the paper size or reduce the margin to fit the test sheet.")
    left = (sheet.width - 5*size)/2
    rows = []
    for index, feed in enumerate(feeds):
        # Paper coordinates are Y-up. Row one is physically at the top.
        y = sheet.height - margin - (index+.5)*(sheet.height-2*margin)/3
        circle = tuple((left + size*(.5+.5*cos(i*pi/32)), y+.5*size*sin(i*pi/32)) for i in range(64))
        diagonal = ((left+1.5*size, y-size/2), (left+2.5*size, y+size/2),
                    (left+2.5*size, y-size/2), (left+1.5*size, y+size/2))
        corner = tuple((left+size*x, y+size*dy) for x, dy in ((3, -.5), (3, .5), (4, .5), (4, -.5), (5, -.5)))
        rows.append(Trial(sheet, (circle+(circle[0],), diagonal, corner), feed))
    return tuple(rows)


RATINGS = ("Untested", "Clean", "Chatter", "Skipped line", "Open seam")


def profile_store(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS cards (pen TEXT, paper TEXT, data TEXT NOT NULL, PRIMARY KEY(pen,paper))")
    return db


def save_card(db, pen, paper, feeds, ratings, notes, winner):
    pen, paper = pen.strip(), paper.strip()
    if not pen or not paper:
        raise ValueError("Name the pen and paper before saving.")
    if len(ratings) != 3 or any(r not in RATINGS for r in ratings) or winner not in range(3) or ratings[winner] != "Clean":
        raise ValueError("Rate the winning row Clean before saving.")
    data = dict(feeds=list(checked_feeds(feeds)), ratings=list(ratings), notes=notes, winner=winner)
    with db:
        db.execute("INSERT OR REPLACE INTO cards VALUES (?,?,?)", (pen, paper, json.dumps(data, allow_nan=False)))
    return data
