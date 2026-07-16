/**
 * Theme model for BetterStats white-labelling.
 *
 * BRAND holds the default BetterStats palette. A club's `theme_config`
 * (stored on the organisation) overrides any subset of these values;
 * resolveTheme() merges club config over the brand defaults, and
 * buildThemeCss() turns the result into the CSS injected at runtime.
 *
 * Accent / indicator / chart colours are shared across light and dark.
 * Only the surface + text tokens differ per theme.
 *
 * Most clubs play in two colours, so the palette carries a primary `accent`
 * and a `accent2` secondary. The secondary drives the primary→secondary
 * gradient (`--pb-gradient`) and the default second chart series (wickets),
 * the two places a second colour reads well without a contrast trap.
 */

export const BRAND = {
  accent: '#16c784',
  accent2: '#3b82f6',
  positive: '#16c784',
  negative: '#ef5b5b',
  chart_runs: '#16c784',
  chart_wickets: '#3b82f6',
  chart_milestone: '#f5b542',
  chart_series: ['#16c784', '#3b82f6', '#f5b542', '#a855f7', '#ef5b5b', '#06b6d4', '#84cc16', '#f97316'],
  // Honour / achievement category colours (badges + header pills)
  cat_honour: '#f5b542',
  cat_role: '#60a5fa',
  cat_award: '#16c784',
  cat_milestone: '#a78bfa',
  dark: {
    bg: '#0a0d14', surface: '#10141d', surface2: '#161b27',
    hairline: '#1d2331', hairline2: '#262d3d',
    text: '#e6e8ef', dim: '#8a90a2', faint: '#5b6072', faintest: '#3a3f50',
  },
  light: {
    bg: '#f5f6f8', surface: '#ffffff', surface2: '#eef0f3',
    hairline: '#e1e4ea', hairline2: '#d0d4dd',
    text: '#1b1e27', dim: '#5b6072', faint: '#8a90a2', faintest: '#b6bac6',
  },
}

/** Brand + chart colour fields shown in the admin form. */
export const COLOR_FIELDS = [
  { key: 'accent', label: 'Accent', hint: 'Primary brand colour — buttons, links, highlights' },
  { key: 'accent2', label: 'Secondary accent', hint: 'Your second club colour, used in gradients and the wickets chart line' },
  { key: 'positive', label: 'Top indicator', hint: 'Good / leading values' },
  { key: 'negative', label: 'Bottom indicator', hint: 'Poor / trailing values' },
  { key: 'chart_runs', label: 'Chart — runs', hint: 'Runs series in graphs' },
  { key: 'chart_wickets', label: 'Chart — wickets', hint: 'Wickets series in graphs' },
  { key: 'chart_milestone', label: 'Chart — milestone', hint: 'Centuries & high-score highlights' },
]

/** Honour / achievement category colours — drive badges and header pills. */
export const HONOUR_FIELDS = [
  { key: 'cat_honour', label: 'Honours', hint: 'Hall of Fame, life membership, premierships' },
  { key: 'cat_role', label: 'Club roles', hint: 'Office bearers — president, committee' },
  { key: 'cat_award', label: 'Awards', hint: 'Club & association awards' },
  { key: 'cat_milestone', label: 'Milestones', hint: 'Games played & cap milestones' },
]

/** Surface + text colours that differ per theme. Kept deliberately small. */
export const PALETTE_FIELDS = [
  { key: 'bg', label: 'Background' },
  { key: 'surface', label: 'Cards & panels' },
  { key: 'text', label: 'Text' },
]

/** Expand #abc → #aabbcc and lowercase; returns null if not a 3/6-digit hex. */
function normHex(hex) {
  const m = /^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.exec((hex || '').trim())
  if (!m) return null
  let h = m[1]
  if (h.length === 3) h = h.split('').map(ch => ch + ch).join('')
  return '#' + h.toLowerCase()
}

/** Lighten a hex toward white by fraction f (0..1). Falls back to the input. */
function mixWhite(hex, f) {
  const h = normHex(hex)
  if (!h) return hex
  const n = parseInt(h.slice(1), 16)
  const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255]
    .map(c => Math.round(c + (255 - c) * f).toString(16).padStart(2, '0'))
  return '#' + ch.join('')
}

/**
 * Derive the full dark surface ramp from a single base background colour, so a
 * club can pick one dark base (navy, maroon…) and get cohesive cards + borders
 * instead of the base sitting under default near-black surfaces. Text levels are
 * kept from the supplied base palette — light greys read on any dark base.
 */
export function deriveDarkPalette(bg, base = BRAND.dark) {
  if (!normHex(bg)) return { ...base }
  return {
    ...base,
    bg,
    surface: mixWhite(bg, 0.05),
    surface2: mixWhite(bg, 0.10),
    hairline: mixWhite(bg, 0.14),
    hairline2: mixWhite(bg, 0.20),
  }
}

/** Inline CSS for the primary→secondary brand gradient. */
export const gradientCss = (accent, accent2) =>
  `linear-gradient(135deg, ${accent} 0%, ${accent2} 100%)`

/** WCAG relative luminance (0 = black, 1 = white) of a hex colour. */
function relLuminance(hex) {
  const h = normHex(hex)
  if (!h) return 0.5
  const n = parseInt(h.slice(1), 16)
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
    const s = c / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/**
 * The secondary accent, made safe to paint on the given theme's surfaces.
 * Plenty of clubs' second colour is black or white (Applecross, the classic
 * navy/white kits) — used raw, that disappears against the matching theme
 * background. Near-black falls back to the primary accent on the dark theme,
 * near-white falls back on the light theme; everything else passes through
 * untouched. Fall back to the PRIMARY accent (a solid, on-brand read) rather
 * than trying to bend the colour itself into something the club never chose.
 */
export function safeAccent2(accent2, accent, mode) {
  const h = normHex(accent2)
  if (!h) return accent
  const L = relLuminance(h)
  if (mode === 'dark' && L < 0.05) return accent
  if (mode === 'light' && L > 0.8) return accent
  return h
}

/** Merge a club's stored theme_config over the brand defaults. */
export function resolveTheme(config) {
  const c = config || {}
  return {
    accent: c.accent || BRAND.accent,
    accent2: c.accent2 || BRAND.accent2,
    positive: c.positive || BRAND.positive,
    negative: c.negative || BRAND.negative,
    chart_runs: c.chart_runs || BRAND.chart_runs,
    // The wickets series follows the secondary accent by default, so a club that
    // sets two colours gets an on-brand runs/wickets pairing for free. An
    // explicit chart_wickets still wins.
    chart_wickets: c.chart_wickets || c.accent2 || BRAND.chart_wickets,
    chart_milestone: c.chart_milestone || BRAND.chart_milestone,
    chart_series: (Array.isArray(c.chart_series) && c.chart_series.length)
      ? c.chart_series
      : BRAND.chart_series,
    cat_honour: c.cat_honour || BRAND.cat_honour,
    cat_role: c.cat_role || BRAND.cat_role,
    cat_award: c.cat_award || BRAND.cat_award,
    cat_milestone: c.cat_milestone || BRAND.cat_milestone,
    dark: { ...BRAND.dark, ...(c.dark || {}) },
    light: { ...BRAND.light, ...(c.light || {}) },
  }
}

/** Build the CSS text injected as <style id="club-theme">. */
export function buildThemeCss(config) {
  const t = resolveTheme(config)
  const shared = [
    `--pb-accent:${t.accent}`,
    `--pb-accent-2:${t.accent2}`,
    `--pb-gradient:${gradientCss(t.accent, t.accent2)}`,
    `--pb-positive:${t.positive}`,
    `--pb-negative:${t.negative}`,
    `--pb-red:${t.negative}`,
    `--pb-chart-runs:${t.chart_runs}`,
    `--pb-chart-wickets:${t.chart_wickets}`,
    `--pb-chart-milestone:${t.chart_milestone}`,
    `--pb-amber:${t.chart_milestone}`,
    `--pb-cat-honour:${t.cat_honour}`,
    `--pb-cat-role:${t.cat_role}`,
    `--pb-cat-award:${t.cat_award}`,
    `--pb-cat-milestone:${t.cat_milestone}`,
    ...t.chart_series.map((c, i) => `--pb-chart-${i + 1}:${c}`),
  ].join(';')

  const palette = (p) => [
    `--pb-bg:${p.bg}`, `--pb-surface:${p.surface}`, `--pb-surface2:${p.surface2}`,
    `--pb-hairline:${p.hairline}`, `--pb-hairline2:${p.hairline2}`,
    `--pb-text:${p.text}`, `--pb-dim:${p.dim}`, `--pb-faint:${p.faint}`,
    `--pb-faintest:${p.faintest}`,
  ].join(';')

  // Per-theme SAFE secondary accent (see safeAccent2): the raw --pb-accent-2
  // stays available, but anything painting on theme surfaces (the gradient,
  // the wickets chart line, --pb-accent-2-safe consumers) gets the guarded
  // value so a black or white club colour never vanishes into the background.
  const safeVars = (mode) => {
    const a2 = safeAccent2(t.accent2, t.accent, mode)
    const wk = t.chart_wickets === t.accent2 ? a2 : safeAccent2(t.chart_wickets, t.accent, mode)
    return [
      `--pb-accent-2-safe:${a2}`,
      `--pb-gradient:${gradientCss(t.accent, a2)}`,
      `--pb-chart-wickets:${wk}`,
    ].join(';')
  }

  return `:root{${shared}}` +
    `[data-theme="dark"]{${palette(t.dark)};${safeVars('dark')}}` +
    `[data-theme="light"]{${palette(t.light)};${safeVars('light')}}`
}
