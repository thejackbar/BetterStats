"""Performance Tracker: one competition's round, read from one pasted match link.

An association workspace pastes a play.cricket.com.au match link (or a grade link
with the round picked) for each competition it follows. That link names a grade and a round, and
this reads the WHOLE round the same way an association workspace's posts do
(services/social_competition.resolve_round): every finished match in the grade
with that round id. Nothing here reads or writes a club's own data, and no side
is "ours", so a club and an association workspace get the same answer.

What one pull gives the tracker:

  results        every finished match, home side first, with the scores, the
                 result text and the margin as a number (for "closest match")
  batting        the round's best innings, best first
  bowling        the round's best bowling in an innings, best first
  performers     the round's best all-round days, scored with the same points as
                 player of the match and team of the week (_rank_our_side)
  milestones     fifties, hundreds, five-wicket hauls, hat-tricks, big catching days
  catches        catching dismissals; those Cricket Australia filmed carry a clip
  run_outs       run outs, with a clip when filmed
  ladder         the grade ladder as Cricket Australia shows it now
  upsets         a winner sitting well below the side it beat on that ladder
  next_round     the next round's fixtures, each side's ladder place, and a
                 suggested match of the round (the two highest placed sides)

Upsets are read off the CURRENT ladder (Cricket Australia publishes no ladder as
it stood before the round), so the page names that lens.
"""
from __future__ import annotations

import asyncio
import re

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services.social_competition import (
    _club_of,
    _labels,
    _round_cards,
    _round_id,
    _round_name,
    _season_label,
    _sides,
    resolve_round,
    short_club,
)
from app.services.social_rounds import (
    _DNB_TYPES,
    _NOT_OUT_ID,
    _label,
    _match_day_time,
    _rank_our_side,
    _round_label,
    _score_str,
    _team_id_from_inn,
    _to_12h,
)

MATCH_URL = "https://play.cricket.com.au/match/{}"

# How many of each list a pull hands back. A grade round is a handful of
# matches, so these are generous; the page shows the top few and keeps the rest
# for a host who wants to read further down.
_TOP_BAT = 12
_TOP_BOWL = 12
_TOP_PERFORMERS = 8
_MAX_CLIPS = 30

# A run margin and a wicket margin are not the same unit. For ranking "closest
# match" one wicket in hand is counted as this many runs, a rough par for club
# cricket. The page shows the real margin; this only orders the list.
RUNS_PER_WICKET = 12

# An upset is a winner this many ladder places or more below the side it beat.
UPSET_GAP = 3

_MARGIN_RE = re.compile(r"\bby\s+(\d+)\s+(run|wicket|wkt)", re.I)
_CAUGHT_RE = re.compile(r"^\s*c\s*(?:&|and)\s*b\s*:?\s*(.+?)\s*$|^\s*c\s*:\s*(.+?)\s+b\s*:", re.I)
_RUN_OUT_RE = re.compile(r"run\s*out\s*\(([^)]*)\)", re.I)


# ── Names ─────────────────────────────────────────────────────────────────────

def _team_names(matches: list[dict]) -> dict[str, str]:
    """team id -> the name a host reads out. The same choice as the posts
    (social_competition._labels: a club's short name when it has one side in the
    grade, else the side's own name), in its own casing rather than capitals."""
    upper = _labels(matches)
    out: dict[str, str] = {}
    for m in matches:
        for t in list(_sides(m)) + list(m.get("teams") or []):
            tid = (t.get("id") or "").lower()
            if not tid or tid in out:
                continue
            want = upper.get(tid, "")
            club = short_club(_club_of(t)["name"])
            for cand in (club, t.get("displayName") or "", _club_of(t)["name"]):
                if cand and cand.upper() == want:
                    out[tid] = cand
                    break
            else:
                out[tid] = t.get("displayName") or club or want.title()
    return out


def _tidy(name: str) -> str:
    """A name typed all in lower case ('sourav goyal') reads as 'Sourav Goyal'.
    Any other casing is the club's own and is kept."""
    n = (name or "").strip()
    return n.title() if n and n == n.lower() else n


def _roster_names(sc: dict) -> dict[str, str]:
    """participant id -> full display name, from both sides' team sheets."""
    out: dict[str, str] = {}
    for team in sc.get("teams") or []:
        for p in (team.get("players") or []) + (team.get("nonPlayingMembers") or []):
            pid = (p.get("participantId") or "").lower()
            name = _tidy(p.get("displayName") or p.get("name") or "")
            if pid and name and pid not in out:
                out[pid] = name
    return out


def _short_to_full(sc: dict, team_id: str, roster: dict[str, str]) -> dict[str, str]:
    """'O Bower' -> 'Owen Bower' for one side, so a fielder named in dismissal
    text (which uses the short name) reads in full. The team sheet carries no
    short name, so the pairing comes from that side's own scorecard rows (its
    batting, and its bowling and fielding while the other side bats)."""
    out: dict[str, str] = {}
    for inn in sc.get("innings") or []:
        batting_side = (_team_id_from_inn(inn) or "") == team_id
        rows = (inn.get("batting") or []) if batting_side else \
            (inn.get("bowling") or []) + (inn.get("fielding") or [])
        for r in rows:
            short = (r.get("playerShortName") or "").strip()
            full = roster.get((r.get("participantId") or "").lower())
            if short and full:
                out.setdefault(short.lower(), full)
    return out


def _full(short_map: dict[str, str], short: str) -> str:
    s = (short or "").strip()
    return short_map.get(s.lower(), s)


# ── Margins ───────────────────────────────────────────────────────────────────

def margin_of(result_text: str | None) -> dict:
    """``{runs, wickets, tie, closeness}`` from a result line. ``closeness`` orders
    matches for "closest" (smaller is closer); None when the line names no margin
    (a draw, a no result, a forfeit)."""
    text = result_text or ""
    if re.search(r"\btie[d]?\b", text, re.I):
        return {"runs": None, "wickets": None, "tie": True, "closeness": 0}
    m = _MARGIN_RE.search(text)
    if not m:
        return {"runs": None, "wickets": None, "tie": False, "closeness": None}
    n = int(m.group(1))
    if m.group(2).lower().startswith("run"):
        return {"runs": n, "wickets": None, "tie": False, "closeness": n}
    return {"runs": None, "wickets": n, "tie": False, "closeness": n * RUNS_PER_WICKET}


# ── Ladder ────────────────────────────────────────────────────────────────────

def ladder_rows(raw, names: dict[str, str]) -> list[dict]:
    """The first ladder view Cricket Australia lists for the grade ("Overall" when
    there are several), as ``[{rank, team_id, team, played, won, lost, points}]``.
    The upstream shape is read defensively (routers/ladders.py has the same)."""
    if not isinstance(raw, dict):
        return []
    views = [v for v in (raw.get("ladders") or []) if isinstance(v, dict)]
    if not views:
        return []
    view = next((v for v in views if (v.get("name") or "").lower() == "overall"), views[0])
    rows = []
    for pool in view.get("pools") or []:
        for t in pool.get("teams") or []:
            if not isinstance(t, dict):
                continue
            stats = {d.get("id"): d.get("val") for d in (t.get("ladderData") or []) if isinstance(d, dict)}
            tid = (t.get("id") or "").lower()
            rows.append({
                "rank": t.get("rank"),
                "team_id": tid,
                "team": names.get(tid) or t.get("displayName") or "",
                "played": stats.get("played"),
                "won": stats.get("won"),
                "lost": stats.get("lost"),
                "points": stats.get("competitionPoints"),
                "quotient": stats.get("quotient"),
            })
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] if r["rank"] is not None else 9999))
    return rows


# ── Reading one scorecard ─────────────────────────────────────────────────────

def _card_lines(m: dict, sc: dict, names: dict[str, str]) -> dict:
    """Every innings, spell, catch and run out on one card, each tagged with the
    side and the opponent. Absent and did-not-bat rows are not innings."""
    mid = m.get("id")
    home, away = _sides(m)
    hid, aid = (home.get("id") or "").lower(), (away.get("id") or "").lower()
    roster = _roster_names(sc)

    def other(tid):
        return aid if tid == hid else hid

    bats, bowls, catches, run_outs, fielders = [], [], [], [], {}
    for inn in sc.get("innings") or []:
        bat_tid = _team_id_from_inn(inn) or ""
        fld_tid = other(bat_tid)
        fld_short = _short_to_full(sc, fld_tid, roster)
        keepers = {
            (f.get("playerShortName") or "").strip().lower()
            for f in inn.get("fielding") or []
            if int(f.get("wicketKeeperCatches") or 0) > 0 or int(f.get("stumpings") or 0) > 0
        }
        for b in inn.get("batting") or []:
            dt = (b.get("dismissalType") or "").strip().lower()
            if dt in _DNB_TYPES:
                continue
            pid = (b.get("participantId") or "").lower()
            name = roster.get(pid) or _tidy(b.get("playerShortName") or "")
            runs = int(b.get("runsScored") or 0)
            balls = int(b.get("ballsFaced") or 0)
            not_out = (b.get("dismissalTypeId") == _NOT_OUT_ID) or dt == "not out"
            bats.append({
                "name": name, "team": names.get(bat_tid, ""), "team_id": bat_tid, "opp": names.get(fld_tid, ""),
                "runs": runs, "balls": balls,
                "fours": int(b.get("foursScored") or 0), "sixes": int(b.get("sixesScored") or 0),
                "not_out": not_out, "match_id": mid,
            })
            text = b.get("dismissalText") or ""
            clip = ((b.get("highlight") or {}).get("highlightURL")) or None
            if dt == "caught" or b.get("dismissalTypeId") == 2:
                cm = _CAUGHT_RE.match(text)
                bowler_short = (text.split("b:")[-1].strip() if "b:" in text else "")
                catcher_short = (cm.group(1) or cm.group(2)).strip() if cm else ""
                catches.append({
                    "fielder": _full(fld_short, catcher_short) or None,
                    "bowler": _full(fld_short, bowler_short) or None,
                    "batter": name, "batter_runs": runs,
                    "team": names.get(fld_tid, ""), "opp": names.get(bat_tid, ""),
                    "keeper": bool(catcher_short) and catcher_short.lower() in keepers,
                    "caught_and_bowled": bool(cm and cm.group(1)),
                    "clip": clip, "match_id": mid,
                })
            elif "run out" in dt or "run out" in text.lower():
                rm = _RUN_OUT_RE.search(text)
                who = [f.strip() for f in (rm.group(1).split(",") if rm else []) if f.strip()]
                run_outs.append({
                    "fielders": [_full(fld_short, f) for f in who],
                    "batter": name, "batter_runs": runs,
                    "team": names.get(fld_tid, ""), "opp": names.get(bat_tid, ""),
                    "clip": clip, "match_id": mid,
                })
        for bw in inn.get("bowling") or []:
            pid = (bw.get("participantId") or "").lower()
            name = roster.get(pid) or _tidy(bw.get("playerShortName") or "")
            bowls.append({
                "name": name, "team": names.get(fld_tid, ""), "team_id": fld_tid, "opp": names.get(bat_tid, ""),
                "overs": str(bw.get("oversBowled") or 0), "maidens": int(bw.get("maidensBowled") or 0),
                "runs": int(bw.get("runsConceded") or 0), "wickets": int(bw.get("wicketsTaken") or 0),
                "hat_tricks": int(bw.get("hatTricks") or 0), "match_id": mid,
            })
        for f in inn.get("fielding") or []:
            pid = (f.get("participantId") or "").lower()
            if not pid:
                continue
            total = f.get("totalCatches")
            if total is None:
                total = int(f.get("catches") or 0) + int(f.get("wicketKeeperCatches") or 0)
            slot = fielders.setdefault(pid, {
                "name": roster.get(pid) or _tidy(f.get("playerShortName") or ""),
                "team": names.get(fld_tid, ""), "catches": 0, "keeper_catches": 0,
                "stumpings": 0, "run_outs": 0, "match_id": mid,
            })
            slot["catches"] += int(total or 0)
            slot["keeper_catches"] += int(f.get("wicketKeeperCatches") or 0)
            slot["stumpings"] += int(f.get("stumpings") or 0)
            slot["run_outs"] += int(f.get("runOuts") or 0)
    return {"bats": bats, "bowls": bowls, "catches": catches, "run_outs": run_outs,
            "fielders": list(fielders.values())}


def _bat_key(b):
    return (-b["runs"], b["balls"] if b["balls"] else 999, b["name"])


def _bowl_key(b):
    return (-b["wickets"], b["runs"], b["name"])


def bat_line(b: dict) -> str:
    """'112* (98)'."""
    star = "*" if b.get("not_out") else ""
    return f"{b['runs']}{star} ({b['balls']})" if b.get("balls") else f"{b['runs']}{star}"


def bowl_line(b: dict) -> str:
    """'5/23 (10)'."""
    return f"{b['wickets']}/{b['runs']} ({b['overs']})"


def _milestones(bats, bowls, fielders) -> list[dict]:
    out = []
    for b in bats:
        if b["runs"] >= 100:
            out.append({"kind": "hundred", "name": b["name"], "team": b["team"],
                        "text": f"{b['name']} ({b['team']}) made {bat_line(b)} against {b['opp']}",
                        "match_id": b["match_id"], "sort": (0, -b["runs"])})
        elif b["runs"] >= 50:
            out.append({"kind": "fifty", "name": b["name"], "team": b["team"],
                        "text": f"{b['name']} ({b['team']}) made {bat_line(b)} against {b['opp']}",
                        "match_id": b["match_id"], "sort": (2, -b["runs"])})
    for b in bowls:
        if b["hat_tricks"]:
            out.append({"kind": "hat_trick", "name": b["name"], "team": b["team"],
                        "text": f"{b['name']} ({b['team']}) took a hat-trick against {b['opp']} ({bowl_line(b)})",
                        "match_id": b["match_id"], "sort": (-1, 0)})
        if b["wickets"] >= 5:
            out.append({"kind": "five_for", "name": b["name"], "team": b["team"],
                        "text": f"{b['name']} ({b['team']}) took {bowl_line(b)} against {b['opp']}",
                        "match_id": b["match_id"], "sort": (1, -b["wickets"])})
    for f in fielders:
        dismissals = f["catches"] + f["stumpings"] + f["run_outs"]
        if dismissals >= 4:
            out.append({"kind": "fielding", "name": f["name"], "team": f["team"],
                        "text": f"{f['name']} ({f['team']}) had a hand in {dismissals} dismissals in the field",
                        "match_id": f["match_id"], "sort": (3, -dismissals)})
    out.sort(key=lambda x: x["sort"])
    for x in out:
        x.pop("sort")
    return out


def _performer_line(p: dict) -> str:
    parts = []
    bat = p.get("batting")
    if bat:
        parts.append(f"{bat['r']}{'*' if bat.get('notOut') else ''} ({bat['b']})")
    bowl = p.get("bowling")
    if bowl and (bowl.get("w") or bowl.get("o") not in (None, "0.0")):
        parts.append(f"{bowl['w']}/{bowl['r']}")
    fld = p.get("fielding") or {}
    ct = (fld.get("catches") or 0)
    if ct:
        parts.append(f"{ct} ct")
    if fld.get("stumpings"):
        parts.append(f"{fld['stumpings']} st")
    if fld.get("run_outs"):
        parts.append(f"{fld['run_outs']} ro")
    return ", ".join(parts)


# ── Next round ────────────────────────────────────────────────────────────────

def _next_round(all_matches: list[dict], round_matches: list[dict]) -> list[dict]:
    """The matches of the round that starts after this one ends: the earliest
    round whose first day is later than this round's last day."""
    this_ids = {_round_id(m) for m in round_matches}
    this_last = max((_match_day_time(m, last=True)[0] or "" for m in round_matches), default="")
    first_by_round: dict[str, str] = {}
    for m in all_matches:
        rid = _round_id(m)
        if not rid or rid in this_ids:
            continue
        day = _match_day_time(m)[0] or ""
        if day and day > this_last and (rid not in first_by_round or day < first_by_round[rid]):
            first_by_round[rid] = day
    if not first_by_round:
        return []
    nxt = min(first_by_round, key=lambda r: first_by_round[r])
    return sorted((m for m in all_matches if _round_id(m) == nxt), key=lambda x: _match_day_time(x))


def match_of_round(fixtures: list[dict]) -> int | None:
    """Index of the fixture between the two highest placed sides (smallest sum of
    ladder places, then the closer pair). None when no fixture has both places."""
    best, best_key = None, None
    for i, f in enumerate(fixtures):
        hr, ar = f.get("home_rank"), f.get("away_rank")
        if not isinstance(hr, int) or not isinstance(ar, int):
            continue
        key = (hr + ar, abs(hr - ar))
        if best_key is None or key < best_key:
            best, best_key = i, key
    return best


async def _team_crests(db: AsyncSession, org, matches: list[dict]) -> dict[str, dict]:
    """team id -> ``{logo, colour}`` for every side in the grade, through the
    workspace crest library (social_competition._crests). A club has no library,
    so it gets Cricket Australia's crest address as it is."""
    from app.services.social_competition import _crests, is_association
    teams: dict[str, dict] = {}
    for m in matches:
        for t in list(_sides(m)) + list(m.get("teams") or []):
            tid = (t.get("id") or "").lower()
            if tid and _club_of(t)["id"] and tid not in teams:
                teams[tid] = _club_of(t)
    if not teams:
        return {}
    ids = list(teams)
    if is_association(org):
        got = await _crests(db, org, [(teams[t]["id"], teams[t]["logo"], teams[t]["name"]) for t in ids])
    else:
        got = [{"logo": teams[t]["logo"], "colour": None} for t in ids]
    return {t: {"logo": c.get("logo"), "colour": c.get("colour")} for t, c in zip(ids, got)}


# ── The pull ──────────────────────────────────────────────────────────────────

async def pull_competition(db: AsyncSession, org, raw: str) -> dict:
    """One pasted link -> the run sheet's figures for that competition's round.
    An error comes back as ``{kind, message}`` (the same kinds as the posts)."""
    err, ctx = await resolve_round(raw, want="done")
    if err is not None:
        return err

    all_matches, ladder_raw = await asyncio.gather(
        gr.get_grade_matches(ctx["grade_id"]), gr.get_grade_ladder(ctx["grade_id"]),
    )
    all_matches = all_matches or ctx["matches"]
    names = _team_names(all_matches + ctx["matches"])
    ladder = ladder_rows(ladder_raw, names)
    rank_of = {r["team_id"]: r["rank"] for r in ladder if r.get("team_id")}

    pairs, skipped = await _round_cards(ctx, include_live=False)
    done_ids = {m.get("id") for m, _ in pairs}

    results, bats, bowls, catches, run_outs, fielders, performers = [], [], [], [], [], [], []
    for m, sc in pairs:
        home, away = _sides(m)
        hid, aid = (home.get("id") or "").lower(), (away.get("id") or "").lower()
        inn_by_team: dict[str, dict] = {}
        for inn in sc.get("innings") or []:
            tid = _team_id_from_inn(inn)
            if tid:
                inn_by_team.setdefault(tid, inn)
        ms = sc.get("matchSummary") or {}
        winner = None
        for st in ms.get("teams") or []:
            if st.get("isWinner") or (st.get("resultType") or "").upper().startswith("WON"):
                winner = "home" if (st.get("id") or "").lower() == hid else "away"
        result_text = ms.get("resultText") or ms.get("result") or m.get("resultText") or ""
        lines = _card_lines(m, sc, names)
        bats += lines["bats"]
        bowls += lines["bowls"]
        catches += lines["catches"]
        run_outs += lines["run_outs"]
        fielders += lines["fielders"]
        day = _match_day_time(m)[0] or ""
        results.append({
            "match_id": m.get("id"),
            "url": MATCH_URL.format(m.get("id")),
            "home": names.get(hid, ""), "away": names.get(aid, ""), "home_id": hid, "away_id": aid,
            "home_score": _score_str(inn_by_team.get(hid)) or "",
            "away_score": _score_str(inn_by_team.get(aid)) or "",
            "winner": winner,
            "result": result_text,
            "margin": margin_of(result_text),
            "venue": ((m.get("venue") or {}).get("name")) or "",
            "date": day,
            "home_rank": rank_of.get(hid), "away_rank": rank_of.get(aid),
            "top_bat": [{**b, "line": bat_line(b)} for b in sorted(lines["bats"], key=_bat_key)[:2]],
            "top_bowl": [{**b, "line": bowl_line(b)} for b in sorted(lines["bowls"], key=_bowl_key)[:2]],
        })
        # Player of the round: the same points as player of the match, for both sides.
        for team in sc.get("teams") or []:
            tid = (team.get("id") or "").lower()
            if not tid:
                continue
            try:
                ranked = await _rank_our_side(db, org, sc, team_id=tid)
            except HTTPException:
                continue
            for p in ranked["players"][:3]:
                performers.append({
                    "name": _tidy(" ".join(x for x in (p.get("first"), p.get("last")) if x)) or p.get("short"),
                    "team": names.get(tid, ""), "team_id": tid, "opp": names.get(aid if tid == hid else hid, ""),
                    "points": p["points"], "line": _performer_line(p), "match_id": m.get("id"),
                })

    # Finished without a result (abandoned, washed out, forfeited) or not read.
    not_played = []
    for m in ctx["matches"]:
        if m.get("id") in done_ids:
            continue
        home, away = _sides(m)
        not_played.append({
            "match_id": m.get("id"),
            "home": names.get((home.get("id") or "").lower(), home.get("displayName") or ""),
            "away": names.get((away.get("id") or "").lower(), away.get("displayName") or ""),
            "status": (m.get("status") or "").replace("_", " ").title(),
            "result": m.get("resultText") or "",
        })

    if not results:
        return {"kind": "no_results", "message": "No finished matches in that round yet.",
                "grade": ctx["grade_name"], "round": _round_label(ctx["round_name"]),
                "skipped": skipped, "not_played": not_played}

    upsets = []
    for r in results:
        if r["winner"] not in ("home", "away"):
            continue
        w_rank = r["home_rank"] if r["winner"] == "home" else r["away_rank"]
        l_rank = r["away_rank"] if r["winner"] == "home" else r["home_rank"]
        if isinstance(w_rank, int) and isinstance(l_rank, int) and w_rank - l_rank >= UPSET_GAP:
            upsets.append({
                "match_id": r["match_id"],
                "winner": r["home"] if r["winner"] == "home" else r["away"],
                "loser": r["away"] if r["winner"] == "home" else r["home"],
                "winner_rank": w_rank, "loser_rank": l_rank, "result": r["result"],
            })
    upsets.sort(key=lambda u: -(u["winner_rank"] - u["loser_rank"]))

    nxt = _next_round(all_matches, ctx["matches"])
    fixtures = []
    for m in nxt:
        home, away = _sides(m)
        hid, aid = (home.get("id") or "").lower(), (away.get("id") or "").lower()
        day, tm = _match_day_time(m)
        fixtures.append({
            "match_id": m.get("id"), "url": MATCH_URL.format(m.get("id")),
            "home": names.get(hid, home.get("displayName") or ""), "home_id": hid, "away_id": aid,
            "away": names.get(aid, away.get("displayName") or ""),
            "home_rank": rank_of.get(hid), "away_rank": rank_of.get(aid),
            "date": day, "label": _label(day) if day else "", "time": _to_12h(tm),
            "venue": ((m.get("venue") or {}).get("name")) or "",
        })

    performers.sort(key=lambda p: (-p["points"], p["name"]))
    fielders = [f for f in fielders if f["catches"] + f["stumpings"] + f["run_outs"] > 0]
    fielders.sort(key=lambda f: (-(f["catches"] + f["stumpings"] + f["run_outs"]), f["name"]))
    # Filmed dismissals first: a host can watch them before picking the best.
    catches.sort(key=lambda c: (c["clip"] is None, c["keeper"]))
    run_outs.sort(key=lambda c: c["clip"] is None)

    crests = await _team_crests(db, org, all_matches + ctx["matches"])

    last_day = max((r["date"] for r in results if r["date"]), default="")
    first_day = min((r["date"] for r in results if r["date"]), default="")
    return {
        "kind": "round",
        "grade": ctx["grade_name"],
        "grade_id": ctx["grade_id"],
        "round": _round_label(ctx["round_name"]),
        "round_id": ctx["round_id"],
        "season": _season_label(last_day),
        "date": first_day,
        "label": _label(first_day) if first_day else "",
        "results": results,
        "not_played": not_played,
        "skipped": skipped,
        "batting": [{**b, "line": bat_line(b)} for b in sorted(bats, key=_bat_key)[:_TOP_BAT]],
        "bowling": [{**b, "line": bowl_line(b)} for b in sorted(bowls, key=_bowl_key)[:_TOP_BOWL]],
        "performers": performers[:_TOP_PERFORMERS],
        "milestones": _milestones(bats, bowls, fielders),
        "fielders": fielders[:8],
        "catches": catches[:_MAX_CLIPS],
        "catches_total": len(catches),
        "run_outs": run_outs[:_MAX_CLIPS],
        "ladder": ladder,
        # team id -> {logo, colour}: the workspace's crest library, the same crests its posts use.
        "crests": crests,
        "upsets": upsets,
        "upset_gap": UPSET_GAP,
        "next_round": {
            "round": _round_label(_round_name(nxt[0])) if nxt else "",
            "fixtures": fixtures,
            "match_of_round": match_of_round(fixtures),
        },
    }
