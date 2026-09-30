"""BetterFootball — the league and club rules a selected side is checked against.

Football's own vocabulary, not cricket's. Cricket's rule engine
(``services/selection_rules.py``) carries bowling workloads, an overseas-player
cap and nets attendance, none of which a football league writes; football
leagues write different things again:

  * **team_size**   — how many take the field, how many sit on the interchange
                      bench, how many emergencies are named. Senior football is
                      18 on the ground; junior and women's competitions often
                      play 15 or 16, and bench limits differ by league.
  * **age**         — an age limit measured the football way: as at 1 January
                      of the season's year (the AFL community standard), on the
                      day of the match, or a set date.
  * **finals_qualification** — a minimum number of home-and-away games before a
                      player may play finals, counted in this grade, this grade
                      or higher, or anywhere at the club.
  * **higher_grade_limit** — a player who has played more than N games in a
                      HIGHER side this season is not eligible for this side
                      (usually in finals only), which is how leagues stop a
                      club dropping its seniors into the reserves for September.
  * **concussion**  — the stand-down after a concussion. AFL community
                      guidelines put the minimum at 21 days; a club records the
                      date and the board counts from it, and a medical clearance
                      is recorded as a permit.
  * **registration** / **fees** — registered on PlayHQ this season, and nothing
                      owing, read off BetterFees where the club uses it.
  * **custom**      — anything else a league writes, with the players it
                      applies to ticked by hand.

The same discipline cricket's engine keeps, because it is what makes a rule
engine trustworthy: SILENCE WHERE THE CLUB'S DATA CANNOT ANSWER. No date of
birth, no fees season, no games recorded yet — none of those is a breach.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.afl import AflSelectionRule, AflSelectionRulePlayer
from app.services.afl.grade_labels import GRADE_CATEGORIES, strip_sponsor_suffix
from app.services.afl.grade_scope import category_of
from app.services.player_age import age_on

SEVERITIES = ("info", "warn", "block")
MIN_OPS = ("gte", "gt")
MAX_OPS = ("lt", "lte")
AGE_BASES = ("jan1", "match_date", "fixed_date")
QUALIFY_COUNTS = ("grade", "grade_or_higher", "club")
MODES = ("permit", "block", "incident")

DEFAULT_FIELD = 18
DEFAULT_BENCH = 10
DEFAULT_EMERGENCIES = 3
DEFAULT_CONCUSSION_DAYS = 21

RULE_KINDS: dict[str, dict] = {
    "team_size": {
        "label": "Team size",
        "help": "How many take the field, how many can sit on the interchange bench, and how many emergencies are named.",
    },
    "age": {
        "label": "Age limit",
        "help": "A minimum or maximum age, measured as at 1 January of the season, on match day, or on a set date.",
    },
    "finals_qualification": {
        "label": "Finals qualification",
        "help": "A minimum number of home-and-away games before a player may play finals.",
    },
    "higher_grade_limit": {
        "label": "Games in a higher side",
        "help": "A player who has played more than this many games in a higher side this season can't play in this one.",
    },
    "concussion": {
        "label": "Concussion stand-down",
        "help": "No selection within this many days of a recorded concussion, unless a medical clearance is recorded.",
    },
    "registration": {
        "label": "Registered on PlayHQ",
        "help": "The player must be ticked as registered on PlayHQ for this season in BetterFees.",
    },
    "fees": {
        "label": "Fees paid",
        "help": "The player must owe nothing for this season in BetterFees.",
    },
    "custom": {
        "label": "Other rule",
        "help": "Any other rule. Tick the players it rules out, or who have been cleared.",
    },
}

_INFO_ONLY = {"team_size"}
# Only these ask a question the fixture's date or grade decides; the others
# are about the player alone.
_FINALS_KINDS = {"finals_qualification"}


def _int(value, lo: int, hi: int, fallback: Optional[int] = None) -> Optional[int]:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return fallback
    return n if lo <= n <= hi else fallback


def _str_list(value, limit: int = 60) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        s = str(item or "").strip()
        if s and s not in out:
            out.append(s[:120])
        if len(out) >= limit:
            break
    return out


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


# ── Cleaning what a browser sends ────────────────────────────────────────────

def clean_severity(kind: str, value) -> str:
    if kind in _INFO_ONLY:
        return "info"
    return value if value in ("warn", "block") else "warn"


def clean_scope(raw) -> dict:
    """Which fixtures a rule covers. An empty list means EVERY one."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "grade_names": _str_list(raw.get("grade_names")),
        "categories": [c for c in _str_list(raw.get("categories")) if c in GRADE_CATEGORIES],
        "team_ids": [t for t in _str_list(raw.get("team_ids")) if _is_uuid(t)],
    }


def clean_config(kind: str, raw) -> dict:
    c = raw if isinstance(raw, dict) else {}
    if kind == "team_size":
        return {
            "field": _int(c.get("field"), 9, 18, DEFAULT_FIELD),
            "bench": _int(c.get("bench"), 0, 15, DEFAULT_BENCH),
            "emergencies": _int(c.get("emergencies"), 0, 6, DEFAULT_EMERGENCIES),
        }
    if kind == "age":
        out: dict = {
            "min_age": _int(c.get("min_age"), 4, 99),
            "min_op": c.get("min_op") if c.get("min_op") in MIN_OPS else "gte",
            "under_age": _int(c.get("under_age"), 5, 100),
            "max_op": c.get("max_op") if c.get("max_op") in MAX_OPS else "lt",
            "basis": c.get("basis") if c.get("basis") in AGE_BASES else "jan1",
        }
        if out["basis"] == "fixed_date":
            try:
                out["date"] = date.fromisoformat(str(c.get("date"))[:10]).isoformat()
            except (TypeError, ValueError):
                out["basis"] = "jan1"
        return out
    if kind == "finals_qualification":
        return {
            "min_games": _int(c.get("min_games"), 1, 40, 6),
            "count": c.get("count") if c.get("count") in QUALIFY_COUNTS else "grade_or_higher",
        }
    if kind == "higher_grade_limit":
        return {
            "max_games": _int(c.get("max_games"), 0, 40, 5),
            "finals_only": c.get("finals_only") is not False,
        }
    if kind == "concussion":
        return {"days": _int(c.get("days"), 1, 120, DEFAULT_CONCUSSION_DAYS)}
    if kind == "custom":
        return {"text": str(c.get("text") or "").strip()[:500]}
    return {}


def _d(d: date) -> str:
    return f"{d.day} {d.strftime('%b')}"


def _min_phrase(age: int, op: str) -> str:
    return f"over {age}" if op == "gt" else f"{age} and over"


def _max_phrase(age: int, op: str) -> str:
    return f"{age} or under" if op == "lte" else f"under {age}"


def basis_label(cfg: dict) -> str:
    b = cfg.get("basis")
    if b == "match_date":
        return "on match day"
    if b == "fixed_date" and cfg.get("date"):
        d = date.fromisoformat(cfg["date"])
        return f"as at {d.day} {d.strftime('%B')} {d.year}"
    return "as at 1 January of the season"


def rule_summary(kind: str, config: dict) -> str:
    c = config or {}
    if kind == "team_size":
        emg = c.get("emergencies", DEFAULT_EMERGENCIES)
        return (f"{c.get('field', DEFAULT_FIELD)} on the field, up to {c.get('bench', DEFAULT_BENCH)} "
                f"on the bench" + (f", {emg} emergencies" if emg else ""))
    if kind == "age":
        bits = []
        if c.get("min_age") is not None:
            bits.append(_min_phrase(c["min_age"], c.get("min_op")))
        if c.get("under_age") is not None:
            bits.append(_max_phrase(c["under_age"], c.get("max_op")))
        if not bits:
            return "No age set yet"
        return f"{' and '.join(bits).capitalize()}, {basis_label(c)}"
    if kind == "finals_qualification":
        where = {"grade": "in this grade", "grade_or_higher": "in this grade or higher",
                 "club": "for the club"}[c.get("count", "grade_or_higher")]
        return f"At least {c.get('min_games', 6)} home-and-away games {where} to play finals"
    if kind == "higher_grade_limit":
        when = " (finals only)" if c.get("finals_only", True) else ""
        return f"No more than {c.get('max_games', 5)} games in a higher side this season{when}"
    if kind == "concussion":
        return f"{c.get('days', DEFAULT_CONCUSSION_DAYS)} days' stand-down after a recorded concussion"
    if kind == "custom":
        return c.get("text") or "A rule of the club's own"
    return RULE_KINDS.get(kind, {}).get("help", "")


def rule_out(r: AflSelectionRule, players: Optional[list] = None) -> dict:
    cfg = clean_config(r.kind, r.config)
    return {
        "id": str(r.id),
        "kind": r.kind,
        "kind_label": RULE_KINDS.get(r.kind, {}).get("label", r.kind),
        "name": r.name or RULE_KINDS.get(r.kind, {}).get("label", r.kind),
        "severity": clean_severity(r.kind, r.severity),
        "scope": clean_scope(r.scope),
        "config": cfg,
        "enabled": bool(r.enabled),
        "summary": rule_summary(r.kind, cfg),
        "players": players or [],
    }


async def list_rules(db: AsyncSession, org_id, *, enabled_only: bool = False) -> list[AflSelectionRule]:
    q = select(AflSelectionRule).where(AflSelectionRule.organisation_id == org_id)
    if enabled_only:
        q = q.where(AflSelectionRule.enabled.is_(True))
    return list((await db.execute(q.order_by(AflSelectionRule.sort_order, AflSelectionRule.created_at))).scalars().all())


async def rule_players(db: AsyncSession, org_id) -> dict[str, list[AflSelectionRulePlayer]]:
    rows = (await db.execute(
        select(AflSelectionRulePlayer).where(AflSelectionRulePlayer.organisation_id == org_id)
    )).scalars().all()
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(str(r.rule_id), []).append(r)
    return out


# ── The fixture a rule is judged against ─────────────────────────────────────

@dataclass
class FixtureFacts:
    """What the evaluation needs to know about one fixture."""
    fixture_id: Optional[str]
    played_on: Optional[date]
    grade_id: Optional[str]
    grade_name: Optional[str]
    category: Optional[str]
    team_id: Optional[str]
    team_sequence: Optional[int]
    is_final: bool
    season_ids: list[str]            # every season row of this year (merged comps)
    season_year: Optional[int]
    fees_season_id: Optional[str]    # the season row BetterFees would bill


def scope_matches(scope: dict, facts: FixtureFacts) -> bool:
    s = clean_scope(scope)
    if s["grade_names"]:
        if not facts.grade_name:
            return False
        want = {strip_sponsor_suffix(n).lower() for n in s["grade_names"]}
        if strip_sponsor_suffix(facts.grade_name).lower() not in want:
            return False
    if s["categories"] and (not facts.category or facts.category not in s["categories"]):
        return False
    if s["team_ids"] and (not facts.team_id or facts.team_id not in s["team_ids"]):
        return False
    return True


def team_size_for(rules: list[dict], facts: Optional[FixtureFacts]) -> dict:
    """The field, bench and emergency counts that apply. The first team_size
    rule whose scope covers the fixture wins; with none, a senior side."""
    for r in rules:
        if r["kind"] == "team_size" and r["enabled"] and (facts is None or scope_matches(r["scope"], facts)):
            return dict(r["config"])
    return {"field": DEFAULT_FIELD, "bench": DEFAULT_BENCH, "emergencies": DEFAULT_EMERGENCIES}


@dataclass
class RuleResult:
    rules: list[dict] = field(default_factory=list)         # applying to this fixture
    flags: dict[str, list[dict]] = field(default_factory=dict)
    team_size: dict = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return any(r["kind"] != "team_size" for r in self.rules)

    def blocking(self, player_ids: list[str], names: dict[str, str]) -> list[str]:
        out = []
        for pid in player_ids:
            for f in self.flags.get(pid, []):
                if f["severity"] == "block":
                    out.append(f"{names.get(pid, 'A player')}: {f['detail']}")
        return out


def _age_as_at(cfg: dict, facts: FixtureFacts) -> Optional[date]:
    b = cfg.get("basis", "jan1")
    if b == "match_date":
        return facts.played_on
    if b == "fixed_date":
        try:
            return date.fromisoformat(cfg["date"])
        except (KeyError, TypeError, ValueError):
            return None
    year = facts.season_year or (facts.played_on.year if facts.played_on else None)
    return date(year, 1, 1) if year else None


async def season_games(db: AsyncSession, org_id, season_ids: list[str]) -> list:
    """Every game our players played in these seasons: (player, grade, date,
    is_final, goals, behinds, bog). Our side only — the opposition's lines sit
    on the same games."""
    if not season_ids:
        return []
    rows = await db.execute(text("""
        SELECT l.player_id, g.grade_id, g.played_at, COALESCE(g.is_final, false) AS is_final,
               l.goals, l.behinds, l.bog_ranking, g.id AS game_id
          FROM afl_player_game_lines l
          JOIN afl_game_details d ON d.game_id = l.game_id AND l.side = d.our_side
          JOIN games g ON g.id = l.game_id
          JOIN grades gr ON gr.id = g.grade_id
          JOIN seasons s ON s.id = gr.season_id
          JOIN players p ON p.id = l.player_id AND p.organisation_id = :org
         WHERE s.organisation_id = :org
           AND s.id = ANY(CAST(:seasons AS uuid[]))
           AND l.played
    """), {"org": str(org_id), "seasons": [str(s) for s in season_ids]})
    return rows.fetchall()


async def grade_ranks(db: AsyncSession, org_id) -> dict[str, int]:
    """grade row id -> the rank of the side that plays in it (1 = top side).

    A club's sides are ``teams`` rows ordered by ``sequence``. A side's grade
    changes from year to year, so it is matched two ways: the grade the side
    names directly, and every grade PlayHQ filed a team of that name under in
    any season (``afl_teams``)."""
    rows = await db.execute(text("""
        SELECT t.grade_id AS gid, t.sequence FROM teams t
         WHERE t.organisation_id = :org AND t.grade_id IS NOT NULL AND t.is_active
        UNION ALL
        SELECT at.grade_id, t.sequence FROM afl_teams at
          JOIN teams t ON t.organisation_id = at.organisation_id AND lower(t.name) = lower(at.name)
         WHERE at.organisation_id = :org AND at.grade_id IS NOT NULL AND t.is_active
    """), {"org": str(org_id)})
    out: dict[str, int] = {}
    for gid, seq in rows.fetchall():
        k = str(gid)
        out[k] = min(out.get(k, seq), seq) if seq is not None else out.get(k, 99)
    return out


async def evaluate(db: AsyncSession, org, facts: FixtureFacts, players: list, *,
                   games: Optional[list] = None, ranks: Optional[dict] = None) -> RuleResult:
    """Judge every player against the rules that cover this fixture."""
    rows = await list_rules(db, org.id, enabled_only=True)
    marks = await rule_players(db, org.id)
    applying = [rule_out(r) for r in rows if scope_matches(r.scope, facts)]
    res = RuleResult(rules=applying, team_size=team_size_for(applying, facts))
    checks = [r for r in applying if r["kind"] != "team_size"]
    if not checks:
        return res

    kinds = {r["kind"] for r in checks}
    if games is None and kinds & {"finals_qualification", "higher_grade_limit"}:
        games = await season_games(db, org.id, facts.season_ids)
    if ranks is None and kinds & {"finals_qualification", "higher_grade_limit"}:
        ranks = await grade_ranks(db, org.id)
    games = games or []
    ranks = ranks or {}
    my_rank = ranks.get(facts.grade_id) if facts.grade_id else None
    if my_rank is None:
        my_rank = facts.team_sequence

    owing: Optional[set] = None
    registered: Optional[dict] = None
    if "fees" in kinds and facts.fees_season_id:
        try:
            from app.services.fees import owing_player_ids
            owing = {str(p) for p in await owing_player_ids(db, org.id, facts.fees_season_id)}
        except Exception:  # noqa: BLE001 — no fees data is silence, not a breach
            await db.rollback()
            owing = None
    if "registration" in kinds and facts.fees_season_id:
        try:
            reg = await db.execute(text("""
                SELECT fm.player_id, ms.playhq_registered
                  FROM fee_member_seasons ms JOIN fee_members fm ON fm.id = ms.member_id
                 WHERE fm.organisation_id = :org AND ms.season_id = :s AND fm.player_id IS NOT NULL
            """), {"org": str(org.id), "s": facts.fees_season_id})
            registered = {str(p): bool(v) for p, v in reg.fetchall()}
        except Exception:  # noqa: BLE001
            await db.rollback()
            registered = None

    by_player: dict[str, list] = {}
    for g in games:
        by_player.setdefault(str(g.player_id), []).append(g)

    for p in players:
        pid = str(p.id)
        mine = by_player.get(pid, [])
        for r in checks:
            rid = r["id"]
            mark = next((m for m in marks.get(rid, []) if str(m.player_id) == pid and m.mode != "incident"), None)
            if mark and mark.mode == "permit":
                continue
            detail = _judge(r, p, facts, mine, ranks, my_rank, owing, registered,
                            [m for m in marks.get(rid, []) if str(m.player_id) == pid])
            if mark and mark.mode == "block" and not detail:
                detail = mark.note or "Ruled out by the club"
            if detail:
                res.flags.setdefault(pid, []).append({
                    "rule_id": rid, "kind": r["kind"], "name": r["name"],
                    "severity": r["severity"], "detail": detail,
                })
    return res


def _judge(r: dict, p, facts: FixtureFacts, mine: list, ranks: dict, my_rank,
           owing, registered, marks: list) -> Optional[str]:
    kind, c = r["kind"], r["config"]
    if kind == "age":
        as_at = _age_as_at(c, facts)
        age = age_on(getattr(p, "date_of_birth", None), as_at) if as_at else None
        if age is None:
            return None
        if c.get("min_age") is not None:
            ok = age > c["min_age"] if c.get("min_op") == "gt" else age >= c["min_age"]
            if not ok:
                return f"Aged {age} {basis_label(c)}; this grade is {_min_phrase(c['min_age'], c.get('min_op'))}"
        if c.get("under_age") is not None:
            ok = age <= c["under_age"] if c.get("max_op") == "lte" else age < c["under_age"]
            if not ok:
                return f"Aged {age} {basis_label(c)}; this grade is {_max_phrase(c['under_age'], c.get('max_op'))}"
        return None

    if kind == "finals_qualification":
        if not facts.is_final:
            return None
        ha = [g for g in mine if not g.is_final]
        count = c.get("count", "grade_or_higher")
        if count == "grade":
            n = sum(1 for g in ha if str(g.grade_id) == facts.grade_id)
        elif count == "club" or my_rank is None:
            n = len(ha)
        else:
            n = sum(1 for g in ha if (ranks.get(str(g.grade_id), 999) <= my_rank))
        need = c.get("min_games", 6)
        if n < need:
            return f"{n} home-and-away game{'s' if n != 1 else ''}, {need} needed for finals"
        return None

    if kind == "higher_grade_limit":
        if c.get("finals_only", True) and not facts.is_final:
            return None
        if my_rank is None:
            return None
        n = sum(1 for g in mine if ranks.get(str(g.grade_id), 999) < my_rank)
        cap = c.get("max_games", 5)
        if n > cap:
            return f"{n} games in a higher side this season, {cap} allowed"
        return None

    if kind == "concussion":
        days = c.get("days", DEFAULT_CONCUSSION_DAYS)
        on = facts.played_on or date.today()
        for m in marks:
            if m.mode != "incident" or not m.incident_date:
                continue
            clear = m.incident_date + timedelta(days=days)
            if m.incident_date <= on < clear:
                return f"Concussed {_d(m.incident_date)}; can return from {_d(clear)}"
        return None

    if kind == "fees":
        if owing is None:
            return None
        return "Owes fees for this season" if str(p.id) in owing else None

    if kind == "registration":
        if not registered:
            return None
        return None if registered.get(str(p.id)) else "Not ticked as registered on PlayHQ"

    return None
