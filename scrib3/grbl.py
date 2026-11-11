from __future__ import annotations

from time import monotonic, sleep

import serial
from serial.tools import list_ports


def ports() -> list[str]:
    return sorted(port.device for port in list_ports.comports())


def _receive(connection, seconds: float, finished) -> list[str]:
    deadline = monotonic() + seconds
    lines: list[str] = []
    pending = bytearray()
    while monotonic() < deadline and len(lines) < 250:
        pending.extend(connection.read_until(b"\n", size=512))
        if len(pending) > 512:
            raise ValueError("The controller returned an oversized serial line.")
        if pending.endswith(b"\n"):
            line = pending.decode("ascii", errors="replace").strip()
            pending.clear()
            if line:
                lines.append(line)
                if finished(line):
                    break
    return lines


def inspect(port: str, baud: int = 115200) -> str:
    """Collect the startup banner, status, build information, and settings."""
    if not port or not 1 <= baud <= 2_000_000:
        raise ValueError("Select a serial port and enter a valid baud rate.")
    with serial.Serial(port, baud, timeout=0.2, write_timeout=1) as connection:
        startup = _receive(connection, 2.0, lambda line: line.startswith("Grbl "))
        connection.write(b"?")
        status = _receive(connection, 1.5, lambda line: line.startswith("<") and line.endswith(">"))
        if not any(line.startswith(("Grbl ", "<")) for line in startup + status):
            raise ValueError("No GRBL banner or status received. Check the port, baud, and firmware.")
        report = startup + ["?", *status]
        for command in ("$I", "$$", "$G", "$#"):
            connection.write((command + "\n").encode("ascii"))
            reply = _receive(connection, 2.0, lambda line: line == "ok" or line.startswith("error:"))
            report.extend([command, *reply])
            if not reply or not (reply[-1] == "ok" or reply[-1].startswith("error:")):
                report.append("(response timed out before acknowledgement)")
                break
        # Overrides are reported intermittently. Request a bounded series of status snapshots.
        for _ in range(20):
            if any(line.startswith("<") and "|Ov:" in line for line in report):
                break
            sleep(0.2)
            connection.write(b"?")
            snapshot = _receive(
                connection, 0.5, lambda line: line.startswith("<") and line.endswith(">"),
            )
            report.extend(["?", *snapshot])
            if not snapshot:
                break
    return "\n".join(report)
