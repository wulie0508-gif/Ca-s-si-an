"""Local interview transcription with case-owned artifacts."""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def transcribe_media(
    media_path: str | Path,
    output_dir: str | Path,
    *,
    model_name: str = "base",
    language: str | None = None,
    model_cache: str | Path | None = None,
) -> dict[str, Any]:
    """Run ffmpeg + faster-whisper locally using CPU int8."""

    source = Path(media_path)
    if not source.is_file():
        raise ValueError(f"Interview media does not exist: {source}")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for local interview transcription")
    try:
        faster_whisper = importlib.import_module("faster_whisper")
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is required for transcription; install it in the local environment"
        ) from exc
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ctf-interview-") as temporary:
        wav_path = Path(temporary) / "audio.wav"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-c:a",
                "pcm_s16le",
                str(wav_path),
            ],
            check=True,
        )
        model_kwargs: dict[str, Any] = {
            "device": "cpu",
            "compute_type": "int8",
        }
        if model_cache:
            model_kwargs["download_root"] = str(Path(model_cache))
        model = faster_whisper.WhisperModel(model_name, **model_kwargs)
        generated_segments, info = model.transcribe(
            str(wav_path),
            language=language,
            vad_filter=True,
            word_timestamps=True,
        )
        segments = [
            {
                "index": index,
                "start_seconds": round(float(segment.start), 3),
                "end_seconds": round(float(segment.end), 3),
                "text": str(segment.text).strip(),
                "words": [
                    {
                        "start_seconds": (
                            round(float(word.start), 3) if word.start is not None else None
                        ),
                        "end_seconds": (
                            round(float(word.end), 3) if word.end is not None else None
                        ),
                        "word": str(word.word),
                        "probability": round(float(word.probability), 4),
                    }
                    for word in (segment.words or [])
                ],
            }
            for index, segment in enumerate(generated_segments, start=1)
        ]
    stem = source.stem
    transcript_path = target / f"{stem}.transcript.txt"
    index_path = target / f"{stem}.transcript.json"
    transcript_path.write_text(
        "\n".join(
            f"[{item['start_seconds']:.3f}-{item['end_seconds']:.3f}] {item['text']}"
            for item in segments
        )
        + "\n",
        encoding="utf-8",
    )
    index_path.write_text(
        json.dumps(
            {
                "source_media": str(source.resolve()),
                "model": model_name,
                "device": "cpu",
                "compute_type": "int8",
                "language": getattr(info, "language", language),
                "language_probability": getattr(info, "language_probability", None),
                "segments": segments,
                "rag_ingestion": False,
                "authority": "Case-owned transcript; owner statements are not verified facts.",
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "transcript_path": str(transcript_path.resolve()),
        "index_path": str(index_path.resolve()),
        "model": model_name,
        "language": getattr(info, "language", language),
        "segments": segments,
    }
