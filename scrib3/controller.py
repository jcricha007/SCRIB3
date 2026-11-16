"""Single-owner GRBL connection. Each operation waits for acknowledgement.

The serial worker also services realtime controls while waiting for a command
(including homing). Only one operation can be submitted at a time.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import isfinite
from queue import Empty, Queue
import re
from threading import Event, Lock, Thread
from time import monotonic

import serial

from .firmware import ServoSettings
from .gcode import pen_command


# Editable EEPROM fields; all other firmware settings remain untouched.
SETUP_FIELDS = (
    (3, "Motion", "Direction mask (X=1, Y=2, Z=4)", 0, 7, True),
    (100, "Motion", "X steps/mm", .001, 100000, False),
    (101, "Motion", "Y steps/mm", .001, 100000, False),
    (110, "Motion", "X maximum rate (mm/min)", .001, 100000, False),
    (111, "Motion", "Y maximum rate (mm/min)", .001, 100000, False),
    (120, "Motion", "X acceleration (mm/s²)", .001, 100000, False),
    (121, "Motion", "Y acceleration (mm/s²)", .001, 100000, False),
    (130, "Motion", "X maximum travel (mm)", .001, 10000, False),
    (131, "Motion", "Y maximum travel (mm)", .001, 10000, False),
    (5, "Homing", "Invert limit pins (0/1)", 0, 1, True),
    (20, "Homing", "Soft limits (0/1)", 0, 1, True),
    (21, "Homing", "Hard limits (0/1)", 0, 1, True),
    (22, "Homing", "Enable homing (0/1)", 0, 1, True),
    (23, "Homing", "Homing direction mask (X=1, Y=2, Z=4)", 0, 7, True),
    (24, "Homing", "Homing locate rate (mm/min)", .001, 100000, False),
    (25, "Homing", "Homing seek rate (mm/min)", .001, 100000, False),
    (26, "Homing", "Switch debounce (ms)", 0, 65535, True),
    (27, "Homing", "Switch pull-off (mm)", .001, 1000, False),
    (30, "Pen", "Spindle maximum ($30)", .001, 100000, False),
    (31, "Pen", "Spindle minimum ($31)", 0, 100000, False),
    (32, "Pen", "Laser mode (0/1)", 0, 1, True),
)


def positive(value, label: str, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Enter a numeric {label}.") from exc
    number = round(number, 3)
    if not isfinite(number) or not .001 <= number <= maximum:
        raise ValueError(f"{label.capitalize()} must be between 0.001 and {maximum:g}.")
    return number


def jog_command(axis: str, distance, feed) -> str:
    if axis not in ("X", "Y"):
        raise ValueError("Choose the X or Y axis.")
    try:
        amount = float(distance)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a numeric jog distance.") from exc
    step = positive(abs(amount), "jog distance in mm", 100)
    rate = positive(feed, "jog rate in mm/min", 100000)
    return f"$J=G21 G91 {axis}{step if amount > 0 else -step:.3f} F{rate:.3f}"


def setting_changes(values: dict, current: dict[int, float]) -> dict[int, float]:
    definitions = {item[0]: item for item in SETUP_FIELDS}
    result = {}
    for number, raw in values.items():
        if number not in definitions or number not in current:
            raise ValueError(f"Read the supported setting ${number} from this controller first.")
        _, _, label, low, high, integer = definitions[number]
        try:
            value = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Enter a numeric value for {label}.") from exc
        if not isfinite(value) or not low <= value <= high or (integer and value != int(value)):
            raise ValueError(f"${number}: enter {'a whole number' if integer else 'a number'} from {low:g} to {high:g}.")
        value = round(value, 3)
        if value != current[number]:
            result[number] = value
    merged = current | result
    if merged.get(20) == 1 and merged.get(22) != 1:
        raise ValueError("Soft limits require homing ($22=1).")
    if merged.get(30, 1) <= merged.get(31, 0):
        raise ValueError("Spindle maximum $30 must be greater than minimum $31.")
    return result


@dataclass(frozen=True)
class Status:
    state: str
    position: tuple[float, ...]
    machine_coordinates: bool
    wco: tuple[float, ...] | None
    override: int | None
    pins: str
    raw: str


def parse_status(line: str) -> Status | None:
    if not line.startswith("<") or not line.endswith(">"):
        return None
    fields = line[1:-1].split("|")
    if fields[0].split(":")[0] not in {"Idle", "Run", "Jog", "Home", "Alarm", "Hold", "Door", "Check", "Sleep"}:
        return None
    data = dict(field.split(":", 1) for field in fields[1:] if ":" in field)
    try:
        machine = "MPos" in data
        def vector(value):
            numbers = tuple(float(item) for item in value.split(","))
            if len(numbers) != 3 or not all(isfinite(item) for item in numbers):
                raise ValueError("Invalid position")
            return numbers
        position = vector(data["MPos"] if machine else data["WPos"])
        wco = vector(data["WCO"]) if "WCO" in data else None
        override = int(data["Ov"].split(",")[2]) if "Ov" in data else None
        return Status(fields[0], position, machine, wco, override, data.get("Pn", ""), line)
    except (KeyError, ValueError, IndexError):
        return None


class SessionFault(OSError):
    """The command stream cannot safely accept another line until reconnection."""


class Controller:
    def __init__(self, port: str, baud: int = 115200, *, serial_factory=serial.Serial):
        if not port or not 1200 <= baud <= 2000000:
            raise ValueError("Select a port and a baud rate between 1200 and 2000000.")
        self.port, self.baud = port, baud
        self.factory = serial_factory
        self.events = Queue()
        self.operations = Queue(maxsize=1)
        self.stop = Event()
        self.reset_requested = Event()
        self.cancel_requested = Event()
        self.lock = Lock()
        self.connected = False
        self.busy = True
        self.fault = ""
        self.state = "Connecting"
        self.status: Status | None = None
        self.status_time = 0.0
        self.settings: dict[int, float] = {}
        self.wco = None
        self.override = None
        self.override_line = ""
        self.operation_kind = ""
        self.aborted = False
        self.report = ""
        self.log = deque(maxlen=500)
        self.pending = None
        self.reply = None
        self.lines = []
        self.buffer = b""
        self.poll_pending = False
        self.poll_time = 0.0
        self.connection = None
        self.thread = Thread(target=self._run, daemon=True, name="SCRIB3 serial")

    def start(self):
        self.thread.start()

    def snapshot(self):
        with self.lock:
            status = self.status
            factor = 25.4 if self.settings.get(13) == 1 else 1
            work = machine = None
            # Never label coordinates in mm before $13 has been read.
            if status and 13 in self.settings:
                position = tuple(value * factor for value in status.position)
                offset = tuple(value * factor for value in self.wco) if self.wco else None
                if status.machine_coordinates:
                    machine = position
                    if offset is not None:
                        work = tuple(p - o for p, o in zip(position, offset))
                else:
                    work = position
                    if offset is not None:
                        machine = tuple(p + o for p, o in zip(position, offset))
            return dict(connected=self.connected, busy=self.busy, fault=self.fault,
                        state=self.state, fresh=monotonic() - self.status_time < 2,
                        work=work, machine=machine, pins=status.pins if status else "",
                        settings=dict(self.settings), report=self.report, log="\n".join(self.log))

    def request(self, kind: str, **values):
        if kind not in {"refresh", "jog", "home", "unlock", "zero", "pen", "settings"}:
            raise ValueError("Unsupported controller operation.")
        with self.lock:
            if not self.connected or self.fault:
                raise ValueError("Connect to a responding GRBL controller first.")
            if self.busy:
                raise ValueError("Wait for the current controller operation to finish.")
            self.busy = True
            self.operation_kind = kind
            self.operations.put_nowait((kind, values))

    def cancel_jog(self):
        self.cancel_requested.set()

    def reset(self):
        self.reset_requested.set()

    def close(self):
        self.stop.set()

    def _write(self, data: bytes):
        if self.connection.write(data) != len(data):
            raise SessionFault("Incomplete serial write. Reconnect before continuing.")

    def _note(self, text: str):
        with self.lock:
            self.log.append(text)

    def _pump(self):
        if self.stop.is_set() or self.reset_requested.is_set():
            # Disconnect during motion/unknown execution aborts before closing.
            if self.reset_requested.is_set() or self.pending or self.state not in {"Idle", "Alarm"}:
                self._write(b"\x18")
                self.aborted = True
                self._note("Reset sent. Reconnect and re-establish position before moving.")
            raise SessionFault("Disconnected.")
        now = monotonic()
        if self.cancel_requested.is_set():
            self._write(b"\x85")
            # Repeat until a jog's acknowledgement and subsequent Idle status:
            # an immediate cancel can otherwise arrive before GRBL enters Jog.
            if not self.busy and self.state == "Idle" and now - self.status_time < .5:
                self.cancel_requested.clear()
        # EEPROM writes disable AVR interrupts. Wait for their ack before
        # sending a status byte that the controller could otherwise lose.
        eeprom_write = self.pending and (re.match(r"\$\d+=", self.pending) or self.pending.startswith("G10 "))
        if not eeprom_write and not self.poll_pending and now - self.poll_time >= .25:
            self._write(b"?")
            self.poll_pending = True
            self.poll_time = now
        if self.poll_pending and now - self.poll_time > 3:
            raise SessionFault("GRBL stopped reporting status. Reconnect and check the machine position.")
        chunk = self.connection.read(max(1, min(self.connection.in_waiting, 4096)))
        self.buffer += chunk
        if len(self.buffer) > 16384:
            raise SessionFault("Serial response exceeded the receive limit.")
        while b"\n" in self.buffer:
            raw, self.buffer = self.buffer.split(b"\n", 1)
            line = raw.strip().decode("ascii", errors="replace")
            if not line:
                continue
            if status := parse_status(line):
                with self.lock:
                    self.status = status
                    self.state = status.state
                    self.status_time = monotonic()
                    if status.wco is not None:
                        self.wco = status.wco
                    if status.override is not None:
                        self.override = status.override
                        self.override_line = line
                        if self.report:
                            base = self.report.split("\n<", 1)[0]
                            self.report = base + "\n" + line
                self.poll_pending = False
                continue
            self._note(line)
            if line.startswith("Grbl "):
                if self.connected or self.pending:
                    raise SessionFault("Controller restarted. Reconnect to refresh settings and position.")
                if not line.startswith("Grbl 1.1"):
                    raise SessionFault("These controls require GRBL 1.1.")
                # The USB-open reset can lose our first query in the bootloader.
                self.poll_pending = False
                self.poll_time = 0.0
            if line.startswith("ALARM:"):
                with self.lock:
                    self.state = "Alarm"
                if self.pending:
                    raise SessionFault(f"{line}. Resolve the cause, then reset and reconnect.")
            if self.pending:
                self.lines.append(line)
                if len(self.lines) > 300:
                    raise SessionFault("GRBL response exceeded the line limit.")
                if line == "ok" or line.startswith("error:"):
                    self.reply = line

    def _wait(self, predicate, seconds: float):
        deadline = monotonic() + seconds
        while not predicate():
            if monotonic() >= deadline:
                raise SessionFault("GRBL response timed out. Reset and reconnect before continuing.")
            self._pump()

    def _fresh_status(self):
        # Drain the previous query, then request a status after the last ack.
        if self.poll_pending:
            self._wait(lambda: not self.poll_pending, 4)
        self._write(b"?")
        self.poll_pending = True
        self.poll_time = monotonic()
        self._wait(lambda: not self.poll_pending, 4)

    def _command(self, command: str, timeout: float = 5) -> list[str]:
        if self.stop.is_set() or self.reset_requested.is_set():
            self._pump()
        if self.cancel_requested.is_set() and command.startswith("$J="):
            self.cancel_requested.clear()
            raise ValueError("Jog cancelled before movement.")
        self._note("> " + command)
        self.pending, self.reply, self.lines = command, None, []
        self._write(command.encode("ascii") + b"\n")
        self._wait(lambda: self.reply is not None, timeout)
        lines, reply = self.lines, self.reply
        self.pending = None
        if reply != "ok":
            raise ValueError(f"{command}: {reply}. No following commands were sent.")
        return lines

    def _read_all(self):
        with self.lock:
            previous_units = self.settings.get(13)
            self.settings = {}
            self.report = ""
        report = []
        for command in ("$I", "$$", "$G", "$#"):
            lines = self._command(command)
            report.extend([command, *lines])
            if command == "$$":
                settings = {}
                for line in lines[:-1]:
                    match = re.fullmatch(r"\$(\d+)=([+-]?(?:\d+(?:\.\d*)?|\.\d+))", line)
                    if not match:
                        raise ValueError("Incomplete GRBL settings response. Read GRBL again.")
                    settings[int(match[1])] = float(match[2])
                if not {13, 22}.issubset(settings):
                    raise ValueError("GRBL did not return the required settings ($13 and $22).")
                with self.lock:
                    self.settings = settings
                    if previous_units is not None and previous_units != settings[13]:
                        self.wco = None
        # Ov is intermittent on idle GRBL. Keep polling without inventing it.
        deadline = monotonic() + 4
        while self.override is None and monotonic() < deadline:
            self._pump()
        self._fresh_status()
        if self.status:
            report.append(self.status.raw)
        if self.override is not None:
            report.append(self.override_line)
        with self.lock:
            self.report = "\n".join(report)

    def _operate(self, kind, values):
        self._fresh_status()
        allowed = {"Idle", "Alarm"} if kind in {"refresh", "home", "settings"} else {"Alarm"} if kind == "unlock" else {"Idle"}
        if self.state not in allowed:
            raise ValueError(f"Cannot {kind} while GRBL reports {self.state}.")
        if kind == "refresh":
            self._read_all()
        elif kind == "jog":
            self._command(jog_command(values["axis"], values["distance"], values["feed"]))
        elif kind == "home":
            if self.settings.get(22) != 1:
                raise ValueError("Homing is disabled ($22=0). Configure the switches and homing settings in Setup first.")
            self._command("$H", timeout=180)
            self.wco = None
        elif kind == "unlock":
            self._command("$X")
        elif kind == "zero":
            self._command("G21 G54 G92.1")
            self._command("G10 L20 P1 X0 Y0")
            self.wco = None
        elif kind == "pen":
            family, command, position = pen_command(values["command"])
            if values.get("servo"):
                if family != "PWM":
                    raise ValueError("The uploaded servo firmware uses M3 S or M5.")
                if not {30, 31, 32}.issubset(self.settings) or self.override is None:
                    raise ValueError("Read GRBL to capture servo settings and the spindle override first.")
                servo = ServoSettings(self.settings[30], self.settings[31], self.settings[32], self.override)
                servo.timer_count(None if command == "M5" else position)
            settle = float(values.get("settle", 0))
            if not 0 <= settle <= 10:
                raise ValueError("Pen settle time must be between 0 and 10 seconds.")
            if family == "Z":
                self._command("G21 G90 G94 G54 G49")
            self._command(command)
            if settle:
                self._command(f"G4 P{settle:.3f}", timeout=15)
        elif kind == "settings":
            changes = setting_changes(values["values"], self.settings)
            # Enable homing before soft limits; disable soft limits before homing.
            order = sorted(changes, key=lambda n: -1 if n == 22 and changes[n] == 1 else n)
            with self.lock:
                self.report = ""
            try:
                for number in order:
                    self._command(f"${number}={changes[number]:g}")
            except ValueError:
                # Earlier EEPROM writes may have succeeded; show actual readback.
                self._read_all()
                raise
            else:
                self._read_all()
        self._fresh_status()

    def _run(self):
        try:
            self.connection = self.factory(self.port, self.baud, timeout=.05, write_timeout=.5)
            # Opening a USB serial port can reset an Arduino. Allow its startup
            # banner to settle before sending any newline-terminated command.
            until = monotonic() + 2
            while monotonic() < until:
                self._pump()
            self._fresh_status()
            if self.state not in {"Idle", "Alarm"}:
                raise ValueError(f"Controller reports {self.state}. Connect while idle or in Alarm.")
            self._read_all()
            with self.lock:
                self.connected, self.busy = True, False
            self.events.put(("connected", f"Connected to {self.port} at {self.baud}."))
            while True:
                self._pump()
                try:
                    kind, values = self.operations.get_nowait()
                except Empty:
                    continue
                try:
                    self._operate(kind, values)
                except ValueError as exc:
                    self.events.put(("error", str(exc)))
                else:
                    self.events.put(("done", kind))
                finally:
                    with self.lock:
                        self.busy = False
        except (OSError, ValueError) as exc:
            with self.lock:
                self.fault = str(exc)
            self.events.put(("disconnected", str(exc)))
        finally:
            if self.connection is not None:
                # A timeout leaves execution unknown. Abort before abandoning the
                # session; no command is ever retried after a missing ack.
                if (self.pending or self.connected and self.fault != "Disconnected.") and not self.aborted:
                    try:
                        self._write(b"\x18")
                    except OSError:
                        pass
                self.connection.close()
            with self.lock:
                self.connected, self.busy = False, False
                self.state = "Disconnected"
                self.status = None
                self.settings = {}
                self.report = ""
