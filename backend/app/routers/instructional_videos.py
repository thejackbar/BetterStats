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

import os
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import User, get_db
from app.routers.auth import require_super_admin
from app.services import instructional_videos as svc

public_router = APIRouter(prefix="/public/videos", tags=["videos"])
admin_router = APIRouter(prefix="/club-admin/super/videos", tags=["videos-admin"])

# A range request is served in slices when the app is doing the serving. In
# production it is not: nginx does, via X-Accel-Redirect, which handles Range
# and caching natively and never puts the file through Python. This path is the
# local-dev fallback, where there is no nginx in front.
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


def _read_slice(path, start: int, length: int) -> bytes:
    with open(path, "rb") as fh:
        fh.seek(start)
        return fh.read(length)


# GET *and* HEAD. FastAPI, unlike plain Starlette, does not add HEAD to a GET
# route, so this 405'd on a HEAD — and a public file endpoint gets plenty of
# them: players and download managers probe for Content-Length and
# Accept-Ranges before they start streaming, and uptime checks use HEAD by
# default.
@public_router.api_route("/{slug}/file", methods=["GET", "HEAD"])
async def stream_video(
    slug: str, request: Request, download: int = 0, db: AsyncSession = Depends(get_db)
):
    """Serve the video, honouring Range so the player can seek.

    ``?download=1`` is what the Download button uses: same bytes, served with a
    Content-Disposition so the browser saves the file rather than playing it.

    A MISSING FILE IS AN ORDINARY STATE HERE, not an error to be surprised by:
    video files are deliberately outside the regular backup, so a database
    restored onto a fresh box has rows whose files are legitimately gone. It
    reports 404 with a plain reason, and the page draws its "not playing" note.
    """
    found = await svc.video_file(db, slug)
    if not found:
        exists = await svc.get_video(db, slug)
        raise HTTPException(
            status_code=404,
            detail=("That video's file is not on this server." if exists else "No such video"),
        )
    path, mime, size, filename = found

    disposition = None
    if download:
        safe = (filename or slug).replace('"', "")
        disposition = f'attachment; filename="{safe}"'

    # A HEAD asks what this file IS, so it answers with the whole file's size
    # and nothing else — never a range, and never a body.
    if request.method == "HEAD":
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(size),
            "Cache-Control": "public, max-age=3600",
        }
        if disposition:
            headers["Content-Disposition"] = disposition
        return Response(status_code=200, media_type=mime, headers=headers)

    # Production: hand the bytes to nginx. The access check has already run;
    # nginx serves from disk with native Range support and never blocks a
    # worker on a 400MB read.
    accel = (settings.video_accel_location or "").strip()
    if accel:
        headers = {
            "X-Accel-Redirect": f"{accel.rstrip('/')}/{path.name}",
            "Content-Type": mime,
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
        }
        if disposition:
            headers["Content-Disposition"] = disposition
        return Response(status_code=200, headers=headers)

    # Serve it ourselves. This is the default path — see settings for why the
    # nginx hand-off is opt-in rather than assumed.
    base_headers = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"}
    if disposition:
        base_headers["Content-Disposition"] = disposition

    rng = _parse_range(request.headers.get("range"), size)

    if rng is None:
        # No range asked for. FileResponse streams the file off disk in chunks,
        # so a 96MB download is a complete file without ever being a 96MB
        # string in memory. Serving a truncated first chunk here instead would
        # hand `?download=1` a broken file.
        return FileResponse(path, media_type=mime, headers=base_headers)

    start, end = rng
    # CLAMP WHAT ONE RESPONSE CARRIES. Chrome opens a video with
    # `Range: bytes=0-`, which asks for the whole file — reading that into a
    # single Response is the entire file in memory, per viewer. A short 206 is
    # legal and expected: the player just asks for the next part.
    end = min(end, start + CHUNK_BYTES - 1)
    data = _read_slice(path, start, end - start + 1)
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


@public_router.api_route("/{slug}/poster", methods=["GET", "HEAD"])
async def stream_poster(slug: str, db: AsyncSession = Depends(get_db)):
    """The thumbnail, which stays in Postgres — small enough to back up, and it
    keeps a restored library recognisable when the video files are gone."""
    found = await svc.poster_bytes(db, slug)
    if not found:
        raise HTTPException(status_code=404, detail="No poster for that video")
    data, mime = found
    return Response(content=data, media_type=mime,
                    headers={"Cache-Control": "public, max-age=3600"})


# -------------------------------------------------------------- admin writes

class ReorderBody(BaseModel):
    ids: list[str]


def _check_size(file: UploadFile, cap: int, kind: str) -> int:
    """Measure an upload without reading it into memory.

    UploadFile wraps a SpooledTemporaryFile, so seeking to the end gives the
    size directly. Reading a 512MB video just to call len() on it is the thing
    this exists to avoid.
    """
    fh = file.file
    fh.seek(0, os.SEEK_END)
    size = fh.tell()
    fh.seek(0)
    if size > cap:
        raise HTTPException(
            status_code=413,
            detail=f"{kind} files are limited to {cap // (1024 * 1024)}MB. That one is "
                   f"{size // (1024 * 1024)}MB.",
        )
    return size


def _check_mime(file: UploadFile, allowed: set[str], kind: str) -> str:
    """The mime on the wire is whatever the client claims, so an unrecognised
    one is refused outright rather than stored and left to fail for every
    visitor later."""
    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"{kind} must be one of: {', '.join(sorted(allowed))}. That file says it is "
                   f"'{mime or 'unknown'}'.",
        )
    return mime


def _video_upload(file: UploadFile | None):
    """(stream, mime) for a video upload, or None when nothing was sent.

    The stream is handed to the service to copy to disk in chunks; it is never
    read into memory here.
    """
    if file is None or not file.filename:
        return None
    size = _check_size(file, svc.MAX_VIDEO_BYTES, "Video")
    if size == 0:
        return None
    return file.file, _check_mime(file, set(svc.ALLOWED_VIDEO_MIMES), "Video")


async def _poster_upload(file: UploadFile | None):
    """(bytes, mime) for a poster, or None. Small enough to hold in memory."""
    if file is None or not file.filename:
        return None
    _check_size(file, svc.MAX_POSTER_BYTES, "Poster image")
    mime = _check_mime(file, svc.ALLOWED_POSTER_MIMES, "Poster image")
    data = await file.read()
    return (data, mime) if data else None


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
    # Seconds. The browser measures it off the uploaded file and lets the admin
    # correct it, so nothing here has to parse "2m 45s".
    duration_seconds: str = Form(""),
    video: UploadFile = File(...),
    poster: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_super_admin),
):
    if not title.strip():
        raise HTTPException(status_code=422, detail="A video needs a title.")
    read_video = _video_upload(video)
    if not read_video:
        raise HTTPException(status_code=422, detail="Choose a video file to upload.")
    stream, video_mime = read_video
    read_poster = await _poster_upload(poster)

    return await svc.create_video(
        db,
        title=title,
        description=description,
        module_label=module_label,
        video_stream=stream,
        video_mime=video_mime,
        video_filename=video.filename,
        duration_seconds=duration_seconds,
        poster_bytes_data=read_poster[0] if read_poster else None,
        poster_mime=read_poster[1] if read_poster else None,
        created_by_user_id=user.id,
    )


@admin_router.patch("/{video_id}")
async def admin_update_video(
    video_id: str,
    title: str | None = Form(None),
    description: str | None = Form(None),
    module_label: str | None = Form(None),
    duration_seconds: str | None = Form(None),
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
    if duration_seconds is not None:
        fields["duration_seconds"] = duration_seconds

    read_video = _video_upload(video)
    read_poster = await _poster_upload(poster)

    try:
        updated = await svc.update_video(
            db, video_id,
            fields=fields,
            video_stream=read_video[0] if read_video else None,
            video_mime=read_video[1] if read_video else None,
            video_filename=video.filename if video else None,
            poster_bytes_data=read_poster[0] if read_poster else None,
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
