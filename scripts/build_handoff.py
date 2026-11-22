"""Run tests, regenerate HANDOFF_MANIFEST.md, build and verify VirtualMouse_Handoff_vNNN.zip.

Usage: python scripts/build_handoff.py --version 2
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache", "dist", ".mypy_cache", ".ruff_cache", "node_modules"}
EXCLUDE_GLOBS = ["*.pyc", "*.zip", "*.task", "*.log", ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.egg-info", "Thumbs.db", ".DS_Store"]
REQUIRED = [
    "README.md", "PROJECT_STATUS.md", "ARCHITECTURE.md", "CHANGELOG.md", "NEXT_SESSION_PROMPT.md", "HANDOFF_MANIFEST.md",
    "requirements.txt", "pyproject.toml", "src/virtual_mouse/__init__.py", "tests/conftest.py", "scripts/build_handoff.py",
    "src/virtual_mouse/pipeline.py", "src/virtual_mouse/mouse/controller.py", "src/virtual_mouse/mouse/backend.py",
    "src/virtual_mouse/tools/run_cursor.py", "src/virtual_mouse/__main__.py",
    "src/virtual_mouse/gestures/recognizer.py", "src/virtual_mouse/gestures/config.py", "src/virtual_mouse/gestures/types.py",
]


def clean() -> None:
    for d in list(ROOT.rglob("__pycache__")) + list(ROOT.rglob(".pytest_cache")):
        shutil.rmtree(d, ignore_errors=True)


def excluded(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return any(p in EXCLUDE_DIRS for p in rel.parts) or any(fnmatch.fnmatch(path.name, g) for g in EXCLUDE_GLOBS)


def collect() -> list[Path]:
    return sorted(p for p in ROOT.rglob("*") if p.is_file() and not excluded(p))


def run_tests() -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True)
    out = (proc.stdout + proc.stderr).strip()
    return proc.returncode, out


def tree(files: list[Path]) -> str:
    return "\n".join(str(f.relative_to(ROOT)).replace("\\", "/") for f in files)


def write_manifest(version: int, files: list[Path], rc: int, test_out: str) -> None:
    manifest = ROOT / "HANDOFF_MANIFEST.md"
    if manifest not in files:
        files = sorted(files + [manifest])
    summary = test_out.splitlines()[-1] if test_out else "(no output)"
    text = f"""# Handoff Manifest

* **Handoff version:** v{version:03d}
* **Built (UTC):** {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M}
* **Build environment:** Python {platform.python_version()} on {platform.system()} (project supports Python 3.11-3.13; user hardware: Windows 11, Python 3.13.7)

## Test results (actually executed at build time)
* Command: `python -m pytest -q`  -> exit code {rc}
* Result line: `{summary}`

```
{test_out[-3000:]}
```

Categories:
* **Executed:** the pytest suite above: config, types, mapping, smoothing, safety, camera (fake capture), detector (fake landmarker),
  model helper (fake downloader), drawing helper, MediaPipe API-surface check, mouse backends (fake + PyAutoGUIBackend against an injected fake module),
  MouseController gate, gate-enforcement (AST scan of all source), Pipeline (fake camera/detector/mouse), runner start-up error paths.
* **Executed outside the suite (session 3, Linux, not part of this build):** real PyAutoGUI 0.9.54 on a virtual X11 display through `PyAutoGUIBackend`
  and a full pipeline simulation with fake camera/detector. See `ARCHITECTURE.md` ("Session 3 audit").
* **Static inspection only:** main loop of `tools/run_cursor.py`, Win32 forced-release fallback, PyAutoGUI's Windows code (`SetCursorPos`, DPI awareness; read, not run).
* **User-reported (Windows 11, Python 3.13.7), not independently verified:** webcam opens, real model loads, landmarks track smoothly, ~24 FPS, score ~0.99 (preview).
* **NOT yet done (requires the user's Windows machine):** real Windows cursor movement, failsafe on Windows, tracking/latency/jitter feel with the cursor enabled
  (see `HARDWARE_TEST_PROTOCOL.md`).

## Dependency information
See `requirements.txt` (runtime) and `requirements-dev.txt` (adds pytest). `pyautogui` is used by `PyAutoGUIBackend` (lazy import); `PySide6` is planned, not yet imported.
Model asset `models/hand_landmarker.task` is NOT included (download with `python -m virtual_mouse.tools.preview --download-model`).
Install the package with `pip install -e . --no-deps` (or set `PYTHONPATH=src`) before using `python -m virtual_mouse`.

## Excluded from the ZIP
Virtual environments, `__pycache__`/`.pytest_cache`, `*.pyc`, `*.zip`, `*.task` model files, logs, `.env*`, keys/certificates, `dist/`, `.git`.
No credentials or personal data are included.

## Known limitations
See `PROJECT_STATUS.md` ("Known bugs / risks"). In short: the cursor-enabled path has not been run on real Windows hardware yet.

## Project structure / files included
```
{tree(files)}
```
"""
    (ROOT / "HANDOFF_MANIFEST.md").write_text(text, encoding="utf-8")


def build_zip(version: int) -> Path:
    clean()
    files = collect()
    if ROOT / "HANDOFF_MANIFEST.md" not in files:
        files.append(ROOT / "HANDOFF_MANIFEST.md")
        files.sort()
    out_dir = ROOT / "dist"
    out_dir.mkdir(exist_ok=True)
    zip_path = out_dir / f"VirtualMouse_Handoff_v{version:03d}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, Path("VirtualMouse") / f.relative_to(ROOT))
    return zip_path


def verify(zip_path: Path) -> list[str]:
    problems: list[str] = []
    if not zip_path.is_file():
        return [f"zip missing: {zip_path}"]
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        if bad:
            problems.append(f"corrupt member: {bad}")
        names = set(zf.namelist())
        for req in REQUIRED:
            if f"VirtualMouse/{req}" not in names:
                problems.append(f"missing in zip: {req}")
        if not any(n.startswith("VirtualMouse/tests/test_") for n in names):
            problems.append("no tests in zip")
        for n in names:
            if any(fnmatch.fnmatch(Path(n).name, g) for g in EXCLUDE_GLOBS) or any(p in EXCLUDE_DIRS for p in Path(n).parts):
                problems.append(f"excluded file present: {n}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, required=True)
    args = ap.parse_args()
    clean()
    rc, out = run_tests()
    print(out.splitlines()[-1] if out else "no test output")
    files = collect()
    write_manifest(args.version, files, rc, out)
    zip_path = build_zip(args.version)
    problems = verify(zip_path)
    if problems:
        print("HANDOFF FAILED:")
        for p in problems:
            print(" -", p)
        return 1
    with zipfile.ZipFile(zip_path) as zf:
        print(f"OK: {zip_path} ({zip_path.stat().st_size} bytes, {len(zf.namelist())} files, tests exit code {rc})")
    return 0 if rc == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
