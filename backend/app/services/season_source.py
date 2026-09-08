"""Which source a season is counted from, as SQL other readers paste in.

Migration 287 lets a club say its CricketStatz import is the record for a
season it also syncs, and applies that on read in the two effective views. But
`player_season_grade_stats` — Cricket Australia's OWN per-grade aggregate — is
a separate table those views do not cover, and several club-facing figures read
it directly.

**THE GRADE NAMES DO NOT MATCH, so the two sources ADD rather than one winning.**
Cricket Australia files a season under "NMCA - Jika Shield"; CricketStatz files
the same cricket under "A-GRADE". A per-(season, grade) reconciliation like the
by-grade grid's `max(held, claimed)` therefore never compares them — they land
in different cells and sum. Reported live: a career grid showing 28 matches for
2002/03 where CricketStatz has 14, every shared season exactly doubled, while
the career header two inches above it was correct.

So a reader of CA's per-grade rows has to apply the same decision the views do.
Expressed against a `seasons` alias the query already joins, never as a
correlated EXISTS — these run on the record boards, and a per-row subplan there
is the trap `records.py`'s own timing notes document.
"""
from __future__ import annotations

CRICKETSTATZ = "cricketstatz"
PLAYHQ = "playhq"


def ca_aggregate_clause(season_alias: str = "s") -> str:
    """Drop CA's per-grade rows for a season read from CricketStatz.

    `season_alias` must be a `seasons` row already joined to the grade the
    aggregate row belongs to. Emits a leading ` AND `, so it pastes into a
    WHERE or a JOIN condition that already has one term.
    """
    return f" AND {season_alias}.stats_source IS DISTINCT FROM '{CRICKETSTATZ}'"
