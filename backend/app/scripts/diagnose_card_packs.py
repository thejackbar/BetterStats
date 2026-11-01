"""Why did this player not get a Winner Winner or Match Day pack? Read-only.

Prints, for each player record in the club that matches the name: the club's switches and start day, the fixtures on the day with
whether the player is on their confirmed team sheet, the scorecards dated that day, whether `Match Day` would be granted, the games
finished in the last week that count as a win for them and why each does or does not, and the packs they already hold. Anything
that raises is printed rather than hidden.

    python -m app.scripts.diagnose_card_packs <club slug> "<part of the player's name>" [--date YYYY-MM-DD]

Run inside the betterstats-backend container (`docker compose exec`, from /srv/docker, with COMPOSE_PROJECT_NAME set).
"""
import argparse
import asyncio
from datetime import date, timedelta

from sqlalchemy import select, text

from app.models.db import Organisation, async_session_maker
from app.services import player_cards as pc


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("club")
    ap.add_argument("name")
    ap.add_argument("--date", default="")
    args = ap.parse_args()
    async with async_session_maker() as db:
        club = (await db.execute(select(Organisation).where(Organisation.slug == args.club.lower()))).scalars().first()
        if not club:
            print(f"No club called {args.club!r}.")
            raise SystemExit(1)
        org = str(club.id)
        s = await pc.load_settings(db, org)
        today = date.fromisoformat(args.date) if args.date else pc.club_today(s)
        print(f"Club {club.slug}: today (club time) {pc.club_today(s)}, looking at {today}")
        print(f"  cards enabled={s.get('enabled')} launched_at={s.get('launched_at')} day packs={s.get('event_packs_enabled')} "
              f"winner packs={s.get('winner_packs')} winner start day={s.get('winner_packs_from')} timezone={pc.club_zone(s)}")
        snap = await pc.club_snapshot(db, club, fresh=True)
        rows = (await db.execute(text("""
            SELECT id::text, name, display_name_override, is_player, is_public, status, organisation_id::text FROM players
             WHERE organisation_id = CAST(:o AS UUID) AND (name ILIKE :n OR display_name_override ILIKE :n) ORDER BY name
        """), {"o": org, "n": f"%{args.name}%"})).fetchall()
        if not rows:
            print("  No player record matches that name.")
        for pid, name, override, is_player, is_public, status, _o in rows:
            print(f"\nPlayer {override or name} ({pid[:8]}) is_player={is_player} public={is_public} status={status} in the card pool={pid in snap['people']}")
            fx = (await db.execute(text("""
                SELECT f.id::text, f.played_on, f.end_on, f.status, f.source, f.locked_at IS NOT NULL AS locked, COALESCE(f.label, ''), COALESCE(f.opponent_name, ''),
                       EXISTS (SELECT 1 FROM fixture_lineups fl WHERE fl.fixture_id = f.id AND fl.player_id = CAST(:p AS UUID)) AS on_sheet,
                       (SELECT COUNT(*) FROM fixture_lineups fl WHERE fl.fixture_id = f.id) AS sheet_size
                  FROM fixtures f WHERE f.organisation_id = CAST(:o AS UUID) AND (f.played_on = :d OR f.end_on = :d) ORDER BY f.start_time NULLS LAST
            """), {"o": org, "p": pid, "d": today})).fetchall()
            print(f"  fixtures on {today}: {len(fx)}")
            for f in fx:
                print(f"    {f[0][:8]} {f[1]}..{f[2]} status={f[3]} source={f[4]} locked={f[5]} '{f[6]}' v {f[7]}  on the sheet={f[8]} (sheet has {f[9]})")
            apps = (await db.execute(text("""
                SELECT g.id::text, g.played_at, ga.team_name, ga.is_reserve FROM game_appearances ga JOIN v_effective_games g ON g.id = ga.game_id
                 WHERE ga.player_id = CAST(:p AS UUID) AND g.played_at = :d
            """), {"p": pid, "d": today})).fetchall()
            print(f"  scorecards dated {today} with this player: {len(apps)}")
            print(f"  playing today by the Match Day rule: {await pc._playing_today(db, org, pid, today)}")
            others = (await db.execute(text("""
                SELECT p2.id::text, p2.name FROM fixture_lineups fl JOIN fixtures f ON f.id = fl.fixture_id JOIN players p2 ON p2.id = fl.player_id
                 WHERE f.organisation_id = CAST(:o AS UUID) AND (f.played_on = :d OR f.end_on = :d) AND p2.id <> CAST(:p AS UUID)
                   AND (p2.name ILIKE :n OR p2.display_name_override ILIKE :n)
            """), {"o": org, "p": pid, "d": today, "n": f"%{args.name}%"})).fetchall()
            for o in others:
                print(f"  NOTE: another record with a similar name IS on a sheet today: {o[1]} ({o[0][:8]}). A duplicate player record?")
            print("  wins in the last week:")
            try:
                counted = set(await pc._winning_games(db, org, pid, today - timedelta(days=8), today + timedelta(days=1)))
                games = (await db.execute(text("""
                    SELECT g.id::text, g.played_at, g.home_team, g.away_team, g.winning_team, g.result, g.status, g.organisation_id::text, g.home_org_id::text, g.away_org_id::text,
                           ga.team_name, ga.is_reserve, (SELECT end_on FROM fixtures f WHERE f.id = g.id)
                      FROM game_appearances ga JOIN v_effective_games g ON g.id = ga.game_id
                     WHERE ga.player_id = CAST(:p AS UUID) AND g.played_at >= :since ORDER BY g.played_at
                """), {"p": pid, "since": today - timedelta(days=9)})).fetchall()
                for g in games:
                    mark = "COUNTS" if g[0] in counted else "does not count"
                    print(f"    {g[1]} {g[2]} v {g[3]} winner={g[4]!r} result={g[5]!r} status={g[6]} owner={'us' if g[7] == org else g[7]} home_org={'us' if g[8] == org else g[8]} "
                          f"away_org={'us' if g[9] == org else g[9]} team_name={g[10]!r} reserve={g[11]} end_on={g[12]}  -> {mark}")
                if not games:
                    print("    no scorecards for this player in the last 9 days (the sync may not have read the games yet)")
            except Exception as exc:
                print(f"    THE WINS QUERY RAISED: {type(exc).__name__}: {exc}")
                await db.rollback()
            held = (await db.execute(text("""
                SELECT source, ref_key, granted_at, opened_at IS NOT NULL FROM player_card_packs
                 WHERE player_id = CAST(:p AS UUID) AND source IN ('winner_winner', 'match_day') ORDER BY granted_at DESC LIMIT 12
            """), {"p": pid})).fetchall()
            print("  packs held (latest 12 of winner_winner and match_day):")
            for h in held:
                print(f"    {h[0]} {h[1]} granted {h[2]:%Y-%m-%d %H:%M} opened={h[3]}")
            if not held:
                print("    none")


if __name__ == "__main__":
    asyncio.run(main())
