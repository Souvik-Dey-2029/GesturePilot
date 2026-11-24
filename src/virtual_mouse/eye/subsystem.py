"""Rebuilt Eye and Face Interaction Subsystem.

Combines:
- EyeFeatureExtractor: Standard 6-pt geometric EAR + blendshape category parsing
- EyeStateEstimator: Schmitt-trigger hysteresis state machine
- BlinkDetector: Duration-filtered natural single blink detection
- BlinkSequenceRecognizer: Rapid deliberate double/triple sequence recognition with natural blink rejection
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..events import EventType, ModalityType, MultimodalEvent
from .blink_detector import BlinkDetector, BlinkSequenceRecognizer, CompletedBlink
from .calibration import EyeCalibration
from .feature_extractor import EyeFeatureExtractor, EyeFeatureObservation
from .state_estimator import EyeState, EyeStateEstimator


@dataclass(frozen=True, slots=True)
class FaceObservation:
    """Normalized facial landmarks (478 pts) and blendshapes."""
    landmarks: Tuple[Tuple[float, float, float], ...] = ()
    blendshapes: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.95


@dataclass
class EyeTelemetry:
    face_detected: bool = False
    confidence: float = 0.0
    left_blink: float = 0.0
    right_blink: float = 0.0
    ear: float = 0.28
    current_state: str = "EYES_OPEN"
    sequence_count: int = 0
    last_action: str = "NONE"
    rejection_reason: str = ""
    latency_ms: float = 0.0
    # Detailed diagnostic telemetry
    ear_closed_threshold: float = 0.18
    ear_open_threshold: float = 0.22
    blend_closed_threshold: float = 0.55
    blend_open_threshold: float = 0.35
    in_blink: bool = False
    cooldown_remaining: float = 0.0
    # Legacy fields for backward compatibility with HUD overlay
    left_ear: float = 0.28
    right_ear: float = 0.28
    symmetry_blink: float = 0.0

    @property
    def ear_threshold(self) -> float:
        return self.ear_closed_threshold

    @property
    def blend_threshold(self) -> float:
        return self.blend_closed_threshold


class EyeSubsystem:
    """Detects intentional blink sequences and gates mouse scroll actions."""

    def __init__(self, calibration: EyeCalibration | None = None) -> None:
        self.calib = calibration or EyeCalibration()
        self.enabled = False

        self.extractor = EyeFeatureExtractor()
        self.estimator = EyeStateEstimator(
            ear_open_baseline=self.calib.natural_ear_baseline,
            ear_closed_threshold=self.calib.ear_closed_threshold,
            ear_open_threshold=self.calib.ear_open_threshold,
            blend_closed_threshold=self.calib.blend_closed_threshold,
            blend_open_threshold=self.calib.blend_open_threshold,
        )
        self.detector = BlinkDetector(
            min_duration_s=self.calib.min_blink_duration_s,
            max_duration_s=self.calib.max_blink_duration_s,
        )
        self.recognizer = BlinkSequenceRecognizer(
            max_inter_blink_pause_s=self.calib.max_inter_blink_pause_s,
            wait_for_triple_timeout_s=self.calib.wait_for_triple_timeout_s,
            cooldown_s=self.calib.cooldown_s,
            scroll_amount_ticks=self.calib.scroll_amount_ticks,
        )

        # Live telemetry
        self.telemetry = EyeTelemetry()

    def enable(self) -> None:
        self.enabled = True
        self.reset()

    def disable(self) -> None:
        self.enabled = False
        self.reset()

    def reset(self) -> None:
        self.estimator.reset()
        self.detector.reset()
        self.recognizer.reset()
        self.telemetry = EyeTelemetry()

    def apply_calibration(self, calib: EyeCalibration) -> None:
        self.calib = calib
        self.estimator = EyeStateEstimator(
            ear_open_baseline=calib.natural_ear_baseline,
            ear_closed_threshold=calib.ear_closed_threshold,
            ear_open_threshold=calib.ear_open_threshold,
            blend_closed_threshold=calib.blend_closed_threshold,
            blend_open_threshold=calib.blend_open_threshold,
        )
        self.detector = BlinkDetector(
            min_duration_s=calib.min_blink_duration_s,
            max_duration_s=calib.max_blink_duration_s,
        )
        self.recognizer = BlinkSequenceRecognizer(
            max_inter_blink_pause_s=calib.max_inter_blink_pause_s,
            wait_for_triple_timeout_s=calib.wait_for_triple_timeout_s,
            cooldown_s=calib.cooldown_s,
            scroll_amount_ticks=calib.scroll_amount_ticks,
        )

    def compute_blink_metrics(self, face: FaceObservation) -> Tuple[float, float, float]:
        """Backward compatibility helper returning (left_blink, right_blink, ear_avg)."""
        obs = self.extractor.extract(face.landmarks, face.blendshapes, face.confidence)
        return obs.blink_left, obs.blink_right, obs.ear_avg

    def process(self, face: Optional[FaceObservation], now: float | None = None) -> List[MultimodalEvent]:
        """Evaluates face observation and returns confirmed multimodal events."""
        t0 = time.perf_counter()
        t = now if now is not None else time.monotonic()
        events: List[MultimodalEvent] = []

        if not self.enabled:
            self.reset()
            self.telemetry = EyeTelemetry(
                face_detected=False,
                confidence=0.0,
                current_state="DISABLED",
                rejection_reason="Subsystem disabled",
            )
            return events

        if face is None:
            # Tracking lost
            obs = self.extractor.extract(None, None, 0.0, t)
            st = self.estimator.estimate(obs)
            self.detector.reset()
            self.recognizer.cancel("Face tracking lost")
            self.telemetry = EyeTelemetry(
                face_detected=False,
                confidence=0.0,
                current_state="NO_FACE",
                rejection_reason="Face not detected",
            )
            return events

        # 1. Feature Extraction
        obs = self.extractor.extract(face.landmarks, face.blendshapes, face.confidence, t)

        # 2. State Estimation with Hysteresis
        state = self.estimator.estimate(obs)

        # 3. Single Blink Detection
        completed_blink = self.detector.update(state, obs)

        # 4. Sequence Recognition
        events = self.recognizer.process(completed_blink, t, state)

        # 5. Populate Telemetry
        latency = (time.perf_counter() - t0) * 1000.0
        rej = self.recognizer.last_rejection or self.detector.last_rejection_reason

        self.telemetry = EyeTelemetry(
            face_detected=obs.face_detected,
            confidence=obs.tracking_confidence,
            left_blink=obs.blink_left,
            right_blink=obs.blink_right,
            ear=obs.ear_avg,
            left_ear=obs.ear_left,
            right_ear=obs.ear_right,
            symmetry_blink=obs.symmetry_blink,
            current_state=state.value,
            sequence_count=self.recognizer.sequence_count,
            last_action=self.recognizer.last_action,
            rejection_reason=rej,
            latency_ms=latency,
            ear_closed_threshold=self.calib.ear_closed_threshold,
            ear_open_threshold=self.calib.ear_open_threshold,
            blend_closed_threshold=self.calib.blend_closed_threshold,
            blend_open_threshold=self.calib.blend_open_threshold,
            in_blink=self.detector.in_blink,
            cooldown_remaining=max(0.0, self.recognizer.cooldown_until - t),
        )

        return events
