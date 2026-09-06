"""A club's competitions: which grades were played under which banner.

WHY THIS IS THE CLUB'S OWN RECORD AND NOT A SYNCED ONE
------------------------------------------------------
Cricket Australia's feed does not publish a competition. PlayHQ's public site
groups a season's grades under one ("Border Cup", "VCV Over 60s Competition",
"WASTCA Seniors"), and that level is absent from every endpoint this app can
read: the organisation's seasons, its teams, a grade's own record, a grade's
match list, and the full match record. Every plausible competition path on the
proxy answers 403, and PlayHQ's own API — where the name does live — sits
behind a CloudFront WAF this app is documented never to hang a club-facing
button on.

What CA DOES publish, on every grade, is the ASSOCIATION that runs it
(``grade.owningOrganisation`` on the teams payload sync already fetches).
That is exact, free, and available back to the club's oldest season. So:

  * the association is synced onto ``grades`` and never guessed, and
  * a competition is a named group of the club's grades, SEEDED one per
    association so a club whose whole programme is one association's grades
    never has to touch it.

The seed alone answers Applecross, which plays 2025/26 across three
associations at once. It does not answer Hamilton Veterans, where one
association (Veterans Cricket Victoria) runs the Border Cup, an Over 60s
competition and the Echuca divisions — so a club splits and renames from
there, and ``is_seeded`` is cleared the moment they do, which is what stops a
later sync putting their own naming back.

A GRADE BELONGS TO AT MOST ONE COMPETITION, and that is the whole reason this
is expressible at all. A team may play in several (Hamilton's Over 60 Men are
in the Border Cup and the Over 60s competition in one season; Applecross's 7th
XI plays One Day Grade 2 and Grade 3), but each of those is a DIFFERENT grade
row, so grouping by grade separates them cleanly with no per-game decision to
make.
"""
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# A competition with no association behind it — a club's own grouping across
# associations, or a grade CA never told us the association for. Sorted last
# in every listing, the same rule the unattributed/unassigned rows elsewhere
# in this app follow: shown, never dropped.
UNGROUPED_LABEL = "Other grades"


def clean_name(value) -> str:
    """A competition name as it will be stored: trimmed, whitespace collapsed."""
    return " ".join(str(value or "").split())[:120]


async def org_associations(db: AsyncSession, org_id) -> list[dict]:
    """Every association the club's grades were played under, most-used first.

    Keyed on the association's CA organisation GUID, so two spellings of one
    association (or a rename between seasons) resolve to one entry. The name
    reported is the one on the club's most recent grade for that association —
    an association that has since renamed itself reads as its current name
    rather than whatever it was called in 1984.
    """
    res = await db.execute(
        text(
            """
            SELECT gr.association_id,
                   (ARRAY_AGG(gr.association_name ORDER BY s.year DESC NULLS LAST))[1] AS name,
                   (ARRAY_AGG(gr.association_short_name ORDER BY s.year DESC NULLS LAST))[1] AS short_name,
                   COUNT(*) AS grade_count
              FROM grades gr
              JOIN seasons s ON s.id = gr.season_id
             WHERE s.organisation_id = CAST(:org AS UUID)
               AND gr.association_id IS NOT NULL
             GROUP BY gr.association_id
             ORDER BY grade_count DESC, name
            """
        ),
        {"org": str(org_id)},
    )
    return [
        {
            "association_id": row[0],
            "name": row[1] or "",
            "short_name": row[2] or "",
            "grade_count": int(row[3] or 0),
        }
        for row in res.fetchall()
    ]


async def seed_competitions_for_org(db: AsyncSession, org_id) -> dict:
    """Give every un-grouped grade a competition, one per association.

    SKIP, NEVER REPLACE. A grade that already has a competition is left alone,
    and a competition the club has edited (``is_seeded`` false) is never
    renamed or re-pointed. So this is safe to run on every sync, which is what
    keeps a club's new grades grouped without anyone pressing anything.

    Does NOT commit — the caller owns the transaction, since sync and the
    admin route reach this from different places.
    """
    created = 0
    assigned = 0

    # The competitions this club already holds, by association. A club that has
    # split one association into several competitions has more than one row
    # here; the FIRST (its own display order) is the one a newly-discovered
    # grade of that association joins, because there is nothing that could tell
    # us which of their splits it belongs in and the club can move it.
    res = await db.execute(
        text(
            """
            SELECT id, association_id FROM club_competitions
             WHERE organisation_id = CAST(:org AS UUID)
               AND association_id IS NOT NULL
             ORDER BY display_order NULLS LAST, created_at
            """
        ),
        {"org": str(org_id)},
    )
    by_assoc: dict[str, UUID] = {}
    for comp_id, assoc_id in res.fetchall():
        by_assoc.setdefault(assoc_id, comp_id)

    for assoc in await org_associations(db, org_id):
        assoc_id = assoc["association_id"]
        comp_id = by_assoc.get(assoc_id)
        if comp_id is None:
            name = clean_name(assoc["name"]) or clean_name(assoc["short_name"]) or "Competition"
            # A club that has already named a competition this exact thing by
            # hand keeps it and takes ownership of the association's grades,
            # rather than the insert failing on the case-folded unique index.
            row = await db.execute(
                text(
                    """
                    INSERT INTO club_competitions
                        (organisation_id, name, association_id, association_name, is_seeded)
                    VALUES (CAST(:org AS UUID), :name, :assoc_id, :assoc_name, true)
                    ON CONFLICT (organisation_id, lower(name)) DO UPDATE
                        SET association_id = COALESCE(club_competitions.association_id,
                                                      EXCLUDED.association_id),
                            association_name = COALESCE(club_competitions.association_name,
                                                        EXCLUDED.association_name)
                    RETURNING id, (xmax = 0) AS inserted
                    """
                ),
                {
                    "org": str(org_id),
                    "name": name,
                    "assoc_id": assoc_id,
                    "assoc_name": assoc["name"] or None,
                },
            )
            comp_id, inserted = row.first()
            by_assoc[assoc_id] = comp_id
            if inserted:
                created += 1

        upd = await db.execute(
            text(
                """
                UPDATE grades gr
                   SET competition_id = CAST(:comp AS UUID)
                  FROM seasons s
                 WHERE s.id = gr.season_id
                   AND s.organisation_id = CAST(:org AS UUID)
                   AND gr.association_id = :assoc_id
                   AND gr.competition_id IS NULL
                """
            ),
            {"comp": str(comp_id), "org": str(org_id), "assoc_id": assoc_id},
        )
        assigned += upd.rowcount or 0

    return {"competitions_created": created, "grades_assigned": assigned}


async def list_competitions(db: AsyncSession, org_id) -> list[dict]:
    """The club's competitions with what each one holds.

    ``grade_count`` and ``season_count`` are what make the admin screen
    readable — a competition holding one grade in one season is almost
    certainly a cup, and one holding fourteen across fifty seasons is the
    club's home association.
    """
    res = await db.execute(
        text(
            """
            SELECT c.id, c.name, c.association_id, c.association_name,
                   c.display_order, c.is_seeded,
                   COUNT(gr.id) AS grade_count,
                   COUNT(DISTINCT gr.season_id) AS season_count
              FROM club_competitions c
              LEFT JOIN grades gr ON gr.competition_id = c.id
             WHERE c.organisation_id = CAST(:org AS UUID)
             GROUP BY c.id
             ORDER BY c.display_order NULLS LAST, c.name
            """
        ),
        {"org": str(org_id)},
    )
    return [
        {
            "id": str(row[0]),
            "name": row[1],
            "association_id": row[2],
            "association_name": row[3],
            "display_order": row[4],
            "is_seeded": bool(row[5]),
            "grade_count": int(row[6] or 0),
            "season_count": int(row[7] or 0),
        }
        for row in res.fetchall()
    ]


async def competition_grades(db: AsyncSession, org_id) -> list[dict]:
    """Every distinct grade NAME the club holds, and which competition it is in.

    Grouped by name rather than listed per row because a grade is one thing to
    a club across every season it ran — the same rule the category and
    display-order editors on Manage Grades already follow — so assigning "1st
    Grade" to a competition assigns all fifty of its season rows at once.
    """
    res = await db.execute(
        text(
            """
            SELECT gr.name,
                   (ARRAY_AGG(gr.competition_id ORDER BY s.year DESC NULLS LAST))[1] AS comp_id,
                   (ARRAY_AGG(gr.association_name ORDER BY s.year DESC NULLS LAST))[1] AS assoc,
                   COUNT(DISTINCT gr.competition_id) AS distinct_comps,
                   MAX(s.year) AS latest_year,
                   COUNT(*) AS rows
              FROM grades gr
              JOIN seasons s ON s.id = gr.season_id
             WHERE s.organisation_id = CAST(:org AS UUID)
             GROUP BY gr.name
             ORDER BY MAX(s.year) DESC NULLS LAST, gr.name
            """
        ),
        {"org": str(org_id)},
    )
    return [
        {
            "name": row[0],
            "competition_id": str(row[1]) if row[1] else None,
            "association_name": row[2],
            # True where this grade name's season rows are split across more
            # than one competition. Reported rather than hidden: it is a real
            # state (a grade that moved association) and the screen says so
            # instead of silently showing whichever row sorted first.
            "mixed": int(row[3] or 0) > 1,
            "latest_year": row[4],
            "season_rows": int(row[5] or 0),
        }
        for row in res.fetchall()
    ]


async def create_competition(
    db: AsyncSession, org_id, name: str, association_id: Optional[str] = None
) -> dict:
    """Create a competition the club named itself. Raises ValueError on a clash."""
    clean = clean_name(name)
    if not clean:
        raise ValueError("A competition needs a name.")
    dup = await db.execute(
        text(
            "SELECT 1 FROM club_competitions WHERE organisation_id = CAST(:org AS UUID)"
            " AND lower(name) = lower(:name)"
        ),
        {"org": str(org_id), "name": clean},
    )
    if dup.first():
        raise ValueError(f"This club already has a competition called {clean}.")
    row = await db.execute(
        text(
            """
            INSERT INTO club_competitions (organisation_id, name, association_id, is_seeded)
            VALUES (CAST(:org AS UUID), :name, :assoc, false)
            RETURNING id
            """
        ),
        {"org": str(org_id), "name": clean, "assoc": association_id or None},
    )
    return {"id": str(row.scalar_one()), "name": clean}


async def rename_competition(db: AsyncSession, org_id, competition_id, name: str) -> None:
    """Rename a competition. Clears ``is_seeded`` — this is now the club's own."""
    clean = clean_name(name)
    if not clean:
        raise ValueError("A competition needs a name.")
    dup = await db.execute(
        text(
            "SELECT 1 FROM club_competitions WHERE organisation_id = CAST(:org AS UUID)"
            " AND lower(name) = lower(:name) AND id <> CAST(:id AS UUID)"
        ),
        {"org": str(org_id), "name": clean, "id": str(competition_id)},
    )
    if dup.first():
        raise ValueError(f"This club already has a competition called {clean}.")
    res = await db.execute(
        text(
            "UPDATE club_competitions SET name = :name, is_seeded = false"
            " WHERE id = CAST(:id AS UUID) AND organisation_id = CAST(:org AS UUID)"
        ),
        {"name": clean, "id": str(competition_id), "org": str(org_id)},
    )
    if not res.rowcount:
        raise ValueError("That competition is not this club's.")


async def delete_competition(db: AsyncSession, org_id, competition_id) -> None:
    """Delete a competition. Its grades are un-grouped, never deleted."""
    res = await db.execute(
        text(
            "DELETE FROM club_competitions WHERE id = CAST(:id AS UUID)"
            " AND organisation_id = CAST(:org AS UUID)"
        ),
        {"id": str(competition_id), "org": str(org_id)},
    )
    if not res.rowcount:
        raise ValueError("That competition is not this club's.")


async def assign_grade(
    db: AsyncSession, org_id, grade_name: str, competition_id: Optional[str]
) -> int:
    """Put every season row of one grade NAME into a competition (or none).

    ``competition_id`` None un-groups the grade. A competition id belonging to
    another club is refused rather than silently doing nothing — the id
    arrives from a browser.
    """
    if competition_id:
        owned = await db.execute(
            text(
                "SELECT 1 FROM club_competitions WHERE id = CAST(:id AS UUID)"
                " AND organisation_id = CAST(:org AS UUID)"
            ),
            {"id": str(competition_id), "org": str(org_id)},
        )
        if not owned.first():
            raise ValueError("That competition is not this club's.")
    res = await db.execute(
        text(
            """
            UPDATE grades gr
               SET competition_id = CAST(:comp AS UUID)
              FROM seasons s
             WHERE s.id = gr.season_id
               AND s.organisation_id = CAST(:org AS UUID)
               AND gr.name = :name
            """
        ),
        {
            "comp": str(competition_id) if competition_id else None,
            "org": str(org_id),
            "name": grade_name,
        },
    )
    # A grade this club does not hold updates nothing, which is the right
    # answer — nothing is created for a name that is not theirs.
    return res.rowcount or 0


async def reorder_competitions(db: AsyncSession, org_id, ids: Sequence) -> None:
    """Stamp display_order by position over the ids given.

    A foreign or stale id is SKIPPED without leaving a gap in the numbering,
    the same rule ``reorder_agenda_items`` and ``reorder_plan_tree`` follow —
    the list arrives from a browser.
    """
    owned = await db.execute(
        text(
            "SELECT id FROM club_competitions WHERE organisation_id = CAST(:org AS UUID)"
        ),
        {"org": str(org_id)},
    )
    valid = {str(r[0]) for r in owned.fetchall()}
    position = 0
    for raw in ids:
        if str(raw) not in valid:
            continue
        await db.execute(
            text(
                "UPDATE club_competitions SET display_order = :pos WHERE id = CAST(:id AS UUID)"
            ),
            {"pos": position, "id": str(raw)},
        )
        position += 1
