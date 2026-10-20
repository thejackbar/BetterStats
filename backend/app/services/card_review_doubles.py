"""Card review, step one: matches the record holds twice that nothing links.

Card review's other four groups all start from a LINKED pair (`manual_games.superseded_by_game_id`).
A match stored twice and never linked is invisible to them, and it is the worst kind: both copies
count, so a batter's career, the two-day and one-day tabs and every record board carry the match
twice. This module finds those, read only. Linking and dismissing live in `card_review_actions`.

TWO KINDS OF DOUBLE.

* ``ca``    a club scorecard (`manual_games`: a file import, a typed-in card or a photo) with no link,
            and a synced Cricket Australia game with no club scorecard linked to it, that look like
            one match. The fix is to link them, after which the match joins the normal review.
* ``relink`` a club card that IS linked, but to a game that does not match it, while an unlinked
            synced game matches it strongly. This is what an import leaves where a club plays several
            grades against one opposition on one day: its duplicate check ignores grade, so the "B
            grade" card is linked to the A grade game, the real B grade game stays unlinked, and the
            match counts twice (once the club card, once the unlinked game). Seen at Shoalwater Bay on
            four fixtures. The fix is to move the link to the right game (`card_review_actions.relink`);
            the game it leaves is free again and, if its own card is unlinked, shows up as a ``ca`` pair
            on the next scan. A link a person decided (`review_source = 'hand'`, or confirmed with
            `review_pair_ok`) is never second-guessed, and only a strong match is offered.
* ``club``  two club scorecards that look like one match, at least one of them unlinked (a file
            imported twice, or an import beside a hand-typed or photographed card). The other may
            already be linked to its Cricket Australia game: that is what a second import of a
            linked match leaves behind. There is no link between two club cards, so the fix is to
            remove the extra copy through Manual Entries, which keeps the audit trail and the undo.
            Nothing here removes anything.

THE EVIDENCE IS `match_pairing.score_pair`, NOT A SECOND COPY OF ITS RULES. The same function
decides whether a CricketStatz match is a synced game, so a club card and a synced game that this
step offers are the pairs the automatic matcher would have written had the club card been one it
looks at (it only reads CricketStatz imports). Two things are added on top, both to keep a list a
person has to read honest:

* two cards that BOTH hold batters and share none are two different matches, not a double. The
  matcher accepts "same day, same club" on its own; here it also needs one shared score when both
  cards are there to compare (two grades play one club on one Saturday);
* two club cards need more than a date, because a club files two grades against one opposition on
  one day all the time. They need two shared scores, or one shared score on the same day, or (no
  cards at all) the same day, the same grade and the same opposition. And they must be within ten
  days of each other: two imports months apart are two matches whatever their scores.

A person's "these are different matches" is a row in ``card_review_log`` (action ``not_double``),
so it is undoable and keyed on the pair, not on the match: a second candidate for the same club
card is still offered. Each card and each synced game is offered at most once, strongest first.

STRENGTH, so the list can be read from the top. When both cards hold batters the bar is the one
the automatic pairing trusts (`card_review.confirms_pair`: 60% of the smaller card, at least two),
NOT a count of coincidences: a low-scoring team shares two scores with any other week's card, and
two shared scores once offered two different matches (different opposition, one a win and one a
loss) as "strong".

* ``strong``   both cards hold batters and the smaller card is mostly on the other.
* ``likely``   both hold batters, only some agree (the two sources can name a player differently),
               but it is the same day and the opposition names agree.
* ``possible`` one card has no batters to compare, so the date and the opposition are all there is.

Two cards that both hold batters and are neither are two different matches and are never offered.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Optional

from sqlalchemy import text

from app.services import card_review as cr
from app.services import match_pairing as mp

KINDS = ("ca", "club", "relink")
STRENGTHS = ("strong", "likely", "possible")

_MANUALS = """
    SELECT mg.id::text AS mid, mg.played_at, COALESCE(mg.opposition, '') AS opposition,
           COALESCE(mg.home_team, '') AS home_team, COALESCE(mg.away_team, '') AS away_team,
           mg.match_format, mg.result AS m_result, mg.grade_id::text AS grade_id,
           s.name AS season_name, COALESCE(gr.display_name_override, gr.name) AS grade_name,
           mg.cricketstatz_import_id IS NOT NULL AS from_cricketstatz,
           mg.extracted_payload IS NOT NULL AS has_payload, mg.created_at,
           mg.created_by_user_id, mg.superseded_by_game_id IS NOT NULL AS linked,
           mg.superseded_by_game_id::text AS linked_to, mg.review_pair_ok, mg.review_source
      FROM manual_games mg
      LEFT JOIN seasons s ON s.id = mg.season_id
      LEFT JOIN grades gr ON gr.id = mg.grade_id
     WHERE mg.organisation_id = CAST(:org AS UUID)
"""

_SYNCED_DETAIL = """
    SELECT g.id::text AS gid, g.played_at, g.match_format, g.result AS g_result, g.winning_team,
           g.home_team, g.away_team, g.home_org_id::text AS home_org, g.away_org_id::text AS away_org,
           s.name AS season_name, COALESCE(gr.display_name_override, gr.name) AS grade_name,
           CASE WHEN g.home_org_id = CAST(:org AS UUID) THEN g.away_team
                WHEN g.away_org_id = CAST(:org AS UUID) THEN g.home_team
                ELSE COALESCE(g.opp_club_name, g.home_team || ' v ' || g.away_team) END AS opposition
      FROM games g
      LEFT JOIN grades gr ON gr.id = g.grade_id
      LEFT JOIN seasons s ON s.id = gr.season_id
     WHERE g.id = ANY(CAST(:ids AS UUID[]))
"""

_BOWLERS = """
    SELECT manual_game_id::text AS mid, count(*) AS n
      FROM manual_bowling_spells WHERE manual_game_id = ANY(CAST(:ids AS UUID[])) GROUP BY manual_game_id
"""
_CA_BOWLERS = """
    SELECT bs.game_id::text AS gid, count(*) AS n
      FROM bowling_spells bs JOIN players p ON p.id = bs.player_id AND p.organisation_id = CAST(:org AS UUID)
     WHERE bs.game_id = ANY(CAST(:ids AS UUID[])) GROUP BY bs.game_id
"""

_DISMISSED = """
    SELECT l.id, l.manual_game_id::text AS mid, l.detail->>'other_id' AS other,
           COALESCE(l.detail->>'other_kind', 'ca') AS kind, l.created_at, u.username
      FROM card_review_log l LEFT JOIN users u ON u.id = l.user_id
     WHERE l.org_id = CAST(:org AS UUID) AND l.action = 'not_double' AND l.undone_at IS NULL
     ORDER BY l.id DESC
"""


async def _all(db, sql, **params):
    return [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]


def pair_key(kind: str, a: str, b: str) -> tuple:
    """A dismissed pair, the same whichever way round it was written."""
    return (kind, a, b) if kind == "ca" else (kind, *sorted((a, b)))


def _evidence(a: mp.MatchRow, b: mp.MatchRow) -> dict:
    gap = mp._day_gap(a.played_at, b.played_at)
    return {"shared": len(a.signature & b.signature), "gap_days": gap, "same_day": gap == 0,
            "opposition_agrees": mp.teams_agree(a.opposition, b.opposition),
            "both_cards": a.has_card and b.has_card,
            "confirmed": cr.confirms_pair(a.signature, b.signature)}


def strength_of(ev: dict) -> Optional[str]:
    """strong, likely or possible; None when the two cards are plainly two matches."""
    if not ev["both_cards"]:
        return "possible"
    if ev["confirmed"]:
        return "strong"
    if ev["shared"] >= 1 and ev["same_day"] and ev["opposition_agrees"]:
        return "likely"
    return None


def _greedy(left: list, right: list, banned: set, accept, symmetric: bool) -> list:
    """Each row on either side used at most once, strongest first. The ids break ties so the
    same data always gives the same list. `accept(a, b, evidence)` is the extra bar."""
    cands = mp._candidates(left, right)
    scored = []
    for a in left:
        for b in cands.get(a.id, ()):
            if a.id == b.id or (a.id, b.id) in banned:
                continue
            key = mp.score_pair(a, b)
            if key is None:
                continue
            ev = _evidence(a, b)
            if strength_of(ev) is None or not accept(a, b, ev):
                continue
            # strongest evidence first, so a weak neighbour never takes a card a strong one needs
            rank = (2 - STRENGTHS.index(strength_of(ev)), ev["shared"], ev["same_day"], ev["opposition_agrees"], key)
            scored.append((rank, a.id, b.id, ev))
    scored.sort(key=lambda r: (r[0], r[1], r[2]), reverse=True)
    used_a, used_b, out = set(), set(), []
    for key, a_id, b_id, ev in scored:
        if a_id in used_a or b_id in used_b:
            continue
        if symmetric and (a_id in used_b or b_id in used_a):
            continue
        used_a.add(a_id)
        used_b.add(b_id)
        out.append({"a": a_id, "b": b_id, "evidence": ev, "strength": strength_of(ev), "key": key})
    return out


def match_pairs_ca(manuals: list, synced: list, banned: set, linked_ids=frozenset()) -> list:
    """Club cards against synced games nobody has linked. Pure: rows in, pairs out.

    `linked_ids` are cards that already have a link and are being offered a better one: only a
    strong match moves a link, because the card is already counted once and a weaker reason is not
    enough to take it from the game it is on."""
    def accept(a, b, ev):
        # `strength_of` has already turned away two cards that are different matches
        return ev["confirmed"] if a.id in linked_ids else True
    return _greedy(manuals, synced, banned, accept, symmetric=False)


def match_pairs_club(manuals: list, meta: dict, banned: set) -> list:
    """Two club cards, at least one of them unlinked. A date and an opposition alone are not
    enough: a club files two grades against one opposition on one day."""
    def accept(a, b, ev):
        if meta[a.id]["linked"] and meta[b.id]["linked"]:
            return False  # two linked cards are each already counted once
        if ev["gap_days"] is not None and ev["gap_days"] > mp.NEAR_DAYS:
            return False
        if ev["both_cards"]:
            return True
        ga, gb = meta[a.id]["grade_id"], meta[b.id]["grade_id"]
        return bool(ev["same_day"] and ev["opposition_agrees"] and ga and ga == gb)
    pairs = _greedy(manuals, manuals, set(banned) | {(y, x) for x, y in banned}, accept, symmetric=True)
    # An older card first, so the left side is the one that was there before the other.
    def age(i):
        return (str(meta[i]["created_at"] or ""), i)

    for p in pairs:
        if age(p["a"]) > age(p["b"]):
            p["a"], p["b"] = p["b"], p["a"]
    return pairs


async def dismissed_pairs(db, org_id) -> list:
    return await _all(db, _DISMISSED, org=str(org_id))


def _banned(dismissed: list) -> tuple[set, set]:
    ca, club = set(), set()
    for d in dismissed:
        if not d["other"]:
            continue
        (club if d["kind"] == "club" else ca).add((d["mid"], d["other"]))
    return ca, club


def _manual_side(m: dict, card: frozenset, bowlers: int, src: Optional[dict], org: str) -> dict:
    return {
        "kind": "club", "id": m["mid"], "linked": bool(m.get("linked")),
        "date": str(m["played_at"]) if m["played_at"] else None,
        "season": m["season_name"], "grade": m["grade_name"], "opposition": m["opposition"] or None,
        "format": m["match_format"], "result": cr.result_word(m["m_result"]),
        "batters": len(card), "bowlers": bowlers,
        "source": cr.source_of({"from_cricketstatz": m["from_cricketstatz"], "has_payload": m["has_payload"],
                                "created_at": m["created_at"]}, src),
    }


def _synced_side(g: dict, card: frozenset, bowlers: int, org: str) -> dict:
    p = {"winning_team": g["winning_team"], "g_result": g["g_result"], "home_org": g["home_org"],
         "away_org": g["away_org"], "home_team": g["home_team"], "away_team": g["away_team"]}
    return {
        "kind": "ca", "id": g["gid"], "date": str(g["played_at"]) if g["played_at"] else None,
        "season": g["season_name"], "grade": g["grade_name"], "opposition": g["opposition"],
        "format": g["match_format"], "result": cr.ca_result_for(org, p),
        "batters": len(card), "bowlers": bowlers,
        "source": {"kind": "cricket_australia", "label": "Synced from Cricket Australia", "filename": None,
                   "at": None, "by": None},
    }


def _line(kind, pair, side_a, side_b, current=None) -> dict:
    ev = pair["evidence"]
    fa, fb = (side_a["format"] or "").strip().lower(), (side_b["format"] or "").strip().lower()
    return {
        "key": f"{kind}:{side_a['id']}:{side_b['id']}", "kind": kind, "strength": pair["strength"],
        "a": side_a, "b": side_b,
        "shared": ev["shared"], "gap_days": ev["gap_days"], "same_day": ev["same_day"],
        "opposition_agrees": ev["opposition_agrees"], "both_cards": ev["both_cards"],
        "confirmed": ev["confirmed"],
        # The two copies sit under different match types, which is how a double shows up on a
        # player's profile: once under Two Day and once under One Day.
        "formats_differ": bool(fa and fb and fa != fb),
        "date": side_a["date"] or side_b["date"],
        # for a wrong link: the game the card is on now
        "current": current,
    }


async def find_doubles(db, org_id) -> dict:
    """Every possible double of the club, strongest first, plus the pairs a person has dismissed."""
    org = str(org_id)
    club_tokens = mp.team_tokens((await db.execute(text(mp._CLUB_NAME_SQL), {"org": org})).scalar() or "")
    club_cards = await _all(db, _MANUALS, org=org)  # every club card; `linked` says which are
    dismissed = await dismissed_pairs(db, org)
    if not club_cards:  # no club cards at all
        return {"rows": [], "dismissed": await _dismissed_lines(db, org, dismissed)}
    ids = [m["mid"] for m in club_cards]
    cards = await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": ids})
    meta = {m["mid"]: m for m in club_cards}
    manuals = []
    for m in club_cards:
        ours, opp = mp.split_sides(m["home_team"], m["away_team"], m["opposition"], club_tokens)
        manuals.append(mp.MatchRow(m["mid"], m["played_at"], opp, frozenset(cards.get(m["mid"], ())), ours))
    open_manuals = [m for m in manuals if not meta[m.id]["linked"]]
    # Linked cards whose game does not match them are offered a better game too.
    linked_to = sorted({m["linked_to"] for m in club_cards if m["linked_to"]})
    cur_cards = await mp._cards(db, mp._SYNCED_CARD_SQL, {"org": org, "ids": linked_to}) if linked_to else {}
    wrong = []
    for m in manuals:
        mm = meta[m.id]
        if not mm["linked"] or not m.has_card or mm["review_pair_ok"]:
            continue
        if cr.confirms_pair(set(m.signature), set(cur_cards.get(mm["linked_to"], ()))):
            continue
        wrong.append(m)
    wrong_ids = frozenset(m.id for m in wrong)

    dates = [m.played_at for m in manuals if m.played_at is not None]
    span = timedelta(days=mp.WINDOW_DAYS)
    synced = await mp.load_synced(db, org_id, club_tokens=club_tokens, exclude_twinned=True,
                                  from_day=(min(dates) - span) if dates else None,
                                  to_day=(max(dates) + span) if dates else None)
    ban_ca, ban_club = _banned(dismissed)
    pairs_ca, pairs_club = await asyncio.gather(
        asyncio.to_thread(match_pairs_ca, open_manuals + wrong, synced, ban_ca, wrong_ids),
        asyncio.to_thread(match_pairs_club, manuals, meta, ban_club))

    manual_by = {m.id: m for m in manuals}
    synced_by = {m.id: m for m in synced}
    cur_of = {p["a"]: meta[p["a"]]["linked_to"] for p in pairs_ca if p["a"] in wrong_ids}
    gids = sorted({p["b"] for p in pairs_ca} | set(cur_of.values()))
    gdet = {g["gid"]: g for g in (await _all(db, _SYNCED_DETAIL, org=org, ids=gids))} if gids else {}
    mbow = {r["mid"]: r["n"] for r in await _all(db, _BOWLERS, ids=ids)}
    gbow = {r["gid"]: r["n"] for r in await _all(db, _CA_BOWLERS, org=org, ids=gids)} if gids else {}
    srcs = await cr._sources(db, org)

    def m_side(mid):
        return _manual_side(meta[mid], manual_by[mid].signature, mbow.get(mid, 0), srcs.get(mid), org)

    rows = []
    for p in pairs_ca:
        g = gdet.get(p["b"])
        if not g:
            continue
        current = None
        if p["a"] in wrong_ids:
            cg = gdet.get(cur_of[p["a"]])
            if not cg:
                continue
            csig = frozenset(cur_cards.get(cg["gid"], ()))
            current = {**_synced_side(cg, csig, gbow.get(cg["gid"], 0), org),
                       "shared_with_club": len(manual_by[p["a"]].signature & csig)}
        rows.append(_line("relink" if current else "ca", p, m_side(p["a"]),
                          _synced_side(g, synced_by[p["b"]].signature, gbow.get(p["b"], 0), org), current))
    for p in pairs_club:
        rows.append(_line("club", p, m_side(p["a"]), m_side(p["b"])))
    order = {s: i for i, s in enumerate(STRENGTHS)}
    rows.sort(key=lambda r: (order[r["strength"]], -r["shared"], r["date"] or "", r["key"]))
    return {"rows": rows, "dismissed": await _dismissed_lines(db, org, dismissed)}


async def _dismissed_lines(db, org: str, dismissed: list) -> list:
    """The pairs a person said are different matches, drawn with both sides so they can be put back."""
    if not dismissed:
        return []
    mids = sorted({d["mid"] for d in dismissed} | {d["other"] for d in dismissed if d["kind"] == "club" and d["other"]})
    gids = sorted({d["other"] for d in dismissed if d["kind"] in ("ca", "relink") and d["other"]})
    by_m = {m["mid"]: m for m in await _all(db, _MANUALS + " AND mg.id = ANY(CAST(:ids AS UUID[]))", org=org, ids=mids)}
    cards = await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": mids})
    mbow = {r["mid"]: r["n"] for r in await _all(db, _BOWLERS, ids=mids)}
    gdet = {g["gid"]: g for g in (await _all(db, _SYNCED_DETAIL, org=org, ids=gids))} if gids else {}
    gcards = await mp._cards(db, mp._SYNCED_CARD_SQL, {"org": org, "ids": gids}) if gids else {}
    srcs = await cr._sources(db, org)
    out = []
    for d in dismissed:
        a = by_m.get(d["mid"])
        if not a or not d["other"]:
            continue
        side_a = _manual_side(a, frozenset(cards.get(d["mid"], ())), mbow.get(d["mid"], 0), srcs.get(d["mid"]), org)
        if d["kind"] == "club":
            b = by_m.get(d["other"])
            if not b:
                continue
            side_b = _manual_side(b, frozenset(cards.get(d["other"], ())), mbow.get(d["other"], 0),
                                  srcs.get(d["other"]), org)
        else:
            g = gdet.get(d["other"])
            if not g:
                continue
            side_b = _synced_side(g, frozenset(gcards.get(d["other"], ())), 0, org)
        out.append({"kind": d["kind"], "a": side_a, "b": side_b, "date": side_a["date"] or side_b["date"],
                    "dismissed_at": d["created_at"].isoformat() if d["created_at"] else None,
                    "dismissed_by": d["username"], "key": f"{d['kind']}:{side_a['id']}:{side_b['id']}"})
    return out


def counts(result: dict) -> dict:
    rows = result["rows"]
    return {"total": len(rows), "dismissed": len(result["dismissed"]),
            "by_strength": {s: sum(1 for r in rows if r["strength"] == s) for s in STRENGTHS},
            "by_kind": {k: sum(1 for r in rows if r["kind"] == k) for k in KINDS},
            "formats_differ": sum(1 for r in rows if r["formats_differ"])}
