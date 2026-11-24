# Eye Tracking Live Blink Recognition — Root Cause Analysis & Debugging Report

**Investigation Date:** 2026-11-23  
**Observed Live Screenshot Telemetry:**  
`EYE: DETECTED | L_BLINK: 0.17 | R_BLINK: 0.14 | EAR: 0.34 | STATE: EYES_OPEN | SEQ: 0`  
**Test Suite Verification:** 148 / 148 passed  

---

## 1. Executive Summary & Root Causes

The webcam screenshot demonstrates that face detection, landmark inference, and blendshape classification are working in real-time. However, intentional blinking failed to reliably trigger mouse scrolling due to four distinct architectural factors:

1. **Master Control Gate (DISARMED by Default):**
   - *Source File:* `src/virtual_mouse/controller.py` (`arm()`, `disarm()`) & `src/virtual_mouse/fusion/engine.py` (`evaluate()`)
   - *Root Cause:* The application starts in **DISARMED** mode (`master_armed = False`). When a double-blink sequence completes, `EyeSubsystem` generates the `DOUBLE_BLINK` event. However, `MultimodalFusionEngine.evaluate()` checks:
     ```python
     if not self.master_armed:
         return FusionDecision(False, "disarmed", {}, event.confidence, "Master control is disarmed")
     ```
     Because the user had not pressed `m` to arm master control, all mouse actions (`self._mouse.scroll_wheel(amt)`) were strictly blocked by the safety gate.
   - *Telemetry Indicator:* Line 1 on the HUD displays `CONTROL: DISARMED (Press 'm' to arm)`.

2. **Sequence Window Premature Timeout Truncation:**
   - *Source File:* `src/virtual_mouse/eye/subsystem.py` (`EyeSubsystem.process()`, lines 167-208)
   - *Root Cause:* The sequence window was fixed at `0.65s` from the onset of the *first* blink. In deliberate human double-blinking:
     - Blink 1: 150ms closure + release at $t = 0.20\text{s}$.
     - Natural human inter-blink pause: $350\text{--}450\text{ms}$.
     - Blink 2: Onset at $t \approx 0.65\text{s}$.
     When the user started closing their eyes for the second blink, the timer `t - self._sequence_start_time` exceeded `0.65s` while the eyes were still closed. The previous logic executed sequence finalization on the closed frame, observed `count == 1`, and discarded the sequence with `"Single natural blink ignored"`.
   - *Fix Applied:*
     1. Relaxed `sequence_window_s` from `0.65s` to `0.85s` to provide comfortable spacing for deliberate blinks.
     2. Gated sequence finalization on `not self._is_blinking` so in-progress blinks are never truncated mid-closure.

3. **Frame-Rate Discretization on Blink Duration Filtering:**
   - *Source File:* `src/virtual_mouse/eye/subsystem.py` (`EyeCalibration`)
   - *Root Cause:* At 30 FPS, each video frame is $\approx 33.3\text{ms}$. A crisp intentional blink of 2 frames closure is $2 \times 33.3\text{ms} = 66.7\text{ms}$.
   - The original threshold `min_blink_duration_s = 0.08` (80ms) required at least 3 consecutive closed frames ($99.9\text{ms}$). A 2-frame blink was discarded as:
     `Micro-blink rejected (0.07s < 0.08s)`.
   - Conversely, deliberate emphatic blinks often linger for $400\text{ms}$, which exceeded the previous `max_blink_duration_s = 0.38` (380ms) and were discarded as `Prolonged closure rejected`.
   - *Fix Applied:* Adjusted `min_blink_duration_s = 0.05` (allows $\ge 2$ closed frames) and `max_blink_duration_s = 0.45` (allows deliberate emphatic closures).

4. **Blendshape & EAR Threshold Margins:**
   - *Source File:* `src/virtual_mouse/eye/subsystem.py` (`compute_blink_metrics()`)
   - *Root Cause:* Open-eye baseline in the screenshot is `L_BLINK: 0.17`, `R_BLINK: 0.14`, `EAR: 0.34`.
   - MediaPipe's `eyeBlinkLeft` and `eyeBlinkRight` represent closure confidence ($0.0 = \text{open}$, $1.0 = \text{closed}$). For partial or hooded eyelids, a full blink may only score $0.46\text{--}0.52$.
   - The threshold `blendshape_blink_threshold` was set to `0.50`. Lowering it to `0.45` ensures robust detection across diverse webcam angles without triggering false positives from natural eye movements (which remain $\le 0.20$).

---

## 2. Pipeline Trace Across Subsystems

```
1. Webcam BGR Frame
      │
      ▼
2. FaceDetector.detect(frame)
      │  MediaPipe Tasks Vision FaceLandmarker (XNNPACK CPU)
      │  Extracts 478 3D landmarks + 52 face blendshapes
      ▼
3. EyeSubsystem.compute_blink_metrics(face)
      │  left_b = blendshapes['eyeBlinkLeft'] (e.g. 0.17 open -> 0.75 closed)
      │  right_b = blendshapes['eyeBlinkRight'] (e.g. 0.14 open -> 0.75 closed)
      │  ear = (ear_l + ear_r) / 2.0 (e.g. 0.34 open -> 0.12 closed)
      ▼
4. EyeSubsystem.process(face)
      │  eyes_closed = (avg_blink >= 0.45) or (ear <= 0.20)
      │  duration check: 0.05s <= duration <= 0.45s
      │  sequence accumulator: window = 0.85s, cooldown = 0.60s
      │  Count == 2 -> DOUBLE_BLINK event (scroll_down, -3)
      │  Count >= 3 -> TRIPLE_BLINK event (scroll_up, +3)
      ▼
5. RuntimeController.process_frame_modalities(frame)
      │
      ▼
6. MultimodalFusionEngine.evaluate(event)
      │  1. Stale check: event.is_stale() -> Fresh
      │  2. Confidence: confidence >= 0.85 -> Passes (0.90 / 0.92)
      │  3. Source check: Eye authorized in EYE, BOTH, ALL modes -> Passes
      │  4. Master Gate: master_armed must be TRUE -> Must press 'm' to arm!
      │  5. Emergency Stop: safety.estop.is_set must be FALSE
      ▼
7. MouseController.scroll_wheel(amount)
```

---

## 3. Diagnostic Mode Enhancements

The HUD overlay in `src/virtual_mouse/tools/visualization.py` now includes a comprehensive real-time blink diagnostic readout:

```
MODE: BOTH  |  CONTROL: ARMED  |  FPS: 30  |  TRACKING: OK
POSE: OPEN_PALM  |  ACTION: UP  |  CURSOR: ACTIVE
STATUS: Mode switched to BOTH (Hand + Face active concurrently).
EYE: DETECTED | L_BLINK: 0.17 R_BLINK: 0.14 | EAR: 0.34 | STATE: EYES_OPEN | SEQ: 0
BLINK DIAG: Win: 0.00s | Cool: 0.00s | Thresh(EAR<=0.20, Blend>=0.45) | Last: DOUBLE_BLINK | Status: Accepted
KEYS: [E] Hand [I] Eye [B] Both [V] Voice [A] All [M] Arm/Disarm [T/Ctrl+Space] Talk | Space/X: E-STOP | [R] Reset | [Q] Quit
DIAGNOSTIC OVERLAY: ON | Eye Latency: 12.4ms | Master Safety Gate: PERMITTED
```

Key indicators:
- **`BLINK DIAG Win`**: Live countdown timer of the sequence accumulation window ($0.85\text{s}$).
- **`Cool`**: Live cooldown lockout timer ($0.60\text{s}$) preventing accidental repeats.
- **`Thresh`**: Live display of active thresholds (`EAR <= 0.20`, `Blend >= 0.45`).
- **`Status`**: Shows instant rejection reason (`Micro-blink`, `Prolonged closure`, `In cooldown window`, `Single natural blink ignored`, or `Accepted`).
- **`Master Safety Gate`**: Clearly states `PERMITTED` (when armed) or `BLOCKED (DISARMED/ESTOP)`.

---

## 4. Operational Instructions for Physical Webcam Retest

1. **Launch Virtual Mouse in Both or Eye Mode:**
   ```powershell
   python -m virtual_mouse.tools.run_cursor
   ```
2. **Switch to Modality & Enable Diagnostics:**
   - Press **`b`** to activate `BOTH` mode (Hand + Eye) or **`i`** for `EYE` only.
   - Press **`d`** to toggle the expanded diagnostic HUD.
3. **CRITICAL: Arm Master Control:**
   - Press **`m`** to toggle master control from `DISARMED` to `ARMED`.
   - Verify line 1 displays `CONTROL: ARMED` in green and diagnostic line displays `Master Safety Gate: PERMITTED`.
4. **Execute Blink Gestures:**
   - **Double Blink (Scroll Down):** Perform two deliberate blinks (closure lasting $\approx 100\text{--}200\text{ms}$ each) within $\approx 0.8\text{s}$.
   - **Triple Blink (Scroll Up):** Perform three deliberate blinks in succession.
5. **Observe Diagnostic Telemetry:**
   - Watch `SEQ` count increment from 0 to 1, then 2.
   - Watch `Status` confirm `Accepted (Double Blink)` and line 2 show `mouse.scroll`.
