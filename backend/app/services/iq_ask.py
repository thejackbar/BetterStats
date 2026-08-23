"""BetterIQ — natural-language questions, answered with tools over the club's data.

A grounded agentic Q&A. Instead of stuffing a fixed summary into the prompt (which
can't know every player by name, a specific grade, or recent form), we give Claude
a small set of tools that query the data we already compute — find a player, read
their form, pull team record/par, opening partnerships, who's in or out of form —
and let it call them to answer. Org-scoping is injected server-side; the model only
supplies a player_id or grade name. Reuses the Anthropic client pattern from the
yearbook narrative generator; gated on the IQ module + MANAGE_IQ at the router and
rate-limited at the route. Degrades gracefully when the key/package is absent.
"""
from __future__ import annotations

import json
import logging
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import async_session_maker
from app.services import iq_opponent, iq_players, iq_team, iq_trends
from app.services import iq as iq_service
from app.services.aggregations import get_player_by_opposition
from app.services.bowling_style import bowling_class, bowling_label
from app.services.llm_text import strip_em_dashes

logger = logging.getLogger(__name__)

# Capable model for the tool-use reasoning + synthesis. Tunable; lower to
# claude-sonnet-4-6 / claude-haiku-4-5 for cheaper/faster at some quality cost.
MODEL = "claude-opus-4-8"
MAX_TOKENS = 1500
MAX_STEPS = 8          # tool-call round trips before we force a final answer
                       # (fixture questions chain upcoming_fixtures → report →
                       # squad → danger players, so they need more room than 6)
MAX_HISTORY_TURNS = 8  # prior Q&A pairs carried in so follow-ups keep their subject
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-", re.I)

_SYSTEM = (
    "You are a cricket analyst for a grassroots Australian cricket club. Answer the "
    "user's question about THIS club using the tools provided. Never invent players, "
    "clubs or numbers. Find a player with find_players before asking for their detail; "
    "use grades to learn the exact grade names before filtering by grade. Read the "
    "tool results and answer in a few sentences, plain Australian cricket-club tone "
    "(no corporate words). Never use the \", \" (em dash) character anywhere in your "
    "answer; use a comma, full stop, or parentheses instead. Numbers in the tool "
    "results are the truth.\n"
    "Scope and samples:\n"
    "- Every tool result echoes a 'scope' (which season, or all-time). Always say "
    "which scope your figures come from ('across all seasons we hold', 'in 2024/25', "
    "'this season'), and don't blend scopes without saying so. team_overview defaults "
    "to all-time; form_movers and current_squad default to the latest season; all "
    "three take an optional season (e.g. '2024/25').\n"
    "- Treat any figure built from fewer than about 6 innings or 6 wickets as a "
    "small sample: say so plainly rather than leaning on it.\n"
    "- If a tool comes back with 'ambiguous' and a list of players, don't guess "
    "which one was meant. Ask the user which player they mean, naming the options.\n"
    "Selection sense:\n"
    "- For picking/dropping/promoting/relegating between teams, judge by who is "
    "actually IN that side now, each player's 'squad' (their BetterSelect team like "
    "'1st XI', '2nd XI') is the selection signal. Don't guess the XI from season "
    "averages alone.\n"
    "- A club's grade and its same-numbered XI are usually the same team, so '2nd XI' "
    "and '2nd Grade' mean the same side. If a grade name returns nothing, filter the "
    "full current squad by 'squad' instead.\n"
    "- Wicketkeepers ('keeper': true) earn their spot with the gloves, so don't call a "
    "keeper a 'specialist batter' or judge them on runs alone; weigh their keeping.\n"
    "- Genuine bowlers and all-rounders earn their spot with wickets, so a low batting "
    "average isn't a reason to drop them.\n"
    "Bowling sense:\n"
    "- Every bowler's style is given (bowling_style like 'Off spin' or 'Right-arm "
    "fast-medium', and bowling_class 'pace' or 'spin'). Describe a bowler by their real "
    "style: never call a spinner a 'seamer', 'quick', 'third seamer' or similar, and "
    "only call a bowler 'sharp', 'quick', 'express' or 'pacy' when their bowling_class is "
    "'pace'. A spinner is 'crafty' or 'flighted', not 'sharp'.\n"
    "- When asked to pick or balance a bowling group, weigh the pace/spin mix (a good "
    "attack usually wants both), not wicket counts alone, and label each suggestion "
    "with its real style.\n"
    "Combinations:\n"
    "- To judge whether two players combine well in the same side (do they play well "
    "together / win together), use players_together. It gives the team's record when "
    "both play vs when only one does.\n"
    "Upcoming games and the opposition:\n"
    "- For any question about an upcoming match ('who should we pick for the 1st XI "
    "game', 'who do we play next', 'how do we beat them'), start with "
    "upcoming_fixtures to find the fixture, its team/grade and opponent. Then use "
    "opposition_report for our head-to-head and which of OUR players bat/bowl well "
    "against them, current_squad for the side in question, and "
    "opponent_danger_players for their in-form threats.\n"
    "- Keep selection suggestions TEAM-RELEVANT: each performer carries their "
    "'squad' (the side they're currently picked in). For a 1st XI fixture, weigh "
    "players in or around the 1st XI; a lower-grade player's strong record against "
    "this opponent is worth a mention as a possible promotion, never an automatic "
    "pick over the side's regulars.\n"
    "- If opponent_danger_players says the dossier is still building, answer now "
    "from opposition_report and add that the deeper scout (their current-season "
    "form) will be ready if they ask again in a minute, or on the BetterIQ "
    "Opposition page.\n"
    "- If a fixture's opponent has no linked history (has_history false), say the "
    "club can be linked via 'Match club' on the BetterIQ Opposition page to unlock "
    "the head-to-head.\n"
    "If the tools don't cover what was asked, say so plainly and point to where in "
    "BetterIQ to look (Opposition scout for an opponent, Player search for one player, "
    "Team analysis for the side)."
)


# ─── tools ────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "find_players",
        "description": "Find players in the club by name (or list the whole roster when no query). Returns each player's id, role, whether they keep wicket, their bowling_style (e.g. 'Off spin', 'Right-arm fast-medium') and bowling_class ('pace' or 'spin'), their selection squad (their BetterSelect team, e.g. '1st XI'), and career matches/runs/wickets. Use this to get a player_id before calling player_detail or player_vs_club.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "part of a player's name; omit to list everyone"}},
        },
    },
    {
        "name": "player_detail",
        "description": "One player's profile: career batting & bowling, recent form (last innings), starts/conversion, best batting position, who they dominate or struggle against, and a rising/declining verdict. Needs the player_id from find_players.",
        "input_schema": {
            "type": "object",
            "properties": {"player_id": {"type": "string"}},
            "required": ["player_id"],
        },
    },
    {
        "name": "player_vs_club",
        "description": "One player's record against each opposition club (games, win/loss, runs, batting average, wickets, bowling average). Optionally filter to one club name. Needs the player_id.",
        "input_schema": {
            "type": "object",
            "properties": {"player_id": {"type": "string"}, "club": {"type": "string", "description": "optional opponent club name to filter to"}},
            "required": ["player_id"],
        },
    },
    {
        "name": "players_together",
        "description": "Two players' record AS A PAIR (all-time): the team's win/loss/draw record and win% in games BOTH of them played, how that compares to games only one of them played (the selection lift), and each player's batting & bowling output in their shared games. Use to judge whether two players combine well in the same side, or to answer 'how do X and Y go together'. Pass two player ids (or names). Get ids from find_players.",
        "input_schema": {
            "type": "object",
            "properties": {
                "player_a": {"type": "string", "description": "first player's id or name"},
                "player_b": {"type": "string", "description": "second player's id or name"},
            },
            "required": ["player_a", "player_b"],
        },
    },
    {
        "name": "team_overview",
        "description": "The club's record and approach: win rate, home/away, batting-first vs chasing win rate, par first-innings score, how we win and lose, score-band win rates, batting & bowling profile, best opening partnerships and our typical opening stand. Optionally scope to one grade and/or one season; without a season the figures are ALL-TIME.",
        "input_schema": {
            "type": "object",
            "properties": {
                "grade": {"type": "string", "description": "optional grade name (from grades)"},
                "season": {"type": "string", "description": "optional season, e.g. '2024/25' or '2024'; omit for all-time"},
            },
        },
    },
    {
        "name": "form_movers",
        "description": "Who is in or out of form in a season: batters and bowlers rising or sliding vs their career baseline, plus emerging players. Use for 'who's in/out of form' questions. Defaults to the latest season; pass a season to look at an earlier one.",
        "input_schema": {
            "type": "object",
            "properties": {"season": {"type": "string", "description": "optional season, e.g. '2023/24'; omit for the latest season"}},
        },
    },
    {
        "name": "current_squad",
        "description": "Players who've played in a season with their form (runs/average, wickets/average), their selection squad (BetterSelect team like '1st XI'/'2nd XI'), role, whether they keep wicket, and their bowling_style (e.g. 'Off spin') and bowling_class ('pace' or 'spin'). Returns the list of squads present too. Use for selection questions: a player's SQUAD is which side they're picked in, and a grade and its same-numbered XI are usually the same team, so filter by squad to answer 'who's in the 2nd XI'. Optionally pass a grade name; if it matches nothing it falls back to the whole squad. Defaults to the latest season; pass a season for an earlier one.",
        "input_schema": {
            "type": "object",
            "properties": {
                "grade": {"type": "string", "description": "optional grade name (from grades)"},
                "season": {"type": "string", "description": "optional season, e.g. '2023/24'; omit for the latest season"},
            },
        },
    },
    {
        "name": "grades",
        "description": "The grade (team) names the club fields, so you can filter other tools by an exact grade name.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "upcoming_fixtures",
        "description": "The club's upcoming fixtures: date, team/grade, opponent, venue, home/away, plus a fixture_id and whether we hold history against that opponent (has_history). Use this FIRST for any question about an upcoming game ('who should we pick for the 1st XI game', 'who do we play next') to identify the fixture, its team and its opponent, then feed the fixture_id into opposition_report / opponent_danger_players.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "opposition_report",
        "description": "Our held record against ONE opponent club: head-to-head (won/lost, recent form), which of OUR players bat and bowl well against them (each with their current selection squad, for team relevance), our bowler → their batter repeat dismissals, our best/worst venues vs them, and what happened last meeting. Pass a fixture_id from upcoming_fixtures OR an opponent club name. Optionally scope to a grade name (from grades).",
        "input_schema": {
            "type": "object",
            "properties": {
                "fixture_id": {"type": "string", "description": "fixture id from upcoming_fixtures"},
                "opponent": {"type": "string", "description": "opponent club name (or opp_key) when not asking about a specific fixture"},
                "grade": {"type": "string", "description": "optional grade name to scope the record to"},
            },
        },
    },
    {
        "name": "opponent_danger_players",
        "description": "The opponent's CURRENT-SEASON danger batters and bowlers from the live scouting dossier: their form, averages, record against us, and a suggested plan for each. Pass a fixture_id or an opponent club name. If the dossier hasn't been built yet it starts building in the background and returns status 'building'. Answer from opposition_report in the meantime and say the deeper scout will be ready shortly.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fixture_id": {"type": "string", "description": "fixture id from upcoming_fixtures"},
                "opponent": {"type": "string", "description": "opponent club name (or opp_key)"},
            },
        },
    },
]


def _round(v, nd=2):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


def _scope_echo(*, season: str | None = None, grade: str | None = None, basis: str | None = None) -> dict:
    """The resolved scope echoed on every tool result, so the model can state
    which season (or all-time) its figures come from."""
    return {
        "season": season or "all seasons",
        "grade": grade or "all grades",
        "basis": basis or ("season" if season else "all-time"),
    }


_YEAR4 = re.compile(r"(\d{4})")
_YEAR2 = re.compile(r"\b(\d{2})\s*[/-]\s*\d{2}\b")


def _season_label(row: dict) -> str:
    y = row.get("year")
    return f"{y}/{str(y + 1)[-2:]}" if y is not None else (row.get("name") or "season")


def _parse_season_year(value: str) -> int | None:
    """'2024/25', '2024-25' or '2024' → 2024 (Season.year is the START year);
    '24/25' → 2024."""
    m = _YEAR4.search(value)
    if m:
        return int(m.group(1))
    m = _YEAR2.search(value)
    if m:
        return 2000 + int(m.group(1))
    return None


async def _resolve_season(session: AsyncSession, org_id: str, season: str | None) -> tuple[str | None, str | None]:
    """Resolve a model-supplied season label ('2024/25', '2024', a stored season
    name) to a (season_row_id, display_label) pair. Any ONE row of the real
    season is enough — the IQ season filter year-expands it to every sibling row
    of the same year (see iq_filters). Returns (None, None) when no season was
    asked for, and (None, <as typed>) when the label matched nothing we hold, so
    the caller says so instead of silently answering from a different scope."""
    season = (season or "").strip()
    if not season:
        return None, None
    rows = await iq_team.team_seasons(session, org_id)
    sl = season.lower()
    named = [r for r in rows if sl == (r["name"] or "").lower()]
    if named:
        return named[0]["season_id"], _season_label(named[0])
    year = _parse_season_year(season)
    if year is not None:
        for r in rows:
            if r["year"] == year:
                return r["season_id"], _season_label(r)
    return None, season


async def _resolve_pid(session: AsyncSession, org_id: str, value: str) -> str | dict | None:
    """Accept a player_id or a name; return the id when it resolves to ONE
    player, None when nothing matches, or {"ambiguous": [candidates]} when
    several players match — the calling tool returns that to the model, whose
    instructions say to ask the user which player they meant rather than guess."""
    value = (value or "").strip()
    if not value:
        return None
    if _UUID.match(value):
        return value
    players = await iq_players.list_all_players(session, org_id)
    vl = value.lower()
    exact = [p for p in players if (p["name"] or "").lower() == vl]
    if len(exact) == 1:
        return exact[0]["player_id"]
    matches = exact or [p for p in players if vl in (p["name"] or "").lower()]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]["player_id"]
    return {"ambiguous": [
        {"player_id": p["player_id"], "name": p["name"], "squad": p.get("squad"),
         "matches": p["matches"], "last_year": p["last_year"]}
        for p in matches[:8]
    ]}


_AMBIGUOUS_NOTE = ("Several players match that name. Ask the user which one they "
                   "meant, then call again with the exact player_id.")


async def _tool_find_players(session, org_id, *, query=None):
    players = await iq_players.list_all_players(session, org_id)
    if query:
        q = query.strip().lower()
        players = [p for p in players if q in (p["name"] or "").lower()]
    players = players[:40]
    return {"count": len(players), "scope": _scope_echo(), "players": [
        {"player_id": p["player_id"], "name": p["name"], "role": p.get("player_role"),
         "keeper": p.get("is_keeper"), "bowling_style": p.get("bowling_style"), "bowling_class": p.get("bowling_class"),
         "squad": p.get("squad"),
         "matches": p["matches"], "runs": p["runs"], "wickets": p["wickets"], "last_year": p["last_year"]}
        for p in players
    ]}


async def _tool_player_detail(session, org_id, *, player_id):
    pid = await _resolve_pid(session, org_id, player_id)
    if isinstance(pid, dict):
        return {"ambiguous": pid["ambiguous"], "note": _AMBIGUOUS_NOTE}
    if not pid:
        return {"error": "No player found for that id/name. Call find_players first."}
    # Role / keeper / bowling style from the player row (cheap; so a keeper isn't
    # read as a bat and a spinner isn't read as a seamer).
    role = keeper = bstyle = bclass = None
    try:
        meta = (await session.execute(
            text("SELECT player_role, skill_positions, bowling_action, bowling_type FROM players WHERE id = CAST(:pid AS UUID)"),
            {"pid": pid},
        )).mappings().first()
        if meta:
            sp = meta["skill_positions"] or []
            role = meta["player_role"]
            keeper = ("WKT" in sp) or bool(role and "KEEP" in (role or "").upper())
            bstyle = bowling_label(meta["bowling_action"], meta["bowling_type"])
            bclass = bowling_class(meta["bowling_type"])
    except Exception:
        pass
    try:
        trend = await iq_trends.player_trend(session, org_id, pid)
    except Exception:
        logger.exception("iq_ask player_detail trend failed")
        trend = None
    if not trend:
        return {"player_id": pid, "role": role, "keeper": keeper,
                "bowling_style": bstyle, "bowling_class": bclass,
                "note": "Couldn't load this player's full profile. Use find_players / current_squad numbers instead."}
    deep = None
    try:
        deep = await iq_trends.player_deep_dive(session, org_id, pid)
    except Exception:
        logger.exception("iq_ask player_detail deep failed")
    b = (trend.get("career") or {}).get("batting") or {}
    bo = (trend.get("career") or {}).get("bowling") or {}
    recent = [(x.get("runs"), bool(x.get("not_out"))) for x in (trend.get("recent_form") or {}).get("batting", [])][:6]
    out = {
        "name": (trend.get("player") or {}).get("name"),
        "role": role, "keeper": keeper,
        "bowling_style": bstyle, "bowling_class": bclass,
        "scope": _scope_echo(),  # career figures span every season we hold
        "verdict": trend.get("verdict"),
        "batting": {"runs": b.get("total_runs"), "average": _round(b.get("average")), "100s": b.get("hundreds"), "50s": b.get("fifties")},
        "bowling": {"wickets": bo.get("total_wickets"), "average": _round(bo.get("average")), "economy": _round(bo.get("economy"))},
        "recent_innings": [f"{r}{'*' if no else ''}" for r, no in recent],
    }
    if deep:
        conv = deep.get("conversion") or {}
        out["conversion"] = {"reach25_pct": conv.get("start_pct"), "convert25to50_pct": conv.get("convert_25_to_50"), "50s": conv.get("fifties"), "100s": conv.get("hundreds")}
        byopp = deep.get("by_opposition") or {}
        out["dominates"] = [{"club": o["name"], "runs": o["runs"], "avg": _round(o.get("average"))} for o in (byopp.get("best") or [])[:3]]
        out["struggles_vs"] = [{"club": o["name"], "runs": o["runs"], "avg": _round(o.get("average"))} for o in (byopp.get("worst") or [])[:3]]
        bestpos = max((p for p in (deep.get("by_position") or []) if (p.get("innings") or 0) >= 3 and p.get("average") is not None), key=lambda p: p["average"], default=None)
        if bestpos:
            out["best_position"] = {"bucket": bestpos.get("bucket") or bestpos.get("position"), "average": _round(bestpos.get("average"))}
        if deep.get("reliability"):
            out["reliability"] = deep["reliability"].get("profile")
        if deep.get("scouting_note"):
            out["note"] = deep["scouting_note"]
    return out


async def _tool_player_vs_club(session, org_id, *, player_id, club=None):
    pid = await _resolve_pid(session, org_id, player_id)
    if isinstance(pid, dict):
        return {"ambiguous": pid["ambiguous"], "note": _AMBIGUOUS_NOTE}
    if not pid:
        return {"error": "No player found for that id/name."}
    rows = await get_player_by_opposition(session, pid) or []
    if club:
        cl = club.strip().lower()
        rows = [r for r in rows if cl in (r["opposition"] or "").lower()]
    rows = rows[:20]
    return {"scope": _scope_echo(), "opponents": [
        {"club": r["opposition"], "games": r["games"], "wins": r["wins"], "losses": r["losses"],
         "runs": r["total_runs"], "bat_avg": _round(r.get("batting_average")), "high": r.get("high_score"),
         "wickets": r["wickets"], "bowl_avg": _round(r.get("bowling_average"))}
        for r in rows
    ]}


async def _tool_players_together(session, org_id, *, player_a, player_b):
    a = await _resolve_pid(session, org_id, player_a)
    b = await _resolve_pid(session, org_id, player_b)
    for res in (a, b):
        if isinstance(res, dict):
            return {"ambiguous": res["ambiguous"], "note": _AMBIGUOUS_NOTE}
    if not a or not b:
        return {"error": "Couldn't find one of those players. Call find_players first."}
    if a == b:
        return {"error": "Those are the same player, pass two different players."}
    out = await iq_team.pair_synergy(session, org_id, a, b)
    if isinstance(out, dict):
        out.setdefault("scope", _scope_echo())
    return out


async def _tool_team_overview(session, org_id, *, grade=None, season=None):
    season_id, season_label = await _resolve_season(session, org_id, season)
    ov = await iq_team.team_overview(session, org_id, season_id=season_id, grade_id=grade)
    rec = ov.get("record") or {}
    inn = ov.get("innings") or {}
    bat = ov.get("batting") or {}
    bowl = ov.get("bowling") or {}
    pairs = ov.get("batting_pairs") or []
    starts = ov.get("starts") or {}
    out = {
        "scope": _scope_echo(season=season_label if season_id else None, grade=grade),
        "grade": grade or "all grades",
        "record": {"wins": rec.get("wins"), "losses": rec.get("losses"), "draws": rec.get("draws"), "matches": rec.get("matches"), "win_pct": rec.get("win_pct")},
        "bat_first_win_pct": (inn.get("bat_first") or {}).get("win_pct"),
        "chasing_win_pct": (inn.get("chasing") or {}).get("win_pct"),
        "par_score": (inn.get("par") or {}).get("par_score"),
        "how_we_win": (ov.get("how_we_win") or [])[:4],
        "how_we_lose": (ov.get("how_we_lose") or [])[:4],
        "score_bands": [{"band": s["band"], "win_pct": s.get("win_pct"), "games": s.get("played")} for s in (ov.get("score_bands") or [])],
        "batting_profile": {"avg_score": _round(bat.get("avg_score"), 1), "boundary_pct": bat.get("boundary_pct")},
        "bowling_profile": {"avg_conceded": _round(bowl.get("avg_conceded"), 1), "wkts_per_game": _round(bowl.get("avg_wickets_taken"), 1)},
        "opening_partnerships": [{"pair": f"{p['a']} & {p['b']}", "stands": p["stands"], "avg": _round(p.get("avg")), "best": p.get("best"), "opening": p.get("opening")} for p in pairs[:8]],
        "typical_opening_stand": {"avg": _round(starts.get("avg")), "best": starts.get("best")} if starts else None,
    }
    if season and not season_id:
        out["note"] = f"Season '{season}' didn't match a season we hold. These figures are ALL-TIME instead."
    return out


async def _tool_form_movers(session, org_id, *, season=None):
    season_id, season_label = await _resolve_season(session, org_id, season)
    ov = await iq_trends.trends_overview(session, org_id, season_id=season_id)
    # trends_overview always answers for ONE season (latest with stats when none
    # was picked), so echo the year it actually used.
    sy = ov.get("season_year")
    label = season_label if season_id else (_season_label({"year": sy}) if sy is not None else "latest season")

    def mv(items):
        return [{"name": p["name"], "from": _round(p.get("baseline")), "to": _round(p.get("latest"))} for p in (items or [])[:6]]
    out = {
        "scope": _scope_echo(season=label, basis="season"),
        "batting_rising": mv((ov.get("batting") or {}).get("risers")),
        "batting_sliding": mv((ov.get("batting") or {}).get("fallers")),
        "bowling_improving": mv((ov.get("bowling") or {}).get("risers")),
        "bowling_slipping": mv((ov.get("bowling") or {}).get("fallers")),
        "emerging": [{"name": e["name"], "runs": e.get("runs"), "wickets": e.get("wickets")} for e in (ov.get("emerging") or [])[:6]],
    }
    if season and not season_id:
        out["note"] = f"Season '{season}' didn't match a season we hold. Showing the latest season instead."
    return out


async def _tool_current_squad(session, org_id, *, grade=None, season=None):
    season_id, season_label = await _resolve_season(session, org_id, season)
    players = await iq_trends.list_players(session, org_id, season_id=season_id, grade_id=grade) or []
    note = None
    if season and not season_id:
        note = f"Season '{season}' didn't match a season we hold. Showing the latest season instead."
    if grade and not players:
        # A grade name that matched nothing — fall back to the whole squad for
        # that season so the model can filter by the selection squad itself (the
        # XI and the same-numbered grade are usually the same side).
        players = await iq_trends.list_players(session, org_id, season_id=season_id) or []
        note = ((note + " ") if note else "") + (
            f"No players under grade '{grade}' for that season. Showing the whole squad; "
            "filter by 'squad' (the selection team, e.g. '2nd XI') yourself, a grade and its "
            "same-numbered XI are usually the same side.")
    players = sorted(players, key=lambda p: (p.get("runs") or 0), reverse=True)[:40]
    squads = sorted({p.get("squad_name") for p in players if p.get("squad_name")})
    return {
        "scope": _scope_echo(season=(season_label if season_id else "latest season"), grade=grade, basis="season"),
        "grade": grade or "all grades",
        "note": note,
        "squads": squads,
        "players": [
            {"name": p["name"], "squad": p.get("squad_name"), "role": p.get("role"), "keeper": p.get("is_keeper"),
             "bowling_style": p.get("bowling_style"), "bowling_class": p.get("bowling_class"),
             "matches": p.get("matches"), "runs": p.get("runs"), "bat_avg": _round(p.get("bat_avg")),
             "wickets": p.get("wickets"), "bowl_avg": _round(p.get("bowl_avg"))}
            for p in players
        ],
    }


async def _tool_grades(session, org_id):
    rows = await iq_team.team_grades(session, org_id, None)
    names = sorted({r["name"] for r in rows})
    return {"grades": names}


async def _tool_upcoming_fixtures(session, org_id):
    data = await iq_service.list_opponents(session, org_id)
    fixtures = (data.get("upcoming") or [])[:10]
    if not fixtures:
        return {
            "count": 0,
            "note": "No upcoming fixtures held. Fixtures sync from the BetterSelect Fixtures screen (or can be added manually there).",
        }
    return {"count": len(fixtures), "fixtures": [
        {
            "fixture_id": f["fixture_id"],
            "date": f.get("played_on"),
            "team": f.get("team_name"),
            "grade": f.get("grade_name"),
            "opponent": f.get("opponent_name"),
            "home_away": f.get("home_away"),
            "venue": f.get("venue"),
            "has_history": bool(f.get("opp_key")),
        }
        for f in fixtures
    ]}


async def _resolve_opp_arg(session, org_id: str, opponent: str | None):
    """Fuzzy-match a model-supplied club name onto a stable opp_key.

    A synced opponent's key is an org GUID, not its name, so a bare name passed
    straight through would miss it. Returns (opp_key_or_passthrough, name|None).
    """
    if not opponent:
        return None, None
    data = await iq_service.list_opponents(session, org_id)
    ol = opponent.strip().lower()
    opps = data.get("opponents") or []
    exact = [o for o in opps if (o.get("name") or "").lower() == ol]
    hits = exact or [
        o for o in opps
        if ol in (o.get("name") or "").lower() or (o.get("name") or "").lower() in ol
    ]
    if hits:
        return hits[0]["opp_key"], hits[0].get("name")
    return opponent, None  # may already be an opp_key / org GUID


def _trim_performer(p, kind):
    out = {"name": p.get("name"), "squad": p.get("squad"), "active": p.get("active")}
    if kind == "bat":
        out.update({"runs": p.get("runs"), "average": _round(p.get("average")), "innings": p.get("innings"), "high_score": p.get("high_score")})
    else:
        # Keep the sample sizes the source rows carry (wickets + runs conceded;
        # innings when present), same as the batting branch keeps "innings" —
        # so the model can flag a 3-wicket "hold" as a small sample.
        out.update({"wickets": p.get("wickets"), "average": _round(p.get("average")), "economy": _round(p.get("economy")),
                    "runs_conceded": p.get("runs"), "best_wickets": p.get("best_wickets")})
        if p.get("innings") is not None:
            out["innings"] = p.get("innings")
    return out


async def _tool_opposition_report(session, org_id, *, fixture_id=None, opponent=None, grade=None):
    if not fixture_id and not opponent:
        return {"error": "Pass a fixture_id (from upcoming_fixtures) or an opponent club name."}
    opp_arg, opp_name = (None, None)
    if not fixture_id:
        opp_arg, opp_name = await _resolve_opp_arg(session, org_id, opponent)
    rep = await iq_service.opposition_report(
        session, org_id, opponent=opp_arg, fixture_id=fixture_id, grade=grade, display_name=opp_name,
    )
    if not (rep.get("opponent") or {}).get("opp_key"):
        return {
            "opponent": (rep.get("opponent") or {}).get("name") or opponent,
            "no_history": True,
            "note": ((rep.get("coverage") or {}).get("note") or "No history held against this opponent.")
            + " The user can link this opponent to a known club via 'Match club' on the BetterIQ Opposition page.",
        }
    h2h = rep.get("head_to_head") or {}
    perf = rep.get("our_performers") or {}
    lm = rep.get("last_meeting")
    out = {
        "opponent": (rep.get("opponent") or {}).get("name"),
        "grade_scope": grade or "all grades",
        "scope": _scope_echo(grade=grade),
        "note": "The head-to-head and performer figures span every season we hold against this opponent"
                + (" within that grade." if grade else " (there is no season filter on this tool)."),
        "record": {
            "meetings": h2h.get("meetings"), "wins": h2h.get("wins"), "losses": h2h.get("losses"),
            "draws": h2h.get("draws"), "win_pct": h2h.get("win_pct"),
            "recent_form": h2h.get("recent_form"),
        },
        "our_batters_who_go_well": [_trim_performer(p, "bat") for p in (perf.get("batting") or [])[:8]],
        "our_bowlers_who_go_well": [_trim_performer(p, "bowl") for p in (perf.get("bowling") or [])[:8]],
        "our_bowler_holds_over_their_batter": [
            {"bowler": m.get("bowler"), "their_batter": m.get("batter"), "dismissals": m.get("dismissals")}
            for m in ((rep.get("matchups") or {}).get("bowler_dominance") or [])[:8]
        ],
        "venues": [
            {"venue": v.get("venue"), "played": v.get("played"), "wins": v.get("wins"), "losses": v.get("losses")}
            for v in (rep.get("venues") or [])[:5]
        ],
    }
    if lm:
        out["last_meeting"] = {
            "date": lm.get("played_at"), "result": lm.get("result"),
            "our_runs": lm.get("our_runs"), "their_runs": lm.get("opp_runs"),
            "our_top_bat": lm.get("our_top_bat"), "our_top_bowl": lm.get("our_top_bowl"),
        }
    their = rep.get("their_key_players")
    if their:
        out["their_all_time_key_players"] = {
            "batting": [{"name": p.get("name"), "runs": p.get("runs")} for p in (their.get("batting") or [])[:5]],
            "bowling": [{"name": p.get("name"), "wickets": p.get("wickets")} for p in (their.get("bowling") or [])[:5]],
        }
    return out


async def _tool_opponent_danger_players(session, org_id, *, fixture_id=None, opponent=None):
    if not fixture_id and not opponent:
        return {"error": "Pass a fixture_id (from upcoming_fixtures) or an opponent club name."}
    opp_arg, opp_name = (None, None)
    if not fixture_id:
        opp_arg, opp_name = await _resolve_opp_arg(session, org_id, opponent)
    opp_key, name, grade_id = await iq_service.resolve_opponent(
        session, org_id, opponent=opp_arg, fixture_id=fixture_id, display_name=opp_name,
    )
    # Same keying as the dossier route: a never-played opponent is still
    # scoutable when a fixture supplies their grade.
    key = opp_key or (name if grade_id else None)
    if not key:
        return {
            "status": "unavailable",
            "note": f"No identity to scout for {name or opponent} yet. The user can link them via 'Match club' on the BetterIQ Opposition page.",
        }
    d = await iq_opponent.get_or_start_dossier(
        session, org_id, key, opp_name=name, grade_id=grade_id,
    )
    status = d.get("status")
    if status == "building":
        return {
            "status": "building",
            "note": (
                f"The live scout of {name or 'this opponent'} has started building in the background "
                "(takes up to a minute). Answer from opposition_report for now and tell the user the "
                "deeper current-season scout will be ready if they ask again shortly, or on the "
                "BetterIQ Opposition page."
            ),
        }
    if status in ("error", "unavailable"):
        return {"status": status, "note": d.get("message") or "Couldn't build the live scout just now. Use opposition_report instead."}

    def _bat(p):
        alert = p.get("alert") if isinstance(p.get("alert"), dict) else None
        return {
            "name": p.get("name"), "runs": p.get("runs"), "average": _round(p.get("average")),
            "strike_rate": _round(p.get("strike_rate")), "form": p.get("form"),
            "vs_us": p.get("vs_us"), "note": p.get("key_note"), "plan": p.get("plan"),
            "alert": {
                "level": alert.get("level"),
                "reasons": (alert.get("danger") or []) + (alert.get("caution") or []),
            } if alert else None,
        }

    def _bowl(p):
        return {
            "name": p.get("name"), "wickets": p.get("wickets"), "average": _round(p.get("average")),
            "economy": _round(p.get("economy")), "form": p.get("form"),
            "vs_us": p.get("vs_us"), "note": p.get("key_note"), "plan": p.get("plan"),
        }

    out = {
        "status": "ready",
        "opponent": name or (d.get("opponent") or {}).get("name"),
        "season_scope": "current season (live scout)",
        "danger_batters": [_bat(p) for p in (d.get("danger_batters") or [])[:6]],
        "danger_bowlers": [_bowl(p) for p in (d.get("danger_bowlers") or [])[:6]],
    }
    gp = d.get("game_plan") or {}
    if gp:
        out["game_plan"] = {
            "one_liner": gp.get("one_liner"),
            "remove_early": (gp.get("remove_early") or {}).get("name") if isinstance(gp.get("remove_early"), dict) else gp.get("remove_early"),
            "see_off": (gp.get("see_off") or {}).get("name") if isinstance(gp.get("see_off"), dict) else gp.get("see_off"),
            "target_bowler": (gp.get("target_bowler") or {}).get("name") if isinstance(gp.get("target_bowler"), dict) else gp.get("target_bowler"),
            "key_warning": gp.get("key_warning"),
        }
    return out


_DISPATCH = {
    "find_players": _tool_find_players,
    "player_detail": _tool_player_detail,
    "player_vs_club": _tool_player_vs_club,
    "players_together": _tool_players_together,
    "team_overview": _tool_team_overview,
    "form_movers": _tool_form_movers,
    "current_squad": _tool_current_squad,
    "grades": _tool_grades,
    "upcoming_fixtures": _tool_upcoming_fixtures,
    "opposition_report": _tool_opposition_report,
    "opponent_danger_players": _tool_opponent_danger_players,
}


# The ~900-word system prompt + 11 tool schemas are the stable prefix of every
# request in the up-to-8-step tool loop, so one cache breakpoint on the last
# (only) system block caches them all — tools render before system, and the
# combined prefix clears the model's minimum cacheable size. anthropic 0.40.0's
# typed params don't know cache_control on a system block, but the SDK forwards
# unknown dict keys to the API unchanged (the same pass-through the scorecard
# reader's PDF document blocks already rely on), so the plain dict works.
_SYSTEM_BLOCKS = [{"type": "text", "text": _SYSTEM, "cache_control": {"type": "ephemeral"}}]


def _answer_from(resp, *, empty_msg: str) -> dict:
    """Turn a final (non-tool_use) model response into the route payload, honest
    about WHY it ended: a max_tokens cut is marked truncated rather than passed
    off as complete, and a refusal or empty response gets a plain message
    instead of reading as a generic failure."""
    text = strip_em_dashes("".join(b.text for b in resp.content if b.type == "text").strip())
    if resp.stop_reason == "refusal":
        return {"available": True,
                "answer": text or "I'd best not answer that one. Try a question about the club's cricket."}
    if resp.stop_reason == "max_tokens" and text:
        return {"available": True, "answer": text + " (answer truncated)"}
    return {"available": True, "answer": text or empty_msg}


async def _run_tool(org_id: str, name: str, args: dict) -> dict:
    fn = _DISPATCH.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    # A fresh session per tool: a heavy/timed-out query aborts only its own
    # transaction (auto-rolled back here), never poisoning later tool calls in
    # the loop, and each tool gets a live connection between the slow model turns.
    try:
        async with async_session_maker() as session:
            return await fn(session, org_id, **(args or {}))
    except Exception as e:
        logger.exception("iq_ask tool %s failed", name)
        return {"error": f"that lookup failed ({str(e)[:120]})"}


async def answer(
    session: AsyncSession,
    org_id: str,
    club_name: str,
    question: str,
    history: list | None = None,
) -> dict:
    if not settings.anthropic_api_key:
        return {"available": False, "message": "Natural-language answers aren't switched on for this server yet."}
    try:
        import anthropic as anthropic_sdk
    except ImportError:
        return {"available": False, "message": "The AI package isn't installed on this server."}

    client = anthropic_sdk.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Seed the prior turns so a follow-up ("how does he take his wickets") keeps
    # its subject. We carry only the plain question/answer text, not the tool
    # round-trips — the model re-calls whatever tools it needs; the history just
    # tells it who/what the thread is about. Clipped and capped so the context
    # stays small, and validated here so a malformed client body can't poison it.
    messages: list = []
    for turn in (history or [])[-MAX_HISTORY_TURNS:]:
        if not isinstance(turn, dict):
            continue
        prev_q = str(turn.get("question") or "").strip()[:600]
        prev_a = str(turn.get("answer") or "").strip()[:1500]
        if not prev_q:
            continue
        messages.append({"role": "user", "content": prev_q})
        messages.append({"role": "assistant", "content": prev_a or "(no answer)"})
    messages.append({"role": "user", "content": f"Club: {club_name}\nQuestion: {question.strip()[:600]}"})

    try:
        for _ in range(MAX_STEPS):
            resp = await client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=_SYSTEM_BLOCKS,
                tools=TOOLS,
                messages=messages,
            )
            if resp.stop_reason != "tool_use":
                return _answer_from(resp, empty_msg="I couldn't put an answer together, try rephrasing.")

            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = await _run_tool(org_id, block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)})
            messages.append({"role": "user", "content": results})

        # Ran out of steps — ask for a final answer with no more tools.
        final = await client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=_SYSTEM_BLOCKS, messages=messages,
        )
        return _answer_from(final, empty_msg="That one took too many steps, try a more specific question.")
    except Exception as e:
        logger.exception("iq_ask: model call failed")
        return {"available": False, "message": f"Couldn't get an answer just now ({str(e)[:120]}). Try again shortly."}
