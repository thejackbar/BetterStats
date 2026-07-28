// ─────────────────────────────────────────────────────────────────────────────
// BLANK CANVAS — freeform, WYSIWYG post builder
//
// A 1080×1080 canvas the user fills themselves: drag/resize text and image
// blocks anywhere, plus a movable club-branding lockup that's added by default
// (these posts double as club/recruitment ads, so the club mark is seeded in).
// The same component renders three ways from AdminSocialPost:
//   • desktop preview  → interactive (drag to move, corner handle to resize)
//   • mobile preview / hidden export → static (interactive = false)
// Coordinates are stored in 1080-space; the interactive layer divides pointer
// deltas by the preview `scale` so dragging lines up 1:1 with the cursor.
// ─────────────────────────────────────────────────────────────────────────────
import { useRef } from 'react'
import { BrandLockup, GrainSVG } from './cricket-templates'

// Colour tokens resolve against the live palette so a palette switch re-tints
// any block left on a token; a raw hex (custom colour) is passed straight
// through. Keep these keys in sync with the colour picker in AdminSocialPost.
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

export function newBlankItem(type) {
  const id = nextId()
  if (type === 'text') {
    return {
      id, type: 'text', text: 'YOUR TEXT HERE',
      x: 90, y: 440, w: 900,
      fontFamily: "'Anton', sans-serif", fontSize: 120, bold: true,
      color: 'ink', align: 'left', lineHeight: 0.92, letterSpacing: 0,
      uppercase: true, bg: 'none',
    }
  }
  if (type === 'image') {
    return { id, type: 'image', x: 340, y: 340, w: 400, h: 400, src: null, radius: 0, fit: 'contain' }
  }
  if (type === 'brand') {
    return { id, type: 'brand', x: 60, y: 60, size: 150, layout: 'row', showName: true, align: 'left', color: 'ink' }
  }
  return null
}

// The canvas a new "Blank" post opens with: club lockup top-left, one headline.
export function defaultBlankItems() {
  return [
    { ...newBlankItem('brand'), x: 60, y: 56, size: 160 },
    { ...newBlankItem('text'), text: 'PLAYERS WANTED', x: 70, y: 470, w: 940, fontSize: 150, color: 'ink' },
    { ...newBlankItem('text'), text: 'Join the club this season — all grades, all ages welcome.', x: 72, y: 720, w: 780, fontSize: 40, bold: false, fontFamily: "'Inter', sans-serif", uppercase: false, color: 'ink', lineHeight: 1.2 },
  ]
}

function TextBlock({ item, palette }) {
  return (
    <div style={{
      width: item.w,
      fontFamily: item.fontFamily,
      fontSize: item.fontSize,
      fontWeight: item.bold ? 800 : 400,
      color: resolveBlankColor(item.color, palette),
      textAlign: item.align,
      lineHeight: item.lineHeight ?? 1,
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
    return (
      <img src={item.src} alt=""
        style={{ width: item.w, height: item.h, objectFit: item.fit || 'contain', borderRadius: item.radius || 0, display: 'block' }} />
    )
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

function BlankBlock({ item, palette, team, interactive, scale, selected, onSelect, onChange, onCommit }) {
  const start = (e, mode) => {
    if (!interactive) return
    e.stopPropagation()
    e.preventDefault()
    onSelect && onSelect(item.id)
    const sx = e.clientX, sy = e.clientY
    const x0 = item.x, y0 = item.y, w0 = item.w, h0 = item.h, sz0 = item.size, fs0 = item.fontSize
    const s = scale || 1
    const move = (ev) => {
      const dx = (ev.clientX - sx) / s
      const dy = (ev.clientY - sy) / s
      if (mode === 'move') {
        onChange(item.id, { x: Math.round(x0 + dx), y: Math.round(y0 + dy) })
      } else if (mode === 'resize') {
        if (item.type === 'text') {
          onChange(item.id, { w: Math.max(60, Math.round(w0 + dx)) })
        } else if (item.type === 'image') {
          const nw = Math.max(40, Math.round(w0 + dx))
          const ratio = h0 && w0 ? h0 / w0 : 1
          onChange(item.id, { w: nw, h: Math.max(40, Math.round(nw * ratio)) })
        } else if (item.type === 'brand') {
          onChange(item.id, { size: Math.max(48, Math.round(sz0 + dx)) })
        }
      } else if (mode === 'font') {
        onChange(item.id, { fontSize: Math.max(12, Math.round(fs0 + dy)) })
      }
    }
    const up = () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
      onCommit && onCommit()
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const content = item.type === 'text'
    ? <TextBlock item={item} palette={palette} />
    : item.type === 'image'
      ? <ImageBlock item={item} palette={palette} />
      : <BrandLockup team={team} palette={palette} size={item.size} layout={item.layout} align={item.align} showName={item.showName} nameColor={resolveBlankColor(item.color, palette)} />

  const handle = Math.max(10, Math.round(16 / (scale || 1)))
  const outline = Math.max(1, Math.round(2 / (scale || 1)))

  return (
    <div
      onPointerDown={interactive ? (e) => start(e, 'move') : undefined}
      style={{
        position: 'absolute', left: item.x, top: item.y,
        cursor: interactive ? 'move' : 'default',
        outline: interactive && selected ? `${outline}px solid ${resolveBlankColor('accent', palette)}` : 'none',
        outlineOffset: outline * 2,
        touchAction: 'none',
      }}>
      {content}
      {interactive && selected && (
        <div
          onPointerDown={(e) => start(e, 'resize')}
          title="Drag to resize"
          style={{
            position: 'absolute', right: -handle / 2, bottom: -handle / 2,
            width: handle, height: handle, borderRadius: 3,
            background: resolveBlankColor('accent', palette),
            border: `${outline}px solid #000`,
            cursor: 'nwse-resize',
          }} />
      )}
    </div>
  )
}

export function BlankCanvas({
  items = [], palette = {}, team = {},
  interactive = false, scale = 1, selectedId = null,
  onSelect, onChange, onCommit,
}) {
  const rootRef = useRef(null)
  return (
    <div
      ref={rootRef}
      onPointerDown={interactive ? (e) => { if (e.target === rootRef.current) onSelect && onSelect(null) } : undefined}
      style={{
        width: 1080, height: 1080, position: 'relative', overflow: 'hidden',
        background: palette.primary || '#101113', color: palette.ink || '#fff',
        fontFamily: "'Inter', sans-serif",
      }}>
      <GrainSVG opacity={0.16} id="blankcanvas" />
      {items.map((it) => (
        <BlankBlock
          key={it.id} item={it} palette={palette} team={team}
          interactive={interactive} scale={scale} selected={selectedId === it.id}
          onSelect={onSelect} onChange={onChange} onCommit={onCommit}
        />
      ))}
    </div>
  )
}
