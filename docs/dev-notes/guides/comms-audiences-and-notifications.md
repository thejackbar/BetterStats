# Guide: BetterComms audiences, lists, segments, templates and club notifications

**Read this before** (triggers):
- Editing `backend/app/services/comms_segments.py`, `comms_contacts.py`, `club_trial_window.py`, `admin_contact_list.py`, or `backend/app/routers/comms.py` (`reconcile_contacts_from_directory`, `audience_figures`).
- Adding a segment field or rule, a merge variable (`{{trial_days_left}}`, `{{club}}`) or a Lists/Segments facet.
- Touching `frontend/src/pages/admin/clubhouse/crudShell.jsx`, `segmentEngine.jsx`, `CommsLists.jsx`, `CommsCampaigns`/`CommsCompose`/`CommsTemplates`, `components/admin/EmailEditorTabs.jsx`.
- Anything in club notifications: `notification_events.py`, `notification_scan.py`, `notifications.py`, `milestone_scan.py`, `NotificationBell`, `NotificationModal`, `/club-admin/notifications/*`.
- Symptoms: `a[r.key] is not iterable`; a segment matching everyone; Comms reaching far fewer people than the Directory; a certificate warning raised twice or never; a bell that opens nothing; a club admin missing from the internal list.
- Shipping a release (changelog file format).

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/comms-audiences-and-notifications.md`. Grep hints: `facetOptionsFrom`, `decides what it is told`, `Certificate stages`, `One CRUD shape`, `Design / Preview`, `Notification Centre`, `Naming a club`, `nobody at the club ever ran`, `How many clubs an audience`, `one internal list`, `trial, as an audience`, `no sync step`.

**Related guides**: none confirmed (check `docs/dev-notes/guides/` for CRM, accounts/onboarding and verification-harness guides).

## Standing rules

**Audience safety (segments and lists)**

1. Club scope reads the club's own people. Directory scope (BetterCricket outreach) is super-admin only. Never expose Directory fields, context bar or copy in a club build (`CLUB_FIELD_DEFS` and `DIRECTORY_FIELD_DEFS` are imported by separate screens only).
2. The engine enforces it, not just the screen: `comms_segments.directory_rules_allowed(club)` reads `org_is_outreach` (same as `/auth/me` `is_marketing_org`). A directory rule in a club context EMPTIES the audience (`where(false())`), never dropped (dropping widens to the whole list). Write paths refuse with 422 too.
3. Every audience rule fails closed. An unrecognised vocabulary value or wrong case (`WON`) used to drop the condition and widen to everyone. `_vocab` / `_vocab_list` fold case for `deal_won`, `primary_admin`, `trial_status`.
4. Rules are ANDed, no NOT. Exclusion needs a multi-select (`input: 'multi'`) whose options PARTITION the audience, so exclude X means pick the others.
5. "Named club" / "named contact" (`is any of` / `is none of`) NARROW as ordinary ANDed rules, not union overrides (a union include could email someone another rule excluded). Do not join `MarketingClub` for them: `marketing_club_id NOT IN (...)` is NULL for a contact with no directory club and would drop hand-added contacts, so `_pick_clause`'s `nullable` argument ORs `IS NULL` back in on excludes. An empty selection drops the rule; junk ids drop individually.
6. Picking clubs/contacts: server search `GET /segments/entities?kind=club|contact&q=&ids=` (Directory never shipped to the browser). `ids` is answered whatever `q` is. Scoped to the acting org, same scope guard as the engine. Drop a response if the box has moved on.
7. Primary-admin state has three values: `assigned`, `unassigned`, `not_onboarded`. `unassigned` = nobody is PRIMARY (a non-primary `club_admin` still reads unassigned). `not_onboarded` = prospect with no org (`marketing_clubs.existing_org_id` is `ON DELETE SET NULL`). Predicate mirrors `trial_engagement.org_has_primary_admin` (`role='club_admin'` AND `is_primary_admin`). A yes/no would fold prospects in with test clubs.
8. Deal won-ness comes from the STAGE (`crm_stages.is_won`, boolean), never `crm_deals.status` or stage name. Scope through the stage's pipeline, never `crm_deals.scope`. Archived deals are off the rule.
9. `comms_segments.sendable_where` is the one definition of "can be sent to". An opt-out (unsubscribed, bounced, complained, globally suppressed) is never overridden by any sync or export, and a suppressed address is never resurrected.
10. Building a list from a Directory selection (`POST /club-admin/comms/lists/from-directory`, `source='auto'`, `origin='Clubhouse Directory'`): the browser sends person KEYS, never emails. The server re-reads and goes through `_upsert_contact`.

**Comms reads the live Directory (no sync step)**

11. No "sync contacts" concept. `comms.reconcile_contacts_from_directory(db, club)` runs on the read path (`GET /contacts`, `_resolve_audience`, the three segment endpoints). It writes only MISSING addresses (safe on a GET), keeps the old contact when an email changes (may carry suppression/send history), never deletes, skips the outreach org.
12. Do not filter who becomes a contact by `Player.status` (targeting is a list/segment decision). Do not reintroduce a sync button. Any new Comms surface listing people calls `reconcile_contacts_from_directory` first. Email filling is the Directory's job (Has email / No email filter); do not add an overlapping member-kind filter to Comms.

**Audience figures**

13. `/segments/resolve` caps its contact list at 5000 but its count is exact. `reachable`, `other_route` and the distinct-club count come from `routers/comms.py::audience_figures` over the WHOLE audience, never from the capped slice. The browser falls back to `clubCount` in `crudShell.jsx` only for an older server.
14. Club count = distinct linked directory clubs among REACHABLE contacts. It self-gates (a club's own members have no `marketing_club_id`, so 0 and not drawn). A blank address is matched but not reachable. Python `audience_figures` and JS `clubCount` are one rule in two languages, keep them in step.

**Trial as audience and merge variable**

15. Trial fields are Directory scope only (`DIR_TRIAL_FIELDS`); the club field set must carry none. `services/club_trial_window.py` is the ONE definition: segment SQL and merge vars read the same subquery and day maths, so the printed figure equals the segment boundary (in at `<= n`, out at `<= n-1`).
16. Expired trial = row stays `status='trial'` with a past `trial_ends_at` (`module_subscriptions.sweep_expired_trials`). Window = `MAX(trial_ends_at)` across modules. `ends_at` cannot answer "has a trial" (NULL for none and for open-ended), so the subquery carries `has_trial`. An open-ended trial reads as running, never expired, no day count.
17. Days-since floors on its own side, never the negation of days-left (finished 3.2 days ago is 3, negation gives 4).
18. A figure that does not apply renders BLANK, never `0`; every directory club (never-onboarded included) gets a lookup entry so no literal `{{trial_days_left}}` goes out. Trial figures are NOT in `EDITABLE_MERGE_KEYS`. `_apply_overrides` holds that rule; `_contact_vars` is the one builder used by preview, test send and real send.

**Internal "club admins" list**

19. "Club Admin or Primary" is one query: `club_memberships.role='club_admin'` plus the `is_primary_admin` flag. Sync covers every `club_admin`, or the list drifts.
20. `services/admin_contact_list.py::sync` is the whole job; hooks and the backfill run the same code at different scope. UPSERT ONLY (losing the role removes nobody). Archived clubs' admins not added. An existing list of that name is adopted (unique org + name; `source`/`origin` untouched). Contact is linked to the club's directory row so `{{club}}`, `{{association}}`, `{{trial_days_left}}` resolve (no row means NULL). An admin with no email is reported, not dropped.
21. It runs on its OWN session, AFTER the caller's commit, and never raises (`run_sync`). Use `queue_sync` after a commit, else `background_tasks.add_task(run_sync, ...)`. Fired mid-transaction it finds no membership and silently does nothing.
22. `services/comms_contacts.py` is the ONE upsert copy (`routers/comms.py` delegates). It FILLS, never clobbers.
23. Add New User takes optional email and mobile, validated as `patch_user` does (format only, never uniqueness: `users.email` stopped being DB-unique at migration 145). Validate before `setSaving(true)`. The AFL silo is untouched (own database, no outreach org).

**Comms record screens and editor**

24. Build Comms-style screens from `crudShell.jsx` (`CrudPanes`, `RecordListPane`, `DetailPane`, `RecordTitleRow`, `CountBar`, `SaveRow`, `reachability`), not a fifth layout.
25. Emails is one screen on two URLs (`/admin/comms`, `/admin/comms/:id`, both `CommsCampaigns`; `CommsCompose` exports `EmailDetail`). Keep URLs stable. Composer is `lazy()`. Deleting a SENT email lives on the email. Subject is the title row (`TextInput` forwards its ref).
26. A selection effect may only LOAD a draft, never clear one (clearing wipes a fresh "New list"/"New template"). `EmailEditorTabs` seeds its design iframe once, so bump `editorKey` when HTML is replaced wholesale.
27. Facet shapes are DERIVED from `FACETS` (`emptyFilters`, `facetOptionsFrom`, matcher), never a second hand-written list.
28. Design mode edits the REAL DOM (`designMode = 'on'`, `execCommand`, `serializeIframeDocument`), not a schema (rich-text libraries rewrite table email markup). Fragment vs full doc is auto-detected (`isFullHtmlDoc` in `lib/htmlEmailFormat.js`, mirrors backend `_is_full_doc`); a fragment is wrapped only for the editing surface (`wrapFragmentForEditing`) and only its inner content is read back, so the backend club shell and mandatory footer still apply. Tidying (`tidyHtml`, js-beautify) is client-side only.
29. `ref.flush()` on `EmailEditorTabs` is mandatory before every Save, Test and Send; use its return value, not `html`/`body` state (not landed yet). A 400ms live sync keeps Send enablement and unknown-`{{variable}}` warnings current.

**Club notifications (migration 288, v9.69.0, v9.89.0)**

30. Catalogue is CODE, choices are DATA: a new event needs an `EventType` in `notification_events.EVENT_TYPES` AND a source in `notification_scan.SOURCES` (suite asserts they match). A club with no rows behaves as the registry declares, so defaults change with no backfill.
31. Notice period is per event (`EventType.config_fields`), server-side bounds CLAMP. `clean_config` direction is load-bearing: SAVE passes the club's current config as base, READ passes nothing (falls to registry default). Backwards resets a club's setting on next save. An already-lapsed certificate is raised whatever the notice period.
32. Dedupe key names the FACT, never the run. Certificate key carries its expiry DATE (renewal is a new fact). Sources re-report everything; the unique index on `(organisation_id, dedupe_key)` decides what is new (read-then-write would race a manual scan against the nightly). Sole exception: low stock puts the ISO week in the key.
33. Certificate stages: notice (ORIGINAL unsuffixed key), `:final` (`final_days`, 0 = off), `:lapsed` (severity `urgent` via `emit(severity=...)`). Only the CURRENT stage raised; a pre-stage notice is read by payload `days_remaining`. Excluded: superseded, archived-member, retired-type and long-lapsed (`lapsed_days`) certificates.
34. `notifications.channel_allowed` is the whole subscription decision (kill switch, channel switch, event switch, per-event channel, person opt-out, plus module gate and recipient capability). Each fails closed alone; one copy only. An opt-out silences and never switches on; `event_key = '*'` (`ALL_EVENTS`) is the whole-club floor. Capability filters who is TOLD, never who may configure their own inbox.
35. Recipients: `club_admin` AND `club_member` (allowlist members such as the volunteer coordinator with `MANAGE_QUALIFICATIONS`). Do NOT reuse `admin_contact_list.admin_rows`. A `super_admin` or `sales` membership is never a recipient.
36. One digest per recipient. Mark sent only when the provider accepts; record a refusal on the row and retry. Console provider is NOT a send (deliveries stay pending). First run capped (`MAX_PER_EVENT` = 40, `LOOKBACK_DAYS` = 21 in `notification_scan.py`). `sync_completed` defaults to the bell, not the inbox. A channel is TEXT (`notification_events.CHANNELS`); absent from `default_channels` means OFF.
37. Bell and modal were two separate `role === 'super_admin'` gates in `AdminLayout`; both lifted (endpoints are club-scoped via `get_current_club`). Lifting one leaves a bell that opens nothing. Login auto-open stays staff-only.
38. `services/session_safety.rollback_keeping` is the ONE "rollback but keep instances readable". A bare `rollback()` expires loaded instances; the next attribute read raises MissingGreenlet far from the cause.
39. Grade milestones (`milestone_scan.grade_milestones`): name folded through active `grade_merge_logs`, active players only, ids bound as `uuid[]` (never a subquery). One-grade players skipped, judged across ALL stats.
40. `POST .../settings/test-email`: self-only `[Test]` digest, touches no delivery, 5 per 10 minutes.

**Old bell (v7.7.3)**

41. `users.last_notification_seen_at`, `last_seen_app_version` (migration 029); `GET /club-admin/notifications/count` (60s poll), `/summary`, `POST /seen`; window 14 days.
42. Changelog: one file per release in `frontend/src/data/changelog/`, default-exporting `{ version, date, sortKey, title, items[] }`. `SITE_VERSION` derives from `CHANGELOG[0]`; never hand-edit `version.js`. Bell adds `newChangelogCount` client-side; login auto-open fires if `unseen_count > 0` or an entry is newer than `last_seen_version`.

## Traps and failure signatures

- `a[r.key] is not iterable`: `facetOptionsFrom` spread `opts[f.key]` for every `FACETS` key but `opts` was a hardcoded literal predating `role`. Throws for empty and `null` lists; `Cannot read properties of undefined (reading 'add')` once a contact has a role. Not the rows. Fix: rule 27. 
- Segment matches everyone: a dropped condition (unknown value, wrong case, directory rule in club scope; rules 2, 3). The join-less fields (`exported`, `emailed`, `opened`, `clicked`, `enquired`) once evaluated on a club's own contacts.
- Exclude drops hand-added contacts (rule 5). Primary-admin filter sweeps prospects (rule 7).
- Comms reaches 128 of 1,578: `sync_from_club` filtered `Player.status == "active"` (rules 11, 12). Club count stops at 5000 (rule 13).
- "0 days left", literal `{{trial_days_left}}`, expired off by one, open-ended trial dropped: rules 16 to 18.
- Club admin never on the internal list: hook before commit, or no email at create (rules 21, 23). Dry-run backfill said "0 to add" because it queried contacts that do not exist yet; it must project rows it would create.
- Bell opens nothing (37). Certificate never re-announced (32, 33). Empty capability check for a volunteer coordinator (35). Notice period reset on save (31). MissingGreenlet (38). Stale HTML sent from Design mode (29). Fresh draft wiped (26).
- Harness: a control run that crashes is not one (guard reads and imports so absence is REPORTED). A check comparing two widened sets cannot fail. Locators can match the sidebar nav, not the open panel. CSS-`uppercase` text reads transformed. `uncheck({ force: true })` throws. Lifespan-only tables (`member_membership_types`, `player_achievements`) are invisible to `create_all`.

## How to verify a change here

- `backend/verification/verify_notifications.py` (control must REPORT services absent; gate, opt-out and retired-threshold neutered fails those three) and `frontend/verification/verify_notifications_browser.mjs` (exact params on the wire: a toggle sends only its own field, personal opt-out goes to preferences never the rule endpoint, Check now emails nobody, bell opens).
- `backend/verification/verify_primary_admin_segment.py` (control: every naming rule matches the WHOLE audience; case folding reverted makes `"Won"` match all clubs), `verify_club_trial_segments.py` (SQL and Python day counts agree; controls: engine reverted, scope guard removed so `emailed` returns everyone), `verify_audience_clubs.py` (6001 contacts across 6000 clubs proves the cap does not apply; real JS `clubCount` run against Python), `verify_admin_contact_list.py` (dry run equals apply; controls: hooks reverted, create form reverted).
- `frontend/verification/verify_comms_facets.mjs`: shipped functions lifted from the file; control shows `opts[f.key] is not iterable`.

## Operator commands and scripts

- `python -m app.scripts.sync_admin_contact_list [<org-id-or-slug>] [--apply]`: backfill club admins onto the internal list. Dry run by default; no arg means whole platform.

## Open follow-ups

- Nothing asserts a key added to `FACETS`, `MODE_FILTERS` or the engagement filter reaches every consumer (only `FACETS` covered).
- Nothing prunes old notifications (retention is a person's decision). No per-event digest frequency, SMS or push. `member_reminders` still emails the MEMBER about their own lapsing qualification (different audience). Reconcile does not refresh names on existing contacts (deliberate).
- `crm.trial_days_remaining_by_club` still negates its signed figure for the CRM expired badge (off-by-one from rule 17).

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-COMMS-1] Admin-contact rule cites "the Twenty pushes" for archived-club exclusion | Twenty CRM is retired (no `twenty` in `admin_contact_list.py`) | "Every club admin, on one internal list" (L16805-16911) | keep the rule, ignore the Twenty reference.
- [FLAG-COMMS-2] Old Notification Centre says "no dedicated notifications table", three endpoints | `routers/notifications.py` also has `/settings`, `/settings/events/{event_key}`, `/settings/preferences/{event_key}`, `/feed`, `/feed/read` (grep) from the 9.69.0 system | "Notification Centre (v7.7.3)" (L15738-15771) vs "A club decides what it is told about" (L2701-2886) | verify what the bell reads today before editing either.
- [FLAG-COMMS-3] "AFL silo untouched" | later work elsewhere mounts cricket routers on football | "A club decides..." (L2701-2886), "Every club admin..." (L16805-16911) | verify before assuming football is covered.
- [FLAG-COMMS-4] `FACETS` gained `role` in "migration 295's commit"; `PROJECT_RULES.md` cited as scope authority | migration numbers were renumbered often; the file was not opened | "A FACET LISTED IN THE KIT..." (L1577-1630), "A club's trial..." (L16980-17074) | verify both before relying on them.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| A FACET LISTED IN THE KIT AND MISSING FROM ONE FUNCTION (v9.73.1) L1577-1630 | rules extracted | Rule 27, Traps 1, harness, Open 1, Flag 4 |
| A club decides what it is told about (migration 288, v9.69.0) L2701-2886 | rules extracted | Rules 30 to 38, 40, Traps, Open 2, Flags 2, 3 |
| &nbsp;&nbsp;Certificate stages, grade milestones and a test email (v9.89.0) | rules extracted | Rules 33, 36, 38 to 40 |
| One CRUD shape for Emails, Lists, Segments and Templates (v9.17.0) L8316-8369 | rules extracted | Rules 24 to 26 |
| BetterComms — HTML / Design / Preview editor (Jul 2026) L13844-13888 | rules extracted | Rules 28, 29 |
| Notification Centre (v7.7.3) L15738-15771 | rules extracted (partly superseded by the 9.69.0 section); its open follow-ups (`deep_sync_player`, alias-season redirects) are outside comms and stay in the archive | Rules 41, 42, Flag 2 |
| Naming a club or a contact outright (v9.58.3) L16616-16672 | rules extracted | Rules 5, 6 |
| Targeting the clubs nobody at the club ever ran (v9.58.0) L16673-16755 | rules extracted | Rules 3, 4, 7, 8 |
| &nbsp;&nbsp;Won, and anything but Won (v9.58.1) | rules extracted | Rule 8 |
| &nbsp;&nbsp;Vocabulary values matched case-insensitively (v9.58.2) | rules extracted | Rule 3 |
| How many clubs an audience reaches (v9.57.0) L16756-16804 | rules extracted | Rules 13, 14 |
| Every club admin, on one internal list (v9.56.0) L16805-16911 | rules extracted | Rules 19 to 22, Operator commands, Flag 1 |
| &nbsp;&nbsp;Add New User takes an email and mobile (v9.56.1) | rules extracted | Rule 23 |
| A club's trial, as an audience and as a number in the email (v9.55.0) L16980-17074 | rules extracted | Rules 1, 2, 15 to 18, Open 3 |
| Comms has no sync step: it reads the live Directory (v9.12.0) L17075-17125 | rules extracted | Rules 10 to 12 |
