import time

import numpy as np
import pytest

from virtual_mouse.capture.camera import Camera, CameraError
from virtual_mouse.config import CameraConfig


class FakeCap:
    def __init__(self, opened=True, frames=None, fail_after=None):
        self.opened, self.released, self.reads = opened, False, 0
        self.fail_after = fail_after

    def isOpened(self):
        return self.opened

    def read(self):
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            return False, None
        time.sleep(0.002)
        return True, np.full((4, 4, 3), self.reads % 255, dtype=np.uint8)

    def release(self):
        self.released = True


def test_open_failure_releases_and_raises():
    cap = FakeCap(opened=False)
    with pytest.raises(CameraError):
        Camera(CameraConfig(), lambda c: cap).start()
    assert cap.released


def test_frames_have_increasing_index_and_timestamp():
    cap = FakeCap()
    with Camera(CameraConfig(), lambda c: cap) as cam:
        a = cam.read(timeout=1.0)
        b = cam.read(timeout=1.0)
    assert a is not None and b is not None
    assert b.index > a.index and b.timestamp_ms > a.timestamp_ms
    assert cap.released


def test_read_times_out_returns_none_without_new_frame():
    cap = FakeCap(fail_after=3)
    cam = Camera(CameraConfig(max_read_failures=10_000), lambda c: cap)
    cam.start()
    try:
        while cam.read(timeout=0.05) is not None:
            pass
        assert cam.read(timeout=0.05) is None
    finally:
        cam.stop()


def test_persistent_failure_raises_error():
    cap = FakeCap(fail_after=2)
    cam = Camera(CameraConfig(max_read_failures=5), lambda c: cap)
    cam.start()
    try:
        with pytest.raises(CameraError):
            for _ in range(200):
                cam.read(timeout=0.1)
    finally:
        cam.stop()
    assert cap.released


def test_stop_idempotent_and_double_start_rejected():
    cap = FakeCap()
    cam = Camera(CameraConfig(), lambda c: cap)
    cam.start()
    with pytest.raises(CameraError):
        cam.start()
    cam.stop()
    cam.stop()
