# BetterFantasyCricket release notes

## v9.106.6 (2026-10-05): unsettle, live points on a long round, Better HQ competitions list

Reported: a round settled by accident could not be undone; a two-week round showed no points until it ended; Better HQ could not see every club's competition.

- `fantasy_engine.unsettle_round` and `POST /club-admin/fantasy/rounds/{id}/unsettle`. Deletes the round's `fantasy_player_round_scores`, deletes squad round rows that carry no chip or transfer, clears scoring on the rest, blanks the round's head-to-head fixtures, recomputes pool and squad totals (`fantasy_squad.recompute_squad_totals` now zeroes squads with no rows left) and subtracts the banked free transfer. Status goes to `upcoming` if the round's `end_date` is today or later (it is still running and is refreshed straight away), otherwise `unsettled`.
- `fantasy_engine.refresh_live_round`, run by the nightly `settle_all_fantasy` and by `settle-due` for rounds that have started and not ended. `score_squads_for_round(rollover=False)` skips the free-transfer rollover.
- `public_fantasy.live` used `squad.total_points + round points`; with provisional rows stored that counted the round twice. It now subtracts the stored round row first.
- `GET /club-admin/fantasy/super/competitions` (super admin) and `SuperFantasyCompetitions.jsx`. `switchClub` takes an optional landing path.
- Caught while verifying: `routers/fantasy.py` had no `text` import, which would have 500ed the new endpoint.
- Verified with `verification/verify_fantasy_unsettle.py` against a real Postgres; `--control` against HEAD fails on the missing route and the double-counted live rank. Not driven in a browser.
