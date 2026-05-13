from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.config import get_settings


class CloneRejected(ValueError):
    pass


@dataclass
class CloneCleanResult:
    path: str
    duration_seconds: float
    cleaned: bool


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _probe_duration(path: str) -> float | None:
    if not shutil.which("ffprobe"):
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
        return float(payload["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def preprocess_clone(input_path: str) -> CloneCleanResult:
    settings = get_settings()
    src = Path(input_path)
    if not src.exists():
        raise CloneRejected("Voice clone file is missing.")

    if not _ffmpeg_available():
        duration = _probe_duration(str(src)) or 0.0
        return CloneCleanResult(path=str(src), duration_seconds=duration, cleaned=False)

    output = src.with_name(f"{src.stem}-clean-{uuid4().hex[:8]}.wav")
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(src),
        "-af",
        "silenceremove=start_periods=1:start_silence=0.1:start_threshold=-45dB:detection=peak,"
        "areverse,silenceremove=start_periods=1:start_silence=0.1:start_threshold=-45dB:detection=peak,areverse,"
        "loudnorm=I=-18:TP=-2:LRA=11",
        "-ar",
        "44100",
        "-ac",
        "1",
        str(output),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60)
    except (subprocess.SubprocessError, OSError):
        duration = _probe_duration(str(src)) or 0.0
        return CloneCleanResult(path=str(src), duration_seconds=duration, cleaned=False)

    if result.returncode != 0 or not output.exists():
        duration = _probe_duration(str(src)) or 0.0
        return CloneCleanResult(path=str(src), duration_seconds=duration, cleaned=False)

    duration = _probe_duration(str(output)) or 0.0
    if duration < settings.clone_min_duration_seconds:
        output.unlink(missing_ok=True)
        raise CloneRejected(
            f"Clone clip is too short after trimming silence (need ≥ {settings.clone_min_duration_seconds}s)."
        )
    if duration > settings.clone_max_duration_seconds:
        output.unlink(missing_ok=True)
        raise CloneRejected(
            f"Clone clip is too long ({duration:.1f}s, max {settings.clone_max_duration_seconds}s)."
        )

    try:
        src.unlink(missing_ok=True)
    except OSError:
        pass

    return CloneCleanResult(path=str(output), duration_seconds=duration, cleaned=True)
