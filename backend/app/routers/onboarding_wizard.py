"""Club Setup Wizard — the whole-platform, step-by-step onboarding flow at
/admin/setup (grew out of the Phase 15 checklist modal, which it replaces —
see docs/self-serve-trial-onboarding-plan.md).

The wizard is a guided walk over EXISTING admin tools, grouped by module.
Simple actions (branding, fixture sync, squad seeding, the self-serve
availability link, comms sender settings, fantasy season/pool) run inline on
the wizard page through their existing endpoints; genuinely complex tools
(player/grade merging, imports, the fee schedule, the website builder) are
link-out steps the wizard tracks completion for.

Completion is a blend of two signals, resolved in ``GET /flow``:
- **auto-detection** — cheap org-scoped EXISTS queries against the state each
  step actually produces (a logo on the org, sponsor rows, merge_logs rows, a
  successful full sync, a fee schedule, a fantasy season…). Whenever a step
  auto-detects as done it is persisted into ``completed_steps``, so progress
  accumulates server-side and the cheap ``/state`` summary (polled by
  AdminLayout on every admin page mount) never has to re-run the detectors.
- **manual marks** — every step can also be ticked done (or explicitly
  skipped) by the admin; steps whose effect we can't see in the DB
  (e.g. the Socials palette, which lives in localStorage) are manual-only.

Always available (the old ``onboarding_wizard_enabled`` flag gate was
dropped when the wizard became a permanent menu item — it only orchestrates
existing tools, so there's nothing risky to gate). Ordinary club-admin auth;
no special capability is required to VIEW the wizard — onboarding guidance
isn't privileged — but each inline action goes through its own existing
endpoint, which enforces its own capability. Auto-open stays conservative
(see get_state) so long-established clubs are never yanked into it.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.auth.modules import org_entitled_modules
from app.models.db import (
    ClubMembership,
    FantasyPoolPlayer,
    FantasySeason,
    FeeSchedule,
    FeeXeroConnection,
    Fixture,
    ManualPartnershipRecord,
    MerchProduct,
    MerchSquareConnection,
    OnboardingWizardState,
    OppositionDossier,
    Organisation,
    Player,
    Sponsor,
    SyncRun,
    Team,
    get_db,
)
from app.routers.auth import get_current_club

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/club-admin/onboarding-wizard", tags=["onboarding-wizard"])


# ─── Step registry ────────────────────────────────────────────────────────────
# Groups render in this order. A step's ``modules`` is the set of entitlement
# keys that make it relevant (shown if the club holds ANY of them); None means
# always shown (Core). ``kind`` is 'inline' (the wizard page hosts the action)
# or 'link' (the step deep-links to the existing admin tool). ``vital`` steps
# get a warning dialog before they can be skipped. ``auto`` names the
# detection this router runs (see _detect_steps); steps without one are
# manual-mark only. Copy here is what the admin reads — keep it plain.

GROUPS = [
    {
        "key": "data", "title": "Get your data in",
        "blurb": "Pull your club's full playing history across, then put your club's own stamp on it.",
        "steps": [
            {
                "key": "full_rebuild", "title": "Run your first full sync",
                "kind": "inline", "vital": True, "modules": None,
                "blurb": (
                    "This pulls every season, game and player from PlayHQ into "
                    "BetterCricket. It can take an hour or more for a club with a "
                    "long history — you can leave the page and come back. Most of "
                    "the later steps rely on this data, so run it first."
                ),
            },
            {
                "key": "branding", "title": "Logo, colours and player names",
                "kind": "inline", "vital": False, "modules": None,
                "blurb": (
                    "Upload your club logo, pick your primary and secondary "
                    "colours, and choose how player names read across the site "
                    "(for example Smith, John or John Smith)."
                ),
            },
            {
                "key": "invite_admin", "title": "Invite another admin",
                "kind": "link", "route": "/admin/users", "vital": False, "modules": None,
                "blurb": (
                    "Add a second committee member so the club isn't relying on "
                    "one login. Invited admins get an email to set their own "
                    "password."
                ),
            },
            {
                "key": "sponsors", "title": "Add your sponsors",
                "kind": "inline", "vital": False, "modules": None,
                "blurb": (
                    "Sponsors appear on your public pages. Add each one's name, "
                    "website and logo — you can reorder them later from the "
                    "Sponsors page."
                ),
            },
        ],
    },
    {
        "key": "tools", "title": "Tidy your data", "requires_sync": True,
        "blurb": (
            "PlayHQ history often carries duplicates — the same player under two "
            "spellings, the same grade under different names. These tools fix "
            "that, and they need your first full sync to finish before they can "
            "see anything."
        ),
        "steps": [
            {
                "key": "merge_players", "title": "Merge duplicate players",
                "kind": "link", "route": "/admin/merge", "vital": True, "modules": None,
                "blurb": (
                    "The same person often exists twice in PlayHQ history (name "
                    "changes, junior and senior records, typos). Merging combines "
                    "their stats into one career. The tool suggests likely "
                    "duplicates — most clubs find a handful. This one really is "
                    "worth doing: unmerged players show wrong career totals."
                ),
            },
            {
                "key": "merge_grades", "title": "Merge duplicate grades",
                "kind": "link", "route": "/admin/grades", "vital": True, "modules": None,
                "blurb": (
                    "Competitions rename grades over the years (\"2nd Grade\" vs "
                    "\"2s\" vs \"B Grade\"). Merging them keeps season-by-season "
                    "records comparable. The grades page suggests likely matches."
                ),
            },
            {
                "key": "player_details", "title": "Import player details",
                "kind": "link", "route": "/admin/players/import", "vital": False, "modules": None,
                "blurb": (
                    "Bulk-fill emails, phone numbers, roles and batting/bowling "
                    "styles from a spreadsheet. Download the template, fill in "
                    "what you have, and upload — blanks never overwrite anything."
                ),
            },
            {
                "key": "import_stats", "title": "Import historical stats",
                "kind": "link", "route": "/admin/import", "vital": False, "modules": None,
                "blurb": (
                    "If your club has records from before PlayHQ (old scorebooks, "
                    "a previous website), import them here so careers read "
                    "complete. Skip this if PlayHQ already covers your history."
                ),
            },
            {
                "key": "import_honours", "title": "Upload awards and honours",
                "kind": "link", "route": "/admin/awards", "vital": False, "modules": None,
                "blurb": (
                    "Club champions, fairest and best, premierships, life members. "
                    "Add them one by one or import a spreadsheet — they power the "
                    "honour boards and player profiles."
                ),
            },
            {
                "key": "partnerships", "title": "Upload partnership records",
                "kind": "link", "route": "/admin/partnerships", "vital": False, "modules": None,
                "blurb": (
                    "Record partnership records (highest stands per wicket) that "
                    "pre-date the synced scorecards, so the record boards show "
                    "your club's real history."
                ),
            },
        ],
    },
    {
        "key": "select", "title": "BetterSelect",
        "blurb": "Team selection, availability and training — get match day organised.",
        "steps": [
            {
                "key": "fixtures", "title": "Sync your fixtures",
                "kind": "inline", "vital": False, "modules": {"select"},
                "blurb": (
                    "Pull your upcoming fixtures from PlayHQ. If your association "
                    "hasn't published fixtures yet, nothing will come through — "
                    "that's normal, just re-run this once they're up."
                ),
            },
            {
                "key": "squads", "title": "Set up your squads",
                "kind": "inline", "vital": False, "modules": {"select"},
                "blurb": (
                    "Squads mirror the sides you actually field (1st XI, 2nd XI and "
                    "so on). We suggest them from the teams your players appeared "
                    "for last season — tick the ones you want."
                ),
            },
            {
                "key": "assign_players", "title": "Assign players to squads",
                "kind": "inline", "vital": False, "modules": {"select"},
                "blurb": (
                    "Put each player in the squad they mostly play for, based on "
                    "where they actually played. You can drag players between "
                    "squads any time on the Squads board."
                ),
            },
            {
                "key": "self_serve", "title": "Turn on the availability link",
                "kind": "inline", "vital": False, "modules": {"select"},
                "blurb": (
                    "One link (or QR code) your players use to set their own "
                    "availability — no accounts, no app, just their name and the "
                    "last four digits of their phone number."
                ),
            },
            {
                "key": "nets", "title": "Set up Net Manager",
                "kind": "link", "route": "/admin/betterselect/nets", "vital": False, "modules": {"select"},
                "blurb": (
                    "Timed batting rotations and attendance for training nights. "
                    "Open it, set your net count and timings, and it's ready for "
                    "your first session."
                ),
            },
        ],
    },
    {
        "key": "socials", "title": "BetterSocials",
        "blurb": "Your public face — the club website and match-day social graphics.",
        "steps": [
            {
                "key": "website", "title": "Turn on your club website",
                "kind": "inline", "vital": False, "modules": {"socials"},
                "blurb": (
                    "A full public club site — news, honour boards, committee, "
                    "photo galleries — at your club's own page. Switch it on and "
                    "add a tagline here; add content whenever you're ready."
                ),
            },
            {
                "key": "socials_palette", "title": "Set your socials colours",
                "kind": "link", "route": "/admin/social-post", "vital": False, "modules": {"socials"},
                "blurb": (
                    "The post generator ships with ready-made palettes. Open it, "
                    "pick or build the one that matches your club colours, and "
                    "every match-day graphic comes out on-brand. Mark this done "
                    "once you've saved a palette you like."
                ),
            },
        ],
    },
    {
        "key": "admin", "title": "BetterAdmin",
        "blurb": "Fees, emails and the kit room — the club's paperwork, minus the paper.",
        "steps": [
            {
                "key": "square", "title": "Connect Square",
                "kind": "link", "route": "/admin/fees/square", "vital": False,
                "modules": {"fees", "merch"},
                "blurb": (
                    "If the club takes payments through Square, connect it once "
                    "and BetterCricket can match fee payments and mirror your "
                    "canteen stock. Skip this if you don't use Square."
                ),
            },
            {
                "key": "xero", "title": "Connect Xero",
                "kind": "link", "route": "/admin/fees/xero", "vital": False, "modules": {"fees"},
                "blurb": (
                    "If the club's books live in Xero, connect it to reconcile "
                    "fee payments against your bank feed. Skip this if you don't "
                    "use Xero."
                ),
            },
            {
                "key": "fee_schedule", "title": "Set your fee schedule",
                "kind": "link", "route": "/admin/fees/schedule", "vital": False, "modules": {"fees"},
                "blurb": (
                    "Your membership categories and match fees for the season — "
                    "seniors, juniors, family caps, per-game rates. There's a "
                    "starter set you can adjust rather than starting blank."
                ),
            },
            {
                "key": "rollover", "title": "Roll members over from last season",
                "kind": "link", "route": "/admin/fees", "vital": False, "modules": {"fees"},
                "blurb": (
                    "Carry last season's members into the new season in one go, "
                    "keeping their fee categories. Only relevant from your second "
                    "season on BetterCricket — skip it in year one."
                ),
            },
            {
                "key": "comms", "title": "Set your email sender details",
                "kind": "inline", "vital": False, "modules": {"comms"},
                "blurb": (
                    "The reply-to address members answer to, and the footer line "
                    "(club name, ABN or contact) that goes on every email the "
                    "club sends."
                ),
            },
            {
                "key": "merch_stock", "title": "Add your stock and equipment",
                "kind": "link", "route": "/admin/merch/stock", "vital": False, "modules": {"merch"},
                "blurb": (
                    "Playing kit, balls, canteen stock, training gear. Add items "
                    "by hand, or if you sell through Square, import your whole "
                    "catalogue from the Square page in one click."
                ),
            },
        ],
    },
    {
        "key": "iq", "title": "BetterIQ",
        "blurb": "Analytics needs no setup — but you can warm up the opposition scouting before round one.",
        "steps": [
            {
                "key": "iq_prewarm", "title": "Pre-build opposition analysis",
                "kind": "inline", "vital": False, "modules": {"iq"},
                "blurb": (
                    "Opposition dossiers normally build the first time you open "
                    "one (up to a minute each). Pick your top grades and we'll "
                    "build every known opponent's dossier now, so scouting feels "
                    "instant when you need it."
                ),
            },
        ],
    },
    {
        "key": "fantasy", "title": "BetterFantasy",
        "blurb": "A fantasy competition over your club's real games — set up the season once, then it runs itself.",
        "steps": [
            {
                "key": "fantasy_season", "title": "Create this season's competition",
                "kind": "inline", "vital": False, "modules": {"fantasy"},
                "blurb": (
                    "Creates the fantasy season, the club-wide ladder and your "
                    "public sign-up link in one go."
                ),
            },
            {
                "key": "fantasy_pool", "title": "Build the player pool",
                "kind": "inline", "vital": False, "modules": {"fantasy"},
                "blurb": (
                    "Prices every eligible player from their real stats so "
                    "managers can pick their squads. Re-run it any time — prices "
                    "only reset if you ask."
                ),
            },
            {
                "key": "fantasy_rules", "title": "Review team rules and budget",
                "kind": "link", "route": "/admin/fantasy/settings", "vital": False, "modules": {"fantasy"},
                "blurb": (
                    "Salary cap, squad size and trade limits start on sensible "
                    "defaults — look them over and tweak anything that doesn't "
                    "suit your club."
                ),
            },
            {
                "key": "fantasy_scoring", "title": "Review scoring",
                "kind": "link", "route": "/admin/fantasy/scoring", "vital": False, "modules": {"fantasy"},
                "blurb": (
                    "Points per run, wicket, catch and the rest. The defaults are "
                    "balanced for club cricket — mark this done once you're happy "
                    "with them."
                ),
            },
        ],
    },
]

async def _get_or_create_state(db: AsyncSession, org_id) -> OnboardingWizardState:
    state = await db.get(OnboardingWizardState, org_id)
    if state is None:
        state = OnboardingWizardState(organisation_id=org_id, completed_steps=[], skipped_steps=[])
        db.add(state)
        await db.flush()
    return state


async def _sync_ready(db: AsyncSession, org_id) -> bool:
    """The club's first full historical pull has completed successfully —
    either an ordinary full sync (kind='org_full': Sync Now / the self-serve
    registration kickoff) or a Full Rebuild (kind='org_hard_refresh'). The
    old checklist only accepted org_full, which meant a club whose first
    complete pull was a Full Rebuild never unlocked the data-tools steps."""
    row = await db.execute(
        select(func.count()).select_from(SyncRun).where(
            SyncRun.org_id == org_id,
            SyncRun.kind.in_(("org_full", "org_hard_refresh")),
            SyncRun.status == "success",
        )
    )
    return (row.scalar_one() or 0) > 0


async def _exists(db: AsyncSession, stmt) -> bool:
    return (await db.execute(stmt.limit(1))).first() is not None


async def _detect_steps(db: AsyncSession, club: Organisation, sync_ready: bool) -> dict:
    """Auto-detection: step key → done, from the state each step produces.

    Every check is a cheap org-scoped EXISTS (or a column already on the org
    row). Steps that leave no server-visible trace (socials palette, the
    review-only steps) simply aren't here — they're manual-mark only."""
    org_id = club.id
    detected = {
        "full_rebuild": sync_ready,
        "branding": bool(club.logo_url),
        "self_serve": bool(club.availability_self_service_enabled),
        "website": bool(club.website_enabled),
        "comms": bool(club.comms_reply_to or club.comms_sender_footer),
        "nets": bool(club.net_settings),
    }
    detected["invite_admin"] = (await db.execute(
        select(func.count()).select_from(ClubMembership).where(ClubMembership.club_id == org_id)
    )).scalar_one() > 1
    detected["sponsors"] = await _exists(db, select(Sponsor.id).where(Sponsor.organisation_id == org_id))
    # merge_logs / grade_merge_logs / player_achievements are raw (pre-ORM) tables.
    detected["merge_players"] = (await db.execute(
        text("SELECT 1 FROM merge_logs WHERE org_id = :org AND undone_at IS NULL LIMIT 1"),
        {"org": str(org_id)},
    )).first() is not None
    detected["merge_grades"] = (await db.execute(
        text("SELECT 1 FROM grade_merge_logs WHERE org_id = :org AND undone_at IS NULL LIMIT 1"),
        {"org": str(org_id)},
    )).first() is not None
    detected["import_honours"] = (await db.execute(
        text("SELECT 1 FROM player_achievements WHERE org_id = :org LIMIT 1"),
        {"org": str(org_id)},
    )).first() is not None
    detected["partnerships"] = await _exists(
        db, select(ManualPartnershipRecord.id).where(ManualPartnershipRecord.org_id == org_id))
    detected["fixtures"] = await _exists(db, select(Fixture.id).where(Fixture.organisation_id == org_id))
    detected["squads"] = await _exists(db, select(Team.id).where(Team.organisation_id == org_id))
    detected["assign_players"] = await _exists(
        db, select(Player.id).where(Player.organisation_id == org_id, Player.squad_team_id.isnot(None)))
    detected["square"] = await _exists(
        db, select(MerchSquareConnection.id).where(MerchSquareConnection.organisation_id == org_id))
    detected["xero"] = await _exists(
        db, select(FeeXeroConnection.id).where(FeeXeroConnection.organisation_id == org_id))
    detected["fee_schedule"] = await _exists(
        db, select(FeeSchedule.id).where(FeeSchedule.organisation_id == org_id))
    detected["merch_stock"] = await _exists(
        db, select(MerchProduct.id).where(MerchProduct.organisation_id == org_id))
    detected["iq_prewarm"] = await _exists(
        db, select(OppositionDossier.id).where(
            OppositionDossier.organisation_id == org_id, OppositionDossier.status == "ready"))
    detected["fantasy_season"] = await _exists(
        db, select(FantasySeason.id).where(FantasySeason.organisation_id == org_id))
    detected["fantasy_pool"] = await _exists(
        db, select(FantasyPoolPlayer.id).where(FantasyPoolPlayer.organisation_id == org_id))
    return detected


def _applicable_groups(entitled: set) -> list:
    """The registry filtered to this club's entitlements (structure only)."""
    out = []
    for g in GROUPS:
        steps = [s for s in g["steps"] if s["modules"] is None or entitled & s["modules"]]
        if steps:
            out.append({**g, "steps": steps})
    return out


class StepUpdate(BaseModel):
    done: bool | None = None
    skipped: bool | None = None


@router.get("/flow")
async def get_flow(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """The full wizard: groups, steps, completion and progress.

    Runs the auto-detectors and PERSISTS any newly-detected completion into
    completed_steps, so the lightweight /state summary (and the progress a
    second admin sees) stays consistent without re-running detection."""
    state = await _get_or_create_state(db, club.id)
    sync_ready = await _sync_ready(db, club.id)
    detected = await _detect_steps(db, club, sync_ready)

    completed = set(state.completed_steps or [])
    skipped = set(state.skipped_steps or [])
    newly = {k for k, v in detected.items() if v} - completed
    if newly:
        completed |= newly
        skipped -= newly  # doing the thing beats having skipped it
        state.completed_steps = sorted(completed)
        state.skipped_steps = sorted(skipped)
        flag_modified(state, "completed_steps")
        flag_modified(state, "skipped_steps")
    await db.commit()

    entitled = org_entitled_modules(club)
    groups, done_n, addressed_n, total_n = [], 0, 0, 0
    for g in _applicable_groups(entitled):
        locked = bool(g.get("requires_sync")) and not sync_ready
        steps = []
        for s in g["steps"]:
            done = s["key"] in completed
            skip = (not done) and s["key"] in skipped
            total_n += 1
            done_n += 1 if done else 0
            addressed_n += 1 if (done or skip) else 0
            steps.append({
                "key": s["key"], "title": s["title"], "blurb": s["blurb"],
                "kind": s["kind"], "route": s.get("route"), "vital": s["vital"],
                "done": done, "skipped": skip, "auto": s["key"] in detected,
            })
        groups.append({
            "key": g["key"], "title": g["title"], "blurb": g["blurb"],
            "locked": locked, "steps": steps,
        })

    return {
        "club": {"name": club.name, "logo_url": club.logo_url, "slug": club.slug},
        "sync_ready": sync_ready,
        "groups": groups,
        "progress": {"done": done_n, "addressed": addressed_n, "total": total_n},
        "dismissed": state.dismissed_at is not None,
    }


@router.get("/state")
async def get_state(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Lightweight summary for AdminLayout (polled on every admin page mount):
    is the wizard available, and should it auto-open after this login? Reads
    only STORED progress — /flow is where detection runs and persists."""
    state = await _get_or_create_state(db, club.id)
    await db.commit()
    sync_ready = await _sync_ready(db, club.id)
    entitled = org_entitled_modules(club)
    completed = set(state.completed_steps or [])
    skipped = set(state.skipped_steps or [])
    keys = [s["key"] for g in _applicable_groups(entitled) for s in g["steps"]]
    done_n = sum(1 for k in keys if k in completed)
    addressed = sum(1 for k in keys if k in completed or k in skipped)
    all_addressed = bool(keys) and addressed == len(keys)
    # Auto-open (a navigation to /admin/setup on fresh login) is deliberately
    # conservative now that the wizard is always available: (a) a BRAND-NEW
    # club — no successful full sync yet — that hasn't dismissed the wizard;
    # or (b) Decision 11's reopen-once-when-sync-completes, but only for a
    # club that actually engaged with the wizard before its sync finished
    # (stored progress exists). Without (b)'s engagement guard, dropping the
    # old flag gate would auto-navigate every long-established club's admin
    # into setup on their next login. The Setup Wizard menu item is the
    # any-time entry point; auto-open is only for genuine onboarding.
    engaged = bool(completed or skipped)
    should_auto_open = (not all_addressed) and (
        (not sync_ready and state.dismissed_at is None)
        or (sync_ready and state.sync_steps_shown_at is None and engaged)
    )
    return {
        "done": done_n, "total": len(keys), "all_done": all_addressed,
        "sync_ready": sync_ready,
        "should_auto_open": bool(should_auto_open),
        "dismissed": state.dismissed_at is not None,
    }


@router.post("/opened")
async def mark_opened(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    """Call the moment the wizard page opens (auto- or manually-navigated).
    Stamps ``sync_steps_shown_at`` the first time this happens while the
    sync-dependent steps are available — the one-time trigger that stops the
    auto-reopen from firing more than once per sync completion."""
    state = await _get_or_create_state(db, club.id)
    if await _sync_ready(db, club.id) and state.sync_steps_shown_at is None:
        state.sync_steps_shown_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.post("/dismiss")
async def dismiss(club: Organisation = Depends(get_current_club), db: AsyncSession = Depends(get_db)):
    state = await _get_or_create_state(db, club.id)
    state.dismissed_at = datetime.now(timezone.utc)
    await db.commit()
    return {"ok": True}


@router.post("/steps/{step_key}")
async def set_step(step_key: str, data: StepUpdate, club: Organisation = Depends(get_current_club),
                   db: AsyncSession = Depends(get_db)):
    """Mark a step done / not done, or skipped / unskipped. Done and skipped
    are mutually exclusive — setting one clears the other. Unknown keys are
    accepted (old checklist keys like explore_select may still be stored) but
    only registry keys affect progress."""
    state = await _get_or_create_state(db, club.id)
    completed = set(state.completed_steps or [])
    skipped = set(state.skipped_steps or [])
    if data.done is not None:
        if data.done:
            completed.add(step_key)
            skipped.discard(step_key)
        else:
            completed.discard(step_key)
    if data.skipped is not None:
        if data.skipped:
            skipped.add(step_key)
            completed.discard(step_key)
        else:
            skipped.discard(step_key)
    state.completed_steps = sorted(completed)
    state.skipped_steps = sorted(skipped)
    flag_modified(state, "completed_steps")
    flag_modified(state, "skipped_steps")
    await db.commit()
    return {"ok": True, "completed_steps": state.completed_steps, "skipped_steps": state.skipped_steps}
