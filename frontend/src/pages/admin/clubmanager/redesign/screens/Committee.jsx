import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../../../lib/api'
import { C, MONO, Caption, ScreenHeader, NavToggle, SegTabs, StatReadout , ManageLink } from '../ui'
import { MeetingRoomPanel } from '../../../MeetingRoom'

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
  if (isToday(m.scheduled_at)) return { label: 'TODAY', fg: 'var(--pb-accent)' }
  const s = (m.status || '').toLowerCase()
  if (s.includes('complet') || s.includes('held') || s.includes('approv') || s.includes('minutes')) return { label: (m.status || 'COMPLETED').toUpperCase().replace(/_/g, ' '), fg: '#16c784' }
  if (m.scheduled_at && new Date(m.scheduled_at) > new Date()) return { label: 'SCHEDULED', fg: '#8a90a2' }
  return { label: (m.status || 'DRAFT').toUpperCase().replace(/_/g, ' '), fg: '#8a90a2' }
}
function taskState(t) {
  const s = (t.status || '').toLowerCase()
  if (s.includes('done') || s.includes('complet')) return { label: 'DONE', fg: '#16c784' }
  if (t.due_date && new Date(t.due_date) < new Date()) return { label: 'OVERDUE', fg: '#ef5b5b' }
  return { label: (t.status || 'OPEN').toUpperCase().replace(/_/g, ' '), fg: 'var(--pb-accent)' }
}
function motionOutcome(o) {
  const s = (o || '').toLowerCase()
  const lost = s.includes('lost') || s.includes('fail') || s.includes('reject')
  return { label: (o || 'RECORDED').toUpperCase(), fg: lost ? '#ef5b5b' : '#16c784' }
}


// An agenda item, with what it produced folded away underneath it.
//
// Collapsed, the summary answers "did anything come of this?" without a click:
// how many motions and how they went, how many actions and how many are still
// open, and whether anything was minuted against it. Expanded, it shows the
// actual motions, actions and note. Items that produced nothing stay a plain
// row with nothing to open, because a disclosure arrow that reveals "nothing"
// is a small lie.
function AgendaRow({ item, idx, name, motions, actions, open, onToggle }) {
  const carried = motions.filter(m => (m.outcome || '').toLowerCase() === 'carried').length
  const openActions = actions.filter(t => !['done', 'completed', 'cancelled'].includes((t.status || '').toLowerCase())).length
  const note = (item.outcome_notes || '').trim()
  const bits = []
  if (motions.length) bits.push(`${motions.length} motion${motions.length === 1 ? '' : 's'}${carried ? ` · ${carried} carried` : ''}`)
  if (actions.length) bits.push(`${actions.length} action${actions.length === 1 ? '' : 's'}${openActions ? ` · ${openActions} open` : ''}`)
  if (note) bits.push('minuted')
  const has = motions.length > 0 || actions.length > 0 || !!note

  const sub = item.proposed_by_member_id ? name(item.proposed_by_member_id) : item.description

  return (
    <div style={{ background: C.surface, border: `1px solid ${C.hair}`, borderRadius: 8 }}>
      <div onClick={has ? onToggle : undefined}
        style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '10px 13px', cursor: has ? 'pointer' : 'default' }}>
        <span style={{ fontFamily: MONO, fontSize: 10, color: C.faintest, flexShrink: 0, width: 12 }}>{item.position ?? idx + 1}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 13.5, color: C.text }}>{item.title}</div>
          {(sub || bits.length > 0) && (
            <div style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginTop: 2 }}>
              {[sub, ...bits].filter(Boolean).join(' · ')}
            </div>
          )}
        </div>
        {has && (
          <span style={{ fontFamily: MONO, fontSize: 10, color: C.faint, flexShrink: 0 }}>{open ? '▾' : '▸'}</span>
        )}
      </div>

      {has && open && (
        <div style={{ borderTop: `1px solid ${C.hair}`, padding: '10px 13px 12px 36px', display: 'flex', flexDirection: 'column', gap: 12 }}>
          {motions.length > 0 && (
            <div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, marginBottom: 5 }}>MOTIONS</div>
              {motions.map(mo => (
                <div key={mo.id} style={{ fontSize: 12.5, color: C.dim, marginBottom: 4 }}>
                  {mo.description}
                  <span style={{ fontFamily: MONO, fontSize: 9.5, marginLeft: 7, color: outcomeTone(mo.outcome) }}>
                    {(mo.outcome || 'pending').toUpperCase()}
                  </span>
                  {(mo.votes_for != null || mo.votes_against != null) && (
                    <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginLeft: 6 }}>
                      {mo.votes_for || 0} for · {mo.votes_against || 0} against{mo.votes_abstain ? ` · ${mo.votes_abstain} abstain` : ''}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
          {actions.length > 0 && (
            <div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, marginBottom: 5 }}>ACTIONS</div>
              {actions.map(t => (
                <div key={t.id} style={{ fontSize: 12.5, color: C.dim, marginBottom: 4 }}>
                  {t.title}
                  <span style={{ fontFamily: MONO, fontSize: 9.5, marginLeft: 7, color: outcomeTone(t.status) }}>
                    {(t.status || 'todo').replace('_', ' ').toUpperCase()}
                  </span>
                  {t.due_date && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginLeft: 6 }}>due {t.due_date}</span>}
                  {t.assigned_to_member_id && <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, marginLeft: 6 }}>{name(t.assigned_to_member_id)}</span>}
                </div>
              ))}
            </div>
          )}
          {note && (
            <div>
              <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.14em', color: C.faintest, marginBottom: 5 }}>NOTES</div>
              <div style={{ fontSize: 12.5, color: C.dim, whiteSpace: 'pre-wrap', lineHeight: 1.6 }}>{note}</div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Carried and done read green, lost and blocked red, everything mid-flight amber.
function outcomeTone(v) {
  const k = (v || '').toLowerCase()
  if (['carried', 'done', 'completed'].includes(k)) return 'var(--pb-positive-ink)'
  if (['lost', 'blocked', 'withdrawn'].includes(k)) return 'var(--pb-red-ink)'
  return C.warn
}


export default function Committee({ st, patch, narrow }) {
  const tab = st.cteTab || 'meetings'
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [dragId, setDragId] = useState(null)
  const [overId, setOverId] = useState(null)
  // Which agenda items are open. Keyed by item id and kept per meeting view, so
  // opening one item does not collapse the rest.
  const [expanded, setExpanded] = useState({})

  // Reorder a position before another and persist the new sequence.
  const movePosition = (fromId, toId) => {
    setDragId(null); setOverId(null)
    if (!fromId || fromId === toId) return
    setData(d => {
      const arr = [...d.positions]
      const fi = arr.findIndex(p => p.id === fromId)
      const ti = arr.findIndex(p => p.id === toId)
      if (fi < 0 || ti < 0) return d
      const [moved] = arr.splice(fi, 1)
      arr.splice(ti, 0, moved)
      api.committeeReorderPositions(arr.map(p => p.id)).catch(() => {})
      return { ...d, positions: arr }
    })
  }

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

  // Coming out of the meeting room, pull that one meeting's record again so the
  // summary beside the list shows what was just minuted. One fetch, on the way
  // out — the room reloads itself after every edit while it is open.
  const refreshMeeting = useCallback(async (id) => {
    try {
      const fresh = await api.committeeGetMeeting(id)
      setData(d => (d ? { ...d, meetings: d.meetings.map(m => (m.id === id ? { ...m, ...fresh } : m)) } : d))
    } catch { /* the room reports its own failures */ }
  }, [])

  // While the room is open it hands back the meeting record on every load, so
  // the card's status pill follows a change made in the room straight away.
  const onRoomMeta = useCallback((meta) => {
    const m = meta?.meeting
    if (!m) return
    setData(d => (d ? {
      ...d,
      meetings: d.meetings.map(x => (x.id === m.id
        ? { ...x, title: m.title, status: m.status, scheduled_at: m.scheduled_at, location: m.location }
        : x)),
    } : d))
  }, [])

  const cap = { fontFamily: MONO, fontSize: 10, letterSpacing: '0.14em', color: C.faintest, marginBottom: 9 }
  const chip = (fg, fs = 8.5) => ({ fontFamily: MONO, fontSize: fs, letterSpacing: '0.08em', padding: '2px 6px', borderRadius: 4, border: `1px solid ${fg}66`, color: fg, flexShrink: 0 })
  // The OPEN pill is a button, and its colour is the club's accent rather than
  // a hex — so it can't take `chip`'s `${fg}66` edge (a var() with 66 stuck on
  // the end is not a colour and the border silently vanishes). color-mix is how
  // the rest of this screen tints the accent, and --pb-accent-ink is the accent
  // as text, which stays legible on a light theme.
  const openChip = (active, fs = 8.5) => ({
    ...chip(C.accent, fs),
    color: 'var(--pb-accent-ink)',
    border: `1px solid color-mix(in srgb, var(--pb-accent) ${active ? 55 : 38}%, transparent)`,
    background: active ? 'color-mix(in srgb, var(--pb-accent) 18%, transparent)' : 'transparent',
    cursor: 'pointer',
  })

  const Header = ({ children }) => (
    <ScreenHeader>
      <NavToggle narrow={narrow} onClick={() => patch({ navOpen: true })} />
      <div>
        <h1 style={{ fontWeight: 700, fontSize: 19, margin: 0, letterSpacing: '-0.01em' }}>Committee</h1>
        <Caption tone={C.faint} style={{ marginTop: 2 }}>Positions, meetings, motions and actions</Caption>
      </div>
      <SegTabs value={tab} onChange={k => patch({ cteTab: k })} tabs={[{ key: 'meetings', label: 'Meetings' }, { key: 'positions', label: 'Positions' }, { key: 'motions', label: 'Motions & actions' }]} />
      <ManageLink to="/admin/clubhouse/committee/manage">Manage meetings &amp; positions</ManageLink>
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
  // The room is only ever open on the meeting that is selected, so the card the
  // list highlights and the pane beside it can never disagree.
  const room = sel && st.cteRoom === sel.id ? sel.id : null
  const openRoom = (id) => patch({ cteMeeting: id, cteRoom: id })
  const closeRoom = () => { if (room) refreshMeeting(room); patch({ cteRoom: null }) }

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
                  <div key={m.id} onClick={() => patch({ cteMeeting: m.id, cteRoom: null })}
                    style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '11px 12px', borderRadius: 8, cursor: 'pointer', border: sel && m.id === sel.id ? '1px solid color-mix(in srgb, var(--pb-accent) 40%, transparent)' : `1px solid ${C.hair}`, background: sel && m.id === sel.id ? 'color-mix(in srgb, var(--pb-accent) 8%, transparent)' : C.surface }}>
                    {/* The title gets the full width of a 290px rail; the two
                        pills sit on the meta line under it rather than
                        squeezing it into three wrapped lines. */}
                    <div style={{ fontSize: 13.5, fontWeight: 600, color: C.text }}>{m.title}</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ fontFamily: MONO, fontSize: 9.5, color: C.faint, flex: 1, minWidth: 0 }}>
                        {(m.meeting_type || 'Meeting')} · {fmtDate(m.scheduled_at)}
                      </span>
                      {/* Opens the meeting room in the pane beside the list, so
                          the night is minuted here rather than on a page of its
                          own with the other meetings out of sight. */}
                      <button onClick={e => { e.stopPropagation(); openRoom(m.id) }}
                        title="Open the meeting room and record this meeting"
                        style={openChip(room === m.id)}>
                        OPEN
                      </button>
                      <span style={chip(s.fg)}>{s.label}</span>
                    </div>
                  </div>
                )
              })}
              {meetings.length === 0 && <div style={{ fontSize: 13, color: C.faint }}>No meetings recorded yet.</div>}
            </div>
          </div>

          {sel && room && (
            <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
              {/* Keyed on the meeting, so switching rooms starts a clean one
                  rather than showing the last one's agenda while it loads. */}
              <MeetingRoomPanel key={room} meetingId={room} inlineHeader
                onMeta={onRoomMeta} onExit={closeRoom} />
            </div>
          )}

          {sel && !room && (
            <div className="pb-scroll" style={{ flex: 1, minWidth: 0, overflowY: 'auto', padding: '22px 24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                <h2 style={{ fontWeight: 700, fontSize: 21, margin: 0, letterSpacing: '-0.01em' }}>{sel.title}</h2>
                <span style={{ ...chip(meetingStatus(sel).fg, 9), padding: '3px 7px' }}>{meetingStatus(sel).label}</span>
                <button onClick={() => openRoom(sel.id)}
                  title="Open the meeting room and record this meeting"
                  style={{ ...openChip(false, 9), padding: '3px 7px' }}>
                  OPEN
                </button>
              </div>
              <div style={{ fontFamily: MONO, fontSize: 11, color: C.faint, margin: '5px 0 22px' }}>{(sel.meeting_type || 'Meeting')} · {fmtDate(sel.scheduled_at)}{sel.location ? ' · ' + sel.location : ''}</div>

              <div style={cap}>AGENDA</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5, marginBottom: 24 }}>
                {(sel.agenda_items || []).map((i, idx) => (
                  <AgendaRow key={i.id} item={i} idx={idx} name={name}
                    motions={(sel.motions || []).filter(mo => mo.agenda_item_id === i.id)}
                    actions={(sel.actions || []).filter(t => t.agenda_item_id === i.id)}
                    open={!!expanded[i.id]}
                    onToggle={() => setExpanded(e => ({ ...e, [i.id]: !e[i.id] }))} />
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
          <div style={{ fontFamily: MONO, fontSize: 9.5, letterSpacing: '0.08em', color: C.faintest, marginBottom: 8 }}>DRAG THE GRIP TO REORDER</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {positions.map(p => {
              const t = p.current_term
              const dragging = dragId === p.id
              const isOver = overId === p.id && dragId && dragId !== p.id
              return (
                <div key={p.id}
                  onDragOver={e => { if (dragId) { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; if (overId !== p.id) setOverId(p.id) } }}
                  onDrop={e => { e.preventDefault(); movePosition(dragId, p.id) }}
                  style={{ display: 'flex', alignItems: 'center', gap: 10, background: C.surface, borderRadius: 8, padding: '11px 13px',
                    border: `1px solid ${isOver ? C.accent : (t ? C.hair : 'rgba(245,181,66,0.35)')}`,
                    boxShadow: isOver ? 'inset 0 2px 0 var(--pb-accent)' : undefined, opacity: dragging ? 0.5 : 1 }}>
                  <span draggable
                    onDragStart={e => { e.dataTransfer.effectAllowed = 'move'; setDragId(p.id) }}
                    onDragEnd={() => { setDragId(null); setOverId(null) }}
                    title="Drag to reorder"
                    style={{ cursor: 'grab', color: C.faint, fontSize: 15, lineHeight: 1, padding: '0 2px', flexShrink: 0, userSelect: 'none' }}>⠿</span>
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
