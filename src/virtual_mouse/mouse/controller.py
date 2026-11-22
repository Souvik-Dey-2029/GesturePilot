"""Safety gate in front of a MouseBackend. This is the ONLY object that may call a backend."""
from __future__ import annotations

import logging
import threading
from typing import Callable

from ..safety import SafetyController
from .backend import MouseBackend, MouseBackendError, MouseFailSafeTriggered

log = logging.getLogger(__name__)


class MouseController:
    """Gate rules:
    * move/press/click/scroll are emitted only when `SafetyController.can_emit()` is True (checked under a lock).
    * RELEASING a held button is always allowed (it is the safe direction).
    * A backend failure or PyAutoGUI failsafe latches an emergency stop (which releases held buttons).
    * An emergency stop (from any source) releases held buttons via a listener registered here.
    """

    def __init__(self, backend: MouseBackend, safety: SafetyController) -> None:
        self._backend = backend
        self._safety = safety
        self._lock = threading.RLock()
        self._left_held = False
        safety.estop.add_listener(lambda _reason: self.release_all())

    @property
    def left_held(self) -> bool:
        return self._left_held

    def move_to(self, x: int, y: int) -> bool:
        return self._emit(lambda: self._backend.move_to(x, y))

    def left_down(self) -> bool:
        with self._lock:  # re-entrant: keeps "pressed" and the held flag atomic w.r.t. emergency-stop release
            ok = self._emit(self._backend.left_down)
            if ok:
                self._left_held = True
            return ok

    def right_click(self) -> bool:
        return self._emit(self._backend.right_click)

    def scroll_wheel(self, amount: int) -> bool:
        return self._emit(lambda: self._backend.scroll(amount))

    def scroll(self, amount: int) -> bool:
        """Alias for scroll_wheel."""
        return self.scroll_wheel(amount)

    def left_up(self) -> bool:
        """Ungated release. Returns True if a release was performed."""
        with self._lock:
            if not self._left_held:
                return False
            try:
                self._backend.left_up()
            except MouseBackendError:
                log.critical("FAILED to release left mouse button; it may be stuck down", exc_info=True)
                return False
            self._left_held = False
            return True

    def release_all(self) -> None:
        self.left_up()

    def _emit(self, action: Callable[[], None]) -> bool:
        with self._lock:
            if not self._safety.can_emit():
                return False
            try:
                action()
            except MouseFailSafeTriggered:
                self._safety.emergency_stop("PyAutoGUI failsafe triggered")
                return False
            except MouseBackendError as exc:
                self._safety.emergency_stop(f"mouse backend failure: {exc}")
                return False
            return True
