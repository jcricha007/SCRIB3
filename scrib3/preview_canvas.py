"""Draw board paths in a common physical coordinate system."""

from .board import bounds


def paint_paths(canvas, layers, bbox=None, zoom=1, center=None, pen_width=0.35):
    """Overlay paths in one common coordinate system and scale widths to paper mm."""
    canvas.delete("all")
    nonempty = [m for marks, _, _ in layers for m in marks]
    if not nonempty:
        return
    x0, y0, x1, y1 = bbox or bounds(nonempty)
    width, height = max(64, canvas.winfo_width()), max(64, canvas.winfo_height())
    scale = zoom * min((width - 24) / max(0.01, x1 - x0), (height - 24) / max(0.01, y1 - y0))
    cx, cy = center or ((x0 + x1) / 2, (y0 + y1) / 2)
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
