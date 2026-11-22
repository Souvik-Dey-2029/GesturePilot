"""Milestone 3 runner: hand-controlled cursor (cursor movement only; no clicks/drag/scroll).

Windows:  python -m virtual_mouse --download-model        (starts DISABLED)
Keys (the preview window must have focus):  e = enable/disable   Space or x = EMERGENCY STOP
                                            r = acknowledge stop (stays disabled; press e to re-enable)   q/Esc = quit
Backup: moving the real mouse into a screen corner trips PyAutoGUI's failsafe, which latches an emergency stop.
NOT verified on real hardware by the author of this file.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from ..config import AppConfig, ConfigError
from ..detection.model_assets import ModelError, ensure_model
from ..logging_setup import configure_logging
from ..mouse.backend import MouseBackendError
from ..capture.camera import CameraError
from ..pipeline import Pipeline, StepReport, build_pipeline
from .visualization import draw_hand, draw_hud

log = logging.getLogger("virtual_mouse.run_cursor")
WINDOW = "AI Virtual Mouse (e=enable, Space=STOP, r=re-arm, q=quit)"


def _status(p: Pipeline) -> str:
    if p.safety.estop.is_set:
        return f"E-STOP: {p.safety.estop.reason}"
    return "ENABLED" if p.safety.enabled else "DISABLED"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="config/config.json")
    ap.add_argument("--download-model", action="store_true")
    ap.add_argument("--start-enabled", action="store_true", help="enable mouse control at start (default: disabled)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    configure_logging(args.log_level)

    try:
        cfg = AppConfig.load(args.config)
        if args.download_model:
            ensure_model(cfg.detector.model_path)
        pipeline = build_pipeline(cfg)
    except (ConfigError, ModelError, MouseBackendError) as exc:
        log.error("%s", exc)
        return 2

    import cv2

    stats = {"frames": 0, "t0": time.perf_counter(), "diagnostic": False}

    def on_step(report: StepReport) -> bool:
        stats["frames"] += 1
        if report.frame is not None:
            img = report.frame.image.copy()
            hand = report.result.primary_hand if report.result else None
            if hand is not None:
                draw_hand(img, hand)
            fps = stats["frames"] / max(time.perf_counter() - stats["t0"], 1e-6)

            # Determine gesture display info
            active_gest = "none"
            pinch_d = 0.0
            inter_mode = "POINTER"
            rec_pose = "UNKNOWN"
            reject_reason = ""
            scroll_dir = "NONE"
            stability_pct = 100
            cursor_allowed = True
            if report.gesture is not None:
                active_gest = report.gesture.active_gesture.value
                pinch_d = report.gesture.metrics.pinch_dist
                inter_mode = report.gesture.interaction_state.value
                rec_pose = report.gesture.metrics.recognized_pose.value
                reject_reason = report.gesture.metrics.rejection_reason
                scroll_dir = report.gesture.metrics.scroll_direction
                stability_pct = report.gesture.metrics.stability_pct
                cursor_allowed = report.gesture.cursor_movement_allowed

            mouse_st = "down (held)" if pipeline.mouse_controller.left_held else "up"
            if report.gesture and report.gesture.action.action_type.name != "NONE":
                mouse_st = report.gesture.action.action_type.name

            draw_hud(
                img,
                status_text=_status(pipeline),
                tracking_text=report.tracking.value,
                fps=fps,
                active_gesture=active_gest,
                mouse_state=mouse_st,
                pinch_dist=pinch_d,
                cursor_pos=report.target,
                diagnostic_mode=stats["diagnostic"],
                active_region_margins=(
                    cfg.mapping.margin_left,
                    cfg.mapping.margin_right,
                    cfg.mapping.margin_top,
                    cfg.mapping.margin_bottom,
                ),
                interaction_mode=inter_mode,
                recognized_pose=rec_pose,
                rejection_reason=reject_reason,
                scroll_direction=scroll_dir,
                stability_pct=stability_pct,
                cursor_movement_allowed=cursor_allowed,
            )
            cv2.imshow(WINDOW, img)
        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            return True
        if key in (ord(" "), ord("x")):
            pipeline.safety.emergency_stop("keyboard")
        elif key == ord("r"):
            pipeline.safety.acknowledge_emergency_stop()
            log.info("emergency stop acknowledged; control remains DISABLED - press 'e' to enable")
        elif key == ord("d"):
            stats["diagnostic"] = not stats["diagnostic"]
            log.info("diagnostic overlay: %s", "ON" if stats["diagnostic"] else "OFF")
        elif key == ord("e"):
            if pipeline.safety.enabled:
                pipeline.safety.disable()
                log.info("control disabled")
            elif pipeline.safety.enable():
                log.info("control enabled (waiting for reliable tracking)")
            else:
                log.warning("cannot enable while emergency stop is latched; press 'r' first")
        return False

    if args.start_enabled:
        pipeline.safety.enable()
    log.info("starting; control is %s", _status(pipeline))
    try:
        pipeline.run(on_step=on_step)
    except (CameraError, ModelError) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        cv2.destroyAllWindows()
    if pipeline.last_error:
        log.error("stopped because of: %s", pipeline.last_error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
