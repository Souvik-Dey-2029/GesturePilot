# Next Session Prompt: Milestone 5 — Stability, Desktop UI & Optimization

## Context
Milestone 4 (Gesture-Based Mouse Controls) is complete and verified with 105 automated tests.
The system now supports:
- Scale-invariant geometry calculation.
- Pinch-to-left-click with hysteresis and cooldown.
- Pinch-and-hold to drag-and-drop with guaranteed button release.
- Double-click detection with timing intervals.
- Two-finger scrolling with direction, smoothing, and deadzone.
- Right-click gesture (thumb-middle pinch with separated index).
- Full gesture conflict arbitration matrix.
- Clean HUD overlay showing tracking, active gestures, mouse state, and metrics.
- Safety latching and gate enforcement.

## Milestone 5 Objectives
1. **Desktop UI (PySide6 / PyQt)**:
   - Move pipeline execution to a background worker thread.
   - Build a modern desktop window showing live video feed, status indicators, and toggles (enable/disable, sensitivity controls).
   - Interactive calibration screen for active region margins and gesture thresholds.
2. **Global Emergency Hotkey**:
   - Implement focus-independent emergency stop using Windows ctypes `RegisterHotKey`.
3. **Hardware User Feedback Integration**:
   - Collect user feedback on physical feel of drag, double-click, and scroll sensitivity on actual Windows 11 hardware and fine-tune defaults if needed.
