"""P1S stock placement, conservative clip bands and overlapping 1:1 sheets."""
from dataclasses import asdict, dataclass
from math import ceil, floor, isfinite
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile, ZIP_STORED

from .atomic_export import write_atomic_export
from .board import Board, Mark
from .printer_output import plan_printer


@dataclass(frozen=True)
class PaperSetup:
    width: float = 210
    height: float = 148
    left: float = 23
    front: float = 40
    clip_left: float = 0
    clip_front: float = 0
    clip_right: float = 0
    clip_back: float = 0
    overlap: float = 10

    def area(self, holder):
        if holder.printer != "P1S":
            raise ValueError("Choose a P1S holder.")
        a,b,c,d = holder.reach()
        if not all(isfinite(v) for v in vars(self).values()):
            raise ValueError("Enter finite stock measurements in mm.")
        l,f,w,h = self.left,self.front,self.width,self.height
        if min(l,f)<0 or min(w,h)<1 or l+w>256 or f+h>256:
            raise ValueError("Place the physical sheet completely inside the 256 mm bed.")
        if min(self.clip_left,self.clip_front,self.clip_right,self.clip_back)<0:
            raise ValueError("Clip strip widths must be nonnegative.")
        # A clip band excludes both the nozzle and the offset pen tip.
        x0 = max(a,l+self.clip_left+(max(0,holder.offset_x) if self.clip_left else 0))
        y0 = max(b,f+self.clip_front+(max(0,holder.offset_y) if self.clip_front else 0))
        x1 = min(c,l+w-self.clip_right+(min(0,holder.offset_x) if self.clip_right else 0))
        y1 = min(d,f+h-self.clip_back+(min(0,holder.offset_y) if self.clip_back else 0))
        # G-code serializes nozzle coordinates to 0.001 mm. Move each limit inward to that grid.
        def inward(value, offset, rounding):
            return rounding(round((value-offset)*1000, 9))/1000 + offset
        x0 = max(x0, inward(x0, holder.offset_x, ceil))
        y0 = max(y0, inward(y0, holder.offset_y, ceil))
        x1 = min(x1, inward(x1, holder.offset_x, floor))
        y1 = min(y1, inward(y1, holder.offset_y, floor))
        if min(x1-x0,y1-y0)<1:
            raise ValueError("The stock, clips and holder leave no printable area.")
        return x0,y0,x1,y1


def clip_path(points, rect):
    """Clip each authored segment in order, retaining reversals and disconnected pieces."""
    l,t,r,b = rect
    run = []
    for (x,y),(a,c) in zip(points,points[1:]):
        dx,dy = a-x,c-y
        lo,hi = 0.,1.
        for p,q in ((-dx,x-l),(dx,r-x),(-dy,y-t),(dy,b-y)):
            if p == 0:
                if q < 0:
                    hi = -1
                    break
            elif p < 0:
                lo = max(lo,q/p)
            else:
                hi = min(hi,q/p)
        if hi <= lo:
            if len(run)>1:
                yield tuple(run)
            run = []
            continue
        def pt(u):
            xx, yy = (a,c) if u == 1 else (x+u*dx,y+u*dy)
            return max(0,min(r-l,xx-l)),max(0,min(b-t,yy-t))
        first,last = pt(lo),pt(hi)
        if first == last:
            continue
        if not run or run[-1] != first:
            if len(run)>1:
                yield tuple(run)
            run = [first]
        run.append(last)
    if len(run)>1:
        yield tuple(run)


def sheet_grid(board, width, height, overlap, tiled):
    if not tiled:
        return 1, 1
    if not 3 <= overlap < min(width, height)/2:
        raise ValueError("Overlap must be at least 3 mm and less than half the printable width and height.")
    cols = 1 + max(0, ceil((board.width-width-1e-9)/(width-overlap)))
    rows = 1 + max(0, ceil((board.height-height-1e-9)/(height-overlap)))
    if cols*rows > 256:
        raise ValueError("Use larger sheets or a smaller poster (maximum 256 tiles).")
    return rows, cols


class Layout:
    def __init__(self, board, holder, setup, *, tiled=True):
        self.board, self.holder, self.setup = board.checked(), holder, setup
        self.area = setup.area(holder)
        l,f,r,b = self.area
        self.width,self.height = r-l,b-f
        overlap = setup.overlap
        self.sx,self.sy = self.width-overlap,self.height-overlap
        self.rows, self.cols = sheet_grid(board, self.width, self.height, overlap, tiled)
        self.inks = board.pens()
        if not self.inks:
            raise ValueError("Add a visible pen layer first.")
        for mark in board.marks:
            if mark.color not in board.hidden and any(not (0<=x<=board.width and 0<=y<=board.height) for x,y in mark.points):
                raise ValueError("Move visible artwork inside the board before output.")

    def tile(self, index):
        if not 0 <= index < self.rows*self.cols:
            raise ValueError("Choose an existing tile.")
        row,col = divmod(index,self.cols)
        x,y = col*self.sx,row*self.sy
        rect = x,y,x+self.width,y+self.height
        marks = [Mark(m.color,p,m.groups) for m in self.board.marks if m.color not in self.board.hidden
                 for p in clip_path(m.points,rect)]
        # Adjacent sheets share the same two cross centers in poster coordinates.
        overlap = self.setup.overlap
        maxx,maxy = min(self.width,self.board.width-x),min(self.height,self.board.height-y)
        centers = []
        for seam in ([overlap/2] if col else [])+([self.sx+overlap/2] if col+1<self.cols else []):
            centers.extend((seam,maxy*f) for f in (.25,.75))
        for seam in ([overlap/2] if row else [])+([self.sy+overlap/2] if row+1<self.rows else []):
            centers.extend((maxx*f,seam) for f in (.25,.75))
        arm = min(1.5,overlap/4,maxx/5,maxy/5)
        for cx,cy in centers:
            marks.extend((Mark(self.inks[0],((cx-arm,cy),(cx+arm,cy)),("Registration",)),
                          Mark(self.inks[0],((cx,cy-arm),(cx,cy+arm)),("Registration",))))
        return Board(self.width,self.height,tuple(marks),pen_order=self.inks).checked()

    def plan(self, index, dry):
        return plan_printer(self.tile(index), self.holder, area=self.area, dry=dry)

    def export(self, path, dry=True):
        def encode(staged):
            manifest = dict(scale=1, units="mm", paper=asdict(self.setup), holder=asdict(self.holder),
                            board_mm=[self.board.width,self.board.height], rows=self.rows, columns=self.cols,
                            source_origin="top left", dry_run=dry, tiles=[])
            with TemporaryDirectory(dir=staged.parent) as tmp, ZipFile(staged,"w",ZIP_STORED) as archive:
                for i in range(self.rows*self.cols):
                    row,col = divmod(i,self.cols)
                    name = f"row-{row+1:02d}-col-{col+1:02d}.gcode.3mf"
                    plate = Path(tmp)/name
                    self.plan(i,dry).export(plate)
                    archive.write(plate,name)
                    plate.unlink()
                    manifest["tiles"].append(dict(file=name, x_mm=col*self.sx, y_mm=row*self.sy))
                archive.writestr("layout.json",json.dumps(manifest,indent=2,allow_nan=False))
                archive.writestr("assembly.txt","Use a fresh sheet at the saved bed position for each numbered plate. "
                                 "Rows run top to bottom and columns left to right. Align the matching crosses in the overlaps.")
        write_atomic_export(Path(path),encode)
