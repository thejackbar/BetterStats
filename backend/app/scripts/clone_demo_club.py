"""One-off script: clone an existing club's full dataset into a brand-new demo
organisation, so BetterSelect/Availability/BetterFantasy/Voting can be demoed
live without touching a real club's data.

Copies (new ids throughout, remapped FKs): seasons, grades, players (incl.
photo bytes), BetterSelect teams, games + every per-game stat table, season
aggregate stats, award definitions + achievements, sponsors (incl. logo
bytes), yearbooks + sections. Then GENERATES a full demo season of
BetterSelect fixtures (against opponent names lifted from the source club's
own history): a block of already-played rounds (--weeks-back, default 3)
with a real synthetic result and full scorecard, plus a block of upcoming,
unplayed rounds (--weeks-ahead, default 10). EVERY fixture — played or
upcoming — gets an XI pre-selected via BetterSelect's own fixture_lineups,
so Selection/Availability/Voting all have something live to work with
immediately, not just a blank season. Also seeds a BetterFantasy season +
priced player pool, and creates one club_admin login for the new club.

Player email/phone are deliberately NOT copied (real people's contact
details have no place in a public demo club) and neither are grassroots_id/
playhq_id (these rows are not real CA/PlayHQ entities and must never be
mistaken for them by a future sync). The synthetic results are plausible,
not simulated ball-by-ball cricket — see synthetic_scorecard() below.

Usage (run on the server via the app container so it shares its DB access):

    docker compose exec betterstats-backend \\
        python -m app.scripts.clone_demo_club \\
        --source-slug applecross \\
        --admin-email you@example.com \\
        [--name Orangecross] [--slug orangecross] [--admin-password ...] \\
        [--weeks-back 3] [--weeks-ahead 10] [--seasons-limit 5] [--dry-run]

If --admin-password is omitted, a random one is generated and printed at the
end alongside the login details and a running count of everything cloned.
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import random
import secrets
import sys
import uuid
from collections import Counter
from datetime import date, timedelta

import bcrypt
from sqlalchemy import MetaData, Table, insert, select

from app.auth.modules import ALL_MODULES, STATUS_ACTIVE
from app.models.db import (
    BattingInnings, BowlerWicket, BowlingSpell, ClubMembership, FallOfWicket,
    FantasyPoolPlayer, FantasySeason, FieldingStat, Fixture, FixtureLineup, Game,
    GameAppearance, Grade, Milestone, Organisation, Partnership, Player,
    PlayerSeasonGradeStats, PlayerSeasonStats, Season, Sponsor, Team, User,
    VoteSettings, async_session_maker,
)
from app.services.module_subscriptions import ensure_core_subscription, upsert_subscription

_DISMISSALS = ["bowled", "caught", "lbw", "run out", "stumped", "caught and bowled"]


def synthetic_scorecard(rng, lineup_ids):
    """Plausible (not ball-by-ball simulated) batting/bowling/fielding figures
    for OUR eleven only, used to give a handful of demo fixtures a real result
    to explore. Mirrors how a real synced game's per-game tables only ever
    hold OUR side — the opposition's own batting is never stored in the DB
    even for a genuine synced match (see the scorecard-endpoint notes in
    CLAUDE.md); it's fetched live from Grassroots at read time, which a
    fabricated demo game has none of, so the opposition side here is
    represented only via the runs our bowlers concede, same as any other
    club's stored data."""
    n = len(lineup_ids)
    wickets_fallen = rng.randint(min(5, n), min(10, n))
    batting, fow = [], []
    score = 0.0
    cumulative_overs = 0.0
    for i, pid in enumerate(lineup_ids):
        pos = i + 1
        out = i < wickets_fallen
        ceiling = 55 if pos <= 3 else 30 if pos <= 6 else 15
        runs = rng.randint(0, ceiling) if out else rng.randint(5, ceiling + 10)
        balls = max(runs, 1) + rng.randint(0, 20)
        fours = rng.randint(0, max(1, runs // 15))
        sixes = rng.randint(0, max(0, runs // 35))
        dismissal = rng.choice(_DISMISSALS) if out else None
        batting.append(dict(
            player_id=pid, runs=runs, balls=balls, fours=fours, sixes=sixes,
            not_out=not out, batting_position=pos, dismissal_type=dismissal, did_not_bat=False,
        ))
        score += runs
        if out:
            cumulative_overs += rng.uniform(2.5, 5.5)  # increment, so overs_at_fall stays monotonic
            fow.append(dict(
                wicket_number=len(fow) + 1, score_at_fall=int(score),
                overs_at_fall=round(cumulative_overs, 1),
                player_id=pid, dismissal_type=dismissal,
            ))

    # Assign each fallen wicket to a bowler up front (one shared draw), so a
    # bowler's aggregate `wickets` count in `bowling` always matches how many
    # times they appear in `bowler_wickets` below — computing these
    # independently let one bowler swallow every wicket by chance.
    bowler_ids = rng.sample(lineup_ids, min(6, n))
    wicket_credit = [rng.choice(bowler_ids) for _ in fow] if bowler_ids else []
    credit_counts = Counter(wicket_credit)
    bowling, opp_total = [], 0
    for pid in bowler_ids:
        overs = round(rng.uniform(4.0, 10.0), 1)
        runs_c = rng.randint(10, 45)
        opp_total += runs_c
        bowling.append(dict(
            player_id=pid, overs=overs, maidens=rng.randint(0, 2), runs=runs_c,
            wickets=credit_counts.get(pid, 0), wides=rng.randint(0, 4), no_balls=rng.randint(0, 2),
        ))

    # Credit each caught/stumped/run-out dismissal to a fielder (never the
    # batter themself) and every dismissal to the bowler drawn above, same
    # shape as a real bowler_wickets row (batter_name is always free-text —
    # it's the opposition's, which we never hold a player row for).
    catches = Counter()
    stumpings = Counter()
    run_outs = Counter()
    bowler_wickets = []
    for i, w in enumerate(fow):
        candidates = [pid for pid in lineup_ids if pid != w["player_id"]]
        bowler_id = wicket_credit[i] if wicket_credit else None
        fielder = rng.choice(candidates) if candidates else None
        dt = w["dismissal_type"]
        if dt in ("caught", "caught and bowled") and fielder:
            catches[fielder] += 1
        elif dt == "stumped" and fielder:
            stumpings[fielder] += 1
        elif dt == "run out" and fielder:
            run_outs[fielder] += 1
        bowler_wickets.append(dict(
            bowler_id=bowler_id, fielder_id=fielder if dt != "bowled" and dt != "lbw" else None,
            batter_name=f"Opposition batter #{w['wicket_number']}",
            batter_runs=None, batter_balls=None, dismissal_type="caught" if dt == "caught and bowled" else dt,
        ))

    partnerships = []
    prev_score = 0
    for w in fow:
        idx = lineup_ids.index(w["player_id"])
        partner_pid = lineup_ids[idx - 1] if idx > 0 else w["player_id"]
        runs = max(w["score_at_fall"] - prev_score, 0)
        partnerships.append(dict(
            wicket_number=w["wicket_number"], batter1_id=partner_pid, batter2_id=w["player_id"],
            runs=runs, balls=None, batter1_runs=None, batter2_runs=None, is_club_innings=True,
        ))
        prev_score = w["score_at_fall"]

    fielders = set(catches) | set(stumpings) | set(run_outs)
    fielding = [
        dict(player_id=pid, catches=catches.get(pid, 0), catches_wk=0,
             run_outs=run_outs.get(pid, 0), stumpings=stumpings.get(pid, 0))
        for pid in fielders
    ]

    return dict(
        batting=batting, bowling=bowling, fow=fow, bowler_wickets=bowler_wickets,
        partnerships=partnerships, fielding=fielding,
        our_total=int(score), opp_total=opp_total,
    )

CHUNK = 1000


def chunked(seq, size=CHUNK):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


async def reflect_table(session, name):
    conn = await session.connection()
    return await conn.run_sync(lambda sync_conn: Table(name, MetaData(), autoload_with=sync_conn))


def new_image_url(prefix, entity, new_id, has_bytes):
    if not has_bytes:
        return None
    return f"/api/images/{prefix}/{new_id}/{entity}?v={uuid.uuid4().hex[:8]}"


async def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source-slug", default="applecross")
    ap.add_argument("--name", default="Orangecross")
    ap.add_argument("--slug", default="orangecross")
    ap.add_argument("--admin-email", required=True)
    ap.add_argument("--admin-username", default=None)
    ap.add_argument("--admin-password", default=None)
    ap.add_argument("--weeks-back", type=int, default=3, help="already-played rounds, each given a real synthetic result")
    ap.add_argument("--weeks-ahead", type=int, default=10, help="upcoming, unplayed rounds")
    ap.add_argument("--seasons-limit", type=int, default=None, help="only clone the N most recent seasons (default: all)")
    ap.add_argument("--seed", type=int, default=None, help="RNG seed for reproducible synthetic results")
    ap.add_argument("--dry-run", action="store_true", help="do everything except the final commit")
    args = ap.parse_args()

    counts = Counter()

    async with async_session_maker() as session:
        src = (await session.execute(select(Organisation).where(Organisation.slug == args.source_slug))).scalar_one_or_none()
        if src is None:
            print(f"No organisation with slug={args.source_slug!r}", file=sys.stderr)
            sys.exit(1)

        existing = (await session.execute(select(Organisation.id).where(Organisation.slug == args.slug))).scalar_one_or_none()
        if existing is not None:
            print(f"slug={args.slug!r} is already taken", file=sys.stderr)
            sys.exit(1)

        # ── 1. New organisation, cloned branding ────────────────────────────
        new_org_id = uuid.uuid4()
        org = Organisation(
            id=new_org_id,
            name=args.name,
            short_name=src.short_name,
            slug=args.slug,
            is_active=True,
            primary_color=src.primary_color,
            accent_color=src.accent_color,
            logo_data=src.logo_data,
            logo_mime=src.logo_mime,
            hero_image_data=src.hero_image_data,
            hero_image_mime=src.hero_image_mime,
            theme_mode=src.theme_mode,
            theme_config=src.theme_config,
            contact_email=args.admin_email,
            player_name_format=src.player_name_format,
            dormancy_months=src.dormancy_months,
            default_team_size=src.default_team_size,
            public_show_role=src.public_show_role,
            public_show_batting=src.public_show_batting,
            public_show_bowling=src.public_show_bowling,
            public_show_opening=src.public_show_opening,
            public_show_gender=src.public_show_gender,
            include_fill_ins_in_stats=src.include_fill_ins_in_stats,
            subscription_status="active",
            availability_self_service_enabled=True,
            availability_require_pin=False,
            availability_link_token=secrets.token_urlsafe(24),
        )
        org.logo_url = new_image_url("organisations", "logo", new_org_id, bool(org.logo_data))
        org.hero_image_url = new_image_url("organisations", "hero", new_org_id, bool(org.hero_image_data))
        session.add(org)

        # Grant every module so nothing in the demo is gated behind billing.
        ensure_core_subscription(org)
        for key in ALL_MODULES:
            upsert_subscription(org, key, status=STATUS_ACTIVE)
        await session.flush()
        counts["organisation"] = 1

        # ── 2. Admin login ───────────────────────────────────────────────────
        admin_password = args.admin_password or secrets.token_urlsafe(9)
        admin_username = args.admin_username or f"{args.slug}-admin"
        user = User(
            id=uuid.uuid4(),
            email=args.admin_email,
            username=admin_username,
            password_hash=bcrypt.hashpw(admin_password.encode(), bcrypt.gensalt()).decode(),
            display_name="Demo Admin",
            first_name="Demo",
            last_name="Admin",
        )
        session.add(user)
        await session.flush()
        session.add(ClubMembership(
            club_id=org.id, user_id=user.id, role="club_admin", capabilities=[], is_primary_admin=True,
        ))
        await session.flush()
        counts["admin_user"] = 1

        # ── 3. Seasons ────────────────────────────────────────────────────
        seasons_q = select(Season).where(Season.organisation_id == src.id).order_by(Season.year.desc().nullslast())
        src_seasons = (await session.execute(seasons_q)).scalars().all()
        if args.seasons_limit:
            src_seasons = src_seasons[:args.seasons_limit]
        season_id_map = {}
        for s in src_seasons:
            new_id = uuid.uuid4()
            season_id_map[s.id] = new_id
            session.add(Season(
                id=new_id, organisation_id=org.id, grassroots_id=None,
                name=s.name, year=s.year, synced_at=None, display_order=s.display_order,
            ))
        await session.flush()
        counts["seasons"] = len(season_id_map)

        # ── 4. Grades ─────────────────────────────────────────────────────
        grades_q = select(Grade).where(Grade.season_id.in_(season_id_map.keys()))
        src_grades = (await session.execute(grades_q)).scalars().all()
        grade_id_map = {}
        for g in src_grades:
            new_id = uuid.uuid4()
            grade_id_map[g.id] = new_id
            session.add(Grade(
                id=new_id, season_id=season_id_map[g.season_id], grassroots_id=None,
                name=g.name, display_name_override=g.display_name_override, playhq_id=None,
                fee_format=g.fee_format, category=g.category, is_public=g.is_public,
            ))
        await session.flush()
        counts["grades"] = len(grade_id_map)

        # ── 5. Players (photos copied, contact details deliberately dropped) ─
        players_q = select(Player).where(Player.organisation_id == src.id)
        src_players = (await session.execute(players_q)).scalars().all()
        player_id_map = {}
        new_players_by_old_id = {}
        for p in src_players:
            new_id = uuid.uuid4()
            player_id_map[p.id] = new_id
            new_p = Player(
                id=new_id, name=p.name, display_name_override=p.display_name_override,
                organisation_id=org.id, playhq_id=None, grassroots_id=None, claim_note=None,
                photo_data=p.photo_data, photo_mime=p.photo_mime,
                gender=p.gender, is_player=p.is_player, player_role=p.player_role,
                is_overseas=p.is_overseas, overseas_country=p.overseas_country,
                batting_hand=p.batting_hand, bowling_action=p.bowling_action, bowling_type=p.bowling_type,
                is_opening_batsman=p.is_opening_batsman, squad_team_id=None,
                claimed=False, user_id=None, email=None, phone=None,
                skill_positions=list(p.skill_positions or []), status=p.status,
            )
            new_p.photo_url = new_image_url("players", "photo", new_id, bool(new_p.photo_data))
            new_players_by_old_id[p.id] = new_p
            session.add(new_p)
        await session.flush()
        counts["players"] = len(player_id_map)

        # ── 6. BetterSelect teams (+ backfill players.squad_team_id) ────────
        teams_q = select(Team).where(Team.organisation_id == src.id)
        src_teams = (await session.execute(teams_q)).scalars().all()
        team_id_map = {}
        for t in src_teams:
            new_id = uuid.uuid4()
            team_id_map[t.id] = new_id
            session.add(Team(
                id=new_id, organisation_id=org.id, name=t.name, short_name=t.short_name,
                sequence=t.sequence, grade_id=grade_id_map.get(t.grade_id) if t.grade_id else None,
                default_formation=t.default_formation, is_active=t.is_active,
                source=t.source, playhq_id=None,
            ))
        await session.flush()
        counts["teams"] = len(team_id_map)

        for p in src_players:
            if p.squad_team_id and p.squad_team_id in team_id_map:
                new_players_by_old_id[p.id].squad_team_id = team_id_map[p.squad_team_id]

        # ── 7. Games ──────────────────────────────────────────────────────
        games_q = select(Game).where(Game.grade_id.in_(grade_id_map.keys()))
        src_games = (await session.execute(games_q)).scalars().all()
        game_id_map = {}
        game_rows = []
        for g in src_games:
            new_id = uuid.uuid4()
            game_id_map[g.id] = new_id
            game_rows.append(dict(
                id=new_id, grade_id=grade_id_map[g.grade_id], played_at=g.played_at,
                home_team=g.home_team, away_team=g.away_team, home_club=g.home_club, away_club=g.away_club,
                opp_org_id=g.opp_org_id, opp_club_name=g.opp_club_name,
                home_org_id=None, away_org_id=None,
                result=g.result, winning_team=g.winning_team, is_final=g.is_final,
                raw_payload=g.raw_payload, venue=g.venue, match_format=g.match_format,
            ))
        for chunk in chunked(game_rows):
            await session.execute(insert(Game.__table__), chunk)
        counts["games"] = len(game_id_map)

        # Opponent names for later fixture generation — collect before we lose src_games.
        own_names = {n.lower() for n in (src.name, src.short_name) if n}
        opponent_pool = Counter()
        for g in src_games:
            for name in (g.home_team, g.away_team):
                if name and name.lower() not in own_names:
                    opponent_pool[name] += 1
        opponents = [n for n, _ in opponent_pool.most_common(16)] or ["Visiting Cricket Club"]

        # ── 8. Per-game stat tables ───────────────────────────────────────
        async def clone_simple(model, extra=None):
            rows = (await session.execute(select(model).where(model.game_id.in_(game_id_map.keys())))).scalars().all()
            out = []
            for r in rows:
                pid = player_id_map.get(r.player_id) if r.player_id else None
                if r.player_id and pid is None:
                    continue  # cross-club leaked player row we didn't clone — drop, don't fabricate
                d = {c.name: getattr(r, c.name) for c in model.__table__.columns}
                d.pop("id", None)  # autoincrement PK — let the DB assign it
                d["game_id"] = game_id_map[r.game_id]
                d["player_id"] = pid
                if extra:
                    extra(d, r)
                out.append(d)
            for chunk in chunked(out):
                await session.execute(insert(model.__table__), chunk)
            return len(out)

        counts["batting_innings"] = await clone_simple(BattingInnings)
        counts["bowling_spells"] = await clone_simple(BowlingSpell)

        # game_appearances has a composite (game_id, player_id) PK, no id column
        appear_rows = (await session.execute(select(GameAppearance).where(GameAppearance.game_id.in_(game_id_map.keys())))).scalars().all()
        appear_out = []
        for r in appear_rows:
            pid = player_id_map.get(r.player_id)
            if pid is None:
                continue
            appear_out.append(dict(
                game_id=game_id_map[r.game_id], player_id=pid, team_name=r.team_name,
                is_captain=r.is_captain, is_wicket_keeper=r.is_wicket_keeper,
            ))
        for chunk in chunked(appear_out):
            await session.execute(insert(GameAppearance.__table__), chunk)
        counts["game_appearances"] = len(appear_out)

        # fielding_stats / bowler_wickets / fall_of_wickets / partnerships all
        # tolerate a NULL player_id (they carry a free-text name fallback), so a
        # cross-club-leaked row degrades to unlinked-but-still-named rather than
        # being dropped.
        fs_rows = (await session.execute(select(FieldingStat).where(FieldingStat.game_id.in_(game_id_map.keys())))).scalars().all()
        fs_out = [dict(
            game_id=game_id_map[r.game_id], player_id=player_id_map.get(r.player_id),
            catches=r.catches, catches_wk=r.catches_wk, run_outs=r.run_outs, stumpings=r.stumpings,
            player_name=r.player_name,
        ) for r in fs_rows]
        for chunk in chunked(fs_out):
            await session.execute(insert(FieldingStat.__table__), chunk)
        counts["fielding_stats"] = len(fs_out)

        bw_rows = (await session.execute(select(BowlerWicket).where(BowlerWicket.game_id.in_(game_id_map.keys())))).scalars().all()
        bw_out = []
        for r in bw_rows:
            bowler_new = player_id_map.get(r.bowler_id)
            if bowler_new is None:
                continue  # bowler_id is NOT NULL — can't clone without it
            bw_out.append(dict(
                game_id=game_id_map[r.game_id], innings_number=r.innings_number,
                bowler_id=bowler_new, fielder_id=player_id_map.get(r.fielder_id),
                batter_name=r.batter_name, batter_position=r.batter_position,
                batter_runs=r.batter_runs, batter_balls=r.batter_balls,
                dismissal_type=r.dismissal_type, caught_behind=r.caught_behind,
            ))
        for chunk in chunked(bw_out):
            await session.execute(insert(BowlerWicket.__table__), chunk)
        counts["bowler_wickets"] = len(bw_out)

        fow_rows = (await session.execute(select(FallOfWicket).where(FallOfWicket.game_id.in_(game_id_map.keys())))).scalars().all()
        fow_out = [dict(
            game_id=game_id_map[r.game_id], innings_number=r.innings_number, wicket_number=r.wicket_number,
            score_at_fall=r.score_at_fall, overs_at_fall=r.overs_at_fall,
            player_id=player_id_map.get(r.player_id), batter_name=r.batter_name,
        ) for r in fow_rows]
        for chunk in chunked(fow_out):
            await session.execute(insert(FallOfWicket.__table__), chunk)
        counts["fall_of_wickets"] = len(fow_out)

        pships = (await session.execute(select(Partnership).where(Partnership.game_id.in_(game_id_map.keys())))).scalars().all()
        pship_out = [dict(
            game_id=game_id_map[r.game_id], innings_number=r.innings_number, wicket_number=r.wicket_number,
            batter1_id=player_id_map.get(r.batter1_id), batter2_id=player_id_map.get(r.batter2_id),
            runs=r.runs, balls=r.balls, batter1_runs=r.batter1_runs, batter2_runs=r.batter2_runs,
            is_club_innings=r.is_club_innings, batter1_name=r.batter1_name, batter2_name=r.batter2_name,
        ) for r in pships]
        for chunk in chunked(pship_out):
            await session.execute(insert(Partnership.__table__), chunk)
        counts["partnerships"] = len(pship_out)

        ms_rows = (await session.execute(select(Milestone).where(Milestone.player_id.in_(player_id_map.keys())))).scalars().all()
        ms_out = []
        for r in ms_rows:
            pid = player_id_map.get(r.player_id)
            if pid is None:
                continue
            ms_out.append(dict(
                player_id=pid, game_id=game_id_map.get(r.game_id) if r.game_id else None,
                milestone_type=r.milestone_type, milestone_value=r.milestone_value,
                achieved_at=r.achieved_at, detail=r.detail,
            ))
        for chunk in chunked(ms_out):
            await session.execute(insert(Milestone.__table__), chunk)
        counts["milestones"] = len(ms_out)

        # ── 9. Season-aggregate stats ─────────────────────────────────────
        pss_rows = (await session.execute(select(PlayerSeasonStats).where(PlayerSeasonStats.season_id.in_(season_id_map.keys())))).scalars().all()
        pss_out = []
        for r in pss_rows:
            pid = player_id_map.get(r.player_id)
            if pid is None:
                continue
            d = {c.name: getattr(r, c.name) for c in PlayerSeasonStats.__table__.columns}
            d.pop("id", None)
            d["player_id"] = pid
            d["season_id"] = season_id_map[r.season_id]
            pss_out.append(d)
        for chunk in chunked(pss_out):
            await session.execute(insert(PlayerSeasonStats.__table__), chunk)
        counts["player_season_stats"] = len(pss_out)

        psgs_rows = (await session.execute(select(PlayerSeasonGradeStats).where(PlayerSeasonGradeStats.season_id.in_(season_id_map.keys())))).scalars().all()
        psgs_out = []
        for r in psgs_rows:
            pid = player_id_map.get(r.player_id)
            gid = grade_id_map.get(r.grade_id)
            if pid is None or gid is None:
                continue
            d = {c.name: getattr(r, c.name) for c in PlayerSeasonGradeStats.__table__.columns}
            d.pop("id", None)
            d["player_id"] = pid
            d["season_id"] = season_id_map[r.season_id]
            d["grade_id"] = gid
            psgs_out.append(d)
        for chunk in chunked(psgs_out):
            await session.execute(insert(PlayerSeasonGradeStats.__table__), chunk)
        counts["player_season_grade_stats"] = len(psgs_out)

        # ── 10. Awards (no ORM model — reflect the live tables) ───────────
        awd_tbl = await reflect_table(session, "org_award_definitions")
        awd_rows = (await session.execute(select(awd_tbl).where(awd_tbl.c.org_id == src.id))).mappings().all()
        award_def_id_map = {}
        awd_out = []
        for r in awd_rows:
            new_id = uuid.uuid4()
            award_def_id_map[r["id"]] = new_id
            d = dict(r)
            d["id"] = new_id
            d["org_id"] = org.id
            awd_out.append(d)
        for chunk in chunked(awd_out):
            await session.execute(insert(awd_tbl), chunk)
        counts["org_award_definitions"] = len(awd_out)

        pa_tbl = await reflect_table(session, "player_achievements")
        pa_rows = (await session.execute(select(pa_tbl).where(pa_tbl.c.org_id == src.id))).mappings().all()
        pa_out = []
        for r in pa_rows:
            d = dict(r)
            d.pop("id", None)
            d["org_id"] = org.id
            d["player_id"] = player_id_map.get(r["player_id"]) if r["player_id"] else None
            if "import_batch_id" in d:
                d["import_batch_id"] = None
            pa_out.append(d)
        for chunk in chunked(pa_out):
            await session.execute(insert(pa_tbl), chunk)
        counts["player_achievements"] = len(pa_out)

        # ── 11. Sponsors ──────────────────────────────────────────────────
        sponsors_q = select(Sponsor).where(Sponsor.organisation_id == src.id)
        src_sponsors = (await session.execute(sponsors_q)).scalars().all()
        for sp in src_sponsors:
            new_id = uuid.uuid4()
            new_logo_url = f"/images/sponsors/{new_id}/logo?v={uuid.uuid4().hex[:8]}" if sp.logo_data else None
            session.add(Sponsor(
                id=new_id, organisation_id=org.id, name=sp.name, website_url=sp.website_url,
                logo_url=new_logo_url, logo_data=sp.logo_data, logo_mime=sp.logo_mime,
                display_order=sp.display_order, contact_name=None, email=None, klubpro_sponsor_id=None,
            ))
        counts["sponsors"] = len(src_sponsors)

        # ── 12. Yearbooks + sections (no ORM model — reflect) ─────────────
        yb_tbl = await reflect_table(session, "yearbooks")
        yb_rows = (await session.execute(select(yb_tbl).where(yb_tbl.c.org_id == src.id))).mappings().all()
        yearbook_id_map = {}
        yb_out = []
        for r in yb_rows:
            sid = season_id_map.get(r["season_id"])
            if sid is None:
                continue
            new_id = uuid.uuid4()
            yearbook_id_map[r["id"]] = new_id
            d = dict(r)
            d["id"] = new_id
            d["org_id"] = org.id
            d["season_id"] = sid
            yb_out.append(d)
        for chunk in chunked(yb_out):
            await session.execute(insert(yb_tbl), chunk)
        counts["yearbooks"] = len(yb_out)

        ys_tbl = await reflect_table(session, "yearbook_sections")
        if yearbook_id_map:
            ys_rows = (await session.execute(select(ys_tbl).where(ys_tbl.c.yearbook_id.in_(yearbook_id_map.keys())))).mappings().all()
        else:
            ys_rows = []
        ys_out = []
        for r in ys_rows:
            d = dict(r)
            d.pop("id", None)
            d["yearbook_id"] = yearbook_id_map[r["yearbook_id"]]
            ys_out.append(d)
        for chunk in chunked(ys_out):
            await session.execute(insert(ys_tbl), chunk)
        counts["yearbook_sections"] = len(ys_out)

        # ── 13. Generate a fresh block of upcoming BetterSelect fixtures ──
        await session.flush()
        demo_teams = [t for t in team_id_map.values()]
        if not demo_teams:
            # No BetterSelect teams configured on the source club — make one
            # generic team against the most recent (cloned) season's first grade.
            old_season_year = {s.id: (s.year or 0) for s in src_seasons}
            latest_old_season_id = max(old_season_year, key=old_season_year.get) if old_season_year else None
            latest_old_grade_ids = [g.id for g in src_grades if g.season_id == latest_old_season_id]
            latest_grades = [grade_id_map[gid] for gid in latest_old_grade_ids if gid in grade_id_map]
            fallback_team_id = uuid.uuid4()
            session.add(Team(
                id=fallback_team_id, organisation_id=org.id, name="1st XI", short_name="1sts",
                sequence=1, grade_id=latest_grades[0] if latest_grades else None,
                default_formation=None, is_active=True, source="manual", playhq_id=None,
            ))
            await session.flush()
            demo_teams = [fallback_team_id]

        team_rows = (await session.execute(
            select(Team).where(Team.id.in_(demo_teams), Team.is_active.is_(True))
        )).scalars().all() or (await session.execute(select(Team).where(Team.id.in_(demo_teams)))).scalars().all()

        rng = random.Random(args.seed)
        active_pool = [p for p in new_players_by_old_id.values() if p.status == "active" and p.is_player]
        squad_pool = {team.id: [p for p in active_pool if p.squad_team_id == team.id] for team in team_rows}

        def pick_lineup(team):
            # Squad-assigned players first (up to 11); fill any remaining
            # slots from the general active pool. Doesn't enforce
            # one-XI-per-player-per-round across different teams' fixtures on
            # the same date — a cosmetic overlap, not worth the complexity
            # for a demo generator.
            squad = list(squad_pool.get(team.id) or [])
            rng.shuffle(squad)
            chosen = squad[:11]
            if len(chosen) < 11:
                extras = [p for p in active_pool if p not in chosen]
                rng.shuffle(extras)
                chosen += extras[:11 - len(chosen)]
            rng.shuffle(chosen)
            return chosen

        opp_cycle = itertools.cycle(opponents)
        today = date.today()
        next_saturday = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
        fixture_count = lineup_count = result_game_count = 0

        for team in team_rows:
            for offset in range(-args.weeks_back, args.weeks_ahead):
                round_no = offset + args.weeks_back + 1
                played_on = next_saturday + timedelta(weeks=offset)
                opponent = next(opp_cycle)
                is_home = round_no % 2 == 1
                is_played = offset < 0
                home_team = org.name if is_home else opponent
                away_team = opponent if is_home else org.name
                venue = "Home Ground" if is_home else f"{opponent} Ground"
                fixture_id = uuid.uuid4()
                session.add(Fixture(
                    id=fixture_id, organisation_id=org.id, grade_id=team.grade_id, team_id=team.id,
                    source="manual", playhq_id=None, label=None, round=f"Round {round_no}",
                    played_on=played_on, end_on=None, start_time=None,
                    home_team=home_team, away_team=away_team,
                    home_away="HOME" if is_home else "AWAY", opponent_name=opponent,
                    venue=venue, status=("FINAL" if is_played else "UPCOMING"), notes=None,
                ))
                fixture_count += 1

                lineup = pick_lineup(team)
                if not lineup:
                    continue
                keeper = next(
                    (p for p in lineup if "WKT" in (p.skill_positions or [])),
                    lineup[1] if len(lineup) > 1 else lineup[0],
                )
                for i, p in enumerate(lineup):
                    session.add(FixtureLineup(
                        fixture_id=fixture_id, player_id=p.id, organisation_id=org.id,
                        batting_order=i + 1, is_captain=(i == 0), is_wicket_keeper=(p.id == keeper.id),
                        selected_by=None,
                    ))
                lineup_count += len(lineup)

                if is_played:
                    lineup_ids = [p.id for p in lineup]
                    synth = synthetic_scorecard(rng, lineup_ids)
                    game_id = uuid.uuid4()
                    if synth["our_total"] > synth["opp_total"]:
                        result, winning_team = "WIN", org.name
                    elif synth["opp_total"] > synth["our_total"]:
                        result, winning_team = "LOSS", opponent
                    else:
                        result, winning_team = "DRAW", None
                    session.add(Game(
                        id=game_id, grade_id=team.grade_id, played_at=played_on,
                        home_team=home_team, away_team=away_team,
                        home_club=org.name if is_home else opponent,
                        away_club=opponent if is_home else org.name,
                        opp_org_id=None, opp_club_name=opponent, home_org_id=None, away_org_id=None,
                        result=result, winning_team=winning_team, is_final=True,
                        raw_payload=None, venue=venue, match_format=None,
                    ))
                    # BowlerWicket/FallOfWicket/Partnership/FieldingStat carry a
                    # bare game_id FK with no relationship() back to Game, so the
                    # flush dependency sort can't see the edge — flush the Game
                    # row now so the children below always have a real parent.
                    await session.flush()
                    for b in synth["batting"]:
                        session.add(BattingInnings(game_id=game_id, innings_number=1, **b))
                    for b in synth["bowling"]:
                        session.add(BowlingSpell(game_id=game_id, innings_number=1, **b))
                    for f in synth["fow"]:
                        session.add(FallOfWicket(
                            game_id=game_id, innings_number=1, wicket_number=f["wicket_number"],
                            score_at_fall=f["score_at_fall"], overs_at_fall=f["overs_at_fall"],
                            player_id=f["player_id"],
                        ))
                    for bw in synth["bowler_wickets"]:
                        session.add(BowlerWicket(game_id=game_id, innings_number=1, **bw))
                    for ps in synth["partnerships"]:
                        session.add(Partnership(game_id=game_id, innings_number=1, **ps))
                    for fs in synth["fielding"]:
                        session.add(FieldingStat(game_id=game_id, **fs))
                    for p in lineup:
                        session.add(GameAppearance(
                            game_id=game_id, player_id=p.id,
                            is_captain=(p.id == lineup[0].id), is_wicket_keeper=(p.id == keeper.id),
                        ))
                    result_game_count += 1

        counts["fixtures"] = fixture_count
        counts["fixture_lineups"] = lineup_count
        counts["result_games"] = result_game_count

        # ── 14. Vote settings tuned for a frictionless live demo ──────────
        # eligibility_source='lineup' lets voting work off the BetterSelect XI
        # alone — no synced scorecard needed, since these fixtures are unplayed.
        session.add(VoteSettings(
            organisation_id=org.id, enabled=True, link_token=secrets.token_urlsafe(24),
            require_pin=False, voter_mode="players", eligibility_source="lineup",
            allow_non_participants=True,
        ))
        counts["vote_settings"] = 1

        # ── 15. BetterFantasy: a season + a priced pool from real career stats ─
        fantasy_season_id = uuid.uuid4()
        session.add(FantasySeason(
            id=fantasy_season_id, organisation_id=org.id, season_year=today.year,
            name=f"{org.name} Fantasy {today.year}", status="open", registration_open=True,
        ))
        await session.flush()

        totals = {}  # new_player_id -> (runs, wickets)
        for r in pss_out:
            pid = r["player_id"]
            runs, wkts = totals.get(pid, (0, 0))
            totals[pid] = (runs + (r.get("runs") or 0), wkts + (r.get("wickets") or 0))

        pool_out = []
        for pid, (runs, wkts) in totals.items():
            if runs == 0 and wkts == 0:
                continue
            role = "bowler" if wkts * 2 > runs else ("allrounder" if wkts * 10 > runs else "batter")
            price = max(8.0, min(18.0, 8.0 + runs / 300.0 + wkts / 5.0))
            price = round(price * 2) / 2  # nearest 0.5
            pool_out.append(dict(
                id=uuid.uuid4(), fantasy_season_id=fantasy_season_id, organisation_id=org.id,
                player_id=pid, role=role, role_source="auto",
                base_price=price, current_price=price, total_points=0, last_round_points=0,
                owned_count=0, price_change=0,
            ))
        for chunk in chunked(pool_out):
            await session.execute(insert(FantasyPoolPlayer.__table__), chunk)
        counts["fantasy_pool_players"] = len(pool_out)

        if args.dry_run:
            await session.rollback()
            print("DRY RUN — rolled back, nothing was written.")
        else:
            await session.commit()

    print()
    print("=" * 60)
    print(f"Demo club created: {args.name!r}  (slug={args.slug})")
    print(f"  org id: {new_org_id}")
    print(f"  URL:    https://betterat.cricket/{args.slug}")
    print(f"  admin login — username: {admin_username}  password: {admin_password}")
    print("-" * 60)
    for k, v in counts.items():
        print(f"  {k:28s} {v}")
    print("=" * 60)
    print("Next: log in, run through the Setup Wizard for branding, then open")
    print("BetterSelect > Fixtures to pick lineups against the generated fixtures,")
    print("share the Availability/Voting public links, and check BetterFantasy's pool.")


if __name__ == "__main__":
    asyncio.run(main())
