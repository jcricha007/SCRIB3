import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch

from scrib3 import design, ollama, presets
from scrib3.calibration import corrected_steps
from scrib3.drawing import Sheet, fit_to_sheet, read_svg


class DesignTests(TestCase):
    def test_measured_scale_correction_and_invalid_measurements(self):
        self.assertEqual(corrected_steps(250, .1, 5), 5)
        self.assertEqual(corrected_steps(5, 25.4, 24), 5.292)
        for measured in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                corrected_steps(5, 10, measured)

    def test_existing_preferences_migrate_without_losing_calibration_or_units(self):
        legacy = {key: value for key, value in presets.builtin().items() if key in presets.LEGACY_FIELDS}
        legacy.update(schema_version=1, units='mm', pen_down='M3 S80')
        migrated = presets.validate(legacy)
        self.assertEqual((migrated['x_steps_per_mm'], migrated['y_steps_per_mm']), (5, 5))
        self.assertEqual((migrated['units'], migrated['pen_down']), ('mm', 'M3 S80'))
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'prefs.json'
            migrated.update(x_steps_per_mm=5.12, y_steps_per_mm=4.99, ollama_model='engineering:latest')
            presets.save(path, migrated)
            self.assertEqual(presets.load(path), migrated)

    def test_transforms_are_reversible_and_export_matches_preview(self):
        drawing = (((1, 2), (5, 9), (11, 3)),)
        result = drawing
        for _ in range(4):
            result = design.transform(result, 'Rotate 90°')
        self.assertEqual(result, drawing)
        self.assertEqual(design.transform(design.transform(drawing, 'Mirror X'), 'Mirror X'), drawing)
        sheet = Sheet(100, 70, 5)
        fitted = fit_to_sheet(drawing, sheet)
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'design.svg'
            path.write_text(design.svg_document(fitted, sheet))
            restored = fit_to_sheet(read_svg(path), sheet)
        for a, b in zip(fitted[0], restored[0]):
            self.assertAlmostEqual(a[0], b[0], places=5)
            self.assertAlmostEqual(a[1], b[1], places=5)

    def test_patterns_stay_inside_paper_and_complex_revision_is_rejected(self):
        sheet = Sheet(148, 105, 7)
        for kind in ('Grid', 'Spiral', 'Rosette'):
            drawing = design.pattern(kind, 12)
            for stroke in fit_to_sheet(drawing, sheet):
                for x, y in stroke:
                    self.assertTrue(7-1e-8 <= x <= 141+1e-8 and 7-1e-8 <= y <= 98+1e-8)
        with self.assertRaisesRegex(ValueError, 'too detailed'):
            design.ai_reference(design.pattern('Spiral', 12))
        for point in design.ai_reference((((-3, 10), (7, 20)),))[0]:
            self.assertTrue(all(0 <= value <= 1000 for value in point))


class OllamaTests(TestCase):
    def response(self, data):
        return io.BytesIO(json.dumps(data).encode())

    def test_discovery_excludes_remote_aliases_and_cloud_models(self):
        data = {'models': [{'name': 'engineering:latest'}, {'name': 'local:8b'},
                           {'name': 'alias:latest', 'remote_host': 'https://ollama.com'},
                           {'name': 'another-alias', 'remote_model': 'remote'}, {'name': 'big:cloud'}]}
        with patch.object(ollama, '_open', return_value=self.response(data)) as request:
            self.assertEqual(ollama.local_models(), ('engineering:latest', 'local:8b'))
            self.assertEqual(request.call_args.args[0], '/api/tags')

    def test_chat_stream_and_history_limits_without_tool_execution(self):
        raw = b'{"message":{"content":"Hello "},"done":false}\n{"message":{"content":"John"},"done":true}\n'
        messages = [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': str(i)} for i in range(20)]
        chunks = []
        with patch.object(ollama, 'local_models', return_value=('engineering:latest',)), patch.object(ollama, '_open', return_value=io.BytesIO(raw)) as request:
            self.assertEqual(ollama.chat('engineering', messages, 'Paper 148 × 105 mm', on_chunk=chunks.append), 'Hello John')
            payload = request.call_args.args[1]
            self.assertTrue(payload['stream'])
            self.assertEqual(len(payload['messages']), 13)
            self.assertNotIn('tools', payload)
            self.assertIn('Paper 148', payload['messages'][0]['content'])
        self.assertEqual(chunks, ['Hello ', 'John'])

    def test_cancel_and_missing_model_prevent_chat_post(self):
        cancel = Event(); cancel.set()
        with patch.object(ollama, 'local_models', return_value=('local:8b',)), patch.object(ollama, '_open') as request:
            self.assertEqual(ollama.chat('local:8b', [{'role': 'user', 'content': 'Hello'}], cancel=cancel), '')
            with self.assertRaises(ValueError):
                ollama.chat('unknown', [{'role': 'user', 'content': 'Hello'}])
            request.assert_not_called()

    def test_truncated_malformed_and_error_streams_are_rejected(self):
        for raw in (b'', b'not json\n', b'[]\n', b'{"error":"out of memory"}\n',
                    b'{"message":{"content":"part"},"done":false}\n',
                    b'{"message":{"content":"part"},"done":true,"done_reason":"length"}\n'):
            with self.subTest(raw=raw), patch.object(ollama, 'local_models', return_value=('local:8b',)), patch.object(ollama, '_open', return_value=io.BytesIO(raw)):
                with self.assertRaises(ValueError):
                    ollama.chat('local:8b', [{'role': 'user', 'content': 'Hello'}])

    def test_revision_sends_validated_geometry_and_requires_complete_response(self):
        response = {'done': True, 'message': {'content': '{"strokes":[[[0,0],[1000,1000]]]}'}}
        with patch.object(ollama, 'local_models', return_value=('local:8b',)), patch.object(ollama, '_json_request', return_value=response) as request:
            drawing = ollama.generate_drawing('local:8b', 'Add a diagonal', (((-1, 2), (4, 7)),))
            self.assertEqual(drawing, (((0, 0), (1000, 1000)),))
            payload = request.call_args.args[1]
            self.assertEqual(payload['format'], ollama.SCHEMA)
            self.assertIn('1000.0', payload['messages'][1]['content'])
            response['done_reason'] = 'length'
            with self.assertRaisesRegex(ValueError, 'did not finish'):
                ollama.generate_drawing('local:8b', 'Draw')
