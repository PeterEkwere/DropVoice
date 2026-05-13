from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_session
from app.models import Device, WalletTransaction
from app.schemas import WalletResponse, WalletTransactionItem
from app.services.auth import read_device_token


router = APIRouter(prefix="/wallet", tags=["wallet"])


async def get_current_device(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> Device:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing device token.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        device_id = read_device_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    result = await session.execute(
        select(Device)
        .options(selectinload(Device.wallet))
        .where(Device.id == device_id)
    )
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Device not found.")
    return device


@router.get("", response_model=WalletResponse)
async def get_wallet(device: Device = Depends(get_current_device), session: AsyncSession = Depends(get_session)) -> WalletResponse:
    result = await session.execute(
        select(WalletTransaction)
        .where(WalletTransaction.wallet_id == device.wallet.id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(20)
    )
    transactions = [
        WalletTransactionItem(
            id=item.id,
            kind=item.kind.value,
            amount_kobo=item.amount_kobo,
            balance_after_kobo=item.balance_after_kobo,
            reference=item.reference,
            created_at=item.created_at,
        )
        for item in result.scalars().all()
    ]
    return WalletResponse(
        wallet_id=device.wallet.id,
        balance_kobo=device.wallet.balance_kobo,
        currency=device.wallet.currency,
        transactions=transactions,
    )
