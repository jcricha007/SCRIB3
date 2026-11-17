from collections import Counter
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
from unittest import TestCase

from scrib3 import presets
from scrib3.drawing import Sheet, fit_to_sheet, order_strokes, path_lengths, read_svg
from scrib3.gcode import Machine, generate_gcode
from scrib3.routing import join_exact_strokes, optimize_route, stroke_key
from scrib3.toolpath import QualityOptions, prepare_toolpath
from scrib3.vector_io import read_drawing, write_drawing


def ink_edges(drawing):
    return Counter(tuple(sorted((a, b))) for stroke in drawing for a, b in zip(stroke, stroke[1:]))


class RoutingTests(TestCase):
    def test_joining_reversed_fragments_preserves_every_ink_edge_and_reduces_pen_cycles(self):
        source = (((3, 1), (4, 2)), ((2, 1), (1, 1)), ((2, 1), (3, 1)))
        original, report = prepare_toolpath(source, QualityOptions('Original', order=False))
        self.assertEqual(original, source)
        self.assertEqual(report.joins, 0)
        joined, report = prepare_toolpath(source, QualityOptions('Original', join_strokes=True))
        self.assertEqual(report.joins, 2)
        self.assertEqual(ink_edges(joined), ink_edges(source))
        self.assertAlmostEqual(report.before.drawn_mm, report.after.drawn_mm)
        for unit in ('mm', 'in'):
            for mount in ('bottom_left_x', 'top_left_y'):
                machine = Machine(10, 10, 600, 'M5', 'M3 S70', paper_mount=mount)
                before = generate_gcode(original, Sheet(10, 10, 0), machine, unit)
                after = generate_gcode(joined, Sheet(10, 10, 0), machine, unit)
                self.assertEqual(before.count('M3 S70.000'), 3)
                self.assertEqual(after.count('M3 S70.000'), 1)
                dry = generate_gcode(joined, Sheet(10, 10, 0), machine, unit, dry_run=True)
                self.assertNotIn('M3 S70', dry)
                self.assertEqual([s for s in after.splitlines() if s.startswith(('G0 X', 'G1 X'))],
                                 [s for s in dry.splitlines() if s.startswith(('G0 X', 'G1 X'))])

    def test_joining_respects_gaps_branches_interior_vertices_and_existing_loops(self):
        cases = [
            (((0, 0), (1, 0)), ((1.000001, 0), (2, 0))),
            (((0, 0), (1, 0)), ((1, 0), (2, 0)), ((1, 0), (1, 1))),
            (((0, 0), (1, 0)), ((1, 0), (2, 0)), ((1, -1), (1, 0), (1, 1))),
            (((0, 0), (1, 0)), ((1, 0), (2, 0)), ((1, 0), (1, 1), (2, 1), (1, 0))),
        ]
        for source in cases:
            with self.subTest(source=source):
                self.assertEqual(join_exact_strokes(source), source)

    def test_fragment_cycle_closes_without_adding_or_retracing_any_edge(self):
        source = (((0, 0), (1, 0)), ((1, 1), (1, 0)), ((0, 1), (1, 1)), ((0, 0), (0, 1)))
        joined = join_exact_strokes(source)
        self.assertEqual(len(joined), 1)
        self.assertEqual(joined[0][0], joined[0][-1])
        self.assertEqual(ink_edges(joined), ink_edges(source))

    def test_duplicate_loops_ignore_seam_and_direction_but_preserve_nearby_lines(self):
        # The minimum vertex appears twice; identity must not depend on which is chosen.
        ring = ((0, 0), (1, 0), (0, 0), (0, 1))
        loop = ring + (ring[0],)
        copies = []
        for direction in (ring, ring[::-1]):
            for i in range(len(ring)):
                rotated = direction[i:] + direction[:i]
                copies.append(rotated + (rotated[0],))
        nearby = ((0, 0), (1, .000001), (0, 0), (0, 1), (0, 0))
        open_path = loop[:-1] + ((0, .000001),)
        source = tuple(copies) + (nearby, open_path)
        untouched, _ = prepare_toolpath(source, QualityOptions('Original', order=False))
        self.assertEqual(untouched, source)
        cleaned, report = prepare_toolpath(source, QualityOptions('Original', True, False))
        self.assertEqual(cleaned, (loop, nearby, open_path))
        self.assertEqual(report.duplicates_removed, 7)

    def test_loop_entry_uses_both_neighbors_and_can_be_disabled(self):
        loop = ((10, 10), (0, 10), (0, 0), (10, 0), (10, 10))
        source = (loop,)
        fixed = optimize_route(source, (0, 0), reloop=False)
        improved = optimize_route(source, (0, 0))
        self.assertEqual(fixed[0][0], (10, 10))
        self.assertEqual(improved[0][0], (0, 0))
        self.assertEqual(ink_edges(improved), ink_edges(source))
        self.assertEqual(path_lengths(improved)[1], 0)
        kept, _ = prepare_toolpath(source, QualityOptions('Original', order=False))
        self.assertEqual(kept, source)
        # With a following stroke, nearest-to-incoming alone would be worse.
        from scrib3.routing import _relocate_seams
        following = (((11, 10), (12, 10)),)
        both = _relocate_seams(source + following, (0, 0))
        self.assertLessEqual(path_lengths(both)[1], path_lengths(source + following)[1])

    def test_bounded_two_opt_improves_greedy_and_never_changes_ink(self):
        rng = Random(438)
        improvements = []
        for _ in range(30):
            drawing = tuple(tuple((rng.randrange(100), rng.randrange(100)) for _ in range(3))
                            for _ in range(12))
            for start in ((0, 0), (0, 100)):
                candidate = optimize_route(drawing, start)
                greedy = order_strokes(drawing, start)
                self.assertEqual(ink_edges(candidate), ink_edges(drawing))
                self.assertLessEqual(path_lengths(candidate, start)[1], path_lengths(drawing, start)[1])
                self.assertLessEqual(path_lengths(candidate, start)[1], path_lengths(greedy, start)[1] + 1e-10)
                improvements.append(path_lengths(greedy, start)[1] - path_lengths(candidate, start)[1])
                self.assertEqual(candidate, optimize_route(drawing, start))
        self.assertGreater(max(improvements), 20)

    def test_long_fragment_chain_and_repetitive_loop_keep_topology(self):
        source = tuple(((i, 0), (i + 1, 0)) for i in range(2000))
        joined = join_exact_strokes(source)
        self.assertEqual(len(joined), 1)
        self.assertEqual(ink_edges(joined), ink_edges(source))
        ring = ((0, 0), (1, 0)) * 20000 + ((0, 1),)
        rotated = ring[19999:] + ring[:19999]
        self.assertEqual(stroke_key(ring + (ring[0],)), stroke_key(rotated + (rotated[0],)))

    def test_v6_migration_retains_custom_preferences_and_validates_routing_switches(self):
        old = {k: v for k, v in presets.builtin().items() if k in presets.V6_FIELDS}
        old.update(schema_version=6, feed_mm_min=1234, seam_overlap_mm=.3,
                   quality_mode='Fine', remove_duplicates=True, x_steps_per_mm=17)
        new = presets.validate(old)
        self.assertEqual(new['schema_version'], 7)
        for key, value in old.items():
            if key != 'schema_version':
                self.assertEqual(new[key], value)
        self.assertFalse(new['join_strokes'])
        self.assertTrue(new['reloop'])
        for key in ('join_strokes', 'reloop'):
            for invalid in (1, 'true', None):
                with self.assertRaises(ValueError):
                    presets.validate(new | {key: invalid})

    def test_quality_fixture_svg_roundtrip_preserves_cleaned_geometry(self):
        source = read_svg(Path('examples/routing-check.svg'))
        sheet = Sheet(279.4, 215.9, 12.7)
        fitted = fit_to_sheet(source, sheet)
        optimized, report = prepare_toolpath(fitted, QualityOptions('Original', True, True, True))
        self.assertGreater(report.joins, 0)
        self.assertGreater(report.duplicates_removed, 0)
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'clean.svg'
            write_drawing(path, optimized, sheet)
            imported = fit_to_sheet(read_drawing(path), sheet)
        # SVG export changes the Y convention and serializes six decimal places.
        self.assertEqual(len(imported), len(optimized))
        self.assertEqual([s[0] == s[-1] for s in imported], [s[0] == s[-1] for s in optimized])
        self.assertAlmostEqual(path_lengths(imported)[0], path_lengths(optimized)[0], places=4)
