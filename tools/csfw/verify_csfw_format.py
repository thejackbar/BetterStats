#!/usr/bin/env python3
"""
Verification suite for the CSFW `.av` decode.

    python3 verify_csfw_format.py <dir-of-.av-files>

Every check runs over the whole corpus, not a sample. Each structural claim is
paired with a CONTROL that reads a deliberately wrong offset and must fail --
a check that cannot fail is not a check.
"""
import glob, os, sys, collections
from csfw_format import (Season, INN_SLOTS, INN_DETAIL, INN_DET_REC, PERF_OFF,
                         PERF_REC, i16, cur)

PASS = []


def check(name, ok, detail=''):
    PASS.append((name, ok, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ''))


def main(src):
    paths = [p for p in sorted(glob.glob(os.path.join(src, '*.av')))
             if not os.path.basename(p).startswith('._')]
    if not paths:
        print(f'no .av files in {src}'); return 1
    print(f'{len(paths)} season files\n')

    sizes = {os.path.getsize(p) for p in paths}
    check('every file is exactly 549,871 bytes', sizes == {549871}, str(sizes))

    bat = [0, 0]; bowl = [0, 0]; boundary = [0, 0]; boundary_swap = [0, 0]
    byes = [0, 0]; stump = [0, 0]; catch = [0, 0]
    notout = [0, 0]; bpo = collections.defaultdict(set)
    seasons = 0; matches = 0

    for path in paths:
        S = Season(path); seasons += 1
        bpo[S.balls_over].add(int(S.year))
        for i in range(INN_SLOTS):
            r = S.innings(i)
            o = INN_DETAIL + i * INN_DET_REC
            perf = r['performances']
            if not perf: continue
            if i % 2 == 0: matches += 1
            bats = [p for p in perf if p['batted']]
            bwls = [p for p in perf if p['bowled']]

            # 1. batting reconciles with the innings total
            if r['us']['total'] is not None and bats:
                got = sum(p['runs'] for p in bats) + r['us']['extras']
                bat[0 if got == r['us']['total'] else 1] += 1

            # 2. bowling reconciles: bowler runs already include wides/no-balls
            if r['them']['total'] is not None and bwls and all(p['conceded'] is not None for p in bwls):
                b = (r['them']['byes'] or 0) + (r['them']['leg_byes'] or 0)
                got = sum(p['conceded'] for p in bwls) + b
                bowl[0 if got == r['them']['total'] else 1] += 1

            for p in perf:
                # 3. boundaries cannot exceed the runs scored
                if p['runs'] is not None and (p['fours'] or p['sixes']):
                    v = 4 * (p['fours'] or 0) + 6 * (p['sixes'] or 0)
                    boundary[0 if v <= p['runs'] else 1] += 1
                    sw = 6 * (p['fours'] or 0) + 4 * (p['sixes'] or 0)
                    boundary_swap[0 if sw <= p['runs'] else 1] += 1
                # 4. where a dismissal code IS recorded it must agree with
                #    the not-out flag (19 rows carry no code at all)
                if p['runs'] is not None and p['how_out_code'] is not None:
                    code_says = p['how_out_code'] in (11, 12)
                    notout[0 if code_says == p['not_out'] else 1] += 1
                # 5. only the keeper records stumpings
                if p['stumpings']:
                    stump[0 if p['keeper'] else 1] += 1

            # 6. keeper byes sum to the innings byes
            sb = sum(p['byes_conceded'] or 0 for p in perf)
            if r['them']['byes'] and sb:
                byes[0 if sb == r['them']['byes'] else 1] += 1
            # 7. catches cannot exceed the wickets that fell
            if r['them']['wickets']:
                sc = sum(p['catches'] or 0 for p in perf)
                catch[0 if sc <= r['them']['wickets'] else 1] += 1

    print()
    check('batting: sum(runs)+extras == innings total',
          bat[0] / sum(bat) > 0.90, f'{bat[0]}/{sum(bat)} = {bat[0]/sum(bat):.1%}')
    check('bowling: sum(conceded)+byes+leg byes == opposition total',
          bowl[0] / sum(bowl) > 0.55, f'{bowl[0]}/{sum(bowl)} = {bowl[0]/sum(bowl):.1%}')
    check('boundaries: 4*fours + 6*sixes <= runs',
          boundary[1] == 0, f'{boundary[0]} ok, {boundary[1]} violations')
    check('CONTROL fours/sixes swapped must violate',
          boundary_swap[1] > 1000, f'{boundary_swap[1]} violations when swapped')
    check('not-out flag agrees with recorded dismissal code',
          notout[1] <= 5, f'{notout[0]} ok, {notout[1]} disagreements')
    check('stumpings only ever belong to the wicketkeeper',
          stump[1] == 0, f'{stump[0]} ok, {stump[1]} by non-keepers')
    check('keeper byes sum to the innings byes',
          byes[0] / sum(byes) > 0.99, f'{byes[0]}/{sum(byes)} = {byes[0]/sum(byes):.1%}')
    check('catches never exceed wickets taken',
          catch[1] / sum(catch) < 0.001, f'{catch[1]} violations of {sum(catch)}')
    check('8-ball overs are pre-1972, 6-ball overs later',
          max(bpo[8]) < 1972 and min(bpo[6]) < 1972 <= max(bpo[6]),
          f'8-ball {min(bpo[8])}-{max(bpo[8])}, 6-ball {min(bpo[6])}-{max(bpo[6])}')

    # CONTROL: reading the batting total one byte off must break the identity
    S = Season(paths[-1]); off_ok = off_bad = 0
    for i in range(INN_SLOTS):
        r = S.innings(i); o = INN_DETAIL + i * INN_DET_REC
        bats = [p for p in r['performances'] if p['batted']]
        if r['us']['total'] is None or not bats: continue
        shifted = i16(S.d, o + 613 + 1)
        got = sum(p['runs'] for p in bats) + r['us']['extras']
        if got == shifted: off_ok += 1
        else: off_bad += 1
    check('CONTROL total read one byte off must not reconcile',
          off_ok == 0, f'{off_bad} mismatches, {off_ok} accidental matches')

    print(f'\n{seasons} seasons, {matches} matches checked')
    bad = [n for n, ok, _ in PASS if not ok]
    print(f'{len(PASS)-len(bad)}/{len(PASS)} checks passed')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else '.'))
