"""Verification of the evidence document sent to a removed person.

Seeds a club with real games (the hide-juniors fixture), removes one player who
played three of them, then builds the HTML and PDF the person would be sent and
checks them against the real app.

What is proved:
  * every match the person is recorded in is listed, each with a full clickable
    link to its scorecard page and to the raw data, plus the profile page links;
  * the live check opens each address and records what came back, and it can tell
    a leak from a pass: run BEFORE the removal it must report the name and id still
    appear (the control), run AFTER it must report they do not;
  * the document holds nothing financial, not even the fact that a fee record
    exists, and none of the person's contact details;
  * the PDF's links are real link annotations (clickable), not just text, and its
    text is readable and Latin-1 safe;
  * the report's email field says "nothing to block" and not a misleading False.

Run:  DATABASE_URL=postgresql+asyncpg://root@/evidence_test?host=/var/run/postgresql \
      python verification/verify_privacy_evidence.py
"""
from __future__ import annotations

import asyncio
import contextlib
import io
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

import httpx
from sqlalchemy import text

import app.models.scout  # noqa: F401  (registers scouted_players on Base)
import verify_hide_juniors as hj
from app.models.db import FeeMember, Player
from app.services import player_privacy, privacy_evidence
from app.services.player_privacy_ddl import STATEMENTS as PRIVACY_DDL

PASS = FAIL = 0
FAILURES: list[str] = []
NAME = "Zebediah Quillfeather"
import re
FINANCIAL_RE = re.compile(r"\b(fees?|payments?|paid|invoices?|balance|membership|subscriptions?|money|owing|dues)\b|\$|financial\.sentinel", re.I)


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  — ' + detail) if detail else ''}")


class ApiPrefixTransport(httpx.AsyncBaseTransport):
    """nginx strips /api before the backend sees a request; the in-process app has no
    such proxy, so do the same here and the test exercises the real public URLs."""

    def __init__(self, inner):
        self.inner = inner

    async def handle_async_request(self, request):
        path = request.url.path
        if path.startswith("/api/"):
            request.url = request.url.copy_with(path=path[4:])
        return await self.inner.handle_async_request(request)


async def prepare():
    async with hj.engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await hj.build_schema()
    async with hj.engine.begin() as conn:
        for stmt in PRIVACY_DDL:
            await conn.execute(text(stmt))
    async with hj.Session() as s:
        await hj.seed(s)
    pid = hj.P["S1"]
    async with hj.Session() as s:
        await s.execute(text("UPDATE players SET name = :n WHERE id = :i"), {"n": NAME, "i": pid})
        await s.execute(text("UPDATE organisations SET slug='kalamunda', is_active=true WHERE id=:o"), {"o": hj.OURS})
        # A financial record that MUST NOT surface anywhere in the document.
        s.add(FeeMember(organisation_id=hj.OURS, player_id=pid, full_name=NAME, email="financial.sentinel@club.test"))
        await s.commit()
    return pid


def pdf_links_and_text(pdf: bytes):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(pdf))
    uris, text_ = [], ""
    for page in r.pages:
        text_ += (page.extract_text() or "") + "\n"
        for a in page.get("/Annots") or []:
            obj = a.get_object()
            if obj.get("/A") and obj["/A"].get("/URI"):
                uris.append(str(obj["/A"]["/URI"]))
    return uris, text_


async def main() -> int:
    pid = await prepare()
    from app.main import app
    transport = ApiPrefixTransport(httpx.ASGITransport(app=app))
    BASE = "http://t"

    async with hj.Session() as s:
        player = await s.get(Player, pid)
        data = await privacy_evidence.gather(s, player, BASE)

    print("the matches")
    check("the three games he played are listed", len(data["matches"]) == 3, str(len(data["matches"])))
    check("each has a full page URL and a raw-data URL",
          all(m["page_url"] == f"{BASE}/games/{m['id']}" and m["data_url"] == f"{BASE}/api/games/{m['id']}/scorecard"
              for m in data["matches"]))
    check("the profile URLs use his id",
          data["profile_urls"] == [f"{BASE}/players/{pid}"] and data["profile_data_urls"] == [f"{BASE}/api/players/{pid}"])
    check("matches are in date order", [m["date"] for m in data["matches"]] == sorted(m["date"] for m in data["matches"]))

    print("the live check can tell a leak from a pass (control)")
    before = await privacy_evidence.verify(data, transport=transport)
    leaked = [u for u, c in before.items() if c["ok"] is False]
    check("BEFORE the removal the check reports his name or id still appears on at least one scorecard",
          len(leaked) >= 1, str(before))
    check("...and that the profile data is NOT 'not found' (it is still public)",
          any(c["ok"] is False for u, c in before.items() if "/api/players/" in u))

    async with hj.Session() as s:
        pl = await s.get(Player, pid)
        await player_privacy.hide_at_request(s, pl, by="Jack", reason="asked by email")
        await s.commit()
    from app.services import privacy_scrub, privacy_email
    privacy_scrub.forget()
    privacy_email.forget()

    async with hj.Session() as s:
        player = await s.get(Player, pid)
        data = await privacy_evidence.gather(s, player, BASE)
    checks = await privacy_evidence.verify(data, transport=transport)
    check("AFTER the removal every address checks out",
          all(c["ok"] is True for c in checks.values()), str({u: c for u, c in checks.items() if c["ok"] is not True}))
    check("the profile data address returns 404", checks[data["profile_data_urls"][0]]["status"] == 404)
    check("every scorecard returned 200 and holds neither his name nor his id",
          all(checks[m["data_url"]]["status"] == 200 and checks[m["data_url"]]["ok"] for m in data["matches"]))
    unreachable = await privacy_evidence.verify(data, transport=httpx.MockTransport(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down"))))
    check("a site that cannot be reached reads 'not checked', never a pass",
          all(c["ok"] is None for c in unreachable.values()))

    print("the page")
    page = privacy_evidence.render_html(data, checks)
    for m in data["matches"]:
        check(f"HTML links {m['page_url'][-12:]} as a clickable <a href>", f'<a href="{m["page_url"]}">' in page)
        check("...and its raw data", f'<a href="{m["data_url"]}">' in page)
    check("HTML links the profile page and says what it shows",
          f'<a href="{data["profile_urls"][0]}">' in page and "Player not found" in page)
    check("HTML records the live check", "Checked by BetterSports" in page)
    check("HTML explains the ******** mask", "********" in page)

    print("nothing financial, no contact details")
    hits = FINANCIAL_RE.findall(page)
    check("the page holds no financial wording and not the fee-record email", not hits, str(hits))

    print("the PDF")
    pdf = privacy_evidence.render_pdf(data, checks)
    check("it is a PDF", pdf[:5] == b"%PDF-")
    uris, ptext = pdf_links_and_text(pdf)
    expected = set(data["profile_urls"] + data["profile_data_urls"] + [m["page_url"] for m in data["matches"]]
                   + [m["data_url"] for m in data["matches"]])
    check("every address is a real clickable link annotation in the PDF", expected <= set(uris), str(expected - set(uris)))
    check("the full URLs are printed in the text too", all(m["page_url"].split("://", 1)[1][:30] in ptext.replace("\n", "") for m in data["matches"]))
    phits = FINANCIAL_RE.findall(ptext)
    check("the PDF holds no financial wording either", not phits, str(phits))
    check("the PDF says what the person will see", "Player not found" in ptext and "********" in ptext)
    odd = dict(data, name="Zoë Ångström — Ж", display_name="Zoë")
    check("an unusual name cannot break the PDF", privacy_evidence.render_pdf(odd, checks)[:5] == b"%PDF-")

    print("the command")
    args = SimpleNamespace(player_id=str(pid), reason=None, by=None, report=False, restore=False, keep_photos=False,
                           apply=False, evidence=True, format="html", base_url=BASE, no_verify=True)
    from app.scripts import hide_player_at_request as script
    script.async_session_maker = hj.Session
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = await script.run(args)
    out = buf.getvalue()
    check("--evidence --format html writes the page to stdout and nothing else", rc == 0 and out.startswith("<!doctype html>"), out[:60])
    check("--no-verify says 'Not checked' instead of claiming a check", "Not checked when this was made" in out)
    # A removed person with NO address on record: the report must say so, not "False".
    nina = hj.P["N1"]
    async with hj.Session() as s:
        pl = await s.get(Player, nina)
        await player_privacy.hide_at_request(s, pl, by="Jack", reason="asked")
        await s.commit()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await script.run(SimpleNamespace(**{**vars(args), "player_id": str(nina), "evidence": False, "report": True}))
    import json
    rep = json.loads(buf.getvalue())
    check("--report: no address on record reads 'nothing to block', not a misleading False",
          rep["email_blocked"] is None and "nothing to block" in rep["email_note"], str(rep.get("email_blocked")))
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await script.run(SimpleNamespace(**{**vars(args), "evidence": False, "report": True}))
    rep = json.loads(buf.getvalue())
    check("--report: a person WITH an address on record shows it blocked (the control for the above)",
          rep["email_blocked"] is True and rep["email_addresses"], str(rep.get("email_blocked")))

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAILURES:
        print("FAILED:", *FAILURES, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
