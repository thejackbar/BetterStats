# Flags: conflicting, superseded or possibly obsolete guidance

Collected on 2026-09-30 while splitting the old `CLAUDE.md`. Nothing here was deleted from the archive; each entry says what the old text claims, why it is doubtful, and a recommended action. The agents that wrote each guide checked what they could against the code, and the split's author re-checked the ones marked `re-checked`. An entry marked `RESOLVED` was found to be wrong during the split and is kept only so nobody re-raises it.

Format: `[ID] what the archive says | why it may be stale, with evidence | archive section and original lines | recommended action`. Each entry is also in the guide named in its heading.


## betterfootball-afl

See `guides/betterfootball-afl.md`.

- **[FLAG-AFL-1]** Next passes listed: self-serve registration, weekly sync scheduler, BetterSelect AFL, other modules | BetterSelect, BetterAdmin, Socials, votes, manual entries have since shipped; self-serve and scheduler not checked | Multi-sport: the AFL silo, L9925-9974 | verify
- **[FLAG-AFL-2]** `organisations.competitions` (JSON display history, 262) versus `club_competitions` table and `services/afl/competitions` (filter grouping) | two different "competitions" concepts in football, easy to confuse | re-graded team section L6644-6759 and admin port L9975-10040 | keep both
- **[FLAG-AFL-3]** `_DROP_ORDER` described as "wings, then ruck rover"; code holds position codes (`LW`, `RW`, `RR`, `LBP`...) in `services/afl/select.py` | consistent, read the constant | BetterSelect on BetterFootball L76-150 | keep
- **[FLAG-AFL-4]** `discoverTeamFixture` works on the AFL tenant but not cricket's Grassroots API | cross-archive claim, not re-verified live | re-graded team section L6644-6759 | verify if PlayHQ changes
- **[FLAG-AFL-5]** Old `POST /achievements/import` and template remain, unused by the UI | may be dead, cricket may use them | Import Awards L9137-9217 | verify before deleting

## betteriq

See `guides/betteriq.md`.

- **[FLAG-IQ-1]** `DOSSIER_VERSION` "bumped to 3", `DEEP_VERSION`→2 | code has `DOSSIER_VERSION = 10`, `DEEP_VERSION = 3`; numbers are history | "Danger/false-threat alerts", "Manual scouting cards" (L13501-13527, L13641-13718) | keep the rule, ignore numbers.
- **[FLAG-IQ-2]** "NL Q&A is the one remaining phase", "no LLM" | `services/iq_ask.py` exists (`MAX_STEPS = 8`) and v8.74 documents its tools | "Opposition, Selection & Player Trends" vs "Filters honest" (L13501-13527, L13528-13596) | retire "parked"; keep "synthesis is rule-based".
- **[FLAG-IQ-3]** `_safe(session, factory, default)` | code signature is `_safe(session, factory, default, key=None, degraded=None)`, failed cards go in a `degraded` list | "Review Fixes v2.12.1" (L13597-13606) | verify, update rule 24.
- **[FLAG-IQ-4]** "We don't store the toss" | a scorecard note elsewhere in project docs says `matchSummary.teams` carries `wonToss`/`battedFirst`, contradicting the sync-path claim | "Bowler deep-dive, captaincy & bowling discipline" (L13616-13623) | verify against a live payload and `games` schema.
- **[FLAG-IQ-5]** Files not covered by the archive: `iq_phases.py`, `iq_phrases.py`, `iq_players.py`, `iq_radar.py` | their rules are unrecorded | all sections | verify when touching.
- **[FLAG-IQ-6]** Branch name `claude/gifted-babbage-7QE8g` | dated, likely merged | "Review Fixes v2.12.1" (L13597-13606) | retire.
- **[FLAG-IQ-7]** v2.12.2 scopes team analysis by single `grade_id`; v8.74 filters by grade names with `'||'` | not a conflict, but a new card must pick the right path | "Review Round 2" vs "Filters honest" (L13607-13615, L13528-13596) | verify.

## betterposts-socials-and-media

See `guides/betterposts-socials-and-media.md`.

- **[FLAG-POSTS-1]** "Only C1-C4 decompose ... 40+ layouts, large work" | wrong for reflow and layering (v9.74/v9.76) but still true for decomposition; `templateToBlocks.js` exists | "A FIXED LAYOUT CANNOT RE-LAY ITSELF OUT AT 4:5" L995-1085 | keep (decomposition only)
- **[FLAG-POSTS-2]** Fit/Fill picker and `data-post-frame` checks | superseded by v9.74.0; `postSizes.jsx` still exports `PostFrame`/`frameTransform(mode='fit')` for scorecards | same, L995-1085 | verify suite no longer asserts the picker
- **[FLAG-POSTS-3]** `behind` flag, `setBehind`, `pb-template-seethrough` | retired by v9.76.0; grep of `frontend/src` finds none of them | "Every template reflows..." L1086-1200 | retire (rule 26)
- **[FLAG-POSTS-4]** Videos section names `MARKETING_PATHS` as the Navbar-suppress list; other archives record a later split into `OWN_NAV_PATHS` (`MARKETING_PATHS` also forces dark theme and `ClubCTABar`) | `lib/marketingPaths.js` lists `/videos` in `MARKETING_PATHS` | "Instructional videos" L10210-10378 | verify before adding any route

## betterselect-selection-and-nets

See `guides/betterselect-selection-and-nets.md`.

- **[FLAG-BSN-1]** Archive cites Postgres suites for rules, age maths, live session, roster, guests, squads pools | Checked across the whole repo during the split. Present: `backend/verification/verify_net_batting_order.py`, `verify_net_checkin.py`, `verify_player_kit.py`, `verify_multi_squad.py`; `backend/scripts/verify_squads_feedback.py`; browser suites in `frontend/verification/` (`verify_net_checkin_browser.mjs`, `verify_net_batting_order_browser.mjs`, `verify_net_admin_browser.mjs`, `verify_net_alert_browser.mjs`, `verify_guest_promotion_browser.mjs`, `verify_squads_pools_browser.mjs`). Not found anywhere: the Postgres suites the archive describes for selection rules, age maths, the live net session, guests and the squad pools | several sections | verify before citing the missing ones as existing; the check counts in the archive were not re-run.
- **[FLAG-BSN-2]** Kit section notes `require_module("admin")` names the module "admin", then says `module_display_name` fixed it | `auth/modules.py:431` defines it | L12119-12320 | keep later (fixed).
- **[FLAG-BSN-3]** Squads section says AFL has no BetterSelect squad board | football later got its own select module (`betterfootball-afl` archive) | L4592-4665 | verify.

## betterselect-votes-and-medals

See `guides/betterselect-votes-and-medals.md`.

- **[FLAG-VOTES-1]** The v8.92 section describes `vote_settings` as an org singleton with the settings, link and QR on a Settings tab | Superseded by migration 267 (`vote_medals`, `vote_settings` unread). `routers/votes.py` now has `/medals` CRUD, `/medals/{id}/regenerate`, and still exposes `/settings` GET/POST (line ~263, ~274), so check whether `/settings` is a compatibility shim before relying on it | BetterSelect — Vote collection (v8.92.0, migration 193, Jul 2026), L13201-13421 | fix the docstring in a code change (documentation-only here, so not done)
- **[FLAG-VOTES-2]** Archive cites verification suites (59/17 cricket, 47/27 football) | RESOLVED during the split: an agent first reported them missing after searching only `backend/verification` and `frontend/verification`; they exist as `backend/scripts/verify_vote_medals.py`, `verify_afl_votes.py`, `drive_vote_medals.py` and `drive_afl_votes.py`. Their check counts were not re-run | A club runs several medals, L6450-6568 | keep; note that the suites live in `backend/scripts/`
- **[FLAG-VOTES-3]** The redesign and v8.94 notes describe leaderboard/hub behaviour in terms of `data.settings.token` and "the club link" | With medals each medal has its own `link_token`; a share panel or copy-link should be per medal. Not checked in the frontend | Votes redesign, L13422-13500; v8.94.8 sub-note in L13201-13421 | verify
- **[FLAG-VOTES-4]** The v8.92 section says `fixture.id == game GUID` is wrong "at launch" and fixed in v8.94.5, yet the Fixture model docstring still says otherwise | Checked: the `Fixture` docstring in `backend/app/models/db.py` (around line 1516) still says `id == the CA/PlayHQ game GUID` for the 'playhq' source, while synced 'grassroots' fixtures mint a random uuid4 and keep the match GUID in `playhq_id`. The docstring is stale for the grassroots source | L13201-13421 (v8.94.5 bullet) | fix the docstring in a code change (this split is documentation-only, so not done here)

## billing-stripe-and-invoicing

See `guides/billing-stripe-and-invoicing.md`.

- **[FLAG-BILL-1]** "The webhook is the only place entitlement is actually granted" | Conflicts inside the archive: add-on grants synchronously in `create_checkout_session`, and pay-by-invoice grants on `invoice.paid` routed by `billing_method`. Effectively three paths: card new-signup via webhook, add-on synchronous, invoice via its own `invoice.paid` branch | Stripe Checkout section (L14628-15067), first bullets vs "Adding modules" | verify, then rewrite as "three grant paths".
- **[FLAG-BILL-3]** "Not built: applying a coupon to an already-live subscription" | Superseded by `redeem_for_existing_subscription` / `attach_discount_to_subscription` in the managed-coupon section | Bundle discount coupon fixes, "Not built" | retire.
- **[FLAG-BILL-4]** "Not built: Stripe Customer Portal" | `routers/billing.py` now has `/payment-methods*` routes and `services/stripe_connect_billing.py`/`stripe_connect_client.py` exist; neither is in the archive | Stripe Checkout section, "Not built this round" | verify what exists and document in a fresh section.
- **[FLAG-BILL-5]** Section 1 says checkout "always shows the stub notice" and `submitSubscribe` is the future call site | The real flow has shipped (rules 10 to 20) | Billing checkout section (L14594-14627) | keep the flag rules, retire the stub wording.

## club-directory-onboarding-and-admin-shell

See `guides/club-directory-onboarding-and-admin-shell.md`.

- **[FLAG-CDOAS-1]** Teaser section says "NUMBERED 312 after merging origin/main" | code has `312_admin_broadcasts.py` and `314_club_teaser_snapshots.py`, heading says 314 | teaser section (L538-640) | retire the 312 remark.
- **[FLAG-CDOAS-2]** Teaser section says ~25 calls a club and "nightly at 03:30" | first section measured ~15 to 80; scheduler runs by day | L538-640 vs L3-31 | trust the latter.
- **[FLAG-CDOAS-3]** New Club section reuses Twenty `push_self_serve_registration` | Twenty retired, function no longer in `app/` | L8465-8535 | retire that bullet, keep the "no false self-serve stage" lesson.
- **[FLAG-CDOAS-4]** Admin navigation says BetterClubManager routes are super-admin gated, "Coming soon" | text itself says superseded in v9.6.1 (capability-gated for club admins) | L10101-10167 | verify against `App.jsx`.
- **[FLAG-CDOAS-5]** Draft section emails `cricket@bettersports.com.au`, platform support is `support@bettersports.com.au` | deliberate, may be stale | L10041-10100 | verify.

## clubhouse-committee-and-plans

See `guides/clubhouse-committee-and-plans.md`.

- **[FLAG-CTE-1]** Headings say "BetterClubhouse" (v9.3 to v9.7); v9.40.0 renamed back | `BILLABLE_MODULE_NAMES` says BetterAdmin; identifiers keep "clubhouse" | sections 1, 7 to 10 | keep; BetterAdmin for anything a person reads.
- **[FLAG-CTE-2]** `?cascade=true` opt-in on plan/pillar delete vs "no `cascade` flag any more", both in section 1 | no `cascade` in `routers/committee.py` | section 1 (archive L211, L360) | retire the `?cascade` bullet.
- **[FLAG-CTE-3]** 230: "a deleted plan leaves its objectives" | superseded by 276; action/motion half holds | section 9 (archive L765-771) | keep that half.
- **[FLAG-CTE-4]** 232: pillars club-scoped across plans | superseded by 275; rest of 232 holds | section 3 (L7854-7903) | retire that claim.
- **[FLAG-CTE-5]** v9.4.0 follow-up appears twice; the first lists Gantt, upload, Office Bearer sync as "not built" | all three now exist (218, `ActionTimeline`, `office_bearers.py`) | sections 7, 8 | retire "not built" lists.
- **[FLAG-CTE-6]** Section 8 names `ObjectivesTab`, `ActionPlanPanel` | now `PlanTab`, `ActionEditor` | sections 8, 9, 1 | retire old names.
- **[FLAG-CTE-8]** Archive cites Postgres and Chromium suites for plans, room, minutes, agenda, `PersonSearch`, documents | `backend/verification` has none of them; only two frontend suites exist | all sections | verify before trusting a claimed check.
- **[FLAG-CTE-9]** Legibility: room, `ObjectiveSelect` paint no faint text | `MeetingRoom.jsx` clean; `governance.jsx` has 115 `text-pb-faint`/`faintest` uses | section 11 (archive L1149) | verify picker and vote list.
- **[FLAG-CTE-10]** Roster regeneration and `owes_money` belong to other areas | overlaps sibling guides | sections 7, 8 | keep one line here.
- **[FLAG-CTE-11]** Seed label hardcoded "(18)" committee roles | `STARTER_COMMITTEE_ROLES` appears twice in `services/roles_activities.py` (L69, L115) | section 10 (archive L1046-1049) | verify.
- **[FLAG-CTE-12]** 220 renumbered because AFL took 219 | history; same collision trap recurs | section 11 (archive L1094-1098) | keep as reminder: check `origin/main` at merge.

## clubhouse-people-roster-fees

See `guides/clubhouse-people-roster-fees.md`.

- **[FLAG-CLUB-1]** Merge section calls the module BetterClubhouse. | Reversed in v9.40.0; `modules.py` has `"BetterAdmin"` (comment: "briefly BetterClubhouse"). | BetterAdmin to BetterClubhouse merge, L9341-9486 | keep structure, retire naming.
- **[FLAG-CLUB-2]** "Two things deliberately still say BetterAdmin" (marketing, `billing_pricing.py`). | Now everything says BetterAdmin; Stripe Product names keep their creation-time name. | same, L9341-9486 | retire; verify Stripe dashboard.
- **[FLAG-CLUB-3]** Merch: "toggle covers fees+comms+merch", Equipment as a Merch page. | Group is fees, comms, merch, crm; Equipment moved to `club_assets` (279). | L12891-12984 vs L5310-5391 | verify, retire Equipment detail.
- **[FLAG-CLUB-4]** Directory search "above the filter buttons (v9.51.0)" vs "below the buttons that narrow the list (v9.52.1)". | Conflicting wording; later text wins. | L8536-8589 vs L5134-5309 | verify on live Directory.
- **[FLAG-CLUB-5]** Paid via `roster.area_pay_kinds`. | Superseded by 306; function gone. Snapshot rule holds. | L9218-9282, superseded by L8699-8976 | retire resolver.
- **[FLAG-CLUB-6]** Nav `super` flag in the merge section. | Removed in v9.6.1; capability per item is the rule. | L9341-9486, L9647-9671 | retire.
- **[FLAG-CLUB-7]** Draft minutes (`claude-haiku-4-5`, 10/hour/club, 503 without key). | Route and model exist; limit and 503 not re-checked. | L9218-9282 | verify.

## comms-audiences-and-notifications

See `guides/comms-audiences-and-notifications.md`.

- **[FLAG-COMMS-1]** Admin-contact rule cites "the Twenty pushes" for archived-club exclusion | Twenty CRM is retired (no `twenty` in `admin_contact_list.py`) | "Every club admin, on one internal list" (L16805-16911) | keep the rule, ignore the Twenty reference.
- **[FLAG-COMMS-2]** Old Notification Centre says "no dedicated notifications table", three endpoints | `routers/notifications.py` also has `/settings`, `/settings/events/{event_key}`, `/settings/preferences/{event_key}`, `/feed`, `/feed/read` (grep) from the 9.69.0 system | "Notification Centre (v7.7.3)" (L15738-15771) vs "A club decides what it is told about" (L2701-2886) | verify what the bell reads today before editing either.
- **[FLAG-COMMS-3]** "AFL silo untouched" | later work elsewhere mounts cricket routers on football | "A club decides..." (L2701-2886), "Every club admin..." (L16805-16911) | verify before assuming football is covered.
- **[FLAG-COMMS-4]** `FACETS` gained `role` in "migration 295's commit"; `PROJECT_RULES.md` cited as scope authority | migration numbers were renumbered often; the file was not opened | "A FACET LISTED IN THE KIT..." (L1577-1630), "A club's trial..." (L16980-17074) | verify both before relying on them.

## cricketstatz-import

See `guides/cricketstatz-import.md`.

- **[FLAG-CSI-1]** Per-season source marker (`seasons.stats_source`, hand-back, marking timing, 'playhq' state) | Superseded by per-match pairing; code confirms helpers removed, `/superseded/clear` unrouted, column read only by `superseded_years` | v9.68.4, v9.69.2, v9.69.3, v9.69.4, v9.69.8 (L11356-11474, L11583-11750) | retire; lessons kept.
- **[FLAG-CSI-2]** v9.70.0 says a tie is refused; v9.70.2 says it is paired off | later note wins; `assign` not re-read | v9.70.0 (L10782), v9.70.2 (L11286) | verify in `match_pairing.assign`.
- **[FLAG-CSI-3]** v9.70.10 says both views carry a `pairing_applied` guard column; v9.70.11 says it crash-looped boot and was reverted | `grep pairing_applied backend/app` finds nothing | L10947, L10985 | retire the guard; keep verify and hourly repair.
- **[FLAG-CSI-4]** v9.70.6: a paired imported match is never counted from the import at aggregate level | `superseded_ddl.py` `counts_here` now also counts it when `pair_prefers_import` AND `seasons.import_authoritative` (later migration 309 "re-sourced season counts per match") | L11145, L10782 | verify against the stats guide before relying on rule 24.
- **[FLAG-CSI-5]** v9.68.3/9.68.4: overlapping synced seasons are skipped by default (`synced_years` 'skip'), 'cricketstatz' marks seasons so CA steps aside | code keeps the skip default and the option, but marking is gone; the "steps aside" note text is likely stale | L11686-11821 | verify intended default under the AND design.
- **[FLAG-CSI-6]** Migrations 285, 286, 287, 290, 291/292, 293 | 303 and 309 also re-run `superseded_ddl.STATEMENTS`; numbers are history | throughout | keep; edit `STATEMENTS`, not a new copy.

## cross-club-and-data-safety

See `guides/cross-club-and-data-safety.md`.

- **[FLAG-XCLUB-1]** v7.32.1 calls `WHERE s.organisation_id = :org` "already correct" (yearbooks, iq_trends, iq_selection) | v9.62.0 says never use it for a per-game "ours" test and lists yearbook/fantasy as still having it | they differ by read shape (season-aggregate vs per-game) | "Cross-Club Player Over-Count Fix"; "A FIXTURE BELONGS TO BOTH CLUBS" | keep both, read by shape.
- **[FLAG-XCLUB-2]** v9.53.10 and v9.53.11 list the career header and season table counting every game as "noticed, not fixed" | v9.53.12 applied `_club_game_clause` to every player read and asserts they agree | superseded | "seasons drawn two and three times over" (v9.53.10, v9.53.11, v9.53.12 sub-rows) | retire.
- **[FLAG-XCLUB-3]** The nine tables in 142, the 02:30 Perth time and the five-pass bound come from the archive | `GROUP_CLUBS_PER_RUN = 40` and migrations 060, 062, 067, 142, 143, 167, 169, 223 exist; the rest not re-checked | "Super Admin Club Delete"; "Grouping is a job" | verify.
- **[FLAG-XCLUB-4]** `services/org_merge.py` mentions `_resolve_org_grade`/`_resolve_org_player` | not in this archive | may carry more per-club id rules | verify if merging organisations.

## data-sources-and-sync

See `guides/data-sources-and-sync.md`.

- **[FLAG-SYNC-1]** "`playhq_partner_client.py` still used by games, records and organisations routers; live scorecard view for Partner-only games" | No such file exists in `backend/app/services` and nothing imports it; `routers/games.py` has no Partner call | PlayHQ Partner API — May 2026 Audit (L12780-12799) | retire.
- **[FLAG-SYNC-2]** "`suggest_phq_ids()` powers the PHQ ID Match page `/admin/phq-match`" | `suggest_phq_ids` is not in `backend/app`; no phq-match route found | PlayHQ Partner API — May 2026 Audit (L12780-12799) | retire.
- **[FLAG-SYNC-3]** "`deep_sync_player()` calls the Partner API, ~3 seasons" | Now delegates to `sync_organisation(kind="player_deep")`; docstring says the Partner path is retired; still routed from `club_admin.py` | Sync Architecture (L12745-12779) | keep as "delegates to the org sync".
- **[FLAG-SYNC-4]** "The 204 gap is minimal, Partner sync not needed" | `sync.py` (~L1806) says a 204'd match has NO fallback and stays missing on every sync incl. Full Rebuild; `list_skipped_matches` exists | PlayHQ Partner API — May 2026 Audit (L12780-12799); Sync Architecture | verify per club with the script; treat as a known gap.
- **[FLAG-SYNC-5]** "`participantId` is the same GUID as `players.id`", "`grade_id` is the same UUID as `grades.id`", "uses `session.get(Grade, ...)`" | True only for legacy single-club rows; per-club uuid5 ids and `grassroots_id` now exist (`_resolve_org_grade`, `_resolve_org_player`) | Data Source Topology (L12708-12733); Sync Architecture (L12745-12779) | keep, with rule 10 as the correction.
- **[FLAG-SYNC-6]** "Full sync scheduled weekly, the weekly job" | Now Sun and Mon 01:00 Perth, incremental `org_recent` by default | Sync Architecture (L12745-12779) vs scheduled sync (L7293-7402) | keep the newer section.
- **[FLAG-SYNC-7]** "`main.py` restart self-heal resumes only the two full kinds" | Not re-checked; `_FULL_SYNC_KINDS` and `auto_sync._FULL_KINDS` are (`org_full`, `org_hard_refresh`) | The scheduled sync pulls the period's results (L7293-7402) | verify before adding a kind.
- **[FLAG-SYNC-8]** UK plan names `playcricket_scores_client` and org columns | Neither exists in `backend/app` | UK Expansion — Play-Cricket Data Source (L12734-12744) | keep as design only.
- **[FLAG-SYNC-9]** Applecross counts (3957 games, 41423 batting rows), "~3 seasons", "52 seasons" | One-off May 2026 evidence, drifted | May 2026 Historical Data Fix (L12820-12838); Data Source Topology | do not treat as current.
- **[FLAG-SYNC-10]** Match-lookup is described for cricket only | `routers/afl/social.py:236` has its own copy | A PlayHQ game-centre link (L8075-8164) | verify the sport.

## imports-manual-entries-and-data-tidy

See `guides/imports-manual-entries-and-data-tidy.md`.

- **[FLAG-IMP-1]** Archive says the upload cap was 8 MB | code has 64 MB (`_MAX_GAME_UPLOAD_BYTES`, nginx `64m`) | THE SHEET IS PARSED ONCE (L10460-10557) | keep rule 20, ignore the number
- **[FLAG-IMP-2]** 309's `import_authoritative` whole-season model versus later per-match pairing | `import_authoritative` still in `superseded_ddl.py`, so both are live in the views | A RE-SOURCED SEASON COUNTS PER MATCH (L641-788) | verify with `cricketstatz-import` before changing either
- **[FLAG-IMP-3]** Section says the 037 fan-out was "NOT fixed", then "FIXED" | later wins | same section | keep rule 21
- **[FLAG-IMP-4]** Fix credits migration 169 for `v_effective_games` columns | `superseded_ddl.py` re-issues that view every boot, so edits in 169 alone are lost | Uploaded scorecard missing (L15560-15609) | keep rule, edit the view in `superseded_ddl.py`
- **[FLAG-IMP-5]** Reader notes cite `anthropic 0.40.0` | still pinned in `requirements.txt`; claims age | Scorecard reader (L15646-15737) | verify on any bump

## marketing-funnel-ads-and-webinar

See `guides/marketing-funnel-ads-and-webinar.md`.

- **[FLAG-MKT-1]** Archive says `CAMPAIGN_UTM_NAMES` became a set | code now `CAMPAIGN_UTM_CAMPAIGNS` (`meta_ads.py:190`, used by `sales_workspace.py:718`) | ONE CAMPAIGN, TWO PRODUCTS (L789-994) | keep rule, use new name.
- **[FLAG-MKT-2]** Archive names `_META_VISITOR_SUBQUERY` (and `_PLAIN`) | code has `_META_VISITOR_EXISTS = _meta_visitor_exists(_SINCE_LOWER_BOUND)` | L15458-15509 | verify names.
- **[FLAG-MKT-3]** Phone "REQUIRED" then optional; StreamYard link "in the JS bundle" then removed | both reversed in v9.71.3; `EVENT.watch_url` is server side (`webinar.py:73`) | webinar section (L1827-2032) | rules 43, 44 are current.
- **[FLAG-MKT-5]** Two sub-notes carry v9.71.5 and 300 says v9.71.6 | labels collided at merge | L2179-2582 | trust migration numbers (296, 298 to 301), not versions.
- **[FLAG-MKT-6]** v9.71.4, migration 298 gate and association refresh are Club Directory rules nested under the webinar section | not webinar code | L2117-2281 | move to the club directory guide (kept as rules 52 to 54).
- **[FLAG-MKT-7]** Wizard Clubs v9.23.0 searched table versus v9.23.1 | later changes it (`resolved_searched_clubs`) | L7437-7573 | later wins, read both.
- **[FLAG-MKT-8]** Self-serve says Twenty must be configured for the Hot-100 Lead | Twenty retired in v9.71.0 | L15249-15329 | verify `push_self_serve_registration`.
- **[FLAG-MKT-9]** Suites cited for wizard clubs, search beacon, self-serve, usage | none found in `backend/verification` or `frontend/verification` | L7437-7573, L15249-15559 | verify or retire.
- **[FLAG-MKT-10]** Webinar date (Mon 21 Sep 2026) is a hardcoded constant | today is 30 Sep 2026 | webinar section | verify `EVENT` and `webinar_recording_url`.

## platform-ops-and-site

See `guides/platform-ops-and-site.md`.

- **[FLAG-OPS-1]** Archive says the Branch is `claude/fix-historical-game-data-QEN3b` and to push to it AND to `main` via MCP after each change. | Stale: that branch is not in `git branch`, the working branch is `main`, and deploy pulls `origin main`. | Branch, original L12696-12700 | retire (do not follow it; use the branch the session is on).
- **[FLAG-OPS-2]** Archive says `deploy.sh` has a `[4/4]` step for the NPM refresh and that the deploy recreates with `up -d --no-deps --force-recreate`. | `deploy.sh` now has 7 steps: pull, build, `rm -sf` then `up -d --no-deps` (not `--force-recreate`, which hit a fixed-`container_name` rename conflict), NPM refresh (4), API health check (5), backup-agent check (6), backup timer install (7). Rule 2's long form is approximate. | Server Deploy Command, L12334-12355; Admin Outage #2, L12373-12392 | verify against `deploy.sh`, keep the `COMPOSE_PROJECT_NAME`, `--no-deps` and no-`--remove-orphans` rules.
- **[FLAG-OPS-3]** Deploy and outage text say "see CLAUDE.md 'June 2026 Production Outage - Post-Mortem'". | `deploy.sh` and `deployafl.sh` comments still cite that CLAUDE.md heading, which now lives only in the archive and this guide. | Server Deploy Command; both post-mortems | verify, then repoint those comments here.
- **[FLAG-OPS-4]** Post-mortem tells you to use `docker run`, `docker volume ls`, `docker exec` for diagnosis, while the deploy rules ban bare `docker`. | The diagnostics and volume clone are one-off incident tooling against volumes outside any compose service. | Server Deploy Command; June 2026 Production Outage, L12356-12372 | keep both; use `docker compose exec` wherever a service exists.
- **[FLAG-OPS-5]** Archive says `BetterAdmin = fees + comms` in `MODULE_TOGGLES`. | Code: `admin` covers `fees, comms, merch, crm`; there are also `core` and `fantasy` toggles; `org_entitled_modules` now requires a live Core before any add-on works. | Modular entitlements, L12540-12564 | keep the "no tiers" rule; treat the module list as changed.
- **[FLAG-OPS-6]** Archive says the redirect worker is "ready but not yet deployed". | Files exist; deployment state is not visible from the repo. | Public Domain, L12393-12402 | verify with a `curl -I https://betterstats.cricket/` before relying on either state.
- **[FLAG-OPS-7]** Pricing section says `BUNDLE_DISCOUNT` in `pricing.js` is the model. | `pricing.js` still holds the schedule, but checkout reads a super-admin-editable one (`platform_settings.get_bundle_discount_schedule`, seeded from `billing_pricing.py`, a hand-kept port). Site and checkout can drift. `FANTASY` ($49) is outside the bundle. | Public Marketing Pricing, L12511-12539 | verify; the Stripe/billing guide is the authority for checkout.
- **[FLAG-OPS-8]** Contact section names `_resolve_onboarding_club (twenty_sync)` and "the Twenty push". | Twenty is retired: the function now lives in `services/engagement.py`. The `org_id` priority rule still holds. | Marketing Contact form, L12430-12510 | keep the rule, ignore Twenty references.

## sales-crm-and-commissions

See `guides/sales-crm-and-commissions.md`.

- **[FLAG-SALES-1]** Rate stamped on the deal at win (`crm_deals.commission_rate_percent`, migration 277, `_stamp_commission_rate` in move_stage/close_deal/create_deal) | Superseded by 278 (earned reads `billing_invoices`); grep finds no `_stamp_commission_rate` in `backend/app/services/` now | Sales Commissions section, L3894-4428 | verify dead, then retire.
- **[FLAG-SALES-2]** "Earned is filed by the deal's `closed_at`" | After 278 earned is per payment | same section | verify period filing in `sales_commissions.py`.
- **[FLAG-SALES-3]** Add-on win calls `_push_club_to_twenty(...)` | Replaced by `_sync_club_to_crm` (`billing.py:237`) | same section | retire the name, rule 29 is current.
- **[FLAG-SALES-4]** Whole Twenty sync fixes section (`refresh_twenty_engagement`, `/refresh-twenty-engagement`, `/refresh-twenty-leads-tasks`, `twenty_client.py`, `push_onboarding_enquiry`, `push_club_and_contacts`, `push_org_company`, `upsert_lead_for_club`, `force_hot`) | Retired v9.71.0; grep of `backend/app` finds none except a comment at `engagement.py:780`; `/refresh-engagement` replaces the first | Marketing Club Directory section, L13889-14029 | retire; lessons kept in rule 9 and Traps.
- **[FLAG-SALES-5]** Enquiry and trial hooks that pushed Hot 100 and a Lead (`club_directory.set_sales_state`, `create_module_request`, `start_module_trial`, `approve_module_request`) | The push and Lead creation are gone; only the 30-day hold in `_engagement()` survives; whether the hooks still trigger a rescore is unverified | same section | verify.
- **[FLAG-SALES-6]** Twenty-import meta keys (`twenty_kind`, `twenty_note_id`) | Still live in `sales_workspace.py` for historical rows | quiet-week and performance sections | keep.
- **[FLAG-SALES-7]** Migration numbers and the "renumbered 293 -> 295" note | Numbers drift | Twenty retired section | keep only the lesson: check `origin/main` when you merge.
- **[FLAG-SALES-8]** "A query to inspect them is in the session notes below" | No such query in the archive | Empty $0 wins section | retire the pointer.

## scorecards-fixtures-and-lineups

See `guides/scorecards-fixtures-and-lineups.md`.

- **[FLAG-SCORE-1]** Archive: `caught_behind` is synced-only and the fix was NULL with "not a new column" | Code now reads `bi.caught_behind` unconditionally with a comment that it is a real column on both tables (migration 291); the manual dict at `routers/games.py:550` sets `None` | "A two-day match's other two innings..." L10379-10459 | verify migration 291, retire the "no new column" wording, keep the shared-builder lesson
- **[FLAG-SCORE-2]** v8.79.0: badges are initials because "we hold no team logos" | Superseded by v8.79.1 (crests) | "Match scorecard page redesigned..." L14402-14593 | keep rule 23
- **[FLAG-SCORE-3]** v8.79.2: header is home-left/away-right ALWAYS | `MatchScorecard.jsx` now has `sidesSwapped(nameA, nameB, homeTeam, awayTeam)` (~line 294) and other CLAUDE.md notes (v9.98.6, not in this archive) say the header judges both sides against both teams | same section, v8.79.2 | verify against the file before relying on rule 22 for the header
- **[FLAG-SCORE-4]** v8.60.0: our innings `runs` prefer GR's total | Wrong, corrected in v8.60.1 (double-counted extras); rule 5 is current | "Fill-in players on the game scorecard" L14030-14128 | retire the v8.60.0 wording
- **[FLAG-SCORE-5]** v8.60.x "Not done": no partnership name column, fielding skipped for fill-ins | Superseded by v8.61.0 (migration 147) | L14129-14217 | retire; keep only the sync-still-gated item
- **[FLAG-SCORE-6]** v8.78.0 org-crash fix made DB overlap the primary "ours" signal | Reversed in v8.79.3; code at `routers/games.py:1053-1060` matches the reversal | L14218-14401 and L14402-14593 | keep rule 4
- **[FLAG-SCORE-7]** v8.78.0 first follow-up presents the TTL cache fix | The TTL and `_scorecard_looks_incomplete` (`grassroots_scores_client.py:49, 293`) exist but were not the cause of the "16/0" symptom | L14218-14401 | keep rule 8, do not cite as that fix
- **[FLAG-SCORE-8]** Lineups section leans on a "GR path can't see the toss" note from another archive | `wonToss`/`battedFirst` exist on `matchSummary.teams` | L13038-13200 | verify before repeating the no-toss claim
- **[FLAG-SCORE-9]** Yearbook auto-generation text sits inside the v8.79.3 scorecard section | Misfiled; code still matches (`club_admin.py:5084`) | L14402-14593 | move to the yearbooks guide, verify count=3 there

## stats-figures-records-and-filters

See `guides/stats-figures-records-and-filters.md`.

- **[FLAG-STATS-1]** "Milestones are deliberately never filtered" (v9.64.0) | reversed by v9.93.0 (`profile_totals` follows the profile default); Milestones reach-note copy may still say never filtered | Which lens a panel (L16385-16615), A milestone is measured (L454-537) | verify frontend copy, align
- **[FLAG-STATS-2]** Gap heuristic "skipped entirely under an active scope" (v9.64.0) | replaced by per-season gating in v9.64.1 (`seasons_left_to_scorecards` in `aggregations.py`) | Which lens a panel (L16385-16615) | retire blanket wording
- **[FLAG-STATS-3]** Family targets "left alone" (v9.59.0) | settled v9.65.1 | A rate is only as good (L3203-3427) | retire
- **[FLAG-STATS-4]** `if grade_id or grade_name: scope = None` (228) | narrowed by 259 to `formats_only()` (exists in `grade_scope.py`) | Junior stats split (L8226-8315) | keep rule 21
- **[FLAG-STATS-5]** "migration 282 applied... pre-283 schema" | 282 is rate qualification, 283 competitions; typo | Stats by competition (L15772-16384) | keep 283
- **[FLAG-STATS-6]** "Not yet run" for `records_pushdown_test.sql`, "only measures, nothing cached" | later sub-section reports the run and the shipped clause (`pss_club_clause`, `SET LOCAL jit = off` confirmed in `routers/records.py`); caching still open | Stats by competition (L15772-16384) | retire "not yet run"
- **[FLAG-STATS-7]** "Grid carries no scope", "teammates/captain unscoped" | closed in v9.64.0 and v9.64.1 | Stats by competition; Which lens a panel | retire
- **[FLAG-STATS-8]** `aggregations.py:511/553` line refs, "five sites" | stale | A washout is not a match played (L6569-6643) | verify with grep
- **[FLAG-STATS-9]** Timings, milestone dry-run counts, player-count splits | one-off production evidence, Sep 2026 | several | history only
- **[FLAG-STATS-10]** Gender filter kept on Leaderboard/Records with a casing bug | unchecked | A grade is several things (L7001-7212) | verify, fix or retire

## Cross-cutting flags found by the split's author

- **[FLAG-CORE-1]** The old `Branch` section says the active branch is `claude/fix-historical-game-data-QEN3b` and to push it "AND to main via MCP after each change". | Conflicts with the per-session branch rules the harness gives each session (develop on the named branch, never push elsewhere without permission). The named branch is months old. | `platform-ops-and-site` archive, `Branch` (L12696-12700); also `FLAG-OPS-*` | Not acted on. The slim `CLAUDE.md` says to follow the session's branch. Retire the old note if the owner agrees.
- **[FLAG-CORE-2]** Code and docs point at old section titles that never existed as headings: "container-safety rules" (`settings.py:135`, `docs/backup-system.md:96`), "SES notes" (`docs/bettercomms-architecture.md:110`), "Yearbook auto-generate + auto-publish" (`docs/self-serve-trial-onboarding-plan.md:526`, which is really an untitled paragraph at original L14558 inside the SC3 scorecard redesign section), and "Club crests, live from Grassroots" (`grassroots_scores_client.py:393`, actual title "Club crests + match-summary header restored (v8.79.1)"). | Someone once wrote the title from memory or the heading was renamed or removed. | See the code-comment table in `COVERAGE.md`. | Fix the comments in a later code change; the knowledge each one wanted is in the guide named beside it.
- **[FLAG-CORE-3]** The teaser section is headed "migration 314" but its body says "NUMBERED 312 after merging `origin/main`". | `backend/alembic/versions` has 312 admin_broadcasts, 313 social_templates, 314 club_teaser_snapshots, so 314 is right and the body text is stale (the renumber happened after it was written). | `club-directory-onboarding-and-admin-shell` archive, teaser snapshot section (L538-640). | Trust 314.
- **[FLAG-CORE-4]** The old file was not organised by topic or date: a `v9.99.0` entry is dated "Oct 2026" and `v9-100-0.js` carries `sortKey` `2026-10-07T09:00:00Z` while `date` is 2026-09-30 (today is 2026-09-30). | A future sortKey makes that release sort as newest before it exists. | the newest sections at the top of the old file (original L3-189); `frontend/src/data/changelog/v9-100-0.js`. | Owner to confirm the sortKey is intentional (a scheduled release) or correct it.
- **[FLAG-CORE-5]** Sections are misfiled inside other sections. The Club Directory "Rediscover" notes (v9.71.4 and v9.71.5) sit inside the StreamYard webinar section, so they were archived with the marketing topic. | They belong with the Club Directory. | `marketing-funnel-ads-and-webinar` archive (L1827-2582); rules captured in `guides/marketing-funnel-ads-and-webinar.md` rules 52 to 54 and cross-referenced from `guides/club-directory-onboarding-and-admin-shell.md`. | Keep the cross-reference.
- **[FLAG-CORE-6]** The old `Version Numbers` note said changelog files are named `v-X-Y-Z.js`. | The real files are named like `v9-99-2.js`. | `platform-ops-and-site` archive, `Version Numbers` (L12565-12573). | Corrected in the slim `CLAUDE.md`.
- **[FLAG-CORE-7]** Several guide agents reported "no verification suites found" for suites the archive cites. | Two of those claims were wrong. The vote suites exist in `backend/scripts/` (not `backend/verification/`), and several selection and nets suites exist in `frontend/verification/`. The votes and selection guides were corrected after a whole-repo search. The flags in other guides that say a suite or file is missing were spot-checked only for votes, selection, marketing and data-sources. | Guides `betterselect-votes-and-medals` (FLAG-VOTES-2, RESOLVED), `betterselect-selection-and-nets` (FLAG-BSN-1), `marketing-funnel-ads-and-webinar`, `clubhouse-committee-and-plans`. | Before trusting any "suite missing" flag, `find . -name 'verify_*'` across the repo.
- **[FLAG-CORE-8]** The guides total about 384 KB, roughly 31% of the original, well above the 10% target set for them. | Each guide was capped at 20 KB and the rules are dense; the stats and imports guides were compressed hard and say so. | All guides. | A guide is loaded on demand, about 5k tokens each, so this is acceptable. If a rule looks thin, grep the matching archive.
- **[FLAG-CORE-9]** A handful of en and em dashes remain in some guides (quoted identifiers and copied headings), against the writing-voice rule. | Verbatim quotes are exempt by design. | Guides `betteriq`, `data-sources-and-sync`, `betterselect-votes-and-medals`, `billing-stripe-and-invoicing`. | Optional tidy.
