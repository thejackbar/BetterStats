// BetterCricket — Event LIST posters: a club's run of events on one post.
//
// Three directions for the same data, "What's on this term":
//   EL1 Agenda      a dated list, one row per event, with its icon or photo
//   EL2 Calendar    a month grid with the event days lit, and the list beneath
//   EL3 Icon Cards  a grid of cards, each led by its icon or photo
//
// Same contract as event-templates.jsx: full-bleed 1080 wide at square, portrait
// and story, colour from the active `palette`, a sponsor slot reserved and kept
// clear (SPONSOR_SLOTS, registered in sponsorSlots.js), and a `LayerRoot` root.
//
// DATA. The editor holds raw items and hands the template PREPARED ones (see
// `prepareEventList` in event-templates.jsx), so a layout never parses a date or
// looks an icon up:
//   list = { items: [{ id, day, mon, wd, iso, dateLabel, title, time, venue, price,
//                      visual: { kind: 'image' | 'icon', src } | null }],
//            year, month, monthLabel }       (month is 0-11, for the calendar)
//   event = { kicker, title, subtitle, sponsor }   (the poster's own heading)
import { AutoFitText, ClubLogo } from './cricket-templates'
import { PLATFORM_NAME } from '../lib/sport'
import { aspectOf, pick } from './postAspect'
import { LayerRoot } from './postLayers'

const MONO = "'JetBrains Mono', monospace"
const SPORT = "var(--social-display-font, 'Barlow Condensed', sans-serif)"

export const MAX_LIST_ITEMS = 8

const a = (hex, alpha) => {
  if (!hex || hex[0] !== '#' || hex.length < 7) return hex
  return hex + Math.round(Math.max(0, Math.min(1, alpha)) * 255).toString(16).padStart(2, '0')
}

const FRAME = (width = 1080, height = 1080) => ({
  width, height, position: 'relative', overflow: 'hidden',
  fontFamily: "'Inter', sans-serif", boxSizing: 'border-box',
})

// A strip along the foot for the sponsor grid, the same shape every event poster
// keeps. The layout reads this to leave the rectangle clear.
const slotList = (width, height) => {
  const A = aspectOf(width, height)
  const h = pick(A, { square: 100, portrait: 112, story: 128 })
  const bottom = pick(A, { square: 40, portrait: 44, story: 120 })
  return { x: 64, y: height - bottom - h, w: width - 128, h, pad: 8, gap: 24, panel: 'light' }
}

// Where the room for the body is: from the top margin to the sponsor strip.
const bodyBox = (width, height) => {
  const slot = slotList(width, height)
  return { top: 56, bottom: height - slot.y + 22, h: slot.y - 22 - 56 }
}

function Visual({ v, size, accent, radius = 12, ink = '#fff', fill }) {
  const box = { width: size, height: size, borderRadius: radius, flexShrink: 0, overflow: 'hidden', background: fill ?? a(accent, 0.16), display: 'flex', alignItems: 'center', justifyContent: 'center' }
  if (!v || !v.src) {
    return <div style={{ ...box, border: `1.5px dashed ${a(ink, 0.28)}` }} />
  }
  if (v.kind === 'image') {
    return <div style={box}><img src={v.src} alt="" crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} /></div>
  }
  return <div style={box}><img src={v.src} alt="" style={{ width: '78%', height: '78%', objectFit: 'contain', display: 'block' }} /></div>
}
Visual.displayName = 'EventListVisual'

const sub = (it) => [it.time, it.venue].filter(Boolean).join('  ·  ')

// The heading's real height, so the body is sized from it rather than from a guess
// (a guess is how a subtitle ended up under the month row). Logo row, kicker line,
// the title box, then room for a two-line subtitle when there is one.
const headingH = (A, titleMax, event = {}) =>
  56 + pick(A, { square: 14, portrait: 20, story: 26 }) + (event.kicker ? 28 : 0) + Math.round(titleMax * 0.98) + (event.subtitle ? 72 : 0)

function Heading({ team, event, P, ink, A, titleMax, kickerColor, fontFamily = SPORT, uppercase = true }) {
  return (
    <div style={{ flexShrink: 0, height: headingH(A, titleMax, event), overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: pick(A, { square: 14, portrait: 20, story: 26 }) }}>
        {team.logo ? <ClubLogo src={team.logo} size={56} /> : <ClubLogo monogram={team.monogram} color={P.accent} size={56} shape="shield" />}
        <div style={{ fontFamily: SPORT, fontSize: 26, fontWeight: 700, letterSpacing: 2.5, textTransform: 'uppercase', color: ink, lineHeight: 1, maxWidth: 640, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>{team.fullName || team.name}</div>
      </div>
      {event.kicker ? <div style={{ fontFamily: MONO, fontSize: 16, letterSpacing: 5, textTransform: 'uppercase', color: kickerColor || P.accent, marginBottom: 8 }}>{event.kicker}</div> : null}
      <div style={{ height: Math.round(titleMax * 0.98) }}>
        <AutoFitText text={uppercase ? (event.title || '').toUpperCase() : event.title} max={titleMax} min={44} lines={1} measureDeps={[event.title]}
          style={{ fontFamily, fontWeight: 800, lineHeight: 0.96, letterSpacing: uppercase ? 1 : -1, color: ink, textTransform: uppercase ? 'uppercase' : 'none' }} />
      </div>
      {event.subtitle ? <div style={{ fontSize: 24, color: a(ink, 0.7), marginTop: 8, lineHeight: 1.3, maxWidth: 820, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{event.subtitle}</div> : null}
    </div>
  )
}

function Empty({ ink }) {
  return (
    <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: MONO, fontSize: 20, letterSpacing: 3, textTransform: 'uppercase', color: a(ink, 0.45), textAlign: 'center', border: `2px dashed ${a(ink, 0.25)}`, borderRadius: 16 }}>
      Add your events
    </div>
  )
}

function Credit({ event, color }) {
  return (
    <div style={{ flexShrink: 0, fontFamily: MONO, fontSize: 12, letterSpacing: 2, textTransform: 'uppercase', color, marginTop: 10 }}>
      Made with {PLATFORM_NAME}{event.sponsor ? ` · ${event.sponsor}` : ''}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EL1 — AGENDA · a dated list, one row per event
// ─────────────────────────────────────────────────────────────────────────────
export function EVL_Agenda({ team, event = {}, list = {}, width = 1080, height = 1080, palette }) {
  const P = palette
  const A = aspectOf(width, height)
  const box = bodyBox(width, height)
  const items = (list.items || []).slice(0, MAX_LIST_ITEMS)
  const n = Math.max(items.length, 1)
  const titleMax = pick(A, { square: 96, portrait: 104, story: 112 })
  const head = headingH(A, titleMax, event)
  const gap = 10
  const rowsH = box.h - head - 24 - 30
  // A taller post gives its rows more height (and the type with it) instead of
  // leaving the foot of the post empty.
  const rowH = Math.max(52, Math.min(pick(A, { square: 128, portrait: 150, story: 172 }), Math.floor((rowsH - (n - 1) * gap) / n)))
  const day = Math.round(rowH * 0.5)
  const title = Math.max(20, Math.min(pick(A, { square: 40, portrait: 44, story: 48 }), Math.round(rowH * 0.33)))
  const small = Math.max(12, Math.min(pick(A, { square: 20, portrait: 21, story: 23 }), Math.round(rowH * 0.18)))
  const dateW = Math.min(Math.round(rowH * 1.05), 140)
  const visSize = Math.min(Math.round(rowH * 0.7), 104)
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: P.primary, color: '#fff' }}>
      <div style={{ position: 'absolute', left: -200, top: -200, width: 560, height: 560, borderRadius: '50%', background: `radial-gradient(circle, ${a(P.accent, 0.26)}, transparent 68%)`, pointerEvents: 'none' }} />
      <div data-layer="Event list" style={{ position: 'absolute', left: 64, right: 64, top: box.top, bottom: box.bottom, display: 'flex', flexDirection: 'column' }}>
        <Heading team={team} event={event} P={P} ink="#fff" A={A} titleMax={titleMax} />
        <div style={{ marginTop: 24, flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column', gap, justifyContent: A === 'square' ? 'flex-start' : 'center' }}>
          {items.length === 0 ? <Empty ink="#fff" /> : items.map((it) => (
            <div key={it.id} style={{ height: rowH, flexShrink: 0, display: 'flex', alignItems: 'center', gap: 20, padding: '0 20px 0 0', background: a(P.accent, 0.09), borderRadius: 12, overflow: 'hidden' }}>
              <div style={{ width: dateW, alignSelf: 'stretch', background: P.accent, color: P.primary, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                <div style={{ fontFamily: SPORT, fontWeight: 800, fontSize: day, lineHeight: 0.9 }}>{it.day || '·'}</div>
                <div style={{ fontFamily: MONO, fontWeight: 700, fontSize: small, letterSpacing: 2, marginTop: 2 }}>{[it.mon, it.wd].filter(Boolean).join(' ')}</div>
              </div>
              <Visual v={it.visual} size={visSize} accent={P.accent} radius={10} />
              <div style={{ flex: 1, minWidth: 0 }}>
                {/* Fitted, not clipped: a long name shrinks to the room beside the price. */}
                <div style={{ height: Math.round(title * 1.12) }}>
                  <AutoFitText text={(it.title || '').toUpperCase()} max={title} min={16} lines={1} measureDeps={[it.title, title]}
                    style={{ fontFamily: SPORT, fontWeight: 700, lineHeight: 1.05, letterSpacing: 0.5, textTransform: 'uppercase' }} />
                </div>
                {sub(it) ? <div style={{ fontFamily: MONO, fontSize: small, letterSpacing: 1.5, color: 'rgba(255,255,255,0.62)', marginTop: 4, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub(it)}</div> : null}
              </div>
              {it.price ? <div style={{ fontFamily: SPORT, fontWeight: 800, fontSize: Math.round(title * 0.9), color: P.accent, flexShrink: 0, letterSpacing: 0.5 }}>{it.price}</div> : null}
            </div>
          ))}
        </div>
        <Credit event={event} color="rgba(255,255,255,0.42)" />
      </div>
    </LayerRoot>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EL2 — CALENDAR · a month grid with the event days lit, the list beneath
// ─────────────────────────────────────────────────────────────────────────────
const WEEKDAYS = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

// Monday-first weeks of a month, `null` for the blanks either side.
export function monthWeeks(year, month) {
  if (!Number.isInteger(year) || !Number.isInteger(month)) return []
  const first = new Date(Date.UTC(year, month, 1))
  const lead = (first.getUTCDay() + 6) % 7
  const days = new Date(Date.UTC(year, month + 1, 0)).getUTCDate()
  const cells = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)]
  while (cells.length % 7) cells.push(null)
  const weeks = []
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7))
  return weeks
}

export function EVL_Calendar({ team, event = {}, list = {}, width = 1080, height = 1080, palette }) {
  const P = palette
  const A = aspectOf(width, height)
  const box = bodyBox(width, height)
  const paper = P.paper || '#f4efe4'
  const ink = P.deepInk || '#1f1c14'
  const items = (list.items || []).slice(0, MAX_LIST_ITEMS)
  const weeks = monthWeeks(list.year, list.month)
  const lit = new Map()
  items.forEach((it) => {
    if (it.iso && Number(it.iso.slice(0, 4)) === list.year && Number(it.iso.slice(5, 7)) - 1 === list.month) {
      const d = Number(it.iso.slice(8, 10))
      if (!lit.has(d)) lit.set(d, it)
    }
  })
  const titleMax = pick(A, { square: 84, portrait: 92, story: 100 })
  const head = headingH(A, titleMax, event)
  const legendRows = Math.max(1, Math.ceil(items.length / 2))
  const legendRowH = pick(A, { square: 44, portrait: 52, story: 58 })
  const legendH = legendRows * legendRowH + 18
  const calH = box.h - head - legendH - 18 - 36 - 30 - 12
  const dowH = 30
  const rows = Math.max(weeks.length, 4)
  const cellH = Math.max(40, Math.min(104, Math.floor((calH - dowH) / rows)))
  const cellW = Math.floor((width - 128) / 7)
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: paper, color: ink }}>
      <div data-layer="Event calendar" style={{ position: 'absolute', left: 64, right: 64, top: box.top, bottom: box.bottom, display: 'flex', flexDirection: 'column' }}>
        <Heading team={team} event={event} P={P} ink={ink} A={A} titleMax={titleMax} kickerColor={P.accent} fontFamily="'Helvetica Neue', Helvetica, Arial, sans-serif" uppercase={false} />
        <div style={{ marginTop: 18, flexShrink: 0, display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', borderTop: `2px solid ${ink}`, paddingTop: 8 }}>
          <div style={{ fontFamily: MONO, fontSize: 20, letterSpacing: 4, textTransform: 'uppercase', fontWeight: 700 }}>{list.monthLabel || ''}</div>
          <div style={{ fontFamily: MONO, fontSize: 13, letterSpacing: 2, textTransform: 'uppercase', color: a(ink, 0.5) }}>{items.length} {items.length === 1 ? 'event' : 'events'}</div>
        </div>
        <div style={{ flexShrink: 0 }}>
          <div style={{ display: 'flex', height: dowH, alignItems: 'center' }}>
            {WEEKDAYS.map((d, i) => <div key={i} style={{ width: cellW, textAlign: 'center', fontFamily: MONO, fontSize: 13, letterSpacing: 2, color: a(ink, 0.5) }}>{d}</div>)}
          </div>
          {weeks.length === 0 ? <div style={{ height: cellH * 4 }}><Empty ink={ink} /></div> : weeks.map((w, wi) => (
            <div key={wi} style={{ display: 'flex', height: cellH }}>
              {w.map((d, di) => {
                const ev = d ? lit.get(d) : null
                return (
                  <div key={di} style={{ width: cellW, height: cellH, boxSizing: 'border-box', padding: 3 }}>
                    {d ? (
                      <div style={{ width: '100%', height: '100%', borderRadius: 10, background: ev ? P.accent : 'transparent', border: ev ? 'none' : `1px solid ${a(ink, 0.12)}`, color: ev ? (P.primary || '#fff') : ink, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 2 }}>
                        <div style={{ fontFamily: SPORT, fontWeight: ev ? 800 : 500, fontSize: Math.round(cellH * (ev && ev.visual?.src ? 0.3 : 0.4)), lineHeight: 1 }}>{d}</div>
                        {ev && ev.visual?.src ? <img src={ev.visual.src} alt="" crossOrigin={ev.visual.kind === 'image' ? 'anonymous' : undefined} style={{ width: Math.round(cellH * 0.38), height: Math.round(cellH * 0.38), objectFit: ev.visual.kind === 'image' ? 'cover' : 'contain', borderRadius: ev.visual.kind === 'image' ? 6 : 0 }} /> : null}
                      </div>
                    ) : null}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
        <div style={{ marginTop: 'auto', flexShrink: 0, height: legendH, borderTop: `2px solid ${ink}`, paddingTop: 10, display: 'grid', gridTemplateColumns: '1fr 1fr', gridAutoRows: legendRowH, columnGap: 28 }}>
          {items.map((it) => (
            <div key={it.id} style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
              <div style={{ minWidth: Math.round(legendRowH * 0.95), height: Math.round(legendRowH * 0.8), padding: '0 6px', boxSizing: 'border-box', borderRadius: 8, background: ink, color: paper, fontFamily: SPORT, fontWeight: 800, fontSize: Math.round(legendRowH * 0.5), display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, whiteSpace: 'nowrap' }}>{it.day ? `${it.day}${lit.has(Number(it.day)) && lit.get(Number(it.day)) === it ? '' : ' ' + (it.mon || '')}` : '·'}</div>
              <div style={{ minWidth: 0 }}>
                <div style={{ fontWeight: 700, fontSize: Math.round(legendRowH * 0.4), lineHeight: 1.1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{it.title}</div>
                {it.time ? <div style={{ fontFamily: MONO, fontSize: Math.round(legendRowH * 0.26), letterSpacing: 1, color: a(ink, 0.55), whiteSpace: 'nowrap' }}>{it.time}</div> : null}
              </div>
            </div>
          ))}
        </div>
        <Credit event={event} color={a(ink, 0.45)} />
      </div>
    </LayerRoot>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EL3 — ICON CARDS · a grid of cards, each led by its icon or photo
// ─────────────────────────────────────────────────────────────────────────────
export function EVL_Cards({ team, event = {}, list = {}, width = 1080, height = 1080, palette }) {
  const P = palette
  const A = aspectOf(width, height)
  const box = bodyBox(width, height)
  const items = (list.items || []).slice(0, MAX_LIST_ITEMS)
  const n = Math.max(items.length, 1)
  const cols = n === 1 ? 1 : 2
  const rows = Math.ceil(n / cols)
  const titleMax = pick(A, { square: 96, portrait: 104, story: 112 })
  const head = headingH(A, titleMax, event)
  const gap = 16
  const gridH = box.h - head - 20 - 30
  const cardH = Math.floor((gridH - (rows - 1) * gap) / rows)
  const cardW = Math.floor((width - 128 - (cols - 1) * gap) / cols)
  const tall = cardH >= 200
  const t = Math.max(17, Math.min(pick(A, { square: 34, portrait: 38, story: 44 }), Math.round(cardH * (tall ? 0.105 : 0.13))))
  const s = Math.max(12, Math.min(pick(A, { square: 17, portrait: 19, story: 22 }), Math.round(cardH * 0.06)))
  const inner = cardH - 36
  // Tall cards stack: the picture takes what the text (date and price row, up to
  // two title lines, the time and place) leaves. Short cards run picture left.
  const textH = Math.round(s * 1.6 + 10 + 2 * t * 1.05 + s * 1.4 + 6 + 14)
  const visH = tall ? Math.max(56, Math.min(pick(A, { square: 190, portrait: 250, story: 330 }), inner - textH - 12)) : Math.round(inner * 0.9)
  return (
    <LayerRoot style={{ ...FRAME(width, height), background: P.primary, color: '#fff' }}>
      <div style={{ position: 'absolute', right: -220, bottom: -220, width: 620, height: 620, borderRadius: '50%', background: `radial-gradient(circle, ${a(P.accent, 0.22)}, transparent 68%)`, pointerEvents: 'none' }} />
      <div data-layer="Event cards" style={{ position: 'absolute', left: 64, right: 64, top: box.top, bottom: box.bottom, display: 'flex', flexDirection: 'column' }}>
        <Heading team={team} event={event} P={P} ink="#fff" A={A} titleMax={titleMax} />
        <div style={{ marginTop: 20, flex: 1, minHeight: 0 }}>
          {items.length === 0 ? <Empty ink="#fff" /> : (
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, ${cardW}px)`, gridAutoRows: cardH, gap }}>
              {items.map((it) => (
                <div key={it.id} style={{ boxSizing: 'border-box', borderRadius: 18, background: a('#ffffff', 0.06), border: `1px solid ${a(P.accent, 0.32)}`, padding: 18, display: 'flex', flexDirection: tall ? 'column' : 'row', alignItems: tall ? 'stretch' : 'center', justifyContent: tall ? 'center' : 'flex-start', gap: tall ? 14 : 16, overflow: 'hidden', minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: tall ? visH : undefined, flexShrink: 0 }}>
                    {tall && it.visual?.kind === 'image'
                      ? <div style={{ width: '100%', height: visH, borderRadius: 12, overflow: 'hidden' }}><img src={it.visual.src} alt="" crossOrigin="anonymous" style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} /></div>
                      : <Visual v={it.visual} size={tall ? visH : visH} accent={P.accent} radius={14} />}
                  </div>
                  <div style={{ minWidth: 0, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: tall ? 'flex-start' : 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 6 }}>
                      <div style={{ background: P.accent, color: P.primary, fontFamily: MONO, fontWeight: 700, fontSize: s, letterSpacing: 2, textTransform: 'uppercase', padding: '3px 10px', borderRadius: 6, whiteSpace: 'nowrap' }}>{it.dateLabel || 'Date'}</div>
                      {it.price ? <div style={{ fontFamily: SPORT, fontWeight: 800, fontSize: Math.round(t * 0.9), color: P.accent, letterSpacing: 0.5, whiteSpace: 'nowrap' }}>{it.price}</div> : null}
                    </div>
                    <div style={{ fontFamily: SPORT, fontWeight: 800, fontSize: t, lineHeight: 1.02, textTransform: 'uppercase', letterSpacing: 0.5, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>{it.title}</div>
                    {sub(it) ? <div style={{ fontFamily: MONO, fontSize: s, letterSpacing: 1, color: 'rgba(255,255,255,0.62)', marginTop: 5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sub(it)}</div> : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <Credit event={event} color="rgba(255,255,255,0.42)" />
      </div>
    </LayerRoot>
  )
}

// Registry entries, appended to EVENT_TEMPLATES by event-templates.jsx. `list: true`
// is what tells the editor to show the event list instead of one event's facts.
export const EVENT_LIST_TEMPLATES = [
  { id: 'EL1', name: 'Agenda', component: EVL_Agenda, desc: 'A dated list, an icon or photo on each', surface: 'dark', photo: false, list: true },
  { id: 'EL2', name: 'Calendar', component: EVL_Calendar, desc: 'Month grid with the event days lit', surface: 'light', photo: false, list: true },
  { id: 'EL3', name: 'Icon Cards', component: EVL_Cards, desc: 'A card per event, led by its icon', surface: 'dark', photo: false, list: true },
]

export const SPONSOR_SLOTS = { EL1: slotList, EL2: slotList, EL3: slotList }
