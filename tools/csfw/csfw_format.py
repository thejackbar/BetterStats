"""
Reader for Cricket Statistics for Windows (CSFW) `.av` season databases.

CSFW is a VB6 shareware package by Grahame Giddings (clubcricketsoftware.co.uk).
A `.av` file is ONE season for ONE club "database" and is always exactly
549,871 bytes: a single VB6 user-defined type written with `Put`, so every
field is packed with no alignment padding and every array is fixed-length.

Conventions used throughout the file:
  * Fixed-length strings are space-padded, code page 1252.
  * Integer (int16) -1 means "not recorded" / empty slot. VB6 True is also -1.
  * Currency (int64 scaled by 10,000) holds cricket-notation overs, so 6.3
    means 6 overs 3 balls. -1.0 means "did not bowl".
  * Dates are VB6 Doubles: days since 1899-12-30.

See CSFW_FORMAT.md for the derivation and the validation evidence.
"""
import struct, datetime

FILE_SIZE = 549871

# ---- top-level layout -------------------------------------------------------
HEADER          = 0
PLAYER_TBL      = 309;    PLAYER_REC     = 37;   PLAYER_SLOTS = 200
PLAYER_DETAIL   = 7709;   PLAYER_DET_REC = 578
INN_SUMMARY     = 123309; INN_SUM_REC    = 54
INN_DETAIL      = 131840; INN_DET_REC    = 2612; INN_SLOTS    = 160
PERF_OFF        = 867;    PERF_REC       = 116;  PERF_SLOTS   = 15

EPOCH = datetime.date(1899, 12, 30)

# ---- innings-detail field offsets (relative to the innings record) ----------
I_TIME      = 111   # Double  - start time (fraction of a day)
I_VENUE     = 143   # Str*30
I_NOTES     = 345   # Str*~60 free text ("2 day match played on ...")
I_PERSIDE   = 341   # int16   - players per side for this match
I_BALLSOVER = 343   # int16   - balls per over for this match
I_RESULT    = 607   # int16   - 0 won, 1 lost, 2 drawn, 6 tied (see RESULTS)
I_MARGIN_W  = 609   # int16   - winning/losing margin in wickets
I_MARGIN_R  = 611   # int16   - winning/losing margin in runs
I_US        = 613   # innings-total block for our club
I_THEM      = 685   # innings-total block for the opposition
I_FOW       = 757   # 11 x (int16 score, int16 1-based batsman index)

# innings-total block, relative to I_US / I_THEM
T_TOTAL = 0; T_WKTS = 2; T_OVERS = 6      # Currency
T_BYES = 14; T_LEGBYES = 16; T_WIDES = 18; T_NOBALLS = 20; T_PENS = 22

# ---- performance record field offsets (relative to the 116-byte record) -----
P_PLAYER   = 0    # int16 player id
P_ORDER    = 2    # int16 batting order (0-based)
P_CAPTAIN  = 4    # bool  -1 = captain
P_KEEPER   = 6    # bool  -1 = wicketkeeper
P_RUNS     = 8    # int16 runs (-1 = did not bat)
P_NOTOUT   = 10   # bool  -1 = not out
P_SIXES    = 12
P_FOURS    = 14
P_MINUTES  = 16
P_BALLS    = 18
P_HOWOUT   = 20   # int16 dismissal code (see DISMISSALS)
P_BOWLORDER= 22   # int16 order this player came on to bowl (1..n)
P_OVERS    = 24   # Currency, cricket notation
P_MAIDENS  = 32
P_WICKETS  = 34
P_WBOWLED  = 36   # wicket-type breakdown, almost never recorded
P_WCAUGHT  = 38
P_WLBW     = 40
P_CONCEDED = 46
P_WIDES    = 48   # wides conceded by this bowler
P_NOBALLS  = 50   # no-balls conceded by this bowler
P_CATCHES  = 52   # outfield catches
P_CATCHES_WK = 56 # catches taken as wicketkeeper
P_STUMPING = 60
P_BYES     = 64   # byes conceded while keeping

RESULTS = {0: 'won', 1: 'lost', 2: 'drawn', 6: 'tied'}
# Confirmed by frequency + the not-out flag cross-check. 12/13/37 pair with the
# not-out flag or are too rare to name confidently; left as codes.
DISMISSALS = {0: 'bowled', 1: 'caught', 2: 'lbw', 3: 'stumped', 4: 'run out',
              10: 'retired', 11: 'not out', 12: 'not out (2)'}
NOT_OUT_CODES = {11, 12}


def i16(d, p): return struct.unpack('<h', d[p:p + 2])[0]
def cur(d, p): return struct.unpack('<q', d[p:p + 8])[0] / 10000.0
def dbl(d, p): return struct.unpack('<d', d[p:p + 8])[0]
def txt(d, p, n): return d[p:p + n].decode('cp1252', 'replace').rstrip()
def opt(v): return None if v == -1 else v


def overs_to_balls(overs, balls_per_over):
    """6.3 with 6-ball overs -> 39 balls. CSFW stores overs in cricket notation."""
    if overs is None or overs < 0: return None
    whole = int(overs)
    part = int(round((overs - whole) * 10))
    return whole * balls_per_over + part


class Season:
    """One CSFW `.av` file: a club-season database."""

    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as fh:
            self.d = fh.read()
        if len(self.d) != FILE_SIZE:
            raise ValueError(f'{path}: expected {FILE_SIZE} bytes, got {len(self.d)}')
        d = self.d
        self.club        = txt(d, 0, 30)
        self.year        = txt(d, 30, 4)
        self.start_time  = dbl(d, 37)
        self.per_side    = i16(d, 45)
        self.balls_over  = i16(d, 47)
        self.notes       = txt(d, 55, 254)
        self.players     = self._players()

    # -- players --------------------------------------------------------------
    def _players(self):
        d, out = self.d, {}
        for k in range(PLAYER_SLOTS):
            o = PLAYER_TBL + k * PLAYER_REC
            pid = i16(d, o + 2)
            if pid == -1: continue
            out[pid] = dict(id=pid, slot=k,
                            surname=txt(d, o + 4, 16),
                            initials=txt(d, o + 20, 3),
                            alt_initials=txt(d, o + 23, 14),
                            detail=txt(d, PLAYER_DETAIL + k * PLAYER_DET_REC + 2, 576))
        return out

    def player_name(self, pid):
        p = self.players.get(pid)
        if not p: return None
        return (p['initials'] + ' ' + p['surname']).strip()

    # -- innings --------------------------------------------------------------
    def _totals(self, o, base):
        d = self.d
        b = dict(total=opt(i16(d, o + base + T_TOTAL)),
                 wickets=opt(i16(d, o + base + T_WKTS)),
                 overs=(lambda v: None if v < 0 else v)(cur(d, o + base + T_OVERS)),
                 byes=opt(i16(d, o + base + T_BYES)),
                 leg_byes=opt(i16(d, o + base + T_LEGBYES)),
                 wides=opt(i16(d, o + base + T_WIDES)),
                 no_balls=opt(i16(d, o + base + T_NOBALLS)),
                 penalties=opt(i16(d, o + base + T_PENS)))
        b['extras'] = sum(v for k, v in b.items()
                          if k in ('byes', 'leg_byes', 'wides', 'no_balls', 'penalties') and v)
        return b

    def innings(self, i):
        """One innings slot. Slots come in pairs: 2k and 2k+1 are the two
        innings of match k (a 2-innings-per-side database)."""
        d, o = self.d, INN_DETAIL + i * INN_DET_REC
        s = INN_SUMMARY + i * INN_SUM_REC
        dv = dbl(d, s + 4)
        date = EPOCH + datetime.timedelta(days=dv) if 1000 < dv < 80000 else None
        r = dict(index=i, match_no=opt(i16(d, s + 20)), date=date,
                 opposition=txt(d, s + 22, 32),
                 venue=txt(d, o + I_VENUE, 30), notes=txt(d, o + I_NOTES, 60),
                 per_side=i16(d, o + I_PERSIDE), balls_over=i16(d, o + I_BALLSOVER),
                 result=RESULTS.get(i16(d, o + I_RESULT)),
                 result_code=i16(d, o + I_RESULT),
                 margin_runs=opt(i16(d, o + I_MARGIN_R)),
                 margin_wickets=opt(i16(d, o + I_MARGIN_W)),
                 us=self._totals(o, I_US), them=self._totals(o, I_THEM))
        r['fall_of_wickets'] = [
            (i16(d, o + I_FOW + 4 * j), i16(d, o + I_FOW + 2 + 4 * j))
            for j in range(11)
            if i16(d, o + I_FOW + 4 * j) != -1 and i16(d, o + I_FOW + 2 + 4 * j) != -1]
        r['performances'] = self._perfs(o, r['balls_over'])
        return r

    def _perfs(self, o, bpo):
        d, out = self.d, []
        for k in range(PERF_SLOTS):
            b = o + PERF_OFF + k * PERF_REC
            pid = i16(d, b + P_PLAYER)
            if pid == -1: continue
            ov = cur(d, b + P_OVERS)
            how = i16(d, b + P_HOWOUT)
            runs = opt(i16(d, b + P_RUNS))
            out.append(dict(
                player_id=pid, name=self.player_name(pid),
                order=opt(i16(d, b + P_ORDER)),
                captain=i16(d, b + P_CAPTAIN) == -1,
                keeper=i16(d, b + P_KEEPER) == -1,
                batted=runs is not None,
                runs=runs, balls=opt(i16(d, b + P_BALLS)),
                minutes=opt(i16(d, b + P_MINUTES)),
                fours=opt(i16(d, b + P_FOURS)), sixes=opt(i16(d, b + P_SIXES)),
                not_out=i16(d, b + P_NOTOUT) == -1,
                how_out=DISMISSALS.get(how), how_out_code=opt(how),
                bowled=ov >= 0,
                overs=None if ov < 0 else ov,
                balls_bowled=overs_to_balls(ov, bpo),
                maidens=opt(i16(d, b + P_MAIDENS)),
                wickets=opt(i16(d, b + P_WICKETS)),
                conceded=opt(i16(d, b + P_CONCEDED)),
                wides=opt(i16(d, b + P_WIDES)), no_balls=opt(i16(d, b + P_NOBALLS)),
                bowling_order=opt(i16(d, b + P_BOWLORDER)),
                catches=opt(i16(d, b + P_CATCHES)),
                catches_wk=opt(i16(d, b + P_CATCHES_WK)),
                stumpings=opt(i16(d, b + P_STUMPING)),
                byes_conceded=opt(i16(d, b + P_BYES))))
        return out

    def all_innings(self):
        for i in range(INN_SLOTS):
            r = self.innings(i)
            if r['us']['total'] is None and r['them']['total'] is None \
               and not r['performances']:
                continue
            yield r

    def matches(self):
        """Group innings slots into matches (slot 2k and 2k+1)."""
        inns = {r['index']: r for r in self.all_innings()}
        for k in range(INN_SLOTS // 2):
            a, b = inns.get(2 * k), inns.get(2 * k + 1)
            if not a and not b: continue
            yield dict(match_index=k, innings=[x for x in (a, b) if x],
                       date=(a or b)['date'], venue=(a or b)['venue'],
                       opposition=(a or b)['opposition'].rstrip(' 12').strip(),
                       result=(a or b)['result'],
                       margin_runs=(a or b)['margin_runs'],
                       margin_wickets=(a or b)['margin_wickets'])
