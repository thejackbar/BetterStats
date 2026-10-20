"""Ask IQ can put a clarifying question back to the user as buttons.

The model gets an `ask_user` tool. Calling it ends the turn with
`{answer: <question>, clarify: {question, options[{label, value}]}}`; the page
shows the options as buttons and sends the pick back as the next message. A
thread asks at most once: the turn after a clarification is not offered the
tool (the client marks it with `clarified`).

Runs the SHIPPED `iq_ask.answer` loop with the Anthropic client replaced by a
scripted fake, so the loop, the option clean-up and the tool gating are the real
code. No database is touched.

    python -m verification.verify_iq_ask_clarify

Control run: the same file against the previous commit must FAIL the clarify
checks (it has no ask_user tool) and pass the ordinary-answer ones.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/unused")

import anthropic  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.services import iq_ask  # noqa: E402

PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


def tool_use(name, args, id_="tu1"):
    return SimpleNamespace(type="tool_use", name=name, input=args, id=id_)


def text(t):
    return SimpleNamespace(type="text", text=t)


def resp(*blocks, stop="tool_use"):
    return SimpleNamespace(stop_reason=stop, content=list(blocks))


class FakeClient:
    script: list = []
    calls: list = []

    def __init__(self, *_a, **_k):
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kw):
        FakeClient.calls.append(kw)
        return FakeClient.script.pop(0)


async def run(script, history=None, question="Who should we pick?"):
    FakeClient.script, FakeClient.calls = list(script), []
    executed: list[str] = []

    async def fake_run_tool(org_id, name, args):
        executed.append(name)
        return {"ok": True}

    iq_ask._run_tool = fake_run_tool
    out = await iq_ask.answer(None, "org", "Home CC", question, history=history)
    return out, FakeClient.calls, executed


def offered(calls) -> set[str]:
    return {t["name"] for t in (calls[0].get("tools") or [])} if calls else set()


async def main() -> int:
    settings.anthropic_api_key = "test-key"
    anthropic.AsyncAnthropic = FakeClient

    print("\n-- the model asks a question: the turn ends with buttons --")
    ask = tool_use("ask_user", {"question": "Which grade do you mean?", "options": [
        {"label": "1st XI", "value": "Use 1st Grade"}, {"label": "2nd XI"}, {"label": "3rd XI"}]})
    out, calls, executed = await run([resp(ask)])
    cl = out.get("clarify") or {}
    check("ask_user is offered to the model", "ask_user" in offered(calls), str(offered(calls)))
    check("the reply carries a clarify block with three options", len(cl.get("options") or []) == 3, str(out))
    check("the question is also the answer text, so history reads sensibly",
          out.get("answer") == "Which grade do you mean?", str(out.get("answer")))
    check("a button's value is what it sends back, and defaults to its label",
          [o.get("value") for o in cl.get("options", [])] == ["Use 1st Grade", "2nd XI", "3rd XI"],
          str(cl.get("options")))
    check("the loop stopped: one model call, no tool run", len(calls) == 1 and not executed,
          f"calls={len(calls)} executed={executed}")

    print("\n-- a question mixed with a lookup still just asks --")
    out, calls, executed = await run([resp(tool_use("grades", {}, "a"), ask)])
    check("clarify returned", bool((out.get("clarify") or {}).get("options")), str(out))
    check("the lookup in the same step was not run", "grades" not in executed, str(executed))

    print("\n-- the options are cleaned --")
    messy = tool_use("ask_user", {"question": "Which one — batting or bowling?", "options": [
        {"label": "Batting"}, {"label": "batting"}, {"label": "Bowling — all"}, {"label": ""},
        {"label": "A"}, {"label": "B"}, {"label": "C"}, {"label": "D"}]})
    out, _, _ = await run([resp(messy)])
    cl = out.get("clarify") or {}
    labels = [o["label"] for o in cl.get("options", [])]
    check("at most five, duplicates and blanks dropped", 2 <= len(labels) <= 5 and labels.count("Batting") + labels.count("batting") == 1, str(labels))
    check("no em dashes anywhere", "—" not in str(cl), str(cl))

    print("\n-- an unusable question never dead-ends the user --")
    one = tool_use("ask_user", {"question": "Which?", "options": [{"label": "Only one"}]})
    out, calls, _ = await run([resp(one), resp(text("Going on this season's figures."), stop="end_turn")])
    check("one option is not a question: no clarify", not out.get("clarify"), str(out))
    check("the model is told and answers instead", out.get("answer") == "Going on this season's figures.", str(out))
    tr = (calls[1]["messages"][-1]["content"][0]["content"] if len(calls) > 1 else "")
    check("the tool result says it wasn't usable", "usable question" in str(tr), str(tr)[:120])

    print("\n-- one question per thread --")
    hist = [{"question": "Who should we pick?", "answer": "Which grade do you mean?", "clarified": True}]
    out, calls, _ = await run([resp(text("Pick Smith."), stop="end_turn")], history=hist, question="Use 3rd Grade")
    check("after a clarification ask_user is NOT offered", "ask_user" not in offered(calls), str(offered(calls)))
    check("the other tools still are", "find_players" in offered(calls), str(offered(calls)))
    check("and the pick is answered", out.get("answer") == "Pick Smith." and not out.get("clarify"), str(out))
    out, calls, _ = await run([resp(text("Fine."), stop="end_turn")],
                              history=[{"question": "q", "answer": "a"}])
    check("an ordinary earlier turn leaves it on", "ask_user" in offered(calls), str(offered(calls)))

    print("\n-- an ordinary answer is unchanged --")
    out, _, _ = await run([resp(text("We win 60% chasing."), stop="end_turn")], question="Chasing or batting first?")
    check("plain answer, no clarify key", out.get("answer") == "We win 60% chasing." and "clarify" not in out, str(out))

    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
