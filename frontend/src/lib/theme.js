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
 */

export const BRAND = {
  accent: '#16c784',
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

/** Merge a club's stored theme_config over the brand defaults. */
export function resolveTheme(config) {
  const c = config || {}
  return {
    accent: c.accent || BRAND.accent,
    positive: c.positive || BRAND.positive,
    negative: c.negative || BRAND.negative,
    chart_runs: c.chart_runs || BRAND.chart_runs,
    chart_wickets: c.chart_wickets || BRAND.chart_wickets,
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

  return `:root{${shared}}` +
    `[data-theme="dark"]{${palette(t.dark)}}` +
    `[data-theme="light"]{${palette(t.light)}}`
}
