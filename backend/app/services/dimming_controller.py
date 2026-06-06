"""Dimming profile resolver.

Given a time-of-day and an optional ambient lux reading, returns the dimming
level (0-100) that should be applied to a cabinet. Profiles are intentionally
simple: a list of (start_hour, end_hour, level) tuples evaluated in order.
"""
from datetime import time


DEFAULT_PROFILE: list[tuple[time, time, int]] = [
    (time(0, 0), time(6, 0), 30),
    (time(6, 0), time(7, 30), 70),
    (time(7, 30), time(18, 0), 0),
    (time(18, 0), time(22, 0), 100),
    (time(22, 0), time(23, 59, 59), 50),
]

LUX_THRESHOLD_ON = 30.0
LUX_THRESHOLD_OFF = 80.0


def resolve_level(now: time, ambient_lux: float | None = None) -> int:
    if ambient_lux is not None and ambient_lux > LUX_THRESHOLD_OFF:
        return 0

    for start, end, level in DEFAULT_PROFILE:
        if start <= now <= end:
            if ambient_lux is not None and ambient_lux < LUX_THRESHOLD_ON:
                return max(level, 50)
            return level
    return 0
