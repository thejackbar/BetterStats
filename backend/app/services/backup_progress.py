"""Live progress reporting for a running backup/restore task.

Writes into `backup_tasks.progress` (migration 171), a small JSONB blob:
  {"stage": "players", "current": 176, "total": 876,
   "message": "Processing Player 176 of 876",
   "stage_results": {"players": 876, "games": 3957, ...}}

`set_progress` is called often (once per table for a whole-DB pg_dump/
pg_restore, once per row-batch for a per-club restore) so it commits its own
small transaction each time rather than piggybacking on the caller's -
callers should not assume their own transaction is still open afterwards.

Honest limitation: pg_dump/pg_restore don't expose row-level progress within
a table (only "now starting table X"), so whole-database backup and full
restore report TABLE-level progress (table N of M) with each table's known
row count shown once that table starts. Per-club restore is the one place
this reports true row-level progress ("Processing player 176 of 876"),
because that code writes rows itself in Python and can count as it goes.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_progress(session: AsyncSession, task_id: str, *, stage: str,
                        current: int, total: int, message: str | None = None) -> None:
    msg = message or f"Processing {stage} {current} of {total}"
    await session.execute(text("""
        UPDATE backup_tasks
        SET progress = COALESCE(progress, '{}'::jsonb)
            || jsonb_build_object('stage', :stage::text, 'current', :current::int,
                                   'total', :total::int, 'message', :message::text)
        WHERE id = :id
    """), {"stage": stage, "current": current, "total": total, "message": msg, "id": task_id})
    await session.commit()


async def mark_stage_done(session: AsyncSession, task_id: str, stage: str, count: int) -> None:
    """Records a finished stage's final count into progress.stage_results,
    e.g. {"players": 876} — shown as "Players backed up/restored: 876" once
    the stage completes."""
    await session.execute(text("""
        UPDATE backup_tasks
        SET progress = jsonb_set(
            COALESCE(progress, '{}'::jsonb),
            ARRAY['stage_results', :stage]::text[],
            to_jsonb(:count::bigint),
            true
        )
        WHERE id = :id
    """), {"stage": stage, "count": count, "id": task_id})
    await session.commit()
