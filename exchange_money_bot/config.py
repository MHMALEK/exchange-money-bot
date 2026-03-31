from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    telegram_bot_token: Optional[str] = None
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    """Async SQLAlchemy URL, e.g. postgresql+asyncpg://... or sqlite+aiosqlite:///./data/app.db"""

    api_base_url: Optional[str] = None
    """If set, the bot pings the API after upsert (optional loose coupling)."""

    telegram_listings_channel_id: Optional[str] = None
    """Channel chat id (@username or -100…) where new sell offers are posted. Bot must be admin."""

    telegram_membership_channel_id: Optional[str] = None
    """Optional override for membership checks; defaults to listings channel when unset."""

    telegram_disable_membership_gate: bool = False
    """If True, skip channel membership checks (local/dev only). When False, a configured listings or membership channel id enables the gate."""

    telegram_channel_invite_url: Optional[str] = None
    """https://t.me/… link shown on «join channel» and «open listings» prompts."""

    irr_rates_ttl_seconds: int = 300
    """Cache TTL for USD/EUR→rial JSON snapshots (see irr_fiat_rates)."""

    irr_usd_json_url: Optional[str] = None
    """Override USD/RL JSON URL; default is margani/pricedb TGJU mirror."""

    irr_eur_json_url: Optional[str] = None
    """Override EUR JSON URL; default is margani/pricedb TGJU mirror."""

    irr_channel_pin_enabled: bool = True
    """Post/edit a pinned USD/EUR→rial message in TELEGRAM_LISTINGS_CHANNEL_ID when set."""

    irr_channel_pin_interval_seconds: int = 600
    """How often to refresh the pinned channel rates message (background task)."""

    def effective_membership_channel_id(self) -> Optional[str]:
        return self.telegram_membership_channel_id or self.telegram_listings_channel_id

    def membership_gate_active(self) -> bool:
        if self.telegram_disable_membership_gate:
            return False
        return bool(self.effective_membership_channel_id())

    def effective_listings_channel_open_url(self) -> Optional[str]:
        """Public URL for «open channel» buttons: invite link, else https://t.me/name if id is @name."""
        if self.telegram_channel_invite_url:
            s = self.telegram_channel_invite_url.strip()
            if s:
                return s
        cid = (self.telegram_listings_channel_id or "").strip()
        if cid.startswith("@"):
            u = cid[1:].strip()
            if u:
                return f"https://t.me/{u}"
        return None


settings = Settings()
