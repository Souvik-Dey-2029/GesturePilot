"""Gesture recognition module exports."""
from .config import GestureConfig
from .geometry import (
    compute_hand_scale,
    euclidean_dist_2d,
    euclidean_dist_3d,
    finger_extension_ratio,
    is_finger_curled_strict,
    is_finger_extended_strict,
    normalized_distance,
)
from .recognizer import GestureRecognizer, is_finger_extended
from .types import (
    ActiveGesture,
    GestureMetrics,
    GestureResult,
    HandPose,
    InteractionState,
    MouseAction,
    MouseActionType,
)

__all__ = [
    "ActiveGesture",
    "GestureConfig",
    "GestureMetrics",
    "GestureRecognizer",
    "GestureResult",
    "HandPose",
    "InteractionState",
    "MouseAction",
    "MouseActionType",
    "compute_hand_scale",
    "euclidean_dist_2d",
    "euclidean_dist_3d",
    "finger_extension_ratio",
    "is_finger_curled_strict",
    "is_finger_extended",
    "is_finger_extended_strict",
    "normalized_distance",
]
