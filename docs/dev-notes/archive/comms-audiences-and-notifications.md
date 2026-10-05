# Archive: comms-audiences-and-notifications

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: BetterComms lists, segments and templates, club notifications, audience rules.
Read the distilled rules first: `docs/dev-notes/guides/comms-audiences-and-notifications.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L1577-1630 -->
## A FACET LISTED IN THE KIT AND MISSING FROM ONE FUNCTION (v9.73.1, Sep 2026)

Reported off `/admin/comms/lists` as `a[r.key] is not iterable`, straight after
an Export to BetterComms added 800+ contacts — so it read as a problem in the
inserted rows.

- **IT IS NOT THE ROWS, AND ESTABLISHING THAT FIRST IS WHAT STOPPED THIS BEING
  CHASED THROUGH THE DATABASE.** `facetOptionsFrom` ends
  `[...opts[f.key]]` for EVERY entry in `FACETS`, and that line runs whatever
  the contacts are. Reproduced with an empty list and with `null`: it throws
  either way. The export was a coincidence of timing — the screen had been
  down since the deploy before it.
- **V8 PRINTS THE SOURCE TEXT OF THE OFFENDING EXPRESSION, which is what makes
  a minified message locatable.** `a[r.key] is not iterable` is
  `opts[f.key]` after minification, and a grep for a spread of a `.key`-indexed
  member (`\.\.\.[a-z]+\[[a-z]+\.key\]`) returns **exactly one match in the
  whole frontend**. Reach for the expression's shape, not for the variable
  names.
- **THE CAUSE IS A SECOND HAND-WRITTEN COPY OF THE FACET LIST.** `FACETS`
  gained `role` in migration 295's commit; `facetOptionsFrom` built its `opts`
  from a hardcoded five-key literal written before `role` existed, so
  `opts.role` was undefined. **This is the trap this file already records one
  function over** — `CommsLists.jsx`'s own `noFilters` literal, fixed in
  v9.70.0 by aliasing it to `emptyFilters`. The same commit that fixed it there
  introduced it here.
- **TWO CRASH PATHS, AND ONLY ONE OF THEM NEEDS DATA.** The spread throws
  unconditionally; `opts[f.key].add(...)` throws `Cannot read properties of
  undefined (reading 'add')` only once a contact actually carries a role, which
  is what the exported directory rows brought. The control run reports both.
- **A COMMENT CAN DESCRIBE BEHAVIOUR THE FUNCTION CANNOT DELIVER.** The note
  added beside `role` said "facetOptionsFrom only offers a facet that actually
  has values, so it never appears for them" — true of the intent, and the
  function threw before it could offer anything. It is true now.
- **BOTH SHAPES ARE DERIVED FROM `FACETS` NOW, mirroring `emptyModes`**, which
  had this right all along (`Object.fromEntries(MODE_FILTERS.map(...))`). A
  facet added later reaches the filter shape, the options builder and the
  matcher with no second list to keep in step.
- **Verified** (`frontend/verification/verify_comms_facets.mjs`, 11 checks
  against the SHIPPED functions lifted out of the file rather than retyped: an
  empty and a null contact list, a club contact carrying no directory fields,
  every `FACETS` key present in both shapes, role options collected and
  de-duplicated, a facet nobody carries staying empty so it is never offered,
  and the filter it then drives) **with a control run**: 7 of the 11 fail
  against the previous commit, reporting the customer's own
  `opts[f.key] is not iterable`.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN, hit again here.** The
  first cut read `facetOptionsFrom(exported)` into a `const` at module level,
  so the control died on it and said nothing about the four checks below.
  Every read goes through the guarded `check()` now.
- **NOTICED, NOT FIXED**: nothing asserts that a key added to `FACETS`,
  `MODE_FILTERS` or the engagement filter reaches every consumer — the check
  here covers `FACETS` only, and a structural sweep over the kit would be its
  own change.

<!-- END original CLAUDE.md L1577-1630 -->
<!-- BEGIN original CLAUDE.md L2701-2886 -->
## A club decides what it is told about (migration 288, v9.69.0, Sep 2026)

Asked for as a configurable notification system a club admin manages — emails
first, the in-app bell alongside them, room for other channels later — covering
milestones past and upcoming and "other events club admins should be aware of",
with a per-admin opt-out and a club-wide off switch. Then, mid-build, the case
that decided the shape of the settings: volunteer and official certifications
(Working With Children, RSA, first aid) tracked for currency, **with the notice
period before expiry left for the club to define**.

- **THE CATALOGUE IS CODE, THE CHOICES ARE DATA, and that split is the whole
  design.** Every event needs a source that can find it, so a row in a table
  describing an event nothing can produce would be a promise the platform
  cannot keep. `services/notification_events.EVENT_TYPES` is the list; adding
  one means an `EventType` there AND a source in `notification_scan.SOURCES`.
  The settings screen is drawn from that list, so nothing else needs editing —
  and the suite asserts the two sets match, so a half-added event fails rather
  than appearing on screen and doing nothing.
- **A CLUB WITH NO ROWS BEHAVES EXACTLY AS THE REGISTRY DECLARES.** Nothing is
  written until somebody changes something, which is what lets a default be
  changed in code with no backfill and no club silently keeping an old one. The
  same call `organisations.stats_min_rate_innings` makes with NULL.
- **THE NOTICE PERIOD IS PER EVENT, NOT PER CLUB, and the report is why.** A
  Working With Children renewal takes weeks to come back and a first aid
  refresher is a weekend, so one club-wide "warn me N days ahead" would have to
  mean two things at once. `EventType.config_fields` declares the numbers an
  event owns, with bounds enforced server-side — an out-of-range value is
  CLAMPED rather than refused, because the alternative is a source silently
  reading a lead time of -5 and looking backwards through time.
- **AN ALREADY-LAPSED CERTIFICATE IS RAISED WHATEVER THE NOTICE PERIOD.** It is
  the most urgent case there is, and a club switching this on should hear about
  the ones already expired rather than only the ones about to. Verified both
  ways: narrowing the period drops the one now out of reach and keeps the
  lapsed one.
- **EVERY DEDUPE KEY NAMES THE FACT, NEVER THE RUN THAT NOTICED IT.**
  `milestone:<player>:runs:5000` is true forever; a certificate's key carries
  its expiry DATE, so **renewing it creates a genuinely new fact to warn about
  next time and an unchanged one is raised exactly once**. That is what lets a
  source re-report everything it can see on every pass and let the unique index
  on `(organisation_id, dedupe_key)` decide what is new — a read-then-write
  check would race a manual scan against the nightly one.
- **THE ONE EXCEPTION IS LOW STOCK, AND IT IS DELIBERATE.** Standing state, not
  an event: keying on the variant alone would mention it once ever and then
  never again, keying on the day would nag. The ISO week is in the key, so it
  is a weekly reminder while it lasts.
- **SIX CONDITIONS, ONE FUNCTION.** `notifications.channel_allowed` is the
  whole subscription decision — the club's kill switch, the channel's club-level
  switch, the event's own switch, that channel on that event, and the person's
  opt-out — plus the two that need the database (the module gate, and the
  recipient's capability). Two copies of this is how the settings screen and the
  scan start disagreeing about whether a club is subscribed to something. Each
  of the six is asserted failing closed on its own.
- **AN OPT-OUT SILENCES; IT NEVER SWITCHES SOMETHING ON.** A person can stop a
  channel the club has turned on, and cannot turn on one the club has turned
  off. `event_key = '*'` (`ALL_EVENTS`) is the whole-club opt-out, checked as a
  floor under every event.
- **CAPABILITY IS A FILTER ON WHO IS TOLD, NEVER ON WHO MAY CONFIGURE.** A
  report awaiting approval reaches the people who can approve one, the rule the
  bell already applied. Choosing what lands in your OWN inbox is deliberately
  not gated on `MANAGE_SETTINGS` — an admin who cannot edit the club's branding
  is still entitled to stop being emailed.
- **RECIPIENTS ARE `club_admin` AND `club_member`, and the second half is not an
  oversight.** A club_member is somebody the club gave admin-app access to with
  an explicit allowlist — the volunteer coordinator holding
  `MANAGE_QUALIFICATIONS` is exactly who should be told a WWCC is lapsing.
  `admin_contact_list.admin_rows` correctly uses `club_admin` alone because it
  answers a DIFFERENT question (who administers a club, for BetterCricket's own
  outreach); reusing it here would send a club's compliance warnings past the
  person whose job it is. **Found by the verification** — the first cut reused
  it and the capability check came back empty.
- **A super_admin or sales membership is never a recipient.** That is
  BetterCricket's own staff, and staff acting as a club must not be emailed that
  club's milestones.
- **ONE DIGEST PER RECIPIENT, NOT ONE EMAIL PER FACT.** Three milestones and a
  lapsing WWCC are one email — the call `trial_lifecycle` already makes, and the
  difference between a system people read and one they filter. A delivery is
  marked sent only once the provider has accepted it, so an outage retries
  tomorrow rather than silently dropping a certificate; a refusal is recorded
  with its reason ON THE ROW, which is what makes "they say they never got it"
  answerable months later.
- **A FIRST RUN IS CAPPED** (`MAX_PER_EVENT`). An established club switching
  this on has a decade of history in reach of the sources; without a cap one
  club's backlog fills a table and an inbox.
- **THE `sync_completed` EVENT DEFAULTS TO THE BELL AND NOT THE INBOX**, and a
  sync that brought nothing in is not raised at all. A notification system that
  emails "nothing changed" every morning is one nobody reads within a fortnight.
- **A CHANNEL IS TEXT, NOT A COLUMN.** Adding SMS or push later is a value in
  `notification_events.CHANNELS` plus a sender — no migration on a live table,
  and a channel absent from an event's `default_channels` map is OFF, so a new
  one is opt-in rather than switching itself on for every club overnight.
- **THE BELL WAS SUPER-ADMIN-ONLY, WHICH WOULD HAVE MADE THE IN-APP CHANNEL
  REACH NOBODY IT IS FOR.** Both the `NotificationBell` and the
  `NotificationModal` were gated on `role === 'super_admin'` in `AdminLayout` —
  a gate from when the panel was internal that outlived its reason, the same
  shape v9.6.1 removed from the BetterClubhouse screens. Safe to lift because
  the gate was never the real check: every endpoint behind it is club-scoped
  through `get_current_club` and refuses nothing on role (`PRIVILEGED_ROLES`
  only ever WIDENS a capability check there). **They were two separate gates,
  and lifting one and not the other leaves a bell that opens nothing** — the
  suite asserts the panel actually opens, not merely that the bell renders.
  Auto-open on login stays staff-only: opening a panel over a club admin the
  moment they log in is a different decision from giving them the bell.
- **`services/session_safety.rollback_keeping` is now the ONE definition**,
  lifted out of `routers/admin.py` (which delegates). A bare `rollback()`
  EXPIRES every instance the request's own dependencies loaded, and the next
  plain attribute read on one is a lazy refresh that raises a greenlet error a
  long way from the swallowed failure — the v9.53.5.1 trap. Found here by the
  verification hitting it in its own harness.
- **`clean_config`'s FALLBACK DIRECTION IS LOAD-BEARING, and the first cut had
  it backwards.** A SAVE passes the club's current config as the base, so
  typing nonsense into the notice period leaves what they had set alone; a READ
  passes nothing, so a stored value gone bad falls back to the registry default,
  which is the only other thing it could mean. Getting it the wrong way round
  quietly reset a club's own setting on the next save — **found by running it**.
- **Verified against a real Postgres**
  (`backend/verification/verify_notifications.py`, 103 checks through the
  shipped services and route bodies: the DDL applied three times, alembic and
  the lifespan mirror running the same shared list, the registry defaults for a
  club with no rows, every source, the retired milestone threshold never
  announced, a second scan announcing nothing twice, the notice period at both
  ends and a renewal as its own fact, all four switches failing closed
  separately, the capability and module gates both ways, an opt-out per event
  and whole-club, one digest per recipient marked sent only on acceptance, a
  refusal recorded and retried, the weekly cadence on and off its day, the feed
  and mark-read scoped to one person and one club from both sides, and every
  route body incl. three refusals and a malformed id as a 400) **with two
  control runs**: with the services absent it REPORTS the feature missing rather
  than dying on an ImportError, and with the capability gate, the opt-out and
  the retired-threshold filter neutered, 7 of the 103 fail on exactly those
  three behaviours.
- **Driven in Chromium** (`frontend/verification/verify_notifications_browser.mjs`,
  48: the exact params on the wire for every control — a channel toggle sending
  that channel ALONE rather than the whole rule back, an event switch sending
  `enabled` alone, the notice period sending `config` alone and only when it
  changed, the personal opt-out going to the preferences endpoint and never to
  the rule endpoint that would change it for everybody — a club without the
  Settings permission still choosing its own inbox, an event that does not reach
  this person offering no personal toggle, Check now never emailing anybody, and
  the bell opening and its rows linking) **with a control run** that reports the
  screen absent rather than dying on the first missing locator.
- **THREE CHECKS COULD NOT HAVE FAILED AS FIRST WRITTEN.** "The panel offers a
  way to the settings screen" matched the SIDEBAR nav item, which is on every
  admin page and there whether the modal opens or not — it is scoped to the open
  panel now. And two locators were written in the source's casing against
  CSS-`uppercase` text, which `innerText` returns transformed: the trap this file
  already records, hit twice in one suite.
- **`uncheck({ force: true })` VERIFIES THE NEW STATE ONCE AND THROWS.** With
  `force` Playwright skips its retry loop, and these toggles only settle after a
  round trip (PUT, then a reload of the whole payload). Click and wait instead.
- **NOTICED, NOT BUILT**: nothing prunes old notifications — a club's record of
  what it was told is not something a nightly job should quietly delete, and a
  retention rule is a decision for a person. There is no per-event digest
  frequency (the cadence is club-wide), no SMS or push (a channel and a sender
  away), and the AFL silo is untouched. `member_reminders` still emails the
  MEMBER about their own lapsing qualification through the member portal — a
  different audience from this, and deliberately left alone.

### Certificate stages, grade milestones and a test email (v9.89.0, Sep 2026)

- **A CERTIFICATE WAS ANNOUNCED ONCE AND NEVER AGAIN, LAPSE INCLUDED.** Now three
  stages, each its own dedupe key: notice (the ORIGINAL unsuffixed key, so a
  certificate already announced is not re-announced), `:final` (`final_days`,
  0 = off) and `:lapsed` (severity `urgent`, via `emit(severity=...)`). Only the
  CURRENT stage is raised. A pre-stage notice is read by its payload's
  `days_remaining` so the stages it already covered are not repeated.
- **Left out on purpose**: a certificate superseded by a newer record of the same
  type for the same person (later expiry, or none), an archived member, a retired
  type, and anything lapsed longer than `lapsed_days` ago. The old
  `ORDER BY expires_at LIMIT 40` served forty certificates from years ago first.
- **Grade milestones** (`milestone_scan.grade_milestones`): grade = name folded
  through the club's active `grade_merge_logs`, label = the club's display
  override, active players only, bound as a `uuid[]` (never a subquery). "Reached"
  = crossed in the last `LOOKBACK_DAYS` by scorecard date. A player with a record
  in only one grade is skipped, judged across ALL stats (a per-stat check dropped
  a batter whose runs sat in one grade). Upcoming needs a game in that grade since
  the active cutoff. Both events share one pass via `session.info`.
- **`scan_org` used a bare rollback after a failing source**, which expired `org`
  and crashed the rest of the club's scan with MissingGreenlet. `rollback_keeping`.
- **Console is not a send in `dispatch_emails` either** (the sales-email rule): with
  no provider the deliveries stay pending. `POST .../settings/test-email` sends the
  caller alone a `[Test]` digest of the club's recent notifications, never touches
  a delivery, 5 per 10 minutes. `my_last_email` on the settings payload reads the
  delivery record.
- **Verified**: `verify_notifications.py` 146 (control: 20 fail),
  `verify_notifications_browser.mjs` 56 (control: 7 fail).

<!-- END original CLAUDE.md L2701-2886 -->
<!-- BEGIN original CLAUDE.md L8316-8369 -->
## One CRUD shape for Emails, Lists, Segments and Templates (v9.17.0, Aug 2026)

The four Comms records are the same kind of thing — a club has several, picks
one, works on it, saves or deletes it — and had four different answers to that.
Segments had the best one, so it is now the pattern and the other three sit on
it. **Frontend only: no endpoint, payload, capability or route changed.**

- **`pages/admin/clubhouse/crudShell.jsx` is the pattern**, and a new Comms-style
  screen should be built from it rather than inventing a fifth layout:
  `CrudPanes` (the two panes), `RecordListPane` (the left rail — flat `items`, or
  labelled `groups` for records that come from more than one place),
  `DetailPane`, `RecordTitleRow` (the name edited where it is read, actions
  beside it), `CountBar`, `SaveRow`, plus `reachability`, which moved here from
  `segmentEngine` because three screens now report reach the same way.
  `segmentEngine`'s `SegmentListPane`/`SegmentTitleRow` are thin wrappers over
  it and `CountBar`/`reachability` are re-exported, so both segment screens'
  imports are untouched.
- **Emails is ONE screen on two URLs.** `/admin/comms` and `/admin/comms/:id`
  both render `CommsCampaigns`; `CommsCompose` exports `EmailDetail`, which
  draws no layout of its own and lives in the right pane. The URL did not
  change, so every "Email these N now", the Roster's link and any bookmark
  still land on the right email. The composer is `lazy()` inside the shell, so
  glancing at the list does not pull in the HTML editor. **Deleting a SENT
  email moved from the list row to the email itself** — it was the one thing
  the old compose page could not do, and dropping it would have lost a real
  capability.
- **The subject is the email's title row**, not a field in the body: it is the
  email's identity the way a name is a segment's. Name and description stay as
  their own fields, since they label it for the club's own records. This is why
  **`TextInput` forwards its ref** now — the Insert bar places a merge variable
  at the cursor in the subject, so it needs the real input.
- **Lists kept every filter, bulk action and modal** it had; only the shell
  changed. Rename is the name field, "Manage" is simply what the right pane
  always shows, and Export CSV / "Email these N now" appear once, on the record.
  Enter in the name field still creates a list (`RecordTitleRow`'s optional
  `onSubmit`), which is what the old create box did.
- **A draft is only ever LOADED, never cleared, by the selection effect** — the
  trap `useSegments` already documents. Clearing on "nothing selected" is
  exactly the state "New list" / "New template" puts the screen in, and would
  wipe the fresh draft in the same commit.
- **`EmailEditorTabs` seeds its design iframe once on mount**, so Templates
  bumps an `editorKey` whenever the HTML is replaced wholesale (a different
  template picked, a file imported) — same reason Compose already did.
- **Emails, Lists and Templates now get screen introductions** (`INTROS.emails`
  was written and unused; `lists` and `templates` are new). Emails passes a
  `null` key when a `:id` is present, so a deep link to one email never opens an
  introduction first.
- **Verified in a real browser** (Chromium, the app on the dev server with the
  API stubbed at the network layer): all six screens render with data, no page
  errors, no horizontal overflow at 390px, and the state transitions a
  screenshot cannot reach — switching records, New list / New template / New
  segment, typing a name, opening a sent email and a draft, and Send enabling
  once subject, message and audience are all present.

<!-- END original CLAUDE.md L8316-8369 -->
<!-- BEGIN original CLAUDE.md L13844-13888 -->
## BetterComms — HTML / Design / Preview editor (Jul 2026)

Template (`CommsTemplates.jsx`) and Email compose (`CommsCompose.jsx`) both used
to be a plain `<textarea>` + a read-only iframe. Both now share one editor,
`frontend/src/components/admin/EmailEditorTabs.jsx`, with three modes: **HTML**
(the textarea), **Design** (WYSIWYG), **Preview** (unchanged — server-rendered
`srcDoc` iframe, footer injected, exactly what a send produces).

- **Design mode edits the real DOM, not a schema.** Real templates are
  table-based layouts (`role="presentation"`, `cellpadding`, inline styles) for
  email-client compatibility — a schema-based rich-text library (TipTap/Quill/
  Slate) normalises content into its own document model and would strip or
  rewrite that markup on round-trip. Instead Design mode writes the current HTML
  into an iframe and sets `contentDocument.designMode = 'on'`, so the browser's
  native editing operates on the actual markup; the toolbar calls
  `execCommand` on that document. Reading the content back out
  (`serializeIframeDocument`) gets back real HTML, tables and all, modulo the
  user's own edits (browsers do normalise bare `<tr>` into an implicit `<tbody>`
  on any DOM parse — cosmetic, doesn't affect rendering).
- **Fragment vs full-document is auto-detected and preserved**
  (`isFullHtmlDoc` in `lib/htmlEmailFormat.js`, mirrors the backend's
  `_is_full_doc`). A full document (`<html`/`<body>` present — a pasted/imported
  template) edits and serializes as a full document. A fragment (a plain-text or
  simple-HTML compose body) is wrapped in a throwaway shell just for the Design
  iframe's visual editing surface (`wrapFragmentForEditing`) but only the
  fragment's inner content is read back out — so the backend's auto-wrap (club
  shell + mandatory footer) for compose bodies keeps working untouched after a
  round trip through Design mode.
- **Tidy-on-switch**: `js-beautify`'s HTML formatter (`tidyHtml`) reformats the
  code whenever a mode transition, Save, Test or Send happens with pending
  edits — leaving HTML mode always shows clean, indented markup, whether the
  edits came from raw code or from Design mode. Verified against a real
  table-based template that indentation doesn't introduce visible whitespace
  (inline elements like `<a>` inside a `<p>` are left untouched).
- **`ref.flush()` is mandatory before persisting.** `EmailEditorTabs` is a
  `forwardRef` exposing `flush()`, which synchronously returns the latest
  content (Design-iframe edits read back and tidied, or tidied code) — every
  Save/Send/Test call site must use its return value directly rather than the
  `html`/`body` state variable, since the `onChange` callback's state update
  hasn't necessarily landed yet by the time the API call fires. A debounced
  (400ms), untidied live-sync also runs while typing in Design mode so
  Send-button enablement and the unknown-`{{variable}}` warnings don't lag.
- **No backend change** — tidying happens entirely client-side before the
  existing `html`/`body_html` string fields are saved.

<!-- END original CLAUDE.md L13844-13888 -->
<!-- BEGIN original CLAUDE.md L15738-15771 -->
## Notification Centre (v7.7.3, May 2026)

Bell icon in the AdminLayout header + drop-down panel that auto-opens on login when there's something new.

**Architecture** — no dedicated notifications table:
- `User` model gains `last_notification_seen_at TIMESTAMP` and `last_seen_app_version TEXT` (migration `029`).
- Three endpoints under `/club-admin/notifications/`:
  - `GET /count` — cheap badge poll (runs every 60s). Counts sync runs + milestones + pending sync requests since last seen. Returns `{ unseen_count, last_seen_version }`.
  - `GET /summary` — full data fetched only when the modal opens. Returns sync runs, new milestones, upcoming milestones (top 5), pending count.
  - `POST /seen` — sets `last_notification_seen_at = now()` and `last_seen_app_version = <passed version>`.
- "Since last visit" window defaults to 14 days if user has never dismissed notifications.

**Feature Changelog** (`frontend/src/data/changelog/`):
- One file per release, Vite glob-imported and sorted by `sortKey` desc in `index.js`. Each file default-exports `{ version, date, sortKey, title, items[] }`.
- `SITE_VERSION` (in `frontend/src/version.js`) is derived from `CHANGELOG[0].version` — never hand-edited. `Navbar.jsx` still re-exports it for backwards compat.
- The bell computes `newChangelogCount` (entries with version > `last_seen_version`) client-side and adds it to the backend `unseen_count` for the badge.
- Auto-open on login fires if `unseen_count > 0 || any changelog entry is newer than last_seen_version`.

**Adding a new changelog entry**: drop a single file in `frontend/src/data/changelog/`, e.g. `v1-0-5-beta.js`:
```js
export default {
  version: 'v1.0.5 Beta',
  date: '2026-05-29',
  sortKey: '2026-05-29T12:00:00Z', // any ISO string > current top entry; `new Date().toISOString()` works
  title: '...',
  items: ['...'],
}
```
Branches never touch a shared file, so parallel work merges cleanly. `index.js` re-sorts on every build — whichever PR ships latest naturally becomes `CHANGELOG[0]`.

**Open follow-ups worth investigating**:
- `deep_sync_player` (admin-triggered per-player resync via PHQ Partner API) still has a UI surface but is low value now that Grassroots covers all seasons including 25/26. Could be retired or repointed at GR. Low priority — no data pollution.
- Season-alias URL redirects: visiting `/yearbook/{alias_season_id}` still loads the alias's hidden yearbook record + alias-only stats. The stats queries auto-expand when visiting the canonical URL, but no redirect from alias URL → canonical URL exists yet. Old bookmarks to merged-away seasons are the corner case.

<!-- END original CLAUDE.md L15738-15771 -->
<!-- BEGIN original CLAUDE.md L16616-16672 -->
## Naming a club or a contact outright (v9.58.3, Sep 2026)

Asked for on the internal Segments screen straight after the rules above:
explicitly include or exclude every contact at a specific club, or specific
contacts.

- **THEY ARE ORDINARY ANDed RULES, NOT UNION-STYLE OVERRIDES, and that is the
  one design decision here.** `is any of` NARROWS the audience to what is
  picked; it does not add those people on top of what the other rules matched.
  The exclude half — the one this was really asked for — is identical either
  way, and a union INCLUDE could send to somebody an earlier rule had
  deliberately left out, which is the worse direction to be wrong in. The suite
  asserts the narrowing against a second rule rather than checking the field in
  isolation.
- **NEITHER JOINS THE MARKETING CLUB, and that is what makes the exclusion
  correct.** `marketing_club_id NOT IN (…)` is NULL for a contact with no
  directory club, which SQL reads as not-matching — so a naive "is none of club
  X" silently drops every hand-added contact as well. `_pick_clause`'s
  `nullable` argument ORs `IS NULL` back in on the exclude side, and an inner
  join would have thrown them away before the clause was even reached. The
  suite pins both: the excluded club's contacts gone, the club-less ones kept.
- **A JUNK ID IS DROPPED, BUT AN ALL-JUNK VALUE MUST NOT THEN READ AS "NO
  FILTER" any more loosely than an empty one does.** An empty selection drops
  the rule, the same as every other multi-value field — a picker nobody has
  chosen from yet must not empty the audience. Unlike the `_DIR_MC_FIELDS`
  rules, an unpicked rule here does not narrow to directory-linked contacts
  either, since there is no join to do it.
- **THE SERVER SEARCHES; THE DIRECTORY IS NEVER SHIPPED TO THE BROWSER.**
  `GET /segments/entities?kind=club|contact&q=&ids=` is the same call
  `PersonSearch` makes, and it does two jobs in one because they answer one
  question — what is this id called. `ids` is answered WHATEVER `q` is, so a
  saved rule renders its chosen names before anybody types and a chosen row can
  still be un-picked once the search box has moved on. Everything is scoped to
  the acting org's own contacts, so a club id off a browser can only ever name
  a club this org actually holds contacts for.
- **A response is DROPPED if the box has moved on**, per the `PersonSearch`
  rule — a slow search for "sm" must not land on top of the results for
  "smith".
- **The endpoint carries the same scope guard as the engine** — a club build is
  refused outright rather than being handed a searchable list it could never
  build a rule from.
- **Verified against a real Postgres**
  (`backend/verification/verify_primary_admin_segment.py` is 74 checks now:
  naming one club and two, the exclusion keeping the club-less contacts, one
  contact both ways, the narrowing composed with another rule, a junk id
  dropped while the real one still applies, an empty and an all-junk value
  filtering nobody, and the endpoint searching, hydrating a chosen id under a
  non-matching query, never offering another org's contacts, and refusing an
  unknown kind and a club build) **with a control run**: 17 fail against the
  previous commit, every naming rule matching the WHOLE audience rather than
  narrowing it — which is the failing-open direction the checks exist to catch.
- **A CHECK THAT COMPARES TWO WIDENED SETS CANNOT FAIL.** "a junk id is
  dropped, the real one still applies" passed against the broken code on the
  first cut, because both sides came back as everybody; it asserts the narrowed
  set is genuinely narrower now. The endpoint import is guarded so a control
  run reports it absent rather than crashing the rest of the suite.

<!-- END original CLAUDE.md L16616-16672 -->
<!-- BEGIN original CLAUDE.md L16673-16755 -->
## Targeting the clubs nobody at the club ever ran (v9.58.0, Sep 2026)

Asked for on the internal Segments screen: a rule for whether a club's Primary
Club Admin is blank, so the contacts at a club a super admin created or synced
and no real person ever took over — in practice a test club — can be included
in a List or Segment, or left out of one.

- **THREE STATES, NOT A YES/NO, AND THAT IS THE WHOLE DESIGN.** "No primary
  admin" is true of two completely different things: a club on the platform
  that nobody ever took over (the test club) and an ordinary PROSPECT, which
  has no club record to have an admin at all. A yes/no would fold them
  together, and "exclude the clubs with no primary admin" would then quietly
  drop every prospect in the directory — almost the entire outreach audience.
  `assigned` / `unassigned` / `not_onboarded` keep them apart.
- **A MULTI-SELECT IS WHAT MAKES *EXCLUDE* EXPRESSIBLE.** Rules are ANDed and
  there is no NOT, so a single-select could only ever include. The three states
  PARTITION every directory club, so picking `unassigned` targets the test
  clubs and picking the other two leaves them out. The suite asserts the
  partition — the union of the three equals the whole audience with no overlap —
  rather than checking each in isolation. Same `input: 'multi'` shape
  `had_demo` and `is_trialing` already use.
- **`unassigned` IS "NOBODY IS THE PRIMARY", NOT "NOBODY IS AN ADMIN".** A club
  with a `club_admin` who was never made primary still reads as unassigned,
  because the question is who owns the club relationship. A `club_member`
  membership can never be the primary at all.
- **The predicate is the two conditions `trial_engagement.org_has_primary_admin`
  already uses** (`role='club_admin'` AND `is_primary_admin`), expressed as a
  correlated EXISTS. The suite runs both over every seeded club and asserts they
  classify it the same way, rather than taking the mirroring on trust.
- **`existing_org_id` is `ON DELETE SET NULL`**, so "not NULL" reliably means an
  org row exists and `not_onboarded` needs no second EXISTS to confirm it.
- **A selection that resolves to nothing behaves exactly as the existing club
  rules do** — the condition is dropped but the MarketingClub join still
  applies, so the audience narrows to directory-linked contacts and no further.
  The check compares it against `had_demo` on the same data rather than
  asserting a rule of its own.
- **WON, AND ANYTHING BUT WON (v9.58.1), asked for straight after.** Won / not
  won is a clean PARTITION of every directory club, so unlike the three-state
  rule above it needs no multi-select: one single select answers both
  directions.
- **WON-NESS COMES FROM THE STAGE, not `crm_deals.status`** — the same rule
  `sales_commissions.deal_state` follows, and for the same reason: every writer
  derives status from the stage so the two normally agree, but the live data has
  rows where they disagree and the stage is what a reader sees on the board. The
  suite seeds both contradictions and asserts the stage wins each way.
- **SCOPED THROUGH THE STAGE'S OWN PIPELINE, never `crm_deals.scope`.** A club's
  own CRM deal — a sponsorship renewal, a grant — must never read as
  BetterCricket having sold them something, and the pipeline is the authority on
  whose board a stage belongs to.
- **AN ARCHIVED DEAL IS OFF THE PIPELINE, so off this rule**, which is what
  every other CRM read does, the commission report included. The one documented
  exception (`_last_attributed_deal_for_club`, which keeps archived deals so an
  upsell inherits its rep) is about who EARNED a club, a different question from
  where the club sits now.
- **A VOCABULARY VALUE IS MATCHED CASE-INSENSITIVELY (v9.58.2), and the failure
  mode is why it matters.** An unrecognised value drops the CONDITION, so a rule
  saying `WON` did not narrow to the won clubs — it WIDENED the segment to
  everyone. Failing open on a capital letter is the worst direction there is for
  an email audience. `_vocab` / `_vocab_list` fold the case for `deal_won`,
  `primary_admin` and `trial_status`; the picker only ever writes the lowercase
  key, but a saved segment or a hand-made request can carry anything.
- **THE STAGE'S NAME AND KEY NEVER ENTER THE TEST.** Won-ness reads
  `crm_stages.is_won`, a boolean, so a stage called "won", "WON" or "Closed Won"
  behaves identically — that half was never case-sensitive, and the suite pins
  it by renaming the stage mid-run.
- **Deliberately only two options.** `crm_stages` also carries `is_lost`, so
  open / lost / no-deal could each be their own state — but that is not what was
  asked, and "anything but Won" is the useful counterpart to "Won".
- **Verified against a real Postgres**
  (`backend/verification/verify_primary_admin_segment.py`, 33 checks through the
  shipped segment engine: each state on its own, the reported case found, the
  prospects NOT swept in with it, the exclude built from the other two, the
  partition, an admin who is not primary, a plain member, another club's primary
  not counting for this one, a contact with no directory club matched by no
  state, and the scope guard still refusing a club that names it; plus Won
  finding only the club that bought, a club's own won deal not counting, an
  archived one not counting, "anything but Won" covering open / lost / no deal
  at all, the two states partitioning, and a status/stage contradiction resolved
  by the stage both ways) **with a control run**: with the change reverted the
  unknown field is dropped entirely, so every rule matches the whole audience,
  and with only the case folding reverted `"Won"` matches all six seeded clubs
  against `"won"`'s one.

<!-- END original CLAUDE.md L16673-16755 -->
<!-- BEGIN original CLAUDE.md L16756-16804 -->
## How many clubs an audience reaches (v9.57.0, Sep 2026)

Asked for on BetterCricket's internal BetterComms: the live readout under a
List and under a Segment says "79 contacts match · 79 reachable by email" —
add the number of distinct clubs behind it.

- **A CLUB IS THE CONTACT'S LINKED DIRECTORY ROW, so the figure SELF-GATES.**
  Only a BetterCricket outreach contact carries a `marketing_club_id`; a club's
  own members have none, so the count is 0 there and the readout simply does not
  draw it. That is why no context flag had to be threaded anywhere — the same
  call `ageFilterOptions` and the Fees/Training notes make, that a control which
  can only ever answer one thing is worse than none.
- **COUNTED AMONG THE REACHABLE CONTACTS, per the ask.** The question is how many
  clubs an email would actually land at, not how many are represented in the
  match.
- **`/segments/resolve` CAPS ITS CONTACT LIST AT 5000 AND ITS COUNT IS EXACT**,
  so deriving the figure in the browser from that slice would stop at the cap and
  contradict the count beside it in the same sentence. `audience_figures`
  computes it server-side over the WHOLE audience. **`reachable` and
  `other_route` moved there too** — they were derived from the capped slice and
  had the same silent under-report; three numbers in one sentence have to be
  measured the same way. The browser prefers the server's figures and keeps the
  old client-side derivation only as a fallback for an older server mid-deploy.
- **THE LISTS SCREEN NEEDS NO SERVER FIGURE**, because
  `GET /lists/{id}/members` returns every member uncapped and each row already
  carries its club link. `clubCount` in `crudShell.jsx` is that one rule, used
  there and as the segment fallback; `routers/comms.py::audience_figures` mirrors
  it, and the suite runs the REAL JavaScript function (lifted out of the file and
  evaluated in node) against the Python one on the same rows rather than checking
  the source for a phrase — a structural check would pass on a rule that behaved
  differently.
- **A blank address is matched but not reachable, and so contributes no club.**
  `comms_contacts.email` is NOT NULL but a blank one is storable, and it is not a
  person an email reaches.
- **Verified against a real Postgres**
  (`backend/verification/verify_audience_clubs.py`, 19 checks through the shipped
  route bodies: three officers at one club counting once, a club whose only
  contact is unreachable not counted, a contact belonging to no club inventing
  none, a club's own audience reporting 0, 6001 contacts across 6000 clubs all
  counted so the cap is proved not to apply, the list endpoint returning
  everything uncapped, and the two languages agreeing on the awkward cases)
  **with a control run**: with the frontend reverted, 7 fail and the JS rule is
  reported absent rather than crashing the suite.
- **A LIFESPAN-ONLY COLUMN OR TABLE BREAKS A `create_all` HARNESS**, and this
  route body reaches three of them through `reconcile_contacts_from_directory`:
  `fee_members.member_category`, `member_membership_types` and
  `player_achievements`. The suite creates them by hand, per the note this file
  already carries about raw-SQL tables being invisible to the ORM.

<!-- END original CLAUDE.md L16756-16804 -->
<!-- BEGIN original CLAUDE.md L16805-16911 -->
## Every club admin, on one internal list (v9.56.0, Sep 2026)

Asked for: a club admin should land on BetterCricket's own contact list the
moment they become one — a self-serve registration, a super admin creating a
club and naming its primary admin, a primary admin being reassigned — plus a
script that backfills everyone who is already one.

- **THE PRIMARY ADMIN IS NOT A ROLE, IT IS A FLAG.** `club_memberships.role` is
  `club_admin` and `is_primary_admin` rides on top, so "Club Admin or Primary
  Club Admin" is one query. The ongoing sync therefore covers every
  `club_admin`, not only the primary — otherwise the backfill seeds ordinary
  club admins once and nothing ever maintains them, and the list drifts the
  first time a club adds a second admin.
- **`services/admin_contact_list.py::sync` IS THE WHOLE JOB, and the live hooks
  and the backfill script are the same code over different scopes** — one club
  or the platform. That is what makes it idempotent enough to run on every
  membership write, and what stops the script and the hooks disagreeing about
  who belongs.
- **IT RUNS ON ITS OWN SESSION, AFTER THE CALLER'S COMMIT, AND NEVER RAISES.**
  A marketing-list failure must not take down a club registration — and it must
  not share the caller's transaction either, which is the trap this file already
  documents twice: a swallowed database error leaves the transaction aborted and
  the commit that actually matters fails behind it. `run_sync` is that rule
  named; `queue_sync` fires it where the caller has its own post-commit point,
  and `background_tasks.add_task(run_sync, …)` where the commit happens after the
  code returns (`sales_workspace._nominate_primary_admin`, whose caller commits).
- **CALL IT AFTER THE COMMIT.** The task reads its own session, so a hook fired
  mid-transaction finds no membership and quietly does nothing — the one way
  this can silently fail at its job. The suite asserts it structurally: every
  hook line must have a `commit()` between it and the top of its own enclosing
  function. A 12-line lookback passed `create_club`, whose commit sits 20 lines
  up behind a long `except` block.
- **UPSERT ONLY — nothing here removes anybody.** Losing the role does not take
  a person off the list; that is a decision for a person on the Lists screen.
- **AN OPT-OUT IS NEVER OVERRIDDEN, and that is not the same as skipping the
  contact.** An unsubscribed / bounced / complained / globally-suppressed admin
  still has their contact row kept current, but is NOT put back on the list —
  `comms_lists` drops a suppressed contact from every list, and re-adding them
  here would fight it on every run. `comms_segments.sendable_where` is the one
  definition of "can be sent to" and is what decides, so "on this list" can
  never mean something different from "reachable by a send".
- **`services/comms_contacts.py` is now the ONE copy of the upsert**, moved out
  of `routers/comms.py` (which delegates) because it is called from outside a
  request too. It carries the rule that must never be relaxed: a suppressed
  address is never resurrected. Everything else FILLS rather than clobbers, so a
  name a super admin typed always wins over one derived here.
- **THE CONTACT IS LINKED TO THE CLUB'S DIRECTORY ROW**, which is what makes
  `{{club}}`, `{{association}}` and — the reason it matters — `{{trial_days_left}}`
  resolve for these recipients. An email to club admins about their trial is
  exactly what this list is for, and without the link every one of those tokens
  renders blank. A club with no directory row leaves it NULL rather than guessing.
- **AN ARCHIVED CLUB'S ADMINS ARE LEFT OUT**, the house rule `auto_sync`
  eligibility and the Twenty pushes already follow. Anyone already on the list
  stays — nothing removes — they just stop being added by a later run.
- **AN ADMIN WITH NO EMAIL IS REPORTED, NOT DROPPED.** `users.email` is nullable
  and `UserCreate` carries no email field at all, so a super admin's newly
  created club_admin genuinely has none until `patch_user` sets one — which is
  hooked too. That count is what says the list is short of the roster.
- **AN EXISTING LIST OF THAT NAME IS ADOPTED, NEVER DUPLICATED**, and its
  `source`/`origin` are left alone: a list a person made by hand is theirs and
  this only fills it. `comms_lists` is unique on (organisation_id, name), so
  matching by name is exact.
- **THE DRY RUN HAS TO PROJECT A CONTACT THAT DOES NOT EXIST YET.** The first
  cut counted list additions by querying `comms_contacts`, so a run that would
  add everybody reported "0 to add" and read as nothing to do. It now counts the
  rows it would create (subscribed by construction, unless the ADDRESS itself is
  globally suppressed) and the suite asserts the dry run's figures are exactly
  what applying does. Found by running the script, not by reading it.
- **`python -m app.scripts.sync_admin_contact_list [<org-id-or-slug>] [--apply]`**
  is the backfill, dry-run by default per the house rule.
- **The AFL silo is deliberately untouched.** `routers/afl/users_admin.py` and
  `afl/super_clubs.py` write the same shared columns, but that backend runs on
  its own database where the cricket outreach org does not exist.
- **ADD NEW USER TAKES AN EMAIL AND A MOBILE (v9.56.1), which is what makes the
  create-time hook actually land somebody.** `UserCreate` carried neither, so a
  super admin's newly created club_admin had no address and could only reach the
  list once someone edited them afterwards. Both are OPTIONAL — a super admin
  naming an account on someone's behalf often has neither yet, and login is by
  username — and validated exactly as `patch_user` validates them: format only,
  never for uniqueness, since `users.email` stopped being DB-unique at migration
  145 and the edit form allows a repeat. `_INVITE_EMAIL_RE` and `_clean_mobile`
  are the same two the rest of that router uses, so the create and edit forms
  cannot disagree about what a valid address is.
- **A COMMENT THAT JUSTIFIES ITSELF BY ANOTHER FORM'S GAP GOES STALE WITH IT.**
  Both `patch_user` and `SuperUsers.jsx` explained their optional email with
  "this create form doesn't collect one" — true until it did. Corrected in place
  rather than left to mislead the next reader; the field stays optional, for the
  reason above.
- **The form validates BEFORE `setSaving(true)`**, or a rejected form leaves the
  button disabled with no way out. The suite asserts the ordering, not just the
  presence of the check.
- **Verified against a real Postgres**
  (`backend/verification/verify_admin_contact_list.py`, 69 checks through the
  shipped service, script logic and route bodies: who lands on the list and who
  does not, the club_member / super_admin / sales / archived exclusions, the
  list adopted rather than duplicated, a re-run creating nothing twice, all four
  suppression states kept off and their rows kept current, resubscribing putting
  them back, the directory link making the trial countdown resolve, a hand-typed
  name surviving, per-club scoping, two admins sharing one address, the dry run
  matching the apply, and `super_set_primary_admin` / `create_user` / `patch_user`
  driven as real route bodies, plus the address stored folded and trimmed, the
  two refusals creating no account at all, neither field required, a repeat
  address allowed, and a club admin created WITH an address landing on the list
  with no follow-up edit) **with control runs**: with the router hooks reverted,
  8 fail — the route bodies add nobody at all; with the create form reverted,
  12 fail.

<!-- END original CLAUDE.md L16805-16911 -->
<!-- BEGIN original CLAUDE.md L16980-17074 -->
## A club's trial, as an audience and as a number in the email (v9.55.0, Aug 2026)

Asked for on BetterComms → Segments: reach the contacts whose club is in a trial
finishing within N days, and the ones whose club's trial has already run out, and
be able to splice the day count into the template.

- **DIRECTORY SCOPE ONLY, and that is not a judgement call.** In the club scope
  every contact belongs to the ONE sending club, so "is the club in a trial" is
  all-or-nothing and answers nothing; a prospect's trial state is also
  BetterCricket's own sales data. `DIR_TRIAL_FIELDS` sits with the other
  outreach fields and the suite asserts the club field set carries none of them,
  per the hard scope rule in `PROJECT_RULES.md`.
- **`services/club_trial_window.py` IS THE ONE DEFINITION, and that is the whole
  point of the feature.** The segment picks the audience and the merge variable
  writes the number into the body, so an email saying "9 days" inside an
  audience built as "at most 7 days" would be the failure. The segment SQL and
  the merge vars read the same subquery and the same day arithmetic; the suite
  asserts the printed figure is EXACTLY the segment boundary (in at `<= n`, out
  at `<= n-1`) rather than merely close.
- **AN EXPIRED TRIAL'S ROW STAYS `status='trial'` WITH A PAST END** — that is
  what `module_subscriptions.sweep_expired_trials` deliberately leaves behind, so
  a past `trial_ends_at` on a `trial` row IS the expired state. A converted club
  has no `trial` rows and correctly reads as neither.
- **THE WINDOW IS `MAX(trial_ends_at)` ACROSS THE CLUB'S MODULES.** A club is
  still trialing while any one module is live, and has expired only once every
  one has run out. Verified both ways: a club with one finished and one live
  module reads as in a trial off the live one's countdown.
- **`ends_at` CANNOT ANSWER "HAS A TRIAL", which is why the subquery carries a
  `has_trial` marker.** It is NULL both for a club with no trial and for one
  whose only trial has no end date — opposite answers. The first cut used it as
  the test and an open-ended trial fell out of every option including "no trial
  on record"; the verification caught it.
- **AN OPEN-ENDED TRIAL ANSWERS NEITHER QUESTION.** It reads as running, never
  as expired, and carries no day count — telling a club whose trial is still
  going that it has finished is the one thing this must not do. Silence where
  the data cannot answer, the same discipline the selection rules keep.
- **DAYS-SINCE HAS ITS OWN FLOOR, NEVER THE NEGATION OF DAYS-LEFT.** Both count
  whole days elapsed, so each floors towards its own end: a trial that finished
  3.2 days ago has been over for 3 whole days, and negating `days_left` (which
  floors to -4) reports 4. Caught by the suite, not by reading the code. Note
  `crm.trial_days_remaining_by_club` still negates its signed figure for the CRM
  card's expired badge and carries that off-by-one; it was left alone rather
  than widened into this change.
- **A FIGURE THAT DOES NOT APPLY RENDERS BLANK, NEVER `0`.** "0 days left" to a
  club that is not on a trial is a lie. Every directory club gets an entry in
  the batched lookup — including one never onboarded — so the token resolves to
  empty rather than going out as a literal `{{trial_days_left}}`.
- **THE TRIAL FIGURES ARE NOT IN `EDITABLE_MERGE_KEYS`.** They are computed
  facts, and a hand-typed override would print a number the audience disagrees
  with. `_apply_overrides` is the one place that rule lives now, and
  `_contact_vars` is the one per-recipient builder the preview, the test send
  and the real send all call — the send's only difference is fetching the whole
  batch's windows in one query, which the suite asserts agrees contact for
  contact with the one-at-a-time path.
- **`{{trial_end_date}}` rides along free from the same lookup** because a
  countdown written at send time is wrong by the next morning, and an email is
  routinely read days later.
- **SUPER-ADMIN ONLY, AND NOW ENFORCED ON THE SERVER RATHER THAN JUST IN THE
  SCREEN.** The frontend gate was already sound (`SegmentsRoute.jsx` mounts
  `InternalSegments`, the only importer of `DIRECTORY_FIELD_DEFS`, on
  `can_switch_clubs && is_marketing_org`) — but the ENGINE refused nothing: a
  hand-made request from a club admin returned nothing only because the
  `MarketingClub` join happens to be empty for a club's own contacts.
  `directory_rules_allowed` is that boundary named, reading the same
  `org_is_outreach` that `/auth/me`'s `is_marketing_org` does, so the screen and
  the engine cannot disagree about who may ask.
- **IT FAILS CLOSED, AND THAT DIRECTION IS THE WHOLE POINT.** A directory rule in
  a club context empties the audience (`where(false())`) rather than being
  dropped — dropping it would WIDEN the segment to the club's entire list, and
  silently emailing everyone is far worse than reaching nobody. The write paths
  refuse with a 422 as well, so a club gets a sentence rather than a segment that
  can only ever resolve to nobody. The guard logs when it fires: an empty
  audience nobody can explain is the worst way to find out.
- **THE FIVE JOIN-LESS DIRECTORY FIELDS ARE A REAL BEHAVIOUR CHANGE.**
  `exported` / `emailed` / `opened` / `clicked` / `enquired` add no
  `MarketingClub` join, so they genuinely DID evaluate against a club's own
  contacts before this — the control run has a club naming `emailed` getting its
  whole list back. No club-facing screen can build one, and the terms are
  defined against outreach sends and prospect enquiries so they mean nothing for
  a club's own members; a segment saved before the two field sets were split
  apart is the only way one could exist, and it now reads as nobody instead.
  **The trial fields alone could not have proved the guard works** — their join
  already emptied them, so those checks pass against the unguarded code too.
- **Verified against a real Postgres**
  (`backend/verification/verify_club_trial_segments.py`, 73 checks through the
  shipped segment engine and route bodies: both scenarios, every boundary, a
  multi-module club either side of the line, the open-ended cases, a converted
  club, an un-onboarded prospect, the send gate still excluding an unsubscribed
  contact on a live trial, another club's contacts never reached, the SQL and
  Python day counts agreeing row by row, and the figures rendered into a real
  email, plus the super-admin boundary from both sides) **with two control
  runs**: with the segment engine reverted every trial rule is silently dropped
  and the audience comes back as all 12 contacts; with only the scope guard
  removed, a club naming `emailed` gets its whole list.

<!-- END original CLAUDE.md L16980-17074 -->
<!-- BEGIN original CLAUDE.md L17075-17125 -->
## Comms has no sync step: it reads the live Directory (v9.12.0, Aug 2026)

Reported from a club with 1,576 players: the Directory showed 1,578 people,
Comms could reach 128. Two separate causes, and the second is the structural one.

- **`sync_from_club` filtered on `Player.status == "active"`**, so last season's
  players and anyone lapsed were permanently unreachable. At Applecross that hid
  **280 of the 408 people whose email the club holds**. Active-only was the wrong
  place to decide an audience — `comms_contacts` is the address book, and the
  list or segment picked at send time is what chooses recipients. Suppression is
  unaffected either way, so an unsubscribe or bounce still skips the address
  however it was targeted.
- **The whole sync CONCEPT is gone** — endpoint, button, api method. Comms works
  on the Directory, which is itself a live read (every BetterStats player, plus
  anyone imported or hand-added in Clubhouse), so there is nothing to sync FROM.
  Filling in an email address is the club's job on the Directory, which is why
  the No-email filter lives there.
- **`comms.reconcile_contacts_from_directory(db, club)`** replaces it. A
  `comms_contacts` row still has to exist, because it carries what the Directory
  has no opinion about: unsubscribe, bounce, complaint, list membership, send
  history. This reconciles that spine on the READ path instead of asking an admin
  to remember. **Only missing addresses are written** — steady state is two reads
  and no write, which is what makes it safe to call on a GET. Hooked at
  `GET /contacts` (covers the Contacts screen AND the Lists picker, which calls
  the same endpoint), `_resolve_audience` (the single funnel for every preview,
  recipient list and send) and the three segment endpoints (which is what makes
  the merged Clubhouse Audiences screen live too).
- **A changed email gains a contact at the new address and keeps the old one** —
  the old address may carry a suppression or send history worth keeping. Names on
  existing contacts are not refreshed, a deliberate cost of the delta approach.
  Contacts are never deleted by the reconcile.
- **Skipped for the outreach org** (`org_is_outreach`) — BetterCricket's own
  marketing list is not a club directory, and reconciling would pollute it.
- **`POST /club-admin/comms/lists/from-directory`** turns a filtered Directory
  selection into an auto list (`source='auto'`, `origin='Clubhouse Directory'`),
  landing in the same "Auto-generated lists" section the CRM export uses. **The
  browser sends person KEYS, never emails** — the server re-reads the Directory
  and takes addresses from its own data, so a stale or tampered payload cannot
  introduce a recipient the club does not hold. Contacts go through
  `_upsert_contact`, which is what stops list-building resurrecting an opt-out.
- **The Directory's own kind-of-member filters came from v9.11.1 on main**
  (`membership_type` / `category` / `player_status`, the Playing and Former
  players pills). This release adds only **Has email / No email** on top, plus
  the header's no-email count. An earlier cut of this branch had its own
  Non-player and Inactive-player pills; they were dropped in the merge rather
  than shipped alongside, because two overlapping ways to ask the same question
  is how the two drift apart.
- **When adding a Comms surface that lists people**, call
  `reconcile_contacts_from_directory` first rather than reintroducing a sync
  button. Do not add a `status` filter to who becomes a contact — targeting is a
  list/segment decision, not an address-book one.
<!-- END original CLAUDE.md L17075-17125 -->

## v9.106.13: No email to a person who asked to be removed (Oct 2026)

The owner asked that BetterComms, and every email, leave out the removed player, and any person who asks. Rather than audit 26 callers of `get_email_provider()` and hope, the block sits where they all converge: the provider returned by `get_email_provider()` is wrapped (`PrivacyGuardedProvider`) and refuses a recipient on the removed list with a `SendResult(ok=False, error="blocked: ...")`, which every caller already handles as a failed send, so it reads as a failure and never as a success (rule 26). The same list is applied in `email_suppression.deliverable()` for the per-club senders and in `comms_segments.sendable_where` so an audience, a count and a "reachable" figure never include the person.

The list is derived on read (`privacy_email._ADDRESS_SQL`), not stored: a stored list would miss an address added to the person's record after the removal, which is exactly how a removed person gets emailed. `hide_at_request` also writes the addresses to `email_suppressions` (reason `manual`, which `deliverable` already treats as blocking everything; source `privacy_request` marks it) and sets `comms_contacts.excluded` on each linked contact, so the existing screens show them as suppressed. `upsert_contact` creates a contact for a removed address already excluded, because the Directory re-creates contacts on every read.

First draft of the audience clause used a correlated `EXISTS` over `Player` and `FeeMember`; two existing suites (`verify_comms_segments_merge`, `verify_admin_contact_list`) caught it: where the outer query already joins `Player`, SQLAlchemy correlates the table away and the statement has no FROM ("returned no FROM clauses due to auto-correlation"), and `admin_contact_list.sync`, which never raises, then silently produced an empty list. It is now independent sub-queries over aliased tables with explicit NULL tests. `verify_admin_contact_list` fails identically on the commit before this change in this sandbox (7 checks, same traceback), so it cannot vouch for that path here; the segments suite (96) and the others pass.

Not done: a family or guardian address is another person's and is not blocked; an email to the family as a whole still goes to the others. The sign-in email of a claimed account is blocked too, so a removed person cannot receive a password reset until support lifts it.

**Verified against a real Postgres** (`verify_privacy_email.py`, 25 checks: the three addresses, the audience, all three send categories, the provider guard and the real `get_email_provider()`, an address and a contact added after the removal, a club trying to un-suppress, an ordinary bounce still removable, restore) **with a control run** against the previous commit: 14 fail (he stays in the audience, the gate and the real provider send to him). `verify_comms_segments_merge` 96, `verify_comms_recipients` 22, `verify_audience_clubs` 19, `verify_club_trial_segments` 73, `verify_notifications` 146, privacy suites unchanged.

