"""Read-only GRBL detection; baud changes here configure the host UART only."""
from __future__ import annotations

from dataclasses import dataclass
from threading import Event
from time import monotonic

import serial
from serial.tools.list_ports import comports

from .controller import parse_status

BAUD_RATES = (115200, 57600, 38400, 19200, 9600, 230400, 250000)


@dataclass(frozen=True)
class Device:
    port: str
    baud: int
    identity: str


def detect(*, port: str | None = None, baud: int | None = None, cancel: Event | None = None,
           progress=lambda text: None, serial_factory=serial.Serial, port_provider=comports,
           probe_seconds: float = 2.5) -> Device:
    """Return the first GRBL responder. Never unlock, home, or write settings."""
    if baud is not None and not 1200 <= baud <= 2000000:
        raise ValueError("Enter a baud rate between 1200 and 2000000.")
    candidates = [port] if port else [item.device for item in port_provider()]
    # Prefer outbound cu.* ports on macOS and avoid probing both aliases.
    candidates = sorted(set(candidates), key=lambda p: (not p.startswith("/dev/cu."), p))
    candidates = [p for p in candidates if not (p.startswith("/dev/tty.") and p.replace("/dev/tty.", "/dev/cu.", 1) in candidates)]
    if not candidates:
        raise ValueError("No serial ports found. Connect the Arduino with a USB data cable and scan again.")
    rates = (baud,) if baud is not None else BAUD_RATES
    failures = []
    for candidate in candidates:
        for rate in rates:
            if cancel and cancel.is_set():
                raise ValueError("Connection scan cancelled.")
            progress(f"Checking {candidate} at {rate}…")
            try:
                with serial_factory(candidate, rate, timeout=.05, write_timeout=.5) as connection:
                    deadline = monotonic() + probe_seconds
                    buffer = b""
                    last_query = 0.0
                    banner = ""
                    while monotonic() < deadline:
                        if cancel and cancel.is_set():
                            raise ValueError("Connection scan cancelled.")
                        if monotonic() - last_query >= .3:
                            connection.write(b"?")
                            last_query = monotonic()
                        buffer += connection.read(max(1, min(connection.in_waiting, 4096)))
                        if len(buffer) > 16384:
                            buffer = b""
                        while b"\n" in buffer:
                            raw, buffer = buffer.split(b"\n", 1)
                            line = raw.strip().decode("ascii", errors="replace")
                            if line.startswith("Grbl 1.1"):
                                banner = line
                            # Require a valid 1.1 position response, not arbitrary
                            # readable text or an Arduino USB vendor identifier.
                            if parse_status(line):
                                return Device(candidate, rate, banner or "GRBL 1.1 status response")
            except (OSError, serial.SerialException) as exc:
                failures.append(f"{candidate}: {exc}")
                break  # A busy/missing port will not improve at another baud.
    detail = f" Last port error: {failures[-1]}" if failures else ""
    raise ValueError("No GRBL controller responded at the tested rates. Close other serial apps and check the cable/firmware." + detail)
