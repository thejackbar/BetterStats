"""Fall of wickets a club typed from its own scorebook, for a synced match.

WHY THIS EXISTS
---------------
Cricket Australia's scorecard is sometimes short of fall of wickets: six wickets fell and
four rows were recorded. The club's paper scorebook has the rest. Until now a short fall of
wickets could not be put right, and (before `partial_partnerships`) cost the whole innings its
partnerships. A club can now type the fall of wickets for its own innings of a synced match.
Those rows REPLACE the synced fall of wickets for that innings and the partnerships are worked
out from them with the same rules sync uses (`sync._derive_partnerships_grassroots`).

WHERE IT LIVES
--------------
In `fow_overrides` (migration 357), never only in `fall_of_wickets`. A Full Rebuild deletes
every synced game and stores it again, which cascades the synced rows away; a club's typing
has no upstream to pull back. The typed rows are applied to the game each time sync stores it
(`apply`), and by the editor route straight away. `game_id` carries no foreign key for the same
reason.

SCOPE
-----
Only the club's OWN innings can be edited. A fixture between two synced clubs is one `games`
row, and the other club's innings carries rows written from the other club's own sync (their
players linked to their own records); replacing those from here would unlink them. The
opposition's fall of wickets stays whatever Cricket Australia holds.

Nothing here is destructive beyond that: the club's own rows for the innings are replaced,
`reset` puts Cricket Australia's back by reading the card again, and each save and reset is
recorded in `audit_events`.
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import participant_relink as relink
from app.services.partial_partnerships import skipped_reasons
from app.services.sync import _derive_partnerships_grassroots, _dismissed_pids_grassroots

logger = logging.getLogger(__name__)

# A side has eleven batters, so ten wickets at most.
MAX_WICKETS = 10

_NO_BAT = {"absent", "did not bat", "dnb"}


def innings_number(inn: dict) -> int:
    return inn.get("inningsOrder") or inn.get("inningsNumber") or 1


def _guid(v) -> Optional[uuid.UUID]:
    try:
        return v if isinstance(v, uuid.UUID) else uuid.UUID(str(v))
    except (ValueError, TypeError, AttributeError):
        return None


# ─── Stored rows ──────────────────────────────────────────────────────────────

async def load(db: AsyncSession, org_id, game_id) -> dict[int, list[dict]]:
    """The club's typed wickets for a game, by innings number, in wicket order."""
    rows = (await db.execute(text("""
        SELECT innings_number, wicket_number, score_at_fall, participant_id, batter_name
          FROM fow_overrides
         WHERE organisation_id = CAST(:o AS UUID) AND game_id = CAST(:g AS UUID)
         ORDER BY innings_number, wicket_number"""), {"o": str(org_id), "g": str(game_id)})).mappings().all()
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["innings_number"], []).append(dict(r))
    return out


def as_grassroots(rows: list[dict]) -> list[dict]:
    """Typed rows in the shape Cricket Australia's `fallOfWickets` has, so the one deriver reads them."""
    return [{"order": r["wicket_number"], "runs": r["score_at_fall"],
             "participantId": r.get("participant_id") or None,
             "playerShortName": r.get("batter_name")}
            for r in sorted(rows, key=lambda r: r["wicket_number"])]


def overlay(scorecard: dict, typed: dict[int, list[dict]]) -> dict:
    """The scorecard with the typed fall of wickets in place of Cricket Australia's, innings by innings."""
    card = dict(scorecard)
    innings = []
    for inn in scorecard.get("innings") or []:
        rows = typed.get(innings_number(inn))
        innings.append(dict(inn, fallOfWickets=as_grassroots(rows)) if rows else inn)
    card["innings"] = innings
    return card


async def _clear_innings(db: AsyncSession, org_id, game_id, innings: int) -> None:
    """Remove the stored fall of wickets and the club's partnerships for one innings of one game.

    Partnerships go only where neither batter is another club's player: a shared fixture can carry
    the other club's stands in the same innings.
    """
    gid = _guid(game_id)
    await db.execute(text(
        "DELETE FROM fall_of_wickets WHERE game_id = :g AND innings_number = :i"), {"g": gid, "i": innings})
    await db.execute(text("""
        DELETE FROM partnerships p
         WHERE p.game_id = :g AND p.innings_number = :i
           AND NOT EXISTS (SELECT 1 FROM players pl
                            WHERE pl.id IN (p.batter1_id, p.batter2_id)
                              AND pl.organisation_id <> CAST(:o AS UUID))"""),
        {"g": gid, "i": innings, "o": str(org_id)})


async def apply(db: AsyncSession, org_id, game_id, scorecard: dict, resolve) -> dict:
    """Write the club's typed fall of wickets (and the partnerships they give) onto a stored game.

    Replaces the synced rows for each innings the club typed, then lets `attach_innings_detail`
    write both tables, the same code a re-read runs. Returns its counts, or {} when the club has
    typed nothing for this game. Does not commit.
    """
    typed = await load(db, org_id, game_id)
    if not typed:
        return {}
    await db.flush()  # rows sync has added but not flushed must be there to be replaced
    for inn in sorted(typed):
        await _clear_innings(db, org_id, game_id, inn)
    return await relink.attach_innings_detail(
        db, org_id, game_id, overlay(scorecard, typed), resolve, replace_innings=frozenset(typed))


async def apply_in_sync(session: AsyncSession, org_id, game_id, scorecard: dict, resolve) -> dict:
    """`apply` for sync's per-game session. A failure rolls back to a savepoint, so a problem here
    can never take the game's own rows with it."""
    try:
        async with session.begin_nested():
            return await apply(session, org_id, game_id, scorecard, resolve)
    except Exception as exc:
        logger.warning("fow_overrides: could not apply to %s: %s", game_id, exc)
        return {}


# ─── Validating what a person typed ───────────────────────────────────────────

def batting_innings(scorecard: dict, num: int) -> Optional[dict]:
    return next((i for i in scorecard.get("innings") or [] if innings_number(i) == num), None)


def dismissed_batters(inn: dict) -> list[dict]:
    """The batters who were out on the card's batting list, in batting order."""
    out = _dismissed_pids_grassroots(inn.get("batting") or [])
    rows = [b for b in inn.get("batting") or [] if b.get("participantId") in out]
    return sorted(rows, key=lambda b: b.get("batOrder") or 99)


def clean_rows(inn: dict, rows: list[dict]) -> tuple[list[dict], list[str]]:
    """Check typed wickets against the innings' batting card. Returns (rows, errors).

    Errors are things the card cannot be true with (a wicket twice, a batter out twice, a score
    that goes backwards, a batter the card says was not out). A wicket past the card's own
    dismissals is let through, because a scorebook may be right where the card is wrong; the
    partnerships for that innings are then simply not worked out, and the caller says so.
    """
    errors: list[str] = []
    batters = {b["participantId"]: b for b in dismissed_batters(inn) if b.get("participantId")}
    all_batters = {b["participantId"]: b for b in inn.get("batting") or [] if b.get("participantId")}
    out: list[dict] = []
    seen_w: set = set()
    seen_p: set = set()
    for r in rows:
        w = r.get("wicket_number")
        score = r.get("score_at_fall")
        pid = (r.get("participant_id") or "").strip() or None
        if not isinstance(w, int) or isinstance(w, bool) or not 1 <= w <= MAX_WICKETS:
            errors.append(f"Wicket {w!r} is not between 1 and {MAX_WICKETS}.")
            continue
        if w in seen_w:
            errors.append(f"Wicket {w} is entered twice.")
            continue
        seen_w.add(w)
        if score is not None and (not isinstance(score, int) or isinstance(score, bool) or score < 0):
            errors.append(f"Wicket {w}: the score has to be a whole number of runs, 0 or more.")
            continue
        if score is None and not pid:
            errors.append(f"Wicket {w} has no score and no batter. Fill it in or take the row out.")
            continue
        if pid:
            if pid not in all_batters:
                errors.append(f"Wicket {w}: that batter is not on this innings' batting card.")
                continue
            if pid not in batters:
                name = all_batters[pid].get("playerShortName") or "That batter"
                errors.append(f"Wicket {w}: {name} is not out on the batting card.")
                continue
            if pid in seen_p:
                name = all_batters[pid].get("playerShortName") or "A batter"
                errors.append(f"{name} is entered as out at two wickets.")
                continue
            seen_p.add(pid)
        out.append({"wicket_number": w, "score_at_fall": score, "participant_id": pid,
                    "batter_name": (all_batters[pid].get("playerShortName") if pid else None)})
    out.sort(key=lambda r: r["wicket_number"])
    # With every wicket entered the partnerships come from walking the order of dismissal, which
    # needs to know who was out each time. A short list can leave a batter blank (the walk then
    # tries every way the card allows), a complete one cannot.
    wickets = len(batters)
    if wickets and len(out) == wickets:
        for r in out:
            if not r["participant_id"]:
                errors.append(f"Every wicket is entered, so each needs its batter. Pick who was out at wicket {r['wicket_number']}.")
    prev = 0
    for r in out:
        if r["score_at_fall"] is None:
            continue
        if r["score_at_fall"] < prev:
            errors.append(f"Wicket {r['wicket_number']}: {r['score_at_fall']} is lower than the score at an earlier wicket ({prev}).")
        prev = max(prev, r["score_at_fall"])
    return out, errors


# ─── What the editor shows ────────────────────────────────────────────────────

async def _stands(db: AsyncSession, org_id, game_id, innings: int) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT pt.wicket_number, pt.runs,
               COALESCE(p1.display_name_override, p1.name, pt.batter1_name) AS batter1_name,
               COALESCE(p2.display_name_override, p2.name, pt.batter2_name) AS batter2_name
          FROM v_effective_partnerships pt
          LEFT JOIN players p1 ON p1.id = pt.batter1_id AND p1.organisation_id = CAST(:o AS UUID)
          LEFT JOIN players p2 ON p2.id = pt.batter2_id AND p2.organisation_id = CAST(:o AS UUID)
         WHERE pt.game_id = CAST(:g AS UUID) AND pt.innings_number = :i
         ORDER BY pt.wicket_number"""), {"o": str(org_id), "g": str(game_id), "i": innings})).mappings().all()
    return [dict(r) for r in rows]


async def editor(db: AsyncSession, org_id, game_id, scorecard: dict, resolve) -> list[dict]:
    """One entry per innings the club batted in, with what it can be edited from.

    `fow` is the typed rows when the club has typed some, else what Cricket Australia's card holds.
    `stands` are the partnerships stored now, and `missing` says why each other wicket has none.
    """
    team = relink._our_team(scorecard, org_id)
    if not team:
        return []
    our_pids = {resolve(p.get("participantId")) for p in team.get("players") or [] if p.get("participantId")}
    our_pids.discard(None)
    typed = await load(db, org_id, game_id)
    out = []
    for inn in sorted(scorecard.get("innings") or [], key=innings_number):
        if not relink.is_club_innings_of(inn, team, resolve, our_pids):
            continue
        num = innings_number(inn)
        wickets = len(_dismissed_pids_grassroots(inn.get("batting") or []))
        fow = as_grassroots(typed[num]) if num in typed else sorted(
            inn.get("fallOfWickets") or [], key=lambda f: f.get("order") or 99)
        stands = await _stands(db, org_id, game_id, num)
        out.append({
            "innings_number": num,
            "edited": num in typed,
            "wickets": wickets,
            "batters": [{"participant_id": b["participantId"], "name": b.get("playerShortName"),
                         "bat_order": b.get("batOrder"), "runs": b.get("runsScored"),
                         "dismissal": b.get("dismissalType")}
                        for b in dismissed_batters(inn) if b.get("participantId")],
            "fow": [{"wicket_number": f.get("order"), "score_at_fall": f.get("runs"),
                     "participant_id": f.get("participantId") or None,
                     "batter_name": f.get("playerShortName")} for f in fow if f.get("order") is not None],
            "stands": stands,
            "missing": skipped_reasons(wickets, fow, stands) if len(stands) < wickets else {},
        })
    return out


# ─── Saving ───────────────────────────────────────────────────────────────────

async def save(db: AsyncSession, org_id, user_id, game_id, num: int, rows: list[dict]) -> None:
    """Replace the club's typed wickets for one innings. Does not commit."""
    await db.execute(text("""
        DELETE FROM fow_overrides
         WHERE organisation_id = CAST(:o AS UUID) AND game_id = CAST(:g AS UUID) AND innings_number = :i"""),
        {"o": str(org_id), "g": str(game_id), "i": num})
    for r in rows:
        await db.execute(text("""
            INSERT INTO fow_overrides (organisation_id, game_id, innings_number, wicket_number,
                                       score_at_fall, participant_id, batter_name, entered_by)
            VALUES (CAST(:o AS UUID), CAST(:g AS UUID), :i, :w, :s, :p, :n, CAST(:u AS UUID))"""),
            {"o": str(org_id), "g": str(game_id), "i": num, "w": r["wicket_number"],
             "s": r["score_at_fall"], "p": r["participant_id"], "n": r["batter_name"],
             "u": str(user_id) if user_id else None})


async def remove(db: AsyncSession, org_id, game_id, num: int) -> int:
    """Drop the club's typed wickets for one innings. Returns how many rows went. Does not commit."""
    res = await db.execute(text("""
        DELETE FROM fow_overrides
         WHERE organisation_id = CAST(:o AS UUID) AND game_id = CAST(:g AS UUID) AND innings_number = :i"""),
        {"o": str(org_id), "g": str(game_id), "i": num})
    return res.rowcount or 0


async def restore_synced(db: AsyncSession, org_id, game_id, scorecard: dict, resolve, num: int) -> dict:
    """Put Cricket Australia's own fall of wickets and partnerships back for one innings."""
    await db.flush()
    await _clear_innings(db, org_id, game_id, num)
    return await relink.attach_innings_detail(
        db, org_id, game_id, scorecard, resolve, replace_innings=frozenset({num}))


async def audit(db: AsyncSession, org_id, user, game_id, action: str, summary: str, detail: dict) -> None:
    """One `audit_events` row, so the change shows on the club's audit trail."""
    label = (await db.execute(text("""
        SELECT COALESCE(g.home_team, '') || ' v ' || COALESCE(g.away_team, '') || ' ' ||
               COALESCE(to_char(g.played_at, 'DD Mon YYYY'), '')
          FROM v_effective_games g WHERE g.id = CAST(:g AS UUID)"""), {"g": str(game_id)})).scalar()
    name = (getattr(user, "display_name", None) or getattr(user, "username", None)
            or getattr(user, "email", None) or None)
    await db.execute(text("""
        INSERT INTO audit_events (organisation_id, user_id, user_name, via, area, action,
                                  fixture_id, fixture_label, summary, detail)
        VALUES (CAST(:o AS UUID), CAST(:u AS UUID), :un, 'admin', 'scorecard', :a,
                CAST(:g AS UUID), :fl, :s, CAST(:d AS JSONB))"""),
        {"o": str(org_id), "u": str(user.id) if user is not None else None, "un": name, "a": action,
         "g": str(game_id), "fl": (label or "").strip() or None, "s": summary, "d": json.dumps(detail)})


def summarise(inn_num: int, rows: list[dict], stands: list[dict], wickets: int) -> str:
    wk = len(rows)
    base = f"Fall of wickets for innings {inn_num}: {wk} of {wickets} wicket{'s' if wickets != 1 else ''} entered"
    return f"{base}, {len(stands)} partnership{'s' if len(stands) != 1 else ''} worked out."
