"""Compatibility checks for the RC-servo firmware supplied with SCRIB3."""

from __future__ import annotations

from ctypes import c_float
from dataclasses import dataclass
from math import floor, isfinite
import re

SERVO_PROFILE = "Uploaded RC-servo"
SERVO_SHORT = 7
SERVO_LONG = 31
SERVO_RANGE = 100
PEN_UP_BUILD = "[VER:1.1h.20190830.SCRIB3-UP13:"
PEN_UP_COUNT = 13


@dataclass(frozen=True)
class ServoSettings:
    rpm_max: float
    rpm_min: float
    laser_mode: float
    spindle_override: int
    stop_count: int = SERVO_LONG

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in (self.rpm_max, self.rpm_min)):
            raise ValueError("The controller returned invalid $30/$31 values.")
        difference = c_float(c_float(self.rpm_max).value - c_float(self.rpm_min).value).value
        if self.rpm_min < 0 or not isfinite(difference) or difference <= 0:
            raise ValueError("The uploaded servo firmware requires $30 greater than $31, with $31 nonnegative.")
        if self.laser_mode != 0:
            raise ValueError("The uploaded servo firmware requires laser mode $32=0.")
        if self.spindle_override != 100:
            raise ValueError("Set the spindle override to 100% and read GRBL again for the uploaded servo profile.")

    @classmethod
    def from_controller(cls, settings, override, report):
        if not {30, 31, 32}.issubset(settings) or override is None:
            raise ValueError("Read GRBL to capture servo settings and the spindle override first.")
        stop = PEN_UP_COUNT if any(line.startswith(PEN_UP_BUILD) for line in report.splitlines()) else SERVO_LONG
        return cls(settings[30], settings[31], settings[32], override, stop)

    @classmethod
    def from_report(cls, report: str) -> ServoSettings:
        lines = report.splitlines()
        settings: dict[int, float] = {}
        reading = False
        complete = False
        override = None
        for line in lines:
            if line.startswith("<") and line.endswith(">"):
                if match := re.search(r"\|Ov:\d+,\d+,(\d+)(?:\||>)", line):
                    override = int(match.group(1))
            if line == "$$":
                settings.clear()
                reading = True
                complete = False
            elif reading:
                if line == "ok":
                    complete = True
                    reading = False
                elif match := re.fullmatch(r"\$(\d+)=([+-]?(?:\d+(?:\.\d*)?|\.\d+))", line):
                    settings[int(match.group(1))] = float(match.group(2))
                elif line.startswith("<") and line.endswith(">"):
                    continue
                else:
                    raise ValueError("The GRBL settings response was interrupted. Read GRBL again.")
        if not complete or not {30, 31, 32}.issubset(settings):
            raise ValueError("Read GRBL to capture a complete $30/$31/$32 settings response.")
        if override is None:
            raise ValueError("Read GRBL again to capture the spindle override in an Ov status field.")
        return cls.from_controller(settings, override, report)

    def timer_count(self, s_value: float | None) -> int:
        if s_value is None:  # M5 and reset both call spindle_stop().
            return self.stop_count
        if not isfinite(s_value) or s_value < 0:
            raise ValueError("Enter a finite, nonnegative servo S value.")
        # Match the supplied AVR float expression before its conversion to uint8_t.
        difference = c_float(c_float(self.rpm_max).value - c_float(self.rpm_min).value).value
        slope = c_float(SERVO_RANGE / difference).value
        movement = c_float(c_float(s_value).value * slope).value
        timer = c_float(SERVO_LONG - movement).value
        if not isfinite(timer) or not SERVO_SHORT <= timer <= SERVO_LONG:
            raise ValueError(
                f"Servo S{s_value:g} is outside the uploaded firmware's pulse range "
                f"with $30={self.rpm_max:g} and $31={self.rpm_min:g}."
            )
        return floor(timer)

    def check_lift(self, count):
        if self.stop_count == PEN_UP_COUNT and count > PEN_UP_COUNT:
            raise ValueError("This command lowers John's tagged servo below its calibrated raised position. Check Pen up on Machine.")

    def describe(self) -> str:
        limit = (SERVO_LONG - SERVO_SHORT) * (self.rpm_max - self.rpm_min) / SERVO_RANGE
        return (
            "Uploaded GRBL 1.1h RC-servo profile\n"
            f"$30={self.rpm_max:g}   $31={self.rpm_min:g}   $32=0   spindle override 100%\n"
            f"M5 and reset select timer count {self.stop_count}.\n"
            f"M3 S values have a nominal range of 0 to {limit:g} for this settings snapshot.\n"
            "Each export also checks the rounded S value and distinct servo pulse counts.\n"
            "Choose pen-up and pen-down positions from observed lift motion.\n"
            "The profile is based on the supplied source files. Confirm those files were flashed."
        )
