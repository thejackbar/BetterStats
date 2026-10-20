"""The pictures behind a club's teaser link: render, store, find, and the two
email merge variables that point at them.

A snapshot is JSON; an email and an ad need a picture. The picture is NOT
drawn here. It is a screenshot of the real card page (``/preview/{token}/card/
{format}`` in the frontend), taken by headless Chromium, so the email image and
the page it links to can never look like two different products and the design
lives in one place.

Where the files live: ``settings.teaser_image_dir/<token>/<format>.png``, on the
media volume and OUTSIDE the regular backup, like the instructional videos. Any
file can be re-made from its snapshot, so backing them up buys nothing.

When a picture is due: ``club_teaser_snapshots.image_version`` is the snapshot
``version`` the files were drawn from. A snapshot whose ``version`` has moved on
is due again, and until it is re-drawn the old files keep being served (a
slightly old card beats a broken image in an email already sent). A club that
has registered is left alone.

Rules this module keeps:

* Formats are an allowlist. A token and a format name are the only things that
  reach a path, and both are validated, so nothing here can be walked out of the
  directory.
* A file is written to a temporary name and renamed into place, so a request
  never reads half a picture.
* ``image_version`` is only set after EVERY format for the club has been
  written, and only to the version that was drawn, so a snapshot that changed
  mid-render stays due.
* One failing club never stops the batch, and a batch is bounded by ``limit``.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from pathlib import Path
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings

logger = logging.getLogger(__name__)

# The pictures drawn for every club. ``names`` is whether the card may print a
# player's name. The email card and the share preview go to the club's own
# people, who know who the top run-scorer is. An ad is shown to the public, and
# putting a named individual into paid creative is a decision for the club, so
# the two ad sizes leave the name off.
FORMATS = {
    "card": {"width": 1200, "height": 630, "names": True,
             "use": "email image and link preview"},
    "feed": {"width": 1080, "height": 1350, "names": False,
             "use": "Facebook and Instagram feed ad"},
    "story": {"width": 1080, "height": 1920, "names": False,
              "use": "Story and Reel ad"},
}
EMAIL_FORMAT = "card"

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
RENDER_TIMEOUT_MS = 30_000
# Never render more than this many clubs in one run, whatever the caller asks.
MAX_BATCH = 500


def valid_format(fmt: str) -> bool:
    return fmt in FORMATS


def image_root() -> Path:
    return Path(settings.teaser_image_dir)


def image_path(token: str, fmt: str) -> Path:
    """Where one club's picture lives. Raises ValueError for anything that is
    not a real token and a known format, so a path can never be built from
    request input that was not checked."""
    if not TOKEN_RE.match(token or "") or not valid_format(fmt):
        raise ValueError("not a teaser image")
    return image_root() / token / f"{fmt}.png"


def render_base_url() -> str:
    return (settings.teaser_render_base_url or settings.public_base_url).rstrip("/")


def card_url(token: str, fmt: str, *, base: Optional[str] = None) -> str:
    """The page the screenshot is taken of."""
    return f"{(base or render_base_url()).rstrip('/')}/preview/{token}/card/{fmt}"


def public_image_url(token: str, image_version: Optional[int], fmt: str = EMAIL_FORMAT) -> str:
    """The address an email or a share card embeds. ``v`` changes with every
    re-draw so a mail client or a CDN that cached the old picture fetches the
    new one."""
    v = f"?v={image_version}" if image_version is not None else ""
    return f"{settings.public_base_url.rstrip('/')}/api/public/teaser/{token}/image/{fmt}.png{v}"


def public_page_url(token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/preview/{token}"


# ── Merge variables ────────────────────────────────────────────────────────

# The two variables an email can use. Computed facts about a club's snapshot, so
# deliberately NOT in comms.EDITABLE_MERGE_KEYS: a hand-typed token would point
# the email at another club's page.
TEASER_VAR_KEYS = ("teaser_url", "teaser_image_url")
BLANK_TEASER_VARS = {"teaser_url": "", "teaser_image_url": ""}


async def vars_by_marketing_club(session: AsyncSession, clubs: Iterable) -> dict:
    """``{marketing_club.id: {teaser_url, teaser_image_url}}`` for each club, in
    one query. Every club gets an entry, so a template never goes out with a raw
    ``{{teaser_url}}`` in it.

    ``teaser_url`` is set for any club with a good (``ok``) snapshot.
    ``teaser_image_url`` is set only once a picture has been drawn AND its file
    is on disk: an image link to a file that does not exist is a broken box in
    the middle of an email. A club with no good snapshot gets both blank, which is what the
    "Club has a teaser snapshot" audience rule is for.
    """
    ids = [str(c.id) for c in clubs if c is not None and getattr(c, "id", None)]
    out = {c.id: dict(BLANK_TEASER_VARS) for c in clubs if c is not None and getattr(c, "id", None)}
    if not ids:
        return out
    rows = (await session.execute(text("""
        SELECT marketing_club_id, token, image_version FROM club_teaser_snapshots
        WHERE marketing_club_id = ANY(CAST(:ids AS uuid[]))
          AND status = 'ok' AND snapshot IS NOT NULL
    """), {"ids": ids})).mappings().all()
    for r in rows:
        out[r["marketing_club_id"]] = {
            "teaser_url": public_page_url(r["token"]),
            # image_version says it was drawn; the file says it is still there.
            # A recreated container with no volume mounted, or a restore onto a
            # fresh box, leaves the first without the second, and an email must
            # not go out with a link to a picture the server cannot serve.
            "teaser_image_url": (public_image_url(r["token"], r["image_version"])
                                 if r["image_version"] is not None
                                 and image_path(r["token"], EMAIL_FORMAT).is_file() else ""),
        }
    return out


async def vars_for_marketing_club(session: AsyncSession, club) -> dict:
    if club is None:
        return dict(BLANK_TEASER_VARS)
    return (await vars_by_marketing_club(session, [club])).get(club.id, dict(BLANK_TEASER_VARS))


# ── What is due ────────────────────────────────────────────────────────────

_DUE_SQL = """
    FROM club_teaser_snapshots t
    JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
    WHERE t.status = 'ok' AND t.snapshot IS NOT NULL
      AND mc.existing_org_id IS NULL
      AND t.image_version IS DISTINCT FROM t.version
"""


async def images_progress(session: AsyncSession) -> dict:
    """What the panel shows: pictures drawn and pictures waiting. Counts only
    clubs that are not customers yet, like the render itself."""
    row = (await session.execute(text("""
        SELECT count(*) FILTER (WHERE t.image_version IS NOT DISTINCT FROM t.version) AS ready,
               count(*) FILTER (WHERE t.image_version IS DISTINCT FROM t.version) AS pending,
               count(*) FILTER (WHERE t.image_version IS NOT NULL
                                AND t.image_version <> t.version) AS stale
        FROM club_teaser_snapshots t
        JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
        WHERE t.status = 'ok' AND t.snapshot IS NOT NULL AND mc.existing_org_id IS NULL
    """))).mappings().first()
    return {"ready": row["ready"], "pending": row["pending"], "stale": row["stale"]}


async def due_clubs(session: AsyncSession, limit: int, *, club_id: Optional[str] = None,
                    force: bool = False, missing_files: bool = False) -> list:
    """The clubs to draw now: never drawn first, then the longest out of date.
    ``force`` redraws clubs that are up to date (a design change).
    ``missing_files`` is for a restore or an unmounted volume: clubs marked as
    drawn whose card file is not on disk. Unlike ``force`` it makes progress
    across runs, because a club drawn this time no longer matches."""
    limit = max(0, min(int(limit), MAX_BATCH))
    if limit == 0:
        return []
    if missing_files:
        rows = (await session.execute(text(
            "SELECT t.id, t.token, t.version, t.image_version, mc.id AS club_id, mc.name "
            "FROM club_teaser_snapshots t JOIN marketing_clubs mc ON mc.id = t.marketing_club_id "
            "WHERE t.status = 'ok' AND t.snapshot IS NOT NULL AND mc.existing_org_id IS NULL "
            "AND t.image_version IS NOT NULL ORDER BY t.changed_at NULLS LAST"))).mappings().all()
        return [dict(r) for r in rows if not image_path(r["token"], EMAIL_FORMAT).is_file()][:limit]
    where = _DUE_SQL if not force else """
    FROM club_teaser_snapshots t
    JOIN marketing_clubs mc ON mc.id = t.marketing_club_id
    WHERE t.status = 'ok' AND t.snapshot IS NOT NULL AND mc.existing_org_id IS NULL
    """
    params: dict = {"n": limit}
    if club_id:
        where += " AND t.marketing_club_id = CAST(:cid AS uuid)"
        params["cid"] = str(club_id)
    rows = (await session.execute(text(
        "SELECT t.id, t.token, t.version, t.image_version, mc.id AS club_id, mc.name " + where +
        " ORDER BY (t.image_version IS NULL) DESC, t.changed_at NULLS LAST LIMIT :n"),
        params)).mappings().all()
    return [dict(r) for r in rows]


# ── Drawing ────────────────────────────────────────────────────────────────

def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class ChromiumRenderer:
    """One headless Chromium for a whole batch, one page per picture. Used as an
    async context manager; ``shoot(url, width, height)`` returns PNG bytes of
    the element marked ``data-card`` once it says it is ready."""

    def __init__(self, *, executable_path: Optional[str] = None):
        self._exe = executable_path if executable_path is not None else settings.teaser_chromium_path
        self._pw = None
        self._browser = None

    async def __aenter__(self):
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()
        kwargs = {"args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if self._exe:
            kwargs["executable_path"] = self._exe
        self._browser = await self._pw.chromium.launch(**kwargs)
        return self

    async def __aexit__(self, *exc):
        try:
            if self._browser:
                await self._browser.close()
        finally:
            if self._pw:
                await self._pw.stop()

    async def shoot(self, url: str, width: int, height: int) -> bytes:
        ctx = await self._browser.new_context(viewport={"width": width, "height": height},
                                              device_scale_factor=1)
        try:
            page = await ctx.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=RENDER_TIMEOUT_MS)
            await page.wait_for_selector('[data-card][data-card-ready="1"]', timeout=RENDER_TIMEOUT_MS)
            el = await page.query_selector("[data-card]")
            # A card whose content does not fit its frame would be saved with
            # the bottom cut off. Refuse it instead: the club stays unpictured
            # and is listed as failed, which is what an operator can act on.
            if await el.evaluate("e => e.scrollHeight > e.clientHeight + 1 || e.scrollWidth > e.clientWidth + 1"):
                raise RuntimeError("the card content does not fit its frame")
            return await el.screenshot(type="png")
        finally:
            await ctx.close()


async def render_club(renderer, token: str, *, base: Optional[str] = None,
                      formats: Iterable[str] = tuple(FORMATS)) -> dict:
    """Draw every format for one club and write the files. Returns
    ``{format: bytes_written}``; raises if any format fails, leaving whatever
    was already on disk for that club untouched for the formats that did not
    complete."""
    sizes = {}
    for fmt in formats:
        spec = FORMATS[fmt]
        data = await renderer.shoot(card_url(token, fmt, base=base), spec["width"], spec["height"])
        if not data or data[:8] != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(f"{fmt}: the renderer did not return a PNG")
        _write_atomic(image_path(token, fmt), data)
        sizes[fmt] = len(data)
    return sizes


# One batch at a time per process. The panel's button and the script both go
# through ``render_pending``; a second press while one runs is told so rather
# than starting a second Chromium.
_RUN_LOCK = asyncio.Lock()
RUN_STATE: dict = {"running": False, "started_at": None, "finished_at": None, "last": None}


async def render_pending(session_maker, *, limit: int = 50, club_id: Optional[str] = None,
                         force: bool = False, missing_files: bool = False, apply: bool = True, renderer_factory=None,
                         base: Optional[str] = None, on_progress=None) -> dict:
    """Draw the pictures that are due. With ``apply=False`` only reports what
    would be drawn. Never raises for one club's failure; the club is listed in
    ``failed`` and stays due."""
    if _RUN_LOCK.locked():
        return {"status": "busy"}
    async with _RUN_LOCK:
        RUN_STATE.update(running=True, started_at=time.time())
        summary = {"status": "ok", "due": 0, "drawn": 0, "failed": [], "bytes": 0}
        try:
            async with session_maker() as s:
                clubs = await due_clubs(s, limit, club_id=club_id, force=force,
                                        missing_files=missing_files)
            summary["due"] = len(clubs)
            if not apply or not clubs:
                summary["clubs"] = [{"id": str(c["club_id"]), "name": c["name"], "token": c["token"]}
                                    for c in clubs]
                return summary
            factory = renderer_factory or ChromiumRenderer
            async with factory() as renderer:
                for c in clubs:
                    try:
                        sizes = await render_club(renderer, c["token"], base=base)
                    except Exception as e:  # noqa: BLE001 - one club must not stop the batch
                        logger.warning("Teaser image failed for %s: %s", c["name"], e)
                        summary["failed"].append({"id": str(c["club_id"]), "name": c["name"],
                                                  "error": str(e)[:200]})
                        continue
                    async with session_maker() as s:
                        # Only the version that was drawn, and only if it is
                        # still the newest or older: a snapshot that moved on
                        # while this ran stays due.
                        await s.execute(text(
                            "UPDATE club_teaser_snapshots SET image_version = :v, updated_at = now() "
                            "WHERE id = :id AND version >= :v"),
                            {"v": c["version"], "id": c["id"]})
                        await s.commit()
                    summary["drawn"] += 1
                    summary["bytes"] += sum(sizes.values())
                    if on_progress:
                        on_progress(summary)
            return summary
        except Exception as e:  # noqa: BLE001 - no Chromium, no database: reported, never raised
            logger.exception("Teaser image batch failed")
            summary.update(status="error", error=str(e)[:300])
            return summary
        finally:
            RUN_STATE.update(running=False, finished_at=time.time(), last=dict(summary))
