"""Drives the BetterFootball Votes + Team lists screens in a real browser
against the dev server (VITE_SPORT=afl) with the API stubbed at the network
layer.

The point is the state a screenshot can't reach: switching between two medals
and seeing the games list, the count and the ballot shape all follow; the medal
riding in the URL so a link to one count is shareable; a stale medal falling
back rather than emptying the screen; the exact params each screen puts on the
wire; and the public ballot actually submitting what was tapped.

Usage:  python scripts/drive_afl_votes.py [http://127.0.0.1:5200]
"""
from __future__ import annotations

import json
import re
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5200"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")


SENIOR = "11111111-1111-4111-8111-111111111111"
RESERVES = "22222222-2222-4222-8222-222222222222"
G_SEN = "33333333-3333-4333-8333-333333333333"
G_RES = "44444444-4444-4444-8444-444444444444"
GAME_SEN = "55555555-5555-4555-8555-555555555555"
GAME_RES = "66666666-6666-4666-8666-666666666666"
ORG = "77777777-7777-4777-8777-777777777777"


def medal(mid, name, values, grade_names, token):
    return {
        "medal_id": mid, "medal_name": name, "grade_ids": [], "grade_names": grade_names,
        "enabled": True, "token": token, "require_pin": True, "voter_mode": "players",
        "ballot_values": values, "counting_method": "rank", "tie_policy": "share",
        "allow_self_vote": False, "allow_non_participants": False, "auto_close_days": 7,
    }


MEDALS = {
    SENIOR: medal(SENIOR, "Best & Fairest", [3, 2, 1], [], "sen-token"),
    RESERVES: medal(RESERVES, "Reserves Medal", [5, 4, 3, 2, 1], ["Reserves"], "res-token"),
}

GAMES = {
    SENIOR: [
        {"id": GAME_SEN, "opponent": "Melville", "round": "Round 5", "round_key": "5",
         "date": "2026-05-16", "grade": "A Grade Men", "grade_id": G_SEN, "result": "W",
         "state": "open", "closes_on": "2026-05-23", "ballots": 6, "voters_expected": 22,
         "outstanding_count": 16},
        {"id": GAME_RES, "opponent": "Kingsley", "round": "Round 5", "round_key": "5",
         "date": "2026-05-16", "grade": "Reserves", "grade_id": G_RES, "result": "L",
         "state": "open", "closes_on": "2026-05-23", "ballots": 2, "voters_expected": 22,
         "outstanding_count": 20},
    ],
    RESERVES: [
        {"id": GAME_RES, "opponent": "Kingsley", "round": "Round 5", "round_key": "5",
         "date": "2026-05-16", "grade": "Reserves", "grade_id": G_RES, "result": "L",
         "state": "open", "closes_on": "2026-05-23", "ballots": 1, "voters_expected": 22,
         "outstanding_count": 21},
    ],
}

STANDINGS = {
    SENIOR: [{"player_id": "p1", "name": "Sam Ruthven", "points": 9, "raw": 9,
              "counts": [3, 0, 0], "rounds": 3, "grade": "A Grade Men", "movement": 1,
              "form": [3, 3, 3], "cumulative": [3, 6, 9], "round_gain": 3, "tied": False}],
    RESERVES: [{"player_id": "p2", "name": "Tom Deeley", "points": 5, "raw": 5,
                "counts": [1, 0, 0, 0, 0], "rounds": 1, "grade": "Reserves", "movement": 0,
                "form": [5], "cumulative": [5], "round_gain": 5, "tied": False}],
}

SEASONS = [{"id": "s1", "name": "2026", "year": 2026}]
GRADE_OPTS = [{"id": G_SEN, "name": "A Grade Men"}, {"id": G_RES, "name": "Reserves"}]

SEEN = {"games": [], "board": [], "submit": []}


def route(r, req):
    url = req.url
    path = url.split("/api", 1)[1] if "/api" in url else url
    m = re.search(r"medal_id=([0-9a-f-]+)", path)
    mid = m.group(1) if m else None

    def send(b):
        r.fulfill(status=200, content_type="application/json", body=json.dumps(b))

    if path.startswith("/auth/me"):
        return send({"id": "u1", "username": "admin", "role": "club_admin",
                     "club_slug": "cuw", "organisation_id": ORG, "capabilities": [],
                     "entitlements": {"modules": [], "status": "active", "overrides": []}})
    if path.startswith("/votes/medals"):
        return send({"medals": list(MEDALS.values()), "grades": GRADE_OPTS})
    if path.startswith("/votes/games"):
        SEEN["games"].append(path)
        key = mid or SENIOR
        rows = GAMES.get(key, [])
        return send({
            "season_id": "s1", "seasons": SEASONS, "games": rows,
            "settings": MEDALS[key],
            "grades": [g for g in GRADE_OPTS if key == SENIOR or g["id"] == G_RES],
            "grade_id": None, "rounds": [{"key": "5", "label": "Round 5"}],
            "round_key": None, "q": None,
            "summary": {"open": len(rows), "awaiting_team": 0,
                        "ballots_in": sum(g["ballots"] for g in rows),
                        "ballots_expected": 22, "rounds_counted": 1, "rounds_total": 1},
            "medals": list(MEDALS.values()), "medal_id": key,
        })
    if path.startswith("/votes/leaderboard"):
        SEEN["board"].append(path)
        key = mid or SENIOR
        return send({
            "medal_id": key, "medal_name": MEDALS[key]["medal_name"],
            "ballot_values": MEDALS[key]["ballot_values"], "counting_method": "rank",
            "tie_policy": "share", "rounds": [], "standings": STANDINGS[key],
            "through_round": None, "last_round": None, "grades": [], "seasons": SEASONS,
            "season_id": "s1", "club_name": "Curtin Uni Wesley", "club_short": "CUW",
            "season_label": "2026", "grade_name": "Whole club", "grade_id": None,
            "medals": list(MEDALS.values()),
        })

    # ── Team lists ──────────────────────────────────────────────────────────
    if "/afl-lineups/organisations/" in path:
        return send({"has_more": False, "games": [
            {"id": GAME_SEN, "date": "2026-05-16", "round": "Round 5",
             "home_team": "Curtin Uni Wesley", "away_team": "Melville", "result": "W",
             "venue": "Hayman Rd", "grade": "A Grade Men", "grade_id": G_SEN,
             "season": "2026", "our_side": "HOME", "published": True, "named": 23},
            {"id": GAME_RES, "date": "2026-05-09", "round": "Round 4",
             "home_team": "Kingsley", "away_team": "Curtin Uni Wesley", "result": "L",
             "venue": "Kingsley Oval", "grade": "Reserves", "grade_id": G_RES,
             "season": "2026", "our_side": "AWAY", "published": False, "named": 0},
        ]})
    if "/afl-lineups/games/" in path:
        return send({
            "game_id": GAME_SEN, "round": "Round 5", "status": "FINAL",
            "date": "2026-05-16", "venue": "Hayman Rd", "grade": "A Grade Men",
            "grade_id": G_SEN, "season_id": "s1", "season": "2026",
            "published": True, "our_side": "HOME",
            "teams": [
                {"side": "HOME", "name": "Curtin Uni Wesley", "logo_url": None, "is_ours": True,
                 "players": [
                     {"player_id": "p1", "name": "Sam Ruthven", "jumper_number": "1",
                      "is_captain": True, "played": True, "goals": 3, "behinds": 1,
                      "bog_ranking": 1, "photo_url": None},
                     {"player_id": None, "name": "Late Inclusion", "jumper_number": "44",
                      "is_captain": False, "played": True, "goals": 0, "behinds": 0,
                      "bog_ranking": None, "photo_url": None},
                 ]},
                {"side": "AWAY", "name": "Melville", "logo_url": None, "is_ours": False,
                 "players": [
                     {"player_id": None, "name": "Opposition Bloke", "jumper_number": "7",
                      "is_captain": False, "played": True, "goals": 1, "behinds": 0,
                      "bog_ranking": None, "photo_url": None},
                 ]},
            ],
        })

    # ── Public voting ───────────────────────────────────────────────────────
    if re.match(r"^/public/votes/[^/]+/games/[^/]+/ballot", path):
        SEEN["submit"].append(json.loads(req.post_data or "{}"))
        return send({"status": "ok"})
    if re.match(r"^/public/votes/[^/]+/games/", path):
        return send({
            "game": {"id": GAME_SEN, "opponent": "Melville", "round": "Round 5",
                     "grade": "A Grade Men", "date": "2026-05-16", "state": "open"},
            "medal": {"id": SENIOR, "name": "Best & Fairest"},
            "ballot_values": [3, 2, 1], "role": "player", "reason": None,
            "players": [{"id": f"pp{i}", "name": n} for i, n in
                        enumerate(["Sam Ruthven", "Tom Deeley", "Jack Nolan", "Ben Hart"])],
            "my_ballot": None,
        })
    if re.match(r"^/public/votes/[^/]+$", path.split("?")[0]):
        return send({
            "club": {"name": "Curtin Uni Wesley", "short_name": "CUW", "slug": "cuw",
                     "logo_url": None, "primary_color": None, "accent_color": None},
            "medal": {"id": SENIOR, "name": "Best & Fairest"},
            "require_pin": True, "voter_mode": "players", "allow_non_participants": False,
            "allow_self_vote": False, "ballot_values": [3, 2, 1],
            "me": {"id": "pp0", "display_name": "Sam Ruthven"},
            "players": [{"id": "pp0", "display_name": "Sam Ruthven", "has_phone": True}],
            "grades": GRADE_OPTS, "team": None,
            "games": [{"id": GAME_SEN, "opponent": "Melville", "round": "Round 5",
                       "grade": "A Grade Men", "date": "2026-05-16", "state": "open",
                       "open": True}],
        })
    if "/clubs/" in path:
        return send({"id": ORG, "name": "Curtin Uni Wesley", "slug": "cuw", "grades": [],
                     "seasons": SEASONS})
    return send({})


def main():
    errors = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.route("**/api/**", route)
        page.add_init_script("localStorage.setItem('token','stub')")

        # ── Admin votes ────────────────────────────────────────────────────
        page.goto(f"{BASE}/admin/votes", wait_until="networkidle")
        page.wait_for_timeout(1400)
        body = page.inner_text("body")
        check("both medals are offered", "Best & Fairest" in body and "Reserves Medal" in body,
              body[:200])
        check("the all-grades medal lists both grades' games",
              "Melville" in body and "Kingsley" in body)

        SEEN["games"].clear()
        page.get_by_role("button", name=re.compile(r"^Reserves Medal")).click()
        page.wait_for_timeout(900)
        check("switching medal puts it in the URL", f"medal={RESERVES}" in page.url, page.url)
        check("switching medal sends the new medal_id on the wire",
              any(RESERVES in p for p in SEEN["games"]), str(SEEN["games"]))
        body = page.inner_text("body")
        check("the Reserves medal's games drop the seniors game",
              "Kingsley" in body and "Melville" not in body, body[:300])

        SEEN["board"].clear()
        page.get_by_role("button", name="The count").click()
        page.wait_for_timeout(900)
        check("the count asks for the selected medal",
              any(RESERVES in p for p in SEEN["board"]), str(SEEN["board"]))
        body = page.inner_text("body")
        check("the count shows that medal's own standings", "Tom Deeley" in body)
        check("the count names the medal and its ballot shape",
              "Reserves Medal" in body and "5-4-3-2-1" in body, body[:400])
        check("switching tabs keeps the medal", f"medal={RESERVES}" in page.url, page.url)

        page.get_by_role("button", name="Medals").click()
        page.wait_for_timeout(900)
        body = page.inner_text("body")
        check("the medal editor shows the grade picker", "Grades it counts" in body)
        check("the medal's own grade reads as ticked", "Counting Reserves" in body,
              body[body.find("Grades it counts"):][:200] if "Grades it counts" in body else "")
        check("a club with two medals is offered Delete", "Delete Reserves Medal" in body)
        check("the voting link can be copied", "Copy voting link" in body)

        page.goto(f"{BASE}/admin/votes?medal=99999999-9999-4999-8999-999999999999",
                  wait_until="networkidle")
        page.wait_for_timeout(1000)
        check("a medal the club no longer holds falls back to the first",
              "Best & Fairest" in page.inner_text("body"))

        # ── Team lists ─────────────────────────────────────────────────────
        page.goto(f"{BASE}/cuw/team-lists", wait_until="networkidle")
        page.wait_for_timeout(1400)
        body = page.inner_text("body")
        check("team lists lists the club's games", "Melville" in body and "Kingsley" in body,
              body[:300])
        check("a game with a list says how many were named", "23 named" in body, body[:400])
        # PlayHQ's own flag: 'not published' is a different fact from 'we have
        # no list', and the page has to keep them apart.
        check("a game the club never published says so, not just 'no team list'",
              "not published" in body, body[:400])
        page.get_by_text("Curtin Uni Wesley v Melville").click()
        page.wait_for_timeout(900)
        body = page.inner_text("body")
        check("opening a game shows both sides", "Sam Ruthven" in body and "Opposition Bloke" in body)
        check("a named player we hold no record for still shows", "Late Inclusion" in body)

        # ── Public ballot ──────────────────────────────────────────────────
        page.goto(f"{BASE}/vote/sen-token", wait_until="networkidle")
        page.wait_for_timeout(1200)
        body = page.inner_text("body")
        check("the public page names the medal", "BEST & FAIREST" in body.upper(), body[:200])
        page.get_by_text("v Melville").first.click()
        page.wait_for_timeout(900)
        check("the ballot opens with nothing picked",
              "Pick 3 more" in page.inner_text("body"), page.inner_text("body")[:400])
        for name in ("Jack Nolan", "Tom Deeley", "Ben Hart"):
            page.get_by_role("button", name=re.compile(name)).first.click()
            page.wait_for_timeout(150)
        check("the submit button enables once every position is filled",
              "Submit my votes" in page.inner_text("body"))
        page.get_by_role("button", name="Submit my votes").click()
        page.wait_for_timeout(800)
        check("the ballot submits the picks in the order they were tapped",
              SEEN["submit"] and SEEN["submit"][-1]["picks"] == ["pp2", "pp1", "pp3"],
              str(SEEN["submit"]))
        check("the voter is told their ballot landed", "Thanks" in page.inner_text("body"))

        # ── Mobile ─────────────────────────────────────────────────────────
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(500)
        check("the public ballot doesn't overflow at 390px",
              not page.evaluate(
                  "document.documentElement.scrollWidth > document.documentElement.clientWidth"))
        page.goto(f"{BASE}/admin/votes", wait_until="networkidle")
        page.wait_for_timeout(1200)
        check("the admin votes screen doesn't overflow at 390px",
              not page.evaluate(
                  "document.documentElement.scrollWidth > document.documentElement.clientWidth"))

        check("no page errors", not errors, "; ".join(errors[:3]))
        browser.close()

    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
