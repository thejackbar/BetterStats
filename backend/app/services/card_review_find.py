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

import difflib
import re
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
             date_from=None, date_to=None, player_ids=None) -> tuple[str, dict]:
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
    if _words(player):
        # THE PLAYERS ARE RESOLVED FIRST (`resolve_players`) and bound as an array, so the match is
        # a lookup on the batting lines' player id, not a name comparison per match row.
        if not player_ids:
            sql += " AND FALSE"
        else:
            params["pids"] = [str(x) for x in player_ids]
            if manual:
                sql += (" AND (EXISTS (SELECT 1 FROM manual_batting_innings b WHERE b.manual_game_id = mg.id"
                        " AND b.player_id = ANY(CAST(:pids AS UUID[])))"
                        " OR EXISTS (SELECT 1 FROM manual_bowling_spells w WHERE w.manual_game_id = mg.id"
                        " AND w.player_id = ANY(CAST(:pids AS UUID[]))))")
            else:
                sql += (" AND (EXISTS (SELECT 1 FROM batting_innings b WHERE b.game_id = g.id"
                        " AND b.player_id = ANY(CAST(:pids AS UUID[])))"
                        " OR EXISTS (SELECT 1 FROM bowling_spells w WHERE w.game_id = g.id"
                        " AND w.player_id = ANY(CAST(:pids AS UUID[]))))")
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


def _tokens(name: str) -> list:
    return [t for t in re.split(r"[^a-z0-9]+", (name or "").lower()) if t]


def _word_fits(w: str, tokens: list) -> bool:
    """A typed word fits a name if a word of the name starts with it, is within a typo of it, or is
    the initial it stands for ("Ritchie, P" is "peter ritchie")."""
    for t in tokens:
        if t.startswith(w) or (len(t) == 1 and w[0] == t):
            return True
        if len(w) >= 3 and (difflib.SequenceMatcher(None, w, t).ratio() >= 0.8
                            or difflib.SequenceMatcher(None, w, t[:len(w)]).ratio() >= 0.8):
            return True
    return False


async def resolve_players(db, org_id, player: Optional[str]) -> dict:
    """The club's players a typed name means: every word a substring of the name, else (a typo, or
    an initial where the club holds one) every word a close fit. Returns the ids, the names, and
    `fuzzy` when the close fit was needed, so the page can say "showing Ritchie, Peter"."""
    words = [w.lower() for w in _words(player)]
    if not words:
        return {"query": player, "ids": [], "names": [], "fuzzy": False}
    org = str(org_id)
    rows = (await db.execute(text(
        "SELECT id::text, COALESCE(NULLIF(display_name_override, ''), name) FROM players "
        "WHERE organisation_id = CAST(:o AS UUID) AND name IS NOT NULL LIMIT 20000"), {"o": org})).all()
    exact = [(i, n) for i, n in rows if all(w in (n or "").lower() for w in words)]
    fuzzy = False
    hits = exact
    if not hits:
        hits = [(i, n) for i, n in rows if all(_word_fits(w, _tokens(n)) for w in words)]
        fuzzy = bool(hits)
    hits = hits[:200]
    return {"query": player, "ids": [i for i, _ in hits], "names": sorted({n for _, n in hits})[:8], "fuzzy": fuzzy}


def player_note(info: dict) -> Optional[dict]:
    """What to tell the person about a player search, or None when it matched plainly."""
    if not info or not info.get("query"):
        return None
    if not info["ids"]:
        return {"query": info["query"], "matched": [], "fuzzy": False}
    return {"query": info["query"], "matched": info["names"], "fuzzy": info["fuzzy"]} if info["fuzzy"] else None


def has_filter(**kw) -> bool:
    return bool(_words(kw.get("text_q")) or kw.get("season") or (kw.get("grade") or "").strip()
                or kw.get("competition") or _words(kw.get("player")) or kw.get("date_from") or kw.get("date_to"))


async def matching_ids(db, org_id, **kw) -> set:
    """Ids (club cards and synced games alike) of every fixture a search matches, with no cap.

    THIS IS HOW EVERY STEP OF THE REVIEW IS FILTERED. A pair matches if either copy does, so the
    pairing, agree, small and differ lists and the doubles list narrow by the same words people
    use in Find a match, and a pair found by only one of its halves is still in."""
    org = str(org_id)
    pids = (await resolve_players(db, org_id, kw.get("player")))["ids"] if kw.get("player") else None
    ms, m_params = _filters("mg", manual=True, player_ids=pids, **kw)
    ss, s_params = _filters("g", manual=False, player_ids=pids, **kw)
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
    """What the filters can offer, all from this club's own data: its seasons and competitions for
    the dropdowns, and the players, opposition names and grade names for the typeahead. The browser
    matches as the person types (forgivingly: "richie" finds "Ritchie"), so this is one small read
    per page, not one per keystroke.

    PLAYERS ARE THE CLUB'S OWN, never the opposition's. An opposition name is whatever either copy
    of a match calls it, so a club's two spellings of one team both show."""
    org = str(org_id)
    seasons = [r[0] for r in (await db.execute(text(
        "SELECT DISTINCT name FROM seasons WHERE organisation_id = CAST(:o AS UUID) AND name IS NOT NULL"),
        {"o": org})).all()]
    comps = [r[0] for r in (await db.execute(text(
        "SELECT name FROM club_competitions WHERE organisation_id = CAST(:o AS UUID) ORDER BY display_order NULLS LAST, name"),
        {"o": org})).all()]
    players = [r[0] for r in (await db.execute(text(
        "SELECT DISTINCT COALESCE(NULLIF(display_name_override, ''), name) AS n FROM players "
        "WHERE organisation_id = CAST(:o AS UUID) AND name IS NOT NULL ORDER BY n LIMIT 5000"), {"o": org})).all()]
    opp = (await db.execute(text("""
        SELECT n FROM (
            SELECT NULLIF(btrim(mg.opposition), '') AS n FROM manual_games mg WHERE mg.organisation_id = CAST(:o AS UUID)
            UNION
            SELECT NULLIF(btrim(CASE WHEN g.home_org_id = CAST(:o AS UUID) THEN g.away_team
                                     WHEN g.away_org_id = CAST(:o AS UUID) THEN g.home_team
                                     ELSE COALESCE(g.opp_club_name, g.away_team) END), '')
              FROM games g LEFT JOIN grades gr ON gr.id = g.grade_id LEFT JOIN seasons s ON s.id = gr.season_id
             WHERE s.organisation_id = CAST(:o AS UUID) OR g.home_org_id = CAST(:o AS UUID)
                OR g.away_org_id = CAST(:o AS UUID)) t
         WHERE n IS NOT NULL ORDER BY n LIMIT 5000"""), {"o": org})).all()
    grades = [r[0] for r in (await db.execute(text("""
        SELECT DISTINCT COALESCE(NULLIF(gr.display_name_override, ''), gr.name) AS n
          FROM grades gr JOIN seasons s ON s.id = gr.season_id
         WHERE s.organisation_id = CAST(:o AS UUID) AND gr.name IS NOT NULL ORDER BY n LIMIT 2000"""), {"o": org})).all()]
    return {"seasons": sorted(seasons, key=lambda x: (cr.season_sort_key(x), x)), "competitions": comps,
            "players": players, "oppositions": [r[0] for r in opp], "grades": grades}


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
    who = await resolve_players(db, org_id, player) if _words(player) else None
    ms, m_params = _filters("mg", manual=True, player_ids=who["ids"] if who else None, **kw)
    ss, s_params = _filters("g", manual=False, player_ids=who["ids"] if who else None, **kw)
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
    out = {"total": total, "offset": offset, "limit": limit, "capped": capped, "rows": [],
           "player_note": player_note(who) if who else None}
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
