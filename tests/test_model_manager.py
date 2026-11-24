"""Tests for centralized ModelManager and CLI model check commands."""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from virtual_mouse.detection.model_manager import (
    ModelManager,
    ModelStatus,
    compute_sha256,
)
from virtual_mouse.tools.run_cursor import main


def test_model_manager_status_checks(tmp_path: Path):
    models_dir = tmp_path / "models"
    whisper_dir = tmp_path / "whisper"
    mm = ModelManager(models_dir=models_dir, whisper_dir=whisper_dir)
    mm.ensure_directory()

    statuses = mm.check_all_models()
    assert statuses["hand"].status_text == "MISSING"
    assert statuses["face"].status_text == "MISSING"
    assert statuses["voice"].status_text == "ON-DEMAND CACHE"

    # Create dummy hand model
    hand_path = models_dir / "hand_landmarker.task"
    hand_path.write_bytes(b"x" * 1_500_000)

    updated_statuses = mm.check_all_models()
    assert updated_statuses["hand"].status_text == "READY"
    assert updated_statuses["hand"].is_valid is True
    assert updated_statuses["hand"].size_bytes == 1_500_000


def test_model_manager_atomic_download(tmp_path: Path):
    dest = tmp_path / "test_model.task"

    def mock_download(url: str, part: Path):
        part.write_bytes(b"content-of-model")

    mm = ModelManager(models_dir=tmp_path)
    res = mm.download_model_atomic(dest, "http://fake.url/model", downloader=mock_download)
    assert res == dest
    assert dest.is_file()
    assert dest.read_bytes() == b"content-of-model"
    # Ensure temporary .part file was cleaned up
    assert not dest.with_suffix(".task.part").exists()


def test_cli_check_models_invocation(capsys):
    ret = main(["--check-models"])
    assert ret == 0
    captured = capsys.readouterr()
    assert "=== Virtual Mouse Model Readiness Status ===" in captured.out
    assert "hand_landmarker" in captured.out
    assert "face_landmarker" in captured.out
