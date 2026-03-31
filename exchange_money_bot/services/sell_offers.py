from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from exchange_money_bot.i18n import t
from exchange_money_bot.models import SellOffer

ALLOWED_CURRENCIES = frozenset({"EUR", "USD"})


@dataclass
class DeletedSellOfferSnapshot:
    """Row fields needed after an offer row is removed (e.g. channel strikethrough)."""

    amount: int
    currency: str
    seller_display_name: str
    telegram_username: Optional[str]
    telegram_id: int
    listings_channel_message_id: Optional[int]


def currency_label_fa(code: str) -> str:
    return t(f"currency.{code}", default=code)


async def count_public_sell_offers(
    session: AsyncSession,
    *,
    exclude_telegram_id: Optional[int] = None,
    currency: Optional[str] = None,
) -> int:
    stmt = select(func.count()).select_from(SellOffer)
    if exclude_telegram_id is not None:
        stmt = stmt.where(SellOffer.telegram_id != exclude_telegram_id)
    if currency is not None:
        if currency not in ALLOWED_CURRENCIES:
            raise ValueError(f"Invalid currency: {currency}")
        stmt = stmt.where(SellOffer.currency == currency)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def count_offers_by_telegram_and_currency(
    session: AsyncSession,
    telegram_id: int,
    currency: str,
) -> int:
    if currency not in ALLOWED_CURRENCIES:
        raise ValueError(f"Invalid currency: {currency}")
    stmt = select(func.count()).select_from(SellOffer).where(
        SellOffer.telegram_id == telegram_id,
        SellOffer.currency == currency,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def list_public_sell_offers(
    session: AsyncSession,
    *,
    exclude_telegram_id: Optional[int] = None,
    currency: Optional[str] = None,
    limit: int = 5,
    offset: int = 0,
) -> list[SellOffer]:
    stmt = select(SellOffer).order_by(SellOffer.created_at.desc())
    if exclude_telegram_id is not None:
        stmt = stmt.where(SellOffer.telegram_id != exclude_telegram_id)
    if currency is not None:
        if currency not in ALLOWED_CURRENCIES:
            raise ValueError(f"Invalid currency: {currency}")
        stmt = stmt.where(SellOffer.currency == currency)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_offers_for_user(session: AsyncSession, user_id: int) -> list[SellOffer]:
    result = await session.execute(
        select(SellOffer)
        .where(SellOffer.user_id == user_id)
        .order_by(SellOffer.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_offer_owned(
    session: AsyncSession, offer_id: int, user_id: int
) -> Optional[DeletedSellOfferSnapshot]:
    result = await session.execute(
        select(SellOffer).where(SellOffer.id == offer_id, SellOffer.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    snap = DeletedSellOfferSnapshot(
        amount=row.amount,
        currency=row.currency,
        seller_display_name=row.seller_display_name,
        telegram_username=row.telegram_username,
        telegram_id=row.telegram_id,
        listings_channel_message_id=row.listings_channel_message_id,
    )
    await session.delete(row)
    await session.commit()
    return snap


async def set_listings_channel_message_id(
    session: AsyncSession, offer_id: int, message_id: int
) -> None:
    result = await session.execute(select(SellOffer).where(SellOffer.id == offer_id))
    row = result.scalar_one_or_none()
    if row is None:
        return
    row.listings_channel_message_id = message_id
    await session.commit()


async def create_sell_offer(
    session: AsyncSession,
    *,
    user_id: int,
    telegram_id: int,
    telegram_username: Optional[str],
    seller_display_name: str,
    amount: int,
    currency: str,
) -> SellOffer:
    if currency not in ALLOWED_CURRENCIES:
        raise ValueError(f"Invalid currency: {currency}")
    if amount <= 0:
        raise ValueError("Amount must be positive")
    offer = SellOffer(
        user_id=user_id,
        telegram_id=telegram_id,
        telegram_username=telegram_username,
        seller_display_name=seller_display_name,
        amount=amount,
        currency=currency,
    )
    session.add(offer)
    await session.commit()
    await session.refresh(offer)
    return offer
