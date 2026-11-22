"""Static API-surface check: confirms the installed MediaPipe still exposes what hand_detector.py uses.
Does NOT load a model or touch a camera."""
import pytest

mp = pytest.importorskip("mediapipe")


def test_tasks_hand_landmarker_surface():
    vision = mp.tasks.vision
    for name in ("HandLandmarker", "HandLandmarkerOptions", "RunningMode"):
        assert hasattr(vision, name), name
    assert hasattr(vision.RunningMode, "VIDEO")
    for method in ("create_from_options", "detect_for_video", "close"):
        assert hasattr(vision.HandLandmarker, method), method
    opts = vision.HandLandmarkerOptions(
        base_options=mp.tasks.BaseOptions(model_asset_path="unused.task"),
        running_mode=vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.5,
        min_hand_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    assert opts.num_hands == 1
    assert hasattr(mp, "Image") and hasattr(mp.ImageFormat, "SRGB")
