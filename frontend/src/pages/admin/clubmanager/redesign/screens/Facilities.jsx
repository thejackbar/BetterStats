import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, Toast } from '../ui'
import {
  FACILITIES, SOURCES, BOOKINGS_SEED, REQUESTS_SEED, LOANS, ASSETS,
  overlaps, DAY_FROM, DAY_SPAN, FAC_ROW_H, FAC_STACK_MIN, fmtHour, DOW, DATES,
} from '../model'

// Facilities — availability at a glance, an approval queue with conflicts
// already detected, and gear-loan tracking. Absorbs Assets & Facilities +
// Bookings. Booking-block geometry is computed in pixels so a 2h booking clears
// its text and short blocks put title + time on one line.
export default function Facilities({ st, patch, narrow }) {
  const tab = st.facTab || 'availability'
  const bookings = st.bookings || BOOKINGS_SEED
  const requests = st.requests || REQUESTS_SEED
  const returned = st.returned || {}
  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }

  const conflictIds = {}
  bookings.forEach((a, i) => bookings.slice(i + 1).forEach(b => {
    if (overlaps(a, b)) { conflictIds[a.id] = true; conflictIds[b.id] = true }
  }))

  const Block = ({ b, isReq }) => {
    const src = SOURCES[b.src]
    const clash = !!conflictIds[b.id]
    const top = ((b.start - DAY_FROM) / DAY_SPAN) * FAC_ROW_H
    const height = Math.max(20, ((b.end - b.start) / DAY_SPAN) * FAC_ROW_H)
    const oneLine = height < FAC_STACK_MIN
    const fg = clash ? C.block : src.fg
    return (
      <div style={{ position: 'absolute', left: 3, right: 3, top, height, borderRadius: 5, padding: '2px 6px', overflow: 'hidden', cursor: 'pointer',
        ...(oneLine ? { display: 'flex', alignItems: 'baseline', gap: 6 } : {}),
        background: `color-mix(in srgb, ${src.fg} 18%, transparent)`,
        border: `1px ${isReq ? 'dashed' : 'solid'} ${clash ? C.block : `color-mix(in srgb, ${src.fg} 45%, transparent)`}`,
        backgroundImage: clash ? 'repeating-linear-gradient(45deg, transparent 0 4px, rgba(239,91,91,0.3) 4px 8px)' : undefined,
        opacity: isReq ? 0.85 : 1 }}>
        <div style={{ fontSize: 11, fontWeight: 600, lineHeight: 1.35, color: fg, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', ...(oneLine ? { minWidth: 0, flex: '0 1 auto' } : {}) }}>{b.title}</div>
        <div style={{ fontFamily: MONO, fontSize: 9, lineHeight: 1.35, color: fg, opacity: 0.8, whiteSpace: 'nowrap', ...(oneLine ? { flexShrink: 0 } : {}) }}>{fmtHour(b.start)}–{fmtHour(b.end)}</div>
      </div>
    )
  }

  const approve = (r) => {
    const fac = FACILITIES.find(f => f.id === r.fac)
    const clashes = bookings.filter(b => overlaps(r, b))
    if (clashes.length) {
      patch({ toast: { tone: 'block', title: 'That would double-book ' + fac.name + '.', body: 'Move it, shorten it, or decline — ' + clashes[0].title + ' has the space from ' + fmtHour(clashes[0].start) + '.' } })
      return
    }
    patch({
      bookings: bookings.concat([{ id: 'b-' + r.id, fac: r.fac, day: r.day, start: r.start, end: r.end, title: r.title, src: r.src }]),
      requests: requests.filter(x => x.id !== r.id),
      toast: { tone: 'ok', title: 'Approved — ' + r.title + '.', body: 'On the ' + fac.name + ' calendar, and it shows in Events and the Club Diary.' },
    })
  }
  const decline = (r) => patch({
    requests: requests.filter(x => x.id !== r.id),
    toast: { tone: 'info', title: 'Declined — ' + r.title + '.', body: r.who + ' is notified with the reason you give.' },
  })

  const activeLoans = LOANS.filter(l => !returned[l.id])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Facilities</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>WEEK OF MON 3 NOV 2026 · EACH COLUMN RUNS 8AM → MIDNIGHT</Caption>
        </div>
        <SegTabs value={tab} onChange={k => patch({ facTab: k })} tabs={[{ key: 'availability', label: 'Availability' }, { key: 'requests', label: 'Requests', badge: requests.length }, { key: 'assets', label: 'Assets & loans' }]} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginLeft: 'auto', flexWrap: 'wrap' }}>
          {Object.keys(SOURCES).map(k => (
            <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', color: C.faint }}>
              <span style={{ width: 7, height: 7, borderRadius: 2, background: SOURCES[k].fg }} />{SOURCES[k].label}
            </span>
          ))}
        </div>
      </ScreenHeader>

      <Toast toast={st.toast} onClear={() => patch({ toast: null })} />

      {tab === 'availability' && (
        <div className="pb-scroll" style={{ flex: 1, overflow: 'auto' }}>
          <div style={{ minWidth: 1100 }}>
            <div style={{ display: 'grid', gridTemplateColumns: '200px repeat(7, minmax(0, 1fr))', position: 'sticky', top: 0, zIndex: 20, background: C.bg, borderBottom: `1px solid ${C.hair2}` }}>
              <div style={{ padding: '9px 14px', borderRight: `1px solid ${C.hair}`, fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, display: 'flex', alignItems: 'center' }}>FACILITY</div>
              {DOW.map((d, i) => (
                <div key={i} style={{ padding: '9px 11px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', gap: 2, background: i >= 5 ? 'rgba(99,102,241,0.05)' : undefined }}>
                  <span style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faint }}>{d.toUpperCase()}</span>
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: C.dim }}>{DATES[i]}</span>
                </div>
              ))}
            </div>
            {FACILITIES.map(f => {
              const mine = bookings.filter(b => b.fac === f.id)
              const hours = mine.reduce((a, b) => a + (b.end - b.start), 0)
              return (
                <div key={f.id} style={{ display: 'grid', gridTemplateColumns: '200px repeat(7, minmax(0, 1fr))', borderBottom: `1px solid ${C.hair}` }}>
                  <div style={{ padding: '11px 14px', borderRight: `1px solid ${C.hair}`, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 3 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{f.name}</div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{f.kind}</div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest }}>{hours.toFixed(0)}h booked</div>
                  </div>
                  {DOW.map((_, d) => (
                    <div key={d} style={{ position: 'relative', borderRight: `1px solid ${C.hair}`, height: FAC_ROW_H, background: d >= 5 ? 'rgba(99,102,241,0.03)' : undefined }}>
                      {mine.filter(b => b.day === d).map(b => <Block key={b.id} b={b} isReq={false} />)}
                    </div>
                  ))}
                </div>
              )
            })}
          </div>
        </div>
      )}

      {tab === 'requests' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '62rem' }}>
          <p style={{ fontSize: 13, color: C.dim, margin: '0 0 14px', lineHeight: 1.55 }}>Requests come in from members, coaches and external hirers. Each one is checked against every confirmed booking on that space before you see it — clashes are flagged, not discovered later.</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
            {requests.map(r => {
              const clashes = bookings.filter(b => overlaps(r, b))
              const fac = FACILITIES.find(f => f.id === r.fac)
              const src = SOURCES[r.src]
              return (
                <div key={r.id} style={{ background: C.surface, border: `1px solid ${clashes.length ? 'rgba(239,91,91,0.35)' : C.hair}`, borderRadius: 9, padding: '13px 15px' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                        <span style={{ fontSize: 14.5, fontWeight: 600, color: C.text }}>{r.title}</span>
                        <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${src.fg}66`, color: src.fg, flexShrink: 0 }}>{src.label}</span>
                      </div>
                      <div style={{ fontFamily: MONO, fontSize: 11, color: C.dim, marginTop: 5 }}>{fac.name} · {DOW[r.day]} {DATES[r.day]} · {fmtHour(r.start)}–{fmtHour(r.end)}</div>
                      <div style={{ fontSize: 12.5, color: C.faint, marginTop: 4 }}>{r.who} · {r.note}</div>
                    </div>
                    <div style={{ display: 'flex', gap: 7, flexShrink: 0 }}>
                      <button onClick={() => approve(r)} style={{ padding: '7px 13px', borderRadius: 7, fontSize: 12.5, fontWeight: 600, border: 'none', cursor: 'pointer', ...(clashes.length ? { background: C.surface2, color: C.faint } : { background: C.accent, color: '#fff' }) }}>{clashes.length ? 'Approve anyway' : 'Approve'}</button>
                      <button onClick={() => decline(r)} style={{ padding: '7px 13px', borderRadius: 7, fontSize: 12.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer' }}>Decline</button>
                    </div>
                  </div>
                  {clashes.length > 0 && (
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 7, marginTop: 9, padding: '8px 10px', borderRadius: 7, background: 'rgba(239,91,91,0.08)', fontSize: 12, color: C.block, lineHeight: 1.4 }}>
                      <span style={{ flexShrink: 0 }}>⚠</span>
                      <span>Double-booking — {clashes.map(c => c.title + ' (' + fmtHour(c.start) + '–' + fmtHour(c.end) + ')').join(', ')} already holds this space.</span>
                    </div>
                  )}
                </div>
              )
            })}
            {requests.length === 0 && (
              <div style={{ background: C.surface, border: `1px dashed ${C.hair2}`, borderRadius: 9, padding: 28, textAlign: 'center', fontSize: 13.5, color: C.dim }}>Nothing waiting on you. New requests land here with their conflicts already checked.</div>
            )}
          </div>
        </div>
      )}

      {tab === 'assets' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28, maxWidth: '72rem' }}>
            <div>
              <div style={cap}>OUT ON LOAN</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {activeLoans.map(l => (
                  <div key={l.id} style={{ display: 'flex', alignItems: 'center', gap: 12, background: C.surface, border: `1px solid ${l.overdue ? 'rgba(239,91,91,0.35)' : C.hair}`, borderRadius: 8, padding: '10px 13px' }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{l.item}</div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{l.to} · out {l.out} · due {l.due}</div>
                    </div>
                    <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, flexShrink: 0, border: `1px solid ${l.overdue ? 'rgba(239,91,91,0.5)' : 'rgba(22,199,132,0.4)'}`, color: l.overdue ? C.block : C.ok }}>{l.overdue ? 'OVERDUE' : 'ON LOAN'}</span>
                    <button onClick={() => patch({ returned: { ...returned, [l.id]: true }, toast: { tone: 'ok', title: l.item + ' returned.', body: 'Back in the shed and available to loan again.' } })} style={{ padding: '5px 10px', borderRadius: 6, fontSize: 11.5, border: `1px solid ${C.hair2}`, background: 'transparent', color: C.dim, cursor: 'pointer', flexShrink: 0 }}>Returned</button>
                  </div>
                ))}
                {activeLoans.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>Everything is back in the shed.</div>}
              </div>
            </div>
            <div>
              <div style={cap}>INVENTORY</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                {ASSETS.map((a, i) => (
                  <div key={i}>
                    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
                      <span style={{ fontSize: 13, color: C.text }}>{a.name}</span>
                      <span style={{ fontFamily: MONO, fontSize: 10, color: C.dim }}>{a.total - a.out} of {a.total} available</span>
                    </div>
                    <div style={{ height: 4, borderRadius: 2, background: C.surface2, overflow: 'hidden', marginTop: 4 }}>
                      <div style={{ height: '100%', width: Math.round(((a.total - a.out) / a.total) * 100) + '%', background: a.out === a.total ? C.block : C.ok }} />
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faintest, marginTop: 3 }}>{a.cond}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
