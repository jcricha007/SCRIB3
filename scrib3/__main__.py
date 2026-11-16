"""Desktop launch and terminal-assisted GRBL connection."""
from __future__ import annotations

import argparse


def main(argv=None):
    parser = argparse.ArgumentParser(description="SCRIB3 pen plotter studio")
    parser.add_argument("--scan", action="store_true", help="Detect a GRBL controller, print its port/baud, and exit")
    parser.add_argument("--connect", metavar="PORT", help="Connect the app to PORT, or use 'auto' to detect")
    parser.add_argument("--baud", default="auto", help="Host baud rate, or 'auto' to scan (default)")
    args = parser.parse_args(argv)
    try:
        baud = None if args.baud == "auto" else int(args.baud)
        if baud is not None and not 1200 <= baud <= 2000000:
            raise ValueError
    except ValueError:
        parser.error("--baud must be 'auto' or a rate between 1200 and 2000000")
    if args.scan:
        from .discovery import detect
        try:
            found = detect(port=None if args.connect in (None, "auto") else args.connect,
                           baud=baud, progress=print)
        except (OSError, ValueError) as exc:
            parser.exit(1, f"{exc}\n")
        print(f"GRBL found: port={found.port} baud={found.baud}\n{found.identity}")
        return
    from .app import main as desktop
    desktop(connect=args.connect, baud=baud)


if __name__ == "__main__":
    main()
