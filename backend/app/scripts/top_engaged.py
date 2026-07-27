"""List the highest-scoring clubs with a full score breakdown, so a cluster of
top scores (e.g. the pile at 95-100) can be sanity-checked club by club rather
than tuned blind: is a 100 deserved (heavy real activity) or over-credited
(over-broad attribution, a shared officer email matching many clubs)?

Read-only: it re-runs twenty_sync._engagement per club to pull the internal
breakdown fields, but never commits (rolls back at the end).

USAGE (inside the backend container)
    python -m app.scripts.top_engaged                 # top 25, prospects + linked
    python -m app.scripts.top_engaged --top 40        # top 40
    python -m app.scripts.top_engaged --prospects     # directory-only prospects
    python -m app.scripts.top_engaged --min 90        # only clubs scoring >= 90
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.db import MarketingClub, Organisation, async_session_maker
from app.services.twenty_sync import _engagement


async def _load_org(session, org_id):
    if not org_id:
        return None
    return await session.get(
        Organisation, org_id,
        options=[selectinload(Organisation.module_subscriptions)])


def _flags(club, eng) -> str:
    out = []
    if eng.get("_directEnquiryHot"):
        out.append("ENQUIRY-HOT")
    elif eng.get("_onboardingRequested"):
        out.append("enquiry")
    if club.requested_trial_modules:
        out.append("requested_trial")
    if (club.demo_status or "") == "in_trial":
        out.append("in_trial")
    if eng.get("_adSignup"):
        out.append("ad_signup")
    td = eng.get("_trialDepth")
    if td and td.get("score"):
        out.append(f"trial_depth={td['score']}")
    return ",".join(out) or "-"


async def run(*, top: int, prospects_only: bool, min_score: int | None) -> None:
    async with async_session_maker() as session:
        q = (select(MarketingClub.id)
             .where(MarketingClub.engagement_score.isnot(None))
             .order_by(MarketingClub.engagement_score.desc()))
        if prospects_only:
            q = q.where(MarketingClub.existing_org_id.is_(None))
        if min_score is not None:
            q = q.where(MarketingClub.engagement_score >= min_score)
        q = q.limit(top)
        ids = [r[0] for r in (await session.execute(q)).all()]

        header = (f"{'#':>3}  {'score':>5}  {'tier':<4}  {'sess':>4}  {'em30':>4}  "
                  f"{'web':>6}  {'email':>6}  {'ad':>5}  {'freq':>6}  {'rec':>4}   club  [flags]")
        print(header)
        print("-" * len(header))
        for i, cid in enumerate(ids, 1):
            club = await session.get(MarketingClub, cid)
            org = await _load_org(session, club.existing_org_id)
            eng = await _engagement(session, club, org)
            g = lambda k: float(eng.get(k) or 0)  # noqa: E731 — terse local formatter
            mark = "*" if club.existing_org_id else " "   # * = linked (onboarded/customer)
            flags = _flags(club, eng)
            tail = (club.name or "?")[:32] + (f"  [{flags}]" if flags != "-" else "")
            print(f"{i:>3}  {eng.get('engagementScore'):>5}  "
                  f"{(eng.get('engagementTier') or ''):<4}  "
                  f"{eng.get('sessions30d', 0):>4}  {eng.get('emailEngaged30d', 0):>4}  "
                  f"{g('_webDecayPts'):>6.1f}  {g('_emailDecayPts'):>6.1f}  "
                  f"{g('_adDecayPts'):>5.1f}  {g('_freqPts'):>6.1f}  "
                  f"{g('_recencyPts'):>4.1f}   {mark}{tail}")
        print("\n  * = linked (onboarded/customer). email/ad points are 0 when SES "
              "open/click tracking is off. freq can exceed 100 (it's pre-clamp).")
        await session.rollback()  # read-only


def main() -> None:
    ap = argparse.ArgumentParser(description="List top-scoring clubs with breakdown.")
    ap.add_argument("--top", type=int, default=25, help="how many to list (default 25)")
    ap.add_argument("--prospects", action="store_true",
                    help="directory-only prospects (exclude linked/onboarded clubs)")
    ap.add_argument("--min", type=int, default=None, dest="min_score",
                    help="only clubs scoring at or above this")
    args = ap.parse_args()
    asyncio.run(run(top=args.top, prospects_only=args.prospects, min_score=args.min_score))


if __name__ == "__main__":
    main()
