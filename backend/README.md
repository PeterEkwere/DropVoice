# DropVoice Backend

This backend is designed for a mobile app, not a website. It exposes a small anonymous wallet API:

- `POST /v1/device/bootstrap`
- `GET /v1/wallet`
- `POST /v1/topups/initiate`
- `GET /v1/topups/{reference}`
- `POST /v1/topups/opay/webhook`
- `POST /v1/generations`
- `GET /v1/generations/{id}`
- `GET /v1/generations/{id}/audio`
- `DELETE /v1/generations/{id}/audio`

Notes:

- Wallets are device-tied. If the app reinstall changes `installation_id`, the balance is lost in v1.
- Generated audio is stored temporarily on disk and cleared either by TTL or the explicit delete endpoint.
- Voice cloning is limited to audio uploads in this first scaffold.
- The in-process worker is enough for a first pass. If you later run multiple API instances, move the queue worker into a separate process or replace it with Redis/Celery/Sidekiq-style infrastructure.
- All money fields use kobo internally. Your mobile app should send `amount_kobo`, not naira floats.
- Local development defaults to SQLite plus mock top-ups and mock TTS so the whole flow can be exercised without live provider callbacks.

Run locally from `backend/` with:

```bash
uvicorn app.main:app --reload
```

Admin wallet helpers, also run from `backend/`:

```bash
../.venv/bin/python scripts/dropvoice_admin.py list-devices
../.venv/bin/python scripts/dropvoice_admin.py credit-wallet --installation-id <installation_id> --amount-naira 20000
```

Admin website:

- URL: `/admin`
- Auth: HTTP Basic using `ADMIN_USERNAME` and `ADMIN_PASSWORD`
- `ADMIN_PASSWORD` must be set in the server environment or `backend/.env`; otherwise the admin page is disabled.
- The global price form writes to the database and overrides `PRICE_PER_GENERATION_KOBO` for new bootstraps and new generations.

Do not commit production `.env` values. On the server, add only the missing admin lines manually:

```bash
cd ~/DropVoice/backend
grep -q '^ADMIN_USERNAME=' .env || printf '\nADMIN_USERNAME=admin\n' >> .env
grep -q '^ADMIN_PASSWORD=' .env || printf 'ADMIN_PASSWORD=change-this-password\n' >> .env
```
