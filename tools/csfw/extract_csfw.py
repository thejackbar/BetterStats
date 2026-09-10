#!/usr/bin/env python3
"""
Extract every match, innings and player performance from a directory of CSFW
`.av` season databases into flat CSVs (and optionally JSON).

    python3 extract_csfw.py <dir-of-.av-files> -o out/

Writes: seasons.csv, players.csv, matches.csv, innings.csv,
        batting.csv, bowling.csv, fielding.csv, fall_of_wickets.csv
"""
import argparse, csv, glob, json, os, sys
from csfw_format import Season, NOT_OUT_CODES


def season_key(path):
    """A CSFW file has no team/grade field, so identity is (club, year, file)."""
    b = os.path.basename(path)
    return os.path.splitext(b)[0]


def extract(paths, outdir, write_json=False):
    os.makedirs(outdir, exist_ok=True)
    o = lambda n: open(os.path.join(outdir, n), 'w', newline='', encoding='utf-8')

    fh = {n: o(n + '.csv') for n in
          ('seasons', 'players', 'matches', 'innings', 'batting', 'bowling',
           'fielding', 'fall_of_wickets')}
    w = {}
    w['seasons'] = csv.writer(fh['seasons']); w['seasons'].writerow(
        ['season_key', 'file', 'club', 'year', 'players_per_side', 'balls_per_over',
         'num_players', 'num_matches', 'notes'])
    w['players'] = csv.writer(fh['players']); w['players'].writerow(
        ['season_key', 'player_id', 'surname', 'initials', 'alt_initials'])
    w['matches'] = csv.writer(fh['matches']); w['matches'].writerow(
        ['season_key', 'match_index', 'match_no', 'date', 'opposition', 'venue',
         'result', 'result_code', 'margin_runs', 'margin_wickets',
         'players_per_side', 'balls_per_over', 'notes'])
    w['innings'] = csv.writer(fh['innings']); w['innings'].writerow(
        ['season_key', 'match_index', 'innings_slot', 'side', 'total', 'wickets',
         'overs', 'byes', 'leg_byes', 'wides', 'no_balls', 'penalties', 'extras'])
    w['batting'] = csv.writer(fh['batting']); w['batting'].writerow(
        ['season_key', 'match_index', 'innings_slot', 'player_id', 'player',
         'order', 'runs', 'balls', 'minutes', 'fours', 'sixes', 'not_out',
         'how_out', 'how_out_code', 'captain', 'keeper'])
    w['bowling'] = csv.writer(fh['bowling']); w['bowling'].writerow(
        ['season_key', 'match_index', 'innings_slot', 'player_id', 'player',
         'overs', 'balls_bowled', 'maidens', 'runs', 'wickets', 'wides', 'no_balls',
         'bowling_order'])
    w['fielding'] = csv.writer(fh['fielding']); w['fielding'].writerow(
        ['season_key', 'match_index', 'innings_slot', 'player_id', 'player',
         'catches', 'catches_wk', 'stumpings', 'byes_conceded', 'keeper'])
    w['fall_of_wickets'] = csv.writer(fh['fall_of_wickets']); w['fall_of_wickets'].writerow(
        ['season_key', 'match_index', 'innings_slot', 'wicket', 'score', 'batsman_order'])

    stats = dict(files=0, matches=0, innings=0, batting=0, bowling=0, players=0)
    blob = []
    for path in paths:
        try:
            S = Season(path)
        except Exception as e:
            print(f'  !! {path}: {e}', file=sys.stderr); continue
        sk = season_key(path)
        stats['files'] += 1
        ms = list(S.matches())
        w['seasons'].writerow([sk, os.path.basename(path), S.club, S.year,
                               S.per_side, S.balls_over, len(S.players), len(ms), S.notes])
        for p in sorted(S.players.values(), key=lambda x: x['id']):
            w['players'].writerow([sk, p['id'], p['surname'], p['initials'], p['alt_initials']])
            stats['players'] += 1
        for m in ms:
            stats['matches'] += 1
            first = m['innings'][0]
            w['matches'].writerow([sk, m['match_index'], first['match_no'], m['date'],
                                   m['opposition'], m['venue'], m['result'],
                                   first['result_code'], m['margin_runs'], m['margin_wickets'],
                                   first['per_side'], first['balls_over'], first['notes']])
            for inn in m['innings']:
                stats['innings'] += 1
                for side in ('us', 'them'):
                    t = inn[side]
                    if t['total'] is None and t['overs'] is None: continue
                    w['innings'].writerow([sk, m['match_index'], inn['index'], side,
                        t['total'], t['wickets'], t['overs'], t['byes'], t['leg_byes'],
                        t['wides'], t['no_balls'], t['penalties'], t['extras']])
                for j, (sc, bo) in enumerate(inn['fall_of_wickets'], 1):
                    w['fall_of_wickets'].writerow([sk, m['match_index'], inn['index'], j, sc, bo])
                for p in inn['performances']:
                    if p['batted']:
                        stats['batting'] += 1
                        w['batting'].writerow([sk, m['match_index'], inn['index'],
                            p['player_id'], p['name'], p['order'], p['runs'], p['balls'],
                            p['minutes'], p['fours'], p['sixes'], int(p['not_out']),
                            p['how_out'], p['how_out_code'], int(p['captain']), int(p['keeper'])])
                    if p['bowled']:
                        stats['bowling'] += 1
                        w['bowling'].writerow([sk, m['match_index'], inn['index'],
                            p['player_id'], p['name'], p['overs'], p['balls_bowled'],
                            p['maidens'], p['conceded'], p['wickets'], p['wides'], p['no_balls'],
                            p['bowling_order']])
                    if any(p[k] for k in ('catches', 'catches_wk', 'stumpings', 'byes_conceded')):
                        w['fielding'].writerow([sk, m['match_index'], inn['index'],
                            p['player_id'], p['name'], p['catches'], p['catches_wk'],
                            p['stumpings'], p['byes_conceded'], int(p['keeper'])])
        if write_json:
            blob.append(dict(season_key=sk, club=S.club, year=S.year,
                             players=list(S.players.values()), matches=ms))
    for f in fh.values(): f.close()
    if write_json:
        with open(os.path.join(outdir, 'csfw.json'), 'w', encoding='utf-8') as f:
            json.dump(blob, f, default=str, indent=1)
    return stats


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('src'); ap.add_argument('-o', '--out', default='out')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    paths = sorted(glob.glob(os.path.join(a.src, '*.av')))
    paths = [p for p in paths if not os.path.basename(p).startswith('._')]
    print(f'reading {len(paths)} files from {a.src}')
    st = extract(paths, a.out, a.json)
    print('  ' + '  '.join(f'{k}={v}' for k, v in st.items()))
    print(f'  -> {a.out}/')
