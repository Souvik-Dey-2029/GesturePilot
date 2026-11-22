# Security Policy

## Reporting Security Issues

If you discover a security vulnerability or safety-bypass defect in Virtual Mouse, please report it responsibly:

1. Contact project maintainers via a private GitHub Security Advisory or direct repository message.
2. Please provide reproduction steps, Windows build, Python version, and a demonstration script or test case.
3. Allow reasonable time for investigation and remediation before public disclosure.

## Security & Safety Architecture

Virtual Mouse directly interacts with OS input events (`PyAutoGUI` / `mouse_event`). The codebase implements strict defense-in-depth safety controls:

- **Safety Gate:** Every OS input emission is gated behind `SafetyController.can_emit()`. No mouse event can be emitted while disabled, during emergency stop, or when tracking is lost.
- **FailSafe:** PyAutoGUI corner failsafe is forced enabled at startup.
- **Guaranteed Button Release:** In case of emergency stop, tracking loss, exceptions, or shutdown, all held mouse buttons are unconditionally released.
