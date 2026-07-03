// Procedural background-texture overlays — a club-selectable "finish" layered
// on top of ANY social post template (lineups, results, fixtures, events,
// scorecards), independent of whatever a given template already bakes in
// (Grain / Halftone / Stripes). Picked once in the Style panel, applied via
// <BackgroundLayer style={key} palette={...} width={...} height={...} />.
//
// Several styles are inspired by fffuel.co's SVG generator suite (ffflux,
// uuundulate, rrrainbow, hhhorizon, sssplatter) — fffuel doesn't publish an
// API or source code, so these are our own procedural implementations of the
// same visual idea, not a port of their code. Colour-customisable styles
// take a `colors` array (falls back to a palette-derived default); several
// also take a `seed` number for the "Randomize" control.
//
// Every shape uses fixed or deterministically-derived coordinates — never
// Math.random() at render time — because the Post Designer mounts two
// separate instances of the same template (a scaled-down live preview + a
// full-size hidden node used for the PNG export). Real randomness would let
// the two instances diverge, so the exported image wouldn't match what the
// club saw on screen. The seed itself is just a stored integer bumped by a
// click handler (not Math.random), so it stays reproducible.

import { useId } from 'react'

// React's useId() includes colons (e.g. ":r0:"), which are legal in an HTML id
// but awkward inside an SVG url(#...) filter reference — strip them for a
// plain alphanumeric id.
function useFilterId(base) {
  return `${base}-${useId().replace(/:/g, '')}`
}

// Deterministic pseudo-random in [0, 1), seeded by a plain number. Same input
// -> same output on every render, unlike Math.random().
function prand(seed) {
  const x = Math.sin(seed * 12.9898) * 43758.5453
  return x - Math.floor(x)
}

const overlayBox = { position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }

function Svg({ width, height, children, style }) {
  return (
    <svg style={{ ...overlayBox, ...style }} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
      {children}
    </svg>
  )
}

// ── Small hex/HSL helpers, used to derive a multi-hue default for Rainbow ──
function hexToHsl(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  let h = 0, s = 0
  const l = (max + min) / 2
  const d = max - min
  if (d !== 0) {
    s = d / (1 - Math.abs(2 * l - 1))
    if (max === r) h = ((g - b) / d) % 6
    else if (max === g) h = (b - r) / d + 2
    else h = (r - g) / d + 4
    h *= 60
    if (h < 0) h += 360
  }
  return [h, s, l]
}
function hslToHex(h, s, l) {
  const c = (1 - Math.abs(2 * l - 1)) * s
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1))
  const m = l - c / 2
  let r = 0, g = 0, b = 0
  if (h < 60) [r, g, b] = [c, x, 0]
  else if (h < 120) [r, g, b] = [x, c, 0]
  else if (h < 180) [r, g, b] = [0, c, x]
  else if (h < 240) [r, g, b] = [0, x, c]
  else if (h < 300) [r, g, b] = [x, 0, c]
  else [r, g, b] = [c, 0, x]
  const to255 = (v) => Math.round((v + m) * 255).toString(16).padStart(2, '0')
  return `#${to255(r)}${to255(g)}${to255(b)}`
}
function rotateHue(hex, deg) {
  try {
    const [h, s, l] = hexToHsl(hex)
    return hslToHex((h + deg + 360) % 360, s, l)
  } catch {
    return hex
  }
}

// ── 1. Splatter — sharp-edged ink-splat blobs + droplet trail, randomizable ──
// (fffuel sssplatter: "organic splattered liquid forms" — our version.)
function splatPoints(cx, cy, baseR, spikes, seed) {
  const pts = []
  for (let i = 0; i < spikes; i++) {
    const angle = (i / spikes) * Math.PI * 2
    const r = baseR * (0.55 + prand(seed + i * 3.7) * 0.85)
    pts.push(`${cx + Math.cos(angle) * r},${cy + Math.sin(angle) * r}`)
  }
  return pts.join(' ')
}
function Splatter({ palette, width: w, height: h, seed = 0 }) {
  const ink = palette.ink
  const s = seed * 991
  const splats = [
    { x: 0.14, y: 0.16, r: 130, spikes: 12, seed: 4 + s },
    { x: 0.86, y: 0.84, r: 155, spikes: 14, seed: 22 + s },
  ]
  const droplets = Array.from({ length: 26 }, (_, i) => {
    const corner = i % 2 === 0 ? { x: 0.14, y: 0.16 } : { x: 0.86, y: 0.84 }
    const spread = 0.3
    return {
      x: corner.x + (prand(i * 4.2 + 3 + s) - 0.5) * spread,
      y: corner.y + (prand(i * 6.1 + 9 + s) - 0.5) * spread,
      r: 3 + prand(i * 3.4 + 5 + s) * 9,
      o: 0.25 + prand(i * 8.8 + 1 + s) * 0.35,
    }
  })
  return (
    <Svg width={w} height={h}>
      <g fill={ink}>
        {splats.map((sp, i) => (
          <polygon key={`s${i}`} points={splatPoints(sp.x * w, sp.y * h, sp.r, sp.spikes, sp.seed)} opacity={0.4} />
        ))}
        {droplets.map((d, i) => (
          <circle key={`d${i}`} cx={d.x * w} cy={d.y * h} r={d.r} opacity={Math.max(0, Math.min(1, d.o))} />
        ))}
      </g>
    </Svg>
  )
}

// ── 2. Chaos Waves — energetic overlapping wave bands, match-day motion ──
function waveLine(w, baseY, amp, freq, phase) {
  const steps = 24
  const pts = []
  for (let i = 0; i <= steps; i++) {
    const x = (i / steps) * w
    const y = baseY + Math.sin((i / steps) * Math.PI * freq + phase) * amp
    pts.push(`${x},${y}`)
  }
  return pts
}
// A wave band filled between the wavy line and whichever canvas edge it's
// anchored to — 'bottom' closes down to y=h, 'top' closes up to y=0.
function waveBand(w, h, baseY, amp, freq, phase, anchor) {
  const pts = waveLine(w, baseY, amp, freq, phase)
  const edgeY = anchor === 'top' ? 0 : h
  return [`0,${edgeY}`, ...pts, `${w},${edgeY}`].join(' ')
}
function ChaosWaves({ palette, width: w, height: h }) {
  const accent = palette.accent
  const ink = palette.ink
  const bands = [
    { y: h * 0.8, amp: 38, freq: 3.4, phase: 0.4, fill: accent, o: 0.16, anchor: 'bottom' },
    { y: h * 0.9, amp: 26, freq: 4.1, phase: 1.6, fill: ink, o: 0.1, anchor: 'bottom' },
    { y: h * 0.16, amp: 24, freq: 3.8, phase: 2.4, fill: accent, o: 0.1, anchor: 'top' },
  ]
  return (
    <Svg width={w} height={h}>
      {bands.map((b, i) => (
        <polygon key={i} points={waveBand(w, h, b.y, b.amp, b.freq, b.phase, b.anchor)} fill={b.fill} opacity={b.o} />
      ))}
    </Svg>
  )
}

// ── 3. Scribble — dense hand-drawn scribble clusters, playful energy ──
function scribblePath(cx, cy, size, seed) {
  const points = 18
  let d = `M ${cx} ${cy}`
  for (let i = 1; i <= points; i++) {
    const angle = prand(seed + i * 5.3) * Math.PI * 2
    const r = size * (0.2 + prand(seed + i * 2.1) * 0.8)
    d += ` L ${cx + Math.cos(angle) * r} ${cy + Math.sin(angle) * r}`
  }
  return d
}
function Scribble({ palette, width: w, height: h }) {
  const ink = palette.ink
  const clusters = [
    { x: 0.14, y: 0.16, size: 110, seed: 6 },
    { x: 0.86, y: 0.84, size: 130, seed: 31 },
  ]
  return (
    <Svg width={w} height={h}>
      <g stroke={ink} strokeWidth={2} fill="none" opacity={0.26} strokeLinecap="round" strokeLinejoin="round">
        {clusters.map((c, i) => (
          <path key={i} d={scribblePath(c.x * w, c.y * h, c.size, c.seed)} />
        ))}
      </g>
    </Svg>
  )
}

// ── 4. Blurry Blobs — soft, modern gradient-mesh-style abstract blobs ──
function BlurryBlobs({ palette, width: w, height: h }) {
  const accent = palette.accent
  const ink = palette.ink
  const blobs = [
    { x: 0.18, y: 0.22, r: 240, fill: accent, o: 0.18, b: 65 },
    { x: 0.85, y: 0.2, r: 190, fill: ink, o: 0.08, b: 65 },
    { x: 0.75, y: 0.85, r: 260, fill: accent, o: 0.14, b: 75 },
  ]
  return (
    <Svg width={w} height={h}>
      <g>
        {blobs.map((b, i) => (
          <circle key={i} cx={b.x * w} cy={b.y * h} r={b.r} fill={b.fill} opacity={b.o} style={{ filter: `blur(${b.b}px)` }} />
        ))}
      </g>
    </Svg>
  )
}

// ── 5. Flux — fluid, organic gradient-mesh blobs, 2 user colours (ffflux) ──
function Flux({ width: w, height: h, colors, seed = 0 }) {
  const [c1, c2] = colors
  const filterId = useFilterId('bg-flux')
  const s = seed * 991
  const blobs = [
    { x: 0.22 + (prand(1 + s) - 0.5) * 0.15, y: 0.28 + (prand(2 + s) - 0.5) * 0.15, r: 260, fill: c1, o: 0.38 },
    { x: 0.78 + (prand(3 + s) - 0.5) * 0.15, y: 0.32 + (prand(4 + s) - 0.5) * 0.15, r: 230, fill: c2, o: 0.34 },
    { x: 0.5 + (prand(5 + s) - 0.5) * 0.15, y: 0.78 + (prand(6 + s) - 0.5) * 0.15, r: 280, fill: c1, o: 0.3 },
    { x: 0.85 + (prand(7 + s) - 0.5) * 0.1, y: 0.82 + (prand(8 + s) - 0.5) * 0.1, r: 200, fill: c2, o: 0.32 },
  ]
  return (
    <Svg width={w} height={h}>
      <filter id={filterId}>
        <feGaussianBlur stdDeviation="70" />
      </filter>
      <g filter={`url(#${filterId})`}>
        {blobs.map((b, i) => (
          <circle key={i} cx={b.x * w} cy={b.y * h} r={b.r} fill={b.fill} opacity={b.o} />
        ))}
      </g>
    </Svg>
  )
}

// ── 6. Undulate — repeated organic ripple lines, 2 user colours (uuundulate) ──
function undulatePath(w, baseY, amp, freq, phase, seedOffset) {
  const steps = 30
  let d = `M 0 ${baseY}`
  for (let i = 1; i <= steps; i++) {
    const x = (i / steps) * w
    const wobble = (prand(seedOffset + i * 1.7) - 0.5) * amp * 0.4
    const y = baseY + Math.sin((i / steps) * Math.PI * freq + phase) * amp + wobble
    d += ` L ${x} ${y}`
  }
  return d
}
function Undulate({ width: w, height: h, colors, seed = 0 }) {
  const [c1, c2] = colors
  const s = seed * 991
  const lines = Array.from({ length: 7 }, (_, i) => ({
    y: h * (0.1 + i * 0.13),
    amp: 30 + prand(i * 3.3 + s) * 16,
    freq: 2 + prand(i * 5.1 + s) * 1.5,
    phase: prand(i * 7.7 + s) * 6,
    color: i % 2 === 0 ? c1 : c2,
    o: 0.16 + prand(i * 2.2 + s) * 0.14,
  }))
  return (
    <Svg width={w} height={h}>
      <g fill="none" strokeLinecap="round">
        {lines.map((l, i) => (
          <path key={i} d={undulatePath(w, l.y, l.amp, l.freq, l.phase, i * 11 + s)} stroke={l.color} strokeWidth={3.5} opacity={l.o} />
        ))}
      </g>
    </Svg>
  )
}

// ── 7. Rainbow — big packed multi-hue circles, user colours (rrrainbow) ──
function Rainbow({ width: w, height: h, colors, seed = 0 }) {
  const s = seed * 991
  const n = 9
  const circles = Array.from({ length: n }, (_, i) => ({
    x: prand(i * 3.3 + 1 + s),
    y: prand(i * 4.7 + 5 + s),
    r: 40 + prand(i * 6.1 + 2 + s) * 70,
    color: colors[i % colors.length],
    o: 0.3 + prand(i * 2.9 + 7 + s) * 0.25,
  }))
  return (
    <Svg width={w} height={h}>
      {circles.map((c, i) => (
        <circle key={i} cx={c.x * w} cy={c.y * h} r={c.r} fill={c.color} opacity={c.o} />
      ))}
    </Svg>
  )
}

// ── 8. Horizon — cyberpunk sun + receding stripes, 2 user colours (hhhorizon) ──
function Horizon({ width: w, height: h, colors }) {
  const [c1, c2] = colors
  const gradId = useFilterId('bg-horizon-sun')
  const cx = w * 0.5, cy = h * 0.32, r = Math.min(w, h) * 0.22
  const stripes = Array.from({ length: 10 }, (_, i) => {
    const t = i / 9
    return { y: cy + t * (h - cy) * 1.05, width: 2 + t * 11, o: 0.5 - t * 0.35 }
  })
  return (
    <Svg width={w} height={h}>
      <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stopColor={c1} />
        <stop offset="100%" stopColor={c2} />
      </linearGradient>
      <circle cx={cx} cy={cy} r={r} fill={`url(#${gradId})`} opacity={0.35} />
      <line x1={0} y1={cy} x2={w} y2={cy} stroke={c2} strokeWidth={2} opacity={0.4} />
      <g stroke={c2} strokeLinecap="round">
        {stripes.map((st, i) => (
          <line key={i} x1={0} y1={st.y} x2={w} y2={st.y} strokeWidth={st.width} opacity={st.o} />
        ))}
      </g>
    </Svg>
  )
}

// ── 9. Grunge Vintage — bold mottled wear + vignette (tttexture-inspired) ──
// (fffuel's tttexture is real macro-photography, not a generator — no
// algorithm to port. This is our own procedural stand-in: bigger, bolder
// mottled patches than a fine grain, closer to that worn/vintage read.)
function GrungeVintage({ palette, width: w, height: h, seed = 0 }) {
  const ink = palette.ink
  const filterId = useFilterId('bg-grunge-vintage')
  const s = seed * 991
  const patches = Array.from({ length: 6 }, (_, i) => ({
    x: prand(i * 3.1 + 1 + s),
    y: prand(i * 4.4 + 3 + s),
    r: 150 + prand(i * 5.7 + 2 + s) * 170,
    o: 0.08 + prand(i * 2.2 + 6 + s) * 0.14,
    b: 45 + prand(i * 6.6 + 4 + s) * 40,
  }))
  return (
    <>
      <div style={{ ...overlayBox, background: `radial-gradient(ellipse at center, transparent 45%, ${ink}30 100%)` }} />
      <Svg width={w} height={h}>
        <filter id={filterId}>
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch" />
          <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.5 0" />
        </filter>
        <rect width={w} height={h} filter={`url(#${filterId})`} opacity={0.18} />
        <g fill={ink}>
          {patches.map((p, i) => (
            <circle key={i} cx={p.x * w} cy={p.y * h} r={p.r} opacity={p.o} style={{ filter: `blur(${p.b}px)` }} />
          ))}
        </g>
      </Svg>
    </>
  )
}

export const BACKGROUND_STYLES = [
  { key: 'none', label: 'Clean', hint: 'No extra texture — just the template default' },
  { key: 'splatter', label: 'Splatter', hint: 'Sharp-edged ink-splat blobs', Component: Splatter, randomizable: true },
  { key: 'chaoswaves', label: 'Chaos Waves', hint: 'Energetic overlapping wave bands', Component: ChaosWaves },
  { key: 'scribble', label: 'Scribble', hint: 'Dense hand-drawn scribble clusters', Component: Scribble },
  { key: 'blurryblobs', label: 'Blurry Blobs', hint: 'Soft modern gradient-mesh blobs', Component: BlurryBlobs },
  {
    key: 'flux', label: 'Flux', hint: 'Fluid organic gradient mesh', Component: Flux, randomizable: true,
    customColors: { count: 2, labels: ['Colour 1', 'Colour 2'], defaultFrom: (pal) => [pal.accent, pal.ink] },
  },
  {
    key: 'undulate', label: 'Undulate', hint: 'Repeated organic ripple lines', Component: Undulate, randomizable: true,
    customColors: { count: 2, labels: ['Colour 1', 'Colour 2'], defaultFrom: (pal) => [pal.accent, pal.ink] },
  },
  {
    key: 'rainbow', label: 'Rainbow', hint: 'Big packed multi-hue circles', Component: Rainbow, randomizable: true,
    customColors: {
      count: 4, labels: ['Colour 1', 'Colour 2', 'Colour 3', 'Colour 4'],
      defaultFrom: (pal) => [pal.accent, rotateHue(pal.accent, 90), rotateHue(pal.accent, 180), rotateHue(pal.accent, 270)],
    },
  },
  {
    key: 'horizon', label: 'Horizon', hint: 'Cyberpunk sun + receding stripes', Component: Horizon,
    customColors: { count: 2, labels: ['Fill 1', 'Fill 2'], defaultFrom: (pal) => [pal.accent, pal.ink] },
  },
  { key: 'grungevintage', label: 'Grunge Vintage', hint: 'Bold mottled wear + vignette', Component: GrungeVintage, randomizable: true },
]

// Renders the chosen texture (or nothing, for 'none') on top of a template's
// own content. Sits as the last child of the 1080×1080 (or 1920×1080, for
// scorecards) post so it reads as a finish over the whole design.
export function BackgroundLayer({ styleKey, palette, width = 1080, height = 1080, colors, seed = 0 }) {
  const entry = BACKGROUND_STYLES.find((s) => s.key === styleKey)
  if (!entry || !entry.Component || !palette) return null
  const Texture = entry.Component
  const resolvedColors = entry.customColors ? (colors && colors.length === entry.customColors.count ? colors : entry.customColors.defaultFrom(palette)) : undefined
  return <Texture palette={palette} width={width} height={height} colors={resolvedColors} seed={seed} />
}
