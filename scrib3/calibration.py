"""Measured travel correction in a consistent unit system."""
from math import isfinite


def corrected_steps(current: float, commanded: float, measured: float) -> float:
    if not all(isfinite(value) and value > 0 for value in (current, commanded, measured)):
        raise ValueError("Steps and both distances must be finite, positive numbers.")
    result = round(current * commanded / measured, 3)
    if not .001 <= result <= 100000:
        raise ValueError("Calculated steps/mm is outside the controller's supported range.")
    return result
