from dataclasses import replace
import json
from math import dist, pi
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import ezdxf

from scrib3 import presets
from scrib3.design import pattern, transform
from scrib3.drawing import Sheet, fit_to_sheet, order_strokes
from scrib3.gcode import Machine, generate_gcode, overlap_closed_stroke
from scrib3.setup_guides import DRAW_FEED, SMOOTH_SETTINGS
from scrib3.vector_io import read_drawing, write_drawing


class VectorQualityTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)

    def dxf(self, build):
        doc = ezdxf.new('R2010')
        build(doc, doc.modelspace())
        path = self.path / 'test.dxf'
        doc.saveas(path)
        return read_drawing(path)

    def test_rosette_closes_before_overlap_in_both_units_and_mountings(self):
        sheet = Sheet(279.4, 215.9, 12.7)
        drawing = order_strokes(fit_to_sheet(transform(pattern('Rosette', 12), 'Mirror X'), sheet))
        self.assertTrue(all(s[0] == s[-1] for s in drawing))
        for units in ('in', 'mm'):
            for mount in ('top_left_y', 'bottom_left_x'):
                machine = Machine(300, 300, 3000, 'M3 S180', 'M3 S70', .5, paper_mount=mount, seam_overlap=.5)
                program = generate_gcode(drawing, sheet, machine, units)
                strokes = []
                for line in program.splitlines():
                    if line.startswith('G0 X'):
                        strokes.append([line.split()[1:3]])
                    elif line.startswith('G1 X'):
                        strokes[-1].append(line.split()[1:3])
                self.assertEqual(len(strokes), 12)
                for stroke in strokes:
                    self.assertEqual(stroke[0], stroke[-2])
                    self.assertNotEqual(stroke[0], stroke[-1])
                dry = generate_gcode(drawing, sheet, machine, units, dry_run=True)
                self.assertNotIn('M3 S70', dry)
                self.assertEqual([l for l in dry.splitlines() if l.startswith(('G0 X', 'G1 X'))],
                                 [l for l in program.splitlines() if l.startswith(('G0 X', 'G1 X'))])

    def test_overlap_follows_segments_is_bounded_and_never_closes_open_paths(self):
        loop = ((0, 0), (.1, 0), (.1, .2), (0, .2), (0, 0))
        extended = overlap_closed_stroke(loop, .35)
        self.assertEqual(extended[:len(loop)], loop)
        extra_length = sum(dist(a, b) for a, b in zip(extended[len(loop)-1:], extended[len(loop):]))
        self.assertAlmostEqual(extra_length, .35)
        self.assertAlmostEqual(extended[-1][0], .05)
        self.assertEqual(overlap_closed_stroke(loop, 5), loop+loop[1:])
        self.assertEqual(overlap_closed_stroke(loop, 0), loop)
        for open_path in (loop[:-1], loop[:-1]+((0, .00001),)):
            self.assertEqual(overlap_closed_stroke(open_path, .5), open_path)
        for value in (-1, 5.01, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                Machine(100, 100, 60, 'M3 S180', 'M3 S70', seam_overlap=value)

    def test_existing_preset_migrates_without_changing_feed_or_enabling_overlap(self):
        previous = {k: v for k, v in presets.builtin().items() if k in presets.V3_FIELDS}
        previous.update(schema_version=3, feed_mm_min=8890)
        migrated = presets.validate(previous)
        self.assertEqual(migrated['feed_mm_min'], 8890)
        self.assertEqual(migrated['seam_overlap_mm'], 0)
        self.assertEqual(presets.builtin()['seam_overlap_mm'], .5)
        self.assertEqual((SMOOTH_SETTINGS[110], SMOOTH_SETTINGS[111]), (8890, 8890))
        self.assertEqual((SMOOTH_SETTINGS[120], SMOOTH_SETTINGS[121], DRAW_FEED), (25, 25, 3000))
        self.assertNotIn(1, SMOOTH_SETTINGS)

    def test_all_export_formats_round_trip_fitted_geometry_and_closure(self):
        sheet = Sheet(100, 80, 5)
        source = (((0, 0), (10, 0), (10, 5), (0, 0)), ((2, 1), (3, 2), (7, 4)))
        drawing = fit_to_sheet(source, sheet)
        for extension in ('svg', 'dxf', 'json'):
            path = self.path / ('drawing.'+extension)
            write_drawing(path, drawing, sheet)
            restored = fit_to_sheet(read_drawing(path), sheet)
            self.assertEqual(len(restored), 2)
            self.assertEqual(restored[0][0], restored[0][-1])
            self.assertNotEqual(restored[1][0], restored[1][-1])
            for before, after in zip(drawing, restored):
                self.assertEqual(len(before), len(after))
                for a, b in zip(before, after):
                    self.assertLess(dist(a, b), 1e-5)

    def test_dxf_curves_bulges_and_closed_polylines_preserve_topology(self):
        def build(doc, m):
            m.add_circle((10, 10), 5)
            m.add_arc((30, 10), 5, 0, 180)
            m.add_ellipse((50, 10), major_axis=(5, 0), ratio=.5)
            m.add_ellipse((70, 10), major_axis=(5, 0), ratio=.5, end_param=pi)
            m.add_lwpolyline([(0, 0, 1), (10, 0, 0), (10, 10, 0)], format='xyb', close=True)
            m.add_polyline2d([(15, 0), (20, 0), (20, 5)], close=True)
            m.add_spline([(1, 2), (3, 5), (7, 3), (9, 9)])
        drawing = self.dxf(build)
        self.assertEqual([s[0] == s[-1] for s in drawing], [True, False, True, False, True, True, False])
        circle = drawing[0]
        self.assertTrue(all(abs(dist(p, (10, -10))-5) < .003 for p in circle))
        self.assertGreater(len(drawing[4]), 5)  # Bulge is curved, not a straight chord.
        self.assertLess(min(y for _, y in drawing[0]), -14.99)

    def test_dxf_transformed_blocks_arrays_and_hidden_layers(self):
        def build(doc, m):
            hidden = doc.layers.new('hidden'); hidden.off()
            b = doc.blocks.new('B'); b.add_line((0, 0), (1, 0))
            m.add_blockref('B', (5, 7), dxfattribs={'rotation': 90, 'xscale': 2, 'yscale': 2})
            m.add_blockref('B', (0, 0), dxfattribs={'column_count': 2, 'column_spacing': 3})
            m.add_blockref('B', (20, 20), dxfattribs={'layer': 'hidden'})
            m.add_text('hidden text', dxfattribs={'layer': 'hidden'})
        drawing = self.dxf(build)
        self.assertEqual(len(drawing), 3)
        self.assertLess(dist(drawing[0][0], (5, -7)), 1e-8)
        self.assertLess(dist(drawing[0][-1], (5, -9)), 1e-8)
        self.assertEqual(drawing[2], ((3, 0), (4, 0)))

    def test_dxf_rejects_unsupported_nonplanar_and_recursive_geometry(self):
        for build, error in ((lambda d, m: m.add_text('live text'), 'TEXT'),
                            (lambda d, m: m.add_line((0, 0, 0), (2, 1, 1)), 'nonplanar'),
                            (lambda d, m: m.add_hatch(), 'HATCH')):
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                self.dxf(build)
        def recursive(doc, m):
            b = doc.blocks.new('B'); b.add_blockref('B', (0, 0)); m.add_blockref('B', (0, 0))
        with self.assertRaisesRegex(ValueError, 'recursive'):
            self.dxf(recursive)

    def test_json_validation_limits_and_explicit_closure(self):
        path = self.path / 'drawing.json'
        base = {'format': 'scrib3-drawing', 'version': 1, 'units': 'in', 'strokes': [
            {'points': [[0, 0], [1, 0], [1, 1]], 'closed': True},
            {'points': [[0, 0], [1, 1]], 'closed': False}]}
        path.write_text(json.dumps(base))
        result = read_drawing(path)
        self.assertEqual(result[0], ((0, 0), (25.4, 0), (25.4, 25.4), (0, 0)))
        for bad in (base|{'gcode': 'G0 X100'}, base|{'version': True}, base|{'strokes': []},
                    base|{'strokes': [{'points': [[0, 0], [float('nan'), 1]], 'closed': False}]},
                    base|{'strokes': [{'points': [[0, 0], [True, 1]], 'closed': False}]}):
            path.write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                read_drawing(path)
        path.write_text(json.dumps(base))
        with patch('scrib3.vector_io.MAX_POINTS', 3), self.assertRaises(ValueError):
            read_drawing(path)

    def test_svg_close_and_circle_vs_intentionally_open_subpath(self):
        path = self.path / 'curves.svg'
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg"><circle cx="10" cy="10" r="5"/>'
                        '<path d="M20 20L30 20L30 30z M40 40L50 40L40 40.0001"/></svg>')
        drawing = read_drawing(path)
        self.assertEqual([s[0] == s[-1] for s in drawing], [True, True, False])
