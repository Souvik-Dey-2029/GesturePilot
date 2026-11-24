"""Energy and Hybrid Voice Activity Detection (VAD) Engine.

Identifies speech start, speech continuation, and speech end with pre-roll
and post-roll buffering to prevent truncating word initial and final consonants.
"""
from __future__ import annotations

import collections
import logging
from dataclasses import dataclass
from typing import Deque, List, Optional
import numpy as np

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class VADState:
    is_speech: bool
    energy: float
    confidence: float
    speech_duration_s: float
    silence_duration_s: float


class VoiceActivityDetector:
    """Robust VAD with pre-roll history and configurable silence hangover duration."""

    def __init__(
        self,
        sample_rate: int = 16000,
        energy_threshold: float = 0.015,
        min_speech_duration_s: float = 0.15,
        silence_hangover_s: float = 0.60,
        pre_roll_duration_s: float = 0.30,
    ) -> None:
        self.sample_rate = sample_rate
        self.energy_threshold = energy_threshold
        self.min_speech_duration_s = min_speech_duration_s
        self.silence_hangover_s = silence_hangover_s
        self.pre_roll_chunks = int(pre_roll_duration_s / 0.03)

        self._pre_roll_buffer: Deque[np.ndarray] = collections.deque(maxlen=self.pre_roll_chunks)
        self._speech_accumulator: List[np.ndarray] = []
        self._in_speech = False
        self._speech_frames = 0
        self._silence_frames = 0
        self._chunk_duration_s = 0.03

    def reset(self) -> None:
        self._pre_roll_buffer.clear()
        self._speech_accumulator.clear()
        self._in_speech = False
        self._speech_frames = 0
        self._silence_frames = 0

    def process_chunk(self, chunk: np.ndarray) -> tuple[VADState, Optional[np.ndarray]]:
        """Processes 30ms audio chunk. Returns (VADState, completed_utterance_or_none)."""
        energy = float(np.sqrt(np.mean(chunk**2))) if len(chunk) > 0 else 0.0
        is_above_th = energy >= self.energy_threshold
        completed_utterance = None

        if not self._in_speech:
            self._pre_roll_buffer.append(chunk)
            if is_above_th:
                self._speech_frames += 1
                if self._speech_frames >= 2:  # 60ms speech confirmation
                    self._in_speech = True
                    # Prepend pre-roll audio so initial phonemes (p, t, k, s) are preserved
                    self._speech_accumulator = list(self._pre_roll_buffer)
                    self._speech_accumulator.append(chunk)
                    self._silence_frames = 0
            else:
                self._speech_frames = 0
        else:
            self._speech_accumulator.append(chunk)
            if is_above_th:
                self._silence_frames = 0
                self._speech_frames += 1
            else:
                self._silence_frames += 1
                silence_duration = self._silence_frames * self._chunk_duration_s
                if silence_duration >= self.silence_hangover_s:
                    # Utterance completed
                    total_duration = len(self._speech_accumulator) * self._chunk_duration_s
                    if total_duration >= self.min_speech_duration_s:
                        completed_utterance = np.concatenate(self._speech_accumulator)
                    self._in_speech = False
                    self._speech_accumulator.clear()
                    self._speech_frames = 0
                    self._silence_frames = 0

        conf = min(1.0, max(0.0, (energy - 0.005) / 0.04))
        state = VADState(
            is_speech=self._in_speech,
            energy=energy,
            confidence=conf,
            speech_duration_s=self._speech_frames * self._chunk_duration_s,
            silence_duration_s=self._silence_frames * self._chunk_duration_s,
        )
        return state, completed_utterance
