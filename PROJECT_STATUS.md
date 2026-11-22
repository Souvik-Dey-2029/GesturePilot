# Project Status

**Current milestone:** 5 (Gesture Engine Redesign v005: Mutually Exclusive Interaction Vocabulary) — code complete, automated tests passing (111/111).
**Last handoff:** v005. Next milestone: Hardware testing & interactive desktop UI.

## Milestones
| # | Milestone | State |
|---|---|---|
| 1 | Research, architecture, repo structure | **Complete** |
| 2 | Webcam capture + hand landmark detection | Code complete. **User-verified on Windows in preview diagnostic**. |
| 3 | Coordinate mapping + virtual cursor | Code complete; fake-tested; audited; real PyAutoGUI exercised on Linux/Xvfb. **User-verified cursor movement on Windows 11 laptop**. |
| 4 | Click, drag, scroll, double-click, right-click | Code complete. Initial hardware testing revealed gesture overlap. |
| 5 | Gesture Engine Redesign (Mutually exclusive vocabulary) | **Code complete and tested** (111/111 tests pass). Ready for manual hardware validation. |

## Real hardware results (reported by the user; not independently verified by Claude)
Environment: Windows 11, **Python 3.13.7**, OpenCV 5.1.0, MediaPipe 1.2.3, NumPy 2.5.5, PyAutoGUI 0.9.54.
Laptop hardware: Intel Core i5 13th Gen, NVIDIA RTX 3050 6GB, 16GB RAM, 1920x1080 display, built-in webcam.
Hardware observations from prior sessions:
- Cursor movement: smooth.
- Peace-sign scrolling: worked, but suffered from mode overlap with pointing and clicking.
- Left & right pinch gestures: worked, but triggered accidental clicks when pointing or transitioning.
- Solution implemented in v005: discrete mutually exclusive hand poses with stationary click windows vs. intentional vertical motion scrolling, plus Open Palm pause.

## Session 3 audit and verification (software only)
* Source audit of the cursor path completed; **every mouse event passes through `MouseController` -> `SafetyController.can_emit()`**; enforced by new
  `tests/test_gate_enforcement.py`. Details in `ARCHITECTURE.md` ("Session 3 audit").
* Python 3.13 compatibility assessed beyond imports: 95/95 tests pass on Python 3.13.18 (Linux sandbox; user has 3.13.7 on Windows, same minor version) with the user's exact
  versions (mediapipe 1.2.3, numpy 2.5.5, opencv-contrib-python 5.1.0.95 [the wheel behind "OpenCV 5.1.0"], pyautogui 0.9.54); clean under
  `-W error::DeprecationWarning`; `cv2` calls used by the project (VideoCapture + CAP_* constants, imshow/waitKey/putText/cvtColor) exist in 5.1.0; real PyAutoGUI run on a virtual display.
  Remaining unknown: Windows-specific behaviour of PyAutoGUI (`SetCursorPos`, DPI), the real MediaPipe runtime inference on the sandbox (model host unreachable there; user's preview covers it).
* Defect fixed (docs): package not importable on a fresh venv without `pip install -e . --no-deps` or `PYTHONPATH=src`.
* No source code under `src/` changed. No tuning of smoothing/safety defaults was done (no evidence yet).

## Completed features
Config; types; logging; threaded camera; MediaPipe Tasks detector wrapper; model download helper; coordinate mapper; One Euro smoothing;
safety (e-stop latch, enable switch, tracking monitor, safe re-enable procedure); mouse backend protocol + PyAutoGUI/Fake backends;
safety-gated `MouseController`; cursor-only `Pipeline`; `python -m virtual_mouse` runner; preview diagnostic; tests; gate-enforcement tests; handoff builder; hardware test protocol.

## Partially completed / limitations by design
* Calibration: only config values (`mapping.margin_*`, `sensitivity`); no interactive calibration yet.
* Emergency stop: keyboard key in the runner window (needs focus; a physical click moves focus away) + PyAutoGUI corner failsafe + lowering the hand (tracking LOST after 0.25 s). No global hotkey yet.
* Primary monitor only.
* The runner's preview is the raw (unmirrored) camera image while the cursor mapping is mirrored: the drawn hand appears to move opposite to the real hand (cosmetic; pointer is correct).

## Pending
Real cursor test results (user). Then: gesture recognizer (pinch hysteresis, click debounce, drag, two-finger scroll); interactive calibration; global emergency hotkey
(ctypes `RegisterHotKey`); worker-thread pipeline + PySide6 UI; tuning of smoothing/safety defaults based on measured latency/jitter.

## Known bugs / risks
* Unverified on real hardware with cursor enabled: Win32 forced-release fallback, `dshow`/`msmf` explicit backends (auto works for the user), DPI behaviour, failsafe on Windows.
* `SetCursorPos` failures (elevated window, UAC, lock screen) are silent in PyAutoGUI: the pointer just does not move there.
* `HandObservation.score` is the handedness score (proxy for quality); the user saw 0.99 but it may be noisy under poor lighting.
* Default smoothing / safety numbers are untuned guesses; the cursor may feel laggy or jittery until tuned on evidence from the protocol.
* `tools/preview.py` uses a non-DPI-aware `GetSystemMetrics` for its *display-only* screen size; `run_cursor` uses PyAutoGUI's (DPI-aware) size.
* Model SHA-256 constant is third-party-reported (mismatch only warns).

## Exact next actions
1. **User:** follow `HARDWARE_TEST_PROTOCOL.md` (T0-T10) and paste the filled results template (section 6) into the next session.
2. Investigate any reported defect: identify the actual cause (triage table in the protocol) before changing code; smallest justified change + regression test; do not randomly change smoothing values.
3. Record the results in this file, accurately (only observed results count as verified).
4. Only after cursor validation: Milestone 4 gestures as pure functions on `HandObservation` (pinch with hysteresis, click debounce, hold-to-drag, two-finger scroll), feeding
   `Pipeline` -> `MouseController` (never bypass the gate). Then a global emergency hotkey and Milestone 5.

## Test summary
See `HANDOFF_MANIFEST.md` (generated from the real pytest run at build time).
