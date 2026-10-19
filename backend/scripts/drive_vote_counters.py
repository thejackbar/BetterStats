"""Drives the Votes Settings tab in a real browser with the API stubbed at the
network layer: a team set to Captain only gets a "Votes counted by" picker, the
choice puts the exact body on the wire, a team on All players has no picker, and
nothing overflows at 390px. Also drives the public ballot page for the nominated
person, who was not in the side.

Usage:  python scripts/drive_vote_counters.py [http://127.0.0.1:5199] [screenshot_dir]
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
HELPER, JOE = "77777777-7777-4777-8777-777777777777", "88888888-8888-4888-8888-888888888888"
FX = "99999999-9999-4999-8999-999999999999"
GRADES = [{"id": FIRSTS, "name": "1st Grade"}, {"id": COLTS, "name": "Colts"}]
PEOPLE = [{"id": HELPER, "name": "Helen Helper"}, {"id": JOE, "name": "Regular Joe"}]

STATE = {
    "medal_id": MID, "medal_name": "Club Champion", "grade_ids": [], "grade_names": [], "inactive_grades": [],
    "grade_voter_modes": {"1st Grade": "captain"}, "grade_vote_counters": {}, "vote_counter_names": {},
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
    if path.startswith("/votes/counter-options"):
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
                STATE["vote_counter_names"] = {
                    t: next(p["name"] for p in PEOPLE if p["id"] == pid) for t, pid in body["grade_vote_counters"].items()}
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
            "role": "player", "reason": None, "is_counter": True,
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

        counter_sel = lambda: page.locator("select[aria-label^='Who counts the votes for']")
        check("a captain-only team shows the counter picker", counter_sel().count() == 1,
              str(counter_sel().count()))
        check("the picker is for that team", counter_sel().first.get_attribute("aria-label") == "Who counts the votes for 1st Grade")
        opts = counter_sel().first.locator("option").all_inner_texts()
        check("it offers the captain first, then the club's players (not only who played)",
              opts == ["The captain", "Helen Helper", "Regular Joe"], str(opts))
        check("a team on All players has no picker", page.locator("text=Colts").count() == 0 or counter_sel().count() == 1)

        POSTS.clear()
        counter_sel().first.select_option(HELPER)
        page.wait_for_timeout(500)
        check("choosing a person sends the team name and player id",
              POSTS == [{"grade_vote_counters": {"1st Grade": HELPER}}], str(POSTS))
        check("the picker keeps the saved person", counter_sel().first.input_value() == HELPER)

        POSTS.clear()
        counter_sel().first.select_option("")
        page.wait_for_timeout(500)
        check("choosing The captain removes the team's entry",
              POSTS == [{"grade_vote_counters": {}}], str(POSTS))

        # Flip the team to All players: the picker goes away.
        team_select = [s for s in page.locator("select").all() if "Default (" in s.inner_text()][0]
        team_select.select_option("players")
        page.wait_for_timeout(500)
        check("a team switched to All players no longer shows the picker", counter_sel().count() == 0)
        team_select.select_option("captain")
        page.wait_for_timeout(500)
        counter_sel().first.select_option(HELPER)
        page.wait_for_timeout(500)

        if SHOTS:
            page.screenshot(path=f"{SHOTS}/counter-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(300)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("no horizontal overflow at 390px", overflow <= 0, str(overflow))
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/counter-390.png", full_page=True)

        # Public ballot page for the nominated person.
        page.set_viewport_size({"width": 390, "height": 900})
        page.goto(f"{BASE}/vote/champ-token?fixture={FX}", wait_until="domcontentloaded")
        page.wait_for_selector("text=Round 5", timeout=15000)
        page.wait_for_timeout(500)
        body = page.inner_text("body")
        check("the ballot page tells the nominee they count the votes for the team",
              "You are counting the votes for this team, in place of the captain." in body, body[:300])
        check("the ballot lists the team", "Regular Joe" in body and "Sam Side" in body)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("no horizontal overflow on the ballot at 390px", overflow <= 0, str(overflow))
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/counter-ballot-390.png", full_page=True)

        check("no page errors", not errors, str(errors))
        browser.close()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


main()
