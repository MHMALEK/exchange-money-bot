from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: Optional[str] = None
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    """Async SQLAlchemy URL, e.g. postgresql+asyncpg://... or sqlite+aiosqlite:///./data/app.db"""

    api_base_url: Optional[str] = None
    """If set, the bot pings the API after upsert (optional loose coupling)."""

    start_button_1_text: str = "قصد فروش ارز و دریافت ریال دارم"
    start_button_2_text: str = "قصد خرید ارز و پرداخت ریال دارم"
    start_button_1_reply: str = (
        "شما گزینهٔ «فروش ارز و دریافت ریال» را انتخاب کردید. "
        "به‌زودی ادامهٔ فرآیند را اینجا اضافه می‌کنیم."
    )
    # Buyer flow shows the live offer list in the bot; this env override is unused.
    start_button_2_reply: str = ""

    buyer_catalog_page_size: int = Field(default=20, ge=1, le=30)
    """Offers per catalog page. Telegram allows ~100 inline buttons; 20 rows + nav + back stays safe."""

    buyer_show_irr_rates: bool = True
    """Show approximate USD/EUR to IRR on buyer screens (fetched from public JSON)."""

    buyer_irr_rates_ttl_seconds: int = Field(default=120, ge=30, le=3600)
    """Cache TTL for fiat IRR snapshot (seconds)."""

    buyer_irr_rates_usd_json_url: Optional[str] = None
    buyer_irr_rates_eur_json_url: Optional[str] = None
    """Override JSON URLs; defaults use margani/pricedb GitHub raw (tgju)."""


settings = Settings()
