import os
from pathlib import Path
from tempfile import TemporaryDirectory
import tkinter as tk
from unittest import TestCase, skipUnless

from scrib3.drawing import Sheet, fit_to_sheet
from scrib3.gcode import Machine, generate_gcode
from scrib3.lettering import FONTS, add_caption, lettering
from scrib3.vector_io import read_drawing, write_drawing


class LetteringTests(TestCase):
    def test_all_printable_glyphs_have_strokes_and_repeat_exactly(self):
        for font in FONTS:
            for char in map(chr, range(33, 127)):
                drawing = lettering(char, font)
                self.assertTrue(drawing, (font, char))
                self.assertEqual(drawing, lettering(char, font))
        # A consists of two legs and a crossbar, without an outlined silhouette.
        self.assertEqual(len(lettering('A')), 3)

    def test_multiline_alignment_tracking_and_explicit_missing_symbols(self):
        left = lettering('A\nAA')
        center = lettering('A\nAA', alignment='Center')
        self.assertNotEqual(left, center)
        a = lettering('A')
        spaced = lettering('A A', tracking=2)
        self.assertGreater(spaced[len(a)][0][0]-a[0][0][0], 20)
        for text in ('', '   ', '\t', 'Diameter: \u2300', 'A'*301, 'X\x7f'):
            with self.assertRaises(ValueError):
                lettering(text)
        for kwargs in ({'tracking': float('nan')}, {'line_spacing': 0}, {'font': 'missing'}):
            with self.assertRaises(ValueError):
                lettering('ABC', **kwargs)

    def test_caption_preserves_original_strokes_and_bounds_gap(self):
        source = (((10, 20), (110, 20), (110, 70), (10, 20)),)
        result = add_caption(source, lettering('TEST'), 4)
        self.assertEqual(result[:len(source)], source)
        self.assertAlmostEqual(min(y for s in result[1:] for x, y in s), 74)
        self.assertAlmostEqual(max(y for s in result[1:] for x, y in s), 78)
        with self.assertRaises(ValueError):
            add_caption(source, lettering('ABC'), float('inf'))

    def test_vector_exports_and_gcode_keep_glyph_pen_lifts(self):
        sheet = Sheet(100, 80, 5)
        drawing = fit_to_sheet(lettering('SCRIB3\nA-Z 0123'), sheet)
        with TemporaryDirectory() as folder:
            for ext in ('svg', 'json', 'dxf'):
                file = Path(folder) / ('text.'+ext)
                write_drawing(file, drawing, sheet)
                self.assertEqual(len(read_drawing(file)), len(drawing))
        program = generate_gcode(drawing, sheet, Machine(100, 100, 1000, 'M3 S180', 'M3 S70'))
        self.assertEqual(sum(line.startswith('G0 X') for line in program.splitlines()), len(drawing))


@skipUnless(os.environ.get('SCRIB3_DESKTOP_TESTS') == '1', 'Desktop display required')
class LetteringDesktopTests(TestCase):
    def test_preview_apply_undo_invalidation_and_compact_layout(self):
        from scrib3.app import Studio
        from scrib3.lettering_ui import LetteringWindow
        with TemporaryDirectory() as folder:
            root = tk.Tk()
            errors = []
            root.report_callback_exception = lambda *args: errors.append(str(args))
            app = Studio(root, Path(folder)/'prefs.json')
            app.tabs.select(app.design_tab)
            win = LetteringWindow(app)
            try:
                root.update()
                original = app.source
                win.preview()
                self.assertEqual(app.source, original)
                self.assertTrue(win.draft)
                win.placement.set('Caption below drawing')
                self.assertIsNone(win.draft)
                win.preview(); win.apply()
                self.assertEqual(app.source[:len(original)], original)
                app.undo_design()
                self.assertEqual(app.source, original)
                win.preview()
                app.create_pattern()
                changed = app.source
                win.apply()
                self.assertEqual(app.source, changed)
                self.assertIn('changed', win.status.get())
                win.preview()
                win.text.insert('end', '\u2300')
                # Signature validation also catches edits before Tk emits Modified.
                win.apply()
                self.assertEqual(app.source, changed)
                root.update(); win.preview()
                self.assertIn('Unsupported', win.status.get())
                win.window.geometry('620x560'); root.geometry('800x650'); root.update()
                self.assertGreater(win.canvas.winfo_height(), 50)
                for widget, parent in ((win.apply_button, win.window), (app.lettering_button, root)):
                    self.assertTrue(widget.winfo_viewable())
                    self.assertLessEqual(widget.winfo_rooty()+widget.winfo_height(), parent.winfo_rooty()+parent.winfo_height())
                self.assertFalse(errors, errors)
            finally:
                win.close(); app.shutdown()
                for callback in root.tk.call('after', 'info'):
                    root.tk.call('after', 'cancel', callback)
                root.destroy()
