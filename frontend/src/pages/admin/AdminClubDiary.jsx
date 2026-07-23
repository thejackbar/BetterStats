import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const FREQUENCIES = ['annual', 'quarterly', 'once']
const STATUSES = ['pending', 'in_progress', 'done', 'not_applicable']
const STATUS_LABELS = { pending: 'Pending', in_progress: 'In Progress', done: 'Done', not_applicable: 'N/A' }
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const label = (s) => s.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

function TabBar({ tab, setTab }) {
  const tabs = [['board', 'Board'], ['tasks', 'Recurring Tasks']]
  return (
    <div className="flex gap-1 mb-5">
      {tabs.map(([k, l]) => (
        <button key={k} onClick={() => setTab(k)}
          className={`px-4 py-2 rounded font-mono text-[11px] tracking-wide2 ${tab === k ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}>
          {l}
        </button>
      ))}
    </div>
  )
}

// ── Board tab ────────────────────────────────────────────────────────────────
function HistoryPanel({ definitionId }) {
  const toast = useToast()
  const [history, setHistory] = useState(null)
  useEffect(() => {
    api.diaryDefinitionHistory(definitionId).then(d => setHistory(d.history || [])).catch(e => toast.error(e.message))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [definitionId])
  if (history === null) return <PbSpinner message="Loading history…" />
  return (
    <div className="space-y-1.5">
      {history.length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No history yet.</div>}
      {history.map(h => (
        <div key={h.id} className="bg-pb-surface2/40 border pb-hairline rounded px-3 py-2">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] tracking-wide2 text-pb-faint">{h.period_label}</span>
            <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border ${h.status === 'done' ? 'text-pb-accent border-pb-accent/40' : 'text-pb-faint pb-hairline'}`}>
              {STATUS_LABELS[h.status]}
            </span>
          </div>
          {h.notes && <div className="text-pb-dim text-[12px] mt-1">{h.notes}</div>}
        </div>
      ))}
    </div>
  )
}

function TaskCard({ task, members, onChanged }) {
  const toast = useToast()
  const [expanded, setExpanded] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [notes, setNotes] = useState(task.occurrence?.notes || '')
  const occ = task.occurrence

  async function setStatus(status) {
    if (!occ) return
    try { await api.diaryUpdateOccurrence(occ.id, { status }); toast.success('Updated'); onChanged() } catch (e) { toast.error(e.message) }
  }
  async function saveNotes() {
    if (!occ) return
    try { await api.diaryUpdateOccurrence(occ.id, { notes }); toast.success('Notes saved') } catch (e) { toast.error(e.message) }
  }
  async function setAssignee(memberId) {
    if (!occ) return
    try { await api.diaryUpdateOccurrence(occ.id, { assigned_to_member_id: memberId || null }); onChanged() } catch (e) { toast.error(e.message) }
  }

  const assigneeName = members.find(m => m.member_id === occ?.assigned_to_member_id)?.full_name

  return (
    <div className="pb-card px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-pb-text font-semibold text-sm">{task.title}</div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5">
            {occ?.period_label} · {label(task.frequency)}{occ?.due_date ? ` · due ${occ.due_date}` : ''}{assigneeName ? ` · ${assigneeName}` : ''}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border ${occ?.status === 'done' ? 'text-pb-accent border-pb-accent/40' : 'text-pb-faint pb-hairline'}`}>
            {occ ? STATUS_LABELS[occ.status] : '—'}
          </span>
          <button onClick={() => setExpanded(x => !x)} className="font-mono text-[9px] text-pb-faintest">{expanded ? '▾' : '▸'}</button>
        </div>
      </div>
      {expanded && (
        <div className="mt-2.5 pt-2.5 border-t pb-hairline-t space-y-2">
          {task.description && <div className="text-pb-faint text-[12px]">{task.description}</div>}
          <div className="flex flex-wrap gap-1">
            {STATUSES.filter(s => s !== occ?.status).map(s => (
              <button key={s} onClick={() => setStatus(s)} className="font-mono text-[9px] tracking-wide2 border pb-hairline rounded px-1.5 py-0.5 text-pb-faint hover:text-pb-text">
                {STATUS_LABELS[s]}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <label className="font-mono text-[10px] text-pb-faintest">Assigned to</label>
            <select className={`${inp} flex-1`} value={occ?.assigned_to_member_id || ''} onChange={e => setAssignee(e.target.value)}>
              <option value="">Unassigned</option>
              {members.map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
            </select>
          </div>
          <div className="flex gap-2">
            <textarea className={`${inp} flex-1`} placeholder="Notes for this period…" value={notes} onChange={e => setNotes(e.target.value)} />
            <button onClick={saveNotes} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-dim hover:text-pb-text whitespace-nowrap self-start">Save</button>
          </div>
          <button onClick={() => setShowHistory(x => !x)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">
            {showHistory ? 'Hide history' : 'Show history'}
          </button>
          {showHistory && <HistoryPanel definitionId={task.id} />}
        </div>
      )}
    </div>
  )
}

function BoardTab({ members }) {
  const toast = useToast()
  const [tasks, setTasks] = useState(null)

  const load = useCallback(() => {
    api.diaryBoard().then(d => setTasks(d.tasks || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  if (tasks === null) return <PbSpinner message="Loading club diary…" />
  return (
    <div>
      {tasks.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">
          No recurring tasks yet — add the starter set or your own under "Recurring Tasks".
        </div>
      ) : (
        <div className="space-y-2">
          {tasks.map(t => <TaskCard key={t.id} task={t} members={members} onChanged={load} />)}
        </div>
      )}
    </div>
  )
}

// ── Recurring Tasks tab ──────────────────────────────────────────────────────
function ReminderFields({ form, setForm }) {
  return (
    <div className="flex flex-wrap items-center gap-3 mt-2">
      <label className="flex items-center gap-1.5 font-mono text-[11px] text-pb-dim cursor-pointer select-none">
        <input type="checkbox" checked={form.reminder_enabled} onChange={e => setForm(f => ({ ...f, reminder_enabled: e.target.checked }))} />
        Email the assigned person before this is due
      </label>
      {form.reminder_enabled && (
        <label className="flex items-center gap-1.5 font-mono text-[10px] text-pb-faintest">
          <input type="number" min="1" max="180" className={`${inp} w-16`} value={form.reminder_days_before}
            onChange={e => setForm(f => ({ ...f, reminder_days_before: e.target.value }))} />
          days before due
        </label>
      )}
    </div>
  )
}

function NewDefinitionForm({ categories, onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({
    title: '', category_id: '', frequency: 'annual', default_month: '', description: '',
    reminder_enabled: false, reminder_days_before: 14,
  })
  const [newCategory, setNewCategory] = useState('')
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!form.title.trim()) return
    setBusy(true)
    try {
      let categoryId = form.category_id
      if (!categoryId && newCategory.trim()) {
        const c = await api.diaryCreateCategory(newCategory.trim())
        categoryId = c.id
      }
      await api.diaryCreateDefinition({
        title: form.title, category_id: categoryId || null, frequency: form.frequency,
        default_month: form.default_month ? Number(form.default_month) : null, description: form.description || null,
        reminder_enabled: form.reminder_enabled, reminder_days_before: Number(form.reminder_days_before) || 14,
      })
      setForm({ title: '', category_id: '', frequency: 'annual', default_month: '', description: '', reminder_enabled: false, reminder_days_before: 14 })
      setNewCategory('')
      onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">NEW RECURRING TASK</div>
      <div className="flex flex-wrap gap-2 mb-2">
        <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Title (e.g. Ground lease review)" value={form.title}
          onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <select className={`${inp} w-44`} value={form.category_id} onChange={e => setForm(f => ({ ...f, category_id: e.target.value }))}>
          <option value="">Category…</option>
          {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        {!form.category_id && (
          <input className={`${inp} w-40`} placeholder="Or new category" value={newCategory} onChange={e => setNewCategory(e.target.value)} />
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        <select className={`${inp} w-36`} value={form.frequency} onChange={e => setForm(f => ({ ...f, frequency: e.target.value }))}>
          {FREQUENCIES.map(f => <option key={f} value={f}>{label(f)}</option>)}
        </select>
        {form.frequency === 'annual' && (
          <select className={`${inp} w-36`} value={form.default_month} onChange={e => setForm(f => ({ ...f, default_month: e.target.value }))}>
            <option value="">Suggested month…</option>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        )}
        <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Description (optional)" value={form.description}
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
        <button onClick={submit} disabled={busy || !form.title.trim()}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'ADDING…' : '+ TASK'}
        </button>
      </div>
      <ReminderFields form={form} setForm={setForm} />
    </div>
  )
}

function DefinitionEditForm({ def, categories, onSaved, onCancel }) {
  const toast = useToast()
  const [form, setForm] = useState({
    title: def.title, category_id: def.category_id || '', frequency: def.frequency,
    default_month: def.default_month || '', description: def.description || '',
    reminder_enabled: def.reminder_enabled, reminder_days_before: def.reminder_days_before,
  })
  const [busy, setBusy] = useState(false)

  async function save() {
    if (!form.title.trim()) return
    setBusy(true)
    try {
      await api.diaryUpdateDefinition(def.id, {
        title: form.title, category_id: form.category_id || null, frequency: form.frequency,
        default_month: form.default_month ? Number(form.default_month) : null, description: form.description || null,
        reminder_enabled: form.reminder_enabled, reminder_days_before: Number(form.reminder_days_before) || 14,
      })
      toast.success('Saved')
      onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4">
      <div className="flex flex-wrap gap-2 mb-2">
        <input className={`${inp} flex-1 min-w-[160px]`} value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <select className={`${inp} w-44`} value={form.category_id} onChange={e => setForm(f => ({ ...f, category_id: e.target.value }))}>
          <option value="">No category</option>
          {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <div className="flex flex-wrap gap-2">
        <select className={`${inp} w-36`} value={form.frequency} onChange={e => setForm(f => ({ ...f, frequency: e.target.value }))}>
          {FREQUENCIES.map(f => <option key={f} value={f}>{label(f)}</option>)}
        </select>
        {form.frequency === 'annual' && (
          <select className={`${inp} w-36`} value={form.default_month} onChange={e => setForm(f => ({ ...f, default_month: e.target.value }))}>
            <option value="">Suggested month…</option>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        )}
        <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Description" value={form.description}
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
      </div>
      <ReminderFields form={form} setForm={setForm} />
      <div className="flex gap-2 mt-3">
        <button onClick={save} disabled={busy || !form.title.trim()}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'SAVING…' : 'SAVE'}
        </button>
        <button onClick={onCancel} className="px-4 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">Cancel</button>
      </div>
    </div>
  )
}

function DefinitionRow({ def, categories, onChanged }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  async function archive() {
    if (!confirm(`Archive "${def.title}"? Its history is kept.`)) return
    try { await api.diaryArchiveDefinition(def.id); onChanged() } catch (e) { toast.error(e.message) }
  }
  const categoryName = categories.find(c => c.id === def.category_id)?.name

  if (editing) {
    return <DefinitionEditForm def={def} categories={categories} onSaved={() => { setEditing(false); onChanged() }} onCancel={() => setEditing(false)} />
  }
  return (
    <div className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
      <div>
        <span className="text-pb-text text-sm">{def.title}</span>
        <span className="font-mono text-[10px] text-pb-faint ml-2">
          {categoryName ? `${categoryName} · ` : ''}{label(def.frequency)}{def.default_month ? ` · ${MONTHS[def.default_month - 1]}` : ''}
          {def.reminder_enabled ? ` · reminds ${def.reminder_days_before}d before` : ''}
        </span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button onClick={() => setEditing(true)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Edit</button>
        <button onClick={archive} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Archive</button>
      </div>
    </div>
  )
}

function TasksTab() {
  const toast = useToast()
  const [definitions, setDefinitions] = useState(null)
  const [categories, setCategories] = useState([])
  const [seeding, setSeeding] = useState(false)

  const load = useCallback(() => {
    api.diaryListDefinitions().then(d => setDefinitions(d.definitions || [])).catch(e => toast.error(e.message))
    api.diaryListCategories().then(d => setCategories(d.categories || [])).catch(() => {})
  }, [toast])
  useEffect(() => { load() }, [load])

  async function seedStarter() {
    setSeeding(true)
    try {
      const r = await api.diarySeedStarterDefinitions()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} starter task${r.seeded === 1 ? '' : 's'}` : 'Already up to date')
      load()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }

  if (definitions === null) return <PbSpinner message="Loading tasks…" />
  return (
    <div>
      <div className="flex justify-end mb-3">
        <button onClick={seedStarter} disabled={seeding}
          className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
          {seeding ? 'ADDING…' : '+ STARTER SET (11 TASKS)'}
        </button>
      </div>
      <NewDefinitionForm categories={categories} onCreated={load} />
      {definitions.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No recurring tasks yet — add the starter set above.</div>
      ) : (
        <div className="space-y-1.5">
          {definitions.map(d => <DefinitionRow key={d.id} def={d} categories={categories} onChanged={load} />)}
        </div>
      )}
    </div>
  )
}

export default function AdminClubDiary() {
  const toast = useToast()
  const [tab, setTab] = useState('board')
  const [members, setMembers] = useState([])

  useEffect(() => {
    api.adminListSeasons().then(seas => {
      const sorted = (seas || []).filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0))
      if (sorted[0]) api.feeListMembers(sorted[0].id).then(d => setMembers(d.members || [])).catch(() => {})
    }).catch(() => {})
  }, [toast])

  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <h1 className="font-display text-2xl font-bold text-pb-text mb-1">Club Diary</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-5">
          Annual and quarterly compliance/maintenance tasks — BAS, insurance, ground prep, equipment service — with
          who's responsible, notes, and a full history of what happened last time.
        </p>
        <TabBar tab={tab} setTab={setTab} />
        {tab === 'board' && <BoardTab members={members} />}
        {tab === 'tasks' && <TasksTab />}
      </div>
    </AdminLayout>
  )
}
