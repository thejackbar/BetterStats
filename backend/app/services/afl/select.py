"""BetterFootball — team selection.

The football shape of BetterSelect. Three things differ from cricket at the
root, and the rest follows from them:

  * **A side is a field, not a batting order.** Eighteen named positions in
    six lines (back pockets and full back, half-backs, the centre line,
    half-forwards, forward pockets and full forward, then the followers: ruck,
    ruck rover and rover), an interchange bench and a handful of emergencies.
    A junior or women's side can play fewer on the ground; ``formation`` drops
    positions in a fixed order so a 15-a-side team still reads as a football
    team rather than an arbitrary list.
  * **Players are positions, not batters and bowlers.** The pool shows each
    player's own positions (``players.skill_positions``, football's set: FB,
    HB, C, W, MID, RUCK, HF, FF, UTIL) and which field slots they fit.
  * **Fixtures already exist.** The football sync writes every game PlayHQ
    lists for our sides into ``games``, played or not, with the round, date,
    time, venue and opponent. ``sync_fixtures`` turns the ones still to come
    into ``fixtures`` rows keyed on the SAME id as the game, so a side picked
    for a fixture is the side for that game, and the availability tools and
    the player's self-service link work off one fixture list.

Form is football form: games this season, goals, best-on-ground rankings and
the last five games, read from ``afl_player_game_lines`` on our side only
(the opposition's lines sit on the same game rows).
"""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.afl import AflLineupSlot, AflTeam
from app.models.db import (
    Fixture, Grade, Organisation, Player, PlayerAvailability, Season, Team, TeamMember,
)
from app.services.afl import select_rules as rules_svc
from app.services.afl.grade_labels import suggest_category
from app.services.afl.grade_scope import category_of
from app.services.player_age import age_on

# ── The field ────────────────────────────────────────────────────────────────

LINES: list[tuple[str, str, list[str]]] = [
    ("B", "Back line", ["LBP", "FB", "RBP"]),
    ("HB", "Half-back line", ["LHB", "CHB", "RHB"]),
    ("C", "Centre line", ["LW", "C", "RW"]),
    ("HF", "Half-forward line", ["LHF", "CHF", "RHF"]),
    ("F", "Forward line", ["LFP", "FF", "RFP"]),
    ("FOL", "Followers", ["RUCK", "RR", "ROV"]),
]

SLOT_LABELS = {
    "LBP": "Back pocket", "FB": "Full back", "RBP": "Back pocket",
    "LHB": "Half-back flank", "CHB": "Centre half-back", "RHB": "Half-back flank",
    "LW": "Wing", "C": "Centre", "RW": "Wing",
    "LHF": "Half-forward flank", "CHF": "Centre half-forward", "RHF": "Half-forward flank",
    "LFP": "Forward pocket", "FF": "Full forward", "RFP": "Forward pocket",
    "RUCK": "Ruck", "RR": "Ruck rover", "ROV": "Rover",
}

BENCH = "INT"
EMERGENCY = "EMG"

# A smaller side drops positions in this order: the wings first (16-a-side is
# played without them), then the ruck rover (15-a-side), then a pocket and a
# flank at each end, which keeps the ground balanced all the way down to nine.
_DROP_ORDER = ["LW", "RW", "RR", "LBP", "RFP", "LHF", "RHB", "LFP", "RBP"]

# Which of a player's own positions suit a field slot. UTIL suits anywhere.
SLOT_FITS = {
    "LBP": {"FB"}, "FB": {"FB"}, "RBP": {"FB"},
    "LHB": {"HB"}, "CHB": {"HB"}, "RHB": {"HB"},
    "LW": {"W", "MID"}, "C": {"C", "MID"}, "RW": {"W", "MID"},
    "LHF": {"HF"}, "CHF": {"HF"}, "RHF": {"HF"},
    "LFP": {"FF"}, "FF": {"FF"}, "RFP": {"FF"},
    "RUCK": {"RUCK"}, "RR": {"MID", "RUCK"}, "ROV": {"MID", "C"},
}


def formation(field_size: int) -> list[dict]:
    """The lines a side of ``field_size`` lines up in, each with its slots."""
    n = max(9, min(18, int(field_size or 18)))
    dropped = set(_DROP_ORDER[: 18 - n])
    return [
        {"key": key, "label": label,
         "slots": [{"slot": s, "label": SLOT_LABELS[s]} for s in slots if s not in dropped]}
        for key, label, slots in LINES
    ]


def field_slots(field_size: int) -> list[str]:
    return [s["slot"] for line in formation(field_size) for s in line["slots"]]


def fits(slot: str, positions) -> bool:
    mine = set(positions or [])
    if "UTIL" in mine:
        return True
    return bool(mine & SLOT_FITS.get(slot, set()))


# ── Fixtures, from the games the sync already holds ─────────────────────────

async def sync_fixtures(db: AsyncSession, org_id, *, since_days: int = 14) -> dict:
    """Upsert a ``fixtures`` row for every game of ours from a fortnight ago on.

    The fixture's id IS the game's id, so a side picked here belongs to that
    game once it is played. A fixture is never deleted — a side somebody has
    picked must not vanish because PlayHQ moved a game — and a fixture the
    club has marked as a final keeps that answer.
    """
    since = date.today() - timedelta(days=since_days)
    rows = (await db.execute(text("""
        SELECT g.id, g.grade_id, g.played_at, g.home_team, g.away_team, g.opp_club_name,
               g.venue, COALESCE(g.is_final, false) AS is_final,
               d.playhq_id, d.round_name, d.start_time, d.our_side, d.status, d.venue_name,
               COALESCE(d.is_bye, false) AS is_bye
          FROM games g
          JOIN afl_game_details d ON d.game_id = g.id
          JOIN grades gr ON gr.id = g.grade_id
          JOIN seasons s ON s.id = gr.season_id
         WHERE s.organisation_id = :org AND g.played_at >= :since
           AND COALESCE(d.source, 'playhq') = 'playhq'
    """), {"org": str(org_id), "since": since})).fetchall()

    teams = (await db.execute(select(Team).where(Team.organisation_id == org_id))).scalars().all()
    by_name = {t.name.lower(): t for t in teams}
    by_grade = {str(t.grade_id): t for t in teams if t.grade_id}

    created = updated = 0
    for r in rows:
        ours = r.home_team if r.our_side == "HOME" else r.away_team
        team = by_name.get((ours or "").lower()) or by_grade.get(str(r.grade_id))
        fx = await db.get(Fixture, r.id)
        if fx is None:
            fx = Fixture(id=r.id, organisation_id=org_id, source="playhq",
                         is_final=bool(r.is_final) or None)
            db.add(fx)
            created += 1
        else:
            updated += 1
        fx.grade_id = r.grade_id
        if team and not fx.team_id:
            fx.team_id = team.id
        fx.playhq_id = r.playhq_id
        fx.round = r.round_name
        fx.played_on = r.played_at
        fx.start_time = (r.start_time or "")[:5] or None
        fx.home_team, fx.away_team = r.home_team, r.away_team
        fx.home_away = "BYE" if r.is_bye else r.our_side
        fx.opponent_name = r.opp_club_name
        fx.venue = r.venue_name or r.venue
        fx.status = "FINAL" if r.status == "FINAL" else ("BYE" if r.is_bye else "UPCOMING")
    await db.flush()
    return {"created": created, "updated": updated, "fixtures": len(rows)}


# ── Squads ───────────────────────────────────────────────────────────────────

# Checked in this order, and the team's own name before its grade's: a grade
# called "Premier C Reserves" is a reserves grade whatever the "Premier" says.
_RANK_WORDS = [
    (re.compile(r"\b(reserves?|seconds?|2nds?|b[\s-]?grade)\b", re.I), 2),
    (re.compile(r"\b(thirds?|3rds?|c[\s-]?grade)\b", re.I), 3),
    (re.compile(r"\b(seniors?|premier|firsts?|1sts?|a[\s-]?grade)\b", re.I), 1),
]
_CAT_RANK = {"senior": 0, "womens": 10, "masters": 20, "colts": 30, "integrated": 40}


def _team_order(name: str, grade_name: str) -> tuple:
    cat = suggest_category(f"{name} {grade_name}")
    word = next((n for rx, n in _RANK_WORDS if rx.search(name)), None)
    if word is None:
        word = next((n for rx, n in _RANK_WORDS if rx.search(grade_name or "")), 5)
    under = re.search(r"\b(?:u|under[\s-]?)(\d+)", f"{name} {grade_name}", re.I)
    return (_CAT_RANK.get(cat, 50), word, -int(under.group(1)) if under else 0, name.lower())


async def seed_teams(db: AsyncSession, org_id) -> dict:
    """One side per team PlayHQ lists for the club in its latest season.

    Skip-don't-replace: a side the club already has by name is left exactly as
    it is, so pressing it twice changes nothing and never undoes a hand-set
    order. New sides are ordered senior men first, then women's, masters and
    the colts oldest to youngest, which is the usual order of a football club's
    sides; the club can move them afterwards."""
    latest = (await db.execute(text("""
        SELECT s.id FROM seasons s JOIN afl_teams t ON t.season_id = s.id
         WHERE s.organisation_id = :org
         ORDER BY s.year DESC NULLS LAST, s.name DESC LIMIT 1
    """), {"org": str(org_id)})).scalar()
    if not latest:
        return {"created": 0, "teams": 0}
    teams = (await db.execute(text("""
        SELECT t.name, t.grade_id, t.playhq_id, gr.name AS grade_name
          FROM afl_teams t LEFT JOIN grades gr ON gr.id = t.grade_id
         WHERE t.organisation_id = :org AND t.season_id = :s
    """), {"org": str(org_id), "s": latest})).fetchall()
    existing = (await db.execute(select(Team).where(Team.organisation_id == org_id))).scalars().all()
    have = {t.name.lower(): t for t in existing}
    top = max([t.sequence or 0 for t in existing] or [0])
    created = 0
    for t in sorted(teams, key=lambda t: _team_order(t.name, t.grade_name or "")):
        cur = have.get(t.name.lower())
        if cur:
            if not cur.grade_id and t.grade_id:
                cur.grade_id = t.grade_id
            continue
        top += 1
        row = Team(id=uuid.uuid4(), organisation_id=org_id, name=t.name, sequence=top,
                   grade_id=t.grade_id, source="auto", playhq_id=t.playhq_id)
        db.add(row)
        have[t.name.lower()] = row
        created += 1
    await db.flush()
    return {"created": created, "teams": len(teams)}


async def set_squad(db: AsyncSession, org_id, player: Player, team_id: Optional[uuid.UUID]) -> None:
    """Put a player in one side's squad (or none), mirrored into
    ``team_members`` the way cricket's squad board keeps it, so the
    Directory's squad filter and this board agree."""
    player.squad_team_id = team_id
    await db.execute(delete(TeamMember).where(TeamMember.player_id == player.id,
                                              TeamMember.organisation_id == org_id))
    if team_id:
        db.add(TeamMember(team_id=team_id, player_id=player.id, organisation_id=org_id))


async def auto_assign(db: AsyncSession, org_id, *, only_unassigned: bool = True) -> dict:
    """File every player with no squad under the side they played most for in
    the latest season, read off the games' grades. A player who played for
    nobody this season is left where they are."""
    rows = (await db.execute(text("""
        WITH latest AS (
            SELECT s.year FROM seasons s WHERE s.organisation_id = :org AND s.year IS NOT NULL
             ORDER BY s.year DESC LIMIT 1
        )
        SELECT l.player_id, g.grade_id, COUNT(*) AS n
          FROM afl_player_game_lines l
          JOIN afl_game_details d ON d.game_id = l.game_id AND l.side = d.our_side
          JOIN games g ON g.id = l.game_id
          JOIN grades gr ON gr.id = g.grade_id
          JOIN seasons s ON s.id = gr.season_id
          JOIN players p ON p.id = l.player_id AND p.organisation_id = :org
         WHERE s.organisation_id = :org AND s.year = (SELECT year FROM latest) AND l.played
         GROUP BY l.player_id, g.grade_id
    """), {"org": str(org_id)})).fetchall()
    ranks = await rules_svc.grade_ranks(db, org_id)
    teams = (await db.execute(select(Team).where(Team.organisation_id == org_id, Team.is_active.is_(True)))).scalars().all()
    by_seq = {t.sequence: t for t in teams}
    by_grade = {str(t.grade_id): t for t in teams if t.grade_id}
    best: dict[str, tuple[int, uuid.UUID]] = {}
    for pid, gid, n in rows:
        team = by_grade.get(str(gid)) or by_seq.get(ranks.get(str(gid)))
        if not team:
            continue
        k = str(pid)
        if k not in best or n > best[k][0]:
            best[k] = (n, team.id)
    assigned = 0
    for pid, (_, tid) in best.items():
        p = await db.get(Player, uuid.UUID(pid))
        if not p or p.status == "inactive" or (only_unassigned and p.squad_team_id):
            continue
        await set_squad(db, org_id, p, tid)
        assigned += 1
    await db.flush()
    return {"assigned": assigned}


# ── One fixture's facts ──────────────────────────────────────────────────────

async def fixture_facts(db: AsyncSession, org_id, fx: Fixture) -> rules_svc.FixtureFacts:
    grade = await db.get(Grade, fx.grade_id) if fx.grade_id else None
    season = await db.get(Season, grade.season_id) if grade else None
    team = await db.get(Team, fx.team_id) if fx.team_id else None
    year = season.year if season else (fx.played_on.year if fx.played_on else None)
    if year is not None:
        ids = (await db.execute(select(Season.id).where(
            Season.organisation_id == org_id, Season.year == year))).scalars().all()
        season_ids = [str(i) for i in ids]
    else:
        season_ids = [str(season.id)] if season else []
    is_final = bool(fx.is_final) if fx.is_final is not None else "final" in (fx.round or "").lower()
    return rules_svc.FixtureFacts(
        fixture_id=str(fx.id), played_on=fx.played_on,
        grade_id=str(grade.id) if grade else None,
        grade_name=grade.name if grade else None,
        category=category_of(grade.name, grade.category) if grade else None,
        team_id=str(team.id) if team else None,
        team_sequence=team.sequence if team else None,
        is_final=is_final, season_ids=season_ids, season_year=year,
        fees_season_id=str(season.id) if season else None,
    )


def fixture_out(fx: Fixture, team: Optional[Team] = None, grade: Optional[Grade] = None,
                picked: int = 0) -> dict:
    return {
        "id": str(fx.id),
        "source": fx.source,
        "label": fx.label,
        "round": fx.round,
        "played_on": fx.played_on.isoformat() if fx.played_on else None,
        "start_time": fx.start_time,
        "home_team": fx.home_team,
        "away_team": fx.away_team,
        "home_away": fx.home_away,
        "opponent_name": fx.opponent_name,
        "venue": fx.venue,
        "status": fx.status,
        "is_final": fx.is_final,
        "team_id": str(fx.team_id) if fx.team_id else None,
        "team_name": team.name if team else None,
        "grade_id": str(fx.grade_id) if fx.grade_id else None,
        "grade_name": grade.name if grade else None,
        "picked": picked,
    }


# ── Availability ─────────────────────────────────────────────────────────────

async def availability_on(db: AsyncSession, org_id, day: Optional[date]) -> dict[str, dict]:
    """Every player's answer for one date: an explicit answer wins over a
    period covering the date, which is the rule the cricket matrix keeps."""
    if not day:
        return {}
    out: dict[str, dict] = {}
    from app.routers.availability import resolve_period_statuses
    periods = await resolve_period_statuses(db, org_id, [day])
    for pid, info in (periods.get(day.isoformat()) or {}).items():
        out[pid] = {"status": info["status"], "note": info.get("reason"), "source": "period"}
    rows = (await db.execute(select(PlayerAvailability).where(
        PlayerAvailability.organisation_id == org_id, PlayerAvailability.avail_date == day,
    ))).scalars().all()
    for a in rows:
        out[str(a.player_id)] = {"status": a.status, "note": a.note, "source": a.source or "admin"}
    return out


# ── The pool ─────────────────────────────────────────────────────────────────

async def selection(db: AsyncSession, org: Organisation, fx: Fixture) -> dict:
    """Everything the board needs for one fixture."""
    facts = await fixture_facts(db, org.id, fx)
    team = await db.get(Team, fx.team_id) if fx.team_id else None
    grade = await db.get(Grade, fx.grade_id) if fx.grade_id else None
    players = list((await db.execute(select(Player).where(
        Player.organisation_id == org.id, Player.is_player.is_(True),
    ).order_by(func.coalesce(Player.display_name_override, Player.name)))).scalars().all())

    games = await rules_svc.season_games(db, org.id, facts.season_ids)
    ranks = await rules_svc.grade_ranks(db, org.id)
    result = await rules_svc.evaluate(db, org, facts, players, games=games, ranks=ranks)
    avail = await availability_on(db, org.id, fx.played_on)

    teams = (await db.execute(select(Team).where(Team.organisation_id == org.id)
                              .order_by(Team.sequence))).scalars().all()
    team_by_id = {t.id: t for t in teams}

    last_played = dict((await db.execute(text("""
        SELECT l.player_id, MAX(g.played_at)
          FROM afl_player_game_lines l
          JOIN afl_game_details d ON d.game_id = l.game_id AND l.side = d.our_side
          JOIN games g ON g.id = l.game_id
          JOIN players p ON p.id = l.player_id AND p.organisation_id = :org
         WHERE l.played GROUP BY l.player_id
    """), {"org": str(org.id)})).fetchall())

    by_player: dict[str, list] = {}
    for g in games:
        by_player.setdefault(str(g.player_id), []).append(g)

    # Picked for another fixture on the same day — a player can't take the
    # field twice on one afternoon.
    clashes: dict[str, str] = {}
    if fx.played_on:
        rows = (await db.execute(text("""
            SELECT s.player_id, COALESCE(t.name, f.opponent_name, 'another side')
              FROM afl_lineup_slots s
              JOIN fixtures f ON f.id = s.fixture_id
              LEFT JOIN teams t ON t.id = f.team_id
             WHERE s.organisation_id = :org AND f.played_on = :d AND f.id <> :fx
        """), {"org": str(org.id), "d": fx.played_on, "fx": str(fx.id)})).fetchall()
        clashes = {str(p): n for p, n in rows}

    pool = []
    for p in players:
        pid = str(p.id)
        mine = sorted(by_player.get(pid, []), key=lambda g: g.played_at or date.min, reverse=True)
        squad = team_by_id.get(p.squad_team_id) if p.squad_team_id else None
        pool.append({
            "id": pid,
            "name": p.display_name,
            "photo_url": p.photo_url,
            "status": p.status,
            "positions": list(p.skill_positions or []),
            "jumper": getattr(p, "shirt_number", None),
            "age": age_on(p.date_of_birth, fx.played_on) if p.date_of_birth else None,
            "squad_id": str(squad.id) if squad else None,
            "squad_name": squad.name if squad else None,
            "squad_sequence": squad.sequence if squad else None,
            "availability": (avail.get(pid) or {}).get("status", "NO_RESPONSE"),
            "availability_note": (avail.get(pid) or {}).get("note"),
            "games": len(mine),
            "games_here": sum(1 for g in mine if facts.grade_id and str(g.grade_id) == facts.grade_id),
            "goals": sum(g.goals or 0 for g in mine),
            "best_on_ground": sum(1 for g in mine if g.bog_ranking == 1),
            "recent": [{"date": g.played_at.isoformat() if g.played_at else None,
                        "goals": g.goals or 0, "bog": g.bog_ranking} for g in mine[:5]],
            "last_played": last_played.get(p.id).isoformat() if last_played.get(p.id) else None,
            "clash": clashes.get(pid),
            "flags": result.flags.get(pid, []),
        })

    slots = (await db.execute(select(AflLineupSlot).where(AflLineupSlot.fixture_id == fx.id)
                              .order_by(AflLineupSlot.sort_order))).scalars().all()
    return {
        "fixture": fixture_out(fx, team, grade),
        "facts": {"is_final": facts.is_final, "grade_name": facts.grade_name},
        "team_size": result.team_size,
        "formation": formation(result.team_size["field"]),
        "rules": [r for r in result.rules],
        "lineup": [slot_out(s) for s in slots],
        "players": pool,
        "teams": [{"id": str(t.id), "name": t.name, "sequence": t.sequence} for t in teams],
        "dormancy_months": org.dormancy_months or 24,
    }


def slot_out(s: AflLineupSlot) -> dict:
    return {"player_id": str(s.player_id), "slot": s.slot, "sort_order": s.sort_order,
            "is_captain": s.is_captain, "is_vice_captain": s.is_vice_captain}


class LineupError(ValueError):
    pass


def validate_lineup(items: list[dict], team_size: dict, owned: set[str]) -> list[dict]:
    """The side as it will be stored, or a LineupError saying what is wrong.
    Every rule here is structural — the league's rules are the rules engine's."""
    allowed = set(field_slots(team_size["field"]))
    seen_players: set[str] = set()
    seen_slots: set[str] = set()
    bench = emg = caps = vcs = 0
    out = []
    for i, it in enumerate(items):
        pid = str(it.get("player_id") or "")
        slot = str(it.get("slot") or "").upper()
        if pid not in owned:
            raise LineupError("A player on this side isn't one of the club's")
        if pid in seen_players:
            raise LineupError("A player is named twice")
        seen_players.add(pid)
        if slot == BENCH:
            bench += 1
        elif slot == EMERGENCY:
            emg += 1
        elif slot in allowed:
            if slot in seen_slots:
                raise LineupError(f"Two players are named at {SLOT_LABELS.get(slot, slot)}")
            seen_slots.add(slot)
        else:
            raise LineupError(f"{slot or 'That position'} isn't a position on a {team_size['field']}-a-side ground")
        cap, vc = bool(it.get("is_captain")), bool(it.get("is_vice_captain"))
        if cap and vc:
            raise LineupError("A player can't be captain and vice-captain")
        if (cap or vc) and slot == EMERGENCY:
            raise LineupError("An emergency can't be captain or vice-captain")
        caps += cap
        vcs += vc
        out.append({"player_id": pid, "slot": slot, "sort_order": int(it.get("sort_order") or i),
                    "is_captain": cap, "is_vice_captain": vc})
    if bench > team_size["bench"]:
        raise LineupError(f"{bench} on the bench, {team_size['bench']} allowed")
    if emg > team_size["emergencies"]:
        raise LineupError(f"{emg} emergencies, {team_size['emergencies']} allowed")
    if caps > 1:
        raise LineupError("Only one captain")
    if vcs > 2:
        raise LineupError("At most two vice-captains")
    return out


def team_sheet(fixture: dict, lineup: list[dict], names: dict[str, str], team_size: dict) -> str:
    """The side the way a football club writes it on the noticeboard:
    B / HB / C / HF / F / Foll, then the interchange and the emergencies."""
    by_slot = {x["slot"]: x for x in lineup}

    def nm(x):
        n = names.get(x["player_id"], "?")
        if x.get("is_captain"):
            n += " (c)"
        elif x.get("is_vice_captain"):
            n += " (vc)"
        return n

    head = fixture.get("team_name") or "Our side"
    vs = fixture.get("opponent_name")
    when = fixture.get("played_on")
    lines = [f"{head}{' v ' + vs if vs else ''}" + (f" · {fixture['round']}" if fixture.get("round") else "")
             + (f" · {when}" if when else "")]
    tags = {"B": "B", "HB": "HB", "C": "C", "HF": "HF", "F": "F", "FOL": "Foll"}
    for line in formation(team_size["field"]):
        names_on = [nm(by_slot[s["slot"]]) if s["slot"] in by_slot else "-" for s in line["slots"]]
        lines.append(f"{tags[line['key']]}: " + ", ".join(names_on))
    bench = sorted([x for x in lineup if x["slot"] == BENCH], key=lambda x: x["sort_order"])
    emg = sorted([x for x in lineup if x["slot"] == EMERGENCY], key=lambda x: x["sort_order"])
    if bench:
        lines.append("I/C: " + ", ".join(nm(x) for x in bench))
    if emg:
        lines.append("Emg: " + ", ".join(nm(x) for x in emg))
    return "\n".join(lines)


async def previous_lineup(db: AsyncSession, org_id, fx: Fixture) -> list[dict]:
    """The side picked for this team's most recent earlier fixture — what a
    selector starts from on Thursday night."""
    if not fx.team_id:
        return []
    prev = (await db.execute(text("""
        SELECT f.id FROM fixtures f
         WHERE f.organisation_id = :org AND f.team_id = :team AND f.id <> :fx
           AND f.played_on < COALESCE(:d, CURRENT_DATE)
           AND EXISTS (SELECT 1 FROM afl_lineup_slots s WHERE s.fixture_id = f.id)
         ORDER BY f.played_on DESC LIMIT 1
    """), {"org": str(org_id), "team": str(fx.team_id), "fx": str(fx.id), "d": fx.played_on})).scalar()
    if not prev:
        return []
    rows = (await db.execute(select(AflLineupSlot).where(AflLineupSlot.fixture_id == prev)
                             .order_by(AflLineupSlot.sort_order))).scalars().all()
    return [slot_out(s) for s in rows]
