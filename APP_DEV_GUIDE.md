# DropVoice — Mobile App Implementation Guide

> **Audience:** the engineer (or coding agent) building the iOS / Android client.
> **Backend version:** `2026-05-06`
> **Last verified end-to-end:** 2026-05-06.

This document is the single source of truth for what the mobile app must do, in what order, with what timing, and what UI to show in each state. Build to this guide and the result will match the existing web preview in `frontend/index.html` and behave identically against the live backend.

---

## 1. Build the same UI as the web preview

There is a working reference at `frontend/index.html`. Open it in a browser pointed at the dev backend (`?api=http://127.0.0.1:8000/v1`) and use it as the visual + behavioral source of truth. The mobile app is a **single-screen application** — there is no navigation, no tabs, no back button.

### 1.1 Color tokens (WhatsApp green)

| Token | Value | Used for |
|---|---|---|
| `--ac` | `#25D366` | primary accent (button, focus, active chip) |
| `--ac2` | `#128C7E` | gradient end on logo, generate button |
| `--funds1` | `#128C7E` | Add Funds gradient start |
| `--funds2` | `#075E54` | Add Funds gradient end |
| `--acl` | `#DCF8C6` | active chip background, selected language row |
| `--bg` | `#FFFFFF` | page background |
| `--sf` | `#F7F7F8` | status banner / soft surface |
| `--bd` | `#EBEBEB` | borders |
| `--tx` | `#0A0A0F` | primary text |
| `--mu` | `#999` | muted text |
| `--danger` | `#F87171` | error text + over-limit char counter |

Font: **Poppins**, weights 300–900.

### 1.2 Layout (top to bottom)

1. **Sticky header**
   - Left: 34×34 rounded gradient tile with the white mic icon, then "DropVoice" wordmark (weight 800).
   - Right: balance label (`₦12,400`) + green "Add Funds" pill button with `+` icon.
2. **Status banner** (small grey card)
   - Title: "Local Preview" (or "Connected" in production).
   - Subtitle: short connection state. Hidden once everything is healthy if you prefer.
3. **Error banner** (red, only when there is an error). Sits between status and the textarea.
4. **Textarea**
   - Light green tint (`#F0FDF4`), 2px border `#EBEBEB` → `var(--ac)` on focus.
   - Border radius `20px 20px 20px 6px` (the bottom-left corner is the chat-bubble tail).
   - Min height ~128px.
   - Placeholder: "Type what you want to say…".
   - Live char counter bottom-right `n/400`. Counter goes red at >85% of limit. Limit comes from the bootstrap response (`char_limit`), do not hardcode.
5. **Emotion chip row** (horizontally scrollable, no scrollbar)
   - Order, in order: **Neutral · Happy · Laughing · Calm · Sad · Angry · Whisper**.
   - Active chip uses `--acl` background and `--ac` text/border. Inactive uses white background and `#666` text.
6. **Pace chip row** (3 equal-width chips, not scrollable)
   - **Slow · Normal · Fast**. Same active styling as emotion.
7. **Pronunciation hints** (single text input)
   - Label: "Pronunciation hints (optional)".
   - Placeholder: `LaTeX=lay tek, GitHub=git hub`.
   - Helper line below: `Format: term=spelling, term=spelling. Use exact case for proper nouns.`
8. **Language + Custom Voice row** (flex row)
   - Left: square language picker (flag + label, 78px min width). Tapping opens a popover/sheet with the full supported-language list.
   - Right: large dashed-border drop zone for the custom voice file upload. When empty: plus icon + "Custom Voice" + "Upload 5–20s audio sample". When a file is attached: speaker icon + filename + size + small × button to clear.
9. **Generate button**
   - 76×76 circular gradient (`--ac` → `--ac2`).
   - When idle and `text.length > 0`: pulsing rings animation behind the button.
   - When generating: spinner inside, no pulse, label "Generating" + 3 bouncing dots.
   - When disabled (no text): grey, scaled to 95%, mic icon only.
10. **Output player** (only when there is an audio result)
    - Light green gradient card with a chat-bubble tail.
    - Round play/pause button on the left, animated vertical "wave bars" in the middle, duration + size on the right.
    - Below: two equal buttons — **Download** (filled gradient) and **Share** (outlined).
    - Tiny grey "Clear saved audio" link beneath, which calls the delete-audio endpoint.

### 1.3 Add Funds bottom sheet

Triggered by the header pill. Slides up from the bottom, backdrop blur.

- Drag handle pill at the top.
- Title "Add Credits" + small balance line.
- Preset chips: ₦4,000 · ₦8,000 · ₦12,000 · ₦20,000 · ₦40,000 (these are naira; convert to kobo before sending — multiply by 100).
- Custom amount input with ₦ prefix.
- Approx-voice-notes hint card: `~{floor(amount/4000)} voice notes`.
- Big primary button: "Pay ₦{amount}" (gradient `--funds1` → `--funds2`). While the request is in flight: "Processing…" and disabled. If amount is invalid: "Enter valid amount" disabled.

---

## 2. Backend base URL & auth

| Environment | Base URL |
|---|---|
| Local dev | `http://127.0.0.1:8000/v1` |
| Staging / prod | `https://151.80.190.160/v1` |

Do not use the HTTP staging URL in the app. Port 80 redirects to HTTPS, and native HTTP clients may surface that redirect as `Request failed (301)` or another 3xx transport error instead of following it for multipart POSTs.

All `/v1/*` endpoints (except `/v1/device/bootstrap`) require:

```
Authorization: Bearer <device_token>
```

The token is opaque, persistent, and tied to one `installation_id`. Store it in the OS keychain (iOS Keychain / Android Keystore). It does not expire on its own.

### 2.1 First-launch flow

1. On first launch, generate a UUID v4 and persist it as `installation_id` in secure storage. Reuse it forever; do not regenerate on update.
2. POST `/v1/device/bootstrap` with that ID.
3. Store the returned `device_token` in secure storage.
4. Use the bootstrap response to populate the header balance, the language picker, and the char limit.

If the token is ever rejected (`401` from any authenticated endpoint), repeat steps 2–3 silently and retry the failed call once.

---

## 3. The ten endpoints

All paths are relative to the `/v1` base. All money is in **kobo** (1 NGN = 100 kobo). Never use floats for money.

### 3.1 `POST /device/bootstrap` — first-touch handshake

**No auth required.**

```jsonc
// request
{
  "installation_id": "0b8f3c5e-2d2f-4f9b-9b35-7b01a2cc8e91",
  "platform": "ios",                 // "ios" | "android" | "browser" | anything
  "app_version": "1.0.3"             // optional, ≤ 32 chars
}
```

```jsonc
// 200 response
{
  "device_token": "eyJ...",                        // opaque, store in keychain
  "balance_kobo": 800000,
  "currency": "NGN",
  "default_language": "en",
  "supported_languages": [
    { "code": "en", "label": "English" },
    { "code": "ar", "label": "Arabic" },
    { "code": "zh", "label": "Chinese" },
    { "code": "hi", "label": "Hindi" },
    ...
  ],
  "price_per_generation_kobo": 400000,
  "char_limit": 400,
  "default_voice_label": "Default English"
}
```

**UI binding:**
- `balance_kobo / 100` → header balance label.
- `supported_languages` → language picker rows (use a flag map locally).
- `char_limit` → textarea max & counter.
- `price_per_generation_kobo` → "Each generation costs ₦{n} for up to {char_limit} characters." copy in the funds sheet.

**Failures:** 422 if the body is malformed. Show a generic error and offer retry.

**Timing:** typically < 200ms.

---

### 3.2 `GET /wallet` — current balance + recent transactions

Auth required.

```jsonc
// 200 response
{
  "wallet_id": "fb1...",
  "balance_kobo": 800000,
  "currency": "NGN",
  "transactions": [
    {
      "id": "...",
      "kind": "credit" | "debit" | "refund",
      "amount_kobo": 400000,
      "balance_after_kobo": 400000,
      "reference": "topup:dv-topup-abc",
      "created_at": "2026-05-06T17:05:33.104803Z"
    }
  ]
}
```

**Use cases on the app:**
- Refresh balance after a top-up succeeds.
- Pull-to-refresh on the home screen (optional).
- "Recent activity" if you choose to add a small history sheet later.

**Failures:** 401 if token bad → re-bootstrap.

---

### 3.3 `POST /topups/initiate` — open the OPay cashier

Auth required.

```jsonc
// request
{
  "amount_kobo": 800000,             // required, > 0
  "return_url": "dropvoice://payments/return",
  "cancel_url": "dropvoice://payments/cancel",
  "pay_method": null,                // null lets OPay choose; or "Card" / "BankTransfer" / "BankAccount"
  "customer_name": "Peter E.",       // optional
  "customer_email": "peter@example.com",  // optional
  "customer_phone": "+2348012345678"      // optional
}
```

```jsonc
// 200 response — real OPay
{
  "reference": "dv-topup-c297931b92fc4bac91",
  "status": "pending",
  "amount_kobo": 800000,
  "cashier_url": "https://testapi.opaycheckout.com/cashier/short/code123",
  "created_at": "2026-05-06T17:05:33.104803Z"
}

// 200 response — when MOCK_PAYMENTS=true on the backend
{
  "reference": "dv-topup-...",
  "status": "succeeded",             // wallet is already credited
  "amount_kobo": 800000,
  "cashier_url": null,
  "created_at": "..."
}
```

**App flow:**

1. User taps a preset or types a custom amount, taps "Pay ₦…".
2. Send the request. Disable the button, show "Processing…".
3. **If `cashier_url` is present:** open it in an in-app browser (SFSafariViewController on iOS, Custom Tabs on Android). This is the OPay sandbox/production cashier — the user enters card / bank / USSD on OPay's page, not yours.
4. Register your URL scheme (e.g. `dropvoice://payments/return`) in `Info.plist` / `AndroidManifest.xml`. When OPay finishes, it redirects to that scheme. The OS opens the app back up.
5. On `dropvoice://payments/return`, dismiss the in-app browser, **start polling** `GET /topups/{reference}` every 2.5s until status is `succeeded`, `failed`, or `expired` (max 60s). The webhook on the backend usually updates state within a second or two of the user paying.
6. **If `status === "succeeded"` already** (mock or instant), skip the browser entirely, just refresh the wallet and show a toast "Wallet credited."

**OPay status values you might see:**

| Backend status | Meaning | UI |
|---|---|---|
| `pending` | user hasn't completed payment yet | keep polling |
| `succeeded` | money is in the wallet | toast + close sheet + refresh `/wallet` |
| `failed` | OPay declined (card, network) | red toast "Payment failed", let user retry |
| `expired` | user took >30 min | grey toast "Payment expired" |

**Failures from `/topups/initiate`:**

| Status | Body | Meaning |
|---|---|---|
| 422 | validation detail | amount missing or ≤ 0 |
| 503 | `OPay is not configured.` | backend env not set; show an admin-only message |
| 500 | `Cartesia request failed (...)` style | unusual, retry once |

---

### 3.4 `GET /topups/{reference}` — poll a top-up

Auth required.

Returns the same shape as `/topups/initiate`. Use this every 2.5 seconds while the in-app browser is open or until status leaves `pending`. Stop when status is one of `succeeded` / `failed` / `expired`, or after 60 seconds (then surface a "Couldn't confirm payment — pull to refresh" message).

`GET /topups/{reference}` triggers a server-side query to OPay if the topup is still pending, so the app can rely on it as the source of truth.

---

### 3.5 `POST /generations` — submit a generation (the main one)

Auth required. **`Content-Type: multipart/form-data`** (NOT JSON — the optional voice clone needs to ride along).

| Field | Type | Required | Notes |
|---|---|---|---|
| `text` | string | yes | trimmed; ≤ `char_limit` from bootstrap |
| `emotion` | string | yes | one of `neutral`, `happy`, `laughing`, `calm`, `sad`, `angry`, `whisper` |
| `pace` | string | yes | one of `slow`, `normal`, `fast` |
| `language` | string | yes | a code from `supported_languages` |
| `important_terms` | string | no | comma-separated `term=spelling, term=spelling` (see § 4.3) |
| `voice_clone` | file | no | 5–20s audio clip, ≤ 5MB, `audio/*` MIME |

```jsonc
// 200 response — generation accepted and queued
{
  "id": "c75415cc-df6a-4406-aa45-a45ee2f13a5b",
  "status": "queued",
  "charged_kobo": 400000,
  "balance_kobo": 400000,            // post-charge balance
  "audio_download_url": null,
  "audio_clear_url": null,
  "expires_at": null
}
```

The backend has already **debited** the wallet at this point. The actual TTS happens in a background worker — you must poll `GET /generations/{id}` until it's done.

**Failure cases on POST:**

| Status | Body | UI |
|---|---|---|
| 400 | `Text is required.` | inline red banner |
| 400 | `Text exceeds 400 characters.` | inline; counter is already red |
| 400 | `Unsupported language.` | should never happen if you used `supported_languages` |
| 400 | `Invalid pace value.` | should never happen if you used `slow/normal/fast` |
| 400 | `Only audio voice clone uploads are supported in v1.` | the file MIME wasn't `audio/*` |
| 400 | `Voice clone upload is too large.` | reject in-app at 5MB before upload |
| 401 | unauthorized | re-bootstrap, retry once |
| 402 | `Insufficient wallet balance.` | open Add Funds sheet automatically |
| 503 | misc | "Service unavailable, try again" |

**Timing on POST:** ~50–500ms. The work happens after.

---

### 3.6 `GET /generations/{id}` — poll until ready

Auth required. Poll every 1.5s.

```jsonc
// 200 response — terminal: completed
{
  "id": "c754...",
  "status": "completed",
  "charged_kobo": 400000,
  "language": "en",
  "emotion": "happy",
  "pace": "fast",
  "error_message": null,
  "audio_download_url": "/v1/generations/c754.../audio",
  "audio_clear_url": "/v1/generations/c754.../audio",
  "expires_at": "2026-05-06T18:05:41.666039Z"
}

// 200 response — still working
{ "id": "...", "status": "queued"|"processing", ... }

// 200 response — terminal: failed
{
  "id": "...",
  "status": "failed",
  "error_message": "Clone clip is too short after trimming silence (need ≥ 5s).",
  ...
}
```

**State machine for the Generate button:**

| Job status | UI |
|---|---|
| `queued` | spinner + "Queued…" (only really seen for ≤ 1s) |
| `processing` | spinner + "Generating" + bouncing dots |
| `completed` | render the output player using `audio_download_url` |
| `failed` | inline red error using `error_message`, button returns to idle. If the failure was due to a broken clone, the wallet is **automatically refunded** server-side — you don't need to do anything. Just call `/wallet` to refresh. |

**Total expected wall-clock from POST → completed:**

| Path | p50 | p95 |
|---|---|---|
| Default voice, ≤ 80 chars | ~1.5s | ~3s |
| Default voice, 200–400 chars | ~2.5s | ~5s |
| Custom-voice clone, ≤ 80 chars | ~3s | ~4.5s |
| Custom-voice clone, 200–400 chars | ~4s | ~7s |

The backend runs the LLM rewriter (Groq Llama 3.1 8B Instant) in parallel with ffmpeg cleanup of the clone, then calls Cartesia. The user doesn't see any of those substeps — just the final completed status.

---

### 3.7 `GET /generations/{id}/audio` — download the audio bytes

Auth required. Returns the audio as a binary stream with `Content-Type: audio/mpeg` (or `audio/wav` in mock mode).

**Two ways to play it:**

1. Stream the URL directly into your audio player by adding the `Authorization: Bearer ...` header to the player's request. iOS `AVPlayer` and Android `ExoPlayer` both support custom headers.
2. Or: download to a `Data` buffer, write to a temp file, hand the temp path to the player. This is what the web preview does (creates a Blob URL).

**Failures:**

| Status | Meaning |
|---|---|
| 404 | audio is gone (cleared by user or expired). Hide the player. |
| 410 | expired during your read; same UX as 404. |

Audio is automatically purged from the server on expiry (`expires_at`, 60 minutes after completion). After that, only the metadata row remains.

---

### 3.8 `DELETE /generations/{id}/audio` — clear the saved file early

Auth required. Returns 204 no content.

Wire this to the small grey "Clear saved audio" link below the player. It frees server disk and is purely a privacy/control feature for the user. After calling it, hide the player.

---

### 3.9 `GET /health` — liveness check (optional)

No auth required. Returns `{ "status": "ok" }`. Use this on first launch as a "is the backend reachable" probe before bootstrap, if you want to show a polished offline state.

---

### 3.10 `POST /topups/opay/webhook` — server-only

You will not call this from the app. It is the URL you give to OPay so payment confirmations push back into the backend. Documented here only so you understand why polling `/topups/{ref}` works without you doing anything special.

---

## 4. App-side behavior rules

### 4.1 Charge happens before audio. Refunds happen on failure.

- POST `/generations` returns 200 → wallet has **already** been debited. The new `balance_kobo` is in the response.
- If polling later returns `status: "failed"`, the backend has **already refunded** the wallet. Refresh `/wallet` to update the header balance.
- Insufficient balance returns **402** before any debit happens — show the Add Funds sheet.

### 4.2 The seven emotions, with semantics

| Chip | What it does |
|---|---|
| Neutral | Plain voice, no inline tags. |
| Happy | Slightly faster, cheerful tone. The LLM may insert `[laughter]` only if the user wrote `haha`/`lol`. |
| Laughing | Cheerful tone PLUS the LLM proactively places `[laughter]` after amused/funny sentences. It will NOT laugh on sad/factual/command sentences even when this preset is on. |
| Calm | Slightly slower, lower energy. |
| Sad | Slower, somber. |
| Angry | Slightly faster, sharper. |
| Whisper | Much quieter, slower, intimate. |

### 4.3 Pronunciation hints format

User types `LaTeX=lay tek, GitHub=git hub` in the text field. Backend rules (already implemented):

- Pairs are comma-separated.
- Inside each pair: `term` and `replacement` are separated by `=`.
- `LaTeX` (mixed-case) only matches `LaTeX` exactly. Use this for proper nouns.
- `cat` (all-lowercase) matches `cat` AND `Cat` at sentence start. Use this for common words.
- Unknown / malformed pairs are silently ignored.

The mobile app can keep this as a single-line text input (matches the web preview). No need for a fancy chip editor.

### 4.4 Voice clone validation (do this in-app to save a round trip)

- File picker should accept `audio/*`. On iOS also allow `.m4a` (voice memos) and `.wav`. On Android allow `audio/*` MIME.
- Reject anything > 5MB in-app with a toast.
- Backend will further reject if duration < 5s or > 20s after silence trimming. Surface those errors verbatim from `error_message`.

### 4.5 Char limit

- Use `char_limit` from bootstrap (currently 400).
- Counter goes red at 85% of limit.
- Disable the Generate button if `text.trim().length === 0` or `> char_limit`.

### 4.6 Polling cadence

| Endpoint | Cadence | Stop condition |
|---|---|---|
| `GET /generations/{id}` | every 1.5s | status ∈ {`completed`, `failed`} or 60s elapsed |
| `GET /topups/{reference}` | every 2.5s | status ∈ {`succeeded`, `failed`, `expired`} or 60s elapsed |

Use foreground polling only. When the app backgrounds, pause polling; on resume, resume polling.

---

## 5. OPay button — exact UX

Here's the entire payment flow as it must work in the app:

1. **User taps "Add Funds" pill in the header.**
   - Open the bottom sheet described in § 1.3.
2. **User picks an amount.** Enable "Pay ₦{amount}".
3. **User taps "Pay ₦{amount}".**
   - Disable button, change label to "Processing…".
   - POST `/topups/initiate` with `amount_kobo`, plus deep-link `return_url` and `cancel_url` (e.g. `dropvoice://payments/return`).
4. **Branch on response:**
   - If `cashier_url` is present → open in-app browser at that URL. Keep the bottom sheet visible underneath but disabled, so the user has somewhere to return to.
   - If `status === "succeeded"` (mock mode) → close sheet, refresh `/wallet`, toast "Wallet credited".
5. **User completes payment in OPay.** OPay redirects to `dropvoice://payments/return`. The OS deep-links back into the app.
6. **App handles the deep link:** dismiss the in-app browser, start polling `/topups/{reference}` every 2.5s.
7. **First terminal status:**
   - `succeeded` → close sheet, refresh `/wallet`, toast "Wallet credited."
   - `failed` → leave sheet open, show red error, re-enable button.
   - `expired` → leave sheet open, show grey "Payment expired", re-enable button.
8. **If the app is killed mid-flow** (user force-quit during browser hand-off): on next launch you can still recover by storing the pending `reference` in keychain and re-polling on cold start. Optional but nice.

### Keys (already wired on the backend test environment)

| | |
|---|---|
| Merchant ID | `256624011894787` |
| Public Key | `OPAYPUB17055980246580.49637292218017215` |
| Private Key | `OPAYPRV17055980246580.8264273817439224` |
| Base URL | `https://testapi.opaycheckout.com` |

**Do not put the OPay private key in the app.** Only the backend uses it. The app only sees the `cashier_url` it needs to open.

### Local dev caveat

Real OPay needs a public callback URL it can POST to. Localhost won't receive it, so during local dev OPay-real-mode top-ups will get stuck on `pending`. Two options:

- Stay on `MOCK_PAYMENTS=true` while developing — the backend instantly credits the wallet and `cashier_url` comes back as `null`.
- Or expose your local backend with `ngrok http 8000` and set `OPAY_CALLBACK_URL=https://<your-id>.ngrok.app/v1/topups/opay/webhook` in the backend `.env`.

---

## 6. Mock vs real modes (backend env flags)

The mobile app should not need to know which mode the backend is in — both produce the same response shapes. But it helps to understand:

| Flag | Default | What it does |
|---|---|---|
| `MOCK_TTS` | `false` | when `true`, returns a 440Hz sine WAV instead of calling Cartesia. Use for offline UI testing. |
| `MOCK_PAYMENTS` | `false` | when `true`, top-ups instantly succeed without contacting OPay. |
| `TRANSCRIPT_REWRITER` | `groq` | set to anything else to disable Groq and use the rule-based regex fallback. |

---

## 7. Error envelope

All errors are JSON:

```jsonc
{ "detail": "Insufficient wallet balance." }
```

Always read `detail` from the body. Never display the raw body — wrap it in your own UI strings if you want.

Important app mappings:

| Status | Meaning | App behavior |
|---|---|---|
| `301` / `302` / `307` / `308` | wrong base URL or redirecting proxy, not an app business error | switch the API base to `https://151.80.190.160/v1`; do not show this as an input error |
| `400` | invalid text, language, pace, or upload | show `detail` near the relevant input |
| `401` | stale or invalid device token | silently bootstrap again and retry once |
| `402` | wallet balance is below the generation price | open Add Funds automatically |

Never display Dart object strings like `Instance of 'InputFailure'`. Convert every failure to a user-readable message before updating the UI.

---

## 8. Suggested file/module layout for the app

```
DropVoice/
├── Network/
│   ├── DropVoiceClient.swift / DropVoiceClient.kt   // single class, all 9 endpoints
│   ├── Polling.swift                                // GenerationPoller, TopupPoller
│   └── DeepLinkHandler.swift                        // dropvoice:// URL routing
├── Models/
│   ├── BootstrapResponse, WalletResponse, GenerationStatus, Topup
├── State/
│   ├── AppState (balance, pendingTopup, currentGeneration, lastError)
├── UI/
│   ├── Home/
│   │   ├── HomeScreen
│   │   ├── HeaderBalanceBar
│   │   ├── TextInputCard
│   │   ├── EmotionChips, PaceChips, PronunciationField
│   │   ├── LanguagePicker
│   │   ├── VoiceClonePicker
│   │   ├── GenerateButton
│   │   └── OutputPlayer (download / share / clear)
│   └── AddFundsSheet/
│       ├── AmountPresets
│       ├── CustomAmountField
│       └── PayButton
└── Storage/
    └── SecureStore  (installation_id, device_token, pending topup reference)
```

---

## 9. Definition of done — checklist

- [ ] On first launch, app generates an `installation_id` UUID and POSTs `/v1/device/bootstrap`.
- [ ] `device_token` stored in keychain / keystore, NEVER in NSUserDefaults / SharedPreferences.
- [ ] All authenticated requests carry `Authorization: Bearer <token>`.
- [ ] On 401, app silently re-bootstraps and retries the failed call once.
- [ ] Header shows the current balance, refreshes after every top-up and every generation.
- [ ] Add Funds sheet matches § 1.3, opens in-app browser with the `cashier_url`, polls until terminal.
- [ ] Deep link `dropvoice://payments/return` and `dropvoice://payments/cancel` registered.
- [ ] Generate button respects: empty text → disabled, > char_limit → disabled, in-flight → spinner.
- [ ] All 7 emotion chips work and send the lowercase value to the backend.
- [ ] All 3 pace chips work.
- [ ] Pronunciation hints field forwards verbatim, no parsing in-app.
- [ ] Custom voice picker accepts audio files, rejects > 5MB locally, supports re-picking the same file.
- [ ] Output player has play/pause, download, share, and clear-saved-audio.
- [ ] On `failed` generation, the red banner shows `error_message` and the wallet balance is refreshed (it was refunded).
- [ ] On 402 from POST `/generations`, the Add Funds sheet auto-opens.
- [ ] Status banner / health probe shows a friendly "Backend unavailable" if `/health` fails on launch.

---

## 10. Suggested AI agent prompt (paste into the coding agent)

> You are building the DropVoice mobile app for iOS and Android. Your single source of truth is the document at `APP_DEV_GUIDE.md` in the repo root, plus the working web reference in `frontend/index.html`. You must:
>
> 1. Replicate the visual design of `frontend/index.html` exactly — colors, layout order, chip styles, gradient buttons, the chat-bubble border-radius on the textarea and output card, the bottom-sheet Add Funds modal. Use the WhatsApp green token map from § 1.1. The whole app is a single screen — no navigation, no tabs, no splash other than the bootstrap call.
> 2. Implement the nine endpoints in § 3 in a single `DropVoiceClient` module. Use `https://151.80.190.160/v1` as the staging/prod API base URL unless told otherwise. All money is in kobo. All authenticated calls carry `Authorization: Bearer <device_token>`. On 401, silently re-bootstrap once and retry.
> 3. Implement the OPay flow in § 5 with deep links `dropvoice://payments/return` and `dropvoice://payments/cancel`. Open the cashier URL in an in-app browser (SFSafariViewController on iOS, Custom Tabs on Android). Poll `GET /topups/{reference}` every 2.5s after the deep link returns, until terminal. Never store the OPay private key in the app — the backend handles that.
> 4. Implement the generate flow: multipart POST, then poll `GET /generations/{id}` every 1.5s. On `completed` show the player; on `failed` show the `error_message` and refresh the wallet (server already refunded). On 402 auto-open Add Funds.
> 5. Use `char_limit` from bootstrap, never hardcode 400. Use `supported_languages` for the language picker, never hardcode the list.
> 6. Use the seven emotions in § 4.2 in the order Neutral · Happy · Laughing · Calm · Sad · Angry · Whisper, and the three paces Slow · Normal · Fast.
> 7. Validate the voice clone in-app: audio MIME or by extension, ≤ 5MB. Allow re-picking the same file (reset the picker's value before opening). Surface server-side errors verbatim — they are user-readable.
> 8. Treat the helper text and labels in § 1.2 as canonical copy.
> 9. Tick every item in the Definition of Done checklist in § 9 before opening a PR.
> 10. If anything is ambiguous, refer to `frontend/index.html` and reproduce its exact behavior.
>
> Do not invent endpoints, fields, or statuses that are not in this guide. Do not hardcode prices, char limits, or language lists — read them from the bootstrap response.
