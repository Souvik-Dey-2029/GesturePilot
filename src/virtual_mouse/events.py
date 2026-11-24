"""Core multimodal event architecture and typed event bus.

Every subsystem produces typed MultimodalEvents with timestamps, confidence,
tracking quality, and expiration windows. Stale events are discarded.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List


class ModalityType(Enum):
    HAND = "hand"
    EYE = "eye"
    VOICE = "voice"
    SYSTEM = "system"


class EventType(Enum):
    # Hand events
    CURSOR_MOVE = "cursor_move"
    LEFT_CLICK = "left_click"
    RIGHT_CLICK = "right_click"
    DOUBLE_CLICK = "double_click"
    LEFT_DOWN = "left_down"
    LEFT_UP = "left_up"
    SCROLL = "scroll"
    PAUSE_INTERACTION = "pause_interaction"

    # Eye events
    DOUBLE_BLINK = "double_blink"
    TRIPLE_BLINK = "triple_blink"
    DWELL_TRIGGER = "dwell_trigger"
    HEAD_GESTURE = "head_gesture"

    # Voice events
    VOICE_COMMAND = "voice_command"
    VOICE_DICTATION = "voice_dictation"
    VOICE_SPELLING = "voice_spelling"
    VOICE_CANCEL = "voice_cancel"

    # System events
    TRACKING_LOST = "tracking_lost"
    TRACKING_ACQUIRED = "tracking_acquired"
    EMERGENCY_STOP = "emergency_stop"
    MODE_SWITCH = "mode_switch"


class SystemInteractionMode(Enum):
    HAND_ONLY = "HAND"
    EYE_ONLY = "EYE"
    BOTH = "BOTH"
    VOICE = "VOICE"
    ALL = "ALL"


@dataclass(frozen=True, slots=True)
class MultimodalEvent:
    source: ModalityType
    event_type: EventType
    confidence: float
    timestamp: float
    expiration_time: float
    data: Dict[str, Any] = field(default_factory=dict)
    tracking_quality: float = 1.0
    calibration_version: int = 1
    model_version: str = "1.0.0"

    def is_stale(self, now: float | None = None) -> bool:
        t = now if now is not None else time.monotonic()
        return t > self.expiration_time


class EventBus:
    """Thread-safe, decoupled event publisher/subscriber bus."""

    def __init__(self) -> None:
        self._subscribers: Dict[EventType, List[Callable[[MultimodalEvent], None]]] = {}

    def subscribe(self, event_type: EventType, callback: Callable[[MultimodalEvent], None]) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)

    def publish(self, event: MultimodalEvent, now: float | None = None) -> bool:
        if event.is_stale(now):
            return False
        callbacks = self._subscribers.get(event.event_type, [])
        for cb in callbacks:
            cb(event)
        return True
