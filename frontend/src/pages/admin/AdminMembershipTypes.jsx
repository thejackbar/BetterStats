import { useState, useEffect, useCallback } from 'react'
import { api } from '../../lib/api'
import { useToast } from '../../contexts/ToastContext'
import BetterFeesLayout from '../../components/admin/BetterFeesLayout'
import { PbSpinner } from '../../lib/presskit'

const inp = 'w-full bg-pb-surface2 border pb-hairline rounded px-2.5 py-1.5 text-pb-text text-sm focus:outline-none focus:border-pb-accent'
const money = n => n == null ? '—' : `$${Number(n).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`

function FlagPill({ on, children }) {
  return (
    <span className={`font-mono text-[9px] tracking-wide2 rounded px-1.5 py-0.5 border ${
      on ? 'text-pb-accent border-pb-accent/40' : 'text-pb-faintest border pb-hairline'}`}>
      {children}
    </span>
  )
}

function TypeForm({ initial, onSubmit, onCancel, busy }) {
  const [form, setForm] = useState(initial || {
    name: '', description: '', default_annual_fee: '', is_playing: false,
    requires_voting_rights: false, requires_insurance: false, requires_wwcc: false,
    requires_playhq_registration: false, comms_group: '',
  })
  return (
    <div className="pb-card p-4 space-y-3">
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">NAME</label>
        <input autoFocus className={inp} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
      </div>
      <div>
        <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">DESCRIPTION</label>
        <input className={inp} value={form.description || ''} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">DEFAULT ANNUAL FEE ($)</label>
          <input type="number" min="0" className={inp} value={form.default_annual_fee || ''}
            onChange={e => setForm(f => ({ ...f, default_annual_fee: e.target.value }))} />
        </div>
        <div>
          <label className="font-mono text-[10px] tracking-wide3 text-pb-faint mb-1 block">COMMS GROUP</label>
          <input className={inp} value={form.comms_group || ''} onChange={e => setForm(f => ({ ...f, comms_group: e.target.value }))} />
        </div>
      </div>
      <div className="flex flex-wrap gap-3">
        {[
          ['is_playing', 'Playing member'],
          ['requires_voting_rights', 'Voting rights'],
          ['requires_insurance', 'Insurance required'],
          ['requires_wwcc', 'WWCC required'],
          ['requires_playhq_registration', 'PlayHQ registration required'],
        ].map(([key, label]) => (
          <label key={key} className="flex items-center gap-2 font-mono text-[11px] text-pb-dim cursor-pointer select-none">
            <input type="checkbox" checked={!!form[key]} onChange={e => setForm(f => ({ ...f, [key]: e.target.checked }))} />
            {label}
          </label>
        ))}
      </div>
      <div className="flex gap-2 pt-1">
        <button onClick={() => onSubmit(form)} disabled={busy || !form.name.trim()}
          className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
          {busy ? 'SAVING…' : 'SAVE'}
        </button>
        <button onClick={onCancel} className="px-3 py-2 rounded font-mono text-[10px] border pb-hairline text-pb-faint hover:text-pb-text">CANCEL</button>
      </div>
    </div>
  )
}

export default function AdminMembershipTypes() {
  const toast = useToast()
  const [types, setTypes] = useState(null)
  const [showNew, setShowNew] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [busy, setBusy] = useState(false)
  const [seeding, setSeeding] = useState(false)

  const load = useCallback(() => {
    api.feeListMembershipTypes().then(d => setTypes(d.types || [])).catch(e => toast.error(e.message))
  }, [toast])
  useEffect(() => { load() }, [load])

  const create = async (form) => {
    setBusy(true)
    try {
      await api.feeCreateMembershipType({
        ...form, default_annual_fee: form.default_annual_fee === '' ? null : Number(form.default_annual_fee),
      })
      toast.success('Membership type added')
      setShowNew(false)
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const update = async (id, form) => {
    setBusy(true)
    try {
      await api.feeUpdateMembershipType(id, {
        ...form, default_annual_fee: form.default_annual_fee === '' ? null : Number(form.default_annual_fee),
      })
      toast.success('Saved')
      setEditingId(null)
      load()
    } catch (e) { toast.error(e.message) } finally { setBusy(false) }
  }

  const archive = async (t) => {
    if (!window.confirm(`Remove "${t.name}"? Members already holding it keep the reference. This just hides it from new assignments.`)) return
    try { await api.feeArchiveMembershipType(t.id); load() } catch (e) { toast.error(e.message) }
  }

  const seedStarter = async () => {
    setSeeding(true)
    try {
      const r = await api.feeSeedStarterMembershipTypes()
      toast.success(r.seeded > 0 ? `Added ${r.seeded} starter type${r.seeded === 1 ? '' : 's'}` : 'Already up to date')
      load()
    } catch (e) { toast.error(e.message) } finally { setSeeding(false) }
  }

  return (
    <BetterFeesLayout>
      <div className="max-w-4xl">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
          <div>
            <h1 className="font-display font-bold text-2xl text-pb-text mb-1">Membership Types</h1>
            <p className="text-pb-faint text-sm">
              Optional: only adopt what your club actually uses. Senior/Junior Player, Parent, Life Member, Coach,
              Committee Member and more, or build your own.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={seedStarter} disabled={seeding}
              className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 border pb-hairline text-pb-faint hover:text-pb-text hover:border-pb-accent transition-colors disabled:opacity-50 whitespace-nowrap">
              {seeding ? 'ADDING…' : '+ STARTER SET'}
            </button>
            <button onClick={() => setShowNew(true)}
              className="px-3 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg whitespace-nowrap" style={{ background: 'var(--pb-accent)' }}>
              + TYPE
            </button>
          </div>
        </div>

        {showNew && <div className="mb-4"><TypeForm onSubmit={create} onCancel={() => setShowNew(false)} busy={busy} /></div>}

        {types === null ? <PbSpinner message="Loading membership types…" /> : types.length === 0 && !showNew ? (
          <div className="pb-card p-6 text-center">
            <p className="text-pb-dim text-sm mb-3">No membership types yet.</p>
            <button onClick={seedStarter} disabled={seeding}
              className="px-4 py-2 rounded font-mono text-[10px] tracking-wide2 font-semibold text-pb-bg disabled:opacity-50" style={{ background: 'var(--pb-accent)' }}>
              {seeding ? 'ADDING…' : 'ADD STARTER SET (13 TYPES)'}
            </button>
          </div>
        ) : (
          <div className="space-y-2">
            {types.map(t => editingId === t.id ? (
              <TypeForm key={t.id} initial={{ ...t, default_annual_fee: t.default_annual_fee ?? '' }}
                onSubmit={form => update(t.id, form)} onCancel={() => setEditingId(null)} busy={busy} />
            ) : (
              <div key={t.id} className="pb-card px-4 py-3">
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <div className="text-pb-text font-semibold text-sm">{t.name}</div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="font-mono text-[11px] text-pb-faint">{money(t.default_annual_fee)}</span>
                    <button onClick={() => setEditingId(t.id)} className="font-mono text-[10px] text-pb-faint hover:text-pb-text">Edit</button>
                    <button onClick={() => archive(t)} className="font-mono text-[10px] text-pb-faint hover:text-pb-red">Remove</button>
                  </div>
                </div>
                {t.description && <p className="text-pb-faint text-[12px] mb-2">{t.description}</p>}
                <div className="flex flex-wrap gap-1.5">
                  <FlagPill on={t.is_playing}>Playing</FlagPill>
                  <FlagPill on={t.requires_voting_rights}>Voting</FlagPill>
                  <FlagPill on={t.requires_insurance}>Insurance</FlagPill>
                  <FlagPill on={t.requires_wwcc}>WWCC</FlagPill>
                  <FlagPill on={t.requires_playhq_registration}>PlayHQ reg.</FlagPill>
                  {t.comms_group && <FlagPill on>{t.comms_group}</FlagPill>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </BetterFeesLayout>
  )
}
