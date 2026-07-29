"""Published team lists (lineups) from the Grassroots /scores API.

Clubs publish their selected side on play.cricket.com.au before a game, and
``/scores/matches/{id}`` carries it: ``teams[].players[]`` (each
``{participantId, name, shortName, roles}``, roles being Captain / Wicket
Keeper), ``teams[].nonPlayingMembers[]`` (coach, manager) and top-level
``officials`` (umpires). Verified live: an UPCOMING match returns a side as
soon as its club publishes it, and an empty player list for a side that
hasn't — so "not published yet" is a normal, expected state, not an error.

Nothing here is persisted. Lineups are read live (short-TTL cached in the
client) because a pre-game side changes right up to the first ball; the
authoritative record of who actually played still comes from the scorecard at
sync time.

Two consumers:
  * the public Lineups page (both teams, ours flagged and profile-linked)
  * BetterSelect vote collection, where a club can choose to vote on the
    Play.Cricket team list instead of waiting for the scorecard to sync.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services.club_match import club_match_keys

# Cricket Australia redacts junior participants' names to a run of asterisks.
# Existing convention (see the fill-in notes in CLAUDE.md) is to show that
# literally rather than inventing a placeholder identity.
_REDACTED = re.compile(r"^\*+$")


def looks_redacted(name: Optional[str]) -> bool:
    n = (name or "").strip()
    return not n or bool(_REDACTED.match(n))


def _role_flags(roles) -> dict:
    r = {str(x).lower() for x in (roles or [])}
    return {
        "is_captain": "captain" in r,
        "is_wicket_keeper": any("keeper" in x for x in r),
    }


def normalise_team(team: dict) -> dict:
    """One GR team object → ``{id, name, club, logo_url, players[], staff[]}``."""
    org = team.get("owningOrganisation") or {}
    players = []
    for p in team.get("players") or []:
        name = p.get("name") or p.get("shortName")
        players.append({
            "participant_id": p.get("participantId"),
            "name": "********" if looks_redacted(name) else name,
            "short_name": p.get("shortName"),
            "redacted": looks_redacted(name),
            "roles": p.get("roles") or [],
            **_role_flags(p.get("roles")),
        })
    staff = [
        {"name": m.get("name"), "roles": m.get("roles") or []}
        for m in (team.get("nonPlayingMembers") or [])
        if m.get("name")
    ]
    return {
        "id": team.get("id"),
        "name": team.get("displayName") or team.get("name"),
        "club": org.get("name"),
        "club_id": org.get("id"),
        "logo_url": org.get("logoUrl"),
        "players": players,
        "staff": staff,
    }


def our_team_index(teams: list[dict], org) -> Optional[int]:
    """Which of the two teams is the club's own.

    Owning-organisation id first (our ``organisations.id`` IS the CA org GUID
    for synced clubs), then the club's own name keys against the team's club
    and team name. Returns None when neither side matches, so a caller can fall
    back rather than guess wrong.
    """
    org_ids = {str(org.id).lower()}
    if getattr(org, "playhq_id", None):
        org_ids.add(str(org.playhq_id).lower())
    for i, t in enumerate(teams):
        oid = str((t.get("club_id") or "")).lower()
        if oid and oid in org_ids:
            return i
    keys = club_match_keys(org)
    for i, t in enumerate(teams):
        hay = f"{t.get('club') or ''} {t.get('name') or ''}".lower()
        if any(k in hay for k in keys):
            return i
    return None


def _name_key(n: Optional[str]) -> tuple[str, str]:
    """Match on (surname, first_initial) — handles "Surname, First" (our
    stored `name` format) vs "First Surname" (GR's `name`/`shortName`).

    The fallback for when GR's participant GUID for THIS match doesn't match
    anything we have stored at all: CA is known to issue a different GUID for
    the same real person across a MyCricket/PlayHQ migration boundary (see the
    dual-GUID notes in CLAUDE.md) — confirmed live on this exact route: a
    club's own registered player can appear in `/scores/matches/{id}`'s team
    list under a participantId that matches neither their `players.id` nor
    `grassroots_id`, even though the SAME id resolves correctly on the
    scorecard-sync path for other games. Mirrors `games.py::get_scorecard`'s
    identical fallback (`_name_key`/`nk_to_pid`) so the two code paths agree.
    """
    n = (n or "").strip()
    if "," in n:
        surname, _, first = n.partition(",")
        first = first.strip()
        return (surname.strip().lower(), first[0].lower() if first else "")
    words = n.split()
    if not words:
        return ("", "")
    return (words[-1].lower(), words[0][0].lower())


async def resolve_participants(db: AsyncSession, org_id, participants: list[dict]) -> dict[str, dict]:
    """Map CA participants (``{participant_id, name}``) → our own player rows,
    org-scoped.

    Three-step match, same priority as the scorecard merge: the literal id,
    then the stored raw GUID alias (``grassroots_id`` — the per-club ``uuid5``
    scheme), then a name-key match for the GUID-mismatch case above. Loads the
    whole roster rather than filtering by the incoming GUIDs, since the name
    fallback needs every player's name in scope regardless of which GUIDs were
    asked for.
    """
    res = await db.execute(
        text(
            "SELECT id, grassroots_id, COALESCE(display_name_override, name) AS name, photo_url "
            "FROM players WHERE organisation_id = :org"
        ),
        {"org": org_id},
    )
    by_guid: dict[str, dict] = {}
    by_name: dict[tuple, dict] = {}
    for pid, guid, name, photo in res.fetchall():
        hit = {"player_id": str(pid), "name": name, "photo_url": photo}
        by_guid[str(pid)] = hit
        if guid:
            by_guid[str(guid)] = hit
        if name and not looks_redacted(name):
            by_name.setdefault(_name_key(name), hit)

    out: dict[str, dict] = {}
    for p in participants:
        pid = p.get("participant_id")
        if not pid:
            continue
        hit = by_guid.get(pid)
        if not hit and not looks_redacted(p.get("name")):
            hit = by_name.get(_name_key(p.get("name")))
        if hit:
            out[pid] = hit
    return out


async def match_lineups(db: AsyncSession, org, match_id: str, detail: Optional[dict] = None) -> Optional[dict]:
    """Both teams' published lineups for one match, ours flagged and linked.

    Returns None when Grassroots has no such match (a manual fixture, or a
    PlayHQ-namespace id that 204s). ``published`` is False for a side whose club
    hasn't put its team up yet — the normal state early in the week.
    """
    if detail is None:
        detail = await gr.get_match_detail(match_id)
    if not detail:
        return None
    teams = [normalise_team(t) for t in (detail.get("teams") or [])]
    ours = our_team_index(teams, org)

    if ours is not None:
        known = await resolve_participants(db, org.id, teams[ours]["players"])
        for p in teams[ours]["players"]:
            hit = known.get(p["participant_id"])
            p["player_id"] = hit["player_id"] if hit else None
            # Our own players get their club photo; everyone else falls back to
            # the team crest on the frontend.
            p["photo_url"] = hit.get("photo_url") if hit else None
            # A redacted junior still has a real name on our side if we hold
            # the player — CA only withholds it in this feed.
            if hit and p["redacted"]:
                p["name"] = hit["name"]
                p["redacted"] = False

    # isHome / the score live on matchSummary.teams, NOT the top-level teams
    # array (the same gotcha the scorecard parser documents in CLAUDE.md).
    summary = detail.get("matchSummary") or {}
    by_id = {str(s.get("id")): s for s in (summary.get("teams") or []) if s.get("id")}
    by_name = {(s.get("displayName") or "").lower(): s for s in (summary.get("teams") or [])}
    for i, t in enumerate(teams):
        s = by_id.get(str(t.get("id"))) or by_name.get((t.get("name") or "").lower()) or {}
        t["is_ours"] = (i == ours)
        t["published"] = bool(t["players"])
        t["is_home"] = bool(s.get("isHome"))
        t["is_winner"] = bool(s.get("isWinner"))
        t["score_text"] = s.get("scoreText")

    sched = (detail.get("matchSchedule") or [{}])
    start = (sched[0].get("startDateTime") if sched else "") or ""
    return {
        "match_id": detail.get("id") or match_id,
        "status": detail.get("status"),
        "result_text": summary.get("resultText"),
        "date": start[:10] or None,
        "time": start[11:16] if len(start) >= 16 else None,
        "round": (detail.get("round") or {}).get("name"),
        "grade": (detail.get("grade") or {}).get("name"),
        "venue": (detail.get("venue") or {}).get("name"),
        "teams": teams,
        "officials": [
            {"name": o.get("name"), "role": o.get("role")}
            for o in (detail.get("officials") or []) if o.get("name")
        ],
        "any_published": any(t["published"] for t in teams),
    }


async def org_lineups(db: AsyncSession, org, match_ids: list[str]) -> list[dict]:
    """``match_lineups`` across several matches, fetched concurrently."""
    details = await gr.get_matches_detail(match_ids)
    out = []
    for mid in match_ids:
        d = details.get(mid)
        if not d:
            continue
        row = await match_lineups(db, org, mid, detail=d)
        if row:
            out.append(row)
    return out


async def our_lineup_players(db: AsyncSession, org, match_id: str) -> tuple[list[dict], list[str]]:
    """The club's own published XI for a match, as ``(players, unmatched)``.

    ``players`` are the ones we could resolve to a real player row (the shape
    the vote engine needs: ``{id, name, is_captain}``); ``unmatched`` are the
    published names we hold no player for — a genuine fill-in, or a junior CA
    redacted. Surfaced rather than silently dropped so an admin can see why the
    votable list is short.
    """
    data = await match_lineups(db, org, match_id)
    if not data:
        return [], []
    team = next((t for t in data["teams"] if t["is_ours"]), None)
    if team is None:
        return [], []
    players, unmatched = [], []
    for p in team["players"]:
        if p.get("player_id"):
            players.append({
                "id": p["player_id"],
                "name": p["name"],
                "is_captain": p["is_captain"],
            })
        else:
            unmatched.append(p["name"] or "Unknown")
    players.sort(key=lambda x: x["name"].lower())
    return players, unmatched
