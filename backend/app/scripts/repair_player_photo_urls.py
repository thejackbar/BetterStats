"""Repair player photos that hold their picture but point at a deleted player.

A merge used to carry the keeper's missing headshot across by copying the
photo address as well as the picture. The address names the player it was
uploaded to (/api/images/players/<id>/photo), so after the merge it pointed at
the player who had just been deleted: the picture was still stored on the
keeper, but every screen asked for it by the dead id, got a 404 and showed no
photo. This points the address back at the player who holds the picture.

Only an address that names a DIFFERENT player, on a row that still has the
picture bytes, is touched. Nothing is deleted and no picture is changed. A row
whose address names another player but holds no bytes is listed and left alone:
that picture is gone and has to be uploaded again.

Dry run by default. One audit entry per club, in the club's activity log.

    python -m app.scripts.repair_player_photo_urls <org-id-or-slug|all> [--apply]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services.audit_log import log_activity
from app.services.merge_profile import image_url_owner, player_image_url

# url column -> (bytes column, label)
_KINDS = {
    "photo_url": ("photo_data", "headshot"),
    "hero_photo_url": ("hero_photo_data", "action photo"),
}


async def run(target: str, apply: bool) -> None:
    async with async_session_maker() as db:
        if target == "all":
            clubs = (await db.execute(text(
                "SELECT id, name FROM organisations ORDER BY name"))).all()
        else:
            clubs = (await db.execute(text(
                "SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": target})).all()
    if not clubs:
        raise SystemExit(f"no club matches {target!r}")

    grand_fixed = grand_lost = 0
    for club_id, club_name in clubs:
        fixed: list[dict] = []
        lost: list[dict] = []
        async with async_session_maker() as db:
            for url_col, (data_col, label) in _KINDS.items():
                rows = (await db.execute(text(
                    f"SELECT id, COALESCE(NULLIF(display_name_override, ''), name) AS name, "  # noqa: S608 - fixed strings from _KINDS
                    f"       {url_col} AS url, ({data_col} IS NOT NULL) AS has_bytes "
                    f"  FROM players WHERE organisation_id = CAST(:o AS UUID) "
                    f"   AND {url_col} LIKE '/api/images/players/%'"), {"o": str(club_id)})).mappings().all()
                for r in rows:
                    owner = image_url_owner(r["url"])
                    if owner is None or owner == str(r["id"]):
                        continue
                    entry = {"id": str(r["id"]), "name": r["name"], "kind": label, "was": r["url"]}
                    if not r["has_bytes"]:
                        lost.append(entry)
                        continue
                    fixed.append(entry)
                    if apply:
                        await db.execute(text(
                            f"UPDATE players SET {url_col} = :u WHERE id = CAST(:p AS UUID)"),  # noqa: S608
                            {"u": player_image_url(r["id"], url_col), "p": str(r["id"])})
            if apply and fixed:
                await log_activity(
                    db, org_id=club_id, user_id=None, action="repair_player_photo_urls",
                    target_type="player", target_id=None,
                    details={"why": "Photo address pointed at a merged-away player; pointed back at the "
                                    "player who holds the picture.",
                             "players": [{"id": f["id"], "name": f["name"], "kind": f["kind"]} for f in fixed]},
                )
                await db.commit()
        if not fixed and not lost:
            continue
        print(f"\n{club_name}: {len(fixed)} to repair, {len(lost)} with no picture left")
        for f in fixed:
            print(f"  {f['name']} ({f['kind']}): {'repaired' if apply else 'would repair'}")
        for lo in lost:
            print(f"  {lo['name']} ({lo['kind']}): no picture stored, needs uploading again")
        grand_fixed += len(fixed)
        grand_lost += len(lost)

    print(f"\n{'Repaired' if apply else 'Dry run: would repair'} {grand_fixed} photo(s); "
          f"{grand_lost} need uploading again." + ("" if apply else " Run again with --apply."))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        raise SystemExit(__doc__)
    asyncio.run(run(args[0], "--apply" in sys.argv))
