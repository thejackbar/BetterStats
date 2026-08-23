"""Import Awards — a club's honour board brought in from a spreadsheet.

The third of the BetterFootball import tools, built on the same road as
Import Stats (``routers/afl/imports.py``, season totals per player) and
Import Results (``routers/afl/result_imports.py``, the matches themselves):
upload → auto-map the columns → match the people → match the awards →
review → commit, with a one-click undo afterwards. It reuses the same
DB-free matching engine (``services/import_ingest``) and the same frontend
wizard kit, rather than growing a third copy that drifts.

What it writes, and where:
  * ``player_achievements`` — one row per award won. This is the same table
    the Awards screen reads and writes, so an imported award is
    indistinguishable from one typed in by hand.
  * ``org_award_definitions`` — **an award the club's catalogue doesn't
    carry yet is created**, so the honour board and the Awards dropdown end
    up agreeing. A label that already exists is reused, never duplicated.
  * ``players`` — a name with no match on the roster becomes a real player,
    the same way Import Stats does it. A sheet that starts in 1959 is mostly
    people the sync has never seen.

Two decisions worth knowing before changing anything here:

**Identity is the sheet's own player id when it has one.** A club register
spells the same person several ways ("Michael McCombe" / "Michael Mccombe")
and, more dangerously, holds two different people under one name (two Jack
Reeds). Matching on the name alone silently merges those two careers. When
a player-id column is mapped, rows are grouped by THAT, the spellings
collapse on their own, and a name covering more than one id is reported as
a ``clash`` for the admin to split rather than auto-matched.

**A row with no award named is skipped, not imported.** The reference sheet
behind this feature is 7,360 rows of which 6,241 name no trophy — they are
the club's record of who turned out, not awards. They're counted and
reported as skipped, never silently dropped and never invented into a
nameless award.

Re-uploading the same sheet is safe: a row already on the honour board for
that person, season and award reads as ``exists`` and is left alone.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.capabilities import MANAGE_AWARDS, require_cap
from app.models.db import Organisation, Player, User, get_db
from app.routers.auth import get_current_club
from app.services import import_ingest as ingest
from app.services.audit_log import log_activity

router = APIRouter(prefix="/club-admin/award-imports", tags=["afl-award-imports"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
# How many rows come back with per-row detail for the review table. Every
# count, and the commit itself, always covers the whole sheet — see _resolve.
ROW_DETAIL_LIMIT = 5000

KEY_FIELDS = ("player_name", "award_name")
CONTEXT_FIELDS = ("player_ref", "season_label", "season_end", "category", "subcategory", "detail")
ALL_FIELDS = KEY_FIELDS + CONTEXT_FIELDS

SYNONYMS = {
    "player_name": ["player", "name", "player name", "full name", "recipient", "winner", "member"],
    # "payerid" is not a typo on our side — it is exactly how the reference
    # sheet spells its own player id column, and a club's export tends to
    # keep whatever the original database called it.
    "player_ref": ["player id", "playerid", "payer id", "payerid", "member id", "memberid",
                   "player no", "player number", "person id", "ref", "reference", "id"],
    "season_label": ["season", "year", "yr", "season year", "premiership year", "award year"],
    "season_end": ["season end", "end season", "year to", "to year", "end year", "until"],
    "award_name": ["trophy", "award", "achievement", "honour", "honor", "trophy name",
                   "award name", "medal", "title"],
    "category": ["category", "award category", "award type", "type"],
    "subcategory": ["subcategory", "sub category", "team", "grade", "division", "section", "level"],
    "detail": ["detail", "details", "note", "notes", "comment", "comments", "citation", "votes"],
}

CATEGORIES = ["Club Award", "Premiership", "Office Bearer", "Milestone",
              "Hall of Fame", "Life Membership"]


# ── column auto-mapping ──────────────────────────────────────────────────────

def _norm(h) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(h or "").lower())).strip()


def _field_score(nh: str, syns: list) -> float:
    if nh in syns:
        return 1.0
    return max((SequenceMatcher(None, nh, syn).ratio() for syn in syns), default=0.0)


def _suggest_column_mapping(headers: list) -> dict:
    """Best (header -> field) assignment across the whole matrix at once.

    Global rather than per-field, for the same reason Import Results does it
    that way: "Player" and "PayerID" both score against the player synonyms,
    so picking each field's own best header independently is a coin flip.
    Taking the strongest pair in the whole matrix first (PayerID ->
    player_ref at 1.0, since "payerid" is a synonym in its own right) leaves
    "Player" with only player_name to land on, which is right for both.
    """
    normed = {h: _norm(h) for h in headers if _norm(h)}
    syns = {f: [_norm(x) for x in s] for f, s in SYNONYMS.items()}

    pairs = []
    for h, nh in normed.items():
        for field, s in syns.items():
            score = _field_score(nh, s)
            if score >= 0.6:
                pairs.append((score, h, field))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))

    mapping: dict = {}
    used_headers: set = set()
    for score, h, field in pairs:
        if field in mapping or h in used_headers:
            continue
        mapping[field] = {"column": h, "confidence": round(score, 2)}
        used_headers.add(h)
    return mapping


def _col(mapping: dict, field: str) -> Optional[str]:
    v = mapping.get(field)
    if isinstance(v, dict):
        return v.get("column")
    return v or None


def _cell(row: dict, mapping: dict, field: str) -> str:
    c = _col(mapping, field)
    return str(row.get(c, "") or "").strip() if c else ""


# ── value cleanup ────────────────────────────────────────────────────────────

def clean_season(raw: str) -> Optional[str]:
    """A season label as the club wrote it, minus spreadsheet damage.

    A bare-year cell routinely comes back float-typed from Excel ("1980.0")
    because the parser stringifies every cell as-is. Left alone that becomes
    the award's permanent, wrong-looking season.
    """
    s = (raw or "").strip()
    if not s:
        return None
    s = re.sub(r"^(\d{4})\.0+$", r"\1", s)
    return re.sub(r"\s+", " ", s)


def _award_key(name: str) -> str:
    """Two spellings of the same trophy reduced to one key.

    A register hand-kept since 1959 writes "Runner up Best & Fairest" and
    "Runner Up Best & Fairest" and means one award, so case is noise. So is
    the choice between "&" and "and" — both drop out, which is what makes
    "Best & Fairest" and "Best and Fairest" the same award rather than two.
    """
    n = _norm(name)
    return " ".join(t for t in n.split() if t != "and")


# ── category classification ──────────────────────────────────────────────────

# Roles a club elects or appoints, as opposed to trophies it hands out. The
# test is equality, never a substring: "President" is an office, while
# "Presidents Award" is a trophy the president presents, and a substring
# test files the second one under the first.
OFFICE_ROLES = {
    "president", "vice president", "senior vice president", "junior vice president",
    "secretary", "assistant secretary", "treasurer", "assistant treasurer",
    "committee member", "general committee", "chairman", "chairperson", "chair",
    "head coach", "coach", "senior coach", "assistant coach", "reserves coach",
    "captain", "vice captain", "team manager", "manager", "runner", "trainer",
    "registrar", "public officer",
}

_MILESTONE_RE = re.compile(r"^(\d+)\s*(games?|matches?|goals?)\b")


def classify_award(name: str) -> tuple:
    """(category, subcategory) worked out from the award's own name.

    A club sheet carries the trophy and nothing else, but an award has to
    land in a category to show up in the right place on a player's profile.
    This is a suggestion, not a verdict — every one of them is shown on the
    Awards step and can be changed before anything is written.
    """
    n = _award_key(name)
    if not n:
        return ("Club Award", "Season")
    if "life member" in n:
        return ("Life Membership", "Club")
    if "hall of fame" in n:
        return ("Hall of Fame", "Club")
    if "premiership" in n or "premiers" in n or n in ("flag", "flags"):
        return ("Premiership", "Team")
    m = _MILESTONE_RE.match(n)
    if m:
        return ("Milestone", "Goals" if m.group(2).startswith("goal") else "Games")
    if n in OFFICE_ROLES:
        return ("Office Bearer", "Committee")
    return ("Club Award", "Season")


# ── db lookups ───────────────────────────────────────────────────────────────

async def _org_players(db: AsyncSession, org_id) -> list:
    rows = (await db.execute(select(Player).where(Player.organisation_id == org_id))).scalars().all()
    return [(str(p.id), p.display_name or p.name or "") for p in rows]


async def _org_definitions(db: AsyncSession, org_id) -> list:
    rows = await db.execute(text("""
        SELECT id, category, subcategory, achievement, display_name, active
        FROM org_award_definitions
        WHERE org_id = :org AND achievement IS NOT NULL AND achievement <> ''
        ORDER BY sort_order, achievement
    """), {"org": str(org_id)})
    return [dict(r) for r in rows.mappings().all()]


async def _existing_awards(db: AsyncSession, org_id) -> tuple:
    """What's already on the honour board, as two lookup sets.

    Keyed both by player id and by normalised name because a row whose
    player is about to be CREATED has no id to compare against yet — the
    name is the only handle there, and without it a second upload of the
    same sheet would double every award for every new player.
    """
    rows = await db.execute(text("""
        SELECT player_id, player_name, season, achievement
        FROM player_achievements WHERE org_id = :org
    """), {"org": str(org_id)})
    by_id: set = set()
    by_name: set = set()
    for r in rows:
        season = (r.season or "").strip().lower()
        award = _award_key(r.achievement or "")
        if r.player_id:
            by_id.add((str(r.player_id), season, award))
        by_name.add((_norm(r.player_name or ""), season, award))
    return by_id, by_name


# ── request models ───────────────────────────────────────────────────────────

class ResolveRequest(BaseModel):
    rows: list[dict] = []
    mapping: dict = {}
    # keyed by the player identity key returned on each /resolve player row
    player_overrides: dict = {}
    # keyed by the award key: a definition id, '__new__' or '__skip__'
    award_overrides: dict = {}
    # keyed by the award key: {'category': ..., 'subcategory': ...}, applied
    # to awards being created
    award_meta: dict = {}


class CommitRequest(ResolveRequest):
    filename: Optional[str] = None


def _apply_player_overrides(identities: list, overrides: dict) -> None:
    for ident in identities:
        choice = (overrides or {}).get(ident["key"])
        if not choice:
            continue
        if choice == "__skip__":
            ident.update(player_id=None, status="skip")
        elif choice == "__new__":
            ident.update(player_id=None, status="new")
        else:
            ident.update(player_id=str(choice), status="manual", confidence=1.0)


# ── the reconciler ───────────────────────────────────────────────────────────

def _build_identities(rows: list, mapping: dict) -> tuple:
    """Group the sheet's rows into people.

    The identity is the sheet's own player id where one is mapped, otherwise
    the normalised name. Each identity carries the spelling it uses most
    often, which is what gets matched and what a newly created player is
    named — so a register that writes "Mccombe" once and "McCombe" nine
    times creates the McCombe.

    One id does NOT always mean one person. In the reference sheet nine ids
    are held by two different people each ("Zac Barrett" and "Luca Almiento"
    both under 1580) — an id reused when someone left, most likely. So an id
    is only allowed to unify rows whose names agree once case and
    punctuation are set aside; where they genuinely differ the id is split
    back into one identity per name, because giving one player the other's
    honours is the worst thing this tool could do.
    """
    name_col = _col(mapping, "player_name")
    ref_col = _col(mapping, "player_ref")

    groups: dict = {}
    for i, raw in enumerate(rows):
        nm = str(raw.get(name_col, "") or "").strip() if name_col else ""
        ref = str(raw.get(ref_col, "") or "").strip() if ref_col else ""
        # A float-typed id cell ("1957.0") is the same id as 1957.
        ref = re.sub(r"^(\d+)\.0+$", r"\1", ref)
        if not nm and not ref:
            continue
        gkey = f"ref:{ref}" if ref else f"name:{_norm(nm)}"
        g = groups.get(gkey)
        if g is None:
            g = groups[gkey] = {"ref": ref or None, "by_name": {}}
        sub = g["by_name"].setdefault(_norm(nm), {"spellings": Counter(), "row_indexes": []})
        if nm:
            sub["spellings"][nm] += 1
        sub["row_indexes"].append(i)

    out, key_by_row = [], {}
    for gkey, g in groups.items():
        split = len(g["by_name"]) > 1
        for nkey, sub in g["by_name"].items():
            key = f"{gkey}|{nkey}" if split else gkey
            name = sub["spellings"].most_common(1)[0][0] if sub["spellings"] else (g["ref"] or "")
            spellings = sorted(sub["spellings"]) if len(sub["spellings"]) > 1 else []
            note = None
            if split:
                others = [s["spellings"].most_common(1)[0][0] for k, s in g["by_name"].items()
                          if k != nkey and s["spellings"]]
                note = (f"Your sheet has ID {g['ref']} against a different name too "
                        f"({', '.join(others[:3])}). Kept as separate people, since one ID "
                        f"covering two names is an ID that was reused.")
            elif spellings:
                note = ("Spelled " + ", ".join(f'"{s}"' for s in spellings[:3])
                        + " in your sheet, treated as one person.")
            out.append({"key": key, "ref": g["ref"], "raw_name": name,
                        "rows": len(sub["row_indexes"]), "spellings": spellings,
                        "sheet_note": note})
            for i in sub["row_indexes"]:
                key_by_row[i] = key
    return out, key_by_row


def _match_identities(identities: list, players: list) -> None:
    """Attach a roster match to each identity, in place.

    Names are matched once each and then fanned out, so a person with nine
    rows costs one match. Where one name covers more than one identity the
    match is deliberately WITHHELD from all of them: that's two different
    people in the club's own records, and auto-accepting would put one
    person's honours on the other's profile. They come back as a clash with
    the roster player offered as a candidate for each.
    """
    by_name: dict = {}
    for ident in identities:
        by_name.setdefault(_norm(ident["raw_name"]), []).append(ident)

    unique_names = []
    seen = set()
    for ident in identities:
        n = _norm(ident["raw_name"])
        if n not in seen:
            seen.add(n)
            unique_names.append(ident["raw_name"])
    matches = ingest.match_players(unique_names, players)

    # match_players keys on the exact string it was handed; a second identity
    # spelling the name differently in case still has to find it.
    by_raw = {_norm(k): v for k, v in matches.items()}

    for ident in identities:
        m = dict(by_raw.get(_norm(ident["raw_name"]), {"candidates": [], "status": "none", "auto_status": "none"}))
        siblings = by_name.get(_norm(ident["raw_name"]), [])
        if len(siblings) > 1:
            cands = list(m.get("candidates") or [])
            if m.get("player_id"):
                cands = [{"player_id": m["player_id"], "name": m.get("matched_name") or ident["raw_name"],
                          "confidence": m.get("confidence")}] + cands
            refs = [s["ref"] for s in siblings if s["ref"]]
            m = {
                "player_id": None, "confidence": m.get("confidence"),
                "status": "clash", "auto_status": "clash", "candidates": cands,
                "note": ("Your sheet has this name under "
                         + (f"{len(siblings)} different player IDs ({', '.join(refs[:4])})"
                            if refs else f"{len(siblings)} separate entries")
                         + ". Point each at the right player so one person's honours "
                           "don't land on the other's profile."),
            }
        if ident.get("sheet_note"):
            m["note"] = ((m.get("note") + " ") if m.get("note") else "") + ident["sheet_note"]
        ident.update(m)


def _match_awards(labels: list, definitions: list, overrides: dict, meta: dict) -> dict:
    """Each distinct award label -> the catalogue entry it belongs to.

    Exact first (on the definition's own name or its display name), then a
    close match offered as a suggestion. A label with no exact hit DEFAULTS
    TO BEING CREATED rather than being quietly folded into whichever
    existing award looked nearest — "Best Clubman" and "Best Clubperson" are
    two real, different trophies at plenty of clubs, and the admin is the
    one who knows.
    """
    by_norm: dict = {}
    for d in definitions:
        for nm in (d["achievement"], d.get("display_name")):
            if nm:
                by_norm.setdefault(_award_key(nm), d)

    out: dict = {}
    for lab in labels:
        key = _award_key(lab["key"])
        hit = by_norm.get(key)
        if hit:
            m = {"status": "matched", "auto_status": "matched", "definition_id": str(hit["id"]),
                 "category": hit["category"], "subcategory": hit.get("subcategory"),
                 "achievement": hit["achievement"], "candidates": []}
        else:
            cands = []
            for d in definitions:
                score = SequenceMatcher(None, key, _award_key(d["achievement"])).ratio()
                # Loose on purpose: a suggestion never changes what happens
                # by itself (the label is still created unless the admin
                # picks the suggestion), so the cost of one too many is a
                # line in a dropdown, and the cost of one too few is a
                # duplicate trophy in the catalogue.
                if score >= 0.80:
                    cands.append({"definition_id": str(d["id"]), "name": d["achievement"],
                                  "confidence": round(score, 2)})
            cands.sort(key=lambda c: -c["confidence"])
            cat, sub = classify_award(lab["name"])
            m = {"status": "fuzzy" if cands else "new",
                 "auto_status": "fuzzy" if cands else "new",
                 "definition_id": None, "category": cat, "subcategory": sub,
                 "achievement": lab["name"], "candidates": cands[:5]}

        choice = (overrides or {}).get(lab["key"])
        if choice == "__skip__":
            m.update(status="skip", definition_id=None)
        elif choice == "__new__":
            cat, sub = classify_award(lab["name"])
            m.update(status="new", definition_id=None, category=cat, subcategory=sub,
                     achievement=lab["name"])
        elif choice:
            hit = next((d for d in definitions if str(d["id"]) == str(choice)), None)
            if hit:
                m.update(status="manual", definition_id=str(hit["id"]), category=hit["category"],
                         subcategory=hit.get("subcategory"), achievement=hit["achievement"])

        # Category/subcategory are only the admin's to set on an award being
        # created — an existing definition owns its own filing, and letting
        # an upload rewrite it would retype a category the club set up on the
        # Award Types screen.
        if m["status"] in ("new", "fuzzy"):
            over = (meta or {}).get(lab["key"]) or {}
            if over.get("category") in CATEGORIES:
                m["category"] = over["category"]
            if "subcategory" in over:
                m["subcategory"] = (over.get("subcategory") or "").strip() or None
        out[lab["key"]] = m
    return out


async def _resolve(db: AsyncSession, org_id, req: ResolveRequest) -> dict:
    if not _col(req.mapping, "player_name"):
        raise HTTPException(422, "No column is mapped to the player name.")
    if not _col(req.mapping, "award_name"):
        raise HTTPException(422, "No column is mapped to the award.")

    identities, key_by_row = _build_identities(req.rows, req.mapping)
    players = await _org_players(db, org_id)
    _match_identities(identities, players)
    _apply_player_overrides(identities, req.player_overrides)
    ident_by_key = {i["key"]: i for i in identities}

    # Distinct awards, keeping the spelling the sheet uses most often.
    award_spellings: dict = {}
    for raw in req.rows:
        nm = _cell(raw, req.mapping, "award_name")
        if nm:
            award_spellings.setdefault(_award_key(nm), Counter())[nm] += 1
    labels = [{"key": k, "name": c.most_common(1)[0][0], "rows": sum(c.values())}
              for k, c in award_spellings.items()]
    labels.sort(key=lambda l: (-l["rows"], l["name"]))

    definitions = await _org_definitions(db, org_id)
    amatch = _match_awards(labels, definitions, req.award_overrides, req.award_meta)

    have_by_id, have_by_name = await _existing_awards(db, org_id)

    built = []
    seen: set = set()
    for i, raw in enumerate(req.rows):
        key = key_by_row.get(i)
        ident = ident_by_key.get(key) if key else None
        award_raw = _cell(raw, req.mapping, "award_name")
        akey = _award_key(award_raw) if award_raw else None
        am = amatch.get(akey) if akey else None
        season = clean_season(_cell(raw, req.mapping, "season_label"))

        row = {
            "index": i,
            "player_key": key,
            "player_ref": ident["ref"] if ident else None,
            "player_name": ident["raw_name"] if ident else None,
            "player_id": ident.get("player_id") if ident else None,
            "season": season,
            "season_end": clean_season(_cell(raw, req.mapping, "season_end")),
            "award_raw": award_raw or None,
            "achievement": (am or {}).get("achievement") or award_raw or None,
            "category": (am or {}).get("category"),
            "subcategory": _cell(raw, req.mapping, "subcategory") or (am or {}).get("subcategory"),
            "detail": _cell(raw, req.mapping, "detail") or None,
            "creates_player": bool(ident and ident.get("status") == "new"),
            "creates_award": bool(am and am.get("status") in ("new", "fuzzy")),
        }
        # A Category column in the sheet itself outranks anything worked out
        # from the name — the club said so explicitly on that row.
        sheet_cat = _cell(raw, req.mapping, "category")
        if sheet_cat:
            hit = next((c for c in CATEGORIES if _norm(c) == _norm(sheet_cat)), None)
            row["category"] = hit or sheet_cat

        if not ident or not ident["raw_name"]:
            row["status"], row["status_note"] = "blocked", "No player name on this row."
        elif not award_raw:
            # The single biggest bucket in a real club register: a row that
            # records a season played, with no trophy attached.
            row["status"], row["status_note"] = "skipped", "No award named on this row."
        elif ident.get("status") == "skip":
            row["status"], row["status_note"] = "skipped", "Player skipped."
        elif am and am["status"] == "skip":
            row["status"], row["status_note"] = "skipped", "Award skipped."
        elif not ident.get("player_id") and ident.get("status") != "new":
            row["status"], row["status_note"] = "blocked", (
                "Two people share this name. Pick the right one on the Players step."
                if ident.get("status") == "clash" else "Match this player on the Players step.")
        else:
            dedupe = (key, (season or "").lower(), akey)
            pid = ident.get("player_id")
            # Match on the player id when there is one, and fall back to the
            # name ONLY for someone about to be created. Checking both would
            # read one Jack Reed's honour as already recorded because the
            # other Jack Reed has it.
            already = (pid, (season or "").lower(), akey) in have_by_id if pid else \
                      (_norm(ident["raw_name"]), (season or "").lower(), akey) in have_by_name
            if dedupe in seen:
                row["status"], row["status_note"] = "duplicate", "Same award, same season, same player, imported once."
            elif already:
                row["status"], row["status_note"] = "exists", "Already on the honour board, left alone."
            else:
                seen.add(dedupe)
                row["status"], row["status_note"] = "ready", None
        built.append(row)

    importable = [r for r in built if r["status"] == "ready"]
    # Whose names actually have a trophy against them. A person the sheet
    # only records as having turned out has nothing riding on their match,
    # so counting them as "needs a decision" would send an admin hunting for
    # a problem that isn't one.
    keys_with_awards = {r["player_key"] for r in built if r["award_raw"] and r["player_key"]}
    for ident in identities:
        ident["has_awards"] = ident["key"] in keys_with_awards

    # ── summaries ───────────────────────────────────────────────────────────
    by_award: dict = {}
    for r in importable:
        k = r["achievement"] or "—"
        s = by_award.setdefault(k, {"achievement": k, "category": r["category"], "count": 0,
                                    "first": None, "last": None, "creates": r["creates_award"]})
        s["count"] += 1
        yr = (r["season"] or "").strip()
        if yr:
            s["first"] = yr if s["first"] is None else min(s["first"], yr)
            s["last"] = yr if s["last"] is None else max(s["last"], yr)
    award_summary = sorted(by_award.values(), key=lambda s: (-s["count"], s["achievement"]))

    warnings = []
    blocked = [r for r in built if r["status"] == "blocked"]
    if blocked:
        reasons: dict = {}
        for r in blocked:
            reasons[r["status_note"]] = reasons.get(r["status_note"], 0) + 1
        top = sorted(reasons.items(), key=lambda kv: -kv[1])[:3]
        warnings.append({"kind": "sheet_error", "text":
                         f"{len(blocked)} row(s) can't be imported yet, "
                         + "; ".join(f"{n}× {why}" for why, n in top)})
    clashes = [i for i in identities if i.get("status") == "clash"]
    if clashes:
        names = sorted({i["raw_name"] for i in clashes})
        at_stake = [i for i in clashes if i["has_awards"]]
        warnings.append({
            "kind": "sheet_error" if at_stake else "check",
            "text": (f"{len(names)} name(s) cover more than one person in your sheet: "
                     + ", ".join(names[:5]) + (" …" if len(names) > 5 else "")
                     + (". Set each one on the Players step, or their awards won't import."
                        if at_stake else
                        ". None of them has an award in this sheet, so nothing is waiting on it.")),
        })
    no_award = sum(1 for r in built if r["status"] == "skipped" and r["status_note"] == "No award named on this row.")
    if no_award:
        warnings.append({"kind": "check", "text":
                         f"{no_award} row(s) name no award, skipped. Those are usually a record of who "
                         "played that year rather than an honour."})
    exists = sum(1 for r in built if r["status"] == "exists")
    if exists:
        warnings.append({"kind": "check", "text":
                         f"{exists} row(s) are already on the honour board. Left alone, so re-uploading a "
                         "corrected sheet never doubles anything up."})
    new_defs = sorted({r["achievement"] for r in importable if r["creates_award"] and r["achievement"]})
    if new_defs:
        warnings.append({"kind": "check", "text":
                         f"{len(new_defs)} award(s) aren't in your Award Types yet and will be added: "
                         + ", ".join(new_defs[:6]) + ("…" if len(new_defs) > 6 else "")})
    no_season = sum(1 for r in importable if not r["season"])
    if no_season:
        warnings.append({"kind": "check", "text":
                         f"{no_season} row(s) have no season, they import without a year against them."})

    detail = built[:ROW_DETAIL_LIMIT]

    return {
        "players": identities,
        "awards": [{**lab, **amatch[lab["key"]]} for lab in labels],
        "award_options": [{"id": str(d["id"]), "name": d["achievement"],
                           "category": d["category"], "subcategory": d.get("subcategory")}
                          for d in definitions],
        "categories": CATEGORIES,
        "rows": detail,
        "rows_truncated": len(built) - len(detail),
        "award_summary": award_summary,
        "warnings": warnings,
        "totals": {
            "rows": len(built),
            "importable": len(importable),
            "skipped": sum(1 for r in built if r["status"] == "skipped"),
            "blocked": len(blocked),
            "duplicates": sum(1 for r in built if r["status"] == "duplicate"),
            "exists": exists,
            "players_matched": sum(1 for i in identities if i.get("player_id")),
            "players_new": sum(1 for i in identities if i.get("status") == "new"),
            # Only people who actually won something — see keys_with_awards.
            "players_unresolved": sum(1 for i in identities
                                      if i["has_awards"] and not i.get("player_id")
                                      and i.get("status") not in ("new", "skip")),
            "awards_matched": sum(1 for m in amatch.values() if m["status"] in ("matched", "manual")),
            "awards_new": len(new_defs),
        },
        "_importable": importable,
        "_identities": identities,
        "_awards": amatch,
    }


# ── endpoints ────────────────────────────────────────────────────────────────

@router.get("/template.csv")
async def template():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Player ID", "Player", "Year", "Trophy", "Category", "Subcategory", "Detail"])
    writer.writerow(["1", "Targett, Stephen", "1980", "Best & Fairest", "Club Award", "Season", ""])
    writer.writerow(["2", "Thompson, Shane", "1969", "Leading Goalkicker", "Club Award", "A Grade", "62 goals"])
    writer.writerow(["5", "Isaac, Justin", "2016", "Life Membership", "Life Membership", "Club", ""])
    return StreamingResponse(
        iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=afl_award_import_template.csv"},
    )


@router.post("/preview")
async def preview_upload(
    file: UploadFile = File(...),
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
):
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large")
    parsed = ingest.parse_upload(file.filename or "", content)
    if not parsed["rows"]:
        raise HTTPException(400, "No data found in file")
    mapping = _suggest_column_mapping(parsed["headers"])
    return {"headers": parsed["headers"], "rows": parsed["rows"], "mapping": mapping,
            "row_count": len(parsed["rows"])}


@router.post("/resolve")
async def resolve(
    req: ResolveRequest,
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    resolved = await _resolve(db, club.id, req)
    for k in ("_importable", "_identities", "_awards"):
        resolved.pop(k)
    return resolved


@router.post("/commit")
async def commit(
    req: CommitRequest,
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    org_id = str(club.id)
    resolved = await _resolve(db, club.id, req)
    importable = resolved["_importable"]
    if not importable:
        raise HTTPException(422, "Nothing to import, no rows are ready. Check the player and award "
                                 "matches and try again.")

    # 1. People the club doesn't have yet. Same identity rule as Import
    #    Stats: a plain uuid4 player row on this org, named as the sheet
    #    spells them.
    new_pid_by_key: dict = {}
    for ident in resolved["_identities"]:
        if ident.get("status") == "new" and ident["raw_name"]:
            p = Player(id=uuid.uuid4(), name=ident["raw_name"], organisation_id=club.id)
            db.add(p)
            new_pid_by_key[ident["key"]] = str(p.id)
    if new_pid_by_key:
        await db.flush()

    # 2. Awards the catalogue doesn't carry yet. This is what keeps the
    #    honour board and the Awards dropdown from disagreeing after an
    #    import — without it every historical trophy would be a string that
    #    exists on player rows and nowhere in the club's own award list.
    next_order = (await db.execute(text(
        "SELECT COALESCE(MAX(sort_order), 0) FROM org_award_definitions WHERE org_id = :org"
    ), {"org": org_id})).scalar() or 0
    defs_created = 0
    created_defs: dict = {}
    for akey, m in resolved["_awards"].items():
        if m["status"] not in ("new", "fuzzy") or not m.get("achievement"):
            continue
        if not any(r["status"] == "ready" and _award_key(r["award_raw"] or "") == akey for r in importable):
            continue
        next_order += 1
        row = await db.execute(text("""
            INSERT INTO org_award_definitions
                (id, org_id, category, subcategory, achievement, sort_order)
            VALUES (gen_random_uuid(), :org, :category, :subcategory, :achievement, :sort_order)
            RETURNING id
        """), {"org": org_id, "category": m["category"], "subcategory": m.get("subcategory"),
               "achievement": m["achievement"], "sort_order": next_order})
        created_defs[akey] = str(row.scalar())
        defs_created += 1

    # 3. The awards themselves.
    batch_id = uuid.uuid4()
    created = 0
    for r in importable:
        pid = r["player_id"] or new_pid_by_key.get(r["player_key"])
        await db.execute(text("""
            INSERT INTO player_achievements
                (org_id, player_id, player_name, season, season_end, category, subcategory,
                 achievement, detail, import_batch_id)
            VALUES (:org, :pid, :pname, :season, :season_end, :category, :subcategory,
                    :achievement, :detail, :batch)
        """), {
            "org": org_id, "pid": pid, "pname": r["player_name"],
            "season": r["season"], "season_end": r["season_end"],
            "category": r["category"] or "Club Award", "subcategory": r["subcategory"] or None,
            "achievement": r["achievement"], "detail": r["detail"], "batch": str(batch_id),
        })
        created += 1

    await db.execute(text("""
        INSERT INTO achievement_import_batches (id, org_id, filename, row_count, created_count, status)
        VALUES (:id, :org, :filename, :row_count, :created_count, 'imported')
    """), {"id": str(batch_id), "org": org_id, "filename": req.filename,
           "row_count": len(req.rows), "created_count": created})

    await log_activity(
        db, org_id=club.id, user_id=current_user.id, action="afl_import_awards",
        target_type="import_batch", target_id=str(batch_id),
        details={"awards": created, "players_created": len(new_pid_by_key),
                 "definitions_created": defs_created, "rows": len(req.rows)},
    )
    await db.commit()

    return {
        "batch_id": str(batch_id),
        "awards_created": created,
        "players_created": len(new_pid_by_key),
        "definitions_created": defs_created,
        "rows_skipped": resolved["totals"]["skipped"],
        "rows_blocked": resolved["totals"]["blocked"],
        "already_recorded": resolved["totals"]["exists"],
        "award_summary": resolved["award_summary"][:50],
    }


@router.get("")
async def list_imports(
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Shares ``achievement_import_batches`` with the Awards screen's own
    log, so an upload appears in one place rather than two."""
    rows = await db.execute(text("""
        SELECT id, filename, row_count, created_count, status, created_at, undone_at
        FROM achievement_import_batches WHERE org_id = :org
        ORDER BY created_at DESC
    """), {"org": str(club.id)})
    return [dict(r) for r in rows.mappings().all()]


@router.get("/{batch_id}/awards")
async def list_batch_awards(
    batch_id: str,
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    rows = await db.execute(text("""
        SELECT a.id, a.player_id, a.player_name, a.season, a.category, a.subcategory,
               a.achievement, a.detail
        FROM player_achievements a
        WHERE a.import_batch_id = :batch AND a.org_id = :org
        ORDER BY a.season DESC NULLS LAST, a.achievement, a.player_name
    """), {"batch": batch_id, "org": str(club.id)})
    return [dict(r) for r in rows.mappings().all()]


@router.post("/{batch_id}/undo")
async def undo_import(
    batch_id: str,
    current_user: User = Depends(require_cap(MANAGE_AWARDS)),
    club: Organisation = Depends(get_current_club),
    db: AsyncSession = Depends(get_db),
):
    """Removes the awards this upload added.

    Players and award types the import created are deliberately LEFT — same
    call Import Stats makes. A player record is a person, and an award type
    is a catalogue entry the club may already have started using elsewhere;
    deleting either because one upload was reversed does more damage than
    leaving a row that's easy to delete by hand.
    """
    org_id = str(club.id)
    found = await db.execute(text(
        "SELECT id FROM achievement_import_batches WHERE id = :id AND org_id = :org AND undone_at IS NULL"
    ), {"id": batch_id, "org": org_id})
    if found.first() is None:
        raise HTTPException(404, "Import batch not found or already undone")

    result = await db.execute(text(
        "DELETE FROM player_achievements WHERE import_batch_id = :batch AND org_id = :org"
    ), {"batch": batch_id, "org": org_id})
    await db.execute(text(
        "UPDATE achievement_import_batches SET undone_at = NOW(), status = 'undone' WHERE id = :id"
    ), {"id": batch_id})

    await log_activity(
        db, org_id=club.id, user_id=current_user.id, action="undo_afl_import_awards",
        target_type="import_batch", target_id=batch_id,
    )
    await db.commit()
    return {"status": "undone", "awards_removed": result.rowcount}
