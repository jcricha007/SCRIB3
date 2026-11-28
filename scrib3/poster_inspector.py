"""Paper-space placement of artwork and alignment guides for moving a selection."""
from bisect import bisect_left
import tkinter as tk
from tkinter import ttk

from .board import bounds
from .units import display, to_mm, number


def place(board, indices, x, y, width, height, *, keep_aspect=False, driver="width"):
    indices = board.text_selection(indices)
    left, top, right, bottom = bounds(board.marks[i] for i in indices)
    old = right-left, bottom-top
    x, y, width, height = map(number, (x, y, width, height))
    scales = []
    for previous, requested in zip(old, (width, height)):
        if previous == 0 and requested != 0 or previous > 0 and requested <= 0:
            raise ValueError("Keep zero extents at zero and other dimensions positive.")
        scales.append(requested / previous if previous else 1.)
    if keep_aspect:
        axis = 1 if driver == "height" else 0
        if not old[axis]:
            axis = 1-axis
        scales = [scales[axis]] * 2
    return board.transform(indices, scale_x=scales[0], scale_y=scales[1],
                           dx=x-left+(old[0]*scales[0]-old[0])/2,
                           dy=y-top+(old[1]*scales[1]-old[1])/2)


def anchors(low, high):
    return (low, (low+high)/2, high)


def guide_targets(board, selection):
    x = set(anchors(0, board.width))
    y = set(anchors(0, board.height))
    objects = {}
    for i, mark in enumerate(board.marks):
        if i not in selection and mark.color not in board.hidden:
            objects.setdefault(mark.groups[:1] or i, []).append(mark)
    for marks in objects.values():
        a,b,c,d = bounds(marks)
        x.update(anchors(a,c))
        y.update(anchors(b,d))
    return sorted(x), sorted(y)


def snap_axis(low, high, delta, targets, tolerance):
    best = None
    for value in anchors(low+delta, high+delta):
        idx = bisect_left(targets, value)
        for target in targets[max(0,idx-1):idx+1]:
            gap = target-value
            if abs(gap) <= tolerance and (best is None or abs(gap) < abs(best[0])):
                best = gap, target
    return (delta+best[0], best[1]) if best else (delta, None)


class PosterInspector:
    def __init__(self, editor):
        self.editor = editor
        self.window = tk.Toplevel(editor.root)
        self.window.title("SCRIB3 | Precision inspector")
        self.window.transient(editor.root)
        panel = ttk.Frame(self.window, padding=12)
        panel.pack(fill="both", expand=True)
        self.unit = tk.StringVar(value=editor.studio.unit)
        self.aspect = tk.BooleanVar(value=True)
        self.driver = "width"
        self.key = self.group_board = None
        self.syncing = False
        ttk.Label(panel, text="Selection bounds", style="Title.TLabel").grid(row=0, columnspan=2, sticky="w")
        unit = ttk.Combobox(panel, width=5, textvariable=self.unit, values=("mm","in"), state="readonly")
        unit.grid(row=0,column=2,sticky="e")
        unit.bind("<<ComboboxSelected>>", lambda _: self.refresh(force=True))
        self.fields = {}
        for row, (key,label) in enumerate((("x","Left X"),("y","Top Y"),("width","Width"),("height","Height")),1):
            v = self.fields[key] = tk.StringVar()
            ttk.Label(panel,text=label).grid(row=row,column=0,sticky="w")
            ttk.Entry(panel,textvariable=v).grid(row=row,column=1,columnspan=2,sticky="ew",pady=2)
            if key in ("width","height"):
                v.trace_add("write", lambda *_, dim=key: self.dimension_changed(dim))
        ttk.Checkbutton(panel,text="Lock aspect ratio",variable=self.aspect,
                        command=lambda: self.dimension_changed(self.driver)).grid(row=5,columnspan=2,sticky="w")
        self.apply_button = ttk.Button(panel,text="Apply",style="Primary.TButton",command=self.apply)
        self.apply_button.grid(row=5,column=2,sticky="e")
        ttk.Checkbutton(panel,text="Snap to alignment guides",variable=editor.align_guides).grid(row=6,columnspan=3,sticky="w")
        ttk.Label(panel,text="Named groups",style="Section.TLabel").grid(row=7,columnspan=3,sticky="w",pady=(8,2))
        self.tree = ttk.Treeview(panel, show="tree", selectmode="browse", height=9)
        self.tree.grid(row=8,columnspan=3,sticky="nsew")
        scroll = ttk.Scrollbar(panel,command=self.tree.yview)
        scroll.grid(row=8,column=3,sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        panel.rowconfigure(8,weight=1)
        panel.columnconfigure(1,weight=1)
        self.tree.bind("<<TreeviewSelect>>",self.select_group)
        self.status = ttk.Label(panel,wraplength=290)
        self.status.grid(row=9,columnspan=3,sticky="w")
        self.window.bind("<Return>",lambda _: self.apply())
        self.refresh()

    def dimension_changed(self, key):
        if self.syncing:
            return
        self.driver = key
        if self.aspect.get() and self.key:
            w, h = self.extents
            other, previous, paired = ("height",w,h) if key=="width" else ("width",h,w)
            try:
                value = number(self.fields[key].get())
            except ValueError:
                return
            if previous:
                self.syncing = True
                try:
                    self.fields[other].set(f"{value*paired/previous:.10g}")
                finally:
                    self.syncing = False

    def refresh(self, force=False):
        e = self.editor
        if self.group_board is not e.board:
            self.group_board = e.board
            self.tree.delete(*self.tree.get_children())
            self.groups = {}
            ids = {}
            for mark in e.board.marks:
                if mark.color in e.board.hidden | e.board.locked:
                    continue
                for depth in range(1,len(mark.groups)+1):
                    group = mark.groups[:depth]
                    if group not in ids:
                        iid = self.tree.insert(ids.get(group[:-1],""),"end",text=group[-1],open=True)
                        self.groups[iid] = group
                        ids[group] = iid
        key = (e.revision, frozenset(e.selection), self.unit.get())
        if not force and key == self.key:
            return
        self.key = key
        self.syncing = True
        try:
            marks = e.selected()
            values = ("",)*4
            self.extents = 0.,0.
            if marks:
                x,y,r,b = bounds(marks)
                self.extents = r-x,b-y
                values = tuple(display(v,self.unit.get()) for v in (x,y,*self.extents))
            for var, value in zip(self.fields.values(),values):
                var.set(value)
            self.apply_button.state(["!disabled"] if marks else ["disabled"])
            self.status.configure(text=f"{len(marks)} selected paths")
        finally:
            self.syncing = False

    def select_group(self, *_):
        chosen = self.tree.selection()
        if chosen and (group := self.groups.get(chosen[0])):
            e = self.editor
            e.selection = e.board.text_selection(i for i,m in enumerate(e.board.marks) if m.groups[:len(group)] == group)
            e.paint()

    def apply(self):
        try:
            e = self.editor
            board = place(e.board,e.selection,*(to_mm(v.get(),self.unit.get()) for v in self.fields.values()),
                          keep_aspect=self.aspect.get(),driver=self.driver)
            e.commit(board,e.selection)
        except ValueError as error:
            self.status.configure(text=str(error))
