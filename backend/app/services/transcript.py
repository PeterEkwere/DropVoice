from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.pronunciation import PronunciationEntry, apply_pronunciations


EMOTION_TO_CARTESIA_TAG = {
    "neutral": None,
    "happy": "happy",
    "laughing": "happy",
    "calm": "calm",
    "sad": "sad",
    "angry": "angry",
    "whisper": "mysterious",
}

PACE_TO_BASE_SPEED = {"slow": 0.9, "normal": 1.0, "fast": 1.1}

EMOTION_SPEED_MULTIPLIER = {
    "happy": 1.04,
    "laughing": 1.05,
    "sad": 0.92,
    "calm": 0.95,
    "whisper": 0.9,
    "angry": 1.02,
}

EMOTION_VOLUME = {
    "whisper": 0.55,
    "calm": 0.95,
    "angry": 1.05,
    "laughing": 1.02,
}

PACE_TO_BREAK_MS = {"slow": 260, "normal": 150, "fast": 90}

LAUGHTER_HINT = re.compile(r"\b(haha+|hehe+|lol|lmao)[.!?]?", re.IGNORECASE)
SENTENCE_END = re.compile(r"([.!?])(\s+)")
SENTENCE_BOUNDARY = re.compile(r"([.!?])(\s+|$)")
TRAILING_BREAK = re.compile(r"(?:\s*<break time=\"\d+ms\"/>)+\s*$")
WHITESPACE = re.compile(r"\s+")
MISSING_SPACE_AFTER_PUNCT = re.compile(r"([.!?,;:])([A-Za-z])")


@dataclass
class CompiledSegment:
    text: str
    emotion: str
    speed: float
    volume: float


@dataclass
class CompiledTranscript:
    segments: list[CompiledSegment]
    debug_text: str


def normalize_text(text: str) -> str:
    cleaned = WHITESPACE.sub(" ", text.strip())
    cleaned = MISSING_SPACE_AFTER_PUNCT.sub(r"\1 \2", cleaned)
    return cleaned


def _laughter_for(emotion: str, text: str) -> str:
    if emotion == "laughing":
        return SENTENCE_BOUNDARY.sub(r"\1 [laughter]\2", text)
    if emotion == "happy":
        return LAUGHTER_HINT.sub("[laughter]", text)
    return text


def _add_breaks(text: str, pace: str) -> str:
    break_ms = PACE_TO_BREAK_MS.get(pace, 150)
    return SENTENCE_END.sub(rf'\1 <break time="{break_ms}ms"/>\2', text)


def _decorate(text: str, emotion: str, pace: str) -> str:
    body = _laughter_for(emotion, text)
    body = _add_breaks(body, pace)
    body = TRAILING_BREAK.sub("", body)
    tag = EMOTION_TO_CARTESIA_TAG.get(emotion)
    if tag:
        body = f'<emotion value="{tag}"/>{body}'
    return body.strip()


def compile_transcript(
    text: str,
    *,
    emotion_preset: str = "neutral",
    pace: str = "normal",
    pronunciations: list[PronunciationEntry] | None = None,
    pretagged: bool = False,
) -> CompiledTranscript:
    emotion = (emotion_preset or "neutral").lower().strip()
    pace_key = (pace or "normal").lower().strip()
    if pace_key not in PACE_TO_BASE_SPEED:
        pace_key = "normal"

    base_speed = PACE_TO_BASE_SPEED[pace_key]
    speed = round(base_speed * EMOTION_SPEED_MULTIPLIER.get(emotion, 1.0), 3)
    volume = round(EMOTION_VOLUME.get(emotion, 1.0), 3)

    body = normalize_text(text)
    body = apply_pronunciations(body, pronunciations or [])
    if pretagged:
        decorated = _decorate_pretagged(body, emotion)
    else:
        decorated = _decorate(body, emotion, pace_key)

    segment = CompiledSegment(text=decorated, emotion=emotion, speed=speed, volume=volume)
    return CompiledTranscript(segments=[segment], debug_text=decorated)


def _decorate_pretagged(text: str, emotion: str) -> str:
    body = TRAILING_BREAK.sub("", text).strip()
    tag = EMOTION_TO_CARTESIA_TAG.get(emotion)
    if tag:
        body = f'<emotion value="{tag}"/>{body}'
    return body
