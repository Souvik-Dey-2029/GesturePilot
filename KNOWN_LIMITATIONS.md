# Known Limitations & Hardware Boundaries

1. **Webcam RGB Gaze Accuracy:**
   - Standard monocular laptop webcams lack corneal infrared reflection glints. Unconstrained gaze mapping suffers from an inherent angular error of $3^\circ\text{--}5^\circ$ ($100\text{--}200\text{px}$ on 1080p).
   - In GesturePilot, eye tracking is specifically scoped to intentional blink sequences (scrolling) and coarse regional dwell selection rather than sub-pixel pointer positioning.

2. **Acoustic Noise & Speech Latency:**
   - High ambient acoustic background noise can degrade ASR word error rate. The voice engine requires clear speech input and provides push-to-talk (`Ctrl+Space`) to prevent false microphone triggering.

3. **Multi-Monitor Windows Desktop Coordinates:**
   - The current coordinate mapper and PyAutoGUI backend map to the primary display. Virtual desktop spans across mixed-DPI secondary monitors require future UI Automation coordinate translation.

4. **Chrome Manifest V3 Installation:**
   - Chrome requires developer mode to load unpacked extensions from `chrome://extensions`. The extension cannot be installed programmatically without user action.
