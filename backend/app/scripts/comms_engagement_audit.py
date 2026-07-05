#!/usr/bin/env python3
"""BetterComms engagement audit: unsubscribe / suppression rates, and per-UTM-
campaign click-through + pages-per-visitor.

Two reports in one:

1. Always: unsubscribe + suppression numbers and rates, read from
   comms_contacts (per-club opt-out / bounce / complaint / exclusion),
   email_suppressions (the global address-level block list, by reason) and
   comms_recipients (what we sent).

2. If you pass a utm_campaign code: how many visitors clicked through to the
   site from that campaign's links, and how many different pages they hit on
   average (their whole on-site journey), from usage_events (the site's
   page-view tracking). With NO code it lists the top campaigns so you can pick.

MUST run inside the backend container (uses the app's DB). No restart needed —
pipe it in:

    cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
    # summary + list of campaigns:
    docker compose exec -T betterstats-backend python - < comms_engagement_audit.py
    # one campaign (pass the code as an arg, before the redirect):
    docker compose exec -T betterstats-backend python - spring-2026 < comms_engagement_audit.py

Read-only.
"""
import asyncio
import statistics
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from app.models.db import async_session_maker  # noqa: E402

# Same visitor identity + UTM parsing the Usage page uses, so the numbers agree.
_VKEY = "COALESCE(ue.visitor_id::text, ue.ip_hash)"
_CAM = "lower(COALESCE(NULLIF(ue.utm_campaign, ''), substring(ue.path from 'utm_campaign=([^&]+)')))"
_PAGE = "split_part(ue.path, '?', 1)"
_PV = "ue.event_type = 'page_view' AND ue.user_id IS NULL AND " + _PAGE + " !~* '^/admin'"


def _pct(a, b):
    return "%.2f%%" % (100.0 * a / b) if b else "n/a"


def _f(n):
    return "{:,}".format(int(n or 0))


async def suppression_report(s):
    row = (await s.execute(text("""
        SELECT count(*) total,
               count(*) FILTER (WHERE subscribed)            subscribed,
               count(*) FILTER (WHERE NOT subscribed)        unsubscribed,
               count(*) FILTER (WHERE bounced)               bounced,
               count(*) FILTER (WHERE complained)            complained,
               count(*) FILTER (WHERE excluded)              excluded
        FROM comms_contacts
    """))).mappings().first()
    sent = int(await s.scalar(text(
        "SELECT count(*) FROM comms_recipients WHERE status='sent'")) or 0)
    total = int(row["total"] or 0)
    unsub = int(row["unsubscribed"] or 0)

    print("Unsubscribe / suppression — all BetterComms contacts")
    print("  Contacts total           : %s" % _f(total))
    print("  Subscribed               : %s   (%s)" % (_f(row["subscribed"]), _pct(row["subscribed"], total)))
    print("  Unsubscribed             : %s   (%s of contacts, %s of sent)"
          % (_f(unsub), _pct(unsub, total), _pct(unsub, sent)))
    print("  Bounced (flagged)        : %s   (%s of contacts)" % (_f(row["bounced"]), _pct(row["bounced"], total)))
    print("  Complained (spam)        : %s   (%s of contacts, %s of sent)"
          % (_f(row["complained"]), _pct(row["complained"], total), _pct(row["complained"], sent)))
    print("  Excluded (admin)         : %s" % _f(row["excluded"]))
    print("  Emails sent (recipients) : %s" % _f(sent))

    supp = (await s.execute(text("""
        SELECT reason, count(*) AS n FROM email_suppressions GROUP BY reason ORDER BY n DESC
    """))).mappings().all()
    total_supp = sum(int(r["n"]) for r in supp)
    print()
    print("Global suppression list (address-level, blocks every club): %s" % _f(total_supp))
    for r in supp:
        print("  %-16s %s" % (r["reason"], _f(r["n"])))
    if not supp:
        print("  (none)")


async def campaign_list(s):
    rows = (await s.execute(text(f"""
        SELECT {_CAM} AS campaign,
               COUNT(DISTINCT {_VKEY}) AS visitors,
               COUNT(*)                AS views
        FROM usage_events ue
        WHERE {_PV} AND {_CAM} IS NOT NULL AND {_CAM} <> ''
        GROUP BY campaign
        ORDER BY visitors DESC
        LIMIT 30
    """))).mappings().all()
    print()
    if not rows:
        print("No utm_campaign-tagged site visits recorded yet.")
        return
    print("Top campaigns by site visitors (pass one as an arg for the full report):")
    print("  %-40s %9s %9s" % ("utm_campaign", "visitors", "views"))
    for r in rows:
        print("  %-40s %9s %9s" % ((r["campaign"] or "")[:40], _f(r["visitors"]), _f(r["views"])))


async def campaign_report(s, code):
    code = code.strip().lower()
    per = (await s.execute(text(f"""
        SELECT {_VKEY} AS vkey,
               COUNT(DISTINCT {_PAGE}) AS pages,
               COUNT(*)                AS views
        FROM usage_events ue
        WHERE {_PV}
          AND {_VKEY} IN (
            SELECT DISTINCT {_VKEY} FROM usage_events ue
            WHERE ue.event_type = 'page_view' AND {_CAM} = :code
          )
        GROUP BY vkey
    """), {"code": code})).mappings().all()

    print()
    print("Campaign: %s" % code)
    if not per:
        print("  No visitors have clicked through from this campaign (no matching")
        print("  utm_campaign in the site's page-view tracking).")
        return
    pages = [int(r["pages"]) for r in per]
    views = [int(r["views"]) for r in per]
    print("  Visitors clicked through (distinct): %s" % _f(len(per)))
    print("  Total page views by them           : %s" % _f(sum(views)))
    print("  Different pages hit, per visitor    : avg %.2f  (median %s, max %s)"
          % (statistics.mean(pages), int(statistics.median(pages)), max(pages)))
    print("  Page views per visitor              : avg %.2f" % statistics.mean(views))

    top = (await s.execute(text(f"""
        SELECT {_PAGE} AS page, COUNT(*) AS views, COUNT(DISTINCT {_VKEY}) AS visitors
        FROM usage_events ue
        WHERE {_PV}
          AND {_VKEY} IN (
            SELECT DISTINCT {_VKEY} FROM usage_events ue
            WHERE ue.event_type = 'page_view' AND {_CAM} = :code
          )
        GROUP BY page ORDER BY visitors DESC LIMIT 15
    """), {"code": code})).mappings().all()
    print()
    print("  Pages these visitors hit (top 15):")
    print("    %-42s %8s %8s" % ("page", "visitors", "views"))
    for r in top:
        print("    %-42s %8s %8s" % ((r["page"] or "")[:42], _f(r["visitors"]), _f(r["views"])))


async def main():
    code = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] not in ("-",) else None
    async with async_session_maker() as s:
        await suppression_report(s)
        if code:
            await campaign_report(s, code)
        else:
            await campaign_list(s)


if __name__ == "__main__":
    asyncio.run(main())
