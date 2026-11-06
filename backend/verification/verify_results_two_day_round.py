"""A two-day game belongs to the weekend it finished, on the Results post.

Reported (North Perth, November 2026): "When I fetch the latest round results it leaves
out 3rd grade. If I fetch from that game it reverts the other games to the previous round
and removes 1st grade."

A two-day game has one `matchSchedule` entry per day, a week apart, in NO reliable order.
The results pull read `matchSchedule[0]`, so 1st grade (entries Oct 31, Oct 24) was filed
under Oct 31 and 3rd grade (Oct 24, Oct 31) under Oct 24, both "Round 3". A pasted link on
the 3rd grade game anchored on Oct 24, and the plus or minus 3 day window dropped 1st grade
and pulled in the previous week's one-day games.

Pure: the Cricket Australia calls and the grade lookups are stubbed, no database.

  latest    the newest weekend holds 1st AND 3rd grade with the one-day grades that finished it
  previous  the weekend before holds only its own one-day games, not a two-day game
  link      a pasted 3rd grade link gives the same set as `latest`, in the same weekend
  link_1st  a pasted 1st grade link (entries the other way round) gives the same set
  control   a one-day game is unmoved, and a two-day game with ONE entry still files
  fixtures  a pasted FIXTURES link still anchors on the first day of a two-day game

Run:  python verification/verify_results_two_day_round.py
The control run is the same script against the previous commit: `latest`, `previous`
and `link` fail (3rd grade under Oct 24, 1st grade missing from a link on 3rd).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from app.services import grassroots_scores_client as gr
from app.services import social_rounds as sr

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"PASS {label}")
    else:
        FAIL += 1
        print(f"FAIL {label} {detail}")


ORG_ID = str(uuid.uuid4())
ORG = SimpleNamespace(
    id=ORG_ID, name="North Perth Cricket Club", short_name="North Perth",
    playhq_id=None, logo_url=None, logo_data=None,
)
OTHER = "11111111-2222-3333-4444-555555555555"

G1, G3, OD3, OD4 = (str(uuid.uuid4()) for _ in range(4))
GRADE_NAMES = {G1: "1st Grade", G3: "3rd Grade", OD3: "One Day Grade 3", OD4: "One Day Grade 4"}


def _mid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


def match(n: int, grade: str, rnd: str, days: list[str], status: int = 3) -> dict:
    return {
        "id": _mid(n),
        "statusId": status,
        "round": {"name": rnd},
        "grade": {"id": grade},
        "venue": {"name": "Ground"},
        "matchType": "Two Day" if len(days) > 1 else "One Day",
        "matchSchedule": [{"startDateTime": f"{d}T10:00:00"} for d in days],
        "teams": [
            {"isHome": True, "displayName": "North Perth", "owningOrganisation": {"id": ORG_ID}},
            {"isHome": False, "displayName": "Opposition", "owningOrganisation": {"id": OTHER}},
        ],
    }


MATCHES = {
    # Two-day games, both Round 3, played Oct 24 and Oct 31. The entries come back in
    # opposite orders, which is what scattered them.
    G1: [match(1, G1, "Round 3", ["2026-10-31", "2026-10-24"])],
    G3: [match(3, G3, "Round 3", ["2026-10-24", "2026-10-31"])],
    # One-day grades: Round 2 on Oct 24, Round 3 on Oct 31.
    OD3: [match(5, OD3, "Round 3", ["2026-10-31"]), match(6, OD3, "Round 2", ["2026-10-24"])],
    OD4: [match(7, OD4, "Round 3", ["2026-10-31"]), match(8, OD4, "Round 2", ["2026-10-24"])],
}
BY_ID = {m["id"]: m for lst in MATCHES.values() for m in lst}


async def fake_grade_matches(guid, *a, **k):
    return MATCHES.get(guid, [])


async def fake_match_detail(mid):
    return BY_ID.get(mid)


async def fake_scorecard(mid, force=False):
    return {"id": mid}


async def fake_grade_rows(db, org_id):
    return [(g, uuid.uuid4(), n, "2026/27") for g, n in GRADE_NAMES.items()]


async def fake_grade_season(db, org_id, guid):
    return (uuid.uuid4(), "2026/27") if guid in GRADE_NAMES else None


async def fake_season_rows(db, org_id, season_id):
    return [(g, uuid.uuid4(), n, "2026/27") for g, n in GRADE_NAMES.items()]


async def fake_orders(db, org_id):
    return {G1: 1, G3: 3, OD3: 5, OD4: 6}


async def fake_cats(db, org_id):
    return lambda name: ["senior"]


async def fake_finalize(db, rows):
    return None


def fake_row(sc, org, keys, grade_name, grade_order=None, live=False):
    return {"grade": (grade_name or "").upper(), "id": sc.get("id")}


gr.get_grade_matches = fake_grade_matches
gr.get_match_detail = fake_match_detail
gr.get_match_scorecard = fake_scorecard
sr.current_grade_rows_with_live = fake_grade_rows
sr._grade_season = fake_grade_season
sr._grade_rows_for_season = fake_season_rows
sr._grade_display_orders = fake_orders
sr._category_lookup = fake_cats
sr._finalize_opp_logos = fake_finalize
sr._result_row = fake_row

# The window the no-argument pull looks back over is "today minus N days"; pin it so the
# October fixtures are inside it whenever this runs.
class _Date(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 2)


sr.date = _Date


def grades_of(bucket: dict | None, key: str = "results") -> set[str]:
    return {r["grade"] for r in (bucket or {}).get(key, [])}


def bucket_for(dates: list[dict], day: str) -> dict | None:
    return next((d for d in dates if d.get("date") == day), None)


async def main() -> None:
    latest = await sr.social_results(None, ORG)
    dates = latest["dates"]
    newest = dates[0] if dates else {}
    check("latest: newest weekend is Oct 31", newest.get("date") == "2026-10-31", str(newest.get("date")))
    got = grades_of(newest)
    check("latest: 3rd grade is in the latest round", "3RD GRADE" in got, str(sorted(got)))
    check("latest: 1st grade is in the latest round", "1ST GRADE" in got, str(sorted(got)))
    check(
        "latest: the one-day grades that finished that weekend are there too",
        {"ONE DAY GRADE 3", "ONE DAY GRADE 4"} <= got, str(sorted(got)),
    )
    prev = bucket_for(dates, "2026-10-24")
    prev_got = grades_of(prev)
    check("previous: the weekend before has its one-day games", {"ONE DAY GRADE 3", "ONE DAY GRADE 4"} <= prev_got, str(sorted(prev_got)))
    check("previous: no two-day game is filed under the week it started", not (prev_got & {"1ST GRADE", "3RD GRADE"}), str(sorted(prev_got)))
    ids = [r["id"] for d in dates for r in d["results"]]
    check("latest: each game appears once", len(ids) == len(set(ids)) == 6, str(len(ids)))

    for label, anchor in (("link", _mid(3)), ("link_1st", _mid(1))):
        res = await sr.social_results_for_reference(None, ORG, anchor)
        bucket = (res.get("dates") or [{}])[0]
        got = grades_of(bucket)
        check(f"{label}: weekend is Oct 31", bucket.get("date") == "2026-10-31", str(bucket.get("date")))
        check(
            f"{label}: 1st and 3rd grade plus both one-day grades",
            got == {"1ST GRADE", "3RD GRADE", "ONE DAY GRADE 3", "ONE DAY GRADE 4"}, str(sorted(got)),
        )
        check(f"{label}: the previous week's one-day games stay out", len(bucket.get("results", [])) == 4, str(len(bucket.get("results", []))))

    # control: nothing that was right has moved
    one_day = gr.schedule_days(MATCHES[OD3][0])
    check("control: a one-day game is on its own day", one_day and one_day[0][0] == "2026-10-31")
    res = await gr.get_grade_results(OD3)
    check("control: one-day played_at unchanged", {r["played_at"] for r in res} == {"2026-10-31", "2026-10-24"}, str(res))
    res = await gr.get_grade_results(G1)
    check("control: a two-day result is dated its last day and keeps its first", res and res[0]["played_at"] == "2026-10-31" and res[0].get("starts_at") == "2026-10-24", str(res))
    check("control: a game with no schedule is skipped, not a crash", await _no_schedule_ok())

    fx = await sr.social_fixtures_for_reference(None, ORG, _mid(3))
    fb = (fx.get("dates") or [{}])[0]
    check("fixtures: a pasted link on a two-day game anchors on its first day", fb.get("date") == "2026-10-24", str(fb.get("date")))
    check("fixtures: 1st and 3rd grade are both in the round", {"1ST GRADE", "3RD GRADE"} <= grades_of(fb, "fixtures"), str(sorted(grades_of(fb, "fixtures"))))

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


async def _no_schedule_ok() -> bool:
    bye = match(9, G1, "Round 4", [])
    MATCHES["bye"] = [bye]
    try:
        return await gr.get_grade_results("bye") == []
    finally:
        MATCHES.pop("bye", None)


asyncio.run(main())
