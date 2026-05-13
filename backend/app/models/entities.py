from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class TopupStatus(str, Enum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    expired = "expired"


class WalletTransactionKind(str, Enum):
    credit = "credit"
    debit = "debit"
    refund = "refund"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    installation_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    platform: Mapped[str] = mapped_column(String(32))
    app_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    wallet: Mapped["Wallet"] = relationship(back_populates="device", uselist=False)


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), unique=True, index=True)
    currency: Mapped[str] = mapped_column(String(3), default="NGN")
    balance_kobo: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    device: Mapped[Device] = relationship(back_populates="wallet")
    transactions: Mapped[list["WalletTransaction"]] = relationship(back_populates="wallet")
    topups: Mapped[list["Topup"]] = relationship(back_populates="wallet")
    jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="wallet")


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id", ondelete="CASCADE"), index=True)
    kind: Mapped[WalletTransactionKind] = mapped_column(SqlEnum(WalletTransactionKind, native_enum=False, length=16))
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    balance_after_kobo: Mapped[int] = mapped_column(BigInteger)
    reference: Mapped[str] = mapped_column(String(128), index=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    wallet: Mapped[Wallet] = relationship(back_populates="transactions")


class Topup(Base):
    __tablename__ = "topups"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(16), default="opay")
    reference: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    amount_kobo: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[TopupStatus] = mapped_column(SqlEnum(TopupStatus, native_enum=False, length=16), default=TopupStatus.pending)
    cashier_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_order_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_callback_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    wallet: Mapped[Wallet] = relationship(back_populates="topups")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    wallet_id: Mapped[str] = mapped_column(ForeignKey("wallets.id", ondelete="CASCADE"), index=True)
    status: Mapped[JobStatus] = mapped_column(SqlEnum(JobStatus, native_enum=False, length=16), default=JobStatus.queued, index=True)
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer)
    language: Mapped[str] = mapped_column(String(8))
    emotion: Mapped[str] = mapped_column(String(32), default="neutral")
    pace: Mapped[str] = mapped_column(String(16), default="normal")
    important_terms_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    compiled_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_id: Mapped[str] = mapped_column(String(64))
    charged_kobo: Mapped[int] = mapped_column(BigInteger)
    used_voice_clone: Mapped[bool] = mapped_column(Boolean, default=False)
    clone_input_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    clone_content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cartesia_voice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_mime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audio_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    wallet: Mapped[Wallet] = relationship(back_populates="jobs")

