# Eye Recognition Core Rebuild & Stabilization Report

**Platform:** Windows 11, Python 3.13.7  
**Status:** REBUILT, STABILIZED, VERIFIED THROUGH AUTOMATED TESTS  
**Regression Test Suite:** 165 / 165 passed in 2.25s  

---

## 1. Verified Root Causes of False Actions & Unreliable Recognition

The prior implementation exhibited two conflicting problems:
1. When armed, it occasionally reported `DOUBLE_BLINK` or `TRIPLE_BLINK` scroll actions without intentional user gestures.
2. At other times, intentional blinks failed to register or execute.

Through source audit and deterministic simulation, the exact mathematical and temporal root causes were established:

### Root Cause A: Global Sequence Window Boundary Collision
- **Source File & Function:** `src/virtual_mouse/eye/subsystem.py` (`EyeSubsystem.process()`, lines 160-208)
- **Mechanism:** The legacy accumulator measured elapsed time from the start of the *first* blink:
  $$t - t_{\text{sequence\_start}} \ge \text{sequence\_window\_s}$$
  Because this timer was global rather than measuring inter-blink intervals, two natural reading blinks occurring $\approx 450\text{ms}$ apart inside an extended window were merged into an unintended `DOUBLE_BLINK` command.
  Conversely, if the user deliberately initiated a second blink near the window boundary, the timer expired while the eyes were still closed, discarding the second blink and logging `Single natural blink ignored`.

### Root Cause B: Lack of Schmitt-Trigger Hysteresis on Thresholds
- **Source File & Function:** `src/virtual_mouse/eye/subsystem.py` (`compute_blink_metrics()`)
- **Mechanism:** Eye closure was evaluated on single static thresholds ($0.45$ for blendshape or $0.20$ for EAR). Eyelids hovering near the threshold during squinting or downward gaze suffered from single-frame boundary oscillations. Without Schmitt-trigger hysteresis ($T_{\text{closed}} \neq T_{\text{open}}$), noise crossed the boundary repeatedly, generating false blink transitions.

### Root Cause C: Blendshape Fallback Inversion & Premature Actions
- **Source File & Function:** `src/virtual_mouse/eye/subsystem.py` (`compute_blink_metrics()`)
- **Mechanism:** In the fallback path (when dense 468 landmarks were absent), EAR was synthesized from blendshapes as $\text{ear} = \text{baseline} \times (1.0 - \text{avg\_blink})$. When a squint or partial closure occurred, EAR was forced below threshold even when geometric landmarks were wide open, causing double-dipping. Furthermore, double-blink actions were executed without waiting for potential triple-blinks to complete.

---

## 2. Rebuilt Architecture & Mathematical Formulation

The eye subsystem has been decomposed into modular, independently testable layers:

```
Webcam Frame
    │
    ▼
FaceDetector (MediaPipe Tasks Vision)
    │  Extracts 478 3D landmarks + 52 face blendshapes
    ▼
EyeFeatureExtractor (src/virtual_mouse/eye/feature_extractor.py)
    │  - Computes 6-point canonical EAR for left and right eyes
    │  - Extracts blendshapes (eyeBlink, eyeSquint, eyeWide)
    │  - Computes bilateral eye symmetry & tracking quality
    ▼
EyeStateEstimator (src/virtual_mouse/eye/state_estimator.py)
    │  - Dual-threshold Schmitt-trigger hysteresis
    │  - States: EYES_OPEN, EYES_CLOSING, EYES_CLOSED, EYES_OPENING, TRACKING_LOST, UNCERTAIN
    ▼
BlinkDetector (src/virtual_mouse/eye/blink_detector.py)
    │  - Recognizes single complete physiological blinks: OPEN -> CLOSING -> CLOSED -> OPENING -> OPEN
    │  - Enforces min/max duration filters (50ms - 450ms)
    ▼
BlinkSequenceRecognizer (src/virtual_mouse/eye/blink_detector.py)
    │  - Measures inter-blink pause (<= 450ms)
    │  - Single natural blink dropped after quiet window
    │  - Double blink finalized only after 350ms quiet window (prevents cutting triple blink short)
    │  - Triple blink fires immediately on 3rd blink
    │  - Enforces 600ms cooldown lockout
    ▼
MultimodalFusionEngine (src/virtual_mouse/fusion/engine.py)
    │  - Gated by active mode (EYE, BOTH, ALL) and confidence >= 0.85
    │  - Gated by Master Arming (Space/X emergency stop overrides)
    ▼
Desktop Mouse Scroll
```

### 2.1 Canonical 6-Point EAR Formula
Implemented using verified MediaPipe landmark indices (Soukupová & Čech, 2016):
$$\text{EAR} = \frac{\|p_2 - p_6\| + \|p_3 - p_5\|}{2 \cdot \|p_1 - p_4\|}$$
- **Left Eye Indices:** $p_1=362, p_2=385, p_3=387, p_4=263, p_5=373, p_6=380$
- **Right Eye Indices:** $p_1=33, p_2=160, p_3=158, p_4=133, p_5=153, p_6=144$
- Guarded against zero-width landmarks ($\|p_1 - p_4\| \le 10^{-6}$).

### 2.2 Dual-Threshold Schmitt-Trigger Hysteresis
To prevent boundary oscillation:
- **EAR:** Closure requires $\text{EAR} \le 0.18$. Reopening requires $\text{EAR} \ge 0.22$.
- **Blendshape:** Closure requires $\text{Blend} \ge 0.55$. Reopening requires $\text{Blend} \le 0.35$.
- Confirmation requires at least 2 consecutive frames in the closing state.

### 2.3 Strict Inter-Blink Temporal Sequence Separation
Instead of an arbitrary global timer:
- **Inter-Blink Pause:** Must be $\le 450\text{ms}$ between consecutive blinks. If a user naturally blinks while reading (typically spaced $\ge 1\text{s}$ apart), the first blink expires and is discarded.
- **Double Blink Quiet Window:** A double blink waits $350\text{ms}$ after the 2nd blink before dispatching `scroll_down`. If a 3rd blink arrives within $350\text{ms}$, it upgrades directly to `scroll_up` without double-firing.
- **Cooldown Lockout:** Dispatches at most 1 command per sequence followed by a $600\text{ms}$ refractory period.

---

## 3. Dedicated Calibration & Diagnostic CLI Tool

Created `src/virtual_mouse/tools/calibrate_eye.py` to allow live inspection and calibration without moving the mouse:

```powershell
python -m virtual_mouse.tools.calibrate_eye
```

Features:
- **Live Visual Telemetry:** Displays EAR for left, right, and average eyes, blendshape scores, current state, in-blink flag, and live latency.
- **Interactive Calibration:**
  - Press `o` to capture open-eye baseline samples.
  - Press `c` to capture deliberate closed-eye samples.
  - Press `s` to automatically compute Schmitt-trigger thresholds and save to `user_profile.db`.
  - Press `r` to reset calibration buffers.
- **Diagnostic CSV Export:** Run with `--export-csv diagnostics.csv` to record frame-by-frame values for empirical evaluation.

---

## 4. Capability Status Matrix

| Subsystem / Capability | Verification Level | Status | Notes |
| :--- | :--- | :--- | :--- |
| **MediaPipe Tasks FaceLandmarker** | VERIFIED IN SOURCE & TEST | **ACTIVE** | Video running mode, XNNPACK CPU, 478 landmarks + 52 blendshapes. |
| **Canonical 6-pt Geometric EAR** | VERIFIED THROUGH AUTOMATED TEST | **ACTIVE** | Verified against Soukupová & Čech (2016) formulation. |
| **Blendshape Category Extraction** | VERIFIED IN SOURCE & TEST | **ACTIVE** | Explicit dictionary lookup (`eyeBlinkLeft`, `eyeBlinkRight`, `eyeSquint`, `eyeWide`). |
| **Dual Hysteresis Eye State Estimator** | VERIFIED THROUGH AUTOMATED TEST | **ACTIVE** | Dual-threshold Schmitt trigger eliminates boundary flutter. |
| **Physiological Blink Duration Filter** | VERIFIED THROUGH AUTOMATED TEST | **ACTIVE** | 50ms - 450ms duration window accommodates deliberate blinks. |
| **Inter-Blink Natural Pause Gating** | VERIFIED THROUGH AUTOMATED TEST | **ACTIVE** | Discards natural blinks spaced $> 450\text{ms}$ apart. |
| **Double vs Triple Sequence Isolation** | VERIFIED THROUGH AUTOMATED TEST | **ACTIVE** | 350ms quiet window prevents premature double dispatch. |
| **Tracking Loss Safety Reset** | VERIFIED THROUGH AUTOMATED TEST | **ACTIVE** | Sequence cancelled immediately on tracking loss or occlusion. |
| **Master Control Arming Gate** | VERIFIED IN SOURCE & TEST | **ACTIVE** | Blocks desktop scrolling when DISARMED; permits when ARMED. |
| **Diagnostic Overlay Telemetry** | VERIFIED IN SOURCE & TEST | **ACTIVE** | Enhanced HUD with EAR L/R, blendshapes, state, and gate status. |
| **Physical Webcam Live Calibration** | HARDWARE TEST REQUIRED | **READY** | User retest protocol ready via `calibrate_eye` tool. |

---

## 5. Verification Commands for User

1. **Run Full Regression Test Suite (165 Tests):**
   ```powershell
   cmd /c "set PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 && .\.venv\Scripts\python.exe -m pytest -p no:faulthandler"
   ```
2. **Launch Interactive Eye Calibration & Diagnostic Tool:**
   ```powershell
   python -m virtual_mouse.tools.calibrate_eye
   ```
3. **Launch Main Virtual Mouse Application in Both Mode:**
   ```powershell
   python -m virtual_mouse.tools.run_cursor
   ```
   - Press **`b`** to switch to `BOTH` mode (Hand + Eye).
   - Press **`d`** to show diagnostic HUD overlay.
   - Press **`m`** to arm master desktop control.
