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

    # ─── KlubPro → BetterStats migration tooling (super-admin onboarding only) ──
    # Connection to the *separate* KlubPro Postgres holding the staged migration
    # data (the `klubpro_migration` schema). Empty in normal operation — the
    # migration admin page returns a clear "not configured" error until an
    # operator sets it. On the box both DBs live in the same Docker project, so
    # this resolves over the internal network, e.g.:
    #   postgresql+asyncpg://klubpro_admin:<pw>@klubpro-postgres:5432/klubpro
    # NEVER hardcode the password — supply it via the .env / Docker secret.
    klubpro_database_url: str = ""

    # ─── BetterComms — outbound email (part of the BetterAdmin module) ─────────
    # Provider-pluggable so the platform runs zero-cost on a provider's free tier
    # and can switch later with no code change. "console" only logs (the dev
    # default — never sends). Going live = pick a provider, set the API key, and
    # verify the sending domain's SPF/DKIM/DMARC so mail isn't flagged as spam.
    #   brevo  — free 300 emails/day (~9k/mo), best free burst volume
    #   resend — free 3k/mo (100/day), cleanest API
    #   smtp   — any SMTP host: Amazon SES (high volume, ~$0.10/1k, no daily cap),
    #            a self-hosted MTA (Postal/Listmonk), or a club's own Workspace.
    email_provider: str = "console"  # console | brevo | resend | smtp
    email_api_key: str = ""
    email_from_address: str = "noreply@betterstats.cricket"
    email_from_name: str = "BetterStats"
    email_reply_to: str = ""  # optional global default; per-club reply-to overrides
    # Public origin used to build the (mandatory) one-click unsubscribe link.
    # nginx strips the /api prefix, so the public route resolves at
    # {public_base_url}/api/public/comms/unsubscribe/{token}.
    public_base_url: str = "https://betterstats.cricket"
    # SMTP (used when email_provider == "smtp"). SES example:
    #   smtp_host = email-smtp.ap-southeast-2.amazonaws.com  smtp_port = 587
    # Port 465 → implicit TLS; anything else → STARTTLS.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
