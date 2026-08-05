"""Find (and clear) member rows that belong to another club's player.

WHY THESE EXIST
---------------
A fixture between two clubs that both sync BetterCricket is a single ``games``
row, and each club's sync writes its own players' ``game_appearances`` against
it. ``fees.recompute_fee_match_days`` used to read every appearance on our
season's games and enrol the player behind each one as a member of OUR club,
with no check that the player was ours. Every opponent from a both-synced club
therefore became a member: visible in the Directory, counted in the member
totals, and — through the member's player link — exposing that club's photo,
email and phone.

The cause is fixed in ``services/fees.py``; this clears what it already wrote.

WHAT IT TOUCHES
---------------
Only rows whose ``player_id`` points at a player owned by a DIFFERENT
organisation. A member with no player link, or one linked to our own player, is
never considered — those are the club's real people.

Rows carrying anything a human entered (a payment, a role, a qualification, a
committee term, logged hours, a family link) are REPORTED and left alone: the
row is wrong, but something real is hanging off it and a person should decide.
Everything else is archived, which is reversible and enough to clear the
Directory. ``--delete`` removes them outright once you are satisfied.

USAGE
-----
    python -m app.scripts.purge_foreign_members            # every club, dry run
    python -m app.scripts.purge_foreign_members <org_id>   # one club, dry run
    python -m app.scripts.purge_foreign_members all --apply
    python -m app.scripts.purge_foreign_members all --apply --delete
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker


FIND = """
    SELECT fm.id, fm.organisation_id, fm.full_name, fm.archived_at,
           o.name AS club_name, po.name AS player_club_name, p.organisation_id AS player_org
    FROM fee_members fm
    JOIN players p ON p.id = fm.player_id
    JOIN organisations o ON o.id = fm.organisation_id
    LEFT JOIN organisations po ON po.id = p.organisation_id
    WHERE p.organisation_id IS DISTINCT FROM fm.organisation_id
      AND (CAST(:org AS UUID) IS NULL OR fm.organisation_id = CAST(:org AS UUID))
    ORDER BY o.name, fm.full_name
"""

# Anything here means a person has done something with the row.
ATTACHMENTS = [
    ("fee payments", "SELECT COUNT(*) FROM fee_payments fp JOIN fee_member_seasons ms ON ms.id = fp.member_season_id WHERE ms.member_id = :id"),
    ("roles", "SELECT COUNT(*) FROM volunteer_roles WHERE member_id = :id"),
    ("qualifications", "SELECT COUNT(*) FROM member_qualifications WHERE member_id = :id"),
    ("committee terms", "SELECT COUNT(*) FROM committee_terms WHERE member_id = :id"),
    ("logged hours", "SELECT COUNT(*) FROM volunteer_hours WHERE member_id = :id"),
    ("family links", "SELECT COUNT(*) FROM family_members WHERE fee_member_id = :id"),
    ("roster shifts", "SELECT COUNT(*) FROM roster_shifts WHERE assignee_member_id = :id"),
]


async def run(org_id: str | None, apply: bool, hard_delete: bool) -> int:
    async with async_session_maker() as db:
        rows = (await db.execute(text(FIND), {"org": org_id})).mappings().all()
        if not rows:
            print("No member rows point at another club's player. Nothing to do.")
            return 0

        by_club: dict = {}
        for r in rows:
            by_club.setdefault(r["club_name"], []).append(r)

        cleared, kept = 0, []
        for club, members in by_club.items():
            print(f"\n{club} — {len(members)} member row(s) linked to another club's player")
            for m in members:
                attached = []
                for label, sql in ATTACHMENTS:
                    try:
                        n = (await db.execute(text(sql), {"id": m["id"]})).scalar() or 0
                    except Exception:
                        await db.rollback()
                        n = 0          # table absent on this deployment
                    if n:
                        attached.append(f"{n} {label}")
                origin = m["player_club_name"] or "an unknown club"
                if attached:
                    kept.append((club, m["full_name"], origin, ", ".join(attached)))
                    print(f"  KEPT     {m['full_name']:<28} (player belongs to {origin}) — has {', '.join(attached)}")
                    continue
                if m["archived_at"] is not None and not hard_delete:
                    print(f"  already archived  {m['full_name']}")
                    continue
                print(f"  {'DELETE' if hard_delete else 'ARCHIVE'}  {m['full_name']:<28} (player belongs to {origin})")
                if apply:
                    if hard_delete:
                        await db.execute(text("DELETE FROM fee_members WHERE id = :id"), {"id": m["id"]})
                    else:
                        await db.execute(text("UPDATE fee_members SET archived_at = NOW() WHERE id = :id"), {"id": m["id"]})
                cleared += 1

        if apply:
            await db.commit()
            print(f"\n{cleared} row(s) {'deleted' if hard_delete else 'archived'}.")
        else:
            print(f"\nDRY RUN — {cleared} row(s) would be {'deleted' if hard_delete else 'archived'}. "
                  f"Re-run with --apply to act.")
        if kept:
            print(f"\n{len(kept)} row(s) left alone because something is attached to them:")
            for club, name, origin, what in kept:
                print(f"  {club}: {name} (from {origin}) — {what}")
            print("Decide these by hand: the link is wrong, but the attached work may not be.")
        return 0


def main() -> int:
    args = [a for a in sys.argv[1:]]
    apply = "--apply" in args
    hard_delete = "--delete" in args
    positional = [a for a in args if not a.startswith("--")]
    org = None if (not positional or positional[0] == "all") else positional[0]
    return asyncio.run(run(org, apply, hard_delete))


if __name__ == "__main__":
    raise SystemExit(main())
