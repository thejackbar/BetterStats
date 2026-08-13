"""BetterScout — watchlists (Kanban boards).

Replaces the phase-2 scout_tracked_players bookmark. A Scout Org can run
several watchlists; each is a set of named columns (fully renameable/
addable/removable — a label, not a workflow state this module enforces);
each card is one player on one watchlist, carrying tags plus a handful of
scout-entered fields.

DEFAULT_COLUMNS is deliberately neutral, not a sales funnel — not every
Scout Org using this is trying to sign someone (a feeder club just wants to
monitor its own juniors), so nothing here implies an outcome.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scout import (
    ScoutClubCache,  # noqa: F401 — re-exported for callers that want the type
    ScoutOrg,
    ScoutWatchlist,
    ScoutWatchlistCard,
    ScoutWatchlistColumn,
    ScoutedPlayer,
)
from app.services import scout_billing  # tracked-player cap check, see ensure_card_on_watchlist
from app.services import scout_settings  # share-link expiry + include_notes/include_tags defaults
from app.services.scouting_intel import clean_batting_intel, clean_bowling_intel

DEFAULT_COLUMNS = ["Watching", "Shortlisted", "Under Review", "Archived"]
DEFAULT_WATCHLIST_NAME = "My Players"

# Mirrors frontend/src/lib/playerAttributes.js's option lists — kept as a
# small, explicit allow-list rather than importing JS into Python. Empty
# string/None both mean "not set".
ROLE_OPTS = {"", "Batter", "Bowler", "All Rounder", "Wicketkeeper", "Wicketkeeper-Batter"}
BAT_HAND_CODES = {"", "RIGHT", "LEFT"}
BOWLING_ACTION_CODES = {"", "RIGHT_ARM", "LEFT_ARM"}
BOWLING_TYPE_CODES = {"", "FAST", "FAST_MEDIUM", "MEDIUM", "FINGER_SPIN", "WRIST_SPIN"}

REGION_OPTS = [
    "", "WA", "NSW", "VIC", "QLD", "SA", "TAS", "NT", "ACT",
    "North England", "South England", "Midlands", "Scotland", "Wales",
    "Other/International",
]
LEVEL_OPTS = ["", "Premier Cricket", "Grade Cricket", "Community Cricket", "Junior/Colts", "Other"]

_CARD_FIELDS = {
    "tags", "role", "batting_hand", "bowling_action", "bowling_type", "region", "level",
    "transfer_preference", "visa_status", "agent_contact", "availability_window",
    "fee_expectations", "notes",
    "is_opening_batsman", "is_wicket_keeper", "fielding_position",
    "batting_intel", "bowling_intel",
}


# ─── ownership-checked loaders ─────────────────────────────────────────────

async def _get_owned_watchlist(session: AsyncSession, watchlist_id: str, scout_org_id: str) -> ScoutWatchlist:
    wl = await session.get(ScoutWatchlist, watchlist_id)
    if not wl or str(wl.scout_org_id) != str(scout_org_id):
        raise ValueError("Watchlist not found.")
    return wl


async def _get_owned_column(session: AsyncSession, column_id: str, scout_org_id: str) -> ScoutWatchlistColumn:
    col = await session.get(ScoutWatchlistColumn, column_id)
    if not col:
        raise ValueError("Column not found.")
    await _get_owned_watchlist(session, col.watchlist_id, scout_org_id)  # raises if not owned
    return col


async def _get_owned_card(session: AsyncSession, card_id: str, scout_org_id: str) -> ScoutWatchlistCard:
    card = await session.get(ScoutWatchlistCard, card_id)
    if not card:
        raise ValueError("Card not found.")
    await _get_owned_watchlist(session, card.watchlist_id, scout_org_id)
    return card


# ─── watchlists ─────────────────────────────────────────────────────────────

async def create_watchlist(session: AsyncSession, scout_org_id: str, name: str) -> ScoutWatchlist:
    wl = ScoutWatchlist(scout_org_id=scout_org_id, name=name)
    session.add(wl)
    await session.flush()
    for i, col_name in enumerate(DEFAULT_COLUMNS):
        session.add(ScoutWatchlistColumn(watchlist_id=wl.id, name=col_name, position=i))
    await session.commit()
    return wl


async def rename_watchlist(session: AsyncSession, watchlist_id: str, scout_org_id: str, name: str) -> dict:
    wl = await _get_owned_watchlist(session, watchlist_id, scout_org_id)
    wl.name = name
    await session.commit()
    return {"id": str(wl.id), "name": wl.name}


async def ensure_default_watchlist(session: AsyncSession, scout_org_id: str) -> ScoutWatchlist:
    res = await session.execute(
        select(ScoutWatchlist).where(
            ScoutWatchlist.scout_org_id == scout_org_id,
            ScoutWatchlist.name == DEFAULT_WATCHLIST_NAME,
        )
    )
    wl = res.scalar_one_or_none()
    if wl:
        return wl
    return await create_watchlist(session, scout_org_id, DEFAULT_WATCHLIST_NAME)


async def list_watchlists(session: AsyncSession, scout_org_id: str) -> list[dict]:
    res = await session.execute(
        select(ScoutWatchlist).where(ScoutWatchlist.scout_org_id == scout_org_id).order_by(ScoutWatchlist.created_at)
    )
    watchlists = res.scalars().all()
    if not watchlists:
        return []
    # A card's own created_at doubles as "last used" (cards are created, not
    # timestamped on move) — good enough for "which board did this org touch
    # most recently", which is only ever used to pick a sane default in the
    # Discover "Add to watchlist" picker, not shown as a real activity log.
    res = await session.execute(
        select(ScoutWatchlistCard.watchlist_id, func.max(ScoutWatchlistCard.created_at))
        .where(ScoutWatchlistCard.watchlist_id.in_([w.id for w in watchlists]))
        .group_by(ScoutWatchlistCard.watchlist_id)
    )
    last_card_at = {str(wid): ts for wid, ts in res.all()}
    res = await session.execute(
        select(ScoutWatchlistCard.watchlist_id, func.count(ScoutWatchlistCard.id))
        .where(ScoutWatchlistCard.watchlist_id.in_([w.id for w in watchlists]))
        .group_by(ScoutWatchlistCard.watchlist_id)
    )
    card_count = {str(wid): n for wid, n in res.all()}
    return [
        {
            "id": str(w.id), "name": w.name,
            "card_count": card_count.get(str(w.id), 0),
            "last_used_at": (last_card_at.get(str(w.id)) or w.created_at).isoformat(),
        }
        for w in watchlists
    ]


async def cards_for_player(session: AsyncSession, scout_org_id: str, scouted_player_id: str) -> list[dict]:
    """Every card this org has for one player, across every watchlist — the
    profile's "On watchlists" panel and stage control both read this. Each
    row carries enough to render a stage pill (watchlist + column names) and
    to know which card_id the inline recruiting-fields editor should PATCH."""
    player = await session.get(ScoutedPlayer, scouted_player_id)
    res = await session.execute(
        select(ScoutWatchlistCard, ScoutWatchlist.name, ScoutWatchlistColumn.name)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .join(ScoutWatchlistColumn, ScoutWatchlistColumn.id == ScoutWatchlistCard.column_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id, ScoutWatchlistCard.scouted_player_id == scouted_player_id)
        .order_by(ScoutWatchlistCard.created_at)
    )
    out = []
    for card, wl_name, col_name in res.all():
        out.append({
            **_card_out(card, player),
            "watchlist_id": str(card.watchlist_id),
            "watchlist_name": wl_name,
            "column_name": col_name,
        })
    return out


async def get_board(session: AsyncSession, watchlist_id: str, scout_org_id: str) -> dict:
    wl = await _get_owned_watchlist(session, watchlist_id, scout_org_id)

    res = await session.execute(
        select(ScoutWatchlistColumn)
        .where(ScoutWatchlistColumn.watchlist_id == wl.id)
        .order_by(ScoutWatchlistColumn.position)
    )
    columns = res.scalars().all()

    res = await session.execute(
        select(ScoutWatchlistCard, ScoutedPlayer)
        .join(ScoutedPlayer, ScoutedPlayer.id == ScoutWatchlistCard.scouted_player_id)
        .where(ScoutWatchlistCard.watchlist_id == wl.id)
        .order_by(ScoutWatchlistCard.position)
    )
    cards = [_card_out(card, player) for card, player in res.all()]

    return {
        "id": str(wl.id),
        "name": wl.name,
        "columns": [{"id": str(c.id), "name": c.name, "position": c.position} for c in columns],
        "cards": cards,
    }


def _card_out(card: ScoutWatchlistCard, player: ScoutedPlayer) -> dict:
    return {
        "id": str(card.id),
        "column_id": str(card.column_id),
        "position": card.position,
        "player": {
            "id": str(player.id),
            "name": player.name,
            "club_name": player.club_name,
            "source": player.source,
        },
        "tags": card.tags or [],
        "role": card.role,
        "batting_hand": card.batting_hand,
        "bowling_action": card.bowling_action,
        "bowling_type": card.bowling_type,
        "region": card.region,
        "level": card.level,
        "is_opening_batsman": card.is_opening_batsman,
        "is_wicket_keeper": card.is_wicket_keeper,
        "fielding_position": card.fielding_position,
        "batting_intel": card.batting_intel,
        "bowling_intel": card.bowling_intel,
        "transfer_preference": card.transfer_preference,
        "visa_status": card.visa_status,
        "agent_contact": card.agent_contact,
        "availability_window": card.availability_window,
        "fee_expectations": card.fee_expectations,
        "notes": card.notes,
        "share_token": card.share_token,
    }


# ─── columns ────────────────────────────────────────────────────────────────

async def create_column(session: AsyncSession, watchlist_id: str, scout_org_id: str, name: str) -> dict:
    wl = await _get_owned_watchlist(session, watchlist_id, scout_org_id)
    res = await session.execute(
        select(ScoutWatchlistColumn.position)
        .where(ScoutWatchlistColumn.watchlist_id == wl.id)
        .order_by(ScoutWatchlistColumn.position.desc())
        .limit(1)
    )
    last = res.scalar_one_or_none()
    col = ScoutWatchlistColumn(watchlist_id=wl.id, name=name, position=(last + 1) if last is not None else 0)
    session.add(col)
    await session.commit()
    return {"id": str(col.id), "name": col.name, "position": col.position}


async def rename_column(session: AsyncSession, column_id: str, scout_org_id: str, name: str) -> dict:
    col = await _get_owned_column(session, column_id, scout_org_id)
    col.name = name
    await session.commit()
    return {"id": str(col.id), "name": col.name, "position": col.position}


async def reorder_columns(session: AsyncSession, watchlist_id: str, scout_org_id: str, column_ids: list[str]) -> None:
    wl = await _get_owned_watchlist(session, watchlist_id, scout_org_id)
    res = await session.execute(select(ScoutWatchlistColumn).where(ScoutWatchlistColumn.watchlist_id == wl.id))
    by_id = {str(c.id): c for c in res.scalars().all()}
    # Only ids that genuinely belong to this watchlist are honoured — a
    # mismatched list from the browser can't touch anyone else's board.
    ordered = [cid for cid in column_ids if cid in by_id]
    for i, cid in enumerate(ordered):
        by_id[cid].position = i
    await session.commit()


async def delete_column(session: AsyncSession, column_id: str, scout_org_id: str) -> None:
    col = await _get_owned_column(session, column_id, scout_org_id)
    res = await session.execute(
        select(ScoutWatchlistColumn)
        .where(ScoutWatchlistColumn.watchlist_id == col.watchlist_id, ScoutWatchlistColumn.id != col.id)
        .order_by(ScoutWatchlistColumn.position)
    )
    remaining = res.scalars().all()
    if not remaining:
        raise ValueError("A watchlist needs at least one column.")
    target = remaining[0]
    # A column is just a label — the cards under it are the real thing, so
    # deleting it moves them to the first remaining column rather than
    # blocking the delete or losing them.
    res = await session.execute(select(ScoutWatchlistCard).where(ScoutWatchlistCard.column_id == col.id))
    for card in res.scalars().all():
        card.column_id = target.id
    await session.delete(col)
    await session.commit()


# ─── cards ──────────────────────────────────────────────────────────────────

async def move_card(session: AsyncSession, card_id: str, scout_org_id: str, column_id: str, position: int) -> dict:
    card = await _get_owned_card(session, card_id, scout_org_id)
    col = await _get_owned_column(session, column_id, scout_org_id)
    if str(col.watchlist_id) != str(card.watchlist_id):
        raise ValueError("Can't move a card to a column on a different watchlist.")
    card.column_id = col.id
    card.position = position
    await session.commit()
    return {"id": str(card.id), "column_id": str(card.column_id), "position": card.position}


def _validate_card_fields(fields: dict) -> None:
    if "role" in fields and (fields["role"] or "") not in ROLE_OPTS:
        raise ValueError("Unknown role.")
    if "batting_hand" in fields and (fields["batting_hand"] or "") not in BAT_HAND_CODES:
        raise ValueError("Unknown batting hand.")
    if "bowling_action" in fields and (fields["bowling_action"] or "") not in BOWLING_ACTION_CODES:
        raise ValueError("Unknown bowling action.")
    if "bowling_type" in fields and (fields["bowling_type"] or "") not in BOWLING_TYPE_CODES:
        raise ValueError("Unknown bowling type.")
    if "region" in fields and (fields["region"] or "") not in REGION_OPTS:
        raise ValueError("Unknown region.")
    if "level" in fields and (fields["level"] or "") not in LEVEL_OPTS:
        raise ValueError("Unknown level.")
    if "tags" in fields and not isinstance(fields["tags"], list):
        raise ValueError("tags must be a list.")


def _clean_intel_fields(fields: dict) -> None:
    """batting_intel/bowling_intel are normalised, not rejected — an unknown
    code or an all-empty blob is silently dropped down to a clean shape (or
    None) by services/scouting_intel.py, the same permissive rule BetterIQ's
    own scouting cards already follow. Mutates `fields` in place."""
    if "batting_intel" in fields:
        fields["batting_intel"] = clean_batting_intel(fields["batting_intel"])
    if "bowling_intel" in fields:
        fields["bowling_intel"] = clean_bowling_intel(fields["bowling_intel"])


async def update_card(session: AsyncSession, card_id: str, scout_org_id: str, **fields) -> dict:
    card = await _get_owned_card(session, card_id, scout_org_id)
    fields = {k: v for k, v in fields.items() if k in _CARD_FIELDS}
    _validate_card_fields(fields)
    _clean_intel_fields(fields)
    for k, v in fields.items():
        setattr(card, k, v)
    await session.commit()
    player = await session.get(ScoutedPlayer, card.scouted_player_id)
    return _card_out(card, player)


async def remove_card(session: AsyncSession, card_id: str, scout_org_id: str) -> None:
    card = await _get_owned_card(session, card_id, scout_org_id)
    await session.delete(card)
    await session.commit()


async def remove_player_everywhere(session: AsyncSession, scout_org_id: str, scouted_player_id: str) -> int:
    """The "My Players" remove action — deletes every one of THIS org's
    ScoutWatchlistCard rows for one scouted_player_id, across every one of
    this org's watchlists (a player can be on more than one board — see
    ensure_card_on_watchlist). Never touches ScoutedPlayer or
    ScoutedPlayerClub — both are platform-wide, shared by every Scout Org
    (see models/scout.py's docstrings), so deleting either would either wipe
    another org's tracking of the same real person or, via
    ScoutWatchlistCard.scouted_player_id's ondelete=CASCADE, silently delete
    every OTHER org's cards for them too. This is a per-org unlink, nothing
    more. Raises ValueError if this org has no card for this player."""
    card_ids = (await session.execute(
        select(ScoutWatchlistCard.id)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(
            ScoutWatchlist.scout_org_id == scout_org_id,
            ScoutWatchlistCard.scouted_player_id == scouted_player_id,
        )
    )).scalars().all()
    if not card_ids:
        raise ValueError("You aren't tracking this player.")
    for card_id in card_ids:
        card = await session.get(ScoutWatchlistCard, card_id)
        if card:
            await session.delete(card)
    await session.commit()
    return len(card_ids)


# ─── read-only public share link ───────────────────────────────────────────

# Fields excluded from a shared card view — the recruiting-CRM detail is
# commercially sensitive negotiation material that must never ride on a link
# that could be forwarded anywhere. Kept as an explicit list (not "everything
# _card_out returns minus a blocklist") so a future field added to the card
# doesn't leak onto a public page just because nobody remembered to exclude it.
_SHARED_CARD_FIELDS = {
    "tags", "role", "batting_hand", "bowling_action", "bowling_type", "region", "level", "notes",
    "is_opening_batsman", "is_wicket_keeper", "fielding_position",
    "batting_intel", "bowling_intel",
}


async def create_share_link(session: AsyncSession, card_id: str, scout_org_id: str) -> dict:
    """Mints (or, on an already-shared card, ROTATES — the old link dies the
    moment a new one is minted) a share token. One action covers both
    'share' and 'regenerate'."""
    card = await _get_owned_card(session, card_id, scout_org_id)
    card.share_token = secrets.token_urlsafe(24)
    card.share_token_created_at = datetime.now(timezone.utc)
    await session.commit()
    return {"share_token": card.share_token}


async def revoke_share_link(session: AsyncSession, card_id: str, scout_org_id: str) -> None:
    card = await _get_owned_card(session, card_id, scout_org_id)
    card.share_token = None
    card.share_token_created_at = None
    await session.commit()


async def list_share_links(session: AsyncSession, scout_org_id: str) -> list[dict]:
    """Settings → Sharing defaults' "N links live now / Manage links"."""
    res = await session.execute(
        select(ScoutWatchlistCard, ScoutedPlayer)
        .join(ScoutedPlayer, ScoutedPlayer.id == ScoutWatchlistCard.scouted_player_id)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id, ScoutWatchlistCard.share_token.isnot(None))
        .order_by(ScoutWatchlistCard.share_token_created_at.desc().nullslast())
    )
    return [
        {
            "card_id": str(card.id),
            "player_name": player.name,
            "created_at": card.share_token_created_at.isoformat() if card.share_token_created_at else None,
        }
        for card, player in res.all()
    ]


async def revoke_all_share_links(session: AsyncSession, scout_org_id: str) -> int:
    res = await session.execute(
        select(ScoutWatchlistCard)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlist.scout_org_id == scout_org_id, ScoutWatchlistCard.share_token.isnot(None))
    )
    cards = res.scalars().all()
    for card in cards:
        card.share_token = None
        card.share_token_created_at = None
    await session.commit()
    return len(cards)


async def get_shared_card(session: AsyncSession, token: str) -> dict | None:
    """The one unscoped lookup in this module, by design — the token itself
    IS the credential, there's no Scout Org to check ownership against from
    the public side. Returns a deliberately narrow shape: never the five
    recruiting fields, whatever _card_out otherwise carries — and never
    tags/notes either, when the owning org's sharing defaults say not to.
    An expired link (org.share_expiry_days) reads exactly like an unknown
    token — no separate "expired" state leaked to a stranger holding a dead
    link."""
    res = await session.execute(
        select(ScoutWatchlistCard, ScoutedPlayer, ScoutWatchlist.scout_org_id)
        .join(ScoutedPlayer, ScoutedPlayer.id == ScoutWatchlistCard.scouted_player_id)
        .join(ScoutWatchlist, ScoutWatchlist.id == ScoutWatchlistCard.watchlist_id)
        .where(ScoutWatchlistCard.share_token == token)
    )
    row = res.first()
    if not row:
        return None
    card, player, scout_org_id = row
    org = await session.get(ScoutOrg, scout_org_id)
    if org and scout_settings.share_link_expired(org, card.share_token_created_at):
        return None
    full = _card_out(card, player)
    shared = {k: full[k] for k in _SHARED_CARD_FIELDS}
    if org and not org.share_include_notes:
        # Scouting intel is the scout's own analytical commentary, same
        # sensitivity class as notes — gated on the same toggle rather than
        # inventing a third sharing switch.
        shared.pop("notes", None)
        shared.pop("batting_intel", None)
        shared.pop("bowling_intel", None)
    if org and not org.share_include_tags:
        shared.pop("tags", None)
    return {
        "player": full["player"],
        "stats": player.stats_payload,
        **shared,
    }


async def ensure_card_on_watchlist(
    session: AsyncSession, scout_org_id: str, scouted_player_id: str, watchlist_id: str | None = None,
) -> ScoutWatchlistCard:
    """Called by scout_discovery.add_player/add_manual_player — puts a newly
    added player onto a watchlist (the one the scout picked, or the org's
    default — creating the default if needed — when they didn't pick one),
    in its first column. Idempotent: re-adding an already-tracked player to
    the SAME board returns the existing card rather than duplicating it (the
    unique constraint on (watchlist_id, scouted_player_id) makes that the
    only safe behaviour anyway) — adding them to a DIFFERENT board is a
    second, separate card, which is the whole point of "On N watchlists"."""
    wl = await _get_owned_watchlist(session, watchlist_id, scout_org_id) if watchlist_id \
        else await ensure_default_watchlist(session, scout_org_id)
    res = await session.execute(
        select(ScoutWatchlistCard).where(
            ScoutWatchlistCard.watchlist_id == wl.id,
            ScoutWatchlistCard.scouted_player_id == scouted_player_id,
        )
    )
    card = res.scalar_one_or_none()
    if card:
        return card

    # This is the one place a NEW tracked-player fact is created (both
    # add_player and add_manual_player funnel through here), so it's the
    # single enforcement point for the tier's player cap. An already-tracked
    # player (the early return above) never counts against it again.
    org = await session.get(ScoutOrg, scout_org_id)
    cap = scout_billing.cap_for(org.tier if org else None)
    if cap is not None:
        count = await scout_billing.tracked_player_count(session, scout_org_id)
        if count >= cap:
            raise ValueError(
                f"You've reached your {scout_billing.label_for(org.tier if org else None)} "
                f"plan's {cap}-player limit. Contact us to upgrade."
            )

    res = await session.execute(
        select(ScoutWatchlistColumn)
        .where(ScoutWatchlistColumn.watchlist_id == wl.id)
        .order_by(ScoutWatchlistColumn.position)
        .limit(1)
    )
    first_col = res.scalar_one()
    card = ScoutWatchlistCard(watchlist_id=wl.id, column_id=first_col.id, scouted_player_id=scouted_player_id)
    session.add(card)
    await session.flush()
    return card
