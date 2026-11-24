"""Natural Dictation and NATO Phonetic Spelling Engines.

Part 1: DictationEngine:
- Assembles multi-sentence paragraphs
- Converts spoken punctuation: "comma", "full stop", "period", "new line", "new paragraph"
- Supports editing: "delete last word", "clear text", "finish dictation"

Part 2: SpellingEngine:
- Single letter entry & NATO phonetic mapping (Alpha, Bravo, Charlie, etc.)
- Numbers, symbols, backspace, clear, repeat
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

log = logging.getLogger(__name__)

PUNCTUATION_REPLACEMENTS = [
    (r"\s*\bnew line\b\s*", "\n"),
    (r"\s*\bnew paragraph\b\s*", "\n\n"),
    (r"\s*\bfull stop\b", "."),
    (r"\s*\bperiod\b", "."),
    (r"\s*\bcomma\b", ","),
    (r"\s*\bquestion mark\b", "?"),
    (r"\s*\bexclamation mark\b", "!"),
    (r"\s*\bcolon\b", ":"),
    (r"\s*\bsemicolon\b", ";"),
]

NATO_PHONETIC: dict[str, str] = {
    "alpha": "a", "bravo": "b", "charlie": "c", "delta": "d", "echo": "e",
    "foxtrot": "f", "golf": "g", "hotel": "h", "india": "i", "juliet": "j",
    "kilo": "k", "lima": "l", "mike": "m", "november": "n", "oscar": "o",
    "papa": "p", "quebec": "q", "romeo": "r", "sierra": "s", "tango": "t",
    "uniform": "u", "victor": "v", "whiskey": "w", "xray": "x", "yankee": "y",
    "zulu": "z", "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "space": " ", "dot": ".", "slash": "/", "dash": "-", "hyphen": "-", "underscore": "_",
}


class DictationEngine:
    """Manages natural dictation buffer, spoken punctuation replacement, and editing."""

    def __init__(self) -> None:
        self._text_chunks: List[str] = []

    @property
    def current_text(self) -> str:
        return "".join(self._text_chunks).strip()

    def reset(self) -> None:
        self._text_chunks.clear()

    def append_utterance(self, raw_text: str) -> str:
        text = raw_text.strip()
        lower = text.lower()

        # Handle editing commands
        if lower in ("delete last word", "delete word", "undo last word"):
            self.delete_last_word()
            return self.current_text
        elif lower in ("clear text", "clear draft", "clear"):
            self.reset()
            return ""

        # Replace spoken punctuation
        formatted = text
        for pattern, repl in PUNCTUATION_REPLACEMENTS:
            formatted = re.sub(pattern, repl, formatted, flags=re.IGNORECASE)

        # Space management
        if self._text_chunks and not self._text_chunks[-1].endswith(("\n", " ", ".")):
            self._text_chunks.append(" ")
        self._text_chunks.append(formatted)

        return self.current_text

    def delete_last_word(self) -> None:
        if not self._text_chunks:
            return
        last = self._text_chunks.pop()
        words = last.rstrip().split()
        if len(words) > 1:
            self._text_chunks.append(" ".join(words[:-1]))


class SpellingEngine:
    """Manages NATO phonetic and individual letter/digit spelling buffer."""

    def __init__(self) -> None:
        self._characters: List[str] = []

    @property
    def current_word(self) -> str:
        return "".join(self._characters)

    def reset(self) -> None:
        self._characters.clear()

    def process_spelling_tokens(self, text: str) -> tuple[str, bool]:
        """Processes tokens like 'alpha bravo charlie' or 'backspace'. Returns (current_word, is_finished)."""
        tokens = text.lower().split()
        is_finished = False

        for tok in tokens:
            if tok in ("backspace", "delete", "undo"):
                if self._characters:
                    self._characters.pop()
            elif tok in ("clear", "clear all"):
                self._characters.clear()
            elif tok in ("done", "confirm", "finish", "search"):
                is_finished = True
            elif tok in NATO_PHONETIC:
                self._characters.append(NATO_PHONETIC[tok])
            elif len(tok) == 1 and tok.isalnum():
                self._characters.append(tok)

        return self.current_word, is_finished
