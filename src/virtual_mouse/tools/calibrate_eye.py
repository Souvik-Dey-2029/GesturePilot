"""Interactive Eye Calibration and Diagnostic CLI tool.

Allows the user to:
- Run standalone eye tracking diagnostic HUD without arming mouse
- Collect open-eye baseline and closed-eye samples
- Automatically compute personalized Schmitt-trigger EAR and blendshape thresholds
- Save calibrated parameters to SQLite user profile
- Export diagnostic observation logs to CSV
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path
from typing import List

import cv2

from ..capture.camera import Camera, CameraConfig
from ..config import AppConfig
from ..detection.face_detector import FaceDetector
from ..detection.model_manager import ModelManager
from ..eye.calibration import EyeCalibration, EyeCalibrator
from ..eye.feature_extractor import EyeFeatureExtractor, EyeFeatureObservation
from ..eye.subsystem import EyeSubsystem, FaceObservation
from ..logging_setup import configure_logging
from ..personalization.engine import AdaptivePersonalizationEngine


def run_eye_calibration_tool(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Virtual Mouse Eye Tracking Calibration & Diagnostic Utility")
    ap.add_argument("--config", default="config/config.json")
    ap.add_argument("--export-csv", default=None, help="Optional path to export raw frame diagnostics CSV")
    ap.add_argument("--device", type=int, default=0, help="Camera device index")
    args = ap.parse_args(argv)
    configure_logging("INFO")

    # 1. Model Check
    mm = ModelManager()
    if not mm.face_model_path.is_file():
        print(f"Face model missing. Downloading to {mm.face_model_path}...")
        mm.ensure_face_model()

    print("\n" + "=" * 65)
    print(" VIRTUAL MOUSE — EYE CALIBRATION & DIAGNOSTIC UTILITY")
    print("=" * 65)
    print(" Controls:")
    print("   [O] : Collect Open-Eye Baseline Samples (look naturally at screen)")
    print("   [C] : Collect Closed-Eye Samples (perform deliberate full eye closures)")
    print("   [S] : Save Calibrated Profile to Database")
    print("   [R] : Reset Calibration Buffers")
    print("   [Q/Esc] : Exit Utility")
    print("=" * 65 + "\n")

    cam = Camera(CameraConfig(device_index=args.device))
    detector = FaceDetector(model_path=mm.face_model_path)
    subsystem = EyeSubsystem()
    subsystem.enable()
    calibrator = EyeCalibrator(target_samples=60)
    personalization = AdaptivePersonalizationEngine()

    csv_file = None
    csv_writer = None
    if args.export_csv:
        csv_path = Path(args.export_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_file = open(csv_path, "w", newline="", encoding="utf-8")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([
            "timestamp", "face_detected", "ear_left", "ear_right", "ear_avg",
            "blink_left", "blink_right", "blink_avg", "symmetry_blink",
            "eye_state", "in_blink", "sequence_count", "rejection_reason"
        ])

    window_title = "Virtual Mouse — Eye Diagnostics & Calibration"
    cv2.namedWindow(window_title, cv2.WINDOW_AUTOSIZE)

    detector.open()
    cam.start()

    active_collecting = "NONE"
    last_status = "Ready. Look at camera naturally and press 'o' to start open baseline."

    try:
        while True:
            frame = cam.read(timeout=0.1)
            if frame is None:
                continue

            img = frame.image.copy()
            h, w = img.shape[:2]

            face_obs = detector.detect(frame)
            events = subsystem.process(face_obs)

            # Record sample if in collection mode
            if face_obs is not None:
                obs = subsystem.extractor.extract(face_obs.landmarks, face_obs.blendshapes, face_obs.confidence, frame.timestamp_ms / 1000.0)
                if active_collecting == "OPEN":
                    calibrator.add_open_sample(obs)
                elif active_collecting == "CLOSED":
                    calibrator.add_closed_sample(obs)

                if csv_writer:
                    csv_writer.writerow([
                        frame.timestamp_ms,
                        obs.face_detected,
                        round(obs.ear_left, 4),
                        round(obs.ear_right, 4),
                        round(obs.ear_avg, 4),
                        round(obs.blink_left, 4),
                        round(obs.blink_right, 4),
                        round(obs.blink_avg, 4),
                        round(obs.symmetry_blink, 4),
                        subsystem.telemetry.current_state,
                        subsystem.telemetry.in_blink,
                        subsystem.telemetry.sequence_count,
                        subsystem.telemetry.rejection_reason,
                    ])

            # Draw Diagnostic Overlay
            banner_h = 160
            overlay = img.copy()
            cv2.rectangle(overlay, (0, 0), (w, banner_h), (25, 25, 25), -1)
            cv2.addWeighted(overlay, 0.82, img, 0.18, 0, img)

            t = subsystem.telemetry
            # Line 1: Tracking & State
            f_col = (0, 255, 0) if t.face_detected else (0, 0, 255)
            cv2.putText(img, f"FACE: {'DETECTED' if t.face_detected else 'LOST'} | STATE: {t.current_state} | LATENCY: {t.latency_ms:.1f}ms", (12, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.50, f_col, 2)

            # Line 2: Features
            cv2.putText(img, f"L_EAR: {t.left_ear:.3f} R_EAR: {t.right_ear:.3f} (AVG: {t.ear:.3f}) | L_BLINK: {t.left_blink:.2f} R_BLINK: {t.right_blink:.2f}", (12, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1)

            # Line 3: Calibration Buffer Status
            cal_str = f"COLLECTING: {active_collecting} (Open Samples: {calibrator.open_samples_count}/30, Closed: {calibrator.closed_samples_count}/20)"
            cv2.putText(img, cal_str, (12, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 255), 1)

            # Line 4: Thresholds & In-Blink
            th_str = f"THRESH: EAR closed<={t.ear_closed_threshold:.2f}, open>={t.ear_open_threshold:.2f} | Blend closed>={t.blend_closed_threshold:.2f} | In-Blink: {t.in_blink}"
            cv2.putText(img, th_str, (12, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (200, 200, 200), 1)

            # Line 5: Action & Rejection
            act_col = (0, 255, 0) if "Accepted" in t.rejection_reason else (180, 220, 255)
            cv2.putText(img, f"SEQ: {t.sequence_count} | LAST ACTION: {t.last_action} | STATUS: {t.rejection_reason or 'None'}", (12, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.40, act_col, 1)

            # Line 6: Instructions
            cv2.putText(img, f"HELP: [O] Open samples [C] Closed samples [S] Save profile [R] Reset | [Q] Quit", (12, 134), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 200, 255), 1)

            cv2.imshow(window_title, img)
            k = cv2.waitKey(1) & 0xFF
            if k in (ord("q"), 27):
                break
            elif k in (ord("o"), ord("O")):
                active_collecting = "OPEN" if active_collecting != "OPEN" else "NONE"
            elif k in (ord("c"), ord("C")):
                active_collecting = "CLOSED" if active_collecting != "CLOSED" else "NONE"
            elif k in (ord("r"), ord("R")):
                calibrator.reset()
                active_collecting = "NONE"
                print("Calibration buffers reset.")
            elif k in (ord("s"), ord("S")):
                new_calib = calibrator.finalize()
                if new_calib:
                    subsystem.apply_calibration(new_calib)
                    personalization.profile.blink_ear_threshold = new_calib.ear_closed_threshold
                    personalization.profile.model_version += 1
                    personalization.store.save_profile(personalization.profile)
                    print(f"\n[SUCCESS] Calibration saved: Baseline EAR={new_calib.natural_ear_baseline:.3f}, Closed TH={new_calib.ear_closed_threshold:.3f}")
                else:
                    print("\n[WARNING] Could not finalize calibration: need >= 15 open and >= 10 closed samples.")

    finally:
        cv2.destroyAllWindows()
        detector.close()
        cam.stop()
        if csv_file:
            csv_file.close()
            print(f"Exported diagnostic log to {args.export_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(run_eye_calibration_tool())
