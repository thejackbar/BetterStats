import { useState, useEffect, useCallback } from 'react'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterCrmLayout from '../../../components/admin/BetterCrmLayout'
import { PbSpinner } from '../../../lib/presskit'
import DealDetailModal from '../../../components/admin/crm/DealDetailModal'
import { Modal, Field, TextInput, NumberInput, Select, Btn, Pill, money } from '../../../components/admin/crm/ui'

const clubClient = {
  getDeal: api.crmGetDeal,
  updateDeal: api.crmUpdateDeal,
  moveStage: api.crmMoveDealStage,
  closeDeal: api.crmCloseDeal,
  archiveDeal: api.crmArchiveDeal,
  listActivities: api.crmListActivities,
  addActivity: api.crmAddActivity,
  listContacts: api.crmListDealContacts,
  linkContact: api.crmLinkContact,
  unlinkContact: api.crmUnlinkContact,
}

function NewDealModal({ open, onClose, stages, onCreated }) {
  const toast = useToast()
  const [title, setTitle] = useState('')
  const [valueDollars, setValueDollars] = useState('')
  const [stageId, setStageId] = useState(stages?.[0]?.id || '')
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (open) { setTitle(''); setValueDollars(''); setStageId(stages?.[0]?.id || '') } }, [open, stages])

  const submit = async (e) => {
    e.preventDefault()
    if (!title.trim()) return
    setSaving(true)
    try {
      await api.crmCreateDeal({
        title: title.trim(), stage_id: stageId || undefined,
        value_cents: Math.round(Number(valueDollars || 0) * 100),
      })
      onCreated()
      onClose()
    } catch (e2) { toast.error(e2.message || 'Could not create deal') } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title="New deal">
      <form onSubmit={submit} className="space-y-3">
        <Field label="Title"><TextInput autoFocus value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. ABC Plumbing — annual sponsorship" /></Field>
        <Field label="Value ($)"><NumberInput min={0} value={valueDollars} onChange={e => setValueDollars(e.target.value)} /></Field>
        <Field label="Stage">
          <Select value={stageId} onChange={e => setStageId(e.target.value)}>
            {(stages || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </Field>
        <div className="flex justify-end pt-2"><Btn type="submit" variant="primary" disabled={saving}>Create deal</Btn></div>
      </form>
    </Modal>
  )
}

export default function BetterCrmDeals() {
  const toast = useToast()
  const [deals, setDeals] = useState([])
  const [stages, setStages] = useState([])
  const [status, setStatus] = useState('open')
  const [loading, setLoading] = useState(true)
  const [openDealId, setOpenDealId] = useState(null)
  const [showNew, setShowNew] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    Promise.all([api.crmListDeals({ status: status || undefined }), api.crmStages()])
      .then(([d, s]) => { setDeals(d.deals || []); setStages(s.stages || []) })
      .catch(e => toast.error(e.message || 'Could not load deals'))
      .finally(() => setLoading(false))
  }, [status, toast])

  useEffect(() => { load() }, [load])

  const stageName = (id) => stages.find(s => s.id === id)?.name || '—'

  return (
    <BetterCrmLayout title="Deals"
      actions={<Btn variant="primary" sm onClick={() => setShowNew(true)}>New deal</Btn>}>
      <div className="flex items-center gap-2 mb-4">
        {['open', 'won', 'lost', ''].map(s => (
          <button key={s || 'all'} onClick={() => setStatus(s)}
            className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
              status === s ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
            {s ? s[0].toUpperCase() + s.slice(1) : 'All'}
          </button>
        ))}
      </div>
      {loading ? <PbSpinner message="Loading deals…" /> : (
        <div className="pb-card overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-left text-pb-faint border-b border-pb-hairline">
                <th className="px-3 py-2 font-normal">Title</th>
                <th className="px-3 py-2 font-normal">Stage</th>
                <th className="px-3 py-2 font-normal text-right">Value</th>
                <th className="px-3 py-2 font-normal text-right">Weighted</th>
                <th className="px-3 py-2 font-normal">Status</th>
              </tr>
            </thead>
            <tbody>
              {deals.length === 0 && (
                <tr><td colSpan={5} className="px-3 py-6 text-center text-pb-faintest">No deals yet.</td></tr>
              )}
              {deals.map(d => (
                <tr key={d.id} onClick={() => setOpenDealId(d.id)} className="border-b border-pb-hairline last:border-0 hover:bg-pb-surface2 cursor-pointer">
                  <td className="px-3 py-2.5">{d.title}</td>
                  <td className="px-3 py-2.5 text-pb-faint">{stageName(d.stage_id)}</td>
                  <td className="px-3 py-2.5 text-right">{money(d.value_cents)}</td>
                  <td className="px-3 py-2.5 text-right text-pb-faint">{money(d.weighted_value_cents)}</td>
                  <td className="px-3 py-2.5">
                    {d.status === 'won' && <Pill tone="green">Won</Pill>}
                    {d.status === 'lost' && <Pill tone="red">Lost</Pill>}
                    {d.status === 'open' && <Pill>Open</Pill>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <NewDealModal open={showNew} onClose={() => setShowNew(false)} stages={stages} onCreated={load} />
      <DealDetailModal
        dealId={openDealId} open={!!openDealId} onClose={() => setOpenDealId(null)}
        stages={stages} client={clubClient} onChanged={load}
      />
    </BetterCrmLayout>
  )
}
