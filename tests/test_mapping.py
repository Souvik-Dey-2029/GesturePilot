import pytest

from virtual_mouse.config import MappingConfig
from virtual_mouse.mapping.coordinates import CoordinateMapper


def mapper(**kw):
    return CoordinateMapper(MappingConfig(**kw), 1920, 1080)


def test_centre_maps_to_centre():
    # symmetric margins so the region centre is the image centre
    p = mapper(margin_bottom=0.15).map(0.5, 0.5)
    assert p.x == pytest.approx(959.5) and p.y == pytest.approx(539.5)


def test_mirror_flips_x():
    left = mapper(mirror_x=True).map(0.2, 0.5)
    right = mapper(mirror_x=False).map(0.2, 0.5)
    assert left.x > 960 > right.x


def test_clamped_outside_region():
    p = mapper().map(-1.0, 2.0)
    assert 0 <= p.x <= 1919 and p.y == pytest.approx(1079)


def test_region_edges_reach_screen_edges():
    m = mapper(mirror_x=False)
    assert m.map(0.15, 0.15).x == pytest.approx(0.0, abs=1e-6)
    assert m.map(0.85, 0.80).x == pytest.approx(1919)
    assert m.map(0.5, 0.80).y == pytest.approx(1079)


def test_sensitivity_amplifies():
    base = mapper(mirror_x=False, margin_bottom=0.15)
    hi = mapper(mirror_x=False, margin_bottom=0.15, sensitivity=2.0)
    a, b = base.map(0.6, 0.5), hi.map(0.6, 0.5)
    assert (b.x - 959.5) == pytest.approx(2 * (a.x - 959.5))


def test_bad_screen():
    with pytest.raises(ValueError):
        CoordinateMapper(MappingConfig(), 1, 1)


def test_four_corners_and_acceleration():
    m = mapper(mirror_x=False, acceleration=1.0)
    # top-left
    tl = m.map(0.15, 0.15)
    assert tl.x == pytest.approx(0.0) and tl.y == pytest.approx(0.0)
    # bottom-right
    br = m.map(0.85, 0.80)
    assert br.x == pytest.approx(1919.0) and br.y == pytest.approx(1079.0)

    # test acceleration effect
    m_acc = mapper(mirror_x=False, acceleration=1.5)
    # Near center, acceleration reduces displacement (giving higher precision)
    p_linear = m.map(0.55, 0.5)
    p_acc = m_acc.map(0.55, 0.5)
    assert abs(p_acc.x - 959.5) < abs(p_linear.x - 959.5)

