"""betterstats-backup-agent — the ONLY thing on the box with both a Docker
socket and a way for the backend to reach it. Exists purely so a Super
Admin's "Run backup now" button can kick off backup.sh without giving the
betterstats-backend container Docker-socket access itself (a real privilege
escalation risk — socket access is effectively root on the host).

Fixed, narrow API — no arbitrary command execution:
  POST /run-backup   body: {"triggered_by_user_id": "<uuid>"}   (optional)
  GET  /health

Auth: a shared secret in the X-Agent-Secret header, checked against
BACKUP_AGENT_SECRET. This container is NEVER routed through
nginx-proxy-manager — it's reachable only on the internal Docker network the
backend is also on. The shared secret is defence in depth on top of that
network boundary, not the only line of defence.

Deliberately does NOT expose a restore endpoint. Restoring needs the age
PRIVATE key, which docs/backup-system.md says to keep OFFLINE (a password
manager, not on the box) — putting it in a container this reachable would
defeat that. Restore (full or per-club) stays an SSH-to-the-box operation,
see ops/backup/restore.sh.
"""
import asyncio
import os
import subprocess

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="betterstats-backup-agent")

AGENT_SECRET = os.environ.get("BACKUP_AGENT_SECRET", "")
BACKUP_SCRIPT = os.environ.get("BACKUP_SCRIPT", "/srv/docker/betterstats/ops/backup/backup.sh")

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
