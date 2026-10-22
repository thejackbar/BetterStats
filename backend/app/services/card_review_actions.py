"""Card review, write side: choose which stored version of a match the site shows, and undo it.

Every change to a match is one row in ``card_review_log`` holding the state it replaced and the
ids of anything a ``hybrid`` copy wrote, so one match can be put back exactly as it was and no
other match is touched. Nothing here deletes a club's own rows: undo removes only rows this
module inserted, and a balls figure only where it still holds the figure that was copied.

A choice also sets ``pairing_locked``. `match_pairing.reconcile_org` never touches a locked
pair, so a later sync cannot flip a person's choice back.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import text

from app.services import card_review as cr
from app.services import card_review_doubles as dbl
from app.services import link_audit as la
from app.services import card_review_hybrid as hy

_STATE_COLS = ("pair_prefers_import", "pairing_locked", "review_choice", "review_source",
               "review_decided_by", "review_decided_at", "review_note", "review_pair_ok",
               "superseded_by_game_id")

_ROW = """
    SELECT id::text AS mid, organisation_id::text AS org_id, superseded_by_game_id::text AS gid,
           pair_prefers_import, pairing_locked, review_choice, review_source,
           review_decided_by::text AS review_decided_by, review_decided_at, review_note,
           review_pair_ok
      FROM manual_games WHERE id = CAST(:mid AS UUID) AND organisation_id = CAST(:org AS UUID)
     FOR UPDATE
"""


class ReviewError(ValueError):
    """A request the data cannot honour, in words a person can read."""


def _snapshot(row: dict) -> dict:
    snap = {}
    for k in _STATE_COLS:
        v = row.get("gid") if k == "superseded_by_game_id" else row.get(k)
        snap[k] = v.isoformat() if isinstance(v, datetime) else v
    return snap


async def _row(db, org_id, mid) -> dict:
    res = (await db.execute(text(_ROW), {"mid": str(mid), "org": str(org_id)})).mappings().first()
    if not res:
        raise ReviewError("That match was not found for this club.")
    return dict(res)


async def _log(db, org_id, mid, *, action, from_choice, to_choice, source, user_id, note,
               batch_id, before, detail) -> int:
    return (await db.execute(text("""
        INSERT INTO card_review_log (org_id, manual_game_id, action, from_choice, to_choice, source,
                                     user_id, note, batch_id, before_state, detail)
        VALUES (CAST(:org AS UUID), CAST(:mid AS UUID), :action, :f, :t, :src,
                CAST(:uid AS UUID), :note, CAST(:batch AS UUID), CAST(:before AS JSONB),
                CAST(:detail AS JSONB))
        RETURNING id"""), {
        "org": str(org_id), "mid": str(mid), "action": action, "f": from_choice, "t": to_choice,
        "src": source, "uid": str(user_id) if user_id else None, "note": note,
        "batch": str(batch_id) if batch_id else None,
        "before": json.dumps(before, default=str), "detail": json.dumps(detail or {}, default=str),
    })).scalar()


async def _revert_inserted(db, mid) -> dict:
    """Take back everything a hybrid copy of this match wrote, newest entry first."""
    total = {"balls": 0, "bw": 0, "fow": 0, "part": 0}
    rows = (await db.execute(text("""
        SELECT id, detail FROM card_review_log
         WHERE manual_game_id = CAST(:mid AS UUID) AND detail ? 'inserted'
           AND COALESCE((detail->>'reverted')::boolean, FALSE) = FALSE
         ORDER BY id DESC"""), {"mid": str(mid)})).all()
    for log_id, detail in rows:
        ids = (detail or {}).get("inserted") or {}
        res = await hy.revert_detail(db, mid, ids)
        for k in total:
            total[k] += res.get(k, 0)
        await db.execute(text("UPDATE card_review_log SET detail = detail || '{\"reverted\": true}'::jsonb "
                              "WHERE id = :i"), {"i": log_id})
    return total


async def _players_of(db, mid, org_id) -> list:
    rows = (await db.execute(text("""
        SELECT player_id FROM manual_batting_innings WHERE manual_game_id = CAST(:m AS UUID)
        UNION SELECT player_id FROM manual_bowling_spells WHERE manual_game_id = CAST(:m AS UUID)
        UNION SELECT bi.player_id FROM batting_innings bi
          JOIN manual_games mg ON mg.superseded_by_game_id = bi.game_id
          JOIN players p ON p.id = bi.player_id AND p.organisation_id = CAST(:o AS UUID)
         WHERE mg.id = CAST(:m AS UUID)"""), {"m": str(mid), "o": str(org_id)})).all()
    return [r[0] for r in rows]


async def recompute(db, org_id, player_ids) -> None:
    """A switch changes which card a player's career is counted from, so the milestone check
    the sync and the manual-entry routes run is run here too (reconciling, so a figure that
    drops back under a threshold takes its stored milestone with it)."""
    from app.services.sync import _compute_milestones

    ids = sorted({p for p in player_ids if p}, key=str)
    for i in range(0, len(ids), 300):
        await _compute_milestones(db, ids[i:i + 300], org_id, reconcile=True)


async def set_choice(db, org_id, mid, choice: str, user_id, *, note: Optional[str] = None,
                     source: str = "hand", batch_id=None, commit: bool = True,
                     do_recompute: bool = True) -> dict:
    if choice not in cr.CHOICES:
        raise ReviewError("Choose Cricket Australia, the club scorecard, or the club scorecard "
                          "with Cricket Australia detail.")
    row = await _row(db, org_id, mid)
    if not row["gid"]:
        raise ReviewError("This match is not linked to a Cricket Australia card, so there is nothing to choose between.")
    current = cr.current_choice({"review_choice": row["review_choice"],
                                 "pair_prefers_import": row["pair_prefers_import"]})
    before = _snapshot(row)
    if current == "hybrid":
        await _revert_inserted(db, mid)
    inserted, brought, left_out = None, [], []
    if choice == "hybrid":
        plan = await hy.plan_hybrid(db, org_id, mid)
        if not plan["ok"]:
            raise ReviewError(plan["reason"])
        inserted = await hy.apply_plan(db, org_id, mid, plan)
        brought, left_out = plan["brought"], plan["left_out"]
    await db.execute(text("""
        UPDATE manual_games SET pair_prefers_import = :pref, pairing_locked = TRUE,
               review_choice = :c, review_source = :src, review_decided_by = CAST(:uid AS UUID),
               review_decided_at = NOW(), review_note = :note, updated_at = NOW()
         WHERE id = CAST(:mid AS UUID)"""), {
        "pref": choice != "ca", "c": choice, "src": source,
        "uid": str(user_id) if user_id else None, "note": note, "mid": str(mid)})
    log_id = await _log(db, org_id, mid, action="choice", from_choice=current, to_choice=choice,
                        source=source, user_id=user_id, note=note, batch_id=batch_id, before=before,
                        detail={"inserted": inserted, "brought": brought, "left_out": left_out}
                        if inserted else {})
    players = await _players_of(db, mid, org_id) if do_recompute else []
    if commit:
        await db.commit()
        if do_recompute:
            await recompute(db, org_id, players)
            await db.commit()
    return {"match_id": str(mid), "from": current, "to": choice, "log_id": log_id,
            "brought": brought, "left_out": left_out, "players": players}


async def undo_last(db, org_id, mid, user_id) -> dict:
    """Put the match back as it was before its most recent change."""
    row = await _row(db, org_id, mid)
    players_before = await _players_of(db, mid, org_id)
    entry = (await db.execute(text("""
        SELECT id, action, before_state, from_choice, to_choice, detail FROM card_review_log
         WHERE manual_game_id = CAST(:mid AS UUID) AND undone_at IS NULL
           AND action IN ('choice', 'pair_ok', 'relink', 'unlink', 'link')
         ORDER BY id DESC LIMIT 1"""), {"mid": str(mid)})).mappings().first()
    if not entry:
        raise ReviewError("There is nothing to undo for this match.")
    before = dict(entry["before_state"] or {})
    now_state = _snapshot(row)
    current = cr.current_choice({"review_choice": row["review_choice"],
                                 "pair_ok": None, "pair_prefers_import": row["pair_prefers_import"]})
    await _revert_inserted(db, mid)
    if before.get("superseded_by_game_id") != now_state.get("superseded_by_game_id"):
        taken = before.get("superseded_by_game_id") and (await db.execute(text(
            "SELECT 1 FROM manual_games WHERE superseded_by_game_id = CAST(:g AS UUID) "
            "AND id <> CAST(:m AS UUID)"), {"g": before["superseded_by_game_id"], "m": str(mid)})).first()
        if taken:
            raise ReviewError("Another match has been linked to that Cricket Australia card since, "
                              "so this link cannot be put back until that is changed.")
    decided_at = before.get("review_decided_at")
    if isinstance(decided_at, str):
        # asyncpg will not take an ISO string for a timestamp parameter
        decided_at = datetime.fromisoformat(decided_at)
    await db.execute(text("""
        UPDATE manual_games SET pair_prefers_import = :pref, pairing_locked = :lock,
               review_choice = :c, review_source = :src, review_decided_by = CAST(:by AS UUID),
               review_decided_at = :at, review_note = :note,
               review_pair_ok = :ok, superseded_by_game_id = CAST(:gid AS UUID), updated_at = NOW()
         WHERE id = CAST(:mid AS UUID)"""), {
        "pref": bool(before.get("pair_prefers_import")), "lock": bool(before.get("pairing_locked")),
        "c": before.get("review_choice"), "src": before.get("review_source"),
        "by": before.get("review_decided_by"), "at": decided_at,
        "note": before.get("review_note"), "ok": bool(before.get("review_pair_ok")),
        "gid": before.get("superseded_by_game_id"), "mid": str(mid)})
    restored = cr.current_choice({"review_choice": before.get("review_choice"),
                                  "pair_prefers_import": before.get("pair_prefers_import")})
    inserted, brought, left_out = None, [], []
    if before.get("review_choice") == "hybrid" and before.get("superseded_by_game_id"):
        plan = await hy.plan_hybrid(db, org_id, mid)
        if plan["ok"]:
            inserted = await hy.apply_plan(db, org_id, mid, plan)
            brought, left_out = plan["brought"], plan["left_out"]
    await db.execute(text("UPDATE card_review_log SET undone_at = NOW() WHERE id = :i"), {"i": entry["id"]})
    if entry["action"] == "unlink":
        # An unlink also wrote a "different matches" answer for the pair. Putting the link back
        # takes that answer with it, or the pair would be hidden from Possible doubles for good.
        await db.execute(text("""
            UPDATE card_review_log SET undone_at = NOW()
             WHERE manual_game_id = CAST(:m AS UUID) AND action = 'not_double' AND undone_at IS NULL
               AND detail->>'via' = 'unlink'"""), {"m": str(mid)})
    log_id = await _log(db, org_id, mid, action="undo", from_choice=current, to_choice=restored,
                        source="hand", user_id=user_id, note=None, batch_id=None, before=now_state,
                        detail={"undid": entry["id"], "inserted": inserted, "brought": brought,
                                "left_out": left_out} if inserted else {"undid": entry["id"]})
    players = list({*players_before, *await _players_of(db, mid, org_id)})
    await db.commit()
    await recompute(db, org_id, players)
    await db.commit()
    return {"match_id": str(mid), "from": current, "to": restored, "log_id": log_id}


async def refresh_detail(db, org_id, mid, user_id) -> dict:
    """Copy Cricket Australia's detail again, after Cricket Australia has changed its card."""
    row = await _row(db, org_id, mid)
    if cr.current_choice({"review_choice": row["review_choice"],
                          "pair_prefers_import": row["pair_prefers_import"]}) != "hybrid":
        raise ReviewError("Detail can only be refreshed on a match showing the club scorecard "
                          "with Cricket Australia detail.")
    before = _snapshot(row)
    await _revert_inserted(db, mid)
    plan = await hy.plan_hybrid(db, org_id, mid)
    if not plan["ok"]:
        raise ReviewError(plan["reason"])
    inserted = await hy.apply_plan(db, org_id, mid, plan)
    log_id = await _log(db, org_id, mid, action="refresh", from_choice="hybrid", to_choice="hybrid",
                        source="hand", user_id=user_id, note=None, batch_id=None, before=before,
                        detail={"inserted": inserted, "brought": plan["brought"],
                                "left_out": plan["left_out"]})
    await db.commit()
    return {"match_id": str(mid), "log_id": log_id, "brought": plan["brought"],
            "left_out": plan["left_out"]}


async def mark_pair_ok(db, org_id, mid, user_id, note: Optional[str] = None) -> dict:
    """A person says the two cards ARE the same match, so it joins the normal review."""
    row = await _row(db, org_id, mid)
    if not row["gid"]:
        raise ReviewError("This match is not linked to a Cricket Australia card.")
    before = _snapshot(row)
    await db.execute(text("UPDATE manual_games SET review_pair_ok = TRUE, pairing_locked = TRUE, "
                          "updated_at = NOW() WHERE id = CAST(:m AS UUID)"), {"m": str(mid)})
    log_id = await _log(db, org_id, mid, action="pair_ok", from_choice=None, to_choice=None,
                        source="hand", user_id=user_id, note=note, batch_id=None, before=before, detail={})
    await db.commit()
    return {"match_id": str(mid), "log_id": log_id}


async def relink(db, org_id, mid, game_id, user_id, *, batch_id=None, commit: bool = True) -> dict:
    """Link the club card to a different Cricket Australia game."""
    row = await _row(db, org_id, mid)
    gid = str(uuid.UUID(str(game_id)))
    ok = (await db.execute(text("""
        SELECT 1 FROM games g WHERE g.id = CAST(:g AS UUID)
           AND (g.home_org_id = CAST(:o AS UUID) OR g.away_org_id = CAST(:o AS UUID)
                OR EXISTS (SELECT 1 FROM grades gr JOIN seasons s ON s.id = gr.season_id
                            WHERE gr.id = g.grade_id AND s.organisation_id = CAST(:o AS UUID)))"""),
        {"g": gid, "o": str(org_id)})).first()
    if not ok:
        raise ReviewError("That Cricket Australia match is not one of this club's.")
    held = (await db.execute(text(
        "SELECT id::text FROM manual_games WHERE superseded_by_game_id = CAST(:g AS UUID) "
        "AND id <> CAST(:m AS UUID)"), {"g": gid, "m": str(mid)})).first()
    if held:
        raise ReviewError("Another club scorecard is already linked to that Cricket Australia match. "
                          "Re-link that one first, or swap the two.")
    before = _snapshot(row)
    before_players = await _players_of(db, mid, org_id)  # the card the link leaves counted its players too
    await _revert_inserted(db, mid)
    await db.execute(text("""
        UPDATE manual_games SET superseded_by_game_id = CAST(:g AS UUID), pairing_locked = TRUE,
               review_pair_ok = FALSE, review_detail = NULL,
               review_choice = CASE WHEN review_choice = 'hybrid' THEN 'club' ELSE review_choice END,
               updated_at = NOW() WHERE id = CAST(:m AS UUID)"""), {"g": gid, "m": str(mid)})
    log_id = await _log(db, org_id, mid, action="relink", from_choice=None, to_choice=None,
                        source="bulk" if batch_id else "hand", user_id=user_id, note=None, batch_id=batch_id,
                        before=before, detail={"to_game": gid, "from_game": row["gid"]})
    players = set(await _players_of(db, mid, org_id)) | set(before_players)
    if commit:
        await db.commit()
        await recompute(db, org_id, players)
        await db.commit()
    return {"match_id": str(mid), "game_id": gid, "log_id": log_id, "players": list(players)}


async def unlink(db, org_id, mid, user_id, *, quiet: bool = False, batch_id=None, commit: bool = True) -> dict:
    """Say these are two different matches: the club card stands alone.

    `quiet` is for a swap, where the card is unlinked only for an instant on its way to another
    game: it writes no "different matches" answer (the pair is not being declared different)."""
    row = await _row(db, org_id, mid)
    if not row["gid"]:
        raise ReviewError("This match is already not linked.")
    before = _snapshot(row)
    players = set(await _players_of(db, mid, org_id))
    await _revert_inserted(db, mid)
    await db.execute(text("""
        UPDATE manual_games SET superseded_by_game_id = NULL, review_choice = NULL,
               review_detail = NULL, review_pair_ok = FALSE, updated_at = NOW()
         WHERE id = CAST(:m AS UUID)"""), {"m": str(mid)})
    log_id = await _log(db, org_id, mid, action="unlink", from_choice=None, to_choice=None,
                        source="bulk" if batch_id else "hand", user_id=user_id, note=None, batch_id=batch_id,
                        before=before, detail={"swap": True, "from_game": row["gid"]} if quiet else {})
    if not quiet:
        # Saying these are two matches is also the answer to "possible doubles", so that step does
        # not offer the same pair straight back.
        await _log(db, org_id, mid, action="not_double", from_choice=None, to_choice=None, source="hand",
                   user_id=user_id, note=None, batch_id=None, before=before,
                   detail={"other_id": row["gid"], "other_kind": "ca", "via": "unlink"})
    if commit:
        await db.commit()
        await recompute(db, org_id, players)
        await db.commit()
    return {"match_id": str(mid), "log_id": log_id, "players": list(players)}


async def swap_links(db, org_id, mid_x, mid_y, game_y, user_id, *, batch_id=None, commit: bool = True) -> dict:
    """Two club cards each sit on the other's game: put each on its own.

    Card X moves to `game_y` (the game it matches, which card Y is on) and card Y moves to the game
    X was on. The unique index allows one card per game, so it is done in three logged steps in one
    transaction (unlink Y, move X, move Y), all in one batch: undone newest first, each step puts its
    card back to a game that is free by then. Refuses if the cards are no longer as the scan saw them."""
    x, y = await _row(db, org_id, mid_x), await _row(db, org_id, mid_y)
    game_y = str(uuid.UUID(str(game_y)))
    if not x["gid"] or y["gid"] != game_y or x["gid"] == game_y:
        raise ReviewError("These two cards are no longer linked as the scan saw them. Reload the list.")
    game_x = x["gid"]
    batch = batch_id or uuid.uuid4()
    res_y = await unlink(db, org_id, mid_y, user_id, quiet=True, batch_id=batch, commit=False)
    res_x = await relink(db, org_id, mid_x, game_y, user_id, batch_id=batch, commit=False)
    res_y2 = await relink(db, org_id, mid_y, game_x, user_id, batch_id=batch, commit=False)
    players = set(res_y["players"]) | set(res_x["players"]) | set(res_y2["players"])
    if commit:
        await db.commit()
        await recompute(db, org_id, players)
        await db.commit()
    return {"match_id": str(mid_x), "partner_id": str(mid_y), "batch_id": str(batch), "players": list(players)}


async def history(db, org_id, mid) -> list:
    rows = (await db.execute(text("""
        SELECT l.id, l.action, l.from_choice, l.to_choice, l.source, l.note, l.batch_id::text AS batch_id,
               l.created_at, l.undone_at, u.username,
               COALESCE((l.detail->>'reverted')::boolean, FALSE) AS reverted
          FROM card_review_log l LEFT JOIN users u ON u.id = l.user_id
         WHERE l.manual_game_id = CAST(:m AS UUID) AND l.org_id = CAST(:o AS UUID)
         ORDER BY l.id DESC"""), {"m": str(mid), "o": str(org_id)})).mappings().all()
    return [dict(r) for r in rows]


# --- the bulk switch for matches whose cards agree -----------------------------------------------

def bulk_candidates(rows: list) -> list:
    """Matches that agree on every figure, that nobody has chosen for by hand, that are not
    already showing Cricket Australia, and whose club card holds nothing Cricket Australia's lacks
    (a match where it does is for a person: switching would hide that detail from the site)."""
    return [r for r in rows if r["group"] == "agree" and not r["decided_by_hand"]
            and r["current"] != "ca" and not r["club_richer"]]


def bulk_preview(rows: list, *, sample: int = 10, seed: int = 7) -> dict:
    cand = bulk_candidates(rows)
    by_season: dict = {}
    for r in cand:
        by_season[r["season"] or "No season"] = by_season.get(r["season"] or "No season", 0) + 1
    rng = random.Random(seed)
    picked = rng.sample(cand, min(sample, len(cand)))
    held_back = sum(1 for r in rows if r["group"] == "agree" and not r["decided_by_hand"]
                    and r["current"] != "ca" and r["club_richer"])
    return {"matches": len(cand), "held_back": held_back,
            "by_season": [{"season": s, "matches": n} for s, n in
                          sorted(by_season.items(), key=lambda kv: (cr.season_sort_key(kv[0]), kv[0]))],
            "sample": [{"match_id": r["match_id"], "game_id": r["game_id"], "date": r["date"],
                        "grade": r["grade"], "opposition": r["opposition"]} for r in picked]}


async def bulk_apply(db, org_id, user_id, *, limit: Optional[int] = None, chunk: int = 200) -> dict:
    """Switch the agreeing matches to Cricket Australia, one logged change each."""
    rows = await cr.review_rows(db, org_id)
    cand = bulk_candidates(rows)
    cand.sort(key=lambda r: (cr.season_sort_key(r["season"]), str(r["date"])))
    if limit:
        cand = cand[:limit]
    batch = uuid.uuid4()
    done, players, skipped = 0, set(), []
    for i in range(0, len(cand), chunk):
        for r in cand[i:i + chunk]:
            try:
                res = await set_choice(db, org_id, r["match_id"], "ca", user_id, source="bulk",
                                       batch_id=batch, commit=False, do_recompute=False)
                players.update(await _players_of(db, r["match_id"], org_id))
                done += 1
            except ReviewError as e:
                skipped.append({"match_id": r["match_id"], "reason": str(e)})
        await db.commit()
    await recompute(db, org_id, players)
    # Written here and not through `log_activity`, which swallows a failure.
    await db.execute(text("""
        INSERT INTO audit_logs (org_id, action, target_type, target_id, details)
        VALUES (CAST(:o AS UUID), 'card_review_bulk', 'manual_games', :t, CAST(:d AS JSONB))"""), {
        "o": str(org_id), "t": str(batch),
        "d": json.dumps({"why": "Matches whose two cards agree now show the Cricket Australia card.",
                         "batch_id": str(batch), "matches": done, "skipped": len(skipped)})})
    await db.commit()
    return {"batch_id": str(batch), "switched": done, "skipped": skipped}


async def bulk_undo(db, org_id, user_id, batch_id) -> dict:
    """Put every match of a batch back, except one a person has changed since. NEWEST FIRST: a link
    made later in the batch may be holding the game an earlier one is returning to."""
    entries = (await db.execute(text("""
        SELECT l.id, l.manual_game_id::text AS mid FROM card_review_log l
         WHERE l.org_id = CAST(:o AS UUID) AND l.batch_id = CAST(:b AS UUID)
           AND l.undone_at IS NULL AND l.action IN ('choice', 'relink', 'link', 'unlink') ORDER BY l.id DESC"""),
        {"o": str(org_id), "b": str(batch_id)})).mappings().all()
    undone, changed = 0, []
    for e in entries:
        latest = (await db.execute(text("""
            SELECT id FROM card_review_log WHERE manual_game_id = CAST(:m AS UUID) AND undone_at IS NULL
               AND action IN ('choice', 'pair_ok', 'relink', 'unlink', 'link') ORDER BY id DESC LIMIT 1"""),
            {"m": e["mid"]})).scalar()
        if latest != e["id"]:
            changed.append(e["mid"])
            continue
        try:
            await undo_last(db, org_id, e["mid"], user_id)
            undone += 1
        except ReviewError:
            await db.rollback()
            changed.append(e["mid"])
    return {"batch_id": str(batch_id), "undone": undone, "left_alone": changed}


# --- possible doubles: two copies of one match that nothing links ----------------------------------

async def _club_game_ok(db, org_id, gid: str) -> bool:
    return bool((await db.execute(text("""
        SELECT 1 FROM games g WHERE g.id = CAST(:g AS UUID)
           AND (g.home_org_id = CAST(:o AS UUID) OR g.away_org_id = CAST(:o AS UUID)
                OR EXISTS (SELECT 1 FROM grades gr JOIN seasons s ON s.id = gr.season_id
                            WHERE gr.id = g.grade_id AND s.organisation_id = CAST(:o AS UUID)))"""),
        {"g": gid, "o": str(org_id)})).first())


async def link_double(db, org_id, mid, game_id, user_id, *, batch_id=None, commit: bool = True) -> dict:
    """A person says this club card and this Cricket Australia game are one match.

    The two are linked and locked, and the match joins the normal review (the person has said it
    is the same match, so it is not parked under "pairing looks wrong"). Which card the site shows
    follows the rule the automatic pairing keeps: Cricket Australia's, unless the club card holds
    batters and Cricket Australia's has none or does not agree with them, in which case the club's
    stays so nothing the club typed disappears before someone compares the two. Both cards stay
    stored; the choice is for the next steps to make.
    """
    row = await _row(db, org_id, mid)
    if row["gid"]:
        raise ReviewError("This club scorecard is already linked to a Cricket Australia card.")
    gid = str(uuid.UUID(str(game_id)))
    if not await _club_game_ok(db, org_id, gid):
        raise ReviewError("That Cricket Australia match is not one of this club's.")
    held = (await db.execute(text(
        "SELECT 1 FROM manual_games WHERE superseded_by_game_id = CAST(:g AS UUID)"), {"g": gid})).first()
    if held:
        raise ReviewError("Another club scorecard is already linked to that Cricket Australia match.")
    club_card = {(r["pid"], r["runs"]) for r in await cr._all(db, cr._CLUB_BAT, ids=[str(mid)])
                 if not r["dnb"] and r["runs"] is not None}
    ca_card = {(r["pid"], r["runs"]) for r in await cr._all(db, cr._CA_BAT, org=str(org_id), ids=[gid])
               if not r["dnb"] and r["runs"] is not None}
    prefer = bool(club_card) and not cr.confirms_pair(club_card, ca_card)
    before = _snapshot(row)
    players = set(await _players_of(db, mid, org_id))
    await db.execute(text("""
        UPDATE manual_games SET superseded_by_game_id = CAST(:g AS UUID), pair_prefers_import = :pref,
               pairing_locked = TRUE, review_pair_ok = TRUE, review_choice = NULL, updated_at = NOW()
         WHERE id = CAST(:m AS UUID)"""), {"g": gid, "pref": prefer, "m": str(mid)})
    log_id = await _log(db, org_id, mid, action="link", from_choice=None, to_choice="club" if prefer else "ca",
                        source="bulk" if batch_id else "hand", user_id=user_id, note=None, batch_id=batch_id,
                        before=before, detail={"to_game": gid, "shared": len(club_card & ca_card)})
    players.update(await _players_of(db, mid, org_id))
    if commit:
        await db.commit()
        await recompute(db, org_id, players)
        await db.commit()
    return {"match_id": str(mid), "game_id": gid, "log_id": log_id, "shows": "club" if prefer else "ca",
            "players": list(players)}


async def _other_ok(db, org_id, kind: str, mid, other: str) -> None:
    if kind in ("ca", "relink"):
        if not await _club_game_ok(db, org_id, other):
            raise ReviewError("That Cricket Australia match is not one of this club's.")
        return
    if not (await db.execute(text("SELECT 1 FROM manual_games WHERE id = CAST(:i AS UUID) "
                                  "AND organisation_id = CAST(:o AS UUID)"),
                             {"i": other, "o": str(org_id)})).first():
        raise ReviewError("That match was not found for this club.")


def _pair_rows(head: str, org_id, mid, other: str, kind: str) -> tuple:
    """`head` plus a WHERE naming the live "different matches" answers for one pair. Two club
    cards are one pair whichever of them the answer was written on."""
    where = """ WHERE org_id = CAST(:o AS UUID) AND action = 'not_double' AND undone_at IS NULL
                 AND ((manual_game_id = CAST(:m AS UUID) AND detail->>'other_id' = :x_t)"""
    params = {"o": str(org_id), "m": str(mid), "x_t": other}
    if kind == "club":
        where += " OR (manual_game_id = CAST(:x AS UUID) AND detail->>'other_id' = :m_t)"
        params.update({"x": other, "m_t": str(mid)})
    return head + where + ")", params


async def dismiss_double(db, org_id, mid, other_id, kind: str, user_id) -> dict:
    """These two are different matches. Recorded, undoable, and keyed on the pair."""
    if kind not in ("ca", "club", "relink"):
        raise ReviewError("Say whether the other copy is a Cricket Australia card or a club scorecard.")
    other = str(uuid.UUID(str(other_id)))
    row = await _row(db, org_id, mid)
    await _other_ok(db, org_id, kind, mid, other)
    if kind == "club" and other == str(mid):
        raise ReviewError("A match cannot be a double of itself.")
    sql, params = _pair_rows("SELECT id FROM card_review_log", org_id, mid, other, kind)
    mine = (await db.execute(text(sql + " LIMIT 1"), params)).first()
    if mine:
        return {"match_id": str(mid), "log_id": mine[0], "already": True}
    log_id = await _log(db, org_id, mid, action="not_double", from_choice=None, to_choice=None, source="hand",
                        user_id=user_id, note=None, batch_id=None, before=_snapshot(row),
                        detail={"other_id": other, "other_kind": kind})
    await db.commit()
    return {"match_id": str(mid), "log_id": log_id, "already": False}


async def restore_double(db, org_id, mid, other_id, kind: str, user_id) -> dict:
    """Take back a "different matches" answer, so the pair is offered again.

    An answer written by UNLINKING a pair is different: there the link itself was taken away, so
    putting the answer back means putting the link back (`undo_last`). That only makes sense while
    the unlink is still the newest change to the card; otherwise the person is told what to undo
    first, because undoing a newer change by accident is worse than doing nothing."""
    other = str(uuid.UUID(str(other_id)))
    await _row(db, org_id, mid)
    sql, params = _pair_rows("SELECT id, manual_game_id::text, detail FROM card_review_log", org_id, mid, other, kind)
    rows = (await db.execute(text(sql), params)).all()
    unlinked = [r for r in rows if (r[2] or {}).get("via") == "unlink"]
    if unlinked:
        owner = unlinked[0][1]
        newest = (await db.execute(text("""
            SELECT action FROM card_review_log WHERE manual_game_id = CAST(:m AS UUID) AND undone_at IS NULL
               AND action IN ('choice', 'pair_ok', 'relink', 'unlink', 'link') ORDER BY id DESC LIMIT 1"""),
            {"m": owner})).scalar()
        if newest != "unlink":
            raise ReviewError("This pair was unlinked, and the card has been changed since. Undo the newer "
                              "changes first (they are listed under Recent changes), then put this one back.")
        res = await undo_last(db, org_id, owner, user_id)
        return {"match_id": str(mid), "restored": len(rows), "relinked": True, "log_id": res["log_id"]}
    sql, params = _pair_rows("UPDATE card_review_log SET undone_at = NOW()", org_id, mid, other, kind)
    res = await db.execute(text(sql), params)
    await db.commit()
    return {"match_id": str(mid), "restored": res.rowcount, "relinked": False}


# --- fixing the strong doubles in one batch ------------------------------------------------------

BULK_DOUBLE_CAP = 600


def bulk_doubles_preview(rows: list, *, sample: int = 8) -> dict:
    """What a bulk fix would do on its first pass: the strong wrong links it would move and the
    strong unlinked pairs it would link. A later pass can find more (a game freed by a moved link
    may now match its own card), so the numbers are a floor."""
    strong = [r for r in rows if r["strength"] == "strong" and r["kind"] in ("relink", "ca", "swap")]
    pick = sorted(strong, key=lambda r: ({"relink": 0, "swap": 1}.get(r["kind"], 2), r["date"] or ""))[:sample]
    return {"relink": sum(1 for r in strong if r["kind"] == "relink"), "ca": sum(1 for r in strong if r["kind"] == "ca"),
            "swap": sum(1 for r in strong if r["kind"] == "swap"), "sample": pick}


async def bulk_fix_doubles(db, org_id, user_id, *, max_rounds: int = 3) -> dict:
    """Move every strong wrong link to its right game and link every strong unlinked pair, as one
    batch that can be undone. Moving a link frees a game, and that game's own card may then match
    it, so the scan is repeated (up to `max_rounds`) until a pass finds nothing."""
    batch = uuid.uuid4()
    done = {"relink": 0, "ca": 0, "swap": 0}
    skipped, players = [], set()
    for _ in range(max_rounds):
        found = await dbl.find_doubles(db, org_id)
        todo = [r for r in found["rows"] if r["strength"] == "strong" and r["kind"] in done]
        todo.sort(key=lambda r: ({"relink": 0, "swap": 1}.get(r["kind"], 2), r["date"] or "", r["key"]))
        todo = todo[:BULK_DOUBLE_CAP - sum(done.values())]
        if not todo:
            break
        progress = 0
        for r in todo:
            try:
                if r["kind"] == "relink":
                    res = await relink(db, org_id, r["a"]["id"], r["b"]["id"], user_id, batch_id=batch, commit=False)
                elif r["kind"] == "swap":
                    res = await swap_links(db, org_id, r["a"]["id"], r["partner"]["match"]["id"], r["b"]["id"], user_id,
                                           batch_id=batch, commit=False)
                else:
                    res = await link_double(db, org_id, r["a"]["id"], r["b"]["id"], user_id, batch_id=batch, commit=False)
                players.update(res["players"])
                done[r["kind"]] += 1
                progress += 1
            except ReviewError as e:
                skipped.append({"match_id": r["a"]["id"], "reason": str(e)})
        await db.commit()
        if not progress or sum(done.values()) >= BULK_DOUBLE_CAP:
            break
    await recompute(db, org_id, players)
    total = sum(done.values())
    if total:
        await db.execute(text("""
            INSERT INTO audit_logs (org_id, action, target_type, target_id, details)
            VALUES (CAST(:o AS UUID), 'card_review_bulk', 'manual_games', :t, CAST(:d AS JSONB))"""), {
            "o": str(org_id), "t": str(batch),
            "d": json.dumps({"why": "Strong possible doubles fixed: wrong links moved to the right game and unlinked pairs linked.",
                             "kind": "doubles", "batch_id": str(batch), "matches": total,
                             "relinked": done["relink"], "linked": done["ca"], "swapped": done["swap"],
                             "skipped": len(skipped)})})
        await db.commit()
    return {"batch_id": str(batch), "relinked": done["relink"], "linked": done["ca"], "swapped": done["swap"],
            "skipped": skipped}


async def wrong_grade_links(db, org_id) -> list:
    """Linked cards that sit on a game of ANOTHER grade, with nothing a person decided keeping them there.

    The CSV import linked on a date and one shared opposition word and ignored grade. A card whose
    real game the scan can find (a move or a swap) is left to that fix, so this runs after it: what
    is left has no game of its own grade to go to, and the honest state is a card that stands alone.
    A card with an unreadable grade name is never listed (nothing says the grades differ)."""
    found = await dbl.find_doubles(db, org_id)
    offered = set()
    for r in found["rows"]:
        if r["kind"] in ("relink", "swap"):
            offered.add(r["a"]["id"])
            if r.get("partner"):
                offered.add(r["partner"]["match"]["id"])
    return [r for r in await la.linked_verdicts(db, org_id) if r["verdict"] in la.WRONG_GRADE and r["mid"] not in offered]


async def bulk_unlink_wrong_grade(db, org_id, user_id) -> dict:
    """Unlink every card `wrong_grade_links` lists, as one batch that can be undone.

    Unlinking says "these are two different matches": the card stands alone and the game counts on
    its own, so neither is lost, and the pair is not offered again. Nothing is deleted."""
    todo = (await wrong_grade_links(db, org_id))[:BULK_DOUBLE_CAP]
    batch, players, done, skipped = uuid.uuid4(), set(), 0, []
    for r in todo:
        try:
            res = await unlink(db, org_id, r["mid"], user_id, batch_id=batch, commit=False)
            players.update(res["players"])
            done += 1
        except ReviewError as e:
            skipped.append({"match_id": r["mid"], "reason": str(e)})
    await db.commit()
    await recompute(db, org_id, players)
    if done:
        await db.execute(text("""
            INSERT INTO audit_logs (org_id, action, target_type, target_id, details)
            VALUES (CAST(:o AS UUID), 'card_review_bulk', 'manual_games', :t, CAST(:d AS JSONB))"""), {
            "o": str(org_id), "t": str(batch),
            "d": json.dumps({"why": "Cards linked to a game of another grade were unlinked and stand alone.",
                             "kind": "unlink_wrong_grade", "batch_id": str(batch), "matches": done,
                             "skipped": len(skipped)})})
    await db.commit()
    return {"batch_id": str(batch), "unlinked": done, "skipped": skipped}


# --- recent changes: every change anyone has made, with its undo -----------------------------------

_UNDOABLE = ("choice", "pair_ok", "relink", "unlink", "link")

_RECENT = """
    SELECT * FROM (
        SELECT l.id, l.action, l.from_choice, l.to_choice, l.source, l.batch_id::text AS batch_id,
               l.created_at, l.undone_at, l.manual_game_id::text AS mid, l.detail, u.username,
               mg.played_at, mg.opposition, COALESCE(gr.display_name_override, gr.name) AS grade,
               s.name AS season, mg.superseded_by_game_id IS NOT NULL AS linked_now,
               CASE
                 WHEN l.undone_at IS NOT NULL THEN NULL
                 WHEN l.action = 'not_double' THEN 'restore'
                 WHEN l.action IN ('choice', 'pair_ok', 'relink', 'unlink', 'link') AND l.id = (
                      SELECT max(l2.id) FROM card_review_log l2
                       WHERE l2.manual_game_id = l.manual_game_id AND l2.undone_at IS NULL
                         AND l2.action IN ('choice', 'pair_ok', 'relink', 'unlink', 'link')) THEN 'undo'
               END AS can
          FROM card_review_log l
          LEFT JOIN users u ON u.id = l.user_id
          LEFT JOIN manual_games mg ON mg.id = l.manual_game_id
          LEFT JOIN grades gr ON gr.id = mg.grade_id
          LEFT JOIN seasons s ON s.id = mg.season_id
         WHERE l.org_id = CAST(:org AS UUID) AND l.action <> 'undo'
    ) t
     WHERE (CAST(:only AS BOOLEAN) = FALSE OR t.can IS NOT NULL)
     ORDER BY t.id DESC LIMIT :lim OFFSET :off
"""


def describe_change(r: dict) -> str:
    """One sentence for a change, in the words the rest of Card review uses."""
    names = {"ca": "Cricket Australia", "club": "the club scorecard", "hybrid": "the club scorecard with Cricket Australia detail"}
    d = r.get("detail") or {}
    a = r["action"]
    if a == "choice":
        return f"Switched to {names.get(r['to_choice'], '?')} (was {names.get(r['from_choice'], '?')})"
    if a == "pair_ok":
        return "Said the two cards are the same match"
    if a == "link":
        return "Linked the club scorecard to a Cricket Australia match"
    if a == "relink":
        return "Moved the link to a different Cricket Australia match"
    if a == "unlink":
        if d.get("swap"):
            return "Unlinked for a moment, to swap two cards onto each other's games"
        return "Unlinked: said these are two different matches"
    if a == "not_double":
        if d.get("via") == "unlink":
            return "Marked as different matches (by unlinking)"
        return {"club": "Said two club scorecards are different matches",
                "relink": "Said the suggested game is not the right one"}.get(d.get("other_kind"), "Said these are different matches")
    if a == "refresh":
        return "Refreshed the Cricket Australia detail"
    return a


async def recent_changes(db, org_id, *, limit: int = 50, offset: int = 0, only_undoable: bool = False) -> dict:
    rows = [dict(r) for r in (await db.execute(text(_RECENT), {
        "org": str(org_id), "only": only_undoable, "lim": limit + 1, "off": offset})).mappings().all()]
    more = len(rows) > limit
    out = []
    for r in rows[:limit]:
        d = r.get("detail") or {}
        out.append({
            "id": r["id"], "action": r["action"], "what": describe_change(r), "match_id": r["mid"],
            "date": str(r["played_at"]) if r["played_at"] else None, "grade": r["grade"],
            "opposition": r["opposition"], "season": r["season"], "by": r["username"],
            "bulk": bool(r["batch_id"]), "batch_id": r["batch_id"],
            "at": r["created_at"].isoformat() if r["created_at"] else None,
            "undone_at": r["undone_at"].isoformat() if r["undone_at"] else None,
            "can": r["can"], "linked_now": bool(r["linked_now"]),
            "other_id": d.get("other_id"), "other_kind": d.get("other_kind"),
        })
    return {"rows": out, "more": more, "offset": offset, "limit": limit}
