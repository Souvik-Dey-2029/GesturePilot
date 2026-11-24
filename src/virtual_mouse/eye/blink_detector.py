"""Deterministic Temporal Blink Detector and Intentional Blink Sequence Recognizer.

Part 1: BlinkDetector detects individual natural physiological blinks:
  EYES_OPEN -> EYES_CLOSING -> EYES_CLOSED -> EYES_OPENING -> EYES_OPEN
  Measures duration, verifies min/max closure windows, prevents repeat transitions.

Part 2: BlinkSequenceRecognizer accumulates completed blinks into commands:
  - Natural single blink (inter-blink pause > max_pause or count==1) -> NO ACTION
  - Intentional double blink (2 rapid blinks with inter-blink pause <= max_pause) -> SCROLL DOWN (-3)
  - Intentional triple blink (3 rapid blinks with inter-blink pause <= max_pause) -> SCROLL UP (+3)
  - Cooldown lockout after action dispatch.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional
from ..events import EventType, ModalityType, MultimodalEvent
from .feature_extractor import EyeFeatureObservation
from .state_estimator import EyeState, EyeStateEstimator

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CompletedBlink:
    start_time: float
    end_time: float
    duration: float
    min_ear: float
    max_blend: float


class BlinkDetector:
    """Detects single complete, valid physiological blinks from eye state transitions."""

    def __init__(
        self,
        min_duration_s: float = 0.05,  # 50ms (at least 2 frames @ 30 FPS)
        max_duration_s: float = 0.45,  # 450ms (allows deliberate prolonged closure)
    ) -> None:
        self.min_duration_s = min_duration_s
        self.max_duration_s = max_duration_s

        self._in_blink = False
        self._blink_start_time: Optional[float] = None
        self._min_ear_observed = 1.0
        self._max_blend_observed = 0.0
        self.last_rejection_reason = ""

    @property
    def in_blink(self) -> bool:
        return self._in_blink

    def reset(self) -> None:
        self._in_blink = False
        self._blink_start_time = None
        self._min_ear_observed = 1.0
        self._max_blend_observed = 0.0
        self.last_rejection_reason = ""

    def update(self, state: EyeState, obs: EyeFeatureObservation) -> Optional[CompletedBlink]:
        t = obs.timestamp

        # Reset on tracking loss
        if state in (EyeState.EYE_TRACKING_LOST, EyeState.EYE_STATE_UNCERTAIN):
            if self._in_blink:
                self.last_rejection_reason = f"Blink aborted due to {state.value}"
            self.reset()
            return None

        # Onset of closure
        if state in (EyeState.EYES_CLOSING, EyeState.EYES_CLOSED):
            if not self._in_blink:
                self._in_blink = True
                self._blink_start_time = t
                self._min_ear_observed = obs.ear_avg
                self._max_blend_observed = obs.blink_avg
            else:
                self._min_ear_observed = min(self._min_ear_observed, obs.ear_avg)
                self._max_blend_observed = max(self._max_blend_observed, obs.blink_avg)
            return None

        # Eyes returned to open (recovery completed)
        if state == EyeState.EYES_OPEN and self._in_blink:
            start_t = self._blink_start_time or t
            duration = t - start_t
            min_ear = self._min_ear_observed
            max_blend = self._max_blend_observed

            self._in_blink = False
            self._blink_start_time = None
            self._min_ear_observed = 1.0
            self._max_blend_observed = 0.0

            # Duration filter
            if duration < self.min_duration_s:
                self.last_rejection_reason = f"Micro-blink rejected ({duration:.2f}s < {self.min_duration_s}s)"
                return None
            if duration > self.max_duration_s:
                self.last_rejection_reason = f"Prolonged closure rejected ({duration:.2f}s > {self.max_duration_s}s)"
                return None

            self.last_rejection_reason = ""
            return CompletedBlink(start_t, t, duration, min_ear, max_blend)

        return None


class BlinkSequenceRecognizer:
    """Accumulates completed blinks into intentional Double/Triple-Blink commands.
    
    Invariants:
    1. Distinguishes natural single blinks: inter-blink pause > max_inter_blink_pause_s -> single blink dropped.
    2. Intentional double blink: 2 completed blinks with pause <= max_inter_blink_pause_s.
       Finalizes ONLY after quiet interval (wait_for_triple_timeout_s) so triple blink is not cut short.
    3. Intentional triple blink: 3 completed blinks within sequence window -> executes immediately.
    4. Exactly ONE command dispatched per sequence.
    5. Cooldown lockout prevents back-to-back duplicate firings.
    """

    def __init__(
        self,
        max_inter_blink_pause_s: float = 0.45,
        wait_for_triple_timeout_s: float = 0.35,
        cooldown_s: float = 0.60,
        scroll_amount_ticks: int = 3,
    ) -> None:
        self.max_inter_blink_pause_s = max_inter_blink_pause_s
        self.wait_for_triple_timeout_s = wait_for_triple_timeout_s
        self.cooldown_s = cooldown_s
        self.scroll_amount_ticks = scroll_amount_ticks

        self._completed_blinks: List[CompletedBlink] = []
        self._last_blink_time: Optional[float] = None
        self._cooldown_until: float = 0.0
        self.last_action = "NONE"
        self.last_rejection = ""

    @property
    def sequence_count(self) -> int:
        return len(self._completed_blinks)

    @property
    def cooldown_until(self) -> float:
        return self._cooldown_until

    def reset(self) -> None:
        self._completed_blinks.clear()
        self._last_blink_time = None
        self._cooldown_until = 0.0
        self.last_action = "NONE"
        self.last_rejection = ""

    def cancel(self, reason: str = "Tracking lost") -> None:
        if self._completed_blinks:
            self.last_rejection = reason
        self._completed_blinks.clear()
        self._last_blink_time = None

    def process(
        self,
        new_blink: Optional[CompletedBlink],
        now: float,
        eye_state: EyeState = EyeState.EYES_OPEN,
    ) -> List[MultimodalEvent]:
        events: List[MultimodalEvent] = []

        # Tracking loss cancels pending sequence immediately
        if eye_state == EyeState.EYE_TRACKING_LOST:
            self.cancel("Sequence cancelled due to tracking loss")
            return events

        # 1. Process Newly Arrived Blink
        if new_blink is not None:
            if now < self._cooldown_until:
                self.last_rejection = f"In cooldown window ({self._cooldown_until - now:.2f}s remaining)"
                return events

            if not self._completed_blinks:
                # First blink in sequence
                self._completed_blinks.append(new_blink)
                self._last_blink_time = new_blink.end_time
                self.last_rejection = "Blink 1 recorded"
            else:
                pause = new_blink.start_time - (self._last_blink_time or new_blink.start_time)
                if pause <= self.max_inter_blink_pause_s:
                    self._completed_blinks.append(new_blink)
                    self._last_blink_time = new_blink.end_time
                    self.last_rejection = f"Blink {len(self._completed_blinks)} recorded"
                else:
                    # Too much time elapsed between blinks; discard previous sequence as natural blinking
                    self._completed_blinks = [new_blink]
                    self._last_blink_time = new_blink.end_time
                    self.last_rejection = "Previous blink expired (natural blink gap); starting new sequence"

            # Check for immediate Triple Blink (count == 3)
            if len(self._completed_blinks) >= 3:
                events.append(MultimodalEvent(
                    source=ModalityType.EYE,
                    event_type=EventType.TRIPLE_BLINK,
                    confidence=0.92,
                    timestamp=now,
                    expiration_time=now + 0.35,
                    data={"action": "scroll_up", "amount": self.scroll_amount_ticks},
                ))
                self.last_action = f"TRIPLE_BLINK (Scroll Up +{self.scroll_amount_ticks})"
                self.last_rejection = "Accepted (Triple Blink)"
                self._cooldown_until = now + self.cooldown_s
                self._completed_blinks.clear()
                self._last_blink_time = None
                return events

        # 2. Sequence Finalization Window (Check when no new blink arrived)
        if self._completed_blinks and eye_state == EyeState.EYES_OPEN:
            time_since_last = now - (self._last_blink_time or now)

            if len(self._completed_blinks) == 2:
                # Wait for potential 3rd blink quiet window to expire
                if time_since_last >= self.wait_for_triple_timeout_s:
                    events.append(MultimodalEvent(
                        source=ModalityType.EYE,
                        event_type=EventType.DOUBLE_BLINK,
                        confidence=0.90,
                        timestamp=now,
                        expiration_time=now + 0.35,
                        data={"action": "scroll_down", "amount": -self.scroll_amount_ticks},
                    ))
                    self.last_action = f"DOUBLE_BLINK (Scroll Down -{self.scroll_amount_ticks})"
                    self.last_rejection = "Accepted (Double Blink)"
                    self._cooldown_until = now + self.cooldown_s
                    self._completed_blinks.clear()
                    self._last_blink_time = None
                    return events

            elif len(self._completed_blinks) == 1:
                # Single blink timeout -> dropped as natural involuntary blink
                if time_since_last >= self.max_inter_blink_pause_s:
                    self.last_rejection = "Single natural blink ignored (no action)"
                    self._completed_blinks.clear()
                    self._last_blink_time = None

        return events
