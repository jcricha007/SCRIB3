from math import dist
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scrib3.drawing import Sheet, fit_to_sheet, read_svg
from scrib3.gcode import Machine, generate_gcode
from scrib3.svg_dashes import dash_pattern, split_dashes
from scrib3.toolpath import QualityOptions, prepare_toolpath


class SvgDashesTests(TestCase):
    def svg(self, body):
        with TemporaryDirectory() as folder:
            file = Path(folder)/'dashes.svg'
            file.write_text('<svg xmlns="http://www.w3.org/2000/svg">'+body+'</svg>')
            return read_svg(file)

    def test_dash_phase_offsets_odd_arrays_and_subpath_reset(self):
        stroke = ((0, 0), (10, 0))
        self.assertEqual(split_dashes(stroke, (3, 2), 0), (((0, 0), (3, 0)), ((5, 0), (8, 0))))
        self.assertEqual(split_dashes(stroke, (3, 2), 1), (((0, 0), (2, 0)), ((4, 0), (7, 0)), ((9, 0), (10, 0))))
        self.assertEqual(split_dashes(stroke, (3, 2), -1), (((1, 0), (4, 0)), ((6, 0), (9, 0))))
        self.assertEqual(dash_pattern({'stroke-dasharray': '2,1,3'})[0], (2, 1, 3, 2, 1, 3))
        drawing = self.svg('<g stroke-dasharray="3 2"><path d="M0 0L10 0 M0 5L10 5"/></g>')
        self.assertEqual(drawing[-2:], (((0, 5), (3, 5)), ((5, 5), (8, 5))))

    def test_phase_continues_around_vertices_and_closed_seams(self):
        loop = ((0, 0), (10, 0), (10, 10), (0, 10), (0, 0))
        result = split_dashes(loop, (6, 4), 2)
        self.assertEqual(len(result), 4)
        self.assertIn((0, 0), result[0])
        self.assertEqual(result[0], ((0, 2), (0, 0), (4, 0)))
        joined = split_dashes(((0, 0), (5, 0), (5, 5)), (20, 2), 0)
        self.assertEqual(joined, (((0, 0), (5, 0), (5, 5)),))
        self.assertEqual(split_dashes(((0, 0), (10, 0)), (3, 0), 0),
                         (((0, 0), (3, 0), (6, 0), (9, 0), (10, 0)),))

    def test_nonuniform_transform_and_physical_lengths(self):
        drawing = self.svg('<g transform="translate(7,9) scale(2,3)" stroke-dasharray="2 1">'
                           '<path d="M0 0L10 0" style="stroke-dashoffset:1"/></g>')
        self.assertEqual(drawing[0], ((7, 9), (9, 9)))
        self.assertEqual(drawing[1], ((11, 9), (15, 9)))
        pattern, offset = dash_pattern({'stroke-dasharray': '1in 2.54cm', 'stroke-dashoffset': '72pt'})
        self.assertAlmostEqual(pattern[0], pattern[1], places=3)
        self.assertAlmostEqual(offset, 96, places=3)

    def test_curved_dashes_remain_on_curve_and_gaps_survive_gcode(self):
        drawing = self.svg('<path fill="none" stroke="black" stroke-dasharray="4 2" '
                           'd="M10 0 A10 10 0 0 1 0 10"/>')
        self.assertGreater(len(drawing), 1)
        for stroke in drawing:
            for p in stroke:
                self.assertAlmostEqual(dist(p, (0, 0)), 10, delta=.001)
        sheet = Sheet(100, 80, 5)
        plotted, _ = prepare_toolpath(fit_to_sheet(drawing, sheet), QualityOptions(order=False))
        self.assertEqual(len(plotted), len(drawing))
        program = generate_gcode(plotted, sheet, Machine(100, 100, 1000, 'M3 S180', 'M3 S70'))
        self.assertEqual(sum(l.startswith('G0 X') for l in program.splitlines()), len(drawing))

    def test_invalid_unsupported_and_excessively_dense_patterns_fail(self):
        for attributes in ('stroke-dasharray="-1 2"', 'stroke-dasharray="10% 2"',
                           'stroke-dasharray="2 2" pathLength="10"',
                           'stroke-dasharray="2 2" vector-effect="non-scaling-stroke"',
                           'stroke-dasharray="0 2" stroke-linecap="round"',
                           'stroke-dasharray=".00001 .00001"'):
            with self.subTest(attributes=attributes), self.assertRaises(ValueError):
                self.svg('<path d="M0 0L100 0" '+attributes+'/>')
        self.assertEqual(self.svg('<path d="M0 0L100 0" stroke-dasharray="0 0"/>'), (((0, 0), (100, 0)),))
