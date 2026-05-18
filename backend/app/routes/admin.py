from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
import secrets
from urllib.parse import quote, urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_session
from app.models import Device, GenerationJob, Wallet, WalletTransactionKind
from app.services.app_settings import get_price_per_generation_kobo, set_price_per_generation_kobo
from app.services.wallets import apply_wallet_delta


router = APIRouter(prefix="/admin", tags=["admin"])
security = HTTPBasic(auto_error=False)


async def require_admin(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    settings = get_settings()
    if not settings.admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin is not configured. Set ADMIN_PASSWORD in the server environment.",
        )
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        _require_same_origin(request)
    if credentials is None:
        _raise_auth_required()
    username_ok = secrets.compare_digest(credentials.username, settings.admin_username)
    password_ok = secrets.compare_digest(credentials.password, settings.admin_password)
    if not username_ok or not password_ok:
        _raise_auth_required()


def _raise_auth_required() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin authentication required.",
        headers={"WWW-Authenticate": "Basic"},
    )


def _require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    origin_host = urlparse(origin).netloc
    expected_host = request.headers.get("host", request.url.netloc)
    if origin_host != expected_host:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-origin admin form blocked.")


def naira_to_kobo(value: str) -> int:
    try:
        amount = Decimal(value.strip().replace(",", ""))
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError("Enter a valid naira amount.") from exc
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    return int((amount * Decimal("100")).quantize(Decimal("1")))


def format_naira(kobo: int | None) -> str:
    value = Decimal(kobo or 0) / Decimal("100")
    return f"NGN {value:,.0f}"


def format_dt(value: datetime | None) -> str:
    return value.isoformat(sep=" ", timespec="seconds") if value else "-"


def admin_redirect(*, notice: str | None = None, error: str | None = None) -> RedirectResponse:
    query = ""
    if notice:
        query = f"?notice={quote(notice)}"
    elif error:
        query = f"?error={quote(error)}"
    return RedirectResponse(url=f"/admin{query}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("", response_class=HTMLResponse)
async def admin_home(
    request: Request,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> HTMLResponse:
    generation_count = (
        select(func.count(GenerationJob.id))
        .where(GenerationJob.wallet_id == Wallet.id)
        .correlate(Wallet)
        .scalar_subquery()
    )
    result = await session.execute(
        select(
            Device.id,
            Device.installation_id,
            Device.platform,
            Device.app_version,
            Device.last_seen_at,
            Wallet.id.label("wallet_id"),
            Wallet.balance_kobo,
            generation_count.label("generation_count"),
        )
        .join(Wallet, Wallet.device_id == Device.id)
        .order_by(Device.last_seen_at.desc())
    )
    devices = result.mappings().all()
    current_price_kobo = await get_price_per_generation_kobo(session)
    notice = request.query_params.get("notice")
    error = request.query_params.get("error")
    html = render_admin_page(
        devices=devices,
        current_price_kobo=current_price_kobo,
        notice=notice,
        error=error,
    )
    return HTMLResponse(html)


@router.post("/devices/{device_id}/credit")
async def credit_device(
    device_id: str,
    amount_naira: str = Form(...),
    note: str = Form("manual admin credit"),
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    try:
        amount_kobo = naira_to_kobo(amount_naira)
    except ValueError as exc:
        return admin_redirect(error=str(exc))

    result = await session.execute(
        select(Device, Wallet)
        .join(Wallet, Wallet.device_id == Device.id)
        .where(Device.id == device_id)
    )
    row = result.first()
    if not row:
        return admin_redirect(error="Device not found.")
    device, wallet = row
    await apply_wallet_delta(
        session,
        wallet,
        delta_kobo=amount_kobo,
        kind=WalletTransactionKind.credit,
        reference=f"admin-credit:{uuid4().hex}",
        details={"source": "admin_web", "note": note.strip()[:180]},
    )
    await session.commit()
    return admin_redirect(notice=f"Credited {format_naira(amount_kobo)} to {device.installation_id}.")


@router.post("/settings/price")
async def update_price(
    amount_naira: str = Form(...),
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    try:
        amount_kobo = naira_to_kobo(amount_naira)
    except ValueError as exc:
        return admin_redirect(error=str(exc))
    await set_price_per_generation_kobo(session, amount_kobo)
    await session.commit()
    return admin_redirect(notice=f"Generation price set to {format_naira(amount_kobo)}.")


def render_admin_page(
    *,
    devices,
    current_price_kobo: int,
    notice: str | None,
    error: str | None,
) -> str:
    rows = "\n".join(render_device_row(device) for device in devices)
    empty = "<tr><td colspan=\"8\" class=\"empty\">No devices have bootstrapped yet.</td></tr>"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DropVoice Admin</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7f7;
      --surface: #ffffff;
      --line: #dfe7e4;
      --text: #15201d;
      --muted: #64736f;
      --accent: #128c7e;
      --accent-2: #25d366;
      --danger: #b42318;
      --shadow: 0 10px 30px rgba(18, 37, 32, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header {{
      background: #0f241f;
      color: #fff;
      padding: 24px clamp(18px, 4vw, 42px);
    }}
    header .inner, main {{
      max-width: 1180px;
      margin: 0 auto;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: clamp(24px, 4vw, 34px);
      letter-spacing: 0;
    }}
    .subtle {{ color: rgba(255,255,255,.72); margin: 0; }}
    main {{ padding: 24px clamp(14px, 3vw, 28px) 42px; }}
    .notice, .error {{
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 16px;
      font-weight: 700;
    }}
    .notice {{ background: #e8fff1; color: #076b40; border: 1px solid #b7edc9; }}
    .error {{ background: #fff1f0; color: var(--danger); border: 1px solid #ffd1cc; }}
    .toolbar {{
      display: grid;
      grid-template-columns: minmax(260px, 1fr) auto;
      gap: 14px;
      align-items: end;
      margin-bottom: 18px;
    }}
    .panel {{
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 16px;
    }}
    .metric-label {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: .04em;
      margin-bottom: 6px;
    }}
    .price {{
      font-size: 24px;
      font-weight: 900;
    }}
    form.inline {{
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }}
    input {{
      height: 42px;
      border: 1px solid var(--line);
      border-radius: 7px;
      padding: 0 11px;
      font: inherit;
      min-width: 130px;
      background: #fff;
    }}
    button {{
      height: 42px;
      border: 0;
      border-radius: 7px;
      background: linear-gradient(135deg, var(--accent-2), var(--accent));
      color: #fff;
      padding: 0 14px;
      font-weight: 900;
      cursor: pointer;
      white-space: nowrap;
    }}
    .table-wrap {{
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
      box-shadow: var(--shadow);
    }}
    table {{
      width: 100%;
      min-width: 1060px;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th {{
      text-align: left;
      background: #eef4f2;
      color: #40504c;
      padding: 12px 14px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .04em;
    }}
    td {{
      padding: 14px;
      border-top: 1px solid var(--line);
      vertical-align: top;
    }}
    .mono {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      overflow-wrap: anywhere;
    }}
    .balance {{
      font-weight: 900;
      color: #0b6e51;
      white-space: nowrap;
    }}
    .muted {{ color: var(--muted); }}
    .empty {{ text-align: center; color: var(--muted); padding: 36px; }}
    .credit-form input[name="amount_naira"] {{ width: 118px; min-width: 118px; }}
    .credit-form input[name="note"] {{ width: 180px; }}
    @media (max-width: 760px) {{
      .toolbar {{ grid-template-columns: 1fr; }}
      form.inline {{ align-items: stretch; }}
      form.inline input, form.inline button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="inner">
      <h1>DropVoice Admin</h1>
      <p class="subtle">Manage device wallets and voice generation pricing.</p>
    </div>
  </header>
  <main>
    {render_alert("notice", notice)}
    {render_alert("error", error)}
    <section class="toolbar">
      <div class="panel">
        <span class="metric-label">Current price per generation</span>
        <div class="price">{escape(format_naira(current_price_kobo))}</div>
      </div>
      <form class="panel inline" action="/admin/settings/price" method="post">
        <label>
          <span class="metric-label">Set global price</span>
          <input name="amount_naira" inputmode="decimal" placeholder="4000" required>
        </label>
        <button type="submit">Save Price</button>
      </form>
    </section>
    <section class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Device</th>
            <th>Installation</th>
            <th>Platform</th>
            <th>Wallet</th>
            <th>Balance</th>
            <th>Generations</th>
            <th>Last Seen</th>
            <th>Credit Wallet</th>
          </tr>
        </thead>
        <tbody>
          {rows or empty}
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>"""


def render_alert(kind: str, message: str | None) -> str:
    if not message:
        return ""
    return f'<div class="{kind}">{escape(message)}</div>'


def render_device_row(device) -> str:
    device_id = str(device["id"])
    installation_id = str(device["installation_id"])
    return f"""<tr>
  <td><div class="mono">{escape(device_id)}</div></td>
  <td><div class="mono">{escape(installation_id)}</div></td>
  <td>{escape(device["platform"] or "-")}<br><span class="muted">{escape(device["app_version"] or "")}</span></td>
  <td><div class="mono">{escape(str(device["wallet_id"]))}</div></td>
  <td><span class="balance">{escape(format_naira(device["balance_kobo"]))}</span></td>
  <td>{int(device["generation_count"] or 0)}</td>
  <td>{escape(format_dt(device["last_seen_at"]))}</td>
  <td>
    <form class="inline credit-form" action="/admin/devices/{escape(device_id)}/credit" method="post">
      <input name="amount_naira" inputmode="decimal" placeholder="20000" required>
      <input name="note" placeholder="note">
      <button type="submit">Credit</button>
    </form>
  </td>
</tr>"""
