"""Rebuilt Voice Subsystem and Command Intent Router.

Integrates:
- AudioCaptureEngine with non-blocking callback
- VoiceActivityDetector with pre-roll history
- WhisperASR (faster-whisper INT8 CPU)
- VoiceConversationController (multi-turn search and spoken corrections)
- DictationEngine & SpellingEngine
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import numpy as np

from ..events import EventType, ModalityType, MultimodalEvent
from .asr import TranscriptionResult, WhisperASR
from .audio import AudioCaptureEngine
from .conversation import VoiceConversationController, VoiceConversationState, VoiceIntent
from .dictation import DictationEngine, SpellingEngine, NATO_PHONETIC
from .vad import VoiceActivityDetector, VADState

log = logging.getLogger(__name__)


# Backward compatibility aliases for existing tests
class VoiceState(Enum):
    IDLE = "idle"
    LISTENING = "listening"
    COMMAND = "command"
    COMMAND_PENDING = "command_pending"
    AWAITING_SEARCH_TEXT = "awaiting_search_text"
    DICTATION = "dictation"
    DICTATION_MODE = "awaiting_search_text"
    SPELLING = "spelling"
    SPELLING_MODE = "spelling"
    TRANSCRIPT_REVIEW = "transcript_review"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    EXECUTING = "executing"
    CANCELLED = "cancelled"


@dataclass
class VoiceTelemetry:
    enabled: bool = False
    device_name: str = "Default Input"
    sample_rate: int = 16000
    rms_level: float = 0.0
    queue_occupancy: float = 0.0
    vad_is_speech: bool = False
    vad_confidence: float = 0.0
    last_transcript: str = ""
    language: str = "en"
    avg_logprob: float = 0.0
    transcription_latency_ms: float = 0.0
    conversation_state: str = "IDLE"
    pending_prompt: str = ""
    last_action: str = "NONE"
    rejection_reason: str = ""


class VoiceSubsystem:
    """Orchestrates audio capture, VAD, Whisper ASR, conversational state, and browser actions."""

    def __init__(
        self,
        audio_capture: Optional[AudioCaptureEngine] = None,
        asr: Optional[WhisperASR] = None,
    ) -> None:
        self.enabled = False
        self.audio = audio_capture or AudioCaptureEngine()
        self.asr = asr or WhisperASR()
        self.vad = VoiceActivityDetector()

        self.conversation = VoiceConversationController()
        self.dictation = DictationEngine()
        self.spelling = SpellingEngine()

        self._voice_aliases: Dict[str, str] = {}
        self.telemetry = VoiceTelemetry()

    @property
    def state(self) -> VoiceState:
        """Compatibility property mapping conversation state to VoiceState."""
        st = self.conversation.state
        if st == VoiceConversationState.AWAITING_SEARCH_TEXT:
            return VoiceState.AWAITING_SEARCH_TEXT
        if st == VoiceConversationState.DICTATION:
            return VoiceState.DICTATION
        if st == VoiceConversationState.SPELLING:
            return VoiceState.SPELLING
        if st == VoiceConversationState.AWAITING_CONFIRMATION:
            return VoiceState.AWAITING_CONFIRMATION
        if st == VoiceConversationState.EXECUTING:
            return VoiceState.EXECUTING
        if st == VoiceConversationState.CANCELLED:
            return VoiceState.CANCELLED
        return VoiceState.IDLE

    @state.setter
    def state(self, value: VoiceState) -> None:
        if value in (VoiceState.AWAITING_SEARCH_TEXT, VoiceState.DICTATION_MODE):
            self.conversation.state = VoiceConversationState.AWAITING_SEARCH_TEXT
        elif value in (VoiceState.DICTATION,):
            self.conversation.state = VoiceConversationState.DICTATION
        elif value in (VoiceState.SPELLING, VoiceState.SPELLING_MODE):
            self.conversation.state = VoiceConversationState.SPELLING
        elif value == VoiceState.AWAITING_CONFIRMATION:
            self.conversation.state = VoiceConversationState.AWAITING_CONFIRMATION
        elif value == VoiceState.EXECUTING:
            self.conversation.state = VoiceConversationState.EXECUTING
        elif value == VoiceState.CANCELLED:
            self.conversation.state = VoiceConversationState.CANCELLED
        else:
            self.conversation.state = VoiceConversationState.IDLE

    def enable(self) -> bool:
        self.enabled = True
        self.reset()
        started = self.audio.start(on_utterance_ready=self._on_audio_utterance)
        self.telemetry.enabled = True
        return started

    def disable(self) -> None:
        self.enabled = False
        self.audio.stop()
        self.reset()
        self.telemetry.enabled = False

    def reset(self) -> None:
        self.conversation.reset()
        self.dictation.reset()
        self.spelling.reset()
        self.vad.reset()

    def add_alias(self, phrase: str, target_intent: str) -> None:
        self._voice_aliases[phrase.lower().strip()] = target_intent

    def _on_audio_utterance(self, audio: np.ndarray) -> None:
        """Triggered asynchronously by push-to-talk or VAD completion."""
        if not self.enabled or len(audio) == 0:
            return
        res = self.asr.transcribe_detailed(audio)
        if res.is_valid:
            self.telemetry.last_transcript = res.text
            self.telemetry.language = res.language
            self.telemetry.avg_logprob = res.avg_logprob
            self.telemetry.transcription_latency_ms = res.latency_ms

    def process_utterance(self, text: str, now: float | None = None) -> List[MultimodalEvent]:
        """Main conversational intent classification and workflow dispatcher."""
        t = now if now is not None else time.monotonic()
        clean = text.lower().strip()
        self.telemetry.last_transcript = text
        events: List[MultimodalEvent] = []

        # 1. Global Cancellation Command
        if clean in ("cancel", "stop", "abort", "never mind", "clear", "cancel that"):
            msg = self.conversation.cancel("Spoken cancel command")
            self.reset()
            events.append(MultimodalEvent(
                source=ModalityType.VOICE,
                event_type=EventType.VOICE_CANCEL,
                confidence=1.0,
                timestamp=t,
                expiration_time=t + 0.5,
                data={"message": msg},
            ))
            self.telemetry.last_action = "CANCEL"
            return events

        # 2. Spoken Correction Handling ("No, change X to Y")
        corrected = self.conversation.handle_spoken_correction(text)
        if corrected is not None:
            self.telemetry.last_action = f"CORRECTED: {corrected}"
            self.telemetry.rejection_reason = "Phrase corrected"
            return events

        # 2b. Confirmation Handling
        if self.conversation.state == VoiceConversationState.AWAITING_CONFIRMATION:
            if clean in ("yes", "confirm", "correct", "proceed", "open it", "close it", "do it"):
                intent = self.conversation.pending_intent
                self.conversation.state = VoiceConversationState.IDLE
                self.conversation.pending_intent = None
                if intent:
                    events.append(MultimodalEvent(
                        source=ModalityType.VOICE,
                        event_type=EventType.VOICE_COMMAND,
                        confidence=intent.confidence,
                        timestamp=t,
                        expiration_time=t + 1.5,
                        data={"intent": intent.intent_name, "entities": intent.entities, "raw": intent.raw_text, "confirmed": True},
                    ))
                    self.telemetry.last_action = f"CONFIRMED_{intent.intent_name}"
                return events
            elif clean in ("no", "wrong", "change", "cancel", "don't"):
                self.conversation.reset()
                self.telemetry.last_action = "CONFIRMATION_REJECTED"
                return events

        # 3. Dictation Mode
        if self.conversation.state == VoiceConversationState.DICTATION:
            if clean in ("finish dictation", "done dictating", "stop dictation"):
                final_txt = self.dictation.current_text
                self.conversation.state = VoiceConversationState.IDLE
                events.append(MultimodalEvent(
                    source=ModalityType.VOICE,
                    event_type=EventType.VOICE_DICTATION,
                    confidence=1.0,
                    timestamp=t,
                    expiration_time=t + 2.0,
                    data={"action": "dictation.finish", "text": final_txt},
                ))
                self.telemetry.last_action = "DICTATION_COMPLETED"
                return events

            updated = self.dictation.append_utterance(text)
            self.telemetry.last_action = f"DICTATING: {updated}"
            events.append(MultimodalEvent(
                source=ModalityType.VOICE,
                event_type=EventType.VOICE_DICTATION,
                confidence=0.95,
                timestamp=t,
                expiration_time=t + 2.0,
                data={"action": "dictation.append", "text": updated, "raw": text},
            ))
            return events

        # 4. Spelling Mode
        if self.conversation.state == VoiceConversationState.SPELLING:
            word, is_fin = self.spelling.process_spelling_tokens(text)
            if is_fin:
                self.conversation.state = VoiceConversationState.IDLE
                events.append(MultimodalEvent(
                    source=ModalityType.VOICE,
                    event_type=EventType.VOICE_SPELLING,
                    confidence=1.0,
                    timestamp=t,
                    expiration_time=t + 2.0,
                    data={"action": "browser.search", "spelled_word": word, "query": word},
                ))
                self.telemetry.last_action = f"SPELLING_FINISHED: {word}"
                return events

            self.telemetry.last_action = f"SPELLED: {word}"
            events.append(MultimodalEvent(
                source=ModalityType.VOICE,
                event_type=EventType.VOICE_SPELLING,
                confidence=0.95,
                timestamp=t,
                expiration_time=t + 1.0,
                data={"current_buffer": word},
            ))
            return events

        # 5. Search Text Awaiting State (Workflow Step 3 & 4)
        if self.conversation.state == VoiceConversationState.AWAITING_SEARCH_TEXT:
            if clean in ("spell mode", "enter spelling mode", "start spelling"):
                self.conversation.state = VoiceConversationState.SPELLING
                events.append(MultimodalEvent(
                    source=ModalityType.VOICE,
                    event_type=EventType.VOICE_COMMAND,
                    confidence=1.0,
                    timestamp=t,
                    expiration_time=t + 1.0,
                    data={"intent": "system.spelling_active"},
                ))
                return events

            self.conversation.pending_query = text.strip()
            self.conversation.state = VoiceConversationState.IDLE
            self.telemetry.last_action = f"SEARCH: {self.conversation.pending_query}"

            events.append(MultimodalEvent(
                source=ModalityType.VOICE,
                event_type=EventType.VOICE_DICTATION,
                confidence=0.95,
                timestamp=t,
                expiration_time=t + 2.0,
                data={"action": "browser.search", "query": self.conversation.pending_query},
            ))
            return events

        # 6. Command Mode Intent Classification
        intent = self._parse_intent(clean)
        if intent is not None:
            if intent.intent_name == "browser.open_new_tab_and_search":
                prompt = self.conversation.enter_awaiting_search()
                self.telemetry.pending_prompt = prompt
                self.telemetry.last_action = "NEW_TAB_OPENED"
                events.append(MultimodalEvent(
                    source=ModalityType.VOICE,
                    event_type=EventType.VOICE_COMMAND,
                    confidence=intent.confidence,
                    timestamp=t,
                    expiration_time=t + 1.0,
                    data={"intent": "browser.new_tab", "prompt": prompt},
                ))
                return events

            elif intent.intent_name == "system.enter_spelling":
                self.conversation.state = VoiceConversationState.SPELLING
                self.spelling.reset()
                events.append(MultimodalEvent(
                    source=ModalityType.VOICE,
                    event_type=EventType.VOICE_COMMAND,
                    confidence=1.0,
                    timestamp=t,
                    expiration_time=t + 1.0,
                    data={"intent": "system.spelling_active"},
                ))
                return events

            elif intent.intent_name == "system.start_dictation":
                self.conversation.state = VoiceConversationState.DICTATION
                self.dictation.reset()
                events.append(MultimodalEvent(
                    source=ModalityType.VOICE,
                    event_type=EventType.VOICE_COMMAND,
                    confidence=1.0,
                    timestamp=t,
                    expiration_time=t + 1.0,
                    data={"intent": "system.start_dictation"},
                ))
                return events

            # Direct browser commands
            ev_data = {"intent": intent.intent_name, "entities": intent.entities, "raw": intent.raw_text}
            if intent.requires_confirmation:
                ev_data["needs_confirmation"] = True
                self.conversation.state = VoiceConversationState.AWAITING_CONFIRMATION
                self.conversation.pending_intent = intent

            ev = MultimodalEvent(
                source=ModalityType.VOICE,
                event_type=EventType.VOICE_COMMAND,
                confidence=intent.confidence,
                timestamp=t,
                expiration_time=t + 1.5,
                data=ev_data,
            )
            events.append(ev)
            self.telemetry.last_action = intent.intent_name
            return events

        self.telemetry.rejection_reason = f"Unknown command: '{clean}'"
        return events

    def _parse_intent(self, text: str) -> Optional[VoiceIntent]:
        # User defined aliases
        for phrase, target in self._voice_aliases.items():
            if phrase in text:
                return VoiceIntent(target, entities={"query": text}, confidence=0.98, raw_text=text)

        # Mode triggers
        if text in ("start dictation", "enter dictation mode", "dictation"):
            return VoiceIntent("system.start_dictation", confidence=0.99, raw_text=text)
        if text in ("spell mode", "enter spelling mode", "start spelling"):
            return VoiceIntent("system.enter_spelling", confidence=0.99, raw_text=text)

        # Tab opening
        if text in ("open a new tab", "open new tab", "new tab"):
            return VoiceIntent("browser.open_new_tab_and_search", confidence=0.98, raw_text=text)

        # Direct search
        m = re.match(r"^(?:search for|google|search)\s+(.+)$", text)
        if m:
            return VoiceIntent("browser.search", entities={"query": m.group(1).strip()}, confidence=0.95, raw_text=text)

        # Organic result opening
        if text in ("open first result", "open the first result", "first result", "open top result"):
            return VoiceIntent("browser.open_first_result", confidence=0.95, raw_text=text)

        # Tab switching
        m = re.match(r"^(?:switch to|go to|open)\s+(?:the\s+)?(?:tab with\s+)?(.+?)(?:\s+tab)?$", text)
        if m:
            target = m.group(1).strip()
            if target not in ("new", "first result", "a new"):
                return VoiceIntent("browser.switch_tab", entities={"query": target}, confidence=0.94, raw_text=text)

        # Tab closing
        m = re.match(r"^(?:close|turn off)\s+(?:the\s+)?(.+?)(?:\s+tab)?$", text)
        if m:
            target = m.group(1).strip()
            is_current = target in ("current", "this", "tab")
            return VoiceIntent(
                "browser.close_tab",
                entities={"query": target},
                confidence=0.94,
                raw_text=text,
                requires_confirmation=(not is_current),
            )

        # Scrolling
        if text in ("scroll down", "page down"):
            return VoiceIntent("browser.scroll", entities={"direction": "down", "amount": 300}, confidence=0.95, raw_text=text)
        if text in ("scroll up", "page up"):
            return VoiceIntent("browser.scroll", entities={"direction": "up", "amount": 300}, confidence=0.95, raw_text=text)

        return None
