from types import SimpleNamespace as NS

import numpy as np
import pytest

from virtual_mouse.config import DetectorConfig
from virtual_mouse.detection.hand_detector import HandDetector, convert_result
from virtual_mouse.detection.model_assets import ModelError
from virtual_mouse.types import CapturedFrame


def fake_result(n_hands=1, n_landmarks=21, label="Left", score=0.93):
    lms = [[NS(x=0.1 * i % 1, y=0.2, z=-0.01) for i in range(n_landmarks)] for _ in range(n_hands)]
    hd = [[NS(category_name=label, score=score)] for _ in range(n_hands)]
    return NS(hand_landmarks=lms, handedness=hd)


def test_convert_basic():
    r = convert_result(fake_result(), 123, 7)
    assert r.timestamp_ms == 123 and r.frame_index == 7 and len(r.hands) == 1
    assert r.primary_hand.handedness == "Left" and r.primary_hand.score == pytest.approx(0.93)
    assert len(r.primary_hand.landmarks) == 21


def test_convert_empty_and_malformed():
    assert convert_result(NS(hand_landmarks=[], handedness=[]), 1, 1).primary_hand is None
    assert convert_result(fake_result(n_landmarks=5), 1, 1).hands == ()
    r = convert_result(NS(hand_landmarks=fake_result().hand_landmarks, handedness=[]), 1, 1)
    assert r.primary_hand.handedness == "Unknown" and r.primary_hand.score == 0.0


class FakeLandmarker:
    def __init__(self):
        self.timestamps, self.closed = [], False

    def detect_for_video(self, image, ts):
        self.timestamps.append(ts)
        assert image.flags["C_CONTIGUOUS"] and image.shape[2] == 3
        return fake_result()

    def close(self):
        self.closed = True


def frame(ts, idx=1):
    img = np.zeros((6, 8, 3), np.uint8)
    img[..., 0] = 255  # blue in BGR
    return CapturedFrame(img, ts, idx)


def test_detect_forces_strictly_increasing_timestamps_and_converts_to_rgb():
    lm = FakeLandmarker()
    seen = []
    det = HandDetector(DetectorConfig(), landmarker=lm, image_factory=lambda rgb: (seen.append(rgb), rgb)[1])
    det.detect(frame(100))
    det.detect(frame(100))
    det.detect(frame(90))
    assert lm.timestamps == [100, 101, 102]
    assert seen[0][0, 0].tolist() == [0, 0, 255]  # BGR blue -> RGB blue
    det.close()
    assert lm.closed


def test_detect_before_open_raises():
    with pytest.raises(RuntimeError):
        HandDetector(DetectorConfig()).detect(frame(1))


def test_open_missing_model_raises(tmp_path):
    with pytest.raises(ModelError):
        HandDetector(DetectorConfig(model_path=str(tmp_path / "missing.task"))).open()
