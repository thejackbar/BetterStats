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

    grade = Grade(
        id=_derived_id(org_id, "grade", f"{season.id}:{clean.lower()}"),
        season_id=season.id,
        name=clean,
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


async def resolve_player(db: AsyncSession, org_id, person: dict,
                         cache: dict) -> Optional[Player]:
    """Our player row for one of OUR players on a CricketStatz card.

    Matched on CricketStatz's own player id first (stable across eras), then
    on an exact name already in the club, before a new row is created.
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
    if key in cache:
        return cache[key]

    player: Optional[Player] = None
    if source_id:
        player = (await db.execute(
            select(Player).where(Player.organisation_id == org_id,
                                 Player.cricketstatz_player_id == str(source_id))
        )).scalars().first()

    if player is None and name:
        player = (await db.execute(
            select(Player).where(Player.organisation_id == org_id,
                                 Player.name.ilike(name))
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

    cache[key] = player
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
        player = await resolve_player(db, org_id, b.get("batter"), caches["players"])
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
        player = await resolve_player(db, org_id, person, caches["players"])
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
                                  caches["players"]) if stand.get("batter1") else None
        b2 = await resolve_player(db, org_id, (stand["batter2"] or {}).get("batter"),
                                  caches["players"]) if stand.get("batter2") else None
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
        player = await resolve_player(db, org_id, spell.get("bowler"), caches["players"])
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
        bowler = await resolve_player(db, org_id, b.get("bowler"), caches["players"]) \
            if b.get("bowler") else None
        fielder = await resolve_player(db, org_id, b.get("fielder"), caches["players"]) \
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

    return {
        "club_id": club_id,
        "club_name": page["club_name"],
        "seasons_offered": len(page["seasons"]),
        "teams": [t["name"] for t in teams] or [t["name"] for t in page["teams"]],
        "matches_found": len(all_time),
        "truncated": capped,
        "earliest": dates[0] if dates else None,
        "latest": dates[-1] if dates else None,
        "record_reports": len(RECORD_REPORTS),
    }


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


async def run_import(session_maker, org_id, import_id, club_id: str) -> None:
    """Pull the club's whole CricketStatz history. Never raises.

    Runs as a detached background task, so its own session is opened here and
    progress is written as it goes — the screen polls the batch row rather than
    holding a request open for what can be several thousand matches.
    """
    progress = {
        "phase": "starting", "seasons_done": 0, "seasons_total": 0,
        "matches_done": 0, "matches_total": 0, "scorecards": 0,
        "records": 0, "players": 0, "notes": [],
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
        summary = plan_summary(plan)
        progress["seasons_total"] = summary["season_count"]
        progress["matches_total"] = summary["match_count"]
        progress["plan"] = summary
        await _set_progress(session_maker, import_id, phase="planned",
                            progress=progress, stats=summary)

        # ── matches, season by season ───────────────────────────────────────
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
                "seasons": {}, "grades": {}, "players": {},
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
                        note(f"match {row['source_match_id']}: {exc}")
                    progress["matches_done"] += 1

                    if (m_idx + 1) % 5 == 0:
                        await _set_progress(session_maker, import_id,
                                            progress=progress)
            async with session_maker() as db:
                progress["players"] = (await db.execute(text("""
                    SELECT COUNT(*) FROM players
                     WHERE organisation_id = :org
                       AND cricketstatz_player_id IS NOT NULL
                """), {"org": str(org_id)})).scalar() or 0
            await _set_progress(session_maker, import_id, progress=progress)

        # ── the record book ─────────────────────────────────────────────────
        progress["phase"] = "records"
        await _set_progress(session_maker, import_id, phase="records",
                            progress=progress)

        def record_progress(done, total, saved):
            progress["records"] = saved
        async with session_maker() as db:
            progress["records"] = await import_records(
                db, org_id, import_id, club_id, record_progress)

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
    await db.execute(text(
        "UPDATE cricketstatz_imports SET undone_at = NOW() WHERE id = :imp"),
        {"imp": str(import_id)})
    await db.commit()
    return {"matches_removed": len(removed), "records_removed": len(records)}
