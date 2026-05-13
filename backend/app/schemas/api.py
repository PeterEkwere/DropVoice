from datetime import datetime

from pydantic import BaseModel, Field


class SupportedLanguage(BaseModel):
    code: str
    label: str


class BootstrapRequest(BaseModel):
    installation_id: str = Field(min_length=8, max_length=128)
    platform: str = Field(min_length=2, max_length=32)
    app_version: str | None = Field(default=None, max_length=32)


class BootstrapResponse(BaseModel):
    device_token: str
    balance_kobo: int
    currency: str
    default_language: str
    supported_languages: list[SupportedLanguage]
    price_per_generation_kobo: int
    char_limit: int
    default_voice_label: str


class WalletTransactionItem(BaseModel):
    id: str
    kind: str
    amount_kobo: int
    balance_after_kobo: int
    reference: str
    created_at: datetime


class WalletResponse(BaseModel):
    wallet_id: str
    balance_kobo: int
    currency: str
    transactions: list[WalletTransactionItem]


class TopupInitiateRequest(BaseModel):
    amount_kobo: int = Field(gt=0)
    return_url: str | None = None
    cancel_url: str | None = None
    pay_method: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None


class TopupResponse(BaseModel):
    reference: str
    status: str
    amount_kobo: int
    cashier_url: str | None
    created_at: datetime


class GenerationResponse(BaseModel):
    id: str
    status: str
    charged_kobo: int
    balance_kobo: int
    audio_download_url: str | None = None
    audio_clear_url: str | None = None
    expires_at: datetime | None = None


class GenerationStatusResponse(BaseModel):
    id: str
    status: str
    charged_kobo: int
    language: str
    emotion: str
    pace: str
    error_message: str | None = None
    audio_download_url: str | None = None
    audio_clear_url: str | None = None
    expires_at: datetime | None = None

