"""Central Runtime Controller and Modality Lifecycle Manager.

Manages active interaction modes (HAND, EYE, BOTH, VOICE, ALL), master arm/disarm status,
resource lifecycle (lazy init, clean shutdown), emergency stop overrides, and honest
unavailable states for incomplete subsystems (FaceLandmarker model missing, ASR engine missing).
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .browser.bridge import BrowserBridge
from .detection.face_detector import FaceDetector
from .detection.model_assets import ensure_face_model
from .events import EventType, SystemInteractionMode, MultimodalEvent, ModalityType
from .eye.subsystem import EyeSubsystem, EyeTelemetry
from .fusion.engine import MultimodalFusionEngine, FusionDecision
from .personalization.engine import AdaptivePersonalizationEngine, PersonalizationStore
from .pipeline import Pipeline
from .safety import SafetyController
from .voice.subsystem import VoiceSubsystem

log = logging.getLogger(__name__)


class ModalityAvailability(Enum):
    AVAILABLE = "available"
    UNAVAILABLE_MODEL_MISSING = "unavailable: model missing"
    UNAVAILABLE_NO_AUDIO_DEVICE = "unavailable: no audio capture device"
    UNAVAILABLE_NO_ASR_ENGINE = "unavailable: speech recognizer not installed"
    NOT_IMPLEMENTED = "not implemented"


@dataclass(frozen=True, slots=True)
class ModalityStatus:
    mode: SystemInteractionMode
    master_armed: bool
    hand_active: bool
    eye_active: bool
    voice_active: bool
    hand_availability: ModalityAvailability
    eye_availability: ModalityAvailability
    voice_availability: ModalityAvailability
    last_status_message: str


class RuntimeController:
    """Central lifecycle and mode controller.
    
    Invariants:
    1. Preserves existing working Pipeline for Hand mode.
    2. Does not pretend Eye or Voice modes work when required models or libraries are absent.
    3. Starts DISARMED by default.
    4. Emergency stop overrides all modalities immediately.
    5. Lazy loads and safely shuts down modality resources.
    """

    def __init__(
        self,
        pipeline: Pipeline,
        face_model_path: Path | str = "models/face_landmarker.task",
        face_detector: Optional[FaceDetector] = None,
        eye_subsystem: Optional[EyeSubsystem] = None,
        voice_subsystem: Optional[VoiceSubsystem] = None,
        browser_bridge: Optional[BrowserBridge] = None,
        fusion_engine: Optional[MultimodalFusionEngine] = None,
        personalization_engine: Optional[AdaptivePersonalizationEngine] = None,
        on_status_change: Optional[Callable[[ModalityStatus], None]] = None,
    ) -> None:
        self._pipeline = pipeline
        self._mouse = pipeline.mouse_controller
        self._face_model_path = Path(face_model_path)
        self._on_status_change = on_status_change

        # Injected or lazily constructed eye components
        self._face_detector = face_detector
        self.eye = eye_subsystem or EyeSubsystem()

        # Injected or lazily constructed voice and browser components
        self.voice = voice_subsystem or VoiceSubsystem()
        self.browser = browser_bridge or BrowserBridge()

        # Multimodal fusion and personalization engines
        self.personalization = personalization_engine or AdaptivePersonalizationEngine()
        self.fusion = fusion_engine or MultimodalFusionEngine(self._mouse, mode=SystemInteractionMode.HAND_ONLY)

        # Apply profile parameters to subsystems
        self._apply_user_profile()

        # Interaction Mode & States
        self._mode = SystemInteractionMode.HAND_ONLY
        self._master_armed = False
        self._voice_enabled = False
        self._diagnostic_mode = False
        self._last_message = "Ready. Mode: HAND (Disarmed). Press 'm' to arm."

        # Modality worker references (lazy)
        self._hand_active = True
        self._eye_active = False
        self._voice_active = False
        self._push_to_talk_active = False

    def _apply_user_profile(self) -> None:
        """Applies loaded personalization profile to eye detector and voice aliases."""
        prof = self.personalization.profile
        if hasattr(self.eye, "calib"):
            self.eye.calib.ear_closed_threshold = prof.blink_ear_threshold
            if hasattr(self.eye, "apply_calibration"):
                self.eye.apply_calibration(self.eye.calib)
        # Register voice aliases into voice subsystem if present
        if hasattr(self.voice, "add_alias"):
            for phrase, intent in prof.voice_aliases.items():
                self.voice.add_alias(phrase, intent)

    @property
    def eye_active(self) -> bool:
        return self._eye_active

    @property
    def eye_telemetry(self) -> EyeTelemetry:
        return self.eye.telemetry

    @property
    def voice_active(self) -> bool:
        return self._voice_active

    def _ensure_face_detector(self) -> bool:
        if not self._face_model_path.is_file():
            try:
                self._last_message = f"Downloading face model to {self._face_model_path}..."
                log.info(self._last_message)
                self._notify_status()
                ensure_face_model(self._face_model_path)
            except Exception as dl_err:
                log.error("Failed on-demand download of face model: %s", dl_err)
                return False

        if self._face_detector is None:
            if not self._face_model_path.is_file():
                return False
            self._face_detector = FaceDetector(model_path=self._face_model_path)
        if not self._face_detector.is_open:
            self._face_detector.open()
        return True

    def _release_face_detector(self) -> None:
        if self._face_detector is not None and self._face_detector.is_open:
            self._face_detector.close()
        self.eye.disable()

    def _ensure_voice_subsystem(self) -> bool:
        if not self.voice.enabled:
            started = self.voice.enable()
            if not started:
                log.warning("Voice audio capture could not start.")
        if not self.browser.is_running:
            self.browser.start()
        return True

    def _release_voice_subsystem(self) -> None:
        if self.voice.enabled:
            self.voice.disable()
        if self.browser.is_running:
            self.browser.stop()

    @property
    def safety(self) -> SafetyController:
        return self._pipeline.safety

    @property
    def pipeline(self) -> Pipeline:
        return self._pipeline

    @property
    def mode(self) -> SystemInteractionMode:
        return self._mode

    @property
    def master_armed(self) -> bool:
        return self._master_armed

    @property
    def diagnostic_mode(self) -> bool:
        return self._diagnostic_mode

    @property
    def last_message(self) -> str:
        return self._last_message

    def toggle_diagnostic(self) -> bool:
        self._diagnostic_mode = not self._diagnostic_mode
        self._last_message = f"Diagnostic HUD: {'ON' if self._diagnostic_mode else 'OFF'}"
        self._notify_status()
        return self._diagnostic_mode

    # -- Availability Checks (Honest Capability Inspection) -----------------------
    def check_hand_availability(self) -> ModalityAvailability:
        return ModalityAvailability.AVAILABLE

    def check_eye_availability(self) -> ModalityAvailability:
        if not self._face_model_path.is_file():
            return ModalityAvailability.UNAVAILABLE_MODEL_MISSING
        return ModalityAvailability.AVAILABLE

    def check_voice_availability(self) -> ModalityAvailability:
        try:
            import sounddevice  # noqa: F401
            import faster_whisper  # noqa: F401
            return ModalityAvailability.AVAILABLE
        except ImportError:
            return ModalityAvailability.UNAVAILABLE_NO_ASR_ENGINE

    # -- Mode Switching Commands --------------------------------------------------
    def select_hand_mode(self) -> bool:
        """Key 'e': Hand only mode. Validated working baseline."""
        self._mode = SystemInteractionMode.HAND_ONLY
        self._hand_active = True
        self._eye_active = False
        self.fusion.set_mode(self._mode)
        self._release_face_detector()
        self._last_message = "Mode switched to HAND ONLY (Face detector released)."
        log.info(self._last_message)
        self._notify_status()
        return True

    def select_eye_mode(self) -> bool:
        """Key 'i': Eye only mode. Attempts on-demand download if missing."""
        if not self._face_model_path.is_file():
            self._last_message = f"Face model missing. Attempting on-demand download to '{self._face_model_path.name}'..."
            log.info(self._last_message)
            self._notify_status()
            try:
                ensure_face_model(self._face_model_path)
            except Exception as dl_err:
                self._last_message = f"EYE mode unavailable: download failed ({dl_err}). Remaining in {self._mode.value}."
                log.warning(self._last_message)
                self._notify_status()
                return False

        avail = self.check_eye_availability()
        if avail != ModalityAvailability.AVAILABLE:
            self._last_message = f"EYE mode unavailable: {avail.value} ('{self._face_model_path.name}'). Remaining in {self._mode.value}."
            log.warning(self._last_message)
            self._notify_status()
            return False

        try:
            self._ensure_face_detector()
            self.eye.enable()
        except Exception as exc:
            self._last_message = f"Error opening FaceDetector: {exc}. Remaining in {self._mode.value}."
            log.error(self._last_message)
            self._notify_status()
            return False

        self._mode = SystemInteractionMode.EYE_ONLY
        self._hand_active = False
        self._eye_active = True
        self.fusion.set_mode(self._mode)
        self._last_message = "Mode switched to EYE ONLY (Hand inference idle, Face active)."
        log.info(self._last_message)
        self._notify_status()
        return True

    def select_both_mode(self) -> bool:
        """Key 'b': Hand + Eye mode. Attempts on-demand download if missing."""
        if not self._face_model_path.is_file():
            self._last_message = f"Face model missing. Attempting on-demand download to '{self._face_model_path.name}'..."
            log.info(self._last_message)
            self._notify_status()
            try:
                ensure_face_model(self._face_model_path)
            except Exception as dl_err:
                self._last_message = f"BOTH mode unavailable: Eye download failed ({dl_err}). Remaining in {self._mode.value}."
                log.warning(self._last_message)
                self._notify_status()
                return False

        avail = self.check_eye_availability()
        if avail != ModalityAvailability.AVAILABLE:
            self._last_message = f"BOTH mode unavailable: Eye subsystem {avail.value}. Remaining in {self._mode.value}."
            log.warning(self._last_message)
            self._notify_status()
            return False

        try:
            self._ensure_face_detector()
            self.eye.enable()
        except Exception as exc:
            self._last_message = f"Error opening FaceDetector: {exc}. Remaining in {self._mode.value}."
            log.error(self._last_message)
            self._notify_status()
            return False

        self._mode = SystemInteractionMode.BOTH
        self._hand_active = True
        self._eye_active = True
        self.fusion.set_mode(self._mode)
        self._last_message = "Mode switched to BOTH (Hand + Face active concurrently)."
        log.info(self._last_message)
        self._notify_status()
        return True

    def toggle_voice_mode(self) -> bool:
        """Key 'v': Voice toggle independently. Honest check."""
        avail = self.check_voice_availability()
        if avail != ModalityAvailability.AVAILABLE:
            self._voice_enabled = False
            self._voice_active = False
            self._last_message = f"VOICE unavailable: {avail.value}. Audio capture/ASR not installed."
            log.warning(self._last_message)
            self._notify_status()
            return False

        self._voice_enabled = not self._voice_enabled
        self._voice_active = self._voice_enabled
        if self._voice_enabled:
            self._ensure_voice_subsystem()
            self._last_message = "Voice input ENABLED (ASR & Browser Bridge ready)."
        else:
            self._release_voice_subsystem()
            self._last_message = "Voice input DISABLED."
        log.info(self._last_message)
        self._notify_status()
        return self._voice_enabled

    def select_all_mode(self) -> bool:
        """Key 'a': All modalities mode. Requires Hand, Eye, and Voice."""
        eye_avail = self.check_eye_availability()
        voice_avail = self.check_voice_availability()

        if eye_avail != ModalityAvailability.AVAILABLE or voice_avail != ModalityAvailability.AVAILABLE:
            missing = []
            if eye_avail != ModalityAvailability.AVAILABLE:
                missing.append(f"Eye: {eye_avail.value}")
            if voice_avail != ModalityAvailability.AVAILABLE:
                missing.append(f"Voice: {voice_avail.value}")
            self._last_message = f"ALL mode unavailable. Missing: {', '.join(missing)}."
            log.warning(self._last_message)
            self._notify_status()
            return False

        try:
            self._ensure_face_detector()
            self.eye.enable()
        except Exception as exc:
            self._last_message = f"Error initializing Eye in ALL mode: {exc}"
            log.error(self._last_message)
            self._notify_status()
            return False

        self._ensure_voice_subsystem()
        self._mode = SystemInteractionMode.ALL
        self._hand_active = True
        self._eye_active = True
        self._voice_enabled = True
        self._voice_active = True
        self.fusion.set_mode(self._mode)
        self._last_message = "Mode switched to ALL (Hand + Eye + Voice)."
        log.info(self._last_message)
        self._notify_status()
        return True

    # -- Master Arm / Disarm & Safety Controls -----------------------------------
    def toggle_master_arm(self) -> bool:
        """Key 'm': Toggles master control arming."""
        if self.safety.estop.is_set:
            self._last_message = "Cannot arm while emergency stop is latched! Press 'r' first."
            log.warning(self._last_message)
            self._notify_status()
            return False

        if self._master_armed:
            self.disarm()
        else:
            self.arm()
        return self._master_armed

    def arm(self) -> bool:
        if self.safety.estop.is_set:
            return False
        self._master_armed = True
        self.safety.enable()
        self.fusion.arm()
        self._last_message = "Master control ARMED. Mouse control active."
        log.info(self._last_message)
        self._notify_status()
        return True

    def disarm(self) -> None:
        self._master_armed = False
        self.safety.disable()
        self.fusion.disarm()
        self._mouse.release_all()
        self._last_message = "Master control DISARMED. Mouse control paused."
        log.info(self._last_message)
        self._notify_status()

    def emergency_stop(self, reason: str = "manual") -> None:
        """Space / X: Immediate emergency stop across all modalities."""
        self._master_armed = False
        self.safety.emergency_stop(reason)
        self.fusion.disarm()
        self._mouse.release_all()
        self._last_message = f"EMERGENCY STOP LATCHED: {reason}. Press 'r' to re-arm."
        log.warning(self._last_message)
        self._notify_status()

    def recover(self) -> None:
        """Key 'r': Clear emergency stop latch. Leaves master control DISARMED."""
        self.safety.acknowledge_emergency_stop()
        self._master_armed = False
        self._last_message = "Emergency stop acknowledged. Master control remains DISARMED. Press 'm' to arm."
        log.info(self._last_message)
        self._notify_status()

    def toggle_push_to_talk(self) -> bool:
        """Toggles push-to-talk recording state."""
        if not self._voice_enabled:
            return False
        self._push_to_talk_active = not self._push_to_talk_active
        audio = self.voice.audio.set_push_to_talk(self._push_to_talk_active)
        if not self._push_to_talk_active and audio is not None and len(audio) > 0:
            self._last_message = "Transcribing voice input..."
            text = self.voice.asr.transcribe(audio)
            if text:
                events = self.voice.process_utterance(text)
                self.dispatch_voice_events(events)
        return self._push_to_talk_active

    # -- Key Dispatcher -----------------------------------------------------------
    def handle_key(self, key_code: int) -> bool:
        """Dispatches keyboard inputs. Returns True if application should quit."""
        if key_code in (ord("q"), 27):  # Q or Esc
            self.shutdown()
            return True

        if key_code in (ord(" "), ord("x"), ord("X")):
            self.emergency_stop("keyboard")
        elif key_code in (ord("r"), ord("R")):
            self.recover()
        elif key_code in (ord("m"), ord("M")):
            self.toggle_master_arm()
        elif key_code in (ord("e"), ord("E")):
            self.select_hand_mode()
        elif key_code in (ord("i"), ord("I")):
            self.select_eye_mode()
        elif key_code in (ord("b"), ord("B")):
            self.select_both_mode()
        elif key_code in (ord("v"), ord("V")):
            self.toggle_voice_mode()
        elif key_code in (ord("a"), ord("A")):
            self.select_all_mode()
        elif key_code in (ord("d"), ord("D")):
            self.toggle_diagnostic()
        elif key_code in (ord("t"), ord("T"), 0, 16):
            # Push-to-talk key shortcut: 'T' or Ctrl+Space (handled via 0/16 or T)
            self.toggle_push_to_talk()
        elif key_code in (ord("c"), ord("C")):
            self._last_message = "Calibration requested (run 'virtual-mouse-calibrate')."
            log.info(self._last_message)
            self._notify_status()

        return False

    def dispatch_voice_events(self, events: List[Any]) -> None:
        """Dispatches validated voice events to the browser bridge or mouse system."""
        for ev in events:
            ev_data = getattr(ev, "data", {})
            intent = ev_data.get("intent") or ev_data.get("action")
            log.info("Dispatching voice event: %s data=%s", intent, ev_data)

            cmd_id = f"voice-{uuid.uuid4().hex[:8]}"
            if intent in ("browser.new_tab", "browser.open_new_tab_and_search"):
                self.browser.send_command(cmd_id, "browser.new_tab", {})
                self._last_message = "Browser: Opening new tab..."
            elif intent == "browser.search":
                query = ev_data.get("query") or ev_data.get("spelled_word", "")
                self.browser.send_command(cmd_id, "browser.search", {"query": query})
                self._last_message = f"Browser: Searching '{query}'..."
            elif intent == "browser.switch_tab":
                target = ev_data.get("entities", {}).get("query") or ev_data.get("target", {}).get("query", "")
                self.browser.send_command(cmd_id, "browser.switch_tab", {"query": target})
                self._last_message = f"Browser: Switching to tab '{target}'..."
            elif intent == "browser.close_tab":
                target = ev_data.get("entities", {}).get("query") or ev_data.get("target", {}).get("query", "current")
                self.browser.send_command(cmd_id, "browser.close_tab", {"query": target})
                self._last_message = f"Browser: Closing tab '{target}'..."
            elif intent == "browser.open_first_result":
                self.browser.send_command(cmd_id, "browser.open_first_result", {})
                self._last_message = "Browser: Opening first organic result..."
            elif intent == "browser.scroll":
                entities = ev_data.get("entities", {})
                direction = entities.get("direction", "down")
                amt = -3 if direction == "down" else 3
                if self._master_armed and not self.safety.estop.is_set:
                    self._mouse.scroll_wheel(amt)
                self._last_message = f"Browser: Scrolled {direction}."

    def process_frame_modalities(self, frame: Any) -> list[Any]:
        """Processes face observation if Eye or Both mode is active, routing through FusionEngine."""
        if not self._eye_active or self._face_detector is None or not self._face_detector.is_open:
            return []

        try:
            face_obs = self._face_detector.detect(frame)
            events = self.eye.process(face_obs)
            for ev in events:
                # Route through MultimodalFusionEngine for confidence, freshness, and mode authorization
                decision = self.fusion.evaluate(ev)
                if decision.authorized:
                    log.info("Fusion authorized eye action: %s (%s)", decision.action, decision.reason)
                else:
                    log.debug("Fusion blocked eye event: %s", decision.reason)
            return events
        except Exception as exc:
            log.warning("Eye processing error: %s", exc)
            return []

    def shutdown(self) -> None:
        """Guaranteed clean release of all hardware, locks, and workers."""
        log.info("Shutting down RuntimeController...")
        self.disarm()
        self._release_face_detector()
        self._release_voice_subsystem()
        self._pipeline.close()
        self._last_message = "Application shutdown complete."

    def get_status(self) -> ModalityStatus:
        return ModalityStatus(
            mode=self._mode,
            master_armed=self._master_armed,
            hand_active=self._hand_active,
            eye_active=self._eye_active,
            voice_active=self._voice_active,
            hand_availability=self.check_hand_availability(),
            eye_availability=self.check_eye_availability(),
            voice_availability=self.check_voice_availability(),
            last_status_message=self._last_message,
        )

    def _notify_status(self) -> None:
        if self._on_status_change:
            self._on_status_change(self.get_status())
