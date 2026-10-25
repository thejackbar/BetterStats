"""Reconcile a club's synced fixtures against what Cricket Australia lists now.

``POST /fixtures/sync`` used to upsert on the match GUID and nothing else. CA
re-issues a GUID when it redraws a round, and drops a game that is called off,
so every such change left the old row behind next to the new one: two entries
for one game, or a game that is no longer happening still on the draw.

This module decides what to do with a synced ('grassroots') fixture that CA no
longer lists, in this order:

  1. **Re-key.** CA lists a game in the same grade, round and against the same
     opponent under a new GUID. It is the same game: move the new GUID onto the
     existing row, so its team, XI, draft and votes follow it and nothing is
     duplicated. When the new GUID already got its own (empty) row from an
     earlier sync, that duplicate is removed and the older row takes its place.
  2. **Remove.** Nothing a person did hangs off the row: delete it.
  3. **Cancel.** A confirmed XI, a selection draft, votes or a typed note sit on
     the row: keep it, set status CANCELLED, and let the club decide. A club's
     hand-typed work is never deleted by a sync.

A fourth case sits outside that order: a synced fixture that is **not the
club's at all**. A grade is a whole competition, and before fixtures were
filtered by owning club a sync stored other clubs' games too ("North Beach v
Scarborough" on North Perth's list). CA still lists those games, so they never
look stale. ``find_foreign`` names them from the listing (both owning clubs
named, neither ours) and they are removed, or cancelled when somebody has
already picked an XI or recorded votes on one. They are never re-keyed.

Only rows we can judge are touched. A grade whose match list could not be read
(or came back empty, which a blip also looks like) is left alone, as are manual
fixtures, past dates, and games CA still lists as completed, live or in any
state other than cancelled or abandoned.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Fixture

logger = logging.getLogger(__name__)

# CA states that mean "this game is not going ahead". A match CA lists in any
# other state (COMPLETED, LIVE, an unfamiliar one) is never treated as stale.
GONE_STATUSES = frozenset({"CANCELLED", "ABANDONED"})

# Tables a club fills in by hand against one fixture. Each query returns the
# fixture ids that have at least one row.
_WORK_QUERIES = (
    "SELECT DISTINCT fixture_id FROM fixture_lineups WHERE fixture_id = ANY(CAST(:ids AS uuid[]))",
    "SELECT DISTINCT fixture_id FROM selection_drafts WHERE fixture_id = ANY(CAST(:ids AS uuid[]))",
    "SELECT DISTINCT fixture_id FROM vote_ballots WHERE fixture_id = ANY(CAST(:ids AS uuid[]))",
    "SELECT DISTINCT fixture_id FROM vote_fixture_overrides WHERE fixture_id = ANY(CAST(:ids AS uuid[]))",
    "SELECT DISTINCT fixture_id FROM vote_nudges WHERE fixture_id = ANY(CAST(:ids AS uuid[]))",
)


@dataclass
class ReconcileResult:
    rekeyed: list[Fixture] = field(default_factory=list)
    removed: list[Fixture] = field(default_factory=list)
    cancelled: list[Fixture] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return len(self.rekeyed) + len(self.removed) + len(self.cancelled)


def _norm(s: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _row_key(grade_id, round_, home_away, opponent) -> tuple:
    return (str(grade_id) if grade_id else None, _norm(round_), home_away or None, _norm(opponent))


async def fixtures_with_work(db: AsyncSession, fixtures: Iterable[Fixture]) -> set[str]:
    """Ids (as strings) of the given fixtures that carry something a person did.

    That is a confirmed XI, a selection draft, any voting row, or a hand-typed
    note or finals flag. Availability is not here: it is keyed on the date, not
    the fixture, so it survives whatever happens to the row.
    """
    fixtures = list(fixtures)
    ids = [f.id for f in fixtures]
    if not ids:
        return set()
    out: set[str] = {str(f.id) for f in fixtures if (f.notes or "").strip() or f.is_final is not None}
    for sql in _WORK_QUERIES:
        res = await db.execute(text(sql), {"ids": ids})
        out.update(str(r[0]) for r in res.fetchall())
    return out


def find_stale(
    existing: Iterable[Fixture],
    incoming_ids: set[str],
    listing: dict,
    today: date,
) -> list[Fixture]:
    """Synced fixtures dated today or later that CA no longer lists as upcoming.

    ``listing`` is ``fixtures_source.org_grassroots_fixtures_checked``'s second
    value. A row is stale when its grade's list was read and either lacks the
    game altogether or says it is cancelled or abandoned. A row with no grade
    (older syncs never stamped one) is judged against every grade read, and only
    when no grade failed to load: otherwise the game might sit in the one we
    could not see.
    """
    grades: dict = listing.get("grades") or {}
    failed = int(listing.get("failed") or 0)
    stale: list[Fixture] = []
    for f in existing:
        if f.source != "grassroots" or not f.playhq_id or f.playhq_id in incoming_ids:
            continue
        if f.played_on is None or f.played_on < today:
            continue
        if (f.status or "").upper() == "CANCELLED":
            continue
        gid = str(f.grade_id) if f.grade_id else None
        if gid:
            states = grades.get(gid)
            if states is None:
                continue
            state = states.get(f.playhq_id)
        else:
            if failed or not grades:
                continue
            seen = [g[f.playhq_id] for g in grades.values() if f.playhq_id in g]
            if any(s not in GONE_STATUSES for s in seen):
                continue
            state = seen[0] if seen else None
        if state is None or state in GONE_STATUSES:
            stale.append(f)
    return stale


def find_foreign(existing: Iterable[Fixture], incoming_ids: set[str], listing: dict) -> list[Fixture]:
    """Synced fixtures CA lists between two other clubs.

    Any date: a stored game of another club is wrong on the list whether it is
    ahead or behind. Never a row this sync just confirmed as the club's own, and
    not one already marked CANCELLED (kept for the work on it; settled).
    """
    others = listing.get("others") or set()
    return [
        f for f in existing
        if f.source == "grassroots" and f.playhq_id and f.playhq_id in others
        and f.playhq_id not in incoming_ids and (f.status or "").upper() != "CANCELLED"
    ]


async def reconcile(
    db: AsyncSession,
    *,
    existing: list[Fixture],
    games: list[dict],
    incoming_ids: set[str],
    listing: dict,
    today: date,
    derive_sides,
    derive_all_sides=None,
) -> ReconcileResult:
    """Re-key, remove or cancel stale synced fixtures. Does not commit.

    ``games`` are this sync's normalised fixtures (with ``db_grade_id``);
    ``derive_sides(game)`` gives ``(home_away, opponent)`` from our side.
    ``derive_all_sides(game)``, when given, gives a list of them: a game between
    two of the club's own teams is one match with a row for each side, and each
    row re-keys onto its own side of the re-issued game. Without it a game is
    one row. ``existing`` is every fixture row of the club; rows that get removed
    are also taken out of that list's by-GUID view by the caller via the result.
    """
    result = ReconcileResult()
    foreign = find_foreign(existing, incoming_ids, listing)
    foreign_ids = {str(f.id) for f in foreign}
    stale = [f for f in find_stale(existing, incoming_ids, listing, today) if str(f.id) not in foreign_ids]
    if not stale and not foreign:
        return result

    by_gid: dict[str, list[Fixture]] = defaultdict(list)
    for f in existing:
        if f.playhq_id and f.source == "grassroots":
            by_gid[f.playhq_id].append(f)
    work = await fixtures_with_work(
        db, list(stale) + foreign + [f for g in games for f in by_gid.get(g.get("id"), [])])

    # --- 1. Re-key: pair a stale row with the one game CA lists in its place.
    stale_by_key: dict[tuple, list[Fixture]] = defaultdict(list)
    for f in stale:
        stale_by_key[_row_key(f.grade_id, f.round, f.home_away, f.opponent_name)].append(f)
    games_by_key: dict[tuple, list[dict]] = defaultdict(list)
    for g in games:
        if not g.get("id"):
            continue
        for home_away, opponent in (derive_all_sides(g) if derive_all_sides else [derive_sides(g)]):
            games_by_key[_row_key(g.get("db_grade_id"), g.get("round"), home_away, opponent)].append(g)

    handled: set[str] = set()
    for key, rows in stale_by_key.items():
        cands = games_by_key.get(key, [])
        if key[0] is None:
            # A row with no grade: match on the rest, across grades, but only
            # when that still leaves exactly one game.
            cands = [
                g for k, gs in games_by_key.items() for g in gs
                if k[1:] == key[1:]
            ]
        if len(rows) != 1 or len(cands) != 1:
            continue
        old, g = rows[0], cands[0]
        # An earlier sync may already have given this GUID its own row. Fold it
        # into the older one, unless somebody has already started using it. In an
        # in-house game the row for the club's OTHER side is not a twin.
        in_house = bool(derive_all_sides) and len(derive_all_sides(g)) > 1
        twin = next((t for t in by_gid.get(g["id"], [])
                     if t.id != old.id and (not in_house or t.home_away == old.home_away)), None)
        if twin is not None:
            if str(twin.id) in work:
                continue
            await db.delete(twin)
            result.removed.append(twin)
            existing.remove(twin)
            await db.flush()
        old.playhq_id = str(g["id"])
        result.rekeyed.append(old)
        handled.add(str(old.id))

    # --- 2 and 3. Whatever is left is no longer happening, and another club's
    # games were never the club's to have.
    for f in foreign + stale:
        if str(f.id) in handled:
            continue
        if str(f.id) in work:
            f.status = "CANCELLED"
            result.cancelled.append(f)
        else:
            await db.delete(f)
            result.removed.append(f)
    await db.flush()
    return result
