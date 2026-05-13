from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DropVoice API"
    environment: str = "development"
    api_prefix: str = "/v1"
    database_url: str = "sqlite+aiosqlite:///./dropvoice.db"
    device_token_secret: str = "change-me"
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:5500",
            "http://localhost:5500",
            "http://127.0.0.1:8080",
            "http://localhost:8080",
        ]
    )

    cartesia_api_key: str = ""
    cartesia_base_url: str = "https://api.cartesia.ai"
    cartesia_api_version: str = "2026-03-01"
    cartesia_model_id: str = "sonic-3-2026-01-12"
    cartesia_default_voice_id: str = "6ccbfb76-1fc6-48f7-b71d-91ac6298247b"
    cartesia_concurrency_limit: int = 3
    mock_tts: bool = True
    pronunciation_dict_path: str = "pronunciation.json"
    default_pace: str = "normal"

    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    transcript_rewriter: str = "groq"

    opay_merchant_id: str = ""
    opay_public_key: str = ""
    opay_private_key: str = ""
    opay_api_base_url: str = "https://testapi.opaycheckout.com"
    opay_callback_url: str = "https://api.example.com/v1/topups/opay/webhook"
    opay_return_url: str = "dropvoice://payments/return"
    opay_cancel_url: str = "dropvoice://payments/cancel"
    mock_payments: bool = True

    default_language: str = "en"
    supported_languages: list[str] = Field(
        default_factory=lambda: [
            "en",
            "ar",
            "zh",
            "hi",
            "es",
            "fr",
            "de",
            "pt",
            "it",
            "ja",
            "ko",
            "ru",
            "nl",
            "tr",
            "pl",
        ]
    )
    price_per_generation_kobo: int = 400_000
    char_limit: int = 400
    max_clone_upload_bytes: int = 5 * 1024 * 1024
    clone_min_duration_seconds: int = 5
    clone_max_duration_seconds: int = 20
    audio_ttl_minutes: int = 60
    queue_poll_interval_ms: int = 1000

    storage_root: Path = Path("storage")

    @field_validator("supported_languages", mode="before")
    @classmethod
    def parse_supported_languages(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def audio_storage_dir(self) -> Path:
        return self.storage_root / "audio"

    @property
    def input_storage_dir(self) -> Path:
        return self.storage_root / "inputs"

    @property
    def pronunciation_dict_file(self) -> Path:
        return Path(self.pronunciation_dict_path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
