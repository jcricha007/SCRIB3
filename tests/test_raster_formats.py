from threading import Event

import pytest
from PIL import Image, ImageDraw, features

from scrib3.artwork_import import CONVERSION_EXTENSIONS, IMPORT_FORMATS, ImportOptions, read_artwork
from scrib3.drawing import Sheet, fit_to_sheet
from scrib3.gcode import Machine, generate_gcode
from scrib3.raster import ImportCancelled, load_raster


@pytest.mark.parametrize("extension,codec", [
    (".jpg", "JPEG"), (".JPEG", "JPEG"), (".bmp", "BMP"),
    (".webp", "WEBP"), (".tif", "TIFF"), (".TIFF", "TIFF"),
])
def test_local_trace_preserves_distinct_ordinary_strokes(tmp_path, extension, codec, monkeypatch):
    if codec == "WEBP" and not features.check("webp"):
        pytest.skip("This Pillow build does not include WebP")
    path = tmp_path / ("line-art" + extension)
    drawing = Image.new("RGB", (64, 48), "white")
    pencil = ImageDraw.Draw(drawing)
    pencil.line([(8, 8), (40, 8)], fill="black", width=3)
    pencil.line([(16, 30), (50, 30)], fill="black", width=3)
    drawing.save(path, format=codec)
    original = path.read_bytes()

    def no_converter(*args, **kwargs):
        pytest.fail("Direct raster import must not invoke a converter")

    monkeypatch.setattr("scrib3.artwork_import.run_converter", no_converter)
    result = read_artwork(path)
    assert result.image.size == (64, 48)
    assert result.note.startswith("Centerline")
    assert len(result.drawing) == 2
    for stroke in result.drawing:
        assert len(stroke) >= 2
        assert max(y for x, y in stroke) - min(y for x, y in stroke) <= 2
    sheet = Sheet(66, 50, 3)
    program = generate_gcode(fit_to_sheet(result.drawing, sheet), sheet,
                             Machine(66, 50, 100, "M5", "M3 S70"), dry_run=True)
    assert program.count("G0 X") == 2
    assert "M3 S70" not in program
    assert path.read_bytes() == original
    assert extension.lower() in CONVERSION_EXTENSIONS
    assert "*" + extension.lower() in IMPORT_FORMATS[0][1].split()


def test_jpeg_applies_exif_orientation(tmp_path):
    path = tmp_path / "phone.jpeg"
    image = Image.new("RGB", (36, 20), "white")
    exif = image.getexif()
    exif[274] = 6  # Standard orientation, 90 degrees clockwise.
    image.save(path, exif=exif)
    assert load_raster(path).size == (20, 36)


@pytest.mark.parametrize("suffix,codec", [(".tiff", "TIFF"), (".webp", "WEBP")])
def test_rejects_multi_frame_artwork(tmp_path, suffix, codec):
    if codec == "WEBP" and not features.check("webp"):
        pytest.skip("This Pillow build does not include WebP")
    path = tmp_path / ("multiple" + suffix)
    Image.new("RGB", (20, 20), "black").save(
        path, format=codec, save_all=True, append_images=[Image.new("RGB", (20, 20), "white")],
    )
    with pytest.raises(ValueError, match="single-page"):
        read_artwork(path)


def test_mismatched_cancellation_or_vector_requests_are_refused(tmp_path):
    renamed = tmp_path / "wrong.jpeg"
    Image.new("RGB", (20, 20), "white").save(renamed, format="PNG")
    with pytest.raises(ValueError, match="decode.*JPEG"):
        read_artwork(renamed)
    with pytest.raises(ValueError, match="requires Trace"):
        read_artwork(renamed, ImportOptions(method="Vector paths"))
    cancel = Event()
    cancel.set()
    with pytest.raises(ImportCancelled):
        read_artwork(renamed, cancel=cancel)


def test_pixel_budget_checks_before_conversion(tmp_path, monkeypatch):
    path = tmp_path / "large.bmp"
    Image.new("RGB", (11, 11), "white").save(path)
    monkeypatch.setattr("scrib3.raster.MAX_IMAGE_PIXELS", 120)
    with pytest.raises(ValueError, match="Resize"):
        load_raster(path)
