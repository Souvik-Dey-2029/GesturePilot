# Testing & Validation Guide

## Test Suite Structure

The automated test suite runs offline without requiring physical hardware:

- `test_camera.py`: Background frame grabber, non-blocking reads, error handling.
- `test_config.py`: Strict schema validation, JSON persistence.
- `test_detector.py`: MediaPipe tasks conversion and timestamp handling.
- `test_gate_enforcement.py`: AST static verification ensuring no bypass around `MouseController`.
- `test_gestures.py`: Pose classification, state transitions, temporal confirmation, hysteresis, and ambiguity rejection.
- `test_mapping.py`: Coordinate mapping, active region boundaries, non-linear acceleration.
- `test_mouse_backend.py` & `test_mouse_controller.py`: Gate enforcement, failsafe latching, emergency stop button release.
- `test_pipeline.py`: Full pipeline integration using fakes.
- `test_smoothing.py`: One Euro filter adaptive cutoffs, tremor deadband, NaN/Inf protection.

Run the test suite:
```powershell
pytest -v
```
