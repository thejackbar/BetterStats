"""Upload Historical Scorecard — read a photographed scorecard with Claude vision.

Grassroots club scorebooks (the WACA / standard two-page book) are handwritten, so
there is no clean data source for an old paper card. This reads the photo(s) with a
vision model and returns a structured both-team scorecard the admin then reviews and
imports as a manual game. We never blind-import: handwriting can't be read with zero
errors, so the model does the transcription and the admin verifies it on screen.

The extraction is deliberately faithful — transcribe what's on the card, don't compute
or infer beyond it. We re-derive nothing here except a set of advisory reconciliation
checks (does the batting add up to the team total, do the wickets tally) that flag the
cells most likely misread, so the reviewer knows where to look.

Reuses the Anthropic client pattern from iq_ask / the yearbook narrative generator, and
degrades cleanly when the key or package is absent (same as iq_ask).
"""
from __future__ import annotations

import base64
import json
import logging

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Handwriting is the hard part, so default to the most capable model for accuracy.
# Tunable down to sonnet for cheaper/faster at some transcription-quality cost.
MODEL = "claude-opus-4-8"
MAX_TOKENS = 8000
MAX_IMAGES = 8

_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/gif"}

_SYSTEM = (
    "You are a meticulous cricket scorer digitising a photographed club scorecard. "
    "Transcribe EXACTLY what is written on the card. Do not compute, average or infer "
    "numbers that aren't there — if a value is blank or unreadable, leave it null. "
    "These are standard Australian grassroots scorebooks (the two-page WACA-style "
    "book). Read them with a scorer's eye:\n"
    "- The BATSMAN block lists each batter, then HOW OUT (Caught / Bowled / LBW / Run "
    "Out / Stumped / Not Out), the BOWLER who got them, and a TOTAL column which is the "
    "runs that batter scored. The marks next to the name are the scoring strokes — use "
    "the TOTAL column for runs, not your own count of the strokes.\n"
    "- FALL OF WICKETS gives, per wicket, the team score when it fell and which batter "
    "was out (BAT No.).\n"
    "- The BOWLING analysis (lower grid) lists each bowler with their over-by-over marks "
    "and, on the right, their figures: Maidens, Wides, No Balls, Wickets, Runs.\n"
    "- Extras are recorded as No Balls, Wides, Byes and Leg Byes.\n"
    "- Common shorthand: c = caught, b = bowled, lbw, st = stumped, ro/run out, "
    "ct = caught, '†' or (wk) = the wicketkeeper, * = not out / captain.\n"
    "A card usually shows ONE team's innings per page, so several photos are usually the "
    "two innings of ONE match — combine them into one match with multiple innings, do "
    "not invent a second match.\n"
    "You will be told which club is OURS. For each innings set is_our_team to whether the "
    "batting side is that club. The bowling rows of an innings belong to the OTHER side "
    "(the team that was fielding). Record both teams in full. "
    "Call record_scorecard exactly once with everything you can read."
)

_BAT = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Batter's name exactly as written (e.g. 'Pervan L', 'C Browne')."},
        "position": {"type": ["integer", "null"], "description": "Batting order number (1 = opener)."},
        "runs": {"type": ["integer", "null"], "description": "Runs scored (the TOTAL column)."},
        "balls": {"type": ["integer", "null"]},
        "fours": {"type": ["integer", "null"]},
        "sixes": {"type": ["integer", "null"]},
        "how_out": {"type": ["string", "null"], "description": "Dismissal kind: caught, bowled, lbw, run out, stumped, not out, did not bat, absent."},
        "bowler": {"type": ["string", "null"], "description": "Bowler credited with the wicket, if any."},
        "fielder": {"type": ["string", "null"], "description": "Catcher / fielder for a catch, stumping or run out, if shown."},
        "not_out": {"type": "boolean", "default": False},
        "did_not_bat": {"type": "boolean", "default": False},
        "dismissal_text": {"type": ["string", "null"], "description": "The dismissal as it should read, e.g. 'c Aspinall b Raneri', 'b Browne', 'lbw b Aspinall', 'run out'."},
    },
    "required": ["name"],
}

_BOWL = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Bowler's name exactly as written."},
        "overs": {"type": ["number", "null"], "description": "Overs bowled in cricket notation (8.2 = 8 overs 2 balls)."},
        "maidens": {"type": ["integer", "null"]},
        "runs": {"type": ["integer", "null"], "description": "Runs conceded."},
        "wickets": {"type": ["integer", "null"]},
        "wides": {"type": ["integer", "null"]},
        "no_balls": {"type": ["integer", "null"]},
    },
    "required": ["name"],
}

_FOW = {
    "type": "object",
    "properties": {
        "wicket": {"type": "integer", "description": "Which wicket (1..10)."},
        "score": {"type": ["integer", "null"], "description": "Team score when it fell."},
        "batter_out": {"type": ["string", "null"], "description": "Name or bat number of the batter out, if shown."},
    },
    "required": ["wicket"],
}

_INNINGS = {
    "type": "object",
    "properties": {
        "innings_number": {"type": "integer", "description": "1 for the first innings, 2 for the second."},
        "batting_team": {"type": "string", "description": "Name of the team batting in this innings."},
        "is_our_team": {"type": "boolean", "description": "True if the batting team is OUR club (told in the prompt)."},
        "total_runs": {"type": ["integer", "null"], "description": "Innings total as written (e.g. 108, 109)."},
        "total_wickets": {"type": ["integer", "null"], "description": "Wickets fallen (e.g. 10, or 4 for '4 wickets for')."},
        "overs": {"type": ["number", "null"], "description": "Overs faced, if written."},
        "extras": {
            "type": "object",
            "properties": {
                "byes": {"type": ["integer", "null"]},
                "leg_byes": {"type": ["integer", "null"]},
                "wides": {"type": ["integer", "null"]},
                "no_balls": {"type": ["integer", "null"]},
                "penalty": {"type": ["integer", "null"]},
                "total": {"type": ["integer", "null"]},
            },
        },
        "batting": {"type": "array", "items": _BAT},
        "bowling": {"type": "array", "items": _BOWL},
        "fall_of_wickets": {"type": "array", "items": _FOW},
    },
    "required": ["innings_number", "batting_team", "is_our_team", "batting", "bowling"],
}

_TOOL = {
    "name": "record_scorecard",
    "description": "Record the full transcribed scorecard for both teams.",
    "input_schema": {
        "type": "object",
        "properties": {
            "match": {
                "type": "object",
                "properties": {
                    "date": {"type": ["string", "null"], "description": "Match date as ISO YYYY-MM-DD if you can resolve it (e.g. '14-3-20' → '2020-03-14'); null if unsure."},
                    "date_raw": {"type": ["string", "null"], "description": "The date exactly as written on the card."},
                    "venue": {"type": ["string", "null"]},
                    "home_team": {"type": ["string", "null"]},
                    "away_team": {"type": ["string", "null"]},
                    "our_team": {"type": ["string", "null"], "description": "Which of the two clubs is OURS."},
                    "toss_won_by": {"type": ["string", "null"]},
                    "result": {"type": ["string", "null"], "description": "Result text if shown."},
                    "winning_team": {"type": ["string", "null"]},
                },
            },
            "innings": {"type": "array", "items": _INNINGS},
            "read_notes": {"type": ["string", "null"], "description": "Anything you were unsure about or couldn't read."},
        },
        "required": ["match", "innings"],
    },
}


def guess_media_type(content_type: str | None, filename: str | None) -> str:
    ct = (content_type or "").lower().split(";")[0].strip()
    if ct in _ALLOWED_MEDIA:
        return ct
    name = (filename or "").lower()
    if name.endswith(".png"):
        return "image/png"
    if name.endswith(".webp"):
        return "image/webp"
    if name.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def _num(v):
    """Coerce a model number to int when it is whole, leave floats, pass None through."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return int(f) if f == int(f) else f


def reconcile(payload: dict) -> list[str]:
    """Advisory cross-checks that flag the cells most likely misread.

    Never blocks an import — it just tells the reviewer where the card and the numbers
    disagree (batting that doesn't add up to the total, wickets that don't tally).
    """
    warnings: list[str] = []
    _DISMISSED_NOT = {"not out", "did not bat", "dnb", "absent", "", None}
    for inn in (payload.get("innings") or []):
        n = inn.get("innings_number")
        team = inn.get("batting_team") or f"innings {n}"
        label = f"{team} (innings {n})"
        bats = inn.get("batting") or []
        bowls = inn.get("bowling") or []

        run_sum = sum((b.get("runs") or 0) for b in bats if not b.get("did_not_bat"))
        extras = inn.get("extras") or {}
        ex_total = extras.get("total")
        if ex_total is None:
            parts = [extras.get(k) for k in ("byes", "leg_byes", "wides", "no_balls", "penalty")]
            ex_total = sum(p for p in parts if p) if any(p is not None for p in parts) else None
        total = inn.get("total_runs")
        if total is not None:
            expected = run_sum + (ex_total or 0)
            if expected != total:
                warnings.append(
                    f"{label}: batting {run_sum}"
                    + (f" + {ex_total} extras" if ex_total else "")
                    + f" = {expected}, but the card total reads {total} (off by {total - expected})."
                )

        dismissed = [b for b in bats if not b.get("not_out") and not b.get("did_not_bat")
                     and (b.get("how_out") or "").strip().lower() not in _DISMISSED_NOT]
        wkts = inn.get("total_wickets")
        fow = inn.get("fall_of_wickets") or []
        if wkts is not None and fow and len(fow) != wkts:
            warnings.append(f"{label}: {wkts} wickets fell but {len(fow)} fall-of-wickets rows were read.")
        bowl_wkts = sum((b.get("wickets") or 0) for b in bowls)
        if wkts is not None and bowl_wkts > wkts:
            warnings.append(f"{label}: bowlers were credited {bowl_wkts} wickets but only {wkts} fell.")

        bowl_runs = sum((b.get("runs") or 0) for b in bowls if b.get("runs") is not None)
        if total is not None and bowls and bowl_runs:
            byes = (extras.get("byes") or 0) + (extras.get("leg_byes") or 0)
            gap = total - (bowl_runs + byes)
            if abs(gap) > 5:
                warnings.append(
                    f"{label}: bowling concedes {bowl_runs}"
                    + (f" + {byes} byes/leg-byes" if byes else "")
                    + f" = {bowl_runs + byes}, but the innings total is {total} (off by {gap})."
                )
    return warnings


def _normalise(data: dict) -> dict:
    """Coerce the model output into clean numbers and a stable shape."""
    match = data.get("match") or {}
    out_innings = []
    for inn in (data.get("innings") or []):
        extras = inn.get("extras") or {}
        out_innings.append({
            "innings_number": _num(inn.get("innings_number")) or (len(out_innings) + 1),
            "batting_team": inn.get("batting_team"),
            "is_our_team": bool(inn.get("is_our_team")),
            "total_runs": _num(inn.get("total_runs")),
            "total_wickets": _num(inn.get("total_wickets")),
            "overs": _num(inn.get("overs")),
            "extras": {k: _num(extras.get(k)) for k in ("byes", "leg_byes", "wides", "no_balls", "penalty", "total")},
            "batting": [{
                "name": (b.get("name") or "").strip(),
                "position": _num(b.get("position")),
                "runs": _num(b.get("runs")),
                "balls": _num(b.get("balls")),
                "fours": _num(b.get("fours")),
                "sixes": _num(b.get("sixes")),
                "how_out": (b.get("how_out") or None),
                "bowler": (b.get("bowler") or None),
                "fielder": (b.get("fielder") or None),
                "not_out": bool(b.get("not_out")),
                "did_not_bat": bool(b.get("did_not_bat")),
                "dismissal_text": (b.get("dismissal_text") or None),
            } for b in (inn.get("batting") or []) if (b.get("name") or "").strip()],
            "bowling": [{
                "name": (b.get("name") or "").strip(),
                "overs": _num(b.get("overs")),
                "maidens": _num(b.get("maidens")),
                "runs": _num(b.get("runs")),
                "wickets": _num(b.get("wickets")),
                "wides": _num(b.get("wides")),
                "no_balls": _num(b.get("no_balls")),
            } for b in (inn.get("bowling") or []) if (b.get("name") or "").strip()],
            "fall_of_wickets": [{
                "wicket": _num(f.get("wicket")),
                "score": _num(f.get("score")),
                "batter_out": (f.get("batter_out") or None),
            } for f in (inn.get("fall_of_wickets") or []) if f.get("wicket") is not None],
        })
    return {
        "match": {
            "date": match.get("date") or None,
            "date_raw": match.get("date_raw") or None,
            "venue": match.get("venue") or None,
            "home_team": match.get("home_team") or None,
            "away_team": match.get("away_team") or None,
            "our_team": match.get("our_team") or None,
            "toss_won_by": match.get("toss_won_by") or None,
            "result": match.get("result") or None,
            "winning_team": match.get("winning_team") or None,
        },
        "innings": out_innings,
        "read_notes": data.get("read_notes") or None,
    }


async def extract_scorecard(images: list[tuple[bytes, str]], our_club_name: str) -> dict:
    """Read scorecard photo(s) and return a structured both-team scorecard.

    images: list of (raw_bytes, media_type). our_club_name helps the model decide which
    side is ours. Returns {available: True, match, innings, warnings, read_notes} or
    {available: False, message} when the model can't be reached.
    """
    if not settings.anthropic_api_key:
        return {"available": False, "message": "AI scorecard reading isn't switched on for this server yet."}
    try:
        import anthropic as anthropic_sdk
    except ImportError:
        return {"available": False, "message": "The AI package isn't installed on this server."}
    if not images:
        return {"available": False, "message": "No images were uploaded."}

    client = anthropic_sdk.AsyncAnthropic(api_key=settings.anthropic_api_key)

    content: list = []
    for raw, media_type in images[:MAX_IMAGES]:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(raw).decode()},
        })
    content.append({
        "type": "text",
        "text": (
            f"Our club is \"{our_club_name}\". Transcribe these scorecard photo(s) into one match. "
            "Set is_our_team on each innings accordingly, record both teams in full, and call "
            "record_scorecard once."
        ),
    })

    try:
        resp = await client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=_SYSTEM,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "record_scorecard"},
            messages=[{"role": "user", "content": content}],
        )
    except Exception as e:
        logger.exception("scorecard_ocr: model call failed")
        return {"available": False, "message": f"Couldn't read the scorecard just now ({str(e)[:160]}). Try again shortly."}

    tool_input = next((b.input for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
    if not tool_input:
        return {"available": False, "message": "The model didn't return a scorecard. Try a clearer photo."}

    try:
        data = _normalise(tool_input if isinstance(tool_input, dict) else json.loads(tool_input))
    except Exception:
        logger.exception("scorecard_ocr: could not normalise model output")
        return {"available": False, "message": "The scorecard couldn't be parsed. Try again or a clearer photo."}

    data["available"] = True
    data["warnings"] = reconcile(data)
    return data
