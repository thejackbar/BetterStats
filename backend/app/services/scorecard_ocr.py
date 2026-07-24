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
import re

from app.config.settings import settings
from app.services.llm_text import strip_em_dashes

logger = logging.getLogger(__name__)

# Handwriting is the hard part, so default to the most capable model for accuracy.
# Tunable down to sonnet for cheaper/faster at some transcription-quality cost.
MODEL = "claude-opus-4-8"
MAX_TOKENS = 12000
MAX_IMAGES = 8

# USD per million tokens for the extraction model (Opus 4.8) — used only to log an
# estimated cost per upload, so keep it in step with MODEL above. Cache reads/writes
# are priced at the standard 0.1x / 1.25x of input in case caching is ever added here.
_PRICE_INPUT_PER_MTOK = 5.00
_PRICE_OUTPUT_PER_MTOK = 25.00

_ALLOWED_MEDIA = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_PDF_MEDIA = "application/pdf"

_SYSTEM = (
    "You are a meticulous cricket scorer digitising a photographed or scanned club "
    "scorecard. Transcribe EXACTLY what is written on the card. Do not compute, average "
    "or infer numbers that aren't there — if a value is blank or unreadable, leave it "
    "null. The one exception is the match result (see below).\n"
    "Club scorecards come in many layouts. The common families:\n"
    "1. The Australian scorebook (the two-page WACA-style book): one team's innings per "
    "page, with a BATSMAN block, a fall-of-wickets strip, a progress-score grid and a "
    "BOWLING ANALYSIS grid.\n"
    "2. An association OFFICIAL MATCH SUMMARY form: a single page summarising the whole "
    "match from ONE club's side. Their batting card (name / how out / score), their OWN "
    "BOWLERS with figures that are often only Wickets and Runs (no overs or maidens — "
    "leave overs null), an OWN CATCHES column crediting their fielders (the wicketkeeper "
    "marked W/K), sometimes a STUMPINGS BY WICKET-KEEPER box, extras, and the opposition "
    "given only as a totals line (e.g. OPPONENTS' TOTALS 10/111). Record the opposition "
    "as an innings with the totals filled in and an EMPTY batting list — never invent "
    "opposition batters that aren't on the page.\n"
    "3. Typed/printed sheets and other hand-ruled layouts: read whatever is present into "
    "the same shape and note the layout in read_notes.\n"
    "Read with a scorer's eye:\n"
    "- The BATSMAN block lists each batter, then HOW OUT (Caught / Bowled / LBW / Run "
    "Out / Stumped / Not Out), the BOWLER who got them, and a TOTAL column which is the "
    "runs that batter scored. The marks next to the name are the scoring strokes, one "
    "number per scoring shot. Use the TOTAL column for runs (not your own count), and "
    "from those strokes count how many are 4s for `fours` and how many are 6s for "
    "`sixes`. The strokes should add up to the batter's total, so use that as a check. "
    "If a card's layout doesn't record scoring strokes or boundary counts at all (a "
    "summary form), leave fours/sixes null — never 0 — and the same for maidens, wides "
    "and no-balls a card doesn't track.\n"
    "- FALL OF WICKETS gives, per wicket: the team score when it fell, which batter was "
    "out (BAT No.), and often a STAND column which is that partnership's runs. Read every "
    "row into fall_of_wickets, including stand and the time, so partnerships can be "
    "worked out.\n"
    "- The BOWLING analysis (lower grid) lists each bowler with their over-by-over marks "
    "and, on the right, their figures: Maidens, Wides, No Balls, Wickets, Runs. When the "
    "figures are written, use them. Otherwise work out each bowler's overs from how many "
    "over-columns hold their marks: a full column is one over, and a part-filled last "
    "column is that many balls. A column of all dots with no runs is a maiden.\n"
    "- BALLS PER OVER: Australian cricket used EIGHT-ball overs before the 1979/80 "
    "season. On a pre-1980 card, check how many ball cells one over-column of the "
    "bowling grid holds and set match.balls_per_over (8 or 6); leave it null if you "
    "can't tell. Modern cards are 6.\n"
    "- Extras are recorded as No Balls, Wides, Byes and Leg Byes. Extras boxes usually "
    "hold TALLY STROKES with the true number in a separate total column at the right "
    "edge — two strokes '11' means 2, not eleven. Always prefer the written numeral "
    "total over counting strokes.\n"
    "- Australian cards write team scores wickets-first: '7/164' is 164 runs for 7 "
    "wickets, and '10/111' is 111 all out.\n"
    "- Common shorthand: c = caught, b = bowled, lbw, st = stumped, ro/run out, "
    "ct = caught, '†' or (wk) or W/K = the wicketkeeper, * = not out / captain.\n"
    "- For every dismissal record the mode in how_out, the wicket-taking bowler in "
    "bowler, and for a catch or stumping the catcher in fielder, AND write the full "
    "dismissal_text the way a scorecard reads it: 'c Aspinall b Raneri', 'c & b Raneri', "
    "'st Brown b Raneri', 'lbw b Aspinall', 'b Browne', 'run out (Edwards)'. This lets the "
    "bowler and the catcher be credited.\n"
    "- When the card lists catches/stumpings SEPARATELY from dismissals (an OWN CATCHES "
    "column), record them in the innings' `fielding` list — they belong on the innings "
    "where that side was FIELDING (i.e. the other team's batting innings). Put keeper "
    "catches in catches_wk as well as catches.\n"
    "- DATES: old cards write two-digit years — resolve to the sensible historical "
    "century ('2.10.76' is 1976-10-02, never 2076; day first, Australian style). A "
    "two-day match shows two dates: use the FIRST day as match.date and mention the "
    "second in read_notes.\n"
    "- RESULT: transcribe the result box as written. If it is blank but the completed "
    "innings totals clearly decide the match (including on first innings in a drawn "
    "two-innings game), you may state the result and winning_team — then set "
    "result_inferred true so the reviewer knows to check it.\n"
    "A card usually shows ONE team's innings per page, so several photos/pages are "
    "usually the innings of ONE match — combine them into one match with multiple "
    "innings, do not invent a second match. A partial innings (a second innings barely "
    "started before time) is still a real innings: record what's there.\n"
    "- CROSS-REFERENCE NAMES ACROSS THE WHOLE CARD. The SAME person is written many "
    "times — as a batter in the order, as a bowler in the bowling analysis, as the "
    "catcher in a 'c Smith' dismissal, as the wicket-taker in a 'b Jones' dismissal, and "
    "in the fall-of-wickets 'outgoing batsman' row — and handwriting quality varies "
    "between them. Before you settle a name, look at EVERY place it appears and use the "
    "CLEAREST, most complete instance as the true spelling, then use that one spelling "
    "everywhere. The BOWLING ANALYSIS is the authority for bowler names: a bowler scrawled "
    "in a batter's 'how out' column is ALWAYS one of the bowlers listed in that innings' "
    "analysis, so read it as whichever analysis bowler it matches — never emit a "
    "dismissal bowler who isn't in the analysis. The batting order is the authority for "
    "batter names: a name in the fall-of-wickets or a fielder's name that matches a "
    "player already in the order is that same player, spelled the same way. Worked "
    "examples from a real 1976 card: a dismissing bowler that looks like 'S Willingslow' "
    "in a how-out column but is clearly 'G Wittingslow' in the bowling analysis is "
    "'G Wittingslow' in both places; one that looks like 'T Houser' on one page but "
    "'I Heuser' on another is the one person 'I Heuser' throughout; a fielder 'B Pascoe' "
    "who also appears as a bowler should carry the same initial in both. Do NOT, however, "
    "collapse two genuinely different people who merely share a surname — 'N Ziebell' and "
    "'R Ziebell' are different players; only unify instances that are plainly the same "
    "person written more or less legibly.\n"
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
        "fours": {"type": ["integer", "null"], "description": "Number of 4s, counted from the batter's scoring strokes."},
        "sixes": {"type": ["integer", "null"], "description": "Number of 6s, counted from the batter's scoring strokes."},
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
        "overs": {"type": ["number", "null"], "description": "Overs bowled (8.2 = 8 overs 2 balls), counted from how many over-columns hold marks; a part-filled last column gives the part over."},
        "maidens": {"type": ["integer", "null"], "description": "Maiden overs (a column of all dots, no runs)."},
        "runs": {"type": ["integer", "null"], "description": "Runs conceded."},
        "wickets": {"type": ["integer", "null"]},
        "wides": {"type": ["integer", "null"]},
        "no_balls": {"type": ["integer", "null"]},
    },
    "required": ["name"],
}

_FIELD = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Fielder's name exactly as written."},
        "catches": {"type": ["integer", "null"], "description": "Catches taken (including any keeper catches)."},
        "catches_wk": {"type": ["integer", "null"], "description": "Of those catches, how many as wicketkeeper (marked W/K or wk)."},
        "stumpings": {"type": ["integer", "null"]},
        "run_outs": {"type": ["integer", "null"]},
    },
    "required": ["name"],
}

_FOW = {
    "type": "object",
    "properties": {
        "wicket": {"type": "integer", "description": "Which wicket (1..10)."},
        "score": {"type": ["integer", "null"], "description": "Team score when it fell."},
        "batter_out": {"type": ["string", "null"], "description": "Name or bat number of the batter out, if shown."},
        "stand": {"type": ["integer", "null"], "description": "Runs in the partnership that just ended (the STAND column), if shown."},
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
        "batting": {"type": "array", "items": _BAT, "description": "Every batter on the card. EMPTY for a totals-only opposition innings (a summary form's OPPONENTS' TOTALS line)."},
        "bowling": {"type": "array", "items": _BOWL},
        "fall_of_wickets": {"type": "array", "items": _FOW},
        "fielding": {
            "type": "array",
            "items": _FIELD,
            "description": "Fielding credits for the side that was FIELDING during this innings, when the card lists them separately from dismissals (an OWN CATCHES column, a stumpings box). Leave empty when fielders are only named inside dismissals.",
        },
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
                    "result": {"type": ["string", "null"], "description": "Result text as written; or your inferred result when the box is blank but the scores decide it (set result_inferred)."},
                    "winning_team": {"type": ["string", "null"]},
                    "result_inferred": {"type": "boolean", "default": False, "description": "True when no result is written on the card and you deduced it from the innings totals."},
                    "balls_per_over": {"type": ["integer", "null"], "description": "Balls per over on this card: 8 for pre-1980 Australian cards (check the bowling grid's cells per over), 6 for modern cards, null when you can't tell."},
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
    if ct in _ALLOWED_MEDIA or ct == _PDF_MEDIA:
        return ct
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return _PDF_MEDIA
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


def overs_to_balls(o, balls_per_over: int = 6):
    """Cricket-notation overs (10.2 = 10 overs 2 balls) → total balls. None-safe.

    balls_per_over matters for pre-1980 Australian cards (8-ball overs)."""
    if o is None:
        return None
    try:
        o = float(o)
    except (TypeError, ValueError):
        return None
    full = int(o)
    return full * balls_per_over + round((o - full) * 10)


def _surname_key(name) -> str:
    """Longest alphabetic token of a name, lowercased — a rough surname for the
    fuzzy cross-checks (initials and dots dropped)."""
    toks = [t for t in re.split(r"[^a-z]+", (name or "").lower()) if len(t) >= 2]
    return max(toks, key=len) if toks else ""


def _name_close(a: str, b: str) -> float:
    """Surname-level similarity in [0,1] — tolerates a misread letter or initial so
    'wittingslow' vs 'willingslow' scores high but two different surnames score low."""
    from difflib import SequenceMatcher
    sa, sb = _surname_key(a), _surname_key(b)
    if not sa or not sb:
        return 0.0
    if sa == sb or sa in sb or sb in sa:
        return 1.0
    return SequenceMatcher(None, sa, sb).ratio()


def reconcile(payload: dict) -> list[str]:
    """Advisory cross-checks that flag the cells most likely misread.

    Never blocks an import — it just tells the reviewer where the card and the numbers
    disagree (batting that doesn't add up to the total, wickets that don't tally, a
    dismissing bowler whose name isn't among that innings' bowlers).
    """
    warnings: list[str] = []
    _DISMISSED_NOT = {"not out", "did not bat", "dnb", "absent", "", None}
    bpo = (payload.get("match") or {}).get("balls_per_over") or 6
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
        # A totals-only innings (a summary form's opposition line) has no batting rows
        # to add up — skip the batting-sum check rather than flag a bogus mismatch.
        if total is not None and bats:
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

        # Boundaries can't be worth more than the batter's total runs.
        for b in bats:
            r = b.get("runs")
            if r is None:
                continue
            bnd = 4 * (b.get("fours") or 0) + 6 * (b.get("sixes") or 0)
            if bnd > r:
                warnings.append(
                    f"{label}: {b.get('name') or 'a batter'} is shown with {b.get('fours') or 0}x4 and "
                    f"{b.get('sixes') or 0}x6 ({bnd} in boundaries) but only {r} runs."
                )

        # A dismissing bowler is ALWAYS one of the bowlers in this innings' analysis
        # (you can't be dismissed by someone who didn't bowl). A 'b Willingslow' that
        # doesn't match any analysed bowler is a misread name — flag it so the reviewer
        # reconciles it (e.g. to the clearly-written 'G Wittingslow' in the analysis).
        bowler_names = [b.get("name") for b in bowls if (b.get("name") or "").strip()]
        if bowler_names:
            flagged: set[str] = set()
            for b in bats:
                bn = (b.get("bowler") or "").strip()
                if not bn or bn in flagged:
                    continue
                if max((_name_close(bn, cand) for cand in bowler_names), default=0.0) < 0.6:
                    flagged.add(bn)
                    warnings.append(
                        f"{label}: a wicket is credited to bowler \"{bn}\", but no bowler by that "
                        f"name is in the bowling analysis ({', '.join(bowler_names)}) — check the "
                        f"spelling against the analysis, they're the same person."
                    )

        # Bowlers' overs should add up to the innings, when the innings overs are shown.
        inn_balls = overs_to_balls(inn.get("overs"), bpo)
        bowl_balls = [overs_to_balls(b.get("overs"), bpo) for b in bowls]
        if inn_balls and any(x is not None for x in bowl_balls):
            tot = sum(x for x in bowl_balls if x is not None)
            if abs(tot - inn_balls) > bpo:
                warnings.append(
                    f"{label}: bowlers' overs add up to {tot // bpo}.{tot % bpo} but the innings is "
                    f"{inn_balls // bpo}.{inn_balls % bpo} overs."
                )

        # An OWN CATCHES column can't credit a keeper with more wk catches than catches.
        for f in (inn.get("fielding") or []):
            c, wk = f.get("catches"), f.get("catches_wk")
            if c is not None and wk is not None and wk > c:
                warnings.append(
                    f"{label}: {f.get('name') or 'a fielder'} is shown with {wk} keeper catches "
                    f"but only {c} catches in total."
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
                "stand": _num(f.get("stand")),
            } for f in (inn.get("fall_of_wickets") or []) if f.get("wicket") is not None],
            "fielding": [{
                "name": (f.get("name") or "").strip(),
                "catches": _num(f.get("catches")),
                "catches_wk": _num(f.get("catches_wk")),
                "stumpings": _num(f.get("stumpings")),
                "run_outs": _num(f.get("run_outs")),
            } for f in (inn.get("fielding") or []) if (f.get("name") or "").strip()],
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
            "result_inferred": bool(match.get("result_inferred")),
            "balls_per_over": _num(match.get("balls_per_over")),
        },
        "innings": out_innings,
        # read_notes is the one field here that's genuinely the model's own
        # composed prose (everything else is verbatim transcription of what's
        # on the card) — run it through the same dash-stripping backstop as
        # the yearbook narrative / BetterIQ Ask, for consistency.
        "read_notes": strip_em_dashes(data.get("read_notes")) or None,
    }


async def extract_scorecard(images: list[tuple[bytes, str]], our_club_name: str) -> dict:
    """Read scorecard photo(s)/PDF scan(s) and return a structured both-team scorecard.

    images: list of (raw_bytes, media_type) — a media_type of application/pdf goes up as
    a document block (the model reads PDF pages natively), everything else as an image.
    our_club_name helps the model decide which side is ours. Returns
    {available: True, match, innings, warnings, read_notes} or
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
        if media_type == _PDF_MEDIA:
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": _PDF_MEDIA, "data": base64.b64encode(raw).decode()},
            })
        else:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(raw).decode()},
            })
    content.append({
        "type": "text",
        "text": (
            f"Our club is \"{our_club_name}\". Transcribe these scorecard photo(s)/page(s) into one match. "
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

    usage = getattr(resp, "usage", None)
    if usage is not None:
        in_tok = getattr(usage, "input_tokens", 0) or 0
        out_tok = getattr(usage, "output_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        est_cost = (
            in_tok * _PRICE_INPUT_PER_MTOK
            + cache_write * _PRICE_INPUT_PER_MTOK * 1.25
            + cache_read * _PRICE_INPUT_PER_MTOK * 0.10
            + out_tok * _PRICE_OUTPUT_PER_MTOK
        ) / 1_000_000
        logger.info(
            "scorecard_ocr: extract usage model=%s images=%d input_tokens=%d output_tokens=%d "
            "cache_read=%d cache_write=%d est_cost_usd=%.4f",
            MODEL, min(len(images), MAX_IMAGES), in_tok, out_tok, cache_read, cache_write, est_cost,
        )

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
