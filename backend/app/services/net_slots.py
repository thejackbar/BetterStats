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
      "slot_overrides": {"3": 10},   # optional: slot 3 runs ten minutes
      "finish_time": "18:09",        # optional; nets end. NULL = no end, no overflow
      "second_go": true,             # spare cells at the foot repeat the order
      "pad_up_seconds": 120,         # warn the next batters this long before the change; 0 = off
      "tz_offset_minutes": 480,      # minutes EAST of UTC when the plan was saved
      "nets": [
        {"id": "n1", "name": "Net 1", "squad_team_ids": ["<uuid>", ...], "catch_all": false},
        {"id": "n3", "name": "Juniors", "squad_team_ids": [], "catch_all": true}
      ]
    }

SLOT LENGTHS. Every slot is `slot_minutes` long unless `slot_overrides`
(`{"3": 10}`: slot 3 is ten minutes) says otherwise. A coach edits a TIME on the
grid, not a length: setting the 4:37 row to 4:40 makes the slot above it three
minutes longer and every later time moves with it, because start times are
cumulative. People keep their slot numbers, so "fewer players than expected, give
the early batters longer" is one edit. See `set_slot_time`.

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
MAX_SLOT_MINUTES = 240
DEFAULT_SLOT_MINUTES = 7
DEFAULT_PAD_UP_SECONDS = 120
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
        "slot_overrides": {},
        "finish_time": None,
        "second_go": False,
        "pad_up_seconds": DEFAULT_PAD_UP_SECONDS,
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

    ov_raw = raw.get("slot_overrides")
    if isinstance(ov_raw, dict):
        for k, v in ov_raw.items():
            try:
                i, n = int(k), int(v)
            except (TypeError, ValueError):
                continue
            if 0 <= i < MAX_SLOTS and 1 <= n <= MAX_SLOT_MINUTES and n != out["slot_minutes"]:
                out["slot_overrides"][str(i)] = n

    fin = parse_hhmm(raw.get("finish_time"))
    # A finish at or before the start would read as "no slots at all"; an
    # evening session does not cross midnight, so treat it as not set.
    out["finish_time"] = fmt_hhmm(fin) if (fin is not None and first is not None and fin > first) else None

    out["second_go"] = bool(raw.get("second_go"))
    try:
        out["pad_up_seconds"] = max(0, min(1800, int(raw.get("pad_up_seconds", DEFAULT_PAD_UP_SECONDS))))
    except (TypeError, ValueError):
        pass
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


def slot_length(plan: dict, i: int) -> int:
    """How many minutes slot `i` runs."""
    ov = plan.get("slot_overrides") or {}
    return int(ov.get(str(i), plan.get("slot_minutes") or DEFAULT_SLOT_MINUTES))


def slot_offsets(plan: dict, n: int) -> list[int]:
    """Minutes from the first slot's start to the start of each of `n` slots,
    plus the end of the last: `n + 1` numbers. Cumulative, which is why editing
    one time moves everything below it."""
    out, t = [0], 0
    for i in range(n):
        t += slot_length(plan, i)
        out.append(t)
    return out


def slot_starts(plan: dict, n: int) -> list[int]:
    """Clock start (minutes after midnight) of each of the first `n` slots."""
    first = parse_hhmm(plan.get("first_time"))
    if first is None:
        return []
    return [first + o for o in slot_offsets(plan, n)[:n]]


def slot_total(plan: dict) -> Optional[int]:
    """How many whole slots fit before the finish, or None with no finish time."""
    first = parse_hhmm(plan.get("first_time"))
    fin = parse_hhmm(plan.get("finish_time"))
    if first is None or fin is None:
        return None
    n, t = 0, first
    while n < MAX_SLOTS:
        t += slot_length(plan, n)
        if t > fin:
            break
        n += 1
    return n


def start_utc(plan: dict, session_date: date) -> Optional[datetime]:
    """The moment slot 0 starts, as an absolute time."""
    first = parse_hhmm(plan.get("first_time"))
    if first is None or session_date is None:
        return None
    local = datetime(session_date.year, session_date.month, session_date.day, tzinfo=timezone.utc) + timedelta(minutes=first)
    return local - timedelta(minutes=int(plan.get("tz_offset_minutes") or 0))


def slot_start_at(plan: dict, session_date: date, i: int) -> Optional[datetime]:
    """The absolute moment slot `i` starts."""
    st = start_utc(plan, session_date)
    if st is None:
        return None
    return st + timedelta(minutes=slot_offsets(plan, i + 1)[i])


def now_slot(plan: dict, session_date: date, now: datetime) -> Optional[int]:
    """The slot running right now: -1 before the first, None when not planned."""
    st = start_utc(plan, session_date)
    if st is None:
        return None
    mins = (now - st).total_seconds() / 60.0
    if mins < 0:
        return -1
    i, acc = 0, 0
    while acc + slot_length(plan, i) <= mins and i < MAX_SLOTS * 4:
        acc += slot_length(plan, i)
        i += 1
    return i


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
    i, start = 0, 0
    while start < mins and i < MAX_SLOTS * 4:
        start += slot_length(plan, i)
        i += 1
    return i


def has_started(plan: dict, session_date: date, now: datetime) -> bool:
    """Whether the first slot has begun. False when there is no start time to
    measure against, so a queue session or an unplanned grid never "starts"."""
    st = start_utc(plan, session_date) if is_configured(plan) else None
    return st is not None and now >= st


def set_slot_time(plan: dict, i: int, hhmm: str) -> dict:
    """A copy of `plan` with slot `i` starting at `hhmm`.

    Slot 0 is the first net time, and moving it moves every slot. Any other slot
    is set by lengthening or shortening the slot ABOVE it, so every later time
    moves by the same amount. Raises ValueError with a sentence a coach can read
    when the time cannot be."""
    want = parse_hhmm(hhmm)
    first = parse_hhmm(plan.get("first_time"))
    if want is None or first is None:
        raise ValueError("That is not a time.")
    out = clean_plan(plan)
    if i == 0:
        out["first_time"] = fmt_hhmm(want)
        return clean_plan(out)
    if i < 0 or i >= MAX_SLOTS:
        raise ValueError("That slot is not on the grid.")
    prev_start = first + slot_offsets(plan, i)[i - 1]
    new_len = want - prev_start
    if new_len < 1:
        raise ValueError("A slot has to start after the one above it.")
    if new_len > MAX_SLOT_MINUTES:
        raise ValueError("That slot would run for more than four hours.")
    ov = dict(out["slot_overrides"])
    if new_len == out["slot_minutes"]:
        ov.pop(str(i - 1), None)
    else:
        ov[str(i - 1)] = new_len
    out["slot_overrides"] = ov
    return clean_plan(out)


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
        "pad_up_seconds": int(plan.get("pad_up_seconds") or 0),
        "slots": n_rows if configured else 0,
        "times": [fmt_hhmm(t) for t in slot_starts(plan, n_rows)] if configured else [],
        # Minutes from `start_at` to the start of each slot, and the end of the
        # last: what a device needs to find the running slot from its own clock.
        "offsets": slot_offsets(plan, n_rows) if configured else [],
        "custom_slots": sorted(int(k) for k in (plan.get("slot_overrides") or {})),
        "start_at": st.isoformat() if st else None,
        "now_slot": now_slot(plan, session_date, now) if (configured and session_date) else None,
        "nets": nets_out,
        "no_net": no_net,
        "overflow_count": sum(len(v) for v in overflow.values()),
    }
