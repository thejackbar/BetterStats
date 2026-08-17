# Payneham Cricket Club — historical import from "Runs Galore"

Everything here was read out of the club's own two record books, published on their
website as PDFs:

- Volume 1, current competitions — <https://www.paynehamdukescc.com/Records/Runs%20Galore%20Volume%201%20Issue%2019-1.pdf> (143 pages)
- Volume 2, historic teams — <https://www.paynehamdukescc.com/Records/Runs%20Galore%20Volume%202%20Issue%2019-2.pdf> (119 pages)

Both carry a real text layer, so nothing here is OCR or guesswork. The scripts
beside these files re-read the PDFs and rebuild every CSV, so a later issue of the
book can be run through the same pass.

## Import in this order

The order matters: awards and partnerships link to a player by name, so the roster
has to exist before they land, or they import as loose names with no profile behind
them.

| # | File | Screen | Rows |
|---|------|--------|------|
| 1 | `1_payneham_players.csv` | `/admin/import` (BetterImport) | 508 players |
| 2 | `2_payneham_awards.csv` | `/admin/awards` → bulk import | 1,643 awards |
| 3 | `3_payneham_partnerships.csv` | `/admin/partnerships` | 124 stands |

Files 4, 5 and 6 have no screen to go to yet — see below.

### 1. Players

Columns are BetterImport's own template. Every row is a career row
(`Season = "Prior Seasons & Adjustments"`), which is the right shape here because
the book reports careers, not season-by-season lines.

- **482 names come from the First XI cap list** (cap number and debut season in the
  `Notes` column). Most carry no figures — the book doesn't give per-player numbers
  for everyone, and the point of these rows is to put the club's real roster in
  place for the awards and partnerships to attach to.
- **27 players carry career figures**, taken from the WHOLE OF CLUB leading
  runscorers, leading wicket takers and most dismissals tables. Those figures were
  checked line by line against the book (JW Stagg 8,544 runs at 25.35 from 309
  matches; JSH Bickle 880 wickets from 23,537 balls at 11.13; AJ Wilton 284 catches
  and 88 stumpings).
- A career total imported this way is **safe against the synced Cricket Australia
  data**. BetterImport's reconciler only ever adds `max(0, club total − what we
  already hold)`, so Stagg's 8,544 can't double up with the seasons already synced.

**The per-competition figures are deliberately left out of this file.** Adding a
player's 1st XI, 2nd XI and 3rd XI lines together disagrees with the book's own
whole-of-club lists — HJ Davis reads 768 wickets across two competitions but is
nowhere in the club top ten, which starts at 429. Rather than import a number the
club's own book contradicts, those figures sit in
`6_payneham_career_by_competition.csv` (471 rows) for someone to look at and decide
on.

### 2. Awards

Columns are the achievements template. Three kinds of row:

- **694 club trophies** — every honour board in the book, under its own name:
  H R James Memorial Trophy (club batting aggregate), N T Patten Memorial Trophy
  (club bowling), A A Parham (outstanding batting performance), R K Saunders
  (outstanding bowling), I W Scott Trophy, B G Easther, J S H Bickle, M R Hann,
  Mary Elizabeth Hicks (club champion), Grant Wasley Medal, Tony Durdin Medal,
  Von Einem Medal, and the consistency awards.
  The consistency trophies were renamed over the years and each row carries the
  name that was on the trophy that season — L A Walkely 1958–75, Gordon Clark
  1977–97, 'Clacka' Clark 1998–2004, W D Gillard 1994–2015, R G Walsh 2016 on,
  G F Vincent for the sub juniors.
- **491 captaincies**, as `Office Bearer` / `Captains` (1st XI Captain, 2nd XI
  Captain, Under 17 & Under 16 Captain, and so on), 1932/33 to 2023/24.
- **458 First XI caps**, as `Milestone` / `First XI Caps`, with the cap number in
  the detail column.

Where the book records what the award was won with, it is kept in `Detail`
("1st XI 129*", "672 points", "#5").

### 3. Partnerships

Columns are the partnership-records template, `Season` being the season's start
year, as that importer expects. Covers the whole-of-club best stand for each of the
ten wickets plus each team's own list. The extra `Opposition` column is ignored on
import — it is there so a row can be checked against the book.

## What has no home in the app: team records

The page you sent — highest and lowest innings total, the same two against, and the
biggest outright winning and losing margins — **cannot be imported today.** There is
no store for it and no screen that would show it. The Records page has a Team tab,
but it only holds Most Matches Played and Most Seasons Played, both derived from
player rows. Nothing in the app records "8/488 v Woodville, March 1948".

The data is extracted and waiting:

- **`4_payneham_team_records.csv`** — 732 innings totals across every team, both for
  and against, plus the per-ground tables (`Scope` is `Club`, or the ground name for
  a Payneham Oval or Caterer Oval record). The 1st XI rows match the page you sent
  line for line.
- **`5_payneham_margins.csv`** — the 42 biggest outright winning and losing margins,
  split by innings / runs / wickets, with both sides' scores as the book prints
  them. Only the 1st XI section carries these tables.

Building a home for this is a real piece of work, not a config change: a table to
hold a team record, an admin screen to import and edit it, and a Team tab on the
public Records page to show it. Worth deciding on separately.

## Rebuilding these files

```
apt-get install poppler-utils          # pdftotext
python3 parse_awards.py                # -> out_awards_club.csv
python3 build_imports.py               # -> the six numbered CSVs
```

Both scripts expect `rg1.pdf` (Volume 1) and `rg2.pdf` (Volume 2) beside them. The
PDFs themselves are not committed — they are the club's, and they are 23 MB.

## Two things to expect after importing

**Names are initials.** The book writes "JW Stagg" and "K J Duke"; Cricket Australia
gives us "Jack Stagg". The importers match on surname plus first initial, so most
will land on the right person, but a pass through Merge Players afterwards is worth
budgeting for. Anything that doesn't match creates a new player, which is the
correct outcome for the hundreds of pre-2000 names that have no CA record at all.

**The book's own figures don't always agree with each other.** The whole-of-club
lists and the per-competition lists disagree for at least one player (see above).
Where they conflict, these files follow the whole-of-club list and leave the rest
out rather than pick a side.
