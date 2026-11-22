"""Interactive calibration utility for comfortable hand interaction region and thresholds."""
from __future__ import annotations

import argparse
import logging
import sys
import time

from ..config import AppConfig
from ..detection.model_assets import ensure_model
from ..logging_setup import configure_logging
from ..pipeline import build_pipeline
from ..types import StepOutcome

log = logging.getLogger("virtual_mouse.calibrate")


def calibrate(config_path: str = "config/config.json") -> int:
    cfg = AppConfig.load(config_path)
    ensure_model(cfg.detector.model_path)
    pipe = build_pipeline(cfg)

    import cv2

    window = "Virtual Mouse Calibration (Space=Capture, s=Save, q=Quit)"
    step = 0
    instructions = [
        "Move hand to TOP-LEFT comfortable limit and press SPACE",
        "Move hand to BOTTOM-RIGHT comfortable limit and press SPACE",
        "Perform comfortable PINCH and press SPACE",
        "Calibration Complete! Press 's' to save config or 'q' to exit.",
    ]

    captured_tl: tuple[float, float] | None = None
    captured_br: tuple[float, float] | None = None
    captured_pinch: float | None = None

    def on_step(report) -> bool:
        nonlocal step, captured_tl, captured_br, captured_pinch
        if report.frame is not None:
            img = report.frame.image.copy()
            h, w = img.shape[:2]

            # Instruction overlay
            cv2.rectangle(img, (0, 0), (w, 60), (30, 30, 30), -1)
            cv2.putText(img, instructions[min(step, len(instructions) - 1)], (15, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

            if report.result and report.result.primary_hand:
                hand = report.result.primary_hand
                idx_tip = hand.point(8)
                cv2.circle(img, (int(idx_tip.x * w), int(idx_tip.y * h)), 8, (0, 255, 0), -1)

            cv2.imshow(window, img)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), 27):
            return True
        if key == ord(" "):
            if report.result and report.result.primary_hand:
                hand = report.result.primary_hand
                tip = hand.point(8)
                if step == 0:
                    captured_tl = (tip.x, tip.y)
                    log.info("Captured Top-Left: %s", captured_tl)
                    step = 1
                elif step == 1:
                    captured_br = (tip.x, tip.y)
                    log.info("Captured Bottom-Right: %s", captured_br)
                    step = 2
                elif step == 2:
                    if report.gesture:
                        captured_pinch = report.gesture.metrics.pinch_dist
                        log.info("Captured Pinch Dist: %.2f", captured_pinch)
                    step = 3
        elif key == ord("s") and step == 3:
            if captured_tl and captured_br:
                x1, y1 = captured_tl
                x2, y2 = captured_br
                cfg.mapping.margin_left = max(0.05, min(x1, x2))
                cfg.mapping.margin_right = max(0.05, 1.0 - max(x1, x2))
                cfg.mapping.margin_top = max(0.05, min(y1, y2))
                cfg.mapping.margin_bottom = max(0.05, 1.0 - max(y1, y2))
                if captured_pinch:
                    cfg.gestures.pinch_click_threshold = min(0.60, max(0.20, captured_pinch * 1.15))
                    cfg.gestures.pinch_release_threshold = cfg.gestures.pinch_click_threshold * 1.45
                cfg.save(config_path)
                log.info("Saved newly calibrated configuration to %s", config_path)
            return True

        return False

    try:
        pipe.run(on_step=on_step)
    finally:
        cv2.destroyAllWindows()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/config.json")
    args = ap.parse_args(argv)
    configure_logging("INFO")
    return calibrate(args.config)


if __name__ == "__main__":
    sys.exit(main())
