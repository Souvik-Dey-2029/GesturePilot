"""Typed, validated, JSON-serializable application configuration."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    """Raised for invalid or unknown configuration values."""


def _num(name: str, value: Any, lo: float, hi: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{name} must be a number, got {value!r}")
    if not (lo <= value <= hi):
        raise ConfigError(f"{name} must be within [{lo}, {hi}], got {value}")


@dataclass
class CameraConfig:
    device_index: int = 0
    width: int = 640
    height: int = 480
    fps: int = 30
    backend: str = "auto"  # auto | dshow | msmf
    max_read_failures: int = 30  # consecutive failed reads before the camera is declared dead

    def validate(self) -> None:
        _num("camera.device_index", self.device_index, 0, 32)
        _num("camera.width", self.width, 160, 3840)
        _num("camera.height", self.height, 120, 2160)
        _num("camera.fps", self.fps, 1, 120)
        _num("camera.max_read_failures", self.max_read_failures, 1, 10_000)
        if self.backend not in ("auto", "dshow", "msmf"):
            raise ConfigError(f"camera.backend must be auto|dshow|msmf, got {self.backend!r}")


@dataclass
class DetectorConfig:
    model_path: str = "models/hand_landmarker.task"
    num_hands: int = 1
    min_hand_detection_confidence: float = 0.5
    min_hand_presence_confidence: float = 0.5
    min_tracking_confidence: float = 0.5

    def validate(self) -> None:
        _num("detector.num_hands", self.num_hands, 1, 2)
        _num("detector.min_hand_detection_confidence", self.min_hand_detection_confidence, 0.0, 1.0)
        _num("detector.min_hand_presence_confidence", self.min_hand_presence_confidence, 0.0, 1.0)
        _num("detector.min_tracking_confidence", self.min_tracking_confidence, 0.0, 1.0)
        if not isinstance(self.model_path, str) or not self.model_path:
            raise ConfigError("detector.model_path must be a non-empty string")


@dataclass
class MappingConfig:
    """Active region = the part of the camera image that maps to the full screen (normalized margins)."""

    margin_left: float = 0.15
    margin_right: float = 0.15
    margin_top: float = 0.15
    margin_bottom: float = 0.20
    sensitivity: float = 1.0  # >1 amplifies motion about the region centre
    acceleration: float = 1.0  # non-linear response exponent: 1.0 = linear, 1.15 = subtle precision boost
    mirror_x: bool = True  # webcam image is a mirror of the user's view
    # Pixels kept between the cursor and each screen edge by the pipeline. 1 keeps the cursor off the four exact
    # corner pixels that PyAutoGUI's failsafe watches, so normal hand motion cannot trip it. 0 allows corners.
    corner_guard_px: int = 1

    def validate(self) -> None:
        for n in ("margin_left", "margin_right", "margin_top", "margin_bottom"):
            _num(f"mapping.{n}", getattr(self, n), 0.0, 0.45)
        _num("mapping.sensitivity", self.sensitivity, 0.25, 4.0)
        _num("mapping.acceleration", self.acceleration, 0.5, 3.0)
        _num("mapping.corner_guard_px", self.corner_guard_px, 0, 50)
        if not isinstance(self.mirror_x, bool):
            raise ConfigError("mapping.mirror_x must be a bool")


@dataclass
class SmoothingConfig:
    """One Euro filter applied in screen-pixel space with customizable tremor deadzone."""

    enabled: bool = True
    min_cutoff: float = 0.8  # Hz; lower = smoother at rest (reduced from 1.0 to eliminate stationary tremor)
    beta: float = 0.015  # speed coefficient; higher = less lag during fast motion
    d_cutoff: float = 1.0
    deadzone_radius_px: float = 2.5  # pixel tremor suppression radius around stationary cursor

    def validate(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigError("smoothing.enabled must be a bool")
        _num("smoothing.min_cutoff", self.min_cutoff, 0.01, 50.0)
        _num("smoothing.beta", self.beta, 0.0, 10.0)
        _num("smoothing.d_cutoff", self.d_cutoff, 0.01, 50.0)
        _num("smoothing.deadzone_radius_px", self.deadzone_radius_px, 0.0, 50.0)


@dataclass
class SafetyConfig:
    lost_hand_timeout_s: float = 0.25  # no good hand for this long -> tracking LOST
    min_hand_score: float = 0.6  # handedness score used as a proxy for detection quality
    recovery_frames: int = 3  # consecutive good frames needed to become RELIABLE again
    max_consecutive_detector_errors: int = 3  # detector exceptions in a row before an emergency stop

    def validate(self) -> None:
        _num("safety.lost_hand_timeout_s", self.lost_hand_timeout_s, 0.05, 10.0)
        _num("safety.min_hand_score", self.min_hand_score, 0.0, 1.0)
        _num("safety.recovery_frames", self.recovery_frames, 1, 120)
        _num("safety.max_consecutive_detector_errors", self.max_consecutive_detector_errors, 1, 1000)


from .gestures.config import GestureConfig

_SECTIONS: dict[str, type] = {
    "camera": CameraConfig,
    "detector": DetectorConfig,
    "mapping": MappingConfig,
    "smoothing": SmoothingConfig,
    "safety": SafetyConfig,
    "gestures": GestureConfig,
}


@dataclass
class AppConfig:
    camera: CameraConfig = field(default_factory=CameraConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    mapping: MappingConfig = field(default_factory=MappingConfig)
    smoothing: SmoothingConfig = field(default_factory=SmoothingConfig)
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    gestures: GestureConfig = field(default_factory=GestureConfig)

    def validate(self) -> None:
        for name in _SECTIONS:
            getattr(self, name).validate()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        if not isinstance(data, dict):
            raise ConfigError("config root must be a JSON object")
        unknown = set(data) - set(_SECTIONS)
        if unknown:
            raise ConfigError(f"unknown config sections: {sorted(unknown)}")
        kwargs: dict[str, Any] = {}
        for name, section_cls in _SECTIONS.items():
            raw = data.get(name, {})
            if not isinstance(raw, dict):
                raise ConfigError(f"config section {name!r} must be an object")
            allowed = {f.name for f in fields(section_cls)}
            bad = set(raw) - allowed
            if bad:
                raise ConfigError(f"unknown keys in {name!r}: {sorted(bad)}")
            kwargs[name] = section_cls(**raw)
        cfg = cls(**kwargs)
        cfg.validate()
        return cfg

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        """Load from JSON; a missing file yields defaults. Invalid content raises ConfigError."""
        p = Path(path)
        if not p.exists():
            cfg = cls()
            cfg.validate()
            return cfg
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"invalid JSON in {p}: {exc}") from exc
        return cls.from_dict(data)

    def save(self, path: str | Path) -> None:
        self.validate()
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
