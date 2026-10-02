# Archive: betterselect-selection-and-nets

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: BetterSelect selection board, squads, availability, rules, nets sessions and check-in, player kit and date of birth.
Read the distilled rules first: `docs/dev-notes/guides/betterselect-selection-and-nets.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L4592-4665 -->
## The Squads board's unassigned side is three pools (v9.46.0, Aug 2026)

Reported off BetterSelect → Squads: "the hidden people, people who have never
played are on the list… best to filter out inactive, so just active players who
haven't been assigned. Maybe another group with potential fill-ins, with the 1
and 3 year filter. Also maybe if they are made inactive that automatically get
taken out of any squad."

- **UNASSIGNED IS A WORKING LIST, NOT A REMAINDER, and that is the whole
  change.** It was every player with `squad_team_id IS NULL`, thinned by a
  client-side "played ≤ N years" dropdown — so a club's whole history sat in the
  column a selector actually reads. It is now active players who are still
  around and unsquadded; everyone else is FILED, not hidden: `Potential fill-ins`
  (played before, but not lately) and `Not yet played` (no appearance yet).
  Nothing is dropped and a card in any pool still drags into a squad, which is
  what makes filing defensible where hiding would not be.
- **The split runs on the club's own `dormancy_months`, read off the
  availability-matrix payload** — the same definition of "still around" the
  matrix and `selection_pool` already use. The board had invented its own
  3-year number, so it disagreed with every other BetterSelect screen about who
  had dropped off.
- **A never-played player gets their OWN pool rather than being hidden**, because
  `playedWithinYears` deliberately keeps them ("a new manual add") and both
  readings are right: a brand-new signing must be pickable, and a synced name
  who never turned out is noise in the main list. Two facts, two places.
- **The fill-in reach only offers windows WIDER than the dormancy boundary.**
  With a 24-month window, "≤ 1 yr" and "≤ 2 yrs" can only ever answer "nobody" —
  anyone inside the window is already in Unassigned. So the options are built
  from `dormancy_months` (24 → 3/5/10/any, 12 → 2/3/5/10/any) rather than being
  the fixed ladder. Same call `ageFilterOptions` makes: a control that can only
  answer "nobody" is worse than none.
- **INACTIVE IS OFF THE BOARD, AND MARKING SOMEONE INACTIVE NOW CLEARS THEIR
  SQUAD** in the same write (`routers/players.py::update_player_profile`, and
  the profile importer). Gated on the request actually SETTING the status, so
  editing an already-inactive player's phone number doesn't quietly move them.
  Reactivating deliberately does NOT re-file them — which squad they belong in
  now is the club's call. `auto_assign_suggest` skips them for the same reason:
  one half taking them out while the other puts them back is the two disagreeing.
- **The count of what's held back is shown, with a `Show inactive players`
  filter** — the board says "N inactive not shown" rather than a club wondering
  where somebody went. Bulk add never offers an inactive player at all, since
  the assign would only be undone.
- **Fixed while here: `services/directory.py::set_squad` was the one squad write
  that never mirrored into `team_members`**, so a squad set from the Clubhouse
  Directory left the "Squad" filter on Availability and Selection disagreeing
  with the board. Mirrored in raw SQL to keep that module's stated
  out-of-the-ORM-graph posture.
- **Also fixed: `SquadColumn` spread `onCardDragStart`/`onCardDragEnd` onto its
  column `<div>`**, so React warned about unknown DOM props on every render.
  Pre-existing; found because the browser suite asserts no page errors.
- **Verified against a real Postgres** (29 checks through the shipped route
  bodies: the squad and its `team_members` mirror both cleared, an unrelated
  edit to an already-inactive player leaving them alone, squad + inactive in one
  request leaving no stale mirror row either side, reactivation not re-filing,
  auto-assign skipping an inactive player, the Directory write mirroring on
  assign/reassign/unassign and staying idempotent) **with a control run**: with
  the fix stashed, 8 of them fail on exactly the reported behaviour. Driven in
  **Chromium** (33: the three pools and who lands in each, the two secondary
  ones opening collapsed, the reach control never offering a window inside the
  dormancy boundary, opening it to ≤ 5 yrs pulling a 4-year-dormant player in, a
  fill-in card dragging into a squad, the inactive hint and the Show-inactive
  escape hatch, the card badges, Bulk add, no page errors).
- **Noticed, NOT fixed**: the module header's action cluster (Auto-seed /
  Auto-assign / Fix order / Manage squads / New squad) measures 693px inside a
  `shrink-0` wrapper and pushes the page 319px sideways at 390px — the trap the
  Selection-header note below describes. Confirmed pre-existing by re-measuring
  with this change stashed (709px either way); the board's own columns don't
  overflow. It lives in the shared `ModuleLayout` header, so fixing it reaches
  every module surface.
- **Not built**: nothing changes what `GET /club-admin/players` returns — it is
  still the club's whole roster and the board does the filing. The AFL silo's
  own player-status write (`routers/afl/players_admin.py`) is untouched, since
  AFL has no BetterSelect squad board.

<!-- END original CLAUDE.md L4592-4665 -->
<!-- BEGIN original CLAUDE.md L4752-4881 -->
## The batting order is dragged, and two flags a coach sets during the night (migration 284, v9.63.0, Sep 2026)

Reported off a club's Thursday nets, run from an iPad: getting the right people
into the batting spots after finding them in the check-in list was slow; there
was no way to say who was padding up; and a captain on selection night or
somebody leaving at seven had to be walked up the queue by hand.

- **POINTER EVENTS, NEVER THE HTML5 DRAG API, and that is not a preference.**
  iOS Safari fires no `dragstart`, `dragover` or `drop` at all, so on the device
  this screen is actually run from a `draggable` attribute gives nothing and the
  list cannot be reordered. `dragOrder.js` is pointer-based, which covers a
  finger, an Apple Pencil and a mouse with one code path.
- **`touch-action: none` ON THE HANDLE IS WHAT MAKES A TOUCH DRAG START.**
  Without it the browser claims the gesture as a page scroll before the first
  `pointermove` ever arrives. It is on the GRIP rather than the row on purpose —
  the rest of the row keeps its ordinary scrolling, so a thumb can still flick
  past a twenty-name queue. Playwright cannot simulate that arbitration, so the
  suite MEASURES it off the computed style rather than inferring it from a mouse
  drag working.
- **THE THRESHOLDS ARE SNAPSHOTTED AT PICK-UP, IN PAGE COORDINATES.**
  Re-measuring after each swap moves the very threshold that caused it and the
  row oscillates between two slots; and a client-space snapshot shifts under the
  auto-scroll that a queue taller than an iPad needs, so the row stops advancing
  the moment the edge scroll takes over.
- **THE ROWS REORDER UNDER THE FINGER — there is no lifted ghost following it.**
  One thing moves instead of two, there is no copy to keep in step with a
  re-render, and the row that has just landed is the row under the finger.
- **A DRAG HOLDS THE POLL OFF, on the same in-flight counter a write uses.** A
  poll landing mid-drag adopts the server's older order and pulls the row out
  from under the finger. The preview is also held until the write comes back, or
  the row snaps to where it started and forward again a moment later, which
  reads as the drag having failed.
- **ONE LIST FROM THE NETS DOWN, which is what makes the drag worth having.**
  The separate "On now" card and "Up next" list are one "Batting order" now, the
  first `nets` rows tinted and badged `NET n` — so putting the right player in a
  batting spot is the same gesture as moving them up the queue, rather than a
  separate act on a separate card. Who is in, and who is padding up, moved up
  beside the clock where a player reads them from the nets.
- **THE ARROW KEYS MOVE A FOCUSED GRIP.** Dragging is a pointer gesture and a
  screen reader has no pointer; without this the order would be unreachable for
  anyone not using one. That is also what let the two chevron buttons go.
- **PADDING UP IS AN EXPLICIT FLAG, NOT THE NEXT N IN THE QUEUE.** The person who
  pads up is whoever the coach actually spoke to, which on a real night is
  routinely somebody further down the list. It is SPENT BY A ROTATION at both
  ends — the group coming out have batted, the group going in have walked to the
  nets — and cleared when somebody is marked batted or leaves the rotation.
  Without that it slowly becomes a list of everyone the coach has ever spoken
  to; somebody further down must keep theirs through the same rotation, or the
  flag could never be set ahead.
- **PRIORITY RECORDS A FACT AND MOVES NOBODY.** A tick that silently re-sorted
  would undo the order the coach had just dragged into place, and with three
  captains flagged on a selection night nobody could say who was really first.
  So ticking it ASKS — move them up now, or mark the row — every time. The
  reason goes into the existing `note`, the field that already holds what
  somebody said on the way in, pre-filled so a "bowling only" typed at check-in
  can't be written over. Unlike padding up it survives a turn and a spell out of
  the rotation, because "leaving at seven" is still true afterwards.
- **"BAT NEXT" IS THE FRONT OF THE LINE FOR THE NEXT TURN, NOT THE FRONT OF THE
  LIST.** While a turn is under way the top `nets` names are IN, and dropping
  somebody above them swaps out a batter mid-knock — worse, the next rotation
  marks the new arrival as having batted when they never went in. `netsBusy`
  covers the turn-over-but-not-yet-rotated state for the same reason. Dragging
  is exempt: that is the coach saying "swap them", explicitly.
- **THE PAD GLYPH IS A PAIR, AND THE PAIR IS THE WHOLE POINT.** A SINGLE pad at
  16px is a blob: rendered side by side at 16/22/40/72, every one — outlined or
  solid, straps inside or out — collapses into a pill, a pair of curly braces or
  a stack of blocks, and the strap tabs that make it a pad at 72px are the first
  thing to go. The first cut shipped as `{}` on the row, and a helmet drawn to
  replace it read as a mushroom; both were caught by screenshotting the real
  screen, not by reading the code. Two pads side by side is a silhouette
  nothing else in the set has — domed tops, a strap band, scalloped feet — and
  it survives all the way down. **Filled, with the strap cut as an EVEN-ODD
  hole**: a 1.8px outline at 16px leaves nothing inside it, and a notch drawn in
  the background colour is wrong on the light theme and wrong again over the
  tinted button, where a hole shows what is actually behind.
- **THE STRAP BAND IS WHAT STOPS IT READING AS PAUSE**, which is two rounded
  bars and sits on this very screen a few inches above. Without the band the two
  swap at 16px — measured by rendering them in the same sheet, which is the only
  way that kind of collision shows up.
- **EVERY STATE IS A WORD AS WELL AS A TINT** (`NET n` / `PADDING UP` /
  `PRIORITY`), the rule this file already records — the green and amber here
  separate by ΔE 7.2 under protanopia. A row can legitimately be two states at
  once, which no single colour can say, so the pills are always drawn and only
  the LEFT EDGE takes a precedence (in a net, then padding up, then priority).
- **The row action group WRAPS onto its own line** rather than squeezing the
  name: seven 34px targets plus a name do not fit on one 390px line, and this is
  run from a tablet in portrait as often as a laptop. Row numbers and the grip
  read at `--pb-dim`, never `--pb-faintest` (1.64:1).
- **Verified against a real Postgres** (`backend/verification/verify_net_batting_order.py`,
  46 checks through the shipped route bodies: migration 284 applied three times
  to a populated pre-284 table and the lifespan mirror landing on the same
  schema, both statements read out of the real sources rather than retyped,
  every pre-284 row reading false, the flag cleared by a batted mark and by
  leaving the rotation and not resurrected by either coming back, a rotation
  spending it at both ends while somebody further down keeps theirs, priority
  surviving both and moving nobody, an over-long reason capped, the drag's own
  write landing whole, a foreign id ignored without losing anybody, a name the
  sending device never knew about keeping its place, and every cross-club
  refusal) **with a control run**: 20 fail against the previous commit.
- **Driven in Chromium** (`frontend/verification/verify_net_batting_order_browser.mjs`,
  58: the drag with real mouse-generated pointer events AND with synthetic
  touch ones, `touch-action` measured off the computed style, the exact order on
  the wire, no poll running while the finger is down and the poll returning
  after, the arrow keys, the exact params for every flag, a person in a net not
  also reading as padding up, the dialog writing NOTHING until answered, a
  dismissal sending nothing, both bat-next rules, and no overflow at 390px)
  **with a control run**: it reports the six missing parts by name rather than
  dying on the first absent locator.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN.** Both suites read the new
  keys through `.get`/presence checks so an absent feature is REPORTED rather
  than raising on the first `KeyError` or missing locator — otherwise the other
  forty checks say nothing.
- **PLAYWRIGHT'S `**` GLOB DOES NOT CROSS A `?`.** A glob route for the live
  poll silently loses `…/live?since=3` to the catch-all, which hands the screen
  `{}` and takes it down — a page crash a long way from the route that caused
  it. The suite routes by REGEX throughout.
- **Three of the first cut's checks were measuring the harness rather than the
  code**: `NAMES.map(att)` passes `(value, index)` and the stub had them the
  other way round, so every name was a NUMBER and the screen died inside
  `Avatar`; an index hardcoded from the original order, after an earlier drag
  had already moved the list; and "the padding-up line does not name them"
  scoped to the whole hero, where the in-the-nets line right above legitimately
  does — that one passed with the bug and failed without it.
- **NOTICED, NOT FIXED**: `adopt` will take any payload, so a malformed one from
  a server mid-deploy takes the screen down rather than leaving the last good
  state on it. Pre-existing, and swallowing it could hide a real fault. The
  session-register CSV is also unchanged — neither flag is in it, since padding
  up is transient and the reason behind priority already rides in the note
  column the register carries.

<!-- END original CLAUDE.md L4752-4881 -->
<!-- BEGIN original CLAUDE.md L4882-4951 -->
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

<!-- END original CLAUDE.md L4882-4951 -->
<!-- BEGIN original CLAUDE.md L4952-5133 -->
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



<!-- END original CLAUDE.md L4952-5133 -->
<!-- BEGIN original CLAUDE.md L5961-6122 -->
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

<!-- END original CLAUDE.md L5961-6122 -->
<!-- BEGIN original CLAUDE.md L6191-6345 -->
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

<!-- END original CLAUDE.md L6191-6345 -->
<!-- BEGIN original CLAUDE.md L6346-6449 -->
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

<!-- END original CLAUDE.md L6346-6449 -->
<!-- BEGIN original CLAUDE.md L12119-12320 -->
## Three kit fields that do not live in one place (migration 289, v9.69.1, Sep 2026)

Asked for as "store player shirt number, shirt size and pants size in the
BetterAdmin Directory", with the question of whether to reserve the lot for
BetterAdmin as an upsell. **The three are not the same kind of fact and the
split is the answer**, per direct instruction after the options were put:

- **`players.shirt_number` is a PLAYING attribute and is CORE.** A team sheet, a
  lineup post and a scorecard all want it, and a club running nothing but
  BetterStats has every one of those surfaces — so gating it would leave a Core
  club unable to put a number on its own team sheet.
- **`fee_members.shirt_size` / `.pants_size` are KIT MANAGEMENT and are
  BetterAdmin's.** They sit on the person spine because **a coach, a scorer and a
  canteen volunteer all get a club polo and `players` has nowhere to put their
  size** — which is also why they could never have gone on the player record.

- **NUMBERED 289, AFTER TWO COLLISIONS.** `origin/main` reached 287
  (CricketStatz as the record for a season) and then 288 (configurable
  notifications) while this was in flight, and two migrations sharing a
  revision id break Alembic outright. **Re-check `origin/main` at the moment
  you merge, not only when you first number one** — this file has recorded that
  trap three times and it still cost two renumbers in one session.
- **`admin` IS NOT AN ENTITLEMENT KEY, and the first cut of the gate was wrong
  for every club on the platform.** It is the BILLABLE umbrella;
  `MODULE_GROUPS[MODULE_ADMIN]` grants `fees`/`comms`/`merch`/`crm`, and
  `ALL_MODULES` — which `org_entitled_modules` filters `module_overrides`
  through — does not contain it. So `org_has_module(club, "admin")` is **False
  for every club there has ever been**, and the gate would have withheld kit
  sizes from the clubs that had paid for them. The Clubhouse nav has always
  gated on the child keys for this reason. **Caught by the verification, not by
  reading the code.** `ADMIN_MODULE_KEYS` is the frontend's copy of the same
  four, since `hasModule('admin')` is false there too.
- **A SIZE IS WITHHELD FROM A CLUB WITHOUT THE MODULE, never sent and hidden**
  — the `visible_age` rule. `kit_sizes` on the payload says which, and a write
  naming one is refused with the ordinary 402 upsell shape. The NUMBER rides on
  that same payload either way, which is the whole point of the split.
- **THE 402's MODULE NAME COMES FROM `BILLABLE_MODULE_NAMES`, NOT
  `MODULE_META`.** The umbrella has no `MODULE_META` entry at all, so reading it
  there names the module "admin" to a club. **Noticed, not fixed**:
  `require_module("admin")`'s own message has exactly that gap, and the backend
  name ("BetterClubhouse") disagrees with the frontend's ("BetterAdmin") — a
  rename that only went half way, and its own change.
- **NOTHING NORMALISES A SIZE TO A VOCABULARY.** A club buys from whichever
  supplier it buys from, and "Youth 12", "2XL" and "34" are all answers somebody
  has to be able to type; a controlled list leaves a club sizing in centimetres
  with nowhere to put the truth. `services/player_kit.py` is the one rule for all
  three writers (the profile, the Directory, the bulk importer) — trim, collapse
  inner whitespace, cap the length.
- **A NUMBER IS TEXT**, the call `afl_player_game_lines.jumper_number` already
  makes: a club that issues "07" or "00" means it, and an integer column quietly
  makes them 7 and 0.
- **The Directory writes the number through the PLAYER route**, not a second
  copy of the column — so the number on the Directory and the number on the
  player's own profile are one field. Present-and-blank clears, ABSENT leaves
  alone, on all three, which is what lets one panel save without touching
  another.
- **The bulk importer takes it**, because a club assigning numbers does it in a
  spreadsheet and the note this file already carries says a profile field left
  out of that list goes missing with nothing to say so. Something too long to be
  a shirt number is **REPORTED, not clipped** — a silently clipped value reads on
  the team sheet as a number the club chose.
- **Verified against a real Postgres**
  (`backend/verification/verify_player_kit.py`, 43 checks through the shipped
  route bodies: migration 289 applied three times to a populated pre-289 schema
  and the lifespan mirror landing on the same columns, "07" and "00" surviving,
  a non-player holding a size, a Stats-only club still numbering its players and
  never receiving a size, the 402 and its shape, a size minting the person row
  for a read-through player, cross-club, and the importer's three cases) **with
  a control run**: 30 of the 43 fail against the previous commit.
- **A CHECK THAT PASSES ON A COLUMN THAT NEVER HELD ANYTHING IS NOT A CHECK.**
  Four did on the first cut — "a present blank clears it" is trivially true of a
  build with no column, and "the Stats-only payload lacks the size keys" of a
  build that never emits them. Each is paired now: the set AND the clear, the
  entitled club's payload AND the other one's.
- **A HARNESS THAT TAKES A LIFESPAN TABLE'S `CREATE` ALONE LEAVES A TABLE THAT
  MERELY LOOKS RIGHT.** Every column added since one of those tables was written
  lives in its own ALTER further down the lifespan, so the harness has to pull
  those too — the suites share one database and none of them drops the schema.
  `verify_cricketstatz_import.py` met exactly that: it creates
  `player_achievements` IF NOT EXISTS, found the one this harness had left
  behind, and died on a missing `season_end` that had nothing to do with the
  code it was checking. **The ALTER is matched to its CLOSING DOUBLE QUOTE, not
  to the first quote of any kind**: a default value is single-quoted inside the
  Python string (`"... DEFAULT 'volunteer'"`), and stopping there truncates the
  statement to a syntax error.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN.** Every read of a new key
  goes through `.get`, every import of the shipped code through `load()`, and
  every new module attribute through `getattr` — and the suite BAILS after the
  migration section when anything is missing, reporting it, rather than reaching
  the first `None.something`. Found by running the control: it died on
  `players_router.update_player_profile` and said nothing about the other forty
  checks.
- **Verified with the importer** (the suite is 68 checks now) **with a control
  run**: with the number resolution and the two size writes neutered, 7 fail —
  including the second record a sheet of kit sizes would mint.
- **THE MEMBER CSV IMPORT TAKES ALL THREE (v9.69.1)**, asked for straight
  after. `name | email | mobile | category | roles | shirt size | pants size |
  shirt number`, through the ONE shared importer both the Directory and
  BetterFees Members already call.
- **THE THREE COLUMNS DO NOT WRITE TO THE SAME TABLE, so a number has to find a
  player before it means anything.** The sizes land on `fee_members`; the number
  lands on `players.shirt_number` or nowhere. Resolution is the matched member's
  own link, else an exact name match against the club's players — and **a name
  held by two players resolves to NEITHER**, the refuse-to-guess rule, because a
  number written onto the wrong Jack Smith is worse than a number not written.
  Every skip is reported in the preview, with the reason, BEFORE the club
  commits.
- **A NEW PERSON ROW IS LINKED TO THE PLAYER OF THAT NAME, and without it the
  feature is broken for the case it exists for.** A club uploading kit sizes for
  its players would otherwise mint a second, unlinked record for every one of
  them and the Directory would show the whole club twice. Only on an
  unambiguous match to a player with no person row yet — the same row
  `ensure_for_player` would have made. An EXISTING member row is never
  re-pointed at a player, which is the direction that could steal a record.
- **THE GATE IS ON THE SHEET'S OWN COLUMNS, not on what a row happens to carry**,
  so a club without BetterAdmin is refused at the PREVIEW rather than after some
  rows have quietly lost a value. `columns_used` is what the router reads;
  `routers/fees.py` calls the same guard, where it can never fire (that router is
  behind the fees module and holding any of the four IS holding the bundle) —
  two callers of one importer must not disagree about what a sheet may carry.
- **A BARE `shirt` COLUMN IS CLAIMED BY NEITHER.** It is as likely to be a size
  as a number, and guessing wrong puts a size in a number field.
- **A SHEET THAT SAYS NOTHING ABOUT A FIELD LEAVES IT ALONE**, the importer's own
  existing rule, extended to the sizes rather than worked around.
- **`BetterClubhouse` IS GONE FROM EVERY NAME A CLUB READS (v9.69.1).** The
  backend's `BILLABLE_MODULE_NAMES[MODULE_ADMIN]` still said it while the
  sidebar said BetterAdmin, so a 402 named a module that no longer exists.
  **`modules.module_display_name(key)` is now the ONE place the backend names a
  module** — `MODULE_META` first, `BILLABLE_MODULE_NAMES` second — which also
  fixes `require_module("admin")`'s own message, since the umbrella is a bundle
  of four keys and has no `MODULE_META` entry to read. Changelog entries keep
  the old name: they are the record of what happened at the time.

### The minutes go out on the club's own letterhead (v9.69.0)

Asked for alongside: a club logo and a header band in the club's colours on the
Committee Meeting Minutes.

- **THE COLOURS COME FROM `theme_config`, NOT `primary_color` / `accent_color`.**
  That legacy pair themes nothing any more (the v8.70.2 note), so reading them
  would head the document in colours the club has not used for years.
- **A SHADED PARAGRAPH, NEVER A TABLE, and the existing suite is what settled
  it.** A one-row table lets each half of the band carry its own fill and is the
  obvious way to draw a two-colour one — and it makes the letterhead the
  document's FIRST table, which broke 11 checks in
  `verify_minutes_download_browser.mjs` that read the meeting details out of
  `tables[0]`. Word counts it, a reader announces it, and anything walking the
  document's tables meets a band before it meets the meeting. Two stacked
  single-colour paragraphs give the club both colours with none of that, and the
  PDF draws the identical pair of rectangles. **That suite passes unchanged,
  107/107.**
- **THE CREST IS CONVERTED TO JPEG IN THE BROWSER, and that is the whole reason
  it can be embedded at all.** A JPEG goes into a PDF verbatim under
  `/DCTDecode` and into a `.docx` as an ordinary media part; a PNG would need a
  decoder in `textDocs.js`, which has no dependency and is not getting one. The
  canvas does the decoding the browser already knows how to do.
- **THE CANVAS IS FILLED WHITE FIRST.** A club crest is almost always a
  transparent PNG and JPEG has no alpha, so without it every logo lands as a
  black box on a white page.
- **`clubLogoJpeg` RETURNS NULL RATHER THAN THROWING** — a crest that will not
  load, an external URL that taints the canvas, a club with no logo. The band
  draws on its own and the document is still worth having.
- **`header` is its own argument to `docBlocks`, not the head of `blocks`**,
  because `title` is ALSO the PDF's `/Info` Title: emitting a title block instead
  would print the club name twice.
- **`downloadPdf`'s own `header` variable is the REPEATING TABLE HEADER** and had
  to be renamed — a document `header` and a table header are two different things
  in one function.
- **The image objects are numbered LAST**, after the pages, because `images` is
  only complete once every content stream has been written; a page whose
  `/Resources` omits an XObject it draws renders **blank with no error anywhere**.
- **PLAYWRIGHT MATCHES ROUTES MOST-RECENTLY-REGISTERED FIRST.** The crest route
  is registered AFTER the `**/api/**` catch-all, not before it. The other way
  round, the catch-all answers the `<img>` with `{}`, the canvas has nothing to
  draw, and every "no crest" check passes for the wrong reason.
- **`unzip` GLOB-MATCHES THE MEMBER NAME ITSELF**, so `[Content_Types].xml` reads
  as a character class and matches nothing even with no shell involved. The
  brackets have to be escaped.
- **Driven in Chromium** (`frontend/verification/verify_minutes_letterhead_browser.mjs`,
  38 checks against the real meeting room: the band in the club's OWN colours read
  out of both files, the crest as a real JPEG media part with a relationship the
  drawing references and as a `/DCTDecode` XObject the page's `/Resources` names,
  the band not being a table, a club with no crest and a crest that 404s both
  still getting their band with no dangling part, and every xref row pointing at
  the object it claims) **with a control run**: 21 of the 38 fail against the
  previous commit.

### Sponsors: written up, not built (Sep 2026)

Rockingham Mandurah want their sponsors more prominent, and two of them hold
naming rights on specific grounds. Per direct instruction the implementation is
a separate piece of work; the finding is in
**`docs/sponsor-prominence-and-venue-naming-rights.md`**. The short of it:
**more templates is not the fix**. A sponsor reaches 2 of the 62 template
components, always as one of exactly two identical logo boxes in a 56px footer
(`ScSponsorFooter`'s `const slots = [0, 1]`), and the event templates take a
sponsor's NAME as a string and cannot draw a logo at all. A tier on
`org_sponsors` reaches every template; a `sponsor_venues` table keyed on the
club's OWN distinct `games.venue` / `fixtures.venue` strings (picked, never
typed, so there is no fuzzy match to fail silently) is what makes a ground
naming right expressible.

<!-- END original CLAUDE.md L12119-12320 -->
<!-- BEGIN original CLAUDE.md L12985-13037 -->
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

<!-- END original CLAUDE.md L12985-13037 -->

## v9.102.3: inactive players out of the selection pool

The selection board's Available pool listed players marked inactive and tagged them with a squad (legacy `team_members` rows plus recent appearance team names). `assemble_selection` now sends `squads: []`, `squad_team_id: None` and `squad_match: False` for `status == 'inactive'`, leaving tier and `gender_ok` untouched so BetterIQ still flags a saved inactive pick. `AdminSelection.jsx` drops `is_inactive` from `available` and `SelectionFilters` shows "N inactive not shown". Inactive players already in the saved XI still render in their slot. No data was changed: old `team_members` rows for inactive players remain until a repair script clears them.

## v9.102.8: same-day picks that do not clash

Reported by Applecross: a player in both Colts and T20 Div 1 could not be picked for both when the games fall on one day and are played back to back, and a junior and a senior game on the same day had the same problem. The board allowed one XI per date. A higher grade could take a player from a lower one (a call-up that silently dropped them from the lower XI on save); a lower grade could never take a player from a higher one (409).

`services/selection_clash.py` now judges each same-date pair. `compatible_fixtures(db, org, fx, other_ids)` returns the other fixtures that can be played alongside `fx`, and both readers use it: `selection_pool.assemble_selection` (the board) and `routers/selection.set_selection` (the save, which re-judges rather than trusting the browser). Rules, in order: a multi-day game (`end_on` after `played_on`, or a grade that only plays `two_day`) is always a clash; one junior grade against a non-junior grade is always playable whatever the clock says; both start times known means playable unless the estimated games overlap (T20 210 minutes, one day 480, unknown format 480, so an unknown only makes a pair look more clashing); a missing start time with no junior/senior split stays a clash (fail closed, the old behaviour). Junior comes from `grade_labels.org_grade_category_sets`, format from `org_grade_format_sets`, both keyed on the sponsor-stripped grade name.

A playable pair is not a clash. The pool row gets `also_in: [{fixture_id, team_name, start_time, gap_minutes, tight, reason, text}]` and leaves `clash`, `clash_detail` and `clash_blocks` alone, so the call-up cascade and demotions are untouched. The save skips playable pairs in both the block and the call-up, so the player stays in both XIs. `AdminSelection.jsx` toasts "also in ..., adding to both" and `SelectionViews.jsx` draws an amber "Also in" line on the Dual rail and Tray cards (`selectionMeta.alsoIn`, `inAnotherXI`, `alsoInLine`). The "In another XI" filter and Unselected filter use `inAnotherXI`, so they count both kinds. Auto-fill (`okToPick`) and BetterIQ's `_best_available_xi` skip a player with `also_in`: a suggestion never double-books anyone.

Found while testing: `ToastProvider` returns a new `toast` object on every render, and showing a toast re-renders it. `AdminSelection.load` had `toast` in its `useCallback` dependencies, so any toast fired from `tapPlayer` (call-up, "marked unavailable", the new note) re-ran `load()`, refetched the fixture and reset the unsaved slots to the saved lineup, losing the pick. `load` now reads `toast` through a ref and depends on `fixtureId` only. About 88 other places list `toast` in a hook dependency array; none were changed.

Proof: `backend/verification/verify_selection_same_day.py` (53 checks, real Postgres, shipped `assemble_selection` and `set_selection`). The control run against the previous commit fails 19 of them on exactly the reported behaviour (a Colts pick of a T20 player gets 409, a T20 pick silently drops the player from Colts, no `also_in`) and passes the old call-up and block checks. `frontend/verification/verify_selection_same_day_browser.mjs` (13 checks, production build, API stubbed with a real `assemble_selection` dump in `fixtures/selection_same_day.json`) asserts the exact PUT body, no demotions, and no overflow at 390px; its "PUT carries Alex" check failed before the toast fix.

## v9.102.9: pool search ignores the recency window

Applecross could not find a player on the selection board. He last played in Summer 2022/23 and the board opens on "Played ≤ 3 yrs" (`yearsF`, default 3), which hides him with nothing on screen saying why. In `AdminSelection.jsx` the recency filter is now skipped while the search box has text. Inactive players are still left out of the pool (rule 4), so a search never reveals one. The same window on the Players, Teams and Availability screens is unchanged. The Applecross player's missing nets entry is a separate cause: both screens list only `is_player` players, so a record with "Is player" switched off is absent from both whatever the search says.

Proof: `frontend/verification/verify_selection_same_day_browser.mjs` adds a player who last played four years ago to a real `assemble_selection` dump. He is absent by default, found by searching his surname, and gone again when the search is cleared. With the one-line change reverted, "searching finds Daniel" is the single check that fails.

## v9.102.10: the selection board autosaves a draft (migration 317)

Reported: leaving the Selection screen after moving players in and out lost all progress, because the only write was the Save button, a full replace of `fixture_lineups`. The ask: progress saves as it goes, and Save becomes a Confirm.

`fixture_lineups` stays the CONFIRMED XI. The matchday overview, votes, BetterIQ, `selected-players` and the public Lineups page all read it, so autosaving into it would publish a half-built side and run the call-up cascade (which deletes the player from the lower XI) on every tap. The draft is its own table, `selection_drafts` (`fixture_id` PK, `organisation_id`, `draft` JSONB, `updated_by`, `updated_at`), DDL once in `services/selection_draft_ddl.py` (alembic 317 and the lifespan both run it). `draft` holds `slots` (gaps kept, so an empty slot 3 stays empty), `captain_id`, `wicket_keeper_id` and `demotions` (each with `callup_id`, so the cascade is re-judged at Confirm).

Routes in `routers/selection.py`, all `MANAGE_SELECTIONS`: `GET /selection/{id}/draft`, `PUT` (upsert, never touches `fixture_lineups`, runs none of the clash, call-up or blocking-rule checks; only cleans the shape: ids that are not this club's players become empty slots, repeats are dropped, a captain or keeper not in the slots is cleared), `DELETE`. `GET /selection/{id}` is unchanged on purpose: BetterIQ shares `assemble_selection`, and a viewer without the capability is never handed a half-built side. `PUT /selection/{id}` (Confirm) deletes the draft in the same transaction, so a refused Confirm (409 clash or blocking rule) leaves the draft alone.

Frontend (`AdminSelection.jsx`): `dirty` is derived (`confirmSig` of the named XI, captain, keeper and the filtered cascade list differs from the loaded confirmed XI), not a flag, so putting everyone back reads "Confirmed" and deletes the draft. A change is written 600 ms after the last one. Writes are chained through `draftInflight`, so a delete cannot overtake a save, and `load()` and Confirm both wait for it. Leaving (fixture switch, route change, `visibilitychange` to hidden, `pagehide`) flushes the pending write with `keepalive`. A 5xx or dropped connection retries after 5 s; a 4xx does not. Restoring drops anyone no longer in the pool. The pending payload carries its own `fixtureId`: the effect that flushes on a fixture switch runs after the new `fixtureId` is in render scope, while `slots` still belong to the old fixture. `loadedFor` guards the autosave effect for the same reason. `canEdit` is read through a ref in `load` (`hasCapability` is not stable; `toast` rule 58 applies too).

Left as is: two selectors editing one fixture overwrite each other's draft (last write wins, "Last saved by" is shown); the matchday overview does not mark a fixture as having a draft.

Proof: `backend/verification/verify_selection_draft.py` (31 checks, real Postgres, shipped route bodies; control against the previous `selection.py` fails 22). `frontend/verification/verify_selection_draft_browser.mjs` (31 checks, real screen, API stubbed; control against the previous build fails 23, button read presence-safely). `verify_selection_same_day_browser.mjs` now presses Confirm instead of Save.

## v9.102.11: drafts are versioned, and the overview marks them

Closes the two follow-ups left by v9.102.10: two selectors on one fixture overwriting each other's draft, and the matchday overview not showing which fixtures had one.

`selection_drafts.version` (INTEGER, default 1; added to migration 317 in place, the branch was unmerged, with an idempotent `ALTER ... ADD COLUMN IF NOT EXISTS` for any database that ran the first cut) is bumped by every write. `PUT /{id}/draft` takes `base_version` (0 = the board saw no draft). With a base it is one `UPDATE ... WHERE version = :base RETURNING version`; with 0 it is `INSERT ... ON CONFLICT DO NOTHING RETURNING`. No row back means a 409 `draft_conflict` carrying the current `draft`, `version`, `updated_by` (display name or username) and `updated_at`, and nothing is written. Two simultaneous saves on one version therefore cannot both win. A board holding a draft that was confirmed or discarded away gets the 409 with `draft: null, version: 0`, never a resurrected row. `DELETE /{id}/draft?base_version=N` deletes only the version the caller saw (409 if another selector moved it on; a draft already gone is a no-op); the client sends it for both Discard and the automatic revert-to-confirmed delete. `GET /{id}/draft` returns `version` (0 when none). Confirm still deletes unconditionally: it is the explicit act.

`GET /selection/overview` adds `has_draft` and `draft_updated_at` per fixture (one `= ANY(CAST(:ids AS uuid[]))` query). Only a flag: the draft itself still goes only through the capability-gated draft route.

Frontend (`AdminSelection.jsx`): the version is read when a write is SENT (`draftVersion` ref), so a save queued behind another of ours carries the version that one produced. A 409 sets `draftConflict` and stops autosave (the effect returns while it is set). "Keep mine" adopts the server's version as the base and lets the effect send this board; "Use their version" calls `adoptDraft` (or `load()` when theirs is gone). The board polls `GET /draft` every 8 s and on `visibilitychange` to visible (`pollDraft`, a ref reassigned each render so it sees current state). It skips while a write is pending or in flight (`draftBusy`) or a conflict is showing. A version change on a board with nothing unsent (`draftSig === draftServerSig`) is adopted silently with an info toast; with unsent changes it raises the same conflict strip. `restoreDraft` is the one function that lays a draft onto the pool, used by `load` and `adoptDraft`. The overview shows "Draft, not confirmed" and the CTA "Continue draft"; its counts and status pill still describe the confirmed XI.

Still open: Confirm does not check for a newer draft (a selector who never polled can confirm over someone else's draft, which is then deleted); a conflict that happens during the keepalive flush on leaving is lost with the page.

Proof: `backend/verification/verify_selection_draft.py` now 55 checks (control against the previous router fails 22). `frontend/verification/verify_selection_draft_browser.mjs` now 54 checks (control against the previous build fails 17): pickup by a clean board, conflict with both choices and the exact base version on the wire, autosave stopped while unsettled, the draft vanishing elsewhere, the overview marker, 390px.

## v9.102.17: free-text "First Last" overrides show as "Last, First"

A `display_name_override` typed as "Damian O'Hara" listed by first name between the synced "Surname, First" rows in the Availability grid. `services/name_format.canonical_player_name` flips a comma-less two-word name to "Last, First" and leaves a comma name, a single token and three or more words alone (a middle name and a double-barrelled surname look the same). `Player.display_name` applies it on read, so nothing stored changes, and `formatPlayerName` in `frontend/src/lib/nameFormat.js` mirrors it. `availability.py` (`club_player_roster`, `availability_matrix`) now sorts in Python by `name_sort_key` because the SQL `ORDER BY coalesce(override, name)` still orders the raw text. Raw-SQL `COALESCE(display_name_override, name)` readers are not covered.
