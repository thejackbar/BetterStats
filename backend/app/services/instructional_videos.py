"""
The instructional video library shown at /videos (migration 280).

Raw SQL throughout, the same posture services/directory.py keeps: the table is
created by services/instructional_video_ddl.py rather than by `create_all`, so
keeping it out of the ORM graph means nothing here depends on model import
order.

TWO RULES WORTH KEEPING:

  - `video_data` is never selected unless the caller is actually serving bytes.
    Every listing and detail read names its columns, so a page of six videos
    costs six rows of text and not half a gigabyte of blob. `stream_range`
    slices the column in SQL, so serving a seek costs the slice and not the
    file.

  - A slug is derived from the title once, at creation, and then left alone.
    Retitling a video does NOT move its URL: a link handed to a club in an
    email has to keep working after somebody fixes a typo in the heading.
"""
from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Fields every read that is not serving bytes selects. Deliberately excludes
# video_data and poster_data.
_META_COLUMNS = """
    id, slug, title, description, module_label, sort_order,
    video_mime, video_size, video_filename,
    (poster_data IS NOT NULL) AS has_poster,
    (video_data IS NOT NULL) AS has_video,
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
    # The public shape the frontend reads. Paths, not blobs — the browser
    # fetches the bytes from the streaming endpoints on demand.
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


async def create_video(
    db: AsyncSession,
    *,
    title: str,
    description: str,
    module_label: str | None,
    video_bytes: bytes,
    video_mime: str,
    video_filename: str | None,
    poster_bytes: bytes | None,
    poster_mime: str | None,
    created_by_user_id: Any | None,
) -> dict:
    """Add a video to the end of the library.

    The id is generated here rather than left to the column default: a table
    built by `create_all` instead of the DDL module would carry no
    gen_random_uuid() default, and the insert would fail on a NOT NULL id. The
    same trap the self-serve-trial note documents.
    """
    slug = await _unique_slug(db, slugify(title))
    next_order = (await db.execute(
        text("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM instructional_videos")
    )).scalar_one()

    new_id = uuid.uuid4()
    await db.execute(text("""
        INSERT INTO instructional_videos (
            id, slug, title, description, module_label, sort_order,
            video_data, video_mime, video_size, video_filename,
            poster_data, poster_mime, created_by_user_id
        ) VALUES (
            :id, :slug, :title, :description, :module_label, :sort_order,
            :video_data, :video_mime, :video_size, :video_filename,
            :poster_data, :poster_mime, :created_by
        )
    """), {
        "id": new_id,
        "slug": slug,
        "title": title.strip(),
        "description": (description or "").strip(),
        "module_label": (module_label or "").strip() or None,
        "sort_order": next_order,
        "video_data": video_bytes,
        "video_mime": video_mime,
        "video_size": len(video_bytes),
        "video_filename": (video_filename or f"{slug}{ALLOWED_VIDEO_MIMES.get(video_mime, '')}")[:300],
        "poster_data": poster_bytes,
        "poster_mime": poster_mime,
        "created_by": created_by_user_id,
    })
    await db.commit()
    return await get_video_by_id(db, str(new_id))


async def update_video(
    db: AsyncSession,
    video_id: str,
    *,
    fields: dict,
    video_bytes: bytes | None = None,
    video_mime: str | None = None,
    video_filename: str | None = None,
    poster_bytes: bytes | None = None,
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

    sets: list[str] = []
    params: dict[str, Any] = {"id": uuid.UUID(str(video_id))}

    for key, column in (("title", "title"), ("description", "description"), ("module_label", "module_label")):
        if key in fields:
            value = fields[key]
            value = (value or "").strip() if isinstance(value, str) else value
            if key == "title" and not value:
                raise ValueError("A video needs a title.")
            if key == "module_label":
                value = value or None
            sets.append(f"{column} = :{key}")
            params[key] = value

    if video_bytes is not None:
        sets += ["video_data = :video_data", "video_mime = :video_mime",
                 "video_size = :video_size", "video_filename = :video_filename"]
        params["video_data"] = video_bytes
        params["video_mime"] = video_mime
        params["video_size"] = len(video_bytes)
        params["video_filename"] = (video_filename or current["slug"])[:300]

    if poster_bytes is not None:
        sets += ["poster_data = :poster_data", "poster_mime = :poster_mime"]
        params["poster_data"] = poster_bytes
        params["poster_mime"] = poster_mime

    if not sets:
        return current

    sets.append("updated_at = NOW()")
    await db.execute(text(
        f"UPDATE instructional_videos SET {', '.join(sets)} WHERE id = :id"
    ), params)
    await db.commit()
    return await get_video_by_id(db, video_id)


async def delete_video(db: AsyncSession, video_id: str) -> bool:
    """Remove the entry and its file together.

    The bytes live in the row, so there is no orphaned file left on a volume
    afterwards — deleting the entry IS deleting the video.
    """
    try:
        vid = uuid.UUID(str(video_id))
    except (ValueError, AttributeError, TypeError):
        return False
    res = await db.execute(text("DELETE FROM instructional_videos WHERE id = :i"), {"i": vid})
    await db.commit()
    return (res.rowcount or 0) > 0


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


async def video_blob_info(db: AsyncSession, slug: str, *, poster: bool = False) -> tuple[str, int, str] | None:
    """(mime, byte length, filename) without pulling the blob itself.

    octet_length() reads the stored length rather than the column, so asking
    "how big is this" costs nothing even for a 400MB video.
    """
    column = "poster_data" if poster else "video_data"
    row = (await db.execute(text(f"""
        SELECT COALESCE({'poster_mime' if poster else 'video_mime'}, '') AS mime,
               COALESCE(octet_length({column}), 0) AS len,
               COALESCE(video_filename, slug) AS filename
        FROM instructional_videos WHERE slug = :s
    """), {"s": slug})).first()
    if not row or not row.len:
        return None
    return (row.mime or "application/octet-stream", int(row.len), row.filename)


async def read_blob_range(
    db: AsyncSession, slug: str, start: int, length: int, *, poster: bool = False
) -> bytes | None:
    """Slice the stored file in SQL.

    This is what makes seeking in a long video cheap: the browser asks for a
    range, and Postgres returns that range. Loading the whole column to hand
    back a two-megabyte slice would put the entire file through memory on every
    scrub. substring() is 1-indexed, hence the +1.
    """
    column = "poster_data" if poster else "video_data"
    row = (await db.execute(text(
        f"SELECT substring({column} FROM :start FOR :len) AS chunk "
        f"FROM instructional_videos WHERE slug = :s"
    ), {"s": slug, "start": start + 1, "len": length})).first()
    return bytes(row.chunk) if row and row.chunk is not None else None
