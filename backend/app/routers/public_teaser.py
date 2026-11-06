"""The public page behind a club's teaser link (``/preview/{token}``).

A prospect club is emailed (or shown an ad that lands on) a page built from its
own public Cricket Australia figures. Anything on the page opens the same
invitation to claim the club through the trial wizard. Three unauthenticated
routes:

  GET  /public/teaser/by-club?id=..&id=..     the token for the club a visitor just picked on /trial
  GET  /public/teaser/{token}                 the snapshot and what the page leads with
  GET  /public/teaser/{token}/image/{fmt}.png the club's picture (email, share card, ads)
  POST /public/teaser/{token}/event           a view / tile tap / claim beacon

Nothing here needs the self-serve registration flag: the page is an
introduction, and the wizard it hands over to has its own gate. The token is
the whole credential (16 random bytes, made once and never rotated, so a link
already sent keeps working); an unknown, malformed or not-yet-good snapshot is
a plain 404 that tells nothing about which case it was.

Only the ``ok`` snapshots are served. ``empty``, ``junior_only`` and ``error``
have nothing to show, and an unsuitable club must never get a page.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services import club_teaser, club_teaser_images, club_teaser_link, rate_limit
from app.services.login_audit import client_ip
from app.services.usage_tracker import record_event_bg

router = APIRouter(prefix="/public/teaser", tags=["public-teaser"])

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
READ_LIMIT, READ_WINDOW = 120, 3600
EVENT_LIMIT, EVENT_WINDOW = 120, 3600
# What a page may report. An allowlist, so this cannot be used to write
# arbitrary strings into usage_events.
EVENT_KINDS = {"view", "tile", "claim_open", "claim_go"}


async def _row(db: AsyncSession, token: str):
    if not TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="Not found")
    # ``registered_slug`` is set only for a LIVE customer (paying, or still on a
    # running trial), whose page redirects to its own site. An archived club, or
    # one whose trial lapsed without a subscription, keeps its teaser page: it is
    # what a returning admin should see.
    row = (await db.execute(text("""
        SELECT t.snapshot, t.version, t.theme, mc.logo_url AS directory_logo, mc.id AS club_id, mc.existing_org_id,
               (CASE WHEN """ + club_teaser_link.LIVE_CUSTOMER_SQL + """ THEN
                  (SELECT o.slug FROM organisations o WHERE o.id = mc.existing_org_id) END) AS registered_slug
        FROM club_teaser_snapshots t
        JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
        WHERE t.token = :t AND t.status = 'ok' AND t.snapshot IS NOT NULL
    """), {"t": token})).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


def _public_theme(theme):
    """Only what the page needs, and only if it is well formed: the colour goes
    into a style attribute, so anything that is not ``#rrggbb`` is dropped."""
    if not isinstance(theme, dict):
        return None
    ok = lambda v: isinstance(v, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", v) is not None  # noqa: E731
    mode = theme.get("mode") if theme.get("mode") in ("dark", "light") else "dark"
    accent = theme.get("accent") if ok(theme.get("accent")) else None
    return {"mode": mode, "accent": accent,
            "on_accent": theme.get("on_accent") if accent and ok(theme.get("on_accent")) else None}


@router.get("/by-club")
async def teaser_for_club(request: Request, id: list[str] = Query(default=[]),
                          db: AsyncSession = Depends(get_db)):
    """What /trial asks once a visitor has picked their club from the search:
    is there a teaser page for it, and which. ``ids`` are every identifier the
    picker gave for the club; the match rules (CA id first, then the directory
    guid; a tie or a customer is no match) are
    ``club_teaser_link.token_for_ca_org``. Public and rate limited like the page.
    ``found: false`` for anything it cannot place, which /trial treats as "carry
    on with the ordinary choice"."""
    rate_limit.enforce(f"teaser:byclub:{client_ip(request)}", READ_LIMIT, READ_WINDOW,
                       detail="Too many requests.")
    token = await club_teaser_link.token_for_ca_org(db, id)
    return {"found": True, "token": token} if token else {"found": False}


@router.get("/{token}")
async def get_teaser(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    # The picture renderer reads this three times per club from one address and
    # proves itself with a derived key; everyone else is limited per IP.
    if not club_teaser_images.is_render_key(request.headers.get(club_teaser_images.RENDER_HEADER)):
        rate_limit.enforce(f"teaser:read:{client_ip(request)}", READ_LIMIT, READ_WINDOW,
                           detail="Too many requests.")
    row = await _row(db, token)
    snap = row["snapshot"]
    view = club_teaser.presentation(snap)
    club = snap.get("club") or {}
    # A snapshot pulled before the crest was captured has none; the directory row
    # may. Read it here so the page shows the crest without re-pulling the club.
    if not (view.get("club") or {}).get("logo_url") and row["directory_logo"]:
        view["club"] = {**(view.get("club") or {}), "logo_url": row["directory_logo"]}
    return {
        **view,
        "version": row["version"],
        # The full leaders lists (the page shows five of each); the record and
        # ladder are only what presentation() chose to show.
        "batting": snap.get("batting") or [],
        "bowling": snap.get("bowling") or [],
        "fielding": snap.get("fielding") or [],
        "records": snap.get("records") or [],
        "claim": {"ca_org_id": club.get("ca_org_id"), "name": club.get("name")},
        # The club's look, read from its logo (accent colour and light or dark);
        # None when it has no readable logo and the page keeps BetterCricket's.
        "theme": _public_theme(row["theme"]),
        # A club that is already on BetterCricket is sent to its own site
        # rather than to a trial it cannot start.
        "registered": {"slug": row["registered_slug"]} if row["registered_slug"] else None,
    }


@router.get("/{token}/image/{fmt}.png")
async def get_teaser_image(token: str, fmt: str, db: AsyncSession = Depends(get_db)):
    """The drawn picture. No rate limit: mail clients and image proxies fetch it
    from shared addresses in bursts, and a send fans out to thousands of opens.
    It is a file read and one indexed lookup. The file is only served for a
    snapshot that is still good, so a club that turned out unsuitable stops
    being shown. The address changes with ``?v=`` on every re-draw, so it can be
    cached hard."""
    if not TOKEN_RE.match(token or "") or not club_teaser_images.valid_format(fmt):
        raise HTTPException(status_code=404, detail="Not found")
    ok = await db.scalar(text(
        "SELECT 1 FROM club_teaser_snapshots WHERE token = :t AND status = 'ok' "
        "AND snapshot IS NOT NULL AND image_version IS NOT NULL"), {"t": token})
    path = club_teaser_images.image_path(token, fmt)
    if not ok or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400",
                                 "X-Robots-Tag": "noindex"})


class TeaserEvent(BaseModel):
    kind: str
    section: Optional[str] = None
    visitor_id: Optional[str] = None


@router.post("/{token}/event")
async def teaser_event(token: str, body: TeaserEvent, request: Request,
                       db: AsyncSession = Depends(get_db)):
    key = (body.visitor_id or "").strip()[:64] or client_ip(request)
    rate_limit.enforce(f"teaser:event:{key}", EVENT_LIMIT, EVENT_WINDOW, detail="Too many requests.")
    kind = (body.kind or "").strip()
    if kind not in EVENT_KINDS:
        raise HTTPException(status_code=422, detail="Unknown event")
    row = await _row(db, token)
    meta = {"marketing_club_id": str(row["club_id"]), "version": row["version"]}
    section = (body.section or "").strip()[:40]
    if section:
        meta["section"] = section
    record_event_bg(
        event_type="teaser", method="POST", path="/public/teaser/event", route=kind, status=200,
        ip=client_ip(request), user_agent=request.headers.get("user-agent"),
        visitor_id=(body.visitor_id or "").strip()[:64] or None, metadata=meta,
    )
    return {"ok": True}
