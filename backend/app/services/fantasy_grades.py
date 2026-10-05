"""Which competitions and grades count towards a club's Fantasy scoring.

Everything is by grade NAME KEY (``club_grades.club_grade_rows``), not by grade id:
a fixture between two clubs that both sync sits under whichever club's grade row it
was first synced under, so a decision on "Men's Third Grade" has to apply to every
row of that name the club's games sit in. The choice is stored as the list of grades
switched OFF (``rules.excluded_grade_keys``), so a grade that turns up later in the
season counts until someone switches it off. Current season only: it is a property
of the club's latest Fantasy season.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import competitions as comp_service
from app.services import fantasy_engine
from app.services.club_grades import club_game_sql, club_grade_rows


async def grade_options(db: AsyncSession, fs) -> dict:
    """Every grade that can count this season, grouped by the club's competitions,
    with how many of the club's games it holds so far and whether it is switched on."""
    org = str(fs.organisation_id)
    rows = await club_grade_rows(db, fs.organisation_id)
    own_this_year = {str(r[0]) for r in (await db.execute(text("""
        SELECT gr.id FROM grades gr JOIN seasons s ON s.id = gr.season_id
        WHERE s.organisation_id = CAST(:o AS UUID) AND s.year = :y"""), {"o": org, "y": fs.season_year})).all()}
    played = {str(r[0]): int(r[1]) for r in (await db.execute(text(f"""
        SELECT g.grade_id, COUNT(*) FROM v_effective_games g
        JOIN grades gr ON gr.id = g.grade_id JOIN seasons s ON s.id = gr.season_id
        WHERE {club_game_sql("g", "org")} AND s.year = :y AND g.grade_id IS NOT NULL
        GROUP BY g.grade_id"""), {"org": org, "y": fs.season_year})).all()}

    by_key: dict[str, dict] = {}
    for c in rows:
        cid = str(c.id)
        if cid not in own_this_year and cid not in played:
            continue                              # another season's grade: not part of this one
        e = by_key.setdefault(c.key, {"key": c.key, "name": c.name, "competition_id": None, "games": 0, "_own": False})
        e["games"] += played.get(cid, 0)
        if c.is_own and cid in own_this_year and not e["_own"]:
            e["name"], e["_own"] = c.name, True   # the club's own spelling wins over the other club's
        if c.competition_id and not e["competition_id"]:
            e["competition_id"] = str(c.competition_id)

    excluded = fantasy_engine.excluded_grade_keys(fs)
    legacy = {str(i) for i in (fs.included_grade_ids or [])}
    if legacy:                                    # the older "only these grade ids" setting reads as everything else being off
        keep = {c.key for c in rows if str(c.id) in legacy}
        excluded = excluded | {k for k in by_key if k not in keep}
    comps = {str(c["id"]): c for c in await comp_service.list_competitions(db, fs.organisation_id)}
    groups: dict[str, dict] = {}
    for e in sorted(by_key.values(), key=lambda x: (x["name"] or "").lower()):
        cid = e["competition_id"] if e["competition_id"] in comps else None
        g = groups.setdefault(cid or "", {
            "id": cid, "name": comps[cid]["name"] if cid else "Other grades",
            "order": comps[cid]["display_order"] if cid and comps[cid]["display_order"] is not None else 10 ** 6, "grades": []})
        g["grades"].append({"key": e["key"], "name": e["name"], "games": e["games"], "on": e["key"] not in excluded})
    ordered = sorted(groups.values(), key=lambda g: (g["id"] is None, g["order"], g["name"].lower()))
    for g in ordered:
        g.pop("order", None)
    return {"season_year": fs.season_year, "competitions": ordered,
            "excluded_count": sum(1 for e in by_key.values() if e["key"] in excluded),
            "legacy_inclusion": bool(legacy)}


def all_keys(options: dict) -> set[str]:
    return {g["key"] for c in options["competitions"] for g in c["grades"]}
