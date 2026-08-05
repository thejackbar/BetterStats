import { useState, useEffect, useCallback, useRef } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { FilterPill } from '../../components/admin/ui'
import { PbSpinner } from '../../lib/presskit'
import { MemberSelect } from '../../components/admin/clubmanager/pickers'
import { ActionPlanPanel, MotionGovernance, NoteThread, AttachedDocuments, ObjectivesTab, ActionTimeline } from '../../components/admin/clubmanager/governance'

const today = () => new Date().toISOString().slice(0, 10)

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const CATEGORIES = ['operational', 'maintenance', 'compliance', 'finance', 'other']
const STATUSES = ['todo', 'in_progress', 'done', 'blocked']
const STATUS_LABELS = { todo: 'To Do', in_progress: 'In Progress', done: 'Done', blocked: 'Blocked' }
const DOC_CATEGORIES = ['governance', 'policies', 'constitution', 'insurance', 'grants', 'ground_leases', 'coach_accreditation', 'wwcc', 'risk_assessments', 'other']
const EVENT_TYPES = ['committee_meeting', 'working_bee', 'registration_day', 'agm', 'awards_night', 'sponsor_function', 'fundraising', 'other']
const MEETING_TYPES = ['committee', 'agm', 'special_general', 'sub_committee', 'other']
const MEETING_STATUSES = ['scheduled', 'in_progress', 'completed', 'cancelled']
const AGENDA_ITEM_STATUSES = ['proposed', 'discussed', 'carried', 'deferred', 'withdrawn']
const MOTION_OUTCOMES = ['pending', 'carried', 'lost', 'withdrawn']
const NOMINATION_STATUSES = ['nominated', 'elected', 'withdrawn', 'not_elected']
const ATTENDANCE_STATUSES = ['present', 'apology', 'absent']
const label = (s) => s.split('_').map(w => w[0].toUpperCase() + w.slice(1)).join(' ')

function TabBar({ tab, setTab }) {
  const tabs = [['positions', 'Committee Roles'], ['tasks', 'Actions'], ['objectives', 'Plan'], ['documents', 'Documents'], ['calendar', 'Calendar'], ['meetings', 'Meetings & AGM']]
  return (
    <div className="flex flex-wrap gap-1 mb-5">
      {tabs.map(([k, l]) => (
        <FilterPill key={k} active={tab === k} onClick={() => setTab(k)}>{l}</FilterPill>
      ))}
    </div>
  )
}

// ── Committee Roles tab (succession) ────────────────────────────────────────
function StartTermForm({ position, members, onClose, onDone }) {
  const toast = useToast()
  const [memberId, setMemberId] = useState(null)
  const [startedAt, setStartedAt] = useState(today())
  const [busy, setBusy] = useState(false)
  const selected = members.find(m => m.member_id === memberId)
  async function submit() {
    if (!memberId || !selected) { toast.error('Pick a member'); return }
    setBusy(true)
    try {
      await api.committeeStartTerm(position.id, {
        member_id: memberId,
        holder_name: selected.full_name,
        started_at: startedAt || today(),
      })
      toast.success('Term started')
      onDone()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="mt-2 flex flex-col sm:flex-row gap-2 sm:items-start">
      <div className="flex-1 min-w-[180px]">
        <MemberSelect members={members} value={memberId} onChange={setMemberId} placeholder="Choose member…" />
      </div>
      <input type="date" className={`${inp} sm:w-40`} value={startedAt} onChange={e => setStartedAt(e.target.value)} />
      <button onClick={submit} disabled={busy || !memberId}
        className="px-3 py-1.5 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
        {busy ? 'Saving…' : 'Start term'}
      </button>
      <button onClick={onClose} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text whitespace-nowrap">Cancel</button>
    </div>
  )
}

function PositionCard({ position, members, onChanged }) {
  const toast = useToast()
  const [showStart, setShowStart] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [history, setHistory] = useState(null)
  const [endingId, setEndingId] = useState(null)
  const [handoverNotes, setHandoverNotes] = useState('')
  const [editingDate, setEditingDate] = useState(false)
  const [dateDraft, setDateDraft] = useState('')

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

  async function saveDate(termId) {
    try {
      await api.committeeUpdateTerm(termId, { started_at: dateDraft || today() })
      toast.success('Start date updated'); setEditingDate(false); setHistory(null); onChanged()
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
              {editingDate ? (
                <div className="flex items-center gap-1.5 mt-1">
                  <input type="date" className={`${inp} w-36`} value={dateDraft} onChange={e => setDateDraft(e.target.value)} />
                  <button onClick={() => saveDate(term.id)} className="font-mono text-[10px] text-pb-accent">Save</button>
                  <button onClick={() => setEditingDate(false)} className="font-mono text-[10px] text-pb-faint">Cancel</button>
                </div>
              ) : (
                <div className="font-mono text-[10px] text-pb-faint flex items-center gap-2">
                  <span>Since {term.started_at}</span>
                  <button onClick={() => { setDateDraft((term.started_at || '').slice(0, 10) || today()); setEditingDate(true) }}
                    className="text-pb-faintest hover:text-pb-text">edit date</button>
                </div>
              )}
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
        {showStart && <StartTermForm position={position} members={members} onClose={() => setShowStart(false)} onDone={() => { setShowStart(false); onChanged() }} />}
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

// A club that only ever bought BetterStats recorded its office bearers as
// awards. Those awards already point at real club roles (see
// services/office_bearers.py), so the committee history can be built from them
// rather than retyped. Only shown when the club actually has some.
function OfficeBearerAwardsPanel({ onImported }) {
  const toast = useToast()
  const [info, setInfo] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.committeeOfficeBearerAwards().then(setInfo).catch(() => setInfo(null))
  }, [])

  if (!info || !info.committee_awards) return null

  const adopt = async () => {
    setBusy(true)
    try {
      const r = await api.committeeAdoptOfficeBearerAwards()
      const bits = [`Added ${r.created} term${r.created === 1 ? '' : 's'}`]
      if (r.already_there) bits.push(`${r.already_there} already recorded`)
      if (r.no_season_recorded) bits.push(`${r.no_season_recorded} had no season, so no dates to use`)
      toast.success(bits.join(' · '))
      onImported?.()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4 mb-3 flex items-start justify-between gap-4 flex-wrap">
      <div className="min-w-0">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1">FROM BETTERSTATS AWARDS</div>
        <p className="text-[13px] text-pb-dim leading-relaxed max-w-xl">
          This club has {info.committee_awards} Office Bearer award{info.committee_awards === 1 ? '' : 's'} naming a
          committee role. They can be recorded here as terms, so the succession history starts full rather than empty.
          Awards with no season recorded are left alone, and running this twice adds nothing.
        </p>
      </div>
      <button onClick={adopt} disabled={busy}
        className="px-3 py-2 rounded text-[12.5px] font-semibold border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50 whitespace-nowrap shrink-0">
        {busy ? 'Importing…' : 'Import as terms'}
      </button>
    </div>
  )
}

function PositionsTab({ members }) {
  const toast = useToast()
  const [data, setData] = useState(null)
  const [positions, setPositions] = useState([])
  const [seeding, setSeeding] = useState(false)
  const dragIndex = useRef(null)
  const [dragOver, setDragOver] = useState(null)

  const load = useCallback(() => {
    api.committeePositionsCurrent()
      .then(d => { setData(d); setPositions(d.positions || []) })
      .catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  // Native HTML5 drag-and-drop reordering (no library). The drag handle on
  // each card starts the drag; the whole row is the drop zone. On drop we
  // persist the new order, which writes each committee role's sort_order.
  const onDrop = async (toIdx) => {
    const from = dragIndex.current
    dragIndex.current = null
    setDragOver(null)
    if (from === null || from === toIdx) return
    const next = [...positions]
    const [moved] = next.splice(from, 1)
    next.splice(toIdx, 0, moved)
    setPositions(next)  // optimistic
    try {
      await api.committeeReorderPositions(next.map(p => p.id))
    } catch (e) { toast.error(e.message); load() }
  }

  const seedStarter = async () => {
    setSeeding(true)
    try {
      const r = await api.committeeSeedStarterPositions()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} committee role${r.seeded === 1 ? '' : 's'}` : 'Already up to date')
      load()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }

  if (data === null) return <PbSpinner message="Loading committee roles…" />
  return (
    <div>
      <div className="flex items-start justify-between gap-3 mb-3">
        <p className="text-[12.5px] leading-[1.6] text-pb-faint leading-relaxed max-w-xl">
          Committee roles are managed under Roles in the left menu. This tab records who holds each role and when they started.
        </p>
        <button onClick={seedStarter} disabled={seeding}
          className="px-3 py-2 rounded text-[12.5px] font-semibold border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50 whitespace-nowrap shrink-0">
          {seeding ? 'Adding…' : '+ Committee roles (18)'}
        </button>
      </div>
      <OfficeBearerAwardsPanel onImported={load} />
      {positions.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No committee roles yet — add the committee roles above, or create them under Roles.</div>
      ) : (
        <div className="space-y-2">
          <p className="font-mono text-[10px] text-pb-faintest">Drag the ⠿ handle to reorder.</p>
          {positions.map((p, idx) => (
            <div key={p.id} className={`relative rounded ${dragOver === idx ? 'ring-1 ring-pb-accent/60' : ''}`}
              onDragOver={e => { e.preventDefault(); if (dragOver !== idx) setDragOver(idx) }}
              onDragLeave={() => setDragOver(o => (o === idx ? null : o))}
              onDrop={() => onDrop(idx)}>
              <span draggable
                onDragStart={() => { dragIndex.current = idx }}
                onDragEnd={() => { dragIndex.current = null; setDragOver(null) }}
                title="Drag to reorder"
                className="absolute left-1.5 top-4 z-10 cursor-grab active:cursor-grabbing text-pb-faintest hover:text-pb-text select-none text-sm leading-none">⠿</span>
              <div className="pl-6">
                <PositionCard position={p} members={members} onChanged={load} />
              </div>
            </div>
          ))}
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
          className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'Adding…' : '+ Task'}
        </button>
      </div>
      <label className="flex items-center gap-2 font-mono text-[11px] text-pb-dim cursor-pointer select-none mt-2">
        <input type="checkbox" checked={form.is_recurring} onChange={e => setForm(f => ({ ...f, is_recurring: e.target.checked }))} />
        Recurring each season
      </label>
    </div>
  )
}

function TasksTab({ members }) {
  const toast = useToast()
  const [tasks, setTasks] = useState(null)
  const [objectives, setObjectives] = useState([])
  const [openId, setOpenId] = useState(null)   // the action whose plan is showing
  const [view, setView] = useState('board')    // board | timeline
  const [q, setQ] = useState('')
  const [cat, setCat] = useState('')
  const [objId, setObjId] = useState('')
  const [who, setWho] = useState('')
  const [overdueOnly, setOverdueOnly] = useState(false)

  const load = useCallback(() => {
    api.committeeListTasks().then(d => setTasks(d.tasks || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])
  useEffect(() => { api.committeeListObjectives().then(d => setObjectives(d.objectives || [])).catch(() => {}) }, [])

  async function setStatus(task, status) {
    try { await api.committeeUpdateTask(task.id, { status }); load() } catch (e) { toast.error(e.message) }
  }
  async function remove(task) {
    if (!confirm(`Delete "${task.title}"?`)) return
    try { await api.committeeDeleteTask(task.id); load() } catch (e) { toast.error(e.message) }
  }

  if (tasks === null) return <PbSpinner message="Loading actions…" />

  // The board and the timeline read the same filtered set, so switching view
  // keeps whatever you narrowed to instead of throwing it away.
  const today = new Date().toISOString().slice(0, 10)
  const shown = tasks.filter(t => {
    if (q && !`${t.title} ${t.description || ''} ${t.outcome_notes || ''}`.toLowerCase().includes(q.toLowerCase())) return false
    if (cat && t.category !== cat) return false
    if (objId && t.objective_id !== objId) return false
    if (who && !(t.assignee_member_ids || []).includes(who) && t.assigned_to_member_id !== who) return false
    if (overdueOnly && !(t.due_date && t.due_date < today && t.status !== 'done')) return false
    return true
  })
  const selInp = 'bg-pb-surface2 border pb-hairline rounded px-2 py-1.5 text-pb-text font-mono text-[10px]'

  return (
    <div>
      <NewTaskForm onCreated={load} />

      <div className="flex flex-wrap items-center gap-2 mb-3">
        <input className={`${inp} flex-1 min-w-[12rem]`} placeholder="Search actions…"
          value={q} onChange={e => setQ(e.target.value)} />
        <select className={selInp} value={cat} onChange={e => setCat(e.target.value)}>
          <option value="">Any category</option>
          {CATEGORIES.map(c => <option key={c} value={c}>{label(c)}</option>)}
        </select>
        <select className={selInp} value={objId} onChange={e => setObjId(e.target.value)}>
          <option value="">Any objective</option>
          {objectives.map(o => <option key={o.id} value={o.id}>{o.title}</option>)}
        </select>
        <select className={selInp} value={who} onChange={e => setWho(e.target.value)}>
          <option value="">Anyone</option>
          {members.map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
        </select>
        <button onClick={() => setOverdueOnly(v => !v)}
          className={`px-3 py-1.5 rounded font-mono text-[10px] border ${overdueOnly ? 'text-pb-bg border-transparent' : 'pb-hairline text-pb-faint hover:text-pb-text'}`}
          style={overdueOnly ? { background: 'var(--pb-accent)' } : undefined}>Overdue</button>
        {(q || cat || objId || who || overdueOnly) && (
          <button onClick={() => { setQ(''); setCat(''); setObjId(''); setWho(''); setOverdueOnly(false) }}
            className="font-mono text-[10px] text-pb-faint hover:text-pb-text">clear</button>
        )}
        <span className="font-mono text-[10px] text-pb-faintest ml-auto">
          {shown.length} of {tasks.length}
        </span>
      </div>

      <div className="flex items-center gap-1 mb-3">
        {[['board', 'Board'], ['timeline', 'Timeline']].map(([k, l]) => (
          <button key={k} onClick={() => setView(k)}
            className={`px-3 py-1.5 rounded text-[12.5px] font-semibold ${view === k ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}>{l}</button>
        ))}
      </div>
      {view === 'timeline' ? (
        <ActionTimeline tasks={shown} objectives={objectives}
          onOpen={t => { setView('board'); setOpenId(t.id) }} />
      ) : (
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {STATUSES.map(st => (
          <div key={st}>
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">{STATUS_LABELS[st].toUpperCase()} ({shown.filter(t => t.status === st).length})</div>
            <div className="space-y-2">
              {shown.filter(t => t.status === st).map(t => (
                <div key={t.id} className="pb-card px-3 py-2.5">
                  <div className="text-pb-text text-[13px] mb-1">{t.title}</div>
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-mono text-[9px] text-pb-faintest">{label(t.category)}{t.due_date ? ` · ${t.due_date}` : ''}{t.is_recurring ? ' · ↻' : ''}</span>
                    <button onClick={() => remove(t)} className="font-mono text-[9px] text-pb-faintest hover:text-pb-red">✕</button>
                  </div>
                  {/* The planning line, only when there is something to say. */}
                  {(t.budget_estimate != null || t.percent_complete > 0 || (t.depends_on || []).length > 0) && (
                    <div className="flex items-center gap-2 mt-1 font-mono text-[9px]">
                      {t.percent_complete > 0 && <span style={{ color: 'var(--pb-accent-ink)' }}>{t.percent_complete}%</span>}
                      {t.budget_estimate != null && (
                        <span className={Number(t.actual_expenditure || 0) > Number(t.budget_estimate) ? 'text-pb-amber' : 'text-pb-faintest'}>
                          ${Number(t.actual_expenditure || 0).toLocaleString('en-AU')}/${Number(t.budget_estimate).toLocaleString('en-AU')}
                        </span>
                      )}
                      {(t.depends_on || []).length > 0 && <span className="text-pb-faintest">waits on {t.depends_on.length}</span>}
                    </div>
                  )}
                  <div className="flex gap-1 mt-1.5 flex-wrap">
                    {STATUSES.filter(s => s !== st).map(s => (
                      <button key={s} onClick={() => setStatus(t, s)}
                        className="font-mono text-[8px] tracking-wide2 border pb-hairline rounded px-1 py-px text-pb-faint hover:text-pb-text">
                        {STATUS_LABELS[s]}
                      </button>
                    ))}
                    <button onClick={() => setOpenId(o => o === t.id ? null : t.id)}
                      className="font-mono text-[8px] tracking-wide2 border pb-hairline rounded px-1 py-px text-pb-faint hover:text-pb-text ml-auto">
                      {openId === t.id ? 'Close' : 'Plan'}
                    </button>
                  </div>
                  {openId === t.id && (
                    <div className="mt-2 space-y-2">
                      <ActionPlanPanel task={t} allTasks={tasks} objectives={objectives} members={members}
                        onChanged={load} />
                      <div className="pb-card p-3"><NoteThread entityType="task" entityId={t.id} /></div>
                      <div className="pb-card p-3"><AttachedDocuments entityType="task" entityId={t.id} /></div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      )}
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
        <p className="text-[12.5px] leading-[1.6] text-pb-faint mb-2 leading-relaxed">
          Link-based — paste the Drive/Dropbox/etc. link to where the document already lives.
        </p>
        <div className="flex flex-col sm:flex-row gap-2">
          <input className={`${inp} flex-1`} placeholder="Title" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <select className={`${inp} sm:w-44`} value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
            {DOC_CATEGORIES.map(c => <option key={c} value={c}>{label(c)}</option>)}
          </select>
          <input className={`${inp} flex-1`} placeholder="https://…" value={form.url} onChange={e => setForm(f => ({ ...f, url: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.title.trim() || !form.url.trim()}
            className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'Adding…' : '+ Document'}
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
      <p className="text-[12.5px] leading-[1.6] text-pb-faint mb-4 leading-relaxed">
        These are your club events. The full events calendar with month/week/day views, filters, ticketing and registrations lives under Events in the left menu. This is a quick committee view.
      </p>
      <div className="pb-card p-4 mb-4">
        <div className="flex flex-col sm:flex-row gap-2">
          <input className={`${inp} flex-1`} placeholder="Title" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <select className={`${inp} sm:w-48`} value={form.event_type} onChange={e => setForm(f => ({ ...f, event_type: e.target.value }))}>
            {EVENT_TYPES.map(t => <option key={t} value={t}>{label(t)}</option>)}
          </select>
          <input type="datetime-local" className={`${inp} sm:w-56`} value={form.starts_at} onChange={e => setForm(f => ({ ...f, starts_at: e.target.value }))} />
          <input className={`${inp} sm:w-40`} placeholder="Location" value={form.location} onChange={e => setForm(f => ({ ...f, location: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.title.trim() || !form.starts_at}
            className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'Adding…' : '+ Event'}
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

// ── Meetings & AGM tab (Committee Meeting Assistant) ────────────────────────
function AgendaTemplatesPanel({ templates, onChanged }) {
  const toast = useToast()
  const [form, setForm] = useState({ name: '', items: [] })
  const [itemDraft, setItemDraft] = useState('')
  const [busy, setBusy] = useState(false)

  function addItem() {
    if (!itemDraft.trim()) return
    setForm(f => ({ ...f, items: [...f.items, { title: itemDraft.trim() }] }))
    setItemDraft('')
  }
  async function submit() {
    if (!form.name.trim() || form.items.length === 0) return
    setBusy(true)
    try {
      await api.committeeCreateAgendaTemplate(form)
      setForm({ name: '', items: [] })
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove(t) {
    if (!confirm(`Delete template "${t.name}"?`)) return
    try { await api.committeeDeleteAgendaTemplate(t.id); onChanged() } catch (e) { toast.error(e.message) }
  }

  return (
    <div className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">AGENDA TEMPLATES</div>
      <p className="text-[12.5px] leading-[1.6] text-pb-faint mb-2 leading-relaxed">
        A saved agenda shape — pick one when creating a meeting to copy its items straight onto the new meeting's agenda.
      </p>
      {templates.length > 0 && (
        <div className="space-y-1.5 mb-3">
          {templates.map(t => (
            <div key={t.id} className="flex items-center justify-between gap-2 bg-pb-surface2/40 border pb-hairline rounded px-3 py-2">
              <div>
                <span className="text-pb-text text-sm">{t.name}</span>
                <span className="font-mono text-[10px] text-pb-faint ml-2">{t.items.length} item{t.items.length === 1 ? '' : 's'}</span>
              </div>
              <button onClick={() => remove(t)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red shrink-0">Remove</button>
            </div>
          ))}
        </div>
      )}
      <input className={`${inp} mb-2`} placeholder="New template name (e.g. Standard committee meeting)" value={form.name}
        onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
      <div className="flex flex-wrap gap-1 mb-2">
        {form.items.map((it, idx) => (
          <span key={idx} className="font-mono text-[10px] border pb-hairline rounded px-1.5 py-0.5 text-pb-dim flex items-center gap-1">
            {it.title}
            <button onClick={() => setForm(f => ({ ...f, items: f.items.filter((_, i) => i !== idx) }))} className="text-pb-faintest hover:text-pb-red">✕</button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input className={`${inp} flex-1`} placeholder="Agenda item title, press Enter" value={itemDraft} onChange={e => setItemDraft(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addItem() } }} />
        <button onClick={addItem} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">Add item</button>
        <button onClick={submit} disabled={busy || !form.name.trim() || form.items.length === 0}
          className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'Saving…' : '+ Template'}
        </button>
      </div>
    </div>
  )
}

function NewMeetingForm({ templates, onCreated }) {
  const toast = useToast()
  const [form, setForm] = useState({ title: '', meeting_type: 'committee', scheduled_at: '', location: '', agenda_template_id: '' })
  const [busy, setBusy] = useState(false)
  async function submit() {
    if (!form.title.trim() || !form.scheduled_at) return
    setBusy(true)
    try {
      await api.committeeCreateMeeting({
        ...form, scheduled_at: new Date(form.scheduled_at).toISOString(),
        agenda_template_id: form.agenda_template_id || null,
      })
      setForm({ title: '', meeting_type: 'committee', scheduled_at: '', location: '', agenda_template_id: '' })
      onCreated()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  return (
    <div className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">NEW MEETING</div>
      <div className="flex flex-wrap gap-2">
        <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Title (e.g. July committee meeting)" value={form.title}
          onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
        <select className={`${inp} w-44`} value={form.meeting_type} onChange={e => setForm(f => ({ ...f, meeting_type: e.target.value }))}>
          {MEETING_TYPES.map(t => <option key={t} value={t}>{label(t)}</option>)}
        </select>
        <input type="datetime-local" className={`${inp} w-56`} value={form.scheduled_at} onChange={e => setForm(f => ({ ...f, scheduled_at: e.target.value }))} />
        <input className={`${inp} w-40`} placeholder="Location" value={form.location} onChange={e => setForm(f => ({ ...f, location: e.target.value }))} />
        <select className={`${inp} w-56`} value={form.agenda_template_id} onChange={e => setForm(f => ({ ...f, agenda_template_id: e.target.value }))}>
          <option value="">No agenda template</option>
          {templates.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <button onClick={submit} disabled={busy || !form.title.trim() || !form.scheduled_at}
          className="px-4 py-2 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'Creating…' : '+ Meeting'}
        </button>
      </div>
    </div>
  )
}

function MeetingDetail({ meeting, members, positions, onChanged }) {
  const toast = useToast()
  const [detail, setDetail] = useState(null)
  const [minutes, setMinutes] = useState('')
  const [status, setStatus] = useState(meeting.status)
  const [savingMeta, setSavingMeta] = useState(false)
  const [newItem, setNewItem] = useState({ title: '', description: '' })
  const [newMotion, setNewMotion] = useState({ description: '', motion_type: 'motion' })
  const [newNom, setNewNom] = useState({ position_id: '', candidate_member_id: '' })
  const [attendance, setAttendance] = useState({})

  const load = useCallback(() => {
    api.committeeGetMeeting(meeting.id).then(d => {
      setDetail(d)
      setMinutes(d.minutes || '')
      setStatus(d.status)
      const att = {}
      for (const a of d.attendance || []) att[a.member_id] = a.status
      setAttendance(att)
    }).catch(e => toast.error(e.message))
  }, [meeting.id, toast])
  useEffect(() => { load() }, [load])

  async function saveMeta() {
    setSavingMeta(true)
    try {
      await api.committeeUpdateMeeting(meeting.id, { minutes, status })
      toast.success('Saved'); onChanged()
    } catch (e) { toast.error(e.message) } finally { setSavingMeta(false) }
  }

  async function saveAttendance() {
    const entries = Object.entries(attendance).map(([member_id, st]) => ({ member_id, status: st }))
    try { await api.committeeSetAttendance(meeting.id, entries); toast.success('Attendance saved') } catch (e) { toast.error(e.message) }
  }

  async function addAgendaItem() {
    if (!newItem.title.trim()) return
    try {
      await api.committeeCreateAgendaItem(meeting.id, { ...newItem, position: (detail?.agenda_items?.length || 0) })
      setNewItem({ title: '', description: '' }); load()
    } catch (e) { toast.error(e.message) }
  }
  async function setItemStatus(item, itemStatus) {
    try { await api.committeeUpdateAgendaItem(meeting.id, item.id, { status: itemStatus }); load() } catch (e) { toast.error(e.message) }
  }
  async function removeItem(item) {
    if (!confirm(`Remove agenda item "${item.title}"?`)) return
    try { await api.committeeDeleteAgendaItem(meeting.id, item.id); load() } catch (e) { toast.error(e.message) }
  }

  async function addMotion() {
    if (!newMotion.description.trim()) return
    try {
      await api.committeeCreateMotion(meeting.id, newMotion)
      setNewMotion({ description: '', motion_type: 'motion' }); load()
    } catch (e) { toast.error(e.message) }
  }
  async function setMotionOutcome(motion, outcome) {
    try { await api.committeeUpdateMotion(meeting.id, motion.id, { outcome }); load() } catch (e) { toast.error(e.message) }
  }
  async function removeMotion(motion) {
    if (!confirm('Remove this motion?')) return
    try { await api.committeeDeleteMotion(meeting.id, motion.id); load() } catch (e) { toast.error(e.message) }
  }

  async function addNomination() {
    if (!newNom.position_id || !newNom.candidate_member_id) return
    try {
      await api.committeeCreateNomination(meeting.id, newNom)
      setNewNom({ position_id: '', candidate_member_id: '' }); load()
    } catch (e) { toast.error(e.message) }
  }
  async function setNominationStatus(nom, nomStatus) {
    if (nomStatus === 'elected' && !confirm('Mark elected? This starts a new committee term for this position, ending whoever currently holds it.')) return
    try { await api.committeeUpdateNomination(meeting.id, nom.id, { status: nomStatus }); toast.success(nomStatus === 'elected' ? 'Elected — term started' : 'Updated'); load() } catch (e) { toast.error(e.message) }
  }
  async function removeNomination(nom) {
    if (!confirm('Remove this nomination?')) return
    try { await api.committeeDeleteNomination(meeting.id, nom.id); load() } catch (e) { toast.error(e.message) }
  }

  const memberName = (id) => members.find(m => m.member_id === id)?.full_name || '—'
  const positionName = (id) => positions.find(p => p.id === id)?.name || '—'

  if (detail === null) return <PbSpinner message="Loading meeting…" />
  return (
    <div className="border-t pb-hairline-t px-4 py-3 space-y-4">
      <style>{'@media print { body * { visibility: hidden; } #meeting-print-area, #meeting-print-area * { visibility: visible; } #meeting-print-area { position: absolute; left: 0; top: 0; width: 100%; } .no-print { display: none !important; } }'}</style>
      <div className="flex flex-wrap items-center gap-2 no-print">
        <select className={`${inp} w-44`} value={status} onChange={e => setStatus(e.target.value)}>
          {MEETING_STATUSES.map(s => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <button onClick={saveMeta} disabled={savingMeta}
          className="px-3 py-1.5 rounded text-[12.5px] font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
          {savingMeta ? 'Saving…' : 'Save'}
        </button>
        <button onClick={() => window.print()} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-dim hover:text-pb-text ml-auto">
          Print minutes / agenda
        </button>
      </div>

      <div id="meeting-print-area">
        <div className="mb-2">
          <div className="font-display font-bold text-lg text-pb-text">{meeting.title}</div>
          <div className="font-mono text-[10px] text-pb-faint">{new Date(meeting.scheduled_at).toLocaleString()} · {label(meeting.meeting_type)}{meeting.location ? ` · ${meeting.location}` : ''}</div>
        </div>

        <div className="no-print">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">MINUTES</div>
          <textarea className={`${inp} h-28 mb-3`} placeholder="Minutes…" value={minutes} onChange={e => setMinutes(e.target.value)} />
        </div>
        {status === 'completed' && minutes && (
          <div className="hidden print:block mb-3 text-sm text-pb-text whitespace-pre-wrap">{minutes}</div>
        )}

        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">ATTENDANCE</div>
        <div className="flex flex-wrap gap-2 mb-1.5 no-print">
          {members.map(m => (
            <label key={m.member_id} className="flex items-center gap-1 font-mono text-[10px] text-pb-dim border pb-hairline rounded px-1.5 py-1">
              {m.full_name}
              <select className="bg-pb-surface2 text-pb-text text-[9px] border-none focus:outline-none"
                value={attendance[m.member_id] || ''} onChange={e => setAttendance(a => ({ ...a, [m.member_id]: e.target.value }))}>
                <option value="">—</option>
                {ATTENDANCE_STATUSES.map(s => <option key={s} value={s}>{label(s)}</option>)}
              </select>
            </label>
          ))}
        </div>
        <button onClick={saveAttendance} className="font-mono text-[10px] text-pb-faint hover:text-pb-text mb-3 no-print">Save attendance</button>
        <div className="hidden print:block text-[12px] text-pb-text mb-3">
          {(detail.attendance || []).length === 0 ? 'No attendance recorded.' :
            detail.attendance.map(a => `${a.full_name} (${label(a.status)})`).join(', ')}
        </div>

        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5 mt-3">AGENDA</div>
        <div className="space-y-1.5 mb-2">
          {(detail.agenda_items || []).length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No agenda items yet.</div>}
          {(detail.agenda_items || []).map(item => (
            <div key={item.id} className="pb-card px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-pb-text text-[13px]">{item.title}</div>
                <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border pb-hairline ${item.status === 'carried' ? 'text-pb-accent' : 'text-pb-faint'}`}>{label(item.status)}</span>
              </div>
              {item.description && <div className="text-pb-faint text-[11px] mt-0.5">{item.description}</div>}
              <div className="flex gap-1 mt-1 no-print">
                {AGENDA_ITEM_STATUSES.filter(s => s !== item.status).map(s => (
                  <button key={s} onClick={() => setItemStatus(item, s)} className="font-mono text-[8px] tracking-wide2 border pb-hairline rounded px-1 py-px text-pb-faint hover:text-pb-text">{label(s)}</button>
                ))}
                <button onClick={() => removeItem(item)} className="font-mono text-[8px] text-pb-faintest hover:text-pb-red ml-auto">✕</button>
              </div>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mb-3 no-print">
          <input className={`${inp} flex-1`} placeholder="New agenda item" value={newItem.title} onChange={e => setNewItem(f => ({ ...f, title: e.target.value }))} />
          <button onClick={addAgendaItem} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text whitespace-nowrap">+ Item</button>
        </div>

        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5 mt-3">MOTIONS</div>
        <div className="space-y-1.5 mb-2">
          {(detail.motions || []).length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No motions recorded.</div>}
          {(detail.motions || []).map(m => (
            <div key={m.id} className="pb-card px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-pb-text text-[13px]">{m.description}</div>
                <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border ${m.outcome === 'carried' ? 'text-pb-accent border-pb-accent/40' : m.outcome === 'lost' ? 'text-pb-red border-pb-red/40' : 'text-pb-faint pb-hairline'}`}>{label(m.outcome)}</span>
              </div>
              <div className="flex gap-1 mt-1 no-print">
                {MOTION_OUTCOMES.filter(o => o !== m.outcome).map(o => (
                  <button key={o} onClick={() => setMotionOutcome(m, o)} className="font-mono text-[8px] tracking-wide2 border pb-hairline rounded px-1 py-px text-pb-faint hover:text-pb-text">{label(o)}</button>
                ))}
                <button onClick={() => removeMotion(m)} className="font-mono text-[8px] text-pb-faintest hover:text-pb-red ml-auto">✕</button>
              </div>
              <MotionGovernance meeting={meeting} motion={m} members={members} onChanged={load} />
            </div>
          ))}
        </div>
        <div className="flex gap-2 mb-3 no-print">
          <input className={`${inp} flex-1`} placeholder="New motion wording" value={newMotion.description} onChange={e => setNewMotion(f => ({ ...f, description: e.target.value }))} />
          <button onClick={addMotion} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text whitespace-nowrap">+ Motion</button>
        </div>

        {meeting.meeting_type === 'agm' && (
          <>
            <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5 mt-3">AGM NOMINATIONS</div>
            <div className="space-y-1.5 mb-2">
              {(detail.nominations || []).length === 0 && <div className="font-mono text-[10px] text-pb-faintest">No nominations recorded.</div>}
              {(detail.nominations || []).map(n => (
                <div key={n.id} className="pb-card px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-pb-text text-[13px]">{memberName(n.candidate_member_id)} — {positionName(n.position_id)}</div>
                    <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border ${n.status === 'elected' ? 'text-pb-accent border-pb-accent/40' : 'text-pb-faint pb-hairline'}`}>{label(n.status)}</span>
                  </div>
                  <div className="flex gap-1 mt-1 no-print">
                    {NOMINATION_STATUSES.filter(s => s !== n.status).map(s => (
                      <button key={s} onClick={() => setNominationStatus(n, s)} className="font-mono text-[8px] tracking-wide2 border pb-hairline rounded px-1 py-px text-pb-faint hover:text-pb-text">{label(s)}</button>
                    ))}
                    <button onClick={() => removeNomination(n)} className="font-mono text-[8px] text-pb-faintest hover:text-pb-red ml-auto">✕</button>
                  </div>
                </div>
              ))}
            </div>
            <div className="flex flex-wrap gap-2 no-print">
              <select className={`${inp} flex-1 min-w-[140px]`} value={newNom.position_id} onChange={e => setNewNom(f => ({ ...f, position_id: e.target.value }))}>
                <option value="">Position…</option>
                {positions.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
              <select className={`${inp} flex-1 min-w-[140px]`} value={newNom.candidate_member_id} onChange={e => setNewNom(f => ({ ...f, candidate_member_id: e.target.value }))}>
                <option value="">Candidate…</option>
                {members.map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
              </select>
              <button onClick={addNomination} className="px-3 py-1.5 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text whitespace-nowrap">+ Nominate</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function MeetingRow({ meeting, members, positions, onChanged }) {
  const toast = useToast()
  const [expanded, setExpanded] = useState(false)
  async function remove() {
    if (!confirm(`Delete meeting "${meeting.title}"?`)) return
    try { await api.committeeDeleteMeeting(meeting.id); onChanged() } catch (e) { toast.error(e.message) }
  }
  return (
    <div className="pb-card">
      <button onClick={() => setExpanded(x => !x)} className="w-full flex items-center justify-between px-4 py-3 hover:bg-pb-surface2 transition text-left">
        <div>
          <div className="text-pb-text font-semibold text-sm">{meeting.title}</div>
          <div className="font-mono text-[10px] text-pb-faint mt-0.5">
            {new Date(meeting.scheduled_at).toLocaleString()} · {label(meeting.meeting_type)}{meeting.location ? ` · ${meeting.location}` : ''}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* The live screen. This list is for finding a meeting; running one
              happens in the meeting room. */}
          <Link to={`/admin/clubhouse/committee/meeting/${meeting.id}`} onClick={e => e.stopPropagation()}
            className="font-mono text-[9px] tracking-wide2 border pb-hairline rounded px-2 py-1 text-pb-faint hover:text-pb-text whitespace-nowrap">
            OPEN MEETING
          </Link>
          <span className="font-mono text-[9px] tracking-wide2 border pb-hairline rounded px-1.5 py-0.5 text-pb-faint">{label(meeting.status)}</span>
          <span onClick={(e) => { e.stopPropagation(); remove() }} className="font-mono text-[10px] text-pb-faintest hover:text-pb-red">✕</span>
          <span className="font-mono text-[9px] text-pb-faintest">{expanded ? '▾' : '▸'}</span>
        </div>
      </button>
      {expanded && <MeetingDetail meeting={meeting} members={members} positions={positions} onChanged={onChanged} />}
    </div>
  )
}

function MeetingsTab() {
  const toast = useToast()
  const [meetings, setMeetings] = useState(null)
  const [templates, setTemplates] = useState([])
  const [members, setMembers] = useState([])
  const [positions, setPositions] = useState([])

  const load = useCallback(() => {
    api.committeeListMeetings().then(d => setMeetings(d.meetings || [])).catch(e => toast.error(e.message))
  }, [toast])
  const loadTemplates = useCallback(() => {
    api.committeeListAgendaTemplates().then(d => setTemplates(d.templates || [])).catch(e => toast.error(e.message))
  }, [toast])

  useEffect(() => {
    load()
    loadTemplates()
    api.committeeListPositions().then(d => setPositions(d.positions || [])).catch(() => {})
    api.adminListSeasons().then(seas => {
      const sorted = (seas || []).filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0))
      if (sorted[0]) api.feeListMembers(sorted[0].id).then(d => setMembers(d.members || [])).catch(() => {})
    }).catch(() => {})
  }, [load, loadTemplates])

  if (meetings === null) return <PbSpinner message="Loading meetings…" />
  return (
    <div>
      <p className="text-[12.5px] leading-[1.6] text-pb-faint mb-3 leading-relaxed">
        Regular committee meetings and the AGM share the same tool — an AGM meeting also gets a Nominations section where
        marking a candidate "elected" starts a real committee term for that position.
      </p>
      <AgendaTemplatesPanel templates={templates} onChanged={loadTemplates} />
      <NewMeetingForm templates={templates} onCreated={load} />
      {meetings.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No meetings yet — create one above.</div>
      ) : (
        <div className="space-y-2">
          {meetings.map(m => <MeetingRow key={m.id} meeting={m} members={members} positions={positions} onChanged={load} />)}
        </div>
      )}
    </div>
  )
}

export default function AdminCommittee() {
  const toast = useToast()
  const [tab, setTab] = useState('positions')
  const [members, setMembers] = useState([])

  // Deliberately not depending on `toast`: the context value changes whenever a
  // toast is raised, so a club without the fees module used to fail, raise a
  // toast, re-run this effect, and fail again forever.
  useEffect(() => {
    api.feeAllMembers().then(d => setMembers(d.members || [])).catch(e => toast.error(e.message))
  }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <BetterClubManagerLayout title="Committee" caption="Roles, actions, documents and meetings">
      <div className="max-w-5xl">
        <TabBar tab={tab} setTab={setTab} />
        {tab === 'positions' && <PositionsTab members={members} />}
        {tab === 'tasks' && <TasksTab members={members} />}
        {tab === 'objectives' && <ObjectivesTab />}
        {tab === 'documents' && <DocumentsTab />}
        {tab === 'calendar' && <CalendarTab />}
        {tab === 'meetings' && <MeetingsTab />}
      </div>
    </BetterClubManagerLayout>
  )
}
