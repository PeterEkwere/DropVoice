from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Wallet, WalletTransaction, WalletTransactionKind


async def apply_wallet_delta(
    session: AsyncSession,
    wallet: Wallet,
    *,
    delta_kobo: int,
    kind: WalletTransactionKind,
    reference: str,
    details: dict | None = None,
) -> WalletTransaction:
    next_balance = wallet.balance_kobo + delta_kobo
    if next_balance < 0:
        raise ValueError("Insufficient wallet balance.")

    wallet.balance_kobo = next_balance
    transaction = WalletTransaction(
        wallet_id=wallet.id,
        kind=kind,
        amount_kobo=delta_kobo,
        balance_after_kobo=next_balance,
        reference=reference,
        details_json=details,
    )
    session.add(transaction)
    await session.flush()
    return transaction

