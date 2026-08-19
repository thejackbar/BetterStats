"""BetterFootball — best-and-fairest vote collection.

The cricket silo's medals engine pointed at football. Everything is DERIVED ON
READ from raw ballots plus the medal's current config — no stored weekly
results, no stored season points — so changing a ballot shape or counting
method mid-season restates the whole season consistently.

**The counting rules are IMPORTED from ``services/votes.py``, never re-typed.**
``tally_ballots``, ``award_weekly_points``, ``clean_ballot_values`` and the
vocabularies are pure functions over plain data with no cricket in them, and a
second copy is how the two sports quietly start disagreeing about what a
countback is. If a rule needs changing, change it there and both sports move.

What IS football's own, and why:

  * A ballot keys on ``games`` directly. Cricket keys on ``fixtures``,
    BetterSelect's own scheduling table, which this silo has no equivalent of —
    a football game IS the row.
  * There is no eligibility SOURCE to choose between. Cricket picks among the
    scorecard, a saved XI and the published side; football has one team list,
    the one PlayHQ returns with the game, already stored by the sync (see
    ``services/afl/lineups.py``).
  * A season is the ``seasons`` row the game's grade belongs to, not a Jul→Jun
    window. Football runs inside one calendar year, so cricket's summer-spanning
    season maths would file a whole season under the wrong label.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.afl import AflVoteBallot, AflVoteGameOverride, AflVoteMedal, AflVoteNudge
from app.services.afl.lineups import our_lineup_players
# The counting rules and their vocabularies, shared with cricket on purpose.
from app.services.votes import (  # noqa: F401  (re-exported for the routers)
    COUNTING_METHODS,
    DEFAULT_BALLOT,
    MAX_POSITIONS,
    TIE_POLICIES,
    VOTER_MODES,
    award_weekly_points,
    clean_ballot_values,
    clean_grade_ids,
    clean_medal_name,
    round_short_for,
    round_sort_key,
    tally_ballots,
)

logger = logging.getLogger(__name__)

DEFAULT_MEDAL_NAME = "Best & Fairest"
NUDGE_COOLDOWN_HOURS = 24


# ─── Medals ──────────────────────────────────────────────────────────────────

async def list_medals(db: AsyncSession, org_id) -> list[AflVoteMedal]:
    res = await db.execute(
        select(AflVoteMedal)
        .where(AflVoteMedal.organisation_id == org_id)
        .order_by(AflVoteMedal.position, AflVoteMedal.created_at)
    )
    return list(res.scalars().all())


async def get_medal(db: AsyncSession, org_id, medal_id) -> Optional[AflVoteMedal]:
    """One medal, scoped to the club — an id arriving from a browser must never
    resolve against another club's row."""
    if not medal_id:
        return None
    try:
        mid = uuid.UUID(str(medal_id))
    except (TypeError, ValueError):
        return None
    res = await db.execute(
        select(AflVoteMedal).where(
            AflVoteMedal.id == mid, AflVoteMedal.organisation_id == org_id)
    )
    return res.scalar_one_or_none()


async def medal_by_token(db: AsyncSession, token: str) -> Optional[AflVoteMedal]:
    if not token:
        return None
    res = await db.execute(select(AflVoteMedal).where(AflVoteMedal.link_token == token))
    return res.scalar_one_or_none()


async def resolve_medal(db: AsyncSession, org_id, medal_id=None) -> Optional[AflVoteMedal]:
    """The medal a request means: the one it named, else the club's first."""
    if medal_id:
        return await get_medal(db, org_id, medal_id)
    medals = await list_medals(db, org_id)
    return medals[0] if medals else None


async def ensure_default_medal(db: AsyncSession, org_id) -> AflVoteMedal:
    """The club's first medal, created on demand rather than making every
    screen cope with "no medal". Does not commit — the caller's transaction
    owns it."""
    medals = await list_medals(db, org_id)
    if medals:
        return medals[0]
    medal = AflVoteMedal(id=uuid.uuid4(), organisation_id=org_id,
                         name=DEFAULT_MEDAL_NAME, position=0)
    db.add(medal)
    await db.flush()
    return medal


def new_token() -> str:
    return secrets.token_urlsafe(24)


def effective_config(m: Optional[AflVoteMedal]) -> dict:
    """One medal's config with defaults applied — usable whether or not the
    medal exists yet, so a club that has never voted still renders."""
    return {
        "medal_id": str(m.id) if m else None,
        "medal_name": (m.name if m and m.name else DEFAULT_MEDAL_NAME),
        "grade_ids": clean_grade_ids(m.grade_ids if m else None),
        "enabled": bool(m.enabled) if m else False,
        "require_pin": bool(m.require_pin) if m else True,
        "voter_mode": (m.voter_mode if m and m.voter_mode in VOTER_MODES else "players"),
        "ballot_values": clean_ballot_values(m.ballot_values if m else None),
        "counting_method": (m.counting_method if m and m.counting_method in COUNTING_METHODS else "rank"),
        "tie_policy": (m.tie_policy if m and m.tie_policy in TIE_POLICIES else "share"),
        "allow_self_vote": bool(m.allow_self_vote) if m else False,
        "allow_non_participants": bool(m.allow_non_participants) if m else False,
        "auto_close_days": int(m.auto_close_days) if m and m.auto_close_days else 7,
    }


# ─── Grades a medal counts ───────────────────────────────────────────────────

async def medal_grade_ids(db: AsyncSession, org_id, medal: Optional[AflVoteMedal]) -> Optional[set[str]]:
    """Every grade id this medal counts, or None meaning "all of them".

    Same reasoning as the cricket side: ``grades`` rows are PER SEASON, so a
    medal matching on its stored ids alone would stop counting the day the new
    season's grades are created. The stored ids are expanded through their
    NAMES, which is what makes a medal a standing award — a club sets its
    Reserves medal up once, not every March.
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
    """A game whose grade can't be resolved is counted only by an all-grades
    medal — a row we cannot place must not be swept into a restricted count."""
    if allowed is None:
        return True
    return bool(grade_id) and str(grade_id) in allowed


async def club_grade_options(db: AsyncSession, org_id) -> list[dict]:
    """Each distinct grade NAME once, carrying its most recent season's id.
    Listing a name once per season would make the picker unusable for a club
    with real history, and every row would mean the same thing."""
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


async def medal_grade_names(db: AsyncSession, org_id, medals: list[AflVoteMedal]) -> dict[str, list[str]]:
    """medal id → the grade NAMES it counts, so a screen can re-tick a medal's
    selection even when the stored id belongs to an older season's row."""
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


# ─── Games ───────────────────────────────────────────────────────────────────

async def season_games(db: AsyncSession, org_id, season_id=None) -> list[dict]:
    """The club's played games for a season, newest first, with everything the
    games list and the count both need. Org-scoped through grades → seasons, so
    a game belonging to another club's competition can never appear."""
    res = await db.execute(
        text(
            """
            SELECT g.id, g.played_at, g.home_team, g.away_team, g.result,
                   d.round_name, d.status, d.our_side,
                   gr.id AS grade_id, gr.name AS grade_name,
                   s.id AS season_id, s.name AS season_name, s.year
            FROM games g
            JOIN afl_game_details d ON d.game_id = g.id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = :org
              AND g.played_at IS NOT NULL
              AND g.played_at <= CURRENT_DATE
              AND (CAST(:season AS uuid) IS NULL OR s.id = CAST(:season AS uuid))
              AND COALESCE(d.is_bye, false) = false
            ORDER BY g.played_at DESC
            """
        ),
        {"org": org_id, "season": season_id},
    )
    return [dict(r) for r in res.mappings().all()]


async def get_game(db: AsyncSession, org_id, game_id) -> Optional[dict]:
    """One of the club's games, in the same shape ``season_games`` returns.
    Org-scoped through grades → seasons, so a game id from a browser can never
    resolve against another club's competition."""
    res = await db.execute(
        text(
            """
            SELECT g.id, g.played_at, g.home_team, g.away_team, g.result,
                   d.round_name, d.status, d.our_side,
                   gr.id AS grade_id, gr.name AS grade_name,
                   s.id AS season_id, s.name AS season_name, s.year
            FROM games g
            JOIN afl_game_details d ON d.game_id = g.id
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = :org AND g.id = :gid
            """
        ),
        {"org": org_id, "gid": game_id},
    )
    row = res.mappings().first()
    return dict(row) if row else None


async def club_seasons(db: AsyncSession, org_id) -> list[dict]:
    """Seasons the club actually played games in, newest first — the season
    picker should never offer one with nothing behind it."""
    res = await db.execute(
        text(
            """
            SELECT DISTINCT s.id, s.name, s.year
            FROM games g
            JOIN grades gr ON gr.id = g.grade_id
            JOIN seasons s ON s.id = gr.season_id
            WHERE s.organisation_id = :org AND g.played_at IS NOT NULL
            ORDER BY s.year DESC NULLS LAST, s.name DESC
            """
        ),
        {"org": org_id},
    )
    return [{"id": str(r["id"]), "name": r["name"], "year": r["year"]} for r in res.mappings().all()]


def game_label(row: dict) -> str:
    """Who the club played, from whichever side isn't ours."""
    if row.get("our_side") == "HOME":
        return row.get("away_team") or "TBC"
    if row.get("our_side") == "AWAY":
        return row.get("home_team") or "TBC"
    # our_side unresolved (a game synced before the flag, or a club-vs-club
    # match): name both rather than guessing at one.
    return " v ".join(x for x in (row.get("home_team"), row.get("away_team")) if x) or "TBC"


def round_label_for(row: dict) -> str:
    r = (row.get("round_name") or "").strip()
    if r:
        return r if not r.isdigit() else f"Round {r}"
    played = row.get("played_at")
    return played.strftime("%d %b %Y") if played else "Unscheduled"


def round_key_for(row: dict) -> str:
    r = (row.get("round_name") or "").strip()
    if r:
        return r.lower()
    played = row.get("played_at")
    return played.isoformat() if played else "unscheduled"


# ─── Voting state ────────────────────────────────────────────────────────────

def game_close_date(row: dict, cfg: dict) -> Optional[date]:
    played = row.get("played_at")
    if not played:
        return None
    return played + timedelta(days=int(cfg["auto_close_days"]))


def game_vote_state(row: dict, cfg: dict, override: Optional[str], ready: bool,
                    today: Optional[date] = None) -> str:
    """'upcoming' | 'awaiting_team' (played, but PlayHQ has given us no team
    list yet) | 'open' | 'closed' (auto-close passed) | 'locked'. A manual
    lock/reopen always beats the auto window."""
    today = today or date.today()
    played = row.get("played_at")
    if played and played > today:
        return "upcoming"
    if not ready:
        return "awaiting_team"
    if override == "locked":
        return "locked"
    if override == "reopened":
        return "open"
    close = game_close_date(row, cfg)
    if close and today > close:
        return "closed"
    return "open"


async def eligible_players(db: AsyncSession, org_id, game_id) -> tuple[list[dict], list[str]]:
    """Who can be voted for: the club's own side of PlayHQ's team list."""
    return await our_lineup_players(db, org_id, game_id)


async def get_override(db: AsyncSession, medal_id, game_id) -> Optional[AflVoteGameOverride]:
    res = await db.execute(
        select(AflVoteGameOverride).where(
            AflVoteGameOverride.medal_id == medal_id,
            AflVoteGameOverride.game_id == game_id,
        )
    )
    return res.scalar_one_or_none()


async def overrides_by_game(db: AsyncSession, medal_id, game_ids: list) -> dict[str, AflVoteGameOverride]:
    if not game_ids or not medal_id:
        return {}
    res = await db.execute(
        select(AflVoteGameOverride).where(
            AflVoteGameOverride.medal_id == medal_id,
            AflVoteGameOverride.game_id.in_(game_ids),
        )
    )
    return {str(o.game_id): o for o in res.scalars().all()}


# ─── Ballots ─────────────────────────────────────────────────────────────────

async def load_ballots_by_game(db: AsyncSession, org_id, game_ids: list, medal_id=None) -> dict:
    """One medal's ballots (picks eager-loaded) for a set of games, grouped by
    game id. ``medal_id=None`` reads every medal's, which only a cleanup path
    wants — a count must always name its medal or it would add two awards'
    ballots into one total."""
    if not game_ids:
        return {}
    conds = [AflVoteBallot.organisation_id == org_id, AflVoteBallot.game_id.in_(game_ids)]
    if medal_id is not None:
        conds.append(AflVoteBallot.medal_id == medal_id)
    res = await db.execute(select(AflVoteBallot).where(*conds))
    grouped: dict[str, list[AflVoteBallot]] = {}
    for b in res.scalars().all():
        grouped.setdefault(str(b.game_id), []).append(b)
    return grouped


async def ballot_counts(db: AsyncSession, org_id, game_ids: list, medal_id=None) -> dict[str, int]:
    if not game_ids:
        return {}
    res = await db.execute(
        text(
            # CAST is load-bearing: asyncpg infers a bound parameter's type from
            # how it is used, and a bare `:medal IS NULL` gives it nothing to go
            # on — it raises at execute time rather than returning a wrong
            # answer.
            "SELECT game_id, COUNT(*) FROM afl_vote_ballots "
            "WHERE organisation_id = :org AND game_id = ANY(:ids) "
            "AND (CAST(:medal AS uuid) IS NULL OR medal_id = CAST(:medal AS uuid)) "
            "GROUP BY game_id"
        ),
        {"org": org_id, "ids": game_ids, "medal": medal_id},
    )
    return {str(gid): n for gid, n in res.fetchall()}


async def player_ballot_counts(db: AsyncSession, org_id, game_ids: list, medal_id=None) -> dict[str, int]:
    """Distinct PLAYER voters per game — the denominator side of "outstanding"
    is player voters only. Per medal: a player who voted for the Reserves medal
    has not voted for the seniors' one."""
    if not game_ids:
        return {}
    res = await db.execute(
        text(
            "SELECT game_id, COUNT(DISTINCT voter_player_id) FROM afl_vote_ballots "
            "WHERE organisation_id = :org AND game_id = ANY(:ids) AND voter_player_id IS NOT NULL "
            "AND (CAST(:medal AS uuid) IS NULL OR medal_id = CAST(:medal AS uuid)) "
            "GROUP BY game_id"
        ),
        {"org": org_id, "ids": game_ids, "medal": medal_id},
    )
    return {str(gid): n for gid, n in res.fetchall()}


async def outstanding_voters(db: AsyncSession, org_id, eligible: list[dict],
                             ballots: list[AflVoteBallot]) -> list[dict]:
    """Eligible players who haven't voted yet, with enough contact detail for
    the chase panel. ``channel`` is 'email' when we hold an address, else
    'none' — this codebase has no SMS integration, so a nudge can only ever be
    an email."""
    voted = {str(b.voter_player_id) for b in ballots if b.voter_player_id}
    missing = [p for p in eligible if p["id"] not in voted]
    if not missing:
        return []
    res = await db.execute(
        text("SELECT id, photo_url, email FROM players WHERE organisation_id = :org AND id = ANY(:ids)"),
        {"org": org_id, "ids": [uuid.UUID(p["id"]) for p in missing]},
    )
    info = {str(pid): {"photo_url": photo, "email": email} for pid, photo, email in res.fetchall()}
    return [
        {
            "id": p["id"], "name": p["name"],
            "photo_url": info.get(p["id"], {}).get("photo_url"),
            "email": info.get(p["id"], {}).get("email"),
            "channel": "email" if info.get(p["id"], {}).get("email") else "none",
        }
        for p in missing
    ]


async def recently_nudged(db: AsyncSession, medal_id, game_id, player_ids: list) -> set[str]:
    """Players nudged for this game's medal inside the cooldown. Per medal: two
    medals over one game are two ballots the player genuinely owes, so a
    reminder about one must not suppress the other."""
    if not player_ids:
        return set()
    res = await db.execute(
        text(
            "SELECT DISTINCT player_id FROM afl_vote_nudges "
            "WHERE medal_id = :mid AND game_id = :gid AND player_id = ANY(:pids) "
            "AND sent_at > now() - make_interval(hours => :hrs)"
        ),
        {"mid": medal_id, "gid": game_id, "pids": player_ids, "hrs": NUDGE_COOLDOWN_HOURS},
    )
    return {str(r[0]) for r in res.fetchall()}


async def send_nudge(db: AsyncSession, club, medal: AflVoteMedal, game: dict, player: dict,
                     link_token: Optional[str]) -> tuple[bool, Optional[str]]:
    """Email one outstanding voter, deep-linked to this game's ballot. Never
    raises — a provider hiccup on one player must not fail the batch."""
    from app.config.settings import settings
    from app.services import email_service

    email = player.get("email")
    if not email:
        return False, "no_contact"

    link = (f"{settings.public_base_url}/vote/{link_token}?game={game['id']}"
            if link_token else None)
    opponent = game_label(game)
    award = medal.name or DEFAULT_MEDAL_NAME
    first = (player.get("name") or "").split(" ")[0] or "there"
    subject = f"{round_label_for(game)} v {opponent} — {award} votes"
    body_html = (
        f"<p>Hi {first},</p>"
        f"<p><strong>{award}</strong> votes are still open for "
        f"<strong>{round_label_for(game)} v {opponent}</strong>. "
        f"It takes about 30 seconds, and you don't need to log in.</p>"
        + (f'<p><a href="{link}">Cast your vote</a></p>' if link else "")
    )
    body_text = (
        f"Hi {first},\n\n{award} votes are still open for "
        f"{round_label_for(game)} v {opponent}.\n"
    ) + (link or "")
    try:
        msg = email_service.EmailMessage(
            to_email=email, to_name=player.get("name"), subject=subject,
            html=body_html, text=body_text,
            from_email=settings.email_from_address,
            from_name=club.name or settings.email_from_name,
            reply_to=settings.email_reply_to,
        )
        result = await email_service.get_email_provider().send(msg)
    except Exception:
        logger.exception("afl vote nudge failed for player %s / game %s", player.get("id"), game.get("id"))
        return False, "send_failed"
    if not result.ok:
        return False, "send_failed"
    db.add(AflVoteNudge(
        id=uuid.uuid4(), organisation_id=club.id, medal_id=medal.id,
        game_id=uuid.UUID(str(game["id"])), player_id=uuid.UUID(player["id"]),
    ))
    return True, None


# ─── The count ───────────────────────────────────────────────────────────────

async def player_names(db: AsyncSession, org_id, player_ids: set[str]) -> dict[str, str]:
    if not player_ids:
        return {}
    res = await db.execute(
        text(
            "SELECT id, COALESCE(display_name_override, name) FROM players "
            "WHERE organisation_id = :org AND id = ANY(:ids)"
        ),
        {"org": org_id, "ids": [uuid.UUID(p) for p in player_ids]},
    )
    return {str(pid): name for pid, name in res.fetchall()}


async def build_leaderboard(
    db: AsyncSession, org_id, cfg: dict, season_id=None,
    grade_id: Optional[str] = None, through_round: Optional[str] = None,
    medal: Optional[AflVoteMedal] = None,
) -> dict:
    """ONE medal's count: every round in order, each game's weekly result, and
    cumulative standings THROUGH a chosen round — so in round 14 you can replay
    what the count looked like after round 3, which is what awards night needs.

    Only games the medal counts appear. Without that a medal restricted to the
    Reserves would still list every senior round at nil, which reads as "nobody
    voted" rather than "not part of this count".
    """
    rows = await season_games(db, org_id, season_id)
    allowed = await medal_grade_ids(db, org_id, medal)
    rows = [r for r in rows if medal_covers(allowed, r.get("grade_id"))]
    if grade_id:
        rows = [r for r in rows if str(r.get("grade_id")) == grade_id]

    ballots_by_game = await load_ballots_by_game(
        db, org_id, [r["id"] for r in rows], medal.id if medal else None)
    voted = [r for r in rows if ballots_by_game.get(str(r["id"]))]

    # Group into rounds, earliest first — the count is read forwards.
    rounds: list[dict] = []
    by_key: dict[str, dict] = {}
    for r in voted:
        key = round_key_for(r)
        rd = by_key.get(key)
        if not rd:
            rd = {"key": key, "label": round_label_for(r), "date": r["played_at"], "games": []}
            by_key[key] = rd
            rounds.append(rd)
        if r["played_at"] and (rd["date"] is None or r["played_at"] < rd["date"]):
            rd["date"] = r["played_at"]
        rd["games"].append(r)
    rounds.sort(key=lambda x: round_sort_key(x["label"], x["date"]))

    values = cfg["ballot_values"]
    cumulative: dict[str, dict] = {}
    grade_by_pid: dict[str, Optional[str]] = {}
    all_pids: set[str] = set()
    out_rounds: list[dict] = []
    history: dict[str, list[int]] = {}
    rank_snapshots: list[dict[str, int]] = []
    counted = 0
    cutoff_hit = False

    for rd in rounds:
        games_out = []
        for r in rd["games"]:
            totals = tally_ballots(ballots_by_game.get(str(r["id"]), []), values)
            awarded = award_weekly_points(totals, cfg)
            results = []
            for pid, t in totals.items():
                results.append({"player_id": pid, "raw": t["raw"], "counts": t["counts"],
                                "points": awarded.get(pid, 0)})
                all_pids.add(pid)
            results.sort(key=lambda x: (-x["points"], -x["raw"]))
            games_out.append({
                "id": str(r["id"]),
                "opponent": game_label(r),
                "grade_id": str(r["grade_id"]) if r["grade_id"] else None,
                "grade": r["grade_name"],
                "date": r["played_at"].isoformat() if r["played_at"] else None,
                "ballots": len(ballots_by_game.get(str(r["id"]), [])),
                "results": results,
            })
            if not cutoff_hit:
                for x in results:
                    c = cumulative.setdefault(x["player_id"], {
                        "points": 0, "raw": 0, "counts": [0] * len(values), "rounds": 0})
                    c["points"] += x["points"]
                    c["raw"] += x["raw"]
                    for i, n in enumerate(x["counts"]):
                        if i < len(c["counts"]):
                            c["counts"][i] += n
                    if x["points"] > 0 or x["raw"] > 0:
                        c["rounds"] += 1
                    if r["grade_id"]:
                        grade_by_pid[x["player_id"]] = str(r["grade_id"])
        out_rounds.append({
            "key": rd["key"], "label": rd["label"], "short": round_short_for(rd["label"]),
            "date": rd["date"].isoformat() if rd["date"] else None,
            "games": games_out, "counted": not cutoff_hit,
        })
        if not cutoff_hit:
            counted += 1
            for pid in cumulative:
                history.setdefault(pid, []).append(cumulative[pid]["points"])
            ranked = sorted(cumulative, key=lambda p: (-cumulative[p]["points"], -cumulative[p]["raw"]))
            rank_snapshots.append({pid: i + 1 for i, pid in enumerate(ranked)})
        if through_round is not None and rd["key"] == through_round:
            cutoff_hit = True

    # A player who first scored in round k had an implicit 0 before that.
    for pid, h in history.items():
        if len(h) < counted:
            history[pid] = [0] * (counted - len(h)) + h

    movement: dict[str, int] = {}
    if len(rank_snapshots) >= 2:
        cur, prev = rank_snapshots[-1], rank_snapshots[-2]
        for pid, rank in cur.items():
            movement[pid] = (prev[pid] - rank) if pid in prev else 0

    names = await player_names(db, org_id, all_pids)
    grade_names = {str(r["grade_id"]): r["grade_name"] for r in rows if r["grade_id"]}
    standings = []
    for pid, c in cumulative.items():
        h = history.get(pid, [])
        weekly = [h[i] - (h[i - 1] if i > 0 else 0) for i in range(len(h))]
        gid = grade_by_pid.get(pid)
        standings.append({
            "player_id": pid, "name": names.get(pid, "Unknown"),
            "points": c["points"], "raw": c["raw"], "counts": c["counts"], "rounds": c["rounds"],
            "grade": grade_names.get(gid) if gid else None,
            "movement": movement.get(pid, 0),
            "form": weekly[-5:], "cumulative": h,
            "round_gain": weekly[-1] if weekly else 0,
        })
    standings.sort(key=lambda s: (-s["points"], -s["raw"], s["name"]))
    for i, s in enumerate(standings):
        s["tied"] = bool(i > 0 and s["points"] == standings[i - 1]["points"]
                         and s["raw"] == standings[i - 1]["raw"])

    last_round = None
    counted_out = [r for r in out_rounds if r["counted"]]
    if counted_out:
        lr = counted_out[-1]
        lr_results = [
            {"player_id": x["player_id"], "name": names.get(x["player_id"], "Unknown"),
             "points": x["points"]}
            for g in lr["games"] for x in g["results"] if x["points"] > 0
        ]
        lr_results.sort(key=lambda x: -x["points"])
        last_round = {
            "label": lr["label"],
            "game": ", ".join(f"v {g['opponent']}" for g in lr["games"]),
            "results": lr_results,
        }

    return {
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
