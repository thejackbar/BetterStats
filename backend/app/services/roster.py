"""BetterClubManager Roster — the weekly volunteer roster and its rules engine.

Assignments are validated here (qualification, availability, overlap = blocks;
wrong role, over cap, heavy week = warnings). Everything else (coverage,
per-person load, candidate ranking) is derived on read. Raw SQL throughout, so
this subsystem stays out of the ORM/Alembic model graph (same posture as the
families router).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
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
            "available_days": [int(d) for d in (r["available_days"] or [])],
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
