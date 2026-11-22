import json

from virtual_mouse.tools import run_cursor


def test_invalid_config_exits_2_without_touching_hardware(tmp_path):
    bad = tmp_path / "c.json"
    bad.write_text(json.dumps({"camera": {"backend": "nope"}}))
    assert run_cursor.main(["--config", str(bad)]) == 2


def test_pyautogui_unavailable_exits_2(tmp_path, monkeypatch):
    import importlib

    monkeypatch.setattr(importlib, "import_module", lambda name: (_ for _ in ()).throw(KeyError("DISPLAY")))
    assert run_cursor.main(["--config", str(tmp_path / "missing.json")]) == 2
