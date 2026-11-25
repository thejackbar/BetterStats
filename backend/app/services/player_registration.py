"""Player Dashboard self-registration: people who cannot find their name add themselves.

Two ways in, both from "Can't find your name?" on ``/playerdash/:token``:

* **Claim** an older record. The name list hides dormant and inactive players
  (``routers/availability.active_self_service_players``), so most ex-players are
  already on the books with their stats, just out of sight. They search every past
  player (three letters at least, a handful of matches, never the whole register)
  and pick themselves:

  - a record with a mobile on file is proven the usual way, with its last four
    digits (or by name alone where the club has the PIN off). They are signed in
    straight away and the registration is ``approved``.
  - a record with no mobile on file cannot be proven, and the mobile they type
    would become its PIN, so the registration waits (``pending``) and nothing is
    written to the player until an admin approves it.

* **New**: nobody on the books. A players row is created with ``is_player = false``
  (the existing "Not a player" flag, which keeps them off selection boards, voting
  as a player and fantasy pools) and they are signed in at once. The name joins the
  public name list only once an admin approves it, so a made-up name never shows to
  the rest of the club. Approving someone who said they are a current player turns
  them into a player (``is_player = true``).

An admin archives a registration rather than deleting it. Archiving a new one shuts
its record out of the Player Dashboard and marks it inactive; restoring undoes both.
Claims never change who could already sign in.

Nothing the club typed is overwritten: a claim fills only empty email, mobile and
date of birth on the player (rule 1).
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import Organisation, Player

ROLES: list[dict] = [
    {"key": "current_player", "label": "Current player"},
    {"key": "ex_player", "label": "Past player"},
    {"key": "parent", "label": "Parent or family"},
    {"key": "volunteer", "label": "Volunteer"},
    {"key": "coach", "label": "Coach or official"},
    {"key": "supporter", "label": "Supporter"},
    {"key": "other", "label": "Something else"},
]
ROLE_KEYS = {r["key"] for r in ROLES}
# The roles whose cricket (role, batting hand, bowling...) the form asks about.
PLAYING_ROLES = ("current_player", "ex_player")
ROLE_LABELS = {r["key"]: r["label"] for r in ROLES}

INTERESTS: list[dict] = [
    {"key": "play", "label": "Playing (again)"},
    {"key": "volunteer", "label": "Volunteering"},
    {"key": "coach", "label": "Coaching"},
    {"key": "social", "label": "Social events"},
    {"key": "sponsor", "label": "Sponsoring or helping with fundraising"},
]
INTEREST_KEYS = [i["key"] for i in INTERESTS]
INTEREST_LABELS = {i["key"]: i["label"] for i in INTERESTS}

STATUSES = ("pending", "approved", "archived")
# A registration that still lets its record in.
LIVE = ("pending", "approved")

MAX = {"first_name": 60, "last_name": 60, "email": 200, "phone": 30, "years_played": 80,
       "grades_played": 200, "notes": 1000}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[0-9+()\s\-]+$")


def registration_open(club: Organisation) -> bool:
    """The club's "Let people add themselves" switch. NULL (never chosen) reads as on.

    Cricket only for now: football mounts the shared player page but not the register
    routes, and its past players are read from its own match tables."""
    if settings.sport == "afl":
        return False
    return club.player_registration_enabled is not False


def digits(phone: Optional[str]) -> str:
    return re.sub(r"\D", "", phone or "")


def same_mobile(a: Optional[str], b: Optional[str]) -> bool:
    """Two mobiles are the same number when their last nine digits match, so 0412 345 678
    and +61 412 345 678 agree. Fewer than eight digits never matches anything."""
    da, db_ = digits(a), digits(b)
    if len(da) < 8 or len(db_) < 8:
        return False
    return da[-9:] == db_[-9:]


# Answers to "Anything else?" that say nothing. Kept off the club's list as if left blank.
EMPTY_ANSWERS = {"no", "nope", "nil", "none", "n/a", "na", "nothing", "no thanks", "not really", "-", "--", ".", "x"}


def blank_answer(v: Optional[str]) -> bool:
    return (v or "").strip().lower().rstrip(".!") in EMPTY_ANSWERS or not (v or "").strip()


def clean_text(field: str, raw: Optional[str], required: bool = False) -> Optional[str]:
    v = re.sub(r"\s+", " ", (raw or "")).strip() if field != "notes" else (raw or "").strip()
    if field == "notes" and blank_answer(v):
        v = ""
    if not v:
        if required:
            raise HTTPException(status_code=422, detail=REQUIRED_MSG.get(field, "Please fill that in."))
        return None
    if len(v) > MAX[field]:
        raise HTTPException(status_code=422, detail=f"That is too long ({MAX[field]} characters at most).")
    return v


REQUIRED_MSG = {
    "last_name": "Please give your surname.",
    "first_name": "Please give your first name.",
    "phone": "Please give your mobile number. Its last four digits are how you log in.",
}


def clean_email(raw: Optional[str]) -> Optional[str]:
    v = clean_text("email", raw)
    if v and not _EMAIL_RE.match(v):
        raise HTTPException(status_code=422, detail="That email address does not look right.")
    return v


def clean_phone(raw: Optional[str]) -> str:
    v = clean_text("phone", raw, required=True)
    if not _PHONE_RE.match(v) or not 8 <= len(digits(v)) <= 15:
        raise HTTPException(status_code=422, detail="That mobile number does not look right. Use digits, spaces, + and brackets only.")
    return v


def clean_dob(raw: Optional[date]) -> Optional[date]:
    if raw is None:
        return None
    today = date.today()
    if raw > today or raw.year < today.year - 110:
        raise HTTPException(status_code=422, detail="That date of birth does not look right.")
    return raw


def clean_role(raw: Optional[str]) -> str:
    if raw not in ROLE_KEYS:
        raise HTTPException(status_code=422, detail="Pick what best describes you.")
    return raw


def clean_interests(raw: Optional[Iterable]) -> list[str]:
    got = {k for k in (raw or []) if isinstance(k, str)}
    return [k for k in INTEREST_KEYS if k in got]


# ── What they play ─────────────────────────────────────────────────────────────
# The same values Admin > Players writes (routers/club_admin.PlayerPatch, `_PLAYER_ROLE_SKILLS`,
# frontend lib/playerAttributes.BOWLING_OPTS), so a registration lands on the record exactly as an
# admin's edit would.
PLAYER_ROLES = {
    "Batter": ["BAT"], "Bowler": ["BWL"], "All Rounder": ["ALL"],
    "Wicketkeeper": ["WKT"], "Wicketkeeper-Batter": ["WKT", "BAT"],
}
HANDS = {"RIGHT", "LEFT"}
BOWLING_ACTIONS = {"RIGHT_ARM", "LEFT_ARM"}
BOWLING_TYPES = {"FAST", "FAST_MEDIUM", "MEDIUM", "MEDIUM_FAST", "FINGER_SPIN", "WRIST_SPIN"}
PLAYING_KEYS = ("player_role", "batting_hand", "bowling_action", "bowling_type",
                "is_opening_batsman", "is_overseas", "overseas_country")


def clean_playing(raw: Optional[dict]) -> dict:
    """Known keys with known values only. An unknown value is dropped, never stored: this is a
    public form and the record it may land on is the club's."""
    raw = raw or {}
    out: dict = {}
    if raw.get("player_role") in PLAYER_ROLES:
        out["player_role"] = raw["player_role"]
    if raw.get("batting_hand") in HANDS:
        out["batting_hand"] = raw["batting_hand"]
    if raw.get("bowling_action") in BOWLING_ACTIONS and raw.get("bowling_type") in BOWLING_TYPES:
        out["bowling_action"], out["bowling_type"] = raw["bowling_action"], raw["bowling_type"]
    for k in ("is_opening_batsman", "is_overseas"):
        if isinstance(raw.get(k), bool):
            out[k] = raw[k]
    country = re.sub(r"\s+", " ", str(raw.get("overseas_country") or "")).strip()[:60]
    if out.get("is_overseas") and country:
        out["overseas_country"] = country
    return out


FIELD_LABELS = {
    "phone": "mobile", "email": "email", "date_of_birth": "date of birth", "player_role": "role",
    "batting_hand": "batting hand", "bowling": "bowling", "is_opening_batsman": "opening batter",
    "is_overseas": "overseas", "overseas_country": "country",
}


def fill_empty(player: Player, f: dict, *, phone: bool = True) -> list[str]:
    """Copy what they told us onto the player where the club has NOTHING (rule 1: a club's own
    entry is never overwritten). The email crosses only with their consent to be contacted.
    Returns the labels of what was written, for the audit and the admin list."""
    done: list[str] = []
    if phone and not (player.phone or "").strip() and f.get("phone"):
        player.phone = f["phone"]; done.append("mobile")
    if not (player.email or "").strip() and f.get("email") and f.get("contact_consent"):
        player.email = f["email"]; done.append("email")
    if player.date_of_birth is None and f.get("date_of_birth"):
        player.date_of_birth = f["date_of_birth"]; done.append("date of birth")
    pl = f.get("playing") or {}
    if not player.player_role and pl.get("player_role"):
        player.player_role = pl["player_role"]
        if not (player.skill_positions or []):
            player.skill_positions = list(PLAYER_ROLES[pl["player_role"]])
        done.append("role")
    if not player.batting_hand and pl.get("batting_hand"):
        player.batting_hand = pl["batting_hand"]; done.append("batting hand")
    if not player.bowling_action and not player.bowling_type and pl.get("bowling_type"):
        player.bowling_action, player.bowling_type = pl["bowling_action"], pl["bowling_type"]; done.append("bowling")
    if player.is_opening_batsman is None and "is_opening_batsman" in pl:
        player.is_opening_batsman = pl["is_opening_batsman"]; done.append("opening batter")
    if player.is_overseas is None and "is_overseas" in pl:
        player.is_overseas = pl["is_overseas"]; done.append("overseas")
    if not (player.overseas_country or "").strip() and pl.get("overseas_country") and player.is_overseas:
        player.overseas_country = pl["overseas_country"]; done.append("country")
    if "role" in done:
        # The collectable cards keep a short snapshot of the club's players, roles included.
        from app.services import player_cards
        player_cards.forget(player.organisation_id)
    return done


# ── Smart matching ────────────────────────────────────────────────────────────

def _norm(s: Optional[str]) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def split_stored(name: Optional[str]) -> tuple[str, str]:
    """(first, last) from a stored name: "Last, First", or "First Last" as a club typed it."""
    n = (name or "").strip()
    if "," in n:
        last, first = n.split(",", 1)
        return first.strip(), last.strip()
    parts = n.split()
    return (" ".join(parts[:-1]), parts[-1]) if len(parts) > 1 else ("", n)


def same_person_name(player: Player, first: Optional[str], last: str) -> bool:
    """Surname the same (ignoring case, spaces, hyphens and apostrophes) and first names that
    agree: the same, one the start of the other (Russ and Russell), or an initial on the record
    ("Kingdon, R"). Checked against both the synced name and the club's display name."""
    want_f, want_l = _norm(first), _norm(last)
    if not want_l:
        return False
    for stored in (player.name, player.display_name_override):
        if not stored:
            continue
        f, l = split_stored(stored)
        f, l = _norm(f), _norm(l)
        if l != want_l:
            continue
        if not f or not want_f:
            return True
        if f == want_f or (len(f) == 1 and want_f.startswith(f)) or (len(want_f) == 1 and f.startswith(want_f)):
            return True
        short, long_ = sorted((f, want_f), key=len)
        if len(short) >= 3 and long_.startswith(short):
            return True
    return False


def name_matches(name: Optional[str], query: str) -> bool:
    """Every word typed appears in the name, ignoring case and commas (the frontend's
    nameMatchesSearch, so "smith jo" finds "Smith, John")."""
    hay = (name or "").lower().replace(",", " ")
    return all(t in hay for t in query.lower().replace(",", " ").split())


def stored_name(first: Optional[str], last: str) -> str:
    """The "Last, First" convention the sync and Admin > Players write (a mononym as is),
    which keeps the roster in surname order."""
    return f"{last}, {first}" if first else last


async def latest_by_player(db: AsyncSession, club_id, player_ids: Iterable) -> dict[uuid.UUID, dict]:
    """Each player's most recent registration (kind, status), for those that have one."""
    ids = [str(p) for p in player_ids]
    if not ids:
        return {}
    rows = (await db.execute(text(
        "SELECT DISTINCT ON (player_id) player_id, kind, status FROM player_registrations "
        "WHERE organisation_id = :org AND player_id = ANY(CAST(:ids AS uuid[])) "
        "ORDER BY player_id, created_at DESC"
    ), {"org": str(club_id), "ids": ids})).mappings().all()
    return {r["player_id"]: {"kind": r["kind"], "status": r["status"]} for r in rows}


def shut_out(player: Player, reg: Optional[dict]) -> bool:
    """Whether this record may NOT use the Player Dashboard.

    A record a registration created and an admin archived is shut out. Otherwise a real
    player may, and a non-player may only through a live registration (a coach the club
    marked "Not a player" still cannot, as before)."""
    if reg and reg["kind"] == "new" and reg["status"] == "archived":
        return True
    if player.is_player:
        return False
    return not (reg and reg["status"] in LIVE)


async def may_sign_in(db: AsyncSession, club: Organisation, player: Player) -> bool:
    reg = (await latest_by_player(db, club.id, [player.id])).get(player.id)
    return not shut_out(player, reg)


async def approved_newcomers(db: AsyncSession, club: Organisation) -> list[Player]:
    """Approved self-registered people who are not players (supporters, past players new
    to the books, volunteers...). They join the public name list next to the players."""
    rows = (await db.execute(text(
        "SELECT DISTINCT ON (r.player_id) r.player_id, r.status, r.kind FROM player_registrations r "
        "WHERE r.organisation_id = :org AND r.player_id IS NOT NULL "
        "ORDER BY r.player_id, r.created_at DESC"
    ), {"org": str(club.id)})).mappings().all()
    ids = [r["player_id"] for r in rows if r["status"] == "approved" and r["kind"] == "new"]
    if not ids:
        return []
    from sqlalchemy import select
    res = await db.execute(select(Player).where(
        Player.id.in_(ids), Player.organisation_id == club.id,
        Player.is_player.isnot(True), Player.status != "inactive",
    ))
    return list(res.scalars().all())


def now() -> datetime:
    return datetime.now(timezone.utc)


def serialise(row) -> dict:
    """One registration for the admin list."""
    r = dict(row)
    return {
        "id": str(r["id"]),
        "player_id": str(r["player_id"]) if r.get("player_id") else None,
        "player_name": r.get("player_name"),
        "kind": r["kind"],
        "role": r["role"],
        "role_label": ROLE_LABELS.get(r["role"], r["role"]),
        "first_name": r.get("first_name") or "",
        "last_name": r.get("last_name") or "",
        "email": r.get("email") or "",
        "phone": r.get("phone") or "",
        "date_of_birth": r["date_of_birth"].isoformat() if r.get("date_of_birth") else None,
        "years_played": r.get("years_played") or "",
        "grades_played": r.get("grades_played") or "",
        # A bare "No" to "Anything else?" (saved before the form stopped keeping those) is no note.
        "notes": "" if blank_answer(r.get("notes")) else (r.get("notes") or "").strip(),
        "matched_by": r.get("matched_by"),
        "playing": dict(r.get("playing") or {}),
        "applied": list(r.get("applied") or []),
        "player_status": r.get("player_status"),
        "player_dormant": bool(r.get("player_dormant")),
        "interests": list(r.get("interests") or []),
        "contact_consent": bool(r.get("contact_consent")),
        "status": r["status"],
        "admin_note": r.get("admin_note") or "",
        "contacted_at": r["contacted_at"].isoformat() if r.get("contacted_at") else None,
        "reviewed_at": r["reviewed_at"].isoformat() if r.get("reviewed_at") else None,
        "reviewed_by": r.get("reviewed_by"),
        "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
        "last_played": r["last_played"].isoformat() if r.get("last_played") else None,
        "is_player": r.get("is_player"),
    }
