#!/usr/bin/env python3
"""
Convert CSFW `.av` season databases into the sheet BetterCricket's
Manual Entries importer accepts (Admin -> Manual Entries -> Import,
/admin/manual-entries#import).

    python3 to_manual_games_csv.py <dir-of-.av-files> -o out/

The importer takes ONE wide row per player per innings, grouped into matches by
`game_key`; game-level fields are read from the first row of each key. It caps
an upload at 8 MB, so this writes one sheet per season rather than one big file.

Conventions chosen here, and why:

* `season_name` uses BetterCricket's own canonical form, `Summer YYYY/YY`
  (services/season_resolve.canonical_name), so an existing season matches by
  name instead of creating a duplicate.
* `grade_name` is left BLANK. CSFW has no grade field and one file holds
  several grades at once - see CSFW_FORMAT.md. Grade is optional to the
  importer; supply it yourself if you can separate the teams.
* `innings_number` follows cricket's numbering, with our batting odd and our
  bowling even: CSFW innings-pair k gives batting 2k+1 and bowling 2k+2. The
  scorecard view reads "bowling in innings N" as the bowling AGAINST innings
  N's batting, so putting our batting and our bowling under one number would
  render our own attack as if it had bowled at us.
* `player_name` is written `Surname, Initials` - the template's own form, and
  unambiguous about which half is the surname for `import_ingest.match_players`.
* `result` uses the WIN/LOSS/DRAW/TIE vocabulary `v_effective_games` compares
  against; an abandoned or unclassified match is left blank.
* `batting_caught_behind` is always blank. CSFW records the fielder only for
  our own fielding, never for the opposition catching our batsmen, so whether a
  catch was taken by their keeper is unknown - and blank stays NULL, which
  reads as a plain catch.
"""
import argparse, collections, csv, glob, os, sys
from csfw_format import Season, INN_SLOTS

COLUMNS = [
    "game_key", "played_at", "opposition", "venue", "season_name", "grade_name",
    "is_final", "match_format", "home_team", "away_team", "winning_team", "result",
    "player_name", "innings_number", "batting_position",
    "batting_runs", "batting_balls", "batting_fours", "batting_sixes",
    "batting_not_out", "did_not_bat", "dismissal_type", "batting_caught_behind",
    "bowling_overs", "bowling_maidens", "bowling_runs", "bowling_wickets",
    "bowling_wides", "bowling_no_balls",
    "fielding_catches", "fielding_catches_wk", "fielding_run_outs", "fielding_stumpings",
]

RESULT = {0: 'WIN', 1: 'LOSS', 2: 'DRAW', 6: 'TIE'}
DISMISSAL = {0: 'bowled', 1: 'caught', 2: 'lbw', 3: 'stumped', 4: 'run out',
             10: 'retired', 11: 'not out', 12: 'not out'}


def season_name(year):
    y = int(year)
    return f"Summer {y}/{(y + 1) % 100:02d}"


def person(season, pid):
    p = season.players.get(pid)
    if not p: return None
    return f"{p['surname']}, {p['initials']}".rstrip(', ').strip()


def blank(v):
    return '' if v is None else v


def rows_for_file(path):
    """Yield (year, row-dict) for every performance in one .av file."""
    S = Season(path)
    key = os.path.splitext(os.path.basename(path))[0]
    sname = season_name(S.year)
    for k in range(INN_SLOTS // 2):
        for slot in (2 * k, 2 * k + 1):
            if slot >= INN_SLOTS: continue
            inn = S.innings(slot)
            if not inn['performances']: continue
            base = dict(
                game_key=f"{key}-{k:03d}",
                played_at=inn['date'].isoformat() if inn['date'] else '',
                opposition=inn['opposition'].rstrip(' 12').strip(),
                venue=inn['venue'], season_name=sname, grade_name='',
                is_final='', match_format='', home_team='', away_team='',
                winning_team=(S.club if inn['result'] == 'won' else
                              inn['opposition'].rstrip(' 12').strip()
                              if inn['result'] == 'lost' else ''),
                result=RESULT.get(inn['result_code'], ''))
            we_batted = inn['us']['total'] is not None
            bat_inn = 2 * k + 1
            bowl_inn = 2 * k + 2
            for p in inn['performances']:
                name = person(S, p['player_id'])
                if not name: continue
                # our batting innings
                if we_batted:
                    r = dict(base, player_name=name, innings_number=bat_inn,
                             batting_position=blank(p['order']),
                             batting_runs=blank(p['runs']),
                             batting_balls=blank(p['balls']),
                             batting_fours=blank(p['fours']),
                             batting_sixes=blank(p['sixes']),
                             batting_not_out='true' if p['not_out'] else 'false',
                             did_not_bat='false' if p['batted'] else 'true',
                             dismissal_type=('' if not p['batted']
                                             else DISMISSAL.get(p['how_out_code'], '')),
                             batting_caught_behind='')
                    yield S.year, r
                # our bowling and fielding happen during THEIR innings
                fielding = (p['catches'], p['catches_wk'], p['stumpings'])
                if p['bowled'] or any(fielding):
                    r = dict(base, player_name=name, innings_number=bowl_inn,
                             bowling_overs=blank(p['overs']),
                             bowling_maidens=blank(p['maidens']),
                             bowling_runs=blank(p['conceded']),
                             bowling_wickets=blank(p['wickets']),
                             bowling_wides=blank(p['wides']),
                             bowling_no_balls=blank(p['no_balls']),
                             fielding_catches=blank(p['catches']),
                             fielding_catches_wk=blank(p['catches_wk']),
                             fielding_run_outs='',   # CSFW does not credit these
                             fielding_stumpings=blank(p['stumpings']))
                    yield S.year, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('-o', '--out', default='manual_games')
    ap.add_argument('--max-mb', type=float, default=6.0,
                    help='split a season sheet above this size (importer caps at 8 MB)')
    a = ap.parse_args()
    paths = [p for p in sorted(glob.glob(os.path.join(a.src, '*.av')))
             if not os.path.basename(p).startswith('._')]
    os.makedirs(a.out, exist_ok=True)

    by_year = collections.defaultdict(list)
    for path in paths:
        try:
            for year, row in rows_for_file(path):
                by_year[year].append(row)
        except Exception as e:
            print(f'  !! {path}: {e}', file=sys.stderr)

    written = []
    for year in sorted(by_year):
        rows = by_year[year]
        chunks = [rows]
        # split on game_key boundaries so a match is never cut in half
        while True:
            over = [c for c in chunks if len(c) > 40000]
            if not over: break
            new = []
            for c in chunks:
                if len(c) <= 40000: new.append(c); continue
                mid = len(c) // 2
                while mid < len(c) and c[mid]['game_key'] == c[mid - 1]['game_key']:
                    mid += 1
                new += [c[:mid], c[mid:]]
            chunks = new
        for n, chunk in enumerate(chunks, 1):
            suffix = '' if len(chunks) == 1 else f'-part{n}'
            fn = os.path.join(a.out, f'manual_games_{year}{suffix}.csv')
            with open(fn, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction='ignore')
                w.writeheader()
                for r in chunk:
                    w.writerow({c: r.get(c, '') for c in COLUMNS})
            written.append((fn, len(chunk), os.path.getsize(fn)))

    total = sum(n for _, n, _ in written)
    big = [f for f, _, s in written if s > a.max_mb * 1024 * 1024]
    print(f'{len(paths)} .av files -> {len(written)} sheets, {total} rows')
    print(f'  largest sheet: {max(s for _, _, s in written)/1024:.0f} KB'
          f'  ({len(big)} over {a.max_mb} MB)')
    print(f'  -> {a.out}/')


if __name__ == '__main__':
    main()
