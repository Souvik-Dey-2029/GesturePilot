"""Debug drawing helpers (preview only; never used on the mouse-control path)."""
from __future__ import annotations

import numpy as np

from ..types import HandObservation

HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)


def draw_hand(image: np.ndarray, hand: HandObservation) -> None:
    """Draw skeleton + joints in place on a BGR image."""
    import cv2

    h, w = image.shape[:2]
    pts = [(int(p.x * w), int(p.y * h)) for p in hand.landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(image, pts[a], pts[b], (0, 200, 0), 2)
    for pt in pts:
        cv2.circle(image, pt, 3, (0, 0, 255), -1)


def draw_hud(
    image: np.ndarray,
    status_text: str,
    tracking_text: str,
    fps: float,
    active_gesture: str,
    mouse_state: str,
    pinch_dist: float = 0.0,
    cursor_pos: tuple[int, int] | None = None,
    diagnostic_mode: bool = False,
    active_region_margins: tuple[float, float, float, float] | None = None,
    interaction_mode: str = "POINTER",
    recognized_pose: str = "UNKNOWN",
    rejection_reason: str = "",
    scroll_direction: str = "NONE",
    stability_pct: int = 100,
    cursor_movement_allowed: bool = True,
) -> None:
    """Draw clean, non-overloaded HUD overlay with status, gestures, mouse state, and metrics.
    
    If diagnostic_mode is True, displays detailed engineering metrics requested in v005:
    - Tracking: ACTIVE | LOST
    - Pose: <recognized_pose>
    - State: <interaction_mode>
    - Gesture stability: <stability_pct>%
    - Scroll direction: <UP/DOWN/NONE>
    - Cursor control: <ACTIVE/FROZEN>
    - Last action: <mouse_state>
    - Rejection: <rejection_reason>
    - FPS: <fps>
    """
    import cv2

    h, w = image.shape[:2]

    # Draw active region guide rectangle in diagnostic mode
    if diagnostic_mode and active_region_margins is not None:
        ml, mr, mt, mb = active_region_margins
        rx1, ry1 = int(ml * w), int(mt * h)
        rx2, ry2 = int((1.0 - mr) * w), int((1.0 - mb) * h)
        cv2.rectangle(image, (rx1, ry1), (rx2, ry2), (255, 120, 0), 1)
        cv2.putText(image, "ACTIVE INTERACTION BOUNDARY", (rx1 + 4, ry1 + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 120, 0), 1)

    # Draw semi-transparent header banner
    banner_height = 115 if diagnostic_mode else 65
    overlay = image.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_height), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.75, image, 0.25, 0, image)

    # Line 1: Safety & System Status
    if "E-STOP" in status_text:
        status_color = (0, 0, 255)
    elif "ENABLED" in status_text:
        status_color = (0, 255, 0)
    else:
        status_color = (0, 200, 255)

    line1 = f"STATUS: {status_text}  |  TRACKING: {tracking_text.upper()}  |  FPS: {fps:.0f}  |  STATE: {interaction_mode.upper()}"
    cv2.putText(image, line1, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, status_color, 2)

    # Line 2: Gestures, Mouse Action, and Cursor Control
    ctrl_str = "ACTIVE" if cursor_movement_allowed else "FROZEN"
    ctrl_color = (0, 255, 0) if cursor_movement_allowed else (0, 165, 255)
    line2 = f"POSE: {recognized_pose.upper()}  |  ACTION: {mouse_state.upper()}  |  CURSOR: {ctrl_str}"
    cv2.putText(image, line2, (12, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 1)

    # Line 3 & 4: Diagnostic details
    if diagnostic_mode:
        cur_str = f"({cursor_pos[0]}, {cursor_pos[1]})" if cursor_pos else "N/A"
        line3 = f"SCROLL: {scroll_direction} | STABILITY: {stability_pct}% | PINCH_D: {pinch_dist:.2f} | CURSOR_XY: {cur_str}"
        cv2.putText(image, line3, (12, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 255, 255), 1)
        line4 = f"REJECT: {rejection_reason or 'none'} | DIAG: ON ('d' to toggle, 'c' calibrate, 'e' enable)"
        cv2.putText(image, line4, (12, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1)
