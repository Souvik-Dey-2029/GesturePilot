"""Cursor-only pipeline: Camera -> HandDetector -> SafetyController -> CoordinateMapper -> PointFilter -> MouseController.

`step()` processes one newest frame and reports what happened; `run()` loops `step()` with guaranteed cleanup.
All OS mouse output goes through `MouseController`, which applies the safety gate.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from .capture.camera import Camera
from .config import AppConfig
from .detection.hand_detector import HandDetector
from .gestures.config import GestureConfig
from .gestures.recognizer import GestureRecognizer
from .gestures.types import GestureResult, MouseActionType
from .mapping.coordinates import CoordinateMapper
from .mapping.smoothing import PointFilter
from .mouse.backend import MouseBackend, PyAutoGUIBackend
from .mouse.controller import MouseController
from .safety import SafetyController, TrackingState
from .types import CapturedFrame, FrameResult, LandmarkId

log = logging.getLogger(__name__)


class FrameSource(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def read(self, timeout: float = ...) -> CapturedFrame | None: ...


class HandDetectorLike(Protocol):
    def open(self) -> None: ...
    def close(self) -> None: ...
    def detect(self, frame: CapturedFrame) -> FrameResult: ...


class StepOutcome(Enum):
    NO_FRAME = "no_frame"  # no new frame within the timeout
    UNRELIABLE = "unreliable"  # tracking not RELIABLE (acquiring or lost): nothing emitted
    NO_HAND = "no_hand"  # reliable, but no hand in this frame (brief dropout)
    BLOCKED = "blocked"  # target computed, safety gate / backend refused it
    MOVED = "moved"  # cursor move was emitted
    DETECTOR_ERROR = "detector_error"  # single detector failure tolerated
    CAMERA_FAILURE = "camera_failure"  # fatal: emergency stop latched
    DETECTOR_FAILURE = "detector_failure"  # fatal: emergency stop latched


FATAL_OUTCOMES = frozenset({StepOutcome.CAMERA_FAILURE, StepOutcome.DETECTOR_FAILURE})


@dataclass(frozen=True, slots=True)
class StepReport:
    outcome: StepOutcome
    tracking: TrackingState
    frame: CapturedFrame | None = None
    result: FrameResult | None = None
    target: tuple[int, int] | None = None  # pixel target actually requested from the mouse gate
    gesture: GestureResult | None = None


class Pipeline:
    def __init__(
        self,
        camera: FrameSource,
        detector: HandDetectorLike,
        safety: SafetyController,
        mapper: CoordinateMapper,
        smoother: PointFilter,
        mouse: MouseController,
        gestures: GestureRecognizer | None = None,
        corner_guard_px: int = 1,
        max_detector_errors: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._camera, self._detector, self._mouse = camera, detector, mouse
        self.safety = safety
        self._mapper, self._smoother = mapper, smoother
        self._gestures = gestures or GestureRecognizer()
        self._guard = corner_guard_px
        self._max_det_errors = max_detector_errors
        self._clock = clock
        self._det_errors = 0
        self._stop = threading.Event()
        self.last_error: str | None = None

    @property
    def mouse_controller(self) -> MouseController:
        return self._mouse

    # -- lifecycle ------------------------------------------------------------------------
    def open(self) -> None:
        """Open detector then camera; on failure release whatever was opened and re-raise."""
        self._stop.clear()
        self._detector.open()
        try:
            self._camera.start()
        except Exception:
            self._safe(self._detector.close, "detector close")
            raise

    def close(self) -> None:
        """Idempotent. Disables control, releases held buttons, then frees camera and detector (each guarded)."""
        self.safety.disable()
        self._safe(self._mouse.release_all, "release buttons")
        self._smoother.reset()
        self._gestures.reset()
        self._safe(self._camera.stop, "camera stop")
        self._safe(self._detector.close, "detector close")

    def request_stop(self) -> None:
        self._stop.set()

    def __enter__(self) -> "Pipeline":
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @staticmethod
    def _safe(fn: Callable[[], None], what: str) -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001 - cleanup must continue through every step
            log.exception("%s failed during cleanup", what)

    # -- processing -----------------------------------------------------------------------
    def step(self, timeout: float = 0.5) -> StepReport:
        try:
            frame = self._camera.read(timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - CameraError or any driver failure
            self._fatal("camera failure", exc)
            return StepReport(StepOutcome.CAMERA_FAILURE, self.safety.monitor.state)

        now = self._clock()
        if frame is None:
            state = self.safety.update(None, now)  # lets the lost-hand timeout run even if the camera stalls
            self._reset_if_unreliable(state)
            if state is not TrackingState.RELIABLE:
                self._gestures.reset()
                self._mouse.release_all()
            return StepReport(StepOutcome.NO_FRAME, state)

        try:
            result = self._detector.detect(frame)
            self._det_errors = 0
        except Exception as exc:  # noqa: BLE001
            self._det_errors += 1
            log.error("detector error %d/%d: %r", self._det_errors, self._max_det_errors, exc)
            state = self.safety.update(None, now)
            self._reset_if_unreliable(state)
            if state is not TrackingState.RELIABLE:
                self._gestures.reset()
                self._mouse.release_all()
            if self._det_errors >= self._max_det_errors:
                self._fatal("detector failure", exc)
                return StepReport(StepOutcome.DETECTOR_FAILURE, state, frame)
            return StepReport(StepOutcome.DETECTOR_ERROR, state, frame)

        hand = result.primary_hand
        state = self.safety.update(hand, now)
        if state is not TrackingState.RELIABLE:
            self._smoother.reset()
            self._gestures.reset()
            self._mouse.release_all()
            return StepReport(StepOutcome.UNRELIABLE, state, frame, result)
        if hand is None:
            self._gestures.reset()
            self._mouse.release_all()
            return StepReport(StepOutcome.NO_HAND, state, frame, result)

        # 1. Update gestures
        gesture_res = self._gestures.update(hand, now)

        # 2. Map coordinates and move cursor (only if interaction state allows it!)
        tip = hand.point(LandmarkId.INDEX_TIP)
        raw = self._mapper.map(tip.x, tip.y)
        sx, sy = self._smoother(raw.x, raw.y, frame.timestamp_ms / 1000.0)
        target = self._clamp(sx, sy)

        moved = False
        if gesture_res.cursor_movement_allowed:
            moved = self._mouse.move_to(*target)

        # 3. Execute gesture mouse action if any
        action = gesture_res.action
        if action.action_type == MouseActionType.LEFT_DOWN:
            self._mouse.left_down()
        elif action.action_type == MouseActionType.LEFT_UP:
            self._mouse.left_up()
        elif action.action_type == MouseActionType.LEFT_CLICK:
            self._mouse.left_down()
            self._mouse.left_up()
        elif action.action_type == MouseActionType.DOUBLE_CLICK:
            self._mouse.left_down()
            self._mouse.left_up()
            self._mouse.left_down()
            self._mouse.left_up()
        elif action.action_type == MouseActionType.RIGHT_CLICK:
            self._mouse.right_click()
        elif action.action_type == MouseActionType.SCROLL:
            if action.scroll_amount != 0:
                self._mouse.scroll_wheel(action.scroll_amount)

        return StepReport(
            StepOutcome.MOVED if moved else StepOutcome.BLOCKED,
            state,
            frame,
            result,
            target,
            gesture=gesture_res,
        )

    def run(self, on_step: Callable[[StepReport], bool | None] | None = None, step_timeout: float = 0.5) -> None:
        """open(), loop step() until request_stop(), a fatal outcome, or `on_step` returns True; always close()."""
        self.open()
        try:
            while not self._stop.is_set():
                report = self.step(step_timeout)
                if report.outcome in FATAL_OUTCOMES:
                    break
                if on_step is not None and on_step(report):
                    break
        finally:
            self.close()

    # -- helpers --------------------------------------------------------------------------
    def _reset_if_unreliable(self, state: TrackingState) -> None:
        if state is not TrackingState.RELIABLE:
            self._smoother.reset()

    def _clamp(self, x: float, y: float) -> tuple[int, int]:
        w, h = self._mapper.screen_size
        g = self._guard
        return (min(max(int(round(x)), g), w - 1 - g), min(max(int(round(y)), g), h - 1 - g))

    def _fatal(self, reason: str, exc: BaseException) -> None:
        self.last_error = f"{reason}: {exc}"
        log.error("%s", self.last_error)
        self._smoother.reset()
        self.safety.emergency_stop(self.last_error)


def build_pipeline(config: AppConfig, backend: MouseBackend | None = None) -> Pipeline:
    """Wire the real components. Nothing is opened until `open()`/`run()`. Control starts DISABLED."""
    backend = backend or PyAutoGUIBackend()
    width, height = backend.screen_size()
    safety = SafetyController(config.safety)
    return Pipeline(
        camera=Camera(config.camera),
        detector=HandDetector(config.detector),
        safety=safety,
        mapper=CoordinateMapper(config.mapping, width, height),
        smoother=PointFilter(config.smoothing),
        mouse=MouseController(backend, safety),
        gestures=GestureRecognizer(config.gestures),
        corner_guard_px=config.mapping.corner_guard_px,
        max_detector_errors=config.safety.max_consecutive_detector_errors,
    )
