"""One-off diagnostic: print the REAL field names Twenty's metadata API
reports for the objects import_twenty_pipeline.py guesses at (Notes/
NoteTargets read, and Opportunity/Lead assignee), so those guesses can be
corrected against the actual live workspace instead of a second blind
guess. Confirmed wrong so far: noteTarget has no `opportunityId` field
(live 400: "Object noteTarget doesn't have any \"opportunityId\" field"),
and neither opportunity nor lead's assignee (whatever it's really called)
matched via assigneeId/assignee.id/assignedToId (0 matched, 0 unmatched —
meaning none of those keys were even present on the fetched records).

Read-only — makes one GET to /rest/metadata/objects (the same endpoint
bootstrap_twenty.py already uses) and prints every field name/type for the
objects in TARGET_OBJECTS. Nothing is written anywhere.

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.twenty_schema_dump
"""
from __future__ import annotations

import asyncio

import httpx

from app.services.twenty_client import client

# taskTarget is included as a known-working reference point (companyId,
# taskId — already used successfully elsewhere) to compare noteTarget's
# actual shape against.
TARGET_OBJECTS = ("noteTarget", "note", "opportunity", "lead", "taskTarget", "workspaceMember")


async def main() -> None:
    if not client.configured:
        print("Twenty is not configured (TWENTY_API_URL / TWENTY_API_KEY) — nothing to do.")
        return
    async with httpx.AsyncClient() as http:
        # Matches bootstrap_twenty.py's own proven call exactly (no params —
        # this endpoint doesn't take `limit`; `data` is directly the object
        # list, not nested under a `data.objects` key).
        r = await http.get(f"{client.base}/rest/metadata/objects", headers=client._headers)
        if r.status_code >= 400:
            print(f"metadata/objects -> {r.status_code}: {r.text[:500]}")
            return
        objects = r.json().get("data") or []

    by_name = {o.get("nameSingular"): o for o in objects}
    for name in TARGET_OBJECTS:
        obj = by_name.get(name)
        if obj is None:
            print(f"=== {name}: NOT FOUND in this workspace's object list ===\n")
            continue
        print(f"=== {name} ({obj.get('namePlural')}) ===")
        for f in sorted(obj.get("fields") or [], key=lambda f: f.get("name") or ""):
            rel = ""
            if f.get("type") in ("RELATION", "MORPH_RELATION"):
                target = f.get("relationDefinition") or {}
                rel = f"  -> {target}"
            print(f"  {f.get('name'):<28} {f.get('type')}{rel}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
