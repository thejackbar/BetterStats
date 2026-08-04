/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          950: '#070b14',
          900: '#0d1117',
          800: '#131c2e',
          700: '#1a2540',
          600: '#243352',
        },
        accent: {
          DEFAULT: '#16c784',
          dark: '#0fa36a',
          light: '#4dd9a0',
        },
        amber: {
          cricket: '#f59e0b',
        },
        stat: '#e2e8f0',
        pb: {
          bg:        "var(--pb-bg)",
          bg2:       "var(--pb-bg2)",
          surface:   "var(--pb-surface)",
          surface2:  "var(--pb-surface2)",
          surface3:  "var(--pb-surface3)",
          hairline:  "var(--pb-hairline)",
          hairline2: "var(--pb-hairline2)",
          text:      "var(--pb-text)",
          dim:       "var(--pb-dim)",
          faint:     "var(--pb-faint)",
          faintest:  "var(--pb-faintest)",
          accent:    "var(--pb-accent)",
          'accent-bright': "var(--pb-accent-bright)",
          brand:     "var(--pb-brand)",
          red:       "var(--pb-red)",
          amber:     "var(--pb-amber)",
          positive:  "var(--pb-positive)",
          negative:  "var(--pb-negative)",
          milestone: "var(--pb-chart-milestone)",
          runs:      "var(--pb-chart-runs)",
          wickets:   "var(--pb-chart-wickets)",
        },
      },
      fontFamily: {
        // --pb-font-display/-body/-mono are always defined (default value in
        // styles/theme.css :root, overridden per-club by buildThemeCss when a
        // club picks its own typography — see lib/theme.js). `sans` mirrors
        // `body` so ordinary unstyled text (not explicitly font-display'd)
        // also reflects a club's body-font choice, matching what "body text"
        // means to a club admin. `mono` (numbers/stats) covers the many
        // font-mono uses across stat figures and tabular data.
        display: ['var(--pb-font-display)'],
        body:    ['var(--pb-font-body)'],
        mono:    ['var(--pb-font-mono)'],
        sans:    ['var(--pb-font-body)'],
      },
      letterSpacing: {
        wide2: "0.08em",
        wide3: "0.14em",
        wide4: "0.18em",
      },
      fontSize: {
        '2xs': ["0.625rem", { lineHeight: "0.9rem" }],
      },
    },
  },
  plugins: [],
}
