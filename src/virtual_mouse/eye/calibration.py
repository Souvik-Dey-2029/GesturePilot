"""Calibrated Eye Parameter Profile and Calibration Manager.

Computes personalized open-eye baseline, closed-eye EAR, optimal Schmitt-trigger thresholds,
and stores verified parameters in user profile SQLite storage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from .feature_extractor import EyeFeatureObservation

log = logging.getLogger(__name__)


@dataclass
class EyeCalibration:
    natural_ear_baseline: float = 0.28
    ear_closed_threshold: float = 0.18
    ear_open_threshold: float = 0.22
    blend_closed_threshold: float = 0.55
    blend_open_threshold: float = 0.35
    min_blink_duration_s: float = 0.05
    max_blink_duration_s: float = 0.45
    max_inter_blink_pause_s: float = 0.45
    wait_for_triple_timeout_s: float = 0.35
    cooldown_s: float = 0.60
    scroll_amount_ticks: int = 3
    is_calibrated: bool = False

    @property
    def blink_ear_threshold(self) -> float:
        """Alias for backward compatibility."""
        return self.ear_closed_threshold

    @blink_ear_threshold.setter
    def blink_ear_threshold(self, value: float) -> None:
        self.ear_closed_threshold = value


class EyeCalibrator:
    """Collects stable open-eye and closed-eye observation samples and calculates thresholds."""

    def __init__(self, target_samples: int = 60) -> None:
        self.target_samples = target_samples
        self._open_samples: List[EyeFeatureObservation] = []
        self._closed_samples: List[EyeFeatureObservation] = []

    def reset(self) -> None:
        self._open_samples.clear()
        self._closed_samples.clear()

    def add_open_sample(self, obs: EyeFeatureObservation) -> bool:
        if obs.face_detected and obs.landmarks_valid and obs.symmetry_blink < 0.25:
            self._open_samples.append(obs)
            return True
        return False

    def add_closed_sample(self, obs: EyeFeatureObservation) -> bool:
        if obs.face_detected and obs.landmarks_valid:
            self._closed_samples.append(obs)
            return True
        return False

    @property
    def open_samples_count(self) -> int:
        return len(self._open_samples)

    @property
    def closed_samples_count(self) -> int:
        return len(self._closed_samples)

    def finalize(self) -> Optional[EyeCalibration]:
        if len(self._open_samples) < 15 or len(self._closed_samples) < 10:
            log.warning("Insufficient samples for calibration (open=%d, closed=%d)", len(self._open_samples), len(self._closed_samples))
            return None

        # Calculate mean open EAR
        open_ears = [s.ear_avg for s in self._open_samples]
        mean_open_ear = sum(open_ears) / len(open_ears)

        # Calculate mean closed EAR and mean closed blendshape
        closed_ears = [s.ear_avg for s in self._closed_samples]
        mean_closed_ear = sum(closed_ears) / len(closed_ears)

        closed_blends = [s.blink_avg for s in self._closed_samples]
        mean_closed_blend = sum(closed_blends) / len(closed_blends)

        # Check valid physiological separation
        if mean_closed_ear >= mean_open_ear:
            log.warning("Calibration rejected: closed EAR (%.3f) >= open EAR (%.3f)", mean_closed_ear, mean_open_ear)
            return None

        # Derive Schmitt-trigger EAR thresholds:
        # closed_threshold = closed + 0.35 * range
        # open_threshold = closed + 0.65 * range
        ear_range = mean_open_ear - mean_closed_ear
        ear_closed_th = round(mean_closed_ear + 0.35 * ear_range, 3)
        ear_open_th = round(mean_closed_ear + 0.65 * ear_range, 3)

        # Derive blendshape thresholds
        blend_closed_th = round(max(0.45, min(0.70, mean_closed_blend * 0.75)), 2)
        blend_open_th = round(max(0.20, blend_closed_th - 0.20), 2)

        calib = EyeCalibration(
            natural_ear_baseline=round(mean_open_ear, 3),
            ear_closed_threshold=ear_closed_th,
            ear_open_threshold=ear_open_th,
            blend_closed_threshold=blend_closed_th,
            blend_open_threshold=blend_open_th,
            is_calibrated=True,
        )
        log.info("Calibration successful: %s", calib)
        return calib
