"""Hiding a club's junior programme from its PUBLIC Stats (migration 315).

Some clubs field juniors under the same Cricket Australia club id as their
seniors and want the two kept apart on the public site: Kalamunda's juniors
are to disappear from the seniors' Stats entirely. Senior and junior cricket
are run by different associations, so the association (the club's own
"competition", seeded one per association) is what tells them apart.

THE RULE
--------
With ``organisations.hide_juniors`` on, and for a PUBLIC viewer only:

  * a **junior grade** is a grade in a competition tagged junior. Every game
    in one is dropped from public fixtures, results, scorecards and ladders,
    and every figure that reads per-game rows is scoped to leave it out;
  * a **junior-only player** is someone whose only cricket is in junior
    grades. They are hidden from the roster, search, profile and boards;
  * a player who has played ANY senior game is shown, with senior figures
    only (the junior games are out of every scoped figure).

A signed-in club admin, or Better staff, still sees the club whole, the same
escape ``players.is_public`` and ``grades.is_public`` already use.

FAIL OPEN, ALWAYS
-----------------
Anything we cannot place is NOT junior, the rule ``grade_scope`` follows for a
grade it cannot categorise. A grade in no competition, a manual game with no
grade, an import or manual career residual, a season we hold aggregates for
but no games or grades: each counts as evidence the player is not
junior-only, because hiding a real senior on a guess is the worse mistake.

DERIVED ON READ, NEVER STORED
-----------------------------
Which players are hidden depends on their games, on the competition tags and
on sync. A stored flag would be wrong the moment any of them changed. The
answer is cached for a short time per club so a busy public page does not
re-derive it on every request, and dropped on any change to a tag or the
switch (:func:`forget`).
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.club_grades import club_grade_rows
from app.services.grade_labels import _JUNIOR

# Bump when the shape of what is cached changes.
CACHE_VERSION = 1
CACHE_TTL_SECONDS = 120

# Sources of a season row that say nothing about which grade a player was in.
# An import or a hand-typed career lump is a figure somebody typed in: it can
# be senior, and cannot be shown to be junior, so it keeps a player visible.
_RESIDUAL_SOURCES = ("manual_aggregate", "manual_career", "import")

_cache: dict[str, tuple[float, int, "JuniorHiding"]] = {}


def guess_is_junior(*names) -> bool:
    """Would a competition or association NAME read as junior cricket?

    The same youth vocabulary grade names are classified by (``Under 14s``,
    ``Juniors``, ``Colts``, ``Kanga``...), so a competition called "Kalamunda
    Junior Cricket Association" reads junior with nobody having to say so. Only
    ever a suggestion: an admin's own tag always beats it.
    """
    return any(bool(n) and bool(_JUNIOR.search(str(n))) for n in names)


def effective_is_junior(tag: Optional[bool], *names) -> bool:
    """A competition's answer: the admin's tag, else the name's suggestion."""
    return bool(tag) if tag is not None else guess_is_junior(*names)


class JuniorHiding:
    """What is hidden for one club: junior grade ids and junior-only players."""

    __slots__ = ("enabled", "competition_ids", "grade_ids", "player_ids")

    def __init__(self, enabled: bool, competition_ids=(), grade_ids=(), player_ids=()):
        self.enabled = bool(enabled)
        self.competition_ids = frozenset(str(c) for c in competition_ids)
        self.grade_ids = tuple(grade_ids)
        self.player_ids = frozenset(str(p).lower() for p in player_ids)

    @property
    def active(self) -> bool:
        """Is there anything to hide? Empty means every caller skips the SQL."""
        return self.enabled and bool(self.grade_ids)


OFF = JuniorHiding(False)


async def org_hides_juniors(session: AsyncSession, org_id) -> bool:
    if not org_id:
        return False
    val = await session.scalar(
        text("SELECT COALESCE(hide_juniors, false) FROM organisations WHERE id = CAST(:o AS UUID)"),
        {"o": str(org_id)},
    )
    return bool(val)


async def competition_tags(session: AsyncSession, org_id) -> list[dict]:
    """Every competition the club holds with its stored tag and effective answer."""
    res = await session.execute(
        text(
            """
            SELECT id, name, association_name, is_junior
              FROM club_competitions
             WHERE organisation_id = CAST(:o AS UUID)
            """
        ),
        {"o": str(org_id)},
    )
    out = []
    for cid, name, assoc_name, tag in res.fetchall():
        out.append({
            "id": str(cid),
            "name": name,
            "is_junior_tag": tag,
            "is_junior": effective_is_junior(tag, name, assoc_name),
            "suggested_junior": guess_is_junior(name, assoc_name),
        })
    return out


async def junior_competition_ids(session: AsyncSession, org_id) -> set[str]:
    return {c["id"] for c in await competition_tags(session, org_id) if c["is_junior"]}


async def junior_grade_ids(session: AsyncSession, org_id) -> list:
    """Grade ids (the club's own and shared-fixture ones) in a junior competition.

    Goes through ``club_grade_rows`` so a fixture against another synced club,
    whose ``games`` row points at THEIR grade, resolves to OUR competition and
    is judged by our tag. A grade with no competition is not junior.
    """
    comps = await junior_competition_ids(session, org_id)
    if not comps:
        return []
    return [
        r.id for r in await club_grade_rows(session, org_id)
        if r.competition_id is not None and str(r.competition_id) in comps
    ]


# One pass over the club's players. Evidence per (player, season): a grade the
# player has games or per-grade aggregates in. The player is hidden when there
# is at least one junior grade among it and nothing at all that is not.
#
# "Nothing that is not" includes, deliberately, a season row we hold totals for
# but no grade evidence behind (CA aggregates from before games were synced),
# and a residual import or career lump: neither can be shown to be junior.
_HIDDEN_PLAYERS_SQL = """
WITH club_players AS (
    SELECT id FROM players WHERE organisation_id = CAST(:org AS UUID)
),
played_games AS (
    SELECT ga.player_id, ga.game_id FROM game_appearances ga
     WHERE ga.player_id = ANY(CAST(:pids AS uuid[]))
    UNION
    SELECT bi.player_id, bi.game_id FROM v_effective_batting_innings bi
     WHERE bi.player_id = ANY(CAST(:pids AS uuid[]))
    UNION
    SELECT bs.player_id, bs.game_id FROM v_effective_bowling_spells bs
     WHERE bs.player_id = ANY(CAST(:pids AS uuid[]))
    UNION
    SELECT fs.player_id, fs.game_id FROM v_effective_fielding_stats fs
     WHERE fs.player_id = ANY(CAST(:pids AS uuid[]))
),
evidence AS (
    SELECT pg.player_id, g.season_id, g.grade_id
      FROM played_games pg
      JOIN v_effective_games g ON g.id = pg.game_id
    UNION
    SELECT psgs.player_id, psgs.season_id, psgs.grade_id
      FROM player_season_grade_stats psgs
     WHERE psgs.player_id = ANY(CAST(:pids AS uuid[]))
),
season_rows AS (
    -- Every season the club holds a figure for, so a season with totals and
    -- no grade evidence at all is seen and counted as unplaceable.
    SELECT pss.player_id, pss.season_id, pss.source
      FROM v_effective_player_season_stats pss
     WHERE pss.player_id = ANY(CAST(:pids AS uuid[]))
),
verdicts AS (
    SELECT e.player_id,
           (e.grade_id IS NOT NULL AND e.grade_id = ANY(CAST(:jgrades AS uuid[]))) AS is_junior
      FROM evidence e
    UNION ALL
    SELECT sr.player_id, FALSE
      FROM season_rows sr
     WHERE sr.source = ANY(CAST(:residual AS text[]))
        OR NOT EXISTS (
            SELECT 1 FROM evidence e
             WHERE e.player_id = sr.player_id AND e.season_id = sr.season_id
        )
)
SELECT player_id
  FROM verdicts
 GROUP BY player_id
HAVING COUNT(*) FILTER (WHERE is_junior) > 0
   AND COUNT(*) FILTER (WHERE NOT is_junior) = 0
"""


async def junior_only_player_ids(session: AsyncSession, org_id, grade_ids) -> set[str]:
    """Players whose only cricket is in the given junior grades."""
    if not org_id or not grade_ids:
        return set()
    pids = [
        str(p) for p in (await session.execute(
            text("SELECT id FROM players WHERE organisation_id = CAST(:org AS UUID)"),
            {"org": str(org_id)},
        )).scalars().all()
    ]
    if not pids:
        return set()
    rows = await session.execute(
        text(_HIDDEN_PLAYERS_SQL),
        {
            "org": str(org_id),
            "pids": pids,
            "jgrades": [str(g) for g in grade_ids],
            "residual": list(_RESIDUAL_SOURCES),
        },
    )
    return {str(r[0]).lower() for r in rows.fetchall()}


async def resolve(session: AsyncSession, org_id, *, with_players: bool = True) -> JuniorHiding:
    """The club's junior hiding, or an inactive object when the switch is off.

    ``with_players`` False skips the per-player pass, for the callers that only
    need the junior grade ids (a games list has no use for who is hidden).
    """
    if not org_id or not await org_hides_juniors(session, org_id):
        return OFF
    now = time.monotonic()
    # A fully-resolved entry answers a grades-only ask as well.
    for full in ((True,) if with_players else (True, False)):
        hit = _cache.get(f"{org_id}:{int(full)}")
        if hit and hit[1] == CACHE_VERSION and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[2]
    key = f"{org_id}:{int(with_players)}"
    comps = await junior_competition_ids(session, org_id)
    grades = await junior_grade_ids(session, org_id)
    players = await junior_only_player_ids(session, org_id, grades) if with_players else ()
    out = JuniorHiding(True, comps, grades, players)
    _cache[key] = (now, CACHE_VERSION, out)
    return out


def forget(org_id=None) -> None:
    """Drop what is cached for a club (or everybody). Call after any tag or switch change."""
    if org_id is None:
        _cache.clear()
        return
    for key in [k for k in _cache if k.startswith(f"{org_id}:")]:
        _cache.pop(key, None)


def game_clause(hiding: JuniorHiding, column: str = "g.grade_id", param: str = "jh_grades") -> str:
    """A WHERE fragment (leading AND) leaving junior games out. '' when inactive.

    ``column IS NULL OR NOT (...)``: a game with no grade is not known junior.
    """
    if not hiding.active:
        return ""
    return f" AND ({column} IS NULL OR NOT ({column} = ANY(CAST(:{param} AS uuid[]))))"


def bind(hiding: JuniorHiding, params: dict, param: str = "jh_grades") -> dict:
    if hiding.active:
        params[param] = [str(g) for g in hiding.grade_ids]
    return params


def new_uuid_str() -> str:  # pragma: no cover - tiny helper kept for tests
    return str(uuid.uuid4())
