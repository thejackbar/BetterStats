# Brag Plan: BetterPosts (BetterCricket)

Output directory: `docs/marketing-videos/betterposts/`. The sources live in the repo on purpose. The 12 BetterCricket videos from September were built in a scratchpad that was wiped on resume, and only the finished zips survived.

## What is this app?
BetterPosts is the post designer inside BetterSocials. It turns a played game into a finished social graphic for a cricket club: pick the game, and the score, result, top performers and player of the match fill themselves in.

## The angle
Match day ends, and then comes the second job: somebody opens a design app and retypes the score, the margin and the player of the match. BetterPosts already holds the scorecard, so that job is one tap. The video shows a blank result card filling itself from a real game.

The product claims we lean on, in the product's own words:
- "Match-day graphics, in seconds."
- "Auto-fill from your match data. No retyping names and figures."
- "Pick one and the score, result, top performers and player of the match fill in."
- "Your crest, colours and display fonts by default. No design skills needed."

## Hook (first 3 seconds)
Dark screen. Two lines land one after the other: "Stumps called." then "Post still blank." Under them, the real empty Margin Hero card (WIN, a dash, empty brackets) sits at the bottom of the frame. The viewer is meant to recognise the Saturday-night chore.

## Key moments (the middle)
1. **Pick the game.** The real editor's "Or pick from your Games" list opens. Three games arrive one at a time. A cursor clicks "Applecross Cricket Club v Balcatta, WIN".
2. **It fills.** The card goes from "WIN / dash / ()" to 8/204 v 7/141, "BY 63 RUNS" and the POTM strip. "BY 63 RUNS" lands with a bat-on-ball crack, locked to a strong beat.
3. **Every size.** The same post as Square, Portrait and Story, one after the other, each a native layout and not a stretched square.
4. **Not just results.** Four more real posts from the same editor stack in one by one (result and lineup layouts), under the editor's own tab names: Lineup, Final Score, Player of the Match, Team of the Week, Milestones.

## Outro / punchline
"Match-day graphics, in seconds." then the BetterPosts lockup and "Start your BetterCricket trial. betterat.cricket/trial". The final beat is the bat crack again, quieter, as the lockup settles.

## User flow worth showing
Entry: the empty Final Score card in the editor.
Key action: Or pick from your Games, tap the game.
Result: the filled card with margin, both scores and POTM, then the size switch and download.

## Tone
- Preset: `app-store`
- Creative direction: dark, premium, Apple-style product film for a cricket club. Confident, sparing, one bat crack as the only joke.
- Interpretation: feature-card clean, smooth slides and wipes, no mess. This matches the look of the September videos (dark premium, BetterCricket mark on every shot, bat crack where the gong used to be).

## Format: vertical, 1080x1920 (9:16)
A 1080x1080 cut for feed placement is a second composition, not a crop. It is listed as a follow-up, not part of this run.

## Duration: 25 seconds

## Visual identity (from the project)
- Background: `#0a0d14` (`--pb-bg`), surfaces `#10141d`
- Text: `#e6e8ef`
- BetterCricket brand green: `#16c784`
- BetterSocials module accent (the BetterPosts mark): `#EC4899`
- Post accent (club sample): amber `#f5c242` on the Margin Hero template
- Display font: Barlow Condensed (the post headlines); UI labels and numbers in JetBrains Mono
- Body font: Inter
- Strongest visual element: the Margin Hero card, white "WIN" in a heavy condensed face with the margin in amber

## Share copy (draft)
Posted the result before the esky was shut. BetterPosts fills the card from the scorecard: pick the game, and the score, margin and player of the match are in.

## Real material and what is illustrative
- All editor frames are the real BetterPosts editor, run locally with the API stubbed (the same method the repo's `frontend/verification/shoot_templates.mjs` uses). The posts are real exports of the real templates.
- The scoreline (Applecross 8/204 def. Balcatta 7/141) is the one used in the September V5 video. Everything else on the scorecard is sample data: the player names are invented, and none of the real Applecross players from the earlier videos are used. Anything on screen that is sample data is described as such in the share notes, not in the video.
- No price, no competitor name and no claim beyond the product copy above appears in the video.

## Audio direction
- Role: warm bed with sparse, motion-matched accents.
- Music: `happy-beats-business-moves-vol-11-by-ende-dot-app.mp3`, 114.84 BPM, beat interval about 0.525s.
- Music treatment: starts at 0, fades in over the first 0.4s, sits low under the bat crack, fades out across the last 0.9s.
- Music cue guidance (from `assets/music/cues/...vol-11...music-cues.md`):
  - Strong cues to lock: 3.70s (BetterPosts reveal), 12.65s ("BY 63 RUNS" slam), 22.65s (outro lockup).
  - Also used: 6.34s (editor enters).
  - Beat grid for sequential reveals: 7.91, 8.44, 8.96 (game rows); 19.49, 20.02, 20.54, 21.07 (post cards). Sequential text is held to the 0.8s floor, so game rows are spaced every beat but each stays on screen until the click.
- Audio-reactive treatment: subtle. The pink glow behind the BetterPosts mark and the amber on "BY 63 RUNS" breathe with the bass. No waveforms.
- SFX posture: sparse. A synthesised bat-on-ball crack (fast attack, woody decay) at the "BY 63 RUNS" slam and, quieter, at the outro. Soft interface ticks on the game rows and the click. Card sounds for the post stack.
- Audio-coupled moments: cursor click on the game row; "BY 63 RUNS" slam; four post cards stacking.
- Restraint rule: no gong, no stinger on every scene, nothing that covers a line being read.

## Storyboard

### Scene 1: Hook, 0.00 to 3.70s
Dark `#0a0d14`. "Stumps called." slams in at 0.3s and holds. "Post still blank." follows at 1.7s and holds. The real empty Margin Hero card slides up under the lines at 2.0s. Small BetterCricket watermark top right from the first frame.
Sequential/interaction: two lines, each held 1.4s settled or more.
Audio intent: low and a little flat; music fades in, one soft tick per line.
Audio-coupled idea: none beyond the ticks.
Music: bed in.
Transition mood: hard wipe on the strong cue at 3.70 to Scene 2.

### Scene 2: Reveal, 3.70 to 6.34s
The BetterPosts mark (pink rounded square with the share icon) and the word "BetterPosts" scale in, "Better" white, "Posts" pink. Beneath: "Your match, already in it." held 1.2s.
Sequential/interaction: none.
Audio intent: lift; the first clear downbeat of the track.
Audio-coupled idea: glow behind the mark breathes with the bass.
Music: full bed.
Transition mood: smooth push to the editor at 6.34.

### Scene 3: Pick the game and it fills, 6.34 to 15.28s
The real editor (Final Score tab, empty card) fills the frame, panned to the Match Result panel. "Or pick from your Games" opens at about 7.4s. Three game rows arrive on beats 7.91, 8.44, 8.96. The cursor moves to "Applecross Cricket Club v Balcatta" and clicks at 9.5s (strong beat, tick). The view cuts to the filled card. Both scores and the POTM strip come in; "BY 63 RUNS" slams at 12.65s with the bat crack and holds until 15.0s. Caption lines: "Pick the game." (7.0 to 9.4s) and "Score, margin, top performers, player of the match." (10.4 to 14.6s, held 2.5s or more).
Sequential/interaction: yes. Cursor click, rows one by one, the card filling.
Audio intent: the satisfying moment of the video; the crack is the payoff.
Audio-coupled idea: click tick at 9.5s, crack at 12.65s.
Music: full bed, ducked slightly under the crack.
Transition mood: slide to Scene 4 at 15.28.

### Scene 4: Every size, 15.28 to 19.49s
The same post as three real exports side by side, then scaling into a row: "Square" (15.81), "Portrait" (16.86), "Story" (17.91, strong cue). Each label holds 1.2s or more. Caption: "A layout for each size, not a stretched square." held 2.0s.
Sequential/interaction: yes. Three exports arrive in turn.
Audio intent: tidy, rhythmic.
Audio-coupled idea: a card sound per export.
Transition mood: soft wipe to Scene 5 at 19.49.

### Scene 5: Not just results, 19.49 to 22.65s
Four real posts stack in one by one at 19.49, 20.02, 20.54, 21.07 over a strip of the real editor's tab names (Lineup, Final Score, Player of the Match, Team of the Week, Milestones). Caption: "Lineups, results, milestones." held 1.6s.
Sequential/interaction: yes. Four cards, one per beat.
Audio intent: momentum into the outro.
Audio-coupled idea: card sounds on each arrival.
Transition mood: clean cut on the strong cue at 22.65.

### Scene 6: Outro, 22.65 to 25.00s
BetterPosts lockup. "Match-day graphics, in seconds." held 1.4s. "Start your BetterCricket trial. betterat.cricket/trial" on the last line, held to the end. A quiet bat crack as the lockup settles.
Sequential/interaction: none.
Audio intent: resolve; music fades out over the last 0.9s.
Transition mood: end.

**Music mood for this video:** upbeat, restrained.
**Audio summary:** a warm bed that lifts at the reveal, one clear payoff crack at the slam, a quieter echo of it at the end.

## Lessons carried over from the September run
- BetterCricket mark on the opening and a small watermark throughout (the logo source is `frontend/src/assets/bettercricket-white.svg`).
- Bat on ball, not a gong.
- Use real product frames and real exports, not a mock-up.
- Mark anything illustrative as illustrative, and keep invented people out of any real club's data.
- Keep the build sources in the repo. The scratchpad does not survive a resume.
- Open question: the earlier 12 videos were 30 seconds. This one is 25 to stay inside the brag skill's limit. It can stretch to 30 if the Meta ad placement needs it.
