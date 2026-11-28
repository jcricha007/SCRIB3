"""Artwork shared by the startup screen and the two desktop workspaces."""

from pathlib import Path
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk


ASSETS = Path(__file__).with_name("assets")


def _logo_photo(master, logo, pixels, ink=None):
    scaled = logo.resize((pixels, pixels), Image.Resampling.LANCZOS)
    if ink is not None:
        tinted = Image.new("RGBA", scaled.size, ink)
        tinted.putalpha(scaled.getchannel("A"))
        scaled = tinted
    return ImageTk.PhotoImage(scaled, master=master)


def wordmark(parent, *, style, points, ink=None):
    label = ttk.Label(parent, text="SCRIB3", style=style)
    try:
        with Image.open(ASSETS / "logo.png") as logo:
            pixels = max(1, parent.winfo_pixels(f"{points}p"))
            label.mark = _logo_photo(parent, logo.convert("RGBA"), pixels, ink)
        label.configure(image=label.mark, text="CRIB3", compound="left")
    except (OSError, tk.TclError):
        pass  # Keep the text wordmark if the artwork is unavailable.
    return label


def set_window_icon(root):
    try:
        with Image.open(ASSETS / "logo.png") as source:
            logo = source.convert("RGBA")
            icons = [_logo_photo(root, logo, size) for size in (256, 64, 32, 16)]
        root.iconphoto(True, *icons)
    except (OSError, tk.TclError):
        pass  # Window managers can supply their own icon.


def show_splash(root):
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
    try:
        with Image.open(ASSETS / "splash.jpg") as artwork:
            artwork.thumbnail((min(800, screen_width * 9 // 10),
                               min(450, screen_height * 4 // 5)), Image.Resampling.LANCZOS)
            image = ImageTk.PhotoImage(artwork, master=root)
    except (OSError, tk.TclError):
        return None

    width, height = image.width(), image.height()
    left, top = (screen_width - width) // 2, (screen_height - height) // 2
    window = tk.Toplevel(root)
    window.withdraw()
    window.title("SCRIB3")
    window.overrideredirect(True)
    window.geometry(f"{width}x{height}+{left}+{top}")
    label = tk.Label(window, image=image, borderwidth=0, highlightthickness=0, padx=0, pady=0)
    label.image = image
    label.pack()
    window.deiconify()
    window.lift()
    # Paint the splash before importing the drawing and machine workspaces.
    if not window.winfo_viewable():
        window.wait_visibility()
    window.update()
    return window
