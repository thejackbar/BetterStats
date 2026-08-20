# Parameterising the Engagement Score

A design note for making every number in the engagement-score calculation
editable by a Super Admin, from a page linked off the CRM hub, instead of
living as constants in `backend/app/services/twenty_sync.py`.

Nothing here is built yet. This is the shape of the work, the traps found while
reading the current code, and a straight answer to the recalculation question.

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
