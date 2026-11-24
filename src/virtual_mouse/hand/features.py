"""Enhanced hand feature extraction and palm-relative normalization."""
from __future__ import annotations

import math
from dataclasses import dataclass
from ..types import HandObservation, Landmark, LandmarkId


@dataclass(frozen=True, slots=True)
class HandFeatures:
    scale: float
    palm_width: float
    is_left: bool
    confidence: float
    wrist: Landmark
    index_tip: Landmark
    thumb_tip: Landmark
    middle_tip: Landmark
    ring_tip: Landmark
    pinky_tip: Landmark
    thumb_index_dist: float
    thumb_middle_dist: float
    index_middle_dist: float
    index_extended: bool
    middle_extended: bool
    ring_extended: bool
    pinky_extended: bool
    thumb_extended: bool


def extract_hand_features(hand: HandObservation, scale_override: float | None = None) -> HandFeatures:
    """Computes a rich, palm-normalized feature representation from 21 landmarks."""
    wrist = hand.point(LandmarkId.WRIST)
    middle_mcp = hand.point(LandmarkId.MIDDLE_MCP)
    index_mcp = hand.point(LandmarkId.INDEX_MCP)
    pinky_mcp = hand.point(LandmarkId.PINKY_MCP)

    # Scale: Wrist to Middle MCP (anatomical hand size reference)
    scale = scale_override or max(math.hypot(wrist.x - middle_mcp.x, wrist.y - middle_mcp.y), 0.01)
    palm_width = max(math.hypot(index_mcp.x - pinky_mcp.x, index_mcp.y - pinky_mcp.y), 0.01)

    t_tip = hand.point(LandmarkId.THUMB_TIP)
    i_tip = hand.point(LandmarkId.INDEX_TIP)
    m_tip = hand.point(LandmarkId.MIDDLE_TIP)
    r_tip = hand.point(LandmarkId.RING_TIP)
    p_tip = hand.point(LandmarkId.PINKY_TIP)

    i_pip = hand.point(LandmarkId.INDEX_PIP)
    m_pip = hand.point(LandmarkId.MIDDLE_PIP)
    r_pip = hand.point(LandmarkId.RING_PIP)
    p_pip = hand.point(LandmarkId.PINKY_PIP)
    t_ip = hand.point(LandmarkId.THUMB_IP)

    # Distances normalized by hand scale
    def dist(p1: Landmark, p2: Landmark) -> float:
        return math.hypot(p1.x - p2.x, p1.y - p2.y) / scale

    # Finger extension ratio: d(tip, wrist) / d(pip, wrist)
    def is_ext(tip: Landmark, pip: Landmark, min_r: float = 1.10) -> bool:
        d_tip = math.hypot(tip.x - wrist.x, tip.y - wrist.y)
        d_pip = math.hypot(pip.x - wrist.x, pip.y - wrist.y)
        return (d_tip / max(d_pip, 0.001)) >= min_r

    t_ext = (math.hypot(t_tip.x - wrist.x, t_tip.y - wrist.y) / max(math.hypot(t_ip.x - wrist.x, t_ip.y - wrist.y), 0.001)) >= 1.08

    return HandFeatures(
        scale=scale,
        palm_width=palm_width,
        is_left=hand.handedness.lower() == "left",
        confidence=hand.score,
        wrist=wrist,
        index_tip=i_tip,
        thumb_tip=t_tip,
        middle_tip=m_tip,
        ring_tip=r_tip,
        pinky_tip=p_tip,
        thumb_index_dist=dist(t_tip, i_tip),
        thumb_middle_dist=dist(t_tip, m_tip),
        index_middle_dist=dist(i_tip, m_tip),
        index_extended=is_ext(i_tip, i_pip),
        middle_extended=is_ext(m_tip, m_pip),
        ring_extended=is_ext(r_tip, r_pip),
        pinky_extended=is_ext(p_tip, p_pip),
        thumb_extended=t_ext,
    )
