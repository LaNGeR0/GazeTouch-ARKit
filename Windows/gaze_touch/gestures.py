from __future__ import annotations


class PinchGate:
    def __init__(self) -> None:
        self.armed = False
        self.closed = False
        self.last_click = float("-inf")

    def reset(self) -> None:
        self.armed = False
        self.closed = False

    def update(self, ratio: float | None, threshold: float, cooldown: float,
               now: float, enabled: bool) -> bool:
        if ratio is None:
            self.reset()
            return False
        enter = max(0.08, float(threshold))
        release = enter + 0.12
        if not self.armed:
            if ratio >= release:
                self.armed = True
            return False
        if not self.closed and ratio <= enter:
            self.closed = True
            if enabled and now - self.last_click >= cooldown:
                self.last_click = now
                return True
        elif self.closed and ratio >= release:
            self.closed = False
        return False
