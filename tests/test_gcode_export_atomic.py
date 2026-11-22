from pathlib import Path

import pytest

from scrib3 import app
from scrib3.drawing import Sheet
from scrib3.gcode import Machine, review_gcode, write_program


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("units", ["mm", "in"])
def test_saved_program_is_exact_review(tmp_path, dry_run, units):
    reviewed = review_gcode((((1, 2), (17, 13)),), Sheet(20, 20, 1),
                            Machine(25, 25, 600, "M5", "M3 S100"),
                            units, dry_run=dry_run)
    target = tmp_path / "reviewed.gcode"
    target.write_bytes(b"previous file")
    write_program(target, reviewed.program)
    assert target.read_bytes() == reviewed.program.encode("ascii")
    assert list(tmp_path.iterdir()) == [target]


def test_partial_write_never_reaches_destination(tmp_path, monkeypatch):
    target = tmp_path / "reviewed.gcode"
    target.write_bytes(b"previous file")
    write_bytes = Path.write_bytes

    def partial(staged, payload):
        assert staged.parent.parent == tmp_path
        write_bytes(staged, payload[:4])
        raise OSError("synthetic disk error")

    monkeypatch.setattr(Path, "write_bytes", partial)
    with pytest.raises(OSError, match="disk error"):
        write_program(target, "G21 G90\n")
    assert target.read_bytes() == b"previous file"
    assert list(tmp_path.iterdir()) == [target]


def test_failed_save_reports_error_without_success_status(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    target = tmp_path / "reviewed.gcode"
    target.mkdir()
    status, error = Mock(), Mock()
    dialog = object()
    monkeypatch.setattr(app.filedialog, "asksaveasfilename", lambda **kwargs: str(target))
    monkeypatch.setattr(app.messagebox, "showerror", error)
    app.Studio.save_program(SimpleNamespace(status=status), dialog, "G21 G90\n")
    assert error.call_args.args[0] == "Save G-code"
    assert "regular file" in error.call_args.args[1]
    assert error.call_args.kwargs == {"parent": dialog}
    status.set.assert_not_called()
