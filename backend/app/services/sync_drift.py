"""Has Cricket Australia revised a season we already hold?

The scheduled sync only asks for fixtures played since the club's last run, so
a correction CA makes to a scorecard from three seasons ago is never seen —
the fixture is outside every future window. Re-pulling every club's whole
history on a timer to catch that would cost hours of proxy traffic a month to
find, most months, nothing.

This is the cheap counterpart: compare CA's season-aggregate figures against
the ones we stored for that same season, and say so when they no longer
agree. It reads the same three endpoints the sync's own aggregate pass reads
(three calls per season, no scorecards at all), so a whole club is a minute of
traffic rather than an hour. It writes nothing to the club's data — the
outcome is a finding an admin acts on with Full Rebuild.

**What it compares, and why so carefully.** The naive check — sum the season
and compare totals — reports drift on clubs that have nothing wrong with them:

* ``_backfill_missing_season_stats`` writes synthetic aggregate rows for
  players CA omits, so our stored side is legitimately LARGER than CA's.
  Comparing per player, and only for the players CA itself reports, ignores
  those rows entirely.
* A merged player has both CA participants resolving to one of our rows, and
  the sync keeps one participant's figures and drops the other's. Any
  participant caught up in a merge is therefore skipped — its figures could
  not line up even on a perfectly fresh sync.
* A participant CA reports that we hold no player for at all is skipped
  rather than reported: that is the club's identity/merge history, not a
  revision to a scorecard.

What is left is participants that map one-to-one onto one of our players,
where a difference can only mean the underlying data changed. That makes a
finding worth acting on rather than worth explaining away.
"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Player, PlayerSeasonStats, async_session_maker
from app.services import playhq_client

logger = logging.getLogger(__name__)

# Seasons checked per club per run, oldest-checked first. A club is walked
# through its whole history over successive months rather than in one burst,
# which keeps any single night's traffic small and predictable.
MAX_SEASONS_PER_RUN = 12

# The figures compared, mapped from CA's own field names onto our column
# names. Deliberately the headline counts a club would notice moving, not
# every stored column: an average or a strike rate is derived from these, so
# a change in one without a change in these is a rounding difference, not a
# revision.
_COMPARED = (
    ("matches", ("batting", "matches"), ("bowling", "matches"), ("fielding", "matches")),
    ("runs", ("batting", "battingAggregate"), None, None),
    ("batting_innings", ("batting", "battingInnings"), None, None),
    ("wickets", None, ("bowling", "bowlingWickets"), None),
    ("catches", None, None, ("fielding", "fieldingTotalCatches")),
)


def _ca_value(payload: dict, spec) -> int | None:
    if spec is None:
        return None
    section, field = spec
    stats = payload.get(section)
    if not stats:
        return None
    val = stats.get(field)
    return int(val) if isinstance(val, (int, float)) else None


def _expected(payload: dict) -> dict[str, int]:
    """CA's figures for one participant, in our column names."""
    out: dict[str, int] = {}
    for col, bat, bowl, field in _COMPARED:
        for spec in (bat, bowl, field):
            v = _ca_value(payload, spec)
            if v is not None:
                out[col] = v
                break
        else:
            out[col] = 0
    return out


async def check_season(
    session: AsyncSession,
    org_id_str: str,
    season_id: uuid.UUID,
    raw_season_id: str,
    *,
    merged_guids: set[str],
) -> dict:
    """Compare one season's stored aggregates against CA's current figures.

    Returns ``{status, compared, differing, examples}``. ``status`` is 'ok',
    'drift', or 'unavailable' when CA returned nothing for the season (an
    outage, or a season it no longer serves) — which is explicitly NOT drift,
    since an empty response tells us nothing about whether the data changed.
    """
    batting = await playhq_client.get_batting_stats(org_id_str, raw_season_id)
    bowling = await playhq_client.get_bowling_stats(org_id_str, raw_season_id)
    fielding = await playhq_client.get_fielding_stats(org_id_str, raw_season_id)

    if not batting and not bowling and not fielding:
        return {"status": "unavailable", "compared": 0, "differing": 0, "examples": []}

    by_guid: dict[str, dict] = {}
    for section, rows in (("batting", batting), ("bowling", bowling), ("fielding", fielding)):
        for p in rows:
            guid = (p.get("id") or "").strip().lower()
            if not guid:
                continue
            by_guid.setdefault(guid, {"name": p.get("name") or p.get("shortName") or "Unknown"})
            by_guid[guid][section] = p.get("statistics", {})

    # Our players for this org, keyed by the CA participant GUID they were
    # resolved from. grassroots_id is that GUID for every player, whether the
    # row kept the raw GUID as its id or was minted per club.
    ours: dict[str, uuid.UUID] = {}
    for pid, gid in (await session.execute(
        select(Player.id, Player.grassroots_id)
        .where(Player.organisation_id == uuid.UUID(org_id_str))
    )).all():
        if gid:
            ours[str(gid).strip().lower()] = pid

    stored: dict[uuid.UUID, dict] = {}
    for row in (await session.execute(
        select(PlayerSeasonStats).where(PlayerSeasonStats.season_id == season_id)
    )).scalars():
        stored[row.player_id] = {
            "matches": row.matches or 0,
            "runs": row.runs or 0,
            "batting_innings": row.batting_innings or 0,
            "wickets": row.wickets or 0,
            "catches": row.catches or 0,
        }

    compared = 0
    examples: list[dict] = []
    differing = 0
    for guid, payload in by_guid.items():
        if guid in merged_guids:
            continue
        pid = ours.get(guid)
        if pid is None:
            continue
        want = _expected(payload)
        have = stored.get(pid)
        if have is None:
            # CA reports this player for this season and we hold no aggregate
            # row at all. Either the season was revised to include them, or
            # our own sync dropped them — both worth a re-pull.
            differing += 1
            if len(examples) < 5:
                examples.append({"player": payload.get("name"), "field": "missing",
                                 "ours": None, "theirs": want.get("matches")})
            continue
        changed = [(k, have.get(k), v) for k, v in want.items() if have.get(k) != v]
        compared += 1
        if changed:
            differing += 1
            if len(examples) < 5:
                k, mine, theirs = changed[0]
                examples.append({"player": payload.get("name"), "field": k,
                                 "ours": mine, "theirs": theirs})

    return {
        "status": "drift" if differing else "ok",
        "compared": compared,
        "differing": differing,
        "examples": examples,
    }


async def _merged_guids(session: AsyncSession, org_id: uuid.UUID) -> set[str]:
    """Participant GUIDs on either side of a live merge for this club."""
    rows = (await session.execute(
        text(
            "SELECT removed_player_id::text AS removed, keep_player_id::text AS keep "
            "FROM merge_logs WHERE org_id = :oid AND undone_at IS NULL"
        ),
        {"oid": str(org_id)},
    )).mappings().all()
    out: set[str] = set()
    for r in rows:
        out.add(r["removed"].lower())
        out.add(r["keep"].lower())
    if not out:
        return out
    # A merged player's own grassroots_id matters too — the ids above are our
    # player ids, which for a per-club minted row are not the CA GUID.
    for gid in (await session.execute(
        select(Player.grassroots_id).where(
            Player.organisation_id == org_id,
            Player.id.in_([uuid.UUID(v) for v in out if _is_uuid(v)]),
        )
    )).scalars():
        if gid:
            out.add(str(gid).strip().lower())
    return out


def _is_uuid(v: str) -> bool:
    try:
        uuid.UUID(v)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


async def check_org(org_id_str: str, *, max_seasons: int = MAX_SEASONS_PER_RUN) -> dict:
    """Check this club's least-recently-checked seasons and record the findings.

    Skips the club's current season: the scheduled sync rewrites it twice a
    week, so a difference there is a race with the sync, not a revision to
    settled history. Ordering is by when each season was last checked, nulls
    first, so a club is walked through its whole history over successive runs
    and no season is left permanently unexamined.
    """
    org_uuid = uuid.UUID(org_id_str)
    summary = {"checked": 0, "drifted": 0, "unavailable": 0, "seasons": []}

    async with async_session_maker() as session:
        merged = await _merged_guids(session, org_uuid)

        # Least-recently-checked first. The newest season by year is excluded —
        # it is the one the incremental sync is actively maintaining.
        rows = (await session.execute(text("""
            WITH ranked AS (
                SELECT s.id, s.name, s.year, s.grassroots_id,
                       ROW_NUMBER() OVER (ORDER BY s.year DESC NULLS LAST) AS recency
                FROM seasons s
                WHERE s.organisation_id = :oid
                  AND s.grassroots_id IS NOT NULL
            )
            SELECT r.id, r.name, r.year, r.grassroots_id, d.checked_at
            FROM ranked r
            LEFT JOIN sync_drift_findings d
                   ON d.season_id = r.id AND d.organisation_id = :oid
            WHERE r.recency > 1
            ORDER BY d.checked_at ASC NULLS FIRST, r.year DESC NULLS LAST
            LIMIT :lim
        """), {"oid": str(org_uuid), "lim": max_seasons})).mappings().all()

    for row in rows:
        try:
            async with async_session_maker() as session:
                result = await check_season(
                    session, org_id_str, row["id"], row["grassroots_id"],
                    merged_guids=merged,
                )
                await _record(session, org_uuid, row["id"], row["name"], result)
                await session.commit()
        except Exception as e:  # noqa: BLE001 - one season must not stop the club
            logger.warning(f"Drift check failed for org {org_id_str} season {row['name']}: {e}")
            continue

        summary["checked"] += 1
        if result["status"] == "drift":
            summary["drifted"] += 1
        elif result["status"] == "unavailable":
            summary["unavailable"] += 1
        summary["seasons"].append({"season": row["name"], **result})

    return summary


async def _record(session: AsyncSession, org_id: uuid.UUID, season_id, season_name: str,
                  result: dict) -> None:
    """Upsert one season's finding. One row per (club, season) — the current
    state, not a log, so a season that drifts and is then rebuilt reads as ok
    rather than leaving a stale warning behind."""
    await session.execute(text("""
        INSERT INTO sync_drift_findings
            (organisation_id, season_id, season_name, status, players_compared,
             players_differing, examples, checked_at, acknowledged_at)
        VALUES (:oid, :sid, :sname, :status, :compared, :differing,
                CAST(:examples AS JSONB), NOW(), NULL)
        ON CONFLICT (organisation_id, season_id) DO UPDATE
        SET season_name = EXCLUDED.season_name,
            status = EXCLUDED.status,
            players_compared = EXCLUDED.players_compared,
            players_differing = EXCLUDED.players_differing,
            examples = EXCLUDED.examples,
            checked_at = NOW(),
            -- A season that comes back clean drops any acknowledgement with
            -- it; a season still drifting keeps the one an admin already
            -- dismissed, so the banner doesn't reappear every month for a
            -- club that has decided to live with it.
            acknowledged_at = CASE WHEN EXCLUDED.status = 'drift'
                                   THEN sync_drift_findings.acknowledged_at
                                   ELSE NULL END
    """), {
        "oid": str(org_id), "sid": str(season_id), "sname": season_name or "",
        "status": result["status"], "compared": result["compared"],
        "differing": result["differing"],
        "examples": json.dumps(result["examples"]),
    })


async def open_findings(session: AsyncSession, org_id) -> list[dict]:
    """Seasons currently reading as drifted and not yet acknowledged."""
    rows = (await session.execute(text("""
        SELECT season_id, season_name, players_compared, players_differing,
               examples, checked_at
        FROM sync_drift_findings
        WHERE organisation_id = :oid
          AND status = 'drift'
          AND acknowledged_at IS NULL
        ORDER BY season_name DESC
    """), {"oid": str(org_id)})).mappings().all()
    return [
        {
            "season_id": str(r["season_id"]),
            "season": r["season_name"],
            "players_compared": r["players_compared"],
            "players_differing": r["players_differing"],
            "examples": r["examples"] or [],
            "checked_at": r["checked_at"].isoformat() if r["checked_at"] else None,
        }
        for r in rows
    ]


async def acknowledge(session: AsyncSession, org_id) -> int:
    """Dismiss every open finding for this club. Returns how many were open.

    Acknowledging is not fixing — the figures still differ. It says a human
    has looked and decided not to rebuild, so the banner stops asking. The
    next check that finds the season clean clears the acknowledgement too, and
    a season that drifts FURTHER is not re-raised: the finding is per season,
    and it is already open.
    """
    res = await session.execute(text("""
        UPDATE sync_drift_findings SET acknowledged_at = NOW()
        WHERE organisation_id = :oid AND status = 'drift' AND acknowledged_at IS NULL
    """), {"oid": str(org_id)})
    await session.commit()
    return res.rowcount or 0
