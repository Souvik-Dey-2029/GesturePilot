# AI Virtual Mouse

> Touchless Windows desktop mouse control powered by webcam hand tracking and computer vision.

[![CI](https://github.com/souvik-hazra/VirtualMouse/actions/workflows/ci.yml/badge.svg)](https://github.com/souvik-hazra/VirtualMouse/actions/workflows/ci.yml)
[![Python 3.11 | 3.12 | 3.13](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Virtual Mouse allows natural, touchless interaction with Windows 11 desktop environments using an ordinary webcam. It uses Google MediaPipe for 21-landmark hand tracking, an adaptive One Euro filter with micro-tremor deadband for jitter-free cursor motion, and a mutually exclusive state machine for reliable gesture controls.

---

> [!WARNING]
> **Safety Notice:** Virtual Mouse controls your physical system cursor. Always keep a physical mouse or trackpad connected. Flicking the mouse into any screen corner immediately latches PyAutoGUI's emergency failsafe.

---

## Features

- **Jitter-Free Cursor Movement:** Adaptive One Euro filter dynamically suppresses tremors at rest while minimizing lag during fast sweeps.
- **Micro-Tremor Deadband:** Suppresses sub-pixel landmark jitter when holding the hand steady without sticky cursor drag.
- **Natural Pinch Controls:** Scale-invariant normalized distance thresholds for left click and sustained drag-and-drop.
- **Peace-Sign Scrolling:** Mutually exclusive peace-sign pose activates vertical page scrolling while freezing the cursor.
- **Right Click:** Comfortable thumb-to-middle finger pinch with index finger held extended.
- **Safety Gate & Failsafe:** All OS inputs pass through a centralized safety controller. Releasing held buttons is guaranteed on tracking loss or shutdown.
- **Diagnostic HUD & Interactive Calibration:** On-screen heads-up display and interactive margin/threshold calibration tool.

---

## Gestures Reference

| Interaction Mode | Hand Pose | Action | Cursor State |
|---|---|---|---|
| **Pointing (Default)** | Index extended, others curled | Move hand to steer cursor | Active & smoothed |
| **Left Click** | Thumb-Index pinch | Quick pinch and release (<0.35s) | Emits Left Click |
| **Drag & Drop** | Thumb-Index pinch held | Hold pinch >0.35s and move hand | Holds Left Button |
| **Double Click** | Consecutive pinches | Two quick pinches in rapid succession (<0.40s) | Emits Double Click |
| **Two-Finger Scroll** | Peace sign (Index + Middle extended) | Hold peace sign for 0.15s, move hand up/down | Cursor Frozen, scrolls page |
| **Right Click** | Thumb-Middle pinch (Index extended) | Pinch thumb to middle finger with index extended | Emits Right Click |

---

## Installation & Setup

### Requirements
- **OS:** Windows 11 / Windows 10
- **Python:** 3.11, 3.12, or 3.13 (Verified on 3.13.7)
- **Webcam:** 720p or 1080p standard USB or built-in webcam

### Windows PowerShell Installation

1. **Clone the repository:**
   ```powershell
   git clone https://github.com/souvik-hazra/VirtualMouse.git
   cd VirtualMouse
   ```

2. **Create and activate a virtual environment:**
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. **Install the package:**
   ```powershell
   pip install -e .
   ```

4. **Download the MediaPipe Hand Landmarker model & start:**
   ```powershell
   python -m virtual_mouse --download-model
   ```

---

## Keyboard Controls (Preview Window)

- `e` : Toggle mouse control (Enable / Disable)
- `d` : Toggle on-screen Diagnostic HUD
- `Space` or `x` : Trigger Emergency Stop
- `r` : Re-arm after Emergency Stop (enters Disabled mode)
- `q` or `Esc` : Quit

---

## Interactive Calibration

To calibrate your comfortable range of motion and pinch thresholds:
```powershell
python -m virtual_mouse.tools.calibrate
```
Follow the on-screen instructions to record top-left and bottom-right limits and your natural pinch distance.

---

## Documentation

- [User Guide](docs/USER_GUIDE.md): Setup, tips, and gestures walkthrough.
- [Architecture](docs/ARCHITECTURE.md): System components, dataflow, and state machines.
- [Testing Guide](docs/TESTING.md): Test suite details and CI validation.
- [Development Guide](docs/DEVELOPMENT.md): Contribution practices and coding standards.
- [Release Audit](RELEASE_AUDIT.md): Technical readiness and security audit.

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
