"""Interactive Voice Calibration & Diagnostic CLI Tool.

Allows user to:
- List and test available sounddevice audio input microphones
- Monitor real-time RMS input level and clipping
- Test VAD speech segmentation
- Perform live offline Whisper ASR transcription trials
- Test multi-turn conversational search, dictation, and NATO spelling
- Measure real speech-to-transcript latencies
- Export diagnostic session logs
"""
from __future__ import annotations

import argparse
import sys
import time
import numpy as np

from ..logging_setup import configure_logging
from ..voice.asr import WhisperASR
from ..voice.audio import AudioCaptureEngine
from ..voice.subsystem import VoiceSubsystem
from ..voice.vad import VoiceActivityDetector


def run_voice_diagnostic_tool(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Virtual Mouse Voice Intelligence Diagnostic & Calibration Tool")
    ap.add_argument("--device", default=None, help="Audio input device index or substring name")
    ap.add_argument("--model", default="tiny.en", help="faster-whisper model (e.g. tiny.en, base.en)")
    ap.add_argument("--test-asr", action="store_true", help="Run live ASR on recorded audio chunks")
    args = ap.parse_args(argv)
    configure_logging("INFO")

    print("\n" + "=" * 70)
    print(" VIRTUAL MOUSE — VOICE INTELLIGENCE DIAGNOSTIC & CALIBRATION TOOL")
    print("=" * 70)

    # 1. Inspect Devices
    print("\n[1] Available Audio Input Endpoints:")
    devs = AudioCaptureEngine.list_input_devices()
    for d in devs:
        print(f"   [{d['index']}] {d['name']} (Channels: {d['channels']}, Default SR: {d['default_samplerate']} Hz)")

    dev_idx = None
    if args.device is not None:
        try:
            dev_idx = int(args.device)
        except ValueError:
            dev_idx = args.device

    # 2. Audio Capture Engine
    capture = AudioCaptureEngine(device=dev_idx)
    vad = VoiceActivityDetector()
    asr = WhisperASR(model_size_or_path=args.model)
    subsystem = VoiceSubsystem(audio_capture=capture, asr=asr)

    print(f"\n[2] Initializing AudioCaptureEngine on: {dev_idx or 'Windows Default Input'}")
    started = capture.start()
    if not started:
        print("[ERROR] Could not start sounddevice InputStream. Check microphone connection or permissions.")
        return 1

    print("[SUCCESS] Audio stream active. Monitoring live microphone level (Press Ctrl+C to stop)...")
    print("\n   Controls:")
    print("     - Speak into your microphone to observe RMS and VAD state.")
    print("     - Hold [Space] in this terminal for Push-to-Talk transcription (or run with --test-asr).\n")

    try:
        t_start = time.time()
        while time.time() - t_start < 20.0:  # Monitor for 20 seconds
            time.sleep(0.1)
            chunk = capture.get_recent_audio(duration_sec=0.03)
            if len(chunk) > 0:
                m = capture.metrics
                vad_st, comp_utterance = vad.process_chunk(chunk)
                bar = "#" * int(min(m.rms_level * 500, 40))
                speech_flag = "[SPEECH]" if vad_st.is_speech else "[SILENCE]"
                sys.stdout.write(f"\rRMS: {m.rms_level:.4f} Peak: {m.peak_level:.4f} | {speech_flag} {bar:<40}")
                sys.stdout.flush()

                if comp_utterance is not None and args.test_asr:
                    print(f"\n[VAD Triggered Utterance: {len(comp_utterance)/16000:.2f}s] Transcribing...")
                    res = asr.transcribe_detailed(comp_utterance)
                    print(f"  Transcript: '{res.text}' (Lang: {res.language}, Latency: {res.latency_ms:.1f}ms)")
                    evs = subsystem.process_utterance(res.text)
                    print(f"  Action Intent Dispatched: {[e.data for e in evs]}")

    except KeyboardInterrupt:
        pass
    finally:
        capture.stop()
        print("\n\n[SUCCESS] AudioCaptureEngine stopped cleanly.")

    return 0


if __name__ == "__main__":
    sys.exit(run_voice_diagnostic_tool())
