"""Drives the Votes Settings tab in a real browser with the API stubbed at the
network layer, for a club with TWO teams in one grade (Applecross 8th and 10th XI
in One Day Grade 6 Black): each team has its own row, its own mode and its own list
of chosen people, every change puts the exact body on the wire under that team's
key, and nothing overflows at 390px.

Usage:  python scripts/drive_vote_shared_grade_teams.py [http://127.0.0.1:5199] [screenshot_dir]
"""
from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5199"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else None
CHROME = os.environ.get("CHROMIUM_PATH")

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


MID = "11111111-1111-4111-8111-111111111111"
OD6 = "One Day Grade 6 Black"
T8, T10 = "55555555-5555-4555-8555-555555555555", "66666666-6666-4666-8666-666666666666"
K8, K10 = f"{OD6}::{T8}", f"{OD6}::{T10}"
G_OD6, G_FIRSTS = "33333333-3333-4333-8333-333333333333", "44444444-4444-4444-8444-444444444444"
ALF, ABE, BOB, BEN = ("77777777-7777-4777-8777-777777777777", "88888888-8888-4888-8888-888888888888",
                      "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
GRADES = [{"id": G_OD6, "name": OD6}, {"id": G_FIRSTS, "name": "1st Grade"}]
PEOPLE = [{"id": ALF, "name": "Alf Eighth"}, {"id": ABE, "name": "Abe Eighth"},
          {"id": BOB, "name": "Bob Tenth"}, {"id": BEN, "name": "Ben Tenth"}]
NAME = {p["id"]: p["name"] for p in PEOPLE}

STATE = {
    "medal_id": MID, "medal_name": "Club Champion", "grade_ids": [], "grade_names": [], "inactive_grades": [],
    # What the server sends for a club that set one OD6 entry before: shown on both teams.
    "grade_voter_modes": {K8: "chosen", K10: "chosen"},
    "grade_vote_counters": {K8: [ALF, ABE], K10: [ALF, ABE]},
    "vote_chosen": {K8: [{"id": ALF, "name": "Alf Eighth"}, {"id": ABE, "name": "Abe Eighth"}],
                    K10: [{"id": ALF, "name": "Alf Eighth"}, {"id": ABE, "name": "Abe Eighth"}]},
    "team_options": [
        {"key": "1st Grade", "grade_name": "1st Grade", "name": "1st Grade"},
        {"key": K8, "grade_name": OD6, "name": f"{OD6} · 8th XI"},
        {"key": K10, "grade_name": OD6, "name": f"{OD6} · 10th XI"},
    ],
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
        if request.method == "PATCH":
            body = json.loads(request.post_data or "{}")
            POSTS.append(body)
            if "grade_voter_modes" in body:
                STATE["grade_voter_modes"] = body["grade_voter_modes"]
            if "grade_vote_counters" in body:
                STATE["grade_vote_counters"] = body["grade_vote_counters"]
                STATE["vote_chosen"] = {t: [{"id": pid, "name": NAME[pid]} for pid in ids]
                                        for t, ids in body["grade_vote_counters"].items()}
            return send(STATE)
        return send({"medals": [STATE], "grades": GRADES})
    if path.startswith("/votes/settings"):
        if request.method == "POST":
            body = json.loads(request.post_data or "{}")
            POSTS.append(body)
            if "grade_voter_modes" in body:
                STATE["grade_voter_modes"] = body["grade_voter_modes"]
            if "grade_vote_counters" in body:
                STATE["grade_vote_counters"] = body["grade_vote_counters"]
                STATE["vote_chosen"] = {t: [{"id": pid, "name": NAME[pid]} for pid in ids]
                                        for t, ids in body["grade_vote_counters"].items()}
        return send(STATE)
    if path.startswith("/votes/fixtures"):
        return send({"year": 2026, "years": [2026], "fixtures": [], "settings": STATE,
                     "grades": [], "grade_id": None, "rounds": [], "round_key": None, "q": None,
                     "summary": {"open": 0, "awaiting_team": 0, "ballots_in": 0, "ballots_expected": 0,
                                 "rounds_total": 0, "rounds_counted": 0},
                     "medals": [STATE], "medal_id": MID})
    return send({})


def main():
    errors = []
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox"]}
        if CHROME:
            kw["executable_path"] = CHROME
        browser = pw.chromium.launch(**kw)
        ctx = browser.new_context(viewport={"width": 1280, "height": 1300})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route(lambda u: "/api/" in u, route_api)
        page.add_init_script("localStorage.setItem('token','stub'); localStorage.setItem('bs_user','1');")

        page.goto(f"{BASE}/admin/betterselect/votes?tab=settings&medal={MID}", wait_until="domcontentloaded")
        page.wait_for_selector("text=Who votes, by team", timeout=20000)
        page.wait_for_timeout(500)

        body = page.inner_text("body")
        check("each team in the shared grade has its own row",
              f"{OD6} · 8th XI" in body and f"{OD6} · 10th XI" in body)
        check("a grade only one team plays keeps a row named for the grade", "1st Grade" in body)
        check("each shared team shows its own list of chosen people",
              page.locator(f"[data-testid='chosen-{K8}']").count() == 1
              and page.locator(f"[data-testid='chosen-{K10}']").count() == 1)

        add_sel = lambda key: page.locator(f"[data-testid='chosen-{K10 if key == 10 else K8}'] select")
        mode_sel = lambda i: [x for x in page.locator("select").all() if "Default (" in x.inner_text()][i]

        # The 10th XI row (third: 1st Grade, 8th XI, 10th XI): drop the 8th XI's people, add its own.
        POSTS.clear()
        page.get_by_role("button", name=f"Remove Alf Eighth from {OD6} · 10th XI").click()
        page.wait_for_timeout(400)
        check("removing a person from the 10th XI sends only the 10th XI's list, under its own key",
              POSTS == [{"grade_vote_counters": {K8: [ALF, ABE], K10: [ABE]}}], str(POSTS))
        POSTS.clear()
        page.get_by_role("button", name=f"Remove Abe Eighth from {OD6} · 10th XI").click()
        page.wait_for_timeout(400)
        check("emptying the 10th XI's list leaves the 8th XI's alone",
              POSTS == [{"grade_vote_counters": {K8: [ALF, ABE]}}], str(POSTS))
        check("the 10th XI says nobody is chosen; the 8th XI still lists its two",
              "Nobody is chosen yet" in page.locator(f"[data-testid='chosen-{K10}']").inner_text()
              and "Alf Eighth" in page.locator(f"[data-testid='chosen-{K8}']").inner_text())

        POSTS.clear()
        add_sel(10).first.select_option(BOB)
        page.wait_for_timeout(400)
        add_sel(10).first.select_option(BEN)
        page.wait_for_timeout(400)
        check("adding people to the 10th XI sends its list under its own key, the 8th XI's untouched",
              POSTS[-1] == {"grade_vote_counters": {K8: [ALF, ABE], K10: [BOB, BEN]}}, str(POSTS))

        POSTS.clear()
        mode_sel(2).select_option("captain")
        page.wait_for_timeout(400)
        check("changing the 10th XI's mode sends its key and leaves the 8th XI on Chosen people",
              POSTS == [{"grade_voter_modes": {K8: "chosen", K10: "captain"}}], str(POSTS))
        check("the 10th XI no longer shows a list; the 8th XI still does",
              page.locator(f"[data-testid='chosen-{K10}']").count() == 0
              and page.locator(f"[data-testid='chosen-{K8}']").count() == 1)

        if SHOTS:
            page.screenshot(path=f"{SHOTS}/shared-grade-desktop.png", full_page=True)
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(300)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("no horizontal overflow at 390px", overflow <= 0, str(overflow))
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/shared-grade-390.png", full_page=True)
        check("no page errors", not errors, str(errors[:2]))
        browser.close()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


main()
