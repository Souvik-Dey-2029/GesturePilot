"""Static + behavioural enforcement of the safety rule: every OS mouse event goes through MouseController -> can_emit().

Session 3 audit: these tests make the audit result durable, so a future milestone (clicks, drag, scroll) cannot silently bypass the gate.
"""
import ast
from pathlib import Path

import pytest

from virtual_mouse.config import SafetyConfig
from virtual_mouse.mouse.backend import FakeMouseBackend
from virtual_mouse.mouse.controller import MouseController
from virtual_mouse.safety import SafetyController

SRC = Path(__file__).resolve().parent.parent / "src" / "virtual_mouse"
MOUSE_PKG = SRC / "mouse"
BACKEND_METHODS = {"move_to", "left_down", "left_up", "right_click", "scroll"}
# Raw OS / PyAutoGUI input calls that must never appear outside the mouse package.
OS_INPUT_NAMES = {
    "moveTo", "moveRel", "move", "click", "doubleClick", "rightClick", "mouseDown", "mouseUp", "dragTo", "dragRel",
    "drag", "scroll", "hscroll", "vscroll", "SetCursorPos", "mouse_event", "SendInput", "keybd_event",
}


def _modules_outside_mouse_pkg():
    return [p for p in SRC.rglob("*.py") if MOUSE_PKG not in p.parents]


def _dotted(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def test_pyautogui_and_raw_os_input_confined_to_mouse_package():
    offenders = []
    for path in _modules_outside_mouse_pkg():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "pyautogui" for a in node.names):
                offenders.append(f"{path.name}: imports pyautogui")
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "pyautogui":
                offenders.append(f"{path.name}: imports from pyautogui")
            if isinstance(node, ast.Constant) and node.value == "pyautogui":
                offenders.append(f"{path.name}: references the 'pyautogui' module by name")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in OS_INPUT_NAMES:
                offenders.append(f"{path.name}:{node.lineno}: calls {_dotted(node.func)}")
    assert offenders == []


def test_outside_mouse_package_only_mouse_controller_receives_mouse_calls():
    """Any `.move_to/.left_down/...` call outside `mouse/` must be on the MouseController held as `self._mouse`."""
    calls = []
    for path in _modules_outside_mouse_pkg():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in BACKEND_METHODS | {"release_all"}:
                calls.append((path.name, _dotted(node.func)))
    assert calls, "expected the pipeline to call the controller"
    assert all(recv.startswith("self._mouse.") for _, recv in calls), calls
    assert {name for name, _ in calls} <= {"pipeline.py", "engine.py", "controller.py"}


def test_backend_called_only_by_controller_inside_mouse_package():
    calls = []
    for path in MOUSE_PKG.glob("*.py"):
        if path.name in {"backend.py", "__init__.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in BACKEND_METHODS and _dotted(node).startswith("self._backend."):
                calls.append((path.name, node.lineno))
    assert calls and {n for n, _ in calls} == {"controller.py"}


def test_real_backend_constructed_only_in_build_pipeline():
    users = []
    for path in _modules_outside_mouse_pkg():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _dotted(node.func).endswith("PyAutoGUIBackend"):
                users.append(path.name)
    assert users == ["pipeline.py"]


@pytest.mark.parametrize(
    "emit",
    [
        lambda m: m.move_to(10, 10),
        lambda m: m.left_down(),
        lambda m: m.right_click(),
        lambda m: m.scroll(1),
    ],
    ids=["move_to", "left_down", "right_click", "scroll"],
)
def test_every_emitting_method_consults_can_emit(emit):
    """can_emit() False -> nothing reaches the backend; can_emit() True -> exactly one backend call."""
    backend = FakeMouseBackend()
    safety = SafetyController(SafetyConfig())
    mouse = MouseController(backend, safety)
    verdict = {"v": False}
    consulted = []
    safety.can_emit = lambda: (consulted.append(1), verdict["v"])[1]  # type: ignore[method-assign]

    assert emit(mouse) is False and backend.events == [] and len(consulted) == 1
    verdict["v"] = True
    assert emit(mouse) is True and len(backend.events) == 1 and len(consulted) == 2
