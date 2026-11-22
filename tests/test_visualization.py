import numpy as np

from virtual_mouse.tools.visualization import HAND_CONNECTIONS, draw_hand
from virtual_mouse.types import HandObservation, Landmark


def test_connections_valid():
    assert len(HAND_CONNECTIONS) == 21
    assert all(0 <= a < 21 and 0 <= b < 21 for a, b in HAND_CONNECTIONS)


def test_draw_modifies_image():
    img = np.zeros((100, 100, 3), np.uint8)
    hand = HandObservation(tuple(Landmark(0.1 + 0.04 * i, 0.5) for i in range(21)))
    draw_hand(img, hand)
    assert img.any()
