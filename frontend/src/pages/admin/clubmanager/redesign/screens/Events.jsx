import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, ManageLink, HEAD_SIDE, HEAD_CENTRE, HEAD_SIDE_END, HeaderSearch, matchesQuery } from '../ui'
import EntityManager, { reorderBySortOrder } from '../parts/EntityManager'

// Events — the club's real events (club_events) with their registrations.
// The redesign's ticket-type breakdown / volunteer-requirement aren't in the
// backend model, so we show what's held: capacity vs registrations, revenue,
// price, and the attendee list. Roster-this-event links through to the roster.

function money(cents) { return '$' + (Number(cents || 0) / 100).toLocaleString('en-AU', { minimumFractionDigits: 0, maximumFractionDigits: 2 }) }
function fmtWhen(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const day = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][d.getDay()]
  const mon = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()]
  const hh = d.getHours(), mm = d.getMinutes()
  const t = ((hh % 12) || 12) + (mm ? ':' + String(mm).padStart(2, '0') : '') + (hh < 12 ? 'am' : 'pm')
  return `${day} ${d.getDate()} ${mon} ${d.getFullYear()} · ${t}`
}
function eventStatus(e) {
  if (e.registration_open === false) return { label: 'DRAFT', fg: '#8a90a2' }
  if (e.is_ticketed) return { label: 'ON SALE', fg: 'var(--pb-accent)' }
  return { label: 'OPEN', fg: '#16c784' }
}
function payChip(status) {
  const s = (status || '').toLowerCase()
  if (s.includes('paid') || s.includes('complet')) return { label: 'PAID', border: 'rgba(22,199,132,0.4)', color: C.ok }
  if (s === 'free') return { label: 'FREE', border: 'rgba(22,199,132,0.4)', color: C.ok }
  if (s.includes('await') || s.includes('unpaid') || s.includes('pending')) return { label: 'UNPAID', border: 'rgba(245,181,66,0.45)', color: C.warn }
  if (s.includes('cancel')) return { label: 'CANCELLED', border: 'rgba(239,91,91,0.4)', color: C.block }
  return { label: (status || '').toUpperCase(), border: 'rgba(138,144,162,0.4)', color: C.dim }
}

export default function Events({ st, patch, narrow }) {
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [view, setView] = useState('events')

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const evRes = await api.committeeListEvents().catch(() => [])
        const events = (Array.isArray(evRes) ? evRes : (evRes?.events || [])).sort((a, b) => new Date(a.starts_at || 0) - new Date(b.starts_at || 0))
        const regsList = await Promise.all(events.map(e => api.eventListRegistrations(e.id).catch(() => ({ registrations: [], registered_count: 0, capacity: e.capacity }))))
        if (!alive) return
        const regs = {}
        events.forEach((e, i) => { regs[e.id] = regsList[i] })
        setData({ events, regs })
      } catch (e) { if (alive) setErr(String(e?.message || e)) }
    })()
    return () => { alive = false }
  }, [])

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }

  const q = (st.eventQuery || '').trim()

  // NEVER DECLARE A COMPONENT INSIDE A RENDER. React compares element types by
  // identity, so a `const Header = () => …` written here is a different type on
  // every render and its whole subtree is torn down and rebuilt — which throws
  // the caret out of the search box below after every character typed. A plain
  // function returning elements, CALLED rather than mounted, keeps the types
  // stable. Same fix the Committee screen carries.
  const header = () => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div style={HEAD_SIDE}>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>Events</h1>
        <Caption tone={C.faint} style={{ marginTop: 2 }}>TICKETING, RSVPS AND WHO IS COMING</Caption>
      </div>
      <div style={HEAD_CENTRE}>
        <SegTabs value={view} onChange={setView} tabs={[{ key: 'events', label: 'Events' }, { key: 'types', label: 'Event types' }]} />
      </div>
      <div style={HEAD_SIDE_END}>
        <ManageLink to="/admin/clubhouse/events/manage">Manage events &amp; tickets</ManageLink>
      </div>
      <HeaderSearch value={st.eventQuery} onChange={v => patch({ eventQuery: v })}
        placeholder={view === 'types' ? 'Search event types…' : 'Search events, venues and who is coming…'} />
    </ScreenHeader>
  )

  if (view === 'types') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
        {header()}
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '46rem' }}>
          <EntityManager
            describe="The kinds of event your club runs (Fundraiser, Social, Presentation night…). New events pick from these."
            load={() => api.eventListTypes().then(r => r?.types || r || [])}
            fields={[{ key: 'name', label: 'Event type', type: 'text', required: true, span: 2 }, { key: 'is_committee_only', label: 'Committee-only', type: 'checkbox' }, { key: 'description', label: 'Description', type: 'text', span: 2 }]}
            onCreate={v => api.eventCreateType(v)} onUpdate={(id, v) => api.eventUpdateType(id, v)} onDelete={id => api.eventArchiveType(id)}
            onReorder={reorderBySortOrder(api.eventUpdateType)}
            seed={{ label: 'Add Event Types Starter Pack', fn: () => api.eventSeedTypes(false) }}
            primaryKey="name" subtitle={it => [it.is_committee_only ? 'Committee-only' : null, it.description].filter(Boolean).join(' · ')}
            addLabel="Add event type" emptyText="No event types yet." query={q} />
        </div>
      </div>
    )
  }

  if (!data) return <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>{header()}<div style={{ padding: 24, fontSize: 13, color: C.faint }}>{err ? 'Could not load events.' : 'Loading events…'}</div></div>

  const { events, regs } = data
  // The search reaches what is INSIDE an event as well as its own fields — an
  // attendee's name matches the event they are coming to, because "which do I
  // have the Doyles down for" is a question this screen is actually asked.
  const shownEvents = !q ? events : events.filter(e =>
    matchesQuery(q, e.title, e.location, e.event_type)
    || (regs[e.id]?.registrations || []).some(r => matchesQuery(q, r.full_name, r.notes)))
  // The open event is kept even when the query no longer reaches it, so typing
  // never yanks the pane out from under whoever is reading it.
  const sel = events.find(e => e.id === st.event) || shownEvents[0] || events[0] || null
  const regInfo = sel ? (regs[sel.id] || { registrations: [], registered_count: 0, capacity: sel.capacity }) : null
  const attendees = regInfo?.registrations || []
  const sold = regInfo?.registered_count ?? attendees.reduce((a, r) => a + (r.quantity || 1), 0)
  // The server rolls this up over every registration; the client-side reduce is
  // the fallback for a backend that predates it.
  const fin = regInfo?.financials
  const revenue = fin ? Math.round(fin.taken * 100)
    : attendees.reduce((a, r) => a + ((payChip(r.payment_status).label === 'PAID') ? (r.amount_cents || 0) : 0), 0)
  const capacity = sel?.capacity || regInfo?.capacity || 0
  const pctCap = capacity ? Math.min(100, Math.round((sold / capacity) * 100)) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      {header()}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div className="pb-scroll" style={{ width: 290, flex: '0 0 290px', borderRight: `1px solid ${C.hair}`, overflowY: 'auto', padding: 14 }}>
          <div style={cap}>THIS SEASON</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {shownEvents.map(e => {
              const s = eventStatus(e)
              const n = regs[e.id]?.registered_count ?? 0
              return (
                <div key={e.id} onClick={() => patch({ event: e.id })}
                  style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '11px 12px', borderRadius: 8, cursor: 'pointer', border: sel && e.id === sel.id ? '1px solid color-mix(in srgb, var(--pb-accent) 40%, transparent)' : `1px solid ${C.hair}`, background: sel && e.id === sel.id ? 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' : C.surface }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0 }}>{e.title}</span>
                    <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${s.fg}66`, color: s.fg, flexShrink: 0 }}>{s.label}</span>
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{fmtWhen(e.starts_at).split(' · ')[0]}{e.location ? ' · ' + e.location : ''} · {n} in</div>
                </div>
              )
            })}
            {shownEvents.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>{q ? 'No event matches “' + q + '”.' : 'No events yet.'}</div>}
          </div>
        </div>

        {sel && (
          <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <h2 style={{ fontWeight: 700, fontSize: 21, margin: 0, letterSpacing: '-0.01em' }}>{sel.title}</h2>
              <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', padding: '3px 7px', borderRadius: 4, border: `1px solid ${eventStatus(sel).fg}66`, color: eventStatus(sel).fg }}>{eventStatus(sel).label}</span>
            </div>
            <div style={{ fontFamily: MONO, fontSize: 11, color: C.faint, margin: '5px 0 20px' }}>{fmtWhen(sel.starts_at)}{sel.location ? ' · ' + sel.location : ''}{sel.event_type ? ' · ' + sel.event_type : ''}</div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 8, marginBottom: 16 }}>
              {[
                { value: capacity ? sold + '/' + capacity : String(sold), label: sel.is_ticketed ? 'TICKETS SOLD' : 'REGISTERED' },
                { value: revenue ? money(revenue) : '—', label: 'REVENUE' },
                { value: sel.is_ticketed && sel.ticket_price_cents ? money(sel.ticket_price_cents) : (sel.is_ticketed ? 'Free' : '—'), label: 'TICKET PRICE' },
                ...(fin && fin.awaiting_payment > 0
                  ? [{ value: money(Math.round(fin.awaiting_payment * 100)), label: 'AWAITING PAYMENT', warn: true }]
                  : []),
                ...(fin && fin.expected !== fin.taken
                  ? [{ value: money(Math.round(fin.expected * 100)), label: 'EXPECTED IN TOTAL' }]
                  : []),
              ].map((s, i) => (
                <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                  <div style={{ fontWeight: 700, fontSize: 19, color: s.warn ? C.warn : C.accent, fontVariantNumeric: 'tabular-nums' }}>{s.value}</div>
                  <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint, marginTop: 3 }}>{s.label}</div>
                </div>
              ))}
            </div>

            {capacity > 0 && (
              <>
                <div style={{ height: 5, borderRadius: 3, background: C.surface2, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: pctCap + '%', background: pctCap > 90 ? C.warn : C.accent }} />
                </div>
                <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 5 }}>{pctCap}% of capacity</div>
              </>
            )}

            <div style={{ display: 'flex', gap: 7, marginTop: 18, flexWrap: 'wrap' }}>
              {/* Land on the week the event actually falls in, not whatever
                  week the roster happened to be showing. Monday-anchored, the
                  same rule the roster uses server-side. */}
              <button onClick={() => {
                let week
                if (sel.starts_at) {
                  const d = new Date(sel.starts_at)
                  const monday = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
                  monday.setUTCDate(monday.getUTCDate() - ((monday.getUTCDay() + 6) % 7))
                  week = monday.toISOString().slice(0, 10)
                }
                patch({ screen: 'roster', navOpen: false, rosterWeek: week })
              }} style={{ padding: '7px 12px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Roster this event →</button>
              {sel.organiser_name && <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint, alignSelf: 'center' }}>Organiser: {sel.organiser_name}</span>}
            </div>

            <div style={{ ...cap, margin: '24px 0 9px' }}>ATTENDEES</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, maxWidth: '46rem' }}>
              {attendees.map(a => {
                const pc = payChip(a.payment_status)
                return (
                  <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 11, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '9px 12px' }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13, color: C.text }}>{a.full_name}{a.quantity > 1 ? ' ×' + a.quantity : ''}</div>
                      {(a.amount_cents > 0 || a.notes) && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{a.amount_cents > 0 ? money(a.amount_cents) : ''}{a.notes ? (a.amount_cents > 0 ? ' · ' : '') + a.notes : ''}</div>}
                    </div>
                    {pc.label && <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, flexShrink: 0, border: `1px solid ${pc.border}`, color: pc.color }}>{pc.label}</span>}
                  </div>
                )
              })}
              {attendees.length === 0 && (
                <div style={{ background: C.surface, border: `1px dashed ${C.hair2}`, borderRadius: 9, padding: 24, textAlign: 'center', fontSize: 13, color: C.dim }}>No registrations yet. Share the event to start taking them.</div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
