# Research and Prior Art Analysis

## 1. Vision-Based Hand Tracking & Gesture Interfaces
- **MediaPipe Hand Landmarker (Lugaresi et al., 2019; Zhang et al., 2020):** 21 3D landmarks via palm detector and regression model. Highly robust for single-camera desktop setups.
- **Gesture Ambiguity & Overlap:** Continuous Euclidean thresholds between finger tips suffer from anatomical variance and perspective deformation. Classical literature recommends scale normalization using metacarpal landmarks (wrist to middle MCP) and discrete extension ratios.
- **v004 vs. v005 Real-World Observations:** In real user testing, v004's pinch interactions operated reliably, whereas v005's stationary multi-finger hold-to-click encountered high sensitivity to micro-movement. The system must support a configurable dual-profile architecture to retain v004 as an immediate stable fallback.

## 2. Facial & Eye-Gaze Interaction
- **Eye Aspect Ratio (EAR) & Blink Dynamics (Soukupová & Čech, 2016):** Bilateral synchronization and blink duration curves differentiate involuntary natural blinks ($100\text{--}250\text{ms}$) from intentional double or triple blink commands.
- **Webcam Gaze Limitations (Hansen & Ji, 2010):** Monocular RGB webcams lack infrared glint corneal reflection; uncalibrated eye gaze exhibits $3\text{--}5^\circ$ error ($100\text{--}200\text{px}$ on 1080p). Therefore, gaze must be treated as coarse region navigation or dwell selection, paired with head-pose compensation and explicit calibration.

## 3. Local Voice & Intent Systems
- **Offline Automatic Speech Recognition:** Whisper architectures (`faster-whisper`, `whisper.cpp`, `Vosk`) offer high accuracy without cloud egress. On Python 3.13 / Windows 11, lightweight local engines with constrained intent schemas provide sub-$200\text{ms}$ latency for deterministic desktop control.
- **Dictation vs. Command Separation:** A strict conversational finite-state machine is mandatory so that dictated search strings are never interpreted as executable desktop commands.

## 4. Adaptive Personalization & Incremental ML
- **Online Learning (River ML, Bifet et al., 2018):** User-specific calibration parameters (hand scale, blink threshold, phrase aliases) stored in SQLite with WAL mode. Progressive validation guarantees that personal updates are only promoted when exceeding the base model's performance on held-out samples.
