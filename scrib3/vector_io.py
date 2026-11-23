"""Vector interchange. Readers return source coordinates with Y pointing down.

All imports are fitted to the selected paper, preserving aspect ratio. JSON
contains geometry only; machine commands and settings are never imported.
"""
from __future__ import annotations

import json
from math import isfinite, tau
from pathlib import Path

from .atomic_export import write_atomic_export
from .drawing import Drawing, MAX_POINTS, MAX_STROKES, Sheet, read_svg

MAX_FILE_BYTES = 10_000_000
FORMATS = [('Vector drawings', '*.svg *.dxf *.json'), ('SVG', '*.svg'),
           ('DXF', '*.dxf'), ('SCRIB3 drawing JSON', '*.json')]


def checked_drawing(strokes, *, max_strokes=MAX_STROKES) -> Drawing:
    result, total = [], 0
    for stroke in strokes:
        points = []
        for point in stroke:
            total += 1
            if total > MAX_POINTS:
                raise ValueError('Simplify the drawing to 100,000 points or fewer.')
            if (len(point) != 2 or any(type(v) not in (int, float) or
                    not isfinite(v) or abs(v) > 1e9 for v in point)):
                raise ValueError('Drawing points must be finite XY numbers within ±1e9.')
            xy = tuple(float(v) for v in point)
            if not points or xy != points[-1]:
                points.append(xy)
        if len(points) < 2:
            raise ValueError('Each stroke must contain at least two distinct points.')
        result.append(tuple(points))
        if len(result) > max_strokes:
            raise ValueError(f'Simplify the drawing to {max_strokes:,} strokes or fewer.')
    if not result:
        raise ValueError('This file contains no drawable strokes.')
    return tuple(result)


def read_drawing(path: Path) -> Drawing:
    extension = path.suffix.lower()
    if extension not in ('.svg', '.dxf', '.json'):
        raise ValueError('Choose an SVG, DXF, or SCRIB3 drawing JSON file.')
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('Choose a drawing file under 10 MB.')
    reader = {'.svg': read_svg, '.dxf': read_dxf, '.json': read_json}[extension]
    return checked_drawing(reader(path))


def read_json(path: Path) -> Drawing:
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_FILE_BYTES + 1)
        if len(raw) > MAX_FILE_BYTES:
            raise ValueError('Choose a drawing JSON file under 10 MB.')
        data = json.loads(raw.decode('utf-8-sig'))
        if (not isinstance(data, dict) or set(data) != {'format', 'version', 'units', 'strokes'}
                or data['format'] != 'scrib3-drawing' or type(data['version']) is not int
                or data['version'] != 1 or data['units'] not in ('mm', 'in', 'unitless')
                or not isinstance(data['strokes'], list) or len(data['strokes']) > MAX_STROKES):
            raise ValueError('Expected SCRIB3 drawing JSON version 1; see docs/vector-formats.md.')
        strokes = []
        total = 0
        for item in data['strokes']:
            if (not isinstance(item, dict) or set(item) != {'points', 'closed'} or
                    type(item['closed']) is not bool or not isinstance(item['points'], list)):
                raise ValueError('Each JSON stroke needs points and a true/false closed flag.')
            points = item['points']
            if any(not isinstance(p, list) for p in points):
                raise ValueError('JSON points must be [x, y] pairs.')
            total += len(points) + int(item['closed'])
            if total > MAX_POINTS:
                raise ValueError('Simplify the drawing to 100,000 points or fewer.')
            if item['closed'] and points and points[-1] != points[0]:
                points = points + [points[0]]
            strokes.append(points)
        drawing = checked_drawing(strokes)
        scale = 25.4 if data['units'] == 'in' else 1
        return checked_drawing(tuple(tuple((x*scale, y*scale) for x, y in stroke) for stroke in drawing))
    except (UnicodeError, json.JSONDecodeError, TypeError, RecursionError) as exc:
        raise ValueError('Cannot read this SCRIB3 drawing JSON file.') from exc


def read_dxf(path: Path) -> Drawing:
    import ezdxf
    from ezdxf.path import make_path

    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError('Choose a DXF under 10 MB.')
    try:
        doc = ezdxf.readfile(path)
        paths = []
        visited = 0
        control_count = 0
        supported = {'LINE', 'LWPOLYLINE', 'POLYLINE', 'CIRCLE', 'ARC', 'ELLIPSE', 'SPLINE'}

        def visible(entity, inherited_layer):
            layer_name = entity.dxf.get('layer', '0')
            if layer_name == '0':
                layer_name = inherited_layer
            layer = doc.layers.get(layer_name) if layer_name in doc.layers else None
            return (not entity.dxf.get('invisible', 0) and
                    not (layer and (layer.is_off() or layer.is_frozen()))), layer_name

        def skipped(entity, reason):
            raise ValueError(f'Cannot transform DXF {entity.dxftype()}: {reason}. Explode it in CAD first.')

        def collect(entities, ancestors=(), inherited_layer='0'):
            nonlocal visited, control_count
            for entity in entities:
                visited += 1
                if visited > 20_000:
                    raise ValueError('Simplify the DXF: too many entities or block copies.')
                shown, layer = visible(entity, inherited_layer)
                if not shown:
                    continue
                kind = entity.dxftype()
                if kind == 'INSERT':
                    name = entity.dxf.name
                    if len(ancestors) >= 16 or name in ancestors:
                        raise ValueError('Flatten recursive or deeply nested DXF blocks before importing.')
                    block = entity.block()
                    if block is None or block.block.is_xref:
                        raise ValueError('Resolve external or missing DXF blocks before importing.')
                    if entity.has_extension_dict or entity.attribs or any(e.dxftype() == 'ATTDEF' for e in block):
                        raise ValueError('Explode DXF blocks with clipping or text attributes to plain paths first.')
                    if entity.mcount > 20_000:
                        raise ValueError('Simplify the DXF block array before importing.')
                    inserts = entity.multi_insert() if entity.mcount > 1 else (entity,)
                    for insert in inserts:
                        collect(insert.virtual_entities(skipped_entity_callback=skipped), ancestors+(name,), layer)
                    continue
                if kind not in supported:
                    raise ValueError(f'Unsupported visible DXF entity: {kind}. Convert it to plain 2D paths in CAD first.')
                if kind == 'POLYLINE' and (entity.is_polygon_mesh or entity.is_poly_face_mesh):
                    raise ValueError('Export a 2D drawing instead of a DXF mesh.')
                curve = make_path(entity)
                if len(curve) == 0:
                    continue
                controls = list(curve.control_vertices())
                control_count += len(controls)
                if control_count > MAX_POINTS:
                    raise ValueError('Simplify the DXF to reduce curve control points.')
                if any(not isfinite(v) or abs(v) > 1e9 for p in controls for v in p):
                    raise ValueError('DXF contains invalid or excessively large coordinates.')
                if max(p.z for p in controls)-min(p.z for p in controls) > 1e-7:
                    raise ValueError('Export flat XY geometry; this DXF contains nonplanar or tilted paths.')
                # Respect entity topology; a tolerance-based endpoint check can
                # accidentally close an intentionally open curve at large offsets.
                closed = (kind == 'CIRCLE' or
                          kind == 'LWPOLYLINE' and entity.closed or
                          kind == 'POLYLINE' and entity.is_closed or
                          kind == 'SPLINE' and entity.closed or
                          kind == 'ELLIPSE' and abs(abs(entity.dxf.end_param-entity.dxf.start_param)-tau) < 1e-10)
                paths.append((curve, bool(closed), controls))
                if len(paths) > MAX_STROKES:
                    raise ValueError('Simplify the DXF to 2,000 strokes or fewer.')

        collect(doc.modelspace())
        if not paths:
            raise ValueError('No supported paths in DXF model space.')
        xs = [p.x for _, _, points in paths for p in points]
        ys = [p.y for _, _, points in paths for p in points]
        extent = max(max(xs)-min(xs), max(ys)-min(ys))
        tolerance = max(extent/10_000, 1e-9)
        strokes, total = [], 0
        for curve, closed, _ in paths:
            points = []
            for p in curve.flattening(tolerance, segments=8):
                total += 1
                if total > MAX_POINTS:
                    raise ValueError('Simplify the DXF to reduce the number of plotting points.')
                points.append((p.x, -p.y))
            if closed and len(points) > 1:
                points[-1] = points[0]
            strokes.append(tuple(points))
        return checked_drawing(strokes)
    except (ezdxf.DXFError, UnicodeError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError('Cannot read DXF geometry. Re-export as a plain 2D DXF.') from exc


def write_drawing(path: Path, drawing: Drawing, sheet: Sheet) -> None:
    """Render into a sibling staging folder before replacing the destination."""
    drawing = checked_drawing(drawing)
    extension = path.suffix.lower()
    if extension not in ('.svg', '.json', '.dxf'):
        raise ValueError('Use a .svg, .dxf, or .json extension.')
    write_atomic_export(path, lambda staged: _write_drawing_file(staged, extension, drawing, sheet))


def _write_drawing_file(path, extension, drawing, sheet):
    if extension == '.svg':
        from .design import svg_document
        path.write_text(svg_document(drawing, sheet), encoding='utf-8')
    elif extension == '.json':
        data = {'format': 'scrib3-drawing', 'version': 1, 'units': 'mm', 'strokes': [
            {'closed': stroke[0] == stroke[-1],
             'points': [[x, sheet.height-y] for x, y in (stroke[:-1] if stroke[0] == stroke[-1] else stroke)]}
            for stroke in drawing]}
        path.write_text(json.dumps(data, separators=(',', ':'), allow_nan=False)+'\n', encoding='utf-8')
    else:
        import ezdxf
        doc = ezdxf.new('R2010')
        doc.units = ezdxf.units.MM
        model = doc.modelspace()
        for stroke in drawing:
            closed = stroke[0] == stroke[-1]
            model.add_lwpolyline(stroke[:-1] if closed else stroke, close=closed)
        doc.saveas(path)
