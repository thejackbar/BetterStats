"""Which imported match is a synced match, so one match is counted once.

**THE TWO SOURCES COMPLEMENT EACH OTHER. IT IS AN AND, NEVER AN OR.** A club
that syncs from Cricket Australia and imports its CricketStatz history holds
matches from both, and each source has matches the other has not — measured
across five of one club's seasons, Cricket Australia had 401 and CricketStatz
473, with genuine gaps on both sides. Choosing a winner per season (what
`seasons.stats_source` used to do) removed the double count by throwing away
every match the losing source alone held.

So the duplicate is removed **per match**: pair a CricketStatz match to the
synced game that is the same match, count it once, and keep everything
unpaired from BOTH sides. The pair is written on the imported row
(`manual_games.superseded_by_game_id`) and applied on read by the effective
views (`services/superseded_ddl.py`).

**THE SCORECARD IS THE IDENTIFIER, NOT THE DATE.** A two-day match is dated by
one source under the day it started and by the other under the day it
finished — measured on real data: the same match reads 1 March in one and
8 March in the other, so a date key alone paired only about two thirds of
them. Two records of the same match share our own batting card, and three
batters with identical scores in one season is not a coincidence. The date and
the opposition are what settle the seasons Cricket Australia holds no
scorecards for.

**IT RE-DERIVES; IT NEVER ACCUMULATES.** Either side can arrive after the
other — a club has imported while a Full Rebuild was still running, which is
how the previous design's one-shot snapshot went stale and left the club
counting both sources with nothing on screen to say so. So every pass starts
from the data as it stands now, clears the pairs it can no longer justify, and
writes the ones it can. Run it after an import and after a full sync.

**A PAIR NORMALLY HIDES THE IMPORTED HALF.** Cricket Australia is the live
source and keeps its copy current, so it wins by default. `pair_prefers_import`
is the one exception: where the synced game carries no scorecard of ours and
the imported one does, the import is the better record of that match and the
synced game steps aside instead. That is the "if PlayHQ is incomplete, use
CricketStatz to complete" case, decided per match rather than per season.

**MEASURED AT CLUB SCALE, BOTH WAYS.** 3,500 matches each side with 2,800 of
them genuinely the same match: where Cricket Australia holds its scorecards,
all 2,800 pair to the right game with none wrong, in 377ms. In a deliberately
awkward run — a THIRD of the synced games carrying no card of ours and a
QUARTER of the imported ones dated a week off — 2,566 pair correctly, 6 pair to
a neighbouring fixture and 234 are missed, in 291ms. A miss counts a match
twice, which is visible; a wrong pair still counts each match once and only
mis-attributes which fixture it was. Both are the right way round.

**A GAME A CLUB TYPED IN BY HAND IS NEVER TOUCHED.** Only rows carrying a
`cricketstatz_import_id` are considered at all, so a hand-entered scorecard can
never be paired away — the standing rule at the top of CLAUDE.md.
"""
from __future__ import annotations

import re
from datetime import timedelta
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# How far apart the two sources may date the same match. A two-day game is
# routinely a week apart between them; beyond that a "pair" is two different
# fixtures against the same opposition.
NEAR_DAYS = 10

# How coarsely the date index buckets a season, in days. Only ever WIDER than
# NEAR_DAYS — it decides what is worth scoring, never what pairs.
DAY_BUCKET = 30

# How far either side of a season's own dates to look for its synced twin
# when pairing one season at a time. Generous: a season straddles a new year
# and a final can fall well after the last round.
WINDOW_DAYS = 120

# Words that say nothing about WHICH club a team name means.
_NOISE = {
    "cricket", "club", "cc", "cricketclub", "the", "and", "of", "inc",
    "1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th",
    "1sts", "2nds", "3rds", "4ths", "xi", "xis", "x1", "i", "ii", "iii", "iv",
    "a", "b", "c", "d", "e", "f", "g", "h",
    "grade", "div", "division", "seniors", "senior", "juniors", "junior",
    "men", "mens", "women", "womens", "colts", "under", "u",
}


def team_tokens(name: str) -> frozenset[str]:
    """The words in a team name that actually identify a club."""
    words = re.sub(r"[^a-z0-9]+", " ", (name or "").lower()).split()
    return frozenset(w for w in words if w not in _NOISE and len(w) > 1)


def teams_agree(a: str, b: str) -> bool:
    """Do two spellings of an opposition name mean the same club?

    Deliberately forgiving in one direction only: a shared identifying word, or
    one name being the start of the other. It is never the sole reason to pair
    two matches — it always rides alongside a date or a scorecard — so a loose
    match here cannot pair two fixtures on its own.
    """
    ta, tb = team_tokens(a), team_tokens(b)
    if not ta or not tb:
        return False
    if ta & tb:
        return True
    ja, jb = " ".join(sorted(ta)), " ".join(sorted(tb))
    return ja.startswith(jb) or jb.startswith(ja)


@dataclass
class MatchRow:
    """One match on either side, with what identifies it."""

    id: str
    played_at: object = None
    opposition: str = ""
    signature: frozenset = field(default_factory=frozenset)

    @property
    def has_card(self) -> bool:
        return bool(self.signature)


def _day_gap(a, b) -> Optional[int]:
    if a is None or b is None:
        return None
    return abs((a - b).days)


def score_pair(imported: MatchRow, synced: MatchRow) -> Optional[tuple]:
    """How strongly these two look like one match, or None for "not a pair".

    Returns a sort key, strongest first. The four ways in are deliberately
    different in kind, so a season with no synced scorecards is still pairable
    on its dates and a season the two sources date differently is still
    pairable on its cards.
    """
    shared = len(imported.signature & synced.signature)
    gap = _day_gap(imported.played_at, synced.played_at)
    near = gap is not None and gap <= NEAR_DAYS
    same_day = gap == 0
    opp = teams_agree(imported.opposition, synced.opposition)

    ok = (
        # Three batters with the same scores. Not a coincidence.
        shared >= 3
        # One shared score, the same opposition, within a week or so.
        or (shared >= 1 and opp and near)
        # The same day against the same club. What carries a season Cricket
        # Australia holds no scorecards for.
        or (same_day and opp)
        # Two shared scores close together. The two sources name a grade and an
        # opposition differently often enough that this has to stand alone.
        or (shared >= 2 and near)
        # THE SAME CLUB, DAYS APART, WHERE NO CARD COMPARISON IS POSSIBLE.
        # A synced fixture whose scorecard was never pulled has nothing to
        # compare, so the date and the opposition are all there is — and a
        # two-day match is routinely a week apart between the two sources,
        # which is exactly the shape this recovers. Measured over a
        # club-sized history it pairs another 398 of 2,800 duplicates with
        # no wrong pairs at all.
        #
        # Guarded on one side having no card, because two cards that share
        # NOTHING is a strong signal that these are two different matches
        # against the same club.
        or (opp and near and not (imported.has_card and synced.has_card))
    )
    if not ok:
        return None
    return (shared, 1 if opp else 0, 1 if same_day else 0,
            -(gap if gap is not None else 999))


def _candidates(imported: list[MatchRow], synced: list[MatchRow]
                ) -> dict[str, list[MatchRow]]:
    """The synced games worth scoring against each imported match.

    Comparing every match against every other is quadratic, and a club's whole
    history is thousands each side. Two cheap indexes give the same answer: a
    date bucket for the pairs a date can find, and a (player, runs) index for
    the pairs only a scorecard can — which is what carries the two-day matches
    the two sources date a week apart.
    """
    by_day: dict[int, list[MatchRow]] = {}
    by_card: dict[tuple, list[MatchRow]] = {}
    for syn in synced:
        if syn.played_at is not None:
            by_day.setdefault(syn.played_at.toordinal() // DAY_BUCKET, []).append(syn)
        for entry in syn.signature:
            by_card.setdefault(entry, []).append(syn)

    out: dict[str, list[MatchRow]] = {}
    for imp in imported:
        seen: dict[str, MatchRow] = {}
        if imp.played_at is not None:
            bucket = imp.played_at.toordinal() // DAY_BUCKET
            for near in (bucket - 1, bucket, bucket + 1):
                for syn in by_day.get(near, ()):
                    seen[syn.id] = syn
        for entry in imp.signature:
            for syn in by_card.get(entry, ()):
                seen[syn.id] = syn
        out[imp.id] = list(seen.values())
    return out


def assign(imported: list[MatchRow], synced: list[MatchRow]) -> dict[str, tuple[str, bool]]:
    """Pair the two sides one-to-one. Returns imported id -> (game id, prefer).

    ONE SYNCED GAME TAKES AT MOST ONE IMPORTED MATCH and the other way round —
    a many-to-one pairing would fan the views' join out and multiply every
    figure it touches.

    **A TIE IS REFUSED RATHER THAN GUESSED.** Two candidates that look equally
    like the same match are two fixtures we cannot tell apart, and pairing the
    wrong one hides a match that really happened.
    """
    candidates = _candidates(imported, synced)
    scored: list[tuple[tuple, str, str]] = []
    best: dict[str, list[tuple]] = {}
    for imp in imported:
        for syn in candidates.get(imp.id, ()):
            key = score_pair(imp, syn)
            if key is None:
                continue
            scored.append((key, imp.id, syn.id))
            best.setdefault(imp.id, []).append(key)

    ambiguous = set()
    for imp_id, keys in best.items():
        keys.sort(reverse=True)
        if len(keys) > 1 and keys[0] == keys[1]:
            ambiguous.add(imp_id)

    scored.sort(key=lambda row: row[0], reverse=True)
    synced_by_id = {m.id: m for m in synced}
    imported_by_id = {m.id: m for m in imported}
    taken: set[str] = set()
    out: dict[str, tuple[str, bool]] = {}
    for _key, imp_id, syn_id in scored:
        if imp_id in ambiguous or imp_id in out or syn_id in taken:
            continue
        taken.add(syn_id)
        # THE HALF THAT HOLDS THE SCORECARD IS THE HALF THAT COUNTS. Cricket
        # Australia wins by default because it keeps syncing; it only steps
        # aside where it has the fixture and none of the card behind it.
        prefer_import = (not synced_by_id[syn_id].has_card
                         and imported_by_id[imp_id].has_card)
        out[imp_id] = (syn_id, prefer_import)
    return out


# ── reading each side ────────────────────────────────────────────────────────

_SYNCED_SQL = """
    SELECT g.id::text AS id, g.played_at,
           COALESCE(g.opp_club_name, '') AS opposition,
           COALESCE(g.home_team, '') AS home_team,
           COALESCE(g.away_team, '') AS away_team
      FROM games g
      LEFT JOIN grades gr ON gr.id = g.grade_id
      LEFT JOIN seasons s ON s.id = gr.season_id
     WHERE s.organisation_id = :org
        OR g.home_org_id = :org
        OR g.away_org_id = :org
"""

# OUR OWN BATTERS, NEVER THE OPPOSITION'S. A fixture between two synced clubs
# is ONE `games` row carrying both clubs' innings, so a signature built without
# this join would compare our card against theirs.
_SYNCED_CARD_SQL = """
    SELECT bi.game_id::text AS id, bi.player_id::text AS player_id, bi.runs
      FROM batting_innings bi
      JOIN players p ON p.id = bi.player_id AND p.organisation_id = :org
     WHERE NOT bi.did_not_bat AND bi.runs IS NOT NULL
"""

_IMPORTED_SQL = """
    SELECT mg.id::text AS id, mg.played_at,
           COALESCE(mg.opposition, '') AS opposition
      FROM manual_games mg
     WHERE mg.organisation_id = :org
       AND mg.cricketstatz_import_id IS NOT NULL
"""

_IMPORTED_CARD_SQL = """
    SELECT mbi.manual_game_id::text AS id, mbi.player_id::text AS player_id,
           mbi.runs
      FROM manual_batting_innings mbi
      JOIN manual_games mg ON mg.id = mbi.manual_game_id
     WHERE mg.organisation_id = :org
       AND mg.cricketstatz_import_id IS NOT NULL
       AND NOT mbi.did_not_bat AND mbi.runs IS NOT NULL
"""


async def _cards(db: AsyncSession, sql: str, params: dict) -> dict[str, set]:
    cards: dict[str, set] = {}
    for row in (await db.execute(text(sql), params)).mappings():
        cards.setdefault(row["id"], set()).add((row["player_id"], row["runs"]))
    return cards


async def load_sides(db: AsyncSession, org_id, season_ids=None
                     ) -> tuple[list[MatchRow], list[MatchRow]]:
    """Both sides of the club's record, with their cards attached.

    `season_ids` narrows the IMPORTED side to those seasons and the synced side
    to the dates they cover, so an import can pair each season as its own
    matches land rather than leaving the club counting the walked seasons twice
    for the length of the run. It never narrows the synced side by season: the
    two sources routinely file the same year under different season rows, so a
    date window is what actually reaches the twin.
    """
    imp_sql, imp_card_sql = _IMPORTED_SQL, _IMPORTED_CARD_SQL
    params = {"org": str(org_id)}
    if season_ids:
        clause = "\n       AND mg.season_id = ANY(CAST(:seasons AS UUID[]))"
        imp_sql += clause
        imp_card_sql += clause
        params["seasons"] = [str(x) for x in season_ids]

    imp_cards = await _cards(db, imp_card_sql, params)
    imported: list[MatchRow] = []
    for row in (await db.execute(text(imp_sql), params)).mappings():
        imported.append(MatchRow(row["id"], row["played_at"], row["opposition"],
                                 frozenset(imp_cards.get(row["id"], ()))))

    syn_sql, syn_params = _SYNCED_SQL, {"org": str(org_id)}
    if season_ids:
        dates = [m.played_at for m in imported if m.played_at is not None]
        if dates:
            span = timedelta(days=WINDOW_DAYS)
            syn_sql = (f"SELECT * FROM ({_SYNCED_SQL}) w\n"
                       " WHERE w.played_at IS NULL"
                       "    OR (w.played_at >= :from_day AND w.played_at <= :to_day)")
            syn_params |= {"from_day": min(dates) - span, "to_day": max(dates) + span}

    syn_cards = await _cards(db, _SYNCED_CARD_SQL, {"org": str(org_id)})
    synced: list[MatchRow] = []
    for row in (await db.execute(text(syn_sql), syn_params)).mappings():
        # `opp_club_name` is not always filled in; the two team names are, and
        # whichever is not ours is the opposition. Both are offered to the
        # comparison rather than guessed between.
        opp = " ".join(x for x in (row["opposition"], row["home_team"],
                                   row["away_team"]) if x)
        synced.append(MatchRow(row["id"], row["played_at"], opp,
                               frozenset(syn_cards.get(row["id"], ()))))
    return imported, synced


async def reconcile_org(db: AsyncSession, org_id, *, season_ids=None,
                        commit: bool = True) -> dict:
    """Re-derive the pairs for one club. Idempotent; safe to run any time."""
    imported, synced = await load_sides(db, org_id, season_ids)
    if not imported:
        return {"imported": 0, "synced": len(synced), "paired": 0,
                "prefer_import": 0, "only_cricketstatz": 0, "only_synced": 0,
                "changed": 0}

    pairs = assign(imported, synced)

    current_sql = """
        SELECT id::text AS id, superseded_by_game_id::text AS pair,
               pair_prefers_import AS prefer
          FROM manual_games
         WHERE organisation_id = :org
           AND cricketstatz_import_id IS NOT NULL
    """
    cur_params = {"org": str(org_id)}
    if season_ids:
        current_sql += " AND season_id = ANY(CAST(:seasons AS UUID[]))"
        cur_params["seasons"] = [str(x) for x in season_ids]
    current = {
        row["id"]: (row["pair"], row["prefer"])
        for row in (await db.execute(text(current_sql), cur_params)).mappings()
    }

    changed = 0
    for imp in imported:
        want = pairs.get(imp.id)
        have = current.get(imp.id, (None, False))
        now = (want[0], want[1]) if want else (None, False)
        if (have[0] or None, bool(have[1])) == now:
            continue
        changed += 1
        await db.execute(text("""
            UPDATE manual_games
               SET superseded_by_game_id = CAST(:pair AS UUID),
                   pair_prefers_import = :prefer
             WHERE id = CAST(:id AS UUID)
        """), {"id": imp.id, "pair": now[0], "prefer": now[1]})

    if commit and changed:
        await db.commit()
    elif not commit:
        await db.rollback()

    paired_syn = {g for g, _ in pairs.values()}
    return {
        "imported": len(imported),
        "synced": len(synced),
        "paired": len(pairs),
        "prefer_import": sum(1 for _, prefer in pairs.values() if prefer),
        "only_cricketstatz": len(imported) - len(pairs),
        "only_synced": len(synced) - len(paired_syn),
        "changed": changed,
    }


async def summary(db: AsyncSession, org_id) -> dict:
    """What the pairing currently says, without re-deriving it."""
    row = (await db.execute(text("""
        SELECT COUNT(*)::int AS imported,
               COUNT(*) FILTER (WHERE superseded_by_game_id IS NOT NULL)::int AS paired,
               COUNT(*) FILTER (WHERE pair_prefers_import)::int AS prefer_import
          FROM manual_games
         WHERE organisation_id = :org
           AND cricketstatz_import_id IS NOT NULL
    """), {"org": str(org_id)})).mappings().first() or {}
    imported = int(row.get("imported") or 0)
    paired = int(row.get("paired") or 0)
    return {
        "imported": imported,
        "paired": paired,
        "prefer_import": int(row.get("prefer_import") or 0),
        "only_cricketstatz": imported - paired,
    }
