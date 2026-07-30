"""One-off script: clone an existing club's full dataset into a brand-new demo
organisation, so BetterSelect/Availability/BetterFantasy/Voting can be demoed
live without touching a real club's data.

Copies (new ids throughout, remapped FKs): seasons, grades, players (incl.
photo bytes), BetterSelect teams, games + every per-game stat table, season
aggregate stats, award definitions + achievements, sponsors (incl. logo
bytes), yearbooks + sections. Then GENERATES a fresh block of upcoming,
unplayed BetterSelect fixtures (against opponent names lifted from the
source club's own history) so Selection/Availability/Voting have something
live to pick teams and cast ballots against, seeds a BetterFantasy season +
priced player pool, and creates one club_admin login for the new club.

Player email/phone are deliberately NOT copied (real people's contact
details have no place in a public demo club) and neither are grassroots_id/
playhq_id (these rows are not real CA/PlayHQ entities and must never be
mistaken for them by a future sync).

Usage (run on the server via the app container so it shares its DB access):

    docker compose exec betterstats-backend \\
        python -m app.scripts.clone_demo_club \\
        --source-slug applecross \\
        --name "Applecross Demo" \\
        --slug applecross-demo \\
        --admin-email you@example.com \\
        [--admin-password ...] [--weeks-ahead 10] [--seasons-limit 5] [--dry-run]

If --admin-password is omitted, a random one is generated and printed at the
end alongside the login details and a running count of everything cloned.
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
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
    FantasyPoolPlayer, FantasySeason, FieldingStat, Fixture, Game, GameAppearance,
    Grade, Milestone, Organisation, Partnership, Player, PlayerSeasonGradeStats,
    PlayerSeasonStats, Season, Sponsor, Team, User, VoteSettings, async_session_maker,
)
from app.services.module_subscriptions import ensure_core_subscription, upsert_subscription

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
    ap.add_argument("--name", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--admin-email", required=True)
    ap.add_argument("--admin-username", default=None)
    ap.add_argument("--admin-password", default=None)
    ap.add_argument("--weeks-ahead", type=int, default=10)
    ap.add_argument("--seasons-limit", type=int, default=None, help="only clone the N most recent seasons (default: all)")
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
        opp_cycle = itertools.cycle(opponents)
        today = date.today()
        next_saturday = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
        fixture_count = 0
        for team in team_rows:
            for week in range(args.weeks_ahead):
                played_on = next_saturday + timedelta(weeks=week)
                opponent = next(opp_cycle)
                is_home = week % 2 == 0
                home_team = org.name if is_home else opponent
                away_team = opponent if is_home else org.name
                session.add(Fixture(
                    id=uuid.uuid4(), organisation_id=org.id, grade_id=team.grade_id, team_id=team.id,
                    source="manual", playhq_id=None, label=None, round=f"Round {week + 1}",
                    played_on=played_on, end_on=None, start_time=None,
                    home_team=home_team, away_team=away_team,
                    home_away="HOME" if is_home else "AWAY", opponent_name=opponent,
                    venue="Home Ground" if is_home else f"{opponent} Ground",
                    status="UPCOMING", notes=None,
                ))
                fixture_count += 1
        counts["fixtures"] = fixture_count

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
