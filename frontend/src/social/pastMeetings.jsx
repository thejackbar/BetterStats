// Past results against the opponent, as the design layouts draw them.
//
// `past` is the /admin/social/head-to-head answer: { found, opponent, meetings,
// wins, losses, draws, ties, form: ['W','L',…] newest first, recent: [{ played_at,
// grade_name, home_away, outcome }] }. A layout gets it only when the club has
// it switched on and the opponent was found; with nothing to say it draws
// nothing (never a made-up record).
const MONO = "'JetBrains Mono', monospace"
export const OUTCOME_COLOURS = { W: '#16a34a', L: '#dc2626', D: '#6b7280', T: '#a16207', NR: '#4b5563' }

export const hasPast = (past) => !!(past && past.found && past.meetings > 0)

export function recordLine(past) {
  if (!hasPast(past)) return ''
  const bits = [`${past.wins}-${past.losses}`]
  if (past.draws) bits.push(`${past.draws} D`)
  if (past.ties) bits.push(`${past.ties} T`)
  return `${bits.join(' ')} IN ${past.meetings} MEETING${past.meetings === 1 ? '' : 'S'}`
}

function Chip({ o, size }) {
  return (
    <span style={{ display: 'inline-grid', placeItems: 'center', width: size, height: size, background: OUTCOME_COLOURS[o] || '#4b5563', color: '#fff', fontSize: Math.round(size * 0.55), lineHeight: 1, borderRadius: 3 }}>{o}</span>
  )
}

// One line: "LAST 5  W W L T W   3-1 1 T IN 5 MEETINGS". `align` places it.
export function PastStrip({ past, x, y, w, f = 1, color = '#fff', align = 'center', layer = 'Past meetings', label = 'LAST MEETINGS', bg = null }) {
  if (!hasPast(past)) return null
  const chip = Math.round(30 * f)
  return (
    <div data-layer={layer} data-past-strip="" style={{
      position: 'absolute', left: x, top: y, width: w, display: 'flex', alignItems: 'center', gap: Math.round(8 * f),
      justifyContent: align === 'left' ? 'flex-start' : align === 'right' ? 'flex-end' : 'center', color, fontFamily: MONO,
      fontSize: Math.round(15 * f), letterSpacing: 2, whiteSpace: 'nowrap', overflow: 'hidden',
      ...(bg ? { background: bg, padding: `${Math.round(5 * f)}px ${Math.round(10 * f)}px`, width: 'auto', maxWidth: w, boxSizing: 'border-box' } : null),
    }}>
      <span style={{ opacity: 0.8 }}>{label}</span>
      {past.form.map((o, i) => <Chip key={i} o={o} size={chip} />)}
      <span style={{ opacity: 0.85, marginLeft: Math.round(6 * f) }}>{recordLine(past)}</span>
    </div>
  )
}

const shortDate = (iso) => {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00`)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' }).toUpperCase()
}

// The fuller block Head to Head draws: the record and the last few games.
export function PastBlock({ past, x, y, w, h, f = 1, color = '#fff', usC, rows = 4 }) {
  if (!hasPast(past)) return null
  const list = (past.recent || []).slice(0, rows)
  const rowH = Math.min(Math.round(44 * f), Math.floor((h - 60 * f) / Math.max(1, list.length)))
  return (
    <div data-layer="Past meetings" data-past-block="" style={{ position: 'absolute', left: x, top: y, width: w, height: h, color }}>
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, borderBottom: `2px solid ${color}33`, paddingBottom: 6 }}>
        <span style={{ fontFamily: MONO, fontSize: Math.round(15 * f), letterSpacing: 3, opacity: 0.85 }}>PAST MEETINGS</span>
        <span style={{ fontSize: Math.round(30 * f), color: usC }}>{recordLine(past)}</span>
      </div>
      {list.map((m, i) => (
        <div key={i} data-past-row="" style={{ height: rowH, display: 'flex', alignItems: 'center', gap: 14, borderBottom: `1px solid ${color}1a`, fontFamily: MONO, fontSize: Math.round(15 * f), letterSpacing: 1.5 }}>
          <Chip o={m.outcome || 'NR'} size={Math.round(rowH * 0.62)} />
          <span style={{ width: Math.round(150 * f) }}>{shortDate(m.played_at)}</span>
          <span style={{ flex: 1, minWidth: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{String(m.grade_name || '').toUpperCase()}</span>
          <span style={{ opacity: 0.75 }}>{m.home_away || ''}</span>
        </div>
      ))}
    </div>
  )
}

// A roundup row's last results against that row's opponent, as small chips
// beside the name. Nothing when the row has no past games.
export function RowForm({ past, size = 20, gap = 3, max = 5, style }) {
  if (!hasPast(past) || !(past.form || []).length) return null
  return (
    <span data-row-form="" title={recordLine(past)} style={{ display: 'inline-flex', alignItems: 'center', gap, flexShrink: 0, marginLeft: Math.round(size * 0.4), verticalAlign: 'middle', ...style }}>
      {past.form.slice(0, max).map((o, i) => <Chip key={i} o={o} size={size} />)}
    </span>
  )
}

// The past results as a block a club places on any layout (the Club data
// "Past results" block): the last five and the record on a backing panel.
// With no record it takes no space in the post; the editor shows where it is.
export function PastLine({ past, w, h, f = 1, color = '#fff', accent = '#ffc233', panel = 'dark', interactive = false, opponent = '' }) {
  if (!hasPast(past)) {
    if (!interactive) return <div style={{ width: w, height: h }} />
    return (
      <div style={{ width: w, height: h, boxSizing: 'border-box', border: `2px dashed ${color}66`, display: 'grid', placeItems: 'center', fontFamily: MONO, fontSize: 16, letterSpacing: 2, color: `${color}aa`, textAlign: 'center', padding: '0 12px' }}>
        {opponent ? `NO PAST RESULTS AGAINST ${String(opponent).toUpperCase()} · NOT SHOWN ON THE POST` : 'PAST RESULTS · TYPE THE OPPONENT'}
      </div>
    )
  }
  const bg = panel === 'light' ? 'rgba(255,255,255,0.92)' : panel === 'dark' ? 'rgba(8,10,14,0.72)' : 'transparent'
  const ink = panel === 'light' ? '#111111' : color
  const chip = Math.round(Math.min(h * 0.56, 34))
  return (
    <div data-past-line="" style={{ width: w, height: h, boxSizing: 'border-box', background: bg, borderRadius: Math.round(h / 2), display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, padding: `0 ${Math.round(h * 0.4)}px`, color: ink, fontFamily: MONO, fontSize: Math.round(Math.min(18, h * 0.3)), letterSpacing: 2, whiteSpace: 'nowrap', overflow: 'hidden' }}>
      <span style={{ opacity: 0.85 }}>V {String(past.opponent || opponent || '').toUpperCase()}</span>
      {past.form.map((o, i) => <Chip key={i} o={o} size={chip} />)}
      <span style={{ color: panel === 'light' ? '#111111' : accent }}>{recordLine(past)}</span>
    </div>
  )
}
