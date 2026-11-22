import threading
from collections import deque

import numpy as np
import pytest

from virtual_mouse.capture.camera import CameraError
from virtual_mouse.config import AppConfig, MappingConfig, SafetyConfig, SmoothingConfig
from virtual_mouse.mapping.coordinates import CoordinateMapper
from virtual_mouse.mapping.smoothing import PointFilter
from virtual_mouse.mouse.backend import FakeMouseBackend, MouseBackendError
from virtual_mouse.mouse.controller import MouseController
from virtual_mouse.pipeline import FATAL_OUTCOMES, Pipeline, StepOutcome, build_pipeline
from virtual_mouse.safety import SafetyController, TrackingState
from virtual_mouse.types import CapturedFrame, FrameResult, Landmark, LandmarkId, HandObservation, NUM_LANDMARKS

DT = 1 / 30


def hand_at(x, y, score=0.9):
    return HandObservation(tuple(Landmark(x, y, 0.0) for _ in range(NUM_LANDMARKS)), "Right", score)


class FakeCamera:
    def __init__(self):
        self.queue, self.started, self.stopped, self.read_exc, self.start_exc = deque(), False, 0, None, None

    def start(self):
        if self.start_exc:
            raise self.start_exc
        self.started = True

    def stop(self):
        self.stopped += 1

    def read(self, timeout=0.5):
        if self.read_exc:
            raise self.read_exc
        return self.queue.popleft() if self.queue else None


class FakeDetector:
    def __init__(self):
        self.next, self.opened, self.closed = None, False, 0

    def open(self):
        self.opened = True

    def close(self):
        self.closed += 1

    def detect(self, frame):
        if isinstance(self.next, Exception):
            raise self.next
        hands = (self.next,) if self.next is not None else ()
        return FrameResult(frame.timestamp_ms, frame.index, hands)


class Rig:
    def __init__(self, smoothing=False, mapping=None, safety_cfg=None, enable=True):
        self.clock_t = 0.0
        self.idx = 0
        self.camera, self.detector, self.backend = FakeCamera(), FakeDetector(), FakeMouseBackend(1920, 1080)
        self.mapping = mapping or MappingConfig(margin_bottom=0.15)
        self.safety = SafetyController(safety_cfg or SafetyConfig())
        self.mapper = CoordinateMapper(self.mapping, 1920, 1080)
        self.mouse = MouseController(self.backend, self.safety)
        self.pipe = Pipeline(
            self.camera, self.detector, self.safety, self.mapper,
            PointFilter(SmoothingConfig(enabled=smoothing)), self.mouse,
            corner_guard_px=self.mapping.corner_guard_px, clock=lambda: self.clock_t,
        )
        if enable:
            self.safety.enable()

    def tick(self, hand):
        """One 30 fps frame containing `hand` (or no hand)."""
        self.clock_t += DT
        self.idx += 1
        self.camera.queue.append(CapturedFrame(np.zeros((4, 4, 3), np.uint8), int(self.clock_t * 1000), self.idx))
        self.detector.next = hand
        return self.pipe.step()

    def idle(self):
        """One 30 fps interval in which the camera delivers no frame."""
        self.clock_t += DT
        return self.pipe.step()

    def moves(self):
        return [a for n, a in self.backend.events if n == "move_to"]


def test_cursor_mapping_exact_with_hand_calculated_values():
    r = Rig()
    for _ in range(2):
        r.tick(hand_at(0.3, 0.3))  # acquiring
    rep = r.tick(hand_at(0.3, 0.3))
    # u=(0.3-0.15)/0.7 -> mirrored 0.78571*1919=1507.7->1508 ; v=0.15/0.7*1079=231.2->231
    assert rep.outcome is StepOutcome.MOVED and rep.target == (1508, 231)
    assert r.moves() == [(1508, 231)]


def test_no_events_while_acquiring_then_moves():
    r = Rig()
    outcomes = [r.tick(hand_at(0.5, 0.5)).outcome for _ in range(4)]
    assert outcomes[:2] == [StepOutcome.UNRELIABLE] * 2 and outcomes[2:] == [StepOutcome.MOVED] * 2
    assert len(r.moves()) == 2


def test_disabled_state_emits_nothing():
    r = Rig(enable=False)
    outcomes = [r.tick(hand_at(0.5, 0.5)).outcome for _ in range(10)]
    assert StepOutcome.MOVED not in outcomes and r.backend.events == []
    assert r.safety.monitor.state is TrackingState.RELIABLE  # tracking runs, output is gated
    assert outcomes[-1] is StepOutcome.BLOCKED


def test_smoothing_integration_reduces_jitter_and_first_sample_is_raw():
    raw_r, sm_r = Rig(smoothing=False), Rig(smoothing=True)
    seq = [0.5 + (0.01 if i % 2 else -0.01) for i in range(90)]
    for x in seq:
        raw_r.tick(hand_at(x, 0.5))
        sm_r.tick(hand_at(x, 0.5))
    assert raw_r.moves()[0] == sm_r.moves()[0]
    spread = lambda m: max(p[0] for p in m[20:]) - min(p[0] for p in m[20:])  # noqa: E731
    assert spread(sm_r.moves()) < spread(raw_r.moves()) * 0.6


def test_corner_guard_keeps_cursor_off_failsafe_corners():
    r = Rig()
    for _ in range(3):
        rep = r.tick(hand_at(-0.5, -0.5))
    assert rep.target == (1918, 1)  # mirrored x, top edge; never (0,0)/(w-1,0)
    for _ in range(3):
        rep = r.tick(hand_at(1.5, 1.5))
    assert rep.target == (1, 1078)


def test_corner_guard_can_be_disabled():
    r = Rig(mapping=MappingConfig(margin_bottom=0.15, corner_guard_px=0))
    for _ in range(3):
        rep = r.tick(hand_at(1.5, -0.5))
    assert rep.target == (0, 0)


def test_emergency_stop_mid_run_stops_events():
    r = Rig()
    for _ in range(5):
        r.tick(hand_at(0.5, 0.5))
    n = len(r.moves())
    r.safety.emergency_stop("test")
    outcomes = [r.tick(hand_at(0.5, 0.5)).outcome for _ in range(5)]
    assert set(outcomes) == {StepOutcome.BLOCKED} and len(r.moves()) == n


def test_tracking_loss_resets_smoothing_and_recovery_restarts_from_raw_position():
    r = Rig(smoothing=True)
    for _ in range(10):
        r.tick(hand_at(0.3, 0.3))
    before = len(r.moves())
    # hand disappears for 0.4 s > 0.25 s timeout
    outcomes = [r.tick(None).outcome for _ in range(12)]
    assert r.safety.monitor.state is TrackingState.LOST
    assert len(r.moves()) == before and StepOutcome.MOVED not in outcomes
    # hand returns elsewhere: needs 3 good frames, then the first emitted point must be the RAW mapped point (no glide)
    reps = [r.tick(hand_at(0.6, 0.6)) for _ in range(4)]
    assert [x.outcome for x in reps[:2]] == [StepOutcome.UNRELIABLE] * 2
    expected = r.mapper.map(0.6, 0.6)
    assert reps[2].outcome is StepOutcome.MOVED and reps[2].target == (round(expected.x), round(expected.y))


def test_short_dropout_is_tolerated_without_loss_or_events():
    r = Rig()
    for _ in range(5):
        r.tick(hand_at(0.5, 0.5))
    n = len(r.moves())
    rep = r.tick(None)
    assert rep.outcome is StepOutcome.NO_HAND and len(r.moves()) == n
    assert r.tick(hand_at(0.5, 0.5)).outcome is StepOutcome.MOVED


def test_camera_stall_still_triggers_lost_timeout():
    r = Rig()
    for _ in range(5):
        r.tick(hand_at(0.5, 0.5))
    for _ in range(12):
        rep = r.idle()
    assert rep.outcome is StepOutcome.NO_FRAME and rep.tracking is TrackingState.LOST


def test_low_quality_hand_never_moves_cursor():
    r = Rig()
    outcomes = [r.tick(hand_at(0.5, 0.5, score=0.2)).outcome for _ in range(10)]
    assert set(outcomes) == {StepOutcome.UNRELIABLE} and r.backend.events == []


def test_camera_failure_is_fatal_latches_estop_and_releases_buttons():
    r = Rig()
    for _ in range(4):
        r.tick(hand_at(0.5, 0.5))
    r.mouse.left_down()
    r.camera.read_exc = CameraError("unplugged")
    rep = r.pipe.step()
    assert rep.outcome is StepOutcome.CAMERA_FAILURE and rep.outcome in FATAL_OUTCOMES
    assert r.safety.estop.is_set and not r.safety.can_emit() and not r.backend.left_held
    assert "unplugged" in r.pipe.last_error


def test_single_detector_error_tolerated_consecutive_errors_fatal():
    r = Rig()
    for _ in range(4):
        r.tick(hand_at(0.5, 0.5))
    r.detector.next = RuntimeError("inference")
    r.camera.queue.append(CapturedFrame(np.zeros((4, 4, 3), np.uint8), 99999, 99))
    assert r.pipe.step().outcome is StepOutcome.DETECTOR_ERROR and not r.safety.estop.is_set
    r.tick(hand_at(0.5, 0.5))  # success resets the counter
    outcomes = []
    for i in range(3):
        r.camera.queue.append(CapturedFrame(np.zeros((4, 4, 3), np.uint8), 100000 + i, 100 + i))
        r.detector.next = RuntimeError("inference")
        outcomes.append(r.pipe.step().outcome)
    assert outcomes == [StepOutcome.DETECTOR_ERROR, StepOutcome.DETECTOR_ERROR, StepOutcome.DETECTOR_FAILURE]
    assert r.safety.estop.is_set


def test_mouse_backend_failure_latches_estop_and_later_steps_are_blocked():
    r = Rig()
    r.backend.fail_on["move_to"] = MouseBackendError("os says no")
    outcomes = [r.tick(hand_at(0.5, 0.5)).outcome for _ in range(6)]
    assert StepOutcome.BLOCKED in outcomes and StepOutcome.MOVED not in outcomes
    assert r.safety.estop.is_set and "os says no" in r.safety.estop.reason
    r.backend.fail_on.clear()
    assert r.tick(hand_at(0.5, 0.5)).outcome is StepOutcome.BLOCKED and r.backend.events == []


def test_run_cleans_up_after_normal_stop():
    r = Rig()
    count = []

    def on_step(rep):
        count.append(rep)
        return len(count) >= 3

    r.pipe.run(on_step=on_step, step_timeout=0.01)
    assert r.detector.opened and r.camera.started
    assert r.camera.stopped == 1 and r.detector.closed == 1 and not r.safety.enabled


def test_run_cleans_up_when_callback_raises_and_releases_button():
    r = Rig()
    for _ in range(4):
        r.tick(hand_at(0.5, 0.5))
    r.mouse.left_down()

    def boom(rep):
        raise RuntimeError("ui crashed")

    with pytest.raises(RuntimeError):
        r.pipe.run(on_step=boom, step_timeout=0.01)
    assert r.camera.stopped == 1 and r.detector.closed == 1 and not r.backend.left_held and not r.safety.enabled


def test_run_stops_on_fatal_and_request_stop():
    r = Rig()
    r.camera.read_exc = CameraError("gone")
    r.pipe.run(step_timeout=0.01)  # returns by itself
    assert r.camera.stopped == 1 and r.detector.closed == 1
    r2 = Rig()
    timer = threading.Timer(0.1, r2.pipe.request_stop)
    timer.start()
    r2.pipe.run(step_timeout=0.01)  # returns only because request_stop() fires from another thread
    timer.join()
    assert r2.camera.stopped == 1 and r2.detector.closed == 1


def test_open_failure_closes_detector_and_close_is_idempotent():
    r = Rig()
    r.camera.start_exc = CameraError("no camera")
    with pytest.raises(CameraError):
        r.pipe.open()
    assert r.detector.closed == 1
    r.pipe.close()
    r.pipe.close()
    assert r.camera.stopped == 2


def test_cleanup_continues_even_if_a_step_fails():
    r = Rig()

    def bad():
        raise OSError("x")

    r.camera.stop = bad
    r.pipe.close()
    assert r.detector.closed == 1


def test_build_pipeline_wires_real_components_without_opening_hardware():
    backend = FakeMouseBackend(1366, 768)
    pipe = build_pipeline(AppConfig(), backend)
    assert pipe.safety.enabled is False and pipe._mapper.screen_size == (1366, 768)
    assert backend.events == []


def test_pipeline_gesture_integration_two_finger_click(make_hand):
    r = Rig()
    # Acquire reliable tracking
    for _ in range(3):
        r.tick(hand_at(0.5, 0.5))

    # Construct two-finger hand: Index and Middle extended, Ring and Pinky curled
    two_lms = [Landmark(0.5, 0.5, 0.0)] * NUM_LANDMARKS
    two_lms[LandmarkId.WRIST] = Landmark(0.5, 0.8, 0.0)
    two_lms[LandmarkId.MIDDLE_MCP] = Landmark(0.5, 0.5, 0.0)
    two_lms[LandmarkId.INDEX_TIP] = Landmark(0.45, 0.25, 0.0)
    two_lms[LandmarkId.INDEX_PIP] = Landmark(0.45, 0.5, 0.0)
    two_lms[LandmarkId.MIDDLE_TIP] = Landmark(0.52, 0.25, 0.0)
    two_lms[LandmarkId.MIDDLE_PIP] = Landmark(0.52, 0.5, 0.0)
    two_lms[LandmarkId.RING_TIP] = Landmark(0.6, 0.75, 0.0)
    two_lms[LandmarkId.RING_PIP] = Landmark(0.6, 0.65, 0.0)
    two_lms[LandmarkId.PINKY_TIP] = Landmark(0.7, 0.75, 0.0)
    two_lms[LandmarkId.PINKY_PIP] = Landmark(0.7, 0.65, 0.0)
    two_hand = HandObservation(tuple(two_lms), "Right", 0.95)

    # Tick stationary for > two_finger_click_window_s (0.22s) -> ~8 frames
    for _ in range(8):
        r.tick(two_hand)

    # Left click emitted!
    events = [n for n, _ in r.backend.events if n in ("left_down", "left_up")]
    assert events == ["left_down", "left_up"]
    assert not r.backend.left_held


def test_pipeline_gesture_tracking_loss_releases_held_button():
    r = Rig()
    for _ in range(3):
        r.tick(hand_at(0.5, 0.5))

    # Manually hold left button
    r.mouse.left_down()
    assert r.mouse.left_held and r.backend.left_held

    # Drop tracking for > lost_hand_timeout_s (0.25s -> ~9 frames)
    for _ in range(10):
        r.idle()

    # Must release left button!
    assert not r.mouse.left_held and not r.backend.left_held
