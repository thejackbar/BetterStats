"""Parsed scorecard rows, held server-side between preview and commit.

WHY THIS EXISTS. The import is preview -> resolve -> commit, and only preview
takes a file. The browser used to hold the parsed rows and post every one of
them back as JSON on the other two steps — so a club's whole history went up
the wire twice, and `resolve` fires again on EVERY override change, which is
once per player matched, season picked or grade named.

Measured on a 33 MB, 182,154-row sheet: the same rows as a JSON body are
**145.6 MB**, because all 33 column names repeat on every row. The server-side
work is not the problem — `_resolve_games` over that sheet is 1.9s — so the
whole interactive cost was the upload. Staging the rows turns a 145.6 MB
round trip per keystroke into a token and a DB read.

The rows are parsed ONCE, at preview, and stored in the shape `_resolve_games`
reads, so nothing re-parses the sheet.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# One sitting of the wizard, and no longer. A club works through the review
# screen in a single visit — the token exists to carry that visit, not to be a
# resumable draft — and a lapsed one is a whole club history sitting in a table
# nobody will come back for.
TTL = timedelta(hours=1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def sweep_expired(db: AsyncSession) -> int:
    """Drop every lapsed staging row, whoever it belongs to.

    Called on preview — the one moment somebody is already paying for a large
    write, and the only moment new rows arrive — so a lapsed archive is never
    left sitting in the table waiting on a nightly job that might not run.
    """
    res = await db.execute(text(
        "DELETE FROM manual_game_import_staging WHERE expires_at < :now"
    ), {"now": _now()})
    return res.rowcount or 0


async def store(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    rows: list[dict],
    filename: str | None,
    unknown_columns: list[str],
) -> str:
    """Stage a parsed sheet and hand back its token. Commits nothing."""
    token = secrets.token_urlsafe(24)
    await db.execute(text("""
        INSERT INTO manual_game_import_staging
            (token, organisation_id, user_id, filename, row_count,
             unknown_columns, rows, expires_at)
        VALUES (:token, :org, :user, :filename, :row_count,
                CAST(:unknown AS jsonb), CAST(:rows AS jsonb), :expires)
    """), {
        "token": token,
        "org": org_id,
        "user": user_id,
        "filename": filename,
        "row_count": len(rows),
        # Bound as text and cast, rather than handed a Python list: asyncpg
        # infers a bound parameter's type from how it is used, and a bare
        # parameter against a jsonb column gives it nothing to infer from.
        "unknown": json.dumps(unknown_columns or []),
        "rows": json.dumps(rows),
        "expires": _now() + TTL,
    })
    return token


async def load(
    db: AsyncSession,
    *,
    token: str,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict | None:
    """The staged sheet for this token, or None.

    Scoped to the club AND the user in the WHERE clause rather than fetched and
    then checked, so another club's token is indistinguishable from one that
    never existed — the same "404 tells nothing" posture the public routers
    keep. An expired row reads as absent too: the sweep is a tidy-up, never the
    thing that enforces the deadline.
    """
    row = (await db.execute(text("""
        SELECT filename, row_count, unknown_columns, rows
          FROM manual_game_import_staging
         WHERE token = :token
           AND organisation_id = :org
           AND user_id = :user
           AND expires_at >= :now
    """), {"token": token, "org": org_id, "user": user_id, "now": _now()})).mappings().first()
    if not row:
        return None
    return {
        "filename": row["filename"],
        "row_count": row["row_count"],
        "unknown_columns": row["unknown_columns"] or [],
        "rows": row["rows"] or [],
    }


async def discard(db: AsyncSession, *, token: str, org_id: uuid.UUID) -> None:
    """Drop a staged sheet once its import has landed. Commits nothing.

    Scoped to the club for the same reason `load` is. Deliberately NOT scoped
    to the user: a token that has just been committed is spent whoever presses
    the button, and leaving it behind would let the same archive be imported a
    second time.
    """
    await db.execute(text(
        "DELETE FROM manual_game_import_staging WHERE token = :token AND organisation_id = :org"
    ), {"token": token, "org": org_id})
