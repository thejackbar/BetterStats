"""One-off diagnostic: why isn't club X showing in the Sales Workspace queue?

Walks the exact gate chain routers/sales_workspace.list_clubs applies, for one
or more named clubs, and prints where each of the club's deals stops. Two kinds
of gate, reported separately because they need different fixes:

  * HARD gates — the queue's own SQL/logic (platform pipeline, not archived,
    status open, stage not terminal). A deal failing one of these is invisible
    no matter what a rep ticks on screen, and the Sales Pipeline board can
    still be showing it, since that board filters on none of them by default.
  * FILTER gates — the pickers on the screen. The club is in the queue; the
    viewer's own saved filters are hiding it. Every super-admin/sales user's
    stored Call Status preference is printed so it is obvious whose.

Read-only. Makes no writes.

Usage on the server (name match is case-insensitive substring). Run it through
`docker compose` from /srv/docker with the project name set, per the repo's own
deploy rules — a bare `docker exec` falls outside the pinned project:

  cd /srv/docker
  export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.diagnose_workspace_visibility "caboolture"
"""
import asyncio
import sys

from sqlalchemy import select

from app.models.db import (
    ClubMembership, CrmActivity, CrmDeal, CrmStage, MarketingClub, User,
    async_session_maker,
)
from app.services import crm as crm_service
from app.services import sales_workspace as sw

CALL_STATUS_PREF = "sales_call_status_filters"  # mirrors SalesWorkspace.jsx
ALL_STATUSES = list(sw.CALL_STATUS_KEYS)


async def _viewer_filters(session) -> None:
    """Every super admin / sales user's saved Call Status boxes. The screen
    persists these per account (not localStorage), so one rep can have a club
    hidden while another sees it on the same data."""
    rows = (await session.execute(
        select(User).where(
            User.id.in_(select(ClubMembership.user_id).where(
                ClubMembership.role.in_(("sales", "super_admin", "club_admin"))))
        )
    )).scalars().all()
    printed = False
    for u in rows:
        saved = (u.ui_preferences or {}).get(CALL_STATUS_PREF)
        if not isinstance(saved, dict):
            continue
        off = [k for k in ALL_STATUSES if saved.get(k, True) is not True]
        if not off:
            continue
        if not printed:
            print("\n--- Saved Call Status filters that HIDE clubs ---")
            printed = True
        print(f"  {u.display_name or u.username}: unticked {', '.join(off)}")
    if not printed:
        print("\n--- No saved Call Status filter is hiding anything "
              "(every box ticked, or never touched) ---")


async def diagnose(name_query: str) -> None:
    async with async_session_maker() as session:
        clubs = (await session.execute(
            select(MarketingClub).where(MarketingClub.name.ilike(f"%{name_query}%"))
        )).scalars().all()
        if not clubs:
            print(f"No club matching {name_query!r} in marketing_clubs. "
                  "The Sales Workspace only lists CRM deals, and a deal is "
                  "normally attached to a directory club — so there is nothing "
                  "for the queue to show.")
            return

        pipeline = await crm_service.ensure_platform_pipeline(session)
        stage_by_id = {s.id: s for s in pipeline.stages}

        for club in clubs:
            print(f"\n=== {club.name} ({club.id}) ===")
            print(f"  state={club.state!r} engagement_score={club.engagement_score} "
                  f"excluded={club.excluded} not_interested={club.not_interested}")

            # EVERY deal, including archived / closed / other pipelines — the
            # point is to find the one the board is showing and say why the
            # queue isn't.
            deals = (await session.execute(
                select(CrmDeal).where(CrmDeal.marketing_club_id == club.id)
                .order_by(CrmDeal.created_at)
            )).scalars().all()
            if not deals:
                print("  NO CRM DEAL AT ALL for this club. An engagement score "
                      "lives on the directory row, not on a deal — a score of "
                      "100 by itself never puts a club in the queue.")
                continue

            for deal in deals:
                stage = stage_by_id.get(deal.stage_id) or await session.get(CrmStage, deal.stage_id)
                stage_key = stage.key if stage else None
                print(f"\n  deal {deal.id}")
                print(f"    scope={deal.scope!r} source={deal.source!r} "
                      f"stage={stage_key!r} status={deal.status!r} "
                      f"archived_at={deal.archived_at} owner={deal.owner_user_id} "
                      f"attributed={deal.commission_rep_user_id}")

                blockers = []
                if deal.pipeline_id != pipeline.id:
                    blockers.append(
                        f"HARD: not on the platform pipeline (pipeline_id="
                        f"{deal.pipeline_id}). The queue only ever reads the "
                        "platform pipeline.")
                if deal.archived_at is not None:
                    blockers.append(
                        "HARD: archived. list_deals excludes archived rows. "
                        "Note maybe_sync_pipeline_membership auto-archives an "
                        "auto-added deal still parked at Target once its score "
                        "falls below the remove threshold.")
                stage_terminal = bool(stage and (stage.is_won or stage.is_lost))
                # A non-open status on a TERMINAL stage is the two agreeing, so
                # the stage line below says it once. Worth its own finding only
                # when they disagree, which is the case the board can still show.
                if deal.status != "open" and not stage_terminal:
                    blockers.append(
                        f"HARD: status is {deal.status!r}, and the queue asks "
                        "for status='open'. The Sales Pipeline board does NOT "
                        "filter on status, so it can still be showing this deal "
                        f"at {stage_key!r} while the queue hides it. Current "
                        "code keeps status and stage in step (move_stage / "
                        "close_deal / create_deal all derive it), so a "
                        "non-open status on a non-terminal stage is legacy or "
                        "hand-edited data.")
                if stage_terminal:
                    blockers.append(
                        f"HARD: stage {stage_key!r} is terminal (is_won="
                        f"{stage.is_won} is_lost={stage.is_lost}). The queue is "
                        "a calling list, so Won and Lost/Dormant are dropped.")

                if blockers:
                    for b in blockers:
                        print(f"    ✗ {b}")
                    continue

                # In the queue. Which pickers could still be hiding it?
                last_call = (await sw.last_calls_by_deal(session, [deal.id])).get(deal.id)
                follow_up = (await sw.next_follow_ups_by_deal(session, [deal.id])).get(deal.id)
                emailed = deal.id in await sw.emailed_deal_ids(session, [deal.id])
                statuses = sw.call_statuses_of(
                    ever_called=last_call is not None,
                    followup_due=follow_up is not None,
                    last_call_outcome=last_call.outcome if last_call else None,
                    sent_email=emailed,
                )
                calls = (await session.execute(
                    select(CrmActivity).where(CrmActivity.deal_id == deal.id, sw._IS_CONTACT_ROW)
                )).scalars().all()

                print("    ✓ passes every hard gate — it IS in the queue.")
                print(f"    Call Status buckets it answers to: "
                      f"{', '.join(sorted(statuses)) or '(none)'}")
                print(f"    contact rows on the timeline: {len(calls)} "
                      f"(a call, a follow-up or an email; a note is not contact)")
                if "not_called" not in statuses:
                    print("    ⚠ FILTER: this club has been CALLED, so it is "
                          "hidden whenever 'Not Contacted' is the only Call "
                          "Status box ticked. Tick 'Contacted' to see it. This "
                          "is the usual reason an Engaged club is missing — "
                          "Engaged now means a real conversation happened, so "
                          "an Engaged club is almost never 'Not Contacted'.")
                owner_note = "unassigned" if deal.owner_user_id is None else str(deal.owner_user_id)
                print(f"    Assigned picker must include: {owner_note}")
                if deal.commission_rep_user_id is None:
                    print("    Attributed picker: this deal is unattributed. "
                          "Picking any named rep there excludes it.")
                if club.engagement_score is None:
                    print("    ⚠ FILTER: no engagement score, so ANY min/max "
                          "score bound excludes it.")
                if not club.state:
                    print("    ⚠ FILTER: no state on the directory row, so any "
                          "State pick excludes it.")

        await _viewer_filters(session)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(2)
    asyncio.run(diagnose(sys.argv[1]))
