import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { FilterPill } from '../../components/admin/ui'
import { PbSpinner } from '../../lib/presskit'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

const primaryBtn = 'px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap'
const ghostBtn = 'px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50'

function ActivitiesPanel({ activities, types, onChanged }) {
  const toast = useToast()
  const [form, setForm] = useState({ title: '', activity_type_id: '', description: '' })
  const [busy, setBusy] = useState(false)
  const [seeding, setSeeding] = useState(false)
  const [editId, setEditId] = useState(null)
  const [editForm, setEditForm] = useState({ title: '', activity_type_id: '', description: '' })

  async function submit() {
    if (!form.title.trim()) return
    setBusy(true)
    try {
      await api.raCreateActivity({
        title: form.title.trim(),
        activity_type_id: form.activity_type_id || null,
        description: form.description.trim() || null,
      })
      setForm({ title: '', activity_type_id: '', description: '' })
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function seedStarter() {
    setSeeding(true)
    try {
      const r = await api.raSeedActivities()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} starter activit${r.seeded === 1 ? 'y' : 'ies'}` : 'Already up to date')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }

  function startEdit(a) {
    setEditId(a.id)
    setEditForm({ title: a.title || '', activity_type_id: a.activity_type_id || '', description: a.description || '' })
  }
  async function saveEdit(a) {
    if (!editForm.title.trim()) return
    try {
      await api.raUpdateActivity(a.id, {
        title: editForm.title.trim(),
        activity_type_id: editForm.activity_type_id || null,
        description: editForm.description.trim() || null,
      })
      setEditId(null)
      onChanged()
    } catch (e) { toast.error(e.message) }
  }
  async function remove(a) {
    if (!confirm(`Remove "${a.title}"? Hours already logged against it keep their record.`)) return
    try { await api.raArchiveActivity(a.id); onChanged() } catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      <div className="flex justify-end mb-3">
        <button onClick={seedStarter} disabled={seeding} className={ghostBtn}>
          {seeding ? 'ADDING…' : '+ STARTER SET (14 ACTIVITIES)'}
        </button>
      </div>
      <div className="pb-card p-4 mb-3">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">ADD AN ACTIVITY</div>
        <div className="flex flex-wrap gap-2">
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Activity title (e.g. Boundary line marking)" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <select className={`${inp} w-48`} value={form.activity_type_id} onChange={e => setForm(f => ({ ...f, activity_type_id: e.target.value }))}>
            <option value="">no type</option>
            {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Description (optional)" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.title.trim()} className={primaryBtn} style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ADDING…' : '+ ACTIVITY'}
          </button>
        </div>
      </div>
      {activities.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No activities yet. Add one above, or start with the starter set.</div>
      ) : (
        <div className="space-y-1.5">
          {activities.map(a => editId === a.id ? (
            <div key={a.id} className="pb-card p-3">
              <div className="flex flex-wrap gap-2">
                <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Activity title" value={editForm.title} onChange={e => setEditForm(f => ({ ...f, title: e.target.value }))} />
                <select className={`${inp} w-48`} value={editForm.activity_type_id} onChange={e => setEditForm(f => ({ ...f, activity_type_id: e.target.value }))}>
                  <option value="">no type</option>
                  {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
                </select>
                <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Description (optional)" value={editForm.description} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))} />
                <button onClick={() => saveEdit(a)} disabled={!editForm.title.trim()} className={primaryBtn} style={{ background: 'var(--pb-accent)' }}>SAVE</button>
                <button onClick={() => setEditId(null)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2">Cancel</button>
              </div>
            </div>
          ) : (
            <div key={a.id} className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
              <div className="min-w-0">
                <span className="text-pb-text text-sm">{a.title}</span>
                {a.activity_type_name && <span className="font-mono text-[10px] text-pb-faint ml-2">{a.activity_type_name}</span>}
                {a.description && <div className="text-pb-faint text-xs mt-0.5">{a.description}</div>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <button onClick={() => startEdit(a)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Edit</button>
                <button onClick={() => remove(a)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Remove</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function TypesPanel({ types, onChanged }) {
  const toast = useToast()
  const [form, setForm] = useState({ name: '', description: '' })
  const [busy, setBusy] = useState(false)
  const [seeding, setSeeding] = useState(false)
  const [editId, setEditId] = useState(null)
  const [editForm, setEditForm] = useState({ name: '', description: '' })

  async function submit() {
    if (!form.name.trim()) return
    setBusy(true)
    try {
      await api.raCreateActivityType({ name: form.name.trim(), description: form.description.trim() || null })
      setForm({ name: '', description: '' })
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function seedStarter() {
    setSeeding(true)
    try {
      const r = await api.raSeedActivityTypes()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} starter type${r.seeded === 1 ? '' : 's'}` : 'Already up to date')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }

  function startEdit(t) {
    setEditId(t.id)
    setEditForm({ name: t.name || '', description: t.description || '' })
  }
  async function saveEdit(t) {
    if (!editForm.name.trim()) return
    try {
      await api.raUpdateActivityType(t.id, { name: editForm.name.trim(), description: editForm.description.trim() || null })
      setEditId(null)
      onChanged()
    } catch (e) { toast.error(e.message) }
  }
  async function remove(t) {
    if (!confirm(`Remove "${t.name}"? Activities already using it keep the record.`)) return
    try { await api.raArchiveActivityType(t.id); onChanged() } catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      <div className="flex justify-end mb-3">
        <button onClick={seedStarter} disabled={seeding} className={ghostBtn}>
          {seeding ? 'ADDING…' : '+ STARTER SET (7 TYPES)'}
        </button>
      </div>
      <div className="pb-card p-4 mb-3">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">ADD AN ACTIVITY TYPE</div>
        <div className="flex flex-wrap gap-2">
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Type name (e.g. Ground work)" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Description (optional)" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.name.trim()} className={primaryBtn} style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ADDING…' : '+ TYPE'}
          </button>
        </div>
      </div>
      {types.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No activity types yet. Add the starter set above.</div>
      ) : (
        <div className="space-y-1.5">
          {types.map(t => editId === t.id ? (
            <div key={t.id} className="pb-card p-3">
              <div className="flex flex-wrap gap-2">
                <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Type name" value={editForm.name} onChange={e => setEditForm(f => ({ ...f, name: e.target.value }))} />
                <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Description (optional)" value={editForm.description} onChange={e => setEditForm(f => ({ ...f, description: e.target.value }))} />
                <button onClick={() => saveEdit(t)} disabled={!editForm.name.trim()} className={primaryBtn} style={{ background: 'var(--pb-accent)' }}>SAVE</button>
                <button onClick={() => setEditId(null)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text px-2">Cancel</button>
              </div>
            </div>
          ) : (
            <div key={t.id} className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
              <div className="min-w-0">
                <span className="text-pb-text text-sm">{t.name}</span>
                {t.description && <div className="text-pb-faint text-xs mt-0.5">{t.description}</div>}
              </div>
              <div className="flex items-center gap-3 shrink-0">
                <button onClick={() => startEdit(t)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Edit</button>
                <button onClick={() => remove(t)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Remove</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AdminActivities() {
  const toast = useToast()
  const [tab, setTab] = useState('activities')
  const [activities, setActivities] = useState(null)
  const [types, setTypes] = useState(null)

  const loadActivities = useCallback(() => {
    api.raActivities().then(d => setActivities(d.activities || [])).catch(e => toast.error(e.message))
  }, [toast])
  const loadTypes = useCallback(() => {
    api.raActivityTypes().then(d => setTypes(d.activity_types || d.types || [])).catch(e => toast.error(e.message))
  }, [toast])

  useEffect(() => { loadActivities(); loadTypes() }, [loadActivities, loadTypes])

  if (activities === null || types === null) {
    return <BetterClubManagerLayout title="Activities" caption="What volunteer hours are spent on"><PbSpinner message="Loading activities…" /></BetterClubManagerLayout>
  }
  return (
    <BetterClubManagerLayout title="Activities" caption="What volunteer hours are spent on">
      <div className="max-w-4xl">
        <div className="flex flex-wrap gap-1 mb-5">
          {[['activities', 'Activities'], ['types', 'Types']].map(([k, l]) => (
            <FilterPill key={k} active={tab === k} onClick={() => setTab(k)}>{l}</FilterPill>
          ))}
        </div>
        {tab === 'activities' && <ActivitiesPanel activities={activities} types={types} onChanged={loadActivities} />}
        {tab === 'types' && <TypesPanel types={types} onChanged={() => { loadTypes(); loadActivities() }} />}
      </div>
    </BetterClubManagerLayout>
  )
}
