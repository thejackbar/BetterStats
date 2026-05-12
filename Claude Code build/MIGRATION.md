# MIGRATION.md — quick reference

## Files added

```
frontend/src/styles/theme.css
frontend/src/lib/presskit.jsx
frontend/src/lib/mockData.js
frontend/src/components/PressNav.jsx
frontend/src/pages/Dashboard.jsx           (replaces existing)
frontend/src/pages/PlayerProfile.jsx       (replaces existing)
```

## tailwind.config.js — merge into existing

```js
theme: {
  extend: {
    colors: {
      pb: {
        bg: "var(--pb-bg)", surface: "var(--pb-surface)", surface2: "var(--pb-surface2)",
        hairline: "var(--pb-hairline)", hairline2: "var(--pb-hairline2)",
        text: "var(--pb-text)", dim: "var(--pb-dim)",
        faint: "var(--pb-faint)", faintest: "var(--pb-faintest)",
        accent: "var(--pb-accent)", red: "var(--pb-red)", amber: "var(--pb-amber)",
      },
    },
    fontFamily: {
      display: ["Geist", "Inter", "system-ui", "sans-serif"],
      body: ["Geist", "Inter", "system-ui", "sans-serif"],
      mono: ["JetBrains Mono", "Geist Mono", "ui-monospace", "monospace"],
    },
    letterSpacing: { wide2: "0.08em", wide3: "0.14em", wide4: "0.18em" },
    fontSize: { "2xs": ["0.625rem", { lineHeight: "0.9rem" }] },
  },
},
```

## index.html — add to `<head>`

```html
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
```

## main.jsx — add import

```js
import "./styles/theme.css";
```

## App.jsx — swap Navbar

```diff
- import Navbar from "./components/Navbar";
+ import PressNav from "./components/PressNav";

- <Navbar />
+ <PressNav clubName={club.name} clubShort={club.short_name} season="2025/26" />
```

## Real-data wiring

Every page has `// WIRE:` comments showing exactly which `api.js` endpoint each
state slot expects. Uncomment those blocks once your endpoints return data.

`fetchOrMock(promise, mock)` (in `lib/mockData.js`) wraps each call — if the
endpoint errors or returns empty, the mock is used. This lets you migrate
endpoint-by-endpoint without breaking the UI.

## White-label accent

```js
// in useClubTheme.js
document.documentElement.style.setProperty("--pb-accent", club.accent_color);
```

That single line recolours every accent in the app.
