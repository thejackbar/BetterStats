# Reading a club's Cricket Statistics for Windows files

**What this is:** the whole method for turning a club's CSFW season files into a
spreadsheet a person can read and a CSV BetterCricket can import. It was
recovered by decoding Shoalwater Bay Cricket Club's fifteen seasons byte by
byte, and it is written here as a manual for the next club rather than as that
club's history.

**The code is `tools/convert_shoalwater_av.py`.** It takes a folder of `.AV`
files and writes one workbook and two CSVs. This document is the reasoning
behind it: what the bytes mean, which readings were proved and how, every
exception the files threw up, and what has to be re-checked before pointing it
at a different club.

> **A club's files never go in this repository.** They hold members by name
> across thirty years, and this repo is public. `.gitignore` carries
> `data/shoalwater-av/` for exactly that reason. Keep a club's files wherever
> the club keeps them and pass the converter a path.

---

## 1. What CSFW is, and which files matter

Cricket Statistics for Windows is an MS-DOS and early-Delphi era club averages
program. A club keeps one set of files per season, named for the year the
season started:

| File | Holds | Use it for |
|---|---|---|
| `DATA<year>.AV` | Everything: club, players, fixtures, full match records | **This is the one you read.** |
| `DATA<year>.PLR` | Players, with ids stable across seasons | Cross-check only |
| `DATA<year>.FIX` | Fixtures: slot, date, team, opponent | Cross-check only |
| `DATA<year>.MCH` | Matches, 1,756 bytes each, 604-byte header then 12 blocks of 96 | Cross-check only |
| `DATA<year>.DAT` | Nothing. Blank in every season seen | Nothing |

**The `.AV` is a complete, self-consistent export of the others.** Checked
against the 1993 set: its fixtures agree with `.FIX` on date, team and opponent
for all 41 shared slots, and its scorelines agree with `.MCH` on all 35.

**`.DAT` is blank, and so is the `.AV`'s own per-player stats region.** The
program recomputed averages when it drew a screen rather than storing them, so
there is no stored aggregate anywhere to reconcile a conversion against. Every
season figure has to be built from the per-innings rows, which is what the
converter does.

**The `.AV` renumbers its players.** `.PLR` keeps a player id stable across
seasons; the `.AV` does not. That is fine, because an `.AV` match block only
ever refers to the `.AV`'s own roster, so resolving inside one file names the
same eleven in the same order. It does mean a player id means nothing outside
the season file it came from, and the conversion keys on the player's NAME
across seasons rather than on an id.

### The sibling files check the decode; they never feed it

`.FIX` and `.MCH` are an independent record of the same seasons. Use them to
confirm a reading and report a disagreement. Never mix a fixture label from one
file onto a scorecard from another: that is how a match ends up under the wrong
date, and it is silent when it happens.

Shoalwater's nine seasons with siblings agreed on fixtures in 471 of 485 and on
grounds in 473 of 485, with eight of the nine agreeing completely. The one
divergence (1995/96) is **version skew, not a parse fault**: the `.FIX` names
two intra-club fixtures the `.AV`'s own table does not, so from that point the
two files' slots sit two apart for one team. The `.AV` was kept whole and the
disagreement reported.

---

## 2. File layout

Every byte of a 549,871 byte file is accounted for:

```
offset       size                 section
0            311                  header: club name (30) + year (4) + settings
311          200 x 37             player index
7,711        200 x 578            per-player stats area (blank in every file seen)
123,311      160 x 54             fixtures
131,951      160 x 2,612          matches
```

```
FILE_LEN = 311 + 200*37 + 200*578 + 160*54 + 160*2612 = 549,871
```

`parse_file` refuses a file of any other length rather than reading it wrong.
**If a club's files are a different size, do not adjust the constants until you
have re-derived the layout** (section 10).

### Primitives

| Thing | Encoding | Sentinel |
|---|---|---|
| Integer | little-endian `int16` | `-1` means not recorded |
| Overs, votes | Delphi `Currency`: `int64` scaled by 10,000 | `-10000` (that is `-1.0`) means not recorded |
| Date | Delphi/Excel day number from **1899-12-30**, stored as `float64` | `<= 0` means no date |
| Text | Fixed width, latin-1 | Padded with spaces, but **also carries NUL and `0xFF`** |
| Result | A single **byte**, not an int16 | see section 5 |

**Text padding bit you will get wrong once.** A field can be padded with
spaces, with NUL, or with `0xFF`. Shoalwater's fixture name field is 32 bytes
and the two bytes after it are the next field: that held `0x0000` in every
season up to 2005 and `0xFFFF` in 2006, so an opponent read at 34 bytes wide
came out as `Warnbro Knights yy`. Strip NUL **and** `0xFF`, and get the width
right rather than relying on the strip.

### Header (offset 0)

| Offset | Size | Field |
|---|---|---|
| 0 | 30 | Club name |
| 30 | 4 | Season start year, as text |

The rest is program settings and is not read.

### Player index (offset 311, 200 records of 37)

| Offset | Size | Field |
|---|---|---|
| +0 | 2 | Player id (`int16`, `-1` for an empty slot) |
| +2 | 16 | Surname |
| +18 | 3 | Initial |
| +21 | 16 | First name |

A record with no surname is skipped. The display name is built as
**`Surname, First`**, which is the shape BetterCricket's own name matcher reads
best, falling back to `Surname, Initial` and then to the bare surname.

### Fixtures (offset 123,311, 160 records of 54)

| Offset | Size | Field |
|---|---|---|
| +0 | 2 | **Slot of the match record this fixture points at** |
| +2 | 8 | Date (`float64` day number) |
| +18 | 2 | Team number (the grade) |
| +20 | 32 | Opponent name |

**Read the pointer, not the array position.** See section 3; this is the single
most expensive mistake available in this format.

### Match record (160 records of 2,612, from offset 131,951)

| Offset | Size | Field |
|---|---|---|
| +10 | 20 | Round label |
| +30 | 2 | Ground index |
| +32 | 30 | Ground name |
| +496 | 1 | **Result, one byte** (section 5) |
| +502 | 72 | Innings block: **always our club's innings** |
| +574 | 72 | Innings block: the opposition's |
| +646 | 40 | Fall of wickets: 10 pairs of (`int16` score, `int16` batting position) |
| +756 | 16 x 116 | Player blocks |

Offsets 686 to 756 are not mapped. Nothing needed from them has turned up.

### Innings block (72 bytes)

| Offset | Field |
|---|---|
| +0 | Total |
| +2 | Wickets |
| +4 | Innings number |
| +6 | Overs (`Currency`) |
| +14, +16, +18, +20, +22 | Byes, leg byes, wides, no balls, penalty |

An innings counts as played when its total is present and not negative.

### Player block (116 bytes, 16 per match)

| Offset | Field |
|---|---|
| +0 | Player id (`int16`; skip if negative or past the roster) |
| +2 | Batting position, 0-indexed. **255 means did not bat** |
| +8 | Runs |
| +12 | Sixes |
| +14 | Fours |
| +20 | How out (dismissal code, section 4) |
| +24 | Overs bowled (`Currency`) |
| +32 | Maidens |
| +34 | Wickets |
| +42 | Bowling flags (an unidentified bitmask, present only on bowlers) |
| +46 | Runs conceded |
| +48 | Wides |
| +50 | No balls |
| +52 | Catches |
| +56 | Wicket keeper catches |
| +60 | Stumpings |
| +64 | Byes conceded |
| +82 | Award votes (`Currency`) |

Offsets 90 to 116 are not mapped.

**A player batted if runs are present**, not if a batting position is. **A
player bowled if overs are present.** Those two tests are what separate a real
innings from a name on the team sheet.

---

## 3. Four readings the bytes alone cannot give you

Each of these was settled by measuring the data, and each one is wrong in a way
that no amount of re-reading the source would show.

### Overs are cricket notation, not decimals

`93.3` is 93 overs and 3 balls. Confirmed because the fractional digit is never
above 5 anywhere in any file. **Anything that sums or divides overs converts to
balls first** and writes the result back the same way. Adding overs as decimals
inflates a season total and quietly wrecks every economy rate built on it.

### A fixture points at its match; the array position is not the slot

The fixture array is held in **date** order and each record's first field is
the slot of its match record. Those two coincide in 1992 and in no other
season, so reading the array position paired every scorecard from 1993 on with
another match's date, opponent and team.

**Why it survived so long is the lesson.** 1992 was the season hand-checked end
to end, and it was right. Every other check was INTERNAL to a match record:
runs plus extras against the innings total, dismissed batters against the
wickets, bowlers' runs against the total less byes. Not one of them touches the
fixture-to-match join, so all six still passed at exactly the same rates with
every label attached to the wrong scorecard.

> **A suite that only tests inside a record cannot see a record attached to the
> wrong label.** Check the join separately, against a sibling file or by hand.

The tell is cheap to look for: the stored slots are a **permutation of
`0..n-1`** rather than a run.

Fixing it changed attribution and no data. Runs, wickets, catches and games
were identical to the byte counts before and after. What moved was the grade
split: season rows fell from 2,503 to 1,363 because players stopped being
scattered across grades they never played in, and the same-player-two-grades
anomaly fell from 6,740 rows to 4.

### The trailing digit on a fixture name is a leg, not a grade

Seasons up to 1997 store a two-day match as **two records**, `Opponent 1` and
`Opponent 2`. They share a date and a team number, so they are two innings of
one match rather than two opponents and not the grade.

`.FIX` settles it outright: on 1993-10-09 team 1 plays both `Warnbro 1` and
`Warnbro 2`, and team 2 does the same. The digit cannot be the grade.

**Only strip the suffix where the sibling leg is actually present**, so an
opponent whose real name ends in a digit is left alone.

### The grade is the team number

The files hold no grade NAME. The team number on the fixture record is all
there is, so grades come out as `Grade 1` to `Grade 4` and are renamed after
import. Shoalwater's 1992 stores `2` for every fixture, which looks like a
default rather than a real team number, and is called out in the workbook
rather than corrected.

### Two fields that were assigned by measurement, not by guess

- **Fours and sixes.** Tested both ways round: one order gives 690 rows where
  the boundaries account for more than the runs scored, the other gives none.
- **The keeper fields.** Found by concentration. Keeper catches, stumpings and
  byes fall on the same eleven players across a season, while ordinary catches
  spread across fifty.

---

## 4. Dismissal codes

**Codes are the least portable part of this format. Re-derive them per club.**
The method below matters more than Shoalwater's answers.

### The two retirements are different innings, and one of them is a wicket

**This is the rule that decides which codes are not outs, so it comes before
the method.** MCC Law 25.4 splits retirement in two, and the split is worth
exactly one innings in a batting average:

- **Law 25.4.2, "Retired - not out".** Illness, injury or another unavoidable
  cause, and the batter did not resume. **Not a dismissal.** No bowler is
  credited and it does not go in the average's denominator.
- **Law 25.4.3, "Retired - out".** Retired for any other reason without the
  opposing captain's consent. **A dismissal**, credited to no bowler, counting
  against the average.

**Payneham Cricket Club is where this was proved, on live data rather than from
the Law.** The club reported one player showing two different averages on one
screen: 77 runs from 8 innings, reading **15.40** on the profile header and
**12.83** in StatLab. The header was right because it reads Cricket Australia's
own `battingNotOuts` verbatim. The other figure came from our own scorecards,
where `sync.py` decided a not out with `not_out = dt_id == 1`, so every
retirement landed flagged as a wicket. `77 / (8 - 2) = 12.83` against CA's
`77 / (8 - 3) = 15.40`. The two paths disagreed by exactly one innings.

**CSFW encodes the same split, in its own numbers.** Shoalwater's files carry
`11` (not out), `12` (not out, retired) and `10` (retired out), and the wickets
identity below confirms that split from inside the file rather than from the
Law: reading `12` as a not out takes the identity from 908 of 916 innings to
916 of 916, and reading `10` as one breaks 11 innings that currently balance.
Two unrelated formats, one distinction, so treat it as a property of cricket
rather than of either program.

**The reconciliation is the transferable part.** Both of Cricket Australia's
retirement ids were settled by checking a single player against the source's
own season aggregate, in both directions:

- One player's `battingNotOuts: 3` over two plain not outs plus one **Retired
  Not Out** proves that id is a not out.
- Another player retired for 0, and CA counted it among his `batting0s` with
  `battingNotOuts: 1` for his one genuine not out. **A duck and a wicket**,
  which proves plain **Retired** is a dismissal.

**CSFW gives you no aggregate to do that with.** The per-player stats region and
`.DAT` are blank, because the program recomputed averages rather than storing
them. That absence is the whole reason the wickets identity below exists: with
no stored total to reconcile against, the innings' own wickets figure is the
only independent count in the file.

**Never match a retirement with `LIKE 'retired%'`.** That one word is the
difference between "not a dismissal" and "a dismissal". A prefix match sweeps
the plain retired-out in with the two not-out retirements and hands every
retired-out batter an average they have not earned, which is the same bug
pointed the other way. Match the whole phrase.
`backend/app/services/dismissal.py` is the single definition on the app's side
and holds both the Python and the SQL form, asserted to agree row by row.

**Two consequences for a conversion:**

- **Retiring out for 0 is a duck.** A 0 not out is not. The converter counts a
  duck as runs of 0 with the not-out flag clear, which gets both right off the
  one flag.
- **Fix the writer, not the readers.** Every average in BetterCricket is already
  `runs / (innings - not_outs)`. When a not-out flag is wrong, the repair is the
  one place that sets it, plus a backfill. It is never thirty query edits.

### The identity that proves a not out

Count the batters recorded as dismissed in an innings and compare against the
wickets the innings itself reports. Run it with each candidate code treated as
a not out and keep the set that makes the identity hold most often.

For Shoalwater, with `11` alone as the not out the identity held in **908 of
916** innings. Adding `12` made it **916 of 916**, and the 8 innings carrying a
`12` were exactly the 8 that had been failing.

That same identity proves the rest by exclusion: **every other code makes it
worse**, so `7`, `10`, `13`, `14`, `15`, `29` and `37` are all genuine
dismissals whatever they turn out to be called. Adding `13` made it worse by
121, `14` by 243 and `37` by 39.

### Corroborating a label against an independent population

You can support a label without the club by counting a different field in the
same files and looking for the same magnitude:

- Our batters were **run out 443 times** against **404 wickets we took that
  were credited to no bowler**.
- Our batters were **stumped 196 times** against **234 stumpings by our own
  keepers**.

Two separate fields, two separate populations, the same order of magnitude.
Add the ordinary shape of club cricket as a sanity check: caught 47.6% of
dismissals, bowled 27.0, LBW 8.9, run out 6.1, stumped 2.5.

**Reading like something is not evidence.** Code 14 plus caught gives 3,802
against our fielders' own 3,851 catches, which reads like a second catch
category, and it was still left raw until the club confirmed it.

### Shoalwater's decoded table

| Code | Meaning | How it was settled |
|---|---|---|
| 0 | Bowled | Independent population and share |
| 1 | Caught | Independent population and share |
| 2 | LBW | Independent population and share |
| 3 | Stumped | 196 against 234 keeper stumpings |
| 4 | Run out | 443 against 404 bowler-less wickets |
| 7 | Hit wicket | Club confirmed |
| 10 | **Retired out, a DISMISSAL** | Club confirmed, and the identity |
| 11 | Not out | The identity |
| 12 | Not out (retired) | The identity |
| 13 | Caught and bowled | Club confirmed |
| 14 | Caught by the keeper | Club confirmed |
| 15 | Caught in slips | Club confirmed; stored as a plain catch |
| 29 | Unknown, 7 innings | Left raw |
| 37 | Caught by the keeper | Club confirmed |

### Three rules that came out of it

**Code 10 is a dismissal and must stay one.** Law 25.4.3's retired-out is a
genuine wicket credited to no bowler, and it counts against the average. The
files settle it rather than the Law alone: adding 10 to the not-out set breaks
11 of the 916 innings that currently balance. Measured by running it that way.
`backend/app/services/dismissal.py` holds the same distinction on the app's
side, so **never match either retirement with `LIKE 'retired%'`**.

**A catch position is not a dismissal method.** Code 15 is caught in slips, and
there is no field anywhere for where a catch was taken. Spelling the position
into the dismissal text puts a word into the How I Get Out donut that
classifies as its own stray slice beside the real one. It stores as a plain
catch.

**A keeper's catch is a plain `c` plus a flag.** Codes 14 and 37 go into
`CAUGHT_BEHIND_CODES` and ride as the `batting_caught_behind` column, not as
words. That is how the sync stores one, and the scorecard appends its own
`(wk)` from the flag, so spelling it in the text as well renders `c wk (wk)`.
`CAUGHT_BEHIND_CODES` is a set precisely so another such code can be added
without touching anything that reads it, which is exactly what happened when
the club came back with 37 beside 14.

### The keeper codes are UNDER-recorded, not wrong

Codes 14 and 37 together appear 454 times against Shoalwater's batters, while
their own keepers took 958 catches over the same fifteen seasons. A scorer
filling in the batting card reached for the specific code about half the time
and plain `caught` the rest.

**Read a caught-behind figure from these years as a floor.** Stumped is the
control: 196 against 234, which is the agreement the caught-behind pair does
not show. Say this to the club before they read the number.

### Two different "code 14" in one project

| Namespace | 14 means |
|---|---|
| CSFW `B_HOWOUT` | Caught by the wicket keeper |
| Cricket Australia `dismissalTypeId` | Retired Not Out |

They are unrelated. `dismissal.py` documents CA's enumeration; this document
covers CSFW's. Never carry a code from one into the other.

### An unknown code imports as out with no method

Not as a guess, and not dropped. The runs still count, the innings still counts
as a dismissal, and the raw code is carried in its own column beside the label
so a club can come back and name it later. Shoalwater's remaining unknowns are
19 innings out of 9,180: 7 on code 29 and 12 carrying no code at all.

---

## 5. The result field

**The club's own recorded result is in the file, at match offset 496, one
byte.** It was found by scanning every byte of the match record against the
outcome the scores imply.

| Code | Result |
|---|---|
| 0 | Won |
| 1 | Lost |
| 2 | Drawn |
| 3 | Tied |
| 4 | Abandoned |

**Confirmed outright, not inferred.** Across all 914 matches the byte takes
exactly five values, and their counts are exactly the five lines of the club's
own CSFW summary: 467 won, 433 lost, 3 drawn, 3 tied, 8 abandoned. Five values,
five categories, all five counts exact.

`3` is tied and `2` is drawn, which the counts alone cannot settle since both
are 3. The scores do: every match carrying a `3` has our total equal to theirs,
and no scored match carries a `2` at all. `4` is corroborated the same way,
since half the `4`s are scored matches where the side was 15 or 9 all out
against 195, which is what an abandoned innings looks like.

**This field is authoritative over the scoreline.** A club wins on first
innings, loses a two-day match it out-scored, or has a game abandoned
mid-innings, and the scores alone say none of that. The 11 matches where the
two disagree are **reported by `verify` rather than quietly resolved either
way**.

---

## 6. Exceptions, and the rule each one produced

This is the part that took the longest and the part most likely to repeat at
another club.

### A two-day match is one match

Legs share a date, a team and an opponent, so they group into one match with a
`Leg` column saying which record a row came from. **Every reader has to count
that as one match or the games played figure doubles.** A player can still
legitimately record more bowling innings than games: all 36 such rows at
Shoalwater are a bowler bowling in both innings of one two-day match.

### A blank second day is not an innings

231 of Shoalwater's matches have the second day's side named again with no
figures at all, because the game was settled on day one. **Emitting that leg
gives all eleven an invented "did not bat" innings on top of the runs they
really made.** A blank leg is dropped.

### A match whose EVERY leg is blank is a real match

This is the opposite case and it cost 17 matches. A match record with no
innings and nobody who batted or bowled was being read as a fixture nobody
filled in. It is not. Ten were won by forfeit, three drawn and four abandoned,
and none of those produces a figure to record. The club counts them, which is
why the total is 914 and the first conversion said 897.

**One shared function decides both**: a match keeps its blank legs only when
every leg is blank, and then keeps exactly one of them, because the two records
name the same eleven and taking both counts that side twice.

Of the 17, five name a real eleven and record nothing else. Those import as a
match played each and **not** as a batting innings, so no average moves, and
the names go in a `Named side (no scorecard)` column. The other twelve name
nobody, and import as one row carrying the match with the player column empty,
which the importer already reads as a game with no scorecard under it.

### Nobody plays two matches in one afternoon

Some dates name one person in more than one grade. Either the grade on one
record is wrong, or the stored date is a round stamp shared by competitions
that ran on different days. **The files cannot tell you which, and the figures
are sound either way** since every innings still reconciles to its own total.

It only affects the grade split, so it goes on a `Data quality` sheet rather
than being silently dropped or silently kept. After the fixture-pointer fix
this ran to 4 rows out of 9,384 player-dates.

**Do not throw the grade split away to avoid this.** Both the graded and
ungraded roll-ups count the same distinct matches, so games and appearances are
identical either way. The split cannot make a season or career total wrong; it
can only file a right total under a wrong heading, which Manage Grades can
merge after the fact and which no import can recover if it was discarded up
front.

### The graded and ungraded season files are the same file

Summing the graded rows per player-season reproduces the ungraded file exactly,
every counting column and every high score, across all 853 player-seasons. The
grade split is purely additive. So there is **one** season-stats output and no
choice to offer; the `by_grade=False` switch stays on the function for anyone
who wants that roll-up separately.

### Version skew between `.AV` and `.FIX`

See section 1. Report it, keep the `.AV` whole.

### A field width that only shows up in one season

See section 2. Two bytes of `0xFFFF` in one season out of fifteen.

---

## 7. Verification

Seven checks, run against the data's own arithmetic rather than against the
conversion:

| Check | Shoalwater result |
|---|---|
| Batting runs plus extras equal the innings total | short by ones and twos |
| Batters dismissed equal the innings wickets | **916 of 916** |
| Bowlers' runs equal their total less byes and leg byes | short by ones and twos |
| Bowlers' wickets never exceed the innings wickets | all |
| 4s and 6s never account for more than the runs scored | all |
| Award votes add up to 3-2-1 | 114 of 116, both exceptions a tied vote |
| The card's own result agrees with the scoreline | 11 disagreements, left alone |

**Where a check falls short the residual is a one or a two, which is the usual
slip in a hand-kept scorebook. Nothing is corrected.** The workbook says so on
the Notes sheet, because a club statistician reading a 97% figure deserves to
know whose arithmetic it is.

Two of these do double duty. The dismissed-batters identity is what decodes the
not-out codes (section 4). The result check is what surfaces a first-innings
win rather than an error.

**And remember what they cannot see.** All seven are internal to a match
record. They passed at identical rates while every scorecard was attached to
the wrong fixture.

### Cross-checks that are not arithmetic

- `.FIX` and `.MCH` agreement per season, reported on a `Cross-check` sheet.
- The club's own program summary. Shoalwater's headline figures reproduce to
  the run: 146,382 for and 143,574 against, 7,855 wickets lost and 7,895 taken,
  37,210.3 overs.

**Expect the club's totals and yours to count different things.** 146,382 is
the team total and 127,910 the batters' own runs, the 18,451 between them being
extras. 7,895 is every wicket and 7,444 those credited to a bowler, the 451
between them being run outs. Neither is wrong. Work out which is which before
telling a club their file is short.

---

## 8. Output

### `match_detail.xlsx`

One sheet per grain, one row per thing:

`Notes`, `Matches`, `Batting`, `Bowling`, `Fielding`, `Fall of wickets`,
`Votes`, `Players`, `Data quality`, `Cross-check`.

The `Notes` sheet is written for a club statistician who has no other way of
knowing any of this. It carries the overs convention, the grade caveat, the
two-day rule, the no-scorecard matches, the result field, the dismissal
decoding, the caught-behind floor, what the format does not record, and
**which file to import**.

### `manual_games_scorecards.csv`, the one to import

One row per player per match, in the Manual Games importer's own 32 columns.
It lands real match records, so match pages and partnerships work.

### `betterimport_season_stats.csv`, the simpler alternative

Season totals per player and grade, no match detail. 26 of its 27 headers
auto-map through BetterImport's own synonyms with no mapping step; the
exception is award votes, which the importer has no field for and which are
carried anyway rather than dropped.

> **Import ONE of the two, never both.** The same runs would be counted twice.
> Say this on the Notes sheet, because the workbook leaves the building.

---

## 9. Writing for BetterCricket, not for a human reader

Four traps, all of which shipped wrong once.

### The stored vocabulary is not the readable label

BetterStats stores a dismissal as a **short lowercase** code and the How I Get
Out donut classifies on those strings **case-sensitively**. `Bowled`, `Caught`,
`LBW`, `Stumped` and `Run out` match none of them, so every one falls through
to the `ELSE` branch and draws its own slice beside the real one.

So the reading label and the stored code are separate:
`DISMISSALS` is what the workbook prints for a person, `IMPORT_DISMISSALS` is
what the CSV carries for the app.

| Code | Workbook | CSV |
|---|---|---|
| 0 | Bowled | `b` |
| 1 | Caught | `c` |
| 2 | LBW | `lbw` |
| 3 | Stumped | `st` |
| 4 | Run out | `run out` |
| 7 | Hit wicket | `hit wicket` |
| 10 | Retired out | `retired out` |
| 13 | Caught and bowled | `c & b` |
| 14, 15, 37 | (as decoded) | `c` |

`c & b` keeps its text because there is no flag for it, and it still starts
`c ` so it reads as a catch. `hit wicket` and `retired out` are the app's own
spellings, checked in Postgres against the shipped donut CASE,
`dismissal.is_not_out` and StatLab's unusual-dismissals predicate.

### The same trap on results

Every reader in the app compares against `WIN`, `LOSS`, `DRAW` and `TIE`. A
readable `Won` matches none of them, so it counts as neither a win nor a loss
on the club's own dashboard. Run against the first conversion's output the
dashboard reported **0 wins and 0 losses**; it now reports 467 and 433 for a
51.5% win rate, against the 51% the club's own program prints.

**An abandoned match is deliberately blank.** It was played and counts as a
match, but it is not a win, a loss or a draw, and `_club_results` only counts a
row whose result is set. Blank files it exactly where the club's own summary
files it: on the fixture list, off the W/L/D line.

### Blank, zero and false are three different answers

- **Blank** means the format does not record it. Balls faced, batting strike
  rate, run outs and the bowler or fielder who took a wicket are not in CSFW at
  all. A zero would read as a recorded nought.
- **`batting_caught_behind` is blank, never `false`.** The card saying nothing
  is a different answer from the card saying it was not the keeper, and only
  blank reads as a plain catch.
- **`did_not_bat`** is a real `true`/`false`, because the file does say.

### A fact can survive the whole conversion and be dropped at the last step

The keeper's catch was read out of a thirty-year-old file, carried through
every stage, and then lost, because `manual_batting_innings` had no
`caught_behind` column and the effective view's manual branch hardcoded
`NULL::boolean`. **Migration 291** gave it one. Check the destination column
exists before celebrating a decode.

### The importer contract

`manual_games_scorecards.csv` columns:

```
game_key, played_at, opposition, venue, season_name, grade_name,
is_final, match_format, home_team, away_team, winning_team, result,
player_name, innings_number, batting_position,
batting_runs, batting_balls, batting_fours, batting_sixes,
batting_not_out, did_not_bat, dismissal_type, batting_caught_behind,
bowling_overs, bowling_maidens, bowling_runs, bowling_wickets,
bowling_wides, bowling_no_balls,
fielding_catches, fielding_catches_wk, fielding_run_outs, fielding_stumpings
```

- Rows sharing a `game_key` roll up into one game.
- `game_key`, `season_name` and `player_name` must be present as columns.
- A **two-day match is ONE game**, its legs separated by `innings_number`, so
  games played agrees with the workbook and the season CSV.
- The stored innings number is only usable when the legs actually disagree
  about it. Both records routinely store `1`, so fall back to leg order.
- A **blank `player_name`** on an otherwise complete row is how a match with no
  scorecard under it is imported.
- Import goes through the **preview/resolve/commit wizard**, not the strict
  endpoint. The strict one refuses a row naming a season, grade or player the
  club does not already hold, which for a whole history is every row. A season
  or grade is created without ceremony; a **player is proposed and never
  auto-created**, because this codebase carries the scars of a name matcher
  putting two people on one record.

---

## 10. Pointing this at a different club

Work in this order.

### 1. Check the file length first

If it is 549,871, the layout in section 2 applies and you can go straight to
step 3. If it is not, the program version differs and the record counts or
sizes have changed. Do not adjust constants until step 2.

### 2. Re-derive the layout

The layout was recovered by inspection, then checked against the data. The
method:

- **Account for every byte.** The five sections must sum exactly to the file
  length. Solve for the unknown by trying plausible record counts (200 players,
  160 fixtures and 160 matches are round numbers a program author picks) and
  record sizes until the arithmetic closes with nothing left over.
- **Find the text fields first.** They are readable in a hex dump, and a club
  name at offset 0 and a year right after it anchor the header.
- **Find the sentinels.** Runs of `0xFFFF` mark unused `int16` slots and give
  you the record stride for free.
- **Test a field pair both ways round** where the order is ambiguous, and keep
  the one that never violates an identity. That is how fours and sixes were
  assigned.
- **Use concentration** where a label is ambiguous. A keeper field falls on the
  same handful of players; an ordinary fielding field spreads across the squad.
- **Scan every byte against a known outcome** to find a field you suspect
  exists. That is how the result byte at +496 was found.

### 3. Run the converter and read the checks

```
python tools/convert_shoalwater_av.py /path/to/club/files -o /path/to/output
```

Needs `openpyxl`. It prints per-sheet row counts and the seven checks. A check
below about 95% is worth understanding before going further.

### 4. Verify the join, not just the arithmetic

The checks cannot see a scorecard on the wrong fixture. Confirm separately:

- Are the stored fixture slots a permutation rather than a run?
- Does the `Cross-check` sheet agree with `.FIX` and `.MCH`?
- Hand-check one match against the club's own program, in a season **other**
  than the first one in the file set.

### 5. Re-derive the dismissal codes

Do not carry Shoalwater's table across. Run the wickets identity per candidate
not-out code, corroborate the common labels against independent populations,
then take the remainder to the club. Anything unnamed imports as out with no
method.

**Settle the retirements explicitly rather than letting them fall out.** Ask
which codes the club's scorers used for a batter who retired hurt and for one
who retired for any other reason, and check the answer against the identity:
adding a genuine retired-out to the not-out set will break innings that
currently balance. Getting this wrong moves a batting average by one innings
per retirement and shows up as two different averages on one screen, which is
how it was found at Payneham (section 4).

### 6. Confirm the result byte

Count the values it takes and compare against the club's own summary lines.
Five values matching five counts is proof; anything less is a hypothesis.

### 7. Read the club's own totals back

Ask for their program's summary and reconcile. Expect team total against
batters' runs, and all wickets against bowler-credited wickets, to differ by
extras and run outs respectively.

### 8. Import through the wizard, then check a dashboard

The last two defects only showed up after import: the result vocabulary
(dashboard read 0 wins) and the dismissal vocabulary (donut drew stray slices).
Look at the club's own screens, not just the row counts.

---

## 11. What CSFW does not hold

- **Balls faced** and therefore batting strike rate.
- **Run outs** as a fielding credit.
- **Which bowler or fielder took a wicket.** Fall of wickets carries the score
  and the batting position only.
- **Opposition batting and bowling cards.** The program only ever stored the
  club's own players, so the opposition exists as innings totals and nothing
  more.
- **Grade names.** Only a team number.
- **Stored averages.** The player-stats region and `.DAT` are blank.

All of these are left **blank**, never zeroed.

The bowling bitmask at player-block +42 is present only on bowlers, is not
identified, and is passed through raw rather than guessed at.

---

## 12. Payneham Cricket Club

**Payneham's contribution to this method is the retired-not-out rule in section
4, not a CSFW conversion.** The club reported one player carrying two different
batting averages on one screen, which is what proved that the two retirements
under Law 25.4 are different innings and that only one of them belongs in an
average's denominator. That rule governs which CSFW codes may be read as not
outs, so it sits with the decoding method rather than here.

The finding came off Payneham's live Cricket Australia data, not off CSFW
files. Payneham appears in this repository only as a synced club: the
retired-not-out bug (`backend/app/services/dismissal.py`,
`backend/verification/verify_retired_not_out.py`) and the grade grouping
measured in `services/match_coverage.py`. **There is no converter, output
workbook, CSV or source data for Payneham here.**

If Payneham's own CSFW files are decoded later, the parts worth folding into
this document are:

- the file length and, if it differs from 549,871, the section sizes it implies
- the dismissal code table and how each code was settled, including which codes
  carry the two retirements
- the result byte's values and their counts against the club's own summary
- any exception that is not already in section 6

Everything else should apply unchanged, since it describes the format rather
than the club.

## 13. Related

| File | What it holds |
|---|---|
| `tools/convert_shoalwater_av.py` | The converter. The code is the authority; this document is the reasoning. |
| `backend/app/services/dismissal.py` | The one definition of a not out, the two retirements, and CA's separate `dismissalTypeId` enumeration |
| `backend/verification/verify_retired_not_out.py` | The suite that pins both retirements, and that the Python and SQL forms agree row by row |
| `backend/app/scripts/backfill_retired_not_out.py` | Repairs a stored not-out flag without re-syncing |
| `backend/app/routers/manual_entries.py` | The Manual Games CSV importer and its preview/resolve/commit wizard |
| `backend/verification/verify_manual_games_import.py` | The suite that pins the import contract, including the blank-player-name row |
| `docs/betterimport-historical-csv.md` | The season-totals import path and its overlap rules |
| `tools/hamilton_veterans_import/` | A different club, a different source format, the same destination |
