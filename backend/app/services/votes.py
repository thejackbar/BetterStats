"""BetterSelect — vote collection: eligibility, voting state and counting.

The Brownlow-style engine behind /votes (admin) and /public/votes (player
link). Everything here is DERIVED ON READ from raw ballots + the club's
current VoteSettings — no stored weekly results, no stored season points — so
changing the ballot shape, counting method or tie policy mid-season restates
the whole season consistently (same philosophy as BetterFees' derived
match-day allocation).

Eligibility is the SYNCED SCORECARD, per direct instruction: a fixture is
votable only once its game has landed in `games`, and the votable/voter list
is who actually played — the union of game_appearances + per-innings stat
rows, org-scoped through players.organisation_id (never trust a shared
game's rows without that scope, see the cross-club leak notes in CLAUDE.md).

``Fixture.id`` is NOT the real upstream match GUID for a synced fixture —
``routers/fixtures.py::sync_fixtures`` mints a random ``uuid4()`` for the row
and stores the actual Grassroots match id in ``Fixture.playhq_id`` instead
(so two clubs playing each other keep separate fixture rows even though they
share one ``games.id``). ``games.id`` and a live Grassroots lookup are both
keyed on that real match id, so anything here that cross-references either
one must go through ``match_ref_id()``, never bare ``fixture.id``.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Fixture, VoteBallot, VoteFixtureOverride, VoteMedal, VoteNudge

logger = logging.getLogger(__name__)

DEFAULT_BALLOT = [3, 2, 1]
VOTER_MODES = {"players", "captain"}
COUNTING_METHODS = {"rank", "tally"}
TIE_POLICIES = {"share", "countback"}
MAX_POSITIONS = 10

# Where the votable list comes from. 'scorecard' is the truth of who played but
# only exists after the weekly sync; the other two are available on the night.
ELIGIBILITY_SOURCES = ("scorecard", "lineup", "playhq")
SOURCE_LABELS = {
    "scorecard": "Match scorecard",
    "lineup": "BetterSelect XI",
    "playhq": "Play.Cricket team list",
}


# ─── Medals ──────────────────────────────────────────────────────────────────
# A club counts votes towards one medal or several ("Club Champion", "Colts
# Medal"), each with its own ballot shape, voter mode, counting method and
# public link. Before migration 265 a club had exactly one implicit medal, held
# as the singleton `vote_settings` row; that row is now its first VoteMedal and
# nothing reads vote_settings.

DEFAULT_MEDAL_NAME = "Club Champion"
MAX_MEDAL_NAME = 80


async def list_medals(db: AsyncSession, org_id) -> list[VoteMedal]:
    """The club's medals in its own order. The club's first medal is the one
    every unscoped read (a bare leaderboard link, an old bookmark) falls back
    to, so ordering is load-bearing, not just presentation."""
    res = await db.execute(
        select(VoteMedal)
        .where(VoteMedal.organisation_id == org_id)
        .order_by(VoteMedal.position, VoteMedal.created_at)
    )
    return list(res.scalars().all())


async def get_medal(db: AsyncSession, org_id, medal_id) -> Optional[VoteMedal]:
    """One medal, scoped to the club — a medal id arriving from a browser must
    never resolve against another club's row."""
    if not medal_id:
        return None
    try:
        mid = uuid.UUID(str(medal_id))
    except (TypeError, ValueError):
        return None
    res = await db.execute(
        select(VoteMedal).where(VoteMedal.id == mid, VoteMedal.organisation_id == org_id)
    )
    return res.scalar_one_or_none()


async def medal_by_token(db: AsyncSession, token: str) -> Optional[VoteMedal]:
    """The medal a public voting link opens. The token is the medal's own, and
    a club's pre-265 club-wide token was carried onto its first medal, so a
    link already shared with players still lands somewhere real."""
    if not token:
        return None
    res = await db.execute(select(VoteMedal).where(VoteMedal.link_token == token))
    return res.scalar_one_or_none()


async def resolve_medal(db: AsyncSession, org_id, medal_id=None) -> Optional[VoteMedal]:
    """The medal a request means: the one it named, else the club's first.

    Falling back rather than 404-ing is what keeps every pre-medals caller —
    a saved link to /admin/betterselect/votes, the awards-night URL — landing
    on the club's original count instead of an error.
    """
    if medal_id:
        return await get_medal(db, org_id, medal_id)
    medals = await list_medals(db, org_id)
    return medals[0] if medals else None


async def ensure_default_medal(db: AsyncSession, org_id) -> VoteMedal:
    """The club's first medal, created on demand.

    A club that has never voted has no row at all — migration 265 only
    backfilled clubs that already had settings or ballots. Rather than make
    every screen cope with "no medal", the first write (turning voting on,
    entering a paper ballot) mints one. Does not commit; the caller's own
    transaction owns it.
    """
    medals = await list_medals(db, org_id)
    if medals:
        return medals[0]
    medal = VoteMedal(organisation_id=org_id, name=DEFAULT_MEDAL_NAME, position=0)
    db.add(medal)
    await db.flush()
    return medal


def clean_medal_name(raw) -> str:
    name = (raw or "").strip()
    return name[:MAX_MEDAL_NAME] or DEFAULT_MEDAL_NAME


def clean_grade_ids(raw) -> list[str]:
    """The grades a medal counts, as a de-duplicated list of uuid strings.

    An EMPTY list means every grade — that is what a club's only medal means
    before anyone has thought about grades. Junk is dropped rather than stored,
    since a value that is not a uuid can never match a fixture's grade and
    would silently narrow the medal to nothing.
    """
    out: list[str] = []
    seen: set[str] = set()
    for g in (raw or []):
        try:
            gid = str(uuid.UUID(str(g)))
        except (TypeError, ValueError):
            continue
        if gid not in seen:
            seen.add(gid)
            out.append(gid)
    return out


async def medal_grade_ids(db: AsyncSession, org_id, medal: Optional[VoteMedal]) -> Optional[set[str]]:
    """Every grade id this medal counts, or None meaning "all of them".

    A medal is configured by ticking concrete grades, but ``grades`` rows are
    PER SEASON — next season's "Colts" is a different id from this season's. A
    medal that matched on the stored ids alone would therefore stop counting
    the day the new season's grades are created, silently, mid-season-rollover.

    So the stored ids are expanded through their NAMES to every grade of that
    name in the club. That is what makes a medal a standing award rather than a
    one-season one, and it is why the picker offers each grade name once rather
    than once per season.

    A stored id that no longer resolves (its grade was deleted) contributes
    nothing, leaving the medal counting only its remaining grades — never
    silently widening back to everything.
    """
    picked = clean_grade_ids(medal.grade_ids if medal else None)
    if not medal or not picked:
        return None
    res = await db.execute(
        text(
            """
            SELECT sibling.id
            FROM grades picked
            JOIN seasons ps ON ps.id = picked.season_id AND ps.organisation_id = :org
            JOIN grades sibling ON sibling.name = picked.name
            JOIN seasons ss ON ss.id = sibling.season_id AND ss.organisation_id = :org
            WHERE picked.id = ANY(:ids)
            """
        ),
        {"ids": [uuid.UUID(g) for g in picked], "org": org_id},
    )
    return {str(r[0]) for r in res.fetchall()}


def medal_covers(allowed: Optional[set[str]], grade_id) -> bool:
    """Does this medal count a fixture in this grade? ``allowed`` is what
    ``medal_grade_ids`` returned — None means every grade.

    A fixture whose grade can't be resolved at all (``effective_grade_ids``
    found neither a fixture grade nor a synced game) is counted only by an
    all-grades medal: a row we cannot place must not be swept into a
    grade-restricted count.
    """
    if allowed is None:
        return True
    return bool(grade_id) and str(grade_id) in allowed


async def club_grade_options(db: AsyncSession, org_id) -> list[dict]:
    """The grades a medal can be scoped to: each distinct grade NAME once,
    carrying its most recent season's id as the value to store. Offering the
    same name once per season would make the picker unusable for a club with a
    decade of history, and every one of those rows would mean the same thing."""
    res = await db.execute(
        text(
            """
            SELECT DISTINCT ON (gr.name) gr.name, gr.id
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = :org
            ORDER BY gr.name, s.year DESC NULLS LAST
            """
        ),
        {"org": org_id},
    )
    return [{"id": str(gid), "name": name} for name, gid in res.fetchall()]


async def medal_grade_names(db: AsyncSession, org_id, medals: list[VoteMedal]) -> dict[str, list[str]]:
    """medal id → the grade NAMES it counts, so a screen can show and re-tick a
    medal's selection even when the stored id belongs to an older season's
    grade row than the one the picker offers."""
    ids: set[str] = set()
    for m in medals:
        ids.update(clean_grade_ids(m.grade_ids))
    if not ids:
        return {}
    res = await db.execute(
        text(
            "SELECT gr.id, gr.name FROM grades gr "
            "JOIN seasons s ON s.id = gr.season_id AND s.organisation_id = :org "
            "WHERE gr.id = ANY(:ids)"
        ),
        {"org": org_id, "ids": [uuid.UUID(g) for g in ids]},
    )
    name_by_id = {str(gid): name for gid, name in res.fetchall()}
    out: dict[str, list[str]] = {}
    for m in medals:
        seen, names = set(), []
        for gid in clean_grade_ids(m.grade_ids):
            nm = name_by_id.get(gid)
            if nm and nm not in seen:
                seen.add(nm)
                names.append(nm)
        out[str(m.id)] = names
    return out


def clean_ballot_values(raw) -> list[int]:
    """Sanitise a configured ballot: positive ints, best-first (non-increasing),
    at most MAX_POSITIONS. Falls back to 3-2-1 when nothing usable remains."""
    vals: list[int] = []
    for v in (raw or []):
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n > 0:
            vals.append(n)
    vals = sorted(vals, reverse=True)[:MAX_POSITIONS]
    return vals or list(DEFAULT_BALLOT)


def effective_config(s: Optional[VoteMedal]) -> dict:
    """One medal's voting config with defaults applied — usable whether or not
    the medal exists yet, so a club that has never voted still renders."""
    return {
        "medal_id": str(s.id) if s else None,
        "medal_name": (s.name if s and s.name else DEFAULT_MEDAL_NAME),
        "grade_ids": clean_grade_ids(s.grade_ids if s else None),
        "enabled": bool(s.enabled) if s else False,
        "require_pin": bool(s.require_pin) if s else True,
        "voter_mode": (s.voter_mode if s and s.voter_mode in VOTER_MODES else "players"),
        "ballot_values": clean_ballot_values(s.ballot_values if s else None),
        "counting_method": (s.counting_method if s and s.counting_method in COUNTING_METHODS else "rank"),
        "tie_policy": (s.tie_policy if s and s.tie_policy in TIE_POLICIES else "share"),
        "allow_self_vote": bool(s.allow_self_vote) if s else False,
        "allow_non_participants": bool(s.allow_non_participants) if s else False,
        "auto_close_days": int(s.auto_close_days) if s and s.auto_close_days else 7,
        "eligibility_source": (
            s.eligibility_source
            if s and getattr(s, "eligibility_source", None) in ELIGIBILITY_SOURCES
            else "scorecard"
        ),
    }


# ─── Eligibility (who played) ────────────────────────────────────────────────

def match_ref_id(fixture: Fixture):
    """The real upstream match/game GUID for a fixture.

    A synced ('grassroots', and any future 'playhq') fixture keeps a random,
    resync-stable ``uuid4()`` as its own PK and stores the actual Grassroots
    match id in ``playhq_id`` (see ``routers/fixtures.py::sync_fixtures``) —
    that's what ``games.id`` and a live Grassroots lookup are keyed on, not
    the Fixture PK. A manual fixture has no upstream match at all, so its own
    id is used, which correctly never matches a real game.
    """
    if fixture.playhq_id:
        try:
            return uuid.UUID(fixture.playhq_id)
        except ValueError:
            return fixture.playhq_id
    return fixture.id


async def game_exists(db: AsyncSession, game_id) -> bool:
    """Has this game synced? ``game_id`` must be the real match GUID
    (``match_ref_id(fixture)``), not the Fixture PK."""
    res = await db.execute(text("SELECT 1 FROM games WHERE id = :gid LIMIT 1"), {"gid": game_id})
    return res.first() is not None


async def eligible_players(db: AsyncSession, org_id, game_id) -> list[dict]:
    """Who played in this game, from the synced scorecard: the union of
    appearances and every per-innings stat table, so a game whose sync predates
    game_appearances still resolves. Org-scoped through players so a shared
    game (both clubs synced) never leaks the opposition into our list."""
    res = await db.execute(
        text(
            """
            SELECT p.id, COALESCE(p.display_name_override, p.name) AS name,
                   BOOL_OR(src.is_captain) AS is_captain
            FROM (
                SELECT player_id, is_captain FROM game_appearances WHERE game_id = :gid
                UNION ALL SELECT player_id, false FROM batting_innings WHERE game_id = :gid
                UNION ALL SELECT player_id, false FROM bowling_spells WHERE game_id = :gid
                UNION ALL SELECT player_id, false FROM fielding_stats WHERE game_id = :gid
            ) src
            JOIN players p ON p.id = src.player_id
            WHERE p.organisation_id = :org
            GROUP BY p.id, COALESCE(p.display_name_override, p.name)
            ORDER BY 2
            """
        ),
        {"gid": game_id, "org": org_id},
    )
    players = [
        {"id": str(pid), "name": name, "is_captain": bool(cap)}
        for pid, name, cap in res.fetchall()
    ]
    if players and not any(p["is_captain"] for p in players):
        # Older synced games may lack the captain flag — fall back to the saved
        # BetterSelect lineup's captain for captain-only voting.
        lu = await db.execute(
            text(
                "SELECT player_id FROM fixture_lineups "
                "WHERE fixture_id = :fid AND is_captain = true"
            ),
            {"fid": game_id},
        )
        captain_ids = {str(r[0]) for r in lu.fetchall()}
        for p in players:
            if p["id"] in captain_ids:
                p["is_captain"] = True
    return players


async def lineup_players(db: AsyncSession, org_id, fixture_id) -> list[dict]:
    """The XI saved in BetterSelect selection for this fixture, in batting
    order. Org-scoped through players like every other votable list."""
    res = await db.execute(
        text(
            """
            SELECT p.id, COALESCE(p.display_name_override, p.name) AS name, fl.is_captain
            FROM fixture_lineups fl
            JOIN players p ON p.id = fl.player_id
            WHERE fl.fixture_id = :fid AND p.organisation_id = :org
            ORDER BY fl.batting_order NULLS LAST, 2
            """
        ),
        {"fid": fixture_id, "org": org_id},
    )
    return [
        {"id": str(pid), "name": name, "is_captain": bool(cap)}
        for pid, name, cap in res.fetchall()
    ]


async def eligible_from_source(db: AsyncSession, club, fixture, source: str) -> tuple[list[dict], list[str]]:
    """``(players, unmatched)`` for one source.

    ``unmatched`` only ever comes from the Play.Cricket team list — a published
    name we hold no player row for (a genuine fill-in, or a junior whose name CA
    redacts). It's surfaced rather than silently dropped so an admin can see why
    the votable list is short. Votes still can't be cast for them: a ballot pick
    is a real player FK.
    """
    if source == "lineup":
        # BetterSelect XIs are keyed on the Fixture's own PK, not the real
        # match id — that mapping is self-consistent regardless of playhq_id.
        return await lineup_players(db, club.id, fixture.id), []
    game_id = match_ref_id(fixture)
    if source == "playhq":
        from app.services.lineups import our_lineup_players
        try:
            return await our_lineup_players(db, club, str(game_id))
        except Exception:
            # A live upstream fetch must never take the vote page down.
            logger.warning("vote eligibility: Play.Cricket lineup fetch failed for %s", fixture.id)
            return [], []
    if await game_exists(db, game_id):
        return await eligible_players(db, club.id, game_id), []
    return [], []


async def scorecard_voter_counts(db: AsyncSession, org_id, game_ids: list) -> dict[str, int]:
    """Batch version of ``eligible_players``' count only — one query for a
    whole page of fixtures instead of one per row. Keyed on the game id
    (``match_ref_id(fixture)``, stringified)."""
    if not game_ids:
        return {}
    res = await db.execute(
        text(
            """
            SELECT src.gid, COUNT(DISTINCT p.id)
            FROM (
                SELECT game_id AS gid, player_id FROM game_appearances WHERE game_id = ANY(:ids)
                UNION ALL SELECT game_id, player_id FROM batting_innings WHERE game_id = ANY(:ids)
                UNION ALL SELECT game_id, player_id FROM bowling_spells WHERE game_id = ANY(:ids)
                UNION ALL SELECT game_id, player_id FROM fielding_stats WHERE game_id = ANY(:ids)
            ) src
            JOIN players p ON p.id = src.player_id AND p.organisation_id = :org
            GROUP BY src.gid
            """
        ),
        {"ids": game_ids, "org": org_id},
    )
    return {str(gid): n for gid, n in res.fetchall()}


async def lineup_voter_counts(db: AsyncSession, org_id, fixture_ids: list) -> dict[str, int]:
    """Batch version of ``lineup_players``' count only. Keyed on fixture id."""
    if not fixture_ids:
        return {}
    res = await db.execute(
        text(
            "SELECT fixture_id, COUNT(DISTINCT player_id) FROM fixture_lineups "
            "WHERE organisation_id = :org AND fixture_id = ANY(:ids) GROUP BY fixture_id"
        ),
        {"org": org_id, "ids": fixture_ids},
    )
    return {str(fid): n for fid, n in res.fetchall()}


async def player_ballot_counts(db: AsyncSession, org_id, fixture_ids: list, medal_id=None) -> dict[str, int]:
    """Distinct PLAYER voters per fixture (excludes non-player/supporter
    ballots) — the denominator side of "outstanding" is player voters only.

    Scoped to one medal: a player who voted for the Colts Medal has not voted
    for the Club Champion, and counting them as done would hide them from the
    chase list for a count they still owe a ballot to."""
    if not fixture_ids:
        return {}
    res = await db.execute(
        text(
            # CAST is load-bearing: asyncpg infers a bound parameter's type
            # from how it is used, and a bare `:medal IS NULL` gives it nothing
            # to work from — it raises AmbiguousParameterError at execute time
            # rather than returning a wrong answer. Same trap anywhere an
            # optional filter is expressed as "param IS NULL OR col = param".
            "SELECT fixture_id, COUNT(DISTINCT voter_player_id) FROM vote_ballots "
            "WHERE organisation_id = :org AND fixture_id = ANY(:ids) AND voter_player_id IS NOT NULL "
            "AND (CAST(:medal AS uuid) IS NULL OR medal_id = CAST(:medal AS uuid)) "
            "GROUP BY fixture_id"
        ),
        {"org": org_id, "ids": fixture_ids, "medal": medal_id},
    )
    return {str(fid): n for fid, n in res.fetchall()}


def voters_expected_for(source: str, match_id, fixture_id, scorecard_counts: dict, lineup_counts: dict) -> int:
    """The eligible-voter count for one fixture, from whichever batch count
    map matches its resolved source. 'playhq' has no batch form — it needs a
    live per-fixture Play.Cricket fetch, which the fixtures LIST view
    deliberately avoids (see the 'ready' cheap-readiness comment in the
    router) — so it reads 0 there; the fixture detail view (one fixture, one
    live fetch is fine) resolves it properly via resolve_eligibility."""
    if source == "scorecard":
        return scorecard_counts.get(str(match_id), 0)
    if source == "lineup":
        return lineup_counts.get(str(fixture_id), 0)
    return 0


async def outstanding_voters(db: AsyncSession, org_id, eligible: list[dict], ballots: list[VoteBallot]) -> list[dict]:
    """Eligible players who haven't voted yet, with enough contact info for
    the hub's chase panel and the nudge endpoint. ``channel`` is 'email' when
    the player has an address on file, else 'none' — this codebase has no
    SMS/WhatsApp sending integration (BetterComms is email-only), so a nudge
    can only ever be an email reminder."""
    voted_pids = {str(b.voter_player_id) for b in ballots if b.voter_player_id}
    missing = [p for p in eligible if p["id"] not in voted_pids]
    if not missing:
        return []
    ids = [uuid.UUID(p["id"]) for p in missing]
    res = await db.execute(
        text("SELECT id, photo_url, email FROM players WHERE organisation_id = :org AND id = ANY(:ids)"),
        {"org": org_id, "ids": ids},
    )
    info = {str(pid): {"photo_url": photo, "email": email} for pid, photo, email in res.fetchall()}
    out = []
    for p in missing:
        ci = info.get(p["id"], {})
        out.append({
            "id": p["id"],
            "name": p["name"],
            "photo_url": ci.get("photo_url"),
            "email": ci.get("email"),
            "channel": "email" if ci.get("email") else "none",
        })
    return out


NUDGE_COOLDOWN_HOURS = 24


async def recently_nudged(db: AsyncSession, medal_id, fixture_id, player_ids: list) -> set[str]:
    """Player ids nudged for this fixture's medal within the cooldown window.

    Per medal, not per fixture: two medals over one fixture are two ballots
    the player genuinely owes, so a reminder about one must not suppress the
    reminder about the other."""
    if not player_ids:
        return set()
    res = await db.execute(
        text(
            "SELECT DISTINCT player_id FROM vote_nudges "
            "WHERE medal_id = :mid AND fixture_id = :fid AND player_id = ANY(:pids) "
            "AND sent_at > now() - make_interval(hours => :hrs)"
        ),
        {"mid": medal_id, "fid": fixture_id, "pids": player_ids, "hrs": NUDGE_COOLDOWN_HOURS},
    )
    return {str(r[0]) for r in res.fetchall()}


async def send_nudge(db: AsyncSession, club, medal: VoteMedal, fixture: Fixture, player: dict,
                     link_token: Optional[str]) -> tuple[bool, Optional[str]]:
    """Email one outstanding voter a reminder, deep-linked straight to this
    fixture's ballot. Returns (sent, failure_reason); never raises — a
    provider hiccup on one player shouldn't fail the whole nudge batch."""
    from app.config.settings import settings
    from app.services import email_service

    email = player.get("email")
    if not email:
        return False, "no_contact"

    link = f"{settings.public_base_url}/vote/{link_token}?fixture={fixture.id}" if link_token else None
    opponent = fixture.opponent_name or fixture.label or "TBC"
    # The medal is named in the reminder because a club running several counts
    # will send several reminders about the same match, and "cast your vote"
    # twice with nothing to tell them apart reads as a duplicate email.
    award = medal.name if medal and medal.name else DEFAULT_MEDAL_NAME
    subject = f"{round_label_for(fixture)} v {opponent} — {award} votes"
    first = (player.get("name") or "").split(" ")[0] or "there"
    body_html = (
        f"<p>Hi {first},</p>"
        f"<p><strong>{award}</strong> votes are still open for "
        f"<strong>{round_label_for(fixture)} v {opponent}</strong>. "
        f"It takes about 30 seconds, and you don't need to log in.</p>"
        + (f'<p><a href="{link}">Cast your vote</a></p>' if link else "")
    )
    body_text = (
        f"Hi {first},\n\n{award} votes are still open for "
        f"{round_label_for(fixture)} v {opponent}.\n"
    ) + (link or "")
    try:
        msg = email_service.EmailMessage(
            to_email=email, to_name=player.get("name"), subject=subject,
            html=body_html, text=body_text,
            from_email=settings.email_from_address, from_name=club.name or settings.email_from_name,
            reply_to=settings.email_reply_to,
        )
        result = await email_service.get_email_provider().send(msg)
    except Exception:
        logger.exception("vote nudge send failed for player %s / fixture %s", player.get("id"), fixture.id)
        return False, "send_failed"
    if not result.ok:
        return False, "send_failed"
    db.add(VoteNudge(
        organisation_id=club.id, medal_id=medal.id, fixture_id=fixture.id,
        player_id=uuid.UUID(player["id"]),
    ))
    return True, None


def effective_source(cfg: dict, override: Optional[str]) -> str:
    """The fixture's own source override, else the club default."""
    if override in ELIGIBILITY_SOURCES:
        return override
    return cfg.get("eligibility_source") or "scorecard"


async def resolve_eligibility(
    db: AsyncSession, club, fixture, cfg: dict, override: Optional[str] = None,
    *, check_all: bool = False,
) -> dict:
    """Who can be voted for, and where that list came from.

    Uses the fixture's chosen source. When that source has nothing yet (no XI
    saved, team list not published, scorecard not synced) it falls back to the
    first other source that does, rather than leaving a club unable to vote —
    and says so via ``used``/``fell_back`` so the admin page can show which list
    is actually in play.

    ``check_all=True`` also counts the sources not in use, so the admin can see
    what switching would give them. It costs a live upstream call, so the public
    ballot page leaves it off.
    """
    requested = effective_source(cfg, override)
    order = [requested] + [s for s in ELIGIBILITY_SOURCES if s != requested]

    players: list[dict] = []
    unmatched: list[str] = []
    used: Optional[str] = None
    counts: dict[str, Optional[int]] = {}

    for src in order:
        # Without check_all we stop at the first source that yields a list, so
        # a fallback source (and its live Play.Cricket fetch) is only ever paid
        # for when the chosen one is genuinely empty.
        if players and not check_all:
            break
        found, unres = await eligible_from_source(db, club, fixture, src)
        counts[src] = len(found)
        if found and used is None:
            players, unmatched, used = found, unres, src

    return {
        "requested": requested,
        "used": used,
        "fell_back": bool(used and used != requested),
        "players": players,
        "unmatched": unmatched,
        "counts": counts,
        "labels": SOURCE_LABELS,
    }


# ─── Voting state ────────────────────────────────────────────────────────────

def fixture_close_date(fixture: Fixture, cfg: dict) -> Optional[date]:
    """Last day votes are accepted (inclusive): match end + auto_close_days."""
    end = fixture.end_on or fixture.played_on
    if not end:
        return None
    return end + timedelta(days=int(cfg["auto_close_days"]))


def fixture_vote_state(fixture: Fixture, cfg: dict, override: Optional[str], ready: bool,
                       today: Optional[date] = None) -> str:
    """One of: 'upcoming' (not played yet), 'awaiting_team' (played, but no
    votable list from the club's chosen source yet — an unsynced scorecard, an
    unsaved XI, an unpublished team list), 'open', 'closed' (auto-close passed),
    'locked' (admin lock). A manual lock/reopen always wins over the auto
    window."""
    today = today or date.today()
    start = fixture.played_on
    if start and start > today:
        return "upcoming"
    if not ready:
        return "awaiting_team"
    if override == "locked":
        return "locked"
    if override == "reopened":
        return "open"
    close = fixture_close_date(fixture, cfg)
    if close and today > close:
        return "closed"
    return "open"


async def get_override(db: AsyncSession, medal_id, fixture_id) -> Optional[VoteFixtureOverride]:
    """This medal's override row for the fixture (lock/reopen status and/or an
    eligibility source), or None. Callers read ``.status`` /
    ``.eligibility_source``. Per medal since 265 — locking the Colts count on a
    match must not lock the Club Champion count on the same match."""
    res = await db.execute(
        select(VoteFixtureOverride).where(
            VoteFixtureOverride.medal_id == medal_id,
            VoteFixtureOverride.fixture_id == fixture_id,
        )
    )
    return res.scalar_one_or_none()


async def overrides_by_fixture(db: AsyncSession, medal_id, fixture_ids: list) -> dict[str, VoteFixtureOverride]:
    """One medal's override rows for a page of fixtures, keyed on fixture id."""
    if not fixture_ids:
        return {}
    res = await db.execute(
        select(VoteFixtureOverride).where(
            VoteFixtureOverride.medal_id == medal_id,
            VoteFixtureOverride.fixture_id.in_(fixture_ids),
        )
    )
    return {str(o.fixture_id): o for o in res.scalars().all()}


# ─── Counting ────────────────────────────────────────────────────────────────

def tally_ballots(ballots: list[VoteBallot], values: list[int]) -> dict[str, dict]:
    """Raw weekly totals per votable player.

    Returns {player_id: {"raw": int, "counts": [n at values[0], n at values[1], …]}}.
    A pick's value comes from its POSITION against the current config; picks at
    positions beyond the configured ballot (config shrank after votes came in)
    score nothing.
    """
    totals: dict[str, dict] = {}
    for b in ballots:
        for pick in b.picks:
            idx = (pick.position or 0) - 1
            if idx < 0 or idx >= len(values):
                continue
            pid = str(pick.player_id)
            t = totals.setdefault(pid, {"raw": 0, "counts": [0] * len(values)})
            t["raw"] += values[idx]
            t["counts"][idx] += 1
    return totals


def award_weekly_points(totals: dict[str, dict], cfg: dict) -> dict[str, int]:
    """Turn a fixture's raw totals into season points under the club's config.

    'tally'  — season points ARE the raw vote total (10 voters all giving a
               player their 3 = 30 points).
    'rank'   — Brownlow conversion: the week's top vote-getter earns
               ballot_values[0], second earns ballot_values[1], and so on.
               Ties under 'share' all take the value of the best position they
               tie for (standard competition ranking — the next value(s) are
               consumed). Under 'countback' a tie is broken by who received
               more of the highest ballot value, then the next value, etc.;
               only a dead heat after every countback still shares.
    """
    values = cfg["ballot_values"]
    if cfg["counting_method"] == "tally":
        return {pid: t["raw"] for pid, t in totals.items() if t["raw"] > 0}

    contenders = [(pid, t) for pid, t in totals.items() if t["raw"] > 0]
    if cfg["tie_policy"] == "countback":
        def key(item):
            return (item[1]["raw"], *item[1]["counts"])
    else:
        def key(item):
            return (item[1]["raw"],)

    contenders.sort(key=key, reverse=True)
    awarded: dict[str, int] = {}
    consumed = 0
    i = 0
    while i < len(contenders) and consumed < len(values):
        group = [contenders[i]]
        while i + len(group) < len(contenders) and key(contenders[i + len(group)]) == key(contenders[i]):
            group.append(contenders[i + len(group)])
        value = values[consumed]
        for pid, _t in group:
            awarded[pid] = value
        consumed += len(group)
        i += len(group)
    return awarded


# ─── Season / rounds ─────────────────────────────────────────────────────────

def season_year_for(d: Optional[date]) -> Optional[int]:
    """AU season year: Jul→Jun. October 2025 and February 2026 are both season
    2025 ("Summer 2025/26")."""
    if not d:
        return None
    return d.year if d.month >= 7 else d.year - 1


def season_window(year: int) -> tuple[date, date]:
    return date(year, 7, 1), date(year + 1, 6, 30)


def season_label(year: int) -> str:
    return f"{year}/{str((year + 1) % 100).zfill(2)}"


def round_key_for(fixture: Fixture) -> str:
    r = (fixture.round or "").strip()
    if r:
        return r.lower()
    if fixture.played_on:
        return fixture.played_on.isoformat()
    return "unscheduled"


def round_label_for(fixture: Fixture) -> str:
    r = (fixture.round or "").strip()
    if r:
        # Fixture rounds sync as bare numbers or "Round N" — display uniformly.
        return r if not r.isdigit() else f"Round {r}"
    if fixture.played_on:
        return fixture.played_on.strftime("%d %b %Y")
    return "Unscheduled"


def round_short_for(label: str) -> str:
    """A compact round tag for the race chart's x-axis — "Round 8" -> "R8",
    anything without a number (a final, an unscheduled date) -> unchanged."""
    n = _round_numeric(label)
    return f"R{n}" if n is not None else (label or "")


def _round_numeric(label: str) -> Optional[int]:
    m = re.search(r"(\d+)", label or "")
    return int(m.group(1)) if m else None


def round_sort_key(label: str, played_on: Optional[date]) -> tuple:
    """Earliest-first sort key for a round, robust to several grades sharing
    one match date (ordinary Saturday club cricket). Date is the primary
    signal; when several rounds tie on date (different grades, same weekend)
    a numeric label ("Round 13") needs numeric comparison, not string
    comparison ("Round 10" < "Round 7" alphabetically) — a non-numeric label
    (a final) sorts after every numbered round. Reverse the result for a
    most-recent-first list."""
    n = _round_numeric(label)
    return (played_on or date.min, n if n is not None else 10**6, label or "")


async def effective_grade_ids(db: AsyncSession, fixtures: list[Fixture]) -> dict[str, uuid.UUID]:
    """``fixture.id`` (str) → its effective grade id.

    ``routers/fixtures.py::sync_fixtures`` never populates ``Fixture.grade_id``
    at all (it only auto-attributes ``team_id``, BetterSelect's own team
    concept) — so every auto-synced fixture reads NULL there, even long after
    it's played, starving any grade/team filter of options. The separate
    game-level sync IS correct and sets ``games.grade_id``, so this falls back
    to that (via ``match_ref_id``) for any fixture whose own column is unset.
    """
    out: dict[str, uuid.UUID] = {}
    missing = [f for f in fixtures if not f.grade_id]
    if missing:
        match_ids = [match_ref_id(f) for f in missing]
        res = await db.execute(
            text("SELECT id, grade_id FROM games WHERE id = ANY(:ids) AND grade_id IS NOT NULL"),
            {"ids": match_ids},
        )
        game_grade = {str(gid): grade_id for gid, grade_id in res.fetchall()}
        for f in missing:
            gid = game_grade.get(str(match_ref_id(f)))
            if gid:
                out[str(f.id)] = gid
    for f in fixtures:
        if f.grade_id:
            out[str(f.id)] = f.grade_id
    return out


async def load_ballots_by_fixture(db: AsyncSession, org_id, fixture_ids: list, medal_id=None) -> dict:
    """One medal's ballots (picks eager-loaded) for a set of fixtures, grouped
    by fixture id (string keys). ``medal_id=None`` reads every medal's, which
    only the player-merge and cleanup paths want — a count must always name
    its medal or it would add two awards' ballots into one total."""
    if not fixture_ids:
        return {}
    conds = [
        VoteBallot.organisation_id == org_id,
        VoteBallot.fixture_id.in_(fixture_ids),
    ]
    if medal_id is not None:
        conds.append(VoteBallot.medal_id == medal_id)
    res = await db.execute(select(VoteBallot).where(*conds))
    grouped: dict[str, list[VoteBallot]] = {}
    for b in res.scalars().all():
        grouped.setdefault(str(b.fixture_id), []).append(b)
    return grouped


async def player_names(db: AsyncSession, org_id, player_ids: set[str]) -> dict[str, str]:
    if not player_ids:
        return {}
    ids = [uuid.UUID(p) for p in player_ids]
    res = await db.execute(
        text(
            "SELECT id, COALESCE(display_name_override, name) FROM players "
            "WHERE organisation_id = :org AND id = ANY(:ids)"
        ),
        {"org": org_id, "ids": ids},
    )
    return {str(pid): name for pid, name in res.fetchall()}


async def build_leaderboard(
    db: AsyncSession,
    org_id,
    cfg: dict,
    year: int,
    grade_id: Optional[str] = None,
    through_round: Optional[str] = None,
    medal: Optional[VoteMedal] = None,
) -> dict:
    """The Brownlow board: every round (a distinct fixture.round label, or the
    match date when no round is set) in chronological order, each fixture's
    weekly result, and cumulative standings THROUGH a chosen round — so in week
    8 you can replay what the count looked like after week 3.

    ONE medal's count. Two restrictions follow from that and both matter: only
    that medal's ballots are loaded, and only fixtures in the grades the medal
    counts are on the board. Without the second, a club whose Colts Medal is
    restricted to the junior grades would still show every senior round on the
    board with a nil result, which reads as "nobody voted" rather than "this
    match isn't part of this count".

    grade_id narrows further, to one grade within the medal's own set; without
    it the board covers everything the medal counts.
    """
    start, end = season_window(year)
    q = (
        select(Fixture)
        .where(
            Fixture.organisation_id == org_id,
            Fixture.played_on.is_not(None),
            Fixture.played_on >= start,
            Fixture.played_on <= end,
        )
        .order_by(Fixture.played_on.asc())
    )
    all_fixtures = (await db.execute(q)).scalars().all()
    # sync_fixtures never populated Fixture.grade_id (see effective_grade_ids'
    # own docstring) — resolve every fixture's grade before filtering, or a
    # grade_id filter would silently match nothing.
    grade_by_fixture = await effective_grade_ids(db, all_fixtures)
    allowed = await medal_grade_ids(db, org_id, medal)
    fixtures = [f for f in all_fixtures if medal_covers(allowed, grade_by_fixture.get(str(f.id)))]
    if grade_id:
        fixtures = [f for f in fixtures if str(grade_by_fixture.get(str(f.id))) == grade_id]

    ballots_by_fx = await load_ballots_by_fixture(
        db, org_id, [f.id for f in fixtures], medal.id if medal else None
    )
    # Only fixtures that actually collected votes appear on the board.
    voted = [f for f in fixtures if ballots_by_fx.get(str(f.id))]

    # Grade names for the fixture chips.
    grade_ids = {grade_by_fixture.get(str(f.id)) for f in voted if grade_by_fixture.get(str(f.id))}
    grade_names: dict[str, str] = {}
    if grade_ids:
        res = await db.execute(
            text("SELECT id, name FROM grades WHERE id = ANY(:ids)"),
            {"ids": list(grade_ids)},
        )
        grade_names = {str(gid): name for gid, name in res.fetchall()}

    # Group into rounds, ordered by each round's earliest date — a numeric
    # round label ("Round 13") sorts numerically (round_sort_key), since
    # several grades often share a match date (ordinary Saturday cricket) and
    # a plain string sort would put "Round 10" before "Round 7".
    rounds: list[dict] = []
    by_key: dict[str, dict] = {}
    for f in voted:
        key = round_key_for(f)
        rd = by_key.get(key)
        if not rd:
            rd = {"key": key, "label": round_label_for(f), "date": f.played_on, "fixtures": []}
            by_key[key] = rd
            rounds.append(rd)
        rd["date"] = min(rd["date"], f.played_on)
        rd["fixtures"].append(f)
    rounds.sort(key=lambda r: round_sort_key(r["label"], r["date"]))

    values = cfg["ballot_values"]
    cumulative: dict[str, dict] = {}
    grade_by_pid: dict[str, Optional[str]] = {}
    all_pids: set[str] = set()
    out_rounds: list[dict] = []
    # A running-total history per player, one entry per COUNTED round —
    # movement/form/cumulative below are all derived from this, not stored.
    history: dict[str, list[int]] = {}
    rank_snapshots: list[dict[str, int]] = []  # one {player_id: rank} per counted round
    counted_round_count = 0
    cutoff_hit = False
    for rd in rounds:
        fixtures_out = []
        for f in rd["fixtures"]:
            totals = tally_ballots(ballots_by_fx.get(str(f.id), []), values)
            awarded = award_weekly_points(totals, cfg)
            results = []
            for pid, t in totals.items():
                results.append({
                    "player_id": pid,
                    "raw": t["raw"],
                    "counts": t["counts"],
                    "points": awarded.get(pid, 0),
                })
                all_pids.add(pid)
            results.sort(key=lambda r: (-r["points"], -r["raw"]))
            eff_gid = grade_by_fixture.get(str(f.id))
            fixtures_out.append({
                "id": str(f.id),
                "opponent": f.opponent_name or f.label,
                "grade_id": str(eff_gid) if eff_gid else None,
                "grade": grade_names.get(str(eff_gid)) if eff_gid else None,
                "date": f.played_on.isoformat() if f.played_on else None,
                "ballots": len(ballots_by_fx.get(str(f.id), [])),
                "results": results,
            })
            if not cutoff_hit:
                for r in results:
                    c = cumulative.setdefault(r["player_id"], {
                        "points": 0, "raw": 0, "counts": [0] * len(values), "rounds": 0,
                    })
                    c["points"] += r["points"]
                    c["raw"] += r["raw"]
                    for i2, n in enumerate(r["counts"]):
                        if i2 < len(c["counts"]):
                            c["counts"][i2] += n
                    if r["points"] > 0 or r["raw"] > 0:
                        c["rounds"] += 1
                    # Most-recently-played grade — a reasonable single tag for
                    # a player who turns out for more than one grade.
                    if eff_gid:
                        grade_by_pid[r["player_id"]] = str(eff_gid)
        out_rounds.append({
            "key": rd["key"],
            "label": rd["label"],
            "short": round_short_for(rd["label"]),
            "date": rd["date"].isoformat(),
            "fixtures": fixtures_out,
            "counted": not cutoff_hit,
        })
        if not cutoff_hit:
            counted_round_count += 1
            # Snapshot this round's running total (for the race chart) and
            # rank (for next-round's movement) for every player on the board
            # so far — including those who didn't score this particular round.
            for pid in cumulative:
                history.setdefault(pid, []).append(cumulative[pid]["points"])
            ranked = sorted(cumulative.keys(), key=lambda p: (-cumulative[p]["points"], -cumulative[p]["raw"]))
            rank_snapshots.append({pid: i + 1 for i, pid in enumerate(ranked)})
        if through_round is not None and rd["key"] == through_round:
            cutoff_hit = True

    # Left-pad each player's history to the full counted-round length — a
    # player who first scored in round k had an implicit 0 total before that.
    for pid, h in history.items():
        if len(h) < counted_round_count:
            history[pid] = [0] * (counted_round_count - len(h)) + h

    movement: dict[str, int] = {}
    if len(rank_snapshots) >= 2:
        cur_ranks, prev_ranks = rank_snapshots[-1], rank_snapshots[-2]
        for pid, r in cur_ranks.items():
            movement[pid] = (prev_ranks[pid] - r) if pid in prev_ranks else 0

    names = await player_names(db, org_id, all_pids)
    grade_short_names = {gid: _grade_short(name) for gid, name in grade_names.items()}
    standings = []
    for pid, c in cumulative.items():
        h = history.get(pid, [])
        # Weekly deltas from the cumulative history — cumulative only ever
        # grows, so a plain diff recovers each round's own contribution
        # without a second pass over the fixtures.
        weekly = [h[i] - (h[i - 1] if i > 0 else 0) for i in range(len(h))]
        gid = grade_by_pid.get(pid)
        standings.append({
            "player_id": pid,
            "name": names.get(pid, "Unknown"),
            "points": c["points"],
            "raw": c["raw"],
            "counts": c["counts"],
            "rounds": c["rounds"],
            "grade": grade_names.get(gid) if gid else None,
            "grade_short": grade_short_names.get(gid) if gid else None,
            "movement": movement.get(pid, 0),
            "form": weekly[-5:],
            "cumulative": h,
            "round_gain": weekly[-1] if weekly else 0,
        })
    standings.sort(key=lambda s: (-s["points"], -s["raw"], s["name"]))
    for i, s in enumerate(standings):
        s["tied"] = bool(i > 0 and s["points"] == standings[i - 1]["points"] and s["raw"] == standings[i - 1]["raw"])

    # "What just happened" — the last COUNTED round's own results, for the
    # race card and awards-night reveal caption.
    last_round = None
    counted_out = [r for r in out_rounds if r["counted"]]
    if counted_out:
        lr = counted_out[-1]
        opponents = ", ".join(f"vs {fx['opponent'] or 'TBC'}" for fx in lr["fixtures"])
        lr_results = []
        for fx in lr["fixtures"]:
            for r in fx["results"]:
                if r["points"] > 0:
                    lr_results.append({"player_id": r["player_id"], "name": names.get(r["player_id"], "Unknown"), "points": r["points"]})
        lr_results.sort(key=lambda r: -r["points"])
        last_round = {"label": lr["label"], "fixture": opponents, "results": lr_results}

    return {
        "year": year,
        "medal_id": str(medal.id) if medal else None,
        "medal_name": medal.name if medal else cfg.get("medal_name"),
        "ballot_values": values,
        "counting_method": cfg["counting_method"],
        "tie_policy": cfg["tie_policy"],
        "rounds": out_rounds,
        "standings": standings,
        "through_round": through_round if cutoff_hit else None,
        "last_round": last_round,
    }


def _grade_short(name: str) -> str:
    """A compact grade tag for a leaderboard row — "1st Grade" -> "1st",
    "PSWL South" -> "PSWL", anything unmatched -> its first word."""
    m = re.match(r"^(\d+(?:st|nd|rd|th))\b", name or "", re.IGNORECASE)
    if m:
        return m.group(1)
    return (name or "").split(" ")[0][:8] or "—"
