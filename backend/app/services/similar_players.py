"""Players a typed name might already be, so a hand-entered player does not
become a second record for somebody the club holds.

Read-only: it suggests, the caller decides. It reuses the import matcher
(``import_ingest.match_players``: exact, same first and last with a different
middle initial, "Surname Initial", then edit distance, and the short-form rule
for "Steve"/"Steven") so BetterPosts, the scorecard reader and the stats
importers agree on what "the same person" means. Scoped to the club's own
players, and a person who asked to be removed is never offered.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Player
from app.services import player_privacy
from app.services.import_ingest import match_players, short_form_suggestions

# Below this a candidate is noise, not a "did you mean".
MIN_CONFIDENCE = 0.7
MAX_CANDIDATES = 5


async def find_similar(db: AsyncSession, org_id, written: str) -> list[dict]:
    written = " ".join((written or "").split())
    if not written:
        return []
    rows = (await db.execute(select(Player).where(Player.organisation_id == org_id))).scalars().all()
    rows = [p for p in rows if not player_privacy.is_privacy_hidden(p)]
    by_id = {str(p.id): p for p in rows}
    # Matched on the display name, and on the stored "Last, First" name when an
    # override hides it (a club files "Mitch" over "Mitchell, Smith").
    pairs = [(str(p.id), p.display_name or p.name) for p in rows]
    extra = [(str(p.id), p.name) for p in rows if p.name and p.name != (p.display_name or p.name)]
    pool = pairs + extra

    m = match_players([written], pool).get(written) or {}
    hits: dict[str, dict] = {}

    def add(pid, conf, reason):
        pid = str(pid)
        p = by_id.get(pid)
        if not p or conf < MIN_CONFIDENCE:
            return
        cur = hits.get(pid)
        if cur is None or conf > cur["confidence"]:
            hits[pid] = {
                "id": pid, "name": p.display_name or p.name, "photo_url": p.photo_url,
                "player_role": p.player_role, "confidence": round(float(conf), 2), "reason": reason,
            }

    if m.get("player_id"):
        add(m["player_id"], m.get("confidence", 1.0), "Same name" if m.get("confidence", 1) >= 1 else "Same first and last name")
    for c in m.get("candidates") or []:
        if c.get("player_id"):
            add(c["player_id"], c.get("confidence", 0.8), "Similar name")
    sf = short_form_suggestions([written], pool, {written: m}).get(written)
    if sf:
        add(sf["player_id"], 0.9, "Short form of the same first name")

    return sorted(hits.values(), key=lambda h: -h["confidence"])[:MAX_CANDIDATES]
