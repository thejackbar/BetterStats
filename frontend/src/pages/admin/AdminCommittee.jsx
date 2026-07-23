import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const CATEGORIES = ['operational', 'maintenance', 'compliance', 'finance', 'other']
const STATUSES = ['todo', 'in_progress', 'done', 'blocked']
const STATUS_LABELS = { todo: 'To Do', in_progress: 'In Progress', done: 'Done', blocked: 'Blocked' }
const DOC_CATEGORIES = ['governance', 'policies', 'constitution', 'insurance', 'grants', 'ground_leases', 'coach_accreditation', 'wwcc', 'risk_assessments', 'other']
const EVENT_TYPES = ['committee_meeting', 'working_bee', 'registration_day', 'agm', 'awards_night', 'sponsor_function', 'fundraising', 'other']
const label = (s) => s.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

function TabBar({ tab, setTab }) {
  const tabs = [['positions', 'Positions'], ['tasks', 'Tasks'], ['documents', 'Documents'], ['calendar', 'Calendar']]
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

// ── Positions tab ───────────────────────────────────────────────────────────
function StartTermForm({ position, onClose, onDone }) {
  const toast = useToast()
  const [holderName, setHolderName] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit() {
    if (!holderName.trim()) return
    setBusy(true)
    try {
      await api.committeeStartTerm(position.id, { holder_name: holderName.trim() })
      toast.success('Term started')
      onDone()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="mt-2 flex gap-2">
      <input autoFocus className={inp} placeholder="Holder name" value={holderName} onChange={e => setHolderName(e.target.value)} />
      <button onClick={submit} disabled={busy || !holderName.trim()}
        className="px-3 py-1.5 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
        {busy ? 'SAVING…' : 'START TERM'}
      </button>
      <button onClick={onClose} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">Cancel</button>
    </div>
  )
}

function PositionCard({ position, onChanged }) {
  const toast = useToast()
  const [showStart, setShowStart] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState(null)
  const [endingId, setEndingId] = useState(null)
  const [handoverNotes, setHandoverNotes] = useState('')

  const loadHistory = async () => {
    if (history) { setShowHistory(x => !x); return }
    try { setHistory(await api.committeePositionHistory(position.id)); setShowHistory(true) } catch (e) { toast.error(e.message) }
  }

  async function endTerm(termId) {
    try {
      await api.committeeEndTerm(termId, { handover_notes: handoverNotes || null })
      toast.success('Term ended'); setEndingId(null); setHandoverNotes(''); setHistory(null); onChanged()
    } catch (e) { toast.error(e.message) }
  }

  const term = position.current_term
  return (
    <div className="pb-card px-4 py-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-pb-text font-semibold text-sm">{position.name}</div>
          {position.responsibilities && <div className="text-pb-faint text-[12px] mt-0.5">{position.responsibilities}</div>}
        </div>
        <button onClick={loadHistory} className="font-mono text-[10px] text-pb-faint hover:text-pb-text whitespace-nowrap">History</button>
      </div>
      <div className="mt-2">
        {term ? (
          <div className="flex items-center justify-between gap-2 bg-pb-surface2/40 border pb-hairline rounded px-3 py-2">
            <div>
              <div className="text-pb-text text-sm">{term.holder_name}</div>
              <div className="font-mono text-[10px] text-pb-faint">Since {term.started_at}</div>
            </div>
            {endingId === term.id ? (
              <div className="flex items-center gap-1.5">
                <input className={`${inp} w-40`} placeholder="Handover notes" value={handoverNotes} onChange={e => setHandoverNotes(e.target.value)} />
                <button onClick={() => endTerm(term.id)} className="font-mono text-[10px] text-pb-red">Confirm</button>
                <button onClick={() => setEndingId(null)} className="font-mono text-[10px] text-pb-faint">Cancel</button>
              </div>
            ) : (
              <button onClick={() => setEndingId(term.id)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red whitespace-nowrap">End term</button>
            )}
          </div>
        ) : (
          <div className="font-mono text-[11px] text-pb-faintest">Vacant.</div>
        )}
        {!term && !showStart && (
          <button onClick={() => setShowStart(true)} className="mt-2 font-mono text-[10px] text-pb-faint hover:text-pb-text">+ Start a term</button>
        )}
        {showStart && <StartTermForm position={position} onClose={() => setShowStart(false)} onDone={() => { setShowStart(false); onChanged() }} />}
      </div>
      {showHistory && history && (
        <div className="mt-2 pt-2 border-t pb-hairline-t space-y-1">
          {history.length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No history yet.</div>}
          {history.map(h => (
            <div key={h.id} className="font-mono text-[10px] text-pb-faint flex justify-between">
              <span>{h.holder_name}</span>
              <span>{h.started_at} — {h.ended_at || (h.is_current ? 'current' : '—')}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function PositionsTab() {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [seeding, setSeeding] = useState(false)

  const load = useCallback(() => {
    api.committeePositionsCurrent().then(setData).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  const seedStarter = async () => {
    setSeeding(true)
    try {
      const r = await api.committeeSeedStarterPositions()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} starter position${r.seeded === 1 ? '' : 's'}` : 'Already up to date')
      load()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }

  if (data === null) return <PbSpinner message="Loading committee…" />
  return (
    <div>
      <div className="flex justify-end mb-3">
        <button onClick={seedStarter} disabled={seeding}
          className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
          {seeding ? 'ADDING…' : '+ STARTER SET (14 POSITIONS)'}
        </button>
      </div>
      {data.positions.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No committee positions yet — add the starter set above to get going.</div>
      ) : (
        <div className="space-y-2">
          {data.positions.map(p => <PositionCard key={p.id} position={p} onChanged={load} />)}
        </div>
      )}
    </div>
  )
}

// ── Tasks tab ────────────────────────────────────────────────────────────────
function NewTaskForm({ onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({ title: '', category: 'operational', due_date: '', is_recurring: false })
  const [busy, setBusy] = useState(false)
  async function submit() {
    if (!form.title.trim()) return
    setBusy(true)
    try {
      await api.committeeCreateTask({ ...form, due_date: form.due_date || null })
      setForm({ title: '', category: 'operational', due_date: '', is_recurring: false })
      onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="pb-card p-4 mb-4">
      <div className="flex flex-col sm:flex-row gap-2">
        <input className={`${inp} flex-1`} placeholder="Task title (e.g. Book turf wickets)" value={form.title}
          onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <select className={`${inp} sm:w-40`} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
          {CATEGORIES.map(c => <option key={c} value={c}>{label(c)}</option>)}
        </select>
        <input type="date" className={`${inp} sm:w-40`} value={form.due_date} onChange={e => setForm(f => ({ ...f, due_date: e.target.value }))} />
        <button onClick={submit} disabled={busy || !form.title.trim()}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'ADDING…' : '+ TASK'}
        </button>
      </div>
      <label className="flex items-center gap-2 font-mono text-[11px] text-pb-dim cursor-pointer select-none mt-2">
        <input type="checkbox" checked={form.is_recurring} onChange={e => setForm(f => ({ ...f, is_recurring: e.target.checked }))} />
        Recurring each season
      </label>
    </div>
  )
}

function TasksTab() {
  const toast = useToast()
  const [tasks, setTasks] = useState(null)

  const load = useCallback(() => {
    api.committeeListTasks().then(d => setTasks(d.tasks || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  async function setStatus(task, status) {
    try { await api.committeeUpdateTask(task.id, { status }); load() } catch (e) { toast.error(e.message) }
  }
  async function remove(task) {
    if (!confirm(`Delete "${task.title}"?`)) return
    try { await api.committeeDeleteTask(task.id); load() } catch (e) { toast.error(e.message) }
  }

  if (tasks === null) return <PbSpinner message="Loading tasks…" />
  return (
    <div>
      <NewTaskForm onCreated={load} />
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {STATUSES.map(st => (
          <div key={st}>
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">{STATUS_LABELS[st].toUpperCase()} ({tasks.filter(t => t.status === st).length})</div>
            <div className="space-y-2">
              {tasks.filter(t => t.status === st).map(t => (
                <div key={t.id} className="pb-card px-3 py-2.5">
                  <div className="text-pb-text text-[13px] mb-1">{t.title}</div>
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-mono text-[9px] text-pb-faintest">{label(t.category)}{t.due_date ? ` · ${t.due_date}` : ''}{t.is_recurring ? ' · ↻' : ''}</span>
                    <button onClick={() => remove(t)} className="font-mono text-[9px] text-pb-faintest hover:text-pb-red">✕</button>
                  </div>
                  <div className="flex gap-1 mt-1.5">
                    {STATUSES.filter(s => s !== st).map(s => (
                      <button key={s} onClick={() => setStatus(t, s)}
                        className="font-mono text-[8px] tracking-wide2 border pb-hairline rounded px-1 py-px text-pb-faint hover:text-pb-text">
                        {STATUS_LABELS[s]}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Documents tab ────────────────────────────────────────────────────────────
function DocumentsTab() {
  const toast = useToast()
  const [docs, setDocs] = useState(null)
  const [form, setForm] = useState({ title: '', category: 'governance', url: '' })
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.committeeListDocuments().then(d => setDocs(d.documents || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  async function submit() {
    if (!form.title.trim() || !form.url.trim()) return
    setBusy(true)
    try {
      await api.committeeCreateDocument(form)
      setForm({ title: '', category: 'governance', url: '' })
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove(d) {
    if (!confirm(`Remove "${d.title}"?`)) return
    try { await api.committeeDeleteDocument(d.id); load() } catch (e) { toast.error(e.message) }
  }

  if (docs === null) return <PbSpinner message="Loading documents…" />
  return (
    <div>
      <div className="pb-card p-4 mb-4">
        <p className="font-mono text-[10px] text-pb-faintest mb-2 leading-relaxed">
          Link-based — paste the Drive/Dropbox/etc. link to where the document already lives.
        </p>
        <div className="flex flex-col sm:flex-row gap-2">
          <input className={`${inp} flex-1`} placeholder="Title" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <select className={`${inp} sm:w-44`} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
            {DOC_CATEGORIES.map(c => <option key={c} value={c}>{label(c)}</option>)}
          </select>
          <input className={`${inp} flex-1`} placeholder="https://…" value={form.url} onChange={e => setForm(f => ({ ...f, url: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.title.trim() || !form.url.trim()}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ADDING…' : '+ DOCUMENT'}
          </button>
        </div>
      </div>
      {docs.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No documents indexed yet.</div>
      ) : (
        <div className="space-y-1.5">
          {docs.map(d => (
            <div key={d.id} className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
              <div className="min-w-0">
                <a href={d.url} target="_blank" rel="noreferrer" className="text-pb-text text-sm hover:text-pb-accent truncate block">{d.title}</a>
                <span className="font-mono text-[9px] text-pb-faintest">{label(d.category)}</span>
              </div>
              <button onClick={() => remove(d)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red shrink-0">Remove</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Calendar tab ─────────────────────────────────────────────────────────────
function CalendarTab() {
  const toast = useToast()
  const [events, setEvents] = useState(null)
  const [form, setForm] = useState({ title: '', event_type: 'committee_meeting', starts_at: '', location: '' })
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api.committeeListEvents().then(d => setEvents(d.events || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  async function submit() {
    if (!form.title.trim() || !form.starts_at) return
    setBusy(true)
    try {
      await api.committeeCreateEvent({ ...form, starts_at: new Date(form.starts_at).toISOString() })
      setForm({ title: '', event_type: 'committee_meeting', starts_at: '', location: '' })
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove(e) {
    if (!confirm(`Delete "${e.title}"?`)) return
    try { await api.committeeDeleteEvent(e.id); load() } catch (err) { toast.error(err.message) }
  }

  if (events === null) return <PbSpinner message="Loading calendar…" />
  return (
    <div>
      <div className="pb-card p-4 mb-4">
        <div className="flex flex-col sm:flex-row gap-2">
          <input className={`${inp} flex-1`} placeholder="Title" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <select className={`${inp} sm:w-48`} value={form.event_type} onChange={e => setForm(f => ({ ...f, event_type: e.target.value }))}>
            {EVENT_TYPES.map(t => <option key={t} value={t}>{label(t)}</option>)}
          </select>
          <input type="datetime-local" className={`${inp} sm:w-56`} value={form.starts_at} onChange={e => setForm(f => ({ ...f, starts_at: e.target.value }))} />
          <input className={`${inp} sm:w-40`} placeholder="Location" value={form.location} onChange={e => setForm(f => ({ ...f, location: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.title.trim() || !form.starts_at}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ADDING…' : '+ EVENT'}
          </button>
        </div>
      </div>
      {events.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No events on the calendar yet.</div>
      ) : (
        <div className="space-y-1.5">
          {events.map(e => (
            <div key={e.id} className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
              <div>
                <div className="text-pb-text text-sm">{e.title}</div>
                <div className="font-mono text-[10px] text-pb-faint">
                  {new Date(e.starts_at).toLocaleString()} · {label(e.event_type)}{e.location ? ` · ${e.location}` : ''}
                </div>
              </div>
              <button onClick={() => remove(e)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red shrink-0">Remove</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AdminCommittee() {
  const [tab, setTab] = useState('positions')
  return (
    <AdminLayout>
      <div className="max-w-4xl">
        <h1 className="font-display text-2xl font-bold text-pb-text mb-1">Committee Administration</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-5">
          Positions and succession history, the task register, a document index, and the club calendar.
        </p>
        <TabBar tab={tab} setTab={setTab} />
        {tab === 'positions' && <PositionsTab />}
        {tab === 'tasks' && <TasksTab />}
        {tab === 'documents' && <DocumentsTab />}
        {tab === 'calendar' && <CalendarTab />}
      </div>
    </AdminLayout>
  )
}
