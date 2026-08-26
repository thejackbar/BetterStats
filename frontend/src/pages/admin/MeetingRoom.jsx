import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubhouseLayout from '../../components/admin/BetterClubhouseLayout'
import { PbSpinner } from '../../lib/presskit'
import { ObjectiveSelect, useObjectives, objectiveLabel } from '../../components/admin/clubmanager/governance'
import { downloadDocx, downloadPdf, docFilename } from '../../lib/textDocs'
import { buildMinutesDoc } from '../../components/admin/clubmanager/minutesDoc'

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
// An action's own vocabulary, mapped onto the outcome tones above so a glance
// down an agenda reads the same way whatever kind of record it is looking at.
const ACTION_TONE = { done: 'carried', blocked: 'lost', in_progress: 'pending', todo: 'proposed' }
// A date in the minutes is read, not sorted. "18 Sep 2026" beats "2026-09-18".
const shortDate = d => {
  if (!d) return ''
  const t = Date.parse(d)
  return Number.isFinite(t)
    ? new Date(t).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
    : d
}
const titleCase = s => (s || '').split('_').filter(Boolean).map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

// A state is a word on a tint, never a colour on its own: this app's green and
// amber separate by only ~7 ΔE under protanopia, so the word is the channel
// that always works and the colour is the one that usually helps.
function Pill({ tone, children }) {
  const c = toneOf(tone)
  return (
    <span className="px-1.5 py-0.5 rounded font-mono text-[9px] whitespace-nowrap shrink-0"
      style={{ color: c, background: `color-mix(in srgb, ${c} 12%, transparent)` }}>{children}</span>
  )
}

// A meeting's name is edited where it is read, like everything else in this
// room. Click the heading, Enter saves, Escape puts it back. A blank name is
// refused rather than saved: a meeting has to be called something, and an
// accidental select-all-and-delete must not wipe what the minutes are filed
// under. Declared here at module level, never inside a render — a component
// re-declared each render is a new element TYPE, and the browser takes the
// focused input down with the old subtree.
export function EditableHeading({ value, onSave, label = 'Name', size = 21 }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(value)
  const ref = useRef(null)
  useEffect(() => { if (editing && ref.current) { ref.current.focus(); ref.current.select() } }, [editing])
  const commit = () => {
    const next = draft.trim()
    setEditing(false)
    if (next && next !== value) onSave(next)
  }
  if (!editing) {
    return (
      <button type="button" title={`Click to rename. ${label}.`}
        onClick={() => { setDraft(value); setEditing(true) }}
        className="text-left decoration-dotted underline-offset-4 decoration-pb-faintest hover:underline">
        {value}
      </button>
    )
  }
  return (
    <input ref={ref} value={draft} aria-label={label}
      onChange={e => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={e => {
        if (e.key === 'Enter') { e.preventDefault(); commit() }
        if (e.key === 'Escape') { e.preventDefault(); setDraft(value); setEditing(false) }
      }}
      style={{ fontSize: size }}
      className="bg-pb-surface2 border pb-hairline rounded px-2 py-0.5 font-display font-bold text-pb-text w-full max-w-[460px] leading-tight" />
  )
}

// An explanation belongs on hover, not permanently under the control it
// explains. Non-interactive on purpose: there is nothing to open.
function Hint({ text }) {
  return (
    <span title={text} aria-label={text}
      className="inline-flex items-center justify-center w-[13px] h-[13px] ml-1 align-middle rounded-full border border-pb-hairline2 text-[8px] leading-none text-pb-faintest cursor-help">?</span>
  )
}

// Taking a text field away as a document. Word and PDF because those are what a
// committee actually opens: minutes get circulated and filed, and the club's own
// copy should not have to be a screenshot or a copy-paste out of a textarea.
//
// Disabled on an empty field rather than hidden, so the option is visible before
// there is anything to download and the button says why it cannot be pressed.
function DownloadRow({ label, empty, onDownload }) {
  return (
    <div className="flex items-center gap-1.5 mt-2">
      <span className={cap}>DOWNLOAD</span>
      {[['docx', 'Word Doc'], ['pdf', 'PDF']].map(([format, text]) => (
        <button key={format} type="button" className={btn} disabled={empty}
          onClick={() => onDownload(format)}
          title={empty ? `Nothing in ${label} to download yet` : `Download ${label} as ${text === 'PDF' ? 'a PDF' : 'a Word document'}`}>
          {text}
        </button>
      ))}
    </div>
  )
}

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

// The same form creates an action and corrects one. An action typed in a hurry
// at 8pm is exactly the one that needs fixing later, and until now the room
// could only mark it done or delete it.
function ActionForm({ agendaItemId, motionId, present, pool, objectives, defaultObjectiveId,
                      action, onSave, onCancel, onDelete }) {
  const editing = !!action
  const [form, setForm] = useState({
    title: action?.title || '',
    due_date: action?.due_date || '',
    budget_estimate: action?.budget_estimate ?? '',
    // Raised under a motion that already serves an objective? Then it serves
    // the same one unless somebody says otherwise — retyping it is the step
    // that gets skipped, and then the plan reports short.
    objective_id: action?.objective_id || defaultObjectiveId || '',
  })
  const [owners, setOwners] = useState(action?.assignee_member_ids || [])
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
      if (!editing) {
        setForm({ title: '', due_date: '', budget_estimate: '', objective_id: defaultObjectiveId || '' })
        setOwners([])
      }
    } finally { setBusy(false) }
  }

  return (
    <div className="rounded p-2.5 mt-2 bg-pb-surface2/60">
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
      <div className="flex gap-2 items-center">
        <button onClick={submit} disabled={busy || !form.title.trim()} className={btnAccent}
          style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'SAVING…' : editing ? 'SAVE' : '+ ACTION'}
        </button>
        <button onClick={onCancel} className={btn}>Cancel</button>
        {editing && onDelete && (
          <button onClick={onDelete}
            className="font-mono text-[9px] text-pb-faint hover:text-pb-red ml-auto">Delete action</button>
        )}
      </div>
    </div>
  )
}

// AN ACTION IS A RECORD TOO: who is doing it, by when, for how much, and what
// it serves, on two lines. Marking it done stays on the row because that is the
// act a committee repeats; everything else opens in the editor.
function ActionRow({ action, present, pool, objectives, nameOf, objectiveOf, onChange, onDelete }) {
  const [editing, setEditing] = useState(false)
  const owners = (action.assignee_member_ids || []).map(nameOf).filter(Boolean)
  const serves = objectiveOf?.(action.objective_id)

  if (editing) {
    return (
      <ActionForm action={action} present={present} pool={pool} objectives={objectives}
        agendaItemId={action.agenda_item_id} motionId={action.motion_id}
        onSave={async d => { await onChange(d); setEditing(false) }}
        onCancel={() => setEditing(false)}
        onDelete={() => { setEditing(false); onDelete() }} />
    )
  }

  return (
    <div className="flex items-start justify-between gap-2 pl-2.5 py-1"
      style={edge(ACTION_TONE[action.status] || 'deferred')}>
      <div className="min-w-0">
        <div className="flex items-start gap-2">
          <span className="text-[12.5px] text-pb-text">{action.title}</span>
          <Pill tone={ACTION_TONE[action.status]}>{titleCase(action.status)}</Pill>
        </div>
        <div className="font-mono text-[9.5px] text-pb-faintest mt-0.5 flex flex-wrap gap-x-2">
          {owners.length > 0 && <span>{owners.join(' + ')}</span>}
          {action.due_date && <span>due {shortDate(action.due_date)}</span>}
          {action.budget_estimate != null && <span>${Number(action.budget_estimate).toLocaleString('en-AU')}</span>}
        </div>
        {serves && <div className="font-mono text-[9px] text-pb-faintest mt-0.5">serves {serves}</div>}
      </div>
      <div className="flex gap-2 shrink-0">
        {action.status !== 'done' && (
          <button onClick={() => onChange({ status: 'done' })} className="font-mono text-[9px] text-pb-faint hover:text-pb-text">Done</button>
        )}
        <button onClick={() => setEditing(true)} className="font-mono text-[9px] text-pb-faint hover:text-pb-text">Edit</button>
      </div>
    </div>
  )
}

/* ── Motions ────────────────────────────────────────────────────────────── */

// Moved by / seconded by. The people in the room are who moves and seconds a
// motion, so the list is the attendance — but a name already recorded stays
// selectable even when that person is no longer marked present, or reopening
// the record would quietly drop it.
function MemberPick({ label, value, present, pool, onChange }) {
  const off = value && !present.some(p => p.member_id === value)
    ? (pool || []).find(p => p.member_id === value)
    : null
  const options = off ? [...present, off] : present
  return (
    <label className="flex-1 min-w-[9rem]">
      <div className={`${cap} mb-1`}>{label}</div>
      <select className={inp} value={value || ''} onChange={e => onChange(e.target.value || null)}>
        <option value="">— nobody recorded —</option>
        {options.map(p => <option key={p.member_id} value={p.member_id}>{p.full_name}</option>)}
      </select>
    </label>
  )
}

// THE SAME FORM MOVES A MOTION AND CORRECTS ONE. A motion is moved, seconded
// and voted on in one breath, so all of that is on screen the moment somebody
// presses "+ Add motion" — recording the vote used to mean creating the motion
// first and then reopening it under Edit.
//
// The two uses write differently, and both are right. Editing an existing
// motion saves as it is pressed, the way the rest of this room works: a vote is
// written the moment it is cast, so there is nothing a Cancel could undo. A new
// motion has no row to write to yet, so it is held until "+ MOTION" — and the
// NAMED votes go in a second request after that, since they key on the motion's
// own id.
function MotionForm({ motion, present, pool, objectives, defaultObjectiveId,
                      onChange, onVotes, onSave, onCancel, onDelete }) {
  const live = !!motion
  const [form, setForm] = useState({
    description: motion?.description || '',
    proposed_by_member_id: motion?.proposed_by_member_id || '',
    seconded_by_member_id: motion?.seconded_by_member_id || '',
    objective_id: motion?.objective_id || defaultObjectiveId || '',
    outcome: motion?.outcome || 'pending',
  })
  const [votes, setVotes] = useState(() => {
    const m = {}
    ;(motion?.votes || []).forEach(v => { m[v.member_id] = v.vote })
    return m
  })
  const [busy, setBusy] = useState(false)
  // Called on every render so the hook order never changes; only read when the
  // form is editing something that already exists.
  const saveWording = useAutosave(v => onChange?.({ description: v }))

  const set = (patch, { debounce = false } = {}) => {
    setForm(f => ({ ...f, ...patch }))
    if (!live) return
    if (debounce) saveWording(patch.description)
    else onChange?.(patch)
  }
  const voteList = v => Object.entries(v).map(([member_id, vote]) => ({ member_id, vote }))
  const setVote = (memberId, vote) => {
    const next = { ...votes }
    if (vote === null) delete next[memberId]
    else next[memberId] = vote
    setVotes(next)
    if (live) onVotes?.(voteList(next))
  }
  const allPresentFor = () => {
    const next = {}
    present.forEach(p => { next[p.member_id] = 'for' })
    setVotes(next)
    if (live) onVotes?.(voteList(next))
  }

  async function submit() {
    if (!form.description.trim()) return
    setBusy(true)
    try {
      await onSave({
        description: form.description.trim(),
        proposed_by_member_id: form.proposed_by_member_id || null,
        seconded_by_member_id: form.seconded_by_member_id || null,
        objective_id: form.objective_id || null,
        outcome: form.outcome,
        votes: voteList(votes),
      })
    } finally { setBusy(false) }
  }

  return (
    <div className="mt-2 rounded bg-pb-surface2/60 p-2.5 space-y-2">
      <textarea className={`${inp} min-h-[46px]`} value={form.description}
        placeholder="Motion wording…" autoFocus={!live}
        onChange={e => set({ description: e.target.value }, { debounce: true })} />
      {/* Who moved it and who seconded it — the two names every set of minutes
          records beside the wording. */}
      <div className="flex gap-2 flex-wrap">
        <MemberPick label="MOVED BY" value={form.proposed_by_member_id} present={present} pool={pool}
          onChange={v => set({ proposed_by_member_id: v })} />
        <MemberPick label="SECONDED BY" value={form.seconded_by_member_id} present={present} pool={pool}
          onChange={v => set({ seconded_by_member_id: v })} />
        {!live && (
          <label className="flex-1 min-w-[9rem]">
            <div className={`${cap} mb-1`}>OUTCOME</div>
            <select className={inp} value={form.outcome} style={{ color: toneOf(form.outcome) }}
              onChange={e => set({ outcome: e.target.value })}>
              {MOTION_OUTCOMES.map(o => <option key={o} value={o}>{titleCase(o)}</option>)}
            </select>
          </label>
        )}
      </div>
      {/* Which line of the club's plan this decision serves. An action raised
          under the motion inherits it, so the decision and the work that
          follows report against the same objective. */}
      <div className="max-w-md">
        <ObjectiveSelect objectives={objectives} value={form.objective_id}
          onChange={v => set({ objective_id: v || '' })} label="SERVES OBJECTIVE" />
      </div>
      <div>
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className={cap}>
            VOTES
            <Hint text="Recording names re-derives the tallies. Leave it empty and a counted show of hands stands." />
          </div>
          {present.length > 0 && (
            <button onClick={allPresentFor}
              className="font-mono text-[9px] text-pb-faint hover:text-pb-text">All present: For</button>
          )}
        </div>
        {present.length === 0 ? (
          <div className="font-mono text-[10px] text-pb-faintest">
            Only people marked present can vote. Set attendance first.
          </div>
        ) : (
          <div className="max-h-[220px] overflow-y-auto pb-scroll">
            {present.map(p => (
              <div key={p.member_id} className="flex items-center justify-between gap-2 py-0.5">
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
      </div>
      {live ? (
        <button onClick={onDelete} className="font-mono text-[9px] text-pb-faint hover:text-pb-red">Delete motion</button>
      ) : (
        <div className="flex gap-2 items-center">
          <button onClick={submit} disabled={busy || !form.description.trim()} className={btnAccent}
            style={{ background: 'var(--pb-accent)' }}>{busy ? 'SAVING…' : '+ MOTION'}</button>
          <button onClick={onCancel} className={btn}>Cancel</button>
        </div>
      )}
    </div>
  )
}

// NO BOX INSIDE A BOX: the agenda item is the container, and a motion is
// separated from its neighbours by its own tinted edge and by spacing. That is
// one rectangle fewer per record on a screen that had five of them nested.
//
// A MOTION IS A RECORD FIRST AND A FORM SECOND. During the meeting the only
// act is setting the outcome, so that is the one live control on the row; the
// wording, the objective it serves and the per-person votes are detail and open
// behind Edit. Everything still saves as it is pressed, as the rest of the room
// does, so the editor closes with Done rather than pretending to be a
// save-or-cancel transaction it is not: a vote is written the moment it is cast.
function Motion({ motion, present, pool, nameOf, objectives, objectiveOf, onChange, onDelete, onVotes,
                 onAddAction, actions, onActionChange, onActionDelete, dragProps, isOver }) {
  const [open, setOpen] = useState(false)
  const [adding, setAdding] = useState(false)
  const serves = objectiveOf?.(motion.objective_id)
  // Shown only when the club actually recorded one. A club that counts hands
  // and never names a mover should not have every motion carrying a reproach.
  const moved = nameOf?.(motion.proposed_by_member_id)
  const seconded = nameOf?.(motion.seconded_by_member_id)
  const movers = [moved && `moved by ${moved}`, seconded && `seconded by ${seconded}`]
    .filter(Boolean).join(' · ')

  return (
    <div className={`pl-2.5 py-1 ${isOver ? 'ring-1 ring-pb-accent/60 rounded' : ''}`}
      style={edge(motion.outcome)} {...(dragProps?.zone || {})}>
      <div className="flex items-start justify-between gap-2">
        {/* Drag to reorder within this item, or onto another agenda item's row
            to move the motion there. */}
        <span className="cursor-grab active:cursor-grabbing text-pb-faintest select-none pt-0.5 shrink-0"
          title="Drag to reorder, or onto another agenda item" {...(dragProps?.handle || {})}>⠿</span>
        <div className="min-w-0 flex-1">
          <div className="text-[12.5px] text-pb-text">{motion.description}</div>
          {/* The tally and the plan link read as metadata under the wording,
              not as controls. Both are the answer to "what happened", which is
              what a reader coming back to the minutes wants. */}
          <div className="font-mono text-[9.5px] mt-0.5 flex flex-wrap gap-x-2">
            <span>
              <span style={{ color: TONE.carried }}>{motion.votes_for ?? 0} for</span>
              <span className="text-pb-faintest"> · </span>
              <span style={{ color: TONE.lost }}>{motion.votes_against ?? 0} against</span>
              <span className="text-pb-faintest"> · {motion.votes_abstain ?? 0} abstain</span>
            </span>
            {/* Wraps rather than truncates: a breadcrumb is PLAN › THEME › OBJECTIVE
                and the objective's own title is the part on the end, so an ellipsis
                hides exactly the half that says which objective this is. */}
            <span className="text-pb-faintest min-w-0">{serves ? `serves ${serves}` : 'not on the plan'}</span>
          </div>
          {movers && <div className="font-mono text-[9.5px] text-pb-faintest mt-0.5">{movers}</div>}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <select value={motion.outcome} onChange={e => onChange({ outcome: e.target.value })}
            style={{ color: toneOf(motion.outcome) }}
            className="bg-pb-surface2 border pb-hairline rounded px-1.5 py-1 font-mono text-[9px]">
            {MOTION_OUTCOMES.map(o => <option key={o} value={o}>{titleCase(o)}</option>)}
          </select>
          <button onClick={() => setOpen(o => !o)} aria-expanded={open}
            className="font-mono text-[9px] text-pb-faint hover:text-pb-text">{open ? 'Done' : 'Edit'}</button>
        </div>
      </div>

      {open && (
        <MotionForm motion={motion} present={present} pool={pool} objectives={objectives}
          onChange={onChange} onVotes={onVotes} onDelete={onDelete} />
      )}

      {actions.length > 0 && (
        <div className="mt-2 space-y-1">
          {actions.map(a => (
            <ActionRow key={a.id} action={a} present={present} pool={pool} objectives={objectives}
              nameOf={nameOf} objectiveOf={objectiveOf}
              onChange={p => onActionChange(a.id, p)} onDelete={() => onActionDelete(a.id)} />
          ))}
        </div>
      )}
      {adding ? (
        <ActionForm motionId={motion.id} agendaItemId={motion.agenda_item_id} present={present} pool={pool}
          objectives={objectives} defaultObjectiveId={motion.objective_id}
          onSave={async d => { await onAddAction(d); setAdding(false) }} onCancel={() => setAdding(false)} />
      ) : (
        <button onClick={() => setAdding(true)}
          className="font-mono text-[9px] text-pb-faint hover:text-pb-text mt-1.5">+ Add action</button>
      )}
    </div>
  )
}

/* ── One agenda item ────────────────────────────────────────────────────── */

// THE ITEM IS THE PRIMARY CONTAINER, so its ring is the only heavy edge on
// screen: everything inside it is separated by spacing and tint instead.
function AgendaItem({
  item, index, isCurrent, onOpen, dragProps, present, pool, nameOf, objectives, objectiveOf,
  sections, motions, actions, onItemChange, onItemDelete,
  onAddMotion, onMotionChange, onMotionDelete, onMotionVotes,
  onAddAction, onActionChange, onActionDelete,
  motionDrag,
}) {
  const [motionOpen, setMotionOpen] = useState(false)
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
    <div className="pb-card p-3"
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
            {/* An empty form is not information. It appears when somebody
                actually wants to move something — and then it carries the
                whole record, so the vote is taken here rather than by
                creating the motion and reopening it under Edit. */}
            {motionOpen ? (
              <MotionForm present={present} pool={pool} objectives={objectives}
                onSave={async d => { await onAddMotion(d); setMotionOpen(false) }}
                onCancel={() => setMotionOpen(false)} />
            ) : (
              <button onClick={() => setMotionOpen(true)}
                className="font-mono text-[9px] text-pb-faint hover:text-pb-text mt-2">+ Add motion</button>
            )}
          </div>

          <div>
            <div className={`${cap} mb-1`}>ACTIONS</div>
            <div className="space-y-1">
              {actions.filter(a => !a.motion_id).map(a => (
                <ActionRow key={a.id} action={a} present={present} pool={pool} objectives={objectives}
                  nameOf={nameOf} objectiveOf={objectiveOf}
                  onChange={p => onActionChange(a.id, p)} onDelete={() => onActionDelete(a.id)} />
              ))}
            </div>
            {addingAction ? (
              <ActionForm agendaItemId={item.id} present={present} pool={pool} objectives={objectives}
                onSave={async d => { await onAddAction(d); setAddingAction(false) }}
                onCancel={() => setAddingAction(false)} />
            ) : (
              <button onClick={() => setAddingAction(true)}
                className="font-mono text-[9px] text-pb-faint hover:text-pb-text mt-1">+ Add action</button>
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
//   onMeta       — called on every load with { meeting, setStatus, setTitle,
//                  reload }, so a host that draws the header elsewhere (the
//                  full-page route) can show the title, the status select, and
//                  stay in step with a rename made in the room.
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

  // The two things about the meeting itself this screen changes.
  const setStatus = useCallback(v => {
    api.committeeUpdateMeeting(meetingId, { status: v })
      .then(load)
      .catch(e => toast.error(e.message))
  }, [meetingId, load, toast])

  // Reloads rather than patching the local copy, so the name on screen is the
  // name the server actually stored, and `onMeta` carries it back to whatever
  // list is drawn beside the room.
  const setTitle = useCallback(v => {
    api.committeeUpdateMeeting(meetingId, { title: v })
      .then(load)
      .catch(e => toast.error(e.message))
  }, [meetingId, load, toast])

  // Hand the host what it needs to draw the header where it draws headers.
  // Depends on `data` alone: the callback is a setState from the host and the
  // two functions here are only read, never compared.
  useEffect(() => {
    if (!onMeta) return
    onMeta(data ? { meeting: data.meeting, setStatus, setTitle, reload: load } : null)
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
  const notesRef = useRef(null)
  const [drafting, setDrafting] = useState(false)
  // Whether each box has anything in it, for the download buttons. Null means
  // nobody has touched it, so it follows the record; once typed in it follows
  // the box, which is what stops a reload after some unrelated action reading a
  // flag off minutes the autosave has not sent yet.
  const [minutesTyped, setMinutesTyped] = useState(null)
  const [notesTyped, setNotesTyped] = useState(null)
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
      setMinutesTyped(r.draft)
      await api.committeeUpdateMeeting(meetingId, { minutes: r.draft })
      toast.success('Draft written. Read it before it becomes the record.')
    } catch (e) { toast.error(e.message) } finally { setDrafting(false) }
  }
  const saveNotes = useAutosave(v => api.committeeUpdateMeeting(meetingId, { private_notes: v }).catch(e => toast.error(e.message)))

  // Written from the BOX, never re-fetched from the record: the autosave is
  // 700ms behind, and a download pressed straight after the last sentence has
  // to carry that sentence. The meeting's own name and date ride along, or a
  // file called Minutes.pdf in somebody's downloads folder says nothing about
  // which meeting it came from.
  function downloadField(field, format) {
    const isMinutes = field === 'minutes'
    const text = (isMinutes ? minutesRef.current?.value : notesRef.current?.value) || ''
    if (!text.trim()) return
    const when = shortDate(meeting.scheduled_at)
    const title = meeting.title || 'Meeting'
    const write = format === 'pdf' ? downloadPdf : downloadDocx

    if (isMinutes) {
      // The minutes go out as the club's own document: a details table, the
      // agenda, a numbered section per item carrying its motions with the
      // objective each serves and how everyone voted, then the actions table.
      // Built from the RECORD, so nothing the screen holds can be left out of
      // it by a paragraph that did not happen to mention it.
      write({
        filename: docFilename(title, when, 'Minutes'),
        ...buildMinutesDoc({
          club: data.club, meeting, agendaItems: items, motions, actions,
          attendance, pool, objectives, minutesText: text,
        }),
      })
      return
    }
    write({
      filename: docFilename(title, when, 'Notes'),
      title,
      subtitle: ['Private notes', when, meeting.location,
        // The screen says these are never circulated with the minutes; a file
        // that has left the screen should keep saying it.
        'Not part of the minutes'].filter(Boolean).join(' \u00b7 '),
      body: text,
    })
  }

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
              <EditableHeading value={meeting.title} onSave={setTitle} label="Meeting name" />
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
      {/* minmax(0,1fr), never a bare 1fr: a grid track's automatic minimum is its
          content, so one long unbreakable line in the main column pushes the whole
          grid wider than the pane and drives the rail off the right edge. */}
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-5 items-start">
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
                onAddMotion={wrap(async d => {
                  // The named votes key on the motion's own id, so they can
                  // only be written once it exists. Everything else — the
                  // wording, who moved and seconded it, the outcome and the
                  // objective — goes in the one create.
                  const { votes, ...fields } = d
                  const mo = await api.committeeCreateMotion(meetingId, { ...fields, agenda_item_id: item.id })
                  if (votes?.length && mo?.id) await api.committeeSetMotionVotes(meetingId, mo.id, votes)
                })}
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
              <span className={cap}>
                MINUTES
                <Hint text="Saves as you type. A draft is written from the agenda, motions, votes and actions above, and replaces what is in the box for you to correct. It is never the record until you say so." />
              </span>
              <button onClick={draft} disabled={drafting} className="font-mono text-[9px] text-pb-faint hover:text-pb-text disabled:opacity-40">
                {drafting ? 'drafting…' : 'draft from the meeting'}
              </button>
            </div>
            <textarea ref={minutesRef} className={`${inp} min-h-[120px]`} defaultValue={meeting.minutes || ''}
              placeholder="The record that gets circulated…"
              onChange={e => { setMinutesTyped(e.target.value); saveMinutes(e.target.value) }} />
            <DownloadRow label="the minutes"
              empty={!(minutesTyped ?? meeting.minutes ?? '').trim()}
              onDownload={f => downloadField('minutes', f)} />
          </div>

          <div className="pb-card p-4">
            <div className={`${cap} mb-1.5`}>YOUR NOTES</div>
            <textarea ref={notesRef} className={`${inp} min-h-[80px]`} defaultValue={meeting.private_notes || ''}
              placeholder="Not part of the minutes…"
              onChange={e => { setNotesTyped(e.target.value); saveNotes(e.target.value) }} />
            <DownloadRow label="your notes"
              empty={!(notesTyped ?? meeting.private_notes ?? '').trim()}
              onDownload={f => downloadField('notes', f)} />
            <div className="font-mono text-[9px] text-pb-faintest mt-2">
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
