"""Resolve whatever an admin pasted into the Post Designer's "match link" box
into a Cricket Australia match GUID.

Two id namespaces exist for the same match, and they do NOT overlap:

  * **Grassroots (MyCricket)** — a full UUID. It is what ``games.id`` holds,
    what every ``/scores/*`` endpoint answers to, and what the scorecard
    import has always needed.
  * **PlayHQ** — the eight-character code in a game-centre URL
    (``playhq.com/.../game-centre/abecedd5``).

The short code is not a prefix of the Grassroots GUID and nothing derives one
from the other. Checked against a live match rather than assumed: PlayHQ's
``abecedd5`` (D&DCC A Grade semi-final, 31 May 2026) is Grassroots
``ef9b6401-787f-4f93-b9b8-8de0316f3686``.

PlayHQ's own public ``discoverGame`` GraphQL *will* answer for a short code,
but it sits behind a CloudFront WAF that started 403-ing a data-centre IP
after a handful of requests during this investigation — not something a
club's import button can lean on. So a PlayHQ link is resolved against the
club's OWN recent matches instead, which we already pull for the Results
roundup. The grade slug in the URL narrows the list, and the admin picks the
match when more than one still fits.
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.services import grassroots_scores_client as gr
from app.services.club_match import club_match_keys
from app.services.fixtures_source import _current_grade_rows
from app.services.sync import strip_team_suffix

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)
# .../org/<assoc>/<season>/<grade>/game-centre/<code>
_PLAYHQ_RE = re.compile(
    r"playhq\.com/[^\s?#]*?/([^/\s?#]+)/([^/\s?#]+)/game-centre/([0-9a-z]{6,})",
    re.I,
)
# A bare short code typed in on its own.
_BARE_CODE_RE = re.compile(r"^[0-9a-f]{6,12}$", re.I)

# How far back the picker looks. Longer than the Results roundup's 90 days
# because a club posts about a final weeks after it was played (the report
# that prompted this was a semi-final ~10 weeks old).
_LOOKBACK_DAYS = 240
_MAX_CANDIDATES = 40


def _slug(text: str) -> str:
    """PlayHQ's URL slug form of a name: 'A Grade (Gatorade)' → 'a-grade-gatorade'."""
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", (text or "").lower())).strip("-")


def parse_reference(raw: str) -> dict | None:
    """Work out what an admin pasted.

    Returns ``{"match_id": guid}`` for anything carrying a Grassroots GUID,
    ``{"playhq_code": ..., "grade_slug": ..., "season_slug": ...}`` for a
    PlayHQ game-centre link or a bare short code, or ``None`` when it is
    neither.
    """
    text = (raw or "").strip()
    if not text:
        return None
    m = _UUID_RE.search(text)
    if m:
        return {"match_id": m.group(0)}
    m = _PLAYHQ_RE.search(text)
    if m:
        return {
            "season_slug": m.group(1).lower(),
            "grade_slug": m.group(2).lower(),
            "playhq_code": m.group(3).lower(),
        }
    if _BARE_CODE_RE.match(text):
        return {"playhq_code": text.lower(), "grade_slug": "", "season_slug": ""}
    return None


async def _club_results(db: AsyncSession, org) -> tuple[list[dict], dict[str, str]]:
    """The club's own completed matches this season, newest first, each carrying
    its grade name. Returns ``(matches, grade_name_by_guid)``."""
    rows = await _current_grade_rows(db, org.id)
    if not rows:
        return [], {}
    grade_name_by_guid = {guid: gname for guid, _, gname, _ in rows}
    keys = club_match_keys(org)
    since = (date.today() - timedelta(days=_LOOKBACK_DAYS)).isoformat()

    discovered = await asyncio.gather(
        *[gr.get_grade_results(guid, since=since) for guid, *_ in rows],
        return_exceptions=True,
    )
    out: list[dict] = []
    seen: set[str] = set()
    for lst in discovered:
        if not isinstance(lst, list):
            continue
        for m in lst:
            home = (m.get("home_team") or "").lower()
            away = (m.get("away_team") or "").lower()
            # Same rule the Results roundup uses: one side has to be us.
            if not any(k in home or k in away for k in keys):
                continue
            mid = m.get("id")
            if not mid or mid in seen:
                continue
            seen.add(mid)
            out.append(m)
    out.sort(key=lambda x: x.get("played_at") or "", reverse=True)
    return out, grade_name_by_guid


def _card(m: dict, grade_name: str, keys: list[str]) -> dict:
    home = m.get("home_team") or ""
    away = m.get("away_team") or ""
    hl, al = home.lower(), away.lower()
    if any(k in al for k in keys) and not any(k in hl for k in keys):
        ours, opponent, ha = away, home, "A"
    else:
        ours, opponent, ha = home, away, "H"
    return {
        "match_id": m.get("id"),
        "date": m.get("played_at"),
        "round": m.get("round") or "",
        "grade": grade_name or "",
        "team": strip_team_suffix(ours),
        "opponent": strip_team_suffix(opponent),
        "home_away": ha,
        "venue": m.get("venue") or "",
    }


async def resolve_match_reference(db: AsyncSession, org, raw: str) -> dict:
    """Turn a pasted link/id into either a match to load or a list to pick from.

    ``{"kind": "match", "match_id": ...}``  — go straight to the scorecard.
    ``{"kind": "choose", "matches": [...]}`` — the admin picks one.
    ``{"kind": "unknown", "message": ...}``  — nothing usable in the box.

    Every response carries ``source`` — ``"playcricket"`` for a pasted
    Grassroots GUID, ``"playhq"`` for anything born from a playhq.com code,
    ``"unknown"`` otherwise — so the frontend can explain the playhq mistake
    wherever the response lands.
    """
    ref = parse_reference(raw)
    if not ref:
        return {
            "kind": "unknown",
            "source": "unknown",
            "message": "Paste a match link from play.cricket.com.au or playhq.com, or a match ID",
        }
    if ref.get("match_id"):
        return {"kind": "match", "source": "playcricket", "match_id": ref["match_id"]}

    matches, grade_name_by_guid = await _club_results(db, org)
    keys = club_match_keys(org)
    cards = [
        _card(m, grade_name_by_guid.get(m.get("grade_id")) or "", keys) for m in matches
    ]

    grade_slug = ref.get("grade_slug") or ""
    narrowed = cards
    if grade_slug:
        exact = [c for c in cards if _slug(c["grade"]) == grade_slug]
        if not exact:
            # PlayHQ sometimes carries a sponsor or division suffix our grade
            # name doesn't (or the other way round) — fall back to either
            # slug containing the other before giving up on the filter.
            exact = [
                c
                for c in cards
                if _slug(c["grade"])
                and (grade_slug.startswith(_slug(c["grade"])) or _slug(c["grade"]).startswith(grade_slug))
            ]
        if exact:
            narrowed = exact

    source = "playhq" if ref.get("playhq_code") else "playcricket"
    if len(narrowed) == 1:
        return {
            "kind": "match",
            "source": source,
            "match_id": narrowed[0]["match_id"],
            "matched": narrowed[0],
        }

    note = (
        "That's a playhq.com link. BetterPosts pulls match data from "
        "play.cricket.com.au, which uses a different match ID. Find the same "
        "match on play.cricket.com.au and paste that link, or pick it from "
        "your club's recent matches below."
        if ref.get("playhq_code")
        else "Pick the match below."
    )
    return {
        "kind": "choose",
        "source": source,
        "message": note,
        "grade": grade_slug,
        "matches": narrowed[:_MAX_CANDIDATES],
    }
