import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { FilterPill, INPUT_CLS, Modal as UiModal } from '../../components/admin/ui'
import { PbSpinner } from '../../lib/presskit'
import Calendar from '../../components/admin/clubmanager/Calendar'
import { MemberSelect } from '../../components/admin/clubmanager/pickers'
import DiaryGantt from '../../components/admin/clubmanager/DiaryGantt'

// One input look for the whole module — the same class the shared kit's
// TextInput/Select wear, so a hand-built control here matches a kit one.
const inp = INPUT_CLS
const FREQUENCIES = ['annual', 'quarterly', 'monthly', 'once']
const STATUSES = ['pending', 'in_progress', 'done', 'not_applicable']
const STATUS_LABELS = { pending: 'Pending', in_progress: 'In Progress', done: 'Done', not_applicable: 'N/A' }
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
const label = (s) => (s || '').split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')
const num = (v) => (v === null || v === undefined || v === '' ? null : Number(v))
const todayStr = () => new Date().toISOString().slice(0, 10)

const pill = (a) => `px-2.5 py-1 rounded-full text-[11.5px] border transition ${a ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`

// Derive a month number (1-12) from a task's dates / period label.
function taskMonth(t) {
  const d = t.due_date || t.start_date || t.estimated_completion_date
  if (d) { const m = Number(String(d).slice(5, 7)); if (m) return m }
  if (t.period_label) {
    const idx = MONTHS.findIndex(mm => t.period_label.toLowerCase().includes(mm.toLowerCase()))
    if (idx >= 0) return idx + 1
  }
  return null
}
function isLate(t) {
  const d = (t.due_date || '').slice(0, 10)
  return !!d && d < todayStr() && t.status !== 'done' && t.status !== 'not_applicable'
}
function overBudget(t) {
  const b = num(t.budget_estimate), a = num(t.actual_expenditure)
  return b != null && a != null && a > b
}
function underBudget(t) {
  const b = num(t.budget_estimate), a = num(t.actual_expenditure)
  return b != null && a != null && a <= b
}

// ── Tab bar ──────────────────────────────────────────────────────────────────
function TabBar({ tab, setTab }) {
  const tabs = [['calendar', 'Calendar'], ['plan', 'Season Plan'], ['templates', 'Templates'], ['gantt', 'Gantt']]
  return (
    <div className="flex flex-wrap gap-1 mb-5">
      {tabs.map(([k, l]) => (
        <FilterPill key={k} active={tab === k} onClick={() => setTab(k)}>{l}</FilterPill>
      ))}
    </div>
  )
}

// ── Shared filter bar (Calendar + Season Plan) ───────────────────────────────
function FilterBar({ f, setF, categories }) {
  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }))
  return (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      <input className={`${inp} w-48`} placeholder="Search title…" value={f.search} onChange={e => set('search', e.target.value)} />
      <select className={`${inp} w-40`} value={f.category} onChange={e => set('category', e.target.value)}>
        <option value="">All categories</option>
        {categories.map(c => <option key={c.id} value={c.name}>{c.name}</option>)}
      </select>
      <select className={`${inp} w-36`} value={f.frequency} onChange={e => set('frequency', e.target.value)}>
        <option value="">Any frequency</option>
        {FREQUENCIES.map(fr => <option key={fr} value={fr}>{label(fr)}</option>)}
      </select>
      <select className={`${inp} w-32`} value={f.month} onChange={e => set('month', e.target.value)}>
        <option value="">Any month</option>
        {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
      </select>
      <div className="flex items-center gap-1">
        <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">RANGE</span>
        <select className={`${inp} w-24`} value={f.monthFrom} onChange={e => set('monthFrom', e.target.value)}>
          <option value="">From</option>
          {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
        <select className={`${inp} w-24`} value={f.monthTo} onChange={e => set('monthTo', e.target.value)}>
          <option value="">To</option>
          {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
        </select>
      </div>
      {(f.search || f.category || f.frequency || f.month || f.monthFrom || f.monthTo) && (
        <button onClick={() => setF({ search: '', category: '', frequency: '', month: '', monthFrom: '', monthTo: '' })}
          className="pb-btn pb-btn-sm pb-btn-quiet">clear</button>
      )}
    </div>
  )
}
const EMPTY_FILTERS = { search: '', category: '', frequency: '', month: '', monthFrom: '', monthTo: '' }
function applyFilters(tasks, f) {
  return tasks.filter(t => {
    if (f.search && !(t.title || '').toLowerCase().includes(f.search.toLowerCase())) return false
    if (f.category && t.category_name !== f.category) return false
    if (f.frequency && t.frequency !== f.frequency) return false
    const m = taskMonth(t)
    if (f.month && m !== Number(f.month)) return false
    if (f.monthFrom && (m == null || m < Number(f.monthFrom))) return false
    if (f.monthTo && (m == null || m > Number(f.monthTo))) return false
    return true
  })
}

// ── Task badges ──────────────────────────────────────────────────────────────
function Badges({ t }) {
  const late = isLate(t), over = overBudget(t), under = underBudget(t)
  return (
    <div className="flex items-center gap-1.5 flex-wrap">
      {late && <span className="font-mono text-[8.5px] tracking-wide2 rounded px-1.5 py-0.5 text-pb-red border border-pb-red/40">LATE</span>}
      {over && <span className="font-mono text-[8.5px] tracking-wide2 rounded px-1.5 py-0.5 text-pb-red border border-pb-red/40">OVER BUDGET</span>}
      {under && <span className="font-mono text-[8.5px] tracking-wide2 rounded px-1.5 py-0.5 text-pb-faint border pb-hairline">under budget</span>}
      {!late && t.status !== 'done' && t.status !== 'not_applicable' && (
        <span className="font-mono text-[8.5px] tracking-wide2 text-pb-faintest">on track</span>
      )}
    </div>
  )
}

// ── Editable occurrence card (Season Plan + Calendar list/modal) ─────────────
function TaskEditor({ task, members, roles, onPatch }) {
  const toast = useToast()
  const [local, setLocal] = useState({
    percent_complete: task.percent_complete ?? '',
    third_party: task.third_party ?? '',
    budget_estimate: task.budget_estimate ?? '',
    actual_expenditure: task.actual_expenditure ?? '',
  })
  useEffect(() => {
    setLocal({
      percent_complete: task.percent_complete ?? '',
      third_party: task.third_party ?? '',
      budget_estimate: task.budget_estimate ?? '',
      actual_expenditure: task.actual_expenditure ?? '',
    })
  }, [task.id]) // eslint-disable-line react-hooks/exhaustive-deps

  async function patch(fields) {
    try { await onPatch(task.id, fields) } catch (e) { toast.error(e.message) }
  }
  const commitNum = (key, min, max) => {
    let v = local[key]
    if (v === '' || v === null) { patch({ [key]: null }); return }
    let n = Number(v)
    if (Number.isNaN(n)) { patch({ [key]: null }); return }
    if (min != null) n = Math.max(min, n)
    if (max != null) n = Math.min(max, n)
    patch({ [key]: n })
  }

  const assigneeRole = roles.find(r => r.id === task.assigned_to_role_id)

  return (
    <div className="space-y-2.5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">STATUS</span>
          <select className={inp} value={task.status || 'pending'} onChange={e => patch({ status: e.target.value })}>
            {STATUSES.map(s => <option key={s} value={s}>{STATUS_LABELS[s]}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">PERCENT COMPLETE</span>
          <div className="flex items-center gap-2">
            <input type="range" min="0" max="100" step="5" className="flex-1 accent-pb-accent"
              value={local.percent_complete === '' ? 0 : local.percent_complete}
              onChange={e => setLocal(l => ({ ...l, percent_complete: e.target.value }))}
              onMouseUp={() => commitNum('percent_complete', 0, 100)}
              onTouchEnd={() => commitNum('percent_complete', 0, 100)} />
            <input type="number" min="0" max="100" className={`${inp} w-16`}
              value={local.percent_complete}
              onChange={e => setLocal(l => ({ ...l, percent_complete: e.target.value }))}
              onBlur={() => commitNum('percent_complete', 0, 100)} />
          </div>
        </label>
        {/* A div, not a label: a label forwards a click on any of the picker's
            own buttons to the clear button that appears once someone is chosen,
            which wipes the choice. See `Field`'s `composite` note. */}
        <div className="block" role="group" aria-label="Assigned member">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">ASSIGNED MEMBER</span>
          <MemberSelect members={members} value={task.assigned_to_member_id || null}
            onChange={v => patch({ assigned_to_member_id: v || null })} placeholder="Search a member…" />
        </div>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">ASSIGNED ROLE</span>
          <select className={inp} value={task.assigned_to_role_id || ''} onChange={e => patch({ assigned_to_role_id: e.target.value || null })}>
            <option value="">No role</option>
            {roles.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">START DATE</span>
          <input type="date" className={inp} value={(task.start_date || '').slice(0, 10)} onChange={e => patch({ start_date: e.target.value || null })} />
        </label>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">DUE DATE</span>
          <input type="date" className={inp} value={(task.due_date || '').slice(0, 10)} onChange={e => patch({ due_date: e.target.value || null })} />
        </label>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">ESTIMATED COMPLETION</span>
          <input type="date" className={inp} value={(task.estimated_completion_date || '').slice(0, 10)} onChange={e => patch({ estimated_completion_date: e.target.value || null })} />
        </label>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">THIRD PARTY</span>
          <input className={inp} placeholder="Contractor / supplier" value={local.third_party}
            onChange={e => setLocal(l => ({ ...l, third_party: e.target.value }))}
            onBlur={() => patch({ third_party: local.third_party.trim() || null })} />
        </label>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">BUDGET ESTIMATE ($)</span>
          <input type="number" min="0" step="1" className={inp} value={local.budget_estimate}
            onChange={e => setLocal(l => ({ ...l, budget_estimate: e.target.value }))}
            onBlur={() => commitNum('budget_estimate', 0, null)} />
        </label>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">SPENT TO DATE ($)</span>
          <input type="number" min="0" step="1" className={inp} value={local.actual_expenditure}
            onChange={e => setLocal(l => ({ ...l, actual_expenditure: e.target.value }))}
            onBlur={() => commitNum('actual_expenditure', 0, null)} />
        </label>
      </div>
      {assigneeRole && !task.assigned_to_member_id && (
        <div className="font-mono text-[9px] text-pb-faintest">Responsibility: {assigneeRole.title}</div>
      )}
    </div>
  )
}

function TaskPlanCard({ task, members, roles, onPatch, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  const assignee = members.find(m => m.member_id === task.assigned_to_member_id)?.full_name
  const roleName = roles.find(r => r.id === task.assigned_to_role_id)?.title
  const who = assignee || roleName || task.third_party
  return (
    <div className="pb-card px-4 py-3">
      <div className="flex items-start justify-between gap-2 cursor-pointer" onClick={() => setOpen(o => !o)}>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: task.category_color || 'var(--pb-accent)' }} />
            <span className="text-pb-text font-semibold text-sm truncate">{task.title}</span>
          </div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5">
            {task.period_label || ''}{task.category_name ? ` · ${task.category_name}` : ''} · {label(task.frequency)}
            {task.due_date ? ` · due ${task.due_date.slice(0, 10)}` : ''}{who ? ` · ${who}` : ''}
            {task.percent_complete != null ? ` · ${task.percent_complete}%` : ''}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border ${task.status === 'done' ? 'text-pb-accent border-pb-accent/40' : 'text-pb-faint pb-hairline'}`}>
            {STATUS_LABELS[task.status] || '—'}
          </span>
          <button className="font-mono text-[9px] text-pb-faintest">{open ? '▾' : '▸'}</button>
        </div>
      </div>
      <div className="mt-1.5"><Badges t={task} /></div>
      {open && (
        <div className="mt-3 pt-3 border-t pb-hairline-t">
          <TaskEditor task={task} members={members} roles={roles} onPatch={onPatch} />
        </div>
      )}
    </div>
  )
}

// ── Modal (Calendar item click) ──────────────────────────────────────────────
// The house dialog, kept behind this screen's original prop shape so every call
// site below is unchanged.
function Modal({ title, onClose, children }) {
  return (
    <UiModal onClose={onClose} title={title} width={520}>
      <div className="pb-4">{children}</div>
    </UiModal>
  )
}

// ── Calendar tab ─────────────────────────────────────────────────────────────
function CalendarTab({ plan, members, roles, categories, onPatch }) {
  const [view, setView] = useState('calendar')
  const [f, setF] = useState(EMPTY_FILTERS)
  const [selected, setSelected] = useState(null)
  const tasks = useMemo(() => applyFilters(plan, f), [plan, f])
  const selectedTask = selected ? plan.find(t => t.id === selected) : null

  const renderChip = (t) => {
    const color = t.category_color || '#8b7cf6'
    const who = members.find(m => m.member_id === t.assigned_to_member_id)?.full_name
      || roles.find(r => r.id === t.assigned_to_role_id)?.title || t.third_party
    return (
      <div className="rounded px-1.5 py-1 text-[10px] leading-tight" style={{ background: `${color}22`, borderLeft: `2.5px solid ${color}` }}>
        <div className="font-semibold text-pb-text truncate">{t.title}</div>
        {t.category_name && <div className="text-pb-faint truncate">{t.category_name}</div>}
        <div className="text-pb-faintest truncate">
          {t.due_date ? `Due ${t.due_date.slice(0, 10)}` : 'No due date'}{who ? ` · ${who}` : ''}
        </div>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <FilterBar f={f} setF={setF} categories={categories} />
        <div className="flex gap-1.5">
          <button onClick={() => setView('calendar')} className={pill(view === 'calendar')}>Calendar</button>
          <button onClick={() => setView('list')} className={pill(view === 'list')}>List</button>
        </div>
      </div>
      {view === 'calendar' ? (
        <Calendar
          items={tasks}
          getStart={t => t.start_date || t.due_date || t.estimated_completion_date}
          getEnd={t => t.due_date || t.estimated_completion_date || t.start_date}
          renderChip={renderChip}
          onItemClick={t => setSelected(t.id)}
        />
      ) : tasks.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No tasks match. Try clearing the filters, or generate this season under "Season Plan".</div>
      ) : (
        <div className="space-y-2">
          {tasks.map(t => <TaskPlanCard key={t.id} task={t} members={members} roles={roles} onPatch={onPatch} />)}
        </div>
      )}
      {selectedTask && (
        <Modal title={selectedTask.title} onClose={() => setSelected(null)}>
          <div className="mb-3"><Badges t={selectedTask} /></div>
          <TaskEditor task={selectedTask} members={members} roles={roles} onPatch={onPatch} />
        </Modal>
      )}
    </div>
  )
}

// ── Season Plan tab ──────────────────────────────────────────────────────────
function SeasonPlanTab({ plan, planLoading, members, roles, categories, year, setYear, seasonYears, onGenerate, generating, onPatch }) {
  const [f, setF] = useState(EMPTY_FILTERS)
  const tasks = useMemo(() => applyFilters(plan, f), [plan, f])
  const yearOptions = useMemo(() => {
    const set = new Set([...(seasonYears || []), new Date().getFullYear()])
    return [...set].sort((a, b) => b - a)
  }, [seasonYears])

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-3 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] tracking-wide2 text-pb-faintest">SEASON</span>
          <select className={`${inp} w-28`} value={year} onChange={e => setYear(Number(e.target.value))}>
            {yearOptions.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
        </div>
        <button onClick={onGenerate} disabled={generating}
          className="pb-btn pb-btn-primary">
          {generating ? 'Generating…' : 'Generate this season'}
        </button>
      </div>
      <FilterBar f={f} setF={setF} categories={categories} />
      {planLoading ? <PbSpinner message="Loading season plan…" /> : tasks.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">
          {plan.length === 0
            ? 'No tasks for this season yet — click "Generate this season" to create occurrences from your templates.'
            : 'No tasks match the filters.'}
        </div>
      ) : (
        <div className="space-y-2">
          {tasks.map(t => <TaskPlanCard key={t.id} task={t} members={members} roles={roles} onPatch={onPatch} />)}
        </div>
      )}
    </div>
  )
}

// ── Gantt tab ────────────────────────────────────────────────────────────────
function GanttTab({ plan, members, roles, categories, year }) {
  const [search, setSearch] = useState('')
  const [frequency, setFrequency] = useState('')
  const [memberId, setMemberId] = useState('')
  const [thirdParty, setThirdParty] = useState('')

  const tasks = useMemo(() => plan.filter(t => {
    if (search && !(t.title || '').toLowerCase().includes(search.toLowerCase())) return false
    if (frequency && t.frequency !== frequency) return false
    if (memberId && t.assigned_to_member_id !== memberId) return false
    if (thirdParty && !(t.third_party || '').toLowerCase().includes(thirdParty.toLowerCase())) return false
    return true
  }), [plan, search, frequency, memberId, thirdParty])

  return (
    <div>
      <div className="flex flex-wrap items-end gap-2 mb-3">
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">SEARCH</span>
          <input className={`${inp} w-44`} placeholder="Task title…" value={search} onChange={e => setSearch(e.target.value)} />
        </label>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">FREQUENCY</span>
          <select className={`${inp} w-36`} value={frequency} onChange={e => setFrequency(e.target.value)}>
            <option value="">Any</option>
            {FREQUENCIES.map(fr => <option key={fr} value={fr}>{label(fr)}</option>)}
          </select>
        </label>
        <div className="block w-56" role="group" aria-label="Volunteer">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">VOLUNTEER</span>
          <MemberSelect members={members} value={memberId || null} onChange={v => setMemberId(v || '')} placeholder="Any member…" />
        </div>
        <label className="block">
          <span className="font-mono text-[9px] tracking-wide2 text-pb-faintest">THIRD PARTY</span>
          <input className={`${inp} w-40`} placeholder="Contractor…" value={thirdParty} onChange={e => setThirdParty(e.target.value)} />
        </label>
        {(search || frequency || memberId || thirdParty) && (
          <button onClick={() => { setSearch(''); setFrequency(''); setMemberId(''); setThirdParty('') }}
            className="pb-btn pb-btn-sm pb-btn-quiet">clear</button>
        )}
      </div>
      <DiaryGantt tasks={tasks} categories={categories} roles={roles} members={members} year={year} />
    </div>
  )
}

// ── Templates tab ────────────────────────────────────────────────────────────
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

const emptyDefForm = () => ({
  title: '', category_id: '', frequency: 'annual', default_month: '', description: '',
  responsibility_role_id: '', third_party: '', budget_estimate: '',
  reminder_enabled: false, reminder_days_before: 14,
})

function DefinitionFields({ form, setForm, categories, roles, onCreateCategory }) {
  const [newCategory, setNewCategory] = useState('')
  const [addingCat, setAddingCat] = useState(false)
  async function addCat() {
    if (!newCategory.trim()) return
    setAddingCat(true)
    try {
      const c = await onCreateCategory(newCategory.trim())
      if (c?.id) setForm(f => ({ ...f, category_id: c.id }))
      setNewCategory('')
    } finally { setAddingCat(false) }
  }
  const showMonth = form.frequency === 'annual' || form.frequency === 'once'
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <input className={`${inp} flex-1 min-w-[200px]`} placeholder="Title (e.g. Ground lease review)" value={form.title}
          onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <select className={`${inp} w-44`} value={form.category_id} onChange={e => setForm(f => ({ ...f, category_id: e.target.value }))}>
          <option value="">Category…</option>
          {categories.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        <input className={`${inp} w-44`} placeholder="+ new category" value={newCategory} onChange={e => setNewCategory(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCat() } }} />
        <button type="button" onClick={addCat} disabled={addingCat || !newCategory.trim()}
          className="pb-btn pb-btn-sm pb-btn-secondary">{addingCat ? '…' : 'Add category'}</button>
      </div>
      <div className="flex flex-wrap gap-2">
        <select className={`${inp} w-36`} value={form.frequency} onChange={e => setForm(f => ({ ...f, frequency: e.target.value }))}>
          {FREQUENCIES.map(fr => <option key={fr} value={fr}>{label(fr)}</option>)}
        </select>
        {showMonth && (
          <select className={`${inp} w-36`} value={form.default_month} onChange={e => setForm(f => ({ ...f, default_month: e.target.value }))}>
            <option value="">Default month…</option>
            {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
          </select>
        )}
        <select className={`${inp} w-48`} value={form.responsibility_role_id} onChange={e => setForm(f => ({ ...f, responsibility_role_id: e.target.value }))}>
          <option value="">Responsibility (role)…</option>
          {roles.map(r => <option key={r.id} value={r.id}>{r.title}</option>)}
        </select>
      </div>
      <div className="flex flex-wrap gap-2">
        <input className={`${inp} w-48`} placeholder="Third party (contractor)" value={form.third_party}
          onChange={e => setForm(f => ({ ...f, third_party: e.target.value }))} />
        <input type="number" min="0" step="1" className={`${inp} w-40`} placeholder="Budget estimate ($)" value={form.budget_estimate}
          onChange={e => setForm(f => ({ ...f, budget_estimate: e.target.value }))} />
        <input className={`${inp} flex-1 min-w-[200px]`} placeholder="Description (optional)" value={form.description}
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
      </div>
      <ReminderFields form={form} setForm={setForm} />
    </div>
  )
}

function defPayload(form) {
  const showMonth = form.frequency === 'annual' || form.frequency === 'once'
  return {
    title: form.title, category_id: form.category_id || null, frequency: form.frequency,
    default_month: showMonth && form.default_month ? Number(form.default_month) : null,
    description: form.description || null,
    responsibility_role_id: form.responsibility_role_id || null,
    third_party: form.third_party || null,
    budget_estimate: form.budget_estimate === '' ? null : Number(form.budget_estimate),
    reminder_enabled: form.reminder_enabled, reminder_days_before: Number(form.reminder_days_before) || 14,
  }
}

function NewDefinitionForm({ categories, roles, onCreated, onCreateCategory }) {
  const toast = useToast()
  const [form, setForm] = useState(emptyDefForm())
  const [busy, setBusy] = useState(false)
  async function submit() {
    if (!form.title.trim()) return
    setBusy(true)
    try {
      await api.diaryCreateDefinition(defPayload(form))
      setForm(emptyDefForm())
      toast.success('Template added')
      onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">NEW RECURRING TASK TEMPLATE</div>
      <DefinitionFields form={form} setForm={setForm} categories={categories} roles={roles} onCreateCategory={onCreateCategory} />
      <div className="flex justify-end mt-3">
        <button onClick={submit} disabled={busy || !form.title.trim()}
          className="pb-btn pb-btn-primary">
          {busy ? 'Adding…' : '+ Template'}
        </button>
      </div>
    </div>
  )
}

function DefinitionEditForm({ def, categories, roles, onSaved, onCancel, onCreateCategory }) {
  const toast = useToast()
  const [form, setForm] = useState({
    title: def.title, category_id: def.category_id || '', frequency: def.frequency,
    default_month: def.default_month || '', description: def.description || '',
    responsibility_role_id: def.responsibility_role_id || '', third_party: def.third_party || '',
    budget_estimate: def.budget_estimate ?? '',
    reminder_enabled: def.reminder_enabled, reminder_days_before: def.reminder_days_before,
  })
  const [busy, setBusy] = useState(false)
  async function save() {
    if (!form.title.trim()) return
    setBusy(true)
    try {
      await api.diaryUpdateDefinition(def.id, defPayload(form))
      toast.success('Saved')
      onSaved()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="pb-card p-4">
      <DefinitionFields form={form} setForm={setForm} categories={categories} roles={roles} onCreateCategory={onCreateCategory} />
      <div className="flex gap-2 mt-3">
        <button onClick={save} disabled={busy || !form.title.trim()}
          className="pb-btn pb-btn-primary">
          {busy ? 'Saving…' : 'Save'}
        </button>
        <button onClick={onCancel} className="pb-btn pb-btn-secondary">Cancel</button>
      </div>
    </div>
  )
}

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

function DependencyEditor({ def, definitions, onChanged }) {
  const toast = useToast()
  const [addId, setAddId] = useState('')
  const [busy, setBusy] = useState(false)
  const deps = def.depends_on || []
  const nameFor = (id) => definitions.find(d => d.id === id)?.title || 'Unknown'
  const options = definitions.filter(d => d.id !== def.id && !deps.includes(d.id))

  async function add() {
    if (!addId) return
    setBusy(true)
    try { await api.diaryAddDependency(def.id, addId); setAddId(''); onChanged() }
    catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove(depId) {
    try { await api.diaryRemoveDependency(def.id, depId); onChanged() } catch (e) { toast.error(e.message) }
  }
  return (
    <div className="mt-3 pt-3 border-t pb-hairline-t">
      <div className="font-mono text-[9px] tracking-wide2 text-pb-faintest mb-1.5">DEPENDS ON</div>
      {deps.length === 0 && <div className="font-mono text-[10px] text-pb-faintest mb-1.5">No dependencies.</div>}
      <div className="flex flex-wrap gap-1.5 mb-2">
        {deps.map(id => (
          <span key={id} className="inline-flex items-center gap-1 bg-pb-accent/15 text-pb-accent rounded px-1.5 py-0.5 text-[11px]">
            {nameFor(id)}
            <button onClick={() => remove(id)} className="hover:text-pb-red">×</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <select className={`${inp} flex-1`} value={addId} onChange={e => setAddId(e.target.value)}>
          <option value="">Add a prerequisite task…</option>
          {options.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
        </select>
        <button onClick={add} disabled={busy || !addId}
          className="pb-btn pb-btn-sm pb-btn-secondary">
          {busy ? '…' : 'Add'}
        </button>
      </div>
    </div>
  )
}

function DefinitionRow({ def, definitions, categories, roles, onChanged, onCreateCategory }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  async function archive() {
    if (!confirm(`Archive "${def.title}"? Its history is kept.`)) return
    try { await api.diaryArchiveDefinition(def.id); toast.success('Archived'); onChanged() } catch (e) { toast.error(e.message) }
  }
  const categoryName = categories.find(c => c.id === def.category_id)?.name
  const roleName = roles.find(r => r.id === def.responsibility_role_id)?.title

  if (editing) {
    return <DefinitionEditForm def={def} categories={categories} roles={roles}
      onSaved={() => { setEditing(false); onChanged() }} onCancel={() => setEditing(false)} onCreateCategory={onCreateCategory} />
  }
  return (
    <div className="pb-card px-3 py-2.5">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="text-pb-text text-sm">{def.title}</span>
          <span className="font-mono text-[10px] text-pb-faint ml-2">
            {categoryName ? `${categoryName} · ` : ''}{label(def.frequency)}{def.default_month ? ` · ${MONTHS[def.default_month - 1]}` : ''}
            {roleName ? ` · ${roleName}` : ''}{def.budget_estimate != null ? ` · $${def.budget_estimate}` : ''}
            {(def.depends_on || []).length ? ` · ${def.depends_on.length} dep${def.depends_on.length === 1 ? '' : 's'}` : ''}
            {def.reminder_enabled ? ` · reminds ${def.reminder_days_before}d` : ''}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button onClick={() => setExpanded(x => !x)} className="pb-btn pb-btn-sm pb-btn-quiet">{expanded ? 'Less' : 'Deps'}</button>
          <button onClick={() => setEditing(true)} className="pb-btn pb-btn-sm pb-btn-quiet">Edit</button>
          <button onClick={() => setShowHistory(x => !x)} className="pb-btn pb-btn-sm pb-btn-quiet">History</button>
          <button onClick={archive} className="pb-btn pb-btn-sm pb-btn-danger">Archive</button>
        </div>
      </div>
      {expanded && <DependencyEditor def={def} definitions={definitions} onChanged={onChanged} />}
      {showHistory && <div className="mt-3 pt-3 border-t pb-hairline-t"><HistoryPanel definitionId={def.id} /></div>}
    </div>
  )
}

function CategoryManager({ categories, onChanged }) {
  const toast = useToast()
  const [rows, setRows] = useState({})
  useEffect(() => {
    const m = {}
    categories.forEach(c => { m[c.id] = { name: c.name, color: c.color || '#8b7cf6' } })
    setRows(m)
  }, [categories])

  async function save(c) {
    const r = rows[c.id]
    if (!r) return
    try { await api.diaryUpdateCategory(c.id, { name: r.name, color: r.color }); toast.success('Category saved'); onChanged() }
    catch (e) { toast.error(e.message) }
  }
  async function del(c) {
    if (!confirm(`Delete category "${c.name}"? Tasks keep working; they just lose this label.`)) return
    try { await api.diaryDeleteCategory(c.id); toast.success('Deleted'); onChanged() } catch (e) { toast.error(e.message) }
  }
  if (categories.length === 0) return <div className="font-mono text-[10px] text-pb-faintest">No categories yet — add the starter set or create one on a template above.</div>
  return (
    <div className="space-y-1.5">
      {categories.map(c => {
        const r = rows[c.id] || { name: c.name, color: c.color || '#8b7cf6' }
        return (
          <div key={c.id} className="flex items-center gap-2">
            <input type="color" className="w-8 h-8 rounded bg-transparent border pb-hairline cursor-pointer shrink-0"
              value={r.color} onChange={e => setRows(m => ({ ...m, [c.id]: { ...r, color: e.target.value } }))} />
            <input className={`${inp} flex-1`} value={r.name} onChange={e => setRows(m => ({ ...m, [c.id]: { ...r, name: e.target.value } }))} />
            <button onClick={() => save(c)} className="pb-btn pb-btn-sm pb-btn-secondary">Save</button>
            <button onClick={() => del(c)} className="pb-btn pb-btn-sm pb-btn-danger">Delete</button>
          </div>
        )
      })}
    </div>
  )
}

function TemplatesTab({ definitions, categories, roles, onReload, onCreateCategory }) {
  const toast = useToast()
  const [seeding, setSeeding] = useState(false)
  const [seedingCats, setSeedingCats] = useState(false)

  async function seedTasks() {
    setSeeding(true)
    try {
      const r = await api.diarySeedStarterDefinitions()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} starter task${r.seeded === 1 ? '' : 's'}` : 'Already up to date')
      onReload()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }
  async function seedCats() {
    setSeedingCats(true)
    try {
      const r = await api.diarySeedStarterCategories()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} categor${r.seeded === 1 ? 'y' : 'ies'}` : 'Already up to date')
      onReload()
    } catch (e) { toast.error(e.message) } finally { setSeedingCats(false) }
  }

  return (
    <div>
      <div className="flex justify-end gap-2 mb-3">
        <button onClick={seedCats} disabled={seedingCats}
          className="pb-btn pb-btn-secondary">
          {seedingCats ? 'Adding…' : '+ Categories (8)'}
        </button>
        <button onClick={seedTasks} disabled={seeding}
          className="pb-btn pb-btn-secondary">
          {seeding ? 'Adding…' : '+ Starter set (11 tasks)'}
        </button>
      </div>

      <NewDefinitionForm categories={categories} roles={roles} onCreated={onReload} onCreateCategory={onCreateCategory} />

      {definitions.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No templates yet — add the starter set above, or create your own.</div>
      ) : (
        <div className="space-y-1.5">
          {definitions.map(d => (
            <DefinitionRow key={d.id} def={d} definitions={definitions} categories={categories} roles={roles} onChanged={onReload} onCreateCategory={onCreateCategory} />
          ))}
        </div>
      )}

      <div className="pb-card p-4 mt-5">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2.5">CATEGORIES</div>
        <CategoryManager categories={categories} onChanged={onReload} />
      </div>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function AdminClubDiary() {
  const toast = useToast()
  const [tab, setTab] = useState('calendar')

  const [categories, setCategories] = useState([])
  const [definitions, setDefinitions] = useState(null)
  const [roles, setRoles] = useState([])
  const [members, setMembers] = useState([])
  const [seasonYears, setSeasonYears] = useState([])
  const [year, setYear] = useState(null)

  const [plan, setPlan] = useState([])
  const [planLoading, setPlanLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  const loadShared = useCallback(async () => {
    try {
      const [cats, defs, r, mem] = await Promise.all([
        api.diaryListCategories().catch(() => ({ categories: [] })),
        api.diaryListDefinitions().catch(() => ({ definitions: [] })),
        api.raRoles().catch(() => ({ roles: [] })),
        api.feeAllMembers().catch(() => ({ members: [] })),
      ])
      setCategories(cats.categories || [])
      setDefinitions(defs.definitions || [])
      setRoles(r.roles || [])
      setMembers(mem.members || [])
    } catch (e) { toast.error(e.message) }
  }, [toast])

  useEffect(() => { loadShared() }, [loadShared])

  useEffect(() => {
    api.diarySeasonYears().then(d => {
      const years = d.years || []
      setSeasonYears(years)
      setYear(prev => prev || (years.length ? Math.max(...years) : new Date().getFullYear()))
    }).catch(() => setYear(prev => prev || new Date().getFullYear()))
  }, [])

  const loadPlan = useCallback(async (y) => {
    if (!y) return
    setPlanLoading(true)
    try { const d = await api.diarySeasonPlan(y); setPlan(d.tasks || []) }
    catch (e) { toast.error(e.message); setPlan([]) }
    finally { setPlanLoading(false) }
  }, [toast])

  useEffect(() => { if (year) loadPlan(year) }, [year, loadPlan])

  const reloadTemplates = useCallback(() => { loadShared() }, [loadShared])
  const createCategory = useCallback(async (name) => {
    const c = await api.diaryCreateCategory(name)
    await loadShared()
    return c
  }, [loadShared])

  // Patch an occurrence and merge locally (recomputes derived flags from fields).
  const patchOccurrence = useCallback(async (id, fields) => {
    await api.diaryUpdateOccurrence(id, fields)
    setPlan(prev => prev.map(t => t.id === id ? { ...t, ...fields } : t))
  }, [])

  async function generateSeason() {
    if (!year) return
    setGenerating(true)
    try {
      const r = await api.diaryGenerateSeason(year)
      const n = r.created ?? 0
      toast.success(n > 0 ? `Created ${n} task${n === 1 ? '' : 's'} for ${year}` : `${year} is already generated`)
      await loadPlan(year)
    } catch (e) { toast.error(e.message) } finally { setGenerating(false) }
  }

  return (
    <BetterClubManagerLayout title="Club Diary" caption="The club's annual operating plan">
      <div className="max-w-5xl">
        <TabBar tab={tab} setTab={setTab} />

        {definitions === null ? (
          <PbSpinner message="Loading club diary…" />
        ) : (
          <>
            {tab === 'calendar' && (
              <CalendarTab plan={plan} members={members} roles={roles} categories={categories} onPatch={patchOccurrence} />
            )}
            {tab === 'plan' && (
              <SeasonPlanTab plan={plan} planLoading={planLoading} members={members} roles={roles} categories={categories}
                year={year} setYear={setYear} seasonYears={seasonYears} onGenerate={generateSeason} generating={generating} onPatch={patchOccurrence} />
            )}
            {tab === 'templates' && (
              <TemplatesTab definitions={definitions} categories={categories} roles={roles} onReload={reloadTemplates} onCreateCategory={createCategory} />
            )}
            {tab === 'gantt' && (
              <GanttTab plan={plan} members={members} roles={roles} categories={categories} year={year} />
            )}
          </>
        )}
      </div>
    </BetterClubManagerLayout>
  )
}
