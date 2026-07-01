// BetterFantasyCricket — member-app theme tokens (FPL redesign).
//
// The public fantasy app gets its own token set, separate from the admin
// `--pb-*` palette, so it can flip light/dark on a member preference without
// touching the rest of the site. Tokens are scoped under `.bfc-root` and keyed
// off `data-theme`; the accent is one var (`--pb-accent`) so a club's own colour
// still white-labels everything. Mirrors docs/design_handoff_betterfantasy_redesign.

export const THEME_KEY = 'bfc-theme-pref'   // 'dark' | 'light' | 'auto'
export const DEFAULT_ACCENT = '#06B6D4'

// The token CSS, scoped to the fantasy root. color-mix keeps the accent-derived
// text legible on either surface. Aurora keyframes live here too (global, but
// prefixed) with the reduced-motion guard the design calls for.
const THEME_CSS = `
.bfc-root[data-theme="dark"]{
  --bg:#0a0d14; --surface:#10141d; --surface2:#161b27;
  --hairline:#1d2331; --hairline2:#262d3d;
  --text:#e6e8ef; --dim:#8a90a2; --faint:#5b6072; --faintest:#3a3f50;
  --grad-top:#171c2a; --bench:#0c0f17; --ink:#0a0d14; --aurora:.55;
  --accent-strong:color-mix(in srgb, var(--pb-accent,#06B6D4) 74%, #ffffff);
  --frame-shadow:0 1px 3px rgba(0,0,0,.14), 0 22px 60px -22px rgba(0,0,0,.6);
}
.bfc-root[data-theme="light"]{
  --bg:#f4f5f9; --surface:#ffffff; --surface2:#eef0f5;
  --hairline:#e6e8f0; --hairline2:#d6d9e4;
  --text:#1b1e2b; --dim:#5b6072; --faint:#9298ab; --faintest:#c2c6d2;
  --grad-top:#edeef7; --bench:#eef0f5; --ink:#16132a; --aurora:.42;
  --accent-strong:color-mix(in srgb, var(--pb-accent,#06B6D4) 58%, #15132a);
  --frame-shadow:0 1px 3px rgba(80,80,120,.12), 0 22px 60px -24px rgba(40,40,90,.28);
}
@keyframes bfcAuroraA{0%{transform:translate(0,0) scale(1)}100%{transform:translate(22%,16%) scale(1.3)}}
@keyframes bfcAuroraB{0%{transform:translate(0,0) scale(1.1)}100%{transform:translate(-18%,10%) scale(.9)}}
@keyframes bfcAuroraC{0%{transform:translate(0,0) scale(.95)}100%{transform:translate(14%,-18%) scale(1.25)}}
@keyframes bfcAuroraD{0%{transform:translate(0,0) scale(1.15)}100%{transform:translate(-16%,-12%) scale(1)}}
@media (prefers-reduced-motion: reduce){ .bfc-aurora-blob{ animation:none !important } }
`

let injected = false

/** Inject the fantasy token stylesheet once (idempotent). */
export function ensureThemeCss() {
  if (injected || typeof document === 'undefined') return
  if (document.getElementById('bfc-theme')) { injected = true; return }
  const el = document.createElement('style')
  el.id = 'bfc-theme'
  el.textContent = THEME_CSS
  document.head.appendChild(el)
  injected = true
}

export function loadThemePref() {
  try {
    const v = localStorage.getItem(THEME_KEY)
    return v === 'light' || v === 'auto' ? v : 'dark'
  } catch { return 'dark' }
}

export function saveThemePref(pref) {
  try { localStorage.setItem(THEME_KEY, pref) } catch { /* private mode */ }
}

const prefersDark = () =>
  typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-color-scheme: dark)').matches
    : true

/** Resolve a stored preference to a concrete 'dark' | 'light'. */
export function resolveTheme(pref) {
  if (pref === 'auto') return prefersDark() ? 'dark' : 'light'
  return pref === 'light' ? 'light' : 'dark'
}
