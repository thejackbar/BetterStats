"""Super Admin — Backups page.

Lists backup/restore tasks + current DB size stats (both written/computed
elsewhere — ``app/scripts/backup_task.py`` from the host scripts in
``ops/backup/``, ``services/backup_stats.py`` for the live size snapshot) and
exposes ONE write action: "run a backup now". That action proxies to the
``betterstats-backup-agent`` sidecar (see ops/backup/agent/) rather than
doing anything itself — this process has no Docker socket or host filesystem
access, by design, so it can't run backup.sh directly.

Restore (full or per-club) is available BOTH ways: as an SSH-run operation
(``ops/backup/restore.sh``, unchanged) and from this page. The web path is
gated by two independent things, not one:
  1. Typing a literal confirmation word back (``RESTORE_CONFIRM_WORD``
     below) — the same "type it back" friction restore.sh's own interactive
     prompt already used for an SSH operator, just moved into this request.
  2. The age PRIVATE key itself, entered fresh on every single restore
     request — never stored anywhere in this app (not in the DB, not
     logged). It's forwarded to the backup-agent, which cryptographically
     verifies it's the real matching private half of the configured public
     key before the restore is allowed to proceed (see
     ops/backup/agent/app.py's ``_write_and_verify_key``), then shreds its
     temp copy the moment the restore process exits. This process (the
     backend) never sees or holds the key any longer than the single
     request/response cycle needed to relay it onward.

Downloading a backup FILE is different from restoring one — it's offered as
a manual, on-demand option (there's no automatic offsite sync, per direct
instruction) and stays safe without the private key ever leaving the box:
every file served here is still age-ENCRYPTED exactly as it sits in
BACKUP_ROOT, so a downloaded copy is only ever as useful as the private key
someone separately holds to decrypt it.
"""
from __future__ import annotations

import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import User, get_db
from app.routers.auth import require_super_admin
from app.services import backup_stats

router = APIRouter(prefix="/club-admin/super/backups", tags=["backup-admin"])

# The word a Super Admin must type back, verbatim, before a web-triggered
# restore is even attempted — checked here, server-side, BEFORE the private
# key is ever asked for or forwarded anywhere. Deliberately not
# case-insensitive or fuzzy-matched; this is meant to be a genuine typed
# confirmation, not a checkbox.
RESTORE_CONFIRM_WORD = "RESTORE"


@router.get("")
async def list_backup_tasks(
    task_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Requested/running/completed/failed backup + restore tasks, newest
    first, with the size/row-count snapshot stamped at completion time."""
    where = []
    params: dict = {"limit": limit, "offset": offset}
    if task_type:
        where.append("t.task_type = :task_type")
        params["task_type"] = task_type
    if status:
        where.append("t.status = :status")
        params["status"] = status
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    rows = (await db.execute(text(f"""
        SELECT t.id, t.task_type, t.status, t.scope_org_id, o.name AS scope_org_name,
               t.triggered_by, t.triggered_by_user_id, t.bundle_path, t.bundle_timestamp,
               t.started_at, t.completed_at, t.db_size_bytes, t.uploads_size_bytes,
               t.total_row_count, t.club_stats, t.error_message, t.progress
        FROM backup_tasks t
        LEFT JOIN organisations o ON o.id = t.scope_org_id
        {where_clause}
        ORDER BY t.started_at DESC
        LIMIT :limit OFFSET :offset
    """), params)).mappings().all()

    total = (await db.execute(
        text(f"SELECT COUNT(*) FROM backup_tasks t {where_clause}"), params
    )).scalar() or 0

    return {
        "tasks": [
            {
                "id": str(r["id"]),
                "task_type": r["task_type"],
                "status": r["status"],
                "scope_org_id": str(r["scope_org_id"]) if r["scope_org_id"] else None,
                "scope_org_name": r["scope_org_name"],
                "triggered_by": r["triggered_by"],
                "bundle_path": r["bundle_path"],
                "bundle_timestamp": r["bundle_timestamp"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
                "db_size_bytes": r["db_size_bytes"],
                "uploads_size_bytes": r["uploads_size_bytes"],
                "total_row_count": r["total_row_count"],
                "club_stats": r["club_stats"],
                "error_message": r["error_message"],
                "progress": r["progress"],
            }
            for r in rows
        ],
        "total": total,
    }


@router.get("/stats")
async def live_db_stats(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Current (live, computed on request) total DB size and a per-club
    breakdown — not tied to any particular backup bundle. Per-club size is an
    estimate (see backup_stats module docstring); row counts are exact."""
    return await backup_stats.compute_db_stats(db)


@router.post("/run")
async def run_backup_now(
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Kicks off an immediate backup via the backup-agent sidecar. Fire-and-
    forget: the agent starts backup.sh in the background and returns right
    away — poll the task list (GET /club-admin/super/backups) for progress,
    same as a scheduled run. 503s with a clear message if the agent isn't
    configured/reachable rather than hanging on a request that can take
    minutes."""
    if not settings.backup_agent_url:
        raise HTTPException(
            status_code=503,
            detail="The backup agent isn't configured on this server yet "
                   "(BACKUP_AGENT_URL unset) — see docs/backup-system.md. "
                   "Run a backup manually on the server in the meantime: "
                   "ops/backup/backup.sh",
        )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.backup_agent_url.rstrip('/')}/run-backup",
                headers={"X-Agent-Secret": settings.backup_agent_secret},
                json={"triggered_by_user_id": str(user.id)},
            )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Backup agent returned {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach the backup agent: {e}")


# Mirrors ops/backup/agent/app.py's _DOWNLOADABLE_FILES — only db/uploads are
# actually age-encrypted; manifest/checksums are plain, so the download
# filename shouldn't claim a `.age` suffix that isn't there.
_DOWNLOADABLE_FILES = {
    "db": "db.dump.age",
    "uploads": "uploads.tar.zst.age",
    "manifest": "manifest.json",
    "checksums": "checksums.sha256",
}
_BUNDLE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$")


async def _resolve_bundle(db: AsyncSession, task_id: str) -> str:
    """Looks up a completed backup task's bundle directory name (e.g.
    "2026-07-22T13-49-02Z"), validated against the fixed timestamp shape
    backup.sh always produces. Shared by download/restore-full/restore-club
    so there's one place that decides "is this task a real, restorable
    backup" rather than three slightly different checks."""
    row = (await db.execute(
        text("SELECT bundle_path, task_type, status FROM backup_tasks WHERE id = :id"),
        {"id": task_id},
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No such backup task")
    bundle_path, task_type, task_status = row
    if task_type != "backup" or task_status != "completed" or not bundle_path:
        raise HTTPException(status_code=400, detail="Only a completed backup task can be used here")
    bundle = bundle_path.rstrip("/").rsplit("/", 1)[-1]
    if not _BUNDLE_RE.match(bundle):
        raise HTTPException(status_code=500, detail="Unexpected bundle path recorded for this task")
    return bundle


def _require_agent_configured():
    if not settings.backup_agent_url:
        raise HTTPException(
            status_code=503,
            detail="The backup agent isn't configured on this server yet "
                   "(BACKUP_AGENT_URL unset) — see docs/backup-system.md.",
        )


def _require_confirm_word(confirm_word: str):
    if confirm_word != RESTORE_CONFIRM_WORD:
        raise HTTPException(
            status_code=400,
            detail=f'Confirmation word did not match — type "{RESTORE_CONFIRM_WORD}" exactly.',
        )


async def _post_to_agent(path: str, json_body: dict) -> dict:
    """POSTs to the agent and returns its JSON body, or raises a clean
    HTTPException. Used by both restore endpoints — restore requests can
    legitimately take a while to even ACK (the agent verifies the key before
    responding), so this uses a longer timeout than the plain /run-backup
    call, but the restore itself still runs in the background regardless."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.backup_agent_url.rstrip('/')}{path}",
                headers={"X-Agent-Secret": settings.backup_agent_secret},
                json=json_body,
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach the backup agent: {e}")
    if resp.status_code == 403:
        # The agent's own cryptographic key-match check failed — surface its
        # message as-is (it never includes the key itself, see app.py).
        raise HTTPException(status_code=403, detail=resp.json().get("detail", "Private key rejected by the agent."))
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Backup agent returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


class RestoreFullRequest(BaseModel):
    confirm_word: str
    private_key: str


class RestoreClubRequest(BaseModel):
    confirm_word: str
    org_id: str
    private_key: str


@router.post("/{task_id}/restore-full")
async def restore_full_now(
    task_id: str,
    body: RestoreFullRequest,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Restores the WHOLE platform from this task's backup bundle — replaces
    every club's live data, briefly stops the app. Gated by the typed
    confirmation word (checked here) and the private key (checked
    cryptographically by the agent — see module docstring). Fire-and-forget:
    poll the task list for a new `restore_full` task's progress, same as any
    other run."""
    _require_confirm_word(body.confirm_word)
    _require_agent_configured()
    bundle = await _resolve_bundle(db, task_id)
    return await _post_to_agent("/run-restore-full", {"bundle": bundle, "private_key": body.private_key})


@router.post("/{task_id}/restore-club")
async def restore_club_now(
    task_id: str,
    body: RestoreClubRequest,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Restores ONE club's data from this task's backup bundle — no
    downtime, never touches another club's data (see
    app/services/club_restore.py for exactly how a row is attributed to one
    club). Snapshots the club's current live data first, so it's undoable
    via the existing rollback-club SSH command. Same two-gate model as
    restore-full."""
    _require_confirm_word(body.confirm_word)
    _require_agent_configured()
    bundle = await _resolve_bundle(db, task_id)
    return await _post_to_agent(
        "/run-restore-club", {"bundle": bundle, "org_id": body.org_id, "private_key": body.private_key}
    )


@router.get("/{task_id}/download")
async def download_backup_file(
    task_id: str,
    file: str = Query(..., description="One of: db, uploads, manifest, checksums"),
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Streams one still-ENCRYPTED file from a completed backup bundle,
    proxied through the backup-agent (this process has no filesystem access
    to BACKUP_ROOT itself — same reasoning as /run above). Manual, on-demand
    only; there's no automatic offsite sync of these files anywhere."""
    if file not in _DOWNLOADABLE_FILES:
        raise HTTPException(status_code=400, detail=f"file must be one of {sorted(_DOWNLOADABLE_FILES)}")
    _require_agent_configured()
    bundle = await _resolve_bundle(db, task_id)

    client = httpx.AsyncClient(timeout=None)
    try:
        req = client.build_request(
            "GET", f"{settings.backup_agent_url.rstrip('/')}/backup-file",
            params={"bundle": bundle, "file": file},
            headers={"X-Agent-Secret": settings.backup_agent_secret},
        )
        upstream = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Could not reach the backup agent: {e}")
    if upstream.status_code != 200:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=upstream.status_code, detail="Backup agent could not serve that file")

    async def _stream():
        try:
            async for chunk in upstream.aiter_bytes():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        _stream(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{bundle}-{_DOWNLOADABLE_FILES[file]}"'},
    )
