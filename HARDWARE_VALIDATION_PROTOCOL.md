# Hardware Validation Protocol: Adaptive Multimodal HCI Platform

**Status:** Ready for Physical User Execution  
**Hardware Environment:** Windows 11 Laptop, Intel Core i5 13th Gen, NVIDIA RTX 3050, 16GB RAM, built-in webcam, microphone.

---

## 1. Safety Pre-Flight Verification
1. Physical mouse / laptop trackpad is within immediate hand reach.
2. Emergency stops are verified:
   - **Space** or **x** immediately halts all mouse output.
   - **Flicking mouse into screen corner** trips PyAutoGUI failsafe.
   - **Lowering hand** drops tracking within $0.25\text{s}$, releasing all mouse buttons.
3. System starts **DISARMED**; press **`M`** to arm / disarm master control.

---

## 2. Modality Mode Switching Test
In PowerShell, launch the application:
```powershell
python -m virtual_mouse
```
Verify the following hotkeys in the preview window:
- Press **`E`**: Hand Only mode (Hand status ACTIVE, Eye/Voice INACTIVE).
- Press **`I`**: Eye Only mode (Eye status ACTIVE, Hand/Voice INACTIVE).
- Press **`B`**: Both Hand + Eye mode.
- Press **`V`**: Toggle Voice mode independently.
- Press **`A`**: Enable All modalities.
- Press **`d`**: Toggle diagnostic telemetry HUD overlay.

---

## 3. Chrome Manifest V3 Extension Test
1. Open Google Chrome.
2. Navigate to `chrome://extensions/` and enable **Developer mode** (top right toggle).
3. Click **Load unpacked** and select the folder:
   `D:\Development\Projects\MY PERSONAAL WORKS\VirtualMouse_Handoff_v003\VirtualMouse\browser_extension`
4. Confirm "GesturePilot Desktop Bridge" appears with green active badge.

---

## 4. Multimodal Structured Verification Checklist

### A. Hand Subsystem (20 Trials)
- Test pointer cursor tracking across the desktop.
- Switch to v004 fallback profile if stationary multi-finger clicks are too sensitive.
- Verify Open Palm immediately pauses cursor motion.

### B. Eye Subsystem (15 Trials)
- Perform intentional **double blink** (close eyes firmly for ~150ms twice within 0.6s) $\to$ verify downward scroll.
- Perform intentional **triple blink** $\to$ verify upward scroll.
- Verify normal involuntary blinking does NOT trigger accidental scrolling.

### C. Voice & Browser Workflow Test (10 Trials)
- Say: *"Open a new tab"* $\to$ confirm new tab opens.
- Dictate: *"machine learning papers"* $\to$ confirm search executes.
- Say: *"Spell mode"* $\to$ dictate: *"g-o-l-f  d-o-n-e"* $\to$ confirm spelling.
- Say: *"Open the first result"* $\to$ confirm the organic top result opens.
- Say: *"Close current tab"* $\to$ confirm tab closes cleanly.

### D. Personalization Persistence
- Check `config/profiles/user_profile.db` exists.
- Perform user feedback corrections and verify updated parameters persist across application restarts.
