import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, StatReadout } from '../ui'
import { POSITIONS, MEETINGS, CTE_STATUS, ACTION_STATE, dirIdFor } from '../model'

// Committee — positions, and the meeting record that actually governs the club.
export default function Committee({ st, patch, narrow }) {
  const tab = st.cteTab || 'meetings'
  const sel = MEETINGS.find(m => m.id === (st.cteMeeting || 'm5')) || MEETINGS[1]

  const goPerson = (name) => () => {
    const id = dirIdFor(name)
    if (id) patch({ screen: 'directory', dirSel: id, dirSeg: 'All', dirRole: null, dirQuery: '', navOpen: false })
  }

  const allActions = []
  MEETINGS.forEach(m => m.actions.forEach(a => allActions.push({ ...a, from: m.title, date: m.date })))
  const openActions = allActions.filter(a => a.state !== 'done')

  const allMotions = []
  MEETINGS.forEach(m => m.motions.forEach(mo => allMotions.push({ ...mo, from: m.kind + ' · ' + m.date })))

  const vacancies = POSITIONS.filter(p => !p.holder)
  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }

  const chip = (fg, fs = 8.5) => ({ fontFamily: MONO, fontSize: fs, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${fg}66`, color: fg, flexShrink: 0 })
  const motionChip = (outcome) => ({ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, flexShrink: 0, border: `1px solid ${outcome.indexOf('Lost') === 0 ? 'rgba(239,91,91,0.45)' : 'rgba(22,199,132,0.4)'}`, color: outcome.indexOf('Lost') === 0 ? C.block : C.ok })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <ScreenHeader>
        <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
        <div>
          <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Committee</h1>
          <Caption tone={C.faint} style={{ marginTop: 2 }}>2026/27 SEASON</Caption>
        </div>
        <SegTabs value={tab} onChange={k => patch({ cteTab: k })} tabs={[{ key: 'meetings', label: 'Meetings' }, { key: 'positions', label: 'Positions' }, { key: 'motions', label: 'Motions & actions' }]} />
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginLeft: 'auto', flexWrap: 'wrap' }}>
          <StatReadout value={(POSITIONS.length - vacancies.length) + '/' + POSITIONS.length} label="POSITIONS FILLED" fg={vacancies.length ? C.warn : C.ok} />
          <StatReadout value={String(openActions.length)} label="OPEN ACTIONS" fg={openActions.filter(a => a.state === 'overdue').length ? C.block : C.text} />
          <StatReadout value={String(allMotions.length)} label="MOTIONS THIS SEASON" />
        </div>
      </ScreenHeader>

      {tab === 'meetings' && (
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div className="pb-scroll" style={{ width: 290, flex: '0 0 290px', borderRight: `1px solid ${C.hair}`, overflowY: 'auto', padding: 14 }}>
            <div style={cap}>MEETINGS</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {MEETINGS.map(m => {
                const s = CTE_STATUS[m.status]
                return (
                  <div key={m.id} onClick={() => patch({ cteMeeting: m.id })}
                    style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '11px 12px', borderRadius: 8, cursor: 'pointer', border: m.id === sel.id ? '1px solid rgba(99,102,241,0.4)' : `1px solid ${C.hair}`, background: m.id === sel.id ? 'rgba(99,102,241,0.08)' : C.surface }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0 }}>{m.title}</span>
                      <span style={chip(s.fg)}>{s.label}</span>
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{m.kind} · {m.date}</div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <h2 style={{ fontWeight: 700, fontSize: 21, margin: 0, letterSpacing: '-0.01em' }}>{sel.title}</h2>
              <span style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.1em', padding: '3px 7px', borderRadius: 4, border: `1px solid ${CTE_STATUS[sel.status].fg}66`, color: CTE_STATUS[sel.status].fg }}>{CTE_STATUS[sel.status].label}</span>
            </div>
            <div style={{ fontFamily: MONO, fontSize: 11, color: C.faint, margin: '5px 0 22px' }}>{sel.kind} · {sel.date} · {sel.agenda.reduce((a, i) => a + i.mins, 0)} min agenda</div>

            <div style={cap}>AGENDA</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 24 }}>
              {sel.agenda.map((i, idx) => (
                <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 11, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 13px' }}>
                  <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, flexShrink: 0, width: 12 }}>{idx + 1}</span>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 13.5, color: C.text }}>{i.item}</div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{i.who} · {i.mins} min</div>
                  </div>
                  {i.task && <span onClick={() => patch({ task: i.task })} style={{ fontFamily: MONO, fontSize: 9, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: '1px solid rgba(99,102,241,0.4)', color: C.accent, cursor: 'pointer', flexShrink: 0 }}>DIARY TASK →</span>}
                </div>
              ))}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '22px 28px' }}>
              <div>
                <div style={cap}>PRESENT</div>
                <div style={{ fontSize: 13, color: C.dim, lineHeight: 1.55 }}>{sel.present.length ? sel.present.join(', ') : 'Attendance recorded on the night.'}</div>
                <div style={{ ...cap, margin: '16px 0 7px' }}>APOLOGIES</div>
                <div style={{ fontSize: 13, color: C.dim, lineHeight: 1.55 }}>{sel.apologies.length ? sel.apologies.join(', ') : 'None'}</div>
              </div>
              <div>
                <div style={cap}>MOTIONS</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {sel.motions.map((mo, i) => (
                    <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 13px' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
                        <span style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 0, lineHeight: 1.45 }}>{mo.title}</span>
                        <span style={motionChip(mo.outcome)}>{mo.outcome.toUpperCase()}</span>
                      </div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 5 }}>Moved {mo.mover}, seconded {mo.seconder} · {mo.tally}</div>
                    </div>
                  ))}
                  {sel.motions.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No motions recorded yet.</div>}
                </div>
              </div>
            </div>

            <div style={{ ...cap, margin: '24px 0 9px' }}>ACTION ITEMS</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {sel.actions.map((a, i) => (
                <div key={i} onClick={goPerson(a.who)} style={{ display: 'flex', alignItems: 'center', gap: 11, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 13px', cursor: 'pointer' }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 13.5, color: C.text }}>{a.what}</div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{a.who} · due {a.due}</div>
                  </div>
                  <span style={chip(ACTION_STATE[a.state].fg)}>{ACTION_STATE[a.state].label}</span>
                </div>
              ))}
              {sel.actions.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No actions carried out of this meeting.</div>}
            </div>
          </div>
        </div>
      )}

      {tab === 'positions' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '56rem' }}>
          {vacancies.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '10px 12px', borderRadius: 8, background: 'rgba(245,181,66,0.07)', border: '1px solid rgba(245,181,66,0.25)', fontSize: 12.5, color: C.warn, lineHeight: 1.45, marginBottom: 14 }}>
              <span style={{ flexShrink: 0 }}>⚠</span>
              <span>{vacancies.length} position{vacancies.length === 1 ? '' : 's'} unfilled — {vacancies.map(v => v.title).join(' and ')}. Both carry diary tasks with nobody to substitute in.</span>
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {POSITIONS.map((p, i) => (
              <div key={i} onClick={p.holder ? goPerson(p.holder) : undefined}
                style={{ display: 'flex', alignItems: 'center', gap: 12, background: C.surface, border: `1px solid ${p.holder ? C.hair : 'rgba(245,181,66,0.35)'}`, borderRadius: 8, padding: '11px 13px', cursor: p.holder ? 'pointer' : 'default' }}>
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 13, color: C.dim }}>{p.title}</span>
                    {p.exec && <span style={{ fontFamily: MONO, fontSize: 8.5, letterSpacing: '0.1em', padding: '2px 6px', borderRadius: 4, background: 'rgba(99,102,241,0.15)', color: C.accent, flexShrink: 0 }}>EXEC</span>}
                  </div>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: p.holder ? C.text : C.warn }}>{p.holder || 'Vacant'}</div>
                </div>
                <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, flexShrink: 0 }}>{p.term}</span>
                {p.holder && <span style={{ color: C.faintest, fontSize: 13, flexShrink: 0 }}>→</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'motions' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28, maxWidth: '76rem' }}>
            <div>
              <div style={cap}>MOTION REGISTER</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {allMotions.map((mo, i) => (
                  <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
                      <span style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 0, lineHeight: 1.45 }}>{mo.title}</span>
                      <span style={motionChip(mo.outcome)}>{mo.outcome.toUpperCase()}</span>
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 5 }}>{mo.from} · moved {mo.mover}, seconded {mo.seconder} · {mo.tally}</div>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div style={cap}>OPEN ACTIONS ACROSS ALL MEETINGS</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {openActions.map((a, i) => (
                  <div key={i} onClick={goPerson(a.who)} style={{ display: 'flex', alignItems: 'center', gap: 11, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px', cursor: 'pointer' }}>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13, color: C.text, lineHeight: 1.4 }}>{a.what}</div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 3 }}>{a.who} · due {a.due} · from {a.from}</div>
                    </div>
                    <span style={chip(ACTION_STATE[a.state].fg)}>{ACTION_STATE[a.state].label}</span>
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
