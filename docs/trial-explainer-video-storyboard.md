# BetterStats explainer video: storyboard (master, as built)

This is the storyboard of the master video that is rendered and approved. It was read from the composition source, so it says what is on screen and when, not what the brief hoped for. The plan it came from is `docs/trial-explainer-video-brief.md`. Where the build differs from the brief, the difference is listed at the end.

Nobody has frame-checked the render against this document yet. Jack watched it and called it a good video.

## Where everything is

| Thing | Value |
|---|---|
| Creative Claw project (`cloud_project_id`) | `a1c16fba-d65f-487f-97cc-3a5842ebde2e`, revision 1 |
| Master MP4 | https://cdn.creativeclaw.co/u/c62aeb52/videos/cloud/a1c16fba-d65f-487f-97cc-3a5842ebde2e/e39937ce-8a71-4988-b384-073c1e94bbdf/1.mp4 |
| Project ZIP (HyperFrames source) | https://cdn.creativeclaw.co/u/c62aeb52/zips/cloud/a1c16fba-d65f-487f-97cc-3a5842ebde2e/e39937ce-8a71-4988-b384-073c1e94bbdf/1.zip |
| Cost of the master | 480 credits (61 of those were the music bed) |
| 45 second ad cut | Requested, not started: review request `b2dddf39-216a-4d6a-8338-d9f9011cc6f6`, in Review mode, so it waits for Jack to press Generate. It was built from the master ZIP above, so the master project is untouched. |

Tool: `generate_html_video` (Creative Claw). It writes a HyperFrames composition (HTML, CSS, GSAP) and renders it. To change the master, call it with `cloud_project_id` and a prompt that says what to change. To start a variant without touching the master, pass the ZIP as `project_url`.

### Source layout (inside the ZIP)

- `index.html`: the whole composition. Ten `<section id="s1">` to `s10` clips, each with its own `scene1()` to `scene10()` function, so one scene can be edited alone. Scene start and length are the `data-start` and `data-duration` attributes on the sections. Captions are one array, `CUES`, of `[start, end, text]`.
- `assets/crests/*.png` (seven) and `assets/modules/*.png` (six): the uploaded art.
- `assets/music/bed.mp3`, played at volume 0.35 on one audio track.
- `fonts/inter.woff2`.

### Uploaded asset URLs (Creative Claw library)

| Asset | URL |
|---|---|
| Applecross crest | https://cdn.creativeclaw.co/u/c62aeb52/images/35e9bf59-d2be-4a89-882b-4d8bd585260b.png |
| Bannockburn crest | https://cdn.creativeclaw.co/u/c62aeb52/images/f5a0d38f-3e8a-44d7-a7a6-2bf63f175dae.png |
| Gisborne crest | https://cdn.creativeclaw.co/u/c62aeb52/images/a55b385d-b81b-4cfc-8da9-3cffa18ca9ec.png |
| Kalamunda crest | https://cdn.creativeclaw.co/u/c62aeb52/images/fcfda2ca-1370-4611-9a1f-8921a68735fb.png |
| Leeming Spartans crest | https://cdn.creativeclaw.co/u/c62aeb52/images/db6afd83-c73d-4d24-bcae-fa1e3b5b79b6.png |
| Scarborough crest | https://cdn.creativeclaw.co/u/c62aeb52/images/e9c8377c-468f-4b74-a65a-65eb8781f4c4.png |
| Sunbury crest | https://cdn.creativeclaw.co/u/c62aeb52/images/b9d34c39-1979-457d-8523-f041a426e368.png |
| BetterStats logo | https://cdn.creativeclaw.co/u/c62aeb52/images/e8a33f29-3e61-43a7-a40f-46d21183d357.png |
| BetterSelect logo | https://cdn.creativeclaw.co/u/c62aeb52/images/813292b3-3255-43a6-b6bf-379ac8cc7085.png |
| BetterSocials logo | https://cdn.creativeclaw.co/u/c62aeb52/images/82cb4008-443d-4af7-ad10-a1f883320fd8.png |
| BetterAdmin logo | https://cdn.creativeclaw.co/u/c62aeb52/images/0b2bf6cd-8418-4a66-af90-7583ae607939.png |
| BetterIQ logo | https://cdn.creativeclaw.co/u/c62aeb52/images/fa4180dc-7234-4447-9e62-75b178403c2a.png |
| BetterFantasy logo | https://cdn.creativeclaw.co/u/c62aeb52/images/c3d36f9d-ca7a-45ec-97b3-de28b255a4d9.png |

## The frame

- 1080 x 1350 (4:5), 30 fps, 137.5 seconds, MP4. No voiceover.
- Content area: a 900 px wide block, so everything important sits inside the centre 1080 x 1080 and a 1:1 crop works.
- Captions: one line of text at a time (never stacked), white bold on a dark pill, 90 px from the left, 900 px wide, with the bottom edge 215 px above the frame bottom. Each cue fades in over 0.25s and out over 0.2s. Nothing important sits in the top 120 px or bottom 200 px.
- Look: deep navy (`#0B1220`) background, panels `#121B2E`, brand green `#16C784` as the accent, Inter. Every scene has a header with the club crest and the screen name. The dashboard, leaderboards, records, player profile and StatLab headers carry a small "Example club" label. The import, merge and awards screens do not.
- Crests: all on the same white rounded tile. Sunbury is a full-bleed blue tile.
- Names: fictional players only (J. Mercer, T. Okafor, R. Singh, D. Nguyen, A. Papadakis, L. Whitfield). No junior names.
- Transitions: scenes cross-fade into each other (`sceneFade`), and screens inside a scene slide-push (`beat`). There are no hard cuts.
- Music: one 121 second piano and acoustic bed (about 95 bpm as generated), slowed about 12% to cover 137.5 seconds, so it plays at about 84 bpm. It fades in over 2s and out over the last 3s, at volume 0.35.

## Scene list at a glance

| # | Scene | Section runs | Club |
|---|---|---|---|
| 1 | Hook | 0:00 to 0:09.6 | All seven |
| 2 | Sign up | 0:09 to 0:21.6 | Gisborne |
| 3 | First sync, then Sync Now | 0:21 to 0:35.6 | Applecross |
| 4 | Bring in your history (4a to 4d) | 0:35 to 0:57.6 | Sunbury, Bannockburn, Sunbury, Bannockburn |
| 5 | Merge duplicates | 0:57 to 1:09.6 | Leeming Spartans |
| 6 | Your site fills in (6a to 6d) | 1:09 to 1:29.6 | Applecross, Kalamunda, Scarborough |
| 7 | StatLab | 1:29 to 1:39.6 | Applecross |
| 8 | And more | 1:39 to 1:47.5 | none |
| 9 | The other modules | 1:47.5 to 2:06.5 | none |
| 10 | Call to action | 2:06.5 to 2:17.5 | Gisborne (typed in the search box) |

Sections overlap by about 0.6s for the cross-fade. Times below are on the master's clock.

## Scene by scene

### 1. Hook (0:00 to 0:09.6)

- **Screen:** brand header "For grassroots cricket clubs". A large search box at the top with the placeholder "Search your club".
- **Motion:**
  - 0:00.4 onward: a club name types into the box (0.32s each), and a crest card (tile plus club name) pops up below with a back-ease bounce 0.3s later. One club every 0.62s, in this order: Applecross, Bannockburn, Scarborough, Leeming Spartans, Gisborne, Sunbury, Kalamunda.
  - The cards fill a grid of four across the top row and three across the second row. All seven are settled by about 0:05.
  - 0:04.9: the typed text clears and the placeholder fades back in.
- **Hold:** the settled grid stays still from about 0:05 to the end of the scene.
- **Captions:**
  - 0:01.0 to 0:05.6 "Your club's whole cricket history. Kept for you."
  - 0:06.0 to 0:09.6 "Start at betterat.cricket/trial"

### 2. Sign up (0:09 to 0:21.6), Gisborne

- **Screen A (0:09.5 to 0:13.5):** the Gisborne crest tile scales up from small and rises into the centre, with "Gisborne Cricket Club" under it. It then shrinks and fades away (from 0:13.5).
- **Screen B (from 0:13.6):** a sign-up panel with a three-step bar (1 Details, 2 Email code, 3 Terms).
  - 0:14.0 step 1 dot turns green. The Club field types "Gisborne Cricket Club" and the Email field types "secretary@yourclub.com.au".
  - 0:14.6 the progress bar fills to halfway. 0:14.9 onward: four code boxes fill one at a time (4, 8, 2, 7, 0.3s apart) and each border turns green. 0:16.1 a green tick circle pops beside them.
  - 0:17.6 the bar fills the rest of the way, step 3 turns green, and the "I agree to the terms" box ticks (the tick draws itself).
  - 0:18.0 a "about 3 minutes" clock chip pops in.
- **Hold:** the finished form stays until the scene fades.
- **Captions:**
  - 0:10.0 to 0:13.6 "Pick your club."
  - 0:14.0 to 0:17.6 "A few details and a 4-digit email code."
  - 0:18.0 to 0:21.6 "Free trial. No card."

### 3. First sync, then Sync Now (0:21 to 0:35.6), Applecross

- **Screen A, dashboard (0:21.3 to 0:29.5):** header "Dashboard" with the Example club label.
  - A ring fills on its own from 0:21.5 over 2.5s, with a percentage counting 0 to 100 and the label "First sync".
  - Three counters roll up from 0:21.7: Games 412, Players 286, Seasons 38.
  - 0:25.5 a "Cricket Australia" chip rises in. 0:25.8 a green line draws up to the ring, and three glowing dots travel up it (0:26.2 to 0:27.0) and fade as they reach the ring.
  - 0:26.4 text fades in: "Seasons, scorecards and players arrive from your club's past."
- **Screen B, Data Sync (0:29.6 onward):** the dashboard slides out and a "Data Sync" screen slides in with a green "Sync Now" button.
  - 0:30.3 the button is pressed (scale down and bounce back).
  - 0:30.8 a new game card ("Round 9 · 1st XI, Won by 4 wickets", with a green "New" chip) slides in at the top and the two older games shift down.
  - 0:31.4 on the "Most runs · 2024/25" list, R. Singh moves up one place past T. Okafor and the figure counts 371 to 395.
- **Hold:** the final Data Sync screen stays still from about 0:32.3 to the end.
- **Captions:**
  - 0:22.0 to 0:25.6 "Your first sync starts on its own."
  - 0:26.0 to 0:29.8 "It pulls your club's history from Cricket Australia." (text only, no Cricket Australia logo)
  - 0:30.0 to 0:35.4 "Later, one click on Sync Now brings in the latest games."

### 4. Bring in your history (0:35 to 0:57.6)

Four screens, each slid in with a push.

**4a. Spreadsheet, Sunbury (0:35 to 0:40.5)**
- Header "Import a spreadsheet". A light spreadsheet drops in from above with a bounce (0:35.1). Columns: Name, Yr, R, Inn. Rows such as "Jack Mercer, 2011, 402, 14".
- 0:35.8 three green-edged chips appear above it: Player, Season, Runs. 0:36.2 curved lines draw from each chip down to the matching column header. 0:36.8 onward the three matched headers light up green and the chips turn green, one after another.
- **Caption:** 0:35.6 to 0:40.4 "Drop in any spreadsheet. Match the columns once."

**4b. Scorecard photo, Bannockburn (0:40.5 to 0:46.0)**
- Header "Scorecard photo". A paper page, tilted about 5 degrees, with ruled lines, "1st Innings" underlined and handwriting-style names and scribbles. Beside it a dark "Scorecard" panel.
- 0:41.0 a green scan line sweeps down the paper over 1.4s. From 0:41.3 the scorecard rows fill in one by one (Mercer 34, Okafor 12, Singh 57, Nguyen 8, Whitfield 21, Papadakis 40). 0:42.8 a green tick and "Reviewed" pop in.
- **Caption:** 0:41.0 to 0:45.8 "Photograph an old scorecard. It reads it, you check it."

**4c. Partnership records, Sunbury (0:46.0 to 0:51.0)**
- Header "Partnership records". A CSV file icon drops in with a slight rotation (0:46.2). A table below grows four partnership bars (0:46.9, 0.18s apart) with counters: 1st J. Mercer & T. Okafor 187, 2nd R. Singh & D. Nguyen 164, 3rd A. Papadakis & L. Whitfield 142, 4th T. Okafor & R. Singh 118.
- **Caption:** 0:46.5 to 0:50.7 "Add partnership records from a file."

**4d. Awards, Bannockburn (0:51.0 to 0:57.6)**
- Header "Awards and honours". Three dropdown rows highlight in turn from 0:51.2, 0.45s apart: Award "Club Champion", Player "L. Whitfield", Season "2023/24".
- 0:52.8 a gold honour-board plaque fades up: "HONOUR BOARD, CLUB CHAMPION" with 2021/22 R. Singh, 2022/23 T. Okafor and a highlighted new line "2023/24, L. Whitfield".
- **Caption:** 0:51.5 to 0:56.7 "Add club awards and honours."

### 5. Merge duplicates (0:57 to 1:09.6), Leeming Spartans

- **Screen:** header "Merge duplicates".
- **Motion:**
  - 0:57.2 two player cards slide in from the sides: "Dan Nguyen" and "Daniel Nguyen" (initials DN).
  - 0:57.9 they slide toward each other. 0:58.6 they fade and a single green-edged card "Daniel Nguyen, One player" pops in.
  - 0:58.8 a panel appears: "12 pairs found", with two chips: "Exact matches 9" and "Check these 3" (amber), and a "Merge exact matches" button.
  - 1:01.3 the button is pressed. 1:01.6 over 1s the exact-match count counts down 9 to 0 and "12 pairs found" counts down to 3.
  - 1:05.3 a "Check these" list fades in with three pairs, each with a "Review" chip: Tom Okafor and Thomas Okafor, Raj Singh and R Singh, Lachie Whitfield and Lachlan Whitfield. The first has an amber outline.
- **Captions:**
  - 0:57.6 to 1:01.4 "Same player, spelled two ways? We find the pairs."
  - 1:01.8 to 1:05.4 "Merge the exact matches in one click."
  - 1:05.8 to 1:09.4 "Check the rest pair by pair."

### 6. Your site fills in (1:09 to 1:29.6)

**6 intro (1:09 to 1:13.1):** a simple site frame with a nav (Leaderboards, Records, Players, StatLab) and four placeholder cards whose bars grow in with a stagger (1:09.2 and 1:09.4). **Caption:** 1:09.6 to 1:13.2 "Now it all fills in."

**6a. Leaderboards, Applecross (1:13.1 to 1:18.5)**
- Header "Leaderboards". "Most runs" with two chips, "2023/24" and "1st XI". Six horizontal bars (Mercer 512, Okafor 468, Singh 431, Nguyen 377, Papadakis 340, Whitfield 296) slide from scrambled slots into rank order while growing (1:13.3 to 1:14.4).
- 1:14.8 the chips pop and change to "2024/25" and "2nd XI". 1:15.1 the rows reshuffle and the bars resize: L. Whitfield 488 comes to the top, then D. Nguyen 455, J. Mercer 402, A. Papadakis 361, R. Singh 322, T. Okafor 280.
- **Caption:** 1:13.6 to 1:17.9 "Leaderboards for every category."

**6b. Records, Kalamunda (1:18.5 to 1:23.4)**
- Header "Records", title "All-time club records". Three record rows arrive (1:18.7): Highest score 167* J. Mercer 2019/20, Best bowling 7/23 T. Okafor 2016/17, Longest partnership 211 R. Singh & A. Papadakis 2021/22.
- 1:20.0 the rows shift down to make room. 1:20.1 a new row drops in at the top with a green border: Highest score 174, D. Nguyen, 2024/25. 1:20.7 a "New record" flag pops on it, and the old highest score dims.
- **Caption:** 1:19.0 to 1:22.9 "All-time records, flagged the week they're set."

**6c. Player profile, Scarborough (1:23.4 to 1:27.8)**
- Header "Player profile". Card for L. Whitfield, "Career". Counters roll up from 1:23.6: Matches 142, Runs 3,412, Wickets 87. 1:23.9 a "Runs by season" line curve draws itself over 1.1s. 1:24.9 three milestone badges pop in turn: 50, 100, 5-for.
- **Caption:** 1:23.9 to 1:27.7 "A career page for every player."

**6d. Devices (1:27.8 to 1:29.6):** brand header "On every screen". A laptop frame shows a leaderboard and a phone frame shows L. Whitfield's profile card. No caption on this screen, and it holds.

### 7. StatLab (1:29 to 1:39.6), Applecross

- **Screen:** header "StatLab". A report list on the left, a results table on the right.
- **Motion:**
  - 1:29.1 the report list wipes open top to bottom, with items staggering in (Batting group, Most runs, Highest scores, Best averages, then a Bowling group with Most wickets, Best figures, then Fielding, and so on).
  - 1:30.3 "Most runs" is highlighted. 1:30.6 the table slides in with two filter chips ("All seasons", plus a second chip) and rows filling in (J. Mercer 512, L. Whitfield 488, T. Okafor 468, D. Nguyen 455, R. Singh 431, ...).
  - 1:33.8 the chips change to "2024/25" and "1st XI". 1:34.2 the old rows slide out left and 1:34.5 a shorter table of four rows slides in (L. Whitfield 488, D. Nguyen 455, J. Mercer 402, A. Papadakis 361).
- **Captions:**
  - 1:29.6 to 1:33.4 "StatLab: 200+ ready-made reports."
  - 1:34.3 to 1:38.9 "Or build your own with filters."

### 8. And more (1:39 to 1:47.5)

- **Screen:** brand header "And more". A 2 x 2 grid of four tiles. Each tile lights up its border in green when it is its turn, with a simple line-drawn icon that animates. One tile every 2.05s from 1:39.1.
  1. A scorecard sheet with lines that draw in. Caption 1:39.5 to 1:41.4 "Every scorecard, kept for good."
  2. An open book. Caption 1:41.5 to 1:43.4 "A season annual that fills itself."
  3. A gold trophy on a board. Caption 1:43.5 to 1:45.4 "Honour boards and premierships."
  4. A player card that flips from edge-on. Caption 1:45.5 to 1:48.0 "A card for every player."
- These four captions are about 2 seconds each, shorter than the 3.5 second rule, as the brief allowed for this scene.

### 9. The other modules (1:47.5 to 2:06.5)

- **Screen:** a soft radial glow fills the background, tinted to the module in focus. The BetterStats tile (green) sits in the centre.
- **Motion:**
  - 1:47.7 the BetterStats logo pops in with the name "BetterStats" and a green glow.
  - The other five arrive around it, one every 2.5s from 1:51.3, each popping in with its logo and name in its own colour while the glow cross-fades to that colour: BetterSelect (blue) at 1:51.3, BetterSocials (pink) at 1:53.8, BetterAdmin (amber) at 1:56.3, BetterIQ (purple) at 1:58.8, BetterFantasy (cyan) at 2:01.3.
  - 2:04.6 all six slide and shrink into a single evenly spaced row over 1s, and the glow goes back to green.
- **Hold:** the six-logo row holds until the scene fades at about 2:06.5.
- **Captions:**
  - 1:48.2 to 1:51.6 "Once Stats is loaded, add what you need."
  - 1:51.8 to 1:54.2 "Availability and team selection."
  - 1:54.3 to 1:56.7 "Posts that fill from your match data."
  - 1:56.8 to 1:59.2 "Fees, email, rosters and meetings."
  - 1:59.3 to 2:01.7 "Know the opposition."
  - 2:01.8 to 2:04.6 "A club fantasy comp."

### 10. Call to action (2:06.5 to 2:17.5)

- **Screen:** the search box returns. There is no button on this card in the master.
- **Motion:**
  - 2:06.8 the search box rises in. 2:07.3 it types "Gisborne Cricket Club" over 1.2s.
  - 2:07.6 the wordmark "BetterCricket" ("Better" white, "Cricket" green) drops in above it.
  - 2:13.3 the search box fades and shrinks. 2:13.5 a large "betterat.cricket/trial" ("/trial" in green) scales in with a green underline that draws across (2:13.8).
- **Hold:** the final URL frame holds still to the last frame, about 3.5 seconds.
- **Captions:**
  - 2:07.4 to 2:10.6 "Type your club's name."
  - 2:10.8 to 2:13.6 "Free trial. No card."
  - 2:13.8 to 2:17.5 "betterat.cricket/trial" (stays to the end)

## Where the build differs from the brief

| Brief | Master |
|---|---|
| About 1:55 (script 2:01) | 2:17.5. The agent kept the pacing rules (2 second holds, captions up at least 3.5 seconds) over the listed times. Scenes 6 to 10 start later than the brief's targets. |
| 4c and 4d clubs not named | Sunbury for 4c and Bannockburn for 4d (the agent's choice) |
| Merge counter "drops to 0" | "12 pairs found" drops to 3, and the exact-match chip drops 9 to 0, because three pairs stay for review |
| Music 90 to 100 bpm | About 84 bpm. One 121 second track was generated and slowed about 12% to fill the length. |
| End card | Wordmark, typed club name and the URL. No button or chips. (The ad cut adds a button and chips.) |

## Open items that matter before any of this runs as an ad

- **"200+ ready-made reports":** matches the site copy, but the code lists about 162 presets. Check the number first.
- **Sunbury crest:** Jack has not confirmed the supplied image is the club's official crest (it reads as a redrawn version).
- **"Your first sync starts on its own":** confirmed in code (`_onboard_club_core` starts the first sync), but nobody has watched a live trial do it.
- **Written permission for crests:** Jack said he would supply the logos and OK all seven clubs. Keep that on record before the ad runs.
- **The ad cut** (request `b2dddf39-216a-4d6a-8338-d9f9011cc6f6`) is waiting for Jack to press Generate.

## Changing a scene

1. Pick the section (`#s1` to `#s10`) and its `sceneN()` function. Timings are absolute seconds on the master's clock.
2. Captions are the `CUES` array at the top of the script. A caption's length must keep 3 words a second.
3. Ask for the change through `generate_html_video` with the `cloud_project_id`, naming the scene and the exact new behaviour. A revision renders again and the earlier render stays in the library.
