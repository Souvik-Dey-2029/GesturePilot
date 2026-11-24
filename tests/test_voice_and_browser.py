"""Automated tests for Voice Subsystem, Offline ASR, Audio Capture, and Browser Automation."""
from __future__ import annotations

import faster_whisper  # Pre-load CTranslate2 / av DLLs safely before sounddevice
import http.client
import json
import time
import numpy as np
import pytest

from virtual_mouse.browser.bridge import BrowserBridge
from virtual_mouse.controller import ModalityAvailability, ModalityStatus, RuntimeController
from virtual_mouse.events import EventType, ModalityType, SystemInteractionMode
from virtual_mouse.mouse.controller import MouseController
from virtual_mouse.pipeline import Pipeline
from virtual_mouse.safety import SafetyConfig, SafetyController
from virtual_mouse.voice.asr import WhisperASR
from virtual_mouse.voice.audio import AudioCapture
from virtual_mouse.voice.subsystem import NATO_PHONETIC, VoiceIntent, VoiceState, VoiceSubsystem


class DummyMouse:
    def __init__(self) -> None:
        self.scrolled: list[int] = []

    def scroll_wheel(self, amount: int) -> None:
        self.scrolled.append(amount)

    def release_all(self) -> None:
        pass


class DummyPipeline:
    def __init__(self) -> None:
        self.safety = SafetyController(SafetyConfig())
        self.mouse_controller = DummyMouse()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class MockASR(WhisperASR):
    def __init__(self, return_transcript: str = "open new tab") -> None:
        super().__init__()
        self.return_transcript = return_transcript
        self._loaded = True

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load_model(self) -> bool:
        return True

    def transcribe(self, audio: np.ndarray, **kwargs) -> str:
        return self.return_transcript


# -- AudioCapture Tests --
def test_audio_capture_ring_buffer_and_push_to_talk():
    cap = AudioCapture(sample_rate=16000, chunk_duration_ms=20, buffer_duration_sec=1.0)
    # Simulate feeding chunks
    chunk = np.full(320, 0.05, dtype=np.float32)
    cap.feed_chunk(chunk)
    assert len(cap.get_recent_audio(0.1)) > 0
    assert cap.calculate_energy(chunk) > 0.01

    # Push to talk
    cap.set_push_to_talk(True)
    assert cap.is_listening is True
    cap.feed_chunk(chunk)
    cap.feed_chunk(chunk)
    completed = cap.set_push_to_talk(False)
    assert cap.is_listening is False
    assert completed is not None
    assert len(completed) == 640


# Fixture to mock live audio hardware stream in tests so soundcard callbacks don't fire during test teardown
@pytest.fixture(autouse=True)
def mock_audio_stream(monkeypatch):
    monkeypatch.setattr(AudioCapture, "start", lambda self, on_utterance_ready=None: True)
    monkeypatch.setattr(AudioCapture, "stop", lambda self: None)


# -- Voice Subsystem Conversational State Machine Tests --
def test_workflow_a_new_tab_and_search_dictation():
    voice = VoiceSubsystem()
    voice.enable()

    # Step 1: Open new tab
    events1 = voice.process_utterance("open new tab")
    assert len(events1) == 1
    assert events1[0].event_type == EventType.VOICE_COMMAND
    assert events1[0].data["intent"] == "browser.new_tab"
    assert voice.state == VoiceState.AWAITING_SEARCH_TEXT

    # Step 2: Dictate search query
    events2 = voice.process_utterance("python faster whisper benchmarks")
    assert len(events2) == 1
    assert events2[0].event_type == EventType.VOICE_DICTATION
    assert events2[0].data["action"] == "browser.search"
    assert events2[0].data["query"] == "python faster whisper benchmarks"
    assert voice.state == VoiceState.IDLE


def test_workflow_b_spelling_mode_with_nato_phonetic():
    voice = VoiceSubsystem()
    voice.enable()

    # Step 1: Trigger spelling mode
    events1 = voice.process_utterance("spell mode")
    assert len(events1) == 1
    assert events1[0].data["intent"] == "system.spelling_active"
    assert voice.state == VoiceState.SPELLING

    # Step 2: Spell using NATO phonetic and individual letters
    voice.process_utterance("hotel echo lima lima oscar")
    # Step 3: Undo last letter, replace
    voice.process_utterance("backspace")
    voice.process_utterance("oscar")
    # Step 4: Finish spelling
    events2 = voice.process_utterance("done")
    assert len(events2) == 1
    assert events2[0].event_type == EventType.VOICE_SPELLING
    assert events2[0].data["action"] == "browser.search"
    assert events2[0].data["spelled_word"] == "hello"
    assert voice.state == VoiceState.IDLE


def test_workflow_c_first_organic_result():
    voice = VoiceSubsystem()
    voice.enable()

    events = voice.process_utterance("open first result")
    assert len(events) == 1
    assert events[0].data["intent"] == "browser.open_first_result"


def test_workflow_d_tab_switching_and_conservative_closing():
    voice = VoiceSubsystem()
    voice.enable()

    # Tab switching
    ev_switch = voice.process_utterance("switch to youtube tab")
    assert len(ev_switch) == 1
    assert ev_switch[0].data["intent"] == "browser.switch_tab"
    assert ev_switch[0].data["entities"]["query"] == "youtube"

    # Tab closing requiring confirmation
    ev_close = voice.process_utterance("close instagram tab")
    assert len(ev_close) == 1
    assert ev_close[0].data["needs_confirmation"] is True
    assert voice.state == VoiceState.AWAITING_CONFIRMATION

    # Confirm action
    ev_confirm = voice.process_utterance("yes")
    assert len(ev_confirm) == 1
    assert ev_confirm[0].data["intent"] == "browser.close_tab"
    assert ev_confirm[0].data["entities"]["query"] == "instagram"
    assert voice.state == VoiceState.IDLE


def test_cancellation_and_aliases():
    voice = VoiceSubsystem()
    voice.enable()

    voice.process_utterance("open new tab")
    assert voice.state == VoiceState.AWAITING_SEARCH_TEXT
    # Cancel resets to IDLE
    ev_cancel = voice.process_utterance("cancel that")
    assert len(ev_cancel) == 1
    assert ev_cancel[0].event_type == EventType.VOICE_CANCEL
    assert voice.state == VoiceState.IDLE

    # Personalized alias
    voice.add_alias("github dash", "browser.open_first_result")
    ev_alias = voice.process_utterance("github dash")
    assert len(ev_alias) == 1
    assert ev_alias[0].data["intent"] == "browser.open_first_result"


# -- BrowserBridge Tests --
def test_browser_bridge_loopback_server():
    bridge = BrowserBridge(host="127.0.0.1", port=8768)
    started = bridge.start()
    assert started is True
    assert bridge.is_running is True

    try:
        # Enqueue command
        bridge.send_command("cmd-1", "browser.new_tab", {})

        # Poll endpoint via http.client
        conn = http.client.HTTPConnection("127.0.0.1", 8768, timeout=2.0)
        conn.request("GET", "/api/poll")
        resp = conn.getresponse()
        assert resp.status == 200
        data = json.loads(resp.read().decode("utf-8"))
        assert data["id"] == "cmd-1"
        assert data["command"]["action"] == "browser.new_tab"

        # Post result back
        result_payload = json.dumps({"id": "cmd-1", "result": {"success": True, "tabId": 12}}).encode("utf-8")
        conn.request("POST", "/api/result", body=result_payload, headers={"Content-Type": "application/json"})
        post_resp = conn.getresponse()
        assert post_resp.status == 200
        ack = json.loads(post_resp.read().decode("utf-8"))
        assert ack["status"] == "ok"
        conn.close()

        # Check result in bridge
        res = bridge.get_result("cmd-1")
        assert res["success"] is True
        assert res["tabId"] == 12

    finally:
        bridge.stop()
        assert bridge.is_running is False


# -- RuntimeController Integration with Voice and Browser --
def test_runtime_controller_voice_and_browser_dispatch(monkeypatch):
    pipeline = DummyPipeline()
    bridge = BrowserBridge(host="127.0.0.1", port=8769)
    voice = VoiceSubsystem(asr=MockASR("open new tab"))

    # In unit tests, mock audio start so real hardware sound card streams aren't invoked during test teardown
    monkeypatch.setattr(voice.audio, "start", lambda on_utterance_ready=None: True)
    monkeypatch.setattr(voice.audio, "stop", lambda: None)

    ctrl = RuntimeController(
        pipeline=pipeline,
        voice_subsystem=voice,
        browser_bridge=bridge,
    )

    # Initially voice disabled
    assert ctrl.voice_active is False

    # Toggle voice
    res = ctrl.toggle_voice_mode()
    assert res is True
    assert ctrl.voice_active is True
    assert bridge.is_running is True

    # Process voice utterance through controller
    events = voice.process_utterance("open first result")
    ctrl.dispatch_voice_events(events)

    # Verify bridge received command
    assert not bridge.command_queue.empty()
    cmd = bridge.command_queue.get_nowait()
    assert cmd["command"]["action"] == "browser.open_first_result"

    # Clean shutdown
    ctrl.shutdown()
    assert bridge.is_running is False
    assert voice.enabled is False
    assert pipeline.closed is True
