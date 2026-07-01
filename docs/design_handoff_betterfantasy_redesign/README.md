# Handoff: BetterFantasyCricket — FPL-style member redesign

## Overview
A full redesign of the **BetterFantasyCricket** member-facing experience for Applecross
Cricket Club (white-labelled per club). It reskins the existing public fantasy app
(`/fantasy/:token`) in a Fantasy-Premier-League-inspired language — dark **or** light
surfaces, a single pastel-indigo brand accent, a soft animated "aurora" glow on social
surfaces, photo-led player rows (club-crest fallback), and big condensed sporty numbers.

It covers every screen the current app has **plus** a set of new screens we want built
out: player profile, compare, stats explorer, dedicated transfers, chips, fixtures,
league detail, head-to-head, notifications, profile/settings, how-to-play, onboarding,
live gameweek, and shareable social cards.

The design lives in one HTML file as a **design board** — labelled frames laid out in
sections (mobile screens, desktop layouts, light-mode, shareables). It is a reference,
not a component you wire up frame-by-frame.

---

## About the design files
`BetterFantasyCricket.dc.html` is a **design reference created in HTML** — a prototype
showing intended look and behaviour. It is **not production code to copy directly**.

The task is to **recreate these designs inside the existing BetterStats frontend**
(`frontend/`, React + Vite + Tailwind, React Router), using its established patterns:
the `api` lib (`src/lib/api.js`), the `--pb-*` CSS-variable theme system
(`src/lib/theme.js` → `buildThemeCss`), and the existing `PublicFantasy.jsx` page as the
starting point. Lift exact hex/spacing/type values from this doc; build the components
in React, not as raw HTML.

> Open the HTML to see it run: it depends on the sibling `support.js` (included). Toggle
> the design's own tweaks (Theme, Brand colour, Player photos, GW locked) to see states.

---

## Fidelity
**High-fidelity (hifi).** Final colours, typography, spacing, radii, and layout.
Recreate pixel-faithfully with the codebase's libraries. **Note:** the screens are
high-fidelity *static states* — interactions (clicks, fetches, polling) are described
here but were **not** wired in the prototype. Build the behaviour from the
"Interactions", "State", and "Data / API" sections below.

---

## Where it plugs in (current code)
- **Page:** `frontend/src/pages/PublicFantasy.jsx`, route `/fantasy/:token`. The redesign
  replaces its UI. Keep the phase machine (`loading | dead | auth | app`) and the view
  switcher; restyle and expand the view set.
- **API:** `frontend/src/lib/api.js` — the `fan*` methods (see mapping table).
- **Theme:** `frontend/src/lib/theme.js` (`BRAND`, `resolveTheme`, `buildThemeCss`) +
  `src/index.css`. Already emits `[data-theme="dark"]` / `[data-theme="light"]` token
  blocks — the redesign leans on exactly this; we mainly add a **member-facing toggle**.
- **Module brand:** `frontend/src/lib/moduleBrand.js` — `fantasy` accent is
  `#06B6D4` (cyan). (This redesign changed it to `#8C82F0`, later reverted to the
  cyan so it matches the icon. See the note under Design tokens.)

---

## Design tokens

> **Update (Jul 2026): the accent was returned to the icon's cyan.** This redesign
> switched the brand accent to periwinkle `#8C82F0`, but the module icon
> (`betterfantasy.svg`) stayed cyan, so the accent and the mark never matched.
> `moduleBrand.fantasy` and the member-app default (`pages/fantasy/theme.js`) are now
> `#06B6D4` (cyan-500), the middle of the icon's `#22d3ee → #0891b2` gradient. Read the
> `#8C82F0` values below as historical.

### Brand
| Token | Value | Use |
|---|---|---|
| `--pb-accent` (brand) | **`#8C82F0`** pastel periwinkle | Primary accent. Per-club override still wins (club `accent_color`). Update `moduleBrand.fantasy.accent` to this. |
| `--accent-strong` (dark) | `color-mix(in srgb, var(--pb-accent) 74%, #ffffff)` | Accent text on dark tints (lighter, legible) |
| `--accent-strong` (light) | `color-mix(in srgb, var(--pb-accent) 58%, #15132a)` | Accent text on light tints (darker, legible) |

The "FPL gradient" rule under every header uses fixed brights and the accent:
`linear-gradient(90deg, var(--pb-accent), #22D3EE 50%, #00E58E 78%, #EC4899)`.

### Surface palette (themeable)
| Token | Dark | Light |
|---|---|---|
| `--bg` | `#0a0d14` | `#f4f5f9` |
| `--surface` | `#10141d` | `#ffffff` |
| `--surface2` | `#161b27` | `#eef0f5` |
| `--hairline` | `#1d2331` | `#e6e8f0` |
| `--hairline2` | `#262d3d` | `#d6d9e4` |
| `--text` | `#e6e8ef` | `#1b1e2b` |
| `--dim` | `#8a90a2` | `#5b6072` |
| `--faint` | `#5b6072` | `#9298ab` |
| `--faintest` | `#3a3f50` | `#c2c6d2` |
| `--grad-top` (header) | `#171c2a` | `#edeef7` |
| `--bench` | `#0c0f17` | `#eef0f5` |
| `--ink` (text on accent) | `#0a0d14` | `#16132a` |
| `--aurora` (glow opacity) | `0.55` | `0.42` |

### Semantic (shared both themes)
| Token | Value | Use |
|---|---|---|
| positive / green | `#16c784` | Up arrows, high score, "in the bank" |
| negative / red | `#ef5b5b` | Down arrows, point hits, sell, LIVE dot |
| amber | `#f5b542` | Misc highlight (e.g. top scorer) |

### Typography
- **Display / numbers:** `'Saira Condensed'` (Google) weights 500–800. Used for the
  wordmark, screen titles, big point numbers, ranks, stat values. Numbers use
  `font-variant-numeric: tabular-nums`.
- **UI / body:** `'Hanken Grotesk'` (Google) weights 400–800. Labels, names, copy.
- Uppercase + letter-spacing (`.1em`–`.22em`) on labels and titles.
- Min sizes: stat-label ~8.5–9px uppercase; body ~12–13.5px; big hero numbers 46–110px.

### Radii / shadow / spacing
- Radii: phone frame `30px`, desktop frame `18px`, cards `12–14px`, pills/buttons
  `9–11px`, avatars `50%`, crest tile `11–15px`.
- Card frame shadow (dark): `0 1px 3px rgba(0,0,0,.14), 0 22px 60px -22px rgba(0,0,0,.6)`;
  (light) `0 1px 3px rgba(80,80,120,.12), 0 22px 60px -24px rgba(40,40,90,.28)`. Tokenised
  as `--frame-shadow`.
- Section/screen padding ~18px mobile, ~26px desktop. Card inner padding 9–15px.
- Mobile frame width **390px**; desktop frames **1180–1240px**.

### Aurora (soft glow) — pure CSS, **new**
Blurred radial-gradient "blobs" in the brand palette drifting slowly behind social
surfaces (Sign in, headers, Player profile, share cards, onboarding, live).
- A `position:absolute` layer, `filter: blur(44–50px)`, `opacity: var(--aurora)`,
  `pointer-events:none`, behind `position:relative` content.
- 2–4 child `.aurora-blob` divs, each a `radial-gradient(circle, <colour>, transparent ~66%)`
  using `var(--pb-accent)`, `#22D3EE`, `#00E58E`, `#EC4899`.
- Keyframes `auroraA–D` translate/scale (`translate(±10–22%, ±10–18%) scale(.9–1.3)`),
  16–24s, `ease-in-out infinite alternate`.
- **Must honour `@media (prefers-reduced-motion: reduce)` → `animation:none`.**
- In React, build as a small `<Aurora />` component (CSS only); don't drive from JS.

---

## Theme system (how light/dark works)
1. Tokens above are defined under `[data-theme="dark"]` and `[data-theme="light"]`
   selectors (already the pattern in `theme.js` / `index.css`).
2. The app root sets `data-theme` and the accent: `style="--pb-accent: <accent>"`,
   `data-theme="dark|light"`.
3. Everything else uses `var(--token)` (with a literal fallback for first paint, e.g.
   `var(--pb-accent, #8C82F0)`).
4. **New:** a member-level theme preference (Dark / Light / Auto) persisted to
   `localStorage` and applied on load; surfaced in **Profile & settings**. "Auto" follows
   `prefers-color-scheme`. The club's `accent_color` (if set) still overrides `--pb-accent`.

---

## Data / API mapping

### Already exists in `api.js` (reuse)
| Screen | Method(s) |
|---|---|
| Auth | `fanLanding`, `fanRegister`, `fanLogin`, `fanLogout`, `fanMe` |
| My Team / Pick | `fanMe` (manager, squad, round), `fanPool` (players + rules), `fanSaveSquad` |
| Transfers / Captain / Chips | `fanTransfer`, `fanSetCaptain`, `fanChip` |
| Points | `fanRound(token, n)` (round breakdown + `rounds` list + stats) |
| Ladder | `fanLadder` |
| Leagues | `fanLeagues`, `fanCreateLeague`, `fanJoinLeague` |
| Draft | `fanDraftLeagues`, `fanDraftState`, `fanDraftLadder`, `fanJoinDraft`, `fanDraftPick` |

Existing data shapes (from `PublicFantasy.jsx`): `club {name, logo_url, accent_color,
primary_color}`, `season {name, status, rules}`, `rules {role_quota{keeper,batter,
allrounder,bowler}, budget, squad_size}`, `squad {total_points, last_round, value,
budget_remaining, free_transfers, players[{player_id,name,role,is_captain,is_vice_captain,
purchase_price}]}`, pool player `{player_id,name,role,price,total_points}`, ladder row
`{rank, team_name, manager, points}`.

### NEW — needs building (backend + api.js + UI)
| Feature | What's missing | Suggested endpoint / field |
|---|---|---|
| **Player photos** | Pool/squad players have no image. Design uses player photo, **club logo as fallback**. | Add `photo_url` to player payloads (source from the main app's PlayerProfile photo). UI: avatar = photo → else crest. |
| **Player profile** | No per-player detail endpoint. | `fanPlayer(token, playerId)` → `{name, role, price, selected_pct, form, total, season_stats[], last5[{round,points}], fixtures[{round,opp,difficulty}]}`. Difficulty (`easy|even|hard`) is new. |
| **Stats explorer** | Pool lacks `selected_pct`, `form`, `team`. | Extend `fanPool` rows with `selected_pct`, `form`, `team`, plus server-side sort/filter params. |
| **Compare** | — | Client-side from two `fanPlayer` results; no new endpoint strictly needed. |
| **Chips** | `fanChip` only handles `wildcard` + `triple_captain`. Design adds **Bench Boost** & **Free Hit**, and shows per-chip state (available/armed/used). | Extend chip enum; return `chips:[{key,status}]` on `fanMe`. |
| **Fixtures / rounds** | `fanRound` returns a `rounds` list, but no lock times / fixture difficulty / per-round status surfaced together. | Add `fanRounds(token)` → `[{number, lock_at, status:'live|upcoming|scored', my_points, captain}]`. |
| **Head-to-head** | Classic-league H2H matchup view doesn't exist (only draft H2H ladder). | `fanH2H(token, leagueId, round)` → `{me, opp, rows[{role, mine, theirs}]}`. |
| **League detail** | `fanLeagues` returns standings only; design has Standings / Matchups / About tabs + movement arrows. | `fanLeague(token, leagueId)` → standings with `rank_delta`, plus matchups + meta. |
| **Notifications** | No member notification feed (the admin app's NotificationBell is separate). | `fanNotifications(token)` + read state; deadline reminders, price changes, league invites, rank moves. Consider push/email for deadline reminders. |
| **Profile & settings** | Rename team exists via `fanSaveSquad.team_name`; **change PIN**, **notification prefs**, **theme pref** are new. | `fanUpdateProfile(token, {team_name, pin})`, `fanPrefs(token, {...})`; theme pref can be local-only. |
| **Live gameweek** | No live polling; `fanRound` is post-scoring. | `fanLive(token)` polled (~30–60s) during a round → live points + provisional rank. |
| **Share cards** | No social-card generation for fantasy. | Render GW-result + story cards (see the `ShareCard.jsx` pattern already used for player cards) to PNG; web-share / download. |
| **Member light/dark toggle** | Theme tokens exist but no member control. | Persisted pref (see Theme system). |
| **Rank movement arrows** | Ladder/league rows show ▲/▼ deltas. | Need `rank_delta` (vs previous round) on ladder/league rows. |
| **Onboarding steps** | Empty-state exists implicitly (no squad → pick). | Stepped UI; no new data — derive from squad/captain/league presence. |

---

## Screens / Views
Grouped as in the board. All share the chrome: faux status bar (mobile), header
(crest + "Applecross CC" + season) with the FPL gradient rule, accent CSS var, and the
token palette. Player row pattern (reused everywhere): avatar (photo or `ACC` crest
fallback) · name (+ `C`/`V` badge) · sub `Role · $price` · big GW points.

**Squad rules (in copy):** 12 players, **$100** budget, quota **Batter 4 · All-rounder 3
· Wicketkeeper 1 · Bowler 4**, captain scores ×2. **Role display order = Batters,
All-rounders, Wicketkeeper, Bowlers** (keeper sits third — it's a single slot).

### Auth — Register / Sign in
Centred club crest + wordmark over an aurora glow; segmented **New player / Sign in**;
inputs (display name, email, PIN); accent primary button; reassurance copy. → `fanRegister`/`fanLogin`.

### My Team (mobile)
Header → nav pills (My Team·Points·Pick·Ladder·Leagues·Draft) → manager row (team
gradient tile, name, overall rank) → 6 stat tiles (Total, GW pts, Overall rank, Squad
value, In the bank, Free transfers) → round-lock pill → role groups with player rows.
Subtle aurora behind the header. → `fanMe`.

### Pick / Edit squad (mobile)
Build header → bank/picked/spent tiles → role filter pills (with `have/quota`) →
search + sort → pool list (picked = accent + ✓, open = `+`) → save CTA. → `fanPool`, `fanSaveSquad`.

### Points (mobile)
Round selector → huge round score + Avg/High/Hit tiles → lineup rows (captain doubled,
bench dashed + dimmed). → `fanRound`.

### Ladder (mobile)
Club ladder; column head (#, move, Team, GW, Total); rows with ▲/▼/– deltas; your row
accent-highlighted with `YOU` badge; `· · ·` jump to your position. → `fanLadder` (+`rank_delta`).

### Leagues (mobile)
Create (name → Create) + Join (code → Join) blocks; league card with code chip and a
mini standings table (your row highlighted). → `fanLeagues`, `fanCreateLeague`, `fanJoinLeague`.

### Draft (mobile)
"On the clock" banner (accent, pulsing dot, countdown, "still need…"); best-available
list with Draft buttons; recent-picks feed. → `fanDraft*`.

### Light mode (showcase)
Sign in + Ladder rendered with `data-theme="light"` — proves the token swap.

### Shareable (social) — **new**
- **GW result (square, 430×430):** aurora, crest, "Gameweek 7", huge 86, ▲ rank jump,
  captain-of-the-week glass card, footer URL + "beat 71% of the club". Share / Save CTAs.
- **Recruit-a-mate (story, 300×533):** aurora, "Think you know cricket?", join-code block
  (`7KQ2`), "Play free →", club URL.
Render to PNG for web-share/download.

### Player & data — **new**
- **Player profile (mobile):** back row → hero (avatar, name, role/club, price·form·owned
  chips) → 6 stat tiles → **Last-5 form** mini bar chart (accent bars; bar height from
  data) → upcoming fixtures with Easy/Even/Hard difficulty pills → "Transfer in" CTA.
- **Compare (mobile):** two avatars + VS; stat rows where the leader's side is
  accent-filled (A) / cyan-filled (B), loser side neutral.
- **Stats explorer (desktop):** toolbar (role pills All/BAT/BWL/AR/WK, search, sort) →
  table: Player · Role · Team · Price · Sel% · GW · Total. Sortable.

### Manage — **new (mostly)**
- **Transfers (mobile + desktop):** Free/Bank/Cost tiles; **Out → In** swap cards; shortlist
  by role; confirm. Desktop = squad list (left, "Sell") + full pool table (right, `+`).
  → `fanTransfer`.
- **Chips (mobile):** card per chip with description + state. Armed = accent w/ pulsing dot
  + "Cancel"; Available = "Play <chip>"; Used = dimmed. (Bench Boost & Free Hit new.)
- **Fixtures (mobile):** round list; LIVE round = accent card + red LIVE tag; upcoming =
  plain; scored = dimmed with points. → `fanRounds`.

### Social & H2H — **new**
- **League detail (mobile):** header (crest, name, members, code chip) + Standings/Matchups/
  About tabs; full standings with deltas; Invite/Leave. → `fanLeague`.
- **Head-to-head (mobile):** Round title; two teams + big scores; per-line comparison
  (Captain / Top batter / Top bowler / Bench) with the winning side tinted. → `fanH2H`.
- **Notifications (mobile):** "Mark all read"; rows with a coloured glyph badge
  (accent `!`, green `▲`, amber `★`, plain `+`), title, body, unread dot. → `fanNotifications`.

### Account & help — **new (mostly)**
- **Profile & settings (mobile):** manager card; Appearance segmented (Dark/Light/Auto);
  Notifications toggles (deadline reminders, price alerts, league chat); Account rows
  (Rename team, Change PIN, Sign out — red).
- **How to play / scoring (mobile):** rules summary + points table (Run +1, Six +2, 50 +8,
  100 +16, Wicket +12, Maiden +4, Catch/Stumping +4, Run-out +6, Duck −4 — confirm against
  real scoring config in season rules).
- **Onboarding / empty state (mobile):** aurora welcome; 3 steps (Build squad → Name
  captain → Join clubhouse) with step 1 active; "Build my squad" CTA.

### Live gameweek — **new**
Red LIVE dot + "Round 7" + "3 playing now"; big live total + provisional rank ▲; lineup
rows (bench dimmed). Poll `fanLive`.

### Desktop layouts (use the width)
- **Dashboard / team sheet (1240px):** top bar + nav + 6-tile stat ribbon + **roles as
  horizontal rows** (team-sheet cards; the single keeper sits compactly in its own row) +
  right rail (This-round/captain/chips + mini-league).
- **Transfers (1240px):** squad list (left, 380px) + player-pool table (right) with filters.
- **Points (1240px):** big score header + lineup table (left) + stats rail (Avg/High/Hit,
  captain-of-week, chip played).
Also a compact 2-column **My Team** desktop in the responsive section.

---

## Interactions & behaviour
- **Nav pills** switch views within `PublicFantasy` (keep the existing local `view` state).
- **Pick/Transfers:** enforce budget, role quota, squad size; one captain + one vice;
  transfer cost/hits; disable invalid picks (existing logic in `Builder`/`MyTeam`).
- **Captain/Vice:** single of each; tap to set (`fanSetCaptain`).
- **Chips:** confirm before arming; reflect available/armed/used.
- **Theme toggle:** instant; persist to `localStorage`; "Auto" follows OS.
- **Aurora:** ambient loop; disabled under reduced-motion.
- **Live:** poll while a round is in-progress; stop when scored.
- **Share cards:** generate PNG → `navigator.share` / download.
- **Responsive:** mobile = single 390px column; desktop = multi-pane (team-sheet rows,
  side-by-side transfer panes, points + rail). Reuse the same data.

## State
- Phase: `loading | dead | auth | app` (existing).
- View: `team | points | pick | ladder | leagues | draft | player | transfers | chips |
  fixtures | league | h2h | notifications | settings | help | live`.
- Theme pref (`dark | light | auto`) — persisted.
- Builder/transfer working state (picked map, captain, budget) — existing pattern.
- Live polling timer; notifications unread count.

## Assets
- **No bitmap assets ship in this bundle.** Avatars are initials/crest placeholders
  standing in for **player photos** (source from the main app's PlayerProfile `photo_url`;
  fall back to the **club logo / `ACC` crest**).
- Fonts: Google Fonts **Saira Condensed** + **Hanken Grotesk** (swap to the codebase's
  font-loading approach).
- No inline SVG illustrations — the only graphics are CSS (aurora, gradient rule, crest tile).
- Module mark: `frontend/src/assets/modules/betterfantasy.svg` (recolour to `#8C82F0` if
  you adopt the new accent).

## Files
- `BetterFantasyCricket.dc.html` — the full design board (all screens). Open with the
  included `support.js`.
- `support.js` — runtime needed to view the HTML (not for production).
- Reference in the existing repo: `frontend/src/pages/PublicFantasy.jsx`,
  `frontend/src/lib/api.js`, `frontend/src/lib/theme.js`,
  `frontend/src/lib/moduleBrand.js`, `frontend/src/index.css`.
