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
