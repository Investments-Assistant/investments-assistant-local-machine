#!/usr/bin/env python3
"""Download a GGUF model from Hugging Face for the llama_cpp backend.

Models are saved to /app/models/ by default (override with --output-dir).
After downloading, set LLM_MODEL_PATH in your .env to the printed path.

The Hugging Face repositories occasionally change filenames or split a GGUF
into multiple shards.  Presets therefore contain ordered source candidates and
the downloader verifies the current repository file list before downloading.
When the metadata endpoint is unavailable, it falls back to the first known
source and lets the normal download error explain what went wrong.

Usage
-----
    python3 scripts/download_model.py --list             # show available presets
    python3 scripts/download_model.py qwen2.5-7b         # download by key
    python3 scripts/download_model.py                    # interactive picker
    python3 scripts/download_model.py qwen2.5-7b \
        --output-dir ~/models                           # custom directory
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
import urllib.error
import urllib.request


@dataclass(frozen=True)
class ModelSource:
    """One complete model file set in a Hugging Face repository.

    A split GGUF is represented by all of its shard names.  llama.cpp loads a
    split model by receiving the path to the first shard, provided the other
    shards remain beside it.
    """

    repo: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class ModelPreset:
    sources: tuple[ModelSource, ...]
    size: str
    notes: str

    @property
    def display_file(self) -> str:
        return self.sources[0].files[0]


# ---------------------------------------------------------------------------
# Preset catalogue — verified to work with llama-cpp-python tool calling.
# Sources are ordered by preference.  The first Qwen 7B source is the official
# current two-shard repository; the second is a known single-file mirror.
# ---------------------------------------------------------------------------
PRESETS: dict[str, ModelPreset] = {
    "qwen2.5-7b": ModelPreset(
        sources=(
            ModelSource(
                repo="Qwen/Qwen2.5-7B-Instruct-GGUF",
                files=(
                    "qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf",
                    "qwen2.5-7b-instruct-q4_k_m-00002-of-00002.gguf",
                ),
            ),
            ModelSource(
                repo="bartowski/Qwen2.5-7B-Instruct-GGUF",
                files=("Qwen2.5-7B-Instruct-Q4_K_M.gguf",),
            ),
        ),
        size="~4.7 GB",
        notes="Best quality/speed on Pi 5 (8 GB RAM). Native tool calling.",
    ),
    "qwen2.5-3b": ModelPreset(
        sources=(
            ModelSource(
                repo="Qwen/Qwen2.5-3B-Instruct-GGUF",
                files=("qwen2.5-3b-instruct-q8_0.gguf",),
            ),
        ),
        size="~3.3 GB",
        notes="Lighter Qwen. Faster inference, slightly lower quality.",
    ),
    "qwen2.5-1.5b": ModelPreset(
        sources=(
            ModelSource(
                repo="Qwen/Qwen2.5-1.5B-Instruct-GGUF",
                files=("qwen2.5-1.5b-instruct-q4_k_m.gguf",),
            ),
        ),
        size="~1.0 GB",
        notes="Fastest Qwen option for CPU-only Raspberry Pi deployments.",
    ),
    "llama3.2-3b": ModelPreset(
        sources=(
            ModelSource(
                repo="bartowski/Llama-3.2-3B-Instruct-GGUF",
                files=("Llama-3.2-3B-Instruct-Q8_0.gguf",),
            ),
        ),
        size="~3.4 GB",
        notes="Good for testing or memory-constrained setups.",
    ),
    "llama3.1-8b": ModelPreset(
        sources=(
            ModelSource(
                repo="bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
                files=("Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",),
            ),
        ),
        size="~4.9 GB",
        notes="Strong instruction-following and tool use. Needs 8 GB RAM.",
    ),
    "mistral-7b": ModelPreset(
        sources=(
            ModelSource(
                repo="TheBloke/Mistral-7B-Instruct-v0.3-GGUF",
                files=("mistral-7b-instruct-v0.3.Q4_K_M.gguf",),
            ),
        ),
        size="~4.4 GB",
        notes="Solid all-rounder. Good function calling support.",
    ),
    "phi4-14b": ModelPreset(
        sources=(
            ModelSource(
                repo="bartowski/phi-4-GGUF",
                files=("phi-4-Q4_K_M.gguf",),
            ),
        ),
        size="~8.9 GB",
        notes="Microsoft Phi-4. Excellent reasoning. Needs GPU or 16+ GB RAM.",
    ),
}

HF_BASE = "https://huggingface.co"
HF_API_TIMEOUT_SECONDS = 20
DOWNLOAD_TIMEOUT_SECONDS = 120
USER_AGENT = "investments-assistant-model-downloader/1.0"


def list_presets() -> None:
    print("\nAvailable model presets:\n")
    col = max(len(k) for k in PRESETS) + 2
    print(f"  {'Key':{col}} {'Size':<12} Notes")
    print(f"  {'-' * col} {'-' * 12} {'-' * 52}")
    for key, info in PRESETS.items():
        print(f"  {key:{col}} {info.size:<12} {info.notes}")
    print()


def _print_progress(downloaded: int, total_size: int) -> None:
    if total_size <= 0:
        return
    pct = min(100, int(downloaded * 100 / total_size))
    filled = pct // 2
    bar = "#" * filled + "-" * (50 - filled)
    print(f"\r  [{bar}] {pct:3d}%", end="", flush=True)


def _request_json(url: str) -> object:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HF_API_TIMEOUT_SECONDS) as response:
        return json.load(response)


def _repo_files(repo: str) -> set[str]:
    """Return the repository's known filenames using the public HF metadata API."""

    payload = _request_json(f"{HF_BASE}/api/models/{repo}")
    if not isinstance(payload, dict):
        raise ValueError("Hugging Face returned an unexpected metadata response")
    siblings = payload.get("siblings")
    if not isinstance(siblings, list):
        raise ValueError("Hugging Face metadata did not contain a file list")
    return {
        item["rfilename"]
        for item in siblings
        if isinstance(item, dict) and isinstance(item.get("rfilename"), str)
    }


def _resolve_source(preset: ModelPreset) -> ModelSource:
    """Select the first complete, currently available model file set.

    Metadata lookup is deliberately best-effort.  A temporary API outage must
    not prevent a direct download from a known-good URL.
    """

    metadata_errors: list[str] = []
    for source in preset.sources:
        try:
            available = _repo_files(source.repo)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            metadata_errors.append(f"{source.repo}: {exc}")
            continue
        if all(filename in available for filename in source.files):
            return source

    if metadata_errors:
        print("  Could not verify Hugging Face metadata; trying the preferred source directly.")
        return preset.sources[0]

    candidates = ", ".join(
        f"{source.repo} ({', '.join(source.files)})" for source in preset.sources
    )
    raise RuntimeError(f"No complete model file set was found. Candidates: {candidates}")


def _download_file(url: str, destination: Path) -> None:
    """Download to a temporary sibling and publish only after success."""

    partial = destination.with_name(destination.name + ".part")
    partial.unlink(missing_ok=True)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            content_length = response.headers.get("Content-Length")
            total_size = int(content_length) if content_length and content_length.isdigit() else 0
            downloaded = 0
            with partial.open("wb") as handle:
                while chunk := response.read(1024 * 1024):
                    handle.write(chunk)
                    downloaded += len(chunk)
                    _print_progress(downloaded, total_size)
        if not partial.is_file() or partial.stat().st_size == 0:
            raise OSError("Hugging Face returned an empty file")
        partial.replace(destination)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def download(key: str, output_dir: Path) -> Path:
    if key not in PRESETS:
        print(f"\nError: unknown model key '{key}'.")
        print("Run with --list to see available presets.")
        sys.exit(1)

    preset = PRESETS[key]
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        source = _resolve_source(preset)
    except RuntimeError as exc:
        print(f"\nError resolving model source: {exc}")
        sys.exit(1)

    destinations = [output_dir / filename for filename in source.files]
    if all(
        destination.is_file() and destination.stat().st_size > 0 for destination in destinations
    ):
        size_gb = sum(destination.stat().st_size for destination in destinations) / 1024**3
        print(f"\nModel already exists at {destinations[0]} ({size_gb:.1f} GB total)")
        if len(destinations) > 1:
            print(f"  Verified {len(destinations)} model shards.")
        return destinations[0]

    print(f"\nDownloading {key}  ({preset.size})")
    print(f"  Repository: {source.repo}")
    if len(source.files) > 1:
        print(f"  Shards    : {len(source.files)} (all are required by llama.cpp)")

    downloaded_this_run: list[Path] = []
    try:
        for index, (filename, destination) in enumerate(
            zip(source.files, destinations, strict=True), start=1
        ):
            if destination.is_file() and destination.stat().st_size > 0:
                print(f"  Source {index}/{len(source.files)}: already present at {destination}")
                continue
            destination.unlink(missing_ok=True)
            url = f"{HF_BASE}/{source.repo}/resolve/main/{filename}"
            print(f"  Source {index}/{len(source.files)}: {url}")
            print(f"  Target          : {destination}\n")
            _download_file(url, destination)
            downloaded_this_run.append(destination)
    except Exception as exc:
        print(f"\n\nDownload failed: {exc}")
        # Remove files from this attempt so a failed multi-shard download is
        # never mistaken for a complete model on the next run.
        for destination in downloaded_this_run:
            destination.unlink(missing_ok=True)
        sys.exit(1)

    print(f"\n\nDownload complete: {destinations[0]}")
    if len(destinations) > 1:
        print("All shards downloaded. Point LLM_MODEL_PATH at the first shard above.")
    return destinations[0]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download GGUF models for the investment-assistant llama_cpp backend"
    )
    parser.add_argument("model", nargs="?", help="Model key (see --list for options)")
    parser.add_argument("--list", action="store_true", help="List available model presets")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/app/models"),
        help="Directory to save the model file(s) (default: /app/models)",
    )
    args = parser.parse_args()

    if args.list:
        list_presets()
        return

    if args.model:
        dest = download(args.model, args.output_dir)
        print(f"\nAdd to your .env:\n  LLM_MODEL_PATH={dest}\n")
        return

    # Interactive mode
    list_presets()
    key = input("Enter model key to download (or press Enter to cancel): ").strip()
    if not key:
        print("Cancelled.")
        return
    dest = download(key, args.output_dir)
    print(f"\nAdd to your .env:\n  LLM_MODEL_PATH={dest}\n")


if __name__ == "__main__":
    main()
