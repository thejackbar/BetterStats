"""Find the premierships a club has won, and write them to the honour board.

A candidate is a game whose round name says it was a decider (see
``services/finals.py``) and which our club won. The XI comes from
``game_appearances``, which the sync only ever writes for our own players, and
the captain comes off the same row — so an approved premiership lands as the
same shape a hand-typed one does: ``Premiership > <grade> > Premiership``, with
the skipper marked in ``detail``.

**Candidates are derived on read, never stored.** Only the admin's decision is
kept (``premiership_detections``). A club that corrects a round name, re-syncs
a result or merges two players gets a restated list rather than a stale row
describing a game that no longer looks that way.

Three things this deliberately cannot do, all of which is why an approval step
exists rather than the sync writing straight to the honour board:

* **A flag won without winning the match.** A drawn or washed-out final goes to
  the minor premier. The scorecard carries no winner, so there is nothing to
  detect, and the club adds it from the Awards screen as it always has.
* **The squad beyond the XI.** The twelfth man, the thirteenth, someone who
  broke a finger in the prelim. Game data knows who took the field and cannot
  know who else earned a medal, which is what the ``12th Man`` and ``13th Man``
  entries in the award vocabulary are for.
* **A round label that is genuinely ambiguous.** Some associations call a semi
  "Final". Those arrive flagged for review rather than silently approved.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import finals

logger = logging.getLogger(__name__)

STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_IGNORED = "ignored"

CATEGORY = "Premiership"
ACHIEVEMENT = "Premiership"
CAPTAIN_DETAIL = "Captain"


# ── Candidate discovery ────────────────────────────────────────────────────

# Every finals game under one of OUR grades, with our own side's team name
# pulled from our players' appearance rows. Ownership is by the grade's season
# (grades are per-club — uuid5 on a cross-club collision), which is what keeps
# a shared fixture between two synced clubs from being read from both sides.
_CANDIDATE_SQL = """
    SELECT
        g.id                                        AS game_id,
        g.played_at,
        g.round_name,
        g.home_team,
        g.away_team,
        g.winning_team,
        g.home_org_id,
        g.away_org_id,
        g.result,
        gr.id                                       AS grade_id,
        COALESCE(am.canonical_name, gr.name)        AS grade_name,
        s.id                                        AS season_id,
        s.name                                      AS season_name,
        (
            SELECT ga.team_name
              FROM game_appearances ga
              JOIN players p
                ON p.id = ga.player_id
               AND p.organisation_id = CAST(:org_id AS UUID)
             WHERE ga.game_id = g.id
               AND ga.team_name IS NOT NULL
             LIMIT 1
        )                                           AS our_team_name,
        (
            SELECT COUNT(*)
              FROM game_appearances ga
              JOIN players p
                ON p.id = ga.player_id
               AND p.organisation_id = CAST(:org_id AS UUID)
             WHERE ga.game_id = g.id
        )                                           AS appearance_count
    FROM games g
    JOIN grades gr  ON gr.id = g.grade_id
    JOIN seasons s  ON s.id = gr.season_id
    LEFT JOIN grade_merge_logs am
           ON am.org_id = s.organisation_id
          AND am.alias_name = gr.name
          AND am.undone_at IS NULL
    WHERE s.organisation_id = CAST(:org_id AS UUID)
      AND g.round_name IS NOT NULL
      AND g.round_name <> ''
"""


def _decide_outcome(row: Any) -> tuple[bool, str]:
    """Did WE win this game, and how sure are we?

    Never matches the club's NAME against ``home_team``/``away_team`` — that
    is the bug ``aggregations._club_results`` documents, which zeroed every
    game for clubs like "Bayswater-Postels" whose CA-recorded team text does
    not contain the org's first name-token. Three tiers instead, strongest
    first:

    1. ``home_org_id``/``away_org_id`` (migration 167) say which side we were,
       and ``winning_team`` says which side won. Definitive.
    2. Our own players' ``game_appearances.team_name`` is what OUR side was
       called in this match, straight from the scorecard. Comparing that to
       ``winning_team`` is per-game evidence, not a guess about the club.
    3. ``games.result``, which is relative to whichever club synced the row
       first — right for a game only we synced, unreliable for a shared one.
       Reported as weak so the screen can say so.
    """
    winner = (row["winning_team"] or "").strip()
    if not winner:
        # A drawn or washed-out final. The flag may still be ours on higher
        # position, but nothing in the scorecard says so — see module docstring.
        return False, "no_winner"

    org_home = row["home_org_id"] is not None
    org_away = row["away_org_id"] is not None
    if org_home or org_away:
        ours = (row["home_team"] or "") if org_home else (row["away_team"] or "")
        return (winner == ours.strip()), "definitive"

    our_team = (row["our_team_name"] or "").strip()
    if our_team:
        return (winner == our_team), "appearance"

    return ((row["result"] or "").upper() == "WIN"), "weak"


async def _players_for_game(db: AsyncSession, org_id: str, game_id) -> list[dict]:
    """Our XI for one game.

    The ``players.organisation_id`` join is mandatory, not tidiness: a fixture
    between two both-synced clubs is ONE ``games`` row carrying BOTH clubs'
    appearance rows, so reading appearances by game alone would hand a
    premiership to the opposition.
    """
    rows = (await db.execute(
        text("""
            SELECT ga.player_id,
                   COALESCE(p.display_name_override, p.name) AS name,
                   ga.is_captain,
                   ga.is_wicket_keeper
              FROM game_appearances ga
              JOIN players p
                ON p.id = ga.player_id
               AND p.organisation_id = CAST(:org_id AS UUID)
             WHERE ga.game_id = :game_id
             ORDER BY ga.is_captain DESC, name
        """),
        {"org_id": org_id, "game_id": game_id},
    )).mappings().all()
    return [
        {
            "player_id": str(r["player_id"]),
            "name": r["name"],
            "is_captain": bool(r["is_captain"]),
            "is_wicket_keeper": bool(r["is_wicket_keeper"]),
        }
        for r in rows
    ]


async def _decisions(db: AsyncSession, org_id: str) -> dict[str, dict]:
    rows = (await db.execute(
        text("""
            SELECT game_id, status, decided_at, created_achievement_ids
              FROM premiership_detections
             WHERE organisation_id = CAST(:org_id AS UUID)
        """),
        {"org_id": org_id},
    )).mappings().all()
    return {str(r["game_id"]): dict(r) for r in rows}


async def list_candidates(
    db: AsyncSession,
    org_id: str,
    status: str = STATUS_PENDING,
    include_players: bool = True,
) -> list[dict]:
    """Every detected premiership for a club, newest first.

    ``status`` filters to pending / approved / ignored, or 'all'.
    """
    rows = (await db.execute(text(_CANDIDATE_SQL), {"org_id": org_id})).mappings().all()
    decisions = await _decisions(db, org_id)

    out: list[dict] = []
    for row in rows:
        kind = finals.classify_round(row["round_name"])
        if not finals.is_premiership_round(kind):
            continue
        won, basis = _decide_outcome(row)
        if not won:
            continue
        if not row["appearance_count"]:
            # We hold no XI for this game, so there is nobody to award. Almost
            # always a game whose scorecard has not synced yet; listing it
            # would offer an approve button that could do nothing.
            continue

        gid = str(row["game_id"])
        decided = decisions.get(gid)
        row_status = decided["status"] if decided else STATUS_PENDING
        if status != "all" and row_status != status:
            continue

        opponent = (
            row["away_team"] if (row["winning_team"] or "").strip() == (row["home_team"] or "").strip()
            else row["home_team"]
        )
        entry = {
            "game_id": gid,
            "played_at": row["played_at"].isoformat() if row["played_at"] else None,
            "round_name": row["round_name"],
            "round_kind": kind,
            "round_label": finals.label(kind),
            "confidence": finals.confidence(kind),
            "outcome_basis": basis,
            "grade_id": str(row["grade_id"]) if row["grade_id"] else None,
            "grade_name": row["grade_name"],
            "season_id": str(row["season_id"]) if row["season_id"] else None,
            "season_name": row["season_name"],
            "opponent": opponent,
            "winning_team": row["winning_team"],
            "status": row_status,
            "decided_at": decided["decided_at"].isoformat() if decided and decided["decided_at"] else None,
            "awards_created": len(decided["created_achievement_ids"]) if decided else 0,
            "player_count": row["appearance_count"],
        }
        if include_players:
            entry["players"] = await _players_for_game(db, org_id, row["game_id"])
        out.append(entry)

    out.sort(key=lambda e: (e["played_at"] or "", e["grade_name"] or ""), reverse=True)
    return out


async def counts_by_status(db: AsyncSession, org_id: str) -> dict[str, int]:
    """How many candidates sit in each state. Used for the nav badge."""
    everything = await list_candidates(db, org_id, status="all", include_players=False)
    out = {STATUS_PENDING: 0, STATUS_APPROVED: 0, STATUS_IGNORED: 0}
    for e in everything:
        out[e["status"]] = out.get(e["status"], 0) + 1
    return out


async def get_candidate(db: AsyncSession, org_id: str, game_id: str) -> dict | None:
    for e in await list_candidates(db, org_id, status="all"):
        if e["game_id"] == str(game_id):
            return e
    return None


# ── Decisions ──────────────────────────────────────────────────────────────

async def _already_awarded(
    db: AsyncSession, org_id: str, player_id: str, season_id: str,
    season_name: str | None, grade_name: str,
) -> bool:
    """Does this player already hold this premiership?

    Deliberately NOT ``achievements._is_duplicate``: that helper does not
    compare ``subcategory``, so a player who won the 1st Grade and the T20 in
    one season would have the second flag read as a duplicate of the first.
    The grade is exactly what separates them here, so it has to be in the test.

    ``season`` is free text holding either the season's id (what the Awards
    screen writes) or its name (what an import writes), so both are checked.
    """
    row = (await db.execute(
        text("""
            SELECT 1
              FROM player_achievements
             WHERE org_id = CAST(:org_id AS UUID)
               AND player_id = CAST(:player_id AS UUID)
               AND LOWER(TRIM(category)) = LOWER(:category)
               AND LOWER(TRIM(achievement)) = LOWER(:achievement)
               AND LOWER(TRIM(COALESCE(subcategory, ''))) = LOWER(:subcategory)
               AND (season = :season_id OR (:season_name <> '' AND season = :season_name))
             LIMIT 1
        """),
        {
            "org_id": org_id, "player_id": player_id,
            "category": CATEGORY, "achievement": ACHIEVEMENT,
            "subcategory": grade_name or "",
            "season_id": season_id, "season_name": season_name or "",
        },
    )).first()
    return row is not None


async def approve(
    db: AsyncSession,
    org_id: str,
    game_id: str,
    user_id: str | None = None,
    player_ids: list[str] | None = None,
) -> dict:
    """Write the premiership to the honour board and record the decision.

    ``player_ids`` narrows the XI when an admin unticks someone. Passing None
    means everyone who took the field.
    """
    candidate = await get_candidate(db, org_id, game_id)
    if candidate is None:
        raise ValueError("not_a_candidate")
    if candidate["status"] == STATUS_APPROVED:
        return {"already": True, **candidate}

    wanted = set(player_ids) if player_ids is not None else None
    created: list[int] = []
    skipped = 0

    for p in candidate["players"]:
        if wanted is not None and p["player_id"] not in wanted:
            continue
        if await _already_awarded(
            db, org_id, p["player_id"], candidate["season_id"],
            candidate["season_name"], candidate["grade_name"],
        ):
            skipped += 1
            continue
        row = (await db.execute(
            text("""
                INSERT INTO player_achievements
                    (org_id, player_id, player_name, season, category,
                     subcategory, achievement, detail)
                VALUES
                    (CAST(:org_id AS UUID), CAST(:player_id AS UUID), :player_name,
                     :season, :category, :subcategory, :achievement, :detail)
                RETURNING id
            """),
            {
                "org_id": org_id,
                "player_id": p["player_id"],
                "player_name": p["name"],
                # The season ID, matching what the Awards screen writes — the
                # achievements read COALESCEs it back to the season's name.
                "season": candidate["season_id"],
                "category": CATEGORY,
                "subcategory": candidate["grade_name"],
                "achievement": ACHIEVEMENT,
                "detail": CAPTAIN_DETAIL if p["is_captain"] else None,
            },
        )).first()
        if row:
            created.append(int(row[0]))

    await _record_decision(db, org_id, game_id, STATUS_APPROVED, user_id, created)
    await db.commit()
    logger.info(
        "Premiership approved: org=%s game=%s awards=%d skipped=%d",
        org_id, game_id, len(created), skipped,
    )
    return {"status": STATUS_APPROVED, "awards_created": len(created), "already_held": skipped}


async def ignore(db: AsyncSession, org_id: str, game_id: str, user_id: str | None = None) -> dict:
    """Dismiss a candidate. Writes nothing to the honour board."""
    candidate = await get_candidate(db, org_id, game_id)
    if candidate is None:
        raise ValueError("not_a_candidate")
    if candidate["status"] == STATUS_APPROVED:
        raise ValueError("already_approved")
    await _record_decision(db, org_id, game_id, STATUS_IGNORED, user_id, [])
    await db.commit()
    return {"status": STATUS_IGNORED}


async def reset(db: AsyncSession, org_id: str, game_id: str) -> dict:
    """Put a decided candidate back to pending.

    Undoing an approval removes exactly the achievements that approval wrote —
    the ids it recorded — so an award an admin added by hand for the same
    game, or one carried in from a spreadsheet import, is left alone.
    """
    decided = (await _decisions(db, org_id)).get(str(game_id))
    if decided is None:
        return {"status": STATUS_PENDING, "awards_removed": 0}

    ids = [int(i) for i in (decided["created_achievement_ids"] or [])]
    removed = 0
    if ids:
        result = await db.execute(
            text("""
                DELETE FROM player_achievements
                 WHERE org_id = CAST(:org_id AS UUID)
                   AND id = ANY(:ids)
            """),
            {"org_id": org_id, "ids": ids},
        )
        removed = result.rowcount or 0

    await db.execute(
        text("""
            DELETE FROM premiership_detections
             WHERE organisation_id = CAST(:org_id AS UUID)
               AND game_id = :game_id
        """),
        {"org_id": org_id, "game_id": game_id},
    )
    await db.commit()
    return {"status": STATUS_PENDING, "awards_removed": removed}


async def _record_decision(
    db: AsyncSession, org_id: str, game_id: str, status: str,
    user_id: str | None, achievement_ids: list[int],
) -> None:
    await db.execute(
        text("""
            INSERT INTO premiership_detections
                (id, organisation_id, game_id, status, decided_at,
                 decided_by_user_id, created_achievement_ids)
            VALUES
                (:id, CAST(:org_id AS UUID), :game_id, :status, NOW(),
                 :user_id, CAST(:ids AS JSONB))
            ON CONFLICT (organisation_id, game_id) DO UPDATE
               SET status                  = EXCLUDED.status,
                   decided_at              = NOW(),
                   decided_by_user_id      = EXCLUDED.decided_by_user_id,
                   created_achievement_ids = EXCLUDED.created_achievement_ids
        """),
        {
            "id": str(uuid.uuid4()),
            "org_id": org_id,
            "game_id": game_id,
            "status": status,
            "user_id": user_id,
            "ids": json.dumps(achievement_ids),
        },
    )
