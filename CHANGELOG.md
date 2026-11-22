# Changelog

## 1.1.0 — Gesture Engine Redesign | v005 (2026-11-23)
### Added
- Redesigned mutually exclusive 6-gesture interaction vocabulary:
  1. `Open Palm` (5 fingers extended) -> `PAUSE` (freezes cursor, suppresses clicks and scrolling).
  2. `Index Finger Only` -> `POINTER MODE` (smooth cursor movement via One Euro filter and active interaction region).
  3. `Index + Middle` (2 fingers) -> `LEFT CLICK / SCROLL` (stationary hold for 0.22s triggers single left click; intentional vertical motion cancels click and enters continuous scrolling).
  4. `Index + Middle + Ring` (3 fingers) -> `RIGHT CLICK / SCROLL` (stationary hold for 0.22s triggers single right click; intentional vertical motion enters continuous scrolling).
  5. `Thumb + Index Pinch` -> `DOUBLE CLICK` (confirmed pinch triggers single double click with hysteresis release and cooldown).
  6. `Dynamic SCROLL MODE` -> Continuous vertical scrolling with cursor frozen; clean exit when returning to pointer or open palm.
- Enhanced geometric analysis in `gestures/geometry.py`:
  - `finger_extension_ratio` and strict extension/curled checks (`is_finger_extended_strict`, `is_finger_curled_strict`, `is_thumb_extended`).
- HUD overlay upgraded with live v005 telemetry:
  - Interaction state, recognized pose, cursor control status (`ACTIVE` vs `FROZEN`), scroll direction (`UP`, `DOWN`, `NONE`), stability percentage, rejection reason, and live FPS.
- 111 automated tests with 100% pass rate.

## 1.0.0 — Official Open-Source Release (2026-11-23)
### Added
- Standardized open-source packaging: `pyproject.toml` with console script entry points (`virtual-mouse`, `virtual-mouse-calibrate`, `virtual-mouse-preview`).
- Multi-tier documentation: `docs/USER_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`, `docs/TESTING.md`.
- Comprehensive open-source governance: `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `LICENSE`, `RELEASE_AUDIT.md`, `RELEASE_CHECKLIST.md`.
- GitHub Actions CI workflow for Python 3.11, 3.12, and 3.13 on Windows.
- Mutually exclusive gesture state machine with dedicated peace-sign scrolling and cursor freezing.
- Interactive calibration tool `src/virtual_mouse/tools/calibrate.py`.
- Diagnostic HUD overlay toggle (`d` key) showing live mode, pose classification, and rejection details.

## 0.4.0 — Session 4 (handoff v004)
### Added
* Gesture recognition module `src/virtual_mouse/gestures/`:
  - `geometry.py`: hand scale computation (wrist to middle MCP), 2D/3D Euclidean distance, normalized scale-invariant metrics.
  - `config.py`: typed, validated `GestureConfig` (pinch click threshold, hysteresis release threshold, drag hold time, double click interval, click cooldown, right-click thresholds, scroll speed/smoothing/deadzone).
  - `types.py`: enum state models (`PinchState`, `RightClickState`, `ScrollState`, `ActiveGesture`, `MouseActionType`), typed actions and metrics dataclasses.
  - `recognizer.py`: `GestureRecognizer` with state machine transitions, hysteresis, and explicit conflict resolution matrix.
* Two-finger scrolling (index + middle extended together, vertical delta mapping with deadzone and speed scaling).
* Pinch-to-left-click with hysteresis and cooldown.
* Pinch-and-hold to drag-and-drop with guaranteed button release on tracking loss, shutdown, or e-stop.
* Double-click detection with timing interval check.
* Right-click detection (thumb to middle-finger pinch with index held away).
* HUD visual feedback: top banner overlay showing system status, tracking state, FPS, active gesture, mouse state, and live normalized pinch metrics.
* 10 new automated unit and integration tests (105 total).
### Changed
* `Pipeline.step()` integrated with `GestureRecognizer` and maps abstract mouse actions to `MouseController`.
* Guaranteed button release and gesture reset on tracking loss (`TrackingState != RELIABLE` or `hand is None`).
* `AppConfig` updated with `gestures` section and validated defaults.
* `run_cursor.py` updated to render HUD with gesture status and metrics.
* `MouseController` added `scroll_wheel` method (with `scroll` alias).

## 0.3.0 — Session 3 (handoff v003)
### Added
* `HARDWARE_TEST_PROTOCOL.md`: controlled first real-cursor test (safety checklist, stop methods, T0-T10, triage table, results template).
* `tests/test_gate_enforcement.py` (8 tests): AST enforcement that only `MouseController` reaches the backend and that `pyautogui`/raw OS input stays in `mouse/`;
  behaviour test that every emitting method consults `can_emit()`. 95 tests total.
* `SESSION_SUMMARY.md`.
### Changed
* Documentation only: Python support stated as 3.11-3.13 (validated 3.13); setup now includes `pip install -e . --no-deps` (or `PYTHONPATH=src`) because the
  src-layout package was not importable on a fresh venv; user's real preview-level hardware results recorded; `scripts/build_handoff.py` manifest text updated.
### Unchanged
* No source code under `src/` was modified. Interfaces, defaults (smoothing, margins, safety thresholds) are untouched.
### Verified this session (software only)
* 95/95 tests pass on Python 3.13.18 / Linux with mediapipe 1.2.3, numpy 2.5.5, opencv-contrib-python 5.1.0.95, pyautogui 0.9.54; also clean with
  `-W error::DeprecationWarning`. Real PyAutoGUI exercised on a virtual X display. NOT run: real webcam, real model, Windows cursor.

## 0.2.0 — Session 2 (handoff v002)
### Added
* `mouse/` package: `MouseBackend` protocol, `PyAutoGUIBackend` (failsafe forced on, PAUSE=0, error translation, Win32 forced-release fallback),
  `FakeMouseBackend`, `MouseController` (the safety gate).
* `pipeline.py`: cursor-only `Pipeline` (step/run/open/close/request_stop), `StepReport`/`StepOutcome`, `build_pipeline`.
* `tools/run_cursor.py` and `python -m virtual_mouse` (starts disabled; keyboard enable / emergency stop / re-arm).
* `SafetyController.emergency_stop()` and `acknowledge_emergency_stop()`; `CoordinateMapper.screen_size`.
* Config: `mapping.corner_guard_px` (default 1), `safety.max_consecutive_detector_errors` (default 3). v001 config files remain valid.
* `pyautogui==0.9.54` added to `requirements.txt`.
* 38 new tests (87 total).
### Unchanged
* All v001 modules and public interfaces (additions only).
### Notes
* Still no real webcam, model file, Windows machine or real PyAutoGUI execution; see PROJECT_STATUS.md.

## 0.1.0 — Session 1 (handoff v001)
### Added
* Repository structure, `pyproject.toml`, requirements, `.gitignore`.
* `config`, `types`, `logging_setup`.
* `capture.camera.Camera` (threaded newest-frame capture, error surfacing, guaranteed release).
* `detection.hand_detector.HandDetector` (MediaPipe Tasks, VIDEO mode) and `detection.model_assets` (atomic download helper).
* `mapping.coordinates.CoordinateMapper` and `mapping.smoothing` (One Euro).
* `safety` (EmergencyStop, TrackingMonitor, SafetyController).
* `tools.preview` diagnostic (no mouse control) and `tools.visualization`.
* Pytest suite and `scripts/build_handoff.py`.
* Continuity documents.
### Notes
* No real webcam, model file or Windows environment was available; see PROJECT_STATUS.md.
