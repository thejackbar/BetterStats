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
* With ``organisations.hide_juniors`` on, grand finals in junior grades are skipped, and any automatic
  honour already written for one is removed on the next reconcile (it is ours to remove).
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
from app.services import honours, junior_hiding
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
        SELECT g.id, g.grade_id, g.played_at, g.home_team, g.away_team, g.home_org_id, g.away_org_id,
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
    # A club that hides its junior programme from the public site gets no honours written for it:
    # a premiership names every child in the side, and the Premierships page is public.
    hiding = await junior_hiding.resolve(db, org_id, with_players=False)
    hidden_grades = {str(g) for g in hiding.grade_ids} if hiding.active else set()

    candidates: list[dict] = []
    unresolved: list[dict] = []
    for r in rows:
        if not is_grand_final_round(r["round_name"]):
            continue
        if r["grade_id"] is not None and str(r["grade_id"]) in hidden_grades:
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


_FLAG_SUFFIX_RE = re.compile(r"[\s\-\u2013\u2014:]*premierships?$", re.I)


def _label_key(achievement: Optional[str]) -> str:
    """The grade or competition a typed flag names in its AWARD, lowercased: "2nd Grade One Day
    Premiership" -> "2nd grade one day". Applecross types a flag against the team ("1st XI") and names the
    competition in the award, so the subcategory alone says nothing about the grade Cricket Australia calls it."""
    return grade_key(_FLAG_SUFFIX_RE.sub("", (achievement or "").strip()))


def _words_prefix(a: str, b: str) -> bool:
    """a is b, or one is the other followed by more words ("2nd grade" / "2nd grade one day")."""
    if not a or not b:
        return False
    return a == b or a.startswith(b + " ") or b.startswith(a + " ")


async def plan(db: AsyncSession, club: Organisation) -> dict:
    """What reconcile would do, as data. Reads only.

    Matching is per PERSON and season YEAR, never by grade name alone, because clubs type a flag in more than
    one way: against the grade ("F Grade"), or against the team ("1st XI") with the competition in the award
    ("2nd Grade One Day Premiership"). For one person and year:

      * a hand-typed flag whose subcategory or award names the won grade is that win (linked, never doubled);
      * otherwise, when the person has at least as many typed flags that year as won grand finals, the typed
        flags ARE those wins: nothing is added, and an automatic honour already written for one is removed
        (``supersede``), because ours is the duplicate; a 1:1 pair is linked;
      * when they have fewer typed flags than wins and none matches, nothing is guessed (``ambiguous``);
      * with no typed flag that year the win earns the automatic honour.
    """
    org_id = club.id
    wins, unresolved = await grand_final_wins(db, club)
    aliases = await grade_alias_map(db, org_id)
    existing = await _existing_rows(db, org_id)
    excluded = {(str(g), str(p)) for g, p in (await db.execute(text(
        "SELECT game_id, player_id FROM premiership_auto_exclusions WHERE org_id = CAST(:org AS UUID)"
    ), {"org": str(org_id)})).all()}

    def fold(key: str) -> str:
        return aliases.get(key, key)

    desired: dict[tuple[str, str], dict] = {}
    for w in wins:
        for p in w["players"]:
            desired[(w["game_id"], p["player_id"])] = {"win": w, "player": p}

    out = {"create": [], "link": [], "update_detail": [], "delete": [], "supersede": [], "unlink": [],
           "covered": 0, "ambiguous": 0, "unresolved": unresolved, "wins": len(wins)}

    flag_rows = [r for r in existing if honours.is_premiership_award(r["achievement"])]

    # A typed row that names a person but carries no player id is that person by name (the same fallback the
    # profile and the website use), so a link written to it holds on the next run instead of being undone.
    won_games = {w["game_id"] for w in wins}
    by_game_name: dict[tuple[str, str], str] = {}
    for (g, pid), d in desired.items():
        by_game_name[(g, _norm(d["player"]["name"]))] = pid

    # 1. Rows that already point at a game: keep what still holds, drop or unlink what does not.
    typed_linked: set[tuple[str, str]] = set()
    auto_row_for: dict[tuple[str, str], int] = {}
    for r in flag_rows:
        g = r["linked_game_id"]
        if not g:
            continue
        pid = r["player_id"] or by_game_name.get((g, _norm(r["player_name"])))
        d = desired.get((g, pid)) if pid else None
        if d is None:
            if r["auto_created"]:
                out["delete"].append(r["id"])      # ours, and no longer true
            elif g not in won_games:
                out["unlink"].append(r["id"])      # theirs: only let go of it when the game is no longer a win
            # (a person added to the card by hand who is not on the scorecard stays on it)
            continue
        if r["auto_created"]:
            auto_row_for.setdefault((g, pid), r["id"])
            want = "Captain" if d["player"]["is_captain"] else None
            if (r["detail"] or None) != want:
                out["update_detail"].append({"id": r["id"], "detail": want})
        else:
            typed_linked.add((g, pid))

    # 2. Typed, unlinked flags by person and year (a row with no player id is keyed by name).
    typed_open: dict[tuple, list[dict]] = {}
    for r in flag_rows:
        if r["linked_game_id"] or r["auto_created"]:
            continue
        year = honours.year_of(honours.season_label(r["season_name"]), r["season_year"])
        typed_open.setdefault((_person(r["player_id"], r["player_name"]), year), []).append(r)

    def rows_for(pid: str, name: str, year) -> list[dict]:
        return typed_open.get((_person(pid, name), year)) or typed_open.get((_person(None, name), year)) or []

    def row_matches(r: dict, w: dict) -> bool:
        return (_words_prefix(fold(grade_key(r["subcategory"])), w["grade_key"])
                or _words_prefix(fold(_label_key(r["achievement"])), w["grade_key"]))

    by_person: dict[tuple, list[tuple[str, str]]] = {}
    for (g, pid), d in desired.items():
        by_person.setdefault((pid, d["win"]["year"]), []).append((g, pid))

    def cover(item: tuple[str, str], row: Optional[dict]) -> None:
        """This win is the club's typed flag: our row for it goes, the typed one takes the link."""
        if item in auto_row_for:
            out["supersede"].append(auto_row_for[item])
        if row is not None:
            out["link"].append({"id": row["id"], "game_id": item[0]})

    for (pid, year), items in by_person.items():
        name = desired[items[0]]["player"]["name"]
        open_items = []
        for it in items:
            if it in typed_linked:
                cover(it, None)      # a typed row already points here; any automatic twin goes
            else:
                open_items.append(it)
        if not open_items:
            continue
        rows = list(rows_for(pid, name, year))
        if not rows:
            for it in open_items:
                if it in auto_row_for or it in excluded:
                    continue
                d = desired[it]
                out["create"].append({
                    "game_id": it[0], "player_id": pid, "player_name": d["player"]["name"],
                    "season": d["win"]["season_value"], "subcategory": d["win"]["team"],
                    "detail": "Captain" if d["player"]["is_captain"] else None,
                    "season_label": d["win"]["season_label"],
                })
            continue

        # a) a typed flag that names exactly this win's grade, and only this one.
        left = []
        for it in open_items:
            w = desired[it]["win"]
            hits = [r for r in rows if row_matches(r, w)]
            rivals = [o for o in open_items if o != it and hits and row_matches(hits[0], desired[o]["win"])]
            if len(hits) == 1 and not rivals:
                cover(it, hits[0])
                rows.remove(hits[0])
            else:
                left.append(it)
        if not left:
            continue
        # b) what is left: typed flags at least as many as wins are those wins.
        if len(rows) >= len(left):
            only = len(rows) == 1 and len(left) == 1
            for it in left:
                cover(it, rows[0] if only else None)
            if not only:
                out["covered"] += len(left)
        else:
            out["ambiguous"] += len(left)
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
        "supersede": p["supersede"][:200],
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
    if p["supersede"]:
        # Our row replaced by a typed one that says the same thing. Not part of the mass-removal guard: it is
        # not a damaged read, it is the same honour once. The predicate still limits it to rows we wrote.
        await db.execute(text(
            "DELETE FROM player_achievements WHERE id = ANY(:ids) "
            "AND org_id = CAST(:org AS UUID) AND auto_created = TRUE"),
            {"ids": p["supersede"], "org": org})
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


# ── the squad editor ──────────────────────────────────────────────────────

# What an admin can mark on a card. A 12th or 13th man did not play, so the role row alone puts them on the
# card; Player of the Match is only for somebody already in the squad.
SQUAD_ROLES = {"player of the match": "Player of the Match", "12th man": "12th Man", "13th man": "13th Man"}
NON_PLAYING_ROLES = {"12th Man", "13th Man"}


class SquadEditError(ValueError):
    """Something an admin asked for that this card cannot do. The message is shown to them."""


async def edit_squad(db: AsyncSession, club: Organisation, *, game_id, action: str, player_id,
                     role: Optional[str] = None, on: bool = True) -> dict:
    """Change who is on one premiership card (a grand final the club won) and what each person did.

    Every change is a row in ``player_achievements`` linked to the game, so the card, the profile, the
    yearbook and the website all read it the way they read anything else. Role rows are the club's own
    (``auto_created`` stays FALSE), so a later sync never removes them. Commits.

    action ``role``    mark or unmark a role on a player already on the card
           ``add``     put a player on the card: with a 12th/13th Man role they did not play; with no role
                       they played and the sheet missed them
           ``remove``  take a player off: their automatic honour is remembered as removed so the next sync
                       does not write it back, and any roles go with it
    """
    org = str(club.id)
    gid, pid = str(game_id), str(player_id)
    flag = None
    for r in (await db.execute(text("""
        SELECT id, season, subcategory, achievement, auto_created FROM player_achievements
        WHERE org_id = CAST(:org AS UUID) AND linked_game_id = CAST(:g AS UUID) AND category = :cat
        ORDER BY auto_created DESC, id"""), {"org": org, "g": gid, "cat": CATEGORY})).mappings().all():
        if honours.is_premiership_award(r["achievement"]):
            flag = r
            break
    if flag is None:
        raise SquadEditError("This game is not one of the club's premiership cards.")
    player = (await db.execute(text(
        "SELECT COALESCE(display_name_override, name) AS name, organisation_id FROM players WHERE id = CAST(:p AS UUID)"
    ), {"p": pid})).mappings().first()
    if player is None or str(player["organisation_id"]) != org:
        raise SquadEditError("That player is not on this club's roster.")

    mine = (await db.execute(text("""
        SELECT id, achievement, auto_created FROM player_achievements
        WHERE org_id = CAST(:org AS UUID) AND linked_game_id = CAST(:g AS UUID) AND category = :cat
          AND player_id = CAST(:p AS UUID)"""), {"org": org, "g": gid, "cat": CATEGORY, "p": pid})).mappings().all()
    has_flag = any(honours.is_premiership_award(r["achievement"]) for r in mine)
    role_name = SQUAD_ROLES.get((role or "").strip().lower()) if role else None
    if role and role_name is None:
        raise SquadEditError("Choose Player of the Match, 12th Man or 13th Man.")

    async def put(achievement: str) -> None:
        await db.execute(text("""
            INSERT INTO player_achievements (org_id, player_id, player_name, season, category, subcategory,
                                             achievement, linked_game_id, auto_created)
            SELECT CAST(:org AS UUID), CAST(:p AS UUID), :name, :season, :cat, :sub, :ach, CAST(:g AS UUID), FALSE
            WHERE NOT EXISTS (SELECT 1 FROM player_achievements x
                              WHERE x.org_id = CAST(:org AS UUID) AND x.player_id = CAST(:p AS UUID)
                                AND x.linked_game_id = CAST(:g AS UUID) AND x.category = :cat
                                AND lower(x.achievement) = lower(:ach))"""),
                         {"org": org, "p": pid, "name": player["name"], "season": flag["season"], "cat": CATEGORY,
                          "sub": flag["subcategory"], "ach": achievement, "g": gid})

    if action == "role":
        if role_name is None:
            raise SquadEditError("Choose a role.")
        in_squad = bool(mine)
        if on:
            if role_name not in NON_PLAYING_ROLES and not has_flag:
                raise SquadEditError("Player of the Match goes to somebody who played: add them to the squad first.")
            if not in_squad and role_name not in NON_PLAYING_ROLES:
                raise SquadEditError("That player is not on this card.")
            await put(role_name)
        else:
            await db.execute(text("""
                DELETE FROM player_achievements
                WHERE org_id = CAST(:org AS UUID) AND linked_game_id = CAST(:g AS UUID) AND category = :cat
                  AND player_id = CAST(:p AS UUID) AND lower(achievement) = lower(:ach)"""),
                             {"org": org, "g": gid, "cat": CATEGORY, "p": pid, "ach": role_name})
    elif action == "add":
        if role_name in NON_PLAYING_ROLES:
            await put(role_name)
        else:
            if has_flag:
                raise SquadEditError("That player is already on this card.")
            await put(ACHIEVEMENT)
            if role_name:
                await put(role_name)
    elif action == "remove":
        if not mine:
            raise SquadEditError("That player is not on this card.")
        if any(r["auto_created"] for r in mine):
            await db.execute(text("""
                INSERT INTO premiership_auto_exclusions (org_id, game_id, player_id)
                VALUES (CAST(:org AS UUID), CAST(:g AS UUID), CAST(:p AS UUID)) ON CONFLICT DO NOTHING"""),
                             {"org": org, "g": gid, "p": pid})
        await db.execute(text("""
            DELETE FROM player_achievements
            WHERE org_id = CAST(:org AS UUID) AND linked_game_id = CAST(:g AS UUID) AND category = :cat
              AND player_id = CAST(:p AS UUID)"""), {"org": org, "g": gid, "cat": CATEGORY, "p": pid})
    else:
        raise SquadEditError("Unknown change.")
    await db.commit()
    return {"ok": True}
