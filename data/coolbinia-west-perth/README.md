# Coolbinia West Perth — CricketStatz export

Scraped from the club's CricketStatz site (club 35117) with
`tools/cricketstatz_scrape.py`. Covers **55 seasons, 1963/64 to 2025/26**.

Regenerate with:

    python tools/cricketstatz_scrape.py --club 35117 --out data/coolbinia-west-perth

## The two import files

| File | Screen | Rows |
| --- | --- | --- |
| `betterimport_stats.csv` | `/admin/import` | 2,949 |
| `partnership_records.csv` | `/admin/partnerships` | 14,950 |

Both were run through the app's own parsers before being committed. Every
column in the stats sheet auto-maps at full confidence, every row reconstructs
with no warnings, and all 14,950 stands pass the partnership importer's checks
with nothing skipped and nothing rejected.

### betterimport_stats.csv

One row per player per season, for 843 players. Grade is left blank: a season
total spans every grade the player turned out in, and splitting it would need a
season-by-grade breakdown the site does not publish.

Bowling is carried as **Overs in cricket notation** rather than balls. The
figure came off the site as an exact ball count, but the importer has no header
synonym for balls bowled and reads "Balls Bowled" as balls *faced*; overs map
cleanly and convert back to the same count, so nothing is lost. Checked: the
whole club round-trips to 660,972 balls, matching the site exactly.

Thirteen rows sit under **"Prior Seasons & Adjustments"**. The club's career
totals are larger than the sum of its seasons because some matches were recorded
with no season against them — about 2.3% of all runs. That shortfall goes in the
residual bucket the importer already has, so career figures still add up.

### partnership_records.csv

Every stand the site holds, with both batters' full names, the wicket, the runs,
the not-out flag, the season start year, and the grade. Grade is not in the
partnership report, so each stand is joined to its match through the match id
the report links to — 1,897 of 1,897 matches carry one, so the join is complete
rather than a name-and-date guess.

## Reference files

- `matches.csv` — 1,897 results with date, grade, venue and outcome.
- `players.csv` — 867 players with their CricketStatz ids.
- `player_grade_totals.csv` — career totals split by grade, 2,524 rows across 22
  grades. An **alternative** to the season sheet, not an addition: importing both
  would count everything twice.

## What was left out, and why

- `stats_redacted_players.csv` (12 rows) and 46 of the partnership rows involve
  juniors whose names Cricket Australia withholds. The site prints them as
  `********1` and gives the profile a bare number, so the only "name" available
  is a sequence number. Importing that would create players called "1" and "2",
  so they are set aside instead. They account for 424 runs.
- `partnerships_unmatched.csv` (229 rows) — stands the importer would reject:
  178 whose match is not in the results list so no grade could be resolved, 46
  involving a redacted junior, and 5 recorded as 11th-wicket stands.

## Known gaps

Three players' match counts come out 1–4 games higher than the site's own
all-time figure (Jeff Stephenson, Gregory Martin, Steven Freind). The season
boards and the career board disagree in the source data. Everything else —
innings, not-outs, runs, wickets, catches, stumpings and run-outs — reconciles
exactly across all 843 players.

Names come from the profile-link slug, never the visible cell. The tables print
"Chandratilake N", which would not match a roster holding "Nilan Chandratilake".
