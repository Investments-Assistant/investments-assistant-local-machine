"""Tests for the Hugging Face GGUF downloader without downloading models."""

from __future__ import annotations

import sys
from types import ModuleType
from pathlib import Path
import importlib.util

import pytest

# Import a regular application module during collection so the repository's
# shared autouse environment fixture does not import the DB graph mid-fixture.
import src.news.email_reader  # noqa: F401

SCRIPT = Path(__file__).parents[2] / "scripts" / "download_model.py"


@pytest.fixture
def downloader() -> ModuleType:
    spec = importlib.util.spec_from_file_location("download_model_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_qwen_7b_resolves_current_official_shards(downloader: ModuleType, monkeypatch) -> None:
    official = downloader.PRESETS["qwen2.5-7b"].sources[0]
    monkeypatch.setattr(downloader, "_repo_files", lambda repo: set(official.files))

    resolved = downloader._resolve_source(downloader.PRESETS["qwen2.5-7b"])

    assert resolved == official
    assert len(resolved.files) == 2
    assert resolved.files[0].endswith("-00001-of-00002.gguf")


def test_resolver_uses_single_file_fallback_when_preferred_source_is_stale(
    downloader: ModuleType, monkeypatch
) -> None:
    fallback = downloader.PRESETS["qwen2.5-7b"].sources[1]

    def files_for(repo: str) -> set[str]:
        return set(fallback.files) if repo == fallback.repo else set()

    monkeypatch.setattr(downloader, "_repo_files", files_for)

    assert downloader._resolve_source(downloader.PRESETS["qwen2.5-7b"]) == fallback


def test_resolver_keeps_direct_download_available_during_metadata_outage(
    downloader: ModuleType, monkeypatch, capsys
) -> None:
    def metadata_outage(repo: str) -> set[str]:
        raise OSError("temporary network failure")

    monkeypatch.setattr(downloader, "_repo_files", metadata_outage)

    resolved = downloader._resolve_source(downloader.PRESETS["qwen2.5-7b"])

    assert resolved == downloader.PRESETS["qwen2.5-7b"].sources[0]
    assert "trying the preferred source directly" in capsys.readouterr().out


class _FakeResponse:
    headers = {"Content-Length": "8"}

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = iter(chunks)

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        return next(self._chunks, b"")


def test_download_publishes_only_after_complete_file(
    downloader: ModuleType, monkeypatch, tmp_path
) -> None:
    destination = tmp_path / "model.gguf"
    monkeypatch.setattr(
        downloader.urllib.request,
        "urlopen",
        lambda request, timeout: _FakeResponse([b"gguf", b"data"]),
    )

    downloader._download_file("https://example.invalid/model.gguf", destination)

    assert destination.read_bytes() == b"ggufdata"
    assert not destination.with_name("model.gguf.part").exists()


def test_download_removes_partial_file_after_failure(
    downloader: ModuleType, monkeypatch, tmp_path
) -> None:
    destination = tmp_path / "model.gguf"

    class FailingResponse(_FakeResponse):
        def read(self, size: int) -> bytes:
            if not hasattr(self, "_failed"):
                self._failed = True
                return b"partial"
            raise OSError("connection dropped")

    monkeypatch.setattr(
        downloader.urllib.request,
        "urlopen",
        lambda request, timeout: FailingResponse([b"ignored"]),
    )

    with pytest.raises(OSError, match="connection dropped"):
        downloader._download_file("https://example.invalid/model.gguf", destination)

    assert not destination.exists()
    assert not destination.with_name("model.gguf.part").exists()


def test_failed_shard_download_preserves_an_existing_complete_shard(
    downloader: ModuleType, monkeypatch, tmp_path
) -> None:
    source = downloader.ModelSource("example/model", ("first.gguf", "second.gguf"))
    preset = downloader.ModelPreset((source,), "1 GB", "test")
    first = tmp_path / "first.gguf"
    first.write_bytes(b"existing complete shard")

    def offline_download(url: str, destination: Path) -> None:
        raise OSError("offline")

    monkeypatch.setattr(downloader, "_resolve_source", lambda value: source)
    monkeypatch.setattr(downloader, "_download_file", offline_download)
    monkeypatch.setitem(downloader.PRESETS, "test", preset)

    with pytest.raises(SystemExit):
        downloader.download("test", tmp_path)

    assert first.read_bytes() == b"existing complete shard"
    assert not (tmp_path / "second.gguf").exists()
