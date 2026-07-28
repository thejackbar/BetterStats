// ─────────────────────────────────────────────────────────────────────────────
// BLANK CANVAS — freeform, WYSIWYG post builder
//
// A 1080×1080 canvas the user fills themselves: text, images, decorative
// elements (lines / dividers / boxes / circles / triangles) and a movable club
// badge. Blocks can be selected (single or multi with shift), dragged, resized,
// aligned and re-ordered. The same component renders three ways from
// AdminSocialPost: an interactive desktop preview, and static mobile/export
// copies. Coordinates live in 1080-space; the interactive layer divides pointer
// deltas by the preview `scale` so dragging tracks the cursor 1:1.
// ─────────────────────────────────────────────────────────────────────────────
import { useRef } from 'react'
import { BrandLockup, GrainSVG } from './cricket-templates'

// Colour tokens resolve against the live palette so a palette switch re-tints
// any block left on a token; a raw hex (custom colour) passes straight through.
export function resolveBlankColor(c, palette = {}) {
  switch (c) {
    case 'ink': return palette.ink || '#ffffff'
    case 'accent': return palette.accent || '#ffc233'
    case 'primary': return palette.primary || '#101113'
    case 'secondary': return palette.secondary || '#1d1f23'
    case 'white': return '#ffffff'
    case 'black': return '#0a0a0a'
    default: return c || palette.ink || '#ffffff'
  }
}

let _seq = 0
const nextId = () => `bi${Date.now().toString(36)}${(_seq++).toString(36)}`

export const BLANK_FONTS = [
  { key: 'anton', name: 'Anton', family: "'Anton', sans-serif" },
  { key: 'barlow', name: 'Barlow Condensed', family: "'Barlow Condensed', sans-serif" },
  { key: 'bebas', name: 'Bebas Neue', family: "'Bebas Neue', sans-serif" },
  { key: 'archivo', name: 'Archivo Black', family: "'Archivo Black', sans-serif" },
  { key: 'oswald', name: 'Oswald', family: "'Oswald', sans-serif" },
  { key: 'abril', name: 'Abril Fatface', family: "'Abril Fatface', serif" },
  { key: 'marker', name: 'Permanent Marker', family: "'Permanent Marker', cursive" },
  { key: 'caveat', name: 'Caveat', family: "'Caveat', cursive" },
  { key: 'inter', name: 'Inter (body)', family: "'Inter', sans-serif" },
  { key: 'mono', name: 'Mono', family: "'JetBrains Mono', monospace" },
]

// Decorative elements offered in the "+ Element" menu.
export const BLANK_ELEMENTS = [
  { shape: 'line', name: 'Line' },
  { shape: 'divider', name: 'Divider' },
  { shape: 'rect', name: 'Box' },
  { shape: 'ellipse', name: 'Circle' },
  { shape: 'triangle', name: 'Triangle' },
  { shape: 'star', name: 'Star' },
  { shape: 'arrow', name: 'Arrow' },
  { shape: 'chevron', name: 'Chevron' },
  { shape: 'diamond', name: 'Diamond' },
  { shape: 'hexagon', name: 'Hexagon' },
]

// Clip-path polygons for the fill-only decorative shapes (scale with w/h).
const CLIP_SHAPES = {
  star: 'polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%)',
  arrow: 'polygon(0% 30%, 60% 30%, 60% 10%, 100% 50%, 60% 90%, 60% 70%, 0% 70%)',
  chevron: 'polygon(0% 0%, 50% 0%, 100% 50%, 50% 100%, 0% 100%, 50% 50%)',
  diamond: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)',
  hexagon: 'polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)',
}

export function newBlankItem(type, opts = {}) {
  const id = nextId()
  if (type === 'text') {
    return {
      id, type: 'text', text: opts.text || 'YOUR TEXT HERE',
      x: 90, y: 440, w: 900,
      fontFamily: "'Anton', sans-serif", fontSize: 120, bold: true,
      color: 'ink', align: 'left', lineHeight: 0.92, letterSpacing: 0,
      uppercase: true, bg: 'none', rotation: 0,
    }
  }
  if (type === 'image') {
    return { id, type: 'image', x: 340, y: 340, w: 400, h: 400, src: null, radius: 0, fit: 'contain', rotation: 0 }
  }
  if (type === 'brand') {
    return { id, type: 'brand', x: 60, y: 60, size: 160, layout: 'row', showName: true, align: 'left', color: 'ink' }
  }
  if (type === 'element') {
    const shape = opts.shape || 'line'
    if (shape === 'line') return { id, type: 'element', shape, x: 120, y: 220, w: 840, h: 6, thickness: 6, color: 'accent', opacity: 1, rotation: 0 }
    if (shape === 'divider') return { id, type: 'element', shape, x: 90, y: 540, w: 900, h: 4, thickness: 4, color: 'ink', opacity: 0.5, rotation: 0 }
    if (shape === 'rect') return { id, type: 'element', shape, x: 380, y: 400, w: 320, h: 200, color: 'accent', fill: true, radius: 0, thickness: 6, opacity: 1, rotation: 0 }
    if (shape === 'ellipse') return { id, type: 'element', shape, x: 420, y: 380, w: 240, h: 240, color: 'accent', fill: true, thickness: 6, opacity: 1, rotation: 0 }
    // Fill-only clip-path shapes (triangle + star/arrow/chevron/diamond/hexagon)
    return { id, type: 'element', shape, x: 420, y: 380, w: 260, h: 230, color: 'accent', opacity: 1, rotation: 0 }
  }
  return null
}

// Bounding box (1080-space) — used for group selection outline and alignment.
// Text height is an estimate (real height depends on wrapping); good enough for
// drawing the group box and aligning left/centre/right.
export function itemBBox(it) {
  if (!it) return { x: 0, y: 0, w: 0, h: 0 }
  if (it.type === 'text') {
    const lines = Math.max(1, Math.ceil((String(it.text || '').length * it.fontSize * 0.52) / Math.max(it.w, 1)))
    return { x: it.x, y: it.y, w: it.w, h: Math.round(it.fontSize * (it.lineHeight || 1) * lines) }
  }
  if (it.type === 'brand') return { x: it.x, y: it.y, w: it.showName ? it.size * 3 : it.size, h: it.size }
  return { x: it.x, y: it.y, w: it.w || 100, h: it.h || 100 }
}

export function groupBBox(list) {
  const items = (list || []).filter(Boolean)
  if (!items.length) return null
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const it of items) {
    const b = itemBBox(it)
    minX = Math.min(minX, b.x); minY = Math.min(minY, b.y)
    maxX = Math.max(maxX, b.x + b.w); maxY = Math.max(maxY, b.y + b.h)
  }
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY }
}

// ── Starter layouts (the "start from a template" gallery) ────────────────────
const starterBrand = (over = {}) => ({ ...newBlankItem('brand'), ...over })
const starterText = (text, over = {}) => ({ ...newBlankItem('text'), text, ...over })
const starterEl = (shape, over = {}) => ({ ...newBlankItem('element', { shape }), ...over })

export const BLANK_STARTERS = [
  { key: 'blank', name: 'Empty', build: () => [starterBrand({ x: 60, y: 56, size: 150 })] },
  {
    key: 'players', name: 'Players wanted', build: () => [
      starterBrand({ x: 60, y: 56, size: 184 }),
      starterText('PLAYERS WANTED', { x: 70, y: 470, w: 940, fontSize: 150, color: 'ink' }),
      starterText('Join the club this season — all grades, all ages welcome.', { x: 72, y: 720, w: 780, fontSize: 40, bold: false, fontFamily: "'Inter', sans-serif", uppercase: false, color: 'ink', lineHeight: 1.2 }),
    ],
  },
  {
    key: 'announcement', name: 'Announcement', build: () => [
      starterBrand({ x: 700, y: 56, size: 150, layout: 'stack', align: 'right' }),
      starterText('APPOINTMENT', { x: 70, y: 70, w: 360, fontSize: 34, color: 'accent', bg: 'none' }),
      starterEl('line', { x: 70, y: 470, w: 260, h: 10, thickness: 10, color: 'accent' }),
      starterText('PLAYER NAME', { x: 70, y: 520, w: 940, fontSize: 130, color: 'ink' }),
      starterText('NAMED FOR THE 2026-27 SEASON', { x: 72, y: 860, w: 820, fontSize: 40, color: 'accent' }),
    ],
  },
  {
    key: 'quote', name: 'Big quote', build: () => [
      starterBrand({ x: 60, y: 56, size: 150 }),
      starterText('“', { x: 60, y: 300, w: 300, fontSize: 340, color: 'accent', lineHeight: 0.7 }),
      starterText('Add your quote here — a message from the club.', { x: 90, y: 470, w: 900, fontSize: 90, color: 'ink', uppercase: false, lineHeight: 1.05 }),
      starterText('— Name, Role', { x: 92, y: 880, w: 700, fontSize: 44, bold: false, fontFamily: "'Inter', sans-serif", uppercase: false, color: 'accent' }),
    ],
  },
  {
    key: 'fixture', name: 'This week', build: () => [
      starterBrand({ x: 60, y: 56, size: 150 }),
      starterText('THIS WEEK', { x: 70, y: 300, w: 940, fontSize: 120, color: 'accent' }),
      starterText('1ST XI v OPPONENT', { x: 70, y: 470, w: 940, fontSize: 96, color: 'ink' }),
      starterEl('divider', { x: 70, y: 640, w: 940, h: 4, thickness: 4, color: 'ink', opacity: 0.4 }),
      starterText('SAT · 1:00 PM · HOME GROUND', { x: 72, y: 700, w: 900, fontSize: 46, color: 'ink' }),
    ],
  },
]

export function starterItems(key) {
  const s = BLANK_STARTERS.find((x) => x.key === key)
  return s ? s.build() : []
}

export function defaultBlankItems() {
  return starterItems('players')
}

// ── Rendering ────────────────────────────────────────────────────────────────
function TextBlock({ item, palette }) {
  return (
    <div style={{
      width: item.w,
      fontFamily: item.fontFamily, fontSize: item.fontSize,
      fontWeight: item.bold ? 800 : 400,
      color: resolveBlankColor(item.color, palette),
      textAlign: item.align, lineHeight: item.lineHeight ?? 1,
      letterSpacing: item.letterSpacing || 0,
      textTransform: item.uppercase ? 'uppercase' : 'none',
      whiteSpace: 'pre-wrap', wordBreak: 'break-word',
      background: item.bg && item.bg !== 'none' ? resolveBlankColor(item.bg, palette) : 'transparent',
      padding: item.bg && item.bg !== 'none' ? '0.15em 0.4em' : 0,
      boxDecorationBreak: 'clone',
    }}>{item.text || ' '}</div>
  )
}

function ImageBlock({ item, palette }) {
  if (item.src) {
    return <img src={item.src} alt="" draggable={false} style={{ width: item.w, height: item.h, objectFit: item.fit || 'contain', borderRadius: item.radius || 0, display: 'block', pointerEvents: 'none' }} />
  }
  return (
    <div style={{
      width: item.w, height: item.h, borderRadius: item.radius || 0,
      border: `3px dashed ${resolveBlankColor('ink', palette)}55`,
      display: 'grid', placeItems: 'center',
      fontFamily: "'JetBrains Mono', monospace", fontSize: 22, letterSpacing: 2,
      color: `${resolveBlankColor('ink', palette)}99`, textAlign: 'center', padding: 16,
    }}>ADD IMAGE</div>
  )
}

function ElementBlock({ item, palette }) {
  const color = resolveBlankColor(item.color, palette)
  const op = item.opacity ?? 1
  if (item.shape === 'line' || item.shape === 'divider') {
    return <div style={{ width: item.w, height: Math.max(1, item.thickness || 4), background: color, opacity: op }} />
  }
  if (item.shape === 'ellipse') {
    return <div style={{ width: item.w, height: item.h, borderRadius: '50%', background: item.fill !== false ? color : 'transparent', border: item.fill === false ? `${item.thickness || 4}px solid ${color}` : 'none', opacity: op }} />
  }
  if (item.shape === 'triangle') {
    return <div style={{ width: item.w, height: item.h, background: color, opacity: op, clipPath: 'polygon(50% 0, 100% 100%, 0 100%)' }} />
  }
  if (CLIP_SHAPES[item.shape]) {
    return <div style={{ width: item.w, height: item.h, background: color, opacity: op, clipPath: CLIP_SHAPES[item.shape] }} />
  }
  return <div style={{ width: item.w, height: item.h, borderRadius: item.radius || 0, background: item.fill !== false ? color : 'transparent', border: item.fill === false ? `${item.thickness || 4}px solid ${color}` : 'none', opacity: op }} />
}

function renderContent(item, palette, team) {
  if (item.type === 'text') return <TextBlock item={item} palette={palette} />
  if (item.type === 'image') return <ImageBlock item={item} palette={palette} />
  if (item.type === 'element') return <ElementBlock item={item} palette={palette} />
  return <BrandLockup team={team} palette={palette} size={item.size} layout={item.layout} align={item.align} showName={item.showName} nameColor={resolveBlankColor(item.color, palette)} />
}

function BlankBlock({ item, palette, team, interactive, selected, single, outline, handle, accent, onPointerDown, onResize }) {
  const rot = item.rotation ? `rotate(${item.rotation}deg)` : undefined
  return (
    <div
      onPointerDown={interactive ? (e) => onPointerDown(e, item.id) : undefined}
      draggable={false}
      onDragStart={interactive ? (e) => e.preventDefault() : undefined}
      style={{
        position: 'absolute', left: item.x, top: item.y,
        cursor: interactive ? 'move' : 'default',
        outline: interactive && selected ? `${outline}px solid ${accent}` : 'none',
        outlineOffset: outline * 2, transform: rot, transformOrigin: 'center center',
        touchAction: 'none', userSelect: 'none', WebkitUserSelect: 'none',
      }}>
      {renderContent(item, palette, team)}
      {interactive && single && (
        <div onPointerDown={(e) => onResize(e, item)} title="Drag to resize"
          style={{ position: 'absolute', right: -handle / 2, bottom: -handle / 2, width: handle, height: handle, borderRadius: 3, background: accent, border: `${outline}px solid #000`, cursor: 'nwse-resize' }} />
      )}
    </div>
  )
}

export function BlankCanvas({
  items = [], palette = {}, team = {},
  interactive = false, scale = 1, selectedIds = [],
  onSelect, onDeselect, onPatchMany, onCommit,
  transparent = false, width = 1080, height = 1080, style = {},
}) {
  const rootRef = useRef(null)
  const selSet = new Set(selectedIds)
  const s = scale || 1
  const accent = resolveBlankColor('accent', palette)

  const beginMove = (e, id) => {
    if (!interactive) return
    e.stopPropagation()
    const additive = e.shiftKey || e.ctrlKey || e.metaKey
    let active
    if (additive) active = selSet.has(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id]
    else active = selSet.has(id) ? selectedIds : [id]
    onSelect && onSelect(id, additive)
    if (!active.length) return
    const starts = {}
    active.forEach((aid) => { const it = items.find((x) => x.id === aid); if (it) starts[aid] = { x: it.x, y: it.y } })
    const sx = e.clientX, sy = e.clientY
    const move = (ev) => {
      const dx = (ev.clientX - sx) / s, dy = (ev.clientY - sy) / s
      const patch = {}
      Object.entries(starts).forEach(([aid, st]) => { patch[aid] = { x: Math.round(st.x + dx), y: Math.round(st.y + dy) } })
      onPatchMany(patch)
    }
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); onCommit && onCommit() }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const beginResizeSingle = (e, item) => {
    e.stopPropagation(); e.preventDefault()
    const sx = e.clientX, sy = e.clientY
    const w0 = item.w, h0 = item.h, sz0 = item.size, fs0 = item.fontSize
    const move = (ev) => {
      const dx = (ev.clientX - sx) / s, dy = (ev.clientY - sy) / s
      if (item.type === 'text') onPatchMany({ [item.id]: { w: Math.max(40, Math.round(w0 + dx)) } })
      else if (item.type === 'image') { const nw = Math.max(30, Math.round(w0 + dx)); const r = h0 && w0 ? h0 / w0 : 1; onPatchMany({ [item.id]: { w: nw, h: Math.max(30, Math.round(nw * r)) } }) }
      else if (item.type === 'element') onPatchMany({ [item.id]: { w: Math.max(4, Math.round(w0 + dx)), h: Math.max(2, Math.round((h0 || 0) + dy)) } })
      else if (item.type === 'brand') onPatchMany({ [item.id]: { size: Math.max(40, Math.round(sz0 + dx)) } })
    }
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); onCommit && onCommit() }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const beginResizeGroup = (e, bb) => {
    e.stopPropagation(); e.preventDefault()
    const starts = {}
    selectedIds.forEach((id) => { const it = items.find((x) => x.id === id); if (it) starts[id] = { ...it } })
    const sx = e.clientX, w0 = Math.max(bb.w, 1)
    const move = (ev) => {
      const dx = (ev.clientX - sx) / s
      let f = (w0 + dx) / w0; f = Math.max(0.2, Math.min(4, f))
      const patch = {}
      Object.entries(starts).forEach(([id, it]) => {
        const p = { x: Math.round(bb.x + (it.x - bb.x) * f), y: Math.round(bb.y + (it.y - bb.y) * f) }
        if (it.type === 'text') { p.fontSize = Math.max(8, Math.round(it.fontSize * f)); p.w = Math.max(40, Math.round(it.w * f)) }
        else if (it.type === 'image') { p.w = Math.max(30, Math.round(it.w * f)); p.h = Math.max(30, Math.round(it.h * f)) }
        else if (it.type === 'element') { p.w = Math.max(4, Math.round(it.w * f)); p.h = Math.max(2, Math.round((it.h || 0) * f)); if (it.thickness) p.thickness = Math.max(1, Math.round(it.thickness * f)) }
        else if (it.type === 'brand') p.size = Math.max(40, Math.round(it.size * f))
        patch[id] = p
      })
      onPatchMany(patch)
    }
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); onCommit && onCommit() }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const handle = Math.max(10, Math.round(18 / s))
  const outline = Math.max(1, Math.round(2 / s))
  const multi = selectedIds.length > 1
  const gbb = multi ? groupBBox(selectedIds.map((id) => items.find((x) => x.id === id))) : null

  return (
    <div
      ref={rootRef}
      onPointerDown={interactive ? (e) => { if (e.target === rootRef.current) onDeselect && onDeselect() } : undefined}
      style={{
        width, height, position: 'relative', overflow: 'hidden',
        background: transparent ? 'transparent' : (palette.primary || '#101113'),
        color: palette.ink || '#fff', fontFamily: "'Inter', sans-serif",
        ...style,
      }}>
      {!transparent && <GrainSVG opacity={0.14} id="blankcanvas" />}
      {items.map((it) => (
        <BlankBlock
          key={it.id} item={it} palette={palette} team={team} interactive={interactive}
          selected={selSet.has(it.id)} single={selectedIds.length === 1 && selSet.has(it.id)}
          outline={outline} handle={handle} accent={accent}
          onPointerDown={beginMove} onResize={beginResizeSingle}
        />
      ))}
      {interactive && multi && gbb && (
        <div style={{ position: 'absolute', left: gbb.x, top: gbb.y, width: gbb.w, height: gbb.h, outline: `${outline}px dashed ${accent}`, pointerEvents: 'none' }}>
          <div onPointerDown={(e) => beginResizeGroup(e, gbb)} title="Drag to resize group"
            style={{ position: 'absolute', right: -handle / 2, bottom: -handle / 2, width: handle, height: handle, background: accent, border: `${outline}px solid #000`, cursor: 'nwse-resize', pointerEvents: 'auto' }} />
        </div>
      )}
    </div>
  )
}
