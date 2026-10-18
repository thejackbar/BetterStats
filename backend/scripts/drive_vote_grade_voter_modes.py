"""Drives the Votes Settings tab in a real browser with the API stubbed at the
network layer: the grade picker shows only the grades on offer from the server,
a ticked grade that is no longer played is shown apart and can be removed, and a
voter mode can be set per team. Asserts the exact body each change puts on the
wire, and that nothing overflows at 390px.

Usage:  python scripts/drive_vote_grade_voter_modes.py [http://127.0.0.1:5199] [screenshot_dir]
"""
from __future__ import annotations

import json
import re
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5199"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else None

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


MID = "11111111-1111-4111-8111-111111111111"
FIRSTS, COLTS, U12, LADIES = (
    "33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444",
    "55555555-5555-4555-8555-555555555555", "66666666-6666-4666-8666-666666666666",
)
GRADES = [{"id": FIRSTS, "name": "1st Grade"}, {"id": COLTS, "name": "Colts"}, {"id": U12, "name": "Under 12"}]

STATE = {
    "medal_id": MID, "medal_name": "Club Champion", "grade_ids": [FIRSTS, LADIES],
    "grade_names": ["1st Grade", "Old Ladies"], "inactive_grades": [{"id": LADIES, "name": "Old Ladies"}],
    "grade_voter_modes": {}, "enabled": True, "token": "champ-token", "require_pin": True,
    "voter_mode": "players", "ballot_values": [3, 2, 1], "counting_method": "rank", "tie_policy": "share",
    "allow_self_vote": False, "allow_non_participants": False, "auto_close_days": 7,
    "eligibility_source": "scorecard",
}
POSTS = []


def route_api(route, request):
    path = request.url.split("/api", 1)[1] if "/api" in request.url else request.url

    def send(body):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    if path.startswith("/auth/me"):
        return send({"id": "u1", "username": "admin", "role": "club_admin", "club_slug": "applecross",
                     "organisation_id": "org1", "capabilities": [], "entitlements": {
                         "modules": ["select"], "status": "active", "overrides": ["select"]}})
    if path.startswith("/votes/medals"):
        return send({"medals": [STATE], "grades": GRADES})
    if path.startswith("/votes/settings"):
        if request.method == "POST":
            body = json.loads(request.post_data or "{}")
            POSTS.append(body)
            by_id = {g["id"]: g["name"] for g in GRADES + [{"id": LADIES, "name": "Old Ladies"}]}
            if "grade_ids" in body:
                STATE["grade_ids"] = body["grade_ids"]
                names = []
                for gid in body["grade_ids"]:
                    if by_id[gid] not in names:
                        names.append(by_id[gid])
                STATE["grade_names"] = names
                STATE["inactive_grades"] = [{"id": g, "name": by_id[g]} for g in body["grade_ids"] if g == LADIES]
            if "grade_voter_modes" in body:
                STATE["grade_voter_modes"] = body["grade_voter_modes"]
        return send(STATE)
    if path.startswith("/votes/fixtures"):
        return send({"year": 2026, "years": [2026], "fixtures": [], "settings": STATE,
                     "grades": [], "grade_id": None, "rounds": [], "round_key": None, "q": None,
                     "summary": {"open": 0, "awaiting_team": 0, "ballots_in": 0, "ballots_expected": 0,
                                 "rounds_counted": 0, "rounds_total": 0},
                     "medals": [STATE], "medal_id": MID})
    return send({})


def main():
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                                      args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 1100})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/**", route_api)
        page.add_init_script("localStorage.setItem('token','stub'); localStorage.setItem('bs_user','1');")

        page.goto(f"{BASE}/admin/betterselect/votes?tab=settings&medal={MID}", wait_until="domcontentloaded")
        page.wait_for_selector("text=Grades it counts", timeout=15000)
        page.wait_for_timeout(500)

        chips = page.locator("div.flex.flex-wrap.gap-1\\.5 > button").all_inner_texts()
        check("the picker lists the three grades on offer",
              all(n in chips for n in ("1st Grade", "Colts", "Under 12")), str(chips))
        check("a grade that is no longer played is not in the picker",
              "Old Ladies" not in [c.strip() for c in chips], str(chips))
        body = page.inner_text("body")
        check("the still-ticked inactive grade is shown apart, with a way to remove it",
              "Still ticked, but not played this season" in body and "Old Ladies ✕" in body, body[:300])

        # Per-team rows follow the ticked grades (1st Grade only), not every team.
        check("Who votes, by team appears", "Who votes, by team" in page.inner_text("body").replace("WHO VOTES, BY TEAM", "Who votes, by team"))
        selects = page.locator("select").all()
        team_selects = [s for s in selects if "Club default" in s.inner_text() or "Default (" in s.inner_text()]
        check("only the ticked team gets a row", len(team_selects) == 1, str(len(team_selects)))

        POSTS.clear()
        team_selects[0].select_option("captain")
        page.wait_for_timeout(500)
        check("choosing Captain only sends the team's mode by name",
              POSTS and POSTS[-1] == {"grade_voter_modes": {"1st Grade": "captain"}}, str(POSTS))
        check("the row reflects the saved choice",
              page.locator("select").nth(0).count() >= 1 and
              "captain" in [s.input_value() for s in page.locator("select").all()], "")

        POSTS.clear()
        team_selects = [s for s in page.locator("select").all() if s.input_value() == "captain"]
        team_selects[0].select_option("default")
        page.wait_for_timeout(500)
        check("going back to Default removes the team's entry",
              POSTS and POSTS[-1] == {"grade_voter_modes": {}}, str(POSTS))

        # Ticking another grade adds a row, and keeps the inactive id on the wire.
        POSTS.clear()
        page.get_by_role("button", name="Colts", exact=True).click()
        page.wait_for_timeout(500)
        check("ticking a grade keeps the inactive grade ticked until removed",
              POSTS and set(POSTS[-1]["grade_ids"]) == {FIRSTS, COLTS, LADIES}, str(POSTS))
        check("the new team gets its own row",
              len([s for s in page.locator("select").all() if "Default (" in s.inner_text()]) == 2)

        # Removing the inactive grade.
        POSTS.clear()
        page.get_by_role("button", name=re.compile(r"Old Ladies")).click()
        page.wait_for_timeout(500)
        check("removing the inactive grade sends the remaining ids only",
              POSTS and set(POSTS[-1]["grade_ids"]) == {FIRSTS, COLTS}, str(POSTS))
        check("the inactive block is gone", "Still ticked, but not played" not in page.inner_text("body"))

        if SHOTS:
            page.screenshot(path=f"{SHOTS}/settings-desktop.png", full_page=True)

        # 390px
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(300)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("no horizontal overflow at 390px", overflow <= 0, str(overflow))
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/settings-390.png", full_page=True)

        check("no page errors", not errors, str(errors))
        browser.close()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


main()
