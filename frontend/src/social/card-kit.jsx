// Small drawing parts the card-style layouts share (Round Cover, Round
// Highlights, Giant Type): a hairline corner, a hatched strip, a glow disc and
// the glass badge a club mark sits in.
//
// Each one is a plain function that returns the element itself, not a
// component, because a layout's root child has to carry its own `data-layer` for
// the Layers panel to name it (see postLayers.jsx). None uses backdrop-filter:
// the PNG export goes through modern-screenshot, which does not paint it.

// A 1px accent hairline that runs along the top edge and steps up at its end,
// the way the club's own cards are trimmed. `flip` turns it half way round for
// the opposite corner.
export function cornerLine(layer, color, { width, height, flip = false, length = 0.8, opacity = 1 }) {
  const w = Math.round(width * length)
  const d = `M 0 19.5 L ${w - 15} 19.5 L ${w} 0`
  return (
    <svg data-layer={layer} width={w} height="20" viewBox={`0 0 ${w} 20`} aria-hidden="true" style={{
      position: 'absolute', display: 'block', opacity,
      ...(flip ? { right: 0, bottom: 0, transform: 'rotate(180deg)' } : { left: 0, top: 0 }),
    }}>
      <path d={d} fill="none" stroke={color} strokeWidth="1" />
    </svg>
  )
}

// Lines every `gap` pixels at an angle, clipped to a box. Used for the hatched
// strip along the foot of the highlights cover and the faint texture on cards.
export function hatch(layer, color, { left = 0, top = 0, width, height, gap = 12, angle = -45, opacity = 0.6, radius = 0 }) {
  return (
    <div data-layer={layer} style={{
      position: 'absolute', left, top, width, height, borderRadius: radius, opacity, pointerEvents: 'none',
      backgroundImage: `repeating-linear-gradient(${angle + 90}deg, ${color} 0, ${color} 1px, transparent 1px, transparent ${gap}px)`,
    }} />
  )
}

// A soft disc of colour behind a hero. Built from a radial gradient, not a
// blurred element, so it paints the same in the editor and in the PNG.
export function glowDisc(layer, color, { left, top, size, opacity = 1 }) {
  return (
    <div data-layer={layer} style={{
      position: 'absolute', left, top, width: size, height: size, borderRadius: '50%', opacity, pointerEvents: 'none',
      background: `radial-gradient(circle at 50% 50%, ${color} 0%, ${color}cc 28%, ${color}00 72%)`,
    }} />
  )
}

// The pane a club mark sits in: white at 14%, a 1px white edge, radius 6.
export const badgeStyle = (w, h) => ({
  width: w, height: h, boxSizing: 'border-box', borderRadius: 6,
  background: 'rgba(255,255,255,0.14)', border: '1px solid rgba(255,255,255,0.9)',
  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: Math.round(h * 0.12),
})

// The colour the glow behind a hero takes. A club that has set a coloured
// secondary gets it; one on the neutral default (a near-grey) gets a deep shade
// of its accent, so the card is never a flat grey slab.
export function glowColor(palette = {}, mix) {
  const sec = palette.secondary || ''
  const h = String(sec).replace('#', '')
  const ok = h.length >= 6
  const rgb = ok ? [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)] : [128, 128, 128]
  const spread = Math.max(...rgb) - Math.min(...rgb)
  if (ok && spread > 40) return sec
  return mix(palette.accent || '#16c784', palette.primary || '#101113', 0.68)
}

// Surnames and first names come in upper case from some imports ("MINTER-BROWN").
export function niceName(s) {
  const t = String(s || '').trim()
  if (!t || t !== t.toUpperCase()) return t
  return t.toLowerCase().replace(/(^|[\s\-'])([a-z])/g, (m, a, b) => a + b.toUpperCase()).replace(/^Mc([a-z])/, (m, c) => 'Mc' + c.toUpperCase())
}
