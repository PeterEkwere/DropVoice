DropVoice — Project Plan & Build README

Status: Planning. No code written yet. This document is the source of truth for all build decisions made on 2026-05-04. Move this file into /Users/mac/My_bots/dropvoice/ (or whatever folder name you choose) when you start scaffolding.


1. Product Summary
DropVoice is a single-page text-to-speech web app. The user types text (up to 400 chars), picks an emotion preset, optionally uploads a 7–20s voice clone clip, picks a language, and gets back a generated voice note that they can play, download, or share.
It's mobile-first, no navigation, no signup-blocking — fast and instant.
The visual design is a WhatsApp green re-skin of the existing DropVoice prototype (see DropVoice.html and README.md in this folder for the original blue version).

2. Decisions Locked In
DecisionChoiceWhyTTS providerCartesia Sonic-2Best-in-class quality, sub-second latency, instant voice cloning, emotion control via promptsBackend languagePython (FastAPI)Async-first, handles concurrent users at high throughput, official Cartesia SDK support, clean codebaseFrontend stackVanilla HTML/CSS/JS or Next.jsEither works; recommend Next.js if Stripe + auth needed, else vanillaDatabasePostgres (Neon free tier)Single tier, free until we scaleVoice clone storagePass blob directly to Cartesia — never persistPrivacy + zero storage costAuthTBD — see Open QuestionsNeeded if doing multi-user with creditsPaymentsStripe (or Paystack if Nigerian market)Standard, secureDeploymentBackend: Fly.io / Railway. Frontend: VercelCheap, fast, scalesRate limitingHard limit per IP + per userRequired guardrail — see § 7Char limit400 characters (up from 300 in design)Aligns with the per-voice price pointPricing₦4,000 per voice generation (400 chars)~98% gross margin over Cartesia cost

3. TTS Provider: Cartesia Sonic-2
Why Cartesia (over Chatterbox, OpenAI, ElevenLabs):

Quality: Tied with ElevenLabs for top-tier; cleaner than Chatterbox.
Speed: ~40ms time-to-first-audio. Streams audio as it's generated.
Voice cloning: Instant cloning from a 5–20s sample. No model fine-tuning required.
Emotion control: Supported via __[laugh]__, __[sigh]__, etc. inline tags + prompt steering.
Languages: 15+ languages including English, Spanish, French, German, Hindi, Japanese, etc.
Pricing: ~$0.065 per 1,000 characters on pay-as-you-go starter, cheaper on Pro plan.

Cost per generation (400 chars):

~$0.026 USD ≈ ₦40 at current rates.

Pricing model & profit:

Customer pays: ₦4,000 per voice (400 chars).
API cost: ~₦40.
Stripe/Paystack fee: ~1.5–2.9% (~₦60–₦120).
Net margin per voice: ~₦3,800 → ~95% margin.
Break-even: profitable from generation #1.

API integration notes:

Use the official cartesia-python SDK.
Endpoint: client.tts.bytes() (returns audio bytes) or client.tts.sse() (streams).
Voice cloning: client.voices.create(name=..., embedding_data=<file bytes>). Returns a voice_id we can pass to tts.bytes().
For one-shot cloning (no persisted voice), use localize_voice or pass embedding inline.
Output format: mp3 for delivery, optionally wav for higher quality download.


4. Backend Architecture (Python / FastAPI)
Project layout
/Users/mac/My_bots/dropvoice/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI entrypoint
│   │   ├── config.py            # env vars, settings
│   │   ├── routes/
│   │   │   ├── generate.py      # POST /api/generate
│   │   │   ├── balance.py       # GET /api/balance, POST /api/topup
│   │   │   └── webhook.py       # Stripe/Paystack webhook handler
│   │   ├── services/
│   │   │   ├── cartesia.py      # Cartesia client wrapper
│   │   │   ├── pricing.py       # cost calculator + margin logic
│   │   │   └── ratelimit.py     # Redis-backed rate limiter
│   │   ├── db/
│   │   │   ├── models.py        # SQLAlchemy models
│   │   │   └── session.py       # DB session
│   │   └── auth/
│   │       └── ...              # if we add auth
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── frontend/
│   └── DropVoice-green.html     # the WhatsApp-green prototype
└── PROJECT_README.md            # this file
Why FastAPI (not Django, not Flask, not PHP):

Native async — Cartesia calls are I/O-bound; async lets one worker handle hundreds of concurrent generations.
Type hints everywhere — fewer bugs, better DX.
Pydantic validation — request/response schemas validated automatically.
Built-in OpenAPI docs at /docs.
Easy to deploy — single container, runs on Fly.io / Railway / Render for ~$5/mo.

Concurrency model:

Run with uvicorn app.main:app --workers 4 behind a load balancer.
Each worker handles ~100 concurrent connections via asyncio.
Cartesia calls are awaited, not blocking.
Realistic capacity per $5 instance: ~50–100 simultaneous generations.

Why not PHP:

PHP-FPM is process-per-request — much higher memory per concurrent user.
No first-party Cartesia SDK; we'd be hand-rolling HTTP calls.
Async support (Swoole/ReactPHP) is non-standard.
For a real-time-ish API like this, Python wins.


5. API Endpoints
POST /api/generate
Request:
json{
  "text": "Hello world, this is a test.",
  "emotion": "happy",
  "language": "en",
  "voice_clone_blob": "<base64 audio, optional>"
}
Response:
json{
  "audio_url": "https://cdn.dropvoice.app/<id>.mp3",
  "duration_sec": 3.2,
  "size_bytes": 51200,
  "cost_naira": 4000,
  "remaining_balance_naira": 16000
}
Flow:

Auth check (if multi-user) → get user.
Validate text length ≤ 400.
Rate-limit check (per IP + per user).
Balance check — reject if user can't afford.
Map emotion → Cartesia params.
If voice_clone_blob present → create one-shot voice or use embedding.
Call Cartesia tts.bytes() async.
Upload result to S3 / R2 / Cloudflare.
Deduct ₦4,000 from balance, log generation row.
Return audio URL + new balance.

GET /api/balance
Returns current user balance.
POST /api/topup
Creates a Stripe / Paystack checkout session. Redirects user.
POST /api/webhook/stripe (or paystack)
Verifies signature, credits user balance, idempotent.

6. Data Model
sqlCREATE TABLE users (
  id           UUID PRIMARY KEY,
  email        TEXT UNIQUE,
  phone        TEXT,
  balance_kobo BIGINT NOT NULL DEFAULT 0,  -- store in kobo (₦ * 100), avoid float
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE generations (
  id              UUID PRIMARY KEY,
  user_id         UUID REFERENCES users(id),
  text            TEXT NOT NULL,
  char_count      INT NOT NULL,
  emotion         TEXT NOT NULL,
  language        TEXT NOT NULL,
  used_voice_clone BOOLEAN NOT NULL DEFAULT FALSE,
  cartesia_cost_usd_micros BIGINT,  -- what we paid Cartesia
  charged_kobo    BIGINT NOT NULL,  -- what we charged user
  audio_url       TEXT,
  duration_sec    REAL,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE topups (
  id              UUID PRIMARY KEY,
  user_id         UUID REFERENCES users(id),
  amount_kobo     BIGINT NOT NULL,
  provider        TEXT NOT NULL,      -- 'stripe' | 'paystack'
  provider_ref    TEXT UNIQUE,        -- idempotency key
  status          TEXT NOT NULL,      -- 'pending' | 'succeeded' | 'failed'
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_generations_user_created ON generations(user_id, created_at DESC);
Money handling rule: always store amounts as integer kobo (₦ × 100). Never use floats for money.

7. Rate Limiting & Cost Guardrails
This is the single most important thing to get right. Without it, one bad actor can drain Cartesia credits.
Limits (proposed):
ScopeLimitWindowStoragePer IP, unauthenticated3 generations1 hourRedis (Upstash)Per IP, all endpoints60 requests1 minuteRedisPer user (authenticated)30 generations1 hourRedisPer user, daily spend₦100,00024 hoursDBPer text char count400per requestApp-levelVoice clone uploads5 per user24 hoursRedisVoice clone size5 MBper uploadApp-levelVoice clone duration7–20sper uploadApp-level (ffprobe)
Hard kill-switch:
Add a global env-var EMERGENCY_DISABLE=true that returns 503 on /api/generate for everyone. Use this if you ever see a Cartesia bill spike.
Daily budget alarm:
Cron job (or just a check inside /api/generate) that emails / SMS-es you if total Cartesia spend in last 24h exceeds, say, ₦50,000 worth of generations. Cheap insurance.

8. Voice Clone Handling

Accepted formats: audio/mpeg, audio/wav, audio/mp4, audio/webm, video/mp4 (we'll extract audio).
Min duration: 7s. Max: 20s.
Max file size: 5 MB.
Never persist — pass directly from request → Cartesia → discard.
If Cartesia requires a voice ID (not an inline embedding), create a temporary voice and delete it after generation completes.
Validate file is actually audio (use python-magic to sniff MIME, then ffprobe to confirm playable).


9. Frontend: WhatsApp Green Re-skin
The existing DropVoice.html design stays — just swap the color tokens.
New token map:
TokenOld (blue)New (WhatsApp green)--ac (primary)oklch(58% 0.22 235)#25D366--ac2 (gradient end)oklch(60% 0.22 255)#128C7E--acl (light accent)oklch(97% 0.05 290)#DCF8C6Add Funds buttonred gradient#128C7E → #075E54Generate button glowblue shadow0 8px 28px rgba(37,211,102,0.38)Output player tintblue 7%rgba(37,211,102,0.07)Output player borderblue 18%rgba(37,211,102,0.18)
Optional WhatsApp-flavored touches (decide before frontend build):

Output player styled like a WhatsApp voice-note bubble (rounded pill + tail).
"Generating…" replaced with three pulsing dots (typing indicator).
Textarea with one less-rounded corner (chat-bubble feel).

Char counter update:
Change max from 300 → 400 to match pricing tier.

10. Emotion → Cartesia Parameter Map
The original design used Chatterbox's exaggeration / cfg_weight / temperature. Cartesia uses a different model — it accepts inline emotion tags plus speed/voice-mix params.
EmotionCartesia approachNeutralDefault voice, no tagsHappy__[laugh]__ tag option, slightly faster speed (1.05)CalmSpeed 0.95, lower energy voiceExcitedSpeed 1.1, exclamation-heavy prompt steeringSad__[sigh]__ tag, speed 0.9AngrySpeed 1.05, sharper voice variantDramaticPauses (...), variable pacingWhisperUse Cartesia's whisper voice variant
We'll finalize exact params during build by A/B-listening to a few samples per emotion.

11. Deployment & Env
.env shape:
CARTESIA_API_KEY=...
DATABASE_URL=postgres://...
REDIS_URL=...
STRIPE_SECRET_KEY=...        # or PAYSTACK_SECRET_KEY
STRIPE_WEBHOOK_SECRET=...
STORAGE_BUCKET=dropvoice-audio
STORAGE_ACCESS_KEY=...
STORAGE_SECRET_KEY=...
EMERGENCY_DISABLE=false
DAILY_BUDGET_NAIRA=50000
ENVIRONMENT=production
Hosting:

Backend: Fly.io ($5/mo for 1 instance, scales) or Railway ($5/mo).
Database: Neon free tier (3GB), upgrade to $19/mo when needed.
Redis: Upstash free tier (10k commands/day).
Audio CDN: Cloudflare R2 ($0.015/GB stored, free egress).
Frontend: Vercel free tier.

Total monthly cost at low usage: ~$5–$10. Pure Cartesia pass-through after that.

12. Build Sequence (when we start)

Scaffold backend/ — FastAPI + Postgres + Redis + Cartesia client. Stub /api/generate returning a fake URL.
Wire Cartesia: real generations end-to-end without auth or balance.
Add rate limiting (Redis).
Add database, users table, balance tracking, generation logs.
Build the WhatsApp-green frontend (re-skin of DropVoice.html).
Connect frontend → backend.
Add Stripe / Paystack top-ups + webhook.
Add auth (magic link or phone OTP).
Add voice clone upload path.
Production hardening: monitoring, alerts, kill-switch test.


13. Open Questions (decide before we start coding)

Auth model: magic link email, phone OTP, social login, or no auth (single-user / API key only)?
Payment provider: Stripe (international) or Paystack (Nigeria-first)? Or both?
Currency: confirm ₦4,000 NGN. If targeting global, do we have USD pricing too?
Free tier: does a new user get any free generations as a try-it? (Recommend: 1 free, then must top up.)
Frontend stack: vanilla HTML (matches design exactly, less work) or Next.js (better if we add accounts UI)?
Domain: do you have one yet? (e.g. dropvoice.app, dropvoice.ng)
Voice library: do we offer a few preset voices in addition to user clones? Cartesia has a public voice library — pick maybe 6–8 favorites.
Output format: mp3 only or also offer wav download?
Sharing: Web Share API (mobile-friendly) or just download? Both is fine.
Analytics: plain Postgres aggregation, or add PostHog / Plausible?