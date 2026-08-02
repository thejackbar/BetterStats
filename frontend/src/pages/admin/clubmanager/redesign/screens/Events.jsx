import { C, MONO, Caption, ScreenHeader, NavToggle } from '../ui'
import { EVENTS, EV_STATUS, money } from '../model'

// Events — ticketing, RSVPs, who is coming, and whether anyone is rostered.
export default function Events({ st, patch, narrow }) {
  const sel = EVENTS.find(e => e.id === (st.event || 'e3')) || EVENTS[2]
  const sold = sel.tickets.reduce((a, t) => a + t.sold, 0)
  const revenue = sel.tickets.reduce((a, t) => a + t.sold * t.price, 0)
  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }

  const paidChip = (paid) => {
    if (!paid) return null
    const border = paid === 'UNPAID' ? 'rgba(245,181,66,0.45)' : paid === 'RSVP NO' ? 'rgba(239,91,91,0.4)' : 'rgba(22,199,132,0.4)'
    const color = paid === 'UNPAID' ? C.warn : paid === 'RSVP NO' ? C.block : C.ok
    return { fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, flexShrink: 0, border: `1px solid ${border}`, color }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Events</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>TICKETING, RSVPS AND WHO IS COMING</Caption>
        </div>
      </ScreenHeader>

      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
        <div className="pb-scroll" style={{ width: 290, flex: '0 0 290px', borderRight: `1px solid ${C.hair}`, overflowY: 'auto', padding: 14 }}>
          <div style={cap}>THIS SEASON</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {EVENTS.map(e => {
              const s = EV_STATUS[e.status]
              const n = e.tickets.reduce((a, t) => a + t.sold, 0)
              return (
                <div key={e.id} onClick={() => patch({ event: e.id })}
                  style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '11px 12px', borderRadius: 8, cursor: 'pointer', border: e.id === sel.id ? '1px solid rgba(99,102,241,0.4)' : `1px solid ${C.hair}`, background: e.id === sel.id ? 'rgba(99,102,241,0.08)' : C.surface }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0 }}>{e.title}</span>
                    <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${s.fg}66`, color: s.fg, flexShrink: 0 }}>{s.label}</span>
                  </div>
                  <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{e.when.split(' · ')[0]} · {e.venue} · {e.kind === 'Ticketed' ? n + ' sold' : n + ' in'}</div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <h2 style={{ fontWeight: 700, fontSize: 21, margin: 0, letterSpacing: '-0.01em' }}>{sel.title}</h2>
            <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', padding: '3px 7px', borderRadius: 4, border: `1px solid ${EV_STATUS[sel.status].fg}66`, color: EV_STATUS[sel.status].fg }}>{EV_STATUS[sel.status].label}</span>
          </div>
          <div style={{ fontFamily: MONO, fontSize: 11, color: C.faint, margin: '5px 0 20px' }}>{sel.when} · {sel.venue} · {sel.kind}</div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 16 }}>
            {[
              { value: sold + '/' + sel.cap, label: sel.kind === 'Ticketed' ? 'TICKETS SOLD' : 'CONFIRMED' },
              { value: revenue ? money(revenue) : '—', label: 'REVENUE' },
              { value: sel.budget ? money(sel.budget) : '—', label: 'DIARY BUDGET' },
            ].map((s, i) => (
              <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                <div style={{ fontWeight: 700, fontSize: 19, color: C.accent, fontVariantNumeric: 'tabular-nums' }}>{s.value}</div>
                <div style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', color: C.faint, marginTop: 3 }}>{s.label}</div>
              </div>
            ))}
          </div>

          <div style={{ height: 5, borderRadius: 3, background: C.surface2, overflow: 'hidden' }}>
            <div style={{ height: '100%', width: Math.min(100, Math.round((sold / sel.cap) * 100)) + '%', background: sold / sel.cap > 0.9 ? C.warn : C.accent }} />
          </div>
          <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 5 }}>{Math.round((sold / sel.cap) * 100)}% of capacity</div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '22px 28px', marginTop: 24 }}>
            <div>
              <div style={cap}>TICKET TYPES</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {sel.tickets.map((t, i) => (
                  <div key={i}>
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                      <span style={{ fontSize: 13, color: C.text }}>{t.name} · {t.price ? money(t.price) : 'Free'}</span>
                      <span style={{ fontFamily: MONO, fontSize: 10.5, color: C.dim }}>{t.sold} / {t.qty}</span>
                    </div>
                    <div style={{ height: 4, borderRadius: 2, background: C.surface2, overflow: 'hidden', marginTop: 4 }}>
                      <div style={{ height: '100%', width: Math.round((t.sold / t.qty) * 100) + '%', background: C.accent }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div style={cap}>VOLUNTEERS NEEDED</div>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '10px 12px', borderRadius: 8, fontSize: 12.5, lineHeight: 1.45,
                ...(sel.needs.indexOf('nobody') > -1
                  ? { background: 'rgba(239,91,91,0.07)', border: '1px solid rgba(239,91,91,0.25)', color: C.block }
                  : { background: 'rgba(245,181,66,0.07)', border: '1px solid rgba(245,181,66,0.25)', color: C.warn }) }}>
                <span style={{ flexShrink: 0 }}>⚠</span><span>{sel.needs}</span>
              </div>
              <div style={{ display: 'flex', gap: 7, marginTop: 10, flexWrap: 'wrap' }}>
                <button onClick={() => patch({ screen: 'roster', navOpen: false })} style={outBtn}>Roster this event →</button>
                {sel.task && <button onClick={() => patch({ task: sel.task })} style={outBtn}>Open diary task →</button>}
              </div>
            </div>
          </div>

          <div style={{ ...cap, margin: '24px 0 9px' }}>ATTENDEES</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5, maxWidth: '46rem' }}>
            {sel.attendees.map((a, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 11, background: C.surface, border: `1px ${a.type ? 'solid' : 'dashed'} ${C.hair}`, borderRadius: 8, padding: '9px 12px', color: a.type ? undefined : C.faint }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, color: 'inherit' }}>{a.name}</div>
                  {(a.type || a.note) && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{a.type} {a.note}</div>}
                </div>
                {a.paid && <span style={paidChip(a.paid)}>{a.paid}</span>}
              </div>
            ))}
            {sel.attendees.length === 0 && (
              <div style={{ background: C.surface, border: `1px dashed ${C.hair2}`, borderRadius: 9, padding: 24, textAlign: 'center', fontSize: 13, color: C.dim }}>Not on sale yet — no attendees. Publish the event to start taking registrations.</div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

const outBtn = { padding: '7px 12px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: `1px solid var(--pb-hairline2)`, background: 'transparent', color: 'var(--pb-dim)', cursor: 'pointer' }
