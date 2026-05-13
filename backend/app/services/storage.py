from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from app.config import get_settings


def _ensure_dirs() -> None:
    settings = get_settings()
    settings.audio_storage_dir.mkdir(parents=True, exist_ok=True)
    settings.input_storage_dir.mkdir(parents=True, exist_ok=True)


def _suffix_for_content_type(content_type: str | None, fallback: str = ".bin") -> str:
    if not content_type:
        return fallback
    if "mpeg" in content_type or "mp3" in content_type:
        return ".mp3"
    if "wav" in content_type:
        return ".wav"
    if "webm" in content_type:
        return ".webm"
    if "mp4" in content_type:
        return ".mp4"
    return fallback


async def save_upload(upload: UploadFile) -> tuple[str, str]:
    settings = get_settings()
    _ensure_dirs()
    content = await upload.read()
    if len(content) > settings.max_clone_upload_bytes:
        raise ValueError("Voice clone upload is too large.")

    content_type = upload.content_type or "application/octet-stream"
    suffix = _suffix_for_content_type(content_type, fallback=Path(upload.filename or "clip").suffix or ".bin")
    path = settings.input_storage_dir / f"{uuid4()}{suffix}"
    path.write_bytes(content)
    return str(path), content_type


def save_audio_bytes(job_id: str, content: bytes, content_type: str) -> str:
    settings = get_settings()
    _ensure_dirs()
    suffix = _suffix_for_content_type(content_type, fallback=".mp3")
    path = settings.audio_storage_dir / f"{job_id}{suffix}"
    path.write_bytes(content)
    return str(path)


def read_audio_bytes(path: str) -> bytes:
    return Path(path).read_bytes()


def delete_path(path: str | None) -> None:
    if not path:
        return
    file_path = Path(path)
    if file_path.exists():
        file_path.unlink(missing_ok=True)


def cleanup_expired_audio(audio_paths: list[str]) -> None:
    for path in audio_paths:
        delete_path(path)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

