"""Stage offline exports on the destination filesystem before replacing a file."""
from __future__ import annotations

import os
from pathlib import Path
from stat import S_IMODE, S_ISREG
from tempfile import TemporaryDirectory
from typing import Callable


def _export_target(path: Path) -> tuple[int, ...] | None:
    try:
        status = path.lstat()
    except FileNotFoundError:
        return None
    if not S_ISREG(status.st_mode):
        raise ValueError("Export to a regular file, not a link or directory.")
    if not os.access(path, os.W_OK):
        raise PermissionError("The destination file is not writable.")
    return (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns,
            status.st_ctime_ns, S_IMODE(status.st_mode))


def write_atomic_export(path: Path, encode: Callable[[Path], object]) -> None:
    """Publish only after the encoder returns and closes its handles."""
    original = _export_target(path)
    with TemporaryDirectory(prefix=".scrib3-export-", dir=path.parent) as folder:
        staged = Path(folder) / ("export" + path.suffix)
        encode(staged)
        if original is not None:
            staged.chmod(original[-1] & 0o777)
        # Best-effort concurrent edit detection; no portable atomic compare-and-swap.
        if _export_target(path) != original:
            raise ValueError("The destination changed during export. Choose Save again.")
        staged.replace(path)
