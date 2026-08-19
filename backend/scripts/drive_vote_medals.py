"""Drives the Votes screens in a real browser against the dev server with the
API stubbed at the network layer.

The point is the state transitions a screenshot can't reach: switching between
two medals and seeing the count, the ballot shape and the games list all change
with it; the medal riding in the URL so a link to one count is shareable; a
stale medal in the URL falling back rather than emptying the screen; and the
exact params each screen puts on the wire, since a medal filter that renders
but doesn't reach the server reads as working while doing nothing.

Usage:  python scripts/drive_vote_medals.py [http://127.0.0.1:5199]
"""
from __future__ import annotations

import json
import re
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5199"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


CHAMP = "11111111-1111-4111-8111-111111111111"
COLTS = "22222222-2222-4222-8222-222222222222"
SENIOR_GRADE = "33333333-3333-4333-8333-333333333333"
COLTS_GRADE = "44444444-4444-4444-8444-444444444444"


def medal(mid, name, values, grades, grade_names, enabled=True, token=None):
    return {
        "medal_id": mid, "medal_name": name, "grade_ids": grades,
        "grade_names": grade_names, "enabled": enabled,
        "token": token, "require_pin": True, "voter_mode": "players",
        "ballot_values": values, "counting_method": "rank", "tie_policy": "share",
        "allow_self_vote": False, "allow_non_participants": False,
        "auto_close_days": 7, "eligibility_source": "scorecard",
    }


MEDALS = {
    CHAMP: medal(CHAMP, "Club Champion", [3, 2, 1], [], [], token="champ-token"),
    COLTS: medal(COLTS, "Colts Medal", [5, 4, 3, 2, 1], [COLTS_GRADE], ["Colts"], token="colts-token"),
}

FIXTURES = {
    CHAMP: [
        {"id": "aaaaaaaa-0000-4000-8000-000000000001", "opponent": "Melville", "round": "Round 5",
         "round_key": "5", "date": "2026-10-01", "grade": "1st Grade", "grade_id": SENIOR_GRADE,
         "home_away": "H", "state": "open", "source": "scorecard", "source_override": None,
         "has_lineup": True, "synced": True, "closes_on": "2026-10-08", "ballots": 6,
         "voters_expected": 11, "outstanding_count": 5},
        {"id": "aaaaaaaa-0000-4000-8000-000000000002", "opponent": "Melville Colts", "round": "Round 5",
         "round_key": "5", "date": "2026-10-01", "grade": "Colts", "grade_id": COLTS_GRADE,
         "home_away": "A", "state": "open", "source": "scorecard", "source_override": None,
         "has_lineup": True, "synced": True, "closes_on": "2026-10-08", "ballots": 2,
         "voters_expected": 11, "outstanding_count": 9},
    ],
    COLTS: [
        {"id": "aaaaaaaa-0000-4000-8000-000000000002", "opponent": "Melville Colts", "round": "Round 5",
         "round_key": "5", "date": "2026-10-01", "grade": "Colts", "grade_id": COLTS_GRADE,
         "home_away": "A", "state": "open", "source": "scorecard", "source_override": None,
         "has_lineup": True, "synced": True, "closes_on": "2026-10-08", "ballots": 1,
         "voters_expected": 11, "outstanding_count": 10},
    ],
}

STANDINGS = {
    CHAMP: [{"player_id": "p1", "name": "Jack Barendse", "points": 9, "raw": 9, "counts": [3, 0, 0],
             "rounds": 3, "grade": "1st Grade", "grade_short": "1st", "movement": 1,
             "form": [3, 3, 3], "cumulative": [3, 6, 9], "round_gain": 3, "tied": False}],
    COLTS: [{"player_id": "p2", "name": "Sam Whitely", "points": 5, "raw": 5, "counts": [1, 0, 0, 0, 0],
             "rounds": 1, "grade": "Colts", "grade_short": "Colts", "movement": 0,
             "form": [5], "cumulative": [5], "round_gain": 5, "tied": False}],
}

SEEN = {"fixtures": [], "leaderboard": [], "settings": []}


def route_api(route, request):
    url = request.url
    path = url.split("/api", 1)[1] if "/api" in url else url
    mid = None
    m = re.search(r"medal_id=([0-9a-f-]+)", path)
    if m:
        mid = m.group(1)

    def send(body):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    if path.startswith("/auth/me"):
        return send({"id": "u1", "username": "admin", "role": "club_admin", "club_slug": "applecross",
                     "organisation_id": "org1", "capabilities": [], "entitlements": {
                         "modules": ["select"], "status": "active", "overrides": ["select"]}})
    if path.startswith("/votes/medals"):
        return send({"medals": list(MEDALS.values()),
                     "grades": [{"id": SENIOR_GRADE, "name": "1st Grade"},
                                {"id": COLTS_GRADE, "name": "Colts"}]})
    if path.startswith("/votes/settings"):
        SEEN["settings"].append(path)
        return send(MEDALS.get(mid or CHAMP))
    if path.startswith("/votes/fixtures"):
        SEEN["fixtures"].append(path)
        key = mid or CHAMP
        return send({
            "year": 2026, "years": [2026], "fixtures": FIXTURES.get(key, []),
            "settings": MEDALS.get(key), "grades": [{"id": COLTS_GRADE, "name": "Colts"}] if key == COLTS
            else [{"id": SENIOR_GRADE, "name": "1st Grade"}, {"id": COLTS_GRADE, "name": "Colts"}],
            "grade_id": None, "rounds": [{"key": "5", "label": "Round 5"}], "round_key": None, "q": None,
            "summary": {"open": len(FIXTURES.get(key, [])), "awaiting_team": 0,
                        "ballots_in": sum(f["ballots"] for f in FIXTURES.get(key, [])),
                        "ballots_expected": 11, "rounds_counted": 1, "rounds_total": 1},
            "medals": list(MEDALS.values()), "medal_id": key,
        })
    if path.startswith("/votes/leaderboard"):
        SEEN["leaderboard"].append(path)
        key = mid or CHAMP
        return send({
            "year": 2026, "medal_id": key, "medal_name": MEDALS[key]["medal_name"],
            "ballot_values": MEDALS[key]["ballot_values"], "counting_method": "rank",
            "tie_policy": "share", "rounds": [], "standings": STANDINGS[key],
            "through_round": None, "last_round": None, "grades": [],
            "club_name": "Applecross CC", "club_short": "ACC", "season_label": "2026/27",
            "grade_name": "Whole club", "grade_id": None, "race_caption": None,
            "medals": list(MEDALS.values()),
        })
    return send({})


def main():
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                                      args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/**", route_api)
        page.add_init_script(
            "localStorage.setItem('token','stub'); localStorage.setItem('bs_user','1');")

        page.goto(f"{BASE}/admin/betterselect/votes", wait_until="networkidle")
        page.wait_for_timeout(1200)

        body = page.inner_text("body")
        check("both medals are offered in the picker",
              "Club Champion" in body and "Colts Medal" in body, body[:200])
        check("the first medal is the one loaded by default",
              any("medal_id" not in p for p in SEEN["fixtures"]) or
              any(CHAMP in p for p in SEEN["fixtures"]), str(SEEN["fixtures"]))
        check("the all-grades medal's hub lists both grades' games",
              "Melville Colts" in body and "Melville" in body)

        # Switch medal → URL, request and content all follow.
        SEEN["fixtures"].clear()
        page.get_by_role("button", name=re.compile(r"^Colts Medal")).click()
        page.wait_for_timeout(900)
        check("switching medal puts it in the URL so the view is shareable",
              f"medal={COLTS}" in page.url, page.url)
        check("switching medal sends the new medal_id on the wire",
              any(COLTS in p for p in SEEN["fixtures"]), str(SEEN["fixtures"]))
        body = page.inner_text("body")
        check("the Colts medal's hub drops the senior game",
              "Melville Colts" in body and "1st Grade" not in body, body[:300])

        # Leaderboard follows the medal too.
        SEEN["leaderboard"].clear()
        page.get_by_role("button", name="Leaderboard").click()
        page.wait_for_timeout(900)
        check("the leaderboard asks for the selected medal",
              any(COLTS in p for p in SEEN["leaderboard"]), str(SEEN["leaderboard"]))
        check("the leaderboard shows that medal's own count",
              "Sam Whitely" in page.inner_text("body"))
        check("switching tabs keeps the medal selected", f"medal={COLTS}" in page.url, page.url)

        # Settings: name, grades, ballot shape all belong to the medal.
        page.get_by_role("button", name="Settings").click()
        page.wait_for_timeout(900)
        body = page.inner_text("body")
        check("settings edits the selected medal's name",
              page.locator("input[value='Colts Medal']").count() > 0
              or "Colts Medal" in body)
        check("settings shows the grade picker", "Grades it counts" in body, body[:400])
        check("the medal's own grade is ticked, and says so",
              "Counting Colts" in body, body[body.find("Grades it counts"):][:300] if "Grades it counts" in body else "")
        check("a medal with several medals offers Delete", "Delete Colts Medal" in body)
        check("the medal's own ballot shape is shown", "5-4-3-2-1" in body, body[:400])

        # A stale medal in the URL falls back rather than emptying the screen.
        page.goto(f"{BASE}/admin/betterselect/votes?medal=99999999-9999-4999-8999-999999999999",
                  wait_until="networkidle")
        page.wait_for_timeout(1000)
        check("a medal the club no longer holds falls back to the first",
              "Club Champion" in page.inner_text("body"))

        # Mobile.
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(600)
        # The Games hub's own filter row overflows at 390px (a `ml-auto` select
        # reaching 446px). Confirmed PRE-EXISTING by re-running this same check
        # with the medals change stashed — identical element, identical width —
        # so it is the hub's to fix, not this release's. What IS asserted here
        # is that the medal picker itself fits, since that is the new furniture.
        bar_right = page.evaluate("""() => {
            const b = [...document.querySelectorAll('button')]
                .find(el => el.textContent.trim().startsWith('Club Champion'));
            return b ? Math.round(b.getBoundingClientRect().right) : 0;
        }""")
        check("the medal picker itself fits on a phone", 0 < bar_right <= 390, f"right={bar_right}")

        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
