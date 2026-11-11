"""Support chat (Chatwoot bot and widget identity): what the code does with a webhook.

No database and no network. Chatwoot is an httpx MockTransport that records every
call the bot makes, and the Anthropic SDK is a stub that returns whatever tool call
the check asks for. The route is driven through FastAPI's TestClient, so the shipped
route body, secret check and background hand-off run.

    python -m verification.verify_support_chat

Each "nothing happened" check is paired with one where the same call does act, so a
check cannot pass because the whole bot is switched off.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac as hmac_mod
import json
import os
import re
import sys
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres@127.0.0.1:5432/verify_support_chat")

import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.routers import support_chat as router_mod  # noqa: E402
from app.services import support_chat as sc  # noqa: E402

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


# ─── Stubs ────────────────────────────────────────────────────────────────────

class Chatwoot:
    """Records bot calls. ``thread`` is what GET .../messages returns."""

    def __init__(self, thread: list[dict] | None = None, fail_post: bool = False):
        self.thread = thread or []
        self.fail_post = fail_post
        self.calls: list[tuple[str, str, dict | None]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body))
        assert request.headers.get("api_access_token") == "bot-token", "bot must use its own token"
        if request.method == "GET":
            return httpx.Response(200, json={"payload": self.thread})
        if self.fail_post and request.url.path.endswith("/messages"):
            return httpx.Response(500, json={})
        return httpx.Response(200, json={})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

    @property
    def posts(self):
        return [c for c in self.calls if c[0] == "POST" and c[1].endswith("/messages")]

    @property
    def public_posts(self):
        return [c for c in self.posts if not c[2]["private"]]

    @property
    def private_posts(self):
        return [c for c in self.posts if c[2]["private"]]

    @property
    def toggles(self):
        return [c for c in self.calls if c[1].endswith("/toggle_status")]


class Model:
    """Replaces the anthropic module. ``script`` is (tool name, input) or an Exception."""

    def __init__(self):
        self.script = None
        self.calls: list[dict] = []

    def install(self):
        outer = self

        class _Msgs:
            async def create(self, **kw):
                outer.calls.append(kw)
                if isinstance(outer.script, Exception):
                    raise outer.script
                name, data = outer.script
                return types.SimpleNamespace(content=[types.SimpleNamespace(type="tool_use", name=name, input=data)])

        class _Client:
            def __init__(self, **kw):
                self.messages = _Msgs()

        sys.modules["anthropic"] = types.SimpleNamespace(AsyncAnthropic=_Client)


MODEL = Model()
MODEL.install()


def payload(content="How much does it cost?", status="pending", mid=1, conv=77, mtype="incoming", private=False, event="message_created"):
    return {
        "event": event, "id": mid, "content": content, "message_type": mtype, "private": private,
        "sender": {"name": "Sam Club", "email": "sam@example.org", "custom_attributes": {"club": "Test CC", "role": "club_admin"}},
        "conversation": {"id": conv, "status": status},
    }


def configure(on=True):
    settings.chatwoot_base_url = "https://help.example.test" if on else ""
    settings.chatwoot_internal_url = "http://chatwoot-rails:3000" if on else ""
    settings.chatwoot_website_token = "web-token" if on else ""
    settings.chatwoot_hmac_token = "hmac-secret" if on else ""
    settings.chatwoot_account_id = "1" if on else ""
    settings.chatwoot_bot_token = "bot-token" if on else ""
    settings.chatwoot_webhook_secret = "s3cret-path" if on else ""
    settings.chatwoot_mentions = "Jack:3,Elton:4,bad,Nobody:x" if on else ""
    settings.anthropic_api_key = "sk-test"


async def run(p: dict, cw: Chatwoot) -> str:
    sc._seen.clear()
    return await sc.handle_webhook(p, http=cw.client())


async def main() -> None:
    configure(True)

    # ── identity ────────────────────────────────────────────────────────────
    user = types.SimpleNamespace(id="u-1", display_name="Sam Club", username="sam", email="sam@example.org")
    club = types.SimpleNamespace(name="Test CC", slug="test-cc")
    idn = sc.identity(user, club, "club_admin")
    expect = hmac_mod.new(b"hmac-secret", b"bettercricket-user-u-1", hashlib.sha256).hexdigest()
    check("identity: enabled with the signed identifier", idn.get("enabled") is True and idn.get("identifier_hash") == expect)
    check("identity: carries the club and role for the team", idn.get("attributes", {}).get("club") == "Test CC" and idn["attributes"].get("role") == "club_admin")
    check("identity: base url has no trailing slash", idn.get("base_url") == "https://help.example.test")
    configure(False)
    check("identity: off when unset", sc.identity(user, club, "club_admin") == {"enabled": False})
    configure(True)
    settings.chatwoot_hmac_token = ""
    check("identity: off without the signing secret (never an unsigned identity)", sc.identity(user, club, None) == {"enabled": False})
    configure(True)

    # ── history shaping ─────────────────────────────────────────────────────
    thread = [
        {"message_type": 2, "content": "Conversation started"},
        {"message_type": 1, "content": "Hi, I'm the bot", "private": False},
        {"message_type": 0, "content": "How much?"},
        {"message_type": 0, "content": "for BetterIQ"},
        {"message_type": 1, "content": "private note", "private": True},
        {"message_type": 1, "content": "$249 a year"},
        {"message_type": 0, "content": "thanks"},
    ]
    h = sc.build_history(thread)
    check("history: starts and ends on the customer, merges runs, drops notes and activity",
          [t["role"] for t in h] == ["user", "assistant", "user"] and h[0]["content"] == "How much?\nfor BetterIQ", str(h))

    # ── the bot ─────────────────────────────────────────────────────────────
    MODEL.script = ("reply", {"text": "BetterStats is $399 a year — modules extra."})
    cw = Chatwoot([{"message_type": 0, "content": "How much does it cost?"}])
    out = await run(payload(), cw)
    check("reply: answers once, publicly, no hand-off", out == "replied" and len(cw.public_posts) == 1 and not cw.toggles and not cw.private_posts, str(cw.calls))
    sent = cw.public_posts[0][2]["content"] if cw.public_posts else ""
    check("reply: no em dash reaches the customer", "—" not in sent and "$399" in sent, sent)
    check("reply: the model saw the FAQ and the customer's words",
          "reference_notes" in MODEL.calls[-1]["system"] and "$399 a year" in MODEL.calls[-1]["system"] and MODEL.calls[-1]["messages"][-1]["content"] == "How much does it cost?")

    MODEL.script = ("hand_off", {"reason": "billing", "summary": "Wants a refund", "message": "Jack and Elton will pick this up."})
    cw = Chatwoot([{"message_type": 0, "content": "refund please"}])
    out = await run(payload("I want a refund for last year"), cw)
    note = cw.private_posts[0][2]["content"] if cw.private_posts else ""
    check("hand-off: tells the customer, leaves a private note, opens the conversation",
          out == "handed_off" and len(cw.public_posts) == 1 and len(cw.private_posts) == 1 and len(cw.toggles) == 1
          and cw.toggles[0][2] == {"status": "open"}, str(cw.calls))
    check("hand-off: the note names the club, the reason and @mentions both agents",
          "Test CC" in note and "billing" in note and "mention://user/3/Jack" in note and "mention://user/4/Elton" in note, note)
    check("hand-off: a bad mention entry is skipped, not fatal", "Nobody" not in note and "bad" not in note.split("Bot hand-off")[0], note)
    check("hand-off: order is message, note, then open", [c[1].rsplit("/", 1)[1] for c in cw.calls if c[0] == "POST"] == ["messages", "messages", "toggle_status"])

    # A person asked for a person: the model is not asked.
    before = len(MODEL.calls)
    MODEL.script = RuntimeError("the model must not be called")
    cw = Chatwoot([{"message_type": 0, "content": "x"}])
    out = await run(payload("Can I speak to a real person please"), cw)
    check("asked for a person: hands off without calling the model", out == "handed_off" and len(MODEL.calls) == before and len(cw.toggles) == 1)
    MODEL.script = ("reply", {"text": "ok"})
    cw = Chatwoot([{"message_type": 0, "content": "x"}])
    out = await run(payload("Can I add a player called Jack Smith"), cw)
    check("a name in a question is not a request for a person", out == "replied" and not cw.toggles)

    # Whose turn it is.
    MODEL.script = ("reply", {"text": "ok"})
    cw = Chatwoot()
    check("open conversation: the bot stays out", await run(payload(status="open"), cw) == "ignored" and not cw.calls)
    cw = Chatwoot([{"message_type": 0, "content": "hi"}])
    check("pending conversation: the bot acts (pair for the check above)", await run(payload(status="pending"), cw) == "replied" and cw.calls)
    for label, p in (("an outgoing message", payload(mtype="outgoing")), ("a private note", payload(private=True)),
                     ("another event", payload(event="conversation_status_changed")), ("a resolved conversation", payload(status="resolved"))):
        cw = Chatwoot()
        check(f"ignores {label}", await run(p, cw) == "ignored" and not cw.calls)

    # Retries.
    cw = Chatwoot([{"message_type": 0, "content": "hi"}])
    sc._seen.clear()
    first = await sc.handle_webhook(payload(mid=500), http=cw.client())
    second = await sc.handle_webhook(payload(mid=500), http=cw.client())
    check("a retried webhook is answered once", first == "replied" and second == "duplicate" and len(cw.public_posts) == 1)

    # Failing towards a person.
    MODEL.script = RuntimeError("overloaded")
    cw = Chatwoot([{"message_type": 0, "content": "hi"}])
    out = await run(payload("How do I merge two players?"), cw)
    check("model error: hands off with an honest message", out == "handed_off" and cw.public_posts[0][2]["content"] == sc.UNAVAILABLE_MESSAGE and len(cw.toggles) == 1)
    MODEL.script = ("reply", {"text": "ok"})
    settings.anthropic_api_key = ""
    cw = Chatwoot([{"message_type": 0, "content": "hi"}])
    out = await run(payload(), cw)
    check("no API key: hands off, does not go quiet", out == "handed_off" and len(cw.toggles) == 1)
    settings.anthropic_api_key = "sk-test"
    long_thread = [{"message_type": i % 2, "content": f"m{i}"} for i in range(14)] + [{"message_type": 0, "content": "again"}]
    before = len(MODEL.calls)
    cw = Chatwoot(long_thread)
    out = await run(payload("again"), cw)
    check(f"after {sc.MAX_BOT_REPLIES} bot replies a person takes over, model not called", out == "handed_off" and len(MODEL.calls) == before)
    MODEL.script = ("reply", {"text": "   "})
    cw = Chatwoot([{"message_type": 0, "content": "hi"}])
    out = await run(payload(), cw)
    check("empty model reply: hands off rather than sending nothing", out == "handed_off" and len(cw.toggles) == 1)
    MODEL.script = ("hand_off", {"reason": "x", "summary": "y"})
    cw = Chatwoot([{"message_type": 0, "content": "hi"}], fail_post=True)
    out = await run(payload(), cw)
    check("hand-off still opens the conversation when a message post fails", out == "error" and len(cw.toggles) == 1)
    configure(True)
    settings.chatwoot_bot_token = ""
    cw = Chatwoot()
    check("bot off without its token: ignores everything", await run(payload(), cw) == "ignored" and not cw.calls)
    configure(True)

    # ── the route ───────────────────────────────────────────────────────────
    app = FastAPI()
    app.include_router(router_mod.public_router)
    tc = TestClient(app)
    seen: list[dict] = []

    async def fake_handle(p, http=None):
        seen.append(p)
        return "replied"

    real = sc.handle_webhook
    sc.handle_webhook = fake_handle
    try:
        r = tc.post("/public/support-chat/webhook/wrong", json=payload())
        check("route: wrong secret is a 404 and nothing runs", r.status_code == 404 and not seen)
        settings.chatwoot_webhook_secret = ""
        r = tc.post("/public/support-chat/webhook/", json=payload())
        r2 = tc.post("/public/support-chat/webhook/anything", json=payload())
        check("route: an unset secret matches nothing", r.status_code in (404, 405) and r2.status_code == 404 and not seen)
        configure(True)
        r = tc.post("/public/support-chat/webhook/s3cret-path", content=b"not json", headers={"content-type": "application/json"})
        check("route: not JSON is a 400", r.status_code == 400 and not seen)
        r = tc.post("/public/support-chat/webhook/s3cret-path", json=[1, 2])
        check("route: a JSON array is a 400", r.status_code == 400 and not seen)
        r = tc.post("/public/support-chat/webhook/s3cret-path", json=payload(mid=9))
        check("route: right secret is a 200 and the bot gets the payload", r.status_code == 200 and len(seen) == 1 and seen[0]["id"] == 9)
        r = tc.post("/public/support-chat/webhook/s3cret-path", content=b"{" + b" " * (300 * 1024) + b"}", headers={"content-type": "application/json"})
        check("route: an oversized body is refused", r.status_code == 413)
    finally:
        sc.handle_webhook = real

    # ── knowledge base stays in step with the public FAQ page ───────────────
    faq_jsx = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "marketing" / "FAQ.jsx"
    page_qs = len(re.findall(r"^\s+q: ", faq_jsx.read_text(encoding="utf-8"), re.M))
    json_qs = sum(len(c["items"]) for c in json.loads(sc.FAQ_PATH.read_text(encoding="utf-8")))
    check("FAQ file has every question on the FAQ page (re-extract if this fails)", page_qs == json_qs and json_qs > 0, f"page={page_qs} json={json_qs}")

    print()
    print("ALL PASS" if not FAILS else f"{len(FAILS)} FAILED: " + "; ".join(FAILS))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    asyncio.run(main())
