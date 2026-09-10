# CSFW extractor

Reads Cricket Statistics for Windows `.av` season databases and exports every
match, scorecard and player record as CSV/JSON. Written for Payneham Cricket
Club's archive (206 season files, 1928–2025).

* `CSFW_FORMAT.md` — the reverse-engineered file format and the evidence for it
* `csfw_format.py` — the reader (`Season`)
* `extract_csfw.py` — CLI: directory of `.av` files → CSVs
* `verify_csfw_format.py` — verification suite (11 checks, including controls)

```bash
python3 extract_csfw.py /path/to/av-files -o out/
python3 verify_csfw_format.py /path/to/av-files
```

## Mapping to BetterCricket

The CSFW record maps almost 1:1 onto the existing `manual_*` tables that the
CricketStatz importer already writes, so this needs no new schema.

| CSFW | BetterCricket |
|---|---|
| innings pair → match | `manual_games` (`played_at`, `opposition`, `venue`, `result`, `notes`) |
| performance, batting side | `manual_batting_innings` (`batting_position`, `runs`, `balls`, `fours`, `sixes`, `dismissal_type`, `not_out`, `did_not_bat`) |
| performance, bowling side | `manual_bowling_spells` (`overs`, `maidens`, `runs`, `wickets`, `wides`, `no_balls`) |
| performance, fielding | `manual_fielding_stats` (`catches`, `catches_wk`, `stumpings`) |
| fall of wickets | `manual_fall_of_wickets` (`wicket_number`, `score_at_fall`) |
| player name table | resolve through `services/import_ingest.match_players` |

Notes for whoever wires up the import:

* CSFW stores **overs in cricket notation** (`6.3` = 6 overs 3 balls), which is
  the same convention `manual_bowling_spells.overs` uses. Convert to balls with
  the season's own balls-per-over — **8 before 1972, 6 after** — not a hardcoded 6.
* Give each match a deterministic external id (the way `cricketstatz_match_id`
  works) so a re-import corrects rather than duplicates.
* `manual_fielding_stats.run_outs` cannot be filled — see the limitations in
  `CSFW_FORMAT.md`.
* A CSFW file has **no grade field** and holds several grades at once, so grade
  has to be supplied or inferred. This is the main open question before import.
