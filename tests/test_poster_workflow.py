from dataclasses import replace
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import pytest
import trimesh

from scrib3.board import Board, Mark, bounds, export_svg, load_board, save_board
from scrib3.canvas_ui import CanvasEditor
from scrib3.cleanup_ui import clean_marks
from scrib3.engineering_sheet import VIEWS, VIEW_GROUP, lay_out, project_views
from scrib3.p1s_workflow import DRY_A4, REGISTER, open_in_studio, qualification_board as make_target
from scrib3.poster_objects import StrokeText, cubic_points, independent_copy
from scrib3.printer_output import Holder, plan_printer
from scrib3.svg_artwork import import_svg


def editor_test_double(board):
    # Exercise the same editor methods as Tk. Only the file/property pickers and repaint are substituted.
    editor = CanvasEditor.__new__(CanvasEditor)
    editor.root, editor.pen, editor.status = Mock(), Mock(), Mock()
    editor.board, editor.selection = board, set()

    def commit(changed, selection=()):
        editor.board = changed.checked()
        editor.selection = changed.text_selection(selection)

    editor.commit = commit
    return editor


def test_separate_svg_pages_preserve_distances_through_normal_import_and_export(tmp_path):
    editor = editor_test_double(Board())
    options = dict(size="Keep SVG page coordinates", fill="Outline", spacing=1, covered="Hide")
    for x, color in ((10, "red"), (110, "blue")):
        source = tmp_path / f"{color}.svg"
        source.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="297mm" height="210mm" viewBox="0 0 297 210">'
            f'<path d="M{x},30h10" stroke="{color}" fill="none"/></svg>'
        )
        with (
            patch("tkinter.filedialog.askopenfilename", return_value=str(source)),
            patch("scrib3.canvas_ui.form", return_value=options),
        ):
            editor.import_file()
    dest = tmp_path / "both.svg"
    export_svg(dest, editor.board)
    a, b = import_svg(dest)
    assert a.points[0] == pytest.approx((10, 30))
    assert b.points[0] == pytest.approx((110, 30))
    for size, width in (("Center at true size", 10), ("Fit to paper", 297 * 0.94)):
        with (
            patch("tkinter.filedialog.askopenfilename", return_value=str(source)),
            patch("scrib3.canvas_ui.form", return_value={**options, "size": size}),
        ):
            editor.import_file()
        start, end = editor.board.marks[-1].points
        assert end[0] - start[0] == pytest.approx(width)
        assert (start[0] + end[0]) / 2 == pytest.approx(148.5)


def test_grouped_cubic_svg_and_editable_text_round_trip(tmp_path):
    file = tmp_path / "mirror.svg"
    file.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="100mm" viewBox="0 0 100 100">'
        '<g id="Car" transform="translate(4 2)"><g id="Mirror"><path stroke="red" fill="none" '
        'd="M1,1 C3,4 5,6 7,2 S10,5 12,4"/></g></g></svg>'
    )
    (curve,) = import_svg(file)
    assert curve.groups == ("Car", "Mirror") and len(curve.controls) == 7
    assert curve.controls[0] == pytest.approx((5, 3))
    text = StrokeText("title", "Ford GT40").marks("#101010", ("Title",))
    board = Board(marks=(curve, *text))
    board = board.transform(
        range(len(board.marks)), angle=90, factor=1.5, mirror_x=True, center=True
    )
    dest = tmp_path / "editable.scrib3"
    save_board(dest, board)
    assert load_board(dest) == board
    assert load_board(Path(__file__).parents[1] / "examples/studio-demo.scrib3").marks
    export_svg(file, board)
    returned = next(m for m in import_svg(file) if m.controls)
    assert returned.groups == curve.groups
    for pt, ref in zip(returned.controls, board.marks[0].controls):
        assert pt == pytest.approx(ref, abs=2e-6)
    editor = editor_test_double(board)
    editor.selection = board.text_selection([1])
    frame = board.marks[1].text.frame
    with patch(
        "scrib3.canvas_ui.form",
        return_value=dict(
            text="GT40 Mk II", font="Serif", size="7", tracking="1", line="1.5", align="Center"
        ),
    ):
        editor.text(edit=True)
    word = editor.board.marks[1].text
    assert (word.value, word.frame) == ("GT40 Mk II", frame)
    assert editor.board.marks[0] == board.marks[0]
    clone = independent_copy(editor.selected(), editor.board.marks)
    assert clone[0].text.key != word.key
    assert clone[0].groups != editor.selected()[0].groups
    assert clone[0].points == editor.selected()[0].points


def test_cleanup_preserves_corner_endpoints_pen_and_editable_geometry():
    path = Mark(
        "#aa1100", ((0, 0), (1, 0.01), (2, -0.01), (3, 0), (4, 0), (4, 2), (4, 4)), ("Body",)
    )
    second = replace(path, color="#112233")
    handles = ((9, 2), (10, 1), (11, 3), (12, 4))
    curve = Mark("#aa1100", cubic_points(handles), controls=handles)
    replacements, n = clean_marks((path, path, second, curve), 0.1, True, False)
    assert replacements[1] is None
    result = [mark for mark in replacements if mark is not None]
    assert n == 1 and len(result) == 3
    assert result[0].points[0] == (0, 0) and result[0].points[-1] == (4, 4)
    assert (4, 0) in result[0].points and result[0].groups == path.groups
    assert result[1].color == second.color and result[2] == curve
    assert path.points[1] == (1, 0.01)
    with pytest.raises(ValueError):
        clean_marks((path,), float("nan"), False, False)


@pytest.mark.parametrize("size", [(297, 210), (279.4, 215.9)])
def test_four_views_share_scale_and_align_for_asymmetric_extents(size):
    mesh = trimesh.creation.box(extents=(30, 10, 6))
    mesh.apply_translation((55, -13, 6))
    views = project_views(mesh)
    board, scale = lay_out(views, *size, "Test sheet", scale=1.25)
    assert scale == 1.25
    geometry = {
        v: bounds([m for m in board.marks if m.groups == (VIEW_GROUP, v) and not m.text])
        for v in VIEWS
    }
    front, top, right = (geometry[k] for k in ("Front", "Top", "Right"))
    assert (front[0], front[2]) == pytest.approx((top[0], top[2]))
    assert (front[1], front[3]) == pytest.approx((right[1], right[3]))
    assert front[2] - front[0] == pytest.approx(30 * scale)
    assert right[2] - right[0] == pytest.approx(10 * scale)
    assert all(0 <= x <= size[0] and 0 <= y <= size[1] for m in board.marks for x, y in m.points)
    with pytest.raises(ValueError, match="fit"):
        lay_out(views, *size, "Test sheet", scale=200)


@pytest.mark.parametrize("target,dry", [(DRY_A4, True), (REGISTER, False)])
def test_p1s_reviewed_plates_preserve_pauses_registration_and_height(tmp_path, target, dry):
    holder = Holder("P1S", 0, -28, 2.75, 5.5)
    board = make_target(target)
    if target == DRY_A4:
        with pytest.raises(ValueError, match="shrink"):
            plan_printer(board, holder)
    plan = plan_printer(board, holder, fit=True, dry=dry)
    path = tmp_path / "P1S.gcode.3mf"
    plan.export(path)
    with ZipFile(path) as z:
        model = ET.fromstring(z.read("3D/3dmodel.model"))
        metadata = {tag.attrib["name"]: tag.text for tag in model.findall("{*}metadata")}
        assert metadata["Application"].startswith("BambuStudio-")
        assert metadata["Designer"] == "SCRIB3"
        data = z.read("Metadata/plate_1.gcode")
        assert data == plan.gcode().encode("ascii")
        assert (
            z.read("Metadata/plate_1.gcode.md5").decode().lower() == hashlib.md5(data).hexdigest()
        )
        assert b"C12" in z.read("Metadata/slice_info.config")
    lines = data.decode().splitlines()
    assert lines.count("M400 U1") == (1 if dry else 2)
    assert ("G1 Z2.750 F600" in lines) == (not dry)
    commands = [line for line in lines if not line.startswith(";")]
    first_xy = next(i for i, line in enumerate(commands) if line.startswith("G1 X"))
    assert commands[first_xy + 1:first_xy + 3] == ["M400", "G4 P10000"]
    assert commands[-2:] == ["M400", "G4 P10000"]
    assert commands.count("G28") == 1 and commands.index("G28") < first_xy
    if not dry:
        last_xy = max(i for i, line in enumerate(commands) if line.startswith("G1 X"))
        assert commands[last_xy + 1:] == ["M400", "G1 Z5.500 F600", "M400", "G4 P10000"]
        for i, cmd in enumerate(commands):
            if cmd == "G1 Z2.750 F600":
                transition = i - 1 if commands[i - 1] == "G4 P10000" else i
                assert commands[transition - 1] == "M400" and commands[transition - 2].startswith("G1 X")
                assert commands[i + 1] == "M400" and commands[i + 2].startswith("G1 X")
    if target == REGISTER:
        assert plan.scale == 1
        # Diamond and cross from different passes share their measured center.
        midpoints = []
        for _, paths in plan.passes:
            midpoints.append(
                {tuple(round((min(v) + max(v)) / 2, 4) for v in zip(*stroke)) for stroke in paths}
            )
        assert len(midpoints[0] & midpoints[1]) == 5
    with (
        patch("scrib3.p1s_workflow.sys.platform", "darwin"),
        patch("scrib3.p1s_workflow.subprocess.run") as launch,
        patch.dict("os.environ", clear=True),
    ):
        launch.return_value.returncode = 0
        open_in_studio(path)
        assert launch.call_args.args[0] == [
            "/usr/bin/open",
            "-a",
            "BambuStudio",
            str(path.resolve()),
        ]
