import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'

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
export function AttachedDocuments({ entityType, entityId }) {
  const toast = useToast()
  const [docs, setDocs] = useState(null)
  const [form, setForm] = useState({ title: '', url: '' })

  const load = useCallback(() => {
    api.committeeListDocuments()
      .then(d => setDocs((d.documents || []).filter(x => x.entity_type === entityType && x.entity_id === entityId)))
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

  return (
    <div>
      <div className={`${cap} mb-1.5`}>DOCUMENTS</div>
      <div className="space-y-1 mb-2">
        {docs?.length === 0 && <div className="font-mono text-[10px] text-pb-faintest">Nothing attached.</div>}
        {docs?.map(d => (
          <a key={d.id} href={d.url} target="_blank" rel="noreferrer"
            className="block text-[12.5px] underline truncate" style={{ color: 'var(--pb-accent)' }}>{d.title}</a>
        ))}
      </div>
      <div className="flex gap-2">
        <input className={`${inp} flex-1`} placeholder="e.g. Netpro quote" value={form.title}
          onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <input className={`${inp} flex-1`} placeholder="https://…" value={form.url}
          onChange={e => setForm(f => ({ ...f, url: e.target.value }))} />
        <button onClick={add} disabled={!form.title.trim() || !form.url.trim()}
          className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text disabled:opacity-40 whitespace-nowrap">+ Link</button>
      </div>
    </div>
  )
}

/* ── The planning side of one action ────────────────────────────────────── */

export function ActionPlanPanel({ task, allTasks, objectives, members, onChanged }) {
  const toast = useToast()
  const [form, setForm] = useState({
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

  const num = v => (v === '' || v === null ? null : Number(v))

  async function save() {
    setBusy(true)
    try {
      await api.committeeUpdateTask(task.id, {
        objective_id: form.objective_id || null,
        budget_estimate: num(form.budget_estimate),
        actual_expenditure: num(form.actual_expenditure),
        percent_complete: Number(form.percent_complete) || 0,
        start_date: form.start_date || null,
        due_date: form.due_date || null,
        assigned_to_member_id: form.assigned_to_member_id || null,
        outcome_notes: form.outcome_notes || null,
      })
      await api.committeeSetTaskDependencies(task.id, deps)
      toast.success('Action updated')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function close() {
    setBusy(true)
    try {
      // Closing sets percent_complete to 100 server-side — an action that is
      // done is done, not 60% done.
      await api.committeeUpdateTask(task.id, { status: 'done' })
      toast.success('Action closed')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const over = form.budget_estimate !== '' && Number(form.actual_expenditure || 0) > Number(form.budget_estimate)
  const candidates = (allTasks || []).filter(t => t.id !== task.id)
  const blockers = candidates.filter(t => deps.includes(t.id) && t.status !== 'done')

  return (
    <div className="pb-card p-4 space-y-3">
      <div className={cap}>PLAN</div>

      <div className="grid grid-cols-2 gap-2">
        <label className="block">
          <span className={`${cap} block mb-1`}>OBJECTIVE</span>
          <select className={inp} value={form.objective_id}
            onChange={e => setForm(f => ({ ...f, objective_id: e.target.value }))}>
            <option value="">— none —</option>
            {(objectives || []).map(o => <option key={o.id} value={o.id}>{o.title}</option>)}
          </select>
        </label>
        <label className="block">
          <span className={`${cap} block mb-1`}>RESPONSIBLE</span>
          <select className={inp} value={form.assigned_to_member_id}
            onChange={e => setForm(f => ({ ...f, assigned_to_member_id: e.target.value }))}>
            <option value="">— unassigned —</option>
            {(members || []).map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
          </select>
        </label>
        <label className="block">
          <span className={`${cap} block mb-1`}>STARTS</span>
          <input type="date" className={inp} value={form.start_date}
            onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} />
        </label>
        <label className="block">
          <span className={`${cap} block mb-1`}>DUE</span>
          <input type="date" className={inp} value={form.due_date}
            onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
        </label>
        <label className="block">
          <span className={`${cap} block mb-1`}>BUDGET</span>
          <input type="number" step="0.01" className={inp} placeholder="0.00" value={form.budget_estimate}
            onChange={e => setForm(f => ({ ...f, budget_estimate: e.target.value }))} />
        </label>
        <label className="block">
          <span className={`${cap} block mb-1`}>SPENT SO FAR</span>
          <input type="number" step="0.01" className={inp} placeholder="0.00" value={form.actual_expenditure}
            onChange={e => setForm(f => ({ ...f, actual_expenditure: e.target.value }))} />
        </label>
      </div>

      {over && (
        <div className="font-mono text-[10px] text-pb-amber">
          Over budget by {money(Number(form.actual_expenditure) - Number(form.budget_estimate))}.
        </div>
      )}

      <label className="block">
        <span className={`${cap} block mb-1`}>PROGRESS · {form.percent_complete}%</span>
        <input type="range" min="0" max="100" step="5" className="w-full accent-pb-accent"
          value={form.percent_complete}
          onChange={e => setForm(f => ({ ...f, percent_complete: e.target.value }))} />
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
          value={form.outcome_notes} onChange={e => setForm(f => ({ ...f, outcome_notes: e.target.value }))} />
      </label>

      <div className="flex items-center gap-2">
        <button onClick={save} disabled={busy}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-50"
          style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>
          {busy ? 'SAVING…' : 'SAVE'}
        </button>
        {task.status !== 'done' && (
          <button onClick={close} disabled={busy}
            className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">
            Close as complete
          </button>
        )}
      </div>
    </div>
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

/* ── Objectives ─────────────────────────────────────────────────────────── */

export function ObjectivesTab() {
  const toast = useToast()
  const [rows, setRows] = useState(null)
  const [form, setForm] = useState({ title: '', plan: '' })
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.committeeObjectiveProgress()
      .then(d => setRows(d.objectives || []))
      .catch(e => { toast.error(e.message); setRows([]) })
  }, [toast])
  useEffect(() => { load() }, [load])

  async function add() {
    if (!form.title.trim()) return
    setBusy(true)
    try { await api.committeeCreateObjective({ ...form, plan: form.plan || null }); setForm({ title: '', plan: '' }); load() }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove(o) {
    if (!confirm(`Delete "${o.title}"? Actions serving it keep going, they just stop pointing at a plan.`)) return
    try { await api.committeeDeleteObjective(o.id); load() } catch (e) { toast.error(e.message) }
  }

  if (rows === null) return <div className="font-mono text-[11px] text-pb-faint">Loading objectives…</div>

  return (
    <div>
      <p className="text-pb-faint text-[13px] mb-4 max-w-2xl leading-relaxed">
        The club's business or strategic plan. An action points at an objective, so the plan reports against
        the register the committee already keeps rather than a spreadsheet nobody updates.
      </p>

      <div className="pb-card p-4 mb-4 flex flex-col sm:flex-row gap-2">
        <input className={`${inp} flex-1`} placeholder="Objective (e.g. Upgrade the practice nets)"
          value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <input className={`${inp} sm:w-56`} placeholder="Plan (e.g. Strategic Plan 2026-29)"
          value={form.plan} onChange={e => setForm(f => ({ ...f, plan: e.target.value }))} />
        <button onClick={add} disabled={busy || !form.title.trim()}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold disabled:opacity-40 whitespace-nowrap"
          style={{ background: 'var(--pb-accent)', color: '#0a0d14' }}>+ OBJECTIVE</button>
      </div>

      {rows.length === 0 && <div className="font-mono text-[11px] text-pb-faintest">No objectives yet.</div>}
      <div className="space-y-2">
        {rows.map(o => {
          const overspend = o.budget > 0 && o.spent > o.budget
          return (
            <div key={o.id} className="pb-card p-4 group">
              <div className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="text-pb-text font-medium">{o.title}</div>
                  {o.plan && <div className={`${cap} mt-0.5`}>{o.plan.toUpperCase()}{o.season_year ? ` · ${o.season_year}` : ''}</div>}
                </div>
                <button onClick={() => remove(o)}
                  className="font-mono text-[9px] text-pb-faintest hover:text-pb-red opacity-0 group-hover:opacity-100 transition">✕</button>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3">
                {[
                  { v: `${o.actions_done}/${o.actions}`, l: 'ACTIONS DONE' },
                  { v: `${o.percent_complete}%`, l: 'PROGRESS' },
                  { v: money(o.budget), l: 'BUDGETED' },
                  { v: money(o.spent), l: 'SPENT', warn: overspend },
                ].map(s => (
                  <div key={s.l}>
                    <div className="font-display font-bold text-[19px] pb-num"
                      style={{ color: s.warn ? '#f5b542' : 'var(--pb-accent-ink)' }}>{s.v}</div>
                    <div className={cap}>{s.l}</div>
                  </div>
                ))}
              </div>

              <div className="h-1.5 rounded bg-pb-surface2 overflow-hidden mt-3">
                <div className="h-full" style={{ width: `${o.percent_complete}%`, background: 'var(--pb-accent)' }} />
              </div>

              <div className="mt-3"><NoteThread entityType="objective" entityId={o.id} compact /></div>
            </div>
          )
        })}
      </div>
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
