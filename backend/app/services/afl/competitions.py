"""Football competitions: the club's named groups of grades, and the filter.

The table and the editing rules are cricket's (``club_competitions``,
``grades.competition_id``, ``services/competitions.py``), so a competition is
one thing on both sites. What differs is where the SEED comes from.

Cricket seeds one competition per ASSOCIATION, because Cricket Australia
publishes the association on every grade and no competition. PlayHQ's football
feed is the other way round: a football "season" row is already one
competition's season ("VAFA 2026", "VAFA 2025"), and nothing carries an
association. So the seed here reads the competition off the SEASON's name with
its year taken away, and a grade row is filed under the competition of the
season it was played in.

A PICKED COMPETITION IS AN INCLUSION, like a picked grade. It replaces the
club's grade-category default rather than stacking on it: somebody choosing
the Colts competition from the filter means the Colts, and a default that
leaves juniors out would otherwise empty the board they asked for.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.competitions import clean_name

# A year ("2026"), a season span ("2025/26", "2025-2026") or the word "season".
_YEAR = re.compile(r"\b(?:19|20)\d{2}(?:\s*[/-]\s*(?:19|20)?\d{2})?\b")
_NOISE = re.compile(r"\bseasons?\b", re.I)


def competition_from_season_name(name: str | None) -> str:
    """"VAFA 2026" -> "VAFA"; "2025/26 Southern League Season" -> "Southern League".

    Falls back to the name as written when taking the year away leaves
    nothing to call it by, so a season called "2026" is its own competition
    rather than one called "".
    """
    raw = str(name or "")
    stripped = _NOISE.sub(" ", _YEAR.sub(" ", raw))
    stripped = " ".join(stripped.split()).strip(" -–—·,:/")
    return clean_name(stripped or raw)


async def season_competitions(db: AsyncSession, org_id) -> list[dict]:
    """The competitions the club's season names imply, most seasons first.

    Returned in the ``associations`` slot of the admin payload, which is what
    the shared manager reads to decide whether "Group my grades" has anything
    to offer.
    """
    res = await db.execute(text("""
        SELECT s.name FROM seasons s WHERE s.organisation_id = :org
    """), {"org": str(org_id)})
    counts: dict[str, int] = {}
    for (name,) in res.fetchall():
        comp = competition_from_season_name(name)
        if comp:
            counts[comp] = counts.get(comp, 0) + 1
    return [{"association_id": None, "name": k, "seasons": v}
            for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]


async def seed_from_seasons(db: AsyncSession, org_id) -> dict:
    """Group every UN-grouped grade under its season's competition.

    Skip-don't-replace at both levels: a competition the club already holds
    under that name (any case) is reused, never duplicated; a grade already in
    a competition is left exactly where somebody put it. So pressing the
    button twice, or after renaming, writes nothing the club did not ask for.
    """
    existing = await db.execute(text(
        "SELECT id, name FROM club_competitions WHERE organisation_id = :org"
    ), {"org": str(org_id)})
    by_name = {r[1].lower(): str(r[0]) for r in existing.fetchall()}

    rows = await db.execute(text("""
        SELECT gr.id, s.name
          FROM grades gr JOIN seasons s ON s.id = gr.season_id
         WHERE s.organisation_id = :org AND gr.competition_id IS NULL
    """), {"org": str(org_id)})
    created = 0
    assigned = 0
    for grade_id, season_name in rows.fetchall():
        comp = competition_from_season_name(season_name)
        if not comp:
            continue
        cid = by_name.get(comp.lower())
        if cid is None:
            ins = await db.execute(text("""
                INSERT INTO club_competitions (id, organisation_id, name, is_seeded)
                VALUES (gen_random_uuid(), :org, :name, true)
                RETURNING id
            """), {"org": str(org_id), "name": comp})
            cid = str(ins.scalar_one())
            by_name[comp.lower()] = cid
            created += 1
        await db.execute(text(
            "UPDATE grades SET competition_id = CAST(:c AS UUID) WHERE id = :g"
        ), {"c": cid, "g": str(grade_id)})
        assigned += 1
    return {"created": created, "grades_assigned": assigned}


async def competition_grade_ids(db: AsyncSession, org_id, competition_id) -> list[uuid.UUID]:
    """Every grade row of this club filed under one competition.

    A competition that is another club's, or not a uuid at all, returns an
    empty list, and ``= ANY('{}')`` matches nothing: a filter that cannot be
    honoured fails CLOSED rather than quietly showing the whole club.
    """
    try:
        cid = uuid.UUID(str(competition_id))
    except (TypeError, ValueError):
        return []
    res = await db.execute(text("""
        SELECT gr.id FROM grades gr
          JOIN seasons s ON s.id = gr.season_id
          JOIN club_competitions c ON c.id = gr.competition_id
         WHERE s.organisation_id = :org AND c.organisation_id = :org AND c.id = :cid
    """), {"org": str(org_id), "cid": str(cid)})
    return [r[0] for r in res.fetchall()]


async def resolve_grade_filter(db: AsyncSession, org_id, grade_id=None,
                               competition_id=None) -> Optional[list]:
    """The grade rows a read is narrowed to, or None when nothing was picked.

    A grade and a competition together intersect: the grade, but only the
    seasons of it played in that competition.
    """
    from app.services.afl.aggregations import matching_grade_ids
    ids: Optional[set] = None
    if grade_id:
        ids = set(await matching_grade_ids(db, org_id, grade_id))
    if competition_id:
        comp = set(await competition_grade_ids(db, org_id, competition_id))
        ids = comp if ids is None else ids & comp
    return None if ids is None else list(ids)


async def public_competitions(db: AsyncSession, org_id) -> list[dict]:
    """Competitions that hold at least one public grade, in the club's order."""
    res = await db.execute(text("""
        SELECT c.id, c.name, c.display_order
          FROM club_competitions c
         WHERE c.organisation_id = :org
           AND EXISTS (SELECT 1 FROM grades gr WHERE gr.competition_id = c.id AND gr.is_public)
         ORDER BY c.display_order NULLS LAST, c.name
    """), {"org": str(org_id)})
    return [{"id": str(r[0]), "name": r[1]} for r in res.fetchall()]
