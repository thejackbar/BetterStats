"""Drives the Votes Settings tab in a real browser with the API stubbed at the
network layer: a team set to Chosen people gets a list of people to add to and
remove from, each change puts the exact body on the wire, other modes have no
list, and nothing overflows at 390px. Also drives the public ballot page for a
chosen person who was not in the side.

Usage:  python scripts/drive_vote_chosen_voters.py [http://127.0.0.1:5199] [screenshot_dir]
"""
from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5199"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else None

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


MID = "11111111-1111-4111-8111-111111111111"
FIRSTS, COLTS = "33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444"
HELPER, JOE, PAT = "77777777-7777-4777-8777-777777777777", "88888888-8888-4888-8888-888888888888", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
FX = "99999999-9999-4999-8999-999999999999"
GRADES = [{"id": FIRSTS, "name": "1st Grade"}, {"id": COLTS, "name": "Colts"}]
PEOPLE = [{"id": HELPER, "name": "Helen Helper"}, {"id": PAT, "name": "Pat Panel"}, {"id": JOE, "name": "Regular Joe"}]

STATE = {
    "medal_id": MID, "medal_name": "Club Champion", "grade_ids": [], "grade_names": [], "inactive_grades": [],
    "grade_voter_modes": {"1st Grade": "captain"}, "grade_vote_counters": {}, "vote_chosen": {},
    "enabled": True, "token": "champ-token", "require_pin": True,
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
    if "/weighting" in path:
        return send({"year": 2026, "season_label": "2026/27", "mode": "off", "top_grade": None,
                     "ballot_values": [3, 2, 1], "rows": []})
    if path.startswith("/votes/voter-options"):
        return send({"players": PEOPLE})
    if path.startswith("/votes/medals"):
        return send({"medals": [STATE], "grades": GRADES})
    if path.startswith("/votes/settings"):
        if request.method == "POST":
            body = json.loads(request.post_data or "{}")
            POSTS.append(body)
            if "grade_voter_modes" in body:
                STATE["grade_voter_modes"] = body["grade_voter_modes"]
            if "grade_vote_counters" in body:
                STATE["grade_vote_counters"] = body["grade_vote_counters"]
                STATE["vote_chosen"] = {
                    t: [{"id": pid, "name": next(p["name"] for p in PEOPLE if p["id"] == pid)} for pid in ids]
                    for t, ids in body["grade_vote_counters"].items()}
        return send(STATE)
    if path.startswith("/votes/fixtures"):
        return send({"year": 2026, "years": [2026], "fixtures": [], "settings": STATE,
                     "grades": [], "grade_id": None, "rounds": [], "round_key": None, "q": None,
                     "summary": {"open": 0, "awaiting_team": 0, "ballots_in": 0, "ballots_expected": 0,
                                 "rounds_total": 0, "rounds_counted": 0},
                     "medals": [STATE], "medal_id": MID})
    return send({})


CLUB = {"name": "Applecross CC", "short_name": "ACC", "slug": "applecross", "logo_url": None,
        "primary_color": "#0a7", "accent_color": "#07a"}
PUBLIC_POSTS = []


def route_public(route, request):
    path = request.url.split("/api/public/votes", 1)[1]

    def send(body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    if request.method == "POST" and path.endswith("/ballot"):
        PUBLIC_POSTS.append(json.loads(request.post_data or "{}"))
        return send({"status": "ok"})
    me = {"id": HELPER, "display_name": "Helen Helper"}
    if "/fixtures/" in path:
        return send({
            "club": CLUB, "fixture": {"id": FX, "opponent": "Melville", "round": "Round 5", "date": "2026-10-17", "state": "open"},
            "ballot_values": [3, 2, 1], "allow_self_vote": False, "voter_mode": "captain", "me": me,
            "role": "player", "reason": None, "is_chosen": True,
            "players": [{"id": JOE, "name": "Regular Joe", "photo_url": None},
                        {"id": "a1", "name": "Sam Side", "photo_url": None},
                        {"id": "a2", "name": "Captain Cook", "photo_url": None}],
            "my_ballot": None})
    return send({
        "club": CLUB, "medal": {"id": MID, "name": "Club Champion"}, "require_pin": True, "voter_mode": "captain",
        "allow_non_participants": False, "allow_self_vote": False, "ballot_values": [3, 2, 1], "me": me,
        "players": [{"id": HELPER, "display_name": "Helen Helper", "has_phone": True}],
        "grades": [], "rounds": [], "team": None, "round_key": None, "q": None,
        "fixtures": [{"id": FX, "opponent": "Melville", "round": "Round 5", "round_key": "5", "date": "2026-10-17",
                      "home_away": "H", "state": "open", "voted": False}]})


def main():
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                                      args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 1100})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/public/votes/**", route_public)
        page.route(lambda u: "/api/" in u and "/api/public/votes" not in u, route_api)
        page.add_init_script("localStorage.setItem('token','stub'); localStorage.setItem('bs_user','1');")

        page.goto(f"{BASE}/admin/betterselect/votes?tab=settings&medal={MID}", wait_until="domcontentloaded")
        page.wait_for_selector("text=Who votes, by team", timeout=15000)
        page.wait_for_timeout(500)

        team_select = lambda: [x for x in page.locator("select").all() if "Default (" in x.inner_text()][0]
        add_sel = lambda: page.locator("select[aria-label^='Add a person to vote for']")
        check("a team on Captain only has no list of people", add_sel().count() == 0)
        modes = team_select().locator("option").all_inner_texts()
        check("the team picker offers Chosen people alongside the others",
              modes == ["Default (All players)", "All players", "Captain only", "Chosen people"], str(modes))

        POSTS.clear()
        team_select().select_option("chosen")
        page.wait_for_timeout(500)
        check("choosing Chosen people sends the team's mode by name",
              POSTS == [{"grade_voter_modes": {"1st Grade": "chosen"}}], str(POSTS))
        check("with nobody chosen it says so",
              "Nobody is chosen yet, so nobody can vote for this team." in page.inner_text("body"))
        opts = add_sel().first.locator("option").all_inner_texts()
        check("it offers the club's players, not only who played",
              opts == ["Add a person…", "Helen Helper", "Pat Panel", "Regular Joe"], str(opts))

        POSTS.clear()
        add_sel().first.select_option(HELPER)
        page.wait_for_timeout(500)
        check("adding a person sends the team's whole list",
              POSTS == [{"grade_vote_counters": {"1st Grade": [HELPER]}}], str(POSTS))
        POSTS.clear()
        add_sel().first.select_option(JOE)
        page.wait_for_timeout(500)
        check("adding a second person keeps the first, in order",
              POSTS == [{"grade_vote_counters": {"1st Grade": [HELPER, JOE]}}], str(POSTS))
        body = page.inner_text("body")
        check("both people are shown and the warning is gone",
              "Helen Helper" in body and "Regular Joe" in body and "Nobody is chosen yet" not in body)
        opts = add_sel().first.locator("option").all_inner_texts()
        check("a person already chosen is no longer offered", opts == ["Add a person…", "Pat Panel"], str(opts))

        POSTS.clear()
        page.get_by_role("button", name="Remove Helen Helper from 1st Grade").click()
        page.wait_for_timeout(500)
        check("removing a person sends the list without them",
              POSTS == [{"grade_vote_counters": {"1st Grade": [JOE]}}], str(POSTS))

        POSTS.clear()
        team_select().select_option("players")
        page.wait_for_timeout(500)
        check("a team switched to All players no longer shows the list", add_sel().count() == 0)
        check("switching mode sends only the mode (the list stays stored)",
              POSTS == [{"grade_voter_modes": {"1st Grade": "players"}}], str(POSTS))
        team_select().select_option("chosen")
        page.wait_for_timeout(500)
        check("switching back finds the person still chosen", "Regular Joe" in page.inner_text("body"))
        page.get_by_role("button", name="Remove Regular Joe from 1st Grade").click()
        page.wait_for_timeout(500)
        add_sel().first.select_option(HELPER)
        page.wait_for_timeout(500)
        add_sel().first.select_option(PAT)
        page.wait_for_timeout(500)

        if SHOTS:
            page.screenshot(path=f"{SHOTS}/chosen-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(300)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("no horizontal overflow at 390px", overflow <= 0, str(overflow))
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/chosen-390.png", full_page=True)

        # Public ballot page for the nominated person.
        page.set_viewport_size({"width": 390, "height": 900})
        page.goto(f"{BASE}/vote/champ-token?fixture={FX}", wait_until="domcontentloaded")
        page.wait_for_selector("text=Round 5", timeout=15000)
        page.wait_for_timeout(500)
        body = page.inner_text("body")
        check("the ballot page tells a chosen person they are one of those voting for the team",
              "You are one of the people chosen to vote for this team." in body, body[:300])
        check("the ballot lists the team", "Regular Joe" in body and "Sam Side" in body)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("no horizontal overflow on the ballot at 390px", overflow <= 0, str(overflow))
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/chosen-ballot-390.png", full_page=True)

        check("no page errors", not errors, str(errors))
        browser.close()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


main()
