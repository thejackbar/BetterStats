"""BetterSelect — the club's association rules, and the settings around them.

The screen behind this (`/admin/betterselect/rules`) is where a club writes
down what its competition requires: who is old enough for each division, how
many overseas players may be named, how many overs a fourteen year old may
bowl, what qualifies a player for a final. Everything is the club's own —
see services/selection_rules.py for why nothing here has a built-in number.

Gated on MANAGE_SELECTIONS rather than MANAGE_SETTINGS. These are a selector's
settings, and a selector is exactly who has the association handbook open; the
club-wide BetterSelect settings that used to live on the Club Settings screen
(age display, the dormant-player window, default side size) moved in here with
them for that reason, and are still editable from Club Settings by anyone who
holds MANAGE_SETTINGS.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_SELECTIONS, require_cap
from app.models.db import Organisation, User, get_db
from app.routers.auth import get_current_club
from app.services import grade_labels, player_age, selection_rules as rules_svc

router = APIRouter(prefix="/selection-rules", tags=["selection-rules"])


class RuleBody(BaseModel):
    kind: Optional[str] = None
    name: Optional[str] = None
    enabled: Optional[bool] = None
    severity: Optional[str] = None
    scope: Optional[dict] = None
    config: Optional[dict] = None


class ReorderBody(BaseModel):
    ids: list[str]


class ClearanceBody(BaseModel):
    state: Optional[str] = None          # 'cleared' | 'blocked' | None to remove
    note: Optional[str] = None


class SettingsBody(BaseModel):
    age_basis: Optional[dict] = None
    season_start_month: Optional[int] = None
    select_show_age: Optional[bool] = None
    # A genuine tri-state on the wire: absent leaves it alone, null means every
    # player, a number restricts it. Read through model_fields_set below.
    select_show_age_under: Optional[int] = None
    dormancy_months: Optional[int] = None
    default_team_size: Optional[int] = None
    # Whether the board draws the plain fees / training notes beside a player.
    # A rule about either still shows: that one the club asked for.
    show_fees: Optional[bool] = None
    show_training: Optional[bool] = None


async def _grade_options(db: AsyncSession, org_id) -> list[dict]:
    """Every grade a rule can name, as Manage Grades lists them.

    Names rather than ids, because a rule keyed on ids stops applying the day
    next season's grades are created. Merges, renames and the club's own
    reading order all come from :func:`selection_rules.club_grades`, so this
    picker and the Manage Grades screen can't disagree about what the club
    runs or what order it reads in.
    """
    grades = await rules_svc.club_grades(db, org_id)
    cats = await grade_labels.org_grade_category_sets(db, org_id)
    fmts = await grade_labels.org_grade_format_sets(db, org_id)
    return [
        {
            "name": g["name"],
            "recent": g["recent"],
            "categories": sorted(grade_labels.categories_for_name(cats, g["name"])),
            "formats": sorted(grade_labels.formats_for_name(fmts, g["name"])),
        }
        for g in grades
    ]


async def _team_names(db: AsyncSession, org_id) -> dict[str, str]:
    rows = (await db.execute(
        text("SELECT id, COALESCE(short_name, name) FROM teams "
             "WHERE organisation_id = :org ORDER BY sequence, name"),
        {"org": org_id},
    )).fetchall()
    return {str(tid): name for tid, name in rows}


def _settings_out(club: Organisation) -> dict:
    cfg = rules_svc.club_config(club)
    return {
        "age_basis": cfg["age_basis"],
        "age_basis_label": rules_svc.age_basis_label(cfg["age_basis"]),
        "season_start_month": cfg["season_start_month"],
        "select_show_age": bool(club.select_show_age),
        "select_show_age_under": player_age.clean_age_limit(club.select_show_age_under),
        "dormancy_months": club.dormancy_months if club.dormancy_months is not None else 24,
        "default_team_size": club.default_team_size if club.default_team_size is not None else 11,
        "show_fees": cfg["show_fees"],
        "show_training": cfg["show_training"],
    }


@router.get("")
async def get_rules(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Everything the settings screen draws: the club's rules, the settings
    around them, and the options a rule can be scoped to."""
    basis = rules_svc.club_config(club)["age_basis"]
    teams = await _team_names(db, club.id)
    rows = await rules_svc.list_rules(db, club.id)
    counts = (await db.execute(
        text("SELECT rule_id, COUNT(*) FROM selection_rule_players "
             "WHERE organisation_id = :org GROUP BY rule_id"),
        {"org": club.id},
    )).fetchall()
    exceptions = {str(rid): int(n) for rid, n in counts}
    out = []
    for r in rows:
        item = rules_svc.rule_out(r, basis, teams)
        item["exception_count"] = exceptions.get(item["id"], 0)
        out.append(item)
    return {
        "settings": _settings_out(club),
        "rules": out,
        "kinds": [
            {"kind": k, "info_only": k in rules_svc._INFO_ONLY, **meta}
            for k, meta in rules_svc.RULE_KINDS.items()
        ],
        "options": {
            "grades": await _grade_options(db, club.id),
            "categories": [{"value": c, "label": grade_labels.category_label(c)}
                           for c in grade_labels.GRADE_CATEGORIES],
            "formats": [{"value": f, "label": grade_labels.format_label(f)}
                        for f in grade_labels.MATCH_FORMATS],
            "teams": [{"value": tid, "label": name} for tid, name in teams.items()],
        },
    }


@router.patch("/settings")
async def patch_settings(
    body: SettingsBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    cfg = dict(club.selection_rules_config or {})
    if body.age_basis is not None:
        cfg["age_basis"] = rules_svc.clean_age_basis(body.age_basis)
    if body.season_start_month is not None:
        month = int(body.season_start_month)
        if not 1 <= month <= 12:
            raise HTTPException(status_code=400, detail="Pick a month.")
        cfg["season_start_month"] = month
    if body.select_show_age is not None:
        club.select_show_age = bool(body.select_show_age)
    # Presence is the intent: "every player" is a null, so `is not None` would
    # make it unsettable the moment a club picked an age (see migration 269).
    if "select_show_age_under" in body.model_fields_set:
        club.select_show_age_under = player_age.clean_age_limit(body.select_show_age_under)
    if body.dormancy_months is not None:
        club.dormancy_months = max(1, min(600, int(body.dormancy_months)))
    if body.default_team_size is not None and int(body.default_team_size) in (0, 11, 12, 13):
        club.default_team_size = int(body.default_team_size)
    if body.show_fees is not None:
        cfg["show_fees"] = bool(body.show_fees)
    if body.show_training is not None:
        cfg["show_training"] = bool(body.show_training)
    club.selection_rules_config = cfg or None
    await db.commit()
    return _settings_out(club)


def _scope_for(kind: str, raw) -> dict:
    """A rule's scope, with the one kind-specific default applied: a finals
    qualification rule is about finals, so it is scoped to them unless the club
    has deliberately said otherwise."""
    scope = rules_svc.clean_scope(raw)
    if kind == "finals_qualification" and scope["finals"] == "any":
        scope["finals"] = "only"
    return scope


@router.post("")
async def create_rule(
    body: RuleBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    kind = body.kind
    if kind not in rules_svc.RULE_KINDS:
        raise HTTPException(status_code=400, detail="Unknown rule type.")
    try:
        config = rules_svc.clean_config(kind, body.config)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    nxt = (await db.execute(
        text("SELECT COALESCE(MAX(position), -1) + 1 FROM selection_rules WHERE organisation_id = :org"),
        {"org": club.id},
    )).scalar() or 0
    rid = (await db.execute(
        text("INSERT INTO selection_rules (organisation_id, kind, name, enabled, severity, "
             "scope, config, position) VALUES (:org, :kind, :name, :enabled, :sev, "
             "CAST(:scope AS jsonb), CAST(:config AS jsonb), :pos) RETURNING id"),
        {
            "org": club.id, "kind": kind,
            "name": (body.name or "").strip() or None,
            "enabled": True if body.enabled is None else bool(body.enabled),
            "sev": rules_svc.clean_severity(kind, body.severity),
            "scope": _json(_scope_for(kind, body.scope)),
            "config": _json(config),
            "pos": int(nxt),
        },
    )).scalar()
    await db.commit()
    return {"id": str(rid)}


@router.patch("/{rule_id}")
async def update_rule(
    rule_id: str,
    body: RuleBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    row = await _owned_rule(db, rule_id, club.id)
    fields: dict = {"id": row["id"], "org": club.id}
    sets: list[str] = []
    if "name" in body.model_fields_set:
        sets.append("name = :name")
        fields["name"] = (body.name or "").strip() or None
    if body.enabled is not None:
        sets.append("enabled = :enabled")
        fields["enabled"] = bool(body.enabled)
    if body.severity is not None:
        sets.append("severity = :sev")
        fields["sev"] = rules_svc.clean_severity(row["kind"], body.severity)
    if body.scope is not None:
        sets.append("scope = CAST(:scope AS jsonb)")
        fields["scope"] = _json(_scope_for(row["kind"], body.scope))
    if body.config is not None:
        try:
            fields["config"] = _json(rules_svc.clean_config(row["kind"], body.config))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        sets.append("config = CAST(:config AS jsonb)")
    if not sets:
        return {"status": "ok"}
    sets.append("updated_at = now()")
    await db.execute(
        text(f"UPDATE selection_rules SET {', '.join(sets)} "
             "WHERE id = :id AND organisation_id = :org"),
        fields,
    )
    await db.commit()
    return {"status": "ok"}


@router.delete("/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    row = await _owned_rule(db, rule_id, club.id)
    await db.execute(
        text("DELETE FROM selection_rules WHERE id = :id AND organisation_id = :org"),
        {"id": row["id"], "org": club.id},
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/reorder")
async def reorder_rules(
    body: ReorderBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Ids that aren't this club's are ignored rather than rejected — the list
    comes from a browser."""
    for i, rid in enumerate(body.ids):
        if not _uuid_or_none(rid):
            continue
        await db.execute(
            text("UPDATE selection_rules SET position = :pos "
                 "WHERE id = :id AND organisation_id = :org"),
            {"pos": i, "id": rid, "org": club.id},
        )
    await db.commit()
    return {"status": "ok"}


@router.get("/{rule_id}/players")
async def rule_players(
    rule_id: str,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """The club's players and where each stands with this one rule."""
    row = await _owned_rule(db, rule_id, club.id)
    people = (await db.execute(
        text("SELECT p.id, COALESCE(p.display_name_override, p.name) AS name, "
             "rp.state, rp.note FROM players p "
             "LEFT JOIN selection_rule_players rp "
             "ON rp.player_id = p.id AND rp.rule_id = :rid "
             "WHERE p.organisation_id = :org AND p.is_player IS TRUE "
             "AND p.status IS DISTINCT FROM 'inactive' ORDER BY name"),
        {"rid": row["id"], "org": club.id},
    )).fetchall()
    return {
        "rule_id": str(row["id"]),
        "kind": row["kind"],
        "players": [
            {"id": str(pid), "name": name, "state": state, "note": note}
            for pid, name, state, note in people
        ],
    }


@router.put("/{rule_id}/players/{player_id}")
async def set_rule_player(
    rule_id: str,
    player_id: str,
    body: ClearanceBody,
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    user: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Clear a player of one rule (a permit, an association clearance, the tick
    a free-text rule asks for), or mark them ineligible under it. A null state
    removes the exception entirely."""
    row = await _owned_rule(db, rule_id, club.id)
    owned = (await db.execute(
        text("SELECT 1 FROM players WHERE id = :pid AND organisation_id = :org"),
        {"pid": player_id, "org": club.id},
    )).first()
    if not owned:
        raise HTTPException(status_code=404, detail="Player not found")
    if body.state in (None, ""):
        await db.execute(
            text("DELETE FROM selection_rule_players WHERE rule_id = :rid AND player_id = :pid"),
            {"rid": row["id"], "pid": player_id},
        )
        await db.commit()
        return {"status": "ok", "state": None}
    if body.state not in ("cleared", "blocked"):
        raise HTTPException(status_code=400, detail="Unknown state.")
    await db.execute(
        text("INSERT INTO selection_rule_players (rule_id, player_id, organisation_id, "
             "state, note, updated_by, updated_at) VALUES (:rid, :pid, :org, :state, "
             ":note, :uid, now()) ON CONFLICT (rule_id, player_id) DO UPDATE SET "
             "state = EXCLUDED.state, note = EXCLUDED.note, "
             "updated_by = EXCLUDED.updated_by, updated_at = now()"),
        {
            "rid": row["id"], "pid": player_id, "org": club.id, "state": body.state,
            "note": (body.note or "").strip()[:400] or None, "uid": user.id,
        },
    )
    await db.commit()
    return {"status": "ok", "state": body.state}


# The one starter a club can be handed without inventing anything: Cricket
# Australia's published Junior Cricket Policy bowling limits, which the
# association handbook in the screenshots quotes verbatim. Every other rule
# type needs the club's own numbers, so the screen offers those as empty
# templates instead of guessing at them.
_STARTER_BOWLING = {
    "kind": "bowling_workload",
    "name": "Junior bowling limits",
    "config": {
        "applies_to": "pace",
        "max_share_of_overs": 0.2,
        "ladder": [
            {"under_age": 13, "max_overs": 8, "max_spell": 4, "rest_minutes": 30},
            {"under_age": 15, "max_overs": 12, "max_spell": 5, "rest_minutes": 30},
            {"under_age": 17, "max_overs": 16, "max_spell": 6, "rest_minutes": 30},
            {"under_age": 19, "max_overs": 20, "max_spell": 8, "rest_minutes": 30},
        ],
    },
}


@router.post("/starter")
async def seed_starter(
    db: AsyncSession = Depends(get_db),
    club: Organisation = Depends(get_current_club),
    _: User = Depends(require_cap(MANAGE_SELECTIONS)),
):
    """Add the junior bowling limits, if the club hasn't already got some.

    Skip-don't-replace: a club that has already written its own workload rule
    keeps it. Pressing the button twice can't overwrite anything.
    """
    existing = (await db.execute(
        text("SELECT 1 FROM selection_rules WHERE organisation_id = :org AND kind = :kind"),
        {"org": club.id, "kind": _STARTER_BOWLING["kind"]},
    )).first()
    if existing:
        return {"status": "ok", "added": 0}
    await db.execute(
        text("INSERT INTO selection_rules (organisation_id, kind, name, severity, scope, "
             "config, position) VALUES (:org, :kind, :name, 'info', '{}'::jsonb, "
             "CAST(:config AS jsonb), 0)"),
        {"org": club.id, "kind": _STARTER_BOWLING["kind"],
         "name": _STARTER_BOWLING["name"], "config": _json(_STARTER_BOWLING["config"])},
    )
    await db.commit()
    return {"status": "ok", "added": 1}


# ── helpers ──────────────────────────────────────────────────────────────────

def _json(value) -> str:
    import json
    return json.dumps(value)


def _uuid_or_none(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def _owned_rule(db: AsyncSession, rule_id: str, org_id) -> dict:
    if not _uuid_or_none(rule_id):
        raise HTTPException(status_code=404, detail="Rule not found")
    row = (await db.execute(
        text("SELECT id, kind FROM selection_rules WHERE id = :id AND organisation_id = :org"),
        {"id": rule_id, "org": org_id},
    )).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Rule not found")
    return dict(row)
