# Baseline Audit and System Snapshot

**Date:** 2026-11-23  
**Branch:** `recovery/v005-baseline`  
**Host Environment:** Windows 11 (build 26300), Python 3.13.7 (MSC v.1944 64-bit), Intel Core i5 13th Gen, NVIDIA RTX 3050 Laptop GPU (6GB), 16GB RAM, 1080p display.

## 1. Verified Working Modules & Tests
- **Automated Test Suite:** 111/111 passing tests in `2.06s` (`pytest`).
- **Core Vision & ML Stack:**
  - `opencv-python`: 5.1.0
  - `mediapipe`: 1.2.3 (both `HandLandmarker` and `FaceLandmarker` available via `mediapipe.tasks.python.vision`)
  - `numpy`: 2.5.5
  - `pyautogui`: 0.9.54
  - `reportlab`: 5.1.0
  - `matplotlib`: 3.11.2
  - `sqlite3`: built-in standard library

## 2. Safety & Control Invariants
- `SafetyController.can_emit()` gates all OS mouse events.
- PyAutoGUI corner failsafe is strictly enabled.
- Emergency stop (`Space`, `x`) latches system state; `r` required to re-arm.
- Tracking loss watchdog ($>0.25\text{s}$) forces all buttons up and freezes cursor.
- Application starts `DISARMED`/`DISABLED` by default.

## 3. Preservation Strategy
- The v004 gesture pipeline is preserved as a selectable fallback profile (`GESTURE_PROFILE=v004` vs `v005`).
- The new adaptive multimodal architecture wraps existing subsystems cleanly into independent, mockable components.
