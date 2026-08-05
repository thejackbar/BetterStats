"""BetterClubManager Roster — the weekly volunteer roster and its rules engine.

Assignments are validated here (qualification, availability, overlap = blocks;
wrong role, over cap, heavy week = warnings). Everything else (coverage,
per-person load, candidate ranking) is derived on read. Raw SQL throughout, so
this subsystem stays out of the ORM/Alembic model graph (same posture as the
families router).
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
# The long form, because that is what volunteer_profiles.available_days stores
# and what a caller has to send back to filter on a day.
DOW_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# `volunteer_profiles.available_days` is written by two features that never
# agreed on a vocabulary. The Volunteers screen posts day NAMES (its API types
# the field `List[str]`), while the roster has always assumed Monday=0 integers
# — so a single "Monday" in a real club's data crashed the whole roster with
# `invalid literal for int() with base 10: 'Monday'`.
#
# Read-side tolerance rather than a migration: both writers are legitimate, the
# roster only ever needs the index, and an unrecognised value should cost that
# one day rather than the page.
_DAY_INDEX = {}
for _i, _abbr in enumerate(DOW):
    _full = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][_i]
    _DAY_INDEX[_abbr.lower()] = _i
    _DAY_INDEX[_full] = _i
    _DAY_INDEX[str(_i)] = _i


def day_index(value) -> Optional[int]:
    """A stored availability day as a Monday=0 index, or None if unreadable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= 6 else None
    return _DAY_INDEX.get(str(value).strip().lower())

DEFAULT_CAP = 3  # per-person weekly cap when a club/person hasn't set one


def _f(v):
    return float(v) if v is not None else None


# ── areas + patterns ────────────────────────────────────────────────────────
async def list_areas(db: AsyncSession, org_id) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT a.id, a.name, a.department, a.color, a.required_role_id, a.required_qualification_type_id,
               a.sort_order, a.is_active, r.title AS role_name, q.name AS qual_name
        FROM roster_areas a
        LEFT JOIN club_roles r ON r.id = a.required_role_id
        LEFT JOIN qualification_types q ON q.id = a.required_qualification_type_id
        WHERE a.organisation_id = :org AND a.is_active = TRUE
        ORDER BY a.sort_order, lower(a.name)
    """), {"org": org_id})).mappings().all()
    pats = (await db.execute(text("""
        SELECT id, area_id, day_of_week, start_time, end_time, headcount
        FROM roster_shift_patterns WHERE organisation_id = :org
        ORDER BY day_of_week, start_time
    """), {"org": org_id})).mappings().all()
    by_area = {}
    for p in pats:
        by_area.setdefault(str(p["area_id"]), []).append({
            "id": str(p["id"]), "day_of_week": p["day_of_week"],
            "start_time": _f(p["start_time"]), "end_time": _f(p["end_time"]), "headcount": p["headcount"],
        })
    return [{
        "id": str(a["id"]), "name": a["name"], "department": a["department"], "color": a["color"],
        "required_role_id": str(a["required_role_id"]) if a["required_role_id"] else None,
        "required_role_name": a["role_name"],
        "required_qualification_type_id": str(a["required_qualification_type_id"]) if a["required_qualification_type_id"] else None,
        "required_qualification_name": a["qual_name"],
        "sort_order": a["sort_order"], "is_active": a["is_active"],
        "patterns": by_area.get(str(a["id"]), []),
    } for a in rows]


async def create_area(db: AsyncSession, org_id, *, name, department=None, color=None,
                      required_role_id=None, required_qualification_type_id=None) -> str:
    aid = uuid.uuid4()
    n = (await db.execute(text("SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM roster_areas WHERE organisation_id=:org"), {"org": org_id})).scalar() or 1
    await db.execute(text("""
        INSERT INTO roster_areas (id, organisation_id, name, department, color, required_role_id, required_qualification_type_id, sort_order)
        VALUES (:id, :org, :name, :dept, :color, :role, :qual, :sort)
    """), {"id": aid, "org": org_id, "name": name, "dept": department, "color": color,
           "role": required_role_id, "qual": required_qualification_type_id, "sort": n})
    return str(aid)


async def update_area(db: AsyncSession, org_id, area_id, **fields) -> None:
    cols = {"name": "name", "department": "department", "color": "color",
            "required_role_id": "required_role_id", "required_qualification_type_id": "required_qualification_type_id",
            "sort_order": "sort_order"}
    sets, params = [], {"id": area_id, "org": org_id}
    for k, col in cols.items():
        if k in fields:
            sets.append(f"{col} = :{k}")
            params[k] = fields[k]
    if not sets:
        return
    await db.execute(text(f"UPDATE roster_areas SET {', '.join(sets)} WHERE id=:id AND organisation_id=:org"), params)


async def delete_area(db: AsyncSession, org_id, area_id) -> None:
    await db.execute(text("UPDATE roster_areas SET is_active=FALSE WHERE id=:id AND organisation_id=:org"), {"id": area_id, "org": org_id})


async def reorder_areas(db: AsyncSession, org_id, area_ids) -> None:
    for i, aid in enumerate(area_ids):
        await db.execute(text("UPDATE roster_areas SET sort_order=:i WHERE id=:id AND organisation_id=:org"), {"i": i, "id": aid, "org": org_id})


# ── departments (a managed catalogue that feeds the area form's dropdown) ─────
STARTER_DEPARTMENTS = [
    "Cricket Operations", "Food & Beverage", "Grounds & Facilities",
    "Committee & Administration", "Coaching & Development", "Events & Fundraising",
]


async def list_departments(db: AsyncSession, org_id) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT id, name, sort_order, is_active FROM roster_departments
        WHERE organisation_id = :org AND is_active = TRUE
        ORDER BY sort_order, lower(name)
    """), {"org": org_id})).mappings().all()
    return [{"id": str(r["id"]), "name": r["name"], "sort_order": r["sort_order"], "is_active": r["is_active"]} for r in rows]


async def create_department(db: AsyncSession, org_id, *, name) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Name is required")
    # Reactivate an archived same-named department rather than colliding on the
    # unique (org, name) index; otherwise create fresh at the end of the order.
    existing = (await db.execute(text(
        "SELECT id, is_active FROM roster_departments WHERE organisation_id=:org AND lower(name)=lower(:name)"
    ), {"org": org_id, "name": name})).mappings().first()
    if existing is not None:
        if not existing["is_active"]:
            await db.execute(text("UPDATE roster_departments SET is_active=TRUE WHERE id=:id"), {"id": existing["id"]})
        return str(existing["id"])
    did = uuid.uuid4()
    n = (await db.execute(text("SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM roster_departments WHERE organisation_id=:org"), {"org": org_id})).scalar() or 1
    await db.execute(text("""
        INSERT INTO roster_departments (id, organisation_id, name, sort_order) VALUES (:id, :org, :name, :sort)
    """), {"id": did, "org": org_id, "name": name[:120], "sort": n})
    return str(did)


async def update_department(db: AsyncSession, org_id, dept_id, **fields) -> None:
    if "name" in fields and fields["name"] is not None:
        new_name = (fields["name"] or "").strip()
        if new_name:
            old = (await db.execute(text("SELECT name FROM roster_departments WHERE id=:id AND organisation_id=:org"), {"id": dept_id, "org": org_id})).scalar()
            await db.execute(text("UPDATE roster_departments SET name=:name WHERE id=:id AND organisation_id=:org"), {"name": new_name[:120], "id": dept_id, "org": org_id})
            # Cascade the rename onto areas that carry the old department text, so
            # the dropdown and the areas stay in step.
            if old and old != new_name:
                await db.execute(text("UPDATE roster_areas SET department=:new WHERE organisation_id=:org AND department=:old"), {"new": new_name, "old": old, "org": org_id})
    if "sort_order" in fields and fields["sort_order"] is not None:
        await db.execute(text("UPDATE roster_departments SET sort_order=:s WHERE id=:id AND organisation_id=:org"), {"s": fields["sort_order"], "id": dept_id, "org": org_id})


async def delete_department(db: AsyncSession, org_id, dept_id) -> None:
    # Archive the catalogue entry only; areas keep their department text (it just
    # becomes a value not currently in the catalogue).
    await db.execute(text("UPDATE roster_departments SET is_active=FALSE WHERE id=:id AND organisation_id=:org"), {"id": dept_id, "org": org_id})


async def reorder_departments(db: AsyncSession, org_id, dept_ids) -> None:
    for i, did in enumerate(dept_ids):
        await db.execute(text("UPDATE roster_departments SET sort_order=:i WHERE id=:id AND organisation_id=:org"), {"i": i, "id": did, "org": org_id})


async def seed_starter_departments(db: AsyncSession, org_id) -> int:
    """Seed the starter departments plus any department names already in use on
    this club's areas. Reactivates an archived match; skips an active one."""
    existing = {r["name"].lower(): r for r in (await db.execute(text(
        "SELECT id, name, is_active FROM roster_departments WHERE organisation_id=:org"
    ), {"org": org_id})).mappings().all()}
    in_use = [r for r in (await db.execute(text(
        "SELECT DISTINCT department FROM roster_areas WHERE organisation_id=:org AND is_active=TRUE AND department IS NOT NULL AND department <> ''"
    ), {"org": org_id})).scalars().all()]
    names = list(STARTER_DEPARTMENTS)
    for d in in_use:
        if d.lower() not in {n.lower() for n in names}:
            names.append(d)
    seeded = 0
    start = (await db.execute(text("SELECT COALESCE(MAX(sort_order),0) FROM roster_departments WHERE organisation_id=:org"), {"org": org_id})).scalar() or 0
    for name in names:
        cur = existing.get(name.lower())
        if cur is not None:
            if not cur["is_active"]:
                await db.execute(text("UPDATE roster_departments SET is_active=TRUE WHERE id=:id"), {"id": cur["id"]})
                seeded += 1
            continue
        start += 1
        await db.execute(text("""
            INSERT INTO roster_departments (id, organisation_id, name, sort_order) VALUES (:id, :org, :name, :sort)
        """), {"id": uuid.uuid4(), "org": org_id, "name": name, "sort": start})
        seeded += 1
    return seeded


async def add_pattern(db: AsyncSession, org_id, area_id, *, day_of_week, start_time, end_time, headcount=1) -> str:
    pid = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO roster_shift_patterns (id, organisation_id, area_id, day_of_week, start_time, end_time, headcount)
        VALUES (:id, :org, :area, :dow, :start, :end, :hc)
    """), {"id": pid, "org": org_id, "area": area_id, "dow": day_of_week, "start": start_time, "end": end_time, "hc": headcount})
    return str(pid)


async def delete_pattern(db: AsyncSession, org_id, pattern_id) -> None:
    await db.execute(text("DELETE FROM roster_shift_patterns WHERE id=:id AND organisation_id=:org"), {"id": pattern_id, "org": org_id})


# ── settings ────────────────────────────────────────────────────────────────
async def get_settings(db: AsyncSession, org_id) -> dict:
    row = (await db.execute(text("SELECT enforce_qualifications, weekly_shift_cap FROM roster_settings WHERE organisation_id=:org"), {"org": org_id})).mappings().first()
    if not row:
        return {"enforce_qualifications": True, "weekly_shift_cap": 0}
    return {"enforce_qualifications": row["enforce_qualifications"], "weekly_shift_cap": row["weekly_shift_cap"]}


async def set_settings(db: AsyncSession, org_id, *, enforce_qualifications=None, weekly_shift_cap=None) -> dict:
    cur = await get_settings(db, org_id)
    eq = cur["enforce_qualifications"] if enforce_qualifications is None else bool(enforce_qualifications)
    cap = cur["weekly_shift_cap"] if weekly_shift_cap is None else int(weekly_shift_cap)
    await db.execute(text("""
        INSERT INTO roster_settings (organisation_id, enforce_qualifications, weekly_shift_cap, updated_at)
        VALUES (:org, :eq, :cap, NOW())
        ON CONFLICT (organisation_id) DO UPDATE SET enforce_qualifications=:eq, weekly_shift_cap=:cap, updated_at=NOW()
    """), {"org": org_id, "eq": eq, "cap": cap})
    return {"enforce_qualifications": eq, "weekly_shift_cap": cap}


# ── candidates (volunteers) ─────────────────────────────────────────────────
async def candidates(db: AsyncSession, org_id) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT vp.member_id, fm.full_name, vp.available_days, vp.max_shifts_per_week, fm.player_id
        FROM volunteer_profiles vp JOIN fee_members fm ON fm.id = vp.member_id
        WHERE vp.organisation_id = :org
        ORDER BY lower(fm.full_name)
    """), {"org": org_id})).mappings().all()
    role_rows = (await db.execute(text("SELECT member_id, role_id FROM volunteer_roles WHERE organisation_id=:org"), {"org": org_id})).mappings().all()
    qual_rows = (await db.execute(text("""
        SELECT member_id, qualification_type_id FROM member_qualifications
        WHERE organisation_id=:org AND (expires_at IS NULL OR expires_at >= CURRENT_DATE)
    """), {"org": org_id})).mappings().all()
    roles_by = {}
    for r in role_rows:
        roles_by.setdefault(str(r["member_id"]), set()).add(str(r["role_id"]))
    quals_by = {}
    for q in qual_rows:
        quals_by.setdefault(str(q["member_id"]), set()).add(str(q["qualification_type_id"]))
    out = []
    for r in rows:
        mid = str(r["member_id"])
        out.append({
            "member_id": mid, "name": r["full_name"],
            "available_days": [d for d in (day_index(x) for x in (r["available_days"] or [])) if d is not None],
            "max_shifts": r["max_shifts_per_week"],
            "player_id": str(r["player_id"]) if r["player_id"] else None,
            "role_ids": roles_by.get(mid, set()), "qual_type_ids": quals_by.get(mid, set()),
        })
    return out


# ── rules engine ────────────────────────────────────────────────────────────
def check_assignment(area: dict, shift: dict, cand: dict, week_shifts: list[dict], settings: dict) -> dict:
    blocks, warns = [], []
    cap = settings.get("weekly_shift_cap") or cand.get("max_shifts") or DEFAULT_CAP
    req_qual = area.get("required_qualification_type_id")
    if req_qual and req_qual not in cand["qual_type_ids"]:
        msg = "Missing " + (area.get("required_qualification_name") or "required qualification")
        (warns if settings.get("enforce_qualifications") is False else blocks).append(msg)
    if shift["day_of_week"] not in cand["available_days"]:
        blocks.append("Not available " + DOW[shift["day_of_week"]])
    mine = [s for s in week_shifts if s.get("assignee_member_id") == cand["member_id"] and s["id"] != shift["id"]]
    if any(s["day_of_week"] == shift["day_of_week"] and s["start_time"] < shift["end_time"] and shift["start_time"] < s["end_time"] for s in mine):
        blocks.append("Overlaps another shift")
    req_role = area.get("required_role_id")
    if req_role and req_role not in cand["role_ids"]:
        warns.append("Not in the " + (area.get("required_role_name") or "required") + " role")
    if len(mine) + 1 > cap:
        warns.append(f"Over their {cap}-shift weekly cap")
    if len(mine) + 1 >= 4:
        warns.append("Heavy week — spread the load")
    if cand.get("player_id"):
        # BetterSelect match clash: a Saturday daytime shift when they may be playing.
        if shift["day_of_week"] == 5 and shift["start_time"] < 18.5:
            warns.append("May be selected to play Saturday")
    return {"blocks": blocks, "warns": warns}


def _rank(shift, area, cands, week_shifts, settings):
    scored = []
    for c in cands:
        res = check_assignment(area, shift, c, week_shifts, settings)
        if res["blocks"]:
            continue
        load = len([s for s in week_shifts if s.get("assignee_member_id") == c["member_id"]])
        scored.append((res["warns"], load, c))
    scored.sort(key=lambda x: (len(x[0]) * 10 + x[1]))
    return scored


# ── weeks + shifts ──────────────────────────────────────────────────────────
def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def _shift_rows(db: AsyncSession, week_id) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT s.id, s.area_id, s.day_of_week, s.start_time, s.end_time, s.assignee_member_id, s.warnings,
               fm.full_name AS assignee_name
        FROM roster_shifts s LEFT JOIN fee_members fm ON fm.id = s.assignee_member_id
        WHERE s.roster_week_id = :wid
        ORDER BY s.day_of_week, s.start_time
    """), {"wid": week_id})).mappings().all()
    return [{
        "id": str(r["id"]), "area_id": str(r["area_id"]), "day_of_week": r["day_of_week"],
        "start_time": _f(r["start_time"]), "end_time": _f(r["end_time"]),
        "assignee_member_id": str(r["assignee_member_id"]) if r["assignee_member_id"] else None,
        "assignee_name": r["assignee_name"], "warnings": r["warnings"] or [],
    } for r in rows]


async def get_or_create_week(db: AsyncSession, org_id, week_start: date) -> dict:
    ws = _monday(week_start)
    row = (await db.execute(text("SELECT id, status FROM roster_weeks WHERE organisation_id=:org AND week_start=:ws"), {"org": org_id, "ws": ws})).mappings().first()
    if row:
        wid, status = row["id"], row["status"]
        # A week created BEFORE the club configured any operational areas has no
        # shifts, and nothing regenerated it — every later visit found the empty
        # week row and returned it, so the roster stayed blank forever. Fill a
        # week that is still genuinely empty. It can never duplicate a roster in
        # progress, because a week with any shift at all is left alone.
        if status == "draft" and not await _has_shifts(db, wid):
            await _generate_shifts(db, org_id, wid)
    else:
        wid = uuid.uuid4()
        await db.execute(text("INSERT INTO roster_weeks (id, organisation_id, week_start, status) VALUES (:id, :org, :ws, 'draft')"), {"id": wid, "org": org_id, "ws": ws})
        status = "draft"
        await _generate_shifts(db, org_id, wid)
    shifts = await _shift_rows(db, wid)
    return {"id": str(wid), "week_start": ws.isoformat(), "status": status, "shifts": shifts}


async def _has_shifts(db: AsyncSession, week_id) -> bool:
    return bool((await db.execute(
        text("SELECT 1 FROM roster_shifts WHERE roster_week_id = :wid LIMIT 1"), {"wid": week_id}
    )).first())


async def _generate_shifts(db: AsyncSession, org_id, week_id) -> None:
    pats = (await db.execute(text("""
        SELECT p.area_id, p.day_of_week, p.start_time, p.end_time, p.headcount
        FROM roster_shift_patterns p JOIN roster_areas a ON a.id = p.area_id
        WHERE p.organisation_id = :org AND a.is_active = TRUE
    """), {"org": org_id})).mappings().all()
    for p in pats:
        for _ in range(int(p["headcount"] or 1)):
            await db.execute(text("""
                INSERT INTO roster_shifts (id, roster_week_id, organisation_id, area_id, day_of_week, start_time, end_time)
                VALUES (:id, :wid, :org, :area, :dow, :start, :end)
            """), {"id": uuid.uuid4(), "wid": week_id, "org": org_id, "area": p["area_id"],
                   "dow": p["day_of_week"], "start": p["start_time"], "end": p["end_time"]})


async def _week_context(db: AsyncSession, org_id, week_id):
    areas = {a["id"]: a for a in await list_areas(db, org_id)}
    cands = await candidates(db, org_id)
    cand_by = {c["member_id"]: c for c in cands}
    settings = await get_settings(db, org_id)
    shifts = await _shift_rows(db, week_id)
    return areas, cands, cand_by, settings, shifts


async def assign(db: AsyncSession, org_id, week_id, shift_id, member_id) -> dict:
    areas, cands, cand_by, settings, shifts = await _week_context(db, org_id, week_id)
    shift = next((s for s in shifts if s["id"] == shift_id), None)
    if not shift:
        return {"ok": False, "blocks": ["Shift not found"], "warns": []}
    if not member_id:
        await db.execute(text("UPDATE roster_shifts SET assignee_member_id=NULL, warnings='[]'::jsonb WHERE id=:id AND organisation_id=:org"), {"id": shift_id, "org": org_id})
        return {"ok": True, "cleared": True, "shift_id": shift_id}
    cand = cand_by.get(member_id)
    area = areas.get(shift["area_id"])
    if not cand or not area:
        return {"ok": False, "blocks": ["Unknown volunteer or area"], "warns": []}
    res = check_assignment(area, shift, cand, shifts, settings)
    if res["blocks"]:
        return {"ok": False, "blocks": res["blocks"], "warns": []}
    import json
    await db.execute(text("UPDATE roster_shifts SET assignee_member_id=:m, warnings=CAST(:w AS jsonb) WHERE id=:id AND organisation_id=:org"),
                     {"m": member_id, "w": json.dumps(res["warns"]), "id": shift_id, "org": org_id})
    return {"ok": True, "shift_id": shift_id, "assignee_member_id": member_id, "assignee_name": cand["name"], "warns": res["warns"]}


async def autofill(db: AsyncSession, org_id, week_id) -> dict:
    import json
    areas, cands, cand_by, settings, shifts = await _week_context(db, org_id, week_id)
    placed = 0
    for shift in shifts:
        if shift["assignee_member_id"]:
            continue
        area = areas.get(shift["area_id"])
        if not area:
            continue
        ranked = _rank(shift, area, cands, shifts, settings)
        best = next((x for x in ranked if not x[0]), None) or (ranked[0] if ranked else None)
        if best:
            warns, _load, c = best
            await db.execute(text("UPDATE roster_shifts SET assignee_member_id=:m, warnings=CAST(:w AS jsonb) WHERE id=:id"),
                             {"m": c["member_id"], "w": json.dumps(warns), "id": shift["id"]})
            shift["assignee_member_id"] = c["member_id"]  # so subsequent ranks see the load
            placed += 1
    remaining = len([s for s in await _shift_rows(db, week_id) if not s["assignee_member_id"]])
    return {"placed": placed, "remaining": remaining}


async def publish(db: AsyncSession, org_id, week_id) -> dict:
    await db.execute(text("UPDATE roster_weeks SET status='published' WHERE id=:id AND organisation_id=:org"), {"id": week_id, "org": org_id})
    open_count = len([s for s in await _shift_rows(db, week_id) if not s["assignee_member_id"]])
    return {"status": "published", "open": open_count}


async def clear_config(db: AsyncSession, org_id) -> None:
    """Testing reset: remove all roster config for this club — areas, patterns
    and every week/shift. Scoped strictly to the acting-as club; touches nothing
    else (players, members, committee, etc. are untouched)."""
    await db.execute(text("DELETE FROM roster_weeks WHERE organisation_id=:org"), {"org": org_id})  # cascades shifts
    await db.execute(text("DELETE FROM roster_shift_patterns WHERE organisation_id=:org"), {"org": org_id})
    await db.execute(text("DELETE FROM roster_areas WHERE organisation_id=:org"), {"org": org_id})


async def reset_week(db: AsyncSession, org_id, week_id) -> None:
    """Clear all shifts for the week and regenerate them from the current
    patterns (drops every assignment). Scoped to this club's own week."""
    await db.execute(text("DELETE FROM roster_shifts WHERE roster_week_id=:id AND organisation_id=:org"), {"id": week_id, "org": org_id})
    await db.execute(text("UPDATE roster_weeks SET status='draft' WHERE id=:id AND organisation_id=:org"), {"id": week_id, "org": org_id})
    await _generate_shifts(db, org_id, week_id)


# Default starter areas so a club can see the roster populate immediately. Roles
# and qualifications are matched to the club's existing catalogue by name where
# they exist, else left unlinked for the admin to wire up. [day,start,end,count]
STARTER_AREAS = [
    {"name": "Bar", "department": "Food & Beverage", "color": "#f5b542", "role": "Bar Supervisor", "qual": "RSA",
     "patterns": [[1, 17, 21, 1], [3, 17, 22, 2], [5, 12, 24, 2], [6, 12, 24, 2]]},
    {"name": "Kitchen", "department": "Food & Beverage", "color": "#f97316", "role": "Canteen", "qual": "Food Handling",
     "patterns": [[3, 18, 20, 2], [5, 18, 20, 1], [6, 16, 20, 1]]},
    {"name": "Umpires", "department": "Cricket Operations", "color": "#3b82f6", "role": "Umpire", "qual": "Umpire Accreditation",
     "patterns": [[5, 12, 18.5, 4], [6, 12, 18.5, 4]]},
    {"name": "Scorer", "department": "Cricket Operations", "color": "#06b6d4", "role": "Scorer", "qual": None,
     "patterns": [[5, 12, 18.5, 4], [6, 12, 18.5, 4]]},
    {"name": "Groundsman", "department": "Cricket Operations", "color": "#16c784", "role": "Groundsman", "qual": None,
     "patterns": [[0, 12, 15, 1], [5, 9, 10, 1], [6, 9, 10, 1]]},
]


async def seed_starter_areas(db: AsyncSession, org_id) -> int:
    existing = (await db.execute(text("SELECT COUNT(*) FROM roster_areas WHERE organisation_id=:org AND is_active=TRUE"), {"org": org_id})).scalar()
    if existing:
        return 0
    roles = {r["title"].lower(): str(r["id"]) for r in (await db.execute(text("SELECT id, title FROM club_roles WHERE organisation_id=:org AND is_active=TRUE"), {"org": org_id})).mappings().all()}
    quals = {q["name"].lower(): str(q["id"]) for q in (await db.execute(text("SELECT id, name FROM qualification_types WHERE organisation_id=:org AND is_active=TRUE"), {"org": org_id})).mappings().all()}
    # Also lay down the full Departments Starter Pack (idempotent), so the area
    # form's dropdown is populated and the areas below link to real catalogue
    # entries — same as Roles seeding the full Role Types pack.
    await seed_starter_departments(db, org_id)
    seeded = 0
    for a in STARTER_AREAS:
        aid = await create_area(db, org_id, name=a["name"], department=a["department"], color=a["color"],
                                required_role_id=roles.get((a["role"] or "").lower()),
                                required_qualification_type_id=quals.get((a["qual"] or "").lower()))
        for p in a["patterns"]:
            await add_pattern(db, org_id, aid, day_of_week=p[0], start_time=p[1], end_time=p[2], headcount=p[3])
        seeded += 1
    return seeded


async def rostered_contacts(db: AsyncSession, org_id, start: date, end: date) -> dict:
    """Everyone rostered on between two dates, with the email contact behind
    them where there is one.

    A shift's date is its week's Monday plus its day_of_week — shifts store the
    day, not a date, so the window has to be applied to the derived date rather
    than to a column. `end` is inclusive: an officer asking for "this week"
    means Monday to Sunday, not Monday to Saturday.
    """
    rows = (await db.execute(text("""
        SELECT DISTINCT fm.id AS member_id, fm.full_name, fm.player_id, c.id AS contact_id, c.email
        FROM roster_shifts s
        JOIN roster_weeks w ON w.id = s.roster_week_id
        JOIN fee_members fm ON fm.id = s.assignee_member_id
        LEFT JOIN comms_contacts c ON c.player_id = fm.player_id AND c.organisation_id = :org
        WHERE s.organisation_id = :org
          AND s.assignee_member_id IS NOT NULL
          AND (w.week_start + s.day_of_week) BETWEEN :start AND :end
        ORDER BY fm.full_name
    """), {"org": org_id, "start": start, "end": end})).mappings().all()

    people = [{
        "member_id": str(r["member_id"]), "full_name": r["full_name"],
        "contact_id": str(r["contact_id"]) if r["contact_id"] else None,
        "email": r["email"],
    } for r in rows]
    return {
        "from": start.isoformat(), "to": end.isoformat(),
        "people": people,
        # What the composer needs to be handed a ready-made recipient set.
        "contact_ids": [p["contact_id"] for p in people if p["contact_id"]],
        "unreachable": [p["full_name"] for p in people if not p["contact_id"]],
    }


# ── Shifts as first-class things ─────────────────────────────────────────────
#
# Shifts were only ever generated from an area's weekly patterns, so a one-off
# — a night game, an extra bar shift for a final — could not be added, and a
# shift generated in error could not be removed. These make a shift editable in
# its own right without touching the pattern it came from.

async def create_shift(db: AsyncSession, org_id, week_id, *, area_id, day_of_week,
                       start_time, end_time) -> str:
    sid = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO roster_shifts (id, roster_week_id, organisation_id, area_id, day_of_week, start_time, end_time)
        VALUES (:id, :wid, :org, :area, :dow, :st, :et)
    """), {"id": sid, "wid": week_id, "org": org_id, "area": area_id,
           "dow": int(day_of_week), "st": start_time, "et": end_time})
    return str(sid)


async def update_shift(db: AsyncSession, org_id, shift_id, **fields) -> None:
    cols = {"area_id": "area_id", "day_of_week": "day_of_week",
            "start_time": "start_time", "end_time": "end_time"}
    sets, params = [], {"id": shift_id, "org": org_id}
    for k, col in cols.items():
        if k in fields and fields[k] is not None:
            sets.append(f"{col} = :{k}")
            params[k] = fields[k]
    if not sets:
        return
    await db.execute(text(
        f"UPDATE roster_shifts SET {', '.join(sets)} WHERE id = :id AND organisation_id = :org"
    ), params)


async def delete_shift(db: AsyncSession, org_id, shift_id) -> None:
    await db.execute(text("DELETE FROM roster_shifts WHERE id = :id AND organisation_id = :org"),
                     {"id": shift_id, "org": org_id})


# ── Paid vs volunteer ────────────────────────────────────────────────────────
#
# A club's roster mixes people it employs with people doing it for nothing, and
# until now it could not tell them apart. The distinction is NOT a new flag: an
# area already requires a club_role, and a role already has a type whose
# category can be 'paid'. Deriving it keeps one answer instead of two that can
# disagree.

PAID_CATEGORY = "paid"


async def area_pay_kinds(db: AsyncSession, org_id) -> dict:
    """area_id -> True when that area's required role is a paid one."""
    rows = (await db.execute(text("""
        SELECT a.id, COALESCE(rt.category, '') AS category
        FROM roster_areas a
        LEFT JOIN club_roles r ON r.id = a.required_role_id
        LEFT JOIN club_role_types rt ON rt.id = r.role_type_id
        WHERE a.organisation_id = :org
    """), {"org": org_id})).mappings().all()
    return {str(r["id"]): (r["category"] or "").lower() == PAID_CATEGORY for r in rows}


def shift_hours(start_time, end_time) -> float:
    """A shift's length. Times are stored as decimal hours (17.5 = 5:30pm)."""
    try:
        return max(0.0, float(end_time) - float(start_time))
    except (TypeError, ValueError):
        return 0.0


async def confirm_review(db: AsyncSession, org_id, week_id) -> dict:
    """Every filled shift in the week, ready to be checked and confirmed.

    ``worked_hours`` on the shift is what the reviewer has adjusted it to;
    until they touch it, the rostered length is what will be posted. Whether
    the hours are paid comes from the area's role type, decided now rather than
    read from an earlier posting, so retyping a role before confirming is picked
    up. ``posted`` says the ledger already carries this shift, which is what
    makes confirming a corrected week a correction and not a second copy.
    """
    week = (await db.execute(text("""
        SELECT id, week_start, status, confirmed_at FROM roster_weeks
        WHERE id = :id AND organisation_id = :org
    """), {"id": week_id, "org": org_id})).mappings().first()
    if not week:
        return {"week": None, "rows": [], "totals": {}}

    paid_by_area = await area_pay_kinds(db, org_id)
    rows = (await db.execute(text("""
        SELECT s.id, s.area_id, s.day_of_week, s.start_time, s.end_time, s.worked_hours,
               s.assignee_member_id, m.full_name, a.name AS area_name, a.color,
               (h.id IS NOT NULL) AS posted
        FROM roster_shifts s
        JOIN fee_members m ON m.id = s.assignee_member_id
        JOIN roster_areas a ON a.id = s.area_id
        LEFT JOIN volunteer_hours h ON h.roster_shift_id = s.id
        WHERE s.roster_week_id = :wid AND s.organisation_id = :org
        ORDER BY s.day_of_week, s.start_time, a.name
    """), {"wid": week_id, "org": org_id})).mappings().all()

    out, totals = [], {"rostered": 0.0, "worked": 0.0, "worked_paid": 0.0, "worked_volunteer": 0.0}
    for r in rows:
        rostered = shift_hours(r["start_time"], r["end_time"])
        reviewed = r["worked_hours"] is not None
        worked = float(r["worked_hours"]) if reviewed else rostered
        is_paid = paid_by_area.get(str(r["area_id"]), False)
        out.append({
            "shift_id": str(r["id"]), "member_id": str(r["assignee_member_id"]),
            "full_name": r["full_name"], "area_name": r["area_name"], "color": r["color"],
            "day_of_week": r["day_of_week"], "start_time": _f(r["start_time"]), "end_time": _f(r["end_time"]),
            "rostered_hours": round(rostered, 2), "worked_hours": round(worked, 2),
            "reviewed": reviewed, "is_paid": is_paid, "posted": bool(r["posted"]),
        })
        totals["rostered"] += rostered
        totals["worked"] += worked
        totals["worked_paid" if is_paid else "worked_volunteer"] += worked

    return {
        "week": {"id": str(week["id"]), "week_start": week["week_start"].isoformat(),
                 "status": week["status"],
                 "confirmed_at": week["confirmed_at"].isoformat() if week["confirmed_at"] else None},
        "rows": out,
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "open_shifts": (await db.execute(text("""
            SELECT COUNT(*) FROM roster_shifts
            WHERE roster_week_id = :wid AND assignee_member_id IS NULL
        """), {"wid": week_id})).scalar() or 0,
    }


async def set_worked_hours(db: AsyncSession, org_id, week_id, entries: list) -> int:
    """Record the checker's adjustments without confirming the roster.

    Saved separately from confirming so a half-finished check survives someone
    walking away from it. Scoped to the week AND the club, since the shift ids
    come from a browser.
    """
    n = 0
    for e in entries or []:
        hours = e.get("hours")
        if hours is None:
            continue
        res = await db.execute(text("""
            UPDATE roster_shifts SET worked_hours = :h
            WHERE id = :id AND roster_week_id = :wid AND organisation_id = :org
        """), {"h": max(0.0, min(24.0, float(hours))), "id": e["shift_id"], "wid": week_id, "org": org_id})
        n += res.rowcount or 0
    return n


async def confirm_roster(db: AsyncSession, org_id, week_id, *, user_id=None, entries=None) -> dict:
    """Confirm the roster: post every filled shift's hours to the ledger.

    Reconciles rather than appends. A shift that has since been unassigned, or
    reviewed down to zero hours, has its posted row REMOVED — otherwise
    correcting a mistake would leave the original behind and the ledger would
    only ever grow. ``is_paid`` is stamped from the role type as it stands at
    confirmation, and never revisited afterwards (migration 221's note).
    """
    if entries:
        await set_worked_hours(db, org_id, week_id, entries)

    review = await confirm_review(db, org_id, week_id)
    if not review["week"]:
        return {"ok": False, "error": "Week not found"}

    week_start = date.fromisoformat(review["week"]["week_start"])
    keep, posted, removed = set(), 0, 0
    for r in review["rows"]:
        if r["worked_hours"] <= 0:
            continue        # rostered but did not work: nothing to post
        keep.add(r["shift_id"])
        logged = week_start + timedelta(days=int(r["day_of_week"]))
        await db.execute(text("""
            INSERT INTO volunteer_hours
                (id, organisation_id, member_id, logged_date, hours, activity, is_paid, roster_shift_id, created_by_user_id)
            VALUES (:id, :org, :member, :logged, :hours, :activity, :paid, :shift, :user)
            ON CONFLICT (roster_shift_id) WHERE roster_shift_id IS NOT NULL
            DO UPDATE SET hours = EXCLUDED.hours, is_paid = EXCLUDED.is_paid,
                          member_id = EXCLUDED.member_id, logged_date = EXCLUDED.logged_date,
                          activity = EXCLUDED.activity
        """), {"id": uuid.uuid4(), "org": org_id, "member": r["member_id"], "logged": logged,
               "hours": r["worked_hours"], "activity": r["area_name"], "paid": r["is_paid"],
               "shift": r["shift_id"], "user": user_id})
        posted += 1

    # Anything this week previously posted that no longer earns hours: a shift
    # since unassigned, or reviewed down to zero. Resolved in Python rather than
    # binding an id array, so an empty keep set behaves like any other.
    stale = [str(r["id"]) for r in (await db.execute(text("""
        SELECT h.id, h.roster_shift_id FROM volunteer_hours h
        JOIN roster_shifts s ON s.id = h.roster_shift_id
        WHERE s.roster_week_id = :wid AND h.organisation_id = :org
    """), {"wid": week_id, "org": org_id})).mappings().all()
        if str(r["roster_shift_id"]) not in keep]
    for hid in stale:
        await db.execute(text("DELETE FROM volunteer_hours WHERE id = :id"), {"id": hid})
    removed = len(stale)

    await db.execute(text("""
        UPDATE roster_weeks SET status='confirmed', confirmed_at=NOW(), confirmed_by_user_id=:user
        WHERE id=:id AND organisation_id=:org
    """), {"id": week_id, "org": org_id, "user": user_id})
    return {"ok": True, "posted": posted, "removed": removed,
            "totals": review["totals"], "status": "confirmed"}


async def unconfirm_roster(db: AsyncSession, org_id, week_id) -> dict:
    """Let a confirmed roster be edited again.

    Deliberately leaves the posted hours alone: they were worked, and deleting
    them because someone wants to fix a typo would take the club's ledger down
    with the correction. Confirming again reconciles.
    """
    await db.execute(text("""
        UPDATE roster_weeks SET status='published', confirmed_at=NULL, confirmed_by_user_id=NULL
        WHERE id=:id AND organisation_id=:org
    """), {"id": week_id, "org": org_id})
    return {"ok": True, "status": "published"}


async def role_shortages(db: AsyncSession, org_id, *, weeks: int = 4) -> dict:
    """Which roles the club is short of, read from the shifts nobody has filled.

    Demand is the unfilled shifts in the weeks ahead, resolved through their
    operational area to the role that area asks for. Supply is the people who
    hold that role AND are free on the day the shift falls.

    The day matters, and it is the whole point of the function. Six people hold
    the Scorer role is a comforting number that means nothing if all six are
    Sunday-only and every open Scorer shift is a Saturday — so the count that
    drives this is per (role, day), and a role reads as short when a day it is
    needed on has fewer free holders than open shifts.

    An area with no required role is reported separately rather than silently
    dropped: those shifts are open too, and "we need people, for nothing in
    particular" is a different conversation from "we need two more scorers".
    """
    today = date.today()
    horizon = today + timedelta(weeks=max(1, min(weeks, 26)))

    # Demand. Only shifts that are actually in the future — an unfilled shift
    # from last Tuesday is a fact about the past, not something to recruit for.
    open_rows = (await db.execute(text("""
        SELECT s.day_of_week, s.start_time, s.end_time,
               a.id AS area_id, a.name AS area_name, a.color,
               a.required_role_id, r.title AS role_title,
               (w.week_start + s.day_of_week) AS shift_date
        FROM roster_shifts s
        JOIN roster_weeks w ON w.id = s.roster_week_id
        JOIN roster_areas a ON a.id = s.area_id
        LEFT JOIN club_roles r ON r.id = a.required_role_id
        WHERE s.organisation_id = :org AND s.assignee_member_id IS NULL
          AND (w.week_start + s.day_of_week) BETWEEN :today AND :horizon
        ORDER BY (w.week_start + s.day_of_week), s.start_time
    """), {"org": org_id, "today": today, "horizon": horizon})).mappings().all()

    # Supply, per role, per day of the week.
    cands = await candidates(db, org_id)
    holders: dict = {}          # role_id -> [candidate]
    for c in cands:
        for rid in c["role_ids"]:
            holders.setdefault(rid, []).append(c)

    by_role: dict = {}
    unassigned_area: dict = {}
    for row in open_rows:
        rid = str(row["required_role_id"]) if row["required_role_id"] else None
        dow = int(row["day_of_week"])
        if rid is None:
            slot = unassigned_area.setdefault(str(row["area_id"]), {
                "area_id": str(row["area_id"]), "area_name": row["area_name"],
                "color": row["color"], "open_shifts": 0, "days": {},
            })
            slot["open_shifts"] += 1
            slot["days"][dow] = slot["days"].get(dow, 0) + 1
            continue
        slot = by_role.setdefault(rid, {
            "role_id": rid, "role_title": row["role_title"] or "Unnamed role",
            "open_shifts": 0, "areas": {}, "days": {},
        })
        slot["open_shifts"] += 1
        slot["days"][dow] = slot["days"].get(dow, 0) + 1
        slot["areas"][row["area_name"]] = slot["areas"].get(row["area_name"], 0) + 1

    out = []
    for rid, slot in by_role.items():
        people = holders.get(rid, [])
        day_rows, worst = [], 0
        for dow, needed in sorted(slot["days"].items()):
            free = [c for c in people if dow in c["available_days"]]
            short = max(0, needed - len(free))
            worst = max(worst, short)
            day_rows.append({
                "day_of_week": dow, "day": DOW[dow], "day_full": DOW_FULL[dow], "open_shifts": needed,
                "available": len(free), "short_by": short,
                "who": [c["name"] for c in free[:6]],
            })
        out.append({
            **{k: v for k, v in slot.items() if k != "days"},
            "areas": [{"name": n, "open_shifts": c} for n, c in
                      sorted(slot["areas"].items(), key=lambda kv: -kv[1])],
            "holders": len(people),
            "holders_with_no_days": sum(1 for c in people if not c["available_days"]),
            "days": day_rows,
            "short_by": worst,
        })

    # Worst shortage first, then the biggest hole, then by name so the order is
    # stable when two roles are equally short.
    out.sort(key=lambda r: (-r["short_by"], -r["open_shifts"], r["role_title"].lower()))
    return {
        "from": today.isoformat(), "to": horizon.isoformat(), "weeks": weeks,
        "roles": out,
        "no_role_required": sorted(unassigned_area.values(), key=lambda a: -a["open_shifts"]),
        "total_open": len(open_rows),
        "short_roles": sum(1 for r in out if r["short_by"] > 0),
    }


async def hours_summary(db: AsyncSession, org_id, *, start: date, end: date) -> dict:
    """Rostered vs worked hours per person, split paid and volunteer.

    ROSTERED is what the roster committed someone to: the length of every shift
    they are assigned to in the window. WORKED is what was actually logged
    afterwards. They are deliberately separate numbers — the gap between them is
    the thing a club wants to see, and collapsing them would hide it.
    """
    paid_by_area = await area_pay_kinds(db, org_id)
    shifts = (await db.execute(text("""
        SELECT s.assignee_member_id AS member_id, s.area_id, s.start_time, s.end_time,
               m.full_name
        FROM roster_shifts s
        JOIN roster_weeks w ON w.id = s.roster_week_id
        JOIN fee_members m ON m.id = s.assignee_member_id
        WHERE s.organisation_id = :org AND s.assignee_member_id IS NOT NULL
          AND (w.week_start + s.day_of_week) BETWEEN :start AND :end
    """), {"org": org_id, "start": start, "end": end})).mappings().all()

    logged = (await db.execute(text("""
        SELECT h.member_id, m.full_name, h.hours, h.is_paid
        FROM volunteer_hours h JOIN fee_members m ON m.id = h.member_id
        WHERE h.organisation_id = :org AND h.logged_date BETWEEN :start AND :end
    """), {"org": org_id, "start": start, "end": end})).mappings().all()

    people: dict = {}

    def row(mid, name):
        return people.setdefault(str(mid), {
            "member_id": str(mid), "full_name": name,
            "rostered_volunteer": 0.0, "rostered_paid": 0.0,
            "worked_volunteer": 0.0, "worked_paid": 0.0,
        })

    for s in shifts:
        r = row(s["member_id"], s["full_name"])
        key = "rostered_paid" if paid_by_area.get(str(s["area_id"])) else "rostered_volunteer"
        r[key] += shift_hours(s["start_time"], s["end_time"])
    for h in logged:
        r = row(h["member_id"], h["full_name"])
        r["worked_paid" if h["is_paid"] else "worked_volunteer"] += float(h["hours"] or 0)

    out = sorted(people.values(), key=lambda p: p["full_name"].lower())
    totals = {k: round(sum(p[k] for p in out), 2)
              for k in ("rostered_volunteer", "rostered_paid", "worked_volunteer", "worked_paid")}
    for p in out:
        for k in ("rostered_volunteer", "rostered_paid", "worked_volunteer", "worked_paid"):
            p[k] = round(p[k], 2)
    return {"people": out, "totals": totals,
            "start": start.isoformat(), "end": end.isoformat()}


async def member_detail(db: AsyncSession, org_id, member_id) -> dict:
    """One volunteer, as the roster needs them: who they are, when they can do
    it, and what they are qualified for. The roster is where an admin notices
    availability is wrong, so it should be where they can fix it."""
    m = (await db.execute(text("""
        SELECT m.id, m.full_name, m.email, m.mobile
        FROM fee_members m WHERE m.id = :id AND m.organisation_id = :org
    """), {"id": member_id, "org": org_id})).mappings().first()
    if not m:
        return {}
    prof = (await db.execute(text("""
        SELECT available_days, max_shifts_per_week, lives_nearby
        FROM volunteer_profiles WHERE organisation_id = :org AND member_id = :id
    """), {"org": org_id, "id": member_id})).mappings().first()
    quals = (await db.execute(text("""
        SELECT q.id, qt.name, q.expires_at
        FROM member_qualifications q JOIN qualification_types qt ON qt.id = q.qualification_type_id
        WHERE q.organisation_id = :org AND q.member_id = :id
        ORDER BY qt.name
    """), {"org": org_id, "id": member_id})).mappings().all()
    roles = (await db.execute(text("""
        SELECT r.id, r.title, COALESCE(rt.category, '') AS category
        FROM volunteer_roles vr
        JOIN club_roles r ON r.id = vr.role_id
        LEFT JOIN club_role_types rt ON rt.id = r.role_type_id
        WHERE vr.organisation_id = :org AND vr.member_id = :id
        ORDER BY r.title
    """), {"org": org_id, "id": member_id})).mappings().all()
    return {
        "member_id": str(m["id"]), "full_name": m["full_name"],
        "email": m["email"], "mobile": m["mobile"],
        # Normalised through day_index, so a profile saved with day NAMES reads
        # the same as one saved with indexes (see the note on day_index).
        "available_days": [d for d in ((day_index(x) for x in ((prof or {}).get("available_days") or []))) if d is not None],
        "max_shifts_per_week": (prof or {}).get("max_shifts_per_week"),
        "lives_nearby": (prof or {}).get("lives_nearby"),
        "qualifications": [{"id": str(q["id"]), "name": q["name"],
                            "expires_at": q["expires_at"].isoformat() if q["expires_at"] else None}
                           for q in quals],
        "roles": [{"id": str(r["id"]), "title": r["title"],
                   "is_paid": (r["category"] or "").lower() == PAID_CATEGORY} for r in roles],
    }


async def set_member_availability(db: AsyncSession, org_id, member_id, days: list) -> list:
    """Write availability as INDEXES.

    The Volunteers screen writes day names and the roster reads indexes; that
    mismatch is what crashed the roster page. Everything written from here is
    normalised, so the data converges on one vocabulary over time while
    day_index keeps the old rows readable.
    """
    clean = sorted({d for d in (day_index(x) for x in (days or [])) if d is not None})
    existing = (await db.execute(text(
        "SELECT 1 FROM volunteer_profiles WHERE organisation_id = :org AND member_id = :id"
    ), {"org": org_id, "id": member_id})).first()
    if existing:
        await db.execute(text("""
            UPDATE volunteer_profiles SET available_days = CAST(:days AS jsonb)
            WHERE organisation_id = :org AND member_id = :id
        """), {"org": org_id, "id": member_id, "days": json.dumps(clean)})
    else:
        await db.execute(text("""
            INSERT INTO volunteer_profiles (id, organisation_id, member_id, available_days)
            VALUES (gen_random_uuid(), :org, :id, CAST(:days AS jsonb))
        """), {"org": org_id, "id": member_id, "days": json.dumps(clean)})
    return clean
