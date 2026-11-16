from math import dist
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from svgelements import Path as SvgPath, CubicBezier, QuadraticBezier
from scrib3.curves import flatten_segment, segment_distance
from scrib3.drawing import read_svg


class CurveTests(TestCase):
    def test_dense_reference_stays_within_tolerance_for_cusps_s_curves_and_arcs(self):
        curves = [
            CubicBezier((0, 0), (0, 100), (100, -100), (100, 0)),
            CubicBezier((0, 0), (90, 90), (-90, 90), (0, 0)),
            CubicBezier((0, 0), (100, 0), (-100, 0), (1, 0)),
            QuadraticBezier((0, 0), (1, 100), (2, 0)),
            SvgPath('M10 0 A10 1 0 0 1 -10 0')[1],
        ]
        for curve in curves:
            with self.subTest(curve=type(curve).__name__):
                start = (float(curve.start.x), float(curve.start.y))
                points = [start] + flatten_segment(curve, .01, 10000)
                self.assertEqual(points[-1], (curve.end.x, curve.end.y))
                for i in range(1001):
                    p = curve.point(i/1000)
                    error = min(segment_distance((p.x, p.y), a, b) for a, b in zip(points, points[1:]))
                    self.assertLessEqual(error, .01000001)

    def test_straight_bezier_uses_one_segment_and_budget_fails_explicitly(self):
        line = CubicBezier((0, 0), (20, 0), (80, 0), (100, 0))
        self.assertEqual(flatten_segment(line, .01, 2), [(100, 0)])
        curve = CubicBezier((0, 0), (0, 100), (100, 100), (100, 0))
        with self.assertRaisesRegex(ValueError, 'Simplify'):
            flatten_segment(curve, .00001, 4)
        for tolerance in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                flatten_segment(line, tolerance, 100)

    def test_transformed_svg_preserves_small_curves_closure_and_open_gaps(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)/'detail.svg'
            path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><g transform="translate(10 20) scale(3 2)">'
                            '<path d="M0 0 C0 1 1 -1 1 0 M2 0 Q3 1 4 0 Z M5 0 L6 0 L5 .0001"/>'
                            '</g></svg>')
            drawing = read_svg(path)
        self.assertEqual(len(drawing), 3)
        self.assertEqual(drawing[0][0], (10, 20))
        self.assertGreater(len(drawing[0]), 8)
        self.assertEqual(drawing[1][0], drawing[1][-1])
        self.assertNotEqual(drawing[2][0], drawing[2][-1])
