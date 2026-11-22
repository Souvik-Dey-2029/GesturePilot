# Handoff Manifest

* **Handoff version:** v005
* **Built (UTC):** 2026-11-22 22:13
* **Build environment:** Python 3.13.7 on Windows (project supports Python 3.11-3.13; user hardware: Windows 11, Python 3.13.7)

## Test results (actually executed at build time)
* Command: `python -m pytest -q`  -> exit code 0
* Result line: `111 passed in 2.83s`

```
........................................................................ [ 64%]
.......................................                                  [100%]
111 passed in 2.83s
```

Categories:
* **Executed:** the pytest suite above: config, types, mapping, smoothing, safety, camera (fake capture), detector (fake landmarker),
  model helper (fake downloader), drawing helper, MediaPipe API-surface check, mouse backends (fake + PyAutoGUIBackend against an injected fake module),
  MouseController gate, gate-enforcement (AST scan of all source), Pipeline (fake camera/detector/mouse), runner start-up error paths.
* **Executed outside the suite (session 3, Linux, not part of this build):** real PyAutoGUI 0.9.54 on a virtual X11 display through `PyAutoGUIBackend`
  and a full pipeline simulation with fake camera/detector. See `ARCHITECTURE.md` ("Session 3 audit").
* **Static inspection only:** main loop of `tools/run_cursor.py`, Win32 forced-release fallback, PyAutoGUI's Windows code (`SetCursorPos`, DPI awareness; read, not run).
* **User-reported (Windows 11, Python 3.13.7), not independently verified:** webcam opens, real model loads, landmarks track smoothly, ~24 FPS, score ~0.99 (preview).
* **NOT yet done (requires the user's Windows machine):** real Windows cursor movement, failsafe on Windows, tracking/latency/jitter feel with the cursor enabled
  (see `HARDWARE_TEST_PROTOCOL.md`).

## Dependency information
See `requirements.txt` (runtime) and `requirements-dev.txt` (adds pytest). `pyautogui` is used by `PyAutoGUIBackend` (lazy import); `PySide6` is planned, not yet imported.
Model asset `models/hand_landmarker.task` is NOT included (download with `python -m virtual_mouse.tools.preview --download-model`).
Install the package with `pip install -e . --no-deps` (or set `PYTHONPATH=src`) before using `python -m virtual_mouse`.

## Excluded from the ZIP
Virtual environments, `__pycache__`/`.pytest_cache`, `*.pyc`, `*.zip`, `*.task` model files, logs, `.env*`, keys/certificates, `dist/`, `.git`.
No credentials or personal data are included.

## Known limitations
See `PROJECT_STATUS.md` ("Known bugs / risks"). In short: the cursor-enabled path has not been run on real Windows hardware yet.

## Project structure / files included
```
.editorconfig
.gitattributes
.github/workflows/ci.yml
.gitignore
ARCHITECTURE.md
CHANGELOG.md
CODE_OF_CONDUCT.md
config/config.example.json
CONTRIBUTING.md
docs/ARCHITECTURE.md
docs/DEVELOPMENT.md
docs/TESTING.md
docs/USER_GUIDE.md
HANDOFF_MANIFEST.md
HARDWARE_TEST_PROTOCOL.md
models/.gitkeep
NEXT_SESSION_PROMPT.md
PROJECT_STATUS.md
pyproject.toml
README.md
RELEASE_AUDIT.md
RELEASE_CHECKLIST.md
requirements-dev.txt
requirements.txt
scripts/build_handoff.py
SECURITY.md
SESSION_SUMMARY.md
src/virtual_mouse/__init__.py
src/virtual_mouse/__main__.py
src/virtual_mouse/capture/__init__.py
src/virtual_mouse/capture/camera.py
src/virtual_mouse/config.py
src/virtual_mouse/detection/__init__.py
src/virtual_mouse/detection/hand_detector.py
src/virtual_mouse/detection/model_assets.py
src/virtual_mouse/gestures/__init__.py
src/virtual_mouse/gestures/config.py
src/virtual_mouse/gestures/geometry.py
src/virtual_mouse/gestures/recognizer.py
src/virtual_mouse/gestures/types.py
src/virtual_mouse/logging_setup.py
src/virtual_mouse/mapping/__init__.py
src/virtual_mouse/mapping/coordinates.py
src/virtual_mouse/mapping/smoothing.py
src/virtual_mouse/mouse/__init__.py
src/virtual_mouse/mouse/backend.py
src/virtual_mouse/mouse/controller.py
src/virtual_mouse/pipeline.py
src/virtual_mouse/safety.py
src/virtual_mouse/tools/__init__.py
src/virtual_mouse/tools/calibrate.py
src/virtual_mouse/tools/preview.py
src/virtual_mouse/tools/run_cursor.py
src/virtual_mouse/tools/visualization.py
src/virtual_mouse/types.py
src/virtual_mouse.egg-info/dependency_links.txt
src/virtual_mouse.egg-info/entry_points.txt
src/virtual_mouse.egg-info/PKG-INFO
src/virtual_mouse.egg-info/requires.txt
src/virtual_mouse.egg-info/SOURCES.txt
src/virtual_mouse.egg-info/top_level.txt
tests/conftest.py
tests/test_camera.py
tests/test_config.py
tests/test_detector.py
tests/test_gate_enforcement.py
tests/test_gestures.py
tests/test_mapping.py
tests/test_mediapipe_api_surface.py
tests/test_model_assets.py
tests/test_mouse_backend.py
tests/test_mouse_controller.py
tests/test_pipeline.py
tests/test_run_cursor.py
tests/test_safety.py
tests/test_smoothing.py
tests/test_types.py
tests/test_visualization.py
```
