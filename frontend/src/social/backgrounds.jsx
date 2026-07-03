// Procedural background-texture overlays — a club-selectable "finish" layered
// on top of ANY social post template (lineups, results, fixtures, events,
// scorecards), independent of whatever a given template already bakes in
// (Grain / Halftone / Stripes). Picked once in the Style panel, applied via
// <BackgroundLayer style={key} palette={...} width={...} height={...} />.
//
// Every shape uses fixed or deterministically-derived coordinates — never
// Math.random() at render time — because the Post Designer mounts two
// separate instances of the same template (a scaled-down live preview + a
// full-size hidden node used for the PNG export). Real randomness would let
// the two instances diverge, so the exported image wouldn't match what the
// club saw on screen.

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

// ── 1. Grunge Spray — spray-can blots in two opposing corners + fine droplets ──
function GrungeSpray({ palette, width: w, height: h }) {
  const ink = palette.ink
  const blots = [
    { x: 0.05, y: 0.08, r: 70, o: 0.4, b: 4 },
    { x: 0.12, y: 0.05, r: 34, o: 0.5, b: 2 },
    { x: 0.03, y: 0.2, r: 26, o: 0.45, b: 1.5 },
    { x: 0.94, y: 0.9, r: 76, o: 0.4, b: 4 },
    { x: 0.88, y: 0.95, r: 32, o: 0.5, b: 2 },
    { x: 0.97, y: 0.8, r: 24, o: 0.45, b: 1.5 },
  ]
  const droplets = Array.from({ length: 46 }, (_, i) => {
    const corner = i % 2 === 0 ? { x: 0.08, y: 0.1 } : { x: 0.92, y: 0.9 }
    const spread = 0.32
    return {
      x: corner.x + (prand(i * 3.1 + 1) - 0.5) * spread,
      y: corner.y + (prand(i * 5.7 + 4) - 0.5) * spread,
      r: 1.5 + prand(i * 7.3 + 2) * 5,
      o: 0.12 + prand(i * 2.9 + 6) * 0.35,
    }
  })
  return (
    <Svg width={w} height={h}>
      <g fill={ink}>
        {blots.map((b, i) => (
          <circle key={`b${i}`} cx={b.x * w} cy={b.y * h} r={b.r} opacity={b.o} style={{ filter: `blur(${b.b}px)` }} />
        ))}
        {droplets.map((d, i) => (
          <circle key={`d${i}`} cx={d.x * w} cy={d.y * h} r={d.r} opacity={Math.max(0, Math.min(1, d.o))} />
        ))}
      </g>
    </Svg>
  )
}

// ── 2. Torn Paper — a jagged deckle-edge line near the top & bottom ──
// (Drawn as ink-coloured strokes rather than paint-over shapes, since a
// "cut-out" flap the same colour as the background is invisible on most
// templates — a stroke reads on any palette by construction.)
function TornPaper({ palette, width: w, height: h }) {
  const ink = palette.ink
  const teeth = 26
  const jag = 14
  const edgeLine = (baseY, seedOffset) => {
    const pts = []
    for (let i = 0; i <= teeth; i++) {
      const x = (i / teeth) * w
      const y = baseY + (prand(i * 4.4 + seedOffset) - 0.5) * jag
      pts.push(`${x},${y}`)
    }
    return pts.join(' ')
  }
  return (
    <Svg width={w} height={h}>
      <polyline points={edgeLine(28, 11)} fill="none" stroke={ink} strokeWidth={2.5} opacity={0.3} strokeLinejoin="round" strokeLinecap="round" />
      <polyline points={edgeLine(h - 28, 91)} fill="none" stroke={ink} strokeWidth={2.5} opacity={0.3} strokeLinejoin="round" strokeLinecap="round" />
    </Svg>
  )
}

// ── 3. Scratch / Distress — thin random scratches + coarse dust ──
function ScratchDistress({ palette, width: w, height: h }) {
  const ink = palette.ink
  const filterId = useFilterId('bg-distress-dust')
  const lines = Array.from({ length: 16 }, (_, i) => {
    const x1 = prand(i * 3.3 + 1) * w
    const len = 60 + prand(i * 6.6 + 2) * 220
    const angle = (prand(i * 9.1 + 3) - 0.5) * 50
    const y1 = prand(i * 4.7 + 5) * h
    const rad = (angle * Math.PI) / 180
    const x2 = x1 + Math.cos(rad) * len
    const y2 = y1 + Math.sin(rad) * len
    return { x1, y1, x2, y2, o: 0.16 + prand(i * 8.2 + 7) * 0.2 }
  })
  return (
    <Svg width={w} height={h}>
      <filter id={filterId}>
        <feTurbulence type="fractalNoise" baseFrequency="0.35" numOctaves="2" stitchTiles="stitch" />
        <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.6 0" />
      </filter>
      <rect width={w} height={h} filter={`url(#${filterId})`} opacity={0.22} />
      <g stroke={ink} strokeLinecap="round">
        {lines.map((l, i) => (
          <line key={i} x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} strokeWidth={1.4} opacity={l.o} />
        ))}
      </g>
    </Svg>
  )
}

// ── 4. Confetti Burst — scattered celebratory shapes ──
function ConfettiBurst({ palette, width: w, height: h }) {
  const colors = [palette.accent, palette.ink]
  const shapes = Array.from({ length: 44 }, (_, i) => ({
    x: prand(i * 2.13 + 1),
    y: prand(i * 3.71 + 7),
    size: 5 + prand(i * 5.5 + 3) * 9,
    rot: prand(i * 6.1 + 9) * 360,
    kind: Math.floor(prand(i * 1.7 + 2) * 3),
    color: colors[i % colors.length],
    o: 0.35 + prand(i * 7.7 + 2) * 0.4,
  }))
  return (
    <Svg width={w} height={h}>
      {shapes.map((s, i) => {
        const cx = s.x * w, cy = s.y * h
        const t = `rotate(${s.rot} ${cx} ${cy})`
        if (s.kind === 0) return <circle key={i} cx={cx} cy={cy} r={s.size / 2} fill={s.color} opacity={s.o} />
        if (s.kind === 1) return <rect key={i} x={cx - s.size / 2} y={cy - s.size / 2} width={s.size} height={s.size} fill={s.color} opacity={s.o} transform={t} />
        return <polygon key={i} points={`${cx},${cy - s.size / 2} ${cx + s.size / 2},${cy + s.size / 2} ${cx - s.size / 2},${cy + s.size / 2}`} fill={s.color} opacity={s.o} transform={t} />
      })}
    </Svg>
  )
}

// ── 5. Geometric Shards — bold translucent triangles anchored at corners ──
function GeometricShards({ palette, width: w, height: h }) {
  const accent = palette.accent
  const ink = palette.ink
  return (
    <Svg width={w} height={h}>
      <polygon points={`0,0 ${w * 0.34},0 0,${h * 0.28}`} fill={accent} opacity={0.14} />
      <polygon points={`${w},${h} ${w * 0.62},${h} ${w},${h * 0.7}`} fill={accent} opacity={0.14} />
      <polygon points={`${w},0 ${w},${h * 0.16} ${w * 0.84},0`} fill={ink} opacity={0.08} />
      <polygon points={`0,${h} 0,${h * 0.84} ${w * 0.16},${h}`} fill={ink} opacity={0.08} />
    </Svg>
  )
}

// ── 6. Chalkboard Dust — soft chalky haze + hand-drawn arcs ──
function ChalkboardDust({ palette, width: w, height: h }) {
  // Chalk marks drawn in the ink colour (not primary/background) so they
  // actually contrast — a "chalk" stroke the same shade as the board is
  // invisible regardless of how chalky it looks up close.
  const chalk = palette.ink
  const filterId = useFilterId('bg-chalk-dust')
  return (
    <Svg width={w} height={h}>
      <filter id={filterId}>
        <feTurbulence type="fractalNoise" baseFrequency="0.012 0.02" numOctaves="2" stitchTiles="stitch" />
        <feColorMatrix values="0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 0 0.5  0 0 0 0.16 0" />
      </filter>
      <rect width={w} height={h} filter={`url(#${filterId})`} opacity={0.6} />
      <path d={`M ${w * 0.06} ${h * 0.9} Q ${w * 0.16} ${h * 0.82} ${w * 0.28} ${h * 0.9}`} stroke={chalk} strokeWidth={2.5} fill="none" opacity={0.24} strokeDasharray="1 4" strokeLinecap="round" />
      <path d={`M ${w * 0.72} ${h * 0.1} Q ${w * 0.84} ${h * 0.18} ${w * 0.94} ${h * 0.08}`} stroke={chalk} strokeWidth={2.5} fill="none" opacity={0.24} strokeDasharray="1 4" strokeLinecap="round" />
      <circle cx={w * 0.14} cy={h * 0.18} r={30} stroke={chalk} strokeWidth={2} fill="none" opacity={0.16} strokeDasharray="1 5" />
    </Svg>
  )
}

// ── 7. Halftone Pop — comic-style dot burst radiating from one corner ──
function HalftonePop({ palette, width: w, height: h }) {
  const accent = palette.accent
  const cols = 14, rows = 9
  const originX = w, originY = 0
  const maxR = Math.hypot(w, h) * 0.55
  const dots = []
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const cx = (c + 0.5) * (w / cols)
      const cy = (r + 0.5) * (h / rows * 0.6)
      const dist = Math.hypot(cx - originX, cy - originY)
      const radius = Math.max(0, 9 - (dist / maxR) * 9)
      if (radius > 0.6) dots.push({ cx, cy, radius })
    }
  }
  return (
    <Svg width={w} height={h}>
      <g fill={accent} opacity={0.4}>
        {dots.map((d, i) => <circle key={i} cx={d.cx} cy={d.cy} r={d.radius} />)}
      </g>
    </Svg>
  )
}

// ── 8. Vintage Vignette — worn-photograph edges + faint noise + scratches ──
function VintageVignette({ palette, width: w, height: h }) {
  const ink = palette.ink
  const filterId = useFilterId('bg-vintage-grain')
  const lines = Array.from({ length: 5 }, (_, i) => ({
    x: prand(i * 4.1 + 3) * w,
    o: 0.08 + prand(i * 6.6 + 8) * 0.09,
  }))
  return (
    <>
      <div style={{ ...overlayBox, background: `radial-gradient(ellipse at center, transparent 50%, ${ink}38 100%)` }} />
      <Svg width={w} height={h}>
        <filter id={filterId}>
          <feTurbulence type="fractalNoise" baseFrequency="0.8" numOctaves="2" stitchTiles="stitch" />
          <feColorMatrix values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.4 0" />
        </filter>
        <rect width={w} height={h} filter={`url(#${filterId})`} opacity={0.2} />
        {lines.map((l, i) => (
          <line key={i} x1={l.x} y1={0} x2={l.x} y2={h} stroke={ink} strokeWidth={0.8} opacity={l.o} />
        ))}
      </Svg>
    </>
  )
}

export const BACKGROUND_STYLES = [
  { key: 'none', label: 'Clean', hint: 'No extra texture — just the template default' },
  { key: 'grunge', label: 'Grunge Spray', hint: 'Spray-can blots in the corners', Component: GrungeSpray },
  { key: 'torn', label: 'Torn Paper', hint: 'Ragged torn edge, top & bottom', Component: TornPaper },
  { key: 'scratch', label: 'Scratch & Distress', hint: 'Fine scratches + dust', Component: ScratchDistress },
  { key: 'confetti', label: 'Confetti Burst', hint: 'Celebratory scattered shapes', Component: ConfettiBurst },
  { key: 'geometric', label: 'Geometric Shards', hint: 'Bold angular corner blocks', Component: GeometricShards },
  { key: 'chalk', label: 'Chalkboard Dust', hint: 'Soft chalky haze + doodles', Component: ChalkboardDust },
  { key: 'halftonepop', label: 'Halftone Pop', hint: 'Comic-style dot burst', Component: HalftonePop },
  { key: 'vintage', label: 'Vintage Vignette', hint: 'Worn-photo edges + grain', Component: VintageVignette },
]

// Renders the chosen texture (or nothing, for 'none') on top of a template's
// own content. Sits as the last child of the 1080×1080 (or 1920×1080, for
// scorecards) post so it reads as a finish over the whole design.
export function BackgroundLayer({ styleKey, palette, width = 1080, height = 1080 }) {
  const entry = BACKGROUND_STYLES.find((s) => s.key === styleKey)
  if (!entry || !entry.Component || !palette) return null
  const Texture = entry.Component
  return <Texture palette={palette} width={width} height={height} />
}
