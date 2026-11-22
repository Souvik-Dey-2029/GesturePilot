from virtual_mouse.config import SafetyConfig
from virtual_mouse.safety import EmergencyStop, SafetyController, TrackingState


def make(**kw):
    return SafetyController(SafetyConfig(recovery_frames=3, lost_hand_timeout_s=0.25, min_hand_score=0.6, **kw))


def feed_good(sc, hand, start, n=3, dt=0.03):
    for i in range(n):
        sc.update(hand, start + i * dt)
    return start + n * dt


def test_starts_disabled_and_cannot_emit(make_hand):
    sc = make()
    feed_good(sc, make_hand(), 0.0)
    assert sc.monitor.state is TrackingState.RELIABLE and not sc.can_emit()


def test_enable_then_emit_requires_reliable(make_hand):
    sc = make()
    assert sc.enable() and not sc.can_emit()  # still ACQUIRING
    feed_good(sc, make_hand(), 0.0)
    assert sc.can_emit()


def test_low_score_never_reliable(make_hand):
    sc = make()
    sc.enable()
    feed_good(sc, make_hand(score=0.3), 0.0, n=10)
    assert sc.monitor.state is TrackingState.ACQUIRING and not sc.can_emit()


def test_short_dropout_tolerated_long_dropout_lost(make_hand):
    sc = make()
    sc.enable()
    t = feed_good(sc, make_hand(), 0.0)
    sc.update(None, t + 0.1)
    assert sc.monitor.state is TrackingState.RELIABLE
    sc.update(None, t + 0.4)
    assert sc.monitor.state is TrackingState.LOST and not sc.can_emit()


def test_recovery_needs_consecutive_good_frames(make_hand):
    sc = make()
    sc.enable()
    t = feed_good(sc, make_hand(), 0.0)
    sc.update(None, t + 1.0)
    h = make_hand()
    sc.update(h, t + 1.1)
    sc.update(h, t + 1.13)
    assert sc.monitor.state is TrackingState.LOST
    sc.update(None, t + 1.16)  # streak broken
    sc.update(h, t + 1.2)
    sc.update(h, t + 1.23)
    assert sc.monitor.state is TrackingState.LOST
    sc.update(h, t + 1.26)
    assert sc.monitor.state is TrackingState.RELIABLE


def test_estop_blocks_and_prevents_enable(make_hand):
    sc = make()
    sc.enable()
    feed_good(sc, make_hand(), 0.0)
    seen = []
    sc.estop.add_listener(seen.append)
    sc.estop.trigger("test")
    assert not sc.can_emit() and seen == ["test"] and sc.estop.reason == "test"
    sc.disable()
    assert sc.enable() is False and not sc.enabled
    sc.estop.clear()
    assert sc.enable() is True


def test_estop_listener_failure_isolated():
    es = EmergencyStop()
    called = []
    es.add_listener(lambda r: 1 / 0)
    es.add_listener(called.append)
    es.trigger("x")
    es.trigger("again")  # latched: listeners not re-run
    assert called == ["x"]
