"""BetterIQ — natural-language questions over the club's own data.

A *grounded* Q&A. We assemble a compact, factual context from numbers we already
compute (the team self-analysis overview + current-season player form) and ask
Claude to answer the operator's question using ONLY that context, so it can't
invent players or stats. Reuses the Anthropic client pattern from the yearbook
narrative generator; gated on the IQ module + MANAGE_IQ at the router and
rate-limited at the route. Degrades gracefully when the key/package is absent.

Ceiling: the context is club-level (record, approach, par, form), so "how do we
go chasing", "who's in form", "what total usually wins" are answerable, while a
deep opponent-specific question is steered to the Opposition scout (which builds
a live dossier) instead of guessed at.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.services import iq_team, iq_trends

logger = logging.getLogger(__name__)

# Grounded reading over a provided context — well within a fast model's reach.
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 700


def _n(v):
    return v if v is not None else "?"


async def _assemble_context(session: AsyncSession, org_id: str, club_name: str) -> str:
    """A compact, factual brief of the club for the model to answer from."""
    lines = [f"CLUB: {club_name}"]

    try:
        ov = await iq_team.team_overview(session, org_id)  # all-time
    except Exception:
        ov = {}
    rec = (ov or {}).get("record") or {}
    if rec.get("matches"):
        lines.append(
            f"All-time record: {rec.get('wins', 0)}-{rec.get('losses', 0)}-{rec.get('draws', 0)} "
            f"from {rec.get('matches', 0)} games (win rate {_n(rec.get('win_pct'))}%)."
        )
        h, a = rec.get("home") or {}, rec.get("away") or {}
        lines.append(f"Home {h.get('wins', 0)}/{h.get('played', 0)}, away {a.get('wins', 0)}/{a.get('played', 0)}.")
    inn = (ov or {}).get("innings") or {}
    bf, ch, par = inn.get("bat_first") or {}, inn.get("chasing") or {}, inn.get("par") or {}
    if bf.get("win_pct") is not None or ch.get("win_pct") is not None:
        lines.append(
            f"Batting first: win rate {_n(bf.get('win_pct'))}% (avg score {_n(bf.get('avg_score'))}). "
            f"Chasing: win rate {_n(ch.get('win_pct'))}%."
        )
    if par.get("par_score") is not None:
        lines.append(f"Par first-innings score is about {par.get('par_score')}; lowest total defended {_n(par.get('lowest_defended'))}.")
    if ov.get("how_we_win"):
        lines.append("How we win: " + "; ".join(ov["how_we_win"][:4]))
    if ov.get("how_we_lose"):
        lines.append("How we lose: " + "; ".join(ov["how_we_lose"][:4]))
    bands = (ov or {}).get("score_bands") or []
    if bands:
        lines.append("Win rate by first-innings total: " + ", ".join(f"{b['band']} {_n(b.get('win_pct'))}% ({b.get('played', 0)})" for b in bands))
    venues = (ov or {}).get("venues") or []
    if venues:
        lines.append("By venue: " + "; ".join(f"{v['venue']} {v.get('wins', 0)}-{v.get('losses', 0)}" for v in venues[:6]))

    try:
        players = await iq_trends.list_players(session, org_id) or []
    except Exception:
        players = []
    bats = sorted([p for p in players if (p.get("runs") or 0) > 0], key=lambda p: p.get("runs") or 0, reverse=True)
    if bats:
        lines.append("Top batters this season: " + "; ".join(f"{p['name']} {p.get('runs')} runs @ {_n(p.get('bat_avg'))}" for p in bats[:15]))
    bowls = sorted([p for p in players if (p.get("wickets") or 0) > 0], key=lambda p: p.get("wickets") or 0, reverse=True)
    if bowls:
        lines.append("Top bowlers this season: " + "; ".join(f"{p['name']} {p.get('wickets')} wkts @ {_n(p.get('bowl_avg'))}" for p in bowls[:15]))

    return "\n".join(lines)


_SYSTEM = (
    "You are a cricket analyst for a grassroots Australian cricket club. Answer the "
    "question using ONLY the data provided. Be specific and use the numbers from the "
    "data. Keep it to a few sentences in a plain Australian cricket-club tone (no "
    "corporate words, no em dashes). If the data doesn't cover the question, say so "
    "plainly and point them to where in BetterIQ to look: the Opposition scout for a "
    "specific opponent, Player search for one player, or Team analysis for the side. "
    "Never invent players, clubs or numbers."
)


async def answer(session: AsyncSession, org_id: str, club_name: str, question: str) -> dict:
    if not settings.anthropic_api_key:
        return {"available": False, "message": "Natural-language answers aren't switched on for this server yet."}
    try:
        import anthropic as anthropic_sdk
    except ImportError:
        return {"available": False, "message": "The AI package isn't installed on this server."}

    context = await _assemble_context(session, org_id, club_name)
    user = f"DATA:\n{context}\n\nQUESTION: {question.strip()[:500]}"
    try:
        client = anthropic_sdk.AsyncAnthropic(api_key=settings.anthropic_api_key)
        msg = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text_out = "".join(getattr(b, "text", "") for b in (msg.content or [])).strip()
    except Exception as e:
        logger.exception("iq_ask: model call failed")
        return {"available": False, "message": f"Couldn't get an answer just now ({str(e)[:120]}). Try again shortly."}

    return {"available": True, "answer": text_out or "No answer came back — try rephrasing the question."}
