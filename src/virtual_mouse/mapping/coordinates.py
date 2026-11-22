"""Camera-normalized coordinates -> screen pixels via a configurable active region."""
from __future__ import annotations

from ..config import MappingConfig
from ..types import ScreenPoint


class CoordinateMapper:
    def __init__(self, config: MappingConfig, screen_width: int, screen_height: int) -> None:
        if screen_width < 2 or screen_height < 2:
            raise ValueError("screen dimensions must be at least 2x2")
        self._cfg = config
        self._w = screen_width
        self._h = screen_height

    @property
    def screen_size(self) -> tuple[int, int]:
        return self._w, self._h

    def map(self, nx: float, ny: float) -> ScreenPoint:
        """Map a normalized camera point (unmirrored image, 0..1) to a clamped screen pixel position."""
        c = self._cfg
        u = (nx - c.margin_left) / (1.0 - c.margin_left - c.margin_right)
        v = (ny - c.margin_top) / (1.0 - c.margin_top - c.margin_bottom)
        if c.mirror_x:
            u = 1.0 - u

        # Apply sensitivity centered around active region center
        du = u - 0.5
        dv = v - 0.5

        if c.acceleration != 1.0:
            # Subtle power curve for gentle acceleration: sign(d) * (|d| * 2)^acc / 2
            sign_u = 1.0 if du >= 0 else -1.0
            sign_v = 1.0 if dv >= 0 else -1.0
            du = sign_u * (abs(du * 2.0) ** c.acceleration) / 2.0
            dv = sign_v * (abs(dv * 2.0) ** c.acceleration) / 2.0

        u = 0.5 + du * c.sensitivity
        v = 0.5 + dv * c.sensitivity
        u = min(1.0, max(0.0, u))
        v = min(1.0, max(0.0, v))
        return ScreenPoint(x=u * (self._w - 1), y=v * (self._h - 1))
