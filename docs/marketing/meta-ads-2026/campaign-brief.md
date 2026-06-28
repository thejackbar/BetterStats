# BetterCricket — Meta Ads Campaign Kit (2026)

Audience: Australian cricket clubs and the people who follow them.
Goal: website visits, onboarding-form fills, and page follows.
Destination of record: `https://betterat.cricket/contact` (the live onboarding form).

This kit is built from the real product, pricing and brand in the repo, so the
copy and numbers are accurate. Run any edits through the `humanizer` skill before
they ship (the voice rules are in `CLAUDE.md`).

---

## 1. How the click is tracked (already wired, no code change)

The site already captures first-touch attribution in `frontend/src/lib/visitor.js`:
it reads `utm_source`, `utm_medium`, `utm_campaign`, `utm_content` and the
`fbclid` Meta appends, stores them in `localStorage` on the first visit, and the
Contact form posts a `visitorId` with every enquiry. So a lead in the super-admin
Usage page joins back to the exact Facebook campaign and ad that produced it.

What this means for setup:
- Put the UTM string in the **URL parameters** field of each ad (not baked into
  the link field), so the destination link and the tracking stay tidy.
- `utm_medium` should be `paid_social` everywhere so paid traffic separates from
  organic and from the club-outreach emails (which use `utm_id`, a different
  system).

### The one UTM template to paste (dynamic — set once, correct per ad)

Meta fills these macros automatically per impression:

```
utm_source={{site_source_name}}&utm_medium=paid_social&utm_campaign={{campaign.name}}&utm_content={{ad.name}}
```

- `{{site_source_name}}` resolves to `facebook` / `instagram` / `messenger` /
  `an` (Audience Network), which is exactly what `visitor.js` reads as the source.
- `{{campaign.name}}` and `{{ad.name}}` flow straight into `utm_campaign` and
  `utm_content`, so name campaigns and ads in lowercase with underscores (see the
  naming convention below) and the analytics stay clean with zero manual tagging.

### Static examples (for QA, or if you prefer fixed strings)

```
# Campaign A — clubs, traffic to the form
https://betterat.cricket/contact?utm_source=facebook&utm_medium=paid_social&utm_campaign=clubs_au_acq_2026&utm_content=history_hook_1x1

# Campaign C — players/fans, traffic to a live club page
https://betterat.cricket/applecross?utm_source=instagram&utm_medium=paid_social&utm_campaign=fans_au_aware_2026&utm_content=player_card_9x16
```

`/applecross` is a real, live club site, which is a stronger "this is what you
get" landing page for players than the marketing pages.

### Naming convention (because names become UTM values)

- Campaign: `{audience}_{geo}_{intent}_{year}`
  e.g. `clubs_au_acq_2026`, `fans_au_aware_2026`, `clubs_au_leadform_2026`
- Ad set: `{audience-detail}` e.g. `committee_admins`, `parents_juniors`, `lookalike_1pct`
- Ad: `{angle}_{ratio}` e.g. `history_hook_1x1`, `oneplatform_4x5`, `statcard_9x16`

---

## 2. Campaign structure

Four campaigns, because your three objectives and three audiences do not belong
in one budget. Run A first, add the others as budget allows.

| # | Campaign | Objective | Audience | Lands on |
|---|----------|-----------|----------|----------|
| **A** | `clubs_au_acq_2026` | Traffic (or Sales/Leads w/ Pixel) | Club decision-makers | `/contact` |
| **B** | `clubs_au_leadform_2026` | Lead generation (Instant Form) | Club decision-makers | In-Facebook form |
| **C** | `fans_au_aware_2026` | Traffic / Engagement | Players, parents, fans | live club page + Page |
| **D** | `bettercricket_follows_2026` | Page Likes / follows | Players, parents, fans | the Page itself |

A and B chase the buyer. C and D build the audience and the demand that makes A
and B cheaper over time (a player who follows the page is the person who nudges
their committee).

Start budget guide (AUD/day): A $20–30, B $15–20, C $10–15, D $5–10. Give each ad
set 3–4 days before judging it; cricket-club admins are a small, specific
audience, so let the learning phase finish.

---

## 3. Targeting (all of Australia)

### Campaign A & B — club decision-makers

Location: Australia. Age 28–65. All genders.

Detailed targeting (narrow with "must also match"):
- **Layer 1, role/interest in cricket admin**: Cricket Australia, PlayHQ,
  MyCricket, Cricket Victoria / NSW / WA / Queensland / SA / Tasmania,
  club cricket, Kookaburra, community sport.
- **Layer 2, the volunteer/committee signal**: "Volunteering", "Club treasurer",
  "Sports club", "Nonprofit organisation management", Facebook Page admins
  (behaviour), small-business admins.
- **Custom audience**: upload any club-contact list you have (committee emails
  from associations, expo leads). This is your warmest pool.
- **Lookalike (after ~50 leads or from a contact list)**: 1% AU lookalike of
  onboarding enquiries or your contact list. This usually becomes the best ad set.

Exclude: existing customers (upload the customer email list as an exclusion) so
you are not paying to reach Applecross, High Wycombe, Murdoch and Portland again.

### Campaign C & D — players, parents, fans

Location: Australia. Age 16–55. All genders.
- Interests: cricket, local cricket club, Big Bash League, Sheffield Shield,
  PlayHQ, Cricket Australia, plus parenting + youth sport for the junior-parent
  pocket.
- Engagement custom audiences: people who engaged with your Page or Instagram
  (retarget into D for follows).

---

## 4. Ad copy

Voice: plain Australian cricket-club. Short sentences. No em dashes, no hype
words. Every figure below is real: Core from $399/yr, full history imported at no
extra cost, history confirmed back to 1975 for some clubs, proven at Applecross.

Meta primary-text shows ~125 characters before "See more", so the hook lives in
the first line. Headlines stay under ~40 characters where possible.

### Campaign A — clubs → `/contact`

**Ad A1 — History hook** (pair with creative `01-clubs-square-history`)
> Primary text:
> Your club's full history, online and updated automatically.
>
> BetterCricket pulls every player, every match and decades of records into one
> club website, then keeps it current after every game. There are no
> spreadsheets to hand over and no data entry.
>
> Applecross Cricket Club moved their whole history across in under an hour. We
> can build you a free demo on your own club's data.
>
> Tell us about your club and we'll get started. 🏏
>
> Headline: Your club's history, finally online
> Description: Full history imported, free
> CTA button: Learn More

**Ad A2 — One platform / cost** (pair with `02-clubs-portrait-oneplatform`)
> Primary text:
> Most clubs run the season on a few spreadsheets, a website builder, Canva,
> Mailchimp and a pile of group chats.
>
> BetterCricket does the lot in one place, fed by your match data: stats, a
> public club website, team selection, social posts, fees, member email and
> opposition analysis.
>
> From $399 a year for the Core, with your full history imported at no extra cost.
>
> Headline: Run your whole club from one place
> Description: From $399/yr. Demo on your data
> CTA button: Learn More

**Ad A3 — Legacy / emotion**
> Primary text:
> Every catch, every fifty, every five-for your club has ever recorded, kept
> forever and online.
>
> BetterCricket turns your history into player profiles your members actually
> want to visit, with career stats going back decades. We build a free demo in
> your colours, with your real players in it.
>
> Headline: Decades of stats, imported for you
> Description: Built by club cricketers
> CTA button: Learn More

**Ad A4 — Testimonial (social proof)**
> Primary text:
> "At last we have a complete stats package that lets us view the club's entire
> history across every statistic imaginable. It's made pretty much every
> spreadsheet we had redundant, and we had a lot."
> — Tristram Fletcher, Secretary, Applecross Cricket Club
>
> See what BetterCricket would look like on your club's data.
>
> Headline: The end of the club spreadsheet
> Description: Free demo on your data
> CTA button: Learn More

### Campaign B — clubs → Instant Lead Form

Meta's native form fills better on mobile, but the data stays in Meta, so connect
it to your inbox (forward leads to `cricket@bettersports.com.au`) and reply fast.

> Form intro headline: See BetterCricket on your club's data
> Form description: Answer a few quick questions and we'll build a free demo with
> your real players, usually back to you the same day.
>
> Questions:
> - Club name (short answer)
> - Your role at the club (short answer)
> - Best email (auto-fill)
> - Phone (auto-fill, optional)
> - When are you looking to start? (multiple choice: As soon as possible /
>   Before next season / Just exploring for now)
>
> Completion screen: Thanks, we've got it. Want a head start? See a live club
> site at betterat.cricket.
> Button → `https://betterat.cricket/?utm_source=facebook&utm_medium=paid_social&utm_campaign=clubs_au_leadform_2026&utm_content=leadform_thankyou`

Primary text for the lead-form ad reuses A1 or A2, ending on "Answer a few quick
questions for a free demo."

### Campaign C — players / parents / fans → live club page

**Ad C1 — Player career** (pair with `03-players-story-statcard`)
> Primary text:
> Want to see your cricket stats properly?
>
> BetterCricket gives every player a profile with career runs, wickets,
> milestones and a share card for socials, with history going back decades. Ask
> your club to get on it.
>
> Headline: Your cricket career, on one page
> Description: See a real club site
> CTA button: Learn More

**Ad C2 — Parents of juniors**
> Primary text:
> Following a junior's season? BetterCricket keeps every game, every milestone
> and a proper profile for your young cricketer, all in one place your club can
> share.
>
> Headline: Follow every run they score
> CTA button: Learn More

### Campaign D — Page Likes / follows

> Primary text:
> Club cricket stats, done properly. Player profiles, club records, season
> yearbooks and match-day graphics, all built from your club's own data.
>
> Follow along for stat cards, club features and the odd milestone worth
> celebrating. 🏏
>
> CTA button: Like Page / Follow

---

## 5. Creative assets

All creative is in `./creative/`, in the exact brand palette: green `#16C784` to
blue `#3B82F6` gradient, navy `#0A0D14`, amber `#F5B324`, violet `#A855F7`. Two
families to A/B test against each other.

### Family 1 — Launch-poster style (primary, recommended)

This is the same visual language as the in-app "[Club] is now on BetterCricket"
announcement poster (`frontend/src/social/launch-templates.jsx`): Anton display
headline, confetti, halftone texture, a recreated club dashboard, a featured
player, top batters/bowlers, the "Powered by the Better modules" band and the
white footer CTA bar. The only change from the announcement is the message: these
ads recruit clubs not yet signed up ("Big news for your club, get it all on
BetterCricket, book a free demo") rather than announcing a club already on it.

| File | Ratio | Use |
|------|-------|-----|
| `04-clubs-launch-poster-1x1` | 1:1 (1080×1080) | Feed, Campaign A |
| `05-clubs-launch-poster-4x5` | 4:5 (1080×1350) | Feed (more height, adds price + testimonial), Campaign A |
| `06-clubs-launch-poster-9x16` | 9:16 (1080×1920) | Stories / Reels, Campaign A & C |

Each has an editable `.html` source beside the `.png`. Built as HTML so the
dashboard, featured player, top performers, club name, logo and colours are all
swappable. To re-export: render the `.html` with the headless-Chromium command
used here (loads Google Fonts, screenshot slightly taller, crop to the target
size).

**Generic vs real-club**: the poster currently shows an aspirational "Your Cricket
Club" mock so any prospect sees themselves in it. A real-club render (e.g.
Applecross's actual stats, players and crest) is a stronger proof point and is a
near drop-in swap of the panel data. Worth running both, the generic for broad
reach, the real club for credibility.

### Family 2 — Minimalist concepts

Cleaner, type-led cards. Lighter to read at small sizes, good as the A/B
challenger to the poster style.

| File | Ratio | Use |
|------|-------|-----|
| `01-clubs-square-history.svg` | 1:1 (1080×1080) | Feed, Campaign A |
| `02-clubs-portrait-oneplatform.svg` | 4:5 (1080×1350) | Feed, Campaign A |
| `03-players-story-statcard.svg` | 9:16 (1080×1920) | Stories / Reels, Campaign C & D |

To export any SVG to PNG, "Save as PNG" or use the headless-Chromium command used
for the previews here.

### Use the real screenshots too

Meta rewards creative variety, so run the made graphics alongside real product
shots. These exist in `frontend/public/marketing/`:
- `player-profile.jpg`, `leaderboard.jpg`, `yearbook.jpg` — the "this is what you
  get" proof, strongest for Campaign A and C.
- `feature-cards.jpg`, `showcase-scorecard.jpg`, `feature-opposition.jpg` — good
  for variety and for BetterIQ/socials angles.
- `applecross-cc.webp` — real club branding, good for the testimonial ad.

A short **screen-recording** of scrolling a live club site (e.g. the Applecross
profile and leaderboard) tends to be the cheapest, highest-engagement format on
Meta. Worth shooting one 10–15 second video.

### Creative rules that keep cost down
- Keep text under ~20% of the image area.
- The first 3 seconds of any video must show a real stat or profile, not a logo.
- One clear idea per creative. The headline and the image should say the same thing.

---

## 6. SEO / AEO tie-in (so the ad spend compounds)

The ad sends people to pages that are already built to be found and quoted. Keep
the campaign and the organic surfaces saying the same things so they reinforce.

- **`/contact` is indexable and has its own meta** (`usePageMeta` in
  `Contact.jsx`): title "Contact — Request Access for Your Cricket Club", which
  matches the ad intent. Good as-is.
- **AEO via `frontend/public/llms.txt`**: this file already tells AI assistants
  exactly who BetterCricket is, who it is for and what it costs. When someone asks
  ChatGPT or Gemini "best stats platform for an Australian cricket club", this is
  the source that answers. Keep the ad's promises (full history import, $399 Core,
  one platform) identical to the llms.txt wording so paid and AI-answer messaging
  match. It is current, no edit needed for this campaign.
- **Blog as the retargeting destination**: the posts in `frontend/src/data/blog.js`
  (PlayHQ migration, why a stats page, season yearbook, merge duplicate players)
  are ideal mid-funnel landing pages. Run a light retargeting ad to people who
  visited `/contact` but did not submit, pointing at the PlayHQ-migration post,
  then back to the form. Each blog post already has its own social-share card
  (`og_preview.py`), so these links preview well when shared.
- **Branded search safety net**: expect a lift in people Googling "BetterCricket"
  after seeing the ad. The homepage, sitemap and robots already allow indexing, so
  that branded search resolves to the real site. If budget allows, a small Google
  branded-search campaign catches that intent cheaply.
- **Consistent claims**: the three load-bearing facts (history imported free, from
  $399/yr, all in one platform) appear in the ad, the landing page, the blog and
  llms.txt. That repetition is what makes both Google and the AI assistants
  confident enough to surface and quote you.

---

## 7. Measurement

- **Primary metric**: onboarding-form submissions (visible in the super-admin
  area, attributable to campaign/ad via the `visitorId` join).
- **Install the Meta Pixel** on the site if it is not already there. With the
  Pixel you can switch Campaign A from Traffic to a Sales/Leads objective
  optimised for form submits, which usually lowers cost-per-lead a lot once it has
  ~50 conversions to learn from. Add a Pixel "Lead" event on the Contact success
  screen.
- **Watch**: cost per landing-page view (Campaign C/D), cost per lead (A/B),
  and the page-follow growth (D). Kill any ad over 3–4 days with high spend and no
  result; double the budget on the winner.
- **Optional code enhancement** (not done here): stamp the captured campaign onto
  the onboarding row itself (the `heard` field, or the table's `source` column) so
  staff see "Facebook, clubs_au_acq_2026" directly in the enquiry without opening
  the Usage page. Say the word and I'll wire it in.

---

## 8. Launch checklist

1. Confirm Facebook Page + Instagram are set up and linked in Meta Business
   Manager (Campaign D needs them).
2. Install the Meta Pixel and add the Lead event on the Contact success screen.
3. Build Campaign A first (Traffic or Leads), four ads (A1–A4), the dynamic UTM
   template in URL parameters.
4. Upload your customer-email list as an **exclusion**, and any contact list as a
   **custom audience**.
5. Add the three creatives plus 2–3 real screenshots, and shoot one short
   screen-recording.
6. Launch A, let it learn, then add B, C and D.
7. After ~50 leads, build a 1% AU lookalike and let it run as its own ad set.
