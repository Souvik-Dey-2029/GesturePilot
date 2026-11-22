"""Centralized Mutually-Exclusive State Machine & v005 Gesture Engine."""
from __future__ import annotations

import logging
from ..types import HandObservation, Landmark, LandmarkId
from .config import GestureConfig
from .geometry import (
    compute_hand_scale,
    euclidean_dist_2d,
    finger_extension_ratio,
    is_finger_curled_strict,
    is_finger_extended_strict,
    is_thumb_extended,
    normalized_distance,
)
from .types import (
    ActiveGesture,
    GestureMetrics,
    GestureResult,
    HandPose,
    InteractionState,
    MouseAction,
    MouseActionType,
)

log = logging.getLogger(__name__)


def is_finger_extended(hand: HandObservation, tip_id: LandmarkId, pip_id: LandmarkId) -> bool:
    """Backwards-compatible finger extension test."""
    wrist = hand.point(LandmarkId.WRIST)
    tip = hand.point(tip_id)
    pip = hand.point(pip_id)
    return euclidean_dist_2d(tip, wrist) > euclidean_dist_2d(pip, wrist)


class GestureRecognizer:
    """v005 Mutually Exclusive Gesture Recognizer & State Machine.
    
    Interaction Vocabulary:
    1. Open palm: PAUSE (cursor frozen, clicks/scroll ignored).
    2. Index finger only: POINTER MODE (cursor tracks index tip smoothly).
    3. Index + Middle: LEFT CLICK (if held stationary) / SCROLL (if intentional vertical movement).
    4. Index + Middle + Ring: RIGHT CLICK (if held stationary) / SCROLL (if intentional vertical movement).
    5. Thumb + Index pinch: DOUBLE CLICK.
    6. Dynamic SCROLL: Continuous scrolling with frozen cursor until hand returns to pointer or open palm.
    """

    def __init__(self, config: GestureConfig | None = None) -> None:
        self.config = config or GestureConfig()
        self.reset()

    def reset(self) -> None:
        """Reset all state machine variables, timers, and latches."""
        self._state = InteractionState.POINTER
        self._last_state = InteractionState.POINTER

        # Double click pinch tracking
        self._pinch_consecutive_frames = 0
        self._pinch_cooldown_until = 0.0

        # Two-finger gesture tracking
        self._two_finger_start_time: float | None = None
        self._two_finger_anchor_y: float | None = None
        self._left_click_cooldown_until = 0.0
        self._two_finger_clicked = False

        # Three-finger gesture tracking
        self._three_finger_start_time: float | None = None
        self._three_finger_anchor_y: float | None = None
        self._right_click_cooldown_until = 0.0
        self._three_finger_clicked = False

        # Scrolling engine
        self._scroll_source: str = ""  # "TWO_FINGER" or "THREE_FINGER"
        self._last_scroll_y: float | None = None
        self._scroll_accumulator = 0.0
        self._scroll_direction = "NONE"
        self._scroll_exit_pending_start: float | None = None

    @property
    def current_state(self) -> InteractionState:
        return self._state

    def classify_pose(self, hand: HandObservation, scale: float) -> tuple[HandPose, str]:
        """Classify discrete static hand pose using extension ratios and normalized geometry."""
        cfg = self.config

        # Individual finger extensions
        idx_ext = is_finger_extended_strict(hand, LandmarkId.INDEX_TIP, LandmarkId.INDEX_PIP, cfg.finger_extended_ratio)
        mid_ext = is_finger_extended_strict(hand, LandmarkId.MIDDLE_TIP, LandmarkId.MIDDLE_PIP, cfg.finger_extended_ratio)
        ring_ext = is_finger_extended_strict(hand, LandmarkId.RING_TIP, LandmarkId.RING_PIP, cfg.finger_extended_ratio)
        pinky_ext = is_finger_extended_strict(hand, LandmarkId.PINKY_TIP, LandmarkId.PINKY_PIP, cfg.finger_extended_ratio)
        thumb_ext = is_thumb_extended(hand)

        ring_curled = is_finger_curled_strict(hand, LandmarkId.RING_TIP, LandmarkId.RING_PIP, cfg.finger_curled_ratio)
        pinky_curled = is_finger_curled_strict(hand, LandmarkId.PINKY_TIP, LandmarkId.PINKY_PIP, cfg.finger_curled_ratio)
        mid_curled = is_finger_curled_strict(hand, LandmarkId.MIDDLE_TIP, LandmarkId.MIDDLE_PIP, cfg.finger_curled_ratio)

        thumb_tip = hand.point(LandmarkId.THUMB_TIP)
        index_tip = hand.point(LandmarkId.INDEX_TIP)
        pinch_dist = normalized_distance(thumb_tip, index_tip, scale)

        # 1. Double-click Pinch: thumb and index tips close
        if pinch_dist < cfg.pinch_threshold:
            return HandPose.PINCH, "thumb_index_pinch"

        # 2. Open Palm: All 5 fingers extended (or 4 long fingers + thumb away)
        if idx_ext and mid_ext and ring_ext and pinky_ext:
            return HandPose.OPEN_PALM, "open_palm"

        # 3. Three Fingers: Index + Middle + Ring extended, pinky curled
        if idx_ext and mid_ext and ring_ext and pinky_curled:
            return HandPose.THREE_FINGERS, "three_fingers"

        # 4. Two Fingers: Index + Middle extended, ring & pinky curled
        if idx_ext and mid_ext and ring_curled and pinky_curled:
            return HandPose.TWO_FINGERS, "two_fingers"

        # 5. Pointer Mode: Index extended, middle/ring/pinky curled
        if idx_ext and mid_curled and ring_curled and pinky_curled:
            return HandPose.POINTER, "pointer"

        # 6. Fist or ambiguous
        if (not idx_ext) and (not mid_ext) and (not ring_ext) and (not pinky_ext):
            return HandPose.FIST, "fist"

        return HandPose.UNKNOWN, "ambiguous_pose"

    def update(self, hand: HandObservation | None, now: float) -> GestureResult:
        """Process current hand observation and transition the centralized state machine."""
        cfg = self.config

        # 1. Safety & Tracking Loss
        if hand is None:
            self.reset()
            self._state = InteractionState.TRACKING_LOST
            return GestureResult(
                active_gesture=ActiveGesture.NONE,
                action=MouseAction(MouseActionType.NONE),
                metrics=GestureMetrics(rejection_reason="tracking_lost"),
                interaction_state=InteractionState.TRACKING_LOST,
                cursor_movement_allowed=False,
            )

        # Compute geometry & classification
        scale = compute_hand_scale(hand)
        thumb_tip = hand.point(LandmarkId.THUMB_TIP)
        index_tip = hand.point(LandmarkId.INDEX_TIP)
        middle_tip = hand.point(LandmarkId.MIDDLE_TIP)
        ring_tip = hand.point(LandmarkId.RING_TIP)

        pinch_dist = normalized_distance(thumb_tip, index_tip, scale)
        idx_ext = is_finger_extended_strict(hand, LandmarkId.INDEX_TIP, LandmarkId.INDEX_PIP, cfg.finger_extended_ratio)
        mid_ext = is_finger_extended_strict(hand, LandmarkId.MIDDLE_TIP, LandmarkId.MIDDLE_PIP, cfg.finger_extended_ratio)
        ring_ext = is_finger_extended_strict(hand, LandmarkId.RING_TIP, LandmarkId.RING_PIP, cfg.finger_extended_ratio)
        pinky_ext = is_finger_extended_strict(hand, LandmarkId.PINKY_TIP, LandmarkId.PINKY_PIP, cfg.finger_extended_ratio)
        thumb_ext = is_thumb_extended(hand)

        pose, reason = self.classify_pose(hand, scale)

        metrics = GestureMetrics(
            pinch_dist=pinch_dist,
            index_extended=idx_ext,
            middle_extended=mid_ext,
            ring_extended=ring_ext,
            pinky_extended=pinky_ext,
            thumb_extended=thumb_ext,
            recognized_pose=pose,
            rejection_reason=reason,
            scroll_direction=self._scroll_direction,
            stability_pct=95 if pose != HandPose.UNKNOWN else 40,
        )

        # -------------------------------------------------------------
        # STATE 1: PAUSED (Gesture 1 — Open Palm)
        # Suspends cursor movement, ignores click and scroll gestures
        # -------------------------------------------------------------
        if pose == HandPose.OPEN_PALM:
            self._state = InteractionState.PAUSED
            # Reset active gestures
            self._two_finger_start_time = None
            self._three_finger_start_time = None
            self._scroll_direction = "NONE"
            return GestureResult(
                active_gesture=ActiveGesture.PAUSE,
                action=MouseAction(MouseActionType.NONE),
                metrics=metrics,
                interaction_state=InteractionState.PAUSED,
                cursor_movement_allowed=False,  # Cursor frozen
            )

        # -------------------------------------------------------------
        # STATE 2: ACTIVE SCROLLING (Dynamic Interaction Mode)
        # Entered from TWO_FINGER or THREE_FINGER motion.
        # Cursor is frozen. Vertical movement emits scroll ticks.
        # Exits when user returns to POINTER or OPEN_PALM for exit duration.
        # -------------------------------------------------------------
        if self._state == InteractionState.SCROLLING:
            # Check exit conditions
            if pose in (HandPose.POINTER, HandPose.OPEN_PALM):
                if self._scroll_exit_pending_start is None:
                    self._scroll_exit_pending_start = now
                elif (now - self._scroll_exit_pending_start) >= cfg.scroll_exit_duration_s:
                    # Transition cleanly out of scrolling
                    self._state = InteractionState.POINTER
                    self._scroll_exit_pending_start = None
                    self._last_scroll_y = None
                    self._scroll_accumulator = 0.0
                    self._scroll_direction = "NONE"
                    return GestureResult(
                        active_gesture=ActiveGesture.POINTER,
                        action=MouseAction(MouseActionType.NONE),
                        metrics=metrics,
                        interaction_state=InteractionState.POINTER,
                        cursor_movement_allowed=True,
                    )
            else:
                self._scroll_exit_pending_start = None

            # Calculate current vertical reference point (midpoint of active fingers)
            if self._scroll_source == "THREE_FINGER":
                current_y = (index_tip.y + middle_tip.y + ring_tip.y) / 3.0
            else:
                current_y = (index_tip.y + middle_tip.y) / 2.0

            action = MouseAction(MouseActionType.NONE)
            if self._last_scroll_y is not None:
                dy = self._last_scroll_y - current_y  # positive when moving hand upward in camera frame
                if abs(dy) >= cfg.scroll_deadzone_dy:
                    self._scroll_direction = "UP" if dy > 0 else "DOWN"
                    notch_delta = dy * cfg.scroll_speed
                    self._scroll_accumulator += notch_delta
                    int_notches = int(self._scroll_accumulator)
                    if int_notches != 0:
                        self._scroll_accumulator -= int_notches
                        action = MouseAction(MouseActionType.SCROLL, scroll_amount=int_notches)
                else:
                    self._scroll_direction = "NONE"

            self._last_scroll_y = current_y

            return GestureResult(
                active_gesture=ActiveGesture.SCROLL,
                action=action,
                metrics=GestureMetrics(
                    pinch_dist=pinch_dist,
                    index_extended=idx_ext,
                    middle_extended=mid_ext,
                    ring_extended=ring_ext,
                    pinky_extended=pinky_ext,
                    thumb_extended=thumb_ext,
                    recognized_pose=pose,
                    rejection_reason=reason,
                    scroll_direction=self._scroll_direction,
                    stability_pct=90,
                ),
                interaction_state=InteractionState.SCROLLING,
                cursor_movement_allowed=False,  # Cursor remains frozen during scrolling
            )

        # -------------------------------------------------------------
        # STATE 3: PINCH (Gesture 5 — Thumb + Index Pinch: DOUBLE CLICK)
        # -------------------------------------------------------------
        if self._state == InteractionState.PINCH_PENDING:
            # Check for release to re-arm
            if pinch_dist > cfg.pinch_release_threshold:
                self._state = InteractionState.POINTER
                self._pinch_cooldown_until = now + cfg.pinch_cooldown_s
                self._pinch_consecutive_frames = 0
                return GestureResult(
                    active_gesture=ActiveGesture.POINTER,
                    action=MouseAction(MouseActionType.NONE),
                    metrics=metrics,
                    interaction_state=InteractionState.POINTER,
                    cursor_movement_allowed=True,
                )
            return GestureResult(
                active_gesture=ActiveGesture.DOUBLE_CLICK,
                action=MouseAction(MouseActionType.NONE),
                metrics=metrics,
                interaction_state=InteractionState.PINCH_PENDING,
                cursor_movement_allowed=True,
            )

        if pose == HandPose.PINCH and self._state == InteractionState.POINTER:
            if now >= self._pinch_cooldown_until:
                self._pinch_consecutive_frames += 1
                if self._pinch_consecutive_frames >= cfg.pinch_confirm_frames:
                    # Trigger exactly ONE double-click
                    self._state = InteractionState.PINCH_PENDING
                    return GestureResult(
                        active_gesture=ActiveGesture.DOUBLE_CLICK,
                        action=MouseAction(MouseActionType.DOUBLE_CLICK),
                        metrics=metrics,
                        interaction_state=InteractionState.PINCH_PENDING,
                        cursor_movement_allowed=True,
                    )
                return GestureResult(
                    active_gesture=ActiveGesture.DOUBLE_CLICK,
                    action=MouseAction(MouseActionType.NONE),
                    metrics=metrics,
                    interaction_state=InteractionState.POINTER,
                    cursor_movement_allowed=True,
                )
        else:
            self._pinch_consecutive_frames = 0

        # -------------------------------------------------------------
        # STATE 4: TWO FINGERS (Gesture 3 — Index + Middle: LEFT CLICK / SCROLL)
        # -------------------------------------------------------------
        if pose == HandPose.TWO_FINGERS:
            mid_y = (index_tip.y + middle_tip.y) / 2.0

            if self._two_finger_start_time is None:
                self._two_finger_start_time = now
                self._two_finger_anchor_y = mid_y
                self._two_finger_clicked = False
                self._state = InteractionState.TWO_FINGER_PENDING
                return GestureResult(
                    active_gesture=ActiveGesture.LEFT_CLICK,
                    action=MouseAction(MouseActionType.NONE),
                    metrics=metrics,
                    interaction_state=InteractionState.TWO_FINGER_PENDING,
                    cursor_movement_allowed=True,
                )

            # Check if intentional vertical movement occurred before click window completed
            anchor_y = self._two_finger_anchor_y or mid_y
            disp_y = abs(mid_y - anchor_y)
            elapsed = now - self._two_finger_start_time

            if disp_y >= cfg.two_finger_motion_threshold:
                # Cancel pending click, enter SCROLLING!
                self._state = InteractionState.SCROLLING
                self._scroll_source = "TWO_FINGER"
                self._last_scroll_y = mid_y
                self._scroll_accumulator = 0.0
                return GestureResult(
                    active_gesture=ActiveGesture.SCROLL,
                    action=MouseAction(MouseActionType.NONE),
                    metrics=metrics,
                    interaction_state=InteractionState.SCROLLING,
                    cursor_movement_allowed=False,
                )

            # Check if stationary hold window completed without scrolling motion
            if elapsed >= cfg.two_finger_click_window_s and not self._two_finger_clicked:
                self._two_finger_clicked = True
                if now >= self._left_click_cooldown_until:
                    self._left_click_cooldown_until = now + cfg.left_click_cooldown_s
                    return GestureResult(
                        active_gesture=ActiveGesture.LEFT_CLICK,
                        action=MouseAction(MouseActionType.LEFT_CLICK),
                        metrics=metrics,
                        interaction_state=InteractionState.TWO_FINGER_PENDING,
                        cursor_movement_allowed=True,
                    )

            return GestureResult(
                active_gesture=ActiveGesture.LEFT_CLICK,
                action=MouseAction(MouseActionType.NONE),
                metrics=metrics,
                interaction_state=InteractionState.TWO_FINGER_PENDING,
                cursor_movement_allowed=True,
            )
        else:
            # Exited two-finger pose
            self._two_finger_start_time = None
            self._two_finger_anchor_y = None

        # -------------------------------------------------------------
        # STATE 5: THREE FINGERS (Gesture 4 — Index + Middle + Ring: RIGHT CLICK / SCROLL)
        # -------------------------------------------------------------
        if pose == HandPose.THREE_FINGERS:
            tri_y = (index_tip.y + middle_tip.y + ring_tip.y) / 3.0

            if self._three_finger_start_time is None:
                self._three_finger_start_time = now
                self._three_finger_anchor_y = tri_y
                self._three_finger_clicked = False
                self._state = InteractionState.THREE_FINGER_PENDING
                return GestureResult(
                    active_gesture=ActiveGesture.RIGHT_CLICK,
                    action=MouseAction(MouseActionType.NONE),
                    metrics=metrics,
                    interaction_state=InteractionState.THREE_FINGER_PENDING,
                    cursor_movement_allowed=True,
                )

            anchor_y = self._three_finger_anchor_y or tri_y
            disp_y = abs(tri_y - anchor_y)
            elapsed = now - self._three_finger_start_time

            if disp_y >= cfg.three_finger_motion_threshold:
                # Cancel pending right click, enter SCROLLING!
                self._state = InteractionState.SCROLLING
                self._scroll_source = "THREE_FINGER"
                self._last_scroll_y = tri_y
                self._scroll_accumulator = 0.0
                return GestureResult(
                    active_gesture=ActiveGesture.SCROLL,
                    action=MouseAction(MouseActionType.NONE),
                    metrics=metrics,
                    interaction_state=InteractionState.SCROLLING,
                    cursor_movement_allowed=False,
                )

            if elapsed >= cfg.three_finger_click_window_s and not self._three_finger_clicked:
                self._three_finger_clicked = True
                if now >= self._right_click_cooldown_until:
                    self._right_click_cooldown_until = now + cfg.right_click_cooldown_s
                    return GestureResult(
                        active_gesture=ActiveGesture.RIGHT_CLICK,
                        action=MouseAction(MouseActionType.RIGHT_CLICK),
                        metrics=metrics,
                        interaction_state=InteractionState.THREE_FINGER_PENDING,
                        cursor_movement_allowed=True,
                    )

            return GestureResult(
                active_gesture=ActiveGesture.RIGHT_CLICK,
                action=MouseAction(MouseActionType.NONE),
                metrics=metrics,
                interaction_state=InteractionState.THREE_FINGER_PENDING,
                cursor_movement_allowed=True,
            )
        else:
            self._three_finger_start_time = None
            self._three_finger_anchor_y = None

        # -------------------------------------------------------------
        # STATE 6: POINTER (Gesture 2 — Index Finger Only: POINTER MODE)
        # Default active interaction mode
        # -------------------------------------------------------------
        if pose == HandPose.POINTER:
            self._state = InteractionState.POINTER
            return GestureResult(
                active_gesture=ActiveGesture.POINTER,
                action=MouseAction(MouseActionType.NONE),
                metrics=metrics,
                interaction_state=InteractionState.POINTER,
                cursor_movement_allowed=True,
            )

        # -------------------------------------------------------------
        # STATE 7: UNKNOWN / AMBIGUOUS
        # Produces NO mouse action and freezes cursor
        # -------------------------------------------------------------
        self._state = InteractionState.UNKNOWN
        return GestureResult(
            active_gesture=ActiveGesture.NONE,
            action=MouseAction(MouseActionType.NONE),
            metrics=metrics,
            interaction_state=InteractionState.UNKNOWN,
            cursor_movement_allowed=False,  # Don't move cursor on ambiguous poses
        )
