import { useState } from 'react'
import { useToast } from '../../../contexts/ToastContext'
import { money, Pill, DEFAULT_CRM_TERMS } from './ui'

export const TIER_TONE = { HOT: 'red', WARM: 'amber', COLD: 'faint', NOT_INTERESTED: 'faint' }

// A Kanban-style pipeline board — one column per stage, drag-and-drop
// enabled (native HTML5 DnD, no library) between any two columns. `client`
// (the same scope-specific api.js bundle DealDetailModal takes) is what
// actually moves the deal on drop; `onMoved` lets the caller refresh its
// own state afterward. Clicking a card still opens the detail modal for
// everything DnD doesn't cover (won/lost, notes, contacts…).
export default function PipelineBoard({ board, onOpenDeal, onMoved, client, terms }) {
  const toast = useToast()
  const [draggingId, setDraggingId] = useState(null)
  const [overStageId, setOverStageId] = useState(null)
  if (!board) return null
  const { stages, totals } = board
  const visibleStages = stages.filter(s => !s.hidden_from_board)
  const t = { ...DEFAULT_CRM_TERMS, ...terms }

  const drop = async (stageId) => {
    setOverStageId(null)
    const dealId = draggingId
    setDraggingId(null)
    if (!dealId || !client?.moveStage) return
    // No-op drop back onto the same column a card already sits in.
    const currentStage = stages.find(s => s.deals.some(d => d.id === dealId))
    if (currentStage && currentStage.id === stageId) return
    try {
      await client.moveStage(dealId, { stage_id: stageId })
      onMoved?.()
    } catch (e) { toast.error(e.message || 'Could not move stage') }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <div className="pb-card px-4 py-3 border-pb-accent/40">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Open pipeline value</div>
          <div className="font-display font-bold text-xl" style={{ color: 'var(--pb-accent)' }}>{money(totals.open_value_cents)}</div>
        </div>
        <div className="pb-card px-4 py-3">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Weighted value</div>
          <div className="font-display font-bold text-xl">{money(totals.weighted_value_cents)}</div>
        </div>
        <div className="pb-card px-4 py-3">
          <div className="font-mono text-[10px] tracking-wide3 text-pb-faint uppercase mb-1">Open {t.itemPlural}</div>
          <div className="font-display font-bold text-xl">{totals.open_count}</div>
        </div>
      </div>
      {visibleStages.length < stages.length && (
        <p className="text-[11px] text-pb-faintest -mt-2">
          {stages.length - visibleStages.length} stage{stages.length - visibleStages.length === 1 ? '' : 's'} hidden from
          the board (totals above still include them) — unhide from Manage stages.
        </p>
      )}

      <div className="flex gap-3 overflow-x-auto pb-2">
        {visibleStages.map(stage => (
          <div key={stage.id} className="w-64 shrink-0"
            onDragOver={e => { if (draggingId) { e.preventDefault(); setOverStageId(stage.id) } }}
            onDragLeave={() => setOverStageId(id => (id === stage.id ? null : id))}
            onDrop={e => { e.preventDefault(); drop(stage.id) }}>
            <div className="flex items-center justify-between mb-2 px-1">
              <div className="flex items-center gap-1.5 min-w-0">
                <h3 className="font-display font-bold text-[13px] truncate">{stage.name}</h3>
                <Pill>{stage.deal_count}</Pill>
              </div>
              {stage.value_cents > 0 && <span className="text-[11px] text-pb-faint shrink-0">{money(stage.value_cents)}</span>}
            </div>
            <div className={`space-y-2 min-h-[60px] rounded-lg transition ${
              overStageId === stage.id ? 'ring-2 ring-pb-accent/50 bg-pb-accent/5' : ''}`}>
              {stage.deals.length === 0 && (
                <div className="pb-card px-3 py-4 text-center text-[11.5px] text-pb-faintest border-dashed">No {t.itemPlural}</div>
              )}
              {stage.deals.map(deal => (
                <div key={deal.id} draggable={!!client?.moveStage}
                  onDragStart={e => { setDraggingId(deal.id); e.dataTransfer.effectAllowed = 'move' }}
                  onDragEnd={() => { setDraggingId(null); setOverStageId(null) }}
                  onClick={() => onOpenDeal(deal.id)}
                  className={`pb-card w-full text-left px-3 py-2.5 hover:border-pb-accent/40 transition cursor-pointer ${
                    deal.status !== 'open' ? 'opacity-60' : ''} ${draggingId === deal.id ? 'opacity-40' : ''}`}>
                  <div className="font-medium text-[13px] truncate mb-1">{deal.title}</div>
                  {deal.point_of_contact_name && (
                    <div className="text-[11px] text-pb-faint truncate mb-1">{deal.point_of_contact_name}</div>
                  )}
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[12px] text-pb-faint">{money(deal.value_cents)}</span>
                    {deal.effective_probability != null && (
                      <span className="font-mono text-[10.5px] text-pb-faintest">{deal.effective_probability}%</span>
                    )}
                  </div>
                  {(deal.module_keys?.length > 0 || deal.engagement_score != null) && (
                    <div className="flex flex-wrap gap-1 mt-1.5">
                      {deal.engagement_score != null && (
                        <Pill tone={TIER_TONE[deal.engagement_tier] || 'faint'}>{deal.engagement_score}</Pill>
                      )}
                      {(deal.module_keys || []).map(k => <Pill key={k} tone="accent">{k}</Pill>)}
                    </div>
                  )}
                  {deal.status === 'won' && <Pill tone="green">{t.won}</Pill>}
                  {deal.status === 'lost' && <Pill tone="red">{t.lost}</Pill>}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
