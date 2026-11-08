from __future__ import annotations

import math
from collections import deque
from statistics import median


class StableFilter:
    """3-frame median + One-Euro low-pass in screen-pixel space."""

    def __init__(self) -> None:
        self.recent: deque[float] = deque(maxlen=3)
        self.prev_time: float | None = None
        self.prev_raw: float | None = None
        self.value: float | None = None
        self.derivative = 0.0
        self.min_cutoff = 0.65
        self.beta = 0.00012
        self.deadzone = 1.5

    @staticmethod
    def alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2.0 * math.pi * max(cutoff, 0.001))
        return 1.0 / (1.0 + tau / max(dt, 0.001))

    def set_smoothing(self, percent: int) -> None:
        p = max(0, min(100, int(percent))) / 100.0
        self.min_cutoff = 1.8 - 1.35 * p

    def reset(self) -> None:
        self.recent.clear()
        self.prev_time = None
        self.prev_raw = None
        self.value = None
        self.derivative = 0.0

    def filter(self, raw: float, t: float) -> float:
        self.recent.append(float(raw))
        sample = float(median(self.recent))
        if self.value is None or self.prev_time is None or self.prev_raw is None:
            self.value = sample
            self.prev_raw = sample
            self.prev_time = t
            return sample
        dt = max(0.001, min(0.2, t - self.prev_time))
        deriv = (sample - self.prev_raw) / dt
        da = self.alpha(1.0, dt)
        self.derivative += da * (deriv - self.derivative)
        cutoff = self.min_cutoff + self.beta * abs(self.derivative)
        a = self.alpha(cutoff, dt)
        candidate = self.value + a * (sample - self.value)
        if abs(candidate - self.value) > self.deadzone:
            self.value = candidate
        self.prev_raw = sample
        self.prev_time = t
        return self.value
