# Parameterising the Engagement Score

A design note for making every number in the engagement-score calculation
editable by a Super Admin, from a page linked off the CRM hub, instead of
living as constants in `backend/app/services/twenty_sync.py`.

**Status: BUILT (v9.38.0).** Sections 1 to 7 describe the design; what shipped
follows it, with the deviations noted below. Sections 8 and 9 are findings about
the scoring itself, most of which are NOT yet acted on and are the natural next
piece of work.

What shipped:

- `backend/app/services/engagement_params.py` — the catalogue of 53 parameters,
  validation, the sparse override store and the in-process cache.
- `backend/app/services/engagement_param_ddl.py` + migration 270 —
  `engagement_parameter_revisions`, the audit trail and rollback source, with
  the DDL shared between alembic and the lifespan mirror.
- Weights threaded through `_engagement`, `batch_web_stats`,
  `batch_email_stats`, `_recency_pts`, `_tier_for`, `trial_depth_score`,
  `sync_pipeline_membership` and both sweeps. The four hand-written decay
  ladders collapsed into one `_decay_arms` builder.
- `GET`/`PATCH /club-admin/super/crm/engagement-params` and
  `POST .../preview`.
- `frontend/src/pages/admin/SuperEngagementParams.jsx` at
  `/admin/super/crm/engagement-params`, a CRM hub tile, and a Scoring button on
  the Sales Pipeline toolbar.
- `python -m app.scripts.verify_engagement_params` asserts the defaults score
  exactly as the constants they replaced did, including the generated SQL
  byte-for-byte.

Deviations from the plan below, all deliberate:

- Phase 2 and 3 landed together, because the preview is what makes the
  membership floor safe to touch and shipping the floor without it would have
  been the wrong order.
- The two defects in section 8a and 9c are shipped as parameters defaulting to
  the OLD behaviour (`ENQUIRY_OVERRIDE_IS_FLOOR`, `COUNT_ONLY_PAGE_VIEWS`)
  rather than fixed outright. Both move real scores, so they are a decision to
  take with the preview open, not a side effect of a deploy. **Neither is on.**
- `DEPTH_PER_VISITOR_CAP` (section 9d) shipped as a parameter, also off by
  default.
- Revision history is recorded and displayed; one-click rollback to a previous
  revision is not built yet.
- "Club Selected" as a new scored signal (section 1) is not built.

This is the shape of the work, the traps found while reading the current code,
and a straight answer to the recalculation question.

Section 8 is a separate question that came out of the same reading: whether the
current scoring is sound. It is not entirely, and one of the findings is a
defect rather than a tuning choice, so read that before deciding what the page
should default to.

## 1. Where the numbers live today

Two files hold every weight:

- **`services/twenty_sync.py`**, lines 43 to 117, one block titled "Engagement
  scoring weights", plus a few values inlined in the customer branch.
- **`services/trial_engagement.py`**, lines 52 to 60, the self-serve setup-depth
  rollup that acts as a floor on a prospect's score.

`_engagement(session, club, org)` is the one function that turns them into a
score. It caches its answer straight onto the club row
(`marketing_clubs.engagement_score` / `.engagement_tier` / `.engagement_scored_at`,
via `_apply_engagement_cache`), and everything downstream reads that cached
number rather than recomputing.

### "Club Selected" is not a weight today

The worked example in the request was "Club Selected is currently worth 15
points". There is no such parameter. Worth settling before anything is built,
because it changes the scope:

- The trial wizard's `club_prepared` beacon (a visitor picking their club) feeds
  the Meta Ads funnel (`routers/meta_ads.py::get_club_selected_count`) and the
  Wizard Clubs CRM page (`services/wizard_club_lists.py`). Neither of those
  touches the engagement score. `grep club_prepared` across `twenty_sync.py`,
  `trial_engagement.py` and `crm.py` returns nothing.
- The nearest thing that IS scored is `BONUS_VISIT_TRIAL = 20`, awarded when an
  attributed visit hits the `/trial` page at all, whether or not a club was then
  selected.
- The nearest 15 in the code is `IMPORT_STATS_BONUS = 15` in the trial-depth
  rollup, and `MODULE_GROUP_CAP = 15`.

So "make Club Selected worth 10 or 20" is a request to **add a new scored
signal**, not to expose an existing knob. It is a good one: picking a club in
the wizard is a stronger intent signal than merely landing on `/trial`, and the
beacon is already recorded. It just needs its own attribution query alongside
`visited_contact` / `visited_trial` in the web block of `_engagement`. Treat it
as a separate small piece of work that lands on top of the parameter framework
rather than as part of it.

## 2. What there is to parameterise

Around 45 numbers, in nine natural groups. Grouping matters, because a flat
list of 45 inputs is unusable and hides which knobs interact, and because one
group carries far more weight than the other eight put together.

**Pipeline membership**, the two numbers that decide whether a club appears on
the board at all. Neither exists yet. See 2a below, this is the highest-leverage
control on the page.
- `PIPELINE_ADD_MIN`, the score at or above which a club is auto-added to the
  pipeline as a Target deal. Today this is hardcoded as `score > 0` in
  `crm.sync_pipeline_membership`, so the effective value is 1.
- `PIPELINE_REMOVE_BELOW`, the score under which an auto-added Target deal is
  archived back off the board. Today hardcoded as `score == 0`, so the effective
  value is also 1.

**Recency** (`_recency_pts`, a smooth exponential decay of the single most
recent touch of any kind)
- `RECENCY_FULL` 10.0, points at zero days old
- `RECENCY_HALFLIFE_DAYS` 21.0

**Organic web decay** (`WEB_DECAY`), points per page view or API call by its own
age: `d7` 2.0, `d14` 1.5, `d21` 1.0, `d28` 0.5, `d90` 0.25

**Paid ad-click decay** (`AD_DECAY`), the richer curve for a Meta or paid
landing: `d7` 5.0, `d14` 3.5, `d21` 2.0, `d28` 1.0, `d90` 0.5

**Email decay**, click weighted above open because a pixel-fired open can come
from Apple Mail Privacy Protection with nobody reading it
- `EMAIL_CLICK_DECAY` 10.0 / 7.5 / 5.0 / 2.0 / 1.0
- `EMAIL_OPEN_DECAY` 4.0 / 3.0 / 2.0 / 1.0 / 1.0

**Frequency scaling**, how reach and depth convert to points
- `REACH_PER_VISITOR` 2.5, points per distinct 30-day visitor
- `DEPTH_SCALE` 0.6, multiplier on the summed per-event decay points

**Prospect intent bonuses**
- `BONUS_REQUESTED_TRIAL` 12
- `BONUS_IN_TRIAL` 10
- `BONUS_ONBOARDING` 20 (a direct "onboard my club" enquiry)
- `BONUS_CONTACT_PAGE` 10
- `BONUS_VISIT_TRIAL` 20
- `BONUS_AD_SIGNUP` 10

**Customer account health** (the branch for a club holding a paid module)
- `CUSTOMER_BASE` 60
- `CUSTOMER_UPSELL_BONUS` 15
- `CUSTOMER_ONBOARDING_BONUS` 10
- Three values currently inlined rather than named, which should be pulled out
  and named as part of this work: the `0.5` multiplier on recency, the `0.5`
  multiplier on frequency, and the `20` cap on the frequency contribution
  (`twenty_sync.py` line 770)

**Trial depth** (`services/trial_engagement.py`, the self-serve setup-effort
floor)
- `REGISTRATION_CLUB_ADMIN` 70, `REGISTRATION_SUPER_ADMIN` 40
- `SUPER_ADMIN_ACTOR_FRACTION` 0.3, the discount applied when staff did the work
  on the club's behalf rather than the club doing it itself
- `MERGE_BONUS` 10, `IMPORT_STATS_BONUS` 15
- `MODULE_GROUP_BONUS` 2, `MODULE_GROUP_CAP` 15
- `ADMIN_POLISH_BONUS` 2

**Bands and overrides**, the knobs with the largest blast radius
- `TIER_WARM_MIN` 30, `TIER_HOT_MIN` 60
- `DIRECT_ENQUIRY_SCORE` 80, the flat score a recent direct enquiry pins a
  prospect to. Its companion window, `direct_enquiry_hot_days`, is already
  super-admin editable from General Settings, so this is the one parameter with
  half the job already done.
- `OPPORTUNITY_AUTO_THRESHOLD` 90, at or above which
  `twenty_leads_tasks._seed_and_refresh_leads` creates a real Twenty
  Opportunity

Deliberately **not** parameterised, at least in a first pass: the day boundaries
themselves (7 / 14 / 21 / 28 / 90) and the 30-day session window. They are
`INTERVAL` literals inside four separate SQL statements, changing them means
changing the shape of the curve rather than its height, and the tier labels
(`d7`, `d14`) are dictionary keys the whole codebase reads. Adding a sixth tier
is a code change either way. Say so on the page rather than leaving people
hunting for a control that is not there.

### 2a. The membership floor needs two thresholds, not one

`crm.sync_pipeline_membership` is what decides relevance in the most literal
sense. Score above zero and a club with no existing deal gets one auto-created
at Target, valued at the Stats default. Score at zero and an auto-added deal
still parked at Target is archived off the board. With around 6,000 directory
clubs, moving that boundary from 1 to, say, 15 is the difference between a
pipeline and a phone book, and it is the one knob nobody would think to look
for in a block of scoring weights.

It cannot be exposed as a single number, though, and the reason is worth
setting down.

At zero the boundary is naturally sticky. A score of exactly zero means no
attributed activity at all, so a club does not drift back and forth across it.
Anywhere in the middle of the range it is not sticky: a club sitting near the
threshold will cross it in both directions as its decay points tick down and a
fresh page view ticks them back up. That matters more than a flapping log line,
because **re-entry creates a NEW deal row**. The "already has a deal" guard
excludes archived deals (`CrmDeal.archived_at.is_(None)`), which is exactly what
lets a re-engaging club come back, but it also means a club oscillating around
the floor accumulates a trail of archived deals and starts fresh each time.

So model it as a deadband: add at or above `PIPELINE_ADD_MIN`, remove below
`PIPELINE_REMOVE_BELOW`, with the remove threshold constrained to be less than
or equal to the add threshold. Defaulting both to 1 reproduces today's behaviour
exactly (add at `>= 1` is `> 0`; remove at `< 1` is `== 0`), so this ships as a
no-op and a Super Admin opens the gap deliberately, for example add at 20 and
remove below 10.

Two things about the existing code make raising the floor safer than it sounds,
and they are worth saying on the page so nobody hesitates over a control they
should be using:

- Archiving only ever touches an **auto-added deal still sitting at Target**. A
  hand-added deal (`source = "manual"`), one that was hand-moved
  (`stage_auto_locked`), and anything that has advanced to Contacted, Engaged,
  Trial, Won or Lost are all left alone. Raising the floor cannot destroy worked
  deals, only clear out cards nobody has touched.
- It is reversible. Lower the floor again and the clubs return on the next
  sweep, though as new cards rather than the originals.

The archive activity line currently reads "Auto-removed from pipeline:
engagement decayed to 0" and would need to quote the configured floor instead.

## 3. Storage

**Recommendation: a sparse override dict in the existing `platform_settings`
JSONB singleton, under one key (`engagement_weights`), plus a small revisions
table for history and rollback.**

The precedent for the sparse dict is already in `platform_settings.py`:
`bundle_discount_schedule`, `demo_booking_links`, `background_process_settings`
and `backup_schedule` are all nested objects with a dedicated getter, a
dedicated setter and their own validation, kept out of the generic `_INT_KEYS` /
`_BOOL_KEYS` path. No migration for the values themselves.

Sparse matters. Store only what a Super Admin has actually changed, so
`{"BONUS_CONTACT_PAGE": 15}` and nothing else. Every untouched knob keeps
falling through to the code default. The constants block records several rounds
of deliberate tuning (the saturating caps that were removed, the linear reach
and depth scaling that replaced them), so code defaults will keep moving, and
a full snapshot in the database would silently freeze a club's scoring at
whatever the defaults happened to be the day someone first opened the page.

The alternative, a row-per-parameter table on the `CrmAutomationRule`
(migration 190) model, buys less than it looks like it does. That table earns
its keep because the rows themselves are the vocabulary: a Super Admin can add
a third `engagement_score` rule at a new threshold, and the resolver picks a
winner. Here the vocabulary is fixed by the formula. You cannot add a
`BONUS_ATTENDED_WEBINAR` without writing the query that detects it, so a table
would only ever hold the same 45 rows, each needing its label, help text,
default, range and group defined in code regardless.

What a table IS worth having is the **history**. One small migration for
`engagement_parameter_revisions`: the full resolved snapshot as JSONB, the
actor, the timestamp, an optional note, and the summary of the recalculation
that followed (clubs scored, tier counts before and after, deals promoted).
Rollback then means re-applying revision N, and "who dropped HOT to 50 and what
happened" is answerable. Mirror the create idempotently in `main.py`'s lifespan
as usual.

The catalogue itself (label, help text, default, min, max, group, units) lives
in code, in one dict shaped like `crm_rules.TRIGGERS`. One deviation from that
precedent is worth making: `crm_rules` mirrors its catalogue by hand into
`frontend/src/components/admin/crm/automationTriggers.js`. With 45 entries and
real explanatory copy on each, a hand-kept mirror will drift. Serve the
catalogue from the API instead, so `GET /engagement-parameters` returns
catalogue, current values and defaults together and the page renders whatever
it is given.

## 4. The read path, and the traps in it

This is where the work actually is. Three things make it more than a
find-and-replace.

**The decay curves are interpolated into SQL in four places, not one.**
`WEB_DECAY` and `AD_DECAY` appear in `batch_web_stats` (line 410 onward) and
again in `_engagement`'s own per-club web query (line 606 onward). The email
curves appear in `batch_email_stats` (line 479) and again in `_engagement`'s own
email query (line 700). The batch pair exists as the single-pass equivalent used
by a full recalculation, and `recalc_engagement --verify` exists precisely to
assert the two paths agree. Weights must be threaded into all four, or the
nightly sweep and a live single-club rescore will quietly disagree and only
`--verify` will notice.

**`_engagement` is a hot path.** `crm.check_web_signal_promotion` fires it from
the write path of every web page view and every email open or click, debounced
20 seconds per club. A full recalculation calls it around 6,000 times in a loop.
So the weights must be resolved once and passed down, never fetched per call.
Two mechanics, both with precedent in this codebase:

- An in-process cache with explicit invalidation on save, exactly like
  `platform_settings.cached_send_rate` / `warm_send_rate_cache`. The deploy is a
  single uvicorn process, which is the same assumption the rate limiter and
  `crm._LAST_SCORE_RECOMPUTE` already make.
- An explicit `weights=` argument on `_engagement`, `batch_web_stats` and
  `batch_email_stats`, resolved once by `recalc()` and injected, the same way
  `web_stats=` and `email_stats=` already are. This is what keeps a 6,000-club
  sweep honest: every club in one run must be scored with the same weights, even
  if someone saves a change mid-sweep.

**Interpolating a stored value into SQL is a new surface.** Today these are
literals in source. Coerce to `float` in the validator, so by the time anything
reaches an f-string it is provably numeric. If binding as a parameter is
preferred instead, wrap it as `CAST(:w7 AS float8)` rather than a bare `:w7`.
A bare parameter inside a `CASE ... THEN` gives asyncpg nothing to infer a type
from, which is the same class of failure as the `AmbiguousParameterError` noted
in `CLAUDE.md` for `:param IS NULL`.

## 5. The Super Admin surface

**It is a relevance page, not a weights page.** That framing decides the
layout. Three separate levers control what the pipeline treats as relevant, and
the scoring weights are only one of them:

1. The **membership floor** (2a above) decides whether a club is on the board.
   Not editable today. Belongs at the top of this page.
2. The **promotion rules** decide which stage a deal lands in and at what score.
   Already editable, as `CrmAutomationRule` rows on the Sales Automation page
   (`services/crm_rules.py`, migration 190). This page should link to that, not
   restate it.
3. The **weights** decide the number the other two are compared against. They
   are the bulk of the controls and the least of the leverage.

Built as 45 free-floating knobs it is a way to make the score worse, because
there is no loop between changing `WEB_DECAY['d14']` from 1.5 to 1.2 and knowing
whether the pipeline improved. Built floor-first, with the preview below, it is
a genuine control surface.

**Page**: `/admin/super/crm/engagement-parameters`, reached three ways.

- A tile in the CRM hub (`SUPER_SECTIONS.crm.items` in
  `frontend/src/lib/superNav.js`). Items in that section are kept alphabetical,
  so "Engagement Score Parameters" sits between "Directory Segments" and "Sales
  Management".
- A button on the Sales Pipeline toolbar beside the existing Settings and
  Recalculate buttons (`SuperCrm.jsx` line 1475), because that is the screen
  where a score is actually being looked at when someone decides it is wrong.
- Nothing on General Settings. That modal already carries the trial, billing,
  bundle-discount and marketing settings, and 45 more numbers would bury them.

**Layout**: membership floor and tier bands open at the top, since those are
what most visits are actually about, then the eight weight groups as collapsed
sections, then a link out to Sales Automation for the stage rules. Each
parameter is a number input with its label, its help text, its current value,
its code default and a reset-to-default control. Show the default next to the
value at all times: with a sparse store, "this one has been changed" is real
state worth seeing.

Beside the membership floor, show what it currently means. The pipeline's own
deal count and the club count at or above the proposed floor are both cheap
queries, so the page can say "1,240 clubs on the board now, 310 at or above 20"
while someone is typing the number.

**Three things the page has to say out loud**, because they surprise people:

1. A score is clamped to 100. Raising every weight does not spread clubs out, it
   piles them up at the ceiling.
2. `DIRECT_ENQUIRY_SCORE` and the trial-depth floor **override** the recency and
   frequency formula. A club inside its direct-enquiry window scores a flat 80
   no matter what the decay curves say, and an onboarded prospect's score is
   floored at its setup depth. Tuning the web weights does nothing for those
   clubs.
3. A customer scores on a completely different branch. Half the parameters on
   the page do not apply to a paying club at all.
4. Raising the membership floor archives cards. It only ever touches auto-added
   deals still parked at Target, never a hand-added, hand-moved or advanced
   deal, and it is reversible. Say both halves, or nobody will touch the control
   that matters most.

**Preview before save is the feature that makes the page worth building.**
`recalc_engagement` already has `--dry-run`, and it already prints a histogram
in bins of 5 plus min / p25 / median / p75 / p90 / max / mean, split between
linked clubs and directory-only prospects. Expose that: run the proposed weights
against live data without persisting, and show the before and after
distribution, the tier counts either side, how many clubs cross into HOT, how
many deals would auto-promote, and how many cards would join or leave the board
under the proposed floor. That is what turns "should Club Selected be
10 or 20" from a guess into a decision. It reuses machinery that exists rather
than building a simulator.

## 6. Does a change require recalculation?

Short answer: **yes for it to be visible now, no for it to be correct
eventually, and the machinery already exists.**

### Every consumer reads one cached number

`marketing_clubs.engagement_score` is the single stored value. Nothing keeps its
own snapshot:

- **CRM deal cards** read `club.engagement_score` at serialisation time
  (`services/crm.py` line 502). There is no per-deal copy, so **no separate
  pass over deal cards is needed.** Recalculate the clubs and every card is
  right.
- **Club Directory** filters on it (`club_directory.py` line 876).
- **BetterComms segments** filter on it (`comms_segments.py` line 282).
- **Sales Workspace** call-queue priority derives from it
  (`sales_workspace.py` line 626).
- **Twenty** is the exception. It holds its own pushed copy, refreshed by
  `refresh_engagement` on its own schedule and by the "Refresh Twenty scores"
  button. A parameter change does not reach Twenty until one of those runs. Say
  so on the page, or trigger it alongside.

### It self-heals within an hour with no action at all

`jobs/scheduler.py::crm_global_engagement_sweep` (Tier 3) already runs the full
`recalc()` on a super-admin-tunable interval, defaulting to 60 minutes. So a
weight change that nobody follows up on becomes correct on its own within one
sweep. The Tier 2 incremental sweep will not do it, since it only re-scores
clubs with new telemetry.

### And a manual trigger is already built

`SuperCrm.jsx` line 1475 has a "Recalculate" button, backed by
`POST /recalc-engagement` plus a status endpoint and 4-second polling
(`routers/crm.py` line 896). It runs the same code as
`python -m app.scripts.recalc_engagement`. A full sweep over roughly 6,000 clubs
takes minutes rather than hours, because `batch_web_stats` and
`batch_email_stats` resolve the two expensive scans once for the whole table
instead of per club.

**So the recommendation is: Save runs it.** Saving a parameter change kicks the
existing background recalculation and shows the same progress the Recalculate
button already shows. No new job, no new script, no new endpoint. Offer "save
without recalculating" for someone staging several edits, with the page saying
plainly that the change lands within the hour regardless.

### Five side effects a recalculation has

These are the reasons this needs a decision rather than just a button.

**Cards join and leave the board.** The membership floor is applied by
`sync_pipeline_membership`, which `sync_engagement_promotion` calls on every
club in the sweep, so raising the floor mass-archives auto Target cards and
lowering it mass-creates them, in one run. This is the intended effect rather
than a hazard, and it is bounded (untouched auto Target cards only, never a
manual, locked or advanced deal) and reversible. It is still the largest visible
change a save can make, so the preview has to put a number on it and the save
confirmation has to repeat it. Note that the clubs coming back come back as new
cards, not the archived originals, which is the other reason for the deadband in
2a rather than a single threshold.

**The day-over-day arrow will lie.** `_apply_engagement_cache` rolls a club's
previous score into `engagement_score_prev` on the first write of a new Perth
calendar day, and the pipeline draws an up or down arrow from the difference
(migration 192). A mass recalculation after a weight change is exactly that
first write, so every club on the board gets a large arrow that reflects the
parameter change and not any real movement. Fix it in the recalculation itself:
pass a flag through `_apply_engagement_cache` so a parameter-change sweep either
skips the `_prev` roll or stamps `_prev` to the new score, leaving the arrow
flat. Without this, the morning after a tuning session the board is unreadable.

**Auto-promotion is forward-only.** `maybe_promote_by_engagement_score` moves a
deal along when the score qualifies and never moves it back. Raise the weights
and deals promote on the next sweep. Lower them and nothing demotes, so deals
sit at a stage they no longer qualify for. That is deliberate today, and it
should stay deliberate: a stage is partly a human judgement, and silently
walking deals backwards because someone adjusted a decay curve would be worse.
The precedent for cleaning up afterwards already exists in
`crm.reset_auto_promoted_engaged`, a one-off targeted at score-rule promotions
specifically. State the policy on the page: lowering a weight will not demote
anything, here is what to run if you want it to.

**Opportunities can be mass-created.** At or above
`OPPORTUNITY_AUTO_THRESHOLD` (90), `twenty_leads_tasks._seed_and_refresh_leads`
creates a real Twenty Opportunity. A broad increase in weights can therefore
manufacture Opportunities in the external CRM on the next Twenty refresh. This
is the strongest argument for the preview: show the count of clubs that would
cross 90 before anything is saved.

**Tier and floor changes ripple into audiences.** A BetterComms segment built on
`engagement_score >= 60` changes membership the moment scores move. Nothing
sends on its own, so this is a surprise rather than a hazard, but a saved
audience quietly meaning something different is worth a line on the page.

## 7. Suggested phasing

Three steps, ordered so the risky one is provably a no-op and nothing with a
large blast radius ships without the preview that makes it safe.

**Phase 1, no behaviour change.** Build the catalogue dict, the resolver, the
in-process cache, and the `weights=` argument threaded through `_engagement`,
`batch_web_stats`, `batch_email_stats`, `_recency_pts`, `_tier_for` and
`trial_depth_score`. Replace the hardcoded `score > 0` and `score == 0` in
`sync_pipeline_membership` with `PIPELINE_ADD_MIN` and `PIPELINE_REMOVE_BELOW`,
both defaulting to 1, which is today's behaviour written differently. Read only
code defaults, store nothing. Verify with `recalc_engagement --verify` and by
comparing a full `--dry-run` histogram before and after: it must be identical,
club for club, and the pipeline's deal count must not move. This is the phase
where a missed interpolation site shows up, and it shows up against a known
answer.

**Phase 2, storage, the page and the preview together.** The
`platform_settings` key with its getter, setter and validator, the revisions
table and its migration, the API endpoints, and the page laid out floor-first
per section 5. The preview belongs here rather than later: it is what stops a
floor change being a leap, and most of it is `recalc --dry-run` plus the two
counts. Save persists, then triggers the existing background recalculation with
the `_prev` suppression above.

**Phase 3, the rest of the judgement tools.** Revision history with rollback,
the "would cross 90" Opportunity warning, and an option to push to Twenty in the
same action rather than waiting on its own refresh. Then, separately, add "Club
Selected" as a genuinely new scored signal off the `club_prepared` beacon, which
by then is a catalogue entry and a query rather than a code change in four
places.

## 8. Is the current scoring sound?

Short answer: the bottom end is worse than the top end, and neither is the
biggest problem. There is a defect in the direct-enquiry override that no amount
of re-weighting fixes.

The numbers below come from modelling the formula's own arithmetic offline
(constants copied from `twenty_sync.py`, archetype clubs pushed through it).
They describe the shape of the curve, not the observed distribution. The real
check is `python -m app.scripts.recalc_engagement --dry-run`, which already
prints a histogram in bins of 5 plus percentiles, split between linked clubs and
directory-only prospects. Run that before acting on any of this.

### 8a. The defect: the enquiry override can LOWER a score

`twenty_sync.py` line 833:

    if direct_enquiry_hot:
        score, tier = DIRECT_ENQUIRY_SCORE, "HOT"

That is an assignment, not a floor. Its own comment says the purpose is so a
score "doesn't quietly decay back to the ordinary recency/frequency score
overnight", which is entirely about preventing a fall. Nothing in it justifies
capping a club that has independently earned more.

What it actually does:

| Club | Score without enquiry | With a 2-day-old enquiry |
|---|---|---|
| Busy prospect, 20 visitors, hit /contact and /trial | 100 | **80** |
| Onboarded club deep in setup (trial depth 95) | 95 | **80** |

So a club that browses heavily, reaches the trial page and then fills in the
contact form is scored **lower** than the same club that never got in touch.
The most engaged prospects on the platform are the ones this penalises. Fix is
one line, `score = max(score, DIRECT_ENQUIRY_SCORE)`, with the tier recomputed
from the result rather than forced to HOT.

Worth confirming with whoever wrote it, since "flat" is the word used, but the
stated rationale only ever describes a floor.

### 8b. The bottom end is noise, and it is what fills the pipeline

One page view, from one anonymous visitor, is enough to put a club on the sales
pipeline, and stays enough for about 90 days:

| Signal | Score | On the board? |
|---|---|---|
| 1 page view, today | 14 | yes |
| 1 page view, 29 days ago | 6 | yes |
| 1 page view, 89 days ago | 1 | yes |
| 1 page view, 100 days ago | 0 | no |
| 1 email **open**, 30 days ago | 4 | yes |
| 1 email open, 89 days ago | 1 | yes |

Two things make this worse than it looks.

**An email open is not a human.** Apple Mail Privacy Protection fires the
tracking pixel without the recipient ever looking at the message. The code
already knows this, which is why a click is weighted at more than double an
open. But an auto-fired open still scores 4, which still clears `score > 0`, so
it still creates a deal card. Send one outreach campaign across the directory
and the pipeline fills with cards representing nobody.

**Recency does most of the work down here.** A touch today is worth a flat 10
whether it came from one page view or a hundred, so 10 of the first 14 points
say only "somebody was here recently". That is the single largest distortion at
the bottom of the range.

This is the quantified case for the membership floor in 2a. A floor around 15
would admit a club that has had a real visit and exclude a stale page view and
an auto-fired open.

### 8c. The top end saturates early

The clamp binds sooner than the 100-point scale suggests:

| Weekly traffic | Raw score | Reported |
|---|---|---|
| 5 visitors, 20 views | 46 | 46 |
| 10 visitors, 40 views | 83 | 83 |
| 20 visitors, 80 views | 156 | **100** |
| 50 visitors, 200 views | 375 | **100** |
| 100 visitors, 400 views | 740 | **100** |

Saturation starts around 15 visitors a week. Above that every club is
indistinguishable, and the marginal value of a new visitor is zero. A club
pulling 100 visitors reads the same as one pulling 15.

The intent bonuses compound it. Contact page 10, trial page 20, requested trial
12, in trial 10, ad signup 10, enquiry 20 come to **82 points of a 100-point
scale before a single page view is counted**. One visit today to `/trial` scores
34, which is WARM off a single anonymous page view.

Net effect: roughly scores 31 to 99 do the discriminating, and they cover about
an 11x range of real traffic. Below 31 is mostly noise, above 99 is flat.

### 8d. Three incommensurable things share one axis

This matters more than the curve shape, and re-weighting cannot fix it.

- A **customer** floors at `CUSTOMER_BASE` 60 and scores on account health.
- A **self-registered prospect** floors at its trial depth, minimum 70 for
  registering at all.
- A **prospect** scores on lead heat, and needs roughly 8 real visitors in a
  week to reach 60.

So a paying customer who has done nothing outranks a prospect with 7 visitors,
and a club that signed up and then abandoned setup (70, HOT) outranks a prospect
actively browsing (say 55, WARM). They are all sorted together on the pipeline
and all filterable together in Comms segments, where a "score >= 60" audience
silently mixes customers, dormant registrations and hot leads.

### 8e. The 60-day enquiry cliff

The pin does not decay, it falls off:

| Days since enquiry | Score |
|---|---|
| 59 | 80 HOT |
| 60 | 80 HOT |
| 61 | **1 COLD** |

Overnight, from the top of the board to the bottom, with the club still on the
pipeline (1 clears `score > 0`) but reading Cold. Everywhere else the scoring
was deliberately made smooth, which is why `_recency_pts` is an exponential
rather than day buckets. This is the one place that rule was not applied.

### 8f. What to change, in order

1. **Make the enquiry override a floor** (8a). One line, and it is a defect
   rather than a preference.
2. **Raise the membership floor** to something like 15 (2a and 8b). Biggest
   single improvement to what the pipeline shows, and already planned.
3. **Taper the enquiry pin** instead of cliffing it (8e). Simplest version is to
   let it fall as an exponential from `DIRECT_ENQUIRY_SCORE` once the window
   ends, rather than vanishing.
4. **Reconsider `RECENCY_FULL` = 10**, or make recency scale with frequency
   rather than add to it. It is what makes a single stale page view look like
   engagement.
5. **Shape the top instead of clamping it**, for example a soft saturation on
   the final sum (`100 * (1 - exp(-raw / 60))`) so ordering is preserved above
   15 visitors. Note the history here: the constants block records that the
   earlier per-component saturating caps were removed precisely because they
   compressed genuinely different clubs into a lump. A single monotonic
   transform on the final sum is a different thing from per-component caps. It
   never ties two clubs that differ, and it removes the hard ceiling rather than
   adding more of them. Worth trying against the real histogram before
   committing.
6. **Decide whether customers belong on this axis at all** (8d). Options are a
   separate account-health field, or keeping the number and stopping the
   cross-lifecycle comparison in segments and sorting. Not a weights question.

Items 1 to 3 are small and worth doing regardless of whether the parameters page
gets built. Items 4 to 6 are exactly the kind of change the page plus its
preview exists to make safely, so they should wait for it.

## 9. Email link scanners, and event volume generally

Reported: an outreach email containing several links to our site produces a
cluster of page views that all land at once, one per linked page, from the
recipient's mail infrastructure rather than a person. Microsoft Defender for
Office 365 Safe Links, Proofpoint URL Defense, Mimecast and Barracuda all
prefetch links this way. Technically page views; not humans.

It is filterable, and the burst signature is reliable for the multi-link case.
But reading the code around it turned up a larger distortion in the same place,
so take these in order.

### 9a. Confirm it is happening before filtering anything

The page-view beacon is client-side JavaScript (`usePageView.js` POSTs to
`/usage/event`). A scanner that only issues an HTTP GET never runs it and never
appears in `usage_events` at all. Only a scanner that renders the page in a
headless browser, which Safe Links detonation does in some configurations,
shows up. So the volume may be smaller than it looks, or larger, and it is
cheap to find out. This needs no code:

    SELECT ip_hash,
           to_timestamp(floor(extract(epoch FROM created_at) / 10) * 10) AS bucket,
           COUNT(*)                                        AS events,
           COUNT(DISTINCT split_part(path, '?', 1))        AS distinct_paths,
           COUNT(DISTINCT visitor_id)                      AS visitor_ids,
           MAX(created_at) - MIN(created_at)               AS span,
           MIN(user_agent)                                 AS ua
    FROM usage_events
    WHERE event_type = 'page_view'
      AND user_id IS NULL
      AND ip_hash IS NOT NULL
      AND created_at > NOW() - INTERVAL '90 days'
    GROUP BY 1, 2
    HAVING COUNT(DISTINCT split_part(path, '?', 1)) >= 3
    ORDER BY distinct_paths DESC, bucket DESC
    LIMIT 50;

It rides the `(ip_hash, created_at DESC)` index added in migration 214. Read the
`ua` column in the results: if the scanners are announcing themselves, the whole
problem may be one user-agent test.

### 9b. Why the burst signature is reliable, and where it is not

The distinguishing feature is not "many requests from one IP". It is **many
DIFFERENT paths from one IP in a few seconds**, and that is what makes it safe:

- A **link scanner** fetches every link in the email, so it produces N
  **distinct** paths from one IP, effectively simultaneously.
- **Several real people at one club** reading the same email behind one office
  IP produce N hits on the **same** path, spread over minutes or hours.

Those two are cleanly separable. Keying on distinct paths inside a tight window
gets the scanner and leaves the office NAT case alone, which is the false
positive that would actually matter.

Two corroborating signals, both already in the table:

- **A fresh `visitor_id` per row from one `ip_hash`.** Each prefetch is a new
  browser context. The engagement query's own comment already records observing
  this ("18 'visitors' from 2 IPs"), which is why reach is deduped by
  `COALESCE(ip_hash, visitor_id)` rather than raw `visitor_id`.
- **No `page_exit` row.** A scanner never comes back to fire the dwell beacon
  (`event_type = 'page_exit'`, matched to its page view by visitor and path).
  Good as a corroborator, not as a sole test, since a real browser can drop it.

**The honest limit**: this only catches multi-link scans. An email with one link
produces one page view from the scanner, indistinguishable from a fast human on
the data available. That case is lower harm (one view rather than ten) but it is
not solved, and it should not be claimed to be.

User-agent matching is worth adding as a second, independent rule, but not
relied on alone: Safe Links often presents as an ordinary browser.
`routers/usage.py::_parse_device` already has a bot word list, but it is
**display only** on the Usage page. Nothing in `_engagement` filters on it.

### 9c. The bigger distortion: every event type counts

While checking where to apply the filter: `_engagement`'s web query has **no
`event_type` filter at all**. It is a bare `COUNT(*)` and a decay sum over
whatever rows match the club. Four event types are written to that table:

| event_type | Written by | Counts toward depth today |
|---|---|---|
| `page_view` | the SPA beacon | yes |
| `page_exit` | the dwell beacon, one per page view | yes |
| `heartbeat` | **every ~25 seconds while a public page is open** | yes |
| `api` | server-side, per interesting API call | yes |

The heartbeat is the problem. At one every 25 seconds, a single visitor who
leaves a tab open scores:

| Tab left open | Heartbeats | Depth points | Score contribution |
|---|---|---|---|
| 5 minutes | ~12 | 14 | 14 |
| 10 minutes | ~24 | 29 | 29 |
| 60 minutes | ~144 | 173 | **clamped at 100** |

So one person with a forgotten tab outscores ten different clubs' worth of
genuine reading, and an hour of idle tab alone maxes the score. Every page view
also double-counts through its own `page_exit` row, and a JS-heavy page adds
`api` rows on top.

This is worth fixing before, or at least alongside, the scanner work. It is a
one-line `AND ue.event_type = 'page_view'` in the decay sum (in all four
interpolation sites, per section 4), and it is a larger and more certain
distortion than the prefetch traffic. It also shrinks the scanner problem on its
own: a prefetch that currently contributes a page view plus several api rows
would contribute one row.

### 9d. The structural fix that beats any heuristic

Depth is currently linear in **raw event count**, which is what makes it
vulnerable to any repeated-request source, scanners and heartbeats alike. Bound
it per visitor instead:

    depth for a visitor-day = min(their decayed points, a per-visitor cap)

Then a scanner hitting ten links from one IP contributes roughly what one visit
contributes, whether or not it was ever detected as a scanner, and the same
holds for the next source of repeated requests nobody has thought of yet. Reach
(distinct visitors) already works this way, which is exactly why reach was not
the half that broke.

Note the history in section 8f item 5: earlier per-component saturating caps
were removed because they compressed genuinely different clubs together. A
per-visitor cap is a different thing from a per-club cap. It bounds one
visitor's contribution while leaving the club's total linear in how many
visitors it had, which is the quantity actually worth measuring.

### 9e. Where to apply the filter

Mark, do not delete. These are real requests and the Usage page may legitimately
want to show them. Following the same discipline as the cross-club view fix
(migration 060) and every other correction in this codebase: filter on read,
never destroy the row.

Sequence, matching the `resolved_marketing_club_id` precedent:

1. **Query time first.** A gap-and-islands CTE over `usage_events` partitioned
   by `ip_hash` (a new island whenever the gap exceeds ~5 seconds), keeping
   islands with 3 or more distinct paths and a span under ~10 seconds. Works
   retrospectively on existing data with no migration and no backfill, which
   makes it cheap to evaluate and cheap to revert.
2. **Then pre-stamp a column** once the rule has proven itself, exactly as
   `usage_events.resolved_marketing_club_id` did with
   `app/scripts/backfill_resolved_club.py`, so the `fast_web` per-club path stays
   an indexed equality rather than a window function.
3. **Apply it in one place, not four.** The same rows feed the Usage analytics,
   the Club Directory visit panel and the Meta Ads funnel. If prefetch traffic is
   distorting the engagement score it is distorting those too, and a filter that
   lives only inside `_engagement` guarantees the three surfaces disagree.

The burst thresholds (distinct paths, window seconds) belong in the parameter
catalogue from section 3, so the rule can be tightened without a deploy once
there is real data to tune against.

### 9f. Order

1. **Filter the decay sum to `page_view`** (9c). Largest, most certain gain,
   smallest change.
2. **Confirm the prefetch volume** with the query in 9a before building anything
   for it.
3. **Cap depth per visitor** (9d), which makes the remaining prefetch mostly
   harmless whether or not it is ever identified.
4. **Add burst marking** (9b, 9e) if 9a shows it is material after 1 and 3.
