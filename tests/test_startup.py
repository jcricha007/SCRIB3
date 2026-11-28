"""Desktop startup and handoff to the two SCRIB3 windows."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
import tkinter as tk
from tkinter import ttk
from unittest import TestCase, skipUnless
from unittest.mock import patch

from scrib3 import branding, startup
from scrib3.app import Studio


@skipUnless(os.environ.get("SCRIB3_DESKTOP_TESTS") == "1", "Desktop display required")
class StartupTests(TestCase):
    def test_splash_hands_off_to_the_machine_and_board(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        observed = {}
        show_splash = branding.show_splash

        def time_splash(parent):
            splash = show_splash(parent)
            observed["painted_at"] = monotonic()
            return splash

        with TemporaryDirectory() as directory:
            def build_studio(parent):
                splash, = (child for child in parent.winfo_children() if isinstance(child, tk.Toplevel))
                observed["splash"] = splash
                observed["visible_during_load"] = splash.winfo_viewable()
                observed["machine_during_load"] = parent.state()
                observed["studio"] = Studio(parent, Path(directory) / "preset.json")
                return observed["studio"]

            def machine_mapped(event):
                if event.widget is root:
                    observed["opened_at"] = monotonic()
                    root.after_idle(root.quit)

            root.bind("<Map>", machine_mapped, add="+")
            timeout = root.after(15000, root.quit)
            with (patch.object(startup.tk, "Tk", return_value=root), patch("scrib3.app.Studio", build_studio),
                  patch.object(startup, "show_splash", time_splash)):
                startup.main()
            root.after_cancel(timeout)
            self.assertTrue(observed["visible_during_load"])
            self.assertEqual(observed["machine_during_load"], "withdrawn")
            self.assertFalse(observed["splash"].winfo_exists())
            self.assertTrue(root.winfo_viewable())
            self.assertGreaterEqual(observed["opened_at"] - observed["painted_at"], 5)

            studio = observed["studio"]
            self.assertEqual(studio.tabs.select(), str(studio.controls))
            self.assertIsNone(studio.controls.session)
            studio.show_board()
            for workspace in (studio.workbench, studio.board_editor):
                header = workspace.winfo_children()[0]
                wordmark, = (child for child in header.winfo_children()
                             if isinstance(child, ttk.Label) and child.cget("text") == "CRIB3")
                self.assertTrue(wordmark.cget("image"))

    def test_missing_artwork_preserves_the_text_header(self):
        root = tk.Tk()
        self.addCleanup(root.destroy)
        root.withdraw()
        with TemporaryDirectory() as directory, patch.object(branding, "ASSETS", Path(directory)):
            branding.set_window_icon(root)
            self.assertIsNone(branding.show_splash(root))
            label = branding.wordmark(root, style="TLabel", points=16)
            self.assertEqual(label.cget("text"), "SCRIB3")
            self.assertFalse(label.cget("image"))
