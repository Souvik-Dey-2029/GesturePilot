import random

import pytest

from virtual_mouse.config import SmoothingConfig
from virtual_mouse.mapping.smoothing import OneEuroFilter, PointFilter


def test_first_sample_passthrough():
    assert OneEuroFilter(1.0, 0.007, 1.0)(100.0, 0.0) == 100.0


def test_reduces_jitter_at_rest():
    rng = random.Random(1)
    f = OneEuroFilter(1.0, 0.007, 1.0)
    raw = [500 + rng.uniform(-3, 3) for _ in range(200)]
    out = [f(v, i / 30) for i, v in enumerate(raw)]
    spread = lambda xs: max(xs[50:]) - min(xs[50:])  # noqa: E731
    assert spread(out) < spread(raw) * 0.6


def test_tracks_fast_motion_with_bounded_lag():
    f = OneEuroFilter(1.0, 0.007, 1.0)
    out = 0.0
    for i in range(60):
        out = f(i * 40.0, i / 30)  # 1200 px/s sweep
    assert abs(2360.0 - out) < 400.0


def test_non_monotonic_time_holds():
    f = OneEuroFilter(1.0, 0.007, 1.0)
    f(10.0, 1.0)
    held = f(20.0, 1.1)
    assert f(999.0, 1.1) == pytest.approx(held)
    assert f(999.0, 1.0) == pytest.approx(held)


def test_reset_and_disabled():
    pf = PointFilter(SmoothingConfig())
    pf(0, 0, 0.0)
    pf(100, 100, 0.03)
    pf.reset()
    assert pf(500, 500, 1.0) == (500, 500)
    off = PointFilter(SmoothingConfig(enabled=False))
    assert off(7.0, 8.0, 0.0) == (7.0, 8.0) and off(9.0, 1.0, 0.1) == (9.0, 1.0)


def test_deadzone_tremor_suppression():
    # Deadzone 3.0 px: stationary small tremor (< 3.0 px) results in exact same output
    cfg = SmoothingConfig(enabled=True, deadzone_radius_px=3.0)
    pf = PointFilter(cfg)
    p0 = pf(500.0, 500.0, 0.0)
    assert p0 == (500.0, 500.0)

    # Sub-pixel jitter within deadzone: output is completely frozen
    p1 = pf(501.0, 500.8, 0.033)
    assert p1 == (500.0, 500.0)
    p2 = pf(499.2, 500.5, 0.066)
    assert p2 == (500.0, 500.0)

    # Movement beyond deadzone smoothly transitions without sudden discontinuity
    p3 = pf(520.0, 500.0, 0.100)
    assert p3[0] > 500.0 and p3[0] < 520.0


def test_nan_inf_protection():
    f = OneEuroFilter(1.0, 0.01, 1.0)
    f(100.0, 0.0)
    res = f(105.0, 0.033)
    # NaN and Inf should return held value without crashing
    assert f(float("nan"), 0.066) == res
    assert f(float("inf"), 0.100) == res

