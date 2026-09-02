from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, text
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
import uuid
import re
import json
import logging
from difflib import SequenceMatcher

log = logging.getLogger(__name__)

from app.services.grassroots_scores_client import get_match_scorecard

from app.models.db import (
    Player, PlayerSeasonStats, BattingInnings, BowlingSpell,
    FieldingStat, FallOfWicket, Partnership, Milestone, User, Organisation, get_db,
    ImportedStat,
)
from app.routers.auth import get_current_user, get_current_club
from app.auth.capabilities import require_cap, MANAGE_MERGES
from app.services.grade_labels import (
    GRADE_CATEGORIES, MATCH_FORMATS, format_from_match_type, normalise_category,
    normalise_format, suggest_categories, suggest_category, suggest_formats,
)
# The historical-import matcher already knows how to split a name into its parts
# and decide whether two sets of middle initials could belong to one person.
# Reused rather than copied so the two never disagree about what a name is.
from app.services.import_ingest import _name_parts, _middles_compatible
from app.services.player_aliases import seed_alias_on_rename
from app.services.import_reconcile import reconcile_imported_totals
from app.auth.modules import require_module

router = APIRouter(prefix="/admin", tags=["admin"])


def _normalise(name: str) -> str:
    """Normalise 'Last, First' → 'first last' and strip extra spaces for comparison.

    Splits on a bare comma rather than requiring the literal ", " substring, and
    strips each side before rejoining — a stray space before the comma ("Smith ,
    John") used to leave a trailing space baked into the key, so it silently
    failed to match a correctly-typed "Smith, John" and was missed as a
    duplicate here.
    """
    name = name.strip()
    if "," in name:
        parts = name.split(",", 1)
        name = f"{parts[1].strip()} {parts[0].strip()}".strip()
    return re.sub(r"\s+", " ", name).strip().lower()


_REDACTED_NAME_RE = re.compile(r"^\*+$")


def _is_redacted_name(name: str) -> bool:
    """CA redacts junior players' names in the feed as a run of asterisks
    (e.g. "********") — every redacted junior collapses to the same
    placeholder text, so two of them look like an exact-name duplicate even
    though they're unrelated kids. Never eligible for an automatic merge."""
    return bool(_REDACTED_NAME_RE.match((name or "").strip()))


async def _enrich_player(db: AsyncSession, p: Player) -> dict:
    stats_res = await db.execute(select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == p.id))
    season_stats = stats_res.scalars().all()
    innings_res = await db.execute(select(BattingInnings).where(BattingInnings.player_id == p.id))
    game_innings = len(innings_res.scalars().all())
    return {
        "id": str(p.id),
        "name": p.display_name,
        "playhq_id": p.playhq_id,
        "claimed": p.claimed,
        "seasons_count": len(season_stats),
        "total_runs": sum((s.runs or 0) for s in season_stats),
        "total_wickets": sum((s.wickets or 0) for s in season_stats),
        "total_matches": sum((s.matches or 0) for s in season_stats),
        "game_level_innings": game_innings,
    }


@router.get("/player-info")
async def get_player_info(player_id: str, org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Return enriched stats for a single player (used by manual merge UI)."""
    p = await db.get(Player, uuid.UUID(player_id))
    if not p or str(p.organisation_id) != org_id:
        raise HTTPException(status_code=404, detail="Player not found")
    return await _enrich_player(db, p)


FUZZY_MERGE_THRESHOLD = 0.90
MAX_FUZZY_PAIRS = 500
MAX_VARIANT_PAIRS = 300
MIN_SHORT_FORM_LEN = 3


def _name_keys(p: Player) -> list[str]:
    """Every normalised name this player is known by — the raw synced ``name``
    plus, when it differs, the admin's ``display_name_override``.

    Detection used to group on ``name`` alone while the screen renders
    ``display_name``, so a renamed player was only ever compared under the name
    the sync wrote. Their duplicate then read as unlisted even though the two
    cards on screen said the same thing.
    """
    keys: list[str] = []
    for raw in (p.name, p.display_name_override):
        k = _normalise(raw or "")
        if k and k not in keys:
            keys.append(k)
    return keys


def _fuzzy_name_pairs(players: list, ignored: set) -> list:
    """Near-miss spelling pairs the exact-name grouping above can't see — e.g. a
    club's hand-kept 50-year stats sheet has "Taylor, Malcolm" in one season and
    a typo'd "Taylor, Malcom" in another, minting two player records that never
    share an exact normalised-name key. Blocked by the first character of the
    normalised name (same trick ``import_ingest.match_players`` uses) so this
    stays fast on a large roster. Returned separately from the exact-match pairs
    above and never bulk-mergeable — a spelling guess always needs a human to
    confirm it's the same person, not two genuinely different club members
    (e.g. "Steve"/"Steven" or "Brendan"/"Brendon" are often two different people).
    """
    blocks: dict[str, list] = {}
    for p in players:
        if _is_redacted_name(p.name):
            continue
        for key in _name_keys(p):
            blocks.setdefault(key[:1], []).append((p, key))

    # A player carrying a display-name override enters more than one block, so
    # the same pair can be scored twice under different spellings — keep the
    # strongest reading of the two rather than whichever was reached first.
    best: dict[tuple, tuple] = {}
    for block in blocks.values():
        for i in range(len(block)):
            p1, k1 = block[i]
            for j in range(i + 1, len(block)):
                p2, k2 = block[j]
                if p1.id == p2.id or k1 == k2 or abs(len(k1) - len(k2)) > 3:
                    continue
                ratio = SequenceMatcher(None, k1, k2).ratio()
                if ratio < FUZZY_MERGE_THRESHOLD:
                    continue
                pair_key = tuple(sorted([str(p1.id), str(p2.id)]))
                if pair_key in ignored:
                    continue
                if pair_key not in best or ratio > best[pair_key][0]:
                    best[pair_key] = (ratio, p1, p2)
    scored = sorted(best.values(), key=lambda t: t[0], reverse=True)
    return scored[:MAX_FUZZY_PAIRS]


def _first_name_link(f1: str, f2: str):
    """``(confidence, reason)`` when two given names could be one person's, else
    ``None``. Both names are assumed to already share a first letter.

    Deliberately narrow: a bare initial, or a short form that is a genuine
    prefix of the longer name. A nickname that is not a prefix ("Bob"/"Robert",
    "Bill"/"William") is NOT claimed here — it would need a curated list, and
    every entry on such a list is a judgement call that produces a confident
    wrong pair when it misses.
    """
    if f1 == f2:
        return (0.9, "same first name, middle initial differs")
    if len(f1) == 1 or len(f2) == 1:
        return (0.7, "one record has only an initial")
    short, long_ = (f1, f2) if len(f1) < len(f2) else (f2, f1)
    if len(short) >= MIN_SHORT_FORM_LEN and long_.startswith(short):
        return (0.8, "short form of the same first name")
    return None


def _name_variant_pairs(players: list, ignored: set, already: set) -> list:
    """Same surname, compatible first name and compatible middle initials —
    the duplicates full-string similarity structurally cannot see.

    "Brad K Mant" and "Mant, Bradley" are one person, but two differences stack
    (a short form AND a middle initial), and edit-distance degrades
    multiplicatively: each difference alone scores 0.86 and 0.90, together only
    0.78, well under ``FUZZY_MERGE_THRESHOLD``. Dropping that threshold far
    enough to catch it floods a 1,500-player roster with genuinely different
    people, so this compares the name's PARTS instead of the whole string.

    Blocked on (surname, first initial), which costs nothing: every rule in
    ``_first_name_link`` already requires the first letter to agree.

    Never bulk-mergeable. A surname and one initial is not a unique identity —
    two brothers, or a father and son, are exactly this shape.
    """
    groups: dict[tuple, list] = {}
    for p in players:
        if _is_redacted_name(p.name):
            continue
        for key in _name_keys(p):
            parts = _name_parts(key)
            if not parts:
                continue
            first, last, middles = parts
            if len(last) < 2:
                continue
            groups.setdefault((last, first[0]), []).append((p, key, first, middles))

    best: dict[tuple, tuple] = {}
    for group in groups.values():
        for i in range(len(group)):
            p1, k1, f1, m1 = group[i]
            for j in range(i + 1, len(group)):
                p2, k2, f2, m2 = group[j]
                if p1.id == p2.id or k1 == k2:
                    continue
                pair_key = tuple(sorted([str(p1.id), str(p2.id)]))
                if pair_key in ignored or pair_key in already:
                    continue
                link = _first_name_link(f1, f2)
                if not link or not _middles_compatible(m1, m2):
                    continue
                conf, reason = link
                if pair_key not in best or conf > best[pair_key][0]:
                    best[pair_key] = (conf, reason, p1, p2)
    scored = sorted(best.values(), key=lambda t: t[0], reverse=True)
    return scored[:MAX_VARIANT_PAIRS]


@router.get("/merge-candidates")
async def get_merge_candidates(org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Return pairs of players within an org that look like duplicates.

    Three tiers, tagged so the screen can treat them differently:
    ``exact`` (identical normalised names, safe for Bulk Approve), ``fuzzy``
    (a near-miss spelling, e.g. Malcolm/Malcom) and ``name_variant`` (same
    surname, a short form or initial standing in for the first name). Only
    ``exact`` is ever bulk-mergeable; the other two always need a human to
    confirm it is one person.
    """
    result = await db.execute(
        select(Player).where(Player.organisation_id == uuid.UUID(org_id))
    )
    players = result.scalars().all()

    # Load permanently ignored pairs for this org
    ignored_res = await db.execute(
        text("SELECT player_a_id::text, player_b_id::text FROM merge_pair_ignores WHERE org_id = :org_id"),
        {"org_id": org_id},
    )
    ignored = {(r.player_a_id, r.player_b_id) for r in ignored_res.mappings().all()}

    # Enriching a player costs two queries, and the tiers below overlap on the
    # same people — cache per player so a player in several pairs is read once.
    enriched_cache: dict = {}

    async def enrich(p: Player) -> dict:
        if p.id not in enriched_cache:
            enriched_cache[p.id] = await _enrich_player(db, p)
        return enriched_cache[p.id]

    # Group by normalised name. A player with a display-name override is filed
    # under both spellings, so `emitted` stops one pair being listed twice.
    groups: dict[str, list[Player]] = {}
    for p in players:
        for key in _name_keys(p):
            groups.setdefault(key, []).append(p)

    candidate_pairs = []
    emitted: set = set()
    for key, group in groups.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                p1, p2 = group[i], group[j]
                if p1.id == p2.id:
                    continue
                pair_key = tuple(sorted([str(p1.id), str(p2.id)]))
                if pair_key in ignored or pair_key in emitted:
                    continue
                emitted.add(pair_key)
                a, b = await enrich(p1), await enrich(p2)
                candidate_pairs.append({
                    "kind": "exact",
                    "normalised_name": key,
                    "redacted": _is_redacted_name(p1.name) or _is_redacted_name(p2.name),
                    "player_a": a,
                    "player_b": b,
                })

    for ratio, p1, p2 in _fuzzy_name_pairs(players, ignored):
        pair_key = tuple(sorted([str(p1.id), str(p2.id)]))
        if pair_key in emitted:
            continue
        emitted.add(pair_key)
        a, b = await enrich(p1), await enrich(p2)
        candidate_pairs.append({
            "kind": "fuzzy",
            "confidence": round(ratio, 2),
            "normalised_name": None,
            "redacted": False,
            "player_a": a,
            "player_b": b,
        })

    for conf, reason, p1, p2 in _name_variant_pairs(players, ignored, emitted):
        pair_key = tuple(sorted([str(p1.id), str(p2.id)]))
        emitted.add(pair_key)
        a, b = await enrich(p1), await enrich(p2)
        candidate_pairs.append({
            "kind": "name_variant",
            "confidence": conf,
            "reason": reason,
            "normalised_name": None,
            "redacted": False,
            "player_a": a,
            "player_b": b,
        })

    return candidate_pairs


class IgnorePairRequest(BaseModel):
    player_a_id: str
    player_b_id: str
    org_id: str


@router.post("/ignore-pair")
async def ignore_pair(req: IgnorePairRequest, db: AsyncSession = Depends(get_db), _: User = Depends(require_cap(MANAGE_MERGES))):
    """Permanently suppress a suggested duplicate pair."""
    a, b = sorted([req.player_a_id, req.player_b_id])
    await db.execute(
        text("""
            INSERT INTO merge_pair_ignores (org_id, player_a_id, player_b_id)
            VALUES (:org_id, :a, :b)
            ON CONFLICT (org_id, player_a_id, player_b_id) DO NOTHING
        """),
        {"org_id": req.org_id, "a": a, "b": b},
    )
    await db.commit()
    return {"status": "ignored"}


@router.get("/merge-history")
async def get_merge_history(org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """Return recent merges for an org that can be undone."""
    rows = await db.execute(
        text("""
            SELECT id, merged_at, keep_player_id, keep_player_name,
                   removed_player_id, removed_player_name, undone_at
            FROM merge_logs
            WHERE org_id = :org_id
            ORDER BY merged_at DESC
            LIMIT 2000
        """),
        {"org_id": org_id},
    )
    return [
        {
            "id": r.id,
            "merged_at": r.merged_at.isoformat() if r.merged_at else None,
            "keep_player_id": str(r.keep_player_id),
            "keep_player_name": r.keep_player_name,
            "removed_player_id": str(r.removed_player_id),
            "removed_player_name": r.removed_player_name,
            "undone": r.undone_at is not None,
        }
        for r in rows.mappings().all()
    ]


class MergeRequest(BaseModel):
    keep_player_id: str
    remove_player_id: str
    org_id: str


async def _merge_players_core(
    db: AsyncSession, keep_id: uuid.UUID, remove_id: uuid.UUID, org_id: uuid.UUID, current_user: User,
) -> dict:
    """Merge remove_player into keep_player, reassigning all records. Shared by
    the single-pair endpoint and the bulk-approve endpoint below."""
    keep = await db.get(Player, keep_id)
    remove = await db.get(Player, remove_id)

    if not keep or not remove:
        raise HTTPException(status_code=404, detail="Player not found")
    if keep.organisation_id != org_id or remove.organisation_id != org_id:
        raise HTTPException(status_code=400, detail="Players must belong to the specified organisation")
    if keep_id == remove_id:
        raise HTTPException(status_code=400, detail="Cannot merge a player with itself")

    # --- Collect IDs before making changes (for undo log) ---
    def _ids(rows) -> list:
        return [r.id for r in rows]

    try:
        batting_rows = (await db.execute(select(BattingInnings).where(BattingInnings.player_id == remove_id))).scalars().all()
        bowling_rows = (await db.execute(select(BowlingSpell).where(BowlingSpell.player_id == remove_id))).scalars().all()
        fielding_rows = (await db.execute(select(FieldingStat).where(FieldingStat.player_id == remove_id))).scalars().all()
        fow_rows = (await db.execute(select(FallOfWicket).where(FallOfWicket.player_id == remove_id))).scalars().all()
        batter1_rows = (await db.execute(select(Partnership).where(Partnership.batter1_id == remove_id))).scalars().all()
        batter2_rows = (await db.execute(select(Partnership).where(Partnership.batter2_id == remove_id))).scalars().all()
        milestone_rows = (await db.execute(select(Milestone).where(Milestone.player_id == remove_id))).scalars().all()

        # imported_stats (BetterImport's uploaded truth) FKs to players with
        # ON DELETE CASCADE. It was never reassigned here, so merging a player
        # created by a historical stats import (see routers/imports.py::commit
        # — a name that didn't match the existing roster mints a brand-new
        # Player) silently destroyed their entire imported career the moment
        # the removed player row was deleted, with nothing logged for undo.
        # Same class of bug this function already fixed once for
        # bowler_wickets/grade_stats/appearances — see the merge_logs comment
        # in main.py's lifespan.
        remove_imported_res = await db.execute(select(ImportedStat).where(ImportedStat.player_id == remove_id))
        remove_imported = remove_imported_res.scalars().all()
        keep_imported_res = await db.execute(select(ImportedStat).where(ImportedStat.player_id == keep_id))
        keep_imported_keys = {
            (s.scope, s.season_id, s.grade_label, s.is_prior_bucket) for s in keep_imported_res.scalars().all()
        }
        moved_imported_ids = []
        for s in remove_imported:
            key = (s.scope, s.season_id, s.grade_label, s.is_prior_bucket)
            if key in keep_imported_keys:
                # Same (scope, season, grade) cell already imported for keep —
                # a genuine duplicate upload. Drop the removed side rather than
                # risk double-counting; mirrors the PlayerSeasonStats collision
                # rule below.
                await db.execute(delete(ImportedStat).where(ImportedStat.id == s.id))
            else:
                await db.execute(update(ImportedStat).where(ImportedStat.id == s.id).values(player_id=keep_id))
                moved_imported_ids.append(s.id)

        # bowler_wickets is keyed on bowler_id (wicket-taker) and fielder_id
        # (catcher / run-out fielder). Both must follow the player or they're lost:
        # the FK is ON DELETE CASCADE / SET NULL, so deleting the removed player
        # used to silently drop these rows (the removed player's whole wicket-
        # dismissal record). Capture the surrogate ids for the undo log.
        bowler_wkt_ids = (await db.execute(
            text("SELECT id FROM bowler_wickets WHERE bowler_id = :rid"), {"rid": str(remove_id)}
        )).scalars().all()
        fielder_wkt_ids = (await db.execute(
            text("SELECT id FROM bowler_wickets WHERE fielder_id = :rid"), {"rid": str(remove_id)}
        )).scalars().all()

        remove_stats_res = await db.execute(select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == remove_id))
        remove_stats = remove_stats_res.scalars().all()
        keep_stats_res = await db.execute(select(PlayerSeasonStats).where(PlayerSeasonStats.player_id == keep_id))
        keep_season_ids = {s.season_id for s in keep_stats_res.scalars().all()}

        moved_pss_ids = [s.id for s in remove_stats if s.season_id not in keep_season_ids]

        # --- batting_innings: de-duplicate before reassigning ----------------------
        # batting_innings has UNIQUE(game_id, innings_number, player_id) (migration
        # 030). When the two records are the same physical player (the cross-club
        # shared-GUID case — e.g. a uuid5 per-club id and the raw CA GUID), both can
        # hold a row for the same (game, innings). Blindly moving them onto keep
        # would violate that constraint → IntegrityError → a bare 500. So delete the
        # removed player's duplicate rows first, then move what's left. Mirrors the
        # player_season_stats handling below.
        colliding_bat_ids = (await db.execute(
            text(
                "SELECT r.id FROM batting_innings r "
                "JOIN batting_innings k "
                "  ON k.game_id = r.game_id AND k.innings_number = r.innings_number "
                "WHERE r.player_id = :rid AND k.player_id = :kid"
            ),
            {"rid": str(remove_id), "kid": str(keep_id)},
        )).scalars().all()
        if colliding_bat_ids:
            await db.execute(
                text("DELETE FROM batting_innings WHERE id = ANY(:ids)"),
                {"ids": list(colliding_bat_ids)},
            )
        _coll_bat = set(colliding_bat_ids)
        moved_bat_ids = [i for i in _ids(batting_rows) if i not in _coll_bat]

        # --- player_season_grade_stats: de-dup then reassign -----------------------
        # UNIQUE(player_id, season_id, grade_id); same collision shape. (Also
        # previously cascade-deleted with the removed player.)
        all_grade_stat_ids = (await db.execute(
            text("SELECT id FROM player_season_grade_stats WHERE player_id = :rid"), {"rid": str(remove_id)}
        )).scalars().all()
        colliding_grade_ids = (await db.execute(
            text(
                "SELECT r.id FROM player_season_grade_stats r "
                "JOIN player_season_grade_stats k "
                "  ON k.season_id = r.season_id AND k.grade_id = r.grade_id "
                "WHERE r.player_id = :rid AND k.player_id = :kid"
            ),
            {"rid": str(remove_id), "kid": str(keep_id)},
        )).scalars().all()
        if colliding_grade_ids:
            await db.execute(
                text("DELETE FROM player_season_grade_stats WHERE id = ANY(:ids)"),
                {"ids": list(colliding_grade_ids)},
            )
        _coll_grade = set(colliding_grade_ids)
        moved_grade_stat_ids = [i for i in all_grade_stat_ids if i not in _coll_grade]

        # --- game_appearances: de-dup (composite PK game_id, player_id) ------------
        # Record only the game_ids actually moved (where keep has no appearance yet)
        # so the undo can put them back, then drop the removed player's duplicates.
        moved_appearance_game_ids = (await db.execute(
            text(
                "SELECT ga.game_id FROM game_appearances ga "
                "WHERE ga.player_id = :rid AND NOT EXISTS ("
                "  SELECT 1 FROM game_appearances k WHERE k.player_id = :kid AND k.game_id = ga.game_id)"
            ),
            {"rid": str(remove_id), "kid": str(keep_id)},
        )).scalars().all()
        await db.execute(
            text(
                "DELETE FROM game_appearances ga USING game_appearances k "
                "WHERE ga.player_id = :rid AND k.player_id = :kid AND k.game_id = ga.game_id"
            ),
            {"rid": str(remove_id), "kid": str(keep_id)},
        )

        # --- Reassign game-level records ---
        await db.execute(update(BattingInnings).where(BattingInnings.player_id == remove_id).values(player_id=keep_id))
        await db.execute(update(BowlingSpell).where(BowlingSpell.player_id == remove_id).values(player_id=keep_id))
        await db.execute(update(FieldingStat).where(FieldingStat.player_id == remove_id).values(player_id=keep_id))
        await db.execute(update(FallOfWicket).where(FallOfWicket.player_id == remove_id).values(player_id=keep_id))
        await db.execute(update(Partnership).where(Partnership.batter1_id == remove_id).values(batter1_id=keep_id))
        await db.execute(update(Partnership).where(Partnership.batter2_id == remove_id).values(batter2_id=keep_id))
        await db.execute(update(Milestone).where(Milestone.player_id == remove_id).values(player_id=keep_id))
        await db.execute(text("UPDATE bowler_wickets SET bowler_id = :kid WHERE bowler_id = :rid"), {"kid": str(keep_id), "rid": str(remove_id)})
        await db.execute(text("UPDATE bowler_wickets SET fielder_id = :kid WHERE fielder_id = :rid"), {"kid": str(keep_id), "rid": str(remove_id)})
        await db.execute(text("UPDATE player_season_grade_stats SET player_id = :kid WHERE player_id = :rid"), {"kid": str(keep_id), "rid": str(remove_id)})
        await db.execute(text("UPDATE game_appearances SET player_id = :kid WHERE player_id = :rid"), {"kid": str(keep_id), "rid": str(remove_id)})

        # --- Vote collection rows (migrations 193, 267) ---
        # Both FKs are ON DELETE CASCADE, so without this reassignment deleting
        # the removed player would silently destroy their ballots and every vote
        # cast FOR them. De-dup first (one ballot per voter per fixture PER
        # MEDAL; one pick per player per ballot — both records are the same
        # physical person, so keep's row wins), then move the rest. Not recorded
        # in the undo log — an undone merge leaves votes attributed to the kept
        # player, which is still the same human and never loses a vote.
        #
        # The medal must be in the de-dup key or this drops a real ballot: the
        # same person voting for the Club Champion AND the Colts Medal on one
        # fixture holds two legitimate ballots, and matching on fixture alone
        # would delete one of them.
        await db.execute(
            text(
                "DELETE FROM vote_ballots r USING vote_ballots k "
                "WHERE r.voter_player_id = :rid AND k.voter_player_id = :kid "
                "AND k.fixture_id = r.fixture_id AND k.medal_id = r.medal_id"
            ),
            {"rid": str(remove_id), "kid": str(keep_id)},
        )
        await db.execute(
            text("UPDATE vote_ballots SET voter_player_id = :kid WHERE voter_player_id = :rid"),
            {"kid": str(keep_id), "rid": str(remove_id)},
        )
        await db.execute(
            text(
                "DELETE FROM vote_ballot_picks r USING vote_ballot_picks k "
                "WHERE r.player_id = :rid AND k.player_id = :kid AND k.ballot_id = r.ballot_id"
            ),
            {"rid": str(remove_id), "kid": str(keep_id)},
        )
        await db.execute(
            text("UPDATE vote_ballot_picks SET player_id = :kid WHERE player_id = :rid"),
            {"kid": str(keep_id), "rid": str(remove_id)},
        )

        # --- Handle PlayerSeasonStats ---
        for stat in remove_stats:
            if stat.season_id not in keep_season_ids:
                await db.execute(
                    update(PlayerSeasonStats).where(PlayerSeasonStats.id == stat.id).values(player_id=keep_id)
                )
            else:
                await db.execute(delete(PlayerSeasonStats).where(PlayerSeasonStats.id == stat.id))

        # Save data needed for undo log before player is deleted
        keep_original_playhq_id = keep.playhq_id
        removed_playhq_id = remove.playhq_id
        removed_name = remove.name
        removed_display_name = remove.display_name_override or remove.name

        # A merge is a rename in disguise from a live feed's point of view: the
        # removed player's name no longer has ANY row to resolve to once
        # they're gone, so a Play.Cricket team list or a scorecard still using
        # it would go from "matched via the normal fallback" to "unresolved"
        # the moment this merge lands. Seed it as an alias onto the kept
        # player — same mechanism a plain rename uses (services/player_aliases.py).
        await seed_alias_on_rename(db, org_id, keep_id, removed_display_name)

        # --- Delete remove player FIRST (avoids unique constraint violation on playhq_id) ---
        await db.execute(delete(Player).where(Player.id == remove_id))

        # --- Now safe to copy playhq_id to keep (remove is deleted in this transaction) ---
        if not keep.playhq_id and removed_playhq_id:
            keep.playhq_id = removed_playhq_id

        # --- Write merge log ---
        await db.execute(
            text("""
                INSERT INTO merge_logs (
                    org_id, keep_player_id, keep_player_name,
                    removed_player_id, removed_player_name, removed_player_playhq_id,
                    keep_original_playhq_id,
                    moved_season_stat_ids, batting_innings_ids, bowling_spell_ids,
                    fielding_stat_ids, fall_of_wicket_ids,
                    batter1_partnership_ids, batter2_partnership_ids, milestone_ids,
                    bowler_wicket_ids, fielder_wicket_ids, grade_stat_ids, appearance_game_ids,
                    imported_stat_ids
                ) VALUES (
                    :org_id, :keep_id, :keep_name,
                    :remove_id, :remove_name, :remove_playhq_id,
                    :keep_orig_playhq_id,
                    :pss_ids, :bat_ids, :bowl_ids,
                    :field_ids, :fow_ids,
                    :b1_ids, :b2_ids, :mil_ids,
                    :bw_ids, :fw_ids, :grade_ids, :appear_ids,
                    :imported_ids
                )
            """),
            {
                "org_id": str(org_id),
                "keep_id": str(keep_id),
                "keep_name": keep.name,
                "remove_id": str(remove_id),
                "remove_name": removed_name,
                "remove_playhq_id": removed_playhq_id,
                "keep_orig_playhq_id": keep_original_playhq_id,
                "pss_ids": json.dumps(moved_pss_ids),
                "bat_ids": json.dumps(moved_bat_ids),
                "bowl_ids": json.dumps(_ids(bowling_rows)),
                "field_ids": json.dumps(_ids(fielding_rows)),
                "fow_ids": json.dumps(_ids(fow_rows)),
                "b1_ids": json.dumps(_ids(batter1_rows)),
                "b2_ids": json.dumps(_ids(batter2_rows)),
                "mil_ids": json.dumps(_ids(milestone_rows)),
                "bw_ids": json.dumps(list(bowler_wkt_ids)),
                "fw_ids": json.dumps(list(fielder_wkt_ids)),
                "grade_ids": json.dumps(moved_grade_stat_ids),
                "appear_ids": json.dumps([str(g) for g in moved_appearance_game_ids]),
                "imported_ids": json.dumps(moved_imported_ids),
            },
        )

        from app.services.audit_log import log_activity
        await log_activity(
            db, org_id=org_id, user_id=current_user.id,
            action="merge_players", target_type="player", target_id=str(keep_id),
            details={
                "kept_player": {"id": str(keep_id), "name": keep.name},
                "removed_player": {"id": str(remove_id), "name": removed_name},
                "rows_moved": {
                    "season_stats": len(moved_pss_ids),
                    "batting": len(moved_bat_ids),
                    "bowling": len(_ids(bowling_rows)),
                    "fielding": len(_ids(fielding_rows)),
                    "bowler_wickets": len(bowler_wkt_ids),
                    "appearances": len(moved_appearance_game_ids),
                    "milestones": len(_ids(milestone_rows)),
                    "imported_stats": len(moved_imported_ids),
                },
            },
        )

        await db.commit()
    except IntegrityError as e:
        # A data conflict (e.g. both records hold the same physical row under a
        # unique constraint) — surface a clear 409 instead of a bare 500 so the
        # operator knows the merge was blocked, not silently corrupted.
        await db.rollback()
        log.warning("merge_players conflict org=%s keep=%s remove=%s: %s", org_id, keep_id, remove_id, getattr(e, "orig", e))
        raise HTTPException(
            status_code=409,
            detail=f"Couldn't merge these players — a data conflict blocked it: {getattr(e, 'orig', e)}",
        )

    if moved_imported_ids:
        # import_effective_deltas (the blended-into-the-dashboard totals) is
        # fully derived from imported_stats and rebuilt wholesale on every
        # call — regenerate it now so the kept player's effective stats
        # reflect the moved rows immediately, not just after the next sync.
        # Best-effort: a hiccup here must not turn an already-committed merge
        # into a 500 (the next sync/import self-heals it regardless).
        try:
            await reconcile_imported_totals(str(org_id))
        except Exception:
            log.exception("merge_players: post-merge reconcile_imported_totals failed org=%s", org_id)

    return {"status": "merged", "kept_player_id": str(keep_id), "removed_player_id": str(remove_id)}


@router.post("/merge-players")
async def merge_players(req: MergeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_cap(MANAGE_MERGES))):
    return await _merge_players_core(
        db, uuid.UUID(req.keep_player_id), uuid.UUID(req.remove_player_id), uuid.UUID(req.org_id), current_user,
    )


class UndoMergeRequest(BaseModel):
    merge_log_id: int
    org_id: str


# ─── Grade merge ─────────────────────────────────────────

def _resolve_canonical_grade(canonical_chain: dict[str, str], name: str) -> str:
    seen = set()
    current = name
    while current in canonical_chain and current not in seen:
        seen.add(current)
        current = canonical_chain[current]
    return current


@router.get("/grades-with-stats")
async def list_grades_with_stats(org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    """List distinct grade names in an org with aggregate stats, applying active merges."""
    raw = await db.execute(
        text("""
            SELECT
                gr.name AS grade_name,
                COALESCE(MAX(gr.display_name_override), gr.name) AS display_name,
                MAX(gr.category) AS category,
                bool_and(COALESCE(gr.is_public, true)) AS is_public,
                MAX(gr.display_order) AS display_order,
                COUNT(DISTINCT g.id) AS games,
                COUNT(DISTINCT bi.player_id) AS players,
                COALESCE(SUM(bi.runs), 0) AS runs
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN v_effective_games g ON g.grade_id = gr.id
            LEFT JOIN v_effective_batting_innings bi ON bi.game_id = g.id
            WHERE s.organisation_id = :org_id
            GROUP BY gr.name
            ORDER BY gr.name
        """),
        {"org_id": org_id},
    )
    raw_rows = [dict(r) for r in raw.mappings().all()]

    # Classification is its own query on purpose. Unnesting the two array
    # columns into the aggregate above would multiply every batting row by the
    # number of tags on the grade and silently inflate the runs column.
    class_rows = await db.execute(
        text("""
            SELECT gr.name AS grade_name,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT c), NULL)  AS categories,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT f), NULL)  AS match_formats,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT mf), NULL) AS seen_formats
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN LATERAL unnest(COALESCE(gr.categories, '{}'::text[])) AS c ON TRUE
            LEFT JOIN LATERAL unnest(COALESCE(gr.match_formats, '{}'::text[])) AS f ON TRUE
            LEFT JOIN LATERAL (
                SELECT DISTINCT g2.match_format AS mf
                FROM v_effective_games g2
                WHERE g2.grade_id = gr.id AND g2.match_format IS NOT NULL
            ) obs ON TRUE
            WHERE s.organisation_id = :org_id
            GROUP BY gr.name
        """),
        {"org_id": org_id},
    )
    classification = {r["grade_name"]: dict(r) for r in class_rows.mappings().all()}

    log_rows = await db.execute(
        text("""
            SELECT alias_name, canonical_name
            FROM grade_merge_logs
            WHERE org_id = :org_id AND undone_at IS NULL
        """),
        {"org_id": org_id},
    )
    alias_to_canonical = {r["alias_name"]: r["canonical_name"] for r in log_rows.mappings().all()}

    # Map original name -> display_name for lookup after merge resolution
    display_name_map = {row["grade_name"]: row["display_name"] for row in raw_rows}

    # A row's own confirmed category (keyed by raw grade name) so a merged group
    # can prefer the canonical's category over an alias's.
    category_by_name = {row["grade_name"]: normalise_category(row["category"]) for row in raw_rows}

    bucket: dict[str, dict] = {}
    aliases_by_canonical: dict[str, list[str]] = {}
    for row in raw_rows:
        name = row["grade_name"]
        canonical = _resolve_canonical_grade(alias_to_canonical, name)
        slot = bucket.setdefault(canonical, {
            "grade_name": canonical,
            "display_name": display_name_map.get(canonical, canonical),
            "games": 0,
            "players": 0,
            "runs": 0,
            "aliases": [],
            "category": None,
            "categories": set(),
            "match_formats": set(),
            "seen_formats": set(),
            "is_public": True,
            "display_order": None,
        })
        cls = classification.get(name) or {}
        slot["categories"].update(
            c for c in (normalise_category(v) for v in (cls.get("categories") or [])) if c
        )
        slot["match_formats"].update(
            f for f in (normalise_format(v) for v in (cls.get("match_formats") or [])) if f
        )
        slot["seen_formats"].update(
            f for f in (format_from_match_type(v) for v in (cls.get("seen_formats") or [])) if f
        )
        slot["games"] += int(row["games"] or 0)
        slot["runs"] += int(row["runs"] or 0)
        slot["players"] = max(slot["players"], int(row["players"] or 0))
        # Category: prefer the canonical's own, else any confirmed value in the group.
        if slot["category"] is None:
            slot["category"] = normalise_category(row["category"])
        # A merged group is public only if every grade in it is public.
        slot["is_public"] = slot["is_public"] and bool(row["is_public"])
        # display_order is written identically across a merged group, but take
        # the lowest seen defensively rather than assume that always holds.
        if row["display_order"] is not None and (
                slot["display_order"] is None or row["display_order"] < slot["display_order"]):
            slot["display_order"] = row["display_order"]
        if name != canonical:
            slot["aliases"].append(name)
            aliases_by_canonical.setdefault(canonical, []).append(name)

    # Prefer the canonical row's own confirmed category if it has one.
    for canonical, slot in bucket.items():
        if category_by_name.get(canonical):
            slot["category"] = category_by_name[canonical]
        label = slot["display_name"] or canonical
        slot["suggested_category"] = suggest_category(label)
        slot["category_confirmed"] = slot["category"] is not None
        # Effective category readers/UI use when nothing is confirmed yet.
        slot["category"] = slot["category"] or slot["suggested_category"]

        # The two multi-valued axes. Each reports what is CONFIRMED, what would
        # be suggested, and which of the two the effective answer came from, so
        # the screen can mark a row as a guess rather than pass one off as the
        # club's own decision.
        suggested_cats = list(suggest_categories(label))
        confirmed_cats = [c for c in GRADE_CATEGORIES if c in slot["categories"]]
        if not confirmed_cats and slot["category_confirmed"]:
            # A club that only ever used the single-value dropdown.
            confirmed_cats = [slot["category"]]
        slot["categories"] = confirmed_cats or suggested_cats
        slot["suggested_categories"] = suggested_cats
        slot["categories_confirmed"] = bool(confirmed_cats)

        # Format falls back the same way grade_scope reads it: what the club
        # ticked, else what this grade's games actually were, else the name.
        suggested_fmts = [
            f for f in MATCH_FORMATS
            if f in (set(suggest_formats(label)) | slot["seen_formats"])
        ]
        confirmed_fmts = [f for f in MATCH_FORMATS if f in slot["match_formats"]]
        slot["match_formats"] = confirmed_fmts or suggested_fmts
        slot["suggested_formats"] = suggested_fmts
        slot["formats_confirmed"] = bool(confirmed_fmts)
        slot.pop("seen_formats", None)

    out = list(bucket.values())
    # The club's own reading order first (unordered sorts after every ordered
    # grade, not interleaved at position 0), alphabetical within that — same
    # shown-order rule as the AFL Merge Grades screen.
    out.sort(key=lambda r: (r["display_order"] is None, r["display_order"] or 0, r["display_name"].lower()))
    return out


class MergeGradesRequest(BaseModel):
    org_id: str
    alias_name: str
    canonical_name: str


@router.post("/merge-grades")
async def merge_grades(req: MergeGradesRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_cap(MANAGE_MERGES))):
    """Mark `alias_name` as a variant of `canonical_name` for the given org."""
    alias = req.alias_name.strip()
    canonical = req.canonical_name.strip()
    if not alias or not canonical:
        raise HTTPException(status_code=400, detail="Both grade names are required")
    if alias == canonical:
        raise HTTPException(status_code=400, detail="Alias and canonical grade are the same")

    existing = await db.execute(
        text("""
            SELECT alias_name, canonical_name
            FROM grade_merge_logs
            WHERE org_id = :org_id AND undone_at IS NULL
        """),
        {"org_id": req.org_id},
    )
    chain = {r["alias_name"]: r["canonical_name"] for r in existing.mappings().all()}

    resolved_canonical = _resolve_canonical_grade(chain, canonical)
    if resolved_canonical == alias:
        raise HTTPException(status_code=400, detail="That merge would create a cycle")

    # If alias is itself currently a canonical for other merges, redirect those to the new canonical
    await db.execute(
        text("""
            UPDATE grade_merge_logs
            SET canonical_name = :new_canonical
            WHERE org_id = :org_id
              AND undone_at IS NULL
              AND canonical_name = :alias
        """),
        {"org_id": req.org_id, "new_canonical": resolved_canonical, "alias": alias},
    )

    # If this exact alias already maps, replace with the resolved canonical
    await db.execute(
        text("""
            UPDATE grade_merge_logs
            SET undone_at = NOW()
            WHERE org_id = :org_id
              AND undone_at IS NULL
              AND alias_name = :alias
        """),
        {"org_id": req.org_id, "alias": alias},
    )

    await db.execute(
        text("""
            INSERT INTO grade_merge_logs (org_id, alias_name, canonical_name)
            VALUES (:org_id, :alias, :canonical)
        """),
        {"org_id": req.org_id, "alias": alias, "canonical": resolved_canonical},
    )

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=req.org_id, user_id=current_user.id,
        action="merge_grades", target_type="grade", target_id=resolved_canonical,
        details={"alias_name": alias, "canonical_name": resolved_canonical},
    )

    await db.commit()
    return {"status": "merged", "alias": alias, "canonical": resolved_canonical}


class GradeClassifyRequest(BaseModel):
    grade_name: str                 # canonical grade name (as shown in grades-with-stats)
    category: str | None = None     # omit to leave unchanged; one of GRADE_CATEGORIES
    # Every category this grade belongs to — a grade can be more than one
    # ("Girls Under 14" is junior AND women's). Omit to leave unchanged; an
    # empty list clears back to the name-based suggestion. `category` is kept in
    # step with the first entry so every reader of the single column is
    # unaffected, and sending `category` alone still works.
    categories: list[str] | None = None
    # Which format(s) this grade plays — two_day / one_day / t20. Omit to leave
    # unchanged; an empty list clears back to what the games themselves say.
    match_formats: list[str] | None = None
    is_public: bool | None = None   # omit to leave unchanged
    # The club's reading order for this grade — 1 = first. Pass -1 to clear it
    # back to unordered (a plain None can't mean "clear" here, since None is
    # already what "leave unchanged" means for every other field on this model).
    display_order: int | None = None


def _grade_name_group(chain: dict[str, str], target: str) -> set[str]:
    """All raw grade names that roll up to ``target`` (canonical + its aliases)."""
    names = {target}
    for alias in chain:
        if _resolve_canonical_grade(chain, alias) == target:
            names.add(alias)
    return names


@router.patch("/grades/classify")
async def classify_grade(
    req: GradeClassifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    """Set a grade's public category and/or visibility.

    Applies to every grade row that rolls up to this name (the canonical name
    plus any merged aliases), so a merged grade stays consistent, and across all
    seasons — the label attaches to the grade name club-wide, like the rename.
    """
    org_id = str(club.id)
    logs = await db.execute(
        text("""
            SELECT alias_name, canonical_name FROM grade_merge_logs
            WHERE org_id = :org AND undone_at IS NULL
        """),
        {"org": org_id},
    )
    chain = {r["alias_name"]: r["canonical_name"] for r in logs.mappings().all()}
    names = list(_grade_name_group(chain, req.grade_name))

    sets: list[str] = []
    params: dict = {"org": org_id, "names": names}
    if req.categories is not None:
        picked = {c for c in (normalise_category(c) for c in req.categories) if c}
        if req.categories and not picked:
            raise HTTPException(status_code=400, detail="Invalid grade category")
        ordered = [c for c in GRADE_CATEGORIES if c in picked]
        sets.append("categories = :categories")
        params["categories"] = ordered or None
        # `category` is the one-answer view of the same decision and stays in
        # step, so the public grade grouping, the AFL-style single-label readers
        # and grade_labels.org_grade_categories all keep working. Cleared to
        # NULL when the selection is cleared, which is what puts the row back on
        # its name-based suggestion rather than stranding a stale label.
        sets.append("category = :category")
        params["category"] = ordered[0] if ordered else None
    elif req.category is not None:
        cat = normalise_category(req.category)
        if cat is None:
            raise HTTPException(status_code=400, detail="Invalid grade category")
        sets.append("category = :category")
        params["category"] = cat
        sets.append("categories = :categories")
        params["categories"] = [cat]
    if req.match_formats is not None:
        picked_f = {f for f in (normalise_format(f) for f in req.match_formats) if f}
        if req.match_formats and not picked_f:
            raise HTTPException(status_code=400, detail="Invalid match format")
        ordered_f = [f for f in MATCH_FORMATS if f in picked_f]
        sets.append("match_formats = :match_formats")
        params["match_formats"] = ordered_f or None
    if req.is_public is not None:
        sets.append("is_public = :is_public")
        params["is_public"] = req.is_public
    if req.display_order is not None:
        sets.append("display_order = :display_order")
        params["display_order"] = None if req.display_order < 0 else req.display_order
    if not sets:
        return {"updated": 0, "grade_name": req.grade_name}

    result = await db.execute(
        text(f"""
            UPDATE grades gr
            SET {", ".join(sets)}
            FROM seasons s
            WHERE gr.season_id = s.id
              AND s.organisation_id = :org
              AND gr.name = ANY(:names)
        """),
        params,
    )
    await db.commit()
    return {
        "updated": result.rowcount,
        "grade_name": req.grade_name,
        "category": params.get("category"),
        "categories": params.get("categories"),
        "match_formats": params.get("match_formats"),
        "is_public": params.get("is_public"),
    }


class GradeReorderRequest(BaseModel):
    # Canonical grade names, in the order the club wants them read.
    grade_names: list[str]


@router.post("/grades/reorder")
async def reorder_grades(
    req: GradeReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    """Set the whole reading order in one write — Seniors 1, Reserves 2,
    Under 19s 3 — rather than one number at a time.

    Numbering is assigned from the submitted order (1..N) instead of trusting
    numbers from the browser, so the stored orders can never collide or leave
    gaps however the list was dragged about. A name that isn't a grade in this
    club is skipped without consuming a position, rather than failing the save:
    the list comes from a browser and may be a page-load behind a merge.

    The submitted list is the WHOLE ordering, so a grade left out of it is
    reset to unordered rather than keeping a stale number. The admin screen
    always submits every grade it is showing, so "left out" in practice means
    a grade created since the page loaded — and letting that one keep an old
    position is how two grades end up both claiming position 1.
    """
    org_id = str(club.id)
    logs = await db.execute(
        text("""
            SELECT alias_name, canonical_name FROM grade_merge_logs
            WHERE org_id = :org AND undone_at IS NULL
        """),
        {"org": org_id},
    )
    chain = {r["alias_name"]: r["canonical_name"] for r in logs.mappings().all()}

    updated = 0
    seen: set[str] = set()
    position = 0
    for raw_name in req.grade_names:
        canonical = _resolve_canonical_grade(chain, (raw_name or "").strip())
        if not canonical or canonical in seen:
            continue
        seen.add(canonical)
        # Applies to the canonical name AND every alias merged into it, so a
        # merged grade orders as one competition however its rows are spelt.
        names = list(_grade_name_group(chain, canonical))
        res = await db.execute(
            text("""
                UPDATE grades gr SET display_order = :pos
                FROM seasons s
                WHERE gr.season_id = s.id AND s.organisation_id = :org AND gr.name = ANY(:names)
            """),
            {"pos": position + 1, "org": org_id, "names": names},
        )
        # The position is only consumed once a real grade has taken it — a
        # name that matched nothing would otherwise burn a number and leave a
        # gap in the sequence.
        if res.rowcount:
            position += 1
            updated += res.rowcount

    # Anything the list didn't name goes back to unordered, so the stored
    # sequence is exactly 1..N with nothing stale alongside it.
    if seen:
        all_named: set[str] = set()
        for canonical in seen:
            all_named |= _grade_name_group(chain, canonical)
        await db.execute(
            text("""
                UPDATE grades gr SET display_order = NULL
                FROM seasons s
                WHERE gr.season_id = s.id AND s.organisation_id = :org
                  AND gr.display_order IS NOT NULL AND NOT (gr.name = ANY(:names))
            """),
            {"org": org_id, "names": list(all_named)},
        )

    await db.commit()
    return {"updated": updated, "ordered": position}


@router.post("/grades/clear-order")
async def clear_grade_order(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    """Drop the club's ordering entirely, back to the app's own default
    (alphabetical)."""
    res = await db.execute(
        text("""
            UPDATE grades gr SET display_order = NULL
            FROM seasons s
            WHERE gr.season_id = s.id AND s.organisation_id = :org AND gr.display_order IS NOT NULL
        """),
        {"org": str(club.id)},
    )
    await db.commit()
    return {"updated": res.rowcount or 0}


@router.post("/grades/apply-suggestions")
async def apply_grade_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    """Persist the suggested classification for every not-yet-classified grade.

    One-click starting point; admins can still correct any. Covers both axes:
    the category comes from the grade name, the format from the formats actually
    recorded on that grade's games (``games.match_format``) falling back to the
    name. A grade whose format still can't be told is left alone rather than
    given a guess — an unclassified grade drops out of a match-type filter,
    and a wrong tag would put it in the wrong one instead.
    """
    org_id = str(club.id)
    rows = await db.execute(
        text("""
            SELECT gr.name,
                   bool_or(gr.category IS NULL)      AS needs_category,
                   bool_or(gr.match_formats IS NULL) AS needs_formats,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT g.match_format), NULL) AS seen
            FROM grades gr
            JOIN seasons s ON s.id = gr.season_id
            LEFT JOIN v_effective_games g ON g.grade_id = gr.id
            WHERE s.organisation_id = :org
              AND (gr.category IS NULL OR gr.match_formats IS NULL)
            GROUP BY gr.name
        """),
        {"org": org_id},
    )
    pending = rows.mappings().all()
    updated = 0
    for row in pending:
        name = row["name"]
        if row["needs_category"]:
            cats = list(suggest_categories(name))
            res = await db.execute(
                text("""
                    UPDATE grades gr
                    SET category = :cat, categories = :cats
                    FROM seasons s
                    WHERE gr.season_id = s.id
                      AND s.organisation_id = :org
                      AND gr.name = :name
                      AND gr.category IS NULL
                """),
                {"cat": cats[0], "cats": cats, "org": org_id, "name": name},
            )
            updated += res.rowcount or 0
        seen = {f for f in (format_from_match_type(v) for v in (row["seen"] or [])) if f}
        fmts = [f for f in MATCH_FORMATS if f in (seen | set(suggest_formats(name)))]
        if row["needs_formats"] and fmts:
            res = await db.execute(
                text("""
                    UPDATE grades gr
                    SET match_formats = :fmts
                    FROM seasons s
                    WHERE gr.season_id = s.id
                      AND s.organisation_id = :org
                      AND gr.name = :name
                      AND gr.match_formats IS NULL
                """),
                {"fmts": fmts, "org": org_id, "name": name},
            )
            updated += res.rowcount or 0
    await db.commit()
    return {"updated": updated, "grades": len(pending)}


# ---------------------------------------------------------------------------
# Competitions (migration 282)
#
# A club plays across several competitions, sometimes several run by ONE
# association and sometimes across associations in the same season. Cricket
# Australia publishes the association on every grade and no competition at
# all, so the association is synced and the competition is the club's own
# named group of grades — see services/competitions.py for the evidence.
#
# These sit on the Manage Grades capability (MANAGE_MERGES) because that is
# the screen that already owns "what is this grade, and how does the club
# read it": its name, its category, its formats and its order. A competition
# is the same kind of decision.
# ---------------------------------------------------------------------------


class CompetitionCreate(BaseModel):
    name: str
    # Optional: the association this competition belongs to, so a competition
    # a club adds by hand under an association it already plays is recognised
    # as that association's rather than reading as unaffiliated.
    association_id: str | None = None


class CompetitionRename(BaseModel):
    name: str


class CompetitionAssign(BaseModel):
    # The grade NAME, not an id: a grade is one thing to a club across every
    # season it ran, so assigning it moves all of its season rows at once —
    # the same rule the category and display-order editors on this screen
    # already follow.
    grade_name: str
    # None un-groups the grade rather than deleting anything.
    competition_id: str | None = None


class CompetitionReorder(BaseModel):
    competition_ids: list[str]


@router.get("/competitions")
async def list_club_competitions(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    """The club's competitions, its grades and which competition each is in.

    One request for the whole screen: the competitions with what they hold,
    every grade name with its current competition, and the associations CA
    reports — which is what the "group these for me" button is built from.
    """
    from app.services import competitions as comp_svc
    return {
        "competitions": await comp_svc.list_competitions(db, club.id),
        "grades": await comp_svc.competition_grades(db, club.id),
        "associations": await comp_svc.org_associations(db, club.id),
    }


@router.post("/competitions")
async def create_club_competition(
    req: CompetitionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    from app.services import competitions as comp_svc
    try:
        created = await comp_svc.create_competition(
            db, club.id, req.name, req.association_id
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=str(club.id), user_id=current_user.id,
        action="create_competition", target_type="competition",
        target_id=created["id"], details={"name": created["name"]},
    )
    await db.commit()
    return created


@router.patch("/competitions/{competition_id}")
async def rename_club_competition(
    competition_id: str,
    req: CompetitionRename,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    from app.services import competitions as comp_svc
    try:
        await comp_svc.rename_competition(db, club.id, competition_id, req.name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=str(club.id), user_id=current_user.id,
        action="rename_competition", target_type="competition",
        target_id=competition_id, details={"name": req.name},
    )
    await db.commit()
    return {"status": "renamed"}


@router.delete("/competitions/{competition_id}")
async def delete_club_competition(
    competition_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    """Delete a competition. Its grades are un-grouped, never deleted.

    Nothing about a game, a stat or a grade's own name changes — the grades
    simply stop being grouped, and can be put in another competition.
    """
    from app.services import competitions as comp_svc
    try:
        await comp_svc.delete_competition(db, club.id, competition_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=str(club.id), user_id=current_user.id,
        action="delete_competition", target_type="competition",
        target_id=competition_id, details={},
    )
    await db.commit()
    return {"status": "deleted"}


@router.post("/competitions/assign")
async def assign_grade_to_competition(
    req: CompetitionAssign,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    from app.services import competitions as comp_svc
    try:
        moved = await comp_svc.assign_grade(
            db, club.id, req.grade_name, req.competition_id
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await db.commit()
    return {"status": "assigned", "season_rows": moved}


@router.post("/competitions/reorder")
async def reorder_club_competitions(
    req: CompetitionReorder,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    from app.services import competitions as comp_svc
    await comp_svc.reorder_competitions(db, club.id, req.competition_ids)
    await db.commit()
    return {"status": "reordered"}


@router.get("/competitions/grouping")
async def competition_grouping_state(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
    club: Organisation = Depends(get_current_club),
):
    """Is anything still outside this club's competitions, and is a job running.

    Read on every visit to Manage Grades, which is what turns the prompt on
    the moment an admin finishes naming their competitions. A club with
    nothing to fetch reports `needs_grouping: false` and the screen offers
    nothing, because a button that would write nothing is worse than no
    button.
    """
    from app.services import competition_grouping as grouping
    state = await grouping.grouping_gap(db, club.id)
    state["running_run_id"] = await grouping.running_run_id(db, club.id)
    return state


@router.post("/competitions/grouping")
async def start_competition_grouping(
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    """Fetch the missing associations and group what that unlocks.

    One Cricket Australia call per season, so it runs in the background and
    the screen polls `GET /club-admin/sync-runs/{id}` for the bar. Returns the
    run id either way: a club that already has one in flight is handed THAT
    run rather than a second one, so two admins pressing the button at the
    same moment watch the same job instead of racing each other's writes.

    Safe to run twice by construction, so there is no confirm on it: only a
    grade with no association is written, and the seeder never renames or
    re-points a competition the club has edited.
    """
    from app.services import competition_grouping as grouping
    from app.services.sync import start_sync_run

    existing = await grouping.running_run_id(db, club.id)
    if existing:
        return {"run_id": existing, "status": "already_running"}

    run_id = await start_sync_run(
        club.id, grouping.RUN_KIND, triggered_by_user_id=current_user.id,
    )
    background.add_task(grouping.run_grouping_job, club.id, run_id)
    return {"run_id": str(run_id), "status": "started"}


@router.post("/competitions/seed")
async def seed_club_competitions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_cap(MANAGE_MERGES)),
    club: Organisation = Depends(get_current_club),
):
    """Group every un-grouped grade, one competition per association.

    SKIP, NEVER REPLACE — a competition the club has renamed or split is left
    exactly as it is, so pressing this twice cannot undo anyone's work. It is
    the same function every sync runs, offered as a button for a club that
    wants its grades grouped now rather than after the next sync.
    """
    from app.services import competitions as comp_svc
    result = await comp_svc.seed_competitions_for_org(db, club.id)
    await db.commit()
    return result


@router.get("/grade-merge-history")
async def grade_merge_history(org_id: str, db: AsyncSession = Depends(get_db), _: User = Depends(get_current_user)):
    rows = await db.execute(
        text("""
            SELECT id, merged_at, alias_name, canonical_name, undone_at
            FROM grade_merge_logs
            WHERE org_id = :org_id
            ORDER BY merged_at DESC
            LIMIT 100
        """),
        {"org_id": org_id},
    )
    return [
        {
            "id": r["id"],
            "merged_at": r["merged_at"].isoformat() if r["merged_at"] else None,
            "alias_name": r["alias_name"],
            "canonical_name": r["canonical_name"],
            "undone": r["undone_at"] is not None,
        }
        for r in rows.mappings().all()
    ]


class UndoGradeMergeRequest(BaseModel):
    merge_log_id: int
    org_id: str


@router.post("/undo-grade-merge")
async def undo_grade_merge(req: UndoGradeMergeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_cap(MANAGE_MERGES))):
    result = await db.execute(
        text("""
            UPDATE grade_merge_logs
            SET undone_at = NOW()
            WHERE id = :id AND org_id = :org_id AND undone_at IS NULL
            RETURNING id
        """),
        {"id": req.merge_log_id, "org_id": req.org_id},
    )
    if result.first() is None:
        raise HTTPException(status_code=404, detail="Merge log not found or already undone")

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=req.org_id, user_id=current_user.id,
        action="undo_merge_grades", target_type="grade_merge_log",
        target_id=str(req.merge_log_id),
    )
    await db.commit()
    return {"status": "undone"}


@router.post("/undo-merge")
async def undo_merge(req: UndoMergeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_cap(MANAGE_MERGES))):
    """Reverse a previous merge: re-create removed player and reassign records back."""
    log_row = await db.execute(
        text("SELECT * FROM merge_logs WHERE id = :id AND org_id = :org_id"),
        {"id": req.merge_log_id, "org_id": req.org_id},
    )
    log = log_row.mappings().first()
    if not log:
        raise HTTPException(status_code=404, detail="Merge log not found")
    if log["undone_at"] is not None:
        raise HTTPException(status_code=400, detail="This merge has already been undone")

    keep_id = log["keep_player_id"]
    remove_id = log["removed_player_id"]

    keep = await db.get(Player, keep_id)
    if not keep:
        raise HTTPException(status_code=404, detail="Keep player no longer exists")

    # Reverse playhq_id copy on keep player FIRST, before re-creating the removed player,
    # to avoid unique constraint violation (organisation_id, playhq_id).
    if log["keep_original_playhq_id"] is None and log["removed_player_playhq_id"]:
        keep.playhq_id = None
        await db.flush()

    # Re-create removed player. grassroots_id (raw CA participant GUID, added in
    # migration 062) must be restored or the next sync won't find this row by
    # (org, grassroots_id) and would mint a fresh per-club duplicate. The merge
    # log predates the column, but for every legacy row the id IS the raw GUID,
    # so id::text is the correct value (it's exactly what 062's backfill used).
    await db.execute(
        text("""
            INSERT INTO players (id, name, organisation_id, playhq_id, grassroots_id, claimed)
            VALUES (:id, :name, :org_id, :playhq_id, :grassroots_id, false)
            ON CONFLICT (id) DO NOTHING
        """),
        {
            "id": str(remove_id),
            "name": log["removed_player_name"],
            "org_id": req.org_id,
            "playhq_id": log["removed_player_playhq_id"],
            "grassroots_id": str(remove_id),
        },
    )

    # asyncpg returns JSONB columns as Python lists already; guard against
    # legacy string-encoded rows just in case.
    def _jlist(val):
        if isinstance(val, list):
            return val
        return json.loads(val or "[]")

    # Reassign game-level records back
    bat_ids = _jlist(log["batting_innings_ids"])
    if bat_ids:
        await db.execute(
            text("UPDATE batting_innings SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": bat_ids},
        )
    bowl_ids = _jlist(log["bowling_spell_ids"])
    if bowl_ids:
        await db.execute(
            text("UPDATE bowling_spells SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": bowl_ids},
        )
    field_ids = _jlist(log["fielding_stat_ids"])
    if field_ids:
        await db.execute(
            text("UPDATE fielding_stats SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": field_ids},
        )
    fow_ids = _jlist(log["fall_of_wicket_ids"])
    if fow_ids:
        await db.execute(
            text("UPDATE fall_of_wickets SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": fow_ids},
        )
    b1_ids = _jlist(log["batter1_partnership_ids"])
    if b1_ids:
        await db.execute(
            text("UPDATE partnerships SET batter1_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": b1_ids},
        )
    b2_ids = _jlist(log["batter2_partnership_ids"])
    if b2_ids:
        await db.execute(
            text("UPDATE partnerships SET batter2_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": b2_ids},
        )
    mil_ids = _jlist(log["milestone_ids"])
    if mil_ids:
        await db.execute(
            text("UPDATE milestones SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": mil_ids},
        )

    pss_ids = _jlist(log["moved_season_stat_ids"])
    if pss_ids:
        await db.execute(
            text("UPDATE player_season_stats SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": pss_ids},
        )

    # Newer merges also reassign bowler_wickets, player_season_grade_stats and
    # game_appearances. Older merge logs predate these columns; the idempotent
    # ALTERs in main.py backfill them to '[]', so _jlist yields an empty list and
    # these are no-ops for legacy rows. (.get guards the rare un-migrated case.)
    bw_ids = _jlist(log.get("bowler_wicket_ids"))
    if bw_ids:
        await db.execute(
            text("UPDATE bowler_wickets SET bowler_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": bw_ids},
        )
    fw_ids = _jlist(log.get("fielder_wicket_ids"))
    if fw_ids:
        await db.execute(
            text("UPDATE bowler_wickets SET fielder_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": fw_ids},
        )
    grade_ids = _jlist(log.get("grade_stat_ids"))
    if grade_ids:
        await db.execute(
            text("UPDATE player_season_grade_stats SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": grade_ids},
        )
    appear_ids = _jlist(log.get("appearance_game_ids"))
    if appear_ids:
        # Only the rows that were genuinely moved (keep had no appearance for that
        # game at merge time) are recorded, so moving them back off keep is safe.
        await db.execute(
            text(
                "UPDATE game_appearances SET player_id = :pid "
                "WHERE player_id = :kid AND game_id::text = ANY(:ids)"
            ),
            {"pid": str(remove_id), "kid": str(keep_id), "ids": appear_ids},
        )
    imported_ids = _jlist(log.get("imported_stat_ids"))
    if imported_ids:
        await db.execute(
            text("UPDATE imported_stats SET player_id = :pid WHERE id = ANY(:ids)"),
            {"pid": str(remove_id), "ids": imported_ids},
        )

    await db.execute(
        text("UPDATE merge_logs SET undone_at = NOW() WHERE id = :id"),
        {"id": req.merge_log_id},
    )

    from app.services.audit_log import log_activity
    await log_activity(
        db, org_id=req.org_id, user_id=current_user.id,
        action="undo_merge_players", target_type="player", target_id=str(remove_id),
        details={
            "merge_log_id": req.merge_log_id,
            "restored_player": {"id": str(remove_id), "name": log["removed_player_name"]},
            "kept_player": {"id": str(keep_id), "name": log["keep_player_name"]},
        },
    )

    await db.commit()

    if imported_ids:
        try:
            await reconcile_imported_totals(req.org_id)
        except Exception:
            log.exception("undo_merge: post-undo reconcile_imported_totals failed org=%s", req.org_id)

    return {"status": "undone", "restored_player_id": str(remove_id)}


# ─── Social: fetch Grassroots scorecard for social image builder ──────────────

_DNB_TYPES = {"did not bat", "dnb", "absent", "absent hurt"}
_NOT_OUT_ID = 1  # dismissalTypeId == 1 means "not out" in GR API


def _overs_str(overs_raw) -> str:
    """Convert oversBowled string/float or balls int to 'X.Y' display string."""
    if overs_raw is None:
        return "0"
    if isinstance(overs_raw, str) and "." in overs_raw:
        return overs_raw
    try:
        balls = int(float(str(overs_raw)) * 6) if "." not in str(overs_raw) else None
        if balls is not None:
            return f"{balls // 6}.{balls % 6}"
        # already X.Y format
        return str(overs_raw)
    except (TypeError, ValueError):
        return str(overs_raw)


def _org_logo_url(org) -> str | None:
    """An org's crest, uploaded bytes or hosted URL — same precedence
    ``social_rounds._club_dict`` uses."""
    if org is None:
        return None
    if org.logo_url:
        return org.logo_url
    if org.logo_data:
        return f"/api/images/organisations/{org.id}/logo"
    return None


def _org_colour(org) -> str | None:
    """An org's own brand colour for a post.

    Same fallback chain the frontend's ``orgAccent`` walks — theme_config's
    accent (what the branding page actually edits) before the mirrored
    accent_color column and the legacy primary_color. Reading primary_color
    first leaves most clubs on the platform's default green, since nothing
    edits that column any more.
    """
    if org is None:
        return None
    theme = org.theme_config if isinstance(org.theme_config, dict) else {}
    return theme.get("accent") or org.accent_color or org.primary_color or None


async def _org_for_team(team_raw: dict, team_name: str, db: AsyncSession, club=None):
    """Which club in our own data is this side of the match?

    In priority order:

    1. The viewing club, when the match names it. Our own crest and colours
       are the ones we control and can vouch for, and a post a club builds
       about its own game should plainly be in its own colours.
    2. The Grassroots ``owningOrganisation.id``, which IS ``organisations.id``
       for a club we hold — the strongest link there is, and free.
    3. The team name against our org names, which is all a never-synced
       opponent leaves us.

    The name step is deliberately the last resort and deliberately strict.
    The old version matched on ANY word over three characters, unscoped, so
    "CVPCC Fifth XI" could pick up whichever club in the whole database
    happened to have "Fifth" in its name — and a grade-level team name is
    routinely a sponsor's name rather than a club's.
    """
    from sqlalchemy import or_, func

    own = (team_raw.get("owningOrganisation") or {}) if isinstance(team_raw, dict) else {}
    own_id = own.get("id") or own.get("organisationId")
    club_id = str(club.id).lower() if club is not None and getattr(club, "id", None) else None

    if club_id and own_id and str(own_id).lower() == club_id:
        return club
    if own_id:
        try:
            hit = await db.get(Organisation, uuid.UUID(str(own_id)))
            if hit:
                return hit
        except (ValueError, TypeError):
            pass

    # An owning organisation with a name of its own beats the grade-level
    # team name, which carries the sponsor ("A Grade (Gatorade)").
    for candidate in (own.get("name"), team_name):
        words = [w for w in re.split(r"\W+", (candidate or "").upper()) if len(w) > 3]
        if not words:
            continue
        if club is not None and club.name:
            club_words = {w for w in re.split(r"\W+", club.name.upper()) if len(w) > 3}
            if club_words & set(words):
                return club
        # Every meaningful word has to appear, not just one of them — a
        # single shared word is how an unrelated club gets picked.
        conditions = [func.upper(Organisation.name).contains(w) for w in words[:3]]
        res = await db.execute(
            select(Organisation).where(*conditions).limit(2)
        )
        hits = res.scalars().all()
        # Two clubs fitting is not an answer. Better a monogram than the
        # wrong club's crest on a post about somebody else's game.
        if len(hits) == 1:
            return hits[0]
    return None


async def _org_logo_for_team(team_name: str, db: AsyncSession) -> str | None:
    """Back-compat wrapper: an org's crest matched from a team name alone."""
    return _org_logo_url(await _org_for_team({}, team_name, db))


async def _rollback_keeping(db: AsyncSession, *instances) -> None:
    """Roll back a best-effort read without stranding the caller's ORM objects.

    ``rollback()`` expires everything the session has loaded, whatever
    ``expire_on_commit`` says. So a swallowed failure here leaves ``club`` — the
    instance ``get_current_club`` loaded on this same session — expired, and the
    next plain attribute read on it two hundred lines below (``club.id``, in
    ``_org_for_team``) is a lazy refresh. A lazy refresh inside an async request
    raises ``greenlet_spawn has not been called``, which is then what the caller
    reports instead of the read that actually failed. Refreshing here is one
    awaited query and hands back an object the rest of the request can read.
    """
    await db.rollback()
    for inst in instances:
        if inst is None:
            continue
        try:
            await db.refresh(inst)
        except Exception:
            log.exception("post-rollback refresh failed for %r", type(inst).__name__)


def _team_id_from_inn(inn: dict) -> str | None:
    for k in ("battingTeamId", "teamId"):
        v = inn.get(k)
        if v:
            return str(v).lower()
    for k in ("battingTeam", "team"):
        obj = inn.get(k)
        if isinstance(obj, dict) and obj.get("id"):
            return str(obj["id"]).lower()
    return None


@router.get("/social/scorecard/{match_id}", dependencies=[Depends(require_module("socials"))])
async def get_social_scorecard(match_id: str, db: AsyncSession = Depends(get_db),
                               _user=Depends(get_current_user), club=Depends(get_current_club)):
    """Fetch a Grassroots scorecard and return it in the social template format.

    Gated behind the BetterSocials module (require_module).
    """
    try:
        return await _get_social_scorecard_inner(match_id, db, club)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("social scorecard %s failed", match_id)
        raise HTTPException(500, f"Scorecard parse error: {exc}") from exc


@router.get("/social/match-lookup", dependencies=[Depends(require_module("socials"))])
async def social_match_lookup(q: str = "", db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    """Work out which match an admin means from whatever they pasted.

    A play.cricket.com.au link (or a bare match ID) carries the Grassroots GUID
    the scorecard import needs and resolves straight through. A playhq.com
    game-centre link carries PlayHQ's own eight-character code instead, which
    maps to nothing on the Grassroots side — so it comes back as a short list
    of the club's own recent matches for the admin to pick from, narrowed by
    the grade in the URL. See services/social_match_lookup for why there is no
    direct translation.
    """
    from app.services.social_match_lookup import resolve_match_reference
    try:
        return await resolve_match_reference(db, club, q)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("social match lookup failed for %s", getattr(club, "id", "?"))
        raise HTTPException(500, f"Match lookup error: {exc}") from exc


@router.get("/social/fixtures", dependencies=[Depends(require_module("socials"))])
async def get_social_fixtures(q: str = "", db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    """Upcoming/live fixtures across the club's grades, grouped by match-day, for
    the BetterSocials Fixtures roundup posts (the multi-match analogue of the
    single-scorecard import).

    ``q`` (optional) is a pasted match link/ID that anchors the pull on that
    match's round instead — every club grade's match that weekend, whatever
    its status, so an off-season or already-started round is still buildable."""
    from app.services.social_rounds import social_fixtures, social_fixtures_for_reference
    try:
        if q.strip():
            return await social_fixtures_for_reference(db, club, q)
        return await social_fixtures(db, club)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("social fixtures import failed for %s", getattr(club, "id", "?"))
        raise HTTPException(500, f"Fixtures import error: {exc}") from exc


@router.get("/social/results", dependencies=[Depends(require_module("socials"))])
async def get_social_results(q: str = "", db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    """Recent completed results across the club's grades, grouped by match-day,
    for the BetterSocials Results roundup posts. Scores come from each match's
    scorecard — the same Grassroots source as the single-scorecard import.

    ``q`` (optional) is a pasted match link/ID that anchors the pull on that
    match's round instead — the whole round's completed club matches, however
    far back, not just the last 90 days."""
    from app.services.social_rounds import social_results, social_results_for_reference
    try:
        if q.strip():
            return await social_results_for_reference(db, club, q)
        return await social_results(db, club)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("social results import failed for %s", getattr(club, "id", "?"))
        raise HTTPException(500, f"Results import error: {exc}") from exc


@router.get("/social/potm/{match_id}", dependencies=[Depends(require_module("socials"))])
async def get_social_potm(match_id: str, db: AsyncSession = Depends(get_db), club=Depends(get_current_club)):
    """Player-of-the-match shortlist for one match — our side's batting, bowling
    and fielding lines from the Grassroots scorecard, ranked by a simple points
    blend, for the BetterSocials POTM post."""
    from app.services.social_rounds import social_potm
    try:
        return await social_potm(db, club, match_id)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("social potm %s failed for %s", match_id, getattr(club, "id", "?"))
        raise HTTPException(500, f"Player of the match error: {exc}") from exc


async def _get_social_scorecard_inner(match_id: str, db: AsyncSession, club=None):
    raw = await get_match_scorecard(match_id)
    if raw is None:
        raise HTTPException(404, "Scorecard not found — match may be PlayHQ-only or not yet completed")

    match_summary = raw.get("matchSummary") or {}
    teams_raw = raw.get("teams") or []
    innings_list = raw.get("innings") or []

    def find_team(tid, exclude=None):
        if tid:
            t = next((t for t in teams_raw if str(t.get("id", "")).lower() == tid), None)
            if t:
                return t
        # Unresolvable id (or none at all, e.g. an innings that carries no
        # battingTeamId) — fall back to a team, but never the one already
        # claimed by the other side. Without `exclude`, a failure to resolve
        # BOTH sides' ids used to make this return the exact same object
        # twice, rendering one team's name on both cards with the other
        # side's data silently dropped.
        return next((t for t in teams_raw if t is not exclude), (teams_raw[0] if teams_raw else {}))

    # "home"/"away" below means "batted first" / "batted second", not the
    # ground's literal home/away designation — which side has home ground is
    # unrelated to who bats first (a team can win the toss and bat first away
    # from home; the reported match had the away side batting first), and a
    # proper scorebook reads left to right in batting order regardless of
    # whose home ground it was. The frontend template already renders `home`
    # on the left labelled "1ST INNINGS" and `away` on the right labelled
    # "2ND INNINGS", so this is the one place that mapping has to be correct.
    sorted_innings = sorted(
        innings_list, key=lambda i: i.get("inningsOrder") or i.get("inningsNumber") or 1
    )
    home_inn = sorted_innings[0] if sorted_innings else {}
    away_inn = sorted_innings[1] if len(sorted_innings) > 1 else {}
    home_id = _team_id_from_inn(home_inn)
    away_id = _team_id_from_inn(away_inn)
    # Cross-fill from whichever side DID resolve, so a one-sided miss (the
    # common case — one innings object missing battingTeamId) still lands the
    # other side on the correct, different team rather than the `find_team`
    # exclude fallback's blunter "just pick a different team" guess below.
    if not home_id and away_id:
        home_id = next(
            (str(t.get("id", "")).lower() for t in teams_raw if str(t.get("id", "")).lower() != away_id), None
        )
    if not away_id and home_id:
        away_id = next(
            (str(t.get("id", "")).lower() for t in teams_raw if str(t.get("id", "")).lower() != home_id), None
        )
    home_team_raw = find_team(home_id)
    away_team_raw = find_team(away_id, exclude=home_team_raw)

    # Collect all participantIds to look up names from DB
    all_pids: set[str] = set()
    for inn in [home_inn, away_inn]:
        for row in (inn.get("batting") or []):
            if row.get("participantId"):
                all_pids.add(row["participantId"])
        for row in (inn.get("bowling") or []):
            if row.get("participantId"):
                all_pids.add(row["participantId"])

    # Build merge-redirect map: removed player UUID → kept player UUID (transitive, no cycles)
    try:
        merge_res = await db.execute(
            text("SELECT removed_player_id::text AS r, keep_player_id::text AS k "
                 "FROM merge_logs WHERE undone_at IS NULL")
        )
        raw_merge = {row.r: row.k for row in merge_res.mappings().all()}
    except Exception:
        log.exception("merge_logs lookup failed for scorecard %s", match_id)
        await _rollback_keeping(db, club)
        raw_merge = {}

    def _resolve_merge(rid, seen=None):
        seen = seen or set()
        if rid in seen or rid not in raw_merge:
            return rid
        seen.add(rid)
        return _resolve_merge(raw_merge[rid], seen)

    merged_away: dict[str, str] = {k: _resolve_merge(k) for k in raw_merge}

    # Include kept-player IDs in the DB query so redirected lookups succeed
    for removed_id in list(all_pids):
        kept = merged_away.get(removed_id.lower())
        if kept:
            all_pids.add(kept)

    name_map: dict[str, tuple[str, str]] = {}  # participantId -> (first, last)
    if all_pids:
        pid_uuids = []
        for p in all_pids:
            try:
                pid_uuids.append(uuid.UUID(p))
            except (ValueError, AttributeError, TypeError):
                continue
        if pid_uuids:
            try:
                res = await db.execute(select(Player).where(Player.id.in_(pid_uuids)))
                for p in res.scalars().all():
                    raw_name = (p.display_name or p.name or "").strip()
                    if ", " in raw_name:
                        # "Surname, Firstname" → last="SURNAME", first="Firstname"
                        last_part, first_part = raw_name.split(", ", 1)
                        first = first_part.strip()
                        last = last_part.strip().upper()
                    else:
                        parts = raw_name.split()
                        if len(parts) >= 2:
                            first = " ".join(parts[1:])
                            last = parts[0].upper()
                        else:
                            first = ""
                            last = parts[0].upper() if parts else ""
                    last = last.rstrip(".,;:")
                    name_map[str(p.id).lower()] = (first, last)
            except Exception:
                log.exception("player name lookup failed for scorecard %s", match_id)
                await _rollback_keeping(db, club)

    # Build roster name map from team player lists (covers opposition players not in our DB)
    roster_name_map: dict[str, tuple[str, str]] = {}
    # Authoritative short name ("Initial Surname", e.g. "J Barendse") for every
    # roster member — the basis for the consistent "F. Surname" performer label.
    short_name_map: dict[str, str] = {}
    for team_r in teams_raw:
        for rp in ((team_r.get("players") or []) + (team_r.get("nonPlayingMembers") or [])):
            pid = (rp.get("participantId") or "").lower()
            if not pid:
                continue
            nm = rp.get("playerShortName") or rp.get("displayName") or rp.get("name")
            if nm and pid not in short_name_map:
                short_name_map[pid] = nm.strip()
            dn = rp.get("displayName") or rp.get("name") or ""
            if dn and pid not in roster_name_map:
                dn = dn.strip()
                if ", " in dn:
                    lp, fp = dn.split(", ", 1)
                    roster_name_map[pid] = (fp.strip(), lp.strip().upper().rstrip(".,;:"))
                else:
                    pts = dn.split()
                    if len(pts) >= 2:
                        # Roster displayName is "First Last": the first token is the
                        # given name, the rest the surname (the old code had this
                        # reversed, so opponents showed their first name).
                        roster_name_map[pid] = (pts[0], " ".join(pts[1:]).upper().rstrip(".,;:"))
                    else:
                        roster_name_map[pid] = ("", dn.upper().rstrip(".,;:"))

    def get_name(pid: str) -> tuple[str, str]:
        key = str(pid).lower()
        if key in name_map:
            return name_map[key]
        kept_id = merged_away.get(key)
        if kept_id and kept_id.lower() in name_map:
            return name_map[kept_id.lower()]
        return roster_name_map.get(key) or ("", "")

    def get_pid(pid: str) -> str | None:
        """The BetterStats player id for this participant (merge-resolved) when the
        player is one of ours, else None — lets the social designer match a top
        performer to their profile photo. Opposition players (roster-only) → None."""
        key = str(pid).lower()
        if key in name_map:
            return key
        kept_id = merged_away.get(key)
        if kept_id and kept_id.lower() in name_map:
            return kept_id.lower()
        return None

    def short_display(pid: str, row_name: str | None) -> str:
        """'F. SURNAME' for a performer label, derived from GR's 'Initial Surname'
        short name (per-row first, roster fallback, DB name last). Consistent for
        our players and the opposition alike — fixes the first/last-name mix-up."""
        raw = (row_name or short_name_map.get(str(pid).lower()) or "").strip()
        if not raw:
            f, l = get_name(pid)
            raw = f"{f} {l}".strip()
        if not raw:
            return ""
        if "," in raw:
            last, first = (x.strip() for x in raw.split(",", 1))
        else:
            parts = raw.split()
            if len(parts) == 1:
                return parts[0].upper().rstrip(".,;:")
            first, last = parts[0], " ".join(parts[1:])
        fi = first[:1].upper()
        last = last.strip().upper().rstrip(".,;:")
        return f"{fi}. {last}" if fi and last else (last or first.upper())

    def parse_batting(batting_rows: list) -> list:
        rows = sorted(batting_rows, key=lambda b: b.get("batOrder") or 99)
        result = []
        for i, b in enumerate(rows):
            dt = (b.get("dismissalType") or "").lower()
            dt_id = b.get("dismissalTypeId") or 0
            dnb = dt in _DNB_TYPES
            not_out = (dt_id == _NOT_OUT_ID or dt == "not out") and not dnb
            pid = b.get("participantId") or ""
            first, last = get_name(pid)
            runs = int(b.get("runsScored") or 0)
            balls = int(b.get("ballsFaced") or 0)
            result.append({
                "num": i + 1,
                "first": first,
                "last": last,
                "short": short_display(pid, b.get("playerShortName")),
                "r": runs,
                "b": balls,
                "fours": int(b.get("foursScored") or 0),
                "sixes": int(b.get("sixesScored") or 0),
                "sr": round(runs / balls * 100, 2) if balls > 0 else 0,
                "out": dt if not dnb and not not_out else ("not out" if not_out else "did not bat"),
                "notOut": not_out,
                "didNotBat": dnb,
                "role": None,
                "pid": get_pid(pid),
            })
        return result

    def parse_bowling(bowling_rows: list) -> list:
        result = []
        for bw in bowling_rows:
            pid = bw.get("participantId") or ""
            first, last = get_name(pid)
            overs_raw = bw.get("oversBowled")
            overs = _overs_str(overs_raw)
            runs = int(bw.get("runsConceded") or 0)
            try:
                o_float = float(str(overs_raw or 0).replace(",", "."))
                whole = int(o_float)
                part = round((o_float - whole) * 10)
                o_float_real = whole + part / 6
            except (TypeError, ValueError):
                o_float_real = 0
            result.append({
                "first": first,
                "last": last,
                "short": short_display(pid, bw.get("playerShortName")),
                "o": overs,
                "m": int(bw.get("maidensBowled") or 0),
                "r": runs,
                "w": int(bw.get("wicketsTaken") or 0),
                "econ": round(runs / o_float_real, 2) if o_float_real > 0 else 0,
                "pid": get_pid(pid),
            })
        return result

    def parse_extras(inn: dict) -> dict:
        # GR top-level fields confirmed from games router (523-538)
        return {
            "total": inn.get("totalExtras") or 0,
            "b": inn.get("byesRuns") or 0,
            "lb": inn.get("legByesRuns") or 0,
            "nb": inn.get("noBalls") or 0,
            "wd": inn.get("wideBalls") or 0,
        }

    def team_totals(inn: dict, batting: list):
        # GR authoritative fields (confirmed from games router)
        rs_raw = inn.get("runsScored")
        total_runs = int(rs_raw) if rs_raw is not None else (
            sum(b["r"] for b in batting if not b["didNotBat"])
            + int(inn.get("totalExtras") or 0)
        )
        wkts_raw = inn.get("numberOfWicketsFallen")
        total_wkts = int(wkts_raw) if wkts_raw is not None else sum(
            1 for b in batting if not b["notOut"] and not b["didNotBat"]
        )
        # The innings' own total-overs field is "oversBowled" (confirmed live:
        # 39.3 / 39.0) — "totalOvers"/"overs" don't exist on this payload at
        # all, so this always fell back to "0". Same field the overs-allotment
        # guess below already reads correctly off each innings.
        overs_raw = inn.get("oversBowled")
        overs = _overs_str(overs_raw) if overs_raw is not None else "0"
        try:
            o_float = float(str(overs_raw or 0))
            whole = int(o_float)
            part = round((o_float - whole) * 10)
            o_real = whole + part / 6
        except (TypeError, ValueError):
            o_real = 0
        rr = round(total_runs / o_real, 2) if o_real > 0 else 0
        return str(total_runs), total_wkts, overs, str(rr)

    def build_team(team_raw: dict, inn: dict, default_color: str) -> dict:
        # inn = the innings THIS team batted — its own "batting" array is this
        # team's card; its "bowling" array records whoever bowled THAT
        # innings, i.e. the OPPONENT, which is exactly what a proper
        # scorebook nests directly below a team's batting: not their own
        # figures from the other innings, but the bowling that dismissed
        # them. (Previously each side's card carried its OWN bowling from the
        # innings it bowled, contradicting the "{OPPONENT} BOWLING" heading
        # the template already renders above it.)
        batting = parse_batting(inn.get("batting") or [])
        bowling = parse_bowling(inn.get("bowling") or [])
        name = (team_raw.get("displayName") or team_raw.get("name") or "TEAM").upper()
        short = "".join(w[0] for w in name.split()[:3])
        total, wickets, overs, rr = team_totals(inn, batting)
        logo_url = (team_raw.get("logoUrl") or team_raw.get("logo") or
                    team_raw.get("imageUrl") or team_raw.get("image") or None)
        return {
            "name": name,
            "short": short,
            "color": default_color,
            "logo": logo_url,
            "monogram": short,
            "total": total,
            "wickets": wickets,
            "overs": overs,
            "runRate": rr,
            "batting": batting,
            "bowling": bowling,
            "extras": parse_extras(inn),
        }

    home = build_team(home_team_raw, inn=home_inn, default_color="#1a4eb8")
    away = build_team(away_team_raw, inn=away_inn, default_color="#cc1f2c")

    # Each side's real club, so the post carries that club's own crest and
    # colour instead of the generic blue/red the two cards used to get
    # regardless of who was playing. Our own club wins where the match names
    # it — a club posting about its own game should be in its own colours.
    home_org = await _org_for_team(home_team_raw, home["name"], db, club)
    away_org = await _org_for_team(away_team_raw, away["name"], db, club)
    # Two sides can't both be us. If the name match claimed our club twice,
    # keep it for whichever side the owning-organisation id actually named.
    if club is not None and home_org is club and away_org is club:
        home_own = ((home_team_raw.get("owningOrganisation") or {}).get("id") or "")
        if str(home_own).lower() != str(club.id).lower():
            home_org = None
        else:
            away_org = None
    for side, org in ((home, home_org), (away, away_org)):
        if org is not None:
            side["color"] = _org_colour(org) or side["color"]
            # A crest the club uploaded to us beats whatever Grassroots has:
            # it's the one they chose, and it's served from our own domain
            # rather than a hotlink that can 404 mid-render.
            side["logo"] = _org_logo_url(org) or side.get("logo")

    # Result, venue, date and match type live at the TOP level of a /scores/*
    # match, not on matchSummary (which only carries `resultText` + `teams`) —
    # reading them off matchSummary alone silently produced a post with no
    # date, no venue and a bare "RESULT". The matchSummary lookups are kept
    # first so an upstream shape that does carry them still wins.
    result_text = (
        match_summary.get("result")
        or match_summary.get("resultText")
        or match_summary.get("statusText")
        or raw.get("resultText")
        or "RESULT"
    ).upper()
    venue = ((match_summary.get("venue") or raw.get("venue")) or {}).get("name") or ""
    date_raw = (
        match_summary.get("dateTimeUTC")
        or match_summary.get("startDateTime")
        or ((raw.get("matchSchedule") or [{}])[0] or {}).get("startDateTime")
        or ""
    )
    date_str = date_raw[:10] if date_raw else ""
    grade_obj = raw.get("grade") or match_summary.get("grade") or {}
    grade_name = (grade_obj.get("name") or "").upper()
    round_raw = match_summary.get("round") or raw.get("round") or ""
    if isinstance(round_raw, dict):
        round_name = round_raw.get("name") or round_raw.get("shortName") or ""
    else:
        round_name = str(round_raw)
    # "Round 7" needs the prefix; "Semi Finals" and "Grand Final" already read
    # as the round they are, so don't turn them into "ROUND Semi Finals".
    round_label = round_name.strip()
    if round_label and not re.search(r"[a-z]", round_label, re.I):
        round_label = f"ROUND {round_label}"
    match_type = (raw.get("matchType") or "").strip()
    # Nothing upstream states the allotment, so take the longest innings bowled
    # — right for any innings that went the distance, and a far better guess
    # than a flat 20 on a 50-over game. It stays editable on the form.
    bowled = [
        int(float(i.get("oversBowled") or 0))
        for i in innings_list
        if i.get("oversBowled")
    ]

    meta = {
        "competition": grade_name,
        "round": round_label or "ROUND",
        "format": (match_type or "T20").upper(),
        "overs": max(bowled) if bowled else 20,
        "venue": venue,
        "date": date_str,
        "toss": "",
        "result": result_text,
        "series": "",
        "motm": {"first": "", "last": "", "team": "", "line": ""},
    }

    return {"meta": meta, "home": home, "away": away}
