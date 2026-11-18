import os
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from time import monotonic, sleep
import tkinter as tk
from unittest import TestCase, skipUnless
from unittest.mock import patch

from PIL import Image, ImageDraw
from scrib3.app import Studio
from scrib3.artwork_import import ImportResult
from scrib3.import_ui import ImportWindow


@skipUnless(os.environ.get('SCRIB3_DESKTOP_TESTS') == '1', 'Desktop display required')
class ImportDesktopTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.root = tk.Tk()
        self.errors = []
        self.root.report_callback_exception = lambda *args: self.errors.append(str(args))
        self.app = Studio(self.root, preset_file=Path(self.folder.name) / 'prefs.json')
        self.path = Path(self.folder.name) / 'lines.png'
        image = Image.new('RGB', (100, 70), 'white')
        ImageDraw.Draw(image).line((10, 30, 90, 30), fill='black', width=5)
        image.save(self.path)
        self.windows = []
        self.root.update()

    def tearDown(self):
        for window in self.windows + self.app.import_windows:
            window.close()
        for callback in self.root.tk.call('after', 'info'):
            self.root.tk.call('after', 'cancel', callback)
        self.root.destroy()
        self.folder.cleanup()
        self.assertFalse(self.errors, self.errors)

    def wait(self, condition):
        deadline = monotonic() + 12
        while monotonic() < deadline:
            self.root.update()
            if condition():
                return
            sleep(.01)
        self.fail('Import preview timed out')

    def test_png_dialog_previews_without_mutating_and_apply_is_undoable(self):
        original = self.app.source
        with patch('scrib3.app.filedialog.askopenfilename', return_value=str(self.path)) as choose:
            self.app.import_drawing()
        filters = ' '.join(pattern for _, pattern in choose.call_args.kwargs['filetypes'])
        for ext in ('svg', 'ai', 'dwg', 'psd', 'pdf', 'png'):
            self.assertIn('*.' + ext, filters)
        window = self.app.import_windows[-1]
        self.wait(lambda: not window.busy)
        self.assertIsNotNone(window.draft, window.status.get())
        self.assertEqual(self.app.source, original)
        self.assertTrue(window.canvases[0].find_all())
        self.assertTrue(window.canvases[1].find_all())
        draft = window.draft.drawing
        window.window.geometry('800x620'); self.root.update()
        self.assertLessEqual(window.apply_button.winfo_rootx() + window.apply_button.winfo_width(),
                             window.window.winfo_rootx() + window.window.winfo_width())
        self.assertLessEqual(window.apply_button.winfo_rooty() + window.apply_button.winfo_height(),
                             window.window.winfo_rooty() + window.window.winfo_height())
        window.apply()
        self.assertEqual(self.app.source, draft)
        self.assertTrue(window.closed)
        self.app.undo_design()
        self.assertEqual(self.app.source, original)

    def test_changed_settings_or_workspace_invalidate_preview(self):
        window = ImportWindow(self.app, self.path); self.windows.append(window)
        self.wait(lambda: not window.busy)
        window.threshold.set('100')
        self.assertIsNone(window.draft)
        self.assertTrue(window.apply_button.instate(['disabled']))
        window.preview(); self.wait(lambda: not window.busy)
        self.app.create_pattern()
        changed = self.app.source
        window.apply()
        self.assertEqual(self.app.source, changed)
        self.assertIsNone(window.draft)
        self.assertIn('workspace drawing changed', window.status.get())

    def test_cancellation_late_results_and_errors_leave_workspace_intact(self):
        original = self.app.source
        entered, release = Event(), Event()
        def slow(*args):
            entered.set(); release.wait(5)
            return ImportResult((((0., 0.), (1., 1.)),), 'delayed')
        with patch('scrib3.import_ui.read_artwork', side_effect=slow):
            window = ImportWindow(self.app, self.path); self.windows.append(window)
            self.wait(entered.is_set)
            window.cancel_work(); release.set()
            self.wait(lambda: not window.busy)
            self.assertIsNone(window.draft)
            self.assertTrue(window.apply_button.instate(['disabled']))
        with patch('scrib3.import_ui.read_artwork', side_effect=ValueError('Converter unavailable')):
            window.preview(); self.wait(lambda: not window.busy)
            self.assertIn('Converter unavailable', window.status.get())
            self.assertIsNone(window.draft)
        self.assertEqual(self.app.source, original)
