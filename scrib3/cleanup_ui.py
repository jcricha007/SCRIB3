"""Preview and commit line cleanup on a selection in physical paper units."""

from collections import defaultdict
from dataclasses import replace
from math import hypot, isfinite, sqrt
import tkinter as tk
from tkinter import ttk

from .board import bounds
from .preview_canvas import paint_paths
from .routing import joined_strokes_with_indices, stroke_key
from .toolpath import simplify_stroke


def smooth_path(points, tolerance):
    if not tolerance or len(points) < 3:
        return points
    anchors = {0, len(points) - 1}
    for axis in (0, 1):
        anchors.add(min(range(len(points)), key=lambda i: points[i][axis]))
        anchors.add(max(range(len(points)), key=lambda i: points[i][axis]))
    smoothed = list(points)
    for i in range(1, len(points) - 1):
        a, b, c = points[i - 1 : i + 2]
        u, v = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        if u[0] * v[0] + u[1] * v[1] <= hypot(*u) * hypot(*v) / sqrt(2):
            anchors.add(i)  # Keep turns of 45 degrees and sharper.
        if i not in anchors:
            dx, dy = (a[0] + c[0] - 2 * b[0]) / 4, (a[1] + c[1] - 2 * b[1]) / 4
            length = hypot(dx, dy)
            if length:
                k = min(1, tolerance / (2 * length))
                smoothed[i] = b[0] + k * dx, b[1] + k * dy
    kept = [points[0]]
    stops = sorted(anchors)
    for start, stop in zip(stops, stops[1:]):
        kept.extend(simplify_stroke(smoothed[start : stop + 1], tolerance / 2)[1:])
    if points[0] == points[-1] and len(set(kept)) < 3:
        return points
    return tuple(kept)


def clean_marks(marks, tolerance, remove, join):
    """Return one replacement or None for each input, preserving board stacking order."""
    if not isfinite(tolerance) or not 0 <= tolerance <= 5:
        raise ValueError("Use a smoothing tolerance from 0 to 5 mm.")
    buckets = defaultdict(list)
    for i, m in enumerate(marks):
        if not (m.text or m.controls):
            buckets[(m.color, m.groups, m.sheet_part)].append(i)
    changes = {}
    duplicates = 0
    for indices in buckets.values():
        seen, retained = set(), []
        for i in indices:
            p = marks[i].points
            key = stroke_key(p)
            duplicate = key in seen
            duplicates += int(duplicate)
            seen.add(key)
            if join:
                if not (remove and duplicate):
                    retained.append(i)
                changes[i] = None
            else:
                changes[i] = (
                    None
                    if remove and duplicate
                    else replace(marks[i], points=smooth_path(p, tolerance))
                )
        if join:
            paths = tuple(marks[i].points for i in retained)
            for index, points in joined_strokes_with_indices(paths):
                first = retained[index]
                changes[first] = replace(marks[first], points=smooth_path(points, tolerance))
    return tuple(changes.get(i, m) for i, m in enumerate(marks)), duplicates


class CleanupWindow:
    def __init__(self, editor):
        self.editor = editor
        self.source = editor.board
        self.revision = editor.revision
        self.indices = sorted(editor.board.text_selection(editor.selection))
        self.original = tuple(self.source.marks[i] for i in self.indices)
        self.window = tk.Toplevel(editor.root)
        self.window.title("SCRIB3 | Preview line cleanup")
        self.window.transient(editor.root)
        self.view = tk.Canvas(self.window, width=600, height=340, background="white")
        self.view.pack(fill="both", expand=True, padx=8, pady=8)
        options = ttk.Frame(self.window, padding=8)
        options.pack(fill="x")
        self.tolerance = tk.StringVar(value="0.05")
        self.width = tk.StringVar(value="0.35")
        self.remove = tk.BooleanVar(value=False)
        self.join = tk.BooleanVar(value=False)
        self.original_visible = tk.BooleanVar(value=True)
        for col, (label, v) in enumerate(
            (("Tolerance (mm)", self.tolerance), ("Pen width (mm)", self.width))
        ):
            ttk.Label(options, text=label).grid(row=0, column=2 * col)
            ttk.Entry(options, textvariable=v, width=8).grid(row=0, column=2 * col + 1)
        ttk.Checkbutton(options, text="Remove exact duplicates", variable=self.remove).grid(
            row=1, columnspan=2
        )
        ttk.Checkbutton(options, text="Join exact endpoints", variable=self.join).grid(
            row=1, column=2, columnspan=2
        )
        ttk.Checkbutton(
            options,
            text="Overlay original (orange)",
            variable=self.original_visible,
            command=self.draw,
        ).grid(row=2, columnspan=2)
        self.status = tk.StringVar()
        ttk.Label(self.window, textvariable=self.status, wraplength=600).pack(anchor="w", padx=12)
        buttons = ttk.Frame(self.window, padding=8)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Preview", command=self.update).pack(side="left")
        ttk.Button(buttons, text="Fit view", command=self.fit).pack(side="left")
        ttk.Button(buttons, text="Cancel", command=self.window.destroy).pack(side="right")
        ttk.Button(buttons, text="Apply", command=self.apply).pack(side="right")
        self.after_id = None
        self.result = None
        self.zoom, self.center, self.mapping = 1, None, None
        self.box = bounds(self.original)
        self.view.bind("<Configure>", lambda e: self.draw())
        self.view.bind("<MouseWheel>", lambda e: self.wheel(e, 1.4 if e.delta > 0 else 1 / 1.4))
        self.view.bind("<Button-4>", lambda e: self.wheel(e, 1.4))
        self.view.bind("<Button-5>", lambda e: self.wheel(e, 1 / 1.4))
        for v in (self.tolerance, self.width, self.remove, self.join):
            v.trace_add("write", self.schedule)
        self.window.bind("<Destroy>", self.closed)
        self.update()

    def closed(self, event):
        if event.widget == self.window and self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None

    def schedule(self, *_):
        if self.after_id:
            self.window.after_cancel(self.after_id)
        self.after_id = self.window.after(200, self.update)

    def update(self):
        if self.after_id:
            self.window.after_cancel(self.after_id)
            self.after_id = None
        try:
            width = float(self.width.get())
            if not 0.01 <= width <= 10:
                raise ValueError("Use a pen width from 0.01 to 10 mm.")
            self.replacements, duplicates = clean_marks(
                self.original, float(self.tolerance.get()), self.remove.get(), self.join.get()
            )
            result = tuple(m for m in self.replacements if m is not None)
        except ValueError as exc:
            self.result = None
            self.view.delete("all")
            self.status.set(str(exc))
            return
        self.result, self.pen_width = result, width
        points = lambda marks: sum(len(m.points) for m in marks)
        self.status.set(
            f"Points {points(self.original):,} → {points(result):,}    "
            f"Between-stroke lifts {len(self.original) - 1} → {max(0, len(result) - 1)}    "
            f"Exact repeats {duplicates}.  Cleaned paths in blue."
        )
        self.draw()

    def fit(self):
        self.zoom, self.center = 1, None
        self.draw()

    def wheel(self, event, factor):
        if self.mapping:
            cx, cy, k = self.mapping
            mouse = (
                (event.x - self.view.winfo_width() / 2) / k,
                (event.y - self.view.winfo_height() / 2) / k,
            )
            new = min(64, max(1, self.zoom * factor))
            self.center = (
                cx + mouse[0] * (1 - self.zoom / new),
                cy + mouse[1] * (1 - self.zoom / new),
            )
            self.zoom = new
            if new == 1:
                self.center = None
            self.draw()

    def draw(self):
        if self.result is not None:
            layers = [(self.original, "#bd6936", 2)] if self.original_visible.get() else []
            layers.append((self.result, "#164c85", 0))
            self.mapping = paint_paths(
                self.view, layers, self.box, self.zoom, self.center, self.pen_width
            )

    def apply(self):
        if self.editor.revision != self.revision:
            self.status.set("The board changed. Reopen cleanup for the current artwork.")
            return
        self.update()
        if self.result is None:
            return
        if self.result != self.original:
            changes = dict(zip(self.indices, self.replacements))
            marks, indices = [], []
            for index, original in enumerate(self.source.marks):
                mark = changes.get(index, original)
                if mark is not None:
                    if index in changes:
                        indices.append(len(marks))
                    marks.append(mark)
            try:
                self.editor.commit(replace(self.source, marks=tuple(marks)), indices)
            except ValueError as exc:
                self.status.set(str(exc))
                return
        self.window.destroy()
