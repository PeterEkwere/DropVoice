from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from app.config import get_settings
from app.db.session import get_session
from app.models import Device, Topup, TopupStatus, Wallet
from app.models.entities import utcnow
from app.routes.wallet import get_current_device
from app.schemas import TopupInitiateRequest, TopupResponse
from app.services.opay import OPayClient
from app.services.wallets import apply_wallet_delta
from app.models import WalletTransactionKind


router = APIRouter(prefix="/topups", tags=["topups"])


@router.post("/initiate", response_model=TopupResponse)
async def initiate_topup(
    payload: TopupInitiateRequest,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> TopupResponse:
    settings = get_settings()
    opay = OPayClient()
    if not settings.mock_payments and not opay.configured:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="OPay is not configured.")

    reference = f"dv-topup-{uuid4().hex[:18]}"
    if settings.mock_payments:
        topup = Topup(
            wallet_id=device.wallet.id,
            reference=reference,
            amount_kobo=payload.amount_kobo,
            status=TopupStatus.succeeded,
            cashier_url=None,
            provider_order_no=f"mock-{reference}",
            completed_at=utcnow(),
        )
        session.add(topup)
        wallet = await session.get(Wallet, device.wallet.id)
        if wallet:
            await apply_wallet_delta(
                session,
                wallet,
                delta_kobo=payload.amount_kobo,
                kind=WalletTransactionKind.credit,
                reference=f"topup:{topup.reference}",
                details={"provider": "mock"},
            )
    else:
        visit_source = "ANDROID" if device.platform == "android" else "IOS" if device.platform == "ios" else "BROWSER"
        return_url = payload.return_url or settings.opay_return_url
        cancel_url = payload.cancel_url or settings.opay_cancel_url
        opay_response = await opay.create_cashier(
            reference=reference,
            amount_kobo=payload.amount_kobo,
            return_url=return_url,
            cancel_url=cancel_url,
            visit_source=visit_source,
            pay_method=payload.pay_method,
            customer_name=payload.customer_name,
            customer_email=payload.customer_email,
            customer_phone=payload.customer_phone,
            customer_user_id=device.installation_id,
        )

        cashier_url = opay_response.get("data", {}).get("cashierUrl")
        topup = Topup(
            wallet_id=device.wallet.id,
            reference=reference,
            amount_kobo=payload.amount_kobo,
            status=TopupStatus.pending,
            cashier_url=cashier_url,
            provider_order_no=opay_response.get("data", {}).get("orderNo"),
        )
        session.add(topup)
    await session.commit()
    return TopupResponse(
        reference=topup.reference,
        status=topup.status.value,
        amount_kobo=topup.amount_kobo,
        cashier_url=topup.cashier_url,
        created_at=topup.created_at,
    )


@router.get("/{reference}", response_model=TopupResponse)
async def get_topup(
    reference: str,
    device: Device = Depends(get_current_device),
    session: AsyncSession = Depends(get_session),
) -> TopupResponse:
    result = await session.execute(
        select(Topup)
        .where(Topup.reference == reference)
        .where(Topup.wallet_id == device.wallet.id)
    )
    topup = result.scalar_one_or_none()
    if not topup:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Top-up not found.")
    if topup.status == TopupStatus.pending and not get_settings().mock_payments:
        await sync_topup_status(topup, session)
    return TopupResponse(
        reference=topup.reference,
        status=topup.status.value,
        amount_kobo=topup.amount_kobo,
        cashier_url=topup.cashier_url,
        created_at=topup.created_at,
    )


@router.post("/opay/webhook", include_in_schema=False)
async def opay_webhook(request: Request, session: AsyncSession = Depends(get_session)) -> Response:
    if get_settings().mock_payments:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    payload = await request.json()
    opay = OPayClient()
    if not opay.verify_callback_signature(payload):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OPay callback signature.")

    callback_payload = payload.get("payload", {})
    reference = callback_payload.get("reference")
    if not reference:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing OPay reference.")

    result = await session.execute(select(Topup).where(Topup.reference == reference))
    topup = result.scalar_one_or_none()
    if not topup:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    if topup.status == TopupStatus.succeeded:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    topup.raw_callback_json = payload
    await sync_topup_status(topup, session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def sync_topup_status(topup: Topup, session: AsyncSession) -> Topup:
    opay = OPayClient()
    status_payload = await opay.query_status(topup.reference)
    payment_status = (
        status_payload.get("data", {}).get("status")
        or status_payload.get("status")
        or ""
    ).lower()

    if payment_status in {"success", "successful", "paid"} and topup.status != TopupStatus.succeeded:
        wallet = await session.get(Wallet, topup.wallet_id)
        if wallet:
            await apply_wallet_delta(
                session,
                wallet,
                delta_kobo=topup.amount_kobo,
                kind=WalletTransactionKind.credit,
                reference=f"topup:{topup.reference}",
                details={"provider": "opay"},
            )
        topup.status = TopupStatus.succeeded
        topup.completed_at = utcnow()
    elif payment_status in {"failed", "cancelled"}:
        topup.status = TopupStatus.failed
    elif payment_status in {"expired"}:
        topup.status = TopupStatus.expired

    await session.commit()
    await session.refresh(topup)
    return topup
