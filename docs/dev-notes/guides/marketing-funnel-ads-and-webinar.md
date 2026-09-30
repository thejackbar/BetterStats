# Guide: Marketing funnel, Meta ads reporting, webinar registration and self-serve attribution

**Read this before**:
- Touching `backend/app/services/meta_ads.py`, `routers/meta_ads.py`, `meta_capi.py`, or `frontend` `SuperMetaAds.jsx` (Meta Ads HQ), or anything that reads campaign spend, cost per result, funnels or "counting since".
- Touching `/trial`, `/demo`, `Trial.jsx`, `SelfServeTrialModal`, `routers/public_self_serve.py`, `lib/visitor.js`, `metaPixel`, `ClubCTABar`, `lib/marketingPaths.js`, `lib/clubPath.js`.
- Touching the webinar: `services/webinar.py`, `webinar_ddl.py`, `streamyard.py`, `data/webinar.js`, `webinar_registrations`, reminder or `.ics` code, "Webinar registrations" on `/admin/super/onboarding`.
- Touching `wizard_club_lists.py`, the Wizard Clubs page (`/admin/super/crm/wizard-clubs`), or `club_searched` / `club_prepared` beacons.
- Touching `usage_events`, `routers/usage.py`, `usePageView.js`, session duration, `page_exit`, visitor journeys.
- Symptoms: a pixel event firing on the wrong page or twice; cost per signup that includes the other product's spend; "Club selected" above "Started registering"; one visitor split across several club rows; a registration not counted against a campaign; a disabled button with no explanation.

**Archive** (full history, verbatim, do not load whole): `docs/dev-notes/archive/marketing-funnel-ads-and-webinar.md`. Grep hints: `ClubCTABar`, `prospect searched`, `ONE PIXEL EVENT`, `stream_for_ad`, `ad_daily`, `CANNOT FIRE ON STREAMYARD`, `webinar_registrations`, `push_registration`, `Rediscover`, `search beacon`, `run-collapsing`, `Wizard Clubs`, `public_self_serve`, `signup_attribution`, `counting since`, `CAMPAIGN_PLANS`, `time_on_page_ms`.

**Related guides**: club directory / BetterComms (Rediscover, engagement score, segments), billing and Stripe (self-serve trial checkout, coupons), CRM and sales workspace (Hot lead push, attribution reads `signup_attribution`), instructional videos (four-lists route trap), verification harness conventions.

## Standing rules

**Two products, one pixel event (v9.72.0, v9.72.1)**
1. `/trial` and `/demo` both fire `CompleteRegistration` at dataset 1317878090534903. Only `content_category` separates them: `self_serve_trial` (value 399 AUD) and `webinar` (no value). Never add a combined "registrations" total or a single campaign-wide funnel: a trial signup and a webinar registration are different things.
2. Spend is split per stream from the per-ad rows (`stream_totals`, `build_streams`). `campaign.cost_per_lead` is kept under its old name and now means the trial's own. Ad level is the finest split Meta gives, so the split is exact, not apportioned.
3. `stream_for_ad` looks up `AD_DESTINATIONS` first, then falls back to the ad's NAME (`Ad_Webinar_*`), so a new creative classifies with no code change. Never classify from the AD SET name (`AS_Cold_Broad_AU_LPV` is wrong about both broad and LPV).
4. `get_registration_count` reads `organisations`, so it only ever counted trial signups. The bug was the divisor, not double counting. Do not "fix" it by changing the count.
5. `meta_capi.send_complete_registration_event` defaults are the trial's (category, value 399) only because the trial was first. Every other caller (`public_webinar.py`) must name its own event, or Meta gets webinar signups labelled as A$399 trials.
6. Each stream carries a second figure measured from the last deliberate change (`stream_totals_since` sums `level='ad_daily'` rows on or after `_last_change_date()`). All-time figures must say they are all time. Lifetime is kept: it is the real money spent.
7. Add a deliberate change as a row in `CAMPAIGN_ANNOTATIONS` (`{date, label, detail}`); pacing is measured from it, never across it. One day after a change there are not two settled days, so the insight says nothing: correct.
8. Spend is settled, results are not. Spend pacing excludes only today; the 7-day attribution window applies to conversion insights only. Inside the window a since-figure cost is a ceiling: mark it provisional and never alert off it.
9. A partial window withholds the cost per result, and names why. `ad_daily` is retained `CAMPAIGN_LENGTH_DAYS + 5`, so an older change leaves spend short, which would understate cost (flatters the campaign).
10. A signup with no timestamp (orgs carry no `created_at`; use the earliest `self_serve_idempotency_keys` row) is reported as `undated_trial_results`, never guessed either side of the change. The manual leads adjustment is lifetime only, never applied to the since count.
11. `get_registration_count_since` shares `_attribution_matches_campaign` with `get_registration_count` so the two can never disagree about what counts, only about when. The lifetime function is never windowed.
12. `CAMPAIGN_UTM_*` is a SET of names per campaign because one campaign now carries two destination taxonomies. Unrecognised utm tags are dropped, so a missing entry reads as "the new ads produced nothing". After any rename in `meta_ads.py`, sweep every `ImportFrom` and `meta_ads.<attr>` in `app/` (a lazy import inside a function body survives `py_compile` and `vite build`).
13. Untagged webinar registrations (the ad's primary text has a plain link) are reported beside the cost per result, never absorbed. Cost per result is computed on the attributed count alone and reads high (the safe direction).
14. Recharts drops a `ReferenceLine` wrapped in a Fragment. `chartMarkers()` must return an array. A `ReferenceArea` draws as a `<path>`, not a `<rect>`.

**Meta Ads HQ reporting (migrations 200, 201, Jul 2026)**
15. The funnel has a "Club selected" stage (`get_club_selected_count`, distinct Meta-driven visitors who fired `club_prepared`) between landing page views and leads. It is our count, not Meta's.
16. `meta_ad_snapshots.updated_at` (migration 200) is set to `NOW()` on both INSERT and `DO UPDATE` in `upsert_snapshot`; "Last updated" reads it. `created_at` is frozen after the first refresh of a day.
17. Budget and length are per campaign: add each campaign to `CAMPAIGN_PLANS` (campaign_id to (budget, days)); `_campaign_plan()` falls back to `CAMPAIGN_BUDGET_AUD` / `CAMPAIGN_LENGTH_DAYS`. Never judge one campaign against another's plan.
18. The "counting since" cutoff (`platform_settings` key `meta_ads_counting_since`) resets on-site funnel STAT counts and Meta's own insights (`_date_range_params()`, date precision only). It NEVER windows the "Free trial registrations" KPI: a genuine registration must not vanish because the window reset. DB windows use `_SINCE_LOWER_BOUND` (`GREATEST(NOW() - days, COALESCE(:since,'-infinity'))`), so a cutoff only narrows.
19. The Clubs selected and Clubs searched TABLES are NOT windowed by the cutoff (they are a follow-up list). Their default window is 365 days, max 730 (`TABLE_DAYS_DEFAULT` / `TABLE_DAYS_MAX`).
20. The cutoff is seeded once in the lifespan guarded by a separate `meta_ads_counting_since_seeded` marker, so a super admin clearing it is not undone at the next restart. Meta-side numbers come from stored snapshots, so a cutoff change needs `run_snapshot()` (the UI "Reset from..." triggers one).
21. Meta's `campaign["leads"]` is the Lead action only (`_LEAD_ACTION_TYPES`). Never sum `complete_registration` into it: that double counts every completer and makes "Started registering" exceed "Club selected".
22. `_attribution_matches_campaign` accepts exact `utm_content`, then `utm_campaign`, then (last resort) a plain fb/ig/meta `utm_source` or facebook/instagram `click_source`. If a real registration still does not count (null attribution), the manual +/- adjustment with a note on the KPI is the documented correction.
23. `/track-step` rate limit is keyed by `visitor_id` when present, IP only as fallback. IP keying starved beacons behind Facebook in-app browser proxies and carrier CGNAT, producing "more selected than searched". Only `/search` (CA upstream) legitimately needs an IP cap.

**Search beacons and Wizard Clubs (v9.23.0, v9.23.1, migration 251)**
24. A `club_searched` beacon's top match is evidence of what the search engine did, not what the person wanted. The Wizard Clubs page collapses a visitor's consecutive queries into a run (`_same_typing_run`, prefix in either direction, `_SEARCH_RUN_GAP` 30 min) and resolves it to the clicked club, else the club matched by the LONGEST query typed. Fixed on the Wizard Clubs page ONLY, per direct instruction: `meta_ads.get_searched_clubs` (Meta Ads table) stays raw. Do not point the page back at it, and do not have the resolver write anything back.
25. `_query_identifies`: the club name must START with the query, at least 4 characters. `_query_is_ambiguous` demotes a match when the query prefixes more than one surfaced club ("south"). An unresolved search is reported as the query, keyed `search:<query>`, never as a club; `_improve_guesses` upgrades only when exactly one confident club starts with it and drops the guess when two fit. Query rows are never directory-matched or exported.
26. `result_count` rides on the beacon (both callers, `TrackStepRequest`, metadata; NULL for older beacons). Regex-match it before the `::int` cast: metadata is free-form.
27. `merged_wizard_clubs` folds the selected and searched tables on the stripped lowercase club name; a club in both is one row tagged `both`. Directory match is guid first (`club_prepared` captures the CA guid, same as `marketing_clubs.grassroots_guid`), name second.
28. "Has this club been emailed" is DERIVED (sent campaign audience `list_id`, `comms_recipients`, `comms_contacts.marketing_club_id`, only `status='sent'`, only lists this page created), never stored. Compare `list_id` as TEXT (free-form JSON; a `::uuid` cast aborts every row). `wizard_club_lists.list_id` has no FK on purpose (deleting a list must not erase history; row reports `deleted: true`).
29. Export follows the Club Directory rules: never an `excluded` club, never an unsubscribed contact, contacts linked to their directory club, `exported_at` stamped, existing address reused and never un-suppressed. An un-named generic mailbox gets `first_name = "Committee Members"` (`GENERIC_FIRST_NAME`). The browser sends club KEYS, never emails; the server takes addresses from its own data. A tick never targets a hidden club (selection is intersected with what is on screen).

**Self-serve public trial (v8.72.0, migration 161)**
30. `routers/public_self_serve.py` re-registers the internal handlers via `add_api_route` and hand-wraps only status, verify-email send and check, prepare and submit. Whole router 404s while `self_serve_registration_enabled` is off, and `/trial` redirects to `/`.
31. Guardrails: per-IP `rate_limit.enforce`, honeypot `website` field (non-empty gives a plausible fake success, nothing created), minimum fill time (`form_started_at` under 4s gives a generic 422; negative deltas ignored). Provider errors are swallowed to a generic message on the public send. OTP email is the real gate; no CAPTCHA.
32. Submit mints the session cookie and returns `redirect: "/admin"`; client sets `bs_pending_fresh_login`. Attribution: `organisations.signup_source` (`self_serve_ad` when first touch had a campaign or click signal, else `self_serve_organic`; NULL for non-public) and `signup_attribution` JSONB (allowlisted, clipped), written best-effort AFTER the commit. `_ATTRIBUTION_KEYS` in `public_self_serve` must learn any new tag (`utm_term` was captured nowhere until v9.71.1).
33. Public `prepare` fires a server Lead; `submit` fires CompleteRegistration (browser plus CAPI sharing one event id), GA4 `sign_up` and a `conversion` usage event. Use `publicMode` (not `public`, a reserved word) on `SelfServeTrialModal`.
34. Ad to lead-score report: `GET /club-admin/meta-ads/ad-signups`, reads the CACHED `marketing_clubs.engagement_score` via `existing_org_id`, never a live score per row.
35. Launch preconditions are config: flag on, a real `email_provider` (default `console` never sends the OTP), SPF/DKIM/DMARC, rate limiter is in-memory single-process.

**Club page call to action (v9.91.0, v9.92.1)**
36. The bar on a club dashboard is for PROSPECTS only: a session that arrived from a Meta click (utm_source meta/facebook/fb/instagram/ig, medium paid_social, or fbclid/igshid) or passed through `/trial`. Never a club's own members, never anyone signed in. Dismiss minimises to a pill. The club there is already registered (`/trial` navigates only for `already_registered`, and prepare/submit 409 it), so copy names the club and sells the visitor's OWN club; the wizard opens on a blank search.
37. Read campaign params from the session, not the address bar: `visitor.rememberLandingParams()` runs in `main.jsx` before first render into sessionStorage `bc:landingParams`. `metaPixel.buildFbcFromFbclid` falls back to that fbclid.
38. The bar must not draw on `/trial` or `/demo` (each has its own CTA). `lib/clubPath.publicClubSlug` is the one "is this a club page" rule shared with FaviconManager. CompleteRegistration still fires only on `status === 'completed'`.
39. Wording follows the ad: "Check out your club" / "Free · about 3 minutes · no card", no 14-day trial framing. The `/trial` placeholder names no real club (a real one sends prospects to somebody else's page). Keep the bar in step with the creative.

**Webinar registration (migration 296 onwards)**
40. A pixel cannot fire on a third-party domain, so registration happens on our page and success is RENDERED, never redirected (a redirect races the beacon). Order is persist, then fire; never on load, on click, or on a validation failure.
41. Fire the conversion only when the server says `created` (folds on `(event_key, lower(email))`). A resubmission claims no second conversion. A broken backend still hands over the link and fires nothing. Campaign columns are COALESCEd on upsert (fill, never overwrite); phone and the name halves are COALESCEd too.
42. `services/webinar.EVENT` and mirror `frontend/src/data/webinar.js` drive headline, button, promo and success state. The switch to the past state is the event's END. The server's `is_past` wins over the local clock (clock only covers first paint). The suite asserts the two copies agree. `_marketing_html` resolves `/demo` per request and the entry is gone from `MARKETING_PAGES`; title and og copy come from `webinar.page_meta(is_past)` and `webinarState`.
43. The recording link is a setting (`platform_settings.webinar_recording_url`, url-validated, `''` clears). The `.ics` is an endpoint (CRLF, UTC DTSTART). The StreamYard link is NOT in the JS bundle: it comes from `GET /public/webinar` (grep `frontend/dist` to confirm).
44. Phone is OPTIONAL (8 to 15 digits when typed, `PHONE_MIN_DIGITS`/`PHONE_MAX_DIGITS`), stored as typed, deliberately not `admin_identity.mobile_valid`. Label says optional. It rides on the conversion as a second hashed identifier.
45. First and last name are separate fields (migration 301). `name` stays authoritative (joined whole); the halves are stored ONLY when both were given (`resolve_name`); one half is not a pair. `streamyard.resolve_push_name` is the one rule and the stub must CALL it, never retype it. A surname is never invented.
46. Not `club_onboarding_requests`, and no Hot lead push to any CRM (per direct instruction): a demo registration is a weaker signal than "onboard my club".
47. `demo` and `trial` must be in the FOUR top-level-slug lists (`og_preview.RESERVED_ROOT_SEGMENTS`, `FaviconManager.RESERVED_ROOTS`, `SponsorFooter.RESERVED_ROOT_SEGMENTS`, `lib/marketingPaths.MARKETING_PATHS`), else the path resolves as a club slug (wasted `/api/clubs/<slug>` 404, club Navbar over the page nav). But not INTO `MARKETING_PATHS` for the behaviours they do not want: `OWN_NAV_PATHS` / `rendersOwnMarketingNav` is the one behaviour (suppress club Navbar) alone. `MARKETING_PATHS` also forces dark theme and shows `ClubCTABar`.
48. Reminder (migration 299): `webinar.send_reminders` window is `REMINDER_LEAD_HOURS` (3) before start until end, decided by the window not a pinned cron, run hourly by `webinar_upkeep`. Nobody who registered inside the window is reminded. `reminder_sent_at` is the CLAIM (same UPDATE selects and stamps); a refusal hands the claim back with `reminder_error`. Separate columns from the confirmation's `email_sent`/`email_error`. Nothing after the session ends. `POST /club-admin/super/webinar-reminders` runs the same function and refuses outside the window.
49. StreamYard push (migration 300): `services/streamyard.push_registration` posts to `oa-api.streamyard.com/api/public/webinars/{id}/registrations`. Field ids are FETCHED (`_field_map`, cached 10 min), never hardcoded. The broadcast id is parsed from `EVENT.watch_url` (`webinar_id_from`); a non-StreamYard link makes every function no-op. Their API is idempotent on email but does not overwrite; a pushed row is skipped before any request. A mononym is skipped with a recorded reason (blank surname is a 400). Best-effort, backgrounded on its own session, never raises. The hourly pass is the catch-up (`sync_streamyard`, button `POST /club-admin/super/webinar-streamyard-sync`). Skip is not failure: "NOT SENT" with the reason written on the row, not on hover.
50. Only the name is editable on a registration (`PATCH /super/webinar-registrations/{id}`): email is the fold key and StreamYard's idempotency key; campaign fields are the record of origin. "Add surname" shows only where a single-word name is the blocker. `sync_streamyard` reports `reasons` counts.
51. Removing StreamYard's own second form is a StreamYard setting (registration toggle), not code: browser CORS refuses `betterat.cricket`, a registration is bound to the session that made it, and the reminder `?token=` is not the registration id. Turning it off loses their registrant list and attendee report; our own list is complete.

**Club Directory Rediscover gating (misfiled in this archive; see Flags)**
52. A disabled button must say why: one reason string drives the disable, the tooltip and a line beside the button. "Paused" means two things in one payload: `state == 'paused'` (runner on a break) versus the `paused` BOOLEAN (operator Stop). Gate on the boolean.
53. Stop means "stop the UNATTENDED crawler". `discover_clubs` takes `should_stop` defaulting to `is_crawl_paused`; only `rediscover_all` passes its own cancel (`POST /rediscover/stop`, in-process, cleared at run start). A halted run reports `stopped: True`, never the finished line. Server reports `stale` on its own status (12 h `_bg_stale`) so screen and POST agree. `{"skipped": "stopped"}` is not a finished run.
54. `enrich_associations` refreshes stale associations (`marketing_clubs.associations_fetched_at`, migration 298, stamped only on a SUCCESSFUL fetch, backfilled from `COALESCE(last_crawled_at, first_seen_at)`), never-fetched served first. `frontier_remaining` still means never-fetched only (the runner reads it as "backfill done"). An empty refresh clears `association_name`/`association_guid`.

**Usage tracking (migration 165, v8.75.0)**
55. Time on page is a `page_exit` event (`usePageView.js`: `sendBeacon` on `pagehide`, on `visibilitychange` hidden, and on route change) writing `usage_events.time_on_page_ms` via `POST /usage/event/exit`, clamped to 24 h. Session duration is computed on read: a session is `page_view`s grouped on a gap of 30 minutes or more; duration is first to last page_view PLUS the final page's dwell (else single-page bounces read 0).
56. `GET /club-admin/usage/journey?visitor_id=` is the only per-visitor endpoint. `comms._apply_utm` must check each UTM key independently (the old whole-block skip dropped `utm_campaign` when a template hand-placed `utm_source`). `usePageView` sends the CURRENT URL's UTM (`visitor.getCurrentUtm()`) over the sticky first-touch one.

## Traps and failure signatures

- Webinar/`/trial` pixel checks pass on the wrong thing: `addInitScript` cannot stub `gtag` (`index.html` redefines it; read `window.dataLayer`); `fbq` IS stubbable. `waitUntil: 'networkidle'` never settles (HeartbeatBeacon pings every ~25s): wait for the element. A `click({force:true})` on a disabled button hangs: read `isDisabled()` and dispatch directly.
- A device with a wrong clock showed the wrong webinar state (offered a recording that does not exist) until the server's `is_past` took precedence.
- Two lockups on `/demo` or `/trial` ("iiB Be... Cricket"): club `Navbar` over `MarketingNav`, the four-lists trap (rule 47).
- Page advertises a recording before the event: `<title>` and `og:title` were hardcoded post-event; crawlers never run `usePageMeta`.
- Cost per signup too high after adding the webinar ad: divisor included the other stream's spend (rule 2).
- Reference line missing on a chart with no error: Fragment (rule 14). "Shaded band not found": `<path>`, and measure its width too.
- `\d` inside a JS template string passed to `page.evaluate` is just `d`; CSS-`uppercase` text reads transformed via `innerText`; a `data-post-frame`-style locator on a new testid alone measures the harness (fall back to the label so the old build is found).
- A check comparing against `''` or using `.every()` on an empty array is vacuously true. Gate "absence is correct" checks on the block existing first.
- Rediscover button disabled with no note: rule 52. Crawl "paused" read as break versus stop: rule 52.
- "Skipped 2, pushed 0" on StreamYard push: mononyms (blank surname 400). Not a fault; reason must be on the row (v9.73.2).
- Duplicate webinar conversions in Meta CAPI: only fire on `created`.
- Warm prospect rows split into phantom clubs ("Warn" as "Warners Bay"): rule 24.
- "More clubs selected than searched": `/track-step` IP keying (rule 23) or windowing the tables (rule 19).
- "Last updated" never moves after first refresh: `updated_at` not set on conflict (rule 16).

## How to verify a change here

- Backend (real Postgres, shipped route bodies): `backend/verification/verify_meta_ads_streams.py` (per-stream cost, since figures, guards; control with the feature absent REPORTS missing parts by name; with the window and guards neutered the trial's since-spend reads its lifetime figure and a partial window prints a cost instead of withholding), `verify_webinar.py` (DDL three times, mirror agreement, resubmission guard, bot guards, reminder window edges, page meta, phone, name halves, StreamYard push stubbed; controls fail on those parts), `verify_streamyard_skip_reporting.py` (skip reasons on the row, corrected name pushes).
- Browser (Chromium, argv-driven): `frontend/verification/verify_meta_ads_streams_browser.mjs`, `verify_webinar_browser.mjs`, `verify_club_cta_browser.mjs` (34 to 41 checks; control fails the new ones). Note the suite for the CTA bar records what `fbq` is called with; Meta Events Manager Test Events is NOT covered (needs a real registration).
- Never run a live push to StreamYard in a suite: their API has no public DELETE. Stub `push_registration`. If you must probe live, use an obviously marked address; the earlier probes left four test registrations (`bettercricket-integration-test@`, `bc-it-a@`, `bc-it-b@`, `bc-shipped-fn-test@`) to remove by hand in the StreamYard dashboard.
- Control runs must REPORT, not crash: read new keys with `.get`, wrap presence checks (`textOf()`, `seen()`, `reachedSuccess()`), and gate whole blocks (a blank-phone submit on a required-phone build never reaches the success state).
- Compare pass sets between run and control (`comm -12` of the two PASS lists): any check naming the new feature that passes in both is either a don't-regress guard or passing for the wrong reason.
- For search-beacon and wizard-clubs, self-serve and usage changes no verification suite is present in `backend/verification` (see Flags).

## Operator commands and scripts

- No standing scripts in this area. Diagnostics for engagement: `python -m app.scripts.recalc_engagement`, `top_engaged` exist (see the CRM guide).
- Deploy-time or account-side steps that code cannot do: verify `betterat.cricket` in Business Manager; put `CompleteRegistration` in the Aggregated Event Measurement priority list; set the ad's `conversion_domain`; turn registration OFF on the StreamYard broadcast if the second form is unwanted (costs the registrant list and attendee report); set `webinar_recording_url` after the event; SPF/DKIM/DMARC and a real `email_provider` for the OTP; flip `self_serve_registration_enabled` at launch. Creative fix noted: the ad reads "WAST" (West Africa), Perth is AWST.
- After a change to `CAMPAIGN_UTM_*` or `AD_DESTINATIONS`, press Refresh now (`run_snapshot`) to see Meta-side numbers move.

## Open follow-ups

- Nothing reads Meta's own `content_category` breakdown, so Meta-reported conversions cannot be split by product (only shown as "Meta-reported").
- `CAMPAIGN_PLANS` is one budget per campaign, not per stream; pacing is campaign-wide.
- No reminder email beyond the one before the webinar and no attended versus no-show record; the event is one constant, so a second webinar means editing both copies (`event_key` exists on the table).
- Untested: whether StreamYard's "Already registered? Join here" link admits a pushed registrant on email alone; whether their API still accepts a push once registration is disabled.
- Full webinar gate (withhold `watch_url` until register POST) is not built: it conflicts with "a broken backend still hands over the link".
- Wizard Clubs: none noted. Usage: none noted.

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-MKT-1] Archive says `CAMPAIGN_UTM_NAMES` became a set per campaign | code now names it `CAMPAIGN_UTM_CAMPAIGNS` (`meta_ads.py:190`, imported by `sales_workspace.py:718`); `CAMPAIGN_UTM_NAMES` no longer exists | ONE CAMPAIGN, TWO PRODUCTS (orig L789-994) | keep the rule, use the new name.
- [FLAG-MKT-2] Archive names `_META_VISITOR_SUBQUERY` and `_META_VISITOR_SUBQUERY_PLAIN` and a factory `_meta_visitor_subquery(bound)` | code shows `_META_VISITOR_EXISTS = _meta_visitor_exists(_SINCE_LOWER_BOUND)` | Meta Ads HQ follow-up (orig L15458-15509) | verify current names before editing; the since versus plain-days split still holds.
- [FLAG-MKT-3] Webinar section says the phone is REQUIRED (v9.71.2 note) then optional | archive itself reverses it in v9.71.3 | THE CONVERSION CANNOT FIRE ON STREAMYARD'S DOMAIN (orig L1827-2032) | rule 44 is current (optional).
- [FLAG-MKT-4] Archive says a link "is in the JS bundle" then "off WEBINAR entirely" | superseded by v9.71.3; `EVENT.watch_url` still lives server side in `webinar.py:73` | same section | keep rule 43.
- [FLAG-MKT-5] Two archive sub-notes both carry v9.71.5 (gate/298 Rediscover and reminder/299) and "One form, two lists" says v9.71.6/300 | version labels collided at merge time (archive itself notes renumbering) | orig L2179-2582 | treat migration numbers (296, 298, 299, 300, 301) as authoritative, versions as unreliable.
- [FLAG-MKT-6] Three sub-notes (v9.71.4 disabled Rediscover, migration 298 gate, association refresh) are Club Directory rules nested under the webinar section by position | not webinar code | orig L2117-2281 | move into the club directory guide; captured here as rules 52 to 54 only.
- [FLAG-MKT-7] Wizard Clubs "Clubs searched" table (v9.23.0) versus v9.23.1 | the later section changes how the searched rows are built (`resolved_searched_clubs`); `wizard_club_lists.py:14` docstring confirms | Clubs Searched or Selected (orig L7507-7573) | later wins, read both.
- [FLAG-MKT-8] Self-serve section says Twenty must be configured to land the Hot-100 Lead | Twenty was retired in v9.71.0 (CRM guide); `push_self_serve_registration` may be renamed | Public self-serve trial signup (orig L15249-15329) | verify before relying; launch precondition is otherwise config.
- [FLAG-MKT-9] Verification suites cited for Sections 4 to 8 (wizard clubs 47 checks, search beacon 36, self-serve, usage) | none found in `backend/verification` or `frontend/verification` (only meta_ads_streams, webinar, streamyard_skip, club_cta) | orig L7437-7573, L15249-15559 | verify or retire the claim.
- [FLAG-MKT-10] Webinar event date (Mon 21 Sep 2026) is a hardcoded constant | today is past that date, so the page should already be in the post-event state | webinar section | verify `EVENT` and set `webinar_recording_url`.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| The club page a prospect searched their way to asks them to start (v9.91.0), L399-453 | rules extracted | Standing rules 36 to 39; Traps (pixel checks) |
| ONE CAMPAIGN, TWO PRODUCTS, ONE PIXEL EVENT (v9.72.0), L789-994 | rules extracted | Standing rules 1 to 5, 12 to 14; Traps; Open follow-ups |
| &nbsp;&nbsp;The trial's cost was still a lifetime average (v9.72.1), L907-994 | rules extracted | Standing rules 6 to 11 |
| THE CONVERSION CANNOT FIRE ON STREAMYARD'S DOMAIN (migration 296, v9.71.1), L1827-2582 | rules extracted | Standing rules 40 to 47; Traps; Flags 3, 4, 10 |
| &nbsp;&nbsp;What a review of the live page found (v9.71.3), L2032-2116 | rules extracted | Rules 42 to 44, 47; Traps (title, lockup) |
| &nbsp;&nbsp;A disabled button that does not say why reads as broken (v9.71.4), L2117-2178 | rules extracted (misfiled: Club Directory) | Rule 52; Flag 6 |
| &nbsp;&nbsp;And then the gate itself was wrong (migration 298, v9.71.5), L2179-2280 | rules extracted (misfiled: Club Directory) | Rules 53, 54; Flags 5, 6 |
| &nbsp;&nbsp;One form, two lists: pushing the registrant into StreamYard (migration 300, v9.71.6), L2281-2382 | rules extracted | Rules 49, 51; Traps; Verify (no live calls) |
| &nbsp;&nbsp;A skip that does not say why reads as a broken button (v9.73.2), L2383-2435 | rules extracted | Rules 49, 50; Traps |
| &nbsp;&nbsp;The form asked for one name where theirs needs two (migration 301, v9.73.3), L2436-2498 | rules extracted | Rule 45 |
| &nbsp;&nbsp;The second form is StreamYard's, and the reminder that replaces it (migration 299, v9.71.5), L2499-2582 | rules extracted | Rules 48, 51; Open follow-ups; Flag 5 |
| A search beacon's top match is NOT the club they wanted (v9.23.1), L7437-7506 | rules extracted | Rules 24 to 26; Traps; Flag 7 |
| Clubs Searched or Selected in the Wizard (migration 251, v9.23.0), L7507-7573 | rules extracted | Rules 27 to 29; Flag 7 |
| Public self-serve trial signup + ad attribution (v8.72.0), L15249-15329 | rules extracted | Rules 30 to 35; Flags 8, 9 |
| Meta Ads HQ, Club Selected stage, stale last updated, undercounted registrations, per-campaign pacing (migration 200), L15330-15509 | rules extracted | Rules 15 to 17 |
| &nbsp;&nbsp;Counting-since cutoff + broader registration matching (migration 201), L15386-15457 | rules extracted | Rules 18, 20, 22; Flag 2 |
| &nbsp;&nbsp;The cutoff over-applied to the lead tables, a conflated Meta leads figure, and a shared-IP rate-limit bug, L15458-15509 | rules extracted | Rules 19, 21, 23; Traps |
| Usage tracking, session duration, time on page, visitor journeys (migration 165, v8.75.0), L15510-15559 | rules extracted | Rules 55, 56; Flag 9 |
