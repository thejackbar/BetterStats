"""BetterSocials for an association workspace: a whole grade, not one club.

An association workspace (``organisations.workspace_kind = 'association'``) is an
organisation row with no Cricket Australia club behind it. It holds a brand
(name, crest, colours, fonts, sponsors) and nothing else: no seasons, grades or
players. Its posts are built from a pasted link, and every pull reads the WHOLE
grade that link names, every club in it, instead of one club's games.

Two link shapes name a round:

  - a match link, ``play.cricket.com.au/match/<match id>/...``: the match's
    grade, and the round that match is in;
  - a grade link, ``play.cricket.com.au/grade/<grade id>?roundId=<round id>``:
    that grade and round. Without ``roundId`` the round is the next one to be
    played (fixtures, lineups) or the last one finished (results, team of the
    week, player of the match).

A bare id is tried as a match, then as a grade. Both ids are Grassroots ids, so
the round resolves on Cricket Australia's own feed with no club to search from.
A PlayHQ game-centre short code cannot: it is a different id namespace and only
resolves against a club's own grades (see services/social_match_lookup.py).

A round is the matches in the grade whose ``round.id`` matches. That covers both
days of a two-day game, which a date window would miss.

Every row is read from the HOME side: the home team is named first, and in the
shapes the editor already draws (``grade`` / ``opp`` / ``us`` / ``them`` /
``outcome``) the home team stands where a club's own grade would. ``home`` and
``neutral`` mark the row so a layout can drop wording that only makes sense for
one club (a round record, a HOME / AWAY label).

Nothing here reads or writes a club's data. The workspace's own id never appears
in a match, so ``club_match`` name matching is never used: a workspace called
"Applecross Social" would otherwise claim Applecross's games.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services.lineups import normalise_team
from app.services.social_rounds import (
    _NO_ROUND_MESSAGE,
    _NO_ROUND_MESSAGE_LIVE,
    _TOTW_POOL,
    _label,
    _match_day_time,
    _mono,
    _our_keeper_guids,
    _pool_round,
    _rank_our_side,
    _resolve_opp_logos,
    _result_row,
    _round_label,
    _to_12h,
    _totw_kind,
    TOTW_MODES,
)
from app.services.sync import strip_team_suffix

WORKSPACE_ASSOCIATION = "association"

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_UUID_RE = re.compile(_UUID)
_GRADE_RE = re.compile(rf"/grade/({_UUID})", re.I)
_MATCH_RE = re.compile(rf"/match/({_UUID})", re.I)
_ROUND_RE = re.compile(rf"[?&]roundId=({_UUID})", re.I)
_PLAYHQ_RE = re.compile(r"game-centre/[0-9a-f]{8}(?:[/?#]|$)", re.I)

# One grade round is a handful of matches; this only stops a malformed list
# fanning out into hundreds of scorecard reads.
_MAX_ROUND_MATCHES = 16

# Cricket Australia status ids on a grade match list: 0 upcoming, 2 in play,
# 3 completed, 4 abandoned (and other finished-without-a-result states above).
_LIVE = "2"
_DONE = "3"
_AHEAD = {"0", "1", "2"}

INVALID_MESSAGE = (
    "Paste a play.cricket.com.au match link, or a grade link with the round picked "
    "(it has roundId= in it)."
)
PLAYHQ_MESSAGE = (
    "That is a PlayHQ game-centre link, which can only be read for a club's own games. "
    "Open the match on play.cricket.com.au and copy that link instead, or copy the grade's "
    "Matches page link."
)
NOT_FOUND_MESSAGE = "Cricket Australia has no match or grade for that link."

_CLUB_SUFFIX_RE = re.compile(
    r"\s+(district\s+cricket\s+club|cricket\s+club|cricket\s+association|c\.?c\.?)\s*$", re.I,
)


def is_association(org) -> bool:
    """Is this organisation an association socials workspace?"""
    return (getattr(org, "workspace_kind", None) or "") == WORKSPACE_ASSOCIATION


def parse_competition_reference(raw: str) -> dict | None:
    """What a pasted link names: ``{match_id}``, ``{grade_id, round_id}``,
    ``{id}`` (a bare id, match or grade unknown), ``{playhq: True}``, or None."""
    text = (raw or "").strip()
    if not text:
        return None
    g = _GRADE_RE.search(text)
    if g:
        r = _ROUND_RE.search(text)
        return {"grade_id": g.group(1).lower(), "round_id": r.group(1).lower() if r else None}
    m = _MATCH_RE.search(text)
    if m:
        return {"match_id": m.group(1).lower()}
    if _PLAYHQ_RE.search(text) or re.fullmatch(r"[0-9a-fA-F]{8}", text):
        return {"playhq": True}
    u = _UUID_RE.search(text)
    if u:
        return {"id": u.group(0).lower()}
    return None


def short_club(name: str | None) -> str:
    """'Western Suburbs Cricket Club' -> 'Western Suburbs'."""
    n = (name or "").strip()
    return _CLUB_SUFFIX_RE.sub("", n).strip() or n


def _round_id(m: dict) -> str:
    return str(((m.get("round") or {}).get("id")) or "").lower()


def _round_name(m: dict) -> str:
    return ((m.get("round") or {}).get("name") or "").strip()


def _sides(m: dict) -> tuple[dict, dict]:
    """(home, away) team dicts from a grade match list item or a match detail
    (``matchSummary.teams`` first, the same dual read as social_rounds)."""
    ms_teams = (m.get("matchSummary") or {}).get("teams") or []
    teams = ms_teams or (m.get("teams") or [])
    home = next((t for t in teams if t.get("isHome")), None)
    away = next((t for t in teams if t is not home), None)
    if home is None and teams:
        home = teams[0]
        away = teams[1] if len(teams) > 1 else None
    return home or {}, away or {}


def _club_of(team: dict) -> dict:
    org = team.get("owningOrganisation") or {}
    return {"id": (org.get("id") or "").lower() or None, "name": org.get("name") or "", "logo": org.get("logoUrl")}


def _labels(matches: list[dict]) -> dict[str, str]:
    """team id -> the name a post prints for it. A club's short name, since in one
    grade every side is that club's team; a club with two sides in the grade
    (Red and Black) keeps each side's own name so they stay apart.

    A scorecard's ``matchSummary.teams`` carries no owning club, its top-level
    ``teams`` does, so both are read and merged by team id."""
    teams: dict[str, dict] = {}
    for m in matches:
        for t in list(_sides(m)) + list(m.get("teams") or []):
            tid = (t.get("id") or "").lower()
            if not tid:
                continue
            held = teams.setdefault(tid, {})
            for k, v in t.items():
                if v and not held.get(k):
                    held[k] = v
    per_club: dict[str, int] = {}
    for t in teams.values():
        cid = _club_of(t)["id"] or (t.get("displayName") or "")
        per_club[cid] = per_club.get(cid, 0) + 1
    out: dict[str, str] = {}
    for tid, t in teams.items():
        club = _club_of(t)
        cid = club["id"] or (t.get("displayName") or "")
        if club["name"] and per_club.get(cid, 0) == 1:
            out[tid] = short_club(club["name"]).upper()
        else:
            out[tid] = (t.get("displayName") or club["name"] or "TBC").upper()
    return out


def _season_label(day: str) -> str:
    """'2026/27' from a match day, Australian season convention (July start)."""
    try:
        d = date.fromisoformat(day)
    except (TypeError, ValueError):
        return ""
    start = d.year if d.month >= 7 else d.year - 1
    return f"{start}/{str(start + 1)[-2:]}"


def _pick_round(matches: list[dict], want: str) -> str | None:
    """The round a grade link without ``roundId`` means. ``ahead`` is the next
    round to be played (the earliest match not finished), falling back to the
    last; ``done`` is the last round with a finished match, falling back to the
    first."""
    def first_day(m):
        return _match_day_time(m)[0] or ""

    def last_day(m):
        return _match_day_time(m, last=True)[0] or ""

    if want == "ahead":
        pending = sorted((m for m in matches if str(m.get("statusId")) in _AHEAD), key=first_day)
        pick = pending[0] if pending else (sorted(matches, key=last_day)[-1] if matches else None)
    else:
        done = sorted((m for m in matches if str(m.get("statusId")) in (_DONE, _LIVE)), key=last_day)
        pick = done[-1] if done else (sorted(matches, key=first_day)[0] if matches else None)
    return _round_id(pick) if pick else None


async def resolve_round(raw: str, want: str = "done") -> tuple[dict | None, dict | None]:
    """A pasted link -> ``(error, None)`` or ``(None, ctx)``.

    ctx: ``grade_id``, ``grade_name``, ``round_id``, ``round_name``, ``matches``
    (grade match list items in that round, first day order), ``labels`` (team id
    -> printed name), ``anchor`` (the match the link named, else None)."""
    ref = parse_competition_reference(raw)
    if not ref:
        return {"kind": "invalid", "message": INVALID_MESSAGE}, None
    if ref.get("playhq"):
        return {"kind": "playhq", "message": PLAYHQ_MESSAGE}, None

    anchor = None
    grade_id = ref.get("grade_id")
    round_id = ref.get("round_id")
    match_id = ref.get("match_id") or ref.get("id")
    if match_id and not grade_id:
        anchor = await gr.get_match_detail(match_id)
        if anchor:
            grade_id = str(((anchor.get("grade") or {}).get("id")) or "").lower() or None
            round_id = _round_id(anchor) or None
        elif ref.get("id"):
            grade_id = ref["id"]  # a bare id that is not a match: try it as a grade
    if not grade_id:
        return {"kind": "not_found", "message": NOT_FOUND_MESSAGE}, None

    all_matches = await gr.get_grade_matches(grade_id)
    if not all_matches:
        return {"kind": "not_found", "message": NOT_FOUND_MESSAGE}, None
    if not round_id:
        round_id = _pick_round(all_matches, want)

    in_round = [m for m in all_matches if round_id and _round_id(m) == round_id]
    if not in_round and anchor is not None:
        # A list with no round ids: fall back to the anchor's round name.
        name = _round_name(anchor).lower()
        in_round = [m for m in all_matches if name and _round_name(m).lower() == name]
    if not in_round:
        return {"kind": "no_results", "message": "That round has no matches in this grade."}, None

    seen: set = set()
    matches = []
    for m in sorted(in_round, key=lambda x: _match_day_time(x)):
        mid = m.get("id")
        if mid and mid not in seen:
            seen.add(mid)
            matches.append(m)
    matches = matches[:_MAX_ROUND_MATCHES]

    grade_name = ((anchor or {}).get("grade") or {}).get("name") or ""
    if not grade_name:
        detail = await gr.get_match_detail(matches[0].get("id"))
        grade_name = ((detail or {}).get("grade") or {}).get("name") or ""

    return None, {
        "grade_id": grade_id,
        "grade_name": grade_name,
        "round_id": round_id,
        "round_name": _round_name(matches[0]) or _round_name(anchor or {}),
        "matches": matches,
        "labels": _labels(matches),
        "anchor": anchor,
    }


def _club_dict(org) -> dict:
    return {"name": org.name, "short": getattr(org, "short_name", None) or org.name}


def _bucket(ctx: dict, day: str, rows_key: str, rows: list[dict]) -> dict:
    return {
        "date": day,
        "label": _label(day) if day else "",
        "round": _round_label(ctx["round_name"]),
        "comp": (ctx["grade_name"] or "").upper(),
        rows_key: rows,
    }


async def _crests(db: AsyncSession, org, entries: list[tuple]) -> list[dict]:
    """``{logo, colour, colour2}`` per ``(ca_org_id, raw_url, name)``: the
    workspace's crest library first (the crest fetched once, its plain
    background taken off, services/association_crests.py), else a club
    registered here prints its own uploaded crest, else Cricket Australia's."""
    from app.services.association_crests import resolve_crests
    fallback = await _resolve_opp_logos(db, [(ca, raw) for ca, raw, _ in entries])
    return await resolve_crests(db, org, entries, fallback)


async def _attach_logos(db: AsyncSession, org, rows: list[dict]) -> None:
    """In place: ``homeLogo``/``oppLogo`` and ``homeColor``/``oppColor`` from the
    transient club ids and CDN urls, in one batched lookup for the round."""
    home = [(r.pop("_homeOrgId", None), r.pop("_homeLogoRaw", None), r.get("homeClub")) for r in rows]
    away = [(r.pop("_oppOrgId", None), r.pop("_oppLogoRaw", None), r.get("oppClub")) for r in rows]
    got = await _crests(db, org, home + away)
    n = len(rows)
    for i, r in enumerate(rows):
        for side, c in (("home", got[i]), ("opp", got[n + i])):
            if c["logo"]:
                r[f"{side}Logo"] = c["logo"]
            if c["colour"]:
                r[f"{side}Color"] = c["colour"]


def _side_fields(ctx: dict, home: dict, away: dict) -> dict:
    hid, aid = (home.get("id") or "").lower(), (away.get("id") or "").lower()
    hc, ac = _club_of(home), _club_of(away)
    h_label = ctx["labels"].get(hid) or (home.get("displayName") or "HOME").upper()
    a_label = ctx["labels"].get(aid) or (away.get("displayName") or "AWAY").upper()
    return {
        # `grade` is where a club's roundup prints its own side, so every layout
        # names the home team first without a layout of its own.
        "grade": h_label,
        "home": h_label,
        "homeClub": (hc["name"] or "").upper(),
        "homeMono": _mono(hc["name"] or home.get("displayName") or ""),
        "homeTeam": (home.get("displayName") or "").upper(),
        "opp": a_label,
        "oppClub": (ac["name"] or "").upper(),
        "oppMono": _mono(ac["name"] or away.get("displayName") or ""),
        "oppTeam": (away.get("displayName") or "").upper(),
        "neutral": True,
        "categories": [],
        "_homeOrgId": hc["id"],
        "_homeLogoRaw": hc["logo"],
        "_oppOrgId": ac["id"],
        "_oppLogoRaw": ac["logo"],
    }


async def competition_fixtures(db: AsyncSession, org, raw: str) -> dict:
    """Every match in the grade's round, home team first, any status."""
    err, ctx = await resolve_round(raw, want="ahead")
    if err is not None:
        return err
    rows = []
    for m in ctx["matches"]:
        home, away = _sides(m)
        day, tm = _match_day_time(m)
        rows.append({
            **_side_fields(ctx, home, away),
            "ha": "H",
            "time": _to_12h(tm),
            "day": _label(day) if day else "",
            "venue": (((m.get("venue") or {}).get("name")) or "").upper(),
            "matchId": m.get("id"),
        })
    await _attach_logos(db, org, rows)
    day = _match_day_time(ctx["matches"][0])[0]
    return {
        "kind": "round", "neutral": True, "season": _season_label(day), "club": _club_dict(org),
        "grade": ctx["grade_name"], "dates": [_bucket(ctx, day, "fixtures", rows)],
    }


def _has_innings(sc) -> bool:
    return isinstance(sc, dict) and bool(sc.get("innings"))


async def _round_cards(ctx: dict, include_live: bool) -> tuple[list[tuple[dict, dict]], list[str]]:
    """``([(grade list item, scorecard)], skipped)`` for the round's finished
    matches, and the ones in play when ``include_live`` (re-read, never cached).

    Cricket Australia now and then serves a finished match with no innings at all
    (seen live on a WASTCA 2nd Grade game: three reads in a row came back bare).
    Such a card is read once more, past the cache; one still bare is left out and
    named in ``skipped`` ("APPLECROSS V WESTERN SUBURBS") so the editor can say
    so rather than post a round one match short without a word."""
    statuses = {_DONE, _LIVE} if include_live else {_DONE}
    picked = [m for m in ctx["matches"] if str(m.get("statusId")) in statuses]
    cards = list(await asyncio.gather(
        *[gr.get_match_scorecard(m.get("id"), force=str(m.get("statusId")) == _LIVE) for m in picked],
        return_exceptions=True,
    ))
    bare = [i for i, sc in enumerate(cards) if not _has_innings(sc)]
    if bare:
        again = await asyncio.gather(
            *[gr.get_match_scorecard(picked[i].get("id"), force=True) for i in bare], return_exceptions=True,
        )
        for i, sc in zip(bare, again):
            if _has_innings(sc):
                cards[i] = sc
    kept, skipped = [], []
    for m, sc in zip(picked, cards):
        if _has_innings(sc):
            kept.append((m, sc))
        else:
            home, away = _sides(m)
            h = ctx["labels"].get((home.get("id") or "").lower()) or (home.get("displayName") or "")
            a = ctx["labels"].get((away.get("id") or "").lower()) or (away.get("displayName") or "")
            skipped.append(f"{h} V {a}".strip())
    return kept, skipped


_LEAD_RE = re.compile(r"^(\d+)\*?\s*\((\d+)\)")
_BOWL_RE = re.compile(r"^(\d+)/(\d+)")


def _leaders(row: dict) -> tuple[list[dict], list[dict]]:
    """The match's top two run scorers and top two wicket takers from BOTH
    sides, each tagged with their side (``team``: ``home`` or ``away``). Read
    from the per-side top two the row already carries, since the best two of a
    match are always among each side's best two."""
    def bat_key(p):
        m = _LEAD_RE.match(p.get("line") or "")
        return (-int(m.group(1)), int(m.group(2))) if m else (0, 0)

    def bowl_key(p):
        m = _BOWL_RE.match(p.get("line") or "")
        return (-int(m.group(1)), int(m.group(2))) if m else (0, 0)

    bats = [{**p, "team": "home"} for p in row.get("topBat") or []] + \
           [{**p, "team": "away"} for p in row.get("oppTopBat") or []]
    bowls = [{**p, "team": "home"} for p in row.get("topBowl") or []] + \
            [{**p, "team": "away"} for p in row.get("oppTopBowl") or []]
    return sorted(bats, key=bat_key)[:2], sorted(bowls, key=bowl_key)[:2]


async def competition_results(db: AsyncSession, org, raw: str, include_live: bool = False) -> dict:
    """The round's results across the whole grade, each read from the home side."""
    err, ctx = await resolve_round(raw, want="done")
    if err is not None:
        return err
    no_round = _NO_ROUND_MESSAGE_LIVE if include_live else _NO_ROUND_MESSAGE
    pairs, skipped = await _round_cards(ctx, include_live)
    rows = []
    for m, sc in pairs:
        home, away = _sides(m)
        hid = (home.get("id") or "").lower()
        live = str(m.get("statusId")) == _LIVE
        row = _result_row(sc, None, [], "", None, live=live, team_id=hid)
        if not row:
            continue
        row.pop("_oppOrgId", None)
        row.pop("_oppLogoRaw", None)
        row.update(_side_fields(ctx, home, away))
        row["matchId"] = m.get("id")
        # Neither side is the association's: a post leads with the match's best
        # from both sides, and names the winner rather than a W or an L.
        row["leadBat"], row["leadBowl"] = _leaders(row)
        row["winnerSide"] = "home" if row.get("outcome") == "W" else "away" if row.get("outcome") == "L" else None
        rows.append(row)
    if not rows:
        return {"kind": "no_results", "message": no_round, "skipped": skipped}
    await _attach_logos(db, org, rows)
    day = _match_day_time(pairs[-1][0], last=True)[0] if pairs else ""
    return {
        "kind": "round", "neutral": True, "season": _season_label(day), "club": _club_dict(org),
        "grade": ctx["grade_name"], "dates": [_bucket(ctx, day, "results", rows)], "skipped": skipped,
    }


def apply_club_cap(pool: list[dict], cap: int) -> list[dict]:
    """Reorder a ranked pool so that, read from the top, no club has more than
    ``cap`` players. A player past their club's cap is moved below everyone who
    fits and flagged ``overCap`` so a hand swap can still reach them. Past the
    cap the clubs take turns (each club's next ``cap`` before anyone's third
    batch), so a grade with fewer clubs than places still spreads the team.
    ``cap`` of 0 or less leaves the pool alone."""
    if cap <= 0:
        return pool
    seen: dict[str, int] = {}
    tiers: list[tuple[int, int, dict]] = []
    for i, p in enumerate(pool):
        key = p.get("clubId") or p.get("club") or ""
        n = seen.get(key, 0)
        seen[key] = n + 1
        # Tier 0 is each club's best `cap`; tier 1 their next `cap`, and so on.
        # Past the cap, a club's next player waits behind every other club's
        # same-depth player, so a short grade spreads its extra places across
        # clubs rather than handing them all to the strongest one.
        tier = n // cap
        tiers.append((tier, i, p if tier == 0 else {**p, "overCap": True}))
    return [p for _, _, p in sorted(tiers, key=lambda x: (x[0], x[1]))]


async def competition_totw(
    db: AsyncSession, org, q: str = "", mode: str = "week", cap: int = 0,
) -> dict:
    """Team of the week across every club in the grade's round: both sides of
    every match ranked with the club team of the week's own points, pooled one
    entry per player (their better performance), then capped per club."""
    if not (q or "").strip():
        return {"kind": "invalid", "message": INVALID_MESSAGE}
    mode = (mode or "week").strip().lower()
    if mode not in TOTW_MODES:
        mode = "week"
    live_ok = mode == "round"
    err, ctx = await resolve_round(q, want="done")
    if err is not None:
        return err
    pairs, skipped = await _round_cards(ctx, live_ok)
    tasks = []
    for m, sc in pairs:
        for team in sc.get("teams") or []:
            if team.get("id"):
                tasks.append((m, sc, team))

    crests = await _crests(db, org, [(_club_of(t)["id"], _club_of(t)["logo"], _club_of(t)["name"]) for _, _, t in tasks])

    scored = []
    live_matches = set()
    for (m, sc, team), crest in zip(tasks, crests):
        logo = crest["logo"]
        tid = (team.get("id") or "").lower()
        try:
            ranked = await _rank_our_side(db, org, sc, team_id=tid)
        except HTTPException:
            continue
        live = str(m.get("statusId")) == _LIVE
        if live:
            live_matches.add(m.get("id"))
        home, away = _sides(m)
        opp = away if (home.get("id") or "").lower() == tid else home
        label = ctx["labels"].get(tid) or (team.get("displayName") or "").upper()
        opp_label = ctx["labels"].get((opp.get("id") or "").lower()) or (opp.get("displayName") or "").upper()
        club = _club_of(team)
        block = dict(ranked["match"])
        block.update({
            "grade": label, "opponent": opp_label, "oppMono": _mono(_club_of(opp)["name"] or opp_label),
            "categories": [],
        })
        if live:
            block["live"] = True
        keepers = _our_keeper_guids(org, sc, team_id=tid)
        players = []
        for p in ranked["players"]:
            fld = p.get("fielding") or {}
            keeper = p["guid"] in keepers or bool(fld.get("catches_wk") or fld.get("stumpings"))
            players.append({
                **p,
                # No player of an association workspace is held here, so a
                # player is their scorecard participant, never a club player id.
                "pid": None,
                "keeper": keeper,
                "kind": _totw_kind(p, keeper),
                "club": label,
                "clubFull": (club["name"] or "").upper(),
                "clubId": club["id"] or tid,
                "clubMono": _mono(club["name"] or label),
                "clubLogo": logo,
                "clubColor": crest["colour"],
            })
        scored.append((block, players))
    pool = _pool_round(scored)
    if not pool:
        return {"kind": "no_results", "message": _NO_ROUND_MESSAGE_LIVE if live_ok else _NO_ROUND_MESSAGE,
                "skipped": skipped}
    pool = apply_club_cap(pool, cap)
    day = _match_day_time(pairs[-1][0], last=True)[0] if pairs else ""
    return {
        "kind": "round",
        "neutral": True,
        "season": _season_label(day),
        "club": _club_dict(org),
        "grade": ctx["grade_name"],
        "comp": (ctx["grade_name"] or "").upper(),
        "round": _round_label(ctx["round_name"]),
        "date": day,
        "label": _label(day) if day else "",
        "matches": len({m.get("id") for m, _ in pairs}),
        "scope": "all",
        "mode": mode,
        "cap": max(0, cap),
        # How many clubs the pool holds: a cap below team size / clubs cannot be met.
        "clubs": len({p.get("clubId") or p.get("club") for p in pool}),
        "liveMatches": len(live_matches),
        "skipped": skipped,
        "scopeMatches": {"junior": 0, "senior": len(pairs)},
        "players": pool[:_TOTW_POOL],
    }


async def competition_potm(db: AsyncSession, org, match_id: str) -> dict:
    """Player of the match from BOTH sides of one match, best first. The match
    block reads from the home side, the same way the results rows do."""
    raw = await gr.get_match_scorecard(match_id)
    if raw is None:
        raise HTTPException(404, "Scorecard not found. The match may not be finished yet.")
    home, away = _sides(raw)
    labels = _labels([raw])
    hid = (home.get("id") or "").lower()
    teams = [t for t in (raw.get("teams") or []) if t.get("id")]
    crests = await _crests(db, org, [(_club_of(t)["id"], _club_of(t)["logo"], _club_of(t)["name"]) for t in teams])
    logo_by_team = {(t.get("id") or "").lower(): c["logo"] for t, c in zip(teams, crests)}
    colour_by_team = {(t.get("id") or "").lower(): c["colour"] for t, c in zip(teams, crests)}
    match = None
    players = []
    for team in teams:
        tid = (team.get("id") or "").lower()
        try:
            ranked = await _rank_our_side(db, org, raw, team_id=tid)
        except HTTPException:
            continue
        label = labels.get(tid) or (team.get("displayName") or "").upper()
        club = _club_of(team)
        opp = next((t for t in teams if (t.get("id") or "").lower() != tid), {})
        oid = (opp.get("id") or "").lower()
        if tid == hid or match is None:
            match = dict(ranked["match"])
        for p in ranked["players"]:
            # Each player carries their own side and the side they played, so
            # the post can feature that player's club whichever side they were on.
            players.append({
                **p, "pid": None,
                "club": label, "clubFull": (club["name"] or "").upper(),
                "clubMono": _mono(club["name"] or label), "clubLogo": logo_by_team.get(tid),
                "clubColor": colour_by_team.get(tid),
                "opp": labels.get(oid) or (opp.get("displayName") or "").upper(),
                "oppMono": _mono(_club_of(opp)["name"] or opp.get("displayName") or ""),
                "oppLogo": logo_by_team.get(oid),
                "us": ranked["match"].get("us"), "them": ranked["match"].get("them"),
                "outcome": ranked["match"].get("outcome"),
            })
    if match is None:
        raise HTTPException(404, "Scorecard not found. The match may not be finished yet.")
    match["opponent"] = labels.get((away.get("id") or "").lower()) or match.get("opponent")
    match["home"] = labels.get(hid) or ""
    match["neutral"] = True
    players.sort(key=lambda x: -x["points"])
    return {"match": match, "players": players}


async def competition_lineups(db: AsyncSession, org, raw: str) -> dict:
    """Both published sides of every match in the grade's round, in the payload
    shape of the club Lineups list (``matches[].teams[]``). No side is ours: the
    editor asks which one to post."""
    err, ctx = await resolve_round(raw, want="ahead")
    if err is not None:
        return err
    ids = [m.get("id") for m in ctx["matches"] if m.get("id")]
    details = await gr.get_matches_detail(ids)
    out = []
    for mid in ids:
        d = details.get(mid)
        if not d:
            continue
        summary = d.get("matchSummary") or {}
        by_id = {str(s.get("id")).lower(): s for s in (summary.get("teams") or []) if s.get("id")}
        teams = []
        for t in d.get("teams") or []:
            nt = normalise_team(t)
            s = by_id.get(str(nt.get("id") or "").lower()) or {}
            nt["published"] = bool(nt["players"])
            nt["is_home"] = bool(s.get("isHome"))
            nt["is_ours"] = False
            nt["is_club"] = False
            nt["label"] = ctx["labels"].get(str(nt.get("id") or "").lower()) or (nt.get("name") or "").upper()
            for p in nt["players"]:
                p["player_id"] = None
                p["photo_url"] = None
            teams.append(nt)
        teams.sort(key=lambda t: not t["is_home"])
        crests = await _crests(db, org, [(t.get("club_id"), t.get("logo_url"), t.get("club")) for t in teams])
        for t, c in zip(teams, crests):
            t["logo_url"] = c["logo"]
            t["color"] = c["colour"]
        days = gr.schedule_days(d)
        start = days[0][1] if days else ""
        out.append({
            "match_id": d.get("id") or mid,
            "status": d.get("status"),
            "date": start[:10] or None,
            "time": start[11:16] if len(start) >= 16 else None,
            "round": (d.get("round") or {}).get("name"),
            "grade": (d.get("grade") or {}).get("name") or ctx["grade_name"],
            "venue": (d.get("venue") or {}).get("name"),
            "teams": teams,
            "any_published": any(t["published"] for t in teams),
        })
    return {
        "kind": "round", "neutral": True, "grade": ctx["grade_name"],
        "round": _round_label(ctx["round_name"]), "matches": out,
    }


async def competition_matches(raw: str) -> dict:
    """The round's matches as a short pick list (for the single-match post types:
    a scorecard, a match summary, player of the match)."""
    err, ctx = await resolve_round(raw, want="done")
    if err is not None:
        return err
    out = []
    for m in ctx["matches"]:
        home, away = _sides(m)
        day, tm = _match_day_time(m)
        out.append({
            "match_id": m.get("id"),
            "home": ctx["labels"].get((home.get("id") or "").lower()) or (home.get("displayName") or ""),
            "away": ctx["labels"].get((away.get("id") or "").lower()) or (away.get("displayName") or ""),
            "status": m.get("status"),
            "completed": str(m.get("statusId")) == _DONE,
            "date": day,
            "time": _to_12h(tm),
            "result": m.get("resultText") or "",
        })
    return {
        "kind": "round", "grade": ctx["grade_name"], "round": _round_label(ctx["round_name"]),
        "matches": out,
    }


__all__ = [
    "WORKSPACE_ASSOCIATION", "is_association", "parse_competition_reference", "resolve_round",
    "competition_fixtures", "competition_results", "competition_totw", "competition_potm",
    "competition_lineups", "competition_matches", "apply_club_cap", "short_club",
    "strip_team_suffix",
]


def needs_link() -> dict:
    """An association workspace has no club games to fall back on, so a pull
    without a link says what to paste."""
    return {"kind": "needs_link", "message": "Paste a play.cricket.com.au match or grade link to pull the whole grade."}


async def competition_match_reference(raw: str) -> dict:
    """match-lookup for a workspace: a match link resolves straight through; a
    grade link has no single match, so it says to pick one from the round."""
    ref = parse_competition_reference(raw)
    if not ref:
        return {"kind": "invalid", "message": INVALID_MESSAGE}
    if ref.get("playhq"):
        return {"kind": "playhq", "message": PLAYHQ_MESSAGE}
    mid = ref.get("match_id") or ref.get("id")
    if mid:
        return {"kind": "match", "source": "playcricket", "match_id": mid}
    return {"kind": "invalid", "message": "That is a grade link. Pick one of its matches, or paste a match link."}
