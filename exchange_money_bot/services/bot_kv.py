from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from exchange_money_bot.models import BotKv


async def get_value(session: AsyncSession, key: str) -> Optional[str]:
    result = await session.execute(select(BotKv).where(BotKv.key == key))
    row = result.scalar_one_or_none()
    return row.value if row is not None else None


async def set_value(session: AsyncSession, key: str, value: Optional[str]) -> None:
    result = await session.execute(select(BotKv).where(BotKv.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        session.add(BotKv(key=key, value=value))
    else:
        row.value = value
    await session.commit()
