"""Sliced Bambu 3MF package; plot G-code is retained without slicing."""

from hashlib import md5
from io import BytesIO
import json
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image, ImageDraw
from .atomic_export import write_atomic_export
from .printer_output import PRINTERS

REL = "http://schemas.openxmlformats.org/package/2006/relationships"
BBL = "http://schemas.bambulab.com/package/2021"
CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"


def xml(e):
    return ET.tostring(e, encoding="utf-8", xml_declaration=True)


def relations(entries):
    r = ET.Element("Relationships", xmlns=REL)
    for i, (target, kind) in enumerate(entries, 1):
        ET.SubElement(r, "Relationship", Id=f"rel-{i}", Target="/" + target, Type=kind)
    return xml(r)


def config(values):
    r = ET.Element("config")
    p = ET.SubElement(r, "plate")
    for k, v in values.items():
        ET.SubElement(p, "metadata", key=k, value=str(v))
    return xml(r)


def export_plate(path, plan):
    h = plan.holder
    model_id, w, depth = PRINTERS[h.printer]
    program = plan.gcode().encode("ascii")
    image = Image.new("RGB", (512, 512), "white")
    draw = ImageDraw.Draw(image)
    scale = 500 / max(w, depth)
    points = []
    for color, paths in plan.passes:
        for stroke in paths:
            points.extend(stroke)
            draw.line(
                [(6 + (x + h.offset_x) * scale, 506 - (y + h.offset_y) * scale) for x, y in stroke],
                fill=color,
                width=2,
            )
    xs, ys = zip(*points)
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    types = ET.Element(
        "Types", xmlns="http://schemas.openxmlformats.org/package/2006/content-types"
    )
    for ext, mime in [
        ("rels", "application/vnd.openxmlformats-package.relationships+xml"),
        ("model", "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"),
        ("png", "image/png"),
        ("gcode", "text/x.gcode"),
        ("config", "application/xml"),
        ("json", "application/json"),
        ("md5", "text/plain"),
    ]:
        ET.SubElement(types, "Default", Extension=ext, ContentType=mime)
    model = ET.Element(
        "model",
        unit="millimeter",
        xmlns=CORE,
        attrib={"xml:lang": "en-US", "xmlns:BambuStudio": BBL},
    )
    ET.SubElement(model, "metadata", name="Application").text = "SCRIB3"
    ET.SubElement(model, "metadata", name="BambuStudio:3mfVersion").text = "1"
    ET.SubElement(model, "resources")
    ET.SubElement(model, "build")
    gcode = "Metadata/plate_1.gcode"
    thumb = "Metadata/plate_1.png"

    def encode(staged):
        with ZipFile(staged, "w", ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", xml(types))
            z.writestr(
                "_rels/.rels",
                relations(
                    [
                        (
                            "3D/3dmodel.model",
                            "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel",
                        ),
                        (thumb, REL + "/metadata/thumbnail"),
                    ]
                ),
            )
            z.writestr("3D/3dmodel.model", xml(model))
            z.writestr(
                "Metadata/model_settings.config",
                config(
                    {
                        "plater_id": 1,
                        "plater_name": "SCRIB3",
                        "locked": "false",
                        "filament_maps": "1",
                        "gcode_file": gcode,
                        "thumbnail_file": thumb,
                        "pattern_bbox_file": "Metadata/plate_1.json",
                    }
                ),
            )
            z.writestr(
                "Metadata/_rels/model_settings.config.rels", relations([(gcode, BBL + "/gcode")])
            )
            z.writestr(
                "Metadata/slice_info.config",
                config(
                    {
                        "index": 1,
                        "printer_model_id": model_id,
                        "nozzle_diameters": "0.4",
                        "prediction": int(plan.seconds),
                        "weight": 0,
                        "outside": "false",
                        "support_used": "false",
                        "timelapse_type": 0,
                    }
                ),
            )
            z.writestr(
                "Metadata/project_settings.config",
                json.dumps(
                    {
                        "printer_model": "Bambu Lab " + h.printer,
                        "printer_settings_id": "Bambu Lab " + h.printer + " 0.4 nozzle",
                        "nozzle_diameter": ["0.4"],
                        "printable_area": ["0x0", f"{w}x0", f"{w}x{depth}", f"0x{depth}"],
                        "printable_height": "256" if h.printer == "P1S" else "340",
                    }
                ),
            )
            z.writestr(
                "Metadata/plate_1.json",
                json.dumps(
                    {
                        "version": 2,
                        "bbox_all": bbox,
                        "bbox_objects": [],
                        "filament_colors": [],
                        "filament_ids": [],
                        "first_extruder": 0,
                        "bed_type": "textured_plate",
                        "nozzle_diameter": 0.4,
                        "is_seq_print": False,
                    }
                ),
            )
            for name, pic in [
                (thumb, image),
                ("Metadata/plate_1_small.png", image.resize((128, 128))),
            ]:
                b = BytesIO()
                pic.save(b, format="PNG")
                z.writestr(name, b.getvalue())
            z.writestr(gcode, program)
            z.writestr(gcode + ".md5", md5(program).hexdigest().upper())

    write_atomic_export(path, encode)
