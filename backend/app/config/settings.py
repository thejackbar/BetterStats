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
    # email_provider defaults to console, so nothing sends until a provider is set.
    # A dedicated system-notifications identity, deliberately separate from the
    # human-monitored support inbox (email_reply_to below) — system mail (e.g.
    # the self-serve trial OTP) sends FROM here, but replies still land in the
    # real inbox. On betteratcricket-comms.work (== ses_marketing_domain below),
    # already a verified SES domain — chosen specifically to avoid new SES/DNS
    # setup, unlike bettersports.com.au which isn't verified in SES.
    email_from_address: str = "notifications@betteratcricket-comms.work"
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
    # Config-set-by-context (Jun 2026): a normal club's member email sends on the
    # transactional stream; BetterCricket's own cold outreach sends on the campaign
    # stream. Both config sets carry an SNS event destination so bounces/complaints
    # feed the suppression list + breaker either way. See _config_set_for in comms.

    # ─── BetterComms — SES per-club tenants (multi-tenancy) ────────────────────
    # Each club is an SES tenant so its sending reputation is isolated and can be
    # paused independently. Tenants are auto-provisioned (services/ses_tenants) via
    # a SEPARATE admin credential (send stays on ses_access_key_id). Provisioning
    # associates the shared sending identity + the club's context config set with
    # the tenant. Sending "as" the tenant is gated behind ses_tenant_sends_enabled
    # so it can be verified before it touches live sends.
    ses_account_id: str = ""                       # AWS account id, for building resource ARNs
    ses_provision_access_key_id: str = ""          # provisioning-only IAM key (ses:CreateTenant …)
    ses_provision_secret_access_key: str = ""
    ses_reputation_policy: str = ""                # optional named reputation policy (blank = SES default)
    ses_marketing_tenant_name: str = "bettercricket-marketing"  # fixed tenant for the outreach org
    ses_tenant_sends_enabled: bool = False         # include the tenant on each send (flip after verifying)

    # ─── BetterComms — send-rate + quota guards (keep us inside the AWS grant) ──
    # AWS granted this account 14 messages/second and 50,000/day. We pace every
    # send through a process-global token bucket set a touch under the ceiling, so
    # ALL campaigns (every club + the marketing org + any future transactional
    # send) share one account-wide rate. Single uvicorn worker ⇒ the in-process
    # bucket bounds the whole account; if the box ever runs multiple workers,
    # divide ses_max_send_rate by the worker count (or move the bucket to Redis).
    # AWS's granted maximum send rate (per second). Stored here as the seed
    # default; a super admin manages the live value from the BetterComms limits
    # page (platform_settings), so an AWS increase is a settings change, not a
    # redeploy. Raise this only when AWS raises your account's rate.
    ses_aws_max_send_rate: int = 14
    # Our pacing rate — always kept strictly BELOW the AWS ceiling. Seed default;
    # the live value is the super-admin-managed platform setting.
    ses_max_send_rate: int = 13                    # per second, under AWS's 14/s
    # Daily send quota. Both values are super-admin managed from the BetterComms
    # limits page (platform_settings); these are the seed defaults.
    #   ses_daily_quota      — AWS's granted daily ceiling (50,000 today).
    #   ses_daily_send_limit — the practical daily max we hold ourselves to
    #                          (e.g. 40,000), always ≤ the AWS ceiling. Overflow
    #                          past this defers to the next day.
    ses_daily_quota: int = 50000
    ses_daily_send_limit: int = 45000
    ses_daily_quota_headroom: int = 5000           # deprecated (superseded by ses_daily_send_limit)

    # ─── BetterComms — per-club sending tiers (AWS-sandbox-style onboarding) ────
    # A new club starts in 'sandbox' with a low daily cap; once it has sent
    # cleanly it requests a lift to 'production' (a super admin approves). A club
    # whose bounce/complaint rate crosses the AWS danger line is auto-moved to
    # 'suspended' (cap 0) until a super admin reinstates it. These are the global
    # defaults; a club can carry its own per-tier override in
    # organisations.comms_sandbox_cap / comms_production_cap (set by a super admin
    # when onboarding the club on BetterAdmin), which wins over these.
    comms_sandbox_daily_cap: int = 50
    comms_production_daily_cap: int = 2000
    # A per-club monthly ceiling on top of the daily cap — a second guard rail so a
    # club can't churn through a huge volume across a month even while staying under
    # the daily cap each day. Single default for every club; a club can carry its
    # own override in organisations.comms_monthly_cap. 0/None on both = no monthly
    # limit. Counted over a rolling 30-day window.
    comms_monthly_send_default: int = 10000
    # Bounce/complaint circuit breaker. AWS reviews accounts over ~5% bounce or
    # ~0.1% complaint; we trip below that to stay safe, but only once a club has
    # sent enough to judge (min_sample) over the trailing window (days).
    comms_bounce_rate_threshold: float = 0.05
    comms_complaint_rate_threshold: float = 0.001
    comms_metrics_window_days: int = 30
    comms_metrics_min_sample: int = 50

    # ─── Twenty CRM integration (super-admin GTM workspace) ───────────────────
    # Self-hosted Twenty instance that holds the BetterCricket sales/CRM model.
    # The export pushes the *targeted subset* of the Clubs Directory (filtered
    # clubs + their officers) into Twenty as Companies/People/Associations.
    # Blank url/key = the export endpoint reports "not configured" and does
    # nothing. The model itself is built by app/scripts/bootstrap_twenty.py;
    # these drive the ongoing record sync (twenty_client / twenty_sync).
    twenty_api_url: str = ""   # e.g. https://twenty.betterat.cricket (the SERVER_URL)
    twenty_api_key: str = ""   # a workspace API key with record write

    # ─── Pipeline target gauge (routers/pipeline_gauge.py) ─────────────────────
    # HTTP Basic Auth for the superadmin-only dashboard-gauge widget. Blank =
    # every request 500s (fails closed) rather than serving the page open.
    gauge_username: str = ""
    gauge_password: str = ""
    # Shared secret for the INBOUND Twenty webhook (POST /webhooks/twenty). When set,
    # a Twenty record-update webhook can raise a module trial request back in
    # BetterCricket (source=twenty). Blank = the endpoint is a no-op (returns 200 and
    # ignores the payload), so it's safe to leave unconfigured.
    twenty_webhook_secret: str = ""
    # Client-side request ceiling (requests/min) the export paces under, to stay below
    # Twenty's server rate limit (default 100/60s). Raise this in lockstep if you raise
    # Twenty's own API_RATE_LIMITING_* limit, else it becomes the bottleneck.
    twenty_rate_per_min: int = 90
    # Optional Twenty workspaceMember id to assign auto-created Tasks to (the
    # back-office follow-up owner). Blank = Tasks are created unassigned. Find the id
    # in Twenty under Settings > Members, or via GET /rest/workspaceMembers.
    twenty_task_assignee_id: str = ""

    # ─── Meta Ads dashboard (super-admin HQ — BetterCricket's own ad spend) ────
    # System-user token (ads_read + read_insights) for the Meta Marketing API,
    # read-only against one campaign in the platform's own ad account. Blank
    # token = the HQ page shows a friendly "configure token" state, not a crash.
    # See docs handed to Jack for how to generate the token (Business Settings >
    # Users > System users > Assign assets > Generate new token).
    meta_access_token: str = ""
    meta_ad_account_id: str = "1030195476512456"
    meta_campaign_id: str = "120249237210710121"
    meta_api_version: str = "v21.0"

    @property
    def meta_ads_configured(self) -> bool:
        return bool(self.meta_access_token and self.meta_ad_account_id)

    # ─── Meta Conversions API (CAPI) — server-side event redundancy ────────────
    # Sends key events (Lead first) to Meta server-side alongside the browser
    # pixel, sharing an event_id so Meta dedupes the pair into one event. Catches
    # leads the browser pixel misses (ad blockers, iOS ITP, page-load failures).
    # Blank token = CAPI calls are skipped (logged, never blocks the form — the
    # browser pixel keeps working either way). This token is DIFFERENT from
    # meta_access_token above (that one is ads_read for the HQ dashboard; this one
    # needs write access to the dataset's events). Generate via Events Manager >
    # BetterCricket Web dataset > Settings > Conversions API > Generate access
    # token (or the existing Conversions API System User). NEVER commit it.
    meta_dataset_id: str = "1317878090534903"
    meta_capi_access_token: str = ""
    meta_graph_version: str = "v21.0"
    meta_test_event_code: str = ""  # Events Manager > Test Events; leave blank in prod

    @property
    def meta_capi_configured(self) -> bool:
        return bool(self.meta_dataset_id and self.meta_capi_access_token)

    @property
    def twenty_configured(self) -> bool:
        return bool(self.twenty_api_url and self.twenty_api_key)

    @property
    def twenty_webhook_configured(self) -> bool:
        return bool(self.twenty_webhook_secret)

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
