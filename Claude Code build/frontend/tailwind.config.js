// tailwind.config.js — DIFF for BetterStats Press Box
// You only need to MERGE these additions into your existing tailwind.config.js.
// See BUILD_GUIDE.md → "Step 2 — Tailwind config" for line-by-line.

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        pb: {
          bg:        "var(--pb-bg)",
          surface:   "var(--pb-surface)",
          surface2:  "var(--pb-surface2)",
          hairline:  "var(--pb-hairline)",
          hairline2: "var(--pb-hairline2)",
          text:      "var(--pb-text)",
          dim:       "var(--pb-dim)",
          faint:     "var(--pb-faint)",
          faintest:  "var(--pb-faintest)",
          accent:    "var(--pb-accent)",
          red:       "var(--pb-red)",
          amber:     "var(--pb-amber)",
        },
      },
      fontFamily: {
        display: ["Geist", "Inter", "system-ui", "sans-serif"],
        body:    ["Geist", "Inter", "system-ui", "sans-serif"],
        mono:    ["JetBrains Mono", "Geist Mono", "ui-monospace", "monospace"],
      },
      letterSpacing: {
        wide2: "0.08em",
        wide3: "0.14em",
        wide4: "0.18em",
      },
      fontSize: {
        // tiny labels used everywhere
        "2xs": ["0.625rem", { lineHeight: "0.9rem" }], // 10px
      },
    },
  },
  plugins: [],
};
