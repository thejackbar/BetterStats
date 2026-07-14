from sqlalchemy import (
    Column, Boolean, Integer, Numeric, Date, Text, ForeignKey,
    TIMESTAMP, JSON, UniqueConstraint, LargeBinary
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.sql import func
import uuid

from app.config.settings import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, echo=False)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session_maker() as session:
        yield session


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, unique=True, nullable=True)
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
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    memberships = relationship("ClubMembership", back_populates="user")


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
    """Terms of Service / Privacy Policy / club-authority acceptance for the
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
    contact_email = Column(Text, nullable=True)
    player_name_format = Column(Text, default="last_first", nullable=True)
    # BetterSelect: a player is "dormant" (hidden from default selection) if they
    # haven't appeared within this many months. Also bounds team squad
    # suggestions. Default 24 (migration 048).
    dormancy_months = Column(Integer, nullable=False, server_default="24", default=24)
    default_team_size = Column(Integer, nullable=False, server_default="11", default=11)  # 0 = no limit
    # Public player-profile attribute visibility (per-club). Overseas is always
    # shown; these gate the descriptive attributes on the public /players/:id
    # profile so each club chooses how much of a player's profile is public
    # (migration 054). Default off — opt-in.
    public_show_role = Column(Boolean, nullable=False, server_default="false", default=False)
    public_show_batting = Column(Boolean, nullable=False, server_default="false", default=False)
    public_show_bowling = Column(Boolean, nullable=False, server_default="false", default=False)
    public_show_opening = Column(Boolean, nullable=False, server_default="false", default=False)
    public_show_gender = Column(Boolean, nullable=False, server_default="false", default=False)
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
    memberships = relationship("ClubMembership", back_populates="club")
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
    # Whether this grade is shared on the club's public site (migration 123).
    # Defaults true so nothing is hidden until a club explicitly opts a grade
    # (e.g. their whole junior programme) out of public grade surfaces.
    is_public = Column(Boolean, nullable=False, server_default="true", default=True)

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
    photo_url = Column(Text, nullable=True)
    photo_data = Column(LargeBinary, nullable=True)
    photo_mime = Column(Text, nullable=True)
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
    result = Column(Text)
    winning_team = Column(Text)
    is_final = Column(Boolean, default=False, nullable=False, server_default='false')
    raw_payload = Column(JSON)
    venue = Column(Text)
    match_format = Column(Text, nullable=True)

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


class NetSession(Base):
    """BetterSelect → Net Manager: one net/practice session.

    A net session is a training day, keyed on a date + optional label (e.g.
    "Tuesday senior nets"). Attendance rows hang off it (who turned up, who
    batted) and feed the attendance reports + per-player profile stat. The live
    batting-queue + timer that the net manager runs pitch-side is purely
    client-side (single device); only the durable bits — the session, its timer
    settings and the attendance list — are persisted here. Club-wide; created_by
    tracks which admin opened it.
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
    position = Column(Integer, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    session = relationship("NetSession", back_populates="attendees")
    player = relationship("Player")


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"))
    catches = Column(Integer, default=0)
    catches_wk = Column(Integer, default=0)
    run_outs = Column(Integer, default=0)
    stumpings = Column(Integer, default=0)

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
    fours = Column(Integer, server_default="0", nullable=False)
    sixes = Column(Integer, server_default="0", nullable=False)
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
    maidens = Column(Integer, server_default="0", nullable=False)
    runs = Column(Integer, server_default="0", nullable=False)
    wickets = Column(Integer, server_default="0", nullable=False)
    wides = Column(Integer, server_default="0", nullable=False)
    no_balls = Column(Integer, server_default="0", nullable=False)
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
    status = Column(Text, nullable=False, server_default="running")
    started_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    stats = Column(JSON, nullable=False, default=dict)
    error = Column(Text, nullable=True)


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
    player_id = Column(UUID(as_uuid=True), ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    relationship_label = Column("relationship", Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    family = relationship("Family", back_populates="members")
    player = relationship("Player")


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
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    player = relationship("Player")
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
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

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
    """A payment reconciled against a bank statement. Defined now so Phase 2
    (payments + financial status) is purely additive; no endpoints write here
    yet."""
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
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    member_season = relationship("FeeMemberSeason", back_populates="payments")


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


class MerchAsset(Base):
    """An individual high-value piece of equipment (bowling machine, covers,
    sight screen) tracked as one item with its own condition and service/replace
    dates for cashflow planning. Quantity is implicitly 1; not stock-counted."""
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
    # First-party visitor id (localStorage UUID) sent by the Contact form, so an
    # enquiry can be tied back to the anonymous browsing journey on the Usage page.
    visitor_id = Column(Text, nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)


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
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organisation_id = Column(UUID(as_uuid=True), ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    html = Column(Text, nullable=False, server_default="")
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
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    club = relationship("MarketingClub", back_populates="contacts")


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
