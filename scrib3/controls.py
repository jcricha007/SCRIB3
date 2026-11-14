"""Tk controls for connection, machine setup, and deliberate single-step motion."""
from __future__ import annotations

from queue import Empty, Queue
from threading import Event, Thread
import tkinter as tk
from tkinter import messagebox, ttk

from .controller import Controller, SETUP_FIELDS, jog_command, setting_changes
from .discovery import detect
from .firmware import SERVO_PROFILE
from .grbl import ports


class ControlPanel(ttk.Frame):
    def __init__(self, parent, studio):
        super().__init__(parent, padding=8)
        self.studio = studio
        self.session = None
        self.scan_cancel = Event()
        self.scanning = False
        self.scan_thread = None
        self.messages = Queue()
        self.show_report = False
        self.closing = False
        self.step = tk.StringVar(value="1")
        self.rate = tk.StringVar(value="300")
        self.connection_text = tk.StringVar(value="Select a port, or use Auto detect.")
        self.state_text = tk.StringVar(value="Disconnected")
        self.position_text = tk.StringVar(value="Work XY: —\nMachine XY: —")
        self.pin_text = tk.StringVar(value="Limit inputs: —")
        self.buttons = {}
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

        connection = ttk.LabelFrame(self, text="Connection", padding=6)
        connection.grid(row=0, columnspan=3, sticky="ew")
        connection.columnconfigure(0, weight=1)
        self.port_picker = ttk.Combobox(connection, textvariable=studio.port, width=22)
        self.port_picker.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.baud_picker = ttk.Combobox(connection, textvariable=studio.baud, width=8,
                                       values=(115200, 57600, 38400, 19200, 9600, 230400, 250000))
        self.baud_picker.grid(row=0, column=1, sticky="ew")
        actions = ttk.Frame(connection)
        actions.grid(row=1, columnspan=2, sticky="ew", pady=(4, 0))
        for column, (name, command) in enumerate((("Find ports", self.find_ports),
                                                  ("Auto detect", self.auto_detect),
                                                  ("Connect", self.connect))):
            button = ttk.Button(actions, text=name, command=command, padding=(6, 4))
            button.grid(row=0, column=column, sticky="ew", padx=(0, 3))
            actions.columnconfigure(column, weight=1)
            self.buttons[name] = button
        tk.Label(connection, textvariable=self.connection_text, wraplength=330, height=2,
                 justify="left", anchor="w", background="#f1f2ec", foreground="#555e54").grid(row=2, columnspan=2, sticky="w", pady=(4, 0))

        ttk.Label(self, textvariable=self.state_text, style="Title.TLabel").grid(row=1, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(self, textvariable=self.position_text, font="TkFixedFont").grid(row=2, columnspan=3, sticky="w")
        ttk.Label(self, textvariable=self.pin_text, style="Muted.TLabel").grid(row=3, columnspan=3, sticky="w")
        jog = ttk.Frame(self)
        jog.grid(row=4, columnspan=3, sticky="ew", pady=2)
        ttk.Label(jog, text="Step (mm)").grid(row=0, column=0, sticky="w")
        ttk.Combobox(jog, textvariable=self.step, values=(.1, 1, 5, 10), width=7).grid(row=0, column=1, padx=(4, 10))
        ttk.Label(jog, text="Feed (mm/min)").grid(row=0, column=2)
        ttk.Entry(jog, textvariable=self.rate, width=7).grid(row=0, column=3, padx=(4, 0))
        arrows = ttk.Frame(self)
        arrows.grid(row=5, columnspan=3)
        for name, row, column, axis, sign in (("Y +", 0, 1, "Y", 1), ("X −", 1, 0, "X", -1),
                                             ("X +", 1, 2, "X", 1), ("Y −", 2, 1, "Y", -1)):
            self.buttons[name] = ttk.Button(arrows, text=name.replace("−", "-"), width=8, padding=(6, 2),
                                            command=lambda a=axis, s=sign: self.jog(a, s))
            self.buttons[name].grid(row=row, column=column, padx=2, pady=1)
        self.buttons["Cancel jog"] = ttk.Button(arrows, text="Cancel jog", padding=(6, 2), command=self.cancel_jog)
        self.buttons["Cancel jog"].grid(row=1, column=1, padx=2)
        for row, entries in enumerate((
            (("Home", lambda: self.perform("home")), ("Set paper XY zero", lambda: self.perform("zero")), ("Setup…", self.setup)),
            (("Pen up", lambda: self.pen(True)), ("Pen down", lambda: self.pen(False)), ("Unlock alarm", lambda: self.perform("unlock"))),
            (("Read GRBL", self.read_report), ("Connection log", self.show_log), ("Disconnect", self.disconnect)),
            (("Reset / abort", self.reset),),
        ), start=6):
            for column, (name, command) in enumerate(entries):
                label = {"Set paper XY zero": "Paper XY zero", "Connection log": "Log", "Setup…": "Setup..."}.get(name, name)
                button = ttk.Button(self, text=label, command=command, padding=(5, 2))
                button.grid(row=row, column=column, sticky="ew", padx=(0, 3), pady=1,
                            columnspan=3 if name == "Reset / abort" else 1)
                self.buttons[name] = button
        studio.root.after(80, self.poll)

    def error(self, message):
        self.studio.status.set(message)
        messagebox.showerror("Plotter control", message, parent=self.studio.root)

    def find_ports(self):
        try:
            available = ports()
        except OSError as exc:
            self.error(str(exc))
            return
        self.port_picker.configure(values=available)
        if self.studio.port.get() not in available:
            self.studio.port.set(available[0] if available else "")
        self.connection_text.set(f"Found {len(available)} port(s). Auto detect checks GRBL and baud.")

    def auto_detect(self, port=None, baud=None):
        if self.scanning:
            self.scan_cancel.set()
            self.connection_text.set("Cancelling scan…")
            return
        if self.session and self.session.thread.is_alive():
            self.error("Disconnect before scanning other ports.")
            return
        self.scan_cancel.clear()
        self.scanning = True
        self.buttons["Auto detect"].configure(text="Cancel scan")
        self.connection_text.set("Looking for a GRBL controller…")
        def work():
            try:
                device = detect(port=port, baud=baud, cancel=self.scan_cancel,
                                progress=lambda text: self.messages.put(("progress", text)))
                self.messages.put(("found", device))
            except (OSError, ValueError) as exc:
                self.messages.put(("scan_error", str(exc)))
        self.scan_thread = Thread(target=work, daemon=True)
        self.scan_thread.start()

    def connect(self):
        if self.scanning or (self.session and self.session.thread.is_alive()):
            return
        try:
            self.session = Controller(self.studio.port.get(), int(self.studio.baud.get()))
        except ValueError as exc:
            self.error(str(exc))
            return
        self.studio.controller_report = None
        self.connection_text.set(f"Connecting to {self.session.port} at {self.session.baud}…")
        self.session.start()

    def perform(self, kind, **values):
        try:
            if self.session is None:
                raise ValueError("Connect to the Arduino first.")
            self.session.request(kind, **values)
        except ValueError as exc:
            self.error(str(exc))
        else:
            self.studio.status.set(f"Plotter: {kind} requested…")

    def jog(self, axis, sign):
        try:
            distance = float(self.step.get())
            if distance <= 0:
                raise ValueError("Enter a positive step size.")
            jog_command(axis, distance * sign, self.rate.get())
        except ValueError as exc:
            self.error(str(exc))
            return
        self.perform("jog", axis=axis, distance=distance * sign, feed=self.rate.get())

    def pen(self, up):
        self.perform("pen", command=(self.studio.pen_up if up else self.studio.pen_down).get(),
                     servo=self.studio.firmware.get() == SERVO_PROFILE, settle=self.studio.settle.get())

    def cancel_jog(self):
        if self.session:
            self.session.cancel_jog()
            self.studio.status.set("Jog cancel requested; waiting for GRBL to stop.")

    def reset(self):
        if self.session:
            self.session.reset()
            self.studio.status.set("Reset requested. Reconnect and re-establish the plotter position.")

    def disconnect(self):
        if self.session:
            self.session.close()

    def read_report(self):
        self.show_report = True
        self.perform("refresh")

    def show_log(self):
        content = self.session.snapshot()["log"] if self.session else "No connection yet."
        self.studio.text_dialog("GRBL connection log", content)

    def setup(self):
        if not self.session:
            self.error("Connect to the Arduino first.")
            return
        session = self.session
        current = session.snapshot()["settings"]
        dialog = tk.Toplevel(self.studio.root)
        dialog.title("Plotter setup — controller settings")
        dialog.transient(self.studio.root)
        dialog.geometry("560x490")
        panel = ttk.Frame(dialog, padding=12)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Values read from this Arduino", style="Title.TLabel").pack(anchor="w")
        ttk.Label(panel, text="Apply saves changed fields to controller memory. Read GRBL to refresh.",
                  wraplength=520).pack(anchor="w", pady=(3, 8))
        tabs = ttk.Notebook(panel)
        tabs.pack(fill="both", expand=True)
        variables = {}
        for group in ("Motion", "Homing", "Pen"):
            page = ttk.Frame(tabs, padding=8)
            page.columnconfigure(1, weight=1)
            tabs.add(page, text=group)
            row = 0
            for number, category, label, *_ in SETUP_FIELDS:
                if category != group or number not in current:
                    continue
                variable = tk.StringVar(value=f"{current[number]:g}")
                variables[number] = variable
                ttk.Label(page, text=f"${number}  {label}").grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
                ttk.Entry(page, textvariable=variable, width=12).grid(row=row, column=1, sticky="ew")
                row += 1
            if group == "Homing":
                help_text = "Enable homing only after installing and checking the switches.\nThe supplied firmware homes X and Y together."
            elif group == "Motion":
                help_text = "Calibration: new steps/mm = current steps/mm ×\ncommanded distance ÷ measured distance."
            else:
                help_text = "The supplied servo firmware needs laser mode $32=0.\nSet and test lift commands on the Machine and Control tabs."
            ttk.Label(page, text=help_text, wraplength=480, style="Muted.TLabel").grid(row=row, columnspan=2, sticky="w", pady=(10, 0))
        def apply():
            try:
                if self.session is not session:
                    raise ValueError("Connection changed. Reopen Setup for the current Arduino.")
                # Reject stale editors instead of overwriting a newer settings read.
                actual = session.snapshot()["settings"]
                if actual != current:
                    raise ValueError("Controller settings changed. Reopen Setup to use the current values.")
                changes = setting_changes({n: v.get() for n, v in variables.items()}, current)
                if changes:
                    session.request("settings", values=changes)
            except ValueError as exc:
                messagebox.showerror("Plotter setup", str(exc), parent=dialog)
                return
            dialog.destroy()
            self.studio.status.set("Applying controller settings…" if changes else "No settings changed.")
        ttk.Button(panel, text="Apply changed settings", command=apply).pack(anchor="e", pady=(10, 0))

    def copy_travel(self):
        values = self.session.snapshot()["settings"] if self.session else {}
        if not {130, 131}.issubset(values):
            self.error("Connect and read GRBL before copying controller travel.")
            return
        self.studio.machine_width.set(f"{values[130]:g}")
        self.studio.machine_height.set(f"{values[131]:g}")
        self.studio.status.set("Copied controller X/Y travel. Verify the usable paper area on your plotter.")

    def poll(self):
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except Empty:
                break
            if kind == "progress":
                self.connection_text.set(value)
            else:
                self.scanning = False
                self.buttons["Auto detect"].configure(text="Auto detect")
                if kind == "found" and not self.scan_cancel.is_set() and not self.closing:
                    self.studio.port.set(value.port)
                    self.studio.baud.set(str(value.baud))
                    self.connect()
                else:
                    self.connection_text.set(str(value) if kind == "scan_error" else "Scan cancelled.")
        active = self.session is not None and self.session.thread.is_alive()
        snap = self.session.snapshot() if self.session else {}
        if self.session:
            self.studio.controller_report = ((self.session.port, self.session.baud, snap["report"])
                                             if snap["report"] and snap["connected"] else None)
            while True:
                try:
                    kind, value = self.session.events.get_nowait()
                except Empty:
                    break
                if kind == "error":
                    self.show_report = False
                    if not self.closing:
                        self.error(value)
                elif kind == "connected":
                    self.connection_text.set(value)
                    self.studio.status.set(value)
                elif kind == "disconnected":
                    self.connection_text.set(value)
                    self.studio.status.set(value)
                    self.show_report = False
                elif kind == "done":
                    self.studio.status.set("Command acknowledged. Live status shows motion completion.")
                    if value == "refresh" and self.show_report:
                        self.show_report = False
                        dialog, controls = self.studio.text_dialog("GRBL connection report", snap["report"])
                        def copy(report=snap["report"], window=dialog):
                            window.clipboard_clear()
                            window.clipboard_append(report)
                        ttk.Button(controls, text="Copy report", command=copy).pack(side="right")
        fresh = snap.get("fresh", False)
        ready = snap.get("connected", False) and not snap.get("busy", True) and fresh
        state = snap.get("state", "Disconnected")
        self.state_text.set(state + (" · waiting for status" if active and not fresh else ""))
        def xy(position):
            return f"X {position[0]:9.3f}   Y {position[1]:9.3f}" if position and fresh else "—"
        self.position_text.set(f"Work mm: {xy(snap.get('work'))}\nMach mm: {xy(snap.get('machine'))}")
        self.pin_text.set("Active inputs: " + (snap.get("pins") or ("none" if fresh else "—")))
        for name, button in self.buttons.items():
            if name in {"Find ports", "Connect"}:
                enabled = not active and not self.scanning
            elif name == "Auto detect":
                enabled = not active
            elif name in {"Disconnect", "Reset / abort"}:
                enabled = active
            elif name == "Connection log":
                enabled = self.session is not None
            elif name == "Cancel jog":
                enabled = active and (state == "Jog" or snap.get("busy", False))
            elif name == "Unlock alarm":
                enabled = ready and state == "Alarm"
            elif name in {"Home", "Setup…", "Read GRBL"}:
                enabled = ready and state in {"Idle", "Alarm"}
            else:
                enabled = ready and state == "Idle"
            button.state(["!disabled"] if enabled and not self.closing else ["disabled"])
        self.port_picker.configure(state="disabled" if active or self.scanning else "normal")
        self.baud_picker.configure(state="disabled" if active or self.scanning else "normal")
        if self.closing:
            if not active and not (self.scan_thread and self.scan_thread.is_alive()):
                self.studio.root.destroy()
                return
        self.studio.root.after(80, self.poll)

    def shutdown(self):
        self.closing = True
        self.scan_cancel.set()
        if self.session:
            self.session.close()
