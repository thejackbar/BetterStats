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

Schedule, retention and the stored bundles themselves are managed from the
Backup settings page (``/settings``, ``/files`` below). The schedule is a
PERTH wall-clock time end to end — stored that way, checked that way by the
host script, displayed that way here (see services/backup_schedule.py, which
is the only place that maths lives). Deleting a bundle removes files only:
the ``backup_tasks`` row stays as history and is stamped
``bundle_deleted_at``, so the page can say the files are gone rather than
offering a download and a restore that would fail.

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
from app.services import backup_schedule, backup_stats, platform_settings as ps

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
               t.total_row_count, t.club_stats, t.error_message, t.progress,
               t.bundle_deleted_at, t.bundle_deleted_reason
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
                # NULL = the bundle is still expected on disk. Set once its
                # files have gone (retention pruning, or a deliberate delete
                # from the Backup settings page), which is what stops the
                # page offering a download/restore that can only fail.
                "bundle_deleted_at": r["bundle_deleted_at"],
                "bundle_deleted_reason": r["bundle_deleted_reason"],
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


# ─── Backup settings: schedule, retention, and what's on disk ────────────────
# The schedule is a PERTH wall-clock time everywhere — set here, stored here,
# and checked by the host script through the same services/backup_schedule.py
# maths. Nothing converts to UTC and back for display, which is what used to
# make "when does it actually run" a question with two answers.


class BackupSettingsUpdate(BaseModel):
    hour: Optional[int] = None      # 0-23, Perth local
    minute: Optional[int] = None    # 0-59
    retention_days: Optional[int] = None


async def _last_completed_backup(db: AsyncSession):
    row = (await db.execute(text(
        "SELECT COALESCE(completed_at, started_at) FROM backup_tasks "
        "WHERE task_type = 'backup' AND status = 'completed' "
        "ORDER BY COALESCE(completed_at, started_at) DESC LIMIT 1"
    ))).first()
    return row[0] if row else None


async def _settings_payload(db: AsyncSession) -> dict:
    schedule = await ps.get_backup_schedule(db)
    last_completed = await _last_completed_backup(db)
    return {
        "schedule": schedule,
        "retention_min_days": ps.BACKUP_RETENTION_MIN_DAYS,
        "retention_max_days": ps.BACKUP_RETENTION_MAX_DAYS,
        "last_completed_at": last_completed,
        "next_run_at": backup_schedule.next_run_at(schedule, last_completed=last_completed),
        "perth_now": backup_schedule.perth_now(),
        "agent_configured": bool(settings.backup_agent_url),
    }


@router.get("/settings")
async def get_backup_settings(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """The daily backup's schedule (Perth time) and retention window, plus
    when it last ran and when it runs next."""
    return await _settings_payload(db)


@router.patch("/settings")
async def update_backup_settings(
    body: BackupSettingsUpdate,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Change the backup time and/or how many days of bundles are kept. Takes
    effect on the host script's next tick — no redeploy, no unit file to
    edit. Only the fields sent are changed.

    Retention is applied by the NEXT run's prune step, so shortening the
    window doesn't delete anything on save; that is what the file list below
    is for when a super admin wants space back now.
    """
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        return await _settings_payload(db)
    try:
        await ps.update_backup_schedule(
            db,
            hour=fields.get("hour"),
            minute=fields.get("minute"),
            retention_days=fields.get("retention_days"),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return await _settings_payload(db)


async def _agent_get(path: str, params: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{settings.backup_agent_url.rstrip('/')}{path}",
                headers={"X-Agent-Secret": settings.backup_agent_secret},
                params=params or {},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach the backup agent: {e}")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Backup agent returned {resp.status_code}: {resp.text[:300]}")
    return resp.json()


@router.get("/files")
async def list_backup_files(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Every backup bundle currently taking up space on disk, newest first,
    matched to the task that wrote it where there is one.

    DISK IS THE SOURCE OF TRUTH here, not the task table: a bundle from
    before task logging, or one whose row was never written because the run
    died mid-way, is still a directory somebody may want to clear. A task
    row with no bundle left is reported the other way round — as history with
    its files already gone.
    """
    _require_agent_configured()
    data = await _agent_get("/bundles")
    disk = {b["bundle"]: b for b in data.get("bundles", [])}

    rows = (await db.execute(text(
        "SELECT id, bundle_path, started_at, completed_at, db_size_bytes, uploads_size_bytes, "
        "       total_row_count, triggered_by, bundle_deleted_at, bundle_deleted_reason "
        "FROM backup_tasks WHERE task_type = 'backup' AND status = 'completed' "
        "AND bundle_path IS NOT NULL ORDER BY started_at DESC LIMIT 500"
    ))).mappings().all()
    task_by_bundle = {}
    for r in rows:
        name = (r["bundle_path"] or "").rstrip("/").rsplit("/", 1)[-1]
        # Newest wins: a re-run writing the same directory name is not a
        # thing backup.sh can do (the stamp is per-second), but a stale row
        # shouldn't outrank a fresh one if it ever were.
        task_by_bundle.setdefault(name, r)

    bundles = []
    for name, b in sorted(disk.items(), reverse=True):
        task = task_by_bundle.get(name)
        bundles.append({
            "bundle": name,
            "on_disk": True,
            "size_bytes": b.get("size_bytes"),
            "files": b.get("files") or [],
            "complete": b.get("complete", False),
            "task_id": str(task["id"]) if task else None,
            "started_at": task["started_at"] if task else None,
            "triggered_by": task["triggered_by"] if task else None,
            "total_row_count": task["total_row_count"] if task else None,
        })
    missing = [
        {
            "bundle": name,
            "on_disk": False,
            "size_bytes": None,
            "files": [],
            "complete": False,
            "task_id": str(r["id"]),
            "started_at": r["started_at"],
            "triggered_by": r["triggered_by"],
            "total_row_count": r["total_row_count"],
            "deleted_at": r["bundle_deleted_at"],
            "deleted_reason": r["bundle_deleted_reason"],
        }
        for name, r in task_by_bundle.items() if name not in disk
    ]
    missing.sort(key=lambda b: b["bundle"], reverse=True)

    return {
        "bundles": bundles,
        "missing": missing,
        "total_size_bytes": sum(b.get("size_bytes") or 0 for b in bundles),
        "backup_root": data.get("backup_root"),
        "root_missing": data.get("root_missing", False),
    }


class DeleteBundlesRequest(BaseModel):
    bundles: list[str]
    # The newest bundle is the one a restore would actually reach for, so
    # deleting it is a separate, deliberate act rather than something a
    # select-all can sweep up. The page asks again before setting this.
    include_latest: bool = False


@router.post("/files/delete")
async def delete_backup_files(
    body: DeleteBundlesRequest,
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Deletes the FILES of one or more bundles. The backup_tasks rows stay —
    a run's history, sizes and per-club stats are worth keeping after its
    files are gone, and stamping them is what lets the Backups page say so.

    Deleting is per-bundle rather than all-or-nothing: one name the agent
    can't find doesn't stop the rest, and every outcome comes back named.
    """
    if not body.bundles:
        raise HTTPException(status_code=400, detail="Select at least one backup to delete.")
    if len(body.bundles) > 200:
        raise HTTPException(status_code=400, detail="Too many backups in one request (max 200).")
    _require_agent_configured()

    on_disk = {b["bundle"] for b in (await _agent_get("/bundles")).get("bundles", [])}
    latest = max(on_disk) if on_disk else None
    requested = [b for b in dict.fromkeys(body.bundles)]
    for b in requested:
        if not _BUNDLE_RE.match(b):
            raise HTTPException(status_code=400, detail=f"Not a backup bundle name: {b}")
    if latest and latest in requested and not body.include_latest:
        raise HTTPException(
            status_code=400,
            detail=f"{latest} is the most recent backup — the one a restore would use. "
                   "Confirm again to delete it as well.",
        )

    results, freed = [], 0
    for bundle in requested:
        try:
            resp = await _agent_delete_bundle(bundle)
            freed += int(resp.get("freed_bytes") or 0)
            results.append({"bundle": bundle, "status": "deleted",
                            "freed_bytes": resp.get("freed_bytes")})
        except HTTPException as e:
            results.append({"bundle": bundle, "status": "failed", "detail": str(e.detail)})
            continue
        await db.execute(text(
            "UPDATE backup_tasks SET bundle_deleted_at = COALESCE(bundle_deleted_at, NOW()), "
            "bundle_deleted_by = COALESCE(bundle_deleted_by, :uid), "
            "bundle_deleted_reason = COALESCE(bundle_deleted_reason, 'manual') "
            "WHERE task_type = 'backup' AND bundle_path IS NOT NULL "
            "AND regexp_replace(bundle_path, '/+$', '') LIKE :suffix"
        ), {"uid": str(user.id), "suffix": f"%/{bundle}"})
    await db.commit()

    deleted = [r for r in results if r["status"] == "deleted"]
    return {
        "results": results,
        "deleted_count": len(deleted),
        "failed_count": len(results) - len(deleted),
        "freed_bytes": freed,
    }


async def _agent_delete_bundle(bundle: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{settings.backup_agent_url.rstrip('/')}/delete-bundle",
                headers={"X-Agent-Secret": settings.backup_agent_secret},
                json={"bundle": bundle},
            )
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach the backup agent: {e}")
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="No such backup bundle on disk")
    if resp.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Backup agent returned {resp.status_code}")
    return resp.json()


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
        text("SELECT bundle_path, task_type, status, bundle_deleted_at "
             "FROM backup_tasks WHERE id = :id"),
        {"id": task_id},
    )).first()
    if row is None:
        raise HTTPException(status_code=404, detail="No such backup task")
    bundle_path, task_type, task_status, deleted_at = row
    if task_type != "backup" or task_status != "completed" or not bundle_path:
        raise HTTPException(status_code=400, detail="Only a completed backup task can be used here")
    if deleted_at is not None:
        # Checked server-side rather than trusting the page to hide the
        # buttons — a tab left open before a delete would otherwise fire a
        # download or a restore at files that are no longer there.
        raise HTTPException(
            status_code=410,
            detail="This backup's files have been deleted — nothing left to download or restore.",
        )
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
