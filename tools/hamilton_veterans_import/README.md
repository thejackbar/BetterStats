# Hamilton Veterans season statistics extract

The club's `Hamilton_O60s_Season_Statistics.xlsx` turned into CSVs that
`/admin/import` (BetterImport) can read. Batting History, Bowling History and
Games Played are the tabs that carry the history; the per-season tabs
(`24-25 Batting`, `19-20Bowling`, and so on) are the same figures a season at a time and
were not needed.

## What comes out

| File | What it is |
|---|---|
| `hamilton_import_season_by_season.csv` | **The one to upload.** A row per player, season and competition: 497 rows, 92 players, 2010/11 to 2024/25. |
| `hamilton_import_season_totals.csv` | The same figures with the competitions added together, one row per player and season. Use this instead if the club would rather not carry a competition label. |
| `hamilton_import_season_by_season_guests.csv` | The 38 players from the "Extras" tabs who turned out for Hamilton but belong to Geelong, Ballarat, South East Coasters and so on. |
| `hamilton_import_season_totals_guests.csv` | Those same guests, competitions added together. |
| `hamilton_players.csv` | The roster the CSVs name, with debut date, seasons, games, runs and wickets. |
| `hamilton_seasons.csv` | The 14 seasons the data covers. |
| `hamilton_data_notes.csv` | Every figure worth a second look before importing. |
| `hamilton_verification.csv` | Where the workbook's own career total column disagrees with its own season rows. |

## Before you upload

Hamilton currently holds Summer 2023/24, 2024/25 and 2025/26, so the other
eleven seasons in `hamilton_seasons.csv` do not exist yet. Create them as you go:
the Seasons step of the wizard has "+ Create new season" in the dropdown beside
each unmatched label, which mints the season on the spot. Any season left
unmatched is not lost either. It lands in the career "Prior Seasons &
Adjustments" line, so the career total stays right but the season-by-season table
stops at 2023/24.

The six competitions in the Grade column are the same story: none of them exist
online, so the Grades step will show all six as NO MATCH. Use "+ Add as a new
historical grade" on each one, which creates it across the seasons the sheet
records it in, so VCV and Border Cup become grades you can filter the
Leaderboard and Records by. "No online equivalent" is the lighter option: it
keeps the label on the figures without creating a grade.

Then upload at `/admin/import`. The column names are already the ones the wizard
maps itself; `grade_label` carries the competition, which is a display label only.
Nothing is added on top of what Cricket Australia already holds. The reconciler
takes the club's figure as the truth and derives only the part CA is missing.

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
