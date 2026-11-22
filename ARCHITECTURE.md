# Architecture

## Data flow (target design)

```
Camera (thread) --CapturedFrame--> HandDetector --FrameResult--> [Pipeline thread]
                                                                   |-> SafetyController.update(hand, now)
                                                                   |-> CoordinateMapper.map(index tip)
                                                                   |-> PointFilter (One Euro, screen px)
                                                                   |-> GestureRecognizer (M4)  -> events
                                                                   '-> MouseController (M3/M4) -- only if can_emit()
Desktop UI (PySide6, M5) <-> SafetyController / AppConfig / status signals
```

Implemented: `Camera`, `HandDetector`, `CoordinateMapper`, `PointFilter`, `SafetyController`, `AppConfig`, logging, preview tool (session 1);
`MouseBackend`/`PyAutoGUIBackend`/`FakeMouseBackend`, `MouseController` (safety gate), `Pipeline` (cursor only), `run_cursor` (session 2).
Not yet implemented: gesture recognition (click/drag/scroll), calibration, global hotkey, UI. The pipeline currently runs on the caller's thread
(`run_cursor` calls `Pipeline.run`); Milestone 5 will move it to a worker thread.

## Modules and responsibilities

| Module | Responsibility | Status |
|---|---|---|
| `config.py` | Typed dataclasses, strict JSON load/validate/save | done, tested |
| `types.py` | `Landmark`, `HandObservation`, `CapturedFrame`, `FrameResult`, `ScreenPoint`, `LandmarkId` | done, tested |
| `capture/camera.py` | Grab thread, newest-frame-only, error surfacing, guaranteed release | done, tested with fake capture |
| `detection/hand_detector.py` | MediaPipe Tasks `HandLandmarker` (VIDEO mode), result conversion, monotonic timestamps | done, tested with fakes; real model untested |
| `detection/model_assets.py` | Model path/download (atomic), optional hash check | done, tested offline |
| `mapping/coordinates.py` | Active region, mirror, sensitivity, clamp -> screen px | done, tested |
| `mapping/smoothing.py` | One Euro filter | done, tested |
| `safety.py` | `EmergencyStop` latch, `TrackingMonitor`, `SafetyController` (+ `emergency_stop`, `acknowledge_emergency_stop`) | done, tested |
| `tools/preview.py` | Webcam/landmark diagnostic, no mouse | done, **hardware-untested** |
| `mouse/backend.py` | `MouseBackend` protocol (screen_size, move_to, left_down/up, right_click, scroll), `PyAutoGUIBackend`, `FakeMouseBackend` | done; fake + injected-module tests; **real PyAutoGUI/Windows untested** |
| `mouse/controller.py` | `MouseController`: the only caller of a backend; applies `can_emit()` under a lock; releases buttons on e-stop; backend failure/failsafe -> e-stop | done, tested |
| `pipeline.py` | `Pipeline.step/run/open/close`, `StepReport`, `build_pipeline` | done, tested with fakes |
| `tools/run_cursor.py` | keyboard-controlled runner (`python -m virtual_mouse`) | done, tested with HUD feedback |
| `gestures` (M4) | pinch w/ hysteresis, drag, double-click, two-finger scroll, right-click | done, tested (isolated + pipeline) |
| ui (M5) | PySide6 window, calibration, enable/disable, status | pending |

## Verified research (session 1)

* MediaPipe's current Python API is the **Tasks API**: `mp.tasks.vision.HandLandmarker`, `HandLandmarkerOptions`,
  `RunningMode.{IMAGE,VIDEO,LIVE_STREAM}`, `detect_for_video(mp_image, timestamp_ms)`. Model needed: `hand_landmarker.task`
  (palm detector + landmark model). Source: Google AI Edge docs (developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python).
* Verified by import/introspection in the sandbox: mediapipe **0.10.33** (Python 3.12) and **1.2.3** (isolated venv) both expose these
  names and the same `HandLandmarkerOptions` signature; `mp.solutions` is absent in 1.2.3 (legacy API gone). Neither run loaded a model.
* mediapipe depends on `opencv-contrib-python`, so that is the only cv2 package in `requirements.txt`.
* Model URL: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`.
  **Not reachable from the build sandbox, so the download was never tested here.** The SHA-256 in `model_assets.py` comes from a
  third-party source and only triggers a warning on mismatch.
* Not verified: Python 3.11 specifically (sandbox is 3.12.3; code avoids 3.12-only syntax), Windows behaviour, PyAutoGUI, PySide6.

## Milestone 3 design (session 2)

**PyAutoGUI 0.9.54 facts, read from its source (sdist), not executed:**
* `FAILSAFE_POINTS` contains **all four screen corners** (set at import), and `failSafeCheck()` runs *before every* mouse call and raises
  `FailSafeException` if the cursor is on one of those exact pixels.
* `PAUSE` defaults to 0.1 s after every call (would cap the cursor near 10 Hz) and `_pause=False` skips it. We set `PAUSE=0` and pass
  `_pause=False`; the failsafe check is unaffected and `FAILSAFE` is forced `True` in `PyAutoGUIBackend.__init__`.
* The Windows backend calls `SetProcessDPIAware()` and `size()` returns the **primary** monitor's size, hence primary-monitor-only support.

**Decisions**
11. **One gate.** `MouseController` is the only object that calls a backend. Every emitting call checks `SafetyController.can_emit()` under an RLock.
    Releasing a held button is deliberately *ungated* (releasing is the safe direction) and is done on every e-stop and on `Pipeline.close()`.
12. **Failsafe vs. hand motion.** Because every corner is a failsafe point, a hand at the edge of the active region would put the cursor on a corner and
    trip the failsafe on the next call. `MappingConfig.corner_guard_px` (default 1) keeps the pipeline's targets 1 px inside every edge. The failsafe
    stays enabled and remains an escape hatch for the *physical* mouse. Set it to 0 to let the finger reach corners (and trip the failsafe).
13. **Stuck-button protection.** The failsafe check would also block `mouseUp` when the cursor sits on a corner. `PyAutoGUIBackend.left_up()` falls back to a
    Win32 `mouse_event(MOUSEEVENTF_LEFTUP)` in that case. This only releases and never disables the failsafe. Windows-only, untested.
14. **Emergency stop semantics.** `SafetyController.emergency_stop()` disables first, then latches and runs listeners (release buttons). Re-enable is
    two explicit steps: `acknowledge_emergency_stop()` (stays disabled) then `enable()`, after which tracking must be RELIABLE again (`recovery_frames` good frames).
    Camera failure, repeated detector failure (`safety.max_consecutive_detector_errors`), backend failure and PyAutoGUI failsafe all latch an emergency stop.
15. **Smoothing reset.** The filter is reset whenever tracking is not RELIABLE (acquiring/lost, camera stall, detector error), so the first cursor position after
    recovery is the raw mapped point instead of a glide from a stale position. Verified by `test_tracking_loss_resets_smoothing_...`.
16. **Frame timing.** Smoothing uses capture timestamps (`frame.timestamp_ms`); safety timeouts use an injectable monotonic clock. Both use the same time base in production.
17. **Keyboard control** in `run_cursor` works only while its OpenCV window has focus. A global emergency hotkey (ctypes `RegisterHotKey`) is still pending.

## Session 3 audit (cursor path; no architecture change)

Audit of `pipeline.py`, `mouse/backend.py`, `mouse/controller.py`, `safety.py`, `tools/run_cursor.py`, `__main__.py`, `mapping/coordinates.py`:

* **Gate verified.** The only call site of a mouse method outside `mouse/` is `Pipeline.step` -> `self._mouse.move_to` (plus `release_all` on close); inside
  `mouse/` only `MouseController` touches `self._backend`; `PyAutoGUIBackend` is constructed only in `build_pipeline`; `pyautogui` is imported only by
  `mouse/backend.py`. Every emitting `MouseController` method calls `SafetyController.can_emit()` under the lock. Enforced by `tests/test_gate_enforcement.py`
  (AST scan + behaviour; mutation-checked: injecting a bypass makes it fail).
* **Real PyAutoGUI 0.9.54 on Python 3.13** was exercised on a virtual X11 display (Linux, not Windows): `PAUSE=0`/`_pause=False` accepted, failsafe raises at the
  four corners and is translated into an emergency stop through the gate, 200 consecutive moves in 56 ms (no artificial per-call pause), disabled/acquiring states emit nothing.
* **Full-pipeline simulation** (fake camera and detector, real PyAutoGUIBackend, default config): mirror direction, vertical mapping, edge clamping to 1 px inside
  every corner (no failsafe trip even at extreme hand positions), brief dropout holds position, long absence -> LOST -> recovery after `recovery_frames`
  with first position raw (no glide), disable and emergency stop both stop movement, e-stop blocks `enable()` until `acknowledge`.
* **Windows backend facts read from PyAutoGUI source:** `SetProcessDPIAware()` at import; `size()` = `GetSystemMetrics(0/1)` (physical primary-monitor pixels);
  `moveTo` -> `SetCursorPos` with the return value ignored (a refused move, e.g. over an elevated window, is silent). Coordinates are consistent for the primary monitor.
* **Operational findings (not code defects):** (1) the preview is the raw, unmirrored camera image while the mapper mirrors X, so on screen the drawn hand
  moves opposite to the real hand but the pointer follows the real hand; (2) keyboard controls need window focus and a physical click moves focus away,
  so the protocol tells the user not to click and lists focus-independent stops (lower the hand, corner failsafe, Ctrl+C). A global hotkey remains pending.
* **Defect found and fixed (documentation):** the documented `python -m virtual_mouse` commands fail on a fresh venv with `No module named virtual_mouse`
  (src layout, package not installed). README/protocol now include `pip install -e . --no-deps` (verified) or `PYTHONPATH=src`.

## Key decisions and reasoning

1. **Tasks API, VIDEO mode, synchronous.** Camera frames are already decoupled by the grab thread, so a blocking
   `detect_for_video` on a single pipeline thread gives ordered results without LIVE_STREAM callback races. Slow inference simply
   drops stale frames (the camera keeps only the newest), which is the right latency behaviour for a cursor.
2. **Newest-frame-only camera.** A queue would add latency under load; one slot + condition variable bounds latency and memory.
3. **Strictly increasing timestamps.** MediaPipe VIDEO mode requires monotonic timestamps; both `Camera` and `HandDetector` enforce it.
4. **Mirror in the mapper, not the camera.** Landmarks stay in true camera coordinates; the mirror is one boolean applied once.
5. **Smoothing in screen-pixel space** with the One Euro filter: adaptive cutoff removes rest jitter yet limits lag on fast motion.
   Default parameters are initial guesses and need tuning on real hardware.
6. **Detection quality proxy.** MediaPipe's result exposes no hand-presence score, so `HandObservation.score` is the handedness
   classification score and `safety.min_hand_score` thresholds it. Revisit if it proves noisy.
7. **Safety by construction.** One predicate, `SafetyController.can_emit()`, must gate every OS mouse call. Starts disabled; emergency stop is a
   latch with listeners (the future mouse controller will release held buttons on trigger). PyAutoGUI failsafe is never disabled.
8. **Planned emergency hotkey:** a global hotkey via `ctypes` `RegisterHotKey` (no extra dependency), separate from the PyAutoGUI corner failsafe.
   Not implemented yet.
9. **Planned gesture design (M4):** pinch distance normalized by hand size (e.g. wrist->middle MCP) with separate enter/exit thresholds
   (hysteresis), a minimum interval between clicks, and a hold time before a pinch becomes a drag. Threshold values are TBD on hardware.
10. **`src/` layout, injected dependencies** (capture factory, landmarker, image factory, downloader, time) so everything except the real
    camera/model is unit-testable.

## Milestone 4 design (session 4)

### Gesture Architecture & Conflict Arbitration
1. **Normalization**: All distances are normalized by hand scale (`WRIST` (0) to `MIDDLE_MCP` (9)) to ensure invariant behavior regardless of hand distance to webcam.
2. **State Machines**:
   - **Pinch/Drag/Click**:
     - `RELEASED` -> pinch detected (`dist < pinch_click_threshold`) -> `PINCHING`.
     - `PINCHING` -> released before `pinch_drag_hold_s` (`dist > pinch_release_threshold`) -> Emits `LEFT_CLICK` (or `DOUBLE_CLICK` if preceded by another click within `double_click_interval_s`).
     - `PINCHING` -> held longer than `pinch_drag_hold_s` -> Transitions to `DRAGGING` and emits `LEFT_DOWN`.
     - `DRAGGING` -> released (`dist > pinch_release_threshold`) -> Transitions to `RELEASED` and emits `LEFT_UP`.
   - **Two-Finger Scroll**:
     - Requires `Index` and `Middle` extended together, close (`dist < scroll_activation_distance`), while `Ring` and `Pinky` are curled, and `Thumb` separated.
     - While scrolling, vertical delta of midpoint between index and middle tips accumulates and maps to vertical mouse scroll ticks with deadzone filtering.
   - **Right-Click**:
     - Thumb to Middle finger pinch while Index is held away.
     - Latches on activation, re-arms only after release with hysteresis and cooldown.
3. **Conflict Resolution Matrix**:
   - `DRAGGING` state has top priority; no clicks, scrolls, or right-clicks can trigger while dragging.
   - Left pinch suppresses two-finger scroll and right-click.
   - Two-finger scroll requires ring and pinky curled and thumb separated, preventing accidental scroll during normal navigation or clicking.
   - Tracking loss or pipeline stop guarantees `MouseController.release_all()` and resets all gesture state machines.

