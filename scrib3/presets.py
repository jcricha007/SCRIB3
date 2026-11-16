"""A bundled calibration and one explicitly saved local machine preset.

Presets contain preferences only: no live position, homing state, controller
settings snapshot, port connection, or executable code is restored.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile

from .drawing import Sheet
from .firmware import SERVO_PROFILE
from .gcode import Machine
from .units import factor, number
from .paper_mount import validate_mount

BUILTIN = Path(__file__).with_name("presets") / "john-servo.json"
LEGACY_FIELDS = {"schema_version", "name", "units", "firmware", "pen_up", "pen_down", "settle",
          "paper_width_mm", "paper_height_mm", "margin_mm", "machine_width_mm",
          "machine_height_mm", "feed_mm_min", "jog_step_mm", "jog_feed_mm_min"}
NEW_DEFAULTS = {"x_steps_per_mm": 5.0, "y_steps_per_mm": 5.0, "ollama_model": ""}
V2_FIELDS = LEGACY_FIELDS | NEW_DEFAULTS.keys()
FIELDS = V2_FIELDS | {'paper_mount'}


def preset_path() -> Path:
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return base / "SCRIB3" / "machine-preset.json"


def validate(data: dict) -> dict:
    if isinstance(data, dict) and type(data.get("schema_version")) is int and data["schema_version"] == 1 and set(data) == LEGACY_FIELDS:
        data = data | NEW_DEFAULTS | {"schema_version": 2}
    if isinstance(data, dict) and type(data.get('schema_version')) is int and data['schema_version'] == 2 and set(data) == V2_FIELDS:
        # Keep existing coordinate behavior until the operator selects a mounting.
        data = data | {'schema_version': 3, 'paper_mount': 'bottom_left_x'}
    if not isinstance(data, dict) or set(data) != FIELDS or type(data.get("schema_version")) is not int or data["schema_version"] != 3:
        raise ValueError("Unsupported or incomplete machine preset.")
    result = dict(data)
    if not isinstance(result["name"], str) or not result["name"].strip() or len(result["name"]) > 80:
        raise ValueError("Enter a preset name of 1 to 80 characters.")
    result["name"] = result["name"].strip()
    factor(result["units"])
    validate_mount(result['paper_mount'])
    if result["firmware"] not in {"Manual commands", SERVO_PROFILE}:
        raise ValueError("Unknown preset firmware profile.")
    if not isinstance(result["ollama_model"], str) or len(result["ollama_model"]) > 200:
        raise ValueError("Invalid saved Ollama model name.")
    for key in FIELDS - {"schema_version", "name", "units", "firmware", "pen_up", "pen_down", "ollama_model", "paper_mount"}:
        if result[key] is None and key in {"machine_width_mm", "machine_height_mm", "feed_mm_min"}:
            continue
        if type(result[key]) not in {int, float}:
            raise ValueError(f"Invalid preset value: {key}.")
        result[key] = number(result[key])
    Sheet(result["paper_width_mm"], result["paper_height_mm"], result["margin_mm"])
    if not isinstance(result["pen_up"], str) or not isinstance(result["pen_down"], str):
        raise ValueError("Preset pen commands must be text.")
    Machine(result["machine_width_mm"] if result["machine_width_mm"] is not None else 1,
            result["machine_height_mm"] if result["machine_height_mm"] is not None else 1,
            result["feed_mm_min"] if result["feed_mm_min"] is not None else 1,
            result["pen_up"], result["pen_down"], result["settle"])
    if not .001 <= result["jog_step_mm"] <= 100 or not .001 <= result["jog_feed_mm_min"] <= 100000:
        raise ValueError("Preset jog distance or feed is outside the supported range.")
    if not all(.001 <= result[key] <= 100000 for key in ("x_steps_per_mm", "y_steps_per_mm")):
        raise ValueError("Preset steps/mm must be between 0.001 and 100000.")
    return result


def read(path: Path) -> dict:
    if path.stat().st_size > 32768:
        raise ValueError("Machine preset is too large.")
    try:
        return validate(json.loads(path.read_text(encoding="utf-8")))
    except (UnicodeError, json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Cannot read the saved machine preset.") from exc


def builtin() -> dict:
    return read(BUILTIN)


def load(path: Path) -> dict:
    return read(path) if path.exists() else builtin()


def save(path: Path, data: dict) -> None:
    data = validate(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".preset-", suffix=".json", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
