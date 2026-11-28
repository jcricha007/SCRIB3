"""Named P1S holder and stock setups, plate previews and tile export."""
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import theme
from .p1s_layout import Layout, PaperSetup, sheet_grid
from .printer_output import Holder, plan_printer


def stock_rectangles(setup):
    l,f,w,h = setup.left,setup.front,setup.width,setup.height
    yield "paper", (l,f,l+w,f+h)
    for depth, rect in ((setup.clip_left,(l,f,l+setup.clip_left,f+h)),
                        (setup.clip_right,(l+w-setup.clip_right,f,l+w,f+h)),
                        (setup.clip_front,(l,f,l+w,f+setup.clip_front)),
                        (setup.clip_back,(l,f+h-setup.clip_back,l+w,f+h))):
        if depth:
            yield "clip", rect


def board_overlay(editor, setup, area, tiled):
    cv, k = editor.canvas, editor.k
    a,b,c,d = area
    w,h = c-a,d-b
    board = editor.board
    sx,sy = w-setup.overlap,h-setup.overlap
    try:
        rows, cols = sheet_grid(board, w, h, setup.overlap, tiled)
    except ValueError:
        return
    if tiled:
        scale = 1
        offset_x = offset_y = 0
    else:
        scale = min(1,w/board.width,h/board.height)
        offset_x,offset_y = (w/scale-board.width)/-2,(h/scale-board.height)/-2
    for row in range(rows):
        for col in range(cols):
            ox = editor.left+(col*sx+offset_x)*k
            oy = editor.top+(row*sy+offset_y)*k
            for kind, (l,f,r,back) in (*stock_rectangles(setup), ("reach",area)):
                cv.create_rectangle(ox+(l-a)*k/scale,oy+(d-back)*k/scale,
                                    ox+(r-a)*k/scale,oy+(d-f)*k/scale,
                                    outline=theme.TRAVEL if kind=="clip" else theme.ACCENT,
                                    fill="#efc39a" if kind=="clip" else "",dash=(4,3),tags="p1s_guides")
            cv.create_text(ox+3,oy+3,anchor="nw",text=f"{row+1} / {col+1}",fill=theme.ACCENT,tags="p1s_guides")


class PlacementWindow:
    def __init__(self, output):
        self.output = output
        self.window = tk.Toplevel(output.window)
        self.window.title("SCRIB3 | P1S paper placement")
        self.window.geometry("830x560")
        panel = ttk.Frame(self.window,padding=12)
        panel.pack(fill="both",expand=True)
        panel.columnconfigure(0,weight=1)
        panel.rowconfigure(0,weight=1)
        self.canvas = tk.Canvas(panel,width=260,height=220,background=theme.DESK,highlightthickness=0)
        self.canvas.grid(row=0,column=0,sticky="nsew",padx=(0,10))
        self.canvas.bind("<Configure>",self.draw)
        form = ttk.Frame(panel)
        form.grid(row=0,column=1,sticky="ns")
        self.name = tk.StringVar()
        ttk.Label(form,text="Holder and paper setup",style="Section.TLabel").grid(row=0,columnspan=2,sticky="w")
        self.names = ttk.Combobox(form,textvariable=self.name,width=22)
        self.names.grid(row=1,column=0,sticky="ew")
        self.names.bind("<<ComboboxSelected>>",self.load)
        ttk.Button(form,text="Save",command=self.save).grid(row=1,column=1)
        self.fields = {}
        for i,(key,label) in enumerate((("width","Stock width"),("height","Stock height"),("left","Left on bed"),
                                        ("front","Front on bed"),("clip_left","Left clip strip"),("clip_right","Right clip strip"),
                                        ("clip_front","Front clip strip"),("clip_back","Back clip strip"),("overlap","Tile overlap"))):
            v = self.fields[key] = tk.StringVar(value=f"{getattr(PaperSetup(),key):g}")
            ttk.Label(form,text=label+" (mm)").grid(row=2+i,column=0,sticky="w")
            ttk.Entry(form,textvariable=v,width=9).grid(row=2+i,column=1,sticky="ew")
            v.trace_add("write",self.invalidate)
        self.mode = tk.StringVar(value="Full-scale tiles")
        mode = ttk.Combobox(form,textvariable=self.mode,state="readonly",values=("Full-scale tiles","Fit on one sheet"))
        mode.grid(row=11,columnspan=2,sticky="ew",pady=4)
        mode.bind("<<ComboboxSelected>>",self.invalidate)
        self.index = tk.IntVar(value=1)
        ttk.Label(form,text="Tile (row order)").grid(row=12,column=0,sticky="w")
        self.tile = ttk.Spinbox(form,from_=1,to=1,textvariable=self.index,width=8,command=self.preview)
        self.tile.grid(row=12,column=1)
        self.index.trace_add("write",self.invalidate)
        self.dry = tk.BooleanVar(value=True)
        ttk.Checkbutton(form,text="Pen-up test",variable=self.dry,command=self.invalidate).grid(row=13,columnspan=2,sticky="w")
        ttk.Button(form,text="Preview",command=self.preview).grid(row=14,column=0,sticky="ew")
        ttk.Button(form,text="Show on board",command=self.overlay).grid(row=14,column=1)
        ttk.Button(form,text="Export placement…",command=self.export,style="Primary.TButton").grid(row=15,columnspan=2,sticky="ew",pady=5)
        self.status = tk.StringVar(value="Load a setup or enter holder measurements in P1S setup.")
        ttk.Label(panel,textvariable=self.status,wraplength=650).grid(row=1,columnspan=2,sticky="w",pady=5)
        self.layout = self.plan = None
        self.db = None
        try:
            path = output.prefs.with_name("p1s-placements.sqlite3")
            path.parent.mkdir(parents=True,exist_ok=True)
            self.db = sqlite3.connect(path)
            self.db.execute("CREATE TABLE IF NOT EXISTS setups(name TEXT PRIMARY KEY, config TEXT NOT NULL)")
            self.list_names()
        except (OSError,sqlite3.Error) as err:
            self.status.set(str(err))
        self.window.bind("<Destroy>",self.close,add="+")
        self.preview()

    def setup(self):
        return PaperSetup(**{key:float(v.get()) for key,v in self.fields.items()})

    def list_names(self):
        self.names.configure(values=[r[0] for r in self.db.execute("SELECT name FROM setups ORDER BY name")])

    def save(self):
        try:
            setup,holder = self.setup(),self.output.holder()
            setup.area(holder)
            name = self.name.get().strip()
            if not name or len(name)>120 or self.db is None:
                raise ValueError("Enter a setup name and choose a writable settings folder.")
            payload = json.dumps(dict(paper=asdict(setup),holder=asdict(holder)),allow_nan=False)
            with self.db:
                self.db.execute("INSERT OR REPLACE INTO setups VALUES (?,?)",(name,payload))
            self.list_names()
            self.status.set("Saved holder, stock position and clip strips.")
        except (ValueError,sqlite3.Error) as err:
            self.status.set(str(err))

    def load(self, *_):
        try:
            row = self.db.execute("SELECT config FROM setups WHERE name=?",(self.name.get(),)).fetchone()
            if row is None:
                raise ValueError("Choose an existing setup.")
            data = json.loads(row[0])
            holder = Holder(**data["holder"])
            setup = PaperSetup(**data["paper"])
            setup.area(holder)
            for key,v in self.output.fields.items():
                v.set(str(getattr(holder,key)))
            for key,v in self.fields.items():
                v.set(str(getattr(setup,key)))
            self.index.set(1)
            self.preview()
        except (ValueError,TypeError,KeyError,sqlite3.Error) as err:
            self.status.set(str(err))

    def invalidate(self, *_):
        self.plan = None
        self.draw()
        self.status.set("Placement changed. Preview the sheet.")

    def preview(self, *_):
        try:
            tiled = self.mode.get()=="Full-scale tiles"
            layout = Layout(self.output.studio.current_board,self.output.holder(),self.setup(),tiled=tiled)
            total = layout.cols*layout.rows if tiled else 1
            self.tile.configure(to=total)
            i = max(1,min(self.index.get(),total))
            if i != self.index.get():
                self.index.set(i)
            plan = layout.plan(i-1,self.dry.get()) if tiled else plan_printer(
                layout.board,layout.holder,fit=True,dry=self.dry.get(),area=layout.area)
            self.layout,self.plan = layout,plan
            self.status.set(f"Sheet {i}/{total}  ·  {plan.scale:.1%} scale  ·  {plan.width:.1f} × {plan.height:.1f} mm  ·  Orange bands mark clip locations.")
        except (ValueError,tk.TclError) as err:
            self.plan = None
            self.status.set(str(err))
        self.draw()
        return self.plan

    def draw(self, *_):
        cv = self.canvas
        cv.delete("all")
        try:
            setup = self.setup()
            area = setup.area(self.output.holder())
        except ValueError:
            return
        w,h = cv.winfo_width(),cv.winfo_height()
        k = max(.01,min(w-20,h-20)/256)
        l,t = (w-256*k)/2,(h-256*k)/2
        def pt(x,y):
            return l+x*k,t+(256-y)*k
        cv.create_rectangle(*pt(0,256),*pt(256,0),fill=theme.DESK,outline=theme.MUTED)
        for kind,(x,y,r,b) in stock_rectangles(setup):
            cv.create_rectangle(*pt(x,b),*pt(r,y),fill=theme.PAPER if kind=="paper" else "#efc39a",outline=theme.BORDER)
        a,b,c,d = area
        cv.create_rectangle(*pt(a,d),*pt(c,b),outline=theme.ACCENT,dash=(4,3))
        if self.plan is None:
            return
        holder = self.layout.holder
        for color,paths in self.plan.passes:
            for path in paths:
                cv.create_line(*(v for x,y in path for v in pt(x+holder.offset_x,y+holder.offset_y)),fill=color)

    def overlay(self):
        studio = self.output.studio
        try:
            setup = self.setup()
            area = setup.area(self.output.holder())
            left, front, right, back = area
            tiled = self.mode.get() == "Full-scale tiles"
            sheet_grid(studio.current_board, right-left, back-front, setup.overlap, tiled)
        except ValueError as err:
            self.status.set(str(err))
            return
        studio.p1s_overlay = (setup, area, tiled)
        studio.show_board()
        studio.board_editor.paint()

    def export(self):
        plan = self.preview()
        if not plan:
            return
        tiled = self.mode.get()=="Full-scale tiles"
        if not messagebox.askokcancel("Review P1S output",self.status.get()+
                "\nHome with obstructing attachments removed. Install the measured holder at the setup pause. For tiles, use a fresh sheet in the same position for each plate.",
                parent=self.window):
            return
        target = filedialog.asksaveasfilename(parent=self.window,initialfile="poster-tiles.zip" if tiled else "poster.gcode.3mf",
                 defaultextension=".zip" if tiled else ".3mf",filetypes=[("Tile bundle","*.zip")] if tiled else [("Sliced pen plate","*.3mf")])
        if target:
            try:
                if tiled:
                    self.layout.export(Path(target),self.dry.get())
                else:
                    if not target.lower().endswith(".3mf"):
                        raise ValueError("Use the .3mf extension for a sliced plate.")
                    plan.export(Path(target))
                self.status.set("Saved "+Path(target).name)
            except (ValueError,OSError) as err:
                self.status.set(str(err))

    def close(self,event):
        if event.widget is self.window and self.db is not None:
            self.db.close()
