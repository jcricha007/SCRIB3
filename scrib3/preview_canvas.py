"""Draw board paths in a common physical coordinate system."""

from .board import bounds
from . import theme


def paint_paths(canvas, layers, bbox=None, zoom=1, center=None, pen_width=0.35, *, paper=False):
    """Overlay paths in one common coordinate system and scale widths to paper mm."""
    canvas.delete("all")
    nonempty = [m for marks, _, _ in layers for m in marks]
    if not nonempty and not (paper and bbox):
        return
    x0, y0, x1, y1 = bbox or bounds(nonempty)
    width, height = max(64, canvas.winfo_width()), max(64, canvas.winfo_height())
    inset = 50 if paper else 24
    scale = zoom * min((width - inset) / max(0.01, x1 - x0), (height - inset) / max(0.01, y1 - y0))
    cx, cy = center or ((x0 + x1) / 2, (y0 + y1) / 2)
    if paper:
        left, top = (x0 - cx) * scale + width / 2, (y0 - cy) * scale + height / 2
        right, bottom = left + (x1 - x0) * scale, top + (y1 - y0) * scale
        canvas.create_rectangle(left+3, top+4, right+3, bottom+4, fill=theme.BORDER, outline="")
        canvas.create_rectangle(left, top, right, bottom, fill=theme.PAPER, outline="#b6c3d2", tags="sheet")
        if not nonempty:
            canvas.create_text(width / 2, height / 2, text="No visible paths", fill=theme.MUTED)
    for marks, color, extra in layers:
        for m in marks:
            coords = [
                v
                for x, y in m.points
                for v in ((x - cx) * scale + width / 2, (y - cy) * scale + height / 2)
            ]
            canvas.create_line(
                *coords, fill=color or m.color, width=max(1, pen_width * scale) + extra
            )
    return cx, cy, scale
