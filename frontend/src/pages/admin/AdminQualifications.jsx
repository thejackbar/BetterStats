import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import AdminLayout from '../../components/admin/AdminLayout'
import { PbSpinner } from '../../lib/presskit'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'

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
  async function remove(t) {
    if (!confirm(`Remove "${t.name}"? Members already holding it keep the record.`)) return
    try { await api.qualArchiveType(t.id); onChanged() } catch (e) { toast.error(e.message) }
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
          {types.map(t => (
            <div key={t.id} className="flex items-center justify-between gap-2 pb-card px-3 py-2.5">
              <div>
                <span className="text-pb-text text-sm">{t.name}</span>
                <span className="font-mono text-[10px] text-pb-faint ml-2">{t.validity_months ? `renews every ${t.validity_months}mo` : 'no expiry'}</span>
              </div>
              <button onClick={() => remove(t)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red shrink-0">Remove</button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function AddQualificationForm({ types, members, onAdded }) {
  const toast = useToast()
  const [form, setForm] = useState({ member_id: '', qualification_type_id: '', obtained_at: new Date().toISOString().slice(0, 10), certificate_ref: '' })
  const [busy, setBusy] = useState(false)

  async function submit() {
    if (!form.member_id || !form.qualification_type_id) { toast.error('Member and type are required'); return }
    setBusy(true)
    try {
      await api.qualAddQualification(form)
      setForm(f => ({ ...f, certificate_ref: '' }))
      toast.success('Qualification recorded')
      onAdded()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="pb-card p-4 mb-4">
      <div className="font-mono text-[10px] tracking-wide3 text-pb-faintest mb-1.5">RECORD A QUALIFICATION</div>
      <div className="flex flex-wrap gap-2">
        <select className={`${inp} flex-1 min-w-[160px]`} value={form.member_id} onChange={e => setForm(f => ({ ...f, member_id: e.target.value }))}>
          <option value="">Select member…</option>
          {members.map(m => <option key={m.member_id} value={m.member_id}>{m.full_name}</option>)}
        </select>
        <select className={`${inp} flex-1 min-w-[160px]`} value={form.qualification_type_id} onChange={e => setForm(f => ({ ...f, qualification_type_id: e.target.value }))}>
          <option value="">Select type…</option>
          {types.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <input type="date" className={`${inp} w-40`} value={form.obtained_at} onChange={e => setForm(f => ({ ...f, obtained_at: e.target.value }))} />
        <input className={`${inp} w-40`} placeholder="Certificate ref" value={form.certificate_ref} onChange={e => setForm(f => ({ ...f, certificate_ref: e.target.value }))} />
        <button onClick={submit} disabled={busy}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 text-pb-bg disabled:opacity-40 whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'SAVING…' : 'RECORD'}
        </button>
      </div>
    </div>
  )
}

function ExpiringPanel({ types, members }) {
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
      <AddQualificationForm types={types} members={members} onAdded={load} />
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

  const loadTypes = useCallback(() => {
    api.qualListTypes().then(d => setTypes(d.types || [])).catch(e => toast.error(e.message))
  }, [toast])

  useEffect(() => {
    loadTypes()
    api.adminListSeasons().then(seas => {
      const sorted = (seas || []).filter(s => !s.alias_of).sort((a, b) => (b.year || 0) - (a.year || 0))
      if (sorted[0]) api.feeListMembers(sorted[0].id).then(d => setMembers(d.members || [])).catch(() => {})
    }).catch(() => {})
  }, [loadTypes])

  if (types === null) return <AdminLayout><PbSpinner message="Loading qualifications…" /></AdminLayout>
  return (
    <AdminLayout>
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
        {tab === 'expiring' && <ExpiringPanel types={types} members={members} />}
      </div>
    </AdminLayout>
  )
}
