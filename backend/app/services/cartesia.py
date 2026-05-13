from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import math
import struct
import wave

import httpx

from app.config import get_settings
from app.services.transcript import CompiledSegment


LANGUAGE_LABELS = {
    "en": "English",
    "ar": "Arabic",
    "zh": "Chinese",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
    "nl": "Dutch",
    "tr": "Turkish",
    "pl": "Polish",
}


@dataclass
class CartesiaAudioResult:
    content: bytes
    content_type: str


class CartesiaClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.cartesia_api_key}",
            "Cartesia-Version": self.settings.cartesia_api_version,
        }

    async def clone_voice(self, clip_path: str, content_type: str, language: str) -> str:
        if self.settings.mock_tts:
            return "mock-clone-voice"
        if not self.settings.cartesia_api_key:
            raise RuntimeError("Cartesia API key is not configured.")

        clip_bytes = Path(clip_path).read_bytes()
        files = {"clip": (Path(clip_path).name, clip_bytes, content_type)}
        data = {
            "name": f"dropvoice-{Path(clip_path).stem}",
            "description": "Temporary DropVoice instant clone",
            "language": language,
        }
        async with httpx.AsyncClient(base_url=self.settings.cartesia_base_url, timeout=90.0) as client:
            response = await client.post("/voices/clone", headers=self._headers, files=files, data=data)
            if response.status_code >= 400:
                raise_cartesia_error(response)
            payload = response.json()
        return payload["id"]

    async def delete_voice(self, voice_id: str) -> None:
        if self.settings.mock_tts:
            return
        async with httpx.AsyncClient(base_url=self.settings.cartesia_base_url, timeout=30.0) as client:
            response = await client.delete(f"/voices/{voice_id}", headers=self._headers)
            if response.status_code >= 400:
                raise_cartesia_error(response)

    async def synthesize_segment(
        self,
        *,
        segment: CompiledSegment,
        language: str,
        voice_id: str,
    ) -> CartesiaAudioResult:
        if self.settings.mock_tts:
            return CartesiaAudioResult(content=build_mock_wav(segment.text), content_type="audio/wav")
        if not self.settings.cartesia_api_key:
            raise RuntimeError("Cartesia API key is not configured.")

        payload: dict = {
            "model_id": self.settings.cartesia_model_id,
            "transcript": segment.text,
            "voice": {"mode": "id", "id": voice_id},
            "language": language,
            "output_format": {
                "container": "mp3",
                "sample_rate": 44100,
                "bit_rate": 128000,
            },
        }
        if self._supports_speed_volume():
            payload["speed"] = segment.speed
            payload["volume"] = segment.volume

        async with httpx.AsyncClient(base_url=self.settings.cartesia_base_url, timeout=120.0) as client:
            response = await client.post("/tts/bytes", headers=self._headers, json=payload)
            if response.status_code >= 400:
                raise_cartesia_error(response)
            return CartesiaAudioResult(
                content=response.content,
                content_type=response.headers.get("content-type", "audio/mpeg"),
            )

    def _supports_speed_volume(self) -> bool:
        model = (self.settings.cartesia_model_id or "").lower()
        return model.startswith("sonic-3") and not model.startswith("sonic-3.5")


def build_mock_wav(text: str) -> bytes:
    sample_rate = 22050
    duration_seconds = max(1.2, min(8.0, len(text) / 35))
    frequency = 440.0
    amplitude = 9000
    total_frames = int(sample_rate * duration_seconds)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        for frame_index in range(total_frames):
            envelope = 0.45 if frame_index < total_frames * 0.85 else 0.15
            sample = int(amplitude * envelope * math.sin((2.0 * math.pi * frequency * frame_index) / sample_rate))
            wav_file.writeframesraw(struct.pack("<h", sample))
    return buffer.getvalue()


def raise_cartesia_error(response: httpx.Response) -> None:
    message = f"Cartesia request failed ({response.status_code})."
    try:
        payload = response.json()
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("title") or message
    raise RuntimeError(message)
