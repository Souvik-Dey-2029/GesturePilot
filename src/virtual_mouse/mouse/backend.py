"""Mouse backend protocol and implementations. Backends perform OS calls and NEVER make safety decisions;
all callers must go through `MouseController` (see controller.py), which enforces the safety gate."""
from __future__ import annotations

import importlib
import logging
import sys
from typing import Any, Callable, Protocol

log = logging.getLogger(__name__)


class MouseBackendError(RuntimeError):
    """The OS-level mouse operation failed."""


class MouseFailSafeTriggered(MouseBackendError):
    """PyAutoGUI's corner failsafe fired."""


class MouseBackend(Protocol):
    def screen_size(self) -> tuple[int, int]: ...
    def move_to(self, x: int, y: int) -> None: ...
    def left_down(self) -> None: ...
    def left_up(self) -> None: ...
    def right_click(self) -> None: ...
    def scroll(self, amount: int) -> None:
        """Positive = scroll up (PyAutoGUI convention)."""
        ...


def _win32_force_left_up() -> None:
    """Release the left button via Win32 `mouse_event`, bypassing PyAutoGUI's failsafe check.
    Used only for RELEASING a held button (always the safe direction)."""
    if sys.platform != "win32":
        raise MouseBackendError("forced release is only available on Windows")
    import ctypes

    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # type: ignore[attr-defined]  # MOUSEEVENTF_LEFTUP


class PyAutoGUIBackend:
    """Real Windows backend. The failsafe is forced ON at construction and is never turned off.
    `PAUSE` is set to 0 and `_pause=False` passed per call: PyAutoGUI's default 0.1 s sleep after every call would cap
    the cursor at ~10 Hz. This does not affect the failsafe check, which runs before every call."""

    def __init__(self, module: Any | None = None, force_release_left: Callable[[], None] = _win32_force_left_up) -> None:
        if module is None:
            try:
                module = importlib.import_module("pyautogui")
            except Exception as exc:  # noqa: BLE001 - import can fail for many platform reasons (e.g. no display)
                raise MouseBackendError(f"pyautogui is unavailable: {exc!r}") from exc
        self._m = module
        self._m.FAILSAFE = True
        self._m.PAUSE = 0
        self._force_release_left = force_release_left

    def _call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, _pause=False, **kwargs)
        except self._m.FailSafeException as exc:
            raise MouseFailSafeTriggered("PyAutoGUI failsafe triggered (cursor at a screen corner)") from exc
        except Exception as exc:  # noqa: BLE001
            raise MouseBackendError(f"{getattr(fn, '__name__', 'call')} failed: {exc!r}") from exc

    def screen_size(self) -> tuple[int, int]:
        try:
            w, h = self._m.size()
            return int(w), int(h)
        except Exception as exc:  # noqa: BLE001
            raise MouseBackendError(f"could not read screen size: {exc!r}") from exc

    def move_to(self, x: int, y: int) -> None:
        self._call(self._m.moveTo, x, y)

    def left_down(self) -> None:
        self._call(self._m.mouseDown, button="left")

    def left_up(self) -> None:
        try:
            self._call(self._m.mouseUp, button="left")
        except MouseFailSafeTriggered:
            log.warning("failsafe blocked mouseUp; forcing button release via Win32")
            self._force_release_left()

    def right_click(self) -> None:
        self._call(self._m.rightClick)

    def scroll(self, amount: int) -> None:
        self._call(self._m.scroll, amount)


class FakeMouseBackend:
    """In-memory backend for tests. `events` holds (name, args) tuples in call order."""

    def __init__(self, width: int = 1920, height: int = 1080) -> None:
        self._size = (width, height)
        self.events: list[tuple[str, tuple[int, ...]]] = []
        self.position: tuple[int, int] = (width // 2, height // 2)
        self.left_held = False
        self.fail_on: dict[str, Exception] = {}  # method name -> exception to raise on every call

    def _do(self, name: str, *args: int) -> None:
        exc = self.fail_on.get(name)
        if exc is not None:
            raise exc
        self.events.append((name, args))

    def screen_size(self) -> tuple[int, int]:
        return self._size

    def move_to(self, x: int, y: int) -> None:
        self._do("move_to", x, y)
        self.position = (x, y)

    def left_down(self) -> None:
        self._do("left_down")
        self.left_held = True

    def left_up(self) -> None:
        self._do("left_up")
        self.left_held = False

    def right_click(self) -> None:
        self._do("right_click")

    def scroll(self, amount: int) -> None:
        self._do("scroll", amount)

    def names(self) -> list[str]:
        return [n for n, _ in self.events]
