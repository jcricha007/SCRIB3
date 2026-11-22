"""Reviewed raster-to-pen-path conversion using Pillow and scikit-image."""
from dataclasses import dataclass
from pathlib import Path

from .drawing import MAX_POINTS, MAX_STROKES
from .vector_io import checked_drawing

MAX_IMAGE_PIXELS = 25_000_000
MAX_TRACE_NODES = 200_000

RASTER_FORMATS = {
    '.png': 'PNG', '.psd': 'PSD', '.jpg': 'JPEG', '.jpeg': 'JPEG',
    '.bmp': 'BMP', '.webp': 'WEBP', '.tif': 'TIFF', '.tiff': 'TIFF',
}


class ImportCancelled(ValueError):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise ImportCancelled('Import cancelled.')


@dataclass(frozen=True)
class TraceOptions:
    mode: str = 'Centerline'
    threshold: int = 128
    invert: bool = False
    resolution: int = 1024
    despeckle: int = 0

    def __post_init__(self):
        if self.mode not in ('Centerline', 'Outline'):
            raise ValueError('Choose Centerline or Outline tracing.')
        if type(self.threshold) is not int or not 1 <= self.threshold <= 254:
            raise ValueError('Threshold must be a whole number from 1 to 254.')
        if type(self.resolution) is not int or not 128 <= self.resolution <= 2048:
            raise ValueError('Trace resolution must be between 128 and 2048 pixels.')
        if type(self.despeckle) is not int or not 0 <= self.despeckle <= 100:
            raise ValueError('Speck removal must be between 0 and 100 pixels.')
        if type(self.invert) is not bool:
            raise ValueError('Invert must be true or false.')


def load_raster(path):
    from PIL import Image, ImageOps, UnidentifiedImageError
    path = Path(path)
    expected = RASTER_FORMATS.get(path.suffix.lower())
    if expected is None:
        raise ValueError('Choose a supported raster artwork extension.')
    try:
        # Restrict format probing to the intended raster decoder. Renamed files
        # must not silently take a different import route.
        with Image.open(path, formats=(expected,)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError('Resize the image to 25 million pixels or fewer before importing.')
            if expected in ('TIFF', 'WEBP') and getattr(image, 'is_animated', False):
                raise ValueError('Choose a single-page TIFF or a static WebP; export the desired page or frame as PNG.')
            # Image.open() starts at the PSD merged composite. PSD seek() selects
            # individual layers and some documents have no seekable layer zero.
            return ImageOps.exif_transpose(image).convert('RGBA')
    except (UnidentifiedImageError, OSError, EOFError, Image.DecompressionBombError) as exc:
        detail = (' For PSD, save an 8-bit RGB/gray file with Maximize Compatibility enabled, or export PNG.'
                  if expected == 'PSD' else ' Check the file extension or export a fresh PNG.')
        raise ValueError(f'Cannot decode this image as {expected}.' + detail) from exc


def _skeleton_paths(mask, cancel):
    import numpy as np
    ids = np.flatnonzero(mask)
    if len(ids) > MAX_TRACE_NODES:
        raise ValueError('Trace is too complex. Lower resolution or increase speck removal.')
    height, width = mask.shape
    graph = {}
    for number, raw in enumerate(ids):
        if number % 1024 == 0:
            check_cancel(cancel)
        point = int(raw)
        y, x = divmod(point, width)
        neighbors = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if not (dx or dy) or not (0 <= x + dx < width and 0 <= y + dy < height):
                    continue
                if not mask[y + dy, x + dx]:
                    continue
                # Do not add diagonal shortcuts across a connected right angle.
                if dx and dy and (mask[y, x + dx] or mask[y + dy, x]):
                    continue
                neighbors.append((y + dy) * width + x + dx)
        graph[point] = neighbors
    visited = set()

    def edge(a, b):
        return min(a, b), max(a, b)

    def walk(first, second):
        path = [first, second]
        visited.add(edge(first, second))
        previous, current = first, second
        while len(graph[current]) == 2:
            a, b = graph[current]
            following = b if a == previous else a
            key = edge(current, following)
            if key in visited:
                break
            visited.add(key)
            path.append(following)
            previous, current = current, following
        return tuple((p % width + .5, p // width + .5) for p in path)

    # Branches and endpoints first; remaining edges are closed cycles.
    for branches in (True, False):
        for i, (point, neighbors) in enumerate(graph.items()):
            if i % 1024 == 0:
                check_cancel(cancel)
            if (len(neighbors) != 2) != branches:
                continue
            if not neighbors:
                x, y = point % width, point // width
                # Keep isolated ink dots as a short, visible pen mark.
                yield ((x + .25, y + .5), (x + .75, y + .5))
            for neighbor in neighbors:
                if edge(point, neighbor) not in visited:
                    yield walk(point, neighbor)


def trace_image(image, options=TraceOptions(), cancel=None):
    import numpy as np
    from PIL import Image, ImageOps
    from scipy.ndimage import label
    from skimage.measure import approximate_polygon, find_contours
    from skimage.morphology import skeletonize

    check_cancel(cancel)
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise ValueError('Resize the image to 25 million pixels or fewer before importing.')
    rgba = image.convert('RGBA')
    rgba.thumbnail((options.resolution, options.resolution), Image.Resampling.LANCZOS)
    background = (0, 0, 0, 255) if options.invert else (255, 255, 255, 255)
    preview = Image.alpha_composite(Image.new('RGBA', rgba.size, background), rgba).convert('RGB')
    gray = ImageOps.grayscale(preview)
    if options.invert:
        gray = ImageOps.invert(gray)
    mask = np.asarray(gray) < options.threshold
    check_cancel(cancel)
    if options.despeckle:
        components, _ = label(mask, structure=np.ones((3, 3)))
        counts = np.bincount(components.ravel())
        keep = counts > options.despeckle
        keep[0] = False
        mask = keep[components]
    if not mask.any():
        raise ValueError('No ink found. Adjust threshold, inversion, or speck removal.')
    if options.mode == 'Centerline':
        paths = _skeleton_paths(skeletonize(mask), cancel)
    else:
        contours = find_contours(np.pad(mask, 1), .5, fully_connected='high')
        paths = (tuple((float(x) - .5, float(y) - .5) for y, x in contour) for contour in contours)
    result, total = [], 0
    for stroke in paths:
        check_cancel(cancel)
        if len(stroke) < 2:
            continue
        simplified = tuple(tuple(float(v) for v in p) for p in approximate_polygon(np.asarray(stroke), .35))
        if stroke[0] == stroke[-1] and len(set(simplified)) < 3:
            simplified = stroke
        total += len(simplified)
        result.append(simplified)
        if len(result) > MAX_STROKES or total > MAX_POINTS:
            raise ValueError('Trace exceeds the plotter drawing limit. Lower resolution or increase speck removal.')
    return checked_drawing(result), preview
