"""Prepare the Mac environment and launch SCRIB3 from any working directory."""

from __future__ import annotations

import argparse
import fcntl
from pathlib import Path
import subprocess
import sys
import venv

PYTHON_PROBE = (
    "import sys, tkinter, pip; "
    "sys.exit(0 if sys.version_info >= (3, 12) else 1)"
)

DESKTOP_CHECK = """
import platform
import tkinter as tk
from importlib.metadata import version
from scrib3.app import Studio
from scrib3.grbl import ports

root = tk.Tk()
root.withdraw()
Studio(root)
root.update_idletasks()
print(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}")
print(f"Tk {root.tk.call('package', 'require', 'Tk')}")
print(f"svgelements {version('svgelements')} and pySerial {version('pyserial')}")
root.destroy()
devices = ports()
print("Serial ports " + (", ".join(devices) if devices else "(none detected)"))
print("SCRIB3 startup check passed")
"""


def prepare_environment(repo: Path) -> Path:
    environment = repo / ".venv-macos"
    python = environment / "bin" / "python"
    # Serialise installation if the launcher is opened twice. The OS releases
    # the lock when the process exits, including after an interrupted install.
    with (repo / ".venv-macos.lock").open("a") as lock:
        print("Preparing SCRIB3 for macOS…", flush=True)
        fcntl.flock(lock, fcntl.LOCK_EX)
        usable = False
        if python.is_file():
            try:
                probe = subprocess.run(
                    [str(python), "-c", PYTHON_PROBE],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                usable = probe.returncode == 0
            except OSError:
                pass
        if not usable:
            venv.EnvBuilder(with_pip=True, symlinks=True).create(environment)
        subprocess.run(
            [str(python), "-m", "pip", "install", "--disable-pip-version-check",
             "-r", str(repo / "requirements.txt")],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            [str(python), "-c", DESKTOP_CHECK],
            cwd=repo,
            check=True,
        )
    return python


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check setup and exit.")
    parser.add_argument("--connect", metavar="PORT", help="Connect to PORT, or auto-detect with 'auto'.")
    parser.add_argument("--baud", default="auto", help="Host baud rate, or 'auto'.")
    parser.add_argument("--scan", action="store_true", help="Print detected GRBL port and baud, then exit.")
    args = parser.parse_args()
    if args.check and (args.connect or args.scan):
        parser.error("--check cannot be combined with --connect or --scan")
    if args.baud != "auto":
        try:
            rate = int(args.baud)
            if not 1200 <= rate <= 2000000:
                raise ValueError
        except ValueError:
            parser.error("--baud must be 'auto' or a rate between 1200 and 2000000")
    launch_args = ["--baud", args.baud]
    if args.connect:
        launch_args.extend(["--connect", args.connect])
    if args.scan:
        launch_args.append("--scan")
    repo = Path(__file__).resolve().parents[1]
    try:
        python = prepare_environment(repo)
        if args.check:
            return 0
        return subprocess.call([str(python), "-m", "scrib3", *launch_args], cwd=repo)
    except subprocess.CalledProcessError as exc:
        print(f"SCRIB3 setup stopped with exit code {exc.returncode}. Resolve the error above and run the launcher again.",
              file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"SCRIB3 setup or launch failed. {exc}", file=sys.stderr)
        print("Resolve the error above, then run Run-SCRIB3.command again.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
