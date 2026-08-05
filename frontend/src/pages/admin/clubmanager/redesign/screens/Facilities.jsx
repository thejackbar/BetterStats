import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, Toast , ManageLink } from '../ui'
import EntityManager from '../parts/EntityManager'

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
  const [reqs, setReqs] = useState([])
  const [err, setErr] = useState(null)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ facility_id: '', title: '', starts_at: '', ends_at: '', requester_name: '' })

  const loadReqs = () => api.facilityRequests().then(r => setReqs(r?.requests || r || [])).catch(() => {})
  useEffect(() => {
    let alive = true
    Promise.all([
      api.assetsListFacilities().catch(() => ([])),
      api.assetsListBookings({ upcomingOnly: false }).catch(() => ([])),
      api.assetsListItems({}).catch(() => ([])),
      api.facilityRequests().catch(() => ({ requests: [] })),
    ]).then(([facRes, bookRes, itemRes, reqRes]) => {
      if (!alive) return
      setData({
        facilities: (facRes?.facilities || facRes || []).filter(f => f.is_active !== false),
        bookings: bookRes?.bookings || bookRes || [],
        assets: (itemRes?.items || itemRes || []).filter(a => a.is_active !== false),
      })
      setReqs(reqRes?.requests || reqRes || [])
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
      <ManageLink to="/admin/clubhouse/facilities/manage">Manage assets &amp; bookings</ManageLink>
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

  const fmtWhen = (r) => {
    const s = new Date(r.starts_at), e = new Date(r.ends_at)
    return r.facility_name + ' · ' + DOW[(s.getDay() + 6) % 7] + ' ' + s.getDate() + '/' + (s.getMonth() + 1) + ' · ' + fmtHour(hoursOf(s)) + '–' + fmtHour(hoursOf(e))
  }
  const approveReq = async (r) => {
    if (r.clashes && r.clashes.length) {
      const c = r.clashes[0]
      patch({ toast: { tone: 'block', title: 'That would double-book ' + r.facility_name + '.', body: 'Move it, shorten it, or decline — ' + c.title + ' already holds the space.' } })
      return
    }
    const res = await api.facilityRequestApprove(r.id).catch(() => null)
    if (res && res.ok === false && res.clashes) { patch({ toast: { tone: 'block', title: 'That would double-book ' + r.facility_name + '.', body: 'A confirmed booking already holds the space.' } }); await loadReqs(); return }
    await loadReqs()
    api.assetsListBookings({ upcomingOnly: false }).then(b => setData(d => ({ ...d, bookings: b?.bookings || b || [] }))).catch(() => {})
    patch({ toast: { tone: 'ok', title: 'Approved — ' + r.title + '.', body: 'On the ' + r.facility_name + ' calendar now.' } })
  }
  const declineReq = async (r) => { await api.facilityRequestDecline(r.id).catch(() => {}); await loadReqs(); patch({ toast: { tone: 'info', title: 'Declined — ' + r.title + '.', body: 'The requester can be notified with your reason.' } }) }
  const clearReqs = async () => { if (!window.confirm('Clear all pending requests? (Testing reset — only this club.)')) return; await api.facilityRequestsClear().catch(() => {}); await loadReqs() }
  const submitReq = async () => {
    if (!form.facility_id || !form.title || !form.starts_at || !form.ends_at) { patch({ toast: { tone: 'block', title: 'Fill in the request.', body: 'Facility, title, start and end are required.' } }); return }
    await api.facilityRequestCreate({ facility_id: form.facility_id, title: form.title, starts_at: new Date(form.starts_at).toISOString(), ends_at: new Date(form.ends_at).toISOString(), requester_name: form.requester_name || null }).catch(() => {})
    setForm({ facility_id: '', title: '', starts_at: '', ends_at: '', requester_name: '' }); setAdding(false); await loadReqs()
  }
  const inp = { background: C.surface2, border: `1px solid ${C.hair2}`, borderRadius: 7, padding: '7px 10px', color: C.text, fontSize: 13, outline: 'none' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header />
      <Toast toast={st.toast} onClear={() => patch({ toast: null })} />

      {tab === 'availability' && (
        <div className="pb-scroll" style={{ flex: 1, overflow: 'auto' }}>
          {facilities.length === 0 ? (
            <div style={{ padding: 24, fontSize: 13.5, color: C.dim, maxWidth: '46rem' }}>No facilities set up yet. Add your grounds, nets and clubrooms in the Assets &amp; Facilities admin and their bookings will show here.</div>
          ) : (
            <div style={{ minWidth: 1100 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '200px repeat(7, minmax(0, 1fr))', position: 'sticky', top: 0, zIndex: 20, background: C.bg, borderBottom: `1px solid ${C.hair2}` }}>
                <div style={{ padding: '9px 14px', borderRight: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, display: 'flex', alignItems: 'center' }}>FACILITY</div>
                {DOW.map((d, i) => (
                  <div key={i} style={{ padding: '9px 11px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 2, background: i >= 5 ? 'color-mix(in srgb, var(--pb-accent) 5%, transparent)' : undefined }}>
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
                      <div key={d} style={{ position: 'relative', borderRight: `1px solid ${C.hair}`, height: FAC_ROW_H, background: d >= 5 ? 'color-mix(in srgb, var(--pb-accent) 3%, transparent)' : undefined }}>
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
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '62rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
            <p style={{ fontSize: 13, color: C.dim, margin: 0, lineHeight: 1.55, flex: 1 }}>Each request is checked against every confirmed booking on that space before you see it — clashes are flagged, not discovered later.</p>
            <button onClick={() => setAdding(a => !a)} style={{ padding: '7px 12px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer', flexShrink: 0 }}>{adding ? 'Cancel' : '+ New request'}</button>
            {reqs.length > 0 && <button onClick={clearReqs} style={{ padding: '7px 12px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.faint, cursor: 'pointer', flexShrink: 0 }}>Clear all</button>}
          </div>

          {adding && (
            <div style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 9, padding: 14, marginBottom: 12, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <select value={form.facility_id} onChange={e => setForm(f => ({ ...f, facility_id: e.target.value }))} style={inp}>
                <option value="">Facility…</option>
                {facilities.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
              </select>
              <input placeholder="Title (e.g. Doyle engagement)" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} style={inp} />
              <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>START<input type="datetime-local" value={form.starts_at} onChange={e => setForm(f => ({ ...f, starts_at: e.target.value }))} style={{ ...inp, width: '100%', marginTop: 3 }} /></label>
              <label style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>END<input type="datetime-local" value={form.ends_at} onChange={e => setForm(f => ({ ...f, ends_at: e.target.value }))} style={{ ...inp, width: '100%', marginTop: 3 }} /></label>
              <input placeholder="Requester name (optional)" value={form.requester_name} onChange={e => setForm(f => ({ ...f, requester_name: e.target.value }))} style={inp} />
              <button onClick={submitReq} style={{ padding: '7px 12px', borderRadius: 7, fontSize: 13, fontWeight: 600, border: 'none', background: C.accent, color: '#fff', cursor: 'pointer' }}>Add request</button>
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
            {reqs.map(r => (
              <div key={r.id} style={{ background: C.surface, border: `1px solid ${r.clashes.length ? 'rgba(239,91,91,0.35)' : C.hair}`, borderRadius: 9, padding: '13px 15px' }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 14.5, fontWeight: 600, color: C.text }}>{r.title}</div>
                    <div style={{ fontFamily: MONO, fontSize: 11, color: C.dim, marginTop: 5 }}>{fmtWhen(r)}</div>
                    {(r.requester_name || r.note) && <div style={{ fontSize: 12.5, color: C.faint, marginTop: 4 }}>{[r.requester_name, r.note].filter(Boolean).join(' · ')}</div>}
                  </div>
                  <div style={{ display: 'flex', gap: 7, flexShrink: 0 }}>
                    <button onClick={() => approveReq(r)} style={{ padding: '7px 13px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: 'none', cursor: 'pointer', ...(r.clashes.length ? { background: C.surface2, color: C.faint } : { background: C.accent, color: '#fff' }) }}>{r.clashes.length ? 'Approve anyway' : 'Approve'}</button>
                    <button onClick={() => declineReq(r)} style={{ padding: '7px 13px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Decline</button>
                  </div>
                </div>
                {r.clashes.length > 0 && (
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 7, marginTop: 9, padding: '8px 10px', borderRadius: 7, background: 'rgba(239,91,91,0.08)', fontSize: 12, color: C.block, lineHeight: 1.4 }}>
                    <span style={{ flexShrink: 0 }}>⚠</span>
                    <span>Double-booking — {r.clashes.map(c => c.title).join(', ')} already holds this space.</span>
                  </div>
                )}
              </div>
            ))}
            {reqs.length === 0 && (
              <div style={{ background: C.surface, border: `1px dashed ${C.hair2}`, borderRadius: 9, padding: 28, textAlign: 'center', fontSize: 13.5, color: C.dim }}>Nothing waiting on you. New requests land here with their conflicts already checked.</div>
            )}
          </div>
        </div>
      )}

      {tab === 'assets' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '56rem' }}>
          <div style={cap}>FACILITIES</div>
          <EntityManager
            describe="Your grounds, nets and rooms — bookings and the availability grid read from these."
            load={() => api.assetsListFacilities().then(r => (r?.facilities || r || []).filter(f => f.is_active !== false))}
            fields={[{ key: 'name', label: 'Facility name', type: 'text', required: true, span: 2 }, { key: 'facility_type', label: 'Kind', type: 'text' }, { key: 'key_location', label: 'Key location', type: 'text' }, { key: 'description', label: 'Description', type: 'text', span: 2 }]}
            onCreate={v => api.assetsCreateFacility(v)} onUpdate={(id, v) => api.assetsUpdateFacility(id, v)} onDelete={id => api.assetsDeleteFacility(id)}
            seed={{ label: 'Add Facilities Starter Pack', fn: () => api.assetsSeedFacilities() }}
            primaryKey="name" subtitle={it => [it.facility_type, it.key_location, it.description].filter(Boolean).join(' · ')}
            addLabel="Add facility" emptyText="No facilities yet." />

          <div style={{ ...cap, marginTop: 26 }}>ASSETS</div>
          <EntityManager
            describe="Club gear — kit bags, machines, markers and the like."
            load={() => api.assetsListItems({}).then(r => (r?.items || r || []).filter(a => a.is_active !== false))}
            fields={[{ key: 'name', label: 'Asset', type: 'text', required: true, span: 2 }, { key: 'category', label: 'Category', type: 'text' }, { key: 'condition', label: 'Condition', type: 'text' }, { key: 'status', label: 'Status', type: 'text' }, { key: 'notes', label: 'Notes', type: 'text', span: 2 }]}
            onCreate={v => api.assetsCreateItem(v)} onUpdate={(id, v) => api.assetsUpdateItem(id, v)} onDelete={id => api.assetsDeleteItem(id)}
            seed={{ label: 'Add Assets Starter Pack', fn: () => api.assetsSeedItems() }}
            primaryKey="name" subtitle={it => [it.category, it.condition, it.status].filter(Boolean).join(' · ')}
            addLabel="Add asset" emptyText="No assets yet." />
        </div>
      )}
    </div>
  )
}
