# PR: BetterSocials — Event / Announcement posts

> Paste this as the PR body. Suggested branch: `feat/bettersocials-event-posts`.

## What
Adds an **Events** tab to the BetterPosts designer with a whitelabel club-event
poster suite — Auction Night, The 100 Club, Curry Night, Selections,
Presentation Night, Season Launch, Live Music, Quiz Night, and a generic blank —
each available in **11 layouts** (Floodlit, Colour Block, Ticket, Scoreboard,
Gazette, Sticker Pop, Kinetic, Swiss, Crest, Chalkboard, Polaroid).

## Why
Clubs need quick, on-brand posts for socials and fixtures, not just match/stats
content. This reuses the existing designer + export so it's one familiar flow.

## How it fits the existing system
- New templates follow the same contract as `cricket-templates` /
  `round-templates`: full-bleed **1080×1080**, colour from the active `palette`,
  display type via `--social-display-font`, shared primitives (`AutoFitText`,
  `ClubLogo`, `Halftone`, `Stripes`).
- Export is unchanged — same `exportNodeToPng` (modern-screenshot) pipeline.
- Whitelabel by default: club name, logo/monogram and accent come from
  `settings`; the facts are one editable `event` object.

## Headline feature — themed backgrounds
Photo-led layouts take an uploaded image rendered behind a dark/accent scrim at
adjustable opacity (a curry shot for Curry Night, a band for Live Music). Layouts
without a photo slot use a faded 3D glyph from the existing `assets/thiings` set.

## Files
**New**
- `frontend/src/social/event-templates.jsx`
- `frontend/src/components/admin/EventPostEditor.jsx`

**Changed**
- `frontend/src/pages/admin/AdminSocialPost.jsx` — register templates + Events tab + render branch (6 small edits, see `EVENTS_INTEGRATION.md`)
- `frontend/index.html` — add 4 Google Font families

## Test plan
1. `/admin/social-post` → **Events** tab.
2. Pick each preset; confirm copy + suggested layout fill in.
3. Cycle all 11 layouts; check club logo/name/accent render.
4. On a photo layout (Floodlit/Colour Block/Kinetic/Gazette/Sticker/Polaroid):
   upload an image, adjust opacity, confirm legibility.
5. **Export PNG** — confirm 1080×1080 and fonts embed correctly.
6. Try a club with no logo (monogram shield fallback) and a non-default palette.

## Notes
- No new binary assets (reuses `assets/thiings`).
- Light-surface layouts ignore the dark-mode toggle by design.
