import os
from pathlib import Path
import struct
import subprocess
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase, skipUnless
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from scrib3 import artwork_import as imports
from scrib3.artwork_import import ImportOptions, read_artwork
from scrib3.drawing import path_lengths
from scrib3.raster import ImportCancelled, TraceOptions, load_raster, trace_image


def write_psd(path, image):
    image = image.convert('RGB')
    header = b'8BPS' + struct.pack('>H6sHIIHH', 1, b'\0' * 6, 3, image.height, image.width, 8, 3)
    path.write_bytes(header + b'\0' * 12 + b'\0\0' + b''.join(channel.tobytes() for channel in image.split()))


def write_pdf(path, contents):
    # Minimal real multipage PDF fixture, including an embedded font reference.
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'', b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    kids = []
    for content in contents:
        page_id = len(objects) + 1
        kids.append(f'{page_id} 0 R')
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Resources << /Font << /F1 3 0 R >> >> /Contents {page_id + 1} 0 R >>'.encode())
        objects.append(b'<< /Length ' + str(len(content)).encode() + b' >>\nstream\n' + content + b'\nendstream')
    objects[1] = f'<< /Type /Pages /Kids [{" ".join(kids)}] /Count {len(kids)} >>'.encode()
    data = b'%PDF-1.4\n'
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{i} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(data)
    data += f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode()
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets)
    data += f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()
    path.write_bytes(data)


class RasterImportTests(TestCase):
    def test_traced_artwork_exports_svg_and_reviewable_gcode(self):
        from scrib3.drawing import Sheet, fit_to_sheet
        from scrib3.gcode import Machine, generate_gcode
        from scrib3.toolpath import prepare_toolpath
        from scrib3.vector_io import read_drawing, write_drawing
        drawing, _ = trace_image(self.line_image())
        sheet = Sheet(100, 70, 5)
        prepared, _ = prepare_toolpath(fit_to_sheet(drawing, sheet))
        machine = Machine(100, 100, 600, 'M5', 'M3 S70')
        for units in ('mm', 'in'):
            ink = generate_gcode(prepared, sheet, machine, units)
            dry = generate_gcode(prepared, sheet, machine, units, dry_run=True)
            self.assertIn('G1 X', ink)
            self.assertNotIn('M3 S70', dry)
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'traced.svg'
            write_drawing(path, prepared, sheet)
            self.assertEqual(len(read_drawing(path)), len(prepared))

    def line_image(self):
        image = Image.new('RGB', (100, 70), 'white')
        ImageDraw.Draw(image).line((10, 30, 90, 30), fill='black', width=5)
        return image

    def test_centerline_plots_once_and_outline_is_explicit(self):
        center, preview = trace_image(self.line_image())
        outline, _ = trace_image(self.line_image(), TraceOptions(mode='Outline'))
        self.assertEqual(len(center), 1)
        self.assertLess(path_lengths(center)[0], 85)
        self.assertGreater(path_lengths(center)[0], 70)
        self.assertEqual(outline[0][0], outline[0][-1])
        self.assertGreater(path_lengths(outline)[0], 150)
        self.assertEqual(preview.size, (100, 70))

    def test_real_png_and_psd_decode_same_composite(self):
        with TemporaryDirectory() as folder:
            png, psd = Path(folder) / 'drawing.PNG', Path(folder) / 'drawing.PSD'
            image = self.line_image()
            image.save(png)
            write_psd(psd, image)
            a, b = read_artwork(png), read_artwork(psd)
            self.assertEqual(a.drawing, b.drawing)
            self.assertIn('merged composite', b.note)

    def test_transparency_inversion_specks_and_blank_art(self):
        image = Image.new('RGBA', (100, 70), (255, 255, 255, 0))
        draw = ImageDraw.Draw(image)
        draw.line((10, 30, 90, 30), fill=(255, 255, 255, 255), width=5)
        draw.point((5, 5), fill=(255, 255, 255, 255))
        with self.assertRaisesRegex(ValueError, 'No ink'):
            trace_image(image)
        source, _ = trace_image(image, TraceOptions(invert=True))
        cleaned, _ = trace_image(image, TraceOptions(invert=True, despeckle=1))
        self.assertEqual(len(source), 2)
        self.assertEqual(len(cleaned), 1)
        self.assertTrue(all(.0 <= v <= 100 for s in source for p in s for v in p))

    def test_gaps_branches_and_holes_survive_tracing(self):
        image = Image.new('L', (100, 100), 255)
        draw = ImageDraw.Draw(image)
        draw.line((10, 10, 40, 10), fill=0)
        draw.line((45, 10, 90, 10), fill=0)
        drawing, _ = trace_image(image)
        self.assertEqual(len(drawing), 2)
        draw.line((10, 50, 90, 50), fill=0)
        draw.line((50, 50, 50, 90), fill=0)
        drawing, _ = trace_image(image)
        self.assertEqual(len(drawing), 5)
        ring = Image.new('L', (100, 100), 255)
        ImageDraw.Draw(ring).rectangle((10, 10, 90, 90), outline=0, width=5)
        outline, _ = trace_image(ring, TraceOptions(mode='Outline'))
        self.assertEqual(len(outline), 2)
        self.assertTrue(all(s[0] == s[-1] for s in outline))

    def test_limits_invalid_settings_and_cancellation_are_explicit(self):
        for kwargs in ({'threshold':0}, {'threshold':True}, {'resolution':4000},
                       {'despeckle':-1}, {'invert':1}, {'mode':'unknown'}):
            with self.assertRaises(ValueError):
                TraceOptions(**kwargs)
        cancel = Event(); cancel.set()
        with self.assertRaises(ImportCancelled):
            trace_image(self.line_image(), cancel=cancel)
        with patch('scrib3.raster.MAX_TRACE_NODES', 1), self.assertRaisesRegex(ValueError, 'complex'):
            trace_image(self.line_image())
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.png'
            path.write_text('not an image')
            with self.assertRaisesRegex(ValueError, 'Cannot decode'):
                load_raster(path)


class ConverterContractTests(TestCase):
    @skipUnless(os.environ.get('SCRIB3_NATIVE_IMPORT_TESTS') == '1', 'Native import acceptance job only')
    def test_native_acceptance_has_all_converters(self):
        import shutil
        for name in ('inkscape', 'dwg2dxf', 'gs'):
            self.assertIsNotNone(imports.find_converter(name), name)
        self.assertIsNotNone(shutil.which('dxf2dwg'))

    def test_dwg_conversion_uses_argument_list_isolated_paths_and_real_dxf_reader(self):
        import ezdxf
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'drawing ; special $.dwg'
            path.write_bytes(b'AC1027')
            def convert(args, work, cancel):
                self.assertEqual(args[0], '/tool/dwg2dxf')
                self.assertEqual(args[1], '-o')
                self.assertEqual(Path(args[-1]).name, 'input.dwg')
                self.assertNotEqual(Path(work), path.parent)
                doc = ezdxf.new(); doc.modelspace().add_line((1, 2), (3, 4))
                doc.saveas(args[2])
            with patch.object(imports, 'require_converter', return_value='/tool/dwg2dxf'), patch.object(imports, 'run_converter', side_effect=convert):
                result = read_artwork(path)
            self.assertEqual(result.drawing, (((1., -2.), (3., -4.)),))
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_missing_tools_bad_ai_and_conversion_failures_do_not_succeed(self):
        with patch.object(imports, 'find_converter', return_value=None):
            for name in ('inkscape', 'dwg2dxf', 'gs'):
                with self.assertRaisesRegex(ValueError, 'Install|requires'):
                    imports.require_converter(name)
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'private.ai'; path.write_bytes(b'private AI data')
            with self.assertRaisesRegex(ValueError, 'PDF Compatible'):
                read_artwork(path)
            with self.assertRaisesRegex(ValueError, 'no artwork'):
                imports._require_output(Path(folder) / 'missing.svg')
            import sys
            with self.assertRaisesRegex(ValueError, 'exit 3'):
                imports.run_converter([sys.executable, '-c', 'raise SystemExit(3)'], folder)
            with patch.object(imports, 'CONVERTER_TIMEOUT', .1), self.assertRaisesRegex(ValueError, 'timed out'):
                imports.run_converter([sys.executable, '-c', 'import time; time.sleep(10)'], folder)


@skipUnless(imports.find_converter('inkscape'), 'Native Inkscape converter not installed')
class NativePdfImportTests(TestCase):
    @skipUnless(imports.find_converter('gs'), 'Ghostscript not installed')
    def test_legacy_postscript_ai(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'legacy.ai'
            path.write_bytes(b'%!PS-Adobe-3.0\n%%Creator: Adobe Illustrator\n'
                             b'<< /PageSize [200 100] >> setpagedevice\n'
                             b'1 setlinewidth 10 10 moveto 190 90 lineto stroke showpage\n')
            result = read_artwork(path)
            self.assertEqual(len(result.drawing), 1)

    def test_pdf_and_pdf_compatible_ai_paths_and_page_selection(self):
        with TemporaryDirectory() as folder:
            pdf, ai = Path(folder) / 'drawing.pdf', Path(folder) / 'drawing.ai'
            write_pdf(pdf, [b'1 w 10 10 m 190 90 l S', b'1 w 10 10 30 30 re S'])
            ai.write_bytes(pdf.read_bytes())
            first, second = read_artwork(pdf), read_artwork(pdf, ImportOptions(page=2))
            self.assertEqual(first.drawing, read_artwork(ai).drawing)
            self.assertNotEqual(first.drawing[0][0], first.drawing[0][-1])
            self.assertEqual(second.drawing[0][0], second.drawing[0][-1])
            with self.assertRaisesRegex(ValueError, 'page.*not present'):
                read_artwork(pdf, ImportOptions(page=99))

    def test_pdf_text_and_clipped_art_have_an_explicit_rendered_trace(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'clipped.pdf'
            write_pdf(path, [b'q 10 10 40 40 re W n 1 w 0 0 m 200 100 l S Q BT /F1 12 Tf 70 30 Td (A) Tj ET'])
            with self.assertRaisesRegex(ValueError, 'Trace image'):
                read_artwork(path)
            result = read_artwork(path, ImportOptions('Trace image'))
            self.assertTrue(result.drawing)
            self.assertLessEqual(max(result.image.size), 1024)
            self.assertIn('rendered page', result.note)


@skipUnless(imports.find_converter('dwg2dxf') and __import__('shutil').which('dxf2dwg'), 'Native LibreDWG converters not installed')
class NativeDwgImportTests(TestCase):
    def test_real_dwg_roundtrip(self):
        import ezdxf
        import shutil
        with TemporaryDirectory() as folder:
            source, target = Path(folder) / 'source.dxf', Path(folder) / 'source.dwg'
            doc = ezdxf.new('R2000')
            doc.modelspace().add_line((1, 2), (3, 4))
            doc.modelspace().add_circle((10, 10), 2)
            doc.saveas(source)
            imports.run_converter([shutil.which('dxf2dwg'), '--as', 'r2000', '-o', str(target), str(source)], folder)
            drawing = read_artwork(target).drawing
            self.assertEqual(len(drawing), 2)
            self.assertEqual(drawing[0], ((1., -2.), (3., -4.)))
            self.assertEqual(drawing[1][0], drawing[1][-1])
