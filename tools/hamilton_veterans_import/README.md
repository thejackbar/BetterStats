# Hamilton Veterans season statistics extract

The club's `Hamilton_O60s_Season_Statistics.xlsx` turned into CSVs that
`/admin/import` (BetterImport) can read. Batting History, Bowling History and
Games Played are the tabs that carry the history; the per-season tabs
(`24-25 Batting`, `19-20Bowling`, and so on) are the same figures a season at a time and
were not needed.

## What comes out

| File | What it is |
|---|---|
| `hamilton_import_season_by_season.csv` | A row per player, season and competition: 497 rows, 92 players, 2010/11 to 2024/25. |
| `hamilton_import_season_totals.csv` | The same figures with the competitions added together, one row per player and season. Use this instead if the club would rather not carry a competition label. |
| `hamilton_import_season_by_season_guests.csv` | The 38 players from the "Extras" tabs who turned out for Hamilton but belong to Geelong, Ballarat, South East Coasters and so on. |
| `hamilton_import_season_totals_guests.csv` | Those same guests, competitions added together. |
| `hamilton_import_pre_online.csv` | **The one to upload.** The same per-competition rows, stopping at 2022/23 where Cricket Australia's own record begins, so nothing in it can overlap what is already online. |
| `hamilton_import_pre_online_guests.csv` | The guests' half of the same. |
| `hamilton_players.csv` | The roster the CSVs name, with debut date, seasons, games, runs and wickets. |
| `hamilton_seasons.csv` | The 14 seasons the data covers. |
| `hamilton_data_notes.csv` | Every figure worth a second look before importing. |
| `hamilton_verification.csv` | Where the workbook's own career total column disagrees with its own season rows. |

## Before you upload

Create the seasons first. The wizard matches a season by name, and the Seasons
step has "+ Create new season" in the dropdown beside each unmatched label, so
you can mint them as you go. Hamilton holds 2010/11, 2011/12, 2012/13, 2016/17,
2017/18, 2018/19, 2019/20 and the three synced ones, so the five still to create
are **2013/14, 2015/16, 2020/21, 2021/22 and 2022/23**. A season left unmatched
is not lost, but its figures arrive as one "Prior Seasons & Adjustments" line
rather than under their own year.

Then upload at `/admin/import`. The column names are already the ones the wizard
maps itself; `grade_label` carries the competition.

### Which file

**`hamilton_import_pre_online.csv` is the one to use.** It stops at 2022/23,
which is where Cricket Australia's own record for this club begins. Nothing in
it overlaps anything already online, so there is nothing to reconcile: the
club's own figures stand for 2010/11 to 2022/23, and CA's stand for 2023/24
onwards.

The full `hamilton_import_season_by_season.csv` also carries 2023/24 and
2024/25, which CA already holds. A row for a season CA covers is only recognised
as overlapping when its competition matches a CA grade, and most of this club's
competitions have no CA equivalent, so those two seasons would be added on top
of CA's figures rather than deferring to them. Use the full file only if the
club decides its own book should replace CA's for those years, and match the
grades carefully if so.

### The competitions

All six read NO MATCH, because CA carries none of them under these names. Use
"+ Add as a new historical grade" on each: it creates the competition across the
seasons the sheet records it in, so VCV and Border Cup become grades the
Leaderboard and Records can filter by. "No online equivalent" is the lighter
option, keeping the label on the figures without creating a grade.

CA does hold a grade called **Border Cup** (and "Over 60 Mixed", "Echuca
Division 2 Murray", "Echuca Division 3 Goulburn") from 2023/24 on. Adding Border
Cup as a historical grade for the earlier seasons is correct and does not clash:
a grade row is per season, and filters group by name.

## How the workbook was read

- A history tab is block structured: the player's name sits alone in column A,
  their seasons run down column B, and the stat columns repeat once per
  competition under a merged banner.
- **Not out = "Rt No" + "No".** The club's own average column is runs over "Out", so
  a retirement counts as a not out, which is how veterans cricket is scored.
- Overs are cricket notation. Adding two competitions together converts to balls
  first, so 26.2 + 13.5 comes out as 40.1 rather than 39.7.
- Best bowling `0/2` becomes `0-2`.
- Games played comes from the Games Played tab, whose competition split is finer
  than the history tabs'. One-off 40-over and 20-over games, the National O60s
  Championships and the Portland tournament all fold into "One Off Games", which
  is the single column the batting and bowling tabs keep them under.

Two traps worth knowing if this is ever re-run:

- **Each tab carries spare unnamed template blocks** below the last real player:
  season rows and their own zeroed total row, with nobody's name on them. Reading
  past a player's total row hangs those on whoever was named last, and their
  zeroed total then overwrites the real one. That silently lost Gary Milich's
  bowling and Greg Williams' wickets on the first pass.
- **A few of the workbook's own total columns are wrong.** Peter Franklin's
  career total leaves his WillowFest column out of the formula (143 runs where
  his own season rows add to 210); Guy Eastwood's games total says 1 where his
  rows say 3. `hamilton_verification.csv` lists all seven. The CSVs carry what the
  season rows say.

## Partnerships

There is no partnership data in this workbook. No tab records two batters and a
stand. `/admin/partnerships` takes `Batter 1, Batter 2, Runs, Wicket, Season,
Not Out, Grade`, and none of those pairs can be recovered from season aggregates.
If the club keeps a record of its big stands somewhere else, that file can go
straight in.

## Re-running

```
python3 tools/hamilton_veterans_import/extract_hamilton_stats.py <workbook.xlsx> [outdir]
python3 tools/hamilton_veterans_import/verify_hamilton_extract.py <workbook.xlsx> [outdir]
```

The verifier reads the workbook's own career total columns and the Games Played
summary block. Neither is used to build the CSVs, so it is an independent check
on the parse. Needs `openpyxl`.
