"""Interactive board workspace for paper layout and individual pen passes."""

from dataclasses import replace
from math import atan2, ceil, degrees, hypot
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, colorchooser, messagebox, simpledialog
from xml.etree.ElementTree import ParseError

from .board import (
    Board,
    Mark,
    PAPER,
    DEFAULT_PEN,
    bezier,
    bounds,
    export_svg,
    import_svg,
    load_board,
    save_board,
    shape,
)
from .artwork_import import IMPORT_FORMATS, CONVERSION_EXTENSIONS
from .import_ui import ImportWindow
from .lettering import lettering
from .vector_io import read_drawing
from .drawing import path_lengths
from .units import to_mm


class BoardEditor(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent)
        self.studio, self.root = studio, studio.root
        self.board = self.saved = Board()
        self.path = None
        self.revision = 0
        self.history, self.future = [], []
        self.selection = set()
        self.zoom, self.pan = 1, (0, 0)
        self.drag = None
        self.control_points = []
        self.after_preview = None
        self.progress = None
        self.tool = tk.StringVar(value="Select")
        self.tool.trace_add("write", self.tool_changed)
        self.pen = tk.StringVar(value=DEFAULT_PEN)
        self.grid_on = tk.BooleanVar(value=True)
        self.snap = tk.BooleanVar(value=False)
        self.actual = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Drag to select paths or import artwork.")
        self.info = tk.StringVar()
        self.name = tk.StringVar(value="Untitled board")
        bar = ttk.Frame(self, padding=(10, 6))
        bar.pack(fill="x")
        ttk.Label(bar, text="SCRIB3", style="Title.TLabel").pack(side="left", padx=(0, 12))
        self.menu(
            bar,
            "Board",
            [
                ("Plotter workbench", studio.show_workbench),
                ("Add workbench drawing", self.add_workbench),
                ("New", self.new),
                ("Open…", self.open),
                ("Save", self.save),
                ("Save as…", lambda: self.save(True)),
                ("Export visible SVG…", self.export),
                ("Export active pen SVG…", lambda: self.export(active=True)),
            ],
        )
        self.button(bar, "Import…", self.import_file)
        self.menu(
            bar,
            "Edit",
            [
                ("Undo", lambda: self.undo(False)),
                ("Redo", lambda: self.undo(True)),
                ("Select all", self.all),
                ("Duplicate", self.duplicate),
                ("Delete", self.delete),
            ],
        )
        self.menu(
            bar,
            "Paper",
            [(n, lambda p=p: self.paper(*p)) for n, p in PAPER.items()]
            + [
                ("Swap orientation", lambda: self.paper(self.board.height, self.board.width)),
                ("Custom size…", self.custom),
            ],
        )
        self.menu(
            bar,
            "Bed",
            [
                ("Paper only", lambda: self.bed(None)),
                ("A1 mini (180 x 180 mm)", lambda: self.bed((180, 180))),
                ("A1 / P1 / P2S / X1C / X2D (256 x 256 mm)", lambda: self.bed((256, 256))),
                ("A2L (330 x 320 mm)", lambda: self.bed((330, 320))),
                ("H2S · 340 × 320 mm", lambda: self.bed((340, 320))),
                ("Custom bed…", self.custom_bed),
            ],
        )
        self.menu(
            bar,
            "View",
            [
                ("Zoom in", lambda: self.zoom_by(1.25)),
                ("Zoom out", lambda: self.zoom_by(0.8)),
                ("Fit view", self.reset_view),
                ("Play / stop preview", self.play),
            ],
        )
        ttk.Label(bar, textvariable=self.name).pack(side="left", padx=12)
        ttk.Button(
            bar,
            text="Review GRBL pen pass",
            style="Primary.TButton",
            command=lambda: studio.review(board_editor=self),
        ).pack(side="right")
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        rail = ttk.Frame(body, padding=(6, 8))
        rail.pack(side="left", fill="y")
        for mode in (
            "Select",
            "Pan",
            "Freehand",
            "Bézier",
            "Line",
            "Rectangle",
            "Ellipse",
            "Pentagon",
            "Star",
            "Eraser",
        ):
            ttk.Radiobutton(
                rail, text=mode, value=mode, variable=self.tool, style="TRadiobutton"
            ).pack(fill="x", pady=2)
        self.button(rail, "Text…", self.text, "top")
        inspector = ttk.Frame(body, padding=(10, 8))
        inspector.pack(side="right", fill="y")
        ttk.Label(inspector, text="Pen layers", style="Title.TLabel").pack(anchor="w")
        self.layers = tk.Listbox(
            inspector, height=4, width=22, exportselection=False, activestyle="none"
        )
        self.layers.pack(fill="x", pady=6)
        self.layers.bind("<<ListboxSelect>>", self.select_layer)
        self.layer_info = tk.StringVar()
        ttk.Label(inspector, textvariable=self.layer_info).pack(anchor="w")
        self.menu(
            inspector,
            "Layer actions",
            [
                ("Choose drawing pen…", self.choose_pen),
                ("Select layer paths", self.select_paths),
                ("Recolor selected…", self.recolor),
                ("Show / hide", lambda: self.toggle("hidden")),
                ("Lock / unlock", lambda: self.toggle("locked")),
            ],
            side="top",
        )
        ttk.Label(inspector, text="Selection", style="Title.TLabel").pack(anchor="w", pady=(16, 4))
        for title, fn in [
            ("Select all", self.all),
            ("Scale…", self.scale),
            ("Rotate…", self.rotate),
            ("Center on paper", lambda: self.transform(center=True)),
            ("Fit to paper", lambda: self.transform(fit=True)),
            ("Delete selected", self.delete),
        ]:
            self.button(inspector, title, fn, "top")
        self.menu(
            inspector,
            "Fill selected",
            [
                (mode, lambda m=mode: self.hatch(m))
                for mode in ("Horizontal", "Vertical", "Diagonal", "Crosshatch")
            ],
            side="top",
        )
        self.menu(
            inspector,
            "Align to paper",
            [(edge, lambda e=edge: self.align(e)) for edge in ("Left", "Right", "Top", "Bottom")],
            side="top",
        )
        for label, var in [
            ("Grid and rulers", self.grid_on),
            ("Snap to 1 mm", self.snap),
            ("True-size SVG import", self.actual),
        ]:
            ttk.Checkbutton(inspector, text=label, variable=var, command=self.paint).pack(
                anchor="w", pady=2
            )
        self.canvas = tk.Canvas(body, bg="#18202c", highlightthickness=0, takefocus=True)
        self.canvas.pack(side="left", expand=True, fill="both")
        for ev, fn in [
            ("<Configure>", lambda e: self.paint()),
            ("<Button-1>", self.press),
            ("<B1-Motion>", self.motion),
            ("<ButtonRelease-1>", self.release),
            ("<MouseWheel>", lambda e: self.zoom_by(1.25 if e.delta > 0 else 0.8)),
            ("<Control-a>", lambda e: self.all()),
            ("<Delete>", lambda e: self.delete()),
            ("<BackSpace>", lambda e: self.delete()),
            ("<Control-z>", lambda e: self.undo(False)),
            ("<Control-y>", lambda e: self.undo(True)),
            ("<Escape>", lambda e: self.cancel_drag()),
        ]:
            self.canvas.bind(ev, fn)
        footer = ttk.Frame(self, padding=6)
        footer.pack(side="bottom", fill="x", before=body)
        ttk.Label(footer, textvariable=self.status).pack(side="left")
        ttk.Label(footer, textvariable=self.info).pack(side="right")
        self.style_board(bar, rail, inspector, footer)
        self.sync()

    def style_board(self, *panels):
        style = ttk.Style(self)
        dark = "#202938"
        light = "#e8eef5"
        accent = "#91d9ea"
        for kind in ("TFrame", "TLabel", "TButton", "TMenubutton", "TRadiobutton", "TCheckbutton"):
            name = "Board." + kind
            style.configure(
                name,
                background=dark,
                foreground=light,
                bordercolor="#384556",
                lightcolor=dark,
                darkcolor=dark,
                focuscolor=accent,
            )
            style.map(name, background=[("active", "#364657")], foreground=[("active", "white")])
        style.configure(
            "Board.Title.TLabel",
            foreground=accent,
            background=dark,
            font=(self.studio.ui_font, 11, "bold"),
        )
        for frame in panels:
            frame.configure(style="Board.TFrame")
            for widget in frame.winfo_children():
                kind = widget.winfo_class()
                if kind == "Listbox":
                    widget.configure(
                        bg="#17212e",
                        fg=light,
                        selectbackground="#365366",
                        selectforeground="white",
                        highlightthickness=0,
                        bd=0,
                    )
                elif kind in ("TLabel", "TButton", "TMenubutton", "TRadiobutton", "TCheckbutton"):
                    current = widget.cget("style")
                    if current != "Primary.TButton":
                        widget.configure(
                            style=(
                                "Board.Title.TLabel"
                                if current == "Title.TLabel"
                                else "Board." + kind
                            )
                        )

    def button(self, bar, text, fn, side="left"):
        ttk.Button(bar, text=text, command=lambda: self.guard(fn)).pack(
            side=side, fill="x" if side == "top" else "none", padx=1, pady=1
        )

    def menu(self, bar, text, items, side="left"):
        b = ttk.Menubutton(bar, text=text)
        m = tk.Menu(b, tearoff=False)
        for label, fn in items:
            m.add_command(label=label, command=lambda f=fn: self.guard(f))
        b.configure(menu=m)
        b.pack(side=side, fill="x" if side == "top" else "none", padx=1)

    def guard(self, fn):
        try:
            return fn()
        except (ValueError, OSError, ParseError) as e:
            messagebox.showerror("Board", str(e), parent=self.root)

    def commit(self, state, selection=None):
        state.checked()
        if state == self.board:
            return
        self.history = (self.history + [self.board])[-24:]
        self.future.clear()
        self.board = state
        self.selection = set(selection or ())
        self.revision += 1
        self.stop()
        self.sync()

    def undo(self, redo):
        src, dst = (self.future, self.history) if redo else (self.history, self.future)
        if src:
            dst.append(self.board)
            self.board = src.pop()
            self.selection.clear()
            self.revision += 1
            self.stop()
            self.sync()

    def discard(self):
        if self.board == self.saved:
            return True
        answer = messagebox.askyesnocancel(
            "Save board", "Save changes to this board?", parent=self.root
        )
        return answer is False or (answer is True and self.guard(self.save))

    def reset(self, state, path):
        self.stop()
        self.board = self.saved = state
        self.path = path
        self.revision += 1
        self.drag = None
        self.control_points.clear()
        self.selection.clear()
        self.history.clear()
        self.future.clear()
        self.reset_view()
        self.sync()

    def new(self):
        if self.discard():
            self.reset(Board(), None)

    def open(self):
        p = filedialog.askopenfilename(parent=self.root, filetypes=[("SCRIB3 board", "*.scrib3")])
        if p:
            state = load_board(Path(p))
            if self.discard():
                self.reset(state, Path(p))

    def save(self, as_new=False):
        p = self.path
        if as_new or not p:
            name = filedialog.asksaveasfilename(
                parent=self.root,
                defaultextension=".scrib3",
                filetypes=[("SCRIB3 board", "*.scrib3")],
            )
            if not name:
                return False
            p = Path(name)
        save_board(p, self.board)
        self.saved = self.board
        self.path = p
        self.sync()
        self.status.set("Board saved.")
        return True

    def export(self, active=False):
        board = self.board
        if active:
            board.plot_layer(self.pen.get())
            board = replace(board, marks=tuple(m for m in board.marks if m.color == self.pen.get()))
        p = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".svg", filetypes=[("Editable SVG", "*.svg")]
        )
        if p:
            export_svg(Path(p), board)
            self.status.set("SVG exported at board size.")

    def import_file(self):
        f = filedialog.askopenfilename(parent=self.root, filetypes=IMPORT_FORMATS)
        if not f:
            return
        p = Path(f)
        if p.suffix.lower() == ".svg":
            marks = import_svg(p, (self.board.width, self.board.height))
            self.insert(marks, fit=not self.actual.get(), placed=self.actual.get())
        elif p.suffix.lower() in CONVERSION_EXTENSIONS:
            self.studio.import_windows = [w for w in self.studio.import_windows if not w.closed]
            self.studio.import_windows.append(ImportWindow(self, p))
        else:
            self.set_drawing(p.stem, read_drawing(p))

    def set_drawing(self, name, source):
        self.insert(tuple(Mark(self.pen.get(), s) for s in source), fit=True)
        self.status.set(f"Added {name}.")

    def add_workbench(self):
        self.studio.refresh()
        # Both editors use millimetres. The workbench uses an upward Y axis.
        height = self.studio.sheet.height
        marks = tuple(
            Mark(self.pen.get(), tuple((x, height - y) for x, y in stroke))
            for stroke in self.studio.fitted
        )
        self.insert(marks)
        self.status.set("Added the workbench drawing at its current physical size.")

    def insert(self, marks, fit=False, placed=False):
        if not marks:
            raise ValueError("There are no paths to add.")
        start = len(self.board.marks)
        ids = range(start, start + len(marks))
        if any(m.color in self.board.locked | self.board.hidden for m in marks):
            raise ValueError("Show and unlock the destination pens first.")
        b = replace(self.board, marks=self.board.marks + marks).checked()
        if not placed:
            b = b.transform(ids, fit=fit, center=True)
        self.pen.set(marks[0].color)
        self.commit(b, ids)

    def paper(self, w, h):
        self.commit(replace(self.board, width=w, height=h), self.selection)

    def custom(self):
        w = simpledialog.askfloat(
            "Paper",
            "Width (mm)",
            initialvalue=self.board.width,
            parent=self.root,
            minvalue=1,
            maxvalue=10000,
        )
        if w is not None:
            h = simpledialog.askfloat(
                "Paper",
                "Height (mm)",
                initialvalue=self.board.height,
                parent=self.root,
                minvalue=1,
                maxvalue=10000,
            )
            if h is not None:
                self.paper(w, h)

    def text(self):
        s = simpledialog.askstring("Stroke lettering", "Text", parent=self.root)
        if s:
            h = simpledialog.askfloat(
                "Stroke lettering",
                "Capital height (mm)",
                initialvalue=8,
                minvalue=0.2,
                maxvalue=1000,
                parent=self.root,
            )
            if h:
                self.insert(
                    tuple(
                        Mark(self.pen.get(), tuple((x * h / 21, y * h / 21) for x, y in path))
                        for path in lettering(s)
                    )
                )

    def colors(self):
        return list(dict.fromkeys([*(m.color for m in self.board.marks), self.pen.get()]))

    def layer_metrics(self):
        moves = tuple(m.points for m in self.board.marks if m.color == self.pen.get())
        drawn, travel = path_lengths(moves)
        try:
            rate = to_mm(self.studio.feed.get(), self.studio.unit)
            minutes = drawn / rate if rate > 0 else 0
        except (ValueError, AttributeError):
            minutes = 0
        self.layer_info.set(
            f"{drawn/1000:.2f} m ink" + (f"  ·  {minutes:.1f} min drawing" if minutes else "")
        )

    def choose_pen(self):
        color = colorchooser.askcolor(self.pen.get(), parent=self.root)[1]
        if color:
            self.pen.set(color.lower())
            self.sync()

    def select_layer(self, _):
        pick = self.layers.curselection()
        if pick:
            self.pen.set(self.colors()[pick[0]])
            self.layer_metrics()

    def editable(self, i):
        return self.board.marks[i].color not in self.board.hidden | self.board.locked

    def select_paths(self):
        self.selection = {
            i
            for i, m in enumerate(self.board.marks)
            if m.color == self.pen.get() and self.editable(i)
        }
        self.sync()

    def toggle(self, key):
        self.commit(replace(self.board, **{key: getattr(self.board, key) ^ {self.pen.get()}}))

    def recolor(self):
        if not self.selection:
            return
        c = colorchooser.askcolor(self.pen.get(), parent=self.root)[1]
        if c:
            c = c.lower()
            if c in self.board.hidden | self.board.locked:
                raise ValueError("Show and unlock the destination pen first.")
            self.pen.set(c)
            self.commit(
                replace(
                    self.board,
                    marks=tuple(
                        replace(m, color=c) if i in self.selection else m
                        for i, m in enumerate(self.board.marks)
                    ),
                ),
                self.selection,
            )

    def all(self):
        self.selection = {i for i in range(len(self.board.marks)) if self.editable(i)}
        self.sync()
        return "break"

    def duplicate(self):
        add = tuple(
            replace(m, points=tuple((x + 2, y + 2) for x, y in m.points))
            for i, m in enumerate(self.board.marks)
            if i in self.selection
        )
        self.commit(
            replace(self.board, marks=self.board.marks + add),
            range(len(self.board.marks), len(self.board.marks) + len(add)),
        )

    def delete(self):
        if self.selection:
            self.commit(
                replace(
                    self.board,
                    marks=tuple(
                        m for i, m in enumerate(self.board.marks) if i not in self.selection
                    ),
                )
            )

    def transform(self, **params):
        self.commit(self.board.transform(self.selection, **params), self.selection)

    def scale(self):
        n = simpledialog.askfloat(
            "Scale selection",
            "Scale (%)",
            initialvalue=100,
            minvalue=0.01,
            maxvalue=10000,
            parent=self.root,
        )
        if n:
            self.transform(factor=n / 100)

    def rotate(self):
        n = simpledialog.askfloat(
            "Rotate selection", "Clockwise degrees", initialvalue=90, parent=self.root
        )
        if n:
            self.transform(angle=n)

    def align(self, edge):
        if not self.selection:
            return
        x0, y0, x1, y1 = bounds(self.board.marks[i] for i in self.selection)
        dx = {"Left": -x0, "Right": self.board.width - x1}.get(edge, 0)
        dy = {"Top": -y0, "Bottom": self.board.height - y1}.get(edge, 0)
        self.transform(dx=dx, dy=dy)

    def hatch(self, mode):
        from .board import hatch

        pitch = simpledialog.askfloat(
            "Hatch selection",
            "Line spacing (mm)",
            initialvalue=1,
            minvalue=0.15,
            maxvalue=100,
            parent=self.root,
        )
        if pitch:
            marks = hatch([self.board.marks[i] for i in sorted(self.selection)], pitch, mode)
            self.commit(replace(self.board, marks=self.board.marks + marks), self.selection)

    def sync(self):
        self.layers.delete(0, "end")
        counts = {}
        for m in self.board.marks:
            counts[m.color] = counts.get(m.color, 0) + 1
        for i, c in enumerate(self.colors()):
            flag = (
                "hidden" if c in self.board.hidden else "locked" if c in self.board.locked else ""
            )
            self.layers.insert("end", f"{c}   {counts.get(c,0)}   {flag}")
            if c == self.pen.get():
                self.layers.selection_set(i)
        self.layer_metrics()
        self.name.set(
            (self.path.stem if self.path else "Untitled board")
            + (" *" if self.board != self.saved else "")
        )
        self.info.set(
            f"{self.board.width:g} × {self.board.height:g} mm   |   {len(self.board.marks)} paths   |   {len(self.selection)} selected"
        )
        self.paint()

    def reset_view(self):
        self.pan = (0, 0)
        self.zoom = 1
        self.paint()

    def zoom_by(self, k):
        self.zoom = max(0.25, min(12, self.zoom * k))
        self.paint()

    def point(self, e):
        x, y = (e.x - self.left) / self.k, (e.y - self.top) / self.k
        return (round(x), round(y)) if self.snap.get() else (x, y)

    def paint(self):
        cv = self.canvas
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if min(w, h) < 50:
            return
        b = self.board
        bw, bh = b.bed or (b.width, b.height)
        k = self.k = max(
            0.001, min((w - 48) / max(bw, b.width), (h - 48) / max(bh, b.height)) * self.zoom
        )
        l = self.left = (w - b.width * k) / 2 + self.pan[0]
        t = self.top = (h - b.height * k) / 2 + self.pan[1]
        if b.bed:
            dx = (bw - b.width) * k / 2
            dy = (bh - b.height) * k / 2
            cv.create_rectangle(
                l - dx,
                t - dy,
                l + b.width * k + dx,
                t + b.height * k + dy,
                fill="#303c4b",
                outline="#7991a7",
            )
        cv.create_rectangle(
            l, t, l + b.width * k, t + b.height * k, fill="#fafbfd", outline="#79899b"
        )
        if self.grid_on.get():
            step = 10
            while step * k < 30:
                step *= 2
            for x in range(0, ceil(b.width), step):
                px = l + x * k
                if 0 <= px <= w:
                    cv.create_line(px, t, px, t + b.height * k, fill="#e0e6ec")
                    cv.create_text(
                        px, t - 9, text=str(x), fill="#b0bcca", font=("TkDefaultFont", 8)
                    )
            for y in range(0, ceil(b.height), step):
                py = t + y * k
                if 0 <= py <= h:
                    cv.create_line(l, py, l + b.width * k, py, fill="#e0e6ec")
                    cv.create_text(
                        l - 3,
                        py,
                        text=str(y),
                        anchor="e",
                        fill="#b0bcca",
                        font=("TkDefaultFont", 8),
                    )
        for i, m in enumerate(b.marks):
            if self.progress is not None and i >= self.progress:
                break
            if m.color in b.hidden:
                continue
            coords = [v for x, y in m.points for v in (l + x * k, t + y * k)]
            cv.create_line(
                *coords,
                fill="#1288ad" if i in self.selection else m.color,
                width=2 if i in self.selection else 1.4,
                tags=(f"p{i}", "art"),
            )
        if self.control_points:
            handles = [(l + x * k, t + y * k) for x, y in self.control_points]
            if len(handles) > 1:
                cv.create_line(*[v for pt in handles for v in pt], fill="#087a9b", dash=(2, 2))
            for x, y in handles:
                cv.create_oval(x - 3, y - 3, x + 3, y + 3, fill="#087a9b", outline="")
        if self.selection:
            a, b, c, d = bounds(self.board.marks[i] for i in self.selection)
            cv.create_rectangle(
                l + a * k,
                t + b * k,
                l + c * k,
                t + d * k,
                outline="#0087a8",
                dash=(5, 3),
                tags="selection",
            )

            right, bottom = l + c * k, t + d * k
            middle, top = l + (a + c) * k / 2, t + b * k
            cv.create_rectangle(
                right - 4,
                bottom - 4,
                right + 4,
                bottom + 4,
                fill="#0087a8",
                outline="white",
                tags=("selection", "Scale"),
            )
            cv.create_line(middle, top, middle, top - 15, fill="#0087a8", tags="selection")
            cv.create_oval(
                middle - 5,
                top - 20,
                middle + 5,
                top - 10,
                fill="#0087a8",
                outline="white",
                tags=("selection", "Rotate"),
            )

    def handle_transform(self, mode, start, end):
        x0, y0, x1, y1 = bounds(self.board.marks[i] for i in self.selection)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        x, y = start[0] - cx, start[1] - cy
        u, v = end[0] - cx, end[1] - cy
        if mode == "Scale":
            return {"factor": max(0.001, hypot(u, v) / max(0.0001, hypot(x, y)))}
        return {"angle": degrees(atan2(v, u) - atan2(y, x))}

    def hit(self, e):
        for item in reversed(self.canvas.find_overlapping(e.x - 4, e.y - 4, e.x + 4, e.y + 4)):
            tags = self.canvas.gettags(item)
            if "art" in tags:
                i = int(tags[0][1:])
                if self.editable(i):
                    return i
        return None

    def press(self, e):
        self.canvas.focus_set()
        self.stop()
        if not hasattr(self, "k"):
            return
        mode = self.tool.get()
        p = self.point(e)
        if mode == "Select" and self.selection:
            for item in self.canvas.find_overlapping(e.x - 2, e.y - 2, e.x + 2, e.y + 2):
                tags = self.canvas.gettags(item)
                if "Scale" in tags or "Rotate" in tags:
                    self.drag = (
                        "Scale" if "Scale" in tags else "Rotate",
                        p,
                        [],
                        (e.x, e.y),
                        self.pan,
                    )
                    return
        idx = self.hit(e)
        if mode == "Eraser":
            if idx is not None:
                self.selection = {idx}
                self.delete()
            return
        if mode == "Select":
            if idx is not None:
                if e.state & 1:
                    self.selection ^= {idx}
                elif idx not in self.selection:
                    self.selection = {idx}
                mode = "Move"
            else:
                if not e.state & 1:
                    self.selection.clear()
                mode = "Box"
            self.sync()
        if mode == "Bézier":
            if self.pen.get() in self.board.hidden | self.board.locked:
                self.status.set("Show and unlock the active pen to draw.")
                return
            self.control_points.append(p)
            if len(self.control_points) == 4:
                pts = bezier(self.control_points)
                self.control_points.clear()
                self.guard(
                    lambda: self.commit(
                        replace(self.board, marks=self.board.marks + (Mark(self.pen.get(), pts),))
                    )
                )
            else:
                self.status.set(
                    (
                        "Click first control point.",
                        "Click second control point.",
                        "Click end point.",
                    )[len(self.control_points) - 1]
                )
            self.paint()
            return
        self.drag = (mode, p, [p], (e.x, e.y), self.pan)

    def motion(self, e):
        if not self.drag:
            return
        mode, start, trail, (sx, sy), pan = self.drag
        cv = self.canvas
        cv.delete("draft")
        p = self.point(e)
        if mode == "Pan":
            self.pan = (pan[0] + e.x - sx, pan[1] + e.y - sy)
            self.paint()
            return
        if mode in ("Scale", "Rotate"):
            cv.create_line(sx, sy, e.x, e.y, fill="#0798ba", dash=(4, 2), tags="draft")
            params = self.handle_transform(mode, start, p)
            self.status.set(
                f"Scale {params['factor']*100:.1f}%"
                if mode == "Scale"
                else f"Rotate {params['angle']:.1f} degrees"
            )
            return
        if mode == "Move":
            for i in self.selection:
                cv.move(f"p{i}", e.x - sx, e.y - sy)
            cv.move("selection", e.x - sx, e.y - sy)
            self.drag = (mode, start, trail, (e.x, e.y), pan)
            return
        if mode == "Box":
            cv.create_rectangle(sx, sy, e.x, e.y, outline="#0798ba", dash=(4, 2), tags="draft")
            return
        if (
            mode == "Freehand"
            and hypot(p[0] - trail[-1][0], p[1] - trail[-1][1]) * self.k >= 2
            and len(trail) < 10000
        ):
            trail.append(p)
        pts = shape(mode, start, p, trail)
        cv.create_line(
            *[v for x, y in pts for v in (self.left + x * self.k, self.top + y * self.k)],
            fill=self.pen.get(),
            tags="draft",
        )

    def release(self, e):
        if not self.drag:
            return
        mode, start, trail, _, _ = self.drag
        self.drag = None
        p = self.point(e)
        self.canvas.delete("draft")
        if mode == "Pan":
            return
        if mode == "Box":
            x0, x1 = sorted((start[0], p[0]))
            y0, y1 = sorted((start[1], p[1]))
            for i, m in enumerate(self.board.marks):
                if self.editable(i) and all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in m.points):
                    self.selection.add(i)
            self.sync()
            return
        if mode in ("Scale", "Rotate"):
            if p != start:
                self.guard(lambda: self.transform(**self.handle_transform(mode, start, p)))
            self.paint()
            return
        if mode == "Move":
            if self.selection and p != start:
                self.guard(lambda: self.transform(dx=p[0] - start[0], dy=p[1] - start[1]))
            self.paint()
            return
        if self.pen.get() in self.board.hidden | self.board.locked:
            self.status.set("Show and unlock the active pen to draw.")
            return
        pts = shape(mode, start, p, trail)
        if len(set(pts)) > 1:
            self.guard(
                lambda: self.commit(
                    replace(self.board, marks=self.board.marks + (Mark(self.pen.get(), pts),))
                )
            )
        self.paint()

    def cancel_drag(self):
        self.drag = None
        self.control_points.clear()
        self.paint()

    def tool_changed(self, *_):
        self.cancel_drag()
        self.status.set(
            "Click start, two control points, then end."
            if self.tool.get() == "Bézier"
            else self.tool.get()
        )

    def bed(self, size):
        self.commit(replace(self.board, bed=size), self.selection)
        self.reset_view()

    def custom_bed(self):
        w = simpledialog.askfloat(
            "Bed guide", "Bed width (mm)", parent=self.root, minvalue=1, maxvalue=10000
        )
        if w:
            h = simpledialog.askfloat(
                "Bed guide", "Bed depth (mm)", parent=self.root, minvalue=1, maxvalue=10000
            )
            if h:
                self.bed((w, h))

    def stop(self):
        if self.after_preview is not None:
            self.after_cancel(self.after_preview)
            self.after_preview = None
        if self.progress is not None:
            self.progress = None
            self.paint()

    def play(self):
        if self.progress is not None:
            self.stop()
            return
        self.control_points.clear()
        self.selection.clear()
        self.progress = 0
        self.sync()

        def advance():
            if self.progress >= len(self.board.marks):
                self.stop()
                return
            self.progress += max(1, len(self.board.marks) // 150)
            self.paint()
            self.after_preview = self.after(35, advance)

        advance()
