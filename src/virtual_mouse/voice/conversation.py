"""Voice Interaction State Machine and Conversational Controller.

Required States:
1. IDLE
2. LISTENING
3. SPEECH_DETECTED
4. TRANSCRIBING
5. TRANSCRIPT_REVIEW
6. COMMAND_CLASSIFICATION
7. AWAITING_SEARCH_TEXT
8. DICTATION
9. SPELLING
10. AWAITING_CONFIRMATION
11. EXECUTING
12. WAITING_FOR_RESULT
13. COMPLETED
14. CANCELLED
15. ERROR
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class VoiceConversationState(Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    SPEECH_DETECTED = "SPEECH_DETECTED"
    TRANSCRIBING = "TRANSCRIBING"
    TRANSCRIPT_REVIEW = "TRANSCRIPT_REVIEW"
    COMMAND_CLASSIFICATION = "COMMAND_CLASSIFICATION"
    AWAITING_SEARCH_TEXT = "AWAITING_SEARCH_TEXT"
    DICTATION = "DICTATION"
    SPELLING = "SPELLING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    EXECUTING = "EXECUTING"
    WAITING_FOR_RESULT = "WAITING_FOR_RESULT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


@dataclass
class VoiceIntent:
    intent_name: str
    entities: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.95
    raw_text: str = ""
    requires_confirmation: bool = False


class VoiceConversationController:
    """Manages conversational multi-turn workflows, context, confirmations, and cancellations."""

    def __init__(self) -> None:
        self.state = VoiceConversationState.IDLE
        self.pending_intent: Optional[VoiceIntent] = None
        self.pending_query: str = ""
        self.pending_prompt: str = ""
        self.last_action_message: str = ""

    def reset(self) -> None:
        self.state = VoiceConversationState.IDLE
        self.pending_intent = None
        self.pending_query = ""
        self.pending_prompt = ""
        self.last_action_message = ""

    def cancel(self, reason: str = "User cancelled") -> str:
        self.state = VoiceConversationState.CANCELLED
        self.pending_intent = None
        self.pending_query = ""
        self.pending_prompt = ""
        self.last_action_message = f"Cancelled: {reason}"
        self.state = VoiceConversationState.IDLE
        return self.last_action_message

    def enter_awaiting_search(self) -> str:
        self.state = VoiceConversationState.AWAITING_SEARCH_TEXT
        self.pending_prompt = "What would you like to search?"
        return self.pending_prompt

    def handle_spoken_correction(self, text: str) -> Optional[str]:
        """Handles spoken correction patterns: 'No, change X to Y' or 'No, I meant Y'."""
        clean = text.lower().strip()
        # Pattern: "no, change X to Y"
        m = re.search(r"(?:no,?\s+)?(?:change|replace)\s+(.+?)\s+(?:to|with)\s+(.+)$", clean)
        if m and self.pending_query:
            old_w, new_w = m.group(1).strip(), m.group(2).strip()
            self.pending_query = re.sub(re.escape(old_w), new_w, self.pending_query, flags=re.IGNORECASE)
            self.last_action_message = f"Updated search phrase to: '{self.pending_query}'"
            return self.pending_query

        # Pattern: "no, I meant Y" or "no, Y"
        m2 = re.search(r"^(?:no,?\s+)?(?:i meant|actually)\s+(.+)$", clean)
        if m2 and self.state in (VoiceConversationState.AWAITING_SEARCH_TEXT, VoiceConversationState.AWAITING_CONFIRMATION):
            self.pending_query = m2.group(1).strip()
            self.last_action_message = f"Updated phrase: '{self.pending_query}'"
            return self.pending_query

        return None
