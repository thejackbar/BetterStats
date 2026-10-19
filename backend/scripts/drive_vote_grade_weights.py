"""Drives the grade weighting control on the Votes Settings tab in a real
browser with the API stubbed at the network layer. Asserts the exact body each
choice puts on the wire, that the table follows the mode, that a bad manual
weight never reaches the server, and that nothing overflows at 390px.

Usage:  python scripts/drive_vote_grade_weights.py [http://127.0.0.1:5199] [screenshot_dir]
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
G = {"1st Grade": "33333333-3333-4333-8333-333333333333", "2nd Grade": "44444444-4444-4444-8444-444444444444",
     "Colts": "55555555-5555-4555-8555-555555555555"}
GAMES = {"1st Grade": 18, "2nd Grade": 12, "Colts": 7}
AUTO = {"1st Grade": 1.0, "2nd Grade": 1.5, "Colts": 2.57}

STATE = {
    "medal_id": MID, "medal_name": "Club Champion", "grade_ids": [], "grade_names": [], "inactive_grades": [],
    "grade_voter_modes": {}, "grade_weighting": {"mode": "off", "manual": {}}, "enabled": True,
    "token": "champ-token", "require_pin": True, "voter_mode": "players", "ballot_values": [3, 2, 1],
    "counting_method": "rank", "tie_policy": "share", "allow_self_vote": False,
    "allow_non_participants": False, "auto_close_days": 7, "eligibility_source": "scorecard",
}
POSTS = []


def weighting():
    gw = STATE["grade_weighting"]
    mode, manual = gw.get("mode", "off"), gw.get("manual", {})
    in_force = {"off": {}, "auto": AUTO, "manual": manual}[mode]
    rows = []
    for name in ("1st Grade", "2nd Grade", "Colts"):
        w = in_force.get(name, 1.0)
        rows.append({"name": name, "games": GAMES[name], "auto_weight": AUTO[name], "weight": w,
                     "is_top": name == "1st Grade", "top_vote": round(3 * w, 2)})
    return {"year": 2026, "season_label": "2026/27", "mode": mode, "top_grade": "1st Grade",
            "ballot_values": [3, 2, 1], "rows": rows}


def route_api(route, request):
    path = request.url.split("/api", 1)[1] if "/api" in request.url else request.url

    def send(body):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    if path.startswith("/auth/me"):
        return send({"id": "u1", "username": "admin", "role": "club_admin", "club_slug": "applecross",
                     "organisation_id": "org1", "capabilities": [], "entitlements": {
                         "modules": ["select"], "status": "active", "overrides": ["select"]}})
    if "/weighting" in path:
        return send(weighting())
    if path.startswith("/votes/medals"):
        return send({"medals": [STATE], "grades": [{"id": v, "name": k, "display_order": None} for k, v in G.items()]})
    if path.startswith("/votes/settings"):
        if request.method == "POST":
            body = json.loads(request.post_data or "{}")
            POSTS.append(body)
            if "grade_weighting" in body:
                gw = body["grade_weighting"]
                STATE["grade_weighting"] = ({"mode": gw["mode"], "manual": gw.get("manual", {})} if gw
                                            else {"mode": "off", "manual": {}})
        return send(STATE)
    if path.startswith("/votes/fixtures"):
        return send({"year": 2026, "years": [2026], "fixtures": [], "settings": STATE, "grades": [],
                     "grade_id": None, "rounds": [], "round_key": None, "q": None,
                     "summary": {"open": 0, "awaiting_team": 0, "ballots_in": 0, "ballots_expected": 0,
                                 "rounds_counted": 0, "rounds_total": 0},
                     "medals": [STATE], "medal_id": MID})
    return send({})


def main():
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                                      args=["--no-sandbox"])
        page = browser.new_context(viewport={"width": 1280, "height": 1200}).new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/**", route_api)
        page.add_init_script("localStorage.setItem('token','stub'); localStorage.setItem('bs_user','1');")
        page.goto(f"{BASE}/admin/betterselect/votes?tab=settings&medal={MID}", wait_until="domcontentloaded")
        page.wait_for_selector("text=Weight by grade", timeout=15000)
        page.wait_for_selector("text=2026/27", timeout=15000)

        body = page.inner_text("body")
        check("each grade is listed with its fixture count",
              all(f"{n}" in body for n in ("1st Grade", "2nd Grade", "Colts")) and "18" in body and "12" in body, body[:200])
        check("off: the table says what auto would give for the grades that differ",
              "auto ×1.5" in body and "auto ×2.57" in body, "")

        # Auto
        POSTS.clear()
        page.get_by_role("button", name="Auto-weight").click()
        page.wait_for_timeout(600)
        check("Auto-weight sends mode auto and nothing else",
              POSTS and POSTS[-1] == {"grade_weighting": {"mode": "auto"}}, str(POSTS))
        body = page.inner_text("body")
        check("auto: the 12 game grade reads x1.5 and the top grade is named",
              "×1.5" in body and "×2.57" in body and "Measured against 1st Grade" in body, body[-600:])
        check("auto: the top grade is tagged", page.get_by_text("Top", exact=True).count() == 1)
        check("auto: top vote in the 12 game grade is 4.5", "4.5" in body)

        # Manual
        POSTS.clear()
        page.get_by_role("button", name="Manual", exact=True).click()
        page.wait_for_timeout(600)
        check("Manual starts from the auto weights, so nothing resets to 1",
              POSTS and POSTS[-1] == {"grade_weighting": {"mode": "manual", "manual": AUTO}}, str(POSTS))
        inp = page.get_by_label("Vote weight for 2nd Grade")
        check("manual: each grade gets a weight box", inp.count() == 1 and inp.input_value() == "1.5", inp.input_value())

        POSTS.clear()
        inp.fill("0")
        page.get_by_role("button", name="Save weights").click()
        page.wait_for_timeout(400)
        check("a weight of 0 never reaches the server", not POSTS, str(POSTS))

        inp.fill("0.5")
        page.get_by_role("button", name="Save weights").click()
        page.wait_for_timeout(600)
        check("saving sends every grade's weight, with the typed one",
              POSTS and POSTS[-1]["grade_weighting"]["manual"]["2nd Grade"] == 0.5
              and POSTS[-1]["grade_weighting"]["mode"] == "manual", str(POSTS))
        check("manual: the saved weight shows and Save goes away",
              page.get_by_label("Vote weight for 2nd Grade").input_value() == "0.5"
              and page.get_by_role("button", name="Save weights").count() == 0)

        if SHOTS:
            page.screenshot(path=f"{SHOTS}/weights-desktop.png", full_page=True)

        # Back to the same for every grade
        POSTS.clear()
        page.get_by_role("button", name="Same for every grade").click()
        page.wait_for_timeout(600)
        check("Same for every grade clears the setting", POSTS and POSTS[-1] == {"grade_weighting": {}}, str(POSTS))

        # 390px in auto mode (the widest table)
        page.get_by_role("button", name="Auto-weight").click()
        page.wait_for_timeout(600)
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(300)
        overflow = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        check("no horizontal overflow at 390px", overflow <= 0, str(overflow))
        el = page.get_by_text("Weight by grade").first
        el.scroll_into_view_if_needed()
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/weights-390.png", full_page=True)
        check("no page errors", not errors, str(errors))
        browser.close()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


main()
