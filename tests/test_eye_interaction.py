"""Deterministic automated tests for FaceDetector wrapper and EyeSubsystem blink dynamics.

Tests cover:
- Model download asset checks
- MediaPipe FaceDetector initialization / missing model error
- Eye Aspect Ratio (EAR) computation from landmarks
- Blendshape blink weight processing
- Intentional vs natural blink discrimination (min / max duration filtering)
- Double blink sequence recognition (downward scroll)
- Triple blink sequence recognition (upward scroll)
- Incomplete sequence timeout
- Cooldown lockout and duplicate action prevention
- Clean lifecycle release when mode switches
"""
import time
import pytest
from pathlib import Path

from virtual_mouse.detection.face_detector import FaceDetector
from virtual_mouse.detection.model_assets import ModelError, ensure_face_model
from virtual_mouse.events import EventType, ModalityType
from virtual_mouse.eye.subsystem import EyeCalibration, EyeSubsystem, FaceObservation


def test_face_detector_missing_model_raises():
    detector = FaceDetector(model_path="models/nonexistent_face_landmarker.task")
    with pytest.raises(ModelError):
        detector.open()
    assert detector.is_open is False


def test_ensure_face_model_atomic_download(tmp_path):
    dest = tmp_path / "models" / "face_landmarker.task"
    called = []

    def mock_downloader(url, path):
        called.append((url, path))
        path.write_bytes(b"face_model_content_sample")

    path = ensure_face_model(dest, downloader=mock_downloader)
    assert path.is_file()
    assert path.read_bytes() == b"face_model_content_sample"
    assert len(called) == 1

    # Second call should not redownload
    ensure_face_model(dest, downloader=mock_downloader)
    assert len(called) == 1


def test_eye_metrics_from_blendshapes():
    sub = EyeSubsystem()
    face_closed = FaceObservation(blendshapes={"eyeBlinkLeft": 0.85, "eyeBlinkRight": 0.80})
    left_b, right_b, ear = sub.compute_blink_metrics(face_closed)
    assert left_b == 0.85
    assert right_b == 0.80
    assert ear < sub.calib.blink_ear_threshold


def test_eye_metrics_from_468_landmarks():
    sub = EyeSubsystem()
    # Construct 478 mock face landmark points
    lms = [(0.5, 0.5, 0.0)] * 478
    # Left Eye (362, 385, 387, 263, 373, 380)
    lms[362] = (0.4, 0.5, 0.0)
    lms[263] = (0.6, 0.5, 0.0)  # width = 0.2
    lms[385] = (0.5, 0.48, 0.0)
    lms[380] = (0.5, 0.52, 0.0)  # height = 0.04
    lms[387] = (0.5, 0.48, 0.0)
    lms[373] = (0.5, 0.52, 0.0)

    # Right Eye (33, 160, 158, 133, 153, 144)
    lms[33] = (0.2, 0.5, 0.0)
    lms[133] = (0.4, 0.5, 0.0)  # width = 0.2
    lms[160] = (0.3, 0.48, 0.0)
    lms[144] = (0.3, 0.52, 0.0)
    lms[158] = (0.3, 0.48, 0.0)
    lms[153] = (0.3, 0.52, 0.0)

    face = FaceObservation(landmarks=tuple(lms))
    _, _, ear = sub.compute_blink_metrics(face)
    assert ear > 0.15


def test_natural_single_blink_rejected():
    """An involuntary single blink must NOT trigger any scroll action."""
    sub = EyeSubsystem()
    sub.enable()
    t = 1.0

    face_closed = FaceObservation(blendshapes={"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9})
    face_open = FaceObservation(blendshapes={"eyeBlinkLeft": 0.0, "eyeBlinkRight": 0.0})

    # Blink onset
    sub.process(face_closed, t)
    # Blink release after 150ms
    t += 0.15
    events = sub.process(face_open, t)
    assert len(events) == 0

    # Advance past sequence window (0.90s later, since sequence_window_s is 0.85s)
    t += 0.90
    events_after = sub.process(face_open, t)
    assert len(events_after) == 0
    assert "Single natural blink ignored" in sub.telemetry.rejection_reason


def test_micro_flutter_and_prolonged_closure_rejected():
    sub = EyeSubsystem()
    sub.enable()
    t = 1.0
    face_closed = FaceObservation(blendshapes={"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9})
    face_open = FaceObservation(blendshapes={"eyeBlinkLeft": 0.0, "eyeBlinkRight": 0.0})

    # 1. Micro-flutter (30ms < 50ms min)
    sub.process(face_closed, t)
    t += 0.03
    sub.process(face_open, t)
    assert "Micro-blink rejected" in sub.telemetry.rejection_reason

    # 2. Prolonged closure (600ms > 450ms max)
    t += 0.2
    sub.process(face_closed, t)
    t += 0.60
    sub.process(face_open, t)
    assert "Prolonged closure rejected" in sub.telemetry.rejection_reason


def test_double_blink_scroll_down():
    """Two intentional blinks inside sequence window triggers exactly one scroll down."""
    sub = EyeSubsystem()
    sub.enable()
    t = 1.0
    face_closed = FaceObservation(blendshapes={"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9})
    face_open = FaceObservation(blendshapes={"eyeBlinkLeft": 0.0, "eyeBlinkRight": 0.0})

    # Blink 1 (duration: 140ms)
    sub.process(face_closed, t)
    t += 0.14
    sub.process(face_open, t)

    # Blink 2 (duration: 140ms, 180ms after blink 1)
    t += 0.18
    sub.process(face_closed, t)
    t += 0.14
    sub.process(face_open, t)

    # Allow sequence window (0.85s from first blink) to finalize double-blink
    t += 0.60
    events = sub.process(face_open, t)

    assert len(events) == 1
    assert events[0].event_type == EventType.DOUBLE_BLINK
    assert events[0].data["action"] == "scroll_down"
    assert events[0].data["amount"] == -3
    assert "DOUBLE_BLINK" in sub.telemetry.last_action


def test_triple_blink_scroll_up():
    """Three intentional blinks trigger immediate scroll up."""
    sub = EyeSubsystem()
    sub.enable()
    t = 1.0
    face_closed = FaceObservation(blendshapes={"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9})
    face_open = FaceObservation(blendshapes={"eyeBlinkLeft": 0.0, "eyeBlinkRight": 0.0})

    # Blink 1
    sub.process(face_closed, t)
    t += 0.12
    sub.process(face_open, t)

    # Blink 2
    t += 0.10
    sub.process(face_closed, t)
    t += 0.12
    sub.process(face_open, t)

    # Blink 3
    t += 0.10
    sub.process(face_closed, t)
    t += 0.12
    events = sub.process(face_open, t)

    assert len(events) == 1
    assert events[0].event_type == EventType.TRIPLE_BLINK
    assert events[0].data["action"] == "scroll_up"
    assert events[0].data["amount"] == 3
    assert "TRIPLE_BLINK" in sub.telemetry.last_action


def test_cooldown_prevents_duplicate_actions():
    """Blinks occurring during cooldown lockout must be rejected."""
    sub = EyeSubsystem()
    sub.enable()
    t = 1.0
    face_closed = FaceObservation(blendshapes={"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9})
    face_open = FaceObservation(blendshapes={"eyeBlinkLeft": 0.0, "eyeBlinkRight": 0.0})

    # Trigger triple blink
    for _ in range(3):
        sub.process(face_closed, t)
        t += 0.12
        sub.process(face_open, t)
        t += 0.08

    # Attempt another blink during cooldown (cooldown is 0.60s)
    t += 0.10
    sub.process(face_closed, t)
    t += 0.12
    sub.process(face_open, t)
    assert "In cooldown window" in sub.telemetry.rejection_reason


def test_synthetic_open_closing_closed_landmark_sequence():
    """Validates deterministic synthetic open, closing, and closed face landmarks with EAR and blendshapes."""
    sub = EyeSubsystem()
    sub.enable()

    def make_face_observation(ear_val: float, blend_score: float) -> FaceObservation:
        lms = [(0.5, 0.5, 0.0)] * 478
        # Left eye horizontal: dist(362, 263) = 0.20
        lms[362] = (0.4, 0.5, 0.0)
        lms[263] = (0.6, 0.5, 0.0)
        # Left eye vertical: dist = 0.20 * ear_val
        lms[385] = (0.5, 0.5 - (0.10 * ear_val), 0.0)
        lms[380] = (0.5, 0.5 + (0.10 * ear_val), 0.0)
        lms[387] = (0.5, 0.5 - (0.10 * ear_val), 0.0)
        lms[373] = (0.5, 0.5 + (0.10 * ear_val), 0.0)

        # Right eye horizontal: dist(33, 133) = 0.20
        lms[33] = (0.2, 0.5, 0.0)
        lms[133] = (0.4, 0.5, 0.0)
        lms[160] = (0.3, 0.5 - (0.10 * ear_val), 0.0)
        lms[144] = (0.3, 0.5 + (0.10 * ear_val), 0.0)
        lms[158] = (0.3, 0.5 - (0.10 * ear_val), 0.0)
        lms[153] = (0.3, 0.5 + (0.10 * ear_val), 0.0)

        return FaceObservation(
            landmarks=tuple(lms),
            blendshapes={"eyeBlinkLeft": blend_score, "eyeBlinkRight": blend_score},
        )

    # 1. Open eyes (EAR ~ 0.30, blend ~ 0.15)
    f_open = make_face_observation(0.30, 0.15)
    l_b, r_b, ear = sub.compute_blink_metrics(f_open)
    assert ear > 0.25
    assert l_b == 0.15

    # 2. Closing eyes (EAR ~ 0.22, blend ~ 0.35)
    f_closing = make_face_observation(0.22, 0.35)
    l_b, r_b, ear = sub.compute_blink_metrics(f_closing)
    assert 0.20 < ear < 0.25

    # 3. Fully closed eyes (EAR ~ 0.10, blend ~ 0.85)
    f_closed = make_face_observation(0.10, 0.85)
    l_b, r_b, ear = sub.compute_blink_metrics(f_closed)
    assert ear < 0.15
    assert l_b == 0.85

    # Simulate double-blink with realistic synthetic landmarks
    t = 1.0
    sub.process(f_open, t)

    # Blink 1 (onset, held 120ms, release)
    t += 0.033
    sub.process(f_closed, t)
    t += 0.120
    sub.process(f_open, t)
    assert sub.telemetry.sequence_count == 1

    # Pause between blinks (250ms)
    t += 0.250
    sub.process(f_open, t)

    # Blink 2 (onset, held 120ms, release)
    t += 0.033
    sub.process(f_closed, t)
    t += 0.120
    sub.process(f_open, t)
    assert sub.telemetry.sequence_count == 2

    # Sequence window expiry finalizes double-blink
    t += 0.90
    events = sub.process(f_open, t)
    assert len(events) == 1
    assert events[0].event_type == EventType.DOUBLE_BLINK
    assert events[0].data["action"] == "scroll_down"

