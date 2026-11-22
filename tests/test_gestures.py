"""Comprehensive automated tests for v005 gesture recognition:
- Pose classification: Open Palm (Pause), Pointer, Two Fingers, Three Fingers, Pinch, Fist, Unknown
- Open Palm: immediate pause, cursor frozen, suppress clicks/scrolls
- Pointer: cursor movement allowed, no spurious actions
- Two Fingers: stationary click window triggers LEFT_CLICK; vertical motion enters SCROLLING
- Three Fingers: stationary click window triggers RIGHT_CLICK; vertical motion enters SCROLLING
- Pinch: triggers DOUBLE_CLICK with hysteresis and cooldown
- Dynamic SCROLLING: cursor frozen, vertical displacement generates scroll ticks, exits cleanly
- Ambiguity rejection & safety tracking loss
"""
import pytest

from virtual_mouse.gestures.config import GestureConfig
from virtual_mouse.gestures.geometry import compute_hand_scale, normalized_distance
from virtual_mouse.gestures.recognizer import GestureRecognizer
from virtual_mouse.gestures.types import (
    ActiveGesture,
    HandPose,
    InteractionState,
    MouseActionType,
)
from virtual_mouse.types import HandObservation, Landmark, LandmarkId, NUM_LANDMARKS


def create_hand(
    wrist=(0.5, 0.8),
    thumb=(0.3, 0.4),
    index=(0.4, 0.3),
    middle=(0.5, 0.7),
    ring=(0.6, 0.75),
    pinky=(0.7, 0.75),
    index_pip=(0.4, 0.5),
    middle_pip=(0.5, 0.6),
    ring_pip=(0.6, 0.65),
    pinky_pip=(0.7, 0.65),
    score=0.95,
) -> HandObservation:
    """Helper to construct a realistic 21-landmark hand observation with specific keypoints."""
    landmarks = [Landmark(0.5, 0.5, 0.0)] * NUM_LANDMARKS
    landmarks[LandmarkId.WRIST] = Landmark(wrist[0], wrist[1], 0.0)
    landmarks[LandmarkId.INDEX_MCP] = Landmark(0.45, 0.55, 0.0)
    landmarks[LandmarkId.MIDDLE_MCP] = Landmark(0.5, 0.5, 0.0)  # scale = 0.3
    landmarks[LandmarkId.RING_MCP] = Landmark(0.55, 0.55, 0.0)
    landmarks[LandmarkId.PINKY_MCP] = Landmark(0.6, 0.6, 0.0)
    landmarks[LandmarkId.THUMB_TIP] = Landmark(thumb[0], thumb[1], 0.0)
    landmarks[LandmarkId.INDEX_TIP] = Landmark(index[0], index[1], 0.0)
    landmarks[LandmarkId.INDEX_PIP] = Landmark(index_pip[0], index_pip[1], 0.0)
    landmarks[LandmarkId.MIDDLE_TIP] = Landmark(middle[0], middle[1], 0.0)
    landmarks[LandmarkId.MIDDLE_PIP] = Landmark(middle_pip[0], middle_pip[1], 0.0)
    landmarks[LandmarkId.RING_TIP] = Landmark(ring[0], ring[1], 0.0)
    landmarks[LandmarkId.RING_PIP] = Landmark(ring_pip[0], ring_pip[1], 0.0)
    landmarks[LandmarkId.PINKY_TIP] = Landmark(pinky[0], pinky[1], 0.0)
    landmarks[LandmarkId.PINKY_PIP] = Landmark(pinky_pip[0], pinky_pip[1], 0.0)
    return HandObservation(tuple(landmarks), "Right", score)


def test_hand_scale_and_normalized_distance():
    hand = create_hand()
    scale = compute_hand_scale(hand)
    # wrist (0.5, 0.8) to middle_mcp (0.5, 0.5) is 0.3
    assert pytest.approx(scale, 0.001) == 0.3

    p1 = hand.point(LandmarkId.THUMB_TIP)
    p2 = hand.point(LandmarkId.INDEX_TIP)
    nd = normalized_distance(p1, p2, scale)
    assert nd > 0.0


def test_pose_classification():
    rec = GestureRecognizer()

    # 1. Pointing Pose: Index extended, middle/ring/pinky curled
    hand_pointing = create_hand(
        thumb=(0.3, 0.5),
        index=(0.4, 0.2), index_pip=(0.4, 0.5),
        middle=(0.5, 0.75), middle_pip=(0.5, 0.6),
        ring=(0.6, 0.75), ring_pip=(0.6, 0.65),
        pinky=(0.7, 0.75), pinky_pip=(0.7, 0.65),
    )
    scale = compute_hand_scale(hand_pointing)
    pose, _ = rec.classify_pose(hand_pointing, scale)
    assert pose == HandPose.POINTER

    # 2. Two Fingers: Index & Middle extended, Ring & Pinky curled
    hand_two = create_hand(
        thumb=(0.3, 0.5),
        index=(0.45, 0.25), index_pip=(0.45, 0.5),
        middle=(0.52, 0.25), middle_pip=(0.52, 0.5),
        ring=(0.6, 0.75), ring_pip=(0.6, 0.65),
        pinky=(0.7, 0.75), pinky_pip=(0.7, 0.65),
    )
    pose_two, _ = rec.classify_pose(hand_two, compute_hand_scale(hand_two))
    assert pose_two == HandPose.TWO_FINGERS

    # 3. Three Fingers: Index, Middle & Ring extended, Pinky curled
    hand_three = create_hand(
        thumb=(0.3, 0.5),
        index=(0.42, 0.25), index_pip=(0.42, 0.5),
        middle=(0.50, 0.25), middle_pip=(0.50, 0.5),
        ring=(0.58, 0.25), ring_pip=(0.58, 0.5),
        pinky=(0.7, 0.75), pinky_pip=(0.7, 0.65),
    )
    pose_three, _ = rec.classify_pose(hand_three, compute_hand_scale(hand_three))
    assert pose_three == HandPose.THREE_FINGERS

    # 4. Open Palm: All fingers extended
    hand_palm = create_hand(
        thumb=(0.2, 0.3),
        index=(0.4, 0.2), index_pip=(0.4, 0.5),
        middle=(0.5, 0.2), middle_pip=(0.5, 0.5),
        ring=(0.6, 0.2), ring_pip=(0.6, 0.5),
        pinky=(0.7, 0.2), pinky_pip=(0.7, 0.5),
    )
    pose_palm, _ = rec.classify_pose(hand_palm, compute_hand_scale(hand_palm))
    assert pose_palm == HandPose.OPEN_PALM

    # 5. Thumb-Index Pinch
    hand_pinch = create_hand(
        thumb=(0.44, 0.3), index=(0.45, 0.3),
        middle=(0.5, 0.75), middle_pip=(0.5, 0.6),
    )
    pose_pinch, _ = rec.classify_pose(hand_pinch, scale)
    assert pose_pinch == HandPose.PINCH


def test_open_palm_pause():
    """Gesture 1: Open Palm immediately freezes cursor and emits no clicks/scrolls."""
    rec = GestureRecognizer()
    now = 1.0

    hand_palm = create_hand(
        thumb=(0.2, 0.3),
        index=(0.4, 0.2), index_pip=(0.4, 0.5),
        middle=(0.5, 0.2), middle_pip=(0.5, 0.5),
        ring=(0.6, 0.2), ring_pip=(0.6, 0.5),
        pinky=(0.7, 0.2), pinky_pip=(0.7, 0.5),
    )
    res = rec.update(hand_palm, now)
    assert res.interaction_state == InteractionState.PAUSED
    assert res.active_gesture == ActiveGesture.PAUSE
    assert res.cursor_movement_allowed is False
    assert res.action.action_type == MouseActionType.NONE


def test_pointer_mode():
    """Gesture 2: Index-only pointer mode allows cursor movement."""
    rec = GestureRecognizer()
    now = 1.0

    hand_ptr = create_hand(
        thumb=(0.3, 0.5),
        index=(0.4, 0.2), index_pip=(0.4, 0.5),
        middle=(0.5, 0.75), middle_pip=(0.5, 0.6),
        ring=(0.6, 0.75), ring_pip=(0.6, 0.65),
        pinky=(0.7, 0.75), pinky_pip=(0.7, 0.65),
    )
    res = rec.update(hand_ptr, now)
    assert res.interaction_state == InteractionState.POINTER
    assert res.active_gesture == ActiveGesture.POINTER
    assert res.cursor_movement_allowed is True
    assert res.action.action_type == MouseActionType.NONE


def test_two_finger_stationary_left_click():
    """Gesture 3: Stationary 2-finger pose triggers exactly one LEFT_CLICK after window."""
    cfg = GestureConfig(
        two_finger_click_window_s=0.20,
        two_finger_motion_threshold=0.03,
        left_click_cooldown_s=0.15,
    )
    rec = GestureRecognizer(cfg)
    now = 1.0

    hand_two = create_hand(
        thumb=(0.3, 0.5),
        index=(0.45, 0.25), index_pip=(0.45, 0.5),
        middle=(0.52, 0.25), middle_pip=(0.52, 0.5),
        ring=(0.6, 0.75), ring_pip=(0.6, 0.65),
        pinky=(0.7, 0.75), pinky_pip=(0.7, 0.65),
    )

    # Frame 1: Enters pending state
    res1 = rec.update(hand_two, now)
    assert res1.interaction_state == InteractionState.TWO_FINGER_PENDING
    assert res1.action.action_type == MouseActionType.NONE

    # Frame 2: Mid-window, still pending
    now += 0.10
    res2 = rec.update(hand_two, now)
    assert res2.interaction_state == InteractionState.TWO_FINGER_PENDING
    assert res2.action.action_type == MouseActionType.NONE

    # Frame 3: Window expires without motion -> single LEFT_CLICK
    now += 0.12
    res3 = rec.update(hand_two, now)
    assert res3.interaction_state == InteractionState.TWO_FINGER_PENDING
    assert res3.action.action_type == MouseActionType.LEFT_CLICK

    # Frame 4: Further frames do not emit repeat click (locked out)
    now += 0.05
    res4 = rec.update(hand_two, now)
    assert res4.action.action_type == MouseActionType.NONE


def test_two_finger_motion_cancels_click_and_scrolls():
    """Gesture 3: Moving 2-finger pose cancels click and enters SCROLLING mode."""
    cfg = GestureConfig(
        two_finger_click_window_s=0.20,
        two_finger_motion_threshold=0.02,
        scroll_deadzone_dy=0.005,
        scroll_speed=100.0,
    )
    rec = GestureRecognizer(cfg)
    now = 1.0

    hand_two = create_hand(
        thumb=(0.3, 0.5),
        index=(0.45, 0.40), index_pip=(0.45, 0.6),
        middle=(0.52, 0.40), middle_pip=(0.52, 0.6),
        ring=(0.6, 0.85), ring_pip=(0.6, 0.75),
        pinky=(0.7, 0.85), pinky_pip=(0.7, 0.75),
    )

    rec.update(hand_two, now)

    # Move hand upwards significantly before window completes
    now += 0.08
    hand_two_moved = create_hand(
        thumb=(0.3, 0.5),
        index=(0.45, 0.35), index_pip=(0.45, 0.6),
        middle=(0.52, 0.35), middle_pip=(0.52, 0.6),
        ring=(0.6, 0.85), ring_pip=(0.6, 0.75),
        pinky=(0.7, 0.85), pinky_pip=(0.7, 0.75),
    )
    res_scroll = rec.update(hand_two_moved, now)
    assert res_scroll.interaction_state == InteractionState.SCROLLING
    assert res_scroll.cursor_movement_allowed is False

    # Next frame continues scrolling and emits scroll tick
    now += 0.05
    hand_two_moved_again = create_hand(
        thumb=(0.3, 0.5),
        index=(0.45, 0.30), index_pip=(0.45, 0.6),
        middle=(0.52, 0.30), middle_pip=(0.52, 0.6),
        ring=(0.6, 0.85), ring_pip=(0.6, 0.75),
        pinky=(0.7, 0.85), pinky_pip=(0.7, 0.75),
    )
    res_tick = rec.update(hand_two_moved_again, now)
    assert res_tick.interaction_state == InteractionState.SCROLLING
    assert res_tick.action.action_type == MouseActionType.SCROLL
    assert res_tick.action.scroll_amount > 0  # Upward scroll


def test_three_finger_stationary_right_click():
    """Gesture 4: Stationary 3-finger pose triggers exactly one RIGHT_CLICK after window."""
    cfg = GestureConfig(
        three_finger_click_window_s=0.20,
        three_finger_motion_threshold=0.03,
        right_click_cooldown_s=0.15,
    )
    rec = GestureRecognizer(cfg)
    now = 1.0

    hand_three = create_hand(
        thumb=(0.3, 0.5),
        index=(0.42, 0.25), index_pip=(0.42, 0.5),
        middle=(0.50, 0.25), middle_pip=(0.50, 0.5),
        ring=(0.58, 0.25), ring_pip=(0.58, 0.5),
        pinky=(0.7, 0.75), pinky_pip=(0.7, 0.65),
    )

    rec.update(hand_three, now)
    now += 0.22
    res = rec.update(hand_three, now)
    assert res.interaction_state == InteractionState.THREE_FINGER_PENDING
    assert res.action.action_type == MouseActionType.RIGHT_CLICK


def test_pinch_double_click_and_hysteresis():
    """Gesture 5: Thumb-Index pinch triggers DOUBLE_CLICK."""
    cfg = GestureConfig(
        pinch_threshold=0.30,
        pinch_release_threshold=0.50,
        pinch_confirm_frames=1,
        pinch_cooldown_s=0.10,
    )
    rec = GestureRecognizer(cfg)
    now = 1.0

    # Pinch pose
    hand_pinch = create_hand(
        thumb=(0.44, 0.3), index=(0.45, 0.3),
        middle=(0.5, 0.75), middle_pip=(0.5, 0.6),
    )
    res = rec.update(hand_pinch, now)
    assert res.interaction_state == InteractionState.PINCH_PENDING
    assert res.action.action_type == MouseActionType.DOUBLE_CLICK

    # Continued pinch does not trigger duplicate click
    now += 0.05
    res2 = rec.update(hand_pinch, now)
    assert res2.action.action_type == MouseActionType.NONE
    assert res2.interaction_state == InteractionState.PINCH_PENDING

    # Release pinch re-arms
    hand_released = create_hand(
        thumb=(0.30, 0.3), index=(0.50, 0.3),
        middle=(0.5, 0.75), middle_pip=(0.5, 0.6),
    )
    now += 0.05
    res3 = rec.update(hand_released, now)
    assert res3.interaction_state == InteractionState.POINTER


def test_tracking_loss_resets_state():
    """Tracking loss resets state and sets TRACKING_LOST with cursor frozen."""
    rec = GestureRecognizer()
    now = 1.0

    hand_two = create_hand(
        thumb=(0.3, 0.5),
        index=(0.45, 0.25), index_pip=(0.45, 0.5),
        middle=(0.52, 0.25), middle_pip=(0.52, 0.5),
    )
    rec.update(hand_two, now)

    # Tracking lost
    res_lost = rec.update(None, now + 0.05)
    assert res_lost.interaction_state == InteractionState.TRACKING_LOST
    assert res_lost.cursor_movement_allowed is False
    assert res_lost.action.action_type == MouseActionType.NONE


def test_ambiguous_pose_rejection():
    """Verify that ambiguous or intermediate configurations freeze cursor without actions."""
    rec = GestureRecognizer()
    now = 1.0

    # Intermediate hand where middle is curled, ring is extended, pinky is curled (unusual/ambiguous finger combination)
    hand_ambiguous = create_hand(
        thumb=(0.3, 0.5),
        index=(0.4, 0.2), index_pip=(0.4, 0.5),      # extended (ratio > 1.1)
        middle=(0.5, 0.75), middle_pip=(0.5, 0.6),   # curled (ratio < 1.05)
        ring=(0.6, 0.2), ring_pip=(0.6, 0.5),        # extended (ratio > 1.1)
        pinky=(0.7, 0.75), pinky_pip=(0.7, 0.65),    # curled (ratio < 1.05)
    )
    res = rec.update(hand_ambiguous, now)
    assert res.action.action_type == MouseActionType.NONE
    assert res.interaction_state == InteractionState.UNKNOWN
    assert res.cursor_movement_allowed is False
