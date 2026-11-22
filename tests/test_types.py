import pytest

from virtual_mouse.types import HandObservation, Landmark, LandmarkId


def test_landmark_ids():
    assert LandmarkId.INDEX_TIP == 8 and LandmarkId.THUMB_TIP == 4 and LandmarkId.PINKY_TIP == 20


def test_hand_requires_21(make_hand):
    with pytest.raises(ValueError):
        HandObservation((Landmark(0, 0),) * 20)
    assert make_hand().point(LandmarkId.WRIST).x == 0.5
