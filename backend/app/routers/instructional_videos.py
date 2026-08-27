"""
The instructional video library: a public reader and a Super Admin manager.

Two routers in one module because they are two views of one table and the
rules about what a video IS belong in one place:

  - ``public_router`` (/public/videos) is unauthenticated. It serves the
    listing the marketing page draws and streams the files themselves.
  - ``admin_router`` (/club-admin/super/videos) is Super Admin only. This is
    cross-club platform content, not a club's own data, so it is gated by
    ``require_super_admin`` rather than a per-club capability — the same call
    routers/marketing.py makes.

THE GATE IS HERE, NOT IN THE UI. The marketing page only draws its edit
controls for a super admin, but that is presentation: every write below
re-checks on the server, because the page is public and anyone can call these.
"""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, get_db
from app.routers.auth import require_super_admin
from app.services import instructional_videos as svc

public_router = APIRouter(prefix="/public/videos", tags=["videos"])
admin_router = APIRouter(prefix="/club-admin/super/videos", tags=["videos-admin"])

# A range request is served in slices rather than whole, so a browser scrubbing
# a long video never pulls the entire file. 2MB is a comfortable chunk: big
# enough that playback is not a request per second, small enough that a seek
# costs almost nothing.
CHUNK_BYTES = 2 * 1024 * 1024
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


# --------------------------------------------------------------- public read

@public_router.get("")
async def list_public_videos(db: AsyncSession = Depends(get_db)):
    """The whole library, in display order, with no file bytes."""
    return {"videos": await svc.list_videos(db)}


@public_router.get("/{slug}")
async def get_public_video(slug: str, db: AsyncSession = Depends(get_db)):
    video = await svc.get_video(db, slug)
    if not video:
        raise HTTPException(status_code=404, detail="No such video")
    return video


def _parse_range(header: str | None, size: int) -> tuple[int, int] | None:
    """Resolve a Range header to an inclusive (start, end), or None for a whole
    file. An unsatisfiable or malformed range returns None so the caller falls
    back to serving from the start rather than erroring."""
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    raw_start, raw_end = m.group(1), m.group(2)
    if raw_start == "":
        # "bytes=-500" — the last N bytes.
        if raw_end == "":
            return None
        length = min(int(raw_end), size)
        return (max(size - length, 0), size - 1)
    start = int(raw_start)
    if start >= size:
        return None
    end = int(raw_end) if raw_end else size - 1
    return (start, min(end, size - 1))


async def _serve_blob(
    db: AsyncSession, slug: str, request: Request, *, poster: bool, download: bool = False
) -> Response:
    info = await svc.video_blob_info(db, slug, poster=poster)
    if not info:
        raise HTTPException(status_code=404, detail="No such file")
    mime, size, filename = info

    # Public content that never changes for a given slug once uploaded, so it
    # is safe to cache hard. Replacing the file bumps updated_at, which the
    # ETag carries, so a replacement is picked up rather than served stale.
    video = await svc.get_video(db, slug)
    etag = f'"{slug}-{(video or {}).get("updated_at", "")}-{size}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "public, max-age=3600"})

    base_headers = {
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Cache-Control": "public, max-age=3600",
    }
    if download:
        safe = (filename or slug).replace('"', "")
        base_headers["Content-Disposition"] = f'attachment; filename="{safe}"'

    rng = _parse_range(request.headers.get("range"), size)
    if rng is None:
        # No range asked for. A poster is small enough to hand over whole; a
        # video is not, so the first chunk is served and the browser asks for
        # the rest as it plays.
        if poster or size <= CHUNK_BYTES:
            data = await svc.read_blob_range(db, slug, 0, size, poster=poster)
            return Response(content=data or b"", media_type=mime,
                            headers={**base_headers, "Content-Length": str(size)})
        rng = (0, min(CHUNK_BYTES, size) - 1)

    start, end = rng
    length = end - start + 1
    data = await svc.read_blob_range(db, slug, start, length, poster=poster)
    if data is None:
        raise HTTPException(status_code=404, detail="No such file")
    return Response(
        content=data,
        status_code=206,
        media_type=mime,
        headers={
            **base_headers,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(len(data)),
        },
    )


@public_router.get("/{slug}/file")
async def stream_video(
    slug: str, request: Request, download: int = 0, db: AsyncSession = Depends(get_db)
):
    """Stream the video, honouring Range so the player can seek.

    ``?download=1`` is what the Download button uses: same bytes, served with a
    Content-Disposition so the browser saves the file rather than playing it.
    """
    return await _serve_blob(db, slug, request, poster=False, download=bool(download))


@public_router.get("/{slug}/poster")
async def stream_poster(slug: str, request: Request, db: AsyncSession = Depends(get_db)):
    return await _serve_blob(db, slug, request, poster=True)


# -------------------------------------------------------------- admin writes

class ReorderBody(BaseModel):
    ids: list[str]


async def _read_upload(file: UploadFile | None, *, poster: bool) -> tuple[bytes, str] | None:
    """Read an upload and refuse anything the library will not serve.

    Checked here rather than trusted from the browser: the mime on the wire is
    whatever the client claims, so an unrecognised one is rejected outright
    instead of being stored and failing to play for every visitor later.
    """
    if file is None or not file.filename:
        return None
    data = await file.read()
    if not data:
        return None

    allowed = svc.ALLOWED_POSTER_MIMES if poster else set(svc.ALLOWED_VIDEO_MIMES)
    cap = svc.MAX_POSTER_BYTES if poster else svc.MAX_VIDEO_BYTES
    kind = "Poster image" if poster else "Video"

    if len(data) > cap:
        raise HTTPException(
            status_code=413,
            detail=f"{kind} files are limited to {cap // (1024 * 1024)}MB. That one is "
                   f"{len(data) // (1024 * 1024)}MB.",
        )
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"{kind} must be one of: {', '.join(sorted(allowed))}. That file says it is "
                   f"'{mime or 'unknown'}'.",
        )
    return data, mime


@admin_router.get("")
async def admin_list_videos(
    db: AsyncSession = Depends(get_db), _: User = Depends(require_super_admin)
):
    """Same list the public page reads, so the manager and the page can never
    disagree about what the library holds or what order it is in."""
    return {"videos": await svc.list_videos(db)}


@admin_router.post("")
async def admin_create_video(
    title: str = Form(...),
    description: str = Form(""),
    module_label: str = Form(""),
    video: UploadFile = File(...),
    poster: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_super_admin),
):
    if not title.strip():
        raise HTTPException(status_code=422, detail="A video needs a title.")
    read_video = await _read_upload(video, poster=False)
    if not read_video:
        raise HTTPException(status_code=422, detail="Choose a video file to upload.")
    video_bytes, video_mime = read_video
    read_poster = await _read_upload(poster, poster=True)

    return await svc.create_video(
        db,
        title=title,
        description=description,
        module_label=module_label,
        video_bytes=video_bytes,
        video_mime=video_mime,
        video_filename=video.filename,
        poster_bytes=read_poster[0] if read_poster else None,
        poster_mime=read_poster[1] if read_poster else None,
        created_by_user_id=user.id,
    )


@admin_router.patch("/{video_id}")
async def admin_update_video(
    video_id: str,
    title: str | None = Form(None),
    description: str | None = Form(None),
    module_label: str | None = Form(None),
    video: UploadFile | None = File(None),
    poster: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Edit the text, replace the file, or both.

    A field left out of the form is left alone, so the title form cannot blank
    a description and replacing the file cannot reset the text.
    """
    fields: dict = {}
    if title is not None:
        fields["title"] = title
    if description is not None:
        fields["description"] = description
    if module_label is not None:
        fields["module_label"] = module_label

    read_video = await _read_upload(video, poster=False)
    read_poster = await _read_upload(poster, poster=True)

    try:
        updated = await svc.update_video(
            db, video_id,
            fields=fields,
            video_bytes=read_video[0] if read_video else None,
            video_mime=read_video[1] if read_video else None,
            video_filename=video.filename if video else None,
            poster_bytes=read_poster[0] if read_poster else None,
            poster_mime=read_poster[1] if read_poster else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if not updated:
        raise HTTPException(status_code=404, detail="No such video")
    return updated


@admin_router.delete("/{video_id}")
async def admin_delete_video(
    video_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    """Delete the entry and its file in one go — the bytes are the row."""
    if not await svc.delete_video(db, video_id):
        raise HTTPException(status_code=404, detail="No such video")
    return {"deleted": True}


@admin_router.post("/reorder")
async def admin_reorder_videos(
    body: ReorderBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_super_admin),
):
    return {"videos": await svc.reorder_videos(db, body.ids)}
