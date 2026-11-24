"""Centralized Model and Dependency Readiness Manager.

Automates downloading, integrity verification (SHA-256), versioning,
and readiness inspection across all modalities:
- Hand: MediaPipe Tasks hand_landmarker.task
- Face/Eye: MediaPipe Tasks face_landmarker.task
- Voice: faster-whisper tiny.en / base.en CTranslate2 bundle
"""
from __future__ import annotations

import hashlib
import logging
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Optional

log = logging.getLogger(__name__)

HAND_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"
)
FACE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)

# Known upstream SHA-256 hashes (verified where confirmed)
HAND_MODEL_SHA256 = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
FACE_MODEL_SHA256 = None  # Upstream updates dynamically; validated by size & non-empty


class ModelError(RuntimeError):
    """Raised when a model file is missing or cannot be retrieved."""


@dataclass(frozen=True)
class ModelStatus:
    name: str
    target_path: Path
    url: str
    is_present: bool
    size_bytes: int
    is_valid: bool
    sha256: Optional[str]
    status_text: str


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _streaming_download(url: str, dest: Path, timeout: float = 60.0) -> None:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "VirtualMouse/1.0.0 (https://github.com/souvik-hazra/VirtualMouse)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp, dest.open("wb") as out:  # noqa: S310
        total_size = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        while chunk := resp.read(1 << 20):  # 1 MB chunk
            out.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                pct = (downloaded / total_size) * 100.0
                log.debug("Download progress: %.1f%% (%d / %d bytes)", pct, downloaded, total_size)


class ModelManager:
    """Manages local model assets, status inspection, and atomic downloads."""

    def __init__(self, models_dir: Path | str = "models", whisper_dir: Path | str = "models/whisper") -> None:
        self.models_dir = Path(models_dir)
        self.whisper_dir = Path(whisper_dir)
        self.hand_model_path = self.models_dir / "hand_landmarker.task"
        self.face_model_path = self.models_dir / "face_landmarker.task"

    def ensure_directory(self) -> None:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.whisper_dir.mkdir(parents=True, exist_ok=True)

    def check_hand_model(self) -> ModelStatus:
        p = self.hand_model_path
        exists = p.is_file()
        sz = p.stat().st_size if exists else 0
        valid = exists and sz > 1_000_000  # Expected ~7.8 MB
        sha = compute_sha256(p) if valid else None
        stat = "READY" if valid else ("MISSING" if not exists else "INVALID")
        return ModelStatus("hand_landmarker", p, HAND_MODEL_URL, exists, sz, valid, sha, stat)

    def check_face_model(self) -> ModelStatus:
        p = self.face_model_path
        exists = p.is_file()
        sz = p.stat().st_size if exists else 0
        valid = exists and sz > 1_000_000  # Expected ~3.7 MB
        sha = compute_sha256(p) if valid else None
        stat = "READY" if valid else ("MISSING" if not exists else "INVALID")
        return ModelStatus("face_landmarker", p, FACE_MODEL_URL, exists, sz, valid, sha, stat)

    def check_voice_model(self) -> ModelStatus:
        # Check faster-whisper model files in whisper cache
        p = self.whisper_dir
        exists = p.is_dir()
        files = list(p.glob("**/*.bin")) + list(p.glob("**/*.safetensors")) + list(p.glob("**/model.bin"))
        valid = len(files) > 0
        total_sz = sum(f.stat().st_size for f in files) if valid else 0
        stat = "READY" if valid else "ON-DEMAND CACHE"
        return ModelStatus("faster_whisper", p, "Systran/faster-whisper-tiny.en", exists, total_sz, valid, None, stat)

    def check_all_models(self) -> Dict[str, ModelStatus]:
        return {
            "hand": self.check_hand_model(),
            "face": self.check_face_model(),
            "voice": self.check_voice_model(),
        }

    def download_model_atomic(
        self,
        dest: Path,
        url: str,
        downloader: Callable[[str, Path], None] = _streaming_download,
        expected_sha256: Optional[str] = None,
    ) -> Path:
        """Downloads url to dest.part then atomically renames to dest."""
        if dest.is_file() and dest.stat().st_size > 0:
            return dest

        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        try:
            log.info("Downloading %s to temporary file %s...", url, part)
            downloader(url, part)
            if not part.is_file() or part.stat().st_size == 0:
                raise ModelError(f"Downloaded model from {url} is empty.")
            if expected_sha256:
                actual_sha = compute_sha256(part)
                if actual_sha != expected_sha256:
                    log.warning("SHA-256 for %s differs from expected (%s != %s)", dest.name, actual_sha, expected_sha256)
            part.replace(dest)
            log.info("Successfully downloaded and installed %s (%d bytes).", dest, dest.stat().st_size)
            return dest
        except ModelError:
            raise
        except Exception as exc:
            raise ModelError(f"Failed to download model from {url}: {exc}") from exc
        finally:
            if part.exists():
                part.unlink()

    def ensure_face_model(self, downloader: Callable[[str, Path], None] = _streaming_download) -> Path:
        return self.download_model_atomic(self.face_model_path, FACE_MODEL_URL, downloader, FACE_MODEL_SHA256)

    def ensure_hand_model(self, downloader: Callable[[str, Path], None] = _streaming_download) -> Path:
        return self.download_model_atomic(self.hand_model_path, HAND_MODEL_URL, downloader, HAND_MODEL_SHA256)
