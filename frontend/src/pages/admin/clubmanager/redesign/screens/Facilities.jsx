import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs } from '../ui'

// Facilities on real data — the availability grid (this week's real bookings,
// with client-side conflict detection) and the asset register. The redesign's
// booking-requests approval queue is net-new backend and lands next; that tab
// shows a clear placeholder for now.

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const DAY_FROM = 8, DAY_TO = 24, DAY_SPAN = DAY_TO - DAY_FROM
const FAC_ROW_H = 190, FAC_STACK_MIN = 26
function fmtHour(h) { const hh = Math.floor(h), mm = Math.round((h - hh) * 60); if (hh >= 24) return '12am'; let b = hh % 12; if (b === 0) b = 12; return b + (mm ? ':' + String(mm).padStart(2, '0') : '') + (hh >= 12 ? 'pm' : 'am') }
function monday(d) { const x = new Date(d); const day = (x.getDay() + 6) % 7; x.setHours(0, 0, 0, 0); x.setDate(x.getDate() - day); return x }
const hoursOf = (dt) => dt.getHours() + dt.getMinutes() / 60

export default function Facilities({ st, patch, narrow }) {
  const tab = st.facTab || 'availability'
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    Promise.all([
      api.assetsListFacilities().catch(() => ([])),
      api.assetsListBookings({ upcomingOnly: false }).catch(() => ([])),
      api.assetsListItems({}).catch(() => ([])),
    ]).then(([facRes, bookRes, itemRes]) => {
      if (!alive) return
      setData({
        facilities: (facRes?.facilities || facRes || []).filter(f => f.is_active !== false),
        bookings: bookRes?.bookings || bookRes || [],
        assets: (itemRes?.items || itemRes || []).filter(a => a.is_active !== false),
      })
    }).catch(e => { if (alive) setErr(String(e?.message || e)) })
    return () => { alive = false }
  }, [])

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }
  const Header = ({ children }) => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Facilities</h1>
        <Caption tone={C.faint} style={{ marginTop: 2 }}>THIS WEEK · EACH COLUMN RUNS 8AM → MIDNIGHT</Caption>
      </div>
      <SegTabs value={tab} onChange={k => patch({ facTab: k })} tabs={[{ key: 'availability', label: 'Availability' }, { key: 'requests', label: 'Requests' }, { key: 'assets', label: 'Assets' }]} />
      {children}
    </ScreenHeader>
  )

  if (!data) return <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}><Header /><div style={{ padding: 24, fontSize: 13, color: C.faint }}>{err ? 'Could not load facilities.' : 'Loading facilities…'}</div></div>

  const { facilities, bookings, assets } = data
  const weekStart = monday(new Date())
  const weekEnd = new Date(weekStart); weekEnd.setDate(weekStart.getDate() + 7)
  const dates = DOW.map((_, i) => { const d = new Date(weekStart); d.setDate(weekStart.getDate() + i); return d.getDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()] })

  // map this week's bookings onto (facility, day, hours) blocks
  const weekBookings = []
  bookings.forEach(b => {
    if (!b.starts_at || !b.ends_at) return
    const s = new Date(b.starts_at), e = new Date(b.ends_at)
    if (e <= weekStart || s >= weekEnd) return
    const day = Math.floor((new Date(s.getFullYear(), s.getMonth(), s.getDate()) - weekStart) / 86400000)
    if (day < 0 || day > 6) return
    weekBookings.push({ id: b.id, fac: b.facility_id, day, start: hoursOf(s), end: (e.getDate() !== s.getDate() ? 24 : hoursOf(e)), title: b.title || 'Booking' })
  })
  const conflict = {}
  weekBookings.forEach((a, i) => weekBookings.slice(i + 1).forEach(b => {
    if (a.fac === b.fac && a.day === b.day && a.start < b.end && b.start < a.end) { conflict[a.id] = true; conflict[b.id] = true }
  }))

  const Block = ({ b }) => {
    const clash = !!conflict[b.id]
    const top = ((Math.max(DAY_FROM, b.start) - DAY_FROM) / DAY_SPAN) * FAC_ROW_H
    const height = Math.max(20, ((Math.min(DAY_TO, b.end) - Math.max(DAY_FROM, b.start)) / DAY_SPAN) * FAC_ROW_H)
    const oneLine = height < FAC_STACK_MIN
    const fg = clash ? C.block : C.accent
    return (
      <div style={{ position: 'absolute', left: 3, right: 3, top, height, borderRadius: 5, padding: '2px 6px', overflow: 'hidden',
        ...(oneLine ? { display: 'flex', alignItems: 'baseline', gap: 6 } : {}),
        background: `color-mix(in srgb, ${fg} 18%, transparent)`, border: `1px solid ${clash ? C.block : `color-mix(in srgb, ${C.accent} 45%, transparent)`}`,
        backgroundImage: clash ? 'repeating-linear-gradient(45deg, transparent 0 4px, rgba(239,91,91,0.3) 4px 8px)' : undefined }}>
        <div style={{ fontSize: 11, fontWeight: 600, lineHeight: 1.35, color: fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', ...(oneLine ? { minWidth: 0, flex: '0 1 auto' } : {}) }}>{b.title}</div>
        <div style={{ fontFamily: MONO, fontSize: 9, lineHeight: 1.35, color: fg, opacity: 0.8, whiteSpace: 'nowrap', ...(oneLine ? { flexShrink: 0 } : {}) }}>{fmtHour(b.start)}–{fmtHour(b.end)}</div>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header />

      {tab === 'availability' && (
        <div className="pb-scroll" style={{ flex: 1, overflow: 'auto' }}>
          {facilities.length === 0 ? (
            <div style={{ padding: 24, fontSize: 13.5, color: C.dim, maxWidth: '46rem' }}>No facilities set up yet. Add your grounds, nets and clubrooms in the Assets &amp; Facilities admin and their bookings will show here.</div>
          ) : (
            <div style={{ minWidth: 1100 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '200px repeat(7, minmax(0, 1fr))', position: 'sticky', top: 0, zIndex: 20, background: C.bg, borderBottom: `1px solid ${C.hair2}` }}>
                <div style={{ padding: '9px 14px', borderRight: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, display: 'flex', alignItems: 'center' }}>FACILITY</div>
                {DOW.map((d, i) => (
                  <div key={i} style={{ padding: '9px 11px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 2, background: i >= 5 ? 'rgba(99,102,241,0.05)' : undefined }}>
                    <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faint }}>{d.toUpperCase()}</span>
                    <span style={{ fontSize: 12.5, fontWeight: 600, color: C.dim }}>{dates[i]}</span>
                  </div>
                ))}
              </div>
              {facilities.map(f => {
                const mine = weekBookings.filter(b => b.fac === f.id)
                const hours = mine.reduce((a, b) => a + (b.end - b.start), 0)
                return (
                  <div key={f.id} style={{ display: 'grid', gridTemplateColumns: '200px repeat(7, minmax(0, 1fr))', borderBottom: `1px solid ${C.hair}` }}>
                    <div style={{ padding: '11px 14px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 3 }}>
                      <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{f.name}</div>
                      {f.facility_type && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{f.facility_type}</div>}
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>{hours.toFixed(0)}h booked</div>
                    </div>
                    {DOW.map((_, d) => (
                      <div key={d} style={{ position: 'relative', borderRight: `1px solid ${C.hair}`, height: FAC_ROW_H, background: d >= 5 ? 'rgba(99,102,241,0.03)' : undefined }}>
                        {mine.filter(b => b.day === d).map(b => <Block key={b.id} b={b} />)}
                      </div>
                    ))}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {tab === 'requests' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '46rem' }}>
          <div style={{ background: C.surface, border: `1px dashed ${C.hair2}`, borderRadius: 9, padding: 22, fontSize: 13.5, color: C.dim, lineHeight: 1.6 }}>
            The booking-requests approval queue — where a request is checked against every confirmed booking on that space before you approve it, with clashes flagged up front — is being built next. For now, bookings are managed directly in the Assets &amp; Facilities admin.
          </div>
        </div>
      )}

      {tab === 'assets' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '60rem' }}>
          {assets.length === 0 ? (
            <div style={{ fontSize: 13.5, color: C.dim }}>No assets recorded yet. Add club gear in the Assets &amp; Facilities admin.</div>
          ) : (
            [...new Set(assets.map(a => a.category || 'Uncategorised'))].map(catg => (
              <div key={catg} style={{ marginBottom: 20 }}>
                <div style={cap}>{catg}</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {assets.filter(a => (a.category || 'Uncategorised') === catg).map(a => {
                    const s = (a.status || '').toLowerCase()
                    const out = s ? !s.includes('avail') : false
                    const chipFg = out ? C.warn : C.ok
                    return (
                      <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 12, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 13px' }}>
                        <div style={{ minWidth: 0, flex: 1 }}>
                          <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{a.name}</div>
                          <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{[a.condition, a.service_due_date ? 'service due ' + a.service_due_date : null].filter(Boolean).join(' · ') || 'No condition recorded'}</div>
                        </div>
                        {a.status && <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, flexShrink: 0, border: `1px solid ${chipFg}66`, color: chipFg }}>{a.status.toUpperCase().replace(/_/g, ' ')}</span>}
                      </div>
                    )
                  })}
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  )
}
