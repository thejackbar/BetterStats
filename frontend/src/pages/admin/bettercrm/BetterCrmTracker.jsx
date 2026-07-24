import { useState, useEffect, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterCrmLayout from '../../../components/admin/BetterCrmLayout'
import { PbSpinner } from '../../../lib/presskit'
import PipelineBoard from '../../../components/admin/crm/PipelineBoard'
import DealDetailModal from '../../../components/admin/crm/DealDetailModal'
import ManageStagesModal from '../../../components/admin/crm/ManageStagesModal'
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
  setPointOfContact: api.crmSetPointOfContact,
  updatePerson: api.crmUpdatePerson,
}

const DEFAULT_TERMS = { won: 'Won', lost: 'Lost', itemSingular: 'record', itemPlural: 'records', titleLabel: 'Title' }

function NewRecordModal({ open, onClose, pipelineId, stages, terms, onCreated }) {
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
      await api.crmCreateDeal(pipelineId, {
        title: title.trim(), stage_id: stageId || undefined,
        value_cents: Math.round(Number(valueDollars || 0) * 100),
      })
      onCreated()
      onClose()
    } catch (e2) { toast.error(e2.message || `Could not add ${terms.itemSingular}`) } finally { setSaving(false) }
  }

  return (
    <Modal open={open} onClose={onClose} title={`New ${terms.itemSingular}`}>
      <form onSubmit={submit} className="space-y-3">
        <Field label={terms.titleLabel}><TextInput autoFocus value={title} onChange={e => setTitle(e.target.value)} /></Field>
        <Field label="Value ($)"><NumberInput min={0} value={valueDollars} onChange={e => setValueDollars(e.target.value)} /></Field>
        <Field label="Stage">
          <Select value={stageId} onChange={e => setStageId(e.target.value)}>
            {(stages || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </Select>
        </Field>
        <div className="flex justify-end pt-2"><Btn type="submit" variant="primary" disabled={saving}>Add {terms.itemSingular}</Btn></div>
      </form>
    </Modal>
  )
}

// The board/list view for ONE tracker (Sponsors, Grants, a custom one, …) —
// vocabulary comes live from the pipeline's own `terms` (see services/crm.py's
// PIPELINE_TEMPLATES), so this one component serves any tracker a club adds.
export default function BetterCrmTracker() {
  const { pipelineId } = useParams()
  const toast = useToast()
  const [view, setView] = useState('board')
  const [board, setBoard] = useState(null)
  const [deals, setDeals] = useState([])
  const [status, setStatus] = useState('open')
  const [loading, setLoading] = useState(true)
  const [openDealId, setOpenDealId] = useState(null)
  const [showNew, setShowNew] = useState(false)
  const [showStages, setShowStages] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    const calls = [api.crmPipelineBoard(pipelineId)]
    if (view === 'list') calls.push(api.crmListDeals(pipelineId, { status: status || undefined }))
    Promise.all(calls)
      .then(([b, d]) => { setBoard(b); if (d) setDeals(d.deals || []) })
      .catch(e => toast.error(e.message || 'Could not load tracker'))
      .finally(() => setLoading(false))
  }, [pipelineId, view, status, toast])

  useEffect(() => { load() }, [load])

  const terms = board?.pipeline?.terms || DEFAULT_TERMS
  const stages = board?.stages || []
  const stageName = (id) => stages.find(s => s.id === id)?.name || '—'
  const statusLabels = { open: 'Active', won: terms.won, lost: terms.lost, '': 'All' }

  return (
    <BetterCrmLayout title={board?.pipeline?.name || 'Tracker'}
      actions={(
        <>
          <Btn variant="ghost" sm onClick={() => setShowStages(true)}>Manage stages</Btn>
          <Btn variant="primary" sm onClick={() => setShowNew(true)}>New {terms.itemSingular}</Btn>
        </>
      )}>
      {loading && !board ? <PbSpinner message="Loading…" /> : !board ? null : (
        <>
          <div className="flex items-center gap-2 mb-4">
            <button onClick={() => setView('board')}
              className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${view === 'board' ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint'}`}>Board</button>
            <button onClick={() => setView('list')}
              className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${view === 'list' ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint'}`}>List</button>
          </div>

          {view === 'board' && <PipelineBoard board={board} onOpenDeal={setOpenDealId} onMoved={load} client={clubClient} terms={terms} />}
          {view === 'list' && (
            <>
              <div className="flex items-center gap-2 mb-4">
                {['open', 'won', 'lost', ''].map(s => (
                  <button key={s || 'all'} onClick={() => setStatus(s)}
                    className={`px-2.5 py-1 rounded-full text-[11.5px] border transition ${
                      status === s ? 'bg-pb-accent/15 border-pb-accent/50 text-pb-accent' : 'border-pb-hairline2 text-pb-faint hover:text-pb-text'}`}>
                    {statusLabels[s]}
                  </button>
                ))}
              </div>
              <div className="pb-card overflow-x-auto">
                <table className="w-full text-[13px]">
                  <thead>
                    <tr className="text-left text-pb-faint border-b border-pb-hairline">
                      <th className="px-3 py-2 font-normal">{terms.titleLabel}</th>
                      <th className="px-3 py-2 font-normal">Stage</th>
                      <th className="px-3 py-2 font-normal text-right">Value</th>
                      <th className="px-3 py-2 font-normal text-right">Weighted</th>
                      <th className="px-3 py-2 font-normal">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deals.length === 0 && (
                      <tr><td colSpan={5} className="px-3 py-6 text-center text-pb-faintest">No {terms.itemPlural} yet.</td></tr>
                    )}
                    {deals.map(d => (
                      <tr key={d.id} onClick={() => setOpenDealId(d.id)} className="border-b border-pb-hairline last:border-0 hover:bg-pb-surface2 cursor-pointer">
                        <td className="px-3 py-2.5">{d.title}</td>
                        <td className="px-3 py-2.5 text-pb-faint">{stageName(d.stage_id)}</td>
                        <td className="px-3 py-2.5 text-right">{money(d.value_cents)}</td>
                        <td className="px-3 py-2.5 text-right text-pb-faint">{money(d.weighted_value_cents)}</td>
                        <td className="px-3 py-2.5">
                          {d.status === 'won' && <Pill tone="green">{terms.won}</Pill>}
                          {d.status === 'lost' && <Pill tone="red">{terms.lost}</Pill>}
                          {d.status === 'open' && <Pill>Active</Pill>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}

      <NewRecordModal open={showNew} onClose={() => setShowNew(false)} pipelineId={pipelineId} stages={stages} terms={terms} onCreated={load} />
      <ManageStagesModal open={showStages} onClose={() => setShowStages(false)} pipelineId={pipelineId} stages={stages} onChanged={load} />
      <DealDetailModal
        dealId={openDealId} open={!!openDealId} onClose={() => setOpenDealId(null)}
        stages={stages} client={clubClient} onChanged={load} terms={terms}
      />
    </BetterCrmLayout>
  )
}
