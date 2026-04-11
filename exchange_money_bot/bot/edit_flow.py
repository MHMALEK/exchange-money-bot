"""Edit existing sell listing — same steps as create, with channel message refreshed."""

from __future__ import annotations

import logging
import re

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
from exchange_money_bot.bot.sell_flow import (
    _amount_prompt_text,
    _amount_reply_parse_mode,
    _currency_label,
    _end_sell_if_not_member,
    _listing_direction,
    _parse_integer_amount,
    _sell_summary_text,
)
from exchange_money_bot.config import settings
from exchange_money_bot.database import async_session_factory
from exchange_money_bot.i18n import t
from exchange_money_bot.services import sell_offers as sell_offers_service
from exchange_money_bot.services import telegram_channel as telegram_channel_service
from exchange_money_bot.services import users as user_service

logger = logging.getLogger(__name__)

EDIT_AMOUNT, EDIT_CURRENCY, EDIT_DESCRIPTION, EDIT_PAYMENT, EDIT_CONFIRM = range(5)

MAX_DESCRIPTION_LEN = sell_offers_service.MAX_OFFER_DESCRIPTION_LEN

_EDIT_PAYMENT_TOGGLE_PATTERN = (
    r"^edit:pay:(cash_in_person|bank|crypto|other)$"
)


def _clear_edit_user_data(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("editing_offer_id", None)
    context.user_data.pop("sell_amount", None)
    context.user_data.pop("sell_currency", None)
    context.user_data.pop("sell_description", None)
    context.user_data.pop("sell_payment_methods", None)
    context.user_data.pop("listing_direction", None)


def _currency_keyboard() -> InlineKeyboardMarkup:
    return with_back_to_main(
        InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(t("sell.btn_eur"), callback_data="edit:ccy:EUR")],
                [InlineKeyboardButton(t("sell.btn_usd"), callback_data="edit:ccy:USD")],
            ]
        )
    )


def _description_keyboard() -> InlineKeyboardMarkup:
    return with_back_to_main(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        t("sell.btn_desc_skip"), callback_data="edit:desc:skip"
                    ),
                ],
            ]
        )
    )


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return with_back_to_main(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(t("sell.btn_abort"), callback_data="edit:abort"),
                    InlineKeyboardButton(t("edit.btn_save"), callback_data="edit:submit"),
                ],
            ]
        )
    )


def _payment_codes_from_user_data(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    raw = context.user_data.get("sell_payment_methods")
    if not isinstance(raw, list):
        return []
    return [c for c in raw if isinstance(c, str)]


def _payment_keyboard(selected: list[str]) -> InlineKeyboardMarkup:
    sel_set = set(selected)

    def lbl(code: str) -> str:
        mark = "✓ " if code in sel_set else "○ "
        return mark + sell_offers_service.payment_method_label_fa(code)

    codes = sell_offers_service.PAYMENT_METHOD_CODES_ORDER
    return with_back_to_main(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(lbl(codes[0]), callback_data=f"edit:pay:{codes[0]}"),
                    InlineKeyboardButton(lbl(codes[1]), callback_data=f"edit:pay:{codes[1]}"),
                ],
                [
                    InlineKeyboardButton(lbl(codes[2]), callback_data=f"edit:pay:{codes[2]}"),
                    InlineKeyboardButton(lbl(codes[3]), callback_data=f"edit:pay:{codes[3]}"),
                ],
                [
                    InlineKeyboardButton(
                        t("sell.payment_btn_done"),
                        callback_data="edit:pay:done",
                    ),
                ],
            ]
        )
    )


async def _send_payment_prompt(message, context: ContextTypes.DEFAULT_TYPE) -> None:
    sel = _payment_codes_from_user_data(context)
    if not sel:
        context.user_data["sell_payment_methods"] = []
        sel = []
    await message.reply_text(
        t("sell.payment_prompt"),
        reply_markup=_payment_keyboard(sel),
        parse_mode="HTML",
    )


async def edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None or query.data is None or query.from_user is None:
        return ConversationHandler.END
    await query.answer()
    m = re.fullmatch(r"offer:edit:(\d+)", query.data)
    if not m:
        return ConversationHandler.END
    offer_id = int(m.group(1))
    tid = query.from_user.id
    async with async_session_factory() as session:
        registered = await user_service.get_user_by_telegram(session, tid)
    if registered is None:
        await query.message.reply_text(t("sell.register_first"))
        return ConversationHandler.END
    if not await telegram_channel_service.user_passes_membership_gate(context.bot, tid):
        join_kb = (
            await telegram_channel_service.join_channel_keyboard_async(context.bot)
            or InlineKeyboardMarkup([])
        )
        await query.message.reply_text(
            t("membership.sell_gate_html"),
            parse_mode="HTML",
            reply_markup=with_back_to_main(join_kb),
        )
        return ConversationHandler.END
    async with async_session_factory() as session:
        offer = await sell_offers_service.get_offer_by_id(session, offer_id)
    if offer is None or offer.user_id != registered.id:
        await query.message.reply_text(
            t("error.offer_not_yours"),
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END
    _clear_edit_user_data(context)
    context.user_data["editing_offer_id"] = offer_id
    context.user_data["sell_amount"] = offer.amount
    context.user_data["sell_currency"] = offer.currency
    context.user_data["sell_description"] = offer.description
    pm = offer.payment_methods or []
    context.user_data["sell_payment_methods"] = list(pm) if pm else []
    ld = getattr(offer, "listing_direction", None) or sell_offers_service.DEFAULT_LISTING_DIRECTION
    context.user_data["listing_direction"] = ld
    intro = t(
        "edit.intro_html",
        amount=offer.amount,
        currency_label=_currency_label(offer.currency),
    )
    await query.message.reply_text(
        intro + "\n\n" + _amount_prompt_text(context),
        reply_markup=with_back_to_main(InlineKeyboardMarkup([])),
        parse_mode="HTML",
    )
    return EDIT_AMOUNT


async def edit_receive_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        return end
    if update.message is None:
        return EDIT_AMOUNT
    text = update.message.text or ""
    amount = _parse_integer_amount(text)
    if amount is None:
        await update.message.reply_text(
            t("sell.amount_invalid"),
            reply_markup=with_back_to_main(InlineKeyboardMarkup([])),
            parse_mode=_amount_reply_parse_mode(context),
        )
        return EDIT_AMOUNT
    context.user_data["sell_amount"] = amount
    pick_key = (
        "sell.pick_currency_rial_to_fx"
        if _listing_direction(context) == sell_offers_service.LISTING_RIAL_TO_FX
        else "sell.pick_currency"
    )
    await update.message.reply_text(
        t(pick_key),
        reply_markup=_currency_keyboard(),
    )
    return EDIT_CURRENCY


async def edit_currency_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        return end
    if update.message:
        rem_key = (
            "sell.currency_reminder_rial_to_fx"
            if _listing_direction(context) == sell_offers_service.LISTING_RIAL_TO_FX
            else "sell.currency_reminder"
        )
        await update.message.reply_text(
            t(rem_key),
            reply_markup=_currency_keyboard(),
        )
    return EDIT_CURRENCY


async def edit_currency_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None or query.data is None or query.from_user is None:
        return ConversationHandler.END
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        await query.answer()
        return end
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "edit" or parts[1] != "ccy":
        return EDIT_CURRENCY
    code = parts[2]
    if code not in sell_offers_service.ALLOWED_CURRENCIES:
        return EDIT_CURRENCY
    context.user_data["sell_currency"] = code
    amount = context.user_data.get("sell_amount")
    if not isinstance(amount, int):
        await query.message.reply_text(
            t("error.amount_lost"),
            reply_markup=main_menu_keyboard(),
        )
        _clear_edit_user_data(context)
        return ConversationHandler.END
    await query.message.reply_text(
        t("sell.description_prompt", max=MAX_DESCRIPTION_LEN),
        reply_markup=_description_keyboard(),
    )
    return EDIT_DESCRIPTION


async def edit_description_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None or query.from_user is None:
        return ConversationHandler.END
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        await query.answer()
        return end
    await query.answer()
    amount = context.user_data.get("sell_amount")
    code = context.user_data.get("sell_currency")
    if not isinstance(amount, int) or not isinstance(code, str):
        await query.message.reply_text(
            t("error.amount_lost"),
            reply_markup=main_menu_keyboard(),
        )
        _clear_edit_user_data(context)
        return ConversationHandler.END
    context.user_data["sell_description"] = None
    await _send_payment_prompt(query.message, context)
    return EDIT_PAYMENT


async def edit_receive_description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        return end
    if update.message is None:
        return EDIT_DESCRIPTION
    raw = update.message.text or ""
    text = raw.strip()
    if not text:
        await update.message.reply_text(
            t("sell.description_empty"),
            reply_markup=_description_keyboard(),
        )
        return EDIT_DESCRIPTION
    if len(text) > MAX_DESCRIPTION_LEN:
        await update.message.reply_text(
            t("sell.description_too_long", max=MAX_DESCRIPTION_LEN),
            reply_markup=_description_keyboard(),
        )
        return EDIT_DESCRIPTION
    amount = context.user_data.get("sell_amount")
    code = context.user_data.get("sell_currency")
    if not isinstance(amount, int) or not isinstance(code, str):
        await update.message.reply_text(
            t("error.amount_lost"),
            reply_markup=main_menu_keyboard(),
        )
        _clear_edit_user_data(context)
        return ConversationHandler.END
    context.user_data["sell_description"] = text
    await _send_payment_prompt(update.message, context)
    return EDIT_PAYMENT


async def edit_description_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        return end
    if update.message:
        await update.message.reply_text(
            t("sell.description_reminder", max=MAX_DESCRIPTION_LEN),
            reply_markup=_description_keyboard(),
        )
    return EDIT_DESCRIPTION


async def edit_payment_toggle(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> int:
    query = update.callback_query
    if query is None or query.message is None or query.data is None:
        return ConversationHandler.END
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        await query.answer()
        return end
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "edit" or parts[1] != "pay":
        return EDIT_PAYMENT
    code = parts[2]
    if code not in sell_offers_service.ALLOWED_PAYMENT_METHODS:
        return EDIT_PAYMENT
    sel = _payment_codes_from_user_data(context)
    if code in sel:
        sel = [c for c in sel if c != code]
    else:
        sel = [*sel, code]
    context.user_data["sell_payment_methods"] = sel
    try:
        await query.edit_message_reply_markup(reply_markup=_payment_keyboard(sel))
    except Exception:
        logger.debug("edit_message_reply_markup failed (edit payment toggles)", exc_info=True)
    return EDIT_PAYMENT


async def edit_payment_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None or query.from_user is None:
        return ConversationHandler.END
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        await query.answer()
        return end
    sel = _payment_codes_from_user_data(context)
    try:
        normalized = sell_offers_service.normalize_payment_methods(sel)
    except ValueError:
        await query.answer(t("sell.payment_need_one"), show_alert=True)
        return EDIT_PAYMENT
    await query.answer()
    context.user_data["sell_payment_methods"] = normalized
    amount = context.user_data.get("sell_amount")
    code = context.user_data.get("sell_currency")
    if not isinstance(amount, int) or not isinstance(code, str):
        await query.message.reply_text(
            t("error.amount_lost"),
            reply_markup=main_menu_keyboard(),
        )
        _clear_edit_user_data(context)
        return ConversationHandler.END
    desc_raw = context.user_data.get("sell_description")
    description = desc_raw if isinstance(desc_raw, str) else None
    u = query.from_user
    display_name = u.full_name or t("sell.display_fallback")
    uname = f"@{u.username}" if u.username else t("sell.username_none")
    await query.message.reply_text(
        _sell_summary_text(
            amount=amount,
            code=code,
            display_name=display_name,
            uname=uname,
            description=description,
            payment_methods=normalized,
            listing_direction=_listing_direction(context),
        ),
        reply_markup=_confirm_keyboard(),
    )
    return EDIT_CONFIRM


async def edit_payment_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        return end
    if update.message:
        sel = _payment_codes_from_user_data(context)
        await update.message.reply_text(
            t("sell.payment_reminder"),
            reply_markup=_payment_keyboard(sel),
        )
    return EDIT_PAYMENT


async def edit_confirm_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        return end
    if update.message:
        amount = context.user_data.get("sell_amount")
        code = context.user_data.get("sell_currency")
        desc = context.user_data.get("sell_description")
        pm = _payment_codes_from_user_data(context)
        u = update.effective_user
        if (
            isinstance(amount, int)
            and isinstance(code, str)
            and u is not None
            and (desc is None or isinstance(desc, str))
            and pm
        ):
            try:
                pm_norm = sell_offers_service.normalize_payment_methods(pm)
            except ValueError:
                pm_norm = None
            if pm_norm:
                display_name = u.full_name or t("sell.display_fallback")
                uname = f"@{u.username}" if u.username else t("sell.username_none")
                await update.message.reply_text(
                    _sell_summary_text(
                        amount=amount,
                        code=code,
                        display_name=display_name,
                        uname=uname,
                        description=desc if desc else None,
                        payment_methods=pm_norm,
                        listing_direction=_listing_direction(context),
                    ),
                    reply_markup=_confirm_keyboard(),
                )
            else:
                await update.message.reply_text(
                    t("edit.confirm_reminder"),
                    reply_markup=_confirm_keyboard(),
                )
        else:
            await update.message.reply_text(
                t("edit.confirm_reminder"),
                reply_markup=_confirm_keyboard(),
            )
    return EDIT_CONFIRM


async def edit_submit_or_abort(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None or query.data is None or query.from_user is None:
        return ConversationHandler.END
    end = await _end_sell_if_not_member(update, context)
    if end is not None:
        await query.answer()
        return end
    await query.answer()
    if query.data == "edit:abort":
        _clear_edit_user_data(context)
        await query.message.reply_text(
            t("edit.aborted"),
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END
    if query.data != "edit:submit":
        return EDIT_CONFIRM
    offer_id = context.user_data.get("editing_offer_id")
    amount = context.user_data.get("sell_amount")
    currency = context.user_data.get("sell_currency")
    if not isinstance(offer_id, int) or not isinstance(amount, int) or not isinstance(currency, str):
        await query.message.reply_text(
            t("error.data_lost"),
            reply_markup=main_menu_keyboard(),
        )
        _clear_edit_user_data(context)
        return ConversationHandler.END
    u = query.from_user
    async with async_session_factory() as session:
        db_user = await user_service.get_user_by_telegram(session, u.id)
        if db_user is None:
            await query.message.reply_text(
                t("error.user_not_found"),
                reply_markup=main_menu_keyboard(),
            )
            _clear_edit_user_data(context)
            return ConversationHandler.END
        display_name = u.full_name or (db_user.first_name or "—")
        desc_raw = context.user_data.get("sell_description")
        description = desc_raw if isinstance(desc_raw, str) else None
        pm_raw = context.user_data.get("sell_payment_methods")
        if not isinstance(pm_raw, list) or not pm_raw:
            await query.message.reply_text(
                t("error.data_lost"),
                reply_markup=main_menu_keyboard(),
            )
            _clear_edit_user_data(context)
            return ConversationHandler.END
        try:
            payment_methods = sell_offers_service.normalize_payment_methods(pm_raw)
        except ValueError:
            await query.message.reply_text(
                t("error.data_lost"),
                reply_markup=main_menu_keyboard(),
            )
            _clear_edit_user_data(context)
            return ConversationHandler.END
        try:
            offer = await sell_offers_service.update_sell_offer_owned(
                session,
                offer_id,
                db_user.id,
                amount=amount,
                currency=currency,
                description=description,
                payment_methods=payment_methods,
                telegram_username=u.username,
                seller_display_name=display_name,
            )
        except ValueError as e:
            logger.warning("edit offer validation: %s", e)
            await query.message.reply_text(
                t("error.offer_save"),
                reply_markup=main_menu_keyboard(),
            )
            _clear_edit_user_data(context)
            return ConversationHandler.END
        if offer is None:
            await query.message.reply_text(
                t("error.offer_not_yours"),
                reply_markup=main_menu_keyboard(),
            )
            _clear_edit_user_data(context)
            return ConversationHandler.END
    new_mid = await telegram_channel_service.refresh_or_repost_listing(context.bot, offer)
    if new_mid is not None and new_mid != getattr(offer, "listings_channel_message_id", None):
        async with async_session_factory() as session:
            await sell_offers_service.set_listings_channel_message_id(
                session, offer.id, new_mid
            )
    _clear_edit_user_data(context)
    if settings.effective_listings_channel_id():
        channel_note = t("sell.success_channel_on_html")
    else:
        channel_note = t("sell.success_channel_off")
    await query.message.reply_text(
        t(
            "edit.success_html",
            amount=amount,
            currency_label=_currency_label(currency),
            channel_note=channel_note,
        ),
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def edit_conversation_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    _clear_edit_user_data(context)
    if update.message:
        await update.message.reply_text(
            t("edit.cancelled_cmd"),
            reply_markup=main_menu_keyboard(),
        )
    return ConversationHandler.END


async def edit_buy_flow_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None or query.from_user is None:
        return ConversationHandler.END
    _clear_edit_user_data(context)
    from exchange_money_bot.bot.main import execute_buy_flow_callback

    await execute_buy_flow_callback(query, context.bot)
    return ConversationHandler.END


async def edit_menu_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query is None or query.message is None:
        return ConversationHandler.END
    await query.answer()
    _clear_edit_user_data(context)
    from exchange_money_bot.bot.main import apply_home_screen

    await apply_home_screen(query, context.bot)
    return ConversationHandler.END


def build_edit_conversation_handler() -> ConversationHandler:
    menu_main_handler = CallbackQueryHandler(
        edit_menu_main,
        pattern=rf"^{MENU_MAIN_CALLBACK}$",
    )
    buy_flow_handler = CallbackQueryHandler(
        edit_buy_flow_fallback,
        pattern=r"^buy:(choose|ccy:(EUR|USD)|cat:(EUR|USD):\d+)$",
    )
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(edit_entry, pattern=r"^offer:edit:\d+$"),
        ],
        states={
            EDIT_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_amount),
            ],
            EDIT_CURRENCY: [
                CallbackQueryHandler(
                    edit_currency_chosen,
                    pattern=r"^edit:ccy:(EUR|USD)$",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_currency_reminder),
            ],
            EDIT_DESCRIPTION: [
                CallbackQueryHandler(edit_description_skip, pattern=r"^edit:desc:skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_receive_description),
                MessageHandler(~filters.COMMAND, edit_description_reminder),
            ],
            EDIT_PAYMENT: [
                CallbackQueryHandler(edit_payment_done, pattern=r"^edit:pay:done$"),
                CallbackQueryHandler(edit_payment_toggle, pattern=_EDIT_PAYMENT_TOGGLE_PATTERN),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_payment_reminder),
                MessageHandler(~filters.COMMAND, edit_payment_reminder),
            ],
            EDIT_CONFIRM: [
                CallbackQueryHandler(
                    edit_submit_or_abort,
                    pattern=r"^edit:(submit|abort)$",
                ),
                MessageHandler(filters.TEXT & ~filters.COMMAND, edit_confirm_reminder),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", edit_conversation_cancel),
            menu_main_handler,
            buy_flow_handler,
        ],
        name="edit_flow",
    )
