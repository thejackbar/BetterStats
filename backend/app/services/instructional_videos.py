"""
The instructional video library shown at /videos (migration 280).

Raw SQL throughout, the same posture services/directory.py keeps: the table is
created by services/instructional_video_ddl.py rather than by `create_all`, so
keeping it out of the ORM graph means nothing here depends on model import
order.

RULES WORTH KEEPING:

  - THE VIDEO IS A FILE, THE POSTER IS A COLUMN. See instructional_video_ddl
    for why the two are split. Video files are deliberately excluded from the
    regular backup (settings.py says why), so this module must never be the
    only thing that knows a file exists — the row is the index, and a row
    whose file has gone reports that rather than pretending.

  - A FILENAME IS NEVER BUILT FROM ANYTHING A PERSON TYPED. It is
    `<row uuid>.<ext>` with the extension chosen from a fixed map, so a file
    called `../../etc/passwd` cannot escape the storage directory. The name
    the admin uploaded is kept in a column, for the download header only.

  - A slug is derived from the title once, at creation, and then left alone.
    Retitling a video does NOT move its URL: a link handed to a club in an
    email has to keep working after somebody fixes a typo in the heading.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Fields every read selects. Deliberately excludes poster_data, so listing the
# library costs rows of text rather than every thumbnail.
_META_COLUMNS = """
    id, slug, title, description, module_label, sort_order,
    video_path, video_mime, video_size, video_filename,
    (poster_data IS NOT NULL) AS has_poster,
    created_at, updated_at
"""

MAX_VIDEO_BYTES = 512 * 1024 * 1024   # 512MB — a long 1080p screen recording
MAX_POSTER_BYTES = 8 * 1024 * 1024

# Only formats a browser plays from a single <video src>. An admin uploading a
# .mov gets told so rather than publishing a video half their club cannot play.
ALLOWED_VIDEO_MIMES = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}
ALLOWED_POSTER_MIMES = {"image/jpeg", "image/png", "image/webp"}

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")
# A stored filename must look exactly like one we wrote. Anything else is not
# ours and is refused rather than opened.
_SAFE_FILENAME = re.compile(r"^[0-9a-f-]{36}\.(mp4|webm)$")


def storage_dir() -> Path:
    """The directory video files live in, created on first use."""
    p = Path(settings.video_storage_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def resolve_path(video_path: str | None) -> Path | None:
    """Turn a stored filename into a full path, refusing anything that is not
    one of ours.

    The regex is the guard, not the directory check: only a name this module
    generated can pass, so a row edited by hand to say `../../secret` resolves
    to nothing instead of escaping the storage directory.
    """
    if not video_path or not _SAFE_FILENAME.match(video_path):
        return None
    return storage_dir() / video_path


def file_size(video_path: str | None) -> int:
    """Size on disk, or 0 when the file is missing.

    A missing file is an ordinary state here: these are not backed up, so a
    restored database legitimately has rows whose files are gone.
    """
    p = resolve_path(video_path)
    try:
        return p.stat().st_size if p and p.exists() else 0
    except OSError:
        return 0


def store_upload(fileobj, mime: str, *, video_id: uuid.UUID) -> tuple[str, int]:
    """Stream an upload to disk and return (filename, bytes written).

    Written to a temp file in the SAME directory and then renamed, so a partly
    written file is never visible to a reader — rename within one filesystem is
    atomic. Streamed in chunks rather than read whole, or a 512MB upload would
    sit in memory first.
    """
    directory = storage_dir()
    name = f"{video_id}{ALLOWED_VIDEO_MIMES.get(mime, '.mp4')}"
    final = directory / name

    fd, tmp_name = tempfile.mkstemp(dir=str(directory), suffix=".part")
    written = 0
    try:
        with os.fdopen(fd, "wb") as out:
            shutil.copyfileobj(fileobj, out, length=1024 * 1024)
            written = out.tell()
        # mkstemp creates 0600 by design and os.replace keeps the mode, which
        # would leave every video readable by root alone. These are public
        # marketing files with nothing to protect, and 0600 breaks two real
        # things: the host user cannot copy their own videos back off without
        # sudo (they are deliberately outside the backup, so that matters), and
        # nginx workers could not read them if the X-Accel hand-off is ever
        # switched on.
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, final)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return name, written


def delete_file(video_path: str | None) -> None:
    """Best-effort removal. A file already gone is the desired end state, and a
    filesystem error must never stop the row being deleted — an orphaned file
    is recoverable, a row pointing at nothing is what the reader sees."""
    p = resolve_path(video_path)
    if not p:
        return
    try:
        p.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove video file %s", p, exc_info=True)


def slugify(value: str) -> str:
    """Turn a title into a URL segment. Falls back to 'video' so an all-symbol
    title still produces something addressable rather than an empty path."""
    out = _SLUG_STRIP.sub("-", (value or "").strip().lower()).strip("-")
    return out[:80] or "video"


async def _unique_slug(db: AsyncSession, base: str) -> str:
    """Resolve a slug collision by suffixing rather than refusing the upload.

    Two videos legitimately share a title often enough (a re-record of the same
    walkthrough), and failing the upload over it would be a worse answer than
    `merge-players-2`.
    """
    taken = set(
        (await db.execute(
            text("SELECT slug FROM instructional_videos WHERE slug = :b OR slug LIKE :p"),
            {"b": base, "p": f"{base}-%"},
        )).scalars().all()
    )
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def _row_to_dict(row: Any) -> dict:
    d = dict(row._mapping)
    d["id"] = str(d["id"])
    stored = d.pop("video_path", None)
    # `file_present` is what lets a screen tell "not uploaded yet" from "the
    # file is gone", which matters precisely because these are not backed up.
    d["file_present"] = bool(stored) and file_size(stored) > 0
    d["src"] = f"/api/public/videos/{d['slug']}/file"
    d["poster"] = f"/api/public/videos/{d['slug']}/poster" if d.pop("has_poster") else None
    d["date"] = d["created_at"].date().isoformat() if d.get("created_at") else None
    for k in ("created_at", "updated_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


async def list_videos(db: AsyncSession) -> list[dict]:
    """Every video in display order. Used by the public page, the admin
    manager, the sitemap and the share-card builder, so there is one definition
    of what order the library is in."""
    rows = (await db.execute(text(
        f"SELECT {_META_COLUMNS} FROM instructional_videos ORDER BY sort_order, created_at"
    ))).all()
    return [_row_to_dict(r) for r in rows]


async def get_video(db: AsyncSession, slug: str) -> dict | None:
    row = (await db.execute(
        text(f"SELECT {_META_COLUMNS} FROM instructional_videos WHERE slug = :s"),
        {"s": slug},
    )).first()
    return _row_to_dict(row) if row else None


async def get_video_by_id(db: AsyncSession, video_id: str) -> dict | None:
    try:
        vid = uuid.UUID(str(video_id))
    except (ValueError, AttributeError, TypeError):
        return None
    row = (await db.execute(
        text(f"SELECT {_META_COLUMNS} FROM instructional_videos WHERE id = :i"),
        {"i": vid},
    )).first()
    return _row_to_dict(row) if row else None


async def video_file(db: AsyncSession, slug: str) -> tuple[Path, str, int, str] | None:
    """(path, mime, size, download filename) for a video whose file is present."""
    row = (await db.execute(text(
        "SELECT video_path, video_mime, video_filename, slug "
        "FROM instructional_videos WHERE slug = :s"
    ), {"s": slug})).first()
    if not row:
        return None
    path = resolve_path(row.video_path)
    if not path or not path.exists():
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    return (path, row.video_mime or "application/octet-stream", size,
            row.video_filename or row.slug)


async def poster_bytes(db: AsyncSession, slug: str) -> tuple[bytes, str] | None:
    row = (await db.execute(text(
        "SELECT poster_data, poster_mime FROM instructional_videos WHERE slug = :s"
    ), {"s": slug})).first()
    if not row or row.poster_data is None:
        return None
    return bytes(row.poster_data), (row.poster_mime or "image/jpeg")


async def create_video(
    db: AsyncSession,
    *,
    title: str,
    description: str,
    module_label: str | None,
    video_stream,
    video_mime: str,
    video_filename: str | None,
    poster_bytes_data: bytes | None,
    poster_mime: str | None,
    created_by_user_id: Any | None,
) -> dict:
    """Add a video to the end of the library.

    The id is generated here rather than left to the column default: it names
    the file on disk, so it has to exist before the file is written. It also
    sidesteps the trap where a table built by `create_all` carries no
    gen_random_uuid() default and the insert fails on a NOT NULL id.
    """
    slug = await _unique_slug(db, slugify(title))
    next_order = (await db.execute(
        text("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM instructional_videos")
    )).scalar_one()

    new_id = uuid.uuid4()
    stored_name, size = store_upload(video_stream, video_mime, video_id=new_id)

    try:
        await db.execute(text("""
            INSERT INTO instructional_videos (
                id, slug, title, description, module_label, sort_order,
                video_path, video_mime, video_size, video_filename,
                poster_data, poster_mime, created_by_user_id
            ) VALUES (
                :id, :slug, :title, :description, :module_label, :sort_order,
                :video_path, :video_mime, :video_size, :video_filename,
                :poster_data, :poster_mime, :created_by
            )
        """), {
            "id": new_id,
            "slug": slug,
            "title": title.strip(),
            "description": (description or "").strip(),
            "module_label": (module_label or "").strip() or None,
            "sort_order": next_order,
            "video_path": stored_name,
            "video_mime": video_mime,
            "video_size": size,
            "video_filename": (video_filename or stored_name)[:300],
            "poster_data": poster_bytes_data,
            "poster_mime": poster_mime,
            "created_by": created_by_user_id,
        })
        await db.commit()
    except BaseException:
        # The row is what makes the file reachable, so a failed insert must not
        # leave the file behind — nothing would ever point at it or clean it up.
        delete_file(stored_name)
        raise
    return await get_video_by_id(db, str(new_id))


async def update_video(
    db: AsyncSession,
    video_id: str,
    *,
    fields: dict,
    video_stream=None,
    video_mime: str | None = None,
    video_filename: str | None = None,
    poster_bytes_data: bytes | None = None,
    poster_mime: str | None = None,
) -> dict | None:
    """Update whatever was actually sent.

    Only a field PRESENT in `fields` is written, so the title form cannot blank
    a description it never loaded, and replacing the file cannot reset the
    text. The slug is deliberately not recomputed from a new title — see the
    module docstring.
    """
    current = await get_video_by_id(db, video_id)
    if not current:
        return None

    old_row = (await db.execute(
        text("SELECT video_path FROM instructional_videos WHERE id = :i"),
        {"i": uuid.UUID(str(video_id))},
    )).first()
    old_path = old_row.video_path if old_row else None

    sets: list[str] = []
    params: dict[str, Any] = {"id": uuid.UUID(str(video_id))}

    for key in ("title", "description", "module_label"):
        if key in fields:
            value = fields[key]
            value = (value or "").strip() if isinstance(value, str) else value
            if key == "title" and not value:
                raise ValueError("A video needs a title.")
            if key == "module_label":
                value = value or None
            sets.append(f"{key} = :{key}")
            params[key] = value

    new_stored = None
    if video_stream is not None:
        new_stored, size = store_upload(video_stream, video_mime, video_id=uuid.UUID(str(video_id)))
        sets += ["video_path = :video_path", "video_mime = :video_mime",
                 "video_size = :video_size", "video_filename = :video_filename"]
        params["video_path"] = new_stored
        params["video_mime"] = video_mime
        params["video_size"] = size
        params["video_filename"] = (video_filename or new_stored)[:300]

    if poster_bytes_data is not None:
        sets += ["poster_data = :poster_data", "poster_mime = :poster_mime"]
        params["poster_data"] = poster_bytes_data
        params["poster_mime"] = poster_mime

    if not sets:
        return current

    sets.append("updated_at = NOW()")
    try:
        await db.execute(text(
            f"UPDATE instructional_videos SET {', '.join(sets)} WHERE id = :id"
        ), params)
        await db.commit()
    except BaseException:
        if new_stored:
            delete_file(new_stored)
        raise

    # Only once the row points at the new file is the old one safe to remove,
    # and only when the name actually changed (mp4 replaced by mp4 reuses it).
    if new_stored and old_path and old_path != new_stored:
        delete_file(old_path)
    return await get_video_by_id(db, video_id)


async def delete_video(db: AsyncSession, video_id: str) -> bool:
    """Remove the entry and its file together.

    The row goes first: a row with no file shows as unavailable, whereas a file
    with no row is invisible and never cleaned up.
    """
    try:
        vid = uuid.UUID(str(video_id))
    except (ValueError, AttributeError, TypeError):
        return False
    row = (await db.execute(
        text("SELECT video_path FROM instructional_videos WHERE id = :i"), {"i": vid}
    )).first()
    if not row:
        return False
    res = await db.execute(text("DELETE FROM instructional_videos WHERE id = :i"), {"i": vid})
    await db.commit()
    if (res.rowcount or 0) > 0:
        delete_file(row.video_path)
        return True
    return False


async def reorder_videos(db: AsyncSession, ordered_ids: list[str]) -> list[dict]:
    """Stamp sort_order by POSITION over the whole library.

    The ids arrive from a browser, so an id that is not ours is skipped without
    leaving a gap in the numbering, the same rule reorder_agenda_items follows.
    Anything the caller did not mention keeps its relative order after the ones
    it did, rather than being shuffled to the front.
    """
    known = {v["id"]: v for v in await list_videos(db)}
    seen: list[str] = []
    for raw in ordered_ids or []:
        sid = str(raw)
        if sid in known and sid not in seen:
            seen.append(sid)
    for vid in known:
        if vid not in seen:
            seen.append(vid)

    for position, vid in enumerate(seen):
        await db.execute(
            text("UPDATE instructional_videos SET sort_order = :o, updated_at = NOW() WHERE id = :i"),
            {"o": position, "i": uuid.UUID(vid)},
        )
    await db.commit()
    return await list_videos(db)


async def orphaned_files(db: AsyncSession) -> list[str]:
    """Files on disk that no row points at.

    Worth being able to ask, because these are outside the backup: after a
    database restore the rows are older than the directory, and this names what
    is taking up space with nothing referring to it.
    """
    referenced = set(
        (await db.execute(
            text("SELECT video_path FROM instructional_videos WHERE video_path IS NOT NULL")
        )).scalars().all()
    )
    try:
        on_disk = {p.name for p in storage_dir().iterdir() if p.is_file()}
    except OSError:
        return []
    return sorted(n for n in on_disk - referenced if _SAFE_FILENAME.match(n))
