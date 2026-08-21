# BetterStats — Claude Session Notes

## BetterFootball gets Manual Entries — a delta, not a replacement (v9.43.0, Aug 2026)

Asked for by pointing at cricket's `/admin/manual-entries#season` and saying
"build this for betterat.football". That hash is the **Adjustments** tab: add
or correct a player's totals, season blank for a career-only one.

- **ONE table, `afl_manual_adjustments`, because `season_id` is nullable and
  that IS the distinction.** Cricket needs `manual_season_adjustments` AND
  `manual_career_adjustments` because its career deltas carry a different
  column set; football's don't. One table is what lets the screen offer "leave
  the season blank" as a plain choice rather than two forms that look the same,
  and it is why the cricket UI already merges its two lists back together.
- **AN ADJUSTMENT IS ADDITIVE, and that is the whole design.** It carries no
  `NOT EXISTS` gate against the synced rollup anywhere it is read, unlike
  `afl_imported_stats`, whose rows only ever fill a gap the sync hasn't
  covered. An adjustment is a delta an admin typed BECAUSE of what the sync
  holds, so suppressing it where the sync already covers that player-season
  would do nothing in exactly the case it was entered for. Correcting a season
  means entering the SHORTFALL, and every confirm on the screen says so.
- **`services/afl/manual_stats.py::manual_branch` is the one definition of the
  UNION arm**, pasted by name into all thirteen reads. Thirteen hand-written
  copies of the same arm is how the leaderboard and the record book start
  disagreeing about a player's career. Each entry in `columns` is either a name
  from its map (aliased, so the arm lines up with the branch above it) or a raw
  expression passed through — a UNION matches by POSITION, so the two kinds
  interleave in whatever order the caller already uses.
- **A career-only row needs no exclusion clause anywhere.** A season-scoped read
  binds `m.season_id = :season` and a season-keyed one INNER JOINs `seasons`;
  both drop a NULL season for free. What's left is the career reads, which is
  exactly where it belongs.
- **`season_by_season` needed two things nothing else did.** A season can now
  produce more than one grade-less row (the sync's rollup plus a whole-season
  adjustment), which rendered the same year TWICE on the profile — they fold.
  And an adjustment entered against ONE grade of a season still belongs in that
  season's headline: the synced rollup was computed without it, and the
  existing synthesis only fires for a season with no whole-season row at all.
  So a `src` marker rides along, the per-grade manual deltas are held aside
  before the merge-group fold loses it, and applied after. The suite asserts
  the season table sums to the career total.
- **`most_goals_in_a_season` now SUMS per player-season before ranking.** An
  imported row can't coexist with a synced one for the same player-season (the
  gate), but an adjustment can — that is what a correction is — so without the
  grouping a +5 correction listed as its own 5-goal season in the record book.
- **`manual_edit_logs` is reused, not reinvented.** It is ORM-mapped on the
  shared Base, so it already exists in an AFL database. The undo is richer than
  cricket's on one point: an import snapshots each row's BEFORE state, so
  undoing an upload puts an overwritten adjustment back rather than leaving the
  overwrite standing.
- **Deliberately NOT unique on (player, season, grade).** Merging two players
  legitimately brings two rows onto one key, and additive rows read correctly as
  two; the alternative is refusing a legitimate merge or silently summing rows
  nobody asked to combine. A second one created BY HAND is refused (409), which
  is where a duplicate would be a mistake rather than a merge.
- **A merge MUST move them, and the reason is the opposite of the imported
  case.** `afl_imported_stats` has no FK, so forgetting it orphans rows;
  `afl_manual_adjustments` DOES cascade on `players`, so forgetting it DELETES
  the removed player's corrections outright. `_move_side_tables` carries them
  and `afl_merge_logs.adjustment_ids` (idempotent ALTER in the lifespan) is what
  lets an undo hand back exactly those rows. A split moves a season's
  adjustment; a career-only one has no season to attribute and stays put, same
  as an imported row whose season never resolved.
- **No new season endpoint.** The Import Stats wizard already owns
  `POST /club-admin/imports/seasons` and creates the identical row. A grade
  create is new (`/manual-entries/grades`) because nothing else offered one.
- **Deliberately NOT built: per-game manual entry.** Football's answer to
  "type a match in" is Import Results, which writes real `games` rows from the
  club's own register — a better answer than a hand-typed scorecard, and not
  what `#season` points at.
- **Noticed, NOT fixed**: `merge._enrich_player` counts `afl_player_season_stats`
  only, so a club whose history came from an import or an adjustment reads
  0/0/0/0 on the Merge Duplicates cards. Pre-existing, and the same gap cricket
  documents for its own `_enrich_player`.
- **Verified against a real Postgres** (75 checks through the shipped route
  bodies and read helpers, with the schema built by the real AFL lifespan run
  twice: every refusal, the audit summary, additivity against a synced season,
  the season table reconciling with the career total, the leaderboard both
  scoped and not, the vote board, the record book's summed season row, the
  dashboard panels, the admin roster, cross-club isolation, the season-delete
  guard, the CSV template round-tripping through the importer's own parser, a
  re-upload correcting rather than doubling, all five undo paths, and merge /
  undo-merge / split carrying the rows) and **driven in Chromium** (47: the
  exact payload on the wire for create and for the spreadsheet's CSV, the
  career-only confirm wording, a dismissed confirm sending nothing, an inline
  season create, the delete and undo requests, the deep-linked tab, no page
  errors, no overflow at 390px).

## The nets check-in list was hiding players, and turning up isn't batting (migration 273, v9.42.2, Aug 2026)

Reported from a club's Thursday nets, alongside the QR check-in the note below
describes: "I can't add Amardeep Gill though he is on the active list", and
people being entered as guests because they weren't there to find.

- **The roster was `active_self_service_players`, which DROPS DORMANT PLAYERS**
  — anyone whose last appearance falls outside the club's dormancy window
  (default 24 months). Right for a self-service availability link, wrong for a
  door list: Admin → Players shows that player as active, so the two screens
  disagreed and nothing on either said why. `GET /nets/roster` now returns
  **every** `is_player` player the club holds, tagged `dormant` / `inactive`,
  and the screen groups rather than filters. **Nothing is excluded, and that is
  the point** — a player standing at the door with their kit on is there
  whatever the app thinks of their last game, and dormancy was only one of the
  ways a name could go missing.
- **`availability.dormant_player_ids` / `club_player_roster` were extracted so
  both readings share one definition.** `active_self_service_players` is now
  those two composed and is byte-for-byte what it was — asserted, because the
  public availability link and the phone-coverage denominator read it.
- **`net_attendance.bats` splits turning up from batting** (migration 273).
  Someone arriving with a sore shoulder, or to bowl, or to keep, is present and
  counts towards attendance; leaving them in the queue means a net stands empty
  when their name comes up. **`_waiting()` is the one definition of the batting
  queue** and `_rotate` reads it, so the screen and the rotation cannot
  disagree. Coming back in puts them at the BACK, same as returning from batted.
  `note` carries what they said on the way in.
- **`check_in_person` gained `bats` / `note` rather than growing a second
  writer.** A duplicate check-in stays a no-op, and it must NOT rewrite state:
  someone a coach marked as sitting out stays that way when their name is tapped
  again.
- **Up next holds only what is still to come.** Batted and Not batting are their
  own lists, which is what stops a 31-name queue reading as 31 still to bat.
- **The row icons are a cricket bat drawn as TWO DIAGONAL STROKES**, a thick
  round-capped blade and a thin handle, with the mark in the freed bottom-right
  corner (green arrow = bat next, accent tick = mark as batted, no-entry = not
  batting). Rendered side by side at 16/22/40/72px, every upright
  outlined-blade version reads as a BOTTLE; the diagonal and the weight
  difference between blade and handle are what make it a bat. Judged from a
  comparison sheet, not from the code. A key above the list names them, shown by
  default and hideable per person via `usePref` (a four-line twin of the
  Clubhouse kit's, deliberately not an import — that module is a different
  bundle and a remembered toggle shouldn't pull it into first paint).
- **Found while verifying: the shortcut button added to the session header
  pushed the page 44px sideways at 390px.** The cluster measured 418px and could
  not wrap; the outer `flex-wrap` cannot save a group that won't wrap itself.
  Confirmed NEW by re-measuring with the change stashed (baseline 390 = 390).
- **This landed ALONGSIDE the QR check-in below, which shipped from another
  branch the same day.** Both had built a per-club check-in link, both numbered
  their migration 272 and both wrote a `v9.42.0`. The QR version won on the
  overlap (its token, its `require_pin` default of true, its
  `allow_registration` and registration queue, its `/nets-checkin/{token}` path
  and `public_net_checkin.py`); this branch kept the roster fix, the batting
  split and the screen work, and moved to migration 273. **Two migrations with
  one revision id break Alembic outright**, so check `origin/main` before
  numbering one.
- **Verified against a real Postgres** (82 checks through the shipped route
  bodies: the migration applied three times to a populated table and the
  lifespan mirror matching it, the reported player reachable with a control
  asserting the old roster really did hide him, availability's own pool
  unchanged, rotation skipping a non-batter, a repeat check-in not dragging one
  back into the queue, and three genuinely parallel taps on one name landing
  once) and **driven in Chromium** (56: the three lists, all three bat icons and
  what they write, the key showing by default and its hidden state surviving a
  reload, the modal reaching a dormant player and the exact payload on the wire,
  no page errors, no overflow at 390px).
- **Not built here**: nothing writes fixture availability — "here, not batting"
  is about tonight only. Promoting a guest to a real player landed separately in
  v9.42.1 ("Not on the roster" on the Players screens).

## A player checks themselves in at the nets (migration 272, v9.42.0, Aug 2026)

Asked for as an NFC tag by the gate, then as a QR code alongside it. Checking
in was an admin action — a manager tapping each name on the iPad — and this is
the same check-in done by the player on their own phone on the way past.

- **The QR code and the NFC tag are ONE link, and that is not a shortcut.** A
  tag stores a URL and nothing else, so writing the page's address to a tag and
  printing it as a QR code are two ways of handing over one string. One token,
  one `organisations.net_checkin_token`, mirroring `availability_link_token`
  down to the partial unique index. Two tokens would be two things to keep
  alive and two to reprint on a rotate.
- **SCANNING JOINS EVERY LIVE SESSION, not one picked off a list.** Somebody
  walking into the nets does not know which of the club's two concurrent
  sessions the seniors' one is called, and asking them is a question the club
  can already answer. `net_manager.live_sessions` is active sessions dated
  within a day either side of today — the app holds no per-club timezone, so a
  club whose evening is the server's tomorrow would otherwise scan in to
  nothing. Narrow at BOTH ends deliberately: a session somebody forgot to mark
  done last week must not quietly collect tonight's arrivals.
- **A NEWCOMER IS CHECKED IN AS A GUEST, NEVER AS A PLAYER.** `net_attendance`
  has carried guest rows (`player_id` NULL + `guest_name`) since it was
  written, for exactly this person — the trialist not yet in the system — so
  the mechanism was already there and this uses it rather than inventing one.
  It is what stops a stranger who found the QR code writing an unvetted row
  into the club's player table. What they type lands in
  `net_checkin_registrations`, `status='pending'`, and approving it is the ONE
  place this ever creates a player.
- **Approving CONVERTS the guest row, it does not add a second one.** The row
  that already says they turned up has its `player_id` filled in and its
  `guest_name` cleared, so the night counts towards the new player's own tally
  instead of being logged twice. Where the club had also checked them in
  properly, the real row is kept and the guest row dropped — the unique index
  would refuse the pair, and two rows for one person is the wrong answer anyway.
- **Dismissing leaves the guest row alone.** They did turn up; the session's
  record of the night should say so. Dismissing is a decision about the roster,
  not a claim that the evening did not happen.
- **`previous_club` has no home on `players` and does not get one.** One line
  of free text somebody typed about themselves is not a reason for a column;
  it stays with the rest of what they typed.
- **The PIN cannot gate registration, and that is why there are two switches.**
  `net_checkin_require_pin` proves an existing player is themselves via
  last-4-of-phone. A club has no number on file for someone it has never met,
  so `net_checkin_allow_registration` is its own setting rather than something
  read off the PIN one.
- **`net_attendance.source` ('admin' | 'self') is what makes the alert
  possible.** A self check-in has no `recorded_by` to read, so nothing else
  separates a name the manager just tapped from one that scanned itself in.
  Mirrors `player_availability.source`. Rows written before 272 read 'admin',
  which is what they were.
- **`check_in_person` is the one place a check-in is written**, shared by the
  admin screen and the public page; `add_attendee` was refactored onto it.
  Two copies is how the two paths start disagreeing about what a check-in is.
  It returns None for "already in" — a no-op at two levels, app-level read and
  IntegrityError on the unique index — and **the caller must not touch a lazily
  -loaded attribute after that None**, since the rollback expires every loaded
  object (the MissingGreenlet trap this file already documents).
- **`touch_session` is `_touch` under an importable name.** A self check-in has
  to move `net_sessions.version` or the iPad's next poll is told nothing
  changed and the arrival never appears.
- **The live screen ANNOUNCES an arrival** — pop-up, chime (reusing the timer's
  existing `beep`/`unlockAudio`, not new machinery) and `navigator.vibrate`.
  Only `source === 'self'` fires it: a name the manager tapped on that very
  screen must not pop up at them. A screen opening mid-session seeds its seen
  set silently, or it would announce the twenty people already there.
  **iOS Safari ignores `navigator.vibrate` entirely**, so the pop-up and the
  chime carry the alert and the buzz is a bonus on Android. A browser plays no
  sound until the page has been touched, so an iPad propped on a fence gets a
  "tap once to turn on sound" prompt rather than being silently mute.
- **Deliberately NOT built: Web Push.** Real OS-level notifications need a
  service worker, VAPID keys, a subscriptions table and `pywebpush`, none of
  which exist here, and on iOS they only work once the site is installed to the
  Home Screen — a per-device setup step. The device this was asked for is
  already looking at the live screen, which is most of the reason push exists.
  A smartwatch has no direct path at all: a watch mirrors notifications from a
  paired phone, so it would ride on push rather than being targetable.
- **The landing payload never says who is already checked in.** This page is
  served to whoever holds the link.
- **Verified against a real Postgres** (103 checks through the shipped route
  bodies: the token resolving and every 404-not-403 refusal, the live-session
  window at both ends, the PIN gate incl. no-mobile as a 409 rather than a
  failure and a cross-club player reading as a wrong PIN, an availability
  cookie not replayable as a check-in one, a double tap adding nobody, one scan
  joining two sessions, a newcomer landing as a guest with the roster untouched,
  every registration guard, approval converting the guest row and refusing
  twice, matching onto an existing player minting nobody, dismissal leaving the
  attendance alone, cross-club rejection, migration 272 applied three times to a
  populated pre-272 table, and the partial index tolerating NULLs) and **driven
  in Chromium** (82: the exact params on the wire for verify/check-in/register,
  a wrong PIN checking nobody in, one-tap check-in with the PIN off, a returning
  player never re-verified, every registration field on the wire, the QR
  rendering and its download, the review queue's three decisions and the roster
  match, the live screen's pop-up firing for a self check-in and staying quiet
  for an admin one, no page errors, no overflow at 390px).

### Turning a nets guest into a player (v9.42.1)

Reported straight after the above: "how do we turn a guest into a player within
the Players section?" The answer was **you can't** — and it was a real dead end,
not a missing button.

- **A guest row is written two ways and only one of them had an exit.** Somebody
  who scans the QR code lands in the Check-in queue with the details they typed.
  A guest the manager TYPES on the live screen has no `net_checkin_registrations`
  row, so `approve_registration` — which reaches the attendance row only through
  `NetCheckInRegistration.attendance_id` — could never see them. They turned up
  week after week and could only become a player by an admin retyping them,
  which stranded every night they had already attended on rows nothing reads.
  **`AttendeePatch` accepts `batted` only**, so nothing else could attach a
  `player_id` either, and `claim-fill-in` hard-validates a UUID participant id
  so it cannot serve a guest who has none.
- **`GET /nets/guests` groups by NAME, not by row**, because the question is
  about a person: "this bloke has been to five sessions, should he be on the
  list". `_guest_key` folds case and surrounding space and **nothing else** —
  deliberately not fuzzy. Two people really can be typed in under one name, and
  quietly folding "J Smith" into "Jack Smith" would put one person's attendance
  on another. The most recent spelling is the one shown.
- **Anyone carrying a PENDING registration is left OUT and counted instead.**
  They already sit in Check-in *with* their mobile, email and date of birth, and
  one person offered on two screens with different information behind each is
  how the two start disagreeing about who they are. The panel links across.
  Settle their registration and they become an ordinary guest here again.
- **`POST /nets/guests/promote` moves their WHOLE history, not the window.**
  The 90 days is a filter for who is worth looking at; somebody joining the club
  should not leave half their nights behind. Where they are already checked in
  properly for a session the real row is kept and the guest row dropped — the
  unique index would refuse the pair — and two guest rows on one night collapse
  to one for the same reason.
- **It settles any registration pointing at those rows too**, or a person
  promoted from Players would sit in the Check-in queue forever.
- **The key is resolved server-side against the club's own rows**, never a raw
  name off a browser, so a key cannot reach another club's guests.
- **Gated on EITHER `MANAGE_SELECTIONS` or `MANAGE_PLAYERS`** (`require_any_cap`):
  a selections manager runs the nets and can already do this from Check-in, and
  a player manager owns the roster. That is also why the panel is on BOTH
  Players screens — an admin should not have to know which one owns it.
- **`UnrosteredGuests` renders NOTHING when there is nobody to sort out**, and
  never calls the endpoint for a club without BetterSelect (the router is behind
  `require_module("select")`, so it would 402). Same rule as `ageFilterOptions`:
  a control that can only ever answer "everyone is fine" is worse than none.
- **`AdminPlayers`' roster fetch was inline in an effect** and had to be
  extracted to `loadPlayers` so promoting can pull the list again — the person
  is a player now and the screen they were missing from should say so.
- **Verified**: the Postgres suite is 138 checks (the 103 above plus one person
  across three spellings, the window at both ends, another club's guest never
  listed, the pending exclusion both ways, all three nights moving, the clash
  and double-entry collapses, five refusals, and a promotion settling its
  registration) and the Chromium run is 108 across four suites, including the
  panel on both Players screens, the exact payload for create and match, a club
  without BetterSelect never calling the endpoint, and nothing drawn when
  everyone is on the list.


### Ending the night (v9.42.3)

Reported from a live session: nets were running and there was no way to say they
had finished.

- **Ending STOPS THE CLOCK in the same write**, server-side in `update_session`,
  not as a second call from the browser. A finished session otherwise sits there
  counting down on every device it is open on, and whichever one notices the
  deadline pass would rotate a group that has gone home.
- **Ending is what closes the QR code**, because `live_sessions` only ever
  returns active sessions. That is the real cost of the button and the confirm
  names it: a late arrival scans in to nothing rather than joining a session
  that is over. The confirm also counts who is still in the queue.
- **Nothing is destroyed.** Attendance stays, the per-session CSV still
  downloads, and Reopen sets it back to active — which is why ending is a plain
  confirm rather than a typed one.
- **`ended` is read off the server payload**, never a local flag, so a coach
  ending it on the phone by the nets has the laptop in the clubroom follow on
  its next poll. The timer controls, the check-in button and the check-in-screen
  shortcut are all withdrawn on an ended session; the shortcut would only land
  on "no nets on right now".
- **Verified**: 149 Postgres checks (the 138 above plus the clock stopping and
  the deadline clearing, the version moving, a scan no longer joining, the
  attendance untouched, and reopening restoring all three) and 134 in Chromium
  across five suites, including the confirm's wording, dismissing it changing
  nothing, and every control that should disappear.



## BetterClubhouse is BetterAdmin again, and Committee got its button rows (v9.40.0, Aug 2026)

Asked for directly: put the module's name back, and lay the Committee screen out
as sections with their own buttons rather than three tabs and a manage page.

- **The rename is DISPLAY ONLY, and that is the whole point.** `admin` is still
  the module key, `/admin/clubhouse/*` is still the URL, and
  `BetterClubhouseLayout.jsx` is still the component. Entitlement, billing,
  `org_module_subscriptions` and every stored row are untouched — the same call
  the v9.3.0 merge made in the other direction. Only strings a person reads
  changed: `MODULE_BRAND.admin.name`, `MODULE_GROUPS.admin.name`,
  `MODULE_TOGGLES`, `BILLABLE_MODULE_NAMES`, the Comms segment field vocabulary,
  and `ModuleLayout`'s `moduleName` (now "Admin"; `clubhouse` stays in
  `moduleBrand`'s ALIAS map so nothing that still asks for it breaks). The
  marketing site and `billing_pricing.py` already said BetterAdmin, so the app
  has stopped disagreeing with the invoice.
- **Committee's buttons are Meetings (default), Motions & Actions, Plans,
  Documents, Calendar, Positions**, with a second row where a section holds more
  than one thing (Meetings → All Meetings | Meeting Templates) and a third under
  Actions. Every key lives in `st`
  (`cteMeetingsView` / `cteMaView` / `cteActionsView` / `ctePlansView`), so a
  label can be renamed without moving anyone's view. **Positions is kept even
  though the brief's list did not name it** — dropping a working screen is not
  something a rename asks for.
- **Documents, Calendar, Plans and the Actions board/timeline are the MANAGE
  screen's own components, mounted here, not copied.** `TasksTab`,
  `DocumentsTab` and `CalendarTab` are exported from `AdminCommittee.jsx` and
  `PlanTab` from `governance.jsx`; two versions of "the club's documents" is how
  the two start disagreeing about what the club holds. They are `lazy()` inside
  this screen, because most visits only ever look at Meetings — glancing at the
  committee should not pull the editors in.
- **`TasksTab` takes an optional `view`/`onView` and hides its own toggle when
  they are given.** Uncontrolled it is byte-for-byte the manage screen's; passing
  `view` is what lets the Committee screen's own List / Board / Timeline row
  drive it rather than drawing two toggles that disagree. `PlanTab` takes
  `section` the same way — pass nothing and the whole tab renders as it did.
- **A Meeting Template CAN be deleted while meetings are built from it, and that
  is not a gap.** `_apply_agenda_template` COPIES a template's items into real
  `meeting_agenda_items` rows at the moment the meeting is created, and
  `committee_meetings.agenda_template_id` is `ON DELETE SET NULL`. So a past
  meeting keeps its agenda word for word; it simply stops naming where it came
  from. The confirm dialog says so rather than warning about a loss that cannot
  happen. Editing a template is the same story — it sets what the NEXT meeting
  starts from and never rewrites one already held.
- **Deleting a meeting is the destructive one** and its confirm names what goes
  with it (agenda, motions, attendance, minutes). A failed write is reported in
  a line under the header; this screen has no toast.
- **A committee season is the club's DIARY year, not a calendar one.** The
  Season dropdown on All Meetings resolves each meeting through
  `organisations.diary_start_month` (read off `adminGetSettings`, which any
  signed-in admin may call — a committee manager does not hold
  `MANAGE_SETTINGS`), so July 2026 to June 2027 is one season at a club
  starting in July, and a club starting in January gets a one-year label
  rather than "2026/2027". Options are the seasons the club actually met in
  plus the one running now, so a club that has just rolled over can find this
  season and see it is empty. `sel` reads the FILTERED list, or filtering
  could leave a meeting open that the rail no longer holds.
- **`ActionEditor` (governance.jsx) is the one place an action is edited**, and
  it replaced `ActionPlanPanel`, which unfolded a full two-column editor inside
  a 200px board column — reported as a meaningless block, and it was. It opens
  from the List, the Board and the Timeline alike. The plan linkage is a
  written-out breadcrumb (PLAN › THEME › OBJECTIVE plus the objective's owner,
  due date and allocation) rather than a dropdown you had to open to find out
  what the action was for. `ACTION_CATEGORIES` / `ACTION_STATUSES` /
  `ACTION_STATUS_LABELS` are exported from there and imported by
  AdminCommittee, so the vocabulary has one home.
- **`MotionEditor` is the motion's counterpart**, opened from the register.
  A motion belongs to a MEETING, so every row in the register carries the
  `meeting_id` it was moved at and each write goes to that meeting's own
  endpoint — the register is assembled from several meetings and has no id of
  its own to write against.
- **Strategic Plans is a TREE beside a detail pane** (`StrategicPlansSection`,
  governance.jsx), the same two panes All Meetings uses: plan → theme →
  objective → the actions and motions serving it, each branch foldable, the
  first plan opened on load. Clicking an action or a motion opens the SAME
  editor the lists open, `inline` — `EditorShell` is a dialog when it is opened
  over a list and plain content when it IS the pane, so there is one editor
  either way rather than a second read-only copy.
- **A THEME IS CLUB-SCOPED, NOT PLAN-SCOPED** (migration 232), and every delete
  decision here turns on it. Drawn under a plan because that is how a committee
  reads its plan, but deleting one reaches every plan it groups objectives in —
  so the confirm counts across all of them and says how many plans are hit.
  Deleting a PLAN leaves the club's themes alone for the same reason.
- **`sort_order` is stamped by POSITION over a WHOLE level**
  (`reorder_plan_tree`, one endpoint each for plans, pillars and objectives).
  Objectives are ordered club-wide and only GROUPED by plan and theme, so a
  move inside one theme sends every objective in the tree's display order —
  renumbering the dragged group alone would interleave it with another group's
  numbers. A foreign or stale id is skipped without leaving a gap in the
  numbering, the same rule `reorder_agenda_items` follows. Adding a row reuses
  the same endpoint: create, then splice the new id in after the selected one,
  which is what makes "+ THEME" land below the theme you were standing on
  rather than at the bottom.
- **A row only drops on a SIBLING** — same level AND same branch. A cross-level
  or cross-branch dragover deliberately does not `preventDefault`, so the cursor
  refuses before the mouse is released instead of the drop silently doing
  nothing. Moving an objective under a different theme would be a re-parent,
  which is a different act from putting it in order, so it is not a drag.
- **`?cascade=true` is opt-in on both plan and pillar delete**, and the default
  is still the documented "deleting never takes work with it". The screen asks
  first and counts what goes; a caller that has not asked gets the old
  behaviour (objectives survive, ungrouped or off the plan). **Neither mode
  ever deletes an ACTION or a MOTION** — `club_objectives` → tasks/motions is
  ON DELETE SET NULL, so they are kept and simply stop being linked. That is
  the one rule not to relax.
- **The objective PICKER groups rather than repeating.** A flat `<select>` of
  "Plan › Theme › a whole sentence" was reported as overwhelming, and the
  repetition really was ~80% of the text while the part that tells two
  objectives apart was the part being clipped. `ObjectiveSelect` now says the
  plan and theme ONCE as a group heading, gives each objective its own
  wrapping line, ticks the current one and offers a search box past six rows.
  It is not a `<select>` any more, so a test asserting `<option>` text is
  asserting the old control.
- **`planLabels.js` is the one place an objective is NAMED from elsewhere**,
  and it names all three tiers: PLAN › THEME › OBJECTIVE. Skipping the theme
  was the reported bug, and it matters because an objective's own title is
  routinely a whole sentence ("Appoint accredited, high-quality coaches for
  all senior and junior squads.") — the theme is what groups it. `objectiveLabel`
  and `objectiveTiers` are the same data two ways, so the picker's one-line
  label and `ObjectiveLink`'s written-out breadcrumb cannot disagree. It is its
  OWN tiny module rather than a corner of governance.jsx, because the screens
  that only name an objective must not pull that whole bundle into first paint.
- **The Board's lanes are the drop targets, not the cards.** Dropping into the
  empty space under the last card has to work, or an empty lane could never
  receive anything. The move is applied locally first and rolled back on a
  failed write, so a card lands where it was dropped instead of snapping back
  for the length of the request. Testing it needs `DragEvent`s dispatched with
  `dragstart` and `drop` in SEPARATE `evaluate` calls — the trap the roster
  note above describes.
- **Driven in Chromium** against the real screens with the API stubbed at the
  network layer (39 checks: every button row and the ones that correctly do not
  render, the meeting delete reaching the API and leaving the list, the template
  PATCH and POST payloads on the wire, a template delete, all three Actions
  views, Plans / Themes / Objectives, Documents, Calendar, no "BetterClubhouse"
  anywhere on screen, no page errors, no overflow at 390px) plus a second pass
  asserting the MANAGE screen's own Board/Timeline and By plan/All work toggles
  are unchanged.


## A club writes its association's rules down once (migration 271, v9.39.0, Aug 2026)

Asked for so a selector isn't holding the handbook in their head on a Friday
night: age limits per division, a cap on overseas players, the overs a young
quick may bowl, qualifying games for a final, plus fees and training. Built
from a WASTCA handbook but deliberately NOT as its rulebook.

- **`selection_rules` is one table with a `kind`, a `scope` and a `config`,
  and `services/selection_rules.py` is the only place either blob is read or
  written.** Ten kinds: `age`, `overseas`, `bowling_workload`,
  `finals_qualification`, `grade_cap`, `fees`, `training`, `registration`,
  `rest`, `custom`. A per-kind table would have been ten migrations and ten
  screens for what is one question — "does this player break something".
- **THE DATE AN AGE IS MEASURED ON IS A SETTING, and that is the whole reason
  this generalises.** One competition counts age as at 1 September of the year
  the season started, the next as at 1 January, a third on the day of the
  match. `age_basis` is a month, a day and which END of the season the year
  comes from, so all three fall out of one field. A cutoff resolves against
  the SEASON, not the calendar — 1 September 2025 for every match of a 2025/26
  season, February ones included — which is what makes a player the same age
  all season, the entire point of a cutoff. `season_start_month` (default 7)
  is the fallback for a fixture with no season to read, and is what lets a club
  playing an English April-to-September season land its ages in the right year.
- **A rule names its grades, never their ids.** Grades are per-season rows, so
  a rule keyed on ids silently stops applying the day the new season's grades
  are created — mid-rollover, with nothing to see. The same call `vote_medals`
  had to make. Names are matched sponsor-suffix-stripped and case-folded, so
  "A Grade (Gatorade)" and "A Grade" are one rule's worth. **An EMPTY scope
  means EVERY fixture**, which is what a club's first rule means before anyone
  has thought about divisions. A rule can be scoped by grade CATEGORY or
  FORMAT instead, so "every junior grade" is one rule rather than eleven.
- **Severity is the club's, not ours.** The same age limit is a hard bar at one
  association and a guideline at the next, so each rule carries `warn` (say so,
  ask before saving) or `block` (refuse the save). `bowling_workload` is the
  one kind forced to `info`: a fourteen year old is not ineligible, there is
  simply a limit on what may be asked of them once they are out there. Making
  it a breach would have been us inventing a rule nobody wrote.
- **`selection_rule_players` is the escape hatch, and it is per RULE.**
  Associations grant permits, and a system that can't express one gets switched
  off rather than corrected. A fourteen year old cleared for Division 1 is not
  thereby cleared of everything else, which is why this is not a flag on
  `players`. It doubles as the tick a free-text rule asks for.
- **SILENCE IS THE ANSWER WHENEVER THE CLUB'S DATA CAN'T ANSWER.** No date of
  birth, no fees module and no override, no registration row, no nets session
  in the window, no squad seniority — every one of those is "we cannot say",
  never a breach. A rule that flags the whole squad because nobody filled a
  field in gets turned off, and then it flags nothing at all. This is the same
  discipline the `is_financial` / `trained_recently` tri-states already keep.
- **The overseas cap is the ONE rule whose answer depends on who else is
  picked**, so it rides on the payload as a definition the browser counts live
  (a selector watches it fill up) and the SAVE re-counts for real. Every other
  rule is per-player and decided server-side. Never let the browser's count be
  the one that decides.
- **`selection_pool.assemble_selection` resolves fees and training FIRST and
  hands the two maps to the rules engine** (`_flag_maps`), rather than the
  engine asking again. A rule and the badge beside it disagreeing about the
  same player is exactly the bug this shape prevents. `rule_context` /
  `club_rule_context` are the same resolution for the save path and for the
  screens with no fixture, so there is one answer everywhere.
- **An age rule moves the age ON THE CARD to the date the competition counts
  it on** (`visible_age(dob, club, as_of=age_at)`), because that is the number
  a selector is checking against the handbook. The club's display gate still
  applies, server-side: a club that shows ages for under-16s only never sends
  an adult's age to a browser, rule or no rule.
- **A blocking rule takes the player out of AUTO-FILL** (`autofill_eligible`),
  since auto-fill must not build a side the save would then refuse. A warning
  is left alone — that is the club saying "tell me, don't decide for me".
- **Qualifying games count scorecards AND named XIs, deduped on the DATE.** A
  final is picked the week after the last round, before that round has synced;
  counting only what has synced would tell a club its own captain hasn't
  qualified. A synced game and the fixture it came from share their date, so
  a match counted from both sources counts once.
- **`_FIXTURE_ONLY_KINDS` is what keeps the roster honest.** The availability
  matrix and the Players roster have no fixture, so they answer only the rules
  that hold whatever the match — fees, registration, training, a club-wide age
  limit. "Has this player qualified for a final" has no answer until you say
  which final, so it isn't answered badly there.
- **Every screen asks the payload whether the club has any rules at all**
  (`flags.rules` / `rules.active`) and draws nothing when it doesn't — no
  badge, no filter, no compliance strip. Same call `ageFilterOptions` and the
  Fees/Training source notes already make: a control that can only ever answer
  "everyone is fine" is worse than no control.
- **The starter is the published CA Junior Cricket Policy bowling ladder and
  nothing else.** Every other kind needs the club's own numbers, and a number
  we invented would be quoted back at us. Skip-don't-replace, so pressing it
  twice can't overwrite a club's own workload rule.
- **The BetterSelect settings moved out of Club Settings** (age display,
  dormant-player window, default side size) onto this screen, which is gated on
  `MANAGE_SELECTIONS` rather than `MANAGE_SETTINGS` — a selector holds the
  handbook, and may not hold the club's colours. Club Settings links across.
- **Found while verifying: `shrink-0` on a rule's action cluster pushed the
  settings screen 79px sideways at 390px.** `flex-wrap` on the parent cannot
  save a child that has been told not to shrink — the same trap the Selection
  header note below describes. Measured, not eyeballed.
- **Verified against a real Postgres** (79 checks through the shipped route
  bodies and services: migration 271 applied three times, the two age bases
  disagreeing about the same player, a name-scoped rule still applying after
  the season rollover, category scoping, warn saving and block refusing, a
  permit clearing and a manual block flagging, the overseas cap both ways,
  the workload note firing for a junior quick and not a spinner the same age,
  qualifying games from both sources deduped on the date, the grade cap, all
  five module-derived rules incl. every "we can't tell" branch, five validation
  guards, cross-club rejection, the tri-state age-limit setting, a 29 February
  cutoff in a non-leap year, and BetterIQ reading the same verdict) and
  **driven in Chromium** (35: the exact params on the wire for the basis and a
  new rule, grades scoped by name, the badges and the workload note, the strip
  turning red as a barred player is picked, the overseas cap counted live, a
  refused save quoting the server's reason, the rules filter, the same badge on
  the availability matrix and the roster, a rules-free club seeing none of it,
  no page errors, no overflow at 390px).
- **Not built**: a bowling-overs COUNT against what a junior actually bowled —
  the app holds scorecards, so it could report a breach after the fact, but the
  rule is a limit on the day and the umpires enforce it. Nothing here writes to
  PlayHQ or claims an association has approved anything.

### What the first round of use changed (v9.41.2)

- **The rule scope picker reads Manage Grades, not `grades` directly.** The
  first cut listed every distinct grade name in the club, alphabetically — a
  decade of history in an order nobody chose, with merged grades listed twice.
  `selection_rules.club_grades` now mirrors that screen exactly: aliases folded
  onto the grade that was kept, the club's `display_order` first and unplaced
  grades after, and a `recent` flag for the two most recent seasons so the
  picker offers what the club RUNS and hides the rest behind a link. **A picker
  and the screen that owns the thing it is picking must agree**, or a selector
  is choosing from a list they don't recognise.
- **The fixture's grade is folded the same way before a rule is matched**
  (`grade_alias_map`), so a rule naming the kept grade covers a fixture
  arriving under a name merged into it. Scoping by name is only standing if
  both sides resolve names the same way.
- **A blocking rule now filters the pool for you.** The board opens on
  eligible-only when any rule in play can bar someone — once per fixture, as an
  ordinary filter pill, so clearing it sticks until you move to another
  fixture. WARNINGS are deliberately still shown: a warning is the selector's
  to weigh, and hiding those people would be deciding for them.
- **An age rule carries a comparison at each end** (`min_op` gte/gt, `max_op`
  lt/lte). "15 and over" is not "over 15" and "under 21" is not "21 or under",
  and an association writes them either way round. `_min_phrase` / `_max_phrase`
  are the one wording, shared by the summary, the breach text and the editor's
  live preview. A stored config with no operator reads as gte/lt, which is what
  every pre-existing rule meant.
- **`fixed_date` is a third age basis**: one calendar date, typed in, for a
  competition that publishes a date rather than a rule about the season. It
  deliberately does NOT move with the season — the screen says so, because
  somebody has to change it each year.
- **The age ladder runs to 23**, on the rule, the display setting and the pool
  filter. Colts and under-21 competitions are ordinary, and stopping at 19 made
  them unexpressible.
- **The fees and training notes can each be switched off**
  (`selection_rules_config.show_fees` / `show_training`) and the value is then
  WITHHELD rather than sent and hidden — the same call `visible_age` makes. The
  filter goes with it, since there is nothing left to filter on. A fees or
  training RULE still flags: that one the club asked for explicitly.
- **"Has a problem" reads as "Flagged".** A player a rule has something to say
  about is not a problem.
- **Verified**: the Postgres suite is 102 checks now (the 79 above plus the age
  comparisons both ways, an exactly-one-age rule, a fixed date not moving with
  the season, junk falling back to the default, the Manage Grades order with an
  unplaced and a merged grade, `recent` excluding a 2010 grade, a rule matching
  through a merge, and a switched-off note withheld while its rule still
  flags), and the Chromium run is 49.

## Season × grade matches on a player profile, and the undercount it exposed (v9.37.3, Aug 2026)

Asked for on Analysis → Team: seasons down one axis, a column per grade the
player actually turned out in, a plain match count in each cell, columns in the
club's own reading order. No migration, no new endpoint.

- **The grid and the by-grade table above it come from ONE attribution pass.**
  `get_player_team_breakdown` now builds a per-(season, grade) cell map and
  derives `rows` from it, rather than the two being computed separately. That
  is what makes the grid's column totals equal the table's `matches` **by
  construction** — the same one-place discipline `_season_by_season_scoped`
  exists for, and the reason a screen can't end up disagreeing with the card
  sitting two inches above it.
- **Doing it per season fixed a live undercount.** Step 1 used to compare CA's
  exact per-grade aggregate against the scorecard count **across the whole
  career** (`extra = max(0, agg_total - scorecard_total)`), which is only right
  when every season is one or the other. A player with `player_season_grade_stats`
  for 2024/25 (CA: 10, held: 3) and scorecards only for 2025/26 (5) read **10**,
  not 15 — the scorecard season was swallowed by the aggregate one. Reproduced
  against a real Postgres by running the pre-change function, then the new one.
  It flows into the grade-matches milestones too (`players.py` ×2 read
  `rows[].matches`).
- **The two attribution rules are unchanged, just applied per season**: CA's
  per-grade row wins but never below the scorecards we hold; with no per-grade
  row, a season's shortfall goes to the one grade it can only have come from,
  else to `unattributed`. A season CA HAS broken down is taken at its word, so
  a shortfall against its own season total is left alone rather than guessed at
  — the deliberate `seasons_with_exact` skip the old code made, kept.
- **Seasons are folded onto their canonical row before anything is counted**
  (`load_reverse_alias_map`), or a Merge Seasons pair, or one CA season guid per
  competition, draws the one year as two lines.
- **`_org_grade_display_orders` is keyed on the FOLDED grade name**, not the raw
  CA guid `social_rounds._grade_display_orders` uses — these rows have already
  been through the merge alias and the club's rename, and two guids can land on
  one name. `MIN(display_order)`: the reorder endpoint stamps the position onto
  the canonical grade and every alias merged into it, so MIN ignores a NULL left
  on an alias nobody ordered. A grade the club has never placed reads NULL and
  the column sorts after every placed one, the same rule everywhere else.
- **The existing MATCHES BY GRADE table is deliberately still sorted by matches
  descending.** The club's order was asked for on the new grid; re-sorting a
  leaderboard-shaped summary was not, and quietly widening the change is how a
  screen someone relies on moves under them.
- **`unattributed` gets its own muted column, only when non-zero**, so the
  columns plus that column equal the TOTAL on every row and on the career line.
  The AFL grid's trade-off (season total ≠ sum of cells, documented in its own
  comment) is avoided rather than copied.
- **A historical bundle season is NOT special-cased.** `_HISTORICAL_BUNDLE_MATCH_CAP`
  hides those from `get_season_by_season`, but the by-grade table has always
  attributed their matches into grades, so excluding them here would make the
  grid disagree with the table above it — the worse of the two outcomes. A club
  with one will see a large early row.
- **Merge Grades is renamed Manage Grades** (nav label + the copy that names it;
  the URL `/admin/grades` and the in-page "Merge Grades" panel heading are
  unchanged, and the AFL silo's own screen is untouched).
- **Verified against a real Postgres** (41 checks through the shipped
  `get_player_team_breakdown`: the plain grid, the club's order with an unplaced
  grade last, a merged grade as one column under one position, a renamed grade,
  the mixed-history undercount, an unplaceable mixed-grade season, a
  single-grade gap, two merged seasons as one row, the season filter, a grade CA
  counts but we hold no scorecard for, a club that has never ordered anything,
  an empty player, and another club's order not reaching ours) and **driven in
  Chromium** (9: the column headings in club order, every rendered row and its
  dashes, the career line, the rendered rows and columns meeting at the same
  total, the grid agreeing with the table above it, no page errors, no overflow
  at 390px). The harness builds its tables from the ORM models and pulls the
  five `v_effective_*` views straight out of migrations 038 / 075 / 147 / 266.


## A player's date of birth, and who is told their age (migration 269, v9.37.0, Aug 2026)

Asked for so a selector can see a young quick's age while deciding bowling
workloads. `players.date_of_birth`, plus a club rule for whether BetterSelect
shows the age it works out to.

- **The AGE IS NEVER STORED.** `services/player_age.py` derives it on every
  read, because a stored age is wrong from the day after it is written and a
  volunteer who fills a birthday in once should not have to maintain it.
  `age_on` returns None for no date, a future date and anything past 120 years
  — all three mean "we cannot say", which a screen renders as nothing rather
  than as a number. The month/day tuple comparison is what makes 29 February
  turn a year older on 1 March in a non-leap year.
- **Nothing syncs a birthday.** CA's feeds carry none and PlayHQ redacts its
  juniors' names rather than dating them, so this is the club writing down
  what its own registration form already holds. Entered on the profile only.
- **The club's rule is applied SERVER-SIDE, in one place**
  (`player_age.visible_age`). `organisations.select_show_age` is off by
  default, and `select_show_age_under` is NULL for every player or an age to
  show it only BELOW. A club restricted to under-16s never sends an adult's
  age to a browser at all — the alternative, sending every age and telling the
  browser not to draw some, is a leak dressed as a setting. Two copies of "can
  this screen show an age" is how one screen ends up disagreeing with another.
- **The profile is the exception, deliberately.** It returns the date of birth
  itself and an ungated `age`: the club rule governs the SELECTION screens, not
  the record a `MANAGE_PLAYERS` admin is editing. It also returns
  `age_visible`, the gated answer, so a screen that has just saved a birthday
  corrects its own roster row to what everyone else sees rather than to the
  number the editor is looking at.
- **`select_show_age_under` is a genuine tri-state on the wire**, so
  `patch_settings` reads `model_fields_set`, not `is not None` — otherwise
  "every player" (a null) would be unsettable the moment a club picked an age.
  `clean_age_limit` turns 0, junk or an out-of-range number into that same
  every-player null, so the setting can never mean "show nobody" while reading
  as switched on.
- **Never public.** No `public_show_age` was added and none should be without
  asking: a date of birth is the personal data a junior's family is most
  likely to object to, and the ask was about selection. `clone_demo_club` does
  not copy it, alongside the contact details it already drops.
- **A native date input clips its own year the moment anything shares its
  row.** The first cut put the age beside the input in a half-width field and
  it measured 82px at 1400 and 22px at 1024. The age sits on the CAPTION line
  now and the field is full width: 274 / 129 / 316px at 1400 / 1024 / 390,
  comfortably wider than the neighbouring fields everywhere.
- **Verified against a real Postgres** (37 checks through the shipped route
  bodies: migration 269 applied three times to a populated pre-269 table, an
  existing club defaulting to off, both refusal guards leaving the stored date
  intact, a null clearing the birthday and a null clearing the age limit
  without switching ages off, an out-of-range limit storing as every-player,
  and the roster and selection payloads withholding an adult's age under an
  under-16 rule while carrying the junior's) plus 20 on the age maths itself
  (the leap-day birthday both sides of 1 March, and "exactly 16 is not under
  16"), and **driven in Chromium** (21: the picker hidden until ages are on,
  the exact params on the wire including the explicit null, the roster row,
  the profile field and its live age, the selection board's tag, no page
  errors, no overflow at 390px).
- **The Age filter offers only what the club's own rule can answer.**
  `ageFilterOptions` (selectionMeta.js) reads the `flags.age` echo the
  selection payload carries: no rule, no group at all — a dead control is
  worse than none, the same call the Fees and Training source notes make. A
  club limited to under-16s is offered thresholds up to 16 and NOT "18 and
  over" (no adult carries an age, so it would always be empty) and NOT "no
  date of birth" (under a limit a null means "an adult, OR nobody recorded
  one", which is two questions wearing one label). A fixed ladder rather than
  one option per age present, so "Under 16" is where a coach expects it week
  to week.
- **Not built**: any bowling-workload limit encoded in the app. What counts
  as too many overs for a fourteen year old is a policy call the club's own
  association makes, and a number we invented would be quoted back at us.

### The profile importer only knew the fields it was born with (v9.37.1)

Reported: Import player details was missing the date of birth. It was missing
eight fields — every profile column added after it was built. A field added to
`players` and to the profile editor does NOT reach this importer on its own,
and nothing failed to tell anyone.

- **`profile_import.VALUE_FIELDS` is the list, and `PLAYER_FIELDS` is what
  gets written.** Adding a profile column means adding to both, plus a
  `FIELD_LABELS` entry, a `SYNONYMS` block for auto-mapping, a branch in
  `row_profile`, a line in the router's `_current_profile` (or a sheet
  re-stating a value a player already has reads as a change), the two
  templates and the wizard's own `FIELDS`/`SIMPLE` maps. The suite asserts
  it structurally now: every field on `PlayerProfileUpdate` is either
  importable or on a short named list of ones deliberately left out
  (display name, PlayHQ id, skill positions, the non-player flag).
- **A date of birth is read four ways** — ISO, `4 Mar 2012`, `04/03/2012`, and
  an Excel serial — because `import_ingest` stringifies every cell, so an
  Excel date cell arrives as `"2012-03-04 00:00:00"` and a date column nobody
  formatted arrives as `"40972"`. **A slashed date is DAY FIRST**: this app
  serves Australian and British clubs, the parser has to pick one, and the
  column hint and template say which. The serial floor is deliberately above
  any 4-digit year, so a bare `1998` typed into a date column reads as
  unreadable rather than as 20 May 1905.
- **It refuses what the profile editor refuses**, through the same
  `player_age.dob_error` — a future date or one past 120 years is reported
  and the player left alone, so a bulk upload can't write a birthday the
  single-player form would reject.
- **A country on its own marks a player overseas**, since that is the only
  reading under which naming one means anything, but an explicit "No" in the
  overseas column still wins.
- **The two BetterSelect overrides can be SET from a sheet, never cleared.**
  A blank cell already means "leave this player alone" everywhere in this
  importer and it cannot also mean "back to automatic"; clearing stays a
  profile-screen action, and the field hint says so.
- **`FIELDS` had carried a hint per field since it was written and the wizard
  never drew it** — `FIELDS.map(([f, label, required]) => …)` dropped the
  fourth element. Harmless while the hints were "Male / Female", and not
  harmless at all for a date whose day/month order has to be stated.
- **The AFL silo's importer is a different, deliberately simpler one**
  (`routers/afl/player_import.py` — name, email, phone, gender, no squads,
  nothing auto-created) and is untouched.
- **Verified against a real Postgres** (69 checks through the shipped
  preview → resolve → commit bodies with a real uploaded sheet: every new
  field auto-mapped from a club's own header wording, both date shapes
  stored, an all-unreadable row changing nothing and reporting three notes,
  a re-upload of the same sheet proposing no further changes, and both
  templates round-tripping back through the importer's own parser) plus 24
  on the date and boolean normalisers, and **driven in Chromium** (24: every
  new field on the mapping screen with its hint, the before/after rows, the
  age beside the date, no page errors, no overflow at 390px).

### A `min-w-0` flex group whose children can't shrink OVERLAPS its siblings

Reported off the same screen: the Selection board's Dual rail / Team sheet
toggle was being painted over by the module pills and the Share button. Not a
z-index problem and nothing to do with the age work — the header's first group
carried `min-w-0`, so flex shrank the BOX below its content while the title
and the toggle inside it could not shrink. The overflow slid under the later
siblings, which paint on top. Measured, not eyeballed: the toggle's right edge
sat at 591px while its own group ended at 315px, and from 1100px down an
`elementFromPoint` at the centre of the last tab returned a module icon.

- **`min-w-0` belongs on the ELEMENT that may shrink, not the group.** The
  `<h1>` carries `truncate min-w-0` and the toggle carries `shrink-0`, so the
  group's automatic minimum is now "hamburger + toggle" and flex will not
  squeeze it past that. Putting `min-w-0` on the group instead is what removed
  that floor.
- **Shrinking alone was not enough and the fix is not one line.** With nowrap
  the overlap went away and the page started overflowing horizontally at
  ≤900px instead, and the module switcher was crushed to a 21px stub at 1024.
  `flex-wrap xl:flex-nowrap` is the answer: one row at ≥1280 (byte-identical
  to what it was, 65px), and below that the bar wraps rather than overlapping.
  The signed-in user's name + Logout moved from `sm` to `xl` for the same
  reason — ~110px of the least useful thing in the bar at exactly the widths
  where the bar has too much in it.
- **Every other BetterSelect screen is untouched** (53px, one row, no
  overflow at 1440/1024/390): only Selection passes `headerLeft`, so only
  Selection had the extra 214px to fit.
- **Verified by measuring at eight widths with the change stashed and again
  with it applied** — the baseline overlaps from 1100px down and never
  overflows the page; the fix overlaps nowhere and overflows nowhere. When a
  header looks crowded, measure `elementFromPoint` over the thing that is
  meant to be clickable rather than judging it from a screenshot.

## A net session is run from several devices at once (migration 268, v9.36.0, Aug 2026)

Reported: the same admin account open on a phone by the nets and a laptop in the
clubroom showed two different sessions. Plus: download who attended, put the
tally on the player's profile, and open it into the dates.

### The live session moved onto the server, and that is the whole change

- **It was a client-side state machine that pushed a debounced full-replace
  snapshot** (`PUT /nets/sessions/{id}/attendance`, the whole attendance list,
  700ms after the last tap). So the second device's check-in survived exactly
  until the first device's next write, which silently replaced the list with the
  one IT was holding. **Never reintroduce a full-replace attendance write** —
  replacing the list IS the bug.
- **Every change is a small, discrete write now** (check in, remove, mark
  batted, re-order, rotate, drive the clock), each bumping
  `net_sessions.version`, and every open screen polls `GET /sessions/{id}/live?since=`.
  Matching versions come back as `{version, server_time, unchanged: true}`, so a
  phone left open on the boundary costs one tiny query every 2.5s.
- **The version is bumped as `version = version + 1` IN SQL** (`_touch` assigns
  the SQLAlchemy expression, never `s.version + 1` read in Python). Two coaches
  tapping at the same moment would otherwise compute the same next value, and
  one device's change would land with the version unmoved — invisible to
  everyone else's poll. Verified by racing two real database sessions.
- **The clock is an absolute deadline (`live_state.ends_at`), not a local
  stopwatch.** Each device works out its own countdown from it against
  `server_time`, which rides on every poll — a phone an hour fast still stops
  the batter's turn at the same second as the laptop. A passed deadline READS as
  stopped for everyone before anyone writes it down (`_timer_payload` resolves
  `remaining_seconds` at read time), so the devices can't disagree while the
  write is in flight.
- **Rotating is the one action that must not repeat**, because doing it twice
  skips a whole group of batters. `RotateBody.turn_seq` is what the sending
  device was looking at; a request carrying a turn that has already moved on is
  ignored. Tapping "Next group" deliberately twice still works — the first
  response hands back the new turn number.
- **Auto-roll happens on the SERVER, inside the `expire` action**, not on
  whichever device noticed the clock run out. Every open screen notices within a
  second of each other, so a device-side rotation would race. `expire` is
  idempotent and refuses a deadline that hasn't actually passed, so a fast clock
  can't end a turn early.
- **A duplicate check-in is a no-op, not an error**, at two levels: an
  app-level existence check for the ordinary case, and `IntegrityError` on the
  partial unique for the genuinely simultaneous one. **The rollback path caught a
  MissingGreenlet**: `club.id` read after `db.rollback()` is a lazy load in the
  wrong place, so `club_id` is captured before the flush. Found by racing three
  simultaneous check-ins of one player, not by reading the code.
- **A stale re-order can't drop anyone.** `reorder_queue` takes the ids the
  sending device knew about and appends anyone it didn't — a player checked in
  from another phone a second earlier keeps their place at the back rather than
  vanishing.
- **`position` is re-laid as 0..n-1 after every mutation** (`_renumber`), over
  the canonical order (still waiting first, then those who have batted). Sending
  someone back to the queue puts them at the END, which is what "they need
  another go" means.

### The lists a club can take away

- **`GET /nets/sessions/{id}/attendance.csv`** is the register for the night and
  **includes guests** — a trialist who came along is part of who turned up.
  Offered on the live screen and on every past session row.
- **`GET /nets/reports/attendance.csv`** is the per-player report and
  **excludes guests**, because it is keyed on real players and links to their
  profiles. Same split the on-screen report already made.
- **`days=0` means all time** (the range param went `ge=1` → `ge=0`), which is
  what "how many has he been to" actually asks. The `since` filter is a
  `CAST(:since AS date) IS NULL OR ...` — the asyncpg bare-`:param IS NULL` trap
  the vote-medals note describes.
- **Downloads are plain `<a href>`**, so the session cookie rides along and
  there is no blob to build and hold. `Btn` gained `href`, since a link inside a
  button is markup no browser agrees on — which is also why the session ROW
  became a div with `role="button"`.

### The tally opens into the dates

- **`GET /nets/players/{id}/attendance` returns every session** (capped at 500),
  not the eight it used to. `attended` is now the length of that list rather
  than a separate COUNT, so the number and the dates behind it cannot disagree.
- Clicking the tally expands it in place on the player profile
  (`NetAttendanceStat`, shared by BetterSelect Players and Admin → Players) and
  opens a modal from the Nets report. The modal deliberately reads the player's
  WHOLE history, not the window the report is showing — a coach clicking a
  number is asking about the person, not about the last 90 days.

### Verification

**67 checks against a real Postgres** through the shipped route bodies
(migration 268 applied three times to a populated pre-268 table and matching the
lifespan mirror, which is read out of `main.py` rather than retyped; the poll's
cheap answer; the duplicate check-in; the stale re-order; the rotate turn guard;
the early-expire refusal; server-side auto-roll and the second device's expiry
rotating nobody; a mid-turn duration change not jumping the batter's clock; the
guest split between the two CSVs; cross-club rejection on every read and write),
**including 5 that race two genuine parallel database sessions** — twelve
check-ins interleaved with none lost and the version landing on exactly 12.

**31 checks driven in Chromium** against the real router and a real Postgres,
with TWO browser contexts on one session: check-ins crossing between them
untouched, both clocks agreeing within two seconds, pause on one stopping the
other, a rotation moving the batters on both, a screen woken from a pocket
catching up at once, both downloads' contents and filenames, the report's
columns and All time, and the tally opening on the profile. No page errors, no
overflow at 390px on any of the three screens.

## A club runs several medals, in both sports (migration 267, v9.33.0 / v9.34.0, Aug 2026)

`vote_settings` had `organisation_id` as its PRIMARY KEY, so a club held exactly
one ballot shape, one voter mode, one counting method and one public link. A
club running a Club Champion on 3-2-1 alongside a Colts medal on 5-4-3-2-1 had
no way to express it, and its two counts could only be told apart by filtering
the one leaderboard down to a grade after the fact.

### `vote_medals` is the record, and `vote_settings` is history

- **Every settings column moves across UNCHANGED IN NAME**, which is what lets
  `votes.effective_config` read a medal with no edit. Plus `name`, `grade_ids`
  and `position`. `vote_settings` is left in place and **nothing reads it after
  267** — the same call migration 230 made for `club_objectives.plan`.
- **A ballot belongs to ONE medal** (per direct instruction). A fixture counting
  towards two collects a separate ballot for each, so a 3-2-1 medal and a
  5-4-3-2-1 medal can genuinely disagree about who was best. The two "one live
  ballot per voter per fixture" partial uniques are rebuilt with `medal_id` in
  front, and `vote_fixture_overrides` moves from a `fixture_id` primary key to
  `(medal_id, fixture_id)` — locking a count is a decision about that medal, not
  about the fixture in the abstract.
- **GRADES ARE PER-SEASON ROWS, so a medal must not match on stored grade ids.**
  Next season's "Colts" is a different id, and a medal keyed on ids alone would
  silently stop counting the day the new season's grades are created —
  mid-rollover, with nothing to see. `medal_grade_ids` expands the stored ids
  through their NAMES to every grade of that name in the club, which is what
  makes a medal a standing award. The picker therefore offers each grade NAME
  once (`club_grade_options`), not once per season, and each medal reports its
  `grade_names` so a screen can re-tick a selection whose stored id belongs to
  an older season's row. **An EMPTY `grade_ids` means EVERY grade** — that is
  what a club's only medal means before anyone has thought about grades, and it
  is what the migrated row has to mean so an existing count doesn't narrow.
- **A grade-restricted medal's screens drop the fixtures it doesn't count**
  rather than showing them at zero ballots, which reads as "nobody voted"
  instead of "not part of this count". Resolve grades BEFORE narrowing, or a
  fixture carrying its grade only on its synced game falls out of every
  restricted medal (`effective_grade_ids` is the fallback).
- **An existing club keeps everything.** Its settings row becomes its first
  medal, `link_token` included, so ballots already cast still count and the link
  already in players' hands still works. A club with ballots or overrides but no
  settings row (an admin typing paper votes never opened the settings screen)
  gets a medal too, or the `NOT NULL` would have nothing to point those rows at.
- **The DDL lives in ONE list both alembic and the lifespan run**
  (`services/vote_medal_ddl.py`), in the same order, so the two copies cannot
  drift. Every statement stays idempotent because the lifespan re-runs the whole
  list on every boot; the backfills are no-ops once a club has a medal.
- **`merge_players`' ballot de-dup needed the medal in its key.** It matched on
  fixture alone, so merging two records of one person who had voted for both
  medals on a fixture would have deleted one of their two legitimate ballots.
- **`main.py`'s mirror deliberately no longer creates the two OLD per-fixture
  ballot uniques.** 267 drops them a few statements later, and rebuilding a
  unique index over the whole table on every API restart just to drop it again
  is real cost for nothing.

### asyncpg cannot type a bare `:param IS NULL`

Found by the verification, and it would have 500'd in production: an optional
filter written as `(:medal IS NULL OR medal_id = :medal)` raises
`AmbiguousParameterError` at execute time — asyncpg infers a bound parameter's
type from how it is used and that gives it nothing. **Any "param IS NULL OR col
= param" needs an explicit `CAST(:param AS uuid)`.**

### BetterFootball got the same engine, and a team-list service (v9.34.0)

- **The counting rules are IMPORTED from `services/votes.py`, never re-typed.**
  `tally_ballots`, `award_weekly_points`, `clean_ballot_values`,
  `round_sort_key` and the vocabularies are pure functions with no cricket in
  them. A second copy is how the two sports start disagreeing about what a
  countback is. Change a rule there and both sports move.
- **Football's ballots key on `games` directly** — cricket keys on `fixtures`,
  BetterSelect's own scheduling table, which the AFL silo has no equivalent of.
- **There is no eligibility SOURCE to choose.** Cricket picks among the
  scorecard, a saved XI and the published side. Football has one team list, and
  the sync already stores it: PlayHQ's
  `gameView.statistics.{home,away}.players[]` becomes `afl_player_game_lines`,
  both sides, with jumper number and captain flag. So
  `services/afl/lineups.py` is a plain read of held data — no upstream call, no
  cache, and it keeps working when PlayHQ is down. **Scope every team-list read
  to `afl_game_details.our_side`**: the opposition's own named side sits on the
  same game row, so a read that forgets is one that lists them as ours.
- **A season is the `seasons` row the game's grade belongs to**, not cricket's
  Jul→Jun window. Football runs inside one calendar year, so the summer-spanning
  maths would file a whole season under the wrong label.
- **`publish_lineup` was already selected by the gameView query and discarded.**
  Stored now, because it is what separates "this club never named a side" from
  "we haven't synced this game" — both render as an empty list, only one is
  worth chasing.
- **Post-game only, per direct instruction.** The sync only fetches games PlayHQ
  marks FINAL, so a scheduled match reads as not played rather than as a side
  nobody named. Pulling a pre-game side would mean a gameView call per upcoming
  game per sync.
- **No AFL lifespan change was needed**: `create_all` makes the new ORM tables
  and `_sync_missing_columns` self-heals `afl_game_details.publish_lineup`.
- **Capabilities are shared**, so `MANAGE_VOTES` / `VIEW_VOTE_RESULTS` gate the
  football surface with no new vocabulary.

### Verification

Cricket: 59 checks against a real Postgres through the shipped statements and
route bodies (267 applied three times to a populated pre-267 table, the link
token and settings carried across, the old uniques gone and the new ones holding
both ways, the two counts staying apart, per-medal overrides and nudge
cooldowns, next season's grade of the same name still counted, the delete
guards) and 17 driven in Chromium. Football: 47 and 27.

**Both harnesses build their tables from the ORM models**, never by hand — the
one exception being the five vote tables in the cricket suite, which have to
start in their PRE-267 shape for the migration to have anything to do.

Three real findings came from running them rather than reading the code: the
asyncpg cast above, the self-vote rule refusing a fixture whose voter picked
themselves, and rank conversion (the default) not being a raw tally — three
voters all giving 3-2-1 to the same three players is still 3+2+1 for that game,
not 18.

**Noticed, NOT fixed**: the cricket Games hub's filter row overflows at 390px (a
`ml-auto` select reaching 446px). Confirmed pre-existing by re-running the same
check with the change stashed — identical element, identical width.

## A washout is not a match played (migration 266, v9.32.1, Aug 2026)

Reported off Hamilton Veterans: Geoff Barker's 25/26 reads 13 matches, the club
counts 10, and three fixtures were washed out.

- **Nothing was miscounting. `player_season_stats.matches` is CA's own
  `statistics.matches`, copied verbatim** (`sync.py`'s season-stats upsert),
  and CA's answer really is 13. **CA counts a player as having played the
  moment they are on the team sheet**, ball bowled or not. Verified live rather
  than reasoned about: the club's 25/26 card is 14 fixtures, three
  `status: ABANDONED`, and a team-mate named in all of them reads 14.
- **The comment in `aggregations.py`'s opposition breakdown claiming CA already
  excludes abandoned games is wrong**, and was wrong before this. It is
  corrected in place. Do not build on it.
- **`games.status` (migration 266) exists because `result` cannot answer the
  question.** A NULL result covers a washout, a fixture still to be played, one
  in progress and one we could not classify, all four. The column takes CA's
  own word verbatim.
- **The correction lands in `v_effective_player_season_stats`, not in the
  callers** — the same one-place discipline migration 060 used for the
  cross-club leak, so career totals, the season table, the leaderboards and
  records all move together and a club with no washouts joins an empty set and
  is byte-for-byte unchanged.
- **The rule is "named and recorded nothing at all", not "abandoned".** A game
  called off at tea with a hundred on the board was played and the club counts
  it, so the subtraction only fires where the player has no batting, bowling or
  fielding row for that fixture. `NO RESULT` (statusId 5) is deliberately NOT
  in `NOT_PLAYED_STATUSES` for the same reason — that is a game that started.
- **`services/game_status.py` is the one vocabulary**, shared by the sync, the
  view, the read paths, the backfill script and (as a mirrored constant) the
  two screens. Two copies of "which statuses mean it never happened" is how
  they start disagreeing.
- **The view was NOT enough, and this is the lesson.** Correcting
  `v_effective_player_season_stats` fixes every reader that sums CA's season
  aggregate, and misses every reader that counts matches from
  `game_appearances` itself — which is what StatLab does. Reported live:
  StatLab still read 13 after the platform-wide figure was already 10.
  `appearance_counts_as_match(alias)` is the shared predicate, applied at
  **five** sites found by auditing every `game_appearances` read rather than
  assuming: StatLab's `appear` CTE (the only source of its `matches`), the
  by-grade and by-season-grade breakdowns, by-venue, and the FORMATS page.
  **When adding a screen that counts matches, ask which of the two sources it
  reads.** By-opposition needed nothing — it already drops a result-NULL game.
  The recent-games lists at `aggregations.py:511/553` are deliberately left
  alone: a fixture list should show a washout a player was picked for.
- **No Full Rebuild.** The grade match list already carries `status` per
  fixture and the discovery loop already fetches it, so a plain Sync Now fixes
  the current season through the same bulk pass `is_final` and `match_format`
  use. `python -m app.scripts.backfill_game_status <org-id-or-slug|all>` covers
  the seasons an incremental run no longer scans.
- **A club whose season rows came from "Fix Missing Totals" needs it re-run.**
  Those rows (`source = 'backfill'`) store a count computed from per-game rows
  rather than reading CA's, so the view's correction cannot reach them. The
  rollup's `appearances` CTE now excludes called-off fixtures; the script says
  when a club has such rows.
- **Scale, measured before building rather than assumed**: 316 of 4,165
  fixtures across all 102 clubs' latest season carry no result; ~88% of a
  sample are genuinely ABANDONED/CANCELLED and about half of those have a team
  sheet. So ~140 fixtures a season platform-wide, across ~45 clubs. Invisible
  at a club playing 380 fixtures, glaring at one playing 14 — which is why a
  veterans club found it and nobody else had.
- **Found while verifying: `CREATE OR REPLACE VIEW` cannot DROP a column.**
  The first cut of 266's downgrade replaced the status-carrying
  `v_effective_games` with the shorter prior definition and failed outright.
  It drops and recreates now. **Migration 169's own downgrade has the same
  latent defect** and would fail the same way; it has simply never been run.
- **Verified against a real Postgres** (24 checks through the shipped view and
  the real service functions: the reported 13 → 10 and a team-mate's 14 → 11, a
  control club-mate unchanged, CA's stored row never rewritten, a mid-play
  abandonment staying counted, a NULL status subtracting nothing, NO RESULT
  still counting, CANCELLED behaving like ABANDONED, the rollup, the scoped
  path, the season-by-season table and career games both reading 10, the
  Matches screen's list, migration 266 applied three times to a populated
  table, and the downgrade putting CA's figure back).

## BetterFootball: a re-graded team's first rounds, club competitions, navbar search, splitting a player (migration 262, v9.30.0, Aug 2026)

Four things reported off Hampton Hammers' page. The first is the one worth
remembering.

### `discoverTeams` reports the grade a team is in NOW, and that loses rounds

Reported: Hampton's Under 19s show from round 6 of 2026 and the first five
rounds are simply absent. They opened the year in **Under 19s Division 1** and
were re-graded to **Division 2** from round 6.

- **Nothing was broken. The grade was unreachable.** `discoverTeams` answers
  with each team's CURRENT grade and carries no history at all, so the division
  the side started in never enters `grade_infos`, `_discover_grade_games` is
  never pointed at its fixture, and those games are never discovered. Verified
  live: `discoverTeams(season aea5195c, org f0727a8b)` returns exactly three
  teams, the U19s under Division 2 alone.
- **`discoverTeamFixture(teamID)` is the fix and it WORKS on the AFL tenant**
  (it does not on cricket's Grassroots API, per the note further down about the
  two APIs disagreeing). It returns the team's whole season round by round with
  **the grade on each round**, which is the only place PlayHQ says a team
  changed division. For the U19s it returns 19 rounds: 5 in Division 1
  (a9823a21) and 14 in Division 2 (c1d73395).
- **`_former_grades_for_team` filters two ways, and both are load-bearing.**
  Every game in a round comes back, not just ours, so it keeps only rounds where
  the team id is actually one of the two sides. And it drops a grade whose
  `round.grade.season.id` is not the season being synced, so a team id PlayHQ
  reuses across years can't drag another season's grade in.
- **A former grade becomes an ordinary entry in `by_grade`**, so the existing
  game-discovery walk picks it up with no special-casing, and a plain **Sync
  Now** is what pulls the missing rounds in. What it must NOT do is move the
  team ROW: `afl_teams.grade_id` holds one grade, and that is the division the
  side is in now, so `is_current` guards the write. Current grades are inserted
  into `by_grade` first, so a brand-new team row is always created under its
  current grade.
- **`link_grade_manually` (paste a PlayHQ match link) still exists** and is
  still the way in for a grade even this can't see. It is no longer the only
  way, which is the point: nobody knew to use it.
- **`stats["former_grades"]` counts what was found**, so a re-grade the club
  never mentioned reads as something the sync discovered rather than an
  unexplained jump in the grade count.
- **Verified against live PlayHQ** through the shipped functions: the reported
  pair found (`{'a9823a21': 'Under 19s Division 1'}`), nothing found for the
  Seniors or Reserves (no false positives), the current grade never re-reported
  as a former one, the season guard, and the Division 1 fixture yielding exactly
  the 5 missing Hampton games, rounds 1 to 5.

### `organisations.competitions` (migration 262)

- **The same `{name, from_year, to_year}` shape as `previous_names`, sharing
  ONE validator** (`club_history._clean_year_spans`) rather than a second copy
  of rules about what a year is. Its own column because a club changes
  competition far more often than it changes its name.
- Shown beside the season picker on the dashboard, not under the club name: the
  left column is the club's identity, and a league list is what the page is
  scoped by, like the season. Renders nothing when a club has filled none in.
- **Only the seasons PlayHQ ran are synced**, so a league a club left before
  that has no other way onto the page, and the settings copy says so.
- Verified against a real Postgres (12 checks: migration 262 applied three times
  to a populated table, an existing club reading NULL, the trim/coerce/backwards-
  span rules through the real settings routes, competitions and former names not
  disturbing each other, the public payload, and clearing storing NULL rather
  than `[]`) and driven in Chromium (15, against the LIVE club payload with
  competitions injected: the card in the reported empty space above the season
  picker, a closed span, an open-ended one, no empty bracket on a yearless one).

### Splitting a player, and the merge bug it uncovered

Reported: "Graeme Cole" holds 1961-64 AND 1988-89 and was never merged. He never
was: **Import Stats resolves a sheet row to a player by NAME**, so a father and
son land on one record and there is no merge to undo.

- **A SEASON is the unit that moves.** Every AFL stat hangs off one, and two
  people's playing years under one name do not overlap. Moves
  `afl_imported_stats`, `afl_player_game_lines` (via their games' season) and
  `player_achievements`, then recomputes `afl_player_season_stats` with the
  sync's own rollup, exactly as a merge does.
- **No undo log, deliberately.** A split leaves two records with the same name,
  which is precisely what Merge Players lists as an exact-name pair, so merging
  them back IS the undo and it is already built.
- **An honour's `season` is free text holding EITHER the season's id (the Awards
  screen) or its name (an import)**, so the split matches both rather than
  assuming one.
- **The new record deliberately gets no `playhq_id`** — that belongs to whoever
  the sync has been matching all along, and handing it over would put the next
  sync's games on the wrong man.
- **Splitting off EVERY season is refused.** That is a rename with extra steps,
  and it would leave the original record empty.
- **The bug this uncovered, and it was live: `_merge_players_core` only ever
  moved the game lines.** `afl_imported_stats` and `player_achievements` are
  raw-SQL tables carrying a bare `player_id` with NO foreign key, so nothing
  moved or cleared them and they were left pointing at a deleted player — where
  every read that joins `players` (career totals, the profile, the leaderboards)
  drops them without a word. **A BetterImport club lost the removed player's
  whole career to a routine duplicate merge.** Both now move with the rest, and
  their ids are recorded on `afl_merge_logs` (two new JSONB columns, mirrored
  idempotently) so the undo hands back exactly those rows. A log written before
  those columns existed reads as `[]`, which is the right answer for it.
- **Verified against a real Postgres** (28 checks through the shipped route
  bodies: the reported career split at the right year, the preview's ordering
  and counts, three guards, an unattributable seasonless imported row staying
  put, another club's row never touched, each honour following its own career,
  the two halves coming back as an exact-name merge pair, and the round trip
  split → merge → undo landing byte-for-byte on the original) and driven in
  Chromium (16).

### Player search in the navbar

`AflPlayerSearch` is BetterCricket's `NavbarPlayerSearch` pointed at the AFL
roster and the club-scoped `/{slug}/players/{id}` route. The roster is fetched
once and filtered locally, same as cricket. Each result carries games and goals,
because a football club has several people with the same name and the numbers
are what tells them apart. **The navbar's breakpoint moved from `md` to `lg`**:
with a search box in the bar there is no room for six links at 768px, and
splitting the two would have left that width with neither.

## StatLab gets the platform's Grade Type / Match Type filters (v9.29.4, Aug 2026)

StatLab was the last stats surface with no `GradeScope` (migration 259). Two
consequences, and the second is the one that mattered: there was no way to ask
it for the T20s or the women's grades, AND it counted every grade whatever the
club had set, so a club that leaves juniors out saw StatLab disagree with its
own Leaderboard.

- **StatLab now applies the club default like every other screen, and that is a
  deliberate behaviour change.** `categories=None` means "the club's default"
  everywhere else, so it means that here too. A club with junior grades will see
  StatLab's unfiltered figures drop to match the Leaderboard's, including inside
  a saved report written before this. The Grade type control says what the
  default leaves out ("Club default (no Juniors)") rather than reading "All",
  and the results carry `scopeNote`'s own line, the same one Records shows.
- **The resolved scope rides in the context dict under `_scope`, and that key
  can never arrive from a browser.** `_ctx_from_request` only ever writes keys
  from its own whitelists and none of them start with an underscore, so a
  crafted URL cannot hand the query builder a scope of its choosing. Doing it
  this way meant two touch points instead of threading a new argument through
  all ~30 `_build_context_filters` call sites.
- **`_scope_fragment` exists because the two sides format differently.**
  `GradeScope.clause()` hands back a fragment with a leading ` AND ` for callers
  that paste it into a WHERE; StatLab keeps conditions in a list and joins them
  itself, so the AND comes off. Every condition inside is already bracketed, so
  what is left composes.
- **`kind` per read, exactly as the platform rule says.** `game_universe` gets
  `clause("g.grade_id")` (per-game: category off the grade, format off each
  fixture's own `match_format`, which is what stops a grade that plays both
  formats filing all its games under one). The residual CTEs and the three
  aggregate-only queries get `clause("pss.grade_id", "aggregate")`, which emits
  `AND FALSE` under a match-type filter rather than counting an imported season
  towards a T20 record it can say nothing about.
- **The three aggregate-only queries had to be found, not assumed**:
  `query_family_career`, `query_family_season` and `derived_most_minutes_in_season`
  sum `player_season_stats` directly and never touch `game_universe`, so the
  clause `_build_context_filters` adds would have missed them entirely and the
  filter would have read as working while doing nothing. Same class of gap as
  the `_pss_season_filter` one the release before. On family_career it goes in
  the JOIN condition, not the WHERE: a family whose every row is out of scope
  should still list at zero rather than disappear.
- **An active scope sets `any_match_used`,** so the aggregate-path targets
  (player_career, player_season) switch to live per-innings aggregation. A scope
  is only answerable from per-game rows, and this is the same trade
  `records.py`'s `use_game_level` makes with its own `scope_active`.
- **A match type genuinely cannot be answered by Family career / Family by
  season, and the screen says so** instead of showing an unexplained empty
  table. Those two have no per-game path at all.
- **The picker offers only what the club runs.** `GET /organisations/{id}/grade-categories`
  (public, cheap, already there) supplies `available` / `default` /
  `available_formats`; a club with no junior programme is never shown a Juniors
  tick box, which is also exactly when the filter would do nothing.
- **On the wire they are ONE comma-separated string each** (`?categories=senior,womens`),
  not a repeated param, because that is the shape every other stats endpoint
  takes and what `resolve_scope` reads. So they stay plain text context keys and
  the picker splits and joins around them — the opposite call to `grade_names`,
  which is repeated precisely because a grade name can contain a comma and these
  fixed keys cannot.
- **Verified against a real Postgres** (19 checks through the real `resolve_scope`
  and the shipped StatLab builders: the club default leaving juniors out, an
  explicit junior pick finding them, one mixed grade splitting 1 two-day / 1
  one-day / 1 unplaceable, an unlabelled game inheriting a single-format grade's
  format but NOT a mixed grade's, every-format reading as no filter, the two
  axes composing with each other and with a picked grade, residuals kept under a
  category scope and emptied under a format one, and a senior-only club emitting
  no clause and binding nothing) and **driven in Chromium** (35 checks, the 26
  from the multi-select release plus the two new pickers: the club-default
  label, only the offered types, the exact params on the wire, both chips,
  dismissing one, the left-out note, and a shared link opening with both ticked;
  no page errors, no overflow at 390px).
- **Noticed, NOT fixed**: Family career and Family by season ignore every OTHER
  context filter too (opposition, result, dismissal, a picked grade). They sum
  season aggregates and predate the live per-innings path the player targets
  use. That is a pre-existing gap, not one this release introduced.

## StatLab's list filters take several values at once (v9.29.2, Aug 2026)

Reported: StatLab could only ever be scoped to ONE grade, so "most runs across
1st and 3rd Grade" was unanswerable. A range picker was the obvious shape and is
the wrong one — the whole point is dropping a grade out of the middle of a run.

**The rule that decided the scope: a filter whose values come from a KNOWN LIST
gets the tick-box picker; everything else keeps the control it had.** So Grade,
Season, Result and Dismissal are multi-select (`grade_names`, `season_ids`,
`results`, `dismissals`); opposition, player role and the award fields stay free
text (there is no list to tick), the year and position fields stay ranges, and
Gender / Overseas stay single because ticking every option there IS "no filter".

- **`grade_names` (a list) is the new filter; `grade_name` (single) stays.** The
  UI writes `grade_names` and clears `grade_name` in the same update, so the two
  can never disagree; the single key is kept because a saved report and a shared
  link written before this shipped both carry it. If both arrive anyway they
  AND, which is what a link the user then added to should do.
- **It is NOT a new spec-dict entry.** `MATCH_CONTEXT_FILTERS` values are one
  fixed SQL string with one bound param, and this clause grows with the
  selection, so it lives in `_build_match_list_filters` beside the `season_ids` /
  `grade_ids` id filters that already worked that way. Same expression the
  single-value filter compares (`COALESCE(am.canonical_name, gr.name)`), so a
  merged grade still resolves through its canonical name.
- **`_text_list` deliberately does NOT comma-split, and the router gives text
  lists their own reader.** The id lists accept `?grade_ids=a,b` because a UUID
  can't contain a comma; a grade name can ("A Grade (Smith, Jones)" is real
  enough — a sponsor suffix does this), and splitting it would quietly turn one
  grade into two that match nothing. `_CTX_KEYS_LIST_TEXT` reads the repeated
  param only. The URL is `?c_grade_names=…&c_grade_names=…` for the same reason.
- **Residuals answer it, and their halves are ORed.** `_residual_grade_match`
  took a `suffix` so each ticked grade binds its own param; the clauses are ORed
  inside one bracket, since ANDing them asks for a row that is two grades at
  once. `grade_names` is not in `_RESIDUAL_DISQUALIFYING_MATCH_KEYS` for the
  same reason `grade_name` isn't — an imported or manual row carries its grade.
- **A selected grade that is no longer in the club's list still draws a row** in
  the picker (renamed, merged away, arriving from a saved report), so it can be
  seen and un-ticked instead of silently scoping the query from nowhere.
- **`results` and `dismissals` reuse ONE definition of their SQL, extracted.**
  `_RESULT_CASE_SQL` and `_dismissal_match_sql(param)` are now shared by the
  single-value spec entry and the multi-select builder, because two copies of a
  CASE that size drift the first time one is edited. The dismissal CASE takes
  its bind param BY NAME so each ticked value gets its own.
- **`dismissals` lands in the INNINGS block, and that is what keeps residuals
  honest.** `_residual_disqualified` treats any innings clause as unanswerable,
  so putting the clause in `ic` costs nothing extra. `results` needed its own
  entry (`_RESIDUAL_DISQUALIFYING_LIST_KEYS`) since it has no spec entry to read
  a `value_kind` from — and it **coerces before disqualifying**, or a selection
  that is entirely junk would filter nothing while still knocking residuals out.
- **Season multi-select was supported server-side all along and one query had
  never been told.** Three queries aggregate straight off `player_season_stats`
  rather than through `game_universe` (player_season's aggregate path,
  family_season, batting minutes), so they each carry their own season clause —
  and `query_family_season` only ever honoured the single `season_id`. Shipping
  the picker would have meant a multi-season pick working on four screens and
  silently doing nothing on Family by season. All three go through
  `_pss_season_filter(context, params, prefix)` now.
- **The Season chip is labelled the way the picker labels it** (`formatSeason`,
  so "2025/26"), not the season's stored `name` ("Summer 2025/26") as it was.
  A chip should read back what was ticked.
- **Verified against a real Postgres** (33 checks through the shipped builders'
  own SQL: two grades returning exactly those two, one grade matching the old
  single-value result byte for byte, a merged grade pulling in its alias' games
  and its alias-tagged residual rows, the comma-carrying name, an unknown grade
  returning nothing rather than everything, the residual halves ORing rather
  than ANDing, both results and both seasons, caught counting the keeper's catch
  as well, a junk value filtering nothing AND not disqualifying residuals, and
  the shared pss season clause honouring a multi-season pick) and **driven in
  Chromium** (26: the exact params on the wire for all four pickers, each chip's
  wording, dismissing one clearing both keys, un-ticking one of three, the
  search box, an old single-value link on each filter still opening pre-ticked
  and handing over cleanly once a second value is added, no page errors, no
  overflow at 390px).
- **Noticed, deliberately NOT fixed**: the Result filter offers "Tied" and can
  never match it. `games` carries a winning team or it doesn't, so the CASE only
  ever emits won/lost/drawn and a tie is indistinguishable from a draw. Fixing
  it is a data-model question, not a filter one.

## A duplicate whose first name is shortened is invisible to edit distance (v9.26.1, Aug 2026)

Reported from the Leaderboard: "Brad K Mant" (15,542 runs) and "Bradley Mant"
(10,341, same high score of 194) are one person, Manual Merge finds them in a
second, and Merge Duplicates never suggested them.

- **Nothing was broken — the pair scores 0.78 and the gate is 0.90.** They pass
  every other gate in `_fuzzy_name_pairs` (same first-letter block, length
  difference 1), so the miss is purely the threshold.
- **Edit distance degrades MULTIPLICATIVELY, which is the whole lesson.** Two
  differences stack here: a short form and a middle initial. Alone, `brad mant`
  vs `bradley mant` is **0.857** and `brad k mant` vs `brad mant` is **0.90** —
  either would have been caught. Together they are **0.783**. So a
  two-difference duplicate is not "slightly harder" to catch than a
  one-difference one, it is off the scale, and **lowering
  `FUZZY_MERGE_THRESHOLD` is not the fix** — 0.78 across a 1,500-player roster
  buries the real pairs in strangers.
- **`_name_variant_pairs` compares the name's PARTS instead of the whole
  string**, blocked on (surname, first initial) — free, because every rule in
  `_first_name_link` already requires the first letter to agree. It is a THIRD
  tier (`kind: "name_variant"`), beside exact and fuzzy, not a loosening of
  either.
- **`_first_name_link` is deliberately narrow: a bare initial, or a genuine
  prefix of at least 3 characters.** A nickname that is not a prefix
  ("Bob"/"Robert", "Bill"/"William") is NOT claimed. It would need a curated
  list, and every entry on such a list is a judgement call that produces a
  confidently wrong pair the day it misses. Two characters is too short —
  "Jo"/"John"/"Joe" are three people.
- **Never bulk-mergeable, and that is not caution for its own sake.** A surname
  plus one initial is exactly the shape of two brothers, or a father and son.
  The screen says so in the badge rather than implying a match it cannot make.
- **`_name_parts`/`_middles_compatible` are IMPORTED from
  `services/import_ingest.py`**, not re-typed. That module is the
  historical-import matcher and already decides whether two sets of middle
  initials could be one person; a second copy is how the two start disagreeing
  about what a name is. It is DB-free, so importing it into a router is cheap.
  **Its own `match_players` would ALSO have missed this pair** — the first+last
  tier needs identical first names, and `_parse_initial_form` needs a bare
  single-letter token in first or last position, which "Brad K Mant" (initial in
  the middle) does not have.
- **Detection grouped on `p.name` while the cards render `p.display_name`.**
  So a renamed player was only ever compared under the name the sync wrote, and
  their duplicate read as unlisted even though both cards on screen said the
  same thing. `_name_keys(p)` files a player under BOTH spellings; a player
  therefore enters several blocks, which is why the fuzzy pass now keeps the
  BEST ratio per pair rather than whichever was reached first, and why the
  endpoint carries an `emitted` set so one pair cannot be listed twice.
- **Bulk Approve is an allowlist now (`isExactPair`), not `kind !== 'fuzzy'`.**
  The denylist meant this new tier would have been silently bulk-mergeable the
  moment it shipped. A tier added later must be manual-confirm by default.
- **Verified** against the real shipped functions (39 checks: the reported pair,
  every shape it should and should not catch, the ignore and de-dup rules, one
  read per player however many pairs they are in, and 8ms over a 1,500-player
  roster returning 1 pair) and **driven in Chromium** (16: all three tiers'
  labels, the reason text, Bulk Approve counting only the exact pair, no page
  errors, no overflow at 390px).
- **Not addressed**: `_enrich_player` counts `player_season_stats` and
  `batting_innings` only, so a BetterImport club's player reads 0/0/0/0 on these
  cards even when they have a career in `imported_stats` (the
  `_RESIDUAL_SOURCES` split the junior-stats note describes). That is a display
  gap on the merge screen, not a detection one.
## A grade is several things at once, and the dashboard filters on that (migration 259, v9.26.0, Aug 2026)

Reported off the club dashboard: the GENDER filter should be a **Grade Type**
filter (Men's / Juniors / Women's / Masters), T20 needs to exist, a grade should
be able to hold several classifications at once, there should be a second
**Match Type** filter (Two Day / One Day / T20), and the CAPTAIN filter should
go.

- **The Gender filter was reading a player attribute to answer a question about
  the grade.** `p.gender` is free text, every writer stores it lowercase, and
  the leaderboard SQL compared `p.gender = :gender` against the `'Male'` /
  `'Female'` the pill sent — so it returned an empty board wherever it was
  actually wired, and on the dashboard it was a **dead control** (no state, a
  no-op setter). Same for CAPTAIN there, and on Players, Games and Ladders.
  Those pills are off on all four screens now. **Gender is left in place on
  Leaderboard and Records**, where it is wired; the casing bug is theirs and was
  not chased here.
- **`grades.categories` and `grades.match_formats` (TEXT[], migration 259)**,
  and **`grades.category` stays and is kept in step with the first entry of
  `categories`** in canonical order. That is what makes this additive: the
  public grade grouping, `grade_labels.org_grade_categories`, the AFL silo's own
  single-label readers and everything else that reads one value are untouched.
  Send `category` alone to `PATCH /admin/grades/classify` and it still works.
- **The two axes resolve into ONE `GradeScope` and one exclusion list**, so
  adding a whole second filter changed no query — `resolve_scope` gained a
  `formats=` argument and every one of the ~25 `scope.clause(...)` call sites is
  as it was. A grade has to pass both tests to stay in.
- **The axes fail differently on an unclassified grade, deliberately.** Every
  grade has a category (the name suggestion bottoms out at men's senior), so
  that test always has something to judge. A grade's FORMAT is often genuinely
  unknowable, so a grade we cannot place is left OUT of an explicit format
  filter rather than swept in — asking for T20 and being shown everything the
  club has ever run is worse than being shown what we can vouch for.
- **Format is derived, not asked for.** `org_grade_format_sets` falls: what the
  club ticked → **the formats actually recorded on that grade's games
  (`games.match_format`)** → the grade name. The middle step is the one that
  matters: it is accurate for a single-format grade and needs no admin action,
  which is why most clubs will find their grades already right. `fee_format` is
  read too, but `'exclude'`/`'women'` are billing answers and map to nothing.
- **`format_from_match_type` returns None for an unrecognised string, and must
  keep doing so.** `fees.derive_fee_format` has to pick something ("everything
  else is a single day") because a match day must be billed; a filter that
  cannot tell has to say so instead.
- **An explicit pick matches ANY of a grade's categories; the club DEFAULT
  matches only the primary one.** Load-bearing, and the browser found it: with
  ANY-matching everywhere, a "Girls Under 16" grade sneaks back into a default
  that leaves junior out, on its women's half — junior seasons back inside
  senior careers, which is the exact bug migration 228 exists to prevent. An
  explicit "show me the women's grades" is an INCLUSION and should find it;
  the default is an EXCLUSION and should not. `primary_category()` is the same
  junior-first precedence `suggest_category` already used, so the default path
  is byte-for-byte what it was.
- **A picked grade beats the CATEGORY half of the scope and NOT the format half
  (`GradeScope.formats_only()`).** Reported from the Leaderboard with 4th Grade
  selected: the Match Type pills did nothing. The rule above was written as
  `if grade_id or grade_name: scope = None`, which threw the format away with
  the category — and picking a grade AND a format is the single most useful
  thing this filter does, because a grade routinely plays both in one season.
  Six sites: the three extended leaderboards, `records.py`, `games.py`,
  `get_org_results`, `_club_results` and `get_club_summary`'s grade branch.
- **The grade branches never interpolated `scope_clause` at all**, which is the
  other half of the same report. A picked grade takes its OWN query path in
  every one of those functions (`WHERE g.grade_id = :grade_id`, or
  `WHERE {_GRADE_MATCH}` for a grade picked by name), and those templates simply
  had no `{scope_clause}` in them — so even once `formats_only()` kept the scope
  alive it had nowhere to land. **When adding a filter to a leaderboard, check
  the picked-grade branch as well as the default one**; they are separate SQL and
  the default branch passing is not evidence about the other. `records.py` is
  the worst of it — `game_grade_clause`, `pairs_grade_clause`, `_bat_where`,
  `_bowl_where` and `_match_grade_filter` are five separate fragments, and the
  first two used to REPLACE the scope clause with the grade condition rather
  than append to it.
- **FORMAT IS PER FIXTURE, CATEGORY IS PER GRADE, and the two are not
  symmetrical.** The first cut filtered format at grade level and was wrong:
  Applecross 1st Grade plays 32 one-day and 26 two-day games inside ONE season,
  so a grade-level answer files most of a season under the wrong heading.
  `GradeScope.format_clause()` is a condition on each game's own
  `match_format`; `clause()` gained a `kind` argument so the ~22 per-game call
  sites needed no edit at all (`kind='game'` is the default) and only the five
  that are not per-game did:
  - **`kind='aggregate'`** (3 sites, `pss.grade_id`) emits `AND FALSE` under a
    format filter. A `player_season_stats` residual has no game and therefore no
    format — counting it towards "his T20 record" would be inventing a figure
    rather than filtering one. A CATEGORY-only scope still keeps residuals, per
    the `_RESIDUAL_SOURCES` rule below.
  - **`kind='grade'`** is an EXISTS over that grade's games, for a genuine grade
    LISTING with no game in the query. **The two `gr.id` sites are NOT that** —
    `get_batting_by_grade`/`get_bowling_by_grade` join games and express only the
    CATEGORY exclusion against `gr.id`, so they pass `game_alias="g"` and read
    format per fixture. Classifying them as `'grade'` was the first cut and the
    verification caught it: a two-day filter returned every innings in a grade
    that *sometimes* plays two-day, i.e. the exact bug this design exists to
    prevent. If a query joins `v_effective_games`, its format is per fixture,
    whatever column the category half happens to use.
  - **`scope.active` now includes `format_active`**, so a format filter switches
    every reader to the per-game path even when no grade is excluded. That is
    what makes it work at all: the aggregates cannot answer it.
- **A game with no recorded `match_format` falls back to its GRADE's format,
  but only when the grade plays exactly one.** A mixed grade says nothing useful
  about one unlabelled fixture, and guessing would put one-day runs in the
  two-day column. So the Grades screen's Match Type ticks are a FALLBACK for
  pre-`match_format` history, not the filter itself — the copy says so.
- **`format_sql_case()` is the SQL mirror of `format_from_match_type`**, and the
  verification asserts they agree on a table of 18 real strings ("Two Day+",
  "TWENTY20", "40-over", "BYE", "2-day", …). Change one and change the other, or
  the dashboard's filter and the profile's split file the same game differently.
- **Confirmed against live CA data for the reported grade.**
  `/scores/grades/94159f73-…/matches` (Applecross 1st Grade 25/26) returns
  **39 One Day and 32 Two Day in the ONE grade**, and the fixture the club
  linked (`/scores/matches/4dbd37f7-…`) reads `matchType: 'Two Day'`,
  `matchTypeId: 1`. That is the field PlayHQ shows as **Match Info → Format**,
  it is on the match record AND on every row of the grade match list, and it is
  what `games.match_format` stores.
- **A bare curl of that endpoint returns PascalCase, and it will send you
  chasing a bug that isn't there.** `grassroots_scores_client._get` always
  sends `jsconfig=eccn:true` (a ServiceStack formatting flag), which is what
  camelCases the payload — WITH it the envelope is `{"matches": [...]}` and rows
  carry `matchType`; WITHOUT it they are `{"Matches": [...]}` and `MatchType`,
  so `data.get("matches")` and `m.get("matchType")` both read empty. Reproduce
  through the client, or pass `jsconfig=eccn:true` by hand.
- **Fixed while here, and it was a real one**: `_JUNIOR`/`_MASTERS` ended their
  age patterns `\d+\b`, and a word boundary cannot match before a letter — so
  **"Under 14s", "U14s", "Year 9s" and "Over 40s" all classified as SENIOR**.
  The singular spellings always worked, which is why nobody noticed, and the
  plural is how clubs actually write them. Junior seasons have been sitting
  inside senior career averages for every club that spells it that way. Now
  `\d+s?`.
- **The filter is on every stats surface, from one control.** Leaderboard,
  Records, Players, Games and the player profile all draw the same two pill rows
  (`components/GradeFilterPills.jsx`, shared with `SeasonSelector`) and send the
  same two params. The additive "Include" row is gone from all of them — it and
  Grade Type answer the same question, and `SeasonSelector` refuses to draw both.
- **The profile threads the scope into every Analysis panel, not just the
  header.** `_resolve_player_scope` gained `formats`, so dismissals, by-grade,
  by-position, by-venue, by-opposition, partnerships, bowling breakdowns and the
  season-by-season table all move together — a header that says T20 above a
  by-venue panel counting two-day games is worse than no filter.
- **`resolve_scope_for_player` never widens a FORMAT.** The junior auto-widen
  exists so a junior-only player doesn't open on zeroes; a player with no T20
  matches asking for T20 SHOULD see an empty page, because that is the answer.
  Gated on `scope.category_active`, not `scope.active`.
- **`api.js` has one `scopeQuery()` helper** for the ten player sub-endpoints,
  which previously each hand-built `?categories=`. Ten copies of a URL builder
  is how one of them ends up not sending the new param.
- **`GET /players/{id}/formats` (`services/player_formats.py`) is the
  per-format profile page** — two-day vs one-day vs T20 batting, bowling and
  fielding, rendered as a FORMATS sub-tab under the profile's Analysis tab
  (self-fetching and lazy, so a visitor reading the batting tab never pays for
  the query). Reads per-innings rows only, groups on the same
  `format_sql_case`, recomputes every average from its own column's counts
  (never an average of averages), and converts cricket-notation overs to balls
  before any economy. **A match we cannot place gets its own `not_recorded`
  bucket and a coverage line** rather than being folded into one of the three —
  a club whose history predates the `match_format` writer sees most of its games
  there until `backfill_match_format` has run, and the page says so.
  Deliberately takes no `categories` scope: slicing a career two ways at once
  buys nothing.
- **`get_club_summary` switches source under a scope**, the same trade the
  leaderboards and career totals already make: CA's season aggregates carry no
  grade (`v_effective_player_season_stats`'s `api` branch hardcodes NULL), so a
  filtered figure is only answerable from the per-innings scorecards.
- **The additive "Include" row and the pick-one "Grade Type" row are never
  shown together** (`showCategoryFilter && !showGradeTypeFilter`). They answer
  the same question two ways, and the dashboard briefly drew both. "All" on the
  Grade Type row means the club's own default, and the note under the bar says
  what that leaves out rather than dropping a club's juniors quietly.
- **Auto-suggestion is untouched and now covers both axes.** An unclassified
  grade still resolves on the fly, `POST /grades/apply-suggestions` still fills
  the blanks (category from the name, format from the grade's own games, and it
  refuses to guess a format it cannot tell), and the sync still persists a guess
  for a brand-new grade. **Every site that writes `category=suggest_category(...)`
  must ALSO write `categories=`** — sync ×2 and manual_entries ×2 — or a synced
  "Girls Under 16" lands as junior alone and loses its women's half, which is
  NARROWER than leaving both blank. Asserted structurally so a new write site
  can't skip it. `match_formats` is deliberately left NULL on creation: a new
  grade has no games yet, and leaving it unset keeps the derive-from-games step
  live so it self-corrects as they arrive.
- **`grades-with-stats` computes classification in its OWN query.** Unnesting
  the two array columns into the existing aggregate multiplies every batting row
  by the number of tags and silently inflates the RUNS column — written that way
  first, caught before it shipped, and asserted against.
- **Verified against a real Postgres** (191 checks: migration 259 applied three
  times to a populated pre-259 table and matching the lifespan mirror, the
  plural age-group spellings, both org resolvers' three-step fallbacks, every
  branch of the two axes composing, a senior-only club coming out inactive and
  emitting no clause, the scoped summary, and the route bodies incl. the
  runs-inflation guard, the `category` column staying in step, an empty list
  clearing back to the suggestion and apply-suggestions refusing to guess a
  format, plus the every-write-site-pairs-both-columns guard; and the
  per-fixture suite: the reported mixed grade splitting 180/60 rather than
  double-counting, an unlabelled game in a mixed grade landing in NO column, the
  Python/SQL format mappings agreeing on 18 real strings, an import residual
  contributing nothing to a format column while still counting under a category
  filter, every figure on the new profile page, and the picked-grade suite: a
  grade plus Two Day, a grade plus One Day, the two splitting back to the
  grade's own total, and the same across club records, the club summary and its
  game count, the games list and the results list — with a control asserting an
  explicitly picked junior grade still beats the CATEGORY filter) and
  **driven in Chromium** (50: the pills that render and the ones
  that no longer do, the exact params on the wire for all four dashboard
  fetches, the two filters composing, clearing one without the other, the
  Grades screen's chips and its PATCH, plus the profile's FORMATS tab — lazy
  fetch, all three columns, the strongest-format callout picking the LOWEST
  bowling average, the coverage line, and the same two rows on Leaderboard,
  Records, Players, Games and the profile with the exact params on the wire —
  no page errors, no overflow at 390px on any of them).
- **The harness builds its tables from the ORM models, not by hand, and that is
  load-bearing.** A hand-written test schema spelled `bowling_spells.runs` as
  `runs_conceded`, the new format-split service made the same mistake, and 51
  checks passed against the shared error. The real column is `runs` (runs
  conceded).

## `games.match_format` was never written, so every match was a one-dayer (v9.25.2, Aug 2026)

Reported from Applecross Accounts: grades that play two-day cricket all showed a
Fee Format of One Day, and it "used to be right". Every match day was being
charged as one day.

- **The column has no writer.** `derive_fee_format(grade.fee_format,
  game.match_format)` is correct and always was; `games.match_format` was NULL
  for every synced row, and its own fallback is "everything else (One Day,
  blank, unknown) is treated as a single day". So the bug reads as a wrong
  format rather than a missing one, which is why it looks like a settings
  problem and isn't. **Migration 033's docstring claims the sync backfills this
  ("also opportunistically backfilled during incremental syncs") — that code
  does not exist in this tree.** The docstring is the only trace of it; treat a
  migration's prose as intent, not proof, and grep for the writer.
- **The format is per FIXTURE, and a grade cannot answer it.** Applecross 5th
  Grade 2025/26 is **32 One Day and 26 Two Day** fixtures (verified live against
  `/scores/grades/{id}/matches`); 1st Grade is 39/32. So the grade-level
  `fee_format` override is NOT the fix — setting a mixed grade to `two_day`
  would double-charge its one-day half. Leave that override for what it is for:
  telling a women's grade from a men's one, and excluding a grade from fees.
- **Read from the match LIST, not the scorecard.** `get_grade_matches` already
  returns `matchType` ("One Day" / "Two Day" / "T20") and the discovery loop
  already fetches it, so this costs no extra call and also covers a fixture
  whose scorecard is never opened. `matchTypeId` (1 = Two Day, 2 = One Day) is
  there too; the string is stored because every consumer substring-parses this
  column (`fees.derive_fee_format`, `iq_team._fmt_of`) and the manual-entry form
  writes free text into it.
- **"BYE" is also a `matchType`** (48 of Colts T20's 87 entries) and is
  deliberately NOT stored — it is not a format, and every consumer would parse
  it as a one-dayer. A bye has no scorecard so it never becomes a `games` row
  anyway; the guard just keeps the column honest.
- **Setting it on `Game()` alone would have fixed almost nothing.** An
  already-synced game never reaches the per-game block (the appearances-done
  gate short-circuits it), so the write is ALSO a bulk pass beside the existing
  `is_final` one — the same reason that one exists. That is what corrects a
  club's existing season on an ordinary Sync Now.
- **`python -m app.scripts.backfill_match_format <org-id-or-slug>`** (dry-run,
  `--apply`, `--recompute`, `--season YYYY`, `--all-seasons`) is the retroactive
  half, for the seasons an incremental run no longer scans. It restricts writes
  to games under the club's OWN grades — a grade match list is competition-wide
  and names plenty of fixtures that are not ours.
- **It deliberately does NOT default to the whole history.** A club collects
  fees for the season it is in and maybe the one before, so the default scope is
  **the seasons carrying `fee_member_seasons` rows, plus the club's latest
  season** — the latter because a club setting up this season's fees has no fee
  rows in it yet. Reaching back to 2011 spends a CA call per grade correcting
  money nobody is collecting. `--all-seasons` is there for the stats side
  (StatLab / BetterIQ format filters, migration 033's original purpose), not for
  fees. **A club onboarded after this shipped needs none of it** — its games get
  the format at creation.
- **Fee rows are not edited directly** — `recompute_fee_match_days` re-derives
  them and already leaves an admin-overridden (`auto_derived=False`) or
  already-paid row alone. Nothing new was needed for that; don't reimplement it.
- **Verified against live Cricket Australia data** (7 checks over six real
  Applecross 25/26 grades through the shipped `derive_fee_format`: the bug
  reproduced from a NULL, all three formats mapping, the mixed grade proving the
  per-fixture requirement, and the women's/exclude overrides still winning).

## Accounts kept resetting to the newest season (v9.25.2, Aug 2026)

Same report: work through 2025/26, open a member, come back, and you are in
2026/27.

- **`AdminFeeMemberDetail` already linked back with `?season=`; the Accounts
  screen just ignored it** — `useState('')` then "set `sorted[0]`" on every
  mount, unconditionally. Half the round trip had been built.
- **The season is URL state now**, seeded from `?season=` and mirrored back on
  change (`replace`, so the back button leaves the screen instead of walking the
  season history). It survives a refresh and is shareable, which is what the
  reported URL was.
- **A season named in the URL that the club no longer holds falls back to the
  newest** rather than leaving an empty screen with no way out.
- **Driven in Chromium** against the real screens with the API stubbed (11
  checks: the round trip holding 25/26, the back link, the no-param default, the
  stale-id fallback, the dropdown writing the URL, no page errors). The one
  failing check, horizontal overflow at 390px, was confirmed **pre-existing** by
  re-running it with the change stashed — the members table is wide, and that is
  not this fix's to solve.

## The scheduled sync pulls the period's results, not the club's whole history (migration 258, v9.25.0, Aug 2026)

`jobs/scheduler.py::sync_all_organisations` was `select(Organisation)` with no
WHERE and a full historical `sync_organisation` per club, at 03:00 **UTC** —
11:00 Sunday morning in WA, so a club's weekend results landed most of a day
late. Four separate problems, and the fix for each lives in
**`services/auto_sync.py`**, which is now the one place "who gets synced, and
how far back" is decided.

- **Perth, not UTC.** `PERTH` is module-level in scheduler.py and every
  club-facing job uses it. Sunday AND Monday 01:00 — same job both days, since
  each run asks the same question ("what has happened since this club's last
  sync") and doesn't need to know which day it is.
- **Eligibility reuses `auth.modules.org_core_live`** rather than inventing a
  second idea of "lapsed". That function already knows about a cancelled or
  paused Core row, an expired Core trial and the org-level master switch, and
  **it fails OPEN** for a club whose subscription rows predate the per-module
  scheme — so no long-established club is dropped by accident. Plus
  `archived_at IS NULL` and `is_active`. Skips are counted and logged by
  reason; a club quietly falling out of the sync with no trace is how you end
  up debugging "why is this club three months old" from scratch.
- **The watermark is the last run that actually PULLED MATCHES** — of
  `org_recent`/`org_full`/`org_hard_refresh`, a manual Sync Now counts, and an
  errored, cancelled or restart-interrupted run does NOT, so the next run
  automatically re-covers the gap instead of leaving a hole. A club whose last
  run failed therefore asks for fourteen days rather than seven, with no state
  to keep. `OVERLAP_HOURS = 26` is subtracted, which catches a result typed in
  hours after the last ball and makes Monday re-cover Sunday's fixtures.
- **"Successful run" is NOT the same as "pulled matches", and that gap was a
  real hole.** `sync.py` deliberately swallows a failure of the game-level
  pass so the season aggregates it already wrote are kept — which meant the
  run finished as a plain success, the watermark stepped over the period whose
  scorecards had just failed, and the club was quietly short those results
  forever. It now stamps **`match_pull_failed`** on the run's stats, and
  `auto_sync.last_sync_at` ignores a run carrying it (`_pulled_matches_ok`).
  **`ever_full` deliberately does NOT apply that filter** — "has this club's
  history ever been pulled" is about whether seasons and grades were seeded,
  and filtering it would hand a club whose game-level pass keeps failing a
  fresh full historical sync twice a week forever. For the same reason
  `plan_run` will not escalate to a full run twice: if a full run has already
  completed since the watermark and the club is still behind, it returns
  `full_sync_did_not_catch_up` and stays incremental at the `MAX_LOOKBACK_DAYS`
  cap rather than looping.
- **`kind = 'org_recent'` is deliberately NOT one of the existing kinds.**
  `org_full`/`org_hard_refresh` mean "this club's whole history has been
  pulled", which the Setup Wizard's own sync gate (`onboarding_wizard._sync_ready`),
  `wizard_analytics` and All Clubs' `_FULL_SYNC_KINDS` all read as their
  ready signal. An incremental run must not satisfy those. Same reason
  `main.py`'s restart self-heal still only resumes the two full kinds — a
  dropped incremental run needs no resume, because its watermark never moved.
- **Incremental mode is the SAME code path with a smaller input set**, never a
  different one: `since` filters the API season list through
  `auto_sync.season_in_window` (400-day span, so a straddling season or a late
  final can't be filtered out), and `sync_grassroots_game_level_data` takes
  `since` + `season_ids` to restrict the grade fan-out and drop out-of-window
  fixtures. **The grade fan-out is as much of the saving as the scorecards** —
  an established club has hundreds of grades across its seasons, each costing a
  `/scores/grades/{id}/matches` call on every run before a single scorecard.
- **Three whole-club tail passes are skipped when an incremental run added no
  games** (`_backfill_missing_season_stats`, `reconcile_imported_totals`, the
  bare `ANALYZE` that walks the whole DB). They derive from per-game data that
  by definition did not change. **Milestones are scoped, not skipped**:
  `_compute_milestones` runs a query per player, so an incremental run passes
  only the players whose season aggregates it just rewrote.
- **Nothing played in the period, nothing pulled.**
  `auto_sync.fixtures_in_window` asks the cheap question first — did this club
  play anything since its last pull — and the grade match lists it fetches are
  cached in-process, so when the answer is yes the sync that follows reuses
  them. **This is deliberately NOT a notion of "is the season over".** A club
  has an empty period for many ordinary reasons (the off-season, the Christmas
  break, a bye, a washed-out round, a team between grades) and every one has
  the same right answer. Modelling season boundaries per club and per
  competition would be more code reaching the same outcome only some of the
  time. **Every branch that returns "sync anyway" is load-bearing**: a CA
  season we don't hold yet or hold with no grades (deciding "nothing played"
  from grades we haven't created is how a club silently stops syncing the day
  its new season opens), and every grade returning an empty list
  (`get_grade_matches` returns `[]` for a transient failure and for a
  genuinely empty grade alike, so "whole card empty" is "could not tell").
  A fixture dated in the future doesn't count — it isn't a result to pull.
- **An idle check still records a successful `org_recent` run, and that is not
  bookkeeping for its own sake** — it moves the watermark. Without it a club
  that plays nothing for a stretch has its window grow every run until it
  crosses `MAX_LOOKBACK_DAYS` (90) and is handed a full historical rebuild,
  quarterly, forever, for having done nothing.
- **Historical drift is DETECTED, not blindly re-pulled** (per direct
  instruction — no periodic full sync). `services/sync_drift.py` compares CA's
  season aggregates against our stored `player_season_stats`, monthly, ~12
  seasons per club per run rotating oldest-checked-first, three calls per
  season and no scorecards. **The naive "sum the season and compare" reports
  drift on healthy clubs**, so it compares per player and only for
  participants CA itself reports: `_backfill_missing_season_stats` rows (for
  players CA omits) are ignored, and any participant caught up in a live merge
  is skipped, since the aggregate pass keeps one side's figures and drops the
  other's. CA returning nothing is `unavailable`, never drift. Surfaced as a
  banner on Data Sync with a Full Rebuild button; **acknowledging survives a
  re-check that still finds drift** (no monthly nag) and is cleared by one
  that finds the season clean.
- **Verified against a real Postgres** (77 checks: migration 258 applied three
  times and matching the lifespan mirror, every eligibility branch incl. the
  fail-open legacy club, the watermark ignoring an errored run AND a
  successful run whose match pull failed, the anti-escalation guard, the
  season and fixture filtering asserted inside the real
  `sync_grassroots_game_level_data` against stubbed CA responses, every
  empty-period probe branch incl. a mid-season break and a bye, the drift
  check's backfill/merge false-positive guards, the acknowledge semantics, and
  the scheduler choosing the right run per club) and **driven in Chromium**
  (13: the notice's copy and examples, dismiss posting to the endpoint, no
  page errors, no overflow at 390px).

## A picker inside a `<label>` cancels its own selection (v9.23.1.1, Aug 2026)

Reported from Accounts → Add member → Find in club: picking a player from the
search results left "Player or member" empty for one super admin and worked for
another, on the same club, the same person and the same two search results. The
difference was the browser. Chrome held the pick; Edge and Safari dropped it.

- **`Field` renders a `<label>`, and a label forwards a click on ANY descendant
  to whichever labelable control the field holds at that moment.** Choosing
  someone re-renders `PersonSearch` from "an input plus a list of option
  buttons" into "the chosen name plus a CLEAR button", so the forwarded click
  lands on Clear and wipes the choice before it can be seen. Nothing to do with
  the data, the club, capabilities or `active_club_id`, which is why two super
  admins on identical rows disagreed.
- **It survives only if the re-render has NOT committed by the time the browser
  forwards.** Verified in Chromium against the real components: commit the swap
  synchronously or in a microtask and the pick is wiped, defer it a task and it
  holds. That race is the whole "works for me, not for them", and no amount of
  reading the search endpoint would have found it.
- **`Field` gained `composite`**, which renders a `role="group"` div instead of
  a label. Use it for anything holding its own buttons. An ordinary input keeps
  the `<label>`, which is what gives it an accessible name and its
  click-the-caption-to-focus behaviour, so this is not a blanket change.
- **The pickers also defend themselves**: every option row and clear button in
  `clubmanager/pickers.jsx` goes through `choose()`, which calls
  `preventDefault()`. That suppresses the forwarding, so a picker mounted in a
  stray label still holds its choice. It cannot save a click on the label's own
  caption text, which is why the wrapper is the real fix and the guard is the
  net. The Club Diary's assigned-member and volunteer pickers had the same
  wrapper and are fixed too.
- **The trap generalises.** Any composite widget (a combobox, a chip
  multi-select, a segmented control) inside a `<label>` is a click-forwarding
  bug waiting to be reported by whoever is not on Chrome.

## A search beacon's top match is NOT the club they wanted (v9.23.1, Aug 2026)

Reported off the Meta Ads page: one person typing their way to Warnbro Swans
Cricket Club in a single minute left THREE rows — "Warn" logged as a club called
"CNSW WWCF Program - Warners Bay", "Warnb"/"Warnbro" as "WA Cricket Programs -
Warnbro Community High School", and only the last as the club they wanted. Two
prospect clubs that nobody ever searched for, and one real one split three ways.

- **Cause: `club_searched` records the TOP result and nothing else.** For a
  half-typed query that is close to arbitrary — the search ranks *something*
  first and the beacon writes it down as fact. `get_searched_clubs` groups on
  it. **A beacon's top match is evidence of what the search engine did, not of
  what the person wanted.**
- **Fixed on the Wizard Clubs page ONLY, per direct instruction — the Meta Ads
  page's "Clubs searched in the wizard" table is deliberately left reporting the
  raw top match.** So `meta_ads.get_searched_clubs` is untouched and
  `wizard_club_lists.resolved_searched_clubs` reads the same beacons itself.
  The split is defensible rather than accidental: Meta Ads is a report, whereas
  this page matches a club to the Club Directory and emails its committee, so a
  guessed club there is an email to the wrong people. **The two are allowed to
  disagree, and the resolver never writes anything back.** Don't "tidy this up"
  by pointing the page back at the Meta Ads table.
- **The heavy lifting is run-collapsing, not better string matching.** A
  visitor's consecutive searches where each query is a prefix of the last (typing
  forward AND backspacing — `_same_typing_run` tests prefix in both directions)
  inside `_SEARCH_RUN_GAP` are ONE run. The run resolves to the club they went
  on to click, else the club matched by the LONGEST query they typed. Six
  keystroke beacons become one row, and the two phantoms vanish because nobody
  ever finished typing them.
- **`_query_identifies` is "does the club's name START with what was typed".**
  That is exactly what separates "warnbro swa" → *Warnbro Swans Cricket Club*
  (typing this club's name) from "warn" → "…**Warn**ers Bay" (a hit on a word
  buried mid-name that the searcher never aimed at). Under 4 characters never
  identifies anyone.
- **Prefixing the matched club is not enough — it has to prefix ONLY it.**
  Found by the verification, not by reading the code: "south" genuinely is a
  prefix of "Southern Cricket Club", and equally of "Southern Districts CC".
  `_query_is_ambiguous` checks the query against every club name these beacons
  surfaced and demotes a match that fits more than one.
- **An unresolved search is reported as the QUERY, keyed `search:<query>`** —
  never as a club, so two guesses at the same club can't merge back into a
  phantom prospect row. The arbitrary top match rides along as `guess_name`
  only. `_improve_guesses` then upgrades that guess when exactly ONE
  confidently-resolved club in the same result set starts with the query (the
  "warn" → Warnbro Swans case), and **drops the guess entirely when two fit** —
  a coin toss presented as an answer is worse than no answer.
- **`result_count` is now on the beacon** (both callers, `TrackStepRequest`,
  metadata) so ambiguity is knowable rather than inferred: a search returning
  exactly one club names it outright whatever was typed. NULL for every beacon
  sent before this shipped, which is why the retroactive rules above carry the
  historical data. Regex-matched before the `::int` cast — the metadata blob is
  free-form and one junk value would abort the cast for every row (same lesson
  as the `list_id`-as-text comparison below).
- **A query row is never directory-matched or exported.** `_directory_matches`
  filters them out before matching, so a fragment can't be handed whatever club
  happens to be spelled like it, and the create-list flow reports it as
  unmatched rather than emailing someone on a guess.
- **The Wizard Clubs page shows the search terms**, which is the real fix for
  trust: a row's club can be judged against what was actually typed. An
  unresolved row reads `Searched "Warn"` + `Maybe …`, with a Resolved /
  Unresolved filter beside the others.
- **Verified against a real Postgres** (36 checks, the reported case replayed
  beacon-for-beacon: six searches → one row, both phantoms gone, plus the
  clicked-club override, the lone fragment, the two-clubs-fit fragment, the
  single-result search, per-visitor and per-session boundaries, and the page
  refusing to export an unresolved search) — **including four that assert the
  Meta Ads table still splits that same visitor across three rows and still
  returns its original payload keys**, so the deliberate split can't be
  regressed by accident. Driven in Chromium (15 checks).

## Clubs Searched or Selected in the Wizard (migration 251, v9.23.0, Aug 2026)

The Meta Ads page names the warm prospects — "Clubs selected in the wizard" and
"Clubs searched in the wizard" — and could do nothing with them. Both tables are
now merged into one CRM tool at `/admin/super/crm/wizard-clubs` (tile on the CRM
hub) that matches each club to the Club Directory, turns a filtered set into a
BetterComms list, and reports the outreach back per club.

- **The two tables merge on the key they already share.** `get_selected_clubs`
  and `get_searched_clubs` both group on the stripped, lowercased club name and
  both already drop the rows a super admin flagged as test noise, so
  `merged_wizard_clubs` just folds them together — a club in both is ONE row
  tagged `both`. **The Meta Ads page is untouched**; nothing there changed.
- **Directory matching is guid-first, name-second.** The wizard's
  `club_prepared` beacon captures the club's real CA organisation guid, which is
  the same guid the PlayHQ crawler keys `marketing_clubs.grassroots_guid` on —
  the strongest signal, and the reason "Applecross CC" and "Applecross Cricket
  Club" land on one row. Case-insensitive name is the fallback for a beacon that
  predates the guid being captured. Same priority `twenty_sync
  ._resolve_onboarding_club` already uses.
- **"Has this club been emailed" is DERIVED, not stored.** A sent campaign
  carries its audience `list_id`, a `comms_recipients` row carries its contact,
  and a directory-exported `comms_contacts` row carries its `marketing_club_id`
  — join those three, restricted to campaigns whose audience was one of the
  lists THIS page created, and the club's whole send history falls out. **No
  send-path hook**, so a corrected or repeated send needs nothing kept in step,
  and only `status = 'sent'` counts (a failed recipient is not a contact made).
  The `list_id` comparison is made **as text**: a campaign's audience JSON is
  free-form and one non-uuid value there would abort a `::uuid` cast for every
  row.
- **`wizard_club_lists.list_id` deliberately has NO foreign key.** A super admin
  deleting an old list must not take the club's email history with it, and the
  id is still exactly what the sent campaign's stored audience holds, so the
  reporting keeps resolving after the list is gone (the row reports
  `deleted: true` instead). `list_name` is stored alongside for the same reason.
- **Export follows the Club Directory's own rules** rather than a second set —
  never an `excluded` club, never an unsubscribed contact, every new contact
  linked back to its directory club (so `{{club}}` and the per-recipient
  unsubscribe resolve) and `exported_at` stamped so the Directory badge stays
  accurate. An existing address is reused, never re-created and never
  un-suppressed.
- **An un-named generic mailbox gets `first_name = "Committee Members"`**
  (`GENERIC_FIRST_NAME`). A club address is read by whoever is on the committee
  this year: blank renders "Hi ,", and a person's name would be a lie.
- **The browser sends club KEYS, never emails.** The server re-reads the
  directory and takes addresses from its own data, so a stale or tampered
  payload cannot introduce a recipient the club does not hold — the same rule
  the Directory's own "create a list from this selection" follows.
- **A tick never targets a hidden club.** `selectedRows` is intersected with
  what is on screen, and with nothing ticked the button acts on the whole
  filtered set — "create a list from what I picked" has to mean what it says.
- **Filters**: search, source (selected / searched), progress (Registration
  completed / Not completed / Reached terms — read off `furthest_step`, and a
  searched-only club has no step, so "Not completed" is the absence of the
  completed label) and Emailed / Not emailed. Sort by club, last seen or
  contacts. Select-all is scoped to the shown rows.
- **Verified against a real Postgres** (47 checks: the merge, guid and name
  matching, the emailable count excluding an opt-out and a no-email contact, the
  "Committee Members" greeting, the excluded/unmatched clubs reported rather
  than dropped, a failed recipient not counting, an unrelated list's send not
  reading as outreach, a junk `list_id` not breaking the report, re-export
  minting no duplicate person, a deleted list keeping its history, and the route
  bodies) with **migration 251 applied three times to a populated table**, and
  **driven in Chromium** (34 checks: every filter incl. Registration completed,
  both sort directions, select-all, the tick-survives-filtering rule, the exact
  create-list payload, no page errors, no overflow at 390px).

## A PlayHQ registration checkbox on Accounts (migration 235, v9.19.14, Aug 2026)

Playing a season requires the person to be registered with PlayHQ, and there
is no API this app can read that fact back from — Grassroots' `/scores/*`
and the Partner API are both match-data feeds, neither exposes registration
status. So it is a plain admin-ticked fact, the same shape as the existing
`is_new_registration` checkbox already living on the same row.

- **`fee_member_seasons.playhq_registered`** (bool, default false) +
  **`.playhq_registered_at`** (nullable timestamp, set/cleared with the
  checkbox — "when did we last check"). `PATCH /club-admin/fees/members/
  {id}/season` gained the field, alongside the two it already had.
- **Deliberately NOT carried forward by rollover** — `rollover_members`
  never sets it, so a rolled-over row always starts unticked. Registration is
  a per-season requirement; carrying last season's tick forward would assert
  something nobody has confirmed for the new season.
- **Surfaced in two places**: a PLAYHQ column on every Accounts row (checkbox,
  optimistic toggle via `PATCH .../season`) plus a "Not on PlayHQ" filter
  pill (`summary.playhq_missing`), and the same checkbox on the member detail
  page beside "New registration this season".
- **No new endpoint** — reuses the existing per-season PATCH, same as
  `is_new_registration`.

## BetterFees season rollover: undo, find-and-add, and remove (v9.19.13, Aug 2026)

Reported from Applecross getting 26/27 ready: rolling players over before the
new season's fee schedule is set up leaves everyone mismatched (rollover
resolves each member's tier by name against the DESTINATION season's rate
card, so an empty rate card means everyone lands "needs tier" with no way
back short of SQL), there was no way to add a player who sat out last season
or one new to the club without minting a duplicate manual entry, and no way
to drop a player who isn't returning.

- **`POST /club-admin/fees/rollover/undo`** clears every `FeeMemberSeason`
  row for a season in one go — "Remove all" on the Accounts page, for
  exactly the mismatched-rollover case above. A member with a payment
  already recorded this season is kept, never deleted (`fee_member_seasons`
  → `fee_payments` is `ON DELETE CASCADE`, so removing the row would take
  real money with it). Deliberately a season-wide reset, not "undo only what
  the last rollover added" — by the time someone reaches for this, sorting
  rollover-added rows from anyone else added since isn't a distinction worth
  making.
- **`RolloverModal` warns up front** when the destination season has no fee
  schedule yet, with a link straight to Fee Schedule, rather than letting the
  admin discover the mismatch after the fact.
- **`POST /club-admin/fees/members/enroll`** is the search-driven
  counterpart to the existing `create_member` (which only ever makes a
  brand-new non-playing person): finds an existing `fee_members` row OR a
  Stats player with none yet (`needs_member: true` off the existing
  `GET /people/search` / `PersonSearch` picker, the same one Committee's
  "start term" already uses), enrols them into the season via
  `members_svc.ensure_for_player` when needed, and is idempotent — enrolling
  someone already in the season just returns their row. "Add member" on the
  Accounts page is now two tabs, **Find in club** (this) and **New person**
  (the old manual-create form).
- **`DELETE /club-admin/fees/members/{member_id}/season`** removes one
  member's line from one season — a Remove action on every row and on the
  existing bulk-select bar, for "I know they're not coming back this
  season". Only clears that season's row; the person record and every other
  season are untouched. Refused (409) once a payment is recorded against
  them this season, for the same cascade-delete-real-money reason the undo
  above guards against.
- **No schema change** — all three read/write the existing `fee_members` /
  `fee_member_seasons` / `fee_payments` tables.

## Families is a BetterStats tool again, and a suggestion is opted INTO (v9.19.7, Aug 2026)

Families moved into BetterClubhouse with the v9.3.0 merge, which put it behind a
module a club may not hold — but a family grouping is Core data (it is a StatLab
player filter, `PLAYER_CONTEXT_FILTERS` in `services/statlab.py`), so it belongs
with Players and Seasons.

- **`/admin/families` is the screen again**, under BetterStats → Club Data.
  `AdminFamilies.jsx` renders in `BetterStatsLayout` and the route is
  `requireCore`, matching every other Core tool. That URL previously mounted the
  Clubhouse Directory; **`/admin/clubhouse/directory/families` now redirects to
  it**, so the Directory's own Families button and any bookmark still land.
  `BetterStatsLayout` had to start forwarding `caption` to `ModuleLayout` — it
  accepted only `title`, so the screen's mono subtitle was being dropped.
- **The nav item carries `MANAGE_FAMILIES`, the same capability
  `routers/families.py` enforces** — the rule the Clubhouse note below sets, and
  it holds across modules.
- **The Directory keeps its per-person family panel.** Only the setup screen
  moved; `dirCreateFamily`/`dirAddToFamily` are untouched, and a person's family
  is still read and edited where that person is.
- **A suggestion now starts with NOBODY selected.** It used to select every
  player sharing the surname and ask the admin to deselect the strangers, which
  makes the destructive reading ("these people are a family") the default and
  the correct one an act of removal. Two unrelated Matthews households are
  ordinary, so **opting a player IN is the deliberate act** and the confirm
  button is dead until someone is picked ("Select players above" → "Confirm —
  create with N"). An unselected player is drawn plain, not struck through — it
  means "not chosen yet", not "excluded".
- **Anyone left unselected stays in the suggestion list** and comes back on the
  next refresh, which is what lets one surname be split into two families across
  two passes. That behaviour is unchanged; the card now says so in place of the
  old "N will be re-suggested".
- **No backend change** — same endpoints, same payloads, same capability.
- **Driven in Chromium** (18 checks: the BetterStats shell and sidebar item, the
  old URL redirecting, the confirm button disabled with nothing selected and its
  label at each count, select-all/clear, the not-selected hint's singular and
  plural, both create and add-to-existing paths, no page errors, no overflow at
  390px).

## Season list tidy-up script (v9.19.4.2, Aug 2026)

Reported for Yarraville: the seasons page was a mix of synced "Summer 1968/69"
rows and bare "1968/69" rows the historical import created (grassroots_id NULL,
no year), interleaved and duplicated. **`python -m app.scripts.cleanup_seasons
<org-id-or-slug>`** (dry-run by default, `--apply` to act) makes the list
uniform:

- **Only manually-created seasons are ever written** (`grassroots_id IS NULL` —
  the documented "not from a sync" marker). A synced season is never renamed,
  re-yeared or aliased, and the merge target is chosen among synced siblings
  first.
- **A duplicate is MERGED, not renamed** — an alias row through the club's own
  Merge Seasons machinery (`season_aliases`), so stats aggregate under the
  canonical season and the merge is undoable from Admin → Seasons. The script
  mirrors the endpoint's chain rule: anything previously merged INTO the manual
  season is re-pointed at the new canonical so resolution stays single-hop.
- **A manual season with no synced sibling is renamed** to "Summer YYYY/YY" and
  given its `year` (which is what fixes the sort order — `_season_sort_key`
  reads the 4-digit year out of the name, and `resolve_season_filter` expands
  year siblings). Two manual seasons for one year: the exact-named or fullest
  one becomes canonical, the other is aliased into it.
- **Two things it refuses to guess**: a year with several synced seasons and
  none named plain "Summer YYYY/YY" (e.g. a masters comp under its own CA
  season id — merging into the wrong one would co-mingle comps), and a manual
  name with no recognisable "YYYY/YY" token. Both are reported and left alone.
- **Verified against a real Postgres** (13 checks: the merge with data counts,
  the rename+year, `1960-61` dash form, year-fill on an already-right name,
  two-manual collapse, the ambiguous-synced skip, exact-name preference among
  two synced, the chain re-point, a pre-existing alias untouched, another
  club untouched, idempotent re-run, slug and org-id resolution).

## Seasons are editable and deletable from the Seasons page (v9.19.5, Aug 2026)

Follow-up to the cleanup script: Admin → Seasons only ever offered reorder and
merge, so fixing one season's name or year meant a script or SQL.

- **`PATCH /club-admin/seasons/{id}`** (`manual_entries.update_season`, cap
  `MANAGE_MANUAL_ENTRIES`, mirrors AFL's `rename_season`) edits name and/or
  year, with a case-insensitive org-scoped duplicate-name 409. **Deliberately
  not restricted to manual seasons** — the sync never overwrites an existing
  season's name (it only backfills a NULL year, see `sync.py`'s season upsert),
  so a tidied name on a synced season sticks. Audited via `_log_edit`.
- **Delete reuses the existing `delete_manual_season`** (manual-only + empty-
  only), now surfaced as a per-row button. **`_season_in_use` gained
  `player_season_stats` and `imported_stats`** — the deletable seasons are
  exactly the ones BetterImport writes aggregate rows against, both FKs
  cascade, and neither table was checked, so a season full of imported history
  deleted straight through before this.
- **`GET /club-admin/seasons` now returns `synced`** (`grassroots_id IS NOT
  NULL`) so the page only offers Delete on rows the endpoint could ever
  accept. `synced_at` alone was the wrong proxy for this — it's a display
  field.
- **Frontend**: `AdminSeasons.jsx`'s row became `SeasonRow` — inline name/year
  edit (Enter saves, Escape cancels, only changed fields are sent), Delete
  behind a `window.confirm` with the server's refusal reason shown inline.
- **Verified against a real Postgres** (20 route-level checks: rename+audit,
  synced rename persisting, year-only patch, dup/blank/foreign/junk-id
  rejections, cross-club name reuse allowed, the two new in-use guards, all
  three delete refusals, the actual delete, and the `synced` flag) **and
  driven in Chromium** (14 checks: the exact PATCH payload on the wire,
  no-change save sending nothing, confirm dismiss/accept, a refused delete's
  reason rendered, Delete absent on synced rows, no overflow at 390px).

## Undoing a stats import deletes the players it minted (migration 234, v9.19.4.1, Aug 2026)

Reported from the Leeming Spartans demo: a mis-mapped BetterImport upload
created dozens of surname-only players, and undoing the import left every one
of them behind — `/undo` only ever deleted `imported_stats`, and nothing
recorded WHICH players a batch had created, so it couldn't have known.

- **`players.import_batch_id` (migration 234) is the marker** — set only when
  the import commit itself mints the row, NULL for every synced or hand-added
  player, `ON DELETE SET NULL` so a deleted batch never takes a player with
  it. **A re-import moves the marker forward**: latest-upload-wins re-homes the
  player's rows onto the new batch, so undoing THAT batch is what would leave
  them empty, and the marker has to follow (only where it was already non-NULL
  — a synced player is never stamped).
- **`services/import_cleanup.py` is the one deletability rule**, shared by both
  undo endpoints and the retroactive script. A batch-created player is deleted
  by the undo ONLY when nothing real has attached since: ~40 `BLOCKING_REFS`
  (stats from any source, membership, votes, lineups, achievements, merge
  history…) plus a profile check (photo, contact details, squad, skill
  positions) and a hard stop on any synced identity (`grassroots_id` /
  `playhq_id`). Derivative rows (`import_effective_deltas`, `milestones`,
  aliases) are deliberately NOT blocking — they cascade away with the player.
  Kept players are reported with the reasons, and the undo's audit row names
  both the deleted and the kept.
- **The emptiness check runs after `db.flush()`** — it must not see the
  imported rows the same transaction just deleted, or every player reads as
  still holding data and nothing is ever cleaned up.
- **`python -m app.scripts.purge_import_only_players <org-id-or-slug>`** is the
  retroactive cleanup for batches undone before the marker existed (Leeming's
  case). Candidates are never-synced players only; the same `deletable_players`
  check decides; dry-run by default, `--apply` to act; one club at a time on
  purpose — a hand-added player with genuinely nothing recorded yet is
  indistinguishable from import residue by data alone, so a person reads the
  list first.
- **Verified against a real Postgres** (23 checks: the migration applied three
  times, commit stamping + the pre-existing player NOT stamped, the re-import
  marker move, whole-batch and per-player undo deleting the empty player and
  keeping the one with an achievement, the audit naming both, a synced player
  never deletable, and the script's dry-run/apply against marker-less
  leftovers).

## Themes, a seat that owns work, and a plan to start from (migration 232, v9.19.3, Aug 2026)

The reference a club gave for a real strategic plan has four **pillars**
(participation, finances, volunteers, facilities), each with an objective and
owner. Two rounds of pushback shaped what got built and what did not:
**community clubs are run by volunteers, so this has to stay simple.**

- **A pillar is a GROUPING, not a fourth level.** `club_strategic_pillars` +
  `club_objectives.pillar_id`, drawn as a filter chip row above the plans and a
  heading inside one. Plan → objective → action stays three deep, because the
  screen had only just been made legible at three and a fourth indent would undo
  it. **Resist adding a level here.**
- **Club-scoped, not plan-scoped, and that is the whole reason it is a table.**
  A club's pillars are stable across plans, so the same four serve the 12-month
  plan and the 5-year one and "how is Finances going" can be asked across both.
  A free-text field would also have repeated the two-spellings bug migration 230
  had to clean up.
- **`club_objectives.owner_position_id` — a committee SEAT can own an
  objective**, so ownership transfers at the AGM with nobody editing anything.
  Copied from `club_diary_task_definitions.default_assignee_position_id`, which
  already does this for the same reason. The form opens on the seat and offers a
  named person as the exception; **one owner is written, never both**.
- **`seed_starter_plan` is the point of the whole release.** Four pillars, a
  plan named for the club's own diary year (`_season_label` reads
  `organisations.diary_start_month`, so it is not a second idea of when a season
  runs), and one example objective per pillar. **The blank page is what kills
  this feature, not a missing column** — a committee that opens something
  filled-in and deletes what does not apply will finish.
- **Seeding is skip-don't-replace at every level**: a pillar the club already
  has by name is reused, and the plan is only created when there is none by that
  name, so the examples can never be dumped into a plan somebody has edited.
  Re-seeding after deleting the plan reuses the existing pillars.
- **Deleting never takes work with it** (the rule 230 set): a deleted pillar
  leaves its objectives, they just stop being grouped.
- **Deliberately NOT built, after cross-checking the proposal against a
  volunteer committee**: parent/child plan nesting (a club wanting a 5-year and
  a 12-month plan just wants two plans), a `horizon` enum (the year range says
  it), a `progress_source` setting (derive it: targets if there are any, else
  the actions), and `item_type` on agenda items. Each was a plausible-sounding
  level of configuration that a tradie treasurer would have had to answer.
- **Still open**: objective TARGETS — a label, a target number and where it is
  up to now, three fields, so "grow registrations by 15%" is expressible. Today
  an objective's percentage is effort (the mean of its actions'), not outcome.
- **Verified against a real Postgres** (49 checks: the migration applied three
  times to a populated pre-232 table, pillar CRUD and cross-club rejection of a
  foreign pillar or position, clearing either owner, the seeding's
  skip-don't-replace at both levels, and `_season_label` either side of the
  diary-year boundary) and driven in Chromium (54 on the Plan screen, plus 12
  on an empty club pressing the starter button).

## An agenda has sections (migration 231, v9.19.2, Aug 2026)

A club's order of business is grouped — opening formalities, the reports,
elections, general business, closing — and the agenda was a flat ordered list,
so a 20-item AGM read as one undifferentiated column.

- **`meeting_agenda_items.section` is a LABEL, not a table, and that is the
  whole design.** The agenda stays ONE ordered sequence (`position`), which is
  what keeps the existing drag-to-reorder working untouched; the screen draws a
  heading wherever the section changes from the previous item. A section table
  would buy draggable and empty sections at the cost of a join, a second CRUD
  surface and a second ordering to keep in step. **A section with no items is
  not a state a meeting needs to hold.**
- **Order and section move in ONE write.** `reorder_agenda_items` takes an
  optional `sections` list parallel to `ids`, because dragging an item under a
  different heading is one action to the person doing it — two requests could
  half-succeed and leave an item under a heading it is not in. A mismatched pair
  of arrays is ignored rather than applied, so it cannot shuffle sections onto
  the wrong items.
- **A dragged item adopts the section it lands among** (the row above, or below
  when it goes to the top), and a NEW item joins whatever section the agenda
  currently ends in. Both are "what the person obviously meant", and both are
  editable after the fact.
- **A section repeated in two non-adjacent runs draws its heading twice.** That
  is deliberate: the agenda is what the order actually is, and sorting items by
  section behind the club's back would silently reorder a meeting.
- **`STARTER_AGENDA_TEMPLATES` (AGM + committee meeting) are the real win**, and
  the reason is not schema: a volunteer committee opening a blank agenda closes
  it. Seeded on demand like `seed_starter_positions`, never automatically, and a
  template the club already has by that name is **skipped, not replaced** — so
  pressing the button twice cannot overwrite an agenda somebody has since
  edited.
- **`agenda_templates.items` is JSONB and needed no migration** to carry
  `{section, title, description}`. A template written before sections has none
  and its items land under no heading, exactly as they always did.
- **Verified against a real Postgres** (31 checks: the migration applied three
  times to a populated pre-231 agenda, the starter seeding and its
  skip-don't-replace rule, template application preserving sections and order,
  clearing a section, the mismatched-arrays guard, and an item from another
  meeting being unable to be re-sectioned through this one) and driven in
  Chromium (25: headings once per run and in order, the add box naming the
  section it will join, the section editor, a drag sending both arrays, and the
  starter button on the manage screen).

## Picking a person is a SEARCH, not a list (v9.19.1, Aug 2026)

Reported: the Start-a-term dropdown on Committee Roles is "very short". It was
drawing `.slice(0, 30)` of `/fees/all-members` with nothing to say there were
more, so an unfiltered list stopped inside the A's and read as the whole club.

- **`PersonSearch` (clubmanager/pickers.jsx) is the pattern now** — type a name,
  the SERVER searches, only matches come back. Modelled on the meeting room's
  "who is doing it" field. A club with fifteen hundred people should never have
  its roster shipped to the browser to draw a dropdown somebody is about to type
  into anyway. **Reach for this over `MemberSelect` on any picker that has to
  offer the whole club.**
- **`GET /club-admin/fees/people/search`** searches `fee_members` UNION the
  club's players with no member row, org-scoped on both sides of the
  read-through, archived never offered. Returns `needs_member: true` for a
  player who is not enrolled, and asks for one row over the limit purely to
  answer "is that all of them" without a second COUNT.
- **Debounced 220ms, and the response is DROPPED if the box has moved on** — a
  slow search for "sm" must not land on top of the results for "smith".
- **`start_term` takes a `player_id` and enrols them itself.** Committee terms
  FK to `fee_members`, so a not-yet-enrolled player needs a row first; doing it
  here keeps it one request under `MANAGE_COMMITTEE`, whereas the Directory's
  own ensure-member route needs `MANAGE_MEMBERS`, which a committee manager does
  not necessarily hold. `members.ensure_for_player` is idempotent and un-archives.
- **`fee_members.archived_at` had existed since migration 212 and was never
  mapped on the model**, so reading it off an ORM row raised at request time.
  Mapped now. **A raw-SQL column the services only ever touched through `text()`
  is invisible to the ORM until someone adds it.**
- **`/fees/all-members` still means "member rows"** and is unchanged for its
  eight callers, plus an `archived` flag. Screens keep using it to resolve a
  name against a record that already names someone; only CHOOSING is a search.
- **Verified against a real Postgres** (27 checks: the read-through, cross-club
  scoping both ways, archived never offered, enrolling on the first term and
  reusing the row on the second, the limit bounded against a caller asking for
  thousands) and driven in Chromium (17: nothing listed before typing, no
  request for an empty box, four keystrokes debounced into one, and the payloads
  for both an ordinary member and an unenrolled player).

## Strategic plans → objectives → actions and motions (migration 230, v9.19.0, Aug 2026)

Reported: the Committee screen's Plan tab could create an objective and nothing
else. There was no CRUD for the strategic plan an objective belongs to, no way
to edit or delete an objective, and a motion could not point at the plan at all.

- **A plan was free text on every objective row** (`club_objectives.plan`,
  migration 217), so "Strategic Plan 2026" and "strategic plan 2026" were two
  plans, renaming one was impossible, and a plan had nowhere to keep its own
  dates or description. **`club_strategic_plans` is the record now**, and
  `club_objectives.plan_id` points at it. The old text column is **backfilled
  and then left alone as history — nothing reads it after 230**; the API returns
  `plan_id` + `plan_name` instead.
- **The backfill groups case-insensitively on the trimmed name**, so a club that
  typed the same plan two ways gets one plan rather than two to merge by hand.
- **It guards with `NOT EXISTS`, NOT `ON CONFLICT`, and that is load-bearing.**
  Found by running the migration twice: there is no unique constraint on
  `(organisation_id, name)` for a conflict clause to fire against, so the first
  cut minted a fresh set of plans on **every app boot** (this file is mirrored
  into `main.py`'s lifespan, which re-runs it each time). The constraint is
  deliberately absent — a club is entitled to name two plans the same thing.
- **An objective carries its own `due_date`, `owner_member_id` and `budget`.**
  Those three sat on the ACTIONS serving an objective and nowhere on the
  objective itself, so an objective with no actions yet had no owner, no date
  and no budget.
- **`budget` vs `own_budget` in the rollup, and the distinction matters.**
  `_delivery()` returns `budget` as the EFFECTIVE figure (the objective's own
  allocation, else the sum of its actions'), so `objective_progress` also emits
  **`own_budget`** — the club's actual allocation. Without it a rolled-up 0 is
  indistinguishable from "nothing allocated", and the screen said "allocated $0"
  about an objective nobody had budgeted while its edit form seeded a 0 the club
  never typed. Caught by screenshotting the real page, not by any assertion.
- **`meeting_motions.objective_id`** — an action already had one, so "the
  committee resolved to do this" and "someone is doing it" reported against the
  plan differently. An action raised under a motion in the meeting room
  **inherits the motion's objective**, because retyping it is the step that gets
  skipped and then the plan reports short.
- **A null means "clear it", and that needed fixing in three places.**
  `update_task` guarded every field with `if fields[f] is not None`, so an
  action's objective, budget, spend or due date could be set and never unset —
  `_TASK_CLEARABLE` lists the nullable columns and assigns them on presence
  alone (the router sends `exclude_unset`, so a key being there IS the intent).
  Same for `update_motion`'s `objective_id` and the objective/plan routes, which
  moved from `exclude_none` to `exclude_unset`. Title, category, status and
  percent stay guarded — they are NOT NULL.
- **Deleting never cascades into the work.** A deleted plan leaves its
  objectives (FK SET NULL, reported under "Not on a plan"); a deleted objective
  leaves its actions and motions. An objective is real work the club committed
  to, and binning it because the document it was written in was deleted would
  take every action serving it down too.
- **`plan_report` scopes motions through their MEETING's org**, not the
  objective's — `meeting_motions` has no `organisation_id` of its own, so an
  objective id arriving from a browser must not be able to pull another club's
  motions into the report. Same rule the shared-game notes below describe.
- **A plan's figures are the sum of its OBJECTIVES', not a second pass over the
  actions** — otherwise an objective with its own budget and an objective
  budgeted through its actions get added up two different ways in one total.
- **`ObjectiveSelect` / `useObjectives` (governance.jsx) is the one picker**, and
  it shows `Plan › Objective`: two plans can each have an objective called "Grow
  junior numbers" and picking the wrong one is otherwise invisible. Fetched once
  per screen, never per motion — a meeting with ten motions would otherwise fire
  ten identical requests.
- **`ObjectivesTab` became `PlanTab`** and has two views: "By plan" (the
  editable hierarchy) and "All work" (every action and motion flat, in plan
  context, filterable to late / over budget). Both read the one `/plans/report`
  fetch.
- **Three levels, three shades (v9.19.1).** `LEVEL` in governance.jsx sets the
  rail, tint and figure colour per depth, and `Nested` is the step-in. The rails
  are `color-mix`, never `${accent}66` — the accent resolves to a `var()` and a
  hex suffix on one is not a colour, so the border silently vanishes (the trap
  `chip()` already documents). Figures are mixed towards `--pb-dim` rather than
  switched to another hue: same kind of number, less of the club's accent each
  time. Checked by computing the styles in both themes, not by eye.
- **An action reports the meeting it was raised at**, falling back to its
  MOTION's meeting when it has none of its own. Served as `raised_meeting_id`,
  deliberately NOT overwriting `meeting_id` — that key means the action's own
  column, and a row must not claim a link it does not hold.
- **Verified against a real Postgres** — 85 service- and route-level checks
  (the migration applied twice to a populated pre-230 table, the two-spelling
  collapse, cross-club rejection of a foreign plan id, every clearable field,
  the budget fallback, the motion leak) plus 11 asserting the lifespan mirror
  runs the same statements in the same order and lands on the same schema after
  three applications. Then driven in a real browser (Chromium, dev server with
  the API stubbed at the network layer): 38 checks on the Plan screen and 17 on
  the meeting room, including the payloads sent on the wire, no page errors and
  no overflow at 390px.

## A PlayHQ game-centre link is a different id namespace (v9.18.0.2, Aug 2026)

Reported: pasting `playhq.com/.../a-grade-gatorade/game-centre/abecedd5` into
BetterPosts → Final Score got "Paste a match URL or a match ID". Both import
handlers matched a full UUID and nothing else, so a PlayHQ link was a dead end.

- **The short code is NOT a prefix of the Grassroots GUID, and nothing derives
  one from the other.** Checked against the reported match rather than assumed:
  PlayHQ `abecedd5` is Grassroots `ef9b6401-787f-4f93-b9b8-8de0316f3686`
  (D&DCC A Grade semi-final, 31 May 2026, found by walking
  org search → seasons → teams → `/scores/grades/{guid}/matches`). The grade
  short code `596e3b20` likewise has nothing to do with the grade GUID
  `f1d5d3aa-…`. **This contradicts the AFL note in `docs/afl-playhq-data-source.md`
  ("the short code IS the real gameID") — that holds for the AFL tenant's own
  discover API, not for cricket's Grassroots API.**
- **PlayHQ's public `discoverGame` GraphQL does answer for a short code**
  (`tenant: ca`, returns date/grade/round), **but do not build on it.** It sits
  behind a CloudFront WAF that started 403-ing this environment's IP after
  about three requests and never recovered — an import button a club presses
  cannot depend on that. Schema introspection is blocked too.
- **So the resolution is local**: `services/social_match_lookup.py` +
  `GET /admin/social/match-lookup`. A full UUID (a Play.Cricket link, or a
  pasted id) resolves straight through exactly as before; a PlayHQ link comes
  back as the club's own recent completed matches for the admin to pick from,
  narrowed by slugifying the grade out of the URL and matching it against our
  grade names ("A Grade (Gatorade)" → `a-grade-gatorade`, with a
  either-side-prefix fallback for a sponsor suffix one side carries). Candidate
  discovery reuses `_current_grade_rows` + `gr.get_grade_results`, the same
  machinery behind the Results roundup, so there is no second copy of "which
  matches are ours". Lookback is 240 days, not the roundup's 90 — the reported
  match was a semi-final ~10 weeks old.
- **Bug found while verifying, in the same import path**: `_get_social_scorecard_inner`
  read `result`/`venue`/`date` off `matchSummary`, which on a `/scores/*` match
  only carries `resultText` + `teams`. All three live at the TOP level
  (`raw.venue`, `raw.matchSchedule[0].startDateTime`, `matchSummary.resultText`),
  so every imported post had a blank date, a blank ground and a bare "RESULT".
  Fixed as extra fallbacks, matchSummary still tried first. `format` now reads
  `matchType` instead of hardcoding "T20" (a 50-over final was labelled T20),
  `overs` takes the longest innings bowled, and the round label only gets a
  "ROUND " prefix when the name has no letters — it used to emit
  "ROUND Round 7" and "ROUND Semi Finals".
- **Verified against live Cricket Australia data end to end**, then driven in a
  real browser (Chromium, the dev server with the API stubbed but the actual
  resolver and scorecard parser running): the reported link narrows to 10 A
  Grade matches, picking the semi-final fills 9/243 v 227 with both sides' top
  three batters and bowlers, MOTM, Kahlin Oval and 31 May; a Play.Cricket URL
  still loads with no picker; junk input reports plainly; no page errors, no
  overflow at 390px.

## Junior stats split off career stats (migration 228, v9.18.0, Aug 2026)

An Under-14 season was landing inside a senior career average. `grades.category`
(migration 123, Senior/Junior/Women's/Masters/Mixed) had existed since v8.x and
**nothing in the stats layer had ever read it** — it drove grouping and public
visibility only.

- **`services/grade_scope.py` is the one place a category selection becomes SQL**,
  and **it works by EXCLUSION, which is load-bearing**. The obvious shape is an
  include-list of senior grade ids; it is wrong twice. A manual game may have no
  `grade_id` at all (Grade is optional on Upload Scorecard) and a career-scope
  import residual has none either — an include-list drops both, an exclude-list
  keeps them, because **a row we cannot categorise is not a row we know to be
  junior**. And an empty exclusion set emits **no clause at all**, so a club with
  no junior grades runs byte-for-byte the queries it ran before. That is what
  makes a default that excludes junior safe to ship platform-wide. Every caller
  gates on `scope.active`, never on `scope is None`.
- **`clause()` is `col IS NULL OR NOT (col = ANY(...))`, not a bare `NOT`** —
  with a NULL `grade_id` the ANY comparison is NULL and `NOT NULL` is NULL, so a
  grade-less manual game would be silently dropped by a filter that has no
  opinion about it.
- **Categories resolve per grade NAME, in Python, never in the WHERE clause.** A
  category may be an unconfirmed `suggest_category` guess rather than a stored
  column (the 25/26 "Under 14s" row typically has `category` NULL), so it cannot
  go into SQL. Same approach the public lineups endpoint already takes.
- **CA's season aggregates carry no grade — `v_effective_player_season_stats`'s
  `api` branch hardcodes `grade_id NULL`.** So a scoped career total is only
  answerable from per-innings scorecards, and an active scope switches source.
  Same trade the leaderboards already make for a grade/finals/captain filter
  (`use_game_level` in records.py now includes `scope_active` for this reason).
- **The three aggregate-only residual branches must be added back, or a
  BetterImport club loses its history the moment the default filter applies.**
  `_RESIDUAL_SOURCES = (manual_aggregate, manual_career, import)` — the branches
  with no per-innings rows behind them. `api` and `manual_game` are excluded from
  that list because the per-game views already cover the same games; counting
  either alongside them doubles every figure. `_career_residuals` does this for
  one player, `_residual_totals_cte` for the leaderboards (the same shape as the
  existing `import_totals` CTE beside it). **Every blended average is recomputed
  from summed counts**, never averaged from two averages.
- **An explicitly picked grade beats the category default** (`if grade_id or
  grade_name: scope = None`). Someone choosing "Under 14s" from a dropdown means
  it; returning an empty board would read as broken.
- **Two things a scoped view genuinely cannot answer, and says so rather than
  guessing**: `fielding_stats` holds one run-out count and never splits assisted
  from unassisted (only CA's season aggregate does) → returned as **NULL, not 0**,
  because 0 reads as "never assisted a run-out"; and best bowling *figures* come
  from the per-spell rows only, since a residual branch knows the wicket count but
  its figures string belongs to a spell we hold no scorecard for.
- **`get_season_by_season` needed its own per-game variant** (`_season_by_season_scoped`),
  or the table would sum to a different number than the scoped header above it.
  It drops the "Prior Seasons & Adjustments" row — that lump is the NULL-season
  residual and belongs to no season, though it is still counted in the header.
- **`organisations.stats_grade_categories`** (migration 228, JSONB list, NULL =
  platform default) is the club's own default. An empty or all-junk selection
  **stores NULL rather than saving**, or a club would be looking at empty stats
  with no obvious way back. Edited from Club Settings → "Stats by grade"; Senior
  is shown but disabled, since it is the baseline the rest are added to.
- **Bug the verification caught**: the leaderboards' finals and captain branches
  built `scope_clause` but nothing bound its parameter, so those two combinations
  failed at execute time. Bound once right after each `params` dict is created.
  A clause built from a helper and interpolated into several branches needs its
  bind at the point every branch shares, not beside the interpolation.
- **Verified against a real Postgres** — 47 service-level + 18 route-level checks
  against the real 5-branch view stack (pulled straight out of migrations 038 /
  070 / 075 / 092 / 147 / 169 rather than retyped): the unconfirmed-junior guess,
  a senior-only club coming out inactive and byte-identical, import history
  surviving the filter, the season table reconciling with the header, an
  explicitly picked junior grade still returning its runs, finals composing with
  the filter, and migration 228 applied twice to a populated table.
- **A junior-only player must not open on a page of zeroes** (migration 229,
  `organisations.stats_auto_show_played_grades`, default TRUE).
  `resolve_scope_for_player` widens the scope to the categories a player has
  actually turned out in **when the default would leave them with nothing at
  all**, and returns `auto_shown` so the profile can say why its figures differ
  from the Leaderboard's. Three rules: it only ever applies to the DEFAULT (an
  explicit `categories=` is honoured even when it comes back empty, or the
  toggle would appear not to work); it is **profile-only**, never a club-wide
  board; and a career-level residual carries no grade, so it counts towards
  neither side of "has this player played in a counted category".
- **Bug found in the wild**: `get_settings` had no `db` dependency, so the two
  grade-category fields added to its response raised at request time and the
  Settings page sat on "Loading…" forever (`AdminSettings.jsx` swallows the
  error with `.catch(() => {})`). The route suite had exercised every OTHER new
  endpoint but never `get_settings` itself. **A handler missing a `Depends`
  compiles, imports and passes `py_compile` — only actually awaiting it fails.**
  It is called for real in the suite now.
- **Deliberately not touched**: BetterIQ (its own `iq_filters` grade vocabulary
  and a client-side "Seniors only" preset already), StatLab, Yearbooks, and the
  AFL silo (`services/afl/grade_labels.py` has its own category set —
  senior/colts/womens/masters/integrated — and would need its own pass).
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

## The meeting room runs inside the Committee screen (v9.17.1, Aug 2026)

OPEN, a second pill on every meeting card in Clubhouse → Committee, puts the
meeting room (`pages/admin/MeetingRoom.jsx`) in the pane beside the list instead
of on a page of its own. **Frontend only, and no endpoint changed.**

- **`MeetingRoomPanel` is the whole room with no chrome**, and the default export
  is now a thin route wrapper around it. So there is ONE meeting room, mounted
  twice, and `/admin/clubhouse/committee/meeting/:meetingId` is byte-for-byte the
  page it always was — which matters, because OPEN MEETING on the manage screen
  and any bookmark still go there.
- **The header is the awkward part and `onMeta` is the answer.** The full-page
  version draws the title, the status select and "All meetings" in the MODULE
  header, which is outside the panel; the panel therefore hands `{ meeting,
  setStatus, reload }` up on every load and the route renders the header from
  that. Embedded, `inlineHeader` draws the same three things inside the pane with
  Close in place of the link. Do not be tempted to move the header into the panel
  permanently — that would change the standalone page.
- **The room is only ever open on the SELECTED meeting** (`room = st.cteRoom ===
  sel.id ? sel.id : null`), so the highlighted card and the pane can never
  disagree, and clicking any card exits the room back to its summary.
- **`onMeta` also keeps the card's status pill live** (a cheap merge of the
  meeting-level fields), and `refreshMeeting` re-reads the one meeting on the way
  OUT so the summary shows what was just minuted. One fetch on exit, not one per
  edit — the room already reloads itself after every change.
- **`chip(C.accent)` does not work in that screen.** `chip` builds its edge as
  `${fg}66`, and `C.accent` is `var(--pb-accent)` — `var(--pb-accent)66` is not a
  colour, so the border silently disappears. `openChip` uses `color-mix` for the
  edge and `--pb-accent-ink` for the text, which is also what keeps it legible on
  a light theme.
- **Verified in a real browser** against the running app with the API stubbed:
  OPEN on each card, the agenda and its items, a motion and its votes, minutes
  autosaving (the PATCH and the attendance PUT were both observed on the wire),
  the status select, Close returning to a refreshed summary, no overflow at
  390px, both themes, and the standalone route still rendering its own header.

## A club font with no bold, and ink on a dark accent (migration 226, v9.14.0, Aug 2026)

Reported by Leeming Spartan: their uploaded font looked "too dark" as an H1 and
on the win rate / total runs figures, and the accent button's text was
unreadable. Both are one-line symptoms of two systemic gaps.

- **The bold was never real. It was SYNTHESISED.** Their file is Patua One,
  `usWeightClass 400`, no `fvar`, no italic - a single-weight slab serif. Asked
  for `font-weight: 700` the browser fakes one by smearing the outlines, which
  on an already-heavy face reads as mud. **A font FILE holds exactly one weight
  unless it is a variable font**, so this is the normal case for an upload, not
  an edge case. `services/fonts.describe_font` reads the file at upload time
  (sfnt directly, `.woff` per-table zlib, `.woff2` tag directory only since
  there is no brotli dependency - enough to spot an `fvar`) and stores
  `metrics` on the `font_config` role entry; `buildThemeCss` emits
  **`font-synthesis: none`** when any role cannot really bold. Safe page-wide:
  every app default and multi-weight preset carries a real bold, so nothing
  that COULD bold properly loses it. A file uploaded before this shipped has no
  `metrics` and is treated as single weight, which is right almost always and
  self-corrects on re-upload.
- **Five of our own presets have the same problem** (`oneWeight: true` on anton,
  bebas, archivo_black, abril, bungee). Either the family has no bold cut or
  index.html requests it with no weight axis. **Keep those flags in step with
  the Google Fonts `<link>`** - adding a family there without a weight range
  means adding the flag here.
- **`--pb-weight-display` / `-body` / `-mono`** are the per-role weight, set
  from Typography settings. Consumed through `.pb-heading` / `.pb-figure`
  (styles/theme.css), which is what `PageHeader`'s `<h1>` and `Kpi`'s figure use
  instead of `font-bold`. For everything else `buildWeightCss` emits
  `.font-display.font-bold {…}` style rules - **two classes, so they beat a
  Tailwind utility on specificity** and a club's choice wins over the ~590
  `font-bold`s written into components without editing any of them. Scoped to
  elements that opted into the club's display or mono font, so ordinary bold
  body text is untouched.
- **`--pb-on-accent` is the ONE answer for text on an accent fill** (default
  `#08110b` in theme.css, per-club in `buildThemeCss`). `onAccentInk` picks
  white or near-black by WCAG contrast, so the BetterStats green keeps its dark
  ink and navy/maroon/black get white. **Never hardcode a hex or `text-pb-bg`
  on a `var(--pb-accent)` fill again** - that is what made a navy club's primary
  button near-black on near-black. Swept across the public pages; the admin
  app still uses its own `ON_ACCENT` (`components/admin/ui.jsx`), which is
  correct there because that surface is BetterCricket amber, not club colour.
- **`organisations.public_header_logo`** (migration 226, mirrored in the
  lifespan) puts the crest beside the club name in `PageHeader`. Beside, not
  instead of: the page keeps a real `<h1>` for search and screen readers.
  Opt-in, so no existing club's public site changes on upgrade. **Read it off
  the `/clubs/{slug}` payload, not `/organisations/{id}`** - the Dashboard has
  both in scope and only the former carries it.
- **Deliberately not built**: an italic toggle. Patua One has no italic either,
  so it would hand back faux-slanted glyphs, the same class of problem. A club
  wanting a real bold or italic should upload that file for the role.
- **Verified against the club's real live site** (dev server with
  `VITE_PROXY_TARGET=https://betterat.cricket/api`, screenshotted in Chromium):
  `font-synthesis` computes to `none` on their H1, the Leaderboard button
  computes `rgb(255,255,255)` on their navy, an explicit weight choice moves the
  H1 to 400, and the crest sits beside the name at 1280px and 390px with no
  horizontal overflow. The parser was checked against their actual .ttf plus a
  known Bold file (reads 700) and a woff2 (table directory walks clean).

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

## What kind of member is this? The Directory's three type axes (v9.11.1, Aug 2026)

Reported: BetterStats → Players marks a player Inactive, but the Clubhouse
Directory read every person the same — a social member, a life member, a
sponsor's contact and this season's opening bat all just "Player" or nothing.

- **There is no single "membership type" column, and there should not be. Three
  independent axes already exist and all three are now returned by
  `services/directory.list_people`:**
  1. **`membership_types`** (migration 175) — the club's own cross-season
     catalogue: Senior/Junior Player, Parent, Social Member, Life Member, Coach,
     Selector, Volunteer, Umpire, Scorer, **Sponsor Contact**, Committee Member,
     Honorary Member (`services/membership_types.STARTER_TYPES`, carrying
     `is_playing` + voting/insurance/WWCC/PlayHQ flags). **This is the real
     membership type**, and nothing seeds it — a club adopts the starter set or
     builds its own, so it is legitimately empty for plenty of clubs.
  2. **`fee_members.member_category`** — volunteer | parent | committee |
     life_member | third_party | official | other. What the Directory's own
     "Add person" TYPE dropdown writes; drives the computed `segs`.
  3. **`players.status`** ('active' | 'inactive') — the flag the Stats Players
     screen shows. Returned as `player_status`, and **NULL for a non-player**,
     so "not playing" and "not a player" stay distinguishable. Plus the
     `is_life_member` / `is_honorary` (+ expiry) flags on `fee_members`.
- **Sponsors are not people.** `org_sponsors` is the sponsoring ORGANISATION
  (name, logo, website, one carried-over contact name/email from the KlubPro
  import). A sponsor's person belongs in the Directory as an ordinary member
  with the "Sponsor Contact" membership type. Don't union the two lists.
- **The membership-type catalogue's CRUD lives in BetterFees** (`/club-admin/fees/
  membership-types`, `MANAGE_FEES` + the fees module), which a volunteer or
  committee manager does not hold — so `GET /club-admin/directory/people`
  returns the catalogue itself alongside the people rather than sending the
  screen to an endpoint that would 403 for half its readers.
- **The Directory can now SET `membership_type_id`** (`MemberUpsert`, resolved
  through `_resolved_type_id` → 422 for another club's id, "" clears it). Without
  this the filter would be dead for every club that doesn't run BetterFees,
  since nothing else writes the column.
- **The `membership_types` join is org-scoped on BOTH sides**
  (`mt.organisation_id = fm.organisation_id`), same rule as the `players` join
  above it — see the cross-club member leak note further down.
- **Frontend** (`redesign/screens/Directory.jsx`): `typeLabel(p)` falls
  membership type → category → player/former player → "Member", shown on every
  list row and as an accented chip on the detail pane. New filters: Playing /
  Former players (both exclude non-players rather than lumping them in with the
  inactive), a membership-type select with a **"No type set"** option, and the
  Life member / Official / Honorary segments — `list_people` had always computed
  those and they simply had no pill.
- **Verified against a real Postgres** (27 checks): the new join and every
  returned field, a member pointed at another club's type reading as no type,
  read-through players carrying their status, archived behaviour, and the
  router's own guard rejecting a foreign/unknown/non-uuid type id.

## BetterFootball — Import Results (v9.7.0, Aug 2026)

A club's own results register (one row per match, going back as far as the
club's records do) imported as **real games**, not a parallel store. Sibling
of Import Stats (`routers/afl/imports.py`, season totals per player). Built
against a real 3,044-row 1947–2023 register from an AFL club.

- **`routers/afl/result_imports.py`** (`/club-admin/result-imports/*`, cap
  `MANAGE_MANUAL_ENTRIES`) — preview → resolve → commit → undo, plus a
  template. Seasons come from Import Stats' own `/club-admin/imports/seasons`
  endpoints; there is deliberately no second copy of season listing/creation.
- **Rows land in the shared `games` table + `afl_game_details`**, so they show
  on the public results list, the dashboard W/L/D and records exactly like a
  synced game. Three columns on `afl_game_details` carry the distinction:
  `source` ('playhq' | 'import'), `import_batch_id`, plus `import_ref`,
  `is_bye`, `is_forfeit`, `result_note` (what the club actually wrote —
  "Won on Forfiet"). `playhq_id` went **nullable** (an imported game has no
  PlayHQ game behind it). All idempotently ALTERed in `afl_main.py`'s
  lifespan, since `create_all` never retrofits a column.
- **The game id is `uuid5(org, "import-game:" + season|team|date|opponent|round)`**
  — so re-uploading a corrected sheet UPDATES the same rows instead of
  duplicating them. Round is in the key because a re-scheduled fixture carried
  at its original date is otherwise indistinguishable from its twin.
- **The already-synced guard must include the TEAM, not just date+opponent.**
  Found in testing: a club's Seniors and Reserves play the same opposition on
  the same afternoon, so date+opponent alone read the whole day's card as one
  already-synced game and silently dropped every other team's result. Matching
  is (date, opponent, grade name); a game against the same club that day under
  a *different* grade still imports, with a `check` warning naming the other
  grade in case the two are the one match under two labels.
- **Warning kinds mirror the scorecard reader**: `sheet_error` (the sheet's own
  figures disagree — goals×6+behinds ≠ total, a "Won" against level scores, a
  margin that doesn't match) vs `check` (a result worked out from the scores
  because the outcome column was blank, a 0-0 game, a neutral-ground final).
  Nothing is auto-corrected; the import button reads "IMPORT N, KEEP AS
  WRITTEN" when errors remain. A row that genuinely can't import (no date, no
  season) is `blocked` and named, never silently dropped.
- **Outcome vocabulary is matched on substrings**, since a register hand-kept
  since 1947 spells things its own way — the reference sheet writes "Forfiet"
  throughout. Cancelled/unscored rows are always skipped; forfeits import as
  the W/L they were (toggle); byes are opt-in and stored with
  `status='BYE'` + NULL result, which is what keeps them out of BOTH the
  W/L/D tallies and the played count.
- **Blank home/away is neutral, not an error** — 103 rows of the reference
  sheet are finals at a third club's ground. Stored with our club as the
  nominal home side (affects only which column the name prints in) and
  reported once as a summary warning.
- **Column auto-mapping is a GLOBAL best-assignment, not per-field.**
  "HamPoints" and "OppPoints" both score 0.8 against the plain synonym
  "points", so picking each field's own best header independently is a coin
  flip; taking the strongest pair in the whole matrix first resolves both.
  Plus a **content sniff** for a header that says nothing ("Column1" — which
  is exactly how a real club's result column arrives): a column whose VALUES
  are ≥60% a known vocabulary is that field. All 18 columns of the reference
  sheet map with no human input.
- **`frontend/src/afl/pages/admin/importMatching.jsx`** is the extracted shared
  wizard kit (`SearchSelect`, `MatchTable`, `FieldRow`, `StatusBadge`,
  `parseSeasonGuess`, …) now used by BOTH import wizards — `AflAdminImport`
  was refactored onto it rather than a second copy being written.
- **Undo deletes the games** (details/periods/lines/events cascade), scoped to
  `source='import'` so a game the sync has since taken over is never removable
  by undoing the upload that first created it. Because ids are derived, a
  re-upload restamps rows with the new batch — undo removes what that batch
  last wrote, and the older batch's log entry remains.
- **`GET /resolve` caps per-row detail at `ROW_DETAIL_LIMIT` (5000)**; every
  count, and the commit itself, always covers the whole sheet.
- **Verified end to end against a real Postgres** (22 checks): the lifespan's
  new ALTERs, the full 3,044-row sheet, season/grade creation and reuse, the
  one genuine sheet error caught, the synced-game guard, re-import
  idempotency (0 new / 2875 updated), byes on/forfeits off, and undo leaving
  the synced game intact.
- **Not built**: no cricket equivalent (Core already has Upload Scorecard and
  manual games for this), and an imported result carries no player lines —
  it's the match record, not a scorecard.

## One look across BetterClubhouse: the Directory is the reference (v9.10.1, Aug 2026)

Reported from a phone: the Directory reads well, and the older full editors
(Committee Administration and friends) clearly did not match it.

- **The difference was never the typeface.** The obvious guess is `font-display`
  vs the body font, but a club that has not chosen its own typography resolves
  both to the same face, and measuring the live pages confirmed every heading
  was already Geist. **Measure the rendered page before theorising about a
  design inconsistency** — the real causes were heading SIZE (24px in the page
  body vs 19px in a sticky header), tab rows that could not wrap, mono used as
  body copy, and mono uppercase buttons.
- **`ModuleLayout` already renders the Directory header** — 19px title, mono
  caption, sticky, on `--pb-surface`. The ten editors simply never passed
  `title`/`caption`, so the bar showed only the module lockup while the page
  drew its own 24px `<h1>` underneath. Passing the two props and deleting the
  in-body heading block is the whole fix. **A new Clubhouse screen should pass
  `title` and `caption` and draw no heading of its own.**
- **`FilterPill` (components/admin/ui.jsx) is byte-for-byte the Directory's own
  chip**, so the editors' hand-rolled mono tab buttons became `FilterPill` and
  matched for free. Prefer it over a local tab button.
- **Tab rows wrap, they do not scroll sideways.** Two screens overflowed at
  390px purely because a `flex` row of tabs could not wrap; the Directory's
  filter chips already wrap onto four lines on a phone, so wrapping is the
  house answer. `SegTabs` wraps too now.
- **The repo rule was already right and simply unenforced**: mono is for labels
  and figures, never buttons, headings or body. Long mono paragraphs moved to
  the body font and ~56 mono uppercase action buttons became body-font sentence
  case across the ten editors.
- **Verified by screenshotting all 17 Clubhouse screens at 390px** and asserting
  on each one's `<h1>` computed font, size and weight plus
  `documentElement.scrollWidth > clientWidth`. That check is worth repeating
  whenever a Clubhouse screen is added.

## Confirming the roster, a frozen first column, and the drags that never worked (migration 222, v9.10.0, Aug 2026)

- **"Confirm roster" is the name, in the code as well as the UI.** The action was
  briefly called "closing off a week"; it was renamed everywhere the same day
  (service functions, routes, the `roster_weeks.status` value, the migration
  filename) rather than leaving the two languages to drift.
- **`roster_shifts.worked_hours` is the roster's record of what was worked;
  `volunteer_hours` is the club's ledger.** The flow is one-way — confirming
  POSTS to the ledger, nothing reads back. NULL `worked_hours` means "not
  checked yet" and a checked **0** means "rostered but did not turn up"; both
  have to be expressible, which is why it is nullable rather than defaulted.
- **Confirming RECONCILES, it never appends.** `uq_volunteer_hours_shift` (a
  partial unique on `roster_shift_id`) makes the insert an upsert, and a shift
  that has since been unassigned or checked down to zero has its posted row
  DELETED. Without that, correcting a mistake would leave the original behind
  and the ledger could only ever grow. `is_paid` is stamped from the role type
  at the moment of confirming and never revisited (migration 221's snapshot rule).
- **Unconfirming deliberately leaves the posted hours alone.** They were worked;
  deleting them because someone wants to fix a typo would take the club's ledger
  down with the correction. Confirming again reconciles.
- **The frozen first column is `position: sticky` on the GRID ITEM.** A grid
  item's containing block is its grid area, which suggests this cannot work —
  it does, verified in an isolated page and then in the app (9 cells holding at
  x=232 through a 694px scroll). **The trap is the background**: the rail's
  opaque `background` must not be overridden by a row tint, or the columns
  scrolling underneath show straight through it. The open-shifts row layers its
  amber over the top via `backgroundImage` instead.
- **`usePref(key, fallback)`** in `redesign/ui.jsx` is the per-user, per-browser
  screen preference (keyed on user id, like the screen introductions). Reads in
  the state initialiser, not an effect, or the panel renders open for one frame
  before snapping shut. Used for the minimised rail and the volunteer pool.
- **The People view's drags were half-wired.** `cellDrop` only ever read
  `st.dragId` (a shift) and `slotDrop` (a person) was attached in the AREAS view
  only, so dragging a volunteer from the pool onto an open shift in People did
  nothing and said nothing. Open chips are drop targets now.
- **A shift can only be dropped in its own day column.** It carries its own day,
  so accepting it anywhere else silently left it where it was — which reads as
  the roster ignoring you. Other days don't `preventDefault`, so the cursor says
  no before the mouse is released; a person who would be blocked still accepts
  the drop, so the refusal comes back from the server as a sentence.
- **Testing HTML5 drag-and-drop**: Playwright's real mouse cannot steer
  Chromium's native drag loop — it hangs. Dispatch `DragEvent`s instead, and put
  the `dragstart` and the `drop` in SEPARATE `evaluate` calls, or React has not
  re-rendered with the drag in flight and every drop reads as refused.

## Cross-club member leak: the opposition were enrolled as our members (Aug 2026)

Reported live: a High Wycombe player (and HW club admin) appeared in
**Applecross's** Clubhouse Directory, under Everyone and Players, carrying his
real email, phone and photo. Not a display bug — Applecross genuinely held a
`fee_members` row for him.

- **Cause: `services/fees.py::recompute_fee_match_days`.** It selected the
  season's games (correctly org-scoped through grades → seasons), then read
  **every** `game_appearances` row on those games and enrolled the player behind
  each one as a member, with a comment asserting "only our club's players have
  rows". **That assertion is false and this file already documents why**: a
  fixture between two clubs that BOTH sync is a single `games` row, and each
  club's sync writes its own players' appearances against it. So every opponent
  from every both-synced club became one of our members. The `select(Player)`
  that followed had no org filter either, so nothing downstream could catch it.
- **This is the exact anti-pattern the v8.79.3 note names**: never read a
  per-game table "for a game in our org's grades" without ALSO scoping
  `players.organisation_id` when attributing to our side. The fix loads the
  appearing players org-scoped FIRST, then filters the appearances to them, so
  member creation and match-day charges both inherit the scope.
- **`services/directory.py::list_people` amplified it.** Its
  `LEFT JOIN players p ON p.id = fm.player_id` had no org condition, so a member
  row pointing at another club's player served that club's **photo, email and
  phone** into our Directory. Now joined on `AND p.organisation_id =
  fm.organisation_id`: a stray link degrades to a plain name rather than leaking
  contact details. **Any read-through from a member to its player needs this.**
- **`python -m app.scripts.purge_foreign_members [org|all] [--apply] [--delete]`**
  clears what was already written. Dry run by default; archives (reversible,
  and enough to clear the Directory) unless `--delete`. A row with anything
  attached — a payment, role, qualification, committee term, logged hours, a
  family link, a roster shift — is **reported and left alone**, because the link
  is wrong but the attached work may not be.
- **The state is now unrepresentable, not just filtered out (migration 223).**
  A composite foreign key on `fee_members (organisation_id, player_id)` →
  `players (organisation_id, id)` means Postgres refuses a member row that
  points outside its own club, whatever code is writing. Added **NOT VALID**:
  enforced on every new INSERT/UPDATE immediately, while rows the earlier bug
  wrote are tolerated until `purge_foreign_members` clears them. Run
  `ALTER TABLE fee_members VALIDATE CONSTRAINT fk_fee_members_player_same_org`
  once a database is clean to turn on the retrospective check too.
- **`list_people` reads `our_player_id` (the org-scoped join result), never
  `fm.player_id`.** A link that does not resolve within the club must not tag
  the person "Player" and must not carry a `player_id` through to the frontend —
  otherwise a stray row still reads as one of our players and still links to
  someone else's profile. Scoping the join alone was not enough.
- **Verified by reproducing it**: two clubs, one shared fixture, both sets of
  appearances on it. With the fix reverted the suite fails on exactly the
  reported symptom (the opponent enrolled and listed); with it in place, 14
  checks pass including that a pre-existing bad link leaks no contact details
  and a re-sync does not recreate the row.
- **The three different people counts are NOT all the same bug.** Core's
  Players screen reads `players` (unfiltered, so it is the true player count),
  Accounts reads `fee_members` for one season, the Directory reads all
  `fee_members` ∪ org players, and BetterComms Lists reads `comms_contacts` —
  a **fourth, separately-populated table** that nothing syncs from the other
  three. A club will legitimately see four different totals until step 4 of the
  Clubhouse handoff (joining the data) is done.
## The shared-game rule: scope the PLAYER, not just the game (v9.11.1, Aug 2026)

The member leak above was one instance of a much wider bug. An audit of every
SQL block that reads a per-game table and joins `players` found **15 more
sites** doing the same thing, and a production count confirmed **326,816
cross-club rows across 38 clubs** were being read as the viewing club's own.

- **The rule, and it is not optional**: a fixture between two clubs that BOTH
  sync is a SINGLE `games` row, and each club's sync writes its own players'
  rows against it. So `games → grades → seasons → organisation_id` tells you the
  game is in our competition; it tells you **nothing** about whose player a row
  belongs to. **Any read of `batting_innings`, `bowling_spells`,
  `fielding_stats`, `game_appearances`, `partnerships`, `fall_of_wickets` or
  `bowler_wickets` that attributes a row to our side must ALSO scope
  `players.organisation_id`.** Season-aggregate reads (`player_season_stats`)
  are a different shape and are already handled by the v7.32.1 view fix.
- **Fixed here**: `aggregations.get_fielding_leaderboard` (the finals and
  captain branches, the only public-facing one), all ten of `iq_team.py`
  (`_team_fielding`, `_batting_pairs`, `_attack_structure`, `_captaincy`,
  `_combinations`, `_discipline`, `_collapse_bowlers`, `_role_ratings`,
  `_batting_extra`), `iq_review.game_review`'s best-partnership query,
  `iq_teammates.teammates`, and `iq_opponent._db_season_accumulators` (×3).
  `iq.py` had already been done in v8.74; `iq_team.py` never got the same pass.
- **`_captaincy` also summed the OPPOSITION's runs** into "average team score
  under this captain" — its `scores` CTE read `batting_innings` for our games
  with no player scope at all. Not a join bug, so an audit that only looks at
  `JOIN players` misses it. Check the CTEs too.
- **`is_club_innings` is set PER CLUB** (`sync.py`: TRUE for whichever side is
  its own), so a shared fixture's one `games` row carries BOTH clubs'
  partnerships marked TRUE. `WHERE game_id = X AND is_club_innings IS TRUE` is
  therefore NOT a club filter. That is what put the opposition's best stand in
  our own match review.
- **Scope ONE side of a partnership, not both.** Both batters in a stand are
  from the same innings and so the same club, so scoping either one excludes an
  opposition pair. Scoping both would also drop a legitimate stand involving a
  teammate whose `players` row sits under another club (the shared-participant-
  GUID case). `_combinations` is the exception and scopes BOTH, because its
  pairs come from appearances on the same game, where one of ours can genuinely
  pair with one of theirs. Same reasoning for `bowler_wickets`: scope the
  BOWLER, leave the fielder, they are on the same fielding side.
- **Deliberately left unscoped** (verified safe, do not "fix" them):
  `aggregations.get_player_partnerships` and `iq_trends.bowler_deep_dive`
  (anchored on a specific `:pid`), `yearbooks._generate_narrative_core`,
  `statlab.derived_best_partnership_pair` / `_partnership_aggregates_pair` /
  `_century_partnerships_pair` / `_bowler_fielder_combo` (one side already
  scoped), and `iq_team._team_fielding`'s combo query / `_batting_pairs`
  (partner alias, per the rule above).
- **The audit is repeatable and worth re-running when adding a per-game read.**
  Extract every triple-quoted SQL block, keep those with a per-game table after
  `FROM`/`JOIN` **and** a `JOIN players <alias>`, and flag any alias with no
  `<alias>.organisation_id` anywhere in the block. Match the table only after
  `FROM`/`JOIN` or `st.batting_innings` (a COLUMN on `player_season_stats`)
  produces a pile of false positives.
- **Read-side only.** No migration, no data change, no re-sync: the rows are
  correct and belong exactly where they are. Every affected figure corrects
  itself on the next page load.

## BetterFootball — Import Awards (v9.9.0, Aug 2026)

A club's honour board imported as real `player_achievements` rows. Third
sibling of Import Stats (`routers/afl/imports.py`) and Import Results
(`routers/afl/result_imports.py`), built against a real 7,360-row 1959–2026
awards register from an AFL club.

- **`routers/afl/award_imports.py`** (`/club-admin/award-imports/*`, cap
  `MANAGE_AWARDS`) — preview → resolve → commit → undo, plus a template.
  **No schema change**: it writes the existing `player_achievements` +
  `org_award_definitions` + `achievement_import_batches` tables, so an
  imported award is indistinguishable from one typed into the Awards screen.
- **An award the catalogue doesn't carry is CREATED** (`org_award_definitions`),
  which is what stops a historical trophy existing on player rows and nowhere
  in the club's own award list. A label already there is reused and **keeps its
  own category** — the Award Types screen owns filing, and an upload retyping
  a category the club set up by hand is the wrong way round. Only an award
  being created has its category/subcategory editable on the wizard.
- **`_award_key` collapses case AND "&"/"and"**, which is why 43 raw trophy
  spellings in the reference sheet resolve to 39 awards ("Runner up Best &
  Fairest" / "Runner Up Best & Fairest" are one trophy). A near-miss offers a
  suggestion at ≥0.80 but still DEFAULTS to creating the label — "Best
  Clubman" and "Best Clubperson" are two real trophies at plenty of clubs.
- **Identity is the sheet's own player id where one is mapped**, not the name.
  A register spells one person several ways, and — the dangerous half — holds
  two different people under one name (two Jack Reeds). But **one id does not
  always mean one person either**: nine ids in the reference sheet cover two
  genuinely different names each (an id reused after someone left), so
  `_build_identities` only lets an id unify rows whose names agree once case
  is set aside, and splits it per name otherwise. A NAME covering more than
  one identity is never auto-matched — it comes back `clash` with the roster
  player offered as a candidate for each.
- **A row naming no award is skipped, not invented into a nameless one** —
  6,241 of the reference sheet's 7,360 rows are the club's record of who
  turned out, not honours. Counted and reported, never silently dropped.
- **Re-upload is safe**: a row already on the honour board for that person,
  season and award reads as `exists`. Matched on the player id when there is
  one and on the name ONLY for someone about to be created — checking both
  would read one Jack Reed's honour as already recorded because the other
  has it.
- **`players_unresolved` counts only people who actually won something.** An
  unmatched name with no trophy against it has nothing riding on the decision,
  and counting it sends an admin hunting for a problem that isn't there.
- **Undo removes the awards only.** Players and award types the import created
  are left — a player record is a person, and a catalogue entry may already be
  in use elsewhere. Same call Import Stats makes.
- **`PlayerMatch` was extracted from `AflAdminImport.jsx` into
  `importMatching.jsx`** and is now shared by Import Stats and Import Awards
  (`sheetLine` prop for the per-name context line, `key`-based overrides so an
  id-carrying sheet can hold two people under one name). `SearchSelect` gained
  an `award` kind. New page `AflAdminAwardsImport.jsx` at
  `/admin/import-awards`; the Awards screen's old one-shot CSV uploader was
  replaced by a link to it, so there's one award-import path rather than two.
  `POST /achievements/import` and its template endpoint still exist and are
  unchanged — nothing in the UI calls them now.
- **The honour board on the public player profile** (v9.9.1) — an imported
  award was reaching `player_achievements` and nowhere else, because the AFL
  profile never read them. `GET /afl-players/{id}` now returns `achievements`
  and `frontend/src/afl/components/honours.jsx` renders both surfaces Core
  has: the coloured pills under the player's name and a full Honour board
  section, grouped honour / award / milestone / role on the same `--pb-cat-*`
  tokens and the same `styles/honour-badge.css` cards. Three rules worth
  keeping: **repeated wins of one trophy are ONE entry** carrying every year
  (a nine-time winner is not nine cards; past three years the pill reads
  "N× · first–last"); the **display_name rename is resolved in Python, not a
  join** — a club holding two definitions with the same name would otherwise
  fan one award row into two; and the **name fallback only applies to a row
  with no `player_id` at all**, so one of two same-named players' honours can
  never surface on the other's profile. `afl/components/honours.css` widens
  the shared 160px card to 196px and allows a third title line, scoped under
  `.afl-honours` — football trophy names ("3rd Runner Up Best & Fairest") were
  being clipped mid-name by Core's two-line clamp.
- **Verified end to end** against a real Postgres (28 checks) with the full
  7,360-row sheet, and driven through the real app in a browser: auto-mapping
  all four columns incl. "PayerID", 1,119 awards written, 39 award types
  created, 25 players created, the shared-name split, a re-upload importing 0,
  a sheet with no id column, a sheet naming its own categories, and undo
  leaving the award types intact. The honour board has its own 7 checks (the
  rename, the duplicate-definition fan-out, the name fallback and the
  same-name guard) and was checked in both light and dark themes.

## Roster shift CRUD, paid vs volunteer hours, diary year, draft minutes (migration 221, v9.8.0, Aug 2026)

Six items from the second live feedback batch, plus the paid/volunteer split that
underpins one of them.

- **Paid work is derived from the role type, never stored as a second flag.**
  `club_role_types.category` has accepted `'paid'` since the roles catalogue was
  built but nothing ever read it, so a club could not tell the bar manager it
  employs from the parent running the canteen for nothing.
  `roster.area_pay_kinds` resolves an area → its `required_role_id` → that
  role's type category, and `PAID_CATEGORY = "paid"` is the only test. **Don't
  add a per-shift or per-person paid flag** — it would immediately disagree with
  the role type. `volunteer_hours.is_paid` (migration 221) is the ONE exception
  and is deliberately a snapshot: it records what the derivation decided AT THE
  TIME the hours were logged, so retyping a role later cannot silently rewrite
  last season's wage bill.
- **`roster.hours_summary(start, end)`** returns four numbers per person plus
  totals: `rostered_{volunteer,paid}` (the length of every shift they are
  assigned to in the window, from `roster_shifts`) and `worked_{volunteer,paid}`
  (what was logged afterwards, from `volunteer_hours`). **Rostered and worked
  are deliberately separate** — the gap between them is the thing a club wants
  to see, and a club's wage bill and its volunteer effort must never be summed
  (one goes to the treasurer, the other to the grant application). Surfaced as a
  third **Hours** tab beside People/Areas on the Roster (`HoursView` in
  `screens/Roster.jsx`, week/month/season spans; season is Jul-Jun).
  `volunteer_hours.roster_shift_id` exists for hours logged against a specific
  shift and **has no FK on purpose** — `roster_shifts` is one of the raw-SQL
  lifespan tables, so an ORM-side constraint would make `create_all()`
  order-dependent on a fresh database.
- **Shift CRUD** (`roster.create_shift/update_shift/delete_shift`, routed and
  org-scoped). Weekly patterns still materialise the week; this is for the shift
  a pattern should not carry (a final, a night game, an extra hand behind the
  bar) — editing the pattern would change every other week too. The Roster
  sidebar carries `+ Add a shift` and, with a shift selected, `Delete this shift`.
- **`PersonPanel`** on the Roster: click anyone in the volunteer pool to read and
  edit their availability (`roster.member_detail` / `set_member_availability`)
  and read their qualifications, rather than being sent to Directory → Volunteers.
  **Availability is stored as Monday=0 indexes but read tolerantly** — the
  volunteers router types `available_days: List[str]`, so `roster.day_index()`
  accepts `'Monday'`/`'mon'`/`'0'`/`0` and `set_member_availability` normalises
  writes back to indexes. That mismatch was the original Roster HTTP 500.
- **`organisations.diary_start_month`** (1-12, default 7, so no club changes by
  upgrading) drives the Club Diary's season plan; `ClubDiary.jsx`'s
  `monthDefs(startIdx, startYear)` uses real calendar day counts rather than the
  old hardcoded table. Edited from Clubhouse → Settings (`DiaryYearPanel`).
- **Draft minutes** (`POST /committee/meetings/{id}/draft-minutes`) composes the
  attendance, agenda, motions/votes and actions the meeting already holds into a
  prompt (`claude-haiku-4-5`, `strip_em_dashes`, rate-limited to 10/hour/club).
  **It returns the text and never saves it** — minutes are the club's legal
  record, so a machine writes the first pass and the secretary decides whether
  any of it is true. No API key configured gives a clean 503, not a 500.
- **Action board + timeline share one filter** (search, category, objective,
  assignee, overdue) in `AdminCommittee.jsx` — one `shown` list feeds both, so
  they can't disagree about what is in scope.
- **Fixed an infinite request loop** in `AdminCommittee`: the members effect
  depended on `toast`, and its own error handler raised a toast, which changed
  the context value, which re-ran the effect. A club without the fees module hit
  `/fees/all-members` 60+ times per page load. **Watch for this shape anywhere**
  a `catch` calls `toast.*` in an effect that lists `toast` as a dependency.
- **Local harness gotcha**: `player_achievements`, `org_award_definitions` and
  `audit_logs` are lifespan-created raw-SQL tables, so a stubbed-lifespan boot
  has to create them by hand. A missing `audit_logs` is especially misleading —
  `audit_log` catches its own failure and logs a warning, but the aborted
  transaction then poisons the caller's commit, so an unrelated PATCH 500s.

## BetterClubhouse follow-ups: roster, orphaned editors, governance (v9.4.0, Aug 2026)

- **The roster was blank for any club that opened it before configuring areas.**
  `get_or_create_week` created the week row on first visit, generated shifts from
  zero patterns, and every later visit found that empty week and returned it —
  permanently. It now fills a week that is still genuinely empty (`_has_shifts`
  guard, so a roster in progress is never touched). Reproduced and fixed against
  a real Postgres: 0 shifts → 30. **The roster screen also reports the real
  error + HTTP status now**; it used to say "Could not load the roster." for a
  403, a 500 and a timeout alike.
- **~5,300 lines of working CRUD were unrouted** since commit `6ff23c6`, when
  the redesign screens took `/admin/committee`, `/admin/events`, `/admin/assets`
  etc. The redesign screens are read-only viewers; the editors
  (`AdminCommittee` 885 lines, `AdminFamilies` 926, `AdminClubDiary` 890,
  `AdminAssets` 693, `AdminEvents` 646 with the QR code + ticketing, plus
  Qualifications/Volunteers/Roles/Activities) had nowhere to be reached from.
  They now live under `/admin/clubhouse/*/manage` and each viewer carries a
  `ManageLink` to its editor. **Folding the CRUD into the viewers is still the
  right end state** — this is the bridge, not the destination.
- **Migration 217 — committee governance.** `club_objectives` (the business /
  strategic plan an action serves), `committee_task_dependencies`,
  `meeting_motion_votes` (named votes; the tallies on `meeting_motions` stay,
  and are *derived* from names when names exist), `committee_notes`
  (polymorphic: task | motion | meeting | objective), plus columns on
  `committee_tasks` (budget_estimate, actual_expenditure, percent_complete,
  start_date, objective_id, meeting_id, motion_id, outcome_notes,
  closed_by_member_id) and `meeting_motions` (is_resolution, resolution_ref,
  resolved_at). `committee_documents` gained `entity_type`/`entity_id` so a
  quote hangs off the action that asked for it — **still link-based by design**,
  the club's docs stay in Drive/Dropbox. Only a **carried** motion can become a
  resolution (422 otherwise). `GET /committee/objectives/progress` reports the
  plan against the actions serving it. All verified end to end against a real
  Postgres, not just compiled.
- **`await db.refresh(obj)` after `commit()` before serialising an ORM object** —
  the resolution endpoint hit `MissingGreenlet` exactly as the Square-sync note
  warns. commit() expires the instance and the response then lazy-loads outside
  the greenlet.
- **`owes_money` is a club audience field** (`comms_segments.SPECIAL_FIELDS`).
  A balance is derived, never stored, so it can't be SQL: `build_query`
  resolves the owing player ids in Python via `services/fees.owing_player_ids`
  (the same `_financials` the Accounts screen runs) and the rule becomes
  `player_id IN (...)`. **Don't reimplement the balance in SQL** — that's how
  the sidebar badge and an audience start disagreeing.
- **Local verification harness**: a real Postgres + the app is reachable in this
  environment. `Base.metadata.create_all` gets the ORM tables; the raw-SQL
  tables only exist because the lifespan creates them, and the lifespan aborts
  on the first failing statement (it ALTERs tables that later raw-SQL blocks
  create). Replay the `text(...)` statements from `main.py` skipping failures,
  and boot with the lifespan stubbed out.
- **Still not built**: a Gantt view for committee actions (the data — start
  date, due date, dependencies, percent — is all there now, and `ClubDiary.jsx`
  already derives a critical path from the same shape, so it is a frontend
  job); file *upload* against a committee record (links only); emailing everyone
  rostered for a period; committee ↔ BetterStats Awards "Office Bearer" sync
  (two unrelated things sharing a name — Clubhouse's is a *role type*, Awards'
  is an achievement category); and editing UI for the new governance fields
  beyond the API.

## BetterAdmin → BetterClubhouse: four sub-modules merged into one (v9.3.0, Aug 2026)

BetterFees, BetterComms, BetterMerch and BetterClubManager shared a codebase but
not a design language, and duplicated three person lists, two money ledgers, two
Square connections and three reports surfaces. They are now **one module,
BetterClubhouse**, on the old BetterAdmin amber. Handoff:
**`docs/design_handoff_betterclubhouse/`** (`README.md` is the spec,
`BetterClubhouse.dc.html` the prototype, `BetterAdmin Review.dc.html` the why,
`PROJECT_RULES.md` the scope rule below).

- **The `admin` key is unchanged.** Only display names moved —
  `MODULE_GROUPS.admin.name`, `moduleBrand('admin').name` and the backend
  `BILLABLE_MODULE_NAMES[admin]` read "BetterClubhouse". Entitlement, billing,
  `org_module_subscriptions` and every stored row still key on `admin` /
  `fees|comms|merch|crm`. **Two things deliberately still say BetterAdmin**: the
  public marketing site (incl. the `/modules/betteradmin` URL, its SEO/OG
  metadata and the dated blog articles) and `billing_pricing.py` / `pricing.js`,
  which are a hand-synced pair feeding Stripe Product creation — an existing
  Stripe Product keeps its old name until it's renamed in the dashboard. Both
  are commercial calls, not design ones.
- **`components/admin/ModuleLayout.jsx` is the shell for every module surface**
  and now carries the whole design: 232px sidebar (not 240), club identity +
  season line, module lockup (the `← Back to admin` link is gone), grouped nav
  with count badges, and — the load-bearing decision — the **module switcher,
  account and bookmarks in the sidebar FOOTER**, which frees the sticky screen
  header for title + mono caption + `?` + filters + stat readouts + one primary
  action. New optional props: `caption`, `onHelp`, `filters`, `stats`, `bare`
  (screen owns its padding), `hideHeader` (screen draws its own — the
  transitional escape hatch the promoted ClubManager screens use). **One
  breakpoint for the module: `lg` (1024px)**, sidebar becomes a drawer below it.
- **`components/admin/ui.jsx` is the one admin UI language** — Button,
  TextInput/Select/Field/SearchInput, FilterPill, StatCard, StatReadout,
  Caption/FieldLabel/StatLabel, AttentionRow, TableWrap/TableHead/TableRow/
  TableFootRow/Cell, Badge, Chip, Initials, ListRow, Drawer, Toast, Note,
  HelpDot. **Use these instead of writing a local copy** (that's what produced
  the four divergent sets). Two rules: mono is for labels and figures only,
  never buttons/headings/body; and text on an accent fill is `ON_ACCENT`
  (`#0a0d14`), one answer everywhere. Accent tints come from `TINT` (color-mix,
  NOT `rgba(var(--pb-accent-rgb), α)` — that var is space-separated and the
  comma-form rgba can't parse it).
- **`--pb-accent-ink`** (theme.css) is the accent as *text*, darkened on light
  so amber stays legible on white. It's derived from whatever `--pb-accent`
  resolves to **on the element it's computed on**, so any surface that
  re-points `--pb-accent` must also carry **`.pb-ink`** (ModuleLayout's root
  does). `--pb-positive-ink` / `--pb-red-ink` are the same idea, static.
  `.pb-card` radius went 6px → 10px, which moves most of the app onto the new
  scale in one change.
- **`BetterClubhouseLayout`** owns the merged nav: six capability-gated groups
  (People / Money / Stock / Comms / Club / Setup) with `Today` above the first
  heading. Items carry `cap` (a capability, or an array meaning any-of),
  `module` (one of the umbrella's paid keys — the whole group disappears for a
  club that doesn't hold it) and `super` (the promoted ClubManager screens —
  real data, and open to the club's own admins since v9.6.1 — see the access
  note below). **The four old layouts
  are thin wrappers over it now**, which is how every existing screen inherited
  the shell without being rewritten. `BetterMerchLayout` still owns the
  storefront flag and passes `storefront` down.
- **Counts are computed once**: `pages/admin/clubhouse/data.js`'s
  `useClubhouseData` (module-level cache, 60s TTL) + `deriveCounts` feed the
  sidebar badge, the Today row, the Accounts KPI and the Reports figures from
  the same fetch. **Don't denormalise these** — if issuing a shirt changes a
  balance, all of them have to move together.
- **New screens** (`pages/admin/clubhouse/`): `ClubhouseToday` (the front door —
  aggregates money/stock/comms, omits a row whose count is zero),
  `ClubhouseAudiences` (replaces Contacts + Lists + Segments; both
  `/admin/comms/segments` and `/admin/comms/lists` now redirect here),
  `ClubhouseIntegrations` (Square + Xero + email sending, each linking to the
  screen that owns the setup), `ClubhouseReports` (source selector),
  `ClubhouseSettings` (the screen-introduction flag).
- **Screen introductions** (`clubhouse/intro.jsx`): `'always' | 'once' | 'never'`,
  **per person** (localStorage per user id), default `once`. Today never gets
  one; a deep link (`navigate(to, { state: { skipIntro: true } })` — every Today
  action uses it) always skips AND marks seen; the `?` reopens on demand in every
  mode. `useScreenIntro` decides **once at mount** in a state initialiser —
  deriving it live flashes the page for one frame, because marking the screen
  seen re-renders it away.
- **The indigo is retired.** Every `#6366F1` / `rgba(99,102,241,α)` in
  `pages/admin/clubmanager/` became `var(--pb-accent)` / `color-mix`, and
  `MODULE_BRAND.clubmanager` is gone (aliased to `admin`). `ClubManagerApp`
  dropped its own 232px sidebar and renders inside `BetterClubhouseLayout`
  (`bare hideHeader`); its screen comes from the route via `initialScreen`,
  synced by an effect because React can reuse the component across two routes.
- **⚠ BetterComms scope rule — hard, not a preference.** Club scope reads the
  club's own people; Super Admin scope is BetterCricket's sales telemetry
  against the Clubs Directory. **Never expose the Super Admin fields, context
  bar or copy in a club build** — not behind a dropdown, not greyed out, not
  listed and disabled. Enforced structurally: `segmentFields.jsx` exports
  `CLUB_FIELD_DEFS` (imported ONLY by `clubhouse/ClubhouseSegments.jsx`) and
  `DIRECTORY_FIELD_DEFS` (imported ONLY by `clubhouse/InternalSegments.jsx`),
  with no runtime context switch to get it wrong; `CommsContextBar` no longer
  renders in the club layout. Apply the same rule to any future module that
  gains a platform-side mode.
- **Both segment builders are Clubhouse screens on one URL** (`/admin/comms/
  segments`), and `clubhouse/SegmentsRoute.jsx` is the single place the two are
  chosen between — on `is_marketing_org`, once, lazily, so a club session never
  fetches the directory chunk. The internal one used to be a separate page
  outside the module (`SuperDirectoryAudiences`, on the plain `AdminLayout`
  chrome), so picking Segments in internal mode threw you out of BetterClubhouse
  mid-task; that page is gone and its URL redirects. **No backend change was
  needed** — `/segments/*` already resolves against whichever org you are acting
  as (`get_current_club`), and `/segments/options` already returns
  `context: "directory"` for the outreach org.
- **`clubhouse/segmentEngine.jsx` is the shared builder**: `useSegments` (load,
  live sizes, draft, resolve-as-you-type, save/duplicate/delete, "Email these N
  now") plus `RuleBuilder` / `SegmentListPane` / `SegmentTitleRow` / `CountBar`.
  It imports NEITHER field set — `defs` is a required argument, and each screen
  passes the one constant it imports. **`defs` is required because `newRule`
  reads the first field's first operator**, so an empty vocabulary is a
  TypeError, which is what a saved segment carrying zero rules would hit.
  Adding an `isInternal` flag in here is the wrong move; a third mount is a
  third screen.
- **Not done, and it's the real work**: step 4 of the handoff's sequencing —
  joining the data. The Directory is still not the one person list (Fees
  members, Comms contacts and the ClubManager directory remain three), and a
  member still has a fee balance and a merch balance rather than one account.
  Accounts, Directory and Inventory therefore keep their existing data layers;
  only their shell, language and naming changed. The BetterClubhouse **logo mark
  also does not exist yet** — the lockup currently reuses `betteradmin.svg`.

## BetterClubhouse follow-up: roster fix, committee governance (v9.4.0–v9.5.0, Aug 2026)

The audit that followed the merge found one real bug, a pile of orphaned
editors, and a set of genuinely-unbuilt committee features. All three are done.

- **The Roster bug was a permanently empty week, not a load failure.** A club
  that opened the roster BEFORE configuring any operational areas got a
  `roster_weeks` row created with zero shifts, and nothing ever regenerated it —
  every later visit found the empty draft week and returned it, so the roster
  stayed blank forever. `services/roster.py` now regenerates shifts when it
  finds a `draft` week with none (`_has_shifts` → `_generate_shifts`). Verified
  against real Postgres: 0 → 30 shifts. The screen's error state also shows the
  real message and HTTP status now instead of a bare shrug.
- **~5,300 lines of working CRUD were orphaned since `6ff23c6`** (pre-existing,
  not caused by the merge): Committee, Events, Facilities, Club Diary,
  Families, Qualifications and Volunteer hours all had full editors with no
  route. Routed back and linked from the read-only screen that shows their
  data. `AdminCommittee` lives at **`/admin/clubhouse/committee/manage`**
  (open to club admins since v9.6.1), reached from the Clubhouse Committee screen —
  `/admin/committee` is the Clubhouse screen, not the editor.
- **Migration 217 — committee governance.** `club_objectives`,
  `committee_task_dependencies`, `meeting_motion_votes`, `committee_notes`;
  plus columns on `committee_tasks` (objective_id, budget_estimate,
  actual_expenditure, percent_complete, start_date, closed_by_member_id,
  outcome_notes, meeting_id, motion_id), `meeting_motions` (is_resolution,
  resolution_ref, resolved_at) and `committee_documents` (entity_type,
  entity_id). Mirrored idempotently in `main.py`'s lifespan as usual.
  **Only a carried/passed motion can become a resolution** (`make_resolution`
  raises otherwise). Per-member votes RE-DERIVE the tallies, so a club that
  just counts hands still only stores a count.
- **`frontend/src/components/admin/clubmanager/governance.jsx`** is the whole
  governance UI: `NoteThread`, `AttachedDocuments`, `ActionPlanPanel`,
  `MotionGovernance` (vote matrix + resolution toggle), `ObjectivesTab` and
  `ActionTimeline` (the Gantt). The timeline groups rows by objective, derives
  the critical path from `depends_on` over not-done actions, and lists undated
  actions underneath. Two things to leave alone: its month ruler shares the
  rows' `w-[38%]` + `flex-1` geometry rather than guessing offsets
  arithmetically, and **ticks snap to the 1st of the month** (iterating
  `min + n months` mislabels a mid-month start and drops the final month).
  `chain()` carries a `walking` cycle guard — nothing server-side rejects
  A-waits-on-B-waits-on-A, only self-dependency, so without it a saved cycle
  hangs the tab.
- **Pydantic models are the trap when adding a column here.** New fields on
  `TaskCreate`/`TaskPatch`/`DocumentCreate`/`DocumentPatch` silently never
  reach the service if you only add them to the migration and the service —
  that's what made `objective_progress` report 0 actions. Also: after
  `commit()` the instance is expired, so serialising it lazy-loads outside the
  greenlet and 500s with `MissingGreenlet` — `await db.refresh(obj)` before
  returning (the vote and resolution endpoints both need it).
- **`owes_money` is an audience condition**, resolved server-side from the same
  `_financials` the Accounts screen runs (`fees.owing_player_ids`), so "email
  everyone who owes" targets exactly the people that screen lists. It's a
  `SPECIAL_FIELDS` member in `comms_segments.py` — precomputed once per query,
  not a per-row join. Verified it partitions exactly (13 owing + 287 settled =
  300 contacts).
- **`services/roster.py::rostered_contacts`** derives a shift's date as
  `w.week_start + s.day_of_week` and backs the roster's "email everyone
  rostered" for a day/week/month, which hands off to the normal comms composer.
- **Still open, needs a decision**: file **upload** against a committee record
  (documents stay link-based by design — governance docs live where the club
  already keeps them), and any committee ↔ BetterStats Awards "Office Bearer"
  sync. Those two are unrelated things that share a name: a Clubhouse committee
  position IS a committee-flagged `club_role` (migration 198), whereas "Office
  Bearer" in Awards is an achievement category. Don't wire them together
  without asking.

## Committee document uploads + Office Bearer awards on Clubhouse roles (v9.6.0, migration 218, Aug 2026)

Two asks that both come back to "BetterStats is the core module and may be all a
club ever buys."

### Uploaded committee documents

- **`committee_documents` can now hold the file** (`file_data`/`file_name`/
  `file_mime`/`file_size`/`uploaded_by_user_id`), not only a link. `url` went
  nullable: a row carries a url **or** a file, never both. Bytes live in
  Postgres for the same reason player photos do (the upload volume is not
  guaranteed to persist). Cap is `MAX_DOCUMENT_BYTES` = 15MB and
  `ALLOWED_DOCUMENT_MIMES` is an allowlist, not a blocklist — the file comes
  back to other members from our own domain, so nothing scriptable gets in.
- **`organisations.committee_docs_office_bearer_only`** (default **TRUE**)
  decides who may open an upload. Edited from BetterClubhouse → Settings via the
  existing `/club-admin/settings` PATCH, gated on `MANAGE_SETTINGS`.
- **The rule, in `services/committee.can_open_document`**: uploader, current
  Office Bearer, or the club's **Main Admin** (`club_memberships.role ==
  'club_admin'`, unconstrained on upload/view/download/delete **per direct
  instruction**). It **only governs uploads** — a link is a URL we neither host
  nor can gate, and pretending otherwise would be false assurance. Say that in
  any UI copy rather than implying a wall that is not there.
- **Enforcement is `GET /documents/{id}/file`**, which re-checks before serving
  and sends `Cache-Control: private, no-store`. The list's `can_open` flag is
  presentation only (it draws the lock). PATCH/DELETE route through
  `_document_writable_or_403` — being able to destroy a file you may not read is
  not a lesser permission than reading it.
- **`file_data` is deferred on the list query** (`options(defer(...))`) and
  `has_file` reads `file_size`, never the bytes. Touching the deferred column
  while serialising a listed row is a `MissingGreenlet` waiting to happen, and
  without the defer a register of twenty uploads pulls every payload into memory
  to render a list of titles.
- **There is no `users` → `fee_members` FK.** `committee.member_for_user` joins
  on lowercased email, which is the only honest link; a member with no email, or
  one who logs in under a different address, simply does not resolve and is
  treated as "not an office bearer". Do not invent a stronger claim here.
- **`is_office_bearer` on a position now derives from the role's TYPE**
  (`_role_is_office_bearer`), resynced on every `sync_committee_positions`, not
  set once from the name. It gates document access now, so a role retyped in the
  Roles catalogue has to move the position with it. The name set is the fallback
  for a role with no type — dropping it would silently strip access.

### Office Bearer awards ARE BetterClubhouse roles

`services/office_bearers.py` is the whole bridge. Award **category** is fixed
("Office Bearer"), **subcategory** is a `club_role_types` row, **achievement** is
a `club_roles` row, and `player_achievements.club_role_id` records which.

- **`sync_award_definitions` runs both ways and is idempotent**, called from
  `GET /award-definitions` (wrapped in try/rollback — a club must still get its
  awards list if this hiccups). ADOPT pulls both existing definitions **and
  recorded achievements** into `club_roles`; PUBLISH pushes committee/captain/
  coach roles back out as definitions. **Adopting from definitions alone is not
  enough** — that was the first cut and it left a club's actual history behind,
  because an imported award never had a definition behind it.
- **Seeding is gated on having no ROLES, not no definitions.** A club can easily
  have one hand-typed definition and an empty role catalogue; gating on
  definitions left exactly that club with nothing.
- **`SUBCATEGORY_TO_ROLE_TYPE` / `ROLE_TYPE_TO_SUBCATEGORY`** hold the mapping
  (Executive Committee ↔ Office Bearer, General Committee ↔ Committee Member,
  Captains ↔ Captain, Coaches ↔ Coach, Other Roles ↔ Other). `PUBLISHED_ROLE_TYPES`
  keeps ground staff / canteen / officials OUT of the awards dropdown;
  `COMMITTEE_ROLE_TYPES` decides which become committee positions (a 1st XI
  Captain is an honour, not a seat).
- **`ensure_role_for_award` matches on title alone** because `club_roles` is
  unique per (org, title). An award whose subcategory disagrees with an existing
  role's type reuses the role and leaves the type alone — the Roles screen owns
  types, and a stray award must not retype a position the committee set up.
- **Starter pack grew to 18 committee roles**: the three portfolio Vice
  Presidents and Operations were added so BetterStats' long-standing Office
  Bearer options land on real roles. `STARTER_ROLE_TYPES` gained **Captain**.
  The seed button label is hardcoded — it reads `(18)` now.
- **`adopt_awards_as_terms`** turns recorded awards into `committee_terms`.
  Inserts directly rather than through `start_term`, which auto-closes the open
  term for a position — right for a real handover, wrong when back-filling a
  decade in arbitrary order. Idempotent on (position, holder, start date). Season
  → date is Jul 1 of the start year to Jun 30 after the end year; an award with
  no season is skipped, never guessed. Surfaced as a panel on the Committee
  Roles tab that only appears when the club actually has such awards.
- **`_season_year` handles both shapes** `player_achievements.season` has held:
  a `seasons` UUID (what the UI writes) and a plain label like "2025/26" (what
  imports write).

### Verification

Two suites against a real Postgres, exercising the shipped functions and the
route bodies rather than a replay of their logic (64 checks): service-level
(both sync directions, idempotency, achievement linking, term adoption, the
access rule across four identities, the deferred-bytes serialisation, role
retyping) and route-level (upload incl. MIME + size rejection, per-reader
`can_open`, the download 403, delete gating, and the unrestricted mode). The
migration was also applied twice to a populated pre-218 schema.

## BetterClubhouse is open to club admins (v9.6.1, Aug 2026)

Most of the module was invisible to the people paying for it. Directory,
Roster, Committee, Diary, Events, Facilities and the whole Setup catalogue
carried `requireRole="super_admin"` in `App.jsx` **and** a `super: true` flag in
`BetterClubhouseLayout`'s nav, so a club admin's sidebar showed only Today,
Audiences, Integrations, Reports and Settings. That gate came from
BetterClubManager being unlaunched and long outlived its reason.

- **Both halves are gone.** The routes are plain `<ProtectedRoute>`, and each
  nav item now carries the **capability its own router already enforces**
  (Roster → `MANAGE_VOLUNTEERS`, Committee/Events → `MANAGE_COMMITTEE`,
  Facilities → `MANAGE_ASSETS`, Diary → `MANAGE_CLUB_DIARY`, Directory and
  Areas & roles → the same any-of sets their routers use).
- **Safe because the server never relied on the route gate.** Every router
  behind these screens has `require_cap` / `require_any_cap` (verified across
  all eleven before removing anything). `club_admin` and `super_admin` imply
  every capability; a `club_member` gets their explicit allowlist, so the
  sidebar and the API now agree instead of the UI being the only check.
- **`/admin/member-portal` stays super-admin-only** — a genuinely unlaunched
  feature behind its own flag, not part of the merged module's nav.
- **When adding a Clubhouse screen**, give the nav item the same capability its
  router enforces. Do not reach for a role gate: role is not how this app
  expresses permission anywhere else in the module.

## The meeting room — running a committee meeting (v9.7.0, migration 220, Aug 2026)

The tabbed Committee screen is a set of lists (meetings here, motions there,
actions elsewhere). That is fine for looking something up afterwards and useless
at 8pm on a Tuesday. `pages/admin/MeetingRoom.jsx` at
**`/admin/clubhouse/committee/meeting/:meetingId`** is the screen a secretary
runs a meeting from, reached from OPEN MEETING on each row of the meetings list.

- **The agenda is the spine.** Click an item to open it; the motions, actions
  and outcome notes you record attach to that item. Ordering is HTML5 drag on
  `meeting_agenda_items.position` (which already existed) via
  `POST .../agenda-items/reorder`. `reorder_agenda_items` **ignores ids that do
  not belong to the meeting** — the list comes from a browser.
- **Attendance starts from the committee, not the membership.**
  `meeting_attendee_pool` returns everyone but flags and sorts current
  committee-term holders first; the screen shows only those (plus anyone
  already marked) until you type. A 300-member club was the whole problem.
- **Only people marked present can vote or be given an action.** `present` is
  derived on the screen from attendance, so setting attendance first is what
  makes the rest usable. This is a UI restriction, not a server rule —
  `set_motion_votes` still accepts any member, because a phone vote is real.
- **Migration 220** (mirrored in the lifespan): `committee_tasks.agenda_item_id`,
  `committee_task_assignees` (task ↔ member), `meeting_motions.position`,
  `committee_meetings.private_notes`. **NOTE the numbering** — AFL shipped its
  own `219`, and this file was briefly `219` too before being renumbered; two
  migrations with the same `revision` break Alembic outright.
- **`assigned_to_member_id` stays the primary owner.** `set_task_assignees`
  writes the join table AND sets that column to the first id, because the board,
  the timeline and every existing report read it. Never drop it in favour of the
  table alone. `load_task_assignees` falls back to it for pre-220 actions.
- **`GET .../meetings/{id}/room`** is one fetch for the whole screen (meeting,
  agenda, motions with votes, actions, attendance, attendee pool). A secretary
  mid-meeting should not wait on six requests.
- **Everything saves as it happens** — no Save button for the meeting. Free text
  (minutes, private notes, outcome notes) goes through a 700ms debounce
  (`useAutosave`); everything else writes on the click that made it.
- **A completed meeting opens the same screen**, which is how past minutes,
  motions and actions are read. Nothing is read-only: minutes are usually
  finished after the room empties.
- **Motions drag two ways** (v9.7.2). One `drag` ref carries a `kind` of
  `'item' | 'motion'`, because an agenda row is a drop target for both: drop an
  item on it to reorder the agenda, drop a motion on it to move that motion
  under that heading. Dropping a motion on another motion reorders within the
  item. **Motions are ordered across the whole MEETING but dragged within an
  item**, so `motionOrderAfter` splices the within-item move back into the
  meeting-wide sequence before sending it — reordering under one heading would
  otherwise scramble every other. The motion handle's `onDragStart` calls
  `stopPropagation`, or grabbing it would drag the whole agenda card.
- **Attendance carries over** (v9.7.2). `previous_meeting_attendance` walks back
  up to 10 meetings **of the same type** and returns the first that actually
  recorded someone present, so a meeting where only apologies were logged is
  skipped rather than carried as an empty list. Only `present` comes across: an
  apology is about one evening, and carrying it forward asserts something nobody
  said. The button only shows while attendance is empty, so it can never
  overwrite a list someone has started.

## Multi-sport: the AFL silo (Aug 2026)

**One codebase, per-sport operational silos.** BetterStats now also serves AFL
(BetterFootball, betterat.football) from THIS repo — separate docker services
(`bs-afl-frontend` / `bs-afl-backend` / `bs-afl-database`), separate database,
same source. Full architecture + product decisions:
**`docs/afl-betterstats-plan.md`**; the PlayHQ AFL API investigation behind it:
**`docs/afl-playhq-data-source.md`**. Key facts:

- **Backend**: `app/afl_main.py` is the AFL entrypoint (`uvicorn
  app.afl_main:app`, env `SPORT=afl` + its own `DATABASE_URL`) — cricket's
  `app/main.py` is untouched and must stay that way. AFL reuses the shared
  models (organisations/users/auth/seasons/grades/games/players/sync_runs) and
  the whole `routers/auth.py` stack; AFL-specific code lives in
  `models/afl.py`, `services/afl/`, `routers/afl/`. The AFL DB is created by
  `create_all` on first boot (cricket tables exist empty there by design).
- **Identity**: every AFL synced row's PK is `uuid5(org, playhq_id)` from day
  one (org itself `uuid5(AFL_NS, org_code)`) — the cricket shared-GUID
  collision saga cannot recur. Raw PlayHQ ids live in
  `grassroots_id`/`playhq_id` columns and are what API calls use. Players key
  on the PlayHQ *profile* id (stable per person), not participant id.
- **PlayHQ AFL API**: two public unauthenticated GraphQL endpoints —
  `api.playhq.com/graphql` (header `tenant: afl`, lowercase) and
  `spectator.playhq.com/graphql` (header `X-PHQ-Tenant: afl`) for
  play-by-play. GraphQL rejects unused variables (a trimmed query that keeps
  a var declaration 400s every call). Old games (pre-~2024) legitimately
  return "not electronically scored" from the spectator API — empty events
  are a normal state.
- **`afl_game_details.synced_at` is the incremental-sync signal** (NULL =
  discovered, stats not yet pulled) — it must never get a server default.
- **Frontend**: one app, sport picked at build time — `VITE_SPORT=afl` mounts
  `src/afl/AflApp.jsx` (App.jsx early-returns it; cricket bundle unchanged).
  AFL pages reuse the shared theme tokens/contexts/components. Dockerfile
  args: `VITE_SPORT=afl` + `VITE_BASE=/afl/` + `NGINX_CONF=nginx.afl.conf` +
  `WEB_ROOT=.../html/afl` (nginx proxies /afl/api to
  `bs-afl-backend` — never the cricket backend).
- **Stats model (pass 1, per product decision)**: games played, goals,
  behinds, Best on Ground (flat count; per-game ranking stored for future
  weighted views), quarter scores + play-by-play per game. No StatLab, no
  Yearbook, no Website module for AFL. Season aggregates are OUR rollup from
  per-game lines (`afl_player_season_stats`, recomputed every sync).
- **Ops**: service definitions to merge into the central compose file:
  `ops/afl/docker-compose.afl.yml`. First admin + club:
  `python -m app.scripts.afl_bootstrap <playhq_org_id> <user> '<pw>' --sync`.
  Test club: Curtin Uni Wesley, PlayHQ org code `d14445c4`.
- **Next passes (agreed direction)**: public self-serve registration wired to
  betterat.football; weekly sync scheduler; BetterSelect AFL (drag-and-drop
  field whiteboard — FF/HF/C/HB/FB + Followers, 12–18 on field, up to 20
  bench); then the other modules, each with an AFL review before enabling.

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

## Writing Voice — always run prose through the humanizer

Any user-facing prose you write or edit (marketing copy, changelog entries, UI
strings, docs, PR/commit bodies, longer chat replies) must go through the
**`humanizer`** skill before it ships — it's vendored at
`.claude/skills/humanizer/` so it's available in every web session. Apply its
rules even when you don't invoke the skill explicitly: no em/en dashes, no
forced rule-of-three triads, no promotional "AI vocabulary" (vibrant, seamless,
testament, elevate…), no tailing negations ("no guessing", "no fuss"), plain
`is`/`are`/`has` over "serves as"/"boasts". Keep the plain Australian
cricket-club voice. Page-`<title>` separators use the site-wide `—` convention
(structural, not prose) and are the one allowed exception.

## Server Deploy Command

The box runs **all ~26 containers as ONE systemd-managed compose project, `bltbox_docker_app`** (`/etc/systemd/system/docker-compose-app.service`: `WorkingDirectory=/srv/docker`, `Environment="COMPOSE_PROJECT_NAME=bltbox_docker_app"`, `ExecStart=docker compose up -d`). BetterStats is defined inside the **central** file `/srv/docker/docker-compose.yaml` (NOT the retired `/srv/docker/betterstats/docker-compose.yml`).

**Deploy by running the committed script — `/srv/docker/betterstats/deploy.sh`.** Long form:

```bash
cd /srv/docker
export COMPOSE_PROJECT_NAME=bltbox_docker_app   # ← LOAD-BEARING (see post-mortem below)
git -C /srv/docker/betterstats pull origin main
docker compose build --no-cache betterstats-frontend betterstats-backend
docker compose up -d --no-deps --force-recreate betterstats-frontend betterstats-backend
```

- **`COMPOSE_PROJECT_NAME=bltbox_docker_app` is mandatory.** Without it, `docker compose` from `/srv/docker` defaults to project `docker` (the directory name) → a *second* betterstats stack on a *separate, empty* pgdata volume that steals the `betterstats-*` container names. **This caused the June 2026 outage (post-mortem below).**
- Run from `/srv/docker` so `.env` (secrets) + the override file load — matches how systemd runs it. Don't pass `-f` (it skips the override and drifts the config hash).
- `--no-deps` + naming only the two services ⇒ the database (`betterstats-db`) and the other ~24 apps on the box are never touched. **Never recreate `betterstats-db`** — the data lives in the `bltbox_docker_app_betterstats_pgdata` volume.
- `--no-cache` on the build avoids stale Docker layer cache.
- **Operate containers ONLY via `docker compose …` (from `/srv/docker`, with `COMPOSE_PROJECT_NAME` set) — never bare `docker run/restart/exec/ps`.** Bare `docker` commands fall outside the pinned project and spawn/leave duplicate stacks/containers that are a nightmare to tell apart (same root cause as the project-split outage below). To act on another app on the box (e.g. nginx-proxy-manager), discover its compose **service** name (`docker compose ps --services`) and use `docker compose exec/restart <service>` — don't hardcode a container name or shell out to `docker <verb>`.
- Ignore `POSTGRES_PASSWORD` / `LANGFLOW_*` "not set" warnings (other services' vars). **NEVER add `--remove-orphans`** — it would delete `klubpro-mongo` / `restreamer` (other people's apps).
- nginx-proxy-manager routes `betterstats.cricket` → `betterstats-frontend` on `docker-shared-net` (apex is canonical; `www.betterstats.cricket` 301-redirects to it). The frontend `nginx.conf` MUST proxy `/api` to **`betterstats-backend`** — never the bare `backend`, which on the shared network resolves to a *different app's* API (that was bug #2 below).

## June 2026 Production Outage — Post-Mortem (compose project split)

**Symptom**: `betterstats.cricket` 502'd, then returned showing a months-old marketing page with **every club page blank** (`/applecross` empty). Looked like total data loss.

**Nothing was actually lost** — three independent problems had stacked up:

1. **Compose project split → wrong (empty) data volume.** All ~26 containers run as systemd project `bltbox_docker_app`, but betterstats had *also* been deployed as an ad-hoc project `docker` (what you get running `docker compose` from `/srv/docker` WITHOUT `COMPOSE_PROJECT_NAME`). The real 370 MB database lived in the `docker` project's volume (`docker_betterstats_pgdata`); when the systemd stack (re)started, *its* betterstats came up on the empty `bltbox_docker_app_betterstats_pgdata` and — `container_name:` being hardcoded/global — stole the `betterstats-*` names. Result: site up, zero data. *Fix*: clone the real volume into the one the live stack uses —
   `docker run --rm -v docker_betterstats_pgdata:/from:ro -v bltbox_docker_app_betterstats_pgdata:/to postgres:15 bash -c 'find /to -mindepth 1 -delete; cp -a /from/. /to/; rm -f /to/postmaster.pid'`
2. **Crossed `/api` proxy → answered by a DIFFERENT app.** The deployed frontend's `nginx.conf` proxied `/api` to the bare host `backend`, which on `docker-shared-net` resolves to *another app's* API (ProLog). Every cricket data call got someone else's 404s → blank pages. The repo's current `nginx.conf` correctly uses `betterstats-backend`; the running image just predated that fix.
3. **Stale image / version mismatch.** That old frontend/backend pair predated the `/clubs/{slug}` endpoint, so club pages 404'd even after the proxy fix. Deploying current code (matched pair) fixed it.

**Root trigger**: a deploy/restart run WITHOUT `COMPOSE_PROJECT_NAME=bltbox_docker_app`, which forked a second betterstats project. **Prevention**: always deploy via `deploy.sh` (project name pinned). **If it recurs, diagnose in this order**:
1. `docker compose ls -a` — are there TWO projects with betterstats? (`docker` vs `bltbox_docker_app`)
2. `docker volume ls | grep pgdata`, then `docker run --rm -v <vol>:/v postgres:15 du -sh /v` — which pgdata volume holds the data (the big one)?
3. `curl -s https://betterstats.cricket/api/openapi.json | head` — is `/api` answered by **"BetterStats API"** (title) or a different app?
4. `docker exec betterstats-frontend grep -rn proxy_pass /etc/nginx/` — does `/api` point at `betterstats-backend`?

## June 2026 Admin Outage #2 — Post-Mortem (NPM can't resolve betterstats-frontend)

**Symptom**: `/admin` died with **"Failed to fetch dynamically imported module: …/assets/AdminDashboard-H0O_EwuY.js"** and an intermittent 502 on that chunk. Looked like a stale/corrupt asset or poisoned cache — it was **neither**.

**Root cause**: after `betterstats-frontend` was recreated (a deploy, then a manual `--force-recreate`), it got a **new Docker IP**, and **nginx-proxy-manager could not reliably DNS-resolve the `betterstats-frontend` name** — error log: `betterstats-frontend could not be resolved (2: Server failure)` (a DNS SERVFAIL) for `server: betterstats.cricket`. NPM resolves the upstream **per worker** at request time, so some workers had a good resolution (→ 200) and some a cached SERVFAIL (→ 502). That per-worker split is why it looked like **one specific file/URL**: `?v=2`, `/api/openapi.json` and most assets happened to hit "good" workers, while the bare admin chunk kept hitting a "bad" one. The file was fine all along.

**Misleading signals that wasted time (don't repeat the chase)**:
- `?v=2` on the chunk → 200, bare URL → 502. *Looked* like a URL-keyed cache; was actually per-worker DNS luck.
- The file on disk in the container was byte-perfect (`sha256` matched a clean local build) and served **200 directly** (`docker compose exec betterstats-frontend wget -qO- localhost/assets/<chunk>`), proving the origin was healthy.
- There was **no cached object** for the asset in any NPM cache zone — purging did nothing. Not a cache bug.

**The tell is in the NPM error logs, not the app logs**: `docker compose exec <npm-service> sh -c 'grep -RhiE "could not be resolved|betterstats-frontend" /data/logs/*error*.log | tail'`. The per-host access log also lives in `/data/logs/proxy-host-*_access.log` (`[Sent-to betterstats-frontend]`).

**Fix (what actually worked)**: restart NPM so all workers re-resolve the frontend's current IP. **Do it the compose way** (bare `docker` is banned — see deploy rules): discover the proxy service then
`docker compose restart "$(docker compose ps --services | grep -iE 'proxy|npm|manager' | head -1)"`. A graceful `nginx -s reload` was tried first and did **NOT** clear it during the incident — a full restart was required.

**Prevention (shipped)**: `deploy.sh` now has a `[4/4]` step that, after recreating the frontend, reloads NPM, health-checks `https://betterstats.cricket/` 3×, and restarts the proxy service only if any check is non-200 — so every deploy self-heals this. The frontend also reloads once on a chunk-load failure (`vite:preloadError` in `main.jsx` + chunk-aware `ErrorBoundary`), turning a transient 502/stale-chunk into a silent retry instead of the "Something went wrong" dead-end.

**If it recurs**: 1) NPM error log for `could not be resolved`; 2) confirm the two containers still share a network (`docker compose exec <npm> getent hosts betterstats-frontend`); 3) if the name resolves from NPM but the site still 502s, it's stale per-worker resolver state → restart the proxy **service** via `docker compose restart`.

## Public Domain

The canonical public domain is **`https://betterat.cricket`** (no `www`), the **BetterCricket** brand. The brand name is written **as one word, "BetterCricket"** (Jun 2026 — was the two-word "Better Cricket"); keep it one word in all user-facing copy, page titles, OG/social cards, metadata and the `BRAND` constant in `frontend/src/data/marketing.js`. The module names stay camelCase (BetterStats, BetterSelect, BetterSocials, BetterAdmin, BetterIQ — **BetterStats remains the Core module name**), and the trading company stays **BetterSports**. A permanent redirect from the old `betterstats.cricket` to `betterat.cricket` (301 for GET/HEAD, 308 otherwise) is **prepared in `cloudflare-worker/worker.js` but not yet deployed**; once it ships it consolidates the old domain's link equity onto the canonical. Until then both hostnames serve the same app, so links work on either. The older `betterstats.bltbox.com` domain is retired.

- **Everything public points at `betterat.cricket`** (keep new public-URL references there): `frontend/src/hooks/usePageMeta.js` (`BASE_URL`), `frontend/index.html` (`og:url`, canonical, JSON-LD), `frontend/public/{llms.txt,robots.txt,sitemap.xml,site.webmanifest}`, the backend `routers/seo.py` (`SITE`, the live sitemap + robots nginx proxies), `routers/og_preview.py` (`SITE`), `config/settings.py` (`public_base_url`, the email unsubscribe link), the `deploy.sh` health check, and the `tools/sync_watch.py` default base.
- **Email — one address everywhere: `support@bettersports.com.au`** (Jul 2026, was `cricket@bettersports.com.au`; before that a `noreply@betterstats.cricket` From plus a `betteratcricket@gmail.com` reply-to/contact). It's the default reply-to (`config/settings.py` `email_reply_to`, from-name "BetterCricket" — `email_from_address` is a separate deliverability-only sending address, currently `notifications@betteratcricket-comms.work`) AND the public contact address shown across the site: `SUPPORT_EMAIL` in `frontend/src/data/marketing.js`, the hardcoded copies in `frontend/index.html` (JSON-LD), `frontend/public/llms.txt`, `backend/app/routers/og_preview.py`, `backend/app/routers/self_serve_trial.py`, and the marketing/login pages (Privacy, Terms, Contact, FAQ, Login, MarketingFooter). **DNS still to do**: for sent mail to pass authentication, `bettersports.com.au` needs SPF/DKIM/DMARC set up (the records used to live on `betterstats.cricket`); until then sent mail may be flagged as spam. `email_provider` defaults to `console`, so nothing sends until a provider is configured anyway.
- `CORS_ORIGINS` should be `https://betterat.cricket` in the server `.env`, but CORS is dormant in practice: the frontend calls the API via a same-origin relative `/api` path, so cross-origin checks never fire. Updating it is hygiene, not a functional requirement.
- `betterat.cricket` social link-preview cards are server-rendered for the marketing routes by `backend/app/routers/og_preview.py` (`MARKETING_PAGES`), so per-page OG tags work for crawlers that do not run JS; keep that map in sync when marketing routes change.
- `cloudflare-worker/worker.js` is a pure old-domain redirect, **ready but not yet deployed** (its old OG-injection job is handled by `og_preview`). When ready, `wrangler deploy` it and keep the Cloudflare route `betterstats.cricket/*` active.

## Blog post social-share cards (Jun 2026)

Each blog post (`/blog/{slug}`) gets its own social-share card from
`backend/app/routers/og_preview.py` (`_blog_html`): the post's own hero image,
title and description, `og:type=article`, and BlogPosting + Breadcrumb JSON-LD
that mirrors `frontend/src/pages/marketing/BlogPost.jsx`. Before this, a shared
post fell through to the generic homepage card, because the SPA's client-side
`usePageMeta` tags never reach Facebook/LinkedIn crawlers (they read raw HTML,
not rendered JS).

The backend's blog metadata is in one place, `backend/app/content/blog.py`
(`BLOG_POSTS`: slug, title, description, image, date). Both `og_preview.py` (the
card) and `routers/seo.py` (the sitemap, via `BLOG_SLUGS`) read it, so the old
hand-kept slug list in `seo.py` is gone.

**Adding a future post** is three steps that have to stay in sync:
1. Drop the hero image in `frontend/public/marketing/blog/` (1920x1080 reads
   well as a `summary_large_image` card).
2. Add the full post to `frontend/src/data/blog.js` (the article body and the
   in-app meta).
3. Add a matching row to `backend/app/content/blog.py`, copying the
   title/description/image/date straight from `blog.js` so the card matches the
   page.

After deploy, re-scrape an already-shared link in Facebook's Sharing Debugger
(and LinkedIn's Post Inspector) to clear their cached copy of the old card.

## Marketing Contact form → club onboarding requests (Jun 2026)

The public Contact page (`betterat.cricket/contact`,
`frontend/src/pages/marketing/Contact.jsx`) still emails enquiries via Formspree,
and now also stores each one in BetterStats so staff can track onboarding. On
submit the form fires a best-effort `POST /api/public/contact` (api
`submitOnboarding`) alongside the Formspree post. Formspree stays the primary
delivery and drives the success/error UI, so a failed store never blocks the form.

- **Table** `club_onboarding_requests` (migration 079, mirrored idempotently in the
  `main.py` lifespan): name / club / email / phone / association / grades / storage /
  timeline / club_url / message, plus `status` (new | contacted | onboarded | closed),
  source, user_agent, created_at. No `organisation_id` (the sender is a prospect, not
  a member).
- **Public router** `routers/public_contact.py` (`POST /public/contact`,
  unauthenticated, NOT module-gated): validates name/club/email, clips every field,
  stores one row.
- **Super-admin UI** `/admin/super/onboarding` (`pages/admin/SuperOnboarding.jsx`,
  `requireRole="super_admin"`, linked from AdminLayout `SUPER_LINKS`): lists requests
  newest-first, filter by status, change a row's status. Backed by `GET` + `PATCH
  /club-admin/super/onboarding-requests` in `club_admin.py`.
- **Deploy note**: the store assumes `betterat.cricket` routes `/api` to
  `betterstats-backend` the same way `betterstats.cricket` does (same frontend
  container + nginx `/api` proxy). If the marketing domain is ever served separately
  without that proxy, point the form at the absolute backend URL instead. It degrades
  gracefully meanwhile, since Formspree still delivers the email.

### Club name is a search, not a text box (migration 224, v9.12.2, Aug 2026)

The Club name field asked a person under time pressure to spell their club, and
every downstream match then had to work back from that string — so "Applecross
CC" and "Applecross Cricket Club" became two prospect rows. It now searches the
same Cricket Australia club list the self-serve trial wizard searches, and a
picked club carries its real CA organisation guid through with the enquiry.

- **`GET /public/contact/club-search`** reuses `self_serve_trial.search_clubs`
  (one club list, one matching rule) but is deliberately **NOT** routed through
  `/public/self-serve`: that whole router sits behind the
  `self_serve_registration_enabled` platform flag, and the Contact form has to
  keep working whether or not self-serve registration is switched on. Rate-limited
  per IP (120/hour) like its sibling, since every keystroke reaches CA's API.
  The response is **projected down** — the self-serve search also returns the
  registered club's public slug and its Primary Admin's first name + last initial
  (for the "talk to your admin" card), and a marketing page has no business
  serving either. `already_registered` is kept and shown, but never blocks: an
  already-registered club is still entitled to get in touch.
- **`club_onboarding_requests.club_org_id` + `.club_source`** ('search' |
  'manual'). A guid is only ever stored alongside `club_source='search'` — a
  typed name has nothing to key on, and letting a manual row carry an id would
  put a guessed identity on the record. An unrecognised `clubSource` drops both.
- **`_resolve_onboarding_club` (twenty_sync) takes `org_id`** and checks it
  **after** the submitter's email but **before** the name, so the established
  email-first priority `_onboarding_signal` shares is untouched. A new row is
  created on the REAL guid — the same one the PlayHQ crawler uses — so a row
  created by an enquiry and a row the crawler finds later are one row.
  `crm.sync_deal_for_enquiry` takes and forwards the same `org_id`, so the local
  pipeline and the Twenty push can't resolve different clubs.
- **A `manual:` guid is upgraded once the real one is known**, but only when no
  other row already holds it. `grassroots_guid` is unique, so the check is also
  what stops a background task raising; and two rows for one club is a merge
  decision for a person, not a silent write.
- **The typed name stays, on purpose.** The CA list only covers Australia, so
  "can't find your club" hands back a plain text field rather than a dead end —
  that is what keeps a club in England or New Zealand able to reach us.
- **`frontend/src/components/marketing/ClubSearchField.jsx`** holds one
  invariant worth keeping: **`club` is only ever set once `clubSource` is**, so a
  half-typed search term is the field's own local state and the form's existing
  "Club name is required" check blocks a search nobody finished. A `?club=` link
  (`ClubInactive.jsx`) seeds the search rather than answering it.
- **Verified** against a real Postgres (25 checks — the resolution priority, the
  guid upgrade and its collision guard, the migration applied twice to a
  populated pre-224 table, the route bodies incl. a junk `clubSource` and the
  short CTA form's unchanged bare post, and the original bug reproduced: two
  spellings made two clubs, now make one) and driven in a browser (search,
  keyboard pick, submitted payload, the no-results fallback, validation blocking
  an unfinished search, `?club=` seeding, no mobile overflow).
- **Not done**: the short "Get your club on BetterCricket" CTA modal
  (`QuickEnquiryModal`) still posts a free-text club name to the same endpoint —
  the backend fields are optional so it is unaffected, and it is the obvious next
  place to reuse `ClubSearchField`.

## Public Marketing Pricing — modular model (Jun 2026)

The **public** marketing pricing and the in-app entitlement model are both
**modular** now (the Good/Better/Best tiers were retired, see "Modular
entitlements" below). The public price model is still kept separate from the
entitlement registry (`frontend/src/lib/modules.js`) so marketing copy and
gating logic move independently. Public model: **Core (BetterStats) $399/yr**
plus modules **BetterSelect / BetterSocials / BetterAdmin $149 each** and
**BetterIQ $249**, an **annual licence only** (no monthly). Bundle discount is a
**set dollar amount** keyed on module count (2 modules save $48, 3 save $97, all
4 save $146), so Core + all four = **$949** (see `BUNDLE_DISCOUNT` in
`pricing.js`).

- **Source of truth**: `frontend/src/data/pricing.js` (`CORE`, `PRICED_MODULES`,
  `priceFor`, `ALL_IN`, `COMPETITOR_STACK`, `COMPETITOR_TOTAL`). Edit prices here.
- **Pricing page** (`pages/marketing/Pricing.jsx`) is **calculator-first**: the
  `PricingCalculator` (module picker, live annual total with the bundle discount)
  is the main tool, plus a module price list, a **competitor cost comparison**
  ("One platform. One price.": the all-in BC price vs a stack of real competitors
  with their own published prices, ClubStats / Pitchero / Canva, summed with the
  `SAVING` highlighted; CricketStatz noted; Better Cricket includes historical
  import where ClubStats charges a one-off fee, `IMPORT_NOTE`) and a modular
  pricing FAQ. All competitor figures live in `pricing.js`.
- **Monthly removed** from the public site (Pricing toggle, Overview snapshot,
  Landing/Features price lines, Terms clause, a blog callout). The dormant
  monthly toggle in `ComparisonTable` was left (no caller enables it). The in-app
  `BILLING_CYCLES` constant remains (a super admin can still record a club's
  billing cycle); `TIER_INFO` and the whole tier model were removed (below).

## Modular entitlements — tiers retired (v8.12, Jun 2026)

The Good/Better/Best plan tiers are **retired and not returning.** A club's
`module_overrides` (the explicit list of module keys it holds) is now the
**single source of truth** for entitlement, gated only by `subscription_status`
(`backend/app/auth/modules.py::org_entitled_modules` = the module list while the
sub is active, else Core only). Core (BetterStats) is always on and is never a
gateable module.

- **Migration 080** backfilled every club's `module_overrides` from its old tier
  (`best` → all 5, `better` → select+socials, `good` → none) so **no club lost
  access**. Additive and idempotent.
- `organisations.tier` is **kept but deprecated** (no longer read anywhere;
  retained for history, not dropped). Don't read it.
- **Super admins** assign a club's modules via per-module checkboxes
  (`MODULE_TOGGLES` in `lib/modules.js`; **BetterAdmin = fees + comms**) in
  `SuperClubs.jsx` — there's no tier dropdown.
- `/auth/me` + `/auth/login` no longer return `entitlements.tier` (just
  `modules`, `overrides`, `status`, `renewal_date`, `billing_cycle`). Frontend
  gating already reads `entitlements.modules` (`AuthContext.hasModule`).
- **Don't reintroduce** `TIER` / `TIER_INFO` / `TIER_ORDER` / `requiredTier` /
  `tier_modules` / `MODULE_REQUIRED_TIER` anywhere. Locked modules read as
  "add-ons", not a higher tier. (BetterFees membership/fee-schedule *tiers* are a
  different, unrelated feature — leave those.)

## Version Numbers

Each release lives in its own file under **`frontend/src/data/changelog/`** — never hand-edit `frontend/src/version.js` (it derives `SITE_VERSION` from the highest-sortKey entry in that folder). Drop a new `v-X-Y-Z.js` file when you ship:
- Small fix: `+0.0.0.1`
- Medium change: `+0.0.1`
- Large change: `+0.1`

See "Feature Changelog" below for the file format.

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

## Awards — default templates (v8.28.0, Jun 2026)

Award catalogue lives in two tables (created in `main.py` lifespan, not Alembic):
`org_award_definitions` (the per-club catalogue that drives the dropdowns; clubs
rename via `display_name`, hide via `active`) and `player_achievements` (the
records). Templates are built in `backend/app/routers/award_definitions.py`:

- **`STARTER_TEMPLATE`** (`_build_starter_template`) — the **default for new
  clubs**, ~55 rows, club-agnostic: whole-club Season awards, a 1st/2nd/3rd XI
  block, generic `Premiership › Team`, the universal Milestone ladders, a
  `Committee` role list, Hall of Fame + Life Membership. No WASTCA/WABCC/PSWL,
  no OD/ICL/Colts ladder.
- **`GLOBAL_TEMPLATE`** (`_build_global_template`) — the old ~450-row
  comprehensive WA list. Kept as the opt-in **'comprehensive'** preset only.
- **`APPLECROSS_TEMPLATE`** — ACC's exact trophy names, matching their existing
  `player_achievements` values. Seeded for slug `applecross` on startup; not in
  the picker.
- `/award-definitions/seed?template=` reads the `TEMPLATES` map
  (`starter`|`comprehensive`|`global`(alias)|`applecross`); unknown → starter.
  Frontend auto-seeds **`starter`** on first visit to the definitions page when a
  club has zero defs, and the "Reset to Template" control offers Starter vs
  Comprehensive.

Seeding only fills an **empty** org (`seed_org_definitions` is a no-op if any def
exists), so Applecross and any already-seeded club are never touched. The
hardcoded `ACHIEVEMENT_TREE` in `frontend/src/lib/achievementOptions.js` (+ its
Python mirror in `routers/achievements.py`, used by the CSV import template) is
still the ACC-flavoured deep fallback shown only when an org has no defs at all —
a leaner import template is a possible follow-up, not done here.

## Branch

Active development branch: `claude/fix-historical-game-data-QEN3b`
Push to this branch AND to `main` via MCP after each change.

## Architecture

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (`backend/`)
- **Frontend**: React + Vite + Tailwind CSS (`frontend/`)
- **API**: Grassroots API proxy (`grassrootsapiproxy.cricket.com.au`) — season-aggregate stats freely accessible; game-level paths exist but the proxy's upstream API key is restricted
- `jsconfig=eccn:true` is a ServiceStack formatting flag, NOT an API key

## Data Source Topology (May 2026 investigation)

Cricket Australia hosts club cricket data across **two separate backends**, both reached via `play.cricket.com.au`:

1. **PlayHQ** (post-migration, ~2023+): GUID-keyed. Reachable via:
   - Partner REST API `api.playhq.com/v1/...` — public key only returns ~3 seasons (Summer 23/24, 24/25, 25/26). `/teams` is 401 with public key. `/grades` (org-level) is 404. `/v2/games/{id}/summary` works for IDs in this universe.
   - Public GraphQL `api.playhq.com/graphql` — `discoverGame` works for current games, `discoverGradeFixture` and `discoverTeamFixture` 500 with "Bolt adapter map not found" (require session/cookie auth the website holds). Schema introspection disabled.

2. **MyCricket / Pulselive Play Community** (legacy / pre-migration): GUID-keyed throughout (different namespace from PlayHQ). Data confirmed to reach back to at least 1975. Reachable via the same `grassrootsapiproxy.cricket.com.au` host we already use — just on a different path prefix than the proxy's restricted endpoints:
   - **`/scores/grades/{grade_id}/matches`** — all matches in a grade. ✓ unauthenticated. **Primary match discovery path** — grade_id is the same UUID as `grades.id` in our DB, works for all seasons including pre-2000. Confirmed 200 OK for a 1996 Applecross 8th Grade game.
   - **`/scores/teams/{team_id}/matches`** — list of matches a team played that season. ✓ unauthenticated. Secondary/fallback; team IDs require a fixturesladders call first.
   - **`/scores/matches/{match_id}?responseModifier=includeScorecard`** — full scorecard (batting, bowling, fielding, fall-of-wickets). ✓ unauthenticated. Returns **HTTP 204 No Content** for post-migration PlayHQ-namespace IDs, which is a clean "not mine" signal.
   - **`/fixturesladders/grades/{grade_id}/ladders`** — grade ladder (win/loss/points standings). ✓ unauthenticated 200 OK. Useful for future ladder feature — not yet synced.
   - **`/fixturesladders/grades/{grade_id}`** — grade metadata. ✓ unauthenticated 200 OK.
   - `participantId` in the response **is the same GUID as `players.id` in our DB** — no extra mapping needed.
   - The restricted paths (`/fixturesladders/games/{id}`, `/participants/games/{id}/batting`, `/scorecards/...`) all return `403 "API key does not have access"`. **Don't try those.** The `/scores/*` path is the one that works.
   - `apiv2.cricket.com.au` — has Swagger UI at `/`, OpenAPI at `/openapi.json`. Looks promising at first glance but is the **international** stats API (Ashes, BBL, Sheffield Shield) — does NOT contain club cricket data. Skip.
   - `api.playcommunity.pulselive.com` — verified `/registration` only; broader scope unknown.
   - `crm-communitycricket-cdn.cricket.com.au` — referenced by the bundle, scope unknown.

   **How to find the real API call**: the play.cricket.com.au website is a CSR Pulselive SPA (`window.API_ACCOUNT = 'playcommunity'`, bundle at `/resources/playcricket/v1.28.6/scripts/bundle-es.min.js`). HTML is just a shell. Anonymous server-side curls of `ca.playhq.com/*` and JS bundles get 403'd. Network-tab the request from a real browser load to recover the URL — that's how we found `/scores/*`.

3. **Pagination quirk**: PlayHQ's `links.next` is sometimes returned forever even when the data is exhausted (observed paginating past page 1100 on a single grade). Our pagination loops cap at MAX_PAGES=200 and stop on the first short batch — never trust `links.next` alone.

4. **Org duplication trap**: `upsert_organisation` keys on whatever `id` is passed in, so calling sync with a PlayHQ UUID after the org was already created with a Grassroots GUID would create a duplicate row (one with `playhq_id=NULL` matching the other org's `id`). Detected May 2026 for Applecross, cleaned up via direct DELETE. Guarded since commit ceadd84 — layered check on (a) primary id, (b) existing org's `playhq_id` matching incoming id, (c) name match (case-insensitive) before inserting.

## UK Expansion — Play-Cricket Data Source (Jun 2026 investigation)

UK club cricket runs on **Play-Cricket** (ECB), a **server-rendered Rails** app, one subdomain per club (`{club}.play-cricket.com`). The pages carry **no client JSON** — a browser network capture shows only telemetry (New Relic `bam.nr-data.net`, GA4 `g/collect`, OneTrust consent), never data. **Don't scrape the HTML** (brittle + terms breach). Full investigation: **`docs/uk-play-cricket-data-source.md`**.

- **The data tap is the official Play-Cricket API v2**: `https://play-cricket.com/api/v2/*.json`, **token-gated per club** (`api_token` required on every call; a club admin signs an agreement → key issued). Key endpoints: `result_summary.json?site_id=&season=` (discovery + `last_updated`), `match_detail.json?match_id=` (**full scorecard, both teams**), `matches.json` (fixtures), `league_table.json?division_id=` (ladders), `players.json`/`teams.json`. Integrator pattern = poll `result_summary`, fetch `match_detail` only when `last_updated` changes — same shape as our CA grade→matches→scorecard flow.
- **NO statistics endpoints** — *"a club can access the full scorecards of their games but we do not offer endpoints for statistics."* So unlike AU (CA aggregate API → `player_season_stats`), **the UK has scorecards only and we must compute every season aggregate ourselves** (promote the "Fix Missing Totals" rollup to primary). `match_detail` maps almost 1:1 onto our tables (`games`/`grades`/`players`/`batting_innings`/`bowling_spells`/`fielding_stats`/`bowler_wickets`/`partnerships`/FOW) — see the schema map in the doc.
- **IDs are integers, not GUIDs** — slot into the existing per-club collision scheme (raw id in `grassroots_id`, `id = uuid5(org, raw_id)` on collision). **Season** is a query param, not in the payload — derive `Season.year` from `match_date` (DD/MM/YYYY).
- **Bonus data vs AU**: `match_detail` carries **toss** (`toss`/`toss_won_by_team_id`/`batted_first`) and **extras** (byes/leg-byes/wides/no-balls/penalty) — both unavailable on CA's `/scores/*`, so UK data unlocks BetterIQ toss/captaincy analysis (brief §4) and exact score reconstruction.
- **Token scope** (technical reach ≠ contractual scope): a token authenticates *you*; the `site_id`/`match_id`/`division_id` you pass picks *whose* data. Published cross-club data *appears* broadly readable (any `site_id`/`match_id` — community-reported via `pyplaycricket`, not live-tested), but you're contractually data controller for **your own club only**. **No stats endpoint for anyone** (own or other clubs — always compute from scorecards). In-scope cross-club data = the **opponent half of your own games** (`match_detail` has both teams) → full head-to-head scouting; a **full** opponent dossier (their form vs everyone) needs the opponent's token, a **league-site token** (one token → every club in the competition, via `division_id`/`cup_id`), or partner access. **Onboarding a league is the highest-leverage in-scope unit** — restores AU-like "scout anyone in the comp". Private/unpublished fields (PII, unpublished matches) presumably own-site only — unverified without a token. **REJECTED shortcut**: reusing ONE shared club key for all English clubs (token authenticates us, `site_id` picks the data) — unverified technically, breaches the host club's agreement, single point of nationwide failure, and UK-GDPR-unlawful (processing other clubs' members — incl. children — with no lawful basis). Use league/partner tokens, never a shared club key. (Doc §6.)
- **Access policy & strategy**: API is for **clubs/leagues to export their own data**; third-party commercial use needs an ECB exception ("compelling reason … well-established customer base"). The ECB's own advice is the **BYO-token model** — *"allow clubs to add in their own API tokens for their specific data while you grow"* — then approach the helpdesk at "hundreds of clubs / thousands of users." So **Phase 1 = per-club token** (add `playcricket_api_token`+`playcricket_site_id` to the org; new token-authed `playcricket_scores_client`; no ECB relationship needed), **Phase 2 = partner access** (our AU customer base is the exception lever). Not real-time / low-traffic only; minimise retained PII (UK GDPR — we'd be a processor).

## Sync Architecture

### Admin UI button names (Sync Actions card)

The three buttons on `/admin/sync` map to backend endpoints as follows. When
the user says one of the UI names, this is what they mean:

| UI button             | Backend route                                  | What it does                                                        |
|-----------------------|------------------------------------------------|---------------------------------------------------------------------|
| **Sync Now**          | `POST /organisations/{id}/sync`                | Pull latest games & stats. Safe to run anytime — the weekly job.    |
| **Fix Missing Totals**| backfill aggregates endpoint (`/club-admin/...`) | Recomputes `player_season_stats` from existing per-game rows. No CA fetch. Use when a player shows 0 matches/runs despite having scorecards. |
| **Full Rebuild**      | `POST /club-admin/hard-refresh`                | Wipes per-game tables and re-pulls everything from CA. Slow (hour+). Use after sync-logic changes. |

(Renamed Apr–May 2026; old labels were "Sync" / "Backfill Aggregates" /
"Hard Refresh". Internal endpoint names and the `kind` field on `sync_runs`
are unchanged.)

- **Full sync** (`POST /organisations/{id}/sync`) / **Hard refresh** (`POST /club-admin/hard-refresh`): scheduled weekly + on-demand. Two passes:
  1. **Grassroots aggregate** (`playhq_client.get_*_stats`) — season totals for all 52 seasons. Source of `player_season_stats`.
  2. **Grassroots scores** (`grassroots_scores_client` + `sync_grassroots_game_level_data`) — game-level scorecards confirmed back to at least 1975. Iterates grades from DB (all seasons, all grades), calls `/scores/grades/{grade_id}/matches` for each to get match IDs, fetches `/scores/matches/{id}?includeScorecard` for each. Skips PHQ-namespace IDs that 204. Per-game session pattern to avoid async session deadlock. Uses `session.get(Grade, ...)` to avoid stale-cache FK violations. No longer depends on fixturesladders for discovery, so pre-2000 seasons are fully covered.
- **PlayHQ Partner game-level sync** is **removed** from `sync_organisation` (May 2026 audit). The public API key only exposed ~3 seasons of history vs Grassroots's 50+, AND because the same physical match has different UUIDs in PHQ vs Grassroots, running both produced duplicate batting rows. `sync_game_level_data`, `_backfill_player_playhq_ids`, and `process_game_updated_webhook` were deleted from sync.py — see git history if ever needed again.
- **Per-player deep sync**: `deep_sync_player()` — admin-triggered, still present but pre-dates the Grassroots unlock. Calls PlayHQ Partner API; only covers ~3 recent seasons. Low value now that Grassroots covers everything including 25/26.
- **Sync runs persisted** in `sync_runs` table (migration 005). `update_sync_run` and `finish_sync_run` MERGE stats into the existing row (don't replace) so sub-phases accumulate. Stale `running` rows are marked `error` on backend startup.
- **`owns_run` gotcha**: inside `sync_organisation`, `owns_run = run_id is None`. So when a caller passes `run_id` (e.g. the hard-refresh handler that calls `start_sync_run` itself), sync_organisation only ever calls `update_sync_run` on success and NEVER `finish_sync_run`. The **caller** is responsible for finishing the run. The hard-refresh handler (`club_admin.py:_run`) used to only call `finish_sync_run` in the exception branch, so every successful hard-refresh sat at `running` forever — fixed May 2026.
- **Merge-aware GR sync** (May 2026, v3.0.2): `sync_grassroots_game_level_data` now builds a `merged_away: removed_player_id → keep_player_id` map from `merge_logs WHERE undone_at IS NULL` (with transitive resolution) during discovery. Each of the five `participantId` consumers (batting, bowling, fielding, fall-of-wickets, derived partnerships) checks `known_player_ids` first and falls back to `merged_away` before skipping. Without this, scorecards referencing a previously-merged player_id silently dropped those stats, leaving the kept player short on innings/wickets/catches/fall-of-wickets.
- **Aggregate-sync merge map** (v3.0.2.1) was previously NOT filtering `merge_logs` by `undone_at IS NULL` AND was building only a single-hop redirect dict. Two consequences:
  1. Stale entries (e.g. a merge that was reversed by a later re-merge in the opposite direction) poisoned the map — observed for Cooper Jnr (`92F`) where a 04:59 merge `KEEP=09c REMOVED=92F` redirected his aggregate stats to `09c` (which no longer exists), silently dropping every season except those keyed under a different ID that resolved cleanly. Symptom: per-game `batting_innings` correct (different sync path), but `player_season_stats` summary showed only 3 seasons.
  2. Multi-step merges (A→B→C) would redirect A to B only; if B was later merged away, the insert hit the safety net and got dropped.
  Fix: filter by `undone_at IS NULL` and resolve transitively with cycle break — same pattern as the GR sync function. Manual cleanup also needed for already-poisoned rows: `UPDATE merge_logs SET undone_at = NOW() WHERE undone_at IS NULL AND removed_player_id IN (SELECT id FROM players)` to mark entries where the "removed" player is back in the players table.
- **"Absent" / "DNB" dismissals aren't innings** (v3.0.2.2): GR scorecards mark a batter "Absent" or "Did Not Bat" with `dismissalTypeId > 0` but no ball faced. CA's aggregate API correctly excludes these, but our per-game parser used to insert `batting_innings` rows for them — causing per-game counts to over-shoot aggregate by 1-2 rows for any player who's ever been Absent. Now filtered in both the batting-row insert and `_derive_partnerships_grassroots` (since absent batters were never at the crease). Existing over-counted rows need a one-time `DELETE FROM batting_innings WHERE dismissal_type IN ('absent', 'did not bat', 'dnb')` to clean up.
- **GR scorecard team-name parsing**: `isHome` lives on `matchSummary.teams`, NOT on the top-level `teams` array. Reading from the wrong field is silently OK (no error) but produces empty `home_team`.
- **Caught-behind (caught by the keeper)** (migration 075): **CA does NOT mark the keeper in `dismissalText`** — it reads plain `"c: C Cecchi b: A Ricci"`, no dagger, no `(wk)` (an early assumption that a `†` was present was WRONG — verified against live data Jun 2026: 6597 catches, 0 daggers). The real signal is **structural**: the innings' **fielding rows carry `wicketKeeperCatches`**, so a catch is "caught behind" **iff its catcher is the fielder with `wicketKeeperCatches > 0`** (or a stumping). `sync._innings_keeper_names(inn["fielding"])` builds the keeper short-name set; `sync._caught_by_keeper(dismissalText, keeper_names)` extracts the catcher (between `c` and `b`) and matches it (apostrophe-normalised) against that set. Persists `batting_innings.caught_behind` (nullable bool, surfaced through `v_effective_batting_innings`; manual branch → NULL; kept OFF the `dismissal_type` string so the many "count caught" readers are untouched). `NULL` = unknown → readers treat it as a plain catch. The four call-sites all build `keeper_names` from the same innings' `fielding` rows: the batting insert + `_extract_bowler_wickets` (sync), `backfill_caught_behind`, `iq_opponent` (live dossier) and `games.py` (scorecard opp rows). Readers that split out a "caught behind" slice: `aggregations.get_dismissal_breakdown` (the profile "HOW I GET OUT" donut), `iq_trends.player_deep_dive` (also un-collapsed `_DISM_MAP`, which used to map `"caught behind"→"caught"`, and added the missing short-code keys `c`/`b`/`st`), `yearbooks` season breakdown, and `iq_team` team batting breakdown (`_dismissal_key`, now also short-code-aware). **Backfill history** with `python -m app.scripts.backfill_caught_behind <org_id>` (or `all` / no arg for every org — re-reads scorecards, sets the flag in place; same network cost as a Full Rebuild but only touches `batting_innings.caught_behind`; new games get it automatically on sync).
- **Caught-behind, bowling side** (migration 076): `bowler_wickets.caught_behind` (nullable bool) is the mirror — set in `_extract_bowler_wickets` via the same `_caught_by_keeper(dismissalText, keeper_names)` on the `method == "caught"` branch (keeper_names from that innings' fielding rows). Splits the "HOW I TAKE WICKETS" donut (`aggregations.get_bowling_dismissal_breakdown`), the `iq_trends.bowler_deep_dive` scouting note, `iq_team._wickets_quality` (team "how we take wickets"), and the **live opponent dossier** (`iq_opponent` matches the opponent batter's catcher against our keeper in the live scorecard; `_DISMISSAL_ADVICE["caught behind"]` now fires, `DOSSIER_VERSION` bumped to 4 so caches rebuild). `bowler_wickets` is read directly (no effective view), so no view change. **Backfill** by re-running `python -m app.scripts.rebuild_bowler_wickets <org_id|all>` (re-derives the table with the flag). Also split: `iq._our_bowler_dominance` `how` array (matchup dismissal methods) and the **match scorecard** — `games.py` returns `batting_innings.caught_behind` on each of our batters' rows and `MatchScorecard.fmtDismissal` shows "(wk)" when caught-behind isn't already daggered (our players' live-enriched text and opposition rows already carry the `†` straight from the scorecard). NOT split (deliberate, low value): StatLab's derived caught/catcher leaderboards.
- **Fielding catches vs WK catches are fully held** — `fielding_stats.catches`/`catches_wk` per-game (from the scorecard's `wicketKeeperCatches`/`totalCatches`), `player_season_stats.catches`/`catches_wk`/`catches_non_wk` per-season (from `fieldingTotalCatches`/`fieldingCatchesWK`/`fieldingCatchesNonWK`). Outfield = `catches − catches_wk`. Split is shown on PlayerProfile/Leaderboard/TeamDetail/Yearbook/PlayerComparison/ShareCard/TeamAnalysis, plus (v8.5) BetterIQ Player Trends, the shared `PlayerProfilePanel` snapshot (`players.py` now returns `season_catches_wk`), AdminManualEntries review tables, and StatLab (`catches_wk`/`catches_non_wk` metrics). Combined-only surfaces that stay combined **by design**: catches milestones, player rankings, MVP/all-rounder/dismissals composites. `player_season_grade_stats` stores combined catches only (count-only use; can't back a grade-filtered WK split).

## PlayHQ Partner API — May 2026 Audit

**Finding**: Grassroots `/scores/*` IS returning scorecards for recent seasons (25/26 confirmed). The "204 for post-migration games" gap is minimal in practice — Applecross's May 2026 hard refresh got 4204 GR matches, 3947 new games, across all seasons including recent ones. The Partner sync was not needed.

**What was removed (May 2026)**:
- `sync_game_level_data()` — the disabled PHQ Partner game-level sync (was called with `all_games=[]`)
- `_backfill_player_playhq_ids()` — PHQ ID backfill from game appearances, never called in sync flow
- `process_game_updated_webhook()` — empty stub

**What was kept (still live)**:
- `deep_sync_player()` in sync.py — admin-triggered per-player resync via Partner API; low value now, but still callable from admin UI
- `suggest_phq_ids()` in sync.py — powers the "PHQ ID Match" admin page (`/admin/phq-match`)
- `playhq_partner_client.py` — still used by games router (live scorecard view for the rare Partner-only games), records router, and organisations router
- `playhq_id` on Player/Organisation models — retained as nullable legacy field; harmless and used for display in admin

**Data layer summary**:
- Season-aggregate stats (`player_season_stats`): Grassroots aggregate API → all 52 seasons ✓
- Game-level stats (`batting_innings`, `bowling_spells`, `fielding_stats`): Grassroots `/scores/*` → all seasons including 25/26 ✓ (204 gap is minimal)
- Live scorecard view for Partner-only games: PlayHQ Partner API via games router (rarely hit)

## Super Admin Club Delete — soft-delete + FK cascade fix (Jul 2026)

**Symptom**: clicking "DELETE PERMANENTLY" on a club (Super Admin → All Clubs) looked like it succeeded (no error surfaced), but the club was still there afterwards.

**Root cause**: `DELETE /club-admin/super/clubs/{id}` deletes `organisations`, relying on `ON DELETE CASCADE` FKs to remove everything downstream (seasons → grades → games → per-game stat rows). Live logs showed the real error: `ForeignKeyViolationError: ... "partnerships_game_id_fkey" ... Key (game_id)=(...) is not present in table "games"` — `partnerships.game_id` was **not actually `ON DELETE CASCADE` in the live database**, even though `app/models/db.py`'s ORM column has always declared `ondelete="CASCADE"`. The model's intent was never applied to the schema — these are pre-Alembic tables (no migration has ever touched these constraints by name), so the drift went unnoticed until a club with real synced data (partnerships rows) was actually deleted. The whole `DELETE` transaction rolled back, which is why it looked like nothing happened.

**Fix (migration 142)**: reconciled the FK on every sibling legacy per-game/per-player stat table sharing the same origin (`batting_innings`, `bowling_spells`, `fielding_stats`, `bowler_wickets`, `game_appearances`, `fall_of_wickets`, `partnerships`, `milestones`, `fee_match_days`) — not just the one that happened to be hit first. Safe on a live, populated table: builds each corrected constraint `NOT VALID` (near-instant) then `VALIDATE CONSTRAINT` separately (a background scan, doesn't block reads/writes), and checks `pg_constraint.confdeltype` first so an already-correct constraint is left alone (cheap no-op on every app-restart re-run via `main.py`'s idempotent mirror).

**Also shipped (migration 143), per direct request**: club "delete" is now a **soft-delete (archive)**, reversible. `organisations.archived_at` (nullable timestamp) — `POST /club-admin/super/clubs/{id}/archive` sets it (no row anywhere is touched), `POST .../restore` clears it. The old hard-delete (`DELETE /club-admin/super/clubs/{id}`) still exists for a genuine permanent purge later, but now requires the club to already be archived first (a speed bump), and is no longer what the UI's "Delete"/now "Archive" button calls. `GET /club-admin/super/clubs` hides archived clubs by default (`?include_archived=true` to show them); `SuperClubs.jsx` has a "Show archived" toggle and a "Restore" action per archived row. Archiving deliberately does **not** touch `is_active` — restoring shouldn't silently flip a state the admin didn't touch themselves.

**Follow-up bug (same day)**: archiving a club then trying to self-serve-register it again under the same CA org id was rejected as "already registered" — `find_matching_organisation` (the shared duplicate-check `sync.py` helper) had no awareness of `archived_at` at all. Fixed with an `include_archived` param (default `True`, preserving `upsert_organisation`'s own dedup guard — it must still find and reuse an archived row rather than creating a second one for the same CA org): `self_serve_trial.py`'s three duplicate-check call sites (`search`, `/prepare`, `/submit`) now pass `include_archived=False`, so an archived club reads as available to register again. `/submit`'s finishing block (alongside the existing `is_active=True`/slug backfill) now also clears `archived_at` — registering a previously-archived club un-archives it, which is what "available to register again" has to mean once submit reaches that point and reuses the row.

## Key Notes

- PlayHQ public game summary API is "not applicable to Cricket" — no scorecards without a partner JWT
- PostgreSQL `ORDER BY year DESC` defaults to NULLS FIRST — always use `.nullslast()`
- API field names: `bowlingEconomyRate`, `fieldingTotalCatches`, no `bowlingOvers` (derive from `bowlingBalls`)
- `Season.year` is NULL when Grassroots doesn't return `startDate` — extract from name (`"Summer 2010/11"` → `2010`) as a fallback
- `stats["player_seasons"]` in sync is `len(player_data)` summed across seasons, i.e. player-season records, not unique players. With 52 seasons × ~3.4 avg seasons/player ≈ 5326 (which Applecross actually shows). Renamed from `stats["players"]` to match what it counts.

## May 2026 Historical Data Fix — Resolution Log

**Problem**: post-migration, every historical game had blank `home_team`/`away_team` AND Jack Barendse had ~280 batting rows instead of the expected 200. Two root causes.

**Fix 1 — duplicate batting rows from running both sync paths**:
PlayHQ Partner game-level sync was disabled in `sync_organisation` (see Sync Architecture above). Same physical match has different UUIDs in PHQ vs Grassroots; the existing-game skip is UUID-based; running both produced duplicate batting rows.

**Fix 2 — `isHome` lookup on wrong field**:
GR scorecard parser was reading `isHome` from the top-level `teams` array — silently absent, so every game's `home_team` was empty. The flag actually lives on `matchSummary.teams`. Fixed and re-parses cleanly.

**Verification (Applecross, post-wipe + hard refresh)**:
- games: 3957 (was 4418 — old number was bloated by PHQ/GR duplicates)
- batting_innings: 41423, bowling_spells: 26862, fielding_stats: 15495
- games with empty home_team: **0**
- Barendse, Jack: **200 batting / 168 bowling / 93 fielding** ✓

**Fix 3 — successful hard-refresh stuck at `running`** (discovered during the verification of Fixes 1+2):
`sync_organisation` only calls `finish_sync_run` when it owns the run (i.e. when called without a `run_id`). The hard-refresh handler owns the run itself but only called `finish_sync_run` in its exception branch. Fixed `club_admin.py::hard_refresh_org._run` to call `finish_sync_run(run_id, stats)` after a successful `await sync_organisation(...)`.

## June 2026 Cross-Club Player Over-Count Fix (v7.32.1)

**Symptom**: a player who turned out for two synced clubs (e.g. Applecross **Cricket Club** *and* Applecross **Junior Cricket Club**) showed his *combined* career on each club's page — 7 ACC matches displayed as 63 (7 + 56 junior).

**Root cause — players have the SAME shared-GUID collision that Seasons already solved.** `players.id` is the raw Cricket Australia participant GUID used as a **global** primary key, but CA reuses one participant GUID for a person across every club they play for. Both clubs' org-scoped aggregate feeds (`/participants/organisations/{org}/...-statistics`) therefore return that one GUID. Whichever club syncs first **creates** the single `players` row (and sets its `organisation_id`); the other club's sync then finds it by PK — `session.get(Player, pid)` is a **global** lookup, not org-scoped (sync.py ~538/558) — and attaches *its* seasons' `player_season_stats` to the same row. Every career query then did `SUM(player_season_stats.matches) … WHERE player_id = :pid` with **no organisation filter**, so the total double-counted across both clubs. (Seasons dodge this via a per-club derived id `uuid5(org, grassroots_id)`; players were never given that treatment.)

**Fix — enforce the invariant "a player's effective season stats are only the rows whose season belongs to the player's own org", once at the view + at every base-table reader that summed by org-*membership* instead of by *season's* org:**
- **Migration 060** redefines `v_effective_player_season_stats` so the base-table branch only emits a row when `EXISTS (player.organisation_id IS NULL OR player.org = season.org)`. This is the single point that fixes **every** view consumer — `get_career_*` / `get_season_by_season` (player profile), `records.py` (club records), `get_player_team_breakdown`'s aggregate count. Non-destructive (filters on read; base rows untouched), so it self-corrects and survives a re-sync — **no data cleanup or re-sync needed**.
- Base-table readers that bypass the view were scoped to the org's seasons individually: `players.py` upcoming-milestones, `sync.py::_compute_milestones` (stops minting inflated milestone rows), `iq.py::_their_key_players`, `statlab.py` (career + per-season + family + minutes), `iq_trends.py` active-players overview, `selection_pool.py` latest-season form snapshot, `club_admin.py` milestone projection.
- **Anti-pattern to avoid in new queries**: summing `player_season_stats` for a player filtered only by `players.organisation_id = :org` (player *membership*) without also constraining the **season** to that org. Read the view, or join `seasons s` and filter `s.organisation_id`. Queries that filter `WHERE s.organisation_id = :org` or `WHERE pss.season_id = <specific org season>` were already correct (yearbooks, iq_trends trajectory/breakout, iq_selection, the sync backfill).

**Deeper fix — per-club player ids (in progress, phased)**: the display scoping above stops a shared CA participant GUID from *displaying* co-mingled, but the second club of a shared GUID still can't see a player's stats at all (they sit on the first club's record — e.g. a junior club showing 30 when the player's junior career is 56, because the 56 live on the senior club's row). Giving players a per-club derived id like Seasons fixes it at the source. Rolled out incrementally so the 50+ single-club orgs are never touched:

- **Phase 1 (migration 062)** — add `players.grassroots_id` (raw CA participant GUID), backfilled from `id` (which IS the raw GUID for every legacy row), + `UNIQUE (organisation_id, grassroots_id)`. Non-breaking; no id changes.
- **Phase 2a (sync.py aggregate pass)** — `_resolve_org_player()` looks a participant up by `(org, grassroots_id)` and mints `id = uuid5(org, guid)` **only when the raw GUID is already a player id in another club** (the real collision); otherwise it keeps the raw-GUID id. So ordinary new players are unchanged and the **game-level scorecard sync (participantId == player id) keeps working untouched**. The aggregate pass deletes+reinserts per season, so a **re-sync moves a shared player's seasons off the first club's row onto his new per-club row** — the second club then shows the right career total. The first club is unaffected (it keeps the raw-GUID id and its own seasons).
- **Phase 2b (done)** — `sync_grassroots_game_level_data` now translates scorecard `participantId` (raw GUID) → per-club `uuid5` id before every game-level insert, so a per-club player gets per-innings rows (batting/bowling/fielding/FOW/partnerships/appearances/bowler-wickets) too. Implemented via a single `_team_pid(guid)` closure + a `pid_by_guid` map built in discovery (and threaded into `extract_bowler_wickets`, whose 3rd arg is now `gate_pids` + a new `pid_by_guid`; `app/scripts/rebuild_bowler_wickets.py` updated to match). **Identity for legacy single-club orgs** (`grassroots_id == id` ⇒ `pid_by_guid[g] == g` ⇒ `_team_pid` returns the same value the old `guid in our_team_pids` checks used), so their game-level attribution is byte-for-byte unchanged. The aggregate pass runs before the GR pass in `sync_organisation`, so the per-club player row exists before its game-level rows reference it (FK-safe). **Still verify on a data copy before prod**: confirm a normal club's per-game counts are unchanged and the shared player's per-game rows land on his per-club id. Game-level only re-attaches on a **Full Rebuild** (the GR sync skips already-synced games), so the cutover for a club with a shared player is Full Rebuild → merge the duplicate.

**Rollout / cutover** (after deploying phases 1+2a):
1. **Re-sync the second club** (Sync Now, or Full Rebuild) — mints the per-club player and moves his aggregate seasons onto it. The club's career number corrects (junior → 56).
2. (After Phase 2b) Full Rebuild the club for game-level consistency.

**⚠️ Do NOT merge the legacy-GUID duplicate into the per-club record when their seasons OVERLAP.** Discovered Jun 2026 on Matthew Watt: the post-migration GUID's per-club record (`eddde526…`, a uuid5 — note the `5` in the 3rd group) already held the **complete** 56-match junior career (CA back-fills full history onto the post-migration PlayHQ GUID). The legacy MyCricket GUID (`09ce6a6c…`, a v4 raw GUID) was a **duplicate of the older seasons** — but under **different season records**, because MyCricket and PlayHQ assign different season GUIDs to the same real season. `merge_players` dedupes by raw `season_id` (admin.py ~205), so it didn't recognise the dup, **moved** the 30 over and the career read **86 = 56 + 30**. Recovery: **undo-merge** (restores 56). The two records can't be cleanly merged until the duplicate *seasons* are reconciled (season-alias / migration-season-dedup is the unbuilt proper fix); the merge is only safe for genuinely **disjoint** registrations.

**`undo-merge` grassroots_id fix** (Jun 2026): the undo re-creates the removed player and **must** set `grassroots_id` (= `id::text`, correct for any legacy raw-GUID player), or the next sync won't find it by `(org, grassroots_id)` and will mint *another* per-club duplicate. Fixed in `admin.py::undo_merge`.

**Anti-pattern reminder**: don't reintroduce a global `session.get(Player, raw_guid)` create/lookup in sync — use `_resolve_org_player`. `players.id` is no longer guaranteed to equal the CA GUID (it's `uuid5(org, guid)` for per-club rows); the raw GUID lives in `grassroots_id`.

## June 2026 Cross-Club Grade Collision Fix (v2.16.1)

**Symptom**: a newly-onboarded club (High Wycombe) showed only the 3 grades *unique* to it (Year 8/9) in the dashboard Grade dropdown and BetterSelect auto-seed, even though it plays ~16 grades. Recent-matches (PlayHQ-partner, live) and the season summary (participant-stats, whole-club) looked correct, so only the grade-scoped surfaces were starved.

**Root cause — grades had the SAME shared-GUID collision Seasons and Players already solved.** A CA **grade is a competition-wide entity**: one grade GUID (`/scores/grades/{id}/matches` returns every match between *all* clubs in it — verified 10 clubs share HW's "1st Grade") is returned by `get_teams` for *every* club in the grade. But `grades.id` used the raw shared GUID as a **global** primary key, and sync's `session.get(Grade, grade_id)` was a **global** lookup — so the **first club to sync a grade created the row, and every later club's sync skipped it**, leaving the grade attached to whoever synced first. Applecross was onboarded before HW, so HW's 12 shared grades (1st/3rd/5th Grade, One Day 2/3/5, Colts, RJR T20, Year 5/6/9-Central) sat on Applecross's seasons; HW only created the 3 Applecross didn't have. The aggregate season stats (`player_season_stats`) survived because they come from the **participant**-scoped stats endpoint (whole club, grade-agnostic), not from grades.

**Fix — per-club grade ids, exactly mirroring the Season/Player scheme** (phased, mint-on-collision so the 50+ single-club orgs are byte-for-byte unchanged):
- **Migration 067** — add `grades.grassroots_id` (raw CA grade GUID), backfill from `id` (which IS the raw GUID for every legacy row), + `UNIQUE (season_id, grassroots_id)`. Non-breaking; no id changes.
- **`sync._resolve_org_grade()`** (mirrors `_resolve_org_player`) replaces the global `session.get(Grade, guid)` skip in the aggregate grade-seeding loop. Looks a grade up by `(org, grassroots_id)`; mints `id = uuid5(org, guid)` **only** when the raw GUID is already a grade in another club; else keeps the raw GUID. `org_grade_map` is built once per sync alongside `org_player_map`.
- **The raw GUID is what every grassroots API call must use** (not the per-club PK). Switched: per-grade stats `gradeId` (sync.py), the scores pass `get_grade_matches` (uses `grassroots_id`; scorecard `grade.id` → per-club id via a `grade_id_by_guid` map so `games.grade_id` is the per-club id), `iq_opponent._target_season_grades`/`_our_games_vs`/`_grade_name`, `ladders.py` (team + grade-ladder), `iq.opponent_ladder`. Every one is `COALESCE(grassroots_id, id)` ⇒ identical for legacy grades.
- **`rebuild_bowler_wickets.py` is unaffected** — it iterates *game* ids and only joins grades via the DB FK.

**Cutover for an affected (2nd+) club**: deploy + migrate, then **Sync Now** (re-runs the aggregate grade-seeding → mints the per-club grades, so the dropdown + per-grade stats fill immediately; the scores pass then discovers the never-before-synced shared-grade games and pulls them). A **Full Rebuild** is the guaranteed-complete version. **Known residue**: a match between two *both-synced* clubs (e.g. HW vs Applecross) is one shared `games.id` (= match GUID) owned by whoever synced it first, so the 2nd club won't get its own row for that one game — pre-existing game-identity limitation, separate from grades; HW-vs-unsynced-club games (the vast majority) are unaffected.

**Anti-pattern reminder**: don't reintroduce a global `session.get(Grade, raw_guid)` create/skip in sync — use `_resolve_org_grade`. `grades.id` is no longer guaranteed to equal the CA GUID (it's `uuid5(org, guid)` for per-club rows); the raw GUID lives in `grassroots_id`, which is what `/scores/grades/{id}/matches`, the ladder API, and the per-grade stats `gradeId` are keyed on.

## BetterFees — Match-Fee Auto-Allocation (v7.32.0, Jun 2026)

A recorded match-fee payment settles a member's games automatically, **oldest game first**. Per-game Paid / Part-paid / Unpaid is **derived on read, not stored** — there is no per-row paid flag any more.

- **Single source of truth**: the sum of a member-season's `match_day` `fee_payments`. `allocate_match_days(charges, match_paid)` in `services/fees.py` walks the games oldest-first (`played_at` nullslast, then `id`), paying each in full while money lasts; the boundary game is `partial`, the rest `unpaid`, and a $0 game (rate $0 / no tier) is `na`. Money left once every game is covered = **credit** ("in the Green").
- `routers/fees.py::get_member` computes this on read and returns per-row `status` + `amount_covered` + `charge`. `_financials` now surfaces `membership_credit` / `match_fee_credit` / `credit` / `in_credit` (overpayment is **no longer clamped to 0**). Buckets are **kept separate** — match-fee credit never offsets membership owing. No tier ⇒ no credit claimed.
- Because status is derived, adding/removing a payment or editing `days_played` re-allocates automatically — **no migration, no stored flag to keep in sync**.
- **Legacy, still live**: the `paid_payment_id` column and the `mark-paid` / `unmark` / `payments/bulk` endpoints still exist and still create `match_day` payments (which feed allocation), but no longer drive the per-row display. The old per-row MARK PAID / UNMARK buttons were removed from the member page in favour of a single "Record match-fee payment" box (`RecordMatchFeeForm`). The bulk-payment page still works (it reads the derived `is_paid` and creates payments).

## BetterMerch — club stock register (v8.18, Jun 2026)

Third module under the **BetterAdmin** umbrella (`MODULE_GROUPS.admin` already
anticipated it; no separate price, the BetterAdmin toggle now covers
`fees`+`comms`+`merch`). Tracks club stock across three category templates on one
engine: **apparel** (sized/coloured variants), **equipment** (quantity OR
individual assets), **food_drink** (canteen/bar, with expiry). Gated by
`require_module("merch")` + the `MANAGE_MERCH` cap. Surface at `/admin/merch`
(`BetterMerchLayout`, BetterAdmin amber via `moduleBrand('merch')`); pages
Overview / Stock / Equipment / Activity / Reports / Square.

- **Migration 083** (mirrored idempotently in `main.py` lifespan): `merch_products`
  (the catalogue line), `merch_variants` (**stock lives here** as a running
  `quantity`; one 'Standard' variant for un-varied products so apparel and canteen
  read through the same code), `merch_movements` (signed in/out audit log:
  received/sold/issued/used/adjustment/stocktake/write_off), `merch_assets`
  (individual high-value equipment: condition + service/replace dates).
- **`services/merch.py`**: `record_movement` (bumps the variant balance + writes the
  audit row, no commit), `merch_alerts` (low-stock / expiring / service-due,
  computed on read, no table), `stock_summary`. `routers/merch.py`
  (`/club-admin/merch`) is products+variants, movements, assets, a player merch
  view, alerts, reports + CSV.
- **Player link** (admin-only): a sold/issued movement carries `player_id` + a
  `paid` flag; outstanding merch money = sum of unpaid movement amounts. Surfaced on
  the admin player profile modal via the `footer` prop added to
  `PlayerProfilePanel.Profile` (`PlayerMerchPanel`), gated on
  `hasModule('merch') && hasCapability(MANAGE_MERCH)`. Never on the public profile.
- **Alerts feed the notification bell**: `notifications.py` count+summary add merch
  alerts when `org_has_module(club,'merch')`. Like the pending-request counts, this
  is current state, not "since last seen".
- **Per-variant pricing + tracking mode (migration 085)**: each variant carries its
  own `unit_cost`/`unit_price` (override of the product default via `_eff_cost`/
  `_eff_price`), so one product holds several priced kinds (e.g. a 4-piece match ball
  and a 2-piece trainer). `merch_products.for_resale` splits stock into bought-to-sell
  (cost + price, sold/issued to members) vs **club-use** consumable (a straight cost,
  no sell price, no owing — e.g. balls); the New Product form defaults equipment to
  club-use. Club-use products drop sold/issued from the movement picker. Report margin
  counts only priced items (a `CASE` in `stock_summary`) so club-use cost doesn't drag
  it down. Money displays two decimals.
- **Category tree (migration 086)**: `merch_categories` is a self-referencing tree
  (≤3 levels) per club, partitioned by the fixed top type (`top_category`); products
  get an optional `category_id`. Created **inline** as items are added (POST
  `/categories` dedupes a same-named sibling). Endpoints `GET/POST/PATCH/DELETE
  /merch/categories` (delete reparents children, nulls products via FK SET NULL). The
  Stock list filters by node+descendants (`_descendant_ids`); reports add `by_item`
  and a rolled-up `by_category_node` (each node carries its whole subtree's totals).
  Frontend `CategoryPicker` is one dropdown (paths like "Balls › Match") + an inline
  "+ New category" with an optional parent. A `CategoryManagerModal` (the "Categories"
  button on Stock) renames/deletes nodes; `POST /categories/seed-defaults`
  (`MERCH_DEFAULT_CATEGORIES`, "Add starter set") seeds a generic one-level set
  (Match attire / Balls / Canteen…), idempotent. The three fixed types stay as the
  template drivers (sizes / expiry / club-use default), separate from the tree.
  Products and individual variants are both editable after creation (product Edit
  modal via the card gear; per-line `VariantEditModal` via the line gear — label/
  size/colour, cost/price, threshold, expiry; quantity stays movement-driven).

### Square POS integration (migration 084, v8.18.1)

One-way mirror, **Square → BetterMerch** (Square's till owns the canteen count).
OAuth code-flow, per club.

- **Migration 084**: `merch_square_connections` (one per club: tokens,
  `location_id`, `sync_enabled`/`sync_sales`, `sales_cursor`, last-sync status),
  plus mapping columns `merch_products.source/.square_object_id`,
  `merch_variants.square_object_id`, `merch_movements.source/.external_ref` (+ a
  partial unique index on `(org, external_ref)` to dedupe imported rows).
- **`services/square_client.py`** (httpx) — OAuth obtain/refresh/revoke, locations,
  `ListCatalog` (ITEMs carry their ITEM_VARIATIONs nested), `BatchRetrieveInventoryCounts`,
  `SearchOrders` (COMPLETED). Host from `settings.square_environment`
  (sandbox vs production). `services/square_sync.py` — catalog upsert → sales import →
  inventory reconcile, **all in ONE transaction** (helpers `flush`, sync commits
  once) so ORM objects don't expire mid-sync (async `MissingGreenlet` trap);
  `ensure_fresh_token` refreshes the 30-day access token within a week of expiry
  (`session.refresh(conn)` after, since that commit expires conn).
- **Double-count design**: inventory count is the source of truth for `quantity`.
  Sales are imported as `sold` movements (real negative delta + revenue), THEN we
  reconcile each variant to Square's current count via a `stocktake` movement. The
  stocktake is a set-to-absolute, not a second decrement, so sales never double down
  the stock; receipts/waste show up as the reconcile delta. Re-runs dedupe sales on
  `external_ref` (`square:{order_id}:{line_uid}`).
- **OAuth**: gated `GET /square/connect-url` mints a signed JWT `state`
  (`sign_square_state`, typ `square_oauth`, 20 min) and returns the authorize URL;
  the **public** `routers/public_square.py` `GET /public/square/callback`
  (unauthenticated, protected by the signed state) exchanges the code, stores the
  connection, auto-picks the location if there's one, then 302s back to
  `/admin/merch/square`. Scheduler runs `sync_all_square` daily at 04:00.
- **Deploy** (server `.env`): set `SQUARE_APP_ID` + `SQUARE_APP_SECRET` (never
  commit), `SQUARE_ENVIRONMENT=production` (or `sandbox`), optional
  `SQUARE_API_VERSION`. In the Square Developer dashboard register the app's OAuth
  **redirect URL = `https://betterat.cricket/api/public/square/callback`** (matches
  `settings.square_oauth_redirect`; nginx strips `/api`). The box must reach
  `connect.squareup.com`. Tokens are stored per club as plain columns (same
  precedent as `playcricket_api_token`); encryption-at-rest is a hardening follow-up.

## BetterSelect — Self-service player availability (v8.1, Jun 2026)

Players set their own availability with **no account, no app, no Facebook** — one
per-club magic link + a last-4-of-phone PIN, shared by QR / group chat. Full
design note: `docs/betterselect-self-availability.md`.

- **Migration 068**: `organisations.availability_link_token` (unique, nullable,
  **rotatable** — `secrets.token_urlsafe(24)`), `availability_self_service_enabled`,
  `availability_require_pin` (default true). `player_availability.source`
  (`'admin' | 'self'`) — `recorded_by` is NULL for self answers, so `source` is
  the audit/badge signal. Idempotent ALTERs mirrored in `main.py` lifespan.
- **Public router** `routers/public_availability.py` (prefix `/public/availability`,
  **unauthenticated** — NOT wrapped in `require_module`; it resolves the club from
  the token and checks `org_has_module(club, "select")` + the enabled flag itself,
  so a disabled/downgraded club's link 404s). Endpoints: `GET /{token}` (branding
  + active-player names), `POST /{token}/verify` ({player_id, pin} → signed
  HttpOnly **`bs_avail`** cookie {club, pid, typ:'avail', ~30d}), `GET|POST
  /{token}/me` (this player's dates + answers / upsert `source='self'`,
  `recorded_by=NULL`), `POST /{token}/switch` (clear cookie). PIN gate =
  last-4-of-`Player.phone` (strip non-digits). **Lockout** after 5 wrong / 15 min
  per (token, player, IP) via new `services/rate_limit.FailureTracker`
  (`assert_not_locked`/`record_failure`/`clear_failures`) + a coarse per-IP
  `enforce` throttle. Unknown-player and wrong-PIN both count as a failure so the
  link can't enumerate the roster.
- **Admin** (on the gated `availability` router, cap `MANAGE_SELECTIONS`):
  `GET /availability/self-service`, `POST /availability/self-service`
  ({enabled?, require_pin?} — mints a token on first enable),
  `POST /availability/self-service/regenerate`. Returns a phone-coverage count
  (active players with a usable last-4). The admin matrix now returns the real
  `source` (was hardcoded `'manual'`) so self cells get a corner-dot badge; an
  admin override re-stamps `source='admin'`.
- **Shared helpers** in `routers/availability.py`: `phone_last4`,
  `active_self_service_players` (non-dormant active roster — same recency rule as
  the matrix), `upcoming_fixtures_by_date` (the matrix's date grouping, extracted
  so the public page and matrix agree on valid dates). The matrix was refactored
  to call it (pure extraction).
- **Frontend**: public route `/avail/:token` (`pages/PublicAvailability.jsx`,
  outside `ProtectedRoute`, global Navbar suppressed in `App.jsx` — own minimal
  white-labelled header, club accent via inline `--pb-accent`). 3 steps: pick
  name → last-4 PIN → tap Available/Maybe/Unavailable (date-keyed; cookie resume
  jumps straight to step 3). Admin `SelfServiceLinkPanel.jsx` on the Availability
  screen: enable/PIN segmented toggles, link, copy-link, copy-message
  (`🏏 Set your availability: {link}`), **client-side QR** (`qrcode` npm dep —
  `QRCode.toDataURL`), regenerate, phone-coverage nudge. New `api.js` methods:
  `bsGetSelfService`/`bsSetSelfService`/`bsRegenerateSelfService` +
  `availPublicLanding`/`Verify`/`Switch`/`Me`/`Set`.
- **Cross-feature**: self answers are plain `player_availability` rows, so they
  flow into the Selection pool automatically. `/auth/me` + `/auth/login` now
  return `club_slug` (powers the admin "View Public Page" button).
- **Navbar buttons** (separate small ask, shipped same release): "Admin Login" on
  the public club `Navbar.jsx` (→ `/login`, or "Admin" → `/admin` when signed in);
  "View Public Page" in `AdminLayout.jsx` header (→ `/{club_slug}`).

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

## BetterSelect — Vote collection (v8.92.0, migration 193, Jul 2026)

Brownlow-style best-player votes per fixture, its own "Votes" menu item in
BetterSelect. Everything is **derived on read** from raw ballots + the club's
current `vote_settings` (no stored weekly results or season points), so a
mid-season config change restates the whole season — same philosophy as
BetterFees' derived allocation.

- **Migration 193** (+ idempotent `main.py` lifespan mirror): `vote_settings`
  (org singleton: `enabled`/`link_token`/`require_pin`, `voter_mode`
  'players'|'captain', `ballot_values` JSONB default `[3,2,1]` — fully custom,
  best-first, ≤10 positions — `counting_method` 'rank'|'tally', `tie_policy`
  'share'|'countback', `allow_self_vote` default false,
  `allow_non_participants` default false, `auto_close_days` default 7),
  `vote_ballots` (one per voter per fixture — `voter_player_id` for a club
  player OR bare `voter_name` for a non-participant; partial uniques per
  identity space; `source` 'self'|'admin'), `vote_ballot_picks` (ranked
  positions only — values derived from config at count time),
  `vote_fixture_overrides` ('locked'|'reopened' on top of the auto-close
  window).
- **Eligibility = the synced scorecard** (per direct instruction, not the
  saved lineup): a fixture is votable once its game has landed in `games`
  (manual fixtures aren't votable yet), and the votable/voter list is
  `services/votes.eligible_players` — the union of `game_appearances` +
  batting/bowling/fielding rows, **org-scoped through `players.organisation_id`**
  (the shared-game cross-club leak rule). Captain-only mode uses
  `game_appearances.is_captain`, falling back to the lineup's captain when the
  sync predates the flag. **`games.id` is NOT `fixture.id`** for a synced
  fixture — see `services.votes.match_ref_id` below; this was wrong at launch
  and is fixed in the v8.94.5 note further down.
- **Counting** (`services/votes.py`, pure functions, unit-checked offline):
  'tally' = season points are the raw sum (10 voters' 3s = 30). 'rank' =
  weekly conversion — top raw vote-getter earns `ballot_values[0]`, etc.;
  'share' ties use standard competition ranking (both take the higher value,
  next value(s) consumed), 'countback' breaks on most-of-the-highest-value
  then down the ballot, dead heats still share. Season year = Jul→Jun
  (`season_year_for`); rounds group on `fixtures.round` (label else date) and
  the leaderboard can replay standings "as at" any round (`through_round`).
- **Two capabilities**: `MANAGE_VOTES` (settings/link, ballot entry + delete,
  lock/reopen, per-fixture ballot detail — which shows who voted for whom) and
  `VIEW_VOTE_RESULTS` (leaderboard) — the Main Admin hands the latter out per
  user since many clubs keep the count secret (club_admins implicitly hold
  both). New `require_any_cap(*caps)` factory in `auth/capabilities.py`;
  `BetterSelectLayout` NAV gained `anyCaps` support. **No tallies on any
  public surface** — leaderboard is admin-app only, by decision.
- **Routers**: `routers/votes.py` (`/votes/*`, mounted with
  `require_module("select")`) — settings GET/POST/regenerate, fixtures list
  (season-year filter + state + ballot counts), fixture detail, admin ballot
  upsert (paper votes / captain texting in — works after close, any named
  voter, but picks still restricted to who played + the self-vote rule),
  ballot delete (spoof moderation), lock/reopen, leaderboard.
  `routers/public_votes.py` (`/public/votes/*`, unauthenticated — resolves
  club from `vote_settings.link_token`, checks entitlement + enabled itself,
  404-tells-nothing): landing, PIN verify (same lockout/rate limits as
  availability, own `bs_vote` cookie), per-fixture state, ballot submit.
  Verified players vote as themselves ('captain' mode restricts to the
  captain); a typed name is accepted only when `allow_non_participants` — a
  verified player who didn't play also counts as a non-player ballot (stronger
  identity than a typed name). Self-vote + played-only + open-window all
  enforced server-side.
- **Frontend**: `pages/admin/betterselect/AdminVotes.jsx`
  (`/admin/betterselect/votes` — Fixtures / Leaderboard / Settings tabs; the
  settings tab has the link+QR panel and points at the Users page for
  leaderboard access) and `pages/PublicVoting.jsx` (`/vote/:token`,
  standalone/no-navbar like `/avail/`): pick game → verify (or "I didn't
  play" name entry when allowed) → assign positions one at a time ("Who gets
  your 3?") → review → submit; resubmitting updates the same ballot.
- **Eligibility source is a club choice** (v8.94.0, **migration 194**): the
  votable list comes from `vote_settings.eligibility_source` —
  **`scorecard`** (default, who actually played) | **`lineup`** (the saved
  BetterSelect `fixture_lineups` XI) | **`playhq`** (the team list the club
  published on Play.Cricket, live via `services/lineups.our_lineup_players`).
  The last two are ready on match day, so a club can vote on the night instead
  of waiting for the weekly sync. Per-fixture override on
  `vote_fixture_overrides.eligibility_source` (its `status` went nullable so a
  row can carry a source alone); `POST /votes/fixtures/{id}/source` ('' clears
  back to the club default). `votes.resolve_eligibility` picks the requested
  source and **falls back to the first other source that has players**,
  reporting `requested`/`used`/`fell_back`/`counts`/`unmatched` so the admin
  page shows which list is really in play; `check_all=True` (admin detail only)
  also counts the unused sources, which costs one live Play.Cricket fetch.
  `fixture_vote_state`'s old `awaiting_sync` is now **`awaiting_team`** (no
  votable list from ANY source yet) and takes `ready` rather than `has_game`.
  **The list views compute `ready` cheaply** (`has_game or has_lineup`, or
  played-and-`playhq`) — a live per-fixture upstream call per row would be one
  request per fixture, so an unpublished Play.Cricket side is reported when the
  ballot page is actually opened.
- **`merge_players` reassigns vote rows** (`admin.py::_merge_players_core`):
  both vote FKs are ON DELETE CASCADE, so without the reassignment a routine
  merge would silently destroy the removed record's ballots and every vote
  cast for them. De-dups (keep's ballot/pick wins) then moves; deliberately
  NOT in the undo log — an undone merge leaves votes on the kept player
  (same human, no vote lost).
- **Known gap** (deliberate v1): manual fixtures/games aren't votable — the
  votable probe needs a real synced game (see `match_ref_id` below), and a
  manual fixture has no upstream match at all.
- **Fixed: `fixture.id` was never the real match GUID (v8.94.5)** — reported
  live: a played fixture (Darwin CC 2nd XI vs Waratah Warriors B, already
  fully scorecarded on Play.Cricket) showed **0** for all three eligibility
  sources — "Match scorecard", "BetterSelect XI" AND "Play.Cricket team
  list" — even though the match had a live team list AND a completed
  scorecard, confirmed by fetching the Grassroots match directly. Root
  cause: `routers/fixtures.py::sync_fixtures` (the only automated path that
  creates `Fixture` rows) sets `source='grassroots'` and mints a **random
  `uuid4()`** for `Fixture.id`, storing the REAL Grassroots match GUID in
  `Fixture.playhq_id` instead (so two clubs playing each other keep separate
  fixture rows despite sharing one `games.id`) — the Fixture model's own
  docstring ("`id == the CA/PlayHQ game GUID`") describes a scheme that was
  never actually implemented this way. `services/votes.py` took that
  docstring at face value: `game_exists`/`eligible_players` (scorecard
  source) and the live `our_lineup_players` call (Play.Cricket source) both
  cross-referenced bare `fixture.id` against `games.id` / a live Grassroots
  fetch — which never matches, so both sources always read empty for any
  auto-synced fixture, regardless of whether the game was actually synced or
  published. Fixed with `services.votes.match_ref_id(fixture)` — returns
  `fixture.playhq_id` (parsed to a UUID) when set, else `fixture.id` for a
  manual fixture (correctly never matches a real game) — used everywhere
  `eligible_from_source`, `routers/votes.py::list_vote_fixtures`'s `synced`
  set, and `routers/public_votes.py::_open_fixtures`'s `synced` set
  previously used the bare Fixture PK. `fixture_lineups` (BetterSelect XI)
  is untouched — it's keyed on the Fixture's own PK throughout, which is
  self-consistent regardless of `playhq_id`.
- **Fixtures tab filters (v8.94.5)**: with the id bug fixed, clubs running
  several grades hit the next problem — one flat, unfilterable list of every
  played fixture across every team for the season. `GET /votes/fixtures`
  gained `grade_id`/`round_key`/`q` (free-text opponent search); the
  response's `grades`/`rounds` option lists are always built from the WHOLE
  season regardless of the other filters, so the dropdowns never collapse to
  the current selection. `AdminVotes.jsx`'s Fixtures tab grew Team/Grade,
  Round and a search box alongside the existing season-year picker; picking
  a grade resets the round filter, since round options are scoped to it.
- **Ballot entry now respects "Captain only" voting (v8.94.6)**: reported
  live — with "Who votes" set to Captain only, the "Enter a ballot" voter
  dropdown still listed every player who played, not just the captain.
  `admin_enter_ballot` was always deliberately looser than the public page on
  who it lets vote (any named voter, so an admin can transcribe paper votes
  from any source) — nothing server-side actually enforces `voter_mode`
  there, so this is a frontend-only default, not a new backend restriction.
  `BallotEntryForm` now defaults the voter picker to just the fixture's
  captain(s) when `settings.voter_mode === 'captain'` and any are known,
  with a "Show all players" link for the edge case (vice-captain filling in,
  a sync predating the captain flag leaving `eligible[].is_captain` all
  false, in which case it falls back to showing everyone rather than an
  empty list).
- **Fixed: round order + a missing grade filter (v8.94.7)**: reported live —
  the Round dropdown listed rounds out of numeric order ("Round 13, 15, 12,
  14, 11, 7, 10…"), and the Team/Grade filter didn't appear at all. Both
  traced to the same underlying gap: `routers/fixtures.py::sync_fixtures`
  (the only automated path that creates `Fixture` rows) never populated
  `Fixture.grade_id` at all — it only auto-attributes `team_id` (BetterSelect's
  own team concept) — so every auto-synced fixture read `grade_id = NULL`,
  starving the grade dropdown of any options; and several grades' fixtures
  routinely share one match date (ordinary Saturday club cricket), so the old
  date-only round sort left same-date rounds in undefined order, exposing
  that a numeric label ("Round 13") was being tie-broken as a plain string
  ("Round 10" < "Round 7" alphabetically). Fixed three ways:
  1. `services.votes.round_sort_key(label, date)` sorts numerically on the
     label first (falls back to a large sentinel for a non-numeric label like
     a final, so it sorts after every numbered round), date second — used by
     both `list_vote_fixtures`'s round options and `build_leaderboard`'s
     round grouping.
  2. `services.votes.effective_grade_ids(db, fixtures)` resolves a fixture's
     grade from its own `grade_id` when set, else falls back to the synced
     game's `grade_id` (via `match_ref_id` — the game-level sync is a
     separate, correct pipeline that always sets this). Used everywhere
     `list_vote_fixtures`/`build_leaderboard` build grade options, filter by
     grade, or label a fixture's grade — so the filter/leaderboard grade chip
     both work retroactively for already-synced fixtures, no backfill needed.
  3. `sync_fixtures` itself now also stamps `Fixture.grade_id` going forward,
     via a new `db_grade_id` field threaded through
     `services.fixtures_source.org_grassroots_fixtures` (our own `grades.id`
     for the fixture's grade — NOT the raw CA grade guid the function already
     returned under `grade_id`, which can differ on a cross-club collision,
     see the grade-collision note above).
- **Entering ballots on a closed/locked round already worked, made obvious
  (v8.94.7)**: asked live whether a club admin or super admin can catch up on
  end-of-season voting for rounds that auto-closed. Turns out
  `admin_enter_ballot` never had a voting-state gate at all ("works whatever
  the voting state — paper votes often arrive after close", already in its
  own docstring) and `build_leaderboard`/`tally_ballots` count every stored
  ballot regardless of the fixture's current state — so a late-entered ballot
  on a closed round already counted correctly, no code change needed there.
  What was missing was that the UI never SAID so: `FixtureDetail` now shows a
  plain note on a closed/locked fixture that ballots can still be entered
  below without reopening, and that "Reopen voting" is only needed if players
  should be able to self-serve vote via the public link again.
- **Direct fixture/team links + filters on the public voting page (v8.94.8)**:
  per direct request — one club-wide link (`vote_settings.link_token`) was the
  only way in, so every player had to wade through the whole season's games to
  find their own team's, and there was no way to point someone straight at a
  single match. Rather than mint a token per fixture/team (a real proliferation
  for a multi-grade club), the SAME base link now takes optional query params
  that scope it — no new token, no new settings row:
  - `?fixture=<id>` — `PublicVoting.jsx` auto-opens straight into that game's
    ballot once the landing data loads (skips the games list entirely), via
    the existing `GET .../fixtures/{id}` endpoint (unchanged). Reached
    directly rather than via the games list's `disabled={!open}` guard, so a
    link to a not-yet-open or already-closed game needs its own message —
    added a `fixture.fixture.state !== 'open'` check ahead of the existing
    role check, reusing `fixture_vote_state`'s state values.
  - `?team=<grade_id>` (+ `?round=`/`?q=`) — scopes the landing list itself.
    `GET /public/votes/{token}` gained `team`/`round_key`/`q` params, threaded
    into `_open_fixtures`, which now ALSO returns `grades`/`rounds` option
    lists (built from the whole lookback window regardless of the current
    filter, same pattern as the admin Fixtures tab) by reusing
    `services.votes.effective_grade_ids`/`round_sort_key` — no new backend
    logic, just wiring the same v8.94.7 fix into the public path too.
  - The public landing page shows Team/Round selects (+ a search box) when
    there's more than one option, changing a filter updates the URL's query
    params (`replace: true`, so it doesn't spam browser history) — which is
    what makes the "team link" shareable: filter down once, copy the address
    bar. `updateFilter`/`backToGames` centralise all the URL-parameter
    bookkeeping so every "back to games" button in the flow keeps the
    team/round filter but drops `?fixture=`.
  - Admin-side generation: `FixtureDetail` gets a "Copy link" button
    (`?fixture=`) next to Lock/Reopen; the Fixtures tab's grade filter gets
    "Copy this team's link" (`?team=`) once a grade is picked. Both reuse
    `data.settings.token`/`detail.settings.token` (already returned by
    `list_vote_fixtures`/`fixture_detail`) and only show once the link itself
    is enabled.

## Votes redesign — Games hub, podium leaderboard, awards night, one-screen ballot (Jul 2026)

The three-tab admin screen (Fixtures/Leaderboard/Settings) and the public
stepper ballot were rebuilt from the `docs/design_handoff_betterselect_votes`
handoff. Every existing endpoint/field keeps its shape — this is additive.

- **Games hub** (was "Fixtures", `?tab=hub`, `VotesHub.jsx`): a 4-cell counter
  strip (open now / ballots this round / awaiting team / rounds counted, from
  the new `GET /votes/fixtures` `summary` block), a status segmented control
  (client-side filter, so counts stay stable while flicking) + grade chips +
  round/search/season selects (server-side), a fixture table with a
  `<BallotProgress>` bar per row (`voters_expected`/`outstanding_count`,
  computed batch-per-page — see below), multi-select bulk open/lock
  (`POST /votes/bulk-state`), and one `ShareVotePanel` (WhatsApp/SMS/copy/QR/
  socials, all client-side URL schemes — no backend send) + `OutstandingVoters`
  chase card for whichever open fixture is "in focus".
- **`voters_expected`/`outstanding_count`** (new fixture-list fields): batch
  SQL across the whole season's fixtures (`services/votes.py::
  scorecard_voter_counts`/`lineup_voter_counts`/`player_ballot_counts`) rather
  than one live-eligibility call per row. `'playhq'`-sourced fixtures read 0 in
  the list (a live Play.Cricket fetch per row isn't worth the round trips) —
  same "cheap readiness" trade-off the pre-existing `ready` flag already made;
  the fixture DETAIL view (one fixture, one fetch) resolves it exactly via
  `resolve_eligibility`. `summary`'s counters are computed over the WHOLE
  season regardless of the hub's own grade/round/search filters, matching how
  `grades`/`rounds` options already work.
- **Leaderboard** (`VotesLeaderboard.jsx`): a 1st/2nd/3rd `PodiumCard` row
  (gold/silver/bronze — the one new hex is `#c98b4a` bronze), a standings table
  with rank movement (▲/▼ vs the previous counted round) and a per-player form
  sparkline (last 5 counted rounds), and a `RaceChart` (hand-rolled inline SVG,
  cumulative points for the top 5 — no charting library pulled in for five
  polylines). All of `movement`/`tied`/`form`/`cumulative`/`round_gain`/
  `grade`/`grade_short` are computed inside `build_leaderboard` from a rank
  snapshot taken after every counted round — no new storage, still fully
  derived-on-read like the rest of this feature. `last_round` (the race card's
  "what just happened" block) is the last counted round's own results.
- **Awards night** (`AwardsNight.jsx`, `?tab=leaderboard` → Presentation mode):
  full-screen, forced-dark stage (re-declares `color`, not just the `--pb-*`
  tokens, since `color` inherits), reveals the count one round at a time via
  `through_round` replay (→/Space/←/Esc). `board.club_name`/`club_short`/
  `season_label`/`grade_name`/`grade_id` are stamped onto the leaderboard
  payload by the router (`_club_short` falls back to initials when the club
  has no `short_name`); `grade_id` on the board is what fixes the awards-night
  reveal actually replaying the SAME grade the leaderboard was scoped to
  (without it, a grade-filtered presentation would silently replay whole-club
  standings on every reveal).
- **Public ballot, one screen** (`PublicVoting.jsx`): the old per-position
  stepper is replaced by 3 tap-targets (3/2/1) above the team list — tap a
  name to fill the next empty slot, tap a filled slot/chosen name to clear it,
  Submit once full. No API change; `picks` is still the same fixed-length
  array submitted as-is.
- **`POST /votes/bulk-state`** — `{fixture_ids, action: 'open'|'lock'}`, same
  per-fixture rules as the existing single lock/reopen endpoints; a fixture
  that can't open (no team list) is reported in `skipped`, not a hard failure.
- **`POST /votes/nudge`** — `{fixture_id, player_ids}` or `{fixture_ids}` (every
  outstanding voter across several fixtures). **Deviates from the design
  brief on purpose**: the brief assumed automated SMS/WhatsApp reminders, but
  this codebase has no SMS/WhatsApp sending integration at all (BetterComms is
  email-only, `services/email_service.py`) — so a nudge is a reminder EMAIL to
  the player's stored address (`services/votes.py::send_nudge`), and a player
  with no email simply reads `channel: 'none'` and can't be nudged this way
  (`reason: 'no_contact'`). Rate-limited to one nudge per player per fixture
  per 24h via the new **`vote_nudges`** table (migration 196, mirrored in
  `main.py`'s lifespan) — the send log both backs the cooldown and makes the
  count auditable, same posture as the BetterComms usage policy.
- **`OutstandingVoters` on the hub tab** needed its own fixture-detail fetch
  (`fixture.outstanding` only exists on `GET /votes/fixtures/{id}`, not the
  list) — `VotesHub` fetches it for whichever open fixture is "in focus" and
  merges it in, rather than the list row's bare `outstanding_count`. Manage-
  only (nudging is a `MANAGE_VOTES` action; a `VIEW_VOTE_RESULTS`-only user
  never triggers the extra fetch).
- **"Post to socials"** (phase 2 in the brief — no standings-card renderer
  exists yet in BetterSocials): `ShareVotePanel` copies the message and
  deep-links to the plain `/admin/social-post` composer instead of doing
  nothing.
- Capabilities unchanged: `MANAGE_VOTES` gates the hub's write actions/bulk/
  nudge/fixture detail/settings; `VIEW_VOTE_RESULTS` gates the leaderboard and
  presentation mode. No tallies anywhere on the public page.

## BetterIQ — Opposition, Selection & Player Trends (v2.1.0, June 2026)

Best-tier analytics module (master-plan Phase 4). Gated by `require_module("iq")` + the `MANAGE_IQ` cap. Module surface mirrors BetterSelect — own `IQLayout` (violet `--pb-accent` override), dashboard tile + sidebar entry flip on automatically once `MODULE_INFO`/`MODULE_META` have `built: true`. Routes under `/admin/betteriq` (Overview + Opposition + Selection + Player trends). **NL Q&A is the one remaining phase** (still needs an LLM-provider decision — open in the spec).

**Selection & Player trends (v2.1.0)** — two more read-only surfaces, both pure reads over held data (org-scoped via grades→seasons over the `v_effective_*` views):
- `iq_selection.py` (`/iq/selection/*`) analyses a fixture's saved BetterSelect lineup (`fixture_lineups`). **It reuses BetterSelect's own pool** — `services/selection_pool.assemble_selection` (extracted v2.2.0 from `routers/selection.py`, which now delegates to it) — so eligibility (12-month recency wall, women's/men's gender wall, squad tier, per-date availability incl. period fallback) is **identical** to the selection board. Re-deriving it earlier let ghosts through (a women's player / years-dormant names appearing as promote picks for a men's 2nd XI). On top it computes XI **balance** (pace/spin, keeper, openers, all-rounders, LH/RH from `skill_positions`+`bowling_type`), last-5 **form**, **warnings** (no keeper, thin attack `<5`, plus ineligible-pick flags: wrong-grade/inactive/dormant/unavailable, out-of-form bat `<15`), **promote** (`autofill_eligible` + available + in form, never selected), **rest** (ineligible/out-of-form picks), playing up/down via the pool `tier`, and a **match-up** column (each player's record vs the fixture's opponent via `resolve_opponent` + `opp_key`). `_resolve_opp_key` prefers explicit opponent so this stays correct.
- `iq_trends.py` (`/iq/trends/*`) reuses `aggregations.get_season_by_season` / `get_career_*` / `get_upcoming_milestones_for_org` + `milestone_rules`: per-player season-by-season **trajectory**, **breakout/decline** (latest season vs prior-career baseline, min-sample gated: bat ≥5 recent / ≥10 prior inns, bowl ≥6/≥15 wkts), and **milestone forecasting**. No new tables.
- **Opponent match-to-club**: `_resolve_opp_key` now prefers an explicit `opponent` over `fixture_id` (identity from the chosen club; the fixture only supplies the grade), so the Opposition UI's "Match club" search can link an unlinked upcoming fixture to a known `opp_key`.
- **Deeper analytics (v2.3.0)** — all read-only: **Trends** add recent-form sparklines (`_player_recent`), milestone **ETA** (career per-game rate, `_eta_games`), peak season + **consistency** (σ of season avg), **role-evolution** (bat/bowl share, first vs last third), and an **"emerging"** shelf (`_emerging`). **Selection** adds `_best_available_xi` — a greedy best XI from the `autofill_eligible` pool (keeper + ≥5 bowlers enforced) diffed against the picked XI (`suggest_in`/`suggest_out`). **Opposition** adds `_venues_vs` (W/L by venue) and `_our_bowler_dominance` (our-bowler × their-batter repeat-dismissal grid from `bowler_wickets`; merged with main's parallel whole-club opposition rework).
- **Live dossier depth (v2.4.0)** — `iq_opponent.py` (main's whole-club scout) now also parses opponent **fall-of-wickets** into a partnership-by-wicket / collapse map (`season_fow` → `partnerships` + `_partnership_insight`) and a team-wide **dismissal breakdown** (`dismissal_breakdown`, summed from the per-batter `dism` counters). Frontend `KeyPlayersCard.jsx` — a Uiverse crypto-card-inspired, IQ-themed showcase — flicks through the danger batters/bowlers with a headline stat, vs-us record and a drawn recent-form sparkline.
- **Scouting synthesis (v2.5.0)** — rule-based, scorecard-derived, **no LLM** (NL Q&A stays parked). In `iq_opponent._assemble`: `_enrich_batter`/`_enrich_bowler` add a `key_note` + recommended `plan` + `risk` + `confidence` (sample-gated per the brief's §19.5) onto each danger player; `_how_they_win_lose` + `_game_plan` produce team tendencies (top-order reliance, strongest/fragile partnership, thin attack) and a "How to beat them" one-pager (`remove_early` / `see_off` / `target_bowler` / `key_warning` / `one_liner`). Surfaced via `GamePlan` + `WinLose` in `OppositionScout`, enriched on the frontend with head-to-head + best venue + our-performers from the instant report. **North-star vision doc: `docs/community-cricket-analytics-brief.md`** — the full "digital cricket analyst" roadmap. Reality filter: our data is **scorecard-level, not ball-by-ball**, so phase/ball-matchup/pressure/win-probability features (brief §1.2–1.3, §2.2–2.4, §10.1, §15.1) are out of reach; the matchup proxy that survives is `_our_bowler_dominance` (our-bowler dismissals of their batters).
- **Team self-analysis (v2.6.0)** — brief §7/§8, the opposition lens pointed at us. `iq_team.py` (`/iq/team/*`, page `TeamAnalysis.jsx` at `/admin/betteriq/team`) reconstructs **our** team score from `SUM(batting_innings.runs)` and the **opponent's** from `SUM(bowling_spells.runs)` (runs our bowlers conceded), so bat-first vs chase, "what score wins" bands and defending/chasing all come from stored per-innings data (no live fetch) — close-but-not-exact (extras we don't store are excluded). One per-game pull (`_per_game`, org-scoped via grades→seasons over `v_effective_*`), aggregated in Python into record/home-away, batting profile (top/mid/lower split via `batting_position`, boundary%), bowling, bat-first/chase win%, score-band win rates, venue records, partnership-by-wicket (`partnerships.is_club_innings`), and a `_how_we_win_lose` synthesis.
- **Player deep-dive (v2.7.0)** — brief §1.4/1.5/1.9/1.10. `iq_trends.player_deep_dive` (`GET /iq/trends/player/{id}/deep`) does ONE innings pull (runs, not_out, dismissal_type, batting_position, opp_key) and derives in Python: **starts & conversion** (reach-25 %, 25→50, 50→100, score bands), **dismissal breakdown**, **batting by position** (Opening/First-drop/Middle/Lower/Tail buckets + best position), **by-opposition** (best/worst by avg, min 2 inns) and a rule-based **scouting note** (CricViz card §16.9). Surfaced as extra cards in the `PlayerTrends` detail view (lazy-loaded alongside the trend). Dossier `DOSSIER_VERSION` bumped so the v2.5 opposition synthesis (game plan / win-lose / scouting notes) rebuilds for **every** cache key — whole-club and each team — instead of waiting on the 7-day TTL.
- **Captain's Cheat Sheet (v2.8.0)** — brief §16.6. `CheatSheet.jsx` at `/admin/betteriq/opposition/cheatsheet?opponent=…&fixture=…&team=…` — a **print-ready, light-themed one-pager** composed entirely from the existing report + dossier payloads (no new backend): game plan, danger batters/bowlers (with their plan), our bowler match-ups (`bowler_dominance` → "save X for Y"), how-they-win/lose, our edge (`our_performers`) and head-to-head + best venue. `window.print()` + a `@media print` block (hides chrome, fits A4). "Cheat sheet" button in `OppositionScout` passes the current opponent/fixture/team through the URL.
- **Danger/false-threat alerts (v2.9.0)** — brief §16.2/16.3. `_enrich_batter` now adds an `alert` (`danger` reasons: in hot form / averages big vs us; `caution`/"paper tiger" reasons: not-out-inflated average, leans on one big score, low-confidence sample, slow SR); `_enrich_bowler` flags the main threat. `DOSSIER_VERSION` → 3 so caches rebuild. Surfaced as a Danger / "Paper tiger?" badge + reason line on `KeyPlayersCard`.
- **More scorecard analytics (v2.10.0)** — **Fielding/keeping** (brief §3/§9): `iq_team._team_fielding` → top fielders, keepers, run-out specialists + fielder→bowler catching combos (from `bowler_wickets.fielder_id`), in `team_overview.fielding`. **Opposition memory** (§16.10): `iq._last_meeting` → most-recent meeting result, our/their score (`SUM(batting_innings.runs)` / `SUM(bowling_spells.runs)`), our top bat & bowler that game, in the instant report. **Selection value** (§6.2): `iq_trends.player_deep_dive` adds `selection_value` — team win% with vs without the player (`game_appearances` vs all org games) + swing.
- **All-rounder analysis (v2.10.1)** — brief §5. `iq_team._all_rounders`: players who clear both a batting-innings and a wickets floor (4/4 per season, 10/10 all-time) over the per-game `v_effective_*` tables; bat avg recomputed exactly from `batting_innings.not_out`, bowl avg from `runs_conceded/wickets`; ranked by the classic bat_avg−bowl_avg diff and role-classified (genuine / batting / bowling all-rounder). In `team_overview.all_rounders`, board on the Team page.
- **Batting partnership pairs (v2.10.2)** — brief §11.1. `iq_team._batting_pairs`: groups `partnerships` (is_club_innings) by the unordered `LEAST/GREATEST(batter1_id, batter2_id)` pair, org-scoped via games→grades→seasons; per pair → stands, total runs, avg-per-stand, best, 50+ stands, and an `opening` flag (≥half their stands at the 1st wicket). `team_overview.batting_pairs`, board on the Team page.
- **Similar player search (v2.10.3)** — brief §15.8. `iq_trends._similar_players`: club-internal nearest neighbour over a career profile (bat avg [innings-weighted from `batting_average`], bat SR, bowl avg, economy — all from `player_season_stats`), z-scored across the squad and compared only on features both players have (≥2 shared), distance→similarity `100/(1+d)`. In `player_deep_dive.similar_players`, card in the Player trends detail.
- **Club MVPs / player impact (v2.11.0)** — brief §15.3 (the scorecard-reachable subset; ball-level inputs like phase/pressure/dot-balls are out of reach). `iq_team.player_impact` (route `GET /iq/team/mvp`, optional `season_id`, defaults to latest season via `team_seasons`): per-player per-match rates over `player_season_stats` (runs, wickets, fielding dismissals) + economy (≥30 balls), z-scored across the squad (`statistics.pstdev`), blended `1.0·bat + (0.9·wkt + 0.45·inv-econ) + 0.35·field`, min-max scaled 0–100, role-tagged (Batting/Bowling/All-round/Fielding). Headline board on `BetterIQHome`, rows deep-link to `trends?player=`.
- **Matchup advantage matrix (v2.11.1)** — brief §16.5. Frontend-only reshape of the instant report's `matchups.bowler_dominance` (already a flat bowler→batter pairing list) into a heatmap grid in `OppositionScout` (`buildMatrix`/`MatchupMatrix`): top 6 our-bowlers × top 8 their-batters, cells shaded by dismissal count, Matrix/List toggle (matrix when ≥2 bowlers and ≥2 batters). No backend change.
- **Collapse analysis (v2.11.2)** — brief §7.5. `iq_team._collapses`: reconstructs fall-of-wickets per club innings from stored `partnerships` runs (keyed by `(game_id, innings_number)`, is_club_innings), finds the worst 3-consecutive-wicket span (sum of three contiguous partnership runs), flags a collapse when ≤15, and reports collapse %, worst collapse, and a start-wicket histogram ("where the wheels come off"). `team_overview.collapses`, card on the Team page.
- **Batting reliability (v2.11.3)** — brief §6.1 (scorecard-reachable subset). `iq_trends.player_deep_dive` adds `reliability` computed from the SAME innings pull (no extra query): floor/median/ceiling via `_percentile` (25th/50th/90th of the runs distribution), failure rate (dismissed <10), 20+ contribution rate, and a boom-or-bust/steady/balanced `profile` from the coefficient of variation. Card in the Player trends detail.
- **Milestone watch on home (v2.11.4)** — frontend-only. `BetterIQHome` calls `iqTrendsOverview()` and renders the top upcoming milestones (`{needed} to {target} {type}`) in a panel beside the Club MVPs; rows deep-link to `trends?player=`. No backend change.
- **Bowling attack structure (v2.11.5)** — brief §8.3. `iq_team._attack_structure`: per-bowler workload over `v_effective_bowling_spells` — **overs are cricket notation** (10.2 = 10 overs 2 balls), so converted to balls in SQL (`FLOOR(overs)*6 + ROUND(frac*10)`) before summing; pace/spin split from `players.bowling_type` (`_PACE_TYPES`/`_SPIN_TYPES`), per-bowler econ/avg/SR + a Strike/Containment/Stock role tag (min 60 balls season / 300 all-time). `team_overview.attack`, card on the Team page.
- **Consolidation & polish (v2.12.0)** — frontend-only. `TeamAnalysis` reorganised from a ~13-card scroll into **Overview / Batting / Bowling / Players** tabs (a `tab` state + tab bar; cards regrouped, the stray "conceding on avg" line promoted to a proper Bowling summary card). Added a reusable `<Note>` footnote component and "how this is worked out" notes to the opaque blended ratings (Club MVPs on home, all-rounders, collapse, bowling roles, reliability, similar-player). Player deep-dive detail gets a "Deep dive" section divider between the season-trajectory cards and the per-innings cards. No backend/API change.

## BetterIQ — Filters honest, cross-club leak fix, multi-grade filter, clickable players, fixture-aware Ask (v8.74, Jul 2026)

Five related fixes/features from live feedback on the Opposition page:

- **Cross-club player leak (the "Zeplin in our bowl-well list" bug)**: a match
  between two both-synced clubs shares ONE `games.id` carrying BOTH clubs'
  per-innings rows (each club's sync attaches only its own players — by design,
  see the shared-game note in sync.py). Any per-game read that org-scopes the
  GAME (grades→seasons) but not the PLAYER join therefore mixes the opponent's
  players into "our" lists. Fixed by adding `p.organisation_id = :org_id` at:
  `iq._our_performers_vs` (both queries; also now excludes redacted `^\*+$`
  names and returns each player's BetterSelect `squad`), `iq._our_bowler_dominance`,
  `iq._last_meeting` (scoreline sums + top bat/bowl, which used to credit the
  opponent's best batter as ours), and `iq_review.game_review` (totals + top-5s).
  **Anti-pattern**: never read per-game tables "for a game in our org's grades"
  without also scoping `players.organisation_id` when attributing to OUR side.
- **Filters mean what they say**: `OppositionScout` no longer treats the
  default newest season as "no filter" while the header shows 2025/26 over
  all-time numbers. On first visit (filter bar untouched this session — new
  `ctx.touched` flag set by ContextBar interactions) the page defaults the
  global season to **All seasons**; any picked season/grade then genuinely
  scopes every instant-report card (backend already supported it).
- **Multi-select grade filter, IQ-wide**: `ctx.team.id` may now be several
  grade base-names joined with `'||'` — `iq_filters.grade_match_clause`
  (`= ANY(string_to_array(:grade, '||'))`) replaced every `= :grade` site
  (iq_filters/iq/_opp_scope/iq_team×2/iq_trends), so the SAME single `:grade`
  bind serves one name or many; all existing callers unchanged. The filter-bar
  TeamPicker is a checkbox multi-select with a **Seniors only** preset driven
  by `team_grades`'s new `category` field (stored `grades.category` else
  `grade_labels.suggest_category` — the merge-grades classifier). Client-side
  grade comparisons (MatchPreview/SelectionAnalysis fixture narrowing) use
  `teamNames()` from Context.jsx.
- **Clickable player names** (`PlayerLink.jsx`): our players →
  `/admin/betteriq/trends?player=`, opposition → `/admin/betteriq/
  opposition-player?opponent=&player=` (or `&playerName=` for name-only rows —
  the instant report's danger batters have no participant id; OppositionPlayer
  resolves it via its pending-name matcher once the dossier builds). Applied
  across OppositionScout (our-record, match-ups, last meeting, squad tables,
  radars, historical threats), KeyPlayersCard, TeamAnalysis boards, MatchReview,
  MatchPreview, SelectionAnalysis XI.
- **Radar context**: `viz.Radar` has hover/focus tooltips per vertex (score,
  and with `buildRadar`'s new `details` the actual value + peer mean) and a
  `legend` prop; opposition + deep-dive callers pass both.
- **Multi-grade also honours the merge-grades admin feature**: a club can
  merge two literally-different raw grade names (e.g. "PSWL South" / "PSWL:
  South") into one competition via `grade_merge_logs` (org-scoped active
  `alias_name -> canonical_name` rows, `aggregations._GRADE_MATCH` already
  reads it for leaderboards) — the first cut of this filter only stripped the
  sponsor parenthetical (`grade_base`), so a merged club still saw both raw
  names as separate filter options that each only matched their own literal
  games. `iq_filters.grade_canonical_label(alias, org_param)` resolves an
  active alias to its canonical raw name (single-hop, matching
  `_GRADE_MATCH` — merges are re-targeted onto the final root at merge time,
  not chased through a chain here) before stripping the sponsor
  parenthetical; `season_grade_clause`/`iq_team._scope`/`iq_team.player_impact`
  /`iq_trends._movers_src`/`iq._opp_scope`/`iq_team.team_grades` (the
  filter-bar listing query) all route through it. `org_param` defaults to
  `"org"` (every caller except `iq.py`, which binds `"org_id"`).
- **Ask BetterIQ fixture/opposition tools** (`iq_ask.py`): `upcoming_fixtures`,
  `opposition_report` (trimmed instant report; performers carry `squad` for
  team-relevance), `opponent_danger_players` (reads the dossier cache via
  `get_or_start_dossier` — a cold dossier starts building in the background and
  the tool reports `building`, so the model answers from held data now and says
  the deeper scout will be ready shortly). System prompt: resolve the fixture
  first; keep suggestions team-relevant via `squad` (a lower-grade record vs
  the opponent is a "possible promotion" mention, not an automatic pick);
  unlinked opponents → point at "Match club" on the Opposition page.
  `MAX_STEPS` 6 → 8 for the longer tool chains.

## BetterIQ — Review Fixes (Jun 2026, v2.12.1)

Post-v2.12.0 review pass (live-site feedback). All on branch `claude/gifted-babbage-7QE8g`.
- **Team analysis resilience**: `team_overview` wraps every optional add-on (fielding, all-rounders, batting pairs, collapse, attack, partnerships) in `iq_team._safe(session, factory, default)` — logs + `session.rollback()` on failure so one heavy/failing query (e.g. an all-time statement timeout) can't blank the page. Root cause of "Couldn't load team analysis" was the cumulative weight of the new all-time scans; the wrapper makes the core always render. Also renamed a risky `no` SQL alias → `nout`.
- **Club MVP links**: `player_impact` now emits `player_id` (was `id`) to match the IQ-wide convention; home-page deep-links were going to `?player=undefined`.
- **Current-season gating (trends)**: `iq_trends._current_season_year(org)` = MAX(season year with stats). `_batting_movers`/`_bowling_movers`/`_emerging` take `current_year` and gate `latest.year = :cur`, so years-dormant "active" players no longer surface as risers/decliners. `list_players` now returns **current-season** players with this-season stats (runs/avg, wkts/avg, recomputed from not_outs) **+ their BetterSelect squad** (`players.squad_team_id` → `teams.name`) for the new All-squads filter. Averages 2dp everywhere (frontend `fmt2`). Milestone watch removed from home + trends overview (still computed in payload / shown in the bell). Full player grid → `PlayerSearch` combobox.
- **Selection shows unselected fixtures**: `iq_selection.list_lineups` LEFT JOINs `fixture_lineups` and keeps upcoming fixtures even with 0 picked (`HAVING COUNT(fl)>0 OR f.played_on >= CURRENT_DATE`). Frontend shows "needs selecting" + a "no XI saved yet" prompt (empty `data.players`).
- **Opposition match persists** (migration **063** `opponent_aliases`: org_id, alias_name [lowercased], opp_key, display_name, unique(org, alias_name)): `iq.save_opponent_alias` upserts; `iq._load_aliases` (defensive — returns {} if the table isn't migrated) is merged into `opposition_opponents`'s `by_name` and checked first in `_resolve_opp_key`'s fixture branch. New `POST /iq/opposition/match`; frontend `applyMatch` saves then refreshes the picker. Once "Bassendean" → "Bassendean Cricket Club" is matched, all fixtures with that name link.
- **MVP is a whole-season value measure, not current form** — by design it's season-aggregate per-match rates (a late-season slump averages in). The home note says so; "Form movers" / recent-form sparklines are the form lens.

## BetterIQ — Review Round 2 (Jun 2026, v2.12.2)

- **MVP year-based**: `iq_team.player_impact` aggregates over ALL season records of the current YEAR (org-scoped `s.year = :year`), not a single `team_seasons[0]` season_id. A club year often spans several season rows (comps / per-club grassroots ids); keying on one id silently dropped in-form players recorded under a sibling row (Monument/Seen symptom). Year resolved from `resolved.year`; falls back to single season_id only when year is NULL.
- **Team analysis by season AND team (grade)**: `team_overview(season_id, grade_id)`; a `_scope(season, grade)` clause (prefers `gr.id`, else `gr.season_id`, else all-time) threaded through every per-game add-on. `_team_fielding` rewritten onto per-game `v_effective_fielding_stats` (grade-filterable + outfield catches = `catches − catches_wk`). New `team_grades()` + `GET /iq/team/grades`. Frontend defaults to the latest season with prominent Season + Team dropdowns.
- **Trends picker = current-season players**: `list_players` returns this-season players (org-scoped seasons join, merged with main's cross-club guard) + BetterSelect squad; `PlayerSearch` combobox opens on focus & reports empty states.
- **Player deep-dive depth**: reuses `get_player_by_venue` (at-venues) + `get_bowling_dismissal_breakdown` (how they take wickets); career strip splits Caught / Ct (wk) / Stumpings via `total_catches_non_wk`/`total_catches_wk`.
- **Opposition player scout** (frontend-only): the dossier already returns full `batting`/`bowling` per-player lists (form, dismissals, vs_us); `OppPlayerScout`/`OppPlayerDetail` in `OppositionScout` add a search → full per-player profile.
- **Caught vs caught (wk)**: PlayerProfile, Leaderboard, TeamDetail, Yearbook already split; fixed `PlayerComparison` (was `total_catches`) → `total_catches_non_wk` / `total_catches_wk`. StatLab keeps a total + keeper-only-preset model.

## BetterIQ — Bowler deep-dive, captaincy & bowling discipline (v2.14.0, Jun 2026)

Three scorecard-reachable additions from the brief (no schema change, no new tables, no LLM):
- **Bowler deep-dive** (brief §2.5/§2.9) — `iq_trends.bowler_deep_dive` (`GET /iq/trends/player/{id}/bowling-deep`), the bowling mirror of `player_deep_dive`. Reads `bowler_wickets` (org-scoped via games→grades→seasons) — the table was previously only consumed for opposition matchups (`iq._our_bowler_dominance`). Derives **wicket quality** from the dismissed batter's stored `batter_runs`: set (30+) vs started (10–29) vs new (<10), avg scalp value, ducks inflicted; **fielder combos** (`fielder_id` on caught/stumped/run-out, c&b excluded); per-bowler **discipline** (wides+no-balls/over from `v_effective_bowling_spells`); + a rule-based bowling scouting note. Surfaced in `PlayerTrends.jsx` under a new "Bowling deep dive" header — the existing career `bowling_profile` card (added v2.13.0, sourced from the `/deep` batting payload) was **relocated** there so all bowling reads together; the new section is gated on `bdeep.wickets > 0` independent of `innings_count`, so a pure bowler still gets it. `player_deep_dive` itself was left untouched.
- **Captaincy** (brief §4) — `iq_team._captaincy`, added to `team_overview` via `_safe`. First analytics use of `game_appearances.is_captain`: per-skipper W/L/D, win%, team avg score under them (reconstructed like `_per_game`), finals record. Min 3 games. Board on the Team page **Players** tab. **Toss-decision analysis is out** — we don't store the toss (the Partner API has `coinToss` but the GR `/scores/*` sync path doesn't capture it; would need a `games` column).
- **Bowling discipline** (brief §2.9/§8.5) — `iq_team._discipline`, added to `team_overview`. Team wides/no-balls per over, extras as % of runs conceded, most-disciplined-first per-bowler ranking (min 10 overs season / 50 all-time). **Guarded**: returns `None` when no extras are recorded across the dataset (older scorecards omit them) so we never show a misleading "spotless" card. Card on the Team page **Bowling** tab.
- All three respect the `season_id`/`grade_id` `_scope` filter on the Team page; the bowler deep-dive is all-time (matches the player-trend view).

## BetterIQ — Match review, par, role-adjusted batting & batting depth (v2.15.0, Jun 2026)

More scorecard-reachable brief items, no schema change:
- **Post-match review** (brief §16.8) — new service `iq_review.py` (`GET /iq/review/games`, `GET /iq/review/game/{id}`) + new page `MatchReview.jsx` at `/admin/betteriq/review` (sidebar entry "Match review"). Per game: scoreline (our `SUM(batting_innings.runs)` / their `SUM(bowling_spells.runs)`), top batting/bowling contributions, best partnership, extras conceded, a single-game collapse check (worst 3-consecutive-wicket span from `partnerships`, same reconstruction as `iq_team._collapses`), and a rule-based "what changed the game" synthesis. Biggest-over / win-probability swings are out (ball-by-ball).
- **Player batting depth** (brief §1.1/§1.2) — `player_deep_dive` now also returns `batting_style` (strike rate, boundary % = share of runs in 4s/6s, balls-per-boundary, accumulator/boundary-hitter profile — needs `balls`/`fours`/`sixes`, now added to its one innings pull) and `context` (batting average in wins vs losses, batting first vs chasing via `g.result` + `innings_number`). Dot% / SR-by-ball-range stay out (ball-by-ball). Cards in `PlayerTrends.jsx`.
- **Team depth** — all added to `team_overview` via `_safe`, all honour `_scope`:
  - `_wickets_quality` (brief §8.4) — club-wide `bowler_wickets` roll-up: top-order/middle/tail split + set/new batters dismissed + dismissal-type mix. Bowling tab.
  - `_team_starts` (brief §7.4) — opening-stand (`partnerships` wicket 1, club innings) profile + win rate after a good (≥30) vs poor start. Batting tab.
  - `_role_ratings` (brief §15.4) — buckets innings by batting position, pools a club average per slot, rates each batter by their primary-slot average minus that slot's average (so an opener and a No. 8 aren't judged alike). Players tab.
  - **Par score** (brief §15.9) — `innings.par` = median first-innings total in bat-first wins + lowest defended. Surfaced on the Overview "What score wins" card.

## BetterIQ — Match preview, opponent ladder & opposition scouting tags (v2.16.0, Jun 2026)

- **Opposition player scouting tags** (brief §13 "Useful Optional Metadata" — opponent edition) — `opponent_player_tags` table (**migration 064**): org-scoped manual attributes (batting_hand, bowling_action, bowling_type, player_role, is_wicket_keeper, is_danger, notes), keyed by `(organisation_id, participant_id)` where `participant_id` is the CA participant GUID = the dossier's `player_id`. Opposition players aren't in our tables (only the dossier JSON), so tags live **decoupled** from the 7-day dossier cache and are merged on the frontend. `iq.get_opponent_tags` / `iq.upsert_opponent_tag` (raw SQL, mirrors `opponent_aliases`; controlled-vocab fields validated, unknown→NULL); routes `GET /iq/opposition/player-tags` + `PUT /iq/opposition/player-tags/{player_id}`. Editor + coloured badges in `OppPlayerProfile.jsx` (`ScoutingTags` + `TagBadges`), wired through `OppositionPlayer.jsx`. Vocab mirrors `players.*` so the choices match our own players.
- **Opponent ladder standing** — `iq.opponent_ladder` (`GET /iq/opposition/ladder`): fetches the live grade ladder (`grassroots_scores_client.get_grade_ladder` + an inline `_ladder_rows` parser of the documented fixturesladders shape) for the **fixture's grade** (via `resolve_opponent`), flags our row with `club_match_keys`, and matches the opponent row by club-name tokens (stop-words stripped). Returns `our_row` + `opponent_row` (rank/P/W/L/pts). **Current** standings only — historical "vs top-4" splits would need ladder snapshots we don't keep.
- **Match preview** (brief §17.4) — new page `MatchPreview.jsx` at `/admin/betteriq/preview` (sidebar "Match preview"). Frontend composition (no new aggregator endpoint): picks an upcoming fixture from `list_opponents`'s `upcoming`, then fetches `opposition_report` (instant — no dossier build) + `opponent_ladder` + `team_overview` (par/record) in parallel and renders a lean (synthesised client-side), ladder, head-to-head, last meeting, their danger players, our edge, and links to the full scout + cheat sheet. Uses the instant report (fast), not the live dossier.

## BetterIQ — Manual scouting cards: batting & bowling intel (v8.26.0, Jun 2026)

The ball-level read CA does **not** record (no shot direction, no delivery
length/line, no bowler-type-faced) entered by the scout, the same posture as the
existing scout-entered scoring-zones wagon wheel. A **per-player** card (not a
per-dismissal log — deliberately lighter than the competitor app that prompted
it), for **both opposition players and our own**, blended on read with the
dismissal mix we *do* hold into a short "DNA" read.

- **Storage** (**migration 094** + idempotent `main.py` lifespan mirror): two JSONB
  blobs `batting_intel` / `bowling_intel`. For opponents they're new columns on
  the existing `opponent_player_tags` (keyed by CA participant GUID, merged onto
  the dossier on the frontend like the other tags). For our own players, a new
  `player_scouting_cards` table (`organisation_id`, `player_id`, the two blobs,
  `updated_by`; unique `(org, player)`). Blob shape — batting: `vuln_bowling[]`,
  `fav_bowling[]`, `zones[20]` (4 lengths × 5 lines, intensity 0–3), `fav_shots[]`,
  `risky_shots[]`, `strengths`, `weaknesses`, `plan`; bowling: `stock`,
  `variations[]`, `zones[20]`, `danger[]`, `strengths`, `weaknesses`, `plan`.
- **Validation** — `services/scouting_intel.py` (`clean_batting_intel` /
  `clean_bowling_intel` + the controlled vocab: `BOWLING_KINDS`, `BAT_SHOTS`,
  `BOWL_VARIATIONS`, `BOWL_DANGER`, `ZONE_LENGTHS`/`ZONE_LINES`). Shared by the
  opponent upsert (`iq.upsert_opponent_tag`) and the own-player upsert
  (`iq_trends.upsert_player_scouting`). An empty blob normalises to NULL.
- **Present-aware partial save** — `upsert_opponent_tag` now only overwrites a
  field when its **key is present** in the body (per-field `CASE WHEN :x_present`),
  so the four distinct editors (basic tags / scoring zones / batting card / bowling
  card) don't clobber each other. This also **fixed a latent bug**: saving the
  scoring-zones editor used to NULL the role/danger flags it doesn't send. The
  upsert re-selects and returns the full stored row (not an echo of the partial
  body). Same present-aware pattern in `player_scouting_cards`.
- **Routes** — own players: `GET`/`PUT /iq/trends/player/{id}/scouting`
  (`iq_trends.get_player_scouting` / `upsert_player_scouting`, org-scoped via the
  same `players WHERE id AND organisation_id` gate as `player_deep_dive`).
  Opponents reuse `PUT /iq/opposition/player-tags/{id}` (the body just carries
  `batting_intel`/`bowling_intel` too). api.js: `iqPlayerScouting` /
  `iqSavePlayerScouting`.
- **Frontend** — shared `ScoutingCard.jsx` (Batting + Bowling cards, each a
  display + inline editor) + `scoutDna.js` (vocab labels mirroring the backend +
  `buildBattingDna`/`buildBowlingDna`, which blend manual intel with the held
  dismissal breakdown into bullet insights and a headline "plan"). New
  `viz.ZoneGrid` (editable length×line heatmap, click cycles 0→3). Wired into
  `OppPlayerProfile.jsx` (opponent tag save) and the shared `PlayerDeepDive.jsx`
  `DeepDiveTab` (optional `scouting`/`onSaveScouting` props) used by both
  `PlayerTrends.jsx` and `PlayerHub.jsx`.
- **Bowler-fairness fixes** (the original ask — the opponent profile was
  batting-first): the radar is now a Bat/Bowl toggle (`OppRadarCard`, defaults to
  the player's stronger side; a bowler no longer gets forced into a batting radar);
  the Bowling stat card adds strike rate + a recent-wickets sparkline; the
  scoring-zones wagon wheel (a *batting* feature) is hidden for a pure bowler; and
  the opponent **deep scan** (`iq_scout._scan_player_deep`, `DEEP_VERSION`→2) now
  derives **"how he takes wickets"** + wicket quality (set/started/new from the
  dismissed batter's runs) by parsing the opposition cards in the innings he
  bowled — reusing sync's `_parse_bowler_and_fielder` / `_BOWLER_CREDIT_DT`.
- **Batting intel split into favoured vs risky (Jul 2026)**: the original single
  "Favoured / risky shots" chip group and single "Vulnerable to (bowler type)"
  group didn't distinguish a batter's comfort zone from his danger zone. Batting
  intel now carries four vocab lists instead of two: `vuln_bowling[]`/
  `fav_bowling[]` (both `BOWLING_KINDS`) and `risky_shots[]`/`fav_shots[]` (both
  `BAT_SHOTS`) — `ScoutingCard.jsx`'s batting editor shows them as two side-by-side
  pairs. `scoutDna.buildBattingDna` emits a bullet per populated list ("Vulnerable
  to…" / "Comfortable against…" / "Goes after the…, set the trap" / "Favours
  the…"). A pre-split blob's old combined `shots[]` key is a **read-side
  fallback only** (never written again): `buildBattingDna` and the editor's
  `seed()` both treat it as `risky_shots` when the new split fields are still
  empty, so already-saved intel isn't silently dropped when the deploy lands or
  the editor is reopened; bowling intel (`stock`/`variations`/`danger`) is
  unchanged.

**Two data layers** (`backend/app/services/`):
- `iq.py` — *instant* report from data we already hold: head-to-head vs an opponent (W/L/D, home/away split, recent meetings) + our players' record vs them (selection intel). Opponent identity = `COALESCE(opp_org_id, opp_club_name)` (`opp_key`), org-scoped via grades→seasons over the `v_effective_*` views — same pattern as `aggregations.get_player_by_opposition`.
- `iq_opponent.py` — *live* opponent dossier. Opponents aren't synced, but they play in grades we already track and the Grassroots `/scores/*` scorecards carry BOTH teams (sync discards the opponent half: `if pid not in our_team_pids: continue`). So we fetch the fixture's grade matches, keep the opponent (the `teams[]` entry whose `owningOrganisation.id` ≠ ours, or matched by club name), and aggregate their current-season batting/bowling/fielding per `participantId` — the mirror of sync's `our_team_pids` gate. Plus deep head-to-head: re-fetch our stored games vs them (capped) and parse the opponent cards → each opponent player annotated with their record vs us. A never-played-but-fixtured opponent is still scoutable (key the dossier on the name + fixture grade).

**Dossier cache** (`opposition_dossiers`, migration 059): built on demand in a detached `asyncio` task (its own `async_session_maker` session; tasks held in `_BUILD_TASKS` to dodge GC). `status` building→ready/error drives a frontend poll — `GET /iq/opposition/dossier` returns `{status:'building'}` until ready, then the payload. TTL 7 days + a Refresh button (`force=True`, `POST .../dossier/refresh`). Opponent player stats are NOT normalised into tables — this JSON cache is the only place live opponent data lands (keeps the data-rights surface small, no opponent-stats schema).

**Ceiling**: we hold scorecards, not ball-by-ball — so form / averages / SR / conversion / dismissal-patterns / vs-us / venue, but NO phase or ball-level matchup data. The UI says so (`coverage.notes`).

**Bounds** (CA-proxy politeness + latency): `MAX_OPP_SEASON_MATCHES=18`, `MAX_HEAD_TO_HEAD_GAMES=25`; reuses `grassroots_scores_client`'s in-process scorecard cache + semaphore(6). First build ~10–40s, then cached. Overs maths: `_overs_to_balls(10.2)=62` (10 overs + 2 balls).

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

## Marketing Club Directory — Twenty sync fixes (Jul 2026)

Two related fixes to the super-admin Club Directory (`/admin/super/marketing`)'s
Twenty CRM integration, prompted by a live "Gateway Time-out" on Refresh
Twenty leads/tasks and a club whose direct enquiry never showed up as a Twenty
lead or engagement score.

- **Background-task pattern extended to the two Refresh buttons** (`backend/app/routers/marketing.py`).
  `/refresh-twenty-engagement` and `/refresh-twenty-leads-tasks` used to `await`
  the whole sweep synchronously — fine for a small exported-club set, but
  `twenty_client.py`'s self-imposed 90-req/60s rate limiter means a sweep over a
  meaningful number of clubs routinely exceeds nginx's default 60s
  `proxy_read_timeout` (`frontend/nginx.conf` has no override for `/api/`),
  producing a proxy-level "Gateway Time-out" — the backend kept running to
  completion regardless, the browser just gave up first. Both now follow the
  exact pattern `/export-twenty` already used (documented in its own comment,
  same reasoning): `POST` kicks off a `BackgroundTasks` runner and returns
  `{"status": "started"}` immediately; the UI polls a new `GET .../status`
  endpoint (`/refresh-twenty-engagement/status`, `/refresh-twenty-leads-tasks/status`).
  In-process module-level state dicts (`_twenty_engagement_refresh`,
  `_twenty_leads_refresh`), same shape as the existing `_twenty_export` —
  a `_bg_stale()` helper (extracted from the export's own `_export_stale()`) is
  now shared by all three. Frontend: `SuperMarketing.jsx`'s `pollTwentyExport`
  was generalised into `pollTwentyJob(statusFn, formatResult, {onDone})`, reused
  by all three buttons.
  **Bonus fix surfaced while mirroring the pattern**: `export_to_twenty` /
  `refresh_engagement` / `refresh_leads_and_tasks` all document "never raises,
  returns `{"error": ...}` instead" — but the original `_export_twenty_bg`
  stored that dict straight into `state["result"]`, so the UI's
  `formatTwentyResult` tried to format an error dict as a success shape
  (`"Exported to Twenty: undefined club(s) matched…"`) instead of showing the
  real error. New `_settle_bg(state, res)` helper (used by all three background
  runners) detects a truthy `res["error"]` and routes it into `state["error"]`
  instead, so the UI's existing `if (s.error)` branch catches it correctly —
  fixes this for the pre-existing export button too, not just the two new ones.

- **A direct "onboard my club" enquiry now immediately upserts a Company +
  Lead in Twenty at a forced Hot (100) score**, regardless of whether the club
  was ever exported before (`backend/app/services/twenty_sync.py`,
  wired from `routers/public_contact.py`). Previously, BOTH the daily 06:00/07:00
  cron jobs AND the on-demand Refresh buttons only ever touched clubs already
  in `twenty_links` — nothing in the `/public/contact` submission path (used
  identically by the short "Get your club on BetterCricket" CTA modal
  and the full Contact page, distinguished only by `source`) auto-exported a
  new prospect, so a club that enquired but was never separately exported
  showed no engagement score and no Twenty lead until someone noticed and
  clicked "Export to Twenty" manually.
  - `_resolve_onboarding_club()` finds-or-creates the `MarketingClub` +
    `MarketingClubContact` the enquiry belongs to, mirroring
    `_onboarding_signal()`'s own existing priority: the submitter's email
    against a known officer first, then an exact case-insensitive club-name
    match, else a brand-new prospect club is created from what the form gave
    us (synthetic `grassroots_guid = "manual:" + uuid5(name)` — deterministic,
    so a second enquiry from the same club upserts the same row rather than
    duplicating). Verified against a real Postgres instance: name-match reuse,
    email-match-wins-over-a-mismatched-typed-name, and no duplicate rows across
    repeated submissions.
  - `push_club_and_contacts()` gained an `engagement_override` param — when
    given, it's merged over the normally-computed `_engagement()` rollup
    (preserving the other real telemetry fields — sessions, upsell modules,
    etc. — only `engagementScore`/`engagementTier`/`inSalesCycle` are forced).
    It also switches from the existing mirror-only `_sync_lead_from_company`
    (which no-ops if the club has no Lead yet) to a REAL create-or-refresh via
    the new `twenty_leads_tasks.upsert_lead_for_club()` — a single-club
    extraction of `_seed_and_refresh_leads`'s per-club body, so a Lead is
    actually created immediately rather than only mirrored onto one that
    already exists. **Scoped to the `engagement_override` path only** — an
    ordinary campaign-send call to `push_club_and_contacts` (its original
    caller) is untouched, since `_lead_signal`'s own qualifying-signal gate
    already prevents a routine send alone from creating a Lead.
  - `push_onboarding_enquiry(club_name, contact_name, email, phone)` is the
    top-level orchestration, backgrounded from `public_contact.py`'s
    `submit_contact` alongside the existing `mark_contact_source` call — never
    raises, no-ops cleanly when Twenty isn't configured (verified).
  - The **daily 06:00 engagement / 07:00 lead refresh jobs still can't discover
    a brand-new club on their own** — they're unchanged, still scoped to
    `twenty_links`. This enquiry-triggered push is now the one path that closes
    that gap; the jobs remain correct for their existing job (keeping
    already-exported clubs' scores current day-to-day).

- **A trial — requested or started, either as a prospect or an onboarded
  club — gets the same forced Hot (100) + Lead treatment**, on top of the
  enquiry case above. Four distinct code paths all write to the same
  `trial_modules`/`requested_trial_modules`/`demo_status` (prospect) or
  `org_module_subscriptions` (onboarded) state, so each is hooked at its own
  write point rather than centralised:
  - `club_directory.set_sales_state()` — the super-admin Sales Pipeline panel
    in the Club Directory (Trialing / Requested Trial checkboxes, Demo
    dropdown). Tracks the delta of newly-added `trial_modules` /
    `requested_trial_modules` (already existed, for the `request_trial_modules`
    presync-Task queueing) and now ALSO fires
    `push_club_and_contacts(club.id, engagement_override=…)` when a module is
    newly added OR `demo_status` freshly transitions **into** `in_trial`
    (transitioning out, or re-saving the same already-in_trial state, doesn't
    re-push — verified against a real Postgres instance across 7 scenarios).
  - `club_admin.py::create_module_request` — a club's own admin self-serving a
    trial request (`kind == "trial"`) from inside the app. This is the
    "requests a trial" moment for an already-onboarded club.
  - `club_admin.py::start_module_trial` / `approve_module_request` — a super
    admin directly granting a trial, or approving a self-serve trial request.
    This is the "is put on a trial" moment. `approve_module_request` only
    forces it for `req.kind == "trial"` — a subscribe/cancel approval keeps the
    ordinary billing-fields-only push.
  - Both onboarded-club paths go through `_push_club_to_twenty(org_id,
    force_hot=True)` → `twenty_sync.push_org_company(org_id,
    engagement_override=…)`, which gained the same `engagement_override`
    param `push_club_and_contacts` has: only when given does it compute the
    real `_engagement()` rollup (merging the override on top, so the other
    real telemetry fields survive) and create-or-refresh the Lead via
    `twenty_leads_tasks.upsert_lead_for_club()` — an ordinary subscription-change
    push (activate/cancel/renewal-date edit) is untouched, still the
    billing-fields-only push it always was.
  - **Bonus fix surfaced while extending `push_org_company`**: it never
    actually called `session.commit()` — `_upsert`'s `twenty_links` bookkeeping
    (the id-mapping/content-hash dedupe row) was silently rolled back on every
    call, on every existing caller, since the function was first written. Now
    commits like every sibling push function.

- **The forced Hot 100 from a direct enquiry didn't stick.** `push_onboarding_enquiry`
  only forced `engagementScore: 100` on the ONE push it made at submission time — every
  later recompute (`refresh_engagement`'s daily 06:00 job, a BetterComms send, a manual
  "Refresh Twenty scores") called `twenty_sync._engagement()` fresh with no override, so
  a brand-new prospect with no other web/email history landed back around 30–45 (Warm)
  overnight. `_engagement()` now holds a non-customer at a flat `engagementScore: 100` /
  `engagementTier: "HOT"` for `platform_settings.get_direct_enquiry_hot_days()` (default
  **30**, `DEFAULT_DIRECT_ENQUIRY_HOT_DAYS` in `platform_settings.py` — a plain in-repo
  default, not an env var) after the most recent `club_onboarding_requests` row
  attributed to the club (`_onboarding_signal`'s own `onboarding_last`), computed on
  every call so it self-corrects on the next scheduled/manual refresh with no backfill
  needed. Ends the moment the deal is **won** (the club becomes a paying customer —
  `is_customer` routes it to the account-health formula instead) or **lost**
  (`not_interested`, which already early-returns `_engagement()` before this check is
  reached) — whichever comes first. **Super-admin managed**, not server config: a new
  Marketing section on the All Clubs "General Settings" modal (`SuperClubs.jsx`) edits
  it via `direct_enquiry_hot_days` on the existing singleton `platform_settings` JSONB
  row (migration 120 — same store as `default_trial_days`, no new migration), through
  `GET`/`PATCH /club-admin/super/general-settings`. Diagnostic-only `_directEnquiryHot`
  flag added alongside the existing `_recencyPts`/`_freqPts` breakdown (stripped before
  anything reaches Twenty — `twenty_client.py` drops every underscore-prefixed key),
  surfaced in `diagnose_club_lead.py`.

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

## Billing checkout — feature-flagged while it's built (v8.65.0, Jul 2026)

The Account page's SUBSCRIBE button (`AdminAccount.jsx`, Phase 19) has always
been a deliberate stub ("Online subscribing isn't connected yet…"). Work is
now starting on the real thing — preparing bills/invoices, then a Stripe
checkout link — and per direct instruction a Primary Admin must **not** be
able to click through any of it until the team is satisfied it works, even as
pieces of the real flow land on `main`.

- **`platform_settings.billing_checkout_enabled`** (new boolean key in the
  existing `_BOOL_KEYS` allowlist, same JSONB singleton as
  `self_serve_registration_enabled`/`onboarding_wizard_enabled`/
  `trial_nudges_enabled` — no migration needed). Off by default.
  `get_billing_checkout_enabled(db)` reads it; **`require_billing_checkout_enabled`**
  is a ready-to-use FastAPI dependency (`Depends(require_billing_checkout_enabled)`)
  that 403s a route while the flag is off — **every new invoicing/Stripe-checkout
  endpoint must depend on it as it's built**, since the frontend gate is UX
  only and can't be trusted as the real block.
- **Super admin control**: `GET`/`PATCH /club-admin/super/general-settings`
  carries `billing_checkout_enabled` alongside the other flags; a "Billing (in
  progress)" toggle in `SuperClubs.jsx`'s General Settings modal.
- **Frontend**: `GET /club-admin/account/plan` now returns
  `billing_checkout_enabled` alongside `modules`/`is_primary_admin`.
  `AdminAccount.jsx`'s `submitSubscribe` is where the real checkout call will
  eventually go — for now it always shows the stub notice, but the flag and
  its comment are already in place so the real implementation branches on
  `plan.billing_checkout_enabled` from the start instead of needing a
  follow-up safety retrofit.
- **Turning it on**: only once the invoicing/checkout build is tested and
  ready to go live — flip `billing_checkout_enabled` on from General
  Settings. There is no staging environment, so (same as the other
  self-serve-onboarding flags) this switch is the only thing standing between
  "merged" and "a real club paying through it".

## Stripe Checkout — recurring subscription billing (migration 150, Jul 2026)

The real build behind the flag above: a Primary Admin's selected modules
become a single recurring **Stripe Subscription** per club (one Stripe
Customer/Subscription covers every module the club buys through Stripe, not
one subscription per module), priced from the SAME numbers as the public
pricing calculator. Everything here is still gated by
`platform_settings.billing_checkout_enabled` (off by default) — this schema
and code can sit on `main` fully inert until a super admin flips it on, and
Stripe keys are configured.

- **`services/billing_pricing.py`** is a hand-kept Python port of
  `frontend/src/data/pricing.js` (`CORE` $399, the four `PRICED_MODULES` at
  $149/$149/$149/$249, `BUNDLE_DISCOUNT` $0/$0/$48/$97/$146, `FANTASY` $49
  priced standalone outside the bundle). `price_for(selected_keys)` is the ONE
  place both the invoice-preview quote and the real Checkout Session line
  items are computed from — no separate "what Stripe charges" number to drift
  out of sync with "what the app shows". Verified against pricing.js: Core +
  all four modules totals **$949**, matching `ALL_IN`. Keep both files in sync
  by hand; there's no shared build step between the Vite frontend and FastAPI
  backend.
- **No pre-created Stripe Price objects** — `services/stripe_client.py`
  builds each Checkout Session line item from `price_data` on the fly
  (recurring, `interval: year`, `unit_amount` from `billing_pricing`), so a
  new module or a price change never needs a matching dashboard edit. The
  bundle discount, when any, is applied via a cached `duration: once` Coupon
  (see "Bundle discount coupon fixes" below — this used to say `forever`,
  which was wrong).
- **Migration 150** (mirrored idempotently in `main.py`'s lifespan, same
  pattern as every recent migration): `organisations.stripe_customer_id` /
  `.stripe_subscription_id` (set by the webhook once a checkout completes),
  and `billing_invoices` — a local mirror of each Stripe Invoice event so the
  Account page's Billing History never calls the Stripe API directly.
  `billing_invoices.line_items` is OUR OWN `price_for()` snapshot at the
  moment the invoice landed, not Stripe's own line items, so it always reads
  in the same module/price shape the rest of the app uses.
- **Entitlement still lives entirely in `org_module_subscriptions`**
  (migration 118) — a successful Stripe payment just calls the SAME
  `module_subscriptions.set_status_billing`/`remove_billing` writers the
  existing super-admin "approve a subscribe/cancel request" flow already
  uses (`club_admin.py::approve_module_request`). There is no separate
  Stripe-only entitlement path to keep in sync.
- **`routers/billing.py`** (`/club-admin/billing/*`, gated by
  `Depends(require_billing_checkout_enabled)` on `/quote` and
  `/checkout-session` — NOT on `/invoices`, so a club that has already paid
  can always see its own billing history even if the flag is later switched
  off for new signups): `POST /quote` previews a selection with no Stripe
  call (pure `price_for()`); `POST /checkout-session` re-validates the
  primary-admin gate server-side (mirrors `cancel_own_module`'s pattern) and
  that none of the selected modules are already a live paid subscription,
  then returns a real Checkout Session URL to redirect to.
- **`routers/public_stripe.py`** (`POST /public/stripe/webhook`,
  unauthenticated by necessity — trust comes from verifying the
  `Stripe-Signature` header locally against `STRIPE_WEBHOOK_SECRET`, the same
  "verify the signature, not a login" posture `routers/public_ses.py` uses for
  inbound SNS events) is the **only place entitlement is actually granted** —
  the frontend's post-checkout redirect is UX only (shows a status, re-fetches
  the plan after a short delay). Handles `checkout.session.completed` (grants
  immediately, using the fresh subscription's period end as the renewal date),
  `invoice.paid` (rolls renewal_date forward on every renewal, reactivates a
  `past_due` module, upserts the `billing_invoices` row — idempotent on
  `stripe_invoice_id` so a replayed event is safe), `invoice.payment_failed`
  (moves the affected modules to `past_due` — a grace period, not an instant
  cutoff, matching the existing `ACTIVE_STATUSES` semantics), and
  `customer.subscription.deleted` (drops every module the subscription
  covered, same end state as the in-app self-service cancel). Deploy note:
  register this URL in the Stripe dashboard as
  `https://betterat.cricket/api/public/stripe/webhook` (nginx strips `/api`).
  A handler failure returns 500 so Stripe retries, rather than silently
  swallowing a failed entitlement write.
- **`org_id` + the selected billing keys round-trip through Stripe's own
  metadata** (the Checkout Session's `client_reference_id`/`metadata` AND the
  Subscription's own `metadata`) rather than a custom signed-state JWT (the
  pattern Square's OAuth callback uses, `routers/merch.py::sign_square_state`)
  — Stripe already carries `metadata` through the whole
  session/subscription/invoice object graph, so the webhook never needs a
  second lookup against our own DB to know what was bought.
- **Settings** (`config/settings.py`, mirrors the Square block's shape):
  `stripe_publishable_key` / `stripe_secret_key` / `stripe_webhook_secret` /
  `stripe_currency` (default `aud`), a `stripe_configured` property (blank
  keys = every billing call raises `StripeNotConfigured`, turned into a clean
  503 rather than a raw SDK traceback), and `stripe_checkout_success_url` /
  `stripe_checkout_cancel_url` computed from `public_base_url`.
- **Not built this round**: a Stripe Customer Portal link (self-service
  card update / cancel from the Stripe side) and per-club Stripe tax
  handling — both natural follow-ups once the base flow is verified end to
  end with real keys.
- **One club, one Stripe Subscription — never a second, parallel one.** A
  Checkout Session in subscription mode always creates a brand NEW Stripe
  Subscription; it can't add items to one that already exists. Originally
  (this section used to say) `/checkout-session` just 409'd outright once a
  club had a live subscription, to avoid a double-billed Core and an orphaned
  original. **v2 (below) replaces that outright block with the real
  feature** — adding modules to the existing subscription instead of ever
  creating a second one.
- **Webhook delivery order isn't guaranteed** — `invoice.paid` for a brand-new
  subscription's first invoice can arrive before `checkout.session.completed`
  has stamped `stripe_subscription_id` onto the org.
  `stripe_billing._resolve_org_for_subscription` falls back to fetching the
  subscription and reading its own `metadata.org_id` when the org isn't found
  by `stripe_subscription_id` yet, and self-heals by stamping it — otherwise
  that first invoice would silently never show up in Billing History even
  though entitlement was still granted correctly via `checkout.session.completed`.

### Adding modules to an already-live subscription (migration 152, Jul 2026)

Per direct instruction: **no bundle discount on a module added after the
initial subscribe**, and it must be **prorated to the existing subscription's
renewal date**, then renew at full price from there — Stripe's own
proration engine does exactly this natively, so we lean on it rather than
hand-rolling day-count math.

- **Two distinct paths in `routers/billing.py`, chosen by whether
  `club.stripe_subscription_id` is already set**: no subscription yet → the
  original Checkout Session flow (`billing_pricing.price_for` — Core +
  selection, bundle discount, redirect to Stripe to collect payment details).
  Already subscribed → add items to the EXISTING subscription
  (`billing_pricing.price_for_addon` — no Core line, no discount, ever). The
  add-on path never redirects to Stripe at all — the card is already on
  file, so it charges the prorated amount immediately and synchronously,
  server-side.
- **`/quote` mirrors the same branch**: returns `{"mode": "new_subscription",
  ...price_for()}` or `{"mode": "add_to_existing", ...}` where the add-on
  shape's `total`/`line_items` come from a REAL Stripe call —
  `stripe_client.preview_add_modules` calls `Invoice.create_preview` with the
  hypothetical new items and `proration_behavior=always_invoice` — so the
  preview is Stripe's own exact proration figure, not an approximation we
  compute from day-counts. `AdminAccount.jsx` renders each mode differently
  (a "Charged today (prorated)" total + a note about full-price renewal for
  the add-on case, vs the usual bundle-discount breakdown for a fresh
  subscribe).
- **`stripe_client.add_modules_to_subscription`** creates a `SubscriptionItem`
  per new module (`proration_behavior=always_invoice`, so Stripe invoices and
  charges the prorated amount as part of that same call, against the
  existing payment method — no 3-D Secure/SCA re-authentication flow is
  handled for this path, a known limitation) and then `Subscription.modify`s
  the subscription's own `metadata.billing_keys` to the union of old + new
  keys, so future `invoice.paid` renewals (`stripe_billing.py`) keep
  refreshing the newly-added module's `renewal_date` too — without this the
  renewal loop would silently stop touching it, since it reads the
  subscription's metadata to know what's on it.
- **Real Stripe Product ids, unlike the Checkout Session path.** Checkout
  Session line items support an inline ad-hoc `price_data.product_data`
  (no product to pre-create), but `SubscriptionItem.create` and
  `Invoice.create_preview` do NOT — both require a real Product id via
  `price_data.product`. `stripe_client._ensure_product` creates each
  billable module's Product exactly once and caches the id in the new
  `stripe_products` table (migration 152) rather than re-creating — or
  Stripe-searching for — it on every add-on checkout. (Verified this whole
  parameter shape against Stripe's own current API docs while building it,
  not assumed from memory — the inline-vs-real-product-id split between
  these two endpoint families is easy to get wrong.)
- **Entitlement granted synchronously, not via webhook**, for this path —
  there's no `checkout.session.completed` event for a flow that never
  touched Stripe Checkout, so `routers/billing.py::create_checkout_session`
  itself calls `module_subscriptions.set_status_billing` right after Stripe
  confirms the item + invoice were created, using the subscription's own
  freshly-returned `current_period_end` as the renewal date. The `invoice.paid`
  webhook that follows moments later re-applies the same state — harmless,
  since every entitlement write here is idempotent.
- **`stripe_billing._upsert_invoice` now snapshots `line_items` from
  Stripe's OWN invoice lines**, not recomputed from `billing_pricing` against
  every currently-held module — a renewal invoice bills everything, but an
  add-on invoice only bills the newly-added module(s), so re-deriving "what's
  on this invoice" from the full held-module set would have shown a partial
  invoice as if it were a full one.

### Promotion codes + other payment methods (Jul 2026)

- **Promotion codes** — `create_checkout_session` sets `allow_promotion_codes:
  true` (shows a customer-facing "Add promotion code" field on Stripe's own
  checkout page) whenever the bundle discount ISN'T already applying.
  **Never set both** — Stripe rejects a session with `discounts` AND
  `allow_promotion_codes` set together (`amount_off/percent_off Coupons` and
  customer-enterable **Promotion Codes** are created/managed entirely in the
  Stripe Dashboard, Product catalogue → Coupons — no admin UI of ours
  needed).
- **Apple Pay / Google Pay already work with zero setup** — confirmed live
  (a real Apple Pay button appeared on a test checkout without any
  `payment_method_types` configuration). Neither `create_checkout_session`
  nor anything else in this codebase sets `payment_method_types` explicitly,
  so every session already uses Stripe's **dynamic payment methods**: it
  shows whatever's enabled in Dashboard → Settings → Payment methods,
  automatically, no code change ever needed to add a new one.
- **AU BECS Direct Debit and PayTo are both Stripe-supported for AU
  accounts** — same story, a Dashboard toggle away, no code change. Two
  things worth knowing before switching either on: BECS/PayTo both take
  days (BECS) or up to ~60 seconds after bank-app mandate authorization
  (PayTo) to confirm, vs a card's instant response — our webhook-driven
  entitlement grant already handles that fine (a club just sees a shorter
  "processing" window before Subscribed lands). PayTo specifically performs
  best under $1,000 AUD (BetterCricket's most expensive bundle is $998, a
  good fit) but has "relatively low" business-bank-account coverage
  (consumer accounts are its stronger suit) and bank-side mandate caps
  around $25,000 — a non-issue at these price points, just worth knowing if
  pricing ever changes materially.

### Bundle discount is now config, not code (Jul 2026)

`billing_pricing.BUNDLE_DISCOUNT` (module-count → whole-dollar discount) was
a hardcoded constant; per direct instruction it's now editable from General
Settings without a deploy, same pattern as every other super-admin-tunable
number in this app.

- **`platform_settings.get_bundle_discount_schedule(db)` /
  `update_bundle_discount_schedule(db, schedule)`** — reads/writes a
  `bundle_discount_schedule` key in the existing JSONB singleton (no
  migration). Falls back to `billing_pricing.BUNDLE_DISCOUNT` (now just the
  SEED DEFAULT) when unset. `update_...` **replaces the whole table** (not a
  merge — the UI always sends every row) and validates every key/value is a
  non-negative integer.
- **`billing_pricing.py` stays a pure, DB-free module** — `bundle_discount()`
  and `price_for()` both take an optional `schedule` override param instead
  of reaching into the DB themselves, so they're still trivially unit-
  testable with no session. Callers that have `db` (`routers/billing.py`'s
  `/quote` and `/checkout-session`, which thread it through to
  `stripe_client.create_checkout_session`) fetch the live schedule and pass
  it down; `price_for_addon` is untouched (never discounted, so there's
  nothing to override).
- **Overflow beyond the highest configured row** falls back to that row's
  discount (generalises the old hardcoded "cap at 4 modules" rule to
  whatever's actually configured — so a future 5th/6th priced module needs
  no code change here, just a new row filled in).
- **Discount is clamped to the subtotal** in `price_for()` — a super-admin
  typo in the (now-editable) schedule can't produce a negative checkout
  total.
- **UI**: `SuperClubs.jsx`'s General Settings modal, a "Bundle discount
  schedule" section under Billing — 6 number inputs (module-count → $),
  rows 5-6 pre-wired but inert today (only 4 priced bolt-on modules exist),
  saved via the existing `PATCH /club-admin/super/general-settings`
  (`GeneralSettingsUpdate.bundle_discount_schedule`, popped out and routed to
  the dedicated setter rather than the generic `_INT_KEYS`/`_BOOL_KEYS`
  `update_settings` path, since it's a nested object).

### Bundle discount coupon fixes: `once` not `forever`, cached not re-minted (migration 153, Jul 2026)

Caught during live testing: two bugs in how the bundle-discount Coupon was
created at checkout.

- **`duration` was `forever`, should have been `once`.** Per direct
  instruction: the bundle discount is a one-time incentive for subscribing to
  several modules at once — it must apply to the initial payment ONLY. A
  renewal (or an add-on to an already-live subscription, which never gets
  the bundle discount at all — see above) must bill at full price unless a
  *separate* coupon is deliberately applied to that specific renewal.
  `duration=forever` was silently discounting every future renewal too.
  Fixed: `stripe_client._ensure_bundle_coupon` now creates the coupon with
  `duration="once"`.
- **A fresh Coupon was minted on every single checkout attempt** — even two
  identical attempts (e.g. a retry) produced two separate Coupon objects in
  the Dashboard, both showing 1 redemption, reading as duplicates. Fixed the
  same way `_ensure_product` already caches Stripe Products: `stripe_coupons`
  (migration 153, `discount_cents` primary key → `stripe_coupon_id`) reuses
  ONE coupon per distinct dollar amount instead of creating a new one each
  time. Keyed on amount alone since `duration` is fixed at `once` for every
  bundle coupon today — if duration ever becomes independently configurable
  per amount, key on `(amount, duration)` instead.
- **Stripe Coupon fields, for reference** (verified against Stripe's own API
  docs while fixing this): `duration` (`once`/`repeating`/`forever`) controls
  how many charges on ONE subscription get the discount once redeemed.
  `duration_in_months` (only with `repeating`) — on an annual plan,
  `duration_in_months=12` covers only the first invoice (same practical
  effect as `once`); `24` covers the first invoice PLUS the next renewal;
  generally `12 × N` covers N annual charges. `redeem_by`/`max_redemptions`
  are a completely different axis — they cap the coupon's overall
  availability (a deadline / a total redemption count across ALL customers),
  not how long the discount lasts on any one subscription. The Dashboard's
  "Redemptions" column is `times_redeemed`; "Expires" is `redeem_by`
  (blank = redeemable indefinitely, which is what every coupon this app
  creates uses — nothing sets `redeem_by`/`max_redemptions`).
- **Not built**: applying a coupon to an ALREADY-LIVE subscription ahead of
  its next renewal (`Subscription.modify(sub_id, discounts=[{coupon: ...}])`
  — takes effect from the next invoice the subscription generates) — no
  admin action for this exists yet, in BetterCricket or otherwise; today a
  coupon can only be attached at Checkout Session creation (the initial
  subscribe, or theoretically via `allow_promotion_codes` on a future
  Checkout — but the add-on flow above never redirects to Checkout at all,
  so a promo code has no entry point there either). Configurable
  duration/repeat-count for the BUNDLE discount specifically (vs the fixed
  `once` behaviour above) is also not built — flagged as an open question,
  not assumed wanted.

### A cached Stripe id belongs to ONE mode (migration 263, Aug 2026)

Reported live off the first real checkouts: `No such coupon: 'IBBpUgf0'; a
similar object exists in test mode, but a live mode key was used`, and a club
entering the code LEEDY got nowhere.

- **Nothing was wrong with the coupon. It was in the other Stripe mode.**
  Every Stripe object id (Coupon, Product, Customer, Subscription) exists in
  test OR live, never both, and the id itself carries no marker saying which.
  BetterCricket had three places holding one: `stripe_products` (152),
  `stripe_coupons` (153) and `discount_coupons.stripe_coupon_id` (156), all
  written while the box still ran test keys, all handed straight to the live
  API the day the keys changed. **The cache key has to include the mode**, or
  every discount on the platform dies at the key switch.
- **`stripe_client.stripe_mode()` reads it off the secret key** (`_live_` /
  `_test_` in an `sk_` or `rk_` key, else `unknown`). The two caches are keyed
  on `(key, mode)` — the old single-column PKs are gone, replaced by unique
  indexes, which is what the `ON CONFLICT` targets.
- **Existing rows are backfilled to `'unknown'`, deliberately not guessed.**
  A cached id can't be interrogated for its mode without asking Stripe, so
  `unknown` is a value no lookup matches and the object is simply re-created
  in the mode being used. The stale rows stay as history; the orphaned
  test-mode objects they point at cost nothing.
- **A discount coupon RE-SYNCS rather than refusing.**
  `discount_coupons.ensure_stripe_coupon` mints a fresh Stripe Coupon and
  stamps `discount_coupons.stripe_mode` whenever the stored mode isn't the
  one in use (NULL for every coupon predating this, so each re-syncs once, on
  first use). A code already given to a club therefore survives the key
  switch with no Super Admin re-creating the catalogue. Called from both
  redeem paths, NOT from `/quote` — a price preview does no Stripe call at
  all and shouldn't start creating objects.
- **A stale `organisations.stripe_customer_id` used to kill the whole
  checkout** ("No such customer" is a hard reject, not a fallback), so
  `create_checkout_session` checks the Customer resolves first and starts a
  new one if not; `handle_checkout_completed` re-stamps the org either way.
  **A transient Stripe error reads as "exists"**, so a wobble can't orphan a
  real club's Customer.
- **Not covered, and it can't be**: a club whose `stripe_subscription_id` was
  created in test mode has no live subscription to add modules to. That is a
  club that never really subscribed, not an id to repair.
- **Verified against a real Postgres** (migration 263 applied three times to
  a populated pre-263 table carrying the reported ids, the lifespan mirror
  landing on the same schema, both modes coexisting, the race-tolerant
  upsert still no-oping) and through the shipped functions themselves with
  Stripe stubbed: the stale rows ignored, live rows reused, one create per
  new object, and `ensure_stripe_coupon` re-syncing a NULL/test coupon while
  leaving an already-live one alone.

### Add-on pricing was still applying the bundle discount (Jul 2026)

Caught in live testing: adding modules to an already-subscribed club's
existing subscription (`preview_add_modules`/`add_modules_to_subscription`)
still discounted the prorated charge by the original bundle-discount amount,
contradicting the "no bundle discount on an add-on" rule documented above.
Root cause: the `duration=once` bundle coupon is only consumed by a
*regular* invoice — if it hadn't yet been applied to one (e.g. modules added
the same day as the initial subscribe, before the first renewal invoice),
it was still attached to the subscription and Stripe's proration engine
applied it to the add-on invoice too.

- **`stripe_client.preview_add_modules`** now passes `discounts=""` (the
  SDK's literal-empty-string form — an empty *list* is a no-op and still
  inherits the subscription's discount, confirmed against the SDK's own
  param typing) to `Invoice.create_preview`, so the preview never includes
  an inherited discount.
- **`stripe_client.add_modules_to_subscription`** calls
  `Subscription.delete_discount_async` before creating the new
  `SubscriptionItem`s, stripping any lingering coupon so the real
  `proration_behavior=always_invoice` charge matches the preview. Errors
  (nothing to remove) are swallowed — that's already the desired end state.
- **Per-module price breakdown**: `preview_add_modules` now returns each
  line item with `full_price` (the module's plain annual rate, from
  `billing_pricing.price_for_addon`) and `deduction` (`full_price` minus the
  prorated amount) alongside the existing `amount`, matched to
  `billing_keys` by position (both derive from the same
  `PRICED_MODULES`/`FANTASY` order). `AdminAccount.jsx`'s add-on summary
  shows, per module: full annual price → prorata deduction → charged today,
  instead of a single opaque prorated figure.

### GST via Stripe Tax (Jul 2026)

Caught in live testing: checkout never charged GST, because nothing in
`create_checkout_session` ever asked Stripe to calculate tax — a Dashboard
tax configuration alone does nothing without the API request opting in.

- **GST-exclusive per direct instruction**: the advertised prices (Core
  $399/yr etc.) are what BetterCricket keeps; GST is added ON TOP at
  checkout, not carved out of the advertised figure. Every `price_data` now
  sets `tax_behavior: "exclusive"` (both the Checkout Session line items in
  `create_checkout_session` and the add-on `SubscriptionItem`/preview items
  in `_addon_price_data_items`).
- **`automatic_tax: {"enabled": True}`** is set at Checkout Session creation
  (top-level, NOT nested under `subscription_data` — that param doesn't
  exist there, verified against the SDK while building this). It carries
  onto the resulting Subscription automatically, so renewals keep
  calculating tax with no further code. `SubscriptionItem.create` has no
  `automatic_tax` field of its own — `add_modules_to_subscription`
  re-asserts it via `Subscription.modify` on every add-on call (so a
  subscription created before this shipped still picks it up), and
  `preview_add_modules` passes it explicitly to `Invoice.create_preview` too
  (so the prorated preview is accurate even before that modify call runs).
- **No explicit `tax_code` set on our Products** — deliberately left to the
  account's own **Preset product category** fallback (Dashboard → Settings →
  Tax → Business information → "Digital products › Business and web
  services", already configured) rather than guessing a specific Stripe tax
  code in code. Revisit only if a specific module ever needs different tax
  treatment from the rest.
- **Still required on the Stripe side, not something code can do**: an
  active AU GST registration under Settings → Tax → Registrations — without
  one, `automatic_tax` calculates $0 tax regardless of `tax_behavior`.
- **The Account page's OWN quote preview for a brand-new subscription can't
  show the exact GST figure** — `billing_pricing.price_for()` is pure local
  math with no Stripe call (deliberately, so `/quote` stays fast with no API
  round trip for the common case), so it shows a "Plus GST, calculated on
  Stripe's secure checkout page" note instead of a number. The **add-on**
  preview (`preview_add_modules`) is different — it's already a live
  `Invoice.create_preview` call, so once tax is enabled its `total` already
  includes the real GST automatically, no separate note needed there.

### Account page — price summary stays in view while selecting (Jul 2026)

`AdminAccount.jsx`'s module list can run to 6 rows; stacking the price
summary below it (the original layout) pushed the summary — the part an
admin most needs while still picking modules — below the fold. Fixed with a
two-column CSS Grid (`grid-cols-1 lg:grid-cols-[1fr_320px]`) once at least one
module is selected (`hasSummary`): the module list + billing history stay in
the left column, the price summary becomes the right column with
`lg:sticky lg:top-6` so it stays in view as the list scrolls. Below `lg` it
falls back to the original single-column stack (a sidebar doesn't fit a
narrow screen). No backend change.

### Per-club override for testing (migration 151)

`platform_settings.billing_checkout_enabled` is all-or-nothing across the
whole platform — no way to let one club's Primary Admin through the real
Stripe flow while everyone else stays on the stub. `organisations.
billing_checkout_override` (nullable boolean) sits on top of it: **NULL**
follows the platform default (the normal case), **true** force-enables
checkout for that one club regardless of the platform default, **false**
force-disables it even once the platform default is switched on. Resolved by
`platform_settings.billing_checkout_enabled_for_org(db, org)` — the function
`require_billing_checkout_enabled` and `GET /club-admin/account/plan` both now
call, in place of the old platform-default-only `get_billing_checkout_enabled`
(that raw getter still exists, for the General Settings page itself and as
the fallback `billing_checkout_enabled_for_org` reads). `require_billing_
checkout_enabled` now depends on `get_current_club` as well as `get_db` so it
can resolve the caller's own club's override.

Super admin control lives on the **club**, not General Settings — a "Stripe
checkout (this club)" select (Platform default / Force ON / Force OFF) in
each club's edit panel in `SuperClubs.jsx`, saved via the existing `PATCH
/club-admin/super/clubs/{id}` (`ClubUpdate.billing_checkout_override`, a
plain column so the generic `setattr` loop in `patch_club` handles it with no
special-casing). Typical use: flip one real or test club to Force ON, run a
live checkout end to end, then flip the platform default on for everyone once
satisfied (the per-club overrides can stay — they only matter when the
platform default is off, or when someone still needs a specific club blocked).

## BetterCricket-managed discount coupons (migration 156, Jul 2026)

A full coupon engine, entirely owned by BetterCricket — per direct
instruction, **Super Admin never edits a Coupon by hand in the Stripe
Dashboard for this** (unlike the earlier bundle-discount coupon, which was a
simple cached single-purpose object). Every eligibility rule lives in
BetterCricket's own tables and is decided before Stripe is ever touched; the
corresponding Stripe Coupon is a pure sync target with no `redeem_by`/
`max_redemptions` of its own, so there's exactly one place a redemption is
judged valid.

- **`discount_coupons`** (the catalogue) + **`discount_coupon_redemptions`**
  (the audit trail and the "one live redemption per club per coupon"
  enforcement — a partial unique index on non-`revoked` rows, so a Super
  Admin's revoke frees the slot back up). A coupon has: `code` (typed in) +
  `display_name`; `discount_type` (percent | amount) + `discount_value`;
  `module_keys` (null/empty = every billable module, else restricted —
  mirrored onto Stripe's native `Coupon.applies_to.products`, reusing the
  SAME per-module Stripe Product `stripe_client._ensure_product` already
  caches for the add-on-module flow, so a covered/non-covered mix on one
  invoice is split automatically by Stripe); `redeem_window_*` (when the code
  can be entered at all); `new_signup_window_*` (only usable at a club's
  very first subscribe, and only if that subscribe falls in this range) and
  `loyalty_window_*` (only usable by a club whose original subscription
  start — `MIN(org_module_subscriptions.started_at)` — falls in this
  historical range) — **both optional and independent**, each restricting
  nothing unless at least one of its own bounds is set;
  `duration_mode` (once | repeating | forever, `duration_renewals` years for
  repeating → Stripe's `duration_in_months = 12×N`); `stackable_with_bundle`;
  `max_redemptions`; `active` (the deactivate switch — coupons are never
  deleted, so history stays traceable).
- **Financial-terms lock**: once a coupon has ≥1 non-revoked redemption,
  `services/discount_coupons.update_coupon` rejects changes to
  `discount_type`/`discount_value`/`module_keys`/`duration_mode`/
  `duration_renewals` — Stripe Coupons are themselves immutable on these
  fields after creation, and rewriting them out from under an
  already-redeemed club would silently change what that club was promised.
  Only `display_name`, the window dates, `max_redemptions`,
  `stackable_with_bundle` and `active` stay editable after that point; the
  Super Admin edit modal (`SuperCoupons.jsx`) greys those fields out and
  explains why once `redemption_count > 0`.
- **Two redemption flows, one rule engine**
  (`discount_coupons.validate_redemption`, called by both):
  - **New signup** — a club with no Stripe subscription yet, entering a code
    alongside their module selection. `routers/billing.py`'s existing
    `/quote` and `/checkout-session` both grew an optional `coupon_code` —
    `/quote` validates read-only and folds the discount into the preview
    numbers (`_apply_coupon_to_quote`, pure local math, no Stripe call, same
    as the rest of `/quote`); `/checkout-session` calls
    `redeem_for_new_signup` (writes a `pending` redemption row) and passes
    the resulting Stripe coupon id through to
    `stripe_client.create_checkout_session`'s new `extra_coupon_id`/
    `extra_stackable` params — Stripe natively supports multiple
    simultaneous discounts (`discounts` is a list on Checkout Session,
    Subscription and Invoice preview alike, confirmed against the SDK's own
    param typing), so a stackable coupon combines with the bundle discount;
    a non-stackable one **replaces** it outright (never diluted by the
    generic bundle schedule). If Stripe then fails, the `pending` redemption
    is revoked so a config hiccup on our side can't permanently burn a
    club's one-time code. `stripe_billing.handle_checkout_completed` reads
    `coupon_redemption_id` back out of the session's metadata and flips the
    row to `active` once the subscription is actually confirmed created.
  - **Already-subscribed, ahead of renewal** — a Primary Admin (self-serve,
    a new "Redeem a discount code" card on the Account page, separate from
    module selection) or a Super Admin (`force=True` on the new
    "Force-apply…" action in `SuperCoupons.jsx`, which skips the
    redeem-window/max-redemption checks but never "already redeemed" or
    "inactive") call `redeem_for_existing_subscription` →
    `stripe_client.attach_discount_to_subscription`. This is a genuine
    **fetch-then-append**, not an overwrite — `Subscription.modify`'s
    `discounts` param replaces the whole list, so blindly setting a new
    single-entry list would silently evict a different coupon redeemed
    earlier for the same upcoming renewal. Stripe applies a
    subscription-level discount starting at the **next** invoice the
    subscription generates, never retroactively — exactly "apply ahead of
    the renewal date", no proration or immediate charge triggered.
- **Not built**: a self-serve "browse eligible codes" list (deliberately —
  confirmed a typed-in code is the right UX, matching how a coupon code
  normally works); configurable per-coupon retry/grace period for a stuck
  `pending` new-signup redemption beyond the immediate Stripe-failure revoke
  above (a truly abandoned Checkout Session — the club navigates away
  without completing — leaves the redemption `pending` forever, which the
  "already redeemed" check treats as used; a Super Admin can manually revoke
  it via the Redemptions modal as the recovery path today).

## Public self-serve trial signup + ad attribution (v8.72.0, Jul 2026)

The Meta ad campaign's destination: the internal self-serve trial registration
(`routers/self_serve_trial.py`, previously Super-Admin-only) went public.
**`routers/public_self_serve.py`** (`/public/self-serve/*`, unauthenticated)
re-registers the SAME step handlers (they're plain coroutines; the auth gates
live on the internal router's constructor) via `add_api_route` for identical
steps, and hand-wraps only `status` / `verify-email/send` / `prepare` /
`verify-email/check` / `submit` where public behaviour differs. Still behind
the `self_serve_registration_enabled` platform flag (the whole router 404s
while it's off — merge-safe ahead of campaign launch). The internal
`/self-serve-trial/*` router is untouched.

- **Light guardrails (per direct instruction — auto-approve, no review
  queue)**: per-IP `rate_limit.enforce` caps on search/prepare/send/check/
  submit layered over the shared per-email limits (the email-only lockout was
  otherwise a public DoS vector on a victim's email); a honeypot `website`
  field on prepare+submit (non-empty → plausible fake success, nothing
  created); a minimum-fill-time check (`form_started_at`, <4s ⇒ generic 422,
  negative deltas ignored so clock skew can't false-reject). CAPTCHA
  deliberately NOT added (needs an account to provision; fast-follow if abuse
  appears). The OTP email step is the real gate.
- **Error tightening**: the public `verify-email/send` wrapper swallows the
  raw provider error (the internal route's "TIGHTEN BEFORE PUBLIC LAUNCH"
  note) → generic message; real error still logged. Known accepted public
  surfaces (documented in the router docstring): `verify-email/status` is an
  is-this-email-mid-verification oracle (low value); submit's 500 carries the
  org/user support reference on purpose.
- **Auto-login**: public submit mints the session cookie itself
  (`create_session_token`/`set_session_cookie` — the primitive the internal
  `login-as` endpoint documented as "what a future public flow will call") and
  returns `redirect: "/admin"`; replays re-login the same registrant. Sets
  `bs_pending_fresh_login` client-side so the setup wizard auto-open fires.
- **Attribution (migration 161)**: `organisations.signup_source`
  (`self_serve_ad` when the browser's first-touch had a campaign/click signal,
  else `self_serve_organic`; NULL for every non-public onboarding) +
  `organisations.signup_attribution` JSONB (the `visitor.js getAttribution()`
  payload, key-allowlisted + clipped server-side). Written best-effort AFTER
  the shared submit commits — an attribution hiccup never fails a
  registration. Signup timestamps come from `self_serve_idempotency_keys`
  (orgs have no created_at).
- **Meta Pixel / CAPI**: `meta_capi.py` refactored — generic `_send_event`,
  `send_lead_event` re-expressed on it, new `send_complete_registration_event`
  ($399/AUD, `self_serve_trial` category). Public `prepare` fires a
  server-side Lead (browser fires the matching pixel Lead with the shared
  eventId — a picked club is a lead even if they stall); public `submit`
  fires CompleteRegistration browser+server (the campaign's optimisation
  event) + GA4 `sign_up` + a `conversion` usage-event breadcrumb.
- **Frontend**: `/trial` (`pages/marketing/Trial.jsx`, in the OG map; its
  sitemap entry in `seo.py` stays COMMENTED OUT until full launch). HIDDEN
  while the flag is off (redirects to `/` — briefly flipped to
  public-with-contact-fallback on Jul 17, reverted the same day per direct
  request); flipping the flag on makes the page AND signup live with no
  deploy. Meta's ad-review crawler (Prineville/Luleå/Clonee data-centre
  IPs, carrying the ad UTMs) hits this URL when ads are created — reads as
  "visits" on the Usage page, not real users —
  hero-first single-CTA landing page opening `SelfServeTrialModal` with the
  new **`publicMode` prop** (NOT `public` — reserved word when destructured):
  switches the api.js family to `publicSelfServe*`, sends honeypot/
  fill-time/attribution/visitorId/meta on the wire, skips the admin-only
  sync-log polling + login-as button, success screen → redirect to `/admin`
  after ~1.2s (lets pixel beacons out). ViewContent fires ref-guarded (once
  per visit, StrictMode-proof).
- **Ad → lead-score report**: `GET /club-admin/meta-ads/ad-signups`
  (routers/meta_ads.py) — every org with `signup_source`, its attribution,
  trial/paid modules (via `twenty_sync._module_split`), and the CACHED
  `marketing_clubs.engagement_score` via LEFT JOIN on `existing_org_id`
  (never a live `_engagement()` per row; an org registered while Twenty was
  unconfigured has NO MarketingClub row → "not yet scored" in the UI). Panel
  on `SuperMetaAds.jsx` with per-campaign rollup + cost-per-signup.
- **Launch preconditions (config, not code)**: flip
  `self_serve_registration_enabled` ON; set a real `email_provider` (defaults
  to `console` — OTP never sends!) + the SPF/DKIM/DMARC DNS still pending per
  the Public Domain note; Twenty configured so `push_self_serve_registration`
  lands the Hot-100 Lead. Rate limiter is in-memory single-process (fine for
  the single-uvicorn deploy).
- **Local-dev quirk** (not prod): `Base.metadata.create_all` doesn't add the
  `gen_random_uuid()` server defaults some raw-SQL migrations set (e.g.
  `org_module_subscriptions.id`), so a fresh ORM-created DB needs those
  defaults added by hand before the lifespan module backfill runs.

## Meta Ads HQ — Club Selected stage, stale "last updated", undercounted registrations, per-campaign pacing (migration 200, Jul 2026)

Four fixes to `/admin/super/meta-ads`, from live feedback.

- **New "Club selected" funnel stage.** `compute_funnel()` used to jump
  straight from `landing_page_views` to `leads` ("Started registering
  (Meta-reported)") — the same click-a-club moment, but only Meta's own
  self-reported number. A new `get_club_selected_count()` counts distinct
  Meta-driven visitors who fired the wizard's `club_prepared` beacon (same
  signal `get_selected_clubs`/`get_searched_clubs` already use, scoped to
  Meta traffic via `_META_VISITOR_SUBQUERY`) and `compute_funnel()` now takes
  it as a `club_selected` param, inserted as its own stage between
  `landing_page_views` and `leads`. It's a real, ours-not-Meta's count of a
  genuine buying signal — picking a club even without finishing — tracked
  even for visitors who dropped off immediately after.
- **"Last updated" was frozen after the first refresh of the day.**
  `meta_ad_snapshots.created_at` is set once on INSERT; `upsert_snapshot`'s
  `ON CONFLICT DO UPDATE` never touched it, so every later same-day refresh
  (the daily job, a manual "Refresh now") updated the numbers but not the
  timestamp the page reads for "Last updated". Migration 200 adds
  `updated_at` (backfilled from `created_at`), `upsert_snapshot` now sets it
  to `NOW()` on both the INSERT and the `DO UPDATE` branch, and
  `get_latest_summary` reads it back instead of `created_at`.
- **"Free trial registrations" undercounted real completions.**
  `get_registration_count()` only counted a signup if its
  `signup_attribution.utm_content` exactly matched an ad hand-mapped in the
  hardcoded `AD_DESTINATIONS` dict — a new ad/creative built in Ads Manager
  needs its `utm_content` added there by hand before a real registration
  through it counts, and until then it silently reads as if nobody
  registered. Added `CAMPAIGN_UTM_NAMES` (each campaign's own canonical
  `utm_campaign` string, identical across every ad in it per
  `docs/meta-ad-campaign-self-serve.md` §4's naming convention) and a shared
  `_attribution_matches_campaign()` that counts a signup if EITHER its
  `utm_content` is mapped to this campaign OR its `utm_campaign` matches the
  campaign's own name — the latter needs no AD_DESTINATIONS entry, so a
  brand-new ad counts correctly the moment it's built off the right
  destination-URL template. `get_registration_count()` and the ad-signups
  report (`routers/meta_ads.py::ad_signups`) both route through this one
  function now instead of two hand-matched checks that could disagree.
- **Headlines/pacing notes judged every campaign against the CURRENT one's
  plan.** `CAMPAIGN_BUDGET_AUD`/`CAMPAIGN_LENGTH_DAYS` were flat constants
  fed into `build_insights()` and the KPI "Spend $X of $750"/"~30 days from
  launch" display regardless of which campaign the header's picker had
  selected — so switching to an older, finished campaign (a different real
  budget per the campaign doc) judged its pacing against the current
  campaign's $750/30-day plan instead of its own, producing an "Overspending
  the budget pace" / "Under-pacing" headline that didn't apply to the
  campaign actually on screen. New `CAMPAIGN_PLANS` (campaign_id →
  (budget, length_days)) + `_campaign_plan()` resolve the ACTIVE campaign's
  own numbers; `get_latest_summary` threads them through everywhere the
  flat constants used to be, falling back to `CAMPAIGN_BUDGET_AUD`/
  `CAMPAIGN_LENGTH_DAYS` for a campaign not yet added to the map. The
  per-endpoint `days` lookback defaults (registration funnel, selected/
  searched clubs — a report window, not a budget figure) are untouched.

### Counting-since cutoff + broader registration matching (migration 201, Jul 2026)

Follow-up the same day: the "Club selected" stage above (17) read LOWER
than "Started registering (Meta-reported)" (20, 117.6% "continued"), and the
registration-wizard funnel showed "Club selected" (25) higher than "Club
searched" (13, 192.3%) — both impossible in a real funnel, the tell that
early/test traffic before the campaign was actually clean was still baked
into every number. Separately, "Completed registrations" read 1 when it
should have read 2 (two real signups, "Alvie" and "Altona North"), per
direct correction.

- **A super-admin-settable "counting since" cutoff** excludes data from
  before it out of the on-site funnel/table numbers AND Meta's own campaign
  insights — but deliberately NEVER the "Free trial registrations" KPI,
  which always counts every real completed registration however long ago it
  happened (a genuine registration must never disappear from the books just
  because the reporting window reset). `platform_settings.get_meta_ads_since`/
  `set_meta_ads_since` store an ISO datetime in the existing JSONB singleton
  (key `meta_ads_counting_since`, no schema migration needed for the setting
  itself). `meta_ads.py` resolves it into a `_counting_since` ContextVar
  alongside the active campaign (`_use_active_campaign` now sets both) so the
  many no-`db` helper functions can read it via `_since()`.
- **DB-side windows**: `_SINCE_LOWER_BOUND` — `GREATEST(NOW() - (:days *
  INTERVAL '1 day'), COALESCE(:since, '-infinity'::timestamptz))` — replaces
  every `NOW() - (:days * INTERVAL '1 day')` bound across
  `_META_VISITOR_SUBQUERY`, `get_club_selected_count`,
  `get_registration_step_funnel`, `get_selected_clubs`, `get_searched_clubs`
  (both the beacon/ack/registration sources and the meta-visitor detection
  subquery they all embed). A cutoff only ever narrows the window, never
  widens it past the requested `days` — `GREATEST` always picks the more
  recent bound.
- **Meta-side numbers** use `_date_range_params()`: the ordinary
  `date_preset: maximum` when no cutoff is set, else a `time_range` from the
  cutoff's DATE (Meta's insights API has no hour precision, unlike our own
  usage_events) through today. Threaded into `fetch_campaign_totals`,
  `fetch_per_ad`, `fetch_daily_trend`, `fetch_ad_daily_trend` — so a cutoff
  resets Meta's own impressions/clicks/LPV/spend/leads too, not just the
  on-site funnel. These come from STORED snapshot rows on ordinary page
  load, so a cutoff set purely via migration/lifespan-seed doesn't visibly
  change them until the next `run_snapshot()` (the daily job, or Refresh
  now) — the UI's own "Reset from…" control (below) triggers one
  immediately so the change is visible without waiting.
- **Migration 201** seeds the initial cutoff (2026-07-28 06:00
  Australia/Perth) once, guarded by a SEPARATE `meta_ads_counting_since_seeded`
  marker rather than by whether the value itself is present — so a super
  admin later clearing the cutoff from the UI (back to unfiltered lifetime
  numbers) can't have it silently reinstated by the next app restart
  re-running the idempotent lifespan mirror.
- **UI**: a "Counting since {time} (Perth)" line under the campaign picker
  in `SuperMetaAds.jsx`'s header, with "Reset from…" (a `datetime-local`
  input, submitted as Perth-offset `+08:00`) and "Clear". Backed by `GET`/
  `POST /club-admin/meta-ads/counting-since` — POST re-runs `run_snapshot`
  (best-effort, like Refresh now) before returning the fresh summary, and
  the frontend re-pulls every panel (`load()`) since the DB-windowed
  numbers change immediately regardless of the Meta re-pull's success.
- **Registration matching broadened a third way.** `_attribution_matches_campaign`
  now also accepts a plain Meta click signal (a fb/ig/meta `utm_source`, or a
  facebook/instagram `click_source`) as a last-resort match, alongside the
  existing exact `utm_content`/`utm_campaign` checks — a genuine
  Meta-driven registration shouldn't silently vanish from the count just
  because its UTM tags don't exactly match a hand-maintained mapping. In
  practice only one campaign has ever been live at a time, so "a Meta click
  happened" is a good enough stand-in for "it was THIS campaign" once the
  more precise checks come up empty. `get_registration_count` remains
  completely unwindowed by the counting-since cutoff (unchanged from the
  fix above). **If a real registration still doesn't count** after this
  (e.g. its `signup_attribution` is genuinely null — no UTM/click signal
  captured at all), the existing manual `+`/`-` adjustment on the "Free
  trial registrations" KPI card (with a note) is the documented way to
  correct it — it was already built for exactly this "our tracking didn't
  capture it" case, not a new addition here.

### The cutoff over-applied to the lead tables, a conflated Meta "leads" figure, and a shared-IP rate-limit bug (Jul 2026)

Immediate follow-up, from live feedback on the fixes above: "Clubs
selected"/"Clubs searched" had emptied out to the cutoff window when they're
meant to be a standing follow-up list, "Club selected" (14) read LOWER than
Meta's own "Started registering" (20, 142.9% "continued"), and the wizard
funnel showed "Club selected" (18) higher than "Club searched" (13,
138.5%) — backwards for a funnel where selecting requires searching first.

- **The "Clubs selected"/"Clubs searched" TABLES are no longer windowed by
  the counting-since cutoff.** Only the funnel STAT counts
  (`get_club_selected_count`, `get_registration_step_funnel`, Meta's own
  campaign insights) reset with the cutoff — these two tables are a
  follow-up/lead-management list ("who do we chase up"), and a super admin
  resetting the funnel to a clean baseline still wants every past lead
  listed, not dropped from view. `_meta_visitor_subquery(bound)` is now a
  factory so both a since-aware (`_META_VISITOR_SUBQUERY`, funnel stats) and
  a plain days-only (`_META_VISITOR_SUBQUERY_PLAIN`, the tables) variant
  share one template instead of drifting. The router/frontend default window
  for these two endpoints also grew from 30 to 365 days (server caps at
  730, new `TABLE_DAYS_DEFAULT`/`TABLE_DAYS_MAX` in `routers/meta_ads.py`) —
  "I want to see all the clubs selected and searched for."
- **Meta's own "leads" figure (campaign["leads"], "Started registering
  (Meta-reported)") was conflating two funnel stages.** `_LEAD_ACTION_TYPES`
  used to sum BOTH the genuine `lead` action (fired at club-pick, step 1)
  AND `complete_registration` (fired at the final step) into one number —
  double-counting every completer and inflating the figure above our own
  real "Club selected" count even once both were scoped to the same date
  window. Trimmed to just the Lead action types; CompleteRegistration stays
  tracked separately via `get_registration_count()` (unchanged), never
  blended back in.
- **`/track-step`'s rate limiter was keyed by IP, starving beacons across
  visitors who share one.** The likely cause of "more people selected a club
  than ever searched for one" in the wizard funnel: `handleClubClick`
  (`Trial.jsx`) only ever fires `club_prepared` for a click on a search
  result row, which by construction can't happen without `club_searched`
  having already fired for that same visitor — so a genuine per-visitor gap
  shouldn't be possible. But `/track-step`'s limiter was keyed by
  `client_ip(request)` at 60/hour, shared across every beacon type AND every
  visitor behind that IP — and Meta ad-click traffic disproportionately
  arrives via the Facebook/Instagram in-app browser's own proxy and mobile
  carrier CGNAT, both of which put MANY distinct real visitors behind one
  apparent IP. A busy shared IP could exhaust the quota, silently dropping
  a *different* visitor's beacon (fire-and-forget, no retry) — and because
  `club_searched` fires earlier and more often per visitor than the
  one-shot `club_prepared`, it's the more likely of the two to get starved
  out from under someone else's traffic first. Now keyed by `visitor_id`
  when present (falling back to IP only when storage is blocked and no
  visitor_id was sent) — unlike `/search` (which genuinely needs an IP-based
  cap to protect the CA upstream API regardless of who's asking), `/track-
  step` only ever writes to our own DB, so there's no abuse-surface reason
  to keep the shared-IP keying that was causing this.

## Usage tracking — session duration, time on page, visitor journeys (migration 165, v8.75.0, Jul 2026)

`usage_events` had club, page, and UTM/campaign granularity but nothing on how
long a visitor actually stayed anywhere, and no built-in ordered-journey view
(see the earlier "Data Source Topology"-style investigation this session did
into what the table could and couldn't answer). Both gaps are closed without
a new table:

- **`usage_events.time_on_page_ms`** (migration 165) is filled by a new
  `page_exit` event, not by the existing `page_view` row. `usePageView.js`
  fires it via `navigator.sendBeacon` on `pagehide` and on `visibilitychange`
  going hidden (covers both real navigation/tab-close and a mobile browser
  backgrounding the tab without ever firing `pagehide`), and again on every
  route change to close out the page just left. `POST /usage/event/exit`
  (`routers/usage.py`) writes it; clamped server-side to 24h so a stuck timer
  (laptop asleep, tab backgrounded for hours) can't skew an average.
- **Session duration is computed on read, not stored.** A "session" is a
  visitor's `page_view` timestamps grouped on a ≥30-minute gap (the
  industry-standard boundary); duration is the span between first and last
  page_view PLUS the final page's own `time_on_page_ms` (matched by visitor +
  path + nearest-following `page_exit`) — without that tail, a single-page
  bounce session always reads 0ms even if the visitor read the page for a
  minute before leaving. `GET /club-admin/usage/session-duration` returns
  avg/median session length, a length distribution, and top pages by average
  dwell time; surfaced as a new "Engagement" panel on the Usage page.
- **`GET /club-admin/usage/journey?visitor_id=`** reconstructs one visitor's
  actual ordered page-path, split into sessions, each step carrying its
  matched dwell time and whatever UTM/campaign tag was on it — every other
  Usage endpoint aggregates across visitors, this is the only one that
  replays a single visitor's route through the site. Surfaced automatically
  on the Usage page: typing (or deep-linking with) a visitor UUID into the
  existing search box now shows a "Visitor journey" panel above the regular
  aggregate views.
- **Campaign-capture fix, found while building this**: a club outreach
  link's UTM tags are applied by `comms.py::_apply_utm`, keyed on `utm_id`
  (the recipient club's `marketing_clubs.utm_code`) plus the sending
  campaign's own `utm_source`/`medium`/`campaign`/`content`. The old skip
  logic gated the WHOLE campaign-params block behind "does the link already
  have `utm_source=`" — so a template that hand-placed
  `{{utm_source}}={{utm_code}}` (a documented per-club merge-var pattern)
  silently dropped `utm_campaign` too, even though only `utm_source` was
  actually already present. Now each UTM key is checked and added
  independently. Separately, `usePageView.js` used to send only the
  visitor's STICKY first-touch `utm_campaign` (`getAttribution()`) — a
  returning visitor clicking a brand-new campaigned link would have that
  click's `utm_id` recorded fresh but its `utm_campaign` reported as
  whatever their first-ever visit happened to carry. `visitor.js` gained
  `getCurrentUtm()` (a non-sticky parse of the CURRENT URL's own UTM params),
  which now wins over the first-touch snapshot whenever present.

## Uploaded scorecard missing from the public Games page (migration 169, v8.76.1, Jul 2026)

Reported: a scorecard uploaded via `/admin/upload-scorecard` for Legana
Cricket Club never showed up on `/legana-cricket-club/games`.

**Root cause**: the upload form (`AdminScorecardUpload.jsx`) lets Grade be
left as "— none —" (Season is required, Grade isn't). `GET
/organisations/{id}/results` (`organisations.py::get_org_results`, what
`GamesPage.jsx` calls, and it always applies a season filter — it
auto-selects the most recent season on load) derived season purely by
joining `grades gr ON gr.id = g.grade_id` then `seasons s ON s.id =
gr.season_id`. With `grade_id` NULL, both `gr` and `s` came back NULL, so the
season filter (`s.id = :season_id ...`) could never match — even though
`manual_games.season_id` itself is a required, always-set column. The row
was silently excluded under every season, on every page load.

**Also found while fixing it**: the same query's org-ownership check had a
bare `g.source = 'manual'` clause with no organisation check at all, so
literally any club's manual game read as "ours" on every other club's
results/W-L-D headline — a cross-club data leak. `games.py::list_games`'s
`api_games` sub-query had the identical clause even though manual games are
already fetched separately and correctly (org-scoped) by
`_fetch_manual_games_as_list` in the same function, so that endpoint doubly
leaked (any org's manual games) and duplicated (this org's own manual games,
once via each path). `manual_entries.py`'s upload-time duplicate-check
(`check_scorecard_duplicate`) had the same grade-required join, so it also
couldn't detect an existing grade-less manual game on re-upload.

**Fix**: `v_effective_games` now carries `season_id`/`organisation_id`
columns directly (migration 169 — for `games`, derived via
grade→season same as before; for `manual_games`, its own always-set
columns), appended at the end so no existing consumer (none `SELECT *`
against this view) is affected. `get_org_results`, `_club_results`
(aggregations.py, the headline W/L/D — explicitly mirrors `get_org_results`
so the two agree) and `check_scorecard_duplicate` now join season off the
view's own `season_id` and check `g.organisation_id = :org_id` instead of
the blanket `g.source = 'manual'`. `list_games`'s `api_games` sub-query now
scopes to `g.source = 'api'` only, since manual games are handled entirely
by the separate, already-correct fetch. Verified end-to-end against a real
local Postgres instance (base schema + the view + sample cross-org data)
before shipping — confirmed the bug reproduced against the old query and no
longer does against the new one, including a regression check that an
ordinary graded API-synced game is unaffected.

**Anti-pattern reminder**: a manual game can legitimately have no
`grade_id` (Grade is optional on upload) but always has a `season_id` and
`organisation_id` — don't derive either one by joining through `grade_id`
for a `v_effective_games` row; read the view's own `season_id`/
`organisation_id` columns instead.

## Uploaded scorecards log — edit/undo from the upload page (v8.76.2, Jul 2026)

`/admin/upload-scorecard` (`AdminScorecardUpload.jsx`) was a one-shot flow —
upload, review, import, done — with no way to see or revisit what had already
been uploaded from that page short of finding it in the general-purpose
"Manual Games" tab on `/admin/manual-entries`. It now has its own list,
scoped to just the scorecards that came through the photo-upload flow.

- **`GET /club-admin/manual-entries/games`** (`list_manual_games`) gained
  `is_photo_upload` (whether `manual_games.extracted_payload` is set — the
  AI reader's saved match+innings JSON, present only for a photo upload, not
  a hand-typed manual game) and `created_by_name` (a `LEFT JOIN users`,
  mirroring the pattern `list_audit` already used). The list keeps the full
  `extracted_payload` blob out of the response (popped after computing the
  boolean) — it's only needed in full when a single game is reopened via
  `GET /games/{id}` (already returned it; unchanged).
- **Jump back in ("Edit")**: since `extracted_payload` is the exact
  `{match, innings}` shape the review screen already edits in memory,
  reopening a past upload replays it through the SAME review UI used at
  upload time — no separate "already-imported" editor to keep in sync. The
  WK-catch split (`wkByPid`, not itself persisted) is reconstructed from the
  saved `fielding_stats.catches_wk` per player. Saving calls `PATCH
  /games/{id}` instead of `POST /games`; a fresh photo read always clears
  `editingId` first so it can't accidentally overwrite a prior edit target.
- **Duplicate check gained `exclude_id`** (`check_scorecard_duplicate`) — 
  editing an already-saved game used to flag the game against itself as a
  "possible duplicate" on the same date, since the query had no way to
  exclude the row being edited.
- **Delete** reuses the existing `DELETE /games/{id}`; the list's own footer
  points at `/admin/manual-entries#audit` for restoring a deleted or edited
  entry rather than re-implementing undo/restore on this page too — one
  audit trail, not two.
- Verified end-to-end against a real local Postgres instance: the
  `is_photo_upload`/`created_by_name` join, and the `exclude_id` fix to the
  duplicate check, both before shipping.

## Scorecard reader — multi-format, PDFs, fielding column, eval set (v8.80.0, Jul 2026)

`scorecard_ocr.py` (the Upload Historical Scorecard reader) taught about more than
the WACA-style scorebook, prompted by a Toowoomba club's archive (1976 scorebook
pages + a 1993 TCA "Official Summary of Match" form). Full how-to-improve-it doc:
**`docs/scorecard-reader-eval.md`**.

- **Prompt knows three format families**: the two-page scorebook, the association
  match-summary form (one club's side only + opposition as a bare "10/111" totals
  line → an innings with totals and an EMPTY batting list), and "anything else,
  note the layout in read_notes". Also warned about: tally strokes in extras
  boxes (the numeral total column wins), wickets-first "7/164" notation,
  two-digit years → 1900s, two-day matches (first day = match.date), and
  **pre-1980 Australian 8-ball overs** → new `match.balls_per_over` (reconcile's
  overs check + `overs_to_balls(o, balls_per_over)` honour it; DB storage is
  unchanged — overs stay as written on the card).
- **Result inference is the ONE allowed deviation from transcribe-only**: blank
  result box + completed innings that decide it → model may fill `result` and
  set `result_inferred`, which the review screen flags ("worked out from the
  scores, check it"). Everything else stays faithful-transcription-only.
- **New `innings[].fielding` section** ({name, catches, catches_wk, stumpings,
  run_outs}) for cards that credit fielders separately from dismissals (OWN
  CATCHES column, W/K = keeper). Attached to the innings where that side was
  FIELDING. The extract endpoint adds these names to the roster-suggestion set;
  the review screen shows them as an editable, player-matchable table, and
  import merges them with the dismissal-derived fielding by **max per stat** so
  the same catch seen both ways counts once. Re-editing a saved upload seeds
  this table from the saved `fielding_stats` so a re-save can't drop
  column-sourced fielding.
- **PDF uploads work end to end**: `guess_media_type` recognises `.pdf`,
  `extract_scorecard` sends PDFs as native `document` blocks (no rasterising;
  anthropic 0.40.0 passes the dict through), the file input accepts them and
  previews show a file chip. Mind the API's ~32MB request cap for huge scans.
- **Eval harness** `python -m app.scripts.scorecard_eval <cases_dir>`: local
  (never committed) case folders of scans + a verified `expected.json`; only
  keys present in the truth file are scored, rows matched by normalised name.
  Run before/after any prompt/schema/model change to the reader — that's the
  training loop, since the model itself never learns from uploads.
- **Tracked-fields toggles (v8.80.1, migration 184)**: a "This card tracks"
  panel on the review screen (balls faced / 4s & 6s / maidens / bowler
  wides+no-balls). Unticked → the column is hidden AND imports as **NULL, not
  0** — `manual_batting_innings.fours/sixes` and
  `manual_bowling_spells.maidens/wides/no_balls` went nullable (the synced
  tables always were, so every effective-view reader already copes). The
  pydantic defaults stay `Optional[int] = 0`, so the CSV import and hand-typed
  manual-game form (which omit rather than null the fields) are byte-for-byte
  unchanged; only an EXPLICIT null means "not recorded". Toggle defaults come
  from whether the reader found any value; re-editing a saved upload recovers
  the choice from the stored rows' nulls. The prompt also tells the model to
  leave untracked stats null, never 0.
- **Card-error vs misread flags (v8.80.3)**: `reconcile()` now returns
  `list[dict]` `{kind, text}` instead of `list[str]` — `kind` is `card_error`
  (the card's OWN figures don't reconcile: batting≠total, wickets≠FOW count,
  bowling≠total, overs mismatch — a decades-old scorer slip, fix-or-keep) or
  `misread` (a value the READER likely got wrong: dismissal bowler not in the
  analysis, boundaries>runs, keeper catches>catches — worth fixing). The reader
  still transcribes faithfully; nothing auto-corrects. Frontend
  (`AdminScorecardUpload.jsx`) renders two boxes: amber "the original scorecard
  doesn't add up here (correct below or import as-is to keep the card's
  figures)" and red "likely misreads — worth fixing above", and the import
  confirm spells out the keep-or-fix choice (button reads "Import, keep
  original" when only card errors remain). The eval prints `w["text"]`. Old
  plain-string warnings tolerated on the frontend via `asWarn`. Per direct
  request: read exactly what the card says, flag where it's wrong, let the user
  choose.
- **Name cross-referencing across the card (v8.80.2)**: the standout
  handwriting win, from a real correction pass — the same person is written
  many times (batting order, bowling analysis, a "c Smith" catcher, a "b Jones"
  wicket-taker, fall-of-wickets) with wildly varying legibility. The prompt now
  says to read EVERY occurrence and use the clearest as the true spelling, then
  use it everywhere: the **bowling analysis is authority for bowler names** (a
  dismissing bowler is always one of the analysed bowlers), the **batting order
  authority for batter names** — but never collapse two players who merely share
  a surname (N Ziebell ≠ R Ziebell). `reconcile()` backs it with an advisory:
  `_name_close` (surname-level `SequenceMatcher`, ≥0.6) flags a dismissal bowler
  whose name isn't among that innings' analysed bowlers — the exact
  "S Willingslow" that's really "G Wittingslow" case. Worked examples baked into
  the prompt (Wittingslow, Houser/Heuser, Pascoe initials). Verified truth file
  for the 1976 Railways match kept locally as the first eval golden case.
- **Roster matching = the historical-import engine (v8.80.1)**: the extract
  endpoint now runs card names through `import_ingest.match_players` (the same
  exact → middle-initial-tolerant → "Surname Initial" form → blocked
  SequenceMatcher pipeline BetterImport and the Merge Players fuzzy pairs
  use) instead of the old bespoke `_suggest_player` token matcher.
  Auto-fill policy: exact hits, plus a single candidate at confidence ≥0.9
  (the unique "G Evans" surname+initial case — parity with the old matcher);
  everything else ships as `result["match_info"]` candidates, which
  `PlayerSelect` shows as a one-click "CLOSE MATCHES" group with confidence %
  at the top of every picker (batters, bowlers, dismissal fielders, own-catches
  rows). `_suggest_player` still exists for `_replace_game_children`'s
  import-time FOW/partnership name resolution — unchanged on purpose.

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
