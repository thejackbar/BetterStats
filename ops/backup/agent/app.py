"""betterstats-backup-agent — the ONLY thing on the box with both a Docker
socket and a way for the backend to reach it. Exists purely so a Super
Admin's "Run backup now" button can kick off backup.sh without giving the
betterstats-backend container Docker-socket access itself (a real privilege
escalation risk — socket access is effectively root on the host).

Fixed, narrow API — no arbitrary command execution:
  POST /run-backup    body: {"triggered_by_user_id": "<uuid>"}   (optional)
  GET  /backup-file    ?bundle=<timestamp>&file=<db|uploads|manifest|checksums>
  GET  /health

Auth: a shared secret in the X-Agent-Secret header, checked against
BACKUP_AGENT_SECRET. This container is NEVER routed through
nginx-proxy-manager — it's reachable only on the internal Docker network the
backend is also on. The shared secret is defence in depth on top of that
network boundary, not the only line of defence.

Deliberately does NOT expose a restore endpoint, and /backup-file only ever
serves the STILL-ENCRYPTED bundle files as-is (db.dump.age,
uploads.tar.zst.age, ...) — it has no access to the age PRIVATE key (see
docs/backup-system.md: that key is kept OFFLINE, never on the box), so a
downloaded file is exactly as safe in transit/at rest as it already was
sitting in BACKUP_ROOT. Restore (full or per-club) stays an SSH-to-the-box
operation, see ops/backup/restore.sh.
"""
import asyncio
import os
import re
import subprocess
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="betterstats-backup-agent")

AGENT_SECRET = os.environ.get("BACKUP_AGENT_SECRET", "")
BACKUP_SCRIPT = os.environ.get("BACKUP_SCRIPT", "/srv/docker/betterstats/ops/backup/backup.sh")
BACKUP_ROOT = Path(os.environ.get("BACKUP_ROOT", "/mnt/media/bettercricket/backup"))

# Bundle directory names are always backup.sh's own `date -u +%Y-%m-%dT%H-%M-%SZ`
# stamp — validating against this shape (rather than just checking the
# resolved path stays under BACKUP_ROOT) is the actual defence against path
# traversal via a crafted `bundle` query param.
_BUNDLE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$")

_DOWNLOADABLE_FILES = {
    "db": "db.dump.age",
    "uploads": "uploads.tar.zst.age",
    "manifest": "manifest.json",
    "checksums": "checksums.sha256",
}

# Guards against a double-click firing two overlapping backup runs — backup.sh
# itself is also idempotent (has-run-today), this just avoids two pg_dumps
# stepping on each other's bundle directory in the same second.
_run_lock = asyncio.Lock()
_running = False


class RunBackupBody(BaseModel):
    triggered_by_user_id: str | None = None


def _check_secret(x_agent_secret: str | None):
    if not AGENT_SECRET:
        raise HTTPException(status_code=503, detail="Agent has no BACKUP_AGENT_SECRET configured")
    if x_agent_secret != AGENT_SECRET:
        raise HTTPException(status_code=403, detail="Bad or missing agent secret")


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _run_backup_process(triggered_by_user_id: str | None):
    global _running
    env = dict(os.environ)
    env["BACKUP_FORCE"] = "1"
    env["BACKUP_TRIGGERED_BY"] = "manual"
    if triggered_by_user_id:
        env["BACKUP_TRIGGERED_BY_USER_ID"] = triggered_by_user_id
    try:
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash", BACKUP_SCRIPT,
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            # backup.sh already logs its own failure into backup_tasks; this
            # is just for `docker logs betterstats-backup-agent`.
            print(f"[backup-agent] backup.sh exited {proc.returncode}:\n{out.decode(errors='replace')}")
    finally:
        _running = False


@app.post("/run-backup")
async def run_backup(body: RunBackupBody, x_agent_secret: str | None = Header(default=None)):
    _check_secret(x_agent_secret)
    global _running
    async with _run_lock:
        if _running:
            return {"status": "already_running"}
        _running = True
        asyncio.create_task(_run_backup_process(body.triggered_by_user_id))
    return {"status": "started"}


@app.get("/backup-file")
async def backup_file(bundle: str, file: str, x_agent_secret: str | None = Header(default=None)):
    _check_secret(x_agent_secret)
    if not _BUNDLE_RE.match(bundle):
        raise HTTPException(status_code=400, detail="Invalid bundle timestamp")
    filename = _DOWNLOADABLE_FILES.get(file)
    if not filename:
        raise HTTPException(status_code=400, detail=f"Unknown file kind {file!r} (expected one of {sorted(_DOWNLOADABLE_FILES)})")
    path = BACKUP_ROOT / bundle / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No such backup file")
    return FileResponse(path, filename=f"{bundle}-{filename}", media_type="application/octet-stream")
