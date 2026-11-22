"""Locate / download the MediaPipe hand_landmarker.task model bundle."""
from __future__ import annotations

import hashlib
import logging
import urllib.request
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
# SHA-256 reported by a third-party package for the float16/1 bundle. NOT verified by us (the build
# sandbox cannot reach storage.googleapis.com). A mismatch only logs a warning.
REPORTED_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"


class ModelError(RuntimeError):
    """Raised when the model file is missing and cannot be obtained."""


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _urllib_download(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url, timeout=30) as resp, dest.open("wb") as out:  # noqa: S310 - fixed https URL
        while chunk := resp.read(1 << 20):
            out.write(chunk)


def ensure_model(
    path: str | Path,
    url: str = MODEL_URL,
    expected_sha256: str | None = REPORTED_SHA256,
    downloader: Callable[[str, Path], None] = _urllib_download,
) -> Path:
    """Return `path` if it exists and is non-empty; otherwise download it atomically (.part then rename)."""
    dest = Path(path)
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    try:
        log.info("downloading hand landmarker model to %s", dest)
        downloader(url, part)
        if not part.is_file() or part.stat().st_size == 0:
            raise ModelError("downloaded model file is empty")
        if expected_sha256 and sha256_of(part) != expected_sha256:
            log.warning("model SHA-256 differs from the reported value; continuing (value is unverified)")
        part.replace(dest)
    except ModelError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ModelError(
            f"could not download model from {url}: {exc!r}. Download it manually to {dest}."
        ) from exc
    finally:
        if part.exists():
            part.unlink()
    return dest
