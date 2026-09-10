# Cricket Statistics for Windows (`.av`) — file format

Reverse-engineered from Payneham Cricket Club's archive: 206 season databases
covering 1928–2025, plus ~40 CSV report exports and the CSFW user manual.

CSFW is VB6 shareware by Grahame Giddings (`clubcricketsoftware.co.uk`); the
archive here is **v5.00.138**. A `.av` file is one club "database" — one season
— and is always **exactly 549,871 bytes**. The manual's own packing list
confirms this: the bundled sample `OCC1991.AV` is listed at 549871 bytes.

The file is a single VB6 user-defined type written with `Put`, so it is
**packed with no alignment padding** and every array is a fixed-length slot
table. Nothing is compressed, indexed or checksummed.

## Conventions

| | |
|---|---|
| Strings | fixed-length, space-padded, code page 1252 |
| `int16` | little-endian; **-1 means "not recorded"**, and VB6 `True` is also -1 |
| `Currency` | int64 scaled by 10,000. Holds **overs in cricket notation**: `6.3` = 6 overs 3 balls. `-1.0` = did not bowl |
| `Double` | dates as days since 1899-12-30; times as a fraction of a day |

## Top-level layout

| Offset | Size | Contents |
|---|---|---|
| 0 | 309 | Header |
| 309 | 7,400 | Player name table — 200 × 37 |
| 7,709 | 115,600 | Player detail (address/contact) — 200 × 578 |
| 123,309 | 8,640 | Innings summary — 160 × 54 |
| 131,840 | 417,920 | Innings detail — 160 × 2,612 |
| 549,760 | 111 | Trailer (not decoded) |

The two player tables are parallel: slot *k* in each describes the same player.

### Header (0–308)

| Off | Type | Field |
|---|---|---|
| 0 | Str×30 | Club/team name (e.g. `Payneham`, `Payneham W`, `Payneham S J 12`) |
| 30 | Str×4 | Season start year |
| 34 | Str×1 | Always `W` in this archive |
| 37 | Double | Default match start time |
| 45 | int16 | Players per side (6–16 seen) |
| 47 | int16 | **Balls per over** (6 or 8) |
| 55 | Str×254 | Free-text season notes (nearly always blank) |

### Player name record (37 bytes)

| Off | Type | Field |
|---|---|---|
| 0 | 2 bytes | unused (spaces) |
| 2 | int16 | Player id — stable key, not the slot index |
| 4 | Str×16 | Surname |
| 20 | Str×3 | Initials |
| 23 | Str×14 | Alternate/full initials, used to separate same-surname players |

The table is sorted by surname; unused slots have id `-1`. Ids are referenced
by every performance record.

### Innings summary record (54 bytes)

| Off | Type | Field |
|---|---|---|
| 0 | int16 | unknown |
| 2 | int16 | sequence |
| 4 | Double | **Match date** |
| 12 | 8 bytes | unknown (always zero) |
| 20 | int16 | Match/round number |
| 22 | Str×32 | Opposition, with the innings number appended (`Para Hills 1`) |

### Innings detail record (2,612 bytes)

Slots come in pairs: **2k and 2k+1 are the two innings of match k** (CSFW
supports two innings per side). Each record stores *our club's* whole
contribution to that half of the match — our batting **and** our bowling.
Opposition individuals are not stored, only their team name and totals.

| Off | Type | Field |
|---|---|---|
| 111 | Double | Start time |
| 143 | Str×30 | Venue |
| 341 | int16 | Players per side (per match) |
| 343 | int16 | Balls per over (per match) |
| 345 | Str | Free-text match note (`2 day match played on …`) |
| 607 | int16 | **Result**: 0 won, 1 lost, 2 drawn, 6 tied |
| 609 | int16 | Winning/losing margin, wickets |
| 611 | int16 | Winning/losing margin, runs |
| 613 | 72 | Innings totals — **our club** |
| 685 | 72 | Innings totals — **opposition** |
| 757 | 44 | Fall of wickets: 11 × (int16 score, int16 1-based batsman index) |
| 867 | 1,740 | Performances — 15 × 116 |

#### Innings totals block (72 bytes, used twice)

| Off | Type | Field |
|---|---|---|
| +0 | int16 | Total |
| +2 | int16 | Wickets |
| +6 | Currency | Overs |
| +14 | int16 | Byes |
| +16 | int16 | Leg byes |
| +18 | int16 | Wides |
| +20 | int16 | No balls |
| +22 | int16 | Penalties |

#### Performance record (116 bytes)

One per player per innings — batting, bowling and fielding together.

| Off | Type | Field |
|---|---|---|
| 0 | int16 | Player id |
| 2 | int16 | Batting order (0-based) |
| 4 | bool | **Captain** |
| 6 | bool | **Wicketkeeper** |
| 8 | int16 | Runs (-1 = did not bat) |
| 10 | bool | Not out |
| 12 | int16 | Sixes |
| 14 | int16 | Fours |
| 16 | int16 | Minutes batted |
| 18 | int16 | Balls faced |
| 20 | int16 | Dismissal code |
| 22 | int16 | **Bowling order** (1..n, exactly sequential in 452/452 innings) |
| 24 | Currency | Overs bowled |
| 32 | int16 | Maidens |
| 34 | int16 | Wickets |
| 36/38/40 | int16 | Wicket-type breakdown (bowled/caught/lbw) — effectively never recorded |
| 42/44 | int16 | **Not identified** |
| 46 | int16 | Runs conceded |
| 48 | int16 | Wides conceded |
| 50 | int16 | No balls conceded |
| 52 | int16 | Outfield catches (only 0.5% are the keeper) |
| 56 | int16 | Catches taken keeping (100% keeper) |
| 60 | int16 | Stumpings (100% keeper) |
| 64 | int16 | Byes conceded (keeper) |
| 66–113 | 6 × Currency | Further bowling spells — almost always unset |

Dismissal codes, by frequency, with 11/12 always paired with the not-out flag:

| Code | Meaning | n |
|---|---|---|
| 1 | caught | 29,984 |
| 0 | bowled | 24,373 |
| 11 | not out | 14,247 |
| 2 | lbw | 7,260 |
| 12 | not out (second form — retired not out?) | 6,956 |
| 4 | run out | 5,414 |
| 3 | stumped | 1,847 |
| 10 | retired (mean 25 runs, 3% ducks) | 204 |
| 13, 37, 14, … | not identified | <900 each |

## Validation

Each claim below was checked against the whole 206-file corpus, not a sample.

* **Batting reconciles**: `sum(batsmen runs) + extras == innings total` for
  9,136 of 10,030 innings. Failures are concentrated in the 1940s and are
  residuals of ±1–5 — hand-entry slop, not a decode error. In the 1970s and
  1990s the identity holds for 98–99% of innings.
* **Bowling reconciles**: `sum(runs conceded) + byes + leg byes == opposition
  total`, exactly as cricket requires (wides and no-balls are already charged
  to the bowler). Holds outright for 61.5%; of the remainder, 1,664 innings
  simply have byes or leg-byes unrecorded.
* **Fours/sixes**: `4×fours + 6×sixes ≤ runs` holds for **40,742 of 40,742**
  cases (100.00%). The swapped assignment fails 9,007 times, so the two
  columns are not interchangeable.
* **Byes**: `sum(keeper byes) == innings byes` in 5,905 of 5,916 innings (99.8%).
* **Stumpings**: every one of 1,338 occurrences belongs to the flagged keeper.
* **Catches**: `sum(catches) ≤ opposition wickets` in 9,925 of 9,926 innings.
* **Balls per over** reads 8 for 1928–1971 and 6 from 1972, matching the
  `8 Ball Overs` line CSFW itself printed in the 1938 and 1970 CSV exports.
* **Result code**: value 6 is a tie in 11 of 14 occurrences; 0 and 1 predict
  win/loss at ~88% against a naive runs comparison (the gap is first-innings
  and outright results in two-day cricket).
* **Margin**: offset 611 equals `|our total − their total|` for 82% of decided
  matches; most of the rest are wicket-margin wins carried at offset 609.
* CSFW's own CSV exports list batting columns `Mch, Inn, N O, Mins, Balls,
  Runs, H S, 100s, 50s, 6s, 4s` and bowling columns `Ov, Mdn, Wkts, …, Runs,
  W, N B` — an independent confirmation of the stored per-innings fields.

## Known limitations

1. **There is no grade or team field.** A file's only team identity is the
   header club name. Payneham used one file per season for several grades at
   once: `data2024.av` holds 61 matches and 120 players, and three different
   squads played on 2024-10-12. Grade must be reconstructed by clustering on
   squads, or supplied by the club. The filename slot letter is *not* a stable
   grade key — `dat1` is the women's team in 2025 but a senior side earlier.
2. **Opposition individuals are not stored** — only the team name and innings
   totals. So "c Smith b Jones" cannot be recovered; the bowler and fielder who
   dismissed our batsmen are absent from the file.
3. **Season aggregates are not stored.** CSFW computes averages from match
   records. Where an old CSV export shows a full season but the `.av` holds one
   match (1938), the aggregates came from a database that has since been edited
   — the CSVs name players no longer in the file.
4. **Run-outs are not credited to a fielder.** A run out is visible on the
   batting side (dismissal code 4) but no per-player run-out counter was
   found, so `manual_fielding_stats.run_outs` cannot be populated.
5. Offsets 42/44 in the performance record, the 111-byte trailer, and several
   header booleans are not identified. None is needed to reconstruct a scorecard.
