"""Paper layout, vector drawing and color-pass editing workspace."""

from dataclasses import replace
from math import atan2, degrees, hypot
from pathlib import Path
from uuid import uuid4
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from xml.etree.ElementTree import ParseError

from .board import Board, Mark, DEFAULT_PEN, PAPER, bounds, save_board, load_board, export_svg
from .branding import wordmark
from .geometry import shape, hatch, offset, array
from .svg_artwork import import_svg
from .lettering import FONTS, ALIGNMENTS
from .poster_objects import StrokeText, cubic_points, independent_copy, unused_group


def form(parent, title, fields):
    """Return named values from a small modal property editor, or None."""
    window = tk.Toplevel(parent)
    window.title(title)
    window.transient(parent)
    panel = ttk.Frame(window, padding=14)
    panel.pack(fill="both", expand=True)
    variables = {}
    result = []
    for i, (key, label, value) in enumerate(fields):
        ttk.Label(panel, text=label).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=4)
        options = value if isinstance(value, tuple) else None
        var = tk.StringVar(value=options[0] if options else str(value))
        variables[key] = var
        widget = (
            ttk.Combobox(panel, textvariable=var, values=options, state="readonly", width=28)
            if options
            else ttk.Entry(panel, textvariable=var, width=30)
        )
        widget.grid(row=i, column=1, sticky="ew")

    def accept():
        result.append({k: v.get() for k, v in variables.items()})
        window.destroy()

    ttk.Button(panel, text="Apply", command=accept).grid(
        row=len(fields), column=1, sticky="e", pady=(10, 0)
    )
    window.bind("<Return>", lambda e: accept())
    window.bind("<Escape>", lambda e: window.destroy())
    window.grab_set()
    parent.wait_window(window)
    return result[0] if result else None


class CanvasEditor(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent)
        self.studio = studio
        self.root = parent.winfo_toplevel()
        self.board = self.saved = Board()
        self.path = None
        self.history = []
        self.future = []
        self.selection = set()
        self.revision = 0
        self.pen = tk.StringVar(value=DEFAULT_PEN)
        self.mode = tk.StringVar(value="Select")
        self.grid = tk.BooleanVar(value=True)
        self.snap = tk.BooleanVar(value=False)
        self.zoom = 1.0
        self.pan = (0, 0)
        self.drag = None
        self.preview = None
        self.timer = None
        self.bezier_points = []
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")
        wordmark(bar, style="Title.TLabel", points=18, ink="#93c5fd").pack(side="left", padx=8)
        self.menu(
            bar,
            "Board",
            [
                ("New", self.new),
                ("Open", self.open),
                ("Save", self.save),
                ("Save as", lambda: self.save(True)),
                ("Export SVG", self.export),
                ("Export active pen SVG", lambda: self.export(True)),
                ("Add workbench artwork", self.add_workbench),
                ("Save sheet template…", lambda: self.save_asset(template=True)),
                ("New from template…", lambda: self.open_asset(template=True)),
                ("Machine & calibration", studio.show_workbench),
            ],
        )
        self.menu(
            bar,
            "Import",
            [
                ("SVG / vector / image", self.import_file),
                ("Photo art", self.photo),
                ("3D model", self.mesh),
                ("Engineering drawing sheet…", self.engineering_sheet),
                ("Saved element…", self.open_asset),
                ("GeoJSON map", self.map),
            ],
        )
        self.menu(
            bar,
            "Edit",
            [
                ("Undo", self.undo),
                ("Redo", lambda: self.undo(True)),
                ("Select all", self.all),
                ("Preview line cleanup…", self.clean),
                ("Name group…", self.group),
                ("Select named group…", self.select_group),
                ("Edit lettering…", lambda: self.text(edit=True)),
                ("Save selection as element…", self.save_asset),
                ("Duplicate", self.duplicate),
                ("Delete", self.delete),
            ],
        )
        self.menu(
            bar,
            "Paper",
            [
                (n, lambda size=v: self.commit(replace(self.board, width=size[0], height=size[1])))
                for n, v in PAPER.items()
            ]
            + [
                (
                    "Swap orientation",
                    lambda: self.commit(
                        replace(self.board, width=self.board.height, height=self.board.width)
                    ),
                ),
                ("Custom size", self.paper),
            ],
        )
        self.menu(
            bar,
            "Bed",
            [
                ("Paper only", lambda: self.bed(None)),
                ("P1S (256 x 256 mm)", lambda: self.bed((256, 256))),
                ("H2S (340 x 320 mm)", lambda: self.bed((340, 320))),
                ("Custom bed", self.custom_bed),
            ],
        )
        self.menu(
            bar,
            "Create",
            [
                ("Text", self.text),
                ("Pattern", self.pattern),
                ("QR code", self.qr),
                ("Linear / radial array", self.array),
                ("Offset contours", self.offset),
            ],
        )
        self.menu(
            bar,
            "Output",
            [
                ("Current pen to GRBL", lambda: studio.review(board_editor=self)),
                ("All pens to GRBL", self.run_passes),
                ("Bambu P1S", lambda: self.printer("P1S")),
                ("Bambu H2S", lambda: self.printer("H2S")),
                ("Play / stop", self.play),
            ],
        )
        footer = ttk.Frame(self, padding=6)
        footer.pack(side="bottom", fill="x")
        self.status = tk.StringVar(value="Import artwork or draw on the paper.")
        ttk.Label(footer, textvariable=self.status).pack(side="left")
        self.info = tk.StringVar()
        ttk.Label(footer, textvariable=self.info).pack(side="right")
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        rail = ttk.Frame(body, padding=6)
        rail.pack(side="left", fill="y")
        for tool in (
            "Select",
            "Pan",
            "Freehand",
            "Bezier",
            "Edit nodes",
            "Line",
            "Rectangle",
            "Ellipse",
            "Star",
            "Pentagon",
            "Eraser",
        ):
            ttk.Radiobutton(rail, text=tool, value=tool, variable=self.mode).pack(
                anchor="w", pady=3
            )
        side = ttk.Frame(body, padding=8)
        side.pack(side="right", fill="y")
        ttk.Label(side, text="Pen layers", style="Title.TLabel").pack(anchor="w")
        self.layers = tk.Listbox(
            side, width=23, height=5, exportselection=False, bg="#1c2938", fg="white", bd=0
        )
        self.layers.pack(fill="x", pady=6)
        self.layers.bind("<<ListboxSelect>>", self.layer_selected)
        self.menu(
            side,
            "Layer actions",
            [
                ("Choose drawing pen", self.choose_pen),
                ("Select pen paths", self.select_pen),
                ("Recolor selected", self.recolor),
                ("Hide / show", lambda: self.flag("hidden")),
                ("Lock / unlock", lambda: self.flag("locked")),
                ("Move pen earlier", lambda: self.reorder(-1)),
                ("Move pen later", lambda: self.reorder(1)),
            ],
            side="top",
        )
        ttk.Label(side, text="Selection", style="Title.TLabel").pack(anchor="w", pady=(12, 5))
        for text, fn in [
            ("Select all", self.all),
            ("Transform", self.transform_dialog),
            ("Rotate 90°", lambda: self.transform(angle=90)),
            ("Center", lambda: self.transform(center=True)),
            ("Fit to paper", lambda: self.transform(fit=True)),
            ("Delete", self.delete),
        ]:
            ttk.Button(side, text=text, command=lambda f=fn: self.guard(f)).pack(fill="x", pady=2)
        self.menu(
            side,
            "Fill selected",
            [
                (s, lambda mode=s: self.fill(mode))
                for s in ("Horizontal", "Vertical", "Diagonal", "Crosshatch", "Concentric")
            ],
            side="top",
        )
        self.menu(
            side,
            "Align to paper",
            [(s, lambda edge=s: self.align(edge)) for s in ("Left", "Right", "Top", "Bottom")],
            side="top",
        )
        ttk.Checkbutton(side, text="Grid", variable=self.grid, command=self.paint).pack(
            anchor="w", pady=(12, 0)
        )
        ttk.Checkbutton(side, text="Snap to 1 mm", variable=self.snap).pack(anchor="w")
        ttk.Button(side, text="Fit view", command=self.reset_view).pack(fill="x", pady=6)
        self.canvas = tk.Canvas(body, bg="#17212e", highlightthickness=0, takefocus=True)
        self.canvas.pack(fill="both", expand=True)
        events = {
            "<Configure>": lambda e: self.paint(),
            "<Button-1>": self.press,
            "<B1-Motion>": self.motion,
            "<ButtonRelease-1>": self.release,
            "<MouseWheel>": lambda e: self.zoom_by(1.2 if e.delta > 0 else 1 / 1.2),
            "<Button-4>": lambda e: self.zoom_by(1.2),
            "<Button-5>": lambda e: self.zoom_by(1 / 1.2),
            "<Control-a>": lambda e: self.all(),
            "<Delete>": lambda e: self.delete(),
            "<Control-z>": lambda e: self.undo(),
            "<Control-y>": lambda e: self.undo(True),
            "<Escape>": lambda e: self.cancel(),
        }
        if self.root.tk.call("tk", "windowingsystem") == "aqua":
            events.update({"<Command-a>": lambda e: self.all(), "<Command-z>": lambda e: self.undo(),
                           "<Command-Shift-Z>": lambda e: self.undo(True), "<BackSpace>": lambda e: self.delete()})
        for ev, fn in events.items():
            self.canvas.bind(ev, lambda e, f=fn: self.guard(lambda: f(e)))
        style = ttk.Style(self.root)
        for cls in ("TFrame", "TLabel", "TButton", "TMenubutton", "TRadiobutton", "TCheckbutton"):
            style.configure(
                "Canvas." + cls, background="#202c3a", foreground="#e4edf6", bordercolor="#425064"
            )
            style.map(
                "Canvas." + cls,
                background=[("active", "#34485d")],
                foreground=[("active", "white")],
            )
        style.configure(
            "Canvas.Title.TLabel",
            background="#202c3a",
            foreground="#d8e9fa",
            font=(studio.ui_font, 11, "bold"),
        )

        def restyle(widget):
            cls = widget.winfo_class()
            if cls in (
                "TFrame",
                "TLabel",
                "TButton",
                "TMenubutton",
                "TRadiobutton",
                "TCheckbutton",
            ):
                widget.configure(
                    style=(
                        "Canvas.Title.TLabel"
                        if widget.cget("style") == "Title.TLabel"
                        else "Canvas." + cls
                    )
                )
            for child in widget.winfo_children():
                restyle(child)

        restyle(self)
        self.sync()
        self.mode.trace_add("write", lambda *_: self.cancel())
        self.pen.trace_add("write", studio.queue_board_preview)

    def guard(self, fn):
        try:
            return fn()
        except (ValueError, OSError, ParseError, TypeError) as e:
            messagebox.showerror("SCRIB3", str(e), parent=self.root)

    def menu(self, parent, text, items, side="left"):
        b = ttk.Menubutton(parent, text=text)
        m = tk.Menu(b, tearoff=False)
        for label, fn in items:
            m.add_command(label=label, command=lambda f=fn: self.guard(f))
        b.configure(menu=m)
        b.pack(side=side, fill="x" if side == "top" else "none", padx=2, pady=2)

    def commit(self, board, selection=None):
        board.checked()
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.preview = None
        if board != self.board:
            self.history = (self.history + [self.board])[-32:]
            self.future.clear()
            self.board = board
            self.revision += 1
        self.selection = board.text_selection(selection or ())
        self.sync()

    def undo(self, redo=False):
        self.cancel()
        source, dest = (self.future, self.history) if redo else (self.history, self.future)
        if source:
            dest.append(self.board)
            self.board = source.pop()
            self.selection.clear()
            self.revision += 1
            self.sync()

    def discard(self):
        if self.board == self.saved:
            return True
        answer = messagebox.askyesnocancel(
            "Save board", "Save this board before continuing?", parent=self.root
        )
        return answer is False or answer is True and self.save()

    def new(self):
        if self.discard():
            self.load(Board(), None)

    def load(self, board, path):
        self.cancel()
        self.board = self.saved = board
        self.path = path
        self.history.clear()
        self.future.clear()
        self.selection.clear()
        self.revision += 1
        self.reset_view()
        self.sync()

    def open(self):
        target = filedialog.askopenfilename(
            parent=self.root, filetypes=[("SCRIB3 board", "*.scrib3")]
        )
        if target:
            board = load_board(Path(target))
            if self.discard():
                self.load(board, Path(target))

    def save(self, as_new=False):
        target = self.path
        if target is None or as_new:
            target = filedialog.asksaveasfilename(
                parent=self.root,
                defaultextension=".scrib3",
                filetypes=[("SCRIB3 board", "*.scrib3")],
            )
        if target:
            save_board(Path(target), self.board)
            self.path = Path(target)
            self.saved = self.board
            self.studio.queue_board_preview()
            self.status.set("Board saved.")
            return True
        return False

    def export(self, active=False):
        b = self.board
        if active:
            b = replace(b, marks=tuple(m for m in b.marks if m.color == self.pen.get()))
        target = filedialog.asksaveasfilename(
            parent=self.root, defaultextension=".svg", filetypes=[("SVG", "*.svg")]
        )
        if target:
            export_svg(Path(target), b)
            self.status.set("SVG exported at paper size.")

    def import_file(self):
        from .artwork_import import IMPORT_FORMATS, CONVERSION_EXTENSIONS
        from .import_ui import ImportWindow
        from .vector_io import read_drawing

        target = filedialog.askopenfilename(parent=self.root, filetypes=IMPORT_FORMATS)
        if not target:
            return
        p = Path(target)
        if p.suffix.lower() == ".svg":
            opts = form(
                self.root,
                "SVG import",
                [
                    ("size", "Placement", ("Keep SVG page coordinates", "Center at true size", "Fit to paper")),
                    ("fill", "Fill", ("Outline", "Horizontal", "Crosshatch", "Concentric")),
                    ("spacing", "Fill spacing mm", 1),
                    ("covered", "Covered lines", ("Hide", "Keep")),
                ],
            )
            if opts:
                self.insert(
                    import_svg(
                        p,
                        fill=opts["fill"],
                        spacing=float(opts["spacing"]),
                        hide_covered=opts["covered"] == "Hide",
                    ),
                    fit=opts["size"] == "Fit to paper",
                    placed=opts["size"] == "Keep SVG page coordinates",
                )
        elif p.suffix.lower() in CONVERSION_EXTENSIONS:
            self.studio.import_windows.append(ImportWindow(self, p))
        else:
            self.set_drawing(p.stem, read_drawing(p))

    def set_drawing(self, name, source):
        self.insert(tuple(Mark(self.pen.get(), s) for s in source), fit=True)
        self.status.set("Added " + name)

    def insert(self, marks, fit=False, placed=False):
        if not marks:
            raise ValueError("No paths to add.")
        if any(m.color in self.board.hidden | self.board.locked for m in marks):
            raise ValueError("Show and unlock the destination pen layers first.")
        marks = independent_copy(marks, self.board.marks)
        start = len(self.board.marks)
        ids = range(start, start + len(marks))
        b = replace(self.board, marks=self.board.marks + tuple(marks)).checked()
        if not placed:
            b = b.transform(ids, fit=fit, center=True)
        self.pen.set(marks[0].color)
        self.commit(b, ids)

    def add_workbench(self):
        self.studio.refresh()
        h = self.studio.sheet.height
        self.insert(
            tuple(Mark(self.pen.get(), tuple((x, h - y) for x, y in s)) for s in self.studio.fitted)
        )

    def all(self):
        self.selection = {
            i
            for i, m in enumerate(self.board.marks)
            if m.color not in self.board.hidden | self.board.locked
        }
        self.paint()

    def selected(self):
        return tuple(
            self.board.marks[i]
            for i in sorted(self.selection)
            if self.board.marks[i].color not in self.board.hidden | self.board.locked
        )

    def delete(self):
        self.commit(
            replace(
                self.board,
                marks=tuple(m for i, m in enumerate(self.board.marks) if i not in self.selection),
            )
        )

    def clean(self):
        from .cleanup_ui import CleanupWindow
        if not self.selected():
            raise ValueError("Select paths to clean.")
        return CleanupWindow(self)

    def group(self):
        selected = self.board.text_selection(self.selection)
        if not selected:
            raise ValueError("Select artwork to group.")
        values = form(self.root, "Name group", [("name", "Group name", "Artwork")])
        if values:
            taken = {m.groups[0] for m in self.board.marks if m.groups}
            name = unused_group(values["name"], taken)
            marks = tuple(replace(m, groups=(name, *m.groups)) if i in selected else m
                          for i, m in enumerate(self.board.marks))
            self.commit(replace(self.board, marks=marks), selected)

    def select_group(self):
        groups = sorted({m.groups[:depth] for m in self.board.marks
                         if m.color not in self.board.hidden | self.board.locked
                         for depth in range(1, len(m.groups) + 1)})
        if not groups:
            raise ValueError("No visible unlocked groups on this board.")
        choices = {f"{i + 1}. " + " / ".join(g): g for i, g in enumerate(groups)}
        values = form(self.root, "Select group", [("name", "Group", tuple(choices))])
        if values:
            group = choices[values["name"]]
            self.selection = self.board.text_selection(
                i for i, m in enumerate(self.board.marks) if m.groups[:len(group)] == group)
            self.paint()

    def asset_folder(self, template):
        path = self.studio.preset_file.parent / ("templates" if template else "elements")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_asset(self, template=False):
        if template:
            marks = tuple(m for m in self.board.marks if m.sheet_part != "view")
        else:
            marks = self.selected()
            if not marks:
                raise ValueError("Select the element to save.")
        title = "Save sheet template" if template else "Save reusable element"
        path = filedialog.asksaveasfilename(parent=self.root, title=title, initialdir=self.asset_folder(template),
                                            defaultextension=".scrib3", filetypes=[("SCRIB3", "*.scrib3")])
        if path:
            colors = {m.color for m in marks}
            asset = replace(self.board, marks=marks, hidden=self.board.hidden & colors,
                            locked=self.board.locked & colors, pen_order=tuple(c for c in self.board.pen_order if c in colors))
            save_board(Path(path), asset)
            self.status.set(f"Saved {Path(path).stem}.")

    def open_asset(self, template=False):
        title = "New from sheet template" if template else "Insert saved element"
        path = filedialog.askopenfilename(parent=self.root, title=title, initialdir=self.asset_folder(template),
                                          filetypes=[("SCRIB3", "*.scrib3")])
        if path:
            asset = load_board(Path(path))
            if template:
                if self.discard():
                    self.load(asset, None)
            else:
                self.insert(asset.marks)

    def engineering_sheet(self):
        from .engineering_sheet import SheetWindow
        path = filedialog.askopenfilename(parent=self.root, title="Choose a model for the sheet",
                                          filetypes=[("Mesh models", "*.stl *.obj *.3mf")])
        if path:
            return SheetWindow(self, Path(path))

    def duplicate(self):
        self.insert(self.selected(), placed=True)

    def transform(self, **kwargs):
        self.commit(self.board.transform(self.selection, **kwargs), self.selection)

    def transform_dialog(self):
        d = form(
            self.root,
            "Transform selection",
            [
                ("scale", "Scale percent", 100),
                ("angle", "Rotation degrees", 0),
                ("dx", "Move X mm", 0),
                ("dy", "Move Y mm", 0),
                ("mirror", "Mirror", ("None", "Horizontal", "Vertical")),
            ],
        )
        if d:
            self.transform(
                factor=float(d["scale"]) / 100,
                angle=float(d["angle"]),
                dx=float(d["dx"]),
                dy=float(d["dy"]),
                mirror_x=d["mirror"] == "Horizontal",
                mirror_y=d["mirror"] == "Vertical",
            )

    def paper(self):
        d = form(
            self.root,
            "Paper",
            [("w", "Width mm", self.board.width), ("h", "Height mm", self.board.height)],
        )
        if d:
            self.commit(replace(self.board, width=float(d["w"]), height=float(d["h"])))

    def align(self, edge):
        a, b, c, d = bounds(self.selected())
        dx = {"Left": -a, "Right": self.board.width - c}.get(edge, 0)
        dy = {"Top": -b, "Bottom": self.board.height - d}.get(edge, 0)
        self.transform(dx=dx, dy=dy)

    def bed(self, size):
        self.commit(replace(self.board, bed=size), self.selection)

    def custom_bed(self):
        width, height = self.board.bed or (self.board.width, self.board.height)
        values = form(self.root, "Bed guide", [("w", "Width mm", width), ("h", "Depth mm", height)])
        if values:
            self.bed((float(values["w"]), float(values["h"])))

    def fill(self, mode):
        d = form(self.root, mode + " fill", [("spacing", "Spacing mm", 1)])
        if d:
            self.insert(hatch(self.selected(), float(d["spacing"]), mode), placed=True)

    def offset(self):
        d = form(self.root, "Offset contours", [("distance", "Distance mm", 2)])
        if d:
            self.insert(offset(self.selected(), float(d["distance"])), placed=True)

    def array(self):
        d = form(
            self.root,
            "Repeat selection",
            [
                ("count", "Total copies", 5),
                ("x", "X step mm", 10),
                ("y", "Y step mm", 0),
                ("angle", "Angle step degrees", 0),
            ],
        )
        if d:
            marks = array(
                self.selected(), int(d["count"]), float(d["x"]), float(d["y"]), float(d["angle"])
            )
            self.commit(
                replace(
                    self.board,
                    marks=tuple(
                        m for i, m in enumerate(self.board.marks) if i not in self.selection
                    )
                    + marks,
                )
            )

    def text(self, edit=False):
        chosen = self.selected() if edit else ()
        if edit and (not chosen or chosen[0].text is None or any(m.text != chosen[0].text for m in chosen)):
            raise ValueError("Select one lettering object to edit.")
        original = chosen[0].text if edit else StrokeText(uuid4().hex)
        def preferred(current, choices):
            return (current, *(v for v in choices if v != current))
        d = form(self.root, "Edit lettering" if edit else "Stroke text", [
            ("text", r"Text (use \n for a new line)", original.value.replace("\n", "\\n")),
            ("font", "Font", preferred(original.font, FONTS)),
            ("size", "Capital height mm", original.height), ("tracking", "Tracking", original.tracking),
            ("line", "Line spacing", original.spacing), ("align", "Alignment", preferred(original.alignment, ALIGNMENTS))])
        if not d:
            return
        spec = replace(original, value=d["text"].replace("\\n", "\n"), font=d["font"], height=float(d["size"]),
                       tracking=float(d["tracking"]), spacing=float(d["line"]), alignment=d["align"])
        if not edit:
            self.insert(spec.marks(self.pen.get()))
            return
        marks = tuple(replace(m, sheet_part=chosen[0].sheet_part)
                      for m in spec.marks(chosen[0].color, chosen[0].groups))
        selected = self.board.text_selection(self.selection)
        first = min(selected)
        updated = self.board.marks[:first] + marks + tuple(
            m for i, m in enumerate(self.board.marks[first:], first) if i not in selected)
        self.commit(replace(self.board, marks=updated), range(first, first + len(marks)))

    def qr(self):
        from .creator import qr_paths

        d = form(
            self.root,
            "QR code",
            [("text", "Text or URL", "https://example.com"), ("size", "Width mm", 50)],
        )
        if d:
            self.insert(qr_paths(d["text"], float(d["size"])))

    def pattern(self):
        from .creator import pattern_paths

        d = form(
            self.root,
            "Pattern",
            [
                (
                    "kind",
                    "Pattern",
                    ("Grid", "Spiral", "Rosette", "Guilloche", "Flow field", "Terrain"),
                ),
                ("detail", "Detail", 40),
                ("seed", "Variation seed", 1),
            ],
        )
        if d:
            self.insert(pattern_paths(d["kind"], int(d["detail"]), int(d["seed"])), fit=True)

    def photo(self):
        from .creator import photo_paths

        target = filedialog.askopenfilename(
            parent=self.root, filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.webp")]
        )
        if not target:
            return
        d = form(
            self.root,
            "Photo art",
            [
                ("style", "Style", ("Engraving", "Squiggle", "Stipple", "Lines")),
                ("width", "Width mm", 180),
                ("spacing", "Spacing mm", 1),
                ("threshold", "Threshold", 128),
            ],
        )
        if d:
            self.insert(
                photo_paths(
                    Path(target),
                    d["style"],
                    float(d["width"]),
                    float(d["spacing"]),
                    int(d["threshold"]),
                ),
                fit=True,
            )

    def mesh(self):
        from .creator import mesh_paths

        target = filedialog.askopenfilename(
            parent=self.root, filetypes=[("3D models", "*.stl *.obj *.3mf")]
        )
        if not target:
            return
        d = form(
            self.root,
            "Model to lines",
            [
                ("yaw", "Yaw degrees", 35),
                ("pitch", "Pitch degrees", 25),
                ("style", "Edges", ("Visible edges", "Feature edges", "Wireframe")),
            ],
        )
        if d:
            self.insert(
                mesh_paths(Path(target), float(d["yaw"]), float(d["pitch"]), d["style"]), fit=True
            )

    def map(self):
        from .creator import map_paths

        target = filedialog.askopenfilename(
            parent=self.root, filetypes=[("GeoJSON", "*.geojson *.json")]
        )
        if target:
            self.insert(map_paths(Path(target)), fit=True)

    def choose_pen(self):
        c = colorchooser.askcolor(self.pen.get(), parent=self.root)[1]
        if c:
            self.pen.set(c.lower())
            self.sync()

    def recolor(self):
        c = colorchooser.askcolor(self.pen.get(), parent=self.root)[1]
        if c:
            if c.lower() in self.board.hidden | self.board.locked:
                raise ValueError("Show and unlock that pen first.")
            self.commit(
                replace(
                    self.board,
                    marks=tuple(
                        replace(m, color=c.lower()) if i in self.selection else m
                        for i, m in enumerate(self.board.marks)
                    ),
                ),
                self.selection,
            )

    def layer_selected(self, e):
        rows = self.layers.curselection()
        if rows:
            self.pen.set(self.colors()[rows[0]])

    def colors(self):
        return tuple(dict.fromkeys((*self.board.pens(False), self.pen.get())))

    def select_pen(self):
        self.selection = {
            i
            for i, m in enumerate(self.board.marks)
            if m.color == self.pen.get() and m.color not in self.board.hidden | self.board.locked
        }
        self.paint()

    def flag(self, name):
        self.commit(
            replace(self.board, **{name: getattr(self.board, name) ^ frozenset([self.pen.get()])})
        )

    def reorder(self, direction):
        colors = list(self.board.pens(False))
        c = self.pen.get()
        if c in colors:
            i = colors.index(c)
            j = max(0, min(len(colors) - 1, i + direction))
            colors[i], colors[j] = colors[j], colors[i]
            self.commit(replace(self.board, pen_order=tuple(colors)))

    def sync(self):
        self.studio.queue_board_preview()
        self.layers.delete(0, "end")
        for i, c in enumerate(self.colors()):
            label = f"{c}  {sum(m.color==c for m in self.board.marks)}"
            label += (
                " hidden" if c in self.board.hidden else " locked" if c in self.board.locked else ""
            )
            self.layers.insert("end", label)
            if c == self.pen.get():
                self.layers.selection_set(i)
        self.paint()

    def reset_view(self):
        self.zoom = 1
        self.pan = (0, 0)
        self.paint()

    def zoom_by(self, k):
        self.zoom = max(0.2, min(15, self.zoom * k))
        self.paint()

    def point(self, e):
        p = (e.x - self.left) / self.k, (e.y - self.top) / self.k
        return tuple(round(v) for v in p) if self.snap.get() else p

    def paint(self):
        cv = self.canvas
        cv.delete("all")
        w, h = cv.winfo_width(), cv.winfo_height()
        if min(w, h) < 40:
            return
        b = self.board
        bw, bh = b.bed or (b.width, b.height)
        self.k = k = min((w - 50) / max(b.width, bw), (h - 50) / max(b.height, bh)) * self.zoom
        self.left = l = (w - b.width * k) / 2 + self.pan[0]
        self.top = t = (h - b.height * k) / 2 + self.pan[1]
        if b.bed:
            dx, dy = (bw - b.width) * k / 2, (bh - b.height) * k / 2
            cv.create_rectangle(l-dx, t-dy, l+b.width*k+dx, t+b.height*k+dy,
                                fill="#303c4b", outline="#7991a7", tags="bed_guide")
        cv.create_rectangle(
            l, t, l + b.width * k, t + b.height * k, fill="#fbfcfd", outline="#7d8c9b"
        )
        if self.grid.get():
            step = 10
            while step * k < 25:
                step *= 2
            for x in range(0, int(b.width) + 1, step):
                px = l + x * k
                cv.create_line(px, t, px, t + b.height * k, fill="#e4e9ef")
                cv.create_text(px, t - 10, text=str(x), fill="#b8c6d5", font=("TkDefaultFont", 8))
            for y in range(0, int(b.height) + 1, step):
                py = t + y * k
                cv.create_line(l, py, l + b.width * k, py, fill="#e4e9ef")
                cv.create_text(
                    l - 4, py, text=str(y), anchor="e", fill="#b8c6d5", font=("TkDefaultFont", 8)
                )
        zero_y = t if self.studio.paper_mount.get() == "top_left_y" else t + b.height * k
        cv.create_oval(l-4, zero_y-4, l+4, zero_y+4, fill="#0087a8", outline="", tags="paper_origin")
        cv.create_text(l+7, zero_y, text="GRBL zero", anchor="w", fill="#0087a8", tags="paper_origin")
        for i, m in enumerate(b.marks):
            if m.color in b.hidden or self.preview is not None and i >= self.preview:
                continue
            cv.create_line(
                *[v for x, y in m.points for v in (l + x * k, t + y * k)],
                fill="#0091b2" if i in self.selection else m.color,
                width=2 if i in self.selection else 1.2,
                tags=(f"p{i}", "art"),
            )
        if self.mode.get() == "Edit nodes" and len(self.selection) == 1:
            index = next(iter(self.selection))
            mark = b.marks[index]
            if not mark.text:
                points = mark.controls or mark.points
                if mark.controls:
                    cv.create_line(*[v for x, y in points for v in (l+x*k, t+y*k)], fill="#52839a", dash=(3, 3))
                previous = None
                for node, (x, y) in enumerate(points):
                    px, py = l+x*k, t+y*k
                    if not mark.controls and previous and node < len(points)-1 and hypot(px-previous[0], py-previous[1]) < 6:
                        continue
                    if -6 <= px <= w+6 and -6 <= py <= h+6:
                        previous = px, py
                        cv.create_rectangle(px-3, py-3, px+3, py+3, fill="white", outline="#008088",
                                            tags=(f"point-{index}-{node}", "node"))
        elif self.selection:
            a, bb, c, d = bounds(self.selected())
            x0, y0, x1, y1 = l + a * k, t + bb * k, l + c * k, t + d * k
            cv.create_rectangle(x0, y0, x1, y1, outline="#0091b2", dash=(4, 3))
            cv.create_rectangle(x1 - 5, y1 - 5, x1 + 5, y1 + 5, fill="#0091b2", tags="scale")
            cv.create_oval(
                (x0 + x1) / 2 - 5,
                y0 - 24,
                (x0 + x1) / 2 + 5,
                y0 - 14,
                fill="#0091b2",
                tags="rotate",
            )
        self.info.set(
            f"{b.width:g} x {b.height:g} mm | {len(b.marks)} paths | {len(self.selection)} selected"
        )

    def press(self, e):
        self.canvas.focus_set()
        p = self.point(e)
        mode = self.mode.get()
        hit = None
        for item in reversed(self.canvas.find_overlapping(e.x - 4, e.y - 4, e.x + 4, e.y + 4)):
            tags = self.canvas.gettags(item)
            if mode == "Edit nodes" and "node" in tags:
                index, node = map(int, tags[0].split("-")[1:])
                self.drag = ("Node", p, (e.x, e.y), self.board, (index, node), self.pan)
                return
            if mode == "Select" and ("scale" in tags or "rotate" in tags):
                mode = tags[0]
                break
            if "art" in tags:
                idx = int(tags[0][1:])
                if self.board.marks[idx].color not in self.board.locked:
                    hit = idx
                    break
        if mode == "Edit nodes":
            if hit is not None and self.board.marks[hit].text:
                raise ValueError("Use Edit lettering for a text object.")
            self.selection = {hit} if hit is not None else set()
            self.paint()
            return
        if mode == "Bezier":
            if self.pen.get() in self.board.hidden | self.board.locked:
                raise ValueError("Show and unlock the drawing pen first.")
            self.bezier_points.append(p)
            self.status.set(f"Bezier control points {len(self.bezier_points)}/4")
            if len(self.bezier_points) == 4:
                controls = tuple(self.bezier_points)
                mark = Mark(self.pen.get(), cubic_points(controls), controls=controls)
                self.commit(replace(self.board, marks=(*self.board.marks, mark)), [len(self.board.marks)])
                self.bezier_points = []
            return
        if mode == "Select":
            if hit is not None:
                if e.state & 1:
                    members = self.board.text_selection([hit])
                    if members <= self.selection:
                        self.selection -= members
                    else:
                        self.selection |= members
                elif hit not in self.selection:
                    self.selection = self.board.text_selection([hit])
                mode = "Move"
            else:
                if not e.state & 1:
                    self.selection.clear()
                mode = "Box"
        if mode == "Eraser":
            if hit is not None:
                self.selection = self.board.text_selection([hit])
                self.delete()
            return
        self.drag = (mode, p, (e.x, e.y), self.board, [p], self.pan)
        self.paint()

    def motion(self, e):
        if not self.drag:
            return
        mode, p, pixel, b, trail, pan = self.drag
        q = self.point(e)
        self.canvas.delete("ghost")
        if mode == "Pan":
            self.pan = (pan[0] + e.x - pixel[0], pan[1] + e.y - pixel[1])
            self.paint()
        elif mode == "Node":
            index, node = trail
            mark = b.marks[index]
            pts = list(mark.controls or mark.points)
            pts[node] = q
            preview = cubic_points(pts) if mark.controls else pts
            self.canvas.create_line(*[v for x, y in preview for v in (self.left + x*self.k, self.top + y*self.k)],
                                    fill="#008e91", width=2, tags="ghost")
        elif mode == "Freehand":
            trail.append(q)
            self.canvas.create_line(
                *[v for x, y in trail for v in (self.left + x * self.k, self.top + y * self.k)],
                fill=self.pen.get(),
                tags="ghost",
            )
        else:
            self.canvas.create_rectangle(
                *pixel, e.x, e.y, outline="#0091b2", dash=(3, 3), tags="ghost"
            )

    def release(self, e):
        if not self.drag:
            return
        mode, p, pixel, b, trail, pan = self.drag
        self.drag = None
        q = self.point(e)
        self.canvas.delete("ghost")
        if mode == "Pan":
            return
        if mode == "Node":
            index, node = trail
            mark = b.marks[index]
            pts = list(mark.controls or mark.points)
            if pts[0] == pts[-1] and node in (0, len(pts) - 1):
                pts[0] = pts[-1] = q
            pts[node] = q
            controls = tuple(pts) if mark.controls else ()
            changed = replace(mark, points=cubic_points(controls) if controls else tuple(pts), controls=controls)
            self.commit(replace(b, marks=(*b.marks[:index], changed, *b.marks[index+1:])), [index])
            return
        if mode == "Box":
            a, c = sorted((p[0], q[0]))
            bb, d = sorted((p[1], q[1]))
            self.selection |= {
                i
                for i, m in enumerate(b.marks)
                if m.color not in b.hidden | b.locked
                and all(a <= x <= c and bb <= y <= d for x, y in m.points)
            }
            self.selection = b.text_selection(self.selection)
            self.paint()
        elif mode == "Move":
            if self.selection and q != p:
                self.transform(dx=q[0] - p[0], dy=q[1] - p[1])
        elif mode in ("scale", "rotate"):
            a, bb, c, d = bounds(self.selected())
            cx, cy = (a + c) / 2, (bb + d) / 2
            if mode == "scale":
                self.transform(
                    factor=max(
                        0.001,
                        hypot(q[0] - cx, q[1] - cy) / max(0.0001, hypot(p[0] - cx, p[1] - cy)),
                    )
                )
            else:
                self.transform(
                    angle=degrees(atan2(q[1] - cy, q[0] - cx) - atan2(p[1] - cy, p[0] - cx))
                )
        elif hypot(q[0] - p[0], q[1] - p[1]) > 0.01:
            if self.pen.get() in b.hidden | b.locked:
                raise ValueError("Show and unlock the drawing pen first.")
            pts = tuple(trail + [q]) if mode == "Freehand" else shape(mode, p, q)
            self.commit(replace(b, marks=b.marks + (Mark(self.pen.get(), pts),)), [len(b.marks)])

    def cancel(self):
        self.drag = None
        self.bezier_points = []
        if self.timer:
            self.root.after_cancel(self.timer)
            self.timer = None
        self.preview = None
        self.paint()

    def play(self):
        if self.timer:
            self.cancel()
            return
        self.preview = 0

        def tick():
            self.preview += max(1, len(self.board.marks) // 100)
            self.paint()
            if self.preview >= len(self.board.marks):
                self.timer = None
                self.preview = None
            else:
                self.timer = self.root.after(50, tick)

        tick()

    def printer(self, model):
        if model == "P1S":
            return self.studio.show_p1s()
        from .printer_ui import PrinterWindow

        return PrinterWindow(self.studio, model, parent=self.root)

    def run_passes(self):
        from .pass_ui import PassWindow

        PassWindow(self)
