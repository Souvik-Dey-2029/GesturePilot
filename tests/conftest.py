import numpy as np
import pytest

from virtual_mouse.types import NUM_LANDMARKS, HandObservation, Landmark


@pytest.fixture
def make_hand():
    def _make(score: float = 0.9, x: float = 0.5, y: float = 0.5) -> HandObservation:
        return HandObservation(tuple(Landmark(x, y, 0.0) for _ in range(NUM_LANDMARKS)), "Right", score)

    return _make


@pytest.fixture
def blank_frame():
    return np.zeros((48, 64, 3), dtype=np.uint8)
