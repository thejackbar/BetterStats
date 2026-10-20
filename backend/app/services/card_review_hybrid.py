"""The ``hybrid`` choice: the club's numbers with Cricket Australia's detail added where it fits.

A club card (a scorebook import, a typed card) records runs and wickets and little else. The
synced card it replaced holds balls faced, who took each wicket, the fall of wickets, the
partnerships and the opposition's innings. This copies that detail onto the club card, for ONE
match, and leaves the club's own runs, wickets and result exactly as they are.

WHAT FITS. A piece of detail is copied only where it cannot contradict the club's numbers:

* balls faced for a batter whose runs, batting position and innings are the same on both cards;
* who took each wicket for a bowler whose wicket count is the same on both cards (a bowler held
  under two records, "Smith, Reuben" and "Smith, RG", is matched on surname and initial when
  the counts agree);
* fall of wickets and partnerships for an innings of ours only where every batter's runs agree
  on both cards; for an opposition innings only where the two opposition totals do not differ;
* the opposition's batting and bowling cards and the "c Sam Aplin b Wes Dagg" text for each of
  our dismissals, taken ONCE from the same live Cricket Australia scorecard the match page draws
  for a synced match (the opposition's batters are not stored locally) and kept on
  ``manual_games.review_detail`` for the match page to read. Dismissal text is kept only for a
  batter whose runs agree on both cards. If Cricket Australia cannot be reached the rest still
  comes over and the plan says this part was left out.

WHAT IS LEFT OUT is listed, in plain words, with the reason, so a person can see exactly which
numbers kept something from coming over.

NOTHING IS OVERWRITTEN. A balls figure is filled only where the club's is empty. Rows are
inserted only where the club has none for that innings. Every id written is returned, so
`revert_detail` removes exactly that and nothing else.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Optional

from sqlalchemy import delete as sa_delete, insert, text

from app.models.db import ManualBowlerWicket, ManualFallOfWicket, ManualPartnership
from app.services.card_review import _all, _grouped, _names
from app.services.import_player_link import label

# What a source writes when it knows only HOW a batter was out, not who did it. Text that is
# one of these carries no names, so it is not copied over the club's own.
_BARE = {"c", "b", "lbw", "st", "ct", "run out", "stumped", "caught", "bowled", "not out",
         "retired", "retired hurt", "retired not out", "c&b", "hit wicket", "did not bat",
         "dnb", "absent"}

# A dismissal that credits no bowler, so there is no name to copy.
NO_CREDIT = ("run out", "retired", "retired out", "obstructing the field", "timed out",
             "handled the ball", "hit the ball twice", "absent")


def _uuid(v):
    return v if v is None or isinstance(v, uuid.UUID) else uuid.UUID(str(v))


_CLUB_BAT = """
    SELECT id, player_id::text AS pid, innings_number, runs, balls, batting_position,
           COALESCE(did_not_bat, FALSE) AS dnb
      FROM manual_batting_innings WHERE manual_game_id = CAST(:mid AS UUID)
"""
_CA_BAT = """
    SELECT bi.player_id::text AS pid, bi.innings_number, bi.runs, bi.balls, bi.fours, bi.sixes,
           bi.batting_position, bi.dismissal_type, COALESCE(bi.not_out, FALSE) AS not_out,
           COALESCE(bi.did_not_bat, FALSE) AS dnb, p.organisation_id::text AS org_id,
           COALESCE(NULLIF(p.display_name_override, ''), p.name) AS name
      FROM batting_innings bi JOIN players p ON p.id = bi.player_id
     WHERE bi.game_id = CAST(:gid AS UUID)
"""
_CA_BOWL = """
    SELECT bs.player_id::text AS pid, bs.innings_number, bs.overs, bs.maidens, bs.runs, bs.wickets,
           bs.wides, bs.no_balls, p.organisation_id::text AS org_id,
           COALESCE(NULLIF(p.display_name_override, ''), p.name) AS name
      FROM bowling_spells bs JOIN players p ON p.id = bs.player_id
     WHERE bs.game_id = CAST(:gid AS UUID)
"""
_CLUB_SPELLS = """
    SELECT player_id::text AS pid, COALESCE(SUM(wickets), 0) AS w
      FROM manual_bowling_spells WHERE manual_game_id = CAST(:mid AS UUID) GROUP BY 1
"""
_CA_CREDITS = """
    SELECT bw.innings_number, bw.bowler_id::text AS bowler_id, bw.fielder_id::text AS fielder_id,
           bw.batter_name, bw.batter_position, bw.batter_runs, bw.dismissal_type, bw.caught_behind,
           pb.organisation_id::text AS bowler_org
      FROM bowler_wickets bw LEFT JOIN players pb ON pb.id = bw.bowler_id
     WHERE bw.game_id = CAST(:gid AS UUID)
"""
_CA_FOW = """
    SELECT innings_number, wicket_number, score_at_fall, overs_at_fall, player_id, batter_name
      FROM fall_of_wickets WHERE game_id = CAST(:gid AS UUID)
"""
_CA_PART = """
    SELECT innings_number, wicket_number, batter1_id, batter2_id, runs, balls, batter1_runs,
           batter2_runs, is_club_innings, batter1_name, batter2_name
      FROM partnerships WHERE game_id = CAST(:gid AS UUID)
"""
_CLUB_HAS = """
    SELECT 'fow' AS kind, innings_number, count(*) AS n FROM manual_fall_of_wickets
     WHERE manual_game_id = CAST(:mid AS UUID) GROUP BY innings_number
    UNION ALL SELECT 'part', innings_number, count(*) FROM manual_partnerships
     WHERE manual_game_id = CAST(:mid AS UUID) GROUP BY innings_number
    UNION ALL SELECT 'bw', 0, count(*) FROM manual_bowler_wickets
     WHERE manual_game_id = CAST(:mid AS UUID)
"""
_CLUB_INN = """
    SELECT innings_number, batting_side, total_runs FROM manual_innings
     WHERE manual_game_id = CAST(:mid AS UUID)
"""
_GAME = """
    SELECT mg.superseded_by_game_id::text AS gid, mg.opposition, g.innings_totals
      FROM manual_games mg JOIN games g ON g.id = mg.superseded_by_game_id
     WHERE mg.id = CAST(:mid AS UUID) AND mg.organisation_id = CAST(:org AS UUID)
"""


async def _ca_card(db, gid) -> Optional[dict]:
    """Cricket Australia's scorecard for the synced game, as the match page draws it. Called as
    the route body (the verification suites and Club Room do the same), so a card built here is
    the card a visitor sees. None when Cricket Australia could not be reached."""
    from app.routers.games import get_scorecard

    try:
        card = await get_scorecard(str(gid), db=db, viewer=None, org_param=None)
    except Exception:  # noqa: BLE001 - the copy goes ahead without this one part
        return None
    return card if isinstance(card, dict) else None


def _empty_plan(reason: str) -> dict:
    return {"ok": False, "reason": reason, "balls": [], "credits": [], "fow": [], "part": [],
            "detail": None, "brought": [], "left_out": [reason]}


async def plan_hybrid(db, org_id, mid) -> dict:
    """What copying would bring over and what it would leave out. Writes nothing."""
    org, mid = str(org_id), str(mid)
    g = await _all(db, _GAME, org=org, mid=mid)
    if not g:
        return _empty_plan("This match is not paired to a Cricket Australia card.")
    gid, opposition, innings_totals = g[0]["gid"], g[0]["opposition"], g[0]["innings_totals"]
    club_bat = [r for r in await _all(db, _CLUB_BAT, mid=mid) if not r["dnb"]]
    ca_all = await _all(db, _CA_BAT, gid=gid)
    ca_ours = [r for r in ca_all if r["org_id"] == org and not r["dnb"] and r["runs"] is not None]
    ca_theirs = [r for r in ca_all if r["org_id"] != org]
    if not ca_ours:
        return _empty_plan("Cricket Australia has no card of ours for this match.")
    names = await _names(db, org)
    ours_club = sorted({r["innings_number"] for r in club_bat})
    ours_ca = sorted({r["innings_number"] for r in ca_ours})
    if not ours_club or len(ours_club) != len(ours_ca):
        return _empty_plan("Our innings do not line up between the two cards, so nothing is copied.")
    inn_map = dict(zip(ours_ca, ours_club))
    ca_credits = await _all(db, _CA_CREDITS, gid=gid)
    ca_fow, ca_part = await _all(db, _CA_FOW, gid=gid), await _all(db, _CA_PART, gid=gid)
    ca_bowl = await _all(db, _CA_BOWL, gid=gid)
    seen = ({r["innings_number"] for r in ca_fow} | {r["innings_number"] for r in ca_part}
            | {r["innings_number"] for r in ca_credits} | {r["innings_number"] for r in ca_theirs}
            | {r["innings_number"] for r in ca_bowl})
    for k, n in enumerate(sorted(seen - set(ours_ca))):
        if k < len(ours_club):
            inn_map[n] = ours_club[k] + 1
    has = {(r["kind"], r["innings_number"]): r["n"] for r in await _all(db, _CLUB_HAS, mid=mid)}

    def nm(pid):
        return names.get(pid) or pid[:8]

    brought, left_out = [], []

    # --- balls faced -------------------------------------------------------------------------
    by_key = defaultdict(list)
    for r in ca_ours:
        by_key[(r["pid"], ours_ca.index(r["innings_number"]))].append(r)
    balls, no_balls_runs, agree_runs = [], [], set()
    for r in club_bat:
        key = (r["pid"], ours_club.index(r["innings_number"]))
        cands = by_key.get(key, [])
        same = [c for c in cands if c["runs"] == r["runs"]
                and c["batting_position"] == r["batting_position"]]
        if cands and any(c["runs"] == r["runs"] for c in cands):
            agree_runs.add(key)
        if r["balls"] is not None:
            continue
        good = [c for c in same if (c["balls"] or 0) > 0]
        if len(good) == 1:
            balls.append((r["id"], good[0]["balls"]))
        elif cands and not any(c["runs"] == r["runs"] for c in cands):
            no_balls_runs.append(f"Balls faced for {nm(r['pid'])}: Cricket Australia has "
                                 f"{cands[0]['runs']} runs and the club card {r['runs']}")
    if balls:
        brought.append(f"Balls faced for {len(balls)} batter{'s' if len(balls) != 1 else ''}")
    left_out += no_balls_runs

    # --- who took each wicket (our bowlers' wickets) -------------------------------------------
    credits = []
    ours_credits = [c for c in ca_credits if c["bowler_org"] == org
                    and (c["dismissal_type"] or "").lower() not in NO_CREDIT]
    if ours_credits and not has.get(("bw", 0)):
        club_w = {r["pid"]: int(r["w"]) for r in await _all(db, _CLUB_SPELLS, mid=mid) if int(r["w"]) > 0}
        per = defaultdict(int)
        for c in ours_credits:
            per[c["bowler_id"]] += 1
        used, as_club = set(), {}
        for b, n in per.items():
            if club_w.get(b) == n:
                used.add(b)
                as_club[b] = b
        for b, n in per.items():
            if b in as_club:
                continue
            hit = next((i for i, w in club_w.items()
                        if i not in used and i not in per and w == n
                        and label(names.get(i)) and label(names.get(i)) == label(names.get(b))), None)
            if hit:
                used.add(hit)
                as_club[b] = hit
            else:
                left_out.append(f"Who took {nm(b)}'s wickets: Cricket Australia credits {n}, "
                                f"the club card shows {club_w.get(b, 0)}")
        for c in ours_credits:
            tgt = inn_map.get(c["innings_number"])
            if c["bowler_id"] in as_club and tgt is not None:
                credits.append({**c, "bowler_id": as_club[c["bowler_id"]], "target": tgt})
        if credits:
            brought.append(f"Who took the wicket, for {len(credits)} dismissal{'s' if len(credits) != 1 else ''}")

    # --- fall of wickets and partnerships ------------------------------------------------------
    totals = {}
    for t in innings_totals or []:
        try:
            totals[int(t.get("innings_number"))] = t
        except (TypeError, ValueError):
            pass
    club_inn = {r["innings_number"]: r for r in await _all(db, _CLUB_INN, mid=mid)}
    runs_ca, runs_club = defaultdict(set), defaultdict(set)
    for r in ca_ours:
        runs_ca[r["innings_number"]].add((r["pid"], r["runs"]))
    for r in club_bat:
        runs_club[r["innings_number"]].add((r["pid"], r["runs"]))
    fow, part = [], []
    for kind, src, out in (("fow", ca_fow, fow), ("part", ca_part, part)):
        for n, rows in _grouped(src, "innings_number").items():
            tgt = inn_map.get(n)
            if tgt is None or has.get((kind, tgt)):
                continue
            what = "Fall of wickets" if kind == "fow" else "Partnerships"
            if n in ours_ca:
                if runs_ca[n] != runs_club[tgt]:
                    left_out.append(f"{what} for our innings {ours_ca.index(n) + 1}: they depend on "
                                    f"batters' runs that differ between the two cards")
                    continue
            else:
                t, row = totals.get(n), club_inn.get(tgt)
                if t and row and row.get("total_runs") is not None and t.get("runs_scored") is not None \
                        and row["total_runs"] != t["runs_scored"]:
                    left_out.append(f"{what} for the opposition innings: the opposition total differs "
                                    f"({t['runs_scored']} against {row['total_runs']})")
                    continue
            out += [{**r, "target": tgt} for r in rows]
    if fow:
        brought.append(f"Fall of wickets ({len(fow)} wickets)")
    if part:
        brought.append(f"Partnerships ({len(part)})")

    # --- the opposition card and the text on each dismissal --------------------------------------
    card = await _ca_card(db, gid)
    our_dismissals = []
    if card:
        for r in card.get("batting") or []:
            n, pid = r.get("innings_number"), str(r.get("player_id") or "")
            txt = (r.get("dismissal_type") or "").strip()
            if not pid or n not in inn_map or not txt or txt.lower() in _BARE:
                continue
            if (pid, ours_ca.index(n) if n in ours_ca else -1) not in agree_runs:
                continue
            our_dismissals.append({"innings_number": inn_map[n], "player_id": pid, "text": txt})
    if our_dismissals:
        brought.append(f"Bowler and fielder named on {len(our_dismissals)} of our dismissals")

    opp_batting, opp_bowling, opp_totals = [], [], {}
    if card:
        card_totals = card.get("innings_totals") or {}
        for key in sorted(card_totals, key=lambda k: int(k)):
            n = int(key)
            tgt = inn_map.get(n)
            t = card_totals[key] or {}
            if tgt is None or n in ours_ca:
                continue
            row = club_inn.get(tgt)
            full = (t.get("runs") or 0) + (t.get("extras") or 0) if t.get("runs") is not None else None
            if row and full is not None and row.get("total_runs") is not None and row["total_runs"] != full:
                left_out.append("The opposition's card: the opposition total differs between the two "
                                f"cards ({full} against {row['total_runs']})")
                opp_totals = {}
                opp_batting = []
                break
            opp_totals[str(tgt)] = {k: t.get(k) for k in ("runs", "wickets", "extras", "overs",
                                                             "batting_team", "extras_breakdown")
                                    if t.get(k) is not None}
        else:
            for r in card.get("opp_batting") or []:
                tgt = inn_map.get(r.get("innings_number"))
                if tgt is not None:
                    opp_batting.append({**r, "innings_number": tgt})
        for r in card.get("opp_bowling") or []:
            tgt = inn_map.get(r.get("innings_number"))
            if tgt is not None:
                opp_bowling.append({**r, "innings_number": tgt})
        if opp_batting:
            brought.append("The opposition's batting card")
        if opp_bowling:
            brought.append("The opposition's bowling card")
        if not opp_batting and not opp_bowling and not our_dismissals:
            left_out.append("Cricket Australia's scorecard held no opposition card or dismissal names for this match")
    else:
        left_out.append("Cricket Australia could not be reached just now, so the opposition's card and "
                        "the bowler and fielder names on dismissals were not copied. Refresh the detail "
                        "later to add them.")

    detail = {"version": 1, "from_game_id": gid, "our_dismissals": our_dismissals,
              "opp_batting": opp_batting, "opp_bowling": opp_bowling,
              "innings_totals": opp_totals} if (our_dismissals or opp_batting or opp_bowling) else None
    return {"ok": True, "reason": None, "balls": balls, "credits": credits, "fow": fow, "part": part,
            "detail": detail, "brought": brought, "left_out": left_out,
            "counts": {"balls": len(balls), "credits": len(credits), "fow": len(fow),
                       "part": len(part), "our_dismissals": len(our_dismissals),
                       "opposition_batters": len(opp_batting), "opposition_bowlers": len(opp_bowling)}}


async def apply_plan(db, org_id, mid, plan: dict) -> dict:
    """Write a plan inside the caller's transaction and return exactly what it wrote."""
    mid = str(mid)
    ids: dict = {"balls": [], "bw": [], "fow": [], "part": [], "detail": False}
    if not plan.get("ok"):
        return ids
    for row_id, value in plan["balls"]:
        res = await db.execute(text(
            "UPDATE manual_batting_innings SET balls = :b WHERE id = :i AND balls IS NULL"),
            {"b": value, "i": row_id})
        if res.rowcount:
            ids["balls"].append([row_id, value])
    if plan["fow"]:
        ids["fow"] = list((await db.execute(
            insert(ManualFallOfWicket).returning(ManualFallOfWicket.id),
            [dict(manual_game_id=_uuid(mid), innings_number=r["target"],
                  wicket_number=r["wicket_number"], score_at_fall=r["score_at_fall"],
                  overs_at_fall=r["overs_at_fall"], player_id=r["player_id"],
                  batter_name=r["batter_name"]) for r in plan["fow"]])).scalars())
    if plan["part"]:
        ids["part"] = list((await db.execute(
            insert(ManualPartnership).returning(ManualPartnership.id),
            [dict(manual_game_id=_uuid(mid), innings_number=r["target"],
                  wicket_number=r["wicket_number"], batter1_id=r["batter1_id"],
                  batter2_id=r["batter2_id"], runs=r["runs"], balls=r["balls"],
                  batter1_runs=r["batter1_runs"], batter2_runs=r["batter2_runs"],
                  is_club_innings=r["is_club_innings"], batter1_name=r["batter1_name"],
                  batter2_name=r["batter2_name"]) for r in plan["part"]])).scalars())
    if plan["credits"]:
        ids["bw"] = list((await db.execute(
            insert(ManualBowlerWicket).returning(ManualBowlerWicket.id),
            [dict(manual_game_id=_uuid(mid), innings_number=r["target"],
                  bowler_id=_uuid(r["bowler_id"]), fielder_id=_uuid(r["fielder_id"]),
                  batter_name=r["batter_name"], batter_position=r["batter_position"],
                  batter_runs=r["batter_runs"], batter_balls=None,
                  dismissal_type=r["dismissal_type"], caught_behind=r["caught_behind"])
             for r in plan["credits"]])).scalars())
    if plan["detail"]:
        import json
        await db.execute(text("UPDATE manual_games SET review_detail = CAST(:d AS JSONB) "
                              "WHERE id = CAST(:m AS UUID)"),
                         {"d": json.dumps(plan["detail"], default=str), "m": mid})
        ids["detail"] = True
    return ids


async def revert_detail(db, mid, ids: dict) -> dict:
    """Remove exactly what `apply_plan` wrote. A balls figure a person has since corrected is
    theirs, so it is only cleared where it still holds the figure that was copied."""
    out = {"balls": 0, "bw": 0, "fow": 0, "part": 0, "detail": False}
    for row_id, value in ids.get("balls") or []:
        res = await db.execute(text(
            "UPDATE manual_batting_innings SET balls = NULL WHERE id = :i AND balls = :b"),
            {"i": row_id, "b": value})
        out["balls"] += res.rowcount or 0
    for key, model in (("fow", ManualFallOfWicket), ("part", ManualPartnership), ("bw", ManualBowlerWicket)):
        if ids.get(key):
            out[key] = (await db.execute(sa_delete(model).where(
                model.id.in_(ids[key]), model.manual_game_id == _uuid(mid)))).rowcount or 0
    if ids.get("detail"):
        await db.execute(text("UPDATE manual_games SET review_detail = NULL WHERE id = CAST(:m AS UUID)"),
                         {"m": str(mid)})
        out["detail"] = True
    return out
