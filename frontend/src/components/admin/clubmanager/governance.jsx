import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import { PersonSearch } from './pickers'
import { objectiveTiers, objectiveLabel } from './planLabels'

// The editing surface for what migration 217 added: an action's budget, spend,
// progress, plan and dependencies; a carried motion recorded as a resolution
// and the named votes behind it; and notes against any of them.
//
// These live here rather than inside AdminCommittee.jsx because that file is
// already 885 lines and every one of these is reusable — the same note thread
// hangs off an action, a motion, a meeting and an objective.

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const cap = 'font-mono text-[10px] tracking-wide3 text-pb-faintest'
const money = n => `$${Number(n || 0).toLocaleString('en-AU', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

/* ── Notes ──────────────────────────────────────────────────────────────── */

// A note thread against anything. `entityType` is task | motion | meeting |
// objective; the backend validates it, so a typo fails loudly rather than
// writing notes nobody will ever find again.
export function NoteThread({ entityType, entityId, compact = false }) {
  const toast = useToast()
  const [notes, setNotes] = useState(null)
  const [body, setBody] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.committeeListNotes(entityType, entityId)
      .then(d => setNotes(d.notes || []))
      .catch(() => setNotes([]))
  }, [entityType, entityId])
  useEffect(() => { load() }, [load])

  async function add() {
    if (!body.trim()) return
    setBusy(true)
    try { await api.committeeAddNote(entityType, entityId, body.trim()); setBody(''); load() }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove(n) {
    if (!confirm('Delete this note?')) return
    try { await api.committeeDeleteNote(n.id); load() } catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      {!compact && <div className={`${cap} mb-1.5`}>NOTES</div>}
      <div className="space-y-1.5 mb-2">
        {notes === null && <div className="font-mono text-[10px] text-pb-faintest">Loading…</div>}
        {notes?.length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No notes yet.</div>}
        {notes?.map(n => (
          <div key={n.id} className="pb-card px-3 py-2 group">
            <div className="text-pb-text text-[12.5px] leading-relaxed whitespace-pre-wrap">{n.body}</div>
            <div className="flex items-center gap-2 mt-1">
              <span className="font-mono text-[9px] text-pb-faintest">
                {n.created_at ? new Date(n.created_at).toLocaleString() : 'just now'}
              </span>
              <button onClick={() => remove(n)}
                className="font-mono text-[9px] text-pb-faintest hover:text-pb-red ml-auto opacity-0 group-hover:opacity-100 transition">✕</button>
            </div>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <textarea rows={2} className={inp} placeholder="Add a note…" value={body}
          onChange={e => setBody(e.target.value)} />
        <button onClick={add} disabled={busy || !body.trim()}
          className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-40 self-start whitespace-nowrap">
          {busy ? 'Adding…' : '+ Note'}
        </button>
      </div>
    </div>
  )
}

/* ── Documents attached to one record ───────────────────────────────────── */

// Documents stay link-based on purpose: a club's quotes and policies already
// live in Drive or Dropbox, and copying them here would make this the second
// place to look. What changed is that a link can now belong to the action that
// asked for it rather than a general list.
const fileSize = n => {
  if (!n && n !== 0) return ''
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

// Documents against a record — either a link to where the club already keeps
// the file, or the file itself.
//
// The two are deliberately not equivalent. A link is a URL we neither host nor
// can gate, so it opens for anyone who can see the register. An upload is
// served by us and obeys the club's setting, so a row the reader may not open
// shows as locked rather than as a link that 403s when clicked.
export function AttachedDocuments({ entityType, entityId }) {
  const toast = useToast()
  const [docs, setDocs] = useState(null)
  const [restricted, setRestricted] = useState(false)
  const [form, setForm] = useState({ title: '', url: '' })
  const [uploading, setUploading] = useState(false)

  const load = useCallback(() => {
    api.committeeListDocuments()
      .then(d => {
        setDocs((d.documents || []).filter(x => x.entity_type === entityType && x.entity_id === entityId))
        setRestricted(!!d.office_bearer_only)
      })
      .catch(() => setDocs([]))
  }, [entityType, entityId])
  useEffect(() => { load() }, [load])

  async function add() {
    if (!form.title.trim() || !form.url.trim()) return
    try {
      await api.committeeCreateDocument({ ...form, entity_type: entityType, entity_id: entityId })
      setForm({ title: '', url: '' }); load()
    } catch (e) { toast.error(e.message) }
  }

  async function upload(file) {
    if (!file) return
    setUploading(true)
    try {
      // The typed title is used when there is one, so an upload can be called
      // "Netpro quote" rather than "scan_0043.pdf".
      await api.committeeUploadDocument(file, {
        title: form.title.trim(), entity_type: entityType, entity_id: entityId,
      })
      setForm({ title: '', url: '' }); load()
    } catch (e) { toast.error(e.message) } finally { setUploading(false) }
  }

  return (
    <div>
      <div className={`${cap} mb-1.5`}>DOCUMENTS</div>
      <div className="space-y-1 mb-2">
        {docs?.length === 0 && <div className="font-mono text-[10px] text-pb-faintest">Nothing attached.</div>}
        {docs?.map(d => {
          if (!d.has_file) {
            return (
              <a key={d.id} href={d.url} target="_blank" rel="noreferrer"
                className="block text-[12.5px] underline truncate" style={{ color: 'var(--pb-accent)' }}>{d.title}</a>
            )
          }
          if (!d.can_open) {
            return (
              <div key={d.id} className="flex items-center gap-2 text-[12.5px] text-pb-faint">
                <span aria-hidden>🔒</span>
                <span className="truncate">{d.title}</span>
                <span className="font-mono text-[10px] text-pb-faintest shrink-0">office bearers only</span>
              </div>
            )
          }
          return (
            <div key={d.id} className="flex items-center gap-2 text-[12.5px]">
              <a href={api.committeeDocumentFileUrl(d.id)} target="_blank" rel="noreferrer"
                className="underline truncate" style={{ color: 'var(--pb-accent)' }}>{d.title}</a>
              <span className="font-mono text-[10px] text-pb-faintest shrink-0">{fileSize(d.file_size)}</span>
              <a href={api.committeeDocumentFileUrl(d.id, { download: true })}
                className="font-mono text-[10px] text-pb-faint hover:text-pb-text shrink-0">download</a>
            </div>
          )
        })}
      </div>
      {/* Wraps rather than squeezing: this panel sits inside a ~230px kanban
          column on the Actions board, where a single flex row crushed both
          inputs to a few pixels wide. */}
      <div className="flex flex-wrap gap-2">
        <input className={`${inp} flex-1 min-w-[9rem]`} placeholder="e.g. Netpro quote" value={form.title}
          onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <input className={`${inp} flex-1 min-w-[9rem]`} placeholder="https://… (or upload below)" value={form.url}
          onChange={e => setForm(f => ({ ...f, url: e.target.value }))} />
        <div className="flex gap-2 shrink-0">
          <button onClick={add} disabled={!form.title.trim() || !form.url.trim()}
            className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-40 whitespace-nowrap">+ Link</button>
          <label className={`px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline whitespace-nowrap cursor-pointer
            ${uploading ? 'opacity-40' : 'text-pb-faint hover:text-pb-text'}`}>
            {uploading ? 'Uploading…' : '↑ Upload'}
            <input type="file" className="hidden" disabled={uploading}
              onChange={e => { upload(e.target.files?.[0]); e.target.value = '' }} />
          </label>
        </div>
      </div>
      {restricted && (
        <div className="font-mono text-[10px] text-pb-faintest mt-1.5">
          Uploads open only to office bearers, whoever uploaded them, and the main admin. Links stay open to the committee.
        </div>
      )}
    </div>
  )
}

/* ── One action, opened for editing ─────────────────────────────────────── */

// An editor is a dialog when it is opened over a list, and plain content when
// it IS the pane — the Strategic Plans tree opens an action in the detail pane
// beside it, where an overlay would be a dialog over nothing.
function EditorShell({ inline, onClose, busy, children }) {
  if (inline) return <div className="space-y-4">{children}</div>
  return (
    <div onClick={() => { if (!busy) onClose?.() }}
      className="fixed inset-0 z-[120] flex items-start justify-center overflow-y-auto p-4 sm:p-8"
      style={{ background: 'rgba(0,0,0,0.55)' }}>
      <div onClick={e => e.stopPropagation()} className="pb-card w-full max-w-3xl p-5 space-y-4">
        {children}
      </div>
    </div>
  )
}

// The vocabulary an action is filed under, in ONE place. The board, the list,
// the timeline and this editor all read these, so a status added here shows up
// everywhere rather than in whichever screen was edited last.
export const ACTION_CATEGORIES = ['operational', 'maintenance', 'compliance', 'finance', 'other']
export const ACTION_STATUSES = ['todo', 'in_progress', 'done', 'blocked']
export const ACTION_STATUS_LABELS = { todo: 'To Do', in_progress: 'In Progress', done: 'Done', blocked: 'Blocked' }
const catLabel = s => s.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

// What an action is FOR, said in one line rather than left to a dropdown.
//
// An objective is three tiers deep (plan › theme › objective) and the old
// inline panel showed only the picker, which meant the linkage — the single
// most useful thing about an action serving the strategic plan — was readable
// only by opening the dropdown and reading which row happened to be selected.
// Here it is a breadcrumb, with what the club committed to underneath it.
function ObjectiveLink({ objective, noun = 'ACTION' }) {
  if (!objective) {
    return (
      <div className="pb-card p-3">
        <div className={`${cap} mb-1`}>STRATEGIC PLAN</div>
        <div className="text-[12.5px] text-pb-faint">
          Not linked yet. Point it at an objective below and this {noun.toLowerCase()} starts counting towards the plan.
        </div>
      </div>
    )
  }
  const tiers = objectiveTiers(objective)
  const meta = [
    objective.owner_position_name ? `Owned by the ${objective.owner_position_name}` : null,
    objective.due_date ? `Due ${objective.due_date}` : null,
    objective.budget != null ? `${money(objective.budget)} allocated` : null,
  ].filter(Boolean)
  return (
    <div className="pb-card p-3" style={{ borderColor: 'color-mix(in srgb, var(--pb-accent) 35%, transparent)' }}>
      <div className={`${cap} mb-2`}>THIS {noun} SERVES</div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {tiers.map(({ key: k, value: v }, i) => (
          <span key={k} className="flex items-center gap-2">
            {i > 0 && <span className="text-pb-faintest text-[13px]">›</span>}
            <span className="flex flex-col">
              <span className={cap}>{k}</span>
              <span className={`text-[13px] ${i === tiers.length - 1 ? 'text-pb-text font-semibold' : 'text-pb-dim'}`}>{v}</span>
            </span>
          </span>
        ))}
      </div>
      {meta.length > 0 && (
        <div className="font-mono text-[10px] text-pb-faintest mt-2">{meta.join(' · ')}</div>
      )}
    </div>
  )
}

// The whole of one action, in a dialog with room to lay it out.
//
// It replaces the panel that used to unfold inside a board card: a two-column
// grid of dates and money in a 200px-wide column, which is why it read as a
// jumble. Opened from the list, the board and the timeline alike, so there is
// one place an action is edited however you reached it.
export function ActionEditor({ task, allTasks, objectives, members, inline, onClose, onSaved, onDeleted }) {
  const toast = useToast()
  const [form, setForm] = useState({
    title: task.title || '',
    description: task.description || '',
    category: task.category || 'operational',
    status: task.status || 'todo',
    objective_id: task.objective_id || '',
    budget_estimate: task.budget_estimate ?? '',
    actual_expenditure: task.actual_expenditure ?? '',
    percent_complete: task.percent_complete ?? 0,
    start_date: task.start_date || '',
    due_date: task.due_date || '',
    assigned_to_member_id: task.assigned_to_member_id || '',
    outcome_notes: task.outcome_notes || '',
  })
  const [deps, setDeps] = useState(task.depends_on || [])
  const [busy, setBusy] = useState(false)

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const num = v => (v === '' || v === null ? null : Number(v))

  async function save() {
    if (!form.title.trim()) { toast.error('An action needs a title'); return }
    setBusy(true)
    try {
      await api.committeeUpdateTask(task.id, {
        title: form.title.trim(),
        description: form.description || null,
        category: form.category,
        status: form.status,
        objective_id: form.objective_id || null,
        budget_estimate: num(form.budget_estimate),
        actual_expenditure: num(form.actual_expenditure),
        // Marking it done means done, so the progress bar stops disagreeing
        // with the status pill above it.
        percent_complete: form.status === 'done' ? 100 : (Number(form.percent_complete) || 0),
        start_date: form.start_date || null,
        due_date: form.due_date || null,
        assigned_to_member_id: form.assigned_to_member_id || null,
        outcome_notes: form.outcome_notes || null,
      })
      await api.committeeSetTaskDependencies(task.id, deps)
      toast.success('Action updated')
      onSaved?.()
      onClose?.()
    } catch (e) { toast.error(e.message); setBusy(false) }
  }

  async function remove() {
    // Deleting takes the action's notes and attachments with it, so it says so
    // rather than asking "are you sure?" about something unnamed.
    if (!window.confirm(`Delete "${task.title}"?\n\nIts notes and attached documents go with it. This can't be undone.`)) return
    setBusy(true)
    try {
      await api.committeeDeleteTask(task.id)
      toast.success('Action deleted')
      onDeleted?.()
      onClose?.()
    } catch (e) { toast.error(e.message); setBusy(false) }
  }

  const objective = (objectives || []).find(o => o.id === form.objective_id) || null
  const over = form.budget_estimate !== '' && Number(form.actual_expenditure || 0) > Number(form.budget_estimate)
  const candidates = (allTasks || []).filter(t => t.id !== task.id)
  const blockers = candidates.filter(t => deps.includes(t.id) && t.status !== 'done')

  return (
    <EditorShell inline={inline} onClose={onClose} busy={busy}>
        <div className="flex items-start gap-3">
          <label className="flex-1 min-w-0 block">
            <span className={`${cap} block mb-1`}>ACTION</span>
            <input className={`${inp} !text-[15px] !py-2`} value={form.title}
              onChange={e => set('title', e.target.value)} placeholder="What has to happen" />
          </label>
          {!inline && (
            <button onClick={() => { if (!busy) onClose?.() }} aria-label="Close"
              className="text-pb-faint hover:text-pb-text text-[15px] leading-none px-1 pt-6">✕</button>
          )}
        </div>

        <div>
          <div className={`${cap} mb-1`}>STATUS</div>
          <div className="flex flex-wrap gap-1">
            {ACTION_STATUSES.map(s => (
              <button key={s} onClick={() => set('status', s)}
                className={`px-3 py-1.5 rounded text-[12.5px] border ${form.status === s ? 'text-pb-text' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
                style={form.status === s
                  ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' }
                  : undefined}>
                {ACTION_STATUS_LABELS[s]}
              </button>
            ))}
          </div>
        </div>

        <ObjectiveLink objective={objective} />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <ObjectiveSelect objectives={objectives} value={form.objective_id}
            onChange={v => set('objective_id', v || '')} />
          <label className="block">
            <span className={`${cap} block mb-1`}>RESPONSIBLE</span>
            <select className={inp} value={form.assigned_to_member_id}
              onChange={e => set('assigned_to_member_id', e.target.value)}>
              <option value="">— unassigned —</option>
              {(members || []).map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className={`${cap} block mb-1`}>CATEGORY</span>
            <select className={inp} value={form.category} onChange={e => set('category', e.target.value)}>
              {ACTION_CATEGORIES.map(c => <option key={c} value={c}>{catLabel(c)}</option>)}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className={`${cap} block mb-1`}>STARTS</span>
              <input type="date" className={inp} value={form.start_date}
                onChange={e => set('start_date', e.target.value)} />
            </label>
            <label className="block">
              <span className={`${cap} block mb-1`}>DUE</span>
              <input type="date" className={inp} value={form.due_date}
                onChange={e => set('due_date', e.target.value)} />
            </label>
          </div>
          <label className="block">
            <span className={`${cap} block mb-1`}>BUDGET</span>
            <input type="number" step="0.01" className={inp} placeholder="0.00" value={form.budget_estimate}
              onChange={e => set('budget_estimate', e.target.value)} />
          </label>
          <label className="block">
            <span className={`${cap} block mb-1`}>SPENT SO FAR</span>
            <input type="number" step="0.01" className={inp} placeholder="0.00" value={form.actual_expenditure}
              onChange={e => set('actual_expenditure', e.target.value)} />
          </label>
        </div>

        {over && (
          <div className="font-mono text-[10px] text-pb-amber">
            Over budget by {money(Number(form.actual_expenditure) - Number(form.budget_estimate))}.
          </div>
        )}

        <label className="block">
          <span className={`${cap} block mb-1`}>PROGRESS · {form.status === 'done' ? 100 : form.percent_complete}%</span>
          <input type="range" min="0" max="100" step="5" className="w-full accent-pb-accent"
            disabled={form.status === 'done'}
            value={form.status === 'done' ? 100 : form.percent_complete}
            onChange={e => set('percent_complete', e.target.value)} />
        </label>

        <label className="block">
          <span className={`${cap} block mb-1`}>DETAIL</span>
          <textarea rows={2} className={inp} placeholder="Anything the committee needs to know before it starts."
            value={form.description} onChange={e => set('description', e.target.value)} />
        </label>

        <div>
          <div className={`${cap} mb-1`}>WAITS ON</div>
          {candidates.length === 0 ? (
            <div className="font-mono text-[10px] text-pb-faintest">No other actions to depend on yet.</div>
          ) : (
            <div className="max-h-32 overflow-y-auto space-y-0.5 pr-1">
              {candidates.map(t => (
                <label key={t.id} className="flex items-center gap-2 text-[12.5px] text-pb-dim cursor-pointer">
                  <input type="checkbox" className="accent-pb-accent" checked={deps.includes(t.id)}
                    onChange={e => setDeps(d => e.target.checked ? [...d, t.id] : d.filter(x => x !== t.id))} />
                  <span className="truncate">{t.title}</span>
                  {t.status === 'done' && <span className="font-mono text-[8px] text-pb-positive">DONE</span>}
                </label>
              ))}
            </div>
          )}
          {blockers.length > 0 && (
            <div className="font-mono text-[10px] text-pb-amber mt-1">
              Blocked — {blockers.length} {blockers.length === 1 ? 'action it waits on is' : 'actions it waits on are'} still open.
            </div>
          )}
        </div>

        <label className="block">
          <span className={`${cap} block mb-1`}>OUTCOME</span>
          <textarea rows={2} className={inp} placeholder="What actually happened, once it's done."
            value={form.outcome_notes} onChange={e => set('outcome_notes', e.target.value)} />
        </label>

        <div className="pb-card p-3"><NoteThread entityType="task" entityId={task.id} /></div>
        <div className="pb-card p-3"><AttachedDocuments entityType="task" entityId={task.id} /></div>

        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={save} disabled={busy || !form.title.trim()}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-50"
            style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
            {busy ? 'SAVING…' : 'SAVE'}
          </button>
          {!inline && (
            <button onClick={() => { if (!busy) onClose?.() }} disabled={busy}
              className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">
              Cancel
            </button>
          )}
          <button onClick={remove} disabled={busy}
            className="px-3 py-2 rounded font-mono text-[10px] border text-pb-red hover:text-pb-text ml-auto"
            style={{ borderColor: 'color-mix(in srgb, var(--pb-red) 40%, transparent)' }}>
            Delete action
          </button>
        </div>
    </EditorShell>
  )
}

/* ── One motion, opened for editing ─────────────────────────────────────── */

// What a motion can end as. The meeting room, the manage screen and this editor
// all read this list, so the vocabulary has one home.
export const MOTION_OUTCOMES = ['pending', 'carried', 'lost', 'withdrawn']
const outcomeLabel = s => s.charAt(0).toUpperCase() + s.slice(1)

// The motion register is a read of every motion the club has passed, and until
// now that was all it was — a typo in a resolution could only be corrected by
// finding the meeting it was moved at. A motion belongs to its meeting, so the
// meeting's id rides along with the row and every write goes to that meeting's
// own endpoint.
export function MotionEditor({ meetingId, motion, members, objectives, inline, onClose, onSaved, onDeleted }) {
  const toast = useToast()
  const [form, setForm] = useState({
    description: motion.description || '',
    outcome: motion.outcome || 'pending',
    votes_for: motion.votes_for ?? '',
    votes_against: motion.votes_against ?? '',
    votes_abstain: motion.votes_abstain ?? '',
    proposed_by_member_id: motion.proposed_by_member_id || '',
    seconded_by_member_id: motion.seconded_by_member_id || '',
    objective_id: motion.objective_id || '',
    notes: motion.notes || '',
  })
  const [busy, setBusy] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const num = v => (v === '' || v === null ? null : Number(v))

  async function save() {
    if (!form.description.trim()) { toast.error('A motion needs its wording'); return }
    setBusy(true)
    try {
      await api.committeeUpdateMotion(meetingId, motion.id, {
        description: form.description.trim(),
        outcome: form.outcome,
        votes_for: num(form.votes_for),
        votes_against: num(form.votes_against),
        votes_abstain: num(form.votes_abstain),
        proposed_by_member_id: form.proposed_by_member_id || null,
        seconded_by_member_id: form.seconded_by_member_id || null,
        objective_id: form.objective_id || null,
        notes: form.notes || null,
      })
      toast.success('Motion updated')
      onSaved?.()
      onClose?.()
    } catch (e) { toast.error(e.message); setBusy(false) }
  }

  async function remove() {
    // A motion is the record of a decision the committee took, so this names
    // what it is rather than asking about an unnamed row.
    if (!window.confirm(`Delete this motion?\n\n“${motion.description}”\n\nIts votes and notes go with it. This can't be undone.`)) return
    setBusy(true)
    try {
      await api.committeeDeleteMotion(meetingId, motion.id)
      toast.success('Motion deleted')
      onDeleted?.()
      onClose?.()
    } catch (e) { toast.error(e.message); setBusy(false) }
  }

  const objective = (objectives || []).find(o => o.id === form.objective_id) || null

  return (
    <EditorShell inline={inline} onClose={onClose} busy={busy}>
        <div className="flex items-start gap-3">
          <label className="flex-1 min-w-0 block">
            <span className={`${cap} block mb-1`}>MOTION</span>
            <textarea rows={2} className={`${inp} !text-[14px]`} value={form.description}
              onChange={e => set('description', e.target.value)}
              placeholder="That the committee…" />
          </label>
          {!inline && (
            <button onClick={() => { if (!busy) onClose?.() }} aria-label="Close"
              className="text-pb-faint hover:text-pb-text text-[15px] leading-none px-1 pt-6">✕</button>
          )}
        </div>

        <div>
          <div className={`${cap} mb-1`}>OUTCOME</div>
          <div className="flex flex-wrap gap-1">
            {MOTION_OUTCOMES.map(s => (
              <button key={s} onClick={() => set('outcome', s)}
                className={`px-3 py-1.5 rounded text-[12.5px] border ${form.outcome === s ? 'text-pb-text' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
                style={form.outcome === s
                  ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' }
                  : undefined}>
                {outcomeLabel(s)}
              </button>
            ))}
          </div>
        </div>

        <ObjectiveLink objective={objective} noun="MOTION" />

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <ObjectiveSelect objectives={objectives} value={form.objective_id}
            onChange={v => set('objective_id', v || '')} />
          <div />
          <label className="block">
            <span className={`${cap} block mb-1`}>MOVED BY</span>
            <select className={inp} value={form.proposed_by_member_id}
              onChange={e => set('proposed_by_member_id', e.target.value)}>
              <option value="">— nobody recorded —</option>
              {(members || []).map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className={`${cap} block mb-1`}>SECONDED BY</span>
            <select className={inp} value={form.seconded_by_member_id}
              onChange={e => set('seconded_by_member_id', e.target.value)}>
              <option value="">— nobody recorded —</option>
              {(members || []).map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
            </select>
          </label>
        </div>

        <div className="grid grid-cols-3 gap-3">
          {[['votes_for', 'FOR'], ['votes_against', 'AGAINST'], ['votes_abstain', 'ABSTAIN']].map(([k, l]) => (
            <label key={k} className="block">
              <span className={`${cap} block mb-1`}>{l}</span>
              <input type="number" min="0" className={inp} value={form[k]}
                onChange={e => set(k, e.target.value)} placeholder="—" />
            </label>
          ))}
        </div>

        <label className="block">
          <span className={`${cap} block mb-1`}>NOTE FOR THE MINUTES</span>
          <textarea rows={2} className={inp} placeholder="Anything the minutes should carry alongside it."
            value={form.notes} onChange={e => set('notes', e.target.value)} />
        </label>

        {/* The committee's own thread against this motion — a different thing
            from the line above, which goes into the minutes. */}
        <div className="pb-card p-3"><NoteThread entityType="motion" entityId={motion.id} /></div>

        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={save} disabled={busy || !form.description.trim()}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-50"
            style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
            {busy ? 'SAVING…' : 'SAVE'}
          </button>
          {!inline && (
            <button onClick={() => { if (!busy) onClose?.() }} disabled={busy}
              className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">
              Cancel
            </button>
          )}
          <button onClick={remove} disabled={busy}
            className="px-3 py-2 rounded font-mono text-[10px] border text-pb-red hover:text-pb-text ml-auto"
            style={{ borderColor: 'color-mix(in srgb, var(--pb-red) 40%, transparent)' }}>
            Delete motion
          </button>
        </div>
    </EditorShell>
  )
}

/* ── A motion's votes and resolution status ─────────────────────────────── */

const VOTE_OPTS = [['for', 'For'], ['against', 'Against'], ['abstain', 'Abstain']]

export function MotionGovernance({ meeting, motion, members, onChanged }) {
  const toast = useToast()
  const [votes, setVotes] = useState(() =>
    Object.fromEntries((motion.votes || []).map(v => [v.member_id, v.vote])))
  const [ref, setRef] = useState(motion.resolution_ref || '')
  const [busy, setBusy] = useState(false)
  const [openVotes, setOpenVotes] = useState(false)

  const carried = ['carried', 'passed'].includes((motion.outcome || '').toLowerCase())
  const cast = Object.values(votes).filter(Boolean)

  async function saveVotes() {
    setBusy(true)
    try {
      await api.committeeSetMotionVotes(meeting.id, motion.id,
        Object.entries(votes).filter(([, v]) => v).map(([member_id, vote]) => ({ member_id, vote })))
      toast.success('Votes recorded')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function toggleResolution() {
    setBusy(true)
    try {
      await api.committeeSetResolution(meeting.id, motion.id, {
        resolution_ref: ref.trim() || null, on: !motion.is_resolution,
      })
      toast.success(motion.is_resolution ? 'No longer a resolution' : 'Recorded as a resolution')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="mt-1.5 pt-1.5 border-t pb-hairline no-print">
      <div className="flex items-center gap-2 flex-wrap">
        <button onClick={() => setOpenVotes(o => !o)}
          className="font-mono text-[9px] tracking-wide2 border pb-hairline rounded px-1.5 py-px text-pb-faint hover:text-pb-text">
          {openVotes ? 'Hide votes' : cast.length ? `Votes (${cast.length} named)` : 'Record votes'}
        </button>

        {motion.is_resolution ? (
          <span className="font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border"
            style={{ color: 'var(--pb-accent-ink)', borderColor: 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' }}>
            RESOLUTION{motion.resolution_ref ? ` · ${motion.resolution_ref}` : ''}
          </span>
        ) : carried && (
          <>
            <input className="bg-pb-surface2 border pb-hairline rounded px-2 py-0.5 text-[11px] text-pb-text w-28 focus:outline-none focus:border-pb-accent"
              placeholder="Ref e.g. R2026-04" value={ref} onChange={e => setRef(e.target.value)} />
            <button onClick={toggleResolution} disabled={busy}
              className="font-mono text-[9px] tracking-wide2 border rounded px-1.5 py-px disabled:opacity-50"
              style={{ color: 'var(--pb-accent-ink)', borderColor: 'color-mix(in srgb, var(--pb-accent) 45%, transparent)' }}>
              Make it a resolution
            </button>
          </>
        )}
        {motion.is_resolution && (
          <button onClick={toggleResolution} disabled={busy}
            className="font-mono text-[9px] text-pb-faintest hover:text-pb-red">undo</button>
        )}
        {!carried && !motion.is_resolution && (
          <span className="font-mono text-[9px] text-pb-faintest">A motion has to carry before it can be a resolution.</span>
        )}
      </div>

      {openVotes && (
        <div className="mt-2 pb-card p-3">
          <div className={`${cap} mb-2`}>WHO VOTED WHICH WAY</div>
          <div className="max-h-56 overflow-y-auto space-y-1 pr-1">
            {(members || []).map(m => (
              <div key={m.member_id} className="flex items-center gap-2">
                <span className="text-[12.5px] text-pb-dim flex-1 truncate">{m.full_name}</span>
                {VOTE_OPTS.map(([v, l]) => (
                  <button key={v}
                    onClick={() => setVotes(s => ({ ...s, [m.member_id]: s[m.member_id] === v ? '' : v }))}
                    className={`font-mono text-[8px] tracking-wide2 border rounded px-1.5 py-px ${votes[m.member_id] === v ? 'text-pb-text' : 'text-pb-faintest pb-hairline hover:text-pb-faint'}`}
                    style={votes[m.member_id] === v
                      ? { borderColor: 'var(--pb-accent)', background: 'color-mix(in srgb, var(--pb-accent) 14%, transparent)' }
                      : undefined}>
                    {l}
                  </button>
                ))}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 mt-2">
            <button onClick={saveVotes} disabled={busy}
              className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-50"
              style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
              {busy ? 'SAVING…' : 'SAVE VOTES'}
            </button>
            <span className="font-mono text-[9px] text-pb-faintest">
              Recording names re-derives the tallies. Leave it empty and the counts you typed stand.
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

/* ── Strategic plans → objectives → actions and motions ─────────────────── */

// Three levels, and the screen reads top down: the club's plans, the objectives
// in each, and the actions and motions serving each objective. Every figure
// here is derived from the action register the committee already keeps, so
// correcting an action's spend moves its objective and its plan in the same
// breath — there is no second set of numbers to keep in step.

const pct = n => (n === null || n === undefined ? '—' : `${n}%`)
const AMBER = '#f5b542'
// What the club allocated to this objective itself, as opposed to the effective
// budget a rolled-up row carries (which falls back to the sum of its actions').
const ownBudget = o => ('own_budget' in o ? o.own_budget : o.budget)

// Three levels, and the page has to read as three levels. Each one steps in
// from the left behind its own rail and takes a weaker share of the accent, so
// depth is legible at a glance instead of every card looking equally important.
//
// The rails are `color-mix`, not `${accent}66` — the accent resolves to a
// var(), and a hex suffix on a var() is not a colour, so the border silently
// disappears (the same trap `chip()` documents).
const mix = (pctAccent, base = 'transparent') =>
  `color-mix(in srgb, var(--pb-accent) ${pctAccent}%, ${base})`

// The figures step down the same way the rails do, so a plan's numbers read
// louder than its objectives' and an objective's louder than its actions'.
// Mixed towards the body colour rather than switched to a different hue: they
// are the same kind of figure, just less of the club's accent each time.
const LEVEL = {
  plan: {
    rail: mix(75), tint: 'transparent',
    figure: 'var(--pb-accent-ink)', size: 'text-[19px]',
  },
  objective: {
    rail: mix(42), tint: mix(5, 'var(--pb-surface2)'),
    figure: 'color-mix(in srgb, var(--pb-accent-ink) 66%, var(--pb-dim))', size: 'text-[15px]',
  },
  work: {
    rail: mix(22), tint: 'transparent',
    figure: 'var(--pb-dim)', size: 'text-[13px]',
  },
}

// The step-in itself. Modest at 390px, where a deep indent would cost more
// reading width than the structure is worth.
function Nested({ level, children, className = '' }) {
  const L = LEVEL[level]
  return (
    <div className={`ml-2 sm:ml-4 pl-3 sm:pl-4 border-l-2 rounded-l-none ${className}`}
      style={{ borderColor: L.rail }}>
      {children}
    </div>
  )
}

// "Raised at the March committee, 4 Mar 2026" — the context that turns a line
// of a plan into something a committee recognises.
function RaisedAt({ title, date, verb = 'Raised at' }) {
  if (!title && !date) return null
  const when = date ? new Date(date).toLocaleDateString(undefined,
    { day: 'numeric', month: 'short', year: 'numeric' }) : null
  return (
    <span className="font-mono text-[9px] text-pb-faintest">
      {verb} {title || 'a meeting'}{when ? ` · ${when}` : ''}
    </span>
  )
}

function Bar({ percent, tone }) {
  return (
    <div className="h-1.5 rounded bg-pb-surface2 overflow-hidden">
      <div className="h-full" style={{
        width: `${Math.max(0, Math.min(100, percent || 0))}%`,
        background: tone || 'var(--pb-accent)',
      }} />
    </div>
  )
}

// Progress, spend against what was allocated, and whether it has run late —
// the three questions asked of anything on a plan, in one strip. `level` sets
// how loudly it reads, so an objective's figures do not compete with its plan's.
function Delivery({ row, level = 'objective' }) {
  const L = LEVEL[level]
  const spendTone = row.over_budget ? AMBER : 'var(--pb-accent)'
  const stats = [
    { v: `${row.actions_done}/${row.actions}`, l: 'ACTIONS DONE' },
    { v: pct(row.percent_complete), l: 'PROGRESS' },
    { v: money(row.budget), l: 'BUDGET' },
    { v: money(row.spent), l: 'SPENT', warn: row.over_budget },
  ]
  return (
    <div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
        {stats.map(s => (
          <div key={s.l}>
            <div className={`font-display font-bold pb-num ${L.size}`}
              style={{ color: s.warn ? AMBER : L.figure }}>{s.v}</div>
            <div className={cap}>{s.l}</div>
          </div>
        ))}
      </div>
      <div className="mt-2 space-y-1">
        <Bar percent={row.percent_complete} />
        {row.budget > 0 && (
          <div className="flex items-center gap-2">
            <div className="flex-1"><Bar percent={row.percent_spent} tone={spendTone} /></div>
            <span className="font-mono text-[9px] shrink-0"
              style={{ color: row.over_budget ? AMBER : 'var(--pb-faintest)' }}>
              {pct(row.percent_spent)} of budget spent
            </span>
          </div>
        )}
      </div>
    </div>
  )
}


/* ── How the plan is actually going ─────────────────────────────────────── */

// A committee dashboard, not a dump of everything filed against the plan. It
// answers three questions in the order a meeting asks them: are we delivering
// the plan, are we on time and on budget, and what needs attention. Everything
// else is one click deeper.
//
// THE OBJECTIVE IS THE UNIT, NOT THE ACTION. An objective is what the committee
// committed to; an action is how. The first cut of this screen drew both with
// the same card, so a reader had to work out which was which — the uniformity
// was deliberate (compare like with like) and wrong, because a committee scans
// before it analyses.
//
// EVERY STATE IS A GLYPH AND A WORD, and the colour is third. Checked rather
// than assumed: the green and the amber this app uses separate by ΔE 7.2 under
// protanopia, inside the band that is only legal with a second channel, and in
// the light theme the red and the amber are ΔE 14 apart for a reader with FULL
// colour vision. So nothing here is told apart by colour alone.
//
// SILENCE WHERE THE CLUB'S DATA CANNOT ANSWER — and silence means MUTED, not a
// badge. An action with no dates has no elapsed fraction, so it gets a quiet
// "no dates set" under the bar rather than a chip competing with the real
// verdicts. The first cut rendered that silence as a chip, which is the
// opposite of silent.

const POSITIVE = 'var(--pb-positive-ink)'
const RED = 'var(--pb-red-ink)'

// How far behind the clock is worth calling out. A plan is not a project
// schedule and a committee is not a contractor, so an action a day behind is
// drift rather than a problem — without a tolerance almost everything reads
// BEHIND and the colour stops meaning anything. Ten points is a deliberate
// choice, not a measurement; change it here and every level moves with it.
const DRIFT_TOLERANCE = 10
// The same idea for money: spend runs ahead of progress all the time (you buy
// the materials before you lay them), so only a real gap is worth flagging.
const SPEND_TOLERANCE = 15

const startOfToday = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.getTime() }

// Where a piece of work should be by now, as a percentage of its own span.
// Null when it cannot be worked out — no start, no due, or a span that ends
// before it begins. A missing answer is not a zero.
function elapsedPercent(startISO, dueISO, today) {
  if (!startISO || !dueISO) return null
  const s = Date.parse(startISO), d = Date.parse(dueISO)
  if (!Number.isFinite(s) || !Number.isFinite(d) || d <= s) return null
  return Math.max(0, Math.min(100, Math.round(((today - s) / (d - s)) * 100)))
}

// The vocabulary. `rank` is what a roll-up sorts on, so the worst thing under a
// theme is the thing the theme reports. `glyph` is the second channel the
// colour measurements above make necessary.
const STATE = {
  done: { label: 'DONE', glyph: '✓', tone: POSITIVE, rank: 0 },
  on_track: { label: 'ON TRACK', glyph: '●', tone: POSITIVE, rank: 1 },
  // `rank` is the severity a roll-up sorts on. NOT STARTED carries none: it
  // is an absence, not a problem, and `rollUp` takes it out of the comparison
  // entirely — see there.
  not_started: { label: 'NOT STARTED', glyph: '○', tone: null, rank: 0 },
  behind: { label: 'BEHIND', glyph: '●', tone: AMBER, rank: 3 },
  late: { label: 'LATE', glyph: '●', tone: RED, rank: 4 },
}

// One action's verdict, and the point on its own bar where it should have got
// to by now.
function actionState(a, today) {
  const percent = a.percent_complete || 0
  if ((a.status || '') === 'done' || percent >= 100) return { key: 'done', target: null, percent: 100 }
  const due = a.due_date ? Date.parse(a.due_date) : null
  if (due && Number.isFinite(due) && due < today) return { key: 'late', target: 100, percent }
  const target = elapsedPercent(a.start_date, a.due_date, today)
  // No dates is not a status, it is missing metadata. An action nobody has
  // started and nobody has dated reads NOT STARTED; one with work on it and no
  // dates reads ON TRACK, because there is nothing to say it is not.
  if (target === null) return { key: percent > 0 ? 'on_track' : 'not_started', target: null, percent }
  return { key: percent + DRIFT_TOLERANCE < target ? 'behind' : 'on_track', target, percent }
}

// A group's verdict is the WORST of the things under it — a theme is late if
// any action serving it is late, and done only when every one is. Rolling up
// this way is what makes a theme's figure mean the same thing as an action's,
// and lets the headline be traced to the work dragging it.
function rollUp(keys) {
  if (!keys.length) return 'not_started'
  // NOT STARTED IS AN ABSENCE, NOT A SEVERITY, and taking it out of the
  // comparison is the whole point. It used to outrank ON TRACK, so a theme at
  // 43% with two objectives going well read NOT STARTED because a third had
  // not begun — reported off a live screen. It only wins when nothing under it
  // has begun at all.
  const begun = keys.filter(k => k !== 'not_started')
  if (!begun.length) return 'not_started'
  const worst = begun.reduce((w, k) => (STATE[k].rank > STATE[w].rank ? k : w), 'done')
  // Everything that HAS begun is finished, but something has not begun yet:
  // the theme is not DONE, it is simply going well so far.
  if (worst === 'done' && begun.length < keys.length) return 'on_track'
  return worst
}

// Spend against what was allocated. Null when nothing is allocated: "0 of 0" is
// not an answer, and a club that budgets at the plan level rather than per
// action should not be told its actions are all under budget.
function budgetState(budget, spent, progress) {
  const b = Number(budget || 0)
  if (!b) return null
  const s = Number(spent || 0)
  const percentSpent = Math.round((s / b) * 100)
  if (s > b) return { label: 'over budget', tone: RED, percentSpent, over: true }
  if (percentSpent > (progress || 0) + SPEND_TOLERANCE) {
    return { label: 'spending ahead', tone: AMBER, percentSpent }
  }
  return { label: null, tone: null, percentSpent }
}

// The variance, said out loud. On a scanning surface a sentence beats a mark
// the reader has to interpret — "18% behind" needs no key, where an upright
// tick needs a paragraph explaining it (which is what the first cut had to
// print above the whole screen). The tick survives one level down, on the
// action detail, where the reader has already chosen to look closely.
function scheduleVariance(percent, target) {
  if (target === null || target === undefined) return null
  const gap = Math.round((percent || 0) - target)
  if (Math.abs(gap) < DRIFT_TOLERANCE) return null
  return gap > 0 ? `${gap}% ahead` : `${Math.abs(gap)}% behind`
}

const shortDate = iso => {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

// The state, as a glyph and a word. Never colour on its own.
function StateTag({ state, size = 'sm' }) {
  const st = STATE[state]
  if (!st) return null
  const tone = st.tone || 'var(--pb-faintest)'
  return (
    <span className={`font-mono tracking-wide2 shrink-0 whitespace-nowrap ${size === 'sm' ? 'text-[8.5px]' : 'text-[9.5px]'}`}
      style={{ color: tone }}>
      <span aria-hidden="true">{st.glyph}</span> {st.label}
    </span>
  )
}

// A plain progress track. No target mark: on the scanning surfaces the variance
// is written out instead, so nothing here needs a key to read.
function Track({ percent, tone, className = '' }) {
  const p = Math.max(0, Math.min(100, Math.round(percent || 0)))
  return (
    <div className={`h-1.5 rounded bg-pb-surface2 ${className}`}>
      <div className="h-full rounded" style={{ width: `${p}%`, background: tone || 'var(--pb-accent)' }} />
    </div>
  )
}

// Delivery and budget as one pair, which is how they are read: what has been
// done, and what it has cost against what was set aside. Both run 0–100 so they
// share a base — never a second axis relating money to time.
function Pair({ percent, tone, variance, budget, spent, dense }) {
  const spend = budgetState(budget, spent, percent)
  return (
    <div className={`grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-2 ${dense ? 'mt-1.5' : 'mt-2'}`}>
      <div>
        <div className="flex items-baseline gap-2">
          <span className={cap}>DELIVERY</span>
          <span className="font-mono text-[10px] pb-num" style={{ color: tone || 'var(--pb-dim)' }}>
            {Math.round(percent || 0)}%
          </span>
          {variance && <span className="font-mono text-[9.5px] text-pb-faintest ml-auto">{variance}</span>}
        </div>
        <Track percent={percent} tone={tone} className="mt-1" />
      </div>
      <div>
        <div className="flex items-baseline gap-2">
          <span className={cap}>BUDGET</span>
          {spend ? (
            <>
              <span className="font-mono text-[10px] pb-num" style={{ color: spend.tone || 'var(--pb-dim)' }}>
                {spend.percentSpent}%
              </span>
              {spend.label && (
                <span className="font-mono text-[9.5px] ml-auto" style={{ color: spend.tone }}>{spend.label}</span>
              )}
            </>
          ) : (
            <span className="font-mono text-[9.5px] text-pb-faintest">Not allocated</span>
          )}
        </div>
        {spend ? (
          <>
            <Track percent={spend.percentSpent} tone={spend.tone} className="mt-1" />
            <div className="font-mono text-[9.5px] text-pb-faintest mt-1">
              {money(spent)} of {money(budget)}
            </div>
          </>
        ) : <div className="h-1.5 mt-1" />}
      </div>
    </div>
  )
}

/* ── The work under an objective, one click in ──────────────────────────── */

// An action, compact. THIS is where the target mark earns its place: the reader
// has opened this on purpose, so a mark showing where the work should have got
// to by now is worth more than a sentence — and the tooltip carries the key
// rather than a paragraph printed over the whole dashboard.
function WorkAction({ action, state }) {
  const st = STATE[state.key]
  const spend = budgetState(action.budget_estimate, action.actual_expenditure, state.percent)
  const span = [shortDate(action.start_date), shortDate(action.due_date)].filter(Boolean).join(' – ')
  const hasTarget = state.target !== null && state.target !== undefined
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <span aria-hidden="true" className="font-mono text-[10px] leading-5 shrink-0"
        style={{ color: st?.tone || 'var(--pb-faintest)' }}>{st?.glyph}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-pb-text text-[12.5px] leading-snug">{action.title}</span>
          <span className="font-mono text-[9px] shrink-0" style={{ color: st?.tone || 'var(--pb-faintest)' }}>
            {st?.label}
          </span>
        </div>
        <div className="relative h-1.5 rounded bg-pb-surface2 mt-1.5"
          title={hasTarget
            ? `${state.percent}% done, and ${state.target}% of the time between ${span} has gone`
            : 'No start and due date, so there is nothing to measure progress against'}>
          <div className="h-full rounded"
            style={{ width: `${Math.max(0, Math.min(100, state.percent))}%`, background: st?.tone || 'var(--pb-accent)' }} />
          {hasTarget && (
            // 2px, with a surface RING rather than a border, so it reads over
            // the fill and over the empty track alike.
            <span aria-hidden="true" className="absolute top-[-3px] h-[12px] w-[2px] rounded"
              style={{
                left: `calc(${Math.max(0, Math.min(100, state.target))}% - 1px)`,
                background: 'var(--pb-text)',
                boxShadow: '0 0 0 2px var(--pb-surface)',
              }} />
          )}
        </div>
        <div className="font-mono text-[9.5px] text-pb-faintest mt-1 flex flex-wrap gap-x-3">
          <span>{state.percent}% done</span>
          {span ? <span>{span}</span> : <span>No dates set</span>}
          {spend
            ? <span style={{ color: spend.tone || undefined }}>
                {money(action.actual_expenditure)} of {money(action.budget_estimate)}
                {spend.label ? ` · ${spend.label}` : ''}
              </span>
            : <span>No budget</span>}
        </div>
      </div>
    </div>
  )
}

// A motion is evidence, not work: the committee resolved something, and that
// supports the objective without itself having a schedule or a cost. So it is
// one compact line rather than the bordered card the register gives it — that
// card is right where motions ARE the subject, and wrong here.
function WorkMotion({ motion }) {
  const carried = /^(carried|passed)$/i.test(motion.outcome || '')
  const lost = /^(lost|failed|defeated)$/i.test(motion.outcome || '')
  const tone = carried ? POSITIVE : lost ? RED : null
  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <span aria-hidden="true" className="font-mono text-[10px] leading-5 shrink-0"
        style={{ color: tone || 'var(--pb-faintest)' }}>{carried ? '✓' : lost ? '✕' : '○'}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-pb-dim text-[12.5px] leading-snug">{motion.description}</span>
          <span className="font-mono text-[9px] shrink-0" style={{ color: tone || 'var(--pb-faintest)' }}>
            {(motion.outcome || 'pending').toUpperCase()}
          </span>
        </div>
        <div className="font-mono text-[9.5px] text-pb-faintest mt-0.5">
          {[motion.meeting_title, shortDate(motion.meeting_date)].filter(Boolean).join(' · ') || 'Not linked to a meeting'}
        </div>
      </div>
    </div>
  )
}

/* ── The dashboard ──────────────────────────────────────────────────────── */

// Everything the screen needs, worked out in ONE pass so the overview, the
// attention strip and the rows underneath cannot disagree about the same plan.
function readPlan(plan, pillars, today) {
  const objs = plan.objective_list || []
  const themes = (pillars || [])
    .filter(p => p.plan_id === plan.id)
    .map(p => {
      const rows = objs.filter(o => o.pillar_id === p.id).map(o => {
        const actions = (o.action_list || []).map(a => ({ ...a, _s: actionState(a, today) }))
        const motions = o.motion_list || []
        // An objective with nothing serving it has not been started, whatever
        // percentage it happens to carry.
        const key = actions.length ? rollUp(actions.map(a => a._s.key)) : 'not_started'
        const targets = actions.map(a => a._s.target).filter(t => t !== null && t !== undefined)
        const target = targets.length ? Math.round(targets.reduce((n, t) => n + t, 0) / targets.length) : null
        const percent = o.percent_complete || 0
        return {
          ...o, actions, motions, key, target, percent,
          spend: budgetState(o.budget, o.spent, percent),
          variance: scheduleVariance(percent, target),
        }
      })
      const percent = rows.length ? Math.round(rows.reduce((n, r) => n + r.percent, 0) / rows.length) : 0
      const budget = rows.reduce((n, r) => n + Number(r.budget || 0), 0)
      const spent = rows.reduce((n, r) => n + Number(r.spent || 0), 0)
      return {
        ...p, rows, percent, budget, spent,
        key: rollUp(rows.map(r => r.key)),
        onTrack: rows.filter(r => r.key === 'on_track' || r.key === 'done').length,
        spend: budgetState(budget, spent, percent),
      }
    })
    .filter(t => t.rows.length)

  const all = themes.flatMap(t => t.rows)
  // What needs attention, worst first. Only objectives — a committee acts on
  // what it committed to, and the action underneath is the detail of why.
  const attention = all
    .filter(r => r.key === 'late' || r.key === 'behind' || r.spend?.over)
    .map(r => ({
      row: r,
      why: r.key === 'late'
        ? `${r.actions.filter(a => a._s.key === 'late').length || 1} overdue action${(r.actions.filter(a => a._s.key === 'late').length || 1) === 1 ? '' : 's'}`
        : r.variance ? `${r.variance} on delivery`
        : r.spend?.over ? 'spending past its budget'
        : 'behind schedule',
      rank: STATE[r.key].rank + (r.spend?.over ? 0.5 : 0),
    }))
    .sort((a, b) => b.rank - a.rank)

  // The plan's own headline figures come from the PLAN ROW, not from summing
  // these themes again: the backend already rolled them up, the card is built
  // from them elsewhere, and two ways of computing one number is how a screen
  // ends up printing 44% and 45% for the same plan an inch apart. Only the
  // counts — on track, needing attention — are derived here, and they are
  // things the payload does not carry.
  return {
    themes,
    objectives: all.length,
    onTrack: all.filter(r => r.key === 'on_track' || r.key === 'done').length,
    percent: plan.percent_complete || 0,
    budget: Number(plan.budget || 0),
    spent: Number(plan.spent || 0),
    attention,
  }
}

// The plan's four figures, rendered by the plan pane INSIDE its own title card
// rather than by a second card underneath it — the first cut stacked two
// summaries on each other, saying the same thing twice and disagreeing about
// the percentage because each computed it its own way.
//
// Deliberately NOT one overall verdict. A worst-of rollup at this altitude
// brands a sixteen-objective plan LATE off a single overdue action and never
// recovers; a proportion is the honest headline for a whole plan.
//
// Delivered, budget and spend come from the PLAN ROW the backend already
// rolled up — the same numbers the rest of the app reads. Only the counts are
// derived here, and only because the payload does not carry them.
export function PlanFigures({ plan, pillars }) {
  const today = startOfToday()
  const d = useMemo(() => readPlan(plan, pillars, today), [plan, pillars, today])
  const spend = budgetState(d.budget, d.spent, d.percent)
  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-5">
      <div>
        <div className="font-display font-bold text-[22px] leading-none pb-num" style={{ color: 'var(--pb-accent-ink)' }}>
          {d.percent}%
        </div>
        <div className={`${cap} mt-1`}>DELIVERED</div>
        <Track percent={d.percent} className="mt-2" />
      </div>
      <div>
        <div className="font-display font-bold text-[22px] leading-none pb-num"
          style={{ color: spend?.over ? RED : 'var(--pb-accent-ink)' }}>
          {spend ? `${spend.percentSpent}%` : '—'}
        </div>
        <div className={`${cap} mt-1`}>{spend ? 'OF BUDGET SPENT' : 'NO BUDGET SET'}</div>
        {spend
          ? <>
              <Track percent={spend.percentSpent} tone={spend.tone} className="mt-2" />
              <div className="font-mono text-[9.5px] text-pb-faintest mt-1">{money(d.spent)} of {money(d.budget)}</div>
            </>
          : <div className="h-1.5 mt-2" />}
      </div>
      <div>
        <div className="font-display font-bold text-[22px] leading-none pb-num" style={{ color: 'var(--pb-accent-ink)' }}>
          {d.onTrack}<span className="text-pb-faint">/{d.objectives}</span>
        </div>
        <div className={`${cap} mt-1`}>OBJECTIVES ON TRACK</div>
      </div>
      <div>
        <div className="font-display font-bold text-[22px] leading-none pb-num"
          style={{ color: d.attention.length ? RED : POSITIVE }}>
          {d.attention.length}
        </div>
        <div className={`${cap} mt-1`}>{d.attention.length === 1 ? 'NEEDS ATTENTION' : 'NEED ATTENTION'}</div>
      </div>
    </div>
  )
}

export function PlanDelivery({ plan, pillars }) {
  const today = startOfToday()
  const d = useMemo(() => readPlan(plan, pillars, today), [plan, pillars, today])
  // Every theme starts folded, so the page opens as a list of themes rather
  // than the whole plan at once — but a committee comparing two themes should
  // not have the first one shut on it when the second is opened, so any number
  // can be open together. The work under an objective is a further click.
  const [openThemes, setOpenThemes] = useState(() => new Set())
  const toggleTheme = id => setOpenThemes(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })
  const [openWork, setOpenWork] = useState(() => new Set())
  const toggleWork = id => setOpenWork(s => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n })

  if (!d.themes.length) {
    return (
      <div className="pb-card p-6 text-center">
        <div className="text-pb-text text-[13px] mb-1">Nothing to report on yet.</div>
        <div className="font-mono text-[11px] text-pb-faintest">
          Add a theme and an objective, and the plan's progress appears here.
        </div>
      </div>
    )
  }

  // Opening a theme from the attention strip: the theme is expanded and the
  // objective's own work with it, so one click lands on the thing named.
  const jumpTo = row => {
    const theme = d.themes.find(t => t.rows.some(r => r.id === row.id))
    // Opened alongside whatever the reader already had open, not instead of it.
    if (theme) setOpenThemes(s => new Set([...s, theme.id]))
    setOpenWork(s => new Set([...s, row.id]))
    requestAnimationFrame(() => {
      document.getElementById(`plan-obj-${row.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }

  return (
    <div className="space-y-3">
      {/* ── what needs attention, worst first ──────────────────────────── */}
      {/* Only drawn when there is something to say. An empty box headed
          "needs attention" is a control that can only ever answer "nothing",
          which is worse than no control at all. */}
      {d.attention.length > 0 && (
        <div className="pb-card p-4">
          <div className={`${cap} mb-2`}>NEEDS ATTENTION</div>
          <div className="space-y-1">
            {d.attention.slice(0, 5).map(({ row, why }) => (
              <button key={row.id} type="button" onClick={() => jumpTo(row)}
                className="w-full text-left flex items-start gap-2.5 rounded px-1.5 py-1 -mx-1.5 hover:bg-pb-surface2">
                <span aria-hidden="true" className="font-mono text-[10px] leading-5 shrink-0"
                  style={{ color: STATE[row.key].tone || 'var(--pb-faintest)' }}>{STATE[row.key].glyph}</span>
                <span className="min-w-0 flex-1 text-pb-text text-[12.5px] leading-snug">{row.title}</span>
                {/* The state is NAMED here too, not just glyphed: BEHIND and
                    LATE share the ● and are told apart by colour alone
                    otherwise, which the palette measurements rule out. */}
                <span className="font-mono text-[9.5px] shrink-0 pt-0.5"
                  style={{ color: STATE[row.key].tone || 'var(--pb-faintest)' }}>
                  {STATE[row.key].label} · {why}
                </span>
              </button>
            ))}
            {d.attention.length > 5 && (
              <div className="font-mono text-[9.5px] text-pb-faintest pt-1">
                and {d.attention.length - 5} more
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── the themes, one summary row each ───────────────────────────── */}
      <div className="pb-card divide-y pb-hairline">
        <div className={`${cap} px-4 pt-4 pb-2`}>THEMES</div>
        {d.themes.map(t => {
          const isOpen = openThemes.has(t.id)
          return (
            <div key={t.id}>
              <button type="button" onClick={() => toggleTheme(t.id)}
                aria-expanded={isOpen}
                className="w-full text-left px-4 py-3 hover:bg-pb-surface2">
                <div className="flex items-start gap-2">
                  <span aria-hidden="true" className="font-mono text-[10px] text-pb-faint leading-5 shrink-0 w-3">
                    {isOpen ? '▾' : '▸'}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-3">
                      <span className="text-pb-text text-[13.5px] font-semibold leading-snug">{t.name}</span>
                      <StateTag state={t.key} size="lg" />
                    </div>
                    <div className="font-mono text-[9.5px] text-pb-faintest mt-0.5">
                      {t.rows.length} objective{t.rows.length === 1 ? '' : 's'} · {t.onTrack} on track
                    </div>
                    <Pair percent={t.percent} tone={STATE[t.key].tone} budget={t.budget} spent={t.spent} />
                  </div>
                </div>
              </button>

              {isOpen && (
                <div className="px-4 pb-4 space-y-2">
                  {t.rows.map(o => {
                    const workOpen = openWork.has(o.id)
                    const work = o.actions.length + o.motions.length
                    return (
                      <div key={o.id} id={`plan-obj-${o.id}`}
                        className="border-l-2 pl-3" style={{ borderColor: LEVEL.objective.rail }}>
                        <div className="flex items-start gap-2.5">
                          <span aria-hidden="true" className="font-mono text-[11px] leading-5 shrink-0"
                            style={{ color: STATE[o.key].tone || 'var(--pb-faintest)' }}>{STATE[o.key].glyph}</span>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-start justify-between gap-3">
                              <span className="text-pb-text text-[13px] leading-snug">{o.title}</span>
                              <StateTag state={o.key} />
                            </div>
                            <Pair percent={o.percent} tone={STATE[o.key].tone} variance={o.variance}
                              budget={o.budget} spent={o.spent} dense />
                            <div className="flex items-center justify-between gap-2 mt-1.5">
                              <span className="font-mono text-[9.5px] text-pb-faintest">
                                {work
                                  ? [o.actions.length && `${o.actions.length} action${o.actions.length === 1 ? '' : 's'}`,
                                     o.motions.length && `${o.motions.length} motion${o.motions.length === 1 ? '' : 's'}`]
                                      .filter(Boolean).join(' · ')
                                  : 'No actions or motions yet'}
                              </span>
                              {work > 0 && (
                                <button type="button" onClick={() => toggleWork(o.id)} aria-expanded={workOpen}
                                  className="font-mono text-[9.5px] text-pb-faint hover:text-pb-text shrink-0">
                                  {workOpen ? 'Hide details' : 'View details ›'}
                                </button>
                              )}
                            </div>
                            {workOpen && (
                              <div className="mt-2 rounded bg-pb-surface2/40 px-3 py-1.5">
                                {o.actions.length > 0 && (
                                  <>
                                    <div className={`${cap} pt-1`}>ACTIONS</div>
                                    {o.actions.map(a => <WorkAction key={a.id} action={a} state={a._s} />)}
                                  </>
                                )}
                                {o.motions.length > 0 && (
                                  <>
                                    <div className={`${cap} pt-2`}>SUPPORTING MOTIONS</div>
                                    {o.motions.map(m => <WorkMotion key={m.id} motion={m} />)}
                                  </>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

/* ── Pointing something at the plan ─────────────────────────────────────── */

// One picker for "which objective does this serve", used by an action's plan
// panel, a motion in the meetings list and the meeting room. It shows the plan
// an objective belongs to as well as the objective, because two plans can each
// have an objective called "Grow junior numbers" and picking the wrong one is
// otherwise invisible.
export function useObjectives() {
  const [objectives, setObjectives] = useState([])
  useEffect(() => {
    let live = true
    api.committeeListObjectives()
      .then(d => { if (live) setObjectives(d.objectives || []) })
      .catch(() => {})
    return () => { live = false }
  }, [])
  return objectives
}

export { objectiveLabel, objectiveTiers }

// Picking the objective an action or a motion serves.
//
// This was a plain <select> of every objective the club holds, each option
// reading "Plan › Theme › a whole sentence" — fifteen rows of the same plan
// name, every title clipped at the width of the control. Reported as
// overwhelming, and it was: the repetition was 80% of the text and the part
// that tells them apart was the part being cut off.
//
// So it is drawn as the tree it actually is — plan, then its themes indented
// under it, then the objectives indented under those — with each objective's
// title given a full line to wrap onto and a search box to narrow a long plan.
// The closed control shows the choice as the breadcrumb it is, which is also
// what the card above the picker spells out in full.
//
// ONLY THE OBJECTIVES ARE SELECTABLE, and that is the whole reason it reads as
// a tree rather than a flat list: an action or a motion serves an objective and
// nothing else, so a plan and a theme are there to LOCATE one. They are plain
// headings, not buttons, and carry no role="option" — there is nothing to pick
// by mistake, and a screen reader is read the objectives it can actually
// choose from.
export function ObjectiveSelect({ objectives, value, onChange, label = 'OBJECTIVE' }) {
  const rows = objectives || []
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const chosen = rows.find(o => o.id === value) || null

  // Plan → themes → objectives, built in the order the objectives arrive
  // (which is the club's own sort order), so a branch never jumps around
  // between renders.
  //
  // Keyed on plan_id and pillar_id, NOT on their names: two plans may
  // legitimately be called the same thing, and grouping by name would draw
  // one branch holding both plans' themes — the exact leak migration 275
  // exists to prevent, reintroduced in a picker.
  const tree = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const plans = []
    const planBy = {}
    for (const o of rows) {
      if (needle && !`${o.title} ${o.plan_name || ''} ${o.pillar_name || ''}`.toLowerCase().includes(needle)) continue
      const pk = String(o.plan_id ?? '~')
      let plan = planBy[pk]
      if (!plan) { plan = planBy[pk] = { key: pk, name: o.plan_name, themes: [], themeBy: {} }; plans.push(plan) }
      const tk = String(o.pillar_id ?? '~')
      let theme = plan.themeBy[tk]
      if (!theme) { theme = plan.themeBy[tk] = { key: `${pk}¦${tk}`, name: o.pillar_name, rows: [] }; plan.themes.push(theme) }
      theme.rows.push(o)
    }
    return plans
  }, [rows, q])
  const anyMatch = tree.length > 0

  const pick = (id) => { onChange(id || null); setOpen(false); setQ('') }

  return (
    <div className="block">
      {label && <span className={`${cap} block mb-1`}>{label}</span>}
      <button type="button" onClick={() => setOpen(v => !v)}
        aria-expanded={open} aria-haspopup="listbox"
        className={`${inp} flex items-start gap-2 text-left`}>
        <span className="flex-1 min-w-0">
          {chosen ? (
            <>
              {(chosen.plan_name || chosen.pillar_name) && (
                <span className={`${cap} block truncate`}>
                  {[chosen.plan_name, chosen.pillar_name].filter(Boolean).join(' › ')}
                </span>
              )}
              <span className="block text-pb-text leading-snug">{chosen.title}</span>
            </>
          ) : (
            <span className="text-pb-faint">— not on the plan —</span>
          )}
        </span>
        <span className="text-pb-faint text-[11px] leading-none pt-1">{open ? '▴' : '▾'}</span>
      </button>

      {open && (
        <div className="mt-1 rounded border pb-hairline bg-pb-surface2 overflow-hidden">
          {rows.length > 6 && (
            <input autoFocus value={q} onChange={e => setQ(e.target.value)}
              placeholder="Search objectives…"
              className="w-full bg-transparent border-b pb-hairline px-2.5 py-1.5 text-[12.5px] text-pb-text focus:outline-none" />
          )}
          <div className="max-h-64 overflow-y-auto pb-scroll" role="listbox">
            <button type="button" onClick={() => pick('')}
              className={`w-full text-left px-2.5 py-1.5 text-[12.5px] hover:bg-pb-surface ${value ? 'text-pb-faint' : 'text-pb-text'}`}>
              — not on the plan —
            </button>
            {/* Plan → theme → objective, indented. Only the OBJECTIVES are
                buttons: an action or a motion can serve an objective and
                nothing else, so a plan or a theme is a heading that locates
                one, never something that can be picked by mistake. They carry
                no role="option" either, so a screen reader reads the list as
                the objectives it can actually choose from. */}
            {tree.map((plan, i) => (
              <div key={plan.key} role="group" aria-label={plan.name || 'Not on a plan'}
                className={i > 0 ? 'border-t pb-hairline mt-1' : ''}>
                <div className={`${cap} px-2.5 pt-2 pb-1 text-pb-dim`}>
                  {(plan.name || 'NOT ON A PLAN').toUpperCase()}
                </div>
                {plan.themes.map(theme => (
                  // A rail down each branch, in the same accent-mix the plan
                  // screen's own nesting uses, so the indent reads as a tree
                  // rather than as text that happens to start further in. The
                  // step is slimmer than `Nested`'s: a long objective title
                  // needs the reading width more than this panel needs depth.
                  <div key={theme.key} role="group" aria-label={theme.name || 'No theme'}
                    className="ml-2.5 pl-2 border-l-2" style={{ borderColor: LEVEL.objective.rail }}>
                    <div className={`${cap} px-2.5 py-1 text-pb-faintest`}>
                      {(theme.name || 'NO THEME').toUpperCase()}
                    </div>
                    {theme.rows.map(o => (
                      <button key={o.id} type="button" onClick={() => pick(o.id)} role="option"
                        aria-selected={o.id === value}
                        className={`w-full text-left pl-5 pr-2.5 py-1.5 text-[12.5px] leading-snug hover:bg-pb-surface ${o.id === value ? 'text-pb-text' : 'text-pb-dim'}`}
                        style={o.id === value ? { background: 'color-mix(in srgb, var(--pb-accent) 12%, transparent)' } : undefined}>
                        {o.id === value && <span style={{ color: 'var(--pb-accent-ink)' }}>✓ </span>}
                        {o.title}
                      </button>
                    ))}
                  </div>
                ))}
              </div>
            ))}
            {!anyMatch && (
              <div className="px-2.5 py-3 font-mono text-[10px] text-pb-faintest">Nothing matches that.</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function LateTag({ row }) {
  if (!row.is_late) return null
  const overdue = row.actions_overdue || 0
  return (
    <span className="font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border border-pb-red/40 text-pb-red">
      LATE{overdue ? ` · ${overdue} OVERDUE` : ''}
    </span>
  )
}

/* ── The plan itself ────────────────────────────────────────────────────── */

const emptyPlan = { name: '', description: '', start_year: '', end_year: '' }

function PlanForm({ plan, onSave, onCancel }) {
  const [form, setForm] = useState(() => plan
    ? { name: plan.name || '', description: plan.description || '',
        start_year: plan.start_year ?? '', end_year: plan.end_year ?? '' }
    : emptyPlan)
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!form.name.trim()) return
    setBusy(true)
    try {
      await onSave({
        name: form.name.trim(),
        description: form.description.trim() || null,
        start_year: form.start_year === '' ? null : Number(form.start_year),
        end_year: form.end_year === '' ? null : Number(form.end_year),
      })
      if (!plan) setForm(emptyPlan)
    } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4 space-y-2">
      <div className={cap}>{plan ? 'EDIT PLAN' : 'NEW PLAN'}</div>
      <div className="flex flex-col sm:flex-row gap-2">
        <input className={`${inp} flex-1`} placeholder="Plan name (e.g. Strategic Plan 2026-29)"
          value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        <input type="number" className={`${inp} sm:w-28`} placeholder="From"
          value={form.start_year} onChange={e => setForm(f => ({ ...f, start_year: e.target.value }))} />
        <input type="number" className={`${inp} sm:w-28`} placeholder="To"
          value={form.end_year} onChange={e => setForm(f => ({ ...f, end_year: e.target.value }))} />
      </div>
      <textarea rows={2} className={inp} placeholder="What this plan is for (optional)"
        value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
      <div className="flex gap-2">
        <button onClick={submit} disabled={busy || !form.name.trim()}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-40"
          style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
          {busy ? 'SAVING…' : plan ? 'SAVE PLAN' : '+ PLAN'}
        </button>
        {onCancel && (
          <button onClick={onCancel} className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">
            Cancel
          </button>
        )}
      </div>
    </div>
  )
}

/* ── An objective within a plan ─────────────────────────────────────────── */

const emptyObjective = {
  title: '', description: '', due_date: '', budget: '', season_year: '',
  pillar_id: '', owner_position_id: '',
}

function ObjectiveForm({ objective, plans, pillars, positions, planId, pillarId, members, onSave, onCancel }) {
  const [form, setForm] = useState(() => objective
    ? {
        title: objective.title || '', description: objective.description || '',
        due_date: objective.due_date || '',
        // `own_budget` on a rolled-up row is the club's OWN allocation;
        // `budget` there is the effective figure and may have been summed from
        // the actions, which is not something to seed an edit form with.
        budget: ownBudget(objective) ?? '', season_year: objective.season_year ?? '',
        plan_id: objective.plan_id || '', pillar_id: objective.pillar_id || '',
        owner_position_id: objective.owner_position_id || '',
      }
    : { ...emptyObjective, plan_id: planId || '', pillar_id: pillarId || '' })
  // A person owner is the exception, so the form opens on the committee seat
  // unless this objective already names someone.
  const [ownerMode, setOwnerMode] = useState(objective?.owner_member_id ? 'person' : 'position')
  const [person, setPerson] = useState(() => {
    const m = (members || []).find(x => x.member_id === objective?.owner_member_id)
    return m ? { member_id: m.member_id, full_name: m.full_name } : null
  })
  const [busy, setBusy] = useState(false)

  async function submit() {
    // An objective belongs to a theme, and its plan comes from that theme
    // (migration 276), so both have to be picked before there is anywhere to
    // put it. The server refuses one without them either way.
    if (!form.title.trim() || !form.plan_id || !form.pillar_id) return
    setBusy(true)
    try {
      await onSave({
        title: form.title.trim(),
        description: form.description.trim() || null,
        plan_id: form.plan_id,
        pillar_id: form.pillar_id,
        // The rest are nullable and the API reads an explicit null as "clear
        // it", so anything set here can be taken off again.
        due_date: form.due_date || null,
        // One owner, not two: a seat OR a person, never both half-set.
        owner_position_id: ownerMode === 'position' ? (form.owner_position_id || null) : null,
        owner_member_id: ownerMode === 'person' ? (person?.member_id || null) : null,
        budget: form.budget === '' ? null : Number(form.budget),
        season_year: form.season_year === '' ? null : Number(form.season_year),
      })
      if (!objective) {
        setForm({ ...emptyObjective, plan_id: planId || '', pillar_id: pillarId || '' })
        setPerson(null)
      }
    } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4 space-y-2">
      <div className={cap}>{objective ? 'EDIT OBJECTIVE' : 'NEW OBJECTIVE'}</div>
      <input className={inp} placeholder="Objective (e.g. Upgrade the practice nets)"
        value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
      <textarea rows={2} className={inp} placeholder="What success looks like (optional)"
        value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <label className="block">
          <span className={`${cap} block mb-1`}>STRATEGIC PLAN</span>
          <select className={inp} value={form.plan_id}
            onChange={e => setForm(f => ({ ...f, plan_id: e.target.value, pillar_id: '' }))}>
            <option value="">— pick a plan —</option>
            {(plans || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label className="block">
          <span className={`${cap} block mb-1`}>THEME</span>
          {/* Only the chosen plan's themes: a theme belongs to one plan, so
              offering another plan's would file this objective in a tree it
              is not in. Changing the plan therefore clears the theme. */}
          <select className={inp} value={form.pillar_id}
            onChange={e => setForm(f => ({ ...f, pillar_id: e.target.value }))}
            disabled={!form.plan_id}>
            <option value="">{form.plan_id ? '— pick a theme —' : '— pick a plan first —'}</option>
            {(pillars || []).filter(p => p.plan_id === form.plan_id)
              .map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        {/* A committee SEAT by default: ownership then transfers at the AGM
            without anyone editing this. A named person is still available for
            work that genuinely belongs to an individual. */}
        <div className="block">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className={cap}>RESPONSIBLE</span>
            <button type="button"
              onClick={() => setOwnerMode(m => m === 'position' ? 'person' : 'position')}
              className="font-mono text-[9px] text-pb-faint hover:text-pb-text">
              {ownerMode === 'position' ? 'a specific person instead' : 'a committee role instead'}
            </button>
          </div>
          {ownerMode === 'position' ? (
            <select className={inp} value={form.owner_position_id}
              onChange={e => setForm(f => ({ ...f, owner_position_id: e.target.value }))}>
              <option value="">— unassigned —</option>
              {(positions || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          ) : (
            <PersonSearch value={person} onChange={setPerson}
              placeholder="Type a name to search the club…" />
          )}
        </div>
        <label className="block">
          <span className={`${cap} block mb-1`}>DUE</span>
          <input type="date" className={inp} value={form.due_date}
            onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
        </label>
        <label className="block">
          <span className={`${cap} block mb-1`}>BUDGET</span>
          <input type="number" step="0.01" className={inp} placeholder="Leave blank to add up its actions"
            value={form.budget} onChange={e => setForm(f => ({ ...f, budget: e.target.value }))} />
        </label>
      </div>
      <div className="flex gap-2">
        <button onClick={submit} disabled={busy || !form.title.trim() || !form.plan_id || !form.pillar_id}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-40"
          style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
          {busy ? 'SAVING…' : objective ? 'SAVE OBJECTIVE' : '+ OBJECTIVE'}
        </button>
        {onCancel && (
          <button onClick={onCancel} className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">
            Cancel
          </button>
        )}
      </div>
    </div>
  )
}

/* ── What is actually being done about an objective ─────────────────────── */

// An action's own progress and spend, editable where they are read. The Actions
// board can do this too, but an objective is where somebody reviewing the plan
// is sitting, and sending them to another tab to move a percentage is how a
// plan goes stale.
function ActionLine({ action, onSave }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({
    percent_complete: action.percent_complete ?? 0,
    actual_expenditure: action.actual_expenditure ?? '',
    budget_estimate: action.budget_estimate ?? '',
  })
  const [busy, setBusy] = useState(false)

  const budget = Number(action.budget_estimate || 0)
  const spent = Number(action.actual_expenditure || 0)
  const spentPct = budget ? Math.round(spent / budget * 100) : null
  const overdue = action.status !== 'done' && action.due_date && action.due_date < new Date().toISOString().slice(0, 10)

  async function save() {
    setBusy(true)
    try {
      await onSave({
        percent_complete: Number(form.percent_complete) || 0,
        actual_expenditure: form.actual_expenditure === '' ? null : Number(form.actual_expenditure),
        budget_estimate: form.budget_estimate === '' ? null : Number(form.budget_estimate),
      })
      setOpen(false)
    } finally { setBusy(false) }
  }

  return (
    <div className="border pb-hairline rounded px-3 py-2" style={{ background: LEVEL.work.tint }}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-[12.5px] text-pb-text">{action.title}</div>
          <div className="font-mono text-[9.5px] text-pb-faintest mt-0.5 flex flex-wrap gap-x-2">
            <span>{action.percent_complete || 0}% complete</span>
            {budget > 0 && (
              <span style={spent > budget ? { color: AMBER } : undefined}>
                {money(spent)} of {money(budget)}{spentPct !== null ? ` · ${spentPct}%` : ''}
              </span>
            )}
            {action.due_date && (
              <span style={overdue ? { color: 'var(--pb-red)' } : undefined}>
                due {action.due_date}{overdue ? ' · late' : ''}
              </span>
            )}
            {action.status === 'done' && <span style={{ color: 'var(--pb-positive)' }}>done</span>}
          </div>
          {action.meeting_title && (
            <div className="mt-0.5">
              <RaisedAt title={action.meeting_title} date={action.meeting_date} />
            </div>
          )}
        </div>
        <button onClick={() => setOpen(o => !o)}
          className="font-mono text-[9px] text-pb-faint hover:text-pb-text shrink-0">
          {open ? 'Close' : 'Update'}
        </button>
      </div>
      <div className="mt-1.5"><Bar percent={action.percent_complete} tone={action.status === 'done' ? 'var(--pb-positive)' : overdue ? 'var(--pb-red)' : undefined} /></div>

      {open && (
        <div className="mt-2 pt-2 border-t pb-hairline space-y-2">
          <label className="block">
            <span className={`${cap} block mb-1`}>PROGRESS · {form.percent_complete}%</span>
            <input type="range" min="0" max="100" step="5" className="w-full accent-pb-accent"
              value={form.percent_complete}
              onChange={e => setForm(f => ({ ...f, percent_complete: e.target.value }))} />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className={`${cap} block mb-1`}>BUDGET</span>
              <input type="number" step="0.01" className={inp} placeholder="0.00" value={form.budget_estimate}
                onChange={e => setForm(f => ({ ...f, budget_estimate: e.target.value }))} />
            </label>
            <label className="block">
              <span className={`${cap} block mb-1`}>SPENT TO DATE</span>
              <input type="number" step="0.01" className={inp} placeholder="0.00" value={form.actual_expenditure}
                onChange={e => setForm(f => ({ ...f, actual_expenditure: e.target.value }))} />
            </label>
          </div>
          <button onClick={save} disabled={busy}
            className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-50"
            style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
            {busy ? 'SAVING…' : 'SAVE'}
          </button>
        </div>
      )}
    </div>
  )
}

function MotionLine({ motion }) {
  const tone = motion.outcome === 'carried' ? 'var(--pb-positive)'
    : motion.outcome === 'lost' ? 'var(--pb-red)' : 'var(--pb-faint)'
  return (
    <div className="border pb-hairline rounded px-3 py-2" style={{ background: LEVEL.work.tint }}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-[12.5px] text-pb-text min-w-0">{motion.description}</div>
        <span className="font-mono text-[9px] tracking-wide2 shrink-0" style={{ color: tone }}>
          {(motion.outcome || 'pending').toUpperCase()}
        </span>
      </div>
      <div className="mt-0.5 flex flex-wrap items-center gap-x-2">
        <RaisedAt title={motion.meeting_title} date={motion.meeting_date} verb="Moved at" />
        {motion.is_resolution && (
          <span className="font-mono text-[9px]" style={{ color: 'var(--pb-accent-ink)' }}>
            RESOLUTION{motion.resolution_ref ? ` · ${motion.resolution_ref}` : ''}
          </span>
        )}
      </div>
    </div>
  )
}

function ObjectiveCard({ objective, plans, pillars, positions, members, memberName, onChanged }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [open, setOpen] = useState(false)

  const o = objective
  const actions = o.action_list || []
  const motions = o.motion_list || []

  async function save(data) {
    try { await api.committeeUpdateObjective(o.id, data); toast.success('Objective saved'); setEditing(false); onChanged() }
    catch (e) { toast.error(e.message) }
  }
  async function remove() {
    if (!confirm(`Delete "${o.title}"? The actions and motions serving it keep going, they just stop pointing at an objective.`)) return
    try { await api.committeeDeleteObjective(o.id); onChanged() } catch (e) { toast.error(e.message) }
  }
  async function updateAction(id, data) {
    try { await api.committeeUpdateTask(id, data); toast.success('Action updated'); onChanged() }
    catch (e) { toast.error(e.message) }
  }

  if (editing) {
    return (
      <ObjectiveForm objective={o} plans={plans} pillars={pillars} positions={positions}
        members={members} onSave={save} onCancel={() => setEditing(false)} />
    )
  }

  return (
    <div className="rounded-lg border pb-hairline p-3 sm:p-4" style={{ background: LEVEL.objective.tint }}>
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="min-w-0">
          <div className={`${cap} mb-0.5`}>OBJECTIVE</div>
          <div className="text-pb-text font-medium flex items-center gap-2 flex-wrap">
            {o.title}<LateTag row={o} />
          </div>
          {o.description && <div className="text-pb-faint text-[12.5px] mt-0.5">{o.description}</div>}
          <div className="font-mono text-[9.5px] text-pb-faintest mt-1 flex flex-wrap gap-x-2">
            {/* A seat reads as the seat, so it stays right after a handover. */}
            {o.owner_position_name && <span>{o.owner_position_name}</span>}
            {!o.owner_position_name && o.owner_member_id && <span>{memberName(o.owner_member_id)}</span>}
            {o.due_date && <span>due {o.due_date}</span>}
            {o.season_year && <span>{o.season_year}</span>}
            {ownBudget(o) != null && <span>allocated {money(ownBudget(o))}</span>}
            {ownBudget(o) == null && o.budget > 0 && <span>{money(o.budget)} across its actions</span>}
          </div>
        </div>
        <div className="flex gap-2 shrink-0">
          <button onClick={() => setEditing(true)}
            className="font-mono text-[9px] text-pb-faint hover:text-pb-text">Edit</button>
          <button onClick={remove}
            className="font-mono text-[9px] text-pb-faintest hover:text-pb-red">Delete</button>
        </div>
      </div>

      <Delivery row={o} level="objective" />

      <button onClick={() => setOpen(v => !v)}
        className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-text mt-3">
        {open ? '▾' : '▸'} {open ? 'Hide' : 'Show'} work · {actions.length} {actions.length === 1 ? 'action' : 'actions'} · {motions.length} {motions.length === 1 ? 'motion' : 'motions'} · notes
      </button>

      {open && (
        <Nested level="work" className="mt-3 space-y-3">
          <div>
            <div className={`${cap} mb-1.5`}>ACTIONS</div>
            {actions.length === 0 ? (
              <div className="font-mono text-[10px] text-pb-faintest">
                Nothing yet. Point an action at this objective from the Actions tab or in a meeting.
              </div>
            ) : (
              <div className="space-y-1.5">
                {actions.map(a => (
                  <ActionLine key={a.id} action={a} onSave={d => updateAction(a.id, d)} />
                ))}
              </div>
            )}
          </div>
          <div>
            <div className={`${cap} mb-1.5`}>MOTIONS</div>
            {motions.length === 0 ? (
              <div className="font-mono text-[10px] text-pb-faintest">
                No motion has been tied to this objective.
              </div>
            ) : (
              <div className="space-y-1.5">{motions.map(m => <MotionLine key={m.id} motion={m} />)}</div>
            )}
          </div>
          <NoteThread entityType="objective" entityId={o.id} />
        </Nested>
      )}
    </div>
  )
}

/* ── Strategic Plans: the tree, and one thing open beside it ────────────── */

// The club's plan is four levels deep — plan, theme, objective, and the actions
// and motions doing the work — and reading it as one long scrolling page meant
// scrolling past everything to reach anything. So it is the same two panes the
// meetings list uses: the whole plan as a tree you can fold down the left, and
// whatever is selected open on the right.
//
// A THEME IS CLUB-SCOPED, not plan-scoped (migration 232) — the same theme
// groups objectives in several plans at once. It is drawn under a plan here
// because that is how a committee reads its plan, but it belongs to the club,
// which is what makes deleting one reach further than this plan and why the
// confirm counts across all of them.

const TREE_ROW = 'w-full text-left flex items-start gap-1.5 rounded px-1.5 py-1 hover:bg-pb-surface2 select-none'

// The expand/collapse control. It used to be an 11px glyph in a 14px box
// wrapped in a button with no padding of its own, so the hit area WAS the
// glyph — a hard thing to aim at for the one control that folds the tree away.
// Twice the glyph, twice the box, and the box is the button rather than
// something inside it.
//
// The spacer and the control are the same class, so a row with nothing to fold
// lines up with one that has by construction rather than by two numbers being
// kept in step.
const TWISTY_BOX = 'w-7 h-7 shrink-0 flex items-start justify-center text-[22px] leading-[22px]'
// One level's step in, and it is DERIVED rather than chosen: the control is
// 28px (`w-7`) and the row's own gap is 6px (`gap-1.5`), so a child indented
// by 34px puts its caret directly under the first letter of its parent's
// label. Anything less and a theme's caret sits to the LEFT of the word PLAN
// above it, which reads as though it belonged to the level above. Change
// either of those two and this has to move with them.
const TREE_STEP = 'ml-[34px]'

function Twisty({ open, hidden, onToggle }) {
  if (hidden || !onToggle) return <span className={TWISTY_BOX} aria-hidden="true" />
  return (
    <button type="button" aria-label={open ? 'Collapse' : 'Expand'} aria-expanded={open}
      onClick={e => { e.stopPropagation(); onToggle() }}
      className={`${TWISTY_BOX} rounded text-pb-faint hover:text-pb-text hover:bg-pb-surface2`}>
      {open ? '▾' : '▸'}
    </button>
  )
}

// A row's ✕. Never on an action or a motion: those are deleted from the thing
// itself, where the confirm can say what goes with them.
function DelDot({ onClick, title }) {
  return (
    <button onClick={e => { e.stopPropagation(); onClick() }} title={title} aria-label={title}
      className="shrink-0 font-mono text-[9px] text-pb-faintest hover:text-pb-red px-1 leading-5">✕</button>
  )
}

function TreeLabel({ kind, children, active, dim }) {
  return (
    <span className="min-w-0 flex-1">
      <span className={`${cap} block leading-3`}>{kind}</span>
      <span className={`block text-[12.5px] leading-snug ${active ? 'text-pb-text font-semibold' : dim ? 'text-pb-faint' : 'text-pb-dim'}`}>
        {children}
      </span>
    </span>
  )
}

// Actions and motions under one objective, either kept apart or run together in
// the order they were raised. A committee reads it both ways: "what are we
// doing about this" and "what has happened on this, in order".
function workRows(objective, mode) {
  const actions = (objective.action_list || []).map(a => ({ ...a, _kind: 'action', _label: a.title }))
  const motions = (objective.motion_list || []).map(m => ({ ...m, _kind: 'motion', _label: m.description }))
  if (mode !== 'date') return [...actions, ...motions]
  // The plan report carries the meeting each was raised at, which is the only
  // date the club actually keeps for both. An action raised outside a meeting
  // falls back to its own dates so it still lands somewhere sensible.
  const at = r => r.meeting_date || r.start_date || r.due_date || ''
  return [...actions, ...motions].sort((x, y) => String(at(x)).localeCompare(String(at(y))))
}

function StatTile({ value, label, tone }) {
  return (
    <div>
      <div className="text-[22px] font-bold leading-none" style={{ color: tone || 'var(--pb-accent-ink)' }}>{value}</div>
      <div className={`${cap} mt-1`}>{label}</div>
    </div>
  )
}

// A theme is a name and, if the club wants one, a line about what it means.
// It used to be renamed through window.prompt, which is the one control on this
// screen that cannot show a description or be cancelled cleanly.
function ThemeForm({ pillar, onSave, onCancel }) {
  const [form, setForm] = useState({
    name: pillar?.name || '',
    description: pillar?.description || '',
  })
  const [busy, setBusy] = useState(false)
  return (
    <div className="pb-card p-4 space-y-3">
      <div className={cap}>{pillar ? 'EDIT THEME' : 'NEW THEME'}</div>
      <label className="block">
        <span className={`${cap} block mb-1`}>NAME *</span>
        <input autoFocus className={inp} value={form.name} placeholder="e.g. Community & Club Culture"
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
      </label>
      <label className="block">
        <span className={`${cap} block mb-1`}>DESCRIPTION</span>
        <textarea rows={2} className={inp} value={form.description}
          placeholder="What this theme covers, in a line."
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
      </label>
      <div className="flex items-center gap-2">
        <button disabled={busy || !form.name.trim()}
          onClick={async () => { setBusy(true); try { await onSave({ name: form.name.trim(), description: form.description || null }) } finally { setBusy(false) } }}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-50"
          style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
          {busy ? 'SAVING…' : 'SAVE'}
        </button>
        <button onClick={onCancel} disabled={busy}
          className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">
          Cancel
        </button>
      </div>
    </div>
  )
}

function StrategicPlansSection({ report, pillars, positions, members, memberName, onChanged, query = '' }) {
  const toast = useToast()
  const [openIds, setOpenIds] = useState(null)     // null until the first plan seeds it
  const [sel, setSel] = useState(null)
  const [workMode, setWorkMode] = useState('grouped')
  // The rail and the dashboard want the same width, and while a plan is open
  // the rail is redundant navigation — the dashboard IS a tree. So it folds
  // away rather than being split onto tabs of its own: the tree is how you
  // reorder and add, which is a different job from reading the plan, and two
  // more tabs would recreate the pick-between-three-views-of-one-thing the
  // Strategic Plans / Themes / Objectives row was removed for.
  const [railOpen, setRailOpen] = useState(true)
  const [editingPlan, setEditingPlan] = useState(null)
  const [addingPlan, setAddingPlan] = useState(false)
  const [editingObjective, setEditingObjective] = useState(null)
  const [addingObjectiveTo, setAddingObjectiveTo] = useState(null)
  const [editingTheme, setEditingTheme] = useState(null)
  // null, or { planId } — the plan the new theme is being added from, so it
  // can be selected under that plan once it exists.
  const [addingTheme, setAddingTheme] = useState(null)
  const [allTasks, setAllTasks] = useState([])
  // The row being dragged. `level` is what makes a drop legal: a plan only
  // lands among plans, a theme among themes, an objective among the objectives
  // of its OWN branch — dropping it under another theme would be a re-parent,
  // which is a different act from putting it in order.
  const [drag, setDrag] = useState(null)
  const [dropOn, setDropOn] = useState(null)

  // The waits-on list in the action editor should offer every action the club
  // holds, not only the ones already on a plan.
  useEffect(() => {
    api.committeeListTasks().then(d => setAllTasks(d.tasks || [])).catch(() => {})
  }, [])

  const plans = report.plans || []
  // Every objective is on a plan and under a theme (migration 276), so there
  // is no "Not on a plan" group and no "No theme" bucket — neither state can
  // exist. The tree is exactly plan → theme → objective.
  const groups = plans

  // Open the first plan and select it, once, when the tree first has one.
  useEffect(() => {
    if (openIds !== null || groups.length === 0) return
    setOpenIds(new Set([`plan:${groups[0].id}`]))
    setSel({ kind: 'plan', id: groups[0].id })
  }, [groups, openIds])

  const isOpen = k => !!openIds?.has(k)
  const toggle = k => setOpenIds(s => {
    const next = new Set(s || [])
    next.has(k) ? next.delete(k) : next.add(k)
    return next
  })
  const select = (kind, id, extra = {}) => setSel({ kind, id, ...extra })
  const isSel = (kind, id) => sel?.kind === kind && sel?.id === id

  const allObjectives = groups.flatMap(g => g.objective_list || [])

  // A theme belongs to ONE plan (migration 275), so a plan's themes are simply
  // the themes whose plan_id is this plan — including the ones with nothing
  // filed under them yet.
  //
  // This used to derive a plan's themes from its objectives, and fill an empty
  // plan from the club's whole set. Both were wrong for the same reason: a
  // theme was shared, so a second plan drew the first plan's themes, an
  // objective read as belonging to both, and deleting a theme from the second
  // plan's tree deleted the FIRST plan's objectives. There is no linkage
  // between one plan's hierarchy and another's.
  const themesIn = (plan) => {
    const objs = plan.objective_list || []
    return pillars
      .filter(p => p.plan_id === plan.id)
      .map(p => ({ id: p.id, name: p.name, rows: objs.filter(o => o.pillar_id === p.id) }))
  }

  // ── searching the tree ────────────────────────────────────────────────
  //
  // A search over a plan has to reach the work: an action or a motion is what
  // somebody remembers, and it sits two levels below the plan's own name. So a
  // branch is kept when ANYTHING under it matches, and every level is drawn
  // open while a query is running — otherwise a match three levels down is
  // found and then hidden behind two carets.
  //
  // The filtering is for DRAWING only. `groups`, `themesIn` and
  // `objectiveOrder` stay whole, or a reorder would renumber against a
  // filtered list and a selected row could stop resolving.
  const q = (query || '').trim().toLowerCase()
  const qHit = (...vals) => vals.some(v => v != null && String(v).toLowerCase().includes(q))
  const objMatches = o => qHit(o.title, o.description)
    || (o.action_list || []).some(a => qHit(a.title, a.description, a.outcome_notes))
    || (o.motion_list || []).some(m => qHit(m.description, m.notes))
  const shownThemes = plan => {
    const themes = themesIn(plan)
    if (!q) return themes
    return themes
      .map(t => (qHit(t.name) ? t : { ...t, rows: t.rows.filter(objMatches) }))
      .filter(t => qHit(t.name) || t.rows.length > 0)
  }
  const shownGroups = q
    ? groups.filter(p => qHit(p.name, p.description) || shownThemes(p).length > 0)
    : groups
  // A running query opens everything it left standing.
  const railOpenFor = k => (q ? true : isOpen(k))

  const objectiveById = id => allObjectives.find(o => o.id === id)
  const workById = (kind, id) => {
    for (const o of allObjectives) {
      const hit = (kind === 'action' ? o.action_list : o.motion_list)?.find(r => r.id === id)
      if (hit) return { row: hit, objective: o }
    }
    return null
  }

  /* ── deleting, with the cascade spelled out before it happens ─────────── */

  const tally = (objs) => {
    const a = objs.reduce((n, o) => n + (o.action_list || []).length, 0)
    const m = objs.reduce((n, o) => n + (o.motion_list || []).length, 0)
    return { a, m }
  }
  const keptLine = ({ a, m }) => {
    if (!a && !m) return ''
    const bits = []
    if (a) bits.push(`${a} action${a === 1 ? '' : 's'}`)
    if (m) bits.push(`${m} motion${m === 1 ? '' : 's'}`)
    return `\n\n${bits.join(' and ')} serving ${a + m === 1 ? 'it' : 'them'} will be KEPT — they simply stop being linked to an objective.`
  }

  async function removePlan(plan) {
    const objs = plan.objective_list || []
    const msg = `Delete “${plan.name}”?`
      + (objs.length
        ? `\n\nIts ${objs.length} objective${objs.length === 1 ? '' : 's'} go with it.` + keptLine(tally(objs))
        : '')
      + `\n\nIts themes go with it too — a theme belongs to one plan.\n\nThis cannot be undone.`
    if (!window.confirm(msg)) return
    try {
      await api.committeeDeletePlan(plan.id)
      setSel(null)
      onChanged()
    } catch (e) { toast.error(e.message) }
  }

  async function removeTheme(pillarId, name) {
    // A theme belongs to one plan, so this can only ever reach that plan's
    // objectives — it used to be club-scoped, and deleting a theme from one
    // plan's tree took another plan's work with it.
    const objs = allObjectives.filter(o => o.pillar_id === pillarId)
    const msg = `Delete the theme “${name}”?`
      + (objs.length
        ? `\n\nIts ${objs.length} objective${objs.length === 1 ? '' : 's'} go with it.`
          + keptLine(tally(objs))
        : '')
      + `\n\nThis cannot be undone.`
    if (!window.confirm(msg)) return
    try {
      await api.committeeDeletePillar(pillarId)
      setSel(null)
      onChanged()
    } catch (e) { toast.error(e.message) }
  }

  async function removeObjective(o) {
    const t = tally([o])
    const msg = `Delete “${o.title}”?` + keptLine(t) + `\n\nThis cannot be undone.`
    if (!window.confirm(msg)) return
    try {
      await api.committeeDeleteObjective(o.id)
      setSel(null)
      onChanged()
    } catch (e) { toast.error(e.message) }
  }

  async function savePlan(id, data) {
    try { await api.committeeUpdatePlan(id, data); toast.success('Plan saved'); setEditingPlan(null); onChanged() }
    catch (e) { toast.error(e.message) }
  }
  async function createPlan(data) {
    try {
      const made = await api.committeeCreatePlan(data)
      toast.success('Plan created')
      setAddingPlan(false)
      if (made?.id) {
        await spliceAfter(api.committeeReorderPlans, plans.map(p => p.id),
          sel?.kind === 'plan' ? sel.id : null, made.id)
        // Open what was just written, rather than leaving the pane on whatever
        // happened to be selected before.
        setSel({ kind: 'plan', id: made.id })
        setOpenIds(o => new Set([...(o || []), `plan:${made.id}`]))
      }
      onChanged()
    } catch (e) { toast.error(e.message) }
  }
  async function saveObjective(id, data) {
    try {
      if (id) await api.committeeUpdateObjective(id, data)
      else {
        const made = await api.committeeCreateObjective(data)
        if (made?.id) {
          await spliceAfter(api.committeeReorderObjectives, allObjectives.map(o => o.id),
            sel?.kind === 'objective' ? sel.id : null, made.id)
          setSel({ kind: 'objective', id: made.id })
          // Open the branch it landed in, so it is visible in the tree rather
          // than folded away under the theme it was just added to.
          const planId = data.plan_id || addingObjectiveTo?.planId || ''
          const pillarId = data.pillar_id || addingObjectiveTo?.pillarId || ''
          setOpenIds(o => new Set([...(o || []),
            `plan:${planId}`, `theme:${planId}:${pillarId}`, `obj:${made.id}`]))
        }
      }
      toast.success(id ? 'Objective saved' : 'Objective added')
      setEditingObjective(null); setAddingObjectiveTo(null); onChanged()
    } catch (e) { toast.error(e.message) }
  }
  async function saveTheme(id, data) {
    try {
      if (id) await api.committeeUpdatePillar(id, data)
      else {
        // The plan the new theme belongs to: the one it was added from, else
        // the plan of the theme that is selected. Never a positional guess —
        // a theme in the wrong plan is the failure 275 exists to prevent.
        const planId = addingTheme?.planId
          || (sel?.kind === 'theme' ? pillars.find(x => x.id === sel.id)?.plan_id : null)
          || sel?.planId || null
        const made = await api.committeeCreatePillar({ ...data, plan_id: planId })
        // A new theme lands directly below the one that was selected, so it
        // appears where the person was looking rather than at the bottom.
        if (made?.id) {
          await spliceAfter(api.committeeReorderPillars, pillars.map(x => x.id),
            sel?.kind === 'theme' ? sel.id : null, made.id)
          // Selected under the plan it was added from, so the pane can offer
          // "+ OBJECTIVE" against the right plan straight away.
          setSel({ kind: 'theme', id: made.id, planId })
          setOpenIds(o => new Set([...(o || []), `plan:${planId}`, `theme:${planId}:${made.id}`]))
        }
      }
      toast.success(id ? 'Theme saved' : 'Theme added')
      setEditingTheme(null); setAddingTheme(null); onChanged()
    } catch (e) { toast.error(e.message) }
  }

  // Put `newId` straight after `afterId` in a level's order and persist it.
  // Everything at that level is sent, since sort_order is club-wide.
  async function spliceAfter(reorder, ids, afterId, newId) {
    const rest = ids.filter(i => i !== newId)
    const at = afterId ? rest.indexOf(afterId) : -1
    const next = at >= 0 ? [...rest.slice(0, at + 1), newId, ...rest.slice(at + 1)] : [...rest, newId]
    await reorder(next).catch(() => {})
  }

  // The tree's own order for each level, which is what gets persisted: a move
  // inside one theme still sends every objective, since sort_order is club-wide
  // and renumbering one group alone would interleave it with another's.
  const planOrder = plans.map(p => p.id)
  const pillarOrder = pillars.map(p => p.id)
  const objectiveOrder = groups.flatMap(g => themesIn(g).flatMap(th => th.rows.map(o => o.id)))

  const REORDER = {
    plan: [() => planOrder, api.committeeReorderPlans],
    theme: [() => pillarOrder, api.committeeReorderPillars],
    objective: [() => objectiveOrder, api.committeeReorderObjectives],
  }

  async function moveWithin(level, fromId, toId) {
    setDrag(null); setDropOn(null)
    if (!fromId || fromId === toId) return
    const [orderOf, reorder] = REORDER[level]
    const rest = orderOf().filter(i => i !== fromId)
    const at = rest.indexOf(toId)
    if (at < 0) return
    try {
      await reorder([...rest.slice(0, at), fromId, ...rest.slice(at)])
      onChanged()
    } catch (e) { toast.error(e.message) }
  }

  // A row can only be dropped on a sibling: same level, same branch, and never
  // on itself. Anything else does not preventDefault, so the cursor says no
  // before the mouse is released rather than the drop silently doing nothing.
  const dragProps = (level, id, branch) => ({
    draggable: true,
    onDragStart: e => { e.stopPropagation(); e.dataTransfer.effectAllowed = 'move'; setDrag({ level, id, branch }) },
    onDragEnd: () => { setDrag(null); setDropOn(null) },
    onDragOver: e => {
      if (!drag || drag.level !== level || drag.branch !== branch || drag.id === id) return
      e.preventDefault(); e.dataTransfer.dropEffect = 'move'
      if (dropOn !== id) setDropOn(id)
    },
    onDragLeave: () => setDropOn(d => (d === id ? null : d)),
    onDrop: e => {
      if (!drag || drag.level !== level || drag.branch !== branch) return
      e.preventDefault(); e.stopPropagation()
      moveWithin(level, drag.id, id)
    },
  })
  const dragStyle = (level, id) => ({
    cursor: 'grab',
    opacity: drag?.id === id && drag?.level === level ? 0.45 : 1,
    boxShadow: dropOn === id && drag && drag.id !== id ? 'inset 0 2px 0 var(--pb-accent)' : undefined,
  })

  // Which level the rail's add button offers, and what pressing it opens.
  const addLevel = sel?.kind === 'theme' ? 'theme'
    : ['objective', 'action', 'motion'].includes(sel?.kind) ? 'objective'
      : 'plan'
  function startAdd() {
    setEditingPlan(null); setEditingObjective(null); setEditingTheme(null)
    setAddingPlan(false); setAddingTheme(null); setAddingObjectiveTo(null)
    if (addLevel === 'plan') setAddingPlan(true)
    else if (addLevel === 'theme') {
      setAddingTheme({ planId: pillars.find(x => x.id === sel?.id)?.plan_id || sel?.planId || null })
    }
    else {
      // Under the objective that is selected, so it lands in the same branch.
      const near = sel?.kind === 'objective' ? objectiveById(sel.id)
        : workById(sel.kind, sel.id)?.objective
      setAddingObjectiveTo({ planId: near?.plan_id || '', pillarId: near?.pillar_id || null })
    }
  }

  /* ── the tree ─────────────────────────────────────────────────────────── */

  const tree = (
    <div className="space-y-1">
      {shownGroups.map(plan => {
        const pk = `plan:${plan.id}`
        const themes = shownThemes(plan)
        return (
          <div key={plan.id || '__none'}>
            <div className={`${TREE_ROW} ${isSel('plan', plan.id) ? 'bg-pb-surface2' : ''}`}
              {...(plan.id ? dragProps('plan', plan.id, 'plans') : {})}
              title={plan.id ? 'Drag to reorder' : undefined}
              style={{
                ...(isSel('plan', plan.id) ? { boxShadow: 'inset 2px 0 0 var(--pb-accent)' } : {}),
                ...(plan.id ? dragStyle('plan', plan.id) : {}),
              }}>
              <Twisty open={railOpenFor(pk)} hidden={themes.length === 0} onToggle={() => toggle(pk)} />
              <button onClick={() => select('plan', plan.id)} className="min-w-0 flex-1 text-left">
                <TreeLabel kind={plan.id ? 'PLAN' : ''} active={isSel('plan', plan.id)}>{plan.name}</TreeLabel>
              </button>
              {plan.id && <DelDot onClick={() => removePlan(plan)} title={`Delete ${plan.name}`} />}
            </div>

            {railOpenFor(pk) && themes.map(th => {
              const tk = `theme:${plan.id}:${th.id}`
              return (
                <div key={tk} className={TREE_STEP}>
                  <div className={`${TREE_ROW} ${isSel('theme', th.id) ? 'bg-pb-surface2' : ''}`}
                    {...dragProps('theme', th.id, `themes:${plan.id}`)}
                    title="Drag to reorder"
                    style={{
                      ...(isSel('theme', th.id) ? { boxShadow: 'inset 2px 0 0 var(--pb-accent)' } : {}),
                      ...dragStyle('theme', th.id),
                    }}>
                    <Twisty open={railOpenFor(tk)} onToggle={() => toggle(tk)} />
                    <button onClick={() => select('theme', th.id, { planId: plan.id })}
                      className="min-w-0 flex-1 text-left">
                      <TreeLabel kind="THEME" active={isSel('theme', th.id)} dim={th.rows.length === 0}>
                        {th.name}
                      </TreeLabel>
                    </button>
                    <DelDot onClick={() => removeTheme(th.id, th.name)} title={`Delete ${th.name}`} />
                  </div>

                  {railOpenFor(tk) && th.rows.map(o => {
                    const ok = `obj:${o.id}`
                    const work = workRows(o, workMode)
                    return (
                      <div key={o.id} className={TREE_STEP}>
                        <div className={`${TREE_ROW} ${isSel('objective', o.id) ? 'bg-pb-surface2' : ''}`}
                          {...dragProps('objective', o.id, `objs:${plan.id}:${th.id}`)}
                          title="Drag to reorder"
                          style={{
                            ...(isSel('objective', o.id) ? { boxShadow: 'inset 2px 0 0 var(--pb-accent)' } : {}),
                            ...dragStyle('objective', o.id),
                          }}>
                          <Twisty open={railOpenFor(ok)} hidden={work.length === 0} onToggle={() => toggle(ok)} />
                          <button onClick={() => select('objective', o.id)} className="min-w-0 flex-1 text-left">
                            <TreeLabel kind="OBJECTIVE" active={isSel('objective', o.id)}>{o.title}</TreeLabel>
                          </button>
                          <DelDot onClick={() => removeObjective(o)} title={`Delete ${o.title}`} />
                        </div>
                        {railOpenFor(ok) && (
                          <div className={TREE_STEP}>
                            {work.map(r => (
                              <button key={`${r._kind}-${r.id}`} onClick={() => select(r._kind, r.id)}
                                className={`${TREE_ROW} ${isSel(r._kind, r.id) ? 'bg-pb-surface2' : ''}`}
                                style={isSel(r._kind, r.id) ? { boxShadow: 'inset 2px 0 0 var(--pb-accent)' } : undefined}>
                                <Twisty hidden />
                                <TreeLabel kind={r._kind === 'action' ? 'ACTION' : 'MOTION'} active={isSel(r._kind, r.id)}>
                                  {r._label}
                                </TreeLabel>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </div>
        )
      })}
      {groups.length === 0 && (
        <div className="text-pb-faint text-[13px] px-1.5 py-3 leading-relaxed">
          No plans written down yet.
        </div>
      )}
      {groups.length > 0 && shownGroups.length === 0 && (
        <div className="text-pb-faint text-[13px] px-1.5 py-3 leading-relaxed">
          Nothing in the plans matches “{query}”.
        </div>
      )}
    </div>
  )

  /* ── the pane ─────────────────────────────────────────────────────────── */

  let pane = <div className="text-pb-faint text-[13px]">Pick something on the left to open it.</div>

  const adding = addingPlan || addingTheme || !!addingObjectiveTo
  if (addingPlan) {
    pane = <div className="max-w-3xl"><PlanForm onSave={createPlan} onCancel={() => setAddingPlan(false)} /></div>
  } else if (addingTheme) {
    pane = <div className="max-w-3xl"><ThemeForm onSave={d => saveTheme(null, d)} onCancel={() => setAddingTheme(null)} /></div>
  } else if (addingObjectiveTo) {
    pane = (
      <div className="max-w-3xl">
        <ObjectiveForm plans={plans} pillars={pillars} positions={positions}
          planId={addingObjectiveTo.planId} pillarId={addingObjectiveTo.pillarId}
          members={members} onSave={d => saveObjective(null, d)}
          onCancel={() => setAddingObjectiveTo(null)} />
      </div>
    )
  } else if (sel?.kind === 'plan') {
    const plan = groups.find(g => g.id === sel.id)
    if (plan && editingPlan === plan.id) {
      pane = <PlanForm plan={plan} onSave={d => savePlan(plan.id, d)} onCancel={() => setEditingPlan(null)} />
    } else if (plan) {
      const objs = plan.objective_list || []
      pane = (
        <div className="space-y-5 max-w-3xl">
          <div className="pb-card p-4 sm:p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className={`${cap} mb-1`}>{plan.id ? 'STRATEGIC PLAN' : ''}</div>
                <h2 className="text-pb-text text-[21px] font-bold leading-tight">{plan.name}</h2>
                <div className={`${cap} mt-1`}>
                  {[plan.start_year && plan.end_year ? `${plan.start_year}–${plan.end_year}` : (plan.start_year || null),
                    `${objs.length} OBJECTIVE${objs.length === 1 ? '' : 'S'}`,
                    plan.late_objectives ? `${plan.late_objectives} LATE` : null].filter(Boolean).join(' · ')}
                </div>
              </div>
              {plan.id && (
                <div className="flex gap-2 shrink-0">
                  <button onClick={() => setEditingPlan(plan.id)}
                    className="font-mono text-[9px] text-pb-faint hover:text-pb-text">Edit</button>
                  <button onClick={() => removePlan(plan)}
                    className="font-mono text-[9px] text-pb-faintest hover:text-pb-red">Delete</button>
                </div>
              )}
            </div>

            {/* One summary, not two. This used to be four tiles of its own
                (objectives done / progress / budget / spent) with the delivery
                dashboard repeating them in a second card directly underneath —
                the same figures twice, and disagreeing on the percentage
                because each side worked it out its own way. */}
            {plan.id
              ? <PlanFigures plan={plan} pillars={pillars} />
              : (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-5">
                  <StatTile value={`${plan.objectives_done || 0}/${objs.length}`} label="OBJECTIVES DONE" />
                  <StatTile value={`${plan.percent_complete || 0}%`} label="PROGRESS" />
                  <StatTile value={money(plan.budget || 0)} label="BUDGET" />
                  <StatTile value={money(plan.spent || 0)} label="SPENT"
                    tone={plan.over_budget ? 'var(--pb-red-ink)' : undefined} />
                </div>
              )}
          </div>

          {plan.description && (
            <div className="pb-card p-4">
              <div className={`${cap} mb-1.5`}>DESCRIPTION</div>
              <div className="text-pb-dim text-[13px] leading-relaxed whitespace-pre-wrap">{plan.description}</div>
            </div>
          )}

          {/* The pane adds the level BELOW what it is showing, because the
              structure is plan → theme → objective. The rail's button adds at
              the level you are standing on. */}
          {/* How the plan is actually going, under the figures that summarise
              it: what needs attention first, then a row per theme that opens
              onto its objectives. Actions and motions are a further click, so
              the page opens as a plan rather than as everything filed against
              one. */}
          {plan.id && <PlanDelivery plan={plan} pillars={pillars} />}

          {plan.id && (
            <button onClick={() => { setAddingTheme({ planId: plan.id }); setAddingObjectiveTo(null) }}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold self-start"
              style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>+ THEME</button>
          )}
        </div>
      )
    }
  }

  if (!adding && sel?.kind === 'theme') {
    const p = pillars.find(x => x.id === sel.id)
    const objs = allObjectives.filter(o => o.pillar_id === sel.id)
    const ownPlan = plans.find(pl => pl.id === p?.plan_id)
    const done = objs.filter(o => (o.percent_complete || 0) >= 100).length
    const pct = objs.length ? Math.round(objs.reduce((n, o) => n + (o.percent_complete || 0), 0) / objs.length) : 0
    if (p && editingTheme === p.id) {
      pane = <div className="max-w-3xl"><ThemeForm pillar={p} onSave={d => saveTheme(p.id, d)}
        onCancel={() => setEditingTheme(null)} /></div>
    } else pane = p && (
      <div className="space-y-5 max-w-3xl">
        <div className="pb-card p-4 sm:p-5">
          {/* No flex-wrap: the actions belong in the corner, and wrapping put
              them under the meta line instead. */}
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className={`${cap} mb-1`}>THEME</div>
              <h2 className="text-pb-text text-[21px] font-bold leading-tight">{p.name}</h2>
              {/* One plan, always — which is the whole point of 275. */}
              <div className={`${cap} mt-1`}>
                {(ownPlan?.name || 'NOT ON A PLAN').toUpperCase()}
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              <button onClick={() => setEditingTheme(p.id)}
                className="font-mono text-[9px] text-pb-faint hover:text-pb-text">Edit</button>
              <button onClick={() => removeTheme(p.id, p.name)}
                className="font-mono text-[9px] text-pb-faintest hover:text-pb-red">Delete</button>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 mt-5">
            <StatTile value={`${done}/${objs.length}`} label="OBJECTIVES DONE" />
            <StatTile value={`${pct}%`} label="PROGRESS" />
            <StatTile value={String(tally(objs).a + tally(objs).m)} label="ACTIONS & MOTIONS" />
          </div>
          <div className="mt-4"><Bar percent={pct} /></div>
        </div>
        {/* The level below a theme, added against the plan it is being read
            under — a theme belongs to the club, so the plan has to come from
            where you are rather than from the theme itself. */}
        <button onClick={() => setAddingObjectiveTo({ planId: p.plan_id || '', pillarId: p.id })}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold"
          style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>+ OBJECTIVE</button>
        {p.description && (
          <div className="pb-card p-4">
            <div className={`${cap} mb-1.5`}>DESCRIPTION</div>
            <div className="text-pb-dim text-[13px] leading-relaxed whitespace-pre-wrap">{p.description}</div>
          </div>
        )}
        <div className="pb-card p-4">
          <div className={`${cap} mb-2`}>OBJECTIVES UNDER THIS THEME</div>
          {objs.length === 0 ? (
            <div className="font-mono text-[10px] text-pb-faintest">Nothing filed under it yet.</div>
          ) : (
            <div className="space-y-1">
              {objs.map(o => (
                <button key={o.id} onClick={() => select('objective', o.id)}
                  className="w-full text-left text-[12.5px] text-pb-dim hover:text-pb-text leading-snug">
                  {o.title}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  if (!adding && sel?.kind === 'objective') {
    const o = objectiveById(sel.id)
    if (o && editingObjective === o.id) {
      pane = <ObjectiveForm objective={o} plans={plans} pillars={pillars} positions={positions}
        members={members} onSave={d => saveObjective(o.id, d)} onCancel={() => setEditingObjective(null)} />
    } else if (o) {
      const work = workRows(o, workMode)
      pane = (
        <div className="space-y-5 max-w-3xl">
          <div className="pb-card p-4 sm:p-5">
            {/* No flex-wrap here either — Edit and Delete were ending up under
                the owner line instead of in the corner. */}
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className={`${cap} mb-1`}>
                  {[o.plan_name, o.pillar_name].filter(Boolean).map(x => x.toUpperCase()).join(' › ') || 'OBJECTIVE'}
                </div>
                <h2 className="text-pb-text text-[19px] font-bold leading-snug flex items-start gap-2 flex-wrap">
                  {o.title}<LateTag row={o} />
                </h2>
                <div className={`${cap} mt-1 flex flex-wrap gap-x-2`}>
                  {o.owner_position_name && <span>{o.owner_position_name.toUpperCase()}</span>}
                  {!o.owner_position_name && o.owner_member_id && <span>{memberName(o.owner_member_id).toUpperCase()}</span>}
                  {o.due_date && <span>DUE {o.due_date}</span>}
                </div>
              </div>
              <div className="flex gap-2 shrink-0">
                <button onClick={() => setEditingObjective(o.id)}
                  className="font-mono text-[9px] text-pb-faint hover:text-pb-text">Edit</button>
                <button onClick={() => removeObjective(o)}
                  className="font-mono text-[9px] text-pb-faintest hover:text-pb-red">Delete</button>
              </div>
            </div>
            {o.description && <div className="text-pb-faint text-[12.5px] mt-2 leading-relaxed">{o.description}</div>}
            <Delivery row={o} level="objective" />
          </div>

          <div className="pb-card p-4">
            <div className="flex items-center justify-between gap-2 flex-wrap mb-2">
              <div className={cap}>THE WORK SERVING IT</div>
              <span className={cap}>{workMode === 'date' ? 'IN THE ORDER RAISED' : 'ACTIONS, THEN MOTIONS'}</span>
            </div>
            {work.length === 0 ? (
              <div className="font-mono text-[10px] text-pb-faintest">
                Nothing points at this objective yet.
              </div>
            ) : (
              <div className="space-y-1">
                {work.map(r => (
                  <button key={`${r._kind}-${r.id}`} onClick={() => select(r._kind, r.id)}
                    className="w-full text-left flex items-start gap-2 hover:bg-pb-surface2 rounded px-1 py-1">
                    <span className={`${cap} w-12 shrink-0 pt-0.5`}>{r._kind === 'action' ? 'ACTION' : 'MOTION'}</span>
                    <span className="text-[12.5px] text-pb-dim leading-snug flex-1 min-w-0">{r._label}</span>
                    {r.meeting_date && <span className={`${cap} shrink-0 pt-0.5`}>{r.meeting_date}</span>}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="pb-card p-4"><NoteThread entityType="objective" entityId={o.id} /></div>
        </div>
      )
    }
  }

  if (!adding && sel?.kind === 'action') {
    const hit = workById('action', sel.id)
    // The report's row carries the plan context; the tasks fetch carries the
    // dependencies. Merge, so the editor has both.
    const task = hit && { ...hit.row, ...(allTasks.find(t => t.id === sel.id) || {}) }
    pane = task
      ? <div className="max-w-3xl"><ActionEditor key={task.id} task={task} allTasks={allTasks}
          objectives={allObjectives} members={members} inline
          onSaved={onChanged} onDeleted={() => { setSel(null); onChanged() }} /></div>
      : <div className="text-pb-faint text-[13px]">That action is no longer on the plan.</div>
  }

  if (!adding && sel?.kind === 'motion') {
    const hit = workById('motion', sel.id)
    pane = hit
      ? <div className="max-w-3xl"><MotionEditor key={hit.row.id} meetingId={hit.row.meeting_id}
          motion={hit.row} members={members} objectives={allObjectives} inline
          onSaved={onChanged} onDeleted={() => { setSel(null); onChanged() }} /></div>
      : <div className="text-pb-faint text-[13px]">That motion is no longer on the plan.</div>
  }

  return (
    // Two panes side by side where there is room for them; on a phone the tree
    // sits above what it opens, because 320px of rail leaves a detail pane too
    // narrow to read and pushes the page sideways.
    <div className="flex flex-col lg:flex-row flex-1 min-h-0">
      {!railOpen && (
        <button type="button" onClick={() => setRailOpen(true)}
          className="shrink-0 border-b lg:border-b-0 lg:border-r pb-hairline px-2 py-2
            text-left font-mono text-[10px] tracking-wide2 text-pb-faint hover:text-pb-text hover:bg-pb-surface2">
          <span aria-hidden="true">›</span> PLAN STRUCTURE
        </button>
      )}
      <div className={`pb-scroll w-full lg:w-[320px] lg:shrink-0 max-h-[45vh] lg:max-h-none
        border-b lg:border-b-0 lg:border-r pb-hairline overflow-y-auto p-3 ${railOpen ? '' : 'hidden'}`}>
        <div className="flex items-center gap-2 mb-2">
          <button type="button" onClick={() => setRailOpen(false)}
            title="Hide the plan structure" aria-label="Hide the plan structure"
            className="font-mono text-[12px] text-pb-faint hover:text-pb-text leading-none">‹</button>
          <span className={cap}>STRATEGIC PLANS</span>
          {/* Adding at the level you are standing on: a plan when a plan is
              selected, a theme under a theme, an objective under an objective.
              Selecting an action or a motion still offers an objective, since
              that is the nearest level anything can be added at. */}
          <button onClick={startAdd} title={`Add a ${addLevel}`}
            className="ml-auto font-mono text-[10px] font-semibold px-2 py-1 rounded"
            style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
            + {addLevel.toUpperCase()}
          </button>
        </div>
        {/* How the work under an objective is laid out. Both readings are
            useful, so it is a toggle rather than a decision made for them. */}
        <div className="flex gap-1 mb-3">
          {[['grouped', 'Grouped'], ['date', 'By date']].map(([k, l]) => (
            <button key={k} onClick={() => setWorkMode(k)}
              className={`px-2 py-1 rounded text-[11.5px] ${workMode === k ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}>{l}</button>
          ))}
        </div>
        {tree}
        {groups.length > 0 && (
          <div className={`${cap} mt-3`}>DRAG A ROW TO REORDER IT WITHIN ITS OWN LEVEL</div>
        )}
      </div>
      <div className="pb-scroll flex-1 min-w-0 overflow-y-auto p-5 sm:p-6">{pane}</div>
    </div>
  )
}

/* ── The Plan tab ───────────────────────────────────────────────────────── */

/* ── The club's themes ──────────────────────────────────────────────────────
 *
 * A pillar groups objectives; it is NOT another level of the hierarchy. So it
 * shows as a filter above the plans and a heading inside one, and the plan →
 * objective → action indent stays three deep.
 */
// The theme filter above a list of objectives. It only FILTERS since migration
// 275 — a theme belongs to a plan, so creating, renaming and deleting one
// happens in Strategic Plans or on the Themes screen, where the plan it belongs
// to is on screen. A bar of chips has nowhere to say which plan it means.
function PillarBar({ pillars, active, onPick }) {
  if (!pillars.length) return null
  return (
    <div className="mb-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className={cap}>THEME</span>
        <button onClick={() => onPick(null)}
          className={`px-2.5 py-1 rounded-full text-[12px] border ${!active ? 'text-pb-text' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
          style={!active ? { borderColor: mix(55), background: mix(10) } : undefined}>All</button>
        {pillars.map(p => (
          <span key={p.id} className="inline-flex items-center">
            <button onClick={() => onPick(active === p.id ? null : p.id)}
              className={`px-2.5 py-1 rounded-full text-[12px] border ${active === p.id ? 'text-pb-text' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
              style={active === p.id ? { borderColor: mix(55), background: mix(10) } : undefined}>
              {p.name}
            </button>
          </span>
        ))}
      </div>
    </div>
  )
}


/* ── Themes, on their own screen ────────────────────────────────────────── */

// The theme chips above the plans are a FILTER that happens to be editable.
// This is the same rows read as a catalogue: what the club groups its work
// under, how much work sits under each, and the rename/delete that goes with
// owning a list. Since migration 276 a theme belongs to one plan and owns its
// objectives, so deleting one takes that plan's objectives under it with it —
// the confirm says so, and the actions and motions serving them are kept.
function ThemesSection({ pillars, plans, onChanged }) {
  const toast = useToast()
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)

  const all = plans.flatMap(p => p.objective_list || [])
  const count = id => all.filter(o => o.pillar_id === id).length

  // A theme belongs to a plan, so this screen has to say which — there is no
  // such thing as a club-wide theme.
  const [planId, setPlanId] = useState('')
  useEffect(() => { setPlanId(id => id || plans[0]?.id || '') }, [plans])

  async function add() {
    if (!draft.trim() || !planId) return
    setBusy(true)
    try { await api.committeeCreatePillar({ name: draft.trim(), plan_id: planId }); setDraft(''); onChanged() }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function rename(pl) {
    const name = prompt('Rename this theme', pl.name)
    if (!name || !name.trim() || name === pl.name) return
    try { await api.committeeUpdatePillar(pl.id, { name: name.trim() }); onChanged() }
    catch (e) { toast.error(e.message) }
  }
  async function remove(pl) {
    const n = count(pl.id)
    if (!confirm(`Delete "${pl.name}"?${n ? ` Its ${n} objective${n === 1 ? '' : 's'} go with it. Any actions and motions serving them are kept, they simply stop being linked.` : ''}`)) return
    try { await api.committeeDeletePillar(pl.id); onChanged() } catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      <p className="text-pb-faint text-[13px] mb-4 max-w-2xl leading-relaxed">
        The headings a plan groups its objectives under — participation, finances, volunteers,
        facilities, or whatever your own plan is built around. A theme belongs to one plan, and
        the objectives under it belong to that plan too.
      </p>

      <div className="flex flex-wrap gap-2 mb-4 max-w-2xl">
        <input className={`${inp} flex-1 min-w-[14rem]`} placeholder="New theme, e.g. Facilities &amp; community"
          value={draft} onChange={e => setDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') add() }} />
        <select className={`${inp} sm:w-56`} value={planId} onChange={e => setPlanId(e.target.value)}>
          {plans.length === 0 && <option value="">No plans yet</option>}
          {plans.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button onClick={add} disabled={busy || !draft.trim() || !planId}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-40 whitespace-nowrap"
          style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>+ THEME</button>
      </div>

      {pillars.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-[13px]">
          No themes yet. Add one above and your objectives can be grouped under it.
        </div>
      ) : (
        <div className="space-y-2 max-w-2xl">
          {pillars.map(pl => (
            <div key={pl.id} className="pb-card p-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <div className="text-pb-text font-semibold text-[15px]">{pl.name}</div>
                <div className={`${cap} mt-0.5`}>
                  {(plans.find(p => p.id === pl.plan_id)?.name || 'Plan').toUpperCase()}
                  {' · '}
                  {count(pl.id)} {count(pl.id) === 1 ? 'OBJECTIVE' : 'OBJECTIVES'}
                </div>
              </div>
              <div className="flex gap-2 shrink-0">
                <button onClick={() => rename(pl)} className="font-mono text-[9px] text-pb-faint hover:text-pb-text">Rename</button>
                <button onClick={() => remove(pl)} className="font-mono text-[9px] text-pb-faintest hover:text-pb-red">Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


export function PlanTab({ members, section, query = '' }) {
  const toast = useToast()
  const [report, setReport] = useState(null)
  const [positions, setPositions] = useState([])
  const [addingPlan, setAddingPlan] = useState(false)
  const [editingPlan, setEditingPlan] = useState(null)
  const [addingObjectiveTo, setAddingObjectiveTo] = useState(null)   // the plan id being added under
  const [openPlan, setOpenPlan] = useState(null)
  const [view, setView] = useState('plan')                            // plan | delivery
  const [pillarFilter, setPillarFilter] = useState(null)
  const [seeding, setSeeding] = useState(false)

  const load = useCallback(() => {
    api.committeePlanReport()
      .then(setReport)
      .catch(e => { toast.error(e.message); setReport({ plans: [], pillars: [] }) })
  }, [toast])
  useEffect(() => { load() }, [load])
  // Committee seats, for the owner picker. Small list, fetched once.
  useEffect(() => {
    api.committeeListPositions().then(d => setPositions(d.positions || [])).catch(() => {})
  }, [])

  async function seedStarter() {
    setSeeding(true)
    try {
      const r = await api.committeeSeedStarterPlan()
      toast.success(r.created_plan ? 'Added a plan to edit' : 'You already have this year\'s plan')
      setOpenPlan(r.plan?.id || null)
      load()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }

  const memberName = useCallback(
    id => (members || []).find(m => m.member_id === id)?.full_name || 'Someone',
    [members])

  async function createPlan(data) {
    try { await api.committeeCreatePlan(data); toast.success('Plan created'); setAddingPlan(false); load() }
    catch (e) { toast.error(e.message) }
  }
  async function savePlan(id, data) {
    try { await api.committeeUpdatePlan(id, data); toast.success('Plan saved'); setEditingPlan(null); load() }
    catch (e) { toast.error(e.message) }
  }
  async function removePlan(p) {
    if (!confirm(`Delete "${p.name}"? Its themes and objectives go with it. Any actions and motions serving them are kept, they simply stop being linked.`)) return
    try { await api.committeeDeletePlan(p.id); load() } catch (e) { toast.error(e.message) }
  }
  async function createObjective(data) {
    try { await api.committeeCreateObjective(data); toast.success('Objective added'); setAddingObjectiveTo(null); load() }
    catch (e) { toast.error(e.message) }
  }

  if (report === null) return <div className="font-mono text-[11px] text-pb-faint">Loading the plan…</div>

  const plans = report.plans || []
  const pillars = report.pillars || []
  const objectiveProps = { plans, pillars, positions, members, memberName, onChanged: load }
  // The theme filter narrows what is shown; it never changes what is stored.
  const inTheme = o => !pillarFilter || o.pillar_id === pillarFilter
  // Objectives within a plan, grouped under their theme, in the club's own
  // pillar order. Every objective is under a theme (migration 276); a row whose
  // theme this payload doesn't carry is a load ordering problem, not a state
  // the club can be in, so it is named as one rather than filed under "none".
  const byTheme = list => {
    const shown = list.filter(inTheme)
    const groups = pillars
      .map(p => ({ id: p.id, name: p.name, rows: shown.filter(o => o.pillar_id === p.id) }))
      .filter(g => g.rows.length)
    const loose = shown.filter(o => !pillars.some(p => p.id === o.pillar_id))
    if (loose.length) groups.push({ id: '', name: 'Theme not loaded', rows: loose })
    return groups
  }

  // `section` splits this one screen into the three things it holds, for a
  // caller that draws its own buttons (BetterAdmin → Committee → Plans).
  // Passing nothing keeps the whole tab as it was, which is what the manage
  // screen still renders.
  if (section === 'plans') {
    return (
      <StrategicPlansSection report={report} pillars={pillars} positions={positions}
        members={members} memberName={memberName} onChanged={load} query={query} />
    )
  }

  if (section === 'themes') {
    return <ThemesSection pillars={pillars} plans={plans} onChanged={load} />
  }

  if (section === 'objectives') {
    // Every objective the club holds, in one list rather than one plan at a
    // time — the way "what are we actually committed to" gets asked. Each still
    // says which plan it belongs to, so flattening loses nothing.
    const rows = plans.flatMap(pl =>
      (pl.objective_list || []).map(o => ({ ...o, plan_name: o.plan_name || pl.name })))
    return (
      <div>
        <p className="text-pb-faint text-[13px] mb-4 max-w-2xl leading-relaxed">
          Every objective across every plan. The actions and motions serving each one are folded
          away underneath it, and the figures add up from the register the committee already keeps.
        </p>
        <PillarBar pillars={pillars} active={pillarFilter} onPick={setPillarFilter} />
        <div className="flex flex-wrap items-center gap-2 mb-4">
          {!addingObjectiveTo && addingObjectiveTo !== '' && (
            <button onClick={() => setAddingObjectiveTo('')}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold ml-auto"
              style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>+ OBJECTIVE</button>
          )}
        </div>
        <div className="space-y-2">
          {addingObjectiveTo === '' && (
            <ObjectiveForm plans={plans} pillars={pillars} positions={positions}
              planId="" pillarId={pillarFilter} members={members}
              onSave={createObjective} onCancel={() => setAddingObjectiveTo(null)} />
          )}
          {byTheme(rows).map(g => (
            <div key={g.id || '__none'} className="space-y-2">
              {g.name && <div className={`${cap} pt-1`}>{g.name.toUpperCase()}</div>}
              {g.rows.map(o => <ObjectiveCard key={o.id} objective={o} {...objectiveProps} />)}
            </div>
          ))}
          {rows.filter(inTheme).length === 0 && addingObjectiveTo !== '' && (
            <div className="pb-card p-6 text-center text-pb-dim text-[13px]">
              {pillarFilter ? 'No objectives under that theme.' : 'No objectives written down yet.'}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div>
      <p className="text-pb-faint text-[13px] mb-4 max-w-2xl leading-relaxed">
        The club's strategic plans, the objectives in each, and the actions and motions doing the work.
        Everything below adds up from the register the committee already keeps, so the plan reports
        against itself rather than a spreadsheet nobody updates.
      </p>

      {view === 'plan' && (
        <PillarBar pillars={pillars} active={pillarFilter} onPick={setPillarFilter} />
      )}

      <div className="flex flex-wrap items-center gap-2 mb-4">
        {[['plan', 'By plan'], ['delivery', 'All work']].map(([k, l]) => (
          <button key={k} onClick={() => setView(k)}
            className={`px-3 py-1.5 rounded text-[12.5px] font-semibold ${view === k ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}>{l}</button>
        ))}
        {view === 'plan' && !addingPlan && (
          <button onClick={() => { setAddingPlan(true); setEditingPlan(null) }}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold ml-auto"
            style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>+ STRATEGIC PLAN</button>
        )}
      </div>

      {view === 'delivery'
        ? <DeliveryRegister report={report} memberName={memberName} onChanged={load} />
        : (
          <div className="space-y-3">
            {addingPlan && (
              <PlanForm onSave={createPlan} onCancel={() => setAddingPlan(false)} />
            )}

            {plans.length === 0 && !addingPlan && (
              <div className="pb-card p-6 text-center">
                <div className="text-pb-text text-[13px] mb-1">No plan yet.</div>
                <div className="font-mono text-[11px] text-pb-faintest mb-3 max-w-md mx-auto leading-relaxed">
                  Start from a filled-in one and change what does not fit. It sets up
                  four themes, a plan for this year, and an example objective under each.
                </div>
                <button onClick={seedStarter} disabled={seeding}
                  className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-40"
                  style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
                  {seeding ? 'SETTING UP…' : 'START ME OFF'}
                </button>
                <div className="font-mono text-[10px] text-pb-faintest mt-2">
                  Or use + STRATEGIC PLAN above to write your own.
                </div>
              </div>
            )}

            {plans.map(p => editingPlan === p.id ? (
              <PlanForm key={p.id} plan={p} onSave={d => savePlan(p.id, d)} onCancel={() => setEditingPlan(null)} />
            ) : (
              <div key={p.id} className="pb-card p-4 border-l-2" style={{ borderLeftColor: LEVEL.plan.rail }}>
                <div className="flex items-start justify-between gap-3 flex-wrap">
                  <div className="min-w-0">
                    <div className={`${cap} mb-0.5`}>STRATEGIC PLAN</div>
                    <div className="text-pb-text font-semibold text-[17px]">{p.name}</div>
                    <div className={`${cap} mt-0.5`}>
                      {[p.start_year, p.end_year].filter(Boolean).join('–') || 'NO DATES SET'}
                      {' · '}{p.objectives} {p.objectives === 1 ? 'OBJECTIVE' : 'OBJECTIVES'}
                      {p.late_objectives > 0 ? ` · ${p.late_objectives} LATE` : ''}
                    </div>
                    {p.description && <div className="text-pb-faint text-[12.5px] mt-1">{p.description}</div>}
                  </div>
                  <div className="flex gap-2 shrink-0">
                    <button onClick={() => { setEditingPlan(p.id); setAddingPlan(false) }}
                      className="font-mono text-[9px] text-pb-faint hover:text-pb-text">Edit</button>
                    <button onClick={() => removePlan(p)}
                      className="font-mono text-[9px] text-pb-faintest hover:text-pb-red">Delete</button>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
                  {[
                    { v: `${p.objectives_done}/${p.objectives}`, l: 'OBJECTIVES DONE' },
                    { v: pct(p.percent_complete), l: 'PROGRESS' },
                    { v: money(p.budget), l: 'BUDGET' },
                    { v: money(p.spent), l: 'SPENT', warn: p.over_budget },
                  ].map(s => (
                    <div key={s.l}>
                      <div className="font-display font-bold text-[19px] pb-num"
                        style={{ color: s.warn ? AMBER : 'var(--pb-accent-ink)' }}>{s.v}</div>
                      <div className={cap}>{s.l}</div>
                    </div>
                  ))}
                </div>
                <div className="mt-2 space-y-1">
                  <Bar percent={p.percent_complete} />
                  {p.budget > 0 && (
                    <div className="flex items-center gap-2">
                      <div className="flex-1"><Bar percent={p.percent_spent} tone={p.over_budget ? AMBER : 'var(--pb-accent)'} /></div>
                      <span className="font-mono text-[9px] shrink-0"
                        style={{ color: p.over_budget ? AMBER : 'var(--pb-faintest)' }}>
                        {pct(p.percent_spent)} of budget spent
                      </span>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-3 mt-3">
                  <button onClick={() => setOpenPlan(v => v === p.id ? null : p.id)}
                    className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-text">
                    {openPlan === p.id ? '▾ Hide objectives' : '▸ Show objectives'}
                  </button>
                  <button onClick={() => { setOpenPlan(p.id); setAddingObjectiveTo(p.id) }}
                    className="font-mono text-[9px] tracking-wide2 text-pb-faint hover:text-pb-text">+ Objective</button>
                </div>

                {openPlan === p.id && (
                  <Nested level="objective" className="mt-3 space-y-2">
                    {addingObjectiveTo === p.id && (
                      <ObjectiveForm plans={plans} pillars={pillars} positions={positions}
                        planId={p.id} pillarId={pillarFilter} members={members}
                        onSave={createObjective} onCancel={() => setAddingObjectiveTo(null)} />
                    )}
                    {byTheme(p.objective_list || []).length === 0 && addingObjectiveTo !== p.id && (
                      <div className="font-mono text-[10px] text-pb-faintest">
                        {pillarFilter ? 'Nothing on this plan under that theme.' : 'Nothing on this plan yet.'}
                      </div>
                    )}
                    {/* A theme is a heading, not another indent — the plan →
                        objective → action depth stays three. */}
                    {byTheme(p.objective_list || []).map(g => (
                      <div key={g.id || '__none'} className="space-y-2">
                        {g.name && <div className={`${cap} pt-1`}>{g.name.toUpperCase()}</div>}
                        {g.rows.map(o => <ObjectiveCard key={o.id} objective={o} {...objectiveProps} />)}
                      </div>
                    ))}
                  </Nested>
                )}
              </div>
            ))}
          </div>
        )}
    </div>
  )
}

/* ── Every action and motion, in plan context ───────────────────────────── */

// The same work as above read the other way round: one flat register of
// everything serving the plan, so "what is late" and "what has eaten its
// budget" can be answered without opening each plan in turn.
function DeliveryRegister({ report, memberName, onChanged }) {
  const toast = useToast()
  const [lateOnly, setLateOnly] = useState(false)
  const [overOnly, setOverOnly] = useState(false)

  const today = new Date().toISOString().slice(0, 10)
  const groups = report.plans || []

  const rows = []
  for (const p of groups) {
    for (const o of (p.objective_list || [])) {
      for (const a of (o.action_list || [])) {
        const budget = Number(a.budget_estimate || 0)
        const spent = Number(a.actual_expenditure || 0)
        rows.push({
          kind: 'action', id: a.id, title: a.title, plan: p.name, theme: o.pillar_name, objective: o.title,
          percent: a.percent_complete || 0, budget, spent,
          percentSpent: budget ? Math.round(spent / budget * 100) : null,
          over: budget > 0 && spent > budget,
          late: a.status !== 'done' && !!a.due_date && a.due_date < today,
          due: a.due_date, status: a.status,
          owner: a.assigned_to_member_id ? memberName(a.assigned_to_member_id) : null,
        })
      }
      for (const m of (o.motion_list || [])) {
        rows.push({
          kind: 'motion', id: m.id, title: m.description, plan: p.name, theme: o.pillar_name, objective: o.title,
          percent: null, budget: 0, spent: 0, percentSpent: null, over: false,
          // A motion is a decision, not work with a deadline of its own. It
          // reads as late when the objective it serves is, which is the only
          // honest thing to say about it.
          late: !!o.is_late, due: null, status: m.outcome,
          resolution: m.is_resolution, ref: m.resolution_ref,
          meeting: m.meeting_title, meetingDate: m.meeting_date,
        })
      }
    }
  }

  const shown = rows.filter(r => (!lateOnly || r.late) && (!overOnly || r.over))

  async function bump(row, data) {
    try { await api.committeeUpdateTask(row.id, data); toast.success('Action updated'); onChanged() }
    catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        <button onClick={() => setLateOnly(v => !v)}
          className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border ${lateOnly ? 'text-pb-text border-pb-red/60' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}>
          LATE ({rows.filter(r => r.late).length})
        </button>
        <button onClick={() => setOverOnly(v => !v)}
          className={`px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 border ${overOnly ? 'text-pb-text' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
          style={overOnly ? { borderColor: AMBER } : undefined}>
          OVER BUDGET ({rows.filter(r => r.over).length})
        </button>
        <span className="font-mono text-[10px] text-pb-faintest ml-auto">{shown.length} of {rows.length}</span>
      </div>

      {shown.length === 0 ? (
        <div className="pb-card p-6 text-center">
          <div className="text-pb-text text-[13px] mb-1">Nothing to show.</div>
          <div className="font-mono text-[11px] text-pb-faintest">
            Point an action or a motion at an objective and it appears here.
          </div>
        </div>
      ) : (
        <div className="space-y-1.5">
          {shown.map(r => (
            <div key={`${r.kind}-${r.id}`} className="pb-card px-3 py-2.5">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-[8.5px] tracking-wide2 border pb-hairline rounded px-1.5 py-px text-pb-faintest">
                      {r.kind === 'action' ? 'ACTION' : 'MOTION'}
                    </span>
                    <span className="text-[12.5px] text-pb-text">{r.title}</span>
                    {r.late && <span className="font-mono text-[8.5px] tracking-wide2 text-pb-red">LATE</span>}
                    {r.over && <span className="font-mono text-[8.5px] tracking-wide2" style={{ color: AMBER }}>OVER BUDGET</span>}
                    {r.resolution && (
                      <span className="font-mono text-[8.5px] tracking-wide2" style={{ color: 'var(--pb-accent-ink)' }}>
                        RESOLUTION{r.ref ? ` · ${r.ref}` : ''}
                      </span>
                    )}
                  </div>
                  <div className={`${cap} mt-1`}>{[r.plan, r.theme, r.objective].filter(Boolean).map(x => x.toUpperCase()).join(' › ')}</div>
                  <div className="font-mono text-[9.5px] text-pb-faintest mt-0.5 flex flex-wrap gap-x-2">
                    {r.owner && <span>{r.owner}</span>}
                    {r.due && <span>due {r.due}</span>}
                    {r.meeting && <span>{r.meeting}{r.meetingDate ? ` · ${r.meetingDate.slice(0, 10)}` : ''}</span>}
                    {r.status && <span>{r.status.replace('_', ' ')}</span>}
                  </div>
                </div>
                {r.kind === 'action' && (
                  <div className="text-right shrink-0">
                    <div className="font-display font-bold text-[17px] pb-num" style={{ color: 'var(--pb-accent-ink)' }}>
                      {r.percent}%
                    </div>
                    <div className={cap}>
                      {r.budget > 0 ? `${money(r.spent)} / ${money(r.budget)} · ${r.percentSpent}%` : 'NO BUDGET'}
                    </div>
                  </div>
                )}
              </div>
              {r.kind === 'action' && (
                <div className="mt-2 flex items-center gap-2">
                  <div className="flex-1"><Bar percent={r.percent} tone={r.status === 'done' ? 'var(--pb-positive)' : r.late ? 'var(--pb-red)' : undefined} /></div>
                  {r.status !== 'done' && (
                    <button onClick={() => bump(r, { status: 'done' })}
                      className="font-mono text-[9px] text-pb-faint hover:text-pb-text shrink-0">Mark done</button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

/* ── Actions on a timeline ──────────────────────────────────────────────── */

// A Gantt over the action register. Actions carry a start, a due date, a
// percentage and what they wait on now, which is everything a bar chart of the
// plan needs — this derives the critical path the same way ClubDiary does over
// its own dependencies, rather than inventing a second idea of "blocked".
//
// An action with no dates can't be placed on a timeline, so it is listed
// underneath rather than silently dropped: an undated action is usually one
// nobody has committed to yet, which is worth seeing.
const DAY = 86400000

export function ActionTimeline({ tasks, objectives, onOpen }) {
  const dated = (tasks || []).filter(t => t.start_date || t.due_date)
  const undated = (tasks || []).filter(t => !t.start_date && !t.due_date)

  if (dated.length === 0) {
    return (
      <div className="pb-card p-6 text-center">
        <div className="text-pb-text text-[13px] mb-1">Nothing to put on a timeline yet.</div>
        <div className="font-mono text-[11px] text-pb-faintest">
          Give an action a start or a due date and it appears here.
        </div>
      </div>
    )
  }

  const at = iso => (iso ? Date.parse(iso) : null)
  const starts = dated.map(t => at(t.start_date) ?? at(t.due_date))
  const ends = dated.map(t => at(t.due_date) ?? at(t.start_date))
  const min = Math.min(...starts)
  const max = Math.max(...ends)
  const span = Math.max(DAY * 14, max - min)      // never squash into a sliver
  const pos = ms => ((ms - min) / span) * 100
  const now = Date.now()

  const byId = Object.fromEntries(dated.map(t => [t.id, t]))
  const doneOf = Object.fromEntries((tasks || []).map(t => [t.id, t.status === 'done']))
  const objName = Object.fromEntries((objectives || []).map(o => [o.id, o.title]))

  // Longest chain of not-yet-done work — the run that decides the finish date.
  // `walking` breaks a dependency cycle: nothing stops an admin saving A waits
  // on B and B waits on A, and without the guard this recurses until the tab
  // dies. A cycle has no meaningful length, so we stop at the repeat.
  const memo = {}
  const walking = new Set()
  const chain = id => {
    if (memo[id]) return memo[id]
    const t = byId[id]
    const own = Math.max(1, ((at(t.due_date) ?? at(t.start_date)) - (at(t.start_date) ?? at(t.due_date))) / DAY)
    let best = { len: own, path: [id] }
    if (walking.has(id)) return best
    walking.add(id)
    ;(t.depends_on || []).filter(d => byId[d] && !doneOf[d]).forEach(d => {
      const c = chain(d)
      if (c.len + own > best.len) best = { len: c.len + own, path: [...c.path, id] }
    })
    walking.delete(id)
    memo[id] = best
    return best
  }
  const critical = new Set(
    dated.filter(t => !doneOf[t.id])
      .map(t => chain(t.id))
      .sort((a, b) => b.len - a.len)[0]?.path || [])

  // Group by objective so the plan reads as the plan, not a flat list.
  const groups = []
  const seen = new Set()
  for (const t of dated) {
    const key = t.objective_id || '__none'
    if (seen.has(key)) continue
    seen.add(key)
    groups.push({ key, title: objName[t.objective_id] || 'Not against an objective',
      rows: dated.filter(x => (x.objective_id || '__none') === key) })
  }

  // Ticks sit on the 1st of each month the span touches, not on min + n months
  // — otherwise a plan starting mid-July labels 15 Jul as "Jul" and drops the
  // final month entirely when the last step lands before the same day-of-month.
  const months = []
  const cursor = new Date(min)
  cursor.setDate(1)
  cursor.setHours(0, 0, 0, 0)
  while (cursor.getTime() <= max) {
    months.push({
      label: cursor.toLocaleDateString(undefined, { month: 'short' }),
      // The first month usually starts before the span does; clamp it to the
      // left edge so its label stays inside the track.
      left: Math.max(0, pos(cursor.getTime())),
    })
    cursor.setMonth(cursor.getMonth() + 1)
  }

  return (
    <div>
      <div className="flex items-center gap-4 mb-2 font-mono text-[9px] tracking-wide2 text-pb-faintest">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-1.5 rounded-sm" style={{ background: 'var(--pb-accent)' }} />CRITICAL PATH
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-1.5 rounded-sm bg-pb-hairline2" />OTHER WORK
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-px h-3 bg-pb-red" />TODAY
        </span>
      </div>

      <div className="pb-card overflow-hidden">
        {/* Month ruler. Same 38% title column + flex-1 track as every row below,
            so the ticks line up structurally rather than by arithmetic. */}
        <div className="flex h-6 border-b pb-hairline bg-pb-surface2">
          <div className="w-[38%] shrink-0" />
          <div className="relative flex-1">
            {months.map((m, i) => (
              <span key={i} className="absolute font-mono text-[9px] text-pb-faintest top-1.5"
                style={{ left: `${m.left}%` }}>{m.label}</span>
            ))}
          </div>
        </div>

        {groups.map(g => (
          <div key={g.key}>
            <div className="px-3 py-1.5 bg-pb-surface2/60 font-mono text-[9px] tracking-wide3 text-pb-faint uppercase border-b pb-hairline">
              {g.title}
            </div>
            {g.rows.map(t => {
              const s = at(t.start_date) ?? at(t.due_date)
              const e = at(t.due_date) ?? at(t.start_date)
              const left = pos(s)
              const width = Math.max(1.5, pos(e) - left)
              const isCritical = critical.has(t.id)
              const overdue = t.status !== 'done' && e < now
              const blocked = (t.depends_on || []).some(d => !doneOf[d])
              return (
                <div key={t.id} className="flex items-center border-b pb-hairline last:border-0 hover:bg-pb-surface2/40 cursor-pointer"
                  onClick={() => onOpen?.(t)}>
                  <div className="w-[38%] shrink-0 px-3 py-2 min-w-0">
                    <div className="text-[12.5px] text-pb-text truncate">{t.title}</div>
                    <div className="font-mono text-[9px] text-pb-faintest">
                      {t.percent_complete || 0}%
                      {blocked && <span className="text-pb-amber"> · blocked</span>}
                      {overdue && <span className="text-pb-red"> · overdue</span>}
                    </div>
                  </div>
                  <div className="relative flex-1 h-9">
                    <div className="absolute top-0 bottom-0 border-l border-pb-red/60"
                      style={{ left: `${Math.min(100, Math.max(0, pos(now)))}%` }} />
                    <div className="absolute top-1/2 -translate-y-1/2 h-2.5 rounded-sm overflow-hidden"
                      style={{
                        left: `${left}%`, width: `${width}%`,
                        background: isCritical ? 'color-mix(in srgb, var(--pb-accent) 35%, transparent)' : 'var(--pb-hairline2)',
                      }}
                      title={`${t.start_date || '?'} → ${t.due_date || '?'}`}>
                      <div className="h-full" style={{
                        width: `${t.percent_complete || 0}%`,
                        background: t.status === 'done' ? 'var(--pb-positive)' : overdue ? 'var(--pb-red)' : 'var(--pb-accent)',
                      }} />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        ))}
      </div>

      {undated.length > 0 && (
        <div className="mt-3">
          <div className={`${cap} mb-1.5`}>NOT SCHEDULED ({undated.length})</div>
          <div className="flex flex-wrap gap-1.5">
            {undated.map(t => (
              <button key={t.id} onClick={() => onOpen?.(t)}
                className="pb-card px-2.5 py-1 text-[12px] text-pb-dim hover:text-pb-text">{t.title}</button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
