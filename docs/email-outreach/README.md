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
2. **Module icons are coloured tiles with the site's geometric glyphs, not the real module logos.** The logos are bundled SVGs with no public URL, and Gmail blocks remote images from unknown senders by default. The coloured tiles (each in that module's brand accent) always show on first open. If you want the real logos, we'd need to publish them as PNGs under `frontend/public/` and deploy first.
3. **Each card shows the module name + its one-line tagline + an "Explore →" link**, not the three feature bullets from the site. Five cards with three bullets each makes the email very long; the bullets live on the page each card clicks through to. Easy to add a couple of bullets per card if you want it richer.
4. **The "find out more" button goes to the homepage** (`betterat.cricket/?utm...welcome`), matching the "Find out more here" line in your copy. The follow-up email's second button instead goes to `/contact` (the site's "Get Your Club" CTA). The Google Form URL is still in the repo (`frontend/src/data/marketing.js`, `FORM_URL`) if you'd prefer to point a button straight at the form.
5. **Links are `https://`** rather than the `http://` in your copy (same destination, avoids Gmail flagging the links).
6. **UTM campaign is `welcome`** on the signature, header, footer and find-out-more links. One-word change to `followup` if you'd rather.

## Dark-mode note (initial email)

You asked for the dark background, so the initial email is dark navy throughout. One thing to watch: a few mail clients force their own dark-mode treatment and can shift dark emails slightly (mostly text/border contrast). Gmail on desktop and iOS renders it as built; the test send is mainly to confirm it on whatever you and your recipients read mail on. The follow-up email keeps the light body specifically to dodge that, so the two emails cover both approaches.

## Brand values used (pulled from the repo)

- Base navy: `#0b1220` (site theme-colour); card surface `#131c2e`, borders `#243352` / `#1d2331` (Tailwind `navy.*`)
- Core accent green: `#16C784` (`--pb-accent` / Tailwind `accent`)
- Module accents (`src/lib/moduleBrand.js`): BetterStats `#16C784`, BetterSelect `#3B82F6`, BetterSocials `#EC4899`, BetterAdmin `#F59E0B`, BetterIQ `#A855F7`
- Body text on dark `#e6e8ef`, dim text `#aab1c2` / `#8a90a2` (theme tokens)
- Module taglines + routes are copied from `src/data/modules-marketing.js`
- Font: the site uses Geist/Inter, which email clients won't load, so the email falls back to Helvetica Neue / Arial.
