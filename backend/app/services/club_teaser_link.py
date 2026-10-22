"""The linkage between a teaser token and a club, in one place.

A teaser snapshot belongs to one Club Directory row (``marketing_clubs``) and
carries the token that its page and pictures are reached by. Everything else
that identifies the same club hangs off that row, so the token and each of the
following always refer to the same club:

  token  <->  club_teaser_snapshots.marketing_club_id  ->  marketing_clubs.id
                                                            .utm_code        (tracking code, not unique)
                                                            .grassroots_guid (PlayHQ's own id)
                                                            .existing_org_id -> organisations.slug (once registered)
  token  <->  snapshot.club.ca_org_id   (Cricket Australia's organisation id, the one
                                         the /trial club search returns as ``id``)

Nothing here is stored twice: each lookup reads the one row, so a corrected
UTM code or a re-pulled snapshot is picked up at once and the two can never
disagree.

Rules:

* A lookup by an identifier that is NOT unique (a UTM code two clubs share, a
  CA id two snapshots claim) answers None. Showing a club another club's season
  is worse than showing nothing.
* The token-to-club direction answers for any snapshot status; the
  identifier-to-token directions answer only for ``ok`` snapshots, because
  those are the only ones that have a page or a picture.
* A club that has registered (``existing_org_id`` set) has no teaser to show
  and is not returned by the identifier lookups.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")
MAX_IDS = 6

_CLUB = """
    SELECT t.token, t.status, t.version, t.image_version,
           mc.id AS club_id, mc.name, mc.utm_code, mc.grassroots_guid, mc.existing_org_id,
           lower(t.snapshot->'club'->>'ca_org_id') AS ca_org_id,
           (SELECT o.slug FROM organisations o WHERE o.id = mc.existing_org_id AND o.archived_at IS NULL) AS slug
    FROM club_teaser_snapshots t
    JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
"""


def _clean_code(code) -> str:
    return str(code).strip().lower() if code is not None and str(code).strip() else ""


async def club_for_token(session: AsyncSession, token: str) -> Optional[dict]:
    """The club a token belongs to, with every identifier it is known by, or
    None for a malformed or unknown token."""
    if not TOKEN_RE.match(token or ""):
        return None
    row = (await session.execute(text(_CLUB + " WHERE t.token = :t"), {"t": token})).mappings().first()
    return dict(row) if row else None


async def link_for_club(session: AsyncSession, club_id) -> Optional[dict]:
    """The same record, from the club's directory id."""
    row = (await session.execute(text(_CLUB + " WHERE mc.id = CAST(:c AS uuid)"), {"c": str(club_id)})).mappings().first()
    return dict(row) if row else None


async def token_for_utm(session: AsyncSession, code) -> Optional[str]:
    """The token of the club whose UTM code this is, if exactly ONE directory
    club has that code (compared without case) and it has a good, not yet
    registered snapshot. Otherwise None."""
    want = _clean_code(code)
    if not want:
        return None
    rows = (await session.execute(text(
        "SELECT mc.id, mc.existing_org_id, t.token, t.status FROM marketing_clubs mc "
        "LEFT JOIN club_teaser_snapshots t ON t.marketing_club_id = mc.id "
        "WHERE lower(mc.utm_code) = :c LIMIT 3"), {"c": want})).mappings().all()
    if len(rows) != 1:
        return None
    r = rows[0]
    if r["token"] is None or r["status"] != "ok" or r["existing_org_id"] is not None:
        return None
    return r["token"]


async def token_for_ca_org(session: AsyncSession, ids: Iterable) -> Optional[str]:
    """The token for the club a visitor picked on /trial. ``ids`` are the
    identifiers the picker gives for it (CA's ``id`` / ``organisationGuid`` and
    PlayHQ's ``playHQId``). A snapshot is found by the CA id it was built from,
    or by the directory club's own guid; the CA id is tried first. A tie at the
    best match is no match."""
    want = sorted({str(i).strip().lower() for i in ids if i and ID_RE.match(str(i).strip())})[:MAX_IDS]
    if not want:
        return None
    rows = (await session.execute(text(_CLUB + """
        WHERE t.status = 'ok' AND t.snapshot IS NOT NULL AND mc.existing_org_id IS NULL
          AND (lower(t.snapshot->'club'->>'ca_org_id') = ANY(:ids) OR lower(mc.grassroots_guid) = ANY(:ids))
        LIMIT 20"""), {"ids": want})).mappings().all()
    if not rows:
        return None
    ranked = [(0 if r["ca_org_id"] in want else 1, r["token"]) for r in rows]
    best = min(k for k, _ in ranked)
    top = [tok for k, tok in ranked if k == best]
    return top[0] if len(top) == 1 else None


async def link_health(session: AsyncSession) -> dict:
    """How well the identifiers pin down a club, across the ``ok`` snapshots of
    clubs that have not registered. The UTM and CA-id lookups above answer None
    for an identifier that is missing or shared, so these are the clubs each
    lookup can and cannot reach."""
    r = (await session.execute(text("""
        WITH ok AS (
          SELECT mc.id, lower(NULLIF(btrim(mc.utm_code), '')) AS utm,
                 lower(NULLIF(t.snapshot->'club'->>'ca_org_id', '')) AS ca,
                 lower(NULLIF(btrim(mc.grassroots_guid), '')) AS guid
          FROM club_teaser_snapshots t JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
          WHERE t.status = 'ok' AND t.snapshot IS NOT NULL AND mc.existing_org_id IS NULL
        ),
        utm_use AS (SELECT lower(NULLIF(btrim(utm_code), '')) AS u, count(*) AS n FROM marketing_clubs GROUP BY 1),
        ca_use AS (SELECT lower(NULLIF(snapshot->'club'->>'ca_org_id', '')) AS c, count(*) AS n
                   FROM club_teaser_snapshots WHERE status = 'ok' GROUP BY 1)
        SELECT count(*) AS total,
               count(*) FILTER (WHERE ok.utm IS NULL) AS no_utm,
               count(*) FILTER (WHERE ok.utm IS NOT NULL AND utm_use.n > 1) AS shared_utm,
               count(*) FILTER (WHERE ok.utm IS NOT NULL AND utm_use.n = 1) AS utm_ok,
               count(*) FILTER (WHERE ok.ca IS NULL) AS no_ca,
               count(*) FILTER (WHERE ok.ca IS NOT NULL AND ca_use.n > 1) AS shared_ca,
               count(*) FILTER (WHERE ok.ca IS NOT NULL AND ca_use.n = 1) AS ca_ok,
               count(*) FILTER (WHERE ok.guid IS NULL) AS no_guid
        FROM ok
        LEFT JOIN utm_use ON utm_use.u = ok.utm
        LEFT JOIN ca_use ON ca_use.c = ok.ca
    """))).mappings().first()
    return dict(r)


async def unlinked_clubs(session: AsyncSession, kind: str, limit: int = 25) -> list:
    """Clubs the ``kind`` lookup ("utm" or "ca") cannot reach: name, token, and
    why (missing or shared)."""
    col = "lower(NULLIF(btrim(mc.utm_code), ''))" if kind == "utm" else "lower(NULLIF(t.snapshot->'club'->>'ca_org_id', ''))"
    use = ("SELECT lower(NULLIF(btrim(utm_code), '')) AS k, count(*) AS n FROM marketing_clubs GROUP BY 1"
           if kind == "utm" else
           "SELECT lower(NULLIF(snapshot->'club'->>'ca_org_id', '')) AS k, count(*) AS n "
           "FROM club_teaser_snapshots WHERE status = 'ok' GROUP BY 1")
    rows = (await session.execute(text(f"""
        SELECT mc.name, t.token, {col} AS k, u.n
        FROM club_teaser_snapshots t JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
        LEFT JOIN ({use}) u ON u.k = {col}
        WHERE t.status = 'ok' AND t.snapshot IS NOT NULL AND mc.existing_org_id IS NULL
          AND ({col} IS NULL OR u.n > 1)
        ORDER BY mc.name LIMIT :n"""), {"n": max(1, min(int(limit), 500))})).mappings().all()
    return [{"name": r["name"], "token": r["token"], "why": "missing" if r["k"] is None else f"shared by {r['n']}"}
            for r in rows]
