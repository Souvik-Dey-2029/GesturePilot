# Development Guide

## Environment Setup

1. Python 3.11 - 3.13 on Windows 11.
2. Install in editable mode with development dependencies:
   ```powershell
   pip install -e .[dev]
   ```
3. Run tests before submitting changes:
   ```powershell
   pytest
   ```

## Design Principles

- Keep all mouse actions within `MouseController`.
- Never bypass `SafetyController.can_emit()`.
- Use `FakeMouseBackend` for unit and integration testing.
- Maintain scale-invariant metrics using `compute_hand_scale`.
