# BetterStats — Marketing Redesign Handoff

This package contains a complete redesign of the BetterStats marketing site, ready to commit to a branch in `thejackbar/BetterStats`.

The new design pivots from the existing utilitarian/admin-feeling pages to a conversion-led modern SaaS marketing site, while keeping all existing SEO content (JSON-LD schemas, FAQ answers, feature copy) intact.

---

## Quick start

### 1. Create a branch

```bash
cd BetterStats
git checkout -b marketing-redesign
```

### 2. Copy files into place

The `production/frontend/src/` folder in this handoff mirrors the destination paths in the BetterStats repo. Copy them across, preserving structure:

```
production/frontend/src/components/MarketingNav.jsx              → frontend/src/components/MarketingNav.jsx          (REPLACE)
production/frontend/src/components/marketing/                    → frontend/src/components/marketing/                (NEW FOLDER)
    ├── Comparison3Way.jsx
    ├── CountUp.jsx
    ├── MarketingFooter.jsx
    ├── Mockups.jsx
    ├── Reveal.jsx
    └── ScreenshotOrMock.jsx
production/frontend/src/data/marketing.js                        → frontend/src/data/marketing.js                    (NEW)
production/frontend/src/pages/marketing/Landing.jsx              → frontend/src/pages/marketing/Landing.jsx          (REPLACE)
production/frontend/src/pages/marketing/Features.jsx             → frontend/src/pages/marketing/Features.jsx         (REPLACE)
production/frontend/src/pages/marketing/Pricing.jsx              → frontend/src/pages/marketing/Pricing.jsx          (REPLACE)
production/frontend/src/pages/marketing/About.jsx                → frontend/src/pages/marketing/About.jsx            (REPLACE)
production/frontend/src/pages/marketing/Contact.jsx              → frontend/src/pages/marketing/Contact.jsx          (REPLACE)
production/frontend/src/pages/marketing/FAQ.jsx                  → frontend/src/pages/marketing/FAQ.jsx              (REPLACE)
```

### 3. Add the new CSS

Open `frontend/src/index.css` and **append** the contents of `production/frontend/src/index.css.additions.css` at the bottom of the file. All new utility classes (`.cta-primary`, `.surface`, `.pill`, `.tabbar`, `.gradient-text`, `.reveal`, etc.) live in there.

No existing classes are modified.

### 4. Run locally

```bash
cd frontend
npm install         # (no new dependencies — uses what's already installed)
npm run dev
```

Visit `localhost:5173` and walk through `/`, `/features`, `/pricing`, `/about`, `/faq`, `/contact`.

### 5. Push & PR

```bash
git add .
git commit -m "Marketing redesign — Landing, Features, Pricing, About, Contact, FAQ"
git push -u origin marketing-redesign
```

Then open a PR. Suggested PR description is at the bottom of this file.

---

## What changed

### Visual / structural
- **New design language**: dark-themed modern SaaS look. Big confident hooks ("Every player. Every season. Kept forever."), gradient text accents, glow effects, generous whitespace.
- **All pages converted** to a hook → CTA → product showcase → social proof structure (was previously a feature grid + CTA).
- **Reusable marketing components** extracted: `MarketingNav`, `MarketingFooter`, `Comparison3Way`, `Reveal`, `CountUp`, mock product surfaces. All in `components/marketing/`.

### New on every page
- Floating dark-glass nav that goes transparent over the hero and solid on scroll
- Consistent `cta-primary` / `cta-secondary` buttons (replaces inline button styles)
- New shared `MarketingFooter` (4-column layout)

### Landing page (`/`)
- Heritage-card hero ("22-season career profile" mockup) instead of the old text-only hero
- Tabbed product showcase (Leaderboards / Player profiles / Yearbook)
- 3-way Comparison table (see below)
- "Player-first commitment" panel — *"If it's important to you, it's important to us"*
- Australian-clubs-only note panel
- 6-card feature grid linking to deeper Features page

### Features page (`/features`)
- Existing 11-section content preserved (high SEO value) but reorganised
- Top 6 sections get hero blocks with alternating layout + product mock
- Remaining 5 sections compressed to a tight 3-column grid
- 3-way Comparison table embedded near the bottom

### Pricing page (`/pricing`)
- Monthly / Annual toggle (live)
- Annual plan highlighted as "★ Most clubs · save $188"
- New **value table** — "What you stop paying for" (custom dev fees, manual stats time, archive project hours, etc.)
- DeepAnalytics teaser preserved
- Inline pricing FAQ
- **Pricing JSON-LD preserved verbatim** for SEO

### About page (`/about`)
- New hook: "The cricket stats platform your club deserves."
- Origin story matches existing copy — no fabrication
- 4 principles preserved ("Cricketers first", "Honest with data", "No tiers, no upsells", "You own the data")
- **Player-first commitment + Australian-only callout** added

### Contact page (`/contact`)
- Cleaner split layout — context on the left, big CTA on the right
- Form opens the existing Google Form (`FORM_URL` constant, single source of truth in `data/marketing.js`)
- Email + based-in + response-time info

### FAQ page (`/faq`)
- **All existing 16 FAQs preserved verbatim** (SEO!)
- Reorganised into 6 categories with sticky sidebar nav: Setup, Data, Product, Customisation, Pricing, Hosting
- **FAQPage JSON-LD preserved**

### Comparison table — new (`/`, `/features#compare`)
- 3-way: PlayHQ vs CricketStatz vs BetterStats
- Sections: Data depth · Surface & presentation · Setup & operations
- Mixed cell types: ✓, ✗, "Partial" pill, "Manual" pill, text values
- "Manual data entry required" row: PlayHQ ✓, CStatz ✓, BetterStats ✗ (we're the only one that doesn't require it)
- **Live Monthly/Annual toggle** on the "Cost for a large club" row
- Below-table reframe: *"You don't have to pick one — BetterStats syncs on top of PlayHQ"*

---

## Screenshots

The site uses a **`ScreenshotOrMock`** wrapper: it tries to load a real screenshot from `/public/marketing/`, and falls back to a polished React mock if the file is missing.

This means **the site looks great from day one** with the mocks, and **auto-upgrades** the moment you drop a real PNG in `/public/marketing/`. No code changes needed.

### Where to put screenshots

Create `frontend/public/marketing/` and drop PNGs with these filenames:

| Filename | Where it appears | What to capture | Suggested dims |
|---|---|---|---|
| `hero-career-card.png` | Landing hero (right side) | A deep player profile — pick a long-career player. Top half of the page: header + 4 career stat tiles + chart + honours. | 1200×1100 |
| `leaderboard.png` | Landing showcase · Leaderboards tab | Season leaderboard with full column set visible. 1st Grade. Sorted by Runs. | 1400×900 |
| `player-profile.png` | Landing showcase · Profiles tab | Full player profile with charts visible. | 1400×1800 (long) |
| `yearbook.png` | Landing showcase · Yearbook tab | Yearbook cover/spread for 2024/25 (or latest complete season). | 900×1200 (portrait) |
| `feature-profile.png` | Features page · Player Profiles | Profile scrolled to show career timeline chart + partnerships section. | 1400×1050 |
| `feature-leaderboard.png` | Features page · Auto sync block | Leaderboard with filter UI / chips visible. | 1400×1050 |
| `feature-yearbook.png` | Features page · Yearbooks | Yearbook interior spread — awards or top performers page. | 900×1100 |
| `feature-match.png` | Features page · Leaderboards | Match scorecard view — 2 innings side-by-side. | 1400×1050 |
| `feature-honours.png` | Features page · Records | All-time records page — partnerships, individual scores. | 1400×1050 |
| `feature-cards.png` | Features page · Stat Cards | A real exported social card (1080×1080). | 1080×1080 |
| `founder.png` | About hero (right side) | Founder photo — clear, well-lit, cricket setting preferred. | 800×1000 |

Priority order: **the four landing-page screenshots are the highest value** (`hero-career-card.png`, `leaderboard.png`, `player-profile.png`, `yearbook.png`). The rest can roll in over time.

---

## Notes for the developer

### Conventions preserved
- React Router `<Link>` for all internal nav (no `<a href="/foo">`)
- Existing `usePageMeta()` hook for `<title>`, `<meta>`, OG tags, JSON-LD
- Existing Tailwind tokens used throughout — `bg-pb-bg`, `text-pb-text`, `text-pb-dim`, `bg-pb-surface`, `border-pb-hairline`, `text-accent`, etc.
- Existing CSS variables — `--pb-bg`, `--pb-accent`, `--pb-hairline` etc. drive everything, so **light theme support works out of the box**
- Existing `FORM_URL` (the Google Form for access requests) is centralised in `data/marketing.js`
- Existing logo asset (`betterstatslogo_white.png`) used in nav and footer

### New files inventory
```
src/components/MarketingNav.jsx              (REPLACES existing)
src/components/marketing/Comparison3Way.jsx
src/components/marketing/CountUp.jsx
src/components/marketing/MarketingFooter.jsx
src/components/marketing/Mockups.jsx
src/components/marketing/Reveal.jsx
src/components/marketing/ScreenshotOrMock.jsx
src/data/marketing.js
src/pages/marketing/Landing.jsx              (REPLACES existing)
src/pages/marketing/Features.jsx             (REPLACES existing)
src/pages/marketing/Pricing.jsx              (REPLACES existing)
src/pages/marketing/About.jsx                (REPLACES existing)
src/pages/marketing/Contact.jsx              (REPLACES existing)
src/pages/marketing/FAQ.jsx                  (REPLACES existing)
```

### Files NOT touched
- `App.jsx`, routing config — no routing changes needed; all existing routes work
- `Terms.jsx`, `Privacy.jsx`, `Blog.jsx`, `BlogPost.jsx` — left as-is
- Admin pages, public club pages, `Navbar.jsx` (the in-app nav)
- `index.css` — only **appends** new utility classes (see step 3)
- `tailwind.config.js` — no changes needed (all my classes use existing tokens)
- `package.json` — no new dependencies

### Dependencies
**None added.** All work uses React, React Router, and Tailwind that's already installed.

---

## Suggested PR description

> ## Marketing site redesign
>
> Refreshes the public marketing pages with a conversion-led design while preserving all existing SEO content (JSON-LD schemas, FAQ answers, the 11-section feature breakdown).
>
> ### What's new
> - **Landing**: heritage-card hero, tabbed product showcase, 3-way comparison (PlayHQ / CricketStatz / BetterStats), player-first commitment + Australia-only callout
> - **Features**: same 11 sections, reorganised — top 6 get visual hero blocks, rest in compact grid
> - **Pricing**: monthly/annual toggle, new "What you stop paying for" value table, JSON-LD preserved
> - **About**: rewritten hook + story, 4 principles preserved, new commitment panel
> - **Contact**: cleaner split layout, prominent form CTA
> - **FAQ**: 16 FAQs reorganised into 6 categories with sticky sidebar nav, JSON-LD preserved
>
> ### Component additions
> - `MarketingNav` (updated) — scroll-aware glass nav, "Compare" replaces "vs. PlayHQ", added "Request access" CTA in nav
> - `MarketingFooter` (new) — 4-column layout
> - `Comparison3Way` (new) — reusable 3-way feature comparison with billing toggle
> - `Mockups.jsx` (new) — polished placeholder mocks until real screenshots arrive
> - `ScreenshotOrMock.jsx` (new) — tries to load a real screenshot from `/public/marketing/`, falls back to mock
>
> ### Screenshots
> The site auto-upgrades when PNGs are dropped in `frontend/public/marketing/` (see filenames in HANDOFF.md).
>
> ### Notes
> - No new dependencies
> - No routing changes
> - All existing tokens (`pb-*`, `accent`) used — light theme works out of the box
> - All marketing JSON-LD preserved (Pricing Product, FAQPage)
> - `index.css` gets appended with new utility classes — no existing classes modified
