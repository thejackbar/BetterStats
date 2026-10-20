"""Card review, find a match: look a fixture up and see every copy of it the record holds.

The possible-doubles scan answers "what might be counted twice?". This answers the question a
person arrives with: someone has queried a figure on a scorecard, or is hunting a particular
fixture, and wants to see BOTH copies whether or not anything has linked them. Read only.

A fixture is shown as the copies the record holds:

* ``linked``    a club card and the Cricket Australia game it is linked to (one match, two copies);
* ``club_only`` a club card with no link;
* ``ca_only``   a synced game no club card is linked to.

A fixture on its own may carry ``candidate``: the possible double the scan found for it, so it can
be linked or dismissed from the result. Two results the person picks can be linked by hand when
the scan did not suggest them (`card_review_actions.link_double` is the same call either way).

THE FILTERS are the ways people name a match: free text (the opposition or a team name), season,
grade, competition, a player (every word must appear in a batter's or bowler's name on either
copy), and a date range. A search with no filter at all is refused: it would be every synced game
the club has, and "show me everything" is not a question. Every filter is bound, never joined into
the SQL text.
"""
from __future__ import annotations

from datetime import date as date_cls
from typing import Optional

from sqlalchemy import text

from app.services import card_review as cr
from app.services import card_review_doubles as dbl
from app.services import match_pairing as mp

# Each source is read newest first and capped, then the two are merged and paged. A filter that
# still matches more than this is too wide to read, and the answer says so.
SOURCE_CAP = 400


class FindError(ValueError):
    """A search the data cannot honour, in words a person can read."""


def _words(value: Optional[str]) -> list:
    return [w for w in (value or "").replace(",", " ").split() if w][:6]


def _filters(alias: str, *, manual: bool, text_q=None, season=None, grade=None, competition=None, player=None,
             date_from=None, date_to=None) -> tuple[str, dict]:
    """The WHERE tail shared by both sources, as (sql, params). `manual` picks the tables."""
    sql, params = "", {}
    if season:
        sql += " AND s.name = :season"
        params["season"] = season
    if grade:
        sql += f" AND COALESCE(gr.display_name_override, gr.name) ILIKE :grade"
        params["grade"] = f"%{grade.strip()}%"
    if competition:
        sql += " AND cc.name = :competition"
        params["competition"] = competition
    if date_from:
        sql += f" AND {alias}.played_at >= :d_from"
        params["d_from"] = date_from
    if date_to:
        sql += f" AND {alias}.played_at <= :d_to"
        params["d_to"] = date_to
    for i, w in enumerate(_words(text_q)):
        sides = ("COALESCE(mg.opposition, '') || ' ' || COALESCE(mg.home_team, '') || ' ' || COALESCE(mg.away_team, '')"
                 if manual else
                 "COALESCE(g.opp_club_name, '') || ' ' || COALESCE(g.home_team, '') || ' ' || COALESCE(g.away_team, '')")
        sql += f" AND ({sides}) ILIKE :t{i}"
        params[f"t{i}"] = f"%{w}%"
    for i, w in enumerate(_words(player)):
        params[f"p{i}"] = f"%{w}%"
        if manual:
            sql += (f" AND EXISTS (SELECT 1 FROM players pl WHERE pl.organisation_id = CAST(:org AS UUID)"
                    f" AND COALESCE(pl.display_name_override, pl.name) ILIKE :p{i} AND ("
                    f"EXISTS (SELECT 1 FROM manual_batting_innings b WHERE b.manual_game_id = mg.id AND b.player_id = pl.id)"
                    f" OR EXISTS (SELECT 1 FROM manual_bowling_spells w WHERE w.manual_game_id = mg.id AND w.player_id = pl.id)))")
        else:
            sql += (f" AND EXISTS (SELECT 1 FROM players pl WHERE pl.organisation_id = CAST(:org AS UUID)"
                    f" AND COALESCE(pl.display_name_override, pl.name) ILIKE :p{i} AND ("
                    f"EXISTS (SELECT 1 FROM batting_innings b WHERE b.game_id = g.id AND b.player_id = pl.id)"
                    f" OR EXISTS (SELECT 1 FROM bowling_spells w WHERE w.game_id = g.id AND w.player_id = pl.id)))")
    return sql, params


_MANUAL_HITS = """
    SELECT mg.id::text AS mid, mg.superseded_by_game_id::text AS gid, mg.played_at
      FROM manual_games mg
      LEFT JOIN seasons s ON s.id = mg.season_id
      LEFT JOIN grades gr ON gr.id = mg.grade_id
      LEFT JOIN club_competitions cc ON cc.id = gr.competition_id
     WHERE mg.organisation_id = CAST(:org AS UUID)
"""
_SYNCED_HITS = """
    SELECT g.id::text AS gid, g.played_at,
           (SELECT tw.id::text FROM manual_games tw WHERE tw.superseded_by_game_id = g.id LIMIT 1) AS mid
      FROM games g
      LEFT JOIN grades gr ON gr.id = g.grade_id
      LEFT JOIN seasons s ON s.id = gr.season_id
      LEFT JOIN club_competitions cc ON cc.id = gr.competition_id
     WHERE (s.organisation_id = CAST(:org AS UUID) OR g.home_org_id = CAST(:org AS UUID)
            OR g.away_org_id = CAST(:org AS UUID))
"""


def has_filter(**kw) -> bool:
    return bool(_words(kw.get("text_q")) or kw.get("season") or (kw.get("grade") or "").strip()
                or kw.get("competition") or _words(kw.get("player")) or kw.get("date_from") or kw.get("date_to"))


async def matching_ids(db, org_id, **kw) -> set:
    """Ids (club cards and synced games alike) of every fixture a search matches, with no cap.

    THIS IS HOW EVERY STEP OF THE REVIEW IS FILTERED. A pair matches if either copy does, so the
    pairing, agree, small and differ lists and the doubles list narrow by the same words people
    use in Find a match, and a pair found by only one of its halves is still in."""
    org = str(org_id)
    ms, m_params = _filters("mg", manual=True, **kw)
    ss, s_params = _filters("g", manual=False, **kw)
    out = set()
    for r in (await db.execute(text(_MANUAL_HITS + ms), {"org": org, **m_params})).mappings():
        out.add(r["mid"])
        if r["gid"]:
            out.add(r["gid"])
    for r in (await db.execute(text(_SYNCED_HITS + ss), {"org": org, **s_params})).mappings():
        out.add(r["gid"])
        if r["mid"]:
            out.add(r["mid"])
    return out


async def facets(db, org_id) -> dict:
    """What the filters can offer: the club's seasons, competitions and grade names."""
    org = str(org_id)
    seasons = [r[0] for r in (await db.execute(text(
        "SELECT DISTINCT name FROM seasons WHERE organisation_id = CAST(:o AS UUID) AND name IS NOT NULL"),
        {"o": org})).all()]
    comps = [r[0] for r in (await db.execute(text(
        "SELECT name FROM club_competitions WHERE organisation_id = CAST(:o AS UUID) ORDER BY display_order NULLS LAST, name"),
        {"o": org})).all()]
    return {"seasons": sorted(seasons, key=lambda x: (cr.season_sort_key(x), x)), "competitions": comps}


async def find_fixtures(db, org_id, *, text_q=None, season=None, grade=None, competition=None, player=None,
                        date_from: Optional[date_cls] = None, date_to: Optional[date_cls] = None,
                        limit: int = 25, offset: int = 0, doubles: Optional[dict] = None) -> dict:
    org = str(org_id)
    if not has_filter(text_q=text_q, season=season, grade=grade, competition=competition, player=player,
                      date_from=date_from, date_to=date_to):
        raise FindError("Give at least one thing to look for: an opposition, a player, a season, a grade, "
                        "a competition or a date.")
    kw = dict(text_q=text_q, season=season, grade=grade, competition=competition, player=player,
              date_from=date_from, date_to=date_to)
    ms, m_params = _filters("mg", manual=True, **kw)
    ss, s_params = _filters("g", manual=False, **kw)
    m_rows = (await db.execute(text(_MANUAL_HITS + ms + f" ORDER BY mg.played_at DESC NULLS LAST, mg.id LIMIT {SOURCE_CAP + 1}"),
                               {"org": org, **m_params})).mappings().all()
    s_rows = (await db.execute(text(_SYNCED_HITS + ss + f" ORDER BY g.played_at DESC NULLS LAST, g.id LIMIT {SOURCE_CAP + 1}"),
                               {"org": org, **s_params})).mappings().all()
    capped = len(m_rows) > SOURCE_CAP or len(s_rows) > SOURCE_CAP

    # One fixture per club card; a synced game is its own fixture only if no club card is linked.
    fixtures: dict = {}
    for r in m_rows[:SOURCE_CAP]:
        fixtures[f"m:{r['mid']}"] = {"mid": r["mid"], "gid": r["gid"], "date": r["played_at"]}
    for r in s_rows[:SOURCE_CAP]:
        if r["mid"]:
            fixtures.setdefault(f"m:{r['mid']}", {"mid": r["mid"], "gid": r["gid"], "date": r["played_at"]})
        else:
            fixtures[f"g:{r['gid']}"] = {"mid": None, "gid": r["gid"], "date": r["played_at"]}
    ordered = sorted(fixtures.values(), key=lambda f: (str(f["date"] or "0000"), f["mid"] or f["gid"]), reverse=True)
    total = len(ordered)
    page = ordered[offset:offset + limit]
    out = {"total": total, "offset": offset, "limit": limit, "capped": capped, "rows": []}
    if not page:
        return out

    mids = [f["mid"] for f in page if f["mid"]]
    gids = sorted({f["gid"] for f in page if f["gid"]})
    manual = {m["mid"]: m for m in await dbl._all(db, dbl._MANUALS + " AND mg.id = ANY(CAST(:ids AS UUID[]))", org=org, ids=mids)} if mids else {}
    gdet = {g["gid"]: g for g in await dbl._all(db, dbl._SYNCED_DETAIL, org=org, ids=gids)} if gids else {}
    mcards = await mp._cards(db, mp._IMPORTED_CARD_SQL, {"ids": mids}) if mids else {}
    gcards = await mp._cards(db, mp._SYNCED_CARD_SQL, {"org": org, "ids": gids}) if gids else {}
    mbow = {r["mid"]: r["n"] for r in await dbl._all(db, dbl._BOWLERS, ids=mids)} if mids else {}
    gbow = {r["gid"]: r["n"] for r in await dbl._all(db, dbl._CA_BOWLERS, org=org, ids=gids)} if gids else {}
    srcs = await cr._sources(db, org)
    review = {r["match_id"]: r for r in await cr.review_rows(db, org, mids=[f["mid"] for f in page if f["mid"] and f["gid"]])} \
        if any(f["mid"] and f["gid"] for f in page) else {}
    cand_by = {}
    for row in (doubles or {}).get("rows", []):
        cand_by[row["a"]["id"]] = row
        cand_by[row["b"]["id"]] = row

    for f in page:
        copies = []
        if f["mid"] and f["mid"] in manual:
            copies.append(dbl._manual_side(manual[f["mid"]], frozenset(mcards.get(f["mid"], ())),
                                           mbow.get(f["mid"], 0), srcs.get(f["mid"]), org))
        if f["gid"] and f["gid"] in gdet:
            copies.append(dbl._synced_side(gdet[f["gid"]], frozenset(gcards.get(f["gid"], ())),
                                           gbow.get(f["gid"], 0), org))
        if not copies:
            continue
        state = "linked" if f["mid"] and f["gid"] else "club_only" if f["mid"] else "ca_only"
        rv = review.get(f["mid"]) if state == "linked" else None
        cand = None if state == "linked" else cand_by.get(f["mid"] or f["gid"])
        out["rows"].append({
            "key": f"{state}:{f['mid'] or ''}:{f['gid'] or ''}", "state": state,
            "date": str(f["date"]) if f["date"] else None, "copies": copies,
            "match_id": f["mid"], "game_id": f["gid"],
            "review": {"group": rv["group"], "current": rv["current"], "headline": rv["headline"],
                       "differences": len(rv["items"]), "decided_by_hand": rv["decided_by_hand"]} if rv else None,
            "candidate": cand,
        })
    return out
