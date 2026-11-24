# Real Eye Tracking and Blink Interaction Guide

**Document Version:** 1.0.0 (Follow-up 1)  
**Target Environment:** Windows 11, Python 3.13.7, MediaPipe 1.2.3, OpenCV 5.1.0

---

## 1. System Overview

The Eye Interaction subsystem uses Google MediaPipe's official `FaceLandmarker` to extract 478 3D facial landmarks and facial blendshapes (`eyeBlinkLeft`, `eyeBlinkRight`) directly from the shared webcam capture.

It integrates directly into `RuntimeController` and `run_cursor.py`, enabling standalone Eye mode (`I`), joint Hand + Eye mode (`B`), and full multimodal operation (`A`).

---

## 2. Model Asset Management

- **Model Bundle:** `models/face_landmarker.task` (MediaPipe Tasks FaceLandmarker float16 bundle).
- **Download Location:** `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`
- **Asset Integrity & Lifecycle:**
  - Automated download helper `ensure_face_model()` in `src/virtual_mouse/detection/model_assets.py`.
  - Atomic `.part` file download with verify-and-rename.
  - Stored in the git-ignored `models/` directory.
  - Initialized **lazily** only when Eye (`I`) or Both (`B`) mode is chosen.
  - Closed and released immediately when returning to Hand-only mode (`E`).

To download the model via command line:
```powershell
python -m virtual_mouse --download-model
```

---

## 3. Blink Recognition Dynamics

Natural human blinking occurs at an involuntary frequency of 15–20 blinks per minute, with an average duration of 100–250ms. To prevent natural blinks from triggering unwanted actions, GesturePilot employs strict temporal filtering and sequence finalization windows:

### Blink Parameter Thresholds (`EyeCalibration`)
- `min_blink_duration_s = 0.08`: Filters out sensor noise and micro-flutters (<80ms).
- `max_blink_duration_s = 0.38`: Filters out eye fatigue or prolonged squinting (>380ms).
- `blendshape_blink_threshold = 0.50`: Blink score threshold confirming eyelid closure.
- `sequence_window_s = 0.65`: Time window to accumulate multiple blinks before finalization.
- `cooldown_s = 0.60`: Lockout window after an action to prevent duplicate triggers.

### Blink Command Vocabulary
1. **Single Natural Blink:** **NO ACTION.** Sequence window times out and resets harmlessly.
2. **Intentional Double Blink:** **Scroll Down** (-3 ticks). Triggered when exactly two deliberate blinks occur within the 0.65s window.
3. **Intentional Triple Blink:** **Scroll Up** (+3 ticks). Triggered immediately on the 3rd deliberate blink.

---

## 4. Modality Modes

- **Hand Only (`E`):** Verified cursor pipeline. Face detector is closed and released to conserve CPU/GPU.
- **Eye Only (`I`):** Hand inference is idle. FaceLandmarker processes the shared camera stream and executes blink scrolling.
- **Both Mode (`B`):** Hand tracking moves the cursor while Eye tracking simultaneously handles vertical scrolling. A tracking dropout in one does not disable the other.
- **Master Control (`M`):** Controls whether actions emit to the desktop. Application starts **DISARMED** by default.
- **Emergency Stop (`Space` / `X`):** Immediately stops all pointer movement and scrolling across all modalities.

---

## 5. Telemetry & Diagnostic HUD

When diagnostic mode is toggled (`d`), the HUD overlay displays live eye metrics:
```text
MODE: BOTH  |  CONTROL: ARMED  |  FPS: 30  |  TRACKING: RELIABLE
POSE: POINTER  |  ACTION: NONE  |  CURSOR: ACTIVE
STATUS: Mode switched to BOTH (Hand + Face active concurrently).
EYE: DETECTED | L_BLINK: 0.02 R_BLINK: 0.01 | EAR: 0.28 | STATE: EYES_OPEN | SEQ: 0
KEYS: [E] Hand [I] Eye [B] Both [V] Voice [A] All [M] Arm/Disarm | Space/X: E-STOP
```

---

## 6. Physical Hardware Validation Checklist

To validate on your physical Windows 11 webcam:
1. Ensure the face model is downloaded:
   ```powershell
   python -m virtual_mouse --download-model
   ```
2. Start the application:
   ```powershell
   python -m virtual_mouse
   ```
3. Press **`b`** to enter BOTH mode. Verify HUD displays `EYE: DETECTED`.
4. Press **`m`** to arm mouse control.
5. In a web browser or text document:
   - Perform natural blinks $\to$ verify zero accidental scrolling.
   - Perform two deliberate blinks $\to$ verify page scrolls down.
   - Perform three deliberate blinks $\to$ verify page scrolls up.
6. Press **`e`** to switch back to Hand-only mode $\to$ verify FaceDetector is closed and released.
