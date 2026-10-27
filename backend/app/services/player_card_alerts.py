"""Player Cards alert email: "someone has asked you for a swap" and "a card on your wish list is available".

Rules this module holds to (the same ones the selection notices keep):

* "No live email provider" is a failure that is written down, never a success (the console provider only logs).
* Every address goes through `email_suppression.deliverable` as operational mail, so a bounce, a complaint or a person who
  asked to be removed is skipped.
* A player under 18 with a date of birth on file is not emailed directly.
* A club can switch all of it off (`club_card_settings.alerts_enabled`) and a player can switch each kind off (`player_card_prefs`).
* A wish list alert goes once per card until nobody could swap that card any more (the live row in `player_card_alerts` is the
  memory; clearing it re-arms the alert), so a card that stays available is not announced again and again.
* Both entry points run after the request that caused them has committed, on their own session, and never raise.
"""
from __future__ import annotations

import html
import logging
from typing import Optional

from sqlalchemy import text

from app.config.settings import settings
from app.services import email_service, player_age, player_card_catalogue as catalogue, player_card_swaps as swaps, player_cards as cards
from app.services.player_card_social import load_prefs
from app.services.selection_notify import ADULT_AGE, _deliver, _shell

logger = logging.getLogger(__name__)

KIND_SWAP = "swap_asked"
KIND_WANT = "want_available"

REASON_TEXT = {
    "club_off": "The club has switched card alerts off.",
    "player_off": "The player has switched this alert off.",
    "no_email": "No email address on file.",
    "junior": "Under 18, so not emailed directly.",
    "email_not_live": "No live email provider is set up.",
    "no_link": "The club has no player page link.",
    "send_failed": "The email provider refused the send.",
}


def _page_link(club, path: str = "") -> Optional[str]:
    if not club.availability_link_token:
        return None
    return f"{settings.public_base_url}/playerdash/{club.availability_link_token}/cards{path}"


def _first(name: str) -> str:
    n = (name or "").strip()
    if "," in n:
        n = n.split(",", 1)[1].strip() or n
    return n.split(" ")[0] if n else "there"


def _wrap(club, paragraphs: list[str], link: Optional[str], link_label: str, settings_link: Optional[str]) -> tuple[str, str]:
    inner = "".join(f"<p style=\"margin:0 0 14px\">{html.escape(p)}</p>" for p in paragraphs)
    plain = "\n\n".join(paragraphs)
    if link:
        inner += (f'<p style="margin:18px 0"><a href="{html.escape(link)}" style="background:{html.escape(club.accent_color or "#243352")};'
                  f'color:#ffffff;padding:11px 20px;border-radius:8px;text-decoration:none;font-weight:600">{html.escape(link_label)}</a></p>')
        plain += f"\n\n{link_label}: {link}"
    if settings_link:
        inner += f'<p style="margin:18px 0 0;font-size:12px;color:#6b7280">You can switch these emails off in <a href="{html.escape(settings_link)}">Player Cards settings</a>.</p>'
        plain += f"\n\nSwitch these emails off: {settings_link}"
    return _shell(club, inner), plain


async def _gate(db, club, player_id: str, pref: str) -> tuple[Optional[dict], Optional[str]]:
    """The recipient, or the reason they are not to be emailed."""
    row = (await db.execute(text(
        "SELECT COALESCE(display_name_override, name) AS name, email, date_of_birth FROM players "
        "WHERE id = CAST(:p AS UUID) AND organisation_id = CAST(:o AS UUID)"), {"p": player_id, "o": str(club.id)})).mappings().first()
    if not row:
        return None, "no_email"
    enabled = (await db.execute(text(
        "SELECT alerts_enabled FROM club_card_settings WHERE organisation_id = CAST(:o AS UUID)"), {"o": str(club.id)})).scalar()
    if enabled is False:
        return dict(row), "club_off"
    if not (await load_prefs(db, player_id)).get(pref, True):
        return dict(row), "player_off"
    email = (row["email"] or "").strip()
    if not email:
        return dict(row), "no_email"
    age = player_age.age_on(row["date_of_birth"])
    if age is not None and age < ADULT_AGE:
        return dict(row), "junior"
    return dict(row), None


async def _log(db, club, player_id: str, kind: str, ref: str, status: str, detail: Optional[str] = None) -> bool:
    """Write the alert down. False when a live alert for the same thing already exists (nothing was written)."""
    if status == "failed":
        # A failure is not a live alert (it is retried on the next scan), so it must not pile up one row a scan.
        res = await db.execute(text(
            "UPDATE player_card_alerts SET detail = :d, created_at = NOW() WHERE player_id = CAST(:p AS UUID) AND kind = :k "
            "AND ref_key = :r AND cleared_at IS NULL AND status = 'failed'"), {"p": player_id, "k": kind, "r": ref, "d": detail})
        if res.rowcount:
            return True
    res = await db.execute(text(
        "INSERT INTO player_card_alerts (organisation_id, player_id, kind, ref_key, status, detail) "
        "VALUES (CAST(:o AS UUID), CAST(:p AS UUID), :k, :r, :s, :d) ON CONFLICT DO NOTHING"
    ), {"o": str(club.id), "p": player_id, "k": kind, "r": ref, "s": status, "d": detail})
    return bool(res.rowcount)


async def _send(db, club, player_id: str, kind: str, ref: str, pref: str, subject: str, build) -> str:
    """Gate, log and send one alert. `build(recipient)` returns (html, text). Returns the status written."""
    recipient, why = await _gate(db, club, player_id, pref)
    if why is None and not email_service.email_is_live():
        why = "email_not_live"
    if why is not None:
        status = "skipped" if why in ("club_off", "player_off", "no_email", "junior") else "failed"
        await _log(db, club, player_id, kind, ref, status, why)
        return status
    # Claim the live slot first, so two scans racing each other cannot send twice.
    if not await _log(db, club, player_id, kind, ref, "sent"):
        return "duplicate"
    body_html, body_text = build(recipient)
    ok, reason = await _deliver(db, club, to_email=recipient["email"].strip(), to_name=recipient["name"], subject=subject,
                                body_html=body_html, body_text=body_text)
    if not ok:
        await db.execute(text(
            "UPDATE player_card_alerts SET status = 'failed', detail = :d WHERE player_id = CAST(:p AS UUID) AND kind = :k AND ref_key = :r "
            "AND cleared_at IS NULL AND status = 'sent'"), {"d": reason, "p": player_id, "k": kind, "r": ref})
        return "failed"
    return "sent"


async def swap_asked(club_id, swap_id: str) -> None:
    """Tell the person asked that a swap is waiting. Runs after the request committed; never raises."""
    try:
        from app.models.db import Organisation, async_session_maker
        async with async_session_maker() as db:
            club = await db.get(Organisation, club_id)
            if club is None:
                return
            row = (await db.execute(text(
                "SELECT s.from_player_id::text AS f, s.to_player_id::text AS t, s.note, s.parent_swap_id IS NOT NULL AS counter "
                "FROM player_card_swaps s WHERE s.id = CAST(:i AS UUID) AND s.organisation_id = CAST(:o AS UUID)"),
                {"i": swap_id, "o": str(club.id)})).mappings().first()
            if not row:
                return
            names = {r[0]: r[1] for r in (await db.execute(text(
                "SELECT id::text, COALESCE(display_name_override, name) FROM players WHERE id = ANY(CAST(:ids AS uuid[]))"),
                {"ids": [row["f"], row["t"]]})).fetchall()}
            sides = (await swaps._items_of(db, [swap_id]))[swap_id]
            n_give = sum(q for _c, q in sides["give"]); n_want = sum(q for _c, q in sides["want"])
            who = names.get(row["f"], "A player")
            link = _page_link(club, "/swaps")

            def build(rec):
                lines = [f"Hi {_first(rec['name'])},",
                         (f"{who} has answered your swap with a changed one: {n_give} of their cards for {n_want} of yours." if row["counter"]
                          else f"{who} has asked to swap {n_give} of their cards for {n_want} of yours.")]
                if row["note"]:
                    lines.append(f"They wrote: {row['note']}")
                lines.append("Open Player Cards to see the cards and say yes, say no, or send a changed swap back. The request lapses after "
                             f"{swaps.SWAP_DAYS} days.")
                return _wrap(club, lines, link, "See the swap", _page_link(club, "/settings"))

            subject = f"{who} {'answered your swap' if row['counter'] else 'wants to swap cards with you'}"
            if link is None:
                await _log(db, club, row["t"], KIND_SWAP, swap_id, "failed", "no_link")
            else:
                await _send(db, club, row["t"], KIND_SWAP, swap_id, "alert_swaps", subject, build)
            await db.commit()
    except Exception:
        logger.exception("swap alert for %s failed", swap_id)


async def scan_wants(club_id, keys: Optional[list[str]] = None) -> None:
    """For each wish list entry (of the given cards, or all), email the person once when someone could swap that card, and re-arm
    the alert when nobody can any more. Runs after the request committed; never raises."""
    try:
        from app.models.db import Organisation, async_session_maker
        async with async_session_maker() as db:
            club = await db.get(Organisation, club_id)
            if club is None:
                return
            where, params = "organisation_id = CAST(:o AS UUID)", {"o": str(club.id)}
            if keys:
                cards_ = [swaps.parse_key(k) for k in keys]
                subjects = [c[0] for c in cards_ if c[0]]
                specials = [c[1] for c in cards_ if c[1]]
                where += " AND (subject_player_id = ANY(CAST(:subjects AS uuid[])) OR special_id = ANY(CAST(:specials AS uuid[])))"
                params.update({"subjects": subjects, "specials": specials})
            wants = (await db.execute(text(
                f"SELECT player_id::text, subject_player_id::text, special_id::text FROM player_card_wants WHERE {where}"), params)).fetchall()
            if not wants:
                return
            snap = await cards.club_snapshot(db, club)
            specials_map = await swaps._special_subjects(db, club.id, [w[2] for w in wants if w[2]])
            # Who could swap each card, as seen by each wanter (the wanter themselves is left out).
            everyone = await swaps._rows_by_card(db, club.id)
            link = _page_link(club, "/wishlist")
            for player_id, subject, special_id in wants:
                card = (subject, special_id)
                ref = swaps.key_of(*card)
                holders = []
                for owner, held in everyone.items():
                    if owner == player_id or owner not in snap["people"]:
                        continue
                    n = swaps.tradeable(owner, card, held.get(card, 0))
                    if n > 0:
                        holders.append(snap["people"][owner]["display_name"])
                if not holders:
                    await db.execute(text(
                        "UPDATE player_card_alerts SET cleared_at = NOW() WHERE player_id = CAST(:p AS UUID) AND kind = :k AND ref_key = :r AND cleared_at IS NULL"),
                        {"p": player_id, "k": KIND_WANT, "r": ref})
                    continue
                payload = swaps._payload(snap, card, specials_map)
                if payload is None or link is None:
                    continue
                label = f"{payload['name']}: {payload['title']}" if payload.get("title") else f"{payload['name']}'s card"

                def build(rec, label=label, holders=holders):
                    who = holders[0] + (f" and {len(holders) - 1} more" if len(holders) > 1 else "")
                    return _wrap(club, [f"Hi {_first(rec['name'])},", f"A card on your wish list can be swapped now: {label}. {who} could swap you a copy.",
                                        "Open your wish list to ask for it."], link, "Open my wish list", _page_link(club, "/settings"))
                await _send(db, club, player_id, KIND_WANT, ref, "alert_wants", "A card on your wish list is available", build)
            await db.commit()
    except Exception:
        logger.exception("wish list scan for %s failed", club_id)
