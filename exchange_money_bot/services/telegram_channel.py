"""Post sell listings to a Telegram channel and enforce optional channel membership."""

from __future__ import annotations

import html
import logging
from typing import Optional, Protocol, Sequence

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

from exchange_money_bot.config import settings
from exchange_money_bot.constants import TELEGRAM_INLINE_BUTTON_LABEL_MAX
from exchange_money_bot.database import async_session_factory
from exchange_money_bot.i18n import t
from exchange_money_bot.services import bot_kv as bot_kv_service
from exchange_money_bot.services import irr_fiat_rates
from exchange_money_bot.services import sell_offers as sell_offers_service

logger = logging.getLogger(__name__)

CHANNEL_PINNED_RATES_KV_KEY = "listings_channel_pinned_rates_message_id"


class _ListingDisplay(Protocol):
    amount: int
    currency: str
    seller_display_name: str
    telegram_username: Optional[str]
    telegram_id: int


_MEMBER_OK = frozenset(
    {
        ChatMemberStatus.MEMBER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.OWNER,
        ChatMemberStatus.RESTRICTED,
    }
)


def _contact_url(offer: _ListingDisplay) -> str:
    if offer.telegram_username:
        u = offer.telegram_username.strip().lstrip("@")
        if u:
            return f"https://t.me/{u}"
    return f"tg://user?id={offer.telegram_id}"


def format_listing_html(
    offer: _ListingDisplay,
    *,
    closed: bool = False,
    closed_note_key: str = "listing.closed_note",
) -> str:
    ccy_fa = sell_offers_service.currency_label_fa(offer.currency)
    name = html.escape(offer.seller_display_name.strip(), quote=False)
    ccy_esc = html.escape(ccy_fa, quote=False)
    cur_esc = html.escape(offer.currency, quote=False)
    if offer.telegram_username:
        u = offer.telegram_username.strip().lstrip("@")
        uname = f"@{html.escape(u, quote=False)}"
    else:
        uname = t("listing.no_username")
    body = "\n".join(
        [
            t("listing.header_html"),
            t(
                "listing.amount_line",
                amount=offer.amount,
                ccy_fa=ccy_esc,
                currency=cur_esc,
            ),
            t("listing.seller_line", name=name),
            t("listing.telegram_line", telegram_line=uname),
            "",
            t("listing.tags_template", currency=offer.currency.upper()),
        ]
    )
    if closed:
        return f"<s>{body}</s>\n\n{t(closed_note_key)}"
    return body


def listing_contact_keyboard(offer: _ListingDisplay) -> InlineKeyboardMarkup:
    ccy_fa = sell_offers_service.currency_label_fa(offer.currency)
    label = t("listing.contact_btn", amount=offer.amount, ccy_fa=ccy_fa)
    max_len = TELEGRAM_INLINE_BUTTON_LABEL_MAX
    if len(label) > max_len:
        label = label[: max_len - 1] + "…"
    contact_btn = InlineKeyboardButton(label, url=_contact_url(offer))
    oid = getattr(offer, "id", None)
    if oid is not None:
        rial_lbl = t("listing.rial_btn")
        if len(rial_lbl) > max_len:
            rial_lbl = rial_lbl[: max_len - 1] + "…"
        return InlineKeyboardMarkup(
            [
                [contact_btn],
                [
                    InlineKeyboardButton(
                        rial_lbl,
                        callback_data=f"rial:{int(oid)}",
                    )
                ],
            ]
        )
    return InlineKeyboardMarkup([[contact_btn]])


async def resolve_listings_channel_open_url(bot: Bot) -> Optional[str]:
    """Invite URL, t.me from @id, or from get_chat (invite_link / username) for numeric channel ids."""
    direct = settings.effective_listings_channel_open_url()
    if direct:
        return direct
    cid = (settings.telegram_listings_channel_id or "").strip()
    if not cid:
        return None
    try:
        chat = await bot.get_chat(chat_id=cid)
        link = getattr(chat, "invite_link", None)
        if link:
            return link
        uname = getattr(chat, "username", None)
        if uname and str(uname).strip():
            return f"https://t.me/{str(uname).strip().lstrip('@')}"
    except TelegramError as e:
        logger.debug("resolve_listings_channel_open_url get_chat failed: %s", e)
    return None


async def join_channel_keyboard_async(bot: Bot) -> Optional[InlineKeyboardMarkup]:
    url = await resolve_listings_channel_open_url(bot)
    if not url:
        return None
    return InlineKeyboardMarkup([[InlineKeyboardButton(t("channel.btn_join"), url=url)]])


async def user_is_channel_member(
    bot: Bot, user_id: int, channel_chat_id: str
) -> bool:
    try:
        m = await bot.get_chat_member(chat_id=channel_chat_id, user_id=user_id)
        return m.status in _MEMBER_OK
    except TelegramError as e:
        logger.warning("get_chat_member failed user_id=%s chat=%s: %s", user_id, channel_chat_id, e)
        return False


async def user_passes_membership_gate(bot: Bot, user_id: int) -> bool:
    if not settings.membership_gate_active():
        return True
    cid = settings.effective_membership_channel_id()
    assert cid is not None
    return await user_is_channel_member(bot, user_id, cid)


async def post_offer_to_listings_channel(bot: Bot, offer: _ListingDisplay) -> Optional[int]:
    cid = settings.telegram_listings_channel_id
    if not cid:
        return None
    text = format_listing_html(offer, closed=False)
    try:
        msg = await bot.send_message(
            chat_id=cid,
            text=text,
            parse_mode="HTML",
            reply_markup=listing_contact_keyboard(offer),
        )
        return int(msg.message_id)
    except TelegramError:
        oid = getattr(offer, "id", "?")
        logger.exception("Failed to post listing offer_id=%s to channel", oid)
        return None


async def mark_listing_closed_on_channel(
    bot: Optional[Bot],
    *,
    message_id: Optional[int],
    offer: _ListingDisplay,
    closed_note_key: str = "listing.closed_note",
) -> None:
    if bot is None or message_id is None:
        return
    cid = settings.telegram_listings_channel_id
    if not cid:
        return
    text = format_listing_html(offer, closed=True, closed_note_key=closed_note_key)
    try:
        await bot.edit_message_text(
            chat_id=cid,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=None,
        )
    except TelegramError:
        logger.warning(
            "Could not strikethrough listing message_id=%s (offer may be old or deleted)",
            message_id,
        )


async def close_listings_for_offers(
    bot: Optional[Bot],
    offers: Sequence[_ListingDisplay],
) -> None:
    for o in offers:
        mid = getattr(o, "listings_channel_message_id", None)
        if mid is not None:
            await mark_listing_closed_on_channel(bot, message_id=mid, offer=o)


async def refresh_channel_pinned_rates(bot: Bot) -> None:
    """Create or edit a pinned HTML message with live USD/EUR per-unit rial (listings channel)."""
    cid = (settings.telegram_listings_channel_id or "").strip()
    if not cid or not settings.irr_channel_pin_enabled:
        return

    usd_url = settings.irr_usd_json_url or irr_fiat_rates.DEFAULT_USD_JSON_URL
    eur_url = settings.irr_eur_json_url or irr_fiat_rates.DEFAULT_EUR_JSON_URL
    try:
        usd, eur, ts = await irr_fiat_rates.get_usd_eur_rial_snapshot(
            usd_json_url=usd_url,
            eur_json_url=eur_url,
            ttl_seconds=settings.irr_rates_ttl_seconds,
        )
    except Exception:
        logger.exception("IRR snapshot for channel pin failed")
        usd, eur, ts = None, None, None

    text = irr_fiat_rates.format_buyer_rates_banner_html(usd, eur, ts)
    if not text.strip():
        logger.warning("Channel rates pin skipped: no price lines in banner")
        return

    async with async_session_factory() as session:
        mid_raw = await bot_kv_service.get_value(session, CHANNEL_PINNED_RATES_KV_KEY)

    message_id: Optional[int] = None
    if mid_raw and str(mid_raw).strip().isdigit():
        message_id = int(str(mid_raw).strip())

    if message_id is not None:
        try:
            await bot.edit_message_text(
                chat_id=cid,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
            )
            return
        except TelegramError as e:
            logger.info("Channel rates edit failed, sending new message: %s", e)
            message_id = None

    try:
        msg = await bot.send_message(chat_id=cid, text=text, parse_mode="HTML")
    except TelegramError:
        logger.exception("Could not send channel rates message (check bot admin rights)")
        return

    new_id = int(msg.message_id)
    async with async_session_factory() as session:
        await bot_kv_service.set_value(session, CHANNEL_PINNED_RATES_KV_KEY, str(new_id))

    try:
        await bot.pin_chat_message(
            chat_id=cid,
            message_id=new_id,
            disable_notification=True,
        )
    except TelegramError as e:
        logger.warning("pin_chat_message failed (need can_pin_messages): %s", e)
