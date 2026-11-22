"""MediaPipe Tasks HandLandmarker wrapper (VIDEO running mode, synchronous)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ..config import DetectorConfig
from ..types import NUM_LANDMARKS, CapturedFrame, FrameResult, HandObservation, Landmark
from .model_assets import ModelError

log = logging.getLogger(__name__)


def convert_result(result: Any, timestamp_ms: int, frame_index: int) -> FrameResult:
    """Convert a MediaPipe HandLandmarkerResult (or any duck-typed equivalent) to our types."""
    landmark_sets = getattr(result, "hand_landmarks", None) or []
    handedness_sets = getattr(result, "handedness", None) or []
    hands: list[HandObservation] = []
    for i, lms in enumerate(landmark_sets):
        if len(lms) != NUM_LANDMARKS:
            log.warning("ignoring hand with %d landmarks", len(lms))
            continue
        points = tuple(Landmark(float(p.x), float(p.y), float(getattr(p, "z", 0.0))) for p in lms)
        label, score = "Unknown", 0.0
        if i < len(handedness_sets) and handedness_sets[i]:
            cat = handedness_sets[i][0]
            label = getattr(cat, "category_name", None) or "Unknown"
            score = float(getattr(cat, "score", 0.0) or 0.0)
        hands.append(HandObservation(landmarks=points, handedness=label, score=score))
    return FrameResult(timestamp_ms=timestamp_ms, frame_index=frame_index, hands=tuple(hands))


def _default_image_factory(rgb: np.ndarray) -> Any:
    import mediapipe as mp

    return mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)


class HandDetector:
    """Owns a HandLandmarker. Not thread-safe: call detect() from a single thread."""

    def __init__(
        self,
        config: DetectorConfig,
        landmarker: Any | None = None,
        image_factory: Callable[[np.ndarray], Any] = _default_image_factory,
    ) -> None:
        self._config = config
        self._landmarker = landmarker
        self._image_factory = image_factory
        self._last_ts = -1

    def open(self) -> None:
        if self._landmarker is not None:
            return
        model = Path(self._config.model_path)
        if not model.is_file():
            raise ModelError(f"model file not found: {model} (run with --download-model or place it manually)")
        import mediapipe as mp

        vision = mp.tasks.vision
        options = vision.HandLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model)),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=self._config.num_hands,
            min_hand_detection_confidence=self._config.min_hand_detection_confidence,
            min_hand_presence_confidence=self._config.min_hand_presence_confidence,
            min_tracking_confidence=self._config.min_tracking_confidence,
        )
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        log.info("hand landmarker created (%s)", model)

    def detect(self, frame: CapturedFrame) -> FrameResult:
        if self._landmarker is None:
            raise RuntimeError("HandDetector.open() must be called before detect()")
        import cv2

        rgb = np.ascontiguousarray(cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB))
        ts = max(frame.timestamp_ms, self._last_ts + 1)  # MediaPipe VIDEO mode needs strictly increasing ts
        self._last_ts = ts
        result = self._landmarker.detect_for_video(self._image_factory(rgb), ts)
        return convert_result(result, ts, frame.index)

    def close(self) -> None:
        lm, self._landmarker = self._landmarker, None
        if lm is not None and hasattr(lm, "close"):
            lm.close()

    def __enter__(self) -> "HandDetector":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
