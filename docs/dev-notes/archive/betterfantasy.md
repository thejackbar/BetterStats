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
