import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubhouseLayout from '../../components/admin/BetterClubhouseLayout'
import { PbSpinner } from '../../lib/presskit'
import { ObjectiveSelect, useObjectives, objectiveLabel } from '../../components/admin/clubmanager/governance'

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
//
// TWO PLACES, ONE ROOM. `MeetingRoomPanel` is the whole screen minus its
// chrome, so it also runs inside the Committee screen's right-hand pane when
// OPEN is pressed on a meeting card — the club's other meetings stay in view
// beside the one being minuted. The route below is unchanged and still the
// full-page version, so /admin/clubhouse/committee/meeting/:meetingId and every
// link to it work exactly as before.
//   · standalone — the layout header carries the title, the status select and
//     "All meetings"; the panel reports what it needs through `onMeta`.
//   · embedded   — `inlineHeader` draws the same three things inside the pane,
//     with Close in place of the link, since the list is already beside it.

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const cap = 'font-mono text-[10px] tracking-wide3 text-pb-faintest'
const btn = 'px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-40 whitespace-nowrap'
const btnAccent = 'px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap'

const AGENDA_STATUSES = ['proposed', 'discussed', 'carried', 'deferred', 'withdrawn']
const MOTION_OUTCOMES = ['pending', 'carried', 'lost', 'withdrawn']
// Chair is a kind of present — someone has to run the meeting, and recording it
// matters when the President is away. It sorts first so the chair is obvious.
const ATTEND = [['chair', 'Chair'], ['present', 'Present'], ['apology', 'Apology'], ['absent', 'Absent']]
const IN_ROOM = new Set(['chair', 'present'])

// An outcome should be readable without reading. These are the existing theme
// tokens, not new colours: green carried, red lost, amber pending/deferred,
// grey for anything withdrawn or not yet reached.
const TONE = {
  carried: 'var(--pb-positive-ink)',
  lost: 'var(--pb-red-ink)',
  deferred: 'var(--pb-accent-ink)',
  pending: 'var(--pb-accent-ink)',
  discussed: 'var(--pb-accent-ink)',
  proposed: 'var(--pb-faint)',
  withdrawn: 'var(--pb-faint)',
}
const toneOf = v => TONE[v] || 'var(--pb-faint)'
// A tinted left edge, so a glance down the agenda reads as a set of outcomes.
const edge = v => ({ borderLeft: `2px solid ${toneOf(v)}` })
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

function Attendance({ pool, attendance, onChange, previous, onCarryOver }) {
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
  const present = attendance.filter(a => IN_ROOM.has(a.status)).length
  const chair = pool.find(p => byId[p.member_id] === 'chair')

  return (
    <div className="pb-card p-4">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-2">
        <div className={cap}>WHO IS HERE</div>
        <div className="font-mono text-[10px] text-pb-faint">
          {present} present · {attendance.filter(a => a.status === 'apology').length} apologies
        </div>
      </div>
      <div className="font-mono text-[10px] mb-2" style={{ color: chair ? 'var(--pb-accent-ink)' : 'var(--pb-faintest)' }}>
        {chair ? `Chaired by ${chair.full_name}` : 'No chair recorded'}
      </div>
      {/* Committee attendance is largely the same people every month. Offered
          only while nothing is recorded yet, so it can never quietly overwrite
          a list someone has started. */}
      {previous && attendance.length === 0 && (
        <button onClick={() => onCarryOver(previous.present_member_ids)}
          className={`${btn} w-full mb-2`}>
          Same as {previous.title} ({previous.present_member_ids.length} present)
        </button>
      )}
      <input className={`${inp} mb-2`} placeholder="Search anyone in the club…"
        value={query} onChange={e => setQuery(e.target.value)} />
      <div className="space-y-1 max-h-[260px] overflow-y-auto pb-scroll">
        {shown.length === 0 && (
          <div className="font-mono text-[10px] text-pb-faintest py-2">No one matches that.</div>
        )}
        {/* Two lines per person, not one: a fourth button (Chair) left the name
            column so narrow that "Ali Nunn" truncated and the position under it
            never showed at all. */}
        {shown.map(p => (
          <div key={p.member_id} className="py-0.5">
            <div className="text-[12.5px] text-pb-text truncate leading-tight">{p.full_name}</div>
            <div className="flex items-center justify-between gap-2 mt-0.5">
              <span className="font-mono text-[9px] text-pb-faintest truncate">
                {p.position ? p.position.toUpperCase() : ''}
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

function ActionForm({ agendaItemId, motionId, present, pool, objectives, defaultObjectiveId, onSave, onCancel }) {
  const [form, setForm] = useState({
    title: '', due_date: '', budget_estimate: '',
    // Raised under a motion that already serves an objective? Then it serves
    // the same one unless somebody says otherwise — retyping it is the step
    // that gets skipped, and then the plan reports short.
    objective_id: defaultObjectiveId || '',
  })
  const [owners, setOwners] = useState([])
  const [busy, setBusy] = useState(false)
  const [who, setWho] = useState('')

  const toggle = id => setOwners(o => o.includes(id) ? o.filter(x => x !== id) : [...o, id])
  // People in the room are the quick picks, but plenty of work goes to someone
  // who is not at the meeting — an absent committee member, a club member, a
  // contractor. Typing searches everyone.
  const q = who.trim().toLowerCase()
  const chosen = (pool || []).filter(p => owners.includes(p.member_id))
  const options = q
    ? (pool || []).filter(p => p.full_name.toLowerCase().includes(q)).slice(0, 8)
    : [...present, ...chosen.filter(c => !present.some(p => p.member_id === c.member_id))]

  async function submit() {
    if (!form.title.trim()) return
    setBusy(true)
    try {
      await onSave({
        title: form.title.trim(),
        due_date: form.due_date || null,
        budget_estimate: form.budget_estimate === '' ? null : Number(form.budget_estimate),
        objective_id: form.objective_id || null,
        agenda_item_id: agendaItemId || null,
        motion_id: motionId || null,
        assignee_member_ids: owners,
      })
      setForm({ title: '', due_date: '', budget_estimate: '', objective_id: defaultObjectiveId || '' })
      setOwners([])
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
      <div className="mb-2">
        <ObjectiveSelect objectives={objectives} value={form.objective_id}
          onChange={v => setForm(f => ({ ...f, objective_id: v || '' }))} label="SERVES OBJECTIVE" />
      </div>
      <div className={`${cap} mb-1`}>WHO IS DOING IT</div>
      <input className={`${inp} mb-1.5`} placeholder="Anyone in the club — type to search…"
        value={who} onChange={e => setWho(e.target.value)} />
      <div className="flex flex-wrap gap-1 mb-2">
        {options.length === 0 && (
          <span className="font-mono text-[10px] text-pb-faintest">
            {q ? 'Nobody matches that.' : 'Mark someone present, or search above.'}
          </span>
        )}
        {options.map(p => (
          <button key={p.member_id} onClick={() => toggle(p.member_id)}
            className={`px-2 py-1 rounded font-mono text-[9px] border ${owners.includes(p.member_id)
              ? 'text-pb-bg border-transparent' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
            style={owners.includes(p.member_id) ? { background: 'var(--pb-accent)' } : undefined}>
            {p.full_name}
          </button>
        ))}
      </div>
      <div className="flex gap-2">
        <button onClick={submit} disabled={busy || !form.title.trim()} className={btnAccent}
          style={{ background: 'var(--pb-accent)' }}>{busy ? 'SAVING…' : '+ ACTION'}</button>
        <button onClick={onCancel} className={btn}>Cancel</button>
      </div>
    </div>
  )
}

function ActionRow({ action, nameOf, objectiveOf, onChange, onDelete }) {
  const owners = (action.assignee_member_ids || []).map(nameOf).filter(Boolean)
  const serves = objectiveOf?.(action.objective_id)
  return (
    <div className="flex items-start justify-between gap-2 border pb-hairline rounded px-2.5 py-2 bg-pb-surface2/30"
      style={edge(action.status === 'done' ? 'carried' : action.status === 'blocked' ? 'lost' : 'deferred')}>
      <div className="min-w-0">
        <div className="text-[12.5px] text-pb-text">{action.title}</div>
        <div className="font-mono text-[9.5px] text-pb-faintest mt-0.5 flex flex-wrap gap-x-2">
          {owners.length > 0 && <span>{owners.join(', ')}</span>}
          {action.due_date && <span>due {action.due_date}</span>}
          {action.budget_estimate != null && <span>${Number(action.budget_estimate).toLocaleString('en-AU')}</span>}
          <span>{titleCase(action.status)}</span>
        </div>
        {serves && <div className="font-mono text-[9px] text-pb-faintest mt-0.5">serves {serves}</div>}
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

function Motion({ motion, present, pool, nameOf, objectives, objectiveOf, onChange, onDelete, onVotes,
                 onAddAction, actions, onActionChange, onActionDelete, dragProps, isOver }) {
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
    <div className={`border pb-hairline rounded p-2.5 bg-pb-surface2/30 ${isOver ? 'ring-1 ring-pb-accent/60' : ''}`}
      style={edge(motion.outcome)} {...(dragProps?.zone || {})}>
      <div className="flex items-start justify-between gap-2">
        {/* Drag to reorder within this item, or onto another agenda item's row
            to move the motion there. */}
        <span className="cursor-grab active:cursor-grabbing text-pb-faintest select-none pt-0.5 shrink-0"
          title="Drag to reorder, or onto another agenda item" {...(dragProps?.handle || {})}>⠿</span>
        <div className="text-[12.5px] text-pb-text min-w-0 flex-1">{motion.description}</div>
        <div className="flex items-center gap-1 shrink-0">
          <select value={motion.outcome} onChange={e => onChange({ outcome: e.target.value })}
            style={{ color: toneOf(motion.outcome) }}
            className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-1 font-mono text-[9px]">
            {MOTION_OUTCOMES.map(o => <option key={o} value={o}>{titleCase(o)}</option>)}
          </select>
          <button onClick={onDelete} className="font-mono text-[9px] text-pb-faint hover:text-pb-red">✕</button>
        </div>
      </div>
      <div className="flex items-center gap-2 mt-1.5 flex-wrap">
        <button onClick={() => setShowVotes(v => !v)} className="font-mono text-[9px] text-pb-faint hover:text-pb-text">
          {showVotes ? 'Hide votes' : 'Record votes'}
        </button>
        <span className="font-mono text-[9px]">
          <span style={{ color: TONE.carried }}>{motion.votes_for ?? 0} for</span>
          <span className="text-pb-faintest"> · </span>
          <span style={{ color: TONE.lost }}>{motion.votes_against ?? 0} against</span>
          <span className="text-pb-faintest"> · {motion.votes_abstain ?? 0} abstain</span>
        </span>
        <button onClick={() => setAdding(a => !a)} className="font-mono text-[9px] text-pb-faint hover:text-pb-text">+ Action</button>
      </div>

      {/* Which line of the club's plan this decision serves. An action raised
          under the motion inherits it, so the decision and the work that
          follows report against the same objective. */}
      <div className="mt-1.5 max-w-md">
        <ObjectiveSelect objectives={objectives} value={motion.objective_id}
          onChange={v => onChange({ objective_id: v })} className={`${inp} text-[12px]`} label="SERVES OBJECTIVE" />
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
        <ActionForm motionId={motion.id} agendaItemId={motion.agenda_item_id} present={present} pool={pool}
          objectives={objectives} defaultObjectiveId={motion.objective_id}
          onSave={async d => { await onAddAction(d); setAdding(false) }} onCancel={() => setAdding(false)} />
      )}
      {actions.length > 0 && (
        <div className="mt-2 space-y-1">
          {actions.map(a => (
            <ActionRow key={a.id} action={a} nameOf={nameOf} objectiveOf={objectiveOf}
              onChange={p => onActionChange(a.id, p)} onDelete={() => onActionDelete(a.id)} />
          ))}
        </div>
      )}
    </div>
  )
}

/* ── One agenda item ────────────────────────────────────────────────────── */

function AgendaItem({
  item, index, isCurrent, onOpen, dragProps, present, pool, nameOf, objectives, objectiveOf,
  sections, motions, actions, onItemChange, onItemDelete,
  onAddMotion, onMotionChange, onMotionDelete, onMotionVotes,
  onAddAction, onActionChange, onActionDelete,
  motionDrag,
}) {
  const [addingMotion, setAddingMotion] = useState('')
  const [addingAction, setAddingAction] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(item.title)
  const [sectionDraft, setSectionDraft] = useState(item.section || '')
  const saveNotes = useAutosave(v => onItemChange({ outcome_notes: v }))
  const saveEdit = () => {
    onItemChange({ title: draft, section: sectionDraft.trim() || null })
    setEditing(false)
  }

  return (
    <div className={`pb-card p-3 ${isCurrent ? 'ring-1' : ''}`}
      style={{ ...edge(item.status), ...(isCurrent ? { boxShadow: '0 0 0 1px var(--pb-accent)' } : {}) }}
      {...dragProps}>
      <div className="flex items-start gap-2">
        <span className="cursor-grab active:cursor-grabbing text-pb-faintest select-none pt-0.5" title="Drag to reorder">⠿</span>
        <div className="flex-1 min-w-0">
          {editing ? (
            <div className="flex gap-2 flex-wrap">
              <input className={`${inp} flex-1 min-w-[10rem]`} value={draft} autoFocus
                onChange={e => setDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') saveEdit() }} />
              {/* Type a new heading or pick one already in this meeting. A
                  datalist rather than a select, because the first item of a
                  section has to be able to invent it. */}
              <input className={`${inp} w-full sm:w-52`} list={`sections-${item.id}`}
                placeholder="Section (optional)" value={sectionDraft}
                onChange={e => setSectionDraft(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') saveEdit() }} />
              <datalist id={`sections-${item.id}`}>
                {(sections || []).map(s => <option key={s} value={s} />)}
              </datalist>
              <button onClick={saveEdit} className={btn}>Save</button>
            </div>
          ) : (
            <button onClick={onOpen} className="text-left w-full">
              <span className="font-mono text-[10px] text-pb-faintest mr-2">{index + 1}</span>
              <span className="text-[13.5px] text-pb-text">{item.title}</span>
              {/* What is attached, without having to open it. */}
              <div className="font-mono text-[9.5px] mt-0.5 flex flex-wrap gap-x-2">
                <span style={{ color: toneOf(item.status) }}>{titleCase(item.status)}</span>
                {motions.length > 0 && (
                  <span className="text-pb-faintest">
                    {motions.length} motion{motions.length === 1 ? '' : 's'}
                    {motions.some(m => m.outcome === 'carried') &&
                      <span style={{ color: TONE.carried }}> · {motions.filter(m => m.outcome === 'carried').length} carried</span>}
                    {motions.some(m => m.outcome === 'lost') &&
                      <span style={{ color: TONE.lost }}> · {motions.filter(m => m.outcome === 'lost').length} lost</span>}
                  </span>
                )}
                {actions.length > 0 && (
                  <span className="text-pb-faintest">
                    {actions.length} action{actions.length === 1 ? '' : 's'}
                    {actions.some(a => a.status !== 'done') &&
                      <span style={{ color: TONE.deferred }}> · {actions.filter(a => a.status !== 'done').length} open</span>}
                  </span>
                )}
                {item.outcome_notes && <span className="text-pb-faintest">minuted</span>}
              </div>
            </button>
          )}
        </div>
        <select value={item.status} onChange={e => onItemChange({ status: e.target.value })}
          style={{ color: toneOf(item.status) }}
          className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-1 font-mono text-[9px] shrink-0">
          {AGENDA_STATUSES.map(o => <option key={o} value={o}>{titleCase(o)}</option>)}
        </select>
        <button onClick={() => { setDraft(item.title); setSectionDraft(item.section || ''); setEditing(true) }}
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
              {motions.map((mo, mi) => (
                <Motion key={mo.id} motion={mo} present={present} pool={pool} nameOf={nameOf}
                  objectives={objectives} objectiveOf={objectiveOf}
                  actions={actions.filter(a => a.motion_id === mo.id)}
                  onChange={p => onMotionChange(mo.id, p)} onDelete={() => onMotionDelete(mo.id)}
                  onVotes={v => onMotionVotes(mo.id, v)} onAddAction={onAddAction}
                  onActionChange={onActionChange} onActionDelete={onActionDelete}
                  isOver={motionDrag?.overId === mo.id}
                  dragProps={motionDrag?.propsFor(mo, mi)} />
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
                <ActionRow key={a.id} action={a} nameOf={nameOf} objectiveOf={objectiveOf}
                  onChange={p => onActionChange(a.id, p)} onDelete={() => onActionDelete(a.id)} />
              ))}
            </div>
            {addingAction ? (
              <ActionForm agendaItemId={item.id} present={present} pool={pool} objectives={objectives}
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

/* ── The room itself ────────────────────────────────────────────────────── */

// Everything the meeting room does, with no page chrome of its own.
//
//   meetingId    — which meeting to run.
//   onMeta       — called on every load with { meeting, setStatus, reload }, so
//                  a host that draws the header elsewhere (the full-page route)
//                  can show the title, the status select and stay in step.
//   inlineHeader — draw that header inside the pane instead (the embedded case).
//   onExit       — offered as Close beside the inline header.
export function MeetingRoomPanel({ meetingId, onMeta, inlineHeader = false, onExit }) {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [err, setErr] = useState(null)
  const [currentId, setCurrentId] = useState(null)
  const [newItem, setNewItem] = useState('')
  // One drag controller for both kinds. An agenda row is a drop target for
  // BOTH — drop an item on it to reorder the agenda, or drop a motion on it to
  // move that motion under it — so the ref has to say which is in flight.
  const drag = useRef({ kind: null, index: null, motionId: null })
  const [dragOver, setDragOver] = useState(null)
  const [motionOver, setMotionOver] = useState(null)

  const load = useCallback(() => {
    api.committeeMeetingRoom(meetingId)
      .then(d => { setData(d); setErr(null) })
      .catch(e => setErr(`${e.message}${e.status ? ` (HTTP ${e.status})` : ''}`))
  }, [meetingId])
  useEffect(() => { load() }, [load])

  // The one thing about the meeting itself this screen changes.
  const setStatus = useCallback(v => {
    api.committeeUpdateMeeting(meetingId, { status: v })
      .then(load)
      .catch(e => toast.error(e.message))
  }, [meetingId, load, toast])

  // Hand the host what it needs to draw the header where it draws headers.
  // Depends on `data` alone: the callback is a setState from the host and the
  // two functions here are only read, never compared.
  useEffect(() => {
    if (!onMeta) return
    onMeta(data ? { meeting: data.meeting, setStatus, reload: load } : null)
  }, [data])   // eslint-disable-line react-hooks/exhaustive-deps

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
  // The club's plan, so anything raised in the meeting can be pointed at the
  // objective it serves. Fetched once for the room, not per motion.
  const objectives = useObjectives()
  const objectiveOf = useCallback(id => {
    const o = objectives.find(x => x.id === id)
    return o ? objectiveLabel(o) : null
  }, [objectives])
  // The headings already in use, in agenda order, for the section picker.
  const sections = useMemo(
    () => [...new Set(items.map(i => i.section).filter(Boolean))], [items])
  // Only people actually in the room can vote or be given an action.
  // Who is in the room, for voting. The chair is present too.
  const present = useMemo(
    () => attendance.filter(a => IN_ROOM.has(a.status))
      .map(a => ({ member_id: a.member_id, full_name: a.full_name || nameOf(a.member_id) || 'Unknown' })),
    [attendance, nameOf])

  const minutesRef = useRef(null)
  const [drafting, setDrafting] = useState(false)
  const saveMinutes = useAutosave(v => api.committeeUpdateMeeting(meetingId, { minutes: v }).catch(e => toast.error(e.message)))

  // Writes into the box rather than saving straight over the record: minutes
  // are the club's account of what happened, and a machine's first pass is a
  // starting point, not a decision.
  async function draft() {
    if (minutesRef.current?.value?.trim() &&
        !confirm('Replace what is in the minutes box with a fresh draft?')) return
    setDrafting(true)
    try {
      const r = await api.committeeDraftMinutes(meetingId)
      if (minutesRef.current) minutesRef.current.value = r.draft
      await api.committeeUpdateMeeting(meetingId, { minutes: r.draft })
      toast.success('Draft written. Read it before it becomes the record.')
    } catch (e) { toast.error(e.message) } finally { setDrafting(false) }
  }
  const saveNotes = useAutosave(v => api.committeeUpdateMeeting(meetingId, { private_notes: v }).catch(e => toast.error(e.message)))

  // One write, not one per person: the endpoint replaces the whole list anyway.
  const carryOver = wrap(async ids => {
    await api.committeeSetAttendance(meetingId, ids.map(member_id => ({ member_id, status: 'present' })))
  })

  const setAttendance = wrap(async (memberId, status) => {
    const next = attendance.filter(a => a.member_id !== memberId).map(a => ({ member_id: a.member_id, status: a.status }))
    if (status) next.push({ member_id: memberId, status })
    await api.committeeSetAttendance(meetingId, next)
  })

  // Motions are ordered across the whole meeting, but dragged within an item.
  // So a within-item reorder is spliced back into the meeting-wide sequence
  // before it is sent, otherwise moving a motion under one heading would
  // scramble the order under every other.
  const motionOrderAfter = (movedId, targetId) => {
    const all = [...motions]
    const from = all.findIndex(m => m.id === movedId)
    const to = all.findIndex(m => m.id === targetId)
    if (from < 0 || to < 0 || from === to) return null
    const [moved] = all.splice(from, 1)
    all.splice(to, 0, moved)
    return all
  }

  const dropOnMotion = wrap(async targetMotion => {
    const { kind, motionId } = drag.current
    drag.current = { kind: null, index: null, motionId: null }
    setMotionOver(null)
    if (kind !== 'motion' || !motionId || motionId === targetMotion.id) return
    const next = motionOrderAfter(motionId, targetMotion.id)
    if (!next) return
    setData(d => ({ ...d, motions: next }))
    await api.committeeReorderMotions(meetingId, next.map(m => m.id))
  })

  const onDrop = wrap(async toIdx => {
    const { kind, index: from, motionId } = drag.current
    drag.current = { kind: null, index: null, motionId: null }
    setDragOver(null)

    // A motion dropped on an agenda row moves under that heading.
    if (kind === 'motion' && motionId) {
      const target = items[toIdx]
      const mo = motions.find(m => m.id === motionId)
      if (!target || !mo || mo.agenda_item_id === target.id) return
      await api.committeeUpdateMotion(meetingId, motionId, { agenda_item_id: target.id })
      return
    }

    if (kind !== 'item' || from === null || from === toIdx) return
    const next = [...items]
    const [moved] = next.splice(from, 1)
    next.splice(toIdx, 0, moved)
    // An item dragged in among another section's rows joins that section —
    // dropping it under "Annual reports" and having it stay in "Opening
    // formalities" is not what the person doing it meant. It takes the section
    // of whatever it landed after, or of the row below when it went to the top.
    const at = next.indexOf(moved)
    const neighbour = next[at - 1] || next[at + 1]
    moved.section = neighbour ? (neighbour.section || null) : moved.section
    setData(d => ({ ...d, agenda_items: next }))   // optimistic, so the drag feels instant
    await api.committeeReorderAgenda(meetingId, next.map(i => i.id), next.map(i => i.section || null))
  })

  const motionDrag = {
    overId: motionOver,
    propsFor: (mo) => ({
      handle: {
        draggable: true,
        onDragStart: e => {
          e.stopPropagation()
          drag.current = { kind: 'motion', index: null, motionId: mo.id }
        },
        onDragEnd: () => { drag.current = { kind: null, index: null, motionId: null }; setMotionOver(null) },
      },
      zone: {
        onDragOver: e => {
          if (drag.current.kind !== 'motion') return
          e.preventDefault(); e.stopPropagation()
          if (motionOver !== mo.id) setMotionOver(mo.id)
        },
        onDragLeave: () => setMotionOver(o => (o === mo.id ? null : o)),
        onDrop: e => { e.stopPropagation(); dropOnMotion(mo) },
      },
    }),
  }

  if (err) {
    return (
      <div className="pb-card p-6">
        <div className="text-pb-text text-sm mb-1">Could not open this meeting.</div>
        <div className="font-mono text-[11px] text-pb-red mb-3">{err}</div>
        <button onClick={load} className={btn}>Try again</button>
      </div>
    )
  }
  if (!data) return <PbSpinner message="Opening the meeting…" />

  const when = meeting.scheduled_at ? new Date(meeting.scheduled_at).toLocaleString() : ''
  const isClosed = meeting.status === 'completed' || meeting.status === 'cancelled'

  return (
    <>
      {inlineHeader && (
        <div className="flex items-start justify-between gap-3 flex-wrap mb-4">
          <div className="min-w-0">
            <h2 className="font-display font-bold text-[21px] text-pb-text leading-tight tracking-[-0.01em] m-0">
              {meeting.title}
            </h2>
            <div className="font-mono text-[11px] text-pb-faint mt-1">
              {when}{meeting.location ? ` · ${meeting.location}` : ''}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <select value={meeting.status} onChange={e => setStatus(e.target.value)}
              className="bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 font-mono text-[10px] text-pb-text">
              {['scheduled', 'in_progress', 'completed', 'cancelled'].map(s => <option key={s} value={s}>{titleCase(s)}</option>)}
            </select>
            {onExit && <button onClick={onExit} className={btn}>Close</button>}
          </div>
        </div>
      )}
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
              {/* The order of business is one ordered list; a heading is drawn
                  wherever the section changes. So the agenda reads as a club's
                  agenda without a second thing to keep in order. */}
              {(item.section || null) !== (items[idx - 1]?.section || null) && item.section && (
                <div className={`${cap} pt-3 pb-1`}>{item.section.toUpperCase()}</div>
              )}
              <AgendaItem
                item={item} index={idx} isCurrent={currentId === item.id}
                onOpen={() => setCurrentId(c => (c === item.id ? null : item.id))}
                dragProps={{
                  draggable: true,
                  onDragStart: () => { drag.current = { kind: 'item', index: idx, motionId: null } },
                  onDragEnd: () => { drag.current = { kind: null, index: null, motionId: null }; setDragOver(null) },
                }}
                motionDrag={motionDrag}
                present={present} pool={pool} nameOf={nameOf} sections={sections}
                objectives={objectives} objectiveOf={objectiveOf}
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

          {/* A new item joins whatever section the agenda currently ends in,
              which is what building one top to bottom means. Edit it if the
              new item starts the next section instead. */}
          {(() => {
            const tail = items[items.length - 1]?.section || null
            const addItem = () => {
              wrap(() => api.committeeCreateAgendaItem(meetingId, {
                title: newItem.trim(), position: items.length, section: tail,
              }))()
              setNewItem('')
            }
            return (
              <div className="pt-1">
                <div className="flex gap-2">
                  <input className={`${inp} flex-1`} placeholder="Add an agenda item…" value={newItem}
                    onChange={e => setNewItem(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter' && newItem.trim()) addItem() }} />
                  <button className={btn} disabled={!newItem.trim()} onClick={addItem}>+ Item</button>
                </div>
                {tail && (
                  <div className={`${cap} mt-1`}>GOES UNDER {tail.toUpperCase()}</div>
                )}
              </div>
            )
          })()}

          {/* Anything raised before an agenda existed, or against a deleted item,
              would otherwise be invisible on this screen. */}
          {actions.filter(a => !a.agenda_item_id).length > 0 && (
            <div className="pb-card p-3 mt-2">
              <div className={`${cap} mb-1.5`}>ACTIONS NOT AGAINST AN AGENDA ITEM</div>
              <div className="space-y-1">
                {actions.filter(a => !a.agenda_item_id).map(a => (
                  <ActionRow key={a.id} action={a} nameOf={nameOf} objectiveOf={objectiveOf}
                    onChange={wrap(p => api.committeeUpdateTask(a.id, p))}
                    onDelete={wrap(() => api.committeeDeleteTask(a.id))} />
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="space-y-3 xl:sticky xl:top-6">
          <Attendance pool={pool} attendance={attendance} onChange={setAttendance}
            previous={data.previous_attendance} onCarryOver={carryOver} />

          <div className="pb-card p-4">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className={cap}>MINUTES</span>
              <button onClick={draft} disabled={drafting} className="font-mono text-[9px] text-pb-faint hover:text-pb-text disabled:opacity-40">
                {drafting ? 'drafting…' : 'draft from the meeting'}
              </button>
            </div>
            <textarea ref={minutesRef} className={`${inp} min-h-[120px]`} defaultValue={meeting.minutes || ''}
              placeholder="The record that gets circulated…" onChange={e => saveMinutes(e.target.value)} />
            <div className="font-mono text-[9px] text-pb-faintest mt-1">
              Saves as you type. A draft is written from the agenda, motions, votes and
              actions above, and replaces what is in the box for you to correct. It is
              never the record until you say so.
            </div>
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
    </>
  )
}

/* ── The full-page route ────────────────────────────────────────────────── */

// /admin/clubhouse/committee/meeting/:meetingId — unchanged. The header is
// still the module's own, fed by whatever the panel last loaded.
export default function MeetingRoom() {
  const { meetingId } = useParams()
  const [meta, setMeta] = useState(null)
  const meeting = meta?.meeting
  const when = meeting?.scheduled_at ? new Date(meeting.scheduled_at).toLocaleString() : ''

  return (
    <BetterClubhouseLayout
      title={meeting?.title || 'Meeting'}
      caption={meeting ? `${when}${meeting.location ? ` · ${meeting.location}` : ''}` : undefined}
      actions={meeting && (
        <div className="flex items-center gap-2">
          <select value={meeting.status} onChange={e => meta.setStatus(e.target.value)}
            className="bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 font-mono text-[10px] text-pb-text">
            {['scheduled', 'in_progress', 'completed', 'cancelled'].map(s => <option key={s} value={s}>{titleCase(s)}</option>)}
          </select>
          <Link to="/admin/clubhouse/committee/manage" className={btn}>All meetings</Link>
        </div>
      )}
    >
      <MeetingRoomPanel meetingId={meetingId} onMeta={setMeta} />
    </BetterClubhouseLayout>
  )
}
