"""Integration tests for RuntimeController, modality mode switching, and honest availability checking."""
import pytest
from pathlib import Path
from virtual_mouse.controller import ModalityAvailability, RuntimeController
from virtual_mouse.events import SystemInteractionMode
from virtual_mouse.mouse.backend import FakeMouseBackend
from virtual_mouse.mouse.controller import MouseController
from virtual_mouse.pipeline import Pipeline
from virtual_mouse.safety import SafetyConfig, SafetyController


class DummyDetector:
    def open(self): pass
    def close(self): pass
    def detect(self, f): return None


class DummyCamera:
    def start(self): pass
    def stop(self): pass
    def read(self, timeout=0.5): return None


class DummyMapper:
    screen_size = (1920, 1080)
    def map(self, x, y):
        class Pt:
            x, y = 100, 100
        return Pt()


class DummySmoother:
    def __call__(self, x, y, t): return (x, y)
    def reset(self): pass


class DummyGestures:
    def reset(self): pass
    def update(self, h, t):
        class Res:
            cursor_movement_allowed = True
            action = type("Action", (), {"action_type": type("T", (), {"name": "NONE"})()})()
            active_gesture = type("G", (), {"value": "none"})()
            interaction_state = type("S", (), {"value": "POINTER"})()
            metrics = type("M", (), {"pinch_dist": 0.0, "recognized_pose": type("P", (), {"value": "POINTER"})()})()
        return Res()


class DummyFaceDetector:
    def __init__(self, model_path):
        self.model_path = model_path
        self.is_open = False
    def open(self):
        self.is_open = True
    def close(self):
        self.is_open = False
    def detect(self, f):
        return None


def make_test_runtime(tmp_path: Path, mock_face_detector=False) -> tuple[RuntimeController, FakeMouseBackend, SafetyController]:
    backend = FakeMouseBackend()
    safety = SafetyController(SafetyConfig())
    mouse = MouseController(backend, safety)
    pipeline = Pipeline(
        camera=DummyCamera(),
        detector=DummyDetector(),
        safety=safety,
        mapper=DummyMapper(),
        smoother=DummySmoother(),
        mouse=mouse,
        gestures=DummyGestures(),
    )
    face_model_mock = tmp_path / "face_landmarker.task"
    detector = DummyFaceDetector(face_model_mock) if mock_face_detector else None
    runtime = RuntimeController(pipeline, face_model_path=face_model_mock, face_detector=detector)
    return runtime, backend, safety


def test_runtime_starts_disarmed(tmp_path):
    runtime, _, safety = make_test_runtime(tmp_path)
    assert runtime.master_armed is False
    assert safety.enabled is False
    assert runtime.mode == SystemInteractionMode.HAND_ONLY


def test_runtime_arm_and_disarm(tmp_path):
    runtime, _, safety = make_test_runtime(tmp_path)
    # Arming
    armed = runtime.arm()
    assert armed is True
    assert runtime.master_armed is True
    assert safety.enabled is True

    # Disarming
    runtime.disarm()
    assert runtime.master_armed is False
    assert safety.enabled is False


def test_hand_mode_always_available(tmp_path):
    runtime, _, _ = make_test_runtime(tmp_path)
    assert runtime.check_hand_availability() == ModalityAvailability.AVAILABLE
    res = runtime.select_hand_mode()
    assert res is True
    assert runtime.mode == SystemInteractionMode.HAND_ONLY


def test_eye_mode_reports_honest_unavailable_when_model_missing(tmp_path, monkeypatch):
    runtime, _, _ = make_test_runtime(tmp_path)
    # Mock face model is not created on disk
    assert runtime.check_eye_availability() == ModalityAvailability.UNAVAILABLE_MODEL_MISSING

    # If download fails, it reports download failed and remains in Hand mode
    from virtual_mouse import controller
    def fail_download(*args, **kwargs):
        raise RuntimeError("network unreachable")
    monkeypatch.setattr(controller, "ensure_face_model", fail_download)

    # Attempt to switch to Eye mode
    switched = runtime.select_eye_mode()
    assert switched is False
    # Remains in previous mode
    assert runtime.mode == SystemInteractionMode.HAND_ONLY
    assert "download failed" in runtime.last_message


def test_eye_mode_attempts_and_succeeds_on_demand_download(tmp_path, monkeypatch):
    runtime, _, _ = make_test_runtime(tmp_path, mock_face_detector=True)
    fake_model = tmp_path / "face_landmarker.task"
    assert not fake_model.exists()

    from virtual_mouse import controller
    def mock_download(path, **kwargs):
        fake_model.write_bytes(b"downloaded_mock_model")
        return fake_model
    monkeypatch.setattr(controller, "ensure_face_model", mock_download)

    switched = runtime.select_eye_mode()
    assert switched is True
    assert runtime.mode == SystemInteractionMode.EYE_ONLY
    assert fake_model.is_file()


def test_eye_mode_available_when_model_present(tmp_path):
    runtime, _, _ = make_test_runtime(tmp_path, mock_face_detector=True)
    # Create fake face model file
    fake_model = tmp_path / "face_landmarker.task"
    fake_model.write_bytes(b"mock_model")

    assert runtime.check_eye_availability() == ModalityAvailability.AVAILABLE
    switched = runtime.select_eye_mode()
    assert switched is True
    assert runtime.mode == SystemInteractionMode.EYE_ONLY


def test_voice_mode_reports_honest_unavailable_without_asr(tmp_path, monkeypatch):
    runtime, _, _ = make_test_runtime(tmp_path)
    # Simulate missing ASR dependency
    monkeypatch.setattr(runtime, "check_voice_availability", lambda: ModalityAvailability.UNAVAILABLE_NO_ASR_ENGINE)
    assert runtime.check_voice_availability() == ModalityAvailability.UNAVAILABLE_NO_ASR_ENGINE
    toggled = runtime.toggle_voice_mode()
    assert toggled is False
    assert "VOICE unavailable" in runtime.last_message


def test_all_mode_checks_all_modalities(tmp_path):
    runtime, _, _ = make_test_runtime(tmp_path)
    switched = runtime.select_all_mode()
    assert switched is False
    assert runtime.mode == SystemInteractionMode.HAND_ONLY
    assert "ALL mode unavailable" in runtime.last_message


def test_emergency_stop_overrides_master_arm_immediately(tmp_path):
    runtime, backend, safety = make_test_runtime(tmp_path)
    runtime.arm()
    assert runtime.master_armed is True

    # Press Space or X -> Emergency stop
    runtime.emergency_stop("keyboard")
    assert runtime.master_armed is False
    assert safety.enabled is False
    assert safety.estop.is_set is True

    # Arming must be rejected while estop is latched
    armed_again = runtime.arm()
    assert armed_again is False
    assert runtime.master_armed is False

    # Safe recovery procedure ('r')
    runtime.recover()
    assert safety.estop.is_set is False
    assert runtime.master_armed is False  # Must stay DISARMED until explicit 'm'
    assert "DISARMED" in runtime.last_message


def test_key_handling_dispatch(tmp_path):
    runtime, _, _ = make_test_runtime(tmp_path)
    # Diagnostic toggle
    assert runtime.diagnostic_mode is False
    runtime.handle_key(ord("d"))
    assert runtime.diagnostic_mode is True

    # Master arm toggle
    runtime.handle_key(ord("m"))
    assert runtime.master_armed is True

    # Quit key
    quit_req = runtime.handle_key(ord("q"))
    assert quit_req is True
