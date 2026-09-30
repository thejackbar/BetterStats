# Guide: Marketing funnel, Meta ads reporting, webinar registration and self-serve attribution

**Read this before**:
- Touching `services/meta_ads.py`, `routers/meta_ads.py`, `meta_capi.py`, `SuperMetaAds.jsx` (Meta Ads HQ), campaign spend, cost per result, funnels or "counting since".
- Touching `/trial`, `/demo`, `Trial.jsx`, `SelfServeTrialModal`, `routers/public_self_serve.py`, `lib/visitor.js`, `metaPixel`, `ClubCTABar`, `lib/marketingPaths.js`, `lib/clubPath.js`.
- Touching the webinar: `services/webinar.py`, `webinar_ddl.py`, `streamyard.py`, `data/webinar.js`, `webinar_registrations`, reminders, `.ics`.
- Touching `wizard_club_lists.py`, Wizard Clubs page, `club_searched` / `club_prepared` beacons.
- Touching `usage_events`, `routers/usage.py`, `usePageView.js`, session duration, `page_exit`, visitor journeys.
- Symptoms: pixel event on the wrong page or twice; inflated cost per signup; "Club selected" above "Started registering"; one visitor split over several club rows; an uncounted registration; a disabled button with no reason.

**Archive** (verbatim, do not load whole): `docs/dev-notes/archive/marketing-funnel-ads-and-webinar.md`. Grep hints: `ClubCTABar`, `ONE PIXEL EVENT`, `ad_daily`, `CANNOT FIRE ON STREAMYARD`, `push_registration`, `Rediscover`, `search beacon`, `Wizard Clubs`, `public_self_serve`, `counting since`, `CAMPAIGN_PLANS`, `time_on_page_ms`.

**Related guides**: club directory / BetterComms (Rediscover, segments), billing and Stripe (trial checkout), CRM and sales workspace (reads `signup_attribution`), instructional videos (top-level slug lists).

## Standing rules

**Two products, one pixel event (v9.72.0, v9.72.1)**
1. `/trial` and `/demo` fire `CompleteRegistration` at dataset 1317878090534903; only `content_category` separates them: `self_serve_trial` (value 399 AUD) and `webinar` (no value). Never add a combined registrations total or one campaign-wide funnel.
2. Spend is split per stream from per-ad rows (`stream_totals`, `build_streams`), exact not apportioned. `campaign.cost_per_lead` now means the trial's own.
3. `stream_for_ad`: `AD_DESTINATIONS` first, then the ad NAME (`Ad_Webinar_*`). Never classify from the AD SET name.
4. `get_registration_count` reads `organisations` (trial only). The bug was the divisor, not the count; do not change the count.
5. `meta_capi.send_complete_registration_event` defaults are the trial's (value 399). Other callers (`public_webinar.py`) must name their own event.
6. Each stream also carries a figure since the last deliberate change (`stream_totals_since`, `level='ad_daily'`, `_last_change_date()`). Label all-time figures as all time.
7. Record deliberate changes in `CAMPAIGN_ANNOTATIONS` (`{date, label, detail}`); pacing never crosses one.
8. Spend is settled, results are not. Pacing excludes only today; the 7-day attribution window applies to conversion insights only, so a since-cost inside it is a provisional ceiling: never alert off it.
9. A partial window withholds the cost and says why (`ad_daily` kept `CAMPAIGN_LENGTH_DAYS + 5`; short spend understates cost).
10. `get_registration_count_since` shares `_attribution_matches_campaign` with the lifetime count; the lifetime count is never windowed.
11. A signup with no timestamp (orgs have no `created_at`; use earliest `self_serve_idempotency_keys`) is `undated_trial_results`, never guessed. The manual leads adjustment is lifetime only.
12. `CAMPAIGN_UTM_*` is a SET per campaign. Unrecognised utm tags are dropped, so a missing entry reads as "new ads produced nothing". After any rename in `meta_ads.py` sweep every `ImportFrom` and `meta_ads.<attr>` in `app/`: a lazy import inside a function survives `py_compile` and `vite build`.
13. Untagged webinar registrations are reported beside cost per result, never absorbed (cost reads high, the safe direction).
14. Recharts drops a `ReferenceLine` wrapped in a Fragment (`chartMarkers()` returns an array); `ReferenceArea` draws a `<path>`.

**Meta Ads HQ reporting (migrations 200, 201)**
15. Funnel has a "Club selected" stage (`get_club_selected_count`: distinct Meta visitors who fired `club_prepared`), our count not Meta's.
16. `meta_ad_snapshots.updated_at` must be set on INSERT and `DO UPDATE` in `upsert_snapshot`.
17. Budget and length are per campaign: add to `CAMPAIGN_PLANS`; `_campaign_plan()` falls back to `CAMPAIGN_BUDGET_AUD` / `CAMPAIGN_LENGTH_DAYS`.
18. "Counting since" (`platform_settings.meta_ads_counting_since`) resets on-site funnel STAT counts and Meta insights (`_date_range_params()`), via `_SINCE_LOWER_BOUND` (only narrows). It NEVER windows the "Free trial registrations" KPI. Meta numbers come from stored snapshots: a change needs `run_snapshot()`.
19. Clubs selected / searched TABLES are NOT windowed by the cutoff (follow-up list); default 365 days, max 730.
20. The cutoff is seeded once (marker `meta_ads_counting_since_seeded`), so clearing it survives restarts.
21. Meta `campaign["leads"]` is Lead actions only (`_LEAD_ACTION_TYPES`); never sum `complete_registration` in.
22. `_attribution_matches_campaign` accepts `utm_content`, then `utm_campaign`, then a plain fb/ig/meta `utm_source` or `click_source`. Null attribution: use the KPI manual +/- with a note.
23. `/track-step` rate limit is keyed by `visitor_id` (IP only as fallback): IP keying starved beacons behind Facebook in-app proxies and CGNAT. Only `/search` needs an IP cap.

**Search beacons and Wizard Clubs (v9.23.0, v9.23.1, migration 251)**
24. A `club_searched` top match is what the engine ranked, not what the person wanted. The Wizard Clubs page collapses consecutive queries into a run (`_same_typing_run`, prefix either way, `_SEARCH_RUN_GAP` 30 min) and resolves to the clicked club, else the club matched by the LONGEST query. This is on that page ONLY, per direct instruction: `meta_ads.get_searched_clubs` stays raw. The resolver never writes back.
25. `result_count` on the beacon is NULL for older ones; regex-match before `::int`. `_query_identifies`: club name must START with the query, 4+ chars. `_query_is_ambiguous` demotes a query prefixing several surfaced clubs. Unresolved searches report as `search:<query>`, never a club; `_improve_guesses` upgrades only on exactly one confident club, drops on two. Query rows are never directory-matched or exported.
27. `merged_wizard_clubs` folds selected and searched on stripped lowercase name (`both`). Directory match: CA guid first (`club_prepared` captures it), name second.
28. "Emailed" is DERIVED (sent campaign audience `list_id`, `comms_recipients`, `comms_contacts.marketing_club_id`, `status='sent'`, lists this page made). Compare `list_id` as TEXT. `wizard_club_lists.list_id` has no FK on purpose.
29. Export follows Directory rules: never `excluded` or unsubscribed, linked to the directory club, existing address reused and not un-suppressed. Generic mailbox gets `first_name = "Committee Members"`. Browser sends club KEYS never emails.

**Self-serve public trial (v8.72.0, migration 161)**
30. `public_self_serve.py` re-registers internal handlers via `add_api_route`; hand-wraps status, verify-email, prepare, submit. The router 404s while `self_serve_registration_enabled` is off; `/trial` redirects to `/`.
31. Guardrails: per-IP `rate_limit.enforce`, honeypot `website` (non-empty gives fake success), min fill time (`form_started_at` under 4s gives 422), generic provider errors. OTP email is the gate; no CAPTCHA.
32. Submit mints the session cookie, returns `redirect: "/admin"`, client sets `bs_pending_fresh_login`. `organisations.signup_source` (`self_serve_ad` / `self_serve_organic`, NULL non-public) and `signup_attribution` JSONB are written best-effort AFTER commit. New tags must be added to `_ATTRIBUTION_KEYS` (`utm_term` was dropped until v9.71.1).
33. `prepare` fires a server Lead; `submit` fires CompleteRegistration (browser plus CAPI, one event id), GA4 `sign_up`. Modal prop is `publicMode`, not `public`.
34. `GET /club-admin/meta-ads/ad-signups` reads the CACHED `marketing_clubs.engagement_score`, never a live score per row.
35. Launch is config: flag on, real `email_provider` (default `console` never sends OTP), SPF/DKIM/DMARC; rate limiter is in-memory.

**Club page call to action (v9.91.0, v9.92.1)**
36. The bar is for PROSPECTS only: a session from a Meta click (utm_source meta/facebook/fb/instagram/ig, medium paid_social, or fbclid/igshid) or that passed `/trial`. Never a club's members, never signed-in users. Dismiss minimises to a pill. The club shown is already registered, so copy sells the visitor's OWN club.
37. Read campaign params from the session (`visitor.rememberLandingParams()` in `main.jsx`, `bc:landingParams`), not the address bar. The bar must not draw on `/trial` or `/demo`. `lib/clubPath.publicClubSlug` is the one "is a club page" rule. CompleteRegistration fires only on `status === 'completed'`.
38. (merged into 37)
39. Wording follows the ad ("Check out your club", "Free · about 3 minutes · no card"); `/trial` placeholder names no real club.

**Webinar registration (migration 296 on)**
40. A pixel cannot fire on a third-party domain: register on our page, RENDER success (never redirect; it races the beacon). Order: persist, then fire; never on load, click or validation failure.
41. Fire only when the server says `created` (fold on `(event_key, lower(email))`). A resubmission claims nothing; a broken backend still hands over the link and fires nothing. Campaign columns, phone and name halves are COALESCEd (fill, never overwrite).
42. `services/webinar.EVENT` and mirror `frontend/src/data/webinar.js` drive the page (suite asserts they agree). Past switch is the event's END; server `is_past` beats the local clock. `/demo` is resolved per request (`webinar.page_meta`, `webinarState`), not in `MARKETING_PAGES`.
43. Recording link is a setting (`webinar_recording_url`, url-validated, `''` clears). `.ics` is an endpoint (CRLF, UTC). The StreamYard link is NOT in the JS bundle (`GET /public/webinar`; grep `frontend/dist`).
44. Phone is OPTIONAL (8 to 15 digits when typed), stored as typed, not `admin_identity.mobile_valid`.
45. First and last name are separate fields (migration 301). `name` stays authoritative; halves stored only when BOTH given (`resolve_name`); a surname is never invented. `streamyard.resolve_push_name` is the one rule; stubs must CALL it.
46. Webinar registrations are not `club_onboarding_requests` and push no Hot lead to any CRM (per direct instruction).
47. `demo` and `trial` must be in all FOUR top-level-slug lists (`og_preview.RESERVED_ROOT_SEGMENTS`, `FaviconManager.RESERVED_ROOTS`, `SponsorFooter.RESERVED_ROOT_SEGMENTS`, `lib/marketingPaths.MARKETING_PATHS`), but NOT in the `MARKETING_PATHS` behaviours they do not want: `OWN_NAV_PATHS` / `rendersOwnMarketingNav` suppresses the club Navbar alone (`MARKETING_PATHS` also forces dark theme and shows `ClubCTABar`).
48. Reminder (migration 299): `send_reminders` window is `REMINDER_LEAD_HOURS` (3) before start to end, hourly via `webinar_upkeep`. Registrants inside the window are not reminded. `reminder_sent_at` is the CLAIM; a refusal hands it back with `reminder_error`. `POST /club-admin/super/webinar-reminders` refuses outside the window.
49. StreamYard push (migration 300): `push_registration` posts to `oa-api.streamyard.com/api/public/webinars/{id}/registrations`. Field ids are FETCHED (`_field_map`, 10 min cache), never hardcoded; broadcast id parsed from `EVENT.watch_url`. Idempotent on email, no overwrite; pushed rows skip before any request. A mononym is skipped with a recorded reason (blank surname is a 400). Best-effort, own session, never raises. `sync_streamyard` (hourly catch-up, `POST /club-admin/super/webinar-streamyard-sync`) reports `reasons`; "NOT SENT" shows the reason on the row.
50. Only the name is editable (`PATCH /super/webinar-registrations/{id}`); email is the fold and idempotency key.
51. Removing StreamYard's second form is their registration toggle, not code (CORS refuses our origin; registration binds to the creating session; reminder `?token=` is not the registration id). Turning it off loses their registrant list and attendee report.

**Club Directory Rediscover (misfiled here, see Flags)**
52. A disabled button must say why: one reason string drives disable, tooltip and a note. Gate on the `paused` BOOLEAN (operator Stop), not `state == 'paused'` (runner break).
53. Stop means the UNATTENDED crawler. `discover_clubs(should_stop=...)` defaults to `is_crawl_paused`; only `rediscover_all` passes its own cancel (`POST /rediscover/stop`, cleared at run start). A halted run reports `stopped: True`; `{"skipped": "stopped"}` is not a finished run. Server reports `stale` (12 h) so screen and POST agree.
54. `enrich_associations` refreshes stale ones (`marketing_clubs.associations_fetched_at`, migration 298, stamped only on SUCCESS, backfilled from `COALESCE(last_crawled_at, first_seen_at)`), never-fetched first. `frontier_remaining` stays never-fetched only. An empty refresh clears `association_name`/`association_guid`.

**Usage tracking (migration 165)**
55. Dwell is a `page_exit` event (`usePageView.js`: `sendBeacon` on `pagehide`, `visibilitychange` hidden, route change) writing `usage_events.time_on_page_ms` via `POST /usage/event/exit`, clamped 24 h. Sessions are computed on read: `page_view`s grouped on a gap of 30 min or more; duration is first to last PLUS the final page's dwell (else bounces read 0).
56. `GET /club-admin/usage/journey?visitor_id=` is the only per-visitor view. `comms._apply_utm` checks each UTM key independently; `usePageView` sends the CURRENT URL's UTM (`visitor.getCurrentUtm()`) over first-touch.

## Traps and failure signatures

- Wrong webinar state on a bad-clock device: server `is_past` must win. Recording advertised pre-event: title/`og:title` were hardcoded (crawlers skip `usePageMeta`).
- Two logo lockups on `/demo` or `/trial`: four-lists trap (rule 47). Inflated cost per signup: divisor included the other stream (rule 2). Chart marker missing, no error: Fragment (rule 14).
- Phantom club rows ("Warn" as "Warners Bay"): rule 24. "More selected than searched": rules 19, 23. "Last updated" stuck: rule 16. StreamYard "0 pushed, 2 skipped": mononyms, not a fault.
- Harness: `addInitScript` cannot stub `gtag` (read `window.dataLayer`); `networkidle` never settles; `click({force:true})` on a disabled button hangs; CSS-`uppercase` reads transformed; `.every()` on an empty array is vacuous.

## How to verify a change here

- Backend (real Postgres, shipped route bodies): `backend/verification/verify_meta_ads_streams.py` (control with feature absent REPORTS missing parts; window and guards neutered: since-spend reads lifetime, a partial window prints a cost), `verify_webinar.py` (DDL three times, mirror agreement, resubmission and bot guards, reminder edges, name halves), `verify_streamyard_skip_reporting.py`.
- Browser: `frontend/verification/verify_meta_ads_streams_browser.mjs`, `verify_webinar_browser.mjs`, `verify_club_cta_browser.mjs`. Meta Events Manager Test Events is NOT covered.
- Never call live StreamYard in a suite (no public DELETE); stub `push_registration`. Earlier probes left four test registrations (`bc-it-a@` and similar) to delete by hand.
- Control runs must REPORT, not crash: `.get`, presence-safe helpers (`textOf()`, `seen()`, `reachedSuccess()`), gate whole blocks. Diff PASS lists of run and control (`comm -12`) to find checks that cannot fail.

## Operator commands and scripts

- No standing scripts here (engagement scripts belong to the CRM guide). After changing `CAMPAIGN_UTM_*` or `AD_DESTINATIONS`, press Refresh now (`run_snapshot`).
- Account-side (not code): verify the domain in Business Manager; `CompleteRegistration` in Aggregated Event Measurement priority; ad `conversion_domain`; StreamYard registration toggle; `webinar_recording_url` after the event; SPF/DKIM/DMARC and a real `email_provider`; `self_serve_registration_enabled` at launch.

## Open follow-ups

- Meta's own `content_category` breakdown is unread, so Meta-reported conversions cannot be split by product.
- `CAMPAIGN_PLANS` is one budget per campaign, not per stream.
- No attended/no-show record; a second webinar means editing both `EVENT` copies (`event_key` exists).
- Untested: StreamYard "Already registered? Join here" for pushed registrants; pushes once registration is off.
- Full webinar gate (withhold `watch_url` until register POST) not built: conflicts with "a broken backend still hands over the link".

## Flags: conflicting, superseded or possibly obsolete guidance

- [FLAG-MKT-1] Archive says `CAMPAIGN_UTM_NAMES` became a set | code now `CAMPAIGN_UTM_CAMPAIGNS` (`meta_ads.py:190`, used by `sales_workspace.py:718`) | ONE CAMPAIGN, TWO PRODUCTS (L789-994) | keep rule, use new name.
- [FLAG-MKT-2] Archive names `_META_VISITOR_SUBQUERY` (and `_PLAIN`) | code has `_META_VISITOR_EXISTS = _meta_visitor_exists(_SINCE_LOWER_BOUND)` | L15458-15509 | verify names.
- [FLAG-MKT-3] Phone "REQUIRED" then optional; StreamYard link "in the JS bundle" then removed | both reversed in v9.71.3; `EVENT.watch_url` is server side (`webinar.py:73`) | webinar section (L1827-2032) | rules 43, 44 are current.
- [FLAG-MKT-5] Two sub-notes carry v9.71.5 (298 gate, 299 reminder), and 300 says v9.71.6 | version labels collided at merge (archive notes renumbering) | L2179-2582 | trust migration numbers 296, 298, 299, 300, 301, not versions.
- [FLAG-MKT-6] v9.71.4, migration 298 gate and association refresh are Club Directory rules nested under the webinar section | not webinar code | L2117-2281 | move to the club directory guide; kept here as rules 52 to 54.
- [FLAG-MKT-7] Wizard Clubs v9.23.0 searched table versus v9.23.1 | later changes it (`resolved_searched_clubs`) | L7437-7573 | later wins, read both.
- [FLAG-MKT-8] Self-serve says Twenty must be configured for the Hot-100 Lead | Twenty retired in v9.71.0 (CRM guide) | L15249-15329 | verify `push_self_serve_registration` before relying.
- [FLAG-MKT-9] Suites cited for wizard clubs, search beacon, self-serve, usage | none found in `backend/verification` or `frontend/verification` | L7437-7573, L15249-15559 | verify or retire.
- [FLAG-MKT-10] Webinar date (Mon 21 Sep 2026) is a hardcoded constant | today is 30 Sep 2026, so the page should be post-event | webinar section | verify `EVENT` and `webinar_recording_url`.

## Section coverage

| Original section (heading, original CLAUDE.md line range) | Disposition | Where captured |
|---|---|---|
| The club page a prospect searched their way to asks them to start (v9.91.0), L399-453 | rules extracted | Rules 36 to 39 |
| ONE CAMPAIGN, TWO PRODUCTS, ONE PIXEL EVENT (v9.72.0), L789-994 | rules extracted | Rules 1 to 5, 12 to 14; Flag 1 |
| sub: The trial's cost was still a lifetime average (v9.72.1), L907-994 | rules extracted | Rules 6 to 11 |
| THE CONVERSION CANNOT FIRE ON STREAMYARD'S DOMAIN (migration 296, v9.71.1), L1827-2582 | rules extracted | Rules 40 to 47; Flags 3, 4, 10 |
| sub: What a review of the live page found (v9.71.3), L2032-2116 | rules extracted | Rules 42 to 44, 47; Traps |
| sub: A disabled button that does not say why reads as broken (v9.71.4), L2117-2178 | rules extracted (misfiled, Club Directory) | Rule 52; Flag 6 |
| sub: And then the gate itself was wrong (migration 298, v9.71.5), L2179-2280 | rules extracted (misfiled, Club Directory) | Rules 53, 54; Flags 5, 6 |
| sub: One form, two lists: pushing the registrant into StreamYard (migration 300, v9.71.6), L2281-2382 | rules extracted | Rules 49, 51; Verify |
| sub: A skip that does not say why reads as a broken button (v9.73.2), L2383-2435 | rules extracted | Rules 49, 50 |
| sub: The form asked for one name where theirs needs two (migration 301, v9.73.3), L2436-2498 | rules extracted | Rule 45 |
| sub: The second form is StreamYard's, and the reminder that replaces it (migration 299, v9.71.5), L2499-2582 | rules extracted | Rules 48, 51; Flag 5 |
| A search beacon's top match is NOT the club they wanted (v9.23.1), L7437-7506 | rules extracted | Rules 24, 25; Flag 7 |
| Clubs Searched or Selected in the Wizard (migration 251, v9.23.0), L7507-7573 | rules extracted | Rules 27 to 29; Flag 7 |
| Public self-serve trial signup + ad attribution (v8.72.0), L15249-15329 | rules extracted | Rules 30 to 35; Flags 8, 9 |
| Meta Ads HQ, Club Selected stage, stale "last updated", undercounted registrations, per-campaign pacing (migration 200), L15330-15509 | rules extracted | Rules 15 to 17 |
| sub: Counting-since cutoff + broader registration matching (migration 201), L15386-15457 | rules extracted | Rules 18, 20, 22; Flag 2 |
| sub: The cutoff over-applied to the lead tables, conflated Meta "leads", shared-IP rate-limit bug, L15458-15509 | rules extracted | Rules 19, 21, 23 |
| Usage tracking, session duration, time on page, visitor journeys (migration 165, v8.75.0), L15510-15559 | rules extracted | Rules 55, 56 |
