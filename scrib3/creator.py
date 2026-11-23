"""Image tone, QR, map and mesh tools that produce editable pen paths."""

from math import sin, cos, tau, ceil, isfinite
import json
import numpy as np
from .board import Mark, DEFAULT_PEN, MAX_PATHS
from .geometry import check_size, line_marks


def photo_paths(path, style, width=180, spacing=1, threshold=128):
    from .raster import load_raster
    from PIL import Image

    if style not in ("Engraving", "Squiggle", "Stipple", "Lines"):
        raise ValueError("Choose a listed photo style.")
    if not all(isfinite(v) for v in (width, spacing, threshold)) or not (
        1 <= width <= 2000 and 0.2 <= spacing <= 20 and 0 <= threshold <= 255
    ):
        raise ValueError("Use width 1–2000 mm, spacing 0.2–20 mm and threshold 0–255.")
    rgba = load_raster(path)
    white = Image.new("RGBA", rgba.size, "white")
    white.alpha_composite(rgba)
    image = white.convert("L")
    image.thumbnail((1200, 1200))
    data = np.asarray(image, dtype=float) / 255
    height = width * image.height / image.width
    rows = ceil(height / spacing)
    cols = ceil(width / spacing)
    if not 0.2 <= spacing <= 20 or rows * cols > 200000:
        raise ValueError("Increase photo spacing or reduce output size.")
    marks = []
    for row in range(rows):
        y = (row + 0.5) * spacing
        samples = np.linspace(0, width, max(2, cols * 3))
        pixels = np.clip((samples / width * (image.width - 1)).astype(int), 0, image.width - 1)
        darkness = 1 - data[min(image.height - 1, int(y / height * (image.height - 1))), pixels]
        if style == "Stipple":
            for i, x in enumerate(samples[::3]):
                tone = darkness[i * 3]
                if tone > 0.1:
                    r = spacing * 0.4 * tone
                    pts = tuple(
                        (x + r * cos(tau * j / 10), y + r * sin(tau * j / 10)) for j in range(11)
                    )
                    marks.append(Mark(DEFAULT_PEN, pts))
        elif style == "Squiggle":
            pts = tuple(
                (float(x), float(y + spacing * 0.4 * t * sin(i * tau / 3)))
                for i, (x, t) in enumerate(zip(samples, darkness))
            )
            marks.append(Mark(DEFAULT_PEN, pts))
        else:
            # Tone is represented by segments of each scanline, leaving highlights blank.
            segment = []
            level = (row % 4 + 0.5) / 4 if style == "Engraving" else 1 - threshold / 255
            for x, t in zip(samples, darkness):
                if t >= level:
                    segment.append((float(x), float(y)))
                else:
                    if len(segment) > 1:
                        marks.append(Mark(DEFAULT_PEN, (segment[0], segment[-1])))
                    segment = []
            if len(segment) > 1:
                marks.append(Mark(DEFAULT_PEN, (segment[0], segment[-1])))
        check_size(marks)
    if not marks:
        raise ValueError("Photo settings produced no paths.")
    return tuple(marks)


def mesh_paths(path, yaw=35, pitch=25, style="Feature edges"):
    import trimesh

    if not all(isfinite(v) for v in (yaw, pitch)) or style not in (
        "Feature edges",
        "Visible edges",
        "Wireframe",
    ):
        raise ValueError("Choose finite view angles and a listed edge style.")
    if path.stat().st_size > 50_000_000:
        raise ValueError("Model exceeds 50 MB.")
    mesh = trimesh.load(str(path), force="mesh", process=True)
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) > 60000 or len(mesh.faces) == 0:
        raise ValueError("Choose a triangulated model with 1 to 60,000 faces.")
    from scipy.spatial.transform import Rotation

    xyz = Rotation.from_euler("yx", [yaw, pitch], degrees=True).apply(
        np.array(mesh.vertices, copy=True)
    )
    normals = Rotation.from_euler("yx", [yaw, pitch], degrees=True).apply(
        np.array(mesh.face_normals, copy=True)
    )
    edges = mesh.edges_unique
    if style in ("Feature edges", "Visible edges"):
        sharp = mesh.face_adjacency_edges[mesh.face_adjacency_angles > np.deg2rad(15)]
        silhouettes = mesh.face_adjacency_edges[
            np.sign(normals[mesh.face_adjacency[:, 0], 2])
            != np.sign(normals[mesh.face_adjacency[:, 1], 2])
        ]
        boundary = mesh.edges_unique[
            np.bincount(mesh.edges_unique_inverse, minlength=len(mesh.edges_unique)) == 1
        ]
        edges = np.unique(np.sort(np.concatenate([sharp, silhouettes, boundary]), axis=1), axis=0)
    if style == "Visible edges":
        return visible_edges(xyz, mesh.faces, edges)
    marks = tuple(
        Mark(DEFAULT_PEN, tuple((float(xyz[i, 0]), float(-xyz[i, 1])) for i in edge))
        for edge in edges
        if np.linalg.norm(xyz[edge[0], :2] - xyz[edge[1], :2]) > 1e-7
    )
    check_size(marks)
    if not marks:
        raise ValueError("This view contains no edges.")
    return marks


def qr_paths(text, size=50):
    import qrcode

    if not isfinite(size) or not 5 <= size <= 1000 or not 1 <= len(text) <= 1024:
        raise ValueError("Use a 5–1000 mm QR code and 1–1024 text characters.")
    qr = qrcode.QRCode(border=4)
    qr.add_data(text)
    try:
        qr.make(fit=True)
    except qrcode.exceptions.DataOverflowError as exc:
        raise ValueError("Shorten the text to fit a QR code.") from exc
    grid = qr.get_matrix()
    step = size / len(grid)
    marks = []
    for row, cells in enumerate(grid):
        for col, on in enumerate(cells):
            if on:
                # Dense strokes form each dark module. Four-module quiet zone stays blank.
                n = max(2, ceil(step / 0.25))
                for i in range(n):
                    y = (row + (i + 0.5) / n) * step
                    marks.append(Mark(DEFAULT_PEN, ((col * step, y), ((col + 1) * step, y))))
    check_size(marks)
    return tuple(marks)


def map_paths(path):
    from shapely.geometry import shape
    from shapely import force_2d

    if path.stat().st_size > 10_000_000:
        raise ValueError("Map exceeds 10 MB.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(data, dict)
        or data.get("type") != "FeatureCollection"
        or not isinstance(data.get("features"), list)
    ):
        raise ValueError("Import a GeoJSON FeatureCollection.")
    colors = {"water": "#247baa", "building": "#8b5e3c", "road": "#242c39"}
    marks = []
    for f in data["features"]:
        if not isinstance(f, dict):
            raise ValueError("Invalid GeoJSON feature.")
        if f.get("geometry") is None:
            continue
        try:
            g = force_2d(shape(f["geometry"]))
        except (KeyError, TypeError, AttributeError) as exc:
            raise ValueError("Invalid GeoJSON geometry.") from exc
        props = f.get("properties") or {}
        color = colors[
            (
                "water"
                if props.get("water") or props.get("natural") == "water"
                else "building" if props.get("building") else "road"
            )
        ]
        if g.geom_type in ("Polygon", "MultiPolygon"):
            g = g.boundary
        marks.extend(line_marks(g, color))
        check_size(marks)
    if not marks:
        raise ValueError("Map contains no line or polygon features.")
    coords = [p for m in marks for p in m.points]
    if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x, y in coords):
        raise ValueError("GeoJSON must use WGS84 longitude and latitude.")
    x0 = sum(x for x, _ in coords) / len(coords)
    y0 = sum(y for _, y in coords) / len(coords)
    # Local equirectangular projection keeps city-scale geographic proportions.
    k = cos(y0 * tau / 360)
    return tuple(Mark(m.color, tuple(((x - x0) * k, y0 - y) for x, y in m.points)) for m in marks)


def pattern_paths(kind, detail=50, seed=1):
    from .design import pattern

    if kind in ("Grid", "Spiral", "Rosette"):
        return tuple(Mark(DEFAULT_PEN, s) for s in pattern(kind, detail))
    if not 5 <= detail <= 150:
        raise ValueError("Detail must be 5 to 150.")
    rng = np.random.default_rng(seed)
    marks = []
    if kind == "Guilloche":
        for i in range(max(2, detail // 5)):
            r = 50 + i * 0.5
            pts = tuple(
                ((r + 8 * cos(7 * t)) * cos(t), (r + 8 * cos(7 * t)) * sin(t))
                for t in np.linspace(0, tau, 1200)
            )
            marks.append(Mark(DEFAULT_PEN, pts))
    elif kind == "Flow field":
        phases = rng.uniform(-tau, tau, 3)
        for row in range(detail):
            x, y = 0.0, row * 100 / detail
            pts = []
            for _ in range(450):
                if not (0 <= x <= 150 and 0 <= y <= 100):
                    break
                pts.append((float(x), float(y)))
                a = 0.7 * sin(x / 25 + phases[0]) + 0.6 * cos(y / 20 + phases[1])
                x += 0.5 * cos(a)
                y += 0.5 * sin(a)
            if len(pts) > 1:
                marks.append(Mark(DEFAULT_PEN, tuple(pts)))
    elif kind == "Terrain":
        for row in range(detail):
            pts = tuple(
                (
                    float(x),
                    float(
                        row * 100 / detail
                        + 4 * sin(x / 16 + row * 0.15)
                        + 2 * sin(x / 7 - row * 0.2)
                    ),
                )
                for x in np.linspace(0, 150, 500)
            )
            marks.append(Mark(DEFAULT_PEN, pts))
    else:
        raise ValueError("Choose a listed pattern.")
    check_size(marks)
    return tuple(marks)


def visible_edges(vertices, faces, edges):
    """Remove occluded edge intervals with an orthographic triangle depth test."""
    from shapely import STRtree
    from shapely.geometry import Polygon, LineString

    triangles = []
    planes = []
    for face in faces:
        tri = vertices[face]
        normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
        if abs(normal[2]) < 1e-10:
            continue
        polygon = Polygon(tri[:, :2])
        if polygon.area < 1e-10:
            continue
        triangles.append(polygon)
        planes.append(
            (-normal[0] / normal[2], -normal[1] / normal[2], np.dot(normal, tri[0]) / normal[2])
        )
    tree = STRtree(triangles)
    result = []
    extent = max(np.ptp(vertices, axis=0))
    epsilon = max(1e-8, extent * 1e-7)
    for a, b in edges:
        start, end = vertices[a], vertices[b]
        line = LineString([start[:2], end[:2]])
        if line.length < epsilon:
            continue
        cuts = []
        for idx in tree.query(line, predicate="intersects"):
            part = line.intersection(triangles[int(idx)])
            if part.geom_type != "LineString" or part.length < epsilon:
                continue
            t0 = line.project(__import__("shapely").Point(part.coords[0])) / line.length
            t1 = line.project(__import__("shapely").Point(part.coords[-1])) / line.length
            t0, t1 = sorted((t0, t1))
            px, py, pz = planes[int(idx)]

            def depth(t):
                xyz = start + (end - start) * t
                return px * xyz[0] + py * xyz[1] + pz - xyz[2] - epsilon

            d0, d1 = depth(t0), depth(t1)
            if max(d0, d1) <= 0:
                continue
            if d0 * d1 < 0:
                crossing = t0 + (t1 - t0) * (-d0) / (d1 - d0)
                if d0 > 0:
                    t1 = crossing
                else:
                    t0 = crossing
            cuts.append((t0, t1))
        # Subtract parameter intervals. Floating point line differences can fail
        # when interpolated cut endpoints miss exact collinearity by a few ulps.
        cursor = 0.0
        gaps = []
        tolerance = epsilon * 10 / line.length
        for lo, hi in sorted(cuts):
            if lo - cursor > tolerance:
                gaps.append((cursor, lo))
            cursor = max(cursor, hi)
        if 1 - cursor > tolerance:
            gaps.append((cursor, 1.0))
        for lo, hi in gaps:
            points = [start + (end - start) * t for t in (lo, hi)]
            result.append(Mark(DEFAULT_PEN, tuple((float(p[0]), float(p[1])) for p in points)))
        check_size(result)
    return tuple(Mark(m.color, tuple((x, -y) for x, y in m.points)) for m in result)
