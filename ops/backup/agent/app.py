"""betterstats-backup-agent — the ONLY thing on the box with both a Docker
socket and a way for the backend to reach it. Exists so Super Admin's "Run
backup now" / "Restore" actions on the Backups page can happen without
giving the betterstats-backend container Docker-socket access itself (a real
privilege escalation risk — socket access is effectively root on the host).

Fixed, narrow API — no arbitrary command execution:
  POST /run-backup         body: {"triggered_by_user_id": "<uuid>"}   (optional)
  POST /run-restore-full   body: {"bundle": "<timestamp>", "private_key": "<age identity>"}
  POST /run-restore-club   body: {"bundle": "<timestamp>", "org_id": "<uuid>", "private_key": "<age identity>"}
  GET  /backup-file        ?bundle=<timestamp>&file=<db|uploads|manifest|checksums>
  GET  /health

Auth: a shared secret in the X-Agent-Secret header, checked against
BACKUP_AGENT_SECRET. This container is NEVER routed through
nginx-proxy-manager — it's reachable only on the internal Docker network the
backend is also on. The shared secret is defence in depth on top of that
network boundary, not the only line of defence.

/backup-file only ever serves the STILL-ENCRYPTED bundle files as-is
(db.dump.age, uploads.tar.zst.age, ...).

RESTORE AND THE PRIVATE KEY — the web-restore endpoints below are the
*supplement* to (not a replacement for) SSH-run restore.sh: both remain
fully available. This agent never stores the age private key at rest, ever:
- It's supplied fresh on every single restore request, in the request body.
- It's written to a private (0600) temp file that lives only on this
  container's own ephemeral filesystem (/tmp — not a bind mount, unlike
  /srv/docker or BACKUP_ROOT, so it never touches host disk).
- Before the restore is allowed to proceed, `age-keygen -y` derives the
  PUBLIC key from the supplied private key and it's compared against this
  server's configured AGE_RECIPIENT — a wrong or unrelated key is rejected
  outright, so the two keys being a real matching pair is verified here,
  server-side, not just trusted from the caller.
- The temp file is shredded the moment the restore process exits, success or
  failure (see the `finally` blocks below) — never logged, never returned in
  any response, never persisted between requests.
The word-confirmation step (typing e.g. "RESTORE" back) happens in the
backend (routers/backup_admin.py), before this agent is ever called — this
agent's own gate is the cryptographic key-match check.
"""
import asyncio
import os
import re
import subprocess
import tempfile
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="betterstats-backup-agent")

AGENT_SECRET = os.environ.get("BACKUP_AGENT_SECRET", "")
AGE_RECIPIENT = os.environ.get("AGE_RECIPIENT", "")
BACKUP_SCRIPT = os.environ.get("BACKUP_SCRIPT", "/srv/docker/betterstats/ops/backup/backup.sh")
RESTORE_SCRIPT = os.environ.get("RESTORE_SCRIPT", "/srv/docker/betterstats/ops/backup/restore.sh")
BACKUP_ROOT = Path(os.environ.get("BACKUP_ROOT", "/mnt/media/bettercricket/backup"))

# Bundle directory names are always backup.sh's own `date -u +%Y-%m-%dT%H-%M-%SZ`
# stamp — validating against this shape (rather than just checking the
# resolved path stays under BACKUP_ROOT) is the actual defence against path
# traversal via a crafted `bundle` query param.
_BUNDLE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z$")
_ORG_ID_RE = re.compile(r"^[0-9a-fA-F-]{32,36}$")

_DOWNLOADABLE_FILES = {
    "db": "db.dump.age",
    "uploads": "uploads.tar.zst.age",
    "manifest": "manifest.json",
    "checksums": "checksums.sha256",
}

# One operation (backup OR either kind of restore) at a time — they all touch
# the same fixed-name scratch container / live DB, so overlapping runs would
# collide. backup.sh/restore.sh are the source of truth for per-run task
# state (backup_tasks); this lock is purely to stop two runs stepping on each
# other's scratch container or the live DB mid-cutover.
_run_lock = asyncio.Lock()
_running_op: str | None = None


class RunBackupBody(BaseModel):
    triggered_by_user_id: str | None = None


class RestoreFullBody(BaseModel):
    bundle: str
    private_key: str


class RestoreClubBody(BaseModel):
    bundle: str
    org_id: str
    private_key: str


def _check_secret(x_agent_secret: str | None):
    if not AGENT_SECRET:
        raise HTTPException(status_code=503, detail="Agent has no BACKUP_AGENT_SECRET configured")
    if x_agent_secret != AGENT_SECRET:
        raise HTTPException(status_code=403, detail="Bad or missing agent secret")


def _shred(path: str):
    """Best-effort secure delete of a private-key temp file. Never raises —
    called from `finally` blocks where the restore's own outcome matters
    more than a cleanup hiccup."""
    try:
        subprocess.run(["shred", "-u", path], capture_output=True, timeout=10)
    except Exception:
        pass
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except Exception:
        pass


def _write_and_verify_key(private_key: str) -> str:
    """Writes the supplied private key to a private (0600) temp file on this
    container's own ephemeral filesystem, and verifies it's the REAL private
    half of this server's configured AGE_RECIPIENT (derives the public key
    from it via `age-keygen -y` and compares). Returns the temp file path on
    success. On any failure, shreds the temp file itself before raising —
    callers still don't need to clean up a rejected key."""
    if not AGE_RECIPIENT:
        raise RuntimeError("AGE_RECIPIENT is not configured on this agent")
    fd, path = tempfile.mkstemp(prefix="restore-key-", dir="/tmp")
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(private_key.strip() + "\n")
        result = subprocess.run(
            ["age-keygen", "-y", path], capture_output=True, text=True, timeout=15,
        )
        derived = result.stdout.strip()
        if result.returncode != 0:
            raise ValueError(
                "That doesn't look like a valid age private key "
                f"(age-keygen couldn't read it: {result.stderr.strip()[:200]})"
            )
        if derived != AGE_RECIPIENT:
            raise ValueError(
                "That private key doesn't match this server's configured public key "
                "(AGE_RECIPIENT) — it can't decrypt these backups."
            )
        return path
    except Exception:
        _shred(path)
        raise


@app.get("/health")
async def health():
    return {"status": "ok"}


async def _run_backup_process(triggered_by_user_id: str | None):
    global _running_op
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
        _running_op = None


async def _run_restore_process(args: list[str], key_path: str, label: str):
    global _running_op
    env = dict(os.environ)
    env["AGE_IDENTITY_FILE"] = key_path
    env["ASSUME_YES"] = "1"
    try:
        proc = await asyncio.create_subprocess_exec(
            "/bin/bash", RESTORE_SCRIPT, *args,
            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        if proc.returncode != 0:
            # Never includes key material — restore.sh's own output doesn't
            # echo the identity file's contents, only the path we gave it.
            print(f"[backup-agent] {label} exited {proc.returncode}:\n{out.decode(errors='replace')}")
    finally:
        _shred(key_path)
        _running_op = None


@app.post("/run-backup")
async def run_backup(body: RunBackupBody, x_agent_secret: str | None = Header(default=None)):
    _check_secret(x_agent_secret)
    global _running_op
    async with _run_lock:
        if _running_op:
            return {"status": "already_running", "operation": _running_op}
        _running_op = "backup"
        asyncio.create_task(_run_backup_process(body.triggered_by_user_id))
    return {"status": "started"}


@app.post("/run-restore-full")
async def run_restore_full(body: RestoreFullBody, x_agent_secret: str | None = Header(default=None)):
    _check_secret(x_agent_secret)
    if not _BUNDLE_RE.match(body.bundle):
        raise HTTPException(status_code=400, detail="Invalid bundle timestamp")
    global _running_op
    async with _run_lock:
        if _running_op:
            return {"status": "already_running", "operation": _running_op}
        try:
            key_path = _write_and_verify_key(body.private_key)
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        _running_op = "restore_full"
        asyncio.create_task(_run_restore_process(["apply", body.bundle], key_path, "restore.sh apply"))
    return {"status": "started"}


@app.post("/run-restore-club")
async def run_restore_club(body: RestoreClubBody, x_agent_secret: str | None = Header(default=None)):
    _check_secret(x_agent_secret)
    if not _BUNDLE_RE.match(body.bundle):
        raise HTTPException(status_code=400, detail="Invalid bundle timestamp")
    if not _ORG_ID_RE.match(body.org_id):
        raise HTTPException(status_code=400, detail="Invalid org id")
    global _running_op
    async with _run_lock:
        if _running_op:
            return {"status": "already_running", "operation": _running_op}
        try:
            key_path = _write_and_verify_key(body.private_key)
        except ValueError as e:
            raise HTTPException(status_code=403, detail=str(e))
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))
        _running_op = "restore_club"
        asyncio.create_task(_run_restore_process(
            ["restore-club", body.bundle, body.org_id, "--apply"], key_path, "restore.sh restore-club",
        ))
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
