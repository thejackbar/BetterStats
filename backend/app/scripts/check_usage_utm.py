"""Report how site visits (usage breadcrumbs) tie back to directory clubs by UTM.

The Clubs Directory marks a prospect club as "visited" when a public page_view
carries the club's `utm_code`. An outreach email can tag that code into either
`usage_events.utm_id` (the auto-appended ?utm_id=…) or `usage_events.utm_source`
(when the campaign sets utm_source={{utm_code}}, which is how outreach is sent in
practice, e.g. ?utm_source=pinjarra-cricket-club&utm_medium=email). The directory
matches on EITHER column.

This script is read-only. It prints where the codes are landing and how many
clubs match, so you can confirm the directory will populate (and spot any codes
that don't line up with a club).

Usage from the backend container:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.check_usage_utm
"""

import asyncio

from sqlalchemy import text

from app.models.db import async_session_maker


async def main() -> None:
    async with async_session_maker() as s:
        async def sc(q):
            return (await s.scalar(text(q))) or 0

        base = "FROM usage_events ue WHERE ue.event_type = 'page_view'"
        print("Page-view breadcrumbs")
        print("  total:                         ", await sc("SELECT COUNT(*) " + base))
        print("  utm_id column set:             ", await sc("SELECT COUNT(*) " + base + " AND ue.utm_id IS NOT NULL"))
        print("  utm_source column set:         ", await sc("SELECT COUNT(*) " + base + " AND ue.utm_source IS NOT NULL"))

        print("\nClubs the directory shows as visited")
        print("  via utm_id only:               ", await sc(
            "SELECT COUNT(*) FROM marketing_clubs mc WHERE EXISTS ("
            "SELECT 1 " + base + " AND ue.utm_id = mc.utm_code)"))
        print("  via utm_id OR utm_source (live):", await sc(
            "SELECT COUNT(*) FROM marketing_clubs mc WHERE EXISTS ("
            "SELECT 1 " + base + " AND (ue.utm_id = mc.utm_code OR ue.utm_source = mc.utm_code))"))

        print("\nCodes seen on visits that MATCH a club (top 25):")
        for r in (await s.execute(text(
            "SELECT code, SUM(n) AS views FROM ("
            "  SELECT ue.utm_id AS code, COUNT(*) n " + base + " AND ue.utm_id IS NOT NULL "
            "  AND EXISTS (SELECT 1 FROM marketing_clubs mc WHERE mc.utm_code = ue.utm_id) GROUP BY 1 "
            "  UNION ALL "
            "  SELECT ue.utm_source AS code, COUNT(*) n " + base + " AND ue.utm_source IS NOT NULL "
            "  AND EXISTS (SELECT 1 FROM marketing_clubs mc WHERE mc.utm_code = ue.utm_source) GROUP BY 1 "
            ") t GROUP BY code ORDER BY views DESC LIMIT 25"))).all():
            print(f"   {int(r.views):>6}  {r.code}")

        print("\nCodes seen on visits that match NO club (top 25 — likely a typo / "
              "unregistered club):")
        rows = (await s.execute(text(
            "SELECT code, SUM(n) AS views FROM ("
            "  SELECT ue.utm_id AS code, COUNT(*) n " + base + " AND ue.utm_id IS NOT NULL "
            "  AND ue.utm_id ~* 'cricket|club' "
            "  AND NOT EXISTS (SELECT 1 FROM marketing_clubs mc WHERE mc.utm_code = ue.utm_id) GROUP BY 1 "
            "  UNION ALL "
            "  SELECT ue.utm_source AS code, COUNT(*) n " + base + " AND ue.utm_source IS NOT NULL "
            "  AND ue.utm_source ~* 'cricket|club' "
            "  AND NOT EXISTS (SELECT 1 FROM marketing_clubs mc WHERE mc.utm_code = ue.utm_source) GROUP BY 1 "
            ") t GROUP BY code ORDER BY views DESC LIMIT 25"))).all()
        if rows:
            for r in rows:
                print(f"   {int(r.views):>6}  {r.code}")
        else:
            print("   (none)")


if __name__ == "__main__":
    asyncio.run(main())
