import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.models import Device, GenerationJob, JobStatus, Wallet
from app.routes.wallet import get_current_device
from app.schemas import GenerationResponse, GenerationStatusResponse
from app.services.audio_clean import preprocess_clone
from app.services.queue import GenerationProcessor
from app.services.storage import delete_path, save_upload
from app.services.wallets import apply_wallet_delta
from app.models import WalletTransactionKind
from app.services.app_settings import get_price_per_generation_kobo


router = APIRouter(prefix="/generations", tags=["generations"])


def normalize_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


VALID_PACES = {"slow", "normal", "fast"}


@router.post("", response_model=GenerationResponse)
async def create_generation(
    request: Request,
    text: str = Form(...),
    emotion: str = Form("neutral"),
    language: str = Form("en"),
    pace: str = Form("normal"),
    important_terms: str | None = Form(default=None),
    voice_clone: UploadFile | None = File(default=None),
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> GenerationResponse:
    settings = get_settings()
    clean_text = text.strip()
    if not clean_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text is required.")
    if len(clean_text) > settings.char_limit:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Text exceeds {settings.char_limit} characters.")
    if language not in settings.supported_languages:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported language.")
    pace_value = (pace or settings.default_pace).lower().strip()
    if pace_value not in VALID_PACES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid pace value.")

    price_per_generation_kobo = await get_price_per_generation_kobo(session)
    wallet = await session.get(Wallet, device.wallet.id)
    if not wallet or wallet.balance_kobo < price_per_generation_kobo:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Insufficient wallet balance.")

    clone_path = None
    clone_content_type = None
    if voice_clone:
        content_type = voice_clone.content_type or ""
        if not content_type.startswith("audio/"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only audio voice clone uploads are supported in v1.")
        try:
            clone_path, clone_content_type = await save_upload(voice_clone)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await apply_wallet_delta(
        session,
        wallet,
        delta_kobo=-price_per_generation_kobo,
        kind=WalletTransactionKind.debit,
        reference=f"generation:charge:{device.id}:{datetime.now(timezone.utc).timestamp()}",
        details={"language": language, "emotion": emotion},
    )
    job = GenerationJob(
        wallet_id=wallet.id,
        text=clean_text,
        char_count=len(clean_text),
        language=language,
        emotion=emotion.lower().strip(),
        pace=pace_value,
        important_terms_raw=(important_terms.strip() if important_terms else None) or None,
        model_id=settings.cartesia_model_id,
        charged_kobo=price_per_generation_kobo,
        used_voice_clone=bool(clone_path),
        clone_input_path=clone_path,
        clone_content_type=clone_content_type,
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    processor: GenerationProcessor = request.app.state.generation_processor
    if clone_path:
        cleanup_task = asyncio.create_task(asyncio.to_thread(preprocess_clone, clone_path))
        processor.attach_clone_cleanup(job.id, cleanup_task)
    processor.kick()

    return GenerationResponse(
        id=job.id,
        status=job.status.value,
        charged_kobo=job.charged_kobo,
        balance_kobo=wallet.balance_kobo,
    )


@router.get("/{job_id}", response_model=GenerationStatusResponse)
async def get_generation(
    job_id: str,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> GenerationStatusResponse:
    job = await session.get(GenerationJob, job_id)
    if not job or job.wallet_id != device.wallet.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found.")
    download_url = f"/v1/generations/{job.id}/audio" if job.audio_path else None
    clear_url = f"/v1/generations/{job.id}/audio" if job.audio_path else None
    return GenerationStatusResponse(
        id=job.id,
        status=job.status.value,
        charged_kobo=job.charged_kobo,
        language=job.language,
        emotion=job.emotion,
        pace=job.pace,
        error_message=job.error_message,
        audio_download_url=download_url,
        audio_clear_url=clear_url,
        expires_at=job.expires_at,
    )


@router.get("/{job_id}/audio")
async def download_generation_audio(
    job_id: str,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    job = await session.get(GenerationJob, job_id)
    if not job or job.wallet_id != device.wallet.id or not job.audio_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audio not found.")
    expires_at = normalize_utc(job.expires_at)
    if expires_at and expires_at < datetime.now(timezone.utc):
        delete_path(job.audio_path)
        job.audio_path = None
        job.audio_mime = None
        job.expires_at = None
        await session.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Audio has expired.")
    filename = Path(job.audio_path).name
    return FileResponse(job.audio_path, media_type=job.audio_mime or "audio/mpeg", filename=filename)


@router.delete("/{job_id}/audio", status_code=status.HTTP_204_NO_CONTENT)
async def clear_generation_audio(
    job_id: str,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> None:
    job = await session.get(GenerationJob, job_id)
    if not job or job.wallet_id != device.wallet.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found.")
    delete_path(job.audio_path)
    job.audio_path = None
    job.audio_mime = None
    await session.commit()
