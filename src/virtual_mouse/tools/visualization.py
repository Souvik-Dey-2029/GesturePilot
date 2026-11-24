"""Updated HUD overlay supporting RuntimeController modes, arming status, and honest unavailability."""
from __future__ import annotations

import cv2
import numpy as np
from typing import Optional, Tuple

HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20),
    (0, 17),
)


def draw_hand(image: np.ndarray, hand: Any) -> None:
    h, w = image.shape[:2]
    pts = [(int(p.x * w), int(p.y * h)) for p in hand.landmarks]
    for a, b in HAND_CONNECTIONS:
        cv2.line(image, pts[a], pts[b], (0, 200, 0), 2)
    for pt in pts:
        cv2.circle(image, pt, 3, (0, 0, 255), -1)


def draw_runtime_hud(
    image: np.ndarray,
    mode_text: str,
    master_armed: bool,
    estop_set: bool,
    estop_reason: str,
    tracking_text: str,
    fps: float,
    active_gesture: str,
    mouse_state: str,
    recognized_pose: str,
    status_message: str,
    diagnostic_mode: bool = False,
    active_boundary: Optional[Tuple[float, float, float, float]] = None,
    cursor_movement_allowed: bool = True,
    eye_telemetry: Optional[Any] = None,
) -> None:
    """Renders the comprehensive runtime telemetry HUD with honest modality and status indicators."""
    h, w = image.shape[:2]

    # Draw active region guide rectangle in diagnostic mode
    if diagnostic_mode and active_boundary is not None:
        ml, mr, mt, mb = active_boundary
        rx1, ry1 = int(ml * w), int(mt * h)
        rx2, ry2 = int((1.0 - mr) * w), int((1.0 - mb) * h)
        cv2.rectangle(image, (rx1, ry1), (rx2, ry2), (255, 120, 0), 1)
        cv2.putText(image, "ACTIVE MAPPING BOUNDARY", (rx1 + 4, ry1 + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 120, 0), 1)

    # Dynamic banner height based on active modalities and diagnostics
    has_eye = mode_text in ("EYE", "BOTH", "ALL")
    has_voice = mode_text in ("VOICE", "ALL")
    banner_height = 250 if diagnostic_mode else (175 if (has_eye or has_voice) else 75)
    overlay = image.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_height), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.78, image, 0.22, 0, image)

    # Line 1: Mode & Safety Arming Status
    if estop_set:
        status_str = f"E-STOP: {estop_reason.upper()}"
        status_col = (0, 0, 255)  # Red
    elif master_armed:
        status_str = "ARMED"
        status_col = (0, 255, 0)  # Green
    else:
        status_str = "DISARMED (Press 'm' to arm)"
        status_col = (0, 180, 255)  # Amber

    line1 = f"MODE: {mode_text.upper()}  |  CONTROL: {status_str}  |  FPS: {fps:.0f}  |  TRACKING: {tracking_text.upper()}"
    cv2.putText(image, line1, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.50, status_col, 2)

    # Line 2: Active Gesture, Pose, and Movement Authorization
    ctrl_str = "ACTIVE" if cursor_movement_allowed else "FROZEN"
    line2 = f"POSE: {recognized_pose.upper()}  |  ACTION: {mouse_state.upper()}  |  CURSOR: {ctrl_str}"
    cv2.putText(image, line2, (12, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1)

    # Line 3: System Status / Honest Feedback Message
    cv2.putText(image, f"STATUS: {status_message}", (12, 64), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 230, 255), 1)

    curr_y = 84
    # Line 4: Eye Telemetry (when eye tracking is active)
    if has_eye and eye_telemetry:
        f_stat = "DETECTED" if eye_telemetry.face_detected else "NO_FACE"
        eye_col = (0, 255, 0) if eye_telemetry.face_detected else (0, 165, 255)
        l_ear = getattr(eye_telemetry, "left_ear", eye_telemetry.ear)
        r_ear = getattr(eye_telemetry, "right_ear", eye_telemetry.ear)
        line_eye = (
            f"EYE: {f_stat} | L_EAR: {l_ear:.2f} R_EAR: {r_ear:.2f} (AVG: {eye_telemetry.ear:.2f}) | "
            f"L_BLINK: {eye_telemetry.left_blink:.2f} R_BLINK: {eye_telemetry.right_blink:.2f} | "
            f"STATE: {eye_telemetry.current_state} | SEQ: {eye_telemetry.sequence_count}"
        )
        cv2.putText(image, line_eye, (12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, eye_col, 1)
        curr_y += 20

        # Detailed blink diagnostic line
        rej = eye_telemetry.rejection_reason or "None"
        cool_s = getattr(eye_telemetry, "cooldown_remaining", 0.0)
        ear_c = getattr(eye_telemetry, "ear_closed_threshold", 0.18)
        ear_o = getattr(eye_telemetry, "ear_open_threshold", 0.22)
        bl_c = getattr(eye_telemetry, "blend_closed_threshold", 0.55)
        in_b = "YES" if getattr(eye_telemetry, "in_blink", False) else "NO"
        line_blink_diag = (
            f"BLINK DIAG: In-Blink: {in_b} | Cool: {cool_s:.2f}s | "
            f"Hysteresis(EAR: {ear_c:.2f}->{ear_o:.2f}, Blend: {bl_c:.2f}) | "
            f"Last: {eye_telemetry.last_action} | Status: {rej}"
        )
        cv2.putText(image, line_blink_diag, (12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (220, 220, 180), 1)
        curr_y += 18

    # Line 5: Voice Telemetry (when voice is active)
    if has_voice:
        line_voice = f"VOICE: {status_message}"
        cv2.putText(image, line_voice, (12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 200, 100), 1)
        curr_y += 18

    # Diagnostic Details
    if diagnostic_mode:
        line_keys = "KEYS: [E] Hand [I] Eye [B] Both [V] Voice [A] All [M] Arm/Disarm [T/Ctrl+Space] Talk | Space/X: E-STOP | [R] Reset | [Q] Quit"
        cv2.putText(image, line_keys, (12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 255), 1)
        curr_y += 18
        gate_status = "PERMITTED" if (master_armed and not estop_set) else "BLOCKED (DISARMED/ESTOP)"
        line_diag = f"DIAGNOSTIC OVERLAY: ON | Eye Latency: {getattr(eye_telemetry, 'latency_ms', 0.0):.1f}ms | Master Safety Gate: {gate_status}"
        cv2.putText(image, line_diag, (12, curr_y), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (180, 180, 180), 1)
