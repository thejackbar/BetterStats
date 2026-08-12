# BetterScout Redesign — Build Plan

Companion to `README.md` (which is the visual spec). This file is the engineering brief: what already exists on `main`, what each redesigned screen needs behind it, and what is deliberately left unbuilt.

**Guiding rule: keep the design, build the functionality to match it.** Where the design shows something the data cannot support, the design already says so on screen (dashed "not built yet" cards, `SEASON ONLY` badges, "no photo in CA data" slots). Preserve those honesty affordances — do not quietly fake them, and do not delete them.

---

## 1. What exists today

### Backend

| File | What it gives you |
| --- | --- |
| `backend/app/models/scout.py` | `ScoutOrg` (name, slug, is_active, **tier**, theme colours, logo_url), `ScoutUser` (username, password_hash, display_name, advisory `role`, lockout fields), `ScoutClubCache` (one shared build per club GUID: status `building`/`ready`/`error`, `payload`, `built_at`), `ScoutedPlayer` (platform-wide person: `source` = `au_grassroots`\|`manual`, `grassroots_participant_id`, `club_org_guid`, `club_name`, `grade_name`, `notes`, `stats_payload`, `stats_built_at`), `ScoutWatchlist`, `ScoutWatchlistColumn` (name + position), `ScoutWatchlistCard` (position, `tags` JSONB, role/batting_hand/bowling_action/bowling_type, region, level, the five recruiting fields, `notes`, `share_token`). **Zero foreign keys in or out of club tables** — isolation is structural; keep it that way. |
| `backend/app/routers/scout/auth.py` | Separate session/login (`get_current_scout_user` → `(ScoutUser, ScoutOrg)`), backed by `services/scout_auth.py`. Not the club `bs_session` cookie. |
| `backend/app/routers/scout/discovery.py` | `GET /scout/clubs/search`, `GET /scout/clubs/{org_guid}/roster`, `POST .../roster/refresh`, `POST /scout/players/add`, `POST /scout/players/manual`, `GET /scout/players`, `GET /scout/players/{id}`, `POST /scout/players/{id}/refresh`. |
| `backend/app/routers/scout/watchlist.py` | Full board CRUD: watchlists, columns (create/rename/delete/reorder), cards (move/update/remove), share link create/revoke. Ownership re-checked per call in the service, never trusted from the URL. |
| `backend/app/routers/scout/public_share.py` | `GET /public/scout/share/{token}` — no session. |
| `backend/app/services/scout_discovery.py` | `get_or_start_club_roster` (build/poll contract, mirrors BetterIQ's opposition dossiers), `add_player`, `add_manual_player`, `list_tracked_players`, `refresh_player`, `player_out`. |
| `backend/app/services/iq_scout.py` | The hard part, already solved: club → roster → per-player per-season career build, including the raw counts (`balls_faced`, `bowling_balls`, `runs_conceded`, innings, not_outs, fifties, hundreds, ducks, maidens, five_fors, catches, catches_wk, stumpings, run_outs, best figures, high score). |
| `backend/app/services/scout_billing.py` | `TIER_LIMITS` = `starter: 25`, `growth: 100`, `unlimited: None`; `usage_for(org)` → `{tier, tier_label, player_count, player_cap, at_cap}`. Tracked count = distinct players carrying a card on any of the org's watchlists. Tier set by staff via `scripts/scout_set_tier.py`; **no Stripe wiring**. |
| `backend/app/services/milestone_rules.py` | The house milestone scheme, reusable as-is: thresholds (runs 500 then every 1,000; wickets 50 then every 100; matches and catches every 50), `next_threshold`, `crossed_thresholds`, `reach_window` (runs 50/100, wickets 5/10, matches 2/5, catches 5), `is_displayable`. |
| `backend/app/services/aggregations.py` | `get_upcoming_milestones_for_org`, `get_recently_achieved_milestones_for_org` — including the season-by-season cumulative simulation used to work out *which season* a milestone was crossed in. The scout version is this logic pointed at `ScoutedPlayer.stats_payload` instead of club tables. |

Migrations already in place: `236_scout_org_tenant`, `237_scout_discovery`, `238_scout_watchlists`, `239_scout_share_link`, `240_scout_pricing_tiers`.

### Frontend

`frontend/src/scout/` — `ScoutApp.jsx` (pathless route group + `ScoutAuthProvider`), `ScoutLayout.jsx` (**the top-tab shell being replaced**), `pages/` (Login, Dashboard, Discover, Watchlists, WatchlistBoard, Players, PlayerProfile, Compare, PublicShare), `components/ScoutCardEditor.jsx`, `components/ScoutProtectedRoute.jsx`, `contexts/ScoutAuthContext.jsx`, `lib/scoutApi.js`, `lib/seasonRollup.js` (client-side window rollups + `WINDOW_OPTIONS`), `lib/watchlistOptions.js`, `kanbanDnd.jsx`.

Reusable from the wider app: `components/admin/ModuleLayout.jsx`, `components/ModuleLockup.jsx`, `components/admin/ModuleSwitcher.jsx`, `pages/admin/betterselect/ui.jsx` (`Icon`, `Avatar`, `Btn`, `Segmented`, `Chip`, `Search`, `Tag`), `pages/PlayerComparison.jsx` (the comparison pattern + `PLAYER_COLORS` + `getRowHighlights`), `pages/admin/AdminMilestones.jsx` (milestone UI vocabulary), `lib/moduleBrand.js`, `styles/theme.css`.

---

## 2. Work item by work item

### 2.1 Module shell — mostly a port

**Status: chrome exists, but not reusable as-is.**

`ModuleLayout.jsx` is club-coupled: it calls `useAuth()`, `api.adminGetSettings()`, `useClubTheme()`, `hasCapability()`, `BookmarkButton`, and `ModuleSwitcher` (which itself reads club module entitlements). A Scout Org has none of those.

Recommended: add `frontend/src/scout/ScoutModuleLayout.jsx` — the same visual shell, fed by `useScoutAuth()` instead. Keep `ModuleLayout`'s structure verbatim (232px sticky sidebar, brand block, `Icon`+label nav rows with the 2px active right border and accent tint, footer chrome, sticky header with title/caption/stats/actions slots, `bare`/`hideHeader` escape hatches, off-canvas drawer below `lg`) and re-point `--pb-accent` to the scout brand at the wrapper with `pb-ink` alongside it, exactly as `ModuleLayout` does per module.

Also needed:

1. `MODULE_BRAND.scout = { name: 'BetterScout', accent: '#C026D3', accentRgb: '192 38 211', logo: scoutLogo }` in `lib/moduleBrand.js`, with aliases `betterscout`/`scout`.
2. `frontend/src/assets/modules/betterscout.svg` — **new asset, needs designing** in the style of the existing four.
3. A scout-flavoured switcher. The real `ModuleSwitcher` is entitlement-driven for clubs; for a Scout Org the pills should either be omitted or reduced to a static, non-navigating "part of BetterCricket" row. Decide this before building — the design shows pills, but a scout org genuinely cannot reach the other modules. If they can't, drop the switcher and keep the footer to user + log out.

Do **not** touch `ScoutLayout.jsx` until the new layout is behind the same routes; the redesign changes chrome only, so every existing page component should mount inside it unchanged.

### 2.2 Overview (`1a`) — new endpoint, existing data

**Status: screen is new; two of three panels compute from data already stored; one needs a new table.**

New: `GET /scout/overview` → `{ usage, form_movers[], stale[], recent_clubs[], pipeline_counts }`.

- **`usage`** — already available: `scout_billing.usage_for(org)`.
- **`pipeline_counts`** (header readouts `IN PIPELINE` / `OFFER OUT`) — count cards per column across the org's watchlists. Note columns are free-text labels the backend has no opinion about (`ScoutWatchlistColumn` docstring is explicit), so "offer out" cannot be inferred. Either (a) count all cards not in the last column, or (b) introduce an optional `stage_kind` on columns that an org can set once. Prefer (b) only if the org actually wants it; otherwise show total tracked + cards in the final column and label it with the column's own name.
- **`form_movers`** — computable now from `ScoutedPlayer.stats_payload.seasons`: for each tracked player, roll up the latest active season and the two before it with the same rules as `seasonRollup.js`, then diff the player's primary metric (batting average for batters, bowling average for bowlers, strike rate where it moved most). Sparkline data is the last five seasons of that metric. Do this in a new `services/scout_overview.py` so the "which metric matters for this player" rule lives in one place. Reuse the season rollup rules from `seasonRollup.js`/`iq_scout._rollup` — never average per-season rates.
- **`stale`** — `stats_built_at` older than the org's stale threshold (new setting, see 2.6), or no note activity in that window. "No note activity" needs the notes table from 2.4; until then, fall back to `ScoutWatchlistCard.updated_at`. Manual players are surfaced but marked `manual entry` (nothing to refresh automatically).
- **`recent_clubs`** — **needs a new table.** `ScoutClubCache` is platform-wide, so it cannot tell you which clubs *this org* looked at. Add `scout_club_views (id, scout_org_id, club_org_guid, club_name, last_viewed_at)`, unique on `(scout_org_id, club_org_guid)`, upserted by `GET /scout/clubs/{org_guid}/roster`. Join to `ScoutClubCache` for the player count and `built_at`; flag "rebuild needed" when `built_at` is older than the org's refresh cadence.

### 2.3 Discover (`1b`) — restyle plus three additions

**Status: mostly exists. Window, filtering, sorting, expand and add are all built and stay client-side.**

Keep: `WINDOW_OPTIONS`, `rollupSeasons`, the client-side filter/sort, the build/poll contract, the "stay put after Add" behaviour, the at-cap block.

New:

1. **Filter presets** (`Bat avg 35+`, `Bowl avg <25`, `SR 85+`, `All-rounders`, `10+ matches`) — pure front-end sugar that sets the existing min/max filter state. No backend.
2. **Form sparkline column** — last five seasons of the currently sorted metric, from the seasons already in the payload. No backend.
3. **Grade column in the expanded season table, and the `Grades played` summary** — **verify first.** `iq_scout`'s per-season rollup must carry the grade for each season. The roster payload already returns a club-level `grades[]` list (today's UI shows it as chips), but per-season grade attribution needs confirming; if it isn't there, extend the build to record it. This is the one Discover addition that may touch `iq_scout.py`.
4. **Player identity line** (`1ST GRADE · RHB TOP ORDER · 24y`) — grade comes from the payload; **role and batting hand only exist once a scout has filled them in on a watchlist card**, and **age is not in the public data**. For an untracked player, show grade only. Drop the age chip unless a DOB genuinely appears in the payload — do not invent it.
5. **`Add to watchlist ▾`** — today's `POST /scout/players/add` creates the tracked player; the design lets the scout pick which watchlist (and therefore which column) the card lands on. Extend the request with an optional `watchlist_id`; default to the org's most recently used board.
6. **`On N watchlists`** — count of cards for that `scouted_player_id` across the org's boards; add it to the roster response for players the org already tracks (or to `GET /scout/players`).

### 2.4 Player profile (`1c`) — the biggest build

**Status: stat tiles and the season table exist. Everything else on this screen is new.**

Existing: `GET /scout/players/{id}` (totals + seasons snapshot), `POST /scout/players/{id}/refresh` (background rebuild, "check back shortly" posture — keep the 4s re-fetch or replace it with a proper poll on `stats_built_at`).

New:

1. **Discipline tabs** (batting / bowling / fielding / career) — pure presentation over the existing totals; every field needed (innings, runs, average, strike_rate, high_score, fifties, hundreds, ducks, wickets, bowling_average, economy, best, five_fors, maidens, catches, catches_wk, stumpings, run_outs) is already in the rollup.
2. **Window pills on the profile** — reuse `rollupSeasons()` client-side, same as Discover.
3. **Season chart** — runs + wickets bars from the seasons array. Use the same chart primitives the app already uses elsewhere rather than a new charting dependency.
4. **Grade per season** — same dependency as 2.3.3.
5. **Recruiting panel inline** — the five fields already live on `ScoutWatchlistCard` and are already writable via `PATCH /scout/watchlists/cards/{card_id}`. Decision needed: these are **per-card**, but the profile is **per-player**. If a player sits on two boards, which card does the profile edit? Recommended: keep the fields per-card and have the profile edit the card for the currently-selected watchlist (shown in the stage control), with the other boards' values visible in the "On watchlists" panel. Alternative — promote the five fields to a per-org-per-player record — is a migration and a data merge; only take it if scouts complain.
6. **Notes timeline** — **new table.** `ScoutedPlayer.notes` and `ScoutWatchlistCard.notes` are single free-text fields, not a history. Add `scout_player_notes (id, scout_org_id, scouted_player_id, author_scout_user_id, body, kind, occurred_at, created_at)` where `kind` is a small picklist matching the design's mono labels (`WATCHED LIVE`, `PHONE`, `SCORECARD REVIEW`, `OTHER`). Scope every read/write to `scout_org_id` — notes are the org's private intel and must never appear on a public share. Endpoints: `GET/POST /scout/players/{id}/notes`, `PATCH/DELETE /scout/players/notes/{note_id}`.
7. **Watchlist membership + stage move** — read from the cards; move via the existing `POST /scout/watchlists/cards/{card_id}/move`. The stage control is that endpoint with the column ids of the current board.
8. **Photo slot** — **new.** No photos exist in the public data. Add `photo_url` to `scouted_players` (platform-wide, like the rest of that row) or, if a photo should be org-private, to the card. Reuse the app's existing upload/storage path rather than inventing one; accept a pasted URL as the cheap first version. Until a photo exists, render the initials avatar — the frame is always reserved so the layout never shifts.

### 2.5 Compare (`1d`) — rebuild on the club pattern

**Status: a basic compare exists (`ScoutCompare.jsx`, two static tables). The redesign replaces it with the club-side head-to-head layout.**

Port from `frontend/src/pages/PlayerComparison.jsx`: `PLAYER_COLORS`, `PlayerAvatar` (photo → initials fallback), the avatar-headed fixed-layout table, `getRowHighlights` (unique best/worst only, ties unmarked), the tinted cells, the tab bar, and the footer caption. `ScoutCompare.jsx` already has a local copy of `rowHighlights` — replace it with the ported version rather than keeping two.

Differences to hold onto:

- **Window presets are season-based only** (`ALL TIME` / `THIS SEASON` / `LAST SEASON` / `LAST 2` / `LAST 5`), computed client-side by `rollupSeasons()`. The club page's "last 3 games" presets are impossible here — BetterScout has season rollups, not ball-by-ball. The design states this on screen; keep the sentence.
- **Up to 5 players**, selection held in the query string so a comparison is linkable.
- **`RECRUITING` tab** — new, reads the card fields (visa, availability, fee, stage) side by side. Internal only.
- **`Export as one-page PDF`** — new; the print path already exists in spirit on `ScoutPublicShare.jsx` (`window.print()` + a print stylesheet). Follow that.
- **`Share read-only link`** for a comparison — new. `share_token` today is per-card. A comparison share needs either a new `scout_shared_comparisons (id, scout_org_id, player_ids JSONB, token, created_at, expires_at)` table plus a public route, or an explicit decision not to ship it. Same rule as the card share: stats, tags and notes may travel; the five recruiting fields never do.

### 2.6 Milestones (`1e`) — new screen, existing scheme

**Status: entirely new for BetterScout. The thresholds, the reach windows and the UI vocabulary all already exist and must be reused, not re-derived.**

**Concept.** A scout's job is knowing when to make contact. A player three wickets from 150, or two games from their 100th, is both a reason to call and a reason the player will remember the call. BetterStats already computes exactly this for a club's own members; BetterScout points the same scheme at the players an org tracks, and is honest that its dating is coarser.

Build `backend/app/services/scout_milestones.py`:

- Import `next_threshold`, `reach_window`, `crossed_thresholds`, `is_displayable` from `services/milestone_rules.py`. **Do not restate the thresholds** — the design's copy quotes them from that file, and the two must not drift.
- For each tracked player, take `stats_payload`. **In reach**: career totals for runs / wickets / matches / catches versus `next_threshold`, kept when `needed <= reach_window`. **Reached**: replay seasons oldest → newest accumulating totals to find which season each threshold was crossed in — the same simulation as `aggregations.get_recently_achieved_milestones_for_org`.
- **Dating.** Public CA data is season-granular, so a crossing gets a season, not a date, and the row is badged `SEASON ONLY`. Where the player's `club_org_guid` matches a club already on BetterCricket, the match-level data exists and the crossing can be dated exactly (`MATCH DATED`, green). This two-tier honesty is a load-bearing part of the design — build both paths or ship only `SEASON ONLY` and leave the badge in place.
- **Season counters** (fifties, hundreds, five-fors, milestone games ahead) come straight from the current-season rollups; they're sums, not new computation.
- **`Mark as seen`** needs persistence: `scout_milestone_seen (id, scout_org_id, scouted_player_id, milestone_type, milestone_value, seen_at)`, unique on the middle four. This also drives the sidebar badge and the "since your last visit" count.

Endpoint: `GET /scout/milestones` → `{ season_counters, in_reach[], reached[] }` with `category` on every row (`batting`/`bowling`/`fielding`/`matches`) so the front end can filter without knowing the mapping. Filtering, search and category tabs are client-side, matching `AdminMilestones.jsx`.

Freshness caveat: this page is only as current as each player's last refresh. Say so — the design does.

### 2.7 Settings (`1f`) — new screen, mostly new columns

**Status: new. `ScoutOrg` has name, logo_url and theme colours; everything else on this screen is new.**

New columns on `scout_orgs` (one migration): `org_type` (`agency` \| `club` \| `selector`), `home_region`, `refresh_cadence` (`daily`\|`weekly`\|`manual`), `stale_after_weeks` (default 6), `default_window` (`1`\|`2`\|`5`\|`full`), `share_include_notes` (default true), `share_include_tags` (default true), `share_expiry_days` (nullable), `digest_enabled`, `alert_scope` (`all_tracked`\|`watchlisted_only`).

Endpoints: `GET /scout/settings`, `PATCH /scout/settings`. Wire the settings that other screens read: `stale_after_weeks` → Overview's stale panel, `default_window` → Discover and the profile, `refresh_cadence` → the refresh job (see 2.8), `share_*` → share payloads, `digest_enabled`/`alert_scope` → the digest.

Other pieces:

- **People.** `ScoutUser` exists with an advisory `role` and no enforcement. The design shows an owner, a scout and a pending read-only invite. That means (a) a real role check on write endpoints and (b) `scout_invites (id, scout_org_id, email, role, token, invited_by, created_at, accepted_at, expires_at)` plus an accept flow. Both are new. Ship the invite table and enforce two roles (`owner` writes, `viewer` reads) before showing a read-only invite in the UI.
- **Share-link management.** "4 links live now / Manage links / Revoke all" — list cards with a non-null `share_token`; bulk revoke sets them to null. `share_expiry_days` needs actual enforcement in `get_shared_card` (today a token lives until revoked).
- **Recruiting fields never shared** — already true in `scout_watchlist.get_shared_card`; the toggle is shown deliberately disabled to state the guarantee. Keep it non-editable.
- **Close org** — cascade already exists via `ondelete="CASCADE"` on org-scoped tables. Cached club rosters are platform-wide and must survive; say so in the confirm.
- **Billing.** Caps are enforced today; collection is not wired. Keep the amber `BILLING NOT COLLECTING YET` badge and the "Request an upgrade" path until Stripe lands. Tier labels in the UI must come from `scout_billing.TIER_LABELS` (`Starter` 25 / `Growth` 100 / `Unlimited`), not hardcoded copy.

### 2.8 Scheduled refresh — new infrastructure

`refresh_cadence` implies a job that rebuilds tracked players' snapshots on a schedule. Today every refresh is a user-initiated `POST /scout/players/{id}/refresh`. This is the smallest piece of real infrastructure the redesign depends on, and both Overview's "form movers" and Milestones' freshness rest on it. Implement it with whatever scheduling the app already uses; scope it to tracked players only (not whole-country crawling — that's the next section).

---

## 3. Deliberately NOT built

These are visible in the design as dead or dashed affordances. That is intentional: the product tells the truth about its edges rather than hiding them. Keep them, and keep the copy.

| Not built | Why, and what it would take |
| --- | --- |
| **Player name search across Australia** (sidebar row, Overview card) | BetterScout only knows clubs a scout has actually searched for; rosters are fetched on demand and cached per club. Name search means proactively crawling and indexing ~6,900 clubs' rosters, an indexing strategy, and ongoing staleness management — weeks of infrastructure, and its own decision. |
| **Country-wide hot-form feed** (sidebar row) | Same dependency as name search: you cannot rank "who's in form right now" across the country without having already crawled the country. |
| **Real-time milestone alerts** | Needs the crawl plus scheduled evaluation. The weekly digest in Settings is the deliberately modest version, and it is only as fresh as the last refresh. |
| **Payment collection** | Tiers and caps are real and enforced (`scout_billing.py`); Stripe checkout is a flag flip away, held back on purpose. Follow the club product's precedent (ship the entitlement model, wire collection later). |
| **Share-link expiry enforcement** | The setting is in the design; the check does not exist in `get_shared_card` yet. Either enforce it or hide the control — do not show a setting that does nothing. |
| **Inter-card reordering on the Kanban board** | A dropped card lands at the end of its target column today; the design does not change that. |
| **Player photos from public data** | None exist. The design reserves the frame and falls back to initials; a real photo needs an upload path (2.4.8). |
| **Player ages** | Not in the public payload. Any age shown in the prototype is illustrative only — omit unless the data proves otherwise. |
| **AFL** | Explicitly out of scope. Cricket, Australia, only. |

---

## 4. Suggested sequence

1. **Shell** — `ScoutModuleLayout`, `moduleBrand.scout`, `betterscout.svg`, nav with icons and the two dead rows. Every existing page mounts inside it unchanged. Ship this alone; it is a pure chrome change and instantly makes BetterScout feel like a Better module.
2. **Discover restyle** — presets, sparkline, avatars, filter chips, `Add to watchlist ▾`, `On N watchlists`. Verify per-season grade in `iq_scout`.
3. **Settings** — the org columns and endpoints, because Overview and Milestones both read settings.
4. **Profile** — tabs, chart, notes table, inline recruiting panel, stage control, photo slot.
5. **Overview** — `scout_club_views`, `services/scout_overview.py`, `GET /scout/overview`.
6. **Milestones** — `services/scout_milestones.py`, `scout_milestone_seen`, `GET /scout/milestones`.
7. **Compare** — port the club-side pattern, add the recruiting tab and the PDF export; decide on comparison sharing.
8. **Scheduled refresh** — the cadence job.
9. **People and invites** — roles enforced, invite flow.

Steps 1–2 are safe, self-contained wins. Steps 5–6 are where the new value is.

---

## 5. Migration checklist

New tables: `scout_club_views`, `scout_player_notes`, `scout_milestone_seen`, `scout_invites`, and optionally `scout_shared_comparisons`.

Altered tables: `scout_orgs` (the ten settings columns), `scouted_players` (`photo_url`), `scout_watchlist_columns` (optional `stage_kind`).

Follow the existing conventions exactly: numbered alembic revisions after `240_scout_pricing_tiers`, plus the idempotent mirrors in `main.py`'s lifespan, and **no foreign keys to club tables** from anything scout-scoped.
