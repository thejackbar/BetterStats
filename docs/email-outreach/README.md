# BetterCricket outreach emails

Two pasteable HTML emails for the Cricket Australia outreach, plus plain-text fallbacks.

| File | Use | Subject | Theme |
|------|-----|---------|-------|
| `email-initial-demo.html` | First email in the sequence | How many volunteer hours did your club burn this week? | Dark navy, with the module section |
| `email-followup-demo.html` | The short follow-up | Worth two minutes of your time | Light body, navy header/footer |

Each has a matching `.txt` plain-text fallback (`email-initial-demo.txt`, `email-followup-demo.txt`).

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
6. **UTM campaign is `welcome`** on the signature, header, footer and find-out-more links. One-word change to `followup` if you'd rather.

## Voice

The initial email's body copy was run through the project humanizer to sit with the rest of the site: em dashes taken out (the body, the signature and two module taglines), a doubled "chasing" reworded, and the sign-off split onto its own line. The two site taglines that used an em dash (BetterStats, BetterAdmin) read with a colon in the email instead, so the email itself stays dash-free. If you'd rather the cards quote the live site string exactly, those two are the only spots that differ.

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
