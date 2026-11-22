import pytest

from virtual_mouse.config import SafetyConfig
from virtual_mouse.mouse.backend import FakeMouseBackend, MouseBackendError, MouseFailSafeTriggered
from virtual_mouse.mouse.controller import MouseController
from virtual_mouse.safety import SafetyController


@pytest.fixture
def rig(make_hand):
    backend = FakeMouseBackend()
    safety = SafetyController(SafetyConfig())
    mouse = MouseController(backend, safety)

    def arm():
        assert safety.enable()
        for i in range(3):
            safety.update(make_hand(), i * 0.03)

    return backend, safety, mouse, arm


def test_nothing_emitted_while_disabled_or_unreliable(rig, make_hand):
    backend, safety, mouse, arm = rig
    assert mouse.move_to(1, 1) is False  # disabled
    safety.enable()
    assert mouse.move_to(1, 1) is False  # enabled but still ACQUIRING
    assert not any((mouse.left_down(), mouse.right_click(), mouse.scroll(1)))
    assert backend.events == []


def test_emitted_when_armed(rig):
    backend, _, mouse, arm = rig
    arm()
    assert mouse.move_to(5, 6) and mouse.right_click() and mouse.scroll(2)
    assert backend.names() == ["move_to", "right_click", "scroll"]


def test_estop_releases_held_button_and_blocks_everything(rig):
    backend, safety, mouse, arm = rig
    arm()
    assert mouse.left_down() and mouse.left_held and backend.left_held
    safety.emergency_stop("test")
    assert not backend.left_held and not mouse.left_held and not safety.enabled
    n = len(backend.events)
    assert not any((mouse.move_to(1, 1), mouse.left_down(), mouse.right_click(), mouse.scroll(1)))
    assert len(backend.events) == n


def test_release_allowed_while_disabled(rig):
    backend, safety, mouse, arm = rig
    arm()
    mouse.left_down()
    safety.disable()
    assert mouse.left_up() is True and not backend.left_held
    assert mouse.left_up() is False  # nothing held


def test_backend_error_latches_estop_and_releases(rig):
    backend, safety, mouse, arm = rig
    arm()
    mouse.left_down()
    backend.fail_on["move_to"] = MouseBackendError("driver gone")
    assert mouse.move_to(1, 1) is False
    assert safety.estop.is_set and "driver gone" in safety.estop.reason and not backend.left_held


def test_failsafe_latches_estop(rig):
    backend, safety, mouse, arm = rig
    arm()
    backend.fail_on["move_to"] = MouseFailSafeTriggered("corner")
    assert mouse.move_to(0, 0) is False
    assert safety.estop.is_set and "failsafe" in safety.estop.reason.lower()


def test_failed_release_keeps_held_flag(rig):
    backend, safety, mouse, arm = rig
    arm()
    mouse.left_down()
    backend.fail_on["left_up"] = MouseBackendError("stuck")
    safety.emergency_stop("x")  # must not raise
    assert mouse.left_held is True
    backend.fail_on.clear()
    mouse.release_all()
    assert not mouse.left_held and not backend.left_held


def test_safe_reenable_procedure(rig, make_hand):
    backend, safety, mouse, arm = rig
    arm()
    safety.emergency_stop("x")
    assert safety.enable() is False
    safety.acknowledge_emergency_stop()
    assert not safety.enabled and not safety.estop.is_set  # acknowledged but still disabled
    assert mouse.move_to(1, 1) is False
    assert safety.enable() is True
    assert mouse.move_to(1, 1) is False  # must re-acquire reliable tracking first
    for i in range(3):
        safety.update(make_hand(), 10 + i * 0.03)
    assert mouse.move_to(1, 1) is True
