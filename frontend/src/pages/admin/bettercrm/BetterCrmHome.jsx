import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../../lib/api'
import { useToast } from '../../../contexts/ToastContext'
import BetterCrmLayout from '../../../components/admin/BetterCrmLayout'
import { PbSpinner } from '../../../lib/presskit'
import PipelineBoard from '../../../components/admin/crm/PipelineBoard'
import DealDetailModal from '../../../components/admin/crm/DealDetailModal'

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

export default function BetterCrmHome() {
  const toast = useToast()
  const [board, setBoard] = useState(null)
  const [loading, setLoading] = useState(true)
  const [openDealId, setOpenDealId] = useState(null)

  const load = useCallback(() => {
    api.crmPipeline().then(setBoard).catch(e => toast.error(e.message || 'Could not load pipeline')).finally(() => setLoading(false))
  }, [toast])

  useEffect(() => { load() }, [load])

  const stages = board?.stages || []

  return (
    <BetterCrmLayout title="BetterCRM"
      actions={<Link to="/admin/crm/deals" className="text-[12px] font-mono text-pb-faint hover:text-pb-accent">Deals list →</Link>}>
      {loading ? <PbSpinner message="Loading pipeline…" /> : !board ? null : (
        <PipelineBoard board={board} onOpenDeal={setOpenDealId} />
      )}
      <DealDetailModal
        dealId={openDealId} open={!!openDealId} onClose={() => setOpenDealId(null)}
        stages={stages} client={clubClient} onChanged={load}
      />
    </BetterCrmLayout>
  )
}
