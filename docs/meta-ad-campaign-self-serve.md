# Meta Ad Campaign — Self-Serve Trial Signups (Aug 2026)

The campaign plan for the ~$500 / 30-day Meta (Facebook + Instagram) push
driving clubs to register themselves at **betterat.cricket/trial**. The
platform side (public signup, attribution, tracking, the lead-score report)
shipped in v8.72.0; this doc is the ads side: structure, creative, budget,
naming conventions the tracking depends on, and the launch runbook.

Ops dashboard: `/admin/super/meta-ads` (per-ad spend/CTR/cost-per-LPV plus the
new "Self-serve trial signups → lead score" panel). The panel groups signups
by `utm_campaign` / `utm_content`, so the naming rules in §4 are load-bearing,
not cosmetic.

## 1. What we learned from the last campaign

The July traffic campaign (`BC_AU_Traffic_ClubHistory_Jul2026`) taught us:

- Traffic-objective ads bought cheap landing-page views but conversion
  depended on a human follow-up. The Contact form was the only conversion
  event, and a form enquiry still needed us to onboard the club by hand.
- The club-history angle (decades of stats, "your 1975 premiership is in
  there") is the hook that got clicks. Keep it.
- Meta's own lead count needed manual +/- correction (the adjustment buttons
  exist because of this). Our own site-tracked attribution was the more
  trustworthy number, which is why signups now write their attribution into
  our own database at the moment of registration.

This campaign removes the human from the conversion: the click lands on
/trial and the club is live before we ever hear about it.

## 2. Objective and funnel

Run **one campaign** with the **Leads or Sales objective optimising for the
`CompleteRegistration` pixel event** (a finished self-serve registration).
Not Traffic: we now have a real conversion event both browser- and
server-side (Conversions API), so let Meta's delivery optimise for people
who finish, not people who click.

The tracked funnel, each step visible in Events Manager and each with a
server-side twin so ad blockers and iOS don't blind us:

| Step | Event | Fired when |
|---|---|---|
| 1 | `PageView` | any page load (existing global pixel) |
| 2 | `ViewContent` (self_serve_trial) | the /trial page renders |
| 3 | `Lead` (self_serve_trial) | a visitor picks their real club in step 1 of the wizard |
| 4 | `CompleteRegistration` | registration finishes; the club and trial exist |

If Meta won't optimise on `CompleteRegistration` at first (it wants ~10+
conversions a week before it settles), start the campaign optimising on
`Lead` and switch the ad set to `CompleteRegistration` once 15-20
registrations have accumulated.

## 3. Structure and budget ($500 over 30 days ≈ $16.50/day)

One campaign, two ad sets, three creatives each. Small budgets fragment fast,
so resist more ad sets than this.

**Campaign**: `BC_AU_SelfServe_Aug2026` (this exact string is the
`utm_campaign` too, §4).

- **Ad set A — Cricket interest, cold ($10/day)**. AU, age 24-60, interests:
  cricket, PlayHQ, community sport administration, plus stacked interests
  like Cricket Australia and local cricket associations. Placements:
  Facebook feed, Instagram feed and reels. This is the prospecting engine.
- **Ad set B — Warm retargeting ($6.50/day)**. Website visitors 180 days
  (the pixel has been live since the last campaign), engaged FB/IG page
  interactions 365 days, and video viewers of this campaign's own ads.
  Exclude converters (custom audience on `CompleteRegistration`). These
  people already know the brand; the ad's job is only "you can now do it
  yourself, no call needed".

Once ~50+ registrations exist, build a 1% lookalike on the
`CompleteRegistration` custom audience and graduate ad set A to it. That's
likely a next-campaign move at this budget.

## 4. UTM and naming conventions (load-bearing for tracking)

Every ad's destination URL must be:

```
https://betterat.cricket/trial?utm_source=facebook&utm_medium=paid_social&utm_campaign=BC_AU_SelfServe_Aug2026&utm_content=<creative_code>
```

- `utm_campaign` identical across the whole campaign, and it should match
  the campaign name in Ads Manager so the dashboard's spend figures line up
  with the signup report's grouping.
- `utm_content` unique per creative (`video_walkthrough_15s`,
  `static_history_hook`, `carousel_modules`, …). This is how the
  "signups → lead score" panel tells creatives apart, and it feeds the same
  first-touch store the Usage page already reads.
- `fbclid` is appended by Meta automatically and captured as the click id;
  don't add one.
- Instagram placements ride the same URL; `utm_source` stays `facebook`
  (the click id source detection still distinguishes actual IG shares).

## 5. Creative brief (three concepts per ad set)

All creative can be produced from real product screens; nothing mocked up.
The strongest screens to capture (a normal browser on the production site,
1920x1080, light or dark to taste):

1. A long-established club's public home page (e.g. `betterat.cricket/applecross`)
   showing the decades-deep season list.
2. A veteran player's profile: career runs, season-by-season table going
   back to the 1980s-90s.
3. Club records / leaderboard page (all-time records with names and years).
4. The new /trial page itself (hero + "No credit card · No sales call" pill).
5. BetterIQ opposition dossier and the BetterSelect board, for the
   "more than stats" frames.

**Concept 1 — "It already knows your club" (15s video or GIF, expected
winner).** Screen-record scrolling a real club's history: season list flying
past 2026 → 1975, cut to a player profile, cut to the records page. Text
overlay beats: "Your club's entire history" → "already in here" → "Free
trial. No credit card. 3 minutes." CTA: Sign Up. This is the proven hook
from the last campaign, now with a self-serve payoff.

**Concept 2 — "Still doing this by hand?" (static image or 2-frame).**
Split-frame: a messy spreadsheet vs the club records page. Primary text
speaks to the poor soul who maintains the spreadsheet: "Someone at your club
is still typing scorecards into a spreadsheet. It stopped being necessary
today." CTA: Sign Up.

**Concept 3 — "The whole club, one platform" (carousel, 5 cards).** One card
per module with its real screen: stats site, selection board, match-day
graphic, fees screen, opposition dossier. Last card: the /trial hero.
Carousels usually lose to video on cold traffic but are cheap to make from
the same screenshots and occasionally win retargeting.

Primary-text drafts (A/B the first line):
- "Every scorecard your club has ever filed with Cricket Australia, turned
  into a live website. Find your club, verify your email, and it builds
  itself. Free for 14 days, no credit card."
- "Your 3rd XI's 1994 season is in here. So is last Saturday. Register your
  club yourself in about 3 minutes."

## 6. KPI targets and kill/scale rules

Benchmarks from the July campaign plus AU paid-social norms. Check the
dashboard twice a week; act on the rules, not vibes.

| Metric | Target | Rule |
|---|---|---|
| Link CTR | > 1.0% | creative under 0.7% after $50 spend: pause it |
| CPC | < $1.50 | |
| /trial view → registration | 5-10% | under 3% with healthy CTR = landing-page problem, not ad problem |
| Cost per registration | $20-50 | a creative holding under $25/reg after 5+ regs: shift budget to it |
| Registrations (30 days) | 10-25 | 15 registrations at ~10% trial→paid ≈ 1-2 paying clubs ≈ $400-2000/yr ARR, before word-of-mouth |

Wizard drop-off shows up as `Lead` events (club picked) without
`CompleteRegistration` — if that gap is wide, the friction is inside the
wizard (likely the email OTP step) and it's a product fix, not an ads fix.

## 7. Launch runbook (in order)

Config, not code. The feature ships inert until these are done.

1. **Email provider first.** Set a real `email_provider` in the server
   `.env` (it defaults to `console`: OTP codes print to server logs and no
   mail sends, which dead-ends every real registrant). Finish the
   SPF/DKIM/DMARC DNS for the sending domain (still outstanding per
   CLAUDE.md) or codes land in spam. **Do not spend a dollar before a real
   end-to-end signup with a personal email works in production.**
2. Confirm Twenty CRM env is configured so `push_self_serve_registration`
   lands each signup as a Hot (100) Company + Lead + Opportunity.
3. Confirm Meta CAPI env (`META_DATASET_ID`, `META_CAPI_ACCESS_TOKEN`) is
   set so the server-side Lead / CompleteRegistration events flow; verify
   with `META_TEST_EVENT_CODE` in Events Manager's Test Events tab.
4. Deploy, run migration 160 (or let the lifespan mirror apply it), then
   flip **`self_serve_registration_enabled` ON** (Super Admin → General
   Settings). While the flag is off the /trial page is public but shows a
   "leave your details" Contact CTA instead of the signup button; flipping
   the flag swaps in the real self-serve wizard with no deploy. Also
   uncomment the `/trial` sitemap entry in `backend/app/routers/seo.py` at
   launch so the page gets indexed.
5. Register a real test club end-to-end in production (a small club we can
   archive after, or use the archive/restore flow). Confirm: the org exists
   with trials, the session lands in /admin, `signup_attribution` is
   populated from a UTM-tagged visit, the events appear in Events Manager,
   and the club shows in the ad-signups panel.
6. Build the two ad sets and six ads in Ads Manager with §4's URLs.
   Schedule, don't boost.
7. Days 1-3: watch delivery daily (a $500 account can burn a third of its
   budget on a bad creative before weekly checks catch it). Then twice
   weekly per §6.

## 8. The Meta Ads MCP server (the email that prompted this)

Meta opened their **ads MCP server** to developers with their own app: the
BetterCricket app (App ID 2045189966179927, Business ID 1008763395320306)
can now drive campaign creation, optimisation and insights through natural
language via MCP. Worth adopting, but deliberately not part of this build:

- Nothing about it changes what was built here. Attribution, the /trial
  funnel and the lead-score report work regardless of how the campaign is
  created.
- The practical near-term use is plugging the MCP server into Claude (or
  this codebase's tooling) to create/adjust the campaign of §3
  conversationally, and later to automate §6's kill/scale rules instead of
  the current read-only `meta_ads.py` recommendation engine.
- It needs the app's credentials wired to whichever client speaks MCP; no
  `meta_app_id` / `meta_app_secret` settings exist in this codebase today.
  Add them only when something here actually consumes the MCP server.
