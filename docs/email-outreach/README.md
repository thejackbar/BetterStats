# BetterCricket outreach emails

Pasteable HTML emails for the Cricket Australia outreach, plus plain-text fallbacks.

| File | Use | Subject | Theme |
|------|-----|---------|-------|
| `email-preseason-2026.html` | **The current send.** Pre-season push to the cold list (clubs in the directory who have never signed up) | The season's nearly here. Get the whole club sorted now. | Dark navy, section rules, five module cards with BetterClubhouse badged NEW, static trusted-by strip |
| `email-preseason-2026-lapsed.html` | The same push to the warm list (past enquiries and unfinished trials) | A fair bit has changed since you last looked at us | Same shell, roughly half the length, leads on what is new |
| `email-selfserve-launch.html` | The self-serve launch (sent alongside the BC_AU_SelfServe_Aug2026 Meta campaign) | Get all of your club's stats online today! Free 14 day trial, no strings attached | Dark navy, echoes the /trial page |
| `email-initial-demo.html` | First email of the original sequence | How many volunteer hours did your club burn this week? | Dark navy, with the module section |
| `email-followup-demo.html` | The short follow-up | Worth two minutes of your time | Light body, navy header/footer |

Each has a matching `.txt` plain-text fallback.

## The pre-season send (Aug 2026)

Two variants of one campaign, `utm_campaign=BC_AU_PreSeason_EDM_Aug2026`. They
share the campaign so the send reads as one line on the ad-signups report;
`utm_content` is what separates them (`edm_*` on the cold email,
`edm_lapsed_*` on the warm one).

**Split the list before sending.** The cold email explains what BetterCricket
is; the warm one assumes they already know and would read as condescending to
someone who has never heard of us. Alternative subject lines are listed in the
comment at the top of each HTML file.

**What each one argues, in order.** Cold: the season is close and the jobs are
piling up, it was never just stats (the five modules), your spreadsheet has
errors in it and we find them, you are not doing the setup alone, set it up
once and never touch it again, then the analysis payoff, then proof, then the
trial. Warm: here is what is new since you looked (BetterClubhouse, vote
counting, guided setup), a short reminder of the accuracy and set-and-forget
argument, proof, then the trial.

**CTA structure is trial first, demo second.** Every green button goes to
`/trial`. Under each one, a smaller "Book a demo with us" text link goes to
`/contact`. The demo link exists because the emails promise hand-holding, and a
committee that wants that needs somewhere to land other than a self-serve
signup form.

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

### Naming

These emails call the back-office module **BetterClubhouse**, which is what it
is called in the app. The marketing site was renamed to match in the same
commit, and `/modules/betteradmin` now redirects to `/modules/betterclubhouse`,
so older emails and blog links still resolve.

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
