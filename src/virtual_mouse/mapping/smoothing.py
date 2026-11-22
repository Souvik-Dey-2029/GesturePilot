"""One Euro filter (Casiez et al., 2012) and adaptive point filtering for jitter reduction."""
from __future__ import annotations

import math
from ..config import SmoothingConfig


def _alpha(cutoff: float, dt: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuroFilter:
    def __init__(self, min_cutoff: float, beta: float, d_cutoff: float) -> None:
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self) -> None:
        self._t: float | None = None
        self._x_raw = 0.0
        self._x_hat = 0.0
        self._dx_hat = 0.0

    def __call__(self, x: float, t: float) -> float:
        if math.isnan(x) or math.isinf(x):
            return self._x_hat
        if self._t is None:
            self._t, self._x_raw, self._x_hat, self._dx_hat = t, x, x, 0.0
            return x
        dt = t - self._t
        if dt <= 0.0:  # non-monotonic or duplicate timestamp: hold last output
            return self._x_hat
        # Cap dt to avoid large instability gaps if there was a brief pause
        if dt > 1.0:
            self._t, self._x_raw, self._x_hat, self._dx_hat = t, x, x, 0.0
            return x

        dx = (x - self._x_raw) / dt
        a_d = _alpha(self.d_cutoff, dt)
        self._dx_hat = a_d * dx + (1.0 - a_d) * self._dx_hat
        cutoff = self.min_cutoff + self.beta * abs(self._dx_hat)
        a = _alpha(cutoff, dt)
        self._x_hat = a * x + (1.0 - a) * self._x_hat
        self._x_raw, self._t = x, t
        return self._x_hat


class PointFilter:
    """2-D One Euro filter with configurable deadzone and non-linear power curve."""

    def __init__(self, config: SmoothingConfig) -> None:
        self._config = config
        self._enabled = config.enabled
        self._fx = OneEuroFilter(config.min_cutoff, config.beta, config.d_cutoff)
        self._fy = OneEuroFilter(config.min_cutoff, config.beta, config.d_cutoff)
        self._last_out_x: float | None = None
        self._last_out_y: float | None = None

    def reset(self) -> None:
        """Call when the hand is lost so the cursor does not glide from a stale position."""
        self._fx.reset()
        self._fy.reset()
        self._last_out_x = None
        self._last_out_y = None

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        if not self._enabled:
            return x, y

        # 1. Apply One Euro Filter to continuous input
        fx = self._fx(x, t)
        fy = self._fy(y, t)

        # 2. Movement deadzone & continuous thresholding
        if self._last_out_x is None or self._last_out_y is None:
            self._last_out_x, self._last_out_y = fx, fy
            return fx, fy

        dx = fx - self._last_out_x
        dy = fy - self._last_out_y
        dist = math.hypot(dx, dy)

        deadzone = self._config.deadzone_radius_px
        if deadzone > 0.0:
            if dist < deadzone:
                # Inside deadzone: completely suppress micro-tremor
                return self._last_out_x, self._last_out_y
            else:
                # Outside deadzone: smooth transition so cursor doesn't jump
                # Scale factor starts at 0 at deadzone edge and approaches 1 smoothly
                scale = (dist - deadzone) / dist
                fx = self._last_out_x + dx * scale
                fy = self._last_out_y + dy * scale

        self._last_out_x, self._last_out_y = fx, fy
        return fx, fy

