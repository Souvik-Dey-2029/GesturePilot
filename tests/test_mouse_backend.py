from types import SimpleNamespace as NS

import pytest

from virtual_mouse.mouse.backend import (
    FakeMouseBackend,
    MouseBackendError,
    MouseFailSafeTriggered,
    PyAutoGUIBackend,
)


class FakeFailSafe(Exception):
    pass


def fake_module(**overrides):
    calls = []

    def rec(name):
        def fn(*a, **k):
            calls.append((name, a, k))
            if name in overrides.get("raise_on", {}):
                raise overrides["raise_on"][name]

        return fn

    m = NS(
        FAILSAFE=False,
        PAUSE=0.1,
        FailSafeException=FakeFailSafe,
        moveTo=rec("moveTo"),
        mouseDown=rec("mouseDown"),
        mouseUp=rec("mouseUp"),
        rightClick=rec("rightClick"),
        scroll=rec("scroll"),
        size=lambda: (1920, 1080),
    )
    return m, calls


def test_init_forces_failsafe_on_and_pause_zero():
    m, _ = fake_module()
    PyAutoGUIBackend(m)
    assert m.FAILSAFE is True and m.PAUSE == 0


def test_calls_pass_no_pause_and_right_arguments():
    m, calls = fake_module()
    b = PyAutoGUIBackend(m)
    b.move_to(10, 20)
    b.left_down()
    b.left_up()
    b.right_click()
    b.scroll(-3)
    assert calls == [
        ("moveTo", (10, 20), {"_pause": False}),
        ("mouseDown", (), {"button": "left", "_pause": False}),
        ("mouseUp", (), {"button": "left", "_pause": False}),
        ("rightClick", (), {"_pause": False}),
        ("scroll", (-3,), {"_pause": False}),
    ]
    assert b.screen_size() == (1920, 1080)


def test_failsafe_and_generic_errors_are_translated():
    m, _ = fake_module(raise_on={"moveTo": FakeFailSafe("corner"), "rightClick": OSError("boom")})
    b = PyAutoGUIBackend(m)
    with pytest.raises(MouseFailSafeTriggered):
        b.move_to(0, 0)
    with pytest.raises(MouseBackendError) as ei:
        b.right_click()
    assert not isinstance(ei.value, MouseFailSafeTriggered)


def test_left_up_falls_back_to_forced_release_on_failsafe():
    m, _ = fake_module(raise_on={"mouseUp": FakeFailSafe("corner")})
    forced = []
    PyAutoGUIBackend(m, force_release_left=lambda: forced.append(1)).left_up()
    assert forced == [1]


def test_left_up_other_error_propagates_without_forcing():
    m, _ = fake_module(raise_on={"mouseUp": OSError("x")})
    forced = []
    with pytest.raises(MouseBackendError):
        PyAutoGUIBackend(m, force_release_left=lambda: forced.append(1)).left_up()
    assert forced == []


def test_import_failure_becomes_backend_error(monkeypatch):
    import importlib

    def boom(name):
        raise KeyError("DISPLAY")

    monkeypatch.setattr(importlib, "import_module", boom)
    with pytest.raises(MouseBackendError):
        PyAutoGUIBackend()


def test_fake_backend_records_and_fails_on_demand():
    f = FakeMouseBackend(100, 50)
    f.move_to(3, 4)
    f.left_down()
    assert f.position == (3, 4) and f.left_held and f.names() == ["move_to", "left_down"]
    f.fail_on["scroll"] = MouseBackendError("x")
    with pytest.raises(MouseBackendError):
        f.scroll(1)
    f.left_up()
    assert not f.left_held
