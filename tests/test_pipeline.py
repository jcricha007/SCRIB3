import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scrib3 import grbl, ollama
from scrib3.drawing import Sheet, fit_to_sheet, read_svg
from scrib3.gcode import Machine, generate_gcode


class PlottingTests(TestCase):
    def test_svg_subpaths_become_independent_y_up_strokes(self):
        with TemporaryDirectory() as directory:
            svg = Path(directory) / "figure.svg"
            svg.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
                '<g transform="translate(10 20)">'
                '<path d="M0 0 L10 10 M5 0 Q2 4 0 10" />'
                '</g></svg>',
                encoding="utf-8",
            )
            drawing = read_svg(svg)
        self.assertEqual(drawing[0], ((10, 20), (20, 30)))
        self.assertEqual(len(drawing), 2)
        sheet = Sheet(40, 30, 5)
        first, second = fit_to_sheet(drawing, sheet)
        self.assertEqual(first, ((10, 25), (30, 5)))
        self.assertEqual(second[0], (20, 25))
        self.assertEqual(second[-1], (10, 5))

    def test_gcode_lifts_between_strokes_and_reasserts_drawing_feed(self):
        sheet = Sheet(40, 30, 5)
        machine = Machine(40, 30, 600, "G0 Z3", "G1 Z0 F100")
        drawing = (((10, 5), (20, 15)), ((30, 20), (35, 25)))
        program = generate_gcode(drawing, sheet, machine).splitlines()
        self.assertEqual(program[2:], [
            "G0 Z3.000", "G0 X10.000 Y5.000", "G1 Z0.000 F100.000",
            "G1 X20.000 Y15.000 F600.000", "G0 Z3.000",
            "G0 X30.000 Y20.000", "G1 Z0.000 F100.000",
            "G1 X35.000 Y25.000 F600.000", "G0 Z3.000",
        ])

    def test_gcode_rejects_jobs_outside_travel_and_non_pen_commands(self):
        machine = Machine(40, 30, 600, "M5", "M3 S90")
        with self.assertRaisesRegex(ValueError, "paper does not fit"):
            generate_gcode((((10, 5), (20, 15)),), Sheet(41, 30, 5), machine)
        with self.assertRaisesRegex(ValueError, "outside the paper"):
            generate_gcode((((10, 5), (41, 15)),), Sheet(40, 30, 5), machine)
        for invalid in ("G0 Z3 X99", "G0\nZ3", "G1 Z0 F0.0001", "$H"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                Machine(40, 30, 600, "G0 Z3", invalid)

    def test_ollama_returns_geometry_and_rejects_commands(self):
        response = {"message": {"content": '{"strokes":[[[0,1],[12,34]]]}' }}
        with patch.object(ollama, "build_opener") as build:
            opener = build.return_value
            opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
            self.assertEqual(ollama.generate_drawing("sample:latest", "draw a line"), (((0, 1), (12, 34)),))
            request = opener.open.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:11434/api/chat")
            self.assertEqual(json.loads(request.data)["format"], ollama.SCHEMA)
        for invalid in ('{"gcode":"$H"}', '{"strokes":[[[true,1],[2,3]]]}',
                        '{"strokes":[[[0,1],[1001,2]]]}'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ollama.parse_drawing(invalid)

    def test_serial_inspection_sends_only_read_queries(self):
        with patch.object(grbl.serial, "Serial") as serial:
            connection = serial.return_value.__enter__.return_value
            connection.read_until.side_effect = [
                b"Grbl 1.1h\n", b"<Id", b"le|MPos:0,0,0|Ov:100,100,100>\n",
                b"[VER:1.1h]\n", b"ok\n", b"$130=150.000\n", b"ok\n",
                b"[GC:G0 G54 G17 G21 G90 G94 M5 M9 T0 F0 S0]\n", b"ok\n",
                b"[G54:0.000,0.000,0.000]\n", b"ok\n",
            ]
            report = grbl.inspect("COM3")
            self.assertEqual([call.args[0] for call in connection.write.call_args_list],
                             [b"?", b"$I\n", b"$$\n", b"$G\n", b"$#\n"])
            self.assertIn("<Idle|MPos:0,0,0|Ov:100,100,100>", report)
            self.assertIn("$130=150.000", report)
