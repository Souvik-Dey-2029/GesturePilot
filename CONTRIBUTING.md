# Contributing to Virtual Mouse

Thank you for contributing to Virtual Mouse!

## Development Guidelines

1. **Safety First:** The safety gate (`MouseController.can_emit()`) and PyAutoGUI failsafe must never be bypassed.
2. **Determinism:** Tests must use `FakeMouseBackend` and avoid physical mouse moves or hardware webcam requirements in automated runs.
3. **Compatibility:** Support Python 3.11, 3.12, and 3.13 on Windows.

## Pull Request Process

1. Fork repository and create a feature branch.
2. Run test suite: `pytest`
3. Ensure no regressions in gate enforcement: `pytest tests/test_gate_enforcement.py`
4. Submit PR with detailed description of changes and test results.
