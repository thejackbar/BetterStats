import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterClubManagerLayout from '../../components/admin/BetterClubManagerLayout'
import { PbSpinner } from '../../lib/presskit'
import { MemberSelect, RoleMultiSelect } from '../../components/admin/clubmanager/pickers'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

function TypeRow({ type, onChanged }) {
  const toast = useToast()
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ name: type.name, description: type.description || '', validity_months: type.validity_months ?? '' })
  const [busy, setBusy] = useState(false)

  function startEdit() {
    setForm({ name: type.name, description: type.description || '', validity_months: type.validity_months ?? '' })
    setEditing(true)
  }
  async function save() {
    if (!form.name.trim()) { toast.error('Name is required'); return }
    setBusy(true)
    try {
      await api.qualUpdateType(type.id, {
        name: form.name.trim(),
        description: form.description.trim() || null,
        validity_months: form.validity_months === '' ? null : Number(form.validity_months),
      })
      setEditing(false)
      toast.success('Type updated')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove() {
    if (!confirm(`Remove "${type.name}"? Members already holding it keep the record.`)) return
    try { await api.qualArchiveType(type.id); onChanged() } catch (e) { toast.error(e.message) }
  }

  if (editing) {
    return (
      <div className="pb-card px-3 py-2.5 space-y-2">
        <div className="flex flex-wrap gap-2">
          <input className={`${inp} flex-1 min-w-[160px]`} placeholder="Type name" value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <input type="number" min="0" className={`${inp} w-40`} placeholder="Validity (months)" value={form.validity_months}
            onChange={e => setForm(f => ({ ...f, validity_months: e.target.value }))} />
        </div>
        <input className={inp} placeholder="Description (optional)" value={form.description}
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
        <div className="flex gap-2 justify-end">
          <button onClick={() => setEditing(false)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Cancel</button>
          <button onClick={save} disabled={busy || !form.name.trim()}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'SAVING…' : 'SAVE'}
          </button>
        </div>
      </div>
    )
  }
  return (
    <div className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
      <div className="min-w-0">
        <span className="text-pb-text text-sm">{type.name}</span>
        <span className="font-mono text-[10px] text-pb-faint ml-2">{type.validity_months ? `renews every ${type.validity_months}mo` : 'no expiry'}</span>
        {type.description ? <div className="text-pb-faint text-[12px] mt-0.5 truncate">{type.description}</div> : null}
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <button onClick={startEdit} className="font-mono text-[10px] text-pb-faint hover:text-pb-accent">Edit</button>
        <button onClick={remove} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Remove</button>
      </div>
    </div>
  )
}

function TypesPanel({ types, onChanged }) {
  const toast = useToast()
  const [form, setForm] = useState({ name: '', validity_months: '' })
  const [busy, setBusy] = useState(false)
  const [seeding, setSeeding] = useState(false)

  async function submit() {
    if (!form.name.trim()) return
    setBusy(true)
    try {
      await api.qualCreateType({ name: form.name.trim(), validity_months: form.validity_months ? Number(form.validity_months) : null })
      setForm({ name: '', validity_months: '' })
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function seedStarter() {
    setSeeding(true)
    try {
      const r = await api.qualSeedStarterTypes()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} starter type${r.seeded === 1 ? '' : 's'}` : 'Already up to date')
      onChanged()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }

  return (
    <div>
      <div className="flex justify-end mb-3">
        <button onClick={seedStarter} disabled={seeding}
          className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50">
          {seeding ? 'ADDING…' : '+ STARTER SET (6 TYPES)'}
        </button>
      </div>
      <div className="pb-card p-4 mb-3">
        <div className="flex gap-2">
          <input className={`${inp} flex-1`} placeholder="Type name (e.g. Chainsaw Ticket)" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
          <input type="number" min="0" className={`${inp} w-40`} placeholder="Validity (months)" value={form.validity_months} onChange={e => setForm(f => ({ ...f, validity_months: e.target.value }))} />
          <button onClick={submit} disabled={busy || !form.name.trim()}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'ADDING…' : '+ TYPE'}
          </button>
        </div>
      </div>
      {types.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">No qualification types yet — add the starter set above.</div>
      ) : (
        <div className="space-y-1.5">
          {types.map(t => <TypeRow key={t.id} type={t} onChanged={onChanged} />)}
        </div>
      )}
    </div>
  )
}

// Roles a qualification is relevant to, shown as chips with an inline editor.
function MemberQualList({ memberId, roles, onRolesChanged }) {
  const toast = useToast()
  const [quals, setQuals] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [draftRoles, setDraftRoles] = useState([])
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    if (!memberId) { setQuals(null); return }
    api.qualListMemberQualifications(memberId).then(d => setQuals(d.qualifications || [])).catch(e => toast.error(e.message))
  }, [memberId, toast])
  useEffect(() => { load() }, [load])

  function startEdit(q) {
    setEditingId(q.id)
    setDraftRoles((q.roles || []).map(r => r.id))
  }
  async function saveRoles(q) {
    setBusy(true)
    try {
      await api.qualUpdateQualification(q.id, { role_ids: draftRoles })
      setEditingId(null)
      toast.success('Roles updated')
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }
  async function remove(q) {
    if (!confirm('Delete this qualification record?')) return
    try { await api.qualDeleteQualification(q.id); load() } catch (e) { toast.error(e.message) }
  }

  if (!memberId) return null
  return (
    <div className="mt-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">THIS MEMBER'S QUALIFICATIONS</div>
      {quals === null ? <PbSpinner message="Loading…" /> : quals.length === 0 ? (
        <div className="pb-card p-4 text-center text-pb-dim text-sm">No qualifications recorded for this member yet.</div>
      ) : (
        <div className="space-y-1.5">
          {quals.map(q => (
            <div key={q.id} className="pb-card px-3 py-2.5">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <span className="text-pb-text text-sm">{q.type_name}</span>
                  {q.expires_at ? <span className="font-mono text-[10px] text-pb-faint ml-2">expires {q.expires_at}</span> : <span className="font-mono text-[10px] text-pb-faint ml-2">no expiry</span>}
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  <button onClick={() => (editingId === q.id ? setEditingId(null) : startEdit(q))}
                    className="font-mono text-[10px] text-pb-faint hover:text-pb-accent">{editingId === q.id ? 'Cancel' : 'Edit roles'}</button>
                  <button onClick={() => remove(q)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Delete</button>
                </div>
              </div>
              {editingId === q.id ? (
                <div className="mt-2 flex flex-wrap gap-2 items-start">
                  <div className="flex-1 min-w-[200px]">
                    <RoleMultiSelect roles={roles} value={draftRoles} onChange={setDraftRoles}
                      onCreateRole={(title) => api.raCreateRole({ title }).then(r => { onRolesChanged && onRolesChanged(); return r })}
                      label="Relevant roles" />
                  </div>
                  <button onClick={() => saveRoles(q)} disabled={busy}
                    className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
                    {busy ? 'SAVING…' : 'SAVE ROLES'}
                  </button>
                </div>
              ) : (
                (q.roles && q.roles.length > 0) ? (
                  <div className="flex flex-wrap gap-1 mt-1.5">
                    {q.roles.map(r => (
                      <span key={r.id} className="inline-flex items-center bg-pb-accent/15 text-pb-accent rounded px-1.5 py-0.5 text-[11px]">{r.title}</span>
                    ))}
                  </div>
                ) : (
                  <div className="font-mono text-[10px] text-pb-faintest mt-1.5">No roles assigned</div>
                )
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AddQualificationForm({ types, members, roles, onAdded, onRolesChanged }) {
  const toast = useToast()
  const [form, setForm] = useState({ member_id: null, qualification_type_id: '', obtained_at: new Date().toISOString().slice(0, 10), certificate_ref: '' })
  const [roleIds, setRoleIds] = useState([])
  const [busy, setBusy] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  async function submit() {
    if (!form.member_id || !form.qualification_type_id) { toast.error('Member and type are required'); return }
    setBusy(true)
    try {
      await api.qualAddQualification({ ...form, role_ids: roleIds })
      setForm(f => ({ ...f, certificate_ref: '' }))
      setRoleIds([])
      toast.success('Qualification recorded')
      setReloadKey(k => k + 1)
      onAdded()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="mb-4">
      <div className="pb-card p-4">
        <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">RECORD A QUALIFICATION</div>
        <div className="flex flex-wrap gap-2">
          <div className="flex-1 min-w-[200px]">
            <MemberSelect members={members} value={form.member_id} onChange={id => setForm(f => ({ ...f, member_id: id }))} placeholder="Search for a player or member…" />
          </div>
          <select className={`${inp} flex-1 min-w-[160px]`} value={form.qualification_type_id} onChange={e => setForm(f => ({ ...f, qualification_type_id: e.target.value }))}>
            <option value="">Select type…</option>
            {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          <input type="date" className={`${inp} w-40`} value={form.obtained_at} onChange={e => setForm(f => ({ ...f, obtained_at: e.target.value }))} />
          <input className={`${inp} w-40`} placeholder="Certificate ref" value={form.certificate_ref} onChange={e => setForm(f => ({ ...f, certificate_ref: e.target.value }))} />
        </div>
        <div className="flex flex-wrap gap-2 mt-2 items-start">
          <div className="flex-1 min-w-[200px]">
            <RoleMultiSelect roles={roles} value={roleIds} onChange={setRoleIds}
              onCreateRole={(title) => api.raCreateRole({ title }).then(r => { onRolesChanged && onRolesChanged(); return r })}
              label="Relevant roles (optional)" />
          </div>
          <button onClick={submit} disabled={busy}
            className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
            {busy ? 'SAVING…' : 'RECORD'}
          </button>
        </div>
      </div>
      <MemberQualList key={reloadKey} memberId={form.member_id} roles={roles} onRolesChanged={onRolesChanged} />
    </div>
  )
}

function ExpiringPanel({ types, members, roles, onRolesChanged }) {
  const toast = useToast()
  const [report, setReport] = useState(null)

  const load = useCallback(() => {
    api.qualExpiringReport(60).then(setReport).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  async function remove(q) {
    if (!confirm('Delete this qualification record?')) return
    try { await api.qualDeleteQualification(q.id); load() } catch (e) { toast.error(e.message) }
  }

  return (
    <div>
      <AddQualificationForm types={types} members={members} roles={roles} onAdded={load} onRolesChanged={onRolesChanged} />
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-2">EXPIRED OR EXPIRING WITHIN 60 DAYS</div>
      {report === null ? <PbSpinner message="Loading…" /> : report.qualifications.length === 0 ? (
        <div className="pb-card p-6 text-center text-pb-dim text-sm">Nothing expired or expiring soon.</div>
      ) : (
        <div className="space-y-1.5">
          {report.qualifications.map(q => (
            <div key={q.id} className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
              <div>
                <span className="text-pb-text text-sm">{q.full_name}</span>
                <span className="font-mono text-[10px] text-pb-faint ml-2">{q.type_name}</span>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border ${q.is_expired ? 'text-pb-red border-pb-red/40' : 'text-pb-amber border-pb-amber/40'}`}>
                  {q.is_expired ? 'EXPIRED' : 'EXPIRES SOON'} {q.expires_at}
                </span>
                <button onClick={() => remove(q)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Remove</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AdminQualifications() {
  const toast = useToast()
  const [tab, setTab] = useState('expiring')
  const [types, setTypes] = useState(null)
  const [members, setMembers] = useState([])
  const [roles, setRoles] = useState([])

  const loadTypes = useCallback(() => {
    api.qualListTypes().then(d => setTypes(d.types || [])).catch(e => toast.error(e.message))
  }, [toast])

  const loadRoles = useCallback(() => {
    api.raRoles().then(d => setRoles(d.roles || [])).catch(() => {})
  }, [])

  useEffect(() => {
    loadTypes()
    loadRoles()
    api.feeAllMembers().then(d => setMembers(d.members || [])).catch(() => {})
  }, [loadTypes, loadRoles])

  if (types === null) return <BetterClubManagerLayout><PbSpinner message="Loading qualifications…" /></BetterClubManagerLayout>
  return (
    <BetterClubManagerLayout>
      <div className="max-w-4xl">
        <h1 className="font-display text-2xl font-bold text-pb-text mb-1">Qualifications</h1>
        <p className="font-mono text-[11px] text-pb-faint mb-5">
          Coach/umpire/scorer accreditation, WWCC, First Aid, RSA — with expiry tracking. No automated reminder emails yet;
          check this page for what needs renewing.
        </p>
        <div className="flex gap-1 mb-5">
          {[['expiring', 'Expiring / Members'], ['types', 'Types']].map(([k, l]) => (
            <button key={k} onClick={() => setTab(k)}
              className={`px-4 py-2 rounded font-mono text-[11px] tracking-wide2 ${tab === k ? 'bg-pb-surface2 text-pb-text' : 'text-pb-faint hover:text-pb-text'}`}>
              {l}
            </button>
          ))}
        </div>
        {tab === 'types' && <TypesPanel types={types} onChanged={loadTypes} />}
        {tab === 'expiring' && <ExpiringPanel types={types} members={members} roles={roles} onRolesChanged={loadRoles} />}
      </div>
    </BetterClubManagerLayout>
  )
}
