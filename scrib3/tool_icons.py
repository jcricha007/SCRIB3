"""Small outline glyphs for the drawing board's labeled tool buttons."""

from PIL import Image, ImageDraw, ImageTk

from .theme import INK


# Coordinates are on a 20-unit design grid. Each tuple is one pen stroke.
STROKES = {
    "Select": [((4, 2), (16, 10), (10, 11), (7, 17), (4, 2))],
    "Pan": [((3, 10), (17, 10)), ((10, 3), (10, 17)),
            ((6, 7), (3, 10), (6, 13)), ((14, 7), (17, 10), (14, 13)),
            ((7, 6), (10, 3), (13, 6)), ((7, 14), (10, 17), (13, 14))],
    "Freehand": [((2, 14), (5, 14), (7, 10), (9, 5), (11, 4), (12, 6), (11, 12), (12, 14), (15, 9), (18, 9))],
    "Bezier": [((3, 15), (5, 10), (8, 7), (12, 6), (17, 6)), ((4, 5), (16, 5))],
    "Edit nodes": [((3, 14), (9, 6), (17, 10)), ((7, 4), (11, 4), (11, 8), (7, 8), (7, 4))],
    "Line": [((3, 16), (17, 3))],
    "Rectangle": [((3, 5), (17, 5), (17, 15), (3, 15), (3, 5))],
    "Star": [((10, 2), (12, 7), (18, 8), (14, 12), (15, 18), (10, 15),
              (5, 18), (6, 12), (2, 8), (8, 7), (10, 2))],
    "Pentagon": [((10, 2), (18, 8), (15, 17), (5, 17), (2, 8), (10, 2))],
    "Eraser": [((3, 12), (12, 3), (17, 8), (9, 16), (7, 16), (3, 12)),
               ((7, 8), (12, 13)), ((8, 16), (18, 16))],
}


def tool_icon(master, tool):
    # Oversample thin oblique strokes, then size them to the display's Tk scale.
    image = Image.new("RGBA", (80, 80))
    draw = ImageDraw.Draw(image)
    if tool == "Ellipse":
        draw.ellipse((11, 20, 69, 60), outline=INK, width=6)
    else:
        for stroke in STROKES[tool]:
            draw.line([(4*x, 4*y) for x, y in stroke], fill=INK, width=6, joint="curve")
    pixels = max(12, master.winfo_pixels("13p"))
    return ImageTk.PhotoImage(image.resize((pixels, pixels), Image.Resampling.LANCZOS), master=master)
