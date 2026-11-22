"""Geometric analysis, finger pose estimation, and scale computation for v005."""
from __future__ import annotations

import math
from ..types import HandObservation, Landmark, LandmarkId


def euclidean_dist_2d(p1: Landmark, p2: Landmark) -> float:
    """Euclidean distance in normalized (x, y) coordinates."""
    dx = p1.x - p2.x
    dy = p1.y - p2.y
    return math.hypot(dx, dy)


def euclidean_dist_3d(p1: Landmark, p2: Landmark) -> float:
    """Euclidean distance in normalized landmark coordinates (x, y, z)."""
    dx = p1.x - p2.x
    dy = p1.y - p2.y
    dz = p1.z - p2.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def compute_hand_scale(hand: HandObservation) -> float:
    """Stable reference scale of the hand to normalize distance metrics across hand-camera distances.
    
    Uses distance from WRIST (0) to MIDDLE_MCP (9).
    """
    wrist = hand.point(LandmarkId.WRIST)
    middle_mcp = hand.point(LandmarkId.MIDDLE_MCP)
    scale = euclidean_dist_2d(wrist, middle_mcp)
    return max(scale, 0.01)


def normalized_distance(p1: Landmark, p2: Landmark, scale: float) -> float:
    """Distance between two landmarks normalized by hand scale."""
    return euclidean_dist_2d(p1, p2) / max(scale, 0.01)


def finger_extension_ratio(hand: HandObservation, tip_id: LandmarkId, pip_id: LandmarkId) -> float:
    """Calculates the ratio of (tip to wrist distance) over (pip to wrist distance).
    
    A fully extended finger typically has ratio >= 1.10.
    A curled finger typically has ratio <= 1.05.
    """
    wrist = hand.point(LandmarkId.WRIST)
    tip = hand.point(tip_id)
    pip = hand.point(pip_id)
    d_tip_wrist = euclidean_dist_2d(tip, wrist)
    d_pip_wrist = euclidean_dist_2d(pip, wrist)
    if d_pip_wrist <= 0.001:
        return 1.0
    return d_tip_wrist / d_pip_wrist


def is_finger_extended_strict(hand: HandObservation, tip_id: LandmarkId, pip_id: LandmarkId, min_ratio: float = 1.10) -> bool:
    """Check if finger is extended using wrist distance ratio."""
    ratio = finger_extension_ratio(hand, tip_id, pip_id)
    return ratio >= min_ratio


def is_finger_curled_strict(hand: HandObservation, tip_id: LandmarkId, pip_id: LandmarkId, max_ratio: float = 1.05) -> bool:
    """Check if finger is curled (bent inward toward palm or wrist)."""
    ratio = finger_extension_ratio(hand, tip_id, pip_id)
    return ratio <= max_ratio


def is_thumb_extended(hand: HandObservation, min_ratio: float = 1.08) -> bool:
    """Check if thumb is extended relative to thumb CMC joint (wrist)."""
    wrist = hand.point(LandmarkId.WRIST)
    tip = hand.point(LandmarkId.THUMB_TIP)
    ip = hand.point(LandmarkId.THUMB_IP)
    d_tip = euclidean_dist_2d(tip, wrist)
    d_ip = euclidean_dist_2d(ip, wrist)
    if d_ip <= 0.001:
        return True
    return (d_tip / d_ip) >= min_ratio
