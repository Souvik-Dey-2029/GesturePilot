# User Guide: AI Virtual Mouse

## Quick Start

### 1. Installation
In PowerShell on Windows 11:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

### 2. Download Model & Run
```powershell
python -m virtual_mouse --download-model
```

### 3. Keyboard Shortcuts (Window focused)
- `e` : Toggle mouse control (Enable / Disable)
- `d` : Toggle diagnostic HUD
- `Space` / `x` : Emergency Stop
- `r` : Re-arm after Emergency Stop
- `q` / `Esc` : Quit

---

## Gestures Reference (v005 Mutually Exclusive Vocabulary)

1. **Pause (`OPEN_PALM`):** Extend all 5 fingers facing the camera. Cursor movement immediately suspends and clicks/scrolls are suppressed.
2. **Pointer Mode (`POINTER`):** Extend index finger only (middle, ring, pinky curled). Cursor tracks smoothly according to the index fingertip.
3. **Left Click / Scroll (`TWO_FINGERS`):** Extend index and middle fingers together (ring and pinky curled).
   - *Left Click:* Hold stationary for ~0.22s to trigger exactly one left click.
   - *Scroll:* Move hand vertically before the 0.22s window expires to enter continuous vertical scrolling.
4. **Right Click / Scroll (`THREE_FINGERS`):** Extend index, middle, and ring fingers together (pinky curled).
   - *Right Click:* Hold stationary for ~0.22s to trigger exactly one right click.
   - *Scroll:* Move hand vertically before the 0.22s window expires to enter continuous vertical scrolling.
5. **Double Click (`PINCH`):** Pinch thumb tip and index fingertip together. Emits a confirmed double click; release pinch to re-arm.
6. **Dynamic Scrolling:** Active during vertical movement in 2-finger or 3-finger pose. Cursor is strictly frozen while scrolling. Return to Pointer mode or Open Palm to exit scrolling cleanly.

---

## Safety Guidelines

- Always keep a physical mouse or trackpad nearby.
- Flicking the physical mouse cursor into any screen corner immediately activates the emergency failsafe latch.
