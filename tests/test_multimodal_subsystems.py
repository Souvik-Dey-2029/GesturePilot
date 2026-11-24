"""Unit and integration tests for multimodal events, eye, voice, fusion, and personalization."""
import time
import pytest
from virtual_mouse.events import EventBus, EventType, ModalityType, MultimodalEvent, SystemInteractionMode
from virtual_mouse.eye.subsystem import EyeCalibration, EyeSubsystem, FaceObservation
from virtual_mouse.fusion.engine import MultimodalFusionEngine
from virtual_mouse.hand.subsystem import HandSubsystem
from virtual_mouse.mouse.backend import FakeMouseBackend
from virtual_mouse.mouse.controller import MouseController
from virtual_mouse.personalization.engine import AdaptivePersonalizationEngine, PersonalizationStore, UserProfile
from virtual_mouse.safety import SafetyController
from virtual_mouse.voice.subsystem import VoiceState, VoiceSubsystem


def test_event_staleness():
    now = time.monotonic()
    ev_fresh = MultimodalEvent(ModalityType.HAND, EventType.LEFT_CLICK, 0.95, now, now + 0.5)
    assert not ev_fresh.is_stale(now)

    ev_stale = MultimodalEvent(ModalityType.HAND, EventType.LEFT_CLICK, 0.95, now - 1.0, now - 0.1)
    assert ev_stale.is_stale(now)


def test_event_bus_publish():
    bus = EventBus()
    received = []
    bus.subscribe(EventType.LEFT_CLICK, lambda e: received.append(e))

    now = time.monotonic()
    ev = MultimodalEvent(ModalityType.HAND, EventType.LEFT_CLICK, 0.95, now, now + 0.5)
    published = bus.publish(ev, now)
    assert published is True
    assert len(received) == 1


def test_eye_subsystem_double_and_triple_blink():
    sub = EyeSubsystem()
    sub.enable()

    t = 1.0
    # Create face with open eyes (blink score 0.0)
    face_open = FaceObservation(landmarks=(), blendshapes={"eyeBlinkLeft": 0.0, "eyeBlinkRight": 0.0})
    # Create face with closed eyes (blink score 0.9)
    face_closed = FaceObservation(landmarks=(), blendshapes={"eyeBlinkLeft": 0.9, "eyeBlinkRight": 0.9})

    # Blink 1
    sub.process(face_closed, t)
    t += 0.15
    events1 = sub.process(face_open, t)
    assert len(events1) == 0  # single blink ignored

    # Blink 2 (Double blink window)
    t += 0.20
    sub.process(face_closed, t)
    t += 0.15
    sub.process(face_open, t)

    # Allow sequence window to finalize double blink (sequence_window_s is 0.85s)
    t += 0.60
    events2 = sub.process(face_open, t)
    assert len(events2) == 1
    assert events2[0].event_type == EventType.DOUBLE_BLINK
    assert events2[0].data["action"] == "scroll_down"


def test_voice_subsystem_intent_and_spelling():
    voice = VoiceSubsystem()
    voice.enable()

    # 1. New tab & search workflow
    evs = voice.process_utterance("open a new tab")
    assert len(evs) == 1
    assert voice.state == VoiceState.DICTATION_MODE

    # 2. Dictate search query
    evs_search = voice.process_utterance("artificial intelligence research")
    assert len(evs_search) == 1
    assert evs_search[0].event_type == EventType.VOICE_DICTATION
    assert evs_search[0].data["query"] == "artificial intelligence research"
    assert voice.state == VoiceState.IDLE

    # 3. Spelling mode
    voice.process_utterance("spell mode")
    assert voice.state == VoiceState.SPELLING_MODE

    voice.process_utterance("kilo")
    voice.process_utterance("india")
    evs_spell = voice.process_utterance("done")
    assert len(evs_spell) == 1
    assert evs_spell[0].data["spelled_word"] == "ki"
    assert voice.state == VoiceState.IDLE


def test_multimodal_fusion_and_action_policy():
    from virtual_mouse.safety import SafetyConfig
    from virtual_mouse.types import HandObservation, Landmark, LandmarkId, NUM_LANDMARKS
    backend = FakeMouseBackend()
    safety = SafetyController(SafetyConfig())
    safety.enable()

    # Feed reliable tracking streak to satisfy SafetyController.can_emit()
    hand_lms = [Landmark(0.5, 0.5, 0.0)] * NUM_LANDMARKS
    hand = HandObservation(tuple(hand_lms), "Right", 0.95)
    for _ in range(3):
        safety.update(hand, time.monotonic())

    mouse = MouseController(backend, safety)
    fusion = MultimodalFusionEngine(mouse, SystemInteractionMode.HAND_ONLY)

    # Disarmed test
    now = time.monotonic()
    ev_click = MultimodalEvent(ModalityType.HAND, EventType.LEFT_CLICK, 0.95, now, now + 1.0)
    dec_disarmed = fusion.evaluate(ev_click, now)
    assert dec_disarmed.authorized is False
    assert dec_disarmed.action == "disarmed"

    # Armed test
    fusion.arm()
    dec_armed = fusion.evaluate(ev_click, now)
    assert dec_armed.authorized is True
    assert dec_armed.action == "mouse.left_click"
    assert ("left_down", ()) in backend.events
    assert ("left_up", ()) in backend.events


def test_personalization_store_and_adaptation(tmp_path):
    db_file = tmp_path / "test_profile.db"
    store = PersonalizationStore(db_file)
    engine = AdaptivePersonalizationEngine(store)

    # Register voice alias correction
    engine.register_correction("voice", "yt", "youtube -> browser.switch_tab")
    assert engine.profile.voice_aliases.get("youtube") == "browser.switch_tab"
    assert engine.profile.model_version > 1

    # Reload from store to verify persistence
    p_reloaded = store.load_profile()
    assert p_reloaded.voice_aliases.get("youtube") == "browser.switch_tab"
