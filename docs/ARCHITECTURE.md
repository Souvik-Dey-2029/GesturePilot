# Architecture Guide: AI Virtual Mouse

## Overview

Virtual Mouse processes webcam frames through a pipeline decoupled into modular stages:

```
Camera (Threaded grabber)
  │
  ▼
HandDetector (MediaPipe Tasks VIDEO mode)
  │
  ▼
SafetyController (Reliability streak & Lost-hand timeout)
  │
  ▼
GestureRecognizer (Mutually exclusive state machine)
  │
  ▼
CoordinateMapper & OneEuroFilter (Adaptive smoothing & deadzone)
  │
  ▼
MouseController (Safety gate & button tracking)
  │
  ▼
MouseBackend (PyAutoGUI / Win32 forced release)
```

## Centralized State Machine (v005)

The interaction states are mutually exclusive:
- `PAUSED`: Open palm (5 fingers extended), cursor strictly frozen, clicks/scrolls ignored.
- `POINTER`: Index finger only extended, controlling cursor movement.
- `TWO_FINGER_PENDING`: Index + middle extended, differentiating stationary left click vs. intentional vertical motion scrolling.
- `THREE_FINGER_PENDING`: Index + middle + ring extended, differentiating stationary right click vs. intentional vertical motion scrolling.
- `PINCH_PENDING`: Thumb + index pinch, triggers double click with hysteresis release and cooldown lockout.
- `SCROLLING`: Continuous vertical displacement scrolling with cursor frozen; clean exit when returning to pointer or pause.
- `TRACKING_LOST`: Instant button release and safety latch.
