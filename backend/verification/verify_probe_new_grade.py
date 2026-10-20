"""The scheduled sync's "did anything get played" probe must notice a grade it
has never seen.

Reported: Leederville played Round 1 on Saturday 3 Oct 2026 in six grades and
the Sunday and Monday scheduled syncs both recorded "No fixtures played since
..., nothing to pull". Cricket Australia's match lists held all six fixtures.

Why: ``auto_sync.fixtures_in_window`` decided from the grades OUR database
holds for the in-play season. A club's season row is created the first time a
sync sees it, often in the pre-season when only one team has been placed in a
grade (Leederville's PSWL side, first game 11 Oct). The A to I Grade teams
arrive when the draw is made. The probe then saw one held grade, no fixture in
the window, and answered "nothing played" for ever, while the only code that
seeds a missing grade (the season loop in ``sync_organisation``) never got to
run because the probe was what gated it. The existing guard covered a season
we do not hold and a season held with NO grades, not one held with SOME.

What is checked, through the SHIPPED ``fixtures_in_window`` against a real
Postgres, with only the Cricket Australia calls stubbed:

  · season held with only the PSWL grade, CA lists seven grades, six with a
    fixture in the window  →  sync, reason ``new_grade_to_seed``   (the bug)
  · every grade held, same fixtures                                →  sync, ``fixtures_played``
  · every grade held, window opens after the last fixture          →  no sync, ``no_fixtures_in_window``
    (pairs with the above: the probe can still say "nothing played")
  · teams feed returns nothing (transient)                         →  falls back to the held grades
  · a team whose grade id is not a UUID is ignored, not "new"
  · the grade match list cache expires (control: it used to live for the process)

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/var/run/pgsock\\&port=5439 \\
      python -m verification.verify_probe_new_grade
"""
import asyncio
import os
import sys
import uuid
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

DB = os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@/betterstats_verify?host=/var/run/pgsock&port=5439",
)

PASS = FAIL = 0


def ck(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name} {extra}")


# Leederville's real ids, as read from Cricket Australia on 5 Oct 2026.
ORG = "8694ee57-87d8-eb11-a7ad-2818780da0cc"
SEASON = "69609582-ba37-4440-9d1e-a38fa912f6d3"
PSWL = "7c952853-0000-4000-8000-000000000001"
SIX = {
    "A Grade": "272b38d7-30fd-4728-b25d-8fb582c11805",
    "C Grade": "d7b671c4-0000-4000-8000-000000000002",
    "D Grade": "039d7c6a-0000-4000-8000-000000000003",
    "F Grade": "af41b98d-0000-4000-8000-000000000004",
    "G Grade": "55113bda-0000-4000-8000-000000000005",
    "I Grade": "76d27fa0-0000-4000-8000-000000000006",
}
OTHER_ORG = "9b2cc575-86d8-eb11-a7ad-2818780da0cc"


def _fixture(day: str, status: str = "COMPLETED") -> dict:
    return {
        "id": str(uuid.uuid4()), "status": status,
        "matchSchedule": [{"matchDay": 1, "startDateTime": f"{day}T12:30:00.0000000+08:00"}],
        "teams": [{"owningOrganisation": {"id": OTHER_ORG}},
                  {"owningOrganisation": {"id": ORG}}],
    }


# What the CA grade match lists held on 5 Oct 2026.
MATCH_LISTS = {g: [_fixture("2026-10-03"), _fixture("2026-10-17", "UPCOMING")] for g in SIX.values()}
MATCH_LISTS[PSWL] = [_fixture("2026-10-11", "UPCOMING")]

CA_TEAMS = [{"name": n, "grade": {"id": g, "name": n}, "grades": [{"id": g, "name": n}]}
            for n, g in SIX.items()]
CA_TEAMS.append({"name": "Leederville Cricket Club", "grade": {"id": PSWL, "name": "PSWL North-East B"},
                 "grades": [{"id": PSWL, "name": "PSWL North-East B"}]})


async def seed(engine, grade_guids):
    """A club whose 2026/27 season we hold, with exactly ``grade_guids``."""
    org = uuid.UUID(ORG)
    season_pk = uuid.uuid5(org, SEASON)
    async with engine.begin() as c:
        await c.execute(text("DELETE FROM grades"))
        await c.execute(text("DELETE FROM seasons"))
        await c.execute(text("DELETE FROM organisations"))
        await c.execute(text("INSERT INTO organisations (id, name, is_active) VALUES (:i, 'Leederville CC', true)"),
                        {"i": org})
        await c.execute(text(
            "INSERT INTO seasons (id, organisation_id, grassroots_id, name, year) "
            "VALUES (:i, :o, :g, 'Summer 2026/27', 2026)"), {"i": season_pk, "o": org, "g": SEASON})
        for g in grade_guids:
            await c.execute(text(
                "INSERT INTO grades (id, season_id, grassroots_id, name) VALUES (:i, :s, :g, 'grade')"),
                {"i": uuid.uuid5(org, g), "s": season_pk, "g": g})


async def main():
    from app.models.db import Base
    from app.services import auto_sync, playhq_client
    from app.services import grassroots_scores_client as gr

    engine = create_async_engine(DB)
    async with engine.begin() as c:
        await c.execute(text("DROP SCHEMA public CASCADE"))
        await c.execute(text("CREATE SCHEMA public"))
        await c.run_sync(Base.metadata.create_all)

    teams_calls: list = []
    teams_feed = {"value": CA_TEAMS}

    async def fake_get_seasons(org_id):
        return [
            {"id": SEASON, "name": "Summer 2026/27", "startDate": "2026-07-01T00:00:00.0000000+00:00"},
            {"id": "a826b403-b813-4318-9805-5bbe4cf7f238", "name": "Summer 2025/26",
             "startDate": "2025-07-01T00:00:00.0000000+00:00"},
        ]

    async def fake_get_teams(org_id, season_id):
        teams_calls.append(season_id)
        return teams_feed["value"]

    async def fake_get_grade_matches(grade_id, *, force=False):
        return MATCH_LISTS.get(grade_id, [])

    playhq_client.get_seasons = fake_get_seasons
    playhq_client.get_teams = fake_get_teams
    gr.get_grade_matches = fake_get_grade_matches

    since, now = date(2026, 10, 2), date(2026, 10, 4)

    # 1. The reported club: season held with only the PSWL grade.
    await seed(engine, [PSWL])
    r = await auto_sync.fixtures_in_window(ORG, since, now)
    ck("held season with only the PSWL grade: probe says sync", r.get("sync") is True, str(r))
    ck("  ...and names the reason new_grade_to_seed", r.get("reason") == "new_grade_to_seed", str(r))

    # 2. Everything held: the ordinary case still finds the fixtures.
    await seed(engine, [PSWL, *SIX.values()])
    r = await auto_sync.fixtures_in_window(ORG, since, now)
    ck("every grade held: fixtures_played", r.get("sync") is True and r.get("reason") == "fixtures_played"
       and r.get("fixtures") == 6, str(r))

    # 3. Pair: the probe can still answer "nothing played".
    r = await auto_sync.fixtures_in_window(ORG, date(2026, 10, 4), now)
    ck("every grade held, window after the last fixture: no sync",
       r.get("sync") is False and r.get("reason") == "no_fixtures_in_window", str(r))

    # 4. Teams feed returns nothing (transient): cannot tell, falls back to held grades.
    teams_feed["value"] = []
    await seed(engine, [PSWL])
    r = await auto_sync.fixtures_in_window(ORG, since, now)
    ck("teams feed empty: falls back to held grades (cannot tell)",
       r.get("sync") is False and r.get("reason") == "no_fixtures_in_window", str(r))

    # 5. A team whose grade id is not a UUID is not a grade we could ever seed.
    teams_feed["value"] = [{"name": "odd", "grade": {"id": "not-a-uuid", "name": "Odd"}}]
    await seed(engine, [PSWL])
    r = await auto_sync.fixtures_in_window(ORG, since, now)
    ck("non-UUID grade id is ignored, not read as new",
       r.get("sync") is False and r.get("reason") == "no_fixtures_in_window", str(r))

    # 6. No extra call when the season has no grades at all (already syncs).
    teams_feed["value"] = CA_TEAMS
    teams_calls.clear()
    await seed(engine, [])
    r = await auto_sync.fixtures_in_window(ORG, since, now)
    ck("season held with no grades still syncs", r.get("sync") is True
       and r.get("reason") == "no_grades_seeded_yet", str(r))
    ck("  ...without asking CA for teams", teams_calls == [], str(teams_calls))

    # 7. The grade match list cache expires. Real function, stubbed HTTP.
    import importlib
    importlib.reload(gr)
    served = []

    class _Resp:
        status_code = 200

        def __init__(self, n):
            self._n = n

        def json(self):
            return {"matches": [{"id": f"m{self._n}"}]}

    async def fake_http_get(url, params=None):
        served.append(url)
        return _Resp(len(served))

    gr._get = fake_http_get
    clock = {"t": 1000.0}
    real_time = gr.time.time
    gr.time.time = lambda: clock["t"]
    try:
        a = await gr.get_grade_matches("g1")
        b = await gr.get_grade_matches("g1")
        ck("second call inside the window is served from cache", len(served) == 1 and a == b, str(served))
        clock["t"] += getattr(gr, "_GRADE_MATCHES_TTL", 10 ** 9) + 1
        c = await gr.get_grade_matches("g1")
        ck("call after the TTL fetches again", len(served) == 2 and c != a, f"served={len(served)}")
        d = await gr.get_grade_matches("g1", force=True)
        ck("force=True still bypasses the cache", len(served) == 3 and d != c, f"served={len(served)}")
    finally:
        gr.time.time = real_time

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
