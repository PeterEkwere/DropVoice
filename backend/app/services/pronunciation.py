from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PronunciationEntry:
    term: str
    replacement: str


def parse_terms_string(raw: str | None) -> list[PronunciationEntry]:
    if not raw:
        return []
    entries: list[PronunciationEntry] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk or "=" not in chunk:
            continue
        term, replacement = chunk.split("=", 1)
        term = term.strip()
        replacement = replacement.strip()
        if not term or not replacement:
            continue
        entries.append(PronunciationEntry(term=term, replacement=replacement))
    return entries


def load_global_dictionary(path: Path) -> list[PronunciationEntry]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    raw_entries = payload.get("entries") if isinstance(payload, dict) else payload
    if not isinstance(raw_entries, list):
        return []
    out: list[PronunciationEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term", "")).strip()
        replacement = str(item.get("replacement") or item.get("pronunciation") or "").strip()
        if not term or not replacement:
            continue
        out.append(PronunciationEntry(term=term, replacement=replacement))
    return out


def merge_dictionaries(*sources: list[PronunciationEntry]) -> list[PronunciationEntry]:
    seen: dict[str, PronunciationEntry] = {}
    for source in sources:
        for entry in source:
            seen[entry.term] = entry
    merged = list(seen.values())
    merged.sort(key=lambda e: len(e.term), reverse=True)
    return merged


def apply_pronunciations(text: str, entries: list[PronunciationEntry]) -> str:
    if not entries or not text:
        return text
    result = text
    for entry in entries:
        result = _replace_with_cartesia_rules(result, entry.term, entry.replacement)
    return result


def _replace_with_cartesia_rules(text: str, term: str, replacement: str) -> str:
    if term.islower():
        pattern = re.compile(rf"\b{re.escape(term)}\b")
        text = pattern.sub(replacement, text)
        cap_term = term[0].upper() + term[1:]
        cap_replacement = replacement[0].upper() + replacement[1:] if replacement else replacement
        cap_pattern = re.compile(rf"(?<=[.!?]\s){re.escape(cap_term)}\b|^{re.escape(cap_term)}\b")
        text = cap_pattern.sub(cap_replacement, text)
        return text
    pattern = re.compile(rf"\b{re.escape(term)}\b")
    return pattern.sub(replacement, text)
