# DropVoice

DropVoice turns text into natural, expressive voice notes. You type a message, pick an emotion and a speaking pace, optionally upload a short clip to clone a voice, and you get back a voice note you can play, download or share. It is mobile first and there is no signup wall.

Backend is Python and FastAPI. Speech is from Cartesia, text cleanup is from a Groq model, and the audio work is done with FFmpeg.

## Why it is more than a plain TTS call

Getting a voice note that actually sounds good takes a few steps beyond calling a TTS API:

1. **Text cleanup with an LLM.** Before anything is spoken, a Groq model fixes typos, punctuation and casing, and adds performance cues like `[laughter]`, `[sigh]` and short pauses. It has rules so it will not add laughter to sad, serious or factual text even if you picked the laughing emotion.
2. **A real audio pipeline.** Voice clone uploads get their silence trimmed from both ends, loudness normalised (EBU R128), converted to 44.1 kHz mono and checked for length. Long text is spoken in parts and then joined into one MP3. If FFmpeg is missing or a step fails, it falls back instead of breaking.
3. **Pronunciation control.** A global dictionary plus per request terms fix how names and odd words are said, with proper word boundary and capitalisation handling.

## What it does

- Text to speech with Cartesia, with emotion and pace per request.
- Instant voice cloning from a short clip. The clone is made for one job and deleted from the provider right after, so voices are not kept.
- A generation queue that limits how many run at once, and runs the text cleanup and clone cleanup at the same time.
- A wallet in kobo with a transaction ledger that cannot go negative, and an automatic refund when a generation fails.
- OPay checkout for topping up the wallet, with callbacks, plus a mock mode.
- Generated audio and clones expire and get cleaned up, and the clone source is never stored.
- Mock modes for TTS and payments so you can run the whole thing offline.
- Per device tokens, admin routes and a small admin CLI.

## How it fits together

```
Client
  |  POST /generations            POST /topups/initiate
  v                                   |
FastAPI  --> wallet debit (kobo) <----+
  |
  v
Generation queue (async, limited)
  |-- Groq        text cleanup and cues
  |-- Cartesia    optional clone, then synthesize
  |-- FFmpeg      trim silence, loudnorm, join parts
  |-- Storage     expiring audio -> result
          |
   on failure --> wallet refund
```

| Part | Where |
|------|-------|
| API routes | `app/routes/` (generations, wallet, topups, device, admin, health) |
| Services | `app/services/` (queue, cartesia, transcript_llm, audio_clean, pronunciation, wallets, opay, storage, transcript) |
| Data | `app/models/entities.py`, `app/db/session.py` (SQLAlchemy async) |
| Config | `app/config.py` |

## Stack

Python 3.11, FastAPI, SQLAlchemy (async, Postgres or SQLite), httpx, Cartesia TTS, Groq, FFmpeg and ffprobe, OPay, Uvicorn.

## Running it

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # fill in your own values
uvicorn app.main:app --reload
```

You need FFmpeg and ffprobe on your PATH for the audio steps. Without them it still runs and just skips the processing.

### Config

Copy `.env.example` to `.env` and set your values. The groups are:

| Group | Keys |
|-------|------|
| Core | `DATABASE_URL`, `CORS_ORIGINS`, `DEVICE_TOKEN_SECRET` |
| Cartesia | `CARTESIA_API_KEY`, `CARTESIA_MODEL_ID`, `CARTESIA_DEFAULT_VOICE_ID`, `CARTESIA_CONCURRENCY_LIMIT`, `MOCK_TTS` |
| Groq | `GROQ_API_KEY`, `GROQ_MODEL`, `TRANSCRIPT_REWRITER` |
| OPay | `OPAY_MERCHANT_ID`, `OPAY_PUBLIC_KEY`, `OPAY_PRIVATE_KEY`, `OPAY_*_URL`, `MOCK_PAYMENTS` |
| Limits | `PRICE_PER_GENERATION_KOBO`, `CHAR_LIMIT`, `CLONE_*_DURATION_SECONDS`, `MAX_CLONE_UPLOAD_BYTES`, `AUDIO_TTL_MINUTES` |

Do not commit a real `.env`. Keep keys out of git, and rotate any key that was ever committed.

## Status

The whole flow works end to end: text to speech, voice cloning, wallet billing and payments. Next on the list is a hosted frontend, more languages, and tests around the queue and wallet.

## License

See [`LICENSE`](LICENSE).

