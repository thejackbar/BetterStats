from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://cricket:cricket@db/betterstats"
    sync_database_url: str = "postgresql://cricket:cricket@db/betterstats"
    secret_key: str = "changeme-secret-key-32-chars-min"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 30  # 30 days
    cookie_secure: bool = True  # set False in local dev
    playhq_base_url: str = "https://grassrootsapiproxy.cricket.com.au"
    playhq_api_key: str = ""
    anthropic_api_key: str = ""
    cors_origins: str = "http://localhost:3000"

    # ─── BetterComms — outbound email (part of the BetterAdmin module) ─────────
    # Provider-pluggable so the platform runs zero-cost on a provider's free tier
    # and can switch later with no code change. "console" only logs (the dev
    # default — never sends). Going live = pick a provider, set the API key, and
    # verify the sending domain's SPF/DKIM/DMARC so mail isn't flagged as spam.
    #   brevo  — free 300 emails/day (~9k/mo), best free burst volume
    #   resend — free 3k/mo (100/day), cleanest API
    email_provider: str = "console"  # console | brevo | resend
    email_api_key: str = ""
    email_from_address: str = "noreply@betterstats.cricket"
    email_from_name: str = "BetterStats"
    email_reply_to: str = ""  # optional global default; per-club reply-to overrides
    # Public origin used to build the (mandatory) one-click unsubscribe link.
    # nginx strips the /api prefix, so the public route resolves at
    # {public_base_url}/api/public/comms/unsubscribe/{token}.
    public_base_url: str = "https://betterstats.cricket"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
