// ─────────────────────────────────────────────────────────────────────────────
// DESIGN EFFECTS for BetterPosts blocks: frames (masks), photo looks (colour
// splash, black and white, duotone, tint, grain), and the drawn textures
// (brush stroke, splatter, speed lines, torn paper, halftone, burst, grunge).
//
// Everything here is described by plain settings stored on the block, never by a
// baked picture: a block keeps its original `src` and the processed copy is made
// in the browser from `src + fx` each time it is drawn, then cached. So an
// effect can always be changed or taken off, a saved template carries no `blob:`
// URL, and a club library photo is never overwritten.
//
// Only things that the PNG export (modern-screenshot) paints are used:
// clip-path, mask-image, CSS filter drop-shadow, opacity, plain SVG. Never
// backdrop-filter. Pixel work happens on a canvas before the picture reaches
// the DOM, so the export sees an ordinary <img>.
// ─────────────────────────────────────────────────────────────────────────────
import { useEffect, useState } from 'react'

// ── Seeded random ────────────────────────────────────────────────────────────
// A texture or a torn frame is drawn from its `seed`, so it looks the same in
// the editor, the preview and the export, and "Shuffle" just picks a new seed.
export function rng(seed = 1) {
  let s = (Math.floor(Math.abs(seed)) % 2147483646) + 1
  return () => {
    s = (s * 16807) % 2147483647
    return (s - 1) / 2147483646
  }
}
export const newSeed = () => Math.floor(Math.random() * 1e9) + 1

// ── Frames ───────────────────────────────────────────────────────────────────
// Points are in 0..100 of the frame box. `pop` is where a cut-out may rise out
// of the frame: the share of the frame's height above which the photo shows
// unclipped when "Pop out" is on (0 = the top edge; 0.5 = halfway down a circle,
// so a head sits over the ring rather than being cut off by its top).
const arc = (cx, cy, rx, ry, a0, a1, n) => {
  const out = []
  for (let i = 0; i <= n; i++) {
    const a = (a0 + ((a1 - a0) * i) / n) * Math.PI / 180
    out.push([cx + rx * Math.cos(a), cy + ry * Math.sin(a)])
  }
  return out
}

function tornPoints(seed) {
  const r = rng(seed)
  const pts = []
  const steps = 28
  for (let i = 0; i <= steps; i++) pts.push([(i / steps) * 100, 1 + r() * 4])
  for (let i = 0; i <= 12; i++) pts.push([97 + r() * 3, (i / 12) * 100])
  for (let i = steps; i >= 0; i--) pts.push([(i / steps) * 100, 95 + r() * 4.5])
  for (let i = 12; i >= 0; i--) pts.push([r() * 3, (i / 12) * 100])
  return pts
}

export const FRAMES = [
  { key: 'none', name: 'None' },
  { key: 'rounded', name: 'Rounded', pop: 0 },
  { key: 'circle', name: 'Circle', ellipse: true, pop: 0.5 },
  { key: 'vbottom', name: 'V base', pts: [[0, 0], [100, 0], [100, 74], [50, 100], [0, 74]], pop: 0 },
  { key: 'shield', name: 'Shield', pts: [[0, 0], [100, 0], [100, 58], ...arc(50, 58, 50, 42, 0, 180, 16).slice(1, -1), [0, 58]], pop: 0 },
  { key: 'arch', name: 'Arch', pts: [...arc(50, 50, 50, 50, 180, 360, 18), [100, 100], [0, 100]], pop: 0.5 },
  { key: 'slant', name: 'Slant', pts: [[14, 0], [100, 0], [86, 100], [0, 100]], pop: 0 },
  { key: 'slash', name: 'Slash top', pts: [[0, 22], [100, 0], [100, 100], [0, 100]], pop: 0.1 },
  { key: 'triangle', name: 'Triangle', pts: [[50, 0], [100, 100], [0, 100]], pop: 0.55 },
  { key: 'tribase', name: 'Point down', pts: [[0, 0], [100, 0], [50, 100]], pop: 0 },
  { key: 'diamond', name: 'Diamond', pts: [[50, 0], [100, 50], [50, 100], [0, 50]], pop: 0.5 },
  { key: 'hexagon', name: 'Hexagon', pts: [[25, 0], [75, 0], [100, 50], [75, 100], [25, 100], [0, 50]], pop: 0.5 },
  { key: 'chevron', name: 'Chevron', pts: [[0, 0], [50, 18], [100, 0], [100, 82], [50, 100], [0, 82]], pop: 0.18 },
  { key: 'star', name: 'Star', pts: [[50, 0], [61, 35], [98, 35], [68, 57], [79, 91], [50, 70], [21, 91], [32, 57], [2, 35], [39, 35]], pop: 0.5 },
  { key: 'torn', name: 'Torn edge', torn: true, pop: 0.05 },
  { key: 'brush', name: 'Brush', brush: true, pop: 0.3 },
]
export const frameOf = (key) => FRAMES.find((f) => f.key === key) || null

export function framePoints(frame, seed) {
  if (!frame) return null
  if (frame.torn) return tornPoints(seed || 7)
  if (frame.ellipse) return arc(50, 50, 50, 50, 0, 360, 48)
  return frame.pts || null
}

// clip-path for a frame drawn inside a box that is `lift` px taller than the
// frame at the top (the room a popped-out head needs). y is remapped so the
// shape still sits on the frame, not on the taller box.
export function frameClip(points, h, lift = 0) {
  if (!points) return undefined
  const total = h + lift
  const map = ([x, y]) => `${x.toFixed(2)}% ${(((lift + (y / 100) * h) / total) * 100).toFixed(3)}%`
  return `polygon(${points.map(map).join(', ')})`
}

// ── Drawn textures (SVG strings and React-free shape data) ───────────────────
// Each returns an array of { d, opacity } paths in a w×h box, or circles.
const f1 = (n) => Math.round(n * 10) / 10

export function brushPaths(w, h, seed = 1) {
  const r = rng(seed)
  const paths = []
  // Body: a band with rough top and bottom edges, tapering at both ends.
  const n = 40
  const top = []
  const bot = []
  for (let i = 0; i <= n; i++) {
    const t = i / n
    const x = t * w
    const taper = Math.pow(Math.sin(Math.PI * Math.min(1, 0.08 + t * 0.92)), 0.35)
    const half = (h * 0.36) * taper
    const wob = Math.sin(t * Math.PI * 1.3 + seed) * h * 0.05
    top.push([x, h / 2 - half + wob + (r() - 0.5) * h * 0.08])
    bot.push([x, h / 2 + half + wob + (r() - 0.5) * h * 0.08])
  }
  const body = [...top, ...bot.reverse()]
  paths.push({ d: `M${body.map(([x, y]) => `${f1(x)},${f1(y)}`).join('L')}Z`, opacity: 1 })
  // Bristles: thin streaks running past the ends and along the edges.
  for (let i = 0; i < 26; i++) {
    const y = h * (0.12 + r() * 0.76)
    const x0 = -w * 0.02 + r() * w * 0.25
    const x1 = w * (0.7 + r() * 0.32)
    const t = h * (0.008 + r() * 0.03)
    paths.push({ d: `M${f1(x0)},${f1(y - t)}L${f1(x1)},${f1(y - t * 0.3)}L${f1(x1)},${f1(y + t * 0.3)}L${f1(x0)},${f1(y + t)}Z`, opacity: 0.35 + r() * 0.5 })
  }
  // Dry-brush flecks at the tail.
  for (let i = 0; i < 18; i++) {
    const cx = w * (0.82 + r() * 0.18)
    const cy = h * (0.2 + r() * 0.6)
    const rr = h * (0.006 + r() * 0.02)
    paths.push({ d: circlePath(cx, cy, rr), opacity: 0.5 + r() * 0.5 })
  }
  return paths
}

function circlePath(cx, cy, r) {
  return `M${f1(cx - r)},${f1(cy)}a${f1(r)},${f1(r)} 0 1,0 ${f1(r * 2)},0a${f1(r)},${f1(r)} 0 1,0 ${f1(-r * 2)},0Z`
}

function blobPath(cx, cy, rad, r, spikes = 18, rough = 0.35) {
  const pts = []
  const n = spikes * 2
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2
    const k = i % 2 === 0 ? 1 + r() * rough : 1 - r() * rough * 0.6
    pts.push([cx + Math.cos(a) * rad * k, cy + Math.sin(a) * rad * k])
  }
  return `M${pts.map(([x, y]) => `${f1(x)},${f1(y)}`).join('L')}Z`
}

export function splatterPaths(w, h, seed = 1) {
  const r = rng(seed)
  const paths = []
  const m = Math.min(w, h)
  const cx = w / 2
  const cy = h / 2
  paths.push({ d: blobPath(cx, cy, m * 0.24, r, 16, 0.4), opacity: 1 })
  for (let i = 0; i < 4; i++) {
    paths.push({ d: blobPath(cx + (r() - 0.5) * m * 0.35, cy + (r() - 0.5) * m * 0.35, m * (0.08 + r() * 0.08), r, 10, 0.4), opacity: 1 })
  }
  // Drops thrown outward, smaller the further they travel.
  for (let i = 0; i < 70; i++) {
    const a = r() * Math.PI * 2
    const dist = m * (0.26 + Math.pow(r(), 0.7) * 0.26)
    const rr = m * 0.028 * (1 - (dist / m - 0.26) / 0.3) * (0.3 + r())
    if (rr <= 0.4) continue
    const x = cx + Math.cos(a) * dist * (w / m)
    const y = cy + Math.sin(a) * dist * (h / m)
    paths.push({ d: circlePath(x, y, rr), opacity: 1 })
  }
  // A few streaks pointing away from the centre.
  for (let i = 0; i < 9; i++) {
    const a = r() * Math.PI * 2
    const d0 = m * 0.2
    const d1 = m * (0.3 + r() * 0.18)
    const t = m * (0.008 + r() * 0.012)
    const ux = Math.cos(a)
    const uy = Math.sin(a)
    const px = -uy * t
    const py = ux * t
    const x0 = cx + ux * d0
    const y0 = cy + uy * d0
    const x1 = cx + ux * d1
    const y1 = cy + uy * d1
    paths.push({ d: `M${f1(x0 + px)},${f1(y0 + py)}L${f1(x1)},${f1(y1)}L${f1(x0 - px)},${f1(y0 - py)}Z`, opacity: 1 })
  }
  return paths
}

export function speedPaths(w, h, seed = 1) {
  const r = rng(seed)
  const paths = []
  for (let i = 0; i < 34; i++) {
    const y = r() * h
    const len = w * (0.25 + r() * 0.75)
    const x0 = r() * (w - len)
    const t = h * (0.003 + r() * 0.012)
    paths.push({ d: `M${f1(x0)},${f1(y)}L${f1(x0 + len)},${f1(y - t)}L${f1(x0 + len)},${f1(y + t)}Z`, opacity: 0.3 + r() * 0.7 })
  }
  return paths
}

export function tornPaperPaths(w, h, seed = 1) {
  const r = rng(seed)
  const top = []
  const bot = []
  const n = 46
  for (let i = 0; i <= n; i++) {
    const x = (i / n) * w
    top.push([x, h * (0.02 + r() * 0.1)])
    bot.push([x, h * (0.88 + r() * 0.1)])
  }
  const pts = [...top, ...bot.reverse()]
  return [{ d: `M${pts.map(([x, y]) => `${f1(x)},${f1(y)}`).join('L')}Z`, opacity: 1 }]
}

export function burstPaths(w, h, seed = 1) {
  const r = rng(seed)
  const paths = []
  const cx = w / 2
  const cy = h / 2
  const R = Math.hypot(w, h)
  const rays = 18 + Math.floor(r() * 10)
  for (let i = 0; i < rays; i++) {
    const a0 = (i / rays) * Math.PI * 2
    const a1 = a0 + (Math.PI * 2 / rays) * (0.35 + r() * 0.2)
    paths.push({ d: `M${f1(cx)},${f1(cy)}L${f1(cx + Math.cos(a0) * R)},${f1(cy + Math.sin(a0) * R)}L${f1(cx + Math.cos(a1) * R)},${f1(cy + Math.sin(a1) * R)}Z`, opacity: 1 })
  }
  return paths
}

export function grungePaths(w, h, seed = 1) {
  const r = rng(seed)
  const paths = []
  for (let i = 0; i < 40; i++) {
    const x = r() * w
    const y = r() * h
    const len = Math.min(w, h) * (0.05 + r() * 0.3)
    const a = (r() - 0.5) * 0.8
    const t = 0.6 + r() * 1.8
    const x1 = x + Math.cos(a) * len
    const y1 = y + Math.sin(a) * len
    paths.push({ d: `M${f1(x)},${f1(y)}L${f1(x1)},${f1(y1 - t)}L${f1(x1)},${f1(y1 + t)}Z`, opacity: 0.25 + r() * 0.6 })
  }
  for (let i = 0; i < 160; i++) {
    paths.push({ d: circlePath(r() * w, r() * h, 0.6 + r() * 2.6), opacity: 0.2 + r() * 0.7 })
  }
  return paths
}

// Halftone is a grid of dots shrinking across the box (left to right; rotate
// the block for any other direction).
export function halftoneDots(w, h, size = 22) {
  const dots = []
  const cols = Math.max(1, Math.ceil(w / size))
  const rows = Math.max(1, Math.ceil(h / size))
  for (let j = 0; j < rows; j++) {
    for (let i = 0; i < cols; i++) {
      const t = 1 - i / cols
      const rr = (size / 2) * 0.95 * t
      if (rr < 0.5) continue
      dots.push([f1(i * size + size / 2 + (j % 2 ? size / 2 : 0)), f1(j * size + size / 2), f1(rr)])
    }
  }
  return dots
}

export const TEXTURES = {
  brush: brushPaths,
  splatter: splatterPaths,
  speed: speedPaths,
  torn: tornPaperPaths,
  burst: burstPaths,
  grunge: grungePaths,
}

// Brush-shaped frame: the brush body as an SVG mask, white on clear.
export function brushMaskUrl(seed = 1) {
  const W = 1000
  const H = 600
  const paths = brushPaths(W, H, seed).map((p) => `<path d="${p.d}" fill="#fff" fill-opacity="${p.opacity}"/>`).join('')
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">${paths}</svg>`
  return `url("data:image/svg+xml;utf8,${encodeURIComponent(svg)}")`
}

// ── Colour helpers ───────────────────────────────────────────────────────────
export function parseColor(c) {
  if (!c || typeof c !== 'string') return null
  let s = c.trim()
  if (s[0] === '#') {
    s = s.slice(1)
    if (s.length === 3) s = s.split('').map((x) => x + x).join('')
    if (s.length >= 6) {
      const n = parseInt(s.slice(0, 6), 16)
      if (!Number.isNaN(n)) return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
    }
    return null
  }
  const m = s.match(/rgba?\(([^)]+)\)/)
  if (m) {
    const p = m[1].split(/[ ,/]+/).map(Number)
    if (p.length >= 3 && p.every((x, i) => i > 2 || Number.isFinite(x))) return [p[0], p[1], p[2]]
  }
  return null
}

export const toHex = ([r, g, b]) => `#${[r, g, b].map((v) => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')}`

// sRGB (0-255) to CIE Lab (D65). The table makes the gamma step a lookup.
const LIN = new Float32Array(256)
for (let i = 0; i < 256; i++) { const c = i / 255; LIN[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4) }
const labF = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116)
export function rgbToLab(r, g, b) {
  const R = LIN[Math.max(0, Math.min(255, Math.round(r)))]
  const G = LIN[Math.max(0, Math.min(255, Math.round(g)))]
  const B = LIN[Math.max(0, Math.min(255, Math.round(b)))]
  const x = labF((R * 0.4124 + G * 0.3576 + B * 0.1805) / 0.95047)
  const y = labF(R * 0.2126 + G * 0.7152 + B * 0.0722)
  const z = labF((R * 0.0193 + G * 0.1192 + B * 0.9505) / 1.08883)
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)]
}

// Colour splash sliders, both 0 to 100. Range is how far (in Lab distance) a
// colour may sit from the kept one and still stay in colour; it is eased so
// the low end gives fine control and 100 reaches almost every colour. Softness
// is the width of the fade from kept to black and white. Lightness counts for
// less than hue and saturation, so a kit in shadow is still the kit.
export const SPLASH_DEFAULT = { range: 30, soft: 30 }
const SPLASH_L_WEIGHT = 0.28
export function splashReach(range, soft) {
  const r = Math.max(0, Math.min(100, Number(range) || 0)) / 100
  const k = Math.max(0, Math.min(100, Number(soft) || 0)) / 100
  return { tol: 2 + 128 * Math.pow(r, 1.35), feather: 1 + 90 * Math.pow(k, 1.1) }
}

export function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return [0, 0, l]
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h
  if (max === r) h = (g - b) / d + (g < b ? 6 : 0)
  else if (max === g) h = (b - r) / d + 2
  else h = (r - g) / d + 4
  return [h * 60, s, l]
}

// ── Photo looks ──────────────────────────────────────────────────────────────
// fx (all optional, absent = untouched):
//   brightness, contrast, saturation   -100..100
//   tone      'none' | 'mono' | 'duotone' | 'tint'
//   duoDark, duoLight                  resolved colours for duotone
//   tint, tintAmount                   resolved colour, 0..100
//   splash    [{ color, range, soft }] keep these hues in colour, the rest goes to the tone
//   splashStrength                     0..100 (how fully the rest is toned)
//   grain                              0..100
//   silhouette                         a colour: the picture's shape filled flat
//   edgeOutline { width, color }, edgeGlow { size, color }   baked into the
//                 picture (for built-in layouts, which draw a plain <img>)
export const PIXEL_KEYS = ['brightness', 'contrast', 'saturation', 'tone', 'duoDark', 'duoLight', 'tint', 'tintAmount', 'splash', 'splashStrength', 'grain', 'silhouette', 'edgeOutline', 'edgeGlow']

export function needsPixels(fx) {
  if (!fx) return false
  if (fx.silhouette) return true
  if ((fx.edgeOutline && fx.edgeOutline.width > 0) || (fx.edgeGlow && fx.edgeGlow.size > 0)) return true
  if (fx.tone && fx.tone !== 'none') return true
  if (Array.isArray(fx.splash) && fx.splash.length) return true
  return !!(fx.brightness || fx.contrast || fx.saturation || fx.grain)
}

export function pixelKey(fx) {
  const o = {}
  for (const k of PIXEL_KEYS) if (fx && fx[k] !== undefined && fx[k] !== null && fx[k] !== '') o[k] = fx[k]
  return JSON.stringify(o)
}

const smooth = (e0, e1, x) => {
  if (e1 <= e0) return x >= e1 ? 1 : 0
  const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0)))
  return t * t * (3 - 2 * t)
}

// The pixel pass itself. Works in place on an ImageData-like { data }.
export function applyPixels(data, fx, seed = 1) {
  const d = data
  const br = (fx.brightness || 0) * 1.28
  const ct = fx.contrast || 0
  const cf = (259 * (ct * 1.28 + 255)) / (255 * (259 - ct * 1.28))
  const sat = 1 + (fx.saturation || 0) / 100
  const splash = Array.isArray(fx.splash) ? fx.splash.map((s) => {
    const c = parseColor(s.color)
    if (!c) return null
    const [L, A, B] = rgbToLab(c[0], c[1], c[2])
    const { tol, feather } = splashReach(s.range ?? SPLASH_DEFAULT.range, s.soft ?? SPLASH_DEFAULT.soft)
    return { L, A, B, tol, feather }
  }).filter(Boolean) : []
  const tone = fx.tone && fx.tone !== 'none' ? fx.tone : (splash.length ? 'mono' : 'none')
  const strength = splash.length ? (fx.splashStrength ?? 100) / 100 : 1
  const dark = parseColor(fx.duoDark) || [10, 10, 10]
  const light = parseColor(fx.duoLight) || [255, 255, 255]
  const tint = parseColor(fx.tint) || [225, 6, 0]
  const tintAmt = (fx.tintAmount ?? 70) / 100
  const grain = (fx.grain || 0) * 0.9
  const sil = fx.silhouette ? parseColor(fx.silhouette) : null
  const rand = rng(seed)

  for (let i = 0; i < d.length; i += 4) {
    if (sil) { d[i] = sil[0]; d[i + 1] = sil[1]; d[i + 2] = sil[2]; continue }
    let r = d[i]
    let g = d[i + 1]
    let b = d[i + 2]
    if (br) { r += br; g += br; b += br }
    if (ct) { r = cf * (r - 128) + 128; g = cf * (g - 128) + 128; b = cf * (b - 128) + 128 }
    if (sat !== 1) {
      const l0 = 0.2126 * r + 0.7152 * g + 0.0722 * b
      r = l0 + (r - l0) * sat; g = l0 + (g - l0) * sat; b = l0 + (b - l0) * sat
    }
    r = r < 0 ? 0 : r > 255 ? 255 : r
    g = g < 0 ? 0 : g > 255 ? 255 : g
    b = b < 0 ? 0 : b > 255 ? 255 : b
    const lum = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
    let tr = r
    let tg = g
    let tb = b
    if (tone === 'mono') { tr = tg = tb = lum * 255 }
    else if (tone === 'duotone') {
      tr = dark[0] + (light[0] - dark[0]) * lum
      tg = dark[1] + (light[1] - dark[1]) * lum
      tb = dark[2] + (light[2] - dark[2]) * lum
    } else if (tone === 'tint') {
      const gr = lum * 255
      // Multiply the grey by the tint, then lift the highlights back a little
      // so whites stay white-ish rather than going flat.
      const mr = (gr * tint[0]) / 255
      const mg = (gr * tint[1]) / 255
      const mb = (gr * tint[2]) / 255
      const hl = smooth(0.7, 1, lum)
      tr = gr + ((mr + (gr - mr) * hl * 0.6) - gr) * tintAmt
      tg = gr + ((mg + (gr - mg) * hl * 0.6) - gr) * tintAmt
      tb = gr + ((mb + (gr - mb) * hl * 0.6) - gr) * tintAmt
    }
    let keep = 0
    if (splash.length) {
      // Distance in Lab, the way people judge colour: a jersey's shadows and
      // highlights stay close to its colour, a different colour does not.
      const [L, A, B] = rgbToLab(r, g, b)
      for (const s of splash) {
        const dl = (L - s.L) * SPLASH_L_WEIGHT
        const d = Math.sqrt(dl * dl + (A - s.A) * (A - s.A) + (B - s.B) * (B - s.B))
        const w = 1 - smooth(s.tol, s.tol + s.feather, d)
        if (w > keep) keep = w
        if (keep >= 1) break
      }
    }
    const mix = (1 - keep) * strength
    r = r + (tr - r) * mix
    g = g + (tg - g) * mix
    b = b + (tb - b) * mix
    if (grain) {
      const n = (rand() - 0.5) * grain
      r += n; g += n; b += n
    }
    d[i] = r; d[i + 1] = g; d[i + 2] = b
  }
  return data
}

// ── Processing, cache and the hook ───────────────────────────────────────────
const MAX_SIDE = 1600
const cache = new Map() // key -> { url, promise }
const pending = new Set()
let scheduled = 0

function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    if (!/^(blob:|data:)/.test(src)) {
      try {
        const u = new URL(src, window.location.href)
        if (u.origin !== window.location.origin) img.crossOrigin = 'anonymous'
      } catch { /* relative or odd URL: same origin */ }
    }
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('Could not load the picture'))
    img.src = src
  })
}

export async function processImage(src, fx) {
  const img = await loadImage(src)
  const k = Math.min(1, MAX_SIDE / Math.max(img.naturalWidth || 1, img.naturalHeight || 1))
  const w = Math.max(1, Math.round((img.naturalWidth || 1) * k))
  const h = Math.max(1, Math.round((img.naturalHeight || 1) * k))
  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const ctx = c.getContext('2d', { willReadFrequently: true })
  ctx.drawImage(img, 0, 0, w, h)
  const id = ctx.getImageData(0, 0, w, h) // throws on a tainted (cross-origin) picture
  applyPixels(id.data, fx, 1)
  ctx.putImageData(id, 0, 0)
  const out = bakeEdges(c, fx, k)
  const blob = await new Promise((res) => out.toBlob(res, 'image/png'))
  if (!blob) throw new Error('Could not process the picture')
  return URL.createObjectURL(blob)
}

// An outline or glow round a cut-out, painted into the picture itself. The
// canvas grows by the edge width so nothing is clipped; widths are in the
// original picture's pixels (scaled by k when it was shrunk).
function bakeEdges(src, fx, k = 1) {
  const ow = fx.edgeOutline && fx.edgeOutline.width > 0 ? Math.max(1, Math.round(fx.edgeOutline.width * k)) : 0
  const gs = fx.edgeGlow && fx.edgeGlow.size > 0 ? Math.max(1, Math.round(fx.edgeGlow.size * k)) : 0
  if (!ow && !gs) return src
  const pad = ow + gs * 2
  const c = document.createElement('canvas')
  c.width = src.width + pad * 2
  c.height = src.height + pad * 2
  const ctx = c.getContext('2d')
  if (gs) {
    ctx.save()
    ctx.shadowColor = fx.edgeGlow.color || '#ffc233'
    ctx.shadowBlur = gs
    for (let i = 0; i < 3; i++) ctx.drawImage(src, pad, pad)
    ctx.restore()
  }
  if (ow) {
    // A flat copy in the outline colour, stamped round a circle of radius ow.
    const sil = document.createElement('canvas')
    sil.width = src.width
    sil.height = src.height
    const sx = sil.getContext('2d')
    sx.drawImage(src, 0, 0)
    sx.globalCompositeOperation = 'source-in'
    sx.fillStyle = fx.edgeOutline.color || '#ffffff'
    sx.fillRect(0, 0, sil.width, sil.height)
    const steps = Math.max(12, Math.round(ow * 2))
    for (let i = 0; i < steps; i++) {
      const a = (i / steps) * Math.PI * 2
      ctx.drawImage(sil, pad + Math.cos(a) * ow, pad + Math.sin(a) * ow)
    }
  }
  ctx.drawImage(src, pad, pad)
  return c
}

function touch(key, entry) {
  cache.delete(key)
  cache.set(key, entry)
  while (cache.size > 80) {
    const [k0, e0] = cache.entries().next().value
    cache.delete(k0)
    if (e0.url && e0.url.startsWith('blob:')) setTimeout(() => URL.revokeObjectURL(e0.url), 60000)
  }
}

export function fxSrcSync(src, fx) {
  if (!src || !needsPixels(fx)) return src
  const e = cache.get(`${src}|${pixelKey(fx)}`)
  return e && e.url ? e.url : null
}

function startProcess(key, src, fx) {
  const have = cache.get(key)
  if (have) return have.promise
  const entry = { url: null, failed: false, promise: null }
  entry.promise = processImage(src, fx)
    .then((url) => { entry.url = url; return url })
    .catch(() => { entry.failed = true; entry.url = src; return src })
    .finally(() => pending.delete(entry.promise))
  pending.add(entry.promise)
  touch(key, entry)
  return entry.promise
}

// The processed picture for a block. Returns the original `src` until the
// processed copy is ready (and keeps it if processing fails, with `failed`).
export function useFxSrc(src, fx) {
  const on = !!src && needsPixels(fx)
  const key = on ? `${src}|${pixelKey(fx)}` : null
  const [state, setState] = useState(() => {
    if (!key) return { key: null, url: src, failed: false }
    const e = cache.get(key)
    return { key, url: e && e.url ? e.url : null, failed: !!(e && e.failed) }
  })
  useEffect(() => {
    if (!key) return undefined
    const e = cache.get(key)
    if (e && e.url) { setState({ key, url: e.url, failed: e.failed }); return undefined }
    let live = true
    // A slider drag fires many changes; wait for it to settle before redrawing
    // a 1600px picture. The export waits on `scheduled` too.
    scheduled++
    let fired = false
    const t = setTimeout(() => {
      fired = true
      scheduled--
      startProcess(key, src, fx).then((url) => {
        const got = cache.get(key)
        if (live) setState({ key, url, failed: !!(got && got.failed) })
      })
    }, e ? 0 : 110)
    return () => {
      live = false
      if (!fired) { clearTimeout(t); scheduled = Math.max(0, scheduled - 1) }
    }
    // fx is fully described by key
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, src])
  if (!key) return { url: src, ready: true, failed: false }
  if (state.key === key && state.url) return { url: state.url, ready: true, failed: state.failed }
  // While the new look is being made, hold the last processed picture for this
  // src rather than flashing back to the untouched photo.
  return { url: state.url || null, ready: false, failed: false }
}

// Many pictures under one look (every photo a built-in layout draws). Returns a
// lookup from original URL to the processed one; a URL still being made maps
// to itself. Re-renders once each picture is ready.
export function useFxUrls(urls, fx) {
  const on = needsPixels(fx)
  const list = on ? [...new Set((urls || []).filter(Boolean))] : []
  const pk = on ? pixelKey(fx) : ''
  const [, bump] = useState(0)
  const sig = list.join('\n') + '|' + pk
  useEffect(() => {
    if (!on || !list.length) return undefined
    let live = true
    scheduled++
    let fired = false
    const t = setTimeout(() => {
      fired = true
      scheduled--
      Promise.all(list.map((u) => startProcess(`${u}|${pk}`, u, fx))).then(() => { if (live) bump((n) => n + 1) })
    }, 110)
    return () => { live = false; if (!fired) { clearTimeout(t); scheduled = Math.max(0, scheduled - 1) } }
    // sig covers list and fx
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sig])
  return (u) => {
    if (!on || !u) return u
    const e = cache.get(`${u}|${pk}`)
    return e && e.url ? e.url : u
  }
}

// The photo fields a built-in layout's props carry (player cut-outs, the Hero
// Image upload, the player of the match). Logos and crests are never touched.
export const PHOTO_KEYS = new Set(['headshot', 'hero', 'action', 'photo', 'heroImage', 'cutout'])
export function collectPhotos(value, out = [], depth = 0) {
  if (!value || depth > 6) return out
  if (Array.isArray(value)) { value.forEach((v) => collectPhotos(v, out, depth + 1)); return out }
  if (typeof value === 'object') {
    for (const [k, v] of Object.entries(value)) {
      if (PHOTO_KEYS.has(k) && typeof v === 'string' && v) out.push(v)
      else if (v && typeof v === 'object' && !(v.$$typeof)) collectPhotos(v, out, depth + 1)
    }
  }
  return out
}
export function mapPhotos(value, get, depth = 0) {
  if (!value || depth > 6) return value
  if (Array.isArray(value)) return value.map((v) => mapPhotos(v, get, depth + 1))
  if (typeof value === 'object' && !(value.$$typeof)) {
    const out = {}
    for (const [k, v] of Object.entries(value)) {
      out[k] = PHOTO_KEYS.has(k) && typeof v === 'string' ? get(v) : (v && typeof v === 'object' ? mapPhotos(v, get, depth + 1) : v)
    }
    return out
  }
  return value
}

// Called by the PNG export before it paints, so a look still being made is
// waited for rather than exported half-done.
export async function waitForFx(timeoutMs = 8000) {
  const t0 = Date.now()
  while ((pending.size || scheduled > 0) && Date.now() - t0 < timeoutMs) {
    if (pending.size) await Promise.race([Promise.all([...pending]), new Promise((r) => setTimeout(r, 200))])
    else await new Promise((r) => setTimeout(r, 60))
  }
  // Let React draw the finished pictures before the export reads the DOM.
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))
}

// ── CSS for the cut-out effects ──────────────────────────────────────────────
// outline: { width, color }   glow: { size, color }   shadow: { x, y, blur, color, opacity }
export function cutoutFilter(fx, resolve) {
  if (!fx) return undefined
  const parts = []
  if (fx.outline && fx.outline.width > 0) {
    const c = resolve(fx.outline.color || 'white')
    const w = fx.outline.width
    // Eight hard shadows read as a solid stroke round the cut-out's edge.
    const d = w * 0.7071
    ;[[w, 0], [-w, 0], [0, w], [0, -w], [d, d], [-d, d], [d, -d], [-d, -d]].forEach(([x, y]) => parts.push(`drop-shadow(${f1(x)}px ${f1(y)}px 0 ${c})`))
  }
  if (fx.glow && fx.glow.size > 0) {
    const c = resolve(fx.glow.color || 'accent')
    parts.push(`drop-shadow(0 0 ${fx.glow.size}px ${c})`, `drop-shadow(0 0 ${Math.round(fx.glow.size / 2)}px ${c})`)
  }
  if (fx.shadow && (fx.shadow.blur > 0 || fx.shadow.x || fx.shadow.y)) {
    const rgb = parseColor(resolve(fx.shadow.color || 'black')) || [0, 0, 0]
    const a = (fx.shadow.opacity ?? 60) / 100
    parts.push(`drop-shadow(${fx.shadow.x || 0}px ${fx.shadow.y || 0}px ${fx.shadow.blur || 0}px rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a}))`)
  }
  return parts.length ? parts.join(' ') : undefined
}

// ── One-click looks ──────────────────────────────────────────────────────────
// Each returns the fx to merge, from the palette's tokens (stored as tokens so
// a palette switch re-tints them).
export const LOOKS = [
  { key: 'original', name: 'Original', fx: { tone: 'none', splash: [], brightness: 0, contrast: 0, saturation: 0, grain: 0 } },
  { key: 'pop', name: 'Colour pop', fx: { tone: 'mono', splash: [{ color: 'primary', range: 30, soft: 30 }], splashStrength: 100, contrast: 12, grain: 0 } },
  { key: 'noir', name: 'Noir', fx: { tone: 'mono', splash: [], contrast: 32, brightness: -4, saturation: 0, grain: 8 } },
  { key: 'duo', name: 'Club duotone', fx: { tone: 'duotone', duoDark: 'primary', duoLight: 'accent', splash: [], contrast: 10, grain: 0 } },
  { key: 'tint', name: 'Club tint', fx: { tone: 'tint', tint: 'primary', tintAmount: 80, splash: [], contrast: 18, grain: 0 } },
  { key: 'poster', name: 'Poster', fx: { tone: 'mono', splash: [], contrast: 48, brightness: 4, grain: 22 } },
  { key: 'faded', name: 'Faded', fx: { tone: 'none', splash: [], contrast: -22, brightness: 10, saturation: -45, grain: 10 } },
  { key: 'vivid', name: 'Vivid', fx: { tone: 'none', splash: [], contrast: 18, saturation: 40, grain: 0 } },
]

// Turns fx colour tokens (primary, accent, …) into real colours for the pixel
// pass. Kept separate so the stored fx stays as tokens.
export function resolveFx(fx, resolve) {
  if (!fx) return fx
  const out = { ...fx }
  if (fx.duoDark) out.duoDark = resolve(fx.duoDark)
  if (fx.duoLight) out.duoLight = resolve(fx.duoLight)
  if (fx.tint) out.tint = resolve(fx.tint)
  if (Array.isArray(fx.splash)) out.splash = fx.splash.map((s) => ({ ...s, color: resolve(s.color) }))
  if (fx.edgeOutline) out.edgeOutline = { ...fx.edgeOutline, color: resolve(fx.edgeOutline.color || 'white') }
  if (fx.edgeGlow) out.edgeGlow = { ...fx.edgeGlow, color: resolve(fx.edgeGlow.color || 'accent') }
  return out
}
