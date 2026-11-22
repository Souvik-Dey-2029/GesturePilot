import json

import pytest

from virtual_mouse.config import AppConfig, ConfigError


def test_defaults_valid_and_roundtrip(tmp_path):
    cfg = AppConfig()
    cfg.validate()
    p = tmp_path / "c.json"
    cfg.save(p)
    assert AppConfig.load(p) == cfg


def test_missing_file_gives_defaults(tmp_path):
    assert AppConfig.load(tmp_path / "nope.json") == AppConfig()


def test_partial_override(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"mapping": {"sensitivity": 2.0}}))
    cfg = AppConfig.load(p)
    assert cfg.mapping.sensitivity == 2.0 and cfg.camera.width == 640


@pytest.mark.parametrize(
    "data",
    [
        {"bogus": {}},
        {"camera": {"nope": 1}},
        {"camera": {"backend": "v4l"}},
        {"mapping": {"sensitivity": 100}},
        {"mapping": {"margin_left": "x"}},
        {"safety": {"min_hand_score": 2}},
        {"camera": 5},
    ],
)
def test_invalid_rejected(data):
    with pytest.raises(ConfigError):
        AppConfig.from_dict(data)


def test_invalid_json(tmp_path):
    p = tmp_path / "c.json"
    p.write_text("{not json")
    with pytest.raises(ConfigError):
        AppConfig.load(p)


def test_milestone3_fields_defaults_and_validation():
    cfg = AppConfig()
    assert cfg.mapping.corner_guard_px == 1 and cfg.safety.max_consecutive_detector_errors == 3
    with pytest.raises(ConfigError):
        AppConfig.from_dict({"mapping": {"corner_guard_px": -1}})
    with pytest.raises(ConfigError):
        AppConfig.from_dict({"safety": {"max_consecutive_detector_errors": 0}})
    # a v001-style config without the new keys still loads (backward compatible)
    assert AppConfig.from_dict({"mapping": {"sensitivity": 1.5}}).mapping.corner_guard_px == 1


def test_overhaul_fields_defaults_and_validation():
    cfg = AppConfig()
    assert cfg.smoothing.deadzone_radius_px == 2.5
    assert cfg.mapping.acceleration == 1.0
    with pytest.raises(ConfigError):
        AppConfig.from_dict({"smoothing": {"deadzone_radius_px": -1.0}})
    with pytest.raises(ConfigError):
        AppConfig.from_dict({"mapping": {"acceleration": 0.1}})

