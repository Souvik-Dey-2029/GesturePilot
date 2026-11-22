"""Gesture state definitions, event types, and recognition data types for v005."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class MouseActionType(Enum):
    NONE = auto()
    LEFT_CLICK = auto()
    DOUBLE_CLICK = auto()
    LEFT_DOWN = auto()
    LEFT_UP = auto()
    RIGHT_CLICK = auto()
    SCROLL = auto()


@dataclass(frozen=True, slots=True)
class MouseAction:
    action_type: MouseActionType
    scroll_amount: int = 0  # Only used when action_type is SCROLL


class InteractionState(Enum):
    """Mutually exclusive system interaction states for v005."""
    DISABLED = "disabled"
    UNKNOWN = "unknown"
    PAUSED = "paused"
    POINTER = "pointer"
    TWO_FINGER_PENDING = "two_finger_pending"
    THREE_FINGER_PENDING = "three_finger_pending"
    PINCH_PENDING = "pinch_pending"
    SCROLLING = "scrolling"
    TRACKING_LOST = "tracking_lost"
    EMERGENCY_STOP = "emergency_stop"


class HandPose(Enum):
    """Static spatial configuration of the hand for v005."""
    UNKNOWN = "unknown"
    OPEN_PALM = "open_palm"            # 5 fingers extended -> PAUSE
    POINTER = "pointer"                # Index extended, middle/ring/pinky curled -> POINTER MODE
    TWO_FINGERS = "two_fingers"        # Index & middle extended, ring & pinky curled -> LEFT CLICK / SCROLL
    THREE_FINGERS = "three_fingers"    # Index, middle & ring extended, pinky curled -> RIGHT CLICK / SCROLL
    PINCH = "pinch"                    # Thumb & index pinch -> DOUBLE CLICK
    FIST = "fist"


class ActiveGesture(Enum):
    """Active gesture indicator for HUD and metrics."""
    NONE = "none"
    PAUSE = "pause"
    POINTER = "pointer"
    LEFT_CLICK = "left_click"
    RIGHT_CLICK = "right_click"
    DOUBLE_CLICK = "double_click"
    SCROLL = "scroll"


@dataclass(frozen=True, slots=True)
class GestureMetrics:
    pinch_dist: float = 0.0
    index_extended: bool = False
    middle_extended: bool = False
    ring_extended: bool = False
    pinky_extended: bool = False
    thumb_extended: bool = False
    recognized_pose: HandPose = HandPose.UNKNOWN
    rejection_reason: str = ""
    scroll_direction: str = "NONE"  # UP | DOWN | NONE
    stability_pct: int = 100


@dataclass(frozen=True, slots=True)
class GestureResult:
    active_gesture: ActiveGesture
    action: MouseAction
    metrics: GestureMetrics
    interaction_state: InteractionState = InteractionState.POINTER
    cursor_movement_allowed: bool = True
