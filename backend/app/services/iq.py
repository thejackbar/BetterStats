"""BetterIQ — analytics + AI module (Best tier).

Phase 1 is **Opposition analysis**: scout an upcoming opponent from the data the
Core already holds. Everything here is a *read* over existing tables — no new
ingestion (per the BetterIQ spec). The build order across the module is
opposition → selection → player trends → NL Q&A; only opposition ships here.

Data reality (and why coverage is tiered)
------------------------------------------
We only store **our own club's** per-innings rows (``batting_innings`` etc. FK
to our ``players``). We do *not* store opposition batting cards — see the
``bowler_wickets`` model comment. So what we can say about an opponent depends
on what we hold:

* **Always** — head-to-head results vs us (``games.result`` / ``winning_team``)
  and *our* players' record against them (great selection context too).
* **Partial** — opponent batters our bowlers have dismissed, with the runs they
  made (``bowler_wickets.batter_name`` + ``batter_runs``). A "batters to watch"
  signal, not a full record (not-outs and un-dismissed knocks are invisible).
* **Rich** — only when the opponent club is *itself* a synced organisation we
  hold (multi-club, or a derby where both clubs synced): then we can show their
  real top run-scorers / wicket-takers from their own season stats.

The UI flags the coverage level rather than failing (spec: "flag coverage gaps
in the UI rather than failing").

Opponent identity follows the established ``opp_key`` pattern from
``aggregations.get_player_by_opposition``: ``COALESCE(opp_org_id,
opp_club_name)`` — a stable org UUID when sync populated it, else the club name.
Org-scoping of games goes through ``grades → seasons`` (the views don't carry
``organisation_id``), matching ``routers/records.py``.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import Organisation
from app.services import grassroots_scores_client
from app.services.club_match import club_match_keys


# The opponent key + display name for a game, from our club's perspective.
# Used in several queries below, so defined once.
_OPP_KEY = "COALESCE(g.opp_org_id, g.opp_club_name)"

# Standard org-scoping join for the effective games view (records.py pattern).
_ORG_SCOPE = (
    " JOIN grades gr ON gr.id = g.grade_id"
    " JOIN seasons s ON s.id = gr.season_id"
)


def _opp_scope(grade: str | None, season_ids: list[str] | None, params: dict) -> str:
    """Extra WHERE clauses to narrow an opponent query to a grade (by name, the
    BetterIQ filter convention — see ``iq_team._scope``) and/or a set of seasons.

    Mutates ``params`` with the bound values and returns SQL to append after the
    ``opp_key`` predicate. Empty inputs ⇒ no clause ⇒ all-time / all-grades, so
    the default report is byte-for-byte what it was before filtering existed."""
    clauses: list[str] = []
    if grade:
        params["grade"] = grade
        clauses.append("AND gr.name = :grade")
    if season_ids:
        keys = []
        for i, sid in enumerate(season_ids):
            k = f"season_{i}"
            params[k] = sid
            keys.append(f"CAST(:{k} AS UUID)")
        clauses.append(f"AND gr.season_id IN ({', '.join(keys)})")
    return " ".join(clauses)


async def _held_org_keys(session: AsyncSession) -> set[str]:
    """Org ids + playhq_ids of organisations we hold that have players.

    An opponent whose ``opp_key`` is in this set has been synced as its own
    club, so we can show its real roster ("rich" coverage).
    """
    res = await session.execute(
        text(
            """
            SELECT o.id::text AS id, o.playhq_id AS playhq_id
            FROM organisations o
            WHERE EXISTS (SELECT 1 FROM players pl WHERE pl.organisation_id = o.id)
            """
        )
    )
    keys: set[str] = set()
    for r in res.mappings():
        if r["id"]:
            keys.add(r["id"])
        if r["playhq_id"]:
            keys.add(r["playhq_id"])
    return keys


async def list_opponents(session: AsyncSession, org_id: str) -> dict:
    """Opponents we have history against + upcoming fixtures to scout.

    Returns ``{opponents: [...], upcoming: [...]}``. ``opponents`` is ordered by
    most-played; each carries a ``coverage`` flag ('rich' | 'limited'). Upcoming
    fixtures (from BetterSelect's ``fixtures`` table) get an ``opp_key`` resolved
    by name so the UI can link "scout this opponent" straight to a report.
    """
    res = await session.execute(
        text(
            f"""
            SELECT
                {_OPP_KEY} AS opp_key,
                -- Most-frequent club name for this opponent key (not MAX, which
                -- alphabetically prefers a rare association label like "West
                -- Australian Suburban Turf Cricket Assoc" over the real club).
                mode() WITHIN GROUP (ORDER BY g.opp_club_name) AS name,
                COUNT(*) AS meetings,
                MAX(g.played_at) AS last_played
            FROM v_effective_games g{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND g.opp_club_name IS NOT NULL AND g.opp_club_name <> ''
            GROUP BY {_OPP_KEY}
            ORDER BY COUNT(*) DESC, MAX(g.played_at) DESC NULLS LAST
            """
        ),
        {"org_id": org_id},
    )
    held = await _held_org_keys(session)
    opponents = []
    for r in res.mappings():
        opp_key = r["opp_key"]
        opponents.append(
            {
                "opp_key": opp_key,
                "name": r["name"],
                "meetings": r["meetings"],
                "last_played": r["last_played"].isoformat() if r["last_played"] else None,
                "coverage": "rich" if opp_key in held else "limited",
            }
        )

    # Synced *sibling* clubs (other organisations in this instance that share a
    # grade competition with us) are scoutable via the live dossier's grade scan
    # even with NO head-to-head rows — so a derby club we both sync, whose shared
    # game is owned by the other club, is still findable (#16). Surface them as
    # opponents keyed on their org id, de-duped against history by key and name.
    existing_keys = {o["opp_key"] for o in opponents}
    existing_names = {(o["name"] or "").strip().lower() for o in opponents}
    sib = await session.execute(
        text(
            """
            SELECT DISTINCT o.id::text AS opp_key, o.name AS name
            FROM organisations o
            WHERE o.id <> CAST(:org_id AS UUID)
              AND EXISTS (
                  SELECT 1 FROM grades g2
                  JOIN seasons s2 ON s2.id = g2.season_id AND s2.organisation_id = o.id
                  JOIN grades g1 ON g1.grassroots_id = g2.grassroots_id
                  JOIN seasons s1 ON s1.id = g1.season_id AND s1.organisation_id = CAST(:org_id AS UUID)
                  WHERE g2.grassroots_id IS NOT NULL
              )
            ORDER BY o.name
            """
        ),
        {"org_id": org_id},
    )
    for r in sib.mappings():
        nm = (r["name"] or "").strip().lower()
        if r["opp_key"] in existing_keys or (nm and nm in existing_names):
            continue
        opponents.append({
            "opp_key": r["opp_key"], "name": r["name"],
            "meetings": 0, "last_played": None,
            "coverage": "rich", "shared_grade": True,
        })
        existing_keys.add(r["opp_key"])
        if nm:
            existing_names.add(nm)

    # Name → opp_key lookup so upcoming fixtures can deep-link to a report.
    by_name = {(o["name"] or "").strip().lower(): o["opp_key"] for o in opponents}
    # Manual matches saved by the user take precedence / fill the gaps.
    for alias_nm, (akey, _dn) in (await _load_aliases(session, org_id)).items():
        by_name[alias_nm] = akey

    fx_res = await session.execute(
        text(
            """
            SELECT
                f.id::text AS id,
                f.opponent_name,
                f.played_on,
                f.home_away,
                f.venue,
                gr.name AS grade_name,
                t.name AS team_name
            FROM fixtures f
            LEFT JOIN grades gr ON gr.id = f.grade_id
            LEFT JOIN teams t ON t.id = f.team_id
            WHERE f.organisation_id = CAST(:org_id AS UUID)
              AND f.status = 'UPCOMING'
              AND (f.played_on IS NULL OR f.played_on >= CURRENT_DATE)
              AND f.opponent_name IS NOT NULL AND f.opponent_name <> ''
            ORDER BY f.played_on ASC NULLS LAST, f.start_time ASC NULLS LAST
            LIMIT 12
            """
        ),
        {"org_id": org_id},
    )
    upcoming = []
    for r in fx_res.mappings():
        nm = (r["opponent_name"] or "").strip().lower()
        upcoming.append(
            {
                "fixture_id": r["id"],
                "opponent_name": r["opponent_name"],
                "opp_key": by_name.get(nm),  # None when we have no history vs them
                "played_on": r["played_on"].isoformat() if r["played_on"] else None,
                "home_away": r["home_away"],
                "venue": r["venue"],
                "grade_name": r["grade_name"],
                "team_name": r["team_name"],
            }
        )

    return {"opponents": opponents, "upcoming": upcoming}


async def _load_aliases(session: AsyncSession, org_id: str) -> dict[str, tuple[str, str | None]]:
    """Manual fixture-opponent → club links saved by the user (opponent_aliases),
    keyed by the lowercased alias name → (opp_key, display_name). Defensive: if
    the table isn't there yet (migration not applied), behave as if empty."""
    try:
        res = await session.execute(
            text("SELECT alias_name, opp_key, display_name FROM opponent_aliases WHERE organisation_id = CAST(:org AS UUID)"),
            {"org": org_id},
        )
        return {r["alias_name"]: (r["opp_key"], r["display_name"]) for r in res.mappings()}
    except Exception:
        await session.rollback()
        return {}


async def save_opponent_alias(session: AsyncSession, org_id: str, opponent_name: str, opp_key: str, display_name: str | None) -> None:
    """Persist a manual opponent match so every fixture with this name (now and
    future) resolves to the chosen opp_key."""
    alias = (opponent_name or "").strip().lower()
    if not alias or not opp_key:
        return
    await session.execute(
        text(
            """
            INSERT INTO opponent_aliases (organisation_id, alias_name, opp_key, display_name)
            VALUES (CAST(:org AS UUID), :alias, :opp_key, :dn)
            ON CONFLICT (organisation_id, alias_name)
            DO UPDATE SET opp_key = EXCLUDED.opp_key, display_name = EXCLUDED.display_name, updated_at = NOW()
            """
        ),
        {"org": org_id, "alias": alias, "opp_key": opp_key, "dn": display_name},
    )
    await session.commit()


# ─── Opponent player scouting tags (manual colour/detail) ────────────────────
# Controlled vocab mirrors the Player attributes BetterSelect uses, so the
# opposition tag editor offers the same choices as our own players.
_TAG_BAT_HANDS = {"LEFT", "RIGHT"}
_TAG_BOWL_ACTIONS = {"RIGHT_ARM", "LEFT_ARM"}
_TAG_BOWL_TYPES = {"FAST", "FAST_MEDIUM", "MEDIUM", "MEDIUM_FAST", "FINGER_SPIN", "WRIST_SPIN"}
_TAG_ROLES = {"BAT", "BOWL", "ALL", "WK"}


async def get_opponent_tags(session: AsyncSession, org_id: str) -> dict[str, dict]:
    """All of an org's opponent scouting tags, keyed by participant_id (the
    dossier's player_id). Defensive: empty if the table isn't migrated yet."""
    try:
        res = await session.execute(
            text(
                """
                SELECT participant_id, player_name, batting_hand, bowling_action, bowling_type,
                       player_role, is_wicket_keeper, is_danger, notes, scoring_zones
                FROM opponent_player_tags WHERE organisation_id = CAST(:org AS UUID)
                """
            ),
            {"org": org_id},
        )
        return {r["participant_id"]: dict(r) for r in res.mappings()}
    except Exception:
        await session.rollback()
        return {}


async def upsert_opponent_tag(session: AsyncSession, org_id: str, participant_id: str, fields: dict, user_id: str | None = None) -> dict:
    """Create/update one opponent player's scouting tag. Controlled-vocab fields
    are validated (an unknown value clears to NULL rather than erroring); name and
    notes are free text. Returns the stored tag."""
    pid = (participant_id or "").strip()
    if not pid:
        return {}

    def _choice(v, allowed):
        v = (v or "").strip().upper() or None
        return v if (v is None or v in allowed) else None

    def _flag(v):
        return bool(v) if v is not None else None

    def _zones(v):
        # Scout-entered wagon-wheel: up to 8 non-negative numbers (% of runs by
        # area). Anything else clears the field. Returns a JSON string or None.
        if not isinstance(v, (list, tuple)):
            return None
        out = []
        for x in v[:8]:
            try:
                out.append(max(0, round(float(x), 1)))
            except (TypeError, ValueError):
                out.append(0)
        return json.dumps(out) if any(out) else None

    payload = {
        "player_name": (fields.get("player_name") or "").strip() or None,
        "batting_hand": _choice(fields.get("batting_hand"), _TAG_BAT_HANDS),
        "bowling_action": _choice(fields.get("bowling_action"), _TAG_BOWL_ACTIONS),
        "bowling_type": _choice(fields.get("bowling_type"), _TAG_BOWL_TYPES),
        "player_role": _choice(fields.get("player_role"), _TAG_ROLES),
        "is_wicket_keeper": _flag(fields.get("is_wicket_keeper")),
        "is_danger": _flag(fields.get("is_danger")),
        "notes": (fields.get("notes") or "").strip() or None,
    }
    zones = _zones(fields.get("scoring_zones"))
    await session.execute(
        text(
            """
            INSERT INTO opponent_player_tags
                (organisation_id, participant_id, player_name, batting_hand, bowling_action,
                 bowling_type, player_role, is_wicket_keeper, is_danger, notes, scoring_zones, updated_by)
            VALUES (CAST(:org AS UUID), :pid, :player_name, :batting_hand, :bowling_action,
                    :bowling_type, :player_role, :is_wicket_keeper, :is_danger, :notes,
                    CAST(:scoring_zones AS JSONB), CAST(:uid AS UUID))
            ON CONFLICT (organisation_id, participant_id) DO UPDATE SET
                player_name = COALESCE(EXCLUDED.player_name, opponent_player_tags.player_name),
                batting_hand = EXCLUDED.batting_hand,
                bowling_action = EXCLUDED.bowling_action,
                bowling_type = EXCLUDED.bowling_type,
                player_role = EXCLUDED.player_role,
                is_wicket_keeper = EXCLUDED.is_wicket_keeper,
                is_danger = EXCLUDED.is_danger,
                notes = EXCLUDED.notes,
                scoring_zones = COALESCE(EXCLUDED.scoring_zones, opponent_player_tags.scoring_zones),
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            """
        ),
        {"org": org_id, "pid": pid, "uid": user_id, "scoring_zones": zones, **payload},
    )
    await session.commit()
    out = {"participant_id": pid, **payload}
    out["scoring_zones"] = json.loads(zones) if zones else None
    return out


async def _resolve_opp_key(session: AsyncSession, org_id: str, *, opponent: str | None, fixture_id: str | None) -> tuple[str | None, str | None]:
    """Resolve a request into (opp_key, display_name).

    Accepts an explicit ``opponent`` (already an opp_key) and/or a ``fixture_id``
    whose opponent name we look up against our game history. An explicit
    ``opponent`` **takes precedence** — the "match this opponent" UI passes both a
    chosen opp_key and the fixture, and we want identity from the chosen club
    (the fixture is only used for its grade, resolved separately). Returns
    ``(None, name)`` when a fixture names an opponent we've never played (so the
    caller can show an honest "no history" report).
    """
    if opponent:
        # Confirm the opp_key exists in our history and fetch its display name.
        nm_res = await session.execute(
            text(
                f"""
                SELECT mode() WITHIN GROUP (ORDER BY g.opp_club_name) AS name
                FROM v_effective_games g{_ORG_SCOPE}
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND {_OPP_KEY} = :opp_key
                """
            ),
            {"org_id": org_id, "opp_key": opponent},
        )
        nrow = nm_res.mappings().first()
        name = nrow["name"] if nrow else None
        if not name:
            # A synced sibling club (opp_key = their org id) with no head-to-head
            # has no game name to read — use the organisation's own name so the
            # scout shows "Applecross", not a UUID (#16).
            try:
                uuid.UUID(opponent)
                orow = (await session.execute(
                    text("SELECT name FROM organisations WHERE id = CAST(:id AS UUID)"),
                    {"id": opponent},
                )).first()
                if orow:
                    name = orow[0]
            except (ValueError, TypeError):
                pass
        return opponent, name or opponent

    if fixture_id:
        fx = await session.execute(
            text(
                "SELECT opponent_name FROM fixtures"
                " WHERE id = CAST(:fid AS UUID) AND organisation_id = CAST(:org_id AS UUID)"
            ),
            {"fid": fixture_id, "org_id": org_id},
        )
        row = fx.mappings().first()
        name = (row["opponent_name"] if row else None) or None
        if not name:
            return None, None
        # A manual match saved by the user wins over name-matching history.
        hit = (await _load_aliases(session, org_id)).get(name.strip().lower())
        if hit:
            return hit[0], hit[1] or name
        # Map the fixture's opponent name onto a stable opp_key from history.
        key_res = await session.execute(
            text(
                f"""
                SELECT {_OPP_KEY} AS opp_key, MAX(g.opp_club_name) AS name
                FROM v_effective_games g{_ORG_SCOPE}
                WHERE s.organisation_id = CAST(:org_id AS UUID)
                  AND LOWER(g.opp_club_name) = LOWER(:name)
                GROUP BY {_OPP_KEY}
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            ),
            {"org_id": org_id, "name": name},
        )
        krow = key_res.mappings().first()
        if krow:
            # Keep the stable identity (opp_key) but display the club the user
            # actually picked from the fixture, not MAX(opp_club_name) for the
            # key (which can be a shared association label).
            return krow["opp_key"], name
        return None, name  # named opponent, but no history held

    return None, None


async def resolve_opponent(
    session: AsyncSession,
    org_id: str,
    *,
    opponent: str | None = None,
    fixture_id: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Public resolver → (opp_key, display_name, grade_id).

    Wraps ``_resolve_opp_key`` and additionally surfaces the fixture's grade_id
    (so the live dossier knows which league-wide grade to scout for current
    form). grade_id is None when resolving from an explicit opponent key.
    """
    opp_key, name = await _resolve_opp_key(session, org_id, opponent=opponent, fixture_id=fixture_id)
    grade_id = None
    if fixture_id:
        res = await session.execute(
            text(
                "SELECT grade_id::text AS gid FROM fixtures"
                " WHERE id = CAST(:fid AS UUID) AND organisation_id = CAST(:org AS UUID)"
            ),
            {"fid": fixture_id, "org": org_id},
        )
        row = res.mappings().first()
        grade_id = row["gid"] if row else None
    return opp_key, name, grade_id


async def _head_to_head(
    session: AsyncSession, org_id: str, opp_key: str,
    *, grade: str | None = None, season_ids: list[str] | None = None,
) -> dict:
    """Our overall record vs an opponent + home/away split + recent meetings.

    ``our_venue`` is derived from the known opponent name against the game's
    home/away club — no need to know our own (multi-team) names. Manual games
    have NULL home/away club, so their venue reads as unknown.

    ``grade``/``season_ids`` optionally scope the record to one grade (by name)
    and/or a set of seasons (the card's All-time/Season/Grade toggle).
    """
    params = {"org_id": org_id, "opp_key": opp_key}
    scope = _opp_scope(grade, season_ids, params)
    summary = await session.execute(
        text(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE g.result IS NOT NULL) AS decided,
                COUNT(*) AS meetings,
                COUNT(*) FILTER (WHERE g.result = 'WIN') AS wins,
                COUNT(*) FILTER (WHERE g.result = 'LOSS') AS losses,
                COUNT(*) FILTER (WHERE g.result = 'DRAW') AS draws,
                COUNT(*) FILTER (WHERE g.result = 'TIE') AS ties,
                COUNT(*) FILTER (WHERE g.result = 'WIN' AND g.away_club = g.opp_club_name) AS home_wins,
                COUNT(*) FILTER (WHERE g.result IS NOT NULL AND g.away_club = g.opp_club_name) AS home_decided,
                COUNT(*) FILTER (WHERE g.result = 'WIN' AND g.home_club = g.opp_club_name) AS away_wins,
                COUNT(*) FILTER (WHERE g.result IS NOT NULL AND g.home_club = g.opp_club_name) AS away_decided
            FROM v_effective_games g{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              {scope}
            """
        ),
        params,
    )
    s = summary.mappings().first() or {}
    wins, losses = (s.get("wins") or 0), (s.get("losses") or 0)
    decided = s.get("decided") or 0

    recent_res = await session.execute(
        text(
            f"""
            SELECT
                g.played_at,
                g.result,
                g.winning_team,
                g.venue,
                gr.name AS grade_name,
                CASE
                    WHEN g.away_club = g.opp_club_name THEN 'HOME'
                    WHEN g.home_club = g.opp_club_name THEN 'AWAY'
                    ELSE NULL
                END AS our_venue
            FROM v_effective_games g{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND g.played_at IS NOT NULL
              {scope}
            ORDER BY g.played_at DESC
            LIMIT 12
            """
        ),
        params,
    )
    recent = [
        {
            "played_at": r["played_at"].isoformat() if r["played_at"] else None,
            "result": r["result"],
            "winning_team": r["winning_team"],
            "venue": r["venue"],
            "grade_name": r["grade_name"],
            "our_venue": r["our_venue"],
        }
        for r in recent_res.mappings()
    ]

    # "Recent form" = our last-5 decided results vs them, newest first (W/L/D).
    form = [r["result"][0] for r in recent if r["result"]][:5]

    return {
        "meetings": s.get("meetings") or 0,
        "decided": decided,
        "wins": wins,
        "losses": losses,
        "draws": s.get("draws") or 0,
        "ties": s.get("ties") or 0,
        "win_pct": round(100.0 * wins / (wins + losses), 1) if (wins + losses) else None,
        "home": {"played": s.get("home_decided") or 0, "wins": s.get("home_wins") or 0},
        "away": {"played": s.get("away_decided") or 0, "wins": s.get("away_wins") or 0},
        "recent": recent,
        "recent_form": form,
    }


async def _our_performers_vs(
    session: AsyncSession, org_id: str, opp_key: str,
    *, grade: str | None = None, season_ids: list[str] | None = None,
) -> dict:
    """Our players' batting + bowling record against this opponent.

    Doubles as selection intel — who in our squad has historically enjoyed this
    match-up. Restricted to currently-active players so retired names don't crowd
    the list, ordered by output. ``grade``/``season_ids`` scope it to match the
    record card's filter.
    """
    params = {"org_id": org_id, "opp_key": opp_key}
    scope = _opp_scope(grade, season_ids, params)
    batting = await session.execute(
        text(
            f"""
            SELECT
                p.id::text AS id,
                COALESCE(p.display_name_override, p.name) AS name,
                p.status AS status,
                COUNT(*) FILTER (WHERE bi.did_not_bat IS NOT TRUE AND bi.runs IS NOT NULL) AS innings,
                COALESCE(SUM(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0) AS runs,
                MAX(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE) AS high_score,
                COUNT(*) FILTER (
                    WHERE bi.did_not_bat IS NOT TRUE AND NOT bi.not_out AND bi.dismissal_type IS NOT NULL
                ) AS dismissals
            FROM v_effective_batting_innings bi
            JOIN v_effective_games g ON g.id = bi.game_id{_ORG_SCOPE}
            JOIN players p ON p.id = bi.player_id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND p.status = 'active'
              {scope}
            GROUP BY p.id, p.display_name_override, p.name, p.status
            HAVING COALESCE(SUM(bi.runs) FILTER (WHERE bi.did_not_bat IS NOT TRUE), 0) > 0
            ORDER BY runs DESC
            LIMIT 10
            """
        ),
        params,
    )
    top_batting = []
    for r in batting.mappings():
        dis = r["dismissals"] or 0
        runs = r["runs"] or 0
        top_batting.append(
            {
                "player_id": r["id"],
                "name": r["name"],
                "active": r["status"] == "active",
                "innings": r["innings"] or 0,
                "runs": runs,
                "high_score": r["high_score"],
                "average": round(runs / dis, 2) if dis else None,
            }
        )

    bowling = await session.execute(
        text(
            f"""
            SELECT
                p.id::text AS id,
                COALESCE(p.display_name_override, p.name) AS name,
                p.status AS status,
                COALESCE(SUM(bs.wickets), 0) AS wickets,
                COALESCE(SUM(bs.runs), 0) AS runs,
                COALESCE(SUM(FLOOR(bs.overs) * 6 + ROUND((bs.overs - FLOOR(bs.overs)) * 10)), 0) AS balls,
                MAX(bs.wickets) AS best_wkts
            FROM v_effective_bowling_spells bs
            JOIN v_effective_games g ON g.id = bs.game_id{_ORG_SCOPE}
            JOIN players p ON p.id = bs.player_id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND p.status = 'active'
              {scope}
            GROUP BY p.id, p.display_name_override, p.name, p.status
            HAVING COALESCE(SUM(bs.wickets), 0) > 0
            ORDER BY wickets DESC, runs ASC
            LIMIT 10
            """
        ),
        params,
    )
    top_bowling = []
    for r in bowling.mappings():
        wkts = r["wickets"] or 0
        runs = r["runs"] or 0
        balls = float(r["balls"] or 0)
        top_bowling.append(
            {
                "player_id": r["id"],
                "name": r["name"],
                "active": r["status"] == "active",
                "wickets": wkts,
                "runs": runs,
                "average": round(runs / wkts, 2) if wkts else None,
                "economy": round(runs / (balls / 6), 2) if balls else None,
                "best_wickets": r["best_wkts"],
            }
        )

    return {"batting": top_batting, "bowling": top_bowling}


async def _their_danger_batters(
    session: AsyncSession, org_id: str, opp_key: str,
    *, grade: str | None = None, season_ids: list[str] | None = None,
) -> list[dict]:
    """Opponent batters our bowlers have dismissed, with the runs they made.

    A *partial* signal (only dismissals BY us; not-outs and knocks we didn't end
    are invisible — we don't store opposition batting). Surfaced as "batters to
    watch", ordered by runs scored against us. Only synced games carry
    ``bowler_wickets`` (manual games have none), which is fine.
    """
    params = {"org_id": org_id, "opp_key": opp_key}
    scope = _opp_scope(grade, season_ids, params)
    res = await session.execute(
        text(
            f"""
            SELECT
                bw.batter_name AS name,
                COUNT(*) AS times_out,
                COALESCE(SUM(bw.batter_runs), 0) AS runs,
                MAX(bw.batter_runs) AS top_score
            FROM bowler_wickets bw
            JOIN v_effective_games g ON g.id = bw.game_id{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND bw.batter_name IS NOT NULL AND bw.batter_name <> ''
              {scope}
            GROUP BY bw.batter_name
            HAVING COALESCE(SUM(bw.batter_runs), 0) > 0
            ORDER BY runs DESC, times_out DESC
            LIMIT 15
            """
        ),
        params,
    )
    out = []
    for r in res.mappings():
        times_out = r["times_out"] or 0
        runs = r["runs"] or 0
        out.append({
            "name": r["name"],
            "times_out": times_out,
            "runs": runs,
            # Runs per time we've dismissed them — a partial "average vs us" (we
            # only see knocks our bowlers ended), but enough for the danger read
            # the preview/scout render (they read `average`).
            "average": round(runs / times_out, 2) if times_out else None,
            "top_score": r["top_score"],
        })
    return out


async def search_opponent_players(session: AsyncSession, org_id: str, q: str) -> list[dict]:
    """Search opposition batters we've faced (by name) across ALL opponents, so a
    scout can jump straight to a player without first picking the club.

    Sourced from ``bowler_wickets.batter_name`` — the only opponent-player data we
    hold without building a live dossier. Each hit carries the club (opp_key +
    name) so the UI can open that club's dossier and pre-select the player.
    """
    q = (q or "").strip()
    if len(q) < 2:
        return []
    res = await session.execute(
        text(
            f"""
            SELECT bw.batter_name AS name,
                   {_OPP_KEY} AS opp_key,
                   mode() WITHIN GROUP (ORDER BY g.opp_club_name) AS club_name,
                   COUNT(*) AS times_out,
                   COALESCE(SUM(bw.batter_runs), 0) AS runs,
                   MAX(bw.batter_runs) AS top_score,
                   MAX(g.played_at) AS last_played
            FROM bowler_wickets bw
            JOIN v_effective_games g ON g.id = bw.game_id{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND bw.batter_name ILIKE :q
              AND {_OPP_KEY} IS NOT NULL
            GROUP BY bw.batter_name, {_OPP_KEY}
            ORDER BY runs DESC, times_out DESC
            LIMIT 30
            """
        ),
        {"org_id": org_id, "q": f"%{q}%"},
    )
    return [
        {
            "name": r["name"],
            "opp_key": r["opp_key"],
            "club_name": r["club_name"],
            "times_out": r["times_out"],
            "runs": r["runs"],
            "top_score": r["top_score"],
            "average": round((r["runs"] or 0) / r["times_out"], 2) if r["times_out"] else None,
            "last_played": r["last_played"].isoformat() if r["last_played"] else None,
        }
        for r in res.mappings()
    ]


async def _venues_vs(
    session: AsyncSession, org_id: str, opp_key: str,
    *, grade: str | None = None, season_ids: list[str] | None = None,
) -> list[dict]:
    """Our win/loss record at each venue against this opponent."""
    params = {"org_id": org_id, "opp_key": opp_key}
    scope = _opp_scope(grade, season_ids, params)
    res = await session.execute(
        text(
            f"""
            SELECT g.venue,
                   COUNT(*) FILTER (WHERE g.result IS NOT NULL) AS played,
                   COUNT(*) FILTER (WHERE g.result = 'WIN') AS wins,
                   COUNT(*) FILTER (WHERE g.result = 'LOSS') AS losses
            FROM v_effective_games g{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND g.venue IS NOT NULL AND g.venue <> ''
              {scope}
            GROUP BY g.venue
            HAVING COUNT(*) FILTER (WHERE g.result IS NOT NULL) >= 2
            ORDER BY played DESC
            LIMIT 8
            """
        ),
        params,
    )
    return [
        {"venue": r["venue"], "played": r["played"], "wins": r["wins"], "losses": r["losses"]}
        for r in res.mappings()
    ]


async def _our_bowler_dominance(
    session: AsyncSession, org_id: str, opp_key: str,
    *, grade: str | None = None, season_ids: list[str] | None = None,
) -> list[dict]:
    """Our bowler → their batter match-ups: who we've dismissed repeatedly.

    Selection gold — "Smith has Jones' number" — read straight from
    ``bowler_wickets`` (``bowler_id`` is our player; ``batter_name`` the opponent).
    Only pairings we've ended 2+ times, ordered by count then runs they made off us.
    A *partial* signal like ``their_danger_batters`` (knocks we didn't end are
    invisible), but the repeat-dismissal pattern is exactly the matchup intel asked
    for. Only synced games carry ``bowler_wickets`` (manual games have none).
    """
    params = {"org_id": org_id, "opp_key": opp_key}
    scope = _opp_scope(grade, season_ids, params)
    res = await session.execute(
        text(
            f"""
            SELECT
                p.id::text AS bowler_id,
                COALESCE(p.display_name_override, p.name) AS bowler,
                p.status AS status,
                bw.batter_name AS batter,
                COUNT(*) AS dismissals,
                COALESCE(SUM(bw.batter_runs), 0) AS runs_made,
                MAX(bw.batter_runs) AS top_score,
                ARRAY_AGG(DISTINCT CASE
                    WHEN bw.dismissal_type = 'caught' AND bw.caught_behind IS TRUE
                        THEN 'caught behind'
                    ELSE LOWER(bw.dismissal_type) END) AS how
            FROM bowler_wickets bw
            JOIN v_effective_games g ON g.id = bw.game_id{_ORG_SCOPE}
            JOIN players p ON p.id = bw.bowler_id
            WHERE s.organisation_id = CAST(:org_id AS UUID)
              AND {_OPP_KEY} = :opp_key
              AND bw.batter_name IS NOT NULL AND bw.batter_name <> ''
              {scope}
            GROUP BY p.id, bowler, p.status, bw.batter_name
            HAVING COUNT(*) >= 2
            ORDER BY COUNT(*) DESC, runs_made ASC, bowler ASC
            LIMIT 20
            """
        ),
        params,
    )
    out = []
    for r in res.mappings():
        out.append(
            {
                "bowler_id": r["bowler_id"],
                "bowler": r["bowler"],
                "active": r["status"] == "active",
                "batter": r["batter"],
                "dismissals": r["dismissals"],
                "runs_made": r["runs_made"],
                "top_score": r["top_score"],
                "how": [h for h in (r["how"] or []) if h],
            }
        )
    return out


async def _last_meeting(
    session: AsyncSession, org_id: str, opp_key: str,
    *, grade: str | None = None, season_ids: list[str] | None = None,
) -> dict | None:
    """Opposition memory (brief §16.10) — what happened last time we played them:
    our score, their score, our top performers, from the most recent meeting."""
    params = {"org_id": org_id, "opp_key": opp_key}
    scope = _opp_scope(grade, season_ids, params)
    g = await session.execute(
        text(
            f"""
            SELECT g.id::text AS id, g.played_at, g.result, g.winning_team, g.venue, gr.name AS grade
            FROM v_effective_games g{_ORG_SCOPE}
            WHERE s.organisation_id = CAST(:org_id AS UUID) AND {_OPP_KEY} = :opp_key
              AND g.played_at IS NOT NULL
              {scope}
            ORDER BY g.played_at DESC LIMIT 1
            """
        ),
        params,
    )
    row = g.mappings().first()
    if not row:
        return None
    gid = row["id"]
    our_runs = (await session.execute(
        text("SELECT COALESCE(SUM(runs), 0) FROM v_effective_batting_innings WHERE game_id = CAST(:gid AS UUID)"),
        {"gid": gid},
    )).scalar() or 0
    opp_runs = (await session.execute(
        text("SELECT COALESCE(SUM(runs), 0) FROM v_effective_bowling_spells WHERE game_id = CAST(:gid AS UUID)"),
        {"gid": gid},
    )).scalar() or 0
    tb = (await session.execute(
        text(
            "SELECT COALESCE(p.display_name_override, p.name) AS name, bi.runs"
            " FROM v_effective_batting_innings bi JOIN players p ON p.id = bi.player_id"
            " WHERE bi.game_id = CAST(:gid AS UUID) AND bi.runs IS NOT NULL"
            " ORDER BY bi.runs DESC LIMIT 1"
        ),
        {"gid": gid},
    )).mappings().first()
    tw = (await session.execute(
        text(
            "SELECT COALESCE(p.display_name_override, p.name) AS name, bs.wickets, bs.runs"
            " FROM v_effective_bowling_spells bs JOIN players p ON p.id = bs.player_id"
            " WHERE bs.game_id = CAST(:gid AS UUID) AND bs.wickets IS NOT NULL"
            " ORDER BY bs.wickets DESC, bs.runs ASC LIMIT 1"
        ),
        {"gid": gid},
    )).mappings().first()
    return {
        "played_at": row["played_at"].isoformat() if row["played_at"] else None,
        "result": row["result"], "winning_team": row["winning_team"],
        "venue": row["venue"], "grade": row["grade"],
        "our_runs": our_runs, "opp_runs": opp_runs,
        "our_top_bat": {"name": tb["name"], "runs": tb["runs"]} if tb else None,
        "our_top_bowl": {"name": tw["name"], "wickets": tw["wickets"], "runs": tw["runs"]} if tw else None,
    }


async def _their_key_players(session: AsyncSession, opp_org_uuid: str) -> dict:
    """Rich coverage: the opponent's own top run-scorers / wicket-takers.

    Only reachable when the opponent is itself a synced organisation. Aggregates
    their season stats across all seasons.
    """
    batting = await session.execute(
        text(
            """
            SELECT
                COALESCE(p.display_name_override, p.name) AS name,
                COALESCE(SUM(pss.runs), 0) AS runs,
                COALESCE(SUM(pss.batting_innings), 0) AS innings,
                MAX(pss.high_score) AS high_score,
                COALESCE(SUM(pss.hundreds), 0) AS hundreds
            FROM players p
            JOIN player_season_stats pss ON pss.player_id = p.id
                -- Only count seasons belonging to this org. A CA participant
                -- GUID is shared across clubs, so a dual-club player can carry
                -- season rows from another club; counting them would over-state
                -- the opponent's totals (see migration 060).
                AND EXISTS (
                    SELECT 1 FROM seasons s
                    WHERE s.id = pss.season_id
                      AND s.organisation_id = CAST(:oid AS UUID)
                )
            WHERE p.organisation_id = CAST(:oid AS UUID)
            GROUP BY p.id, name
            HAVING COALESCE(SUM(pss.runs), 0) > 0
            ORDER BY runs DESC
            LIMIT 8
            """
        ),
        {"oid": opp_org_uuid},
    )
    bowling = await session.execute(
        text(
            """
            SELECT
                COALESCE(p.display_name_override, p.name) AS name,
                COALESCE(SUM(pss.wickets), 0) AS wickets,
                COALESCE(SUM(pss.runs_conceded), 0) AS runs,
                COALESCE(SUM(pss.bowling_balls), 0) AS balls,
                COALESCE(SUM(pss.five_wicket_innings), 0) AS five_fors
            FROM players p
            JOIN player_season_stats pss ON pss.player_id = p.id
                -- Only count seasons belonging to this org. A CA participant
                -- GUID is shared across clubs, so a dual-club player can carry
                -- season rows from another club; counting them would over-state
                -- the opponent's totals (see migration 060).
                AND EXISTS (
                    SELECT 1 FROM seasons s
                    WHERE s.id = pss.season_id
                      AND s.organisation_id = CAST(:oid AS UUID)
                )
            WHERE p.organisation_id = CAST(:oid AS UUID)
            GROUP BY p.id, name
            HAVING COALESCE(SUM(pss.wickets), 0) > 0
            ORDER BY wickets DESC
            LIMIT 8
            """
        ),
        {"oid": opp_org_uuid},
    )
    top_batting = []
    for r in batting.mappings():
        top_batting.append(
            {
                "name": r["name"],
                "runs": r["runs"],
                "innings": r["innings"],
                "high_score": r["high_score"],
                "hundreds": r["hundreds"],
            }
        )
    top_bowling = []
    for r in bowling.mappings():
        wkts = r["wickets"] or 0
        runs = r["runs"] or 0
        balls = r["balls"] or 0
        top_bowling.append(
            {
                "name": r["name"],
                "wickets": wkts,
                "average": round(runs / wkts, 2) if wkts else None,
                "economy": round(6.0 * runs / balls, 2) if balls else None,
                "five_fors": r["five_fors"],
            }
        )
    return {"batting": top_batting, "bowling": top_bowling}


# ─── Opponent ladder standing (live, current-season) ─────────────────────────
# Words to strip from a club name before token-matching it against a ladder row,
# so "Bassendean Cricket Club" matches on "bassendean", not "cricket"/"club".
_LADDER_STOP = {"cricket", "club", "cc", "the", "inc", "junior", "juniors", "seniors", "grade"}


def _ladder_rows(raw) -> tuple[list[dict], str | None]:
    """Pull the Overall ladder's rows from CA's fixturesladders payload (the
    documented shape; see routers/ladders.py). Returns (rows, view_name)."""
    if not isinstance(raw, dict):
        return [], None
    ladders = raw.get("ladders") or []
    if not ladders:
        return [], None
    ladder = next(
        (l for l in ladders if isinstance(l, dict) and (l.get("name") or "").strip().lower() in ("overall", "ladder")),
        None,
    ) or ladders[0]
    rows = []
    for pool in (ladder.get("pools") or []):
        for t in (pool.get("teams") or []):
            if not isinstance(t, dict):
                continue
            stats = {d.get("id"): d.get("val") for d in (t.get("ladderData") or []) if isinstance(d, dict)}
            rows.append({
                "rank": t.get("rank"),
                "team_name": t.get("displayName") or "—",
                "org": t.get("owningOrganisation") or {},
                "played": stats.get("played"),
                "won": stats.get("won"),
                "lost": stats.get("lost"),
                "points": stats.get("competitionPoints"),
            })
    rows.sort(key=lambda r: (r["rank"] is None, r["rank"] if r["rank"] is not None else 9999))
    return rows, (ladder.get("name") or "Ladder")


async def opponent_ladder(session: AsyncSession, org_id: str, *, opponent: str | None = None, fixture_id: str | None = None) -> dict:
    """Current ladder standing for an upcoming opponent — fetched live from CA's
    fixturesladders for the fixture's grade. Returns our row and the opponent's
    row so a preview can frame the matchup ("you're 2nd, they're 5th"). Needs a
    fixture (for the grade). Standings are *current*, so this is upcoming-opponent
    context, not a historical 'vs top-4' split (that needs ladder snapshots we
    don't keep)."""
    opp_key, name, grade_id = await resolve_opponent(session, org_id, opponent=opponent, fixture_id=fixture_id)
    base = {"opponent": {"opp_key": opp_key, "name": name}, "grade_id": grade_id}
    if not grade_id:
        return {**base, "available": False, "note": "Pick an upcoming fixture to see its grade ladder."}
    # grade_id is our DB grade PK (a per-club uuid5 for a shared grade); the CA
    # ladder API is keyed on the raw grade GUID (grassroots_id == id for legacy).
    grade_gr = (await session.execute(
        text("SELECT grassroots_id FROM grades WHERE id = CAST(:gid AS UUID)"),
        {"gid": grade_id},
    )).scalar_one_or_none()
    raw = await grassroots_scores_client.get_grade_ladder(grade_gr or grade_id)
    rows, view = _ladder_rows(raw)
    if not rows:
        return {**base, "available": False, "note": "No ladder published for this grade yet."}

    org = await session.get(Organisation, uuid.UUID(org_id))
    club_keys = club_match_keys(org) if org else []

    def _hay(r):
        return " ".join(str(x).lower() for x in [r["team_name"], r["org"].get("name"), r["org"].get("shortName")] if x)
    for r in rows:
        r["is_club"] = any(k and k in _hay(r) for k in club_keys)

    our_row = next((r for r in rows if r["is_club"]), None)
    nm = (name or "").strip().lower()
    core = [t for t in nm.replace("-", " ").split() if len(t) > 2 and t not in _LADDER_STOP]
    # Pick the BEST-matching opponent row (most name tokens in common), not the
    # first row to share any single token — otherwise "Wembley Districts" could
    # latch onto "Wembley Downs". A full-name substring match wins outright.
    opp_row, best = None, 0
    for r in rows:
        if r["is_club"]:
            continue
        h = _hay(r)
        score = 100 if (nm and nm in h) else sum(1 for t in core if t in h)
        if score > best:
            best, opp_row = score, r

    grr = (await session.execute(
        text("SELECT name FROM grades WHERE id = CAST(:g AS UUID)"), {"g": grade_id}
    )).mappings().first()

    def _clean(r):
        if not r:
            return None
        return {"rank": r["rank"], "team_name": r["team_name"], "played": r["played"],
                "won": r["won"], "lost": r["lost"], "points": r["points"]}

    return {
        **base,
        "available": True,
        "grade_name": grr["name"] if grr else None,
        "view": view,
        "teams": len(rows),
        "our_row": _clean(our_row),
        "opponent_row": _clean(opp_row),
    }


async def opposition_report(
    session: AsyncSession,
    org_id: str,
    *,
    opponent: str | None = None,
    fixture_id: str | None = None,
    grade: str | None = None,
    season_ids: list[str] | None = None,
) -> dict:
    """Assemble the full opposition scouting report for one opponent.

    Coverage tiers (see module docstring) are reflected in the ``coverage`` block
    so the UI can be honest about what's known. ``grade`` (a grade name) and
    ``season_ids`` optionally scope the head-to-head record, our record vs them,
    venues, last meeting and bowler match-ups — the record card's
    All-time/Season/Grade toggle. Both empty ⇒ all-time/all-grades.
    """
    opp_key, name = await _resolve_opp_key(session, org_id, opponent=opponent, fixture_id=fixture_id)

    if not opp_key:
        # A named-but-unplayed opponent (e.g. from a fixture) — honest empty state.
        return {
            "opponent": {"opp_key": None, "name": name},
            "coverage": {
                "level": "none",
                "note": (
                    f"No history held against {name}." if name else "Opponent not found."
                )
                + " Head-to-head and player records appear once you've played them"
                " (or once their club is synced).",
            },
            "head_to_head": None,
            "our_performers": None,
            "their_danger_batters": [],
            "their_key_players": None,
            "venues": [],
            "matchups": {"bowler_dominance": []},
            "last_meeting": None,
        }

    head_to_head = await _head_to_head(session, org_id, opp_key, grade=grade, season_ids=season_ids)
    our_performers = await _our_performers_vs(session, org_id, opp_key, grade=grade, season_ids=season_ids)
    danger = await _their_danger_batters(session, org_id, opp_key, grade=grade, season_ids=season_ids)
    venues = await _venues_vs(session, org_id, opp_key, grade=grade, season_ids=season_ids)
    bowler_dominance = await _our_bowler_dominance(session, org_id, opp_key, grade=grade, season_ids=season_ids)
    last_meeting = await _last_meeting(session, org_id, opp_key, grade=grade, season_ids=season_ids)

    # Rich coverage only if the opponent is itself a synced org we hold.
    held = await _held_org_keys(session)
    their_key_players = None
    coverage_level = "limited"
    if opp_key in held:
        org_row = await session.execute(
            text(
                "SELECT id::text AS id FROM organisations"
                " WHERE id::text = :k OR playhq_id = :k LIMIT 1"
            ),
            {"k": opp_key},
        )
        orow = org_row.mappings().first()
        if orow:
            their_key_players = await _their_key_players(session, orow["id"])
            coverage_level = "rich"

    if coverage_level == "rich":
        note = (
            f"{name} is synced as its own club, so their full top run-scorers and"
            " wicket-takers are shown below."
        )
    else:
        note = (
            "Limited coverage: we hold our results and our players' record against"
            f" {name}, plus opponent batters we've dismissed. Their full batting/"
            "bowling records aren't available because their club isn't synced."
        )

    return {
        "opponent": {"opp_key": opp_key, "name": name},
        "coverage": {"level": coverage_level, "note": note},
        "head_to_head": head_to_head,
        "our_performers": our_performers,
        "their_danger_batters": danger,
        "their_key_players": their_key_players,
        "venues": venues,
        "matchups": {"bowler_dominance": bowler_dominance},
        "last_meeting": last_meeting,
    }
