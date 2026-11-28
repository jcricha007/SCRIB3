"""Third-angle poster sheets from a single mesh and a shared physical scale."""

from dataclasses import replace
from math import isfinite, sqrt
from queue import Queue, Empty
from threading import Event, Thread
import tkinter as tk
from tkinter import ttk
from uuid import uuid4

import numpy as np
from . import theme
from .board import Board, Mark, PAPER, DEFAULT_PEN, bounds
from .creator import load_mesh, project_mesh
from .geometry import shape, check_size
from .poster_objects import StrokeText
from .preview_canvas import paint_paths

VIEW_GROUP = "Engineering views"
FRAME_GROUP = "Sheet furniture"
VIEWS = {
    "Top": np.eye(3),
    "Isometric": np.array(
        (
            (1 / sqrt(2), 1 / sqrt(2), 0),
            (-1 / sqrt(6), 1 / sqrt(6), 2 / sqrt(6)),
            (1 / sqrt(3), -1 / sqrt(3), 1 / sqrt(3)),
        )
    ),
    "Front": np.array(((1, 0, 0), (0, 0, 1), (0, -1, 0))),
    "Right": np.array(((0, 1, 0), (0, 0, 1), (1, 0, 0))),
}


def project_views(mesh, cancel=None):
    center = np.mean(mesh.bounds, axis=0)
    views = {}
    for name, rotation in VIEWS.items():
        if cancel and cancel():
            raise ValueError("Sheet projection cancelled.")
        try:
            marks = project_mesh(mesh, rotation, "Visible edges", cancel)
        except ValueError as exc:
            # A flat part can have an empty edge-on view.
            if "no edges" not in str(exc).lower() and "no visible" not in str(exc).lower():
                raise
            marks = ()
        x, y, _ = map(float, rotation @ center)
        views[name] = tuple(
            replace(m, points=tuple((px - x, py + y) for px, py in m.points)) for m in marks
        )
        check_size(tuple(m for view in views.values() for m in view))
    if not any(views.values()):
        raise ValueError("The model has no visible edges.")
    return views


def sheet_text(value, x, y, height, groups, color):
    spec = StrokeText(
        uuid4().hex, value=value, height=height, frame=((x, y), (x + 1, y), (x, y + 1))
    )
    marks = spec.marks(color, groups)
    # Place the visible lettering at the requested top-left.
    x0, y0, _, _ = bounds(marks)
    return Board(marks=marks).transform(range(len(marks)), dx=x - x0, dy=y - y0).marks


def lay_out(views, width, height, title, scale=None, frame=True, color=DEFAULT_PEN):
    cell_w, cell_h = (width - 20) / 2, (height - 30) / 2
    if cell_w < 30 or cell_h < 22:
        raise ValueError("Choose a larger sheet.")
    limits = []
    for marks in views.values():
        if marks:
            x0, y0, x1, y1 = bounds(marks)
            for extent, capacity in (
                (2 * max(abs(x0), abs(x1)), cell_w - 10),
                (2 * max(abs(y0), abs(y1)), cell_h - 14),
            ):
                if extent:
                    limits.append(capacity / extent)
    maximum = min(limits)
    if scale is None:
        scale = maximum
    if not isfinite(scale) or not 0 < scale <= maximum + 1e-9:
        raise ValueError(f"Scale must fit all views (maximum {maximum:.5g} mm per model unit).")
    marks = []
    for i, name in enumerate(VIEWS):
        col, row = i % 2, i // 2
        cx, cy = 10 + (col + 0.5) * cell_w, 7 + (row + 0.5) * cell_h - 3
        group = (VIEW_GROUP, name)
        for m in views[name]:
            marks.append(
                Mark(color, tuple((cx + x * scale, cy + y * scale) for x, y in m.points), group)
            )
        marks.extend(
            sheet_text(
                name.upper(), 12 + col * cell_w, 7 + (row + 1) * cell_h - 6, 2.5, group, color
            )
        )
    if frame:
        group = (FRAME_GROUP,)
        marks.append(Mark(color, shape("Rectangle", (6, 6), (width - 6, height - 6)), group))
        marks.append(Mark(color, ((6, height - 21), (width - 6, height - 21)), group))
        title_marks = sheet_text(title.strip() or "DRAWING", 10, height - 17, 4, group, color)
        if bounds(title_marks)[2] > width - 10:
            raise ValueError("Shorten the title to fit the sheet.")
        marks.extend(title_marks)
    parts = tuple(
        replace(m, sheet_part="frame" if m.groups == (FRAME_GROUP,) else "view") for m in marks
    )
    return Board(width, height, parts).checked(), scale


class SheetWindow:
    def __init__(self, editor, path):
        self.editor, self.revision = editor, editor.revision
        self.window = tk.Toplevel(editor.root)
        self.window.title("SCRIB3 | Engineering drawing sheet")
        self.window.transient(editor.root)
        self.canvas = tk.Canvas(self.window, background=theme.PAPER, width=650, height=360, highlightthickness=1, highlightbackground=theme.BORDER)
        self.canvas.pack(fill="both", expand=True)
        panel = ttk.Frame(self.window, padding=8)
        panel.pack(fill="x")
        self.paper = tk.StringVar(value="Current paper")
        self.view = tk.StringVar(value="Four-view sheet")
        self.scale = tk.StringVar()
        self.title = tk.StringVar(value=path.stem)
        self.frame = tk.BooleanVar(
            value=not any(m.sheet_part == "frame" for m in editor.board.marks)
        )
        for col, (label, variable, values) in enumerate(
            (
                ("Paper", self.paper, ("Current paper", "A4", "Letter")),
                ("Preview", self.view, ("Four-view sheet", *VIEWS)),
            )
        ):
            ttk.Label(panel, text=label).grid(row=0, column=2 * col)
            ttk.Combobox(
                panel, textvariable=variable, values=values, width=16, state="readonly"
            ).grid(row=0, column=2 * col + 1)
        ttk.Label(panel, text="Title").grid(row=1, column=0)
        ttk.Entry(panel, textvariable=self.title).grid(row=1, column=1)
        ttk.Label(panel, text="mm / model unit (blank = fit)").grid(row=1, column=2)
        ttk.Entry(panel, textvariable=self.scale, width=12).grid(row=1, column=3)
        ttk.Checkbutton(panel, text="Generate border and title block", variable=self.frame).grid(
            row=2, columnspan=3, sticky="w"
        )
        self.status = tk.StringVar(value="Projecting visible edges…")
        ttk.Label(panel, textvariable=self.status, wraplength=480).grid(
            row=3, columnspan=3, sticky="w"
        )
        self.add = ttk.Button(panel, text="Apply four views", style="Primary.TButton", command=self.apply, state="disabled")
        self.add.grid(row=3, column=3)
        self.views = self.result = None
        for v in (self.paper, self.scale, self.title, self.frame):
            v.trace_add("write", self.update)
        self.view.trace_add("write", self.draw)
        self.canvas.bind("<Configure>", self.draw)
        self.cancel = Event()
        q = Queue()

        def worker():
            try:
                q.put((project_views(load_mesh(path), self.cancel.is_set), ""))
            except Exception as exc:
                q.put((None, str(exc)))

        Thread(target=worker, daemon=True).start()
        self.poll_id = None

        def poll():
            self.poll_id = None
            try:
                self.views, error = q.get_nowait()
            except Empty:
                self.poll_id = self.window.after(80, poll)
                return
            if error:
                self.status.set(error)
            else:
                self.update()

        def close(event):
            if event.widget == self.window:
                self.cancel.set()
                if self.poll_id is not None:
                    self.window.after_cancel(self.poll_id)
                    self.poll_id = None

        self.window.bind("<Destroy>", close)
        poll()

    def update(self, *_):
        if self.views is None:
            return
        try:
            w, h = PAPER.get(self.paper.get(), (self.editor.board.width, self.editor.board.height))
            value = self.scale.get().strip()
            self.result, scale = lay_out(
                self.views,
                w,
                h,
                self.title.get(),
                float(value) if value else None,
                self.frame.get(),
                self.editor.pen.get(),
            )
            self.status.set(f"Shared scale {scale:.5g} mm per model unit.")
            self.add.state(["!disabled"])
        except (ValueError, TypeError) as exc:
            self.result = None
            self.add.state(["disabled"])
            self.status.set(str(exc))
        self.draw()

    def draw(self, *_):
        self.canvas.delete("all")
        if self.result:
            view = self.view.get()
            full = view == "Four-view sheet"
            marks = (
                self.result.marks
                if full
                else tuple(m for m in self.result.marks if m.groups == (VIEW_GROUP, view))
            )
            bbox = (0, 0, self.result.width, self.result.height) if full else None
            paint_paths(self.canvas, [(marks, None, 0)], bbox)

    def apply(self):
        if self.editor.revision != self.revision:
            self.status.set("The board changed. Reopen the sheet builder.")
            return
        if self.result is None:
            return
        current = self.editor.board
        replacing = {"view", "frame"} if self.frame.get() else {"view"}
        remove = [m for m in current.marks if m.sheet_part in replacing]
        protected = current.hidden | current.locked
        if any(m.color in protected for m in (*remove, *self.result.marks)):
            self.status.set("Show and unlock the affected pens first.")
            return
        keep = tuple(m for m in current.marks if m.sheet_part not in replacing)
        try:
            board = replace(
                current,
                width=self.result.width,
                height=self.result.height,
                marks=keep + self.result.marks,
            )
            self.editor.commit(board, range(len(keep), len(board.marks)))
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self.window.destroy()
