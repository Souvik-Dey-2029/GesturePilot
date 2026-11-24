"""Offline Speech Recognition wrapper using faster-whisper.

Supports:
- Local model caching in models/whisper/
- INT8 CPU execution (fast, memory-efficient)
- Indian English & generic English biasing via initial_prompt
- Detailed telemetry: language probability, avg_logprob, duration, word error rejection
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional
import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TranscriptionResult:
    text: str
    language: str
    language_prob: float
    avg_logprob: float
    no_speech_prob: float
    duration_s: float
    latency_ms: float
    is_valid: bool


class WhisperASR:
    """Offline ASR engine based on faster-whisper CTranslate2."""

    def __init__(
        self,
        model_size_or_path: str = "tiny.en",
        download_root: Path | str = "models/whisper",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 4,
    ) -> None:
        self.model_size_or_path = model_size_or_path
        self.download_root = Path(download_root)
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads
        self._model: Optional[Any] = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load_model(self) -> bool:
        """Loads model weights lazily from local cache or downloads on-demand."""
        if self._model is not None:
            return True

        try:
            from faster_whisper import WhisperModel

            self.download_root.mkdir(parents=True, exist_ok=True)
            log.info(
                "Loading faster-whisper model '%s' (device=%s, compute=%s, cache=%s)...",
                self.model_size_or_path,
                self.device,
                self.compute_type,
                self.download_root,
            )
            self._model = WhisperModel(
                self.model_size_or_path,
                device=self.device,
                compute_type=self.compute_type,
                download_root=str(self.download_root),
                cpu_threads=self.cpu_threads,
            )
            log.info("faster-whisper model '%s' loaded successfully.", self.model_size_or_path)
            return True
        except Exception as exc:
            log.error("Failed to load faster-whisper model: %s", exc)
            self._model = None
            return False

    def unload_model(self) -> None:
        self._model = None
        log.info("faster-whisper model unloaded.")

    def transcribe_detailed(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        initial_prompt: Optional[str] = (
            "new tab, search, spell mode, alpha bravo charlie delta, close tab, switch tab, YouTube, Google"
        ),
    ) -> TranscriptionResult:
        t0 = time.perf_counter()
        if len(audio) == 0:
            return TranscriptionResult("", "en", 0.0, 0.0, 1.0, 0.0, 0.0, False)

        if self._model is None:
            if not self.load_model():
                return TranscriptionResult("", "en", 0.0, 0.0, 1.0, 0.0, 0.0, False)

        # Audio preprocessing & normalization
        audio_clean = audio - np.mean(audio)
        max_val = np.max(np.abs(audio_clean))
        if max_val > 0:
            audio_clean = audio_clean / max_val

        audio_duration = len(audio_clean) / sample_rate

        try:
            segments, info = self._model.transcribe(
                audio_clean,
                beam_size=3,
                language="en",
                initial_prompt=initial_prompt,
                condition_on_previous_text=False,
                vad_filter=True,
            )
            # Fully consume transcription generator
            seg_list = list(segments)
            transcribed_text = " ".join(seg.text.strip() for seg in seg_list).strip()
            latency = (time.perf_counter() - t0) * 1000.0

            avg_logprob = float(np.mean([s.avg_logprob for s in seg_list])) if seg_list else 0.0
            no_speech = float(np.mean([s.no_speech_prob for s in seg_list])) if seg_list else 0.0

            valid = bool(transcribed_text) and no_speech < 0.85
            log.info("Whisper transcribed: '%s' (prob=%.2f, latency=%.1fms)", transcribed_text, info.language_probability, latency)

            return TranscriptionResult(
                text=transcribed_text,
                language=info.language,
                language_prob=info.language_probability,
                avg_logprob=avg_logprob,
                no_speech_prob=no_speech,
                duration_s=audio_duration,
                latency_ms=latency,
                is_valid=valid,
            )
        except Exception as exc:
            log.warning("ASR transcription error: %s", exc)
            return TranscriptionResult("", "en", 0.0, 0.0, 1.0, audio_duration, 0.0, False)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """Simplified transcription string helper for backward compatibility."""
        res = self.transcribe_detailed(audio, sample_rate)
        return res.text
