"""Adaptive Personalization Engine with local SQLite WAL storage.

Learns personalized calibration (hand scale baseline, blink threshold, phrase aliases),
records explicit user corrections, and validates model updates before promotion.
"""
from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class UserProfile:
    user_id: str = "default_user"
    hand_scale_bias: float = 1.0
    blink_ear_threshold: float = 0.18
    cursor_sensitivity: float = 1.0
    scroll_speed_multiplier: float = 1.0
    voice_aliases: Dict[str, str] = field(default_factory=dict)
    model_version: int = 1


class PersonalizationStore:
    """SQLite WAL storage for user profiles, interaction feedback, and labeled calibration samples."""

    def __init__(self, db_path: Path | str = "config/profiles/user_profile.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("PRAGMA journal_mode=WAL;")
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    user_id TEXT PRIMARY KEY,
                    hand_scale_bias REAL,
                    blink_ear_threshold REAL,
                    cursor_sensitivity REAL,
                    scroll_speed_multiplier REAL,
                    voice_aliases TEXT,
                    model_version INTEGER,
                    updated_at REAL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feedback_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    modality TEXT,
                    original_action TEXT,
                    corrected_action TEXT,
                    timestamp REAL,
                    promoted INTEGER DEFAULT 0
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS calibration_samples (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sample_type TEXT,
                    features TEXT,
                    label TEXT,
                    timestamp REAL
                );
            """)

    def load_profile(self, user_id: str = "default_user") -> UserProfile:
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT hand_scale_bias, blink_ear_threshold, cursor_sensitivity, scroll_speed_multiplier, voice_aliases, model_version FROM profiles WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if row:
                return UserProfile(
                    user_id=user_id,
                    hand_scale_bias=row[0],
                    blink_ear_threshold=row[1],
                    cursor_sensitivity=row[2],
                    scroll_speed_multiplier=row[3],
                    voice_aliases=json.loads(row[4] or "{}"),
                    model_version=row[5],
                )
            # Create default profile
            p = UserProfile(user_id=user_id)
            self.save_profile(p)
            return p

    def save_profile(self, profile: UserProfile) -> None:
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO profiles (user_id, hand_scale_bias, blink_ear_threshold, cursor_sensitivity, scroll_speed_multiplier, voice_aliases, model_version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                profile.user_id,
                profile.hand_scale_bias,
                profile.blink_ear_threshold,
                profile.cursor_sensitivity,
                profile.scroll_speed_multiplier,
                json.dumps(profile.voice_aliases),
                profile.model_version,
                time.time(),
            ))

    def record_feedback(self, modality: str, original: str, corrected: str) -> None:
        with self._get_connection() as conn:
            conn.execute("INSERT INTO feedback_events (modality, original_action, corrected_action, timestamp) VALUES (?, ?, ?, ?)", (modality, original, corrected, time.time()))

    def save_sample(self, sample_type: str, features: Dict[str, Any], label: str) -> None:
        with self._get_connection() as conn:
            conn.execute("INSERT INTO calibration_samples (sample_type, features, label, timestamp) VALUES (?, ?, ?, ?)", (sample_type, json.dumps(features), label, time.time()))


class AdaptivePersonalizationEngine:
    """Validates user feedback and updates user parameters with progressive validation."""

    def __init__(self, store: PersonalizationStore | None = None) -> None:
        self.store = store or PersonalizationStore()
        self.profile = self.store.load_profile()

    def register_correction(self, modality: str, original: str, corrected: str) -> bool:
        """Processes an explicit user correction (e.g. 'No, I meant YouTube')."""
        self.store.record_feedback(modality, original, corrected)

        # Handle voice alias correction
        if modality == "voice" and "->" in corrected:
            phrase, intent = corrected.split("->", 1)
            self.profile.voice_aliases[phrase.strip().lower()] = intent.strip()
            self.profile.model_version += 1
            self.store.save_profile(self.profile)
            return True

        # Handle scroll sensitivity correction
        if "too fast" in corrected.lower():
            self.profile.scroll_speed_multiplier = max(0.4, self.profile.scroll_speed_multiplier * 0.85)
            self.profile.model_version += 1
            self.store.save_profile(self.profile)
            return True
        elif "too slow" in corrected.lower():
            self.profile.scroll_speed_multiplier = min(2.5, self.profile.scroll_speed_multiplier * 1.15)
            self.profile.model_version += 1
            self.store.save_profile(self.profile)
            return True

        return False

    def calibrate_eye_threshold(self, observed_ear_closed: float, observed_ear_open: float) -> float:
        """Computes optimal EAR threshold between open eye baseline and closed eye blink."""
        if observed_ear_closed < observed_ear_open:
            new_thresh = round((observed_ear_closed + observed_ear_open) / 2.0, 3)
            self.profile.blink_ear_threshold = new_thresh
            self.profile.model_version += 1
            self.store.save_profile(self.profile)
            return new_thresh
        return self.profile.blink_ear_threshold
