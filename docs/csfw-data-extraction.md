# Cricket Statistics for Windows: extracting a club's history

How a club's Cricket Statistics for Windows (CSFW) archive is turned into
spreadsheets BetterCricket can import. Written from the Shoalwater Bay Cricket
Club conversion (15 seasons, 1992/93 to 2006/07, 914 matches), and meant to be
followed for any other club that arrives with the same files.

The working code is `tools/convert_shoalwater_av.py`. This document is the
reasoning behind it: the byte layout, the rules, the exceptions that cost
real matches when they were got wrong, and the checks that catch it.

---

## 0. Which archive has the club actually got?

Two different products turn up under names a club may use interchangeably, and
they need completely different handling. Establish which one you have before
anything else.

| | **CSFW `.AV` files** | **CricketStatz web reports** |
|---|---|---|
| What you receive | A folder of `DATA<year>.AV` binaries | A URL like `www2.cricketstatz.com/ss/w?mode=104&club=93931` |
| Era | MS-DOS / early Delphi, 1990s to mid 2000s | Current, subscription hosted |
| Reader | `tools/convert_shoalwater_av.py` | `backend/app/services/cricketstatz_*` |
| Output | Spreadsheets, imported by hand | In-app import wizard |
| Covered by | Part 1 below | Part 2 below |

**Shoalwater Bay is the `.AV` case.** Keon Park and Cockburn are the
CricketStatz case. Part 1 is the bulk of this document because the binary
format had to be reverse engineered and nothing else in this repository reads
it.

### Payneham Cricket Club

**There is no Payneham CSFW data in this repository.** No `.AV` file, no
CricketStatz club id, no conversion output. The only mention of Payneham
anywhere in the codebase is a Cricket Australia sync fix (the retired-not-out
work in v9.66.0, which is about a live PlayHQ feed and has nothing to do with
CSFW).

So either Payneham's files have not been supplied yet, or a different club was
meant. When they arrive, run the checklist in section 10: nothing in the
converter is specific to Shoalwater Bay beyond the club name it reads out of
the file header.

---

# Part 1: the `.AV` binary format

## 1. Identifying the files

A CSFW season is one `DATA<year>.AV` file of **exactly 549,871 bytes**. The
converter refuses anything else rather than reading it wrongly, because every
offset below is fixed and a short file means a different version of the format.

The same folder usually holds siblings for the same seasons:

| Extension | What it is | Used? |
|---|---|---|
| `.AV` | The complete club averages database | **Yes, this is the source** |
| `.PLR` | Players, with ids stable across seasons | Cross-check only |
| `.FIX` | Fixtures | Cross-check only |
| `.MCH` | Matches | Cross-check only |
| `.DAT` | Blank in every file seen | Ignored |
| `.HIS`, `.FAN`, `.000` | Present in some seasons, not decoded | Ignored |

**The `.AV` is a complete, self-consistent export of the others**, verified
against the 1993 set: its fixtures agree with `.FIX` on date, team and opponent
for all 41 shared slots, and its scorelines agree with `.MCH` on all 35. It
renumbers the players (`.PLR` keeps ids stable across seasons, the `.AV` does
not), but its match blocks use its own numbering throughout, so resolving
through its own embedded roster names the same eleven in the same order.

**Read the `.AV` and use the siblings only to check it.** Mixing a fixture
label from one file onto a scorecard from another is how a match ends up under
the wrong date. `cross_check()` does exactly that and reports agreement counts
on a Cross-check sheet.

**File names are not reliably uppercase.** Shoalwater's 2006 season arrived as
`data2006.av` while every other year is `DATA1999.AV`. Linux is case sensitive,
so glob on `p.suffix.lower() == ".av"` or you will silently drop a season.

## 2. File layout

Every byte of the 549,871 is accounted for:

```
offset       size                 section
0            311                  header: club name (30) + year (4) + settings
311          200 x 37             player index
7,711        200 x 578            per-player stats area (blank in every file seen)
123,311      160 x 54             fixtures
131,951      160 x 2,612          matches
```

The per-player stats region is empty because the program recomputed averages
on demand rather than storing them. Do not go looking for career figures there.

## 3. Primitives

| Type | Encoding | "Not recorded" |
|---|---|---|
| Integer | little-endian `int16` | `-1` |
| Overs, votes | Delphi `Currency`: `int64` scaled by 10,000 | `-10000` (that is, `-1.0`) |
| Date | Delphi/Excel day number, `float64` | `<= 0` |
| Text | Fixed length, latin-1 | Padded with spaces, sometimes `\x00` or `\xff` |

Epoch for dates is **1899-12-30**.

**Overs are cricket notation, never decimals.** `93.3` is 93 overs and 3 balls.
Confirmed against the data: the fractional digit is never above 5. Anything
that sums or divides overs converts to balls first
(`overs_to_balls`, `balls_to_overs`).

## 4. Section layouts

### Header (offset 0)

| Offset | Size | Field |
|---|---|---|
| 0 | 30 | Club name |
| 30 | 4 | Season start year, as text |

The rest is program settings and is not read.

### Player index (offset 311, 200 records of 37 bytes)

| Offset | Size | Field |
|---|---|---|
| 0 | 2 | Player id (`int16`, `-1` = empty slot) |
| 2 | 16 | Surname |
| 18 | 3 | Initial |
| 21 | 16 | First name |

Displayed as `"Surname, First"`, which is the shape BetterCricket's own name
matcher reads best. **Player ids are per season**, not stable across files, so
a player is identified by name when rolling seasons together.

### Fixtures (offset 123,311, 160 records of 54 bytes)

| Offset | Size | Field |
|---|---|---|
| 0 | 2 | **Match slot this fixture points at** |
| 2 | 8 | Date, `float64` day number |
| 18 | 2 | Team number (the grade) |
| 20 | 32 | Opponent name |

**The single most damaging trap in the format.** The fixture array is held in
date order, and each record's first field is the slot of its match record. The
two coincide only when the fixtures happened to be entered in slot order, which
is true of 1992 and of no other season. Reading the array position instead of
the stored slot pairs a scorecard with a different match's date, opponent and
team.

The tell is that the stored slots are a permutation of `0..n-1` rather than a
run. `parse_fixtures()` therefore keys its result on the slot the fixture
points at, never on its own position.

### Matches (offset 131,951, 160 records of 2,612 bytes)

| Offset | Size | Field |
|---|---|---|
| 10 | 20 | Round label |
| 30 | 2 | Ground index |
| 32 | 30 | Ground name |
| **496** | 1 | **The club's own recorded result** (see section 5) |
| 502 | 72 | Our innings block |
| 574 | 72 | Their innings block |
| 646 | 40 | Fall of wickets: 10 pairs of (score, batting position) |
| 756 | 16 x 116 | Player blocks |

Slot A at 502 is **always our own club's innings**, never the home side's.

Fall-of-wicket batting positions are 1-indexed and a score of `-1` ends the
list.

### Innings block (72 bytes)

| Offset | Field |
|---|---|
| 0 | Total |
| 2 | Wickets |
| 4 | Innings number |
| 6 | Overs (`Currency`) |
| 14, 16, 18, 20, 22 | Byes, leg byes, wides, no balls, penalty |

An innings counts as played when its total is present and non-negative.

### Player block (116 bytes, 16 per match)

| Offset | Field |
|---|---|
| 0 | Player id (`-1` or `>= 200` means empty slot) |
| 2 | Batting position (`255` or `-1` means did not bat; stored 0-indexed) |
| 8 | Runs |
| 12 | Sixes |
| 14 | Fours |
| 20 | Dismissal code (see section 5) |
| 24 | Overs bowled (`Currency`) |
| 32 | Maidens |
| 34 | Wickets |
| 42 | Bowling flags (unidentified bitmask, passed through raw) |
| 46 | Runs conceded |
| 48 | Wides |
| 50 | No balls |
| 52 | Catches |
| 56 | Keeper catches |
| 60 | Stumpings |
| 64 | Byes conceded |
| 82 | Award votes (`Currency`) |

A player **batted** when runs are present, and **bowled** when overs are
present. Both can be absent while the block still exists, which is how a named
side with no figures is stored (see section 6).

**Only this club's own players are ever in these blocks.** The program never
stored the opposition's names, so there are no opposition batting or bowling
cards anywhere in the format, only their innings totals.

## 5. The two vocabularies, and how each was proved

Nothing here was assumed from the numbers looking plausible. Each mapping was
either forced by the data's own arithmetic or confirmed by the club.

### Dismissal codes (player block offset 20)

```python
DISMISSALS = {0: "Bowled", 1: "Caught", 2: "LBW", 3: "Stumped",
              4: "Run out", 7: "Hit wicket", 10: "Retired out",
              13: "Caught and bowled", 14: "Caught behind",
              15: "Caught", 29: "Absent", 37: "Caught behind",
              11: "Not out", 12: "Not out (retired)"}
```

**The not-out codes are proved, not guessed, and the proof also settles every
other code.** Count the dismissed batters in an innings and compare against
that innings' own wickets figure. Treating only 11 as a not out balances 908 of
916 innings. Adding 12 (8 innings across fifteen seasons) balances **916 of
916**, and those 8 are exactly the 8 failures. Every other candidate makes the
identity worse, which means 7, 10, 13, 14, 15, 29 and 37 were all genuine
dismissals before anybody knew what a single one of them was called. Do this
first at a new club: it settles the whole vocabulary in one pass, and it is
what the club's own answers are then checked against.

**Code 10 is retired OUT and must stay a dismissal.** Law 25.4.3's retirement
without the opposing captain's consent is a genuine wicket credited to no
bowler. Read as a not out, 11 innings stop balancing. This is the same
distinction `backend/app/services/dismissal.py` keeps on the application side.

Codes 0 to 4 are corroborated by counting an independent population in the same
files: our batters were run out 443 times against 404 wickets we took that were
not credited to a bowler, and stumped 196 times against 234 stumpings by our
own keepers. The resulting shares are ordinary club rates (caught 47.6%, bowled
27.0, LBW 8.9, run out 6.1, stumped 2.5).

Seven more were **confirmed by the club from its own records**: 7 hit wicket,
10 retired out, 13 caught and bowled, 14 and 37 caught by the keeper, 15 caught
in slips, and **29 absent**.

**Code 29 is Absent, and it is the one code that is a dismissal in the file and
not an innings in the app.** In the club's own words: "Most of Shoalwater Bay's
games are one day fixtures, so I believe it is where a player was selected, and
is either running late, or didn't turn up, or had to leave early. In some
instances where Shoalwater Bay batted first, and the absent batter arrived
after the close of our innings."

All seven rows across fifteen seasons agree with that, and they were read out
of the files before the label was accepted rather than after: every one is at
batting position 10 or 11, every one is 0, and **three of the seven bowled in
that same match**, which is the club's "arrived after the close of our innings"
showing up in the data. Every one of those innings is all out with exactly ten
dismissed batters.

**So 29 stays a dismissal on the CSFW side, and imports as a did-not-bat.** The
file counts the absent batter among the ten wickets, so reading the code as a
not out breaks the wickets identity: **911 of 916 rather than 916 of 916**,
measured by running it that way rather than reasoned about. It costs five
innings and not seven because two pairs of absent batters share an innings
between them.

Nobody faced a ball, though, so importing a real 0-run innings would hand a
duck to a player who was not there. The row carries `did_not_bat = true`, no
batting figures, and `dismissal_type = absent`. **Both halves are needed,
because the app's two readers filter differently.** Every batting average in
`aggregations.py` excludes it by the WORD
(`LOWER(dismissal_type) NOT IN ('absent', 'did not bat', 'dnb')`), while
`get_dismissal_breakdown`, the How I Get Out donut, has no such word filter and
would draw "absent" as its own slice, so it is excluded by the FLAG instead.
Being absent is not a way of getting out, the same call this app already makes
for a retirement.

**The import shape is the one the Cricket Australia sync already writes**, and
that is a check rather than a coincidence: `sync.py` stores an absent batter as
`did_not_bat=True` with `runs=None`, so a scorecard can still list them while
no innings count or average can reach them. The converter lands on the same
row from the other direction.

**Where the two DO diverge is the wicket, and both are right.** CA's feed never
counts an absent batter among the wickets (`sync._NON_WICKET_DT` holds
"absent"), so nothing on that side has to reconcile. CSFW's own bookkeeping
does count them, so the converter's wickets identity needs the code to stay a
dismissal. Expect the same in another club's archive: reconcile a code against
the innings wickets to decide whether it is a dismissal, and read the club's
word for it to decide what to import, and do not let either answer overrule the
other.

**A code confirmed by a club is still worth checking against the files.** Every
one of the seven above sits where an absent batter would sit and behaves how an
absent batter would behave. Had they been spread through the top order, or had
none of them bowled, the label would have needed another question rather than
an import.

**Caught behind is a floor, not a count.** Codes 14 and 37 appear 454 times
against our batters, while our own keepers took 958 catches over the same
fifteen seasons. A scorer filling in our batting card reached for a specific
code about half the time and plain "caught" the rest. The meaning is right, the
number is under-recorded, and the Notes sheet says so.

### Result codes (match record offset 496)

```python
RESULT_LABELS = {0: "Won", 1: "Lost", 2: "Drawn", 3: "Tied", 4: "Abandoned"}
```

**Found by scanning every byte of the match record against the outcome the
scores imply**, then confirmed outright: across all 914 matches the field takes
exactly five values, and their counts are exactly the five lines of the club's
own CSFW summary screen (467 won, 433 lost, 3 drawn, 3 tied, 8 abandoned). Five
values, five categories, five exact counts.

3 is tied and 2 is drawn, which the counts alone cannot settle since both are
3. The scores do: every match carrying a 3 has our total equal to theirs, and
no scored match carries a 2 at all. 4 is corroborated the same way, since half
the 4s are scored matches where the club was 15 or 9 all out against 195, which
is what an abandoned innings looks like.

**This field is authoritative over the scoreline.** A club wins on first
innings, loses a two-day match it out-scored, or has a game abandoned mid
innings, and the scores alone say none of that. The 11 matches where the two
disagree are reported by `verify()` rather than quietly resolved either way.

**The byte offset is not guaranteed to be 496 in another club's files** if the
program version differs. Re-run the correlation scan (section 10, step 3)
before trusting it.

## 6. The rules, and the exceptions that cost real matches

These are the parts that were wrong at some point in the build and had to be
found by measurement.

### Every fixture-backed record is a match the club counts

An earlier cut skipped a match record that had no innings and no batting or
bowling, reading it as a fixture nobody ever filled in. **That dropped 17 real
matches**: 10 won by forfeit, 3 drawn and 4 abandoned, none of which produces a
figure to record. It was the difference between 897 matches and the club's own
914.

A match with a result and no figures is still a match. Keep it.

### A two-day match is two records

Seasons up to 1997 store a match as two fixture records named `"Opponent 1"`
and `"Opponent 2"`, sharing a date and a team number. These are the two legs of
one match, not two opponents and not the grade.

`split_leg()` strips the suffix **only where the sibling leg is actually
present**, so an opponent whose real name genuinely ends in a digit is left
alone.

`group_legs()` then groups on `(date, team, opponent)`. Every reader has to
count that as one match or the games-played figure doubles.

### A blank second leg is not an innings, unless every leg is blank

This is the sharpest rule in the converter and it was got wrong twice.

**231 of Shoalwater's matches have a blank second day**: the side is named
again, the game was settled on day one, and no figures were ever entered.
Emitting that leg gives all eleven players a second, invented "did not bat"
innings on top of the runs they really made. Removing the skip described above
inflated the Matches sheet from 936 rows to 1,187 for exactly this reason.

But a match whose **every** leg is blank is a different thing. It is a match
the club played and counts, and it must not disappear for want of a scorecard.
Those keep **one** leg, because the two records name the same eleven and taking
both would count that side twice. Confirmed by checking the three blank two-leg
matches: they name identical XIs.

```python
def leg_has_card(leg) -> bool:
    return leg["has_play"] or any(b["batted"] or b["bowled"] for b in leg["blocks"])

def match_legs(legs: list) -> list:
    scored = [l for l in legs if leg_has_card(l)]
    return scored or legs[:1]
```

**`match_legs()` is the one definition.** Every consumer goes through it:
`build_rows`, `build_season_stats`, `build_game_rows` and `verify`. Two copies
of this rule is how the workbook and the import CSV start disagreeing about how
many games a player played.

### Grade comes from the team number, and has no name

The fixture record carries a team number, not a grade name. The format holds no
grade names at all, so grades come out as `"Grade 1"` through `"Grade 4"` and
can be renamed at import time.

**1992 stores 2 for every fixture**, which may be a program default rather than
a real team number. Worth flagging to the club rather than presenting as fact.

### Blank is not zero

Balls faced, batting strike rate, run outs, and the bowler or fielder credited
with a wicket are **not in the format at all**. They are left blank, never
zeroed. A zero would read as a recorded nought, which is a different claim.

### One person, two grades on one day

Nobody plays two matches on one afternoon, so where the files name one person
in two grades on one date, either the grade is wrong or the stored date is a
round stamp shared by competitions that ran on different days. The files cannot
tell us which, and the figures are sound either way since every innings still
reconciles to its own total.

`squad_clashes()` lists them on a Data quality sheet rather than silently
dropping or silently keeping them. For Shoalwater this is 4 rows out of 9,384
player-dates. Squads for different grades on one day do not overlap at all, and
a player spends a median 93% of a season in one grade, so the grade split can
be trusted.

## 7. Verification

`verify()` checks the decode against the data's own arithmetic, never against
itself. Shoalwater's results:

| Check | Result |
|---|---|
| Batting runs + extras equal the innings total | 824 / 916 (90.0%) |
| Batters dismissed equal the innings wickets | 916 / 916 (100%) |
| Bowlers' runs equal their total less byes and leg byes | 720 / 898 (80.2%) |
| Bowlers' wickets never exceed the innings wickets | 916 / 917 (99.9%) |
| 4s and 6s never account for more than the runs scored | 9180 / 9180 (100%) |
| Award votes add up to 3-2-1 | 114 / 116 (98.3%) |
| The card's own result agrees with the scoreline | 883 / 894 (98.8%) |

**Where a check falls short, the shortfall is in the club's own figures rather
than the conversion.** The residuals are ones and twos, the usual slips in a
hand-kept scorebook. Nothing is corrected. The 100% on wickets and boundaries
is what proves the decode itself is right: a wrong offset would fail those, not
scatter ones and twos through the totals.

The result check is not an error when it differs. A first-innings win, a
forfeit and a match abandoned partway all read as something else on runs alone,
so a disagreement is counted rather than resolved.

## 8. Outputs

The converter writes three files:

| File | What it is |
|---|---|
| `match_detail.xlsx` | The full archive as sheets: Notes, Matches, Batting, Bowling, Fielding, Fall of wickets, Votes, Players, Data quality, Cross-check |
| `manual_games_scorecards.csv` | **The one to import.** One row per player per match, in the Manual Games importer's columns |
| `betterimport_season_stats.csv` | The simpler alternative: season totals per player, no match detail |

**Import one of the two CSVs, never both**, or the same runs are counted twice.
The scorecard CSV is the richer route: it lands real match records, so match
pages, partnerships and fall of wickets all work.

Both CSVs are written **utf-8-sig** (with a byte order mark), which is what the
importer reads. Anything reading them back has to use `encoding="utf-8-sig"` or
the first column header comes back with a BOM glued to it.

The Notes sheet is written first and carries every caveat above in the club's
own language. It is the part a club actually reads.

## 9. Mapping to BetterCricket

`build_game_rows()` emits the Manual Games importer's columns
(`GAME_CSV_COLUMNS`). The parts worth knowing:

### Use the app's own vocabularies, not human-readable words

**This was a live bug.** The first cut emitted `Won` / `Lost` / `Tie`, while
every reader in the application compares against `WIN` / `LOSS` / `DRAW` /
`TIE` (see `aggregations._club_results`). A human-readable "Won" matches none of
them, so the club's dashboard read **0 wins and 0 losses** off a correctly
converted archive.

```python
IMPORT_RESULTS = {0: "WIN", 1: "LOSS", 2: "DRAW", 3: "TIE", 4: ""}
IMPORT_DISMISSALS = {0: "b", 1: "c", 2: "lbw", 3: "st", 4: "run out",
                     7: "hit wicket", 10: "retired out",
                     13: "c & b", 14: "c", 15: "c", 37: "c"}
```

Dismissals have the same trap. The How I Get Out donut classifies by
`dismissal_type = 'c'` and `LIKE 'c %'`, case sensitively, so a
human-readable "Caught" falls through to the ELSE branch and becomes its own
slice sitting beside the real one.

**An abandoned match imports with a blank result.** It was played and it counts
as a match, but it is not a win, a loss or a draw, and `_club_results` only
counts a row whose result is set. Blank files it exactly where the club's own
summary files it: on the fixture list, off the W/L/D line.

### A keeper's catch is a plain `c` plus the flag

`batting_caught_behind` is a separate column (migration 291 gave
`manual_batting_innings` that column). Spelling it in the dismissal text as
well renders "c wk (wk)" on the scorecard.

It is **blank, never `"false"`**, when the card does not say. The card saying
nothing is a different answer from the card saying it was not the keeper, and
only blank reads as a plain catch.

### A match with nobody named is one row with the player column empty

`_write_games` in `backend/app/routers/manual_entries.py` already contains
`if not pname: continue`, and `_GAME_REQUIRED` checks the column exists in the
header rather than that every row has a value. So a game with no scorecard
under it imports with **no backend change**: one row carrying the match, the
date, the opponent, the venue and the result, and an empty `player_name`.

Twelve of Shoalwater's matches are exactly that.

### An unmapped dismissal code imports blank

Better a match with the runs and no method than a made-up method. Every code
Shoalwater's archive carries is now named, so nothing currently falls through,
but the branch stays for the next club, whose files will carry codes this one
never used. It keeps the innings and the runs and leaves `dismissal_type`
empty, and the raw code sits in its own column on the Batting sheet so somebody
can ask the club what it means.

## 10. Onboarding another club's `.AV` archive

1. **Check the file size.** Every `.AV` must be exactly 549,871 bytes. A
   different size means a different program version and every offset below
   needs re-deriving before anything else.
2. **Read the header.** Club name at offset 0, season year at offset 30. Confirm
   the club name matches who you think you are converting.
3. **Re-confirm the result byte.** Scan every byte of the match record against
   the outcome the scores imply, and check that the winning value's count is
   plausible. If the club can supply its CSFW summary screen, the five counts
   should match exactly, which settles it outright.
4. **Run the converter** and read the seven checks. Wickets and boundaries at or
   near 100% is the signal the decode is sound. Anything materially below that
   means an offset is wrong, not that the club's scorers were careless.
5. **Ask the club for its own totals** (the CSFW summary screen: matches, won,
   lost, drawn, tied, abandoned). Reconcile the match count first, since that is
   the figure a club checks and the one most likely to expose a dropped-record
   bug like the 897-versus-914 case.
6. **Ask about any unmapped dismissal codes** before importing, then check the
   answer against the files rather than taking it and moving on: where each one
   sits in the batting order, what the batter scored, and whether they also
   bowled. Leave a code blank rather than guessing at it. A code the club names
   as **absent** or **did not bat** needs the extra step above, a dismissal in
   the file and a `did_not_bat` row on import.
7. **Check the Data quality sheet** for same-day grade clashes and raise them
   with the club.
8. **Import `manual_games_scorecards.csv`** through the Manual Games wizard.
   Verify the games count and the club's W/L/D line afterwards.

### Reconciling runs and wickets against the club's summary screen

Shoalwater reported a "difference between CSFW and Claude Code's analysis with
wickets and runs". **There was no discrepancy.** Every headline on the CSFW
summary reproduces exactly from the binary. The two sets of figures answer
different questions:

| CSFW summary line | What it counts | Our equivalent |
|---|---|---|
| Runs For | The team total, extras included | Batters' runs alone is a smaller number |
| Wickets (for) | Every wicket that fell | Bowler-credited wickets excludes run outs |
| Runs Against | Their innings totals | Same |

So the club's 146,382 runs for is the innings totals, while a sum of batting
rows is the batters' own runs, and the gap is extras. Likewise 7,855 wickets
against a bowler-credited figure differs by every run out and every wicket the
scorer never attributed.

**Explain the arithmetic rather than "fixing" either number.** Both are right
about their own question.

### What cannot come across

- **The toss.** The `.AV` toss field is not decoded, and BetterCricket has no
  toss column to receive it. Shoalwater's 448 of 895 is not importable.
- **Balls faced and strike rate.** Not in the format.
- **Run outs as a fielding credit.** Not in the format.
- **The bowler or fielder credited with a wicket.** Not in the format, so
  partnerships and fall of wickets come across but "c Smith b Jones" cannot.
- **Opposition players.** The program never stored them.

---

# Part 2: CricketStatz web reports

The other route a club may arrive on. A club hands over the address of its own
public CricketStatz stats page and the in-app wizard pulls the history across.
Fully built: `backend/app/services/cricketstatz_client.py`,
`cricketstatz_parse.py`, `cricketstatz_import.py`, `cricketstatz_awards.py`.

The essentials, so the two paths are not confused:

- **Everything is served by one documented embed endpoint**,
  `/ss/linkreport?mode=<report>&club=<id>&web=1`, which answers with
  `document.write("<table>…")`, HTML tables inside a one-line JS string.
- **Three reports carry everything**: `mode=12` match results (one row per
  match, each linking `mode=100`), `mode=100` the full two-team scorecard, and
  `mode=107` the team list. Roughly 180 further modes are record boards.
- **`limit` caps a report at 999 rows**, so match lists are pulled season by
  season. An all-time pull silently truncates for a club with a long history.
- **Column layouts vary by era.** A modern card is `R M B SR 4s 6s`; a 1995 one
  is `R M 4s 6s` with no balls faced and no strike rate. Read the header row,
  never positions.
- **Captain, keeper and duck are `title=` attributes**, not the emoji. The
  glyphs vary by era and encoding, `title='Duck'` does not.
- **Identity is CricketStatz's own `playerid`**, not the printed name, which is
  abbreviated inconsistently across eras.
- **Split a dismissal on each `span.ss_block`'s opening tag.** A clause nests
  its own `ss_howout` span, so a non-greedy match to the first `</span>` stops
  inside it and loses every name.
- **A lapsed subscription returns "Subscription expired"**, not a 404. A club
  moving to BetterCricket is exactly the club whose subscription is lapsing, so
  that error is typed and reported rather than read as "this club has no
  matches".
- **One club at a time, on demand.** Low concurrency, a delay between requests,
  a User-Agent that says who we are. Their `robots.txt` disallows `/ss/`; this
  proceeds on the data-portability reading and never enumerates club ids or
  sweeps the site.

The full behavioural notes for this path, including the match-pairing work that
stops a club holding the same fixture from two sources, are in `CLAUDE.md`
under the CricketStatz headings.

---

## Appendix: running the converter

```bash
python3 tools/convert_shoalwater_av.py <folder of .AV files> -o <output folder>
```

It prints a row count per sheet and the seven checks. No network access, no
database, no configuration.

Despite the file name it is not Shoalwater specific. The club name comes out of
the file header.
