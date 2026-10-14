"""Telling people about a confirmed side: the captain's team sheet and the players' notice.

Two sends, both of the CONFIRMED XI (``fixture_lineups``), never a draft:

``send_to_captain``
    One email to the player flagged captain, with the side in batting order and
    every player's mobile from their profile, so the captain does not have to
    look each one up. It goes automatically on Confirm when the club has turned
    ``notify_captain_on_confirm`` on, and a selector can send it by hand at any
    time. The automatic send skips a side the captain already has (same
    ``fingerprint``), so tweaking and re-confirming does not email them twice.

``send_to_players``
    One email per selected player who has an address on file: the match details
    and who the captain is. Always a deliberate button, never automatic. It does
    not carry anybody's phone number.

Rules this module holds to:

* "No live email provider" is a failure the selector can read, never a success
  (the console provider only logs). Every send is refused up front in that case.
* Each address goes through ``email_suppression.deliverable`` as operational
  mail, so a bounce, a complaint or a person who asked to be removed is skipped
  and named, not silently dropped.
* A player under 18 with a date of birth on file is not emailed directly; they
  are listed as skipped so the club can reach a parent through BetterComms.
* Every send writes a ``selection_notices`` row (sent, skipped or failed), so
  the board can say what went where.
* Nothing here raises into a request: the automatic send runs after the confirm
  has committed, on its own session, and swallows its own errors.
"""
from __future__ import annotations

import hashlib
import html
import logging
from datetime import date
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.services import email_service, email_suppression, player_age
from app.services.comms_policy import OPERATIONAL

logger = logging.getLogger(__name__)

ADULT_AGE = 18

# Words the selector reads for a refusal. Anything not here is shown as is.
REASONS = {
    "no_lineup": "No side has been confirmed for this fixture yet.",
    "no_captain": "No captain is flagged in the confirmed side.",
    "no_email": "No email address on the player's profile.",
    "junior": "Under 18: email a parent from BetterComms instead.",
    "email_not_live": "This club's email is not live, so nothing was sent.",
    "already_sent": "The captain already has this exact side.",
    "hard_bounce": "That address has bounced before.",
    "complaint": "That address has marked club email as spam.",
    "suppressed": "That address is suppressed.",
    "privacy_request": "This person asked not to be emailed.",
    "send_failed": "The email provider refused the send.",
}


def reason_text(code: Optional[str]) -> str:
    return REASONS.get(code or "", code or "")


# ── The side, as it stands ───────────────────────────────────────────────────

async def load_sheet(db: AsyncSession, club, fixture_id) -> Optional[dict]:
    """The fixture and its confirmed side, or None when the fixture is not the
    club's. ``players`` is empty when nothing is confirmed."""
    fx = (await db.execute(
        text(
            "SELECT f.id, f.played_on, f.end_on, f.start_time, f.venue, f.opponent_name, "
            "f.home_away, f.label, f.round, COALESCE(t.short_name, t.name) AS team_name "
            "FROM fixtures f LEFT JOIN teams t ON t.id = f.team_id "
            "WHERE f.id = :fid AND f.organisation_id = :org"
        ),
        {"fid": fixture_id, "org": club.id},
    )).mappings().first()
    if fx is None:
        return None
    rows = (await db.execute(
        text(
            "SELECT fl.player_id, COALESCE(p.display_name_override, p.name) AS name, "
            "p.phone, p.email, p.date_of_birth, fl.batting_order, "
            "COALESCE(fl.is_captain, FALSE) AS is_captain, "
            "COALESCE(fl.is_wicket_keeper, FALSE) AS is_wicket_keeper "
            "FROM fixture_lineups fl "
            "JOIN players p ON p.id = fl.player_id AND p.organisation_id = :org "
            "WHERE fl.fixture_id = :fid "
            "ORDER BY fl.batting_order NULLS LAST, name"
        ),
        {"fid": fixture_id, "org": club.id},
    )).mappings().all()
    players = [dict(r) for r in rows]
    return {"fixture": dict(fx), "players": players}


def fingerprint(players: list[dict]) -> str:
    """Identifies the side that was sent: who, in what order, captain and keeper."""
    raw = "|".join(
        f"{p['player_id']}:{p.get('batting_order')}:{int(bool(p['is_captain']))}:{int(bool(p['is_wicket_keeper']))}"
        for p in players
    )
    return hashlib.sha1(raw.encode()).hexdigest()


def _is_junior(p: dict, today: Optional[date] = None) -> bool:
    age = player_age.age_on(p.get("date_of_birth"), today)
    return age is not None and age < ADULT_AGE


def _clean_phone(raw: Optional[str]) -> Optional[str]:
    s = (raw or "").strip()
    return s or None


def _tel(raw: str) -> str:
    return "".join(ch for ch in raw if ch.isdigit() or ch == "+")


# ── Wording ──────────────────────────────────────────────────────────────────

def _when(fx: dict) -> str:
    d = fx.get("played_on")
    day = d.strftime("%a %-d %b") if d else "Date to be confirmed"
    if fx.get("end_on") and d and fx["end_on"] != d:
        day += f" to {fx['end_on'].strftime('%a %-d %b')}"
    return f"{day}, {fx['start_time']}" if fx.get("start_time") else day


def _title(fx: dict) -> str:
    team = fx.get("team_name") or "Team"
    opp = fx.get("opponent_name") or fx.get("label")
    return f"{team} v {opp}" if opp else team


def _match_lines(fx: dict) -> list[tuple[str, str]]:
    lines = [("When", _when(fx))]
    if fx.get("venue"):
        lines.append(("Where", fx["venue"]))
    if fx.get("round"):
        lines.append(("Round", fx["round"]))
    if fx.get("home_away") in ("HOME", "AWAY"):
        lines.append(("Home or away", fx["home_away"].title()))
    return lines


def captain_email(club, sheet: dict, captain: dict) -> tuple[str, str, str]:
    """(subject, html, text) of the captain's team sheet."""
    fx, players = sheet["fixture"], sheet["players"]
    title = _title(fx)
    first = (captain["name"] or "").split(" ")[0] or "there"
    missing = [p["name"] for p in players if not _clean_phone(p.get("phone"))]

    h_rows, t_rows = [], []
    for i, p in enumerate(players, 1):
        tags = [t for t, on in (("C", p["is_captain"]), ("WK", p["is_wicket_keeper"])) if on]
        tag = f" ({', '.join(tags)})" if tags else ""
        phone = _clean_phone(p.get("phone"))
        h_phone = (f'<a href="tel:{html.escape(_tel(phone))}">{html.escape(phone)}</a>'
                   if phone else '<span style="color:#888">no number on file</span>')
        h_rows.append(
            f'<tr><td style="padding:4px 10px 4px 0">{i}</td>'
            f'<td style="padding:4px 10px 4px 0"><strong>{html.escape(p["name"])}</strong>{html.escape(tag)}</td>'
            f'<td style="padding:4px 0">{h_phone}</td></tr>'
        )
        t_rows.append(f"{i}. {p['name']}{tag}  {phone or '(no number on file)'}")

    h_match = "".join(
        f'<tr><td style="padding:2px 10px 2px 0;color:#666">{html.escape(k)}</td>'
        f'<td style="padding:2px 0">{html.escape(v)}</td></tr>' for k, v in _match_lines(fx))
    t_match = "\n".join(f"{k}: {v}" for k, v in _match_lines(fx))
    note_h = note_t = ""
    if missing:
        note_h = ("<p style=\"color:#666\">No mobile on file for: "
                  + html.escape(", ".join(missing)) + ".</p>")
        note_t = "\nNo mobile on file for: " + ", ".join(missing) + "."

    body_h = (
        f"<p>Hi {html.escape(first)},</p>"
        f"<p>You are captain for <strong>{html.escape(title)}</strong>. This is the side as confirmed, "
        f"with each player's mobile from their {html.escape(club.name or 'club')} profile.</p>"
        f'<table style="border-collapse:collapse;margin:0 0 12px">{h_match}</table>'
        f'<table style="border-collapse:collapse">{"".join(h_rows)}</table>'
        f"{note_h}"
        f"<p>Reply to this email if something looks wrong.</p>"
    )
    body_t = (
        f"Hi {first},\n\nYou are captain for {title}. This is the side as confirmed, with each "
        f"player's mobile from their profile.\n\n{t_match}\n\n" + "\n".join(t_rows) + f"{note_t}\n\n"
        "Reply to this email if something looks wrong.\n"
    )
    return f"Team sheet: {title}, {_when(fx)}", body_h, body_t


def player_email(club, sheet: dict, player: dict, captain_name: Optional[str],
                 message: Optional[str]) -> tuple[str, str, str]:
    """(subject, html, text) telling one player they are in."""
    fx = sheet["fixture"]
    title = _title(fx)
    first = (player["name"] or "").split(" ")[0] or "there"
    extra = (message or "").strip()
    h_match = "".join(
        f'<tr><td style="padding:2px 10px 2px 0;color:#666">{html.escape(k)}</td>'
        f'<td style="padding:2px 0">{html.escape(v)}</td></tr>' for k, v in _match_lines(fx))
    t_match = "\n".join(f"{k}: {v}" for k, v in _match_lines(fx))
    cap_h = f"<p>Your captain is <strong>{html.escape(captain_name)}</strong>.</p>" if captain_name else ""
    cap_t = f"Your captain is {captain_name}.\n\n" if captain_name else ""
    msg_h = "".join(f"<p>{html.escape(line)}</p>" for line in extra.splitlines() if line.strip())
    msg_t = (extra + "\n\n") if extra else ""
    body_h = (
        f"<p>Hi {html.escape(first)},</p>"
        f"<p>You have been selected for <strong>{html.escape(title)}</strong>.</p>"
        f'<table style="border-collapse:collapse;margin:0 0 12px">{h_match}</table>'
        f"{cap_h}{msg_h}"
    )
    body_t = f"Hi {first},\n\nYou have been selected for {title}.\n\n{t_match}\n\n{cap_t}{msg_t}"
    return f"Selected: {title}, {_when(fx)}", body_h, body_t


# ── Sending ──────────────────────────────────────────────────────────────────

async def _deliver(db: AsyncSession, club, *, to_email: str, to_name: str,
                   subject: str, body_html: str, body_text: str) -> tuple[bool, Optional[str]]:
    """One email. Returns ``(sent, reason_code)``; never raises."""
    try:
        ok, reason = await email_suppression.deliverable(
            db, email=to_email, organisation_id=club.id, category=OPERATIONAL)
        if not ok:
            return False, reason or "suppressed"
        if not email_service.email_is_live():
            return False, "email_not_live"
        from app.routers.comms import _sender  # the club's From name, address and reply-to
        from_name, from_email, reply_to, _footer = _sender(club)
        msg = email_service.EmailMessage(
            to_email=to_email, to_name=to_name, subject=subject, html=body_html, text=body_text,
            from_email=from_email, from_name=from_name,
            reply_to=reply_to or settings.email_reply_to,
        )
        result = await email_service.get_email_provider().send(msg)
        if not result.ok:
            logger.warning("selection notice to %s failed: %s", to_email, result.error)
            return False, "send_failed"
        return True, None
    except Exception:
        logger.exception("selection notice to %s raised", to_email)
        return False, "send_failed"


async def _record(db: AsyncSession, club, fixture_id, *, kind: str, player_id=None, name=None,
                  email=None, fp=None, status: str, detail: Optional[str] = None,
                  automatic: bool = False, user_id=None) -> None:
    await db.execute(
        text(
            "INSERT INTO selection_notices (fixture_id, organisation_id, kind, player_id, "
            "recipient_name, recipient_email, fingerprint, status, detail, automatic, sent_by) "
            "VALUES (:fid, :org, :kind, :pid, :name, :email, :fp, :status, :detail, :auto, :by)"
        ),
        {"fid": fixture_id, "org": club.id, "kind": kind, "pid": player_id, "name": name,
         "email": email, "fp": fp, "status": status, "detail": detail, "auto": automatic,
         "by": user_id},
    )


async def send_to_captain(db: AsyncSession, club, fixture_id, *, user_id=None,
                          automatic: bool = False) -> dict:
    """Email the confirmed side, with phone numbers, to its captain.

    Returns ``{"status": "sent" | "skipped" | "failed", "reason", "message",
    "captain", "missing_phones"}``. Commits its own notice row."""
    sheet = await load_sheet(db, club, fixture_id)
    if sheet is None:
        return {"status": "failed", "reason": "not_found", "message": "Fixture not found."}
    players = sheet["players"]

    def out(status, reason=None, **extra):
        return {"status": status, "reason": reason, "message": reason_text(reason), **extra}

    if not players:
        return out("skipped", "no_lineup")
    captain = next((p for p in players if p["is_captain"]), None)
    if captain is None:
        return out("skipped", "no_captain")
    fp = fingerprint(players)
    email = (captain.get("email") or "").strip()
    missing = [p["name"] for p in players if not _clean_phone(p.get("phone"))]
    base = {"captain": captain["name"], "missing_phones": missing}

    if not email:
        await _record(db, club, fixture_id, kind="captain", player_id=captain["player_id"],
                      name=captain["name"], fp=fp, status="skipped", detail="no_email",
                      automatic=automatic, user_id=user_id)
        await db.commit()
        return out("skipped", "no_email", **base)

    if automatic:
        already = await db.scalar(
            text("SELECT 1 FROM selection_notices WHERE fixture_id = :fid AND kind = 'captain' "
                 "AND status = 'sent' AND fingerprint = :fp LIMIT 1"),
            {"fid": fixture_id, "fp": fp},
        )
        if already:
            return out("skipped", "already_sent", **base)

    subject, body_h, body_t = captain_email(club, sheet, captain)
    sent, reason = await _deliver(db, club, to_email=email, to_name=captain["name"],
                                  subject=subject, body_html=body_h, body_text=body_t)
    await _record(db, club, fixture_id, kind="captain", player_id=captain["player_id"],
                  name=captain["name"], email=email, fp=fp,
                  status="sent" if sent else "failed", detail=reason,
                  automatic=automatic, user_id=user_id)
    await db.commit()
    return out("sent", None, **base) if sent else out("failed", reason, **base)


async def send_to_players(db: AsyncSession, club, fixture_id, *, user_id=None,
                          message: Optional[str] = None) -> dict:
    """Email each selected player their selection. Returns ``{"sent": n,
    "skipped": [{name, reason, message}], "failed": [...], "status"}``."""
    sheet = await load_sheet(db, club, fixture_id)
    if sheet is None:
        return {"status": "failed", "sent": 0, "skipped": [], "failed": [],
                "message": "Fixture not found."}
    players = sheet["players"]
    if not players:
        return {"status": "skipped", "sent": 0, "skipped": [], "failed": [],
                "message": reason_text("no_lineup")}
    if not email_service.email_is_live():
        return {"status": "failed", "sent": 0, "skipped": [], "failed": [],
                "message": reason_text("email_not_live")}

    captain = next((p for p in players if p["is_captain"]), None)
    fp = fingerprint(players)
    sent, skipped, failed = 0, [], []
    for p in players:
        email = (p.get("email") or "").strip()
        reason = None
        if not email:
            reason = "no_email"
        elif _is_junior(p):
            reason = "junior"
        if reason is None:
            subject, body_h, body_t = player_email(
                club, sheet, p, captain["name"] if captain else None, message)
            ok, reason = await _deliver(db, club, to_email=email, to_name=p["name"],
                                        subject=subject, body_html=body_h, body_text=body_t)
            if ok:
                sent += 1
                await _record(db, club, fixture_id, kind="player", player_id=p["player_id"],
                              name=p["name"], email=email, fp=fp, status="sent", user_id=user_id)
                continue
            failed.append({"name": p["name"], "reason": reason, "message": reason_text(reason)})
            await _record(db, club, fixture_id, kind="player", player_id=p["player_id"],
                          name=p["name"], email=email, fp=fp, status="failed", detail=reason,
                          user_id=user_id)
            continue
        skipped.append({"name": p["name"], "reason": reason, "message": reason_text(reason)})
        await _record(db, club, fixture_id, kind="player", player_id=p["player_id"],
                      name=p["name"], email=email or None, fp=fp, status="skipped", detail=reason,
                      user_id=user_id)
    await db.commit()
    status = "sent" if sent and not failed else "partial" if sent else "failed" if failed else "skipped"
    return {"status": status, "sent": sent, "skipped": skipped, "failed": failed}


async def list_notices(db: AsyncSession, club, fixture_id) -> list[dict]:
    """What has been sent for this fixture, newest first (most recent 50)."""
    rows = (await db.execute(
        text(
            "SELECT kind, recipient_name, status, detail, automatic, created_at, "
            "(fingerprint IS NOT NULL) AS has_fp "
            "FROM selection_notices WHERE fixture_id = :fid AND organisation_id = :org "
            "ORDER BY created_at DESC LIMIT 50"
        ),
        {"fid": fixture_id, "org": club.id},
    )).mappings().all()
    return [
        {"kind": r["kind"], "name": r["recipient_name"], "status": r["status"],
         "reason": r["detail"], "message": reason_text(r["detail"]) if r["detail"] else None,
         "automatic": bool(r["automatic"]),
         "at": r["created_at"].isoformat() if r["created_at"] else None}
        for r in rows
    ]


async def auto_send_captain(club_id, fixture_id, user_id) -> None:
    """The send on Confirm. Runs after the confirm has committed, on its own
    session, and never raises: a failed email must not look like a failed confirm."""
    try:
        from app.models.db import Organisation, async_session_maker
        async with async_session_maker() as session:
            club = await session.get(Organisation, club_id)
            if club is None:
                return
            res = await send_to_captain(session, club, fixture_id, user_id=user_id, automatic=True)
            logger.info("selection auto-send for %s: %s %s", fixture_id, res.get("status"), res.get("reason"))
    except Exception:
        logger.exception("selection auto-send for %s failed", fixture_id)
