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
    # From should be on a domain with SPF/DKIM/DMARC set up so mail isn't flagged
    # as spam. Set those records up on bettersports.com.au (the From domain), or
    # override the address with EMAIL_FROM_ADDRESS in the server .env.
    # email_provider defaults to console, so nothing sends until a provider is set.
    email_from_address: str = "cricket@bettersports.com.au"
    email_from_name: str = "BetterCricket"
    email_reply_to: str = "cricket@bettersports.com.au"  # global default; per-club reply-to overrides
    # Public origin used to build the (mandatory) one-click unsubscribe link.
    # nginx strips the /api prefix, so the public route resolves at
    # {public_base_url}/api/public/comms/unsubscribe/{token}.
    public_base_url: str = "https://betterat.cricket"
    # SMTP (used when email_provider == "smtp"). SES example:
    #   smtp_host = email-smtp.ap-southeast-2.amazonaws.com  smtp_port = 587
    # Port 465 → implicit TLS; anything else → STARTTLS.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # ─── BetterMerch — Square POS integration (canteen/bar stock + sales) ──────
    # A club connects its own Square account via OAuth. Register ONE Square
    # application (developer.squareup.com), then set the application ID + secret
    # here and add the redirect URL (square_oauth_redirect below) to the app's
    # OAuth settings. Blank app id/secret = the Square page shows "not configured"
    # and nothing connects. square_api_version is optional — left blank, Square
    # uses the application's pinned default version.
    square_app_id: str = ""
    square_app_secret: str = ""
    square_environment: str = "production"  # 'sandbox' | 'production'
    square_api_version: str = ""

    # ─── Marketing club directory crawl (BetterCricket outreach, super-admin) ──
    # Walks the CA/grassroots org graph to build the national club list for our
    # own outreach. Politeness is deliberate: low concurrency + a jittered delay
    # between requests + a nightly cap, run off-peak, so we stay a quiet API
    # citizen. Disabled by default — the scheduler only runs the nightly batch
    # when marketing_crawl_enabled is true (flip it in the server .env once the
    # tables exist and you want collection to begin).
    marketing_crawl_enabled: bool = False
    marketing_crawl_nightly_limit: int = 300  # max clubs association-enriched per nightly batch
    # Per-request gap (jittered, applied before every PlayHQ call). 15-40s reads as
    # organic browsing rather than a scraper; see docs/marketing-club-directory.md.
    marketing_crawl_min_delay: float = 15.0   # min seconds between requests
    marketing_crawl_max_delay: float = 40.0   # max seconds between requests (jitter)
    # Continuous mode: a long-lived background runner that walks the whole backfill
    # within a daily active window, with occasional longer breaks, instead of one
    # capped nightly batch. Opt-in; when on, the nightly cron is skipped.
    marketing_crawl_continuous: bool = False
    marketing_crawl_tz: str = "Australia/Perth"      # window timezone
    marketing_crawl_window_start: str = "04:30"      # active window start (HH:MM)
    marketing_crawl_window_end: str = "23:30"        # active window end (HH:MM, same day)
    marketing_crawl_break_after_min: int = 30        # take a long break after this many clubs…
    marketing_crawl_break_after_max: int = 60        # …to this many (random)
    marketing_crawl_break_min: float = 120.0         # long break length, min seconds (2 min)
    marketing_crawl_break_max: float = 180.0         # long break length, max seconds (3 min)
    marketing_crawl_refresh_daemon: bool = True      # after backfill, re-discover daily for new clubs
    # PlayHQ public discovery endpoints (no API key — read the same as playhq.com).
    # Search enumerates every cricket club + its committee; the main graph maps a
    # club to the association(s) it plays in (needs the tenant header below).
    playhq_search_url: str = "https://search.playhq.com/graphql"
    playhq_graph_url: str = "https://api.playhq.com/graphql"
    playhq_tenant: str = "cricket-australia"
    # Org that owns the outreach campaigns in BetterComms (export target). Set to
    # the platform marketing org's slug; blank = the export endpoint requires an
    # explicit organisation_id. Lets BetterCricket reuse the per-club comms
    # pipeline (and a separate SES-verified sending domain) for its own sends.
    marketing_outreach_org_slug: str = ""

    # BetterComms — SES inbound event webhook (SNS → /public/ses/events). Verify
    # the SNS message signature by default; the suppression list is forgeable
    # otherwise. An optional shared token on the path adds defence in depth.
    ses_sns_verify_signatures: bool = True
    ses_event_token: str = ""

    # BetterComms — Amazon SES sending provider (SESv2 API, SigV4-signed). Set
    # email_provider=ses to use it. Per-club From sits on the verified per-silo
    # domains with a per-club local-part (no per-club AWS setup); the
    # configuration set routes events to the webhook and isolates reputation.
    ses_region: str = "ap-southeast-2"            # Sydney — closest AU region
    ses_access_key_id: str = ""
    ses_secret_access_key: str = ""
    ses_configuration_set: str = ""               # campaign stream (carries the event destination)
    ses_configuration_set_transactional: str = ""  # transactional stream, kept apart
    ses_club_domain: str = "betteradmin-comms.work"
    ses_marketing_domain: str = "betteratcricket-comms.work"

    # ─── Twenty CRM integration (super-admin GTM workspace) ───────────────────
    # Self-hosted Twenty instance that holds the BetterCricket sales/CRM model.
    # The export pushes the *targeted subset* of the Clubs Directory (filtered
    # clubs + their officers) into Twenty as Companies/People/Associations.
    # Blank url/key = the export endpoint reports "not configured" and does
    # nothing. The model itself is built by app/scripts/bootstrap_twenty.py;
    # these drive the ongoing record sync (twenty_client / twenty_sync).
    twenty_api_url: str = ""   # e.g. https://twenty.betterat.cricket (the SERVER_URL)
    twenty_api_key: str = ""   # a workspace API key with record write

    @property
    def twenty_configured(self) -> bool:
        return bool(self.twenty_api_url and self.twenty_api_key)

    @property
    def square_api_base(self) -> str:
        return (
            "https://connect.squareupsandbox.com"
            if self.square_environment == "sandbox"
            else "https://connect.squareup.com"
        )

    @property
    def square_oauth_redirect(self) -> str:
        # nginx strips the /api prefix, so this resolves at the public callback.
        return f"{self.public_base_url}/api/public/square/callback"

    @property
    def square_configured(self) -> bool:
        return bool(self.square_app_id and self.square_app_secret)

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_file = ".env"


settings = Settings()
