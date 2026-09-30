# Archive: clubhouse-committee-and-plans

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Committee screen, meeting room, minutes, strategic plans, governance.
Read the distilled rules first: `docs/dev-notes/guides/clubhouse-committee-and-plans.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L5392-5894 -->
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
- **THE HEADER NO LONGER LINKS TO THE MANAGE SCREEN (v9.50.4).** Every one of
  its editors is mounted here, so `Manage meetings & positions` only ever took
  a reader to a second copy of what they were already looking at.
  `/admin/clubhouse/committee/manage` still exists and still renders — it is
  simply not offered as a destination from this screen any more.
- **Committee's buttons are Meetings (default), Plans, Documents, Calendar,
  Positions.** Every key lives in `st` (`cteMeetingsView` / `cteActionsView`),
  so a label can be renamed without moving anyone's view. **Positions is kept
  even though the brief's list did not name it** — dropping a working screen is
  not something a rename asks for.
- **NEVER DECLARE A COMPONENT INSIDE A RENDER (v9.51.1).** Reported: typing in
  the section search threw the caret out after ONE character and nothing landed.
  `Header` and `SubBar` were written as `const X = () => …` in the render body,
  so React saw a different element TYPE on every render and tore the whole
  subtree down and rebuilt it — taking the focused input with it. They are plain
  functions returning elements now, CALLED (`{subBar()}`) rather than mounted.
  **`fill()` cannot catch this**: it sets the value in one shot, so the suite
  types character by character and asserts `document.activeElement` is still the
  box after each one. Control run with the fix stashed: all five characters lost
  focus and only the first landed, exactly as reported.
- **ONE SEARCH PER SECTION, and it searches the SECTION rather than the list on
  screen (v9.50.9).** A box on Meetings that only filtered the visible meetings
  would answer the wrong question: a motion, an action or something minuted sits
  INSIDE a meeting. `meetingMatches` reads the agenda (title, description,
  outcome notes), the minutes, the private notes, every motion and every action
  raised from the meeting; the register, the actions list and the templates rail
  narrow to the same query. It sits on its own line in `SubBar`, below the
  section buttons and above any second row of them, and `matches()` is the one
  case-folded rule so no two sections search differently.
- **The PLAN TREE narrows and the DASHBOARD BESIDE IT DOES NOT.** A branch is
  kept when anything under it matches, and `railOpenFor` draws every level open
  while a query runs, or a match three levels down is found and then hidden
  behind two carets. The filtering is for DRAWING only — `groups`, `themesIn`
  and `objectiveOrder` stay whole, or a reorder would renumber against a
  filtered list. The dashboard is left whole deliberately: its figures are a
  proportion of the plan, and a filtered "2 of 3 objectives on track" is a
  different, wrong number.
- **`query` on `TasksTab` works the way `view` does**: a caller drawing its own
  box passes it and the tab stops drawing one, rather than two that disagree.
  Its category / objective / assignee / overdue filters stay either way, since
  they ask different questions. `DocumentsTab` and `CalendarTab` take `query`
  defaulting to `''`, so the manage screen — which passes none — is unchanged.
- **A section change clears the query**, since a query typed against meetings
  means nothing against documents. Positions is deliberately not searched.
- **A harness that reaches for "the first input on the page" now gets the search
  box** — `check2.mjs` had two such selectors and typed a theme name into it.
  Address a form's own field.
- **AN ACTION AND A MOTION BOTH COME OUT OF A MEETING, so they live under
  Meetings** — All Meetings | Actions | Motions | Meeting Templates, with
  Actions keeping its own List | Board | Timeline row underneath. The
  `Motions & Actions` tab and its `cteMaView` key are gone; `cteMaView` is read
  in exactly one place, to carry a stored `cteTab === 'motions'` onto the
  button it became, so somebody sat on that tab when the change landed arrives
  on Meetings rather than on a tab that no longer exists. Picking any Meetings
  button rewrites `cteTab`, so the carry-over applies once.
- **Plans has no button row: it IS the Strategic Plans tree.** Themes and
  Objectives were two more readings of the rows the tree already holds, and
  everything they offered (create, edit, delete a theme or an objective) the
  tree offers too. **`PlanTab`'s `section="themes"` / `"objectives"` branches
  are therefore mounted nowhere** — the manage screen renders the tab
  UNCONTROLLED, which is its own By plan / All work view, not either of those.
  They are kept rather than deleted so the screens can come back without being
  rewritten; do not assume they are exercised by anything.
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
- **A THEME BELONGS TO ONE PLAN (migration 275), and 232's club-scoped pillar
  was wrong.** 232 reasoned that a club's themes are stable across plans, so
  the same few could serve the 12-month plan and the 5-year one. Running it as
  a tree broke that in the worst way, and it was reported as data loss: a
  second plan drew the FIRST plan's themes, an objective added under one read
  as belonging to both, and deleting that theme from the second plan's tree
  deleted the first plan's objectives. `club_strategic_pillars.plan_id`,
  `ON DELETE CASCADE`. A plan owns its themes, a theme owns its objectives,
  and there is no linkage between one plan's hierarchy and another's.
- **The 275 backfill SPLITS rather than picking a winner.** A pillar whose
  objectives span several plans is copied once per extra plan and that plan's
  objectives re-pointed at its own copy, so every plan's tree survives intact.
  The split must run BEFORE the claim, or one plan takes the original and the
  others are left pointing at a theme that now belongs to someone else. A
  pillar with no objectives anywhere cannot be attributed and comes out of 275
  with a NULL `plan_id`; migration 276 below is what settles those.
  `services/pillar_plan_ddl.py` is the ONE copy both alembic and the lifespan
  mirror run, per the `vote_medal_ddl` rule; both statements are idempotent.
- **`upsert_objective` takes its plan FROM its theme.** A theme is the more
  specific of the two and is what the person picked in the tree, so an
  objective saved with a mismatched pair follows the theme rather than being
  refused. The objective form offers only the chosen plan's themes, and
  changing the plan clears the theme.
- **Deleting a PLAN takes its themes** (that is what belonging to a plan
  means), and since 276 their objectives too. Deleting a THEME can only ever
  reach its own plan's objectives.
- **The PANE adds the level below; the RAIL adds at the level you are on.**
  A plan's pane offers + THEME, a theme's + OBJECTIVE, which is the shape of
  plan → theme → objective. A plan draws the themes whose `plan_id` is that
  plan, empty ones included — the "draw every club theme when the plan is
  empty" and "draw an unused theme everywhere" rules are gone with 232's
  club-scoped pillar, and were how the reported leak got in.
  The plan an objective is added under is read off the THEME's own `plan_id`
  since 275 — never a positional fallback, since a theme in the wrong plan is
  the failure 275 exists to prevent.
- **THE TREE IS A DATABASE INVARIANT, NOT A CONVENTION THE SCREENS KEEP
  (migration 276).** 275 stopped one plan's tree leaking into another and left
  three states that still contradicted the model: a theme on no plan, an
  objective on no plan, an objective under no theme. `plan_id` on
  `club_strategic_pillars` and `plan_id`/`pillar_id` on `club_objectives` are
  all **NOT NULL** now, and the two objective FKs are **ON DELETE CASCADE** —
  `SET NULL` cannot coexist with `NOT NULL`, so the cascade IS the tree. There
  is nowhere for an orphan to go, which is the point: a plan and its themes and
  objectives are entirely separate from every other plan's.
- **`committee_tasks` / `meeting_motions` → `club_objectives` stays ON DELETE
  SET NULL, and that is the one rule not to relax.** Deleting a plan, a theme
  or an objective never deletes an ACTION or a MOTION — the work is kept and
  simply stops being linked. The suite asserts the referential action itself,
  not just that a row survived one delete.
- **276 CARRIES the unattributable rather than binning it.** A theme with no
  plan but real objectives under it, and an objective on no plan at all, go
  into a per-club plan named `Unfiled work`; an objective with no theme is
  filed under a `General` theme created inside its OWN plan, so carrying it can
  never move it between plans. The one row deleted is a theme with no plan AND
  no objectives, which holds nothing but a word. `services/plan_tree_ddl.py` is
  the ONE copy alembic and the lifespan mirror both run, in order, and every
  statement is idempotent.
- **The order of 276's steps is load-bearing.** Inherit-plan-from-theme first,
  so a theme 275 could attribute drags its objectives onto the same plan; then
  the carrier plan; then the `General` theme, which reads each objective's plan
  and so must run AFTER every objective has one; then the FKs; then the NOT
  NULLs, which would refuse anything the earlier steps had not settled.
- **`upsert_pillar` / `upsert_objective` validate BEFORE adding the row, and
  the reason is autoflush.** Each ownership check is a SELECT, a SELECT
  autoflushes, and a half-built theme or objective has no plan yet — so adding
  it first turned "that plan is not this club's" into a NOT NULL violation, a
  500 where a plain 422 was meant. Found by the verification, not by reading
  the code. Anything added to those two functions goes after the checks.
- **A theme is created with its plan or refused, and an objective with its
  theme or refused.** No `cascade` flag on either delete route any more — it
  described a choice that no longer exists.
- **`plan_report` still emits an empty `unassigned` key.** Always empty by
  construction; kept on the wire so a browser served mid-deploy from an older
  bundle reads the key it expects rather than crashing.
- **Verified against a real Postgres** (47 checks: the conversion applied three
  times to a populated pre-276 table, no objective deleted, each of the three
  bad states settled, a carried theme keeping its own objectives, an objective
  filed under its own plan's `General` rather than another plan's, the action
  and motion surviving, all three NOT NULLs and all five referential actions
  read out of `pg_constraint`, both writers' refusals, an objective following
  its theme rather than the caller's plan, a theme delete reaching one plan
  only, a plan delete taking its branch and leaving the rest, and the action
  and motion outliving the whole plan unlinked) with a **separate check that
  alembic and the lifespan mirror land on the same schema**, and **driven in
  Chromium** (23 on the manage screen and the three Plans sections plus the
  existing 108 and 40: nothing draws "Not on a plan" or a "No theme" bucket
  anywhere, the objective form refusing to save without both, the two deletes
  sending no cascade flag and saying what goes, and the register naming all
  three tiers).
- **`confdeltype` comes back from asyncpg as BYTES**, since it is Postgres's
  internal `"char"`. Cast it in SQL (`confdeltype::text`) or a comparison
  against `'c'` is quietly false however right the constraint is — five checks
  read as failing before that was spotted.
- **A level's step-in is DERIVED from the caret's width, not chosen
  (v9.49.6).** `TREE_STEP` is `ml-[34px]` = the 28px control plus the row's own
  6px gap, which is exactly what puts a child's caret under the first letter of
  its parent's label. At the old `ml-3` a theme's caret sat 22px LEFT of the
  word PLAN above it, reading as though it belonged to the level above. Change
  `TWISTY_BOX`'s width or `TREE_ROW`'s gap and this moves with them. The cost
  is real and accepted: a name three levels down has ~34px less to sit in and
  wraps more readily, which is why the row-height check asserts "a one-line row
  is still 37px" rather than a fixed array of heights.
- **`Twisty` IS the button, not something inside one (v9.48.2).** The
  expand/collapse control was an 11px glyph in a `w-3.5` span wrapped in a
  button with no width of its own, so the button shrank to the glyph's advance
  width and the hit area measured **5.53 × 24px** — measured with the change
  stashed, not estimated. It is a 28×28 box now, carrying the click, the
  `aria-label`/`aria-expanded` and the hover tint, and `TWISTY_BOX` is shared
  by the control and the spacer so a row with nothing to fold cannot drift out
  of line with one that has. Row heights are untouched (the two-line label is
  taller than the control either way — 37px before and after).
- **A PLAN IS ALSO READ AS DELIVERY, NOT ONLY AS A STRUCTURE (v9.50.0).**
  `PlanDelivery` sits under the plan's summary card and asks the same two
  questions of every theme, objective and action: is the work where it should
  be by now, and is the money keeping pace with it. **No backend change** —
  `plan_report` already carries `start_date`, `due_date`, `percent_complete`,
  `budget_estimate` and `actual_expenditure` on every action.
- **IT IS A DASHBOARD, NOT A DUMP, AND THE FIRST CUT WAS THE DUMP (v9.50.2).**
  Reported as unreadable, and the cause is worth keeping: `DeliveryRow` was
  used at every level SO THAT a reader could compare like with like. That is
  right for analysis and wrong for scanning, and a committee scans first — the
  uniformity was the bug. The order is now plan figures → what needs attention
  → a row per theme, with objectives inside an opened theme and the work inside
  an opened objective. **Progressive disclosure, not more screens.**
- **THE OBJECTIVE IS THE UNIT.** An objective is what the committee committed
  to; an action is how. Actions and motions sit behind `View details`, so the
  page opens as a plan rather than as everything filed against one.
- **NO SINGLE VERDICT AT PLAN LEVEL, deliberately.** `rollUp` takes the worst
  of what is underneath, which is right for a theme and wrong for a plan: one
  overdue action would brand a sixteen-objective plan LATE forever. The
  headline is a PROPORTION (`n/m objectives on track`) plus a count of what
  needs attention.
- **The plan is summarised ONCE.** `PlanFigures` is rendered by the plan pane
  INSIDE its title card. The first cut left the card's old four tiles in place
  and put the delivery figures in a second card directly underneath — the same
  numbers twice, printing 44% and 45% for one plan an inch apart because each
  side worked it out its own way. Delivered/budget/spent come from the PLAN ROW
  the backend already rolled up; only the counts are derived here.
- **`NO DATES` was a chip and is now muted metadata**, which is what the
  silence rule always meant — the first cut rendered "we cannot say" as a badge
  competing with the real verdicts. `not_started` is a real state and covers
  what the badge was being used for.
- **Every state is a GLYPH and a WORD** (`✓ DONE`, `● BEHIND`, `○ NOT
  STARTED`), including in the attention list, where BEHIND and LATE share the ●
  and would otherwise be told apart by colour alone.
- **The variance is written out on the scanning surfaces** (`18% behind`,
  `spending ahead`) and the target TICK survives only on the action detail. A
  mark needs a key; the first cut had to print a paragraph explaining it over
  the whole dashboard. One level in, the reader has chosen to look closely and
  a tooltip carries it.
- **The rail folds away rather than becoming its own tab.** The tree and the
  dashboard want the same width, and while a plan is open the tree is redundant
  navigation. Splitting them onto `Overview | Plan Structure | Timeline |
  Budget` would recreate exactly the pick-between-three-views-of-one-thing the
  Strategic Plans / Themes / Objectives row was removed for.
- **The form is a METER WITH A TARGET TICK, and the gap between them is the
  whole reading.** The fill is where the work got to; the tick is where it
  should be — on SCHEDULE the share of the action's own span that has passed,
  on BUDGET the share of the work that is done. Two numbers side by side do not
  show a gap, and a second bar would be a second scale for one quantity. Both
  meters run 0–100 so money and time share a base: **never a second axis**.
- **EVERY VERDICT IS A WORD; the colour is second, and that is measured rather
  than assumed.** Running the palette validator over this app's own status
  colours: the green and the amber separate by **ΔE 7.2 under protanopia**
  (inside the 6–8 band that is legal only with a second channel), and in the
  LIGHT theme the red and the amber are **ΔE 14** apart for a reader with full
  colour vision — under the 15 floor. So `StateChip` always spells the state
  out (DONE / ON TRACK / BEHIND / LATE / NO DATES / OVER BUDGET / SPENDING
  AHEAD / IN BUDGET). Do not add a state that is distinguished by colour alone.
- **A group's verdict is the WORST of what is under it**, ignoring what could
  not be judged: a theme is late if any action serving it is late, and done only
  when every one is. That is what makes a theme's figure mean the same thing as
  an action's, and lets the headline be traced to the work dragging it.
- **`DRIFT_TOLERANCE` (10 points) and `SPEND_TOLERANCE` (15) are deliberate
  choices, not measurements.** Without them an action a day behind the clock
  reads BEHIND and nearly everything lights up, so the colour stops meaning
  anything; spend legitimately runs ahead of progress (you buy the materials
  before you lay them). Both are named constants with the reasoning attached.
- **SILENCE WHERE THE CLUB'S DATA CANNOT ANSWER**, the same rule the selection
  rules keep. No start AND due date means no elapsed fraction, so there is no
  schedule verdict and no tick — never a flattering one. Nothing allocated
  means no budget verdict, because "0 of 0" is not under budget. A motion is a
  decision rather than a piece of work, so it is listed with its outcome and
  given no meters at all.
- **ANY NUMBER OF THEMES OPEN AT ONCE (v9.50.3).** Every theme starts folded,
  so the page still opens as a list of themes rather than the whole plan — but
  a committee comparing two themes must not have the first shut on it when the
  second is opened, so `openThemes` is a Set and `jumpTo` UNIONS rather than
  replaces. `openWork` already worked this way.
- **NOT STARTED IS AN ABSENCE, NOT A SEVERITY, and `rollUp` takes it out of
  the comparison entirely (v9.50.3).** Reported off a live screen: a theme at
  43% with two objectives going well read NOT STARTED because a third had not
  begun. It only wins when nothing under it has begun at all; when everything
  that HAS begun is finished but something has not, the theme reads ON TRACK —
  not DONE, because it isn't.
- **Verified in Chromium** (49 checks, dark and light: every state on screen at
  once from dates relative to today, the strip's counts matching the rows
  beneath it, a theme rolling up to LATE off one late action, the tick measured
  as a 2px mark inside its own track and landing at the elapsed 50%, both
  silences, an empty plan saying so, no verdict rendered colour-only, two
  themes open together with closing one leaving the other alone, the mixed
  theme reading ON TRACK while its own unstarted objective still says NOT
  STARTED, and no overflow at 390px).
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
- **The objective PICKER is a TREE, and only its LEAVES are selectable.** A
  flat `<select>` of "Plan › Theme › a whole sentence" was reported as
  overwhelming, and the repetition really was ~80% of the text while the part
  that tells two objectives apart was the part being clipped. It became one
  combined `PLAN › THEME` heading, and is now the tree it always was: the plan,
  its themes indented under it with a rail down each branch, the objectives
  indented under those. **The plan and theme rows are headings, not buttons,
  and carry no `role="option"`** — an action or a motion serves an OBJECTIVE
  and nothing else, so those two levels exist to locate one and there is
  nothing to pick by mistake; a screen reader is read the objectives it can
  actually choose from. Each objective gets its own wrapping line, the current
  one is ticked, and a search box appears past six rows. It is not a `<select>`
  any more, so a test asserting `<option>` text is asserting the old control.
- **The branches are keyed on `plan_id`/`pillar_id`, never on their names.**
  Two plans may legitimately be called the same thing, and grouping by name
  would draw one branch holding both plans' themes — the exact leak migration
  275 exists to prevent, reintroduced in a picker.
- **One component, six mounts.** `ObjectiveSelect` is the only control that
  links an action or a motion to an objective (the two editors in
  `governance.jsx`, the register's row and new-motion forms in
  `AdminCommittee.jsx`, and the two SERVES OBJECTIVE boxes in `MeetingRoom.jsx`),
  so a change here reaches all of them. The Actions list's "Any objective"
  dropdown is deliberately NOT this: it FILTERS a list rather than creating a
  link, and lives in a compact filter row where a tree panel would be wrong.
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


### The PDF's own typography (v9.53.4)

Reported off the generated PDF: the motion and action blocks sat far too deep,
the page wanted air, and the file should be Arial. The Word file was fine.

- **`indent` IS TWIPS AND THE PDF WAS READING IT AS POINTS.** One number served
  both writers, so `indent: 200` meant 10pt in Word (right, and why only the PDF
  looked wrong) and 200pt in the PDF, an indent nearly a third of the page.
  `pdfIndent` converts, and `indentPt` overrides it where the two formats are
  deliberately set apart — which they are here, since the Word depth was already
  what the club wanted and only the PDF was asked to change.
- **ARIAL IS A REAL FONT OBJECT, not a base-14 alias.** The PDF declares
  `/Arial` and `/Arial,Bold` as TrueType with a FontDescriptor and their own
  Widths, and embeds nothing: a reader uses the Arial it has and substitutes a
  metrically compatible face where it has none. **The declared Widths are the
  ones the layout measured with**, so the glyphs land where they were placed
  either way. Word names the face on every run, since its default comes from
  whatever template the reader opens it in.
- **HELVETICA-BOLD HAS ITS OWN WIDTH TABLE NOW.** Bold was measured off the
  regular table times 1.06, which is close on a short heading and wrong across a
  table header. Arial Bold matches Helvetica-Bold, so one table serves the
  measurement and the declared widths.
- **A BARE LINE MATCHING AN AGENDA ITEM'S TITLE IS A HEADING.** The draft heads
  its sections that way, with no markup at all, so matching only `**bold**` and
  `## ` found nothing and the entire account fell into one Record of Discussion
  lump at the end — carrying the model's own title block, which is what read as
  "APPLECROSS CRICKET CLUBCOMMITTEE MEETING MINUTES10 August 2026" mid-document.
  `splitNarrative` takes the agenda's titles and treats a bare line matching one
  as a heading; a short run of short lines ahead of the first heading is the
  preamble the prompt already forbids and is dropped.
- **Verified in Chromium** (95 checks: the indent measured off the real draw
  operations at 200/3 from the margin, a heading still at the margin, the gap
  before an agenda title, after it and before a MOTION or ACTION block each
  measured baseline to baseline, both fonts named, the declared width range, the
  narrative filed under the item it names and no Record of Discussion left over)
  **with a control run** failing exactly those nine.
- **A gap is measured PER PAGE.** `y` restarts at the top of each one, so the
  first element on a page has no meaningful gap above it and the check reads the
  next occurrence instead of failing on a page break.

### The minutes are a DOCUMENT, composed from the record (v9.53.3)

Reported with the current output and a Word file of what was expected: the
draft was one block of prose with its `**` marks showing, and it had lost the
motion moved during the President's report, the objective that motion served,
the votes, and the detail of the actions.

- **A FLAT LIST OF MOTIONS IS WHY THE MODEL GUESSED.** `draft_minutes` handed
  the model every motion in one list with nothing saying which agenda item each
  belonged to, so a Premium Sponsorship motion moved under the President's
  report was written up under Sponsorship & Fundraising, where its subject read
  as belonging. `_minutes_context` now nests each motion and action UNDER its
  agenda item, with the objective breadcrumb, the tally and the named votes, and
  the prompt says to write a motion up under the item it is listed against
  rather than the one its subject suits.
- **THE DOCUMENT IS COMPOSED FROM THE RECORD, NOT FROM THE NARRATIVE.**
  `minutesDoc.buildMinutesDoc` builds the details table, the agenda, a numbered
  section per item, each item's motions and actions, and the actions table out
  of the room payload. A figure the club has already entered cannot go missing
  because a paragraph failed to mention it. The written account is only ever the
  prose inside a section.
- **`splitNarrative` returns `loose` as well as `sections`, and that is
  load-bearing.** The first cut keyed the narrative on its own headings and
  dropped everything else, so a secretary who typed plain prose into the box
  lost all of it. Anything not under a heading, plus any heading no agenda item
  claimed, is kept in a `Record of Discussion` section.
- **`textDocs` takes BLOCKS now** (title, heading, para, label, bullets, table,
  spacer), because a details table and an actions table cannot be expressed as
  lines of text. `body` still works for the plain-text case, which is what the
  private notes use.
- **A PDF OP THAT REPORTS NO HEIGHT POISONS THE WHOLE LAYOUT.** The rule under a
  heading carried no font size, so `op.size * 1.32` was NaN, `room()` was false
  for everything after it and `y` never recovered: a two-page document came out
  as **19 pages, half of them blank**, and every content check still passed.
  `heightOf` is per-kind and falls back to 0. **The suite now asserts the page
  count and that no page is blank** — the check it was missing.
- **`push(...tableOps(b))` into a one-argument helper drew ONE ROW PER TABLE**
  and silently dropped the rest, which a check asking "is a row drawn" passed.
  `push` is variadic, and the suite counts the rows it expects.
- **The short table columns are sized against the widest value they actually
  hold** (a name, a date, a money figure, "Not recorded", "In Progress"), or
  "Not recorded" breaks as "Not recorde / d" and reads as a fault.
- **Names are stored "Surname, First", so a list of them is joined with
  semicolons.** Comma-joining "Hullett, Mark" and "Monument, Darren" reads as
  four people.
- **Verified in Chromium** (83 checks: the reported meeting replayed, the motion
  measured as sitting between the President's report heading and the next one,
  its objective, tally and named votes, the action's own different objective,
  every row of both tables read out of the real table cells, the page count, no
  blank pages, nothing drawn outside the margins, cells tiling with no gap, and
  the narrative kept when it has no headings) **with a control run**: with the
  change stashed there is no club heading, no details table, no agenda and no
  tables at all. The context builder is checked separately in Python against the
  reported meeting, with no database and no API key.

<!-- END original CLAUDE.md L5392-5894 -->
<!-- BEGIN original CLAUDE.md L5895-5960 -->
## The minutes leave the screen as a document (v9.53.2, Aug 2026)

Asked for directly: two buttons under MINUTES and two under YOUR NOTES, to take
each away as a Word document or a PDF.

- **BOTH FORMATS ARE WRITTEN IN THE BROWSER FROM THE BOX, NOT FETCHED BACK FROM
  THE RECORD, and that is the whole reason it is not a download endpoint.** The
  autosave is a 700ms debounce, so a download taken a second after the last
  sentence would hand back the version without it. `downloadField` reads the
  textarea's own ref, so what is on screen is what is in the file. Measured, not
  assumed: the suite blocks the PATCH entirely and still finds the typed text in
  all four files.
- **`lib/textDocs.js` carries no dependency, deliberately.** A `.docx` is a zip
  of three XML parts and a PDF is a handful of objects and a table of byte
  offsets; a document toolkit would cost more to ship than the ~250 lines that
  write both. The zip entries are STORED rather than deflated — Word accepts
  either and storing them means no compressor to carry.
- **The PDF wraps against real Helvetica advance widths**, not a guessed
  character count, which is what puts the line break where the text actually
  ends. A word too long for a line of its own is broken by character, so a
  pasted URL cannot overrun the margin silently. Every one of the 150 rows the
  suite draws is measured: widest 476.88pt against a 483.28pt column.
- **A PDF is WinAnsi, so it genuinely cannot hold every character.** Curly
  quotes, dashes and an ellipsis live in WinAnsi's own 0x80–0x9F block rather
  than at their Unicode code points and are mapped; Latin-1 passes through; a
  character outside it becomes a question mark rather than a broken glyph. **The
  .docx is UTF-8 and has no such limit**, which is the honest answer for a club
  whose minutes carry a name the base-14 fonts cannot draw.
- **`w:sz` is HALF-points and `w:spacing w:after` is twentieths of a point**, so
  32 reads as 16pt and 120 as 6pt. A line of the box becomes its own paragraph
  and a blank line becomes an empty one, so the text reads in Word as it is laid
  out on screen. A control character is stripped before it reaches the XML —
  Word refuses the whole document over one, rather than skipping it.
- **A NULL means "nobody has touched this box".** `minutesTyped`/`notesTyped`
  start null and the disabled flag falls back to the record; once typed in they
  follow the box. Without that, a reload after some unrelated action would
  recompute the flag off minutes the autosave has not sent yet and disable a
  button over a full field. `draft()` writes straight into the ref, so it sets
  the flag too.
- **The buttons are disabled on an empty field rather than hidden**, so the
  option is visible before there is anything to download, and the title says why
  it cannot be pressed.
- **The notes document says on it that it is not part of the minutes.** The
  screen says they are never circulated; a file that has left the screen should
  keep saying so.
- **Verified in Chromium** (`frontend/verification/verify_minutes_download_browser.mjs`,
  40 checks against the real meeting room with the API stubbed: both rows
  measured as BELOW their own text box off the real boxes rather than source
  order, disabled while empty and enabled once not, the four files produced and
  named for the meeting and its date, the typed text present with the PATCH
  deliberately blocked, `&` and `<` escaped rather than breaking the XML, the
  blank line kept, minutes and notes not leaking into each other, each `.docx`
  unzipping to the OOXML parts a reader expects and each `.pdf` carrying an
  xref table whose `startxref` points at it, the same two rows with the room
  EMBEDDED in the Committee screen, the autosave still firing afterwards, no
  page errors, no overflow at 390px) **with a control run**: with the change
  stashed the rows are absent and nothing downloads at all.
- **A stub that returns the wrong SHAPE measures a broken page**, twice over
  here: `previous_attendance` is an object or null and an empty array is truthy,
  which crashed the attendance panel; and the single-meeting GET must answer
  with the MEETING, not the list, or every card on the Committee screen has no
  id and no OPEN button — which also produced a React key warning that read as a
  pre-existing app bug and was the stub's own fault.
- **`page.evaluate` treats a STRING as an expression**, so a probe written as a
  function-expression string comes back unevaluated rather than called.

<!-- END original CLAUDE.md L5895-5960 -->
<!-- BEGIN original CLAUDE.md L7854-7903 -->
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

<!-- END original CLAUDE.md L7854-7903 -->
<!-- BEGIN original CLAUDE.md L7904-7947 -->
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

<!-- END original CLAUDE.md L7904-7947 -->
<!-- BEGIN original CLAUDE.md L7948-7985 -->
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

<!-- END original CLAUDE.md L7948-7985 -->
<!-- BEGIN original CLAUDE.md L7986-8074 -->
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
- **Deleting never cascades into the work.** A deleted objective leaves its
  actions and motions. An objective is real work the club committed to, and
  binning it because the document it was written in was deleted would take
  every action serving it down too. **SUPERSEDED IN PART BY 276**: a deleted
  plan no longer leaves its objectives — a plan owns its themes and a theme
  owns its objectives, so the branch goes. The actions and motions serving
  them are still kept, which is the half of this rule that holds.
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

<!-- END original CLAUDE.md L7986-8074 -->
<!-- BEGIN original CLAUDE.md L8370-8405 -->
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

<!-- END original CLAUDE.md L8370-8405 -->
<!-- BEGIN original CLAUDE.md L9283-9340 -->
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

<!-- END original CLAUDE.md L9283-9340 -->
<!-- BEGIN original CLAUDE.md L9487-9552 -->
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

<!-- END original CLAUDE.md L9487-9552 -->
<!-- BEGIN original CLAUDE.md L9553-9646 -->
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

<!-- END original CLAUDE.md L9553-9646 -->
<!-- BEGIN original CLAUDE.md L9672-9924 -->
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
- **A MOTION IS A RECORD FIRST AND A FORM SECOND (v9.50.5).** Reported off a
  live meeting: the screen read as an administration form because almost
  everything was in edit state at once. A motion's row now carries the wording,
  the tally and the objective it serves as metadata, with the OUTCOME as the one
  live control — that is the act a chair repeats all night and it must not cost
  an extra click. The wording, the objective picker, the per-person votes and
  the delete are behind `Edit`. **It closes with `Done`, not Save/Cancel**: a
  vote is written the moment it is cast, as everything else in this room is, and
  a Cancel that could not undo it would be a lie.
- **An empty field is not information.** The permanent `Motion wording…` box is
  gone behind `+ Add motion` (Escape closes it). `All present: For` writes a For
  for everyone in the room in one click, because most motions pass unanimously.
  The tallies note moved onto a hover `Hint`.
- **AN ACTION IS A RECORD TOO, AND IT CAN NOW BE CORRECTED (v9.50.7).** The
  room could mark an action done or delete it and nothing else, which is a poor
  set of options for something typed in a hurry mid-meeting. `ActionForm` takes
  an optional `action` and edits in place; `Done` stays on the row (the repeated
  act) and the delete moved into the editor. The row reads title + status pill,
  then owners / due / budget, then what it serves — `shortDate` writes the date
  for reading rather than sorting.
- **NO BOX INSIDE A BOX (v9.50.7).** A motion and an action each carried a
  border, a radius and a tint INSIDE the agenda item's own card, which is what
  made the screen read as a stack of rectangles. Both are a tinted left edge and
  spacing now; the agenda item is the only full container. The suite asserts it
  on the computed style (no element around a record has four borders, and each
  still has its left one), not on class names.
- **A DIVISION IS THE EXCEPTION, NOT THE RULE (v9.53.8).** Most motions pass on
  the voices: moved, seconded, the chair says carried, nobody counts. A counted
  vote is for a contested motion, a special resolution that has to clear a
  majority threshold, or a declared conflict where somebody must abstain and the
  minutes have to show it. So the per-person list sits behind
  `+ Record a division` rather than costing every motion ~100px of form it will
  not use. **Seeded OPEN when the motion already carries names**, or a division
  recorded last month would be hidden the next time anybody opened the record.
  Nothing about what is STORED changed: the tallies still derive from the names
  when a club records them, and an outcome on its own is still a complete record
  of a voice vote.
- **1.6:1 IS NOT A LEGIBLE COLOUR FOR WORDS, AND THIS WAS MEASURED (v9.53.7).**
  Reported off a live meeting: the objective picker, the vote list, the member
  names and the small links were all too pale. `--pb-faintest` computes to
  **1.64:1** against `--pb-surface2` in dark and 1.70:1 in light; `--pb-faint`
  is 2.75/2.79, also under the 4.5:1 floor for text this size. `--pb-dim` is
  **5.40/5.47**. So the meeting room paints nothing at faintest or faint any
  more, `cap` in both `MeetingRoom.jsx` and `governance.jsx` is `text-pb-dim`,
  and `ObjectiveSelect`'s plan heading, theme heading and objective rows read at
  full strength — the tick and the accent tint are what mark the current one,
  not a dimmer sibling. **The tokens themselves are unchanged**: `faintest` is
  still right for a rule or a disabled state, and a platform-wide sweep is a
  different change from the one that was asked for.
- **The check is "nothing in the room paints at the palest token"**, walked over
  every element inside the room's own grid and compared against the token as the
  BROWSER resolves it, not against a class name. Against the previous commit it
  names **21 to 28 elements** at 1.64:1. A first cut hunted a hand-picked list of
  labels and passed against the broken code — a contrast check that cannot fail
  is not a check.
- **`\d` INSIDE A JS TEMPLATE LITERAL IS JUST `d`.** The probe's own
  `/[-\d.]+/` silently became `/[-d.]+/`, matched no digits, and every ratio
  came back NaN — which `JSON.stringify` prints as `null`. Escape it as `\\d`
  in a probe passed to `page.evaluate` as a string.
- **CLICKING A RECORD OPENS IT, and it is deliberately NOT a `role="button"`.**
  Reading a motion and correcting it are the same act at 8pm. But a role on the
  wrapper gives one control an accessible name made of the record's whole text,
  which reads as a giant unlabelled button and swallows every word inside it —
  it also broke `getByRole('button', { name: /not on the plan/ })` in the picker
  suite, which then matched the record instead of the picker. The Edit button
  beside it IS the accessible control; the click on the record is a mouse
  convenience on top of it. The outcome select, the drag handle and Done all
  `stopPropagation`, so the one act repeated all night opens nothing.
- **THE BUTTON THAT FINISHES A RECORD MUST NOT CARRY THE NAME OF THE ONE THAT
  OPENED IT.** Reported as "you say Add motion, type it, then click add motion
  again": `+ Add motion` opened the form and `+ MOTION` finished it, a few lines
  apart. They are `RECORD MOTION` and `RECORD ACTION` now, and Enter finishes
  either (Shift+Enter for a second line of motion wording, Escape backs out).
- **`WHAT WAS SAID` is `rows={10}`, not a pixel height**, so a club that has
  picked its own font gets ten of ITS lines.
- **An action can be due back at the next meeting**, and it fills in that
  meeting's REAL date rather than storing "next meeting" as an idea: the minutes
  print a date, the overdue rules read a date, and an action that outlives a
  rescheduled meeting still says when it was wanted. `next_meeting_after`
  prefers the next meeting of the SAME kind (an AGM is not what "the next
  committee meeting" means to somebody sitting in one), falls back to any kind,
  skips a cancelled one, and rides on the room payload so it costs no second
  request. The button names the date it will set and is not drawn at all when
  the club has nothing later scheduled.
- **THE MINUTES SUMMARISE WHAT WAS RESOLVED.** `Motions arising from this
  meeting` is a table of #, motion, moved, seconded and result, ahead of the
  actions table. Motions are numbered `M-01` in the order the DOCUMENT reads
  them — down the agenda, then anything raised outside it — and the same number
  is printed on the motion's own block, so "M-02 carried" in a later meeting's
  business arising resolves to one motion rather than being matched by wording.
- **A blank line either side of every agenda heading and every MOTION / ACTION
  label**, in both formats. Word had no gap of its own the way the PDF path
  does, so `para()` gained `w:spacing w:before`; it is twentieths of a point and
  the body runs at 10.5pt, so ~240 is one clear line.
- **A TABLE HEADER REPEATS ON EVERY PAGE IT RUNS ONTO** (`textDocs` marks it
  `repeat`), so a check counting header-width rows must be `>=`, not `===`.
  Adding one motion to the fixture lengthened the document, the actions table
  crossed a page, and an exact count failed on a document that was correct.
- **Verified against a real Postgres** (11 checks on `next_meeting_after`: the
  same-kind preference, the AGM skipped between two committee meetings, a
  cancelled meeting skipped, the fallback to any kind, the last meeting
  reporting nothing, another club's never offered, and the room payload
  carrying it) and **driven in Chromium** (the room suite is 90, dark and light;
  the minutes suite is 107) **with a control run**: 16 of the 90 fail against
  the previous commit, including the box measuring 2 rows and 21 elements
  painted at 1.64:1.
- **A MOTION IS MOVED, SECONDED AND VOTED ON IN ONE BREATH, so it is recorded
  in one (v9.53.6).** Asked for directly: record who moved a motion and who
  seconded it, and take the vote at the moment the motion is created rather
  than having to reopen it under Edit. **No migration** —
  `meeting_motions.proposed_by_member_id` / `.seconded_by_member_id` have
  existed since the table was written, the minutes PDF already prints "moved
  by X" / "seconded by Y" off them, and the register's own `MotionEditor` has
  always offered both. Only the MEETING ROOM never did.
- **`MotionForm` is ONE definition of what a motion record holds**, mounted by
  `+ Add motion` and by a row's `Edit`, the same call `ActionForm` makes. **The
  two uses write differently and both are right**: an existing motion saves as
  it is pressed, the way the rest of the room works, so there is nothing a
  Cancel could undo; a new one has no row to write to yet and is held until
  `+ MOTION`. A `live` flag is the whole difference, and `useAutosave` is
  called on every render either way so the hook order cannot change.
- **The NAMED votes are a second request, unavoidably.** They key on the
  motion's own id, so `onAddMotion` creates the motion with everything else
  (wording, both names, outcome, objective) and then writes the votes against
  the id that comes back. `MotionCreate` and `create_motion` gained `outcome`,
  the three tallies and `notes` so the rest lands in ONE write; every field
  falls back to the column default, so an existing caller is unchanged.
- **A mover is picked from the people in the room**, since that is who moves
  and seconds a motion — but a name already recorded stays selectable when that
  person is no longer marked present, or reopening the record would quietly
  drop it.
- **SILENCE WHERE THE CLUB DOES NOT RECORD IT.** The `moved by … seconded by …`
  line is drawn only when at least one is set. A club that counts a show of
  hands and never names a mover should not have every motion carrying a "not
  recorded" reproach — the opposite call to `not on the plan`, which is about a
  link the club is being encouraged to make.
- **Verified against a real Postgres** (10 checks through the shipped route
  body and `create_motion`: the whole record in one create, a bare create still
  opening as pending with nobody named and no tallies invented, the named votes
  re-deriving the tallies, a correction landing, and all three coming back on
  the room payload) and **driven in Chromium** (the room suite is 73 now: both
  pickers offering the people in the room in attendance order, a vote cast
  before the motion exists being HELD rather than sent, the exact create
  payload, the votes following in their own write, the row's mover line, and a
  motion with neither recorded drawing nothing) **with a control run**: 11 of
  the 73 fail against the previous commit.
- **A MEETING IS RENAMED WHERE ITS NAME IS READ (v9.51.7).** Renaming used to
  live on the manage screen, and the header link to it was removed in v9.50.4,
  so there was nowhere left to do it. `EditableHeading` (exported from
  `MeetingRoom.jsx`) is ONE component mounted twice — the Committee summary
  pane's `<h2>` and the room's own inline header — so the two cannot behave
  differently about the same field. Click, type, Enter saves; Escape puts the
  old name back and sends nothing; **a blank name is refused rather than
  saved**, since a meeting has to be called something and an accidental
  select-all-and-delete must not wipe what the minutes are filed under. It is
  declared at MODULE level, per the never-declare-a-component-inside-a-render
  rule — a re-declared component is a new element TYPE and the focused input
  goes down with the old subtree.
- **`setTitle` rides on `onMeta` beside `setStatus`**, and both reload rather
  than patching the local copy: the name on screen is the name the server
  stored, and the host's `onRoomMeta` already carries `title` onto the card in
  the rail, so a rename in the room shows in the list beside it without waiting
  for the room to be closed. **The standalone route is deliberately NOT
  editable** — its title is the MODULE header's, a plain string that also feeds
  `ModuleLayout`'s bookmark label, so a node there would render as
  `[object Object]` in the bookmark.
- **`getByRole`'s `name` is a SUBSTRING match by default**, which is how the
  first cut of the rename check silently clicked the row's
  `aria-label="Delete August committee"` instead of the heading and reported
  "the field never opened". Pass `exact: true` whenever one record's name is a
  prefix of a control's label for that same record.
- **A GRID TRACK'S AUTOMATIC MINIMUM IS ITS CONTENT, WHICH IS WHY `1fr` LEAKS
  (v9.51.6).** Reported off a live meeting: the room ran off the right of the
  screen and took the attendance and minutes rail with it. The room is
  `grid-cols-[1fr_320px]`, and a bare `1fr` resolves to `minmax(auto, 1fr)` — so
  one unbreakable line in the main column widens the whole grid rather than
  being contained by it, and the fixed rail is pushed past the viewport. It is
  `minmax(0,1fr)` now. The pane it sits in already carried `minWidth: 0`, which
  is the same rule one level up and is not enough on its own: **every level
  between the long text and the scroll container has to be told it may shrink.**
- **`truncate` INSIDE A WRAPPING FLEX ROW DOES NOT TRUNCATE, IT EXPANDS
  (v9.51.6).** The other half of the same report. A motion's `serves …`
  breadcrumb carried `truncate`, which is `overflow:hidden` + `nowrap` — but
  nothing constrained its width, so the nowrap won and a 927px line stretched
  the row. It wraps now, which is also the better answer on its own terms: a
  breadcrumb is PLAN › THEME › OBJECTIVE and the objective's own title is the
  part on the END, so an ellipsis hides exactly the half that says which
  objective it is. Truncating is for a name in a fixed-width rail, not for a
  breadcrumb.
- **The suite measures the EMBEDDED room, not only the standalone page.** The
  report came from the room mounted inside Committee, where the pane is narrower
  than the window — so a check that only asks "is it inside the viewport" passes
  while the thing is visibly off screen. `room.mjs` opens the meeting from the
  Committee screen, expands an agenda item and asserts the breadcrumb sits
  inside its own `.pb-scroll` pane. With the fix stashed: 282px of document
  overflow at 1440px, 442px at 1280px, and 70 elements drawn past the right
  edge in the embedded case.
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

<!-- END original CLAUDE.md L9672-9924 -->
