# Virtual Mouse — Model Setup and Dependency Guide

This guide details the vision and speech models used by the Virtual Mouse platform, their storage paths, and download commands.

## 1. Inspecting Model Readiness

You can check whether all required models and dependencies are installed by running:

```powershell
python -m virtual_mouse.tools.run_cursor --check-models
```

This prints a status table showing presence, size, and validity for each modality:
- Hand tracking (`hand_landmarker.task`)
- Face/Eye tracking (`face_landmarker.task`)
- Speech recognition (`faster-whisper` cache)

---

## 2. Model Inventory and Specifications

### A. Hand Landmarker Model
- **Filename:** `models/hand_landmarker.task`
- **Size:** ~7.8 MB
- **Upstream URL:** `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`
- **Expected SHA-256:** `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`
- **Manual Download Command:**
  ```powershell
  python -m virtual_mouse.tools.run_cursor --download-model
  ```

### B. Face Landmarker Model (Eye Tracking)
- **Filename:** `models/face_landmarker.task`
- **Size:** ~3.7 MB
- **Upstream URL:** `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`
- **Auto-Download:** Attempted automatically in the runtime application when switching to Eye mode (`I`) or Both mode (`B`).
- **Manual Pre-Download Command:**
  ```powershell
  python -m virtual_mouse.tools.run_cursor --download-face-model
  ```

### C. Voice Model (Speech Recognition)
- **Engine:** `faster-whisper`
- **Default Model:** `tiny.en` or `base.en`
- **Cache Location:** `models/whisper/`
- **Auto-Download:** Downloaded automatically on first voice transcription to `models/whisper/`.

---

## 3. Pre-Fetching All Models

To download all required models before launching:

```powershell
python -m virtual_mouse.tools.run_cursor --download-all-models
```
