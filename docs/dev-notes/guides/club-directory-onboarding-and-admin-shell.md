# Guide: Club Directory crawl and teasers, club onboarding, setup wizard, admin shell, draft pages, KlubPro, dashboard messages

**Read this before**:
- Touching `services/club_directory.py` (discovery, `_upsert_club`, `_prune_committee`, `export_to_comms`), the Rediscover button, or Directory contact/role/`former_at`.
- Touching `services/club_teaser.py`, `club_teaser_report.py`, `scripts/pull_club_teasers.py`, `club_teaser_snapshots`, or the `nightly_club_teasers` job.
- Changing how a club is created (`create_club`, `_onboard_club_core`, self-serve submit), `organisations.onboarding_method`, `admin_identity.py`, or the club-admin mobile backfill.
- Editing the Setup Wizard (`routers/onboarding_wizard.py`, `pages/admin/setup/`, `SetupReturnBar`, `SetupProgressReminder`) or `theme.js` accent pairing.
- Adding a page, tile or tool to the admin app (`AdminLayout`, `ModuleLayout`, `GROUPS`, `HubCard`, `ModuleHub`, `lib/modules.js`, `lib/superNav.js`).
- Draft (PIN) pages, the 423 response, `club_lock.py`, `ClubPinGate`, unpause requests.
- KlubPro migration tooling (`routers/klubpro_migration.py`, `/admin/super/migration`).
- Super admin messages on the club dashboard (`admin_broadcasts`, `AdminBroadcastBanner`).
- Symptoms: teaser pull returns every club `empty` with 204s; departed officer still listed; opted-out officer re-emailed.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/club-directory-onboarding-and-admin-shell.md`. Grep hints: `playHQId`, `admin_broadcasts`, `next_pull_at`, `type_filtered_ids`, `former_at`, `_onboard_club_core`, `password_protected`, `CORE_TILES`, `bs_setup_return`, `safeAccent2`, `migrate_fields`, `backfill_admin_mobiles`.

**Related guides**: comms/segments (Segments `teaser_snapshot`, directory scope rule, `comms_contacts.role`); billing and trials (`start_trial_billing`, module entitlement); CRM/sales (`sync_super_admin_trial_deal`); public site/theme (`theme_config`); migrations and lifespan mirror (check `origin/main` before numbering a migration).

## Standing rules

**Teaser pulls**
1. `marketing_clubs.grassroots_guid` is PlayHQ's search GUID (`playHQId`), not CA's `organisationGuid`; the seasons/participants APIs answer 204 to it. `LiveAPI.resolve_org` finds the club by name and accepts a hit only if its `playHQId` or `organisationGuid` equals the directory guid (two clubs can share a name). An unplaceable club is `empty` after that one call. The snapshot still keys on the directory guid (`org_guid`); `pull_club` calls `resolve_org` only if the API has it.
2. A teaser is not the sync: one season only, nothing written to `organisations`, `players` or `games` (an unclaimed club must not reach the public site, sync scheduler or duplicate checks). A claim runs the normal sync and leaves the snapshot as history.
3. Juniors are decided per grade: stats fetched grade by grade for SENIOR grades only and merged (`merge_rows`). Junior-only club = `junior_only`, no snapshot. Drop CA-redacted names (`********`); a marketing page must not name children.
4. Newest season often has no stats (September): probe newest-first up to `MAX_SEASON_PROBES`; `season_pending` puts the club on the weekly cadence. Find our ladder row by `owningOrganisation.id` (`iq._ladder_rows`), never team name.
5. `version` moves only when content does (`data_hash`); the Chromium email image lives on `/mnt/media` (outside backup). `image_version` is reserved for that renderer. The token is made once and never rotated by a refresh (emailed links must work).
6. `next_pull_at` (indexed) is set at write time: in play 7 days, off season 45, empty 14, junior-only 90, errors 1/3/7/14/30 then flat, plus stable per-club jitter up to +20%. A failed pull keeps the last good snapshot and only backs off.
7. Targets: kind club, not excluded, not `not_interested`, no `existing_org_id`, real CA guid (not `manual:`), no `trial_modules` (`--include-trialists` overrides). Order: never pulled, emailable contact, longest overdue.
8. Who gets a snapshot follows the Directory's type filters: `club_teaser.type_filtered_ids` reads `club_directory._filter_conditions`. Default `DEFAULT_TYPE_MODES` excludes junior, carnival, school, rep, cricket_au; setting `club_teaser_type_modes` overrides (`{}` = none). Ids bound as a uuid array. A NULL test counts as "does not match" (coalesce each condition, or the cricket_au exclude drops every club with a blank field).
9. The job runs by day, never overnight (asked for directly): `OrTrigger`, Perth time, `hour="6-8,21" minute="*/10"` plus `hour="9-20" minute="*/5"`. Id `nightly_club_teasers`; setting `club_teaser_nightly_limit` (clubs per run, unset = 0 = off). Honours the shared Stop switch (`marketing_crawl_control`) between clubs.
10. Segments field `teaser_snapshot` (ready/empty/junior_only/error/none): contact-level rule on `comms_contacts.marketing_club_id`, no MarketingClub join, club-less contact reads `none`. Directory scope only; fails closed in a club build.

**Directory committee (Rediscover)**
11. Discovery was additive (`_store_contact` upserts on lower(email), never removes). Rediscover is the same pass with flags: `discover_clubs(prune=True, retick=True)`, not a second reader. `crawl_batch` runs discovery only `if total == 0 or rediscover`; the Run crawl batch button does enrichment only.
12. Role is resolved within the payload first (one person twice: senior wins) in `_upsert_club`. Rediscover replaces the stored role; the ordinary crawl stays improve-only.
13. Never delete an unsubscribed officer (next crawl re-adds them ticked and we email an opt-out). `_prune_committee` deletes only where nothing a person decided goes with the row; it KEEPS unticked with `former_at`: unsubscribe, bounce, `do_not_contact`, a note, or a `crm_people` link (255's bridge is ON DELETE SET NULL, a delete cuts it silently).
14. Never prune: `source='manual'` contacts, the org club mailbox (`_CLUB_CONTACT_RANK` 5), anything at `_HAND_ADDED_RANK` 99. `_role_for_position` must never return either (suite asserts). `sales_workspace.add_directory_contact` must store `source='manual'` (it once wrote `'api'` and a prune deleted a rep's contact).
15. `contacts` absent/null = payload said nothing, prunes nobody. `contacts: []` = no committee, prunable rows go. An upstream shape change must not empty the directory.
16. A listed officer with an email is ticked (default is "has an email", not `rank <= 4`), never one who unsubscribed/bounced/opted out. Ordinary crawl never re-ticks an unticked contact (`retick=False`); only Rediscover and "Tick officers with an email" do.
17. `export_to_comms` updates rather than skips: refreshes `comms_contacts.role`, fills blank name and club link, never overwrites a hand-set name, never resurrects a suppressed address. `comms_contacts.role` is a stored copy on purpose (departed officers stay in BetterComms) and backs the Role facet.
18. One contact serialiser (`list_clubs` calls shared `_contact_out`); `emptyFilters` is the one facet shape (`CommsLists.jsx` keeps no literal).
19. Rate: `marketing_crawl_min_delay=15.0`/`_max_delay=40.0` before each request behind a module-level `asyncio.Semaphore(1)`; full Rediscover ~30 to 60 min. Single-club Rediscover uses the short interactive delay (0.2 to 0.7s).

**Onboarding a club**
20. Super admin New Club goes through `_onboard_club_core` (first full sync, `auto_yearbooks=True`, Directory link); form slug, short name, contact email, colours are applied AFTER (`upsert_organisation` never sets them). User is created flush-only first (username race surfaces early); membership and trials follow in a try whose failure says "don't retry".
21. A Primary Club Admin is mandatory; staff never choose the password: `password_hash=NULL` + `invite_token`, `user_invite.send_invite_email` sends `/login?invite=`. Do not add the self-serve 4-digit PIN (the entrant must hold the inbox).
22. `services/admin_identity.py` is the one set of primary-admin field rules; only difference is `require_mobile` (mandatory for the club's own admin, optional for staff). Every module trials, Core included (`BILLABLE_MODULES`, `start_trial_billing`, `get_default_trial_days`), with `is_active=True`.
23. `organisations.onboarding_method` (`self_serve_trial|super_admin_trial|direct_subscriber|none`, NULL pre-225) replaced two broken inferences: `trial_engagement.trial_depth_score` reads it (falls back to the primary-admin proxy for pre-225 clubs), and wizard auto-open branch (c) `first_opened_at IS NULL`, not dismissed, method set.
24. `crm.sync_super_admin_trial_deal` stamps `super_admin_trial` and fires `trial_started`, not `self_serve_signup`; no `lead_source` (never fabricate a channel).
25. Club-admin mobile backfill: email match is identity, name match is not, so any email match beats any name match. A name match with two different numbers is refused (father/son). Two numbers under one email: source order (`fee_members.mobile`, linked `players.phone`, Clubs Directory contact via `marketing_clubs.existing_org_id`). Store only `admin_identity.mobile_valid` numbers; report a landline, do not store it. The `fee_members` to `players` join must be org-scoped. Only blank `mobile_number` is touched, never overwritten. `admin_contact_list.admin_rows` is the one definition of "club admin".

**Setup wizard**
26. Route `/admin/setup(/:stepKey)`. `GET /flow` runs `_detect_steps` (cheap org-scoped EXISTS) and persists new completion into `completed_steps`, so `GET /state` (polled every AdminLayout mount) reads stored state only. `POST /steps/{key}` takes `{done?, skipped?}` (exclusive; detection beats a skip). `skipped_steps` = migration 157. Steps the DB cannot see (socials palette in localStorage, review-only fantasy steps) are manual-mark.
27. The `onboarding_wizard_enabled` flag gates nothing now (General Settings toggle inert). Auto-open is conservative: (a) new club, no successful full sync, not dismissed; (b) one-shot reopen-after-sync when stored progress exists; (c) rule 23. Super admins are never auto-navigated.
28. `_sync_ready` accepts `org_full` OR `org_hard_refresh`; "Tidy your data" locks until a successful full pull.
29. Branding step edits `theme_config` (accent/accent2), NOT legacy `primary_color`/`accent_color`. Paint club colour pairs with `var(--pb-gradient)` or `--pb-accent-2-safe`, never raw `--pb-accent-2` (`theme.js::safeAccent2` guards near-black/white per theme).
30. Link-out steps stamp `sessionStorage.bs_setup_return`; `SetupReturnBar` (bottom-centre, in `ProtectedRoute` beside `TrialBanner`) returns. Vital steps (full_rebuild, merge_players, merge_grades) confirm before skip. `SetupProgressReminder` (bottom-right toast) fires every 5th bare `/admin` landing while steps remain, regardless of `dismissed_at`; counted in `localStorage['bs_setup_reminder_visits_<user.id>']`.
31. Sidebar sections and Better HQ links stay alphabetical by label. IQ pre-warm (`services/iq_prewarm.py`): one dossier at a time, at most 40 opponents, 5 min each.

**Admin shell**
32. `AdminLayout` is chrome only (Dashboard, Setup Wizard, tiles, Account, Better HQ). Each product is a `ModuleLayout` surface. Never add Core tools to `AdminLayout` `NAV_SECTIONS`.
33. To add a tool: put the page under the right module layout and add it to that layout's `GROUPS` `items` (`to/label/icon/cap/desc`); sidebar, group page and counts derive from it. Group `key`s drive `:group` URLs: rename labels, never keys.
34. `CORE_TILES` (BetterStats) is in `lib/modules.js` outside `MODULE_INFO` (entitlement/billing); `alwaysOpen` keeps it entitled. Use `HubCard` for any menu card. Tool URLs did not move; `/admin/yearbook` stays standalone.

**Draft (PIN) pages**
35. Migration 205: `organisations.password_protected`, `.password_protect_reason` (`'draft'|'trial_ended'`), `.access_pin_hash` (bcrypt), audit columns; table `club_unpause_requests`. Independent of `is_active`; the gate checks `password_protected` FIRST.
36. `services/club_lock.py` (modelled on `bs_avail`): cookie `bs_lock` (signed JWT, HttpOnly, 30 days). `GET /{slug}` raises 423 (not 403) with `lock_detail`, ahead of `_public_blocked`. `POST /{slug}/unlock` is rate-limited with lockout. `POST /{slug}/request-unpause` only for `trial_ended`; emails `cricket@bettersports.com.au` deliberately, `reply_to` the requester.
37. A club enables Draft itself only while `subscription_status` is `trial` or `active` (off always allowed), always reason `'draft'`; `'trial_ended'` is Super Admin only. Frontend: `useClub.js` `locked` on 423; `ClubPinGate` is checked before `inactive`/`notFound` in the 12 public pages. It is a soft gate: only `GET /clubs/{slug}`, ladders and website are gated server-side.

**KlubPro migration (super admin)**
38. Lazy second engine `services/klubpro_db.py` (`KLUBPRO_DATABASE_URL`), never ORM-mapped, raw schema-qualified SQL, never Alembic. Router `require_super_admin`. Backup/batch tables are BetterStats-side (migration 072).
39. Invariants (`services/klubpro_migration.py`): fill gaps, never clobber with empties; `is_opening_batsman=False` = no info; skills compare as a set; write only `MIGRATABLE_FIELDS` (not first/last/nickname). Flow: dry-run, confirm, per-row backup, write, rollback-able. `plan_player` is the one source for dry-run and import; dry-run reflects saved approvals.
40. Approve is not import: only Import writes `players`. `upsert_match_mapping` UPDATEs in place for reject/skip with past-tense `match_status`. Approve first frees the KP id from any other BS player (unique on KP id), so `klubpro_player_id` must be nullable (`ensure_match_columns`).
41. KlubPro stages display labels, BS stores codes: `_norm_batting_hand/_norm_bowling/_norm_gender/_norm_role` (mirror `frontend/src/lib/playerAttributes.js`); unrecognised = empty; `bowling_type` sets both bowling columns; import sets `photo_url` as well as `photo_data`/`photo_mime`.
42. Club mapping is UPDATE-or-INSERT on `club_mappings`, never DELETE; conflict returns `{status:'conflict'}` with HTTP 200 (api client hides status), UI confirms then sends `force`. `sponsor_import_selections` is not the source of truth (dedupe on the BS unique index). Client auto-suggest never auto-picks when two or more candidates share a name (`ambiguous`).

**Dashboard messages (migration 312)**
43. Tables `admin_broadcasts` + `admin_broadcast_receipts`; DDL once in `services/admin_broadcast_ddl.py` (alembic and lifespan). Banner `AdminBroadcastBanner.jsx` mounted ABOVE the Welcome heading in `AdminDashboard.jsx` only.
44. Audience `all|clubs|users`; `audience_roles` (`all_admins` = club_admin AND club_member, `club_admins`, `primary`) narrows the first two; a named-user list is never narrowed. Archived clubs never counted; composer refuses an archived club or non-club-admin user. Persistence `until_cleared` (no close) | `dismissible` | `view_once_user` | `view_once_club`; `expires_at` stops any.
45. View-once runs on a receipt the browser posts AFTER drawing, not on the GET; `/seen` records only ids the user can currently see. Staff acting as a club see every live message aimed at it, marked `preview`; `/seen` and `/dismiss` store nothing (must not use up a view-once).

## Traps and failure signatures
- Every club `empty`, all 204: wrong guid namespace (rule 1). Real cost is ~15 to 80 calls a club; re-read `api_calls` off a fresh `--sample`.
- Rep's typed contact vanishes after Rediscover: stored `source='api'` (14). Unsubscribed officer re-emailed: row deleted instead of `former_at` (13). Directory emptied: absent `contacts` read as `[]` (15).
- Type filter drops clubs with blank fields: NULL logic (8). Email image invalidated weekly: `version` bumped without a content change (5).
- Staff-created club's admin never sees the wizard: `onboarding_method` unset (23). "Tidy your data" locked after Full Rebuild (28). Dead-looking accent (29).
- KlubPro "approved but data not pulled across": Import never run. A club imported before value normalisation (Murdoch) needs a re-Import.

## How to verify a change here
- `backend/verification/verify_club_teaser.py` (real Postgres, scripted CA, no live call). Controls: reverted resolved-guid/one-call/unplaceable checks fail; change detection and junior filter neutered fail; service-absent must REPORT not crash. Never run against live CA: `--sample 20` first.
- `verify_committee_rediscover.py`: seed the pre-293 table in RAW SQL (the ORM has the columns). Control: prune, retick, role refresh neutered fails.
- `verify_admin_mobile_backfill.py` (control: org scoping, mobile check, ambiguity refusal neutered).
- `verify_admin_broadcasts.py` (control: view-once and primary filter neutered) and `frontend/verification/verify_admin_broadcasts_browser.mjs` (control: banner unmounted).
- New Club flow suite: archive names no file; grep `verification/` for `onboarding_method`.

## Operator commands and scripts
- `python -m app.scripts.pull_club_teasers all --limit N --apply` (dry run by default). `--sample N` runs clubs one at a time with status and call counts. Also `--include-trialists`, `--type key=include|exclude`, `--no-type-filter`. `--apply` ends with the work report (`club_teaser_report.py`; under 20 clubs it warns the sample is too small).
- `python -m app.scripts.backfill_admin_mobiles [<org|all>] [--apply] [--email-only]` (dry run by default, no network).
- Set General Settings `club_teaser_nightly_limit` to switch the scheduled pull on (no UI input yet).
- KlubPro deploy: set `KLUBPRO_DATABASE_URL` (never commit) and share a Docker network with `klubpro-postgres`. See `docs/klubpro-migration.md`, `docs/marketing-club-directory.md`.

## Open follow-ups
- Teaser: `/preview/{token}` page, PNG renderer, `{{teaser_url}}` merge variables, match/lineup layer, limit setting input.
- No `role` Segment field (only a Lists/Segments facet). Nothing prunes `former_at` contacts (deliberate); nightly discovery is still additive.
- Club-admin mobile not filled at account creation.

## Flags: conflicting, superseded or possibly obsolete guidance
- [FLAG-CDOAS-1] Teaser section says "NUMBERED 312 after merging origin/main" | code has `312_admin_broadcasts.py` and `314_club_teaser_snapshots.py`, heading says 314 | teaser section (L538-640) | retire the 312 remark.
- [FLAG-CDOAS-2] Teaser section says ~25 calls a club and "nightly at 03:30" | first section measured ~15 to 80; scheduler runs by day | L538-640 vs L3-31 | trust the latter.
- [FLAG-CDOAS-3] New Club section reuses Twenty `push_self_serve_registration` | Twenty retired, function no longer in `app/` | L8465-8535 | retire that bullet, keep the "no false self-serve stage" lesson.
- [FLAG-CDOAS-4] Admin navigation says BetterClubManager routes are super-admin gated, "Coming soon" | text itself says superseded in v9.6.1 (capability-gated for club admins) | L10101-10167 | verify against `App.jsx`.
- [FLAG-CDOAS-5] Draft section emails `cricket@bettersports.com.au`, platform support is `support@bettersports.com.au` | deliberate, may be stale | L10041-10100 | verify.

## Section coverage
| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| The teaser pull was handing CA the wrong kind of id (L3-31) | rules extracted | Standing 1; Traps 1; Flag 2 |
| BetterCricket's messages on the club admin dashboard (L151-189) | rules extracted | Standing 43 to 45; Traps last |
| A teaser snapshot of a club that has not registered (L538-640) | rules extracted | Standing 2 to 10; Operator; Open; Flags 1, 2 |
| The Club Directory's committee only ever grew (L2583-2700) | rules extracted | Standing 11 to 19; Traps 2 |
| Super Admin New Club = the self-serve registration (L8465-8535) | rules extracted (Twenty part superseded) | Standing 20 to 24; Flag 3 |
| Password-protected "Draft" pages + trial-ended unpause requests (L10041-10100) | rules extracted | Standing 35 to 37; Flag 5 |
| Admin navigation, module surfaces (L10101-10167) | rules extracted (BetterClubManager gating superseded v9.6.1) | Standing 32 to 34; Flag 4 |
| Club Setup Wizard (L12574-12665) | rules extracted | Standing 26 to 31 |
| . Periodic setup reminder (v8.70.3) | rules extracted | Standing 30 |
| . Secondary accent, luminance-guarded (v8.70.2) | rules extracted | Standing 29 |
| KlubPro to BetterStats Migration Tooling (L13719-13843) | rules extracted | Standing 38 to 42; Traps 4; Operator |
| A club admin's mobile is already written down at their club (L16912-16979) | rules extracted | Standing 25; Operator; Open |
