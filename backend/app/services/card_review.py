"""Card review, read side: compare a match's two stored versions and sort every paired match.

A match is stored twice when a synced Cricket Australia game (`games`) and a club scorecard
(`manual_games`: imported from a file, typed in, or read from a photo) are linked by
`manual_games.superseded_by_game_id`. `pair_prefers_import` says which one the site shows.
Nothing here writes; `card_review_actions` does.

WHAT IS COMPARED. Only what both sides really store, so a difference is never invented:
our batters' runs and how they were out, our bowlers' wickets and runs conceded, the date, the
result for OUR side (the rule `aggregations._club_results` uses, because `games.result` is
relative to whichever club synced the game first), and, where both sides carry them, the team
total, the extras and the opposition total (`games.innings_totals` against `manual_innings`).
A figure only one side holds is not a difference.

THE FIVE GROUPS. Each paired match is in exactly one:

* ``nocard``  Cricket Australia has no card of ours for it, so there is nothing to compare.
* ``pairing`` the two cards do not look like the same game: fewer than 60% of the batters
              appear with the same score on both (the same bar `import_detail_restore` uses
              to trust a pair). A person can say it is the same match (``review_pair_ok``).
* ``differ``  a batter's runs differ, or a batter is on one card only, or the result flips
              between a win and a loss. These need a person.
* ``small``   the batting agrees; only the date, the extras, the bowling figures, the result
              wording or how a batter was out differ.
* ``agree``   nothing differs.

A SUGGESTION is a default, never an action. ``agree`` and ``small`` suggest Cricket Australia
(it holds the richer card and the numbers are the same) unless the club card holds something
Cricket Australia lacks (``club_richer``): then the suggestion is the combined choice when
Cricket Australia has detail too, else the club card, and a bulk switch skips the match. ``differ`` with at most three
differences and a Cricket Australia card that holds detail suggests ``hybrid`` (the club's
numbers with Cricket Australia's detail added where it fits). Anything else suggests nothing.
"""
from __future__ import annotations

import math
import uuid
from collections import defaultdict
from typing import Optional

from sqlalchemy import text

CHOICES = ("ca", "club", "hybrid")
GROUPS = ("agree", "small", "differ", "pairing", "nocard")

# A dismissal is compared by what it IS, not how a source spells it ("Caught" against "c").
_HOW_OUT = {
    "c": "c", "ct": "c", "caught": "c",
    "c&b": "cb", "c & b": "cb", "caught and bowled": "cb", "caught & bowled": "cb",
    "b": "b", "bowled": "b",
    "lbw": "lbw", "leg before wicket": "lbw", "leg before": "lbw",
    "run out": "ro", "runout": "ro", "ro": "ro",
    "stumped": "st", "st": "st",
    "not out": "no", "no": "no",
    "hit wicket": "hw", "hit-wicket": "hw",
    "retired": "ret", "retired out": "ret",
    "retired hurt": "rh", "retired not out": "rno",
}

# How much each kind of difference counts toward a match's size bar (capped at 100).
_WEIGHT = {"result_flip": 50, "team_total": 30, "batter_runs": 12, "batter_missing": 12,
           "innings": 25, "bowler_wickets": 6, "bowler_runs": 4, "extras": 4, "opp_total": 6,
           "result": 2, "date": 2, "how_out": 1}
# Their order when a line has room for one, biggest first.
_ORDER = ["result_flip", "team_total", "batter_runs", "batter_missing", "innings", "bowler_wickets",
          "bowler_runs", "extras", "opp_total", "result", "date", "how_out"]
_CATEGORY = {"result_flip": "result", "result": "result", "team_total": "total", "opp_total": "total",
             "batter_runs": "batting", "batter_missing": "batting", "innings": "batting",
             "how_out": "batting", "bowler_wickets": "bowling", "bowler_runs": "bowling",
             "extras": "extras", "date": "date"}
_SEVERE = {"result_flip", "batter_runs", "batter_missing", "innings"}

_PAIRED = """
    SELECT mg.id::text AS mid, mg.superseded_by_game_id::text AS gid,
           mg.organisation_id::text AS org_id,
           s.name AS season_name, COALESCE(gr.display_name_override, gr.name) AS grade_name,
           mg.played_at AS m_date, mg.opposition AS m_opposition, mg.result AS m_result,
           mg.pair_prefers_import, mg.pairing_locked, mg.innings_order_known,
           mg.review_choice, mg.review_source, mg.review_decided_by, mg.review_decided_at,
           mg.review_note, mg.review_pair_ok, mg.cricketstatz_import_id IS NOT NULL AS from_cricketstatz,
           mg.extracted_payload IS NOT NULL AS has_payload, mg.created_by_user_id, mg.created_at,
           g.played_at AS g_date, g.home_org_id::text AS home_org, g.away_org_id::text AS away_org,
           g.home_team, g.away_team, g.winning_team, g.result AS g_result, g.innings_totals,
           CASE WHEN g.home_org_id = CAST(:org AS UUID) THEN g.away_team
                WHEN g.away_org_id = CAST(:org AS UUID) THEN g.home_team
                ELSE COALESCE(g.opp_club_name, g.home_team || ' v ' || g.away_team) END AS g_opposition
      FROM manual_games mg
      JOIN games g ON g.id = mg.superseded_by_game_id
      LEFT JOIN seasons s ON s.id = mg.season_id
      LEFT JOIN grades gr ON gr.id = mg.grade_id
     WHERE mg.organisation_id = CAST(:org AS UUID)
       AND mg.superseded_by_game_id IS NOT NULL
"""
_ONLY = " AND mg.id = ANY(CAST(:mids AS UUID[]))"

_CLUB_BAT = """
    SELECT manual_game_id::text AS mid, player_id::text AS pid, innings_number, runs, balls,
           dismissal_type, batting_position, not_out, COALESCE(did_not_bat, FALSE) AS dnb, id
      FROM manual_batting_innings WHERE manual_game_id = ANY(CAST(:ids AS UUID[]))
"""
_CA_BAT = """
    SELECT bi.game_id::text AS gid, bi.player_id::text AS pid, bi.innings_number, bi.runs, bi.balls,
           bi.dismissal_type, bi.batting_position, bi.not_out, COALESCE(bi.did_not_bat, FALSE) AS dnb
      FROM batting_innings bi
      JOIN players p ON p.id = bi.player_id AND p.organisation_id = CAST(:org AS UUID)
     WHERE bi.game_id = ANY(CAST(:ids AS UUID[]))
"""
_CLUB_BOWL = """
    SELECT manual_game_id::text AS mid, player_id::text AS pid, innings_number,
           COALESCE(wickets, 0) AS wickets, COALESCE(runs, 0) AS runs
      FROM manual_bowling_spells WHERE manual_game_id = ANY(CAST(:ids AS UUID[]))
"""
_CA_BOWL = """
    SELECT bs.game_id::text AS gid, bs.player_id::text AS pid, bs.innings_number,
           COALESCE(bs.wickets, 0) AS wickets, COALESCE(bs.runs, 0) AS runs
      FROM bowling_spells bs
      JOIN players p ON p.id = bs.player_id AND p.organisation_id = CAST(:org AS UUID)
     WHERE bs.game_id = ANY(CAST(:ids AS UUID[]))
"""
_CLUB_INN = """
    SELECT manual_game_id::text AS mid, innings_number, batting_side, byes, leg_byes, wides,
           no_balls, penalty, extras_total, total_runs, total_wickets
      FROM manual_innings WHERE manual_game_id = ANY(CAST(:ids AS UUID[]))
"""
# What each side holds beyond the batting and bowling lines, as counts per match.
_INVENTORY = """
    SELECT 'ca' AS side, game_id::text AS k, 'credits' AS what, count(*) AS n
      FROM bowler_wickets WHERE game_id = ANY(CAST(:gids AS UUID[])) GROUP BY game_id
    UNION ALL SELECT 'ca', game_id::text, 'fow', count(*)
      FROM fall_of_wickets WHERE game_id = ANY(CAST(:gids AS UUID[])) GROUP BY game_id
    UNION ALL SELECT 'ca', game_id::text, 'partnerships', count(*)
      FROM partnerships WHERE game_id = ANY(CAST(:gids AS UUID[])) GROUP BY game_id
    UNION ALL SELECT 'ca', bi.game_id::text, 'opp_batters', count(*)
      FROM batting_innings bi JOIN players p ON p.id = bi.player_id
     WHERE bi.game_id = ANY(CAST(:gids AS UUID[]))
       AND p.organisation_id IS DISTINCT FROM CAST(:org AS UUID)
       AND NOT COALESCE(bi.did_not_bat, FALSE) GROUP BY bi.game_id
    UNION ALL SELECT 'ca', game_id::text, 'team_sheet', count(*)
      FROM game_appearances WHERE game_id = ANY(CAST(:gids AS UUID[])) GROUP BY game_id
    UNION ALL SELECT 'club', manual_game_id::text, 'credits', count(*)
      FROM manual_bowler_wickets WHERE manual_game_id = ANY(CAST(:mids AS UUID[])) GROUP BY manual_game_id
    UNION ALL SELECT 'club', manual_game_id::text, 'fow', count(*)
      FROM manual_fall_of_wickets WHERE manual_game_id = ANY(CAST(:mids AS UUID[])) GROUP BY manual_game_id
    UNION ALL SELECT 'club', manual_game_id::text, 'partnerships', count(*)
      FROM manual_partnerships WHERE manual_game_id = ANY(CAST(:mids AS UUID[])) GROUP BY manual_game_id
"""
_SOURCES = """
    SELECT DISTINCT ON (mid) mid, l.created_at AS at, l.user_id::text AS uid,
           l.after_json->>'filename' AS filename, u.username
      FROM (SELECT l.id, l.created_at, l.user_id, l.after_json,
                   jsonb_array_elements_text(l.after_json->'created_game_ids') AS mid
              FROM manual_edit_logs l
             WHERE l.organisation_id = CAST(:org AS UUID) AND l.action = 'import'
               AND l.target_table = 'manual_games' AND l.undone_at IS NULL) l
      LEFT JOIN users u ON u.id = l.user_id
     ORDER BY mid, l.created_at DESC
"""


def _grouped(rows, key):
    out = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out


async def _all(db, sql, **params):
    return [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]


def how_out(value: Optional[str]) -> Optional[str]:
    v = " ".join((value or "").lower().split())
    if not v:
        return None
    return _HOW_OUT.get(v, v)


def result_word(value: Optional[str]) -> Optional[str]:
    v = (value or "").strip().upper()
    if not v:
        return None
    if v in ("W", "WIN", "WON"):
        return "WIN"
    if v in ("L", "LOSS", "LOST", "LOSE"):
        return "LOSS"
    if v in ("D", "DRAW", "DRAWN"):
        return "DRAW"
    if v in ("T", "TIE", "TIED"):
        return "TIE"
    return v


def ca_result_for(org_id: str, p: dict) -> Optional[str]:
    """OUR result from a synced row: `winning_team` is neutral, `result` is not."""
    win = p.get("winning_team")
    if not win:
        return result_word(p.get("g_result"))
    if p.get("home_org") == org_id:
        if win == p.get("home_team"):
            return "WIN"
        if win == p.get("away_team"):
            return "LOSS"
    if p.get("away_org") == org_id:
        if win == p.get("away_team"):
            return "WIN"
        if win == p.get("home_team"):
            return "LOSS"
    return result_word(p.get("g_result"))


def _extras_of(row: dict) -> Optional[int]:
    if row.get("extras_total") is not None:
        return row["extras_total"]
    parts = [row.get(k) for k in ("byes", "leg_byes", "wides", "no_balls", "penalty")]
    known = [x for x in parts if x is not None]
    return sum(known) if known else None


def _totals_by_innings(innings_totals) -> dict:
    out = {}
    for t in innings_totals or []:
        try:
            out[int(t.get("innings_number"))] = t
        except (TypeError, ValueError):
            continue
    return out


def confirms_pair(card_club: set, card_ca: set) -> bool:
    """The same bar `import_detail_restore` uses to trust a pair."""
    if not card_club or not card_ca:
        return False
    need = max(2, math.ceil(0.6 * min(len(card_club), len(card_ca))))
    return len(card_club & card_ca) >= need


def compare_match(org_id: str, p: dict, club_bat: list, ca_bat: list, club_bowl: list,
                  ca_bowl: list, club_inn: list, names: dict) -> dict:
    """One match's differences, group, size and suggestion. Pure: rows in, verdict out."""
    items: list = []

    def add(kind, label, ca, club):
        items.append({"kind": kind, "category": _CATEGORY[kind], "label": label,
                      "ca": ca, "club": club, "weight": _WEIGHT[kind]})

    cb = [r for r in club_bat if not r["dnb"] and r["runs"] is not None]
    kb = [r for r in ca_bat if not r["dnb"] and r["runs"] is not None]
    ours_club = sorted({r["innings_number"] for r in cb})
    ours_ca = sorted({r["innings_number"] for r in kb})
    card_club = {(r["pid"], r["runs"]) for r in cb}
    card_ca = {(r["pid"], r["runs"]) for r in kb}
    shared = len(card_club & card_ca)
    pair_ok = bool(p.get("review_pair_ok")) or confirms_pair(card_club, card_ca)

    if not kb:
        group = "nocard"
    elif not pair_ok:
        group = "pairing"
    else:
        group = None

    # Innings are lined up by order, never by number: the import numbers ours 1, 3, 5 and
    # theirs 2, 4, 6; Cricket Australia numbers by who batted first.
    if group is None and len(ours_club) != len(ours_ca):
        add("innings", "Innings we batted", len(ours_ca), len(ours_club))
    inn_ca = {n: i for i, n in enumerate(ours_ca)}
    inn_club = {n: i for i, n in enumerate(ours_club)}

    def nm(pid):
        return names.get(pid) or pid[:8]

    if group is None:
        by_ca = {(r["pid"], inn_ca[r["innings_number"]]): r for r in kb}
        by_club = {(r["pid"], inn_club[r["innings_number"]]): r for r in cb}
        for key in sorted(set(by_ca) | set(by_club), key=lambda k: (nm(k[0]), k[1])):
            a, c = by_ca.get(key), by_club.get(key)
            who = nm(key[0])
            if a and c:
                if a["runs"] != c["runs"]:
                    add("batter_runs", f"{who}, runs", a["runs"], c["runs"])
                ha, hc = how_out(a["dismissal_type"]), how_out(c["dismissal_type"])
                if ha and hc and ha != hc and not (a["not_out"] or c["not_out"]) or \
                        (ha and hc and ha != hc and (a["not_out"] != c["not_out"])):
                    add("how_out", f"{who}, how out", a["dismissal_type"], c["dismissal_type"])
            elif a:
                add("batter_missing", f"{who}, only on the Cricket Australia card", a["runs"], None)
            else:
                add("batter_missing", f"{who}, only on the club card", None, c["runs"])

        # Bowling, per bowler over the whole match.
        wa, ra, wc, rc = defaultdict(int), defaultdict(int), defaultdict(int), defaultdict(int)
        for r in ca_bowl:
            wa[r["pid"]] += r["wickets"]
            ra[r["pid"]] += r["runs"]
        for r in club_bowl:
            wc[r["pid"]] += r["wickets"]
            rc[r["pid"]] += r["runs"]
        for pid in sorted(set(wa) | set(wc), key=nm):
            if pid in wa and pid in wc:
                if wa[pid] != wc[pid]:
                    add("bowler_wickets", f"{nm(pid)}, wickets", wa[pid], wc[pid])
                if ra[pid] != rc[pid]:
                    add("bowler_runs", f"{nm(pid)}, runs conceded", ra[pid], rc[pid])
            elif pid in wa and (wa[pid] or ra[pid]):
                add("bowler_wickets", f"{nm(pid)}, bowled on the Cricket Australia card only", wa[pid], None)
            elif pid in wc and (wc[pid] or rc[pid]):
                add("bowler_wickets", f"{nm(pid)}, bowled on the club card only", None, wc[pid])

        # Totals and extras, only where BOTH sides carry the figure.
        totals = _totals_by_innings(p.get("innings_totals"))
        inn_rows = {r["innings_number"]: r for r in club_inn}
        for i, n_ca in enumerate(ours_ca):
            t = totals.get(n_ca)
            if i >= len(ours_club) or not t:
                continue
            row = inn_rows.get(ours_club[i])
            if not row:
                continue
            extras_club = _extras_of(row)
            if t.get("extras") is not None and extras_club is not None and t["extras"] != extras_club:
                add("extras", "Extras", t["extras"], extras_club)
            total_club = row.get("total_runs")
            if total_club is None and extras_club is not None:
                total_club = sum(r["runs"] for r in cb if r["innings_number"] == ours_club[i]) + extras_club
            if t.get("runs_scored") is not None and total_club is not None and t["runs_scored"] != total_club:
                add("team_total", "Team total", t["runs_scored"], total_club)
        opp_ca = [n for n in sorted(totals) if n not in ours_ca]
        for k, n_ca in enumerate(opp_ca):
            if k >= len(ours_club):
                break
            row = inn_rows.get(ours_club[k] + 1)
            t = totals.get(n_ca)
            if row and t and row.get("total_runs") is not None and t.get("runs_scored") is not None \
                    and row["total_runs"] != t["runs_scored"]:
                add("opp_total", "Opposition total", t["runs_scored"], row["total_runs"])

    if group not in ("nocard", "pairing"):
        ra_, rc_ = ca_result_for(org_id, p), result_word(p.get("m_result"))
        if ra_ and rc_ and ra_ != rc_:
            if {ra_, rc_} == {"WIN", "LOSS"}:
                add("result_flip", "Result", ra_, rc_)
            else:
                add("result", "Result", ra_, rc_)
        if p.get("g_date") and p.get("m_date") and p["g_date"] != p["m_date"]:
            add("date", "Date", str(p["g_date"]), str(p["m_date"]))

    items.sort(key=lambda it: (_ORDER.index(it["kind"]), -abs((it["ca"] or 0) - (it["club"] or 0))
                               if isinstance(it["ca"], int) and isinstance(it["club"], int) else 0))
    if group is None:
        if any(it["kind"] in _SEVERE for it in items):
            group = "differ"
        elif items:
            group = "small"
        else:
            group = "agree"
    size = min(100, sum(it["weight"] for it in items))
    return {"group": group, "items": items, "size": size, "shared": shared,
            "club_batters": len(card_club), "ca_batters": len(card_ca),
            "headline": headline(items[0]) if items else None}


def headline(item: dict) -> str:
    a, c = item["ca"], item["club"]
    if a is None or c is None:
        return item["label"]
    return f"{item['label']} {a} v {c}"


def club_richer_of(club_bat: list, ca_bat: list, club_holds: dict, ca_holds: dict) -> dict:
    """What the club card holds that Cricket Australia's card does not, as {kind: how many}.
    Balls faced are counted per batter (same player and innings, club has a figure, Cricket
    Australia has none); credits, fall of wickets and partnerships by count, where the club has
    more. Empty means the club card adds nothing, so Cricket Australia's card is the richer one."""
    ca_has_balls = {(r["pid"], r["innings_number"]) for r in ca_bat if not r["dnb"] and (r["balls"] or 0) > 0}
    out = {}
    balls = sum(1 for r in club_bat if not r["dnb"] and (r["balls"] or 0) > 0
                and (r["pid"], r["innings_number"]) not in ca_has_balls)
    if balls:
        out["balls"] = balls
    for kind in ("credits", "fow", "partnerships"):
        extra = (club_holds.get(kind) or 0) - (ca_holds.get(kind) or 0)
        if extra > 0:
            out[kind] = extra
    return out


def suggest(group: str, items: list, ca_has_detail: bool, club_richer: Optional[dict] = None) -> Optional[str]:
    if group in ("agree", "small"):
        if club_richer:
            return "hybrid" if ca_has_detail else "club"
        return "ca"
    if any(it["kind"] in ("result_flip", "team_total") for it in items):
        return None  # a different winner or total is never suggested
    if group == "differ" and ca_has_detail and sum(1 for it in items if it["category"] == "batting") <= 3:
        return "hybrid"
    return None


def current_choice(p: dict) -> str:
    """What the site shows now: the recorded choice, else whichever half `pair_prefers_import`
    names. The two agree for every match a person has chosen for."""
    if p.get("review_choice") in CHOICES:
        return p["review_choice"]
    return "club" if p.get("pair_prefers_import") else "ca"


async def _names(db, org_id: str) -> dict:
    return {r[0]: r[1] for r in (await db.execute(text(
        "SELECT id::text, COALESCE(NULLIF(display_name_override, ''), name) FROM players "
        "WHERE organisation_id = CAST(:org AS UUID)"), {"org": org_id})).all()}


async def _sources(db, org_id: str) -> dict:
    return {r["mid"]: r for r in await _all(db, _SOURCES, org=org_id)}


def source_of(p: dict, src: Optional[dict]) -> dict:
    """Where the club card came from: a named file, an import with no file name, CricketStatz,
    a photo read by the scorecard reader, or typed in by hand."""
    if src:
        who = src.get("username")
        if src.get("filename"):
            return {"kind": "file", "label": f"Imported from file {src['filename']}",
                    "filename": src["filename"], "at": src["at"], "by": who}
        return {"kind": "import", "label": "Imported from a file", "filename": None,
                "at": src["at"], "by": who}
    if p.get("from_cricketstatz"):
        return {"kind": "cricketstatz", "label": "Imported from CricketStatz", "filename": None,
                "at": p.get("created_at"), "by": None}
    if p.get("has_payload"):
        return {"kind": "photo", "label": "Read from a scorebook photo", "filename": None,
                "at": p.get("created_at"), "by": None}
    return {"kind": "typed", "label": "Typed in by a club admin", "filename": None,
            "at": p.get("created_at"), "by": None}


async def review_rows(db, org_id, *, mids: Optional[list] = None) -> list:
    """Every paired match of the club (or just ``mids``), compared, as plain dicts."""
    org = str(org_id)
    sql = _PAIRED + (_ONLY if mids else "")
    params = {"org": org, **({"mids": [str(m) for m in mids]} if mids else {})}
    paired = await _all(db, sql, **params)
    if not paired:
        return []
    ids = [p["mid"] for p in paired]
    gids = sorted({p["gid"] for p in paired})
    club_bat = _grouped(await _all(db, _CLUB_BAT, ids=ids), "mid")
    ca_bat = _grouped(await _all(db, _CA_BAT, org=org, ids=gids), "gid")
    club_bowl = _grouped(await _all(db, _CLUB_BOWL, ids=ids), "mid")
    ca_bowl = _grouped(await _all(db, _CA_BOWL, org=org, ids=gids), "gid")
    club_inn = _grouped(await _all(db, _CLUB_INN, ids=ids), "mid")
    inv = defaultdict(lambda: defaultdict(int))
    for r in await _all(db, _INVENTORY, org=org, gids=gids, mids=ids):
        inv[(r["side"], r["k"])][r["what"]] = r["n"]
    names = await _names(db, org)
    sources = await _sources(db, org)

    out = []
    for p in paired:
        mid, gid = p["mid"], p["gid"]
        cmp = compare_match(org, p, club_bat.get(mid, []), ca_bat.get(gid, []),
                            club_bowl.get(mid, []), ca_bowl.get(gid, []), club_inn.get(mid, []), names)
        ca_inv, club_inv = dict(inv[("ca", gid)]), dict(inv[("club", mid)])
        ca_balls = sum(1 for r in ca_bat.get(gid, []) if not r["dnb"] and (r["balls"] or 0) > 0)
        club_balls = sum(1 for r in club_bat.get(mid, []) if not r["dnb"] and r["balls"] is not None)
        ca_has_detail = bool(ca_inv.get("credits") or ca_inv.get("fow") or ca_balls)
        club_richer = club_richer_of(club_bat.get(mid, []), ca_bat.get(gid, []), club_inv, ca_inv)
        out.append({
            "match_id": mid, "game_id": gid, "season": p["season_name"], "grade": p["grade_name"],
            "date": p["m_date"] or p["g_date"], "opposition": p["m_opposition"] or p["g_opposition"],
            "group": cmp["group"], "items": cmp["items"], "headline": cmp["headline"],
            "size": cmp["size"], "shared": cmp["shared"], "club_batters": cmp["club_batters"],
            "ca_batters": cmp["ca_batters"],
            "suggested": suggest(cmp["group"], cmp["items"], ca_has_detail, club_richer),
            "club_richer": club_richer,
            "current": current_choice(p), "decided_by_hand": p["review_source"] == "hand",
            "decided_source": p["review_source"], "decided_at": p["review_decided_at"],
            "note": p["review_note"], "pair_ok": bool(p["review_pair_ok"]),
            "locked": bool(p["pairing_locked"]),
            "ca_holds": {**ca_inv, "balls": ca_balls}, "club_holds": {**club_inv, "balls": club_balls},
            "source": source_of(p, sources.get(mid)),
        })
    return out


def season_sort_key(name: Optional[str]):
    """Newest season first: 'Summer 2025/26' before 'Summer 2008/09'."""
    import re
    m = re.search(r"(\d{4})", name or "")
    return -(int(m.group(1)) if m else 0)


def overview(rows: list) -> dict:
    groups = {g: 0 for g in GROUPS}
    by_season: dict = {}
    for r in rows:
        groups[r["group"]] += 1
        s = by_season.setdefault(r["season"] or "No season", {
            "season": r["season"] or "No season", "matches": 0, "ca": 0, "club": 0, "hybrid": 0,
            "needs_decision": 0})
        s["matches"] += 1
        s[r["current"]] += 1
        if r["group"] in ("differ", "pairing") and not r["decided_by_hand"]:
            s["needs_decision"] += 1
    seasons = sorted(by_season.values(), key=lambda s: (season_sort_key(s["season"]), s["season"]))
    current = {c: sum(1 for r in rows if r["current"] == c) for c in CHOICES}
    richer = sum(1 for r in rows if r["group"] == "agree" and r["club_richer"] and not r["decided_by_hand"])
    return {"total": len(rows), "groups": groups, "seasons": seasons, "current": current,
            "agree_club_richer": richer,
            "decided_by_hand": sum(1 for r in rows if r["decided_by_hand"])}


# --- one match, side by side ---------------------------------------------------------------------

async def match_detail(db, org_id, mid) -> Optional[dict]:
    """Everything the compare screen draws for one match: the two cards aligned row by row, with
    the cells that differ marked, what each side holds beyond the lines, and the two ids."""
    org = str(org_id)
    rows = await review_rows(db, org, mids=[mid])
    if not rows:
        return None
    r = rows[0]
    p = (await _all(db, _PAIRED + _ONLY, org=org, mids=[str(mid)]))[0]
    names = await _names(db, org)
    club_bat = [x for x in await _all(db, _CLUB_BAT, ids=[str(mid)]) if not x["dnb"]]
    ca_bat = [x for x in await _all(db, _CA_BAT, org=org, ids=[r["game_id"]]) if not x["dnb"]]
    club_bowl = await _all(db, _CLUB_BOWL, ids=[str(mid)])
    ca_bowl = await _all(db, _CA_BOWL, org=org, ids=[r["game_id"]])
    club_inn = {x["innings_number"]: x for x in await _all(db, _CLUB_INN, ids=[str(mid)])}
    ours_club = sorted({x["innings_number"] for x in club_bat})
    ours_ca = sorted({x["innings_number"] for x in ca_bat})
    by_ca = {(x["pid"], ours_ca.index(x["innings_number"])): x for x in ca_bat}
    by_club = {(x["pid"], ours_club.index(x["innings_number"])): x for x in club_bat}

    def side(x):
        if not x:
            return None
        return {"runs": x["runs"], "balls": x["balls"], "how_out": x["dismissal_type"],
                "position": x["batting_position"], "not_out": bool(x["not_out"])}

    innings = []
    for i in range(max(len(ours_ca), len(ours_club), 1)):
        lines = []
        keys = sorted([k for k in set(by_ca) | set(by_club) if k[1] == i],
                      key=lambda k: ((by_club.get(k) or by_ca.get(k))["batting_position"] is None,
                                     (by_club.get(k) or by_ca.get(k))["batting_position"] or 0,
                                     names.get(k[0]) or ""))
        for k in keys:
            a, c = by_ca.get(k), by_club.get(k)
            differs = bool(a and c and a["runs"] != c["runs"]) or not (a and c)
            lines.append({"player_id": k[0], "name": names.get(k[0]) or k[0][:8],
                          "ca": side(a), "club": side(c), "differs": differs})
        innings.append({"number": i + 1, "batting": lines})
    wa, wc = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for x in ca_bowl:
        wa[x["pid"]][0] += x["wickets"]
        wa[x["pid"]][1] += x["runs"]
    for x in club_bowl:
        wc[x["pid"]][0] += x["wickets"]
        wc[x["pid"]][1] += x["runs"]
    bowling = [{"player_id": pid, "name": names.get(pid) or pid[:8],
                "ca": {"wickets": wa[pid][0], "runs": wa[pid][1]} if pid in wa else None,
                "club": {"wickets": wc[pid][0], "runs": wc[pid][1]} if pid in wc else None,
                "differs": pid not in wa or pid not in wc or wa[pid] != wc[pid]}
               for pid in sorted(set(wa) | set(wc), key=lambda k: names.get(k) or "")]
    totals = _totals_by_innings(p.get("innings_totals"))
    ca_totals = [{"innings": ours_ca.index(n) + 1, "runs": t.get("runs_scored"), "wickets": t.get("wickets"),
                  "extras": t.get("extras")} for n, t in sorted(totals.items()) if n in ours_ca]
    club_totals = [{"innings": ours_club.index(n) + 1, "runs": x.get("total_runs"),
                    "wickets": x.get("total_wickets"), "extras": _extras_of(x)}
                   for n, x in sorted(club_inn.items()) if n in ours_club]
    from app.services.card_review_actions import history

    return {
        **r,
        "date": str(r["date"]) if r["date"] else None,
        "ca_date": str(p["g_date"]) if p["g_date"] else None,
        "club_date": str(p["m_date"]) if p["m_date"] else None,
        "ca_result": ca_result_for(org, p), "club_result": result_word(p.get("m_result")),
        "ca_opposition": p["g_opposition"], "club_opposition": p["m_opposition"],
        "innings": innings, "bowling": bowling,
        "totals": {"ca": ca_totals, "club": club_totals},
        "effective_game_id": r["match_id"] if r["current"] != "ca" else r["game_id"],
        "history": [{**h, "created_at": h["created_at"].isoformat() if h["created_at"] else None,
                     "undone_at": h["undone_at"].isoformat() if h["undone_at"] else None}
                    for h in await history(db, org, mid)],
    }


async def for_game(db, org_id, any_id) -> Optional[dict]:
    """The pair a match page belongs to, whichever of its two ids the page was opened on."""
    org = str(org_id)
    row = (await _all(db, """
        SELECT id::text AS mid FROM manual_games
         WHERE organisation_id = CAST(:o AS UUID)
           AND superseded_by_game_id IS NOT NULL
           AND (id = CAST(:i AS UUID) OR superseded_by_game_id = CAST(:i AS UUID))
         LIMIT 1""", o=org, i=str(any_id)))
    if not row:
        return None
    rows = await review_rows(db, org, mids=[row[0]["mid"]])
    if not rows:
        return None
    r = rows[0]
    return {"paired": True, "match_id": r["match_id"], "game_id": r["game_id"], "current": r["current"],
            "group": r["group"], "suggested": r["suggested"], "decided_by_hand": r["decided_by_hand"],
            "headline": r["headline"], "item_count": len(r["items"]),
            "effective_game_id": r["match_id"] if r["current"] != "ca" else r["game_id"]}


_CAND = """
    SELECT g.id::text AS gid, g.played_at, g.opp_club_name, g.home_team, g.away_team,
           g.home_org_id::text AS home_org, g.away_org_id::text AS away_org,
           COALESCE(gr.display_name_override, gr.name) AS grade,
           (SELECT mg2.id::text FROM manual_games mg2 WHERE mg2.superseded_by_game_id = g.id
               AND mg2.id <> CAST(:mid AS UUID) LIMIT 1) AS taken_by
      FROM games g LEFT JOIN grades gr ON gr.id = g.grade_id LEFT JOIN seasons s ON s.id = gr.season_id
     WHERE (g.home_org_id = CAST(:org AS UUID) OR g.away_org_id = CAST(:org AS UUID)
            OR s.organisation_id = CAST(:org AS UUID))
       AND g.played_at BETWEEN CAST(:d AS DATE) - 7 AND CAST(:d AS DATE) + 7
       AND g.id <> CAST(:cur AS UUID)
"""


async def pairing_candidates(db, org_id, mid, *, limit: int = 3) -> list:
    """Other Cricket Australia games of the club close to the match's date, best score match first.

    Scored on batters appearing with the same runs on both cards (the evidence the pairing
    itself rests on), so a re-link is offered only where the scorecards back it."""
    org = str(org_id)
    p = (await _all(db, _PAIRED + _ONLY, org=org, mids=[str(mid)]))
    if not p or not p[0]["m_date"]:
        return []
    p = p[0]
    club = {(x["pid"], x["runs"]) for x in await _all(db, _CLUB_BAT, ids=[str(mid)])
            if not x["dnb"] and x["runs"] is not None}
    games = await _all(db, _CAND, mid=str(mid), org=org, d=p["m_date"], cur=p["gid"])
    if not games:
        return []
    ca = _grouped(await _all(db, _CA_BAT, org=org, ids=[g["gid"] for g in games]), "gid")
    out = []
    for g in games:
        card = {(x["pid"], x["runs"]) for x in ca.get(g["gid"], []) if not x["dnb"] and x["runs"] is not None}
        shared = len(club & card)
        if shared < 2:
            continue
        opp = (g["away_team"] if g["home_org"] == org else g["home_team"] if g["away_org"] == org
               else g["opp_club_name"])
        out.append({"game_id": g["gid"], "date": str(g["played_at"]), "opposition": opp, "grade": g["grade"],
                    "shared": shared, "ca_batters": len(card), "club_batters": len(club),
                    "taken_by": g["taken_by"]})
    out.sort(key=lambda c: (-c["shared"], c["date"]))
    return out[:limit]


# --- the spreadsheet for the reviewer --------------------------------------------------------------

_CHOICE_WORDS = {"ca": "Cricket Australia", "club": "Club scorecard", "hybrid": "Club + CA detail", None: ""}
RICHER_WORDS = {"balls": "balls faced", "credits": "dismissal credits", "fow": "fall of wickets",
                "partnerships": "partnerships"}
EXPORT_HEADERS = ["Match id", "Season", "Grade", "Date", "Opposition", "Group", "Biggest difference",
                  "Number of differences", "All differences", "Size (0 to 100)", "Suggested", "Showing now",
                  "Chosen by hand", "Club scorecard source", "Cricket Australia also holds",
                  "Club scorecard holds more",
                  "Review link", "Your choice", "Notes"]
_GROUP_WORDS = {"agree": "Scores agree", "small": "Small differences", "differ": "Scores differ",
                "pairing": "Pairing looks wrong", "nocard": "No Cricket Australia card"}


def export_rows(rows: list, base_url: str = "") -> list:
    """One spreadsheet row per match with a discrepancy (everything except an exact match or a
    match with no Cricket Australia card), newest season first, biggest difference first. An exact
    match is listed only when the club card holds something Cricket Australia's lacks, because a
    person has to decide it. The last two columns are blank for the reviewer to fill in."""
    keep = [r for r in rows if r["group"] in ("differ", "small", "pairing")
            or (r["group"] == "agree" and r["club_richer"])]
    keep.sort(key=lambda r: (season_sort_key(r["season"]), str(r["date"]) or ""), reverse=False)
    keep.sort(key=lambda r: ({"differ": 0, "pairing": 1, "small": 2, "agree": 3}[r["group"]], season_sort_key(r["season"]),
                             -r["size"], str(r["date"])))
    out = []
    for r in keep:
        diffs = "; ".join(
            (f"{i['label']}: Cricket Australia {i['ca']}, club {i['club']}"
             if i["ca"] is not None and i["club"] is not None else i["label"]) for i in r["items"])
        richer = ", ".join(f"{name} {r['club_richer'][k]}" for k, name in RICHER_WORDS.items() if r["club_richer"].get(k))
        if not diffs:
            diffs = "The scores agree, but the club card holds more than Cricket Australia's"
        holds = ", ".join(f"{k} {v}" for k, v in (
            ("balls faced", r["ca_holds"].get("balls")), ("dismissal credits", r["ca_holds"].get("credits")),
            ("fall of wickets", r["ca_holds"].get("fow")), ("partnerships", r["ca_holds"].get("partnerships")),
            ("opposition batters", r["ca_holds"].get("opp_batters"))) if v)
        out.append([
            r["match_id"], r["season"] or "", r["grade"] or "", str(r["date"] or ""), r["opposition"] or "",
            _GROUP_WORDS[r["group"]], r["headline"] or "", len(r["items"]), diffs, r["size"],
            _CHOICE_WORDS[r["suggested"]], _CHOICE_WORDS[r["current"]],
            "yes" if r["decided_by_hand"] else "", r["source"]["label"], holds, richer,
            f"{base_url}/admin/card-review/match/{r['match_id']}" if base_url else "", "", ""])
    return out
