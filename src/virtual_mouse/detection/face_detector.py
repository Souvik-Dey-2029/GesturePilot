"""MediaPipe Face Landmarker Tasks Vision wrapper.

Extracts 478 face landmarks and facial blendshapes (specifically eyeBlinkLeft and eyeBlinkRight)
using the official FaceLandmarker model in live video streaming mode.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

import cv2
import mediapipe as mp
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core.base_options import BaseOptions

from ..eye.subsystem import FaceObservation
from ..types import CapturedFrame
from .model_assets import ModelError

log = logging.getLogger(__name__)


class FaceDetector:
    """Wraps MediaPipe FaceLandmarker with video timestamp tracking and blendshape extraction."""

    def __init__(
        self,
        model_path: Path | str = "models/face_landmarker.task",
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self.model_path = Path(model_path)
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self._landmarker: Optional[vision.FaceLandmarker] = None
        self._last_timestamp_ms: int = -1

    def open(self) -> None:
        if self._landmarker is not None:
            return
        if not self.model_path.is_file():
            raise ModelError(f"Face model missing: {self.model_path}. Download with ensure_face_model().")

        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(self.model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=self.min_detection_confidence,
            min_tracking_confidence=self.min_tracking_confidence,
            output_face_blendshapes=True,
        )
        self._landmarker = vision.FaceLandmarker.create_from_options(options)
        self._last_timestamp_ms = -1
        log.info("FaceLandmarker opened successfully with blendshapes enabled.")

    def close(self) -> None:
        if self._landmarker is not None:
            try:
                self._landmarker.close()
            except Exception as exc:  # noqa: BLE001
                log.warning("Error closing FaceLandmarker: %s", exc)
            self._landmarker = None
            self._last_timestamp_ms = -1
            log.info("FaceLandmarker closed.")

    @property
    def is_open(self) -> bool:
        return self._landmarker is not None

    def detect(self, frame: CapturedFrame) -> Optional[FaceObservation]:
        """Detect face landmarks and blendshapes from a captured video frame."""
        if self._landmarker is None:
            raise RuntimeError("FaceDetector must be opened before detect().")

        # MediaPipe Video mode requires strictly increasing timestamps
        ts = int(frame.timestamp_ms)
        if ts <= self._last_timestamp_ms:
            ts = self._last_timestamp_ms + 1
        self._last_timestamp_ms = ts

        # Convert BGR OpenCV image to MediaPipe RGB Image
        rgb = cv2.cvtColor(frame.image, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        result = self._landmarker.detect_for_video(mp_image, ts)
        if not result.face_landmarks:
            return None

        # Extract 468 or 478 face landmarks for first face
        raw_lms = result.face_landmarks[0]
        landmarks_tuple = tuple((lm.x, lm.y, lm.z) for lm in raw_lms)

        # Extract facial blendshapes (including eyeBlinkLeft, eyeBlinkRight)
        blendshapes_dict: dict[str, float] = {}
        if result.face_blendshapes:
            for category in result.face_blendshapes[0]:
                blendshapes_dict[category.category_name] = category.score

        return FaceObservation(
            landmarks=landmarks_tuple,
            blendshapes=blendshapes_dict,
            confidence=0.95,
        )
