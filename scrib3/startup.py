"""Show the desktop splash while the studio loads."""

import tkinter as tk
from math import ceil
from time import monotonic

from .branding import set_window_icon, show_splash

MIN_SPLASH_SECONDS = 5


def main(connect: str | None = None, baud: int | None = None) -> None:
    root = tk.Tk()
    root.withdraw()
    try:
        set_window_icon(root)
        splash = show_splash(root)
        reveal_at = monotonic() + MIN_SPLASH_SECONDS if splash is not None else 0
        from .app import Studio

        studio = Studio(root)
    except Exception:
        root.destroy()
        raise

    def open_workspace():
        root.deiconify()
        if splash is not None:
            splash.destroy()
        if connect is not None:
            studio.tabs.select(studio.controls)
            if connect == "auto" or baud is None:
                root.after(100, lambda: studio.controls.auto_detect(
                    port=None if connect == "auto" else connect, baud=baud))
            else:
                studio.port.set(connect)
                studio.baud.set(str(baud))
                root.after(100, studio.controls.connect)

    root.after(max(0, ceil((reveal_at - monotonic()) * 1000)), open_workspace)
    root.mainloop()
