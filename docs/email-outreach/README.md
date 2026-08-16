# BetterCricket outreach emails

Pasteable HTML emails for the Cricket Australia outreach, plus plain-text fallbacks.

| File | Use | Subject | Theme |
|------|-----|---------|-------|
| `email-preseason-2026-plain.txt` | **Send this to a cold list.** Written as a real plain-text email from one person | {Club}: stats sorted before round one | No template at all, on purpose. See the format note below |
| `email-preseason-2026.html` | The branded version, for the warm list | {Club}: stats sorted before round one | Dark navy, one CTA, compact module list, static trusted-by strip |
| `email-preseason-2026-lapsed.html` | Re-engagement: past enquiries and unfinished trials | Come and see what you're missing | Same shell. The example clubs ARE the pitch and sit above the button, new-feature cards below it |
| `email-selfserve-launch.html` | The self-serve launch (sent alongside the BC_AU_SelfServe_Aug2026 Meta campaign) | Get all of your club's stats online today! Free 14 day trial, no strings attached | Dark navy, echoes the /trial page |
| `email-initial-demo.html` | First email of the original sequence | How many volunteer hours did your club burn this week? | Dark navy, with the module section |
| `email-followup-demo.html` | The short follow-up | Worth two minutes of your time | Light body, navy header/footer |

Each has a matching `.txt` plain-text fallback.

## The pre-season send (Aug 2026)

### Campaign name and UTM scheme

**`BC_AU_PreSeason_EDM_Aug2026`** is the campaign. Both variants carry it, so
the push reads as one line in reporting; `utm_content` is what separates them
and tells you which link was clicked.

The name follows the convention the Meta campaigns already use
(`BC_AU_SelfServe_EDM_Aug2026`, `BC_AU_Trials_CBO_Aug2026`):
`BC` + `AU` + theme + channel (`EDM` for email, omitted for paid social) +
month and year.

Every link in every file carries all four tags:

| Tag | Value | Why |
|-----|-------|-----|
| `utm_source` | `ca` | Per-club placeholder. `make_sends.py` swaps it for the recipient club's `utm_code`, which is what ties a visit back to that club. |
| `utm_medium` | `email` | Separates this from paid social. |
| `utm_campaign` | `BC_AU_PreSeason_EDM_Aug2026` | The campaign. Same on both variants. |
| `utm_content` | see below | Which link, in which variant. |

`utm_content` values, all prefixed so a wildcard picks up a whole variant:

| Value | Where |
|-------|-------|
| `edm_primary_cta` | The main trial button |
| `edm_demo_cta` | "Book a demo first" under it |
| `edm_module_<slug>` | One per module card (`betterstats`, `betterselect`, `bettersocials`, `betteradmin`, `betteriq`, `betterfantasy`) |
| `edm_trust_strip` | The four club crests |
| `edm_lapsed_*` | The same set in the re-engagement variant |
| `edm_lapsed_new_<slug>` | One per new-feature card in the re-engagement variant (`juniorstats`, `votecounting`, `bettersocials`, `betteradmin`) |

**The re-engagement variant has drifted, on purpose.** It is sent through
BetterComms rather than pasted, so its `utm_source` carries the `{{utm_code}}`
merge variable instead of the `ca` placeholder (the pattern the root
`CLAUDE.md` documents for a template that places its own UTM tags), and its
campaign is **`BC_AU_PreSeason_lapsed_EDM_16Aug2026`** rather than the shared
`BC_AU_PreSeason_EDM_Aug2026`. Its greeting and club name are `{{first_name}}`
and `{{club}}`. `make_sends.py` only ever rewrites `email-initial-demo.html`,
so none of this affects it.

**Where it shows up.** `usePageView.js` writes `utm_campaign` into
`usage_events` on every page view, so the Usage page reports the campaign
without anything being registered first. A completed signup stores the whole
attribution blob on `organisations.signup_attribution`, which is what the
ad-signups panel on the Meta Ads page lists.

Two things worth knowing. A signup from this email is stamped
`signup_source = 'self_serve_ad'` rather than something email-specific, because
that flag keys on "was there any campaign signal", and our links carry one.
Read `utm_campaign` in the attribution to tell email from paid. And these
signups are correctly **excluded** from the Meta campaign's own registration
count: `_attribution_matches_campaign` only accepts a `utm_source` in
`{fb, facebook, meta, ig, instagram}`, and ours is `ca`.

**Split the list before sending.** The cold email explains the problem from
scratch; the re-engagement one assumes they already know what BetterCricket is
and would read as a mailshot if it repeated the pitch. Alternative subject lines
are in the comment at the top of each HTML file.

### What the ad account says actually converts

Pulled from the live Meta account rather than assumed. Two ads carry the whole
lesson, and it is exactly the clicks-but-no-conversions problem:

| Ad | Headline | Ask | CTR | Landing views | Club picks | Registrations |
|----|----------|-----|-----|---------------|------------|---------------|
| `Ad_CheckOutYourClub_v2` | "Is your club's history online yet?" | "Have a look at your own club's page" (SEE_DETAILS) | 2.53% | 348 | 62 | **12** at A$43.51 |
| `Ad_ClubHistory_Trial_Hero_v3` | "Your club's full history, kept up to date for you" | Feature list, then SIGN_UP | 1.99% | **420** | 0 | **0** |

The second ad has the best outbound CTR in the whole account (1.90%) and the
most landing-page views, and it has never produced a single registration. The
first ad produced every registration the account has ever had.

Three things separate them, and all three are now in the email:

1. **A question about THEIR club beats a statement about our product.** The
   winner's headline is the email's headline and subject line.
2. **"Have a look" beats "sign up".** The winner's button was SEE_DETAILS, not
   SIGN_UP. The email's button is now "Find your club and have a look", which
   is also literally what `/trial` opens on, so the promise and the page agree.
   Asking a volunteer committee member to commit in an email is a bigger ask
   than asking them to be curious about their own club.
3. **Short beats a feature list.** The winner's body is two sentences. The
   zero-conversion ad lists six features across five sentences.

The proven reassurance line is "free, no card needed, about 3 minutes", and it
sits directly under the button in both emails. **Do not swap the button back to
a commitment ask without a test** — that is the one change the account already
has evidence against.

### Why these are shaped the way they are

Written against published cold-email benchmarks rather than instinct. The rules
that drove the structure, and what they cost:

- **Length.** Reply rates peak at 50-125 words and fall roughly by half past 200
  (8.2% vs 3.9% across a 4M+ email aggregate; Boomerang's 40M-email study puts
  the sweet spot near 75). The cold email's reading copy is **124 words**, inside
  that band. Each of the three paragraphs is one idea: your history already
  exists and we make a site of it, we fix its errors, then it runs itself. **If
  something new has to go in, take a paragraph out.**
- **Order: headline, copy, CTA, proof, then modules.** The trusted-by strip sits
  directly under the button so the crests land while someone is deciding whether
  to click, rather than three screens down. The module cards come after the ask,
  because anyone still scrolling past the CTA is browsing and the stats are what
  is being sold. The whole pitch now fits on one phone screen before the cards.
- **The re-engagement email inverts that on purpose.** Its clubs sit ABOVE the
  button under an "Already online" heading, because there they are not
  reassurance next to an ask, they are the ask: these clubs are live and this one
  is not, go and look at one. The button follows as the obvious next step once
  someone has seen what a finished club looks like. That email is a "what you're
  missing" pitch rather than a changelog — an earlier version led with three
  things we had built, which is us talking about ourselves to someone who has
  already said no once. What we have built since is one sentence in the body,
  and the detail sits in three cards BELOW the button.
- **The re-engagement email's new-feature cards** (the BetterSocials rebuild,
  vote counting, the updated BetterAdmin, junior stats, in that order) reuse the
  cold email's module-card styling and sit after the CTA for the same reason its
  module cards do. They are a feature list, and a feature list read before the reason to
  click is what turns this into the changelog the angle is meant to avoid. Each
  card links to the module page that feature lives on.
- **They are a 2x2 grid, not a stack**, which is what let a fourth card go in
  for no extra height. Cells are 50% with their own padding rather than a
  spacer column, because email has no grid-gap and Outlook collapses an empty
  column. The card is the full-width one shrunk: 32px icon tile, 14px title,
  one line of copy.
- **The reading copy above the crests is 51 words**, down from about 110. The
  four things we have built were a paragraph and are now the grid, so nothing
  was lost by cutting it.
- **The range line under the crests** ("single team country sides to the top
  Premier Cricket clubs") answers the objection those four crests raise on
  their own: all metro, all a similar size. It is placed with the crests rather
  than in the body because that is where the objection is formed.
- **One CTA.** Every green button goes to `/trial` and nothing competes with it.
  The demo option is a small text link underneath, not a second button, because
  a rival button splits the click.
- **Problem, then agitate, then solution.** The email opens on their spreadsheet
  rather than on us, makes the cost of it concrete (three specific failures, not
  "errors creep in"), and only then says what we do. Specific beats general:
  "totals that stopped adding up in 2019" outperforms "inaccurate data".
- **Subject lines are 3-7 words** and personalised with `{Club}`. One
  personalised attribute is worth a real lift in opens, and the club name is the
  one attribute we always hold. Anything past 60 characters truncates on mobile.
- **The deadline sits in the P.S.**, which is one of the most-read lines in an
  email. Opening on the season would have pushed the hook down the page.
- **The old draft's section headings are gone.** Headed sections make an email
  read as a newsletter, and a newsletter is skimmed rather than answered.

### Plain text for cold, HTML for warm

This is the one place the research argues against a designed template. In B2B
outreach, plain text from a named person beats styled HTML on replies by a wide
margin, because a designed email reads as a broadcast and people answer emails
that look like they were written to them.

So `email-preseason-2026-plain.txt` is the cold-list send: 113 words, no logo,
no buttons, sent from Jack's own address. The HTML version is for the warm list,
where the crests and the brand do real work and nobody is deciding whether you
are a stranger. **If you only send one thing to strangers, send the plain one.**

### The trusted-by strip

The site's `TrustedByStrip` scrolls with a CSS marquee. **That cannot work in
email** — Gmail strips `<style>` so there are no keyframes, and Outlook has no
animation at all. The strip in these emails is the same four clubs laid out
statically, styled to match. Each crest links to that club's live public site,
which is the part that actually builds trust.

Clubs shown: Scarborough, Rockingham-Mandurah, Applecross, Leeming Spartan. To
swap one, replace the crest `<img>`, the club name and the `/{slug}` link, and
add a matching PNG under `frontend/public/email/`.

**Two crests are new and must be deployed before the send.**
`scarborough-cc.png` and `rockingham-mandurah-cc.png` were added to
`frontend/public/email/` in the same commit as these emails and currently 404
on production. They were downscaled to 88px square (2x the 44px display size)
from the clubs' own uploaded logos, which are up to 700KB at full size. Send
yourself a test after the deploy and confirm all four crests render.

### No product screenshots in these emails

Tried and pulled from the re-engagement email: a strip of two app screenshots
under the new-feature grid, cropped from `frontend/public/screenshots/`. The
emails carry club crests and module icons only.

Two things worth keeping if it ever comes back. Only two of the four new
features have an honest current screenshot, so a shot per card was never on,
and at the 252px a grid cell allows, none of the UI is legible anyway. And
**do not resize a screenshot with headless Chromium** - it returns a
part-painted image for a file:// PNG that size, which reads as an empty band
across the bottom of the shot and looks like the app failing to load. Crop and
resample the PNG directly.

### Naming

These emails call the back-office module **BetterAdmin**, matching the public
site. The app calls the same module BetterClubhouse, and that split is
deliberate and long-standing (see the note in the root `CLAUDE.md`). A prospect
only ever sees the public name, so the emails and the site agree; a club that
signs up will see BetterClubhouse once they are inside the admin app.

The emails describe it as **expanded** rather than new, because BetterAdmin
itself is not new. What is new is what it covers: the member directory, the
volunteer roster, committee meetings and the club diary, on top of the fees and
comms it always had. The module page was updated to say so.

The **initial** email is the one to send first. It runs the longer "we've been those volunteers" copy, carries the five-module section (each card links to its page on the site), and uses the dark background you asked for. The **follow-up** is the short two-minute nudge, on a light body.

## How to send either one

**Gmail (web):**

1. Open the `.html` file in Chrome or Safari (double-click it).
2. Select everything (Cmd+A), copy (Cmd+C).
3. New compose window in Gmail, paste (Cmd+V). Layout, colours, module cards, buttons and links all carry across.
4. Set the subject yourself (it's in a comment at the top of each HTML file, and in the table above).
5. Replace `[first name]` with the recipient's name before sending.

**Mac Mail:** same workflow. Open the HTML in Safari, Cmd+A, Cmd+C, paste into a new message. Set the subject and swap in the first name.

Send yourself a test first and check it on your phone, especially the dark initial email (see the dark-mode note below).

## Decisions to confirm, Jack

1. **Module cards link to `https://betterat.cricket/modules/{slug}`** (betterstats, betterselect, bettersocials, betteradmin, betteriq) — the same `/modules/...` routes the site nav uses. You pointed me at `betterstats.cricket/modules`; both domains serve the same app, and I kept everything on `betterat.cricket` so the module links match the `/applecross` and homepage links in the body. Say the word if you'd rather the whole email sat on `betterstats.cricket`.
2. **Module icons are the real site icons**, rasterised from `frontend/src/assets/modules/*.svg` to PNGs at `frontend/public/email/*.png` (email clients can't render SVG). The email points at `https://betterat.cricket/email/{module}.png`, so they show once the frontend is deployed. Each icon sits on a cell filled with that module's accent colour, so if a recipient has images off (Gmail's default for unknown senders) the cell still shows as a coloured tile and the card text reads normally.
3. **Each card shows the module name + its one-line tagline + an "Explore →" link**, not the three feature bullets from the site. Five cards with three bullets each makes the email very long; the bullets live on the page each card clicks through to. Easy to add a couple of bullets per card if you want it richer.
4. **The "find out more" button goes to the homepage** (`betterat.cricket/?utm...welcome`), matching the "Find out more here" line in your copy. The follow-up email's second button instead goes to `/contact` (the site's "Get Your Club" CTA). The Google Form URL is still in the repo (`frontend/src/data/marketing.js`, `FORM_URL`) if you'd prefer to point a button straight at the form.
5. **Links are `https://`** rather than the `http://` in your copy (same destination, avoids Gmail flagging the links).
6. **Every link carries `?utm_source=ca&utm_medium=email&utm_campaign=welcome`** now: the header wordmark, all five module cards, the See-a-club button, Find-out-more, the new Request-a-free-trial button, the signature and the footer. One-word change to `followup` if you'd rather.
7. **The 14-day free trial is the closing CTA.** The trial line sits at the bottom above a green "Request a free trial" button that goes to the contact page (`/contact`), the same destination as the follow-up email's "Get your club" button. It was moved there from mid-email so it doesn't read twice.
8. **Wording is pitched at premier/grade clubs.** "community cricket" / "community cricketers" became "club cricket" / "club cricketers". (The BetterSocials tagline's "your community actually reposts" is left as-is, since there it means the club's followers, not the level of cricket.)

## Voice

The initial email opens on the gap PlayHQ left ("the tools clubs actually want and need") and goes straight into BetterStats, then opens out to the other modules so none of them slip. Tone is deliberately plain and understated rather than salesy: the hype lines ("the lot", "no club at your level has had before", "before paying a cent", the "built by club cricketers" sign-off) were cut, and the savings, trial and CTAs are stated straight. Subject matches: "The stats page PlayHQ never built for your club" (swap freely in Gmail).

The three CTAs are spread down the email rather than stacked: "See a club in action" (Applecross) sits right after the intro, "Find out more" (homepage) in the middle after the savings line, and "Request a free trial" (contact page) as the closing CTA above the signature.

Earlier it was run through the project humanizer to sit with the rest of the site: no em dashes anywhere (body, signature, the two module taglines that used one now read with a colon), and the plain Australian voice kept throughout. If you'd rather the cards quote the live site tagline exactly, the BetterStats and BetterAdmin lines are the only spots that differ.

## Header (initial email)

The header is the text wordmark "BetterCricket" (one word, green "Cricket"), no logo image. We tried the logo mark there, but it can't show until the PNG is deployed to betterat.cricket, so it read as a broken image on a paste-test and was pulled. If you want it back, the mechanism works the same as the module icons: deploy the asset first, then add the `<img>`.

## Dark-mode note (initial email)

You asked for the dark background, so the initial email is dark navy throughout. One thing to watch: Gmail's dark mode inverts *pure* white text (`#ffffff`) to black on any cell that has no background colour of its own, which is what turned the trial line black. Every white text run now uses the body near-white `#e6e8ef`, which Gmail leaves alone, and the module-card names stay white because they sit on a coloured/dark card cell. A few other clients also force their own dark treatment and can shift contrast slightly, so do a test send and check it on whatever you and your recipients read mail on. The follow-up email keeps a light body to dodge all of this.

## Brand values used (pulled from the repo)

- Base navy: `#0b1220` (site theme-colour); card surface `#131c2e`, borders `#243352` / `#1d2331` (Tailwind `navy.*`)
- Core accent green: `#16C784` (`--pb-accent` / Tailwind `accent`)
- Module accents (`src/lib/moduleBrand.js`): BetterStats `#16C784`, BetterSelect `#3B82F6`, BetterSocials `#EC4899`, BetterAdmin `#F59E0B`, BetterIQ `#A855F7`
- Body text on dark `#e6e8ef`, dim text `#aab1c2` / `#8a90a2` (theme tokens)
- Module taglines + routes are copied from `src/data/modules-marketing.js`
- Font: the site uses Geist/Inter, which email clients won't load, so the email falls back to Helvetica Neue / Arial.
