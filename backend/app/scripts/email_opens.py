#!/usr/bin/env python3
"""How many BetterComms emails have been opened, to date.

Reads the ``email_events`` table (where SES delivery / open / click events are
stored) plus ``comms_recipients`` (what we sent), and prints sent / delivered /
unique-opened / open-rate overall, then a per-campaign breakdown.

MUST run inside the backend container (it uses the app's DB connection). No
restart needed — pipe it into the running container:

    cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
    docker compose exec -T betterstats-backend python - < email_opens.py

Read-only.

IMPORTANT — open tracking has to be ON at the AWS end for any of this to be
non-zero. SES only emits 'open' events when the configuration set has
"Open and click tracking" enabled (it injects a 1x1 tracking pixel). If every
number below is 0 opens, that's almost certainly why — enable engagement
tracking on the bettercricket-transactional / bettercricket-campaigns config
sets in the SES console. Also note open tracking undercounts: a recipient whose
client blocks remote images (or Apple Mail Privacy Protection, which pre-fetches
and inflates) makes the pixel unreliable — treat opens as indicative, not exact.
"""
import asyncio
import sys

sys.path.insert(0, "/app")  # so `from app...` works however the container invokes us

from sqlalchemy import text  # noqa: E402
from app.models.db import async_session_maker  # noqa: E402


def _pct(a, b):
    return "%.1f%%" % (100.0 * a / b) if b else "n/a"


async def main():
    async with async_session_maker() as s:
        sent = int(await s.scalar(text(
            "SELECT count(*) FROM comms_recipients WHERE status='sent'")) or 0)
        delivered = int(await s.scalar(text(
            "SELECT count(DISTINCT recipient_id) FROM email_events "
            "WHERE event_type='delivery' AND recipient_id IS NOT NULL")) or 0)
        opened_unique = int(await s.scalar(text(
            "SELECT count(DISTINCT recipient_id) FROM email_events "
            "WHERE event_type='open' AND recipient_id IS NOT NULL")) or 0)
        open_events = int(await s.scalar(text(
            "SELECT count(*) FROM email_events WHERE event_type='open'")) or 0)
        clicked_unique = int(await s.scalar(text(
            "SELECT count(DISTINCT recipient_id) FROM email_events "
            "WHERE event_type='click' AND recipient_id IS NOT NULL")) or 0)

        print("BetterComms email opens — all time")
        print("  Sent (recipients)        : %s" % f"{sent:,}")
        print("  Delivered (SES 'delivery'): %s" % f"{delivered:,}")
        print("  Opened (unique people)   : %s   (%s of delivered, %s of sent)"
              % (f"{opened_unique:,}", _pct(opened_unique, delivered), _pct(opened_unique, sent)))
        print("  Open events (incl repeat): %s" % f"{open_events:,}")
        print("  Clicked (unique people)  : %s   (%s of delivered)"
              % (f"{clicked_unique:,}", _pct(clicked_unique, delivered)))

        rows = (await s.execute(text("""
            SELECT c.subject,
                   (SELECT count(*) FROM comms_recipients r
                      WHERE r.campaign_id = c.id AND r.status='sent')            AS sent,
                   (SELECT count(DISTINCT e.recipient_id) FROM email_events e
                      WHERE e.campaign_id = c.id AND e.event_type='open')        AS opened
            FROM comms_campaigns c
            WHERE c.status IN ('sent','sending')
            ORDER BY c.sent_at DESC NULLS LAST
            LIMIT 30
        """))).all()

        if rows:
            print()
            print("Per campaign (most recent 30):")
            print("  %-46s %8s %8s %8s" % ("subject", "sent", "opened", "rate"))
            for subj, csent, copened in rows:
                csent = int(csent or 0)
                copened = int(copened or 0)
                label = (subj or "(no subject)")[:46]
                print("  %-46s %8s %8s %8s"
                      % (label, f"{csent:,}", f"{copened:,}", _pct(copened, csent)))

        if opened_unique == 0:
            print()
            print("0 opens recorded. If you've sent real emails, open tracking is")
            print("probably OFF on the SES configuration set — enable 'Open and click")
            print("tracking' on it in the SES console and future sends will report opens.")


if __name__ == "__main__":
    asyncio.run(main())
