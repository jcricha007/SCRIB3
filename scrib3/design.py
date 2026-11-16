"""Small vector design operations; source coordinates use Y down."""
from math import cos, sin, pi

from .drawing import Drawing, Sheet


def transform(drawing: Drawing, operation: str) -> Drawing:
    operations = {"Rotate 90°": lambda x, y: (-y, x),
                  "Mirror X": lambda x, y: (-x, y), "Mirror Y": lambda x, y: (x, -y)}
    if operation not in operations:
        raise ValueError("Choose a supported drawing transform.")
    return tuple(tuple(operations[operation](x, y) for x, y in stroke) for stroke in drawing)


def pattern(kind: str, count: int) -> Drawing:
    if type(count) is not int or not 3 <= count <= 40:
        raise ValueError("Detail must be a whole number from 3 to 40.")
    if kind == "Grid":
        return tuple(stroke for i in range(count + 1) for stroke in
                     (((i * 1000 / count, 0), (i * 1000 / count, 1000)),
                      ((0, i * 1000 / count), (1000, i * 1000 / count))))
    if kind == "Spiral":
        points = count * 80
        return (tuple((500 + 490 * i / points * cos(2 * pi * count * i / points),
                       500 + 490 * i / points * sin(2 * pi * count * i / points))
                      for i in range(points + 1)),)
    if kind == "Rosette":
        circles = tuple(tuple((500 + 280 * cos(2*pi*k/count) + 200 * cos(2*pi*i/96),
                            500 + 280 * sin(2*pi*k/count) + 200 * sin(2*pi*i/96))
                           for i in range(96)) for k in range(count))
        return tuple(points + (points[0],) for points in circles)
    raise ValueError("Choose Grid, Spiral, or Rosette.")


def svg_document(drawing: Drawing, sheet: Sheet) -> str:
    """Export the fitted paper geometry in physical mm with standard SVG Y down."""
    paths = []
    for stroke in drawing:
        points = " ".join(f"{x:.6f},{sheet.height-y:.6f}" for x, y in stroke)
        paths.append(f'  <polyline points="{points}" />')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{sheet.width:.6f}mm" '
            f'height="{sheet.height:.6f}mm" viewBox="0 0 {sheet.width:.6f} {sheet.height:.6f}">\n'
            '<g fill="none" stroke="black" stroke-width="0.2">\n' + '\n'.join(paths) + '\n</g>\n</svg>\n')


def ai_reference(drawing: Drawing) -> Drawing:
    if len(drawing) > 60 or any(len(stroke) > 120 for stroke in drawing):
        raise ValueError("This drawing is too detailed for AI revision (maximum 60 strokes, 120 points each).")
    points = [point for stroke in drawing for point in stroke]
    if not points:
        raise ValueError("Create a drawing before requesting a revision.")
    xs, ys = zip(*points)
    extent = max(max(xs)-min(xs), max(ys)-min(ys))
    if extent <= 0:
        raise ValueError("The drawing has no measurable extent.")
    return tuple(tuple((round((x-min(xs))/extent*1000, 3), round((y-min(ys))/extent*1000, 3))
                       for x, y in stroke) for stroke in drawing)
