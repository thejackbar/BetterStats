"""Is this game the player's? Judged from Cricket Australia's own scorecard.

One rule shared by `scripts/audit_player_games` (read only) and
`scripts/repair_misattributed_games` (which changes data), so the thing that is reported is
exactly the thing that is repaired.

A synced game belongs on a player's record when their participant id is on the scorecard (a team
sheet entry, or a batting, bowling or fielding row), or an id that was merged into them is. Their
rows can also reach a record some other way (a link by name, a shared placeholder id); when none of
their ids is on the card, the rows are somebody else's.

  ON     the player's own id is on the card.
  MERGE  an id merged into them is on the card (raw, or the per-club uuid5 the removed record used).
  OFF    neither is. The card has people on it, just not this one.
  EMPTY  the card names nobody (no team sheet, no rows). Nothing can be judged: never OFF.

The placeholder id CA gives every hidden participant (`participant_names.is_placeholder_id`) never
counts as anyone's.
"""
from __future__ import annotations

import uuid
from typing import Iterable, Optional

from app.services.participant_names import is_placeholder_id


def card_ids(scorecard: Optional[dict]) -> tuple[set[str], set[str]]:
    """``(team sheet ids, row ids)`` on a scorecard, lower case, placeholders removed."""
    sheet: set[str] = set()
    rows: set[str] = set()
    sc = scorecard or {}
    for team in sc.get("teams") or []:
        for p in team.get("players") or []:
            sheet.add((p.get("participantId") or "").lower())
    for inn in sc.get("innings") or []:
        for kind in ("batting", "bowling", "fielding"):
            for r in inn.get(kind) or []:
                rows.add((r.get("participantId") or "").lower())
    keep = lambda s: {x for x in s if x and not is_placeholder_id(x)}  # noqa: E731
    return keep(sheet), keep(rows)


def classify(scorecard: Optional[dict], own_ids: Iterable[str], merged_ids: Iterable[str],
             org_id: Optional[uuid.UUID] = None) -> str:
    """``ON`` / ``MERGE`` / ``OFF`` / ``EMPTY`` for one game (see the module docstring)."""
    sheet, rows = card_ids(scorecard)
    on_card = sheet | rows
    if not on_card:
        return "EMPTY"
    own = {str(i).lower() for i in own_ids}
    if on_card & own:
        return "ON"
    merged = {str(i).lower() for i in merged_ids}
    if on_card & merged:
        return "MERGE"
    if org_id is not None:
        # A merged-away record of a per-club player carries uuid5(org, raw id), not the raw id.
        for cid in on_card:
            try:
                if str(uuid.uuid5(org_id, cid)) in merged:
                    return "MERGE"
            except ValueError:
                continue
    return "OFF"


def merged_into(redirects: dict, player_id) -> set[str]:
    """Every record id that was merged into ``player_id``, directly or through a chain.

    ``redirects`` is ``{removed_id: keep_id}`` from the un-undone merge log. A chain A -> B -> player
    counts A as well as B, as sync's own redirect does.
    """
    target = {str(k): str(v) for k, v in redirects.items()}
    me = str(player_id)
    out: set[str] = set()
    for removed in target:
        seen = {removed}
        cur = target[removed]
        while cur in target and cur not in seen:
            seen.add(cur)
            cur = target[cur]
        if cur == me:
            out.add(removed.lower())
    return out
