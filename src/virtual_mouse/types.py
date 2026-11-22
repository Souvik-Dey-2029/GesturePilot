"""Shared immutable data types passed between modules (no behaviour beyond validation)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import numpy as np

NUM_LANDMARKS = 21


class LandmarkId(IntEnum):
    """MediaPipe hand landmark indices."""

    WRIST = 0
    THUMB_CMC = 1
    THUMB_MCP = 2
    THUMB_IP = 3
    THUMB_TIP = 4
    INDEX_MCP = 5
    INDEX_PIP = 6
    INDEX_DIP = 7
    INDEX_TIP = 8
    MIDDLE_MCP = 9
    MIDDLE_PIP = 10
    MIDDLE_DIP = 11
    MIDDLE_TIP = 12
    RING_MCP = 13
    RING_PIP = 14
    RING_DIP = 15
    RING_TIP = 16
    PINKY_MCP = 17
    PINKY_PIP = 18
    PINKY_DIP = 19
    PINKY_TIP = 20


@dataclass(frozen=True, slots=True)
class Landmark:
    """Normalized landmark: x,y in [0,1] relative to the (unmirrored) camera image; z is relative depth."""

    x: float
    y: float
    z: float = 0.0


@dataclass(frozen=True, slots=True)
class HandObservation:
    """One detected hand. `score` is the handedness classification score (see ARCHITECTURE.md)."""

    landmarks: tuple[Landmark, ...]
    handedness: str = "Unknown"
    score: float = 0.0

    def __post_init__(self) -> None:
        if len(self.landmarks) != NUM_LANDMARKS:
            raise ValueError(f"expected {NUM_LANDMARKS} landmarks, got {len(self.landmarks)}")

    def point(self, landmark_id: LandmarkId) -> Landmark:
        return self.landmarks[int(landmark_id)]


@dataclass(frozen=True, slots=True)
class CapturedFrame:
    """A BGR frame from the webcam. `image` must be treated as read-only."""

    image: np.ndarray
    timestamp_ms: int
    index: int


@dataclass(frozen=True, slots=True)
class FrameResult:
    """Detection output for one frame. `hands` may be empty."""

    timestamp_ms: int
    frame_index: int
    hands: tuple[HandObservation, ...]

    @property
    def primary_hand(self) -> HandObservation | None:
        return self.hands[0] if self.hands else None


@dataclass(frozen=True, slots=True)
class ScreenPoint:
    """Screen-space position in pixels (float, before integer rounding for OS calls)."""

    x: float
    y: float
