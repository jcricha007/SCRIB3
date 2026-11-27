from math import sin
from unittest import TestCase
from dataclasses import replace

from scrib3 import presets
from scrib3.curves import segment_distance
from scrib3.drawing import Sheet
from scrib3.gcode import Machine, generate_gcode
from scrib3.toolpath import QualityOptions, prepare_toolpath


class ToolpathTests(TestCase):
    def test_simplification_reduces_gcode_with_measured_error_bound(self):
        original = (tuple((i/20, 10+sin(i/30)) for i in range(1001)),)
        optimized, report = prepare_toolpath(original, QualityOptions('Balanced', order=False))
        self.assertLess(report.after.points, report.before.points/4)
        self.assertEqual(optimized[0][0], original[0][0])
        self.assertEqual(optimized[0][-1], original[0][-1])
        for p in original[0]:
            self.assertLessEqual(min(segment_distance(p, a, b) for a, b in zip(optimized[0], optimized[0][1:])), .020000001)
        sheet = Sheet(60, 30, 1)
        machine = Machine(60, 60, 600, 'M5', 'M3 S70')
        self.assertLess(len(generate_gcode(optimized, sheet, machine)),
                        len(generate_gcode(original, sheet, machine))/3)
        # G-code mode and mounting never affect the physical cleanup tolerance.
        for units in ('mm', 'in'):
            for mount in ('top_left_y', 'bottom_left_x'):
                ink = generate_gcode(optimized, sheet, replace(machine, paper_mount=mount), units)
                dry = generate_gcode(optimized, sheet, replace(machine, paper_mount=mount), units, dry_run=True)
                self.assertNotIn('M3 S70', dry)
                self.assertEqual([s for s in ink.splitlines() if s.startswith(('G0 X', 'G1 X'))],
                                 [s for s in dry.splitlines() if s.startswith(('G0 X', 'G1 X'))])

    def test_preserves_tiny_loops_open_gaps_extrema_and_backtracking(self):
        loop = ((0, 0), (.001, 0), (.001, .001), (0, .001), (0, 0))
        opened = loop[:-1]+((0, .000001),)
        reversal = ((0, 0), (1, 0), (.5, 0), (2, 0))
        optimized, _ = prepare_toolpath((loop, opened, reversal), QualityOptions(order=False))
        self.assertEqual(optimized[0][0], optimized[0][-1])
        self.assertGreaterEqual(len(set(optimized[0])), 3)
        self.assertNotEqual(optimized[1][0], optimized[1][-1])
        self.assertEqual(optimized[2], reversal)
        for before, after in zip((loop, opened, reversal), optimized):
            for axis in (0, 1):
                self.assertEqual(min(p[axis] for p in before), min(p[axis] for p in after))
                self.assertEqual(max(p[axis] for p in before), max(p[axis] for p in after))

    def test_duplicate_removal_is_exact_opt_in_and_before_simplifying(self):
        a = ((0, 0), (1, 0), (2, 0))
        nearby = ((0, 0), (1, .0001), (2, 0))
        source = (a, a[::-1], nearby)
        untouched, _ = prepare_toolpath(source, QualityOptions('Original', order=False))
        self.assertEqual(untouched, source)
        cleaned, report = prepare_toolpath(source, QualityOptions('Balanced', True, False))
        self.assertEqual(len(cleaned), 2)
        self.assertEqual(report.duplicates_removed, 1)

    def test_ordering_uses_selected_origin_and_never_increases_travel(self):
        source = (((1, 0), (2, 0)), ((1, 20), (2, 20)), ((10, 10), (11, 10)))
        bottom, br = prepare_toolpath(source, QualityOptions('Original'), (0, 0))
        top, tr = prepare_toolpath(source, QualityOptions('Original'), (0, 20))
        self.assertEqual(bottom[0], source[0])
        self.assertEqual(top[0], source[1])
        for report in (br, tr):
            self.assertLessEqual(report.after.travel_mm, report.before.travel_mm)

    def test_v5_migration_and_quality_validation(self):
        legacy = {k: v for k, v in presets.builtin().items() if k in presets.V5_FIELDS}
        legacy.update(schema_version=5, feed_mm_min=1234)
        upgraded = presets.validate(legacy)
        self.assertEqual(upgraded['schema_version'], 8)
        self.assertEqual(upgraded['feed_mm_min'], 1234)
        self.assertEqual(upgraded['quality_mode'], 'Balanced')
        self.assertFalse(upgraded['remove_duplicates'])
        for mode in ('unknown', None, []):
            with self.assertRaises(ValueError):
                QualityOptions(mode)
        with self.assertRaises(ValueError):
            presets.validate(upgraded | {'remove_duplicates': 1})
