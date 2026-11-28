"""Paper, pen and feed comparison for the current GRBL machine."""
import json
import sqlite3
import tkinter as tk
from tkinter import ttk

from . import theme
from .drawing import Sheet
from .quality_card import RATINGS, profile_store, save_card, trials
from .units import display, to_mm


class QualityCardWindow:
    def __init__(self, studio):
        self.studio = studio
        self.window = tk.Toplevel(studio.root)
        self.window.title("SCRIB3 | Plot-quality calibration")
        frame = ttk.Frame(self.window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Compare drawing feeds", style="Title.TLabel").grid(row=0, columnspan=5, sticky="w")
        ttk.Label(frame, text="Keep the sheet and paper zero fixed. Review each row, then inspect its circle seam, diagonals and corners.",
                  wraplength=550).grid(row=1, columnspan=5, sticky="w", pady=6)
        self.canvas = tk.Canvas(frame, width=540, height=160, bg=theme.DESK, highlightthickness=0)
        self.canvas.grid(row=2, columnspan=5, sticky="ew")
        self.feeds, self.ratings = [], []
        self.winner = tk.IntVar(value=0)
        self.notes, self.pen, self.paper = (tk.StringVar() for _ in range(3))
        self.status = tk.StringVar()
        for col, text in enumerate(("Row", "Feed (mm/min)", "Observation", "Review", "Best")):
            ttk.Label(frame, text=text, style="Section.TLabel").grid(row=3, column=col, sticky="w", pady=6)
        try:
            feed = to_mm(studio.feed.get(), studio.unit)
            if feed <= 0:
                raise ValueError
        except ValueError:
            from .motion_profile import DRAW_FEED
            feed = DRAW_FEED
        for index, multiplier in enumerate((.5, .75, 1)):
            v = tk.StringVar(value=f"{feed*multiplier:g}")
            rating = tk.StringVar(value=RATINGS[0])
            self.feeds.append(v)
            self.ratings.append(rating)
            row = 4+index
            ttk.Label(frame, text=str(index+1)).grid(row=row, column=0)
            ttk.Entry(frame, width=12, textvariable=v).grid(row=row, column=1, sticky="w")
            ttk.Combobox(frame, width=13, state="readonly", values=RATINGS, textvariable=rating).grid(row=row, column=2)
            ttk.Button(frame, text="Review row", command=lambda i=index: self.review(i)).grid(row=row, column=3)
            ttk.Radiobutton(frame, variable=self.winner, value=index).grid(row=row, column=4)
            v.trace_add("write", lambda *_, i=index: self.ratings[i].set(RATINGS[0]))
        for row, (label, var) in enumerate((("Pen", self.pen), ("Paper", self.paper), ("Notes", self.notes)), 7):
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
            ttk.Entry(frame, textvariable=var).grid(row=row, column=1, columnspan=4, sticky="ew", pady=2)
        self.db = None
        self.profiles = []
        self.choice = ttk.Combobox(frame, width=30, state="readonly")
        self.choice.grid(row=10, columnspan=3, sticky="ew", pady=6)
        self.choice.bind("<<ComboboxSelected>>", self.load)
        ttk.Button(frame, text="Save result", command=self.save).grid(row=10, column=3, columnspan=2)
        ttk.Button(frame, text="Use winning feed", command=self.apply).grid(row=11, column=3, columnspan=2)
        ttk.Label(frame, textvariable=self.status, wraplength=340).grid(row=11, columnspan=3, sticky="w")
        self.window.bind("<Destroy>", self.closed, add="+")
        try:
            self.db = profile_store(studio.preset_file.with_name("quality-cards.sqlite3"))
            self.refresh_profiles()
        except (OSError, sqlite3.Error) as error:
            self.status.set(str(error))
        self.canvas.bind("<Configure>", self.paint)

    def rows(self):
        s = self.studio
        sheet = Sheet(*(to_mm(v.get(), s.unit) for v in (s.paper_width, s.paper_height, s.margin)))
        return trials(sheet, [v.get() for v in self.feeds])

    def paint(self, *_):
        cv = self.canvas
        cv.delete("all")
        try:
            rows = self.rows()
        except ValueError as error:
            self.status.set(str(error))
            return
        w, h = cv.winfo_width(), cv.winfo_height()
        sheet = rows[0].sheet
        k = min((w-12)/sheet.width, (h-12)/sheet.height)
        l, t = (w-k*sheet.width)/2, (h-k*sheet.height)/2
        cv.create_rectangle(l,t,l+k*sheet.width,t+k*sheet.height,fill=theme.PAPER,outline=theme.BORDER)
        for trial in rows:
            for path in trial.paths:
                cv.create_line(*(a for x,y in path for a in (l+k*x,t+k*(sheet.height-y))), fill=theme.INK)

    def review(self, index):
        try:
            trial = self.rows()[index]
            self.studio.review(trial=trial)
        except ValueError as error:
            self.status.set(str(error))

    def refresh_profiles(self):
        self.profiles = self.db.execute("SELECT pen,paper FROM cards ORDER BY pen,paper").fetchall()
        self.choice.configure(values=[f"{p} / {s}" for p,s in self.profiles])

    def load(self, *_):
        pen, paper = self.profiles[self.choice.current()]
        data = json.loads(self.db.execute("SELECT data FROM cards WHERE pen=? AND paper=?", (pen,paper)).fetchone()[0])
        self.pen.set(pen)
        self.paper.set(paper)
        for i in range(3):
            self.feeds[i].set(f"{data['feeds'][i]:g}")
            self.ratings[i].set(data["ratings"][i])
        self.notes.set(data["notes"])
        self.winner.set(data["winner"])
        self.status.set("Saved comparison loaded.")

    def save(self):
        try:
            if self.db is None:
                raise ValueError("The profile store is unavailable.")
            save_card(self.db, self.pen.get(), self.paper.get(), [r.feed for r in self.rows()],
                      [v.get() for v in self.ratings], self.notes.get(), self.winner.get())
            self.refresh_profiles()
            self.status.set("Pen and paper comparison saved.")
        except (OSError, ValueError, sqlite3.Error) as error:
            self.status.set(str(error))

    def apply(self):
        try:
            i = self.winner.get()
            if self.ratings[i].get() != "Clean":
                raise ValueError("Select a row rated Clean.")
            feed = self.rows()[i].feed
            self.studio.feed.set(display(feed, self.studio.unit))
            self.status.set(f"Drawing feed set to {feed:g} mm/min.")
        except ValueError as error:
            self.status.set(str(error))

    def closed(self, event):
        if event.widget is self.window and self.db is not None:
            self.db.close()
