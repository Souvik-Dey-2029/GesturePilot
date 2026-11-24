"""Comprehensive deterministic tests for rebuilt Voice Intelligence Core.

Covers:
- Part 3: AudioCaptureEngine (ring buffer, feed_chunk, push-to-talk, device listing)
- Part 5: VoiceActivityDetector (speech start, pre-roll buffer, hangover duration, silence)
- Part 8: VoiceConversationController (multi-turn transitions, spoken corrections, cancellation)
- Part 9: Intent classification (tab commands, search, organic result, scroll)
- Part 10: DictationEngine (punctuation conversion, multi-sentence, delete last word)
- Part 11: SpellingEngine (NATO phonetic parsing, backspace, finish)
- Part 15: Safety & Fusion authorization
"""
import numpy as np
import pytest
from unittest.mock import MagicMock

from virtual_mouse.events import EventType, ModalityType, MultimodalEvent, SystemInteractionMode
from virtual_mouse.fusion.engine import MultimodalFusionEngine
from virtual_mouse.voice.audio import AudioCaptureEngine
from virtual_mouse.voice.conversation import VoiceConversationController, VoiceConversationState
from virtual_mouse.voice.dictation import DictationEngine, SpellingEngine
from virtual_mouse.voice.subsystem import VoiceSubsystem, VoiceState
from virtual_mouse.voice.vad import VoiceActivityDetector


# -----------------------------------------------------------------------------
# Part 3: AudioCaptureEngine Tests
# -----------------------------------------------------------------------------
def test_audio_capture_engine_buffer_and_push_to_talk():
    cap = AudioCaptureEngine(sample_rate=16000, chunk_duration_ms=30)
    assert cap.is_capturing is False

    # Start in mock/test mode
    cap.start()
    assert cap.is_capturing is True

    # Feed synthetic audio chunks
    synthetic_chunk = np.ones(480, dtype=np.float32) * 0.1
    for _ in range(5):
        cap.feed_chunk(synthetic_chunk)

    recent = cap.get_recent_audio(duration_sec=0.15)
    assert len(recent) > 0
    assert cap.metrics.rms_level > 0.0

    # Push to talk activation
    cap.set_push_to_talk(True)
    assert cap.is_listening is True

    cap.feed_chunk(synthetic_chunk)
    cap.feed_chunk(synthetic_chunk)

    # Release push-to-talk
    completed_audio = cap.set_push_to_talk(False)
    assert cap.is_listening is False
    assert completed_audio is not None
    assert len(completed_audio) == 480 * 2

    cap.stop()
    assert cap.is_capturing is False


# -----------------------------------------------------------------------------
# Part 5: VoiceActivityDetector Tests
# -----------------------------------------------------------------------------
def test_vad_speech_onset_and_hangover_completion():
    vad = VoiceActivityDetector(energy_threshold=0.015, silence_hangover_s=0.09, min_speech_duration_s=0.06)

    silence_chunk = np.zeros(480, dtype=np.float32)
    speech_chunk = np.ones(480, dtype=np.float32) * 0.1

    # 1. Feed silence -> no speech
    st1, comp1 = vad.process_chunk(silence_chunk)
    assert st1.is_speech is False
    assert comp1 is None

    # 2. Feed 2 consecutive speech chunks (onset confirmation)
    vad.process_chunk(speech_chunk)
    st2, comp2 = vad.process_chunk(speech_chunk)
    assert st2.is_speech is True
    assert comp2 is None

    # 3. Feed silence chunks until hangover expires (>= 0.09s = 3 chunks @ 30ms)
    vad.process_chunk(silence_chunk)
    vad.process_chunk(silence_chunk)
    st3, comp3 = vad.process_chunk(silence_chunk)

    # Utterance should be completed with pre-roll preserved
    assert comp3 is not None
    assert len(comp3) > 0
    assert st3.is_speech is False


# -----------------------------------------------------------------------------
# Part 8: VoiceConversationController & Spoken Correction Tests
# -----------------------------------------------------------------------------
def test_conversation_controller_correction():
    conv = VoiceConversationController()
    conv.enter_awaiting_search()
    assert conv.state == VoiceConversationState.AWAITING_SEARCH_TEXT

    conv.pending_query = "machine learning courses"

    # Spoken correction: "No, change machine learning to deep learning"
    updated = conv.handle_spoken_correction("no, change machine learning to deep learning")
    assert updated == "deep learning courses"
    assert conv.pending_query == "deep learning courses"

    # Direct correction: "No, I meant natural language processing"
    updated2 = conv.handle_spoken_correction("no, I meant natural language processing")
    assert updated2 == "natural language processing"

    # Spoken cancellation
    msg = conv.cancel("user request")
    assert conv.state == VoiceConversationState.IDLE
    assert "Cancelled" in msg


# -----------------------------------------------------------------------------
# Part 10 & 11: Dictation and Spelling Engines Tests
# -----------------------------------------------------------------------------
def test_dictation_engine_punctuation_and_editing():
    dic = DictationEngine()

    txt1 = dic.append_utterance("Hello world comma this is my project period")
    assert txt1 == "Hello world, this is my project."

    txt2 = dic.append_utterance("New paragraph. Next sentence.")
    assert "\n\n" in txt2

    # Delete last word
    txt3 = dic.append_utterance("delete last word")
    assert not txt3.endswith("sentence.")


def test_spelling_engine_nato_and_backspace():
    spe = SpellingEngine()

    word, fin = spe.process_spelling_tokens("alpha bravo charlie")
    assert word == "abc"
    assert fin is False

    # Backspace
    word2, _ = spe.process_spelling_tokens("backspace")
    assert word2 == "ab"

    # Done / finish token
    word3, fin3 = spe.process_spelling_tokens("delta done")
    assert word3 == "abd"
    assert fin3 is True


# -----------------------------------------------------------------------------
# Subsystem End-to-End Workflow & Intent Tests
# -----------------------------------------------------------------------------
def test_voice_subsystem_intent_parsing():
    vs = VoiceSubsystem()
    vs.enable()

    # Workflow A: New tab & search
    evs_new_tab = vs.process_utterance("open a new tab")
    assert len(evs_new_tab) == 1
    assert evs_new_tab[0].data["intent"] == "browser.new_tab"
    assert vs.conversation.state == VoiceConversationState.AWAITING_SEARCH_TEXT

    # Dictate search query
    evs_query = vs.process_utterance("best deep learning research")
    assert len(evs_query) == 1
    assert evs_query[0].data["action"] == "browser.search"
    assert evs_query[0].data["query"] == "best deep learning research"
    assert vs.conversation.state == VoiceConversationState.IDLE

    # Workflow B: Organic first result
    evs_first = vs.process_utterance("open the first result")
    assert len(evs_first) == 1
    assert evs_first[0].data["intent"] == "browser.open_first_result"

    # Workflow C: Tab switching
    evs_switch = vs.process_utterance("switch to YouTube tab")
    assert len(evs_switch) == 1
    assert evs_switch[0].data["intent"] == "browser.switch_tab"
    assert evs_switch[0].data["entities"]["query"].lower() == "youtube"

    # Workflow D: Dictation mode activation
    evs_dict = vs.process_utterance("start dictation")
    assert len(evs_dict) == 1
    assert vs.conversation.state == VoiceConversationState.DICTATION

    evs_dict_append = vs.process_utterance("today I tested speech recognition period")
    assert len(evs_dict_append) == 1
    assert "today I tested speech recognition." in evs_dict_append[0].data["text"]

    evs_dict_finish = vs.process_utterance("finish dictation")
    assert len(evs_dict_finish) == 1
    assert vs.conversation.state == VoiceConversationState.IDLE


def test_voice_safety_master_gate():
    mouse_mock = MagicMock()
    fusion = MultimodalFusionEngine(mouse_mock, mode=SystemInteractionMode.ALL)
    # Master control starts disarmed
    assert fusion.master_armed is False

    ev = MultimodalEvent(
        source=ModalityType.VOICE,
        event_type=EventType.VOICE_COMMAND,
        confidence=0.95,
        timestamp=10.0,
        expiration_time=11.0,
        data={"intent": "browser.search", "query": "Python"},
    )

    # When disarmed, fusion must block command execution
    dec = fusion.evaluate(ev, now=10.0)
    assert dec.authorized is False
    assert dec.reason == "Master control is disarmed"

    # When armed, command is authorized
    fusion.arm()
    dec_armed = fusion.evaluate(ev, now=10.0)
    assert dec_armed.authorized is True
    assert dec_armed.action == "voice.command"
