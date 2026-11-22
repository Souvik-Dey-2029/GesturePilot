# Hardware Validation Protocol — Gesture Engine Redesign (v005)

**Status:** Ready for User Hardware Execution.
**Target Hardware:** Windows 11 Laptop, Intel Core i5 13th Gen, NVIDIA RTX 3050, 16GB RAM, built-in webcam, 1920x1080 display.
**Environment:** Python 3.13.7, OpenCV 5.1.0, MediaPipe 1.2.3, NumPy 2.5.5, PyAutoGUI 0.9.54.

---

## 1. Safety Measures & Pre-flight Checklist

Before starting `python -m virtual_mouse`:
1. Physical mouse or laptop touchpad is within immediate reach.
2. The emergency stop mechanism is always accessible:
   - **Space** or **x** key in the preview window immediately latches emergency stop.
   - **Physical mouse slam into any screen corner** triggers PyAutoGUI failsafe and e-stops.
   - **Lowering hand out of camera frame** drops tracking (`TRACKING_LOST`) within 0.25s, freezing cursor and releasing all mouse buttons.
3. Open Palm (`PAUSE`) suspends cursor movement and ignores clicks/scrolls.

---

## 2. Launching Virtual Mouse v005

In PowerShell within the project repository:

```powershell
pip install -e . --no-deps
python -m virtual_mouse
```

Key controls in preview window:
- `e`: Enable / Disable mouse interaction (starts DISABLED).
- `d`: Toggle Diagnostic HUD overlay (shows live state, pose, scroll direction, stability %, cursor status).
- `Space` or `x`: Emergency stop latch.
- `r`: Acknowledge emergency stop (re-arms to DISABLED).
- `q` or `Esc`: Quit application safely.

---

## 3. Structured Gesture Testing Protocol

Complete each structured test session and record the observed counts:

### Test Set 1: Pointer Mode & Open Palm Pause (20 cycles)
- **Action:** Switch between Index-only pointer mode and 5-finger Open Palm.
- **Expected Outcome:** In pointer mode, cursor moves smoothly according to index fingertip. In Open Palm pose, HUD reports `POSE: OPEN_PALM | STATE: PAUSED | CURSOR: FROZEN`, cursor freezes immediately, and no clicks/scrolls trigger.
- **Target:** 20/20 successful pause/resume cycles.

### Test Set 2: Stationary Two-Finger Left Click (30 trials)
- **Action:** Extend Index + Middle fingers together (ring & pinky curled) and hold stationary over a desktop icon or test window for ~0.25 seconds.
- **Expected Outcome:** Exactly ONE left-click is emitted after `0.22s`. No double clicks or spurious drags occur. When holding fingers still after the click, no repeat clicks occur.
- **Target:** 30/30 intentional left clicks with zero false doubles.

### Test Set 3: Stationary Three-Finger Right Click (20 trials)
- **Action:** Extend Index + Middle + Ring fingers together (pinky curled) and hold stationary for ~0.25 seconds.
- **Expected Outcome:** Exactly ONE right-click is emitted after `0.22s`, opening the Windows context menu. No left click or scroll is triggered.
- **Target:** 20/20 intentional right clicks.

### Test Set 4: Thumb-Index Double Click (20 trials)
- **Action:** Pinch thumb tip and index fingertip together briefly and release.
- **Expected Outcome:** Exactly ONE double-click is emitted, opening the desktop folder/file. Releasing the pinch re-arms the gesture.
- **Target:** 20/20 intentional double clicks.

### Test Set 5: Dynamic Two-Finger & Three-Finger Scrolling (20 trials each direction)
- **Action:** Extend 2 fingers (or 3 fingers) and move hand vertically up and down in a web browser or text document before the `0.22s` stationary click window expires.
- **Expected Outcome:** Vertical motion cancels any pending click. Interaction enters `SCROLLING` state. Cursor is strictly frozen. Moving hand up scrolls page up; moving hand down scrolls page down. Returning to pointer mode exits scrolling cleanly after 0.10s.
- **Target:** 20 scroll up trials, 20 scroll down trials.

### Test Set 6: 10-Minute Continuous Usability Test
- **Action:** Navigate between browser tabs, scroll Wikipedia or a long PDF, click links, and right-click to inspect or open context menus for 10 continuous minutes.
- **Expected Outcome:** Zero accidental clicks while scrolling, zero unintended scrolling while pointing, zero cursor drift during pause.

---

## 4. Hardware Verification Results Form (To Fill After Testing)

```markdown
### Hardware Verification Summary
- **Tester:** [User]
- **Date & OS:** [Windows 11 / Python 3.13.7]
- **Webcam FPS Observed:** [e.g. 24-30 FPS]

| Gesture Feature | Trials Attempted | Successful | False Triggers / Notes |
|---|---|---|---|
| Open Palm Pause | 20 | | |
| Pointer Cursor Tracking | Continuous | | |
| Two-Finger Left Click | 30 | | |
| Three-Finger Right Click | 20 | | |
| Thumb-Index Double Click | 20 | | |
| Dynamic Vertical Scroll (Up/Down) | 40 | | |
| Tracking Loss Safety Release | 5 | | |
| 10-Min Continuous Navigation | 1 session | | |

**Overall Usability Rating (1-5):**
**Observed Latency / Stability Notes:**
```
