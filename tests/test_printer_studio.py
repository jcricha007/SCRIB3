from dataclasses import replace
from hashlib import md5
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from scrib3.board import Board, Mark, save_board, load_board, export_svg
from scrib3.printer_output import Holder, plan_printer
from scrib3.svg_artwork import import_svg
from scrib3.geometry import hatch, shape

PURPLE = "#522d80"
ORANGE = "#f56600"
ART = Board(
    100,
    80,
    (Mark(PURPLE, ((0, 0), (100, 80))), Mark(ORANGE, ((30, 10), (70, 60)))),
    pen_order=(ORANGE, PURPLE),
)


class PrinterTests(unittest.TestCase):
    def test_large_board_quality_review_retains_points_and_pen_order_validation(self):
        from scrib3.board import MAX_PATHS, MAX_POINTS
        from scrib3.toolpath import QualityOptions, prepare_toolpath

        paths = (tuple((i / 1000, 10.0) for i in range(100001)),)
        with self.assertRaisesRegex(ValueError, "100,000"):
            prepare_toolpath(paths, QualityOptions("Original", False, False, False, False))
        result, _ = prepare_toolpath(
            paths, QualityOptions("Original", False, False, False, False),
            max_strokes=MAX_PATHS, max_points=MAX_POINTS,
        )
        self.assertEqual(result, paths)
        with self.assertRaisesRegex(ValueError, "pen order"):
            replace(ART, pen_order=(ORANGE, ORANGE)).checked()

    def holder(self, name):
        return Holder(name, 10, -15, 1.25, 5, 5, 30, 5, 5)

    def test_registered_coordinates_lift_pause_and_native_plate_metadata(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "boat.scrib3"
            save_board(p, ART)
            self.assertEqual(load_board(p), ART)
            for printer, identifier in [("P1S", "C12"), ("H2S", "O1S")]:
                h = self.holder(printer)
                plan = plan_printer(ART, h, dry=False, optimize=False)
                a, b, c, d = h.reach()
                left = (a + c - ART.width) / 2
                front = (b + d - ART.height) / 2
                for (color, paths), idx in zip(plan.passes, [1, 0]):
                    self.assertEqual(color, ART.marks[idx].color)
                    for (nx, ny), (x, y) in zip(paths[0], ART.marks[idx].points):
                        self.assertAlmostEqual(nx + h.offset_x, left + x, 3)
                        self.assertAlmostEqual(ny + h.offset_y, front + ART.height - y, 3)
                f = Path(tmp) / (printer + ".gcode.3mf")
                plan.export(f)
                with ZipFile(f) as z:
                    self.assertIsNone(z.testzip())
                    g = z.read("Metadata/plate_1.gcode")
                    self.assertEqual(
                        z.read("Metadata/plate_1.gcode.md5").decode(), md5(g).hexdigest().upper()
                    )
                    self.assertEqual(
                        ET.fromstring(z.read("Metadata/slice_info.config"))
                        .find(".//metadata[@key='printer_model_id']")
                        .get("value"),
                        identifier,
                    )
                    self.assertEqual(g.count(b"M400 U1"), 2)
                    hold = b"G4 P10000" if printer == "P1S" else b"G4 P5000"
                    self.assertEqual(g.count(hold), 2 if printer == "P1S" else 1)
                    self.assertLess(g.index(hold), g.index(b"G1 Z1.250"))
                    self.assertIn(b"G1 Z5.000", g[g.rindex(b"G1 X") :])
                    for l in g.splitlines():
                        if not l.startswith(b";"):
                            self.assertNotIn(b" E", l)
                dry = plan_printer(replace(ART, hidden=frozenset([PURPLE])), h)
                self.assertEqual(tuple(c for c, _ in dry.passes), (ORANGE,))
                self.assertNotIn("G1 Z1.250", dry.gcode())

    def test_fit_invalid_calibration_and_rounding(self):
        h = self.holder("P1S")
        with self.assertRaisesRegex(ValueError, "Paper exceeds"):
            plan_printer(replace(ART, width=297), h)
        self.assertLess(plan_printer(replace(ART, width=297), h, fit=True).scale, 1)
        for bad in [
            replace(h, offset_x=float("nan")),
            replace(h, front=5),
            replace(h, contact_z=5),
            replace(h, contact_z=-0.0001),
            replace(h, lift_z=200.0001),
            replace(h, back=1000),
        ]:
            with self.assertRaises(ValueError):
                plan_printer(ART, bad)
        tiny = Board(marks=(Mark(PURPLE, ((10, 10), (10.00001, 10))),))
        with self.assertRaisesRegex(ValueError, "disappears"):
            plan_printer(tiny, self.holder("H2S"))

    def test_svg_physical_registration_colors_and_legacy_board(self):
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "art.svg"
            export_svg(p, ART)
            got = import_svg(p)
            for m in got:
                original = next(x for x in ART.marks if x.color == m.color)
                for actual, want in zip(m.points, original.points):
                    for v, w in zip(actual, want):
                        self.assertAlmostEqual(v, w, 6)
            q = Path(tmp) / "legacy.scrib3"
            save_board(q, ART)
            import json

            d = json.loads(q.read_text())
            del d["pen_order"]
            q.write_text(json.dumps(d))
            self.assertEqual(len(load_board(q).marks), 2)

    def test_svg_occlusion_clipping_invisible_guides_and_holes(self):
        source = """<svg xmlns="http://www.w3.org/2000/svg" width="40mm" height="40mm" viewBox="0 0 40 40"><defs><clipPath id="c"><rect x="10" y="10" width="10" height="10"/></clipPath></defs><path stroke="purple" fill="none" d="M0,15 L40,15"/><rect x="10" y="10" width="10" height="10" fill="orange"/><path d="M0,0 L40,40" fill="none" stroke="red" clip-path="url(#c)"/><path d="M0,0 L40,0" stroke="none" fill="none"/></svg>"""
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "clip.svg"
            p.write_text(source)
            marks = import_svg(p)
            red = [m for m in marks if m.color == "#ff0000"]
            self.assertEqual(len(red), 1)
            self.assertAlmostEqual(red[0].points[0][0], 10, 5)
            self.assertAlmostEqual(red[0].points[-1][0], 20, 5)
            purple = [m for m in marks if m.color == "#800080"]
            self.assertEqual(len(purple), 2)
            self.assertFalse(any(m.color == "#000000" for m in marks))
        contours = [
            Mark(PURPLE, shape("Rectangle", (0, 0), (20, 20))),
            Mark(PURPLE, shape("Rectangle", (5, 5), (15, 15))),
        ]
        for mode in ("Horizontal", "Concentric"):
            for m in hatch(contours, 1, mode):
                for x, y in m.points:
                    self.assertFalse(5 < x < 15 and 5 < y < 15)

    def test_creator_imports_and_all_bundled_fonts(self):
        import trimesh
        from PIL import Image
        from scrib3.creator import photo_paths, mesh_paths, qr_paths
        from scrib3.lettering import FONTS, lettering

        self.assertGreaterEqual(len(FONTS), 12)
        for font in FONTS:
            self.assertTrue(lettering("Club 420", font))
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "photo.png"
            Image.new("RGB", (50, 40), "#666666").save(p)
            for mode in ("Engraving", "Squiggle", "Stipple", "Lines"):
                self.assertTrue(photo_paths(p, mode, 30, 2))
            m = Path(tmp) / "box.stl"
            trimesh.creation.box().export(m)
            self.assertTrue(mesh_paths(m))
            visible = mesh_paths(m, style="Visible edges")
            feature = mesh_paths(m, style="Feature edges")
            # A generic orthographic cube has nine visible edges, twelve total.
            self.assertEqual((len(visible), len(feature)), (9, 12))
            self.assertTrue(qr_paths("SCRIB3", 25))

    def test_svg_nested_group_clips_and_opacity(self):
        source = """<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">
        <defs><clipPath id="clip"><rect width="10" height="10"/></clipPath>
        <clipPath id="relative" clipPathUnits="objectBoundingBox"><rect width="0.5" height="1"/></clipPath></defs>
        <g transform="translate(20)" clip-path="url(#clip)"><path transform="translate(5)" d="M0,5L30,5" stroke="red" fill="none"/></g>
        <path d="M0,15L50,15" stroke="purple" fill="none"/>
        <g opacity="0.5"><rect x="10" y="10" width="20" height="10" fill="orange" opacity="1"/></g>
        <g transform="translate(40,40)" clip-path="url(#relative)"><rect transform="translate(5)" width="20" height="20" stroke="blue" fill="none"/></g>
        <g opacity="0"><path opacity="1" d="M0,80L80,80" stroke="black"/></g>
        </svg>"""
        with TemporaryDirectory() as tmp:
            p = Path(tmp) / "group.svg"
            p.write_text(source)
            marks = import_svg(p)
            red = [m for m in marks if m.color == "#ff0000"]
            self.assertEqual(len(red), 1)
            self.assertAlmostEqual(red[0].points[0][0], 25)
            self.assertAlmostEqual(red[0].points[-1][0], 30)
            purple = [m for m in marks if m.color == "#800080"]
            self.assertEqual(len(purple), 1)
            self.assertAlmostEqual(purple[0].points[-1][0], 50)
            blue = [p for m in marks if m.color == "#0000ff" for p in m.points]
            self.assertAlmostEqual(min(x for x, _ in blue), 45)
            self.assertAlmostEqual(max(x for x, _ in blue), 55)
            self.assertFalse(any(m.color == "#000000" for m in marks))
