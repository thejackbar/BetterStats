# Archive: club-directory-onboarding-and-admin-shell

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Club Directory crawl and teasers, new club onboarding, setup wizard, admin navigation, draft pages, KlubPro, dashboard messages.
Read the distilled rules first: `docs/dev-notes/guides/club-directory-onboarding-and-admin-shell.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L3-31 -->
## The teaser pull was handing CA the wrong kind of id (Sep 2026)

The first live `pull_club_teasers all --sample 20 --apply` read 20 of 20 clubs
as `empty`, one call each, every call a `204 No Content` on
`fixturesladders/organisations/{guid}/seasons`.

- **`marketing_clubs.grassroots_guid` IS PLAYHQ'S SEARCH GUID (the `playHQId`
  namespace), NOT THE CA `organisationGuid`.** The seasons and participants APIs
  only answer to the second and return 204 for the first, whatever the paging
  (offset 0, 1 and none were all tried). The CA search returns both ids side by
  side: Traralgon West is `organisationGuid 0dce4bf0-...` and `playHQId
  fdfccdd0-...`, and the directory held the second. This is the namespace split
  `playhq_client.search_organisations` already warns about.
- **`LiveAPI.resolve_org` FINDS THE CLUB BY NAME AND CONFIRMS IT ON THE ID.** One
  extra call per club. A name hit whose `playHQId` (or `organisationGuid`) is not
  the directory's own guid is refused, because two clubs can share a name. A club
  CA's search cannot place is `empty` after that one call and makes no data call.
  `pull_club` only resolves when the API has `resolve_org`, so scripted APIs in
  the suite are unchanged.
- **The snapshot row still keys on the directory guid** (`org_guid`); only the
  calls to CA use the resolved one.
- **Live check** through the shipped `LiveAPI`: Traralgon West 35 calls / 77
  matches, Kaniva 15 / 16, Applecross 78 / 132, a made-up club empty after 1.
  Expect ~15-80 calls a club now, not the ~25 assumed, and re-read `api_calls`
  off a fresh `--sample` before scaling.
- **Verified** (`verify_club_teaser.py`, 92 checks, real Postgres) **with a control
  run**: reverted, the resolved-guid, one-call and unplaceable-club checks fail
  and the run then stops on the missing `resolve_org`.

<!-- END original CLAUDE.md L3-31 -->
<!-- BEGIN original CLAUDE.md L151-189 -->
## BetterCricket's messages on the club admin dashboard (migration 312, v9.99.0, Oct 2026)

Asked for: a super admin sends a one-line message visible only on the Club
Admin Dashboard, to all clubs, chosen clubs or chosen users, with a choice of
how long it lasts (a time period, until cleared, until seen once, and so on),
and it has to work on every device.

- **`admin_broadcasts` + `admin_broadcast_receipts`**, DDL once in
  `services/admin_broadcast_ddl.py` (alembic 312 and the lifespan both run it).
  Router `routers/admin_broadcasts.py`. Screen `SuperBroadcasts.jsx` at
  `/admin/super/broadcasts` (Better HQ > Comms > Dashboard Messages); banner
  `components/admin/AdminBroadcastBanner.jsx`, mounted ABOVE the Welcome
  heading in `AdminDashboard.jsx` and nowhere else.
- **Audience** is `all` | `clubs` (org_ids) | `users` (user_ids), and for the
  first two `audience_roles` narrows it: `all_admins` (club_admin AND
  club_member, the admin-app users), `club_admins`, `primary`. A named-user list
  is never narrowed by role. Archived clubs are never in the reach count, and
  the composer refuses an archived club or a user who is not a club admin.
- **Persistence** is `until_cleared` (no close button) | `dismissible` |
  `view_once_user` | `view_once_club`, and `expires_at` stops ANY of them. A
  super admin can always clear, restore, reset views or delete.
- **VIEW-ONCE RUNS ON A RECEIPT THE BROWSER POSTS AFTER DRAWING**, not on the
  GET. The GET computes what shows from receipts written on an EARLIER view, so
  the view that shows it is the one view. `/seen` only records ids the user can
  see right now, so a browser cannot plant a receipt.
- **STAFF SEE A PREVIEW AND WRITE NOTHING.** A super admin or sales user acting
  as a club gets every live message aimed at it (including a named-user one for
  someone at that club), marked `preview`, and `/seen` and `/dismiss` store
  nothing — a staff glance must not use up a club's view-once message.
- **Verified against a real Postgres** (`verify_admin_broadcasts.py`, 56 checks
  through the shipped route bodies) **with a control run** (view-once and the
  primary filter neutered: 3 fail), and **in Chromium**
  (`verify_admin_broadcasts_browser.mjs`, 80: above the heading at 1440/768/390,
  the most urgent first, the close target at least 36px, a long URL wrapping,
  the seen and dismiss calls, the preview writing nothing, and the composer's
  payload and reach) **with a control run** (banner unmounted: 5 fail).
- **Noticed, not fixed**: the dashboard's module tiles already overflow 7px at
  768px (an ADD-ON/SOON label), with or without a message.

<!-- END original CLAUDE.md L151-189 -->
<!-- BEGIN original CLAUDE.md L538-640 -->
## A teaser snapshot of a club that has not registered (migration 314, Sep 2026)

Asked for as the data half of a marketing campaign: show a prospect their own
club's dashboard (email image, landing page, the Meta click-through) before
they have a trial. Pull and re-pull only; the preview page, the email image
renderer and the match/lineup layer are NOT built yet.

- **IT IS NOT THE SYNC.** The onboarding sync pulls every scorecard a club ever
  played (thousands of calls). A teaser needs one season, and CA already serves
  it pre-computed: seasons (1), batting/bowling/fielding for ONE season, teams
  (1) and one ladder per senior grade. ~15-30 calls a club. Nothing writes
  `organisations` / `players` / `games`: an unclaimed club must not reach the
  public site, the sync scheduler or the duplicate checks. The snapshot is one
  JSON row per Club Directory club (`club_teaser_snapshots`,
  `services/club_teaser.py`); a claim runs the normal sync and leaves it as
  history.
- **JUNIORS ARE DECIDED PER GRADE.** The season aggregate has no grade on a row,
  so a club with junior grades has stats fetched grade by grade for the SENIOR
  grades only and merged (`merge_rows`); a junior-only club is `junior_only` and
  gets no snapshot. A marketing page must not name children, and CA redacts
  many of their names (`********`, also dropped).
- **THE NEWEST SEASON OFTEN HAS NO STATS YET** (September). Seasons are probed
  newest-first, at most `MAX_SEASON_PROBES`, and the first with batting rows is
  used; `season_pending` marks that a newer one is on the way, which puts the
  club on the weekly cadence so the new season is noticed within a week.
- **OUR ROW IN A LADDER IS FOUND BY `owningOrganisation.id`, not by team name.**
  Reuses `iq._ladder_rows`.
- **`version` MOVES ONLY WHEN THE CONTENT DOES** (`data_hash`). The email image
  is rendered by Chromium and stored on the HDD (`/mnt/media`, outside the
  backup, like the videos), so a weekly re-pull that found nothing must not
  invalidate it. `image_version` is reserved for that renderer.
- **THE TOKEN IS MADE ONCE AND NEVER ROTATED BY A REFRESH.** A link already sent
  in an email has to keep working.
- **WHEN TO LOOK AGAIN IS DECIDED WHEN THE PULL IS WRITTEN** (`next_pull_at`,
  indexed): in play 7 days, off season 45, empty 14, junior-only 90, errors
  1/3/7/14/30 then flat, plus a stable per-club jitter (up to +20%) so a
  directory seeded in one week does not come due in one week for ever. A failed
  pull keeps the last good snapshot and only backs off.
- **WHO IS TARGETED**: `marketing_clubs` kind club, not excluded, not
  `not_interested`, no `existing_org_id`, a real CA guid (not `manual:`), and no
  `trial_modules` (a club already in a sales trial has done a trial;
  `--include-trialists` overrides). Never-pulled first, then clubs with an
  emailable contact, then longest overdue.
- **THE PULL RUNS BY DAY, NEVER OVERNIGHT (asked for directly).** Steady
  traffic in working hours is less conspicuous than a burst at 3am, so the job
  is an `OrTrigger` in Perth time, every 10 minutes 06:00-09:00 and 21:00-21:59
  and every 5 minutes 09:01-20:59 (`hour="6-8,21" minute="*/10"` plus
  `hour="9-20" minute="*/5"`; 09:00 sits on the 5-minute grid so nothing fires
  twice). The id stays `nightly_club_teasers`,
  the setting `club_teaser_nightly_limit` keeps its name and now means clubs
  PER RUN). Small runs, so the directory fills gradually.
- **WHO GETS A SNAPSHOT FOLLOWS THE DIRECTORY'S OWN TYPE FILTERS.**
  `club_teaser.type_filtered_ids` reads `club_directory._filter_conditions`, so
  "Juniors" means one thing on both screens. Default `DEFAULT_TYPE_MODES`
  excludes junior, carnival, school, rep and cricket_au; the setting
  `club_teaser_type_modes` overrides it (`{}` = no filtering), the script takes
  `--type key=include|exclude` and `--no-type-filter`. Ids are resolved in
  Python and bound as a uuid array. **A NULL test result counts as "does not
  match"**: the Directory's own cricket_au exclude drops a club with no generic
  email (NULL LIKE is NULL, and NOT NULL is NULL), which here would have removed
  every club with a blank field, so each condition is coalesced.
- **SEGMENTS KNOW WHICH CLUBS HAVE A SNAPSHOT.** Internal Segments has a
  `teaser_snapshot` multi-select (ready / empty / junior_only / error / none),
  a contact-level rule on `comms_contacts.marketing_club_id` like `club_is`
  (no MarketingClub join, so a contact with no club reads as `none`). Directory
  scope only, fails closed in a club build like every other directory field.
- **`--sample N` IS THE FIRST LIVE CHECK**: N clubs one at a time with a line
  each for status and CA calls; dry run unless `--apply`. Read `api_calls` off
  it before scaling. `run_batch` returns a per-club `detail` list for this.
- **OUTBOUND TRAFFIC IS OFF UNTIL SOMEBODY SETS IT.** The job (was: nightly at
  03:30 Perth) reads `club_teaser_nightly_limit` (General Settings key, unset = 0 =
  off) and honours the same Stop switch as every other unattended crawl
  (`marketing_crawl_control`), asked between clubs. The initial fill of the
  directory is `python -m app.scripts.pull_club_teasers all --limit N --apply`
  (dry run by default). At ~25 calls a club, 3,500 clubs is ~90k calls.
- **`--apply` ENDS WITH A WORK REPORT SO A SMALL RUN CAN BE EXTRAPOLATED.**
  `services/club_teaser_report.py` (stdlib only) turns the per-club rows
  (`run_batch` now records `secs` per club) into wall clock, clubs a minute,
  calls a second, a per-outcome table (ok / empty / junior_only / error, with
  calls and seconds per club) and a projection for every club still due. The
  projection is per-club LATENCY times clubs divided by the scheduled job's
  concurrency of 2, not the sample's own throughput (`--sample` runs one at a
  time), and it tabulates batch sizes 3/5/10/20 (plus the configured one) with
  the run length against the tightest 5 minute gap: a longer run loses the slot
  behind it. Under 20 clubs it says the sample is too small to trust. A dry run
  makes no calls, so it prints only the due count.
- **NOT BUILT**: the `/preview/{token}` page (one click handler that opens the
  claim prompt for everything), the PNG renderer and its HDD folder, the
  `{{teaser_url}}` / `{{teaser_image_url}}` merge variables, the match, lineup
  and scorecard layer (needs a Thursday/Friday refresh once the season starts),
  and a General Settings input for `club_teaser_nightly_limit`.
- **Verified against a real Postgres** (`backend/verification/verify_club_teaser.py`,
  67 checks with a scripted stand-in for CA, so no live call: the DDL three
  times, the builder, both junior paths, redaction, season probing, ladders,
  persistence, version-only-on-change, token stability, failure backoff,
  target selection, the batch runner incl. one club failing and the Stop
  switch) **with control runs**: service absent is REPORTED; with the change
  detection and the junior filter neutered, 6 fail. **NOT run against live
  Cricket Australia**: the real payload shapes for `startDate` on seasons and
  `statistics` on stat rows are taken from what `sync.py` reads. Dry-run 20
  directory clubs first and read `api_calls` off the rows before scaling up.
- **NUMBERED 312 after merging `origin/main`**, which had reached 311.

<!-- END original CLAUDE.md L538-640 -->
<!-- BEGIN original CLAUDE.md L2583-2700 -->
## The Club Directory's committee only ever grew (migration 295, v9.70.0, Sep 2026)

Asked for directly: a Rediscover that re-reads what PlayHQ publishes for every
club (and for one named club), prunes the officers it no longer lists, ticks
every officer with an email, leaves departed officers in BetterComms, and
updates the role of a contact already there.

- **DISCOVERY WAS ADDITIVE AND NOTHING SAID SO.** `_store_contact` upserts on
  lower(email) and has never removed a row, so a club that elected a new
  committee read as last season's officers PLUS this season's, with nothing on
  screen separating them. `crawl_batch` could not have fixed it either — its
  discovery phase only runs `if total == 0 or rediscover`, and the UI's Run
  crawl batch button has never sent `rediscover`, so on a populated directory
  that button does association enrichment ONLY.
- **A REDISCOVER IS THE SAME DISCOVERY PASS WITH TWO FLAGS, not a second
  reader.** `discover_clubs(prune=True, retick=True)`. Two copies of "read a
  club's committee" is how the nightly pass and the operator's button start
  disagreeing about what a committee is.
- **THE ROLE IS RESOLVED WITHIN THE PAYLOAD BEFORE ANYTHING IS WRITTEN, which
  is what makes replacing it safe.** The old rule was improve-only
  (`if role_rank < existing.role_rank`) for a real reason: one person
  legitimately appears twice in one payload (Secretary AND Junior Coordinator on
  one address) and the club should read as the senior. That is now decided in
  `_upsert_club` over the whole payload, so a Rediscover can then REPLACE the
  stored role outright — a Secretary who is now Treasurer reads as Treasurer.
  The ordinary crawl stays improve-only.
- **DELETING AN UNSUBSCRIBED OFFICER IS THE ONE THING THIS MUST NOT DO, and it
  is the whole reason `former_at` exists.** Delete the row and the next crawl
  re-adds them from PlayHQ as a fresh contact — subscribed, and ticked under the
  new rule — and we email somebody who opted out. So `_prune_committee` DELETES
  only where nothing a person decided would go with the row, and KEEPS the rest
  unticked with `former_at` stamped: an unsubscribe, a bounce, a
  `do_not_contact`, a note, or a `crm_people` link (migration 255's bridge is
  ON DELETE SET NULL, so a delete would not destroy the CRM person but would
  silently cut the link).
- **THREE ROWS ARE NEVER CANDIDATES AT ALL**: a contact a super admin added by
  hand (`source='manual'` — PlayHQ never listed it, so its absence says
  nothing), the org-level club mailbox, which comes from `discover_org_contact`
  rather than the committee list and is the only row carrying
  `_CLUB_CONTACT_RANK`, and anything at `_HAND_ADDED_RANK`. The suite asserts
  both ranks are unreachable from `_role_for_position`, so neither
  identification can go stale.
- **`sales_workspace.add_directory_contact` WROTE `source='api'`, so the first
  cut of the prune DELETED A PERSON A REP HAD TYPED IN.** Found by asking
  whether the CRM needed a push, not by the suite — the drawer writes through
  `_store_contact`, which hardcoded the source, so a Workspace-added contact was
  indistinguishable from a crawled officer and only survived if it happened to
  carry a note, an opt-out or a logged call. It stores `'manual'` now, and rank
  99 covers every row written before the fix: `_role_for_position` returns only
  1/2/3/4/5/10/50/60, so 99 cannot have come from a crawl. **The control run is
  what showed the size of it** — with both halves reverted, both Workspace
  contacts are gone.
- **`contacts` ABSENT AND `contacts: []` ARE DIFFERENT ANSWERS.** Present-but-
  empty is a club that publishes no committee and everything prunable goes;
  absent or null is a payload that said nothing, and prunes nobody — an upstream
  shape change must not be able to empty the whole directory in one pass.
- **A LISTED OFFICER WITH AN EMAIL IS TICKED, and the insert default changed
  from `rank <= 4` to "has an email"** — a Junior Coordinator with an address is
  as emailable as a Treasurer. Never a contact who unsubscribed, bounced or
  asked not to be contacted: ticking those shows a super admin a recipient who
  can never be sent to. **An ordinary crawl still never re-ticks somebody a
  super admin unticked** (`retick=False`), or the nightly pass would fight the
  operator; only the explicit Rediscover and the explicit "Tick officers with an
  email" button apply the rule to existing rows.
- **THE EXPORT UPDATES RATHER THAN SKIPS.** `export_to_comms` used to stamp
  `exported_at` on an address already in BetterComms and move on, so an officer
  who changed role kept the role they held when they were first exported.
  `comms_contacts.role` is refreshed now; a blank name and a missing club link
  are filled; a name set by hand on the comms side is never overwritten and a
  suppressed address is never resurrected.
- **`comms_contacts.role` IS A STORED COPY ON PURPOSE, against this file's own
  derive-don't-store instinct.** A departed officer is pruned from the Directory
  and KEPT in BetterComms — that is what was asked for — so a join back to
  `marketing_club_contacts` would blank exactly the people the feature exists to
  preserve. It is the last role we knew them by, which is the honest reading.
  It is also what makes Role a filter facet on Lists and Segments.
- **ONE CONTACT SERIALISER.** `list_clubs` had its own copy of `_contact_out`'s
  dict, so `former` would have reached the club card and not the list. It calls
  the shared one now, and the suite asserts there is exactly one copy.
- **`emptyFilters` IS THE ONE FACET SHAPE.** `CommsLists.jsx` kept its own
  `noFilters` literal, which silently drops any facet added to the kit — Role
  was added to the kit.
- **Verified against a real Postgres**
  (`backend/verification/verify_committee_rediscover.py`, 91 checks through the
  shipped service and route bodies with the PlayHQ client stubbed: migration 295
  applied three times to a populated pre-293 table seeded in RAW SQL — the ORM
  model already carries the columns, so a row inserted through it could not be a
  pre-293 row — the ordinary crawl still additive and still not re-ticking, the
  role replaced on a rediscover and improve-only otherwise, one person listed
  twice, all five retained cases marked and unticked, the manual row and the org
  mailbox untouched, a returning officer clearing `former_at` without being
  re-ticked, both upstream-shape guards, one named club matched on its GUID
  rather than a name two clubs share and found by routingCode after a rename, an
  unreachable PlayHQ reading as a fetch failure rather than an empty committee, a
  stopped crawler stopping the run, the ticking rule and its four exclusions, and
  the export updating a role while never resurrecting a suppressed address)
  **with two control runs**: with the whole feature absent the suite REPORTS it
  and bails rather than dying on the ImportError; with the prune, the retick and
  the role refresh neutered, 24 of the 91 fail — the departed officer still
  listed and the comms role stuck on the old one, which is the reported symptom.
- **THE POLITENESS DOC WAS STALE AND IS CORRECTED IN PLACE.**
  `docs/marketing-club-directory.md` said "a jittered 2 to 4s delay"; the shipped
  defaults are `marketing_crawl_min_delay=15.0` / `_max_delay=40.0`, applied
  BEFORE each request behind a module-level `asyncio.Semaphore(1)` that every
  directory call queues on. ~6,900 AU clubs at 100 per page is ~70 requests, so a
  full Rediscover is roughly half an hour to an hour, not the "hours" the first
  cut of the UI copy claimed. A single-club Rediscover uses the short
  interactive delay (0.2-0.7s) `discover_org_contact` already uses for the
  self-serve registration lookup.
- **NUMBERED 293, NOT 291.** `origin/main` had reached 292 while this was in
  flight. Check `origin/main` at the moment you merge, not only when you first
  number one — this file has now recorded that trap four times.
- **NOTICED, NOT BUILT**: there is no `role` SEGMENT field (Role is a Lists and
  Segments facet, not a saved-rule condition — that needs its own entry in
  `comms_segments`' registry); nothing prunes a `former_at` contact later, which
  is deliberate, since the whole reason those rows survived is that somebody
  decided something about them; and the nightly discovery pass still runs
  additive, so the reconcile only happens when an operator asks for it.
<!-- END original CLAUDE.md L2583-2700 -->
<!-- BEGIN original CLAUDE.md L8465-8535 -->
## Super Admin New Club = the self-serve registration (migration 225, v9.13.0, Aug 2026)

Reported: a club a super admin creates from All Clubs → NEW CLUB got none of
what a self-serve trial registration sets up. `create_club` built a bare
`Organisation` row plus a Core subscription and stopped — no trial, no admin
account, no sync, nothing in the CRM. It now runs the same steps
`self_serve_trial.submit` does, sequenced the same way.

- **It goes through `_onboard_club_core`** (organisations.py) rather than
  hand-building an `Organisation`, which is what gets the first full sync +
  `auto_yearbooks=True` + the Marketing Directory link for free. The form's own
  fields (slug, short name, contact email, colours) are applied AFTER, since
  `upsert_organisation` never sets them. Same atomicity caveat as self-serve:
  the User is created **flush-only first** (so a username race surfaces before
  anything exists), then `_onboard_club_core`'s internal commit commits it too,
  then membership + trials in a try whose failure path says "don't retry".
- **A Primary Club Admin is mandatory, and staff never choose their password.**
  The account is created with `password_hash=NULL` + an `invite_token`, and
  `user_invite.send_invite_email` sends the `/login?invite=` link — the existing
  Club Users → Invite admin machinery, unchanged. **The self-serve 4-digit email
  PIN has no equivalent here and shouldn't be bolted on**: that flow is
  synchronous and the person entering the code must hold the inbox, which the
  super admin filling this form does not. The invite link proves the same thing
  (only whoever holds that inbox can activate the account) asynchronously.
- **`services/admin_identity.py` is now the ONE set of primary-admin field
  rules** (username/email/display-name/mobile), shared by self-serve and this
  flow; `self_serve_trial._validate_admin_fields` is a thin wrapper over it.
  Only difference: `require_mobile` — mandatory when the club's own admin is
  filling it in, optional when staff are.
- **Every module trials, Core included** (`BILLABLE_MODULES` via
  `start_trial_billing`, so `admin` correctly expands to fees/comms/merch/crm),
  on `platform_settings.get_default_trial_days`. `is_active=True` too — an
  inactive club would show its own admin a dead public site for the whole trial.
- **`organisations.onboarding_method`** (migration 225, mirrored in the lifespan)
  — `'self_serve_trial' | 'super_admin_trial' | 'direct_subscriber' | 'none'`,
  the same vocabulary the CRM deal carries. NULL for every club onboarded before
  it existed. **This exists because two inferences broke the moment New Club
  started creating a real primary admin:**
  - `trial_engagement.trial_depth_score` scored the registration milestone from
    "does this club have a primary admin" as a proxy for staff-vs-club. Sound
    only while New Club left a club with no admin at all. It reads the column
    now, falling back to the proxy for pre-225 clubs.
  - `onboarding_wizard.get_state`'s auto-open fired on (a) not-yet-synced or (b)
    reopen-after-sync-with-stored-progress. A super-admin-created club's admin
    typically accepts their invite days later, after sync finished and with no
    progress — neither fired. New branch (c): `first_opened_at IS NULL` and not
    dismissed and `onboarding_method` set, which by construction can never catch
    a long-established club.
- **CRM**: `crm.sync_super_admin_trial_deal` stamps `onboarding_method =
  'super_admin_trial'` and fires on the **`trial_started`** rule, not
  `self_serve_signup` — that IS what happened, and a club that didn't sign
  itself up must not trip the self-serve rule. No `lead_source`: staff typing a
  club in have no first-touch attribution, and guessing one puts a fabricated
  channel on the card. Both it and its self-serve sibling share
  `_sync_trial_registration_deal` / `_sync_trial_registration`.
- **Twenty**: reuses `push_self_serve_registration` with `source=
  'super_admin_trial'` and **both stage overrides set to None** — "Self-Serve
  Trial" would be a false claim, and Twenty's enum has no super-admin member to
  name instead, so the Lead opens at its computed lifecycle. The distinction
  lives in our own deal's `onboarding_method`.
- **Confirmed while here**: self-serve DOES already create a deal marked
  Self-Serve Trial (Trial stage, $399 Stats base, lead source derived from ad
  attribution, registering admin as point of contact) — verified, not assumed.
- **Verified against a real Postgres**: 52 checks on the new flow (every module
  trialling, the invite-not-password account, primary-admin flag, sync run,
  audit row, the queued background work and its arguments, the deal card, the
  staff-discounted score with self-serve and pre-225 controls, wizard auto-open
  plus a long-established-club control, and six validation guards) and 16 on
  the untouched self-serve flow. Migration applied twice to a populated
  pre-225 table.

<!-- END original CLAUDE.md L8465-8535 -->
<!-- BEGIN original CLAUDE.md L10041-10100 -->
## Password-protected "Draft" pages + trial-ended unpause requests (v9.0.0, Aug 2026)

A third public-page state alongside `is_active`'s Active/Inactive: the page exists
and is reachable but gated behind a 4-digit PIN, either the club's own voluntary
choice or a Super-Admin sales-conversion lock on a lapsed trial.

- **Migration 205**: `organisations.password_protected` (bool), `.password_protect_reason`
  (`'draft'` | `'trial_ended'`, meaningful only when protected), `.access_pin_hash`
  (bcrypt — the raw PIN is never stored), `.password_protected_at`/`.password_protected_by`
  (audit). New table `club_unpause_requests` (org, email, message, status
  pending/actioned/dismissed, actioned_at/by) — the queue behind the "email me for
  access" form. Both mirrored idempotently in `main.py`'s lifespan per the usual
  pattern. `password_protected` is deliberately independent of `is_active` — the
  gate always checks `password_protected` FIRST, so it wins regardless of `is_active`.
- **`app/services/club_lock.py`** — the shared PIN/cookie primitive, modeled
  directly on `public_availability.py`'s `bs_avail` pattern: `hash_pin`/`verify_pin`
  (bcrypt), `issue_lock_cookie`/`is_unlocked` (signed JWT cookie `bs_lock`, HttpOnly,
  30 days), `is_locked_for_request(org, request)`, and `lock_detail(org)` (the
  structured 423 payload — same `detail={"code": ..., "message": ...}` convention
  `require_module`'s 402 upsell already uses).
- **`routers/clubs.py`**: `GET /{slug}` raises **423** (not 403) with the lock
  payload when password-protected and unlocked-by-cookie fails, checked ahead of
  the existing `_public_blocked` 403. New `POST /{slug}/unlock` (PIN verify,
  rate-limited + lockout via `rate_limit.assert_not_locked`, same shape as
  BetterSelect's self-service PIN) and `POST /{slug}/request-unpause` (only valid
  when `password_protect_reason == 'trial_ended'`; creates the queue row, emails
  **`cricket@bettersports.com.au`** specifically — a deliberate choice, not the
  general support address — with `reply_to` set to the requester's own email so
  Super Admin can just hit reply). Same lock check added to `ladders.py` and
  `website.py`'s public endpoints for defense-in-depth parity with how they
  already duplicate the `is_active` check independently of `clubs.py`.
- **Club-admin self-serve** (`routers/club_admin.py`'s `/settings` PATCH,
  `MANAGE_SETTINGS` cap): a club can enable Draft mode itself only while
  `subscription_status` is `trial` or `active` — turning it off is always allowed.
  Always sets `password_protect_reason='draft'`; `'trial_ended'` is Super-Admin-only
  via `ClubUpdate`/`patch_club` (no subscription-status gate there — "whenever they
  want").
- **Super Admin**: `SuperClubs.jsx`'s edit drawer gets a "Public access" panel
  (independent of the existing Active/Inactive pill) — enable + reason picker
  (Draft / Trial ended) + PIN field, behind a `window.confirm` before turning on.
  New `/admin/super/unpause-requests` (`SuperUnpauseRequests.jsx`, mirrors
  `SuperOnboarding.jsx`'s list/filter/status pattern) added to `lib/superNav.js`'s
  Clubs & Data section with a pending-count badge (same wiring as
  `moduleRequests`/`commsRequests`).
- **Frontend gate**: `useClub.js` gained a `locked` state (detected via `err.status
  === 423`, the payload already surfaces as `error.detail` per api.js's existing
  object-shaped-detail handling) plus `unlock`/`requestAccess`. New
  `ClubPinGate.jsx` (styled like `ClubInactive.jsx`'s hero treatment) renders the
  PIN entry, and — only for `reason: 'trial_ended'` — the "This trial has ended…"
  copy and email-request form. Wired into all 12 public page files that already do
  the `if (inactive) return <ClubInactive/>` pattern (Dashboard, Players, Records,
  Ladders, Leaderboard, StatLab, GamesPage, FixturesPage, LineupsPage, TeamDetail,
  Teams, PlayerComparison), checked before `inactive`/`notFound`.
- **Known scope boundary**: only `GET /clubs/{slug}` (+ `ladders`/`website`'s own
  public endpoints) are PIN-gated server-side. The dozens of other org-scoped data
  endpoints (players, records, games, etc.) aren't independently re-checked — the
  frontend never learns the org id without unlocking first, so this is a soft
  privacy/sales gate, not a hardened access-control boundary (matching the same
  posture the existing self-serve-availability magic link already accepts).

<!-- END original CLAUDE.md L10041-10100 -->
<!-- BEGIN original CLAUDE.md L10101-10167 -->
## Admin navigation — module surfaces, and where the Core tools live (v8.82.0, Jul 2026)

The admin app is organised as **module surfaces**: each Better product is a card
on the admin dashboard that opens its own focused sidebar (`ModuleLayout`, a thin
per-module wrapper: `BetterSelectLayout`, `BetterFeesLayout`, `IQLayout`, …). The
shared `components/admin/AdminLayout` is now just the **app chrome** — Dashboard,
Setup Wizard, the module cards/tiles, and the Account group (Activity Log, Plan &
Billing, Settings, Users) — plus the **Better HQ** section for super admins
(grouped via `lib/superNav.js`, see the Better HQ note if present).

- **BetterStats (Core) is its own surface** now (it used to be a loose pile in the
  shared sidebar). `BetterStatsLayout` (green, `moduleBrand('stats')`), home at
  `/admin/betterstats` (`BetterStatsHome`). GROUPS: **Club Data** (Matches,
  Players, Import Players, Seasons), **Data Import** (Data Sync, Import Stats,
  Upload Scorecard, Manual Entries, Milestones, Partnership Records), **Clean Your
  Data** (Merge Players, Merge Grades) and **Records & content** (Awards, Award
  Types, Yearbooks, Saved Reports, Sponsors). Group `key`s (`data`/`ingest`/`tidy`/
  `records`) are stable and drive the `:group` URLs, so the display labels can be
  renamed without moving a route.
- **BetterClubManager** (provisional name) is an **upcoming** back-office surface,
  NOT a live Core tile. It shows as a **"Coming soon" card under BetterAdmin**
  (`BetterAdminHome`) — greyed/non-clickable for everyone except **super admins**,
  who get a live "Preview" link. Its surface (`BetterClubManagerLayout` indigo,
  home `/admin/betterclub` `BetterClubManagerHome`) and every one of its tool
  routes (`/admin/committee`, `/admin/volunteers`, `/admin/families`,
  `/admin/qualifications`, `/admin/member-portal`, `/admin/events`, `/admin/assets`,
  `/admin/club-diary`) were gated `requireRole="super_admin"` in `App.jsx`, so
  ordinary club admins had **no access** to these tools until BetterClubManager
  launched. **Superseded in v9.6.1** — those screens are now open to the club's
  own admins (see the access note below); the gate had outlived the reason for
  it and was hiding most of BetterClubhouse from the clubs paying for it. It is therefore NOT in `CORE_TILES` /
  `dashboardTiles()` (off the dashboard, sidebar and module switcher).
- **The one Core surface tile** (BetterStats) lives in `CORE_TILES` in
  `lib/modules.js` — deliberately OUTSIDE `MODULE_INFO` (which feeds
  entitlement/billing). `dashboardTiles()` returns `[BetterStats, …paid modules…]`;
  `alwaysOpen` keeps it entitled for every admin.
- **Two-level home, one config.** Each layout exports a `GROUPS` array (key,
  label, icon, `desc`, and `items` each with `to`/`label`/`icon`/`cap`/`desc`).
  It drives all three views so nothing drifts: the surface home
  (`/admin/betterstats`) shows one card per group; a group card opens
  `/admin/betterstats/:group` (one card per tool, with descriptions); and the
  sidebar flattens `GROUPS` into headed sections. `components/admin/ModuleHub`
  renders the home + group pages from `GROUPS`; the `Home` page components pass
  `groupKey` from the `:group` route param. BetterClubManager's Member Portal is
  inserted into its People group only when the flag is on (`withPortal`).
- **`components/admin/HubCard`** is the one house-style menu card (matches
  BetterAdmin's sub-cards): name (+ badges) and arrow on top, description below,
  accent-tinted; `state: 'open'` is a link, `'soon'` is a greyed non-clickable
  teaser. Used by `ModuleHub` (BetterStats overview + group pages), the
  BetterSelect Overview tool grid, and the BetterClubManager "Coming soon" card.
  A `title` starting with "Better" gets the coloured-suffix wordmark. **Use HubCard
  for any new menu card** so the look stays consistent.
- **URLs are unchanged** — the tool pages kept their existing routes
  (`/admin/players`, `/admin/committee`, …); only the layout wrapper each page
  renders changed (`AdminLayout` → the module layout). So bookmarks/links still
  work and no route moved.
- `ModuleLayout`'s `nav` now supports `{ heading }` separators (grouped sidebar);
  a heading with no visible items under it after cap-filtering is dropped.
- **Adding a Core tool**: put the page under the right module layout wrapper and
  add it to the correct group's `items` in that layout's `GROUPS` (that's all —
  the sidebar nav, the group page and the overview count all derive from it).
  Don't add Core tools back into `AdminLayout`'s `NAV_SECTIONS` — that's
  chrome-only now.
- **Yearbooks** (`/admin/yearbook`, `AdminYearbook`) is still a standalone
  full-page editor with no surrounding sidebar (it always was); the BetterStats
  nav links to it but the page itself doesn't wrap in `BetterStatsLayout`.

<!-- END original CLAUDE.md L10101-10167 -->
<!-- BEGIN original CLAUDE.md L12574-12665 -->
## Club Setup Wizard (v8.70.0, Jul 2026)

The Phase-15 checklist modal (`OnboardingWizardModal.jsx`, deleted) grew into a
full-page, whole-platform **Setup Wizard** at `/admin/setup(/:stepKey)`
(`frontend/src/pages/admin/setup/` — `SetupWizard.jsx` + `SetupInlineSteps.jsx`
+ `SetupModuleSteps.jsx` + `setupUi.jsx`). 28 steps in 7 groups (data in →
data tools → BetterSelect → BetterSocials → BetterAdmin → BetterIQ →
BetterFantasy), same table/flag/router as before:

- **Entry points (v8.70.1)**: a permanent **"Setup Wizard" sidebar item** (top
  unheaded section, beside Dashboard, every role) plus the header SETUP GUIDE
  shortcut (any role whose `/state` fetch succeeds — a super admin needs an
  acting-as club). The `onboarding_wizard_enabled` platform-flag gate was
  REMOVED from the router (the flag + `require_onboarding_wizard_enabled` in
  `auth.py` still exist but gate nothing — the General Settings toggle is
  inert for the wizard now). Sidebar sections (and Better HQ links, after
  Platform Overview) are kept in ALPHABETICAL order by label — keep it that
  way when adding links.
- **Auto-open is conservative** (because the gate is gone): fresh-login
  navigation to `/admin/setup` fires only for (a) a brand-new club — no
  successful full sync — that hasn't dismissed it, or (b) the one-shot
  Decision-11 reopen-after-sync, only if stored progress exists (`engaged`),
  so long-established clubs are never yanked into setup. Super admins are
  never auto-navigated.
- **Backend** `routers/onboarding_wizard.py`, club-admin auth. `GET /flow` is the wizard:
  step registry (`GROUPS`) filtered to the club's entitlements, per-step
  auto-detection (`_detect_steps` — cheap org-scoped EXISTS: logo set, sponsor
  rows, merge_logs, fee_schedules, fantasy season/pool, a `ready` dossier…),
  and it **persists newly-detected completion into `completed_steps`** so the
  cheap `GET /state` summary (AdminLayout polls it every mount) reads stored
  state only. `POST /steps/{key}` takes `{done?, skipped?}` (mutually
  exclusive; detection beats a skip). `skipped_steps` column = migration 157
  (+ lifespan mirror). Steps the DB can't see (socials palette → localStorage,
  the review-only fantasy steps) are manual-mark only.
- **Sync gating**: the "Tidy your data" group locks until a successful full
  pull. `_sync_ready` now accepts `org_full` **or** `org_hard_refresh` — the
  old checklist only looked for `org_full`, so a club whose first complete
  pull was a Full Rebuild never unlocked those steps (fixed here).
- **Hybrid steps**: simple actions run inline through their EXISTING endpoints
  (hard-refresh + sync-log polling, branding, sponsor create, fixture
  sync, squad seed/auto-assign, availability self-serve, website enable, comms
  sender settings, Square/Xero connect [live status + the OAuth connect-url,
  stamping the return flag before redirecting], fantasy season/pool); complex
  tools are link-out steps. Link-outs stamp `sessionStorage.bs_setup_return`
  and `SetupReturnBar.jsx` (a **floating bottom pill**, gradient-ringed,
  mounted in `ProtectedRoute` beside `TrialBanner` so it covers module
  layouts and OAuth round-trips too) offers "back to setup". Vital steps
  (full_rebuild, merge_players, merge_grades) get a concrete-consequences
  confirm before skipping. **The branding step edits `theme_config`
  (accent/accent2, merged over the stored config), NOT the legacy
  `primary_color`/`accent_color` columns** — theme_config is what actually
  themes the site (v8.70.2 fix); logo upload goes through `ImageEditorModal`
  (crop + background removal) before saving.
- **IQ pre-warm** (`services/iq_prewarm.py`; `GET/POST /iq/opposition/prewarm*`):
  builds every known opponent's dossier for chosen grades **one at a time** in
  a detached task (in-process progress dict, ≤40 opponents, 5-min per-build
  timeout), reusing `iq_opponent.get_or_start_dossier` — a fresh dossier is a
  cache hit, so re-runs are cheap. Grade options come from the latest season
  year with per-grade distinct-opponent counts; busiest 3 pre-ticked.
- Old `explore_*` step keys may linger in stored `completed_steps` —
  harmless, ignored by the registry.

### Periodic setup reminder (v8.70.3)

A permanently-dismissed `SetupReturnBar` pill (see above) shouldn't mean a
half-finished club setup is forgotten forever. `SetupProgressReminder.jsx` —
a small bottom-RIGHT toast (distinct corner from the pill, which is
bottom-centre) — fires on **every 5th landing on the bare `/admin` dashboard**
while any step is still neither done nor skipped, **regardless of the
wizard's own `dismissed_at`** (dismissing the pill/wizard only stops the
should_auto_open navigation, not this nudge). Counted client-side
(`localStorage['bs_setup_reminder_visits_<user.id>']`, since `AdminLayout`
remounts on every navigation and this is a UX nicety, not real progress
state) inside the same effect that already fetches `GET .../state` on every
mount — no extra request. Auto-hides after ~12s or on its own ✕; dismissing
it only clears this one instance, it reappears on the next 5th-visit tick.
`GET .../state` now also returns `addressed` (done+skipped) alongside `done`/
`total`, so the toast can say how many steps are left.

### Secondary accent, luminance-guarded (v8.70.2)

`theme.js::safeAccent2(accent2, accent, mode)`: many clubs' second colour is
black or white, which vanishes against the matching theme background.
`buildThemeCss` now emits per-theme `--pb-accent-2-safe`, a per-theme
`--pb-gradient`, and a per-theme `--pb-chart-wickets` (all guarded: near-black
falls back to the PRIMARY accent on dark, near-white on light; the raw
`--pb-accent-2` stays available). Consumers of the pairing: Navbar active-tab
underline, `StatCard`'s accent variant (small gradient bar), the wizard
progress bar + return pill, plus the pre-existing `.pb-gradient` utilities /
presskit. **Paint club colour pairs with `var(--pb-gradient)` or
`--pb-accent-2-safe`, never raw `--pb-accent-2`, unless you know the surface.**

<!-- END original CLAUDE.md L12574-12665 -->
<!-- BEGIN original CLAUDE.md L13719-13843 -->
## KlubPro → BetterStats Migration Tooling (v8.4, Jun 2026)

Super-admin-only onboarding wizard (integrated into the admin app, **not** a
standalone tool) that reviews data staged in the **external KlubPro Postgres**
(`klubpro_migration` schema) and imports **player profiles** (matched to existing
BetterStats players by name — KlubPro has no CA ids) + **sponsors**. Full guide:
`docs/klubpro-migration.md`.

- **Two DBs.** BetterStats uses the normal `get_db`. KlubPro gets a **lazy**
  second engine in `app/services/klubpro_db.py` (`get_klubpro_db`, built from
  `KLUBPRO_DATABASE_URL`) — only instantiated when an operator hits a migration
  endpoint, so the app boots/runs normally with it unset (the page shows "not
  configured"). KlubPro is **never ORM-mapped** — schema-qualified raw SQL only,
  so it never enters Alembic.
- **Gating.** Router `routers/klubpro_migration.py` (prefix `/club-admin/klubpro`)
  is `require_super_admin` (cross-club platform tooling, not a per-club cap). UI
  at `/admin/super/migration` (`pages/admin/klubpro/`), `requireRole="super_admin"`,
  linked from `AdminLayout` `SUPER_LINKS`.
- **Migration 072** (+ mirrored idempotent lifespan creates): adds
  `org_sponsors.contact_name/.email/.klubpro_sponsor_id` (the handoff's sponsor
  insert targets these three — the repo's `org_sponsors` lacked them) + partial
  unique `(organisation_id, klubpro_sponsor_id)`; and two **BetterStats-side**
  bookkeeping tables `klubpro_migration_batches` / `klubpro_migration_backups`
  (so backups/audit survive even if KlubPro is decommissioned and rollback is a
  pure BetterStats op).
- **Safety invariants** (`services/klubpro_migration.py`): fills gaps but **never
  clobbers with empties**; `is_opening_batsman=False` = "no info" (only `True`
  applied); **skills compare as a set**; only the **ten profile fields** are ever
  written (no stats/games/ids/org). Sponsor import is dedup-safe on the unique
  index. Flow is **dry-run → confirm → per-row backup → write**, every batch
  **rollback-able** from the History tab.
- **`sponsor_import_selections` is intentionally NOT the source of truth** — its
  columns weren't in the handoff, so selection is client-side and de-dup is
  enforced on the BetterStats side instead of guessing that schema. The other
  KlubPro tables (`player_match_mappings` etc.) have documented columns and are
  used directly.
- **Editable club mapping** (from the dashboard): the "Mapped to" column is a
  dropdown of all orgs (`GET /club-admin/klubpro/organisations`); `PATCH
  /club-admin/klubpro/club-mapping {klubpro_club_id, betterstats_organisation_id,
  force}` does an **UPDATE-or-INSERT** on `club_mappings` (never DELETE → row id
  + `player_match_mappings` FK preserved), keyed by `klubpro_club_id`, and bumps
  the onboarding target to `mapped` (keeps `validated`). Returns
  `{status:'conflict'}` (HTTP 200, not an error — the api client doesn't surface
  status) when the org is already mapped to another KlubPro club; the UI confirms
  then retries with `force`. `fetch_dashboard` LEFT JOINs `club_mappings` so each
  summary row carries its mapping. Mapping is repeatable/update-safe and needs no
  manual SQL for future clubs. Candidate matching is **not** auto-run on map.
- **Field-level approval** (v8.4): approving a match approves the *relationship*,
  not a blanket field overwrite. Each match shows the 9 migratable fields
  (`MIGRATABLE_FIELDS` = gender/email/phone/player_role/batting_hand/bowling_type/
  is_opening_batsman/skill_positions/profile_image) side-by-side with a checkbox;
  only ticked fields migrate. `recommended_fields` pre-ticks every field KlubPro has
  a value for, **including `profile_image` whenever KlubPro has an image** (untick to
  keep a newer BS photo; applying overwrites the BS photo, old one saved in the
  backup for rollback). The collapsed card keeps the rich side-by-side summary (both
  images + details); "Fields" toggles the checkbox panel. Selections persist to
  `player_match_mappings.migrate_fields jsonb` (+ `reviewed_at/by`, `imported_at/by`)
  — columns added at runtime by `ensure_match_columns` since KlubPro is external
  (not in Alembic). `plan_player` is the single source the dry-run AND import share
  (apply = selected ∧ non-empty ∧ differs; photo overwrites only when ticked).
  **Bulk Approve** (`POST .../players/bulk-approve`) approves all eligible rows
  honouring each one's field selections (per-item commit + item-level errors so one
  bad row can't poison the batch). first/last/nickname are NOT migratable (BS has a
  single `name`). The dry-run reflects **saved** approvals — approve → dry-run →
  import.
- **Approve ≠ import** (UX gotcha, fixed v8.4): Approve/Bulk-approve only write the
  *decision* (+`migrate_fields`) to `player_match_mappings`; **`Import` is the only
  step that writes BetterStats `players`**. Cards show `APPROVED · NOT IMPORTED`
  (blue) vs `IMPORTED ✓` (green, from `imported_at`); the header carries
  approved/imported/pending counts; `Import` is enabled on the approved-but-not-yet-
  imported count (no longer requires a prior dry-run) with an amber "click Import to
  apply" nudge. Was reported as "approved but data not pulled across" — the import
  had simply never been run.
- **Reject/skip persistence** (fixed v8.4): `upsert_match_mapping` **UPDATEs the
  existing mapping in place** for reject/skip (never nulls `klubpro_player_id` — the
  column may be NOT NULL) and normalises `match_status` to past-tense
  (`approved`/`rejected`/`skipped`); sending the imperative `reject`/`skip` + a NULL
  match id was erroring on the external table's constraints. Approve still
  DELETE+INSERTs (match id always present).
- **Re-matching a rejected KP player** (fixed v8.4): the KP table has a unique on
  the KP id, so a rejected match still holding `klubpro_player_id` blocked
  approving that KP player to a *different* BetterStats player (symptom: reject
  Jnr, then approving Snr errors). Fix: the approve path first **frees the KP id
  from any other BetterStats player** in the club (`UPDATE … SET
  klubpro_player_id=NULL, approved=false, match_status='rejected' WHERE
  klubpro_player_id=:kpid AND betterstats_player_id<>:bpid`), so the rejected row
  keeps its status but releases the id. Requires the id to be nullable —
  `ensure_match_columns` now also `ALTER COLUMN klubpro_player_id DROP NOT NULL`
  (separate txn so it can't roll back the added columns).
- **Name matching** (fixed v8.4): the candidate picker is whitespace/​suffix/​order
  tolerant — `normName` collapses double spaces (an empty middle-name slot renders
  as "First  Last") and strips Jnr/Snr/Jr/Sr; matching is token-AND over the
  normalised KlubPro name, so "Eadon-Clarke Jnr, Chas" finds "Chas Eadon-Clarke".
  (A genuinely *different* middle name still needs the operator to edit the
  search.)
- **In-tool auto-suggest** (v8.4): the external candidate generation only ran for
  4 clubs (Applecross/High Wycombe/Murdoch/Portland), so a newly-mapped club's
  `player_match_mappings` is empty → every player showed NO MATCH even though the
  staged candidates exist. `KlubproPlayers.load()` now name-matches client-side for
  any player with **no** pre-generated row: exact normalised-name (`nameKey` =
  sorted tokens) → auto-suggest it (SUGGESTED, bulk-approvable); **two+ same-name
  candidates** (e.g. "Grace Abbott" ×2) → flag `ambiguous` → "REVIEW · N MATCHES"
  (never auto-picked). Only fills gaps (rows that already had a generated/decided
  match are untouched), so the 4 done clubs are unchanged. Header shows
  suggested/to-review/no-match counts; filters added for each.
- **Value normalisation** (fixed v8.4 — was importing display labels verbatim):
  KlubPro stages `betterstats_*` as **human labels** ("Right handed", "Right-arm
  fast-medium", "Male") but BetterStats stores **codes** (`batting_hand` 'RIGHT';
  bowling split into `bowling_action` 'RIGHT_ARM' + `bowling_type` 'FAST_MEDIUM';
  gender 'male'). `_norm_batting_hand`/`_norm_bowling`/`_norm_gender`/`_norm_role`
  (mirroring `frontend/src/lib/playerAttributes.js`) convert on import in
  `_incoming_map`; the `bowling_type` checkbox sets **both** bowling columns. Role
  happens to be stored as its label so it always worked. Unrecognised value →
  None → treated as empty (never written). The frontend card now displays codes
  as labels + compares normalised so 'RIGHT' vs "Right handed" isn't a false diff.
  **Photo**: a normal upload sets `photo_url=/api/images/players/{id}/photo?v=…`
  and BetterSelect's avatar renders from `photo_url` — the import now sets it too
  (it had set only `photo_data`/`photo_mime`, so the public profile showed the
  photo but the admin avatar didn't). `_player_before`/rollback now also carry
  `bowling_action` + `photo_url`. **A club imported before this fix (e.g. Murdoch)
  must be re-Imported** — the normalised value differs from the stored bad label,
  so a re-run repairs every row.
- **Deploy**: set `KLUBPRO_DATABASE_URL` (never commit the pw) AND ensure
  `betterstats-backend` shares a Docker network with `klubpro-postgres`.

<!-- END original CLAUDE.md L13719-13843 -->
<!-- BEGIN original CLAUDE.md L16912-16979 -->
## A club admin's mobile is already written down at their club (v9.67.0, Sep 2026)

Asked for: for every club admin we hold no mobile number for, look at their club
in the directory, find that person's record, and store their mobile against the
user account.

- **NEITHER FLOW THAT CREATES A CLUB ADMIN INSISTS ON A MOBILE, WHICH IS WHY THE
  GAP EXISTS.** `admin_identity.validate_admin_fields` takes `require_mobile`
  precisely so a super admin creating a club on somebody's behalf can leave it
  blank, and an admin invited to an existing club (`create_club_user`) is never
  asked for one at all. The number is frequently already on file about the same
  person a table away.
- **THREE PLACES A CLUB HOLDS A PHONE NUMBER, and all three are read** —
  `fee_members.mobile`, the linked `players.phone` the Directory itself falls
  back to (a read-through player with no member row included), and the Clubs
  Directory contact for their club through `marketing_clubs.existing_org_id`.
  That third one is the case a Clubhouse-only reading would have missed: a
  brand-new club's first admin is usually its secretary, and that is the list
  their mobile is on before anybody has built the club's own Directory.
- **AN EMAIL MATCH IS AN IDENTITY; A NAME MATCH IS NOT.** So every email match
  beats every name match whatever source it came from, and where a NAME match
  turns up two different numbers it REFUSES rather than picking — a shared
  surname and first name at one club is the shape of a father and son, the same
  reason `_name_variant_pairs` is never bulk-mergeable. Two different numbers
  under one EMAIL is one person with two recorded numbers, so there the source
  order decides (the club's own member record, then the player behind it, then
  the Clubs Directory contact).
- **THE NUMBER HAS TO BE A MOBILE, AND `admin_identity.mobile_valid` IS THE ONE
  RULE.** `players.phone` and `fee_members.mobile` are free text and routinely
  hold a clubroom landline — `(08) 9364 1234` matches a person perfectly well
  and is not a mobile. It is REPORTED with the number rather than stored, so an
  operator can see it is a landline instead of wondering why the match did
  nothing. Writing a landline into a field the platform will one day text is
  worse than leaving it blank.
- **SCOPED TO THEIR OWN CLUB, and the join is org-scoped as well as keyed.** A
  `fee_members` row can point at another club's player (the cross-club leak this
  file already documents for exactly this join), so without
  `p.organisation_id = fm.organisation_id` this would serve a stranger's mobile
  as if it were the admin's. Caught by the control run, not by reading it.
- **NOTHING IS EVER OVERWRITTEN.** Only an admin whose `mobile_number` is blank
  is considered at all, so a run is idempotent and a second writes nothing. No
  network call either — everything read is already ours — so it is quick enough
  to run platform-wide.
- **`admin_contact_list.admin_rows` IS THE ONE DEFINITION OF "A CLUB ADMIN"**,
  reused rather than re-queried: the primary is that same role carrying
  `is_primary_admin`, a super_admin or sales membership is Better staff, and an
  archived club is left out. Two copies is how this and the contact-list sync
  start disagreeing about who counts.
- **`python -m app.scripts.backfill_admin_mobiles [<org|all>] [--apply]
  [--email-only]`**, dry run by default per the house rule. `--email-only` is
  the strictest pass for an operator who does not want name matching at all.
- **Verified against a real Postgres**
  (`backend/verification/verify_admin_mobile_backfill.py`, 53 checks through the
  shipped service: the reported case, a name match where the addresses differ,
  "Nolan, Sarah" reading as "Sarah Nolan", an email match beating a name match,
  the member's number over the linked player's, a read-through player, the Clubs
  Directory contact, the landline refused, two of one name refused while one
  number spelled two ways is not a conflict, an archived member record ignored,
  another club's records never reached, the foreign-player leak, a super admin
  and a club member not counted, an archived club left out, the dry run writing
  nothing and reporting exactly what applying does, and a second run writing
  nothing) **with a control run**: with the org scoping, the mobile check and
  the ambiguity refusal neutered, 7 fail — the leak among them.
- **NOTICED, NOT FIXED**: nothing fills this in at account-creation time. The
  lookup is a plain service call and the obvious follow-up is running it for the
  one club when an admin is created, but that was not what was asked and a live
  hook needs its own look at what happens when the club's records arrive later.

<!-- END original CLAUDE.md L16912-16979 -->

<!-- ADDED AFTER THE SPLIT: verbatim from CLAUDE.md on origin/main (commits 1713803 and db9bb25, v9.100.1). Outside the BEGIN/END markers, so not part of the byte-identical check. -->
## The seasons feed ignores paging, and a full page is not "more" (v9.100.1, Sep 2026)

The second live `pull_club_teasers all --sample 20 --apply` never finished: one
club's `fixturesladders/organisations/{guid}/seasons` was requested at offset
1, 101, 201 ... past 39,000, every call `200 OK`, until the operator killed it.

- **THE ENDPOINT IGNORES BOTH `offset` AND `limit`.** It answers with the club's
  whole history every time; `offset=1`, `101` and `5001` return the same 119
  ids. `get_seasons` ended only on a short page (`len(batch) < limit`), so any
  club with 100 or more seasons looped for ever. The normal sync, `auto_sync`
  and `iq_scout` call the same function, so they were exposed too.
- **A PAGE THAT ADDS NO NEW ID IS THE END**, and the loop is capped at
  `_MAX_SEASON_PAGES` (20) as a backstop. Live check: 119 seasons in 2 calls; a
  stub that really pages (250 seasons) still returns all 250.
- **Same trap as the `links.next` note above**: never trust "the page was full"
  as proof there is another. Dedupe on id.

<!-- END ADDED AFTER THE SPLIT -->

<!-- ADDED AFTER THE SPLIT (2): verbatim from CLAUDE.md on origin/main (commits 92cc83a and aaf227c, v9.100.2). Outside the BEGIN/END markers, so not part of the byte-identical check. -->
## The teaser crawl is paced, not scheduled (v9.100.2, Sep 2026)

Asked for as a steady, throttled load in place of a small batch every 5 or 10
minutes: "an ongoing load, which varies a bit from time to time, rather than a
burst, then a rest, then another burst". The target was the whole directory
pulled inside one Perth day, 05:00 to 22:00.

- **THE ARITHMETIC CAME FIRST.** 17 hours is 61,200 seconds, so the rate that
  finishes N clubs is `clubs x calls a club / 61,200`. At 3,500 clubs that is
  2.0 calls a second at 35 calls a club, 2.9 at 50 and 4.6 at 80. The recommended
  cap was 3 a second. The calls a club costs is still unmeasured across the
  directory (the live checks read 15, 35 and 78), so read `api_calls` off a
  fresh `--sample 20 --apply` before choosing the number.
- **`services/call_pacer.CallPacer` IS THE WHOLE IDEA.** Callers ask for a slot
  and slots are handed out one gap apart. The gap is `1 / rate` scaled by a
  random factor in 1 +/- 0.25, so the RATE IS AN AVERAGE and single gaps are as
  short as 0.75 / rate. It is a pure module (clock, sleep and random source are
  arguments), which is how the arithmetic is checked without waiting.
- **IDLE TIME IS NEVER BANKED.** A slot is never earlier than now, so a pacer
  that sat quiet for an hour does not release an hour of calls at once. That is
  the difference from a token bucket, and it is the property that stops this
  turning back into a burst. The suite mutates it away and reads the result:
  5 checks fail, including 80 calls going out in 0.02s.
- **ONE PACER PER CRAWL, SHARED BY EVERY CLUB IN FLIGHT.** Each club still gets
  its own `LiveAPI` (and its own `calls` counter, which is what
  `club_teaser_snapshots.api_calls` and the work report read), but they are all
  handed the same pacer. Two clubs at a time therefore share one rate. A pacer
  per club would have doubled it.
- **A WORKER, NOT A JOB.** `club_teaser.run_forever` is started at boot from
  `main.py`'s lifespan, held in `_BACKGROUND_TASKS` (a bare `create_task` result
  can be collected the first time it awaits) and cancelled at shutdown. The
  `nightly_club_teasers` cron job and its `OrTrigger` are gone from the
  scheduler. `paced_cycle` is one pass: read the settings, and if the crawl is on
  and inside its hours pull the next 10 due clubs, two at a time. While there is
  work it never sleeps; otherwise it waits (off 60s, outside the hours until they
  open but never more than 300s so a widened window is noticed, nothing due 300s).
  A cycle that raises is logged and followed by a 60s pause, never a hot loop.
- **THE STOP SWITCH AND THE HOURS ARE ASKED BETWEEN CLUBS.** A club in flight
  finishes (about half a minute of calls), so both are honoured to within that.
  Batches are small on purpose: a settings change lands within a couple of
  minutes.
- **A WHOLE CYCLE OF ERRORS BACKS OFF A QUARTER OF AN HOUR** (3 or more clubs and
  not one success). A continuous crawl reaches a broken upstream far faster than
  a cron job did. Each errored club is also already backed off a day by
  `next_pull_at`, so the same clubs are not picked again.
- **OFF UNTIL SOMEBODY SETS IT, AS BEFORE.** `club_teaser_calls_per_second`
  unset means off. Bounds are 0.05 to 10; a stored value outside them reads as
  OFF rather than being clamped up into traffic nobody chose. The hours are
  `club_teaser_window_start` and `_end` (Perth, start inclusive, end exclusive,
  default 5 and 22; a backwards or out-of-range pair reads as the default, and a
  write that would make one is refused). There is no General Settings INPUT yet:
  set them with `PATCH /club-admin/super/general-settings`. **The retired
  `club_teaser_nightly_limit` is left in place and read by nothing, so a club
  that had set it now has the crawl OFF until the rate is set.**
- **PACED PER CALL, NOT PER HTTP REQUEST.** The pacer sits in `LiveAPI._run`, so
  it counts the same calls the "15 to 80 a club" figures count. A stats call can
  page (100 rows a page) and `playhq_client._get_with_retry` retries connection
  failures, so requests on the wire can run a little above the paced rate.
  Pacing inside the two shared clients would count those too; the sync uses both,
  so it was left alone. NOTICED, NOT BUILT.
- **AN UPSTREAM OUTAGE CAN READ AS `empty`, NOT `error`, and the breaker does not
  catch it.** `get_teams` and friends swallow a failure into `[]`, so a pull
  during an outage can be recorded as an empty club and re-looked-at in 14 days.
  Pre-existing, and worth a look before turning the rate up: at 3 a second a bad
  hour reaches a lot of clubs. NOTICED, NOT FIXED.
- **ONE API PROCESS IS ASSUMED**, like every in-process job here. A second
  process would run a second crawl at the same rate.
- **THE WORK REPORT PROJECTS IN CALLS NOW.** The table of batch sizes against
  the 5 minute gap described a schedule that no longer exists. `--apply` ends
  with the calls still to make, the rate that finishes them inside one window and,
  when a rate is known, how long that takes in days of the window. The script
  takes `--rate` to pace a by-hand run with the same pacer.
- **Verified** (`backend/verification/verify_club_teaser_pacing.py`, 86 checks
  against a real Postgres through the shipped pacer, hours logic, cycle, loop,
  settings and General Settings route bodies, with a scripted stand-in for the two
  Cricket Australia client modules so the real `LiveAPI` is what is exercised):
  average rate within 1% over 20,000 draws, no gap outside the jitter bounds, no
  banking, fifty callers in one instant getting fifty slots, the hours at both
  edges and across zones, every refused setting, the cycle in each of its states,
  the hours closing and Stop pressed mid-batch, a trouble cycle, the loop's
  sleeps and its survival of a raising cycle, and a real 10-club crawl at 60 a
  second measured at 58.5 with the worst half second holding 31 calls against 37
  allowed. **Controls**: against the previous commit it REPORTS the feature
  missing; with the pacer skipped 5 fail, with idle time banked 5 fail, with the
  hours ignored between clubs 2 fail. `verify_club_teaser.py` is 91 (one check
  replaced, the schedule checks now describe the worker).
- **A CONTROL THAT CRASHES IS NOT A CONTROL.** The first cut of the measured
  section read `went[-1]` on the list a skipped pacer leaves empty, so the
  mutation died with a traceback and reported nothing. It reports now.
- **NOT RUN AGAINST LIVE CRICKET AUSTRALIA.** The next step is
  `python -m app.scripts.pull_club_teasers all --sample 20 --apply --rate 2` to
  read the real calls a club and the measured rate, then set
  `club_teaser_calls_per_second`.

<!-- END ADDED AFTER THE SPLIT (2) -->

<!-- AMENDED AFTER THE SPLIT: main changed three bullets inside the teaser snapshot section (original L538-640, archived above). The text above is the ORIGINAL wording. Current wording of the three amended bullets, verbatim from origin/main: -->

- **THE PULL RUNS BY DAY, NEVER OVERNIGHT (asked for directly).** **SUPERSEDED in v9.100.2: the cron job described here is now a paced worker (section above). The hours are 05:00 to 22:00 by default and the setting is `club_teaser_calls_per_second`. Never overnight still holds.** Steady
- **OUTBOUND TRAFFIC IS OFF UNTIL SOMEBODY SETS IT.** **SUPERSEDED in v9.100.2: it is off until `club_teaser_calls_per_second` is set; `club_teaser_nightly_limit` is retired.** The job (was: nightly at
- **`--apply` ENDS WITH A WORK REPORT SO A SMALL RUN CAN BE EXTRAPOLATED.** **CORRECTED in v9.100.2: the projection is in calls and the rate that finishes inside one window; the batch-size table against a 5 minute gap is gone.**

<!-- END AMENDED AFTER THE SPLIT -->
