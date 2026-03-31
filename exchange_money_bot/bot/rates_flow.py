"""Conversation: show live USD/EUR→rial snapshot and approximate IRR for an amount."""

from __future__ import annotations

import logging
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from exchange_money_bot.bot.keyboards import (
    MENU_MAIN_CALLBACK,
    main_menu_keyboard,
    with_back_to_main,
)
from exchange_money_bot.config import settings
from exchange_money_bot.database import async_session_factory
from exchange_money_bot.i18n import t
from exchange_money_bot.services import irr_fiat_rates
from exchange_money_bot.services import sell_offers as sell_offers_service
from exchange_money_bot.services import telegram_channel as telegram_channel_service
from exchange_money_bot.services import users as user_service

logger = logging.getLogger(__name__)

ASK_AMOUNT, PICK_CURRENCY = range(2)


def _parse_integer_amount(text: str) -> Optional[int]:
    s = text.strip()
    if not s or any(ch.isspace() for ch in s):
        return None
    if not s.isascii() or not all("0" <= c <= "9" for c in s):
        return None
    value = int(s)
    if value <= 0:
        return None
    return value


def _ccy_pick_keyboard() -> InlineKeyboardMarkup:
    return with_back_to_main(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        t("rates.btn_usd"), callback_data="rates:ccy:USD"
                    ),
                    InlineKeyboardButton(
                        t("rates.btn_eur"), callback_data="rates:ccy:EUR"
                    ),
                ],
            ]
        )
    )


async def _end_if_not_member(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> Optional[int]:
    u = update.effective_user
    if u is None:
        return ConversationHandler.END
    if not settings.membership_gate_active():
        return None
    if await telegram_channel_service.user_passes_membership_gate(context.bot, u.id):
        return None
    join_kb = (
        await telegram_channel_service.join_channel_keyboard_async(context.bot)
        or InlineKeyboardMarkup([])
    )
    markup = with_back_to_main(join_kb)
    text = t("membership.required_html")
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    elif update.callback_query and update.callback_query.message:
        await update.callback_query.message.reply_text(
            text, parse_mode="HTML", reply_markup=markup
        )
    _clear_rates_keys(context)
    return ConversationHandler.END


def _clear_rates_keys(context: ContextTypes.DEFAULT_TYPE) -> None:
    ud = context.user_data
    for k in (
        "rates_snap_usd",
        "rates_snap_eur",
        "rates_snap_ts",
        "calc_amount",
    ):
        ud.pop(k, None)


async def rates_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None or query.from_user is None:
        return ConversationHandler.END
    await query.answer()
    tid = query.from_user.id
    async with async_session_factory() as session:
        reg = await user_service.get_user_by_telegram(session, tid)
    if reg is None:
        await query.message.reply_text(
            t("error.register_first"),
            reply_markup=with_back_to_main(InlineKeyboardMarkup([])),
        )
        return ConversationHandler.END
    if not await telegram_channel_service.user_passes_membership_gate(
        context.bot, tid
    ):
        join_kb = (
            await telegram_channel_service.join_channel_keyboard_async(context.bot)
            or InlineKeyboardMarkup([])
        )
        await query.message.reply_text(
            t("membership.required_html"),
            parse_mode="HTML",
            reply_markup=with_back_to_main(join_kb),
        )
        return ConversationHandler.END

    _clear_rates_keys(context)
    usd_url = settings.irr_usd_json_url or irr_fiat_rates.DEFAULT_USD_JSON_URL
    eur_url = settings.irr_eur_json_url or irr_fiat_rates.DEFAULT_EUR_JSON_URL
    try:
        usd, eur, ts = await irr_fiat_rates.get_usd_eur_rial_snapshot(
            usd_json_url=usd_url,
            eur_json_url=eur_url,
            ttl_seconds=settings.irr_rates_ttl_seconds,
        )
    except Exception:
        logger.exception("IRR snapshot fetch failed")
        usd, eur, ts = None, None, None

    context.user_data["rates_snap_usd"] = usd
    context.user_data["rates_snap_eur"] = eur
    context.user_data["rates_snap_ts"] = ts

    banner = irr_fiat_rates.format_buyer_rates_banner_html(usd, eur, ts)
    if not banner:
        await query.message.reply_text(
            t("rates.unavailable_html"),
            parse_mode="HTML",
            reply_markup=with_back_to_main(InlineKeyboardMarkup([])),
        )
        return ConversationHandler.END

    await query.message.reply_text(
        banner + "\n\n" + t("rates.amount_prompt_html"),
        parse_mode="HTML",
        reply_markup=with_back_to_main(InlineKeyboardMarkup([])),
    )
    return ASK_AMOUNT


async def rates_receive_amount(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    end = await _end_if_not_member(update, context)
    if end is not None:
        return end
    if update.message is None or not update.message.text:
        return ASK_AMOUNT
    amt = _parse_integer_amount(update.message.text)
    if amt is None:
        await update.message.reply_text(t("rates.amount_invalid"))
        return ASK_AMOUNT
    context.user_data["calc_amount"] = amt
    await update.message.reply_text(
        t("rates.pick_currency"),
        reply_markup=_ccy_pick_keyboard(),
    )
    return PICK_CURRENCY


async def rates_currency_chosen(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.message is None or query.data is None:
        return ConversationHandler.END
    end = await _end_if_not_member(update, context)
    if end is not None:
        await query.answer()
        return end

    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "rates" or parts[1] != "ccy":
        await query.answer()
        return PICK_CURRENCY
    code = parts[2]
    if code not in sell_offers_service.ALLOWED_CURRENCIES:
        await query.answer()
        return PICK_CURRENCY

    amount = context.user_data.get("calc_amount")
    if not isinstance(amount, int):
        await query.answer()
        await query.message.reply_text(
            t("rates.session_lost"),
            reply_markup=main_menu_keyboard(),
        )
        _clear_rates_keys(context)
        return ConversationHandler.END

    usd = context.user_data.get("rates_snap_usd")
    eur = context.user_data.get("rates_snap_eur")
    total = irr_fiat_rates.rial_equivalent(
        amount,
        code,
        usd_rial=usd if isinstance(usd, int) else None,
        eur_rial=eur if isinstance(eur, int) else None,
    )
    await query.answer()
    if total is None:
        await query.message.reply_text(
            t("rates.rate_missing_for_ccy", ccy=code),
            reply_markup=_ccy_pick_keyboard(),
        )
        return PICK_CURRENCY

    rate_val = usd if code == "USD" else eur
    ccy_fa = sell_offers_service.currency_label_fa(code)
    await query.message.reply_text(
        t(
            "rates.result_html",
            amount=amount,
            ccy_fa=ccy_fa,
            code=code,
            rate=rate_val,
            total=total,
        ),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    _clear_rates_keys(context)
    return ConversationHandler.END


async def rates_conversation_cancel(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    _clear_rates_keys(context)
    if update.message:
        await update.message.reply_text(
            t("rates.cancelled"),
            reply_markup=main_menu_keyboard(),
        )
    return ConversationHandler.END


async def rates_back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
    _clear_rates_keys(context)
    if query and query.message:
        from exchange_money_bot.bot.main import apply_home_screen

        await apply_home_screen(query, context.bot)
    return ConversationHandler.END


def build_rates_conversation_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(rates_entry, pattern=r"^rates:start$")],
        states={
            ASK_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, rates_receive_amount),
            ],
            PICK_CURRENCY: [
                CallbackQueryHandler(
                    rates_currency_chosen,
                    pattern=r"^rates:ccy:(EUR|USD)$",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, rates_pick_reminder),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", rates_conversation_cancel),
            CallbackQueryHandler(rates_back_to_main, pattern=rf"^{MENU_MAIN_CALLBACK}$"),
        ],
        name="rates_calc",
        allow_reentry=True,
    )


async def rates_pick_reminder(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    end = await _end_if_not_member(update, context)
    if end is not None:
        return end
    if update.message:
        await update.message.reply_text(
            t("rates.pick_currency_reminder"),
            reply_markup=_ccy_pick_keyboard(),
        )
    return PICK_CURRENCY
