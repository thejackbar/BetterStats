# Hyperframes Composition Brief: BetterPosts

## Objective
A short launch-style brag video for BetterPosts (the post designer inside BetterSocials, part of BetterCricket).

## Output
- Composition directory: `docs/marketing-videos/betterposts/composition/`
- Rendered video: `docs/marketing-videos/betterposts/brag.mp4` (not committed; delivered in chat)
- Format: vertical, 1080x1920
- Duration: 25 seconds

## Source Material
- Project root: the BetterStats repo
- Primary files read: `frontend/src/pages/admin/AdminSocialPost.jsx`, `frontend/src/data/marketing.js` (the BetterSocials compare copy), `frontend/src/lib/moduleBrand.js`, `frontend/src/styles/theme.css`, `frontend/src/lib/modules.js`, the BetterPosts guide in `docs/dev-notes/guides/betterposts-socials-and-media.md`
- Product name: BetterPosts (module: BetterSocials)
- Tagline / strongest claim: "Match-day graphics, in seconds."
- Key UI moment recreated: the Final Score tab, empty Margin Hero card, "Or pick from your Games", the card filling with 8/204 v 7/141, BY 63 RUNS and the POTM strip. These are real frames of the real editor (API stubbed), not a mock-up. `capture/capture.mjs` regenerates them.
- Copy that must appear verbatim:
  - "Pick the game."
  - "Score, margin, top performers, player of the match."
  - "A layout for each size, not a stretched square."
  - "Match-day graphics, in seconds."
  - "Start your BetterCricket trial" and "betterat.cricket/trial"

## Creative Direction
- Tone preset: `app-store`
- Creative direction: dark, premium, Apple-style product film. One joke (the bat crack).
- Interpretation: smooth wipes, no mess, everything on screen is the product. Matches the look of the September BetterCricket videos.
- Angle: match day ends and the result post is still blank. BetterPosts fills it from the scorecard.
- Hook: "Stumps called." then "Post still blank." over the real empty card.
- Outro / punchline: "Match-day graphics, in seconds." with the lockup and trial CTA.
- Avoid: generic SaaS language, abstract filler, prices, competitor names, claims beyond the product copy.

## Visual Identity
- Background: `#0a0d14`
- Text: `#e6e8ef`
- Accent: green `#16c784` (BetterCricket), pink `#ec4899` (BetterSocials), amber `#f5c242` (the post's own accent)
- Display font: Barlow Condensed 700/800. Body: Inter. Labels: JetBrains Mono. All vendored under `composition/assets/fonts/`.
- Visual references from the project: the editor UI, the Margin Hero, Versus Columns, Innings Bars and Match Ticket result layouts, the BetterSocials module mark, the BetterCricket mark.

## Storyboard
Use the storyboard in `brag-plan.md` as the creative contract.

Scene summary (as built):
1. Hook: 0.00 to 3.70s. Two lines, the real empty card rises.
2. Reveal: 3.70 to 6.34s. BetterPosts lockup, "Your match, already in it."
3. Pick the game: 6.34 to 15.28s. Camera pushes into the real editor, cursor opens the list and picks the game, the card fills, "BY 63 RUNS" slams at 12.65s.
4. Every size: 15.28 to 19.49s. The same post as Square, Portrait and Story (real exports, native layouts).
5. Same game, any layout: 19.49 to 22.65s. The editor's real tab names and three more real result layouts. The lineup layout was tried and dropped: with no photos it looked thin.
6. Outro: 22.65 to 25.00s.

## Audio
- Audio role: warm bed with sparse, motion-matched accents.
- Audio arc: bed in at 0, lifts at the reveal, ducks briefly under the crack, fades over the last second.
- Music: `happy-beats-business-moves-vol-11-by-ende-dot-app.mp3` (114.84 BPM). Presets read from `.claude/skills/brag/assets/music/cues/`.
- Music treatment: volume lane fades in over 0.5s, ducks to 0.55 for 1.1s from 12.5s, fades out from 24.0s.
- Music cue guidance: bundled preset. Beat-locked: 3.70s (reveal), 12.65s (BY 63 RUNS and the crack), 17.91s (Story), 22.65s (outro lockup, lands about 0.15s after the cue because the wipe is covering the frame). Beat-grid: 7.91 / 8.44 / 8.96 (three games), 20.02 / 20.54 / 21.07 (three cards). Text was held to the reading floor and not snapped to the grid.
- Audio-reactive treatment: subtle. The pink glow behind the lockup swells with the bass (`assets/audio-data.js`, 30fps, 8 bands, extracted with the Hyperframes creative skill's script).
- Audio-coupled moments: the cursor clicks (7.70, 9.50), the crack (12.65), the size changes (16.86, 17.91), the four cards, the quiet crack at the end (22.85).
- SFX: `assets/sfx/bat-crack.wav` is synthesised here (seeded numpy: bandpassed noise burst, two damped sines, a low knock). Interface ticks and card slides are from the skill's bundled Kenney set.
- Audio files: copied into `composition/assets/`.

## Hyperframes Instructions
Built with the current Hyperframes domain skills (core, animation, creative, audio, cli), not a /brag template. Gate: `npx hyperframes check` reports 0 errors. Remaining warnings are structural hints about keeping the project as a single file.
