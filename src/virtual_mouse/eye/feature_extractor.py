"""Mathematically sound Eye Feature Extraction layer.

Computes Eye Aspect Ratio (EAR) using canonical MediaPipe 468/478 landmark indices,
extracts facial blendshapes, evaluates bilateral eye symmetry, and produces
structured EyeFeatureObservation per frame.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# Canonical 6-point MediaPipe eye landmark indices:
# Soukupova and Cech (2016): EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
# Note: In MediaPipe 468/478 mesh:
# Left Eye (anatomical subject's left):
#   p1: 362 (outer corner / lateral canthus)
#   p2: 385 (superior lateral)
#   p3: 387 (superior medial)
#   p4: 263 (inner corner / medial canthus)
#   p5: 373 (inferior medial)
#   p6: 380 (inferior lateral)
# Right Eye (anatomical subject's right):
#   p1: 33  (outer corner / lateral canthus)
#   p2: 160 (superior lateral)
#   p3: 158 (superior medial)
#   p4: 133 (inner corner / medial canthus)
#   p5: 153 (inferior medial)
#   p6: 144 (inferior lateral)

LEFT_EYE_INDICES = (362, 385, 387, 263, 373, 380)
RIGHT_EYE_INDICES = (33, 160, 158, 133, 153, 144)


@dataclass(frozen=True, slots=True)
class EyeFeatureObservation:
    """Structured feature observation for a single video frame."""
    ear_left: float
    ear_right: float
    ear_avg: float
    blink_left: float
    blink_right: float
    blink_avg: float
    squint_left: float
    squint_right: float
    wide_left: float
    wide_right: float
    symmetry_ear: float        # abs(ear_l - ear_r)
    symmetry_blink: float      # abs(blink_l - blink_r)
    face_detected: bool
    tracking_confidence: float
    landmarks_valid: bool
    timestamp: float
    latency_ms: float = 0.0


def calculate_ear_6pts(
    landmarks: Tuple[Tuple[float, float, float], ...] | list[Tuple[float, float, float]],
    indices: Tuple[int, int, int, int, int, int],
) -> float:
    """Calculates EAR from 6 landmarks: p1 (corner), p2, p3 (top), p4 (corner), p5, p6 (bottom).
    
    EAR = (||p2-p6|| + ||p3-p5||) / (2 * ||p1-p4||)
    """
    if len(landmarks) < max(indices) + 1:
        return 0.0

    p1 = landmarks[indices[0]]
    p2 = landmarks[indices[1]]
    p3 = landmarks[indices[2]]
    p4 = landmarks[indices[3]]
    p5 = landmarks[indices[4]]
    p6 = landmarks[indices[5]]

    # Horizontal distance (eye width)
    w = math.hypot(p1[0] - p4[0], p1[1] - p4[1])
    if w <= 1e-6:
        return 0.0

    # Vertical distances (eye height)
    h1 = math.hypot(p2[0] - p6[0], p2[1] - p6[1])
    h2 = math.hypot(p3[0] - p5[0], p3[1] - p5[1])

    return (h1 + h2) / (2.0 * w)


class EyeFeatureExtractor:
    """Extracts EAR and blendshape metrics from normalized landmarks and blendshapes."""

    def extract(
        self,
        landmarks: Tuple[Tuple[float, float, float], ...] | None,
        blendshapes: Dict[str, float] | None,
        confidence: float = 0.95,
        timestamp: float = 0.0,
        latency_ms: float = 0.0,
    ) -> EyeFeatureObservation:
        if landmarks is None or len(landmarks) < 468:
            # Fallback when landmarks are missing or tracking lost
            blend_dict = blendshapes or {}
            bl_l = float(blend_dict.get("eyeBlinkLeft", 0.0))
            bl_r = float(blend_dict.get("eyeBlinkRight", 0.0))
            bl_avg = (bl_l + bl_r) / 2.0
            # Synthetic EAR approximation from blendshape if face present without dense landmarks
            ear_approx = max(0.05, 0.28 * (1.0 - bl_avg))
            return EyeFeatureObservation(
                ear_left=ear_approx,
                ear_right=ear_approx,
                ear_avg=ear_approx,
                blink_left=bl_l,
                blink_right=bl_r,
                blink_avg=bl_avg,
                squint_left=float(blend_dict.get("eyeSquintLeft", 0.0)),
                squint_right=float(blend_dict.get("eyeSquintRight", 0.0)),
                wide_left=float(blend_dict.get("eyeWideLeft", 0.0)),
                wide_right=float(blend_dict.get("eyeWideRight", 0.0)),
                symmetry_ear=0.0,
                symmetry_blink=abs(bl_l - bl_r),
                face_detected=bool(landmarks is not None or blendshapes),
                tracking_confidence=confidence if landmarks is not None else 0.0,
                landmarks_valid=False,
                timestamp=timestamp,
                latency_ms=latency_ms,
            )

        # Calculate geometric EAR
        ear_l = calculate_ear_6pts(landmarks, LEFT_EYE_INDICES)
        ear_r = calculate_ear_6pts(landmarks, RIGHT_EYE_INDICES)
        ear_avg = (ear_l + ear_r) / 2.0

        # Extract blendshapes
        b = blendshapes or {}
        bl_l = float(b.get("eyeBlinkLeft", 0.0))
        bl_r = float(b.get("eyeBlinkRight", 0.0))
        bl_avg = (bl_l + bl_r) / 2.0

        sq_l = float(b.get("eyeSquintLeft", 0.0))
        sq_r = float(b.get("eyeSquintRight", 0.0))
        wd_l = float(b.get("eyeWideLeft", 0.0))
        wd_r = float(b.get("eyeWideRight", 0.0))

        return EyeFeatureObservation(
            ear_left=ear_l,
            ear_right=ear_r,
            ear_avg=ear_avg,
            blink_left=bl_l,
            blink_right=bl_r,
            blink_avg=bl_avg,
            squint_left=sq_l,
            squint_right=sq_r,
            wide_left=wd_l,
            wide_right=wd_r,
            symmetry_ear=abs(ear_l - ear_r),
            symmetry_blink=abs(bl_l - bl_r),
            face_detected=True,
            tracking_confidence=confidence,
            landmarks_valid=(ear_l > 0.0 and ear_r > 0.0),
            timestamp=timestamp,
            latency_ms=latency_ms,
        )
