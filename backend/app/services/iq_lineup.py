"""BetterIQ: the opposition's NAMED XI for one fixture, matched to the players IQ
has already scanned.

A club publishes its team list on play.cricket.com.au ahead of the game, and the
plain match record (``/scores/matches/{id}``, no scorecard) carries it as
``teams[].players[]`` (see ``grassroots_scores_client.get_match_detail`` and the
public Lineups page, which reads the same route). This service:

1. takes the fixture's real match id (``Fixture.playhq_id``, the Grassroots match
   GUID; a manual fixture has none),
2. finds the OPPONENT's side in that record (never ours),
3. matches each named player to the opponent's dossier, the squad IQ scouted.

Matching is two pools, tried in order, because a named side is not always the
side a player usually plays in:

* **grade pool**: the dossier the Opposition page is showing (the fixture's
  grade, under the Grade Type / Match Type filters). These are the numbers the
  rest of the page uses.
* **other sides**: their whole club, with NO Grade Type / Match Type filter. A
  1st XI T20 batter named in the 3rds is exactly the player a selector wants
  flagged, and under a Two day filter he has no scouted form at all. He is
  matched here and labelled as form from another side or format, never blended
  into the grade pool.

Identity per player is the participant GUID first. CA is known to issue a
different GUID on this route than the scorecard sync stored (see
``services/lineups.py::_name_key``), so a name tier follows: full first name
and surname, then surname plus first initial. A name that fits two scouted
players matches neither. A redacted junior ("********") can only match by GUID.

Nothing here is stored: the team list changes up to the first ball, so it is
read live (five minute cache in the client) and matched on every request.
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services import iq as iq_service
from app.services import iq_filters, iq_opponent
from app.services.lineups import looks_redacted, normalise_team

logger = logging.getLogger(__name__)

# How the player was matched, best first. The UI shows the weaker two as "name match".
BASIS_ID, BASIS_NAME, BASIS_INITIAL = "id", "name", "initial"

_BAT_KEYS = ("innings", "runs", "average", "strike_rate", "high_score", "form", "recent_scores")
_BOWL_KEYS = ("matches", "overs", "wickets", "average", "economy", "best")


# ─── name matching ───────────────────────────────────────────────────────────

def _split_name(name: str | None) -> tuple[str, str]:
    """``(surname, first)`` lowercased, from "Surname, First" or "First Surname"."""
    n = (name or "").strip()
    if "," in n:
        surname, _, first = n.partition(",")
        return surname.strip().lower(), first.strip().split(" ")[0].lower() if first.strip() else ""
    words = n.split()
    if not words:
        return "", ""
    if len(words) == 1:
        return words[0].lower(), ""
    return words[-1].lower(), words[0].lower()


def _firsts_agree(a: str, b: str) -> bool:
    """Two first names that could be one person. An initial agrees with any name
    that starts with it; two full names must be equal or one a prefix of the
    other ("Dave" is not "David", but "Dan" is "Daniel" only when it is a prefix).
    Ashton is never Angus."""
    if not a or not b:
        return False
    if len(a) == 1 or len(b) == 1:
        return a[0] == b[0]
    return a == b or a.startswith(b) or b.startswith(a)


# ─── the scouted pool ────────────────────────────────────────────────────────

def _pool(dossier: dict | None) -> dict[str, dict]:
    """``player_id -> {name, bat, bowl, danger}`` over a dossier's squad."""
    pool: dict[str, dict] = {}
    if not dossier:
        return pool
    danger_bat = {str(d.get("player_id")) for d in (dossier.get("danger_batters") or []) if d.get("player_id")}
    danger_bowl = {str(d.get("player_id")) for d in (dossier.get("danger_bowlers") or []) if d.get("player_id")}
    for row in dossier.get("batting") or []:
        pid = row.get("player_id")
        if pid:
            e = pool.setdefault(str(pid), {"name": row.get("name"), "bat": None, "bowl": None})
            e["bat"] = row
    for row in dossier.get("bowling") or []:
        pid = row.get("player_id")
        if pid:
            e = pool.setdefault(str(pid), {"name": row.get("name"), "bat": None, "bowl": None})
            e["bowl"] = row
    for pid, e in pool.items():
        d_bat, d_bowl = pid in danger_bat, pid in danger_bowl
        e["danger"] = "both" if d_bat and d_bowl else "bat" if d_bat else "bowl" if d_bowl else None
    return pool


def _find(pool: dict[str, dict], participant_id: str | None, name: str | None, redacted: bool):
    """``(pid, basis)`` for one named player in one pool, or ``(None, None)``."""
    if participant_id and str(participant_id) in pool:
        return str(participant_id), BASIS_ID
    if redacted:
        return None, None
    surname, first = _split_name(name)
    if not surname or not first:
        return None, None
    same_surname = [(pid, e) for pid, e in pool.items() if _split_name(e.get("name"))[0] == surname]
    exact = [pid for pid, e in same_surname if _split_name(e.get("name"))[1] == first and len(first) > 1]
    if len(exact) == 1:
        return exact[0], BASIS_NAME
    if len(exact) > 1:
        return None, None  # two scouted players share the name: guess neither
    loose = [pid for pid, e in same_surname if _firsts_agree(first, _split_name(e.get("name"))[1])]
    if len(loose) == 1:
        return loose[0], BASIS_INITIAL
    return None, None


def _figures(entry: dict) -> dict:
    bat, bowl = entry.get("bat") or {}, entry.get("bowl") or {}
    row = bat or bowl
    return {
        "bat": {k: bat.get(k) for k in _BAT_KEYS} if bat else None,
        "bowl": {k: bowl.get(k) for k in _BOWL_KEYS} if bowl else None,
        "danger": entry.get("danger"),
        "alert": (bat.get("alert") or bowl.get("alert")),
        "plan": (bat.get("plan") or bowl.get("plan")),
        "confidence": row.get("confidence"),
        "vs_us": bat.get("vs_us") or bowl.get("vs_us"),
    }


def match_named(named: list[dict], grade_pool: dict[str, dict], other_pool: dict[str, dict] | None) -> list[dict]:
    """Each named player, with the scouted figures they matched (or none).

    ``pool`` on a row says where the figures came from: ``grade`` is the page's
    own scout, ``other_sides`` their whole club with no grade or format filter,
    None means nobody scouted anyone by this name.
    """
    out = []
    for p in named:
        redacted = bool(p.get("redacted")) or looks_redacted(p.get("name"))
        row = {
            "participant_id": p.get("participant_id"),
            "name": p.get("name"),
            "is_captain": bool(p.get("is_captain")),
            "is_keeper": bool(p.get("is_wicket_keeper")),
            "redacted": redacted,
            "matched": False, "basis": None, "pool": None, "player_id": None,
        }
        for label, pool in (("grade", grade_pool), ("other_sides", other_pool)):
            if not pool:
                continue
            pid, basis = _find(pool, p.get("participant_id"), p.get("name"), redacted)
            if pid:
                row.update(matched=True, basis=basis, pool=label, player_id=pid, **_figures(pool[pid]))
                break
        out.append(row)
    return out


# ─── fixture and match ───────────────────────────────────────────────────────

async def _fixture(session: AsyncSession, org_id: str, fixture_id: str) -> dict | None:
    row = (await session.execute(
        text(
            "SELECT id::text AS id, playhq_id, source, played_on, status, round, home_away "
            "FROM fixtures WHERE id = CAST(:fid AS UUID) AND organisation_id = CAST(:org AS UUID)"
        ),
        {"fid": fixture_id, "org": org_id},
    )).mappings().first()
    return dict(row) if row else None


def _opponent_team(detail: dict, *, our_org_id: str, opp_org_id: str | None, opp_name: str | None):
    """The opponent's raw ``teams[]`` entry in a match record, or None.

    Their own org id and club name decide it first. Failing that, "the side that
    isn't ours" is only safe when OURS is positively in the record (two teams,
    exactly one owned by our org): a record that names neither of us must not
    hand back a stranger's team list as the opponent's."""
    hit = iq_opponent._find_opponent_team(
        detail, our_org_id=None, opp_org_id=opp_org_id, opp_name=opp_name,
    )
    if hit is not None:
        return hit
    teams = detail.get("teams") or []
    ours = [t for t in teams if str((t.get("owningOrganisation") or {}).get("id") or "").lower() == our_org_id.lower()]
    if len(teams) == 2 and len(ours) == 1:
        return next(t for t in teams if t is not ours[0])
    return None


async def opponent_lineup(
    session: AsyncSession, club, *, fixture_id: str | None, opponent: str | None = None,
    team: str | None = None, grade: str | None = None, name: str | None = None,
    refresh: bool = False,
) -> dict:
    """The opponent's named XI for a fixture, matched to their scouted squad.

    ``status``: ``named`` | ``not_named`` (they have not published yet, a normal
    state) | ``no_match`` (no upstream match id: a manual fixture) |
    ``unavailable`` (Grassroots holds no record, or no opponent side in it) |
    ``building`` (the dossier is not ready; the caller polls). A ``named`` payload
    can carry ``pending: true`` while the whole-club pool is still being built.
    """
    org_id = str(club.id)
    if not fixture_id:
        return {"status": "no_match", "reason": "Pick a fixture to see who they have named."}
    fx = await _fixture(session, org_id, fixture_id)
    if not fx:
        return {"status": "no_match", "reason": "That fixture isn't one of yours."}
    match_id = (fx.get("playhq_id") or "").strip()
    if not match_id:
        return {"status": "no_match", "reason": "This fixture was added by hand, so there is no match to read a team list from."}

    opp_key, opp_name, grade_id = await iq_service.resolve_opponent(
        session, org_id, opponent=opponent, fixture_id=fixture_id, display_name=name,
    )
    key = opp_key or (opp_name if grade_id else None)

    detail = await gr.get_match_detail(match_id, force=refresh)
    if not detail:
        return {"status": "unavailable", "match_id": match_id,
                "reason": "Cricket Australia holds no match record for this fixture yet."}
    opp_org = opp_key if iq_opponent._is_uuid(opp_key or "") else None
    raw = _opponent_team(detail, our_org_id=org_id, opp_org_id=opp_org, opp_name=opp_name)
    if raw is None:
        return {"status": "unavailable", "match_id": match_id,
                "reason": "Couldn't tell which side in the match record is theirs."}
    side = normalise_team(raw)
    base = {
        "match_id": match_id,
        "match_status": detail.get("status"),
        "team_name": side["name"], "club": side["club"],
        "date": ((detail.get("matchSchedule") or [{}])[0].get("startDateTime") or "")[:10] or None,
        "grade": (detail.get("grade") or {}).get("name"),
        "staff": side["staff"],
    }
    if not side["players"]:
        return {**base, "status": "not_named", "named_count": 0}

    if not key:
        return {**base, "status": "unavailable", "reason": "No scouted squad to match them to yet."}

    # Pool 1: the dossier the page shows (same inputs as GET /iq/opposition/dossier).
    d1 = await iq_opponent.get_or_start_dossier(
        session, org_id, key, opp_name=opp_name, grade_id=grade_id,
        team_grade_id=team, grade_filter=grade,
    )
    if d1.get("status") != "ready":
        return {**base, "status": "building" if d1.get("status") == "building" else "unavailable",
                "reason": d1.get("message")}
    grade_pool = _pool(d1)
    rows = match_named(side["players"], grade_pool, None)

    # Pool 2: only for players pool 1 could not place, and only the whole club.
    pending = False
    if any(not r["matched"] for r in rows):
        token = iq_filters.set_scope(None)
        try:
            d2 = await iq_opponent.get_or_start_dossier(session, org_id, key, opp_name=opp_name)
        finally:
            iq_filters.reset_scope(token)
        if d2.get("status") == "ready":
            rows = match_named(side["players"], grade_pool, _pool(d2))
        elif d2.get("status") == "building":
            pending = True

    named_ids = {r["player_id"] for r in rows if r["player_id"]}
    dangers = [
        {"player_id": d.get("player_id"), "name": d.get("name"), "kind": kind}
        for kind, key_ in (("bat", "danger_batters"), ("bowl", "danger_bowlers"))
        for d in (d1.get(key_) or [])
    ]
    return {
        **base,
        "status": "named",
        "pending": pending,
        "named_count": len(rows),
        "scouted_count": sum(1 for r in rows if r["pool"] == "grade"),
        "other_sides_count": sum(1 for r in rows if r["pool"] == "other_sides"),
        "new_count": sum(1 for r in rows if not r["matched"] and not r["redacted"]),
        "redacted_count": sum(1 for r in rows if not r["matched"] and r["redacted"]),
        "players": rows,
        # Their scouted danger players, split by whether they are in the named XI.
        "danger_named": [d for d in dangers if d["player_id"] in named_ids],
        "danger_missing": [d for d in dangers if d["player_id"] not in named_ids],
        "scope": {"grade_filter": d1.get("grade_filter"), "scope_labels": d1.get("scope_labels") or []},
    }
