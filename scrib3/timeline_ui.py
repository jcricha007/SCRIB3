"""Interactive review playback and controller-confirmed progress."""
from bisect import bisect_right
from time import monotonic
import tkinter as tk
from tkinter import ttk

from . import theme


class TraceView(ttk.Frame):
    def __init__(self, parent, timeline):
        super().__init__(parent)
        self.timeline = timeline
        self.canvas = tk.Canvas(self, bg=theme.DESK, highlightthickness=0, height=220)
        self.canvas.pack(fill="both", expand=True)
        self.caption = ttk.Label(self, style="Muted.TLabel")
        self.caption.pack(anchor="w")
        self.count, self.part, self.stopped = 0, 0., False
        self.runs, self.ends = [], []
        self.canvas.bind("<Configure>", self.layout)

    def layout(self, *_):
        cv, plan = self.canvas, self.timeline
        cv.delete("all")
        width, height = cv.winfo_width(), cv.winfo_height()
        k = max(.01, min((width-32)/plan.sheet.width, (height-32)/plan.sheet.height))
        l, t = (width-k*plan.sheet.width)/2, (height-k*plan.sheet.height)/2
        def project(xy):
            x, y = plan.paper_point(xy)
            return l+k*x, t+k*y
        self.project = project
        cv.create_rectangle(l, t, l+k*plan.sheet.width, t+k*plan.sheet.height, fill=theme.PAPER, outline=theme.BORDER)
        self.runs, self.ends = [], []
        prev = plan.start
        i = 0
        while i < len(plan.events):
            e = plan.events[i]
            if e.kind not in ("Travel", "Draw", "Dry stroke"):
                i += 1
                continue
            first = i
            pts = [*project(prev)]
            while i < len(plan.events) and plan.events[i].kind == e.kind and i-first < 512:
                prev = plan.events[i].xy
                pts.extend(project(prev))
                i += 1
            color = theme.ACCENT if e.kind == "Draw" else theme.TRAVEL
            dash = () if e.kind == "Draw" else (3, 3)
            item = cv.create_line(*pts, fill=theme.BORDER, dash=dash)
            self.runs.append((first, pts, item, color, dash))
            self.ends.append(i)
        self.done = 0
        self.show(self.count, self.part, stopped=self.stopped)

    def show(self, count, part=0., *, stopped=False):
        self.stopped = stopped
        self.count = count = min(max(0, count), len(self.timeline.events))
        self.part = part
        if not hasattr(self, "project"):
            return
        cv, plan = self.canvas, self.timeline
        complete = bisect_right(self.ends, count)
        for i in range(min(complete, self.done), max(complete, self.done)):
            _, _, item, color, _ = self.runs[i]
            cv.itemconfigure(item, fill=color if i < complete else theme.BORDER)
        self.done = complete
        cv.delete("cursor")
        xy = plan.events[count-1].xy if count else plan.start
        event = plan.events[min(count, len(plan.events)-1)] if part else (plan.events[count-1] if count else None)
        if part and event:
            xy = tuple(a+(b-a)*part for a, b in zip(xy, event.xy))
        x, y = self.project(xy)
        if complete < len(self.runs):
            first, pts, _, color, dash = self.runs[complete]
            if count >= first:
                coords = pts[:2*(count-first+1)] + [x, y]
                cv.create_line(*coords, fill=color, dash=dash, tags="cursor")
        cv.create_oval(x-4, y-4, x+4, y+4, fill=theme.NAVY, outline="white", tags="cursor")
        self.caption.configure(text=(f"{'Stopped' if stopped else event.kind}  ·  Pen {'down' if event.down and not stopped else 'up'}  ·  Stroke "
                                     f"{event.stroke}/{plan.strokes}  ·  XY {xy[0]:.2f}, {xy[1]:.2f} mm")
                               if event else "Ready  ·  Starting XY in work coordinates")


class TimelineWindow:
    def __init__(self, parent, plan):
        self.window = tk.Toplevel(parent)
        self.window.title("SCRIB3 | Plot timeline")
        self.window.geometry("720x500")
        self.plan = plan
        frame = ttk.Frame(self.window, padding=12)
        frame.pack(fill="both", expand=True)
        self.view = TraceView(frame, plan)
        self.view.pack(fill="both", expand=True)
        self.seconds = tk.DoubleVar(value=0)
        ttk.Scale(frame, from_=0, to=plan.seconds, variable=self.seconds,
                  command=self.seek).pack(fill="x", pady=5)
        row = ttk.Frame(frame)
        row.pack(fill="x")
        self.button = ttk.Button(row, text="Play", command=self.toggle)
        self.button.pack(side="left")
        self.speed = tk.StringVar(value="1")
        ttk.Combobox(row, width=4, state="readonly", textvariable=self.speed,
                     values=("1", "4", "16", "64")).pack(side="left", padx=4)
        ttk.Label(row, text="× speed").pack(side="left")
        self.clock = ttk.Label(row)
        self.clock.pack(side="right")
        ttk.Label(frame, text=f"Programmed holds {plan.hold_seconds:g} s  ·  Motion time estimated at nominal feeds.",
                  style="Muted.TLabel").pack(anchor="w", pady=4)
        self.timer = None
        self.window.bind("<Destroy>", self.destroyed, add="+")
        self.seek(0)

    def seek(self, value):
        seconds = float(value)
        self.view.show(*self.plan.at_time(seconds))
        self.clock.configure(text=f"{seconds:.1f} / {self.plan.seconds:.1f} s")

    def toggle(self):
        if self.timer is not None:
            self.window.after_cancel(self.timer)
            self.timer = None
            self.button.configure(text="Play")
            return
        if self.seconds.get() >= self.plan.seconds:
            self.seconds.set(0.)
        self.last = monotonic()
        self.tick()

    def tick(self):
        now = monotonic()
        seconds = min(self.plan.seconds, self.seconds.get() + (now-self.last)*float(self.speed.get()))
        self.last = now
        self.seconds.set(seconds)
        self.seek(seconds)
        self.timer = self.window.after(50, self.tick) if seconds < self.plan.seconds else None
        self.button.configure(text="Pause" if self.timer else "Play")

    def destroyed(self, event):
        if event.widget is self.window and self.timer is not None:
            self.window.after_cancel(self.timer)
            self.timer = None
