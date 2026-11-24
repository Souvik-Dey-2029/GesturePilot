# Voice Interaction Subsystem Architecture & User Guide

## Overview

The Voice Subsystem empowers Virtual Mouse users to navigate, search the web, manipulate browser tabs, and dictate text completely touch-free using real-time local speech recognition and a dedicated Chrome Manifest V3 extension.

### Core Architectural Principles
1. **Offline & Private**: Powered by `faster-whisper` (CTranslate2 INT8 quantized execution). Zero audio data leaves the local machine.
2. **Deterministic & Safe**: Operates via a conversational state machine (`VoiceState`). Sensitive actions (e.g., closing non-active tabs) require explicit conversational confirmation.
3. **NATO Phonetic & Spelling Fallback**: Handles challenging domain terminology, proper nouns, and URLs through character-by-character spelling with full NATO phonetic dictionary support.
4. **Push-to-Talk & Modality Gating**: Microphone stream is active only when Voice mode (`v`) or All mode (`a`) is toggled, and can be activated via Push-to-Talk (`t` / `Ctrl+Space`).
5. **No Direct Execution**: Voice commands emit validated intent events that are reviewed by the safety gate and dispatched to the loopback browser bridge (`127.0.0.1:8765`).

---

## Conversational Workflows

### Workflow A: New Tab & Search Dictation
- **Command**: *"open new tab"* / *"new tab"*
- **State Transition**: `IDLE` -> `AWAITING_SEARCH_TEXT`
- **System Prompt**: *"What would you like to search?"*
- **User Utterance**: *"deep learning transformers"*
- **Result**: New tab opens and searches Google for the transcribed query. System resets to `IDLE`.

### Workflow B: Spelling Mode with NATO Phonetic
- **Command**: *"spell mode"* / *"start spelling"*
- **State Transition**: `IDLE` -> `SPELLING`
- **Dictation**: Users speak NATO codewords (*"whiskey oscar romeo lima delta"*) or single alphanumeric characters (*"w o r l d"*).
- **Corrections**: *"backspace"* / *"delete"* removes the trailing character.
- **Completion**: *"done"* / *"confirm"* / *"search"* emits the spelled string and resets to `IDLE`.

### Workflow C: First Organic Search Result
- **Command**: *"open first result"* / *"click first link"* / *"first result"*
- **Action**: Dispatches `extract_first_result` to the active browser tab via the content script.
- **Safety**: Specifically filters out paid ads (`/aclk`, Google Ads containers) and navigates strictly to the highest-ranking organic result.

### Workflow D: Tab Switching & Safe Closing
- **Switching**: *"switch to youtube tab"* / *"go to github"* matches open tabs by partial title/URL and switches focus.
- **Safe Closing**: *"close spotify tab"* enters `AWAITING_CONFIRMATION` (*"Close spotify tab? Confirm with yes/no"*).
- **Current Tab Closing**: *"close current tab"* executes immediately without confirmation.

### Workflow E: Navigation & Page Control
- **Scrolling**: *"scroll down"* / *"page down"* / *"scroll up"* issues native mouse wheel scroll events through the mouse controller.

---

## Speech Recognition Engine: `faster-whisper`

- **Model**: `tiny.en` (~75 MB) or `base.en` (~145 MB).
- **Cache Location**: `models/whisper/` (cached locally, git-ignored).
- **Execution**: CPU INT8 with multithreaded OpenMP (compatible with Windows 11 and Python 3.13). Optional CUDA GPU acceleration on RTX 3050 laptops when CUDA runtime libraries are detected.
- **Prompt Biasing**: Initial prompt primes common domain terms: `"new tab, search, spell mode, alpha bravo charlie delta, close tab, switch tab"`.

---

## Audio Capture: `sounddevice`
- **Sample Rate**: 16,000 Hz, 1-channel, 32-bit float.
- **Ring Buffer**: 10-second rolling circular buffer.
- **VAD / Energy Thresholding**: Computes RMS energy over 30ms frames (`energy_threshold=0.015`) to isolate utterances from background room noise.

---

## Hardware Validation Protocol (Physical Microphone)

1. Connect microphone or verify laptop built-in array in Windows Sound Settings.
2. Launch `virtual-mouse`:
   ```bash
   virtual-mouse
   ```
3. Press `v` to toggle Voice input. The HUD will indicate: `VOICE: ENABLED (ASR & Browser Bridge ready)`.
4. Press `t` to toggle push-to-talk recording, say *"open new tab"*, and press `t` again.
5. Verify on-screen HUD displays transcription and status: `Browser: Opening new tab...`.
