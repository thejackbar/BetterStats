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
        display: ['Geist', 'Barlow Condensed', 'Oswald', 'sans-serif'],
        body:    ['Geist', 'Inter', 'system-ui', 'sans-serif'],
        mono:    ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans:    ['Geist', 'Inter', 'system-ui', 'sans-serif'],
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
