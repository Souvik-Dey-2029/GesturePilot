"""Unified Hand Subsystem with Dual-Profile Support (v004 fallback & v005 mutually exclusive)."""
from __future__ import annotations

import time
from typing import Any, Tuple
from ..events import EventType, ModalityType, MultimodalEvent
from ..gestures.config import GestureConfig
from ..gestures.recognizer import GestureRecognizer as V005Recognizer
from ..gestures.types import GestureResult, MouseActionType
from ..types import HandObservation
from .features import extract_hand_features, HandFeatures


class HandSubsystem:
    """Manages hand gesture classification, cursor target generation, and event publishing."""

    def __init__(self, profile: str = "v005", config: GestureConfig | None = None) -> None:
        self.profile = profile.lower()
        self.config = config or GestureConfig()
        self.v005_engine = V005Recognizer(self.config)

        # v004 Pinch state tracking (fallback profile)
        self._v004_pinched = False
        self._v004_pinch_start: float | None = None
        self._v004_drag_active = False

    def reset(self) -> None:
        self.v005_engine.reset()
        self._v004_pinched = False
        self._v004_pinch_start = None
        self._v004_drag_active = False

    def process(self, hand: HandObservation | None, now: float | None = None) -> Tuple[GestureResult, list[MultimodalEvent]]:
        t = now if now is not None else time.monotonic()
        events: list[MultimodalEvent] = []

        if hand is None:
            self.reset()
            res = self.v005_engine.update(None, t)
            events.append(MultimodalEvent(
                source=ModalityType.HAND,
                event_type=EventType.TRACKING_LOST,
                confidence=0.0,
                timestamp=t,
                expiration_time=t + 0.1,
                tracking_quality=0.0,
            ))
            return res, events

        features = extract_hand_features(hand)

        # Profile selection: v005 (mutually exclusive) vs v004 (pinch-click & hold-drag fallback)
        if self.profile == "v004":
            res = self._process_v004(hand, features, t, events)
        else:
            res = self.v005_engine.update(hand, t)
            self._convert_v005_action_to_events(res, t, events, features)

        return res, events

    def _convert_v005_action_to_events(self, res: GestureResult, t: float, events: list[MultimodalEvent], f: HandFeatures) -> None:
        action = res.action.action_type
        exp = t + 0.15

        if action == MouseActionType.LEFT_CLICK:
            events.append(MultimodalEvent(ModalityType.HAND, EventType.LEFT_CLICK, 0.95, t, exp, {"x": f.index_tip.x, "y": f.index_tip.y}))
        elif action == MouseActionType.RIGHT_CLICK:
            events.append(MultimodalEvent(ModalityType.HAND, EventType.RIGHT_CLICK, 0.95, t, exp, {"x": f.index_tip.x, "y": f.index_tip.y}))
        elif action == MouseActionType.DOUBLE_CLICK:
            events.append(MultimodalEvent(ModalityType.HAND, EventType.DOUBLE_CLICK, 0.95, t, exp, {"x": f.index_tip.x, "y": f.index_tip.y}))
        elif action == MouseActionType.SCROLL:
            events.append(MultimodalEvent(ModalityType.HAND, EventType.SCROLL, 0.90, t, exp, {"amount": res.action.scroll_amount}))

    def _process_v004(self, hand: HandObservation, f: HandFeatures, t: float, events: list[MultimodalEvent]) -> GestureResult:
        # v004 pinch-to-click & drag fallback
        res = self.v005_engine.update(hand, t)
        pinch_dist = f.thumb_index_dist
        exp = t + 0.15

        if pinch_dist < self.config.pinch_threshold:
            if not self._v004_pinched:
                self._v004_pinched = True
                self._v004_pinch_start = t
            elif (t - (self._v004_pinch_start or t)) >= 0.35 and not self._v004_drag_active:
                self._v004_drag_active = True
                events.append(MultimodalEvent(ModalityType.HAND, EventType.LEFT_DOWN, 0.95, t, exp))
        elif pinch_dist > self.config.pinch_release_threshold:
            if self._v004_pinched:
                if self._v004_drag_active:
                    self._v004_drag_active = False
                    events.append(MultimodalEvent(ModalityType.HAND, EventType.LEFT_UP, 0.95, t, exp))
                else:
                    events.append(MultimodalEvent(ModalityType.HAND, EventType.LEFT_CLICK, 0.95, t, exp))
                self._v004_pinched = False
                self._v004_pinch_start = None

        return res
