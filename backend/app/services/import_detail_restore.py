"""Copy the match detail an override hid back onto the import that replaced it.

An overwrite import keeps only what the club's file carried. A scorebook (CSFW) names
nobody on a dismissal, has no partnerships and few falls of wickets, so every replaced
match lost what PlayHQ held. The synced rows are still in `games` and the manual side has
tables that mirror them column for column (`manual_bowler_wickets`,
`manual_fall_of_wickets`, `manual_partnerships`), so this reads them back. Balls faced is
`import_balls_enrich`'s job, and the opposition's cards are not touched here.

WHAT IT WILL NOT DO. It fills; it never overwrites and never deletes the club's rows.

* A match is only used when its scorecard confirms the pair: enough of the import's
  batters (same player, same runs) are on the synced card. A pair the date and the
  opposition made, with no scorecard behind it, is skipped and listed.
* Innings are lined up by order, not by number. The import numbers our innings 1, 3, 5
  and theirs 2, 4, 6; PlayHQ numbers by who batted first. Our first batting innings is the
  import's first, and so on; if the counts differ the match is skipped.
* Fall of wickets and partnerships are copied for an innings only where the import has
  none for it.
* Who took each wicket is copied for a whole match or not at all, and only when every one
  of our bowlers' wickets on the card equals the number PlayHQ credits to him. That is
  the guard against putting a name on the wrong wicket: the new rows can never disagree
  with the club's own bowling figures. The import must have no credits for the match yet.

Each run writes the ids of the rows it inserted to the audit log, and `undo_org` removes
exactly those and nothing else.
"""
from __future__ import annotations

import json
import math
import uuid
from collections import defaultdict
from typing import Optional

from sqlalchemy import insert, text

from app.models.db import (
    ManualBowlerWicket, ManualFallOfWicket, ManualPartnership,
)

SKIP_PAIR = "the scorecard does not confirm the pair"
SKIP_INNINGS = "our innings do not line up between the two cards"
SKIP_CREDITS = "wickets credited to our bowlers differ from the bowling figures"
SKIP_OPP = "the opposition innings cannot be lined up"

_PAIRED = """
    WITH imported AS (
        SELECT DISTINCT (jsonb_array_elements_text(l.after_json->'created_game_ids'))::uuid AS id
          FROM manual_edit_logs l
         WHERE l.organisation_id = :org
           AND l.action = 'import'
           AND l.target_table = 'manual_games'
           AND l.undone_at IS NULL
    )
    SELECT mg.id::text AS id, mg.superseded_by_game_id::text AS game_id, s.name AS season_name
      FROM manual_games mg
      JOIN imported i ON i.id = mg.id
      JOIN seasons s ON s.id = mg.season_id
     WHERE mg.organisation_id = CAST(:org AS UUID)
       AND mg.superseded_by_game_id IS NOT NULL
       AND mg.cricketstatz_import_id IS NULL
"""

_MAN_BAT = """
    SELECT manual_game_id::text AS mid, player_id::text AS pid, runs, innings_number
      FROM manual_batting_innings
     WHERE manual_game_id = ANY(CAST(:ids AS UUID[]))
       AND NOT COALESCE(did_not_bat, FALSE) AND runs IS NOT NULL
"""
_SYN_BAT = """
    SELECT bi.game_id::text AS gid, bi.player_id::text AS pid, bi.runs, bi.innings_number
      FROM batting_innings bi
      JOIN players p ON p.id = bi.player_id AND p.organisation_id = CAST(:org AS UUID)
     WHERE bi.game_id = ANY(CAST(:ids AS UUID[]))
       AND NOT COALESCE(bi.did_not_bat, FALSE) AND bi.runs IS NOT NULL
"""
_SYN_FOW = """
    SELECT game_id::text AS gid, innings_number, wicket_number, score_at_fall, overs_at_fall,
           player_id, batter_name
      FROM fall_of_wickets WHERE game_id = ANY(CAST(:ids AS UUID[]))
"""
_SYN_PART = """
    SELECT game_id::text AS gid, innings_number, wicket_number, batter1_id, batter2_id, runs,
           balls, batter1_runs, batter2_runs, is_club_innings, batter1_name, batter2_name
      FROM partnerships WHERE game_id = ANY(CAST(:ids AS UUID[]))
"""
# Our bowlers only: a fixture between two synced clubs carries both clubs' credits.
_SYN_BW = """
    SELECT bw.game_id::text AS gid, bw.innings_number, bw.bowler_id, bw.fielder_id,
           bw.batter_name, bw.batter_position, bw.batter_runs, bw.batter_balls,
           bw.dismissal_type, bw.caught_behind
      FROM bowler_wickets bw
      JOIN players pb ON pb.id = bw.bowler_id AND pb.organisation_id = CAST(:org AS UUID)
     WHERE bw.game_id = ANY(CAST(:ids AS UUID[]))
"""
_MAN_HAS = """
    SELECT manual_game_id::text AS mid, innings_number, 'fow' AS kind, count(*) AS n
      FROM manual_fall_of_wickets WHERE manual_game_id = ANY(CAST(:ids AS UUID[]))
     GROUP BY 1, 2
    UNION ALL
    SELECT manual_game_id::text, innings_number, 'part', count(*)
      FROM manual_partnerships WHERE manual_game_id = ANY(CAST(:ids AS UUID[]))
     GROUP BY 1, 2
    UNION ALL
    SELECT manual_game_id::text, 0, 'bw', count(*)
      FROM manual_bowler_wickets WHERE manual_game_id = ANY(CAST(:ids AS UUID[]))
     GROUP BY 1
"""
_MAN_SPELLS = """
    SELECT manual_game_id::text AS mid, player_id::text AS pid, COALESCE(SUM(wickets), 0) AS w
      FROM manual_bowling_spells WHERE manual_game_id = ANY(CAST(:ids AS UUID[]))
     GROUP BY 1, 2
"""

_NO_CREDIT = ("run out", "retired", "retired out", "obstructing the field", "timed out",
              "handled the ball", "hit the ball twice", "absent")


def _grouped(rows, key):
    out = defaultdict(list)
    for r in rows:
        out[r[key]].append(r)
    return out


def _uuid(v):
    return v if v is None or isinstance(v, uuid.UUID) else uuid.UUID(str(v))


async def _all(db, sql, **params):
    return [dict(r) for r in (await db.execute(text(sql), params)).mappings().all()]


async def plan_org(db, org_id) -> dict:
    org = str(org_id)
    paired = await _all(db, _PAIRED, org=org)
    if not paired:
        return {"paired": 0, "fow": [], "part": [], "bw": [], "skipped": defaultdict(list),
                "matches": 0, "by_season": {}, "credit_gaps": []}
    mids = [p["id"] for p in paired]
    gids = sorted({p["game_id"] for p in paired})
    man_bat = _grouped(await _all(db, _MAN_BAT, ids=mids), "mid")
    syn_bat = _grouped(await _all(db, _SYN_BAT, org=org, ids=gids), "gid")
    syn_fow = _grouped(await _all(db, _SYN_FOW, ids=gids), "gid")
    syn_part = _grouped(await _all(db, _SYN_PART, ids=gids), "gid")
    syn_bw = _grouped(await _all(db, _SYN_BW, org=org, ids=gids), "gid")
    has = {(r["mid"], r["innings_number"], r["kind"]): r["n"]
           for r in await _all(db, _MAN_HAS, ids=mids)}
    spells = defaultdict(dict)
    for r in await _all(db, _MAN_SPELLS, ids=mids):
        spells[r["mid"]][r["pid"]] = int(r["w"])

    fow_rows, part_rows, bw_rows = [], [], []
    skipped: dict = defaultdict(list)
    credit_gaps: list = []
    touched, by_season = set(), defaultdict(set)

    for p in paired:
        mid, gid = p["id"], p["game_id"]
        mb, sb = man_bat.get(mid, []), syn_bat.get(gid, [])
        card_m = {(r["pid"], r["runs"]) for r in mb}
        card_s = {(r["pid"], r["runs"]) for r in sb}
        need = max(2, math.ceil(0.6 * min(len(card_m), len(card_s)))) if card_m and card_s else 99
        if len(card_m & card_s) < need:
            skipped[SKIP_PAIR].append(mid)
            continue
        ours_man = sorted({r["innings_number"] for r in mb})
        ours_syn = sorted({r["innings_number"] for r in sb})
        if not ours_man or len(ours_man) != len(ours_syn):
            skipped[SKIP_INNINGS].append(mid)
            continue
        inn_map = dict(zip(ours_syn, ours_man))
        seen = ({r["innings_number"] for r in syn_fow.get(gid, [])}
                | {r["innings_number"] for r in syn_part.get(gid, [])}
                | {r["innings_number"] for r in syn_bw.get(gid, [])})
        opp_syn = sorted(seen - set(ours_syn))
        for k, n in enumerate(opp_syn):
            if k < len(ours_man):
                inn_map[n] = ours_man[k] + 1
        wrote = False

        for kind, src, out in (("fow", syn_fow, fow_rows), ("part", syn_part, part_rows)):
            for syn_inn, rows in _grouped(src.get(gid, []), "innings_number").items():
                target = inn_map.get(syn_inn)
                if target is None or has.get((mid, target, kind)):
                    continue
                for r in rows:
                    out.append({**r, "mid": mid, "target": target})
                wrote = True

        credits = [r for r in syn_bw.get(gid, [])
                   if (r["dismissal_type"] or "").lower() not in _NO_CREDIT]
        if credits and not has.get((mid, 0, "bw")):
            per_bowler = defaultdict(int)
            for r in credits:
                per_bowler[str(r["bowler_id"])] += 1
            ours = {k: v for k, v in spells.get(mid, {}).items() if v > 0}
            if per_bowler != ours:
                skipped[SKIP_CREDITS].append(mid)
                credit_gaps.append({"mid": mid, "synced": dict(per_bowler), "import": ours})
            elif any(r["innings_number"] not in inn_map for r in credits):
                skipped[SKIP_OPP].append(mid)
            else:
                for r in credits:
                    bw_rows.append({**r, "mid": mid, "target": inn_map[r["innings_number"]]})
                wrote = True
        if wrote:
            touched.add(mid)
            by_season[p["season_name"]].add(mid)

    return {"paired": len(paired), "fow": fow_rows, "part": part_rows, "bw": bw_rows,
            "skipped": skipped, "matches": len(touched), "credit_gaps": credit_gaps,
            "by_season": {k: len(v) for k, v in sorted(by_season.items())}}


GAP_COUNT = "the same bowlers, but a different number of wickets"
GAP_TWO_RECORDS = "one man under two records (the bowler is not joined yet)"
GAP_MISSING = "a credited bowler has no wickets on the import's card"
GAP_EXTRA = "the import credits a bowler PlayHQ does not"
GAP_OTHER = "bowlers differ in more than one way"


def classify_gap(gap: dict, label_of) -> str:
    """Why one match's wicket credits differ from its bowling figures.

    ``label_of(player id)`` gives (surname, first initial) or None. A credited bowler and
    an import bowler with the same label and no match of their own are one man held
    twice, which `link_import_players` has not been able to prove."""
    syn, imp = gap["synced"], gap["import"]
    only_syn = [b for b in syn if b not in imp]
    only_imp = [b for b in imp if b not in syn]
    if not only_syn and not only_imp:
        return GAP_COUNT
    if only_syn and only_imp:
        left = list(only_imp)
        for b in only_syn:
            hit = next((i for i in left if label_of(b) and label_of(b) == label_of(i)), None)
            if hit is None:
                return GAP_OTHER
            left.remove(hit)
        return GAP_TWO_RECORDS if not left else GAP_OTHER
    return GAP_MISSING if only_syn else GAP_EXTRA


def gap_pairs(gap: dict, label_of) -> list:
    """The (import record, synced record) pairs a match's wicket credits prove, or [].

    Only when the two cards differ ONLY by bowlers that pair off one-to-one on surname and
    initial with the same count, so everything else on the card has agreed exactly."""
    syn, imp = gap["synced"], gap["import"]
    only_syn = [b for b in syn if b not in imp]
    only_imp = [b for b in imp if b not in syn]
    if not only_syn or len(only_syn) != len(only_imp):
        return []
    if any(syn[b] != imp[b] for b in syn if b in imp):
        return []
    left, pairs = list(only_imp), []
    for b in only_syn:
        hit = next((i for i in left if label_of(b) and label_of(b) == label_of(i)
                    and imp[i] == syn[b]), None)
        if hit is None:
            return []
        left.remove(hit)
        pairs.append((hit, b))
    return pairs


async def credit_evidence(db, org_id) -> list:
    """Join evidence for `link_import_players` from the matches whose credits are off by a
    bowler held under two records: ``[{x_id, y_id, matches}]``."""
    from collections import Counter

    from app.services.import_player_link import label

    plan = await plan_org(db, org_id)
    gaps = plan.get("credit_gaps", [])
    ids = {b for g in gaps for k in ("synced", "import") for b in g[k]}
    if not ids:
        return []
    names = {r[0]: r[1] for r in (await db.execute(text(
        "SELECT id::text, COALESCE(NULLIF(display_name_override, ''), name) FROM players "
        "WHERE id = ANY(CAST(:ids AS UUID[]))"), {"ids": sorted(ids)})).all()}
    tally = Counter()
    for g in gaps:
        for x, y in gap_pairs(g, lambda pid: label(names.get(pid))):
            tally[(x, y)] += 1
    return [{"x_id": x, "y_id": y, "matches": n} for (x, y), n in tally.items()]


async def explain_credits(db, org_id, gaps: list) -> dict:
    """Group the credits mismatches by cause, with a few named examples of each."""
    from app.services.import_player_link import label

    ids = {b for g in gaps for k in ("synced", "import") for b in g[k]}
    names = {}
    if ids:
        names = {r[0]: r[1] for r in (await db.execute(text(
            "SELECT id::text, COALESCE(NULLIF(display_name_override, ''), name) FROM players "
            "WHERE id = ANY(CAST(:ids AS UUID[]))"), {"ids": sorted(ids)})).all()}

    def label_of(pid):
        return label(names.get(pid))

    groups: dict = defaultdict(list)
    for g in gaps:
        groups[classify_gap(g, label_of)].append(g)

    def show(g):
        a = ", ".join(sorted(f"{names.get(b, b[:8])} {n}" for b, n in g["synced"].items()))
        b = ", ".join(sorted(f"{names.get(x, x[:8])} {n}" for x, n in g["import"].items()))
        return f"PlayHQ credits [{a}]  import card [{b}]  ({g['mid'][:8]})"

    return {k: {"count": len(v), "examples": [show(g) for g in v[:5]]}
            for k, v in sorted(groups.items(), key=lambda kv: -len(kv[1]))}


async def restore_org(db, org_id, *, apply: bool = False,
                      limit_matches: Optional[int] = None) -> dict:
    """The plan for one club and, with ``apply``, write it in one transaction.

    ``limit_matches`` keeps only the first N matches that would gain detail, in a fixed
    order, so a first run can be small enough to check by eye before the rest."""
    plan = await plan_org(db, org_id)
    if limit_matches:
        order = sorted({r["mid"] for k in ("fow", "part", "bw") for r in plan[k]})
        keep = set(order[:limit_matches])
        for k in ("fow", "part", "bw"):
            plan[k] = [r for r in plan[k] if r["mid"] in keep]
        plan["matches"] = len(keep)
        plan["by_season"] = {}
    res = {**plan, "written": {"fow": 0, "part": 0, "bw": 0}}
    if not apply or not (plan["fow"] or plan["part"] or plan["bw"]):
        return res
    ids: dict = {"fow": [], "part": [], "bw": []}
    if plan["fow"]:
        ids["fow"] = list((await db.execute(
            insert(ManualFallOfWicket).returning(ManualFallOfWicket.id),
            [dict(manual_game_id=_uuid(r["mid"]), innings_number=r["target"],
                  wicket_number=r["wicket_number"], score_at_fall=r["score_at_fall"],
                  overs_at_fall=r["overs_at_fall"], player_id=r["player_id"],
                  batter_name=r["batter_name"]) for r in plan["fow"]])).scalars())
    if plan["part"]:
        ids["part"] = list((await db.execute(
            insert(ManualPartnership).returning(ManualPartnership.id),
            [dict(manual_game_id=_uuid(r["mid"]), innings_number=r["target"],
                  wicket_number=r["wicket_number"], batter1_id=r["batter1_id"],
                  batter2_id=r["batter2_id"], runs=r["runs"], balls=r["balls"],
                  batter1_runs=r["batter1_runs"], batter2_runs=r["batter2_runs"],
                  is_club_innings=r["is_club_innings"], batter1_name=r["batter1_name"],
                  batter2_name=r["batter2_name"]) for r in plan["part"]])).scalars())
    if plan["bw"]:
        ids["bw"] = list((await db.execute(
            insert(ManualBowlerWicket).returning(ManualBowlerWicket.id),
            [dict(manual_game_id=_uuid(r["mid"]), innings_number=r["target"],
                  bowler_id=r["bowler_id"], fielder_id=r["fielder_id"],
                  batter_name=r["batter_name"], batter_position=r["batter_position"],
                  batter_runs=r["batter_runs"], batter_balls=r["batter_balls"],
                  dismissal_type=r["dismissal_type"], caught_behind=r["caught_behind"])
             for r in plan["bw"]])).scalars())
    # In the same transaction as the rows, and not through `log_activity` (which swallows
    # a failure): a restore with no audit entry could not be undone.
    audit_id = (await db.execute(text(
        "INSERT INTO audit_logs (org_id, action, target_type, target_id, details) "
        "VALUES (:org, 'restore_import_detail', 'manual_games', :tid, CAST(:d AS JSONB)) "
        "RETURNING id"),
        {"org": str(org_id), "tid": (plan["fow"] or plan["part"] or plan["bw"])[0]["mid"],
         "d": json.dumps({"why": "Fall of wickets, partnerships and who took each wicket "
                                 "copied from the synced card an override replaced.",
                          "ids": ids})})).scalar()
    await db.commit()
    res["written"] = {k: len(v) for k, v in ids.items()}
    res["audit_id"] = audit_id
    return res


async def undo_org(db, org_id, *, audit_id: int) -> dict:
    """Remove exactly the rows a run inserted, from its audit entry."""
    row = (await db.execute(text(
        "SELECT details FROM audit_logs WHERE id = :i AND org_id = CAST(:o AS UUID) "
        "AND action = 'restore_import_detail'"), {"i": audit_id, "o": str(org_id)})).first()
    removed = {"fow": 0, "part": 0, "bw": 0}
    if not row:
        return removed
    from sqlalchemy import delete as sa_delete

    ids = (row[0] or {}).get("ids", {})
    for kind, model in (("fow", ManualFallOfWicket), ("part", ManualPartnership),
                        ("bw", ManualBowlerWicket)):
        if ids.get(kind):
            removed[kind] = (await db.execute(
                sa_delete(model).where(model.id.in_(ids[kind])))).rowcount
    await db.commit()
    return removed
