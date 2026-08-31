"""A club's trial, as an audience and as a number in the email.

Asked for on BetterComms → Segments: pick the contacts whose club is in a trial
finishing within N days, and the contacts whose club's trial has already run out
— and be able to splice the days-left / days-since figure into the email body.

This runs the SHIPPED service and route bodies (imported, nothing retyped)
against a real Postgres. Run it against the previous commit and the checks fail
on exactly the behaviour that did not exist.

    python -m verification.verify_club_trial_segments
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, CommsContact, MarketingClub, Organisation, OrgModuleSubscription,
)
from app.services import club_trial_window as ctw
from app.services import comms_segments
from app.routers.comms import (
    MERGE_VARIABLES, _apply_overrides, _context_var_keys, _render_parts, _send_vars,
)

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_club_trial",
)

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


NOW = dt.datetime.now(dt.timezone.utc)


def days(n: float) -> dt.datetime:
    return NOW + dt.timedelta(days=n)


async def emails_for(db, org, rules) -> set:
    """The shipped segment engine, resolved to the set of addresses matched."""
    rows = await comms_segments.resolve_contacts(db, org, {"match": "all", "rules": rules})
    return {c.email for c in rows}


async def main() -> int:
    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        # A clean slate each run: circular FKs make drop_all unusable here.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as db:
        # The BetterCricket outreach org doing the sending.
        outreach = Organisation(id=uuid.uuid4(), name="BetterCricket", slug="bettercricket",
                                is_marketing_outreach=True)
        db.add(outreach)
        await db.flush()

        # Each prospect club: an onboarded org, its directory row, and a contact.
        # (label, trial rows as (module, status, ends_at))
        clubs = {
            # Scenario 1 — a live trial, 5 days from finishing.
            "ends-in-5":      [("core", "trial", days(5.4))],
            # Live but a long way off, so an "ends within 7 days" segment must
            # not sweep it in.
            "ends-in-40":     [("core", "trial", days(40.2))],
            # Ends later today — 0 days left, which must read as still running,
            # not as expired.
            "ends-today":     [("core", "trial", days(0.3))],
            # Scenario 2 — finished 3 days ago.
            "expired-3":      [("core", "trial", days(-3.2))],
            # Finished long ago — in the expired set, out of a recent window.
            "expired-200":    [("core", "trial", days(-200.4))],
            # Several modules with different ends: one finished, one still live.
            # The club is still trialing until the LAST one runs out.
            "mixed-live":     [("core", "trial", days(-9.0)), ("select", "trial", days(11.5))],
            # Every module has run out — only now is the club expired, and the
            # window is the latest of them.
            "mixed-expired":  [("core", "trial", days(-30.0)), ("select", "trial", days(-4.1))],
            # A trial with no end date. No countdown, and it must never read as
            # expired — that would tell a club still on a trial it had finished.
            "open-ended":     [("core", "trial", None)],
            # An open-ended row alongside one that has run out. Still trialing.
            "open-plus-past": [("core", "trial", None), ("select", "trial", days(-6.0))],
            # Converted: the trial row became a paid one, so there is no trial.
            "converted":      [("core", "active", None)],
            # Onboarded but never trialled anything.
            "no-rows":        [],
        }
        contacts: dict[str, CommsContact] = {}
        mclubs: dict[str, MarketingClub] = {}
        orgs: dict[str, Organisation] = {}
        for label, subs in clubs.items():
            org = Organisation(id=uuid.uuid4(), name=f"{label} CC", slug=f"{label}-cc")
            db.add(org)
            orgs[label] = org
            await db.flush()
            for module, status, ends in subs:
                db.add(OrgModuleSubscription(
                    id=uuid.uuid4(), organisation_id=org.id, module_key=module,
                    status=status, trial_ends_at=ends))
            mc = MarketingClub(id=uuid.uuid4(), name=f"{label} CC",
                               grassroots_guid=f"guid-{label}", existing_org_id=org.id,
                               utm_code=f"{label}-cc", state="WA")
            db.add(mc)
            mclubs[label] = mc
            await db.flush()
            ct = CommsContact(id=uuid.uuid4(), organisation_id=outreach.id,
                              email=f"{label}@example.com", name=f"{label} Officer",
                              marketing_club_id=mc.id, source="directory")
            db.add(ct)
            contacts[label] = ct

        # A prospect in the directory that was never onboarded — no org at all.
        mc_prospect = MarketingClub(id=uuid.uuid4(), name="Prospect CC",
                                    grassroots_guid="guid-prospect", utm_code="prospect-cc")
        db.add(mc_prospect)
        await db.flush()
        db.add(CommsContact(id=uuid.uuid4(), organisation_id=outreach.id,
                            email="prospect@example.com", name="Prospect Officer",
                            marketing_club_id=mc_prospect.id, source="directory"))
        # A contact on a live trial who has unsubscribed. The send gate must keep
        # it out of every segment below, whatever the trial says.
        unsub_org = Organisation(id=uuid.uuid4(), name="Unsub CC", slug="unsub-cc")
        db.add(unsub_org)
        await db.flush()
        db.add(OrgModuleSubscription(id=uuid.uuid4(), organisation_id=unsub_org.id,
                                     module_key="core", status="trial", trial_ends_at=days(4.0)))
        mc_unsub = MarketingClub(id=uuid.uuid4(), name="Unsub CC", grassroots_guid="guid-unsub",
                                 existing_org_id=unsub_org.id, utm_code="unsub-cc")
        db.add(mc_unsub)
        await db.flush()
        db.add(CommsContact(id=uuid.uuid4(), organisation_id=outreach.id,
                            email="unsub@example.com", marketing_club_id=mc_unsub.id,
                            source="directory", subscribed=False))
        # A contact belonging to ANOTHER club's own comms (not the outreach org),
        # to prove the segment never reaches across orgs.
        db.add(CommsContact(id=uuid.uuid4(), organisation_id=orgs["ends-in-5"].id,
                            email="member@example.com", source="player"))
        await db.commit()

        print("\n── The two scenarios, as segments ─────────────────────────────")

        # ── Scenario 1: in a trial, finishing within N days ──────────────────
        got = await emails_for(db, outreach, [
            {"field": "trial_status", "op": "eq", "value": "in_trial"},
            {"field": "trial_days_left", "op": "lte", "value": 7},
        ])
        check("scenario 1 — trial ends within 7 days",
              got == {"ends-in-5@example.com", "ends-today@example.com"}, sorted(got))

        got = await emails_for(db, outreach, [{"field": "trial_days_left", "op": "lte", "value": 7}])
        check("days-left alone already implies a live trial",
              got == {"ends-in-5@example.com", "ends-today@example.com"}, sorted(got))

        got = await emails_for(db, outreach, [{"field": "trial_days_left", "op": "lte", "value": 3}])
        check("a tighter window drops the 5-day club", got == {"ends-today@example.com"}, sorted(got))

        got = await emails_for(db, outreach, [{"field": "trial_days_left", "op": "lte", "value": 14}])
        check("widening to 14 days picks up the mixed club's live module",
              got == {"ends-in-5@example.com", "ends-today@example.com", "mixed-live@example.com"},
              sorted(got))

        got = await emails_for(db, outreach, [{"field": "trial_days_left", "op": "gte", "value": 30}])
        check("'at least 30 days left' holds fire on a club that just started",
              got == {"ends-in-40@example.com"}, sorted(got))

        # ── Scenario 2: the trial has expired ────────────────────────────────
        got = await emails_for(db, outreach, [{"field": "trial_status", "op": "eq", "value": "expired"}])
        check("scenario 2 — trial has expired",
              got == {"expired-3@example.com", "expired-200@example.com",
                      "mixed-expired@example.com"}, sorted(got))

        got = await emails_for(db, outreach, [
            {"field": "trial_days_since_expiry", "op": "lte", "value": 30}])
        check("expired in the last 30 days",
              got == {"expired-3@example.com", "mixed-expired@example.com"}, sorted(got))

        got = await emails_for(db, outreach, [
            {"field": "trial_days_since_expiry", "op": "gte", "value": 100}])
        check("expired more than 100 days ago", got == {"expired-200@example.com"}, sorted(got))

        got = await emails_for(db, outreach, [{"field": "trial_status", "op": "eq", "value": "in_trial"}])
        check("in_trial excludes every expired club and includes the open-ended ones",
              got == {"ends-in-5@example.com", "ends-in-40@example.com", "ends-today@example.com",
                      "mixed-live@example.com", "open-ended@example.com",
                      "open-plus-past@example.com"}, sorted(got))
        check("an open-ended trial reads as in a trial, not as no trial",
              "open-ended@example.com" in got, sorted(got))

        print("\n── The rules that stop a wrong email going out ────────────────")

        got = await emails_for(db, outreach, [{"field": "trial_status", "op": "eq", "value": "expired"}])
        check("an open-ended trial never reads as expired",
              "open-ended@example.com" not in got and "open-plus-past@example.com" not in got,
              sorted(got))
        got = await emails_for(db, outreach, [
            {"field": "trial_days_since_expiry", "op": "gte", "value": 0}])
        check("...not even under a bare 'expired at all' bound",
              "open-plus-past@example.com" not in got, sorted(got))
        got = await emails_for(db, outreach, [{"field": "trial_days_left", "op": "lte", "value": 999}])
        check("an open-ended trial has no days-left figure to match on either",
              "open-ended@example.com" not in got, sorted(got))

        got = await emails_for(db, outreach, [{"field": "trial_status", "op": "eq", "value": "expired"}])
        check("a club that converted is not expired", "converted@example.com" not in got, sorted(got))
        got = await emails_for(db, outreach, [{"field": "trial_status", "op": "eq", "value": "in_trial"}])
        check("a club that converted is not in a trial",
              "converted@example.com" not in got, sorted(got))

        got = await emails_for(db, outreach, [{"field": "trial_status", "op": "eq", "value": "none"}])
        check("no trial on record — converted, never-trialled, and the un-onboarded prospect",
              got == {"converted@example.com", "no-rows@example.com", "prospect@example.com"},
              sorted(got))

        got = await emails_for(db, outreach, [{"field": "trial_days_left", "op": "lte", "value": 365}])
        check("an unsubscribed contact is never reachable, trial or not",
              "unsub@example.com" not in got, sorted(got))

        got = await emails_for(db, outreach, [{"field": "trial_status", "op": "eq", "value": "none"}])
        check("a member of another club's own comms never appears",
              "member@example.com" not in got, sorted(got))

        got = await emails_for(db, outreach, [
            {"field": "trial_days_left", "op": "lte", "value": 7},
            {"field": "club_state", "op": "eq", "value": "WA"},
        ])
        check("composes with an existing directory field",
              got == {"ends-in-5@example.com", "ends-today@example.com"}, sorted(got))

        # The screen shows a live count as the rule is built, off the same query.
        n = await comms_segments.count(db, outreach, {"match": "all", "rules": [
            {"field": "trial_days_left", "op": "lte", "value": 7}]})
        check("the live count agrees with the resolved list", n == 2, n)
        n = await comms_segments.count(db, outreach, {"match": "all", "rules": [
            {"field": "trial_status", "op": "eq", "value": "expired"}]})
        check("...for the expired side too", n == 3, n)

        got = await emails_for(db, outreach, [
            {"field": "trial_days_left", "op": "lte", "value": "not a number"}])
        check("junk in the box filters nothing rather than emptying the audience",
              len(got) == 12, len(got))

        print("\n── The parameters, and their agreement with the audience ──────")

        for label, expect_left, expect_since in [
            ("ends-in-5", "5", ""), ("ends-today", "0", ""), ("ends-in-40", "40", ""),
            ("expired-3", "", "3"), ("expired-200", "", "200"),
            ("mixed-live", "", ""), ("mixed-expired", "", "4"),
            ("open-ended", "", ""), ("converted", "", ""), ("no-rows", "", ""),
        ]:
            v = await _send_vars(db, contacts[label], mclubs[label])
            if label == "mixed-live":
                expect_left = "11"
            ok = v.get("trial_days_left") == expect_left and \
                v.get("trial_days_since_expiry") == expect_since
            check(f"{label}: left={expect_left!r} since={expect_since!r}", ok,
                  f"got left={v.get('trial_days_left')!r} since={v.get('trial_days_since_expiry')!r}")

        v = await _send_vars(db, contacts["no-rows"], mclubs["no-rows"])
        check("a club with no trial renders BLANK, never 0",
              v["trial_days_left"] == "" and v["trial_days_since_expiry"] == "",
              f"{v['trial_days_left']!r}/{v['trial_days_since_expiry']!r}")

        v = await _send_vars(db, contacts["ends-in-5"], mclubs["ends-in-5"])
        expected_date = ctw.TrialWindow(days(5.4)).ends_at.strftime("%-d %B %Y")
        check("the end date is spelled out for an email read the next morning",
              v["trial_end_date"] == expected_date, f"{v['trial_end_date']!r}")

        # The whole point: the figure the email prints IS the boundary the
        # audience was picked on.
        for label, n in [("ends-in-5", 5), ("ends-today", 0), ("mixed-live", 11)]:
            inside = await emails_for(db, outreach, [
                {"field": "trial_days_left", "op": "lte", "value": n}])
            outside = await emails_for(db, outreach, [
                {"field": "trial_days_left", "op": "lte", "value": n - 1}])
            addr = f"{label}@example.com"
            check(f"{label}: the printed figure is exactly the segment boundary",
                  addr in inside and addr not in outside,
                  f"in<={n}: {addr in inside}, in<={n-1}: {addr in outside}")

        for label, n in [("expired-3", 3), ("mixed-expired", 4), ("expired-200", 200)]:
            inside = await emails_for(db, outreach, [
                {"field": "trial_days_since_expiry", "op": "gte", "value": n}])
            outside = await emails_for(db, outreach, [
                {"field": "trial_days_since_expiry", "op": "gte", "value": n + 1}])
            addr = f"{label}@example.com"
            check(f"{label}: the printed since-figure is exactly the segment boundary",
                  addr in inside and addr not in outside,
                  f"in>={n}: {addr in inside}, in>={n+1}: {addr in outside}")

        print("\n── SQL and Python agree on the day count ──────────────────────")
        w = ctw.trial_window_subquery()
        rows = (await db.execute(select(
            w.c.org_id, w.c.ends_at, w.c.has_trial,
            ctw.days_left_sql(w.c.ends_at), ctw.days_since_sql(w.c.ends_at)))).all()
        dated = [r for r in rows if r[1] is not None]
        mism_left = [(r[0], ctw.days_left(r[1]), int(r[3])) for r in dated
                     if ctw.days_left(r[1]) != int(r[3])]
        mism_since = [(r[0], ctw.days_since(r[1]), int(r[4])) for r in dated
                      if ctw.days_since(r[1]) != int(r[4])]
        check("days-left: FLOOR in SQL == timedelta.days in Python, every dated row",
              not mism_left and len(dated) >= 8, mism_left or f"{len(dated)} dated rows")
        check("days-since: the two agree too, and are NOT the negation of days-left",
              not mism_since and any(ctw.days_since(r[1]) != -ctw.days_left(r[1])
                                     for r in dated if ctw.days_left(r[1]) < 0),
              mism_since)
        check("every club with a trial row carries the has_trial marker",
              all(r[2] is True for r in rows) and len(rows) == 10, len(rows))

        print("\n── Rendered into a real email ─────────────────────────────────")
        body = ("<p>Hi {{first_name}}, {{club}} has {{trial_days_left}} days left "
                "(ends {{trial_end_date}}).</p>")
        subject, html, txt = _render_parts(
            outreach, subject="{{club}}: {{trial_days_left}} days to go", body_html=body,
            utm={}, email=contacts["ends-in-5"].email, name=contacts["ends-in-5"].name,
            unsub_url="https://example.com/u", footer="",
            extra_vars=await _send_vars(db, contacts["ends-in-5"], mclubs["ends-in-5"]))
        check("the days figure lands in the body", "has 5 days left" in html, html[:200])
        check("the end date lands in the body", f"ends {expected_date}" in html, html[:200])
        check("and in the subject line", subject == "ends-in-5 CC: 5 days to go", subject)
        check("no raw token survives", "{{" not in html and "{{" not in subject, html[:200])

        subject2, html2, _ = _render_parts(
            outreach, subject="s", body_html="<p>[{{trial_days_left}}]</p>", utm={},
            email=contacts["expired-3"].email, name=None, unsub_url="https://example.com/u",
            footer="", extra_vars=await _send_vars(db, contacts["expired-3"], mclubs["expired-3"]))
        check("an inapplicable figure renders empty, not as a stray token",
              "[]" in html2, html2[:200])

        # The real send resolves the whole batch in one query while the preview
        # resolves one club at a time; both feed the same _contact_vars builder,
        # so the two must agree contact for contact.
        from app.routers.comms import _contact_vars
        batch = await ctw.vars_by_marketing_club(db, list(mclubs.values()))
        drift = [label for label, mc in mclubs.items()
                 if _contact_vars(mc, contacts[label].merge_vars, batch[mc.id])
                 != await _send_vars(db, contacts[label], mc)]
        check("the batched send and the one-at-a-time preview agree for every club",
              not drift and len(batch) == len(mclubs), drift or len(batch))

        prospect_ct = (await db.execute(select(CommsContact).where(
            CommsContact.email == "prospect@example.com"))).scalars().one()
        v = await _send_vars(db, prospect_ct, mc_prospect)
        check("a never-onboarded prospect still resolves the vars to blank",
              all(v.get(k) == "" for k in ctw.TRIAL_VAR_KEYS), v)

        print("\n── The variables are offered to the editor ────────────────────")
        names = [x["name"] for x in MERGE_VARIABLES]
        check("all three are listed as merge variables",
              all(k in names for k in ctw.TRIAL_VAR_KEYS), names)
        check("all three are marketing-only",
              all(x["marketing_only"] for x in MERGE_VARIABLES if x["name"] in ctw.TRIAL_VAR_KEYS))
        keys = _context_var_keys(outreach)
        check("they appear in the outreach context", all(k in keys for k in ctw.TRIAL_VAR_KEYS), keys)
        club_keys = _context_var_keys(orgs["ends-in-5"])
        check("and NOT in an ordinary club's context",
              not any(k in club_keys for k in ctw.TRIAL_VAR_KEYS), club_keys)

        merged = _apply_overrides(
            {"club": "Real CC", "trial_days_left": "5"},
            {"club": "Typed CC", "trial_days_left": "99"})
        check("a per-contact override can rename the club",
              merged["club"] == "Typed CC", merged)
        check("but cannot rewrite the trial figure the audience was picked on",
              merged["trial_days_left"] == "5", merged)

        print("\n── Super-admin only, enforced on the server ───────────────────")
        # A club officer's own Segments screen cannot build these rules, so a
        # request carrying one is hand-made. It must FAIL CLOSED — dropping the
        # rule would widen the audience to the club's whole list.
        club_org = orgs["ends-in-5"]
        db.add(CommsContact(id=uuid.uuid4(), organisation_id=club_org.id,
                            email="member2@example.com", source="player"))
        await db.commit()
        own = await emails_for(db, club_org, [])
        check("the club has an audience of its own to widen to", len(own) == 2, sorted(own))
        for field, op, value in [("trial_days_left", "lte", 7),
                                 ("trial_status", "eq", "expired"),
                                 ("trial_days_since_expiry", "gte", 0)]:
            got = await emails_for(db, club_org, [{"field": field, "op": op, "value": value}])
            check(f"a club naming {field} reaches nobody, not everybody", got == set(), sorted(got))
        got = await emails_for(db, club_org, [
            {"field": "source", "op": "eq", "value": "player"},
            {"field": "trial_status", "op": "eq", "value": "in_trial"},
        ])
        check("one directory rule fails the whole segment closed", got == set(), sorted(got))
        n = await comms_segments.count(db, club_org, {"match": "all", "rules": [
            {"field": "trial_days_left", "op": "lte", "value": 7}]})
        check("the club's live count says nobody too", n == 0, n)
        got = await emails_for(db, club_org, [{"field": "source", "op": "eq", "value": "player"}])
        check("...while the club's OWN rules keep working untouched",
              got == {"member@example.com", "member2@example.com"}, sorted(got))
        # The trial fields would already resolve to nobody for a club, because
        # their MarketingClub join is empty — so those checks alone cannot tell a
        # deliberate guard from an accident. `emailed` has no such join and DOES
        # evaluate in a club context, so it is the one that proves the guard is
        # load-bearing rather than redundant.
        got = await emails_for(db, club_org, [{"field": "emailed", "op": "eq", "value": "no"}])
        check("a directory field that WOULD have evaluated for a club is stopped too",
              got == set(), sorted(got))

        check("only the outreach org may build on the directory fields",
              comms_segments.directory_rules_allowed(outreach)
              and not comms_segments.directory_rules_allowed(club_org))

        from app.routers.comms import SegmentIn, create_segment, _reject_foreign_rules
        from fastapi import HTTPException as _HTTPException
        trial_def = {"match": "all", "rules": [{"field": "trial_days_left", "op": "lte", "value": 7}]}
        try:
            await create_segment(SegmentIn(name="Ending soon", definition=trial_def),
                                 None, club_org, db)
            check("a club cannot SAVE a segment built on a trial rule", False, "it saved")
        except _HTTPException as e:
            check("a club cannot SAVE a segment built on a trial rule",
                  e.status_code == 422 and "trial_days_left" in str(e.detail), e.detail)
        saved = await create_segment(SegmentIn(name="Ending soon", definition=trial_def),
                                     None, outreach, db)
        check("...and the outreach org still can", saved["definition"] == trial_def, saved)
        _reject_foreign_rules(club_org, {"match": "all", "rules": [
            {"field": "source", "op": "eq", "value": "player"}]})
        check("a club's own rules are never refused", True)

        print("\n── The club scope never sees any of this ──────────────────────")
        # The hard scope rule (PROJECT_RULES.md): the directory field set must
        # never be reachable from a club build, so the trial fields belong to it
        # alone — a club's own members all share one club, and its trial state is
        # BetterCricket's sales data, not the club's.
        check("the trial fields are directory-only in the engine",
              not (comms_segments.DIR_TRIAL_FIELDS & (
                  comms_segments.CONTACT_FIELDS | comms_segments.PLAYER_FIELDS |
                  comms_segments.STAT_FIELDS | comms_segments.SPECIAL_FIELDS)))
        check("and are whitelisted, so a rule naming one is actually evaluated",
              comms_segments.DIR_TRIAL_FIELDS <= comms_segments.ALL_FIELDS)
        defs_src = open(os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "frontend/src/pages/admin/bettercomms/segmentFields.jsx")).read()
        club_block = defs_src.split("export const CLUB_FIELD_DEFS")[1].split(
            "export const DIRECTORY_FIELD_DEFS")[0]
        dir_block = defs_src.split("export const DIRECTORY_FIELD_DEFS")[1]
        check("the picker offers all three in the directory field set",
              all(f"  {k}:" in dir_block for k in
                  ("trial_status", "trial_days_left", "trial_days_since_expiry")))
        check("and offers none of them in the club field set",
              "trial_" not in club_block)
        # An unknown {{token}} is left in the email verbatim, so the editor's own
        # warning has to know these three.
        from app.routers.comms import campaign_warnings
        check("the editor does not warn about them as unknown variables",
              campaign_warnings("", "{{trial_days_left}} {{trial_days_since_expiry}} "
                                    "{{trial_end_date}}", {}) == [],
              campaign_warnings("", "{{trial_days_left}}", {}))

    await engine.dispose()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed")
    for f in FAIL:
        print(f"  FAILED: {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
