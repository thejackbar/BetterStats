"""Drives the voting portal in a real browser with the API stubbed at the network
layer. A player opens the one voting link, finds their name, enters their PIN and
lands on the next game they have not voted on; after each ballot they are offered
the next one until none is left; coming back signed in goes straight to the next
game. Also drives the admin Votes screen: the voting link is shown as just the link
and a copy button, above every tab, with none of the old sharing messages.

Usage:  python scripts/drive_vote_portal.py [http://127.0.0.1:5199] [screenshot_dir]
        (set CHROMIUM_PATH to a Chromium executable if Playwright's own is missing)
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
JOE, SAM, DAVE, CAP = "88888888-8888-4888-8888-888888888888", "a1", "a2", "a3"
F1, F2 = "99999999-9999-4999-8999-999999999991", "99999999-9999-4999-8999-999999999992"
CLUB = {"name": "Applecross CC", "short_name": "ACC", "slug": "applecross", "logo_url": None,
        "primary_color": "#0a7", "accent_color": "#07a"}
ME = {"id": JOE, "display_name": "Regular Joe"}
FIXTURES = {
    F1: {"id": F1, "opponent": "Bentley 4th XI", "round": "Round 2", "round_key": "2", "date": "2026-10-25",
         "home_away": "H", "state": "open", "voted": False},
    F2: {"id": F2, "opponent": "Melville", "round": "Round 1", "round_key": "1", "date": "2026-10-18",
         "home_away": "AWAY", "state": "open", "voted": False},
}
S = {"me": False, "submits": [], "verifies": [], "switches": 0}


def reset(signed_in=False, voted=()):
    S.update(me=signed_in, submits=[], verifies=[], switches=0)
    for fid, f in FIXTURES.items():
        f["voted"] = fid in voted


def route_public(route, request):
    path = request.url.split("/api/public/votes", 1)[1].split("?")[0]

    def send(body, status=200):
        route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    if request.method == "POST" and path.endswith("/verify"):
        S["verifies"].append(json.loads(request.post_data or "{}"))
        S["me"] = True
        return send({"status": "ok", "player": ME})
    if request.method == "POST" and path.endswith("/switch"):
        S["switches"] += 1
        S["me"] = False
        return send({"status": "ok"})
    if request.method == "POST" and path.endswith("/ballot"):
        fid = path.split("/fixtures/")[1].split("/")[0]
        S["submits"].append((fid, json.loads(request.post_data or "{}")))
        FIXTURES[fid]["voted"] = True
        return send({"status": "ok"})
    if "/fixtures/" in path:
        fid = path.split("/fixtures/")[1]
        f = FIXTURES[fid]
        return send({
            "club": CLUB, "fixture": {"id": fid, "opponent": f["opponent"], "round": f["round"], "date": f["date"], "state": "open"},
            "ballot_values": [3, 2, 1], "allow_self_vote": False, "voter_mode": "players",
            "me": ME if S["me"] else None, "role": "player" if S["me"] else "none",
            "reason": None if S["me"] else "verify_required",
            "players": [{"id": SAM, "name": "Sam Side", "photo_url": None}, {"id": DAVE, "name": "Dave Deep", "photo_url": None},
                        {"id": CAP, "name": "Captain Cook", "photo_url": None}],
            "my_ballot": None})
    return send({
        "club": CLUB, "medal": {"id": MID, "name": "Club Champion"}, "require_pin": True, "voter_mode": "players",
        "allow_non_participants": False, "allow_self_vote": False, "ballot_values": [3, 2, 1],
        "me": ME if S["me"] else None,
        "players": [{"id": JOE, "display_name": "Regular Joe", "has_phone": True},
                    {"id": SAM, "display_name": "Sam Side", "has_phone": True}],
        "grades": [], "rounds": [], "team": None, "round_key": None, "q": None,
        "fixtures": list(FIXTURES.values())})


# ── Admin stubs ──
MEDAL = {
    "medal_id": MID, "medal_name": "Club Champion", "grade_ids": [], "grade_names": [], "inactive_grades": [],
    "grade_voter_modes": {}, "grade_vote_counters": {}, "vote_chosen": {}, "team_options": [],
    "enabled": True, "token": "champ-token", "require_pin": True,
    "voter_mode": "players", "ballot_values": [3, 2, 1], "counting_method": "rank", "tie_policy": "share",
    "allow_self_vote": False, "allow_non_participants": False, "auto_close_days": 7,
    "eligibility_source": "scorecard",
}
PATCHES = []


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
        return send({"players": []})
    if path.startswith("/votes/medals"):
        if request.method == "PATCH":
            body = json.loads(request.post_data or "{}")
            PATCHES.append(body)
            MEDAL.update(body)
            return send(MEDAL)
        return send({"medals": [MEDAL], "grades": []})
    if path.startswith("/votes/settings"):
        return send(MEDAL)
    if path.startswith("/votes/leaderboard"):
        return send({"standings": [], "rounds": [], "years": [2026], "year": 2026, "grades": [], "ballot_values": [3, 2, 1],
                     "settings": MEDAL, "last_round": None, "through_round": None})
    if path.startswith("/votes/fixtures"):
        return send({"year": 2026, "years": [2026], "fixtures": [], "settings": MEDAL,
                     "grades": [], "grade_id": None, "rounds": [], "round_key": None, "q": None,
                     "summary": {"open": 0, "awaiting_team": 0, "ballots_in": 0, "ballots_expected": 0,
                                 "rounds_total": 0, "rounds_counted": 0},
                     "medals": [MEDAL], "medal_id": MID})
    return send({})


def pick_name_and_pin(page, name="Regular Joe", pin="1234"):
    page.get_by_role("button", name=name).first.click()
    page.wait_for_selector("input[inputmode='numeric']")
    page.fill("input[inputmode='numeric']", pin)
    page.get_by_role("button", name="Continue").click()


def main():
    errors = []
    with sync_playwright() as pw:
        kw = {"args": ["--no-sandbox"]}
        if CHROME:
            kw["executable_path"] = CHROME
        browser = pw.chromium.launch(**kw)
        ctx = browser.new_context(viewport={"width": 390, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/public/votes/**", route_public)
        page.route(lambda u: "/api/" in u and "/api/public/votes" not in u, route_api)
        page.add_init_script("localStorage.setItem('token','stub'); localStorage.setItem('bs_user','1');")
        text = lambda: page.inner_text("body")
        overflow = lambda: page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")

        # ── 1. A first visit starts at "find your name", not a list of games ──
        reset()
        page.goto(f"{BASE}/vote/champ-token", wait_until="domcontentloaded")
        page.wait_for_selector("text=Find your name to vote", timeout=20000)
        check("opening the link asks who you are first", "Find your name to vote" in text())
        check("it does not start on a list of games", "Round 2" not in text() and "VOTE →" not in text())
        check("no 'back to games' on the sign-in step", "Back to games" not in text())
        check("no horizontal overflow at 390px on sign-in", overflow() <= 0, str(overflow()))

        # ── 2. Name and PIN take them straight to the newest game they have not voted on ──
        pick_name_and_pin(page)
        page.wait_for_selector("text=Round 2 · vs Bentley 4th XI", timeout=10000)
        check("the PIN takes them straight to the newest unvoted game",
              "Round 2 · vs Bentley 4th XI" in text() and "Pick 3 more" in text(), text()[:200])
        check("the PIN is checked once, for the player picked",
              S["verifies"] == [{"player_id": JOE, "pin": "1234"}], str(S["verifies"]))
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/portal-ballot-390.png", full_page=True)
        check("no horizontal overflow on the ballot", overflow() <= 0, str(overflow()))

        # ── 3. After the ballot they are offered the next game ──
        for who in ("Sam Side", "Dave Deep", "Captain Cook"):
            page.get_by_role("button", name=who).click()
        page.get_by_role("button", name="Submit my votes").click()
        page.wait_for_selector("text=Votes in!", timeout=10000)
        check("the first ballot went to the first game", [s[0] for s in S["submits"]] == [F1], str(S["submits"]))
        check("the done screen offers the next game by name",
              page.locator("[data-next-game]").count() == 1 and "Round 1 · @ Melville" in page.locator("[data-next-game]").inner_text(),
              text()[:300])
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/portal-next-390.png", full_page=True)

        page.locator("[data-next-game]").click()
        page.wait_for_selector("text=Round 1 · vs Melville", timeout=10000)
        check("the next button opens that game's ballot", "Pick 3 more" in text())
        for who in ("Sam Side", "Dave Deep", "Captain Cook"):
            page.get_by_role("button", name=who).click()
        page.get_by_role("button", name="Submit my votes").click()
        page.wait_for_selector("text=Votes in!", timeout=10000)
        check("both games now have a ballot", [s[0] for s in S["submits"]] == [F1, F2], str(S["submits"]))
        check("with none left it says they are all caught up and offers no next game",
              page.locator("[data-next-game]").count() == 0 and page.locator("[data-all-caught-up]").count() == 1, text()[:300])

        page.get_by_role("button", name="See my games").click()
        page.wait_for_selector("text=You’re all caught up")
        check("the games list is still there for changing a ballot, marked voted",
              text().count("VOTED · CHANGE →") == 2, text()[:400])

        # ── 4. Coming back signed in goes straight to the next game ──
        reset(signed_in=True, voted=(F1,))
        page.goto(f"{BASE}/vote/champ-token", wait_until="domcontentloaded")
        page.wait_for_selector("text=Round 1 · vs Melville", timeout=20000)
        check("returning signed in goes straight to the game they have not voted on",
              "Pick 3 more" in text() and "Find your name" not in text(), text()[:200])

        reset(signed_in=True, voted=(F1, F2))
        page.goto(f"{BASE}/vote/champ-token", wait_until="domcontentloaded")
        page.wait_for_selector("text=You’re all caught up", timeout=20000)
        check("returning with every game voted shows the list, caught up, not a ballot",
              "Pick 3 more" not in text() and text().count("VOTED · CHANGE →") == 2, text()[:300])

        # ── 5. Not you? goes back to sign-in ──
        page.get_by_role("button", name="Not you?").click()
        page.wait_for_selector("text=Find your name to vote")
        check("'Not you?' clears the sign-in and asks who they are", S["switches"] == 1 and not S["me"])

        # ── 6. A link to one game still opens that game ──
        reset(signed_in=True)
        page.goto(f"{BASE}/vote/champ-token?fixture={F2}", wait_until="domcontentloaded")
        page.wait_for_selector("text=Round 1 · vs Melville", timeout=20000)
        check("a link to one game opens that game even when another is newer", "Round 2" not in text())

        # ── 7. Admin: the link is shown as just the link ──
        page.set_viewport_size({"width": 1280, "height": 1000})
        page.goto(f"{BASE}/admin/betterselect/votes", wait_until="domcontentloaded")
        page.wait_for_selector("[data-vote-link]", timeout=20000)
        val = page.locator("[data-vote-link] input").input_value()
        check("the Games tab shows the voting link above the tabs", val.endswith("/vote/champ-token"), val)
        check("it has a Copy link button", page.get_by_role("button", name="Copy link").count() == 1)
        body = text()
        check("none of the old sharing messages are there",
              not any(w in body for w in ("WhatsApp group", "SMS the XI", "Message preview", "QR for the clubroom",
                                          "Post to socials", "Every link is pre-filtered")), body[:300])
        page.goto(f"{BASE}/admin/betterselect/votes?tab=settings&medal={MID}", wait_until="domcontentloaded")
        page.wait_for_selector("[data-vote-link]", timeout=20000)
        check("the Settings tab shows the same link", page.locator("[data-vote-link] input").input_value().endswith("/vote/champ-token"))
        page.get_by_role("button", name="Leaderboard").click()
        page.wait_for_timeout(300)
        check("and so does the Leaderboard tab", page.locator("[data-vote-link]").count() == 1)
        if SHOTS:
            page.screenshot(path=f"{SHOTS}/portal-admin-desktop.png", full_page=False)

        # The Games and Leaderboard tabs already overflow at 390px on their own filter rows
        # (the guide's open follow-up), so check what this screen adds: the link bar fits.
        page.set_viewport_size({"width": 390, "height": 900})
        page.wait_for_timeout(300)
        right = page.evaluate("document.querySelector('[data-vote-link]').getBoundingClientRect().right")
        check("the link bar fits inside a 390px screen", right <= 390, str(right))
        page.goto(f"{BASE}/admin/betterselect/votes?tab=settings&medal={MID}", wait_until="domcontentloaded")
        page.wait_for_selector("[data-vote-link]", timeout=20000)
        page.wait_for_timeout(300)
        check("no horizontal overflow on the Settings tab at 390px", overflow() <= 0, str(overflow()))
        page.set_viewport_size({"width": 1280, "height": 1000})

        # ── 8. Admin: a link that is off says so and can be turned on ──
        MEDAL["enabled"] = False
        page.goto(f"{BASE}/admin/betterselect/votes", wait_until="domcontentloaded")
        page.wait_for_selector("[data-vote-link-off]", timeout=20000)
        check("a medal that is off has no link, only the notice", page.locator("[data-vote-link]").count() == 0)
        PATCHES.clear()
        page.get_by_role("button", name="Turn on voting link").click()
        page.wait_for_selector("[data-vote-link]", timeout=10000)
        check("turning it on sends exactly {enabled: true} and shows the link", PATCHES == [{"enabled": True}], str(PATCHES))

        check("no page errors", not errors, str(errors[:2]))
        browser.close()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    sys.exit(1 if FAIL else 0)


main()
