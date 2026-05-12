# BetterStats — Build Guide (non-techy edition)

This folder is the **production-ready code** for your redesigned BetterStats. Everything
under `build/frontend/` mirrors your repo's `frontend/` directory — copy file-for-file.

If anything below sounds like jargon, paste it into Claude Code and ask it to
"do this for me in the repo."

---

## What's in the box

```
build/
├── BUILD_GUIDE.md
├── MIGRATION.md
└── frontend/
    ├── tailwind.config.js                  ← additions to merge into yours
    └── src/
        ├── styles/theme.css                ← CSS variables + base styles
        ├── lib/
        │   ├── presskit.jsx                ← shared design components
        │   └── mockData.js                 ← fallback data so pages render before sync
        ├── components/
        │   ├── PressNav.jsx                ← new top bar
        │   └── admin/
        │       └── AdminLayout.jsx         ← admin chrome
        └── pages/
            ├── Dashboard.jsx               ← Club Dashboard
            ├── PlayerProfile.jsx           ← Player Profile
            ├── MatchScorecard.jsx          ← Match scorecard + worm chart
            ├── PlayerComparison.jsx        ← Head-to-head compare
            ├── Leaderboard.jsx             ← Club ladder
            ├── StatLab.jsx                 ← Deep-dive splits + wagon wheel
            ├── Records.jsx                 ← Hall of records
            ├── admin/
            │   ├── AdminSync.jsx           ← Play-Cricket sync console
            │   └── AdminPlayers.jsx        ← Roster CRUD
            └── marketing/
                ├── Landing.jsx             ← Marketing home
                ├── Features.jsx
                └── Pricing.jsx
```

---

## Step 1 — Fonts

Paste this into `frontend/index.html` inside the `<head>` tag:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
```

## Step 2 — Tailwind config

Merge the contents of `build/frontend/tailwind.config.js` into your existing
`frontend/tailwind.config.js`. You're adding a `pb` colour family, font families,
letter-spacing utilities, and a tiny `text-2xs` size.

## Step 3 — Theme CSS

Copy `build/frontend/src/styles/theme.css` → `frontend/src/styles/theme.css`,
then add to `frontend/src/main.jsx` near the top:

```js
import "./styles/theme.css";
```

## Step 4 — Shared library

Copy these as-is to the same paths in your repo:

- `src/lib/presskit.jsx`
- `src/lib/mockData.js`
- `src/components/PressNav.jsx`
- `src/components/admin/AdminLayout.jsx`

## Step 5 — Pages

Each file under `build/frontend/src/pages/` is a **drop-in replacement** for the
file at the same path. Safe migration:

1. Rename your existing file (e.g. `Dashboard.jsx` → `DashboardOld.jsx`).
2. Copy the new file into place.
3. Reload — page renders immediately using mock data.

**To wire real data:** find `// WIRE:` comments at the top of each page. Uncomment
the lines underneath to use your real `api.js` endpoints. `fetchOrMock()` falls
back to mock if any endpoint is empty, so you can wire one at a time.

## Step 6 — Routes (App.jsx)

Add or update these routes:

```jsx
import PressNav         from "./components/PressNav";
import Dashboard        from "./pages/Dashboard";
import PlayerProfile    from "./pages/PlayerProfile";
import MatchScorecard   from "./pages/MatchScorecard";
import PlayerComparison from "./pages/PlayerComparison";
import Leaderboard      from "./pages/Leaderboard";
import StatLab          from "./pages/StatLab";
import Records          from "./pages/Records";
import Landing          from "./pages/marketing/Landing";
import Features         from "./pages/marketing/Features";
import Pricing          from "./pages/marketing/Pricing";
import AdminLayout      from "./components/admin/AdminLayout";
import AdminSync        from "./pages/admin/AdminSync";
import AdminPlayers     from "./pages/admin/AdminPlayers";

<Routes>
  <Route path="/"             element={<><PressNav /><Dashboard /></>} />
  <Route path="/players/:id"  element={<><PressNav /><PlayerProfile /></>} />
  <Route path="/matches/:id"  element={<><PressNav /><MatchScorecard /></>} />
  <Route path="/compare"      element={<><PressNav /><PlayerComparison /></>} />
  <Route path="/leaderboard"  element={<><PressNav /><Leaderboard /></>} />
  <Route path="/stat-lab"     element={<><PressNav /><StatLab /></>} />
  <Route path="/records"      element={<><PressNav /><Records /></>} />
  <Route path="/about"        element={<Landing />} />
  <Route path="/features"     element={<Features />} />
  <Route path="/pricing"      element={<Pricing />} />
  <Route path="/admin" element={<AdminLayout />}>
    <Route index           element={<AdminSync />} />
    <Route path="sync"     element={<AdminSync />} />
    <Route path="players"  element={<AdminPlayers />} />
  </Route>
</Routes>
```

(Wrap PressNav into a layout component once you have more screens — for now,
the `<><PressNav /><Page /></>` pattern keeps things explicit.)

---

## White-labelling (club colours)

The accent colour comes from one CSS variable: `--pb-accent`. Your existing
`useClubTheme` hook needs one line:

```js
document.documentElement.style.setProperty("--pb-accent", club.accent_color);
```

Every accent in the design — buttons, sparklines, progress bars, hot streaks,
the BS logo — recolours instantly.

---

## Mobile

Every page is mobile-first. Tables use `overflow-x-auto` so they stay readable
without breaking layout. The chrome's nav also scrolls horizontally on small
viewports. Test the priority pages at iPhone 14 (390px) and iPad (768px) — they
should both look clean.

If you want to remove anything for mobile, target it with Tailwind's `hidden md:block`.

---

## Going live

1. Land the files on a branch — don't push to main until you've eyeballed each route.
2. Run `npm run dev` and click through every page.
3. White-label colour: set `--pb-accent` for your club; check the entire app recolours.
4. Wire real data one page at a time using the `// WIRE:` comments.
5. Deploy. Tell players to refresh.

Any issues — screenshot it back and we'll sort it.
