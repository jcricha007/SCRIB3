from unittest import TestCase
from unittest.mock import patch

from scrib3 import grbl
from scrib3.drawing import Sheet
from scrib3.firmware import ServoSettings
from scrib3.gcode import Machine, generate_gcode

REPORT = (
    "Grbl 1.1h ['$' for help]\n"
    "?\n<Idle|MPos:0,0,0|Ov:100,100,100>\n"
    "$I\n[VER:1.1h.20190830:]\nok\n"
    "$$\n$30=1000.000\n$31=0.000\n$32=0\nok\n"
)


class FirmwareTests(TestCase):
    def test_servo_commands_use_reported_scale_and_distinct_pulses(self):
        servo = ServoSettings.from_report(REPORT)
        self.assertEqual([servo.timer_count(s) for s in (None, 0, 100, 200, 240)],
                         [31, 31, 21, 11, 7])
        self.assertEqual(ServoSettings(2000, 1000, 0, 100).timer_count(100), 21)
        for invalid in (241, 500, 1000):
            with self.subTest(s=invalid), self.assertRaisesRegex(ValueError, "pulse range"):
                Machine(100, 100, 300, "M5", f"M3 S{invalid}", servo=servo)
        with self.assertRaisesRegex(ValueError, "same servo pulse"):
            Machine(100, 100, 300, "M3 S1", "M3 S9", servo=servo)
        with self.assertRaisesRegex(ValueError, "uses M3"):
            Machine(100, 100, 300, "G0 Z3", "G0 Z0", servo=servo)

    def test_servo_export_retains_dwell_and_final_lift(self):
        machine = Machine(100, 100, 300, "M5", "M3 S100", 0.2,
                          ServoSettings.from_report(REPORT))
        lines = generate_gcode((((5, 5), (15, 5)),), Sheet(20, 20, 0), machine).splitlines()
        self.assertEqual(lines[2:], [
            "M5", "G4 P0.200", "G0 X5.000 Y5.000",
            "M3 S100.000", "G4 P0.200", "G1 X15.000 Y5.000 F300.000",
            "M5", "G4 P0.200",
        ])

    def test_snapshot_requires_complete_settings_and_valid_servo_mode(self):
        for report in (
            REPORT.replace("$32=0\n", ""),
            REPORT.replace("$32=0\nok", "$32=0\nerror:1"),
            REPORT.replace("$32=0\nok", "$32=0\n"),
            REPORT.replace("$32=0", "$32=1"),
            REPORT.replace("$30=1000.000", "$30=0.000"),
            REPORT.replace("Ov:100,100,100", "Ov:100,100,150"),
            REPORT.replace("|Ov:100,100,100", ""),
        ):
            with self.subTest(report=report), self.assertRaises(ValueError):
                ServoSettings.from_report(report)
        interleaved = REPORT.replace("$31=0.000", "<Idle|MPos:0,0,0>\n$31=0.000")
        self.assertEqual(ServoSettings.from_report(interleaved).rpm_max, 1000)

    def test_missing_intermittent_override_is_polled_without_writing_settings(self):
        with patch.object(grbl.serial, "Serial") as serial, patch.object(grbl, "sleep"):
            connection = serial.return_value.__enter__.return_value
            connection.read_until.side_effect = [
                b"Grbl 1.1h\n", b"<Idle|MPos:0,0,0>\n",
                b"[VER:1.1h.20190830:]\n", b"ok\n",
                b"$30=1000\n", b"$31=0\n", b"$32=0\n", b"ok\n",
                b"[GC:G21 G90 G54 M5]\n", b"ok\n",
                b"[G54:0,0,0]\n", b"ok\n",
                b"<Idle|MPos:0,0,0>\n", b"<Idle|MPos:0,0,0|Ov:100,100,100>\n",
            ]
            report = grbl.inspect("COM3")
            self.assertEqual(ServoSettings.from_report(report).spindle_override, 100)
            self.assertEqual(
                [call.args[0] for call in connection.write.call_args_list],
                [b"?", b"$I\n", b"$$\n", b"$G\n", b"$#\n", b"?", b"?"],
            )
