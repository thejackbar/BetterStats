# Archive: scorecards-fixtures-and-lineups

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: The match scorecard endpoint and page, fill-in players, public fixtures and lineups.
Read the distilled rules first: `docs/dev-notes/guides/scorecards-fixtures-and-lineups.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L10379-10459 -->
## A two-day match's other two innings, and a card that would not open (v9.54.1, Aug 2026)

Reported by a club trialling the platform, off one email: a 2025/26 first-grade
grand final showed no second innings, and a game uploaded from a PDF sat in the
Games list returning `Error: Internal Server Error`.

- **THE BACKEND HAD BEEN RETURNING ALL FOUR INNINGS THE WHOLE TIME, and
  establishing that first is what stopped this being chased as a sync bug.**
  `GET /games/{id}/scorecard` answers with `innings_totals` keyed 1-4 and
  batting/bowling rows against each. `MatchScorecard.jsx` took `innings[0]` and
  `innings[1]` and dropped the rest, so each side's SECOND innings was gone.
  Nothing needed re-syncing.
- **THE MARGIN WAS ALSO WRONG, and only the control run surfaced it.** With
  half the match missing, `marginText` compared innings 1 against innings 2 and
  printed **"won by 71 runs"** for a game actually won by 7 wickets. It works
  off each side's AGGREGATE now, so an innings victory ("by an innings and N
  runs"), a chase (wickets in hand, read off the LAST innings) and a defence
  (runs) all fall out of the same function.
- **`splitSides` FILES AN INNINGS UNDER WHOEVER BATTED, NOT BY ODD/EVEN
  POSITION.** A follow-on has one side batting twice in a row, so alternating
  is wrong exactly when it matters; the batting team's own name decides it, and
  alternating is only the fallback for an innings with no name recorded.
- **THE WON BADGE IS DECIDED ONCE PER MATCH, from the same split**, so a team's
  two innings can never disagree about it — the trap `winnerSide`'s own comment
  already documents for the two-card case, which now has four cards to keep
  honest.
- **Two columns means one column per team**, since innings 1 and 3 stack in the
  first and 2 and 4 in the second. Falls out of the existing `lg:grid-cols-2`
  rather than being arranged.
- **Fall of wickets and partnerships needed nothing** — both already grouped on
  `innings_number`, which the control run confirms (they pass against the
  broken code).

### `manual_batting_innings` has no `caught_behind`, and the scorecard read it anyway

- **EVERY manually uploaded card 500'd, on every club, from the day photo
  upload shipped.** `get_scorecard` shares one row-building path between the
  synced and manual tables (`BI = ManualBattingInnings if is_manual else
  BattingInnings`) and read `bi.caught_behind` unconditionally. That column is
  SYNCED-ONLY (migration 075); the manual table never had it, so the row build
  raised `AttributeError` before the response was assembled.
- **NULL, not False, and not a new column.** The AI scorecard reader
  transcribes a dismissal exactly as the card writes it and never judges
  whether the catcher was the keeper, so there is nothing to store. NULL is the
  honest answer and every reader already treats it as a plain catch — the same
  call migration 075's own manual branch made for the effective view.
- **THIS ONLY BECAME REACHABLE IN v8.76.1's WAKE.** An uploaded card was
  invisible on the public Games page until the grade-less season-filter fix
  listed it; the moment it could be clicked, it 500'd. The two are one story,
  a year apart.
- **The blast radius was confirmed, not assumed**: probing all 332 of the
  reporting club's pre-2010 games returned exactly one non-200, the reported
  game — so the club has one manual card and it is the one that failed.
- **Verified against a real Postgres**
  (`backend/verification/verify_manual_scorecard.py`, 24 checks through the
  SHIPPED route body over a manual game seeded the way the upload commit
  writes one: the card opening at all, both teams and their totals, the
  opposition half read out of `extracted_payload` and never linked to one of
  our players, an untracked boundary count still NULL, and the session usable
  afterwards) **with a control run**: with the fix stashed the suite dies at
  check 1 on exactly the reported `AttributeError`.
- **A CHECK THAT MEASURES THE HARNESS IS NOT A CHECK.** The untracked-boundary
  check failed on the first cut because setting `fours=None` on the model does
  NOT store NULL — SQLAlchemy reads an explicit None as "unset" and lets the
  `server_default="0"` apply. The seed forces it in SQL now.
- **Driven in Chromium**
  (`frontend/verification/verify_scorecard_innings_browser.mjs`, 28 checks
  against the REPORTED MATCH's own live payload: all four innings drawn and
  labelled in batting order, each carrying its own score, the winner marked on
  both its cards and neither of the other side's, the header's "31 & 128", the
  7-wicket margin, and an ordinary one-day game reading exactly as it did)
  **with a control run**: 12 fail against the previous commit, including the
  reported "got 2" innings and the wrong margin.
- **`font-display` alone matches the CREST as well as the team name** —
  `TeamBadge`'s initials fall back to the same face, so the first cut of the
  probe read "CS" where the card says "Collegians…". Address the name by its
  own `.truncate`.
- **Noticed, NOT fixed**: `_manual_opp_from_payload` sets no `logo_url` on a
  manual innings, so an uploaded card draws initials badges rather than crests.
  Pre-existing, and a manual upload has no club GUID to resolve one from.

<!-- END original CLAUDE.md L10379-10459 -->
<!-- BEGIN original CLAUDE.md L13038-13200 -->
## Public Fixtures + Lineups pages, and the CA team-list route (v8.94.0, Jul 2026)

The public club site's **Games** dropdown was Results + Ladders; it now also has
**Fixtures** (`/{slug}/fixtures`) and **Lineups** (`/{slug}/lineups`). Both are
live off the Grassroots feed — nothing new is persisted.

- **The lineup route is the PLAIN match record**: `GET /scores/matches/{id}`
  **without** `responseModifier=includeScorecard`. It carries
  `teams[].players[]` (`{participantId, name, shortName, roles}` — roles being
  `Captain` / `Wicket Keeper`), `teams[].nonPlayingMembers[]` (coach/manager)
  and top-level `officials` (umpires). **Verified live against an in-season
  winter fixture: an UPCOMING match returns a side as soon as its club
  publishes it**, and an empty `players` list for a side that hasn't — so "not
  named yet" is a normal state, not an error. `matchSummary.teams` (not the
  top-level `teams`) is where `isHome`/`isWinner`/`scoreText` live — the same
  gotcha the scorecard parser already documents.
- **`get_match_detail` / `get_matches_detail`** (`grassroots_scores_client`)
  are kept SEPARATE from `get_match_scorecard` with their own `_MATCH_TTL` of
  **5 minutes** (vs the scorecard's 15): a pre-game team list is edited right
  up to the first ball, whereas a finished scorecard is settled.
- **`services/lineups.py`** normalises a match, decides which side is ours
  (`owningOrganisation.id` against the org id first — our `organisations.id` IS
  the CA org GUID — then `club_match_keys` name matching), and resolves
  `participantId` → our players by `id` OR `grassroots_id`, **org-scoped** (the
  per-club uuid5 scheme). A redacted junior (`********`) gets their real name
  back when we hold the player. `our_lineup_players` returns
  `(players, unmatched)` for the vote engine.
- **Name-fallback fix (same day)**: two real, long-registered Applecross
  players (100+ games each) showed on the Lineups page with no photo and no
  profile link. Root cause: CA issues a **different participant GUID** for
  the same real person on this plain match-list route than the GUID our
  scorecard sync resolved them under for that exact game (verified live —
  their own scorecard endpoint correctly links them via a GUID that matches
  neither `players.id` nor `grassroots_id` on the lineup route's payload) —
  the same MyCricket/PlayHQ dual-GUID class of issue the scorecard rewrite
  documents above, just hit on a different endpoint. `resolve_participants`
  was GUID-only; it now adds the identical third-step fallback
  `games.py::get_scorecard` already uses — a `(surname, first_initial)`
  name-key match — after the id/`grassroots_id` checks fail. Confirmed against
  the real payload for both players before shipping.
- **`GET /organisations/{id}/lineups`** (public): `mode=upcoming` (falls back to
  recent games when nothing is scheduled, so the page is never blank in the
  off-season) or `mode=past` with `season_id`/`grade_id`/`offset`/`limit`
  paging. Bounded on purpose — every match is a live upstream fetch.
- **Category + Finals filters (same day)**: the Lineups page's Past tab used
  the shared `SeasonSelector`'s Gender/Games/Captain pills, which are
  wired to per-player leaderboard params it never fetches — the toggles
  rendered but silently did nothing. Fixed by giving `SeasonSelector` opt-out
  flags (`showGenderFilter`/`showFinalsFilter`/`showCaptainFilter`, all
  default `true` so every other caller — Players/Records/Leaderboard/
  Dashboard/GamesPage — is unaffected) and replacing them here with two
  filters that actually mean something for a fixture list: **Category**
  (Senior/Junior/Women's/... — how the **grade** is classified, not a player
  attribute) and **Finals** (the game's own `is_final`). Captain has no
  fixture-level meaning and was dropped, not just hidden.
  - `grade_labels.org_grade_categories(db, org_id)` returns every distinct
    grade name in the org mapped to its effective category (confirmed via
    `grades.category`, else `suggest_category`), keyed on the
    sponsor-suffix-stripped name (`strip_sponsor_suffix` — a Python mirror of
    `iq_filters.grade_base`'s SQL regex) so "B Grade (DXC Technology)" from a
    live fixture/lineup and our stored "B Grade" resolve to the same category.
    Verified against every real grade name at two live clubs (Applecross,
    Darwin) before shipping — Colts/Juniors/Under-N → junior, PSWL/Women's →
    womens, everything else → senior, matching the existing
    `suggest_category` heuristic used for the admin grade list.
  - Both filters are server-side and paginate correctly: `category` resolves
    to a `grade_id` list once (category may be an unconfirmed suggestion, not
    a DB column, so it can't go straight into SQL) and both it and
    `finals_only` are applied in `_played()`'s WHERE clause for `mode=past`,
    and as a plain Python filter over `org_grassroots_fixtures()`'s list for
    `mode=upcoming`. The response's `categories` field lists only the
    categories actually present among the org's grades, so a club with no
    Masters/Mixed grades never sees an empty option.
  - Frontend keeps the returned category list in its own state (not reset
    alongside the match data on every refetch) so the filter pills don't
    flash empty while a filter change is loading.
  - Both public pages also dropped their subtitle taglines ("straight from
    the association draw" / "straight from Play.Cricket") per direct
    instruction — a page whose eyebrow+title already say what it is doesn't
    need one.
- **Cross-linking (same day)**: a played match's lineup card now links to its
  scorecard (`/games/{match_id}` — the id is already the same `games.id` for
  every "past"/"recent"-sourced match, so no extra lookup is needed; the link
  only renders when `status === 'COMPLETED'`, which an "upcoming"-sourced
  fixture never is, so there's no dangling link to an unsynced game). A
  Fixtures-page row's "↗ Lineup" now deep-links to that exact match
  (`/{slug}/lineups?match={id}`) instead of the generic list. New `GET
  /organisations/{id}/lineups/{match_id}` (thin wrapper over
  `services.lineups.match_lineups`, same payload shape as one list entry)
  backs the deep link; `LineupsPage`'s `?match=` param renders just that one
  `MatchCard` with a "← All lineups" link, skipping the list fetch entirely.
- **Frontend**: `FixturesPage.jsx` (grouped by date, Today/Tomorrow/In-N-days
  chips) and `LineupsPage.jsx` (Upcoming/Past toggle, `SeasonSelector` on Past,
  Load more). `TeamBadge` was **extracted from `MatchScorecard.jsx` into
  `components/TeamBadge.jsx`** so the lineup match header matches the
  scorecard's; a player shows their club photo, else the club crest, else
  initials. Both pages were verified visually against live Darwin CC (in-season)
  and Applecross (off-season/past) data before shipping — see the v8.79.0 note
  for the local-dev-proxy-to-production technique.
- **Player name aliases (v8.94.2, migration 195)** — a renamed player (a
  preferred/married name) broke matching on this page and on the live
  scorecard merge, in a way the existing GUID-mismatch fallbacks couldn't
  catch: a live feed still using their OLD name shares literally no words
  with their new stored name, so even the surname-and-initial heuristic
  misses (confirmed live: Applecross's Shaylyn Wijesinghe — formerly Johnson
  — showed unresolved on the Lineups page, AND her already-synced
  `batting_innings`/`bowling_spells` rows for that competition were ALSO
  never linked to her player id at all, a pre-existing sync gap this doesn't
  retroactively fix). `player_name_aliases` (org-scoped, `alias_key ->
  player_id`, `services/player_aliases.py`'s `normalise_name_key` — lowercased,
  comma/word-order-independent, so "Wijesinghe, Shaylyn" and "Shaylyn
  Wijesinghe" key identically) is checked as an explicit tier, ahead of the
  loose surname+initial fallback, in BOTH `lineups.resolve_participants` and
  `games.py::get_scorecard`'s `_resolve_linked_id` (display-only there — never
  touches which team a row is on or its stats). **Auto-seeded** the moment a
  player is renamed (`players.py`'s `rename_player` and
  `update_player_profile`'s `display_name_override` change both call
  `seed_alias_on_rename`, `ON CONFLICT DO NOTHING` so it never blocks the
  rename itself) — so this self-heals for every FUTURE rename with no admin
  action. A rename that happened before this shipped needs the alias added by
  hand: new "Also known as" panel on the player profile edit view
  (`PlayerProfilePanel.jsx`'s `AliasManager`, `GET/POST/DELETE
  /players/{id}/aliases`, cap `MANAGE_PLAYERS`) — self-contained, saves
  immediately, not part of the "Save changes" draft flow. **Deliberately NOT
  wired into `sync.py`'s `_team_pid`** (the function that gates every
  batting/bowling/fielding/appearance INSERT) — that's the actual stats-writing
  path, a much higher-stakes surface than a display-only hyperlink, and out of
  scope for this fix; a player whose stats are missing because of this needs a
  Full Rebuild AFTER an admin adds the alias by hand (not automatic).
- **`merge_players` also auto-seeds an alias** (v8.94.3, `admin.py::_merge_players_core`):
  a merge is a rename in disguise from a live feed's point of view — the
  removed player's name has NO row to resolve to at all once they're gone, so
  a Play.Cricket team list or scorecard still using it would go from
  "resolves via the normal fallback" to "unresolved" the moment the merge
  lands. The removed player's effective display name (`display_name_override
  or name`, captured before the delete, same point the undo-log fields
  already are) is seeded onto the KEPT player via the same
  `seed_alias_on_rename`. **Known gap**: undoing a merge doesn't remove this
  alias — matches the same accepted trade-off the vote-reassignment note
  above already makes for this function ("no data lost, but not
  reference-perfect on an undo"); a stale alias after an undo is a rare,
  low-stakes case an admin can delete by hand via "Also known as" if it ever
  comes up.
- **BetterPosts lineup posts can pull from either source** (v8.94.4,
  frontend-only — no backend change, `GET /organisations/{id}/lineups` already
  returned everything needed): `AdminSocialPost.jsx`'s Lineup data step gained
  a BetterSelect / Play.Cricket toggle alongside the existing saved-XI list.
  Picking a Play.Cricket fixture (`loadLineupFromPlayCricket`) needs no second
  fetch — the list call already returns each match's full `teams[].players[]`
  with `player_id` resolved (alias-aware, per the fix above), so it maps
  straight onto the same `selectedPlayers`/`match`/`opponent` shape the
  BetterSelect handoff builds. A resolved player gets their normal roster
  record (photo, role); an unresolved one still renders using the live
  Play.Cricket name. Defaults to whichever source has data (an admin's
  explicit pick always wins from then on, `lineupSourceTouched` ref); a side
  that hasn't been published yet shows in the list but its button is
  disabled ("not published yet") rather than silently building an empty post.
- **Not built (deliberate)**: nothing here is persisted, so there's no lineup
  history beyond what the feed still serves. Also noticed while investigating:
  `matchSummary.teams` carries `wonToss`/`battedFirst`, which contradicts the
  older "the GR path can't see the toss" note elsewhere in this file — a real
  opening for the BetterIQ toss/captaincy analysis, not chased here.

<!-- END original CLAUDE.md L13038-13200 -->
<!-- BEGIN original CLAUDE.md L14030-14128 -->
## Fill-in players on the game scorecard (v8.60.0–v8.60.3, Jul 2026)

A club fielding a borrowed player (a fill-in from another club, or a Cricket
Australia junior whose name is privacy-redacted in the feed) had that
player's entire batting/bowling contribution disappear from
`GET /games/{id}/scorecard`, and the displayed innings total silently
undercounted by exactly their runs. Reported against
`games/504937fb-dd8d-417e-8a7a-c96c36897c25`: our own second innings showed
54/3 against Grassroots' real 197/5, the gap being a fill-in's 116.

- **Root cause**: every "is this participant ours?" check in
  `routers/games.py::get_scorecard`'s live Grassroots-enrichment pass
  (`known_ids`, `our_batting_fingerprints`, `our_team_roster_pids`) requires
  the participant to already be a row in `players` — which a genuine one-off
  fill-in never is (only the season-aggregate feed mints `players` rows, and
  a borrowed player never appears there). A participant on our own team's GR
  roster but not in `players` fell through a `continue` that assumed a later
  DNB-injection step would catch them; that step only resolves players
  already in the DB by name, so it silently dropped them too. A fill-in
  *bowler* fell through even further, into `opp_bowling` (misattributed to
  the opposition). The innings total was summed from the (now-incomplete)
  displayed rows rather than read from Grassroots' own authoritative
  innings total, so it inherited the gap.
- **Fix**: a roster participant not in `players` is now rendered directly on
  our own batting/bowling card, `player_id: null` + `is_fill_in: true` (the
  same shape opposition rows already use, so the frontend's existing
  `player_id`-optional `<Link>`/`<span>` rendering needs no new branch) —
  covers batted, DNB-with-a-batting-array-entry, and DNB-with-no-entry-at-all
  cases. `_fill_in_display_name` falls back to "Fill-In" (or "Fill-In (#N)"
  by batting position) only when Grassroots has no usable name (the
  redacted-junior case, `playerShortName` literally `"********"`); a normal
  fill-in's real name is shown as-is. Our own innings `runs`/`wickets` in
  `innings_totals` now prefer Grassroots' own innings total over the row-sum
  (mirrors how opposition wickets and both sides' extras were already
  sourced), so the total is correct even if a future edge case still can't
  display a row. Frontend: `FillInBadge` in `MatchScorecard.jsx` renders a
  small amber "FILL-IN" tag next to the name on any row with `is_fill_in`.
- **v8.60.1 follow-up — the v8.60.0 fix regressed on redeploy**: the same
  reported game still showed a wrong total (202 instead of 197) and two
  fill-ins (22 and 116 runs) were still missing after v8.60.0 shipped. Two
  distinct bugs, found by pulling the live GR JSON directly
  (`grassrootsapiproxy.cricket.com.au/scores/matches/{id}?responseModifier=includeScorecard`)
  and comparing it to `/api/games/{id}/scorecard`: (1) **double-counted
  extras** — GR's `innings.runsScored` is the FULL team total (batters +
  extras), but v8.60.0 stuffed it straight into `innings_totals.runs`, a
  field that has always meant bat-only runs (the frontend adds extras on
  top separately) — fixed by dropping that substitution and instead
  recomputing `innings_totals` for our own side from the fully-populated
  `batting_flat` once every row (including newly-injected ones) is in place.
  (2) **a stale junk `players` row can already exist for a redacted
  participant** — this game had *three* CA-redacted batters, not two; one of
  them (`9cc9ec36…`) already had a `players` row and a synced
  `batting_innings` row with `display_name` literally `"********"`, which
  hits the `known_ids` branch and returns *before* reaching any of the new
  fill-in logic. Worse, once one redacted participant's DB name is
  `"********"`, every *other* redacted participant's GR name-key
  (`_name_key("********")`) collides with it in `our_batting_fingerprints` /
  `_nk_to_player`, silently swallowing them regardless of whether they're
  `known_ids` too. Fixed three ways: `_looks_redacted()` now excludes
  placeholder names from both fingerprint sets so they can't false-match;
  the `known_ids` branch now injects a **scored** row (not just a DNB one)
  when a known player has no `batting_innings` row for this game, sourced
  from GR's own stats (`our_missing_rows`, generalised from the old
  DNB-only `our_missing_dnb`); and a final pass over `batting_flat`/
  `bowling_flat` normalises ANY row whose name is unusable (blank or
  `"********"`, however it got there — a genuine fill-in or a stale DB row)
  to the same unlinked `player_id: null` + `is_fill_in: true` shape. Verified
  by replaying the real GR payload for this game through the exact loop
  logic under both possible `known_ids` states — both converge on the
  correct 192 bat runs + 5 extras = 197, 5 wickets.
- **v8.60.3 follow-up — redacted juniors were mislabelled "Fill-In"**: user
  feedback caught that a genuinely redacted junior (no name recoverable
  anywhere in the feed) was showing as "Fill-In #1"/"Fill-In (#N)" — the
  same treatment as a real borrowed player with a known name, which
  misrepresents an unknown identity as a known-but-unregistered one and
  breaks the `********` convention clubs already recognise. Split the old
  `_fill_in_display_name` into `_classify_unlinked_name`, returning
  `(display_name, is_fill_in, is_redacted)`: a redacted participant (blank
  or all-asterisks GR name) always renders literally as `"********"` with
  `is_redacted: true` and no badge; only a genuine fill-in with a real GR
  name gets `is_fill_in: true` + the FILL-IN badge. The final
  redacted-DB-row normalisation pass (see the v8.60.1 note above) was
  simplified to always set `is_redacted` (it only ever fires on a name that
  already failed `_looks_redacted`, so there's nothing to classify).
- **Not done this round**: `Partnership` has no free-text-name column (unlike
  `FallOfWicket.batter_name`), so a fill-in's side of a partnership still
  reads "Unknown" — would need a migration to fix properly. Fielding has no
  live-GR merge in this endpoint at all (DB-only), so a fill-in's catches
  aren't backfilled live. Sync (`sync_grassroots_game_level_data`) still
  gates `batting_innings`/`bowling_spells`/`fielding_stats`/`game_appearances`
  inserts on `our_team_pids`, so a fill-in still never lands in the stored
  per-game tables — this fix is live-view-only (the endpoint already
  re-fetches Grassroots on every request regardless of sync state, so no
  re-sync is needed for it to take effect). Also raised but not built: an
  admin flow to edit a fill-in's name, promote them to a real `players` row,
  and match them to a PlayHQ profile via a pasted profile URL — the fill-in
  row now carries a stable `participantId` internally, which is the piece
  that flow would need, but the UI/endpoint itself wasn't scoped in.

<!-- END original CLAUDE.md L14030-14128 -->
<!-- BEGIN original CLAUDE.md L14129-14217 -->
## Fill-in players: partnerships/fielding toggle + claim-a-fill-in (v8.61.0, Jul 2026)

Follow-up to the fill-in scorecard fix above (v8.60.x), extending it two ways.

- **Club-level toggle for partnerships/fielding** (migration 147): a fill-in's
  runs/wickets always show on the batting/bowling card, no toggle. Whether
  their name also shows in the lower-stakes partnerships and fielding cards
  on that same scorecard is a new org setting, `include_fill_ins_in_stats`
  (default **on**), edited via the existing `/club-admin/settings` GET/PATCH
  (`SettingsPatch`) and a new checkbox in `AdminSettings.jsx` ("Fill-in
  players" section). Schema mirrors `FallOfWicket.batter_name`:
  `partnerships.batter1_name`/`batter2_name` and `fielding_stats.player_name`
  (nullable, set only when the linked id is NULL), with matching always-NULL
  columns on `manual_partnerships`/`manual_fielding_stats` purely so the
  `v_effective_*` union views' column lists still line up.
  `fielding_stats.player_id`'s FK was also changed `ON DELETE CASCADE` →
  `SET NULL`, matching every other player-linked per-game table (it was never
  actually nullable in practice before this, just inconsistent).
- **Sync-side capture** (`sync.py`): a new `our_team_roster_guids` set (raw
  GR participantId strings, not just resolved player ids) lets the
  partnership/fielding insert loops tell "one of ours, just unregistered"
  apart from "genuinely the opposition's" — a plain `None` from `_team_pid`
  can't distinguish the two on its own. `_derive_partnerships_grassroots` now
  also returns `batter1_name`/`batter2_name` (sourced from the same raw
  batting-row `playerShortName` already in scope). A partnership is only
  dropped now when **neither** side resolves to an id **or** a name (was:
  dropped whenever either side had no id) — so two fill-ins batting together
  no longer vanish entirely. Fielding for a fill-in is captured the same way
  instead of being unconditionally skipped.
- **Read-side gating** (`games.py`/`aggregations.py`): `get_game_partnerships`
  extends its existing name COALESCE chain
  (`display_name_override → name → batterN_name`) one more step, matching
  `get_game_fall_of_wickets`'s pattern. `get_scorecard` loads the org once
  (`include_fillins_stats`) and applies it after the fact: fielding rows with
  no `player_id` are only emitted when the toggle is on (and their name run
  through the same `_classify_unlinked_name` used for batting/bowling, so a
  CA-redacted fielder still reads as `********`, never "Fill-In"); partnership
  rows have their fallback name stripped back to NULL when the toggle is off,
  or classified the same way when it's on. **Records are unaffected either
  way** — `records.py`'s partnership/fielding leaderboards already inner-join
  through `players` scoped to the org, so a NULL `player_id` row was always
  invisible there regardless of this feature; confirmed via the research
  pass, no extra guard needed.
- **Claim-a-fill-in** (`players.py`, `POST /players/claim-fill-in`, cap
  `MANAGE_PLAYERS`): promotes a fill-in scorecard row into a real `players`
  row, reusing sync's `_resolve_org_player` identity scheme standalone (id =
  the raw GR participant GUID, or `uuid5(org, guid)` only on a genuine
  cross-club collision; `grassroots_id` = the raw GUID) so a later sync
  recognises the row by `(org, grassroots_id)` and attaches to it instead of
  minting a duplicate. Re-claiming the same participant is idempotent (finds
  the existing row by `grassroots_id`, updates the name). An
  `existing_player_id` in the request means the fill-in turned out to already
  be a registered player under a mismatched GR uuid — delegates straight to
  the existing `admin.merge_players` (called as a plain function with
  explicit `db`/`current_user`, bypassing its `Depends()` — merge_players
  already handles the reassignment/de-dup across every per-game table,
  including the exact cross-club-shared-GUID case, no reason to reimplement
  it). `players.claim_note` (new nullable column, same migration) holds an
  optional free-text reference the admin leaves when claiming — e.g. a pasted
  PlayHQ profile link — **stored verbatim, not parsed or verified**.
  `games.py`'s three fill-in row-construction sites now also emit
  `grassroots_participant_id` (previously computed internally but never
  serialised) so the frontend has something to submit back.
- **Why no PlayHQ-URL auto-resolution**: investigated and shelved. PlayHQ's
  player-profile pages are a client-rendered SPA behind CloudFront bot
  protection — both plain curl and headless Chromium (proxied through this
  environment) got blocked, consistent with the existing "UK Expansion" note
  elsewhere in this file about Play-Cricket needing a real browser network
  capture to find API shapes. Worse, the example URL used to investigate this
  (`.../game-centre/c226ff54`) carries a short obfuscated code, not the real
  GUID — the same short-code-vs-real-GUID gap already known for game ids — so
  even a successful fetch likely wouldn't yield something resolvable to the
  actual Grassroots participant id without an authenticated API this project
  doesn't have. Building a parser that looks automatic but silently can't
  verify anything would be worse than not building it — hence `claim_note`
  being a plain stored string instead.
- **Frontend**: `MatchScorecard.jsx` gains a `CLAIM` button next to any
  `is_fill_in` row (never `is_redacted` — nothing to claim on an unknown
  identity), gated on `hasCapability(CAP.MANAGE_PLAYERS)` via the same
  inline-on-a-public-page pattern `PlayerProfile.jsx` already uses (the page
  has no other auth surface — `get_scorecard` itself stays fully
  unauthenticated). `ClaimFillInModal` — name field, an existing-player
  search (client-side filter over `adminListPlayers()`, fetched once only
  when `canManage`), and the reference-note field. Also fixed while touching
  this: `PartnershipsSection` used to assume "has a name ⇒ has an id" and
  linked to `/players/${batterN_id}` unconditionally whenever a name was
  present — broke (linked to `undefined`) the moment a fill-in could have a
  name with no id, which this feature introduces; now checks the id first.

<!-- END original CLAUDE.md L14129-14217 -->
<!-- BEGIN original CLAUDE.md L14218-14401 -->
## Scorecard endpoint rewritten to trust Grassroots, not our own DB, for both teams (v8.78.0, Jul 2026)

Reported: a scorecard's header total didn't match its own batting card (e.g.
"30/1" in the header while the card below it showed seven dismissals — the
real score was 135/7), and a bowler occasionally appeared twice with
identical figures, once linked correctly and once as a bogus "FILL-IN" row
with a CLAIM button.

**Root cause of the wrong total**: `get_scorecard`'s live GR-merge (see the
fill-in notes above) decided whether a participant was "ours" by checking
`pid in known_ids` — is this GUID a `players` row *anywhere* in our org —
before ever checking which team's roster they were actually listed under for
*this match*. A player registered with the club who guested for the
opposition that day (confirmed against the raw GR payload: he's listed only
on the opposing team's roster) got swept onto our own card by that check,
which made the innings-total logic think it already had complete data for
that innings and stopped it from ever falling back to GR's own authoritative
total, wickets included.

**Root cause of the duplicate bowler**: GR can report a different
`participantId` for the same real bowler than the one already stored (the
same MyCricket/PlayHQ dual-GUID class of issue documented elsewhere in this
file), and only the batting side of `get_scorecard`'s merge had a name-based
fallback for that case (`_unresolved_roster_pids` → `_nk_to_player`). The
bowling loop and the first-pass batting DNB-detection loop had no such
fallback, so an unrecognised GUID on our own team's roster fell straight
through to the "unregistered fill-in" branch and rendered as a second,
duplicate row instead of resolving to the existing player.

**Fix — inverted the whole function's precedence.** `get_scorecard` no
longer treats our stored `batting_innings`/`bowling_spells` rows as primary
and reaches for Grassroots only to patch gaps. When the live GR fetch
succeeds (true for essentially every non-manual game — the same `/scores/*`
endpoint reaches back to the 1970s), **both** teams' batting, bowling and
innings totals are built entirely from that response. Team membership is
decided purely by GR's own team roster listing for that match
(`our_team_roster_pids`/`opp_roster_pids`, matched on the org's name against
the GR team name — unchanged from before) — never by whether a GUID happens
to match a `players` row. Our own player table is now consulted for exactly
one purpose: `_resolve_linked_id(pid_str, name)` tries the literal id, then a
new `grassroots_id` lookup, then a name-key match, purely to attach a
`player_id` for a profile hyperlink on rows already classified as ours — it
can never move a row to the other side or change its numbers. Innings
totals now uniformly prefer GR's own `numberOfWicketsFallen`/`totalExtras`
for both sides (previously only the opposition innings got this treatment);
bat-only `runs` is still summed from individual rows, never substituted with
GR's full-team `runsScored`, which would double-count extras once the
frontend adds them.

The DB-sourced batting/bowling/totals built earlier in the function are only
swapped in after the entire GR-sourced rebuild completes without error — a
GR outage or any exception leaves the page showing the last-synced copy
instead of erroring, same resilience as before.

**Consequence for the fill-in feature above**: a DNB roster member who
resolves via the new name fallback (like the O'Kane/Singh case) now renders
as a normal linked row instead of a fill-in with a CLAIM button — CLAIM is
reserved for participants who genuinely have no `players` row.

**Verified against the reported game** by replaying the fix's exact logic
offline against the real Grassroots payload (`/scores/matches/{id}` fetched
directly, bypassing the app): the misattributed player's innings now lands
on the opposition card as intended, the header total reads 115+20 extras =
135 runs for 7 wickets (matching GR's own authoritative figures, and
consistent with the winning team's actual chase target), and the duplicated
bowler's figures appear exactly once, correctly linked. Not done this round:
`fielding_stats` stays DB-only in this endpoint (no live GR fielding merge)
— a known pre-existing gap, unrelated to this fix, flagged as a possible
follow-up.

**Follow-up (same day) — the scorecard cache had no expiry.** After the fix
above deployed, the reported game still showed a wrong, DIFFERENT wrong
total ("16/0" this time, with one side's whole batting card missing).
Re-fetching Grassroots directly (repeatedly, with the app's own request
shape) confirmed the live upstream data is correct and has been stable —
135/7, 20 extras, full batting rows both sides — so the corrupted output
wasn't coming from Grassroots or from the rewritten merge logic. It was
`grassroots_scores_client._scorecard_cache`: an in-process, no-TTL,
never-invalidated cache keyed by match id. Once a match's scorecard is
fetched, that exact response is served forever for the life of the backend
process. A club scorer correcting this match on Grassroots' side got caught
mid-save at some point (an innings with its totals present but its batting
rows momentarily empty is the signature — exactly what's visible in the
symptom), and that half-saved snapshot got pinned permanently the moment
anything first requested this match. `get_match_scorecard` now takes a
`_SCORECARD_TTL` of 15 minutes (`get_grade_ladder` already had this pattern
for the same reason — "ladders move ~weekly, an hour keeps the proxy happy"
— the scorecard cache just never got the equivalent treatment), plus a
`_scorecard_looks_incomplete` guard: a response with an innings that reports
real totals but zero batting rows is never cached at all, so a mid-edit
snapshot can't get pinned even briefly — the very next request retries
instead. `force=True` was also added, matching `get_grade_matches`'s
existing param, for any future caller that needs to explicitly bypass the
cache. This bug predates the rewrite above and would have been silently
capping the OLD merge logic's live-GR data too, on whichever match happened
to be fetched during an in-progress correction.

**Second follow-up (same day) — the cache fix above wasn't the actual cause
of the "16/0" symptom; the real bug was a crash.** After the cache fix
deployed, the page still showed the same wrong total. Repeated, interleaved
checks against Grassroots directly and against our own `/scorecard` and
`/scorecard/gr-debug` endpoints proved the upstream data was correct and
stable on every single check, while `/scorecard` was stable and WRONG on
every single check — impossible if the two endpoints (which share the exact
same `get_match_scorecard` call) were both reading live data normally. The
timing gave it away: `/scorecard` took a full ~1-1.5s per request (a genuine
live fetch, not a cache hit), yet still returned the pre-rewrite DB-only
shape (dismissal text truncated to the DB's own short form, the opposition
side entirely absent, extras undercounted at 16 — exactly the sum of our own
bowlers' wides+no-balls, with no byes/leg-byes, which is what the *old*
pre-rewrite code computed from stored rows alone).

Root cause: `org_word = (org.name or "").lower().split()[0] if org.name else
""` dereferenced `org.name` without checking `org` was truthy first. `org`
being `None` is an anticipated, already-handled state two lines above it
(`include_fillins_stats = ... if org else True`) — grade/season resolve
fine but the season's `organisation_id` doesn't always resolve to a live
`Organisation` row. The `AttributeError` this threw was inside the same
`try` the whole rebuild lives in, so it was swallowed by the generic
`except Exception` and silently fell back to the DB-only pre-rewrite
rendering — reproducing the *original* bug this whole fix was meant to
solve, indistinguishable from the outside from "the fix didn't deploy".

Fixed two ways, not just one: (1) the `if gr_data and org:` guard became
`if gr_data:` and the null-unsafe `org.name`/`org.id` reads are now properly
guarded, so the rebuild no longer requires `org` to resolve at all — losing
the org lookup should only mean losing the ability to hyperlink a name to a
profile, never losing the rebuild itself. (2) Team classification (which GR
team is "ours") no longer leans on `org.name` substring-matching as the
*primary* signal at all: it now checks first whether either team's roster
overlaps with names we already have a stored batting/bowling row for on this
exact game (`batting_rows`/`bowling_rows`, queried earlier in the function
regardless of org resolution) — a signal that's true by construction (sync
only ever writes rows for our own team) and doesn't depend on the
grade→season→org chain resolving at all. `org_word` matching is now only the
fallback for a game with zero prior synced rows to compare against (i.e. the
very first time it's ever viewed). Verified offline against the real
payload with `org_word` forced empty (simulating the exact failure): the
DB-overlap signal alone correctly picks Mulgrave as "ours" (11/12 roster
names match) with no org lookup involved at all.

**The pattern worth remembering**: a broad `except Exception` around a large
rebuild is good for resilience against a flaky upstream, but it also hides a
genuine bug in the rebuild itself behind the SAME "fall back to the old
data" behavior — from the outside, "GR is down" and "our own code just
crashed" look identical. Anything added inside a block like this needs the
same null-safety discipline as the rest of the function, since a silent
`except` won't surface a shortcut taken in a hurry.

**Third follow-up (same day) — the org fix above deployed clean but the bug
was STILL live; this was the real remaining cause.** After confirming (via
`docker exec ... grep`) that the org-safety fix was genuinely running in the
container, the page still showed the exact same wrong numbers. The container
logs (`docker compose logs betterstats-backend`) had the answer directly:
`sqlalchemy.exc.ArgumentError: Column expression, FROM clause, or other
columns clause element expected, got <property object at ...>` on
`select(Player.id, Player.grassroots_id, Player.display_name)`.
`Player.display_name` is a Python `@property` (`display_name_override or
name`, see the `Player` model in `models/db.py`), not a mapped column —
accessing it at the class level (as `select()` does) returns the property
descriptor object itself, not something SQLAlchemy can query. This has
nothing to do with `org` or team classification; it's a straight query bug
in the player-linking lookup added by the original rewrite, and it fired on
every single request, every time, regardless of which of the two prior
fixes was live — which is exactly why "no change whatsoever" kept being the
honest, correct observation from outside. Fixed by selecting the two real
columns behind it (`display_name_override`, `name`) and computing the same
`or` fallback in Python. No offline test caught this because the earlier
verification replayed the row-construction logic in plain Python against a
hand-fetched JSON payload — it never touched a real SQLAlchemy `select()`,
so a query-construction bug like this one was invisible to it. `py_compile`
doesn't catch it either, since `Player.display_name` is syntactically valid
Python; the error only exists at the SQLAlchemy-semantics level and only
throws when the code path actually executes.

**Diagnostic order that actually worked, for next time**: (1) confirm the
deployed code is genuinely the code you think it is (`docker exec ... grep`
for a distinctive string — cheap, and rules out an entire class of "is my
fix even running" confusion in one command); (2) if the code IS current and
the bug persists, go straight to `docker compose logs <service> --since Nm |
grep -A 30 "<your own log line>"` rather than re-reading the source again —
a real traceback finds a bug in seconds that a fourth static read of the
same function won't.

<!-- END original CLAUDE.md L14218-14401 -->
<!-- BEGIN original CLAUDE.md L14402-14593 -->
## Match scorecard page redesigned around the SC3 Dashboard layout (v8.79.0, Jul 2026)

Once the data fixes above were confirmed correct against the live site,
`MatchScorecard.jsx` was restructured to follow the layout of BetterSocials'
`SC3_Dashboard` share-card template (`frontend/src/social/cricket-templates.jsx`),
per direct request — toss and Player of the Match were dropped from the
adaptation since neither is data we hold (no toss column, see the "UK
Expansion" note elsewhere in this file on why toss isn't captured from the AU
`/scores/*` feed either; no MOTM field anywhere in the schema).

- **`MatchHeader`** shrank from a 3-column hero strip with giant score
  numbers to a single lean meta card: grade/season on one line, the result
  pill + `{winning_team} won by N wickets/runs` on the next (margin computed
  client-side by `marginText()` from the two innings' own totals — chasing
  side won ⇒ `10 - their_wickets` wickets in hand; defending side won ⇒ the
  runs difference — since the backend has no pre-written margin string), date
  + venue off to the side. The old toss/umpires strip is gone (those fields
  are never populated).
- **`BattingCard` + `BowlingCard` merged into one `TeamCard`** — matching
  SC3's actual per-team layout: a badge (initials, since we hold no team
  logos) + innings label + team name + big score in the card header, the
  batting table with extras inline underneath, then — nested in the SAME
  card, not a separate row further down the page — the opponent's bowling
  figures, labelled `"{OPPONENT} BOWLING"`. This maps directly onto the
  existing data shape: `innN.bowling` was already "whoever bowled during this
  innings" (i.e. the opponent's figures), so nesting it under `innN`'s own
  `TeamCard` needed no new field, just moving where it renders. Each card
  also now shows overs faced next to the innings label (`sumOversBalls` +
  `ballsToOversStr`, previously computed only for the old header's now-removed
  RR line — reused rather than left dead).
- The main render dropped its "batting row, then a separate bowling row"
  two-`<div>` structure for a single side-by-side grid of two `TeamCard`s.
  Fall of wickets and partnerships stay as their own full-width sections
  below, unchanged — SC3 doesn't have either, but nothing here asked for
  their removal, and dropping working features wasn't part of the brief.
- **Verified visually, not just by build.** `npx vite build` alone would only
  catch syntax errors, not a wrong layout — so the local dev server's `/api`
  proxy was pointed at the live production API for one throwaway session
  (`vite.config.js` target flipped to `https://betterat.cricket`, restored
  after), and the actual rendered page for the reported game was screenshotted
  via the `playwright` CLI. Confirmed against play.cricket.com.au's own page
  for the same match: 135/7 and 136/4 in the right cards, "Mulgrave Brian
  Bolton Realty won by 6 wickets" computed correctly, 35.0 / 31.3 overs
  matching CA's own display, opponent bowling nested correctly under each
  team with no duplicate rows.

### Club crests + match-summary header restored (v8.79.1, Jul 2026)

Two follow-ups on the SC3 redesign above, per direct request.

- **Team logos, live from Grassroots.** `get_scorecard`'s existing GR-merge
  already fetches `teams[]` for roster/name matching — it now also pulls a
  logo per team into `gr_team_logo_by_id`. The team object itself carries no
  logo field; a live payload check found it nested under
  `owningOrganisation.logoUrl` (the grade-level "team" — often a sponsor name
  — is owned by the actual club, which holds the crest). A bare
  `logoUrl`/`logo`/`imageUrl`/`image` fallback chain is kept on the team
  object itself too, matching the existing precedent in
  `admin.py::build_team` (the BetterSocials match-import) for a
  differently-shaped response. For whichever side is ours, our own uploaded
  org logo (`org.logo_url`, else `/images/organisations/{id}/logo` if we
  hold the raw bytes — same precedence `social_rounds.py::_club_dict` uses)
  takes priority over GR's, since it's controlled and always-available when
  set. Threaded onto `innings_totals[n].logo_url` alongside the existing
  `batting_team` name, so the frontend reads it the same way. Neither source
  is guaranteed present — a hotlinked hit can 404 — so `TeamBadge.jsx`'s
  `<img>` falls back to an initials badge on `onError`, the same graceful
  degradation BetterSocials' own share-card templates already rely on.
- **`MatchHeader` restored to a full match-summary strip** — the 3-column
  HOME/RESULT/AWAY hero from before the SC3 rewrite, kept alongside the
  competition line and computed winning margin the rewrite added. Each side
  now also carries its crest (`TeamBadge`, shared with the per-team cards
  below) next to the team name. The per-team `TeamCard`s are unchanged; the
  header duplicating their score is intentional, not a regression — the
  reference site itself (play.cricket.com.au) shows the same score both in
  its top summary and again in the innings detail below.

### Winner clarity + explicit home/away-vs-batting-order split (v8.79.2, Jul 2026)

Feedback on v8.79.1: the winner wasn't obvious at a glance, and the two
sections' ordering rules needed to be pinned down explicitly rather than
left implicit. Per direct instruction: `MatchHeader` stays home-left/
away-right always (unrelated to who batted first or who won); the `TeamCard`
row below it stays ordered by batting sequence (1st innings left, 2nd
right) — this was already how it worked, since `inn1`/`inn2` in the main
component come from sorted `inningsNums`, but nothing said so explicitly
before, which is how the header nearly ended up matching it instead
(reverted mid-build after being pointed out).

- **`WinnerTag`** — a small green "✓ WON" pill (reusing `--pb-positive`,
  the same win-green `ResultPill` already uses for `WIN`), rendered next to
  the winning team's name in both `MatchHeader`'s `Side` and `TeamCard`,
  plus a light green tint on that side's background in both places. Winner
  match is `teamsMatch(game.winning_team, teamName)`, computed independently
  in each component off the same `winning_team` string — no shared state
  needed since both already receive it (`MatchHeader` via `game`, `TeamCard`
  via a new `winner` prop threaded from the main component).

### Cross-club player leak in scorecard team classification (v8.79.3, Jul 2026)

Reported on a DIFFERENT match (Applecross 1st XI vs Pentagon-NBCCC 1st XI):
both teams' crests showed as the same club's logo, and most of Pentagon's
batters rendered as "FILL-IN" with a CLAIM button — except two of them, who
showed as fully linked Applecross players.

**Root cause**: `_our_tid` (get_scorecard's "which GR team is ours" decision,
see the rewrite above) tries the DB-overlap signal (does either team's roster
overlap names we already have a stored row for on this exact game) before
org-name matching. Two of Pentagon-NBCCC's players — real people who had at
some point also played for Applecross — had old `batting_innings` rows
already stored under Applecross for this exact game (their own separate
data-integrity issue, not fixed here — see below), so DB-overlap scored
Pentagon-NBCCC 2 and Applecross 0, and `max()` picked Pentagon-NBCCC as
"ours". Every one of their actual teammates then correctly failed to
resolve against Applecross's roster and rendered as a fill-in, while the two
contaminated names resolved to their (real, but wrong-context) Applecross
`players` rows — and the crest swap followed directly from the same
misclassification.

**Fix**: swapped the precedence — org-name matching is now the PRIMARY
signal (it can't be fooled by a few contaminated rows the way a raw overlap
count can), with DB-overlap only as the fallback for when org itself can't
be resolved at all (the original `org.name`-crash scenario two sections up).
Verified offline against the real payload for this match: org_word alone
correctly picks Applecross even with the 2-vs-0 contaminated overlap still
in play.

**A deeper, separate bug found while investigating**: `get_game_fall_of_wickets`
and `get_game_partnerships` (`services/aggregations.py`) joined `players` on
`player_id` with **no organisation scoping at all** — a fall-of-wicket or
partnership row whose stored `player_id` happens to belong to another club's
roster (the same "shared GUID"/prior-registration class of issue as above)
rendered as if it were one of ours. For fall of wickets specifically this
also produced literal duplicate rows per wicket — one correct unlinked row
(GR short name, no `player_id`) and one wrongly cross-club-linked row for
the same wicket, both stored, both returned. Fixed both functions to accept
an `org_id` and scope the `players` join to it (`AND (:org_id IS NULL OR
p.organisation_id = :org_id)`, so a caller with no org context is
unaffected); `get_game_fall_of_wickets` also now deduplicates by
`(innings_number, wicket_number)` after the org-scoped query, keeping
whichever of the two stored rows has a usable name. A row that loses its
link this way and has no stored free-text fallback name renders as
"Unknown" on the frontend (already-existing behaviour) — a real gap, but
never the wrong person's name.

**Not fixed, flagged for follow-up**: `records.py`'s partnership leaderboard
query (`top_partnerships`) requires BOTH batters' `organisation_id` to match
the viewing club — which sounds safe, but isn't, for exactly this case: the
two contaminated players' `players` rows ARE genuinely org-scoped to
Applecross, so a stand like theirs from a match they didn't actually play
for Applecross in can still surface on Applecross's own records page as a
phantom top partnership. This wasn't chased further today — scope is
"how many historical games/players are affected platform-wide", which needs
a proper audit (and likely a sync-side fix, not just a read-side one) beyond
what one reported match justifies investigating alone.

Yearbook generation was previously **100% manual** — two separate admin
buttons (Generate stubs, Generate narrative) plus a Publish button, with the
only automatic step being an at-startup stub-only sweep (`generate_all_stubs`,
called once from `main.py`'s lifespan). A user expected a Full Rebuild to
auto-generate yearbooks for the last 3 seasons; it never had, since nothing in
`sync_organisation`/`hard_refresh_org` ever called into `routers/yearbooks.py`.
This was a documented-but-unbuilt idea (`docs/self-serve-trial-onboarding-plan.md`
Decisions 12/13, Phase 22 — scoped there to the not-yet-built self-serve
onboarding wizard, not the existing per-club rebuild button), not a regression.

- **`routers/yearbooks.py`**: `generate_narrative` was split into a thin route
  plus a reusable `_generate_narrative_core(db, org_id, season_id)` (same
  rate-limit/API-key/import checks, same body) so it can be called directly
  from a background task, not just over HTTP. New
  `auto_generate_and_publish_recent_yearbooks(db, org_id, count=3)`: ensures
  stubs exist, finds the org's last `count` seasons that actually have
  `player_season_stats` rows (`_last_n_seasons_with_stats`, same recency
  ordering as `_season_sort_key`), and per season generates the narrative
  (promoting `ai_draft` → `content_markdown`, since only `content_markdown` is
  what actually renders) and publishes — **unless that season already has
  narrative content**, so a later rebuild never clobbers an admin's hand
  edits. A season is still published even if narrative generation fails (no
  `anthropic_api_key` configured, rate-limited, transient error) — errors are
  caught per-season and logged, never raised, matching the onboarding-plan's
  accepted "auto-publish, no draft gate" call.
- **`routers/club_admin.py::hard_refresh_org`**: the new call sits inside the
  `_run()` background task's **true-success branch only** (right after
  `await finish_sync_run(run_id, stats)`, not the "wiped but 0 matches came
  back" error branch), in its own `try/except` with a fresh
  `async_session_maker()` session — mirrors the existing post-sync `ANALYZE`
  block's isolation pattern, since a yearbook failure must never look like a
  sync failure (the sync's success has already been recorded).
- **Scope, per direct instruction**: Full Rebuild only — plain "Sync Now" does
  not trigger this (rebuild is the "real completion signal" the shelved plan
  called for; a routine weekly sync isn't).

<!-- END original CLAUDE.md L14402-14593 -->

## The scorecard never drew its fielding (v9.100.3, Sep 2026)

Reported by Shoalwater Bay: no catches on a 1992-93 B Grade scorecard. Their file (`manual_games_scorecards.csv`) has that season's 17 B grade matches, 16 with catch or stumping rows and 54 catches in total, credited to individual players.

- **The data was imported and the API returned it.** `get_scorecard` has always sent `fielding`; `MatchScorecard.jsx` never read it. Synced games look fine only because Cricket Australia writes the catcher into the dismissal text (`c Smith b Jones`).
- **A scorebook records a tally, not a per-wicket catch.** The archive says how many catches each player took in the match and never which batter each one dismissed, so `dismissal_type` is a bare `c`. `FieldingSection` draws the tally. Only columns somebody has a figure in are drawn, most dismissals first, a fill-in is listed unlinked, and nothing is drawn where nothing is recorded.
- **`catches_wk` is on the payload now**, alongside `catches`. The CSFW converter puts a keeper's catches in `catches_wk` with `catches` blank, so the section shows `max(catches, catches_wk)`.
- **Driven in Chromium** (`frontend/verification/verify_scorecard_fielding_browser.mjs`, 23: the columns, the keeper, the ordering, links, dashes, nothing drawn for an empty or older payload, a fill-in, no sideways scroll at 390px) **with a control run**: 4 fail, reporting rather than crashing.
- **A screenshot caught what the checks did not:** the first cut used `border-t pb-hairline`, which is not a class, so the row dividers rendered white. `pb-hairline-t` is the real one.
