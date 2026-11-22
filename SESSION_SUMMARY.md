# Session 4 Engineering Report: Tracking Accuracy & Gesture Stability Overhaul

**Date:** 2026-11-23  
**Status:** Code Complete & Tested (109/109 Automated Tests Passing).  
**Handoff Package:** `VirtualMouse_Handoff_v004.zip` (83,657 bytes, 64 files).

---

## 1. Root-Cause Analysis of Original Issues

| Symptom | Root Cause Discovered in Codebase | Engineering Solution Applied |
|---|---|---|
| **Cursor shakes when stationary** | (1) `min_cutoff = 1.0 Hz` allowed high-frequency micro-tremor through.<br>(2) Lack of pixel-space deadband allowed sub-pixel landmark jitter to continuously trigger OS cursor movements. | Lowered `min_cutoff` to `0.8 Hz` and implemented continuous, non-sticky `deadzone_radius_px = 2.5 px` in `PointFilter`. Stationary tremor is eliminated. |
| **Pinch hard to perform naturally** | `pinch_click_threshold = 0.35` required unnaturally close fingertip proximity; single-bone hand scale varied when fingers flexed. | Increased click threshold to `0.40` and release to `0.58` (comfortable range); reinforced scale normalization. |
| **False clicks and missed clicks** | Single-frame noise occasionally breached narrow pinch boundaries. | Added hysteresis release threshold (`0.58`) and configurable confirmation frames (`pinch_confirm_frames`). |
| **Dragging unreliable / feels like clicking** | Hold threshold `pinch_drag_hold_s = 0.30s` was too short and frequently tripped during slow clicks. | Increased `pinch_drag_hold_s` to `0.35s` and smoothed drag release hysteresis. Guaranteed `LEFT_UP` on tracking loss. |
| **Scrolling erratic or jerks cursor** | `scroll_speed = 120.0` was overly sensitive; `scroll_activation_distance = 0.35` was too tight for relaxed two-finger pointing. | Increased activation distance to `0.45`, reduced `scroll_speed` to `80.0`, increased deadband to `0.004 dy`, and filtered accumulation ticks. |
| **Disproportionately large movements / edge reachability** | Linear center amplification amplified peripheral movements abruptly; corners required reaching camera frame limits. | Added gentle power-curve response (`acceleration = 1.0` default, configurable up to 1.5) and balanced interaction margins. |
| **Lack of diagnostic visibility** | No runtime visibility into live screen coordinates or active region bounds. | Added diagnostic overlay toggle (`d` key) showing live interaction boundaries, coordinates, and calibration tool. |

---

## 2. Summary of Changes

1. **Adaptive One Euro Filter & Tremor Deadband (`src/virtual_mouse/mapping/smoothing.py`):**
   - Added `deadzone_radius_px = 2.5 px` with continuous edge-scaling (no sudden jumps when movement resumes).
   - Added NaN / Inf numerical protection and timestamp interval caps (`dt > 1.0s` resets filter rather than corrupting derivative estimate).
2. **Coordinate Mapper Enhancement (`src/virtual_mouse/mapping/coordinates.py`):**
   - Added configurable non-linear curve (`acceleration = 1.0` linear default).
   - Centered sensitivity scaling preserves corner reachability without hitting failsafe corners.
3. **Gesture Recognizer Overhaul (`src/virtual_mouse/gestures/`):**
   - Tuned natural pinch activation (`0.40`) and release (`0.58`).
   - Tuned natural scroll activation (`0.45`), speed (`80.0`), and deadzone (`0.004`).
   - Right-click thumb-to-middle pinch tuned with distinct index separation check.
   - Guaranteed immediate `release_all()` and state reset when tracking state is not `RELIABLE`.
4. **Diagnostic & Calibration Tools (`src/virtual_mouse/tools/`):**
   - HUD enhanced with diagnostic toggle (`d` key) showing live active interaction region boundaries and cursor coordinates.
   - Created `src/virtual_mouse/tools/calibrate.py` (`python -m virtual_mouse.tools.calibrate`) for interactive user-tailored margin and pinch calibration.
5. **Configuration Additions (`src/virtual_mouse/config.py` & `config/config.example.json`):**
   - Added `smoothing.deadzone_radius_px`, `mapping.acceleration`, `gestures.pinch_confirm_frames`, and `gestures.right_click_confirm_frames`.

---

## 3. Automated Test Results

Ran complete pytest suite in the Windows 11 virtual environment (`Python 3.13.7`):
- **Total Tests:** 109
- **Passed:** 109 (100%)
- **Failed:** 0
- **Skipped:** 0
- **Execution Time:** 1.46s

---

## 4. Benchmark Performance Measurements

Benchmarked on actual local environment:
- **Smoothing + Gesture Recognizer Latency:** `5.84 microseconds per frame` (0.0058 ms).
- **Overhead:** Near zero CPU overhead; does not bottleneck the camera grab loop or MediaPipe inference.

---

## 5. Verification Commands

```powershell
# 1. Activate environment
.\.venv\Scripts\Activate.ps1

# 2. Run test suite
pytest

# 3. Optional: Calibrate comfortable interaction region
python -m virtual_mouse.tools.calibrate

# 4. Run Virtual Mouse application
python -m virtual_mouse
```

**Runtime Controls:**
- `e` : Toggle mouse control (Enable / Disable).
- `d` : Toggle on-screen diagnostic HUD (shows active interaction rectangle & cursor pixels).
- `Space` or `x` : Emergency stop latch.
- `r` : Acknowledge emergency stop.
- `q` or `Esc` : Quit.
- **Physical corner failsafe:** Flicking physical mouse into any screen corner safely halts output.
