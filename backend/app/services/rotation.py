"""Junior Rotation: the generator and the tallies, with no database in them.

A coach loads a group of kids, and each week this hands back a batting order and
who fields where, weighted by what each kid has already had so it evens out
across the season. Everything here is pure: callers pass in the group's
positions, the people who are here, and the LOCKED rounds so far, and get plain
dicts back. ``routers/rotation.py`` owns the storage.

Shape of a round, shared with the router and the screens:

  * ``batting_order``: list of player ids, first to bat first.
  * ``fielding``: one dict per field change, ``{player_id: position_id | None}``;
    ``None`` is a rest. A game with more kids than positions rests the spare
    kids, and everyone present has an entry in every change.

How "random but fair" works, and why it is one knob:

  ``fairness`` (0 to 100) says how hard a draw leans on history. At 0 every
  decision is a plain shuffle. Higher, the batting order is drawn one slot at a
  time with each kid's chance weighted by what they have had (a kid who usually
  bats late is likelier to lead off, one who has led off already is less likely
  to again), so it evens out over a season without next week's order being
  something a parent could work out from this one's. Who rests and who fields
  where draw several random candidates and keep the one that repeats the least
  against history, then polish it with a few swaps. Key positions (pitcher,
  bases and so on) count double, so the ones kids want are shared first.

Never invents history: a kid with no locked rounds is neutral, not owed.
"""
from __future__ import annotations

import math
import random
import uuid
from typing import Iterable, Optional

KEY_WEIGHT = 2
# A position a kid is to be kept out of. Bigger than any history count a season
# can build, so it only loses to the rule when there is genuinely no other way.
AVOID_PENALTY = 1000
# Cost of putting a kid in a key position per key turn they already have.
KEY_TOTAL_WEIGHT = 8
# How hard the batting draw leans, at fairness 100: on a kid's usual position, and
# against handing the first or last slot to a kid who has had it before.
BAT_LEAN = 14.0
EDGE_LEAN = 2.5

PRESETS: dict[str, dict] = {
    "tee_ball": {
        "label": "Tee ball",
        "innings": 1,
        "positions": [
            ("Pitcher", True), ("Catcher", True), ("1st base", True), ("2nd base", True),
            ("3rd base", True), ("Shortstop", True),
            ("Left field", False), ("Centre field", False), ("Right field", False),
        ],
    },
    "junior_cricket": {
        "label": "Junior cricket",
        "innings": 1,
        "positions": [
            ("Wicketkeeper", True), ("Bowler", True), ("Slip", False), ("Point", False),
            ("Cover", False), ("Mid off", False), ("Mid on", False),
            ("Square leg", False), ("Fine leg", False),
        ],
    },
    "custom": {"label": "Start blank", "innings": 1, "positions": []},
}


def new_position_id() -> str:
    return "p" + uuid.uuid4().hex[:8]


def preset_positions(kind: str) -> list[dict]:
    spec = PRESETS.get(kind) or PRESETS["custom"]
    return [{"id": new_position_id(), "name": n, "key": k} for n, k in spec["positions"]]


def clean_positions(raw, existing: Optional[list[dict]] = None) -> list[dict]:
    """A coach-edited list into the stored shape. Keeps the id of any row that
    already has one (so history survives a rename), mints one for a new row,
    drops blanks and a repeated id, and caps the list so one bad paste cannot
    build a thousand-position field."""
    keep = {p["id"] for p in (existing or [])}
    out: list[dict] = []
    seen: set[str] = set()
    for row in (raw or [])[:40]:
        if not isinstance(row, dict):
            continue
        name = " ".join(str(row.get("name") or "").split())[:40]
        if not name:
            continue
        pid = str(row.get("id") or "")
        if not pid or pid in seen or (existing is not None and pid not in keep):
            pid = new_position_id()
        seen.add(pid)
        out.append({"id": pid, "name": name, "key": bool(row.get("key"))})
    return out


def clean_name(raw) -> str:
    return " ".join(str(raw or "").split())[:60]


def split_names(raw: str) -> list[str]:
    """A pasted list (one a line, or comma separated) into clean names, in
    order, without a repeat (case folded)."""
    out: list[str] = []
    seen: set[str] = set()
    for chunk in str(raw or "").replace(",", "\n").splitlines():
        name = clean_name(chunk)
        if name and name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return out


# ─── History ────────────────────────────────────────────────────────────────

def _blank_stat() -> dict:
    return {"games": 0, "bat_pcts": [], "bat_first": 0, "bat_last": 0, "field": {}, "rests": 0}


def history_stats(rounds: Iterable[dict]) -> dict[str, dict]:
    """Per player id, what the given (locked) rounds say they have done.

    ``bat_pcts`` is where they stood in the order as a fraction (0 first, 1
    last; a one-kid order counts as the middle). ``field`` is how many field
    changes they have had at each position id, ``rests`` how many they sat out.
    A player counts as having played a round only if they were present.
    """
    stats: dict[str, dict] = {}
    for rnd in rounds:
        present = [str(p) for p in (rnd.get("present") or [])]
        order = [str(p) for p in (rnd.get("batting_order") or [])]
        n = len(order)
        for pid in present:
            stats.setdefault(pid, _blank_stat())["games"] += 1
        for i, pid in enumerate(order):
            st = stats.setdefault(pid, _blank_stat())
            st["bat_pcts"].append(0.5 if n < 2 else i / (n - 1))
            if i == 0:
                st["bat_first"] += 1
            if i == n - 1 and n > 1:
                st["bat_last"] += 1
        for change in rnd.get("fielding") or []:
            for pid, pos in (change or {}).items():
                st = stats.setdefault(str(pid), _blank_stat())
                if pos is None:
                    st["rests"] += 1
                else:
                    st["field"][pos] = st["field"].get(pos, 0) + 1
    return stats


def _mean_bat(stat: Optional[dict]) -> float:
    pcts = (stat or {}).get("bat_pcts") or []
    return sum(pcts) / len(pcts) if pcts else 0.5


def _candidates(fairness: int) -> int:
    return 1 + round(max(0, min(100, fairness)) / 100 * 60)


def _passes(fairness: int) -> int:
    return max(0, min(100, fairness)) // 25


# ─── The generator ──────────────────────────────────────────────────────────

def _batting(present: list[str], stats: dict, fairness: int, rng: random.Random) -> list[str]:
    """A batting order drawn one slot at a time, each kid's chance leaning on
    what they have had. A kid who usually bats late is likelier to be handed an
    early slot, and one who has already led off or batted last is less likely
    to get that slot again, but nobody's slot is ever fixed: that is what stops
    next week's order being something a parent could work out from this one's.
    At 0 it is a plain shuffle."""
    n = len(present)
    if n < 2:
        return list(present)
    lean = max(0, min(100, fairness)) / 100
    hist = {p: _mean_bat(stats.get(p)) for p in present}
    firsts = {p: (stats.get(p) or {}).get("bat_first", 0) for p in present}
    lasts = {p: (stats.get(p) or {}).get("bat_last", 0) for p in present}
    left = present[:]
    order: list[str] = []
    for slot in range(n):
        x = slot / (n - 1)
        weights = []
        for p in left:
            # Positive for a late batter in an early slot, and the other way round.
            w = math.exp(BAT_LEAN * lean * (hist[p] - 0.5) * (1 - 2 * x))
            if slot == 0:
                w *= math.exp(-EDGE_LEAN * lean * firsts[p])
            elif slot == n - 1:
                w *= math.exp(-EDGE_LEAN * lean * lasts[p])
            weights.append(w)
        pick = rng.choices(left, weights=weights, k=1)[0]
        order.append(pick)
        left.remove(pick)
    return order


def _pick_rests(present: list[str], rest_count: int, running: dict, fairness: int,
                rng: random.Random) -> set[str]:
    """Who sits this field change out: the kids who have sat out least."""
    if rest_count <= 0:
        return set()
    if rest_count >= len(present):
        return set(present)

    def cost(group: Iterable[str]) -> float:
        return sum(running[p]["rests"] for p in group)

    best: Optional[list[str]] = None
    best_cost = 0.0
    for _ in range(_candidates(fairness)):
        cand = rng.sample(present, rest_count)
        c = cost(cand)
        if best is None or c < best_cost - 1e-12:
            best, best_cost = cand, c
    assert best is not None
    chosen = set(best)
    for _ in range(_passes(fairness)):
        improved = False
        for out_p in sorted(chosen):
            for in_p in present:
                if in_p in chosen:
                    continue
                if running[in_p]["rests"] < running[out_p]["rests"]:
                    chosen.discard(out_p)
                    chosen.add(in_p)
                    improved = True
                    break
        if not improved:
            break
    return chosen


def _assign(fielders: list[str], positions: list[dict], running: dict, avoid: dict,
            fairness: int, rng: random.Random) -> dict[str, Optional[str]]:
    """Fielders onto positions with the least repeats. Fewer fielders than
    positions leaves the non-key ones empty first."""
    pos_ids = [p["id"] for p in positions]
    weight = {p["id"]: (KEY_WEIGHT if p.get("key") else 1) for p in positions}
    if len(fielders) < len(pos_ids):
        # Keep key positions; drop the rest at random until it fits.
        droppable = [pid for pid in pos_ids if weight[pid] == 1]
        rng.shuffle(droppable)
        keep = set(pos_ids)
        for pid in droppable:
            if len(keep) <= len(fielders):
                break
            keep.discard(pid)
        extra = [pid for pid in pos_ids if pid in keep and weight[pid] > 1]
        rng.shuffle(extra)
        while len(keep) > len(fielders) and extra:
            keep.discard(extra.pop())
        pos_ids = [pid for pid in pos_ids if pid in keep]

    key_pos = {p["id"] for p in positions if p.get("key")}
    key_turns = {p: sum(c for pos, c in running[p]["field"].items() if pos in key_pos) for p in fielders}

    def cell(p: str, pos: str) -> float:
        c = running[p]["field"].get(pos, 0)
        v = weight[pos] * c * c
        if pos in key_pos:
            # Whoever has had the fewest turns in key positions overall gets
            # them first, not only whoever has not had this one.
            v += KEY_TOTAL_WEIGHT * key_turns[p]
        if pos in avoid.get(p, ()):
            v += AVOID_PENALTY
        return v

    def cost(perm: list[str]) -> float:
        return sum(cell(p, pos) for p, pos in zip(perm, pos_ids))

    best: Optional[list[str]] = None
    best_cost = 0.0
    for _ in range(_candidates(fairness)):
        cand = fielders[:]
        rng.shuffle(cand)
        cand = cand[:len(pos_ids)]
        c = cost(cand)
        if best is None or c < best_cost - 1e-12:
            best, best_cost = cand, c
    assert best is not None
    for _ in range(_passes(fairness)):
        improved = False
        for i in range(len(best)):
            for j in range(i + 1, len(best)):
                best[i], best[j] = best[j], best[i]
                c = cost(best)
                if c < best_cost - 1e-12:
                    best_cost, improved = c, True
                else:
                    best[i], best[j] = best[j], best[i]
        if not improved:
            break
    out: dict[str, Optional[str]] = {p: None for p in fielders}
    out.update({p: pos for p, pos in zip(best, pos_ids)})
    return out


def generate(present: list[str], positions: list[dict], history: dict[str, dict], *,
             innings: int = 1, fairness: int = 60, bats: bool = True,
             avoid: Optional[dict[str, Iterable[str]]] = None,
             rng: Optional[random.Random] = None) -> dict:
    """A batting order and the field for each change, plus plain-words warnings.

    ``history`` is ``history_stats`` of the locked rounds so far. Changes within
    the game build on each other (somebody who rested in the first is not the
    one to rest in the second), without touching ``history``.
    """
    rng = rng or random.Random()
    present = [str(p) for p in dict.fromkeys(present)]
    avoid_sets = {str(k): set(v) for k, v in (avoid or {}).items()}
    running = {p: _copy_stat(history.get(p)) for p in present}
    order = _batting(present, history, fairness, rng) if bats else []
    fielding: list[dict] = []
    n_pos = len(positions)
    if positions and present:
        for change in range(max(1, min(int(innings or 1), 6))):
            rest_n = max(0, len(present) - n_pos)
            resting = _pick_rests(present, rest_n, running, fairness, rng)
            fielders = [p for p in present if p not in resting]
            assigned = _assign(fielders, positions, running, avoid_sets, fairness, rng)
            row: dict[str, Optional[str]] = {p: None for p in present}
            row.update(assigned)
            fielding.append(row)
            for p, pos in row.items():
                if pos is None:
                    running[p]["rests"] += 1
                else:
                    running[p]["field"][pos] = running[p]["field"].get(pos, 0) + 1
    return {
        "batting_order": order,
        "fielding": fielding,
        "warnings": round_warnings(positions, fielding, avoid_sets),
    }


def round_warnings(positions: list[dict], fielding: list[dict],
                   avoid: Optional[dict[str, Iterable[str]]] = None) -> list[str]:
    """Plain-words problems with a field, for a generated round and for a hand
    edit alike: a position nobody is on, and a kid put where they are to be kept
    out of. Silence when there is nothing wrong."""
    names = {p["id"]: p["name"] for p in positions}
    avoid_sets = {str(k): set(v) for k, v in (avoid or {}).items()}
    out: list[str] = []
    for i, change in enumerate(fielding or []):
        suffix = f" (change {i + 1})" if len(fielding) > 1 else ""
        used = {v for v in (change or {}).values() if v}
        empty = [p["name"] for p in positions if p["id"] not in used]
        if empty and change:
            out.append(f"Nobody on: {', '.join(empty)}{suffix}.")
        for pid, pos in (change or {}).items():
            if pos and pos in avoid_sets.get(str(pid), ()):
                out.append(f"A player is in {names.get(pos, 'a position')}, which they are meant to avoid{suffix}.")
    return list(dict.fromkeys(out))


def _copy_stat(stat: Optional[dict]) -> dict:
    base = _blank_stat()
    if stat:
        base["rests"] = stat.get("rests", 0)
        base["field"] = dict(stat.get("field") or {})
    return base


# ─── Tally ──────────────────────────────────────────────────────────────────

def tally(players: list[dict], positions: list[dict], rounds: list[dict]) -> dict:
    """The season table: per player, games, how they bat and where they have
    fielded, from locked rounds only. ``spread`` names the biggest gap between
    two kids so the screen can say whether it is even."""
    stats = history_stats(rounds)
    rows = []
    for pl in players:
        st = stats.get(pl["id"]) or _blank_stat()
        rows.append({
            "id": pl["id"],
            "name": pl["name"],
            "former": bool(pl.get("former_at")),
            "games": st["games"],
            "bat_first": st["bat_first"],
            "bat_last": st["bat_last"],
            "bat_avg": round(_mean_bat(st), 2) if st["bat_pcts"] else None,
            "rests": st["rests"],
            "field": {p["id"]: st["field"].get(p["id"], 0) for p in positions},
            "key_turns": sum(st["field"].get(p["id"], 0) for p in positions if p.get("key")),
        })
    live = [r for r in rows if not r["former"] and r["games"]]
    spread = None
    if len(live) > 1:
        keys = [r["key_turns"] for r in live]
        rests = [r["rests"] for r in live]
        spread = {"key_turns": max(keys) - min(keys), "rests": max(rests) - min(rests)}
    return {"players": rows, "rounds": len(rounds), "spread": spread}
