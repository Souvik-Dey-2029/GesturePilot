"""Confidence-Aware Multimodal Fusion Engine and Central Action Policy.

Synchronizes input timestamps, enforces source authorization, resolves
contradictory events, and executes graceful degradation across Hand, Eye, and Voice.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from ..events import EventType, ModalityType, MultimodalEvent, SystemInteractionMode
from ..mouse.controller import MouseController

log = logging.getLogger(__name__)


@dataclass
class FusionDecision:
    authorized: bool
    action: str
    target: Dict[str, Any]
    confidence: float
    reason: str


class MultimodalFusionEngine:
    """Combines and gates events from Hand, Eye, and Voice based on the active interaction mode."""

    def __init__(self, mouse_controller: MouseController, mode: SystemInteractionMode = SystemInteractionMode.HAND_ONLY) -> None:
        self._mouse = mouse_controller
        self.mode = mode
        self.master_armed = False
        self.min_confidence = 0.85

    def set_mode(self, mode: SystemInteractionMode) -> None:
        self.mode = mode
        log.info("System interaction mode set to %s", mode.value)

    def arm(self) -> None:
        self.master_armed = True
        log.info("Master control ARMED")

    def disarm(self) -> None:
        self.master_armed = False
        self._mouse.release_all()
        log.info("Master control DISARMED")

    def evaluate(self, event: MultimodalEvent, now: float | None = None) -> FusionDecision:
        t = now if now is not None else time.monotonic()

        # 1. Stale event rejection
        if event.is_stale(t):
            return FusionDecision(False, "reject", {}, 0.0, "Stale event expired")

        # 2. Confidence threshold
        if event.confidence < self.min_confidence:
            return FusionDecision(False, "reject", {}, event.confidence, "Confidence below threshold")

        # 3. Emergency stop / System priority
        if event.event_type == EventType.EMERGENCY_STOP:
            self.disarm()
            return FusionDecision(True, "emergency_stop", {}, 1.0, "Emergency stop latched")

        # 4. Modality Source Authorization Check
        if not self._is_source_authorized(event.source):
            return FusionDecision(False, "blocked", {}, event.confidence, f"Source {event.source.value} inactive in mode {self.mode.value}")

        # 5. Master Armed Gate
        if not self.master_armed and event.event_type not in (EventType.MODE_SWITCH, EventType.VOICE_CANCEL):
            return FusionDecision(False, "disarmed", {}, event.confidence, "Master control is disarmed")

        # 6. Action Policy Execution
        return self._execute_action_policy(event)

    def _is_source_authorized(self, source: ModalityType) -> bool:
        if self.mode == SystemInteractionMode.ALL:
            return True
        if self.mode == SystemInteractionMode.BOTH and source in (ModalityType.HAND, ModalityType.EYE):
            return True
        if self.mode == SystemInteractionMode.HAND_ONLY and source == ModalityType.HAND:
            return True
        if self.mode == SystemInteractionMode.EYE_ONLY and source == ModalityType.EYE:
            return True
        if self.mode == SystemInteractionMode.VOICE and source == ModalityType.VOICE:
            return True
        if source == ModalityType.SYSTEM:
            return True
        return False

    def _execute_action_policy(self, event: MultimodalEvent) -> FusionDecision:
        ev_type = event.event_type

        # Mouse clicks
        if ev_type == EventType.LEFT_CLICK:
            self._mouse.left_down()
            self._mouse.left_up()
            return FusionDecision(True, "mouse.left_click", event.data, event.confidence, "Left click executed")

        if ev_type == EventType.RIGHT_CLICK:
            self._mouse.right_click()
            return FusionDecision(True, "mouse.right_click", event.data, event.confidence, "Right click executed")

        if ev_type == EventType.DOUBLE_CLICK:
            self._mouse.left_down()
            self._mouse.left_up()
            self._mouse.left_down()
            self._mouse.left_up()
            return FusionDecision(True, "mouse.double_click", event.data, event.confidence, "Double click executed")

        # Mouse holds (drag)
        if ev_type == EventType.LEFT_DOWN:
            self._mouse.left_down()
            return FusionDecision(True, "mouse.left_down", event.data, event.confidence, "Left down held")

        if ev_type == EventType.LEFT_UP:
            self._mouse.left_up()
            return FusionDecision(True, "mouse.left_up", event.data, event.confidence, "Left button released")

        # Scrolling (from Hand or Eye blink sequences)
        if ev_type in (EventType.SCROLL, EventType.DOUBLE_BLINK, EventType.TRIPLE_BLINK):
            amount = event.data.get("amount", 0)
            if amount != 0:
                self._mouse.scroll_wheel(amount)
                return FusionDecision(True, "mouse.scroll", {"amount": amount}, event.confidence, f"Scrolled {amount} ticks")

        # Tracking loss safety guarantee
        if ev_type == EventType.TRACKING_LOST:
            self._mouse.release_all()
            return FusionDecision(True, "safety.tracking_lost", {}, 1.0, "Tracking lost; buttons released")

        # Voice and Browser automation commands
        if ev_type in (EventType.VOICE_COMMAND, EventType.VOICE_DICTATION, EventType.VOICE_SPELLING):
            return FusionDecision(True, "voice.command", event.data, event.confidence, "Voice command routed to bridge")

        return FusionDecision(False, "unhandled", event.data, event.confidence, "No action policy for event")
