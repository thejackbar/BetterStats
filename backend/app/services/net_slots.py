"""Time-slot nets: the pure rules behind an automatic net session.

A net session has two run modes. In `manual` mode (the original) there is one
batting queue and a timer. In `auto` mode the night is a GRID: each net is a
column, each row a time slot, and a player is placed in one cell of one net as
they check in. This module is the maths and nothing else (no database, no
request), so the rules can be proved without either and the router and the
screen cannot disagree about them.

THE PLAN (`net_sessions.slot_plan`, JSONB)::

    {
      "first_time": "16:45",         # first slot starts, club wall-clock time
      "slot_minutes": 7,
      "finish_time": "18:09",        # optional; nets end. NULL = no end, no overflow
      "second_go": true,             # spare cells at the foot repeat the order
      "tz_offset_minutes": 480,      # minutes EAST of UTC when the plan was saved
      "nets": [
        {"id": "n1", "name": "Net 1", "squad_team_ids": ["<uuid>", ...], "catch_all": false},
        {"id": "n3", "name": "Juniors", "squad_team_ids": [], "catch_all": true}
      ]
    }

WHAT IS STORED AND WHAT IS DERIVED. Stored per attendee: `net_key` (a plan net
id), `slot_index` (0 = the first slot) and `slot_manual` (somebody dragged them
there). Derived on read, never stored: every clock time, which row is "now",
second-go cells, who does not fit. Changing the slot length or the first time
therefore moves every time on the grid and corrupts nothing.

WHY `tz_offset_minutes`. The app holds no per-club timezone, and a late arrival
needs "the next slot that has not started", which is a question about the
club's wall clock. The browser that saves the plan knows its own offset, so the
plan carries it. The grid's "now" row is drawn by each device from the same
absolute start time (`start_utc`), so a phone in the wrong timezone still
agrees with the server.

A squad belongs to one net (the first that names it wins), and a player in
several squads goes to the net of their HIGHEST squad (lowest `teams.sequence`)
that has a net. One net can be marked catch-all: it takes everyone whose squads
have no net, and guests. With no catch-all those people are left "not in a
net", which the screen says in words and lets the coach place by hand. That is
a warning, not a refusal.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Iterable, Optional

MAX_NETS = 8
MAX_SLOTS = 96
DEFAULT_SLOT_MINUTES = 7
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def parse_hhmm(v) -> Optional[int]:
    """'16:45' -> minutes after midnight, or None for anything else."""
    if not isinstance(v, str):
        return None
    m = _TIME_RE.match(v.strip())
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def fmt_hhmm(minutes: int) -> str:
    minutes = int(minutes) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def default_plan() -> dict:
    return {
        "first_time": None,
        "slot_minutes": DEFAULT_SLOT_MINUTES,
        "finish_time": None,
        "second_go": False,
        "tz_offset_minutes": 0,
        "nets": [],
    }


def clean_plan(raw, valid_team_ids: Optional[Iterable[str]] = None) -> dict:
    """Coerce a plan from the browser (or the database) into a complete one.

    Every key always comes back. `valid_team_ids`, when given, is the set of the
    club's own squad ids: anything else is dropped so a plan can never point at
    another club's squad. A squad named by two nets stays in the first, and only
    the first catch-all net keeps the flag, because "which net does this player
    go to" must have one answer.
    """
    raw = raw if isinstance(raw, dict) else {}
    out = default_plan()

    first = parse_hhmm(raw.get("first_time"))
    out["first_time"] = fmt_hhmm(first) if first is not None else None

    try:
        out["slot_minutes"] = max(1, min(60, int(raw.get("slot_minutes", DEFAULT_SLOT_MINUTES))))
    except (TypeError, ValueError):
        pass

    fin = parse_hhmm(raw.get("finish_time"))
    # A finish at or before the start would read as "no slots at all"; an
    # evening session does not cross midnight, so treat it as not set.
    out["finish_time"] = fmt_hhmm(fin) if (fin is not None and first is not None and fin > first) else None

    out["second_go"] = bool(raw.get("second_go"))
    try:
        out["tz_offset_minutes"] = max(-840, min(840, int(raw.get("tz_offset_minutes", 0))))
    except (TypeError, ValueError):
        pass

    valid = None if valid_team_ids is None else {str(t) for t in valid_team_ids}
    seen_squads: set[str] = set()
    seen_ids: set[str] = set()
    have_catch_all = False
    nets_raw = raw.get("nets")
    for i, n in enumerate(nets_raw if isinstance(nets_raw, list) else []):
        if len(out["nets"]) >= MAX_NETS:
            break
        if not isinstance(n, dict):
            continue
        nid = str(n.get("id") or "").strip()[:24]
        if not nid or nid in seen_ids:
            nid = f"n{uuid.uuid4().hex[:6]}"
        seen_ids.add(nid)
        name = str(n.get("name") or "").strip()[:40] or f"Net {len(out['nets']) + 1}"
        squads: list[str] = []
        for t in n.get("squad_team_ids") or []:
            ts = str(t)
            if valid is not None and ts not in valid:
                continue
            if ts in seen_squads or ts in squads:
                continue
            squads.append(ts)
        seen_squads.update(squads)
        catch = bool(n.get("catch_all")) and not have_catch_all
        have_catch_all = have_catch_all or catch
        out["nets"].append({"id": nid, "name": name, "squad_team_ids": squads, "catch_all": catch})
    return out


def is_configured(plan: dict) -> bool:
    return bool(plan.get("first_time")) and bool(plan.get("nets"))


def slot_total(plan: dict) -> Optional[int]:
    """How many slots the night has, or None when there is no finish time."""
    first = parse_hhmm(plan.get("first_time"))
    fin = parse_hhmm(plan.get("finish_time"))
    if first is None or fin is None:
        return None
    return max(0, min(MAX_SLOTS, (fin - first) // int(plan.get("slot_minutes") or DEFAULT_SLOT_MINUTES)))


def start_utc(plan: dict, session_date: date) -> Optional[datetime]:
    """The moment slot 0 starts, as an absolute time."""
    first = parse_hhmm(plan.get("first_time"))
    if first is None or session_date is None:
        return None
    local = datetime(session_date.year, session_date.month, session_date.day, tzinfo=timezone.utc) + timedelta(minutes=first)
    return local - timedelta(minutes=int(plan.get("tz_offset_minutes") or 0))


def now_slot(plan: dict, session_date: date, now: datetime) -> Optional[int]:
    """The slot running right now: -1 before the first, None when not planned."""
    st = start_utc(plan, session_date)
    if st is None:
        return None
    mins = (now - st).total_seconds() / 60.0
    if mins < 0:
        return -1
    return int(mins // int(plan.get("slot_minutes") or DEFAULT_SLOT_MINUTES))


def first_open_slot(plan: dict, session_date: date, now: datetime) -> int:
    """The earliest slot a new arrival may be given: one that has not started.

    Before the first slot that is 0, so people arriving early fill the column
    from the top in the order they check in. Part-way through a slot it is the
    next one, so somebody walking in at 5:08 gets 5:13 and not a slot that
    has gone."""
    st = start_utc(plan, session_date)
    if st is None:
        return 0
    mins = (now - st).total_seconds() / 60.0
    if mins <= 0:
        return 0
    step = int(plan.get("slot_minutes") or DEFAULT_SLOT_MINUTES)
    k = int(mins // step)
    return k if k * step == mins else k + 1


def pick_net(plan: dict, squads: Iterable[tuple[str, Optional[int]]], is_guest: bool = False) -> Optional[str]:
    """Which net a person goes to, or None when no net will have them.

    `squads` is (team id, sequence) for each squad they are in. The highest
    squad (lowest sequence, then id for a stable answer) that has a net wins.
    Everyone else goes to the catch-all net, if there is one.
    """
    nets = plan.get("nets") or []
    by_squad = {t: n["id"] for n in nets for t in n.get("squad_team_ids") or []}
    if not is_guest:
        for tid, _seq in sorted(squads, key=lambda x: (x[1] if x[1] is not None else 10 ** 9, str(x[0]))):
            if str(tid) in by_squad:
                return by_squad[str(tid)]
    for n in nets:
        if n.get("catch_all"):
            return n["id"]
    return None


def first_free(occupied: set[int], total: Optional[int], min_idx: int = 0) -> Optional[int]:
    """The lowest free slot at or after `min_idx`, or None when the net is full."""
    i = max(0, int(min_idx))
    while total is None or i < total:
        if i not in occupied:
            return i
        i += 1
    return None


def build_grid(plan: dict, session_date: Optional[date], rows: list[dict], now: datetime) -> dict:
    """Everything the screen needs to draw the grid, derived from the plan and
    where each attendee currently sits.

    `rows` are dicts with `id`, `net_key`, `slot_index`, `bats` in CHECK-IN
    order. Nothing here is stored: times, second-go cells and "does not fit" are
    all worked out from those three facts each time.
    """
    configured = is_configured(plan)
    total = slot_total(plan)
    step = int(plan.get("slot_minutes") or DEFAULT_SLOT_MINUTES)
    first = parse_hhmm(plan.get("first_time"))
    st = start_utc(plan, session_date) if session_date else None
    net_ids = {n["id"] for n in plan.get("nets") or []}

    placed: dict[str, dict[int, str]] = {nid: {} for nid in net_ids}
    overflow: dict[str, list[str]] = {nid: [] for nid in net_ids}
    no_net: list[str] = []
    for r in rows:
        if not r.get("bats", True):
            continue
        nk = r.get("net_key")
        if nk in net_ids:
            if r.get("slot_index") is None or (total is not None and r["slot_index"] >= total):
                overflow[nk].append(r["id"])
            else:
                placed[nk][int(r["slot_index"])] = r["id"]
        else:
            no_net.append(r["id"])

    top = max((i for col in placed.values() for i in col), default=-1)
    # With no finish time the grid has no end: show the filled rows and a few
    # spare ones, so there is always an empty cell to drop a name into.
    n_rows = total if total is not None else max(8, top + 4)

    nets_out = []
    for n in plan.get("nets") or []:
        col = placed[n["id"]]
        repeat: dict[int, str] = {}
        if plan.get("second_go") and total is not None and col and not overflow[n["id"]]:
            order = [col[i] for i in sorted(col)]
            for k, slot in enumerate(range(max(col) + 1, total)):
                repeat[slot] = order[k % len(order)]
        cells = []
        for i in range(n_rows):
            if i in col:
                cells.append({"slot": i, "attendee_id": col[i], "repeat": False})
            elif i in repeat:
                cells.append({"slot": i, "attendee_id": repeat[i], "repeat": True})
            else:
                cells.append({"slot": i, "attendee_id": None, "repeat": False})
        nets_out.append({
            "id": n["id"], "name": n["name"], "squad_team_ids": n["squad_team_ids"],
            "catch_all": bool(n["catch_all"]),
            "cells": cells, "overflow": overflow[n["id"]], "count": len(col) + len(overflow[n["id"]]),
        })

    return {
        "configured": configured,
        "slot_minutes": step,
        "first_time": plan.get("first_time"),
        "finish_time": plan.get("finish_time"),
        "second_go": bool(plan.get("second_go")),
        "slots": n_rows if configured else 0,
        "times": [fmt_hhmm(first + i * step) for i in range(n_rows)] if (configured and first is not None) else [],
        "start_at": st.isoformat() if st else None,
        "now_slot": now_slot(plan, session_date, now) if (configured and session_date) else None,
        "nets": nets_out,
        "no_net": no_net,
        "overflow_count": sum(len(v) for v in overflow.values()),
    }
