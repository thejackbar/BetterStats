# Archive: marketing-funnel-ads-and-webinar

Verbatim history moved out of `CLAUDE.md` on 2026-09-30. NOT loaded into context automatically.
Scope: Meta ads reporting, trial and demo landing pages, webinar registration and StreamYard, usage tracking, wizard clubs.
Read the distilled rules first: `docs/dev-notes/guides/marketing-funnel-ads-and-webinar.md`. Open this file only when you need the full reasoning, measurements or history behind a rule, and search it (grep) rather than reading it whole.
Sections are in their original relative order. The `BEGIN`/`END` comments carry the line range in the untouched copy `CLAUDE.original-2026-09-30.md`.

<!-- BEGIN original CLAUDE.md L399-453 -->
## The club page a prospect searched their way to asks them to start (v9.91.0, Sep 2026)

Reported as the paid funnel's biggest leak: ad -> /trial -> search -> a club's
dashboard -> nothing to press but ADMIN.

- **THE CLUB ON THAT DASHBOARD IS ALREADY ON BETTERCRICKET, and that decided
  the copy.** `/trial` only navigates to a club's page when the search result
  is `already_registered`, and `/public/self-serve/prepare` and `/submit` both
  409 that club. So the bar can never offer to set up the club on screen: it
  names it ("This is X's real history on BetterCricket") and sells the
  visitor's OWN club, and the wizard opens on a blank search. The animated
  placeholder on `/trial` suggests typing "Applecross", which is one way a
  prospect ends up on somebody else's club.
- **PROSPECTS ONLY, NEVER A CLUB'S OWN MEMBERS AND NEVER ANYONE SIGNED IN.**
  A prospect is a session that arrived from a Meta click (utm_source
  meta/facebook/fb/instagram/ig, utm_medium paid_social, or an fbclid/igshid)
  or that passed through `/trial`. A paying club's public site must not pitch
  its own members. Dismissing it minimises to a Start free pill rather than
  hiding it.
- **THE CAMPAIGN PARAMS ARE READ OFF THE SESSION, NOT THE ADDRESS BAR.**
  `visitor.rememberLandingParams()` runs in `main.jsx` before first render and
  keeps the landing URL's utm_* and click ids in sessionStorage
  (`bc:landingParams`). The old `isPaidVisitor` read `window.location.search`,
  which is empty once the search has navigated client-side.
  `metaPixel.buildFbcFromFbclid` falls back to that fbclid, stamped with the
  click's own time, when the pixel has not set `_fbc`. The submit payload's
  `attribution` was already first-touch from localStorage.
- **THE BAR NO LONGER DRAWS ON /trial OR /demo**, which it had been doing for
  paid traffic: `isPaidVisitor()` ran for any non-marketing path. Both pages
  carry their own call to action.
- **`lib/clubPath.publicClubSlug` is the one "is this a club page" rule**,
  shared with FaviconManager, and gained the sections it had missed
  (fixtures, lineups, premierships, honour-board).
- **CompleteRegistration is unchanged and still fires only on
  `status === 'completed'`**, `content_category: 'self_serve_trial'`, one
  event id shared with the server's CAPI copy.
- **Driven in Chromium** (`frontend/verification/verify_club_cta_browser.mjs`,
  34 checks: the whole funnel with a real client-side hop, the bar naming the
  club and inside the viewport at 1440 and 390, no pixel event on the click,
  CompleteRegistration once on success and not on a failed submit, the UTMs,
  fbclid and fbc on the submit payload after the hops, a direct visitor and a
  signed-in one seeing nothing, the pill persisting) **with a control run**: 11
  fail against the previous commit and it reports rather than crashing.
- **THE WORDING FOLLOWS THE AD (v9.92.1).** The bar's button, the pill and
  the /trial new-club modal read "Check out your club" and "Free · about 3
  minutes · no card", the ad's own words; the 14-day trial framing is off the
  bar because the ad never makes it. The /trial placeholder names NO real
  club: "e.g. Applecross Cricket Club" sent prospects to type a registered
  club and land on somebody else's page. Keep the bar in step with the ad when
  the creative changes. Suite is 41 checks; the control fails the 8 new ones.
- **NOT VERIFIED IN META EVENTS MANAGER.** Test Events needs a real
  registration on the live site, which creates a real club. The browser suite
  records what `fbq` is called with; Events Manager is the one place left to
  look.

<!-- END original CLAUDE.md L399-453 -->
<!-- BEGIN original CLAUDE.md L789-994 -->
## ONE CAMPAIGN, TWO PRODUCTS, ONE PIXEL EVENT (v9.72.0, Sep 2026)

The Meta ad account was restructured 8-9 Sep 2026 and `BC_AU_Trials_CBO_Aug2026`
now runs a webinar ad beside the trial ads. Asked for as "update the page for
the two new ads"; the brief's own framing is the important half: *"registrations
is no longer a single number, and any reporting that treats it as one is now
silently wrong."*

- **BOTH LANDING PAGES FIRE THE SAME PIXEL EVENT ON THE SAME DATASET, AND ONLY
  A PARAMETER SEPARATES THEM.** `/trial` and `/demo` each send
  `CompleteRegistration` to 1317878090534903, told apart by `content_category`
  alone — `self_serve_trial` (value 399 AUD) and `webinar` (no value). A trial
  signup is a prospective paying club; a webinar registration is somebody who
  watched a form. Every cost-per-result figure that adds them describes neither.
- **THE PAGE WAS NEVER DOUBLE-COUNTING, AND ESTABLISHING THAT FIRST IS WHAT
  STOPPED THIS BEING FIXED THE WRONG WAY.** `get_registration_count` reads
  `organisations`, so it has only ever counted trial signups. The bug was the
  DIVISOR: `cost_per_lead` was whole-campaign spend over trial signups, so the
  trial was charged with the webinar's spend from the moment both ran together.
  On the brief's own lifetime figures that is **A$46.84 against a true
  A$43.90** — and it widens with every dollar the webinar spends.
- **SO SPEND IS SPLIT PER STREAM FROM THE PER-AD ROWS.** Ad level is the finest
  split Meta gives us and the two streams are cleanly separable there, so this
  is exact rather than apportioned. `stream_totals` / `build_streams` are the
  one definition; `campaign.cost_per_lead` is kept under its old name and now
  means the trial's own.
- **`stream_for_ad` FALLS BACK TO THE AD'S NAME, and that is the half that
  keeps working.** `AD_DESTINATIONS` is exact where we can be, never the gate —
  a creative added in Ads Manager tomorrow is classified by its name
  (`Ad_Webinar_*`) with no code change. **Never from the AD SET name**:
  `AS_Cold_Broad_AU_LPV` is now wrong about both "broad" and "LPV".
- **`CAMPAIGN_UTM_NAMES` HAD TO BECOME A SET PER CAMPAIGN, AND A SINGLE VALUE
  WOULD HAVE FAILED CLOSED.** One campaign now carries two destination
  taxonomies (`webinar_21sep2026`, `trial_evergreen_sep2026`), neither of them
  the Ads Manager name the old convention assumed. Unrecognised tags are
  DROPPED, so every registration through the new ads would have read as
  belonging to no campaign — which shows up as "the new ads produced nothing"
  rather than as a bug.
- **A LAZY IMPORT OF THE RENAMED CONSTANT SURVIVED `py_compile` AND
  `vite build`.** `sales_workspace._ad_click_history` does
  `from app.services.meta_ads import ... CAMPAIGN_UTM_NAMES` INSIDE a function
  body — the exact trap the Twenty-retirement note above records. Found by a
  sweep that walks every `ImportFrom` and `meta_ads.<attr>` in `app/` and asks
  whether the name still exists; worth re-running on any rename here. Worse
  than an ImportError, it would then have read `.values()` of a set-valued map
  and marked genuine ad traffic "unrecognised campaign".
- **THE PHANTOM VALUE WAS BEING CREATED AT SOURCE, NOT JUST IN THE REPORT.**
  `meta_capi.send_complete_registration_event` hardcoded the trial's
  `content_category` and `value=399`, and `public_webinar.py` took those
  defaults — so every webinar registration reached Meta server-side labelled a
  trial signup carrying A$399, and the deduped conversion's two halves
  contradicted each other. The caller names its own event now; the defaults
  stay the trial's only because it was the first caller.
- **THE SINGLE CAMPAIGN-WIDE FUNNEL WAS REMOVED, NOT RELABELLED.** It put
  campaign-wide impressions above a bottom row counting trial signups only, so
  the drop at the end read as a conversion collapse when it was two products in
  one column. `compute_stream_funnel` builds one per stream; the webinar's has
  no "Club selected" step because there is no wizard on `/demo`.
- **THE UNTAGGED WEBINAR REGISTRATIONS ARE REPORTED, NEVER ABSORBED.** The ad's
  primary text carries a plain link with no UTMs (it had to match a line on the
  artwork), so some genuinely ad-driven registrations are indistinguishable
  from organic. Cost per result is computed on the attributed count alone —
  which reads HIGH, the safe direction — with the shortfall named beside it.
- **SPEND IS NOT SUBJECT TO THE 7-DAY ATTRIBUTION WINDOW, and the first cut had
  that wrong.** Meta credits a CONVERSION to the click date and back-fills for
  seven days; money spent on a day is settled that day. Gating budget pacing on
  the attribution window made it unanswerable for a week after every change —
  the two conditions are contradictory the day a change lands. Pacing excludes
  only today (a part-day); the provisional guard applies to the conversion
  insights it genuinely bites on.
- **PACING IS MEASURED FROM THE LAST DELIBERATE CHANGE, NEVER ACROSS IT.**
  `CAMPAIGN_ANNOTATIONS` is a per-campaign list of `{date, label, detail}` —
  add a row rather than reasoning about a discontinuity somewhere else. One day
  after a change there are not two settled days to pace off and the insight
  correctly says nothing; that is not a bug, and a test expecting otherwise was
  the wrong expectation.
- **A REFERENCE LINE WRAPPED IN A FRAGMENT IS SILENTLY DROPPED BY RECHARTS.**
  It finds `ReferenceLine`/`ReferenceArea` by walking `React.Children` and
  reading each child's `type`; React.Children flattens an ARRAY but treats a
  Fragment as one opaque child. The chart renders perfectly, with no error, and
  simply has no marker on it. `chartMarkers()` returns an array. **Found by the
  browser suite reporting zero markers against code that reads as though it
  draws them.**
- **AND RECHARTS DRAWS A `ReferenceArea` AS A `<path>`, NOT A `<rect>`** — the
  first cut of that check selected `svg rect` and reported zero against code
  that was drawing the band correctly. It measures the real element AND its
  width now: a band collapsed to nothing would pass a bare presence check.
- **Verified against a real Postgres**
  (`backend/verification/verify_meta_ads_streams.py`, 43 checks through the
  shipped service: an unmapped ad classified by name, both new taxonomies
  recognised and an EDM's still refused, each stream's cost per result from its
  own spend, the pre-split figure shown to be higher, only the trial carrying
  value, the untagged registrations counted apart, a creative keeping its two
  result counts separate, nothing dividing by zero on an ad that never spent,
  pacing reading the post-change rate rather than the pre-change one or a
  blend, and a zero-result stream NOT reported as failing while it settles)
  **with a control run** that names all ten missing parts rather than dying on
  the first ImportError.
- **Driven in Chromium** (`verify_meta_ads_streams_browser.mjs`, 41: two stream
  cards with two different costs per result, no combined total anywhere, the
  webinar card saying it carries no value, two funnels, the change marker on
  every chart, the shaded band measured as covering the trailing half of the
  window, the creative table, and an ad that has not gone live yet breaking
  nothing) **with a control run**: 32 of the 41 fail against the previous
  commit, and the nine that pass in both are don't-regress guards (no NaN, no
  page errors, no overflow) rather than checks that should have caught it.
- **FIVE CHECKS COULD NOT HAVE FAILED AS FIRST WRITTEN, and the control run is
  what found them.** Three compared against labels the page renders CSS-
  `uppercase`, which `innerText` returns transformed — the trap this file
  already records, hit three times in one suite. One matched an insight's prose
  rather than the funnel it claimed to read. Two used `.every()` on an array
  that is empty in the control, which is vacuously true.
- **VERIFIED AGAINST THE LIVE AD ACCOUNT for structure, not for figures.** The
  Meta MCP tools confirm the account id, all six ads and their names; they
  return entity ids and names only, no spend or conversion metrics, so the
  numeric totals were NOT independently tied to Ads Manager here. The app's own
  backend holds the token and queries the Graph API directly.
### The trial's cost was still a lifetime average, so the two were never comparable (v9.72.1)

Asked for straight after: "can we split the spend and the costs off from the
old ones and get new numbers for webinar and trial ones?"

- **SPLITTING THE SPEND PER STREAM WAS ONLY HALF OF IT, and the half that was
  left is why the two figures still could not be read against each other.**
  `stream_totals` sums the `level='ad'` snapshot rows, which are LIFETIME
  (`fetch_per_ad` sends `date_preset: maximum`). So the trial's cost per signup
  is an average over the campaign that ran BEFORE the 8 Sep restructure —
  A$50/day, broad targeting, all placements, Instagram on — while the webinar
  has no pre-change history at all. **Comparing them compares two different
  campaigns**, and the brief's own question ("what are we spending per trial
  signup NOW") was unanswerable from the page.
- **SO EACH STREAM CARRIES A SECOND FIGURE, MEASURED FROM THE LAST DELIBERATE
  CHANGE.** `stream_totals_since` sums the TRUE daily per-ad rows
  (`level='ad_daily'`) on or after `_last_change_date()`, and the results behind
  it are windowed too — both streams over the same stretch of calendar or the
  pair means nothing. Lifetime is kept: it is the real money spent.
- **THE COUNTING-SINCE CUTOFF IS NOT THIS, and reaching for it would have been
  the wrong fix.** That is a super-admin setting which resets EVERY figure on
  the page, and it deliberately never windows `get_registration_count` — a
  genuine registration always counts, however long ago. This is per stream, per
  card, automatic, and derived from the annotation that already exists.
- **THE ALL-TIME FIGURES NOW SAY THEY ARE ALL TIME.** Left unlabelled beside a
  since-the-change one, the bigger number reads as the current cost — which is
  the same misreading in a new place.
- **A PARTIAL WINDOW WITHHOLDS THE NUMBER, and the direction of the error is
  why.** `ad_daily` is retained for `CAMPAIGN_LENGTH_DAYS + 5`, so a change
  older than that leaves the sum short of what was really spent — which
  UNDERSTATES cost per result, the direction that flatters the campaign and
  gets quoted back at us. `covers_from` reports it and the block withholds the
  division, naming the reason so silence does not read as a bug.
- **SPEND IS SETTLED, RESULTS ARE NOT, and this block is where that bites
  hardest.** Inside the 7-day click window the results behind a since figure
  are still arriving, so the cost is a CEILING that comes down. Marked
  provisional; nothing alerts off it — the rule the pacing insight already
  keeps, applied to a figure that is mostly window at the moment (the change
  was yesterday).
- **A SIGNUP WITH NO TIMESTAMP IS REPORTED, NEVER GUESSED EITHER WAY.** Orgs
  carry no `created_at`; the date is the earliest `self_serve_idempotency_keys`
  row (the source `ad_signups` already uses). An attributed org with no key row
  cannot be placed either side of the change, so it counts lifetime and in
  neither since figure — surfaced as `undated_trial_results` so a short since
  count reads as a known gap rather than as the ads having stopped working.
- **THE MANUAL LEADS ADJUSTMENT IS NOT APPLIED TO THE SINCE COUNT.** It is a
  lifetime correction and may well relate to a signup from before the change;
  folding it into a windowed figure would move a number nobody can trace.
- **`get_registration_count` IS UNTOUCHED.** `get_registration_count_since` is
  its own function sharing `_attribution_matches_campaign`, so the windowed and
  lifetime figures can never disagree about what COUNTS — only about when it
  happened — and the existing function's documented "never windowed" promise
  still holds exactly.
- **Verified against a real Postgres** (`verify_meta_ads_streams.py` is 67
  checks now: the trial's since-spend being its post-change spend alone and a
  fraction of its lifetime, the webinar's since-spend EQUALLING its lifetime
  because it has no history before the change, a signup from before the change
  excluded, an undated one reported rather than counted or dropped, a webinar
  registration predating the ad falling outside the window, the since cost per
  result differing from the lifetime one, and every guard — partial, no
  results, no spend, settled-vs-provisional, no change at all) **with two
  control runs**: with the feature absent it REPORTS all four missing parts by
  name and the other 43 still pass; with the window and the guards neutered, 8
  fail — the trial's since-spend reading its lifetime 1800.0, and a partial
  window printing A$25.00 instead of withholding.
- **Driven in Chromium** (`verify_meta_ads_streams_browser.mjs` is 57: both
  blocks on screen, the since figure read from its own element and differing
  from the lifetime one beside it, the all-time label, the provisional note on
  one stream and NOT the settled one, a withheld figure printing no digits
  while still reporting its spend, the undated note, and no overflow at 390px)
  **with a control run**: 13 fail against the previous commit, reporting the
  unlabelled `A$43.90 each` that reads as current.
- **FOUR CHECKS PASSED IN THE CONTROL FOR THE WRONG REASON and were
  tightened.** "The since figure is not the lifetime figure", "a settled stream
  is not marked provisional" and "a withheld figure prints no number" are all
  trivially true of a block that never rendered — absence masquerading as
  correct behaviour. Each is now gated on the block existing first.
- **A FIXTURE THAT GROWS MOVES ITS NEIGHBOURS' EXPECTATIONS.** Adding the
  undated org took the lifetime trial count 3 → 4 and failed two pre-existing
  checks. The intent of both was intact — only the fixture's size changed — so
  the count was updated and the cost check re-expressed against
  `trial_results` rather than a hardcoded 3, so the two can no longer drift.

- **NOTICED, NOT BUILT**: nothing reads Meta's own `content_category` breakdown
  off the insights API, so Meta's self-reported conversion counts are still
  un-splittable and are shown only as the labelled "Meta-reported" comparison.
  The campaign plan (`CAMPAIGN_PLANS`) is still one budget per campaign rather
  than per stream, so pacing is campaign-wide.

<!-- END original CLAUDE.md L789-994 -->
<!-- BEGIN original CLAUDE.md L1827-2582 -->
## THE CONVERSION CANNOT FIRE ON STREAMYARD'S DOMAIN (migration 296, v9.71.1, Sep 2026)

Asked for with a paused Meta campaign waiting on it: a page on `betterat.cricket`
that fires `CompleteRegistration` on a successful webinar registration and only
then hands the visitor the StreamYard link. Webinar Mon 21 Sep 2026.

- **THAT ONE CONSTRAINT DECIDED THE WHOLE SHAPE, and it is worth stating because
  every other choice follows from it.** A pixel cannot fire on a third-party
  domain, so an ad pointing straight at StreamYard hands Meta zero conversion
  signal and delivery degrades within days. So the registration happens on our
  own page, and **the success state is rendered rather than redirected** — a
  redirect races the beacon it is supposed to follow, and skips the calendar
  file and the inbox note besides.
- **THE ORDER IS PERSIST, THEN FIRE, AND NOTHING ELSE.** Never on page load,
  never on the click, never on a validation failure. The browser suite asserts
  each of those by recording what `fbq` was actually called with, in order —
  none of it is observable from the backend, which is why it is checked there.
- **A RESUBMISSION IS THE SAME LEAD, SO IT CLAIMS NO SECOND CONVERSION.**
  `webinar.register` folds on `(event_key, lower(email))` and reports `created`;
  the page fires the pixel only when it is true. Counting a resubmission would
  teach the ad set to optimise toward people who fill the form in twice. The
  cost is stated rather than hidden: somebody arriving on a fresh ad click and
  re-registering is a click Meta attributed with no conversion behind it, and
  under-reporting one duplicate is the safer direction than inventing one.
- **A BROKEN BACKEND STILL HANDS OVER THE LINK, AND STILL CLAIMS NOTHING.** The
  registrant is not trapped behind a failed write — but no pixel fires, because
  nothing was registered and a conversion we invented is worse for the ad set
  than one we missed.
- **CAMPAIGN CREDIT IS FILLED, NEVER OVERWRITTEN.** The upsert COALESCEs every
  UTM column, so a registration already credited to a campaign keeps that credit
  and one that arrived with no signal can be upgraded by a later tagged visit.
  Overwriting would credit the registration to whichever visit happened to be
  last rather than the click that earned it.
- **`utm_term` WAS NEVER CAPTURED BY THE SITE AT ALL, and the browser suite is
  what found it.** `lib/visitor.js::parseAcquisition` returned four UTM tags and
  not the fifth, so any campaign tagging it had it silently dropped — on every
  form, not just this one. Fixed at the source, and `public_self_serve`'s own
  `_ATTRIBUTION_KEYS` allowlist had to learn it too or the newly-captured field
  would have been dropped one level down.
- **ONE DATE CONSTANT, TWO PAGES, AND THE PAGE TURNS ITSELF OVER.**
  `services/webinar.EVENT` and its hand-kept mirror `frontend/src/data/webinar.js`
  drive the headline, the button label, the promo block and what the success
  state hands over. **The switch is the event's END, not its start** — somebody
  arriving halfway through should still be sent to the live stream. The mirror
  exists so the H1 paints without a request (this traffic is paid and mobile, and
  a fetch in front of the H1 is a fetch in front of LCP); the suite asserts the
  two copies agree rather than trusting them, the arrangement `billing_pricing.py`
  and `pricing.js` already have.
- **THE SERVER DECIDES WHETHER THE EVENT HAS PASSED; THE LOCAL CLOCK ONLY
  COVERS THE FIRST PAINT.** Found by the browser suite: the first cut derived
  `past` from the mirrored date alone and ignored the server's own `is_past`, so
  a visitor whose device clock is days out would be shown the wrong state
  entirely — offered a recording that does not exist yet, or sent to a stream
  that has already finished. `webinarState({ isPast })` takes the server's
  answer whenever it has one and falls back to the clock until the request
  lands. Seven checks failed on exactly this.
- **THE RECORDING LINK IS A SETTING, NOT A CONSTANT.** It does not exist until
  after the event, and the hour afterwards is when interest peaks — waiting on a
  deploy would spend it. `platform_settings.webinar_recording_url` (a new
  `_STR_KEYS` group, url-validated, `''` CLEARS rather than storing an empty
  string that would read as a link which exists and is blank).
- **THE `.ics` IS AN ENDPOINT, NOT A BROWSER-BUILT BLOB**, because the same URL
  is what the confirmation email links to. `email_service.EmailMessage` carries
  no attachment field and the five providers behind it each take attachments
  differently (SES would need raw MIME rather than the simple content path it
  uses), so a link is both what the brief allowed and the only thing that works
  in every mail client. Written as a UTC `DTSTART` with **CRLF line endings** —
  RFC 5545 requires them, and a file joined with bare LF is accepted by some
  calendar apps and silently rejected by others.
- **DELIBERATELY NOT `club_onboarding_requests`.** That table is the queue of
  clubs asking to be onboarded; somebody who signed up to watch a demo has not
  asked for that, and folding a hundred registrants in would bury the clubs who
  did. Per direct instruction it also does NOT push a Hot lead into Twenty or
  the CRM the way a Contact-form enquiry does — a demo registration is a weaker
  signal than "onboard my club".
- **`/trial` KEEPS ITS OWN `content_category`.** The brief asked for `'trial'`;
  it already fires `'self_serve_trial'`, and renaming it would split the event's
  history so a custom conversion filtered on either value misses half of it.
  Left as it is, per direct decision — the two are already distinguishable.
- **THE PROMO BLOCK SITS BELOW `/trial`'s SEARCH BOX**, measured off the real
  boxes rather than source order: that page converts paid traffic at ~3.4% and
  anything above the fold competing with its search costs it that. It fires no
  pixel event of its own — clicking through and registering is what fires one.
- **A NEW TOP-LEVEL ROUTE IS A CLUB SLUG UNTIL FOUR LISTS SAY OTHERWISE**, the
  trap this file already records for `/videos`. Added `demo` — **and `trial`,
  which had never been added**, so `/trial` was resolving "trial" as a club slug
  on every visit: a wasted `/api/clubs/trial` 404 and the club `Navbar` drawn on
  top of its own `MarketingNav`, on the exact page paid traffic lands on.
  **CORRECTED in v9.71.3 below: only THREE of the four were updated.** The
  fourth, `lib/marketingPaths.MARKETING_PATHS`, is the one that suppresses the
  club Navbar, so the overlap this note claims to have fixed was still live on
  both pages until then — and could be measured on the deployed site.
- **Verified against a real Postgres** (`backend/verification/verify_webinar.py`,
  143 checks through the shipped route bodies and service: the DDL applied three
  times and again over a populated table, both copies of the date agreeing, 17:30
  Perth and 19:30 AEST proved the same instant, the switch at the event's end,
  the calendar file's CRLF and UTC stamps, every UTM tag and the fbclid stored,
  an un-allowlisted key never reaching the blob, the conversion queued once with
  the browser's own event_id, a resubmission storing no duplicate and claiming
  nothing while keeping its campaign credit, an untagged registration upgraded
  later, all five refusals, the honeypot and fill-time guards including a device
  with a fast clock NOT refused, the post-event states with and without a
  recording, the setting cleared and refused, the email's outcome recorded on the
  row through a refusal and a throw, and the downgrade) **with three control
  runs**: the resubmission guard neutered fails 2, the bot guards neutered fail 4,
  and with the service absent it REPORTS the feature rather than dying on the
  first ImportError.
- **Driven in Chromium** (`frontend/verification/verify_webinar_browser.mjs`, 87:
  no conversion on page load or on either validation failure, the exact payload
  on the wire, the conversion fired once with `content_category: 'webinar'`
  sharing the server's event_id, the button refusing a second press while in
  flight, the resubmission and server-error paths both claiming nothing, both
  date-driven states, the promo measured as below the search box, and no
  overflow at 390px) **with a control run**: firing the conversion regardless of
  `created` fails the resubmission checks.
- **`waitUntil: 'networkidle'` NEVER SETTLES ON THIS APP**, and it hangs the
  suite rather than failing it: `HeartbeatBeacon` pings every ~25s for as long
  as the tab is open, so the network is never idle. Wait for the element the
  checks are about. Killing a hung run also leaves its Chromium behind, and
  those pile up until the next launch hangs too.
- **A CHECK THAT MEASURES THE HARNESS IS NOT A CHECK, twice here.**
  `addInitScript` cannot stub `gtag` — `index.html` unconditionally redefines it
  (`function gtag(){dataLayer.push(arguments)}`) after the init script runs, so
  the recorder is replaced and every GA4 check reads empty; the calls are read
  back out of `window.dataLayer` instead. `fbq` IS stubbable there, because its
  own loader bails out when `window.fbq` already exists. And a `click({force:
  true})` on a disabled button hung the suite rather than failing it — the
  in-flight guard is asserted by holding the response and reading `isDisabled()`,
  then dispatching the event directly.
- **STILL ACCOUNT-SIDE, NOT SOMETHING CODE CAN DO**: `betterat.cricket` verified
  in Business Manager, `CompleteRegistration` in the Aggregated Event Measurement
  priority list (or iOS conversions are not attributed), and the ad's
  `conversion_domain`. Also worth fixing on the creative itself: it reads "WAST",
  which is West Africa Summer Time — Perth is **AWST**.
- **THE FORM PRE-FILLS NOTHING ON STREAMYARD, AND THAT WAS ASKED AND ANSWERED
  RATHER THAN ASSUMED (migration 297, v9.71.2).** `EVENT.watch_url` is handed
  over as a plain link and no registration data crosses to it — there is no
  StreamYard API call anywhere in this codebase. Read off the watch page's own
  server-rendered props: the broadcast is configured as a **webinar**
  (`webinarId`) and the page carries a `sessionRegistrationId`, which is
  StreamYard's OWN registration mechanism and is empty for an anonymous
  visitor. Whether that gate is switched on for this broadcast is a setting in
  StreamYard, not something this code can see or change. **If it is on, a
  registrant fills a form twice** — the fix is a StreamYard setting, not a
  code change.
- **A PHONE NUMBER IS GATHERED, AND IT IS OPTIONAL.** It shipped REQUIRED and
  that was reversed the same week — see v9.71.3 below. The original reasoning
  ("make sure we gather" is not satisfied by a field most people skip) is a
  real argument and it loses to two better ones: on cold paid traffic a
  mandatory phone number is the highest-friction field on the form, and it
  reads as a promise to ring, which contradicts the "no sales call" line
  `/trial` makes one click away.
- **STORED EXACTLY AS TYPED, and validated on "could this be a phone number"
  and nothing more.** `PHONE_MIN_DIGITS, PHONE_MAX_DIGITS = 8, 15` — an
  Australian landline with no area code is 8 digits and E.164's own ceiling is
  15. **DELIBERATELY NOT `admin_identity.mobile_valid`**, which is right for a
  club admin's account and wrong here: it refuses anything that is not an
  Australian mobile, and the clubroom landline a secretary writes down is a
  perfectly good number to ring them on. Normalising the stored value would
  only make it harder to read back to whoever rings it; the digits-only form
  is derived once, at the Meta boundary, by `meta_capi._hash_phone`.
- **IT RIDES ON THE CONVERSION BECAUSE IT IS A SECOND HASHED IDENTIFIER.**
  `send_complete_registration_event` has always taken a `phone` and never had
  one to hash — a conversion carrying an email AND a phone matches back to
  whoever saw the ad more often, so this is an attribution improvement rather
  than only a stored field.
- **THE UPSERT COALESCES THE PHONE WHERE IT OVERWRITES THE NAME AND CLUB.**
  Those two are always present, so a resubmission correcting them is
  unambiguous; a phone can legitimately be absent (a browser served an older
  bundle mid-deploy, a caller that is not the form), and losing a stored number
  to one of those is worse than keeping a stale one. A new number still wins.
- **MIGRATION 297 RE-RUNS THE WHOLE SHARED LIST rather than issuing a lone
  ALTER**, so the CREATE covers a fresh database and an idempotent
  `ADD COLUMN IF NOT EXISTS` covers one already at 296 — one list, no second
  copy of the column to drift. **Its downgrade drops the COLUMN, never the
  table**: 296 owns the table, and copying 296's downgrade would destroy every
  registration over one column. The suite pins that.
- **Verified** (the backend suite is 173 now: the pre-297 table rebuilt in raw
  SQL and carried across with its rows, an earlier registration reading as no
  phone rather than a blank, the number stored as typed, the corrected number
  landing, a phone-less write not blanking one already stored, five shapes of
  real number accepted incl. a landline and an international one, four
  refusals, and the staff list carrying it) **with a control run**: 22 fail
  against the previous commit and the run REPORTS rather than crashing.
  **Driven in Chromium** (93: the field with its `tel` type, inputmode and
  autocomplete, its label, the exact number on the wire, and both refusals
  posting nothing and claiming no conversion) **with a control run**: 8 fail.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN, hit twice in one change.**
  The backend's `SELECT phone` died on an `UndefinedColumnError` and said
  nothing about the other 150 checks; the browser's bare `fill('#demo-phone')`
  hung 30s on the locator and killed the run after six. Every phone read is
  presence-checked now — `row.get("phone")` over `row["phone"]`, `attrOf()`
  over a bare `getAttribute`. **The browser's refusal checks needed the WHOLE
  BLOCK gated on the field existing, not each read guarded**: without the
  field those submissions SUCCEED, the form is replaced by the success state,
  and every later check in that section then hangs on a form that is gone.
  Guarding one read at a time just moved the crash further down.
- **NOTICED, NOT BUILT**: no reminder email before the event and no
  attended/no-show record afterwards, so "send the recording to everyone who
  registered" is a CSV export and a BetterComms list rather than one button. The
  event is one constant, so a second webinar means editing both copies rather
  than picking a row — `event_key` is on the table from the start for whenever
  that becomes worth a screen.

### What a review of the live page found, and one note it proved wrong (v9.71.3)

Four findings off `betterat.cricket/demo` as deployed. The pixel behaviour —
the part the page exists for — was confirmed correct; these are everything
around it.

- **THE PAGE ADVERTISED A RECORDING OF A DEMO THAT HAD NOT HAPPENED YET, on
  every share of the link.** `<title>` and the server card's `og:title` were
  both hardcoded to the post-event wording while the H1 correctly read "See
  BetterCricket in action". The tab is the small half; the card is the real
  one, because `usePageMeta` never reaches a crawler.
- **SO THE COPY MOVED TO WHERE THE DATE ALREADY LIVES.**
  `services/webinar.page_meta(is_past)` and `webinarState`'s `pageTitle` /
  `pageDescription`, mirrored the way every other string on this page already
  is, and asserted rather than trusted. **`_marketing_html` resolves `/demo`
  per request** and the entry is GONE from `MARKETING_PAGES` — a frozen dict
  cannot answer a question whose answer changes with the calendar, and leaving
  a stale one there is how the two disagree.
- **THE PHONE IS OPTIONAL, one week after shipping as required.** See the
  corrected note above for why the original argument loses. The 8-15 digit
  check still governs a number that IS typed; a blank one is a complete
  registration. The label says "(OPTIONAL)" — asking silently and accepting
  nothing is its own kind of dishonest.
- **THE STREAMYARD LINK WAS IN THE JS BUNDLE, so the form was bypassable by
  anyone who read the source.** It is off `WEBINAR` entirely now and comes from
  `GET /public/webinar`, a request the page already makes. Grep the BUILT
  bundle to confirm, not the source: `grep -rl <url> frontend/dist`.
- **THE FULL GATE IS NOT BUILT, AND THE REASON IS A DIRECT CONFLICT WITH THE
  BRIEF.** Genuinely gating registration means withholding `watch_url` from the
  page-load read and returning it only from the register POST — which is
  exactly the case the brief's own "a broken backend still hands over the link"
  rule exists for. The two are mutually exclusive. **What ships is the middle
  and it covers the failure that actually happens**: the register WRITE
  erroring still hands the link over, because the page-load READ has already
  succeeded. Only both failing leaves nothing, and there the page says what to
  do instead of drawing a button that goes nowhere.
- **THE OVERLAPPING LOCKUP WAS THE FOUR-LISTS TRAP, NOT A LOGO PROBLEM.**
  Reported as "the header logo renders clipped at narrow widths — it reads as
  'iiB Be… Cricket' with the wordmark overlapping the mark", which reads as a
  CSS bug. Measured instead of guessed: `/demo` renders **a `HEADER` at y=0
  AND a `NAV` at y=0**, the club `Navbar` and the page's own `MarketingNav`
  stacked. The mark is three bars and a B ("iiB"), so two lockups a few pixels
  apart is exactly the reported string.
- **THE FOURTH LIST IS `lib/marketingPaths`, AND IT IS THE ONE THAT MATTERS
  HERE.** `og_preview.RESERVED_ROOT_SEGMENTS`, `FaviconManager.RESERVED_ROOTS`
  and `SponsorFooter.RESERVED_ROOT_SEGMENTS` all had `demo` and `trial`; the
  list that suppresses the club Navbar did not.
- **BUT NOT `MARKETING_PATHS` ITSELF, and that distinction is the whole fix.**
  That list carries THREE behaviours: suppress the club Navbar, force the dark
  marketing theme, and show `ClubCTABar`'s "get your club on BetterCricket"
  bar. `/demo` and `/trial` want only the first — each forces LIGHT with its
  own `data-theme` wrapper, and each IS a conversion page with its own call to
  action, so a second competing CTA across the bottom is the friction they
  exist to avoid. `OWN_NAV_PATHS` / `rendersOwnMarketingNav` is that one
  behaviour on its own.
- **Verified against a real Postgres** (`verify_webinar.py`, 198 checks: both
  page-meta states and the two differing, the mirror carrying both titles, the
  share card built from the state and the retired literal gone from it, `/demo`
  no longer frozen in `MARKETING_PAGES` while another page still is, the watch
  url absent from the mirror, and a blank phone registering, storing nothing
  rather than a blank string, still being handed the link and still sending the
  conversion with no phone to hash) **with a control run**: 8 fail against the
  previous commit, named, with the other 171 still reported.
- **A CHECK THAT COMPARES AGAINST AN EMPTY STRING CANNOT FAIL, and the control
  run is what caught it.** The two share-card checks did `want_title in card`
  with `want_title` defaulting to `""` when `page_meta` was absent — trivially
  true. They assert the value is non-empty first now.
- **Driven in Chromium** (111: the title in both states and `og:title` agreeing
  with it, EXACTLY ONE header at the top of the page, the phone field not
  marked required and its label saying optional, a blank phone posting and
  reaching the success state, a malformed one still refused, the link handed
  over being the one the server sent rather than a constant, and both calls
  failing drawing no dead link) **with a control run**: 12 fail against the
  previous commit, reporting the title as `Watch the BetterCricket demo | Live
  demo + Q&A` and **THREE** headers at the top of `/demo` and of `/trial`.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN, hit again in this same
  file.** The new blank-phone block opened with a bare
  `getByTestId('demo-success').waitFor()`, which is exactly what a
  required-phone build never reaches — so the control died there and said
  nothing about the seventy checks below it. `reachedSuccess()` reports rather
  than throws, and every read that depends on the success state is gated on
  it: guarding one read at a time is not enough when a whole block assumes a
  form has been replaced.


### A disabled button that does not say why reads as broken (v9.71.4, Sep 2026)

Reported: "rediscover committee is disabled on club directory".

- **NOTHING WAS BROKEN, AND THE GATE IS RIGHT.** `disabled={busy === 'rediscover'
  || rediscoverRunning || status?.paused}` — the third one was true, because an
  operator had the crawler stopped. That is correct rather than merely cautious:
  `rediscover_all` returns `{"skipped": "stopped"}` while the flag is set, so a
  button that let you press it would report a finished run that never read a
  page. **The silence was the bug**, and it is the same call this file already
  records for a figure that is correctly zero — it still has to explain itself.
- **THE STOP IS SET TWO ROWS AWAY, which is what made it unreadable.** The crawl
  button beside it is at least next to its own Start crawling button and under
  the red "Stopped" pill; the committee row has neither, so a greyed-out
  Rediscover had nothing anywhere near it to connect the two. One reason string
  now drives the disable, the tooltip and a line beside the button, so the three
  can never disagree.
- **"PAUSED" MEANS TWO DIFFERENT THINGS IN ONE PAYLOAD, and gating on the wrong
  one would have been a real bug.** `crawl_status` emits `state == 'paused'` for
  a runner merely on a break and `state == 'stopped'` for the operator's flag —
  and it is the separate `paused` BOOLEAN that the button reads. Gating on the
  word would kill the button every time the crawler breathed. The suite asserts
  a break leaves it live.
- **A RUN THIS PROCESS HAS LOST TRACK OF USED TO KILL THE BUTTON FOR GOOD.**
  `_rediscover` is in-process and `POST /rediscover` has a 12-hour `_bg_stale`
  escape hatch — so the server would happily start a new run while the screen,
  reading `running` alone, kept it disabled with no way to reach that hatch.
  **The server reports `stale` on its own status now** rather than the browser
  keeping a second copy of the window, which is the one-definition rule this
  file keeps everywhere: the disable and the server's own decision have to be
  the same decision, and the suite asserts they agree both ways.
- **A SKIPPED RUN IS NOT A FINISHED ONE.** `{"skipped": "stopped"}` was
  formatted through the ordinary success path and printed "0 club(s) re-read" —
  which reads as "it ran and there was nothing to do". The same mistake
  `_settle_bg` exists to stop for a soft error, reached from the other end.
  **Found by the browser suite, not by reading it**: the poll's message was
  fixed and the "Last rediscover:" line beside the button was not, and it reads
  the same result dict.
- **Verified against a real Postgres**
  (`backend/verification/verify_rediscover_gating.py`, 19 checks through the
  shipped route body and services: the two meanings of paused kept apart, the
  Stop flag genuinely refusing a rediscover, a 45-minute run NOT stale, a
  day-old one stale, the status and the POST agreeing both ways, a malformed
  start time freeing the button rather than wedging it, and the payload
  otherwise untouched) **with a control run**: 7 fail against the previous
  commit, one of them reporting `stale=None allowed=True` — the server willing
  and the screen refusing.
- **Driven in Chromium** (`verify_rediscover_gating_browser.mjs`, 24: the
  reported case reproduced, the reason on screen and in both tooltips, nothing
  drawn when nothing is blocked, a break not disabling anything, a stale run no
  longer holding it, and the skipped run reported honestly) **with a control
  run**: 9 fail, while "the button is disabled" PASSES in both — the disable was
  never the bug.
- **A LOCATOR KEYED ON A NEW TESTID ALONE MEASURES THE HARNESS.** The first
  control run reported "button not found" everywhere, which says nothing about
  behaviour; it falls back to the label so the old build's button is found and
  fails on what it does. The label itself is checked, so it cannot be the
  primary locator — it reads "Rediscovering..." in exactly the state the suite
  is about.
- **`const URL = ...` SHADOWS THE GLOBAL `URL`** and every `new URL(...)` in the
  route handler dies with "URL is not a constructor".

### And then the gate itself was wrong (migration 298, v9.71.5, Sep 2026)

Asked straight after the fix above: if they are two different jobs, why must the
crawler be restarted to run one of them? Then, once the trade-off was put:
"I do want the ability to stop all crawling traffic with PlayHQ. But I also want
the ability to re-start the crawl, which should re-discover both new and existing
clubs and pick up changes in address, associations, officers etc. The Re-discover
committee members should just run through the existing clubs... (and I should be
able to launch this function even if the typical Crawl is stopped)."

- **THE GATE WAS PROTECTING NOTHING, AND THE OBVIOUS FEAR IS THE WRONG ONE.**
  "A partial rediscover could empty the directory" is false: `_prune_committee`
  is scoped `marketing_club_id = :club` and compares against the ids seen in
  THAT CLUB'S OWN payload, and `_upsert_club(prune=True)` is called per club as
  each page lands. So a run stopped at page N leaves every club on pages N+1..end
  untouched rather than emptied. What the gate actually saved you from was a
  no-op: `discover_clubs` polls the flag at the TOP of the loop, so a rediscover
  started while stopped broke before page one and returned zeroes.
- **THE PLATFORM ALREADY DISAGREED WITH ITSELF, which is the tell that a rule is
  inherited rather than decided.** `rediscover_club` (one club, from its own row)
  bypasses `discover_clubs` entirely and calls `_upsert_club(prune=True,
  retick=True)` direct — **no pause check at all**, and it has always run while
  stopped. If reconciling-while-stopped were unsafe, that one would be gated too.
- **SO STOP MEANS "STOP THE UNATTENDED CRAWLER", AND THE REDISCOVER CARRIES ITS
  OWN CANCEL.** `discover_clubs` takes a `should_stop` callable that DEFAULTS to
  `is_crawl_paused`, so every background path (the continuous runner,
  `crawl_batch`, `enrich_associations`) is byte-for-byte unchanged and the switch
  still stops all unattended traffic. Only `rediscover_all` passes something
  else. The suite presses each background path with the flag set for exactly
  this reason — letting the rediscover through is only defensible while that half
  holds.
- **A RUN THAT IGNORES THE GLOBAL STOP MUST HAVE A STOP OF ITS OWN, or the
  ability to halt all PlayHQ traffic quietly disappears the moment one is
  running.** `POST /rediscover/stop` raises an in-process cancel (in-process is
  right — the run itself is), and starting a run CLEARS it, or a stale cancel
  would kill the next rediscover before its first page. The suite asserts the
  cancel is the check the run actually asks, not a flag nothing reads.
- **A HALTED RUN IS NOT A FINISHED ONE**, the rule this file already records for
  a skipped one, reached from the other end. `discover_clubs` reports
  `stopped: True` when it broke off with pages to go, so the screen says
  "stopped part way" rather than printing the finished line over a partial pass.
- **THE ASSOCIATION WAS THE ONLY REAL GAP IN "PICK UP CHANGES", and two thirds of
  that ask were already true.** `_upsert_club` rewrites name, website, suburb,
  state, postcode and coordinates on EVERY pass, and newly listed officers are
  already added — both are now asserted rather than claimed, which is what makes
  "nothing to build there" an answer. But `enrich_associations`'s frontier was
  `associations IS NULL` and nothing else, so a club's associations were fetched
  once and frozen for the life of the row: a club that moved association kept the
  old one for ever and no crawl would ever correct it.
- **`last_crawled_at` CANNOT ANSWER "WHEN WERE THE ASSOCIATIONS READ".** Discovery
  bumps it for every club it sees, so it records when the club was last SEEN.
  Hence `marketing_clubs.associations_fetched_at` (298), stamped only on a
  SUCCESSFUL fetch — a PlayHQ wobble must not buy a club another 90 days of
  staleness.
- **THE BACKFILL IS SERVED BEFORE ANY REFRESH** (`case((never_fetched, 0),
  else_=1)`), or refreshes starve the clubs nobody has ever enriched.
- **`frontier_remaining` STILL MEANS NEVER-FETCHED ONLY, and that is
  load-bearing.** `run_continuous` reads it as "is the backfill finished" and
  sleeps to the next window at 0; folding refreshes in would mean the runner
  never considered itself done and hot-looped. Refreshes ride alongside as
  `refresh_due`, and get PROCESSED because they are in the frontier QUERY.
- **THE MIGRATION BACKFILLS THE STAMP RATHER THAN LEAVING IT NULL**, or the whole
  directory becomes refresh-due in one burst on the day it ships. Stamped from
  `COALESCE(last_crawled_at, first_seen_at)`, so the longest-unseen clubs come
  due first and the rest drain at the crawler's own pace. Only where
  `associations IS NOT NULL`, so a never-fetched club stays on the ordinary
  backfill frontier.
- **A REFRESH CAN COME BACK EMPTY WHERE A FIRST FETCH COULD NOT** — the club has
  left every association it played in — so `association_name`/`association_guid`
  (a denormalised copy of `assocs[0]`) are CLEARED. Leaving them would show an
  association the club no longer plays in. Unreachable before this change, which
  is why it was never handled.
- **Verified against a real Postgres**
  (`backend/verification/verify_rediscover_gating.py` is 34 checks now, and
  `verify_assoc_refresh.py` is 21: 298 applied three times to a populated pre-298
  table, the backfill stamping only the right rows, a stale club back on the
  frontier and a fresh one not, the backfill served first, a failed fetch not
  restamping, an empty refresh clearing the name, 0 days restoring the pre-298
  behaviour, every background path still honouring the Stop, a rediscover running
  while stopped and storing what it read, the cancel halting it, and a club the
  halted run never reached left exactly as it was) **with two control runs**:
  with both behaviours reverted 8 of the gating checks and 4 of the refresh
  checks fail, reporting the club's own `{'skipped': 'stopped'}` and its stale
  "Old Assoc"; with the feature absent both suites REPORT it by name rather than
  dying on the first import or the missing parameter.
- **A FAKE THAT REPORTS ITS OWN ROW COUNT AS `totalRecords` IS 'FINISHED' AFTER
  PAGE ONE.** `discover_clubs` stops once `(pages_done * 100) >= totalRecords`,
  so the first cut's cancel could never be reached — and "it never asked for
  page 2" PASSED for the wrong reason. The fake reports a high total by default
  now, and the caller lowers it only when running out of pages IS the check.
- **Driven in Chromium** (`verify_rediscover_gating_browser.mjs`, 32: the button
  live while the crawler is stopped, the crawl button beside it still held back,
  the Stop control appearing only while a run is going, its exact endpoint on the
  wire and never the crawler's own, a dismissed confirm sending nothing, and a
  halted run reported as halted) **with a control run**: 11 fail, naming
  `disabled=true` and the old build printing `Last rediscover: 412 club(s)` over
  a partial pass.
- **A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN, hit again here.** A bare
  `.first().innerText()` on the new note killed the control after three checks
  and said nothing about the other twenty-nine. Every read of an element this
  change ADDS goes through `textOf()`, which returns '' for an absent locator.

### One form, two lists: pushing the registrant into StreamYard (migration 300, v9.71.6)

Asked for directly, after the reminder below shipped: **"I want just one single
form and the registrants to be put into StreamYard as well as in BetterCricket
rather than making someone register twice."**

- **THE PUSH IS BUILT AND IT WORKS AGAINST THE LIVE API, verified through the
  SHIPPED function rather than a curl.** `POST oa-api.streamyard.com/api/public/
  webinars/{id}/registrations` returns **201** with the registration's id;
  `services/streamyard.push_registration` is what calls it, and every registrant
  is pushed as they arrive. So StreamYard's registrant list, its attendee report
  and its own reminders all know who is coming, off our one form.
- **REMOVING THE SECOND FORM IS STILL THE STREAMYARD TOGGLE, and that is not a
  shortcut — it is the only thing that works.** Three things were measured
  before settling on it, and each one closes a route that looks open from
  reading their bundle: the browser cannot register from our page (a CORS
  preflight from `betterat.cricket` answers **`{"message":"CORS error: Origin
  not allowed"}`**); a registration is bound to the SESSION that created it
  (`GET /webinars/{id}` reads `isUserRegistered: true` for the session that
  POSTed and **401s on the registration id alone**), so one our backend creates
  cannot be handed to the visitor's browser; and the `?token=` a StreamYard
  reminder links to is **not** the registration id — `/watch/{id}?token={id}`
  leaves `sessionRegistrationId` empty in the page's own server-rendered props,
  and so do `registrationId=`, `rid=` and both `embed=true` variants. **With the
  gate on there is no way to skip the form; with it off there is no form to
  skip.** The push is what makes turning it off cost nothing.
- **THE FIELD IDS ARE FETCHED, NEVER HARDCODED.** The payload keys on
  per-definition uuids (`fields.definitionId` + `fields.values[{field id}]`),
  which change the moment somebody edits the registration form in StreamYard —
  so `_field_map` reads `registrationFieldDefinitions` and maps by `type`,
  cached ten minutes so an edit is picked up within the hour rather than at the
  next deploy. Hardcoding them would work today and break silently the first
  time a field is added.
- **THE BROADCAST IS NEVER A SECOND CONSTANT.** `webinar_id_from` parses it out
  of `EVENT.watch_url`, which is already the one place the event is named. A
  watch link that is not StreamYard's yields None and every function no-ops,
  which is also what makes the next event's setup one line rather than two.
- **THEIR API IS IDEMPOTENT ON THE EMAIL BUT DOES NOT OVERWRITE**, verified:
  posting twice returns the SAME id and leaves the stored values alone. So a
  retry is free — and a row already pushed is skipped before any request is
  made, because re-pushing a corrected name would cost a request and change
  nothing at their end.
- **A REQUIRED FIELD CANNOT BE BLANK, AND A MONONYM IS THEREFORE SKIPPED RATHER
  THAN GIVEN AN INVENTED SURNAME.** Measured: `lastName: ""` is a **400** while
  an empty optional phone is accepted. A name we made up would sit beside that
  person's chat messages in front of everyone watching; they are still
  registered with us, still emailed, and — with the gate off — the link still
  lets them in. The reason is recorded on the row rather than being silent.
- **A SKIP IS NOT A FAILURE, and the staff list says so differently.** `no
  surname to send` and `the broadcast has no registration form` are rows there
  was nothing to do for; an HTTP error is one that went wrong. Both land in
  `streamyard_error`, and both read as `NOT SENT` with the reason on hover
  rather than as `FAILED`.
- **BEST-EFFORT AT EVERY STEP, because it is an undocumented API.** The
  registration is complete once our own row is written and the page has already
  handed the link over, so the push is backgrounded on its own session, never
  raises, and records its outcome on the row. Everything else — the
  registration, the confirmation email, the reminder, the link — works with
  this erroring, switched off, or removed by StreamYard tomorrow.
- **THE HOURLY PASS IS THE CATCH-UP, NOT THE MECHANISM.** `webinar_upkeep`
  (the reminder job, widened) pushes anyone with no id, so a registration taken
  before this existed and a push that failed on a wobble both self-heal. It
  settles — a second pass over a list everybody is on considers nobody and
  makes no request. `POST /club-admin/super/webinar-streamyard-sync` is the
  button for when an hour is too long to wait.
- **Verified against a real Postgres** (`verify_webinar.py`, 259 checks: the
  DDL adding the pair, the id derived from the watch link and a non-StreamYard
  link no-oping, all three name splits, a push stamping the id, a row already
  pushed skipped before any request, a mononym recorded as a skip with no id, a
  refusal recorded rather than raised, the catch-up making one request per row
  and settling to none, and the register route asserted structurally to fire
  it) **with a control run**: 7 fail against the previous commit and the other
  234 are still reported. **No live call is made by the suite** —
  `push_registration` is stubbed, because a verification run must not create
  real registrations in somebody's StreamYard account.
- **THE LIVE API WAS EXERCISED SEPARATELY, THROUGH THE SHIPPED FUNCTION**, which
  is the only way to know an undocumented endpoint's real shape: 201 with an id,
  a second push returning the same id, the mononym skipped and a non-StreamYard
  link no-oping. **It left four test registrations in the account**
  (`bettercricket-integration-test@`, `bc-it-a@`, `bc-it-b@`,
  `bc-shipped-fn-test@`, all `betterat.cricket`) and **there is no public DELETE
  — every id 404s** — so they have to be removed from the StreamYard dashboard
  by hand. Use an obviously-marked address if this is ever done again.
- **STILL ACCOUNT-SIDE**: turn registration OFF on the StreamYard broadcast.
  That is the half that removes the second form, and no code in this repo
  changes it. **Not established, because it needs that toggle flipped**: whether
  their API still accepts a push once registration is disabled. The push handles
  a refusal as an ordinary recorded error, so if it stops working the worst case
  is one form and our own list — check the StreamYard column after the first
  registration to see which way it fell.
- **AND THAT TOGGLE HAS A COST THIS NOTE ORIGINALLY FAILED TO NAME.** Reported
  straight back: "turning off registrations means i can't see the registrants
  list." Correct — StreamYard's registrant list AND its attendee report both
  hang off registration being on, so switching it off trades the second form
  for the attended-vs-registered split. It is a decision with two real sides,
  not a step: **our own list is complete either way** (name, email, club, phone,
  role, every campaign tag, CSV export), so the ONLY thing genuinely lost is
  who turned up. **Untested third path**: their form carries an "Already
  registered? Join here" link, and everyone the push registers genuinely IS
  registered at their end — so that link may admit a registrant on their email
  alone, keeping both. Not verified, so not asserted.

### A skip that does not say why reads as a broken button (v9.73.2, Sep 2026)

Reported: "It's not letting me push to streamyard - says 0 pushed, 2 skipped".

- **NOTHING WAS BROKEN, AND THE SILENCE WAS THE BUG** — the same call this file
  already records for the disabled Rediscover button and for a figure that is
  correctly zero. Both rows had a single-word name, and StreamYard's own form
  has firstName and lastName as separate REQUIRED fields: a blank surname is a
  **400, re-verified against the live endpoint** while diagnosing this (a
  refusal creates nothing, so it is a safe probe). The skip was right; the
  reporting was not.
- **THE OTHER TWO SKIP REASONS WERE RULED OUT BY MEASUREMENT, NOT BY READING.**
  The live broadcast still answers `isRegistrationEnabled: true` with one
  definition and all four fields, so "the broadcast has no registration form"
  was not it; and `webinar_id_from` parses the shipped watch link, so neither
  was "not a StreamYard broadcast". **A session failure is an ERROR, never a
  skip** — `_field_map` calls `raise_for_status()` and an unauthenticated
  `GET /webinars/{id}` answers **401**, which the outer handler records as a
  failure. So "skipped" could only ever have been the surname.
- **`sync_streamyard` REPORTS `reasons`, and the button names them.** A bare
  count is the whole reported problem; the counts and the distinct outcomes now
  come back together and the message reads them out.
- **THE REASON IS WRITTEN OUT ON THE ROW, NOT LEFT ON HOVER.** It was on a
  `title` tooltip, which is a state nobody can see — two rows reading NOT SENT
  with the explanation hidden is how a working feature reads as a fault.
- **A SKIP HAS TO BE FIXABLE OR THE REASON CAN NEVER STOP BEING TRUE.**
  `sync_streamyard` already retries a previously-skipped row on purpose ("the
  reason can stop being true if somebody corrects their name") — and nothing
  could correct the name, so the row was stuck for good and the retry was
  pointless. `PATCH /super/webinar-registrations/{id}` takes a name;
  an **Add surname** button is offered on exactly the rows where a
  single-word name is what is standing in the way, never on a row that pushed
  fine.
- **ONLY THE NAME IS EDITABLE, and that is deliberate.** The email is the
  identity these rows fold on (`(event_key, lower(email))`) AND what
  StreamYard's own idempotency keys on, so editing it would separate our row
  from the registration already made at their end. The campaign fields are the
  record of where a registration came from and are not ours to rewrite.
- **A SURNAME IS STILL NEVER INVENTED.** It would sit beside that person's chat
  messages in front of everyone watching. A person types the correction, or the
  row stays skipped and says so.
- **Verified against a real Postgres**
  (`backend/verification/verify_streamyard_skip_reporting.py`, 62 checks through
  the shipped service and route bodies: the reported run replayed — one pushed,
  two skipped — the reason counted and named, the reason landing on the row, a
  second press not re-registering the one already done while retrying the two,
  a corrected name then pushing, four refusals leaving the row exactly as it
  was, the email absent from the patch model, and the shipped name split)
  **with a control run**: 16 pass and **9 are REPORTED by name** rather than
  dying on the first missing attribute. **No live call is made** —
  `push_registration` is stubbed, because their API has no public DELETE and a
  verification run must not create real registrations in somebody's account.

### The form asked for one name where theirs needs two (migration 301, v9.73.3)

Reported straight after: "Can you double check the form then because it does
say first and last name so it should be pulling across - also, we want to
ensure we pull through a phone number."

- **THE PHONE ALREADY WORKED, AND SAYING SO BEAT BUILDING SOMETHING.** Verified
  by pushing a marked test registration through the SHIPPED payload shape and
  reading it back: `stored phone = '+61 400 111 222'`. It rides in
  `fields.values` under the fetched phone field id, is accepted while optional,
  and the same second POST returned the SAME id — their documented idempotency,
  re-confirmed. Nothing to fix.
- **THE FORM WAS THE MISMATCH, and the expectation was right.** StreamYard's
  registration form has First name and Last name as separate REQUIRED fields;
  ours had ONE field labelled `YOUR NAME`. So a registrant who typed one word
  left nothing to send. The two boxes are `given-name` / `family-name` and sit
  side by side, so two fields cost one line and one autofill tap — which is
  what keeps this from being real friction on the paid traffic this page exists
  for.
- **SPLITTING A STRING IS A GUESS, NOT A FIX.** At the first space it reads
  "Mary Jane Smith" as a surname of "Jane Smith", and it has no answer at all
  for a mononym. Asking for the halves is the only version that cannot be
  wrong, which is why the fix is the form rather than a cleverer splitter.
- **`name` STAYS AND STAYS AUTHORITATIVE.** The confirmation greeting, the
  reminder, the staff list and the CSV all read it, so it is stored as the
  joined whole and the halves sit beside it — no backfill, and nothing
  downstream changed.
- **A SPLIT-DERIVED PAIR IS STORED AS NULL, never as a pair.** `resolve_name`
  returns halves ONLY when both were given; a bare `name` (a browser served an
  older bundle mid-deploy — the rule `plan_report.unassigned` already keeps)
  stores NULL and the push falls back to splitting for itself. So NULL means
  "we only ever had one string", which is exactly what a pre-301 row is.
- **ONE HALF IS NOT A PAIR.** A surname box left empty IS the mononym case and
  has to read as one — storing a lone first name as a pair would push a blank
  surname, which is a 400 at their end.
- **THE HALVES ARE COALESCED WHERE `name` IS OVERWRITTEN OUTRIGHT**, the same
  call the phone already makes: `name` is always present so a correction is
  unambiguous, whereas a one-field resubmission carries no halves and losing a
  real pair to it is worse than keeping it.
- **`streamyard.resolve_push_name` IS THE ONE RULE, AND ITS OWN FUNCTION SO IT
  CAN BE CHECKED OFFLINE.** Everything else in `push_registration` talks to
  StreamYard, so four lines inline meant the fallback could only be tested by
  making a live call. **The stub CALLS it rather than retyping it** — a stub
  that reimplements the rule is measuring the harness.
- **THE STAFF CORRECTION SETS THE HALVES TOO**, or the row would keep pushing
  the old name, since the push prefers them. And the **Add surname** button is
  withdrawn once a row has both, so it only ever appears on the registrations
  taken before the form asked.
- **Verified** (the suite is 62 checks now: migration 301 applied three times
  over a populated pre-301 table with the existing row's name untouched and no
  invented halves, the downgrade dropping the two COLUMNS and never the table,
  every `resolve_name` branch, the halves reaching the row and being sent
  whole, the phone riding with them, a one-field resubmission not blanking a
  stored pair while still correcting the club, and a pre-301 row still pushing
  via the split) **with a control run**: 2 fail on the migration, **11 are
  REPORTED** and nothing crashes. **Getting that control run clean took two
  passes** — the suite's own `SELECT first_name` died on an
  `UndefinedColumnError`, and the shared stub called `resolve_push_name`
  unguarded; both are presence-checked now. **Driven in Chromium**
  (`verify_webinar_browser.mjs`: both fields with their autocomplete tokens and
  labels, both named in the validation message and marked invalid, and
  `firstName`/`lastName` on the wire rather than one string).

### The second form is StreamYard's, and the reminder that replaces it (migration 299, v9.71.5)

Reported with the campaign live: "when you enter your details it takes you to a
page where you click a link and then have to put details in again... it should
automatically go through to StreamYard and save the registration details so
that can be tracked. Where do the registrants go currently?"

- **REGISTRANTS HAVE ALWAYS BEEN TRACKED, and answering that first is what
  stopped this being built as a data-capture feature.** Every registration is a
  `webinar_registrations` row — name, email, club, phone, role, all five UTM
  tags and the fbclid — folded on `(event_key, lower(email))`, listed at
  **`/admin/super/onboarding`** under "Webinar registrations" with a CSV
  export. Nothing was going missing; the panel simply **opened collapsed**
  behind a `Show (N)` toggle, which is how a registration that landed reads as
  one that did not. It opens expanded now.
- **THE SECOND FORM IS STREAMYARD'S OWN, AND v9.71.2 PREDICTED IT EXACTLY.**
  That note read: "Whether that gate is switched on for this broadcast is a
  setting in StreamYard... **If it is on, a registrant fills a form twice** —
  the fix is a StreamYard setting, not a code change." Confirmed against the
  live broadcast: `isRegistrationEnabled: true`, and its fields are email,
  first name, last name (required) and phone (optional) — **every one of which
  our own form already collects**. So the fix is to switch that gate off in
  StreamYard, and nothing in this repo can reach it.
- **CARRYING THE DETAILS ACROSS IS CLOSED OFF, AND IT WAS MEASURED RATHER THAN
  ASSUMED.** StreamYard has an undocumented registration API
  (`POST oa-api.streamyard.com/api/public/webinars/{id}/registrations`) and the
  watch URL takes a per-registrant `?token=`, so an auto-handoff looks possible
  from the bundle. It is not: the API answers
  **`{"message":"CORS error: Origin not allowed"}`** to a preflight from
  `betterat.cricket`, so the visitor's browser cannot register there from our
  page. Server-to-server would bind the registration to OUR session rather than
  theirs, on an unversioned internal API, twelve days before the event — a
  worse trade than one setting.
- **SWITCHING THE GATE OFF COSTS EXACTLY ONE THING, so that one thing is now
  built.** StreamYard's registration is what sends its reminder; ours did not
  have one (`NOTICED, NOT BUILT` in the v9.71.2 note). `webinar.send_reminders`
  is the replacement.
- **THE WINDOW DECIDES, NOT A PINNED CRON.** The sweep runs hourly and returns
  immediately outside `REMINDER_LEAD_HOURS` (3) before the start — a one-shot
  cron at the right minute has to be moved by hand for the next event and
  misses entirely if the app happens to be restarting. It costs one indexed
  UPDATE matching nothing on all but a handful of runs in the event's life.
- **NOBODY WHO REGISTERED INSIDE THE WINDOW IS REMINDED.** Their confirmation
  went out minutes ago carrying the same link; a second one an hour later reads
  as a mistake rather than a courtesy.
- **`reminder_sent_at` IS THE CLAIM, NOT JUST THE RECORD.** The same UPDATE
  that selects the rows stamps it, so two overlapping runs cannot both email
  one person; a refusal HANDS THE CLAIM BACK and keeps its reason, so the next
  hour retries rather than one provider hiccup silently costing somebody their
  only reminder. A hard crash between the stamp and the send leaves it claimed
  and the reminder is missed — the conservative direction, since a duplicate is
  the one a registrant would notice.
- **NOTHING GOES OUT ONCE THE SESSION HAS ENDED.** A reminder landing after the
  event sends somebody to a stream that is over, which is worse than none.
- **A SEPARATE PAIR OF COLUMNS, NOT THE CONFIRMATION'S.** `reminder_sent_at` /
  `reminder_error` sit beside `email_sent` / `email_error` rather than
  overwriting them — two sends, two outcomes, so "did they get reminded" stays
  answerable independently of "did they get the confirmation".
- **`POST /club-admin/super/webinar-reminders` IS THE ESCAPE HATCH, NOT THE
  MECHANISM.** The reminder has one chance to be useful, so a "Send reminder"
  button exists for a sweep missed on the night. It runs the SAME function, so
  pressing it after the sweep emails nobody twice, and it refuses outside the
  window so it cannot fire a week early.
- **NUMBERED 299, NOT 298 — AND v9.71.5, NOT v9.71.4.** `origin/main` reached
  298 (`assoc_refresh`) and shipped its own `v9.71.4` changelog entry while
  this was in flight. **Six times now, and this is the first time the CHANGELOG
  collided in the same merge as the migration** — two files with one name is a
  merge conflict rather than a silent break, but check both. Migration 299
  re-runs the whole shared `webinar_ddl.STATEMENTS` list rather than issuing
  two lone ALTERs, and its downgrade drops the two COLUMNS, never the table —
  296 owns that.
- **Verified against a real Postgres** (`verify_webinar.py`, 232 checks: the
  DDL applied three times over a pre-297 table adding the reminder pair, an
  older registration reading as not reminded, the window at all four edges,
  nobody emailed before it opens, the late registrant and another event's
  registrant both left out, a second sweep emailing nobody twice, a refusal
  handing the claim back with its reason and the next run sending it, nothing
  after the session ends, the email's link and both timezones, the endpoint
  refusing outside the window, and the sweep asserted structurally to be
  registered on the scheduler) **with a control run**: 6 fail against the
  previous commit and the other 202 are still reported.
- **STILL ACCOUNT-SIDE, and it is the actual fix for what was reported**: turn
  registration OFF on the StreamYard broadcast. Until that is done a registrant
  fills two forms, and no code in this repo changes that.

<!-- END original CLAUDE.md L1827-2582 -->
<!-- BEGIN original CLAUDE.md L7437-7506 -->
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

<!-- END original CLAUDE.md L7437-7506 -->
<!-- BEGIN original CLAUDE.md L7507-7573 -->
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

<!-- END original CLAUDE.md L7507-7573 -->
<!-- BEGIN original CLAUDE.md L15249-15329 -->
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

<!-- END original CLAUDE.md L15249-15329 -->
<!-- BEGIN original CLAUDE.md L15330-15509 -->
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

<!-- END original CLAUDE.md L15330-15509 -->
<!-- BEGIN original CLAUDE.md L15510-15559 -->
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

<!-- END original CLAUDE.md L15510-15559 -->
