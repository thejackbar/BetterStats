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

/**
 * Public-site typography — three roles: display (headings), body (paragraph
 * text) and mono (numbers/stats — the app's font-mono styling used throughout
 * stat figures and tabular data). FONT_STACKS are the app defaults (mirrors
 * tailwind.config.js's `display`/`body`/`mono` fontFamily) — always the
 * fallback tail of a club's chosen font, and what's used when a club hasn't
 * set one.
 *
 * DISPLAY_FONT_PRESETS / BODY_FONT_PRESETS / MONO_FONT_PRESETS are the
 * curated built-in choices — every family here is already loaded site-wide
 * via the big Google Fonts <link> in index.html, so picking a preset needs no
 * extra network request. Keep the key sets in sync by hand with
 * backend/app/services/fonts.py (DISPLAY_FONT_PRESET_KEYS /
 * BODY_FONT_PRESET_KEYS / MONO_FONT_PRESET_KEYS) — no shared build step
 * between the two.
 */
export const FONT_STACKS = {
  display: "'Geist','Barlow Condensed','Oswald',sans-serif",
  body: "'Geist','Inter',system-ui,sans-serif",
  mono: "'JetBrains Mono','Fira Code',monospace",
}

/**
 * `oneWeight: true` marks a family that ships a single weight — either the
 * family genuinely has no bold cut (Anton, Bebas Neue, Archivo Black, Abril
 * Fatface, Bungee) or index.html requests it without a weight axis. Asking such
 * a family for `font-weight: 700` makes the browser SYNTHESISE a bold by
 * smearing the outlines, which reads as muddy and too dark. buildThemeCss turns
 * synthesis off for these, so a bold request renders the real weight instead.
 * Keep the flags in step with the Google Fonts <link> in index.html.
 */
export const DISPLAY_FONT_PRESETS = [
  { key: 'barlow_condensed', name: 'Barlow Condensed', family: "'Barlow Condensed', sans-serif" },
  { key: 'oswald', name: 'Oswald', family: "'Oswald', sans-serif" },
  { key: 'anton', name: 'Anton', family: "'Anton', sans-serif", oneWeight: true },
  { key: 'bebas', name: 'Bebas Neue', family: "'Bebas Neue', sans-serif", oneWeight: true },
  { key: 'archivo_black', name: 'Archivo Black', family: "'Archivo Black', sans-serif", oneWeight: true },
  { key: 'teko', name: 'Teko', family: "'Teko', sans-serif" },
  { key: 'big_shoulders', name: 'Big Shoulders', family: "'Big Shoulders Display', sans-serif" },
  { key: 'antonio', name: 'Antonio', family: "'Antonio', sans-serif" },
  { key: 'saira_condensed', name: 'Saira Condensed', family: "'Saira Condensed', sans-serif" },
  { key: 'abril', name: 'Abril Fatface', family: "'Abril Fatface', serif", oneWeight: true },
  { key: 'bungee', name: 'Bungee', family: "'Bungee', sans-serif", oneWeight: true },
  { key: 'playfair', name: 'Playfair Display', family: "'Playfair Display', serif" },
  { key: 'fredoka', name: 'Fredoka', family: "'Fredoka', sans-serif" },
]

export const BODY_FONT_PRESETS = [
  { key: 'inter', name: 'Inter', family: "'Inter', sans-serif" },
  { key: 'geist', name: 'Geist', family: "'Geist', sans-serif" },
  { key: 'hanken', name: 'Hanken Grotesk', family: "'Hanken Grotesk', sans-serif" },
  { key: 'archivo', name: 'Archivo', family: "'Archivo', sans-serif" },
  { key: 'spectral', name: 'Spectral', family: "'Spectral', serif" },
  { key: 'cormorant', name: 'Cormorant Garamond', family: "'Cormorant Garamond', serif" },
]

export const MONO_FONT_PRESETS = [
  { key: 'jetbrains_mono', name: 'JetBrains Mono', family: "'JetBrains Mono', monospace" },
  { key: 'ibm_plex_mono', name: 'IBM Plex Mono', family: "'IBM Plex Mono', monospace" },
  { key: 'space_mono', name: 'Space Mono', family: "'Space Mono', monospace" },
  { key: 'roboto_mono', name: 'Roboto Mono', family: "'Roboto Mono', monospace" },
]

export const FONT_PRESETS_BY_ROLE = { display: DISPLAY_FONT_PRESETS, body: BODY_FONT_PRESETS, mono: MONO_FONT_PRESETS }

export const FONT_ROLES = ['display', 'body', 'mono']

/** What the app uses when a club hasn't chosen a weight for the role. */
export const FONT_WEIGHT_DEFAULTS = { display: 700, body: 400, mono: 600 }

/** Weights offered in Typography settings. Mirrors fonts.FONT_WEIGHT_CHOICES. */
export const FONT_WEIGHT_CHOICES = [
  { value: 300, label: 'Light' },
  { value: 400, label: 'Regular' },
  { value: 500, label: 'Medium' },
  { value: 600, label: 'Semibold' },
  { value: 700, label: 'Bold' },
  { value: 800, label: 'Extrabold' },
  { value: 900, label: 'Black' },
]

/**
 * Resolve a club's chosen fonts (from its font_config + resolved upload
 * URLs) into what buildThemeCss needs: a CSS font-family value per role, an
 * optional @font-face descriptor for an uploaded file, the chosen weight, and
 * whether the family can actually produce a bold.
 *
 * `hasBold: false` is the one that matters — a font file holds exactly one
 * weight unless it is a variable font, so asking it for a bold gets a
 * synthesised one (smeared outlines, muddy and too dark). buildThemeCss turns
 * synthesis off in that case. Returns one entry per role; `family` is null
 * when the club is on the app default, but `weight` may still be set.
 */
export function resolveClubFonts(club) {
  const cfg = (club && club.font_config) || {}
  const out = {}
  for (const role of FONT_ROLES) {
    const entry = cfg[role] || {}
    const weight = FONT_WEIGHT_CHOICES.some(w => w.value === entry.weight) ? entry.weight : null
    const base = { cssFamily: null, fontFace: null, weight, hasBold: true, oneWeight: false }

    if (entry.source === 'preset') {
      const preset = FONT_PRESETS_BY_ROLE[role].find(f => f.key === entry.preset)
      if (preset) {
        out[role] = { ...base, cssFamily: preset.family, hasBold: !preset.oneWeight, oneWeight: !!preset.oneWeight }
        continue
      }
    }
    if (entry.source === 'upload') {
      const url = club && club[`font_${role}_url`]
      const format = club && club[`font_${role}_format`]
      if (url) {
        const family = String(entry.family || 'Club Font').replace(/['"\\]/g, '').slice(0, 60)
        // metrics is written by the upload endpoint from the file itself
        // (services/fonts.describe_font). Missing for a file uploaded before
        // that shipped — treat it as the single weight it almost certainly is.
        const m = entry.metrics || {}
        const variable = !!m.variable
        out[role] = {
          ...base,
          cssFamily: `'${family}', ${FONT_STACKS[role]}`,
          fontFace: {
            family,
            url,
            format: format || 'woff2',
            weight: variable ? `${m.min_weight || 1} ${m.max_weight || 1000}` : (m.weight || null),
          },
          hasBold: variable,
          oneWeight: !variable,
        }
        continue
      }
    }
    out[role] = base
  }
  return out
}

/** The role's effective weight — the club's choice, else the app default. */
export function fontWeightFor(fonts, role) {
  return (fonts && fonts[role] && fonts[role].weight) || FONT_WEIGHT_DEFAULTS[role]
}

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

/** WCAG contrast ratio between two hex colours (1 = identical, 21 = max). */
function contrastRatio(a, b) {
  const la = relLuminance(a)
  const lb = relLuminance(b)
  const [hi, lo] = la > lb ? [la, lb] : [lb, la]
  return (hi + 0.05) / (lo + 0.05)
}

/**
 * Readable ink for text sitting ON an accent fill (a primary button, a filled
 * pill). Whichever of near-black and white has more contrast against the accent
 * wins, so a navy or maroon club gets white lettering while the default green
 * keeps its dark ink. Reported by a club running navy, whose primary button was
 * near-black text on a near-black fill.
 */
export const ACCENT_INK_DARK = '#08110b'
export function onAccentInk(accent) {
  const h = normHex(accent)
  if (!h) return ACCENT_INK_DARK
  return contrastRatio(h, '#ffffff') > contrastRatio(h, ACCENT_INK_DARK) ? '#ffffff' : ACCENT_INK_DARK
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

/** Build the @font-face rule(s) for a club's uploaded font(s), if any. */
function buildFontFaceCss(fonts) {
  if (!fonts) return ''
  return FONT_ROLES
    .map(role => fonts[role]?.fontFace)
    .filter(Boolean)
    .map((f) => {
      // A variable font needs its weight RANGE declared or the browser never
      // uses the axis; a static file gets its real weight so the match is
      // honest rather than an assumed 400.
      const weight = f.weight ? `font-weight:${f.weight};` : ''
      return `@font-face{font-family:'${f.family}';src:url('${f.url}') format('${f.format}');${weight}font-display:swap;}`
    })
    .join('')
}

/**
 * Weight rules for the roles where a club has chosen one, plus the
 * synthesis switch.
 *
 * The two-class selectors (`.font-display.font-bold`) are deliberate: they beat
 * a single Tailwind utility on specificity, so a club's chosen heading weight
 * wins over the `font-bold` written into the components without every one of
 * those having to be edited. Scoped to elements that opted into the club's
 * display or mono font, so ordinary bold body text is left alone.
 */
function buildWeightCss(fonts) {
  if (!fonts) return ''
  const out = []
  const BOLDS = ['.font-bold', '.font-semibold', '.font-extrabold', '.font-black']

  if (fonts.display?.weight) {
    out.push(`${BOLDS.map(b => `.font-display${b}`).join(',')}{font-weight:var(--pb-weight-display);}`)
  }
  if (fonts.mono?.weight) {
    out.push(`${BOLDS.map(b => `.font-mono${b}`).join(',')}{font-weight:var(--pb-weight-mono);}`)
  }
  if (fonts.body?.weight) {
    out.push(`body{font-weight:var(--pb-weight-body);}`)
  }
  // Stop the browser faking a bold (or an italic) the font does not have. Safe
  // to apply page-wide: every app default and multi-weight preset carries a
  // real bold, so nothing that could be bolded properly loses it.
  if (FONT_ROLES.some(role => fonts[role] && !fonts[role].hasBold)) {
    out.push(`:root{font-synthesis:none;}`)
  }
  return out.join('')
}

/**
 * Build the CSS text injected as <style id="club-theme">.
 * `fonts` is the result of resolveClubFonts(club) — pass it whenever the
 * caller has a club object with font_config, so --pb-font-display/-body and
 * any @font-face rules are included alongside the colour palette.
 */
export function buildThemeCss(config, fonts) {
  const t = resolveTheme(config)
  const fontFaces = buildFontFaceCss(fonts)
  const shared = [
    `--pb-font-display:${fonts?.display?.cssFamily || FONT_STACKS.display}`,
    `--pb-font-body:${fonts?.body?.cssFamily || FONT_STACKS.body}`,
    `--pb-font-mono:${fonts?.mono?.cssFamily || FONT_STACKS.mono}`,
    `--pb-weight-display:${fontWeightFor(fonts, 'display')}`,
    `--pb-weight-body:${fontWeightFor(fonts, 'body')}`,
    `--pb-weight-mono:${fontWeightFor(fonts, 'mono')}`,
    `--pb-accent:${t.accent}`,
    // Text sitting ON an accent fill — white or near-black, whichever reads.
    `--pb-on-accent:${onAccentInk(t.accent)}`,
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

  return fontFaces +
    `:root{${shared}}` +
    `[data-theme="dark"]{${palette(t.dark)};${safeVars('dark')}}` +
    `[data-theme="light"]{${palette(t.light)};${safeVars('light')}}` +
    buildWeightCss(fonts)
}
