import { useState, useEffect } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, StatReadout } from '../ui'

// Committee — positions, meetings (agenda / attendance / motions) and the
// club's committee tasks (the closest thing to action items), all on real data.
// Member IDs on agenda/motions/tasks resolve to names via the club member list.

function fmtDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.getDate() + ' ' + ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][d.getMonth()] + ' ' + d.getFullYear()
}
const isToday = (iso) => iso && new Date(iso).toDateString() === new Date().toDateString()

function meetingStatus(m) {
  if (isToday(m.scheduled_at)) return { label: 'TODAY', fg: '#6366F1' }
  const s = (m.status || '').toLowerCase()
  if (s.includes('complet') || s.includes('held') || s.includes('approv') || s.includes('minutes')) return { label: (m.status || 'COMPLETED').toUpperCase().replace(/_/g, ' '), fg: '#16c784' }
  if (m.scheduled_at && new Date(m.scheduled_at) > new Date()) return { label: 'SCHEDULED', fg: '#8a90a2' }
  return { label: (m.status || 'DRAFT').toUpperCase().replace(/_/g, ' '), fg: '#8a90a2' }
}
function taskState(t) {
  const s = (t.status || '').toLowerCase()
  if (s.includes('done') || s.includes('complet')) return { label: 'DONE', fg: '#16c784' }
  if (t.due_date && new Date(t.due_date) < new Date()) return { label: 'OVERDUE', fg: '#ef5b5b' }
  return { label: (t.status || 'OPEN').toUpperCase().replace(/_/g, ' '), fg: '#6366F1' }
}
function motionOutcome(o) {
  const s = (o || '').toLowerCase()
  const lost = s.includes('lost') || s.includes('fail') || s.includes('reject')
  return { label: (o || 'RECORDED').toUpperCase(), fg: lost ? '#ef5b5b' : '#16c784' }
}

export default function Committee({ st, patch, narrow }) {
  const tab = st.cteTab || 'meetings'
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        const [posRes, meetList, tasksRes, membersRes] = await Promise.all([
          api.committeePositionsCurrent().catch(() => ({ positions: [] })),
          api.committeeListMeetings().catch(() => []),
          api.committeeListTasks().catch(() => []),
          api.feeAllMembers().catch(() => ({ members: [] })),
        ])
        const meetingsLite = Array.isArray(meetList) ? meetList : (meetList?.meetings || [])
        // pull full detail (agenda/attendance/motions) for each meeting — few per season
        const meetings = await Promise.all(meetingsLite.map(m => api.committeeGetMeeting(m.id).catch(() => ({ ...m, agenda_items: [], motions: [], attendance: [] }))))
        if (!alive) return
        const nameById = {}
        ;(membersRes?.members || membersRes || []).forEach(m => { nameById[m.member_id] = m.full_name })
        setData({
          positions: posRes?.positions || [],
          meetings: meetings.sort((a, b) => new Date(b.scheduled_at || 0) - new Date(a.scheduled_at || 0)),
          tasks: Array.isArray(tasksRes) ? tasksRes : (tasksRes?.tasks || []),
          nameById,
        })
      } catch (e) { if (alive) setErr(String(e?.message || e)) }
    })()
    return () => { alive = false }
  }, [])

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }
  const chip = (fg, fs = 8.5) => ({ fontFamily: MONO, fontSize: fs, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${fg}66`, color: fg, flexShrink: 0 })

  const Header = ({ children }) => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Committee</h1>
        <Caption tone={C.faint} style={{ marginTop: 2 }}>Positions, meetings, motions and actions</Caption>
      </div>
      <SegTabs value={tab} onChange={k => patch({ cteTab: k })} tabs={[{ key: 'meetings', label: 'Meetings' }, { key: 'positions', label: 'Positions' }, { key: 'motions', label: 'Motions & actions' }]} />
      {children}
    </ScreenHeader>
  )

  if (!data) {
    return <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}><Header /><div style={{ padding: 24, fontSize: 13, color: C.faint }}>{err ? 'Could not load committee data.' : 'Loading committee…'}</div></div>
  }

  const { positions, meetings, tasks, nameById } = data
  const name = (id) => (id && nameById[id]) || 'Unknown'
  const vacancies = positions.filter(p => !p.current_term)
  const openTasks = tasks.filter(t => taskState(t).label !== 'DONE')
  const allMotions = []
  meetings.forEach(m => (m.motions || []).forEach(mo => allMotions.push({ ...mo, from: (m.meeting_type || 'Meeting') + ' · ' + fmtDate(m.scheduled_at) })))

  const sel = meetings.find(m => m.id === st.cteMeeting) || meetings[0] || null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <Header>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginLeft: 'auto', flexWrap: 'wrap' }}>
          <StatReadout value={(positions.length - vacancies.length) + '/' + positions.length} label="POSITIONS FILLED" fg={vacancies.length ? C.warn : C.ok} />
          <StatReadout value={String(openTasks.length)} label="OPEN ACTIONS" fg={openTasks.some(t => taskState(t).label === 'OVERDUE') ? C.block : C.text} />
          <StatReadout value={String(allMotions.length)} label="MOTIONS THIS SEASON" />
        </div>
      </Header>

      {tab === 'meetings' && (
        <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>
          <div className="pb-scroll" style={{ width: 290, flex: '0 0 290px', borderRight: `1px solid ${C.hair}`, overflowY: 'auto', padding: 14 }}>
            <div style={cap}>MEETINGS</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {meetings.map(m => {
                const s = meetingStatus(m)
                return (
                  <div key={m.id} onClick={() => patch({ cteMeeting: m.id })}
                    style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '11px 12px', borderRadius: 8, cursor: 'pointer', border: sel && m.id === sel.id ? '1px solid rgba(99,102,241,0.4)' : `1px solid ${C.hair}`, background: sel && m.id === sel.id ? 'rgba(99,102,241,0.08)' : C.surface }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 13.5, fontWeight: 600, color: C.text, flex: 1, minWidth: 0 }}>{m.title}</span>
                      <span style={chip(s.fg)}>{s.label}</span>
                    </div>
                    <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint }}>{(m.meeting_type || 'Meeting')} · {fmtDate(m.scheduled_at)}</div>
                  </div>
                )
              })}
              {meetings.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No meetings recorded yet.</div>}
            </div>
          </div>

          {sel && (
            <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <h2 style={{ fontWeight: 700, fontSize: 21, margin: 0, letterSpacing: '-0.01em' }}>{sel.title}</h2>
                <span style={{ ...chip(meetingStatus(sel).fg, 9), padding: '3px 7px' }}>{meetingStatus(sel).label}</span>
              </div>
              <div style={{ fontFamily: MONO, fontSize: 11, color: C.faint, margin: '5px 0 22px' }}>{(sel.meeting_type || 'Meeting')} · {fmtDate(sel.scheduled_at)}{sel.location ? ' · ' + sel.location : ''}</div>

              <div style={cap}>AGENDA</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 24 }}>
                {(sel.agenda_items || []).map((i, idx) => (
                  <div key={i.id} style={{ display: 'flex', alignItems: 'center', gap: 11, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 13px' }}>
                    <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, flexShrink: 0, width: 12 }}>{i.position ?? idx + 1}</span>
                    <div style={{ minWidth: 0, flex: 1 }}>
                      <div style={{ fontSize: 13.5, color: C.text }}>{i.title}</div>
                      {(i.proposed_by_member_id || i.description) && <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>{i.proposed_by_member_id ? name(i.proposed_by_member_id) : i.description}</div>}
                    </div>
                  </div>
                ))}
                {(sel.agenda_items || []).length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No agenda items.</div>}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '22px 28px' }}>
                <div>
                  <div style={cap}>PRESENT</div>
                  <div style={{ fontSize: 13, color: C.dim, lineHeight: 1.55 }}>{(sel.attendance || []).filter(a => (a.status || '').toLowerCase().includes('present')).map(a => a.full_name).join(', ') || 'Attendance recorded on the night.'}</div>
                  <div style={{ ...cap, margin: '16px 0 7px' }}>APOLOGIES</div>
                  <div style={{ fontSize: 13, color: C.dim, lineHeight: 1.55 }}>{(sel.attendance || []).filter(a => (a.status || '').toLowerCase().includes('apolog')).map(a => a.full_name).join(', ') || 'None'}</div>
                </div>
                <div>
                  <div style={cap}>MOTIONS</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                    {(sel.motions || []).map(mo => {
                      const oc = motionOutcome(mo.outcome)
                      const tally = [mo.votes_for != null ? mo.votes_for + ' for' : null, mo.votes_against ? mo.votes_against + ' against' : null, mo.votes_abstain ? mo.votes_abstain + ' abstain' : null].filter(Boolean).join(', ')
                      return (
                        <div key={mo.id} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '10px 13px' }}>
                          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
                            <span style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 0, lineHeight: 1.45 }}>{mo.description}</span>
                            <span style={chip(oc.fg)}>{oc.label}</span>
                          </div>
                          <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 5 }}>{mo.proposed_by_member_id ? 'Moved ' + name(mo.proposed_by_member_id) : ''}{mo.seconded_by_member_id ? ', seconded ' + name(mo.seconded_by_member_id) : ''}{tally ? ' · ' + tally : ''}</div>
                        </div>
                      )
                    })}
                    {(sel.motions || []).length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No motions recorded.</div>}
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === 'positions' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20, maxWidth: '56rem' }}>
          {vacancies.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '10px 12px', borderRadius: 8, background: 'rgba(245,181,66,0.07)', border: '1px solid rgba(245,181,66,0.25)', fontSize: 12.5, color: C.warn, lineHeight: 1.45, marginBottom: 14 }}>
              <span style={{ flexShrink: 0 }}>⚠</span>
              <span>{vacancies.length} position{vacancies.length === 1 ? '' : 's'} unfilled — {vacancies.map(v => v.name).join(', ')}.</span>
            </div>
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {positions.map(p => {
              const t = p.current_term
              return (
                <div key={p.id} style={{ display: 'flex', alignItems: 'center', gap: 12, background: C.surface, border: `1px solid ${t ? C.hair : 'rgba(245,181,66,0.35)'}`, borderRadius: 8, padding: '11px 13px' }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 13, color: C.dim }}>{p.name}</div>
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: t ? C.text : C.warn }}>{t ? t.holder_name : 'Vacant'}</div>
                  </div>
                  {t?.started_at && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, flexShrink: 0 }}>since {fmtDate(t.started_at)}</span>}
                </div>
              )
            })}
            {positions.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No committee positions set up yet.</div>}
          </div>
        </div>
      )}

      {tab === 'motions' && (
        <div className="pb-scroll" style={{ flex: 1, overflowY: 'auto', padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 28, maxWidth: '76rem' }}>
            <div>
              <div style={cap}>MOTION REGISTER</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {allMotions.map((mo, i) => {
                  const oc = motionOutcome(mo.outcome)
                  return (
                    <div key={i} style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
                        <span style={{ fontSize: 13, color: C.text, flex: 1, minWidth: 0, lineHeight: 1.45 }}>{mo.description}</span>
                        <span style={chip(oc.fg)}>{oc.label}</span>
                      </div>
                      <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 5 }}>{mo.from}{mo.proposed_by_member_id ? ' · moved ' + name(mo.proposed_by_member_id) : ''}</div>
                    </div>
                  )
                })}
                {allMotions.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No motions recorded this season.</div>}
              </div>
            </div>
            <div>
              <div style={cap}>OPEN COMMITTEE ACTIONS</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {openTasks.map(t => {
                  const s = taskState(t)
                  return (
                    <div key={t.id} style={{ display: 'flex', alignItems: 'center', gap: 11, background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8, padding: '11px 13px' }}>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 13, color: C.text, lineHeight: 1.4 }}>{t.title}</div>
                        <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 3 }}>{t.assigned_to_member_id ? name(t.assigned_to_member_id) : 'Unassigned'}{t.due_date ? ' · due ' + fmtDate(t.due_date) : ''}</div>
                      </div>
                      <span style={chip(s.fg)}>{s.label}</span>
                    </div>
                  )
                })}
                {openTasks.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No open committee actions.</div>}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
