"""Milestone 2 diagnostic: webcam -> hand landmarks preview. Does NOT move the mouse.

Run on Windows:  python -m virtual_mouse.tools.preview --download-model
"""
from __future__ import annotations

import argparse
import logging
import sys
import time

from ..capture.camera import Camera, CameraError
from ..config import AppConfig, ConfigError
from ..detection.hand_detector import HandDetector
from ..detection.model_assets import ModelError, ensure_model
from ..logging_setup import configure_logging
from ..mapping.coordinates import CoordinateMapper
from ..mapping.smoothing import PointFilter
from ..types import LandmarkId
from .visualization import draw_hand

log = logging.getLogger("virtual_mouse.preview")


def _screen_size() -> tuple[int, int]:
    try:
        import ctypes

        user32 = ctypes.windll.user32  # type: ignore[attr-defined]  # Windows only
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:  # noqa: BLE001
        return 1920, 1080


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/config.json")
    ap.add_argument("--download-model", action="store_true", help="download hand_landmarker.task if missing")
    ap.add_argument("--no-window", action="store_true", help="print landmark info instead of showing a window")
    ap.add_argument("--max-frames", type=int, default=0, help="stop after N processed frames (0 = unlimited)")
    ap.add_argument("--log-level", default="INFO")
    args = ap.parse_args(argv)
    configure_logging(args.log_level)

    try:
        cfg = AppConfig.load(args.config)
        if args.download_model:
            ensure_model(cfg.detector.model_path)
    except (ConfigError, ModelError) as exc:
        log.error("%s", exc)
        return 2

    screen_w, screen_h = _screen_size()
    mapper = CoordinateMapper(cfg.mapping, screen_w, screen_h)
    smoother = PointFilter(cfg.smoothing)
    frames, t0 = 0, time.perf_counter()
    try:
        with HandDetector(cfg.detector) as detector, Camera(cfg.camera) as camera:
            import cv2

            while True:
                frame = camera.read(timeout=1.0)
                if frame is None:
                    continue
                result = detector.detect(frame)
                frames += 1
                image = frame.image.copy()
                hand = result.primary_hand
                label = "no hand"
                if hand is not None:
                    draw_hand(image, hand)
                    tip = hand.point(LandmarkId.INDEX_TIP)
                    raw = mapper.map(tip.x, tip.y)
                    sx, sy = smoother(raw.x, raw.y, frame.timestamp_ms / 1000.0)
                    label = f"cursor(not moved) {sx:.0f},{sy:.0f}  score {hand.score:.2f}"
                else:
                    smoother.reset()
                fps = frames / max(time.perf_counter() - t0, 1e-6)
                if args.no_window:
                    print(f"frame {frames} fps {fps:.1f} {label}")
                else:
                    cv2.putText(image, f"{fps:.1f} fps | {label}", (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    cv2.imshow("AI Virtual Mouse - preview (q/Esc to quit)", image)
                    if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                        break
                if args.max_frames and frames >= args.max_frames:
                    break
    except (CameraError, ModelError) as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        if not args.no_window:
            try:
                import cv2

                cv2.destroyAllWindows()
            except Exception:  # noqa: BLE001
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
