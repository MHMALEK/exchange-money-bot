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
    """Required for production: channel where sell offers are posted. Bot must be admin. Not used for auth."""

    telegram_membership_channel_id: Optional[str] = None
    """Optional auth: user must be a member of this channel when the gate is active (see membership_gate_active)."""

    telegram_membership_group_id: Optional[str] = None
    """Optional auth: user must be a member of this group/supergroup when the gate is active."""

    telegram_disable_membership_gate: bool = False
    """If True, skip auth checks (local/dev only)."""

    telegram_channel_invite_url: Optional[str] = None
    """https://t.me/… for «open listings» / join hints tied to the listings channel."""

    telegram_membership_group_invite_url: Optional[str] = None
    """Optional invite link for the auth group join button."""

    irr_rates_ttl_seconds: int = 300
    """Cache TTL for USD/EUR→rial JSON snapshots (see irr_fiat_rates)."""

    irr_usd_json_url: Optional[str] = None
    """Override USD/RL JSON URL; default is margani/pricedb TGJU mirror."""

    irr_eur_json_url: Optional[str] = None
    """Override EUR JSON URL; default is margani/pricedb TGJU mirror."""

    def effective_listings_channel_id(self) -> Optional[str]:
        """Channel used only for posting/editing listings and listings CTA URLs."""
        s = (self.telegram_listings_channel_id or "").strip()
        return s or None

    def effective_auth_channel_id(self) -> Optional[str]:
        """Optional Telegram channel/superchannel id for membership auth (not listings)."""
        s = (self.telegram_membership_channel_id or "").strip()
        return s or None

    def effective_auth_group_id(self) -> Optional[str]:
        s = (self.telegram_membership_group_id or "").strip()
        return s or None

    def membership_gate_active(self) -> bool:
        """Auth required only when at least one auth chat is configured (and gate not disabled)."""
        if self.telegram_disable_membership_gate:
            return False
        return bool(self.effective_auth_channel_id()) or bool(self.effective_auth_group_id())

    def effective_listings_channel_open_url(self) -> Optional[str]:
        """Static URL for listings: explicit invite, or https://t.me/name if listings id is @name."""
        if self.telegram_channel_invite_url:
            s = self.telegram_channel_invite_url.strip()
            if s:
                return s
        cid = (self.effective_listings_channel_id() or "").strip()
        if cid.startswith("@"):
            u = cid[1:].strip()
            if u:
                return f"https://t.me/{u}"
        return None


settings = Settings()
