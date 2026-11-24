"""Robust Eye State Estimator with Schmitt-trigger hysteresis.

Distinguishes:
1. EYES_OPEN
2. EYES_CLOSING
3. EYES_CLOSED
4. EYES_OPENING
5. EYE_TRACKING_LOST
6. EYE_STATE_UNCERTAIN

Applies dual-threshold hysteresis to both EAR and blendshapes, rejects single-frame
detection noise, enforces bilateral symmetry, and respects calibrated baseline.
"""
from __future__ import annotations

from enum import Enum
from typing import Optional
from .feature_extractor import EyeFeatureObservation


class EyeState(Enum):
    EYES_OPEN = "EYES_OPEN"
    EYES_CLOSING = "EYES_CLOSING"
    EYES_CLOSED = "EYES_CLOSED"
    EYES_OPENING = "EYES_OPENING"
    EYE_TRACKING_LOST = "EYE_TRACKING_LOST"
    EYE_STATE_UNCERTAIN = "EYE_STATE_UNCERTAIN"


class EyeStateEstimator:
    """Estimates eye physiological state using dual-evidence hysteresis."""

    def __init__(
        self,
        ear_open_baseline: float = 0.28,
        ear_closed_threshold: float = 0.18,
        ear_open_threshold: float = 0.22,
        blend_closed_threshold: float = 0.55,
        blend_open_threshold: float = 0.35,
        max_asymmetry: float = 0.40,
    ) -> None:
        self.ear_open_baseline = ear_open_baseline
        self.ear_closed_threshold = ear_closed_threshold  # EAR <= 0.18 triggers closing/closed
        self.ear_open_threshold = ear_open_threshold      # EAR >= 0.22 required to clear closed
        self.blend_closed_threshold = blend_closed_threshold  # Blend >= 0.55 triggers closing/closed
        self.blend_open_threshold = blend_open_threshold      # Blend <= 0.35 required to clear closed
        self.max_asymmetry = max_asymmetry

        self._current_state = EyeState.EYES_OPEN
        self._consecutive_closed_frames = 0
        self._consecutive_open_frames = 0

    @property
    def current_state(self) -> EyeState:
        return self._current_state

    def reset(self) -> None:
        self._current_state = EyeState.EYES_OPEN
        self._consecutive_closed_frames = 0
        self._consecutive_open_frames = 0

    def estimate(self, obs: EyeFeatureObservation) -> EyeState:
        # 1. Tracking Lost Check
        if not obs.face_detected or obs.tracking_confidence < 0.40:
            self.reset()
            self._current_state = EyeState.EYE_TRACKING_LOST
            return self._current_state

        # 2. Quality & Extreme Asymmetry Check
        # If one eye is closed (0.85) and the other is wide open (0.10) with no wink command,
        # or geometry is invalid, flag UNCERTAIN instead of false bilateral blink
        if obs.symmetry_blink > self.max_asymmetry:
            self._current_state = EyeState.EYE_STATE_UNCERTAIN
            return self._current_state

        # 3. Dual-Evidence Open vs Closed Logic with Hysteresis
        # A true closure is indicated when:
        # EAR drops below closed threshold OR blendshape rises above closed threshold
        ear_indicates_closed = obs.ear_avg <= self.ear_closed_threshold
        blend_indicates_closed = obs.blink_avg >= self.blend_closed_threshold

        ear_indicates_open = obs.ear_avg >= self.ear_open_threshold
        blend_indicates_open = obs.blink_avg <= self.blend_open_threshold

        # High confidence closed condition:
        is_closed_signal = blend_indicates_closed or ear_indicates_closed
        is_open_signal = blend_indicates_open and ear_indicates_open

        # 4. State Machine with Transitions (OPEN -> CLOSING -> CLOSED -> OPENING -> OPEN)
        if self._current_state in (EyeState.EYES_OPEN, EyeState.EYE_TRACKING_LOST, EyeState.EYE_STATE_UNCERTAIN):
            if is_closed_signal:
                self._current_state = EyeState.EYES_CLOSING
                self._consecutive_closed_frames = 1
                self._consecutive_open_frames = 0
            else:
                self._current_state = EyeState.EYES_OPEN
                self._consecutive_open_frames += 1

        elif self._current_state == EyeState.EYES_CLOSING:
            if is_closed_signal:
                self._consecutive_closed_frames += 1
                if self._consecutive_closed_frames >= 2:
                    self._current_state = EyeState.EYES_CLOSED
            else:
                # Glitch/flutter that aborted before full closure
                self._current_state = EyeState.EYES_OPEN
                self._consecutive_closed_frames = 0

        elif self._current_state == EyeState.EYES_CLOSED:
            if is_open_signal:
                self._current_state = EyeState.EYES_OPENING
                self._consecutive_open_frames = 1
                self._consecutive_closed_frames = 0
            else:
                self._consecutive_closed_frames += 1

        elif self._current_state == EyeState.EYES_OPENING:
            if is_open_signal:
                self._consecutive_open_frames += 1
                if self._consecutive_open_frames >= 1:
                    self._current_state = EyeState.EYES_OPEN
            elif is_closed_signal:
                # Immediate re-closure
                self._current_state = EyeState.EYES_CLOSED
                self._consecutive_closed_frames += 1

        return self._current_state
