"""Diagnostic: a player was merged away but the Merge History does not show it. Read only.

The Merge History screen lists `merge_logs` rows for the club (`org_id`), whichever
route made the merge: the Merge Players screen, the Fantasy merge button, the automatic
merge of a hand-added player into their synced twin after a sync, and the organisation
merge all go through `admin._merge_players_core`, which writes the log row. So a person
who is gone from the club with no row on that screen has one of these shapes, and this
prints the evidence for each:

  1. A merge_logs row exists under a DIFFERENT (or NULL) org_id, so the club's screen
     never selects it.
  2. The merge was automatic (`auto_merge_hand_added` in the audit log): it IS in the
     merge log, but nobody on the club opened the screen to do it.
  3. No merge happened: the person is still there under another spelling or a second
     record (see the players section: two rows, or one row and a name alias).
  4. The merge was undone (`undone_at`), which the screen shows greyed or hides.

Usage, from the server:
  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -m app.scripts.diagnose_player_merge <org_id_or_slug> "<name>"
"""
import argparse
import asyncio
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker


async def _resolve_org(org_ref: str) -> str:
    try:
        return str(uuid.UUID(org_ref))
    except ValueError:
        pass
    async with async_session_maker() as session:
        found = (await session.execute(
            text("SELECT id::text FROM organisations WHERE slug = :s"), {"s": org_ref})).scalar()
    if not found:
        raise SystemExit(f"No club with slug {org_ref!r}")
    return found


async def diagnose(org_ref: str, who: str) -> None:
    org = await _resolve_org(org_ref)
    like = f"%{who}%"
    async with async_session_maker() as s:
        print(f"== players in the club named like {who!r}")
        for r in (await s.execute(text("""
            SELECT id::text AS id, COALESCE(display_name_override, name) AS name, grassroots_id, playhq_id,
                   is_player, import_batch_id IS NOT NULL AS imported,
                   (SELECT COUNT(*) FROM game_appearances ga WHERE ga.player_id = p.id) AS games
            FROM players p
            WHERE organisation_id = CAST(:org AS UUID) AND COALESCE(display_name_override, name) ILIKE :like
            ORDER BY 2"""), {"org": org, "like": like})).mappings():
            print(f"  {r['name']:<28} {r['id']}  ca_id={r['grassroots_id']}  playhq={r['playhq_id']}"
                  f"  is_player={r['is_player']} imported={r['imported']} games={r['games']}")

        print(f"\n== merge_logs naming them, ANY org (this club is {org})")
        rows = (await s.execute(text("""
            SELECT id, merged_at::text AS at, org_id::text AS org_id, keep_player_name, keep_player_id::text AS keep_id,
                   removed_player_name, removed_player_id::text AS removed_id, undone_at::text AS undone
            FROM merge_logs
            WHERE keep_player_name ILIKE :like OR removed_player_name ILIKE :like
            ORDER BY merged_at DESC LIMIT 40"""), {"like": like})).mappings().all()
        if not rows:
            print("  none: no merge was ever logged for this name, in any club")
        for r in rows:
            flag = ""
            if r["org_id"] != org:
                flag = "   <-- UNDER ANOTHER ORG: the club's Merge History cannot show it"
            elif r["undone"]:
                flag = "   (undone)"
            print(f"  #{r['id']} {r['at']}  {r['keep_player_name']} <- {r['removed_player_name']}"
                  f"  org={r['org_id']}{flag}")
            print(f"       keep={r['keep_id']} removed={r['removed_id']}")

        print("\n== audit log entries naming them (merges, automatic or by hand)")
        rows = (await s.execute(text("""
            SELECT created_at::text AS at, action, user_id::text AS user_id, details::text AS details
            FROM audit_logs
            WHERE org_id = CAST(:org AS UUID) AND action ILIKE '%merge%' AND details::text ILIKE :like
            ORDER BY created_at DESC LIMIT 20"""), {"org": org, "like": like})).mappings().all()
        if not rows:
            print("  none")
        for r in rows:
            who_did = "automatic, after a sync" if r["action"] == "auto_merge_hand_added" else (r["user_id"] or "unknown")
            print(f"  {r['at']}  {r['action']}  by {who_did}\n       {r['details'][:300]}")

        print("\n== name aliases (a merge leaves the removed spelling as an alias of the kept player)")
        for r in (await s.execute(text("""
            SELECT a.alias_name, a.source, a.created_at::text AS at,
                   COALESCE(p.display_name_override, p.name) AS player, p.id::text AS player_id
            FROM player_name_aliases a JOIN players p ON p.id = a.player_id
            WHERE a.organisation_id = CAST(:org AS UUID) AND a.alias_name ILIKE :like
            ORDER BY a.created_at DESC"""), {"org": org, "like": like})).mappings():
            print(f"  {r['alias_name']!r} -> {r['player']} ({r['player_id']}) source={r['source']} {r['at']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("org", help="club id or slug")
    ap.add_argument("name", help="part of the player's name")
    a = ap.parse_args()
    asyncio.run(diagnose(a.org, a.name))


if __name__ == "__main__":
    main()
