"""Bring a club's CricketStatz history into BetterCricket.

The club points us at its own public CricketStatz page; this walks every
season, every match and every scorecard behind it, plus the record book
CricketStatz had already computed, and writes it into the same
``manual_games`` tables the scorecard uploader uses — so an imported match
reaches every existing read path (career totals, records, BetterIQ) through
``v_effective_*`` with no reader needing to know where it came from.

Three rules this follows, each of them the codebase's own:

* **Only our own players get ``players`` rows.** A match carries both sides,
  and minting a row for every opponent is the cross-club leak that
  ``purge_foreign_members`` exists to clean up. The opposition half is kept
  verbatim on ``manual_games.extracted_payload``, which is what the match view
  already renders it from.
* **Identity comes from CricketStatz's own player id**, not the printed name.
  Names are abbreviated inconsistently across eras; the id is stable.
* **A re-import corrects, never doubles.** Matches key on
  ``cricketstatz_match_id``, so running it twice updates the same rows.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    Grade,
    ManualBattingInnings,
    ManualBowlerWicket,
    ManualBowlingSpell,
    ManualFallOfWicket,
    ManualFieldingStat,
    ManualGame,
    ManualPartnership,
    Player,
    Season,
)
from app.services import cricketstatz_client as client
from app.services.cricketstatz_awards import classify_note
from app.services.import_ingest import match_players
from app.services.grade_labels import suggest_categories, suggest_category
from app.services.cricketstatz_parse import RECORD_REPORTS, CricketStatzError

logger = logging.getLogger(__name__)

# The longest gap a healthy run can leave between heartbeats is one slow
# request (the client times out at 30s) plus a season probe. Five minutes of
# silence is not a slow import, it is a dead one — the process was redeployed
# or the task was lost.
STALL_AFTER_SECONDS = 300

# uuid5 namespace so a CricketStatz id maps to the same row every run.
_NS = uuid.UUID("6f9a1c2e-5b7d-4e3a-9c81-0d5f2a7b4e60")


def _derived_id(org_id, kind: str, value: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"{org_id}:{kind}:{value}")


# ── seasons ──────────────────────────────────────────────────────────────────

_SEASON_LABEL = re.compile(r"(\d{4})\s*[-/]\s*(\d{2,4})")


def season_year(label: str, value: str) -> Optional[int]:
    """The starting year of a CricketStatz season.

    Its value is the authority ('2025S' is the southern 2025-26); the printed
    label is the fallback.
    """
    m = re.match(r"^(\d{4})S?$", (value or "").strip())
    if m:
        return int(m.group(1))
    m = _SEASON_LABEL.search(label or "")
    return int(m.group(1)) if m else None


def season_name(year: int, southern: bool) -> str:
    """The club-facing name, matching how the rest of the app writes one."""
    if southern:
        return f"Summer {year}/{str(year + 1)[-2:]}"
    return f"Season {year}"


async def resolve_season(db: AsyncSession, org_id, label: str, value: str,
                         cache: dict) -> Optional[Season]:
    """Our season row for a CricketStatz season, reusing one where it exists."""
    year = season_year(label, value)
    if year is None:
        return None
    if year in cache:
        return cache[year]

    existing = (await db.execute(
        select(Season).where(Season.organisation_id == org_id, Season.year == year)
        .order_by(Season.grassroots_id.isnot(None).desc())
    )).scalars().first()
    if existing:
        cache[year] = existing
        return existing

    southern = (value or "").strip().upper().endswith("S")
    season = Season(
        id=_derived_id(org_id, "season", str(year)),
        organisation_id=org_id,
        grassroots_id=None,          # the documented "not from a sync" marker
        name=season_name(year, southern),
        year=year,
    )
    db.add(season)
    await db.flush()
    cache[year] = season
    return season


# ── grades ───────────────────────────────────────────────────────────────────

async def resolve_grade(db: AsyncSession, org_id, season: Season,
                        name: str, cache: dict) -> Optional[Grade]:
    """Our grade row for a CricketStatz division, per season."""
    clean = (name or "").strip()
    if not clean or not season:
        return None
    key = (season.id, clean.lower())
    if key in cache:
        return cache[key]

    existing = (await db.execute(
        select(Grade).where(Grade.season_id == season.id,
                            Grade.name.ilike(clean))
    )).scalars().first()
    if existing:
        cache[key] = existing
        return existing

    # Classified on the way in, the same as every other importer: a grade with
    # no category cannot be told apart by the Grade type filter, so a club's
    # juniors would sit inside its senior careers. Both columns are written —
    # `category` alone loses the second half of a "Girls Under 16".
    grade = Grade(
        id=_derived_id(org_id, "grade", f"{season.id}:{clean.lower()}"),
        season_id=season.id,
        grassroots_id=None,
        name=clean,
        category=suggest_category(clean),
        categories=list(suggest_categories(clean)),
    )
    db.add(grade)
    await db.flush()
    cache[key] = grade
    return grade


# ── players ──────────────────────────────────────────────────────────────────

def _clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


# What a scorer writes when they did not record who it was. Junior cards are
# routinely entered this way — a real Under-9 match came back with every batter
# named "N/A" — and treating that as a person collapses a whole side onto one
# player, which then fails on the one-innings-per-player index.
_PLACEHOLDER_NAMES = {
    "n/a", "na", "n.a.", "-", "--", "?", "unknown", "unsure",
    "tbc", "tba", "not recorded", "no name",
}


def is_placeholder_name(name: str) -> bool:
    """Is this a stand-in rather than somebody's name?"""
    clean = _clean_name(name).lower()
    if not clean:
        return True
    if clean in _PLACEHOLDER_NAMES:
        return True
    # The redaction CA uses for juniors, which these cards carry too.
    return bool(re.fullmatch(r"\*+", clean))


async def _roster(db: AsyncSession, org_id) -> list[tuple[str, str]]:
    """The club's existing players, as the shared matcher wants them."""
    rows = (await db.execute(text("""
        SELECT id, COALESCE(display_name_override, name) FROM players
         WHERE organisation_id = :org
    """), {"org": str(org_id)})).all()
    return [(str(r[0]), r[1] or "") for r in rows]


async def resolve_player(db: AsyncSession, org_id, person: dict,
                         caches: dict) -> Optional[Player]:
    """Our player row for one of OUR players on a CricketStatz card.

    Matched on CricketStatz's own player id first (stable across eras), then
    against the club's EXISTING roster through `import_ingest.match_players` —
    the same pipeline BetterImport, the scorecard reader and Merge Duplicates
    use. An exact-string check is not enough and the difference is not
    cosmetic: a club already holds its players as "Quinsee, Brad" while
    CricketStatz writes "Brad Quinsee", and matching on the raw spelling minted
    a second record for every player the club already had — so its leaderboard
    listed the same person twice, each with half a career.
    """
    source_id = (person or {}).get("source_player_id")
    name = _clean_name((person or {}).get("name", ""))
    # A placeholder is not a person. With no id behind it there is nothing to
    # identify, so the row is left out rather than inventing a player called
    # "N/A" that every unnamed batter in the club would then share. The match
    # itself is still imported, and its full card is kept on the game.
    if not source_id and is_placeholder_name(name):
        return None
    if not name and not source_id:
        return None

    key = source_id or f"name:{name.lower()}"
    if key in caches["players"]:
        return caches["players"][key]

    player: Optional[Player] = None
    if source_id:
        player = (await db.execute(
            select(Player).where(Player.organisation_id == org_id,
                                 Player.cricketstatz_player_id == str(source_id))
        )).scalars().first()

    if player is None and name:
        # The roster is reloaded whenever it has been cleared — a rollback
        # discards any player flushed since the last commit, so a cached list
        # holding them would match against rows that no longer exist.
        if caches.get("roster") is None:
            caches["roster"] = await _roster(db, org_id)
        decision = match_players([name], caches["roster"]).get(name) or {}
        # Only an exact match is taken, which is the matcher's own rule: its
        # 'exact' covers a plain match AND the middle-initial case ("Michael B.
        # White" onto the club's "White, Michael"). Everything below that is
        # left alone deliberately — an initial is not an identity, so "Crosta,
        # T" must not swallow a Torey, a Tim and a Tom, and two of the club's
        # own records sharing a name is the shape of a father and son. Those
        # get their own record and are reported, for Merge Duplicates to settle.
        chosen = decision.get("player_id") if decision.get("status") == "exact" else None
        if not chosen and decision.get("candidates"):
            near = caches.setdefault("near_matches", {})
            near.setdefault(name, [c.get("name") for c in decision["candidates"][:3]])
        if chosen:
            player = (await db.execute(
                select(Player).where(Player.id == uuid.UUID(chosen))
            )).scalars().first()
        if player is not None and source_id and not player.cricketstatz_player_id:
            # Tie the existing record to its CricketStatz identity so later
            # runs match on the id rather than the spelling.
            player.cricketstatz_player_id = str(source_id)

    if player is None:
        player = Player(
            id=_derived_id(org_id, "player", str(source_id or name.lower())),
            organisation_id=org_id,
            name=name or f"Player {source_id}",
            cricketstatz_player_id=str(source_id) if source_id else None,
        )
        db.add(player)
        await db.flush()
        # So the next name in this same import matches the row just created
        # rather than minting a second one beside it.
        if caches.get("roster") is not None:
            caches["roster"].append((str(player.id), player.name))

    caches["players"][key] = player
    return player


# ── which side is ours ───────────────────────────────────────────────────────

def _norm_team(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).strip()


def build_team_matcher(club_name: str, team_names: list[str]):
    """Decide whether a team name on a card is one of the club's own sides.

    The club's team list is the strong signal; its name is the fallback, since
    a side can be entered under a label the team list never carried (a one-off
    "KPCC Summer Smash").
    """
    ours = {_norm_team(t) for t in team_names if t}
    tokens = [t for t in _norm_team(club_name).split() if len(t) > 2]
    # An initialism a club uses for itself ("KPCC" for Keon Park CC).
    initials = "".join(w[0] for w in _norm_team(club_name).split() if w)

    def is_ours(team: str) -> bool:
        norm = _norm_team(team)
        if not norm:
            return False
        if norm in ours:
            return True
        if any(norm.startswith(o) or o.startswith(norm) for o in ours if o):
            return True
        if tokens and all(tok in norm for tok in tokens):
            return True
        if len(initials) >= 3 and norm.split()[0] == initials:
            return True
        return False

    return is_ours


# ── partnerships ─────────────────────────────────────────────────────────────

def derive_partnerships(batters: list[dict], fow: list[dict],
                        innings_runs: Optional[int]) -> list[dict]:
    """Reconstruct each wicket's stand from the fall of wickets.

    Walk the innings: the two openers are at the crease, each fall names who
    went, and the next batter in the order replaces them. The stand's runs are
    the gap between successive scores at the fall — which is why this needs the
    FOW list and cannot be read off the batting card alone.
    """
    order = [b for b in batters if not b.get("did_not_bat")]
    if len(order) < 2 or not fow:
        return []

    def ident(b: dict) -> tuple:
        p = b.get("batter") or {}
        return (p.get("source_player_id"), _clean_name(p.get("name", "")))

    crease = [order[0], order[1]]
    next_in = 2
    previous = 0
    out: list[dict] = []

    for fall in sorted(fow, key=lambda f: f.get("wicket_number") or 0):
        score = fall.get("score_at_fall")
        if score is None:
            continue
        target = (fall.get("batter") or {})
        key = (target.get("source_player_id"), _clean_name(target.get("name", "")))
        going = next((b for b in crease if ident(b) == key), None)
        if going is None:
            # A fall we cannot attribute (an old card with no names) still
            # tells us the stand's runs, so keep the pair as it stands.
            going = crease[0]
        partner = next((b for b in crease if b is not going), None)

        out.append({
            "wicket_number": fall.get("wicket_number"),
            "runs": max(0, score - previous),
            "batter1": going,
            "batter2": partner,
        })
        previous = score

        if next_in < len(order):
            crease = [b for b in crease if b is not going] + [order[next_in]]
            next_in += 1
        else:
            crease = [b for b in crease if b is not going]
        if len(crease) < 2:
            break

    # The unbroken last stand, when the innings closed with wickets in hand.
    if innings_runs is not None and innings_runs > previous and len(crease) == 2:
        out.append({
            "wicket_number": (out[-1]["wicket_number"] if out else 0) + 1,
            "runs": innings_runs - previous,
            "batter1": crease[0],
            "batter2": crease[1],
        })
    return out


# ── writing one match ────────────────────────────────────────────────────────

_FINAL_WORDS = re.compile(
    r"\b(final|semi|elim|qualif|prelim|grand)\b", re.I)




# ── the club's own history, already synced ───────────────────────────────────

async def synced_coverage(db: AsyncSession, org_id) -> dict:
    """Seasons the club ALREADY holds synced games for, and how many.

    A club that syncs from Cricket Australia and then imports its whole
    CricketStatz history ends up holding the same cricket twice — every match
    from the year the sync reaches back to appears once as a synced game and
    once as an imported one, so every career total, average and record board
    counts it twice. Reported live off a real club: 2,324 imported matches
    beside ~3,000 synced ones, and a batter's career reading 14,966 runs where
    CricketStatz has 10,444.

    Keyed on the SEASON's year, so a November and the following March both land
    in the same season the club played.
    """
    rows = (await db.execute(text("""
        SELECT s.year AS year, COUNT(*) AS games
          FROM games g
          JOIN grades gr ON gr.id = g.grade_id
          JOIN seasons s ON s.id = gr.season_id
         WHERE s.organisation_id = :org AND s.year IS NOT NULL
         GROUP BY s.year
    """), {"org": str(org_id)})).mappings().all()
    return {int(r["year"]): int(r["games"]) for r in rows}



async def mark_seasons_superseded(db: AsyncSession, org_id, years) -> int:
    """Say CricketStatz is the record for these seasons of this club.

    A marker on the season, read by `v_effective_games` and
    `v_effective_player_season_stats` (migration 287): the synced side of those
    two views steps aside while the imported matches are rolled up as normal,
    so the season is counted once. Nothing is deleted — the club's Cricket
    Australia data stays, the sync keeps it current underneath, and clearing
    the marker brings it straight back.
    """
    if not years:
        return 0
    result = await db.execute(text("""
        UPDATE seasons SET stats_source = 'cricketstatz'
         WHERE organisation_id = :org AND year = ANY(CAST(:years AS int[]))
           AND stats_source IS DISTINCT FROM 'cricketstatz'
    """), {"org": str(org_id), "years": [int(y) for y in years]})
    return result.rowcount or 0


async def clear_seasons_superseded(db: AsyncSession, org_id, years=None) -> int:
    """Hand the seasons back to the sync. Instant — nothing has to be re-pulled.

    Sets `'playhq'`, NOT NULL, and that is the whole difference. NULL means
    "count what is here", which for a season holding both an imported and a
    synced copy is the double count this exists to prevent — handing a season
    back used to show BOTH, and said so in the confirm. `'playhq'` steps the
    imported side aside instead, so exactly one source is counted either way.

    Only ever applied to a season the sync actually reaches. A season with no
    synced games has nothing to hand back to, and marking it `'playhq'` would
    hide its imported matches and leave the season empty — the "neither source"
    failure reached from the far end.
    """
    sql = ("""UPDATE seasons s SET stats_source = 'playhq'
                WHERE s.organisation_id = :org
                  AND s.stats_source = 'cricketstatz'
                  AND EXISTS (SELECT 1 FROM games g
                                JOIN grades gr ON gr.id = g.grade_id
                               WHERE gr.season_id = s.id)""")
    params = {"org": str(org_id)}
    if years:
        sql += " AND s.year = ANY(CAST(:years AS int[]))"
        params["years"] = [int(y) for y in years]
    return (await db.execute(text(sql), params)).rowcount or 0


async def superseded_years(db: AsyncSession, org_id) -> list:
    rows = (await db.execute(text("""
        SELECT year FROM seasons
         WHERE organisation_id = :org AND stats_source = 'cricketstatz'
           AND year IS NOT NULL
         ORDER BY year
    """), {"org": str(org_id)})).scalars().all()
    return [int(y) for y in rows]


async def hand_edited_games(db: AsyncSession, org_id) -> set:
    """Manual games somebody has created, edited or imported by hand.

    One query for the whole club, so the import's own per-match check costs
    nothing. An edit that was later undone does not count — the club took it
    back, so there is nothing of theirs to protect.
    """
    rows = (await db.execute(text("""
        SELECT DISTINCT target_id FROM manual_edit_logs
         WHERE organisation_id = :org AND target_table = 'manual_games'
           AND undone_at IS NULL
    """), {"org": str(org_id)})).scalars().all()
    return {str(r) for r in rows}


async def import_match(db: AsyncSession, org_id, import_id, card: dict,
                       row: dict, is_ours, caches: dict) -> Optional[str]:
    """Write one CricketStatz match. Returns a note when something was skipped."""
    source_id = str(card.get("source_match_id") or row.get("source_match_id") or "")
    if not source_id:
        return "match with no id"

    played = card.get("date") or row.get("date")
    played_on = None
    if played:
        try:
            played_on = datetime.strptime(played, "%Y-%m-%d").date()
        except ValueError:
            played_on = None

    label = row.get("division") or card.get("division") or ""
    season = await resolve_season(
        db, org_id, caches["season_label"], caches["season_value"], caches["seasons"])
    if season is None:
        return f"{source_id}: no season"
    # ONE SOURCE PER SEASON, DECIDED BY THE DATA RATHER THAN BY A STEP.
    # A season that holds a CricketStatz match is read from CricketStatz — set
    # here, in the SAME transaction as the match itself, so the two can never
    # be out of step. The earlier design worked the overlap out once at the
    # start of the run and marked the seasons afterwards; anything that changed
    # `games` in between (a Full Rebuild finishing, a sync landing) left that
    # snapshot wrong and the club counting both sources with nothing to say so.
    #
    # Unconditional: a season the sync does not reach has no synced games to
    # step aside, so marking it costs nothing and removes the dependence on the
    # overlap being right. An explicit 'playhq' is the club's own decision and
    # is never overwritten.
    # Written on the ORM row rather than as a raw UPDATE: `resolve_season`
    # hands back a Season, the session is already holding it, and a raw
    # statement would leave that instance's own copy stale. A rollback expires
    # it and clears the cache, so the next match resolves and sets it again.
    if season.stats_source is None:
        season.stats_source = "cricketstatz"
        await db.flush()
    grade = await resolve_grade(db, org_id, season, label, caches["grades"])

    home = card.get("home_team") or row.get("home_team") or ""
    away = card.get("away_team") or row.get("away_team") or ""
    our_side = home if is_ours(home) else (away if is_ours(away) else "")
    opposition = away if our_side == home else home
    if not our_side:
        # Both sides read as someone else's — the club's own team list did not
        # cover this fixture. Keep it rather than dropping a real match; the
        # opposition column is what a reader checks.
        opposition = away or home

    existing = (await db.execute(
        select(ManualGame).where(
            ManualGame.organisation_id == org_id,
            ManualGame.cricketstatz_match_id == source_id)
    )).scalars().first()

    # A GAME SOMEBODY HAS WORKED ON BY HAND IS NEVER OVERWRITTEN. Entering or
    # correcting a scorecard costs a club hours, so a re-import refreshing what
    # the import itself wrote must stop at the first row a person has touched —
    # and say so, rather than reverting their work silently. `manual_edit_logs`
    # is the signal because the import writes none of its own: any un-undone
    # row against this game means somebody edited it through Manual Entries.
    if existing is not None and str(existing.id) in caches.get("hand_edited", ()):
        return (f"{source_id}: left as you have it — this match has been edited "
                f"by hand, so the import did not write over it")

    game = existing or ManualGame(
        id=_derived_id(org_id, "match", source_id),
        organisation_id=org_id,
        cricketstatz_match_id=source_id,
    )
    game.season_id = season.id
    game.grade_id = grade.id if grade else None
    game.played_at = played_on
    game.home_team = home or None
    game.away_team = away or None
    game.opposition = opposition or None
    game.venue = card.get("venue") or row.get("venue") or None
    game.result = card.get("result") or row.get("result") or None
    game.winning_team = card.get("winning_team") or row.get("winning_team") or None
    game.is_final = bool(_FINAL_WORDS.search(row.get("round") or card.get("round") or ""))
    game.cricketstatz_import_id = import_id
    game.extracted_payload = card
    if existing is None:
        db.add(game)
    await db.flush()

    # A re-import replaces this match's rows rather than adding a second set.
    for table in ("manual_batting_innings", "manual_bowling_spells",
                  "manual_fielding_stats", "manual_fall_of_wickets",
                  "manual_bowler_wickets", "manual_partnerships"):
        await db.execute(text(f"DELETE FROM {table} WHERE manual_game_id = :g"),
                         {"g": str(game.id)})

    fielding: dict = {}

    for inn in card.get("innings", []):
        batting_team = inn.get("batting_team") or ""
        bowling_team = inn.get("bowling_team") or ""
        seq = inn.get("innings_number") or 1

        if is_ours(batting_team):
            await _write_our_batting(db, org_id, game, inn, seq, caches)
        if is_ours(bowling_team):
            await _write_our_bowling(db, org_id, game, inn, seq, caches, fielding)

    for player_id, tally in fielding.items():
        db.add(ManualFieldingStat(
            manual_game_id=game.id, player_id=player_id,
            catches=tally["catches"], catches_wk=tally["catches_wk"],
            run_outs=tally["run_outs"], stumpings=tally["stumpings"]))

    await db.flush()
    return None


async def _write_our_batting(db, org_id, game, inn, seq, caches) -> None:
    """Our batting card, its fall of wickets and the stands behind it."""
    seen: set = set()
    for b in inn.get("batters", []):
        player = await resolve_player(db, org_id, b.get("batter"), caches)
        if player is None:
            continue
        # One innings row per player: a card can list the same person twice,
        # and the unique index refuses the second. Keep the first.
        if player.id in seen:
            continue
        seen.add(player.id)
        db.add(ManualBattingInnings(
            manual_game_id=game.id, player_id=player.id, innings_number=seq,
            batting_position=b.get("batting_position"),
            runs=b.get("runs") or 0,
            balls=b.get("balls"),
            fours=b.get("fours"),
            sixes=b.get("sixes"),
            strike_rate=b.get("strike_rate"),
            dismissal_type=b.get("dismissal_type"),
            not_out=bool(b.get("not_out")),
            did_not_bat=bool(b.get("did_not_bat")),
        ))

    for fall in inn.get("fall_of_wickets", []):
        person = fall.get("batter") or {}
        player = await resolve_player(db, org_id, person, caches)
        db.add(ManualFallOfWicket(
            manual_game_id=game.id, innings_number=seq,
            wicket_number=fall.get("wicket_number") or 0,
            score_at_fall=fall.get("score_at_fall"),
            overs_at_fall=fall.get("overs_at_fall"),
            player_id=player.id if player else None,
            batter_name=_clean_name(person.get("name", "")) or None,
        ))

    for stand in derive_partnerships(inn.get("batters", []),
                                     inn.get("fall_of_wickets", []),
                                     inn.get("runs")):
        b1 = await resolve_player(db, org_id, (stand["batter1"] or {}).get("batter"),
                                  caches) if stand.get("batter1") else None
        b2 = await resolve_player(db, org_id, (stand["batter2"] or {}).get("batter"),
                                  caches) if stand.get("batter2") else None
        db.add(ManualPartnership(
            manual_game_id=game.id, innings_number=seq,
            wicket_number=stand["wicket_number"] or 0,
            batter1_id=b1.id if b1 else None,
            batter2_id=b2.id if b2 else None,
            runs=stand["runs"], is_club_innings=True,
        ))


async def _write_our_bowling(db, org_id, game, inn, seq, caches, fielding) -> None:
    """Our bowling figures, plus the catches and run outs our fielders took.

    This runs over the innings the OPPOSITION batted, which is where our
    fielding credit lives — the dismissal names the fielder and the bowler.
    """
    for spell in inn.get("bowlers", []):
        player = await resolve_player(db, org_id, spell.get("bowler"), caches)
        if player is None:
            continue
        db.add(ManualBowlingSpell(
            manual_game_id=game.id, player_id=player.id, innings_number=seq,
            overs=spell.get("overs"), maidens=spell.get("maidens"),
            runs=spell.get("runs") or 0, wickets=spell.get("wickets") or 0,
            wides=spell.get("wides"), no_balls=spell.get("no_balls"),
            economy=spell.get("economy"),
        ))

    def credit(player: Player, key: str) -> None:
        tally = fielding.setdefault(player.id, {
            "catches": 0, "catches_wk": 0, "run_outs": 0, "stumpings": 0})
        tally[key] += 1

    for b in inn.get("batters", []):
        kind = b.get("dismissal_type")
        if not kind:
            continue
        bowler = await resolve_player(db, org_id, b.get("bowler"), caches) \
            if b.get("bowler") else None
        fielder = await resolve_player(db, org_id, b.get("fielder"), caches) \
            if b.get("fielder") else None

        if bowler is not None:
            db.add(ManualBowlerWicket(
                manual_game_id=game.id, innings_number=seq,
                bowler_id=bowler.id,
                fielder_id=fielder.id if fielder else None,
                batter_name=_clean_name((b.get("batter") or {}).get("name", "")) or None,
                batter_position=b.get("batting_position"),
                batter_runs=b.get("runs"),
                batter_balls=b.get("balls"),
                dismissal_type=kind,
                caught_behind=b.get("caught_behind"),
            ))

        if fielder is None:
            continue
        if kind == "caught":
            # `catches` is the total and `catches_wk` the keeper's share of it
            # (outfield = catches - catches_wk), so a catch behind counts once
            # in each rather than only in the keeper column.
            credit(fielder, "catches")
            if b.get("caught_behind"):
                credit(fielder, "catches_wk")
        elif kind == "stumped":
            credit(fielder, "stumpings")
        elif kind == "run out":
            credit(fielder, "run_outs")


# ── the record book ──────────────────────────────────────────────────────────

async def import_records(db: AsyncSession, org_id, import_id, club_id: str,
                         on_progress=None) -> int:
    """Capture the club's record book as CricketStatz computed it.

    Kept as its own archive rather than merged into BetterCricket's computed
    records: ours are derived from the scorecards we now hold, theirs cover
    whatever their data covers, and a record book that silently blends two
    sources cannot be checked against either.
    """
    saved = 0
    for idx, (mode, section, title) in enumerate(RECORD_REPORTS):
        try:
            report = await client.fetch_report(club_id, mode)
        except CricketStatzError:
            raise
        except Exception as exc:
            logger.warning("CricketStatz report %s failed: %s", mode, exc)
            continue
        if not report.get("rows"):
            continue
        await db.execute(
            text("""
                INSERT INTO cricketstatz_records
                    (organisation_id, import_id, mode, section, title, scope,
                     headers, rows, row_count, captured_at)
                VALUES (:org, :imp, :mode, :section, :title, :scope,
                        CAST(:headers AS JSONB), CAST(:rows AS JSONB), :n, NOW())
                ON CONFLICT (organisation_id, mode) DO UPDATE SET
                    import_id = EXCLUDED.import_id,
                    section = EXCLUDED.section,
                    title = EXCLUDED.title,
                    scope = EXCLUDED.scope,
                    headers = EXCLUDED.headers,
                    rows = EXCLUDED.rows,
                    row_count = EXCLUDED.row_count,
                    captured_at = NOW()
            """),
            {
                "org": str(org_id), "imp": str(import_id), "mode": mode,
                "section": section, "title": report.get("title") or title,
                "scope": report.get("scope") or None,
                "headers": _json(report.get("headers") or []),
                "rows": _json(report.get("rows") or []),
                "n": len(report.get("rows") or []),
            },
        )
        saved += 1
        if on_progress:
            on_progress(idx + 1, len(RECORD_REPORTS), saved)
    await db.commit()
    return saved



# ── the honour board, out of the players' own notes ──────────────────────────

async def import_notes(db: AsyncSession, org_id, import_id, club_id: str,
                       on_progress=None, note=None) -> dict:
    """Read each player's CricketStatz Notes and file what they say as awards.

    A club that has kept its notes properly has written its honour board there
    — life membership, first-grade caps, trophies, captaincies. Only lines the
    classifier RECOGNISES become achievements: the same block routinely carries
    plain biography ("COLLINGWOOD FC (313 Games)"), and putting a football
    career on a cricket club's honour board is worse than reading nothing.

    Every achievement created carries the import's own id as its
    `import_batch_id`, so undoing the import removes them and the club's Awards
    screen lists the batch alongside its own CSV imports.
    """
    players = (await db.execute(text("""
        SELECT id, COALESCE(display_name_override, name) AS name,
               cricketstatz_player_id
          FROM players
         WHERE organisation_id = :org AND cricketstatz_player_id IS NOT NULL
         ORDER BY name
    """), {"org": str(org_id)})).mappings().all()

    definitions: set[tuple] = set()
    created = 0
    moved = 0
    read = 0
    unread: list[str] = []

    for idx, player in enumerate(players):
        try:
            lines = await client.fetch_player_notes(
                club_id, player["cricketstatz_player_id"])
        except CricketStatzError:
            raise
        except Exception as exc:
            logger.warning("CricketStatz notes for %s failed: %s",
                           player["cricketstatz_player_id"], exc)
            if on_progress:
                on_progress(idx + 1, len(players), created)
            continue
        if lines:
            read += 1
        for line in lines:
            award = classify_note(line)
            if not award:
                # Recorded rather than dropped: a club can see what its notes
                # said that we did not file, instead of wondering.
                if len(unread) < 50:
                    unread.append(line)
                continue
            key = (award["category"], award["subcategory"], award["achievement"])
            if key not in definitions:
                await ensure_award_definition(db, org_id, *key)
                definitions.add(key)
            existing = await _existing_achievement(db, org_id, player["id"], award)
            if existing:
                # A re-import re-stamps its matches and its record boards onto
                # the new import, so an honour it already read has to follow
                # them — otherwise undoing the latest import would leave the
                # honour board behind, pointing at an import that is gone.
                # Only ever a row a CricketStatz import wrote: an honour the
                # club typed in by hand is not this import's to claim, and
                # claiming it would let an undo delete the club's own record.
                if existing["ours"] and str(existing["batch"]) != str(import_id):
                    await db.execute(text("""
                        UPDATE player_achievements SET import_batch_id = :batch
                         WHERE id = :id
                    """), {"batch": str(import_id), "id": existing["id"]})
                    moved += 1
                continue
            await db.execute(text("""
                INSERT INTO player_achievements
                    (org_id, player_id, player_name, season, season_end,
                     category, subcategory, achievement, detail,
                     import_batch_id)
                VALUES (:org, :pid, :pname, :season, :season_end, :category,
                        :subcategory, :achievement, :detail, :batch)
            """), {
                "org": str(org_id), "pid": str(player["id"]),
                "pname": player["name"], "season": award["season"],
                "season_end": award["season_end"], "category": award["category"],
                "subcategory": award["subcategory"],
                "achievement": award["achievement"], "detail": award["detail"],
                "batch": str(import_id),
            })
            created += 1
        if (idx + 1) % 10 == 0:
            await db.commit()
        if on_progress:
            on_progress(idx + 1, len(players), created)

    if created or moved:
        # The Awards screen lists imports out of this table, so the batch row is
        # what makes a notes pass visible — and undoable — beside a CSV upload.
        # Counted from the honours now carrying it rather than from what this
        # pass happened to create: a re-import carries an honour it read the
        # first time, and a batch holding twelve that reports none reads as a
        # mistake.
        held = (await db.execute(text("""
            SELECT COUNT(*) FROM player_achievements
             WHERE org_id = :org AND import_batch_id = :id
        """), {"org": str(org_id), "id": str(import_id)})).scalar() or 0
        await db.execute(text("""
            INSERT INTO achievement_import_batches
                (id, org_id, filename, row_count, created_count, status)
            VALUES (:id, :org, 'CricketStatz player notes', :rows, :made,
                    'imported')
            ON CONFLICT (id) DO UPDATE SET
                row_count = EXCLUDED.row_count,
                created_count = EXCLUDED.created_count,
                status = 'imported'
        """), {"id": str(import_id), "org": str(org_id),
               "rows": read, "made": held})
    await db.commit()
    if note and unread:
        note(f"{len(unread)} note line(s) were not read as awards, "
             f"e.g. {unread[0]!r}. Nothing was guessed at.")
    return {"players_read": read, "awards_created": created,
            "awards_carried": moved, "unread": len(unread)}


async def _existing_achievement(db: AsyncSession, org_id, player_id,
                                award: dict) -> Optional[dict]:
    """Has this player already got this honour, and did an import write it?

    A re-import must not hand somebody a second life membership, and a club may
    have typed the honour in by hand before ever importing. Matched on the
    player, the award and its season — which is what a duplicate IS. `ours`
    says whether the row came from a CricketStatz import of this club's, which
    is what decides whether the row may be re-stamped onto a later one.
    """
    row = (await db.execute(text("""
        SELECT pa.id,
               pa.import_batch_id AS batch,
               EXISTS (SELECT 1 FROM cricketstatz_imports ci
                        WHERE ci.id = pa.import_batch_id
                          AND ci.organisation_id = :org) AS ours
          FROM player_achievements pa
         WHERE pa.org_id = :org AND pa.player_id = :pid
           AND pa.category = :category AND pa.achievement = :achievement
           AND COALESCE(pa.season, '') = COALESCE(:season, '')
         LIMIT 1
    """), {
        "org": str(org_id), "pid": str(player_id),
        "category": award["category"], "achievement": award["achievement"],
        "season": award["season"],
    })).mappings().first()
    return dict(row) if row else None


async def ensure_award_definition(db: AsyncSession, org_id, category,
                                  subcategory, achievement) -> None:
    """Put an award on the club's own catalogue if it is not there already.

    Without this an imported honour exists on a player and nowhere in the list
    the Awards screen offers, so nobody could add a second winner of the same
    trophy without retyping its name.
    """
    exists = (await db.execute(text("""
        SELECT 1 FROM org_award_definitions
         WHERE org_id = :org AND lower(category) = lower(:category)
           AND lower(COALESCE(subcategory, '')) = lower(COALESCE(:sub, ''))
           AND lower(achievement) = lower(:achievement)
         LIMIT 1
    """), {"org": str(org_id), "category": category, "sub": subcategory,
           "achievement": achievement})).scalar()
    if exists:
        return
    await db.execute(text("""
        INSERT INTO org_award_definitions
            (id, org_id, category, subcategory, achievement, sort_order)
        VALUES (gen_random_uuid(), :org, :category, :sub, :achievement,
                COALESCE((SELECT MAX(sort_order) + 1 FROM org_award_definitions
                           WHERE org_id = :org), 1000))
    """), {"org": str(org_id), "category": category, "sub": subcategory,
           "achievement": achievement})



def _json(value) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


# ── inspecting a club before importing it ────────────────────────────────────

async def inspect_club(url: str) -> dict:
    """What a club's site holds, so the club can confirm before anything runs.

    Deliberately cheap: the club page plus one all-time match list. The season
    sweep is the expensive part and belongs to the import itself.
    """
    from app.services.cricketstatz_parse import parse_club_url

    club_id = parse_club_url(url)
    if not club_id:
        raise CricketStatzError(
            "That does not look like a CricketStatz address. Paste the link to "
            "your club's stats page — it carries a club number, like "
            "…/ss/w?mode=104&club=93931",
            kind="bad_url",
        )

    page = await client.fetch_club_page(club_id)
    teams = []
    try:
        teams = await client.fetch_teams(club_id)
    except Exception:  # the team list is a nicety, not a gate
        pass

    all_time = await client.fetch_results(club_id)
    capped = len(all_time) >= 999
    dates = sorted(m["date"] for m in all_time if m.get("date"))

    earliest = dates[0][:4] if dates else None
    latest = dates[-1][:4] if dates else None
    at_least = False
    if capped:
        # The list is the most RECENT 999 matches, so its earliest date says
        # nothing about how far the club goes back — it read 2014 for a club
        # whose history starts in 1953. The all-time record boards carry dates
        # from across the whole history, and a record dated 1954 PROVES there
        # was a season in 1954, so this is a floor rather than a guess. It can
        # understate (a quiet season need not reach a top-100 board), never
        # overstate, and the first pass finds the real answer.
        span = await _span_from_records(club_id)
        if span:
            earliest = str(min(span[0], int(earliest or span[0])))
            latest = str(max(span[1], int(latest or span[1])))
            at_least = True

    return {
        "club_id": club_id,
        "club_name": page["club_name"],
        "seasons_offered": len(page["seasons"]),
        "teams": [t["name"] for t in teams] or [t["name"] for t in page["teams"]],
        "matches_found": len(all_time),
        "truncated": capped,
        "earliest": earliest,
        "latest": latest,
        # True when the span is a floor read off the record boards rather than
        # the exact range, so the screen can say "at least" instead of stating
        # a year it cannot know yet.
        "earliest_at_least": at_least,
        "record_reports": len(RECORD_REPORTS),
    }


# Boards that reach across a club's whole history, so a date on one is proof a
# season existed. Deliberately a handful rather than all 41 — this runs on a
# preview, before the club has committed to anything.
_SPAN_REPORTS = (72, 7, 6, 27, 50)
_YEAR = re.compile(r"\b(19\d{2}|20\d{2})\b")


async def _span_from_records(club_id: str) -> Optional[tuple[int, int]]:
    """The years the club's all-time record boards actually reach."""
    years: set[int] = set()
    for mode in _SPAN_REPORTS:
        try:
            report = await client.fetch_report(club_id, mode)
        except Exception:
            continue
        for row in report.get("rows", []):
            for value in row.get("values", []):
                years.update(int(y) for y in _YEAR.findall(str(value)))
    return (min(years), max(years)) if years else None


# ── working out what there is to pull, before pulling it ─────────────────────

async def plan_seasons(club_id: str, seasons: list[dict], on_progress=None
                       ) -> list[tuple[dict, list[dict]]]:
    """Find which of the site's candidate seasons this club actually played.

    CricketStatz offers every season back to 1860 whatever the club, so the
    dropdown is a list of candidates. Every one is probed — a club's history
    can have gaps, and stopping at the first run of empty years would silently
    truncate it — but the probes run concurrently under the client's own
    semaphore, so 167 candidates cost well under a minute rather than two.

    The season's match rows are kept, so the import that follows re-reads
    nothing: the plan IS the work list, and knowing the real total up front is
    what lets the progress bar mean something.
    """
    done = 0
    found: list[tuple[dict, list[dict]]] = []

    async def probe(season: dict) -> None:
        nonlocal done
        try:
            rows = await client.fetch_results(club_id, season["value"])
        except CricketStatzError:
            raise
        except Exception as exc:
            logger.warning("CricketStatz season %s failed: %s", season["value"], exc)
            rows = []
        done += 1
        if rows:
            found.append((season, rows))
        if on_progress:
            on_progress(done, len(seasons), len(found),
                        sum(len(r) for _, r in found))

    await asyncio.gather(*(probe(s) for s in seasons))
    # Oldest first, so a club watching it sees its history fill forwards.
    found.sort(key=lambda pair: season_year(pair[0]["label"], pair[0]["value"]) or 0)
    return found


def plan_summary(found: list[tuple[dict, list[dict]]]) -> dict:
    """What the plan amounts to, for the screen and the record."""
    years = [season_year(s["label"], s["value"]) for s, _ in found]
    years = [y for y in years if y]
    total = sum(len(rows) for _, rows in found)
    return {
        "seasons": [
            {"label": s["label"], "value": s["value"], "matches": len(rows)}
            for s, rows in found
        ],
        "season_count": len(found),
        "match_count": total,
        "earliest": min(years) if years else None,
        "latest": max(years) if years else None,
        # About a second a match, measured against the live site.
        "estimated_minutes": max(1, round(total * 1.0 / 60)),
    }


# ── the whole import ─────────────────────────────────────────────────────────

async def _set_progress(session_maker, import_id, **fields) -> None:
    import json
    sets, params = [], {"id": str(import_id)}
    for key, value in fields.items():
        if key == "progress":
            sets.append("progress = CAST(:progress AS JSONB)")
            params["progress"] = json.dumps(value, ensure_ascii=False)
        elif key == "stats":
            sets.append("stats = CAST(:stats AS JSONB)")
            params["stats"] = json.dumps(value, ensure_ascii=False)
        else:
            sets.append(f"{key} = :{key}")
            params[key] = value
    # A progress write is also the heartbeat: it is the only thing that tells a
    # long import from a dead one.
    sets.append("updated_at = NOW()")
    async with session_maker() as db:
        await db.execute(text(
            f"UPDATE cricketstatz_imports SET {', '.join(sets)} WHERE id = :id"), params)
        await db.commit()


async def run_import(session_maker, org_id, import_id, club_id: str,
                     synced_years: str = "skip") -> None:
    """Pull the club's whole CricketStatz history. Never raises.

    Runs as a detached background task, so its own session is opened here and
    progress is written as it goes — the screen polls the batch row rather than
    holding a request open for what can be several thousand matches.
    """
    progress = {
        "phase": "starting", "seasons_done": 0, "seasons_total": 0,
        "matches_done": 0, "matches_total": 0, "scorecards": 0,
        "records": 0, "players": 0, "notes": [],
        "notes_done": 0, "notes_total": 0, "awards": 0, "notes_read": 0,
        "skipped_synced_years": [], "replaced_synced_years": [],
        "replaced_done": 0, "synced_years": [],
        "candidates_done": 0, "candidates_total": 0, "current_season": None,
    }

    def note(message: str) -> None:
        if len(progress["notes"]) < 200:
            progress["notes"].append(message)

    try:
        page = await client.fetch_club_page(club_id)
        club_name = page["club_name"]
        teams = []
        try:
            teams = [t["name"] for t in await client.fetch_teams(club_id)]
        except Exception:
            teams = [t["name"] for t in page["teams"]]
        is_ours = build_team_matcher(club_name, teams)

        await _set_progress(session_maker, import_id, club_name=club_name,
                            phase="seasons", progress=progress)

        # Which seasons this club actually played. One all-time pull answers it
        # for most clubs; only a club whose history overflows the report's own
        # 999-row ceiling needs every candidate season probed.
        all_time = await client.fetch_results(club_id)
        seasons: list[dict]
        if len(all_time) < 999:
            years = {m["date"][:4] for m in all_time if m.get("date")}
            seasons = [s for s in page["seasons"]
                       if str(season_year(s["label"], s["value"]) or "") in years
                       or str((season_year(s["label"], s["value"]) or 0) + 1) in years]
        else:
            seasons = page["seasons"]

        progress["seasons_total"] = len(seasons)
        progress["candidates_total"] = len(seasons)
        await _set_progress(session_maker, import_id, progress=progress)

        # ── first pass: what is there, and where ────────────────────────────
        # Probing every candidate season first costs under a minute and buys
        # the real total. Discovering it as we went meant `matches_total` grew
        # with `matches_done`, so a bar drawn against it sat near full from the
        # first season and told a club nothing.
        last_beat = 0.0

        def planning(done, total, found, matches):
            nonlocal last_beat
            progress["candidates_done"] = done
            progress["seasons_total"] = found
            progress["matches_total"] = matches
            now = time.monotonic()
            if now - last_beat > 1.0 or done == total:
                last_beat = now
                asyncio.create_task(_set_progress(
                    session_maker, import_id, progress=dict(progress)))

        plan = await plan_seasons(club_id, seasons, planning)

        # A club that already syncs from Cricket Australia holds those seasons
        # once. Importing them again does not correct anything — it counts the
        # same cricket twice on every career total and every record board — so
        # the years the sync already covers are left out unless the club has
        # asked for them. CricketStatz is for the history the sync cannot
        # reach, and the club is told exactly which years were skipped.
        async with session_maker() as db:
            covered = await synced_coverage(db, org_id)
        overlap = []
        for season, _rows in plan:
            year = season_year(season["label"], season["value"])
            if year is not None and covered.get(year):
                overlap.append(year)
        overlap.sort()

        skipped_years, replaced_years = [], []
        if overlap and synced_years == "skip":
            skipped_years = overlap
            plan = [(sn, rows) for sn, rows in plan
                    if season_year(sn["label"], sn["value"]) not in set(overlap)]
            note(f"{len(skipped_years)} season(s) already covered by your "
                 f"Cricket Australia sync were left out "
                 f"({skipped_years[0]}-{skipped_years[-1]}), so those matches "
                 f"are not counted twice.")
        elif overlap and synced_years == "cricketstatz":
            # The club has said its CricketStatz history is the record for the
            # seasons it also syncs. The seasons are marked AFTER the matches
            # are in, below — marking first would leave the club with neither
            # source showing while the import walked, and a run that failed
            # halfway would leave it that way.
            replaced_years = overlap
            note(f"{len(replaced_years)} season(s) you also sync will read from "
                 f"CricketStatz ({replaced_years[0]}-{replaced_years[-1]}). "
                 f"Your Cricket Australia data is kept and steps aside.")

        progress["skipped_synced_years"] = skipped_years
        progress["replaced_synced_years"] = replaced_years
        progress["synced_years"] = sorted(covered)

        summary = plan_summary(plan)
        progress["seasons_total"] = summary["season_count"]
        progress["matches_total"] = summary["match_count"]
        progress["plan"] = summary
        await _set_progress(session_maker, import_id, phase="planned",
                            progress=progress, stats=summary)

        # ── matches, season by season ───────────────────────────────────────
        # Read once for the whole club: which games a person has already worked
        # on by hand, so a re-import never writes over their scorecard.
        async with session_maker() as db:
            hand_edited = await hand_edited_games(db, org_id)

        progress["phase"] = "matches"
        await _set_progress(session_maker, import_id, phase="matches",
                            progress=progress)
        for s_idx, (season, rows) in enumerate(plan):
            progress["seasons_done"] = s_idx + 1
            progress["current_season"] = season["label"]
            await _set_progress(session_maker, import_id, progress=progress)

            if not rows:
                continue

            caches = {
                "seasons": {}, "grades": {}, "players": {}, "roster": None,
                "near_matches": {}, "hand_edited": hand_edited,
                "season_label": season["label"], "season_value": season["value"],
            }
            async with session_maker() as db:
                for m_idx, row in enumerate(rows):
                    try:
                        card = await client.fetch_scorecard(
                            club_id, row["source_match_id"])
                    except CricketStatzError:
                        raise
                    except Exception as exc:
                        note(f"match {row['source_match_id']}: {exc}")
                        card = {"source_match_id": row["source_match_id"],
                                "innings": []}
                    if card.get("innings"):
                        progress["scorecards"] += 1
                    try:
                        skipped = await import_match(
                            db, org_id, import_id, card, row, is_ours, caches)
                        if skipped:
                            note(skipped)
                        # One match is the unit of work. Committing per match
                        # rather than in batches costs nothing beside the fetch
                        # that precedes it, and means one unreadable match
                        # cannot roll back the ones already done.
                        await db.commit()
                    except Exception as exc:
                        await db.rollback()
                        # A rollback throws away every row flushed since the
                        # last commit — including the season, grade and player
                        # rows resolved for this match. The caches would still
                        # be holding their ids, so the next match would insert
                        # against a season that no longer exists and fail on a
                        # dangling foreign key, and so would every match after
                        # it. Clear them so they are resolved again.
                        caches["seasons"].clear()
                        caches["grades"].clear()
                        caches["players"].clear()
                        caches["roster"] = None
                        note(f"match {row['source_match_id']}: {exc}")
                    progress["matches_done"] += 1

                    if (m_idx + 1) % 5 == 0:
                        await _set_progress(session_maker, import_id,
                                            progress=progress)
            # THIS SEASON IS MARKED THE MOMENT ITS OWN MATCHES ARE IN, not at
            # the end of the run. Marking every season up front would leave the
            # ones not yet walked showing neither source; leaving it all to the
            # end leaves every season already walked counted TWICE for the
            # forty minutes the import takes, which is what a club sees and
            # reports as duplicates on its record board. Per season, after its
            # matches commit, there is no window for either: a season is either
            # still on Cricket Australia or fully across, never both and never
            # neither — and a run that stops halfway leaves exactly that.
            year = season_year(season["label"], season["value"])
            if year is not None and year in set(replaced_years):
                async with session_maker() as db:
                    await mark_seasons_superseded(db, org_id, [year])
                    await db.commit()
                progress["replaced_done"] = (progress.get("replaced_done") or 0) + 1

            async with session_maker() as db:
                progress["players"] = (await db.execute(text("""
                    SELECT COUNT(*) FROM players
                     WHERE organisation_id = :org
                       AND cricketstatz_player_id IS NOT NULL
                """), {"org": str(org_id)})).scalar() or 0
            for new_name, candidates in (caches.get("near_matches") or {}).items():
                note(f"{new_name}: added as a new player — close to "
                     f"{', '.join(candidates)}. Check Merge Duplicates.")
            await _set_progress(session_maker, import_id, progress=progress)

        # Backstop. Each season is marked as its own matches land (above), so
        # by here this normally writes nothing — it exists for a season whose
        # own year could not be read off its label, which would otherwise be
        # imported and then never marked.
        if replaced_years:
            async with session_maker() as db:
                await mark_seasons_superseded(db, org_id, replaced_years)
                await db.commit()

        # ── the record book ─────────────────────────────────────────────────
        progress["phase"] = "records"
        await _set_progress(session_maker, import_id, phase="records",
                            progress=progress)

        def record_progress(done, total, saved):
            progress["records"] = saved
        async with session_maker() as db:
            progress["records"] = await import_records(
                db, org_id, import_id, club_id, record_progress)

        # ── the honour board out of the players' own notes ──────────────────
        progress["phase"] = "notes"
        await _set_progress(session_maker, import_id, phase="notes",
                            progress=progress)

        def notes_progress(done, total, made):
            progress["notes_done"] = done
            progress["notes_total"] = total
            progress["awards"] = made
        async with session_maker() as db:
            try:
                summary_notes = await import_notes(
                    db, org_id, import_id, club_id, notes_progress, note)
                progress["awards"] = summary_notes["awards_created"]
                progress["notes_read"] = summary_notes["players_read"]
            except CricketStatzError:
                raise
            except Exception as exc:
                # An honour board is worth having and is not what the import is
                # for: a failure here must not lose a history already written.
                await db.rollback()
                logger.exception("CricketStatz notes pass failed")
                note(f"player notes could not be read: {exc}")

        progress["phase"] = "done"
        async with session_maker() as db:
            counts = (await db.execute(text("""
                SELECT COUNT(*) FROM manual_games
                 WHERE organisation_id = :org AND cricketstatz_import_id = :imp
            """), {"org": str(org_id), "imp": str(import_id)})).scalar() or 0
            await db.execute(text(
                "UPDATE organisations SET cricketstatz_club_id = :c WHERE id = :o"),
                {"c": club_id, "o": str(org_id)})
            await db.commit()
        progress["matches_imported"] = counts

        await _set_progress(session_maker, import_id, status="complete",
                            phase="done", progress=progress,
                            stats=progress, finished_at=datetime.utcnow())

    except CricketStatzError as exc:
        await _set_progress(session_maker, import_id, status="error",
                            error=str(exc), progress=progress,
                            finished_at=datetime.utcnow())
    except Exception as exc:  # a failed import must report, never vanish
        logger.exception("CricketStatz import failed")
        await _set_progress(session_maker, import_id, status="error",
                            error=f"{type(exc).__name__}: {exc}",
                            progress=progress, finished_at=datetime.utcnow())


async def undo_import(db: AsyncSession, org_id, import_id) -> dict:
    """Remove everything one import wrote.

    Matches cascade to their own batting/bowling/fielding rows. Players and
    seasons are deliberately KEPT: a player is a person, and by the time an
    import is undone they may already carry a photo, a squad or a committee
    role — the same call the stats importer's own undo makes.
    """
    removed = (await db.execute(text("""
        DELETE FROM manual_games
         WHERE organisation_id = :org AND cricketstatz_import_id = :imp
        RETURNING id
    """), {"org": str(org_id), "imp": str(import_id)})).fetchall()
    records = (await db.execute(text("""
        DELETE FROM cricketstatz_records
         WHERE organisation_id = :org AND import_id = :imp
        RETURNING id
    """), {"org": str(org_id), "imp": str(import_id)})).fetchall()
    # The honour board this import read out of the players' notes. Achievements
    # carry the import's own id as their batch, so they go with it.
    awards = (await db.execute(text("""
        DELETE FROM player_achievements
         WHERE org_id = :org AND import_batch_id = :imp
        RETURNING id
    """), {"org": str(org_id), "imp": str(import_id)})).fetchall()
    await db.execute(text("""
        UPDATE achievement_import_batches
           SET status = 'undone', undone_at = NOW()
         WHERE id = :imp AND org_id = :org
    """), {"imp": str(import_id), "org": str(org_id)})
    # Award definitions are deliberately KEPT: a trophy the club now has in its
    # catalogue may already have a second winner typed in by hand, and a
    # catalogue entry holds no claim about anybody.
    await db.execute(text(
        "UPDATE cricketstatz_imports SET undone_at = NOW() WHERE id = :imp"),
        {"imp": str(import_id)})
    # A SEASON LEFT WITH NEITHER SOURCE IS THE ONE STATE THIS MUST NOT LEAVE.
    # Making CricketStatz the record for a season only ever HIDES the synced
    # copy (migration 287) — so undoing the import that replaced it, without
    # taking the marker off, removes the CricketStatz matches AND leaves the
    # club's own Cricket Australia data still hidden. The season then reads
    # empty on every screen with nothing to say why.
    #
    # Cleared per season rather than club-wide: a season still holding an
    # imported match from ANOTHER import is still genuinely read from
    # CricketStatz and keeps its marker. Only a season this undo has just
    # emptied goes back to the sync.
    handed_back = (await db.execute(text("""
        UPDATE seasons s SET stats_source = NULL
         WHERE s.organisation_id = :org
           AND s.stats_source IN ('cricketstatz', 'playhq')
           AND NOT EXISTS (
                 SELECT 1 FROM manual_games mg
                  WHERE mg.season_id = s.id
                    AND mg.cricketstatz_import_id IS NOT NULL)
        RETURNING s.year
    """), {"org": str(org_id)})).scalars().all()
    await db.commit()
    return {"matches_removed": len(removed), "records_removed": len(records),
            "awards_removed": len(awards),
            "seasons_handed_back": sorted(y for y in handed_back if y)}
