"""Verification: a removed person's page is gone (410 + noindex), and the public player
data is rate limited. Real nginx running the SHIPPED `frontend/nginx.conf`, in front of the
SHIPPED `routers/seo.py` and `routers/og_preview.py` on a real Postgres.

Reported: a person who asked to be removed had no profile (the API answered 404), but their
old address still answered 200 with the site's page shell, so search engines kept it as a soft
404; and nothing slowed a client asking for player after player.

What runs:
  * nginx (the repo's conf with only the listen port and web root swapped) -> a small FastAPI
    app that mounts the real `seo` and `og_preview` routers, plus stand-ins for the player and
    games data routes (their contents are not what is under test).
  * three players: REMOVED (asked to be removed), NORMAL, CLUBHID (hidden by the club with the
    older `is_public` switch only).

Every "X is gone / limited" check is paired with a check that X could be present, for a
normal player or a different client (rule 21).

CONTROL (`--conf PATH`): run the same file against the nginx.conf from the commit before this
change (`git show 853a7e7:frontend/nginx.conf > /tmp/old.conf`). It must fail exactly the 410 and
429 checks and nothing else.

Needs: nginx on PATH, a line `127.0.0.1 betterstats-backend` in /etc/hosts (added here if
we may write it), and port 8000 free.

Run:  DATABASE_URL=postgresql+asyncpg://root@/page_gone_test?host=/var/run/postgresql \
      python verification/verify_nginx_player_pages.py [--conf /tmp/old.conf]
"""
from __future__ import annotations

import asyncio
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

import httpx
import uvicorn
from fastapi import FastAPI
from sqlalchemy import text

import verify_fantasy_unsettle as base
from app.models.db import Organisation, Player
from app.routers import og_preview as og_router
from app.routers import seo as seo_router
from app.services.player_privacy_ddl import STATEMENTS as PRIVACY_DDL

Session, check = base.Session, base.check
REPO = Path(__file__).resolve().parent.parent.parent
CONF = Path(sys.argv[sys.argv.index("--conf") + 1]) if "--conf" in sys.argv else REPO / "frontend" / "nginx.conf"
NGINX_PORT = 18081
BACKEND_PORT = 8000

ORG = uuid.uuid4()
REMOVED, NORMAL, CLUBHID, UNKNOWN = (uuid.uuid4() for _ in range(4))
SHELL = "SPA-SHELL-MARKER"


def build_backend() -> FastAPI:
    app = FastAPI()
    app.include_router(seo_router.router)
    app.include_router(og_router.router)

    @app.get("/players")
    async def roster():
        return [{"id": str(NORMAL)}]

    @app.get("/players/{player_id}")
    async def one(player_id: str):
        return {"id": player_id}

    @app.get("/games/{game_id}/scorecard")
    async def card(game_id: str):
        return {"id": game_id}

    @app.get("/ladders/{x}")
    async def ladder(x: str):
        return {"x": x}

    return app


class Server(uvicorn.Server):
    def install_signal_handlers(self) -> None:  # runs in a thread
        pass


def start_backend() -> tuple[Server, threading.Thread]:
    server = Server(uvicorn.Config(build_backend(), host="127.0.0.1", port=BACKEND_PORT, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.1)
    return server, t


def ensure_hosts_entry() -> None:
    try:
        socket.gethostbyname("betterstats-backend")
        return
    except OSError:
        pass
    with open("/etc/hosts", "a") as fh:
        fh.write("\n127.0.0.1 betterstats-backend\n")


def start_nginx(tmp: Path) -> subprocess.Popen:
    html = tmp / "html"
    html.mkdir()
    html.chmod(0o755)
    (html / "index.html").write_text(f"<html><body>{SHELL}</body></html>")
    (html / "index.html").chmod(0o644)
    conf = CONF.read_text().replace("listen 80;", f"listen {NGINX_PORT};") \
                           .replace("/usr/share/nginx/html", str(html))
    (tmp / "conf.d").mkdir()
    (tmp / "conf.d" / "default.conf").write_text(conf)
    main = f"""
pid {tmp}/nginx.pid;
error_log {tmp}/error.log warn;
events {{ worker_connections 256; }}
http {{
    access_log off;
    client_body_temp_path {tmp}/cb; proxy_temp_path {tmp}/pt; fastcgi_temp_path {tmp}/fc;
    uwsgi_temp_path {tmp}/uw; scgi_temp_path {tmp}/sc;
    include {tmp}/conf.d/*.conf;
}}
"""
    (tmp / "nginx.conf").write_text(main)
    test = subprocess.run(["nginx", "-t", "-c", str(tmp / "nginx.conf")], capture_output=True, text=True)
    if test.returncode != 0:
        print(test.stderr)
        raise SystemExit("nginx -t failed")
    proc = subprocess.Popen(["nginx", "-c", str(tmp / "nginx.conf"), "-g", "daemon off;"])
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", NGINX_PORT), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    return proc


async def seed() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        for stmt in PRIVACY_DDL:
            await conn.execute(text(stmt))
    async with Session() as s:
        s.add(Organisation(id=ORG, name="Alpha CC", slug="alpha", is_active=True))
        await s.flush()
        s.add_all([Player(id=REMOVED, name="Removed, Remy", organisation_id=ORG, grassroots_id=str(REMOVED), is_public=False),
                   Player(id=NORMAL, name="Normal, Nora", organisation_id=ORG, grassroots_id=str(NORMAL)),
                   Player(id=CLUBHID, name="Hidden, Hal", organisation_id=ORG, grassroots_id=str(CLUBHID), is_public=False)])
        await s.flush()
        await s.execute(text("UPDATE players SET privacy_hidden_at = NOW(), privacy_hidden_by = 'test', "
                             "privacy_hidden_reason = 'asked to be removed' WHERE id = :p"), {"p": REMOVED})
        await s.commit()


def get(client: httpx.Client, path: str, xff: str | None = None, ua: str | None = None) -> httpx.Response:
    h = {}
    if xff is not None:
        h["X-Forwarded-For"] = xff
    if ua:
        h["User-Agent"] = ua
    return client.get(f"http://127.0.0.1:{NGINX_PORT}{path}", headers=h, follow_redirects=False)


def burst(client: httpx.Client, path: str, n: int, xff: str | None) -> list[int]:
    return [get(client, path, xff).status_code for _ in range(n)]


def run_checks() -> None:
    c = httpx.Client(timeout=10)
    P = "/players/"

    print("1. A person who asked to be removed has no page")
    r = get(c, f"{P}{REMOVED}")
    check("their address answers 410", r.status_code == 410, f"{r.status_code}")
    check("…with a noindex header", "noindex" in r.headers.get("x-robots-tag", "").lower(), str(dict(r.headers)))
    check("…and a body that carries neither the id nor the name",
          str(REMOVED) not in r.text and "Remy" not in r.text and "Removed, Remy" not in r.text)
    check("a trailing slash and a query string get the same answer",
          get(c, f"{P}{REMOVED}/").status_code == 410 and get(c, f"{P}{REMOVED}?tab=career").status_code == 410)
    r = get(c, f"{P}{REMOVED}", ua="GPTBot/1.0")
    check("an AI crawler is told 410 too", r.status_code == 410, f"{r.status_code}")
    r = get(c, f"{P}{REMOVED}", ua="facebookexternalhit/1.1")
    check("so is a social link-preview bot", r.status_code == 410, f"{r.status_code}")

    print("2. Every other page loads exactly as before")
    for label, pid in (("a normal player", NORMAL), ("a player the club hid itself", CLUBHID), ("an id nobody has", UNKNOWN)):
        r = get(c, f"{P}{pid}")
        check(f"{label}: 200 and the page shell", r.status_code == 200 and SHELL in r.text, f"{r.status_code} {r.text[:60]!r}")
    r = get(c, f"{P}{NORMAL}?tab=career")
    check("a normal player with a query string still loads", r.status_code == 200 and SHELL in r.text)
    r = get(c, f"{P}{NORMAL}", ua="GPTBot/1.0")
    check("a normal player still gets the crawler card", r.status_code == 200 and "BetterCricket" in r.text, f"{r.status_code}")
    r = get(c, f"{P}{REMOVED}/share")
    check("the share address is untouched (still the shell)", r.status_code == 200 and SHELL in r.text)
    check("a non-player page is untouched", get(c, "/features").status_code == 200)

    print("3. Rate limits on the public player data")
    n = 40
    got = burst(c, "/api/players?org_id=x", n, None)
    check("no X-Forwarded-For: not limited at all (fails open, never one shared bucket)", got.count(200) == n, str(got))
    got_a = burst(c, "/api/players?org_id=x", 60, "9.9.9.9")
    check("one client asking for the roster over and over gets 429", 429 in got_a, str(got_a))
    check("…after its burst, not before it", got_a[:20].count(200) == 20, str(got_a[:25]))
    r = get(c, "/api/players?org_id=x", "9.9.9.9")
    check("the 429 is JSON with a Retry-After",
          r.status_code == 429 and r.headers.get("retry-after") == "5" and "Too many requests" in r.text,
          f"{r.status_code} {r.headers.get('retry-after')} {r.text[:80]}")
    check("a DIFFERENT client is not slowed by it", get(c, "/api/players?org_id=x", "9.9.9.8").status_code == 200)
    spoof = [get(c, "/api/players?org_id=x", f"10.{i}.0.1, 9.9.9.9").status_code for i in range(10)]
    check("an invented leading address does not evade the limit (the LAST entry is the client)",
          429 in spoof, str(spoof))
    page_load = burst(c, f"/api/players/{NORMAL}", 15, "8.8.8.8")
    check("a profile page's fifteen calls at once are not limited", page_load.count(200) == 15, str(page_load))
    walk = burst(c, f"/api/players/{NORMAL}", 40, "8.8.1.1")
    check("a whole tab walk (forty calls in a burst) is not limited", walk.count(200) == 40, str(walk))
    many = burst(c, f"/api/players/{NORMAL}", 250, "8.8.4.4")
    check("a client asking for profile after profile is limited", 429 in many and many[:100].count(200) == 100, str(many[95:110]))
    sc = burst(c, f"/api/games/{uuid.uuid4()}/scorecard", 250, "7.7.7.7")
    check("so is one pulling scorecard after scorecard", 429 in sc, str(sc[95:110]))
    other = burst(c, "/api/ladders/x", 250, "9.9.9.9")
    check("a route that is not player data is not limited (same busy client)", other.count(200) == 250, str(other[:30]))

    print("4. The backend being down never takes the player pages with it")
    return c


def after_backend_down() -> None:
    c = httpx.Client(timeout=10)
    r = get(c, f"/players/{NORMAL}")
    check("with the backend down a normal player page still serves the shell",
          r.status_code == 200 and SHELL in r.text, f"{r.status_code} {r.text[:60]!r}")
    r = get(c, "/api/players?org_id=x", "5.5.5.5")
    check("…and an API call reads as 'System refreshing', not a limit error", r.status_code == 503, f"{r.status_code}")


async def main() -> None:
    await seed()
    ensure_hosts_entry()
    tmp = Path(tempfile.mkdtemp(prefix="nginx_pages_"))
    tmp.chmod(0o755)   # the worker runs as another user and must be able to read the page shell
    server, thread = start_backend()
    proc = start_nginx(tmp)
    try:
        run_checks()
        server.should_exit = True
        thread.join(timeout=10)
        time.sleep(0.5)
        after_backend_down()
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        err = (tmp / "error.log").read_text() if (tmp / "error.log").exists() else ""
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    if err.strip():
        print("nginx error log (limit lines expected):\n" + "\n".join(err.strip().splitlines()[:6]))
    if base.FAIL:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
