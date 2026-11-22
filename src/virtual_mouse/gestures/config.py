"""Typed configuration for gesture recognition and mouse interactions (v005)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ConfigError(ValueError):
    """Raised for invalid or unknown configuration values."""


def _num(name: str, value: Any, lo: float, hi: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number, got {value!r}")
    if not (lo <= value <= hi):
        raise ConfigError(f"{name} must be within [{lo}, {hi}], got {value}")


@dataclass
class GestureConfig:
    """Configurable thresholds, timings, and sensitivities for v005 gestures."""

    # Double click pinch (Thumb + Index)
    pinch_threshold: float = 0.35  # normalized distance to activate pinch
    pinch_release_threshold: float = 0.52  # normalized distance to release pinch (hysteresis)
    pinch_confirm_frames: int = 2  # consecutive frames to confirm deliberate pinch
    pinch_cooldown_s: float = 0.35  # cooldown after double click before another can trigger

    # Two-finger gesture (Left Click / Scroll)
    two_finger_click_window_s: float = 0.22  # time window to hold stationary for left click
    two_finger_motion_threshold: float = 0.025  # normalized displacement to enter scrolling instead of click
    left_click_cooldown_s: float = 0.30  # cooldown after left click before another click can occur

    # Three-finger gesture (Right Click / Scroll)
    three_finger_click_window_s: float = 0.22  # time window to hold stationary for right click
    three_finger_motion_threshold: float = 0.025  # normalized displacement to enter scrolling instead of click
    right_click_cooldown_s: float = 0.35  # cooldown after right click before another click can occur

    # Dynamic Scrolling Engine
    scroll_speed: float = 80.0  # multiplier from normalized dy movement to scroll ticks
    scroll_smoothing_alpha: float = 0.4  # exponential moving average smoothing for scroll dy
    scroll_deadzone_dy: float = 0.003  # movement below this delta is filtered
    scroll_exit_duration_s: float = 0.10  # stability duration returning to pointer or open palm to exit scrolling

    # Finger Extension Thresholds
    finger_extended_ratio: float = 1.10
    finger_curled_ratio: float = 1.05

    def validate(self) -> None:
        _num("gestures.pinch_threshold", self.pinch_threshold, 0.05, 1.5)
        _num("gestures.pinch_release_threshold", self.pinch_release_threshold, 0.05, 2.0)
        if self.pinch_release_threshold <= self.pinch_threshold:
            raise ConfigError("gestures.pinch_release_threshold must be strictly greater than pinch_threshold for hysteresis")

        _num("gestures.pinch_confirm_frames", self.pinch_confirm_frames, 1, 10)
        _num("gestures.pinch_cooldown_s", self.pinch_cooldown_s, 0.05, 2.0)

        _num("gestures.two_finger_click_window_s", self.two_finger_click_window_s, 0.05, 1.5)
        _num("gestures.two_finger_motion_threshold", self.two_finger_motion_threshold, 0.005, 0.2)
        _num("gestures.left_click_cooldown_s", self.left_click_cooldown_s, 0.05, 2.0)

        _num("gestures.three_finger_click_window_s", self.three_finger_click_window_s, 0.05, 1.5)
        _num("gestures.three_finger_motion_threshold", self.three_finger_motion_threshold, 0.005, 0.2)
        _num("gestures.right_click_cooldown_s", self.right_click_cooldown_s, 0.05, 2.0)

        _num("gestures.scroll_speed", self.scroll_speed, 1.0, 2000.0)
        _num("gestures.scroll_smoothing_alpha", self.scroll_smoothing_alpha, 0.01, 1.0)
        _num("gestures.scroll_deadzone_dy", self.scroll_deadzone_dy, 0.0, 0.1)
        _num("gestures.scroll_exit_duration_s", self.scroll_exit_duration_s, 0.0, 2.0)

        _num("gestures.finger_extended_ratio", self.finger_extended_ratio, 1.0, 2.0)
        _num("gestures.finger_curled_ratio", self.finger_curled_ratio, 0.5, 1.5)
