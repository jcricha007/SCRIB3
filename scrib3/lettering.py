"""Single-stroke Hershey lettering. No browser, system fonts or filled outlines."""
from functools import lru_cache
import json
from math import isfinite
from pathlib import Path

from svgelements import Line, Move, Path as SvgPath

from .drawing import MAX_POINTS, MAX_STROKES
from .vector_io import checked_drawing

FONTS = {'Technical sans': 'futural', 'Script': 'scripts'}
ALIGNMENTS = ('Left', 'Center', 'Right')


@lru_cache(maxsize=1)
def font_data():
    return json.loads(Path(__file__).with_name('fonts').joinpath('hershey.json').read_text(encoding='utf-8'))['fonts']


def lettering(text, font='Technical sans', alignment='Left', tracking=0.0, line_spacing=1.5):
    """Return Y-down polylines; a capital is 21 source units high.

    Only printable ASCII and newline are accepted. Reject missing glyphs rather
    than silently removing symbols from an engineering label.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 300:
        raise ValueError('Enter 1 to 300 characters of lettering.')
    text = text.replace('\r\n', '\n')
    missing = sorted(set(c for c in text if c != '\n' and not 32 <= ord(c) <= 126))
    if missing:
        raise ValueError('Unsupported characters: ' + ', '.join(repr(c) for c in missing) + '. Use printable ASCII.')
    if font not in FONTS or alignment not in ALIGNMENTS:
        raise ValueError('Choose a listed font and alignment.')
    if not isfinite(tracking) or not 0 <= tracking <= 20 or not isfinite(line_spacing) or not 1 <= line_spacing <= 4:
        raise ValueError('Tracking must be 0 to 20; line spacing must be 1 to 4.')
    glyphs = font_data()[FONTS[font]]['chars']
    result = []
    count = 0
    for row, line in enumerate(text.split('\n')):
        advance = lambda c: 10 if c == ' ' else 2 * glyphs[ord(c)-33]['o']
        width = sum(advance(c) for c in line) + tracking * max(0, len(line)-1)
        x = {'Left': 0, 'Center': -width/2, 'Right': -width}[alignment]
        for char in line:
            if char != ' ':
                stroke = []
                for segment in SvgPath(glyphs[ord(char)-33]['d']):
                    if isinstance(segment, Move):
                        if len(stroke) > 1:
                            result.append(tuple(stroke))
                        stroke = []
                    elif isinstance(segment, Line):
                        if not stroke:
                            stroke.append((segment.start.x+x, segment.start.y+row*21*line_spacing))
                        stroke.append((segment.end.x+x, segment.end.y+row*21*line_spacing))
                        count += 2
                    else:
                        raise ValueError('Unsupported bundled glyph geometry.')
                if len(stroke) > 1:
                    result.append(tuple(stroke))
                if len(result) > MAX_STROKES or count > MAX_POINTS:
                    raise ValueError('Shorten this text to stay within the drawing limits.')
            x += advance(char) + tracking
    return checked_drawing(result)


def add_caption(source, letters, height_percent=4.0):
    """Place lettering below existing art; the combined drawing is fitted later."""
    source, letters = checked_drawing(source), checked_drawing(letters)
    if not isfinite(height_percent) or not .5 <= height_percent <= 20:
        raise ValueError('Caption height must be 0.5 to 20 percent of the artwork extent.')
    xs, ys = zip(*(p for s in source for p in s))
    extent = max(max(xs)-min(xs), max(ys)-min(ys))
    height = extent*height_percent/100
    scale = height/21
    lx, ly = zip(*(p for s in letters for p in s))
    left = (min(xs)+max(xs))/2 - (min(lx)+max(lx))*scale/2
    top = max(ys) + height - min(ly)*scale
    caption = tuple(tuple((left+x*scale, top+y*scale) for x, y in s) for s in letters)
    return checked_drawing(source + caption)
