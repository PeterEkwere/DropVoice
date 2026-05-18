from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AppSetting


PRICE_PER_GENERATION_KEY = "price_per_generation_kobo"


async def get_price_per_generation_kobo(session: AsyncSession) -> int:
    setting = await session.get(AppSetting, PRICE_PER_GENERATION_KEY)
    if not setting:
        return get_settings().price_per_generation_kobo
    try:
        value = int(setting.value)
    except (TypeError, ValueError):
        return get_settings().price_per_generation_kobo
    return value if value > 0 else get_settings().price_per_generation_kobo


async def set_price_per_generation_kobo(session: AsyncSession, amount_kobo: int) -> AppSetting:
    if amount_kobo <= 0:
        raise ValueError("Price must be greater than zero.")
    setting = await session.get(AppSetting, PRICE_PER_GENERATION_KEY)
    if not setting:
        setting = AppSetting(key=PRICE_PER_GENERATION_KEY, value=str(amount_kobo))
        session.add(setting)
    else:
        setting.value = str(amount_kobo)
    await session.flush()
    return setting
