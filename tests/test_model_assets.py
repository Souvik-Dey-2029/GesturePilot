import hashlib

import pytest

from virtual_mouse.detection.model_assets import ModelError, ensure_model, sha256_of


def test_existing_file_not_redownloaded(tmp_path):
    p = tmp_path / "m.task"
    p.write_bytes(b"abc")
    assert ensure_model(p, downloader=lambda u, d: pytest.fail("should not download")) == p


def test_download_atomic_and_cleans_part(tmp_path):
    p = tmp_path / "sub" / "m.task"
    ensure_model(p, downloader=lambda u, d: d.write_bytes(b"data"), expected_sha256=hashlib.sha256(b"data").hexdigest())
    assert p.read_bytes() == b"data" and not list(p.parent.glob("*.part"))


def test_sha_mismatch_only_warns(tmp_path, caplog):
    p = tmp_path / "m.task"
    with caplog.at_level("WARNING"):
        ensure_model(p, downloader=lambda u, d: d.write_bytes(b"x"), expected_sha256="0" * 64)
    assert p.exists() and "SHA-256" in caplog.text


def test_empty_download_and_failure(tmp_path):
    with pytest.raises(ModelError):
        ensure_model(tmp_path / "a.task", downloader=lambda u, d: d.write_bytes(b""))
    assert not (tmp_path / "a.task").exists() and not list(tmp_path.glob("*.part"))

    def boom(u, d):
        raise OSError("offline")

    with pytest.raises(ModelError):
        ensure_model(tmp_path / "b.task", downloader=boom)


def test_sha256_of(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"hello")
    assert sha256_of(p) == hashlib.sha256(b"hello").hexdigest()
