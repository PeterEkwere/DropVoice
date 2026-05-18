from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

from app.db.session import SessionLocal
from app.models import Device, Wallet, WalletTransactionKind
from app.services.wallets import apply_wallet_delta


def format_naira(kobo: int | None) -> str:
    value = (kobo or 0) / 100
    return f"NGN {value:,.0f}"


async def list_devices(_: argparse.Namespace) -> None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Device)
            .options(selectinload(Device.wallet))
            .order_by(Device.last_seen_at.desc())
        )
        devices = list(result.scalars().all())

    if not devices:
        print("No devices found.")
        return

    columns = [
        ("device_id", 36),
        ("installation_id", 48),
        ("platform", 14),
        ("app_version", 12),
        ("balance", 14),
        ("last_seen_at", 26),
    ]
    print("  ".join(name.ljust(width) for name, width in columns))
    print("  ".join("-" * width for _, width in columns))
    for device in devices:
        wallet = device.wallet
        values = [
            device.id,
            device.installation_id,
            device.platform,
            device.app_version or "",
            format_naira(wallet.balance_kobo if wallet else 0),
            str(device.last_seen_at),
        ]
        print("  ".join(value.ljust(width) for value, (_, width) in zip(values, columns)))


async def resolve_device(session: AsyncSession, args: argparse.Namespace) -> Device:
    filters = []
    if args.device_id:
        filters.append(Device.id == args.device_id)
    if args.installation_id:
        filters.append(Device.installation_id == args.installation_id)

    if len(filters) != 1:
        raise SystemExit("Pass exactly one of --device-id or --installation-id.")

    result = await session.execute(
        select(Device)
        .options(selectinload(Device.wallet))
        .where(filters[0])
    )
    device = result.scalar_one_or_none()
    if not device:
        raise SystemExit("Device not found.")
    if not device.wallet:
        raise SystemExit("Device has no wallet.")
    return device


async def credit_wallet(args: argparse.Namespace) -> None:
    amount_kobo = int(args.amount_naira * 100)
    if amount_kobo <= 0:
        raise SystemExit("--amount-naira must be greater than zero.")

    async with SessionLocal() as session:
        device = await resolve_device(session, args)
        wallet = await session.get(Wallet, device.wallet.id)
        if not wallet:
            raise SystemExit("Wallet not found.")

        reference = args.reference or f"admin-credit:{uuid4().hex}"
        await apply_wallet_delta(
            session,
            wallet,
            delta_kobo=amount_kobo,
            kind=WalletTransactionKind.credit,
            reference=reference,
            details={"source": "dropvoice_admin_cli", "note": args.note},
        )
        await session.commit()

        print(f"Credited {format_naira(amount_kobo)} to installation_id={device.installation_id}")
        print(f"New balance: {format_naira(wallet.balance_kobo)}")
        print(f"Reference: {reference}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DropVoice device wallet admin tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-devices", help="Show devices with wallet balances")
    list_parser.set_defaults(func=list_devices)

    credit_parser = subparsers.add_parser("credit-wallet", help="Credit a device wallet")
    target = credit_parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--device-id")
    target.add_argument("--installation-id")
    credit_parser.add_argument("--amount-naira", type=int, required=True)
    credit_parser.add_argument("--reference")
    credit_parser.add_argument("--note", default="manual wallet credit")
    credit_parser.set_defaults(func=credit_wallet)

    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    await args.func(args)


if __name__ == "__main__":
    asyncio.run(main())
