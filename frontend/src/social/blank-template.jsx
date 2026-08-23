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
import { BrandLockup, GrainSVG, CreditMark } from './cricket-templates'

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

// Data blocks pull live club info (fixtures, results, record, a scorecard, a
// player's career stats) into the canvas. They render from the `data` bundle
// AdminSocialPost passes down, so a saved template stores only the config and
// always shows current numbers.
// `group` splits the Club-data panel into "from a player profile" vs "from the
// club". The three player kinds all read the same `playerId`, so one picker
// drives photo + name + numbers.
export const BLANK_DATA = [
  { kind: 'playerphoto', name: 'Player photo', group: 'player' },
  { kind: 'playername', name: 'Player name', group: 'player' },
  { kind: 'player', name: 'Player stats', group: 'player' },
  { kind: 'fixtures', name: 'Fixtures', group: 'club' },
  { kind: 'results', name: 'Results', group: 'club' },
  { kind: 'record', name: 'W-L-D record', group: 'club' },
  { kind: 'scorecard', name: 'Scorecard', group: 'club' },
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
      x: opts.x ?? 90, y: opts.y ?? 440, w: opts.w ?? 900,
      fontFamily: opts.fontFamily || "'Anton', sans-serif",
      fontSize: opts.fontSize ?? 120,
      bold: opts.bold ?? true,
      color: opts.color || 'ink', align: opts.align || 'left',
      lineHeight: opts.lineHeight ?? 0.92, letterSpacing: opts.letterSpacing ?? 0,
      uppercase: opts.uppercase ?? true, bg: 'none', rotation: 0,
    }
  }
  if (type === 'image') {
    return {
      id, type: 'image', x: opts.x ?? 340, y: opts.y ?? 340, w: opts.w ?? 400, h: opts.h ?? 400,
      src: opts.src ?? null, srcName: opts.srcName, radius: 0, fit: opts.fit || 'contain', rotation: 0,
    }
  }
  if (type === 'brand') {
    return { id, type: 'brand', x: 60, y: 60, size: 160, layout: 'row', showName: true, showLogo: true, align: 'left', color: 'ink' }
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
  if (type === 'data') {
    const kind = opts.kind || 'fixtures'
    const base = { id, type: 'data', kind, x: 70, y: 300, w: 940, color: 'ink', accent: 'accent', count: 5, rotation: 0 }
    if (kind === 'record') return { ...base, w: 900, h: 240 }
    if (kind === 'player') return { ...base, w: 900, h: 380, playerId: opts.playerId || null }
    if (kind === 'playerphoto') return { ...base, x: 540, y: 300, w: 460, h: 620, playerId: opts.playerId || null, fit: 'cover' }
    if (kind === 'playername') return { ...base, x: 70, y: 560, w: 900, h: 260, playerId: opts.playerId || null, showRole: true }
    if (kind === 'scorecard') return { ...base, w: 940, h: 520 }
    return { ...base, h: 70 + 5 * 70 } // fixtures / results
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

// Human label for a block — shared by the Layers panel, the inspector title and
// the Content panel. Images prefer their stored asset name.
export function itemLabel(it) {
  if (!it) return ''
  if (it.type === 'text') return `“${(it.text || '').slice(0, 16) || 'Text'}${(it.text || '').length > 16 ? '…' : ''}”`
  if (it.type === 'image') return it.srcName || (it.src ? 'Image' : 'Image (empty)')
  if (it.type === 'brand') return 'Club badge'
  if (it.type === 'element') return { line: 'Line', divider: 'Divider', rect: 'Box', ellipse: 'Circle', triangle: 'Triangle', star: 'Star', arrow: 'Arrow', chevron: 'Chevron', diamond: 'Diamond', hexagon: 'Hexagon' }[it.shape] || 'Element'
  if (it.type === 'data') return {
    fixtures: 'Fixtures', results: 'Results', record: 'Record', scorecard: 'Scorecard',
    player: 'Player stats', playerphoto: 'Player photo', playername: 'Player name',
  }[it.kind] || 'Data'
  return it.type
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
      starterText('Join the club this season: all grades, all ages welcome.', { x: 72, y: 720, w: 780, fontSize: 40, bold: false, fontFamily: "'Inter', sans-serif", uppercase: false, color: 'ink', lineHeight: 1.2 }),
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
      starterText('Add your quote here: a message from the club.', { x: 90, y: 470, w: 900, fontSize: 90, color: 'ink', uppercase: false, lineHeight: 1.05 }),
      starterText('. Name, Role', { x: 92, y: 880, w: 700, fontSize: 44, bold: false, fontFamily: "'Inter', sans-serif", uppercase: false, color: 'accent' }),
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

// ── Data blocks (live club info) ─────────────────────────────────────────────
const DISPLAY_FONT = "var(--social-display-font, 'Anton', sans-serif)"
const MONO_FONT = "'JetBrains Mono', monospace"

const BASE_URL = import.meta.env.VITE_API_URL || '/api'
// Same headshot URL the lineup templates use (playerToTemplatePlayer builds
// `headshot` from it) — no new server endpoint needed.
const headshotUrl = (p) => (p?.photo_url ? `${BASE_URL}/images/players/${p.id}/photo` : null)

// "LAST, First" / "First Last" split, mirroring splitName in AdminSocialPost.
function splitPlayerName(name) {
  const n = String(name || '').trim()
  if (!n) return ['', '']
  if (n.includes(', ')) { const [l, f] = n.split(', '); return [f || '', l || ''] }
  const parts = n.split(/\s+/)
  return [parts.slice(0, -1).join(' '), parts.slice(-1)[0] || '']
}

function DataBlock({ item, palette, data = {} }) {
  const ink = resolveBlankColor(item.color, palette)
  const accent = resolveBlankColor(item.accent || 'accent', palette)
  const rule = `${ink}22`
  const count = Math.max(1, Math.min(12, item.count || 5))
  const wrap = { width: item.w, fontFamily: DISPLAY_FONT, color: ink }
  const Head = ({ children }) => (
    <div style={{ fontFamily: DISPLAY_FONT, fontSize: 30, letterSpacing: 2, color: accent, marginBottom: 12 }}>{children}</div>
  )
  const empty = (label) => (
    <div style={wrap}><Head>{label}</Head><div style={{ fontFamily: MONO_FONT, fontSize: 15, color: `${ink}99` }}>No {label.toLowerCase()} loaded yet. Add them on the {label} tab.</div></div>
  )

  if (item.kind === 'fixtures') {
    const rows = (data.fixtures || []).slice(0, count)
    if (!rows.length) return empty('Fixtures')
    return (
      <div style={wrap}>
        <Head>THIS WEEK</Head>
        {rows.map((f, i) => (
          <div key={i} style={{ display: 'grid', gridTemplateColumns: '150px 1fr auto', alignItems: 'baseline', gap: 14, padding: '10px 0', borderTop: i ? `1px solid ${rule}` : 'none' }}>
            <span style={{ fontSize: 26, color: accent, letterSpacing: 1 }}>{f.grade}</span>
            <span style={{ fontSize: 30, letterSpacing: 0.5 }}>v {(f.opp || '').toUpperCase()} <span style={{ fontSize: 18, color: `${ink}aa` }}>({f.ha})</span></span>
            <span style={{ fontFamily: MONO_FONT, fontSize: 15, color: `${ink}bb` }}>{f.time}{f.venue ? ` · ${f.venue}` : ''}</span>
          </div>
        ))}
      </div>
    )
  }

  if (item.kind === 'results') {
    const rows = (data.results || []).slice(0, count)
    if (!rows.length) return empty('Results')
    return (
      <div style={wrap}>
        <Head>RESULTS</Head>
        {rows.map((r, i) => {
          const won = (r.outcome || '').toUpperCase() === 'W'
          return (
            <div key={i} style={{ display: 'grid', gridTemplateColumns: '150px 1fr auto 40px', alignItems: 'baseline', gap: 14, padding: '10px 0', borderTop: i ? `1px solid ${rule}` : 'none' }}>
              <span style={{ fontSize: 24, color: accent, letterSpacing: 1 }}>{r.grade}</span>
              <span style={{ fontSize: 28 }}>v {(r.opp || '').toUpperCase()}</span>
              <span style={{ fontFamily: MONO_FONT, fontSize: 16, color: `${ink}cc` }}>{r.us} / {r.them}</span>
              <span style={{ fontSize: 26, textAlign: 'right', color: won ? accent : `${ink}88` }}>{(r.outcome || '').toUpperCase()}</span>
            </div>
          )
        })}
      </div>
    )
  }

  if (item.kind === 'record') {
    const rec = data.record || { w: 0, l: 0, d: 0 }
    const Cell = ({ n, label }) => (
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 130, lineHeight: 0.9, color: ink }}>{n}</div>
        <div style={{ fontFamily: MONO_FONT, fontSize: 16, letterSpacing: 3, color: accent, marginTop: 6 }}>{label}</div>
      </div>
    )
    return (
      <div style={wrap}>
        <Head>{(data.team?.name || 'CLUB').toUpperCase()} · RECORD</Head>
        <div style={{ display: 'flex', gap: 60, alignItems: 'flex-end' }}>
          <Cell n={rec.w} label="WON" /><Cell n={rec.l} label="LOST" /><Cell n={rec.d} label="DRAWN" />
        </div>
      </div>
    )
  }

  if (item.kind === 'scorecard') {
    const sc = data.scorecard
    const m = sc?.meta || {}
    const side = (t, label) => {
      if (!t) return null
      const topBat = (t.batting || []).slice().sort((a, b) => (b.r || 0) - (a.r || 0))[0]
      const topBowl = (t.bowling || []).slice().sort((a, b) => (b.w || 0) - (a.w || 0))[0]
      return (
        <div style={{ padding: '14px 0', borderTop: `1px solid ${rule}` }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
            <span style={{ fontSize: 34, letterSpacing: 0.5 }}>{(t.name || label).toUpperCase()}</span>
            <span style={{ fontSize: 46, color: accent }}>{t.total}{t.wickets < 10 ? `/${t.wickets}` : ''}<span style={{ fontSize: 20, color: `${ink}aa` }}> ({t.overs})</span></span>
          </div>
          <div style={{ fontFamily: MONO_FONT, fontSize: 15, color: `${ink}bb`, marginTop: 6 }}>
            {topBat ? `Top bat ${topBat.last} ${topBat.r}${topBat.notOut ? '*' : ''} (${topBat.b})` : ''}
            {topBowl && topBowl.w ? `  ·  Top bowl ${topBowl.last} ${topBowl.w}/${topBowl.r}` : ''}
          </div>
        </div>
      )
    }
    return (
      <div style={wrap}>
        <Head>{(m.result || 'SCORECARD').toUpperCase()}</Head>
        {side(sc?.home, 'HOME')}
        {side(sc?.away, 'AWAY')}
      </div>
    )
  }

  if (item.kind === 'playerphoto') {
    const player = (data.players || []).find((p) => p.id === item.playerId)
    const src = headshotUrl(player)
    if (src) {
      return <img src={src} alt="" draggable={false} style={{ width: item.w, height: item.h, objectFit: item.fit || 'cover', display: 'block', pointerEvents: 'none' }} />
    }
    return (
      <div style={{
        width: item.w, height: item.h, border: `3px dashed ${ink}55`,
        display: 'grid', placeItems: 'center', textAlign: 'center', padding: 16,
        fontFamily: MONO_FONT, fontSize: 20, letterSpacing: 2, color: `${ink}99`,
      }}>
        {player ? `NO PHOTO ON ${(player.display_name || player.name || '').toUpperCase()}'S PROFILE` : 'SELECT A PLAYER'}
      </div>
    )
  }

  if (item.kind === 'playername') {
    const player = (data.players || []).find((p) => p.id === item.playerId)
    const name = player ? (player.display_name || player.name || '') : ''
    const [first, last] = splitPlayerName(name)
    const role = player?.roles?.[0] || player?.role || player?.player_role || ''
    return (
      <div style={{ width: item.w, fontFamily: DISPLAY_FONT, color: ink }}>
        {first && <div style={{ fontSize: 52, lineHeight: 1, color: accent, letterSpacing: 1 }}>{first.toUpperCase()}</div>}
        <div style={{ fontSize: 148, lineHeight: 0.92 }}>{(last || 'PLAYER').toUpperCase()}</div>
        {item.showRole && role && (
          <div style={{ fontFamily: MONO_FONT, fontSize: 26, letterSpacing: 3, color: `${ink}aa`, marginTop: 10 }}>{String(role).toUpperCase()}</div>
        )}
      </div>
    )
  }

  if (item.kind === 'player') {
    const stats = item.playerId ? (data.playerStats || {})[item.playerId] : null
    const bat = stats?.career_batting || {}
    const bowl = stats?.career_bowling || {}
    const name = stats?.player?.display_name || stats?.player?.name || item.playerName || 'Select a player'
    const parts = String(name).trim().split(' ')
    const last = parts.length > 1 ? parts.slice(1).join(' ') : name
    const first = parts.length > 1 ? parts[0] : ''
    const tiles = [
      { label: 'MATCHES', value: bat.games ?? bowl.games ?? '—' },
      { label: 'RUNS', value: bat.total_runs ?? '—' },
      { label: 'BAT AVG', value: bat.average ?? '—' },
      { label: 'HS', value: bat.high_score ?? '—' },
      { label: 'WICKETS', value: bowl.total_wickets ?? '—' },
      { label: 'BOWL AVG', value: bowl.average ?? '—' },
    ]
    return (
      <div style={wrap}>
        {first && <div style={{ fontSize: 34, color: `${ink}cc` }}>{first.toUpperCase()}</div>}
        <div style={{ fontSize: 76, lineHeight: 0.95, color: ink }}>{String(last).toUpperCase()}</div>
        {!stats && item.playerId && <div style={{ fontFamily: MONO_FONT, fontSize: 14, color: `${ink}99`, marginTop: 8 }}>Loading stats…</div>}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginTop: 20 }}>
          {tiles.map((t, i) => (
            <div key={i} style={{ padding: '12px 16px', border: `1.5px solid ${accent}`, background: `${ink}0c` }}>
              <div style={{ fontFamily: MONO_FONT, fontSize: 12, letterSpacing: 2, color: `${ink}aa` }}>{t.label}</div>
              <div style={{ fontSize: 50, lineHeight: 0.95, marginTop: 4, color: ink }}>{t.value}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }
  return null
}

function renderContent(item, palette, team, data) {
  if (item.type === 'text') return <TextBlock item={item} palette={palette} />
  if (item.type === 'image') return <ImageBlock item={item} palette={palette} />
  if (item.type === 'element') return <ElementBlock item={item} palette={palette} />
  if (item.type === 'data') return <DataBlock item={item} palette={palette} data={data} />
  return <BrandLockup team={team} palette={palette} size={item.size} layout={item.layout} align={item.align} showName={item.showName} showLogo={item.showLogo !== false} nameColor={resolveBlankColor(item.color, palette)} />
}

// Canva-style selection box: 8 resize handles (corners scale, edges stretch),
// a rotation handle below and a floating toolbar (duplicate / delete) above.
const RESIZE_HANDLES = [
  { k: 'nw', x: 0, y: 0, cur: 'nwse-resize' },
  { k: 'n', x: 0.5, y: 0, cur: 'ns-resize' },
  { k: 'ne', x: 1, y: 0, cur: 'nesw-resize' },
  { k: 'e', x: 1, y: 0.5, cur: 'ew-resize' },
  { k: 'se', x: 1, y: 1, cur: 'nwse-resize' },
  { k: 's', x: 0.5, y: 1, cur: 'ns-resize' },
  { k: 'sw', x: 0, y: 1, cur: 'nesw-resize' },
  { k: 'w', x: 0, y: 0.5, cur: 'ew-resize' },
]

function BlankBlock({ item, palette, team, data, interactive, selected, single, outline, handle, accent, onPointerDown, onResize, onRotate, onDuplicate, onRemove }) {
  const rot = item.rotation ? `rotate(${item.rotation}deg)` : undefined
  const H = handle
  const gap = H * 1.6
  // Near the top of the canvas there's no room above for the toolbar, so drop it
  // below the block and move the rotation handle up.
  const toolBelow = item.y < H * 4.5
  const toolBtn = { width: H * 1.5, height: H * 1.5, display: 'grid', placeItems: 'center', background: 'transparent', border: 'none', cursor: 'pointer', color: '#fff', padding: 0 }
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
      {renderContent(item, palette, team, data)}
      {interactive && single && (
        <>
          {/* Quick toolbar */}
          <div onPointerDown={(e) => e.stopPropagation()}
            style={{ position: 'absolute', left: '50%', top: toolBelow ? '100%' : 0, transform: toolBelow ? `translate(-50%, ${gap}px)` : `translate(-50%, calc(-100% - ${gap}px))`, display: 'flex', gap: H * 0.2, padding: `${H * 0.25}px ${H * 0.4}px`, borderRadius: H, background: 'rgba(16,20,29,.96)', border: `${outline}px solid ${accent}`, boxShadow: '0 4px 14px rgba(0,0,0,.5)', pointerEvents: 'auto' }}>
            <button title="Duplicate" style={toolBtn} onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); onDuplicate && onDuplicate(item.id) }}>
              <svg width={H} height={H} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="11" height="11" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></svg>
            </button>
            <button title="Delete" style={toolBtn} onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); onRemove && onRemove(item.id) }}>
              <svg width={H} height={H} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m2 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /></svg>
            </button>
          </div>

          {/* Resize handles */}
          {RESIZE_HANDLES.map((h) => {
            const corner = h.k.length === 2
            const w = corner ? H : (h.k === 'n' || h.k === 's' ? H * 1.9 : H * 0.7)
            const ht = corner ? H : (h.k === 'e' || h.k === 'w' ? H * 1.9 : H * 0.7)
            return (
              <div key={h.k} onPointerDown={(e) => onResize(e, item, h.k)} title="Drag to resize"
                style={{ position: 'absolute', left: `${h.x * 100}%`, top: `${h.y * 100}%`, width: w, height: ht, transform: 'translate(-50%, -50%)', background: '#fff', border: `${outline}px solid ${accent}`, borderRadius: corner ? Math.round(H * 0.2) : H, cursor: h.cur, pointerEvents: 'auto' }} />
            )
          })}

          {/* Rotation handle (opposite the toolbar) */}
          <div onPointerDown={(e) => onRotate(e, item)} title="Drag to rotate"
            style={{ position: 'absolute', left: '50%', top: toolBelow ? 0 : '100%', transform: toolBelow ? `translate(-50%, calc(-100% - ${gap}px))` : `translate(-50%, ${gap}px)`, width: H * 1.1, height: H * 1.1, borderRadius: '50%', background: '#fff', border: `${outline}px solid ${accent}`, cursor: 'grab', pointerEvents: 'auto', display: 'grid', placeItems: 'center' }}>
            <svg width={H * 0.7} height={H * 0.7} viewBox="0 0 24 24" fill="none" stroke={accent} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7" /><path d="M21 3v5h-5" /></svg>
          </div>
        </>
      )}
    </div>
  )
}

export function BlankCanvas({
  items = [], palette = {}, team = {}, data = {},
  interactive = false, scale = 1, selectedIds = [],
  onSelect, onDeselect, onPatchMany, onCommit, onGestureStart, onDuplicate, onRemove,
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
    let started = false
    const move = (ev) => {
      if (!started) { started = true; onGestureStart && onGestureStart() }
      const dx = (ev.clientX - sx) / s, dy = (ev.clientY - sy) / s
      const patch = {}
      Object.entries(starts).forEach(([aid, st]) => { patch[aid] = { x: Math.round(st.x + dx), y: Math.round(st.y + dy) } })
      onPatchMany(patch)
    }
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); onCommit && onCommit() }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  // Corner handles scale the whole block proportionally (a "pure" resize — an
  // image keeps its aspect, so it grows/shrinks rather than cropping); edge
  // handles stretch a single axis (for images that's a crop/stretch).
  const beginResize = (e, item, hnd) => {
    e.stopPropagation(); e.preventDefault()
    const sx = e.clientX, sy = e.clientY
    const bb = itemBBox(item)
    const w0 = bb.w || 1, h0 = bb.h || 1
    const x0 = item.x, y0 = item.y, fs0 = item.fontSize || 0, sz0 = item.size || 0, th0 = item.thickness || 0, iw0 = item.w || 0, ih0 = item.h || 0
    const right = hnd.includes('e'), left = hnd.includes('w'), bottom = hnd.includes('s'), top = hnd.includes('n')
    const corner = (left || right) && (top || bottom)
    let started = false
    const move = (ev) => {
      if (!started) { started = true; onGestureStart && onGestureStart() }
      const dx = (ev.clientX - sx) / s, dy = (ev.clientY - sy) / s
      let dW = right ? dx : left ? -dx : 0
      let dH = bottom ? dy : top ? -dy : 0
      let f = 1
      if (corner) {
        f = Math.max(0.1, Math.min(8, 1 + (dW / w0 + dH / h0) / 2))
        dW = w0 * (f - 1); dH = h0 * (f - 1)
      }
      const dX = left ? -dW : 0
      const dY = top ? -dH : 0
      const p = {}
      if (item.type === 'text') {
        if (corner) { p.fontSize = Math.max(8, Math.round(fs0 * f)); p.w = Math.max(40, Math.round(iw0 * f)) }
        else if (left || right) p.w = Math.max(40, Math.round(iw0 + dW))
        else p.fontSize = Math.max(8, Math.round(fs0 * (1 + dH / h0)))
        if (dX) p.x = Math.round(x0 + dX)
      } else if (item.type === 'brand') {
        p.size = Math.max(40, Math.round(sz0 * (corner ? f : 1 + (dW || dH) / (w0 || h0))))
        if (dX) p.x = Math.round(x0 + dX)
        if (dY) p.y = Math.round(y0 + dY)
      } else { // image / element / data
        const minW = item.type === 'element' ? 4 : 30
        const minH = item.type === 'element' ? 2 : 30
        p.w = Math.max(minW, Math.round(iw0 + dW))
        if ('h' in item) p.h = Math.max(minH, Math.round(ih0 + dH))
        if (item.type === 'element' && corner && th0) p.thickness = Math.max(1, Math.round(th0 * f))
        if (dX) p.x = Math.round(x0 + dX)
        if (dY) p.y = Math.round(y0 + dY)
      }
      onPatchMany({ [item.id]: p })
    }
    const up = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', up); onCommit && onCommit() }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
  }

  const beginRotate = (e, item) => {
    e.stopPropagation(); e.preventDefault()
    const bb = itemBBox(item)
    const rect = rootRef.current?.getBoundingClientRect()
    const cx = (rect?.left || 0) + (bb.x + bb.w / 2) * s
    const cy = (rect?.top || 0) + (bb.y + bb.h / 2) * s
    const start = Math.atan2(e.clientY - cy, e.clientX - cx) * 180 / Math.PI
    const rot0 = item.rotation || 0
    let started = false
    const move = (ev) => {
      if (!started) { started = true; onGestureStart && onGestureStart() }
      const a = Math.atan2(ev.clientY - cy, ev.clientX - cx) * 180 / Math.PI
      let next = Math.round(rot0 + (a - start))
      if (ev.shiftKey) next = Math.round(next / 15) * 15
      onPatchMany({ [item.id]: { rotation: ((next % 360) + 360) % 360 } })
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
    let started = false
    const move = (ev) => {
      if (!started) { started = true; onGestureStart && onGestureStart() }
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
      {/* BetterCricket credit — only on the standalone Blank canvas, not the
          overlay layer (real templates carry their own footer mark). */}
      {!transparent && (
        <div style={{ position: 'absolute', right: 36, bottom: 30, pointerEvents: 'none', zIndex: 2 }}>
          <CreditMark ink={palette.ink || '#fff'} h={44} />
        </div>
      )}
      {items.map((it) => (
        <BlankBlock
          key={it.id} item={it} palette={palette} team={team} data={data} interactive={interactive}
          selected={selSet.has(it.id)} single={selectedIds.length === 1 && selSet.has(it.id)}
          outline={outline} handle={handle} accent={accent}
          onPointerDown={beginMove} onResize={beginResize} onRotate={beginRotate}
          onDuplicate={onDuplicate} onRemove={onRemove}
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
