# BetterFantasyCricket release notes

## v9.106.6 (2026-10-05): unsettle, live points on a long round, Better HQ competitions list

Reported: a round settled by accident could not be undone; a two-week round showed no points until it ended; Better HQ could not see every club's competition.

- `fantasy_engine.unsettle_round` and `POST /club-admin/fantasy/rounds/{id}/unsettle`. Deletes the round's `fantasy_player_round_scores`, deletes squad round rows that carry no chip or transfer, clears scoring on the rest, blanks the round's head-to-head fixtures, recomputes pool and squad totals (`fantasy_squad.recompute_squad_totals` now zeroes squads with no rows left) and subtracts the banked free transfer. Status goes to `upcoming` if the round's `end_date` is today or later (it is still running and is refreshed straight away), otherwise `unsettled`.
- `fantasy_engine.refresh_live_round`, run by the nightly `settle_all_fantasy` and by `settle-due` for rounds that have started and not ended. `score_squads_for_round(rollover=False)` skips the free-transfer rollover.
- `public_fantasy.live` used `squad.total_points + round points`; with provisional rows stored that counted the round twice. It now subtracts the stored round row first.
- `GET /club-admin/fantasy/super/competitions` (super admin) and `SuperFantasyCompetitions.jsx`. `switchClub` takes an optional landing path.
- Caught while verifying: `routers/fantasy.py` had no `text` import, which would have 500ed the new endpoint.
- Verified with `verification/verify_fantasy_unsettle.py` against a real Postgres; `--control` against HEAD fails on the missing route and the double-counted live rank. Not driven in a browser.

## v9.106.7 (2026-10-05): view the public Fantasy pages as any team

Reported: an admin wanted to get inside the public page (`/fantasy/<token>`) and see every page as each team.

- Admin: `View as` on Registered players (`ManagersCard`) calls `POST /club-admin/fantasy/view-as` (MANAGE_FANTASY, club-scoped manager, needs the club's link token) and opens `/fantasy/<token>` in a new tab opened before the request so popup blockers allow it.
- Public: `landing` returns `view_as`; `ViewAsBar` shows an admin banner, a team switcher (`GET /view-as/managers`, `POST /view-as/switch`) and Exit (`POST /view-as/exit`, which needs no sign-in because it only clears the cookie). The Settings sign-out becomes Exit while viewing.
- Checked: `verification/verify_fantasy_view_as.py` (29 checks, real Postgres, signed cookies, the write guard over HTTP; `--control` against HEAD fails on the missing view-as and guard) and a Chromium run with the API stubbed (bar, switch and exit requests on the wire, no overflow at 390px). Writes were not tried against the real screens, only the guard.

## v9.106.8 (2026-10-05): merge carries Fantasy picks, team and score overrides

Reported (Leederville): a player added to the pool by hand before he had played was picked by managers, then merged into his real record and vanished from their teams. The club asked for a way to get him back, to type scores in, and to override team selection from round 1.

- Root cause: no Fantasy table was on `merge_carry.CARRIED`. Added `fantasy_squad_players`, `fantasy_pool_players`, `fantasy_player_round_scores`, the three player columns on `fantasy_squad_round_scores`, `fantasy_transactions`, `fantasy_draft_picks`, `fantasy_drafts.lot_player_id`, and both columns of `fantasy_waiver_claims`, each club-guarded for club-to-club merges. `_rewrite_fantasy_lineups` points stored lineup JSON at the keeper (not undone; the next settle rewrites it).
- Repair for earlier merges: `services/fantasy_merge_repair` plus `python -m app.scripts.restore_fantasy_merged_picks <org|all> [--apply]`. Evidence is the squad's last scored lineup snapshot before the merge. Unsettling a round clears that snapshot, so a club that unsettled before the repair has no evidence for that round and is handled by hand with the team editor.
- `POST/DELETE /club-admin/fantasy/squads/{id}/players`, `PUT/DELETE /rounds/{id}/players/{id}/score`, `GET /season/{id}/manual-scores`, `GET /season/{id}/player-search`; `/managers` and `/managers/{id}/teams` report `pick_count` and `squad_size`. UI in `shared.jsx` (`SquadEditor`, `ManualScoresCard`).
- Also fixed: a re-settle of a scored round granted a second free transfer.
- Checked with `verification/verify_fantasy_player_merge.py` (34 checks, real Postgres; `--control` runs the merge with HEAD's `merge_carry` and loses the pick) and the existing merge-carry, unsettle, view-as and rounds suites. The new screens were built and compiled but not driven in a browser.

## v9.106.8 follow-up: finding who is missing

Leederville's dry run found no lineup evidence (round 1 had been unsettled, which clears the snapshots), only 15 short teams. Added to `restore_fantasy_merged_picks`: (a) for short teams the dry run now lists the players merged since Fantasy began, and (b) `--backup-url` reads a backup restored into a scratch Postgres and follows each pick the backup holds for a vanished player through the merge log to the live record (`find_lost_picks_from_backup`). Pick a backup from just before the merge. Undoing an old merge does NOT bring picks back: undo only returns rows listed in `merge_logs.carried_row_ids`, and merges before the fix logged nothing for Fantasy; it also takes the merge out of the log the repair reads. The verify script's control now pins `CONTROL_REV` instead of `HEAD`, which moved when the fix was committed.

## Scarborough: hand-added pool players with no stats

"Add new player" creates a brand-new club record with no games (`add_new_player`). The real games sync onto a separate record (their own CA id), so the hand-added player scores 0 while a same-name twin holds the stats. `services/fantasy_pool_check.zero_stat_pool_players` and `python -m app.scripts.fantasy_zero_stat_players <org|all>` (read only) list each pool player with no games this season and the same-name profile that has them; the fix is to merge the pair (the merge now carries picks and the pool entry) and re-settle. Name match is on the sorted words of the name, so "Taylor, Ashton" matches "Ashton Taylor". Covered by section 8 of `verify_fantasy_player_merge.py`.

## Leederville: merges that were undone

The first dry run listed 7 merges but not Raja Pannu: the merge had been undone. Undo re-creates the player under his own id but not his picks (the merge had already cascaded them away), and `fantasy_merge_repair` read only non-undone merges, so neither the lineup snapshots nor `--backup-url` would have found him. Both paths now treat an undone merge as "restore him as himself" (`keep_id = removed_id`), `find_lost_picks_from_backup` restores a same-id pick only when a merge of that player was undone (any other pick a team no longer holds may be a legitimate transfer), and the merged-players list marks undone merges. Section 9 of `verify_fantasy_player_merge.py`.

## Leederville: no backup key, so read the dead rows

`restore.sh check` needs the age private key, which the club operator did not have. Postgres keeps a deleted row's old version until VACUUM, and the merges had deleted only ~30 picks from a few hundred (under autovacuum's 50 + 20% threshold), so `read_deleted_picks` reads the old `fantasy_squad_players` tuples with pageinspect (uuid columns at fixed offsets 0, 16, 32, then `role` as a short varlena and the two booleans), keeps the newest version of each (squad, player), and feeds them through the same matching as the backup route (`_lost_from_rows`). The column layout is checked first and it refuses to read if it differs. Section 10 of `verify_fantasy_player_merge.py`.

## Leederville: filling the teams that cannot be recovered

Six teams stayed short with no trace of who they lost. `services/fantasy_fill_short.plan_fill` and `python -m app.scripts.fantasy_fill_short_teams <org> [--apply]` add, for each missing place, the pool player with the most season points the team does not hold, taking the role the team is short of first (largest gap first) so the quota is met; ties go to the higher price, then name. Lock and budget are ignored, an audit entry is written per team, rounds are re-scored from round 1. Dry run by default and it warns when every chosen player has 0 points (the season may not have started). This is a club decision rather than a repair: the chosen players are not what the manager had. Section 11 of `verify_fantasy_player_merge.py`.

`fantasy_fill_short_teams --only-merged [--merged-since YYYY-MM-DD]` limits the candidates to `merged_player_ids`: the kept profile of every merge since Fantasy began (or the date), plus the merged-away record when the merge was undone (both are live and are the same person). Still ranked by season points, so the real profile with games wins over its hand-added twin. Section 12 of `verify_fantasy_player_merge.py`.

## v9.106.9 (2026-10-05): the Merge button

`GET /club-admin/fantasy/season/{id}/unmatched-players` (pairs with a same-name twin that has games, plus hand-added players waiting) and `POST .../merge-player`. `HandAddedPlayersCard` on Fantasy > Registered players. Chosen so Scarborough (which had not merged anything yet) could merge safely without the command line. Verified with sections 13 and 14 of `verify_fantasy_player_merge.py` (91 checks; 13 proves nothing is lost across all 11 Fantasy player columns, 14 covers the endpoints: only a listed pair is accepted, the reversed pair is refused, the carried and re-scored result) and a Chromium run with the API stubbed (the exact request on the wire, the confirm text, the flash, no overflow at 390px after letting the lines wrap).

## v9.106.10 (2026-10-05): Scarborough, players who played but scored 0

Reported: Ashton Taylor and David Gardner had played (Play-Cricket) and were on 0 in many teams; the My Team page was cut off on the right.

- Checked against the public API: Gardner's 3 Oct Men's Third Grade scorecard (did not bat, bowled 0-43) is in the system under his own profile and is worth +4 for the appearance alone, so the data was there. The engine did not see it, most plausibly because the round was settled before that scorecard landed and nothing re-checked a scored round. Ashton Taylor is a separate data case: his synced profile only has a did-not-bat row in the U17s game, while his season totals (8 runs, 2-21) equal the line the 3rd grade scorecard records for "Taylor, Angus". Either one person has two profiles or the scorecard feed mislabels him; the club has to confirm on Play-Cricket before anyone merges Angus into Ashton.
- Fixed: `round_drift`, `refresh_recent_rounds` (14 days), `from_snapshot` re-settle, drift shown in `list_rounds` and on the overview, `python -m app.scripts.fantasy_round_drift <org> [--apply]`.
- Fixed: engine game reads used `seasons.organisation_id` (rule 2). Not the cause here (every Scarborough game is owned by Scarborough) but a real hole.
- Fixed: My Team desktop grid used `1fr 340px`, which cannot shrink below its content, so the rail overshot by ~240px at 1920 and the page scrolled sideways from 1024 up; now `minmax(0, 1fr)` with wrapping cards. Measured with Playwright at eight widths before and after.
