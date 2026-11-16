from dataclasses import replace
from unittest import TestCase

from scrib3 import presets
from scrib3.drawing import Sheet
from scrib3.gcode import Machine, generate_gcode
from scrib3.paper_mount import machine_point, required_travel


class PaperMountTests(TestCase):
    def test_letter_corners_cover_negative_x_and_positive_y(self):
        self.assertEqual(required_travel(279.4, 215.9, 'top_left_y'), (215.9, 279.4))
        for paper, expected in (((0, 215.9), (0, 0)), ((279.4, 215.9), (0, 279.4)),
                                ((0, 0), (-215.9, 0)), ((279.4, 0), (-215.9, 279.4))):
            self.assertEqual(machine_point(*paper, 215.9, 'top_left_y'), expected)

    def test_asymmetric_path_moves_right_then_down_in_both_units(self):
        sheet = Sheet(279.4, 215.9, 12.7)
        drawing = (((0, 215.9), (25.4, 215.9), (25.4, 165.1)),)
        machine = Machine(215.9, 279.4, 254, 'M3 S180', 'M3 S70', .5, paper_mount='top_left_y')
        inches = generate_gcode(drawing, sheet, machine, 'in', dry_run=True)
        self.assertIn('G0 X0.00000 Y0.00000', inches)
        self.assertIn('G1 X0.00000 Y1.00000 F10.00000', inches)
        self.assertIn('G1 X-2.00000 Y1.00000', inches)
        self.assertNotIn('M3 S70', inches)
        metric = generate_gcode(drawing, sheet, machine)
        self.assertIn('G1 X-50.800 Y25.400', metric)
        self.assertIn('M3 S70.000', metric)

    def test_travel_checks_follow_physical_axes_and_signed_rounding(self):
        sheet = Sheet(279.4, 215.9, 0)
        machine = Machine(215.9, 279.4, 300, 'M3 S180', 'M3 S70', paper_mount='top_left_y')
        drawing = (((0, 0), (279.4, 215.9)),)
        generate_gcode(drawing, sheet, machine)
        for change in ({'width': 215}, {'height': 279}):
            with self.assertRaisesRegex(ValueError, 'paper does not fit'):
                generate_gcode(drawing, sheet, replace(machine, **change))
        with self.assertRaisesRegex(ValueError, 'rounded plotting point'):
            generate_gcode((((0, 0), (1, 1)),), Sheet(2, 1.0002, 0),
                           replace(machine, width=1.0002, height=2), 'in')

    def test_existing_saved_mount_is_preserved_until_explicitly_changed(self):
        legacy = {key: value for key, value in presets.builtin().items() if key in presets.V2_FIELDS}
        legacy.update(schema_version=2, paper_width_mm=148, paper_height_mm=105, feed_mm_min=25.4,
                      x_steps_per_mm=5.2)
        migrated = presets.validate(legacy)
        self.assertEqual(migrated['paper_mount'], 'bottom_left_x')
        self.assertEqual(migrated['x_steps_per_mm'], 5.2)
        self.assertEqual(migrated['paper_width_mm'], 148)
        self.assertEqual(migrated['feed_mm_min'], 25.4)
        self.assertEqual(machine_point(3, 4, 105, migrated['paper_mount']), (3, 4))
        for invalid in ('unknown', [], None):
            with self.assertRaises(ValueError):
                presets.validate(presets.builtin() | {'paper_mount': invalid})
