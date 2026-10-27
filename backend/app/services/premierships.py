"""Premierships, written from scorecards.

A club that wins a grand final should not have to type the flag in. This reads
the club's own synced games, finds the grand finals its side won, and keeps one
Premiership honour per player who played in each, so the three places a
premiership appears (the player's Honours tab, the club's Premierships page and
the scorecard) are all fed by the one game.

What is stored, and what is not:

* The honour is a normal ``player_achievements`` row (category ``Premiership``,
  subcategory the grade, achievement ``Premiership``). Most of the app reads
  that table directly (yearbooks, website boards, player cards, StatLab), so a
  derived-on-read honour would have needed each of them changed; a real row
  works for all of them. ``auto_created`` marks the rows this module wrote,
  and ``linked_game_id`` points every premiership honour at its scorecard.
* A club's hand-typed work is never deleted or overwritten. The reconcile may
  add rows, may link a hand-typed row to the one grand final it matches, and
  may only REMOVE a row it wrote itself (``auto_created``). A row a person
  edits is flipped to ``auto_created = FALSE`` by the achievements router and
  is theirs from then on. A person who deletes an automatic honour leaves a
  ``premiership_auto_exclusions`` row, so it is not written back.
* A player who asked to be removed (``players.privacy_hidden_at``) gets no automatic honour.
* Nothing is guessed. A grand final with no winner on the card (a draw, a
  no-result, a missing round name) writes nothing and is reported.

``reconcile`` is idempotent and takes an advisory lock, so a sync finishing
while an admin presses the button cannot write a player twice.
"""
from __future__ import annotations

import logging
import re
import uuid
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation, async_session_maker
from app.services import honours
from app.services.club_match import fixture_side
from app.services.grade_labels import grade_alias_map, grade_key, strip_sponsor_suffix

logger = logging.getLogger(__name__)

CATEGORY = honours.PREMIERSHIP_CATEGORY
ACHIEVEMENT = "Premiership"

# Cricket Australia names the decider "Grand Final". A few competitions
# (mostly T20 and one-day cups) call it just "Final". A semi, preliminary or
# qualifying final is a final but not the decider, and "Finals" in the plural
# is a round of several matches, so neither counts.
_GRAND_FINAL_RE = re.compile(r"\bgrand[\s\-]*final", re.I)
_NOT_THE_DECIDER_RE = re.compile(r"semi|prelim|qualif|elimin|minor", re.I)
_BARE_FINAL_RE = re.compile(r"^(the\s+)?final$", re.I)


def is_grand_final_round(round_name: Optional[str]) -> bool:
    name = (round_name or "").strip()
    if not name:
        return False
    if _GRAND_FINAL_RE.search(name):
        return not _NOT_THE_DECIDER_RE.search(name)
    return bool(_BARE_FINAL_RE.match(name))


def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ── reading the grand finals the club won ─────────────────────────────────

async def _own_grade_names(db: AsyncSession, org_id) -> dict[str, str]:
    """{grade_key: display name} from the club's OWN grades, so a merged or
    sponsor-renamed grade reads the way the club's other honours spell it."""
    rows = (await db.execute(text("""
        SELECT gr.name FROM grades gr
        JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = CAST(:org AS UUID)
        ORDER BY s.year DESC NULLS LAST
    """), {"org": str(org_id)})).scalars().all()
    out: dict[str, str] = {}
    for n in rows:
        out.setdefault(grade_key(n), strip_sponsor_suffix(n))
    return out


async def grand_final_wins(db: AsyncSession, club: Organisation) -> tuple[list[dict], list[dict]]:
    """``(wins, unresolved)``.

    A win is a completed grand final one of the club's sides won, with the
    players who played for that side. ``unresolved`` is a grand final the club
    was in where the card names no winner (a draw, a tie, no result): nothing
    is awarded for those, and an admin can add the honour by hand.
    """
    org_id = club.id
    rows = (await db.execute(text("""
        SELECT g.id, g.played_at, g.home_team, g.away_team, g.home_org_id, g.away_org_id,
               g.winning_team, g.round_name, g.status, g.ca_called_off,
               gr.name AS grade_name,
               s.id AS season_id, s.name AS season_name, s.year AS season_year,
               s.organisation_id AS season_org
        FROM games g
        JOIN grades gr ON gr.id = g.grade_id
        JOIN seasons s ON s.id = gr.season_id
        WHERE g.is_final = TRUE
          AND g.round_name IS NOT NULL
          AND (g.home_org_id = CAST(:org AS UUID) OR g.away_org_id = CAST(:org AS UUID))
    """), {"org": str(org_id)})).mappings().all()

    own_names = await _own_grade_names(db, org_id)
    aliases = await grade_alias_map(db, org_id)

    candidates: list[dict] = []
    unresolved: list[dict] = []
    for r in rows:
        if not is_grand_final_round(r["round_name"]):
            continue
        if (r["status"] or "COMPLETED").upper() != "COMPLETED" or r["ca_called_off"]:
            continue
        # Both sides the club's own (an in-house final) has two candidate
        # squads and nothing here to choose between them: left to a person.
        if r["home_org_id"] and r["away_org_id"] and r["home_org_id"] == r["away_org_id"]:
            continue
        side = fixture_side(club, r["home_team"], r["away_team"], r["home_org_id"], r["away_org_id"])
        if side is None:
            continue
        ours = r["home_team"] if side == "home" else r["away_team"]
        theirs = r["away_team"] if side == "home" else r["home_team"]
        won = _norm(r["winning_team"])
        base = {
            "game_id": str(r["id"]), "played_at": r["played_at"],
            "grade_name": r["grade_name"], "opponent": theirs, "our_team": ours,
            "round_name": r["round_name"],
        }
        if not won or won != _norm(ours):
            if not won:
                unresolved.append({**base, "reason": "no winner on the card"})
            continue
        key = grade_key(r["grade_name"])
        key = aliases.get(key, key)
        display = own_names.get(key) or strip_sponsor_suffix(r["grade_name"])
        own_season = r["season_org"] == org_id
        label = honours.season_label(r["season_name"])
        candidates.append({
            **base,
            "grade_key": key,
            "team": display,
            "year": honours.year_of(label, r["season_year"]),
            "season_label": label,
            # An honour recorded from the Awards screen holds the season's id;
            # a season that belongs to another club (a shared fixture) is not
            # one this club can point at, so it is written as its label.
            "season_value": str(r["season_id"]) if own_season else label,
        })

    if not candidates:
        return [], unresolved

    ids = [uuid.UUID(c["game_id"]) for c in candidates]
    app = (await db.execute(text("""
        SELECT a.game_id, a.player_id, a.team_name, a.is_captain,
               COALESCE(p.display_name_override, p.name) AS name
        FROM game_appearances a
        JOIN players p ON p.id = a.player_id
        WHERE a.game_id = ANY(:ids)
          AND p.organisation_id = CAST(:org AS UUID)
          AND p.privacy_hidden_at IS NULL
          AND COALESCE(a.is_reserve, FALSE) = FALSE
    """), {"ids": ids, "org": str(org_id)})).mappings().all()
    by_game: dict[str, list[dict]] = {}
    for a in app:
        by_game.setdefault(str(a["game_id"]), []).append(dict(a))

    wins = []
    for c in candidates:
        mine = by_game.get(c["game_id"], [])
        # team_name is the side a player was named for. Keep that side's
        # players; if the column does not carry our side's name at all, every
        # non-reserve player of ours in the game is the squad.
        named = [a for a in mine if _norm(a["team_name"]) == _norm(c["our_team"])]
        squad = named or mine
        c["players"] = [{
            "player_id": str(a["player_id"]), "name": a["name"],
            "is_captain": bool(a["is_captain"]),
        } for a in squad]
        wins.append(c)
    return wins, unresolved


# ── reconcile ─────────────────────────────────────────────────────────────

async def _existing_rows(db: AsyncSession, org_id) -> list[dict]:
    res = await db.execute(text(f"""
        SELECT pa.id, pa.player_id::text AS player_id, pa.player_name,
               COALESCE(s.name, pa.season) AS season_name, s.year AS season_year,
               pa.subcategory, pa.achievement, pa.detail,
               pa.linked_game_id::text AS linked_game_id, pa.auto_created
        FROM player_achievements pa
        {honours._SEASON_JOIN}
        WHERE pa.org_id = :org AND pa.category = :cat
    """), {"org": str(org_id), "cat": CATEGORY})
    return [dict(r) for r in res.mappings().all()]


def _person(player_id: Optional[str], name: Optional[str]) -> str:
    return honours._person_key(player_id, name)


async def plan(db: AsyncSession, club: Organisation) -> dict:
    """What reconcile would do, as data. Reads only."""
    org_id = club.id
    wins, unresolved = await grand_final_wins(db, club)
    aliases = await grade_alias_map(db, org_id)
    existing = await _existing_rows(db, org_id)
    excluded = {(str(g), str(p)) for g, p in (await db.execute(text(
        "SELECT game_id, player_id FROM premiership_auto_exclusions WHERE org_id = CAST(:org AS UUID)"
    ), {"org": str(org_id)})).all()}

    desired: dict[tuple[str, str], dict] = {}
    for w in wins:
        for p in w["players"]:
            desired[(w["game_id"], p["player_id"])] = {"win": w, "player": p}

    # A grade can win two grand finals in one year (spring and summer comps).
    # A hand-typed row then cannot be matched to either, so it is left alone.
    by_slot: dict[tuple, list[dict]] = {}
    for w in wins:
        by_slot.setdefault((w["year"], w["grade_key"]), []).append(w)

    def row_slot(r: dict) -> tuple:
        key = grade_key(r["subcategory"])
        return (honours.year_of(honours.season_label(r["season_name"]), r["season_year"]),
                aliases.get(key, key))

    out = {"create": [], "link": [], "update_detail": [], "delete": [], "unlink": [],
           "covered": 0, "unresolved": unresolved,
           "wins": len(wins)}

    # 1. Rows that already point at a game.
    covered: set[tuple[str, str]] = set()
    auto_row_for: dict[tuple[str, str], int] = {}
    for r in existing:
        g = r["linked_game_id"]
        if not g or not honours.is_premiership_award(r["achievement"]):
            continue
        pid = r["player_id"]
        d = desired.get((g, pid)) if pid else None
        if d is None:
            (out["delete"] if r["auto_created"] else out["unlink"]).append(r["id"])
            continue
        covered.add((g, pid))
        if r["auto_created"]:
            auto_row_for.setdefault((g, pid), r["id"])
        want = "Captain" if d["player"]["is_captain"] else None
        if r["auto_created"] and (r["detail"] or None) != want:
            out["update_detail"].append({"id": r["id"], "detail": want})

    # 2. Hand-typed flag rows with no link yet: link to the one game they match.
    manual_by_person: dict[tuple, list[dict]] = {}
    for r in existing:
        if r["linked_game_id"] or not honours.is_premiership_award(r["achievement"]):
            continue
        manual_by_person.setdefault((_person(r["player_id"], r["player_name"]), row_slot(r)), []).append(r)

    for (g, pid), d in desired.items():
        w = d["win"]
        slot = (w["year"], w["grade_key"])
        hand = manual_by_person.get((_person(pid, d["player"]["name"]), slot), [])
        if (g, pid) in covered:
            # A club typed the honour in (or imported it) after the automatic one was
            # written: the typed row stands and takes the link, ours goes.
            if hand and len(by_slot[slot]) == 1 and (g, pid) in auto_row_for:
                out["delete"].append(auto_row_for[(g, pid)])
                out["link"].append({"id": hand[0]["id"], "game_id": g})
            continue
        if hand:
            if len(by_slot[slot]) == 1:
                out["link"].append({"id": hand[0]["id"], "game_id": g})
                covered.add((g, pid))
            else:
                out["covered"] += 1  # ambiguous: theirs stands, nothing added
            continue
        if (g, pid) in excluded:
            continue
        out["create"].append({
            "game_id": g, "player_id": pid, "player_name": d["player"]["name"],
            "season": w["season_value"], "subcategory": w["team"],
            "detail": "Captain" if d["player"]["is_captain"] else None,
            "season_label": w["season_label"],
        })
    return out


async def reconcile(db: AsyncSession, org_id, apply: bool = True) -> dict:
    """Bring a club's premiership honours in line with its grand-final wins.

    Commits when ``apply``. Returns counts plus the ``plan``'s lists.
    """
    club = (await db.execute(select(Organisation).where(Organisation.id == org_id))).scalar_one_or_none()
    if club is None:
        return {"error": "club not found"}
    if apply:
        got = (await db.execute(text("SELECT pg_try_advisory_xact_lock(hashtext(:k))"),
                                {"k": f"premierships:{org_id}"})).scalar()
        if not got:
            return {"skipped": "another run is in progress"}

    p = await plan(db, club)
    report = {k: (len(v) if isinstance(v, list) else v) for k, v in p.items() if k != "unresolved"}
    report["unresolved"] = p["unresolved"]
    report["applied"] = bool(apply)
    report["preview"] = {
        "create": p["create"][:200],
        "delete": p["delete"][:200],
    }
    if not apply:
        return report

    org = str(org_id)
    for c in p["create"]:
        await db.execute(text("""
            INSERT INTO player_achievements
                (org_id, player_id, player_name, season, category, subcategory,
                 achievement, detail, linked_game_id, auto_created)
            SELECT CAST(:org AS UUID), CAST(:pid AS UUID), :name, :season, :cat, :sub,
                   :ach, :detail, CAST(:gid AS UUID), TRUE
            WHERE NOT EXISTS (
                SELECT 1 FROM player_achievements x
                WHERE x.org_id = CAST(:org AS UUID) AND x.player_id = CAST(:pid AS UUID)
                  AND x.linked_game_id = CAST(:gid AS UUID) AND x.category = :cat)
        """), {"org": org, "pid": c["player_id"], "name": c["player_name"], "season": c["season"],
               "cat": CATEGORY, "sub": c["subcategory"], "ach": ACHIEVEMENT,
               "detail": c["detail"], "gid": c["game_id"]})
    for l in p["link"]:
        await db.execute(text(
            "UPDATE player_achievements SET linked_game_id = CAST(:g AS UUID) "
            "WHERE id = :id AND org_id = CAST(:org AS UUID) AND linked_game_id IS NULL"),
            {"g": l["game_id"], "id": l["id"], "org": org})
    for u in p["update_detail"]:
        await db.execute(text(
            "UPDATE player_achievements SET detail = :d "
            "WHERE id = :id AND org_id = CAST(:org AS UUID) AND auto_created = TRUE"),
            {"d": u["detail"], "id": u["id"], "org": org})
    # A card that suddenly loses most of what it holds is a damaged read (a club's sides
    # cleared, a half-finished rebuild), not a hundred corrections: remove nothing then.
    auto_total = (await db.execute(text(
        "SELECT COUNT(*) FROM player_achievements "
        "WHERE org_id = CAST(:org AS UUID) AND auto_created = TRUE"), {"org": org})).scalar() or 0
    if p["delete"] and len(p["delete"]) > max(5, auto_total // 2):
        report["delete_blocked"] = len(p["delete"])
        p["delete"] = []
    if p["delete"]:
        # Only what this module wrote: the predicate is the guarantee.
        await db.execute(text(
            "DELETE FROM player_achievements WHERE id = ANY(:ids) "
            "AND org_id = CAST(:org AS UUID) AND auto_created = TRUE"),
            {"ids": p["delete"], "org": org})
    if p["unlink"]:
        await db.execute(text(
            "UPDATE player_achievements SET linked_game_id = NULL "
            "WHERE id = ANY(:ids) AND org_id = CAST(:org AS UUID) AND auto_created = FALSE"),
            {"ids": p["unlink"], "org": org})
    await db.commit()
    return report


async def maybe_reconcile(org_id) -> dict:
    """After a sync: reconcile on its own session. Never raises, because a
    premiership failure must not read as a sync failure."""
    try:
        async with async_session_maker() as db:
            has_any = (await db.execute(text("""
                SELECT 1 FROM games g
                WHERE g.is_final = TRUE AND g.round_name IS NOT NULL
                  AND (g.home_org_id = CAST(:org AS UUID) OR g.away_org_id = CAST(:org AS UUID))
                UNION ALL
                SELECT 1 FROM player_achievements
                WHERE org_id = CAST(:org AS UUID) AND auto_created = TRUE LIMIT 1
            """), {"org": str(org_id)})).first()
            if not has_any:
                return {"ran": False, "reason": "no finals"}
            report = await reconcile(db, org_id, apply=True)
            return {"ran": True, **{k: v for k, v in report.items() if k not in ("preview", "unresolved")}}
    except Exception as e:
        logger.warning("Premierships reconcile failed for %s: %s", org_id, e)
        return {"ran": False, "reason": "error"}


async def exclude_auto_honour(db: AsyncSession, org_id, achievement_id: int) -> None:
    """Called before an automatic honour is deleted: remember that a person
    removed it, so the next reconcile does not write it back."""
    await db.execute(text("""
        INSERT INTO premiership_auto_exclusions (org_id, game_id, player_id)
        SELECT org_id, linked_game_id, player_id FROM player_achievements
        WHERE id = :id AND org_id = CAST(:org AS UUID) AND auto_created = TRUE
          AND linked_game_id IS NOT NULL AND player_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """), {"id": achievement_id, "org": str(org_id)})


async def game_premiership_info(db: AsyncSession, game_id) -> list[dict]:
    """Which clubs recorded a premiership off this game, for the scorecard banner."""
    rows = (await db.execute(text("""
        SELECT pa.org_id::text AS org_id, o.slug, o.name AS club_name,
               MIN(pa.subcategory) AS team,
               MIN(COALESCE(s.name, pa.season)) AS season,
               COUNT(DISTINCT COALESCE(pa.player_id::text, pa.player_name)) AS players
        FROM player_achievements pa
        JOIN organisations o ON o.id = pa.org_id
        {season_join}
        WHERE pa.linked_game_id = CAST(:g AS UUID) AND pa.category = :cat
        GROUP BY pa.org_id, o.slug, o.name
    """.replace("{season_join}", honours._SEASON_JOIN)), {"g": str(game_id), "cat": CATEGORY})).mappings().all()
    return [dict(r) for r in rows]


async def achievement_game_links(db: AsyncSession, org_id) -> dict:
    """``{player_achievements.id: game_id}`` for a club's premiership rows that point at a scorecard."""
    rows = (await db.execute(text(
        "SELECT id, linked_game_id::text FROM player_achievements "
        "WHERE org_id = CAST(:org AS UUID) AND category = :cat AND linked_game_id IS NOT NULL"
    ), {"org": str(org_id), "cat": CATEGORY})).all()
    return {r[0]: r[1] for r in rows}


async def game_cards(db: AsyncSession, club: Organisation, game_ids: list[str]) -> dict[str, dict]:
    """The one-line story of each grand final, as the club saw it: date, opponent, round."""
    if not game_ids:
        return {}
    rows = (await db.execute(text("""
        SELECT id::text AS id, played_at, home_team, away_team, home_org_id, away_org_id, round_name
        FROM games WHERE id = ANY(:ids)
    """), {"ids": [uuid.UUID(g) for g in game_ids]})).mappings().all()
    out = {}
    for r in rows:
        side = fixture_side(club, r["home_team"], r["away_team"], r["home_org_id"], r["away_org_id"])
        theirs = None
        if side:
            theirs = r["away_team"] if side == "home" else r["home_team"]
        out[r["id"]] = {"id": r["id"], "played_at": r["played_at"].isoformat() if r["played_at"] else None,
                        "opponent": theirs, "round_name": r["round_name"]}
    return out
