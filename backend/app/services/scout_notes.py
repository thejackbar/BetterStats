"""BetterScout — the player profile's Scouting notes timeline."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scout import ScoutPlayerNote, ScoutUser

KINDS = {"watched_live", "phone", "scorecard_review", "other"}


def _note_out(note: ScoutPlayerNote, author_name: str | None) -> dict:
    return {
        "id": str(note.id),
        "body": note.body,
        "kind": note.kind,
        "author_name": author_name,
        "occurred_at": note.occurred_at.isoformat(),
        "created_at": note.created_at.isoformat(),
    }


async def list_notes(session: AsyncSession, scout_org_id: str, scouted_player_id: str) -> list[dict]:
    res = await session.execute(
        select(ScoutPlayerNote, ScoutUser.display_name, ScoutUser.username)
        .join(ScoutUser, ScoutUser.id == ScoutPlayerNote.author_scout_user_id, isouter=True)
        .where(
            ScoutPlayerNote.scout_org_id == scout_org_id,
            ScoutPlayerNote.scouted_player_id == scouted_player_id,
        )
        .order_by(ScoutPlayerNote.occurred_at.desc())
    )
    return [_note_out(n, display_name or username) for n, display_name, username in res.all()]


async def create_note(
    session: AsyncSession, scout_org_id: str, scouted_player_id: str, author_id: str,
    body: str, kind: str = "other",
) -> dict:
    body = (body or "").strip()
    if not body:
        raise ValueError("Note text is required.")
    if kind not in KINDS:
        raise ValueError("Unknown note kind.")
    note = ScoutPlayerNote(
        scout_org_id=scout_org_id, scouted_player_id=scouted_player_id,
        author_scout_user_id=author_id, body=body, kind=kind,
    )
    session.add(note)
    await session.flush()
    author = await session.get(ScoutUser, author_id)
    await session.commit()
    return _note_out(note, author.display_name or author.username if author else None)


async def _get_owned_note(session: AsyncSession, note_id: str, scout_org_id: str) -> ScoutPlayerNote:
    note = await session.get(ScoutPlayerNote, note_id)
    if not note or str(note.scout_org_id) != str(scout_org_id):
        raise ValueError("Note not found.")
    return note


async def update_note(session: AsyncSession, note_id: str, scout_org_id: str, body: str | None = None, kind: str | None = None) -> dict:
    note = await _get_owned_note(session, note_id, scout_org_id)
    if body is not None:
        body = body.strip()
        if not body:
            raise ValueError("Note text is required.")
        note.body = body
    if kind is not None:
        if kind not in KINDS:
            raise ValueError("Unknown note kind.")
        note.kind = kind
    await session.commit()
    author = await session.get(ScoutUser, note.author_scout_user_id) if note.author_scout_user_id else None
    return _note_out(note, author.display_name or author.username if author else None)


async def delete_note(session: AsyncSession, note_id: str, scout_org_id: str) -> None:
    note = await _get_owned_note(session, note_id, scout_org_id)
    await session.delete(note)
    await session.commit()
