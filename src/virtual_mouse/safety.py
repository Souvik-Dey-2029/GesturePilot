"""Emergency stop, enable/disable switch and tracking-reliability gate.

Rule: mouse events may be emitted only if `SafetyController.can_emit()` is True. The controller
starts DISABLED; it cannot be enabled while the emergency stop is latched.
"""
from __future__ import annotations

import logging
import threading
from enum import Enum
from typing import Callable

from .config import SafetyConfig
from .types import HandObservation

log = logging.getLogger(__name__)


class TrackingState(Enum):
    ACQUIRING = "acquiring"  # no reliable hand seen yet
    RELIABLE = "reliable"
    LOST = "lost"


class EmergencyStop:
    """Thread-safe latch. Listeners (e.g. a future mouse controller releasing buttons) run on trigger."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._set = False
        self._reason = ""
        self._listeners: list[Callable[[str], None]] = []

    def add_listener(self, callback: Callable[[str], None]) -> None:
        with self._lock:
            self._listeners.append(callback)

    def trigger(self, reason: str = "manual") -> None:
        with self._lock:
            already, self._set, self._reason = self._set, True, reason
            listeners = list(self._listeners)
        if already:
            return
        log.warning("EMERGENCY STOP: %s", reason)
        for cb in listeners:
            try:
                cb(reason)
            except Exception:  # noqa: BLE001 - one bad listener must not block the others
                log.exception("emergency-stop listener failed")

    def clear(self) -> None:
        with self._lock:
            self._set, self._reason = False, ""

    @property
    def is_set(self) -> bool:
        with self._lock:
            return self._set

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason


class TrackingMonitor:
    """Decides whether hand tracking is trustworthy. Time is injected (`now`, seconds) for testability."""

    def __init__(self, config: SafetyConfig) -> None:
        self._cfg = config
        self.reset()

    def reset(self) -> None:
        self._state = TrackingState.ACQUIRING
        self._good_streak = 0
        self._last_good: float | None = None

    @property
    def state(self) -> TrackingState:
        return self._state

    def update(self, hand: HandObservation | None, now: float) -> TrackingState:
        good = hand is not None and hand.score >= self._cfg.min_hand_score
        if good:
            self._good_streak += 1
            self._last_good = now
            if self._state is not TrackingState.RELIABLE and self._good_streak >= self._cfg.recovery_frames:
                self._state = TrackingState.RELIABLE
        else:
            self._good_streak = 0
            if self._state is TrackingState.RELIABLE and (
                self._last_good is None or now - self._last_good > self._cfg.lost_hand_timeout_s
            ):
                self._state = TrackingState.LOST
                log.info("tracking lost")
        return self._state


class SafetyController:
    def __init__(self, config: SafetyConfig, estop: EmergencyStop | None = None) -> None:
        self.estop = estop or EmergencyStop()
        self.monitor = TrackingMonitor(config)
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self) -> bool:
        """Enable mouse control. Returns False (and stays disabled) while the emergency stop is latched."""
        if self.estop.is_set:
            return False
        self._enabled = True
        self.monitor.reset()
        return True

    def disable(self) -> None:
        self._enabled = False

    def emergency_stop(self, reason: str = "manual") -> None:
        """Disable control FIRST (so can_emit() is already False), then latch the stop and run listeners."""
        self._enabled = False
        self.estop.trigger(reason)

    def acknowledge_emergency_stop(self) -> None:
        """Step 1 of the safe re-enable procedure: clear the latch but stay DISABLED.
        Step 2 is an explicit enable(), after which tracking must become RELIABLE again before any event is emitted."""
        self._enabled = False
        self.estop.clear()
        self.monitor.reset()

    def update(self, hand: HandObservation | None, now: float) -> TrackingState:
        return self.monitor.update(hand, now)

    def can_emit(self) -> bool:
        return self._enabled and not self.estop.is_set and self.monitor.state is TrackingState.RELIABLE
