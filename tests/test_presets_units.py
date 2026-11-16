import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scrib3 import presets
from scrib3.controller import SETUP_FIELDS, jog_command, setting_changes
from scrib3.drawing import Sheet
from scrib3.firmware import ServoSettings
from scrib3.gcode import Machine, generate_gcode
from scrib3.units import display, from_mm, setting_display, setting_native, to_mm
from test_controller import FakeSerial


class PresetUnitTests(TestCase):
    def test_bundled_preset_contains_observed_pen_positions_and_no_machine_reference(self):
        data = presets.builtin()
        self.assertEqual((data['units'], data['pen_up'], data['pen_down']), ('in', 'M3 S180', 'M3 S70'))
        self.assertIsNone(data['machine_width_mm'])
        self.assertEqual((data['paper_width_mm'], data['paper_height_mm'], data['margin_mm']), (279.4, 215.9, 12.7))
        self.assertEqual(data['paper_mount'], 'top_left_y')
        self.assertEqual((data['feed_mm_min'], data['jog_feed_mm_min']), (300, 150))
        self.assertNotIn('manual_home', data)
        servo = ServoSettings(1000, 0, 0, 100)
        self.assertEqual((servo.timer_count(180), servo.timer_count(70)), (13, 24))

    def test_saved_preset_survives_relaunch_and_failed_write_keeps_previous_file(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'app data' / 'preset.json'
            data = presets.load(path)
            data.update(units='mm', name='My calibration', feed_mm_min=254, machine_width_mm=200)
            presets.save(path, data)
            self.assertEqual(presets.load(path), data)
            changed = data | {'pen_down': 'M3 S80'}
            with patch.object(presets.os, 'replace', side_effect=OSError('write denied')):
                with self.assertRaises(OSError):
                    presets.save(path, changed)
            self.assertEqual(presets.load(path), data)
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_corrupt_or_motion_bearing_presets_are_rejected(self):
        for changes in ({'pen_up': '$H'}, {'pen_down': 'M3 S70\nG0 X100'},
                        {'units': 'degrees'}, {'feed_mm_min': 0}, {'settle': float('nan')},
                        {'schema_version': 999}, {'manual_home': [0, 0]}, {'jog_step_mm': 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                presets.validate(presets.builtin() | changes)
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'broken.json'
            path.write_text('{')
            with self.assertRaises(ValueError):
                presets.load(path)

    def test_inches_jog_is_converted_once_and_servo_values_are_not_scaled(self):
        self.assertEqual(jog_command('X', to_mm(.1, 'in'), to_mm(4, 'in')),
                         '$J=G21 G91 X2.540 F101.600')
        self.assertEqual(from_mm(25.4, 'in'), 1)
        self.assertAlmostEqual(to_mm(display(200, 'in'), 'in'), 200, places=7)

    def test_setup_conversions_preserve_eeprom_values_and_handle_steps_per_inch(self):
        current = FakeSerial().settings
        shown = {n: setting_display(n, current[n], 'in') for n, *_ in SETUP_FIELDS}
        self.assertEqual(shown[100], 6350)
        self.assertAlmostEqual(shown[130], 200 / 25.4)
        native = {n: setting_native(n, f'{value:.10g}', 'in') for n, value in shown.items()}
        self.assertEqual(setting_changes(native, current), {})
        self.assertEqual(setting_native(100, 5080, 'in'), 200)
        self.assertEqual(setting_native(110, 10, 'in'), 254)
        self.assertEqual(setting_native(30, 1000, 'in'), 1000)

    def test_inch_export_retains_physical_geometry_feed_and_servo_commands(self):
        machine = Machine(50.8, 50.8, 254, 'M3 S180', 'M3 S70', .2, ServoSettings(1000, 0, 0, 100))
        program = generate_gcode((((0, 0), (25.4, 50.8)),), Sheet(50.8, 50.8, 0), machine, units='in')
        self.assertIn('G20 G90 G94 G17 G54 G49', program)
        self.assertIn('G1 X1.00000 Y2.00000 F10.00000', program)
        self.assertIn('M3 S180.000', program)
        self.assertIn('M3 S70.000', program)
        self.assertTrue(program.endswith('M3 S180.000\nG4 P0.200\n'))
        metric = generate_gcode((((0, 0), (25.4, 50.8)),), Sheet(50.8, 50.8, 0), machine)
        self.assertIn('G1 X25.400 Y50.800 F254.000', metric)

    def test_inch_export_converts_z_commands_and_rejects_rounded_out_of_bounds(self):
        machine = Machine(50.8, 50.8, 254, 'G0 Z2.54', 'G1 Z0 F25.4')
        program = generate_gcode((((0, 0), (25.4, 25.4)),), Sheet(50.8, 50.8, 0), machine, units='in')
        self.assertIn('G0 Z0.10000', program)
        self.assertIn('G1 Z0.00000 F1.00000', program)
        with self.assertRaisesRegex(ValueError, 'rounded plotting point'):
            generate_gcode((((0, 0), (1.0002, 0)),), Sheet(1.0002, 2, 0),
                           Machine(1.0002, 2, 100, 'M3 S180', 'M3 S70'), units='in')
