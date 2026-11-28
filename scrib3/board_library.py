"""Local artwork catalog and transactionally saved per-session recovery copies."""
from contextlib import closing, contextmanager
from dataclasses import dataclass
from io import BytesIO
import os
from pathlib import Path
import sqlite3
from time import time_ns
from uuid import uuid4

from PIL import Image, ImageDraw

from .board import bounds, decode_board, encode_board, load_board


@dataclass(frozen=True)
class Entry:
    key: str
    name: str
    image: bytes
    updated: int


def thumbnail(board, *, element=False):
    image = Image.new("RGB", (130, 76), "#dce4ed")
    draw = ImageDraw.Draw(image)
    marks = [m for m in board.marks if m.color not in board.hidden]
    x, y, right, bottom = bounds(marks) if element and marks else (0, 0, board.width, board.height)
    width, height = max(.1, right-x), max(.1, bottom-y)
    scale = min(120/width, 68/height)
    left, top = (130-width*scale)/2, (76-height*scale)/2
    draw.rectangle((left, top, left+width*scale, top+height*scale), fill="white")
    for mark in marks:
        draw.line([(left+(px-x)*scale, top+(py-y)*scale) for px, py in mark.points], fill=mark.color)
    stream = BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def lock_session(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)


class BoardLibrary:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / "board-library.sqlite3"
        self.session = uuid4().hex
        self.lease = None

    @contextmanager
    def database(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=3)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS catalog (
                kind TEXT, path TEXT, visited INTEGER, modified INTEGER, size INTEGER, preview BLOB,
                PRIMARY KEY(kind, path))""")
            db.execute("""CREATE TABLE IF NOT EXISTS drafts (
                session TEXT PRIMARY KEY, name TEXT, updated INTEGER, board BLOB, preview BLOB)""")
            yield db

    def remember(self, path, board, kind="Boards", *, visit=True):
        path = Path(path).resolve()
        stat = path.stat()
        with self.database() as db:
            row = db.execute("SELECT modified,size FROM catalog WHERE kind=? AND path=?", (kind,str(path))).fetchone()
            if row == (stat.st_mtime_ns, stat.st_size):
                if visit:
                    db.execute("UPDATE catalog SET visited=? WHERE kind=? AND path=?", (time_ns(),kind,str(path)))
                return
            db.execute("""INSERT INTO catalog VALUES (?,?,?,?,?,?)
                ON CONFLICT(kind,path) DO UPDATE SET modified=excluded.modified, size=excluded.size,
                preview=excluded.preview, visited=CASE WHEN ? THEN excluded.visited ELSE visited END""",
                (kind,str(path),time_ns() if visit else stat.st_mtime_ns,stat.st_mtime_ns,stat.st_size,
                 thumbnail(board,element=kind=="Elements"),visit))
            if kind == "Boards":
                db.execute("""DELETE FROM catalog WHERE kind='Boards' AND path NOT IN
                    (SELECT path FROM catalog WHERE kind='Boards' ORDER BY visited DESC LIMIT 30)""")

    def entries(self, kind):
        if kind == "Recovery":
            if not self.path.exists():
                return []
            with self.database() as db:
                rows = db.execute("SELECT session,name,preview,updated FROM drafts ORDER BY updated DESC").fetchall()
            return [Entry(*row) for row in rows if row[0] != self.session and self.inactive(row[0])]
        with self.database() as db:
            known = {Path(p):(m,s) for p,m,s in db.execute(
                "SELECT path,modified,size FROM catalog WHERE kind=?", (kind,))}
        candidates = set(known)
        if kind in ("Elements","Templates"):
            candidates.update(p.resolve() for p in (self.folder/kind.lower()).glob("*.scrib3"))
        available = set()
        for path in candidates:
            try:
                stat = path.stat()
                if known.get(path) != (stat.st_mtime_ns, stat.st_size):
                    self.remember(path,load_board(path),kind,visit=False)
                available.add(str(path))
            except (ValueError, OSError):
                continue
        with self.database() as db:
            rows = db.execute("SELECT path,preview,visited FROM catalog WHERE kind=? ORDER BY visited DESC", (kind,)).fetchall()
        return [Entry(path, Path(path).stem, preview, visited) for path, preview, visited in rows if path in available]

    def lock_path(self, session):
        return self.folder / ("board-session-"+session+".lock")

    def inactive(self, session):
        try:
            with self.lock_path(session).open("r+b") as stream:
                lock_session(stream)
        except FileNotFoundError:
            return True
        except OSError:
            return False
        return True

    def acquire(self):
        if self.lease is None:
            self.folder.mkdir(parents=True, exist_ok=True)
            lease = self.lock_path(self.session).open("w+b")
            try:
                lease.write(b"0")
                lease.flush()
                lock_session(lease)
            except OSError:
                lease.close()
                raise
            self.lease = lease

    def checkpoint(self, board, name, *, recovered=None):
        payload = encode_board(board)
        preview = thumbnail(board)
        self.acquire()
        with self.database() as db:
            db.execute("INSERT OR REPLACE INTO drafts VALUES (?,?,?,?,?)",
                       (self.session,name,time_ns(),payload,preview))
            if recovered is not None:
                claimed = db.execute("DELETE FROM drafts WHERE session=? AND updated=?", (recovered.key,recovered.updated))
                if not claimed.rowcount:
                    raise ValueError("This recovery copy has already been opened. Refresh the library.")
        if recovered is not None:
            self.remove_lock(recovered.key)

    def restore(self, entry):
        with self.database() as db:
            row = db.execute("SELECT board FROM drafts WHERE session=? AND updated=?", (entry.key,entry.updated)).fetchone()
        if row is None:
            raise ValueError("This recovery copy has already been opened. Refresh the library.")
        return decode_board(row[0])

    def clear(self):
        if self.lease is not None:
            with self.database() as db:
                db.execute("DELETE FROM drafts WHERE session=?", (self.session,))
            self.release()

    def remove_lock(self, session):
        try:
            self.lock_path(session).unlink(missing_ok=True)
        except OSError:
            pass  # A concurrent gallery can briefly hold the lock file open on Windows.

    def release(self):
        if self.lease is not None:
            self.lease.close()
            self.lease = None
            self.remove_lock(self.session)
