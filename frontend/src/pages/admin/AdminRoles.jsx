import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { PbSpinner } from '../../lib/presskit'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

function RoleRow({ r, types, editId, edit, setEdit, startEdit, saveEdit, setEditId, remove }) {
  return (
    <div className="pb-card px-3 py-2.5">
      {editId === r.id ? (
        <div className="flex flex-wrap items-center gap-2">
          <input className={`${inp} flex-1 min-w-[140px]`} value={edit.title} onChange={e => setEdit(s => ({ ...s, title: e.target.value }))} />
          <select className={`${inp} w-44`} value={edit.role_type_id} onChange={e => setEdit(s => ({ ...s, role_type_id: e.target.value }))}>
            <option value="">— no type —</option>
            {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Description" value={edit.description} onChange={e => setEdit(s => ({ ...s, description: e.target.value }))} />
          <label className="flex items-center gap-1.5 text-pb-faint text-xs shrink-0 cursor-pointer">
            <input type="checkbox" checked={edit.is_committee} onChange={e => setEdit(s => ({ ...s, is_committee: e.target.checked }))} />
            Committee role
          </label>
          <button onClick={() => saveEdit(r.id)} className="font-mono text-[10px] tracking-wide2 text-pb-accent hover:opacity-80 shrink-0">Save</button>
          <button onClick={() => setEditId(null)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text shrink-0">Cancel</button>
        </div>
      ) : (
        <div className="flex items-start justify-between gap-2">
          <div>
            <div>
              <span className="text-pb-text text-sm">{r.title}</span>
              {r.role_type_name && <span className="font-mono text-[10px] text-pb-faint ml-2">· {r.role_type_name}</span>}
            </div>
            {r.description && <div className="text-pb-faint text-xs mt-0.5">{r.description}</div>}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button onClick={() => startEdit(r)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Edit</button>
            <button onClick={() => remove(r)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Remove</button>
          </div>
        </div>
      )}
    </div>
  )
}

function RolesPanel({ roles, types, onChanged }) {
  const toast = useToast()
  const [form, setForm] = useState({ title: '', role_type_id: '', description: '', is_committee: false })
  const [busy, setBusy] = useState(false)
  const [seeding, setSeeding] = useState('')
  const [editId, setEditId] = useState(null)
  const [edit, setEdit] = useState({ title: '', role_type_id: '', description: '', is_committee: false })

  async function submit() {
    if (!form.title.trim()) return
    setBusy(true)
    try {
      await api.raCreateRole({
        title: form.title.trim(),
        role_type_id: form.role_type_id || null,
        description: form.description.trim() || null,
        is_committee: form.is_committee,
      })
      setForm({ title: '', role_type_id: '', description: '', is_committee: false })
      toast.success('Role added')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  async function seedStarter(committee) {
    setSeeding(committee ? 'committee' : 'general')
    try {
      const r = await api.raSeedRoles(committee)
      const label = committee ? 'committee' : 'general'
      toast.success(r.seeded > 0 ? `Added ${r.seeded} ${label} role${r.seeded === 1 ? '' : 's'}` : 'Already up to date')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setSeeding('') }
  }

  function startEdit(r) {
    setEditId(r.id)
    setEdit({ title: r.title || '', role_type_id: r.role_type_id || '', description: r.description || '', is_committee: !!r.is_committee })
  }
  async function saveEdit(id) {
    if (!edit.title.trim()) return
    try {
      await api.raUpdateRole(id, {
        title: edit.title.trim(),
        role_type_id: edit.role_type_id || null,
        description: edit.description.trim() || null,
        is_committee: edit.is_committee,
      })
      setEditId(null)
      toast.success('Role updated')
      onChanged()
    } catch (e) { toast.error(e.message) }
  }
  async function remove(r) {
    if (!confirm(`Remove "${r.title}"?`)) return
    try { await api.raArchiveRole(r.id); onChanged() } catch (e) { toast.error(e.message) }
  }

  const committeeRoles = roles.filter(r => r.is_committee === true)
  const generalRoles = roles.filter(r => r.is_committee === false)
  const rowProps = { types, editId, edit, setEdit, startEdit, saveEdit, setEditId, remove }

  return (
    <div>
      <div className="flex flex-wrap justify-end gap-2 mb-3">
        <button onClick={() => seedStarter(true)} disabled={!!seeding}
          className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
          {seeding === 'committee' ? 'ADDING…' : '+ COMMITTEE ROLES (14)'}
        </button>
        <button onClick={() => seedStarter(false)} disabled={!!seeding}
          className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
          {seeding === 'general' ? 'ADDING…' : '+ GENERAL ROLES (10)'}
        </button>
      </div>
      <div className="pb-card p-4 mb-4">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">ADD A ROLE</div>
        <div className="flex flex-wrap gap-2">
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Role title (e.g. Junior Coordinator)" value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
          <select className={`${inp} w-48`} value={form.role_type_id} onChange={e => setForm(f => ({ ...f, role_type_id: e.target.value }))}>
            <option value="">— no type —</option>
            {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Description (optional)" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          <label className="flex items-center gap-1.5 text-pb-faint text-xs cursor-pointer whitespace-nowrap">
            <input type="checkbox" checked={form.is_committee} onChange={e => setForm(f => ({ ...f, is_committee: e.target.checked }))} />
            Committee role
          </label>
          <button onClick={submit} disabled={busy || !form.title.trim()}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ADDING…' : '+ ROLE'}
          </button>
        </div>
      </div>

      <div className="mb-5">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">COMMITTEE ROLES</div>
        {committeeRoles.length === 0 ? (
          <div className="pb-card p-6 text-center text-pb-dim text-sm">No committee roles yet — add the committee starter set above.</div>
        ) : (
          <div className="space-y-1.5">
            {committeeRoles.map(r => <RoleRow key={r.id} r={r} {...rowProps} />)}
          </div>
        )}
      </div>

      <div>
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">GENERAL ROLES</div>
        {generalRoles.length === 0 ? (
          <div className="pb-card p-6 text-center text-pb-dim text-sm">No general roles yet — add the general starter set above.</div>
        ) : (
          <div className="space-y-1.5">
            {generalRoles.map(r => <RoleRow key={r.id} r={r} {...rowProps} />)}
          </div>
        )}
      </div>
    </div>
  )
}

function TypesPanel({ types, onChanged }) {
  const toast = useToast()
  const [form, setForm] = useState({ name: '', description: '' })
  const [busy, setBusy] = useState(false)
  const [seeding, setSeeding] = useState(false)
  const [editId, setEditId] = useState(null)
  const [edit, setEdit] = useState({ name: '', description: '' })

  async function submit() {
    if (!form.name.trim()) return
    setBusy(true)
    try {
      await api.raCreateRoleType({ name: form.name.trim(), description: form.description.trim() || null })
      setForm({ name: '', description: '' })
      toast.success('Role type added')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function seedStarter() {
    setSeeding(true)
    try {
      const r = await api.raSeedRoleTypes()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} starter type${r.seeded === 1 ? '' : 's'}` : 'Already up to date')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }
  function startEdit(t) {
    setEditId(t.id)
    setEdit({ name: t.name || '', description: t.description || '' })
  }
  async function saveEdit(id) {
    if (!edit.name.trim()) return
    try {
      await api.raUpdateRoleType(id, { name: edit.name.trim(), description: edit.description.trim() || null })
      setEditId(null)
      toast.success('Role type updated')
      onChanged()
    } catch (e) { toast.error(e.message) }
  }
  async function remove(t) {
    if (!confirm(`Remove "${t.name}"?`)) return
    try { await api.raArchiveRoleType(t.id); onChanged() } catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      <div className="flex justify-end mb-3">
        <button onClick={seedStarter} disabled={seeding}
          className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
          {seeding ? 'ADDING…' : '+ STARTER SET (5 TYPES)'}
        </button>
      </div>
      <div className="pb-card p-4 mb-3">
        <div className="flex flex-wrap gap-2">
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Type name (e.g. Coach)" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Description (optional)" value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.name.trim()}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ADDING…' : '+ TYPE'}
          </button>
        </div>
      </div>
      {types.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No role types yet — add the starter set above.</div>
      ) : (
        <div className="space-y-1.5">
          {types.map(t => (
            <div key={t.id} className="pb-card px-3 py-2.5">
              {editId === t.id ? (
                <div className="flex flex-wrap items-center gap-2">
                  <input className={`${inp} flex-1 min-w-[140px]`} value={edit.name} onChange={e => setEdit(s => ({ ...s, name: e.target.value }))} />
                  <input className={`${inp} flex-1 min-w-[140px]`} placeholder="Description" value={edit.description} onChange={e => setEdit(s => ({ ...s, description: e.target.value }))} />
                  <button onClick={() => saveEdit(t.id)} className="font-mono text-[10px] tracking-wide2 text-pb-accent hover:opacity-80 shrink-0">Save</button>
                  <button onClick={() => setEditId(null)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text shrink-0">Cancel</button>
                </div>
              ) : (
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="text-pb-text text-sm">{t.name}</span>
                    {t.description && <div className="text-pb-faint text-xs mt-0.5">{t.description}</div>}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button onClick={() => startEdit(t)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Edit</button>
                    <button onClick={() => remove(t)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Remove</button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AdminRoles() {
  const toast = useToast()
  const [tab, setTab] = useState('roles')
  const [types, setTypes] = useState(null)
  const [roles, setRoles] = useState(null)

  const loadTypes = useCallback(() => {
    api.raRoleTypes().then(d => setTypes(d.types || d.role_types || [])).catch(e => toast.error(e.message))
  }, [toast])
  const loadRoles = useCallback(() => {
    api.raRoles().then(d => setRoles(d.roles || [])).catch(e => toast.error(e.message))
  }, [toast])

  useEffect(() => { loadTypes(); loadRoles() }, [loadTypes, loadRoles])

  if (types === null || roles === null) {
    return <BetterClubManagerLayout><PbSpinner message="Loading roles…" /></BetterClubManagerLayout>
  }
  return (
    <BetterClubManagerLayout>
      <div className="max-w-4xl">
        <h1 className="text-2xl md:text-3xl font-display font-bold text-pb-text mb-1">Roles</h1>
        <p className="text-pb-faint text-sm mb-5">
          The club's role catalogue, grouped by role type. Committee roles are held as positions in Committee
          Administration, where you track who fills each one and their term. General roles are the jobs assigned
          to volunteers elsewhere in BetterClubManager.
        </p>
        <div className="flex gap-1 mb-5">
          {[['roles', 'Roles'], ['types', 'Types']].map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`px-4 py-2 rounded font-mono text-[11px] tracking-wide2 ${tab === k ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}>
              {l}
            </button>
          ))}
        </div>
        {tab === 'roles' && <RolesPanel roles={roles} types={types} onChanged={() => { loadRoles(); loadTypes() }} />}
        {tab === 'types' && <TypesPanel types={types} onChanged={() => { loadTypes(); loadRoles() }} />}
      </div>
    </BetterClubManagerLayout>
  )
}
