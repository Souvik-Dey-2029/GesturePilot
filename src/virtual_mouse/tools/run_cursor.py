"""Main application runner integrating RuntimeController, verified pipeline, and honest modality reporting.

Controls:
  E: Hand only mode (Validated working pipeline)
  I: Eye only mode (Reports honest availability)
  B: Hand + Eye mode
  V: Voice mode toggle
  A: All modalities mode
  M: Master arm/disarm (Starts DISARMED by default)
  D: Diagnostic overlay toggle
  C: Calibration
  Space / X: Emergency stop (Overrides every modality immediately)
  R: Safe recovery re-arm (Resets stop latch; stays disarmed until 'm' is pressed)
  Q / Esc: Clean application exit
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from ..capture.camera import CameraError
from ..config import AppConfig, ConfigError
from ..controller import RuntimeController
from ..detection.model_assets import ModelError, ensure_model
from ..logging_setup import configure_logging
from ..mouse.backend import MouseBackendError
from ..pipeline import Pipeline, StepReport, build_pipeline
from .visualization import draw_hand, draw_runtime_hud

log = logging.getLogger("virtual_mouse.run_cursor")
WINDOW = "AI Virtual Mouse — Adaptive HCI Platform"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/config.json")
    ap.add_argument("--download-model", action="store_true", help="Download missing hand tracking model")
    ap.add_argument("--download-face-model", action="store_true", help="Download missing face tracking model")
    ap.add_argument("--download-all-models", action="store_true", help="Download all missing vision models")
    ap.add_argument("--check-models", action="store_true", help="Inspect and display status of all required models")
    ap.add_argument("--start-armed", action="store_true", help="Arm mouse control at start (default: DISARMED)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    configure_logging(args.log_level)

    if args.check_models:
        from ..detection.model_manager import ModelManager
        mm = ModelManager()
        statuses = mm.check_all_models()
        print("\n=== Virtual Mouse Model Readiness Status ===")
        print(f"{'Model Name':<18} {'Status':<16} {'Size (MB)':<12} {'Path'}")
        print("-" * 75)
        for name, st in statuses.items():
            mb_sz = f"{st.size_bytes / (1024 * 1024):.2f}" if st.is_present else "0.00"
            print(f"{st.name:<18} {st.status_text:<16} {mb_sz:<12} {st.target_path}")
        print("-" * 75 + "\n")
        return 0

    try:
        cfg = AppConfig.load(args.config)
        from ..detection.model_manager import ModelManager
        mm = ModelManager()
        if args.download_model or args.download_all_models:
            mm.ensure_hand_model()
        if args.download_face_model or args.download_all_models:
            mm.ensure_face_model()

        pipeline = build_pipeline(cfg)
        runtime = RuntimeController(pipeline)
    except (ConfigError, ModelError, MouseBackendError) as exc:
        log.error("%s", exc)
        return 2

    import cv2

    stats = {"frames": 0, "t0": time.perf_counter()}

    def on_step(report: StepReport) -> bool:
        stats["frames"] += 1
        if report.frame is not None:
            img = report.frame.image.copy()
            hand = report.result.primary_hand if report.result else None
            if hand is not None and runtime.mode.value in ("HAND", "BOTH", "ALL"):
                draw_hand(img, hand)
            fps = stats["frames"] / max(time.perf_counter() - stats["t0"], 1e-6)

            # Determine gesture display info
            active_gest = "none"
            inter_mode = "POINTER"
            rec_pose = "UNKNOWN"
            cursor_allowed = True
            if report.gesture is not None:
                active_gest = report.gesture.active_gesture.value
                inter_mode = report.gesture.interaction_state.value
                rec_pose = report.gesture.metrics.recognized_pose.value
                cursor_allowed = report.gesture.cursor_movement_allowed

            mouse_st = "down (held)" if pipeline.mouse_controller.left_held else "up"
            if report.gesture and report.gesture.action.action_type.name != "NONE":
                mouse_st = report.gesture.action.action_type.name

            # Process eye modality concurrently if Eye or Both mode is active
            runtime.process_frame_modalities(report.frame)

            draw_runtime_hud(
                image=img,
                mode_text=runtime.mode.value,
                master_armed=runtime.master_armed,
                estop_set=runtime.safety.estop.is_set,
                estop_reason=runtime.safety.estop.reason,
                tracking_text=report.tracking.value,
                fps=fps,
                active_gesture=active_gest,
                mouse_state=mouse_st,
                recognized_pose=rec_pose,
                status_message=runtime.last_message,
                diagnostic_mode=runtime.diagnostic_mode,
                active_boundary=(
                    cfg.mapping.margin_left,
                    cfg.mapping.margin_right,
                    cfg.mapping.margin_top,
                    cfg.mapping.margin_bottom,
                ),
                cursor_movement_allowed=cursor_allowed,
                eye_telemetry=runtime.eye_telemetry,
            )
            cv2.imshow(WINDOW, img)

        key = cv2.waitKey(1) & 0xFF
        if key != 255:  # Valid key pressed
            should_quit = runtime.handle_key(key)
            if should_quit:
                return True

        return False

    if args.start_armed:
        runtime.arm()
    else:
        runtime.disarm()

    log.info("Starting runtime. Mode: %s. Master: %s", runtime.mode.value, "ARMED" if runtime.master_armed else "DISARMED")
    try:
        pipeline.run(on_step=on_step)
    except (CameraError, ModelError) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
        runtime.shutdown()

    if pipeline.last_error:
        log.error("Stopped because of: %s", pipeline.last_error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
