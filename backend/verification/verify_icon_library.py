"""The BetterPosts icon search (v9.106.37), `services/icon_library.py`.

Runs the SHIPPED module against a stand-in for Iconify (httpx.MockTransport), so
every claim is about what OUR code asks for, keeps and refuses, then a live
smoke test of the real service when the network allows.

  * only licence-safe sets are asked for, and an icon from any other set that
    slips into an answer is dropped;
  * Phosphor's six weights collapse to one;
  * a club word with no icon of its own ("pumpkin") is searched under its
    synonyms too, and coloured sets sort ahead of single-colour ones;
  * a repeat search and a repeat icon are served from the cache: zero outbound
    requests, paired with the first call which DID go out;
  * the per-club ceiling stops a runaway caller, and another club is unaffected;
  * an SVG carrying script, an event handler, HTML or an external reference is
    refused, and a clean one is returned (so the refusal is a contrast);
  * a colour is applied to a single-colour set and ignored by a coloured one;
  * a malformed id never reaches the network.

CONTROL MODE: against the commit before this change `icon_library` does not
exist; every check then reports as failed rather than crashing.

Run:  python verification/verify_icon_library.py
"""
from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

HAVE = importlib.util.find_spec("app.services.icon_library") is not None
L = importlib.import_module("app.services.icon_library") if HAVE else None
PASS = FAIL = 0


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1; print(f"  ok   {label}")
    else:
        FAIL += 1; print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


CLEAN = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path fill="currentColor" d="M1 1h22v22H1z"/></svg>'
EVIL = {
    "script": '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
    "handler": '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"><path d="M0 0"/></svg>',
    "html": '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject><div>x</div></foreignObject></svg>',
    "remote": '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><image xlink:href="https://evil.example/x.png"/></svg>',
    "js-url": '<svg xmlns="http://www.w3.org/2000/svg"><a href="javascript:alert(1)"><path d="M0 0"/></a></svg>',
    "not svg": '<html>nope</html>',
}


def make_client(calls):
    def handler(req: httpx.Request):
        calls.append(str(req.url))
        path = req.url.path
        if path == "/search":
            q = req.url.params["query"]
            icons = {
                "trophy": ["mdi:trophy", "ph:trophy", "ph:trophy-bold", "ph:trophy-duotone", "noto:trophy", "game-icons:trophy", "lucide:trophy"],
                "jack-o-lantern": ["noto:jack-o-lantern", "fluent-emoji:jack-o-lantern"],
                "pumpkin": [],
                "ghost": ["mdi:ghost", "noto:ghost"],
            }.get(q, [])
            return httpx.Response(200, json={"icons": icons, "total": len(icons)})
        name = path.rsplit("/", 1)[-1]
        if name in ("evil-script.svg", "evil-handler.svg"):
            return httpx.Response(200, text=EVIL["script" if "script" in name else "handler"])
        if name == "gone.svg":
            return httpx.Response(404, text="")
        return httpx.Response(200, text=CLEAN)
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def main():
    if not HAVE:
        for lab in ("licence-safe sets only", "weights collapse", "synonyms", "coloured first", "cache", "ceiling", "svg refused", "svg clean", "colour", "bad id"):
            check(lab, False, "icon_library missing")
        print(f"\n{PASS} passed, {FAIL} failed"); sys.exit(1)

    print("search")
    calls = []
    async with make_client(calls) as c:
        r = await L.search("club-a", "trophy", 48, client=c)
        ids = [i["id"] for i in r["icons"]]
        check("an icon from a set we do not search is dropped", "game-icons:trophy" not in ids, str(ids))
        check("the sets we do search are kept", {"mdi:trophy", "noto:trophy", "lucide:trophy"} <= set(ids), str(ids))
        check("Phosphor's six weights collapse to one", [i for i in ids if i.startswith("ph:")] == ["ph:trophy"], str(ids))
        check("coloured sets sort ahead of single-colour ones", ids.index("noto:trophy") < ids.index("mdi:trophy"), str(ids))
        check("the request names only the licence-safe sets", all(set(httpx.URL(u).params.get("prefixes", "").split(",")) <= set(L.SETS) for u in calls if "/search" in u), str(calls))
        n = len(calls)
        r2 = await L.search("club-a", "trophy", 48, client=c)
        check("the same search again makes no outbound request", len(calls) == n and r2 == r, f"{len(calls)} vs {n}")
        check("... and the first search did go out (so that is a contrast)", n >= 1)

        calls.clear()
        r = await L.search("club-a", "halloween", 48, client=c)
        ids = [i["id"] for i in r["icons"]]
        asked = [httpx.URL(u).params["query"] for u in calls if "/search" in u]
        check("a club word is searched under its synonyms too", "jack-o-lantern" in asked and "halloween" in asked, str(asked))
        check("the synonym's icons come back", "noto:jack-o-lantern" in ids and "noto:ghost" in ids, str(ids))
        r = await L.search("club-a", "pumpkin", 48, client=c)
        check("'pumpkin' (no icon of its own) finds the jack-o-lantern", "noto:jack-o-lantern" in [i["id"] for i in r["icons"]])
        r = await L.search("club-a", "   ", 48, client=c)
        check("a blank search goes nowhere", r["icons"] == [])

    print("icons")
    calls = []
    async with make_client(calls) as c:
        body = await L.svg("club-a", "mdi:trophy", "#ff0000", client=c)
        check("a clean SVG is returned", body.startswith("<svg"))
        check("a colour is passed for a single-colour set", any("color=%23ff0000" in u for u in calls), str(calls))
        calls.clear()
        await L.svg("club-a", "noto:trophy", "#ff0000", client=c)
        check("a colour is NOT passed for a coloured set", not any("color=" in u for u in calls), str(calls))
        n = len(calls)
        await L.svg("club-a", "noto:trophy", "#ff0000", client=c)
        check("the same icon again makes no outbound request", len(calls) == n)
        calls.clear()
        await L.svg("club-a", "mdi:trophy", "red", client=c)
        check("a malformed colour is not forwarded", not any("color=" in u for u in calls), str(calls))
        for bad in ("noid", "game-icons:sword", "mdi:../etc/passwd", "MDI:Trophy", "mdi:", ""):
            calls.clear()
            try:
                await L.svg("club-a", bad, None, client=c)
                check(f"a bad id is refused ({bad!r})", False)
            except L.IconError:
                check(f"a bad id is refused, nothing sent ({bad!r})", not calls)
        for nm in ("evil-script", "evil-handler"):
            try:
                await L.svg("club-a", f"mdi:{nm}", None, client=c)
                check(f"an SVG with {nm.split('-')[1]} is refused", False)
            except L.IconError:
                check(f"an SVG with {nm.split('-')[1]} is refused", True)
        for k, v in EVIL.items():
            try:
                L.clean_svg(v); check(f"clean_svg refuses: {k}", False)
            except L.IconError:
                check(f"clean_svg refuses: {k}", True)
        check("clean_svg passes a clean one", L.clean_svg(CLEAN) == CLEAN)
        try:
            await L.svg("club-a", "mdi:gone", None, client=c)
            check("a missing icon says so", False)
        except L.IconError as e:
            check("a missing icon says so", "not in the library" in str(e), str(e))

    print("ceiling")
    calls = []
    async with make_client(calls) as c:
        hit = None
        for i in range(L.SEARCHES_PER_MIN + 5):
            try:
                await L.search("club-b", f"term{i}", 8, client=c)
            except L.IconError as e:
                hit = (i, str(e)); break
        check("a runaway club is stopped at the ceiling", hit is not None and hit[0] == L.SEARCHES_PER_MIN, str(hit))
        try:
            await L.search("club-c", "fresh", 8, client=c)
            check("another club is unaffected", True)
        except L.IconError as e:
            check("another club is unaffected", False, str(e))

    print("live")
    try:
        L._cache.clear()
        r = await L.search("live", "golf", 12)
        check("the real service answers a search", bool(r["icons"]), str(r)[:120])
        s = await L.svg("live", r["icons"][0]["id"], "#ffffff")
        check("... and an icon", s.startswith("<svg"))
        r = await L.search("live", "pumpkin", 12)
        check("... and 'pumpkin' finds a coloured jack-o-lantern", any("jack-o-lantern" in i["id"] and i["coloured"] for i in r["icons"]), str(r)[:200])
    except L.IconError as e:
        print(f"  skip live ({e})")

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
