"""Multimodal Telemetry HUD and Diagnostic Dashboard Overlay."""
from __future__ import annotations

import cv2
import numpy as np
from typing import Any, Dict, Optional, Tuple


def draw_multimodal_hud(
    image: np.ndarray,
    mode: str,
    master_armed: bool,
    hand_status: str,
    eye_status: str,
    voice_status: str,
    hand_confidence: float,
    eye_confidence: float,
    voice_confidence: float,
    fps: float,
    latency_ms: float,
    last_action: str = "NONE",
    diagnostic_mode: bool = False,
    active_boundary: Optional[Tuple[float, float, float, float]] = None,
) -> None:
    """Renders a clean, highly informative multimodal interaction HUD."""
    h, w = image.shape[:2]

    # Optional active interaction region boundary
    if diagnostic_mode and active_boundary:
        ml, mr, mt, mb = active_boundary
        rx1, ry1 = int(ml * w), int(mt * h)
        rx2, ry2 = int((1.0 - mr) * w), int((1.0 - mb) * h)
        cv2.rectangle(image, (rx1, ry1), (rx2, ry2), (255, 140, 0), 1)
        cv2.putText(image, "ACTIVE MAPPING BOUNDARY", (rx1 + 4, ry1 + 14), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 140, 0), 1)

    # Top overlay banner
    banner_h = 110 if diagnostic_mode else 65
    overlay = image.copy()
    cv2.rectangle(overlay, (0, 0), (w, banner_h), (18, 18, 18), -1)
    cv2.addWeighted(overlay, 0.78, image, 0.22, 0, image)

    # Line 1: Mode & Master Arm Status
    arm_text = "ARMED" if master_armed else "DISARMED"
    arm_col = (0, 255, 0) if master_armed else (0, 165, 255)
    line1 = f"MODE: {mode.upper()}  |  MASTER: {arm_text}  |  FPS: {fps:.0f}  |  LATENCY: {latency_ms:.1f}ms"
    cv2.putText(image, line1, (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.52, arm_col, 2)

    # Line 2: Modality Statuses & Last Action
    h_col = (0, 255, 0) if "ACTIVE" in hand_status else (180, 180, 180)
    e_col = (0, 255, 0) if "ACTIVE" in eye_status else (180, 180, 180)
    v_col = (0, 255, 0) if "ACTIVE" in voice_status else (180, 180, 180)

    line2 = f"HAND: {hand_status} ({hand_confidence*100:.0f}%) | EYE: {eye_status} ({eye_confidence*100:.0f}%) | VOICE: {voice_status}"
    cv2.putText(image, line2, (12, 46), cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1)

    # Line 3 & 4: Diagnostics
    if diagnostic_mode:
        line3 = f"LAST ACTION: {last_action}  |  KEYS: [E] Hand [I] Eye [B] Both [V] Voice [A] All [M] Arm/Disarm"
        cv2.putText(image, line3, (12, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)
        line4 = "DIAGNOSTICS: ON ('d' toggle | 'c' calibrate | Space/X: E-STOP | 'r': Re-arm)"
        cv2.putText(image, line4, (12, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (180, 180, 180), 1)
