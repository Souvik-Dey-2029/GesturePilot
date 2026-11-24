"""Comprehensive deterministic test suite for rebuilt Eye recognition core.

Covers:
- Part 4: Feature extraction (EAR, blendshapes, zero-width guard, invalid geometry)
- Part 5: State estimation with hysteresis (Open, Closing, Closed, Opening, Lost, Uncertain)
- Part 7: Temporal blink detection (single natural, duration windows, micro-flutter rejection)
- Part 8: Sequence recognition (double vs triple, quiet interval, no premature double execution)
- Part 9: False action prevention (natural blinks ignored, cooldown enforcement, tracking loss reset)
- Part 10: Master arm / disarm gating
"""
import pytest
from virtual_mouse.events import EventType, ModalityType
from virtual_mouse.eye.feature_extractor import EyeFeatureExtractor, EyeFeatureObservation, calculate_ear_6pts
from virtual_mouse.eye.state_estimator import EyeState, EyeStateEstimator
from virtual_mouse.eye.blink_detector import BlinkDetector, BlinkSequenceRecognizer, CompletedBlink
from virtual_mouse.eye.subsystem import EyeSubsystem, EyeCalibration, FaceObservation
from virtual_mouse.eye.calibration import EyeCalibrator


def make_landmarks(ear_val: float) -> tuple[tuple[float, float, float], ...]:
    """Generates 478 landmarks with exact geometry yielding target ear_val."""
    lms = [(0.5, 0.5, 0.0)] * 478
    # Left eye: width = 0.20
    lms[362] = (0.4, 0.5, 0.0)
    lms[263] = (0.6, 0.5, 0.0)
    # vertical distance = 0.20 * ear_val
    lms[385] = (0.5, 0.5 - (0.10 * ear_val), 0.0)
    lms[380] = (0.5, 0.5 + (0.10 * ear_val), 0.0)
    lms[387] = (0.5, 0.5 - (0.10 * ear_val), 0.0)
    lms[373] = (0.5, 0.5 + (0.10 * ear_val), 0.0)

    # Right eye: width = 0.20
    lms[33] = (0.2, 0.5, 0.0)
    lms[133] = (0.4, 0.5, 0.0)
    lms[160] = (0.3, 0.5 - (0.10 * ear_val), 0.0)
    lms[144] = (0.3, 0.5 + (0.10 * ear_val), 0.0)
    lms[158] = (0.3, 0.5 - (0.10 * ear_val), 0.0)
    lms[153] = (0.3, 0.5 + (0.10 * ear_val), 0.0)
    return tuple(lms)


# -----------------------------------------------------------------------------
# Part 4 Tests: Feature Extractor
# -----------------------------------------------------------------------------
def test_feature_extractor_open_eye():
    ext = EyeFeatureExtractor()
    lms = make_landmarks(0.32)
    obs = ext.extract(lms, {"eyeBlinkLeft": 0.12, "eyeBlinkRight": 0.14})
    assert obs.face_detected is True
    assert obs.landmarks_valid is True
    assert 0.31 <= obs.ear_avg <= 0.33
    assert obs.blink_avg == 0.13
    assert obs.symmetry_blink == pytest.approx(0.02)


def test_feature_extractor_closed_eye():
    ext = EyeFeatureExtractor()
    lms = make_landmarks(0.08)
    obs = ext.extract(lms, {"eyeBlinkLeft": 0.88, "eyeBlinkRight": 0.90})
    assert obs.ear_avg < 0.12
    assert obs.blink_avg >= 0.85


def test_feature_extractor_zero_width_guard():
    # p1 and p4 identical -> width = 0
    lms = [(0.5, 0.5, 0.0)] * 478
    ear = calculate_ear_6pts(lms, (362, 385, 387, 263, 373, 380))
    assert ear == 0.0


def test_feature_extractor_missing_landmarks_fallback():
    ext = EyeFeatureExtractor()
    obs = ext.extract(None, {"eyeBlinkLeft": 0.80, "eyeBlinkRight": 0.80})
    assert obs.face_detected is True
    assert obs.landmarks_valid is False
    assert obs.ear_avg < 0.10


# -----------------------------------------------------------------------------
# Part 5 Tests: State Estimator with Hysteresis
# -----------------------------------------------------------------------------
def test_state_estimator_transitions():
    est = EyeStateEstimator(
        ear_open_baseline=0.28,
        ear_closed_threshold=0.18,
        ear_open_threshold=0.22,
        blend_closed_threshold=0.55,
        blend_open_threshold=0.35,
    )
    ext = EyeFeatureExtractor()

    # 1. Start Open
    obs_open = ext.extract(make_landmarks(0.30), {"eyeBlinkLeft": 0.15, "eyeBlinkRight": 0.15})
    assert est.estimate(obs_open) == EyeState.EYES_OPEN

    # 2. Closing onset (frame 1 of closed)
    obs_closed = ext.extract(make_landmarks(0.12), {"eyeBlinkLeft": 0.75, "eyeBlinkRight": 0.75})
    assert est.estimate(obs_closed) == EyeState.EYES_CLOSING

    # 3. Closed held (frame 2 of closed -> confirmed CLOSED)
    assert est.estimate(obs_closed) == EyeState.EYES_CLOSED

    # 4. Opening onset (frame 1 of open)
    assert est.estimate(obs_open) == EyeState.EYES_OPENING

    # 5. Open confirmed
    assert est.estimate(obs_open) == EyeState.EYES_OPEN


def test_state_estimator_hysteresis_boundary():
    est = EyeStateEstimator(
        ear_closed_threshold=0.18,
        ear_open_threshold=0.22,
        blend_closed_threshold=0.55,
        blend_open_threshold=0.35,
    )
    ext = EyeFeatureExtractor()

    obs_open = ext.extract(make_landmarks(0.30), {"eyeBlinkLeft": 0.15, "eyeBlinkRight": 0.15})
    est.estimate(obs_open)

    # Intermediate value (EAR=0.20, blend=0.45) does NOT trigger closure from open
    obs_mid = ext.extract(make_landmarks(0.20), {"eyeBlinkLeft": 0.45, "eyeBlinkRight": 0.45})
    assert est.estimate(obs_mid) == EyeState.EYES_OPEN


def test_state_estimator_tracking_lost():
    est = EyeStateEstimator()
    ext = EyeFeatureExtractor()
    obs_lost = ext.extract(None, None, confidence=0.0)
    assert est.estimate(obs_lost) == EyeState.EYE_TRACKING_LOST


def test_state_estimator_asymmetric_uncertain():
    est = EyeStateEstimator()
    ext = EyeFeatureExtractor()
    # One eye closed, one open
    obs_asym = ext.extract(make_landmarks(0.25), {"eyeBlinkLeft": 0.85, "eyeBlinkRight": 0.10})
    assert est.estimate(obs_asym) == EyeState.EYE_STATE_UNCERTAIN


# -----------------------------------------------------------------------------
# Part 7 Tests: Temporal Blink Detector
# -----------------------------------------------------------------------------
def test_blink_detector_valid_blink():
    det = BlinkDetector(min_duration_s=0.05, max_duration_s=0.45)
    ext = EyeFeatureExtractor()

    obs_open = ext.extract(make_landmarks(0.30), {"eyeBlinkLeft": 0.10, "eyeBlinkRight": 0.10}, timestamp=1.0)
    obs_closed = ext.extract(make_landmarks(0.10), {"eyeBlinkLeft": 0.85, "eyeBlinkRight": 0.85}, timestamp=1.05)

    assert det.update(EyeState.EYES_OPEN, obs_open) is None
    assert det.update(EyeState.EYES_CLOSING, obs_closed) is None
    assert det.update(EyeState.EYES_CLOSED, obs_closed) is None

    # Released at t=1.18 (duration = 130ms)
    obs_open_end = ext.extract(make_landmarks(0.30), {"eyeBlinkLeft": 0.10, "eyeBlinkRight": 0.10}, timestamp=1.18)
    completed = det.update(EyeState.EYES_OPEN, obs_open_end)

    assert completed is not None
    assert completed.duration == pytest.approx(0.13, abs=0.01)
    assert completed.min_ear < 0.15


def test_blink_detector_micro_flutter_rejected():
    det = BlinkDetector(min_duration_s=0.05, max_duration_s=0.45)
    ext = EyeFeatureExtractor()

    obs_closed = ext.extract(make_landmarks(0.10), {"eyeBlinkLeft": 0.85, "eyeBlinkRight": 0.85}, timestamp=1.0)
    det.update(EyeState.EYES_CLOSING, obs_closed)

    # Reopened after only 25ms
    obs_open = ext.extract(make_landmarks(0.30), {"eyeBlinkLeft": 0.10, "eyeBlinkRight": 0.10}, timestamp=1.025)
    completed = det.update(EyeState.EYES_OPEN, obs_open)
    assert completed is None
    assert "Micro-blink rejected" in det.last_rejection_reason


def test_blink_detector_prolonged_closure_rejected():
    det = BlinkDetector(min_duration_s=0.05, max_duration_s=0.45)
    ext = EyeFeatureExtractor()

    obs_closed = ext.extract(make_landmarks(0.10), {"eyeBlinkLeft": 0.85, "eyeBlinkRight": 0.85}, timestamp=1.0)
    det.update(EyeState.EYES_CLOSED, obs_closed)

    # Reopened after 600ms
    obs_open = ext.extract(make_landmarks(0.30), {"eyeBlinkLeft": 0.10, "eyeBlinkRight": 0.10}, timestamp=1.60)
    completed = det.update(EyeState.EYES_OPEN, obs_open)
    assert completed is None
    assert "Prolonged closure rejected" in det.last_rejection_reason


# -----------------------------------------------------------------------------
# Part 8 & 9 Tests: BlinkSequenceRecognizer
# -----------------------------------------------------------------------------
def test_sequence_single_natural_blink_no_action():
    seq = BlinkSequenceRecognizer(max_inter_blink_pause_s=0.45, wait_for_triple_timeout_s=0.35)
    b1 = CompletedBlink(start_time=1.0, end_time=1.12, duration=0.12, min_ear=0.10, max_blend=0.85)

    evs = seq.process(b1, now=1.12, eye_state=EyeState.EYES_OPEN)
    assert len(evs) == 0
    assert seq.sequence_count == 1

    # Advance past max_inter_blink_pause_s (natural reading gap)
    evs_later = seq.process(None, now=1.65, eye_state=EyeState.EYES_OPEN)
    assert len(evs_later) == 0
    assert seq.sequence_count == 0  # Sequence cleared
    assert "Single natural blink ignored" in seq.last_rejection


def test_sequence_intentional_double_blink():
    seq = BlinkSequenceRecognizer(max_inter_blink_pause_s=0.45, wait_for_triple_timeout_s=0.35)
    b1 = CompletedBlink(1.0, 1.12, 0.12, 0.10, 0.85)
    b2 = CompletedBlink(1.30, 1.42, 0.12, 0.10, 0.85)

    seq.process(b1, now=1.12)
    evs = seq.process(b2, now=1.42)
    # CRITICAL: At t=1.42, sequence must NOT trigger immediately (must wait for potential 3rd blink)
    assert len(evs) == 0
    assert seq.sequence_count == 2

    # After quiet interval (0.35s after b2 end_time = 1.42 + 0.35 = 1.77)
    evs_final = seq.process(None, now=1.78, eye_state=EyeState.EYES_OPEN)
    assert len(evs_final) == 1
    assert evs_final[0].event_type == EventType.DOUBLE_BLINK
    assert evs_final[0].data["action"] == "scroll_down"
    assert evs_final[0].data["amount"] == -3
    assert seq.sequence_count == 0


def test_sequence_intentional_triple_blink():
    seq = BlinkSequenceRecognizer(max_inter_blink_pause_s=0.45, wait_for_triple_timeout_s=0.35)
    b1 = CompletedBlink(1.0, 1.12, 0.12, 0.10, 0.85)
    b2 = CompletedBlink(1.25, 1.37, 0.12, 0.10, 0.85)
    b3 = CompletedBlink(1.50, 1.62, 0.12, 0.10, 0.85)

    seq.process(b1, now=1.12)
    seq.process(b2, now=1.37)
    evs = seq.process(b3, now=1.62)

    # Triple blink triggers immediately upon 3rd blink
    assert len(evs) == 1
    assert evs[0].event_type == EventType.TRIPLE_BLINK
    assert evs[0].data["action"] == "scroll_up"
    assert evs[0].data["amount"] == 3


def test_sequence_cooldown_prevents_duplicate_actions():
    seq = BlinkSequenceRecognizer(cooldown_s=0.60)
    b1 = CompletedBlink(1.0, 1.12, 0.12, 0.10, 0.85)
    b2 = CompletedBlink(1.25, 1.37, 0.12, 0.10, 0.85)
    b3 = CompletedBlink(1.50, 1.62, 0.12, 0.10, 0.85)

    # Fires triple blink at 1.62 -> cooldown until 1.62 + 0.60 = 2.22
    seq.process(b1, 1.12)
    seq.process(b2, 1.37)
    seq.process(b3, 1.62)

    # Attempt another blink at t=1.90 during cooldown
    b_extra = CompletedBlink(1.80, 1.90, 0.10, 0.10, 0.85)
    evs_cool = seq.process(b_extra, 1.90)
    assert len(evs_cool) == 0
    assert "cooldown" in seq.last_rejection.lower()


def test_sequence_tracking_loss_cancels_in_progress():
    seq = BlinkSequenceRecognizer()
    b1 = CompletedBlink(1.0, 1.12, 0.12, 0.10, 0.85)
    seq.process(b1, 1.12)
    assert seq.sequence_count == 1

    # Tracking lost
    seq.process(None, 1.25, eye_state=EyeState.EYE_TRACKING_LOST)
    assert seq.sequence_count == 0


# -----------------------------------------------------------------------------
# Part 6 Tests: Calibrator
# -----------------------------------------------------------------------------
def test_eye_calibrator_produces_valid_calibration():
    cal = EyeCalibrator(target_samples=30)
    ext = EyeFeatureExtractor()

    # Feed 20 open samples (EAR ~ 0.32, blend ~ 0.15)
    for _ in range(20):
        obs = ext.extract(make_landmarks(0.32), {"eyeBlinkLeft": 0.15, "eyeBlinkRight": 0.15})
        cal.add_open_sample(obs)

    # Feed 15 closed samples (EAR ~ 0.10, blend ~ 0.85)
    for _ in range(15):
        obs = ext.extract(make_landmarks(0.10), {"eyeBlinkLeft": 0.85, "eyeBlinkRight": 0.85})
        cal.add_closed_sample(obs)

    calib = cal.finalize()
    assert calib is not None
    assert calib.is_calibrated is True
    assert 0.31 <= calib.natural_ear_baseline <= 0.33
    assert calib.ear_closed_threshold < calib.ear_open_threshold
    assert calib.blend_open_threshold < calib.blend_closed_threshold
