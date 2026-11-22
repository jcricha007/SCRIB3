from pathlib import Path

import pytest

from scrib3.drawing import Sheet
from scrib3 import vector_io


DRAWING = (((3, 8), (9, 8), (9, 15), (3, 8)), ((4, 10), (7, 11)))
SHEET = Sheet(25, 20, 1)


@pytest.mark.parametrize("extension", ["svg", "dxf", "json"])
def test_encoder_failure_keeps_existing_destination(tmp_path, monkeypatch, extension):
    target = tmp_path / ("kept." + extension)
    vector_io.write_drawing(target, DRAWING, SHEET)
    original = target.read_bytes()

    def fail_after_writing(staged, format, drawing, sheet):
        assert staged.parent.parent == tmp_path
        staged.write_bytes(b"partial output")
        raise OSError("synthetic write failure")

    monkeypatch.setattr(vector_io, "_write_drawing_file", fail_after_writing)
    with pytest.raises(OSError, match="synthetic"):
        vector_io.write_drawing(target, DRAWING[:1], SHEET)
    assert target.read_bytes() == original
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize("extension", ["svg", "dxf", "json"])
def test_success_closes_stage_and_replaces_with_geometry(tmp_path, extension):
    target = tmp_path / ("ordinary drawing." + extension.upper())
    target.write_bytes(b"old")
    vector_io.write_drawing(target, DRAWING, SHEET)
    reopened = vector_io.read_drawing(target)
    assert [len(stroke) for stroke in reopened] == [4, 2]
    assert reopened[0][0] == reopened[0][-1]
    assert reopened[1][0] != reopened[1][-1]
    assert list(tmp_path.iterdir()) == [target]


def test_replace_failure_keeps_original_and_removes_stage(tmp_path, monkeypatch):
    target = tmp_path / "saved.svg"
    target.write_bytes(b"old")

    def replace_fails(self, destination):
        assert destination == target and self.is_file()
        raise PermissionError("file locked")

    monkeypatch.setattr(Path, "replace", replace_fails)
    with pytest.raises(PermissionError, match="locked"):
        vector_io.write_drawing(target, DRAWING, SHEET)
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


def test_export_refuses_destination_observed_to_change(tmp_path, monkeypatch):
    target = tmp_path / "saved.json"
    original = vector_io._write_drawing_file

    def finish_after_other_writer(*args):
        original(*args)
        target.write_bytes(b"external edit")

    monkeypatch.setattr(vector_io, "_write_drawing_file", finish_after_other_writer)
    with pytest.raises(ValueError, match="destination changed"):
        vector_io.write_drawing(target, DRAWING, SHEET)
    assert target.read_bytes() == b"external edit"
    assert list(tmp_path.iterdir()) == [target]


def test_export_refuses_symlink_without_touching_source(tmp_path):
    orig = tmp_path / "original.svg"
    orig.write_bytes(b"original")
    link = tmp_path / "alias.svg"
    try:
        link.symlink_to(orig.name)
    except (OSError, NotImplementedError):
        pytest.skip("Symbolic links are unavailable")
    with pytest.raises(ValueError, match="link"):
        vector_io.write_drawing(link, DRAWING, SHEET)
    assert link.is_symlink() and orig.read_bytes() == b"original"
