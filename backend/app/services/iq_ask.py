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

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.services import iq_players, iq_team, iq_trends
from app.services.aggregations import get_player_by_opposition

logger = logging.getLogger(__name__)

# Capable model for the tool-use reasoning + synthesis. Tunable; lower to
# claude-sonnet-4-6 / claude-haiku-4-5 for cheaper/faster at some quality cost.
MODEL = "claude-opus-4-8"
MAX_TOKENS = 1500
MAX_STEPS = 6          # tool-call round trips before we force a final answer
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-", re.I)

_SYSTEM = (
    "You are a cricket analyst for a grassroots Australian cricket club. Answer the "
    "user's question about THIS club using the tools provided — never invent players, "
    "clubs or numbers. Find a player with find_players before asking for their detail; "
    "use grades to learn the exact grade names before filtering by grade. Read the "
    "tool results and answer in a few sentences, plain Australian cricket-club tone "
    "(no corporate words, no em dashes). If the tools don't cover what was asked, say "
    "so plainly and point to where in BetterIQ to look (Opposition scout for a "
    "specific opponent, Player search for one player, Team analysis for the side). "
    "Numbers in the tool results are the truth; don't round away meaning."
)


# ─── tools ────────────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "find_players",
        "description": "Find players in the club by name (or list the whole roster when no query). Returns each player's id, role, career matches/runs/wickets and last active year. Use this to get a player_id before calling player_detail or player_vs_club.",
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
        "name": "team_overview",
        "description": "The club's record and approach: win rate, home/away, batting-first vs chasing win rate, par first-innings score, how we win and lose, score-band win rates, batting & bowling profile, best opening partnerships and our typical opening stand. Optionally scope to one grade.",
        "input_schema": {
            "type": "object",
            "properties": {"grade": {"type": "string", "description": "optional grade name (from grades)"}},
        },
    },
    {
        "name": "form_movers",
        "description": "Who is in or out of form this season: batters and bowlers rising or sliding vs their career baseline, plus emerging players. Use for 'who's in/out of form' questions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "current_squad",
        "description": "Players with games this season and their form (runs/average, wickets/average), optionally scoped to one grade. Use for 'who's playing/available in grade X' and selection questions.",
        "input_schema": {
            "type": "object",
            "properties": {"grade": {"type": "string", "description": "optional grade name (from grades)"}},
        },
    },
    {
        "name": "grades",
        "description": "The grade (team) names the club fields, so you can filter other tools by an exact grade name.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _round(v, nd=2):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


async def _resolve_pid(session: AsyncSession, org_id: str, value: str) -> str | None:
    """Accept a player_id or a name; return the id (best name match if a name)."""
    value = (value or "").strip()
    if not value:
        return None
    if _UUID.match(value):
        return value
    players = await iq_players.list_all_players(session, org_id)
    vl = value.lower()
    exact = [p for p in players if (p["name"] or "").lower() == vl]
    if exact:
        return exact[0]["player_id"]
    partial = [p for p in players if vl in (p["name"] or "").lower()]
    return partial[0]["player_id"] if partial else None


async def _tool_find_players(session, org_id, *, query=None):
    players = await iq_players.list_all_players(session, org_id)
    if query:
        q = query.strip().lower()
        players = [p for p in players if q in (p["name"] or "").lower()]
    players = players[:40]
    return {"count": len(players), "players": [
        {"player_id": p["player_id"], "name": p["name"], "role": p.get("player_role"),
         "matches": p["matches"], "runs": p["runs"], "wickets": p["wickets"], "last_year": p["last_year"]}
        for p in players
    ]}


async def _tool_player_detail(session, org_id, *, player_id):
    pid = await _resolve_pid(session, org_id, player_id)
    if not pid:
        return {"error": "No player found for that id/name. Call find_players first."}
    trend = await iq_trends.player_trend(session, org_id, pid)
    if not trend:
        return {"error": "No data for that player."}
    deep = None
    try:
        deep = await iq_trends.player_deep_dive(session, org_id, pid)
    except Exception:
        await session.rollback()
    b = (trend.get("career") or {}).get("batting") or {}
    bo = (trend.get("career") or {}).get("bowling") or {}
    recent = [(x.get("runs"), bool(x.get("not_out"))) for x in (trend.get("recent_form") or {}).get("batting", [])][:6]
    out = {
        "name": (trend.get("player") or {}).get("name"),
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
    if not pid:
        return {"error": "No player found for that id/name."}
    rows = await get_player_by_opposition(session, pid) or []
    if club:
        cl = club.strip().lower()
        rows = [r for r in rows if cl in (r["opposition"] or "").lower()]
    rows = rows[:20]
    return {"opponents": [
        {"club": r["opposition"], "games": r["games"], "wins": r["wins"], "losses": r["losses"],
         "runs": r["total_runs"], "bat_avg": _round(r.get("batting_average")), "high": r.get("high_score"),
         "wickets": r["wickets"], "bowl_avg": _round(r.get("bowling_average"))}
        for r in rows
    ]}


async def _tool_team_overview(session, org_id, *, grade=None):
    ov = await iq_team.team_overview(session, org_id, grade_id=grade)
    rec = ov.get("record") or {}
    inn = ov.get("innings") or {}
    bat = ov.get("batting") or {}
    bowl = ov.get("bowling") or {}
    pairs = ov.get("batting_pairs") or []
    starts = ov.get("starts") or {}
    return {
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


async def _tool_form_movers(session, org_id):
    ov = await iq_trends.trends_overview(session, org_id)

    def mv(items):
        return [{"name": p["name"], "from": _round(p.get("baseline")), "to": _round(p.get("latest"))} for p in (items or [])[:6]]
    return {
        "batting_rising": mv((ov.get("batting") or {}).get("risers")),
        "batting_sliding": mv((ov.get("batting") or {}).get("fallers")),
        "bowling_improving": mv((ov.get("bowling") or {}).get("risers")),
        "bowling_slipping": mv((ov.get("bowling") or {}).get("fallers")),
        "emerging": [{"name": e["name"], "runs": e.get("runs"), "wickets": e.get("wickets")} for e in (ov.get("emerging") or [])[:6]],
    }


async def _tool_current_squad(session, org_id, *, grade=None):
    players = await iq_trends.list_players(session, org_id, grade_id=grade) or []
    players = sorted(players, key=lambda p: (p.get("runs") or 0), reverse=True)[:30]
    return {"grade": grade or "all grades", "players": [
        {"name": p["name"], "matches": p.get("matches"), "runs": p.get("runs"), "bat_avg": _round(p.get("bat_avg")),
         "wickets": p.get("wickets"), "bowl_avg": _round(p.get("bowl_avg")), "squad": p.get("squad_name")}
        for p in players
    ]}


async def _tool_grades(session, org_id):
    rows = await iq_team.team_grades(session, org_id, None)
    names = sorted({r["name"] for r in rows})
    return {"grades": names}


_DISPATCH = {
    "find_players": _tool_find_players,
    "player_detail": _tool_player_detail,
    "player_vs_club": _tool_player_vs_club,
    "team_overview": _tool_team_overview,
    "form_movers": _tool_form_movers,
    "current_squad": _tool_current_squad,
    "grades": _tool_grades,
}


async def _run_tool(session: AsyncSession, org_id: str, name: str, args: dict) -> dict:
    fn = _DISPATCH.get(name)
    if not fn:
        return {"error": f"unknown tool {name}"}
    try:
        return await fn(session, org_id, **(args or {}))
    except Exception as e:
        logger.exception("iq_ask tool %s failed", name)
        try:
            await session.rollback()
        except Exception:
            pass
        return {"error": f"that lookup failed ({str(e)[:120]})"}


async def answer(session: AsyncSession, org_id: str, club_name: str, question: str) -> dict:
    if not settings.anthropic_api_key:
        return {"available": False, "message": "Natural-language answers aren't switched on for this server yet."}
    try:
        import anthropic as anthropic_sdk
    except ImportError:
        return {"available": False, "message": "The AI package isn't installed on this server."}

    client = anthropic_sdk.AsyncAnthropic(api_key=settings.anthropic_api_key)
    messages = [{"role": "user", "content": f"Club: {club_name}\nQuestion: {question.strip()[:600]}"}]

    try:
        for _ in range(MAX_STEPS):
            resp = await client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=_SYSTEM,
                tools=TOOLS,
                messages=messages,
            )
            if resp.stop_reason != "tool_use":
                text = "".join(b.text for b in resp.content if b.type == "text").strip()
                return {"available": True, "answer": text or "I couldn't put an answer together — try rephrasing."}

            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = await _run_tool(session, org_id, block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out, default=str)})
            messages.append({"role": "user", "content": results})

        # Ran out of steps — ask for a final answer with no more tools.
        final = await client.messages.create(
            model=MODEL, max_tokens=MAX_TOKENS, system=_SYSTEM, messages=messages,
        )
        text = "".join(b.text for b in final.content if b.type == "text").strip()
        return {"available": True, "answer": text or "That one took too many steps — try a more specific question."}
    except Exception as e:
        logger.exception("iq_ask: model call failed")
        return {"available": False, "message": f"Couldn't get an answer just now ({str(e)[:120]}). Try again shortly."}
