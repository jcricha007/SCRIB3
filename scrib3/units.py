"""Display/export units; geometry and controller APIs use millimeters internally."""
from math import isfinite

MM_PER_INCH = 25.4
UNIT_NAMES = {"in": "Inches", "mm": "Millimeters"}
LENGTH_SETTINGS = {24, 25, 27, 110, 111, 120, 121, 130, 131}
STEPS_SETTINGS = {100, 101}


def factor(unit: str) -> float:
    if unit not in UNIT_NAMES:
        raise ValueError("Select inches or millimeters.")
    return MM_PER_INCH if unit == "in" else 1.0


def number(value) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Enter a finite numeric value.") from exc
    if not isfinite(result):
        raise ValueError("Enter a finite numeric value.")
    return result


def to_mm(value, unit: str) -> float:
    return number(value) * factor(unit)


def from_mm(value, unit: str) -> float:
    return number(value) / factor(unit)


def display(value, unit: str) -> str:
    return f"{from_mm(value, unit):.10g}"


def setting_display(number_: int, value: float, unit: str) -> float:
    if number_ in STEPS_SETTINGS:
        return value * factor(unit)
    return from_mm(value, unit) if number_ in LENGTH_SETTINGS else value


def setting_native(number_: int, value, unit: str) -> float:
    value = number(value)
    if number_ in STEPS_SETTINGS:
        return value / factor(unit)
    return to_mm(value, unit) if number_ in LENGTH_SETTINGS else value


def setting_label(label: str, unit: str) -> str:
    factor(unit)
    return label.replace("mm", unit)
