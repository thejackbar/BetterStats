# Archive: sales-crm-and-commissions

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Sales workspace, sales performance, commissions, the retired Twenty CRM, engagement score.
Read the distilled rules first: `docs/dev-notes/guides/sales-crm-and-commissions.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L1631-1770 -->
## Twenty is retired; the engagement score, the CRM and Sales Management are not (v9.71.0, Sep 2026)

Asked for directly: *"the calculation and continual re-calculation of engagement
score and updating of CRM, and Sales Management functions is essential and both
manual export and background updating functions for CRM, Sales Management and
Club Directory must be preserved whilst retiring Twenty and its points of
integration."*

- **THE NIGHTLY RESCORE HAD SILENTLY STOPPED, AND FINDING THAT IS WHAT MADE
  THIS URGENT RATHER THAN TIDY-UP.** `refresh_twenty_engagement` returned
  immediately when Twenty was unconfigured and only ever touched clubs already
  in `twenty_links` — so the moment Twenty went away, NOTHING rescored anything
  platform-wide and every cached `marketing_clubs.engagement_score` froze
  wherever it was last incidentally touched. The Club Directory, BetterComms
  Lists/Segments, the CRM board and the Sales Workspace all read that cached
  number, so four surfaces were quietly reading a stale one.
- **`crm.recalc_all_engagement` IS THE ONE SWEEP, and three callers share it**:
  the nightly job (`daily_engagement_rescore`), the Club Directory's
  `POST /refresh-engagement`, and `python -m app.scripts.recalc_engagement`.
  The script keeps its histograms and percentiles through an `on_club`
  callback rather than a loop of its own — two copies of "rescore the whole
  directory" is how the button and the cron start disagreeing about what a
  score is.
- **THE ENGINE WAS NEVER TWENTY'S; ONLY ITS FILENAME WAS.** `_engagement` is a
  local read/compute over `usage_events` / `email_events` / our own
  subscription rows that CACHES onto the club row — Twenty was one reader of
  the result. So the move is `git mv services/twenty_sync.py
  services/engagement.py` and strip, NOT an extraction: that file is 1,000
  lines of dense reasoning about the scoring, and lifting 900 of them into a
  new file is how the comments get lost.
- **A `from x import y` INSIDE A FUNCTION BODY COMPILES, IMPORTS, AND STILL
  BREAKS.** Three subscription hooks imported `_push_club_to_twenty` lazily
  inside their own bodies — `billing.py` (a club adds modules to a live
  subscription), `stripe_billing.py` (**a Stripe payment lands**) and
  `organisations.py` (a club's first sync completes). `py_compile`, the import
  smoke test and `vite build` all pass on every one of them; each would have
  raised the first time a club actually paid for something. The suite checks
  the call sites structurally for exactly this reason.
- **`organisations.py` HAD BEEN CALLING A HELPER THAT NO LONGER EXISTED AT
  ALL** — the local `_push_club_to_twenty` was deleted and its call site left
  behind, a bare NameError on the club's first sync. It calls
  `club_admin._sync_club_to_crm` now, which is the right answer anyway: that
  helper links the directory row AND rescores, which is what "we synced the
  club, show it in the CRM straight away" meant.
- **A SEND STILL RESCORES THE CLUBS IT REACHED**, and that is the one place the
  retirement changed a behaviour rather than a name: the rescore used to happen
  as a SIDE EFFECT of pushing to Twenty. It is called directly now, per club,
  on its own session, so a BetterComms outreach send moves the engagement score
  immediately instead of waiting for the nightly sweep.
- **`twenty_links` IS LEFT IN PLACE AND READ BY NOTHING**, the call migration
  267 made for `vote_settings` — but the lifespan no longer CREATES it, so a
  fresh database simply does not have it. Same for
  `club_request_events.twenty_task_id`/`.twenty_task_status` and
  `crm_deals.source = 'twenty_import'`: stored values and history, never
  written again, and the ORM keeps mapping them so an existing row still reads.
- **THE PIPELINE GAUGE WENT WITH IT.** `routers/pipeline_gauge.py` rendered
  widgets for a Twenty dashboard iframe at `twenty.betterat.cricket`, reading
  Twenty's own `/rest/opportunities` — both ends gone, and the internal Sales
  Performance / Sales Commissions screens already answer the same question. Its
  two `GAUGE_*` settings went with it.
- **`OPPORTUNITY_AUTO_THRESHOLD` STILL EXISTS AND NOW MEANS SOMETHING WEAKER,
  so the copy says so.** Nothing auto-creates anything at 90 any more; it is a
  reporting line the parameters page and its preview count against ("Reads as
  an opportunity at"). Leaving the old label would have promised an automation
  that no longer runs.
- **A COMMENT THAT JUSTIFIES ITSELF BY A RETIRED SYSTEM GOES STALE WITH IT.**
  `trial_lifecycle`'s docstring explained its own design as "unlike the Twenty
  scan, this runs whether or not Twenty is configured" — true, and meaningless
  once there is no Twenty scan to be unlike. Corrected in place rather than
  left to mislead the next reader; same for `engagement_params`' user-facing
  group blurb and `models/db.py`'s column comments.
- **Verified against a real Postgres**
  (`backend/verification/verify_twenty_retirement.py`, 57 checks — 11 retired
  modules gone, 9 retired settings gone, no retired route on either side of the
  wire, the three subscription hooks calling something that EXISTS, and then
  the half that matters: the score computed AND cached, the sweep reaching
  every club with the busy one outscoring the club nobody has visited, a dry
  run writing nothing, a single club rescoring on its own signal without
  touching its neighbour, and the operator script running the shared sweep
  rather than a second copy, and thirteen CRM / Sales / Super Admin / Reporting
  route bodies answering) **with two control runs**: 35 of the 40 reachable
  checks fail against the pre-retirement commit, and against the commit that
  had lost the three shared helpers, 5 fail naming them and the three buttons
  they break.
- **THE EXPORT BLOCK TOOK THREE SHARED HELPERS WITH IT, AND NOTHING NOTICED —
  found by auditing rather than by the suite.** `_now_iso`, `_settle_bg` and
  `_bg_stale` sat inside the Twenty-export region of `marketing.py` and are
  called by **Rediscover, Push to BetterCricket CRM and the engagement rescore**.
  The module still imported, `vite build` passed, the route strings were all
  still there, and every one of those three buttons would have raised
  `NameError` the first time it was pressed. **A structural check for a route's
  presence is not a check that the route RUNS**: the suite presses all three
  and their pollers now, and `undefined_names()` walks the whole backend for a
  name a module uses and never defines — the one check that catches a helper
  deleted along with the block it lived in.
- **THE ROUTE TABLE IS THE HONEST DIFF, and it was taken both ways.** Dumping
  `app.openapi()` on this commit and on the previous one and diffing names
  exactly 10 removed routes, every one Twenty-only (3 export/refresh pairs, 4
  gauge, 2 webhooks), against 2 added. No CRM, Sales, Super Admin, Reporting or
  Directory route lost. Repeat that dump whenever a retirement removes code.
- **THE SUITE NOW PRESSES THIRTEEN REAL SURFACES** — the CRM board, its stages,
  deals, events and settings, Wizard Clubs, commissions and periods, the Sales
  Workspace queue, the rep team, Sales Performance and the ad-signup report —
  because "nothing was removed" and "everything still answers" are different
  claims and only the second one is what a club notices.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN.** The first cut died on
  `from app.services import engagement` and said nothing about the twenty-odd
  behavioural checks below it. The behavioural half now REPORTS the engine or
  the sweep as missing and returns; each button press is wrapped for the same
  reason, so a `NameError` in a route body is a named failure rather than the
  end of the run.
- **A CHECK THAT MATCHES MORE THAN IT MEANS IS NOT A CHECK.** "the script keeps
  no loop of its own" scanned the whole file and caught the `--verify`
  equivalence checkers, which legitimately need one. It reads `recalc()`'s own
  body through `inspect.getsource` now.
- **TWO HARNESS ARTEFACTS, BOTH DOCUMENTED TRAPS HIT AGAIN**: a raw
  `UPDATE ... SET engagement_score = NULL` left the ORM's in-memory copy stale,
  so the sweep loaded a club that still LOOKED scored and wrote nothing; and
  `expire_all()` then handing that instance to a service lazy-loads on its
  first attribute read, which is the MissingGreenlet trap. `refresh`, don't
  expire, when the object is about to be passed on.
- **`usage_events`, `platform_settings` AND `marketing_utm_aliases` ARE
  LIFESPAN-CREATED RAW SQL**, invisible to `create_all`, and every column added
  since each was written lives in its own later ALTER — including the
  loop-driven ones whose `(column, type)` pairs sit in a tuple an f-string
  reads. The suite pulls the CREATE **and** every ALTER out of the shipped
  `main.py` rather than retyping them, so a table that merely LOOKS right
  cannot pass.
- **RENUMBERED 293 -> 295.** `origin/main` reached 294 while the Rediscover work
  was in flight, and its own 293 was a different migration entirely — two
  sharing a revision id break Alembic outright. **This file has now recorded
  that trap five times: check `origin/main` at the moment you merge, not only
  when you first number one.** The v9.70.0 changelog entry collided the same
  way and became v9.70.3.
- **NOTICED, NOT DONE**: `twenty_links` still exists on the live database with
  its history in it — dropping it is a decision for a person, not a deploy. The
  five Twenty-era docs are kept as the record of what was built, with a
  retirement banner on `docs/twenty-crm-integration.md`; the changelog entries
  that describe the Twenty era are untouched for the same reason.

<!-- END original CLAUDE.md L1631-1770 -->
<!-- BEGIN original CLAUDE.md L3894-4428 -->
## Sales Commissions: forecast on the open book, earned on the won one (migration 277, v9.49.0, Aug 2026)

Asked for as a tile on Sales Management: per rep, clubs attributed, total pipeline
value, total forecast pipeline commission and total weighted forecast commission,
plus a record of what has been won, what commission that earned, and what has
been paid.

- **THE MODULE-INTEREST MIRRORING WAS ALREADY BUILT, and finding that out was
  half the job.** The Sales Workspace's "Interest in" pills
  (`PATCH /sales-workspace/clubs/{id}/interest`) and the CRM deal card's own
  chips write the SAME `crm_deals.module_keys`, both stamp
  `product_interest_source='manual'`, and `crm.update_deal` recomputes
  `value_cents` from `billing_pricing.price_for` on either. There is no sync
  to build because there are not two fields — which is the whole reason it
  cannot drift. Verified end to end in both directions rather than assumed.
- **A DEAL'S DOLLAR FIGURE HAS ONE DEFINITION AND THIS FEATURE DOES NOT OWN IT.**
  `crm.effective_value_cents` / `effective_probability` (public aliases added
  over the existing private pair) are what the pipeline board's own totals are
  built from, so a rep's forecast and the board cannot disagree about the same
  deal. The suite asserts the two totals are equal, not merely close.
- **THE RATE IS LIVE FOR A FORECAST AND STAMPED FOR A WIN.** An open deal is
  forecast at the rep's CURRENT rate — a forecast is about what is still to
  come. The moment a deal is won, `crm_deals.commission_rate_percent` records
  the rate that applied, so raising a rep's rate tomorrow cannot rewrite what
  they earned last quarter. Deliberately NOT a snapshot of the deal's VALUE:
  correcting a mis-recorded won deal SHOULD flow through to the commission on
  it, which is the opposite of what a rate change should do.
- **`crm.move_stage` and `crm.close_deal` are the only two places a deal's
  status becomes 'won'**, plus `create_deal` for one born straight into a Won
  stage — so the rate is stamped in those three and nowhere else. A win through
  the board, through the Stripe webhook, or through an automation rule is one
  behaviour. `_stamp_commission_rate` imports the commission service inside the
  function, since that service reads crm.py for value and probability and a
  top-level import either way round is a cycle.
- **A REP IS A PERSON, NOT AN ACCOUNT.** `crm.list_platform_owners` already
  folds several login accounts under one display name into one entry (the bug
  v9.48.2.1 fixed in the pickers), so every figure here aggregates over that
  entry's whole set of ids. A rate or a payment is WRITTEN against the entry's
  primary id but READ across all of them — which account counts as primary is
  partly last-login order and can shift, and a payout must not go missing when
  it does. Where two accounts each carry a rate, the HIGHER wins: a person
  should never be paid less because of which account a deal landed on.
- **`exact_value` is what a real payment uses, and the ordinary merge is what a
  forecast uses.** `sync_platform_deal_for_club` normally unions module_keys and
  takes the higher value, which is right for a picture built out of successive
  signals and wrong the moment money changes hands. A club forecast at the full
  bundle that buys Stats alone was being recorded as a win at the forecast
  figure; an add-on was recorded at the club's whole holding. Either way the
  commission owed was overstated.
- **The add-on path never fired a win at all.** `routers/billing.py`'s
  add-modules-to-an-existing-subscription branch never touches Stripe Checkout,
  so there is no `checkout.session.completed` webhook behind it — it now calls
  `_push_club_to_twenty(crm_trigger="subscription_won", won_module_keys=addon_keys)`
  itself. `won_module_keys` threads from both Stripe paths through to
  `exact_value`.
- **REPEAT BUSINESS INHERITS THE ATTRIBUTION.** An upsell is a brand-new deal
  created straight into Won by the payment itself, with nobody having had the
  chance to earn it — so `sync_platform_deal_for_club` carries
  `commission_rep_user_id` from the club's most recently attributed deal
  (`_last_attributed_deal_for_club`, archived deals included: archiving hides a
  deal, it does not unmake the work). Without it, selling more to a club a rep
  brought in pays them nothing. It is set BEFORE `create_deal` stamps the rate,
  or the upsell would be rated as though nobody had earned the club.
- **Clubs attributed counts DISTINCT CLUBS, not deals.** A club that came back
  for more modules has a second deal, and counting it twice reads as two clubs
  won.
- **THE UNATTRIBUTED POOL IS RATED AT ZERO.** Its pipeline VALUE is worth
  showing — unclaimed work waiting for a rep — but no commission is owed on a
  club nobody has earned, and pricing it at the default would inflate the team's
  forecast with money that will never be paid to anyone. Shown, never dropped,
  and sorted last, the same rule Sales Performance's own Unassigned row follows.
- **The default rate seeds at 0, deliberately.** A commission percentage is a
  commercial decision and a number invented here would be quoted back at us, so
  the screen says no rate is set and asks for one rather than pretending to
  know it.
- **A payment is per REP, not per deal**, and a NEGATIVE amount is allowed: it
  is how a payout entered wrongly is corrected without deleting the original,
  which is what an auditable ledger needs. A zero is refused. Commission due is
  earned minus paid and may go negative — an overpayment is a real state, and
  clamping it to zero would lose it.
- **Earned is filed by the deal's `closed_at`, paid by the payment's `paid_on`,
  and the two legitimately land in different periods.** A quarter's work is
  routinely paid in the next one, and forcing a payment into the period it
  settled would be inventing an apportionment nobody made. Periods come straight
  from `crm_targets.period_bounds`, so a commission quarter and a sales-target
  quarter are the same thing rather than two conventions.
- **`services/sales_commission_ddl.py` is the ONE copy alembic and the lifespan
  mirror both run**, per the `vote_medal_ddl` rule. Two partial unique indexes,
  not a plain `UNIQUE(user_id)`: the latter would let any number of NULL rows
  through, and several rows each claiming to be "the default" is the one state
  this table must not hold.
- **Found by running the real boot order: `create_all` builds the table WITHOUT
  the `gen_random_uuid()` server default**, so `CREATE TABLE IF NOT EXISTS` is a
  no-op and the seed INSERT had no id — it failed outright, on a real boot as
  well as in the harness. The seed supplies `gen_random_uuid()` explicitly now.
  Same trap the self-serve-trial note already documents for
  `org_module_subscriptions.id`.
- **Verified against a real Postgres** (107 checks through the shipped services
  and route bodies: the DDL applied three times, a second platform default
  refused, every rate rule, the forecast reconciling with the pipeline board's
  own totals, a discount flowing through, the rate stamped at the win and a
  later rate change not rewriting it, the upsell inheriting its rep and being
  priced at the added module alone, merge-vs-exact both ways, every payment
  rule including the negative correction and the overpayment, the period
  filing, a rep with two accounts reading as one row, every drill-down as long
  as the figure it opens and adding up to it, and both Stripe paths carrying
  the modules actually paid for) and **driven in Chromium** (33: the four asked-
  for figures, every rep row and the pool sorted last, a rep's own rate used
  over the default, the exact params on the wire for a rate save and a payout,
  the drill-down's clubs/modules/stage/commission and its deep link, a zero
  opening nothing, the quarter/financial-year switch, a dismissed delete
  sending nothing, no page errors, no overflow at 390px).
### What the first look at the real data changed (v9.49.1)

- **A DEAL'S VALUE MUST FOLLOW ITS MODULES DOWN AS WELL AS UP.** Reported off
  the live screen: a deal listed as `Stats` sitting at **$998**, which is the
  all-six-modules price. `sync_platform_deal_for_club` merged a new signal's
  modules in and then kept `max(existing, new)` for the value — a ratchet. So a
  club valued at the full bundle during a trial held that price forever after a
  rep narrowed its interest to Stats, and value and modules drifted apart
  permanently. It now recomputes `value_from_modules(merged)`, which is the
  only definition that cannot drift. Reproduced against a real Postgres in
  three steps (trial → rep narrows → later signal) before fixing it.
- **`python -m app.scripts.repair_deal_values`** re-prices the OPEN deals
  already carrying the old figure, dry-run by default. **WON and LOST deals are
  deliberately skipped**: a closed deal's value is the record of what was
  actually sold, and re-pricing it would rewrite the commission earned on it. A
  deal with no modules at all is skipped rather than zeroed — an empty
  selection is "nobody has said yet", not "worth nothing".
- **The Rate column reading 0% was NOT a bug**, and confirming that took
  replaying the exact flow rather than reading the code: the rep had an
  explicit 0 stored (the panel shows RESET rather than a `default` pill, which
  is the tell), and the platform default was 0 too. The fix was to stop the
  screen being silent about it — the drill-down now says a rep has no rate
  where the $0 figures are, and a 0% rate carries an `earns nothing` pill in
  Commission rates. **A figure that is correctly zero still has to explain
  itself.**
- **The drill-down's columns follow the figure that opened it.** An OPEN deal
  has a likelihood, so it carries Stage, Value, Rate, Pipeline commission and
  Weighted commission; a WON deal has neither, so it shows Commission earned
  and no weighted column at all — weighting money that is already owed would
  be inventing a hedge on it. A total row adds up to the figure clicked, the
  same cell-and-its-list discipline the Sales Performance drill-downs keep.
- **One name per figure.** "Forecast commission" and "Pipeline commission" were
  the same number under two names across the KPI strip, the table and the
  drill-down; it is `Pipeline commission` everywhere now, and
  `Weighted commission` for the likelihood-adjusted one.
- **A club name in the drill-down is a real link** to
  `/admin/super/crm/workspace?club=<deal_id>`, which the Workspace's own
  deep-link effect already selects and loads whether or not the club is in the
  current queue filter. It was already a link and simply did not read as one.
- **Verified**: the Postgres suite is 139 checks now (the 107 above plus the
  drift reproduced and fixed both ways, the repair script's dry run / apply /
  won-deal skip / idempotent re-run, and a 22-check replay of the exact
  save-a-rate-then-read-the-column flow for three reps), and the Chromium run
  is 41.

### Picking a module pill scrolled the page out from under the rep (v9.52.2.1)

Reported off the Sales Workspace: clicking a pill under "Interested in" moved
the page, taking the club pane and the pill itself away from the cursor.

- **THE QUEUE'S RE-ANCHOR SCROLLS THE WHOLE PAGE, NOT JUST THE RAIL.**
  `toggleInterest` called `loadClubs()` at its default `anchor: true`, which
  `scrollIntoView`es the open club's RAIL row once the reload lands. The rail
  is its own scroll box, so that reads as harmless — but when the row sits
  above the fold the browser walks up and scrolls the DOCUMENT to reach it.
  Measured, not eyeballed: with a real-shaped club (14 contacts, a 30-row
  timeline) the click moved the page **683px**.
- **THE PILLS SIT BELOW THE RAIL, WHICH IS THE WHOLE REASON THIS BITES.** A
  first repro with an empty pane proved nothing and PASSED against the broken
  code — the pills were level with the rail, the row was on screen, and
  `block: 'nearest'` is a no-op. The contacts and timeline cards are what
  push the call form past the rail's bottom, so the harness has to carry them
  or it is testing a club nobody has.
- **`anchor: false` is right because picking a module is not navigating.** The
  re-anchor exists for a call/email/assign action, where the rep expects to
  move on; a pill is a mid-form edit and must leave the view alone. The queue
  is still refreshed behind it, and a toggle that genuinely drops the club out
  of the filtered list is unaffected — that branch runs whatever `anchor`
  says, and advancing to the next club there is still right.
- **Verified in Chromium** (the interest-pills suite is 11 checks now: the
  page not moving, the pill holding its position to within 2px, the rail row
  measured as genuinely off screen first, and the queue still reloading),
  **with a control run**: with the fix reverted the same two checks fail on
  exactly the reported behaviour.

### A `?club=` deep link opened the Workspace on the WRONG club (v9.49.3)

Reported off the commission drill-down: the link built the right URL and the
Workspace opened on a different club.

- **A club the URL names was never IN the queue, which is not the same as
  having dropped OUT of it**, and `SalesWorkspace.loadClubs` treated the two
  alike. Its "the open club has left the filtered list, advance to the next
  one" rule fired against the deep-linked club and reassigned the selection —
  and the URL — to row one. Every `?club=` caller is affected: Sales
  Commissions links each deal a rep is attributed and Sales Performance each
  deal in a stage, and neither knows or should care what the queue is
  filtered to.
- **Fixing that branch alone was NOT enough, and the second half is the one
  reading the code would have missed.** With the advance skipped, the load
  fell through to `else if (!initialPositionDoneRef.current && rows[0])` —
  the first-load landing — which never checked whether anything was selected.
  Its own comment claimed a deep link "would already have been handled
  above", which holds only when the linked club is IN the filtered list. It
  now also requires `!selectedIdRef.current`, which is what it always meant.
  **Found by instrumenting the running page, after the first fix changed
  nothing** — the branch that actually fired was three `else if`s away from
  the one that looked guilty.
- **`deepLinkedIdRef` is released the moment the rep picks a club from the
  rail**, so the ordinary advance-past-a-dropped-out-club behaviour comes
  back straight after. A pin that outlived the link would be a second bug in
  the other direction.
- **Verified in Chromium** (`frontend/verification/verify_workspace_deeplink_browser.mjs`,
  8 checks): the reported case, a deep link to a club that IS in the queue,
  no deep link at all still landing on row one, and a hand-picked club taking
  over. Reproduced first with the fix absent — the repro bounced to row one
  and rewrote the URL, exactly as reported.

### The deep link landed, but the queue never moved (v9.49.6)

- **`selectClub`'s own scroll fires 60ms after the call, which on a deep link
  is 60ms into a queue request that has not come back yet** — there is no row
  to scroll to, so nothing happened and the club sat correctly selected far
  down a list nobody moved. The queue's OTHER scroll (the re-anchor after an
  action) is deliberately skipped when `anchor === false`, and the first load
  is exactly that (`loadClubs({ anchor: false })` off the filters effect), so
  it never covered this either. `pendingScrollIdRef` is resolved in
  `loadClubs`'s own `.then`, the first moment the row can exist, and
  independently of `anchor`: that flag stops a FILTER TWEAK moving the
  viewport, and arriving on a link is not a filter tweak.
- **`block: 'center'`, not `'nearest'`** — a row 34 of 40 down should land in
  the middle of the rail where it can be read in context, not scraped onto
  the bottom edge.
- **A linked club the filters exclude has no row at all**, and a rail that
  silently highlights nothing reads as broken. It now says so and offers to
  clear the filters, which re-arms the pending scroll so the club is scrolled
  to once it appears.
- **Clearing every "Interested in" pill left the value behind.**
  `update_deal` guarded the recompute with `if keys:`, so an empty selection
  kept the old figure and the deal read "no modules" beside a four-figure
  value — the same value/modules drift the merge ratchet produced, reached
  from the other end. Setting the modules is a deliberate act and the value is
  the price of what was picked.
- **A DEAL HAS TO BE FOR AT LEAST ONE MODULE (v9.49.8), which settled the
  empty case for good.** `update_deal` refuses an empty `module_keys` on a
  platform deal, so the value can never be asked to price nothing. It is
  deliberately NOT "Stats must stay picked": a club already paying for Stats
  and trialling Select is a genuine deal for Select alone, and forcing Core
  back on would overstate it. Both surfaces refuse to unpick the last pill
  without sending anything, and the server refuses it for everything that is
  not the screen — `set_interest` needed its own `try/except ValueError`,
  since only the CRM route went through `_update_deal_or_422`.
- **The pills endpoint returns `get_club(...)`, so the rep's own pane already
  shows the recomputed figure without a reload**, and the CRM deal card reads
  the same row with no sync step in between — asserted both ways rather than
  assumed.
- **Verified**: 12 Chromium checks in
  `frontend/verification/verify_workspace_deeplink_browser.mjs` (the scroll
  into view, the row carrying the selected border, row one NOT selected, the
  outside-filters note, plus the four from v9.49.3), 6 in
  `verify_interest_pills_browser.mjs` (the last pill sending NOTHING, a
  single non-Stats module allowed, the message shown), and the Postgres
  interest suite is 29.

### Empty $0 wins, and a Trial deal listed as won (v9.49.9)

Both reported off the "Unattributed — deals won" drill-down: three deals for
one club, two with no modules at $0, and a row whose Stage column read Trial.

- **A WIN HAS TO BE FOR SOMETHING.** `sync_platform_deal_for_club` looks for an
  OPEN deal and creates one when there is none — so a `subscription_won` firing
  that resolved NO modules (`_org_billable_module_keys` returns `[]` for a club
  holding nothing billable at that moment) filed a $0 win, and every later
  firing found no open deal either and filed another. Reproduced exactly: one
  real $998 win plus two empty ones. It now hands back the club's most recent
  deal instead of minting an empty one — callers still get a real deal, so
  nothing that uses the return value breaks. Only guarded on a WON target
  stage: a module-less deal at Target is an ordinary prospect nobody has
  qualified yet, and several callers deliberately create one.
- **WON-NESS COMES FROM THE STAGE, NOT `status`.** `move_stage`, `close_deal`
  and `create_deal` all derive `status` FROM the stage, so the two normally
  agree and no current writer can separate them — but the live data has rows
  where they disagree, and the drill-down showed a Trial row under "deals won",
  a contradiction the reader cannot resolve. `sales_commissions.deal_state`
  reads the stage's own `is_won`/`is_lost`, falling back to `status` only when
  the stage cannot be resolved at all. A deal not sitting in Won therefore
  earns no commission, which is the conservative direction — nothing is claimed
  for a deal the board does not show as won.
- **Where those rows came from is NOT established**, and the fix deliberately
  does not paper over it: they are simply no longer counted. Every current path
  was ruled out by reading it, so they predate something (the Twenty import, or
  hand-written SQL). A query to inspect them is in the session notes below.
- **Verified**: the Postgres suite is 91 checks (the 86 before plus the corrupt
  shape built by hand and asserted absent from the won figures, present in the
  open ones, and never showing a Trial row under won), and the empty-win repro
  collapses three deals to the one real win.

### Commission is earned on a PAYMENT, not a stage (migration 278, v9.50.1)

Per direct instruction, after a drill-down showed deals as "won" that nobody
had paid for: **the criteria for a won deal are Stripe confirmations of actual
payments.**

- **A STAGE IS A JUDGEMENT, A PAID INVOICE IS A FACT.** Earned commission no
  longer reads `crm_deals` at all. `billing_invoices` — our own mirror of every
  Stripe invoice — carries `billing_reason`, `amount_ex_tax_cents`, and the
  stamped `commission_rep_user_id` / `commission_rate_percent` /
  `commission_cents` / `commission_kind`. The FORECAST still reads open deals,
  which is right: a forecast is about what might happen, and only a payment
  says what did.
- **ONLY NEW BUSINESS EARNS, and Stripe's own `billing_reason` is what says
  which** — no inference from line items. `subscription_create` is the club's
  first payment ('initial'), `subscription_update` is modules added to a live
  subscription ('expansion'), and `subscription_cycle` is a renewal, which
  earns nothing: a renewal is the club not cancelling, not a sale.
- **NET OF GST.** `total_excluding_tax`, falling back to what was paid minus
  the invoice's own tax amounts. Tax collected on our behalf was never our
  revenue, and commissioning it would overpay by the GST rate.
- **The rep and the rate are STAMPED on the payment when it lands** and never
  recomputed, so a rate change cannot rewrite what a past payment earned. The
  stamp is idempotent: a replayed webhook re-reads the same row and an already
  attributed invoice is not re-attributed if the club's attribution later moves.
- **`record_payment_commission` is called from `_upsert_invoice`**, the ONE
  place a payment is recorded, so a first subscribe and an add-on purchase are
  one behaviour. Best-effort: a commission bookkeeping failure must never fail
  the webhook that recorded the payment.
- **`crm_deals.commission_rate_percent` (277) is left in place and NOTHING
  reads it now** — the call migration 267 made for `vote_settings`. A second
  rate living on the deal could only ever drift from the one actually paid.
- **`deal_state` still decides open vs won for the FORECAST**, so a deal in Won
  leaves the pipeline; it just no longer earns anything by itself.
- **`python -m app.scripts.backfill_invoice_commission`** re-reads invoices
  recorded before 278 from Stripe and stamps them through the same function the
  webhook uses. The rate applied is the rep's CURRENT one — the rate on the day
  of a past payment was never recorded, and inventing one would be worse than
  saying so.
- **Verified against a real Postgres** (28 checks through the shipped webhook
  and report: the DDL applied three times, the first payment stamped with rep /
  rate / kind, a renewal recorded but earning nothing, an add-on earning as an
  expansion on the prorated amount, an unpaid invoice earning nothing, a rate
  change not rewriting a payment, a replayed webhook not paying twice, a deal
  dragged to Won earning nothing on its own, the drill-down adding up to the
  figure, an unattributed club's payment recorded but unearned, and the period
  filing), plus the other four suites re-run to 134.

- **Deliberately super-admin only.** Commission rates and payouts are management
  data about staff pay, which is a different thing from the Sales Workspace's
  per-rep view of their own clubs. The service still takes a `rep_user_id` pin,
  so opening it to a rep later is a route change rather than a rewrite.

### A Sales Workspace note on the CRM deal card (v9.53.9)

Asked for directly: a note added in the Sales Workspace — the "add a note"
box, not a call outcome — must be visible on the CRM deal's card.

- **IT WAS ALREADY ON THE WIRE, AND FINDING THAT OUT DECIDED THE WHOLE
  SHAPE OF THE FIX.** `sw.log_note` writes an ordinary `crm_activities` row
  against the SAME `crm_deals` row the Sales Pipeline board manages, and
  `crm_service.list_activities` has no type filter — so the card's endpoint
  was returning the note all along. Verified against a real Postgres through
  the shipped route bodies before touching a line of it. There is no sync to
  build and no missing field; the gap was entirely in how the card drew it.
- **THE CARD IS THE SHOWS-EVERYTHING SURFACE, WHICH IS EXACTLY WHY THE NOTE
  WAS LOST.** `list_activities_for_workspace`'s own docstring says the drawer
  filters the Twenty backfill and the reassignment audit rows and "the CRM
  Pipeline board still shows everything, by design". That design is kept —
  but a rep's note sat in a 192px scroll box among two dozen imported rows,
  under a bare `<Pill>{a.type}</Pill>`, with no author, no pin and no line
  breaks. Measured on a real-shaped deal: the pinned note rendered **1,785px
  below** the plain one, at the bottom of the import pile.
- **A `Notes (n)` filter, not a changed default.** The card still opens on the
  whole history — narrowing what it shows by default would be a different
  change from the one that was asked for. The filter is what makes the notes
  reachable in one click.
- **PINNED MEANS THE SAME THING ON BOTH SCREENS.** The card read `a.type` and
  nothing else, so `meta.pinned` — the rep's own "keep this in front of
  whoever picks this club up next" — was invisible. Pinned notes are lifted
  above the feed in the same amber the drawer uses, whichever filter is on.
  Pinning is still a Sales Workspace action; the card reflects it.
- **`activityLabel` / `activityTone` / `activityByLine` live in
  `components/admin/crm/ui.jsx` and BOTH screens read them** — the drawer's
  `ActivityRow` was rewired onto them rather than left as a second copy. The
  suite asserts the two screens name the same row identically rather than
  taking the comment's word for it; the drawer is compared on the rows it
  actually draws through them (a note, a call, a system row), since a pinned
  note is lifted into its own unlabelled block there.
- **`user_names_by_ids` moved to `services/crm.py`, and
  `sales_workspace.user_names_by_ids` delegates.** An activity's author is a
  CRM fact and the workspace is one reader of it, not its owner. Both
  activity endpoints (club scope AND platform scope) go through one
  `_activities_payload` builder, so the two can never drift about what a
  deal's timeline holds.
- **A HOOK BELOW `if (!open) return null` IS A HOOK-COUNT BUG, and the
  browser found it, not the build.** The first cut put the four `useMemo`s
  next to `contactOptions`, which sits after that early return — the modal
  renders closed most of the time, so React saw a different hook count
  between renders and the card died with "Rendered more hooks than during the
  previous render". `npx vite build` passes on it. Same family as the Roster
  temporal-dead-zone note above: anything a render body reads or registers
  has to sit above every early return.
- **PINNING FROM THE CARD (asked for straight after): `PATCH
  /deals/{id}/activities/{activity_id}` on BOTH scopes, taking `pinned`
  only.** A note is the one activity kind anything here lets a person
  rewrite — a call/email/system entry is a log of something that actually
  happened — so `_note_or_404` refuses anything that is not a note ON THIS
  DEAL, the same rule the workspace's own per-activity write already
  follows. `ActivityCreate.pinned` lets the card's composer write a note
  already pinned; `_new_note_meta` refuses it for a call, and an unpinned
  note still carries a NULL meta rather than `{"pinned": false}` noise.
- **`edit_note` moved to `services/crm.py` and the workspace delegates**, the
  same call `user_names_by_ids` made — a note is a CRM record and the
  workspace is one editor of it, not its owner. Both fields are optional and
  only a field that is PASSED is touched, so the card's one-click toggle
  cannot blank the text.
- **PINNING IS NOT EDITING, and `meta.edited_at` now says so.** The old
  writer stamped it on every save, so pinning a note would have marked it
  "(edited)" without a word of it changing. It is stamped only when the body
  actually differs — which also makes the WORKSPACE's own form honest, since
  it saves body and pin together and a pin-only save used to lie. Re-saving
  identical text is not an edit either.
- **Verified against a real Postgres** (`backend/verification/verify_deal_card_notes.py`,
  40 checks through the shipped route bodies and writers: the reported case
  replayed, the pin and the line breaks surviving onto the card, the author
  named and falling back to the username, a note still found among 31
  import/audit rows while the drawer still hides them, a call staying a call
  and a General Note staying a note with its outcome, an edit landing, a note
  added ON the card showing in the drawer, the club scope getting the same
  treatment with no platform note leaking into it, and an author-less system
  row reporting no name rather than breaking, plus the pin: the round trip
  both ways, the pin visible from the drawer, the three refusals, a note born
  pinned, a call refused one, and neither a pin nor an identical re-save
  stamping edited_at) and **driven in Chromium**
  (`verify_deal_card_notes_browser.mjs`, 35: the exact params on the wire for
  a pin, an unpin and a pinned create, the note moving into and out of the
  pinned block, and the pin control withdrawn once the composer's type is a
  call) **with a control run**: with the display change stashed, 7 fail on
  exactly the reported behaviour, and with the pin stashed the suite cannot
  find a Pin control at all.
- **Four checks passed against the broken code on the first cut and had to
  be tightened**: the byline matched the deal's OWNER (also "Sam Rep") through
  a too-wide section locator; the pinned note was dated newest, so a flat
  chronological feed put it on top anyway; the stub returned its rows in
  array order rather than `occurred_at DESC` the way `list_activities` does,
  so the arrangement was doing the work; and `Unpin` addressed by `.last()`
  unpinned whichever of two pinned notes sorted second, leaving the intended
  one pinned while still reading as a pass. A check that cannot fail is not a
  check. **The stub also has to MUTATE on a write** — one that answers the
  same thing every time cannot tell a working toggle from a no-op.
- **Noticed, NOT fixed**: the deal card modal overflows 360px at 390px.
  Confirmed pre-existing by re-measuring with the change stashed (identical
  either way; the widest element is a 726px `flex items-center gap-2` row this
  change does not touch). The suite budgets the measured number so this can
  never make it worse.

### A sales email that reported itself sent, and was not (v9.51.4)

Reported: the club never received the trial-extension email the rep had been
told was sent.

- **THE CONSOLE PROVIDER IS A FAILURE, NOT A SUCCESS, and reading it as one is
  the whole bug.** `email_service.get_email_provider` falls back to
  `ConsoleEmailProvider` whenever the configured provider is missing or has no
  key — deliberately, so a misconfigured deploy never sends unauthenticated
  mail — and console's own `send` writes a log line and returns `ok=True`.
  `send_sales_email` only raised on `not result.ok`, so every caller recorded
  the email as sent. A rep could work a club for a week believing each email had
  gone out.
- **`sales_email.EmailNotLive` is its own type** because it is not a delivery
  failure: there was no attempt. The compose endpoint turns it into a 503 the
  rep reads, and `extend_trial` records `email_sent=false` with the reason, so
  the extension still lands and the confirmation says to reach them another way.
- **`send_sales_email` returns the provider and the message id**, stamped onto
  the activity's meta, so "did that actually go?" has an answer months later
  rather than a bare "sent".
- **The drawer says so BEFORE the rep writes anything** (`email_templates` now
  carries `provider_status()`), which is what the Comms screens already did and
  this one never had.
- **Verified** (14 checks through the shipped function: console refusing, a
  selected-but-keyless provider falling back and refusing too, the wording, a
  live provider's id and reply-to, and a rejected send raising something that is
  NOT "not connected"), with a control run showing the old code returning
  normally with nothing configured.
- **Still to do on the server, not in code**: `email_provider` defaults to
  `console`, so a deploy with no provider configured sends nothing at all — and
  `bettersports.com.au` still needs SPF/DKIM/DMARC before mail authenticates.
- **A CONTACT TYPED INTO THE DRAWER IS NOT THE PROBLEM, and that was worth
  proving rather than assuming.** 18 checks through the shipped `extend_trial`
  and `send_email` bodies with a stand-in provider: the address typed into
  "+ New contact" is byte-for-byte the address the provider is handed (case
  folded — `_store_contact` lower-cases, since it dedupes on `lower(email)`),
  the mobile is stored, one `CrmPerson` is bridged rather than two, a later
  compose to the same contact reaches the same address, and the activity records
  the provider and message id. A re-test on the live site received the email, so
  a non-delivery there is the provider's or the recipient's, not the capture.
- **The timeline now carries the evidence** — the address, the provider and its
  message id on a send, and `Not sent` with the reason where the extension's
  email failed. "They say they never got it" is answerable from the record.

### A club that loaded forever, then failed (v9.51.3)

Reported off the Sales Workspace: opening Blacktown District Cricket Club sat on
"Loading…" and eventually said "Could not load this club".

- **A SWALLOWED DATABASE ERROR LEAVES THE TRANSACTION ABORTED, and that is what
  took the request down.** `get_club`'s two best-effort analytics reads
  (`club_visit_detail`, `club_engagement_breakdown`) were wrapped in
  `try/except … the drawer must still render without it` — but neither rolled
  back, so after the first failure every later statement in that request came
  back `InFailedSQLTransactionError: current transaction is aborted`. Reproduced
  against a real Postgres: with the fix stashed the suite dies on a plain
  `SELECT 1` after the handler returns. **Same class as the `audit_logs` trap
  this file already documents** — an `except` that hides a database error must
  `await db.rollback()` before carrying on.
- **`get_club_signals._safe` had the identical cascade**: three cards in
  sequence, so the first failure emptied the two after it whatever they were
  going to do.
- **THE TWO ANALYTICS READS ARE OUT OF THE DRAWER PAYLOAD** and live at
  `GET /clubs/{deal_id}/analytics`, fetched after the pane renders. They are the
  only expensive work in that handler — one walks `usage_events`, the other
  recomputes the score and scans `email_events` with `lower(email) IN (…)` — and
  on a club with real history they can outlast nginx's own 60s read timeout,
  which is what "loading, then an error" actually was. **Exactly the call the
  boundary already made** in the same file, for the same reason.
- **`engagement` and `website_visits` stay on the wire as nulls**, so a browser
  served an older bundle mid-deploy reads the keys it expects rather than
  crashing — the `plan_report.unassigned` rule.
- **Verified against a real Postgres** (13 checks through the shipped route
  bodies with a read deliberately failing: the drawer opening, its timeline and
  trial countdown, the analytics absent but their keys present, the session
  still usable afterwards, the analytics endpoint degrading to nulls rather than
  raising, and one failed signal card leaving the others alone) with a control
  run that fails on exactly the reported behaviour.

<!-- END original CLAUDE.md L3894-4428 -->
<!-- BEGIN original CLAUDE.md L4429-4486 -->
## A quiet week is not an empty book (v9.52.2, Aug 2026)

Reported off Sales Performance on a Monday morning: Contact activity read
"Nobody has made contact this week yet." while the team had been calling clubs
for months. Every figure on the screen was correct and every one of them was
about a window that had barely started.

- **ALL TIME IS NOT A LONGER WINDOW, IT IS NO WINDOW.** `report_windows` gains
  `'all': None` — a lower bound of None, read by every caller as "do not
  filter". Deliberately not an early date: an arbitrary epoch would quietly
  become the start of the club's history, and the first club whose records
  predate it would be silently short.
- **A REP IS LISTED AS SOON AS THEY HAVE EVER MADE CONTACT.** The rows come
  from the same pass, so the table now says something whatever the day. **The
  ORDER is unchanged** — this week, then today, with all time only as the
  tiebreaker: the two dated windows are what a working day is managed on, and
  all time decides the order precisely when they are all zero, which is the
  morning this exists for.
- **`REPORT_WINDOWS` is the one list**, and the screen's column groups and KPI
  rows are drawn from it. A fourth window would be one tuple entry plus one
  entry in the frontend's `ACTIVITY_WINDOWS`, not a third hand-written column
  block.
- **AN ALL-TIME PULL MUST NOT DRAG EVERY SENT EMAIL'S HTML WITH IT.** The
  dated windows could afford `select(CrmActivity)`; reading every contact row
  ever written cannot, because an email activity's `meta` holds the whole
  message body (`routers/sales_workspace.py` stamps subject/html/text onto it).
  `_contact_rows` selects the six columns a tally reads plus a Twenty flag, and
  is now the ONE place "the contact rows in scope" is defined — shared by the
  report, the drill-down and `contacted_deal_ids`, which was already paying
  that cost unbounded on the same page.
- **`_IS_TWENTY_IMPORTED_SQL` is derived from the same `_TWENTY_IMPORT_META_KEYS`
  tuple as `_is_twenty_imported`**, so the SQL and the Python cannot disagree
  about what an imported row is; the suite asserts they agree row by row. `?`
  against a NULL meta yields NULL, which is False in Python and correct — a row
  with no meta has no keys. This is the one place a JSONB key test is safe in
  SQL here: the trap `list_activities_for_workspace` documents is `NOT (meta ?
  'k')` in a WHERE, and this is a selected value, not a filter.
- **`_contact_kind` still takes any row carrying the four fields it reads**, so
  a full CrmActivity and a lean reporting row are classified by one function.
  `_row_contact_kind` is the wrapper that always passes the flag, since a lean
  row deliberately carries no `meta` to read it from.
- **Verified against a real Postgres** (75 checks through the shipped service
  and route bodies: the reported case replayed — today and this week zero, six
  contacts behind them, two reps listed — every contact rule holding all time
  as well as this week, a Twenty-imported row and a general-outcome call still
  excluded, clubs_contacted distinct rather than summed, the drill-down for
  each window/metric adding up to the cell it opens, an unknown window refused,
  a 'sales' caller pinned to their own work even when naming another rep, the
  lean row carrying neither `meta` nor `body`, and the SQL and Python Twenty
  tests agreeing on every seeded row) **with a control run**: with the change
  stashed the same data reads 0 rows and no all-time window at all, exactly as
  reported. **Driven in Chromium** (20: the three KPI rows and three column
  groups in order, a rep listed on a blank week, the twelve figure cells, a
  zero still not a button, the group rules measured off the computed style,
  the exact params on the wire for an all-time drill-down and the panel it
  opens, the totals row matching the KPI card, no page errors, no overflow at
  390px).

<!-- END original CLAUDE.md L4429-4486 -->
<!-- BEGIN original CLAUDE.md L4487-4527 -->
## Every figure on Sales Performance opens its clubs (v9.48.2, Aug 2026)

Asked for directly: make every number in both tables clickable and list the
clubs behind it, and rename the pipeline card.

- **A CELL AND ITS LIST ARE COMPUTED BY THE SAME CODE, and that is the whole
  design.** `_classified_deals` was extracted out of `stage_breakdown_by_rep`
  and is what both the table and `pipeline_cell_clubs` read, so a deal cannot
  land in one column for the count and another for the list.
  `activity_cell_clubs` re-runs `_contact_kind` + `report_windows` for the same
  reason. A second query shaped like the first is how a cell reading 14 opens
  13 clubs.
- **The verification walks EVERY cell of both tables**, not a sample — each
  rep, the totals row, every stage column, both the total and the bracketed
  figure, both windows, all four metrics. One disagreeing cell is the bug, so
  a sample would not have been evidence.
- **Three of the four activity metrics count ACTIVITY, not clubs**, so 24
  contacts is legitimately 10 clubs. Those payloads carry `total` AND
  `club_count`, each row carries its own `count`, and the panel says both.
  `clubs_contacted` is the one metric where the list length is the number.
- **The pin is applied SERVER-SIDE from the actor, never read off the params.**
  The cell's identity (whose row, which column) arrives from a browser, so a
  'sales' caller asking for `owner=all` still gets only their own — the same
  rule the queue list already follows.
- **A zero is not a button.** There is nothing behind it, and a table this
  wide stays readable when only the live figures are underlined.
- **One drill-down at a time, rendered under its own card** rather than in a
  dialog: the cell stays on screen, so a run of cells can be compared without
  reopening anything, and clicking a pipeline cell closes an activity one.
- **A row links to `?club=<deal_id>`**, the deep link the Sales Workspace
  already takes, so the list hands off to the drawer rather than being a
  dead end.
- **Verified against a real Postgres** (73 checks, the 58 before plus the
  every-cell walk both ways, a contacts cell reporting total and club_count
  separately, the pool drilling down to unowned clubs only, a pinned rep
  never seeing another rep's, and three refusals) and **driven in Chromium**
  (34: the exact params on the wire for a stage total, its bracketed twin,
  the totals row and an activity cell, the panel's heading and rows, only one
  list open at a time, the deep link, a zero opening nothing, the measured
  click affordance, no page errors, no overflow at 390px).

<!-- END original CLAUDE.md L4487-4527 -->
<!-- BEGIN original CLAUDE.md L4528-4591 -->
## Sales Performance: where the clubs sit, and who actually rang them (v9.47.1, Aug 2026)

Asked for off `/admin/super/crm/performance`: unassigned deals per stage, an
Assigned column that means "still to contact", stage columns rather than a
cumulative funnel, and a section answering "how many calls has each rep made
today".

- **The funnel was cumulative and the screen now shows a DISTRIBUTION.**
  `funnel_by_rep`'s assigned → attempted → contacted → engaged → trial → won
  counted the same deal in every bucket it had passed through, so no column
  told you where a club actually is. `stage_breakdown_by_rep` puts each deal in
  exactly one column, which is what makes an Unassigned row and an All-clubs
  total add up.
- **EVERY CELL CARRIES TWO FIGURES, and that is the whole compromise.** Total
  and, in brackets, the ones the rep has really made contact with. Contacted-only
  would have emptied the Unassigned row (almost nothing in the pool has been
  rung, so its stage spread — the thing that was asked for — would have vanished
  into one column); totals-only would have said nothing about whether a rep had
  worked the clubs. The pair answers both from one table.
- **`_IS_CONTACT_ROW` / `_contact_kind` are the ONE definition of contact**
  (a logged call, a follow-up recorded, or an email sent), shared by the stage
  brackets, the activity table and the KPI strip. A note is not contact, and a
  Twenty-imported row never counts, for the reason `emailed_deal_ids` already
  gives: it is a backfill of somebody else's pipeline. The SQL predicate and the
  Python classifier sit next to each other deliberately — a query that selects
  more rows than the tally accepts is how the two start disagreeing.
- **A follow-up is checked on its own rather than nested under a call**, the
  same call `call_statuses_of` already makes: today a callback can only be
  captured off a call log, but one recorded some other way still counts.
- **ACTIVITY IS COUNTED BY WHO DID THE WORK** (`crm_activities.created_by_user_id`),
  not by who owns the deal, which is what `performance_summary` used to do. "How
  many calls has this rep made today" is a question about the rep, and a call on
  a club since reassigned is still theirs.
- **The KPI strip IS the activity table's totals row**, derived from one pass in
  `activity_report` rather than counted twice. `clubs_contacted` is a genuine
  distinct count across everyone, never a sum of per-rep distinct counts — that
  is the figure a second query would have got wrong.
- **Today and this week are PERTH days** (`report_windows`). The UTC boundary the
  old summary used starts at 8am local, so a rep's whole morning read as
  yesterday's work. Week starts Monday.
- **EVERY NAMED STAGE IS ALWAYS DRAWN, `proposal` included.** An empty Proposal
  column is itself the answer to "is anybody at proposal", which a column that
  comes and goes cannot give. Only `other` — the catch-all for a pipeline stage
  this list doesn't name — is conditional (`stage_columns` reports what to
  draw), because dropping a deal from the table for sitting in an unnamed stage
  is worse than an extra column nobody asked for.
- **A rep with nothing assigned still gets a row**, seeded from the sales-role
  memberships — an empty book is exactly what this screen should make obvious,
  and they would otherwise be invisible.
- **Only trial-stage deals have their clubs loaded** for the current/expired
  split; the whole book would be a far bigger read for a split that cannot apply
  to the rest. No trial dates at all reads as CURRENT, matching the queue's own
  `trial_current`/`trial_expired` filter.
- **Verified against a real Postgres** (58 checks through the shipped service
  and route bodies: each contact route counted and a note and a Twenty row not,
  to_contact + contacted reconciling with the total, the archived deal excluded
  from the breakdown while its call still counts as work done, all three trial
  cases, the pool's stage spread, an idle rep drawn, an empty Proposal column
  still drawn and no deal dropped, the distinct-not-summed club count, a sales caller
  pinned to themselves however they ask, and the Perth boundaries either side of
  8am) and **driven in Chromium** (18: the column order asked for, a rep row's
  total-and-brackets, the Unassigned and All-clubs rows, both totals rows
  agreeing with the cards above them, no page errors, no overflow at 390px).

<!-- END original CLAUDE.md L4528-4591 -->
<!-- BEGIN original CLAUDE.md L10168-10209 -->
## Three voicemail follow-ups: offer the trial, then extend it (v9.46.1 / v9.48.1, Aug 2026)

`voicemail_followup_extend_trial` gained a sibling,
`voicemail_followup_extend_trial_soon`, and the pair now name the moment
rather than the offer.

- **The dropdown order IS `TEMPLATE_LABELS`' insertion order**
  (`email_templates` maps over the dict), so approaching-expiry is declared
  before already-expired — the order a rep works down a trial.
- **A sales template's row in Comms → Templates prints its NAME and, under it,
  `Sales: <dropdown label>`.** So the two are allowed to differ, and for these
  two they do: `TEMPLATE_DB_NAMES` gives each a shorter name, because repeating
  the whole dropdown sentence in the name says the same thing twice on one row.
- **The rename is a guarded UPDATE inside `seed_sales_templates`**, keyed on
  `sales_template_key` AND the row's OLD default name, so a super admin who has
  renamed it themselves keeps their own. The list of (key, was, now) triples is
  the one place a rename lands; add to it rather than writing another UPDATE.
- **Two templates that read the same are one template with two names**, so the
  bodies differ by a paragraph: one says the trial finishes shortly and offers
  to extend it, the other says it has finished and offers to put it back on.
- **A third one, `voicemail_followup_trial_offer`, offers the trial itself**
  ("Email following voicemail - trial offer" in the dropdown, `Email following VM.
  Trial offer` in Comms). It sits IMMEDIATELY after the general follow-up and
  above the two extend-trial ones, because offering a trial is the earlier
  moment than extending one. Copied from `trial_information` per instruction — the same six
  steps, the same `/trial` button, the same subject — behind the "I've left a
  voicemail" opener the other three share. **That opener is the only thing
  separating the two templates**, which is exactly the point: without it this
  would be `trial_information` under a second name.
- **Adding a sales template means SIX places**: `TEMPLATE_LABELS` (the dropdown,
  and its insertion order IS the order shown), `TEMPLATE_DB_NAMES` if the Comms
  name differs, `BUILT_IN_TEMPLATES`, a branch in `_render_template_hardcoded`,
  `_SEED_BODY` and `_SEED_SUBJECT`. The suite asserts every built-in has a
  label, a seed body and a seed subject, so a half-added one fails rather than
  rendering blank.
- **Verified against a real Postgres** (37 checks through the shipped
  `seed_sales_templates` against a database already carrying the previous
  seed: each new key inserted exactly once, the rename landing, a hand-renamed
  row left alone, a second run doing nothing, the seeded bodies' `{{merge}}`
  tokens surviving the `{base}` substitution, the dropdown order, and each
  built body differing from the one it was copied from).

<!-- END original CLAUDE.md L10168-10209 -->
<!-- BEGIN original CLAUDE.md L13889-14029 -->
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

<!-- END original CLAUDE.md L13889-14029 -->
