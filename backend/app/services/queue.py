from __future__ import annotations

import asyncio
import contextlib
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.config import get_settings
from app.db.session import SessionLocal
from app.models import GenerationJob, JobStatus, Wallet, WalletTransactionKind
from app.models.entities import utcnow
from app.services.audio_clean import CloneRejected, preprocess_clone
from app.services.cartesia import CartesiaClient
from app.services.pronunciation import (
    PronunciationEntry,
    load_global_dictionary,
    merge_dictionaries,
    parse_terms_string,
)
from app.services.storage import cleanup_expired_audio, delete_path, save_audio_bytes
from app.services.transcript import CompiledSegment, compile_transcript
from app.services.transcript_llm import rewrite_with_groq
from app.services.wallets import apply_wallet_delta


class GenerationProcessor:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.cartesia = CartesiaClient()
        self._wakeup = asyncio.Event()
        self._running = False
        self._tasks: set[asyncio.Task] = set()
        self._global_dict: list[PronunciationEntry] | None = None
        self._clone_cleanups: dict[str, asyncio.Task] = {}

    def kick(self) -> None:
        self._wakeup.set()

    def attach_clone_cleanup(self, job_id: str, task: asyncio.Task) -> None:
        self._clone_cleanups[job_id] = task

    def _take_clone_cleanup(self, job_id: str) -> asyncio.Task | None:
        return self._clone_cleanups.pop(job_id, None)

    def _global_pronunciations(self) -> list[PronunciationEntry]:
        if self._global_dict is None:
            self._global_dict = load_global_dictionary(self.settings.pronunciation_dict_file)
        return self._global_dict

    async def run(self) -> None:
        self._running = True
        while self._running:
            await self._cleanup_expired()
            capacity = self.settings.cartesia_concurrency_limit - len(self._tasks)
            if capacity > 0:
                job_ids = await self._next_queued_job_ids(capacity)
                for job_id in job_ids:
                    task = asyncio.create_task(self._process_one(job_id))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)

            try:
                await asyncio.wait_for(self._wakeup.wait(), timeout=self.settings.queue_poll_interval_ms / 1000)
            except asyncio.TimeoutError:
                continue
            finally:
                self._wakeup.clear()

    async def stop(self) -> None:
        self._running = False
        self._wakeup.set()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _next_queued_job_ids(self, limit: int) -> list[str]:
        async with SessionLocal() as session:
            result = await session.execute(
                select(GenerationJob.id)
                .where(GenerationJob.status == JobStatus.queued)
                .order_by(GenerationJob.created_at.asc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def _cleanup_expired(self) -> None:
        async with SessionLocal() as session:
            result = await session.execute(
                select(GenerationJob)
                .where(GenerationJob.status == JobStatus.completed)
                .where(GenerationJob.expires_at.is_not(None))
                .where(GenerationJob.expires_at < utcnow())
                .where(GenerationJob.audio_path.is_not(None))
            )
            jobs = list(result.scalars().all())
            cleanup_expired_audio([job.audio_path for job in jobs if job.audio_path])
            for job in jobs:
                job.audio_path = None
                job.audio_mime = None
                job.expires_at = None
            await session.commit()

    async def _process_one(self, job_id: str) -> None:
        voice_id_to_delete: str | None = None
        clone_path_to_cleanup: str | None = None
        rewrite_task: asyncio.Task | None = None
        cleanup_task: asyncio.Task | None = None
        try:
            async with SessionLocal() as session:
                job = await session.get(GenerationJob, job_id)
                if not job or job.status != JobStatus.queued:
                    return
                job.status = JobStatus.processing
                job.started_at = utcnow()
                await session.commit()

            async with SessionLocal() as session:
                job = await session.get(GenerationJob, job_id)
                if not job:
                    return

                pronunciations = merge_dictionaries(
                    self._global_pronunciations(),
                    parse_terms_string(job.important_terms_raw),
                )

                rewrite_task = asyncio.create_task(
                    rewrite_with_groq(job.text, job.emotion, job.pace)
                )

                cleanup_task = self._take_clone_cleanup(job.id)
                if job.clone_input_path and job.clone_content_type and cleanup_task is None:
                    cleanup_task = asyncio.create_task(
                        asyncio.to_thread(preprocess_clone, job.clone_input_path)
                    )

                voice_id = self.settings.cartesia_default_voice_id
                if cleanup_task is not None and job.clone_input_path and job.clone_content_type:
                    cleaned = await cleanup_task
                    cleanup_task = None
                    clone_path_to_cleanup = cleaned.path
                    voice_id = await self.cartesia.clone_voice(
                        cleaned.path, job.clone_content_type, job.language
                    )
                    voice_id_to_delete = voice_id
                    job.cartesia_voice_id = voice_id
                    await session.commit()

                rewritten = await rewrite_task
                rewrite_task = None
                if rewritten:
                    compiled = compile_transcript(
                        rewritten,
                        emotion_preset=job.emotion,
                        pace=job.pace,
                        pronunciations=pronunciations,
                        pretagged=True,
                    )
                else:
                    compiled = compile_transcript(
                        job.text,
                        emotion_preset=job.emotion,
                        pace=job.pace,
                        pronunciations=pronunciations,
                    )
                job.compiled_transcript = compiled.debug_text
                await session.commit()

                audio_chunks: list[tuple[bytes, str]] = []
                for segment in compiled.segments:
                    audio = await self.cartesia.synthesize_segment(
                        segment=segment,
                        language=job.language,
                        voice_id=voice_id,
                    )
                    audio_chunks.append((audio.content, audio.content_type))

                final_bytes, final_mime = _join_audio(audio_chunks)
                audio_path = save_audio_bytes(job.id, final_bytes, final_mime)
                job.status = JobStatus.completed
                job.audio_path = audio_path
                job.audio_mime = final_mime
                job.audio_size_bytes = len(final_bytes)
                job.completed_at = utcnow()
                job.expires_at = utcnow() + timedelta(minutes=self.settings.audio_ttl_minutes)
                await session.commit()
        except CloneRejected as exc:
            await self._fail_and_refund(job_id, str(exc))
        except Exception as exc:
            await self._fail_and_refund(job_id, str(exc))
        finally:
            for pending in (rewrite_task, cleanup_task):
                if pending is not None and not pending.done():
                    pending.cancel()
                    with contextlib.suppress(BaseException):
                        await pending
            if clone_path_to_cleanup:
                delete_path(clone_path_to_cleanup)
            if voice_id_to_delete:
                try:
                    await self.cartesia.delete_voice(voice_id_to_delete)
                except Exception:
                    pass

    async def _fail_and_refund(self, job_id: str, message: str) -> None:
        async with SessionLocal() as session:
            job = await session.get(GenerationJob, job_id)
            if not job:
                return
            job.status = JobStatus.failed
            job.error_message = message
            job.completed_at = utcnow()
            wallet = await session.get(Wallet, job.wallet_id)
            if wallet:
                await apply_wallet_delta(
                    session,
                    wallet,
                    delta_kobo=job.charged_kobo,
                    kind=WalletTransactionKind.refund,
                    reference=f"refund:{job.id}",
                    details={"reason": "generation_failed"},
                )
            await session.commit()


def _join_audio(chunks: list[tuple[bytes, str]]) -> tuple[bytes, str]:
    if len(chunks) == 1:
        return chunks[0]
    return _ffmpeg_concat(chunks)


def _ffmpeg_concat(chunks: list[tuple[bytes, str]]) -> tuple[bytes, str]:
    if not shutil.which("ffmpeg"):
        return chunks[0][0], chunks[0][1]

    settings = get_settings()
    settings.audio_storage_dir.mkdir(parents=True, exist_ok=True)
    work_dir = settings.audio_storage_dir / f".concat-{uuid4().hex[:8]}"
    work_dir.mkdir(parents=True, exist_ok=True)
    list_file = work_dir / "list.txt"
    parts: list[Path] = []
    try:
        with list_file.open("w", encoding="utf-8") as fh:
            for index, (data, mime) in enumerate(chunks):
                suffix = ".mp3" if "mpeg" in mime or "mp3" in mime else ".wav"
                part_path = work_dir / f"part-{index}{suffix}"
                part_path.write_bytes(data)
                parts.append(part_path)
                fh.write(f"file '{part_path.as_posix()}'\n")
        out_path = work_dir / "joined.mp3"
        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(out_path),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120)
        except (subprocess.SubprocessError, OSError):
            return chunks[0][0], chunks[0][1]
        if result.returncode != 0 or not out_path.exists():
            return chunks[0][0], chunks[0][1]
        return out_path.read_bytes(), "audio/mpeg"
    finally:
        for part in parts:
            part.unlink(missing_ok=True)
        list_file.unlink(missing_ok=True)
        out_candidate = work_dir / "joined.mp3"
        out_candidate.unlink(missing_ok=True)
        try:
            work_dir.rmdir()
        except OSError:
            pass
