"""A page or PDF a removed person can be sent as evidence that their request was acted on.

It lists the web addresses where their profile and matches used to appear, as
clickable links, so they can open each one and see for themselves: the profile
page says "Player not found", and each scorecard shows their name as ********.
Optionally it checks every address live from the server and records what came
back, so the document says what was true when it was made.

DELIBERATELY NOT IN IT
----------------------
Anything financial: fee records, membership types, payments, balances, invoices.
It does not mention that such a record exists. It also holds no email, phone,
date of birth or address. What it lists is the public web footprint and what was
done about it, nothing more.

HONESTY
-------
Every statement is either generated from the database at the time (the matches,
whether a photograph is held), derived from a check that was just run, or a plain
fact about how the system now behaves. The "what we cannot do" section says what a
removal does not reach (Cricket Australia's own site, a search engine's old copy).
"""
from __future__ import annotations

import html
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import text

from app.services import player_privacy, privacy_scrub

DEFAULT_BASE_URL = "https://betterat.cricket"
CONTACT = "support@bettersports.com.au"


# --------------------------------------------------------------------------- data

_GAME_IDS_SQL = """
SELECT g.id::text, g.played_at, g.home_team, g.away_team, gr.name
  FROM games g LEFT JOIN grades gr ON gr.id = g.grade_id
 WHERE g.id IN (
        SELECT game_id FROM game_appearances WHERE player_id::text = ANY(:ids)
        UNION SELECT game_id FROM batting_innings WHERE player_id::text = ANY(:ids)
        UNION SELECT game_id FROM bowling_spells WHERE player_id::text = ANY(:ids)
        UNION SELECT game_id FROM fielding_stats WHERE player_id::text = ANY(:ids)
 )
"""

_MANUAL_GAME_IDS_SQL = """
SELECT m.id::text, m.played_at, m.home_team, m.away_team, gr.name
  FROM manual_games m LEFT JOIN grades gr ON gr.id = m.grade_id
 WHERE m.id IN (
        SELECT manual_game_id FROM manual_batting_innings WHERE player_id::text = ANY(:ids)
        UNION SELECT manual_game_id FROM manual_bowling_spells WHERE player_id::text = ANY(:ids)
        UNION SELECT manual_game_id FROM manual_fielding_stats WHERE player_id::text = ANY(:ids)
 )
"""


def _full_name_forms(player) -> list[str]:
    """Only forms that can mean nobody else (the full name), so the live check never
    calls a relative's "T Marlowe" a leak."""
    out: set[str] = set()
    for raw in (player.name, player.display_name):
        pn = privacy_scrub.parse_name(raw or "")
        if pn and pn[0]:
            out |= privacy_scrub.forms_by_kind(*pn)["full"]
            out.add(" ".join((raw or "").split()))
    return sorted(out)


async def gather(session, player, base_url: str = DEFAULT_BASE_URL) -> dict:
    """What the document is about, read from the database now."""
    people = [player] + await player_privacy.siblings(session, player)
    ids = [str(p.id) for p in people]
    games: dict[str, dict] = {}
    for sql in (_GAME_IDS_SQL, _MANUAL_GAME_IDS_SQL):
        try:
            async with session.begin_nested():
                rows = (await session.execute(text(sql), {"ids": ids})).fetchall()
        except Exception:      # no manual tables on this database
            rows = []
        for gid, played, home, away, grade in rows:
            games[gid] = {"id": gid, "date": played, "home": home, "away": away, "grade": grade}
    matches = sorted(games.values(), key=lambda g: (g["date"] or date.min, g["id"]))
    base = base_url.rstrip("/")
    for m in matches:
        m["page_url"] = f"{base}/games/{m['id']}"
        m["data_url"] = f"{base}/api/games/{m['id']}/scorecard"
    return {
        "name": player.name,
        "display_name": player.display_name,
        "ids": ids,
        "hidden_at": player.privacy_hidden_at,
        "has_photo": any(bool(p.photo_data or p.photo_url or p.hero_photo_data or p.hero_photo_url) for p in people),
        "profile_urls": [f"{base}/players/{i}" for i in ids],
        "profile_data_urls": [f"{base}/api/players/{i}" for i in ids],
        "matches": matches,
        "base_url": base,
        "name_forms": _full_name_forms(player),
    }


# ------------------------------------------------------------------------- checks

async def verify(data: dict, *, transport=None, timeout: float = 20.0) -> dict:
    """Open every address now and record what came back. Never raises.

    Returns {url: {"status": int|None, "ok": bool|None, "note": str}}. ``ok`` is True
    when it behaves as promised, False when it does not (a leak), None when it could
    not be checked.
    """
    import httpx

    checks: dict[str, dict] = {}
    needles = [i.lower() for i in data["ids"]] + [f.lower() for f in data["name_forms"] if " " in f or "," in f]

    async with httpx.AsyncClient(transport=transport, timeout=timeout, follow_redirects=True) as client:
        async def get(url: str):
            try:
                return await client.get(url)
            except Exception as exc:     # network down, DNS, timeout
                return exc

        for url in data["profile_data_urls"]:
            r = await get(url)
            if isinstance(r, Exception):
                checks[url] = {"status": None, "ok": None, "note": "could not be checked from the server"}
            else:
                # The MESSAGE, not just the 404: a mistyped address is also a 404.
                said = "player not found" in r.text.lower()
                checks[url] = {"status": r.status_code, "ok": r.status_code == 404 and said,
                               "note": "returns 'Player not found'" if r.status_code == 404 and said
                               else f"returned {r.status_code}, which is not the expected 'Player not found'"}
        for m in data["matches"]:
            r = await get(m["data_url"])
            if isinstance(r, Exception):
                checks[m["data_url"]] = {"status": None, "ok": None, "note": "could not be checked from the server"}
            elif r.status_code != 200:
                checks[m["data_url"]] = {"status": r.status_code, "ok": None,
                                         "note": f"the scorecard returned {r.status_code}, so it could not be checked"}
            else:
                body = r.text.lower()
                leaked = any(n in body for n in needles)
                checks[m["data_url"]] = {"status": 200, "ok": not leaked,
                                         "note": "your name and player ID do not appear" if not leaked
                                         else "YOUR NAME OR ID STILL APPEARS"}
    return checks


# ------------------------------------------------------------------------ wording

def _fmt_date(d) -> str:
    return d.strftime("%a %d %b %Y").replace(" 0", " ") if isinstance(d, (date, datetime)) else "Date unknown"


def _title(m: dict) -> str:
    teams = f"{m['home']} v {m['away']}" if m.get("home") and m.get("away") else "Match"
    return f"{_fmt_date(m['date'])}, {m['grade'] or 'grade not recorded'}: {teams}"


def _result_line(check: Optional[dict], checked_at: str) -> str:
    if not check:
        return "Not checked when this was made."
    if check["ok"] is None:
        return f"Not checked: {check['note']}."
    if check["ok"]:
        return f"Checked by BetterSports at {checked_at} UTC: {check['note']}."
    return f"Checked at {checked_at} UTC: {check['note']}."


def build_sections(data: dict, checks: Optional[dict]) -> dict:
    """The wording, shared by the page and the PDF so they cannot disagree."""
    now = datetime.now(timezone.utc)
    checked_at = now.strftime("%d %b %Y %H:%M")
    when = _fmt_date(data["hidden_at"]) if data.get("hidden_at") else "the date of your request"
    n = len(data["matches"])
    done = [
        "Your profile page, and every page under it, answers 'Player not found'. This is the same for every visitor, "
        "including club administrators.",
        "Your name and player ID are replaced with ******** in public pages and in the data behind them, including match scorecards, "
        "leaderboards, records and yearbooks.",
        ("No photograph of you is held on BetterCricket." if not data["has_photo"]
         else "A photograph of you is still held. Please tell us and we will remove it."),
        "You are left out of the social media post tools (BetterSocials), so no post can be built about you.",
        "BetterCricket will not send email to you, from any club.",
        "A block on your Cricket Australia player ID stops a new profile being created if a club connects or a match "
        "is synced later.",
    ]
    cannot = [
        "Cricket Australia and PlayHQ publish match statistics on their own websites. We do not control those.",
        "A search engine may keep an old copy of a page for a while. If you find one, send us the link and we will ask "
        "for it to be removed.",
        "Your results stay in the club's match records, because other players' scores and the team totals depend on "
        "them. Your name is hidden on every public page.",
    ]
    return {
        "title": "Your BetterCricket profile: what we did and how you can check",
        "subtitle": f"Prepared for {data['name']}. Made {now.strftime('%d %b %Y')} (request recorded {when}).",
        "intro": ("You asked us to remove your profile and personal information from BetterCricket. This document lists the "
                  "web addresses where your profile and your matches used to appear, so you can open each one and see what "
                  "it shows now. Every address is a clickable link."),
        "profile_heading": "1. Your profile page",
        "profile_text": "Open the page below. You will see the message 'Player not found'.",
        "matches_heading": f"2. Your matches ({n})",
        "matches_text": (f"We hold {n} match scorecard{'s' if n != 1 else ''} that included you. Each page still shows the "
                         "match and the result, but your name appears as ********. The second link in each entry is the "
                         "same scorecard as raw data, which also shows ******** where you were."),
        "done_heading": "3. What has been done",
        "done": done,
        "cannot_heading": "4. What this does not reach",
        "cannot": cannot,
        "contact": f"If anything above does not match what you see, email {CONTACT} and we will fix it.",
        "checked_at": checked_at,
        "result": lambda c: _result_line(c, checked_at),
    }


# --------------------------------------------------------------------------- HTML

def render_html(data: dict, checks: Optional[dict] = None) -> str:
    s = build_sections(data, checks)
    e = html.escape

    def link(url: str) -> str:
        return f'<a href="{e(url)}">{e(url)}</a>'

    out = [f"""<!doctype html><html lang="en-AU"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>{e(s['title'])}</title>
<style>
 body{{font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;max-width:820px;margin:32px auto;padding:0 20px;color:#111}}
 h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:19px;margin:32px 0 8px;border-top:1px solid #ddd;padding-top:18px}}
 .sub{{color:#555;margin:0 0 20px}} .m{{margin:0 0 18px;padding:12px 14px;border:1px solid #ddd;border-radius:8px}}
 .m b{{display:block;margin-bottom:6px}} .r{{color:#2b6a2b;font-size:14px;margin:6px 0 0}} .l{{display:block;word-break:break-all;margin:2px 0}}
 a{{color:#0b57d0}} @media print{{a{{color:#000}} body{{margin:0}}}}
</style></head><body>
<h1>{e(s['title'])}</h1><p class="sub">{e(s['subtitle'])}</p><p>{e(s['intro'])}</p>
<h2>{e(s['profile_heading'])}</h2><p>{e(s['profile_text'])}</p>"""]
    for url, durl in zip(data["profile_urls"], data["profile_data_urls"]):
        out.append(f'<div class="m"><span class="l">Profile page: {link(url)}</span>'
                   f'<span class="l">Same thing as data: {link(durl)}</span>'
                   f'<p class="r">{e(s["result"]((checks or {}).get(durl)))}</p></div>')
    out.append(f"<h2>{e(s['matches_heading'])}</h2><p>{e(s['matches_text'])}</p>")
    for i, m in enumerate(data["matches"], 1):
        out.append(f'<div class="m"><b>{i}. {e(_title(m))}</b>'
                   f'<span class="l">Scorecard page: {link(m["page_url"])}</span>'
                   f'<span class="l">Raw data: {link(m["data_url"])}</span>'
                   f'<p class="r">{e(s["result"]((checks or {}).get(m["data_url"])))}</p></div>')
    out.append(f"<h2>{e(s['done_heading'])}</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in s["done"]) + "</ul>")
    out.append(f"<h2>{e(s['cannot_heading'])}</h2><ul>" + "".join(f"<li>{e(x)}</li>" for x in s["cannot"]) + "</ul>")
    out.append(f"<h2>Contact</h2><p>{e(s['contact'])}</p></body></html>")
    return "".join(out)


# ---------------------------------------------------------------------------- PDF

def _latin1(t: str) -> str:
    """The built-in PDF fonts are Latin-1. Fold the few typographic characters and
    replace anything else, so a name with an unusual letter cannot break the file."""
    t = (t or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    t = t.replace("–", "-").replace("—", "-")
    return t.encode("latin-1", "replace").decode("latin-1")


def render_pdf(data: dict, checks: Optional[dict] = None) -> bytes:
    from fpdf import FPDF

    s = build_sections(data, checks)
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(16, 16, 16)
    pdf.set_title(_latin1(s["title"]))
    pdf.set_author("BetterSports")
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    def para(t, size=10.5, bold=False, gap=2, color=(20, 20, 20)):
        pdf.set_font("Helvetica", "B" if bold else "", size)
        pdf.set_text_color(*color)
        pdf.multi_cell(W, 5.4 if size <= 11 else 7, _latin1(t), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(gap)

    def link_line(label, url):
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(20, 20, 20)
        pdf.write(5, _latin1(label + " "))
        pdf.set_text_color(11, 87, 208)
        pdf.set_font("Helvetica", "U", 8.5)
        pdf.write(5, _latin1(url), link=url)       # a real, clickable link annotation
        pdf.ln(5.2)

    def result(c):
        para(s["result"](c), size=9, gap=3, color=(43, 106, 43))

    para(s["title"], size=17, bold=True, gap=1)
    para(s["subtitle"], size=9.5, gap=4, color=(90, 90, 90))
    para(s["intro"])
    para(s["profile_heading"], size=13, bold=True, gap=1)
    para(s["profile_text"])
    for url, durl in zip(data["profile_urls"], data["profile_data_urls"]):
        link_line("Profile page:", url)
        link_line("Same thing as data:", durl)
        result((checks or {}).get(durl))
    para(s["matches_heading"], size=13, bold=True, gap=1)
    para(s["matches_text"])
    for i, m in enumerate(data["matches"], 1):
        if pdf.get_y() > pdf.h - 45:
            pdf.add_page()
        para(f"{i}. {_title(m)}", size=10, bold=True, gap=0.5)
        link_line("Scorecard page:", m["page_url"])
        link_line("Raw data:", m["data_url"])
        result((checks or {}).get(m["data_url"]))
    para(s["done_heading"], size=13, bold=True, gap=1)
    for x in s["done"]:
        para("- " + x, gap=1)
    para(s["cannot_heading"], size=13, bold=True, gap=1)
    for x in s["cannot"]:
        para("- " + x, gap=1)
    pdf.ln(2)
    para(s["contact"])
    return bytes(pdf.output())
