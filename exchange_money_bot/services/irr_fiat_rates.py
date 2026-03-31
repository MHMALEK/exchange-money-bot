
from __future__ import annotations

import asyncio
import html
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEFAULT_USD_JSON_URL = (
    "https://raw.githubusercontent.com/margani/pricedb/main/tgju/current/price_dollar_rl/latest.json"
)
DEFAULT_EUR_JSON_URL = (
    "https://raw.githubusercontent.com/margani/pricedb/main/tgju/current/price_eur/latest.json"
)

_snap_lock = asyncio.Lock()
_snap_expires_at: float = 0.0
_snap_usd: Optional[int] = None
_snap_eur: Optional[int] = None
_snap_ts: Optional[str] = None


def _parse_price_p(value: object) -> Optional[int]:
    if value is None:
        return None
    s = str(value).replace(",", "").replace("٬", "").strip()
    if not s.isdigit():
        return None
    return int(s)


async def _fetch_latest_p(
    client: httpx.AsyncClient,
    url: str,
) -> tuple[Optional[int], Optional[str]]:
    try:
        response = await client.get(url, timeout=12.0)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            return None, None
        price = _parse_price_p(data.get("p"))
        ts = data.get("ts")
        ts_str = ts if isinstance(ts, str) else None
        return price, ts_str
    except Exception:
        logger.debug("IRR snapshot fetch failed (%s)", url, exc_info=True)
        return None, None


async def get_usd_eur_rial_snapshot(
    *,
    usd_json_url: str,
    eur_json_url: str,
    ttl_seconds: int,
) -> tuple[Optional[int], Optional[int], Optional[str]]:
    global _snap_expires_at
    global _snap_usd
    global _snap_eur
    global _snap_ts
    now = time.monotonic()
    async with _snap_lock:
        if _snap_expires_at > now:
            return _snap_usd, _snap_eur, _snap_ts

    async with httpx.AsyncClient(headers={"User-Agent": "exchange-money-bot/1.0"}) as client:
        usd_task = asyncio.create_task(_fetch_latest_p(client, usd_json_url))
        eur_task = asyncio.create_task(_fetch_latest_p(client, eur_json_url))
        usd_p, usd_ts = await usd_task
        eur_p, eur_ts = await eur_task

    ts_out = usd_ts or eur_ts
    async with _snap_lock:
        _snap_usd = usd_p
        _snap_eur = eur_p
        _snap_ts = ts_out
        _snap_expires_at = now + max(30, ttl_seconds)
    return usd_p, eur_p, ts_out


def format_buyer_rates_banner_html(
    usd_rial: Optional[int],
    eur_rial: Optional[int],
    updated_ts: Optional[str],
) -> str:
    """Return Telegram-HTML snippet: Farsi disclaimer/source block plus optional USD/EUR lines."""
    price_lines: list[str] = []
    if usd_rial is not None:
        price_lines.append(f"هر دلار: <b>{usd_rial:,}</b> ریال")
    if eur_rial is not None:
        price_lines.append(f"هر یورو: <b>{eur_rial:,}</b> ریال")
    if not price_lines:
        return ""

    # Above figures: source + disclaimer (fixed copy; user-facing Persian in HTML strings below).
    intro = (
        "<b>راهنمای نرخ تقریبی (ریال)</b>\n"
        "<i>قیمت‌های این ربات از فایل‌های JSON عمومی مخزن "
        '<a href="https://github.com/margani/pricedb">margani/pricedb</a>'
        " خوانده می‌شوند و فقط برای نمایش سریع هستند.</i>\n"
        "<i>برای معامله، حتماً نرخ روز را از منابع معتبر هم بررسی کنید؛ "
        'مثلاً <a href="https://bonbast.com">بن‌بست (Bonbast)</a>'
        " را پیش از سفارش یا خرید ببینید.</i>\n"
        "<i>این ربات فقط واسط بین کاربران است و مسئولیتی در قبال قیمت‌ها، "
        "انجام معامله، صحت اطلاعات کاربران یا هرگونه ضمانت و وریفای ندارد.</i>"
    )
    body = "\n".join(price_lines)
    out = intro + "\n\n" + body
    if updated_ts:
        out += "\n<i>زمان ثبت در منبع: " + html.escape(updated_ts, quote=False) + "</i>"
    return out


def rial_equivalent(
    amount: int,
    currency: str,
    *,
    usd_rial: Optional[int],
    eur_rial: Optional[int],
) -> Optional[int]:
    """Approximate IRR for `amount` units of USD or EUR using per-unit rial prices."""
    if amount <= 0:
        return None
    cur = currency.strip().upper()
    rate = usd_rial if cur == "USD" else eur_rial if cur == "EUR" else None
    if rate is None or rate <= 0:
        return None
    return amount * rate
