# Outreach email: "Worth two minutes of your time"

Files in this folder:

- `email-followup-demo.html` is the branded email. Open it in a browser, select all, copy, paste into your mail client.
- `email-followup-demo.txt` is the plain-text fallback of the same copy.

## How to send it

**From Gmail (web):**

1. Open `email-followup-demo.html` in Chrome or Safari (double-click the file).
2. Select everything (Cmd+A), copy (Cmd+C).
3. In Gmail, start a new compose window and paste (Cmd+V). The layout, colours, buttons and links carry across.
4. Set the subject yourself: `Worth two minutes of your time` (it's also in a comment at the top of the HTML file).
5. Replace `[first name]` with the recipient's name before hitting send.

**From Mac Mail:**

Same workflow. Open the HTML file in Safari, Cmd+A, Cmd+C, paste into a new message in Mail. Mail keeps rich formatting on paste. Set the subject and swap in the first name as above.

Send yourself a test first and check it on your phone before the real sends.

## Decisions to confirm, Jack

1. **"Get your club" button goes to `https://betterat.cricket/contact`.** That's where the site's own "Get Your Club on BetterCricket today!" CTA points (Landing page). The lead-gen Google Form URL still exists in the repo (`frontend/src/data/marketing.js`, `FORM_URL`) if you'd rather send people straight to the form.
2. **No logo image; the header is a styled text wordmark** ("Better" in white, "Cricket" in the brand green), matching the site nav exactly. Two reasons: the only publicly hosted image on betterat.cricket is `/og-image.png`, which still carries the old BetterStats mark, and Gmail blocks images from unknown senders by default, so a text wordmark guarantees the branding shows on first open. If you want the real logo in there, drop a PNG of `frontend/src/assets/bettercricket-white.svg` into `frontend/public/` (e.g. `/logo-email.png`), deploy, and we can swap it in.
3. **Links are `https://`, not the `http://` in the brief.** Same destination (http just redirects), but https avoids Gmail flagging the links.
4. **UTM campaign is `welcome`** on the signature, header and footer links, per the approved brief. Since this is a follow-up send, you may want `utm_campaign=followup` instead; it's a one-word change in three places if so.

## Brand values used (pulled from the repo)

- Navy header/footer: `#0b1220` (site theme-colour)
- Accent green: `#16c784` (Tailwind `accent` / `--pb-accent`)
- Body text: `#1b1e27` on white, footer text `#8a90a2` (theme tokens)
- Font: the site uses Geist/Inter, which email clients won't load, so the email falls back to Helvetica Neue / Arial.

The body section is white on purpose: a full dark-navy email tends to render badly when Gmail dark mode auto-inverts it. The navy lives in the header and footer bands only.
