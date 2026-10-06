# DropVoice

**An asynchronous AI voice-generation service that turns text into expressive, natural speech — with optional instant voice cloning, pay-as-you-go wallet billing, and a production-grade audio pipeline.**

DropVoice is a mobile-first web app and FastAPI backend. A user types a message, picks an emotion and pace, optionally uploads a short clip to clone a voice, and gets back a polished voice note to play, download or share.

Built with Python · FastAPI · Groq LLM · Cartesia TTS · FFmpeg · OPay.

---

## What makes it more than a TTS wrapper

Turning raw text into a *convincing* voice note takes more than one API call. DropVoice adds three layers around the speech engine:

1. **LLM text shaping.** Before any audio is generated, a Groq LLM cleans up the text — fixing typos, punctuation and casing — and inserts emotion-aware performance cues (`[laughter]`, `[sigh]`, timed `<break>` pauses). It follows strict rules: no laughter on sad, factual or command text, even when the chosen emotion is "laughing."
2. **A real audio pipeline (FFmpeg).** Uploaded voice-clone clips are trimmed of leading/trailing silence, loudness-normalised to broadcast level (EBU R128, `loudnorm`), converted to 44.1 kHz mono and validated for length. Long generations are synthesised in segments and stitched into a single MP3. Every FFmpeg step degrades gracefully if the binary is missing or a call fails.
3. **Pronunciation control.** A global dictionary plus per-request terms correct how names and jargon are spoken, with careful word-boundary and capitalisation handling.

## Features

- **Expressive TTS** via Cartesia, with per-request emotion and speaking pace.
- **Instant voice cloning** from a short uploaded clip — the clone is created for a single job and **deleted from the provider immediately after**, so voices are never retained.
- **Concurrency-limited generation queue** that matches the TTS provider's limits, runs the LLM rewrite and clone cleanup in parallel, and wakes on demand.
- **Wallet billing in kobo** backed by an immutable transaction ledger that can never go negative, with **automatic refunds when a generation fails**.
- **OPay checkout** for wallet top-ups, with provider callbacks and a mock mode.
- **Privacy by design:** generated audio and cloned voices expire and are cleaned up automatically; clone source audio is never persisted.
- **Offline/dev mode:** `MOCK_TTS` and `MOCK_PAYMENTS` let the whole system run without external accounts.
- Per-device token auth, admin routes and an admin CLI for operations.

## Architecture

```
Client (SPA)
   │  POST /generations            POST /topups/initiate
   ▼                                   │
FastAPI app ──► wallet (debit, kobo) ──┘
   │
   ▼
Generation queue (async, concurrency-limited)
   ├─ Groq LLM  ── text cleanup + performance cues
   ├─ Cartesia  ── (optional) clone voice  →  synthesize segments
   ├─ FFmpeg    ── silence trim · loudnorm · segment stitch
   └─ Storage   ── expiring audio  →  result
                         │
                 failure ─► automatic wallet refund
```

| Layer | Files |
|---|---|
| API routes | `app/routes/` — `generations`, `wallet`, `topups`, `device`, `admin`, `health` |
| Services | `app/services/` — `queue`, `cartesia`, `transcript_llm`, `audio_clean`, `pronunciation`, `wallets`, `opay`, `storage`, `transcript` |
| Data | `app/models/entities.py`, `app/db/session.py` (SQLAlchemy, async) |
| Config | `app/config.py` (env-driven settings) |

## Tech stack

Python 3.11 · FastAPI · SQLAlchemy (async, Postgres/SQLite) · httpx · Cartesia Sonic TTS · Groq LLM API · FFmpeg/ffprobe · OPay · Uvicorn.

## Getting started

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in the values below
uvicorn app.main:app --reload
```

FFmpeg and ffprobe must be on the PATH for the audio pipeline (silence trimming, loudness normalisation and stitching). Without them the service still runs, falling back to unprocessed audio.

### Configuration

Copy `.env.example` to `.env` and set your own values. Key groups:

| Group | Variables |
|---|---|
| Core | `DATABASE_URL`, `CORS_ORIGINS`, `DEVICE_TOKEN_SECRET` |
| TTS (Cartesia) | `CARTESIA_API_KEY`, `CARTESIA_MODEL_ID`, `CARTESIA_DEFAULT_VOICE_ID`, `CARTESIA_CONCURRENCY_LIMIT`, `MOCK_TTS` |
| LLM (Groq) | `GROQ_API_KEY`, `GROQ_MODEL`, `TRANSCRIPT_REWRITER` |
| Payments (OPay) | `OPAY_MERCHANT_ID`, `OPAY_PUBLIC_KEY`, `OPAY_PRIVATE_KEY`, `OPAY_*_URL`, `MOCK_PAYMENTS` |
| Product limits | `PRICE_PER_GENERATION_KOBO`, `CHAR_LIMIT`, `CLONE_*_DURATION_SECONDS`, `MAX_CLONE_UPLOAD_BYTES`, `AUDIO_TTL_MINUTES` |

> **Security:** never commit a real `.env`. Keep secrets out of version control and rotate any key that has ever been committed.

## Status & roadmap

DropVoice is a working end-to-end prototype: text-to-speech, voice cloning, wallet billing and payments all function. Planned next steps include a hosted frontend, broader language coverage and automated tests around the queue and wallet ledger.

## License

See [`LICENSE`](LICENSE).
