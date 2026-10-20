"""Exposure audit: can a SIGNED-OUT visitor find a player who asked to be removed?

Calls EVERY GET route of the real FastAPI app (`app.main.app`) with no
credentials, over a seeded club in which one player with real games, season
totals and teammates has been removed at their own request, and searches every
response body for their name and id.

It runs TWICE over the same routes:
  * BEFORE the removal: the scanner must find the player in many responses.
    A scanner that finds nobody proves nothing (rule 21), so this pass is the
    control that the net can catch a leak at all.
  * AFTER the removal: the same routes, every response, must hold neither the
    name nor the id.

Each route is called once per candidate value of its path and required-query
parameters (every player, every game, ...), so a teammate's page, a match
page and a club-wide board are all asked about the removed player.

A route that errors (500) in this harness is NOT a pass: it needs tables the
harness does not build. They are listed so a person can read each one.

Run:  DATABASE_URL=postgresql+asyncpg://root@/audit_test?host=/var/run/postgresql \
      python verification/audit_hidden_player_exposure.py
"""
from __future__ import annotations

import asyncio
import inspect
import itertools
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

import httpx
from sqlalchemy import text

import app.models.scout  # noqa: F401  (registers scouted_players on Base)
import verify_hide_juniors as hj           # the seeded club: games, innings, season totals
from app.services import player_privacy
from app.services.player_privacy_ddl import STATEMENTS as PRIVACY_DDL

HIDE_KEY = "S1"                              # a senior with three games and teammates
NAME = "Zebediah Quillfeather"               # unique, so a hit cannot be a common word
SLUG = "kalamunda"


async def prepare() -> None:
    async with hj.engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await hj.build_schema()
    async with hj.engine.begin() as conn:
        for stmt in PRIVACY_DDL:
            await conn.execute(text(stmt))
    async with hj.Session() as s:
        await hj.seed(s)
    async with hj.engine.begin() as conn:
        await conn.execute(text("UPDATE players SET name = :n WHERE id = :i"),
                           {"n": NAME, "i": hj.P[HIDE_KEY]})
        await conn.execute(text("UPDATE organisations SET slug = :s, is_active = true WHERE id = :o"),
                           {"s": SLUG, "o": hj.OURS})


async def hide() -> None:
    async with hj.Session() as s:
        pl = await s.get(__import__("app.models.db", fromlist=["Player"]).Player, hj.P[HIDE_KEY])
        await player_privacy.hide_at_request(s, pl, by="audit", reason="exposure audit")
        await s.commit()
    try:
        from app.services import junior_hiding
        junior_hiding.forget()
    except Exception:
        pass


def candidate_values():
    return {
        "player": [str(hj.P[k]) for k in hj.P] + [str(hj.OPP)],
        "game": [str(g) for g in hj.GAMES.values()],
        "season": [str(hj.S25), str(hj.S24)],
        "grade": [str(hj.G_SEN), str(hj.G_JUN)],
        "org": [str(hj.OURS)],
        "slug": [SLUG],
    }


def kind_of(name: str) -> str | None:
    n = name.lower()
    if n in ("slug", "club_slug", "org_slug"):
        return "slug"
    if "player" in n or n in ("pid", "teammate_id"):
        return "player"
    if "game" in n or "match" in n or "fixture" in n:
        return "game"
    if "season" in n:
        return "season"
    if "grade" in n:
        return "grade"
    if n in ("org_id", "organisation_id", "club_id", "oid", "id", "organization_id") or "org" in n:
        return "org"
    return None


def plan_for(route, values):
    """Yield (path, params) for every combination of the route's key parameters."""
    path_names = [p.name for p in route.dependant.path_params]
    query_req = [q for q in route.dependant.query_params if q.required]
    slots: list[tuple[str, bool, list[str]]] = []   # (name, is_path, candidates)
    for name, is_path in [(n, True) for n in path_names] + [(q.name, False) for q in query_req]:
        k = kind_of(name)
        cands = values[k] if k else [str(uuid.uuid4())]
        slots.append((name, is_path, cands))
    if not slots:
        yield route.path, {}
        return
    # Bound the fan-out: one value per slot kind except `player`/`game`, which
    # are asked about exhaustively (those are the ones that could leak him).
    pools = []
    for name, is_path, cands in slots:
        k = kind_of(name)
        pools.append(cands if k in ("player", "game") else cands[:1])
    for combo in itertools.islice(itertools.product(*pools), 40):
        path = route.path
        params = {}
        for (name, is_path, _), val in zip(slots, combo):
            if is_path:
                path = path.replace("{" + name + "}", val)
                # {name:path} converters
                path = path.replace("{" + name + ":path}", val)
            else:
                params[name] = val
        yield path, params


async def scan(label: str):
    from app.main import app
    from fastapi.routing import APIRoute
    values = candidate_values()
    hidden_id = str(hj.P[HIDE_KEY]).lower()
    needles = (NAME.lower(), "quillfeather", "zebediah", hidden_id)

    hits: dict[str, str] = {}
    errors: list[str] = []
    asked = 0
    ok_200 = 0
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t", timeout=15) as c:
        routes = [r for r in app.routes if isinstance(r, APIRoute) and "GET" in r.methods]
        for r in routes:
            for path, params in plan_for(r, values):
                asked += 1
                try:
                    resp = await asyncio.wait_for(c.get(path, params=params), 20)
                except Exception as exc:   # a hang or crash is not a pass
                    errors.append(f"{r.path}  ({type(exc).__name__})")
                    break
                if resp.status_code >= 500:
                    errors.append(f"{r.path}  ({resp.status_code})")
                    break
                if resp.status_code == 200:
                    ok_200 += 1
                body = resp.text.lower()
                if any(n in body for n in needles):
                    hits.setdefault(r.path, f"{path}?{params}" if params else path)
    print(f"\n[{label}] {len(routes)} GET routes, {asked} requests, {ok_200} answered 200, "
          f"{len(set(errors))} routes errored in this harness, {len(hits)} routes mention the removed player")
    return hits, sorted(set(errors))


async def main() -> int:
    await prepare()
    before_hits, _ = await scan("BEFORE removal (control: the scanner must be able to find him)")
    for p in sorted(before_hits):
        print("   found:", p)
    control_ok = len(before_hits) >= 5
    print("CONTROL", "OK" if control_ok else "FAILED: the scanner is blind, the after-pass proves nothing")

    await hide()
    after_hits, errors = await scan("AFTER removal")
    for p, example in sorted(after_hits.items()):
        print("   LEAK:", p, " e.g.", example)
    print("\nRoutes that errored here (read by hand, NOT counted as safe):")
    for e in errors:
        print("   ", e)
    return 0 if (control_ok and not after_hits) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
