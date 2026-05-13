from __future__ import annotations

import re

import httpx

from app.config import get_settings


SYSTEM_PROMPT = """You are a TTS preprocessor for a voice-note app. Output ONLY the rewritten text on a single line — no commentary, no quotes, no markdown, no <emotion> tag.

Two jobs:

A) Fix obvious typos, missing apostrophes, missing periods between sentences, and run-on punctuation. Do NOT change meaning, language, or word choice. Examples:
   "dont" → "don't"
   "its dangerous" (when possessive context says otherwise — "it is" → "it's"). Use judgement.
   "hello.how are you" → "Hello. How are you?"
   "i am" → "I am"

B) Insert performance tags ONLY where they fit the meaning:
   - [laughter] — for genuinely amused, joyful, or funny beats. Place it AFTER the punchline or amused remark, before a period. Do NOT use it on commands, factual questions, somber statements, sad content, or neutral information.
   - [sigh] — for tired, relieved, or resigned beats. Use sparingly.
   - <break time="150ms"/> — short natural pause where a real speaker would breathe.
   - <break time="300ms"/> — longer pause before a punchline or dramatic moment.

Emotion-specific behavior:
- "laughing": be willing to insert [laughter] on amused/positive sentences. Skip [laughter] on any sad, serious, factual, command, or question content even though emotion is laughing.
- "happy": insert [laughter] only on clearly funny content or where the user wrote "haha"/"lol".
- "sad" / "calm" / "whisper" / "neutral" / "angry": do NOT insert [laughter] or [sigh]. Breaks are allowed.

Examples:

Input  | Emotion: laughing | Pace: normal | Text: That joke was hilarious. I cannot believe he said that.
Output | That joke was hilarious [laughter]. I can't believe he said that [laughter].

Input  | Emotion: laughing | Pace: normal | Text: My grandmother died last week. The funeral is tomorrow.
Output | My grandmother died last week. The funeral is tomorrow.

Input  | Emotion: angry | Pace: fast | Text: please dont touch that.its dangerous
Output | Please don't touch that. It's dangerous.

Input  | Emotion: happy | Pace: normal | Text: hi welcome to dropvoice. type any message and we make it speech.
Output | Hi, welcome to DropVoice. Type any message and we'll turn it into speech.

Input  | Emotion: laughing | Pace: normal | Text: he tripped on the cat haha
Output | He tripped on the cat [laughter].

Now process the next request."""


def _user_prompt(text: str, emotion: str, pace: str) -> str:
    return f"Emotion: {emotion}\nPace: {pace}\nText: {text}"


def _strip_wrappers(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned)
    cleaned = cleaned.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1].strip()
    cleaned = re.sub(r"<emotion[^/]*/>", "", cleaned)
    return cleaned.strip()


async def rewrite_with_groq(text: str, emotion: str, pace: str) -> str | None:
    settings = get_settings()
    if settings.transcript_rewriter.lower() != "groq" or not settings.groq_api_key:
        return None

    payload = {
        "model": settings.groq_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(text, emotion, pace)},
        ],
        "temperature": 0.3,
        "max_tokens": 600,
    }
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(base_url=settings.groq_base_url, timeout=15.0) as client:
            response = await client.post("/chat/completions", json=payload, headers=headers)
            if response.status_code >= 400:
                return None
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    try:
        rewritten = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    if not isinstance(rewritten, str):
        return None
    cleaned = _strip_wrappers(rewritten)
    if not cleaned:
        return None
    return cleaned
