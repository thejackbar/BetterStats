import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubhouseLayout from '../../components/admin/BetterClubhouseLayout'
import { PbSpinner } from '../../lib/presskit'

// The meeting room — one screen a secretary runs a meeting from.
//
// The tabbed Committee screen is a set of lists: meetings here, motions there,
// actions somewhere else. That is fine for looking things up afterwards and
// useless at 8pm on a Tuesday, when the agenda is moving and everything raised
// belongs to whatever is being discussed right now.
//
// So this is arranged the way a meeting runs. The agenda is the spine. You work
// down it, and the motions, actions and outcomes you record attach to the item
// you are on. Attendance is set once at the top and then decides who can vote,
// because the people who can vote are the people in the room.
//
// Everything saves as you go — there is no Save button for the meeting as a
// whole, since a secretary should never lose twenty minutes to a closed laptop.

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const cap = 'font-mono text-[10px] tracking-wide3 text-pb-faintest'
const btn = 'px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-40 whitespace-nowrap'
const btnAccent = 'px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap'

const AGENDA_STATUSES = ['proposed', 'discussed', 'carried', 'deferred', 'withdrawn']
const MOTION_OUTCOMES = ['pending', 'carried', 'lost', 'withdrawn']
const ATTEND = [['present', 'Present'], ['apology', 'Apology'], ['absent', 'Absent']]
const VOTES = [['for', 'For'], ['against', 'Against'], ['abstain', 'Abstain']]
const titleCase = s => (s || '').split('_').map(w => w[0]?.toUpperCase() + w.slice(1)).join(' ')

// A debounced writer for the free-text fields. Typing minutes should not be one
// request per keystroke, and it should not need a button either.
function useAutosave(save, delay = 700) {
  const timer = useRef(null)
  const latest = useRef(save)
  latest.current = save
  useEffect(() => () => clearTimeout(timer.current), [])
  return useCallback((...args) => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => latest.current(...args), delay)
  }, [delay])
}

/* ── Attendance ─────────────────────────────────────────────────────────── */

function Attendance({ pool, attendance, onChange }) {
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)
  const byId = useMemo(() => {
    const m = {}
    attendance.forEach(a => { m[a.member_id] = a.status })
    return m
  }, [attendance])

  // Committee members are shown by default. Everyone else appears once you
  // type — a club with 300 members should never be scrolled to tick six.
  const q = query.trim().toLowerCase()
  const shown = pool.filter(p => {
    if (q) return p.full_name.toLowerCase().includes(q)
    if (showAll) return true
    return p.on_committee || byId[p.member_id]
  })
  const present = attendance.filter(a => a.status === 'present').length

  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
        <div className={cap}>WHO IS HERE</div>
        <div className="font-mono text-[10px] text-pb-faint">
          {present} present · {attendance.filter(a => a.status === 'apology').length} apologies
        </div>
      </div>
      <input className={`${inp} mb-2`} placeholder="Search anyone in the club…"
        value={query} onChange={e => setQuery(e.target.value)} />
      <div className="space-y-1 max-h-[260px] overflow-y-auto pb-scroll">
        {shown.length === 0 && (
          <div className="font-mono text-[10px] text-pb-faintest py-2">No one matches that.</div>
        )}
        {shown.map(p => (
          <div key={p.member_id} className="flex items-center justify-between gap-2">
            <span className="text-[12.5px] text-pb-text truncate">
              {p.full_name}
              {p.on_committee && <span className="font-mono text-[9px] text-pb-faintest ml-1.5">COMMITTEE</span>}
            </span>
            <div className="flex gap-1 shrink-0">
              {ATTEND.map(([v, l]) => (
                <button key={v} onClick={() => onChange(p.member_id, byId[p.member_id] === v ? null : v)}
                  className={`px-2 py-1 rounded font-mono text-[9px] border ${byId[p.member_id] === v
                    ? 'text-pb-bg border-transparent' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
                  style={byId[p.member_id] === v ? { background: 'var(--pb-accent)' } : undefined}>{l}</button>
              ))}
            </div>
          </div>
        ))}
      </div>
      {!q && (
        <button onClick={() => setShowAll(x => !x)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text mt-2">
          {showAll ? 'Show the committee only' : `Show all ${pool.length} members`}
        </button>
      )}
    </div>
  )
}

/* ── Actions raised in the meeting ──────────────────────────────────────── */

function ActionForm({ agendaItemId, motionId, present, onSave, onCancel }) {
  const [form, setForm] = useState({ title: '', due_date: '', budget_estimate: '' })
  const [owners, setOwners] = useState([])
  const [busy, setBusy] = useState(false)

  const toggle = id => setOwners(o => o.includes(id) ? o.filter(x => x !== id) : [...o, id])

  async function submit() {
    if (!form.title.trim()) return
    setBusy(true)
    try {
      await onSave({
        title: form.title.trim(),
        due_date: form.due_date || null,
        budget_estimate: form.budget_estimate === '' ? null : Number(form.budget_estimate),
        agenda_item_id: agendaItemId || null,
        motion_id: motionId || null,
        assignee_member_ids: owners,
      })
      setForm({ title: '', due_date: '', budget_estimate: '' }); setOwners([])
    } finally { setBusy(false) }
  }

  return (
    <div className="border pb-hairline rounded p-2.5 mt-2 bg-pb-surface2/40">
      <input className={`${inp} mb-2`} placeholder="What was agreed?" autoFocus
        value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
      <div className="flex gap-2 mb-2 flex-wrap">
        <label className="flex-1 min-w-[8rem]">
          <div className={`${cap} mb-1`}>DUE</div>
          <input type="date" className={inp} value={form.due_date}
            onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
        </label>
        <label className="flex-1 min-w-[8rem]">
          <div className={`${cap} mb-1`}>BUDGET</div>
          <input type="number" step="0.01" className={inp} placeholder="0.00" value={form.budget_estimate}
            onChange={e => setForm(f => ({ ...f, budget_estimate: e.target.value }))} />
        </label>
      </div>
      <div className={`${cap} mb-1`}>WHO IS DOING IT</div>
      {present.length === 0 ? (
        <div className="font-mono text-[10px] text-pb-faintest mb-2">Mark someone present first.</div>
      ) : (
        <div className="flex flex-wrap gap-1 mb-2">
          {present.map(p => (
            <button key={p.member_id} onClick={() => toggle(p.member_id)}
              className={`px-2 py-1 rounded font-mono text-[9px] border ${owners.includes(p.member_id)
                ? 'text-pb-bg border-transparent' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
              style={owners.includes(p.member_id) ? { background: 'var(--pb-accent)' } : undefined}>
              {p.full_name}
            </button>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <button onClick={submit} disabled={busy || !form.title.trim()} className={btnAccent}
          style={{ background: 'var(--pb-accent)' }}>{busy ? 'SAVING…' : '+ ACTION'}</button>
        <button onClick={onCancel} className={btn}>Cancel</button>
      </div>
    </div>
  )
}

function ActionRow({ action, nameOf, onChange, onDelete }) {
  const owners = (action.assignee_member_ids || []).map(nameOf).filter(Boolean)
  return (
    <div className="flex items-start justify-between gap-2 border pb-hairline rounded px-2.5 py-2 bg-pb-surface2/30">
      <div className="min-w-0">
        <div className="text-[12.5px] text-pb-text">{action.title}</div>
        <div className="font-mono text-[9.5px] text-pb-faintest mt-0.5 flex flex-wrap gap-x-2">
          {owners.length > 0 && <span>{owners.join(', ')}</span>}
          {action.due_date && <span>due {action.due_date}</span>}
          {action.budget_estimate != null && <span>${Number(action.budget_estimate).toLocaleString('en-AU')}</span>}
          <span>{titleCase(action.status)}</span>
        </div>
      </div>
      <div className="flex gap-1 shrink-0">
        {action.status !== 'done' && (
          <button onClick={() => onChange({ status: 'done' })} className="font-mono text-[9px] text-pb-faint hover:text-pb-text">Done</button>
        )}
        <button onClick={onDelete} className="font-mono text-[9px] text-pb-faint hover:text-pb-red">✕</button>
      </div>
    </div>
  )
}

/* ── Motions ────────────────────────────────────────────────────────────── */

function Motion({ motion, present, nameOf, onChange, onDelete, onVotes, onAddAction, actions, onActionChange, onActionDelete }) {
  const [showVotes, setShowVotes] = useState(false)
  const [adding, setAdding] = useState(false)
  const votes = useMemo(() => {
    const m = {}
    ;(motion.votes || []).forEach(v => { m[v.member_id] = v.vote })
    return m
  }, [motion.votes])

  const setVote = (memberId, vote) => {
    const next = { ...votes }
    if (vote === null) delete next[memberId]
    else next[memberId] = vote
    onVotes(Object.entries(next).map(([member_id, v]) => ({ member_id, vote: v })))
  }

  return (
    <div className="border pb-hairline rounded p-2.5 bg-pb-surface2/30">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[12.5px] text-pb-text min-w-0">{motion.description}</div>
        <div className="flex items-center gap-1 shrink-0">
          <select value={motion.outcome} onChange={e => onChange({ outcome: e.target.value })}
            className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-1 font-mono text-[9px] text-pb-text">
            {MOTION_OUTCOMES.map(o => <option key={o} value={o}>{titleCase(o)}</option>)}
          </select>
          <button onClick={onDelete} className="font-mono text-[9px] text-pb-faint hover:text-pb-red">✕</button>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
        <button onClick={() => setShowVotes(v => !v)} className="font-mono text-[9px] text-pb-faint hover:text-pb-text">
          {showVotes ? 'Hide votes' : 'Record votes'}
        </button>
        <span className="font-mono text-[9px] text-pb-faintest">
          {motion.votes_for ?? 0} for · {motion.votes_against ?? 0} against · {motion.votes_abstain ?? 0} abstain
        </span>
        <button onClick={() => setAdding(a => !a)} className="font-mono text-[9px] text-pb-faint hover:text-pb-text">+ Action</button>
      </div>

      {showVotes && (
        <div className="mt-2 border-t pb-hairline pt-2">
          {present.length === 0 ? (
            <div className="font-mono text-[10px] text-pb-faintest">
              Only people marked present can vote. Set attendance first.
            </div>
          ) : (
            <div className="space-y-1 max-h-[220px] overflow-y-auto pb-scroll">
              {present.map(p => (
                <div key={p.member_id} className="flex items-center justify-between gap-2">
                  <span className="text-[12px] text-pb-dim truncate">{p.full_name}</span>
                  <div className="flex gap-1 shrink-0">
                    {VOTES.map(([v, l]) => (
                      <button key={v} onClick={() => setVote(p.member_id, votes[p.member_id] === v ? null : v)}
                        className={`px-2 py-0.5 rounded font-mono text-[9px] border ${votes[p.member_id] === v
                          ? 'text-pb-bg border-transparent' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
                        style={votes[p.member_id] === v ? { background: 'var(--pb-accent)' } : undefined}>{l}</button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
          <div className="font-mono text-[9px] text-pb-faintest mt-1.5">
            Recording names re-derives the tallies. Leave it empty and a counted show of hands stands.
          </div>
        </div>
      )}

      {adding && (
        <ActionForm motionId={motion.id} agendaItemId={motion.agenda_item_id} present={present}
          onSave={async d => { await onAddAction(d); setAdding(false) }} onCancel={() => setAdding(false)} />
      )}
      {actions.length > 0 && (
        <div className="mt-2 space-y-1">
          {actions.map(a => (
            <ActionRow key={a.id} action={a} nameOf={nameOf}
              onChange={p => onActionChange(a.id, p)} onDelete={() => onActionDelete(a.id)} />
          ))}
        </div>
      )}
    </div>
  )
}

/* ── One agenda item ────────────────────────────────────────────────────── */

function AgendaItem({
  item, index, isCurrent, onOpen, dragProps, present, nameOf,
  motions, actions, onItemChange, onItemDelete,
  onAddMotion, onMotionChange, onMotionDelete, onMotionVotes,
  onAddAction, onActionChange, onActionDelete,
}) {
  const [addingMotion, setAddingMotion] = useState('')
  const [addingAction, setAddingAction] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(item.title)
  const saveNotes = useAutosave(v => onItemChange({ outcome_notes: v }))

  return (
    <div className={`pb-card p-3 ${isCurrent ? 'ring-1' : ''}`}
      style={isCurrent ? { boxShadow: '0 0 0 1px var(--pb-accent)' } : undefined} {...dragProps}>
      <div className="flex items-start gap-2">
        <span className="cursor-grab active:cursor-grabbing text-pb-faintest select-none pt-0.5" title="Drag to reorder">⠿</span>
        <div className="flex-1 min-w-0">
          {editing ? (
            <div className="flex gap-2">
              <input className={inp} value={draft} autoFocus onChange={e => setDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') { onItemChange({ title: draft }); setEditing(false) } }} />
              <button onClick={() => { onItemChange({ title: draft }); setEditing(false) }} className={btn}>Save</button>
            </div>
          ) : (
            <button onClick={onOpen} className="text-left w-full">
              <span className="font-mono text-[10px] text-pb-faintest mr-2">{index + 1}</span>
              <span className="text-[13.5px] text-pb-text">{item.title}</span>
            </button>
          )}
        </div>
        <select value={item.status} onChange={e => onItemChange({ status: e.target.value })}
          className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-1 font-mono text-[9px] text-pb-text shrink-0">
          {AGENDA_STATUSES.map(o => <option key={o} value={o}>{titleCase(o)}</option>)}
        </select>
        <button onClick={() => { setDraft(item.title); setEditing(true) }}
          className="font-mono text-[9px] text-pb-faint hover:text-pb-text shrink-0">Edit</button>
        <button onClick={onItemDelete} className="font-mono text-[9px] text-pb-faint hover:text-pb-red shrink-0">✕</button>
      </div>

      {isCurrent && (
        <div className="mt-3 pl-6 space-y-3">
          <div>
            <div className={`${cap} mb-1`}>WHAT WAS SAID</div>
            <textarea className={`${inp} min-h-[60px]`} defaultValue={item.outcome_notes || ''}
              placeholder="Outcome, discussion, anything worth minuting…"
              onChange={e => saveNotes(e.target.value)} />
          </div>

          <div>
            <div className={`${cap} mb-1`}>MOTIONS</div>
            <div className="space-y-2">
              {motions.map(mo => (
                <Motion key={mo.id} motion={mo} present={present} nameOf={nameOf}
                  actions={actions.filter(a => a.motion_id === mo.id)}
                  onChange={p => onMotionChange(mo.id, p)} onDelete={() => onMotionDelete(mo.id)}
                  onVotes={v => onMotionVotes(mo.id, v)} onAddAction={onAddAction}
                  onActionChange={onActionChange} onActionDelete={onActionDelete} />
              ))}
            </div>
            <div className="flex gap-2 mt-2">
              <input className={`${inp} flex-1`} placeholder="Motion wording…" value={addingMotion}
                onChange={e => setAddingMotion(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && addingMotion.trim()) {
                    onAddMotion(addingMotion.trim()); setAddingMotion('')
                  }
                }} />
              <button className={btn} disabled={!addingMotion.trim()}
                onClick={() => { onAddMotion(addingMotion.trim()); setAddingMotion('') }}>+ Motion</button>
            </div>
          </div>

          <div>
            <div className={`${cap} mb-1`}>ACTIONS</div>
            <div className="space-y-1">
              {actions.filter(a => !a.motion_id).map(a => (
                <ActionRow key={a.id} action={a} nameOf={nameOf}
                  onChange={p => onActionChange(a.id, p)} onDelete={() => onActionDelete(a.id)} />
              ))}
            </div>
            {addingAction ? (
              <ActionForm agendaItemId={item.id} present={present}
                onSave={async d => { await onAddAction(d); setAddingAction(false) }}
                onCancel={() => setAddingAction(false)} />
            ) : (
              <button onClick={() => setAddingAction(true)} className={`${btn} mt-1`}>+ Action</button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ── The screen ─────────────────────────────────────────────────────────── */

export default function MeetingRoom() {
  const { meetingId } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [currentId, setCurrentId] = useState(null)
  const [newItem, setNewItem] = useState('')
  const dragIndex = useRef(null)
  const [dragOver, setDragOver] = useState(null)

  const load = useCallback(() => {
    api.committeeMeetingRoom(meetingId)
      .then(d => { setData(d); setErr(null) })
      .catch(e => setErr(`${e.message}${e.status ? ` (HTTP ${e.status})` : ''}`))
  }, [meetingId])
  useEffect(() => { load() }, [load])

  const wrap = fn => async (...args) => {
    try { await fn(...args); load() } catch (e) { toast.error(e.message) }
  }

  const meeting = data?.meeting
  const items = data?.agenda_items || []
  const motions = data?.motions || []
  const actions = data?.actions || []
  const pool = data?.attendee_pool || []
  const attendance = data?.attendance || []

  const nameOf = useCallback(id => pool.find(p => p.member_id === id)?.full_name, [pool])
  // Only people actually in the room can vote or be given an action.
  const present = useMemo(
    () => attendance.filter(a => a.status === 'present')
      .map(a => ({ member_id: a.member_id, full_name: a.full_name || nameOf(a.member_id) || 'Unknown' })),
    [attendance, nameOf])

  const saveMinutes = useAutosave(v => api.committeeUpdateMeeting(meetingId, { minutes: v }).catch(e => toast.error(e.message)))
  const saveNotes = useAutosave(v => api.committeeUpdateMeeting(meetingId, { private_notes: v }).catch(e => toast.error(e.message)))

  const setAttendance = wrap(async (memberId, status) => {
    const next = attendance.filter(a => a.member_id !== memberId).map(a => ({ member_id: a.member_id, status: a.status }))
    if (status) next.push({ member_id: memberId, status })
    await api.committeeSetAttendance(meetingId, next)
  })

  const onDrop = wrap(async toIdx => {
    const from = dragIndex.current
    dragIndex.current = null; setDragOver(null)
    if (from === null || from === toIdx) return
    const next = [...items]
    const [moved] = next.splice(from, 1)
    next.splice(toIdx, 0, moved)
    setData(d => ({ ...d, agenda_items: next }))   // optimistic, so the drag feels instant
    await api.committeeReorderAgenda(meetingId, next.map(i => i.id))
  })

  if (err) {
    return (
      <BetterClubhouseLayout title="Meeting">
        <div className="pb-card p-6">
          <div className="text-pb-text text-sm mb-1">Could not open this meeting.</div>
          <div className="font-mono text-[11px] text-pb-red mb-3">{err}</div>
          <button onClick={load} className={btn}>Try again</button>
        </div>
      </BetterClubhouseLayout>
    )
  }
  if (!data) return <BetterClubhouseLayout title="Meeting"><PbSpinner message="Opening the meeting…" /></BetterClubhouseLayout>

  const when = meeting.scheduled_at ? new Date(meeting.scheduled_at).toLocaleString() : ''
  const isClosed = meeting.status === 'completed' || meeting.status === 'cancelled'

  return (
    <BetterClubhouseLayout
      title={meeting.title}
      caption={`${when}${meeting.location ? ` · ${meeting.location}` : ''}`}
      actions={
        <div className="flex items-center gap-2">
          <select value={meeting.status}
            onChange={e => { api.committeeUpdateMeeting(meetingId, { status: e.target.value }).then(load).catch(err2 => toast.error(err2.message)) }}
            className="bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 font-mono text-[10px] text-pb-text">
            {['scheduled', 'in_progress', 'completed', 'cancelled'].map(s => <option key={s} value={s}>{titleCase(s)}</option>)}
          </select>
          <Link to="/admin/clubhouse/committee/manage" className={btn}>All meetings</Link>
        </div>
      }
    >
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_320px] gap-5 items-start">
        <div className="space-y-2">
          {isClosed && (
            <div className="pb-card p-3 font-mono text-[10px] text-pb-faint">
              This meeting is {titleCase(meeting.status).toLowerCase()}. Everything below is still editable —
              minutes are usually finished after the room empties.
            </div>
          )}

          {items.length === 0 && (
            <div className="pb-card p-6 text-center">
              <div className="text-pb-text text-[13px] mb-1">No agenda yet.</div>
              <div className={cap}>Add the first item below, or apply a template from the meetings list.</div>
            </div>
          )}

          {items.map((item, idx) => (
            <div key={item.id}
              className={`rounded ${dragOver === idx ? 'ring-1 ring-pb-accent/60' : ''}`}
              onDragOver={e => { e.preventDefault(); if (dragOver !== idx) setDragOver(idx) }}
              onDragLeave={() => setDragOver(o => (o === idx ? null : o))}
              onDrop={() => onDrop(idx)}>
              <AgendaItem
                item={item} index={idx} isCurrent={currentId === item.id}
                onOpen={() => setCurrentId(c => (c === item.id ? null : item.id))}
                dragProps={{
                  draggable: true,
                  onDragStart: () => { dragIndex.current = idx },
                  onDragEnd: () => { dragIndex.current = null; setDragOver(null) },
                }}
                present={present} nameOf={nameOf}
                motions={motions.filter(m => m.agenda_item_id === item.id)}
                actions={actions.filter(a => a.agenda_item_id === item.id)}
                onItemChange={wrap(p => api.committeeUpdateAgendaItem(meetingId, item.id, p))}
                onItemDelete={wrap(() => api.committeeDeleteAgendaItem(meetingId, item.id))}
                onAddMotion={wrap(desc => api.committeeCreateMotion(meetingId, { description: desc, agenda_item_id: item.id }))}
                onMotionChange={wrap((id, p) => api.committeeUpdateMotion(meetingId, id, p))}
                onMotionDelete={wrap(id => api.committeeDeleteMotion(meetingId, id))}
                onMotionVotes={wrap((id, v) => api.committeeSetMotionVotes(meetingId, id, v))}
                onAddAction={wrap(d => api.committeeCreateTask({ ...d, meeting_id: meetingId }))}
                onActionChange={wrap((id, p) => api.committeeUpdateTask(id, p))}
                onActionDelete={wrap(id => api.committeeDeleteTask(id))}
              />
            </div>
          ))}

          <div className="flex gap-2 pt-1">
            <input className={`${inp} flex-1`} placeholder="Add an agenda item…" value={newItem}
              onChange={e => setNewItem(e.target.value)}
              onKeyDown={e => {
                if (e.key === 'Enter' && newItem.trim()) {
                  wrap(() => api.committeeCreateAgendaItem(meetingId, { title: newItem.trim(), position: items.length }))()
                  setNewItem('')
                }
              }} />
            <button className={btn} disabled={!newItem.trim()}
              onClick={() => {
                wrap(() => api.committeeCreateAgendaItem(meetingId, { title: newItem.trim(), position: items.length }))()
                setNewItem('')
              }}>+ Item</button>
          </div>

          {/* Anything raised before an agenda existed, or against a deleted item,
              would otherwise be invisible on this screen. */}
          {actions.filter(a => !a.agenda_item_id).length > 0 && (
            <div className="pb-card p-3 mt-2">
              <div className={`${cap} mb-1.5`}>ACTIONS NOT AGAINST AN AGENDA ITEM</div>
              <div className="space-y-1">
                {actions.filter(a => !a.agenda_item_id).map(a => (
                  <ActionRow key={a.id} action={a} nameOf={nameOf}
                    onChange={wrap(p => api.committeeUpdateTask(a.id, p))}
                    onDelete={wrap(() => api.committeeDeleteTask(a.id))} />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-3 xl:sticky xl:top-6">
          <Attendance pool={pool} attendance={attendance} onChange={setAttendance} />

          <div className="pb-card p-4">
            <div className={`${cap} mb-1.5`}>MINUTES</div>
            <textarea className={`${inp} min-h-[120px]`} defaultValue={meeting.minutes || ''}
              placeholder="The record that gets circulated…" onChange={e => saveMinutes(e.target.value)} />
            <div className="font-mono text-[9px] text-pb-faintest mt-1">Saves as you type.</div>
          </div>

          <div className="pb-card p-4">
            <div className={`${cap} mb-1.5`}>YOUR NOTES</div>
            <textarea className={`${inp} min-h-[80px]`} defaultValue={meeting.private_notes || ''}
              placeholder="Not part of the minutes…" onChange={e => saveNotes(e.target.value)} />
            <div className="font-mono text-[9px] text-pb-faintest mt-1">
              Never circulated with the minutes.
            </div>
          </div>
        </div>
      </div>
    </BetterClubhouseLayout>
  )
}
