from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.db.session import get_session
from app.models import Device, Wallet
from app.models.entities import utcnow
from app.schemas import BootstrapRequest, BootstrapResponse, SupportedLanguage
from app.services.auth import issue_device_token
from app.services.cartesia import LANGUAGE_LABELS
from app.services.app_settings import get_price_per_generation_kobo


router = APIRouter(prefix="/device", tags=["device"])


@router.post("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_device(payload: BootstrapRequest, session: AsyncSession = Depends(get_session)) -> BootstrapResponse:
    settings = get_settings()
    result = await session.execute(
        select(Device)
        .options(selectinload(Device.wallet))
        .where(Device.installation_id == payload.installation_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        device = Device(
            installation_id=payload.installation_id,
            platform=payload.platform.lower(),
            app_version=payload.app_version,
            last_seen_at=utcnow(),
        )
        wallet = Wallet(currency="NGN", balance_kobo=0)
        device.wallet = wallet
        session.add(device)
    else:
        wallet = device.wallet
        device.platform = payload.platform.lower()
        device.app_version = payload.app_version
        device.last_seen_at = utcnow()

    await session.commit()

    supported_languages = [
        SupportedLanguage(code=code, label=LANGUAGE_LABELS[code])
        for code in settings.supported_languages
        if code in LANGUAGE_LABELS
    ]
    price_per_generation_kobo = await get_price_per_generation_kobo(session)
    return BootstrapResponse(
        device_token=issue_device_token(device.id),
        balance_kobo=wallet.balance_kobo,
        currency=wallet.currency,
        default_language=settings.default_language,
        supported_languages=supported_languages,
        price_per_generation_kobo=price_per_generation_kobo,
        char_limit=settings.char_limit,
        default_voice_label="Default English",
    )
