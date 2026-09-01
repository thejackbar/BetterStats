from sqlalchemy import (
    Column, Boolean, Integer, BigInteger, Numeric, Date, Text, ForeignKey,
    TIMESTAMP, JSON, UniqueConstraint, LargeBinary, Index, text
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.sql import func
import uuid

from app.config.settings import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=False,
    # See settings.db_pool_* for why the SQLAlchemy defaults (5+10) are too
    # small here. pool_pre_ping recovers a connection the DB/proxy dropped out
    # from under us (returns a live conn instead of a dead-socket error).
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
    pool_pre_ping=True,
)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session_maker() as session:
        yield session


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Not unique (migration 145) — format-validated only, deliberately allowed
    # to repeat across accounts. username remains the unique login credential.
    email = Column(Text, nullable=True)
    username = Column(Text, unique=True, nullable=True)
    password_hash = Column(Text)
    display_name = Column(Text, nullable=True)
    # First/last name + mobile: added for the self-serve trial registration
    # admin-details form (migration 135) — nullable, nothing else reads them yet.
    first_name = Column(Text, nullable=True)
    last_name = Column(Text, nullable=True)
    mobile_number = Column(Text, nullable=True)
    last_login_at = Column(TIMESTAMP(timezone=True), nullable=True)
    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(TIMESTAMP(timezone=True), nullable=True)
    last_notification_seen_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_seen_app_version = Column(Text, nullable=True)
    # Per-account UI preferences (migration 204) — a small namespaced JSON bag
    # so a super admin's UI choices survive across sessions and devices
    # (localStorage is per-browser only). First consumer: the CRM Sales
    # Pipeline stage filter buttons (namespace 'crm_stage_filters'). Read/
    # merged via GET/PATCH /club-admin/account/ui-prefs.
    ui_preferences = Column(JSONB, nullable=False, server_default="{}", default=dict)
    # Super admins (Better staff) manage every club, not just one. active_club_id
    # is the club they are currently "acting as" — every club-scoped request
    # resolves to it instead of their home membership club. NULL = act as the
    # membership club. Only honoured for super_admin memberships
    # (see auth._effective_club_id). ON DELETE SET NULL so deleting a club never
    # strands the staff account (migration 073).
    active_club_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True)
    # Club-user invite flow (migration 141): a user created via "Invite admin"
    # (routers/club_admin.py::create_club_user) with an email address gets
    # password_hash=NULL (there is genuinely no usable password yet — the
    # column has always been nullable, this is the first thing to rely on
    # that) plus this random urlsafe token, emailed as a set-your-password
    # link. Cleared the moment the invite is accepted (routers/auth.py). A
    # user invited without an email still gets a password set on the spot by
    # the inviting admin, same as before — these columns just stay NULL.
    invite_token = Column(Text, unique=True, nullable=True)
    invite_token_expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Admin-triggered "reset your password" email for an EXISTING club-user
    # account (migration 144, routers/club_admin.py::send_password_reset_link).
    # Distinct from invite_token above, which is only for a brand-new
    # account's first-ever password — that flow 404s once password_hash is
    # set, so an already-active admin needs its own token pair here.
    password_reset_token = Column(Text, unique=True, nullable=True)
    password_reset_token_expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # passive_deletes=True: club_memberships.user_id is ON DELETE CASCADE at the
    # DB level (confirmed live) and NOT NULL. Without this flag, deleting a User
    # via the ORM (routers/club_admin.py::delete_user's `await db.delete(user)`)
    # makes SQLAlchemy's unit-of-work try to manage the relationship itself —
    # load the membership row, then null out its user_id to disassociate it —
    # which Postgres rejects with a NOT NULL violation before the DELETE ever
    # gets a chance to rely on the DB's own CASCADE. This is why deleting a
    # club-admin user 500'd even after the club_memberships FK was confirmed
    # to cascade correctly: the ORM never let the database's rule apply.
    memberships = relationship("ClubMembership", back_populates="user", passive_deletes=True)


class SelfServeEmailVerification(Base):
    """A 4-digit email verification code issued for the self-serve trial
    registration flow (migration 136, Phase 6 — see
    docs/self-serve-trial-onboarding-plan.md). Only ``code_hash`` (bcrypt) is
    stored, never the plaintext code. Keyed by email, not by user (no user
    exists yet at this point in registration) — a fresh send sets
    ``superseded_at`` on any earlier unverified row for the same email so only
    the latest is ever valid.
    """
    __tablename__ = "self_serve_email_verifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, nullable=False)
    code_hash = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    verified_at = Column(TIMESTAMP(timezone=True), nullable=True)
    superseded_at = Column(TIMESTAMP(timezone=True), nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False, server_default="0")


class SelfServeAcknowledgement(Base):
    """Terms of Service / Privacy Policy acceptance for the
    self-serve trial registration flow (migration 137, Phase 7 — see
    docs/self-serve-trial-onboarding-plan.md). Keyed by email, same reasoning as
    SelfServeEmailVerification (no user/org exists yet). ``ip_hash`` mirrors
    login_attempts' privacy-conscious approach (truncated SHA-256, never the raw
    IP — see services/usage_tracker.hash_ip)."""
    __tablename__ = "self_serve_acknowledgements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, nullable=False)
    club_name = Column(Text, nullable=False)
    terms_version = Column(Text, nullable=False)
    privacy_version = Column(Text, nullable=False)
    accepted_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    ip_hash = Column(Text, nullable=True)
    user_agent = Column(Text, nullable=True)


class SelfServeIdempotencyKey(Base):
    """The safety rail around the self-serve trial registration's atomic
    registration transaction (migration 138 + 139, Phases 8-9 — see
    docs/self-serve-trial-onboarding-plan.md). The key itself is the primary
    key: a repeat submission with the same key is recognised (found here) and
    replayed rather than reprocessed, so a double-click, browser refresh, or
    network retry can't create duplicate clubs/users/trials. ``org_id``/
    ``user_id`` (migration 139) record what was actually created, so a replay
    can return it."""
    __tablename__ = "self_serve_idempotency_keys"

    idempotency_key = Column(Text, primary_key=True)
    email = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="validated")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    org_id = Column(UUID(as_uuid=True), nullable=True)
    user_id = Column(UUID(as_uuid=True), nullable=True)


class OnboardingWizardState(Base):
    """One row per club tracking its onboarding wizard progress (migration 140,
    Phase 15 — see docs/self-serve-trial-onboarding-plan.md). Scoped to the
    ORG, not a single user — onboarding is a property of the club, so a second
    admin invited later sees the same progress rather than starting over.

    ``dismissed_at`` is set whenever the admin closes the wizard; the wizard
    auto-opens again whenever it's unset, mirroring the notification bell's
    own ``last_notification_seen_at`` pattern. ``sync_steps_shown_at`` is the
    one-time trigger for Decision 11's "reopens automatically once sync
    completes" — it's stamped the first time the wizard is shown (auto or
    manual) after the sync-dependent steps (Import Historical Stats, Import
    Honours, Merge Grades) become available, so that reopen fires exactly
    once rather than on every subsequent page load."""
    __tablename__ = "onboarding_wizard_state"

    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"),
                             primary_key=True)
    completed_steps = Column(JSON, nullable=False, default=list)
    # Steps the admin explicitly skipped in the Setup Wizard (migration 157) —
    # "addressed but not done". Separate from completed_steps so existing
    # progress rows and consumers keep working untouched.
    skipped_steps = Column(JSON, nullable=False, default=list)
    # Steps the admin marked "doesn't apply" (migration 162) — e.g. Connect
    # Square for a club that doesn't use Square. Unlike a skip (parked,
    # still counts as to-do), a not-applicable step drops out of progress
    # counts entirely. Only steps flagged ``optional`` in the registry offer
    # it; auto-detection still beats it if the thing later exists.
    na_steps = Column(JSON, nullable=False, default=list)
    # Stamped the FIRST time POST /opened fires (migration 163) — i.e. the
    # admin actually landed on the wizard page at least once. Distinct from
    # this row's own existence: AdminLayout's /state poll (checked on every
    # admin page mount, to show/hide the SETUP GUIDE button + sidebar badge)
    # calls _get_or_create_state too, so a row can exist for a club that's
    # never opened the wizard itself. This column is the real "did they ever
    # look at it" signal the wizard-analytics page keys off.
    first_opened_at = Column(TIMESTAMP(timezone=True), nullable=True)
    dismissed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    sync_steps_shown_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class UserBookmark(Base):
    """A page an admin user has starred for quick access in the sidebar.

    Keyed to the user (not the club) — the admin routes are identical whatever
    club a super admin is acting as, so the same favourites follow them. ``path``
    is an internal route (e.g. ``/admin/players``); ``label`` is the display name
    captured when it was bookmarked. ``sort_order`` keeps the list stable
    (append-on-add for now; leaves room to reorder later). See migration 082.
    """
    __tablename__ = "user_bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "path", name="uq_user_bookmark_path"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    path = Column(Text, nullable=False)
    label = Column(Text, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False, server_default="0")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class Organisation(Base):
    __tablename__ = "organisations"

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    short_name = Column(Text)
    playhq_id = Column(Text, nullable=True)
    slug = Column(Text, unique=True, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    # Soft-delete (migration 143): a Super Admin "deleting" a club archives it
    # instead of destroying its data — reversible via POST .../restore. NULL =
    # not archived. Separate from is_active (an archived club's public site
    # should also be considered offline, but is_active itself is left alone so
    # restoring doesn't silently flip a state the admin didn't touch).
    archived_at = Column(TIMESTAMP(timezone=True), nullable=True)
    primary_color = Column(Text, default="#16c784", nullable=True)
    accent_color = Column(Text, default="#243352", nullable=True)
    logo_url = Column(Text, nullable=True)
    logo_data = Column(LargeBinary, nullable=True)
    logo_mime = Column(Text, nullable=True)
    hero_image_url = Column(Text, nullable=True)
    theme_mode = Column(Text, default="auto", nullable=True)
    theme_config = Column(JSONB, nullable=True)
    # Public-site typography (migration 215) — see app/services/fonts.py and
    # frontend/src/lib/theme.js. Two independent roles (display heading / body
    # text), each either unset (app default), a curated built-in preset, or an
    # uploaded font file. font_config carries the per-role selection
    # (`{"display": {"source": "upload"|"preset", "preset": ..., "family": ..., "v": ...}, "body": {...}}`);
    # the uploaded bytes live in their own columns, mirroring logo_data/logo_mime.
    font_config = Column(JSONB, nullable=True)
    font_display_data = Column(LargeBinary, nullable=True)
    font_display_mime = Column(Text, nullable=True)
    font_body_data = Column(LargeBinary, nullable=True)
    font_body_mime = Column(Text, nullable=True)
    # Third role: numbers/stats — maps onto the app's `font-mono` styling used
    # throughout stat figures and tabular data (migration 216).
    font_mono_data = Column(LargeBinary, nullable=True)
    font_mono_mime = Column(Text, nullable=True)
    contact_email = Column(Text, nullable=True)
    # The club's own history, shown under its name on the public dashboard
    # (migration 227). `established_year` is a plain year — a club writes
    # "Est. 1889" and rarely holds the founding day. `previous_names` is an
    # ordered list of {"name", "from_year", "to_year"}, oldest first, with
    # both years optional: a club often knows it used to be called something
    # else without knowing when that stopped.
    established_year = Column(Integer, nullable=True)
    previous_names = Column(JSONB, nullable=True)
    # The competitions the club has played in (migration 262) — the same
    # {"name", "from_year", "to_year"} shape as previous_names, and validated
    # by the same rules. Kept as its own column rather than folded into the
    # names list: a club changes competition without changing its name far
    # more often than the other way round.
    competitions = Column(JSONB, nullable=True)
    player_name_format = Column(Text, default="last_first", nullable=True)
    # BetterSelect: a player is "dormant" (hidden from default selection) if they
    # haven't appeared within this many months. Also bounds team squad
    # suggestions. Default 24 (migration 048).
    dormancy_months = Column(Integer, nullable=False, server_default="24", default=24)
    default_team_size = Column(Integer, nullable=False, server_default="11", default=11)  # 0 = no limit
    # BetterSelect: show a player's age beside their name on the selection
    # board and the roster (migration 269). Default off, so no club starts
    # showing dates of birth to its selectors because of an upgrade.
    # select_show_age_under is NULL for every player, or an age to show it
    # only BELOW — the case this was built for, a coach wanting the juniors'
    # ages in front of them when deciding bowling workloads. Applied
    # server-side through services/player_age.visible_age, so a restricted
    # club never sends an adult's age to a browser at all.
    select_show_age = Column(Boolean, nullable=False, server_default="false", default=False)
    select_show_age_under = Column(Integer, nullable=True)
    # Club-wide defaults for BetterSelect's association rules (migration 271) —
    # chiefly how the competition measures age, since one association counts it
    # as at 1 September and the next as at 1 January. NULL = the platform
    # default. Written and read only through services/selection_rules.py.
    selection_rules_config = Column(JSONB, nullable=True)
    # Public player-profile attribute visibility (per-club). Overseas is always
    # shown; these gate the descriptive attributes on the public /players/:id
    # profile so each club chooses how much of a player's profile is public
    # (migration 054). Default off — opt-in.
    public_show_role = Column(Boolean, nullable=False, server_default="false", default=False)
    public_show_batting = Column(Boolean, nullable=False, server_default="false", default=False)
    public_show_bowling = Column(Boolean, nullable=False, server_default="false", default=False)
    public_show_opening = Column(Boolean, nullable=False, server_default="false", default=False)
    public_show_gender = Column(Boolean, nullable=False, server_default="false", default=False)
    # A fill-in (borrowed player) or CA-redacted junior's runs/wickets always
    # show on the match-day batting/bowling card, no toggle. Whether their
    # name/contribution also shows in the partnerships and fielding cards on
    # that same scorecard is the club's own call — default on for parity with
    # batting/bowling; a club can switch it off if it would rather those two
    # cards only ever name registered players (migration 147). Never affects
    # all-time club records — those are already scoped to a `players` join
    # that a NULL player_id naturally never matches.
    include_fill_ins_in_stats = Column(Boolean, nullable=False, server_default="true", default=True)
    # Show the club crest beside the club name in public page headers
    # (migration 226). Opt-in: a club that has uploaded a logo used to see it
    # only in the menu bar, and turning this on for everyone would change every
    # existing club's public site without anyone asking for it.
    public_header_logo = Column(Boolean, nullable=False, server_default="false", default=False)
    # Which grade categories count towards this club's stats by default — a
    # JSONB list of grade_labels.GRADE_CATEGORIES keys (migration 228). NULL
    # means no club preference, and the platform default applies: everything
    # except junior. Read through services/grade_scope.py, never directly.
    stats_grade_categories = Column(JSONB, nullable=True)
    # When the club default would leave out every grade category a player has
    # actually played, show them the categories they did play rather than a page
    # of zeroes (migration 229). Only ever affects the default, never an explicit
    # pick. See services/grade_scope.resolve_scope_for_player.
    stats_auto_show_played_grades = Column(Boolean, nullable=False, server_default="true", default=True)
    # Fewest COVERED innings/spells a player needs before a strike rate or an
    # economy is published for them on a leaderboard (migration 282). Covered
    # means the innings carries a ball count that can carry its runs — see
    # services/rate_coverage.py. NULL means no club preference and the platform
    # default applies, which is 0: nothing has ever qualified these boards, and
    # switching a number on for every club would drop players off their own
    # leaderboard without anybody choosing it. Read through
    # services/stats_display.py, never directly.
    stats_min_rate_innings = Column(Integer, nullable=True)
    stats_min_rate_spells = Column(Integer, nullable=True)
    # ─── AFL — optional public leaderboard categories (migration 217) ────────
    # Games and Goals are always shown; a club decides whether Best on Ground
    # and its two vote-tally leaderboards (Club/Competition Best & Fairest —
    # only ever populated via a historical Import Stats upload, never synced)
    # clutter the public leaderboard tab list or not. Default on (opt-out),
    # preserving what every club already saw before this toggle existed.
    public_show_bog_leaderboard = Column(Boolean, nullable=False, server_default="true", default=True)
    public_show_club_bf_leaderboard = Column(Boolean, nullable=False, server_default="true", default=True)
    public_show_comp_bf_leaderboard = Column(Boolean, nullable=False, server_default="true", default=True)
    # Who may open a committee document the club UPLOADED (migration 218). True
    # (the default) = whoever uploaded it, plus committee members holding an
    # Office Bearer role, plus the club's Main Admin. False = any committee
    # member who can reach the register. Link-only documents are unaffected —
    # a URL we do not host cannot be gated by us.
    committee_docs_office_bearer_only = Column(Boolean, nullable=False, server_default="true", default=True)
    # The month a club's diary year starts, 1-12 (migration 221). 7 = July, the
    # Australian cricket-season convention and the behaviour before this existed.
    diary_start_month = Column(Integer, nullable=False, server_default="7", default=7)
    # ─── Better ecosystem entitlements (migration 056) ───────────────────────
    # module_overrides is the explicit list of modules a club holds, and the
    # single source of truth for entitlement (see app/auth/modules.py). Core
    # (BetterStats) is always on for every club and is not a gateable module.
    # `tier` is the retired Good/Better/Best plan field, kept for history only
    # (migration 080 backfilled module_overrides from it); it is no longer read.
    tier = Column(Text, nullable=False, server_default="good", default="good")
    module_overrides = Column(JSONB, nullable=False, server_default="[]", default=list)
    # ─── Subscription state (migration 057) ──────────────────────────────────
    # Drives entitlement now (status gates module access) and reflects the
    # manual-invoicing state in-app ahead of Stripe. Statuses: active/trial/
    # past_due keep modules live; paused/cancelled fall back to Core only.
    subscription_status = Column(Text, nullable=False, server_default="active", default="active")
    renewal_date = Column(Date, nullable=True)
    billing_cycle = Column(Text, nullable=True)  # 'monthly' | 'annual' | None
    # ─── Stripe Checkout (migration 150) ──────────────────────────────────────
    # Set by the /public/stripe/webhook handler once a Primary Admin completes a
    # real subscription checkout — see services/stripe_billing.py. NULL until a
    # club has ever paid through Stripe. One Stripe Customer/Subscription per
    # club, covering every module it holds via Stripe (subscription items), not
    # one Stripe subscription per module.
    stripe_customer_id = Column(Text, nullable=True)
    stripe_subscription_id = Column(Text, nullable=True)
    # Per-club override of platform_settings.billing_checkout_enabled (migration
    # 151) — lets a super admin let ONE club's Primary Admin through the real
    # Stripe Checkout flow (for testing) while the platform default stays off
    # for everyone else. NULL = follow the platform default; True/False force
    # it either way for this club regardless of the platform default. See
    # services/platform_settings.billing_checkout_enabled_for_org.
    billing_checkout_override = Column(Boolean, nullable=True)
    # Per-club override of platform_settings.member_portal_enabled (migration 178)
    # — same NULL/True/False shape as billing_checkout_override above, so a
    # super admin can switch the member self-service portal on for one test
    # club while it stays invisible to every other club admin. See
    # services/platform_settings.member_portal_enabled_for_org.
    member_portal_override = Column(Boolean, nullable=True)
    # Per-club override of platform_settings.merch_storefront_enabled
    # (migration 179) — same shape as member_portal_override above.
    merch_storefront_override = Column(Boolean, nullable=True)
    # ─── Stripe Connect — club-to-member fee payments (migration 178) ─────────
    # A SEPARATE Stripe integration from stripe_customer_id/stripe_subscription_id
    # above (which is BetterCricket's OWN platform billing, one Stripe account
    # for the whole platform). Here each club gets its OWN Stripe Express
    # connected account so a member's fee payment lands directly in the club's
    # bank account, not BetterCricket's — see services/stripe_connect_client.py.
    stripe_connect_account_id = Column(Text, nullable=True)
    stripe_connect_details_submitted = Column(Boolean, nullable=False, server_default="false", default=False)
    stripe_connect_charges_enabled = Column(Boolean, nullable=False, server_default="false", default=False)
    stripe_connect_payouts_enabled = Column(Boolean, nullable=False, server_default="false", default=False)
    # Club address (migration 158) — resolved at self-serve registration
    # (routers/self_serve_trial.py) so a Stripe Customer can be created with
    # a real address from the first checkout attempt (automatic tax needs
    # one). Mirrors marketing_clubs' address columns for consistency.
    address_line1 = Column(Text, nullable=True)
    suburb = Column(Text, nullable=True)
    state = Column(Text, nullable=True)
    postcode = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    # ─── Signup attribution (migration 161) ───────────────────────────────────
    # Set only by the PUBLIC self-serve registration (routers/public_self_serve.py):
    # signup_source is the coarse bucket ('self_serve_ad' when the browser's
    # first-touch attribution carried a campaign/click signal, else
    # 'self_serve_organic'); signup_attribution is the raw getAttribution()
    # payload from frontend/src/lib/visitor.js (UTM tags, click id, landing
    # path/referrer), stored verbatim for the ad-signups report in
    # routers/meta_ads.py. NULL for every org onboarded any other way.
    signup_source = Column(Text, nullable=True)
    signup_attribution = Column(JSONB, nullable=True)
    # ─── How this club was onboarded (migration 225) ─────────────────────────
    # 'self_serve_trial' (the club registered itself, public or the internal
    # super-admin testing copy of that wizard) | 'super_admin_trial' (a super
    # admin created it from All Clubs → New Club) | 'direct_subscriber' |
    # 'none'. Same vocabulary the CRM deal's own onboarding_method uses, and
    # the deal is stamped from this. NULL for every club onboarded before this
    # column existed — absent means unknown, not "neither".
    onboarding_method = Column(Text, nullable=True)
    # ─── BetterSocials: post-generator style (migration 162) ─────────────────
    # The social post generator's Style choices (palette key, dark/light,
    # font, background texture + colour overrides, saved custom palettes and
    # designs), previously localStorage-only. Persisted per CLUB so the look
    # survives browser changes and a second admin, and so the Setup Wizard's
    # socials_palette step can auto-detect. NULL until an admin changes any
    # style control away from the defaults (the default palette already
    # derives from the club's own colours).
    socials_style = Column(JSONB, nullable=True)
    # ─── BetterSocials brand kit (migration 191) ──────────────────────────────
    # Opaque JSON blob the BetterSocials editor uses as the club's reusable
    # brand palette/fonts/crest/sponsors set. NULL until an admin saves one.
    social_brand_kit = Column(JSONB, nullable=True)
    # ─── Password-protected public page (migration 205) ───────────────────────
    # A third public-page state alongside is_active's Active/Inactive: the page
    # exists and is reachable but gated behind a 4-digit PIN (see
    # services/club_lock.py). Independent of is_active by design — the gate
    # check (routers/clubs.py::_public_blocked and
    # club_lock.is_locked_for_request) always evaluates password_protected
    # FIRST, so it wins regardless of is_active's value.
    # password_protect_reason distinguishes the copy shown on the public gate:
    #   'draft'       — voluntary privacy (club admin or Super Admin), plain
    #                    PIN entry only.
    #   'trial_ended' — Super-Admin-only, deliberate sales-conversion action;
    #                    the gate also offers an "email me for access" form
    #                    (see club_unpause_requests below).
    # access_pin_hash is a bcrypt hash — the raw PIN is never stored.
    password_protected = Column(Boolean, nullable=False, server_default="false", default=False)
    password_protect_reason = Column(Text, nullable=True)
    access_pin_hash = Column(Text, nullable=True)
    password_protected_at = Column(TIMESTAMP(timezone=True), nullable=True)
    password_protected_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # ─── BetterSelect: self-service player availability (migration 068) ───────
    # Players set their own availability via one per-club magic link + a
    # last-4-of-phone PIN — no accounts, no app. The token is the link's only
    # secret; it's pinned publicly (group chat / QR) so it's low-trust by design
    # and rotatable. require_pin lets a club drop the PIN gate (anyone who picks
    # their name is trusted) — the spec's optional per-club toggle.
    availability_link_token = Column(Text, nullable=True)
    availability_self_service_enabled = Column(Boolean, nullable=False, server_default="false", default=False)
    availability_require_pin = Column(Boolean, nullable=False, server_default="true", default=True)
    # ─── BetterFantasyCricket: public fantasy link (migration 087) ────────────
    # The per-club magic link members and supporters use to register and play
    # (mirrors availability_link_token). Rotatable; resolves to the club's
    # currently-open fantasy season. See docs/betterfantasycricket.md.
    fantasy_link_token = Column(Text, nullable=True)
    # Net Manager: club default timer/rotation config (batting_minutes, nets,
    # auto_roll, sound, alerts[]). New net sessions seed from this; NULL falls
    # back to net_manager.DEFAULT_NET_SETTINGS.
    net_settings = Column(JSONB, nullable=True)
    # ─── Net Manager: self check-in at the nets (migration 272) ───────────────
    # One club-wide link behind BOTH the printed QR code and the NFC tag on the
    # gate — a tag holds a URL and nothing else, so there is one token, not two.
    # Mirrors availability_link_token: minted on first enable, rotatable, and
    # low-trust by design since it is pinned somewhere public.
    #
    # require_pin gates the EXISTING-PLAYER path on last-4-of-phone. It cannot
    # gate a newcomer registering — someone the club has never met has no phone
    # number on file to check against — which is why allow_registration is its
    # own switch rather than something read off require_pin.
    net_checkin_token = Column(Text, nullable=True)
    net_checkin_enabled = Column(Boolean, nullable=False, server_default="false", default=False)
    net_checkin_require_pin = Column(Boolean, nullable=False, server_default="true", default=True)
    net_checkin_allow_registration = Column(Boolean, nullable=False, server_default="true", default=True)
    # ─── BetterComms: outbound email sender identity (migration 069) ──────────
    # from_name / reply_to fall back to the club name / contact_email when NULL.
    # sender_footer carries the Spam Act 2003 sender identification (legal name /
    # ABN / a postal or contact line) appended to every campaign alongside the
    # mandatory unsubscribe link.
    comms_from_name = Column(Text, nullable=True)
    comms_reply_to = Column(Text, nullable=True)
    comms_sender_footer = Column(Text, nullable=True)
    # The local-part of the SES From address (before the @), decoupled from the
    # slug so the public From can be set without touching the org's URL. NULL ⇒
    # fall back to the slug. See _from_address in routers/comms.py (migration 128).
    comms_from_local = Column(Text, nullable=True)
    # When true (the default), a contact that unsubscribes (one-click link) or is
    # hard-bounced / marks spam is automatically dropped from every static list it
    # belongs to (comms_list_members), so a suppressed address stops appearing on
    # any list. The send gate already skips suppressed addresses regardless; this
    # keeps the list membership itself tidy. See services/comms_lists.py
    # (migration 202).
    comms_auto_remove_unsubscribed = Column(Boolean, nullable=False, server_default="true", default=True)
    # ─── BetterComms sending tier (migration 125, AWS-sandbox-style) ──────────
    # A new club starts in 'sandbox' with a low daily send cap; a super admin
    # lifts it to 'production' after a clean request. The bounce/complaint
    # circuit breaker auto-moves a club to 'suspended' (cap 0) until reinstated.
    # comms_sandbox_cap / comms_production_cap are per-club overrides of the
    # global default caps for each tier (NULL = use the settings default). A
    # super admin sets these when onboarding the club on BetterAdmin. See
    # services/comms_limits.py.
    comms_tier = Column(Text, nullable=False, server_default="sandbox", default="sandbox")
    comms_sandbox_cap = Column(Integer, nullable=True)
    comms_production_cap = Column(Integer, nullable=True)
    # A monthly ceiling on top of the daily cap (NULL = use the settings default;
    # 0 = no monthly limit). Set per-club by a super admin on BetterAdmin. Counted
    # over a rolling 30-day window. See services/comms_limits.py.
    comms_monthly_cap = Column(Integer, nullable=True)
    # ─── SES per-club tenant (migration 126, multi-tenancy) ──────────────────
    # The club's Amazon SES tenant, auto-provisioned so its reputation is isolated
    # and pausable. ses_tenant_name is the deterministic slugified name (the send
    # key); ses_tenant_id is what SES returned at creation (informational).
    # ses_tenant_paused mirrors an SES tenant-paused event. See services/ses_tenants.
    ses_tenant_name = Column(Text, nullable=True)
    ses_tenant_id = Column(Text, nullable=True)
    ses_tenant_provisioned_at = Column(TIMESTAMP(timezone=True), nullable=True)
    ses_tenant_paused = Column(Boolean, nullable=False, server_default="false", default=False)
    # ─── BetterComms: BetterCricket marketing-outreach designation (migration
    # 108) ─── which org runs BetterCricket's own Clubs Directory campaigns. A
    # super admin flags it from the BetterComms UI (no env change); the
    # marketing_outreach_org_slug setting is a fallback. At most one org is true
    # (partial unique index uq_org_marketing_outreach).
    is_marketing_outreach = Column(Boolean, nullable=False, server_default="false", default=False)
    # ─── Front-end Website (Core, migration 070) ─────────────────────────────
    # The full public club website that can replace a club's existing site:
    # news, editable pages, honour rolls, committee and photo galleries, all
    # under /{slug}/website. Off by default — a club opts in. hero_image_data/
    # _mime persist the homepage hero in the DB (the /uploads volume isn't
    # guaranteed across deploys); website_social is a {network: url} map.
    website_enabled = Column(Boolean, nullable=False, server_default="false", default=False)
    website_tagline = Column(Text, nullable=True)
    website_intro = Column(Text, nullable=True)  # sanitised HTML — homepage welcome
    website_social = Column(JSONB, nullable=True)
    hero_image_data = Column(LargeBinary, nullable=True)
    hero_image_mime = Column(Text, nullable=True)
    # Show the hero as a banner on every website page (not just the homepage).
    website_hero_all_pages = Column(Boolean, nullable=False, server_default="false", default=False)
    # Committee auto-pull config: {"enabled": bool, "groups": [subcategory, ...]}.
    website_committee = Column(JSONB, nullable=True)
    # How many columns to lay the honour *boards* out in on the public page (1–3).
    website_honours_columns = Column(Integer, nullable=False, server_default="1", default=1)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    # ─── Club General Settings (migration 118) ───────────────────────────────
    # Extensible per-club settings blob, super-admin managed (matches the
    # theme_config / net_settings precedent). First key: default_trial_days (int,
    # defaults to 14 when absent) — the trial length prefilled when a module trial
    # is requested/started for this club. Grows with more settings over time.
    general_settings = Column(JSONB, nullable=False, server_default="{}", default=dict)

    seasons = relationship("Season", back_populates="organisation")
    players = relationship("Player", back_populates="organisation")
    # passive_deletes=True: club_memberships.club_id is ON DELETE CASCADE at the
    # DB level and NOT NULL — without this, SQLAlchemy's unit-of-work tries to
    # manage the relationship itself on an ORM delete (load the children, then
    # null out their FK), which fails against a NOT NULL column. See the
    # matching note on User.memberships below for where this actually bit.
    memberships = relationship("ClubMembership", back_populates="club", passive_deletes=True)
    # ─── Per-module subscription state (migration 118) ───────────────────────
    # The source of truth for which modules a club holds and each module's own
    # status / renewal / trial window. module_overrides is kept in sync as a
    # denormalised "currently-held" cache for the fast synchronous gate; see
    # app/auth/modules.py.
    module_subscriptions = relationship(
        "OrgModuleSubscription", back_populates="organisation",
        cascade="all, delete-orphan",
    )


class Sponsor(Base):
    __tablename__ = "org_sponsors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    website_url = Column(Text, nullable=True)
    logo_url = Column(Text, nullable=True)
    logo_data = Column(LargeBinary, nullable=True)
    logo_mime = Column(Text, nullable=True)
    display_order = Column(Integer, default=0, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    # KlubPro migration (migration 072): contact details carried over from the
    # KlubPro sponsor record + the source id, used to skip re-importing a sponsor
    # already brought across (unique per org, NULL for non-migrated sponsors).
    contact_name = Column(Text, nullable=True)
    email = Column(Text, nullable=True)
    klubpro_sponsor_id = Column(Text, nullable=True)


# ─── BetterSocials media library (migration 191) ─────────────────────────────
# A per-club pool of uploaded images the BetterSocials editor can drop into a
# post. Bytes live in-table (like club logos / sponsor logos / yearbook images)
# so they survive container recreation. Served via GET /images/social-media/{id}.

class SocialMediaAsset(Base):
    __tablename__ = "social_media_asset"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organisations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename = Column(Text, nullable=True)
    mime = Column(Text, nullable=True)
    image_data = Column(LargeBinary, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    # 'background' = a reusable post background offered in its own picker
    # (migration 254); NULL = an ordinary Photos-tab upload. Same table, same
    # bytes-in-Postgres storage — just a different shelf.
    kind = Column(Text, nullable=True)


# ─── Club Room Mode (migration 205) ───────────────────────────────────────────
# A club-configured, auto-rotating slideshow (sponsors / fixtures & lineups /
# recent social posts / custom images) meant to be left running full-screen on
# a TV in the club room. One settings row per club, an ordered list of
# playlist entries (each expands into one or more rendered slides on read —
# e.g. a "sponsors" entry becomes one slide per sponsor), and a shared media
# pool for both admin-uploaded images and social-post exports saved from the
# BetterSocials composer.

class ClubRoomSettings(Base):
    __tablename__ = "club_room_settings"

    organisation_id = Column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True
    )
    enabled = Column(Boolean, nullable=False, default=False)
    rotation_seconds = Column(Integer, nullable=False, default=15)
    theme = Column(Text, nullable=False, default="dark")
    shuffle = Column(Boolean, nullable=False, default=False)
    # Public link (migration 210) — a club can run the TV off /room/{token}
    # with no admin session on that browser. Same link+PIN+cookie posture as
    # BetterSelect's self-service availability/vote links.
    link_token = Column(Text, nullable=True)
    public_link_enabled = Column(Boolean, nullable=False, default=False)
    require_pin = Column(Boolean, nullable=False, default=True)
    pin_hash = Column(Text, nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class ClubRoomSlide(Base):
    __tablename__ = "club_room_slides"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slide_type = Column(Text, nullable=False)  # 'sponsors' | 'fixtures' | 'social_posts' | 'custom_images'
    title = Column(Text, nullable=True)
    config = Column(JSONB, nullable=False, default=dict)
    duration_seconds = Column(Integer, nullable=True)  # overrides the club's default rotation_seconds
    position = Column(Integer, nullable=False, default=0)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class ClubRoomMedia(Base):
    __tablename__ = "club_room_media"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(
        UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source = Column(Text, nullable=False, default="upload")  # 'upload' | 'social_export'
    caption = Column(Text, nullable=True)
    image_data = Column(LargeBinary, nullable=False)
    image_mime = Column(Text, nullable=False)
    created_by = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


# ─── Front-end Website CMS (migration 069) ───────────────────────────────────
# All website content is org-scoped and Core (every club gets the website; the
# MANAGE_WEBSITE capability gates editing). Images persist as DB blobs so they
# survive container recreation — same approach as club logos / yearbook images.

class ClubNews(Base):
    """A news article / announcement on the club website."""
    __tablename__ = "club_news"
    __table_args__ = (UniqueConstraint("organisation_id", "slug", name="uq_club_news_slug"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    slug = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    body = Column(Text, nullable=True)  # sanitised HTML
    cover_image_data = Column(LargeBinary, nullable=True)
    cover_image_mime = Column(Text, nullable=True)
    cover_image_url = Column(Text, nullable=True)
    author = Column(Text, nullable=True)
    is_published = Column(Boolean, nullable=False, server_default="true", default=True)
    is_pinned = Column(Boolean, nullable=False, server_default="false", default=False)
    published_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class ClubPage(Base):
    """A free-form rich-text info page (About, History, Join Us, ...)."""
    __tablename__ = "club_pages"
    __table_args__ = (UniqueConstraint("organisation_id", "slug", name="uq_club_pages_slug"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    slug = Column(Text, nullable=False)
    body = Column(Text, nullable=True)  # sanitised HTML
    nav_label = Column(Text, nullable=True)
    # Nav hierarchy: parent_id nests this page under another (a submenu item);
    # is_header marks a dropdown group that has no page of its own (e.g. "Teams").
    parent_id = Column(UUID(as_uuid=True), ForeignKey("club_pages.id", ondelete="SET NULL"), nullable=True)
    is_header = Column(Boolean, nullable=False, server_default="false", default=False)
    show_in_nav = Column(Boolean, nullable=False, server_default="true", default=True)
    is_published = Column(Boolean, nullable=False, server_default="true", default=True)
    display_order = Column(Integer, nullable=False, server_default="0", default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class ClubHonourBoard(Base):
    """A grouped honour roll (Life Members, Hall of Fame, Past Presidents, ...)."""
    __tablename__ = "club_honour_boards"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    # When set, the board auto-populates from player_achievements of this
    # category (optionally narrowed by subcategory) instead of manual entries.
    source_category = Column(Text, nullable=True)
    source_subcategory = Column(Text, nullable=True)
    # How many columns to lay the entries out in on the public site (1–4).
    columns = Column(Integer, nullable=False, server_default="1", default=1)
    display_order = Column(Integer, nullable=False, server_default="0", default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    entries = relationship("ClubHonourEntry", back_populates="board", cascade="all, delete-orphan")


class ClubHonourEntry(Base):
    """A single line on an honour board (a year, a name, an optional detail)."""
    __tablename__ = "club_honour_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    board_id = Column(UUID(as_uuid=True), ForeignKey("club_honour_boards.id", ondelete="CASCADE"), nullable=False)
    year = Column(Integer, nullable=True)
    name = Column(Text, nullable=False)
    detail = Column(Text, nullable=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    display_order = Column(Integer, nullable=False, server_default="0", default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    board = relationship("ClubHonourBoard", back_populates="entries")


class ClubCommitteeMember(Base):
    """A committee / contact entry (role, name, contact details, photo)."""
    __tablename__ = "club_committee"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    phone = Column(Text, nullable=True)
    bio = Column(Text, nullable=True)
    photo_data = Column(LargeBinary, nullable=True)
    photo_mime = Column(Text, nullable=True)
    photo_url = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, server_default="0", default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class ClubGalleryAlbum(Base):
    """A photo gallery album."""
    __tablename__ = "club_gallery_albums"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, server_default="0", default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    images = relationship("ClubGalleryImage", back_populates="album", cascade="all, delete-orphan")


class ClubGalleryImage(Base):
    """A single photo inside a gallery album (blob stored in the DB)."""
    __tablename__ = "club_gallery_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    album_id = Column(UUID(as_uuid=True), ForeignKey("club_gallery_albums.id", ondelete="CASCADE"), nullable=False)
    image_data = Column(LargeBinary, nullable=True)
    image_mime = Column(Text, nullable=True)
    image_url = Column(Text, nullable=True)
    caption = Column(Text, nullable=True)
    display_order = Column(Integer, nullable=False, server_default="0", default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    album = relationship("ClubGalleryAlbum", back_populates="images")


class ClubMembership(Base):
    __tablename__ = "club_memberships"
    __table_args__ = (
        UniqueConstraint("club_id", "user_id", name="uq_club_membership"),
        # An admin account is linked to exactly one club.
        UniqueConstraint("user_id", name="uq_membership_one_per_user"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    club_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, default="club_admin", nullable=False)
    # JSONB array of capability strings. Empty list = "no extra caps beyond
    # role". For super_admin/club_admin the list is ignored (those roles
    # imply all caps). For club_member, this is the explicit allowlist.
    capabilities = Column(JSONB, default=list, nullable=False, server_default="[]")
    # The club's primary / owner admin (migration 118). The first club_admin
    # created for a club is primary; it's reassignable to another club_admin (by
    # the current primary or a super admin). Only the primary may request a paid
    # module subscription (financial authority gate); any club_admin may request a
    # trial. At most one true per club (partial unique index uq_membership_primary).
    is_primary_admin = Column(Boolean, nullable=False, server_default="false", default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    club = relationship("Organisation", back_populates="memberships")
    user = relationship("User", back_populates="memberships")


class OrgModuleSubscription(Base):
    """Per-module subscription state for a club (migration 118).

    One row per club × module that the club holds or is trialing. This is the
    source of truth for entitlement; ``organisations.module_overrides`` is kept in
    sync as a denormalised currently-held cache for the fast synchronous gate (see
    app/auth/modules.py). The org-level ``organisations.subscription_status`` is a
    whole-account master switch above these rows: paused/cancelled there drops the
    club to Core only regardless of per-module state.

    ``status`` mirrors the org-level vocabulary (active / trial / past_due /
    paused / cancelled). A trial is live only while ``now <= trial_ends_at`` —
    expiry is evaluated on read, so a trial lapses on its own with no scheduler.
    """
    __tablename__ = "org_module_subscriptions"
    __table_args__ = (
        UniqueConstraint("organisation_id", "module_key", name="uq_org_module"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    module_key = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="active", default="active")
    trial_started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    trial_ends_at = Column(TIMESTAMP(timezone=True), nullable=True)
    renewal_date = Column(Date, nullable=True)
    started_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    organisation = relationship("Organisation", back_populates="module_subscriptions")


class ModuleActionRequest(Base):
    """A request to change a club's module entitlement, actioned by a super admin
    (migration 119). A request never changes entitlement on its own — it queues an
    action. ``kind`` is trial / subscribe / cancel; ``source`` records where it came
    from (app / super_admin / twenty). The super admin actions it from the queue;
    completing a trial request creates the trial (``result_subscription_id``).

    Mirrors the ClubOnboardingRequest pattern (super-admin actionable, lifecycle +
    source + timestamps). ``external_ref`` dedupes a Twenty-origin request.
    """
    __tablename__ = "module_action_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    module_key = Column(Text, nullable=False)
    kind = Column(Text, nullable=False)                 # trial | subscribe | cancel
    status = Column(Text, nullable=False, server_default="outstanding", default="outstanding")  # outstanding | completed | dismissed
    source = Column(Text, nullable=False, server_default="app", default="app")  # app | super_admin | twenty
    note = Column(Text, nullable=True)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    completed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    result_subscription_id = Column(UUID(as_uuid=True), ForeignKey("org_module_subscriptions.id", ondelete="SET NULL"), nullable=True)
    external_ref = Column(Text, nullable=True)          # dedupe key for a Twenty-origin request


class BillingInvoice(Base):
    """A mirror of a Stripe Invoice, written by the /public/stripe/webhook handler
    (migration 150) so a club's Account page can show its own billing history
    without ever calling the Stripe API directly. ``line_items`` is OUR OWN quote
    snapshot (services/billing_pricing.price_for) at the moment the invoice event
    landed — not Stripe's line items — so it always reads in the same module/price
    shape the rest of the app uses, no Stripe-response parsing needed to display it.
    """
    __tablename__ = "billing_invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    stripe_invoice_id = Column(Text, nullable=False, unique=True)
    stripe_subscription_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False)  # paid | open | void | uncollectible | draft
    amount_due = Column(Integer, nullable=False, server_default="0", default=0)   # cents
    amount_paid = Column(Integer, nullable=False, server_default="0", default=0)  # cents
    currency = Column(Text, nullable=False, server_default="aud", default="aud")
    period_start = Column(TIMESTAMP(timezone=True), nullable=True)
    period_end = Column(TIMESTAMP(timezone=True), nullable=True)
    hosted_invoice_url = Column(Text, nullable=True)
    invoice_pdf = Column(Text, nullable=True)
    line_items = Column(JSONB, nullable=True)
    # Discount breakdown (migration 159) — Stripe's own invoice can only show
    # ONE combined discount line (Checkout Session's one-discount cap, see
    # stripe_client.create_checkout_session), so this is the TRUE separate
    # amounts, computed locally at checkout time and round-tripped through
    # the session's metadata. 0 = that discount didn't apply to this invoice.
    bundle_discount_cents = Column(Integer, nullable=False, server_default="0", default=0)
    coupon_code = Column(Text, nullable=True)
    coupon_discount_cents = Column(Integer, nullable=False, server_default="0", default=0)
    # Migration 278 — sales commission is EARNED on a confirmed payment, not on
    # a CRM deal's stage. Stripe's own reason the invoice exists is what
    # separates new business from a renewal: 'subscription_create' (the first
    # payment) and 'subscription_update' (modules added to a live
    # subscription) earn; 'subscription_cycle' (a renewal of what the club
    # already holds) does not. amount_ex_tax_cents is what the club paid NET
    # OF GST, since tax collected on our behalf was never our revenue. The
    # rep, the rate and the resulting commission are STAMPED when the payment
    # is recorded and never recomputed, so changing a rate later cannot
    # rewrite what a payment already earned. commission_kind is
    # 'initial' | 'expansion', or NULL for a payment that earns nothing.
    billing_reason = Column(Text, nullable=True)
    amount_ex_tax_cents = Column(Integer, nullable=True)
    commission_rep_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    commission_rate_percent = Column(Numeric(6, 3), nullable=True)
    commission_cents = Column(BigInteger, nullable=True)
    commission_kind = Column(Text, nullable=True)
    # Which payment method actually paid this invoice, e.g. "Visa Debit
    # •••• 4242", "PayTo (...0400)" — see stripe_client.describe_payment_method.
    payment_method_type = Column(Text, nullable=True)
    payment_method_summary = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    organisation = relationship("Organisation")


class DiscountCoupon(Base):
    """A BetterCricket-managed discount coupon (migration 156). Super Admin
    owns the full lifecycle entirely inside BetterCricket — never in the
    Stripe Dashboard directly; ``stripe_coupon_id`` is a synced mirror pushed
    via services/stripe_client.sync_coupon_to_stripe, and BetterCricket's own
    columns here (not Stripe's redeem_by/max_redemptions) are the sole
    eligibility gate — see services/discount_coupons.validate_redemption.

    ``module_keys`` null/empty means "all billable modules"; otherwise a
    JSON array of module keys, mirrored onto Stripe's own
    ``Coupon.applies_to.products`` so a covered/non-covered mix on one
    invoice is split automatically by Stripe.

    ``redeem_window_*`` gates when the code can be entered at all (either
    role, either flow). ``new_signup_window_*`` additionally restricts a
    code to a club's very first subscribe if set; ``loyalty_window_*``
    instead restricts it to a club whose original subscription start falls
    in that historical range. Both are optional and independent — a coupon
    can set neither (any club, any time within the redeem window), either
    one, or both (in which case a redemption must satisfy the one that
    matches its flow — new signup vs already-subscribed).

    ``duration_mode`` mirrors Stripe's own Coupon duration vocabulary:
    'once' (first invoice only), 'repeating' (``duration_renewals`` years,
    converted to Stripe's duration_in_months = 12 * N), 'forever'.

    Once a coupon has a live (non-revoked) redemption, its financial terms
    (discount_type/discount_value/module_keys/duration_mode/
    duration_renewals) are locked — Stripe Coupons are themselves immutable
    on these fields after creation, and changing them out from under an
    already-redeemed club would silently rewrite what they were promised.
    See services/discount_coupons.update_coupon.
    """
    __tablename__ = "discount_coupons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(Text, nullable=False, unique=True)  # stored/compared uppercase
    display_name = Column(Text, nullable=False)
    discount_type = Column(Text, nullable=False)   # percent | amount
    discount_value = Column(Numeric, nullable=False)
    module_keys = Column(JSONB, nullable=True)      # null/[] = all billable modules
    redeem_window_start = Column(Date, nullable=True)
    redeem_window_end = Column(Date, nullable=True)
    new_signup_window_start = Column(Date, nullable=True)
    new_signup_window_end = Column(Date, nullable=True)
    loyalty_window_start = Column(Date, nullable=True)
    loyalty_window_end = Column(Date, nullable=True)
    duration_mode = Column(Text, nullable=False, server_default="once", default="once")  # once | repeating | forever
    duration_renewals = Column(Integer, nullable=True)  # years, only for 'repeating'
    stackable_with_bundle = Column(Boolean, nullable=False, server_default="false", default=False)
    max_redemptions = Column(Integer, nullable=True)
    active = Column(Boolean, nullable=False, server_default="true", default=True)
    stripe_coupon_id = Column(Text, nullable=True)
    # Which Stripe mode minted stripe_coupon_id — 'live' | 'test' (migration
    # 263). A test-mode Coupon id is simply not there when a live key asks
    # for it, so services/discount_coupons.ensure_stripe_coupon re-syncs
    # whenever this doesn't match the key the app is running on. NULL for
    # every coupon created before this shipped.
    stripe_mode = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class DiscountCouponRedemption(Base):
    """One club's use of a DiscountCoupon (migration 156) — the audit trail
    AND the enforcement of "one redemption per club, ever" (the partial
    unique index only counts non-revoked rows, so a Super Admin's revoke
    frees the slot for a genuine mistake).

    ``status`` is 'pending' only for a new-signup redemption between
    Checkout Session creation and the checkout.session.completed webhook
    confirming it (stripe_billing.py flips it to 'active' there); an
    existing-subscription redemption applies synchronously and is written
    straight in as 'active' — there's no webhook round-trip for that path.
    """
    __tablename__ = "discount_coupon_redemptions"
    __table_args__ = (
        # Partial unique index, not a plain UniqueConstraint — a 3-column
        # constraint including status would let 'pending' and 'active' rows
        # coexist for the same club+coupon (different status values, same
        # slot). This enforces "at most one NON-REVOKED redemption" instead,
        # matching the docstring above.
        Index(
            "uq_coupon_redemption_live_slot", "coupon_id", "organisation_id",
            unique=True, postgresql_where=text("status <> 'revoked'"),
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    coupon_id = Column(UUID(as_uuid=True), ForeignKey("discount_coupons.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    redeemed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    applied_via = Column(Text, nullable=False)  # self_serve | super_admin
    redeemed_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    stripe_subscription_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="active", default="active")  # pending | active | revoked

    coupon = relationship("DiscountCoupon")
    organisation = relationship("Organisation")


class CommsLimitRequest(Base):
    """A club's request to lift its BetterComms sending tier (migration 125),
    actioned by a super admin — the AWS-sandbox-out-of-sandbox flow, one level up.

    Mirrors ModuleActionRequest: a request never changes the tier on its own, it
    queues a decision. The super admin approves (which sets the club's
    ``comms_tier`` / per-club cap) or denies. Creating one also emits a
    ClubRequestEvent (telemetry + a Twenty task) via services/club_requests.py.
    """
    __tablename__ = "comms_limit_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    current_tier = Column(Text, nullable=True)
    requested_tier = Column(Text, nullable=False, server_default="production", default="production")
    requested_cap = Column(Integer, nullable=True)      # optional explicit daily cap ask
    reason = Column(Text, nullable=True)                # the club's justification
    status = Column(Text, nullable=False, server_default="pending", default="pending")  # pending | approved | denied
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    requested_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(TIMESTAMP(timezone=True), nullable=True)
    decision_note = Column(Text, nullable=True)


class ClubRequestEvent(Base):
    """Telemetry for EVERY club→BetterCricket request across the platform
    (migration 125): a BetterComms tier lift, a module trial/subscribe, and
    future asks. One durable audit row per request, and the hook that fires an
    automated Twenty CRM task so the back office actions it. Written by the
    shared helper services/club_requests.py::record_club_request.

    ``request_type`` is a stable slug (comms_tier_increase | module_request | …);
    ``ref_table`` / ``ref_id`` point back at the domain row (e.g. the
    comms_limit_requests row) so the CRM task and the workflow queue stay linked.
    ``twenty_task_status`` tracks the best-effort CRM push (pending → created /
    failed / skipped) without ever blocking the request itself.
    """
    __tablename__ = "club_request_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    request_type = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    detail = Column(JSONB, nullable=True)
    source = Column(Text, nullable=False, server_default="app", default="app")  # bettercomms | app | super_admin | twenty
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    ref_table = Column(Text, nullable=True)
    ref_id = Column(UUID(as_uuid=True), nullable=True)
    twenty_task_id = Column(Text, nullable=True)
    twenty_task_status = Column(Text, nullable=False, server_default="pending", default="pending")  # pending | created | failed | skipped
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class Season(Base):
    __tablename__ = "seasons"

    id = Column(UUID(as_uuid=True), primary_key=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"))
    # Per-club derived id (uuid5 of org id + grassroots_id). The raw Cricket
    # Australia season GUID lives in grassroots_id — it is shared across clubs
    # so it cannot be the primary key.
    grassroots_id = Column(Text, nullable=True)
    name = Column(Text, nullable=False)
    year = Column(Integer)
    synced_at = Column(TIMESTAMP(timezone=True))
    display_order = Column(Integer, nullable=True)

    organisation = relationship("Organisation", back_populates="seasons")
    grades = relationship("Grade", back_populates="season")
    player_stats = relationship("PlayerSeasonStats", back_populates="season")


class Grade(Base):
    __tablename__ = "grades"

    id = Column(UUID(as_uuid=True), primary_key=True)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"))
    # Per-club derived id (uuid5 of org id + grassroots_id) when the raw CA grade
    # GUID is shared with another club; otherwise the raw GUID itself. A CA grade
    # is competition-wide — one GUID is shared by every club in the grade — so it
    # cannot be a global primary key. The raw GUID lives in grassroots_id and is
    # what the grassroots API (grade matches / ladder / per-grade stats) is keyed
    # on. See migration 067.
    grassroots_id = Column(Text, nullable=True)
    name = Column(Text, nullable=False)
    display_name_override = Column(Text, nullable=True)
    playhq_id = Column(Text, nullable=True)
    # Fee-tracking format override. NULL = derive from Game.match_format.
    # One of: 'two_day' | 'one_day' | 't20' | 'women' | 'exclude'.
    # 'women' is needed because women's (PSWL) grades come through as plain
    # One Day / T20 and can't be told apart from the men's competition;
    # 'exclude' drops a grade from match-fee accrual entirely.
    fee_format = Column(Text, nullable=True)
    # Public-facing category (migration 123). One of the keys in
    # app/services/grade_labels.GRADE_CATEGORIES: 'senior' | 'junior' | 'womens'
    # | 'masters' | 'mixed'. NULL = uncategorised (readers fall back to the
    # name-based suggestion). Attaches to a grade name club-wide, like the
    # display-name override.
    category = Column(Text, nullable=True)
    # Every category this grade belongs to (migration 259). A grade is not one
    # thing: "Girls Under 14" is junior AND women's. Keys are the same
    # GRADE_CATEGORIES set as `category`, which stays in step with the first
    # entry here so nothing that reads the single column has to change.
    # NULL = not classified, and readers fall back to the name suggestion.
    categories = Column(ARRAY(Text), nullable=True)
    # Which format(s) this grade plays (migration 259) — 'two_day' | 'one_day' |
    # 't20', from app/services/grade_labels.MATCH_FORMATS. A grade that plays
    # more than one carries more than one. NULL = not classified, and readers
    # fall back to the formats actually recorded on this grade's games
    # (games.match_format), then to the grade name. Distinct from `fee_format`,
    # which is a BetterFees billing override with its own extra values.
    match_formats = Column(ARRAY(Text), nullable=True)
    # Whether this grade is shared on the club's public site (migration 123).
    # Defaults true so nothing is hidden until a club explicitly opts a grade
    # (e.g. their whole junior programme) out of public grade surfaces.
    is_public = Column(Boolean, nullable=False, server_default="true", default=True)
    # The order a club reads its own teams in — Seniors 1, Reserves 2, Under
    # 19s 3 (migration 227). NULL = unordered, and sorts AFTER every ordered
    # grade, so a club that has ordered three of its ten grades gets those
    # three first and the rest in their previous alphabetical order rather
    # than a scramble. Set across a whole grade name at once by the admin,
    # like display_name_override and category.
    display_order = Column(Integer, nullable=True)

    season = relationship("Season", back_populates="grades")
    games = relationship("Game", back_populates="grade")

    @property
    def display_name(self) -> str:
        return self.display_name_override or self.name


class Player(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("organisation_id", "playhq_id", name="uq_player_org_playhq_id"),
        # A Cricket Australia participant GUID is shared across every club a
        # person plays for, so it can't safely be a global primary key — the
        # second club's sync collides on the first club's row and co-mingles
        # their stats. id is therefore a per-club derived value (uuid5(org,
        # guid)) for players created from migration 062 on, and grassroots_id
        # holds the raw CA GUID (used to match scorecard participantIds). Legacy
        # rows keep their raw-GUID id; either way (org, grassroots_id) is unique.
        # Same pattern Seasons already use (see Season.grassroots_id).
        UniqueConstraint("organisation_id", "grassroots_id", name="uq_player_org_grassroots"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True)
    name = Column(Text, nullable=False)
    display_name_override = Column(Text, nullable=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"))
    playhq_id = Column(Text, nullable=True)
    # Raw Cricket Australia participant GUID. Shared across clubs; matches the
    # scorecard `participantId` and the aggregate feed's player `id`. For a
    # player whose id is a per-club uuid5, this is the join key back to CA.
    grassroots_id = Column(Text, nullable=True)
    # Free-text note an admin leaves when promoting a scorecard fill-in into a
    # real player (migration 147) — e.g. a pasted PlayHQ profile URL for their
    # own future reference. Not parsed or verified; see claim-fill-in.
    claim_note = Column(Text, nullable=True)
    # The BetterImport batch that minted this player (migration 234) — set only
    # when the import commit itself creates the row, NULL for synced or
    # hand-added players. Undoing that batch deletes the player again if the
    # undo leaves them with nothing attached (services/import_cleanup.py);
    # a later re-import moves the marker to the newer batch.
    import_batch_id = Column(UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True)
    photo_url = Column(Text, nullable=True)
    photo_data = Column(LargeBinary, nullable=True)
    photo_mime = Column(Text, nullable=True)
    # The action shot (migration 274) — a separate photograph from the
    # headshot above, for the full-bleed hero slot on a match-day post.
    hero_photo_url = Column(Text, nullable=True)
    hero_photo_data = Column(LargeBinary, nullable=True)
    hero_photo_mime = Column(Text, nullable=True)
    gender = Column(Text, nullable=True)
    is_player = Column(Boolean, default=True, nullable=True)
    player_role = Column(Text, nullable=True)
    is_overseas = Column(Boolean, nullable=True)
    overseas_country = Column(Text, nullable=True)
    # BetterSelect cricket attributes for selection filters (migration 050).
    batting_hand = Column(Text, nullable=True)        # 'LEFT' | 'RIGHT'
    bowling_action = Column(Text, nullable=True)      # 'RIGHT_ARM' | 'LEFT_ARM'
    bowling_type = Column(Text, nullable=True)        # FAST|FAST_MEDIUM|MEDIUM|MEDIUM_FAST|FINGER_SPIN|WRIST_SPIN
    is_opening_batsman = Column(Boolean, nullable=True)
    # BetterSelect: the player's single assigned selection-pool squad (migration
    # 053). Distinct from the team_members M2M, which stays for suggestions.
    squad_team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    # claimed / user_id retained as columns but no longer used in business logic
    claimed = Column(Boolean, default=False)
    user_id = Column(UUID(as_uuid=True), nullable=True)
    # BetterSelect: admin-managed contact + selection attributes (migration 044)
    email = Column(Text, nullable=True)
    phone = Column(Text, nullable=True)
    skill_positions = Column(JSONB, default=list, nullable=False, server_default="[]")  # e.g. ["BAT","WKT"]
    status = Column(Text, default="active", nullable=False, server_default="active")  # active | inactive
    # Whether this player is shown on the club's PUBLIC site (migration 265).
    # Defaults true, so nothing is hidden by an upgrade; a club opts a player
    # out (typically a junior who does not want to be findable) and they drop
    # off the public roster, search, profile page, leaderboards and records
    # while staying fully present in every admin surface. Same shape as
    # grades.is_public, and read through the same user_can_view_org_private
    # escape so a signed-in club admin still sees their own club whole.
    is_public = Column(Boolean, default=True, nullable=False, server_default="true")
    # BetterSelect "non-financial" filter (migration 265). NULL = no override,
    # so the answer comes from BetterFees' own balance; True/False is a club
    # saying so by hand, which is also the only answer a club not running
    # BetterFees can give.
    is_financial_override = Column(Boolean, nullable=True)
    # BetterSelect "attended training" filter (migration 265). NULL = no
    # override, so the answer comes from Net Manager attendance.
    trained_override = Column(Boolean, nullable=True)
    # Date of birth (migration 269), entered by hand on the player profile —
    # no feed carries one. The AGE is never stored: services/player_age.py
    # works it out on read, because a stored age is wrong the day after it
    # was written. Only ever served on the MANAGE_PLAYERS-gated profile
    # payload; every other surface gets the derived age instead, and only
    # when the club's own BetterSelect setting allows it.
    date_of_birth = Column(Date, nullable=True)

    organisation = relationship("Organisation", back_populates="players")
    batting_innings = relationship("BattingInnings", back_populates="player")
    bowling_spells = relationship("BowlingSpell", back_populates="player")
    fielding_stats = relationship("FieldingStat", back_populates="player")
    appearances = relationship("GameAppearance", back_populates="player")
    milestones = relationship("Milestone", back_populates="player")
    season_stats = relationship("PlayerSeasonStats", back_populates="player")

    @property
    def display_name(self) -> str:
        return self.display_name_override or self.name


class PlayerNameAlias(Base):
    """A former/alternate name for a player, so a live feed (Play.Cricket team
    list, a Grassroots scorecard) still resolving by NAME finds the right
    player after a rename — a marriage/preferred-name change, or CA's own
    inconsistent spelling. Auto-seeded with the OLD name whenever a player is
    renamed (source='rename'); an admin can also add one by hand
    (source='manual') for a rename that predates this table, or any other
    name variant. Matched by ``alias_key`` (services/player_aliases.py's
    ``normalise_name_key`` — lowercased, order-independent tokens), org-scoped
    so one alias resolves to exactly one player.
    """
    __tablename__ = "player_name_aliases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    alias_name = Column(Text, nullable=False)
    alias_key = Column(Text, nullable=False)
    source = Column(Text, nullable=False, default="manual", server_default="manual")  # 'manual' | 'rename'
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class Game(Base):
    __tablename__ = "games"

    id = Column(UUID(as_uuid=True), primary_key=True)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="CASCADE"))
    played_at = Column(Date)
    home_team = Column(Text)
    away_team = Column(Text)
    home_club = Column(Text)
    away_club = Column(Text)
    opp_org_id = Column(Text)
    opp_club_name = Column(Text)
    # Per-side org id (migration 167) — the reliable, non-clobbering signal
    # for a shared games.id row between two both-synced clubs. opp_org_id
    # above is a single value set once by whichever club synced the row
    # first, so it can only ever be correct from one side; these two columns
    # let each synced club independently record which side it was on.
    home_org_id = Column(UUID(as_uuid=True), nullable=True)
    away_org_id = Column(UUID(as_uuid=True), nullable=True)
    result = Column(Text)
    winning_team = Column(Text)
    is_final = Column(Boolean, default=False, nullable=False, server_default='false')
    raw_payload = Column(JSON)
    venue = Column(Text)
    match_format = Column(Text, nullable=True)
    # Cricket Australia's own match status, verbatim: COMPLETED, ABANDONED,
    # CANCELLED, UPCOMING, LIVE (migration 266). NULL means we have not been
    # told — every row predating that migration reads that way until a sync
    # or `python -m app.scripts.backfill_game_status` fills it in. Read by
    # v_effective_player_season_stats to keep a washed-out fixture out of a
    # player's matches-played count; `result` cannot answer that question,
    # since a NULL result also covers an upcoming or in-progress fixture.
    status = Column(Text, nullable=True)

    grade = relationship("Grade", back_populates="games")
    batting_innings = relationship("BattingInnings", back_populates="game")
    bowling_spells = relationship("BowlingSpell", back_populates="game")
    fielding_stats = relationship("FieldingStat", back_populates="game")
    appearances = relationship("GameAppearance", back_populates="game")
    fall_of_wickets = relationship("FallOfWicket", back_populates="game")
    partnerships = relationship("Partnership", back_populates="game")


class Fixture(Base):
    """BetterSelect: upcoming / scheduled matches — the foundation availability
    and team selection build on. BetterStats otherwise stores only completed
    games. Two sources:
      - 'playhq': synced from the partner API; id == the CA/PlayHQ game GUID,
        so a played fixture maps 1:1 to the eventual games.id row.
      - 'manual': admin-created (friendlies / pre-season) so lineups & social
        posts can be built without an official PlayHQ game; id is a uuid4.
    """
    __tablename__ = "fixtures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    source = Column(Text, nullable=False, server_default="manual")  # 'playhq' | 'manual'
    playhq_id = Column(Text, nullable=True)
    label = Column(Text, nullable=True)         # free-text title (friendlies / manual)
    round = Column(Text, nullable=True)
    played_on = Column(Date, nullable=True)     # match date (mirrors games.played_at)
    end_on = Column(Date, nullable=True)        # multi-day cricket
    start_time = Column(Text, nullable=True)    # "HH:MM" local, display only
    home_team = Column(Text, nullable=True)
    away_team = Column(Text, nullable=True)
    home_away = Column(Text, nullable=True)     # HOME | AWAY | BYE (our perspective)
    opponent_name = Column(Text, nullable=True)
    venue = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="UPCOMING")  # UPCOMING|IN_PROGRESS|FINAL|CANCELLED|BYE
    # Whether this fixture is a final, for the selection rules that only bite
    # in finals (migration 271). NULL = work it out from the round name, which
    # is what every synced fixture carries; set by hand when an association
    # names its finals something the heuristic can't read.
    is_final = Column(Boolean, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    organisation = relationship("Organisation")
    grade = relationship("Grade")
    team = relationship("Team")


class Team(Base):
    """BetterSelect: a first-class club team. BetterStats otherwise only has
    team *names* on games. Players are not hard-assigned to teams (club-wide
    model); a team groups fixtures and, later, scopes selection.
    """
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_team_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    short_name = Column(Text, nullable=True)
    sequence = Column(Integer, default=0, nullable=False, server_default="0")  # hierarchy rank (1 = top team)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    default_formation = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, server_default="true")
    source = Column(Text, nullable=False, server_default="manual")  # 'auto' | 'manual'
    playhq_id = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    organisation = relationship("Organisation")
    grade = relationship("Grade")


class TeamMember(Base):
    """BetterSelect: manual squad membership — a player in a team's pool.

    Optional override on top of the club-wide model. History suggests who's
    played for a team recently; this records the admin's actual squad. M2M:
    a player can sit in several teams' squads.
    """
    __tablename__ = "team_members"

    team_id = Column(UUID(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class FixtureLineup(Base):
    """BetterSelect Phase 3: a player picked for a fixture (the team sheet).

    Per-fixture: the same player can be in two fixtures' lineups on one weekend
    (the shared-player split). Any cross-fixture selection rule is enforced in
    the app layer, not here. batting_order is the slot (1..n), nullable until
    the side is ordered.
    """
    __tablename__ = "fixture_lineups"

    fixture_id = Column(UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    batting_order = Column(Integer, nullable=True)
    is_captain = Column(Boolean, default=False, nullable=False, server_default="false")
    is_wicket_keeper = Column(Boolean, default=False, nullable=False, server_default="false")
    selected_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class PlayerAvailability(Base):
    """BetterSelect: a player's availability for a playing DATE (admin-recorded).

    Keyed on (player, date), NOT per fixture: one answer covers every fixture
    that day. A two-day game contributes both its dates (played_on = week 1,
    end_on = week 2). Club-wide model — recorded_by/at track which admin set it
    (no player-facing input).
    """
    __tablename__ = "player_availability"
    __table_args__ = (
        UniqueConstraint("player_id", "avail_date", name="uq_player_availability_player_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    avail_date = Column(Date, nullable=False)
    status = Column(Text, nullable=False, server_default="NO_RESPONSE")  # AVAILABLE|UNAVAILABLE|MAYBE|NO_RESPONSE
    note = Column(Text, nullable=True)
    # 'admin' (set in the matrix) | 'self' (the player, via the magic-link page).
    # recorded_by is NULL for self-service, so source is what audits and badges a
    # player-reported answer apart from an admin one (migration 068).
    source = Column(Text, nullable=False, server_default="admin", default="admin")
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recorded_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class PlayerAvailabilityPeriod(Base):
    """BetterSelect: a player's availability across a DATE RANGE (admin-recorded).

    Set once to cover a span — e.g. "injured 1 Jun–15 Jul", or open-ended "out
    until further notice" (end_date NULL). A covering period supplies a date's
    status wherever no explicit per-date PlayerAvailability row exists; explicit
    rows always win. Club-wide; recorded_by/at track which admin set it.
    """
    __tablename__ = "player_availability_periods"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)  # NULL = open-ended
    status = Column(Text, nullable=False)   # AVAILABLE|UNAVAILABLE|MAYBE
    reason = Column(Text, nullable=True)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    recorded_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class VoteMedal(Base):
    """One award a club counts votes towards — its name and its own settings.

    The whole feature is derived-on-read: ballots store ranked POSITIONS only,
    and every weekly result / season leaderboard is recomputed from this config
    at query time — so changing the ballot values, counting method or tie
    policy mid-season restates the season consistently with no backfill.

    Every settings column here is named exactly as it was on ``VoteSettings``,
    which is what lets ``services.votes.effective_config`` read either one.
    ``VoteSettings`` is history after migration 267 and nothing reads it.
    """
    __tablename__ = "vote_medals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    # Public voting link token — rotatable, same low-trust posture as the
    # availability link (identifies the medal only; a player still needs a PIN).
    # One per medal, so a club can share the Colts link with the Colts.
    link_token = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    require_pin = Column(Boolean, nullable=False, default=True, server_default="true")
    voter_mode = Column(Text, nullable=False, default="players", server_default="players")  # 'players' | 'captain'
    ballot_values = Column(JSONB, nullable=False, default=[3, 2, 1])  # descending, position 1 first
    counting_method = Column(Text, nullable=False, default="rank", server_default="rank")  # 'rank' | 'tally'
    tie_policy = Column(Text, nullable=False, default="share", server_default="share")  # 'share' | 'countback'
    allow_self_vote = Column(Boolean, nullable=False, default=False, server_default="false")
    allow_non_participants = Column(Boolean, nullable=False, default=False, server_default="false")
    auto_close_days = Column(Integer, nullable=False, default=7, server_default="7")
    # Which team list decides who can be voted for (migration 194):
    # 'scorecard' (who actually played) | 'lineup' (the BetterSelect XI) |
    # 'playhq' (the side published on Play.Cricket). Overridable per fixture.
    eligibility_source = Column(Text, nullable=False, default="scorecard", server_default="scorecard")
    # The grades this medal counts, as a JSONB list of uuid strings. EMPTY
    # MEANS EVERY GRADE — that is what a club's only medal means before anyone
    # has thought about grades. No FK on purpose: a grade merged away or
    # deleted just stops matching rather than blocking the delete.
    grade_ids = Column(JSONB, nullable=False, default=list, server_default="[]")
    position = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class VoteSettings(Base):
    """DEPRECATED (migration 267) — the pre-medals one-row-per-club config.

    Kept as history: its row was copied onto the club's first ``VoteMedal``,
    link token included, and nothing reads this table any more. Don't add a
    column here; add it to ``VoteMedal``.
    """
    __tablename__ = "vote_settings"

    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), primary_key=True)
    enabled = Column(Boolean, nullable=False, default=False, server_default="false")
    # Public voting link token — rotatable, same low-trust posture as the
    # availability link (identifies the club only; a player still needs a PIN).
    link_token = Column(Text, nullable=True)
    require_pin = Column(Boolean, nullable=False, default=True, server_default="true")
    voter_mode = Column(Text, nullable=False, default="players", server_default="players")  # 'players' | 'captain'
    ballot_values = Column(JSONB, nullable=False, default=[3, 2, 1])  # descending, position 1 first
    counting_method = Column(Text, nullable=False, default="rank", server_default="rank")  # 'rank' | 'tally'
    tie_policy = Column(Text, nullable=False, default="share", server_default="share")  # 'share' | 'countback'
    allow_self_vote = Column(Boolean, nullable=False, default=False, server_default="false")
    allow_non_participants = Column(Boolean, nullable=False, default=False, server_default="false")
    auto_close_days = Column(Integer, nullable=False, default=7, server_default="7")
    # Which team list decides who can be voted for (migration 194):
    # 'scorecard' (who actually played) | 'lineup' (the BetterSelect XI) |
    # 'playhq' (the side published on Play.Cricket). Overridable per fixture.
    eligibility_source = Column(Text, nullable=False, default="scorecard", server_default="scorecard")
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class VoteBallot(Base):
    """One voter's ballot for one fixture, towards ONE medal.

    Voter identity is exactly one of: voter_player_id (a club player — PIN
    verified on the public page, or admin-entered) or voter_name (a
    non-participant: coach / president / supporter, name typed on the public
    page). Partial unique indexes (see migration 267) enforce one live ballot
    per voter per fixture per medal in each identity space — a fixture counting
    towards two medals collects a separate ballot for each, so the two counts
    can genuinely disagree about who was best.
    """
    __tablename__ = "vote_ballots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    medal_id = Column(UUID(as_uuid=True), ForeignKey("vote_medals.id", ondelete="CASCADE"), nullable=False)
    fixture_id = Column(UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False)
    voter_player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=True)
    voter_name = Column(Text, nullable=True)
    voter_kind = Column(Text, nullable=False, default="player", server_default="player")  # 'player' | 'non_player'
    source = Column(Text, nullable=False, default="self", server_default="self")  # 'self' | 'admin'
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    picks = relationship("VoteBallotPick", cascade="all, delete-orphan", lazy="selectin")


class VoteBallotPick(Base):
    """A ballot's ranked pick — position 1 is the voter's best player. The
    pick's point value is derived from VoteSettings.ballot_values on read."""
    __tablename__ = "vote_ballot_picks"
    __table_args__ = (
        UniqueConstraint("ballot_id", "player_id", name="uq_vote_pick_player"),
    )

    ballot_id = Column(UUID(as_uuid=True), ForeignKey("vote_ballots.id", ondelete="CASCADE"), primary_key=True)
    position = Column(Integer, primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)


class VoteFixtureOverride(Base):
    """Manual lock/reopen for one medal's voting on one fixture, layered over
    the auto-close window (game end + auto_close_days). 'locked' closes voting
    immediately; 'reopened' holds it open past auto-close until locked again.

    Keyed on (medal_id, fixture_id) since migration 267 — locking a count is a
    decision about that medal, not about the fixture in the abstract, and two
    medals over one fixture carry their own auto-close windows anyway."""
    __tablename__ = "vote_fixture_overrides"

    medal_id = Column(UUID(as_uuid=True), ForeignKey("vote_medals.id", ondelete="CASCADE"), primary_key=True)
    fixture_id = Column(UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), primary_key=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    # Nullable since migration 194: a row may exist to carry an eligibility
    # override alone, without also locking or reopening the fixture.
    status = Column(Text, nullable=True)  # 'locked' | 'reopened' | NULL
    eligibility_source = Column(Text, nullable=True)  # overrides the club default
    set_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    set_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class VoteNudge(Base):
    """One reminder-email send, for the Games hub's "Nudge non-voters".

    The audit trail the nudge rate limit reads: at most one nudge per player
    per fixture per medal per 24h (migrations 196, 267), so a manager mashing
    the button can't spam the same player with reminder emails.
    """
    __tablename__ = "vote_nudges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    medal_id = Column(UUID(as_uuid=True), ForeignKey("vote_medals.id", ondelete="CASCADE"), nullable=False)
    fixture_id = Column(UUID(as_uuid=True), ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    sent_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class NetSession(Base):
    """BetterSelect → Net Manager: one net/practice session.

    A net session is a training day, keyed on a date + optional label (e.g.
    "Tuesday senior nets"). Attendance rows hang off it (who turned up, who
    batted) and feed the attendance reports + per-player profile stat. The live
    batting-queue + timer that the net manager runs pitch-side is purely
    client-side (single device); only the durable bits — the session, its timer
    settings and the attendance list — are persisted here. The batting queue and
    timer are persisted too (see version / live_state below): the same admin
    account is routinely open on a phone by the nets and a laptop in the
    clubroom, and both have to see and drive the one session. Club-wide;
    created_by tracks which admin opened it.
    """
    __tablename__ = "net_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    session_date = Column(Date, nullable=False)
    label = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    # The timer/rotation config this session ran with (batting_minutes, nets,
    # auto_roll, sound, alerts[]). Per-session so a tweak mid-season doesn't
    # rewrite history; new sessions seed from the club default (Organisation
    # carries no net column — the default lives in the most recent session).
    settings = Column(JSONB, nullable=True)
    status = Column(Text, nullable=False, server_default="active")  # active | done
    # Bumped by every write that changes what the live screen shows, so a
    # second device polling with the version it last saw is told "nothing has
    # changed" in two fields instead of re-reading the whole session. Always
    # incremented in SQL (version + 1), never read-then-write — see migration 268.
    version = Column(Integer, nullable=False, server_default="0")
    # The batting timer: {running, ends_at, remaining_seconds, duration_seconds,
    # turn_seq}. Here rather than in the browser because every device watching
    # the session has to see the same clock. ends_at is absolute, so each device
    # derives its own countdown from it against the server time it is handed.
    live_state = Column(JSONB, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    organisation = relationship("Organisation")
    attendees = relationship("NetAttendance", back_populates="session", cascade="all, delete-orphan")


class NetAttendance(Base):
    """BetterSelect → Net Manager: one attendee of a net session.

    A row is the check-in — its presence means "turned up". player_id is set for
    a real club player; guest_name carries an ad-hoc attendee (trialist / junior
    / newcomer not yet in the system) and leaves player_id NULL so guests never
    pollute the player tables or reports keyed on player_id. `batted` records
    whether they completed a batting turn (a nice-to-have for the report on top
    of raw attendance). `position` preserves the manager's queue order.
    """
    __tablename__ = "net_attendance"
    __table_args__ = (
        # A real player appears at most once per session; guest rows (player_id
        # NULL) are exempt from the constraint and de-duped by the app layer.
        UniqueConstraint("session_id", "player_id", name="uq_net_attendance_session_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("net_sessions.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=True)
    guest_name = Column(Text, nullable=True)
    batted = Column(Boolean, nullable=False, server_default="false")
    # Turning up and batting are two different facts. Someone who arrives with a
    # sore shoulder, or to bowl, or to keep, is present and counts towards
    # attendance — they just aren't in the batting rotation, and leaving them in
    # it means a net stands empty when their turn comes round (migration 273).
    bats = Column(Boolean, nullable=False, server_default="true")
    # What they said on the way in ("bowling only", "sore back"). Never required.
    note = Column(Text, nullable=True)
    position = Column(Integer, nullable=True)
    # 'admin' (a manager tapped the name) or 'self' (the player scanned the QR
    # code or tapped the NFC tag on the way in). Mirrors
    # player_availability.source and exists for the same reason: a self
    # check-in has no recorded_by to read, so nothing else separates the two.
    # The live screen uses it to announce somebody arriving on their own and
    # stay quiet for a row the manager just added themselves.
    source = Column(Text, nullable=False, server_default="admin")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    session = relationship("NetSession", back_populates="attendees")
    player = relationship("Player")


class NetCheckInRegistration(Base):
    """Someone who scanned in at the nets and was not on the club's list.

    They are checked in as a GUEST (a net_attendance row with player_id NULL),
    never as a player: that guest mechanism has existed since the table was
    written, for exactly this person, and it is what stops a stranger with the
    QR code writing an unvetted row into the club's player table. What they
    typed about themselves lands here instead, `status='pending'`, for an admin
    to turn into a real player or point at somebody already on the roster.

    `previous_club` has no column on `players` and does not get one for this —
    it is one line of free text somebody typed about themselves, and it is kept
    with the rest of what they typed.
    """
    __tablename__ = "net_checkin_registrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    # Both SET NULL: a deleted session must not take the registration with it.
    # The person still turned up, and the club still has to decide about them.
    session_id = Column(UUID(as_uuid=True), ForeignKey("net_sessions.id", ondelete="SET NULL"), nullable=True)
    attendance_id = Column(UUID(as_uuid=True), ForeignKey("net_attendance.id", ondelete="SET NULL"), nullable=True)
    full_name = Column(Text, nullable=False)
    phone = Column(Text, nullable=True)
    email = Column(Text, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    previous_club = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="pending")  # pending | approved | dismissed
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())


class BattingInnings(Base):
    __tablename__ = "batting_innings"
    __table_args__ = (
        UniqueConstraint("game_id", "innings_number", "player_id", name="uq_batting_innings_game_inns_player"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
    innings_number = Column(Integer, default=1)
    runs = Column(Integer)
    balls = Column(Integer)
    fours = Column(Integer)
    sixes = Column(Integer)
    strike_rate = Column(Numeric(6, 2))
    dismissal_type = Column(Text)
    not_out = Column(Boolean, default=False)
    batting_position = Column(Integer)
    did_not_bat = Column(Boolean, default=False)
    # True when the dismissal was a catch by the wicketkeeper ("caught behind").
    # Derived from the dagger (†) marker on the catcher in CA's dismissalText.
    # NULL = unknown (legacy rows pre-backfill, and manual entries) → treated as
    # a plain catch by readers. See migration 075.
    caught_behind = Column(Boolean, nullable=True)

    game = relationship("Game", back_populates="batting_innings")
    player = relationship("Player", back_populates="batting_innings")


class BowlingSpell(Base):
    __tablename__ = "bowling_spells"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
    innings_number = Column(Integer, default=1)
    overs = Column(Numeric(4, 1))
    maidens = Column(Integer)
    runs = Column(Integer)
    wickets = Column(Integer)
    wides = Column(Integer)
    no_balls = Column(Integer)
    economy = Column(Numeric(5, 2))

    game = relationship("Game", back_populates="bowling_spells")
    player = relationship("Player", back_populates="bowling_spells")


class FieldingStat(Base):
    __tablename__ = "fielding_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    catches = Column(Integer, default=0)
    catches_wk = Column(Integer, default=0)
    run_outs = Column(Integer, default=0)
    stumpings = Column(Integer, default=0)
    # A fill-in (borrowed player) or CA-redacted junior's GR scorecard name —
    # set only when player_id is NULL, same pattern as FallOfWicket.batter_name
    # (migration 147).
    player_name = Column(Text, nullable=True)

    game = relationship("Game", back_populates="fielding_stats")
    player = relationship("Player", back_populates="fielding_stats")


class BowlerWicket(Base):
    __tablename__ = "bowler_wickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    innings_number = Column(Integer, nullable=False)
    bowler_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    fielder_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter_name = Column(Text)
    batter_position = Column(Integer)
    # Denormalised from the dismissed batter's scorecard row. We don't store
    # opposition batting in batting_innings, so without these columns we have
    # no way to derive 'ducks/golden ducks inflicted'.
    batter_runs = Column(Integer, nullable=True)
    batter_balls = Column(Integer, nullable=True)
    dismissal_type = Column(Text, nullable=False)
    # True when a caught dismissal was taken by the wicketkeeper ("caught
    # behind"). Derived from the dagger (†) on the catcher in dismissalText.
    # NULL = unknown (legacy rows until rebuilt). See migration 076.
    caught_behind = Column(Boolean, nullable=True)


class GameAppearance(Base):
    __tablename__ = "game_appearances"

    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), primary_key=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), primary_key=True)
    team_name = Column(Text, nullable=True)
    is_captain = Column(Boolean, default=False, nullable=False, server_default='false')
    is_wicket_keeper = Column(Boolean, default=False, nullable=False, server_default='false')

    game = relationship("Game", back_populates="appearances")
    player = relationship("Player", back_populates="appearances")


class FallOfWicket(Base):
    __tablename__ = "fall_of_wickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    innings_number = Column(Integer, nullable=False)
    wicket_number = Column(Integer, nullable=False)
    score_at_fall = Column(Integer)
    overs_at_fall = Column(Numeric(5, 1))
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    # The dismissed batter's scorecard name. Set for every FOW row (both teams);
    # for opposition batters player_id is NULL, so this is the only name we hold.
    batter_name = Column(Text, nullable=True)

    game = relationship("Game", back_populates="fall_of_wickets")
    player = relationship("Player")


class Partnership(Base):
    __tablename__ = "partnerships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"))
    innings_number = Column(Integer, nullable=False)
    wicket_number = Column(Integer, nullable=False)
    batter1_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter2_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    runs = Column(Integer, default=0)
    balls = Column(Integer)
    batter1_runs = Column(Integer)
    batter2_runs = Column(Integer)
    is_club_innings = Column(Boolean, nullable=True)
    # A fill-in (borrowed player) or CA-redacted junior's GR scorecard name for
    # whichever side has no batterN_id — same pattern as FallOfWicket.batter_name
    # (migration 147).
    batter1_name = Column(Text, nullable=True)
    batter2_name = Column(Text, nullable=True)

    game = relationship("Game", back_populates="partnerships")
    batter1 = relationship("Player", foreign_keys=[batter1_id])
    batter2 = relationship("Player", foreign_keys=[batter2_id])


class Milestone(Base):
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="SET NULL"), nullable=True)
    milestone_type = Column(Text, nullable=False)
    milestone_value = Column(Integer, nullable=False)
    achieved_at = Column(Date)
    detail = Column(Text)

    player = relationship("Player", back_populates="milestones")
    game = relationship("Game")


class PlayerSeasonGradeStats(Base):
    __tablename__ = "player_season_grade_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "season_id", "grade_id", name="uq_player_season_grade"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    grade_id  = Column(UUID(as_uuid=True), ForeignKey("grades.id",  ondelete="CASCADE"), nullable=False)
    matches          = Column(Integer, default=0)
    batting_innings  = Column(Integer, default=0)
    runs             = Column(Integer, default=0)
    not_outs         = Column(Integer, default=0)
    high_score       = Column(Integer)
    bowling_innings  = Column(Integer, default=0)
    wickets          = Column(Integer, default=0)
    runs_conceded    = Column(Integer, default=0)
    catches          = Column(Integer, default=0)
    run_outs         = Column(Integer, default=0)
    stumpings        = Column(Integer, default=0)
    synced_at        = Column(TIMESTAMP(timezone=True))


class PlayerSeasonStats(Base):
    __tablename__ = "player_season_stats"
    __table_args__ = (UniqueConstraint("player_id", "season_id", name="uq_player_season"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    # Batting
    matches = Column(Integer, default=0)
    batting_innings = Column(Integer, default=0)
    runs = Column(Integer, default=0)
    not_outs = Column(Integer, default=0)
    balls_faced = Column(Integer, default=0)
    fifties = Column(Integer, default=0)
    hundreds = Column(Integer, default=0)
    ducks = Column(Integer, default=0)
    high_score = Column(Integer)
    is_hs_not_out = Column(Boolean, default=False)
    batting_average = Column(Numeric(8, 2))
    batting_strike_rate = Column(Numeric(8, 2))
    fours = Column(Integer, default=0)
    sixes = Column(Integer, default=0)
    batting_minutes = Column(Integer, default=0)
    # Bowling
    bowling_innings = Column(Integer, default=0)
    wickets = Column(Integer, default=0)
    overs = Column(Numeric(8, 1), default=0)
    bowling_balls = Column(Integer, default=0)
    runs_conceded = Column(Integer, default=0)
    maidens = Column(Integer, default=0)
    bowling_economy = Column(Numeric(6, 2))
    bowling_average = Column(Numeric(8, 2))
    bowling_strike_rate = Column(Numeric(6, 2))
    best_bowling_wickets = Column(Integer)
    best_bowling_figures = Column(Text)
    five_wicket_innings = Column(Integer, default=0)
    wides = Column(Integer, default=0)
    no_balls = Column(Integer, default=0)
    # Fielding
    catches = Column(Integer, default=0)
    catches_wk = Column(Integer, default=0)
    catches_non_wk = Column(Integer, default=0)
    run_outs = Column(Integer, default=0)
    assisted_run_outs = Column(Integer, default=0)
    unassisted_run_outs = Column(Integer, default=0)
    stumpings = Column(Integer, default=0)
    source = Column(Text, nullable=False, server_default='api')

    player = relationship("Player", back_populates="season_stats")
    season = relationship("Season", back_populates="player_stats")


class ManualPartnershipRecord(Base):
    __tablename__ = "manual_partnership_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    batter1_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter1_name = Column(Text, nullable=False)
    batter2_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter2_name = Column(Text, nullable=False)
    grade_name = Column(Text, nullable=False)
    season_year = Column(Integer, nullable=False)
    wicket_number = Column(Integer, nullable=False)
    runs = Column(Integer, nullable=False)
    is_not_out = Column(Boolean, server_default="false", nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    org = relationship("Organisation")
    batter1 = relationship("Player", foreign_keys=[batter1_id])
    batter2 = relationship("Player", foreign_keys=[batter2_id])


# ─── Manual entry tables (historical stat backfill) ──────────────────────────


class ManualGame(Base):
    __tablename__ = "manual_games"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    played_at = Column(Date, nullable=True)
    home_team = Column(Text, nullable=True)
    away_team = Column(Text, nullable=True)
    opposition = Column(Text, nullable=True)
    venue = Column(Text, nullable=True)
    result = Column(Text, nullable=True)
    winning_team = Column(Text, nullable=True)
    is_final = Column(Boolean, server_default="false", nullable=False)
    match_format = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    # Opposition club's Grassroots org GUID (from the CA club search), so the manual
    # game links up with head-to-head / BetterIQ opponent matching the same way a
    # synced game's games.opp_org_id does. The display name lives in `opposition`.
    opp_org_id = Column(Text, nullable=True)
    # Full both-team scorecard the AI scorecard upload extracted (both innings,
    # opposition batting/bowling, fall of wickets, toss, extras). Source of truth for
    # rendering the OPPOSITION half of the match view (migration 091).
    extracted_payload = Column(JSONB, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    organisation = relationship("Organisation")
    season = relationship("Season")
    grade = relationship("Grade")
    batting_innings = relationship("ManualBattingInnings", back_populates="manual_game", cascade="all, delete-orphan")
    bowling_spells = relationship("ManualBowlingSpell", back_populates="manual_game", cascade="all, delete-orphan")
    fielding_stats = relationship("ManualFieldingStat", back_populates="manual_game", cascade="all, delete-orphan")


class ManualBattingInnings(Base):
    __tablename__ = "manual_batting_innings"
    __table_args__ = (
        UniqueConstraint("manual_game_id", "innings_number", "player_id", name="uq_manual_batting_game_inns_player"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_game_id = Column(UUID(as_uuid=True), ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    innings_number = Column(Integer, server_default="1", nullable=False)
    batting_position = Column(Integer, nullable=True)
    runs = Column(Integer, server_default="0", nullable=False)
    balls = Column(Integer, nullable=True)
    # NULL = the card didn't track it (migration 184); 0 = a tracked zero.
    fours = Column(Integer, server_default="0", nullable=True)
    sixes = Column(Integer, server_default="0", nullable=True)
    strike_rate = Column(Numeric(6, 2), nullable=True)
    dismissal_type = Column(Text, nullable=True)
    not_out = Column(Boolean, server_default="false", nullable=False)
    did_not_bat = Column(Boolean, server_default="false", nullable=False)

    manual_game = relationship("ManualGame", back_populates="batting_innings")
    player = relationship("Player")


class ManualBowlingSpell(Base):
    __tablename__ = "manual_bowling_spells"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_game_id = Column(UUID(as_uuid=True), ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    innings_number = Column(Integer, server_default="1", nullable=False)
    overs = Column(Numeric(4, 1), nullable=True)
    # NULL maidens/wides/no_balls = the card didn't track them (migration 184).
    maidens = Column(Integer, server_default="0", nullable=True)
    runs = Column(Integer, server_default="0", nullable=False)
    wickets = Column(Integer, server_default="0", nullable=False)
    wides = Column(Integer, server_default="0", nullable=True)
    no_balls = Column(Integer, server_default="0", nullable=True)
    economy = Column(Numeric(5, 2), nullable=True)

    manual_game = relationship("ManualGame", back_populates="bowling_spells")
    player = relationship("Player")


class ManualFieldingStat(Base):
    __tablename__ = "manual_fielding_stats"
    __table_args__ = (
        UniqueConstraint("manual_game_id", "player_id", name="uq_manual_fielding_game_player"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_game_id = Column(UUID(as_uuid=True), ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    catches = Column(Integer, server_default="0", nullable=False)
    catches_wk = Column(Integer, server_default="0", nullable=False)
    run_outs = Column(Integer, server_default="0", nullable=False)
    stumpings = Column(Integer, server_default="0", nullable=False)
    # Always NULL for a manually-uploaded card (player_id is required here) —
    # present only so v_effective_fielding_stats' column list matches
    # `fielding_stats` (migration 147).
    player_name = Column(Text, nullable=True)

    manual_game = relationship("ManualGame", back_populates="fielding_stats")
    player = relationship("Player")


class ManualFallOfWicket(Base):
    __tablename__ = "manual_fall_of_wickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_game_id = Column(UUID(as_uuid=True), ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False)
    innings_number = Column(Integer, nullable=False)
    wicket_number = Column(Integer, nullable=False)
    score_at_fall = Column(Integer, nullable=True)
    overs_at_fall = Column(Numeric(5, 1), nullable=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter_name = Column(Text, nullable=True)


class ManualBowlerWicket(Base):
    __tablename__ = "manual_bowler_wickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_game_id = Column(UUID(as_uuid=True), ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False)
    innings_number = Column(Integer, nullable=False)
    bowler_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    fielder_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter_name = Column(Text, nullable=True)
    batter_position = Column(Integer, nullable=True)
    batter_runs = Column(Integer, nullable=True)
    batter_balls = Column(Integer, nullable=True)
    dismissal_type = Column(Text, nullable=False)
    caught_behind = Column(Boolean, nullable=True)


class ManualPartnership(Base):
    __tablename__ = "manual_partnerships"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_game_id = Column(UUID(as_uuid=True), ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False)
    innings_number = Column(Integer, nullable=False)
    wicket_number = Column(Integer, nullable=False)
    batter1_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    batter2_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    runs = Column(Integer, server_default="0", nullable=True)
    balls = Column(Integer, nullable=True)
    batter1_runs = Column(Integer, nullable=True)
    batter2_runs = Column(Integer, nullable=True)
    is_club_innings = Column(Boolean, nullable=True)
    # Always NULL for a manually-uploaded card (an admin types in real
    # identities) — present only so v_effective_partnerships' column list
    # matches `partnerships` (migration 147).
    batter1_name = Column(Text, nullable=True)
    batter2_name = Column(Text, nullable=True)


class ManualSeasonAdjustment(Base):
    __tablename__ = "manual_season_adjustments"
    __table_args__ = (
        UniqueConstraint("player_id", "season_id", "grade_id", name="uq_manual_season_adj_player_season_grade"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    games_played = Column(Integer, server_default="0", nullable=False)
    batting_innings = Column(Integer, server_default="0", nullable=False)
    batting_runs = Column(Integer, server_default="0", nullable=False)
    batting_not_outs = Column(Integer, server_default="0", nullable=False)
    batting_balls = Column(Integer, server_default="0", nullable=False)
    batting_fours = Column(Integer, server_default="0", nullable=False)
    batting_sixes = Column(Integer, server_default="0", nullable=False)
    batting_fifties = Column(Integer, server_default="0", nullable=False)
    batting_hundreds = Column(Integer, server_default="0", nullable=False)
    batting_ducks = Column(Integer, server_default="0", nullable=False)
    batting_high_score = Column(Integer, nullable=True)
    batting_high_score_not_out = Column(Boolean, server_default="false", nullable=False)
    bowling_innings = Column(Integer, server_default="0", nullable=False)
    bowling_overs = Column(Numeric(8, 1), server_default="0", nullable=False)
    bowling_balls = Column(Integer, server_default="0", nullable=False)
    bowling_maidens = Column(Integer, server_default="0", nullable=False)
    bowling_runs = Column(Integer, server_default="0", nullable=False)
    bowling_wickets = Column(Integer, server_default="0", nullable=False)
    bowling_wides = Column(Integer, server_default="0", nullable=False)
    bowling_no_balls = Column(Integer, server_default="0", nullable=False)
    bowling_five_wicket_innings = Column(Integer, server_default="0", nullable=False)
    bowling_best_wickets = Column(Integer, nullable=True)
    bowling_best_figures = Column(Text, nullable=True)
    fielding_catches = Column(Integer, server_default="0", nullable=False)
    fielding_catches_wk = Column(Integer, server_default="0", nullable=False)
    fielding_run_outs = Column(Integer, server_default="0", nullable=False)
    fielding_stumpings = Column(Integer, server_default="0", nullable=False)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    organisation = relationship("Organisation")
    player = relationship("Player")
    season = relationship("Season")
    grade = relationship("Grade")


class ManualCareerAdjustment(Base):
    __tablename__ = "manual_career_adjustments"
    __table_args__ = (
        UniqueConstraint("player_id", "organisation_id", name="uq_manual_career_adj_player_org"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    games_played = Column(Integer, server_default="0", nullable=False)
    batting_innings = Column(Integer, server_default="0", nullable=False)
    batting_runs = Column(Integer, server_default="0", nullable=False)
    batting_not_outs = Column(Integer, server_default="0", nullable=False)
    batting_balls = Column(Integer, server_default="0", nullable=False)
    batting_fours = Column(Integer, server_default="0", nullable=False)
    batting_sixes = Column(Integer, server_default="0", nullable=False)
    batting_fifties = Column(Integer, server_default="0", nullable=False)
    batting_hundreds = Column(Integer, server_default="0", nullable=False)
    batting_ducks = Column(Integer, server_default="0", nullable=False)
    batting_high_score = Column(Integer, nullable=True)
    batting_high_score_not_out = Column(Boolean, server_default="false", nullable=False)
    bowling_innings = Column(Integer, server_default="0", nullable=False)
    bowling_overs = Column(Numeric(8, 1), server_default="0", nullable=False)
    bowling_balls = Column(Integer, server_default="0", nullable=False)
    bowling_maidens = Column(Integer, server_default="0", nullable=False)
    bowling_runs = Column(Integer, server_default="0", nullable=False)
    bowling_wickets = Column(Integer, server_default="0", nullable=False)
    bowling_five_wicket_innings = Column(Integer, server_default="0", nullable=False)
    bowling_best_wickets = Column(Integer, nullable=True)
    bowling_best_figures = Column(Text, nullable=True)
    fielding_catches = Column(Integer, server_default="0", nullable=False)
    fielding_catches_wk = Column(Integer, server_default="0", nullable=False)
    fielding_run_outs = Column(Integer, server_default="0", nullable=False)
    fielding_stumpings = Column(Integer, server_default="0", nullable=False)
    notes = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    organisation = relationship("Organisation")
    player = relationship("Player")


class ManualEditLog(Base):
    __tablename__ = "manual_edit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(Text, nullable=False)
    target_table = Column(Text, nullable=False)
    target_id = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    before_json = Column(JSONB, nullable=True)
    after_json = Column(JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    undone_at = Column(TIMESTAMP(timezone=True), nullable=True)
    undone_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


# ─── BetterImport — overlap-safe historical CSV import (migration 070) ────────
#
# A club's uploaded summary is stored as *authoritative truth* in
# ``imported_stats``; the reconciler (services/import_reconcile.py) derives only
# the non-GR remainder into ``import_effective_deltas`` (read by the effective
# view's 5th branch). The only thing ever added to GR is ``max(0, club − GR)``,
# so the career total is pinned to the club's figure and can't double-count.


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    filename = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="draft")  # draft | committed | undone
    granularity = Column(Text, nullable=True)  # career | season | grade | unknown
    column_mapping = Column(JSONB, nullable=False, server_default="{}")
    row_count = Column(Integer, nullable=False, server_default="0")
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    committed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    undone_at = Column(TIMESTAMP(timezone=True), nullable=True)

    organisation = relationship("Organisation")


class ImportedStat(Base):
    """Immutable record of what a club uploaded — the source of truth.

    Column names mirror ManualCareerAdjustment. ``scope`` is 'career' (a
    whole-career total) or 'season' (one season). The ``provided_*`` columns
    hold the derived figures the club literally gave (avg/SR/econ); the raw
    component columns are reconstructed from them at import time when absent.
    """

    __tablename__ = "imported_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    import_batch_id = Column(UUID(as_uuid=True), ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    scope = Column(Text, nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True)
    season_label = Column(Text, nullable=True)
    grade_label = Column(Text, nullable=True)
    is_prior_bucket = Column(Boolean, server_default="false", nullable=False)
    games_played = Column(Integer, server_default="0", nullable=False)
    batting_innings = Column(Integer, server_default="0", nullable=False)
    batting_runs = Column(Integer, server_default="0", nullable=False)
    batting_not_outs = Column(Integer, server_default="0", nullable=False)
    batting_balls = Column(Integer, server_default="0", nullable=False)
    batting_fours = Column(Integer, server_default="0", nullable=False)
    batting_sixes = Column(Integer, server_default="0", nullable=False)
    batting_fifties = Column(Integer, server_default="0", nullable=False)
    batting_hundreds = Column(Integer, server_default="0", nullable=False)
    batting_ducks = Column(Integer, server_default="0", nullable=False)
    batting_high_score = Column(Integer, nullable=True)
    batting_high_score_not_out = Column(Boolean, server_default="false", nullable=False)
    bowling_innings = Column(Integer, server_default="0", nullable=False)
    bowling_overs = Column(Numeric(8, 1), server_default="0", nullable=False)
    bowling_balls = Column(Integer, server_default="0", nullable=False)
    bowling_maidens = Column(Integer, server_default="0", nullable=False)
    bowling_runs = Column(Integer, server_default="0", nullable=False)
    bowling_wickets = Column(Integer, server_default="0", nullable=False)
    bowling_wides = Column(Integer, server_default="0", nullable=False)
    bowling_no_balls = Column(Integer, server_default="0", nullable=False)
    bowling_five_wicket_innings = Column(Integer, server_default="0", nullable=False)
    bowling_best_wickets = Column(Integer, nullable=True)
    bowling_best_figures = Column(Text, nullable=True)
    fielding_catches = Column(Integer, server_default="0", nullable=False)
    fielding_catches_wk = Column(Integer, server_default="0", nullable=False)
    fielding_run_outs = Column(Integer, server_default="0", nullable=False)
    fielding_stumpings = Column(Integer, server_default="0", nullable=False)
    provided_batting_average = Column(Numeric(8, 2), nullable=True)
    provided_batting_strike_rate = Column(Numeric(8, 2), nullable=True)
    provided_bowling_average = Column(Numeric(8, 2), nullable=True)
    provided_bowling_economy = Column(Numeric(6, 2), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    organisation = relationship("Organisation")
    player = relationship("Player")
    season = relationship("Season")
    batch = relationship("ImportBatch")


class ImportEffectiveDelta(Base):
    """Derived, regenerable: the non-GR remainder the reconciler emits.

    Read by ``v_effective_player_season_stats``'s ``'import'`` branch. Wiped and
    rebuilt per org on every reconcile, so it never goes stale and never touches
    the hand-entered manual_* tables. Column names match the view's output.
    """

    __tablename__ = "import_effective_deltas"

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    scope = Column(Text, nullable=False)  # season | career
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="SET NULL"), nullable=True)
    grade_id = Column(UUID(as_uuid=True), ForeignKey("grades.id", ondelete="SET NULL"), nullable=True)
    # Free-text grade name (migration 154), set on career-scope residual rows
    # reconciled against a grade-scoped upload — a career residual spans many
    # seasons' worth of same-named grades, so unlike a season delta's exact
    # grade_id it can only be matched by name (mirrors ImportedStat.grade_label
    # and aggregations._GRADE_MATCH's fuzzy/merge-aware matching).
    grade_label = Column(Text, nullable=True)
    matches = Column(Integer, server_default="0", nullable=False)
    batting_innings = Column(Integer, server_default="0", nullable=False)
    runs = Column(Integer, server_default="0", nullable=False)
    not_outs = Column(Integer, server_default="0", nullable=False)
    balls_faced = Column(Integer, server_default="0", nullable=False)
    fifties = Column(Integer, server_default="0", nullable=False)
    hundreds = Column(Integer, server_default="0", nullable=False)
    ducks = Column(Integer, server_default="0", nullable=False)
    fours = Column(Integer, server_default="0", nullable=False)
    sixes = Column(Integer, server_default="0", nullable=False)
    high_score = Column(Integer, nullable=True)
    is_hs_not_out = Column(Boolean, server_default="false", nullable=False)
    bowling_innings = Column(Integer, server_default="0", nullable=False)
    wickets = Column(Integer, server_default="0", nullable=False)
    overs = Column(Numeric(8, 1), server_default="0", nullable=False)
    bowling_balls = Column(Integer, server_default="0", nullable=False)
    runs_conceded = Column(Integer, server_default="0", nullable=False)
    maidens = Column(Integer, server_default="0", nullable=False)
    best_bowling_wickets = Column(Integer, nullable=True)
    best_bowling_figures = Column(Text, nullable=True)
    five_wicket_innings = Column(Integer, server_default="0", nullable=False)
    wides = Column(Integer, server_default="0", nullable=False)
    no_balls = Column(Integer, server_default="0", nullable=False)
    catches = Column(Integer, server_default="0", nullable=False)
    catches_wk = Column(Integer, server_default="0", nullable=False)
    run_outs = Column(Integer, server_default="0", nullable=False)
    stumpings = Column(Integer, server_default="0", nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class PlayerSyncRequest(Base):
    __tablename__ = "player_sync_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, server_default="pending", nullable=False)
    requester_note = Column(Text, nullable=True)
    admin_note = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)

    player = relationship("Player")
    org = relationship("Organisation")


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=True)
    kind = Column(Text, nullable=False)
    # 'running' | 'success' | 'error' | 'paused' | 'cancelled' — unconstrained
    # Text column, same as always; 'paused'/'cancelled' added by migration 161.
    status = Column(Text, nullable=False, server_default="running")
    started_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    stats = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    # Pending pause/cancel signal (migration 161): NULL | 'pause' | 'cancel'.
    # Set by an operator action, cleared once the run's own loop checkpoint
    # (services/sync.py::_check_sync_control) notices and finalizes it.
    control = Column(Text, nullable=True)
    # Who kicked this run off (migration 186) — the club admin (or super admin
    # acting as the club) whose click started it. NULL for system-initiated
    # runs (the weekly scheduler, a self-serve club's first auto-sync) and for
    # runs auto-resumed after a restart where the original trigger's user is
    # carried forward. Powers the "who started it" column on the Super Admin
    # Usage page's Current Background Processes panel.
    triggered_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class OppositionDossier(Base):
    """BetterIQ — cached opponent scouting dossier (assembled live report).

    Keyed by (organisation_id, opp_key). ``payload`` is the fully assembled
    dossier JSON: the opponent's current-season squad + form pulled live from
    the grade's scorecards, plus player-level head-to-head vs us. Built on
    demand; ``status`` drives the build/poll UX and ``built_at`` lets the reader
    apply a freshness TTL + offer a manual refresh. Opponent player stats are
    deliberately *not* normalised into their own tables — this cache is the only
    place live opponent data lands (keeps the data-rights surface small and
    avoids an opponent-stats schema).
    """
    __tablename__ = "opposition_dossiers"
    __table_args__ = (
        UniqueConstraint("organisation_id", "opp_key", name="uq_dossier_org_opp"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    opp_key = Column(Text, nullable=False)
    opp_name = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="building")  # building | ready | error
    payload = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    built_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class SavedReport(Base):
    __tablename__ = "saved_reports"
    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_saved_reports_org_slug"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    slug = Column(Text, nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    query_json = Column(JSONB, nullable=False)
    visibility = Column(Text, nullable=False, server_default="club")
    view_count = Column(Integer, nullable=False, server_default="0")
    # Club-visibility reports start as 'pending' and only show on the public
    # list after an admin approves them. Private and admin-authored reports
    # are auto-approved on save. Values: 'pending' | 'approved' | 'rejected'.
    status = Column(Text, nullable=False, server_default="approved")
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    review_note = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class PhqIdSuggestion(Base):
    __tablename__ = "phq_id_suggestions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=True)
    phq_player_id = Column(Text, nullable=False)
    phq_first_name = Column(Text, nullable=True)
    phq_last_name = Column(Text, nullable=True)
    confidence = Column(Text, nullable=False)  # 'auto' | 'high' | 'low'
    game_count = Column(Integer, server_default="1")
    status = Column(Text, server_default="pending", nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)

    org = relationship("Organisation")
    player = relationship("Player", foreign_keys=[player_id])


class Family(Base):
    __tablename__ = "families"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_families_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    members = relationship("FamilyMember", back_populates="family", cascade="all, delete-orphan")


class FamilyMember(Base):
    __tablename__ = "family_members"
    __table_args__ = (
        UniqueConstraint("family_id", "player_id", name="uq_family_member_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    family_id = Column(UUID(as_uuid=True), ForeignKey("families.id", ondelete="CASCADE"), nullable=False)
    # Nullable (migration 175): a non-playing family member (a parent who
    # isn't a registered player) has no player_id at all — see fee_member_id
    # below. An existing row always has exactly one of the two set; new code
    # should treat "which one is set" as the row's kind (player vs fee member).
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=True)
    # A non-playing family member — parents/guardians and anyone else who's a
    # fee_members row (see FeeMember: "manual members ... have player_id
    # NULL") but not themselves a Player (migration 175).
    fee_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=True)
    # This member is a responsible adult for the family's minors (migration 175).
    is_guardian = Column(Boolean, nullable=False, server_default="false", default=False)
    # Lets a separated parent opt out of "email the whole family" while
    # staying part of the family's structure (migration 175).
    receives_family_comms = Column(Boolean, nullable=False, server_default="true", default=True)
    relationship_label = Column("relationship", Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    family = relationship("Family", back_populates="members")
    player = relationship("Player")
    fee_member = relationship("FeeMember")


# ───────────────────────────────────────────────────────────────────────────
# Fee Tracking (migration 041)
#
# A self-contained membership/match-fee ledger that lives alongside the stats
# data. Every fee-paying person is a `fee_members` row; the financial state
# for a given season is a `fee_member_seasons` row pointing at one
# `fee_schedule` tier. Match-day fees accrue as `fee_match_days` rows, mostly
# auto-derived from GameAppearance each sync (admins can override). Payments
# are reconciled by hand against bank statements (`fee_payments`).
#
# The money is driven entirely by the member's tier (fee_schedule), never the
# format: match fee = days_played × tier.match_day_rate. Format only affects
# how many days a game contributes (two-day = 2) and which report bucket it
# lands in.
# ───────────────────────────────────────────────────────────────────────────

# Payment-type values on a fee_schedule tier.
FEE_PAYMENT_TYPES = ("standard", "upfront", "complimentary", "left_club")
# fee_match_days.fee_format / Grade.fee_format values.
FEE_FORMATS = ("two_day", "one_day", "t20", "women", "exclude")
# fee_member_seasons.status values (migration 175) — the per-season
# membership lifecycle.
MEMBERSHIP_STATUSES = (
    "prospect", "invited", "application_started", "awaiting_documents",
    "awaiting_payment", "active", "suspended", "expired", "archived",
)


class MembershipType(Base):
    """A club-adopted membership category (Senior Player, Parent, Life
    Member, Coach, Committee Member, …) — migration 175. Cross-season,
    unlike FeeSchedule ($ tiers, re-created per season): a type's descriptive
    attributes (voting rights, WWCC required, …) don't change season to
    season. Nothing is seeded automatically — a club adopts a starter set (or
    none at all) via services/membership_types.py, same "may or may not
    apply" posture as the CRM tracker templates."""
    __tablename__ = "membership_types"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_membership_types_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    default_annual_fee = Column(Numeric(10, 2), nullable=True)
    is_playing = Column(Boolean, nullable=False, server_default="false", default=False)
    requires_voting_rights = Column(Boolean, nullable=False, server_default="false", default=False)
    requires_insurance = Column(Boolean, nullable=False, server_default="false", default=False)
    requires_wwcc = Column(Boolean, nullable=False, server_default="false", default=False)
    requires_playhq_registration = Column(Boolean, nullable=False, server_default="false", default=False)
    comms_group = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    # 'internal' | 'external' (migration 248). Internal = a member the club
    # counts; external = someone it records but has not gained as a member (a
    # sponsor's contact, a contractor, an association officer). What makes a
    # membership count answerable.
    scope = Column(Text, nullable=False, server_default="internal", default="internal")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FeeSchedule(Base):
    """A membership tier for one season — the spreadsheet's PARMS rate card.

    `membership_amount` is the one-off membership fee; `match_day_rate` is the
    per-day match fee (0 for Upfront tiers, who prepay via membership).
    """
    __tablename__ = "fee_schedule"
    __table_args__ = (
        UniqueConstraint("season_id", "name", name="uq_fee_schedule_season_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    payment_type = Column(Text, nullable=False, server_default="standard")
    membership_amount = Column(Numeric(10, 2), nullable=False, server_default="0")
    match_day_rate = Column(Numeric(10, 2), nullable=False, server_default="0")
    display_order = Column(Integer, nullable=False, server_default="0")
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FeeMember(Base):
    """A fee-paying person. Linked to a stats Player where one exists; manual
    members (life members, sponsors, ICL who don't play) have player_id NULL.

    `current_tier` carries forward season-to-season: it seeds the tier when a
    new member-season is opened, and is updated whenever an admin sets a tier.
    """
    __tablename__ = "fee_members"
    __table_args__ = (
        UniqueConstraint("organisation_id", "player_id", name="uq_fee_member_org_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    full_name = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    mobile = Column(Text, nullable=True)
    # Name of the fee_schedule tier this member currently sits in (carry-forward
    # default). Not a FK — schedules are per-season, this is a cross-season hint.
    current_tier = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    # Membership Management (migration 175): the catalogue entry this member
    # holds (Senior Player, Parent, Coach, …) — cross-season, distinct from the
    # per-season fee_schedule $ tier. Life/honorary status is cross-season too
    # (it doesn't reset each season the way a fee_schedule tier does).
    membership_type_id = Column(UUID(as_uuid=True), ForeignKey("membership_types.id", ondelete="SET NULL"), nullable=True)
    is_life_member = Column(Boolean, nullable=False, server_default="false", default=False)
    # Migration 248/249. The honour's own date, and free text beside it for
    # whatever the club records against it — usually a life member number.
    life_member_since = Column(Date, nullable=True)
    life_member_detail = Column(Text, nullable=True)
    # Migration 249. Gender lived only on `players`, so a social member or a
    # sponsor's contact had nowhere to carry one. Read precedence is the same as
    # email/mobile: this value, falling back to the linked player's.
    gender = Column(Text, nullable=True)
    is_honorary = Column(Boolean, nullable=False, server_default="false", default=False)
    honorary_expires_at = Column(Date, nullable=True)  # NULL + is_honorary = perpetual
    # Soft-delete (migration 212). The Directory hides an archived person and
    # the pickers stop offering them, but nothing is destroyed, so a record that
    # already names one still resolves. The column has existed since 212 and was
    # only ever read through raw SQL; mapping it lets the ORM readers see it too.
    archived_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    player = relationship("Player")
    membership_type = relationship("MembershipType")
    seasons = relationship("FeeMemberSeason", back_populates="member", cascade="all, delete-orphan")


class FeeMemberSeason(Base):
    """A member's financial state for one season. fee_schedule_id NULL means
    'needs a tier assigned' — the review queue surfaced on the Members page."""
    __tablename__ = "fee_member_seasons"
    __table_args__ = (
        UniqueConstraint("member_id", "season_id", name="uq_fee_member_season"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False)
    season_id = Column(UUID(as_uuid=True), ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    fee_schedule_id = Column(UUID(as_uuid=True), ForeignKey("fee_schedule.id", ondelete="SET NULL"), nullable=True)
    is_new_registration = Column(Boolean, nullable=False, server_default="false")
    membership_payment_method = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    # Per-season membership lifecycle (migration 175): prospect | invited |
    # application_started | awaiting_documents | awaiting_payment | active |
    # suspended | expired | archived. Defaults to 'active' so every row that
    # existed before this migration reads exactly as it did before.
    status = Column(Text, nullable=False, server_default="active", default="active")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    # Fee-owing reminder throttle (migration 178) — same purpose as
    # MemberQualification.last_reminder_sent_at, kept separate since the two
    # reminder kinds fire independently.
    last_fee_reminder_sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # PlayHQ registration (migration 235) — a club-side checkbox, not a synced
    # fact: PlayHQ registration is a per-season playing requirement with no
    # API this app can read it back from, so an admin ticks it once they've
    # sighted it. Deliberately NOT carried forward by rollover (registration
    # has to be redone every season) — a rolled-over row always starts
    # unticked, same as any other new member-season.
    playhq_registered = Column(Boolean, nullable=False, server_default="false", default=False)
    playhq_registered_at = Column(TIMESTAMP(timezone=True), nullable=True)

    member = relationship("FeeMember", back_populates="seasons")
    schedule = relationship("FeeSchedule")
    match_days = relationship("FeeMatchDay", back_populates="member_season", cascade="all, delete-orphan")
    payments = relationship("FeePayment", back_populates="member_season", cascade="all, delete-orphan")


class FeeMatchDay(Base):
    """One game's contribution to a member's match-day count. Auto-derived from
    GameAppearance during sync; `auto_derived=False` once an admin overrides it
    (e.g. drops a two-day game from 2 days to 1), which makes sync leave it
    alone thereafter.

    `paid_payment_id` links to the FeePayment that settled this match day. The
    'Mark Paid' button creates a payment and links it here; deleting the
    payment from the Payments page nulls this out (FK ON DELETE SET NULL).
    A single bulk payment can settle multiple match-day rows, so multiple
    rows may share the same `paid_payment_id`.

    `waived_at` (when set) forgives this one game's fee: the game settles (member
    reads 'Financial', the row shows 'Waived') but it is NOT money the club
    received, so a waiver is stored here rather than as a FeePayment and never
    enters the payment/income totals. Waived games are skipped by
    allocate_match_days (they consume none of the member's match-fee money) and
    excluded from match_fee_payable. Reversible by clearing the flag."""
    __tablename__ = "fee_match_days"
    __table_args__ = (
        UniqueConstraint("member_season_id", "game_id", name="uq_fee_match_day_member_game"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_season_id = Column(UUID(as_uuid=True), ForeignKey("fee_member_seasons.id", ondelete="CASCADE"), nullable=False)
    game_id = Column(UUID(as_uuid=True), ForeignKey("games.id", ondelete="CASCADE"), nullable=True)
    played_at = Column(Date, nullable=True)
    fee_format = Column(Text, nullable=True)
    days_played = Column(Numeric(3, 1), nullable=False, server_default="1")
    auto_derived = Column(Boolean, nullable=False, server_default="true")
    paid_payment_id = Column(UUID(as_uuid=True), ForeignKey("fee_payments.id", ondelete="SET NULL"), nullable=True)
    waived_at = Column(TIMESTAMP(timezone=True), nullable=True)
    waived_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    waive_reason = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    member_season = relationship("FeeMemberSeason", back_populates="match_days")
    game = relationship("Game")
    paid_payment = relationship("FeePayment", foreign_keys=[paid_payment_id])


class FeePayment(Base):
    """A payment reconciled against a bank statement, or (since the Square
    import) a completed Square sale a club admin matched to a member.
    `source` ('manual' | 'square') + `external_ref` (the Square line-item ref,
    NULL for manual rows) mirror `merch_movements`' own dedupe pattern — a
    unique index on (organisation_id, external_ref) stops a re-run of the
    Square import from double-recording the same sale."""
    __tablename__ = "fee_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    member_season_id = Column(UUID(as_uuid=True), ForeignKey("fee_member_seasons.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False, server_default="0")
    paid_at = Column(Date, nullable=True)
    kind = Column(Text, nullable=False, server_default="membership")  # 'membership' | 'match_day'
    method = Column(Text, nullable=True)
    bank_ref = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    source = Column(Text, nullable=False, server_default="manual")  # 'manual' | 'square'
    external_ref = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    member_season = relationship("FeeMemberSeason", back_populates="payments")


class FeeSquareImportLog(Base):
    """One row per Square sale a BetterFees admin has resolved (applied or
    dismissed) in the Square import review queue — keyed by `external_ref` so
    a resolved sale (either way) never resurfaces on the next preview, even
    though the preview itself is stateless (it re-scans Square on every call
    rather than tracking a sync cursor)."""
    __tablename__ = "fee_square_import_log"
    __table_args__ = (
        UniqueConstraint("organisation_id", "external_ref", name="uq_fee_square_import_log_ref"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    external_ref = Column(Text, nullable=False)
    status = Column(Text, nullable=False)  # 'applied' | 'dismissed'
    fee_payment_id = Column(UUID(as_uuid=True), ForeignKey("fee_payments.id", ondelete="SET NULL"), nullable=True)
    item_name = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    amount = Column(Numeric(10, 2), nullable=True)
    occurred_at = Column(Date, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FeeXeroConnection(Base):
    """A club's OAuth connection to its own Xero organisation ('tenant') — one
    per club. Unlike Square, this belongs to BetterFees alone: it exists purely
    to pull bank transactions for reconciliation against fee payments, never to
    write anything back. Xero access tokens last 30 minutes (refreshed
    liberally before each use, see services/fees_xero.ensure_fresh_token);
    refresh tokens have a rolling 60-day expiry that resets on every use, so a
    connection stays alive indefinitely as long as it's used at least that
    often. `tenant_id`/`bank_account_id` are null until the admin picks them
    (a Xero login can grant access to more than one organisation)."""
    __tablename__ = "fee_xero_connections"
    __table_args__ = (
        UniqueConstraint("organisation_id", name="uq_fee_xero_org"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(Text, nullable=True)
    tenant_name = Column(Text, nullable=True)
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    scopes = Column(Text, nullable=True)
    bank_account_id = Column(Text, nullable=True)
    bank_account_name = Column(Text, nullable=True)
    sync_enabled = Column(Boolean, nullable=False, server_default="false")
    last_sync_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_sync_status = Column(Text, nullable=True)   # 'ok' | 'error'
    last_sync_error = Column(Text, nullable=True)
    connected_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    connected_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FeeXeroImportLog(Base):
    """One row per Xero bank transaction a BetterFees admin has resolved
    (applied or dismissed) in the Xero import review queue — mirrors
    fee_square_import_log exactly, kept as its own table (rather than a
    shared/generalised one) so each provider's import stays independently
    reasoned about, matching how this codebase treats other per-integration
    tables (KlubPro, Play-Cricket, Square)."""
    __tablename__ = "fee_xero_import_log"
    __table_args__ = (
        UniqueConstraint("organisation_id", "external_ref", name="uq_fee_xero_import_log_ref"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    external_ref = Column(Text, nullable=False)
    status = Column(Text, nullable=False)  # 'applied' | 'dismissed'
    fee_payment_id = Column(UUID(as_uuid=True), ForeignKey("fee_payments.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=True)
    amount = Column(Numeric(10, 2), nullable=True)
    occurred_at = Column(Date, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


# ─── Committee Administration, Volunteer Management, Qualifications ─────────
# (migration 176). All three are CORE capabilities (like Families and
# Membership Types) — gated by capability, not a paid module, nothing
# auto-seeded. Reuse fee_members as "the person" throughout, the same
# unification point Membership Management and Family/Household use.
# committee_positions/committee_terms is a SEPARATE concern from the existing
# ClubCommitteeMember (`club_committee`, the public website's simple bio
# list) — deliberately not retrofitted, see the migration docstring.

COMMITTEE_TASK_CATEGORIES = ("operational", "maintenance", "compliance", "finance", "other")
COMMITTEE_TASK_STATUSES = ("todo", "in_progress", "done", "blocked")
COMMITTEE_DOCUMENT_CATEGORIES = (
    "governance", "policies", "constitution", "insurance", "grants",
    "ground_leases", "coach_accreditation", "wwcc", "risk_assessments", "other",
)
CLUB_EVENT_TYPES = (
    "committee_meeting", "working_bee", "registration_day", "agm",
    "awards_night", "sponsor_function", "fundraising", "other",
)


class CommitteePosition(Base):
    __tablename__ = "committee_positions"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_committee_positions_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    responsibilities = Column(Text, nullable=True)
    # A committee position IS a committee-flagged club_role (migration 198). The
    # position row stays the anchor for terms/tasks/docs/AGM FKs, but its name +
    # responsibilities are kept in sync from the linked role, so the one catalogue
    # is edited in Roles. NULL only for legacy rows created before the link.
    role_id = Column(UUID(as_uuid=True), ForeignKey("club_roles.id", ondelete="SET NULL"), nullable=True)
    # Executive/legal office bearers (President, VP, Treasurer, Secretary) vs
    # general elected committee members.
    is_office_bearer = Column(Boolean, nullable=False, server_default="false", default=False)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommitteeTerm(Base):
    """Who's held a position, when. ``ended_at IS NULL`` = the current holder;
    a position's history is every row sharing its position_id, newest first."""
    __tablename__ = "committee_terms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    position_id = Column(UUID(as_uuid=True), ForeignKey("committee_positions.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    holder_name = Column(Text, nullable=False)  # snapshot — survives member_id going NULL
    started_at = Column(Date, nullable=False, server_default=func.current_date())
    ended_at = Column(Date, nullable=True)
    handover_notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommitteeTask(Base):
    """The Task Register + the "Calendar of Annual Tasks" from the brief,
    unified — same shape (assigned, due date, status, category)."""
    __tablename__ = "committee_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(Text, nullable=False, server_default="operational", default="operational")
    position_id = Column(UUID(as_uuid=True), ForeignKey("committee_positions.id", ondelete="SET NULL"), nullable=True)
    assigned_to_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(Date, nullable=True)
    status = Column(Text, nullable=False, server_default="todo", default="todo")
    is_recurring = Column(Boolean, nullable=False, server_default="false", default=False)
    recurrence_note = Column(Text, nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Migration 217 — an action becomes plannable: what it should cost, what it
    # did cost, how far along it is, what it is waiting on (see
    # CommitteeTaskDependency), which objective it serves and which meeting or
    # motion asked for it.
    objective_id = Column(UUID(as_uuid=True), ForeignKey("club_objectives.id", ondelete="SET NULL"), nullable=True)
    budget_estimate = Column(Numeric(12, 2), nullable=True)
    actual_expenditure = Column(Numeric(12, 2), nullable=True)
    percent_complete = Column(Integer, nullable=False, server_default="0", default=0)
    start_date = Column(Date, nullable=True)
    closed_by_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    outcome_notes = Column(Text, nullable=True)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("committee_meetings.id", ondelete="SET NULL"), nullable=True)
    motion_id = Column(UUID(as_uuid=True), ForeignKey("meeting_motions.id", ondelete="SET NULL"), nullable=True)
    # The agenda item this action was raised under (migration 220), so "we
    # agreed that under Facilities" survives the meeting.
    agenda_item_id = Column(UUID(as_uuid=True), ForeignKey("meeting_agenda_items.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommitteeDocument(Base):
    """The club's document registry. Link-first — governance/policy docs live
    wherever the club already keeps them (Drive, Dropbox) and this indexes them
    — but a row can instead hold the file itself (migration 218), for the quote
    or letter that has nowhere else to live. A row carries a ``url`` or a
    ``file_data``, not both.

    Access differs between the two, and the difference is real rather than an
    oversight. A link is a URL we neither host nor can gate, so anyone who can
    read the registry can follow it. An uploaded file is served by us, so
    ``organisations.committee_docs_office_bearer_only`` decides who may open it
    — see ``services/committee.can_open_document``."""
    __tablename__ = "committee_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    category = Column(Text, nullable=False, server_default="governance", default="governance")
    url = Column(Text, nullable=True)
    position_id = Column(UUID(as_uuid=True), ForeignKey("committee_positions.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    # Migration 217 — what this document belongs to, so a quote the committee
    # asked for hangs off that action rather than floating in a general list.
    # 'task' | 'motion' | 'meeting' | 'objective'; both null = a club-wide doc.
    entity_type = Column(Text, nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    # The uploaded file, when this row is one (migration 218). Bytes live in
    # Postgres for the same reason player photos do — the container's upload
    # volume is not guaranteed to survive recreation.
    file_data = Column(LargeBinary, nullable=True)
    file_name = Column(Text, nullable=True)
    file_mime = Column(Text, nullable=True)
    file_size = Column(Integer, nullable=True)
    # Who uploaded it — one of the two people the restricted rule always lets in.
    uploaded_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubEvent(Base):
    """The Club Calendar — committee meetings, working bees, the AGM, sponsor
    functions, fundraising — distinct from cricket fixtures."""
    __tablename__ = "club_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    # Legacy free-text kind (kept for back-compat); the club-defined catalogue
    # row is ``event_type_id`` (migration 197). Readers prefer the catalogue
    # name when the FK is set, else fall back to this string.
    event_type = Column(Text, nullable=False, server_default="other", default="other")
    event_type_id = Column(UUID(as_uuid=True), ForeignKey("club_event_types.id", ondelete="SET NULL"), nullable=True)
    # The club person running the event (an internal member), with a free-text
    # fallback name for someone who isn't a recorded member (migration 197).
    organiser_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    organiser_name = Column(Text, nullable=True)
    starts_at = Column(TIMESTAMP(timezone=True), nullable=False)
    ends_at = Column(TIMESTAMP(timezone=True), nullable=True)
    location = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    is_ticketed = Column(Boolean, nullable=False, server_default="false", default=False)
    ticket_price_cents = Column(Integer, nullable=False, server_default="0", default=0)
    capacity = Column(Integer, nullable=True)
    registration_deadline = Column(TIMESTAMP(timezone=True), nullable=True)
    registration_open = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class VolunteerProfile(Base):
    __tablename__ = "volunteer_profiles"
    __table_args__ = (
        UniqueConstraint("organisation_id", "member_id", name="uq_volunteer_profiles_org_member"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False)
    roles_interested = Column(JSONB, nullable=False, server_default="[]", default=list)
    available_days = Column(JSONB, nullable=False, server_default="[]", default=list)
    lives_nearby = Column(Boolean, nullable=False, server_default="false", default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class VolunteerHours(Base):
    __tablename__ = "volunteer_hours"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False)
    logged_date = Column(Date, nullable=False, server_default=func.current_date())
    hours = Column(Numeric(6, 2), nullable=False, server_default="0")
    # Free-text label kept for back-compat; the club-defined catalogue row is
    # ``activity_id`` (migration 197). A logged row can carry either or both.
    activity = Column(Text, nullable=True)
    activity_id = Column(UUID(as_uuid=True), ForeignKey("club_activities.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    # Whether this was PAID work (migration 221), decided from the role's type
    # when the hours were logged. Recorded rather than re-derived on read:
    # retyping a role later must not rewrite last season's wage bill.
    is_paid = Column(Boolean, nullable=False, server_default="false", default=False)
    # The shift these came from, when they came from one. No FK by design —
    # roster_shifts is created by the lifespan's raw SQL, not the ORM, so an
    # ORM-side constraint would make create_all() order-dependent.
    roster_shift_id = Column(UUID(as_uuid=True), nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class QualificationType(Base):
    """WWCC, First Aid, coach/umpire/scorer accreditation, … ``validity_months``
    is a default used to compute a new record's expiry at the time it's
    logged (NULL = doesn't expire) — editable per club, not authoritative."""
    __tablename__ = "qualification_types"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_qualification_types_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    validity_months = Column(Integer, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class MemberQualification(Base):
    __tablename__ = "member_qualifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False)
    qualification_type_id = Column(UUID(as_uuid=True), ForeignKey("qualification_types.id", ondelete="CASCADE"), nullable=False)
    obtained_at = Column(Date, nullable=False, server_default=func.current_date())
    expires_at = Column(Date, nullable=True)
    certificate_ref = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    # Reminder-automation throttle (migration 178) — NULL until the first
    # expiry reminder email fires; a fresh send is skipped while this is
    # recent, so the daily job can run every day without spamming.
    last_reminder_sent_at = Column(TIMESTAMP(timezone=True), nullable=True)


# ─── AGM elections/voting/motions, Committee Meeting Assistant,
# Events/Ticketing, Assets & Facilities (migration 177) ──────────────────────
# committee_meetings generalises to serve both the AGM and ordinary committee
# meetings — agm_nominations reuses committee_positions/committee_terms so an
# elected result and the Positions tab's succession history are one record,
# not two (an "elected" nomination calls the existing committee.start_term()).
# Assets/Facilities is a NEW, separate concern from BetterMerch's
# merch_assets (a paid-module retail/kit table) — general club property
# (mower, clubhouse, nets) isn't retrofitted there. See the migration
# docstring for the Square-scopes reasoning behind Events/Ticketing shipping
# without online payment collection.

MEETING_TYPES = ("committee", "agm", "special_general", "sub_committee", "other")
MEETING_STATUSES = ("scheduled", "in_progress", "completed", "cancelled")
AGENDA_ITEM_STATUSES = ("proposed", "discussed", "carried", "deferred", "withdrawn")
MOTION_TYPES = ("motion", "amendment", "procedural")
MOTION_OUTCOMES = ("pending", "carried", "lost", "withdrawn")
AGM_NOMINATION_STATUSES = ("nominated", "elected", "withdrawn", "not_elected")
FACILITY_TYPES = ("ground", "clubhouse", "nets", "scoreboard", "canteen", "storage", "other")
ASSET_CATEGORIES = ("equipment", "technology", "furniture", "ground_maintenance", "safety", "other")
ASSET_CONDITIONS = ("excellent", "good", "fair", "poor", "unserviceable")
ASSET_STATUSES = ("in_service", "in_repair", "retired", "disposed")


class AgendaTemplate(Base):
    """A reusable agenda shape (e.g. "Standard committee meeting") — ``items``
    is a plain JSON list of {title, description} the Committee Meeting
    Assistant copies onto a new meeting's agenda in one click."""
    __tablename__ = "agenda_templates"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_agenda_templates_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    items = Column(JSONB, nullable=False, server_default="[]", default=list)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommitteeMeeting(Base):
    """A regular committee meeting OR the AGM/a special general meeting —
    ``meeting_type`` distinguishes them; agenda items, motions and (for an
    AGM) nominations all hang off the one meeting record."""
    __tablename__ = "committee_meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    meeting_type = Column(Text, nullable=False, server_default="committee", default="committee")
    scheduled_at = Column(TIMESTAMP(timezone=True), nullable=False)
    location = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="scheduled", default="scheduled")
    minutes = Column(Text, nullable=True)
    # Minutes get circulated. These do not (migration 220) — a secretary keeps
    # working notes that are not part of the record.
    private_notes = Column(Text, nullable=True)
    agenda_template_id = Column(UUID(as_uuid=True), ForeignKey("agenda_templates.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class MeetingAttendance(Base):
    __tablename__ = "meeting_attendance"
    __table_args__ = (
        UniqueConstraint("meeting_id", "member_id", name="uq_meeting_attendance"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("committee_meetings.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, nullable=False, server_default="present", default="present")


class MeetingAgendaItem(Base):
    __tablename__ = "meeting_agenda_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("committee_meetings.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    proposed_by_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    position = Column(Integer, nullable=False, server_default="0", default=0)
    status = Column(Text, nullable=False, server_default="proposed", default="proposed")
    outcome_notes = Column(Text, nullable=True)
    # Which part of the order of business this item sits in (migration 231) —
    # "Opening formalities", "Annual reports", "Elections". A label rather than
    # a table: the agenda stays one ordered sequence and the screen draws a
    # heading wherever the section changes.
    section = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class MeetingMotion(Base):
    __tablename__ = "meeting_motions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("committee_meetings.id", ondelete="CASCADE"), nullable=False)
    agenda_item_id = Column(UUID(as_uuid=True), ForeignKey("meeting_agenda_items.id", ondelete="SET NULL"), nullable=True)
    motion_type = Column(Text, nullable=False, server_default="motion", default="motion")
    description = Column(Text, nullable=False)
    proposed_by_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    seconded_by_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    votes_for = Column(Integer, nullable=True)
    votes_against = Column(Integer, nullable=True)
    votes_abstain = Column(Integer, nullable=True)
    outcome = Column(Text, nullable=False, server_default="pending", default="pending")
    notes = Column(Text, nullable=True)
    # Migration 217 — a carried motion the committee chooses to record as a
    # standing decision. `resolution_ref` is the club's own numbering; ours
    # would only be one more convention to argue about.
    is_resolution = Column(Boolean, nullable=False, server_default="false", default=False)
    resolution_ref = Column(Text, nullable=True)
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Migration 230 — the objective this motion serves. An action already had
    # one, so "the committee resolved to do this" and "someone is doing it"
    # reported against the plan differently until this existed.
    objective_id = Column(UUID(as_uuid=True), ForeignKey("club_objectives.id", ondelete="SET NULL"), nullable=True)
    # Motions are ordered so they can sit against the agenda item they relate
    # to rather than in the order someone happened to type them (migration 220).
    position = Column(Integer, nullable=False, server_default="0", default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommitteeTaskAssignee(Base):
    """Who is doing an action (migration 220).

    ``committee_tasks.assigned_to_member_id`` stays as the primary owner so
    every existing reader keeps working; this holds the full set, because "Dave
    and Priya will get the quotes" is the normal case rather than the exception.
    """
    __tablename__ = "committee_task_assignees"

    task_id = Column(UUID(as_uuid=True), ForeignKey("committee_tasks.id", ondelete="CASCADE"), primary_key=True)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), primary_key=True)


class MeetingMotionVote(Base):
    """One committee member's vote on one motion (migration 217).

    The tallies on MeetingMotion stay: a club that counts hands in the room has
    only a count, and forcing named votes on them would be worse than useless.
    A club that does record names gets both, and the tallies can be derived.
    """
    __tablename__ = "meeting_motion_votes"
    __table_args__ = (UniqueConstraint("motion_id", "member_id", name="uq_motion_vote_per_member"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    motion_id = Column(UUID(as_uuid=True), ForeignKey("meeting_motions.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False)
    vote = Column(Text, nullable=False)   # for | against | abstain
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubStrategicPlan(Base):
    """The club's business or strategic plan (migration 230).

    Objectives belong to a plan and actions and motions belong to an objective,
    so a club can run "Strategic Plan 2026-29" and "Facilities Plan" side by
    side and report each against the register the committee already keeps.
    """
    __tablename__ = "club_strategic_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    start_year = Column(Integer, nullable=True)
    end_year = Column(Integer, nullable=True)
    status = Column(Text, nullable=False, server_default="active", default="active")
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubStrategicPillar(Base):
    """A theme in one plan (migration 232, made plan-scoped by 275) — on-field,
    finances, volunteers, facilities.

    **A theme belongs to ONE plan** (``plan_id``). 232 made it club-scoped on
    the reasoning that a club's themes are stable across plans; running it as a
    tree proved that wrong in the worst way, because the second plan drew the
    first plan's themes and deleting one of them from the second plan's tree
    deleted the FIRST plan's objectives. A plan owns its themes, a theme owns
    its objectives, and there is no linkage between one plan's hierarchy and
    another's.

    NOT NULL since 276: a theme with no plan is not a state the club's plan can
    be in, so there is no club-wide theme to leak into a second plan's tree.
    """
    __tablename__ = "club_strategic_pillars"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    # Deleting a plan takes its themes with it — that is what belonging to a
    # plan means, and the objectives under them go too (see ClubObjective).
    plan_id = Column(UUID(as_uuid=True), ForeignKey("club_strategic_plans.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubObjective(Base):
    """A line in the club's business or strategic plan (migration 217).
    Committee actions point at one, which is what turns a task register into
    progress against a plan."""
    __tablename__ = "club_objectives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    # The plan this used to belong to, as free text (migration 217). Backfilled
    # into real plan rows by migration 230 and not written again — `plan_id` is
    # the plan now. Kept so a club's own first spelling stays on the record.
    plan = Column(Text, nullable=True)
    season_year = Column(Integer, nullable=True)
    status = Column(Text, nullable=False, server_default="active", default="active")
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    # Migration 230 — what a club plans WITH. These sat on the actions serving
    # an objective and nowhere on the objective itself, so an objective with no
    # actions yet had no owner, no date and no budget.
    # Migration 276 — an objective belongs to its theme, with its plan. Both
    # NOT NULL and both CASCADE: SET NULL cannot coexist with NOT NULL, and an
    # objective with nowhere to sit is exactly the state 276 removes. The
    # ACTIONS and MOTIONS serving it are NOT deleted by either cascade — those
    # FKs stay SET NULL, so the work is kept and stops being linked.
    plan_id = Column(UUID(as_uuid=True), ForeignKey("club_strategic_plans.id", ondelete="CASCADE"), nullable=False)
    due_date = Column(Date, nullable=True)
    owner_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    budget = Column(Numeric(12, 2), nullable=True)
    # Migration 232 — the theme it groups under (NOT NULL since 276) — and a
    # committee SEAT that owns it. A position owner transfers at the AGM
    # without anyone editing anything, which a person owner cannot; the two
    # owner fields are both optional, and a club may use either.
    pillar_id = Column(UUID(as_uuid=True), ForeignKey("club_strategic_pillars.id", ondelete="CASCADE"), nullable=False)
    owner_position_id = Column(UUID(as_uuid=True), ForeignKey("committee_positions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommitteeTaskDependency(Base):
    """An action that waits on another (migration 217). Same shape as
    DiaryTaskDependency, so the same client-side critical-path derivation
    works on both."""
    __tablename__ = "committee_task_dependencies"

    task_id = Column(UUID(as_uuid=True), ForeignKey("committee_tasks.id", ondelete="CASCADE"), primary_key=True)
    depends_on_task_id = Column(UUID(as_uuid=True), ForeignKey("committee_tasks.id", ondelete="CASCADE"), primary_key=True)


class CommitteeNote(Base):
    """A note against an action, motion or meeting (migration 217).
    `entity_type` is 'task' | 'motion' | 'meeting' | 'objective'."""
    __tablename__ = "committee_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(Text, nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    body = Column(Text, nullable=False)
    author_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    author_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class AgmNomination(Base):
    """A candidate nominated for a committee position at an AGM. Marking one
    ``elected`` calls committee.start_term() so it writes a real
    committee_terms row (auto-closing whoever held the position before) —
    the election result and the Positions tab's history are the same data."""
    __tablename__ = "agm_nominations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("committee_meetings.id", ondelete="CASCADE"), nullable=False)
    position_id = Column(UUID(as_uuid=True), ForeignKey("committee_positions.id", ondelete="CASCADE"), nullable=False)
    candidate_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False)
    nominated_by_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    seconded_by_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    votes_for = Column(Integer, nullable=True)
    status = Column(Text, nullable=False, server_default="nominated", default="nominated")
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class EventRegistration(Base):
    """A ticket/RSVP against a ClubEvent. ``payment_status`` 'free' (no
    charge) | 'awaiting_payment' (a priced event whose club hasn't connected
    Stripe yet, or a manually-recorded phone/in-person RSVP — reconciled by
    hand) | 'paid' (Stripe Connect checkout confirmed, or an admin marked it
    reconciled) | 'cancelled'. See migration 180 + services/events.py for
    the Stripe Connect checkout path (same per-club connected account the
    member portal and merch storefront use)."""
    __tablename__ = "event_registrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    event_id = Column(UUID(as_uuid=True), ForeignKey("club_events.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    phone = Column(Text, nullable=True)
    quantity = Column(Integer, nullable=False, server_default="1", default=1)
    amount_cents = Column(Integer, nullable=False, server_default="0", default=0)
    payment_status = Column(Text, nullable=False, server_default="free", default="free")
    notes = Column(Text, nullable=True)
    stripe_checkout_session_id = Column(Text, nullable=True)
    stripe_payment_intent_id = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class Facility(Base):
    __tablename__ = "facilities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    facility_type = Column(Text, nullable=False, server_default="other", default="other")
    description = Column(Text, nullable=True)
    key_location = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FacilityBooking(Base):
    __tablename__ = "facility_bookings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    starts_at = Column(TIMESTAMP(timezone=True), nullable=False)
    ends_at = Column(TIMESTAMP(timezone=True), nullable=True)
    booked_by_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    # External hirer's contact + the club person responsible for the booking
    # (migration 197). A booking can span days/weeks/months via ends_at (e.g.
    # a facility rented to another organisation for a whole season).
    contact_name = Column(Text, nullable=True)
    contact_email = Column(Text, nullable=True)
    contact_mobile = Column(Text, nullable=True)
    owner_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    owner_name = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubAsset(Base):
    """THE club's asset register — every piece of property, equipment and fixed
    asset it owns: mower, scoreboard, nets, tables, bowling machine, covers.

    One register, deliberately. BetterMerch's `merch_assets` was a second one
    describing the same class of object (its own docstring: "an individual
    high-value piece of equipment … not stock-counted") and migration 279
    carried it in here; `merch_asset_id` records which rows came across.
    Inventory is the separate concern — that is `merch_products` /
    `merch_variants`, which have a quantity."""
    __tablename__ = "club_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    category = Column(Text, nullable=False, server_default="other", default="other")
    asset_tag = Column(Text, nullable=True)
    purchase_cost = Column(Numeric(10, 2), nullable=True)
    purchase_date = Column(Date, nullable=True)
    condition = Column(Text, nullable=False, server_default="good", default="good")
    status = Column(Text, nullable=False, server_default="in_service", default="in_service")
    service_due_date = Column(Date, nullable=True)
    replace_due_date = Column(Date, nullable=True)
    facility_id = Column(UUID(as_uuid=True), ForeignKey("facilities.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    # The `merch_assets` row this was carried from (migration 279), or NULL for
    # a row the club entered here. No FK: that table is history now, and tidying
    # it must not take the live register's rows with it.
    merch_asset_id = Column(UUID(as_uuid=True), nullable=True)
    # 'club' for a row entered here, 'merch' for one migration 279 created from
    # the old BetterMerch register. A GAP-FILLED row keeps 'club': it is the
    # club's own asset that merely had its blanks filled in, and the downgrade
    # turns on that difference.
    source = Column(Text, nullable=False, server_default="club", default="club")


class MaintenanceLog(Base):
    """Shared between a ClubAsset and a Facility — ``subject_type`` is
    'asset' | 'facility', ``subject_id`` the relevant row's id (no FK, since
    it targets one of two tables — mirrors the pattern used elsewhere in
    this codebase for a polymorphic subject, e.g. sync's opponent tags)."""
    __tablename__ = "maintenance_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    subject_type = Column(Text, nullable=False)
    subject_id = Column(UUID(as_uuid=True), nullable=False)
    performed_at = Column(Date, nullable=False, server_default=func.current_date())
    description = Column(Text, nullable=False)
    cost = Column(Numeric(10, 2), nullable=True)
    performed_by = Column(Text, nullable=True)
    next_due_date = Column(Date, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


# ─── Club Diary (migration 181) — annual/recurring compliance & maintenance
# task calendar ────────────────────────────────────────────────────────────
# A definition/occurrence split, NOT a retrofit of Committee Administration's
# committee_tasks — that table is one mutable row per task with no per-period
# trail, whereas the whole point here is "what did we do about this exact
# recurring task last year, and the year before." See the migration 181
# docstring and services/club_diary.py for the full reasoning.

DIARY_TASK_FREQUENCIES = ("annual", "quarterly", "monthly", "once")
DIARY_TASK_STATUSES = ("pending", "in_progress", "done", "not_applicable")


class DiaryCategory(Base):
    """Club-defined grouping for diary tasks (Compliance, Tax, Ground &
    Equipment, whatever the club calls it) — deliberately NOT the fixed
    category list committee_tasks uses."""
    __tablename__ = "club_diary_categories"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_club_diary_categories_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    # Hex colour used to colour-code the Gantt chart by category (migration 197).
    color = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class DiaryTaskDefinition(Base):
    """The recurring task itself — title, how often, a suggested month,
    and a default assignee (a committee POSITION, so responsibility
    transfers automatically as terms change, or a specific member as a
    fallback). Archived (is_active=False) rather than deleted so its
    occurrence history is never lost."""
    __tablename__ = "club_diary_task_definitions"
    __table_args__ = (
        UniqueConstraint("organisation_id", "title", name="uq_club_diary_definitions_org_title"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    category_id = Column(UUID(as_uuid=True), ForeignKey("club_diary_categories.id", ondelete="SET NULL"), nullable=True)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    frequency = Column(Text, nullable=False, server_default="annual", default="annual")
    default_month = Column(Integer, nullable=True)  # 1-12, a suggestion only
    default_assignee_position_id = Column(UUID(as_uuid=True), ForeignKey("committee_positions.id", ondelete="SET NULL"), nullable=True)
    default_assignee_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    # Template-level responsibility (a club role), an associated third party,
    # and a budgetary estimate — carried onto each season's occurrence when it
    # is generated, then editable per season (migration 197).
    responsibility_role_id = Column(UUID(as_uuid=True), ForeignKey("club_roles.id", ondelete="SET NULL"), nullable=True)
    third_party = Column(Text, nullable=True)
    budget_estimate = Column(Numeric(10, 2), nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    # Optional reminder email to whoever's assigned, ahead of the due date
    # (migration 182) — off by default, per-task opt-in, not mandatory.
    reminder_enabled = Column(Boolean, nullable=False, server_default="false", default=False)
    reminder_days_before = Column(Integer, nullable=False, server_default="14", default=14)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class DiaryTaskOccurrence(Base):
    """One period's instance of a definition — 'period_label' is a plain
    string ("2026" for annual/once, "2026 Q1" for quarterly) rather than
    separate year/quarter columns, so every frequency shares one row shape.
    Querying every occurrence for one definition, newest period first, IS
    the task's history."""
    __tablename__ = "club_diary_task_occurrences"
    __table_args__ = (
        UniqueConstraint("definition_id", "period_label", name="uq_club_diary_occurrence_period"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    definition_id = Column(UUID(as_uuid=True), ForeignKey("club_diary_task_definitions.id", ondelete="CASCADE"), nullable=False)
    period_label = Column(Text, nullable=False)
    due_date = Column(Date, nullable=True)
    status = Column(Text, nullable=False, server_default="pending", default="pending")
    assigned_to_member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    # Per-season planning + tracking (migration 197): a start date (with due_date
    # as the target end, so the pair drives the Gantt bars), progress %, an
    # estimated completion date, the responsible role, a third party, the
    # season's budget estimate and actual expenditure to date — so a task can
    # be shown early/late and under/over budget.
    assigned_to_role_id = Column(UUID(as_uuid=True), ForeignKey("club_roles.id", ondelete="SET NULL"), nullable=True)
    start_date = Column(Date, nullable=True)
    percent_complete = Column(Integer, nullable=False, server_default="0", default=0)
    estimated_completion_date = Column(Date, nullable=True)
    third_party = Column(Text, nullable=True)
    budget_estimate = Column(Numeric(10, 2), nullable=True)
    actual_expenditure = Column(Numeric(10, 2), nullable=True)
    notes = Column(Text, nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Reminder throttle (migration 182) — mirrors MemberQualification/
    # FeeMemberSeason's own last_*_sent_at columns.
    last_reminder_sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


# ─── Roles & Activities (migration 197) — the club's volunteer taxonomy ──────
# A shared catalogue used by BOTH Volunteers (a volunteer holds one or more
# Roles) and Qualifications (a qualification can be tagged with the Roles it
# is required for). Activities describe what a volunteer's logged hours were
# spent on. Both Roles and Activities carry a club-defined Type (its own
# catalogue with a starter set), same opt-in posture as qualification_types /
# club_diary_categories — nothing is auto-seeded.

class ClubRoleType(Base):
    """A club-defined kind of role (Committee Member, Ground Staff, Coach,
    Food & Beverage, Other, …). Archived rather than deleted so a role that
    references it keeps its grouping."""
    __tablename__ = "club_role_types"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_club_role_types_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    # committee / volunteer / paid / third_party / other — drives which surfaces
    # a role of this type appears on (committee positions vs the Roles list).
    category = Column(Text, nullable=False, server_default="volunteer", default="volunteer")
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubRole(Base):
    """A specific role a volunteer can hold — Title + Type + optional
    description (e.g. "Under-12 Coach" of type Coach)."""
    __tablename__ = "club_roles"
    __table_args__ = (
        UniqueConstraint("organisation_id", "title", name="uq_club_roles_org_title"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    role_type_id = Column(UUID(as_uuid=True), ForeignKey("club_role_types.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=True)
    # A committee role is a role that also appears as a Committee position
    # (migration 198). Volunteers pick non-committee roles; Committee terms are
    # held against committee roles. Both live in this one catalogue.
    is_committee = Column(Boolean, nullable=False, server_default="false", default=False)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubActivityType(Base):
    """A club-defined kind of activity, loosely mirroring the role types
    (Committee, Ground, Coaching, Food & Beverage, Match Day, …, Other)."""
    __tablename__ = "club_activity_types"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_club_activity_types_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubActivity(Base):
    """A specific activity a volunteer's logged hours can be recorded against —
    Title + Type + optional description."""
    __tablename__ = "club_activities"
    __table_args__ = (
        UniqueConstraint("organisation_id", "title", name="uq_club_activities_org_title"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    activity_type_id = Column(UUID(as_uuid=True), ForeignKey("club_activity_types.id", ondelete="SET NULL"), nullable=True)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class VolunteerRole(Base):
    """Link: a volunteer (keyed by member) holds a ClubRole. Keyed on member,
    not the profile row, so it survives a profile being re-created."""
    __tablename__ = "volunteer_roles"
    __table_args__ = (
        UniqueConstraint("member_id", "role_id", name="uq_volunteer_roles_member_role"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("club_roles.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class QualificationRole(Base):
    """Link: a member qualification is relevant to a ClubRole (a qualification
    can apply to several roles)."""
    __tablename__ = "qualification_roles"
    __table_args__ = (
        UniqueConstraint("qualification_id", "role_id", name="uq_qualification_roles_qual_role"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    qualification_id = Column(UUID(as_uuid=True), ForeignKey("member_qualifications.id", ondelete="CASCADE"), nullable=False)
    role_id = Column(UUID(as_uuid=True), ForeignKey("club_roles.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubEventType(Base):
    """A club-defined kind of event (Social Night, Awards Night, AGM, Busy Bee,
    …). ``is_committee_only`` marks internal committee events (Committee
    Meeting, Stock Take, End of Season) so the Events page can offer two
    starter sets and filter them apart."""
    __tablename__ = "club_event_types"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_club_event_types_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    is_committee_only = Column(Boolean, nullable=False, server_default="false", default=False)
    sort_order = Column(Integer, nullable=False, server_default="0", default=0)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class DiaryTaskDependency(Base):
    """``definition_id`` cannot start until ``depends_on_definition_id`` is
    done — drives the Gantt chart's dependency arrows and the season plan's
    ordering (migration 197)."""
    __tablename__ = "club_diary_task_dependencies"
    __table_args__ = (
        UniqueConstraint("definition_id", "depends_on_definition_id", name="uq_club_diary_task_dependency"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    definition_id = Column(UUID(as_uuid=True), ForeignKey("club_diary_task_definitions.id", ondelete="CASCADE"), nullable=False)
    depends_on_definition_id = Column(UUID(as_uuid=True), ForeignKey("club_diary_task_definitions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


# ─── BetterMerch (BetterAdmin module) — club stock register ──────────────────
# One engine, three category templates: apparel (sized/coloured variants),
# equipment (quantity OR individual assets), food_drink (canteen/bar stock with
# expiry). Stock always lives on a variant (a product has at least one); every
# change writes a movement so the running balance is fast to read and the
# history is kept. Individual high-value equipment lives in merch_assets.

MERCH_CATEGORIES = ("apparel", "equipment", "food_drink")
MERCH_MAX_CATEGORY_DEPTH = 3   # club-defined sub-categories nest 3 levels under a type
# Signed movements: received/+ , sold/issued/used/write_off/- , adjustment/±,
# stocktake sets an absolute count (delta = new − old).
MERCH_MOVEMENT_KINDS = ("received", "sold", "issued", "used", "adjustment", "stocktake", "write_off")
MERCH_ASSET_CONDITIONS = ("new", "good", "fair", "poor", "retired")
MERCH_ASSET_STATUSES = ("in_service", "out_for_repair", "retired")


class MerchCategory(Base):
    """A club-defined category node for grouping stock items, nested up to three
    levels under a fixed top type (`top_category`). Created inline as items are
    added (deduped by name within a parent); reports roll up by node. Deleting a
    node reparents its children and nulls the products' `category_id`."""
    __tablename__ = "merch_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("merch_categories.id", ondelete="CASCADE"), nullable=True)
    top_category = Column(Text, nullable=False)   # apparel | equipment | food_drink
    name = Column(Text, nullable=False)
    sort_order = Column(Integer, nullable=False, server_default="0")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class MerchProduct(Base):
    """A catalogue line in the club stock register — the 'what'. Stock lives on
    its variants (always at least one). `category` picks the template; the
    `unit_cost`/`unit_price`/`low_stock_threshold` here are defaults a variant
    can override. `category_id` files it under a club-defined category node."""
    __tablename__ = "merch_products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    category = Column(Text, nullable=False, server_default="apparel")
    category_id = Column(UUID(as_uuid=True), ForeignKey("merch_categories.id", ondelete="SET NULL"), nullable=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    unit_cost = Column(Numeric(10, 2), nullable=True)   # default cost to buy
    unit_price = Column(Numeric(10, 2), nullable=True)  # default cost to sell
    low_stock_threshold = Column(Integer, nullable=True)  # default reorder point (NULL = no alert)
    supplier = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    # True: bought to sell — cost + sell price, margin, sold/issued to members
    # (apparel, canteen). False: club-use consumable — a straight cost, no sell
    # price and no owing (e.g. match/training balls, stumps).
    for_resale = Column(Boolean, nullable=False, server_default="true")
    source = Column(Text, nullable=False, server_default="manual")   # 'manual' | 'square'
    square_object_id = Column(Text, nullable=True)                    # Square catalog ITEM id
    is_active = Column(Boolean, nullable=False, server_default="true")
    # Merch storefront (migration 179): whether this product shows on the
    # public online store. Default true so an existing club's whole resale
    # catalogue is visible the moment the storefront is switched on — a
    # Square-synced product (source='square') is excluded from the
    # storefront regardless of this flag (see routers/public_merch_store.py).
    show_in_storefront = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    variants = relationship("MerchVariant", back_populates="product", cascade="all, delete-orphan")


class MerchVariant(Base):
    """One stock-keeping line under a product (a size/colour, or just 'Standard'
    for an un-varied product). `quantity` is the running on-hand balance; every
    change writes a MerchMovement. `unit_cost`/`unit_price` here override the
    product default; `low_stock_threshold` overrides too. `expiry_date` is the
    food/drink batch best-before."""
    __tablename__ = "merch_variants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id = Column(UUID(as_uuid=True), ForeignKey("merch_products.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    label = Column(Text, nullable=False, server_default="Standard")
    size = Column(Text, nullable=True)
    colour = Column(Text, nullable=True)
    sku = Column(Text, nullable=True)
    unit_cost = Column(Numeric(10, 2), nullable=True)
    unit_price = Column(Numeric(10, 2), nullable=True)
    quantity = Column(Integer, nullable=False, server_default="0")
    low_stock_threshold = Column(Integer, nullable=True)
    expiry_date = Column(Date, nullable=True)
    square_object_id = Column(Text, nullable=True)   # Square catalog ITEM_VARIATION id
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    product = relationship("MerchProduct", back_populates="variants")
    movements = relationship("MerchMovement", back_populates="variant", cascade="all, delete-orphan")


class MerchMovement(Base):
    """One change to a variant's stock — the in/out audit log. `delta` is signed.
    `player_id` records who an item went to; for a sale/issue with money owed,
    `amount`/`paid` track the merch owing (kept inside BetterMerch, separate from
    BetterFees). `quantity_after` snapshots the balance for the audit trail."""
    __tablename__ = "merch_movements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("merch_variants.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    kind = Column(Text, nullable=False, server_default="adjustment")
    delta = Column(Integer, nullable=False, server_default="0")
    quantity_after = Column(Integer, nullable=True)
    unit_cost = Column(Numeric(10, 2), nullable=True)
    unit_price = Column(Numeric(10, 2), nullable=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    amount = Column(Numeric(10, 2), nullable=True)            # total money for this movement
    paid = Column(Boolean, nullable=False, server_default="true")  # sales/issues: settled or owing
    paid_at = Column(Date, nullable=True)
    payment_method = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    occurred_on = Column(Date, nullable=True)                # business date of the movement
    source = Column(Text, nullable=False, server_default="manual")   # 'manual' | 'square'
    external_ref = Column(Text, nullable=True)               # dedupe key for imported rows (e.g. Square order line)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    variant = relationship("MerchVariant", back_populates="movements")
    player = relationship("Player")


# ─── Merch storefront (migration 179) ────────────────────────────────────────
# Public online ordering against the SAME catalogue above — a NEW pair of
# tables (not a repurposing of merch_movements), since an order needs its own
# customer/contact details, payment status and Stripe correlation. A paid
# order's line items become ordinary MerchMovement rows (kind='sold',
# source='online_store') via the existing record_movement() once payment is
# confirmed — stock accounting stays in the one place it's always lived.

MERCH_ORDER_STATUSES = ("pending_payment", "paid", "fulfilled", "cancelled")


class MerchOrder(Base):
    __tablename__ = "merch_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    customer_name = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    phone = Column(Text, nullable=True)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    status = Column(Text, nullable=False, server_default="pending_payment", default="pending_payment")
    total_cents = Column(Integer, nullable=False, server_default="0", default=0)
    stripe_checkout_session_id = Column(Text, nullable=True)
    stripe_payment_intent_id = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    items = relationship("MerchOrderItem", back_populates="order", cascade="all, delete-orphan")


class MerchOrderItem(Base):
    """A line-item snapshot — product/variant NAME and price are copied at
    order time (not re-read from the live catalogue) so a later price change
    or product rename never rewrites a historical order."""
    __tablename__ = "merch_order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("merch_orders.id", ondelete="CASCADE"), nullable=False)
    variant_id = Column(UUID(as_uuid=True), ForeignKey("merch_variants.id", ondelete="SET NULL"), nullable=True)
    product_name = Column(Text, nullable=False)
    variant_label = Column(Text, nullable=True)
    unit_price_cents = Column(Integer, nullable=False, server_default="0", default=0)
    quantity = Column(Integer, nullable=False, server_default="1", default=1)

    order = relationship("MerchOrder", back_populates="items")


class MerchAsset(Base):
    """HISTORY. Was BetterMerch's own register of individual high-value
    equipment (bowling machine, covers, sight screen), which is the same class
    of object `club_assets` holds — never inventory, since quantity is
    implicitly 1 and it was not stock-counted.

    Migration 279 carried every row into `club_assets` and NOTHING READS THIS
    AFTER IT. Left in place rather than dropped, the call migration 267 made for
    `vote_settings`. Do not write to it: a second register that still answered
    writes could only drift from the one people are looking at."""
    __tablename__ = "merch_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    asset_tag = Column(Text, nullable=True)                  # serial / club asset tag
    purchase_cost = Column(Numeric(10, 2), nullable=True)
    purchase_date = Column(Date, nullable=True)
    condition = Column(Text, nullable=False, server_default="good")
    service_due_date = Column(Date, nullable=True)
    replace_due_date = Column(Date, nullable=True)
    status = Column(Text, nullable=False, server_default="in_service")
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class MerchSquareConnection(Base):
    """A club's OAuth connection to its own Square account (one per club). Square
    is the source of truth for canteen/bar stock: we mirror its catalog + current
    inventory counts into food_drink products, and import completed sales as
    'sold' movements. Tokens are stored per club (same pattern as other per-club
    API tokens); the code-flow refresh token does not expire, the access token is
    refreshed when it nears its 30-day expiry."""
    __tablename__ = "merch_square_connections"
    __table_args__ = (
        UniqueConstraint("organisation_id", name="uq_merch_square_org"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    merchant_id = Column(Text, nullable=True)
    environment = Column(Text, nullable=False, server_default="production")  # 'sandbox' | 'production'
    access_token = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    token_expires_at = Column(TIMESTAMP(timezone=True), nullable=True)
    scopes = Column(Text, nullable=True)
    location_id = Column(Text, nullable=True)
    location_name = Column(Text, nullable=True)
    sync_enabled = Column(Boolean, nullable=False, server_default="true")
    sync_sales = Column(Boolean, nullable=False, server_default="true")
    last_sync_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_sync_status = Column(Text, nullable=True)   # 'ok' | 'error'
    last_sync_error = Column(Text, nullable=True)
    sales_cursor = Column(TIMESTAMP(timezone=True), nullable=True)  # import orders closed after this
    # BetterFees reuses this same connection (one Square account per club) to
    # pull completed sales that look like match-fee/membership payments. Off
    # by default — a club turns it on and sets its own item-name keywords
    # before the Square review queue starts surfacing anything. Kept as its
    # own last-sync trio so a fees-side failure never clobbers merch's status.
    sync_fees = Column(Boolean, nullable=False, server_default="false")
    fee_item_keywords = Column(Text, nullable=True)  # comma-separated, e.g. "match fee, membership"
    fees_last_sync_at = Column(TIMESTAMP(timezone=True), nullable=True)
    fees_last_sync_status = Column(Text, nullable=True)   # 'ok' | 'error'
    fees_last_sync_error = Column(Text, nullable=True)
    connected_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    connected_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


# ─── BetterComms (BetterAdmin module) — bulk email ───────────────────────────

class ClubOnboardingRequest(Base):
    """A submission from the public marketing Contact form (betterat.cricket/contact).

    A prospective club fills in the "Tell us about your club" form. On submit the
    frontend still emails us via Formspree and also posts here, so every onboarding
    enquiry is kept as a row staff can work through in the super-admin area.
    Public and unauthenticated (the sender is a prospect with no club and no login),
    so there is no organisation_id. ``status`` tracks the follow-up
    (new -> contacted -> onboarded / closed).
    """
    __tablename__ = "club_onboarding_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    club = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    phone = Column(Text, nullable=True)
    association = Column(Text, nullable=True)
    grades = Column(Text, nullable=True)
    storage = Column(Text, nullable=True)
    timeline = Column(Text, nullable=True)
    club_url = Column(Text, nullable=True)
    message = Column(Text, nullable=True)
    # Added migration 081 (extra onboarding questions, mirrored from the old
    # Google Form): role at the club, year founded, whether data is in PlayHQ,
    # whether they hold historical data, what they're most interested in
    # (comma-joined), how they heard of us, and their preferred contact method.
    role = Column(Text, nullable=True)
    founded_year = Column(Text, nullable=True)
    playhq_status = Column(Text, nullable=True)
    has_historical = Column(Text, nullable=True)
    interests = Column(Text, nullable=True)
    heard_about = Column(Text, nullable=True)
    contact_method = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="new")  # new | contacted | onboarded | closed
    source = Column(Text, nullable=False, server_default="contact_form")
    user_agent = Column(Text, nullable=True)
    # Which club the enquirer actually meant (migration 224). The form searches
    # the Cricket Australia club list, so a picked club carries its real CA
    # organisation guid here and every downstream match keys on that rather than
    # on however the name happened to be spelled. ``club_source`` is 'search'
    # (picked from the list) or 'manual' (typed in - the fallback for a club
    # outside Australia, which has no guid).
    club_org_id = Column(Text, nullable=True)
    club_source = Column(Text, nullable=True)
    # First-party visitor id (localStorage UUID) sent by the Contact form, so an
    # enquiry can be tied back to the anonymous browsing journey on the Usage page.
    visitor_id = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class ClubUnpauseRequest(Base):
    """A visitor's request to unlock a club's password-protected public page.

    Only ever created from the public gate when the club's
    ``password_protect_reason`` is 'trial_ended' — the sales-conversion trigger
    for the "This trial has ended..." copy (see routers/clubs.py,
    POST /clubs/{slug}/request-unpause). Reviewed by Super Admin at
    /admin/super/unpause-requests, who can open a sales conversation with the
    requester (reply_to on the notification email is the requester's own
    address for exactly this). ``status`` tracks the follow-up
    (pending -> actioned / dismissed).
    """
    __tablename__ = "club_unpause_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    email = Column(Text, nullable=False)
    message = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="pending")  # pending | actioned | dismissed
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    actioned_at = Column(TIMESTAMP(timezone=True), nullable=True)
    actioned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class CommsContact(Base):
    """A single emailable contact in a club's audience.

    The canonical recipient list, deduped per club by ``email`` (stored
    lowercased + trimmed). Sourced from players, fee members, CSV/paste import
    or manual entry (``source``). ``subscribed`` is the suppression gate: a
    one-click unsubscribe or a hard bounce flips it false and every send skips
    the address (Spam Act 2003 mandates a working, no-login unsubscribe).
    Re-importing a suppressed address keeps it suppressed because the upsert
    lands on the same (org, email) row.
    """
    __tablename__ = "comms_contacts"
    __table_args__ = (
        UniqueConstraint("organisation_id", "email", name="uq_comms_contact_org_email"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    email = Column(Text, nullable=False)
    name = Column(Text, nullable=True)
    source = Column(Text, nullable=False, server_default="manual")  # player | member | import | manual
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    member_id = Column(UUID(as_uuid=True), ForeignKey("fee_members.id", ondelete="SET NULL"), nullable=True)
    # Set when this contact was exported from the marketing directory, so a
    # campaign send can flag the source club emailed.
    marketing_club_id = Column(UUID(as_uuid=True), ForeignKey("marketing_clubs.id", ondelete="SET NULL"), nullable=True)
    subscribed = Column(Boolean, nullable=False, server_default="true", default=True)
    unsubscribed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    bounced = Column(Boolean, nullable=False, server_default="false", default=False)
    bounced_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Admin exclusion (from the marketing directory) — kept out of every audience,
    # distinct from a recipient opt-out (subscribed) or a bounce.
    excluded = Column(Boolean, nullable=False, server_default="false", default=False)
    excluded_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Per-club complaint state (mirror of bounced, migration 110): a spam complaint
    # routed back from SES. The address is also added to the global
    # email_suppressions table; this flag is the per-club view for the UI/audience.
    complained = Column(Boolean, nullable=False, server_default="false", default=False)
    complained_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Per-person, per-category email preferences (migration 110): a JSONB map of
    # category → bool (transactional / operational / news / marketing). Absent key
    # ⇒ opted in. transactional is never gated. See services/comms_policy.py.
    preferences = Column(JSONB, nullable=False, server_default="{}", default=dict)
    # Per-contact merge-variable overrides (migration 115): key → value for the
    # editable merge variables (first_name / club / association / utm_code / state /
    # website). An override wins over the value derived from the linked directory
    # club or the org default, so any contact (manual, imported or exported) can be
    # personalised. Absent key ⇒ use the derived default.
    merge_vars = Column(JSONB, nullable=False, server_default="{}", default=dict)
    tags = Column(JSONB, nullable=False, server_default="[]", default=list)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommsCampaign(Base):
    """One email send (draft → sending → sent/error).

    ``body_html`` is the editor content; ``body_text`` is the plain-text
    alternative (auto-derived when NULL). ``audience`` records the segment the
    admin chose, and ``stats`` accumulates the per-send tallies for the history
    view (recipients / sent / failed / skipped).
    """
    __tablename__ = "comms_campaigns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    subject = Column(Text, nullable=False, server_default="")
    # Human name for the Emails list (migration 132). Blank → auto-filled from the
    # subject + a -MMDD-HH:MM timestamp at send. description is an optional note.
    name = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    preheader = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    body_text = Column(Text, nullable=True)
    audience = Column(JSONB, nullable=False, server_default="{}", default=dict)
    # UTM tags appended to outbound links at render (migration 113). Only applied
    # for the BetterCricket marketing-outreach org — a club's own member email
    # never gets UTM tagging. Keys: utm_source / utm_medium / utm_campaign / ...
    utm = Column(JSONB, nullable=False, server_default="{}", default=dict)
    # The template this email was started from (migration 116) — origin link only,
    # copy-on-use still applies. SET NULL so deleting a template keeps the campaign.
    template_id = Column(UUID(as_uuid=True), ForeignKey("comms_templates.id", ondelete="SET NULL"), nullable=True)
    status = Column(Text, nullable=False, server_default="draft")  # draft | sending | sent | error
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    stats = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommsRecipient(Base):
    """Per-recipient delivery row for a campaign send — the audit of who got
    what. ``provider_message_id`` is the id the email provider returned (lets a
    future webhook reconcile delivered/opened/bounced)."""
    __tablename__ = "comms_recipients"
    __table_args__ = (
        UniqueConstraint("campaign_id", "email", name="uq_comms_recipient_campaign_email"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("comms_campaigns.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("comms_contacts.id", ondelete="SET NULL"), nullable=True)
    email = Column(Text, nullable=False)
    name = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="queued")  # queued | sent | failed | skipped
    provider_message_id = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class WizardClubList(Base):
    """One wizard club's inclusion in an auto-generated BetterComms list
    (migration 251).

    The Meta Ads page names the clubs that searched for themselves or picked
    themselves in the registration wizard; "Clubs Searched or Selected in the
    Wizard" turns a filtered set of them into a list of their Club Directory
    contacts. This is the record of that export, and it is what makes
    per-club email reporting possible: a sent campaign carries its audience
    ``list_id``, a recipient carries its contact, and a contact carries its
    ``marketing_club_id``.

    ``list_id`` deliberately has NO foreign key. A super admin deleting an old
    list must not take the club's email history with it, and a sent campaign's
    stored audience keeps the same id either way, so the reporting still
    resolves once the list itself is gone.
    """
    __tablename__ = "wizard_club_lists"
    __table_args__ = (
        UniqueConstraint("list_id", "club_key", name="uq_wizard_club_lists_list_club"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    list_id = Column(UUID(as_uuid=True), nullable=False)
    list_name = Column(Text, nullable=True)
    # The normalised (lowercased, trimmed) wizard club name — the same key the
    # Meta Ads selected/searched tables group on.
    club_key = Column(Text, nullable=False)
    club_name = Column(Text, nullable=False)
    marketing_club_id = Column(UUID(as_uuid=True), ForeignKey("marketing_clubs.id", ondelete="SET NULL"), nullable=True)
    contacts_added = Column(Integer, nullable=False, server_default="0", default=0)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommsSegment(Base):
    """A saved dynamic segment (migration 111, BetterComms Phase 2).

    ``definition`` is a JSONB rule set ({"match": "all", "rules": [{field, op,
    value}, ...]}) evaluated at send time against the club's contacts joined to
    the player + current-season stats. Not a stored membership — it re-evaluates
    every time, so it always reflects current data. See
    services/comms_segments.py.
    """
    __tablename__ = "comms_segments"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_comms_segment_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    definition = Column(JSONB, nullable=False, server_default="{}", default=dict)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommsTemplate(Base):
    """A reusable email template (migration 113, BetterComms Phase 3).

    ``html`` is the full email HTML — built from scratch, pasted, or imported from
    a .html file. A campaign can start from a template (copy-on-use). Rendering
    merges variables anywhere (incl. link URLs) and always injects the mandatory
    unsubscribe footer, so a template can never opt out of unsubscribe.
    """
    __tablename__ = "comms_templates"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_comms_template_org_name"),
        UniqueConstraint("organisation_id", "sales_template_key", name="uq_comms_template_org_sales_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    # NULL for a template that's only ever used as a campaign's starting body
    # (the campaign supplies its own subject) — set for a template that is
    # itself sent as a self-contained email (migration 260; the Sales
    # Workspace's built-in one-to-one templates).
    subject = Column(Text, nullable=True)
    html = Column(Text, nullable=False, server_default="")
    # Migration 261: the stable machine key (services/sales_email.py's
    # BUILT_IN_TEMPLATES, e.g. 'trial_information') this row backs in the
    # Sales Workspace's Send an Email dropdown, if any -- NULL for an
    # ordinary club template. Lets ``name`` be renamed freely without
    # breaking which dropdown entry resolves to this row; a plain unique
    # constraint on (organisation_id, sales_template_key) permits any
    # number of NULLs (SQL: NULL is never equal to NULL) so it only ever
    # constrains the handful of sales-linked rows.
    sales_template_key = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommsList(Base):
    """A curated static list of contacts (migration 112) — the counterpart to a
    dynamic segment. Membership is the fixed set in ``comms_list_members``."""
    __tablename__ = "comms_lists"
    __table_args__ = (
        UniqueConstraint("organisation_id", "name", name="uq_comms_list_org_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    # 'manual' = created by hand via the Lists page Create button; 'auto' =
    # minted by another BetterCricket function (migration 203) — the first is
    # the CRM Sales Pipeline "Create List" action. The Lists page groups the
    # two into separate sections for super admins. `origin` is a short label
    # for what generated an auto list (e.g. "CRM Sales Pipeline"), NULL for a
    # manual one.
    source = Column(Text, nullable=False, server_default="manual", default="manual")
    origin = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CommsListMember(Base):
    """One contact's membership of a static list (migration 112). Cascaded to both
    the list and the contact, so a deleted contact drops out automatically."""
    __tablename__ = "comms_list_members"
    __table_args__ = (
        UniqueConstraint("list_id", "contact_id", name="uq_comms_list_member"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    list_id = Column(UUID(as_uuid=True), ForeignKey("comms_lists.id", ondelete="CASCADE"), nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("comms_contacts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class EmailSuppression(Base):
    """Global, address-level suppression (migration 110, BetterComms Phase 1).

    The ONE piece of cross-club comms state. A hard bounce or a spam complaint is
    a fact about the mailbox, not a club, so it is keyed on the email and blocks
    that address across every club's sends. Per-club opt-outs stay on
    ``comms_contacts.subscribed``; this table is only the global deliverability
    truth. ``reason`` is hard_bounce | complaint | manual.
    """
    __tablename__ = "email_suppressions"
    __table_args__ = (
        UniqueConstraint("email", name="uq_email_suppressions_email"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, nullable=False)  # stored lowercased + trimmed
    reason = Column(Text, nullable=False)
    source = Column(Text, nullable=True)   # ses | admin | import
    detail = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class EmailEvent(Base):
    """Append-only SES event audit (migration 110, BetterComms Phase 1).

    One row per delivery / bounce / complaint / reject / delay / open / click,
    tied back to the person + campaign via the recipient's ``provider_message_id``
    (= the SES ``messageId``). Deduped on (ses_message_id, event_type, email) so a
    redelivered SNS notification is a no-op. The spine for analytics later.
    """
    __tablename__ = "email_events"
    __table_args__ = (
        UniqueConstraint("ses_message_id", "event_type", "email", name="uq_email_event_dedupe"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("comms_campaigns.id", ondelete="SET NULL"), nullable=True)
    recipient_id = Column(UUID(as_uuid=True), ForeignKey("comms_recipients.id", ondelete="SET NULL"), nullable=True)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("comms_contacts.id", ondelete="SET NULL"), nullable=True)
    email = Column(Text, nullable=True)
    event_type = Column(Text, nullable=False)     # delivery | bounce | complaint | reject | deliverydelay | open | click | send
    event_subtype = Column(Text, nullable=True)   # Permanent / Transient, etc.
    reason = Column(Text, nullable=True)
    ses_message_id = Column(Text, nullable=True)
    payload = Column(JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


# ─── Marketing club directory — BetterCricket outreach (migration 095) ────────
# The crawled CA/grassroots club universe. Prospects, not customers, so decoupled
# from Organisation (same precedent as ClubOnboardingRequest). The crawl is
# resumable through this table: detail_fetched_at IS NULL = a frontier node
# discovered via an affiliation but not yet detailed.

class MarketingClub(Base):
    """One Australian cricket club discovered via the PlayHQ public directory
    (search enumerates clubs + committees; the main graph maps each to the
    association[s] it plays in). ``grassroots_guid`` holds the PlayHQ search GUID
    (dedup key), ``playhq_id`` the short ``routingCode`` the main graph keys on.
    ``existing_org_id`` links a row that is already a BetterStats customer so
    outreach can skip it. ``raw_json`` keeps the full search payload so re-crawls
    are cheap and new fields need no re-fetch."""
    __tablename__ = "marketing_clubs"
    __table_args__ = (
        UniqueConstraint("grassroots_guid", name="uq_marketing_club_guid"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grassroots_guid = Column(Text, nullable=False)
    playhq_id = Column(Text, nullable=True)
    mycricket_id = Column(Integer, nullable=True)
    name = Column(Text, nullable=False)
    short_name = Column(Text, nullable=True)
    kind = Column(Text, nullable=False, server_default="club")  # club | association
    association_name = Column(Text, nullable=True)   # primary (first) association
    association_guid = Column(Text, nullable=True)
    # All association(s) the club plays in: [{"id","name","competition"}, …].
    # NULL = not yet fetched (enrichment frontier); [] = fetched, none.
    associations = Column(JSONB, nullable=True)
    website_url = Column(Text, nullable=True)
    contact_email = Column(Text, nullable=True)
    contact_phone = Column(Text, nullable=True)
    address_line1 = Column(Text, nullable=True)
    address_line2 = Column(Text, nullable=True)
    suburb = Column(Text, nullable=True)
    state = Column(Text, nullable=True)
    postcode = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    latitude = Column(Numeric(10, 6), nullable=True)
    longitude = Column(Numeric(10, 6), nullable=True)
    logo_url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    is_playhq = Column(Boolean, nullable=True)
    status = Column(Text, nullable=False, server_default="new")  # new|enriched|contacted|onboarded|suppressed
    source = Column(Text, nullable=False, server_default="grassroots_api")
    raw_json = Column(JSONB, nullable=True)
    existing_org_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="SET NULL"), nullable=True)
    # Marked emailed (so it isn't emailed again): manually (external campaign) or
    # automatically when a BetterAdmin Comms campaign sends to it.
    emailed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    emailed_via = Column(Text, nullable=True)   # manual | campaign
    emailed_note = Column(Text, nullable=True)
    # Admin exclusion: never export to outreach (reversible). Hard guard.
    excluded = Column(Boolean, nullable=False, server_default="false", default=False)
    excluded_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Editable outreach UTM code (default: first word of name + "-cricket-club").
    utm_code = Column(Text, nullable=True)
    # Sales-pipeline state, set by a super admin in the Clubs Directory (no
    # automated source). Module keys are core/select/socials/admin/iq/fantasy.
    trial_modules = Column(JSONB, nullable=False, server_default="[]", default=list)
    requested_trial_modules = Column(JSONB, nullable=False, server_default="[]", default=list)
    # Demo follow-on state: NULL/'' = no demo; else in_trial | trial_expired | customer.
    demo_status = Column(Text, nullable=True)
    # Sales disposition: club contacted and explicitly not interested. Manual, and it
    # overrides the computed engagement tier in the CRM (never auto-recomputed away).
    not_interested = Column(Boolean, nullable=False, server_default="false", default=False)
    # Cached copy of the last-computed Twenty engagementScore/-Tier — written by
    # every _engagement() call (twenty_sync.py) regardless of what triggered it
    # (manual export, bulk export, "Refresh Twenty scores", "Refresh Twenty
    # leads/tasks", or a nightly job), so the Club Directory / BetterComms
    # Contacts+Lists / Segments can filter on a real number without recomputing
    # this per-club scan themselves. Can lag the live Twenty value by up to
    # however long since this club's score was last (re)computed.
    engagement_score = Column(Integer, nullable=True)
    engagement_tier = Column(Text, nullable=True)
    engagement_scored_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Day-over-day baseline for the CRM pipeline's engagement up/down arrow
    # (migration 192). There is no score-history table — _apply_engagement_cache
    # (twenty_sync.py) rolls the then-current engagement_score into _prev the
    # first time it writes on a NEW calendar day, so _prev holds the last score
    # recorded on an earlier day and (current vs _prev) is the day-over-day
    # direction. _prev_date is the calendar day that _prev value belongs to.
    engagement_score_prev = Column(Integer, nullable=True)
    engagement_score_prev_date = Column(Date, nullable=True)
    # Suburb-level admin boundary polygon (from OpenStreetMap/Nominatim), fetched
    # lazily and cached forever — the closest free approximation to a real
    # postcode-area shape (no AU postcode boundary dataset is bundled here).
    # NULL = never looked up; {} = looked up, nothing found; else a GeoJSON
    # Polygon/MultiPolygon. See services/nominatim_client.py.
    boundary_geojson = Column(JSONB, nullable=True)
    detail_fetched_at = Column(TIMESTAMP(timezone=True), nullable=True)
    first_seen_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    last_crawled_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    contacts = relationship("MarketingClubContact", back_populates="club",
                            cascade="all, delete-orphan")


class MarketingClubContact(Base):
    """An emailable contact for a marketing club. Many-per-club so President /
    Secretary / Treasurer (manual enrichment) can be added later; Phase 1 holds
    the single club contact the grassroots org-detail endpoint exposes (usually a
    role mailbox). ``role_rank`` sequences the priority roles to the top.
    ``subscribed`` is the global suppression gate, synced from BetterComms
    unsubscribes/bounces so an opt-out is never re-contacted across campaigns."""
    __tablename__ = "marketing_club_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    marketing_club_id = Column(UUID(as_uuid=True), ForeignKey("marketing_clubs.id", ondelete="CASCADE"), nullable=False)
    full_name = Column(Text, nullable=True)
    role = Column(Text, nullable=True)
    role_rank = Column(Integer, nullable=False, server_default="99")
    email = Column(Text, nullable=True)
    mobile = Column(Text, nullable=True)
    source = Column(Text, nullable=False, server_default="api")  # api | website | manual
    # Whether this contact is ticked to receive outreach (drives export_to_comms).
    # Office bearers are pre-selected on insert; a super admin adjusts per club.
    outreach_selected = Column(Boolean, nullable=False, server_default="false", default=False)
    # When this contact was pushed into BetterComms (comms_contacts under the
    # outreach org). NULL = never exported. Cleared when the comms contact is
    # deleted or reconciled away, so the directory badge/filter stay accurate.
    exported_at = Column(TIMESTAMP(timezone=True), nullable=True)
    subscribed = Column(Boolean, nullable=False, server_default="true", default=True)
    unsubscribed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    bounced = Column(Boolean, nullable=False, server_default="false", default=False)
    bounced_at = Column(TIMESTAMP(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    # Migration 256 (Sales Workspace): the PERSON-level "don't call me" flag —
    # distinct from `subscribed`, which is email-opt-out only. The club-wide
    # equivalent is marketing_clubs.not_interested, not a column here.
    do_not_contact = Column(Boolean, nullable=False, server_default="false", default=False)
    do_not_contact_reason = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    club = relationship("MarketingClub", back_populates="contacts")


# ─── BetterCRM — People/Contacts + the internal & club-facing Deal pipeline ──
# (migration 173). One schema, two scopes: 'platform' (BetterCricket's own
# sales pipeline — organisation_id NULL, usually linked to a MarketingClub
# prospect row) and 'club' (the BetterAdmin CRM module — organisation_id set,
# gated by the "crm" entitlement key + MANAGE_CRM). See services/crm.py.

class CrmPerson(Base):
    """A generic contact — player, parent, coach, committee member, volunteer,
    sponsor contact, association official… — one row per real person, tagged
    with roles via CrmPersonRole rather than a table per role. ``player_id``
    is a nullable bridge to the existing per-club Player identity (additive
    only; the Player table's own uuid5-on-collision scheme is untouched) so a
    future unified profile has somewhere to anchor without a migration."""
    __tablename__ = "crm_people"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    marketing_club_id = Column(UUID(as_uuid=True), ForeignKey("marketing_clubs.id", ondelete="SET NULL"), nullable=True)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    full_name = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    phone = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    # Migration 255: set only when this row was lazily materialized from a
    # Club Directory contact (see services/sales_workspace.
    # resolve_or_materialize_person) — traces it back and is the dedupe key
    # so touching the same directory contact twice never mints a second row.
    directory_contact_id = Column(UUID(as_uuid=True), ForeignKey("marketing_club_contacts.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    roles = relationship("CrmPersonRole", cascade="all, delete-orphan", passive_deletes=True)


class CrmPersonRole(Base):
    """One role a Person holds — a Person can have several (a parent who is
    also a volunteer and a sponsor contact), each with its own tenure."""
    __tablename__ = "crm_person_roles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(UUID(as_uuid=True), ForeignKey("crm_people.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    role = Column(Text, nullable=False)
    title = Column(Text, nullable=True)
    started_at = Column(Date, nullable=True)
    ended_at = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CrmPipeline(Base):
    """A stage-ordered pipeline. 'platform' scope has exactly one (Better
    Cricket's sales pipeline); a club can in principle run more than one
    (e.g. Sponsorship vs Grants) though only a default is seeded today."""
    __tablename__ = "crm_pipelines"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(Text, nullable=False, server_default="club", default="club")
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    name = Column(Text, nullable=False)
    is_default = Column(Boolean, nullable=False, server_default="false", default=False)
    # Club-scope "trackers" (migration 174): which preset catalogue entry this
    # was added from (NULL = a custom, club-authored tracker), and whether the
    # club currently has it turned on — "removing" a tracker deactivates it
    # rather than deleting, so its historical deals survive re-adding it later.
    template_key = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true", default=True)
    # Migration 188: default-stage keys (see services/crm.py's
    # PLATFORM_DEFAULT_STAGES) a super admin has deliberately deleted from
    # this pipeline — the reconciliation pass that backfills a newly
    # introduced default stage onto an old pipeline checks this list first,
    # so a deliberate delete stays deleted instead of reappearing on the next
    # read.
    removed_stage_keys = Column(JSONB, nullable=False, server_default="[]", default=list)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    stages = relationship("CrmStage", cascade="all, delete-orphan", passive_deletes=True,
                          order_by="CrmStage.position")


class CrmStage(Base):
    """A pipeline stage. ``key`` is a stable slug the app looks up by (auto
    stage-advance hooks, the Won/Lost buttons) — ``name`` is the display label
    a super admin / club admin can freely rename without breaking those
    lookups. ``default_probability`` is what a deal shows unless it carries
    its own override."""
    __tablename__ = "crm_stages"
    __table_args__ = (
        UniqueConstraint("pipeline_id", "key", name="uq_crm_stages_pipeline_key"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("crm_pipelines.id", ondelete="CASCADE"), nullable=False)
    key = Column(Text, nullable=False)
    name = Column(Text, nullable=False)
    position = Column(Integer, nullable=False, server_default="0", default=0)
    default_probability = Column(Integer, nullable=False, server_default="0", default=0)
    is_won = Column(Boolean, nullable=False, server_default="false", default=False)
    is_lost = Column(Boolean, nullable=False, server_default="false", default=False)
    # Migration 183: drops the column from the Kanban board without deleting
    # the stage — a deal can still be filed into/out of it via the Stage
    # dropdown, which always lists every stage regardless of this flag.
    hidden_from_board = Column(Boolean, nullable=False, server_default="false", default=False)
    # Collapse a stage's column to a thin strip on the board (the "Minimize this
    # column" control). Persisted per stage like hidden_from_board so the
    # preference survives across sessions, rather than being a throwaway
    # per-page-view toggle.
    minimized = Column(Boolean, nullable=False, server_default="false", default=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CrmAutomationRule(Base):
    """A configurable, persistent criterion for the PLATFORM pipeline's
    automatic deal creation/stage-promotion (migration 190) — replaces what
    used to be hardcoded thresholds and target stages. ``trigger`` is one of
    services/crm_rules.py's TRIGGERS keys (enquiry_count, engagement_score,
    trial_requested, trial_started, subscription_won, subscription_cancelled,
    self_serve_signup). ``params`` carries the trigger-specific numeric
    condition ({"count": N} or {"threshold": N}; {} for the others).
    ``target_stage_key`` is a platform CrmStage.key — looked up dynamically at
    evaluation time, so a rule harmlessly no-ops if that stage is later
    renamed/deleted rather than erroring. ``force`` bypasses the normal
    advance-only (never-move-backward) semantics, matching the historical
    self-serve-signup behaviour. Managed by a super admin at
    /admin/super/crm-automation; evaluated by crm_rules.resolve()."""
    __tablename__ = "crm_automation_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trigger = Column(Text, nullable=False)
    label = Column(Text, nullable=False)
    params = Column(JSONB, nullable=False, server_default="{}", default=dict)
    target_stage_key = Column(Text, nullable=False)
    force = Column(Boolean, nullable=False, server_default="false", default=False)
    enabled = Column(Boolean, nullable=False, server_default="true", default=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CrmDeal(Base):
    """One Opportunity/Deal. ``value_cents``/``module_keys`` mirror the public
    pricing vocabulary (see billing_pricing.py) for a platform deal's product
    interest; a club deal (sponsorship renewal, grant application…) leaves
    module_keys empty and just uses value_cents + title/notes/activities."""
    __tablename__ = "crm_deals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope = Column(Text, nullable=False, server_default="club", default="club")
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    marketing_club_id = Column(UUID(as_uuid=True), ForeignKey("marketing_clubs.id", ondelete="SET NULL"), nullable=True)
    pipeline_id = Column(UUID(as_uuid=True), ForeignKey("crm_pipelines.id", ondelete="CASCADE"), nullable=False)
    stage_id = Column(UUID(as_uuid=True), ForeignKey("crm_stages.id", ondelete="RESTRICT"), nullable=False)
    title = Column(Text, nullable=False)
    value_cents = Column(Integer, nullable=False, server_default="0", default=0)
    currency = Column(Text, nullable=False, server_default="AUD", default="AUD")
    probability = Column(Integer, nullable=True)  # NULL = use the stage's default_probability
    module_keys = Column(JSONB, nullable=False, server_default="[]", default=list)
    expected_close_date = Column(Date, nullable=True)
    status = Column(Text, nullable=False, server_default="open", default="open")  # open | won | lost
    lost_reason = Column(Text, nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    # Migration 264: commission attribution, which is NOT owner_user_id.
    # owner_user_id says who is working the club now and a super admin may
    # move it at will; this says which sales rep EARNED it, set once by the
    # first qualifying action (a logged call outcome other than General Note,
    # or an email sent to one of the club's contacts) and never moved by a
    # later reassignment. See services/sales_workspace.attribute_commission.
    commission_rep_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    commission_attributed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    commission_attributed_via = Column(Text, nullable=True)  # call | email
    # Migration 277: the commission rate (percent) STAMPED at the moment this
    # deal was won. Editing a rep's rate afterwards must not rewrite what they
    # already earned last quarter; the forecast over OPEN deals reads the LIVE
    # rate instead, because a forecast is about what is still to come. NULL on
    # every open deal, and on one won before this shipped (which then falls
    # back to the rep's current rate — see services/sales_commissions.py).
    commission_rate_percent = Column(Numeric(6, 3), nullable=True)
    source = Column(Text, nullable=True)  # manual | auto_enquiry | auto_trial | self_serve_trial | twenty_import
    # Migration 184: how this club came to be onboarded (independent of `source`,
    # which is about how the DEAL/row was created) — self_serve_trial |
    # super_admin_trial | direct_subscriber | none.
    onboarding_method = Column(Text, nullable=True)
    # Original acquisition channel — edm | meta_ads | outreach | referral |
    # google_search | ai_search_assistants | other.
    lead_source = Column(Text, nullable=True)
    # A super admin's discretionary discount on top of the module-derived
    # value_cents — at most one of amount/percent is set at a time (enforced
    # at the API layer); discount_reason is mandatory whenever either is set.
    discount_amount_cents = Column(Integer, nullable=True)
    discount_percent = Column(Integer, nullable=True)
    discount_reason = Column(Text, nullable=True)
    # Migration 186: 'auto' (module_keys last set by the analytics-inferred
    # recalculation) vs 'manual' (a super admin explicitly toggled a module
    # chip) — lets the UI show which mode a deal is in and offer a
    # "recalculate from analytics" action that only makes sense in 'auto'.
    product_interest_source = Column(Text, nullable=False, server_default="auto", default="auto")
    # Migration 189: set the moment a human explicitly drags/sets this deal's
    # stage — the auto-promotion engine (Contact-Us count, engagement score >
    # 70) then leaves it alone rather than nudging it forward again.
    stage_auto_locked = Column(Boolean, nullable=False, server_default="false", default=False)
    archived_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    stage = relationship("CrmStage")
    contacts = relationship("CrmDealContact", cascade="all, delete-orphan", passive_deletes=True)


class CrmDealContact(Base):
    """Links a Person to a Deal (the people involved — decision maker,
    influencer, the officer who first enquired…)."""
    __tablename__ = "crm_deal_contacts"
    __table_args__ = (
        UniqueConstraint("deal_id", "person_id", name="uq_crm_deal_contacts"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="CASCADE"), nullable=False)
    person_id = Column(UUID(as_uuid=True), ForeignKey("crm_people.id", ondelete="CASCADE"), nullable=False)
    role_on_deal = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    person = relationship("CrmPerson")


class CrmActivity(Base):
    """One timeline entry — a call, email, meeting or note against a Deal
    and/or a Person. ``meta`` carries structured detail for system-logged
    entries (e.g. the engagement score that triggered an auto stage-move)."""
    __tablename__ = "crm_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="CASCADE"), nullable=True)
    person_id = Column(UUID(as_uuid=True), ForeignKey("crm_people.id", ondelete="CASCADE"), nullable=True)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=True)
    type = Column(Text, nullable=False, server_default="note", default="note")
    body = Column(Text, nullable=True)
    occurred_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    meta = Column(JSONB, nullable=True)
    # Migration 255 (Sales Workspace): structured call-outcome key (see
    # services/sales_workspace.CALL_OUTCOMES) — NULL for anything that isn't
    # a logged call. next_follow_up_at is the callback/follow-up date
    # captured off a call log, shown inline until a dedicated queue screen
    # exists.
    outcome = Column(Text, nullable=True)
    next_follow_up_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Migration 256: explicit "resolved" marker for a pending follow-up — a
    # follow-up is pending while next_follow_up_at is set and this is NULL.
    follow_up_done_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class SalesList(Base):
    """Migration 257: one row per Sales Workspace import batch — a Wizard
    Clubs pull, a CRM export, a Club Directory selection, or a manual pick.
    A thin provenance/grouping layer: assignment still lives entirely on
    ``crm_deals.owner_user_id``, and a club's calls/notes/stage are the same
    wherever it's viewed from. A club can sit in several lists."""
    __tablename__ = "sales_lists"

    SOURCE_TYPES = ("wizard_clubs", "manual")

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    source_type = Column(Text, nullable=False, server_default="manual", default="manual")
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class SalesListClub(Base):
    """Migration 257: many-to-many membership of a club in a Sales List.
    Unique per (list, club) so re-importing an overlapping selection is
    idempotent rather than duplicating the row."""
    __tablename__ = "sales_list_clubs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sales_list_id = Column(UUID(as_uuid=True), ForeignKey("sales_lists.id", ondelete="CASCADE"), nullable=False)
    marketing_club_id = Column(UUID(as_uuid=True), ForeignKey("marketing_clubs.id", ondelete="CASCADE"), nullable=False)
    added_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CrmEvent(Base):
    """A scheduled calendar event on the platform Sales Pipeline (migration
    196) — a Call/Demo/Meeting/Review Deal/Other planned for a future date &
    time. Richer than a ``CrmActivity`` note (which only records something that
    already happened): an event carries a ``starts_at``, an optional Title,
    Location, an Owner (a super-admin ``User``), an associated Club Contact
    (``CrmPerson``) and up to two alert offsets. ``body`` is the free-text note
    that a Note-of-type-Event still carries. Created either from a Deal's card
    detail (``deal_id`` set, ``marketing_club_id`` copied from the deal) or
    standalone from the Events page (``deal_id`` NULL, club optional). Deleting
    the deal SET NULLs ``deal_id`` so the event survives on the calendar."""
    __tablename__ = "crm_events"

    # First Alert / Second Alert offsets — stored as a stable code, the actual
    # alert time is starts_at minus this offset (computed on read).
    ALERT_CODES = ("at_time", "5m", "10m", "15m", "30m", "1h", "2h", "1d", "2d", "1w")
    EVENT_TYPES = ("call", "demo", "meeting", "review_deal", "follow_up", "other")

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deal_id = Column(UUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True)
    marketing_club_id = Column(UUID(as_uuid=True), ForeignKey("marketing_clubs.id", ondelete="SET NULL"), nullable=True)
    contact_person_id = Column(UUID(as_uuid=True), ForeignKey("crm_people.id", ondelete="SET NULL"), nullable=True)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(Text, nullable=False, server_default="meeting", default="meeting")
    title = Column(Text, nullable=True)
    location = Column(Text, nullable=True)
    body = Column(Text, nullable=True)
    starts_at = Column(TIMESTAMP(timezone=True), nullable=False)
    first_alert = Column(Text, nullable=True)
    second_alert = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class CrmTarget(Base):
    """One sales target for a period (migration 185) — BetterCricket's own
    platform pipeline only (there is no club-scope equivalent). ``period_type``
    is 'month' | 'quarter' | 'fiscal_year'; ``period_key`` is the matching key
    ('2026-07' | '2026-Q3' | 'FY2026' — FY runs 1 Jul -> 30 Jun, named for the
    year it ENDS in, the common AU convention). Every target_* field is
    optional — a target can track just clubs_won without also setting ARR,
    for instance."""
    __tablename__ = "crm_targets"
    __table_args__ = (
        UniqueConstraint("period_type", "period_key", name="uq_crm_targets_period"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    period_type = Column(Text, nullable=False)
    period_key = Column(Text, nullable=False)
    target_clubs_won = Column(Integer, nullable=True)
    target_arr_cents = Column(BigInteger, nullable=True)
    target_revenue_cents = Column(BigInteger, nullable=True)
    target_trials = Column(Integer, nullable=True)
    target_conversion_rate = Column(Integer, nullable=True)  # percent, 0-100
    notes = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class SalesCommissionRate(Base):
    """Migration 277: what percentage of a won deal's value a sales rep earns.

    One row per rep, plus exactly ONE row with a NULL ``user_id`` — the
    platform default a rep with no row of their own falls back to (two partial
    unique indexes enforce both halves of that). Seeded at 0 rather than at a
    number we invented: a commission percentage is a commercial decision, so
    the screen asks for one."""
    __tablename__ = "sales_commission_rates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    rate_percent = Column(Numeric(6, 3), nullable=False, server_default="0", default=0)
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class SalesCommissionPayment(Base):
    """Migration 277: one commission payout recorded against a sales rep.

    Commission DUE is what they have earned on won deals minus what is
    recorded here, so a payment is the only thing that brings it down.
    Deliberately per-REP and not per-deal: a payout is a payment run covering
    whatever was owed at the time, not a line-by-line settlement of individual
    deals, and pretending otherwise would mean apportioning a round number
    across deals nobody apportioned it across."""
    __tablename__ = "sales_commission_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rep_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    amount_cents = Column(BigInteger, nullable=False)
    paid_on = Column(Date, nullable=False)
    reference = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


# ─── KlubPro → BetterStats migration audit + rollback (migration 072) ─────────
# These live in BetterStats (not KlubPro) so the before-images and the audit
# survive even if the KlubPro database is later decommissioned, and a rollback
# is a pure BetterStats operation. One batch per executed import; one backup row
# per BetterStats row the import touched (a player UPDATE keeps the old field
# values; a sponsor INSERT just records the new id so rollback can delete it).

class KlubproMigrationBatch(Base):
    """One executed KlubPro import (player or sponsor) — the unit of rollback."""
    __tablename__ = "klubpro_migration_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind = Column(Text, nullable=False)                # 'player' | 'sponsor'
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    # The klubpro_migration.club_mappings.id this import ran for. No FK — it lives
    # in the external KlubPro database.
    club_mapping_id = Column(UUID(as_uuid=True), nullable=True)
    klubpro_club_id = Column(Text, nullable=True)
    status = Column(Text, nullable=False, server_default="imported")  # imported | rolled_back
    counts = Column(JSONB, nullable=True)              # {"updated": n, "inserted": n, "skipped": n}
    operator_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    operator_name = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    rolled_back_at = Column(TIMESTAMP(timezone=True), nullable=True)


class KlubproMigrationBackup(Base):
    """Before/after image of a single BetterStats row touched by an import.

    ``action`` 'update' carries ``before_data`` (the field values to restore on
    rollback); 'insert' carries only ``after_data`` (rollback deletes the row).
    """
    __tablename__ = "klubpro_migration_backups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id = Column(UUID(as_uuid=True), ForeignKey("klubpro_migration_batches.id", ondelete="CASCADE"), nullable=False)
    target_table = Column(Text, nullable=False)        # 'players' | 'org_sponsors'
    target_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(Text, nullable=False)              # 'update' | 'insert'
    before_data = Column(JSONB, nullable=True)         # NULL for inserts
    after_data = Column(JSONB, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


# ─── BetterFantasyCricket (migration 087) ─────────────────────────────────────
# Internal club fantasy league, scored off the club's own games. Players are the
# club's playing list; matches are the club's fixtures. Fantasy points come from
# the per-innings stats we already hold. Full design: docs/betterfantasycricket.md.

FANTASY_ROLES = ("keeper", "batter", "allrounder", "bowler")
FANTASY_LEAGUE_KINDS = ("global_salary_cap", "mini_salary_cap", "draft")
FANTASY_TXN_TYPES = ("transfer_in", "transfer_out", "draft_pick", "waiver", "trade", "chip")


class FantasySeason(Base):
    """A club's fantasy competition for one real season-year — the umbrella both
    engines hang off. `scoring`/`rules` are JSONB config seeded from the router
    defaults; `included_grade_ids` NULL means every grade counts. Keyed on
    season_year (not a single season_id) because a club year spans several Season
    rows (comps / per-club grassroots ids), the same reason BetterIQ's MVP is
    year-based."""
    __tablename__ = "fantasy_seasons"
    __table_args__ = (
        UniqueConstraint("organisation_id", "season_year", name="uq_fantasy_season_org_year"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    season_year = Column(Integer, nullable=False)
    name = Column(Text, nullable=False)
    status = Column(Text, nullable=False, server_default="setup")   # setup | open | active | completed
    included_grade_ids = Column(JSONB, nullable=True)               # NULL = all grades
    scoring = Column(JSONB, nullable=False, server_default="{}")
    rules = Column(JSONB, nullable=False, server_default="{}")
    registration_open = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FantasyManager(Base):
    """A human entrant (member or supporter), per club. Not a BetterStats account —
    they register through the public fantasy link with a display name and a
    credential (hashed PIN/passphrase). Email is optional; unique per club when set."""
    __tablename__ = "fantasy_managers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    display_name = Column(Text, nullable=False)
    email = Column(Text, nullable=True)
    credential_hash = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(TIMESTAMP(timezone=True), nullable=True)


class FantasyLeague(Base):
    """A competition grouping within a fantasy season. `kind` is the global
    salary-cap ladder (auto-created with the season), a private salary-cap
    mini-league (join code, ranks members' existing global squads), or a draft
    league (unique ownership, its own squads, snake/auction + total/h2h)."""
    __tablename__ = "fantasy_leagues"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fantasy_season_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_seasons.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    kind = Column(Text, nullable=False, server_default="global_salary_cap")
    name = Column(Text, nullable=False)
    join_code = Column(Text, nullable=True)
    draft_type = Column(Text, nullable=True)      # snake | auction
    scoring_type = Column(Text, nullable=True)    # total | h2h
    settings = Column(JSONB, nullable=False, server_default="{}")
    status = Column(Text, nullable=False, server_default="open")
    created_by_manager_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_managers.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FantasySquad(Base):
    """A manager's team in a league. `budget_remaining` is salary-cap only (NULL
    for draft). `chips_used` records which chips have been spent. The picks live
    in FantasySquadPlayer; per-round scoring snapshots into FantasySquadRoundScore."""
    __tablename__ = "fantasy_squads"
    __table_args__ = (
        UniqueConstraint("league_id", "manager_id", name="uq_fantasy_squad_league_manager"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fantasy_season_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_seasons.id", ondelete="CASCADE"), nullable=False)
    league_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_leagues.id", ondelete="CASCADE"), nullable=False)
    manager_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_managers.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    team_name = Column(Text, nullable=False)
    budget_remaining = Column(Numeric(8, 1), nullable=True)
    free_transfers = Column(Integer, nullable=False, server_default="1")
    chips_used = Column(JSONB, nullable=False, server_default="{}")
    total_points = Column(Numeric(8, 2), nullable=False, server_default="0")
    joined_round = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    players = relationship("FantasySquadPlayer", back_populates="squad", cascade="all, delete-orphan")


class FantasySquadPlayer(Base):
    """One pick in a squad. `role` is the slot it fills against the role quota;
    `is_captain`/`is_vice_captain` drive the scoring multiplier and its fallback;
    `purchase_price` backs the salary-cap sell-on value."""
    __tablename__ = "fantasy_squad_players"
    __table_args__ = (
        UniqueConstraint("squad_id", "player_id", name="uq_fantasy_squad_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    squad_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_squads.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, nullable=False, server_default="batter")
    is_captain = Column(Boolean, nullable=False, server_default="false")
    is_vice_captain = Column(Boolean, nullable=False, server_default="false")
    purchase_price = Column(Numeric(8, 1), nullable=True)
    added_round = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    squad = relationship("FantasySquad", back_populates="players")
    player = relationship("Player")


class FantasyLeagueMember(Base):
    """Manager ↔ league ↔ the squad ranked in that league. For a mini-league the
    squad is the manager's global salary-cap squad; for the global or a draft
    league it's the squad owned there."""
    __tablename__ = "fantasy_league_members"
    __table_args__ = (
        UniqueConstraint("league_id", "manager_id", name="uq_fantasy_league_member"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_leagues.id", ondelete="CASCADE"), nullable=False)
    manager_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_managers.id", ondelete="CASCADE"), nullable=False)
    squad_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_squads.id", ondelete="SET NULL"), nullable=True)
    joined_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FantasyPoolPlayer(Base):
    """The pickable pool, one row per player per fantasy season. Holds the
    fantasy role (+ where it came from), the dynamic price and cached season
    totals. Org-scoped so cross-club shared players never leak between clubs."""
    __tablename__ = "fantasy_pool_players"
    __table_args__ = (
        UniqueConstraint("fantasy_season_id", "player_id", name="uq_fantasy_pool_player"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fantasy_season_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_seasons.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, nullable=False, server_default="batter")
    role_source = Column(Text, nullable=False, server_default="auto")   # admin | profile | auto
    base_price = Column(Numeric(8, 1), nullable=False, server_default="0")
    current_price = Column(Numeric(8, 1), nullable=False, server_default="0")
    total_points = Column(Numeric(8, 2), nullable=False, server_default="0")
    last_round_points = Column(Numeric(8, 2), nullable=False, server_default="0")
    owned_count = Column(Integer, nullable=False, server_default="0")
    price_change = Column(Numeric(6, 1), nullable=False, server_default="0")
    is_available = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    player = relationship("Player")


class FantasyRound(Base):
    """A scoring round (a club weekend), generated from the real game calendar.
    Locks at the first game's start; settles after the weekly sync. Games are
    grouped into the round whose window covers their date."""
    __tablename__ = "fantasy_rounds"
    __table_args__ = (
        UniqueConstraint("fantasy_season_id", "round_number", name="uq_fantasy_round_number"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fantasy_season_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_seasons.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    round_number = Column(Integer, nullable=False)
    name = Column(Text, nullable=True)
    lock_at = Column(TIMESTAMP(timezone=True), nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    status = Column(Text, nullable=False, server_default="upcoming")   # upcoming | locked | scored
    scored_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FantasyPlayerRoundScore(Base):
    """A player's computed fantasy points for one round, with the component
    breakdown. Idempotent on (round, player) — recomputed in place when a
    scorecard is re-synced or corrected."""
    __tablename__ = "fantasy_player_round_scores"
    __table_args__ = (
        UniqueConstraint("round_id", "player_id", name="uq_fantasy_player_round_score"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    fantasy_season_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_seasons.id", ondelete="CASCADE"), nullable=False)
    round_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_rounds.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    base_points = Column(Numeric(8, 2), nullable=False, server_default="0")
    total_points = Column(Numeric(8, 2), nullable=False, server_default="0")   # after role multiplier
    breakdown = Column(JSONB, nullable=False, server_default="{}")
    games_counted = Column(Integer, nullable=False, server_default="0")
    computed_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FantasySquadRoundScore(Base):
    """A squad's result for one round. `points` is the best-11 total with the
    captain doubled before the cut, less any transfer hit; `lineup` is the JSONB
    snapshot of the 12 as they stood at lock (so history survives later transfers)."""
    __tablename__ = "fantasy_squad_round_scores"
    __table_args__ = (
        UniqueConstraint("squad_id", "round_id", name="uq_fantasy_squad_round_score"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    squad_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_squads.id", ondelete="CASCADE"), nullable=False)
    round_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_rounds.id", ondelete="CASCADE"), nullable=False)
    points = Column(Numeric(8, 2), nullable=False, server_default="0")
    raw_points = Column(Numeric(8, 2), nullable=False, server_default="0")
    transfer_hit = Column(Integer, nullable=False, server_default="0")
    transfers_made = Column(Integer, nullable=False, server_default="0")
    chip_used = Column(Text, nullable=True)
    captain_player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    vice_captain_player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    dropped_player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    lineup = Column(JSONB, nullable=False, server_default="[]")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FantasyTransaction(Base):
    """Audit log of a squad action — transfer, waiver, draft pick, trade or chip.
    `counterparty_squad_id` is set for trades; `detail` carries type-specific data."""
    __tablename__ = "fantasy_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    squad_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_squads.id", ondelete="CASCADE"), nullable=False)
    league_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_leagues.id", ondelete="CASCADE"), nullable=True)
    round_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_rounds.id", ondelete="SET NULL"), nullable=True)
    type = Column(Text, nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    counterparty_squad_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_squads.id", ondelete="SET NULL"), nullable=True)
    price = Column(Numeric(8, 1), nullable=True)
    detail = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


# ─── BetterFantasyCricket: draft mode (migration 088) ─────────────────────────

class FantasyDraft(Base):
    """One draft for a draft league. `draft_order` is the manager id order;
    `current_pick` walks the snake; `pick_seconds` is the async per-pick clock."""
    __tablename__ = "fantasy_drafts"
    __table_args__ = (UniqueConstraint("league_id", name="uq_fantasy_draft_league"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_leagues.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    type = Column(Text, nullable=False, server_default="snake")          # snake | auction
    status = Column(Text, nullable=False, server_default="scheduled")    # scheduled | in_progress | complete
    pick_seconds = Column(Integer, nullable=False, server_default="14400")
    current_pick = Column(Integer, nullable=False, server_default="0")
    draft_order = Column(JSONB, nullable=False, server_default="[]")
    rounds = Column(Integer, nullable=False, server_default="12")
    started_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Auction mode (migration 089): the live lot and the nomination pointer. A
    # snake draft pre-creates its pick slots, so these stay 0 / NULL for snake.
    # `nomination_index` walks `draft_order` for whose turn it is to nominate;
    # the `lot_*` columns hold the player currently up for auction, the running
    # high bid and bidder, who nominated it, the anti-snipe deadline, and whether
    # the lot was auto-nominated by the clock.
    nomination_index = Column(Integer, nullable=False, server_default="0")
    lot_player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    lot_high_bid = Column(Numeric(8, 1), nullable=True)
    lot_high_bidder_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_managers.id", ondelete="SET NULL"), nullable=True)
    lot_nominator_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_managers.id", ondelete="SET NULL"), nullable=True)
    lot_deadline = Column(TIMESTAMP(timezone=True), nullable=True)
    lot_auto = Column(Boolean, nullable=False, server_default="false")
    # Per-lot proxy max bids {manager_id: max} (migration 090). Every bid is a max:
    # the system bids up to it, so the displayed price is the runner-up's max plus
    # the increment. Cleared when the lot settles.
    lot_max_bids = Column(JSONB, nullable=False, server_default="{}")
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


class FantasyDraftPick(Base):
    """One slot in the draft order. `player_id` is NULL until the pick is made;
    `auto_picked` marks a pick the clock made on the manager's behalf."""
    __tablename__ = "fantasy_draft_picks"
    __table_args__ = (UniqueConstraint("draft_id", "pick_index", name="uq_fantasy_draft_pick"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_drafts.id", ondelete="CASCADE"), nullable=False)
    pick_index = Column(Integer, nullable=False)
    round_no = Column(Integer, nullable=False)
    manager_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_managers.id", ondelete="CASCADE"), nullable=False)
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    deadline = Column(TIMESTAMP(timezone=True), nullable=True)
    picked_at = Column(TIMESTAMP(timezone=True), nullable=True)
    auto_picked = Column(Boolean, nullable=False, server_default="false")
    bid_amount = Column(Numeric(8, 1), nullable=True)


class FantasyDraftWishlist(Base):
    """A manager's ranked auto-pick preference for a draft (player ids, best first)."""
    __tablename__ = "fantasy_draft_wishlists"
    __table_args__ = (UniqueConstraint("draft_id", "manager_id", name="uq_fantasy_draft_wishlist"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_drafts.id", ondelete="CASCADE"), nullable=False)
    manager_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_managers.id", ondelete="CASCADE"), nullable=False)
    player_ids = Column(JSONB, nullable=False, server_default="[]")


class FantasyWaiverClaim(Base):
    """A claim on an unowned player in a draft league, processed once a round in
    priority order (reverse ladder)."""
    __tablename__ = "fantasy_waiver_claims"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_leagues.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    manager_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_managers.id", ondelete="CASCADE"), nullable=False)
    add_player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    drop_player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="SET NULL"), nullable=True)
    priority = Column(Integer, nullable=False, server_default="0")
    status = Column(Text, nullable=False, server_default="pending")   # pending | approved | rejected
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(TIMESTAMP(timezone=True), nullable=True)


class FantasyTrade(Base):
    """A proposed player swap between two squads in a draft league. `offer` is
    ``{"give": [player_ids], "get": [player_ids]}`` from the proposer's side."""
    __tablename__ = "fantasy_trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_leagues.id", ondelete="CASCADE"), nullable=False)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    proposer_squad_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_squads.id", ondelete="CASCADE"), nullable=False)
    receiver_squad_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_squads.id", ondelete="CASCADE"), nullable=False)
    offer = Column(JSONB, nullable=False, server_default="{}")
    status = Column(Text, nullable=False, server_default="proposed")  # proposed | accepted | rejected | cancelled
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(TIMESTAMP(timezone=True), nullable=True)


class FantasyH2HFixture(Base):
    """A head-to-head pairing for one round in a draft league. A NULL away squad
    is a bye. Points fill in when the round settles."""
    __tablename__ = "fantasy_h2h_fixtures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    league_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_leagues.id", ondelete="CASCADE"), nullable=False)
    round_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_rounds.id", ondelete="SET NULL"), nullable=True)
    round_no = Column(Integer, nullable=False)
    home_squad_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_squads.id", ondelete="CASCADE"), nullable=False)
    away_squad_id = Column(UUID(as_uuid=True), ForeignKey("fantasy_squads.id", ondelete="SET NULL"), nullable=True)
    home_points = Column(Numeric(8, 2), nullable=True)
    away_points = Column(Numeric(8, 2), nullable=True)
    result = Column(Text, nullable=True)   # home | away | draw
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
